from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import urlencode

from workflow_validation import validate_workflow_payload


class InteropImportError(ValueError):
	def __init__(self, message: str, *, detail: Any = None):
		super().__init__(message)
		self.detail = detail if detail is not None else message


@dataclass
class _Component:
	key: str
	label: str
	entry: Optional[int]
	exit: Optional[int]
	data_inputs: Optional[List[Tuple[int, str]]] = None
	data_output: Optional[Tuple[int, str]] = None
	branch_outputs: Optional[Dict[int, Tuple[int, str]]] = None
	dynamic_input_slot_kind: Optional[str] = None


_NUMEL_TYPE_PREFIXES = (
	"agent_",
	"backend_",
	"browser_",
	"channel_",
	"content_",
	"eval_",
	"event_",
	"fswatch_",
	"history_",
	"knowledge_",
	"loop_",
	"memory_",
	"model_",
	"native_",
	"notify_",
	"session_",
	"skill_",
	"start_",
	"end_",
	"timer_",
	"tool_",
	"toolkit_",
	"transform_",
	"user_",
	"webhook_",
)
_N8N_MANUAL_TYPES = {"manualtrigger", "start"}
_N8N_WEBHOOK_TYPES = {"webhook"}
_N8N_SET_TYPES = {"set", "editfields"}
_N8N_IF_TYPES = {"if"}
_N8N_MERGE_TYPES = {"merge"}
_N8N_CODE_TYPES = {"code", "function", "functionitem"}
_N8N_HTTP_TYPES = {"httprequest"}
_N8N_IGNORED_TYPES = {"stickynote"}
_N8N_SAFE_BODYLESS_METHODS = {"GET", "DELETE", "HEAD", "OPTIONS"}


def import_workflow_document(
	document: Dict[str, Any],
	*,
	file_name: Optional[str] = None,
	source_format: Optional[str] = None,
) -> Dict[str, Any]:
	if not isinstance(document, dict):
		raise InteropImportError("Imported content must be a JSON object.")

	working, unwrap_warnings, fallback_name = _unwrap_workflow_document(document)
	detected = _normalize_source_format(source_format) or detect_workflow_source(working)
	if not detected:
		raise InteropImportError(
			"Unsupported workflow format. Numel currently imports native Numel workflow JSON and a pragmatic subset of n8n workflow JSON."
		)

	if detected == "numel":
		workflow_doc = dict(working)
		conversion_warnings = list(unwrap_warnings)
		summary = "Native Numel workflow JSON detected."
	else:
		workflow_doc, conversion_warnings, summary = _import_n8n_workflow(
			working,
			file_name=file_name or fallback_name,
		)
		conversion_warnings = list(unwrap_warnings) + list(conversion_warnings)

	validation = validate_workflow_payload(workflow_doc, apply_repairs=True)
	if not validation["valid"]:
		raise InteropImportError(
			"Imported workflow is not valid after conversion.",
			detail={
				"message": "Imported workflow is not valid after conversion",
				"errors": validation["errors"],
				"warnings": list(conversion_warnings) + list(validation.get("warnings") or []),
				"repairs": validation.get("repairs") or [],
				"source_format": detected,
			},
		)

	final_workflow = validation["workflow"]
	name = _workflow_name(final_workflow) or _fallback_name(
		file_name=file_name,
		document_name=fallback_name,
		default="Imported Workflow",
	)
	if isinstance(final_workflow.get("options"), dict):
		final_workflow["options"].setdefault("type", "workflow_options")
		final_workflow["options"]["name"] = name

	return {
		"source_format": detected,
		"name": name,
		"workflow": final_workflow,
		"warnings": list(conversion_warnings) + list(validation.get("warnings") or []),
		"repairs": validation.get("repairs") or [],
		"summary": summary,
	}


def detect_workflow_source(document: Dict[str, Any]) -> Optional[str]:
	if _looks_numel_workflow(document):
		return "numel"
	if _looks_n8n_workflow(document):
		return "n8n"
	return None


def _unwrap_workflow_document(document: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str], Optional[str]]:
	if isinstance(document.get("workflow"), dict) and not isinstance(document.get("nodes"), list):
		fallback = str(document.get("title") or document.get("name") or "").strip() or None
		return dict(document["workflow"]), ["Imported JSON wrapped a nested workflow payload; Numel unwrapped it automatically."], fallback
	return dict(document), [], str(document.get("name") or "").strip() or None


def _normalize_source_format(value: Optional[str]) -> Optional[str]:
	text = str(value or "").strip().lower()
	if not text:
		return None
	if text in {"numel", "n8n"}:
		return text
	raise InteropImportError("source_format must be 'numel' or 'n8n'")


def _looks_numel_workflow(document: Dict[str, Any]) -> bool:
	if not isinstance(document, dict):
		return False
	options = document.get("options")
	if isinstance(options, dict) and str(options.get("type") or "").strip() == "workflow_options":
		return True
	nodes = document.get("nodes")
	if not isinstance(nodes, list) or not nodes:
		return False
	for node in nodes:
		node_type = str((node or {}).get("type") or "").strip().lower()
		if not node_type:
			continue
		if node_type == "workflow":
			return True
		if node_type.endswith("_flow") or node_type.endswith("_config"):
			return True
		if node_type.startswith(_NUMEL_TYPE_PREFIXES):
			return True
	return False


