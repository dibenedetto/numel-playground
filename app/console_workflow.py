from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from schema import DEFAULT_BACKEND_NAME


_RUNTIME_BOUND_TOOLKITS = {
	"console_toolkit",
	"channel_toolkit",
	"workspace_toolkit",
	"agent_endpoint_toolkit",
}

_RUNTIME_ONLY_TOOLKIT_ARG_KEYS = {
	"base_url",
	"auth_token",
	"internal_token",
	"user_id",
	"local_app",
	"channel_registry",
	"channel_pool",
	"deployment_id",
}

_DECLARATIVE_RUNTIME_BOUND_TOOLKIT_ARGS = {
	"workspace_toolkit": {"workflow_name"},
}


def _node_payload(
	node_type: str,
	*,
	label: str,
	pos: tuple[int, int],
	**fields: Any,
) -> Dict[str, Any]:
	payload: Dict[str, Any] = {"type": node_type, **fields}
	payload["extra"] = {"pos": [pos[0], pos[1]], "name": label}
	return payload


def _slug_key(value: str, *, fallback: str, used: set[str]) -> str:
	raw = "".join(ch.lower() if ch.isalnum() else "_" for ch in str(value or "").strip())
	parts = [part for part in raw.split("_") if part]
	base = "_".join(parts) or fallback
	key = base
	index = 2
	while key in used:
		key = f"{base}_{index}"
		index += 1
	used.add(key)
	return key


def _runtime_binding_hint(toolkit_name: str) -> Optional[Dict[str, Any]]:
	if toolkit_name not in _RUNTIME_BOUND_TOOLKITS:
		return None
	return {
		"binding_kind": "numel_runtime",
		"toolkit": toolkit_name,
		"injected_args": sorted(_RUNTIME_ONLY_TOOLKIT_ARG_KEYS),
	}


