from __future__ import annotations

import json
import sys
import os
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = PROJECT_ROOT / "app"
if str(APP_DIR) not in sys.path:
	sys.path.insert(0, str(APP_DIR))
if str(PROJECT_ROOT) not in sys.path:
	sys.path.insert(1, str(PROJECT_ROOT))


from impl_agno import build_backend_agno
from schema import Workflow
from skills import SkillManager


class AgnoSkillsIntegrationTests(unittest.TestCase):
	def _skill_manager(self) -> SkillManager:
		fd, state_path_str = tempfile.mkstemp(prefix="numel-skills-", suffix=".json")
		os.close(fd)
		state_path = Path(state_path_str)
		self.addCleanup(lambda: state_path.exists() and state_path.unlink())
		mgr = SkillManager(
			skills_dir=str(PROJECT_ROOT / "app" / "skills"),
			builtin_dirs=[],
			state_path=str(state_path),
		)
		mgr.initialize()
		return mgr

	def _load_skill_demo_workflow(self) -> Workflow:
		data = json.loads((PROJECT_ROOT / "app" / "gallery" / "skill_agent_demo.json").read_text(encoding="utf-8"))
		workflow = Workflow(**data["workflow"])
		workflow.link()
		return workflow

	def test_current_skill_directories_expose_backend_neutral_skill_records(self):
		mgr = self._skill_manager()
		definitions = mgr.get_definitions_for(["web-search", "commit-helper"])
		names = [item["name"] for item in definitions]
		self.assertEqual(names, ["web-search", "commit-helper"])
		web_search = next(item for item in definitions if item["name"] == "web-search")
		self.assertIn("DuckDuckGo", web_search["body"])
		self.assertIn("scripts", web_search)
		self.assertIn("references", web_search)

	def test_workflow_agent_uses_native_agno_skills(self):
		mgr = self._skill_manager()
		workflow = self._load_skill_demo_workflow()
		backend = build_backend_agno(workflow, skill_mgr=mgr)

		agent_index = next(i for i, node in enumerate(workflow.nodes) if node.type == "agent_config")
		agent = backend.handles[agent_index]
		self.assertIsNotNone(agent.skills)
		self.assertIsNotNone(agent.skills.get_skill("web-search"))
		self.assertNotIn("DuckDuckGo", "\n".join(agent.instructions or []))

	def test_prompt_override_keeps_native_skill_metadata_available(self):
		mgr = self._skill_manager()
		workflow = self._load_skill_demo_workflow()

		options_index = next(i for i, node in enumerate(workflow.nodes) if node.type == "agent_options_config")
		workflow.nodes[options_index].prompt_override = "You are a custom research agent."

		backend = build_backend_agno(workflow, skill_mgr=mgr)
		agent_index = next(i for i, node in enumerate(workflow.nodes) if node.type == "agent_config")
		agent = backend.handles[agent_index]

		self.assertIsInstance(agent.system_message, str)
		self.assertIn("You are a custom research agent.", agent.system_message)
		self.assertIn("<skills_system>", agent.system_message)
		self.assertIn("web-search", agent.system_message)


if __name__ == "__main__":
	unittest.main()
