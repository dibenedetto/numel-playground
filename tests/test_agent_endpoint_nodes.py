from __future__ import annotations

import asyncio
import sys
import unittest
import uuid

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = PROJECT_ROOT / "app"
if str(APP_DIR) not in sys.path:
	sys.path.insert(0, str(APP_DIR))
if str(PROJECT_ROOT) not in sys.path:
	sys.path.insert(1, str(PROJECT_ROOT))


from assistant_deployments import AssistantDeploymentConfig, AssistantDeploymentManager
from engine import WorkflowEngine
from event_bus import EventBus
from nodes import ImplementedBackend, NodeExecutionContext, WFAgentEndpointFlow
from schema import AgentEndpointConfig, AgentEndpointFlow, Edge, EndFlow, StartFlow, Workflow, WorkflowOptions


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
		return {"response": "Specialist reply", "tool_calls": []}


def _fake_backend(node_count: int) -> ImplementedBackend:
	async def _noop_tool(*args, **kwargs):
		return {}

	async def _noop_agent(*args, **kwargs):
		return {}

	async def _noop_add(*args, **kwargs):
		return []

	async def _noop_search(*args, **kwargs):
		return []

	async def _noop_remove(*args, **kwargs):
		return []

	async def _noop_list(*args, **kwargs):
		return []

	return ImplementedBackend(
		handles=[None] * node_count,
		run_tool=_noop_tool,
		run_agent=_noop_agent,
		get_agent_app=lambda agent: None,
		add_contents=_noop_add,
		search_contents=_noop_search,
		remove_contents=_noop_remove,
		list_contents=_noop_list,
	)


class AgentEndpointNodeTests(unittest.IsolatedAsyncioTestCase):
	async def test_agent_endpoint_flow_executes_general_mode(self):
		captured = {}

		async def fake_ref(*, mode, prompt, session_id=None, source_deployment_id=None, sender_name=None, user_id=None):
			captured["mode"] = mode
			captured["prompt"] = prompt
			captured["session_id"] = session_id
			captured["source_deployment_id"] = source_deployment_id
			captured["sender_name"] = sender_name
			captured["user_id"] = user_id
			return {
				"kind": "deployment",
				"name": "Billing Specialist",
				"response": "Looks good",
				"status": "ok",
				"task_id": None,
			}

		node = WFAgentEndpointFlow({}, None, ref=fake_ref)
		context = NodeExecutionContext()
		context.inputs = {
			"mode": "delegate",
			"prompt": {"message": "Review this invoice issue"},
			"session_id": "sess_1",
			"source_deployment_id": "deploy_source",
			"sender_name": "Support Front Door",
			"user_id": "user_1",
			"config": AgentEndpointConfig(target="deploy_target"),
		}

		result = await node.execute(context)

		self.assertTrue(result.success)
		self.assertEqual(captured["mode"], "delegate")
		self.assertEqual(captured["prompt"], "Review this invoice issue")
		self.assertEqual(result.outputs["response"], "Looks good")
		self.assertEqual(result.outputs["endpoint_name"], "Billing Specialist")
		self.assertEqual(result.outputs["endpoint_kind"], "deployment")

	async def test_workflow_engine_executes_agent_endpoint_flow_via_config_edge(self):
		test_dir = PROJECT_ROOT / "storage" / f"test-agent-endpoint-flow-{uuid.uuid4().hex[:8]}"
		test_dir.mkdir(parents=True, exist_ok=True)
		self.addCleanup(lambda: test_dir.exists() and __import__("shutil").rmtree(test_dir, ignore_errors=True))

		deployment_mgr = AssistantDeploymentManager(config_path=str(test_dir / "assistant_deployments.json"))
		deployment_mgr.initialize(channel_registry=None, channel_pool=None)
		deployment_mgr.add(
			AssistantDeploymentConfig(
				id="deploy_target",
				name="Billing Specialist",
				description="Handles billing questions.",
				model_source="openai",
				model_name="gpt-4o-mini",
				toolkit_names=["file_toolkit"],
				skill_names=["billing_triage"],
				enabled=True,
				created_by="user_1",
			)
		)

		channel_pool = _FakeChannelPool()
		engine = WorkflowEngine(
			EventBus(),
			assistant_deployment_mgr=deployment_mgr,
			channel_pool=channel_pool,
		)
		workflow = Workflow(
			options=WorkflowOptions(name="Endpoint Flow Test"),
			nodes=[
				StartFlow(),
				AgentEndpointConfig(target="deploy_target"),
				AgentEndpointFlow(mode="consult", prompt="Need advice on this invoice"),
				EndFlow(),
			],
			edges=[
				Edge(source=0, target=2, source_slot="flow_out", target_slot="flow_in"),
				Edge(source=1, target=2, source_slot="config", target_slot="config"),
				Edge(source=2, target=3, source_slot="flow_out", target_slot="flow_in"),
			],
		)
		workflow.link()

		backend = _fake_backend(len(workflow.nodes))
		execution_id = await engine.start_workflow(workflow, backend, initial_data={})
		await asyncio.wait_for(engine.execution_tasks[execution_id], timeout=10)
		results = engine.get_execution_results(execution_id)

		self.assertIsNotNone(results)
		node_outputs = results["node_outputs"]
		endpoint_output = node_outputs["2"]
		self.assertEqual(endpoint_output["response"], "Specialist reply")
		self.assertEqual(endpoint_output["status"], "ok")
		self.assertEqual(endpoint_output["endpoint_kind"], "deployment")
		self.assertEqual(channel_pool.calls[0]["assistant_name"], "Billing Specialist")
		self.assertEqual(channel_pool.calls[0]["model_source"], "openai")
		self.assertEqual(channel_pool.calls[0]["model_name"], "gpt-4o-mini")


if __name__ == "__main__":
	unittest.main()