def _looks_n8n_workflow(document: Dict[str, Any]) -> bool:
	if not isinstance(document, dict):
		return False
	nodes = document.get("nodes")
	connections = document.get("connections")
	if not isinstance(nodes, list) or not isinstance(connections, dict):
		return False
	for node in nodes:
		if not isinstance(node, dict):
			continue
		node_type = str(node.get("type") or "").strip().lower()
		if "n8n" in node_type:
			return True
		if isinstance(node.get("parameters"), dict) and isinstance(node.get("position"), list):
			return True
	return False


def _import_n8n_workflow(document: Dict[str, Any], *, file_name: Optional[str] = None) -> Tuple[Dict[str, Any], List[str], str]:
	name = _fallback_name(
		file_name=file_name,
		document_name=str(document.get("name") or "").strip() or None,
		default="Imported n8n Workflow",
	)
	n8n_nodes = document.get("nodes")
	if not isinstance(n8n_nodes, list) or not n8n_nodes:
		raise InteropImportError("n8n import requires a non-empty 'nodes' array.")
	connections = document.get("connections")
	if not isinstance(connections, dict):
		raise InteropImportError("n8n import requires a 'connections' object.")

	warnings: List[str] = []
	nodes_by_name: Dict[str, Dict[str, Any]] = {}
	node_order: List[str] = []
	for index, raw_node in enumerate(n8n_nodes):
		if not isinstance(raw_node, dict):
			raise InteropImportError(f"n8n node {index} is not a JSON object.")
		node_name = str(raw_node.get("name") or "").strip()
		if not node_name:
			raise InteropImportError(f"n8n node {index} is missing a name.")
		if node_name in nodes_by_name:
			raise InteropImportError(f"Duplicate n8n node name '{node_name}' is not supported yet.")
		nodes_by_name[node_name] = raw_node
		node_order.append(node_name)

	outgoing: Dict[str, List[Tuple[int, str]]] = {node_name: [] for node_name in node_order}
	incoming_count: Dict[str, int] = {node_name: 0 for node_name in node_order}
	for node_name in node_order:
		for branch_index, target_name in _iter_n8n_main_targets(connections.get(node_name)):
			if target_name not in nodes_by_name:
				warnings.append(f"n8n connection from '{node_name}' targets missing node '{target_name}' and was ignored.")
				continue
			outgoing[node_name].append((branch_index, target_name))
			incoming_count[target_name] += 1

	positions = [_n8n_position(nodes_by_name[node_name], order=index) for index, node_name in enumerate(node_order)]
	min_x = min((pos[0] for pos in positions), default=0)
	min_y = min((pos[1] for pos in positions), default=0)
	max_x = max((pos[0] for pos in positions), default=0)

	numel_nodes: List[Dict[str, Any]] = []
	numel_edges: List[Dict[str, Any]] = []
	edge_keys: set[Tuple[int, int, str, str]] = set()

	start_index = _append_node(
		numel_nodes,
		{
			"type": "start_flow",
			"extra": {"pos": [min_x - 260, min_y], "name": "Start"},
		},
	)
	http_toolkit_index: Optional[int] = None
	if any(_n8n_node_kind(nodes_by_name[node_name]) == "http" for node_name in node_order):
		http_toolkit_index = _append_node(
			numel_nodes,
			{
				"type": "toolkit_config",
				"name": "toolkits.http_toolkit",
				"extra": {"pos": [min_x, min_y - 220], "name": "HTTP Toolkit"},
			},
		)

	components: Dict[str, _Component] = {}
	placeholder_count = 0
	actionable_count = 0
	for order, node_name in enumerate(node_order):
		component, is_placeholder = _append_n8n_component(
			node_name=node_name,
			node=nodes_by_name[node_name],
			order=order,
			incoming_count=incoming_count.get(node_name, 0),
			http_toolkit_index=http_toolkit_index,
			numel_nodes=numel_nodes,
			numel_edges=numel_edges,
			edge_keys=edge_keys,
			warnings=warnings,
		)
		components[node_name] = component
		if component.entry is not None or component.exit is not None:
			actionable_count += 1
		if is_placeholder:
			placeholder_count += 1

	for node_name in node_order:
		component = components.get(node_name)
		if component is None or component.entry is None:
			continue
		if incoming_count.get(node_name, 0) <= 0 and _n8n_node_kind(nodes_by_name[node_name]) != "manual":
			_add_edge(numel_edges, edge_keys, start_index, component.entry, "flow_out", "flow_in")

	for node_name in node_order:
		source_component = components.get(node_name)
		if source_component is None or source_component.exit is None:
			continue
		for branch_index, target_name in outgoing.get(node_name) or []:
			target_component = components.get(target_name)
			if target_component is None or target_component.entry is None:
				continue
			branch_output = (source_component.branch_outputs or {}).get(branch_index)
			source_data_output = branch_output or source_component.data_output
			used_branch_output = branch_output is not None
			if target_component.dynamic_input_slot_kind == "merge":
				if source_data_output is not None:
					target_key = _merge_input_key(source_component.key, branch_index if used_branch_output else None)
					_add_edge(
						numel_edges,
						edge_keys,
						source_data_output[0],
						target_component.entry,
						source_data_output[1],
						f"input.{target_key}",
					)
				continue
			if not used_branch_output and source_component.exit is not None and target_component.entry is not None:
				_add_edge(numel_edges, edge_keys, source_component.exit, target_component.entry, "flow_out", "flow_in")
			if source_data_output and target_component.data_inputs:
				for input_node, input_slot in target_component.data_inputs:
					_add_edge(
						numel_edges,
						edge_keys,
						source_data_output[0],
						input_node,
						source_data_output[1],
						input_slot,
					)
			elif used_branch_output and target_component.entry is not None:
				_add_edge(
					numel_edges,
					edge_keys,
					source_data_output[0],
					target_component.entry,
					source_data_output[1],
					"flow_in",
				)

	leaf_names: List[str] = []
	for node_name in node_order:
		component = components.get(node_name)
		if component is None or component.exit is None:
			continue
		has_real_target = any(
			components.get(target_name) is not None and components[target_name].entry is not None
			for _, target_name in (outgoing.get(node_name) or [])
		)
		if not has_real_target and _n8n_node_kind(nodes_by_name[node_name]) != "manual":
			leaf_names.append(node_name)

	end_index = _append_node(
		numel_nodes,
		{
			"type": "end_flow",
			"extra": {"pos": [max_x + 820, min_y], "name": "End"},
		},
	)
	if not leaf_names:
		_add_edge(numel_edges, edge_keys, start_index, end_index, "flow_out", "flow_in")
	else:
		for leaf_order, node_name in enumerate(leaf_names):
			component = components[node_name]
			leaf_pos = _n8n_position(nodes_by_name[node_name], order=leaf_order)
			preview_index = _append_node(
				numel_nodes,
				{
					"type": "preview_flow",
					"hint": "json",
					"extra": {
						"pos": [leaf_pos[0] + 280, leaf_pos[1] + (leaf_order * 120)],
						"name": f"Preview · {component.label}",
					},
				},
			)
			if component.data_output is not None:
				_add_edge(
					numel_edges,
					edge_keys,
					component.data_output[0],
					preview_index,
					component.data_output[1],
					"flow_in",
				)
			elif component.exit is not None:
				_add_edge(numel_edges, edge_keys, component.exit, preview_index, "flow_out", "flow_in")
			_add_edge(numel_edges, edge_keys, preview_index, end_index, "flow_out", "flow_in")

	description = "Imported from n8n JSON into a runnable Numel workbench workflow."
	if placeholder_count:
		description += f" {placeholder_count} node(s) require manual review."
	if not actionable_count:
		description += " The imported file contained no executable n8n nodes, so Numel created a minimal scaffold."
		warnings.append("n8n workflow did not expose executable nodes; Numel created a minimal scaffold.")

	workflow_doc = {
		"type": "workflow",
		"options": {
			"type": "workflow_options",
			"name": name,
			"description": description,
		},
		"nodes": numel_nodes,
		"edges": numel_edges,
	}
	summary = f"Converted n8n workflow '{name}' into {len(numel_nodes)} Numel node(s)"
	if placeholder_count:
		summary += f"; {placeholder_count} node(s) need manual review"
	return workflow_doc, warnings, summary


