from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List, Optional, Set, Tuple, get_args

from pydantic import ValidationError

from engine import WorkflowEngine
from event_bus import EventBus
from schema import ConfigType, FieldRole, FlowType, NativeType, OptionsType, SourceMeta, Workflow, WorkflowNodeUnion
from toolkit_runtime import load_numel_toolkit


_STRUCTURAL_FIELDS = {"type", "id", "extra"}
_NODE_CLASS_BY_TYPE: Dict[str, type] = {}
for _node_cls in get_args(WorkflowNodeUnion):
	type_field = getattr(_node_cls, "model_fields", {}).get("type")
	type_name = getattr(type_field, "default", None)
	if type_name:
		_NODE_CLASS_BY_TYPE[str(type_name)] = _node_cls


def _workflow_model_from_doc(doc: Dict[str, Any]) -> Workflow:
	payload = dict(doc or {})
	payload.pop("type", None)
	if hasattr(Workflow, "model_validate"):
		return Workflow.model_validate(payload)
	if hasattr(Workflow, "parse_obj"):
		return Workflow.parse_obj(payload)
	return Workflow(**payload)


def _node_label(idx: int, node_like: Any) -> str:
	node_type = getattr(node_like, "type", None)
	extra = getattr(node_like, "extra", None)
	if isinstance(node_like, dict):
		node_type = node_like.get("type", node_type)
		extra = node_like.get("extra", extra)
	name = ""
	if isinstance(extra, dict):
		name = str(extra.get("name", "") or "").strip()
	if name:
		return f"node {idx} ({name})"
	return f"node {idx} ({node_type or '?'})"


def _looks_module_like(value: str) -> bool:
	text = str(value or "").strip()
	return bool(text) and any(ch in text for ch in (".", "/", "\\")) and " " not in text


def _looks_tool_like(value: str) -> bool:
	text = str(value or "").strip()
	return text.startswith("@") or _looks_module_like(text)


def _compact_validation_errors(exc: ValidationError) -> List[str]:
	errors: List[str] = []
	for item in exc.errors():
		loc = ".".join(str(part) for part in item.get("loc", ()))
		msg = str(item.get("msg", "Invalid value"))
		errors.append(f"{loc}: {msg}" if loc else msg)
	return errors or [str(exc)]


def _slot_base(slot: Any) -> str:
	return str(slot or "").split(".", 1)[0].strip()


def _replace_slot_base(slot: Any, new_base: str) -> str:
	text = str(slot or "")
	if "." in text:
		_, suffix = text.split(".", 1)
		return f"{new_base}.{suffix}"
	return new_base


def _field_roles(field_info: Any) -> Set[FieldRole]:
	roles: Set[FieldRole] = set()
	for meta in getattr(field_info, "metadata", ()) or ():
		if isinstance(meta, FieldRole):
			roles.add(meta)
	return roles


def _input_slots_for_class(node_cls: Optional[type]) -> Set[str]:
	if node_cls is None:
		return set()
	slots: Set[str] = set()
	for name, field_info in getattr(node_cls, "model_fields", {}).items():
		if name in _STRUCTURAL_FIELDS:
			continue
		roles = _field_roles(field_info)
		if FieldRole.INPUT in roles or FieldRole.MULTI_INPUT in roles:
			slots.add(name)
	return slots


def _output_slots_for_class(node_cls: Optional[type]) -> Set[str]:
	if node_cls is None:
		return set()
	slots: Set[str] = set()
	for name, field_info in getattr(node_cls, "model_fields", {}).items():
		if name in _STRUCTURAL_FIELDS:
			continue
		roles = _field_roles(field_info)
		if FieldRole.OUTPUT in roles or FieldRole.MULTI_OUTPUT in roles:
			slots.add(name)
	return slots


def _property_output_slot(node_cls: Optional[type]) -> Optional[str]:
	if node_cls is None:
		return None
	for name in ("value", "config", "reference", "options", "get"):
		if isinstance(getattr(node_cls, name, None), property):
			return name
	return None


def _slot_allowed_for_source(node_type: str, slot: Any) -> bool:
	node_cls = _NODE_CLASS_BY_TYPE.get(str(node_type or ""))
	base = _slot_base(slot)
	if not node_cls or not base:
		return True
	if base in _output_slots_for_class(node_cls):
		return True
	return isinstance(getattr(node_cls, base, None), property)


