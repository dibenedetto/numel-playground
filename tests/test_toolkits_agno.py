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


from agno.tools import Toolkit as AgnoToolkit

from backend_factory import build_backend_toolkit
from impl_agno import build_backend_agno
from schema import Workflow
from toolkit_runtime import load_numel_toolkit


class AgnoToolkitsIntegrationTests(unittest.TestCase):
	def test_numel_toolkit_loader_keeps_magic_discovery(self):
		record = load_numel_toolkit("toolkits.http_toolkit", {}, log_prefix="Test toolkit")
		self.assertIsNotNone(record)
		self.assertEqual(record["module_name"], "toolkits.http_toolkit")
		self.assertTrue(record["tools"])
		self.assertIn("HTTP requests", record["description"])

	def test_backend_toolkit_wrapper_uses_native_toolkit_container(self):
		record = load_numel_toolkit("toolkits.http_toolkit", {}, log_prefix="Test toolkit")
		native_toolkit = build_backend_toolkit(record)
		self.assertIsInstance(native_toolkit, AgnoToolkit)
		self.assertIn("get", native_toolkit.functions)
		self.assertTrue(native_toolkit.add_instructions)
		self.assertIn("HTTP requests", native_toolkit.instructions or "")

	def test_workflow_agent_uses_native_toolkit_container(self):
		data = json.loads((PROJECT_ROOT / "app" / "gallery" / "skill_agent_demo.json").read_text(encoding="utf-8"))
		workflow = Workflow(**data["workflow"])
		workflow.link()

		backend = build_backend_agno(workflow, skill_mgr=None)
		agent_index = next(i for i, node in enumerate(workflow.nodes) if node.type == "agent_config")
		agent = backend.handles[agent_index]

		toolkits = [tool for tool in (agent.tools or []) if isinstance(tool, AgnoToolkit)]
		self.assertTrue(toolkits)
		self.assertEqual(toolkits[0].name, "toolkits.http_toolkit")
		self.assertNotIn("Toolkit for making HTTP requests", "\n".join(agent.instructions or []))


if __name__ == "__main__":
	unittest.main()
