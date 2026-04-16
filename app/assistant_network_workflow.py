from __future__ import annotations

import uuid

from typing import Any, Dict, List, Optional, Tuple


def _node_payload(
	node_type: str,
	*,
	label: str,
	pos: Tuple[int, int],
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


def _clean_string_list(value: Any) -> List[str]:
	if not isinstance(value, list):
		return []
	return [str(item).strip() for item in value if str(item).strip()]


def _string_list(value: Any) -> List[str]:
	if value is None:
		return []
	if isinstance(value, list):
		return [str(item).strip() for item in value if str(item).strip()]
	return [part.strip() for part in str(value).split(",") if part.strip()]


def _optional_text(value: Any) -> Optional[str]:
	text = str(value or "").strip()
	return text or None


def _node_label(node: Dict[str, Any], fallback: str = "") -> str:
	extra = node.get("extra") if isinstance(node.get("extra"), dict) else {}
	return str(node.get("name") or extra.get("name") or fallback).strip()


def _generated_id(prefix: str) -> str:
	return f"{prefix}_{uuid.uuid4().hex[:8]}"


def _proactive_source_id(deployment_id: str, task_id: str) -> str:
	return f"deploy_proactive_{deployment_id}_{task_id}"


_PROACTIVE_SOURCE_TYPES = {
	"timer_source_flow",
	"fswatch_source_flow",
	"webhook_source_flow",
	"browser_source_flow",
	"channel_receive_flow",
}


def _build_proactive_source_node(
	*,
	deployment_id: str,
	task: Dict[str, Any],
	pos: Tuple[int, int],
) -> Dict[str, Any]:
	task_id = str(task.get("id") or task.get("task_id") or _generated_id("proactive"))
	task_name = str(task.get("name") or "Proactive Trigger")
	trigger_kind = str(task.get("trigger_kind") or "timer").strip().lower() or "timer"
	trigger = dict(task.get("trigger") or {})
	source_id = str(trigger.get("source_id") or _proactive_source_id(deployment_id, task_id))

	if trigger_kind == "timer":
		return _node_payload(
			"timer_source_flow",
			label=task_name,
			pos=pos,
			source_id=source_id,
			interval_ms=max(30000, int(task.get("interval_sec") or 900) * 1000),
			max_triggers=int(trigger.get("max_triggers", -1) or -1),
			immediate=bool(trigger.get("immediate", False)),
		)
	if trigger_kind == "fswatch":
		return _node_payload(
			"fswatch_source_flow",
			label=task_name,
			pos=pos,
			source_id=source_id,
			path=str(trigger.get("path") or "."),
			recursive=bool(trigger.get("recursive", True)),
			patterns=trigger.get("patterns") or "*",
			events=trigger.get("events") or "created,modified,deleted,moved",
			debounce_ms=max(0, int(trigger.get("debounce_ms") or 100)),
		)
	if trigger_kind == "webhook":
		return _node_payload(
			"webhook_source_flow",
			label=task_name,
			pos=pos,
			source_id=source_id,
			endpoint=str(trigger.get("endpoint") or f"/hook/{source_id}"),
			methods=trigger.get("methods") or "POST",
			secret=trigger.get("secret"),
		)
	if trigger_kind == "channel":
		return _node_payload(
			"channel_receive_flow",
			label=task_name,
			pos=pos,
			source_id=source_id,
			channel_id=str(trigger.get("channel_id") or ""),
			channel_types=trigger.get("channel_types") or "",
			sender_filter=trigger.get("sender_filter"),
		)
	if trigger_kind == "browser":
		return _node_payload(
			"browser_source_flow",
			label=task_name,
			pos=pos,
			source_id=source_id,
			device_type=str(trigger.get("device_type") or "webcam"),
			mode=str(trigger.get("mode") or "event"),
			interval_ms=max(100, int(trigger.get("interval_ms") or 1000)),
			resolution=trigger.get("resolution"),
			audio_format=trigger.get("audio_format"),
		)
	return _node_payload(
		"timer_source_flow",
		label=task_name,
		pos=pos,
		source_id=source_id,
		interval_ms=max(30000, int(task.get("interval_sec") or 900) * 1000),
		max_triggers=-1,
		immediate=False,
	)


def _trigger_from_source_node(node: Dict[str, Any]) -> tuple[str, Optional[Dict[str, Any]], int]:
	node_type = str(node.get("type") or "").strip()
	if node_type == "timer_source_flow":
		interval_ms = max(30000, int(node.get("interval_ms") or 30000))
		return (
			"timer",
			{
				"immediate": bool(node.get("immediate", False)),
				"max_triggers": int(node.get("max_triggers", -1) or -1),
			},
			max(30, int(interval_ms / 1000)),
		)
	if node_type == "fswatch_source_flow":
		return (
			"fswatch",
			{
				"path": str(node.get("path") or "."),
				"recursive": bool(node.get("recursive", True)),
				"patterns": node.get("patterns") or "*",
				"events": node.get("events") or "created,modified,deleted,moved",
				"debounce_ms": max(0, int(node.get("debounce_ms") or 100)),
			},
			0,
		)
	if node_type == "webhook_source_flow":
		trigger = {
			"endpoint": str(node.get("endpoint") or ""),
			"methods": node.get("methods") or "POST",
		}
		if node.get("secret") not in (None, ""):
			trigger["secret"] = node.get("secret")
		return (
			"webhook",
			trigger,
			0,
		)
	if node_type == "channel_receive_flow":
		trigger = {
			"channel_id": str(node.get("channel_id") or ""),
			"channel_types": node.get("channel_types") or "",
		}
		if node.get("sender_filter") not in (None, ""):
			trigger["sender_filter"] = node.get("sender_filter")
		return (
			"channel",
			trigger,
			0,
		)
	if node_type == "browser_source_flow":
		trigger = {
			"device_type": str(node.get("device_type") or "webcam"),
			"mode": str(node.get("mode") or "event"),
			"interval_ms": max(100, int(node.get("interval_ms") or 1000)),
		}
		if node.get("resolution") not in (None, ""):
			trigger["resolution"] = node.get("resolution")
		if node.get("audio_format") not in (None, ""):
			trigger["audio_format"] = node.get("audio_format")
		return (
			"browser",
			trigger,
			0,
		)
	raise ValueError(f"Unsupported proactive source node type: {node_type or '(missing)'}")


def build_assistant_network_workflow(
	*,
	deployments: List[Dict[str, Any]],
	channels: List[Dict[str, Any]],
) -> Dict[str, Any]:
	"""Materialize the live assistant deployment network as a workflow-shaped graph."""
	items = sorted(list(deployments or []), key=lambda row: (str(row.get("name") or "").lower(), str(row.get("id") or "")))
	channel_rows = sorted(list(channels or []), key=lambda row: (str(row.get("name") or "").lower(), str(row.get("id") or "")))

	channel_bindings: Dict[str, str] = {}
	for deployment in items:
		for channel_id in deployment.get("channel_ids") or []:
			channel_bindings[str(channel_id)] = str(deployment.get("id") or "")

	nodes: List[Dict[str, Any]] = []
	edges: List[Dict[str, Any]] = []
	deployment_indexes: Dict[str, int] = {}

	deployment_positions: Dict[str, Tuple[int, int]] = {}
	for index, deployment in enumerate(items):
		column = index % 2
		row = index // 2
		deployment_positions[str(deployment.get("id") or "")] = (500 + column * 420, 120 + row * 380)

	for deployment in items:
		deployment_id = str(deployment.get("id") or "")
		x, y = deployment_positions[deployment_id]
		runtime = deployment.get("runtime") or {}
		node_index = len(nodes)
		nodes.append(
			_node_payload(
				"assistant_deployment_runtime_config",
				label=str(deployment.get("name") or deployment_id or "Deployment"),
				pos=(x, y),
				deployment_id=deployment_id,
				name=str(deployment.get("name") or ""),
				profile=str(deployment.get("profile") or "general"),
				description=str(deployment.get("description") or "") or None,
				instructions=str(deployment.get("instructions") or "") or None,
				status=str(deployment.get("status") or "stopped"),
				enabled=bool(deployment.get("enabled")),
				auto_start=bool(deployment.get("auto_start")),
				model_source=str(deployment.get("model_source") or "") or None,
				model_name=str(deployment.get("model_name") or "") or None,
				linked_space_id=str(deployment.get("linked_space_id") or "") or None,
				linked_space_title=str(deployment.get("linked_space_title") or "") or None,
				linked_workflow_name=str(deployment.get("linked_workflow_name") or "") or None,
				toolkit_names=_clean_string_list(deployment.get("toolkit_names")),
				skill_names=_clean_string_list(deployment.get("skill_names")),
				proactive_delivery_mode=str(((deployment.get("safety") or {}).get("proactive_delivery_mode") or "")) or None,
				tool_execution_mode=str(((deployment.get("safety") or {}).get("tool_execution_mode") or "")) or None,
				pending_approval_count=int(runtime.get("pending_approval_count") or 0),
			)
		)
		deployment_indexes[deployment_id] = node_index

	bound_channel_offsets: Dict[str, int] = {}
	unbound_y = 120
	for channel in channel_rows:
		channel_id = str(channel.get("id") or "")
		channel_name = str(channel.get("name") or channel_id or "Channel")
		bound_to = channel_bindings.get(channel_id)
		if bound_to and bound_to in deployment_positions:
			dep_x, dep_y = deployment_positions[bound_to]
			offset = bound_channel_offsets.get(bound_to, 0)
			x = dep_x - 340
			y = dep_y - 80 + offset * 130
			bound_channel_offsets[bound_to] = offset + 1
		else:
			x = 80
			y = unbound_y
			unbound_y += 140
		node_index = len(nodes)
		nodes.append(
			_node_payload(
				"channel_runtime_config",
				label=channel_name,
				pos=(x, y),
				channel_id=channel_id,
				name=channel_name,
				channel_type=str(channel.get("channel_type") or ""),
				status=str(channel.get("status") or ""),
				enabled=bool(channel.get("enabled", True)),
				auto_start=bool(channel.get("auto_start")),
				session_id=str(channel.get("session_id") or "") or None,
				allowed_users=_clean_string_list(channel.get("allowed_users")),
				owner=str(channel.get("created_by") or "") or None,
			)
		)
		if bound_to and bound_to in deployment_indexes:
			edges.append(
				{
					"source": node_index,
					"target": deployment_indexes[bound_to],
					"source_slot": "config",
					"target_slot": f"bound_channels.{channel_id}",
				}
			)

	used_route_keys: Dict[str, set[str]] = {}
	for deployment in items:
		deployment_id = str(deployment.get("id") or "")
		source_index = deployment_indexes.get(deployment_id)
		if source_index is None:
			continue
		source_x, source_y = deployment_positions[deployment_id]
		for route_index, rule in enumerate(deployment.get("routing_rules") or []):
			target_deployment_id = str(rule.get("target_deployment_id") or "")
			target_index = deployment_indexes.get(target_deployment_id)
			target_pos = deployment_positions.get(target_deployment_id, (source_x + 420, source_y))
			x = source_x + 300 if target_pos[0] <= source_x else (source_x + target_pos[0]) // 2
			y = int((source_y + target_pos[1]) / 2) + route_index * 80
			node_index = len(nodes)
			nodes.append(
				_node_payload(
					"assistant_route_runtime_config",
					label=str(rule.get("name") or "Route"),
					pos=(x, y),
					route_id=str(rule.get("id") or f"route_{deployment_id}_{route_index}"),
					name=str(rule.get("name") or "") or "Route",
					keywords=", ".join(_clean_string_list(rule.get("keywords"))),
					target_deployment_id=target_deployment_id,
					target_name=str(rule.get("target_name") or "") or None,
					enabled=bool(rule.get("enabled", True)),
				)
			)
			route_keys = used_route_keys.setdefault(deployment_id, set())
			out_key = _slug_key(str(rule.get("id") or f"route_{route_index}"), fallback="route", used=route_keys)
			edges.append(
				{
					"source": node_index,
					"target": source_index,
					"source_slot": "config",
					"target_slot": f"outgoing_routes.{out_key}",
				}
			)
			if target_index is not None:
				in_keys = used_route_keys.setdefault(target_deployment_id, set())
				in_key = _slug_key(str(rule.get("id") or f"route_{route_index}"), fallback="incoming_route", used=in_keys)
				edges.append(
					{
						"source": node_index,
						"target": target_index,
						"source_slot": "config",
						"target_slot": f"incoming_routes.{in_key}",
					}
				)

		proactive_keys = used_route_keys.setdefault(f"{deployment_id}:proactive", set())
		for task_index, task in enumerate(deployment.get("proactive_tasks") or []):
			task_runtime = task.get("runtime") or {}
			source_node_index = len(nodes)
			nodes.append(
				_build_proactive_source_node(
					deployment_id=deployment_id,
					task=task,
					pos=(source_x - 270, source_y + 170 + task_index * 150),
				)
			)
			listener_index = len(nodes)
			nodes.append(
				_node_payload(
					"event_listener_flow",
					label=f"{str(task.get('name') or 'Proactive Task')} Listener",
					pos=(source_x - 30, source_y + 170 + task_index * 150),
					mode="any",
				)
			)
			node_index = len(nodes)
			nodes.append(
				_node_payload(
					"assistant_proactive_runtime_config",
					label=str(task.get("name") or "Proactive Task"),
					pos=(source_x + 240, source_y + 170 + task_index * 150),
					task_id=str(task.get("id") or f"task_{deployment_id}_{task_index}"),
					name=str(task.get("name") or ""),
					prompt=str(task.get("prompt") or "") or None,
					interval_sec=int(task.get("interval_sec")) if task.get("interval_sec") not in (None, "") else (900 if str(task.get("trigger_kind") or "timer").strip().lower() == "timer" else 0),
					trigger_kind=str(task.get("trigger_kind") or "timer"),
					trigger=dict(task.get("trigger") or {}) or None,
					channel_id=str(task.get("channel_id") or "") or None,
					recipient_id=str(task.get("recipient_id") or "") or None,
					enabled=bool(task.get("enabled", True)),
					send_response=bool(task.get("send_response", True)),
					runtime_status=str(task_runtime.get("status") or "") or None,
					last_status=str(task_runtime.get("last_status") or "") or None,
					next_run_at=str(task_runtime.get("next_run_at") or "") or None,
					last_run_at=str(task_runtime.get("last_run_at") or "") or None,
				)
			)
			task_key = _slug_key(str(task.get("id") or task_index), fallback="task", used=proactive_keys)
			edges.append(
				{
					"source": node_index,
					"target": source_index,
					"source_slot": "config",
					"target_slot": f"proactive_tasks.{task_key}",
				}
			)
			edges.append(
				{
					"source": source_node_index,
					"target": listener_index,
					"source_slot": "registered_id",
					"target_slot": "sources.trigger",
				}
			)
			edges.append(
				{
					"source": source_node_index,
					"target": listener_index,
					"source_slot": "flow_out",
					"target_slot": "flow_in",
				}
			)
			edges.append(
				{
					"source": listener_index,
					"target": node_index,
					"source_slot": "event",
					"target_slot": "trigger_event",
				}
			)
			edges.append(
				{
					"source": listener_index,
					"target": node_index,
					"source_slot": "source_id",
					"target_slot": "trigger_source_id",
				}
			)

		approval_keys = used_route_keys.setdefault(f"{deployment_id}:approval", set())
		pending_rows = [
			*list(deployment.get("pending_proactive_approvals") or []),
			*list(deployment.get("pending_tool_approvals") or []),
		]
		for approval_index, approval in enumerate(pending_rows):
			preview = str(
				approval.get("response_text")
				or approval.get("preview")
				or ""
			).strip()
			node_index = len(nodes)
			nodes.append(
				_node_payload(
					"assistant_approval_runtime_config",
					label=str(approval.get("task_name") or approval.get("tool_name") or "Pending Approval"),
					pos=(source_x + 310, source_y - 60 + approval_index * 140),
					approval_id=str(approval.get("id") or f"approval_{deployment_id}_{approval_index}"),
					kind="tool" if approval.get("tool_name") else "proactive",
					status=str(approval.get("status") or "pending"),
					channel_id=str(approval.get("channel_id") or "") or None,
					task_name=str(approval.get("task_name") or "") or None,
					tool_name=str(approval.get("tool_name") or "") or None,
					created_at=str(approval.get("created_at") or "") or None,
					preview=preview[:240] or None,
				)
			)
			approval_key = _slug_key(str(approval.get("id") or approval_index), fallback="approval", used=approval_keys)
			edges.append(
				{
					"source": node_index,
					"target": source_index,
					"source_slot": "config",
					"target_slot": f"pending_approvals.{approval_key}",
				}
			)

	workflow = {
		"type": "workflow",
		"options": {
			"name": "Assistant Deployment Network",
			"description": "Operational workflow-backed view of the current assistant deployment network, including bound channels, routing rules, proactive tasks, and pending approvals.",
		},
		"nodes": nodes,
		"edges": edges,
	}
	return {
		"name": "Assistant Deployment Network",
		"workflow": workflow,
	}


def parse_assistant_network_workflow_import(workflow: Dict[str, Any]) -> Dict[str, Any]:
	"""Parse a workflow-backed assistant network graph into deployment/channel config payloads."""
	if not isinstance(workflow, dict):
		raise ValueError("No valid workflow JSON")
	nodes = workflow.get("nodes")
	edges = workflow.get("edges")
	if not isinstance(nodes, list) or not isinstance(edges, list):
		raise ValueError("Workflow must contain nodes and edges")

	warnings: List[str] = []
	deployment_nodes: Dict[int, Dict[str, Any]] = {}
	channel_nodes: Dict[int, Dict[str, Any]] = {}
	route_nodes: Dict[int, Dict[str, Any]] = {}
	task_nodes: Dict[int, Dict[str, Any]] = {}
	approval_nodes: Dict[int, Dict[str, Any]] = {}
	listener_nodes: Dict[int, Dict[str, Any]] = {}
	source_nodes: Dict[int, Dict[str, Any]] = {}

	seen_deployment_ids: set[str] = set()
	seen_channel_ids: set[str] = set()
	seen_route_ids: set[str] = set()
	seen_task_ids: set[str] = set()

	for index, raw in enumerate(nodes):
		if not isinstance(raw, dict):
			continue
		node_type = str(raw.get("type") or "").strip()
		if node_type == "assistant_deployment_runtime_config":
			deployment_id = _optional_text(raw.get("deployment_id")) or _generated_id("deploy")
			if deployment_id in seen_deployment_ids:
				raise ValueError(f"Deployment id '{deployment_id}' appears more than once in the workflow.")
			seen_deployment_ids.add(deployment_id)
			deployment_nodes[index] = {
				"id": deployment_id,
				"name": _optional_text(raw.get("name")) or _node_label(raw, "Deployment") or deployment_id,
				"profile": _optional_text(raw.get("profile")) or "general",
				"description": _optional_text(raw.get("description")),
				"instructions": _optional_text(raw.get("instructions")),
				"enabled": bool(raw.get("enabled")),
				"auto_start": bool(raw.get("auto_start")),
				"model_source": _optional_text(raw.get("model_source")),
				"model_name": _optional_text(raw.get("model_name")),
				"linked_space_id": _optional_text(raw.get("linked_space_id")),
				"linked_space_title": _optional_text(raw.get("linked_space_title")),
				"linked_workflow_name": _optional_text(raw.get("linked_workflow_name")),
				"toolkit_names": _string_list(raw.get("toolkit_names")),
				"skill_names": _string_list(raw.get("skill_names")),
				"safety": {
					"proactive_delivery_mode": _optional_text(raw.get("proactive_delivery_mode")) or "auto",
					"tool_execution_mode": _optional_text(raw.get("tool_execution_mode")) or "auto",
				},
				"channel_ids": [],
				"routing_rules": [],
				"proactive_tasks": [],
			}
		elif node_type == "channel_runtime_config":
			channel_id = _optional_text(raw.get("channel_id")) or _generated_id("ch")
			if channel_id in seen_channel_ids:
				raise ValueError(f"Channel id '{channel_id}' appears more than once in the workflow.")
			seen_channel_ids.add(channel_id)
			channel_nodes[index] = {
				"id": channel_id,
				"name": _optional_text(raw.get("name")) or _node_label(raw, "Channel") or channel_id,
				"channel_type": _optional_text(raw.get("channel_type")) or "",
				"enabled": bool(raw.get("enabled", True)),
				"auto_start": bool(raw.get("auto_start")),
				"session_id": _optional_text(raw.get("session_id")),
				"allowed_users": _string_list(raw.get("allowed_users")),
				"owner": _optional_text(raw.get("owner")),
			}
		elif node_type == "assistant_route_runtime_config":
			route_id = _optional_text(raw.get("route_id")) or _generated_id("route")
			if route_id in seen_route_ids:
				raise ValueError(f"Route id '{route_id}' appears more than once in the workflow.")
			seen_route_ids.add(route_id)
			route_nodes[index] = {
				"id": route_id,
				"name": _optional_text(raw.get("name")) or _node_label(raw, "Route"),
				"keywords": _string_list(raw.get("keywords")),
				"target_deployment_id": _optional_text(raw.get("target_deployment_id")),
				"enabled": bool(raw.get("enabled", True)),
			}
		elif node_type == "assistant_proactive_runtime_config":
			task_id = _optional_text(raw.get("task_id")) or _generated_id("proactive")
			if task_id in seen_task_ids:
				raise ValueError(f"Proactive task id '{task_id}' appears more than once in the workflow.")
			seen_task_ids.add(task_id)
			trigger = raw.get("trigger")
			if trigger is not None and not isinstance(trigger, dict):
				raise ValueError(f"Proactive task '{task_id}' has a non-dict trigger payload.")
			task_nodes[index] = {
				"id": task_id,
				"name": _optional_text(raw.get("name")) or _node_label(raw, "Proactive Task"),
				"prompt": _optional_text(raw.get("prompt")) or "",
				"interval_sec": max(0, int(raw.get("interval_sec") or 0)),
				"trigger_kind": _optional_text(raw.get("trigger_kind")) or "timer",
				"trigger": dict(trigger or {}) or None,
				"channel_id": _optional_text(raw.get("channel_id")),
				"recipient_id": _optional_text(raw.get("recipient_id")),
				"enabled": bool(raw.get("enabled", True)),
				"send_response": bool(raw.get("send_response", True)),
			}
		elif node_type == "event_listener_flow":
			listener_nodes[index] = {
				"id": _optional_text(raw.get("id")) or f"listener_{index}",
				"mode": _optional_text(raw.get("mode")) or "any",
			}
		elif node_type in _PROACTIVE_SOURCE_TYPES:
			source_nodes[index] = dict(raw)
		elif node_type == "assistant_approval_runtime_config":
			approval_nodes[index] = {"id": _optional_text(raw.get("approval_id")) or _generated_id("approval")}

	if not deployment_nodes and not channel_nodes:
		raise ValueError("The workflow does not contain any assistant deployment network nodes.")

	channel_bindings: Dict[int, int] = {}
	route_sources: Dict[int, int] = {}
	route_targets: Dict[int, int] = {}
	task_bindings: Dict[int, int] = {}
	task_listeners: Dict[int, int] = {}
	listener_sources: Dict[int, List[int]] = {}
	ignored_approvals = 0

	for edge in edges:
		if not isinstance(edge, dict):
			continue
		source = edge.get("source")
		target = edge.get("target")
		if not isinstance(source, int) or not isinstance(target, int):
			continue
		if source < 0 or target < 0 or source >= len(nodes) or target >= len(nodes):
			warnings.append("Ignored an assistant network edge that referenced a missing node.")
			continue
		target_slot = str(edge.get("target_slot") or "")
		source_type = str((nodes[source] or {}).get("type") or "")
		target_type = str((nodes[target] or {}).get("type") or "")
		if source_type == "channel_runtime_config" and target_type == "assistant_deployment_runtime_config" and target_slot.startswith("bound_channels."):
			existing = channel_bindings.get(source)
			if existing is not None and existing != target:
				raise ValueError("A channel cannot be bound to more than one deployment in the assistant network workflow.")
			channel_bindings[source] = target
		elif source_type == "assistant_route_runtime_config" and target_type == "assistant_deployment_runtime_config":
			if target_slot.startswith("outgoing_routes."):
				existing = route_sources.get(source)
				if existing is not None and existing != target:
					raise ValueError("A route cannot originate from more than one deployment in the assistant network workflow.")
				route_sources[source] = target
			elif target_slot.startswith("incoming_routes."):
				existing = route_targets.get(source)
				if existing is not None and existing != target:
					raise ValueError("A route cannot target more than one deployment in the assistant network workflow.")
				route_targets[source] = target
		elif source_type == "assistant_proactive_runtime_config" and target_type == "assistant_deployment_runtime_config" and target_slot.startswith("proactive_tasks."):
			existing = task_bindings.get(source)
			if existing is not None and existing != target:
				raise ValueError("A proactive task cannot be attached to more than one deployment in the assistant network workflow.")
			task_bindings[source] = target
		elif source_type in _PROACTIVE_SOURCE_TYPES and target_type == "event_listener_flow" and target_slot.startswith("sources."):
			listener_sources.setdefault(target, []).append(source)
		elif source_type == "event_listener_flow" and target_type == "assistant_proactive_runtime_config" and target_slot in {"trigger_event", "trigger_source_id"}:
			existing = task_listeners.get(target)
			if existing is not None and existing != source:
				raise ValueError("A proactive task cannot be connected to more than one event listener in the assistant network workflow.")
			task_listeners[target] = source
		elif source_type == "assistant_approval_runtime_config" and target_type == "assistant_deployment_runtime_config" and target_slot.startswith("pending_approvals."):
			ignored_approvals += 1

	for channel_index, deployment_index in channel_bindings.items():
		deployment_nodes[deployment_index]["channel_ids"].append(channel_nodes[channel_index]["id"])

	for route_index, route in route_nodes.items():
		source_index = route_sources.get(route_index)
		if source_index is None:
			warnings.append(f"Ignored route '{route['name'] or route['id']}' because it is not connected to an outgoing deployment slot.")
			continue
		target_edge_id = None
		if route_index in route_targets:
			target_edge_id = deployment_nodes[route_targets[route_index]]["id"]
		target_field_id = route.get("target_deployment_id")
		if target_edge_id and target_field_id and target_edge_id != target_field_id:
			warnings.append(
				f"Route '{route['name'] or route['id']}' used its incoming deployment edge as the target instead of the inline target_deployment_id."
			)
		target_deployment_id = target_edge_id or target_field_id
		if not target_deployment_id:
			raise ValueError(f"Route '{route['name'] or route['id']}' is missing its target deployment.")
		deployment_nodes[source_index]["routing_rules"].append(
			{
				"id": route["id"],
				"name": route["name"],
				"keywords": list(route["keywords"] or []),
				"target_deployment_id": target_deployment_id,
				"enabled": bool(route.get("enabled", True)),
			}
		)

	for task_index, task in task_nodes.items():
		deployment_index = task_bindings.get(task_index)
		if deployment_index is None:
			warnings.append(f"Ignored proactive task '{task['name'] or task['id']}' because it is not connected to a deployment.")
			continue
		listener_index = task_listeners.get(task_index)
		if listener_index is not None:
			source_indexes = [idx for idx in listener_sources.get(listener_index, []) if idx in source_nodes]
			if len(source_indexes) > 1:
				warnings.append(
					f"Proactive task '{task['name'] or task['id']}' is connected to multiple trigger sources; using the first one."
				)
			if source_indexes:
				trigger_kind, trigger_payload, derived_interval = _trigger_from_source_node(source_nodes[source_indexes[0]])
				if task.get("trigger_kind") and str(task.get("trigger_kind")) != trigger_kind:
					warnings.append(
						f"Proactive task '{task['name'] or task['id']}' used its connected source node instead of the inline trigger_kind."
					)
				task["trigger_kind"] = trigger_kind
				task["trigger"] = trigger_payload
				task["interval_sec"] = derived_interval
			else:
				warnings.append(
					f"Proactive task '{task['name'] or task['id']}' is connected to an event listener with no source nodes; keeping inline trigger settings."
				)
		deployment_nodes[deployment_index]["proactive_tasks"].append(dict(task))

	if ignored_approvals or approval_nodes:
		warnings.append("Pending approval nodes were ignored during apply because they represent transient runtime state.")

	return {
		"workflow_name": str(((workflow.get("options") or {}).get("name") or "Assistant Deployment Network")).strip() or "Assistant Deployment Network",
		"deployments": list(deployment_nodes.values()),
		"channels": list(channel_nodes.values()),
		"warnings": warnings,
	}