def _slot_allowed_for_target(node_type: str, slot: Any) -> bool:
	node_cls = _NODE_CLASS_BY_TYPE.get(str(node_type or ""))
	base = _slot_base(slot)
	if not node_cls or not base:
		return True
	return base in _input_slots_for_class(node_cls)


def _preferred_source_slot(node_type: str) -> Optional[str]:
	node_cls = _NODE_CLASS_BY_TYPE.get(str(node_type or ""))
	if node_cls is None:
		return None
	if issubclass(node_cls, FlowType):
		return "flow_out"
	prop_slot = _property_output_slot(node_cls)
	if prop_slot:
		return prop_slot
	output_slots = sorted(_output_slots_for_class(node_cls))
	return output_slots[0] if len(output_slots) == 1 else None


def _preferred_target_slot(node_type: str) -> Optional[str]:
	node_cls = _NODE_CLASS_BY_TYPE.get(str(node_type or ""))
	if node_cls is None:
		return None
	if issubclass(node_cls, FlowType):
		return "flow_in"
	input_slots = sorted(_input_slots_for_class(node_cls))
	return input_slots[0] if len(input_slots) == 1 else None


def _repair_source_slot(node_type: str, slot: Any) -> Optional[str]:
	if _slot_base(slot) != "flow_out":
		return None
	preferred = _preferred_source_slot(node_type)
	if not preferred or preferred == "flow_out":
		return None
	return _replace_slot_base(slot, preferred)


def _repair_target_slot(source_type: str, target_type: str, source_slot: Any, target_slot: Any) -> Tuple[Optional[str], Optional[str]]:
	if _slot_base(target_slot) != "flow_in":
		return None, None
	source_cls = _NODE_CLASS_BY_TYPE.get(str(source_type or ""))
	target_cls = _NODE_CLASS_BY_TYPE.get(str(target_type or ""))
	if source_cls and target_cls and issubclass(source_cls, FlowType) and not issubclass(target_cls, FlowType):
		return None, "drop"
	preferred = _preferred_target_slot(target_type)
	if not preferred or preferred == "flow_in":
		return None, None
	return _replace_slot_base(target_slot, preferred), None


def _normalize_edge_slots(working: Dict[str, Any], *, apply_repairs: bool) -> List[str]:
	repairs: List[str] = []
	nodes = working.get("nodes") or []
	edges = working.get("edges") or []
	sanitized_edges: List[Any] = []
	for idx, edge in enumerate(edges):
		if not isinstance(edge, dict):
			sanitized_edges.append(edge)
			continue

		source_idx = edge.get("source")
		target_idx = edge.get("target")
		source_node = nodes[source_idx] if isinstance(source_idx, int) and 0 <= source_idx < len(nodes) else None
		target_node = nodes[target_idx] if isinstance(target_idx, int) and 0 <= target_idx < len(nodes) else None
		source_type = str(source_node.get("type", "") or "") if isinstance(source_node, dict) else ""
		target_type = str(target_node.get("type", "") or "") if isinstance(target_node, dict) else ""
		source_slot = str(edge.get("source_slot", "") or "")
		target_slot = str(edge.get("target_slot", "") or "")

		if apply_repairs and source_type and source_slot and not _slot_allowed_for_source(source_type, source_slot):
			repaired_slot = _repair_source_slot(source_type, source_slot)
			if repaired_slot:
				edge["source_slot"] = repaired_slot
				repairs.append(
					f"edges.{idx}: rewired source slot {source_type}.{source_slot} -> {source_type}.{repaired_slot}"
				)
				source_slot = repaired_slot

		if apply_repairs and target_type and target_slot and not _slot_allowed_for_target(target_type, target_slot):
			repaired_slot, action = _repair_target_slot(source_type, target_type, source_slot, target_slot)
			if action == "drop":
				repairs.append(
					f"edges.{idx}: removed invalid flow edge into non-flow node {target_type}.{target_slot}"
				)
				continue
			if repaired_slot:
				edge["target_slot"] = repaired_slot
				repairs.append(
					f"edges.{idx}: rewired target slot {target_type}.{target_slot} -> {target_type}.{repaired_slot}"
				)

		sanitized_edges.append(edge)

	working["edges"] = sanitized_edges
	return repairs


