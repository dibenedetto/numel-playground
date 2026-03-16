# gallery — Workflow Gallery / Marketplace
#
# Browse, share, and install workflow templates.
# Supports local gallery (filesystem) and remote gallery (URL-based).

import json
import os
import time
import uuid

from   datetime  import datetime
from   fastapi   import FastAPI, UploadFile, File, Form
from   pydantic  import BaseModel, Field
from   typing    import Any, Dict, List, Optional

from   utils     import log_print


_GALLERY_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "gallery")


# =============================================================================
# DATA MODELS
# =============================================================================

class GalleryItem(BaseModel):
	"""A workflow template in the gallery."""
	id          : str            = Field(default_factory=lambda: f"gal_{uuid.uuid4().hex[:8]}")
	name        : str            = ""
	description : str            = ""
	author      : str            = ""
	version     : str            = "1.0.0"
	tags        : List[str]      = Field(default_factory=list)
	category    : str            = "general"     # general, media, agents, automation, data, ml
	thumbnail   : Optional[str]  = None          # Base64 or URL to preview image
	workflow    : Dict[str, Any] = Field(default_factory=dict)  # Compact workflow JSON
	node_count  : int            = 0
	edge_count  : int            = 0
	created     : str            = Field(default_factory=lambda: datetime.now().isoformat())
	updated     : str            = Field(default_factory=lambda: datetime.now().isoformat())
	downloads   : int            = 0
	rating      : float          = 0.0
	featured    : bool           = False


class GalleryIndex(BaseModel):
	"""Gallery index file."""
	version : str             = "1.0.0"
	items   : List[GalleryItem] = Field(default_factory=list)


# =============================================================================
# GALLERY MANAGER
# =============================================================================

class GalleryManager:
	"""Manages the local workflow gallery."""

	def __init__(self, gallery_dir: str = _GALLERY_DIR):
		self._gallery_dir = gallery_dir
		self._index_path  = os.path.join(gallery_dir, "index.json")
		self._index       = GalleryIndex()

	def initialize(self):
		"""Load or create the gallery index."""
		os.makedirs(self._gallery_dir, exist_ok=True)

		if os.path.exists(self._index_path):
			try:
				with open(self._index_path) as f:
					data = json.load(f)
				self._index = GalleryIndex(**data)
			except Exception as e:
				log_print(f"Failed to load gallery index: {e}")
				self._index = GalleryIndex()
		else:
			self._seed_gallery()

		log_print(f"Gallery initialized ({len(self._index.items)} items)")

	# ── CRUD ──────────────────────────────────────────────────────

	def list(self, category: Optional[str] = None, tags: Optional[List[str]] = None,
			 search: Optional[str] = None, featured_only: bool = False) -> List[dict]:
		"""List gallery items with optional filtering."""
		items = self._index.items

		if category:
			items = [i for i in items if i.category == category]
		if tags:
			tag_set = set(tags)
			items = [i for i in items if tag_set.intersection(i.tags)]
		if featured_only:
			items = [i for i in items if i.featured]
		if search:
			search_lower = search.lower()
			items = [i for i in items if (
				search_lower in i.name.lower() or
				search_lower in i.description.lower() or
				any(search_lower in t.lower() for t in i.tags)
			)]

		# Return without full workflow data (listing)
		return [
			{
				"id":          i.id,
				"name":        i.name,
				"description": i.description,
				"author":      i.author,
				"version":     i.version,
				"tags":        i.tags,
				"category":    i.category,
				"thumbnail":   i.thumbnail,
				"node_count":  i.node_count,
				"edge_count":  i.edge_count,
				"created":     i.created,
				"updated":     i.updated,
				"downloads":   i.downloads,
				"rating":      i.rating,
				"featured":    i.featured,
			}
			for i in items
		]

	def get(self, item_id: str) -> Optional[dict]:
		"""Get a gallery item with full workflow data."""
		for item in self._index.items:
			if item.id == item_id:
				item.downloads += 1
				self._save()
				return item.model_dump()
		return None

	def publish(self, name: str, description: str, workflow: Dict[str, Any],
				author: str = "", tags: Optional[List[str]] = None,
				category: str = "general", thumbnail: Optional[str] = None) -> str:
		"""Publish a workflow to the gallery. Returns the item ID."""
		nodes = workflow.get("nodes", [])
		edges = workflow.get("edges", [])

		item = GalleryItem(
			name        = name,
			description = description,
			author      = author,
			tags        = tags or [],
			category    = category,
			thumbnail   = thumbnail,
			workflow    = workflow,
			node_count  = len(nodes),
			edge_count  = len(edges),
		)

		# Check for duplicates by name
		for i, existing in enumerate(self._index.items):
			if existing.name == name and existing.author == author:
				item.id = existing.id
				item.created = existing.created
				item.downloads = existing.downloads
				item.rating = existing.rating
				self._index.items[i] = item
				self._save()
				return item.id

		self._index.items.append(item)
		self._save()
		return item.id

	def remove(self, item_id: str) -> bool:
		"""Remove a gallery item."""
		before = len(self._index.items)
		self._index.items = [i for i in self._index.items if i.id != item_id]
		if len(self._index.items) < before:
			self._save()
			return True
		return False

	def import_from_file(self, filepath: str, author: str = "") -> Optional[str]:
		"""Import a workflow JSON file into the gallery."""
		try:
			with open(filepath) as f:
				data = json.load(f)

			name = data.get("name") or os.path.splitext(os.path.basename(filepath))[0]
			desc = data.get("description", "")

			# Detect category from node types
			node_types = [n.get("type", "") for n in data.get("nodes", [])]
			category = self._detect_category(node_types)

			tags = self._detect_tags(node_types)

			return self.publish(
				name        = name,
				description = desc,
				workflow    = data,
				author      = author,
				tags        = tags,
				category    = category,
			)
		except Exception as e:
			log_print(f"Gallery import failed: {e}")
			return None

	def get_categories(self) -> List[dict]:
		"""List all categories with counts."""
		counts = {}
		for item in self._index.items:
			counts[item.category] = counts.get(item.category, 0) + 1
		return [{"category": k, "count": v} for k, v in sorted(counts.items())]

	def get_tags(self) -> List[str]:
		"""List all unique tags."""
		tags = set()
		for item in self._index.items:
			tags.update(item.tags)
		return sorted(tags)

	# ── Seed ──────────────────────────────────────────────────────

	def _seed_gallery(self):
		"""Seed gallery from examples/ directory."""
		examples_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "examples")
		if not os.path.isdir(examples_dir):
			self._save()
			return

		for fname in sorted(os.listdir(examples_dir)):
			if not fname.endswith(".json"):
				continue
			filepath = os.path.join(examples_dir, fname)
			self.import_from_file(filepath, author="Numel Team")

		log_print(f"Gallery seeded with {len(self._index.items)} items from examples/")
		self._save()

	# ── Helpers ───────────────────────────────────────────────────

	def _detect_category(self, node_types: List[str]) -> str:
		"""Detect workflow category from node types."""
		type_set = set(node_types)
		if type_set & {"browser_source_flow", "stream_display_flow", "computer_vision_flow"}:
			return "media"
		if type_set & {"agent_flow"}:
			return "agents"
		if type_set & {"event_listener_flow", "loop_start_flow"}:
			return "automation"
		if type_set & {"transform_flow"}:
			return "data"
		return "general"

	def _detect_tags(self, node_types: List[str]) -> List[str]:
		"""Auto-detect tags from node types."""
		tags = set()
		type_set = set(node_types)
		if "agent_flow" in type_set:
			tags.add("agent")
		if "browser_source_flow" in type_set:
			tags.add("media")
		if "computer_vision_flow" in type_set:
			tags.add("vision")
		if "stream_display_flow" in type_set:
			tags.add("display")
		if "loop_start_flow" in type_set:
			tags.add("loop")
		if "event_listener_flow" in type_set:
			tags.add("events")
		if "transform_flow" in type_set:
			tags.add("transform")
		if "for_each_flow" in type_set:
			tags.add("iteration")
		return sorted(tags)

	def _save(self):
		"""Save the gallery index to disk."""
		os.makedirs(self._gallery_dir, exist_ok=True)
		with open(self._index_path, "w") as f:
			json.dump(self._index.model_dump(), f, indent=2)


