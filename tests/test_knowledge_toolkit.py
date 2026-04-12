from __future__ import annotations

import sys
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = PROJECT_ROOT / "app"
if str(APP_DIR) not in sys.path:
	sys.path.insert(0, str(APP_DIR))
if str(PROJECT_ROOT) not in sys.path:
	sys.path.insert(1, str(PROJECT_ROOT))


from agno.tools import Toolkit as AgnoToolkit
from backend_factory import build_backend_toolkit
from toolkit_runtime import load_numel_toolkit
from toolkits.knowledge_toolkit import KnowledgeToolkit


class _FakeBackend:
	def __init__(self):
		self.add_calls = []
		self.search_calls = []
		self.remove_calls = []

	async def add_contents(self, handle, items):
		self.add_calls.append((handle, items))
		return [f"doc_{idx+1}" for idx in range(len(items))]

	async def search_contents(self, handle, *, query, max_results=None, filters=None, search_type=None):
		self.search_calls.append(
			{
				"handle": handle,
				"query": query,
				"max_results": max_results,
				"filters": filters,
				"search_type": search_type,
			}
		)
		return [{"content": "knowledge hit", "metadata": {"topic": "docs"}}]

	async def list_contents(self, handle):
		return [("doc_1", {"topic": "docs"})]

	async def remove_contents(self, handle, ids):
		self.remove_calls.append((handle, ids))
		return [True for _ in ids]


class KnowledgeToolkitTests(unittest.IsolatedAsyncioTestCase):
	def test_toolkit_loader_discovers_knowledge_toolkit(self):
		record = load_numel_toolkit("toolkits.knowledge_toolkit", {}, log_prefix="Test toolkit")
		self.assertIsNotNone(record)
		self.assertEqual(record["module_name"], "toolkits.knowledge_toolkit")
		method_names = {tool.__name__ for tool in record["tools"]}
		self.assertIn("add_text", method_names)
		self.assertIn("search", method_names)

	def test_knowledge_toolkit_wraps_as_native_backend_toolkit(self):
		record = load_numel_toolkit("toolkits.knowledge_toolkit", {}, log_prefix="Test toolkit")
		native_toolkit = build_backend_toolkit(record)
		self.assertIsInstance(native_toolkit, AgnoToolkit)
		self.assertFalse(native_toolkit.functions)
		self.assertIn("add_text", native_toolkit.async_functions)
		self.assertIn("search", native_toolkit.async_functions)
		self.assertIn("add_text", native_toolkit.get_async_functions())
		self.assertIn("search", native_toolkit.get_async_functions())

	async def test_knowledge_toolkit_uses_shared_backend_runtime(self):
		fake_backend = _FakeBackend()
		fake_handle = object()

		with patch("toolkits.knowledge_toolkit.build_knowledge_runtime", return_value=(fake_backend, fake_handle)) as patched:
			toolkit = KnowledgeToolkit(content_db_url="storage/test_content", index_db_url="storage/test_index")
			add_result = await toolkit.add_text("hello knowledge", metadata={"kind": "note"})
			search_result = await toolkit.search("hello")
			list_result = await toolkit.list_contents()
			remove_result = await toolkit.remove_contents(["doc_1"])

		self.assertEqual(patched.call_count, 1)
		self.assertEqual(add_result["count"], 1)
		self.assertEqual(fake_backend.add_calls[0][0], fake_handle)
		self.assertEqual(fake_backend.add_calls[0][1][0]["content"], b"hello knowledge")
		self.assertEqual(fake_backend.add_calls[0][1][0]["metadata"]["kind"], "note")
		self.assertEqual(search_result[0]["content"], "knowledge hit")
		self.assertEqual(fake_backend.search_calls[0]["query"], "hello")
		self.assertEqual(list_result[0]["id"], "doc_1")
		self.assertEqual(remove_result, [True])

	async def test_knowledge_toolkit_add_file_normalizes_path(self):
		fake_backend = _FakeBackend()
		fake_handle = object()

		test_dir = PROJECT_ROOT / "storage" / f"test-knowledge-toolkit-{uuid.uuid4().hex[:8]}"
		test_dir.mkdir(parents=True, exist_ok=True)
		self.addCleanup(lambda: test_dir.exists() and __import__("shutil").rmtree(test_dir, ignore_errors=True))
		path = test_dir / "note.txt"
		path.write_text("hello from file", encoding="utf-8")
		with patch("toolkits.knowledge_toolkit.build_knowledge_runtime", return_value=(fake_backend, fake_handle)):
			toolkit = KnowledgeToolkit()
			result = await toolkit.add_file(str(path), metadata={"source_type": "file"})

		self.assertEqual(result["count"], 1)
		item = fake_backend.add_calls[0][1][0]
		self.assertEqual(item["filename"], "note.txt")
		self.assertIn(b"hello from file", item["content"])
		self.assertEqual(item["metadata"]["source_type"], "file")


if __name__ == "__main__":
	unittest.main()