def _append_n8n_component(
	*,
	node_name: str,
	node: Dict[str, Any],
	order: int,
	incoming_count: int,
	http_toolkit_index: Optional[int],
	numel_nodes: List[Dict[str, Any]],
	numel_edges: List[Dict[str, Any]],
	edge_keys: set[Tuple[int, int, str, str]],
	warnings: List[str],
) -> Tuple[_Component, bool]:
	label = str(node.get("name") or node_name).strip() or node_name
	x, y = _n8n_position(node, order=order)
	kind = _n8n_node_kind(node)

	if kind == "manual":
		return _Component(key=node_name, label=label, entry=0, exit=0), False

	if kind == "ignored":
		warnings.append(f"Ignored n8n node '{label}' because it does not affect runtime execution.")
		return _Component(key=node_name, label=label, entry=None, exit=None), False

	if kind == "webhook":
		params = node.get("parameters") or {}
		endpoint = str(params.get("path") or label).strip() or label
		endpoint = "/" + endpoint.lstrip("/")
		methods = str(params.get("httpMethod") or params.get("methods") or "POST").strip().upper() or "POST"
		source_index = _append_node(
			numel_nodes,
			{
				"type": "webhook_source_flow",
				"endpoint": endpoint,
				"methods": methods,
				"source_id": _slug_key(label),
				"extra": {"pos": [x, y], "name": label},
			},
		)
		listener_index = _append_node(
			numel_nodes,
			{
				"type": "event_listener_flow",
				"mode": "any",
				"extra": {"pos": [x + 240, y], "name": f"{label} Event"},
			},
		)
		_add_edge(numel_edges, edge_keys, source_index, listener_index, "flow_out", "flow_in")
		_add_edge(numel_edges, edge_keys, source_index, listener_index, "registered_id", "sources.webhook")
		warnings.append(f"Webhook node '{label}' was imported as a one-shot webhook listener. Add an explicit event loop if you want it to keep listening after the first event.")
		return _Component(
			key=node_name,
			label=label,
			entry=source_index,
			exit=listener_index,
			data_output=(listener_index, "event"),
		), False

	if kind == "set":
		transform_index = _append_node(
			numel_nodes,
			_build_set_transform_node(node, x=x, y=y, warnings=warnings),
		)
		return _Component(
			key=node_name,
			label=label,
			entry=transform_index,
			exit=transform_index,
			data_inputs=[(transform_index, "input")],
			data_output=(transform_index, "output"),
		), False

	if kind == "if":
		component = _build_if_component(
			node,
			x=x,
			y=y,
			numel_nodes=numel_nodes,
			numel_edges=numel_edges,
			edge_keys=edge_keys,
			warnings=warnings,
		)
		return component, False

	if kind == "merge":
		merge_index = _append_node(
			numel_nodes,
			_build_merge_node(node, x=x, y=y, warnings=warnings),
		)
		return _Component(
			key=node_name,
			label=label,
			entry=merge_index,
			exit=merge_index,
			data_output=(merge_index, "output"),
			dynamic_input_slot_kind="merge",
		), False

	if kind == "http":
		if http_toolkit_index is None:
			warnings.append(f"HTTP node '{label}' could not wire the shared HTTP toolkit automatically.")
		tool_node, builder_node = _build_http_nodes(
			node,
			x=x,
			y=y,
			use_builder=incoming_count > 0,
			warnings=warnings,
		)
		builder_index: Optional[int] = None
		if builder_node is not None:
			builder_index = _append_node(numel_nodes, builder_node)
		tool_index = _append_node(numel_nodes, tool_node)
		if builder_index is not None:
			_add_edge(numel_edges, edge_keys, builder_index, tool_index, "output", "args")
			_add_edge(numel_edges, edge_keys, builder_index, tool_index, "flow_out", "flow_in")
		if http_toolkit_index is not None:
			_add_edge(numel_edges, edge_keys, http_toolkit_index, tool_index, "config", "config")
		return _Component(
			key=node_name,
			label=label,
			entry=builder_index if builder_index is not None else tool_index,
			exit=tool_index,
			data_inputs=[(builder_index, "input")] if builder_index is not None else None,
			data_output=(tool_index, "output"),
		), False

	if kind == "code":
		placeholder_index = _append_node(
			numel_nodes,
			_build_placeholder_transform_node(
				node,
				x=x,
				y=y,
				reason="Original n8n code nodes need manual porting into Numel Python transforms or toolkits.",
			),
		)
		warnings.append(f"Code node '{label}' was imported as a review placeholder because Numel cannot safely translate n8n code automatically.")
		return _Component(
			key=node_name,
			label=label,
			entry=placeholder_index,
			exit=placeholder_index,
			data_inputs=[(placeholder_index, "input")],
			data_output=(placeholder_index, "output"),
		), True

	placeholder_index = _append_node(
		numel_nodes,
		_build_placeholder_transform_node(
			node,
			x=x,
			y=y,
			reason="This n8n node type does not have a direct runnable Numel mapping yet.",
		),
	)
	warnings.append(f"n8n node '{label}' ({node.get('type')}) was imported as a manual-review placeholder.")
	return _Component(
		key=node_name,
		label=label,
		entry=placeholder_index,
		exit=placeholder_index,
		data_inputs=[(placeholder_index, "input")],
		data_output=(placeholder_index, "output"),
	), True


