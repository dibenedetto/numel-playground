from __future__ import annotations

import json
import shutil
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


from gallery import GalleryManager
from schema import Workflow


class GalleryKnowledgeExamplesTests(unittest.TestCase):
	def _load_workflow(self, filename: str) -> Workflow:
		data = json.loads((PROJECT_ROOT / "app" / "gallery" / filename).read_text(encoding="utf-8"))
		workflow = Workflow(**data["workflow"])
		workflow.link()
		return workflow

	def test_knowledge_file_ingestor_example_links(self):
		workflow = self._load_workflow("knowledge_file_ingestor.json")
		node_types = [node.type for node in workflow.nodes]
		self.assertIn("fswatch_source_flow", node_types)
		self.assertIn("knowledge_ingest_flow", node_types)
		self.assertIn("knowledge_manager_config", node_types)

	def test_knowledge_query_assistant_example_links(self):
		workflow = self._load_workflow("knowledge_query_assistant.json")
		node_types = [node.type for node in workflow.nodes]
		self.assertIn("agent_config", node_types)
		self.assertIn("knowledge_manager_config", node_types)
		self.assertIn("user_input_flow", node_types)

	def test_gallery_manager_syncs_missing_builtin_items_into_existing_gallery(self):
		root = PROJECT_ROOT / "storage" / f"gallery-sync-{uuid.uuid4().hex[:8]}"
		gallery_dir = root / "runtime_gallery"
		seed_dir = root / "seed_gallery"
		gallery_dir.mkdir(parents=True, exist_ok=True)
		seed_dir.mkdir(parents=True, exist_ok=True)
		self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))

		existing = {
			"id": "existing_item",
			"title": "Existing",
			"description": "Existing runtime item",
			"category": "examples",
			"tags": ["example"],
			"workflow": {"type": "workflow", "nodes": [], "edges": []},
			"author": "tester",
			"created_at": 1.0,
		}
		(gallery_dir / "existing_item.json").write_text(json.dumps(existing), encoding="utf-8")

		builtin = json.loads((PROJECT_ROOT / "app" / "gallery" / "knowledge_query_assistant.json").read_text(encoding="utf-8"))
		(seed_dir / "knowledge_query_assistant.json").write_text(json.dumps(builtin), encoding="utf-8")
		raw_without_id = {"type": "workflow", "nodes": [], "edges": []}
		(seed_dir / "raw_example.json").write_text(json.dumps(raw_without_id), encoding="utf-8")

		mgr = GalleryManager(gallery_dir=str(gallery_dir), seed_dirs=[str(seed_dir)])
		mgr.initialize()

		items = {item["id"] for item in mgr.list()}
		self.assertIn("existing_item", items)
		self.assertIn("knowledge_query_assistant", items)
		self.assertEqual(len(items), 2)


if __name__ == "__main__":
	unittest.main()