def _edge_slot_validation(workflow_doc: Dict[str, Any]) -> List[str]:
	errors: List[str] = []
	nodes = workflow_doc.get("nodes") or []
	edges = workflow_doc.get("edges") or []
	for idx, edge in enumerate(edges):
		if not isinstance(edge, dict):
			continue
		source_idx = edge.get("source")
		target_idx = edge.get("target")
		source_node = nodes[source_idx] if isinstance(source_idx, int) and 0 <= source_idx < len(nodes) else None
		target_node = nodes[target_idx] if isinstance(target_idx, int) and 0 <= target_idx < len(nodes) else None
		if isinstance(source_node, dict):
			source_type = str(source_node.get("type", "") or "")
			source_slot = str(edge.get("source_slot", "") or "")
			if source_slot and not _slot_allowed_for_source(source_type, source_slot):
				errors.append(
					f"edge {idx} reads invalid slot '{source_slot}' from {source_type}. "
					f"Use '{_preferred_source_slot(source_type) or 'a valid output slot'}' instead."
				)
		if isinstance(target_node, dict):
			target_type = str(target_node.get("type", "") or "")
			target_slot = str(edge.get("target_slot", "") or "")
			if target_slot and not _slot_allowed_for_target(target_type, target_slot):
				errors.append(
					f"edge {idx} writes to invalid slot '{target_slot}' on {target_type}. "
					f"Use '{_preferred_target_slot(target_type) or 'a valid input slot'}' instead."
				)
	return errors


def normalize_workflow_payload(payload: Dict[str, Any], *, apply_repairs: bool = True) -> tuple[Dict[str, Any], List[str]]:
	working = deepcopy(payload if isinstance(payload, dict) else {})
	repairs: List[str] = []

	working.setdefault("type", "workflow")
	if not isinstance(working.get("edges"), list):
		working["edges"] = []
		repairs.append("workflow: created missing edges array")
	if not isinstance(working.get("nodes"), list):
		working["nodes"] = []

	for idx, node in enumerate(working.get("nodes", [])):
		if not isinstance(node, dict):
			continue

		if apply_repairs and ("extra" not in node or not isinstance(node.get("extra"), dict)):
			x = node.pop("x", 0)
			y = node.pop("y", 0)
			label = node.pop("name", node.get("type", ""))
			node["extra"] = {"pos": [x, y], "name": label}
			repairs.append(f"nodes.{idx}: normalized x/y/name into extra")

		fields = node.pop("fields", None) if apply_repairs else None
		if apply_repairs and isinstance(fields, dict):
			node.update(fields)
			repairs.append(f"nodes.{idx}: merged legacy fields into node body")

		extra = node.get("extra") or {}
		display_name = str(extra.get("name", "") or "").strip()
		node_type = str(node.get("type", "") or "").strip()
		current_name = str(node.get("name", "") or "").strip()

		if apply_repairs and node_type == "toolkit_config" and not current_name and _looks_module_like(display_name):
			node["name"] = display_name
			repairs.append(f"nodes.{idx}: recovered toolkit_config.name from extra.name")
		elif apply_repairs and node_type == "tool_config" and not current_name and _looks_tool_like(display_name):
			node["name"] = display_name
			repairs.append(f"nodes.{idx}: recovered tool_config.name from extra.name")
		elif apply_repairs and node_type == "skill_config" and not current_name and display_name:
			node["name"] = display_name
			repairs.append(f"nodes.{idx}: recovered skill_config.name from extra.name")

	repairs.extend(_normalize_edge_slots(working, apply_repairs=apply_repairs))

	return working, repairs