def _build_set_transform_node(node: Dict[str, Any], *, x: int, y: int, warnings: List[str]) -> Dict[str, Any]:
	label = str(node.get("name") or "Set").strip() or "Set"
	params = node.get("parameters") or {}
	assignments: Dict[str, Any] = {}
	for key, value in _extract_set_assignments(params, warnings=warnings, node_name=label).items():
		assignments[key] = value
	keep_only = bool(params.get("keepOnlySet"))

	if keep_only:
		script = f"output = {repr(assignments)}"
	else:
		script = (
			"base = dict(input) if isinstance(input, dict) else {}\n"
			f"base.update({repr(assignments)})\n"
			"output = base"
		)
	return {
		"type": "transform_flow",
		"lang": "python",
		"script": script,
		"extra": {"pos": [x, y], "name": label},
	}


def _build_if_component(
	node: Dict[str, Any],
	*,
	x: int,
	y: int,
	numel_nodes: List[Dict[str, Any]],
	numel_edges: List[Dict[str, Any]],
	edge_keys: set[Tuple[int, int, str, str]],
	warnings: List[str],
) -> _Component:
	label = str(node.get("name") or "If").strip() or "If"
	params = node.get("parameters") or {}
	rules, logic = _extract_if_rules(params, warnings=warnings, node_name=label)
	classifier_index = _append_node(
		numel_nodes,
		{
			"type": "transform_flow",
			"lang": "python",
			"context": {
				"rules": rules,
				"logic": logic,
			},
			"script": _n8n_classifier_script(mode="if"),
			"extra": {"pos": [x, y], "name": f"{label} Classifier"},
		},
	)
	route_index = _append_node(
		numel_nodes,
		{
			"type": "route_flow",
			"output": {"true": None, "false": None},
			"extra": {"pos": [x + 260, y], "name": label},
		},
	)
	_add_edge(numel_edges, edge_keys, classifier_index, route_index, "output", "target")
	return _Component(
		key=node.get("name") or label,
		label=label,
		entry=classifier_index,
		exit=route_index,
		data_inputs=[(classifier_index, "input"), (route_index, "input")],
		branch_outputs={
			0: (route_index, "output.true"),
			1: (route_index, "output.false"),
		},
	)


def _build_merge_node(node: Dict[str, Any], *, x: int, y: int, warnings: List[str]) -> Dict[str, Any]:
	label = str(node.get("name") or "Merge").strip() or "Merge"
	params = node.get("parameters") or {}
	mode = str(
		params.get("mode")
		or params.get("operation")
		or params.get("mergeMode")
		or "append"
	).strip().lower()
	strategy = "all"
	if mode in {"append", "combine", "multiplex", "wait"}:
		strategy = "all"
	elif mode in {"choosebranch", "choose_branch", "passthrough", "pass_through"}:
		preferred = str(params.get("output") or params.get("branch") or "").strip().lower()
		strategy = "last" if preferred in {"input2", "second", "branch2"} else "first"
	else:
		warnings.append(f"Merge node '{label}' uses unsupported mode '{mode}'; Numel imported it with merge strategy 'all'.")
	return {
		"type": "merge_flow",
		"strategy": strategy,
		"input": {},
		"extra": {"pos": [x, y], "name": label},
	}


