from __future__ import annotations

import json

from assistant_memory_contract import normalize_assistant_memory_config
from copy import deepcopy
from typing import Any, Dict, List, Optional

from console_workflow import build_console_workflow_export
from schema import DEFAULT_BACKEND_NAME


def _build_trigger_node(
	*,
	task_name: str,
	trigger_kind: str,
	trigger_config: Dict[str, Any],
	task_interval_sec: int,
	pos: List[int],
) -> Dict[str, Any]:
	source_id = str(trigger_config.get("source_id") or "")
	if not source_id:
		raise ValueError("Proactive trigger requires source_id")
	label = task_name or "Trigger"
	if trigger_kind == "timer":
		return {
			"type": "timer_source_flow",
			"source_id": source_id,
			"interval_ms": max(30, int(task_interval_sec or 0)) * 1000,
			"max_triggers": -1,
			"immediate": bool(trigger_config.get("immediate", False)),
			"extra": {"pos": pos, "name": label or "Timer Source"},
		}
	if trigger_kind == "fswatch":
		return {
			"type": "fswatch_source_flow",
			"source_id": source_id,
			"path": str(trigger_config.get("path") or "."),
			"recursive": bool(trigger_config.get("recursive", True)),
			"patterns": trigger_config.get("patterns") or "*",
			"events": trigger_config.get("events") or "created,modified,deleted,moved",
			"debounce_ms": max(0, int(trigger_config.get("debounce_ms") or 100)),
			"extra": {"pos": pos, "name": label or "File Source"},
		}
	if trigger_kind == "webhook":
		return {
			"type": "webhook_source_flow",
			"source_id": source_id,
			"endpoint": str(trigger_config.get("endpoint") or f"/hook/{source_id}"),
			"methods": trigger_config.get("methods") or "POST",
			"secret": trigger_config.get("secret"),
			"extra": {"pos": pos, "name": label or "Webhook Source"},
		}
	if trigger_kind == "channel":
		return {
			"type": "channel_receive_flow",
			"source_id": source_id,
			"channel_id": str(trigger_config.get("channel_id") or ""),
			"channel_types": trigger_config.get("channel_types") or "",
			"sender_filter": trigger_config.get("sender_filter"),
			"extra": {"pos": pos, "name": label or "Channel Source"},
		}
	if trigger_kind == "browser":
		return {
			"type": "browser_source_flow",
			"source_id": source_id,
			"device_type": str(trigger_config.get("device_type") or "webcam"),
			"mode": str(trigger_config.get("mode") or "event"),
			"interval_ms": max(100, int(trigger_config.get("interval_ms") or 1000)),
			"resolution": trigger_config.get("resolution"),
			"audio_format": trigger_config.get("audio_format"),
			"extra": {"pos": pos, "name": label or "Browser Source"},
		}
	raise ValueError(f"Unsupported proactive trigger kind: {trigger_kind}")


