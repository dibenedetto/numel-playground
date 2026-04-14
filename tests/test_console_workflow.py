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


from console import ConsoleAgentManager
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
		self.assertIn("memory_manager_config", node_types)
		self.assertIn("session_manager_config", node_types)
		self.assertIn("skill_config", node_types)

		toolkit_nodes = [node for node in workflow["nodes"] if node["type"] == "toolkit_config"]
		self.assertEqual(len(toolkit_nodes), 1)
		self.assertEqual(toolkit_nodes[0]["name"], "file_toolkit")
		self.assertEqual(toolkit_nodes[0]["args"], {"root": "."})
		self.assertIn("console_toolkit", exported["omitted_toolkits"])
		self.assertIn("agent_endpoint_toolkit", exported["omitted_toolkits"])

	def test_build_workflow_export_omits_memory_nodes_when_disabled(self) -> None:
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

		self.assertNotIn("memory_manager_config", node_types)
		self.assertNotIn("session_manager_config", node_types)
		self.assertIn("code_toolkit", [node["name"] for node in exported["workflow"]["nodes"] if node["type"] == "toolkit_config"])

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
		self.assertEqual(parsed["toolkit_names"], ["file_toolkit"])
		self.assertEqual(parsed["toolkit_args"], {"file_toolkit": {"root": "."}})
		self.assertEqual(parsed["skill_names"], ["web-search"])
		self.assertTrue(parsed["use_backend_memory"])
		self.assertEqual(parsed["memory_override"], {"session_history": 8})
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


if __name__ == "__main__":
	unittest.main()
