from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List, Optional, Tuple

from assistant_memory_contract import build_assistant_memory_components, normalize_assistant_memory_config
from runtime_settings import get_runtime_settings
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
	"runtime_context_id",
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


def _offset_node_position(node: Dict[str, Any], *, dx: int = 0, dy: int = 0) -> None:
	extra = node.get("extra")
	if not isinstance(extra, dict):
		return
	pos = extra.get("pos")
	if not (isinstance(pos, list) and len(pos) >= 2):
		return
	extra["pos"] = [int(pos[0]) + dx, int(pos[1]) + dy]


def _planner_export_request(planner_state: Dict[str, Any]) -> str:
	profile = _clean_string(planner_state.get("profile")) or "workflow"
	events = [item for item in (_clean_string(v) for v in planner_state.get("subscribe_events") or []) if item]
	timeout_s = int(planner_state.get("timeout_s") or 120)
	session_timeout_s = int(planner_state.get("session_timeout_s") or 600)
	max_iterations = int(planner_state.get("max_iterations") or 10)
	debounce_s = float(planner_state.get("debounce_s") or 2.0)
	instructions = _clean_string(planner_state.get("instructions"))
	event_lines = "\n".join(f"- {name}" for name in events) if events else "- manager.workflow_added"
	return (
		"[Planner Export]\n"
		"This branch represents the active planner turn for the current Assistant session. "
		"It is exported as a workbench-visible graph so you can inspect and adapt the planner logic.\n\n"
		f"[Planner Profile]\n{profile}\n\n"
		f"[Planner Runtime]\n"
		f"- debounce_s: {debounce_s}\n"
		f"- timeout_s: {timeout_s}\n"
		f"- session_timeout_s: {session_timeout_s}\n"
		f"- max_iterations: {max_iterations}\n\n"
		f"[Subscribed Events]\n{event_lines}\n\n"
		f"[Planner Instructions]\n{instructions or '(none)'}\n\n"
		"[Sample Event]\n"
		'{"event_type": "workflow.completed", "data": {"workflow_name": "Example Workflow", "status": "completed"}}\n\n'
		"Use this exported branch as the planner-facing agent turn. Replace the sample event or attach your own event-driven sources when adapting the graph."
	)


def _planner_event_summary(events: List[str]) -> str:
	items = [item for item in (_clean_string(v) for v in events) if item]
	if not items:
		return "0 events"
	if len(items) == 1:
		return items[0]
	if len(items) == 2:
		return f"{items[0]} + {items[1]}"
	return f"{items[0]} +{len(items) - 1}"


