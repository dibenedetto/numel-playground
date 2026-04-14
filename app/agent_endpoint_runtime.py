from __future__ import annotations

import json
import uuid

from typing import Any, Dict, List, Optional

import httpx

from schema import AgentEndpointConfig


_DEFAULT_A2A_CARD_PATH = "/.well-known/agent-card.json"
_SUPPORTED_ENDPOINT_KINDS = {"deployment", "workflow_agent", "a2a_remote", "custom_remote"}
_DEFAULT_ALLOWED_MODES = {
	"deployment": ["consult", "delegate", "notify"],
	"workflow_agent": ["consult", "delegate", "notify"],
	"a2a_remote": ["consult", "delegate", "notify"],
	"custom_remote": ["consult", "delegate", "notify"],
}


def _coerce_json_object(value: Any) -> Dict[str, Any]:
	if value is None:
		return {}
	if isinstance(value, dict):
		return dict(value)
	if isinstance(value, str):
		text = value.strip()
		if not text:
			return {}
		loaded = json.loads(text)
		if isinstance(loaded, dict):
			return dict(loaded)
	raise ValueError("Expected a JSON object")


def _coerce_metadata(value: Any) -> Optional[Dict[str, Any]]:
	if value is None:
		return None
	if isinstance(value, dict):
		return dict(value)
	if isinstance(value, str):
		text = value.strip()
		if not text:
			return None
		loaded = json.loads(text)
		if isinstance(loaded, dict):
			return dict(loaded)
	raise ValueError("metadata must be a dict or JSON object string")


def normalize_agent_endpoint_config(
	*,
	endpoint: Any = None,
	kind: str = "deployment",
	target: str = "",
	name: str = "",
	description: str = "",
	discovery_url: str = "",
	auth: str = "inherit",
	timeout_sec: int = 60,
	allowed_modes: Optional[List[str]] = None,
	metadata: Any = None,
) -> AgentEndpointConfig:
	if isinstance(endpoint, AgentEndpointConfig):
		config = endpoint.model_copy(deep=True)
	elif endpoint is not None:
		payload = _coerce_json_object(endpoint)
		config = AgentEndpointConfig(**payload)
	else:
		config = AgentEndpointConfig(
			kind=kind or "deployment",
			target=target or "",
			name=name or "",
			description=description or None,
			discovery_url=discovery_url or None,
			auth=auth or "inherit",
			timeout_sec=max(1, int(timeout_sec or 60)),
			allowed_modes=list(allowed_modes) if allowed_modes else None,
			metadata=_coerce_metadata(metadata),
		)

	config.kind = str(config.kind or "deployment").strip().lower() or "deployment"
	if config.kind not in _SUPPORTED_ENDPOINT_KINDS:
		raise ValueError(f"Unsupported agent endpoint kind: {config.kind}")
	config.target = str(config.target or "").strip()
	config.name = str(config.name or "").strip()
	config.description = str(config.description or "").strip() or None
	config.discovery_url = str(config.discovery_url or "").strip() or None
	config.auth = str(config.auth or "inherit").strip().lower() or "inherit"
	config.timeout_sec = max(1, int(config.timeout_sec or 60))
	config.metadata = _coerce_metadata(config.metadata)
	if config.allowed_modes:
		config.allowed_modes = [str(mode).strip().lower() for mode in config.allowed_modes if str(mode).strip()]
	else:
		config.allowed_modes = list(_DEFAULT_ALLOWED_MODES.get(config.kind) or ["consult"])
	return config


def serialize_agent_endpoint_config(config: AgentEndpointConfig) -> Dict[str, Any]:
	return config.model_dump()


