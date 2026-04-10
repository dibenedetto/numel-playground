from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = PROJECT_ROOT / "app"
if str(APP_DIR) not in sys.path:
	sys.path.insert(0, str(APP_DIR))
if str(PROJECT_ROOT) not in sys.path:
	sys.path.insert(1, str(PROJECT_ROOT))


from backend_factory import build_backend, get_workflow_backend_name, normalize_backend_name
from schema import DEFAULT_BACKEND_NAME, Workflow
from skills import SkillManager


class BackendFactoryTests(unittest.TestCase):
	def _skill_manager(self) -> SkillManager:
		fd, state_path_str = tempfile.mkstemp(prefix="numel-backends-", suffix=".json")
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

	def _load_workflow(self) -> Workflow:
		data = json.loads((PROJECT_ROOT / "app" / "gallery" / "skill_agent_demo.json").read_text(encoding="utf-8"))
		workflow = Workflow(**data["workflow"])
		workflow.link()
		return workflow

	def test_normalize_backend_name_defaults_to_schema_default(self):
		self.assertEqual(normalize_backend_name(None), DEFAULT_BACKEND_NAME)
		self.assertEqual(normalize_backend_name(""), DEFAULT_BACKEND_NAME)
		self.assertEqual(normalize_backend_name("AGNO"), DEFAULT_BACKEND_NAME)

	def test_get_workflow_backend_name_reads_backend_config(self):
		workflow = self._load_workflow()
		self.assertEqual(get_workflow_backend_name(workflow), DEFAULT_BACKEND_NAME)

	def test_build_backend_uses_backend_dispatch_layer(self):
		mgr = self._skill_manager()
		workflow = self._load_workflow()
		backend = build_backend(workflow, skill_mgr=mgr)

		agent_index = next(i for i, node in enumerate(workflow.nodes) if node.type == "agent_config")
		agent = backend.handles[agent_index]
		self.assertIsNotNone(agent)
		self.assertEqual(get_workflow_backend_name(workflow), DEFAULT_BACKEND_NAME)


if __name__ == "__main__":
	unittest.main()
