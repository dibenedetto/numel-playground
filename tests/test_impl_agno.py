import unittest
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = PROJECT_ROOT / "app"
if str(APP_DIR) not in sys.path:
	sys.path.insert(0, str(APP_DIR))
if str(PROJECT_ROOT) not in sys.path:
	sys.path.insert(1, str(PROJECT_ROOT))

from impl_agno import run_chat_agent_agno


class _FakeResponse:
	def __init__(self, content):
		self.content = content


class _FakeAgent:
	def __init__(self, response):
		self._response = response

	async def arun(self, message, **kwargs):
		return self._response


class ImplAgnoTests(unittest.IsolatedAsyncioTestCase):
	async def test_run_chat_agent_raises_for_missing_model_text(self):
		agent = _FakeAgent(_FakeResponse('Error: model "missing-model" not found, try pulling it first.'))
		with self.assertRaisesRegex(RuntimeError, 'missing-model'):
			await run_chat_agent_agno(agent, 'hello')

	async def test_run_chat_agent_allows_normal_text_response(self):
		response = await run_chat_agent_agno(_FakeAgent(_FakeResponse('Hello from the assistant.')), 'hello')
		self.assertEqual(response.content, 'Hello from the assistant.')
