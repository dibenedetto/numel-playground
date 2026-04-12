from __future__ import annotations

import sys
import unittest
import uuid
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = PROJECT_ROOT / "app"
if str(APP_DIR) not in sys.path:
	sys.path.insert(0, str(APP_DIR))
if str(PROJECT_ROOT) not in sys.path:
	sys.path.insert(1, str(PROJECT_ROOT))


from nodes import NodeExecutionContext, WFKnowledgeIngestFlow, WFKnowledgeSearchFlow


class KnowledgeNodeTests(unittest.IsolatedAsyncioTestCase):
	async def test_knowledge_ingest_flow_normalizes_items(self):
		seen = []

		async def fake_add(items):
			seen.extend(items)
			return ["doc_1", "doc_2"]

		node = WFKnowledgeIngestFlow({}, None, ref=fake_add)
		context = NodeExecutionContext()
		context.inputs = {
			"input": [
				"hello world",
				{"content": "mail body", "filename": "mail.txt", "metadata": {"source_type": "email"}},
			],
			"metadata": {"topic": "docs"},
		}

		result = await node.execute(context)

		self.assertTrue(result.success)
		self.assertEqual(result.outputs["ids"], ["doc_1", "doc_2"])
		self.assertEqual(result.outputs["count"], 2)
		self.assertEqual(len(seen), 2)
		self.assertEqual(seen[0]["filename"], "knowledge_item_1.txt")
		self.assertEqual(seen[0]["content"], b"hello world")
		self.assertEqual(seen[0]["metadata"]["topic"], "docs")
		self.assertEqual(seen[1]["filename"], "mail.txt")
		self.assertEqual(seen[1]["content"], b"mail body")
		self.assertEqual(seen[1]["metadata"]["source_type"], "email")

	async def test_knowledge_ingest_flow_reads_path_items(self):
		test_dir = PROJECT_ROOT / "storage" / f"test-knowledge-node-{uuid.uuid4().hex[:8]}"
		test_dir.mkdir(parents=True, exist_ok=True)
		self.addCleanup(lambda: test_dir.exists() and __import__("shutil").rmtree(test_dir, ignore_errors=True))

		path = test_dir / "note.md"
		path.write_text("# Hello\nKnowledge body", encoding="utf-8")
		seen = []

		async def fake_add(items):
			seen.extend(items)
			return ["doc_1"]

		node = WFKnowledgeIngestFlow({}, None, ref=fake_add)
		context = NodeExecutionContext()
		context.inputs = {
			"input": {"path": str(path), "metadata": {"kind": "file"}},
		}

		result = await node.execute(context)

		self.assertTrue(result.success)
		self.assertEqual(result.outputs["count"], 1)
		self.assertEqual(seen[0]["filename"], "note.md")
		self.assertIn(b"Knowledge body", seen[0]["content"])
		self.assertEqual(seen[0]["metadata"]["kind"], "file")
		self.assertEqual(seen[0]["metadata"]["path"], str(path))

	async def test_knowledge_search_flow_uses_structured_query(self):
		captured = {}

		async def fake_search(*, query, max_results=None, filters=None, search_type=None):
			captured["query"] = query
			captured["max_results"] = max_results
			captured["filters"] = filters
			captured["search_type"] = search_type
			return [{"content": "mesh result", "metadata": {"tag": "mesh"}}]

		node = WFKnowledgeSearchFlow({}, None, ref=fake_search)
		context = NodeExecutionContext()
		context.inputs = {
			"query": {"message": "find mesh documents"},
			"max_results": 3,
			"filters": {"tag": "mesh"},
			"search_type": "vector",
		}

		result = await node.execute(context)

		self.assertTrue(result.success)
		self.assertEqual(captured["query"], "find mesh documents")
		self.assertEqual(captured["max_results"], 3)
		self.assertEqual(captured["filters"], {"tag": "mesh"})
		self.assertEqual(captured["search_type"], "vector")
		self.assertEqual(result.outputs["count"], 1)
		self.assertEqual(result.outputs["results"][0]["content"], "mesh result")


if __name__ == "__main__":
	unittest.main()
