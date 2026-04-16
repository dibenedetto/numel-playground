from __future__ import annotations

import copy
import json

from pathlib import Path
from typing import Any, Dict, List, Optional

from console_workflow import build_console_workflow_export
from runtime_settings import get_runtime_settings
from runtime_toolkit_bindings import bind_runtime_toolkits_to_workflow
from runtime_workflow import run_workflow_in_process
from schema import DEFAULT_BACKEND_NAME


def _stringify_content(value: Any) -> str:
	if value is None:
		return ""
	if isinstance(value, str):
		return value
	if isinstance(value, list):
		parts = [_stringify_content(item) for item in value]
		return "\n".join(part for part in parts if part)
	if isinstance(value, dict):
		for key in ("content", "text", "message", "value", "response"):
			if key in value:
				return _stringify_content(value.get(key))
		return json.dumps(value, default=str)
	return str(value)


def _get_node_output(node_outputs: Dict[Any, Any], index: int) -> Dict[str, Any]:
	if index in node_outputs and isinstance(node_outputs[index], dict):
		return dict(node_outputs[index])
	index_key = str(index)
	if index_key in node_outputs and isinstance(node_outputs[index_key], dict):
		return dict(node_outputs[index_key])
	return {}


def build_agent_turn_workflow(
	*,
	workflow_name: str,
	request: Any,
	model_source: str,
	model_name: str,
	toolkit_names: Optional[List[str]] = None,
	toolkit_args: Optional[Dict[str, Dict[str, Any]]] = None,
	skill_names: Optional[List[str]] = None,
	options_config: Optional[Dict[str, Any]] = None,
	extra_instructions: Optional[List[str]] = None,
	sender_name: Optional[str] = None,
	assistant_name: Optional[str] = None,
	assistant_description: Optional[str] = None,
	backend_name: str = DEFAULT_BACKEND_NAME,
) -> Dict[str, Any]:
	"""Build a transient single-turn workflow around an agent_flow node."""
	options = dict(options_config or {})
	if assistant_name is not None:
		options["name"] = assistant_name
	if assistant_description is not None:
		options["description"] = assistant_description

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
	workflow = copy.deepcopy(exported["workflow"])
	nodes = list(workflow.get("nodes") or [])
	agent_node_index: Optional[int] = None

	for index, node in enumerate(nodes):
		if not isinstance(node, dict):
			continue
		node_type = str(node.get("type") or "")
		if node_type == "agent_options_config":
			instructions = list(node.get("instructions") or [])
			if sender_name:
				instructions.insert(0, f"You are chatting with {sender_name}.")
			if extra_instructions:
				instructions.extend(list(extra_instructions))
			node["instructions"] = instructions
		elif node_type == "agent_chat":
			agent_node_index = index
			node["type"] = "agent_flow"
			node.pop("system_prompt", None)
			node["request"] = request

	if agent_node_index is None:
		raise ValueError("Console workflow export did not contain an agent_chat node")

	options_payload = dict(workflow.get("options") or {})
	options_payload["name"] = workflow_name
	workflow["options"] = options_payload

	return {
		"workflow": workflow,
		"agent_node_index": agent_node_index,
		"runtime_bound_toolkits": list(exported.get("runtime_bound_toolkits") or []),
	}


async def run_workflow_backed_agent_turn(
	*,
	workflow_name: str,
	request: Any,
	model_source: str,
	model_name: str,
	toolkit_names: Optional[List[str]] = None,
	toolkit_args: Optional[Dict[str, Dict[str, Any]]] = None,
	skill_names: Optional[List[str]] = None,
	options_config: Optional[Dict[str, Any]] = None,
	extra_instructions: Optional[List[str]] = None,
	sender_name: Optional[str] = None,
	assistant_name: Optional[str] = None,
	assistant_description: Optional[str] = None,
	base_url: str,
	internal_token: str,
	user_id: Optional[str],
	auth_token: str = "",
	local_app = None,
	channel_registry = None,
	deployment_id: Optional[str] = None,
	backend_name: str = DEFAULT_BACKEND_NAME,
) -> Dict[str, Any]:
	"""Run a single agent turn through a transient Numel workflow."""
	built = build_agent_turn_workflow(
		workflow_name=workflow_name,
		request=request,
		model_source=model_source,
		model_name=model_name,
		toolkit_names=toolkit_names,
		toolkit_args=toolkit_args,
		skill_names=skill_names,
		options_config=options_config,
		extra_instructions=extra_instructions,
		sender_name=sender_name,
		assistant_name=assistant_name,
		assistant_description=assistant_description,
		backend_name=backend_name,
	)
	payload = bind_runtime_toolkits_to_workflow(
		built["workflow"],
		base_url=base_url,
		internal_token=internal_token,
		user_id=user_id,
		auth_token=auth_token,
		local_app=local_app,
		channel_registry=channel_registry,
		deployment_id=deployment_id,
	)
	storage_dir = Path(get_runtime_settings().memory_storage_dir) / "workflow_backed_runtime"
	storage_dir.mkdir(parents=True, exist_ok=True)

	result = await run_workflow_in_process(
		payload,
		workflow_name=workflow_name,
		storage_dir=str(storage_dir),
	)
	node_outputs = dict((result.get("results") or {}).get("node_outputs") or {})
	agent_output = _get_node_output(node_outputs, int(built["agent_node_index"]))
	response_envelope = dict(agent_output.get("response") or {})
	raw_response = response_envelope.get("response")
	text = ""
	if isinstance(raw_response, dict):
		text = _stringify_content(raw_response.get("content"))
	else:
		text = _stringify_content(raw_response)

	return {
		"response": text,
		"raw_response": raw_response,
		"agent_output": agent_output,
		"tool_calls": [],
		"engine_execution_id": result.get("engine_execution_id"),
		"workflow_name": result.get("workflow_name") or workflow_name,
		"status": result.get("status") or "completed",
		"runtime_bound_toolkits": list(built.get("runtime_bound_toolkits") or []),
		"workflow_backed": True,
	}