def list_local_agent_endpoints(
	deployment_mgr,
	*,
	user_id: Optional[str] = None,
	is_admin: bool = False,
	include_disabled: bool = False,
) -> List[Dict[str, Any]]:
	if deployment_mgr is None:
		return []
	rows = deployment_mgr.list(user_id=user_id, is_admin=is_admin)
	result: List[Dict[str, Any]] = []
	for row in rows:
		if not include_disabled and not bool(row.get("enabled")):
			continue
		result.append(
			{
				"id": f"deployment:{row.get('id')}",
				"kind": "deployment",
				"target": row.get("id"),
				"name": row.get("name") or row.get("id"),
				"description": row.get("description") or "",
				"profile": row.get("profile") or "general",
				"enabled": bool(row.get("enabled")),
				"status": row.get("status") or "unknown",
				"channel_ids": list(row.get("channel_ids") or []),
				"toolkit_names": list(row.get("toolkit_names") or []),
				"skill_names": list(row.get("skill_names") or []),
				"allowed_modes": list(_DEFAULT_ALLOWED_MODES["deployment"]),
			}
		)
	return result


async def describe_agent_endpoint(
	config: AgentEndpointConfig,
	*,
	deployment_mgr=None,
) -> Dict[str, Any]:
	if config.kind == "deployment":
		if deployment_mgr is None:
			raise ValueError("Assistant deployment manager is not available")
		row = deployment_mgr.get(config.target)
		if row is None:
			raise ValueError(f"Deployment '{config.target}' not found")
		return {
			"endpoint": serialize_agent_endpoint_config(config),
			"resolved": {
				"id": row.get("id"),
				"name": row.get("name") or row.get("id"),
				"description": row.get("description") or "",
				"profile": row.get("profile") or "general",
				"enabled": bool(row.get("enabled")),
				"status": row.get("status") or "unknown",
				"channel_ids": list(row.get("channel_ids") or []),
				"toolkit_names": list(row.get("toolkit_names") or []),
				"skill_names": list(row.get("skill_names") or []),
				"linked_space_title": row.get("linked_space_title"),
				"linked_workflow_name": row.get("linked_workflow_name"),
				"allowed_modes": list(config.allowed_modes or _DEFAULT_ALLOWED_MODES["deployment"]),
			},
		}
	if config.kind == "a2a_remote":
		card = await discover_a2a_agent_card(config)
		interface_url = resolve_a2a_interface_url(card.get("card") or {}, fallback_target=config.target)
		return {
			"endpoint": serialize_agent_endpoint_config(config),
			"resolved": {
				"name": card.get("name") or config.name or config.target,
				"description": card.get("description") or config.description or "",
				"protocol": "a2a",
				"card_url": card.get("card_url"),
				"service_url": interface_url,
				"capabilities": dict(card.get("capabilities") or {}),
				"default_input_modes": list(card.get("default_input_modes") or []),
				"default_output_modes": list(card.get("default_output_modes") or []),
				"skills": list(card.get("skills") or []),
				"allowed_modes": list(config.allowed_modes or _DEFAULT_ALLOWED_MODES["a2a_remote"]),
			},
		}
	return {
		"endpoint": serialize_agent_endpoint_config(config),
		"resolved": {
			"name": config.name or config.target,
			"description": config.description or "",
			"allowed_modes": list(config.allowed_modes or _DEFAULT_ALLOWED_MODES.get(config.kind) or ["consult"]),
		},
	}


