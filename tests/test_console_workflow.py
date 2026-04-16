from __future__ import annotations

import json
import sys
import unittest

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = PROJECT_ROOT / "app"
if str(APP_DIR) not in sys.path:
	sys.path.insert(0, str(APP_DIR))
if str(PROJECT_ROOT) not in sys.path:
	sys.path.insert(1, str(PROJECT_ROOT))


from console import ConsoleAgentManager, PlannerState
from console_workflow import parse_console_workflow_import
from event_bus import EventBus


class ConsoleWorkflowExportTests(unittest.TestCase):
	def _manager(self) -> ConsoleAgentManager:
		manager = ConsoleAgentManager(
			workspace_mgr=None,
			event_bus=EventBus(),
			port=11361,
			config_path=str(PROJECT_ROOT / "app" / "console_agent.json"),
		)
		manager._config = json.loads((PROJECT_ROOT / "app" / "console_agent.json").read_text(encoding="utf-8"))
		return manager

	def test_build_workflow_export_reflects_runtime_console_state(self) -> None:
		manager = self._manager()
		manager._started = True
		manager._model_source = "openai"
		manager._model_name = "gpt-4o-mini"
		manager._toolkit_names = ["console_toolkit", "file_toolkit", "agent_endpoint_toolkit"]
		manager._toolkit_args = {
			"file_toolkit": {"root": "."},
			"agent_endpoint_toolkit": {"target": "should_not_persist"},
		}
		manager._skill_names = ["web-search"]
		manager._use_backend_memory = True

		exported = manager.build_workflow_export()
		workflow = exported["workflow"]
		node_types = [node["type"] for node in workflow["nodes"]]

		self.assertEqual(exported["name"], "Numel Assistant")
		self.assertIn("agent_chat", node_types)
		self.assertIn("agent_config", node_types)
		self.assertIn("content_db_config", node_types)
		self.assertIn("history_manager_config", node_types)
		self.assertIn("memory_manager_config", node_types)
		self.assertIn("session_manager_config", node_types)
		self.assertIn("skill_config", node_types)

		toolkit_nodes = [node for node in workflow["nodes"] if node["type"] == "toolkit_config"]
		self.assertEqual(
			[node["name"] for node in toolkit_nodes],
			["console_toolkit", "file_toolkit", "agent_endpoint_toolkit"],
		)
		self.assertIsNone(toolkit_nodes[0].get("args"))
		self.assertEqual(toolkit_nodes[1]["args"], {"root": "."})
		self.assertIsNone(toolkit_nodes[2].get("args"))
		self.assertEqual(
			toolkit_nodes[0].get("runtime_binding", {}).get("binding_kind"),
			"numel_runtime",
		)
		self.assertEqual(
			toolkit_nodes[2].get("runtime_binding", {}).get("toolkit"),
			"agent_endpoint_toolkit",
		)
		self.assertEqual(exported["omitted_toolkits"], [])
		self.assertEqual(
			exported["runtime_bound_toolkits"],
			["console_toolkit", "agent_endpoint_toolkit"],
		)

	def test_build_workflow_export_keeps_backend_memory_nodes_even_if_toggle_is_false(self) -> None:
		manager = self._manager()
		manager._started = True
		manager._model_source = "ollama"
		manager._model_name = "qwen3.5:cloud"
		manager._toolkit_names = ["console_toolkit", "code_toolkit"]
		manager._toolkit_args = {}
		manager._skill_names = []
		manager._use_backend_memory = False

		exported = manager.build_workflow_export()
		node_types = [node["type"] for node in exported["workflow"]["nodes"]]

		self.assertIn("content_db_config", node_types)
		self.assertIn("history_manager_config", node_types)
		self.assertIn("memory_manager_config", node_types)
		self.assertIn("session_manager_config", node_types)
		self.assertIn("console_toolkit", [node["name"] for node in exported["workflow"]["nodes"] if node["type"] == "toolkit_config"])
		self.assertIn("code_toolkit", [node["name"] for node in exported["workflow"]["nodes"] if node["type"] == "toolkit_config"])

	def test_build_workflow_export_can_include_active_planner_branch(self) -> None:
		manager = self._manager()
		manager._started = True
		manager._model_source = "openai"
		manager._model_name = "gpt-4o-mini"
		manager._toolkit_names = ["console_toolkit", "workspace_toolkit"]
		manager._toolkit_args = {"workspace_toolkit": {"workflow_name": "Current Workflow"}}
		manager._skill_names = ["web-search"]
		manager._use_backend_memory = True

		planner = PlannerState(key="user_1_tab_1", user_id="user_1", browser_session_id="tab_1")
		planner.enabled = True
		planner.profile = "workflow"
		planner.instructions = "Inspect workflow events and suggest the next graph update."
		planner.subs = ["workflow.completed", "workflow.failed", "manager.workflow_added"]
		planner.timeout = 90
		planner.session_timeout = 900
		planner.max_turns = 7
		planner.debounce = 1.5
		manager._planners[planner.key] = planner

		exported = manager.build_workflow_export(include_planner=True, user_id="user_1", session_id="tab_1")
		workflow = exported["workflow"]
		node_types = [node["type"] for node in workflow["nodes"]]

		self.assertTrue(exported["planner_requested"])
		self.assertTrue(exported["planner_available"])
		self.assertTrue(exported["planner_included"])
		self.assertIn("agent_chat", node_types)
		self.assertIn("agent_flow", node_types)
		self.assertIn("loop_start_flow", node_types)
		self.assertIn("loop_end_flow", node_types)
		self.assertGreaterEqual(node_types.count("transform_flow"), 2)

		planner_agent = next(
			node for node in workflow["nodes"]
			if node.get("type") == "agent_flow" and node.get("extra", {}).get("name") == "Planner Turn · current workbench"
		)
		self.assertIn("[Planner Export]", planner_agent.get("request") or "")
		planner_loop = next(
			node for node in workflow["nodes"]
			if node.get("type") == "loop_start_flow" and "Planner Loop" in (node.get("extra", {}).get("name") or "")
		)
		self.assertEqual(planner_loop.get("max_iter"), 7)
		planner_scope = next(
			node for node in workflow["nodes"]
			if node.get("type") == "transform_flow" and "Planner Scope" in (node.get("extra", {}).get("name") or "")
		)
		self.assertIn("current workbench", planner_scope.get("extra", {}).get("name") or "")

	def test_parse_console_workflow_import_round_trips_console_shape(self) -> None:
		manager = self._manager()
		manager._started = True
		manager._model_source = "openai"
		manager._model_name = "gpt-4o"
		manager._toolkit_names = ["console_toolkit", "file_toolkit"]
		manager._toolkit_args = {"file_toolkit": {"root": "."}}
		manager._skill_names = ["web-search"]
		manager._use_backend_memory = True
		manager._options_override = {
			"name": "Workflow Assistant",
			"description": "Imported from workflow",
			"instructions": ["Stay grounded in the graph."],
			"markdown": True,
		}
		manager._memory_override = {"session_history": 8}

		exported = manager.build_workflow_export()
		parsed = parse_console_workflow_import(exported["workflow"])

		self.assertEqual(parsed["backend_name"], "agno")
		self.assertEqual(parsed["model_source"], "openai")
		self.assertEqual(parsed["model_name"], "gpt-4o")
		self.assertEqual(parsed["toolkit_names"], ["console_toolkit", "file_toolkit"])
		self.assertEqual(parsed["toolkit_args"], {"file_toolkit": {"root": "."}})
		self.assertEqual(parsed["skill_names"], ["web-search"])
		self.assertTrue(parsed["use_backend_memory"])
		self.assertEqual(parsed["memory_override"]["session_history"], 8)
		self.assertEqual(parsed["memory_override"]["history_size"], 5)
		self.assertTrue(parsed["memory_override"]["history_query"])
		self.assertTrue(parsed["memory_override"]["session_query"])
		self.assertTrue(parsed["memory_override"]["session_update"])
		self.assertTrue(parsed["memory_override"]["memory_query"])
		self.assertTrue(parsed["memory_override"]["memory_managed"])
		self.assertEqual(parsed["options_override"]["name"], "Workflow Assistant")
		self.assertEqual(parsed["options_override"]["description"], "Imported from workflow")
		self.assertEqual(parsed["options_override"]["instructions"], ["Stay grounded in the graph."])
		self.assertEqual(parsed["warnings"], [])

	def test_parse_console_workflow_import_rejects_non_console_backend(self) -> None:
		manager = self._manager()
		manager._started = True
		manager._model_source = "ollama"
		manager._model_name = "qwen3.5:cloud"
		manager._toolkit_names = ["console_toolkit"]
		manager._toolkit_args = {}
		manager._skill_names = []
		manager._use_backend_memory = False

		exported = manager.build_workflow_export()
		for node in exported["workflow"]["nodes"]:
			if node.get("type") == "backend_config":
				node["name"] = "other_backend"
				break

		with self.assertRaises(ValueError):
			parse_console_workflow_import(exported["workflow"])

	def test_parse_console_workflow_import_strips_runtime_bound_toolkit_args(self) -> None:
		manager = self._manager()
		manager._started = True
		manager._model_source = "openai"
		manager._model_name = "gpt-4o-mini"
		manager._toolkit_names = ["workspace_toolkit"]
		manager._toolkit_args = {}
		manager._skill_names = []
		manager._use_backend_memory = False

		exported = manager.build_workflow_export()
		for node in exported["workflow"]["nodes"]:
			if node.get("type") == "toolkit_config" and node.get("name") == "workspace_toolkit":
				node["args"] = {"base_url": "http://evil", "workflow_name": "keep_me"}
				break

		parsed = parse_console_workflow_import(exported["workflow"])
		self.assertEqual(parsed["toolkit_names"], ["console_toolkit", "workspace_toolkit"])
		self.assertEqual(parsed["toolkit_args"], {"workspace_toolkit": {"workflow_name": "keep_me"}})
		self.assertTrue(any("runtime-only args were ignored" in warning for warning in parsed["warnings"]))


if __name__ == "__main__":
	unittest.main()
