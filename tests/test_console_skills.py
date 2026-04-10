from __future__ import annotations

import asyncio
import os
import sys
import tempfile
import unittest
from pathlib import Path

from agno.tools import Toolkit as AgnoToolkit


PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = PROJECT_ROOT / "app"
if str(APP_DIR) not in sys.path:
	sys.path.insert(0, str(APP_DIR))
if str(PROJECT_ROOT) not in sys.path:
	sys.path.insert(1, str(PROJECT_ROOT))


from console import ChannelAgentPool, _resolve_native_skill_bundle
from skills import SkillManager


class ConsoleNativeSkillsTests(unittest.TestCase):
	def _skill_manager(self) -> SkillManager:
		fd, state_path_str = tempfile.mkstemp(prefix="numel-console-skills-", suffix=".json")
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

	def test_console_skill_bundle_uses_backend_native_skills(self):
		mgr = self._skill_manager()
		skills = _resolve_native_skill_bundle(mgr, skill_names=["web-search"])
		self.assertIsNotNone(skills)
		self.assertIsNotNone(skills.get_skill("web-search"))

	def test_channel_agent_pool_attaches_native_skills(self):
		mgr = self._skill_manager()
		mgr.enable("web-search")
		pool = ChannelAgentPool()
		pool.set_skill_mgr(mgr)

		agent = asyncio.run(pool._build_agent())
		self.assertIsNotNone(agent.skills)
		self.assertIsNotNone(agent.skills.get_skill("web-search"))
		self.assertNotIn("DuckDuckGo", "\n".join(agent.instructions or []))

	def test_channel_agent_pool_wraps_toolkits_natively(self):
		pool = ChannelAgentPool()
		agent = asyncio.run(pool._build_agent())
		self.assertTrue(any(isinstance(tool, AgnoToolkit) for tool in (agent.tools or [])))


if __name__ == "__main__":
	unittest.main()