def _append_planner_export_subgraph(
	workflow: Dict[str, Any],
	*,
	workflow_name: str,
	model_source: str,
	model_name: str,
	toolkit_names: Optional[List[str]] = None,
	toolkit_args: Optional[Dict[str, Dict[str, Any]]] = None,
	skill_names: Optional[List[str]] = None,
	planner_state: Optional[Dict[str, Any]] = None,
	backend_name: str = DEFAULT_BACKEND_NAME,
) -> bool:
	if not planner_state or not bool(planner_state.get("enabled")):
		return False

	events = [item for item in (_clean_string(v) for v in planner_state.get("subscribe_events") or []) if item]
	planner_profile = _clean_string(planner_state.get("profile")) or "workflow"
	timeout_s = int(planner_state.get("timeout_s") or 120)
	session_timeout_s = int(planner_state.get("session_timeout_s") or 600)
	max_iterations = int(planner_state.get("max_iterations") or 10)
	debounce_s = float(planner_state.get("debounce_s") or 2.0)
	event_summary = _planner_event_summary(events)
	planner_export = build_console_workflow_export(
		config={
			"options": {
				"name": f"{workflow_name} Planner",
				"description": "Workflow-backed export of the active Assistant planner turn.",
				"instructions": [],
				"markdown": True,
			},
			"memory": {},
		},
		model_source=model_source,
		model_name=model_name,
		toolkit_names=list(toolkit_names or []),
		toolkit_args=dict(toolkit_args or {}),
		skill_names=list(skill_names or []),
		use_backend_memory=True,
		backend_name=backend_name,
	)
	planner_workflow = deepcopy(planner_export["workflow"])
	planner_branch_nodes = list(planner_workflow.get("nodes") or [])
	planner_edges = list(planner_workflow.get("edges") or [])

	agent_flow_local_index: Optional[int] = None
	for index, node in enumerate(planner_branch_nodes):
		if not isinstance(node, dict):
			continue
		_offset_node_position(node, dx=0, dy=440)
		node_type = str(node.get("type") or "")
		extra = node.setdefault("extra", {})
		label = _clean_string(extra.get("name"))
		if node_type == "backend_config":
			extra["name"] = "Planner Backend"
		elif node_type == "model_config":
			extra["name"] = "Planner Model"
		elif node_type == "agent_options_config":
			extra["name"] = "Planner Persona"
			instructions = list(node.get("instructions") or [])
			instructions.insert(
				0,
				(
					"[Planner Export]\n"
					f"Profile: {planner_profile}\n"
					"This exported branch is the planner-facing agent turn for the current Assistant session."
				),
			)
			node["instructions"] = instructions
		elif node_type == "agent_config":
			extra["name"] = "Planner Agent"
		elif node_type == "agent_chat":
			agent_flow_local_index = index
			node["type"] = "agent_flow"
			node["request"] = _planner_export_request(planner_state)
			node.pop("system_prompt", None)
			extra["name"] = "Planner Turn · current workbench"
		elif node_type == "toolkit_config" and label:
			extra["name"] = f"Planner Toolkit: {label}"
		elif node_type == "skill_config" and label:
			extra["name"] = f"Planner Skill: {label}"

	if agent_flow_local_index is None:
		raise ValueError("Planner export could not locate the planner agent node.")

	base_nodes = list(workflow.get("nodes") or [])
	base_edges = list(workflow.get("edges") or [])
	index_offset = len(base_nodes)
	agent_flow_global_index = index_offset + agent_flow_local_index

	planner_runtime_script = (
		"output = {\n"
		f"    'profile': {planner_profile!r},\n"
		f"    'timeout_s': {timeout_s},\n"
		f"    'session_timeout_s': {session_timeout_s},\n"
		f"    'max_iterations': {max_iterations},\n"
		f"    'debounce_s': {debounce_s!r},\n"
		f"    'subscribed_events': {events!r},\n"
		"    'target_graph': 'current workbench graph in Numel',\n"
		"    'target_interaction': 'Use workspace_toolkit to inspect and modify the graph loaded in the workbench.',\n"
		f"    'planner_session_id': {_clean_string(planner_state.get('planner_session_id'))!r},\n"
		f"    'browser_session_id': {_clean_string(planner_state.get('browser_session_id'))!r},\n"
		"}\n"
	)
	planner_prompt_script = (
		"state = input or {}\n"
		"events = state.get('subscribed_events') or []\n"
		"event_lines = '\\n'.join(f'- {name}' for name in events) if events else '- manager.workflow_added'\n"
		"output = (\n"
		"    '[Planner Export]\\n'\n"
		"    'This branch represents the active planner turn for the current Assistant session.\\n\\n'\n"
		"    '[Planner Scope]\\n'\n"
		"    + str(state.get('target_graph') or 'current workbench graph in Numel') + '\\n'\n"
		"    + str(state.get('target_interaction') or '') + '\\n\\n'\n"
		"    + '[Planner Profile]\\n' + str(state.get('profile') or 'workflow') + '\\n\\n'\n"
		"    + '[Planner Runtime]\\n'\n"
		"    + f\"- debounce_s: {state.get('debounce_s')}\\n\"\n"
		"    + f\"- timeout_s: {state.get('timeout_s')}\\n\"\n"
		"    + f\"- session_timeout_s: {state.get('session_timeout_s')}\\n\"\n"
		"    + f\"- max_iterations: {state.get('max_iterations')}\\n\\n\"\n"
		"    + '[Subscribed Events]\\n' + event_lines + '\\n\\n'\n"
		"    + '[Planner Session]\\n'\n"
		"    + f\"- planner_session_id: {state.get('planner_session_id') or '(none)'}\\n\"\n"
		"    + f\"- browser_session_id: {state.get('browser_session_id') or '(none)'}\\n\\n\"\n"
		"    + '[Planner Instructions]\\n'\n"
		"    + " + repr(_clean_string(planner_state.get("instructions")) or "(none)") + " + '\\n\\n'\n"
		"    + '[Sample Event]\\n'\n"
		"    + '{\"event_type\": \"workflow.completed\", \"data\": {\"workflow_name\": \"Example Workflow\", \"status\": \"completed\"}}\\n\\n'\n"
		"    + 'Use this exported branch as the planner-facing agent turn for the current workbench graph.'\n"
		")\n"
	)

	planner_control_nodes = [
		_node_payload(
			"start_flow",
			label="Planner Start",
			pos=(40, 640),
		),
		_node_payload(
			"loop_start_flow",
			label=f"Planner Loop · max {max_iterations}",
			pos=(260, 640),
			condition=True,
			max_iter=max_iterations,
		),
		_node_payload(
			"transform_flow",
			label=f"Planner Runtime · {timeout_s}s / {session_timeout_s}s / {debounce_s}s",
			pos=(520, 640),
			lang="python",
			script=planner_runtime_script,
		),
		_node_payload(
			"transform_flow",
			label=f"Planner Scope · current workbench · {event_summary}",
			pos=(820, 640),
			lang="python",
			script=planner_prompt_script,
		),
		_node_payload(
			"loop_end_flow",
			label="Planner Loop End",
			pos=(1760, 640),
		),
		_node_payload(
			"end_flow",
			label="Planner End",
			pos=(1980, 640),
		),
	]

	planner_controls_index_offset = index_offset + len(planner_branch_nodes)
	start_index = planner_controls_index_offset + 0
	loop_start_index = planner_controls_index_offset + 1
	runtime_index = planner_controls_index_offset + 2
	prompt_index = planner_controls_index_offset + 3
	loop_end_index = planner_controls_index_offset + 4
	end_index = planner_controls_index_offset + 5

	base_nodes.extend(planner_branch_nodes)
	base_nodes.extend(planner_control_nodes)

	for edge in planner_edges:
		base_edges.append(
			{
				**edge,
				"source": int(edge.get("source", -1)) + index_offset,
				"target": int(edge.get("target", -1)) + index_offset,
			}
		)

	base_edges.extend(
		[
			{"source": start_index, "target": loop_start_index, "source_slot": "flow_out", "target_slot": "flow_in"},
			{"source": loop_start_index, "target": runtime_index, "source_slot": "flow_out", "target_slot": "flow_in"},
			{"source": runtime_index, "target": prompt_index, "source_slot": "output", "target_slot": "input"},
			{"source": runtime_index, "target": prompt_index, "source_slot": "flow_out", "target_slot": "flow_in"},
			{"source": prompt_index, "target": agent_flow_global_index, "source_slot": "output", "target_slot": "request"},
			{"source": prompt_index, "target": agent_flow_global_index, "source_slot": "flow_out", "target_slot": "flow_in"},
			{"source": agent_flow_global_index, "target": loop_end_index, "source_slot": "flow_out", "target_slot": "flow_in"},
			{"source": loop_end_index, "target": loop_start_index, "source_slot": "flow_out", "target_slot": "flow_in", "loop": True},
			{"source": loop_end_index, "target": end_index, "source_slot": "flow_out", "target_slot": "flow_in"},
		]
	)

	workflow["nodes"] = base_nodes
	workflow["edges"] = base_edges
	options = dict(workflow.get("options") or {})
	description = _clean_string(options.get("description"))
	planner_note = (
		" Includes an exported planner branch for the active Assistant session. "
		"The planner branch is a workbench-visible view of the planner turn, loop budget, timing contract, and current-workbench scope; live debounce and event subscription ownership remain runtime-managed."
	)
	options["description"] = (description + planner_note).strip()
	workflow["options"] = options
	return True