def _extract_set_assignments(params: Dict[str, Any], *, warnings: List[str], node_name: str) -> Dict[str, Any]:
	assignments: Dict[str, Any] = {}
	nested = (((params.get("assignments") or {}).get("assignments")) or [])
	if isinstance(nested, list) and nested:
		for item in nested:
			if not isinstance(item, dict):
				continue
			field_name = str(item.get("name") or "").strip()
			if not field_name:
				continue
			value_kind = str(item.get("type") or "string").strip().lower() or "string"
			assignments[field_name] = _coerce_assignment_value(
				item.get("value"),
				value_kind,
				warnings=warnings,
				node_name=node_name,
				field_name=field_name,
			)
		if assignments:
			return assignments

	values = params.get("values") or {}
	if isinstance(values, dict):
		for value_kind, items in values.items():
			if not isinstance(items, list):
				continue
			for item in items:
				if not isinstance(item, dict):
					continue
				field_name = str(item.get("name") or "").strip()
				if not field_name:
					continue
				assignments[field_name] = _coerce_assignment_value(
					item.get("value"),
					str(value_kind or "string").strip().lower() or "string",
					warnings=warnings,
					node_name=node_name,
					field_name=field_name,
				)
	return assignments


def _coerce_assignment_value(
	value: Any,
	value_kind: str,
	*,
	warnings: List[str],
	node_name: str,
	field_name: str,
) -> Any:
	if _looks_n8n_expression(value):
		warnings.append(f"Set node '{node_name}' field '{field_name}' uses an n8n expression; Numel kept the literal expression text for manual refinement.")
		return value
	if value_kind in {"string", "str", "text"}:
		return "" if value is None else str(value)
	if value_kind in {"number", "float", "int"}:
		try:
			number = float(value)
			return int(number) if number.is_integer() else number
		except Exception:
			warnings.append(f"Set node '{node_name}' field '{field_name}' could not be parsed as a number; Numel kept the original value.")
			return value
	if value_kind in {"boolean", "bool"}:
		if isinstance(value, bool):
			return value
		return str(value).strip().lower() in {"1", "true", "yes", "on"}
	if value_kind in {"json", "object", "array"}:
		if isinstance(value, (dict, list)):
			return value
		try:
			return json.loads(str(value))
		except Exception:
			warnings.append(f"Set node '{node_name}' field '{field_name}' contains JSON-like data that Numel could not parse; the literal value was kept.")
			return value
	return value


def _extract_if_rules(params: Dict[str, Any], *, warnings: List[str], node_name: str) -> Tuple[List[Dict[str, Any]], str]:
	conditions = params.get("conditions") or {}
	logic = "all"
	raw_rules: List[Dict[str, Any]] = []
	if isinstance(conditions, dict):
		combinator = (
			conditions.get("combinator")
			or conditions.get("combineOperation")
			or ((conditions.get("options") or {}).get("combinator") if isinstance(conditions.get("options"), dict) else None)
		)
		if str(combinator or "").strip().lower() in {"or", "any"}:
			logic = "any"
		if isinstance(conditions.get("conditions"), list):
			raw_rules.extend(item for item in conditions.get("conditions") or [] if isinstance(item, dict))
		else:
			for value_kind, items in conditions.items():
				if value_kind in {"options", "combineOperation", "combinator", "conditions"}:
					continue
				if not isinstance(items, list):
					continue
				for item in items:
					if not isinstance(item, dict):
						continue
					copy_item = dict(item)
					copy_item.setdefault("legacy_kind", str(value_kind))
					raw_rules.append(copy_item)

	rules: List[Dict[str, Any]] = []
	for raw_rule in raw_rules:
		rule = _compile_if_rule(raw_rule, warnings=warnings, node_name=node_name)
		if rule is not None:
			rules.append(rule)
	if not rules:
		warnings.append(f"If node '{node_name}' had no supported conditions; Numel imported it with a default truthiness check.")
		rules.append({"path": [], "operator": "truthy", "expected": None})
	return rules, logic


def _compile_if_rule(raw_rule: Dict[str, Any], *, warnings: List[str], node_name: str) -> Optional[Dict[str, Any]]:
	left_raw = raw_rule.get("leftValue", raw_rule.get("value1"))
	right_raw = raw_rule.get("rightValue", raw_rule.get("value2"))
	path = _parse_n8n_json_path(left_raw)
	if path is None:
		if left_raw not in (None, ""):
			warnings.append(f"If node '{node_name}' uses a left-hand expression Numel could not fully decode; it will compare the literal value instead.")
		path = []
		left_literal = left_raw
	else:
		left_literal = None
	operator_value = raw_rule.get("operator", raw_rule.get("operation"))
	legacy_kind = str(raw_rule.get("legacy_kind") or "").strip().lower()
	operator_name = _normalize_if_operator(operator_value, legacy_kind=legacy_kind)
	expected = _coerce_if_expected_value(right_raw, operator_name)
	return {
		"path": path,
		"left_literal": left_literal,
		"operator": operator_name,
		"expected": expected,
	}