async def invoke_agent_endpoint(
	config: AgentEndpointConfig,
	*,
	mode: str,
	prompt: str,
	deployment_mgr=None,
	channel_pool=None,
	user_id: Optional[str] = None,
	sender_name: Optional[str] = None,
	auth_token: str = "",
	source_deployment_id: Optional[str] = None,
	session_id: Optional[str] = None,
) -> Dict[str, Any]:
	mode_value = str(mode or "consult").strip().lower() or "consult"
	if config.allowed_modes and mode_value not in set(config.allowed_modes):
		raise ValueError(f"Endpoint does not allow mode '{mode_value}'")

	try:
		if config.kind == "deployment":
			return await _invoke_local_deployment_endpoint(
				config,
				mode=mode_value,
				prompt=prompt,
				deployment_mgr=deployment_mgr,
				channel_pool=channel_pool,
				user_id=user_id,
				sender_name=sender_name,
				auth_token=auth_token,
				source_deployment_id=source_deployment_id,
				session_id=session_id,
			)
		if config.kind == "a2a_remote":
			result = await _invoke_a2a_remote_endpoint(
				config,
				mode=mode_value,
				prompt=prompt,
				source_deployment_id=source_deployment_id,
				session_id=session_id,
			)
			if source_deployment_id and deployment_mgr is not None:
				deployment_mgr.record_endpoint_interaction(
					source_deployment_id,
					mode=mode_value,
					endpoint_kind="a2a_remote",
					endpoint_target=config.target,
					endpoint_name=str(result.get("name") or config.name or config.target),
					status="error" if result.get("error") else "ok",
					preview=str(result.get("response") or ""),
					error=str(result.get("error") or "") or None,
					session_id=session_id,
					remote_task_id=str(result.get("task_id") or "") or None,
				)
			return result
		raise NotImplementedError(f"Agent endpoint kind '{config.kind}' is not implemented yet")
	except Exception as exc:
		if source_deployment_id and deployment_mgr is not None:
			deployment_mgr.record_endpoint_interaction(
				source_deployment_id,
				mode=mode_value,
				endpoint_kind=config.kind,
				endpoint_target=config.target,
				endpoint_name=config.name or config.target,
				status="error",
				preview=str(exc),
				error=str(exc),
				session_id=session_id,
			)
		raise


async def discover_a2a_agent_card(config: AgentEndpointConfig) -> Dict[str, Any]:
	card_candidates = _candidate_a2a_card_urls(config)
	last_error: Optional[str] = None
	headers = {
		"Accept": "application/json, application/a2a+json",
	}
	headers.update(_a2a_auth_headers(config))
	async with httpx.AsyncClient(timeout=max(1.0, float(config.timeout_sec or 60))) as client:
		for url in card_candidates:
			try:
				response = await client.get(url, headers=headers)
				response.raise_for_status()
				card = response.json()
				if not isinstance(card, dict):
					raise ValueError("A2A agent card response is not a JSON object")
				return _serialize_a2a_card(card, card_url=url)
			except Exception as exc:
				last_error = str(exc)
	if last_error:
		raise RuntimeError(f"Failed to fetch A2A agent card: {last_error}")
	raise RuntimeError("Failed to fetch A2A agent card")


def resolve_a2a_interface_url(card: Dict[str, Any], *, fallback_target: str = "") -> str:
	supported = card.get("supportedInterfaces")
	if isinstance(supported, list):
		for entry in supported:
			if not isinstance(entry, dict):
				continue
			binding = str(entry.get("protocolBinding") or "").strip().upper()
			url = str(entry.get("url") or "").strip()
			if binding in {"HTTP+JSON", "REST"} and url:
				return url.rstrip("/")
	for key in ("url", "endpoint", "baseUrl"):
		value = str(card.get(key) or "").strip()
		if value:
			return value.rstrip("/")
	return str(fallback_target or "").strip().rstrip("/")


def _candidate_a2a_card_urls(config: AgentEndpointConfig) -> List[str]:
	candidates: List[str] = []
	discovery_url = str(config.discovery_url or "").strip()
	if discovery_url:
		candidates.append(discovery_url.rstrip("/"))
	target = str(config.target or "").strip()
	if target:
		normalized = target.rstrip("/")
		if normalized.endswith(".json"):
			candidates.append(normalized)
		else:
			candidates.append(f"{normalized}{_DEFAULT_A2A_CARD_PATH}")
	if not candidates:
		raise ValueError("A2A endpoint requires target or discovery_url")
	seen = set()
	unique: List[str] = []
	for item in candidates:
		if item in seen:
			continue
		seen.add(item)
		unique.append(item)
	return unique


