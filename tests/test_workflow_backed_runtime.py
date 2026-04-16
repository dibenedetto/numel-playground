from __future__ import annotations

import copy
import threading
import sys
import unittest

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = PROJECT_ROOT / "app"
if str(APP_DIR) not in sys.path:
	sys.path.insert(0, str(APP_DIR))
if str(PROJECT_ROOT) not in sys.path:
	sys.path.insert(1, str(PROJECT_ROOT))


from runtime_toolkit_bindings import bind_runtime_toolkits_to_workflow
from workflow_backed_runtime import build_agent_turn_workflow


class WorkflowBackedRuntimeTests(unittest.TestCase):
	def test_build_agent_turn_workflow_converts_chat_to_agent_flow(self) -> None:
		built = build_agent_turn_workflow(
			workflow_name="Planner Turn",
			request="inspect the workflow",
			model_source="openai",
			model_name="gpt-4o-mini",
			toolkit_names=["console_toolkit", "workspace_toolkit"],
			toolkit_args={"workspace_toolkit": {"workflow_name": "Current Workflow"}},
			skill_names=["web-search"],
			options_config={
				"name": "Planner",
				"description": "Workflow-backed planner",
				"instructions": ["Stay grounded in the graph."],
				"markdown": True,
			},
			extra_instructions=["[Planner Mode]"],
			sender_name="Planner",
		)

		workflow = built["workflow"]
		nodes = list(workflow.get("nodes") or [])
		agent_node = nodes[built["agent_node_index"]]
		self.assertEqual(agent_node["type"], "agent_flow")
		self.assertEqual(agent_node["request"], "inspect the workflow")
		self.assertEqual(workflow["options"]["name"], "Planner Turn")

		options_node = next(node for node in nodes if node.get("type") == "agent_options_config")
		self.assertIn("Stay grounded in the graph.", list(options_node.get("instructions") or []))
		self.assertIn("[Planner Mode]", list(options_node.get("instructions") or []))

		toolkit_nodes = [node for node in nodes if node.get("type") == "toolkit_config"]
		self.assertEqual(
			[node.get("name") for node in toolkit_nodes],
			["console_toolkit", "workspace_toolkit"],
		)
		self.assertEqual(
			toolkit_nodes[1].get("args"),
			{"workflow_name": "Current Workflow"},
		)

	def test_bind_runtime_toolkits_to_workflow_injects_live_args(self) -> None:
		built = build_agent_turn_workflow(
			workflow_name="Runtime Bound",
			request="hello",
			model_source="openai",
			model_name="gpt-4o-mini",
			toolkit_names=["console_toolkit", "channel_toolkit", "agent_endpoint_toolkit"],
			toolkit_args={},
			options_config={"name": "Runtime Bound"},
		)

		class _LockedObject:
			def __init__(self) -> None:
				self.lock = threading.RLock()

		bound = bind_runtime_toolkits_to_workflow(
			built["workflow"],
			base_url="http://localhost:11360",
			internal_token="internal-token",
			user_id="user_123",
			auth_token="auth-token",
			local_app=_LockedObject(),
			channel_registry=_LockedObject(),
			deployment_id="deploy_123",
		)

		toolkit_nodes = {
			str(node.get("name")): node
			for node in list(bound.get("nodes") or [])
			if node.get("type") == "toolkit_config"
		}
		self.assertEqual(toolkit_nodes["console_toolkit"]["args"]["base_url"], "http://localhost:11360")
		self.assertIsInstance(toolkit_nodes["console_toolkit"]["args"]["runtime_context_id"], str)
		self.assertIsInstance(toolkit_nodes["channel_toolkit"]["args"]["runtime_context_id"], str)
		self.assertNotIn("local_app", toolkit_nodes["console_toolkit"]["args"])
		self.assertNotIn("channel_registry", toolkit_nodes["channel_toolkit"]["args"])
		self.assertEqual(toolkit_nodes["agent_endpoint_toolkit"]["args"]["deployment_id"], "deploy_123")
		copy.deepcopy(bound)


if __name__ == "__main__":
	unittest.main()