def _normalize_if_operator(operator_value: Any, *, legacy_kind: str = "") -> str:
	if isinstance(operator_value, dict):
		text = str(operator_value.get("operation") or operator_value.get("type") or "").strip()
	else:
		text = str(operator_value or "").strip()
	normalized = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
	if not normalized and legacy_kind:
		normalized = "equal"
	aliases = {
		"equals": "equal",
		"equal": "equal",
		"not_equal": "not_equal",
		"notequal": "not_equal",
		"contains": "contains",
		"not_contains": "not_contains",
		"notcontains": "not_contains",
		"starts_with": "starts_with",
		"startswith": "starts_with",
		"ends_with": "ends_with",
		"endswith": "ends_with",
		"larger": "larger",
		"larger_equal": "larger_equal",
		"largerequal": "larger_equal",
		"smaller": "smaller",
		"smaller_equal": "smaller_equal",
		"smallerequal": "smaller_equal",
		"is_empty": "is_empty",
		"isempty": "is_empty",
		"is_not_empty": "is_not_empty",
		"isnotempty": "is_not_empty",
		"exists": "exists",
		"not_exists": "not_exists",
		"notexists": "not_exists",
		"regex": "regex",
		"matches_regex": "regex",
		"istrue": "is_true",
		"is_true": "is_true",
		"isfalse": "is_false",
		"is_false": "is_false",
	}
	return aliases.get(normalized, "equal")


def _coerce_if_expected_value(value: Any, operator_name: str) -> Any:
	if operator_name in {"exists", "not_exists", "is_empty", "is_not_empty", "is_true", "is_false", "truthy"}:
		return None
	if _looks_n8n_expression(value):
		return value
	if isinstance(value, (dict, list, int, float, bool)) or value is None:
		return value
	text = str(value)
	if operator_name in {"larger", "larger_equal", "smaller", "smaller_equal"}:
		try:
			number = float(text)
			return int(number) if number.is_integer() else number
		except Exception:
			return text
	return text


def _parse_n8n_json_path(raw_value: Any) -> Optional[List[str]]:
	if raw_value in (None, ""):
		return []
	if not isinstance(raw_value, str):
		return None
	text = raw_value.strip()
	if text.startswith("="):
		text = text[1:].strip()
	if text.startswith("{{") and text.endswith("}}"):
		text = text[2:-2].strip()
	if text == "$json":
		return []
	if not text.startswith("$json"):
		return None
	remainder = text[len("$json"):]
	parts: List[str] = []
	while remainder:
		if remainder.startswith("."):
			remainder = remainder[1:]
			match = re.match(r"([A-Za-z0-9_]+)", remainder)
			if not match:
				return None
			parts.append(match.group(1))
			remainder = remainder[len(match.group(1)) :]
			continue
		if remainder.startswith("["):
			match = re.match(r"\[(?:(?:'([^']+)')|(?:\"([^\"]+)\")|(\d+))\]", remainder)
			if not match:
				return None
			part = match.group(1) or match.group(2) or match.group(3)
			parts.append(str(part))
			remainder = remainder[len(match.group(0)) :]
			continue
		return None
	return parts


def _n8n_classifier_script(*, mode: str) -> str:
	body = (
		"def _interop_get_path(data, path):\n"
		"\tcurrent = data\n"
		"\tfor part in path or []:\n"
		"\t\tif isinstance(current, dict):\n"
		"\t\t\tcurrent = current.get(part)\n"
		"\t\telif isinstance(current, (list, tuple)):\n"
		"\t\t\ttry:\n"
		"\t\t\t\tindex = int(part)\n"
		"\t\t\texcept Exception:\n"
		"\t\t\t\treturn None\n"
		"\t\t\tif index < 0 or index >= len(current):\n"
		"\t\t\t\treturn None\n"
		"\t\t\tcurrent = current[index]\n"
		"\t\telse:\n"
		"\t\t\treturn None\n"
		"\treturn current\n"
		"\n"
		"def _interop_match(current, operator, expected):\n"
		"\tif operator == 'truthy':\n"
		"\t\treturn bool(current)\n"
		"\tif operator == 'exists':\n"
		"\t\treturn current is not None\n"
		"\tif operator == 'not_exists':\n"
		"\t\treturn current is None\n"
		"\tif operator == 'is_empty':\n"
		"\t\treturn current in (None, '', [], {}, ())\n"
		"\tif operator == 'is_not_empty':\n"
		"\t\treturn current not in (None, '', [], {}, ())\n"
		"\tif operator == 'is_true':\n"
		"\t\treturn bool(current) is True\n"
		"\tif operator == 'is_false':\n"
		"\t\treturn bool(current) is False\n"
		"\tif operator == 'contains':\n"
		"\t\treturn expected in current if current is not None else False\n"
		"\tif operator == 'not_contains':\n"
		"\t\treturn expected not in current if current is not None else True\n"
		"\tif operator == 'starts_with':\n"
		"\t\treturn str(current or '').startswith(str(expected or ''))\n"
		"\tif operator == 'ends_with':\n"
		"\t\treturn str(current or '').endswith(str(expected or ''))\n"
		"\tif operator == 'larger':\n"
		"\t\treturn current > expected\n"
		"\tif operator == 'larger_equal':\n"
		"\t\treturn current >= expected\n"
		"\tif operator == 'smaller':\n"
		"\t\treturn current < expected\n"
		"\tif operator == 'smaller_equal':\n"
		"\t\treturn current <= expected\n"
		"\tif operator == 'regex':\n"
		"\t\treturn bool(__import__('re').search(str(expected or ''), str(current or '')))\n"
		"\tif operator == 'not_equal':\n"
		"\t\treturn current != expected\n"
		"\treturn current == expected\n"
		"\n"
		"rules = list(context.get('rules') or [])\n"
		"logic = str(context.get('logic') or 'all').lower()\n"
	)
	if mode == "if":
		return (
			body
			+ "matches = []\n"
			+ "for rule in rules:\n"
			+ "\tcurrent = _interop_get_path(input, rule.get('path') or []) if rule.get('left_literal') in (None, '') else rule.get('left_literal')\n"
			+ "\tmatches.append(_interop_match(current, rule.get('operator') or 'equal', rule.get('expected')))\n"
			+ "decision = any(matches) if logic == 'any' else all(matches)\n"
			+ "output = 'true' if decision else 'false'\n"
		)
	raise ValueError(f"Unsupported classifier mode '{mode}'")