def _serialize_a2a_card(card: Dict[str, Any], *, card_url: str) -> Dict[str, Any]:
	skills = []
	for item in card.get("skills") or []:
		if not isinstance(item, dict):
			continue
		skills.append(
			{
				"id": item.get("id"),
				"name": item.get("name"),
				"description": item.get("description"),
				"tags": list(item.get("tags") or []),
			}
		)
	return {
		"card_url": card_url,
		"card": card,
		"name": card.get("name"),
		"description": card.get("description"),
		"capabilities": card.get("capabilities") or {},
		"default_input_modes": list(card.get("defaultInputModes") or []),
		"default_output_modes": list(card.get("defaultOutputModes") or []),
		"skills": skills,
	}


def _a2a_auth_headers(config: AgentEndpointConfig) -> Dict[str, str]:
	metadata = dict(config.metadata or {})
	headers: Dict[str, str] = {}
	auth_mode = str(config.auth or "inherit").strip().lower()
	if auth_mode in {"bearer", "inherit"}:
		token = str(metadata.get("bearer_token") or metadata.get("token") or "").strip()
		if token:
			headers["Authorization"] = f"Bearer {token}"
	elif auth_mode == "api_key":
		api_key = str(metadata.get("api_key") or "").strip()
		header_name = str(metadata.get("api_key_header") or "X-API-Key").strip() or "X-API-Key"
		if api_key:
			headers[header_name] = api_key
	return headers


def _mode_instruction(mode: str) -> str:
	if mode == "delegate":
		return "Treat this as a delegated subtask from another assistant. Complete the subtask and return a concise, directly usable result."
	if mode == "notify":
		return "Treat this as a notification-oriented agent interaction. Acknowledge important points briefly and respond only if useful."
	return "Treat this as a consultation from another assistant. Return focused advice or analysis that the caller can use immediately."


async def _invoke_local_deployment_endpoint(
	config: AgentEndpointConfig,
	*,
	mode: str,
	prompt: str,
	deployment_mgr,
	channel_pool,
	user_id: Optional[str],
	sender_name: Optional[str],
	auth_token: str,
	source_deployment_id: Optional[str],
	session_id: Optional[str],
) -> Dict[str, Any]:
	if deployment_mgr is None:
		raise ValueError("Assistant deployment manager is not available")
	if channel_pool is None:
		raise ValueError("Channel agent pool is not available")
	target = deployment_mgr.get_config(config.target)
	if target is None:
		raise ValueError(f"Deployment '{config.target}' not found")
	if source_deployment_id and source_deployment_id == target.id:
		raise ValueError("Source deployment cannot call itself as an agent endpoint")
	if not target.enabled:
		raise ValueError(f"Deployment '{target.name or target.id}' is not active")

	source_deployment = deployment_mgr.get_config(source_deployment_id) if source_deployment_id else None
	call_session_id = session_id or f"endpoint_{mode}_{target.id}_{uuid.uuid4().hex[:10]}"
	extra_instructions = [
		(
			"[Agent Endpoint Call]\n"
			f"Mode: {mode}\n"
			f"Source deployment: {(source_deployment.name if source_deployment else source_deployment_id) or 'external caller'}\n"
			f"Target deployment: {target.name}\n"
			f"{_mode_instruction(mode)}"
		)
	]

	result = await channel_pool.chat(
		message=prompt,
		session_id=call_session_id,
		toolkits=list(target.toolkit_names) if target.toolkit_names else None,
		sender_name=sender_name or (source_deployment.name if source_deployment else "Agent Endpoint"),
		user_id=user_id or f"endpoint:{source_deployment_id or target.id}",
		auth_token=auth_token or None,
		extra_instructions=extra_instructions,
		model_source=target.model_source,
		model_name=target.model_name,
		skill_names=list(target.skill_names),
		deployment_id=target.id,
		tool_confirmation_mode=target.safety.tool_execution_mode,
		assistant_name=target.name,
		assistant_description=target.description or None,
	)

	response_text = str(result.get("response", "") or "")
	error_text = str(result.get("error", "") or "").strip() or None
	status = "error" if error_text else ("pending" if result.get("pending_tool_approval") else "ok")
	if source_deployment_id:
		deployment_mgr.record_endpoint_interaction(
			source_deployment_id,
			mode=mode,
			endpoint_kind="deployment",
			endpoint_target=target.id,
			endpoint_name=target.name,
			status=status,
			preview=response_text or (error_text or ""),
			error=error_text,
			session_id=call_session_id,
		)

	return {
		"mode": mode,
		"kind": "deployment",
		"target": target.id,
		"name": target.name,
		"session_id": call_session_id,
		"response": response_text,
		"tool_calls": list(result.get("tool_calls") or []),
		"paused": bool(result.get("paused")),
		"pending_tool_approval": result.get("pending_tool_approval"),
		"error": error_text,
	}