def _export_toolkit_args(toolkit_name: str, raw_args: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
	args = dict(raw_args or {})
	if not args:
		return None
	if toolkit_name in _RUNTIME_BOUND_TOOLKITS:
		allowed = _DECLARATIVE_RUNTIME_BOUND_TOOLKIT_ARGS.get(toolkit_name)
		if allowed is None:
			return None
		args = {
			key: value
			for key, value in args.items()
			if key not in _RUNTIME_ONLY_TOOLKIT_ARG_KEYS and key in allowed
		}
	return args or None


def build_console_workflow_export(
	*,
	config: Dict[str, Any],
	model_source: str,
	model_name: str,
	toolkit_names: Optional[List[str]] = None,
	toolkit_args: Optional[Dict[str, Dict[str, Any]]] = None,
	skill_names: Optional[List[str]] = None,
	use_backend_memory: bool = True,
	backend_name: str = DEFAULT_BACKEND_NAME,
) -> Dict[str, Any]:
	"""Build a workflow-backed view of the current assistant console configuration."""
	options_cfg = dict(config.get("options") or {})
	memory_cfg = dict(config.get("memory") or {})
	workflow_name = str(options_cfg.get("name") or "Assistant Console").strip() or "Assistant Console"

	selected_toolkits = [str(name).strip() for name in (toolkit_names or []) if str(name).strip()]
	selected_skills = [str(name).strip() for name in (skill_names or []) if str(name).strip()]
	toolkit_args = dict(toolkit_args or {})

	runtime_bound_toolkits = [
		tk_name
		for tk_name in selected_toolkits
		if tk_name in _RUNTIME_BOUND_TOOLKITS
	]

	workflow_description = (
		"Workflow-backed view of the current assistant console configuration. "
		"The interactive Agent Chat node is the closest workbench equivalent of the console panel."
	)
	if runtime_bound_toolkits:
		workflow_description += (
			" Runtime-bound toolkits are preserved in the graph and rebound by Numel at runtime: "
			+ ", ".join(runtime_bound_toolkits)
			+ "."
		)

	nodes: List[Dict[str, Any]] = [
		_node_payload(
			"backend_config",
			label="Backend",
			pos=(40, 60),
			name=backend_name,
		),
		_node_payload(
			"model_config",
			label="Model",
			pos=(240, 60),
			source=model_source,
			name=model_name,
		),
		_node_payload(
			"agent_options_config",
			label="Assistant Persona",
			pos=(440, 60),
			name=workflow_name,
			description=str(options_cfg.get("description") or "").strip() or None,
			instructions=list(options_cfg.get("instructions") or []),
			markdown=bool(options_cfg.get("markdown", True)),
		),
	]
	edges: List[Dict[str, Any]] = []

	agent_config_index = None
	memory_manager_index = None
	session_manager_index = None

	if use_backend_memory:
		session_manager_index = len(nodes)
		nodes.append(
			_node_payload(
				"session_manager_config",
				label="Session Memory",
				pos=(640, 60),
				query=True,
				update=True,
				history_size=max(1, int(memory_cfg.get("session_history", 5) or 5)),
			)
		)
		memory_manager_index = len(nodes)
		nodes.append(
			_node_payload(
				"memory_manager_config",
				label="Long-Term Memory",
				pos=(860, 60),
				query=True,
				update=True,
				managed=True,
			)
		)

	agent_config_index = len(nodes)
	nodes.append(
		_node_payload(
			"agent_config",
			label="Console Agent",
			pos=(1120, 120),
		)
	)

	chat_index = len(nodes)
	nodes.append(
		_node_payload(
			"agent_chat",
			label="Assistant Chat",
			pos=(1380, 120),
		)
	)

	edges.extend(
		[
			{"source": 0, "target": agent_config_index, "source_slot": "config", "target_slot": "backend"},
			{"source": 1, "target": agent_config_index, "source_slot": "config", "target_slot": "model"},
			{"source": 2, "target": agent_config_index, "source_slot": "options", "target_slot": "options"},
			{"source": agent_config_index, "target": chat_index, "source_slot": "config", "target_slot": "config"},
		]
	)

	if session_manager_index is not None:
		edges.append(
			{"source": session_manager_index, "target": agent_config_index, "source_slot": "config", "target_slot": "session_mgr"}
		)
	if memory_manager_index is not None:
		edges.append(
			{"source": memory_manager_index, "target": agent_config_index, "source_slot": "config", "target_slot": "memory_mgr"}
		)

	used_keys: set[str] = set()
	next_x = 40
	next_y = 260
	for tk_name in selected_toolkits:
		node_index = len(nodes)
		node = _node_payload(
			"toolkit_config",
			label=tk_name,
			pos=(next_x, next_y),
			name=tk_name,
			args=_export_toolkit_args(tk_name, toolkit_args.get(tk_name)),
		)
		runtime_binding = _runtime_binding_hint(tk_name)
		if runtime_binding is not None:
			node["runtime_binding"] = runtime_binding
		nodes.append(node)
		toolkit_key = _slug_key(tk_name.split(".")[-1], fallback="toolkit", used=used_keys)
		edges.append(
			{
				"source": node_index,
				"target": agent_config_index,
				"source_slot": "config",
				"target_slot": f"toolkits.{toolkit_key}",
			}
		)
		next_x += 220

	if selected_toolkits:
		next_y += 170
		next_x = 40

	for skill_name in selected_skills:
		node_index = len(nodes)
		nodes.append(
			_node_payload(
				"skill_config",
				label=skill_name,
				pos=(next_x, next_y),
				name=skill_name,
			)
		)
		skill_key = _slug_key(skill_name, fallback="skill", used=used_keys)
		edges.append(
			{
				"source": node_index,
				"target": agent_config_index,
				"source_slot": "config",
				"target_slot": f"skills.{skill_key}",
			}
		)
		next_x += 220

	workflow = {
		"type": "workflow",
		"options": {
			"name": workflow_name,
			"description": workflow_description,
		},
		"nodes": nodes,
		"edges": edges,
	}

	return {
		"name": workflow_name,
		"workflow": workflow,
		"omitted_toolkits": [],
		"runtime_bound_toolkits": runtime_bound_toolkits,
		"runtime_only_toolkits": sorted(_RUNTIME_BOUND_TOOLKITS),
	}


def _node_name(node: Dict[str, Any], index: Optional[int] = None) -> str:
	extra = node.get("extra") if isinstance(node, dict) else None
	label = None
	if isinstance(extra, dict):
		label = extra.get("name")
	if not label:
		label = node.get("name") if isinstance(node, dict) else None
	if label:
		return str(label)
	return f"node {index}" if index is not None else "node"


def _incoming_edges(edges: List[Dict[str, Any]], target_index: int) -> List[Dict[str, Any]]:
	return [edge for edge in edges if int(edge.get("target", -1)) == target_index]


def _validate_node_type(
	nodes: List[Dict[str, Any]],
	index: int,
	expected_type: str,
	*,
	context: str,
) -> Dict[str, Any]:
	try:
		node = nodes[index]
	except IndexError as exc:
		raise ValueError(f"{context} points to missing node index {index}.") from exc
	node_type = str(node.get("type") or "")
	if node_type != expected_type:
		raise ValueError(
			f"{context} must point to {expected_type}, got {node_type or 'unknown'} ({_node_name(node, index)})."
		)
	return node


def _resolve_single_linked_or_inline(
	nodes: List[Dict[str, Any]],
	edges: List[Dict[str, Any]],
	target_index: int,
	slot_name: str,
	expected_type: str,
) -> Tuple[Optional[Dict[str, Any]], Optional[int]]:
	matches = [edge for edge in _incoming_edges(edges, target_index) if str(edge.get("target_slot") or "") == slot_name]
	if len(matches) > 1:
		raise ValueError(f"{_node_name(nodes[target_index], target_index)} has multiple '{slot_name}' connections; expected exactly one.")
	if matches:
		source_index = int(matches[0].get("source", -1))
		node = _validate_node_type(
			nodes,
			source_index,
			expected_type,
			context=f"{_node_name(nodes[target_index], target_index)}.{slot_name}",
		)
		return node, source_index
	inline_value = nodes[target_index].get(slot_name)
	if inline_value is None:
		return None, None
	if not isinstance(inline_value, dict):
		raise ValueError(f"{_node_name(nodes[target_index], target_index)}.{slot_name} must be a {expected_type} object.")
	inline_type = str(inline_value.get("type") or expected_type)
	if inline_type != expected_type:
		raise ValueError(
			f"{_node_name(nodes[target_index], target_index)}.{slot_name} must be {expected_type}, got {inline_type}."
		)
	return inline_value, None


def _resolve_multi_linked_or_inline(
	nodes: List[Dict[str, Any]],
	edges: List[Dict[str, Any]],
	target_index: int,
	slot_prefix: str,
	expected_type: str,
) -> List[Tuple[str, Dict[str, Any], Optional[int]]]:
	results: List[Tuple[str, Dict[str, Any], Optional[int]]] = []
	prefix = slot_prefix + "."
	linked = [
		edge for edge in _incoming_edges(edges, target_index)
		if str(edge.get("target_slot") or "").startswith(prefix)
	]
	if linked:
		for edge in linked:
			target_slot = str(edge.get("target_slot") or "")
			key = target_slot.split(".", 1)[1] if "." in target_slot else ""
			source_index = int(edge.get("source", -1))
			node = _validate_node_type(
				nodes,
				source_index,
				expected_type,
				context=f"{_node_name(nodes[target_index], target_index)}.{target_slot}",
			)
			results.append((key, node, source_index))
		return results

	inline_value = nodes[target_index].get(slot_prefix)
	if inline_value is None:
		return results
	if not isinstance(inline_value, dict):
		raise ValueError(f"{_node_name(nodes[target_index], target_index)}.{slot_prefix} must be a mapping of {expected_type} nodes.")
	for key, raw_node in inline_value.items():
		if not isinstance(raw_node, dict):
			raise ValueError(f"{_node_name(nodes[target_index], target_index)}.{slot_prefix}.{key} must be a {expected_type} object.")
		inline_type = str(raw_node.get("type") or expected_type)
		if inline_type != expected_type:
			raise ValueError(
				f"{_node_name(nodes[target_index], target_index)}.{slot_prefix}.{key} must be {expected_type}, got {inline_type}."
			)
		results.append((str(key), raw_node, None))
	return results


def _clean_string(value: Any) -> str:
	return str(value or "").strip()


def _clean_string_list(value: Any) -> List[str]:
	if value is None:
		return []
	if isinstance(value, list):
		return [item for item in (_clean_string(v) for v in value) if item]
	if isinstance(value, str):
		text = value.strip()
		return [text] if text else []
	return []


def parse_console_workflow_import(
	workflow: Dict[str, Any],
	*,
	backend_name: str = DEFAULT_BACKEND_NAME,
) -> Dict[str, Any]:
	"""Parse a console-shaped workflow back into live console settings."""
	if not isinstance(workflow, dict):
		raise ValueError("Workflow payload must be a dictionary.")
	nodes = workflow.get("nodes") or []
	edges = workflow.get("edges") or []
	if not isinstance(nodes, list) or not nodes:
		raise ValueError("Workflow must contain nodes.")
	if not isinstance(edges, list):
		raise ValueError("Workflow edges must be a list.")

	chat_indexes = [index for index, node in enumerate(nodes) if str(node.get("type") or "") == "agent_chat"]
	if not chat_indexes:
		raise ValueError("A console workflow must contain one agent_chat node.")
	if len(chat_indexes) > 1:
		raise ValueError("A console workflow import currently supports exactly one agent_chat node.")
	chat_index = chat_indexes[0]

	agent_node, agent_index = _resolve_single_linked_or_inline(nodes, edges, chat_index, "config", "agent_config")
	if agent_node is None:
		raise ValueError("The agent_chat node has no connected agent_config.")

	backend_node, _ = _resolve_single_linked_or_inline(
		nodes if agent_index is not None else [agent_node],
		edges if agent_index is not None else [],
		agent_index if agent_index is not None else 0,
		"backend",
		"backend_config",
	)
	model_node, _ = _resolve_single_linked_or_inline(
		nodes if agent_index is not None else [agent_node],
		edges if agent_index is not None else [],
		agent_index if agent_index is not None else 0,
		"model",
		"model_config",
	)
	options_node, _ = _resolve_single_linked_or_inline(
		nodes if agent_index is not None else [agent_node],
		edges if agent_index is not None else [],
		agent_index if agent_index is not None else 0,
		"options",
		"agent_options_config",
	)
	memory_node, _ = _resolve_single_linked_or_inline(
		nodes if agent_index is not None else [agent_node],
		edges if agent_index is not None else [],
		agent_index if agent_index is not None else 0,
		"memory_mgr",
		"memory_manager_config",
	)
	session_node, _ = _resolve_single_linked_or_inline(
		nodes if agent_index is not None else [agent_node],
		edges if agent_index is not None else [],
		agent_index if agent_index is not None else 0,
		"session_mgr",
		"session_manager_config",
	)

	if backend_node is None:
		raise ValueError("The agent_config has no connected backend_config.")
	if model_node is None:
		raise ValueError("The agent_config has no connected model_config.")

	parsed_backend = _clean_string(backend_node.get("name") or backend_name) or backend_name
	if parsed_backend != backend_name:
		raise ValueError(f"Console workflow import currently supports only backend '{backend_name}', got '{parsed_backend}'.")

	toolkit_entries = _resolve_multi_linked_or_inline(
		nodes if agent_index is not None else [agent_node],
		edges if agent_index is not None else [],
		agent_index if agent_index is not None else 0,
		"toolkits",
		"toolkit_config",
	)
	skill_entries = _resolve_multi_linked_or_inline(
		nodes if agent_index is not None else [agent_node],
		edges if agent_index is not None else [],
		agent_index if agent_index is not None else 0,
		"skills",
		"skill_config",
	)

	toolkit_names: List[str] = []
	toolkit_args: Dict[str, Dict[str, Any]] = {}
	warnings: List[str] = []
	for _, toolkit_node, _ in toolkit_entries:
		tk_name = _clean_string(toolkit_node.get("name"))
		if not tk_name:
			raise ValueError(f"Toolkit node {_node_name(toolkit_node)} is missing its name.")
		toolkit_names.append(tk_name)
		args = toolkit_node.get("args")
		if isinstance(args, dict) and args:
			exported_args = _export_toolkit_args(tk_name, args)
			if exported_args:
				toolkit_args[tk_name] = dict(exported_args)
			if tk_name in _RUNTIME_BOUND_TOOLKITS:
				stripped = sorted(set(args.keys()) - set((exported_args or {}).keys()))
				if stripped:
					warnings.append(
						f"{tk_name} runtime-only args were ignored on import: " + ", ".join(stripped) + "."
					)

	skill_names = [name for name in (_clean_string(node.get("name")) for _, node, _ in skill_entries) if name]

	workflow_options = workflow.get("options") if isinstance(workflow.get("options"), dict) else {}
	options_payload = options_node or {}
	assistant_name = _clean_string(options_payload.get("name")) or _clean_string(workflow_options.get("name")) or "Numel Assistant"
	assistant_description = _clean_string(options_payload.get("description"))
	assistant_instructions = _clean_string_list(options_payload.get("instructions"))
	options_override = {
		"name": assistant_name,
		"description": assistant_description,
		"instructions": assistant_instructions,
		"markdown": bool(options_payload.get("markdown", True)),
	}

	if options_payload.get("prompt_override"):
		warnings.append("agent_options_config.prompt_override is not currently applied by the console bridge and was ignored.")

	use_backend_memory = memory_node is not None or session_node is not None
	memory_override: Dict[str, Any] = {}
	if session_node is not None:
		history_size = session_node.get("history_size")
		if isinstance(history_size, int) and history_size > 0:
			memory_override["session_history"] = history_size
	if (memory_node is None) != (session_node is None):
		warnings.append("Console import maps workflow memory/session managers to a single console memory toggle; partial memory wiring was imported as memory enabled.")

	unsupported_agent_fields = [
		field_name
		for field_name in ("content_db", "history_mgr", "knowledge_mgr", "tools")
		if agent_node.get(field_name)
	]
	if unsupported_agent_fields:
		warnings.append(
			"Console import ignored unsupported agent_config fields: " + ", ".join(unsupported_agent_fields) + "."
		)

	return {
		"workflow_name": _clean_string(workflow_options.get("name")) or assistant_name,
		"backend_name": parsed_backend,
		"model_source": _clean_string(model_node.get("source")) or "ollama",
		"model_name": _clean_string(model_node.get("name")) or "mistral",
		"toolkit_names": toolkit_names,
		"toolkit_args": toolkit_args,
		"skill_names": skill_names,
		"use_backend_memory": use_backend_memory,
		"memory_override": memory_override,
		"options_override": options_override,
		"warnings": warnings,
	}