def _build_http_nodes(
	node: Dict[str, Any],
	*,
	x: int,
	y: int,
	use_builder: bool,
	warnings: List[str],
) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]]]:
	label = str(node.get("name") or "HTTP Request").strip() or "HTTP Request"
	params = node.get("parameters") or {}
	method = str(params.get("method") or "GET").strip().upper() or "GET"
	url = _extract_http_url(params, warnings=warnings, node_name=label)
	headers = _extract_http_headers(params, warnings=warnings, node_name=label)
	static_json_data = _extract_http_json_body(params, warnings=warnings, node_name=label)

	tool_node: Dict[str, Any] = {
		"type": "tool_flow",
		"method": "request",
		"extra": {"pos": [x + (240 if use_builder else 0), y], "name": label},
	}

	if use_builder and (method not in _N8N_SAFE_BODYLESS_METHODS or static_json_data is not None):
		builder_node = {
			"type": "transform_flow",
			"lang": "python",
			"context": {
				"method": method,
				"url": url,
				"json_data": static_json_data,
				"extra_headers": headers or None,
			},
			"script": (
				"payload = input if input is not None else context.get('json_data')\n"
				"args = {\n"
				"    'method': context.get('method') or 'GET',\n"
				"    'url': context.get('url') or '',\n"
				"}\n"
				"if payload is not None:\n"
				"    args['json_data'] = payload\n"
				"headers = context.get('extra_headers') or None\n"
				"if headers:\n"
				"    args['extra_headers'] = headers\n"
				"output = args\n"
			),
			"extra": {"pos": [x, y], "name": f"{label} Request Args"},
		}
		return tool_node, builder_node

	args: Dict[str, Any] = {"method": method, "url": url}
	if static_json_data is not None:
		args["json_data"] = static_json_data
	if headers:
		args["extra_headers"] = headers
	if use_builder and method in _N8N_SAFE_BODYLESS_METHODS:
		warnings.append(f"HTTP node '{label}' receives upstream data, but safe-bodyless method {method} was kept without automatically forwarding that payload.")
	tool_node["args"] = args
	return tool_node, None


def _extract_http_url(params: Dict[str, Any], *, warnings: List[str], node_name: str) -> str:
	base_url = str(params.get("url") or params.get("endpoint") or "").strip()
	if not base_url:
		warnings.append(f"HTTP node '{node_name}' had no URL; Numel inserted a placeholder URL for manual refinement.")
		base_url = "https://example.com"
	if _looks_n8n_expression(base_url):
		warnings.append(f"HTTP node '{node_name}' URL uses an n8n expression; Numel kept the literal expression text for manual refinement.")
		return base_url

	query_pairs: List[Tuple[str, str]] = []
	query_groups = [
		(((params.get("queryParameters") or {}).get("parameters")) or []),
		(((params.get("queryParametersUi") or {}).get("parameter")) or []),
	]
	for group in query_groups:
		if not isinstance(group, list):
			continue
		for item in group:
			if not isinstance(item, dict):
				continue
			key = str(item.get("name") or "").strip()
			value = item.get("value")
			if not key:
				continue
			if _looks_n8n_expression(value):
				warnings.append(f"HTTP node '{node_name}' query parameter '{key}' uses an n8n expression and was not expanded automatically.")
				continue
			query_pairs.append((key, "" if value is None else str(value)))
	if query_pairs:
		separator = "&" if "?" in base_url else "?"
		base_url = f"{base_url}{separator}{urlencode(query_pairs)}"
	return base_url


def _extract_http_headers(params: Dict[str, Any], *, warnings: List[str], node_name: str) -> Dict[str, str]:
	headers: Dict[str, str] = {}
	header_groups = [
		(((params.get("headerParameters") or {}).get("parameters")) or []),
		(((params.get("headersUi") or {}).get("parameter")) or []),
	]
	for group in header_groups:
		if not isinstance(group, list):
			continue
		for item in group:
			if not isinstance(item, dict):
				continue
			key = str(item.get("name") or "").strip()
			value = item.get("value")
			if not key:
				continue
			if _looks_n8n_expression(value):
				warnings.append(f"HTTP node '{node_name}' header '{key}' uses an n8n expression; Numel kept the header out of the automatic import.")
				continue
			headers[key] = "" if value is None else str(value)
	return headers