def build_assistant_proactive_workflow(
	*,
	deployment_name: str,
	deployment_profile: str,
	deployment_description: str,
	deployment_instructions: str,
	task_name: str,
	task_prompt: str,
	task_interval_sec: int,
	model_source: str,
	model_name: str,
	toolkit_names: list[str],
	toolkit_args: Optional[Dict[str, Dict[str, Any]]] = None,
	skill_names: Optional[list[str]] = None,
	options_config: Optional[Dict[str, Any]] = None,
	memory_config: Optional[Dict[str, Any]] = None,
	memory_db_path: Optional[str] = None,
	trigger_kind: str = "timer",
	trigger_config: Optional[Dict[str, Any]] = None,
	trigger_sources: Optional[List[Dict[str, Any]]] = None,
	trigger_mode: str = "any",
	backend_name: str = DEFAULT_BACKEND_NAME,
) -> Dict[str, Any]:
	"""Build a long-running proactive workflow for one deployment task.

	This runtime path now supports timer plus event-driven trigger kinds such as
	fswatch, webhook, channel, and browser, all using the same workflow-backed
	execution shape.
	"""
	options = dict(options_config or {})
	options["name"] = deployment_name or options.get("name") or "Assistant Deployment"
	if deployment_description:
		options["description"] = deployment_description

	exported = build_console_workflow_export(
		config={"options": options, "memory": normalize_assistant_memory_config(memory_config)},
		model_source=model_source,
		model_name=model_name,
		toolkit_names=list(toolkit_names or []),
		toolkit_args=dict(toolkit_args or {}),
		skill_names=list(skill_names or []),
		use_backend_memory=True,
		memory_db_path=memory_db_path,
		backend_name=backend_name,
	)
	workflow = deepcopy(exported["workflow"])
	nodes = list(workflow.get("nodes") or [])
	agent_node_index = next(
		(index for index, node in enumerate(nodes) if isinstance(node, dict) and node.get("type") == "agent_chat"),
		None,
	)
	if agent_node_index is None:
		raise ValueError("Console workflow export did not contain an agent_chat node")
	nodes[agent_node_index]["type"] = "agent_flow"
	nodes[agent_node_index].pop("system_prompt", None)
	nodes[agent_node_index]["request"] = None

	deployment_block = (
		"[Assistant Deployment]\n"
		f"Name: {deployment_name}\n"
		f"Profile: {deployment_profile or 'general'}\n"
		f"Description: {deployment_description or '(none)'}\n"
		f"Instructions: {deployment_instructions or '(none)'}"
	)
	for node in nodes:
		if not isinstance(node, dict) or node.get("type") != "agent_options_config":
			continue
		instructions = list(node.get("instructions") or [])
		instructions.insert(0, deployment_block)
		node["instructions"] = instructions
		break

	workflow["nodes"] = nodes
	edges = list(workflow.get("edges") or [])

	start_idx = len(nodes)
	nodes.append({"type": "start_flow", "extra": {"pos": [40, 20], "name": "Start"}})

	normalized_trigger_mode = str(trigger_mode or "any").strip().lower() or "any"
	if normalized_trigger_mode not in {"any", "all", "race"}:
		normalized_trigger_mode = "any"
	normalized_sources = list(trigger_sources or [])
	if not normalized_sources:
		normalized_sources = [{
			"kind": str(trigger_kind or "timer").strip().lower() or "timer",
			"interval_sec": max(30, int(task_interval_sec or 0)) if str(trigger_kind or "timer").strip().lower() == "timer" else int(task_interval_sec or 0),
			"trigger_config": dict(trigger_config or {}),
		}]

	trigger_indexes: List[int] = []
	source_ids: List[str] = []
	for index, source in enumerate(normalized_sources):
		source_kind = str(source.get("kind") or trigger_kind or "timer").strip().lower() or "timer"
		source_interval = int(source.get("interval_sec") or (task_interval_sec if source_kind == "timer" else 0))
		source_cfg = dict(source.get("trigger_config") or source.get("trigger") or {})
		source_id = str(source_cfg.get("source_id") or "")
		if not source_id:
			raise ValueError("Proactive trigger requires source_id")
		source_ids.append(source_id)
		trigger_indexes.append(len(nodes))
		label = task_name if index == 0 else f"{task_name} Trigger {index + 1}"
		nodes.append(
			_build_trigger_node(
				task_name=label,
				trigger_kind=source_kind,
				trigger_config=source_cfg,
				task_interval_sec=source_interval,
				pos=[260, 20 + index * 120],
			)
		)

	loop_start_idx = len(nodes)
	nodes.append(
		{
			"type": "loop_start_flow",
			"condition": True,
			"max_iter": 1000000,
			"extra": {"pos": [500, 20 + max(0, len(trigger_indexes) - 1) * 60], "name": "Trigger Loop"},
		}
	)

	event_listener_idx = len(nodes)
	nodes.append(
		{
			"type": "event_listener_flow",
			"mode": normalized_trigger_mode,
			"extra": {"pos": [740, 20 + max(0, len(trigger_indexes) - 1) * 60], "name": "Event Listener"},
		}
	)

	build_prompt_idx = len(nodes)
	prompt_literal = json.dumps(str(task_prompt or ""))
	nodes.append(
		{
			"type": "transform_flow",
			"lang": "python",
			"script": (
				"import datetime, json\n"
				f"prompt = {prompt_literal}\n"
				"event_payload = input\n"
				"ts = datetime.datetime.now().isoformat()\n"
				"if isinstance(event_payload, (dict, list)):\n"
				"    payload_text = json.dumps(event_payload, default=str)\n"
				"else:\n"
				"    payload_text = str(event_payload)\n"
				"output = (\n"
				"    '[Proactive Trigger]\\n'\n"
				"    f'Current time: {ts}\\n'\n"
				"    f'Task: ' + " + json.dumps(task_name or "") + " + '\\n\\n'\n"
				"    + prompt\n"
				"    + '\\n\\n[Trigger Event]\\n'\n"
				"    + payload_text[:4000]\n"
				")\n"
			),
			"extra": {"pos": [980, 20], "name": "Build Prompt"},
		}
	)

	extract_reply_idx = len(nodes)
	nodes.append(
		{
			"type": "transform_flow",
			"lang": "python",
			"script": (
				"r = input\n"
				"if isinstance(r, dict):\n"
				"    envelope = r.get('response', {}) or {}\n"
				"    raw = envelope.get('response')\n"
				"    if isinstance(raw, dict):\n"
				"        content = raw.get('content')\n"
				"    else:\n"
				"        content = raw\n"
				"else:\n"
				"    content = r\n"
				"if isinstance(content, list):\n"
				"    output = '\\n'.join(str(item) for item in content)\n"
				"elif content is None:\n"
				"    output = ''\n"
				"else:\n"
				"    output = str(content)\n"
			),
			"extra": {"pos": [1640, 20], "name": "Extract Reply"},
		}
	)

	loop_end_idx = len(nodes)
	nodes.append({"type": "loop_end_flow", "extra": {"pos": [1880, 20], "name": "Loop End"}})

	end_idx = len(nodes)
	nodes.append({"type": "end_flow", "extra": {"pos": [2120, 20], "name": "End"}})

	if not trigger_indexes:
		raise ValueError("Proactive runtime requires at least one trigger source")
	edges.append({"source": start_idx, "target": trigger_indexes[0], "source_slot": "flow_out", "target_slot": "flow_in"})
	for index, trigger_idx in enumerate(trigger_indexes):
		next_target = trigger_indexes[index + 1] if index + 1 < len(trigger_indexes) else loop_start_idx
		edges.append({"source": trigger_idx, "target": next_target, "source_slot": "flow_out", "target_slot": "flow_in"})
		edges.append({"source": trigger_idx, "target": event_listener_idx, "source_slot": "registered_id", "target_slot": f"sources.trigger_{index + 1}"})

	edges.extend(
		[
			{"source": loop_start_idx, "target": event_listener_idx, "source_slot": "flow_out", "target_slot": "flow_in"},
			{"source": event_listener_idx, "target": build_prompt_idx, "source_slot": "event", "target_slot": "input"},
			{"source": event_listener_idx, "target": build_prompt_idx, "source_slot": "flow_out", "target_slot": "flow_in"},
			{"source": build_prompt_idx, "target": agent_node_index, "source_slot": "output", "target_slot": "request"},
			{"source": build_prompt_idx, "target": agent_node_index, "source_slot": "flow_out", "target_slot": "flow_in"},
			{"source": agent_node_index, "target": extract_reply_idx, "source_slot": "response", "target_slot": "input"},
			{"source": agent_node_index, "target": extract_reply_idx, "source_slot": "flow_out", "target_slot": "flow_in"},
			{"source": extract_reply_idx, "target": loop_end_idx, "source_slot": "flow_out", "target_slot": "flow_in"},
			{"source": loop_end_idx, "target": loop_start_idx, "source_slot": "flow_out", "target_slot": "flow_in", "loop": True},
			{"source": loop_end_idx, "target": end_idx, "source_slot": "flow_out", "target_slot": "flow_in"},
		]
	)

	workflow["edges"] = edges
	workflow["options"] = {
		**dict(workflow.get("options") or {}),
		"name": f"Proactive Runtime: {deployment_name} / {task_name}",
		"description": "Generated runtime workflow backing an assistant deployment proactive task.",
	}

	return {
		"workflow": workflow,
		"response_node_index": extract_reply_idx,
		"trigger_node_index": trigger_indexes[0],
		"trigger_kind": str(normalized_sources[0].get("kind") or trigger_kind or "timer").strip().lower() or "timer",
		"trigger_mode": normalized_trigger_mode,
		"source_ids": source_ids,
	}
