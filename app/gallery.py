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
from   runtime_settings import get_runtime_settings


_SETTINGS            = get_runtime_settings()
_GALLERY_DIR         = str(_SETTINGS.gallery_dir)
_BUILTIN_GALLERY_DIR = str(_SETTINGS.builtin_gallery_dir)
_EXAMPLES_DIR        = str(_SETTINGS.examples_dir)


class GalleryItem(BaseModel):
	id:          str
	title:       str
	description: str            = ""
	category:    str            = "general"
	tags:        List[str]      = []
	workflow:    Dict[str, Any] = {}
	author:      str            = "system"
	created_at:  float          = 0.0
	metadata:    Dict[str, Any] = {}


class GalleryManager:
	"""Manages a local gallery of shareable workflow templates."""

	def __init__(self, gallery_dir: str = _GALLERY_DIR, seed_dirs: Optional[List[str]] = None):
		self._dir       = gallery_dir
		self._seed_dirs = [d for d in (seed_dirs or [_BUILTIN_GALLERY_DIR, _EXAMPLES_DIR]) if d]
		self._items: Dict[str, GalleryItem] = {}

	def initialize(self):
		os.makedirs(self._dir, exist_ok=True)
		self._load()
		if not self._items:
			self._seed_from_sources()
		else:
			self._sync_builtin_items()

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

	def _seed_from_sources(self):
		for source_dir in self._seed_dirs:
			if not os.path.isdir(source_dir):
				continue
			for fname in sorted(os.listdir(source_dir)):
				if not fname.endswith(".json"):
					continue
				try:
					with open(os.path.join(source_dir, fname), encoding="utf-8") as f:
						data = json.load(f)
					if isinstance(data, dict) and "workflow" in data and "id" in data:
						item = GalleryItem(**data)
					else:
						name  = fname.replace(".json", "").replace("-", " ").replace("_", " ").title()
						item  = GalleryItem(
							id          = str(uuid.uuid4())[:8],
							title       = name,
							description = f"Example workflow: {name}",
							category    = "examples",
							tags        = ["example"],
							workflow    = data if isinstance(data, dict) else {},
							author      = "system",
							created_at  = time.time(),
						)
					self._items[item.id] = item
					self._save_item(item)
				except Exception:
					pass

	def _sync_builtin_items(self):
		"""Import missing built-in gallery items without duplicating older raw examples.

		This keeps existing runtime galleries up to date when we add a new built-in
		template file with an explicit stable id, while avoiding repeated imports for
		seed files that rely on auto-generated ids."""
		for source_dir in self._seed_dirs:
			if not os.path.isdir(source_dir):
				continue
			for fname in sorted(os.listdir(source_dir)):
				if not fname.endswith(".json"):
					continue
				try:
					with open(os.path.join(source_dir, fname), encoding="utf-8") as f:
						data = json.load(f)
					if not (isinstance(data, dict) and "workflow" in data and "id" in data):
						continue
					item = GalleryItem(**data)
					if item.id in self._items:
						continue
					self._items[item.id] = item
					self._save_item(item)
				except Exception:
					pass

	# ── Public API ────────────────────────────────────────────

	def _decorate_item(self, item: GalleryItem) -> Dict[str, Any]:
		data = item.model_dump()
		metadata = data.get("metadata", {}) or {}
		source = metadata.get("source", {}) or {}
		source_kind = str(source.get("type", "") or "").strip().lower()
		namespace = str(source.get("namespace", "") or "").strip().lower()
		slug = str(source.get("slug", "") or "").strip().lower()
		namespace_slug = str(source.get("namespace_slug", "") or "").strip()
		ref_name = str(source.get("ref", "") or source.get("active_ref", "") or "").strip()
		commit_id = str(source.get("commit_id", "") or "").strip()
		asset_path = str(source.get("asset_path", "") or "").strip()
		public_source = bool(source.get("is_public")) or str(source.get("visibility", "") or "").strip().lower() == "public"
		repo_backed = bool(namespace_slug or (namespace and slug))
		if commit_id:
			version_label = f"snapshot {commit_id[:8]}"
		elif ref_name:
			version_label = ref_name
		elif source_kind == "canvas":
			version_label = "canvas"
		else:
			version_label = "unversioned"
		if namespace and slug:
			source_label = f"{namespace}/{slug}"
		elif namespace_slug:
			source_label = namespace_slug
		else:
			source_label = ""
		if source_label and ref_name:
			source_label = f"{source_label} @ {ref_name}"
		elif source_label and commit_id:
			source_label = f"{source_label} @ {commit_id[:8]}"
		elif not source_label and commit_id:
			source_label = f"snapshot {commit_id[:8]}"
		elif not source_label and source_kind == "canvas":
			source_label = "current canvas"
		if asset_path:
			source_label = f"{source_label} · {asset_path}" if source_label else asset_path
		explicit_featured = bool(metadata.get("featured"))
		curated = explicit_featured or public_source or str(data.get("author", "") or "").strip().lower() == "system"
		featured = explicit_featured or (public_source and repo_backed)
		data["provenance"] = {
			"source_kind": source_kind or "gallery",
			"source_label": source_label,
			"version_label": version_label,
			"repo_backed": repo_backed,
			"public_source": public_source,
			"featured": featured,
			"curated": curated,
			"asset_path": asset_path or "workflow.json",
			"namespace_slug": source_label.split(" · ")[0] if source_label else "",
		}
		return data

	def _sort_key(self, item: Dict[str, Any]):
		provenance = item.get("provenance", {}) or {}
		return (
			0 if provenance.get("featured") else 1,
			0 if provenance.get("curated") else 1,
			0 if provenance.get("repo_backed") else 1,
			-float(item.get("created_at") or 0.0),
			str(item.get("title", "") or "").lower(),
		)

	def list(self, category: str = None, tags: List[str] = None,
	         search: str = None, author: str = None) -> List[dict]:
		results = list(self._items.values())
		if category:
			results = [i for i in results if i.category == category]
		if tags:
			results = [i for i in results if set(tags) & set(i.tags)]
		if author:
			wanted = str(author).strip().lower()
			results = [i for i in results if str(i.author or "").strip().lower() == wanted]
		if search:
			q = search.lower()
			matched = []
			for item in results:
				decorated = self._decorate_item(item)
				haystack = " ".join([
					str(decorated.get("title", "") or ""),
					str(decorated.get("description", "") or ""),
					str(decorated.get("author", "") or ""),
					str((decorated.get("provenance", {}) or {}).get("source_label", "") or ""),
					str((decorated.get("provenance", {}) or {}).get("version_label", "") or ""),
					" ".join(str(tag) for tag in (decorated.get("tags", []) or [])),
				]).lower()
				if q in haystack:
					matched.append(item)
			results = matched
		decorated_results = [self._decorate_item(i) for i in results]
		decorated_results.sort(key=self._sort_key)
		for item in decorated_results:
			item.pop("workflow", None)
		return decorated_results

	def get(self, id: str) -> Optional[dict]:
		item = self._items.get(id)
		return self._decorate_item(item) if item else None

	def publish(self, workflow: dict, title: str, description: str = "",
	            category: str = "community", tags: List[str] = None,
	            author: str = "user", metadata: Optional[Dict[str, Any]] = None) -> dict:
		item = GalleryItem(
			id          = str(uuid.uuid4())[:8],
			title       = title,
			description = description,
			category    = category,
			tags        = tags or [],
			workflow    = workflow,
			author      = author,
			created_at  = time.time(),
			metadata    = metadata or {},
		)
		self._items[item.id] = item
		self._save_item(item)
		return self._decorate_item(item)

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
		author:   Optional[str]  = None

	class GetReq(BaseModel):
		id: str

	class PublishReq(BaseModel):
		workflow_name: Optional[str] = None
		workflow:      Optional[Dict[str, Any]] = None
		title:         str = "Untitled"
		description:   str = ""
		category:      str = "community"
		tags:          List[str] = []
		author:        str = "user"
		metadata:      Dict[str, Any] = {}

	class RemoveReq(BaseModel):
		id: str

	@app.post("/gallery/list")
	async def gallery_list(req: ListReq):
		return mgr.list(category=req.category, tags=req.tags, search=req.search, author=req.author)

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
		                   category=req.category, tags=req.tags,
		                   author=req.author, metadata=req.metadata)

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
