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


from schema import Workflow


class GalleryAssistantDeploymentExamplesTests(unittest.TestCase):
	def _load_gallery_workflow(self, filename: str) -> Workflow:
		data = json.loads((PROJECT_ROOT / "app" / "gallery" / filename).read_text(encoding="utf-8"))
		workflow = Workflow(**data["workflow"])
		workflow.link()
		return workflow

	def _load_tutorial_workflow(self, filename: str) -> Workflow:
		data = json.loads((PROJECT_ROOT / "docs" / filename).read_text(encoding="utf-8"))
		workflow = Workflow(**data)
		workflow.link()
		return workflow

	def test_support_workbench_gallery_example_links(self):
		workflow = self._load_gallery_workflow("assistant_support_workbench.json")
		node_types = [node.type for node in workflow.nodes]
		self.assertIn("agent_config", node_types)
		self.assertIn("knowledge_manager_config", node_types)
		self.assertIn("toolkit_config", node_types)

	def test_ops_workbench_gallery_example_links(self):
		workflow = self._load_gallery_workflow("assistant_ops_workbench.json")
		node_types = [node.type for node in workflow.nodes]
		self.assertIn("agent_config", node_types)
		self.assertIn("agent_flow", node_types)
		self.assertIn("toolkit_config", node_types)

	def test_assistant_deployments_tutorial_workflow_links(self):
		workflow = self._load_tutorial_workflow("tutorial-11-assistant-deployments.json")
		node_types = [node.type for node in workflow.nodes]
		self.assertIn("agent_config", node_types)
		self.assertIn("knowledge_manager_config", node_types)
		self.assertIn("user_input_flow", node_types)


if __name__ == "__main__":
	unittest.main()
