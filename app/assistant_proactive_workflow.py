from __future__ import annotations

import json

from copy import deepcopy
from typing import Any, Dict, Optional

from console_workflow import build_console_workflow_export
from schema import DEFAULT_BACKEND_NAME


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
	trigger_kind: str = "timer",
	trigger_config: Optional[Dict[str, Any]] = None,
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
		config={"options": options, "memory": {}},
		model_source=model_source,
		model_name=model_name,
		toolkit_names=list(toolkit_names or []),
		toolkit_args=dict(toolkit_args or {}),
		skill_names=list(skill_names or []),
		use_backend_memory=False,
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

	trigger_cfg = dict(trigger_config or {})
	trigger_idx = len(nodes)
	source_id = str(trigger_cfg.get("source_id") or "")
	if not source_id:
		raise ValueError("Proactive trigger requires source_id")

	trigger_kind = str(trigger_kind or "timer").strip().lower() or "timer"
	trigger_node: Optional[Dict[str, Any]] = None
	if trigger_kind == "timer":
		trigger_node = {
			"type": "timer_source_flow",
			"source_id": source_id,
			"interval_ms": max(30, int(task_interval_sec or 0)) * 1000,
			"max_triggers": -1,
			"immediate": bool(trigger_cfg.get("immediate", False)),
			"extra": {"pos": [260, 20], "name": task_name or "Timer Trigger"},
		}
	elif trigger_kind == "fswatch":
		trigger_node = {
			"type": "fswatch_source_flow",
			"source_id": source_id,
			"path": str(trigger_cfg.get("path") or "."),
			"recursive": bool(trigger_cfg.get("recursive", True)),
			"patterns": trigger_cfg.get("patterns") or "*",
			"events": trigger_cfg.get("events") or "created,modified,deleted,moved",
			"debounce_ms": max(0, int(trigger_cfg.get("debounce_ms") or 100)),
			"extra": {"pos": [260, 20], "name": task_name or "File Trigger"},
		}
	elif trigger_kind == "webhook":
		trigger_node = {
			"type": "webhook_source_flow",
			"source_id": source_id,
			"endpoint": str(trigger_cfg.get("endpoint") or f"/hook/{source_id}"),
			"methods": trigger_cfg.get("methods") or "POST",
			"secret": trigger_cfg.get("secret"),
			"extra": {"pos": [260, 20], "name": task_name or "Webhook Trigger"},
		}
	elif trigger_kind == "channel":
		trigger_node = {
			"type": "channel_receive_flow",
			"source_id": source_id,
			"channel_id": str(trigger_cfg.get("channel_id") or ""),
			"channel_types": trigger_cfg.get("channel_types") or "",
			"sender_filter": trigger_cfg.get("sender_filter"),
			"extra": {"pos": [260, 20], "name": task_name or "Channel Trigger"},
		}
	elif trigger_kind == "browser":
		trigger_node = {
			"type": "browser_source_flow",
			"source_id": source_id,
			"device_type": str(trigger_cfg.get("device_type") or "webcam"),
			"mode": str(trigger_cfg.get("mode") or "event"),
			"interval_ms": max(100, int(trigger_cfg.get("interval_ms") or 1000)),
			"resolution": trigger_cfg.get("resolution"),
			"audio_format": trigger_cfg.get("audio_format"),
			"extra": {"pos": [260, 20], "name": task_name or "Browser Trigger"},
		}
	else:
		raise ValueError(f"Unsupported proactive trigger kind: {trigger_kind}")
	nodes.append(trigger_node)

	loop_start_idx = len(nodes)
	nodes.append(
		{
			"type": "loop_start_flow",
			"condition": True,
			"max_iter": 1000000,
			"extra": {"pos": [500, 20], "name": "Trigger Loop"},
		}
	)

	event_listener_idx = len(nodes)
	nodes.append(
		{
			"type": "event_listener_flow",
			"mode": "any",
			"extra": {"pos": [740, 20], "name": "Wait for Trigger"},
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

	edges.extend(
		[
			{"source": start_idx, "target": trigger_idx, "source_slot": "flow_out", "target_slot": "flow_in"},
			{"source": trigger_idx, "target": loop_start_idx, "source_slot": "flow_out", "target_slot": "flow_in"},
			{"source": trigger_idx, "target": event_listener_idx, "source_slot": "registered_id", "target_slot": "sources.trigger"},
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
		"trigger_node_index": trigger_idx,
		"trigger_kind": trigger_kind,
		"source_ids": [source_id],
	}