# =============================================================================
# API ROUTES
# =============================================================================

class GallerySearchRequest(BaseModel):
	category     : Optional[str]       = None
	tags         : Optional[List[str]] = None
	search       : Optional[str]       = None
	featured_only: bool                = False

class GalleryPublishRequest(BaseModel):
	name         : str
	description  : str          = ""
	workflow     : Dict[str, Any]
	author       : str          = ""
	tags         : List[str]    = []
	category     : str          = "general"
	thumbnail    : Optional[str] = None


def setup_gallery_api(app: FastAPI, gallery: GalleryManager):
	"""Register gallery API routes."""

	@app.post("/gallery/list")
	async def gallery_list(request: GallerySearchRequest = GallerySearchRequest()):
		return gallery.list(
			category      = request.category,
			tags          = request.tags,
			search        = request.search,
			featured_only = request.featured_only,
		)

	@app.post("/gallery/get")
	async def gallery_get(request: dict):
		item_id = request.get("id", "")
		item = gallery.get(item_id)
		if not item:
			return {"error": "not found"}
		return item

	@app.post("/gallery/publish")
	async def gallery_publish(request: GalleryPublishRequest):
		item_id = gallery.publish(
			name        = request.name,
			description = request.description,
			workflow    = request.workflow,
			author      = request.author,
			tags        = request.tags,
			category    = request.category,
			thumbnail   = request.thumbnail,
		)
		return {"id": item_id}

	@app.post("/gallery/remove")
	async def gallery_remove(request: dict):
		item_id = request.get("id", "")
		return {"removed": gallery.remove(item_id)}

	@app.post("/gallery/categories")
	async def gallery_categories():
		return gallery.get_categories()

	@app.post("/gallery/tags")
	async def gallery_tags():
		return gallery.get_tags()