async def _invoke_a2a_remote_endpoint(
	config: AgentEndpointConfig,
	*,
	mode: str,
	prompt: str,
	source_deployment_id: Optional[str],
	session_id: Optional[str],
) -> Dict[str, Any]:
	card_info = await discover_a2a_agent_card(config)
	service_url = resolve_a2a_interface_url(card_info.get("card") or {}, fallback_target=config.target)
	if not service_url:
		raise ValueError("A2A endpoint did not advertise an HTTP+JSON interface URL")

	post_url = service_url if service_url.endswith("/message:send") else f"{service_url.rstrip('/')}/message:send"
	request_body: Dict[str, Any] = {
		"message": {
			"role": "ROLE_USER",
			"parts": [{"text": prompt}],
			"messageId": session_id or f"msg_{uuid.uuid4().hex[:10]}",
		}
	}
	if source_deployment_id:
		request_body["metadata"] = {"source_deployment_id": source_deployment_id, "mode": mode}

	headers = {
		"Accept": "application/a2a+json, application/json",
		"Content-Type": "application/a2a+json",
		"A2A-Version": "1.0",
	}
	headers.update(_a2a_auth_headers(config))

	async with httpx.AsyncClient(timeout=max(1.0, float(config.timeout_sec or 60))) as client:
		response = await client.post(post_url, json=request_body, headers=headers)
		response.raise_for_status()
		payload = response.json()
		if not isinstance(payload, dict):
			raise ValueError("A2A response is not a JSON object")

	response_text = _extract_a2a_text(payload)
	task = payload.get("task") if isinstance(payload.get("task"), dict) else {}
	status_obj = task.get("status") if isinstance(task.get("status"), dict) else {}
	status = str(status_obj.get("state") or payload.get("state") or "ok")
	return {
		"mode": mode,
		"kind": "a2a_remote",
		"target": config.target,
		"name": card_info.get("name") or config.name or config.target,
		"response": response_text,
		"task_id": task.get("id"),
		"context_id": task.get("contextId"),
		"status": status,
		"service_url": service_url,
		"card_url": card_info.get("card_url"),
		"raw": payload,
	}


def _extract_a2a_text(payload: Dict[str, Any]) -> str:
	parts: List[str] = []

	def _add_from_parts(items: Any) -> None:
		if not isinstance(items, list):
			return
		for part in items:
			if not isinstance(part, dict):
				continue
			text = part.get("text")
			if isinstance(text, str) and text.strip():
				parts.append(text.strip())
			data = part.get("data")
			if data is not None:
				parts.append(json.dumps(data, ensure_ascii=False))

	message = payload.get("message")
	if isinstance(message, dict):
		_add_from_parts(message.get("parts"))

	task = payload.get("task")
	if isinstance(task, dict):
		status = task.get("status")
		if isinstance(status, dict):
			status_message = status.get("message")
			if isinstance(status_message, dict):
				_add_from_parts(status_message.get("parts"))
		for artifact in task.get("artifacts") or []:
			if isinstance(artifact, dict):
				_add_from_parts(artifact.get("parts"))

	status_update = payload.get("statusUpdate")
	if isinstance(status_update, dict):
		status = status_update.get("status")
		if isinstance(status, dict):
			status_message = status.get("message")
			if isinstance(status_message, dict):
				_add_from_parts(status_message.get("parts"))

	seen = set()
	ordered: List[str] = []
	for item in parts:
		if item in seen:
			continue
		seen.add(item)
		ordered.append(item)
	return "\n".join(ordered).strip()
