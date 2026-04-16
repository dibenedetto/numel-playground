from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, Optional

from runtime_toolkit_context import register_runtime_toolkit_context


RUNTIME_BOUND_TOOLKITS = {
	"console_toolkit",
	"channel_toolkit",
	"workspace_toolkit",
	"agent_endpoint_toolkit",
}


def build_runtime_toolkit_args(
	toolkit_name: str,
	*,
	base_url: str,
	internal_token: str,
	user_id: Optional[str],
	auth_token: str = "",
	local_app = None,
	channel_registry = None,
	deployment_id: Optional[str] = None,
	runtime_context_id: Optional[str] = None,
) -> Dict[str, Any]:
	"""Return live Numel constructor args for runtime-bound toolkits."""
	args: Dict[str, Any] = {}
	if not runtime_context_id and (local_app is not None or channel_registry is not None):
		runtime_context_id = register_runtime_toolkit_context(
			local_app=local_app,
			channel_registry=channel_registry,
		)
	if toolkit_name in {"console_toolkit", "workspace_toolkit", "agent_endpoint_toolkit"}:
		args["base_url"] = base_url
		args["auth_token"] = auth_token or ""
		args["internal_token"] = internal_token
		args["user_id"] = user_id
		if runtime_context_id:
			args["runtime_context_id"] = runtime_context_id
	if toolkit_name == "channel_toolkit":
		if runtime_context_id:
			args["runtime_context_id"] = runtime_context_id
	if toolkit_name == "agent_endpoint_toolkit" and deployment_id:
		args["deployment_id"] = deployment_id
	return args


def is_runtime_bound_toolkit_node(node: Dict[str, Any]) -> bool:
	if not isinstance(node, dict) or node.get("type") != "toolkit_config":
		return False
	binding = node.get("runtime_binding")
	if isinstance(binding, dict) and str(binding.get("binding_kind") or "").strip() == "numel_runtime":
		return True
	toolkit_name = str(node.get("name") or "").strip()
	return toolkit_name in RUNTIME_BOUND_TOOLKITS


def bind_runtime_toolkits_to_workflow(
	workflow: Dict[str, Any],
	*,
	base_url: str,
	internal_token: str,
	user_id: Optional[str],
	auth_token: str = "",
	local_app = None,
	channel_registry = None,
	deployment_id: Optional[str] = None,
) -> Dict[str, Any]:
	"""Inject live runtime args into runtime-bound toolkit_config nodes."""
	payload = deepcopy(workflow)
	runtime_context_id = register_runtime_toolkit_context(
		local_app=local_app,
		channel_registry=channel_registry,
	)
	for node in list(payload.get("nodes") or []):
		if not is_runtime_bound_toolkit_node(node):
			continue
		toolkit_name = str(node.get("name") or "").strip()
		args = dict(node.get("args") or {})
		args.update(
			build_runtime_toolkit_args(
				toolkit_name,
				base_url=base_url,
				internal_token=internal_token,
				user_id=user_id,
				auth_token=auth_token,
				local_app=local_app,
				channel_registry=channel_registry,
				deployment_id=deployment_id,
				runtime_context_id=runtime_context_id,
			)
		)
		node["args"] = args or None
	return payload