def build_console_workflow_export(
	*,
	config: Dict[str, Any],
	model_source: str,
	model_name: str,
	toolkit_names: Optional[List[str]] = None,
	toolkit_args: Optional[Dict[str, Dict[str, Any]]] = None,
	skill_names: Optional[List[str]] = None,
	use_backend_memory: bool = True,
	memory_db_path: Optional[str] = None,
	backend_name: str = DEFAULT_BACKEND_NAME,
	planner_state: Optional[Dict[str, Any]] = None,
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
	content_db_index = None
	history_manager_index = None
	memory_manager_index = None
	session_manager_index = None

	if use_backend_memory:
		components = build_assistant_memory_components(
			memory_cfg=memory_cfg,
			model_source=model_source,
			model_name=model_name,
			memory_db_path=memory_db_path or str(get_runtime_settings().user_memory_dir / "assistant_console.db"),
		)
		settings = components["settings"]
		content_db_index = len(nodes)
		nodes.append(
			_node_payload(
				"content_db_config",
				label="Backend Memory Store",
				pos=(620, 60),
				engine="sqlite",
				url=components["content_db"].url,
			)
		)
		history_manager_index = len(nodes)
		nodes.append(
			_node_payload(
				"history_manager_config",
				label="History Context",
				pos=(840, 60),
				query=settings["history_query"],
				size=settings["history_size"],
			)
		)
		session_manager_index = len(nodes)
		nodes.append(
			_node_payload(
				"session_manager_config",
				label="Session Memory",
				pos=(1060, 60),
				query=settings["session_query"],
				update=settings["session_update"],
				history_size=settings["session_history"],
				prompt=components["session_mgr"].prompt,
			)
		)
		memory_manager_index = len(nodes)
		nodes.append(
			_node_payload(
				"memory_manager_config",
				label="Long-Term Memory",
				pos=(1280, 60),
				query=settings["memory_query"],
				update=settings["memory_update"],
				managed=settings["memory_managed"],
				prompt=components["memory_mgr"].prompt,
				instructions=components["memory_mgr"].instructions,
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
			{"source": 1, "target": session_manager_index, "source_slot": "config", "target_slot": "model"}
		)
		edges.append(
			{"source": session_manager_index, "target": agent_config_index, "source_slot": "config", "target_slot": "session_mgr"}
		)
	if history_manager_index is not None:
		edges.append(
			{"source": history_manager_index, "target": agent_config_index, "source_slot": "config", "target_slot": "history_mgr"}
		)
	if memory_manager_index is not None:
		edges.append(
			{"source": 1, "target": memory_manager_index, "source_slot": "config", "target_slot": "model"}
		)
		edges.append(
			{"source": memory_manager_index, "target": agent_config_index, "source_slot": "config", "target_slot": "memory_mgr"}
		)
	if content_db_index is not None:
		edges.append(
			{"source": content_db_index, "target": agent_config_index, "source_slot": "config", "target_slot": "content_db"}
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

	planner_included = _append_planner_export_subgraph(
		workflow,
		workflow_name=workflow_name,
		model_source=model_source,
		model_name=model_name,
		toolkit_names=selected_toolkits,
		toolkit_args=toolkit_args,
		skill_names=selected_skills,
		planner_state=planner_state,
		backend_name=backend_name,
	)

	return {
		"name": workflow_name,
		"workflow": workflow,
		"omitted_toolkits": [],
		"runtime_bound_toolkits": runtime_bound_toolkits,
		"runtime_only_toolkits": sorted(_RUNTIME_BOUND_TOOLKITS),
		"planner_included": planner_included,
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
	history_node, _ = _resolve_single_linked_or_inline(
		nodes if agent_index is not None else [agent_node],
		edges if agent_index is not None else [],
		agent_index if agent_index is not None else 0,
		"history_mgr",
		"history_manager_config",
	)
	content_db_node, _ = _resolve_single_linked_or_inline(
		nodes if agent_index is not None else [agent_node],
		edges if agent_index is not None else [],
		agent_index if agent_index is not None else 0,
		"content_db",
		"content_db_config",
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

	use_backend_memory = True
	memory_override = normalize_assistant_memory_config({})
	if history_node is not None:
		memory_override["history_query"] = bool(history_node.get("query", memory_override["history_query"]))
		history_size = history_node.get("size")
		if isinstance(history_size, int) and history_size > 0:
			memory_override["history_size"] = history_size
	if session_node is not None:
		memory_override["session_query"] = bool(session_node.get("query", memory_override["session_query"]))
		memory_override["session_update"] = bool(session_node.get("update", memory_override["session_update"]))
		history_size = session_node.get("history_size")
		if isinstance(history_size, int) and history_size > 0:
			memory_override["session_history"] = history_size
		if session_node.get("prompt") is not None:
			memory_override["session_prompt"] = session_node.get("prompt")
	if memory_node is not None:
		memory_override["memory_query"] = bool(memory_node.get("query", memory_override["memory_query"]))
		memory_override["memory_update"] = bool(memory_node.get("update", memory_override["memory_update"]))
		memory_override["memory_managed"] = bool(memory_node.get("managed", memory_override["memory_managed"]))
		if memory_node.get("prompt") is not None:
			memory_override["memory_prompt"] = memory_node.get("prompt")
		if memory_node.get("instructions") is not None:
			memory_override["memory_instructions"] = memory_node.get("instructions")
	if content_db_node is None:
		warnings.append("Console import did not find a content_db_config for backend memory; Numel will rebind the backend memory store at runtime.")

	unsupported_agent_fields = [
		field_name for field_name in ("knowledge_mgr", "tools") if agent_node.get(field_name)
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