def _semantic_validation(workflow: Workflow, workflow_doc: Dict[str, Any]) -> tuple[List[str], List[str]]:
	errors: List[str] = []
	warnings: List[str] = []
	nodes = list(getattr(workflow, "nodes", []) or [])
	edges = list(getattr(workflow, "edges", []) or [])

	for edge in edges:
		try:
			source = int(edge.source)
			target = int(edge.target)
		except Exception:
			errors.append("Edge source/target must be integer node indexes")
			continue
		if source < 0 or source >= len(nodes):
			errors.append(f"Edge references missing source node index {source}")
		if target < 0 or target >= len(nodes):
			errors.append(f"Edge references missing target node index {target}")

	def incoming_edges(node_idx: int, slot: str) -> List[Any]:
		return [
			edge
			for edge in edges
			if getattr(edge, "target", None) == node_idx and str(getattr(edge, "target_slot", "") or "") == slot
		]

	config_rules = {
		"tool_flow": {"allowed": {"tool_config", "toolkit_config"}},
		"agent_flow": {"allowed": {"agent_config"}},
		"tool_call": {"allowed": {"tool_config"}},
		"agent_chat": {"allowed": {"agent_config"}},
	}

	for idx, node in enumerate(nodes):
		node_type = str(getattr(node, "type", "") or "")
		if node_type not in config_rules:
			continue
		label = _node_label(idx, node)
		slot_edges = incoming_edges(idx, "config")
		inline_config = getattr(node, "config", None)

		if inline_config is None and not slot_edges:
			errors.append(f"{label} has no config. Connect a config node to its config input.")
			continue
		if len(slot_edges) > 1:
			errors.append(f"{label} has multiple config inputs. Keep only one config source.")
			continue

		source_node = None
		source_type = None
		config_obj = inline_config
		if slot_edges:
			source_idx = int(slot_edges[0].source)
			if 0 <= source_idx < len(nodes):
				source_node = nodes[source_idx]
				source_type = str(getattr(source_node, "type", "") or "")
				config_obj = source_node
			else:
				errors.append(f"{label} receives config from missing node index {source_idx}.")
				continue

		if source_type and source_type not in config_rules[node_type]["allowed"]:
			errors.append(
				f"{label} expects {', '.join(sorted(config_rules[node_type]['allowed']))} on config, "
				f"but received {source_type}."
			)
			continue

		if node_type == "tool_call":
			name = str(getattr(config_obj, "name", "") or "").strip() if config_obj is not None else ""
			script = str(getattr(config_obj, "script", "") or "").strip() if config_obj is not None else ""
			if not name and not script:
				errors.append(f"{label} points to a tool_config without a name or inline script.")
			continue

		if node_type != "tool_flow":
			continue

		method = str(getattr(node, "method", "") or "").strip()
		config_type = str(getattr(config_obj, "type", "") or "")

		if config_type == "tool_config":
			name = str(getattr(config_obj, "name", "") or "").strip()
			script = str(getattr(config_obj, "script", "") or "").strip()
			if not name and not script:
				errors.append(f"{label} points to a tool_config without a name or inline script.")
			if method:
				warnings.append(f"{label} sets method '{method}', but method is ignored for tool_config.")
			continue

		if config_type != "toolkit_config":
			continue

		toolkit_name = str(getattr(config_obj, "name", "") or "").strip()
		if not toolkit_name:
			errors.append(f"{label} points to a toolkit_config without a toolkit name.")
			continue
		if not method:
			errors.append(f"{label} points to toolkit '{toolkit_name}' but does not set method.")
			continue

		record = load_numel_toolkit(
			toolkit_name,
			getattr(config_obj, "args", None) or {},
			log_prefix="Validation toolkit",
			quiet=True,
		)
		if record is None:
			errors.append(f"{label} references toolkit '{toolkit_name}', but it could not be loaded.")
			continue

		method_names = sorted({tool.__name__ for tool in record.get("tools", [])})
		if method not in method_names:
			preview = ", ".join(method_names[:8])
			if len(method_names) > 8:
				preview += ", ..."
			errors.append(
				f"{label} uses unknown toolkit method '{method}' for '{toolkit_name}'. "
				f"Available methods: {preview or '(none)'}."
			)

	return errors, warnings


def validate_workflow_payload(payload: Dict[str, Any], *, apply_repairs: bool = True) -> Dict[str, Any]:
	workflow_doc, repairs = normalize_workflow_payload(payload, apply_repairs=apply_repairs)
	pre_model_errors = _edge_slot_validation(workflow_doc)

	try:
		workflow = _workflow_model_from_doc(workflow_doc)
	except ValidationError as exc:
		return {
			"valid": False,
			"workflow": workflow_doc,
			"errors": pre_model_errors + _compact_validation_errors(exc),
			"warnings": [],
			"repairs": repairs,
			"repaired": bool(repairs),
		}

	engine_validation = WorkflowEngine(EventBus()).validate_workflow(workflow)
	errors = list(pre_model_errors)
	errors.extend(list(engine_validation.get("errors", []) or []))
	warnings = list(engine_validation.get("warnings", []) or [])
	semantic_errors, semantic_warnings = _semantic_validation(workflow, workflow_doc)
	errors.extend(semantic_errors)
	warnings.extend(semantic_warnings)

	return {
		"valid": not errors,
		"workflow": workflow_doc,
		"errors": errors,
		"warnings": warnings,
		"repairs": repairs,
		"repaired": bool(repairs),
	}
