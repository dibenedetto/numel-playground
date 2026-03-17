# gallery.py — Workflow Gallery / Marketplace
#
# Browse, search, and install workflow templates.
# Auto-seeds from examples/ directory on first run.

import json
import os
import time
import uuid
from   typing import Any, Dict, List, Optional

from   fastapi import FastAPI
from   pydantic import BaseModel


_APP_DIR      = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_APP_DIR)
_GALLERY_DIR  = os.path.join(_APP_DIR, "gallery")
_EXAMPLES_DIR = os.path.join(_PROJECT_ROOT, "examples")


class GalleryItem(BaseModel):
	id:          str
	title:       str
	description: str            = ""
	category:    str            = "general"
	tags:        List[str]      = []
	workflow:    Dict[str, Any] = {}
	author:      str            = "system"
	created_at:  float          = 0.0


class GalleryManager:
	"""Manages a local gallery of shareable workflow templates."""

	def __init__(self, gallery_dir: str = _GALLERY_DIR, examples_dir: str = _EXAMPLES_DIR):
		self._dir      = gallery_dir
		self._examples = examples_dir
		self._items: Dict[str, GalleryItem] = {}

	def initialize(self):
		os.makedirs(self._dir, exist_ok=True)
		self._load()
		if not self._items:
			self._seed_from_examples()

	# ── Persistence ───────────────────────────────────────────

	def _load(self):
		for fname in os.listdir(self._dir):
			if not fname.endswith(".json"):
				continue
			try:
				with open(os.path.join(self._dir, fname)) as f:
					data = json.load(f)
				item = GalleryItem(**data)
				self._items[item.id] = item
			except Exception:
				pass

	def _save_item(self, item: GalleryItem):
		path = os.path.join(self._dir, f"{item.id}.json")
		with open(path, "w") as f:
			json.dump(item.model_dump(), f, indent=2)

	def _seed_from_examples(self):
		if not os.path.isdir(self._examples):
			return
		for fname in sorted(os.listdir(self._examples)):
			if not fname.endswith(".json"):
				continue
			try:
				with open(os.path.join(self._examples, fname)) as f:
					wf = json.load(f)
				name  = fname.replace(".json", "").replace("-", " ").replace("_", " ").title()
				item  = GalleryItem(
					id          = str(uuid.uuid4())[:8],
					title       = name,
					description = f"Example workflow: {name}",
					category    = "examples",
					tags        = ["example"],
					workflow    = wf,
					author      = "system",
					created_at  = time.time(),
				)
				self._items[item.id] = item
				self._save_item(item)
			except Exception:
				pass

	# ── Public API ────────────────────────────────────────────

	def list(self, category: str = None, tags: List[str] = None,
	         search: str = None) -> List[dict]:
		results = list(self._items.values())
		if category:
			results = [i for i in results if i.category == category]
		if tags:
			results = [i for i in results if set(tags) & set(i.tags)]
		if search:
			q = search.lower()
			results = [i for i in results
			           if q in i.title.lower() or q in i.description.lower()]
		return [i.model_dump(exclude={"workflow"}) for i in results]

	def get(self, id: str) -> Optional[dict]:
		item = self._items.get(id)
		return item.model_dump() if item else None

	def publish(self, workflow: dict, title: str, description: str = "",
	            category: str = "community", tags: List[str] = None,
	            author: str = "user") -> dict:
		item = GalleryItem(
			id          = str(uuid.uuid4())[:8],
			title       = title,
			description = description,
			category    = category,
			tags        = tags or [],
			workflow    = workflow,
			author      = author,
			created_at  = time.time(),
		)
		self._items[item.id] = item
		self._save_item(item)
		return item.model_dump()

	def remove(self, id: str) -> bool:
		if id not in self._items:
			return False
		del self._items[id]
		path = os.path.join(self._dir, f"{id}.json")
		if os.path.exists(path):
			os.remove(path)
		return True

	def categories(self) -> List[str]:
		return sorted({i.category for i in self._items.values()})

	def tags(self) -> List[str]:
		all_tags = set()
		for i in self._items.values():
			all_tags.update(i.tags)
		return sorted(all_tags)


# ── FastAPI Routes ────────────────────────────────────────────────

def setup_gallery_api(app: FastAPI, mgr: GalleryManager):

	class ListReq(BaseModel):
		category: Optional[str]  = None
		tags:     Optional[List[str]] = None
		search:   Optional[str]  = None

	class GetReq(BaseModel):
		id: str

	class PublishReq(BaseModel):
		workflow_name: Optional[str] = None
		workflow:      Optional[Dict[str, Any]] = None
		title:         str = "Untitled"
		description:   str = ""
		category:      str = "community"
		tags:          List[str] = []

	class RemoveReq(BaseModel):
		id: str

	@app.post("/gallery/list")
	async def gallery_list(req: ListReq):
		return mgr.list(category=req.category, tags=req.tags, search=req.search)

	@app.post("/gallery/get")
	async def gallery_get(req: GetReq):
		item = mgr.get(req.id)
		if not item:
			return {"error": "not found"}
		return item

	@app.post("/gallery/publish")
	async def gallery_publish(req: PublishReq):
		wf = req.workflow or {}
		return mgr.publish(workflow=wf, title=req.title, description=req.description,
		                   category=req.category, tags=req.tags)

	@app.post("/gallery/remove")
	async def gallery_remove(req: RemoveReq):
		ok = mgr.remove(req.id)
		return {"ok": ok}

	@app.post("/gallery/categories")
	async def gallery_categories():
		return mgr.categories()

	@app.post("/gallery/tags")
	async def gallery_tags():
		return mgr.tags()
