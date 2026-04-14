from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from schema import DEFAULT_BACKEND_NAME


_RUNTIME_ONLY_TOOLKITS = {
	"console_toolkit",
	"channel_toolkit",
	"workspace_toolkit",
	"agent_endpoint_toolkit",
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

	persisted_toolkits: List[str] = []
	omitted_toolkits: List[str] = []
	for tk_name in selected_toolkits:
		if tk_name in _RUNTIME_ONLY_TOOLKITS:
			omitted_toolkits.append(tk_name)
			continue
		persisted_toolkits.append(tk_name)

	workflow_description = (
		"Workflow-backed view of the current assistant console configuration. "
		"The interactive Agent Chat node is the closest workbench equivalent of the console panel."
	)
	if omitted_toolkits:
		workflow_description += " Runtime-only console toolkits were omitted from export: " + ", ".join(omitted_toolkits) + "."

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
	for tk_name in persisted_toolkits:
		node_index = len(nodes)
		nodes.append(
			_node_payload(
				"toolkit_config",
				label=tk_name,
				pos=(next_x, next_y),
				name=tk_name,
				args=dict(toolkit_args.get(tk_name) or {}) or None,
			)
		)
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

	if persisted_toolkits:
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
		"omitted_toolkits": omitted_toolkits,
		"runtime_only_toolkits": sorted(_RUNTIME_ONLY_TOOLKITS),
	}