def _extract_http_json_body(params: Dict[str, Any], *, warnings: List[str], node_name: str) -> Any:
	for raw_key in ("jsonBody", "bodyParametersJson"):
		raw_value = params.get(raw_key)
		if raw_value in (None, ""):
			continue
		if _looks_n8n_expression(raw_value):
			warnings.append(f"HTTP node '{node_name}' body uses an n8n expression; Numel kept the literal body text for manual refinement.")
			return raw_value
		if isinstance(raw_value, (dict, list)):
			return raw_value
		try:
			return json.loads(str(raw_value))
		except Exception:
			return raw_value

	body_groups = [
		(((params.get("bodyParameters") or {}).get("parameters")) or []),
		(((params.get("bodyParametersUi") or {}).get("parameter")) or []),
	]
	body: Dict[str, Any] = {}
	for group in body_groups:
		if not isinstance(group, list):
			continue
		for item in group:
			if not isinstance(item, dict):
				continue
			key = str(item.get("name") or "").strip()
			value = item.get("value")
			if not key:
				continue
			if _looks_n8n_expression(value):
				warnings.append(f"HTTP node '{node_name}' body field '{key}' uses an n8n expression; Numel kept the literal text for manual refinement.")
				body[key] = value
				continue
			body[key] = value
	if body:
		return body
	return None


def _build_placeholder_transform_node(node: Dict[str, Any], *, x: int, y: int, reason: str) -> Dict[str, Any]:
	label = str(node.get("name") or "Imported Node").strip() or "Imported Node"
	params = node.get("parameters") or {}
	code = (
		params.get("jsCode")
		or params.get("pythonCode")
		or params.get("functionCode")
		or params.get("code")
		or ""
	)
	return {
		"type": "transform_flow",
		"lang": "python",
		"context": {
			"node_name": label,
			"node_type": str(node.get("type") or ""),
			"parameters": params,
			"original_code": code,
		},
		"script": (
			"output = {\n"
			"    'interop_warning': '" + _escape_single_quote(reason) + "',\n"
			"    'node_name': context.get('node_name'),\n"
			"    'node_type': context.get('node_type'),\n"
			"    'original_code': context.get('original_code'),\n"
			"    'original_parameters': context.get('parameters'),\n"
			"    'input': input,\n"
			"}\n"
		),
		"extra": {"pos": [x, y], "name": label},
	}


def _iter_n8n_main_targets(raw_connection: Any) -> Iterable[Tuple[int, str]]:
	if not isinstance(raw_connection, dict):
		return []
	targets: List[Tuple[int, str]] = []
	main_groups = raw_connection.get("main")
	if not isinstance(main_groups, list):
		return targets
	for branch_index, branch in enumerate(main_groups):
		if not isinstance(branch, list):
			continue
		for item in branch:
			if not isinstance(item, dict):
				continue
			target_name = str(item.get("node") or "").strip()
			if target_name:
				targets.append((branch_index, target_name))
	return targets


def _n8n_position(node: Dict[str, Any], *, order: int) -> Tuple[int, int]:
	position = node.get("position")
	if isinstance(position, list) and len(position) >= 2:
		try:
			return int(position[0]), int(position[1])
		except Exception:
			pass
	return 180 + (order * 240), 180


def _n8n_node_kind(node: Dict[str, Any]) -> str:
	type_slug = _slug_key_from_type(str(node.get("type") or ""))
	if type_slug in _N8N_MANUAL_TYPES:
		return "manual"
	if type_slug in _N8N_WEBHOOK_TYPES:
		return "webhook"
	if type_slug in _N8N_SET_TYPES:
		return "set"
	if type_slug in _N8N_IF_TYPES:
		return "if"
	if type_slug in _N8N_MERGE_TYPES:
		return "merge"
	if type_slug in _N8N_CODE_TYPES:
		return "code"
	if type_slug in _N8N_HTTP_TYPES:
		return "http"
	if type_slug in _N8N_IGNORED_TYPES:
		return "ignored"
	return "placeholder"


def _slug_key(text: str) -> str:
	return re.sub(r"[^a-z0-9]+", "_", str(text or "").strip().lower()).strip("_") or "node"


def _slug_key_from_type(text: str) -> str:
	base = str(text or "").strip().split(".")[-1]
	return re.sub(r"[^a-z0-9]+", "", base.lower())


def _looks_n8n_expression(value: Any) -> bool:
	if not isinstance(value, str):
		return False
	text = value.strip()
	return text.startswith("=") or "{{" in text or "$json" in text or "$node" in text


def _workflow_name(document: Dict[str, Any]) -> Optional[str]:
	options = document.get("options")
	if isinstance(options, dict):
		name = str(options.get("name") or "").strip()
		if name:
			return name
	name = str(document.get("name") or "").strip()
	return name or None


def _fallback_name(*, file_name: Optional[str], document_name: Optional[str], default: str) -> str:
	if document_name:
		return str(document_name).strip()
	if file_name:
		stem = Path(str(file_name)).stem.strip()
		if stem:
			return stem
	return default


def _append_node(nodes: List[Dict[str, Any]], node: Dict[str, Any]) -> int:
	nodes.append(node)
	return len(nodes) - 1


def _merge_input_key(source_key: str, branch_index: Optional[int] = None) -> str:
	base = _slug_key(source_key)
	if branch_index is None:
		return base
	return f"{base}_branch_{int(branch_index) + 1}"


def _add_edge(
	edges: List[Dict[str, Any]],
	edge_keys: set[Tuple[int, int, str, str]],
	source: int,
	target: int,
	source_slot: str,
	target_slot: str,
) -> None:
	key = (int(source), int(target), str(source_slot), str(target_slot))
	if key in edge_keys:
		return
	edge_keys.add(key)
	edges.append(
		{
			"source": int(source),
			"target": int(target),
			"source_slot": str(source_slot),
			"target_slot": str(target_slot),
		}
	)


def _escape_single_quote(value: str) -> str:
	return str(value or "").replace("\\", "\\\\").replace("'", "\\'")
