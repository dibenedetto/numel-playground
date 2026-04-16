# agent_endpoint_toolkit.py

from __future__ import annotations

from typing import Any, Dict, List, Optional

from runtime_toolkit_context import get_runtime_toolkit_context
from agent_endpoint_runtime import (
	describe_agent_endpoint,
	invoke_agent_endpoint,
	list_local_agent_endpoints,
	normalize_agent_endpoint_config,
)


class AgentEndpointToolkit:
	"""Toolkit for agent-to-agent communication through Numel Agent Endpoints.

	This toolkit exposes a backend-neutral surface for assistants that need to
	consult, delegate to, or notify other agents. It uses the shared
	AgentEndpointConfig abstraction internally, so the same conceptual endpoint can
	point either to a local Numel deployment or to a remote A2A server.

	Current behavior:
	- local `deployment` endpoints are fully supported
	- remote `a2a_remote` endpoints support discovery and direct HTTP+JSON calls
	- the caller can pass a full endpoint config as `endpoint_json`, or fill the
	  simple fields directly
	"""

	__toolkit__ = True

	def __init__(
		self,
		base_url: str = "http://localhost:11360",
		auth_token: str = "",
		internal_token: str = "",
		user_id: Optional[str] = None,
		local_app = None,
		deployment_id: Optional[str] = None,
		runtime_context_id: str = "",
	):
		if local_app is None and runtime_context_id:
			local_app = get_runtime_toolkit_context(runtime_context_id).get("local_app")
		self._base_url = base_url
		self._auth_token = auth_token or ""
		self._internal_token = internal_token or ""
		self._user_id = user_id or ""
		self._local_app = local_app
		self._deployment_id = deployment_id or None

	def _deployment_mgr(self):
		app_state = getattr(self._local_app, "state", None)
		return getattr(app_state, "assistant_deployment_mgr", None)

	def _channel_pool(self):
		app_state = getattr(self._local_app, "state", None)
		console_mgr = getattr(app_state, "console_mgr", None)
		return getattr(console_mgr, "_channel_pool", None)

	def _resolve_endpoint(
		self,
		*,
		endpoint_json: str = "",
		kind: str = "deployment",
		target: str = "",
		name: str = "",
		description: str = "",
		discovery_url: str = "",
		auth: str = "inherit",
		timeout_sec: int = 60,
		allowed_modes: str = "",
		metadata_json: str = "",
	):
		modes = [item.strip() for item in str(allowed_modes or "").split(",") if item.strip()]
		return normalize_agent_endpoint_config(
			endpoint=endpoint_json or None,
			kind=kind,
			target=target,
			name=name,
			description=description,
			discovery_url=discovery_url,
			auth=auth,
			timeout_sec=timeout_sec,
			allowed_modes=modes or None,
			metadata=metadata_json or None,
		)

	def list_available_endpoints(self, include_disabled: bool = False) -> List[Dict[str, Any]]:
		"""List local Numel deployments that can be addressed as agent endpoints.

		This is the discovery entry point for local endpoints. Each returned row is a
		summary shaped like an Agent Endpoint, including the local deployment id in
		`target`.
		"""
		return list_local_agent_endpoints(
			self._deployment_mgr(),
			user_id=self._user_id or None,
			include_disabled=include_disabled,
		)

	async def describe_endpoint(
		self,
		endpoint_json: str = "",
		kind: str = "deployment",
		target: str = "",
		name: str = "",
		description: str = "",
		discovery_url: str = "",
		auth: str = "inherit",
		timeout_sec: int = 60,
		allowed_modes: str = "",
		metadata_json: str = "",
	) -> Dict[str, Any]:
		"""Describe one endpoint using the AgentEndpointConfig abstraction.

		Pass either:
		- endpoint_json: full JSON object shaped like AgentEndpointConfig
		or:
		- kind/target/discovery_url/auth/... fields directly

		Useful for checking what a deployment endpoint or A2A endpoint actually
		resolves to before calling it.
		"""
		config = self._resolve_endpoint(
			endpoint_json=endpoint_json,
			kind=kind,
			target=target,
			name=name,
			description=description,
			discovery_url=discovery_url,
			auth=auth,
			timeout_sec=timeout_sec,
			allowed_modes=allowed_modes,
			metadata_json=metadata_json,
		)
		return await describe_agent_endpoint(
			config,
			deployment_mgr=self._deployment_mgr(),
		)

	async def consult_endpoint(
		self,
		prompt: str,
		endpoint_json: str = "",
		kind: str = "deployment",
		target: str = "",
		name: str = "",
		description: str = "",
		discovery_url: str = "",
		auth: str = "inherit",
		timeout_sec: int = 60,
		allowed_modes: str = "",
		metadata_json: str = "",
		session_id: str = "",
		source_deployment_id: str = "",
	) -> Dict[str, Any]:
		"""Consult another agent endpoint and get advice or analysis back.

		Use this when the current assistant wants help from another assistant but
		intends to keep responsibility for the final answer.
		"""
		config = self._resolve_endpoint(
			endpoint_json=endpoint_json,
			kind=kind,
			target=target,
			name=name,
			description=description,
			discovery_url=discovery_url,
			auth=auth,
			timeout_sec=timeout_sec,
			allowed_modes=allowed_modes,
			metadata_json=metadata_json,
		)
		return await invoke_agent_endpoint(
			config,
			mode="consult",
			prompt=prompt,
			deployment_mgr=self._deployment_mgr(),
			channel_pool=self._channel_pool(),
			user_id=self._user_id or None,
			auth_token=self._auth_token,
			source_deployment_id=source_deployment_id or self._deployment_id,
			session_id=session_id or None,
		)

	async def delegate_to_endpoint(
		self,
		task: str,
		endpoint_json: str = "",
		kind: str = "deployment",
		target: str = "",
		name: str = "",
		description: str = "",
		discovery_url: str = "",
		auth: str = "inherit",
		timeout_sec: int = 60,
		allowed_modes: str = "",
		metadata_json: str = "",
		session_id: str = "",
		source_deployment_id: str = "",
	) -> Dict[str, Any]:
		"""Delegate a bounded subtask to another endpoint and return its result."""
		config = self._resolve_endpoint(
			endpoint_json=endpoint_json,
			kind=kind,
			target=target,
			name=name,
			description=description,
			discovery_url=discovery_url,
			auth=auth,
			timeout_sec=timeout_sec,
			allowed_modes=allowed_modes,
			metadata_json=metadata_json,
		)
		return await invoke_agent_endpoint(
			config,
			mode="delegate",
			prompt=task,
			deployment_mgr=self._deployment_mgr(),
			channel_pool=self._channel_pool(),
			user_id=self._user_id or None,
			auth_token=self._auth_token,
			source_deployment_id=source_deployment_id or self._deployment_id,
			session_id=session_id or None,
		)

	async def notify_endpoint(
		self,
		message: str,
		endpoint_json: str = "",
		kind: str = "deployment",
		target: str = "",
		name: str = "",
		description: str = "",
		discovery_url: str = "",
		auth: str = "inherit",
		timeout_sec: int = 60,
		allowed_modes: str = "",
		metadata_json: str = "",
		session_id: str = "",
		source_deployment_id: str = "",
	) -> Dict[str, Any]:
		"""Notify another endpoint without treating it as the user-facing responder."""
		config = self._resolve_endpoint(
			endpoint_json=endpoint_json,
			kind=kind,
			target=target,
			name=name,
			description=description,
			discovery_url=discovery_url,
			auth=auth,
			timeout_sec=timeout_sec,
			allowed_modes=allowed_modes,
			metadata_json=metadata_json,
		)
		return await invoke_agent_endpoint(
			config,
			mode="notify",
			prompt=message,
			deployment_mgr=self._deployment_mgr(),
			channel_pool=self._channel_pool(),
			user_id=self._user_id or None,
			auth_token=self._auth_token,
			source_deployment_id=source_deployment_id or self._deployment_id,
			session_id=session_id or None,
		)
