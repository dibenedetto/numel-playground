from __future__ import annotations

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
	channel_indexes: Dict[str, int] = {}

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
				status=str(deployment.get("status") or "stopped"),
				enabled=bool(deployment.get("enabled")),
				model_source=str(deployment.get("model_source") or "") or None,
				model_name=str(deployment.get("model_name") or "") or None,
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
				owner=str(channel.get("created_by") or "") or None,
			)
		)
		channel_indexes[channel_id] = node_index
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
			node_index = len(nodes)
			nodes.append(
				_node_payload(
					"assistant_proactive_runtime_config",
					label=str(task.get("name") or "Proactive Task"),
					pos=(source_x, source_y + 170 + task_index * 150),
					task_id=str(task.get("id") or f"task_{deployment_id}_{task_index}"),
					name=str(task.get("name") or ""),
					prompt=str(task.get("prompt") or "") or None,
					interval_sec=int(task.get("interval_sec") or 900),
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
