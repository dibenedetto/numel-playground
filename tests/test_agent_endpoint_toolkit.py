from __future__ import annotations

import sys
import unittest
import uuid

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = PROJECT_ROOT / "app"
if str(APP_DIR) not in sys.path:
	sys.path.insert(0, str(APP_DIR))
if str(PROJECT_ROOT) not in sys.path:
	sys.path.insert(1, str(PROJECT_ROOT))


from agno.tools import Toolkit as AgnoToolkit

from assistant_deployments import AssistantDeploymentConfig, AssistantDeploymentManager
from backend_factory import build_backend_toolkit
from toolkit_runtime import load_numel_toolkit
from toolkits.agent_endpoint_toolkit import AgentEndpointToolkit


class _FakeChannelPool:
	def __init__(self):
		self.calls = []

	async def chat(self, message, session_id, **kwargs):
		self.calls.append(
			{
				"message": message,
				"session_id": session_id,
				**kwargs,
			}
		)
		return {
			"session_id": session_id,
			"response": "endpoint answer",
			"tool_calls": [],
		}


class _FakeResponse:
	def __init__(self, payload, status_code: int = 200):
		self._payload = payload
		self.status_code = status_code

	def json(self):
		return self._payload

	def raise_for_status(self):
		if self.status_code >= 400:
			raise RuntimeError(f"HTTP {self.status_code}")


class AgentEndpointToolkitTests(unittest.IsolatedAsyncioTestCase):
	def test_toolkit_loader_discovers_agent_endpoint_toolkit(self):
		record = load_numel_toolkit("toolkits.agent_endpoint_toolkit", {}, log_prefix="Test toolkit")
		self.assertIsNotNone(record)
		self.assertEqual(record["module_name"], "toolkits.agent_endpoint_toolkit")
		method_names = {tool.__name__ for tool in record["tools"]}
		self.assertIn("list_available_endpoints", method_names)
		self.assertIn("consult_endpoint", method_names)

	def test_agent_endpoint_toolkit_wraps_as_native_backend_toolkit(self):
		record = load_numel_toolkit("toolkits.agent_endpoint_toolkit", {}, log_prefix="Test toolkit")
		native_toolkit = build_backend_toolkit(record)
		self.assertIsInstance(native_toolkit, AgnoToolkit)
		self.assertIn("list_available_endpoints", native_toolkit.functions)
		self.assertIn("consult_endpoint", native_toolkit.async_functions)

	async def test_agent_endpoint_toolkit_lists_and_consults_local_deployments(self):
		test_dir = PROJECT_ROOT / "storage" / f"test-agent-endpoints-{uuid.uuid4().hex[:8]}"
		test_dir.mkdir(parents=True, exist_ok=True)
		self.addCleanup(lambda: test_dir.exists() and __import__("shutil").rmtree(test_dir, ignore_errors=True))

		manager = AssistantDeploymentManager(config_path=str(test_dir / "assistant_deployments.json"))
		manager.initialize(channel_registry=None, channel_pool=None)
		manager.add(
			AssistantDeploymentConfig(
				id="deploy_source",
				name="Source Assistant",
				description="Front door deployment",
				created_by="user_1",
				enabled=True,
			)
		)
		manager.add(
			AssistantDeploymentConfig(
				id="deploy_target",
				name="Target Specialist",
				description="Handles delegated endpoint calls",
				model_source="openai",
				model_name="gpt-4o-mini",
				toolkit_names=["file_toolkit"],
				skill_names=["triage"],
				created_by="user_1",
				enabled=True,
			)
		)
		manager.add(
			AssistantDeploymentConfig(
				id="deploy_disabled",
				name="Disabled Specialist",
				created_by="user_1",
				enabled=False,
			)
		)

		pool = _FakeChannelPool()
		app = SimpleNamespace(
			state=SimpleNamespace(
				assistant_deployment_mgr=manager,
				console_mgr=SimpleNamespace(_channel_pool=pool),
			)
		)
		toolkit = AgentEndpointToolkit(local_app=app, user_id="user_1", deployment_id="deploy_source")

		listed = toolkit.list_available_endpoints()
		self.assertEqual([row["target"] for row in listed], ["deploy_source", "deploy_target"])

		result = await toolkit.consult_endpoint(
			"Can you review this billing case?",
			kind="deployment",
			target="deploy_target",
		)

		self.assertEqual(result["response"], "endpoint answer")
		self.assertEqual(pool.calls[0]["assistant_name"], "Target Specialist")
		self.assertEqual(pool.calls[0]["model_source"], "openai")
		self.assertEqual(pool.calls[0]["model_name"], "gpt-4o-mini")
		self.assertEqual(pool.calls[0]["toolkits"], ["file_toolkit"])
		self.assertEqual(pool.calls[0]["skill_names"], ["triage"])
		self.assertEqual(pool.calls[0]["deployment_id"], "deploy_target")
		self.assertTrue(any("[Agent Endpoint Call]" in str(item) for item in pool.calls[0]["extra_instructions"]))

		source_data = manager.get("deploy_source")
		self.assertIsNotNone(source_data)
		self.assertEqual(source_data["runtime"]["endpoint_call_count"], 1)
		self.assertEqual(source_data["runtime"]["last_endpoint_target"], "deploy_target")
		self.assertTrue(any(row["kind"] == "endpoint_call" for row in source_data["recent_activity"]))

	async def test_agent_endpoint_toolkit_describes_and_calls_a2a_remote_endpoint(self):
		class _FakeAsyncClient:
			def __init__(self, *args, **kwargs):
				self.calls = []

			async def __aenter__(self):
				return self

			async def __aexit__(self, exc_type, exc, tb):
				return False

			async def get(self, url, headers=None):
				self.calls.append(("get", url, headers))
				return _FakeResponse(
					{
						"name": "Remote Planner",
						"description": "Remote planning specialist",
						"supportedInterfaces": [
							{
								"url": "https://remote.example/a2a/json",
								"protocolBinding": "HTTP+JSON",
								"protocolVersion": "1.0",
							}
						],
						"capabilities": {"streaming": True},
						"defaultInputModes": ["text/plain"],
						"defaultOutputModes": ["text/plain"],
						"skills": [{"id": "plan", "name": "Planning"}],
					}
				)

			async def post(self, url, json=None, headers=None):
				self.calls.append(("post", url, json, headers))
				return _FakeResponse(
					{
						"task": {
							"id": "task_123",
							"contextId": "ctx_456",
							"status": {
								"state": "TASK_STATE_COMPLETED",
								"message": {
									"parts": [{"text": "Remote endpoint answer"}]
								},
							},
						}
					}
				)

		with patch("agent_endpoint_runtime.httpx.AsyncClient", _FakeAsyncClient):
			toolkit = AgentEndpointToolkit()
			description = await toolkit.describe_endpoint(
				kind="a2a_remote",
				target="https://remote.example",
			)
			self.assertEqual(description["resolved"]["name"], "Remote Planner")
			self.assertEqual(description["resolved"]["service_url"], "https://remote.example/a2a/json")

			result = await toolkit.consult_endpoint(
				"Summarize the current task context.",
				kind="a2a_remote",
				target="https://remote.example",
			)
			self.assertEqual(result["name"], "Remote Planner")
			self.assertEqual(result["task_id"], "task_123")
			self.assertEqual(result["response"], "Remote endpoint answer")


if __name__ == "__main__":
	unittest.main()
