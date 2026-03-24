# memory — Persistent Agent Memory
#
# ChromaDB-backed long-term memory for the console agent.
# Stores conversation summaries, user preferences, and project knowledge
# that persist across sessions.

import json
import os
import time
import uuid

from   datetime  import datetime
from   pydantic  import BaseModel, Field
from   typing    import Any, Dict, List, Optional

from   utils     import log_print


_STORAGE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "storage", "memory")


# =============================================================================
# DATA MODELS
# =============================================================================

class MemoryEntry(BaseModel):
	"""A single memory entry."""
	id        : str            = Field(default_factory=lambda: f"mem_{uuid.uuid4().hex[:12]}")
	type      : str            = "general"    # general, conversation, preference, project, fact
	content   : str            = ""
	metadata  : Dict[str, Any] = Field(default_factory=dict)
	timestamp : str            = Field(default_factory=lambda: datetime.now().isoformat())
	importance: float          = 0.5          # 0.0–1.0 relevance scoring
	session_id: Optional[str]  = None


class MemorySearchResult(BaseModel):
	"""A memory search result with relevance score."""
	entry    : MemoryEntry
	score    : float = 0.0


# =============================================================================
# MEMORY STORE
# =============================================================================

class MemoryStore:
	"""Persistent vector memory backed by ChromaDB.
	Falls back to a simple JSON file store if ChromaDB is unavailable."""

	def __init__(self, storage_dir: str = _STORAGE_DIR, collection_name: str = "agent_memory"):
		self._storage_dir    = storage_dir
		self._collection_name = collection_name
		self._backend        = None   # "chromadb" or "json"
		self._collection     = None   # ChromaDB collection
		self._json_store     = []     # Fallback JSON entries
		self._json_path      = os.path.join(storage_dir, f"{collection_name}.json")
		self._initialized    = False

	def initialize(self):
		"""Initialize the memory store. Tries ChromaDB first, falls back to JSON."""
		os.makedirs(self._storage_dir, exist_ok=True)

		# Try ChromaDB
		try:
			import chromadb
			client = chromadb.PersistentClient(path=os.path.join(self._storage_dir, "chromadb"))
			self._collection = client.get_or_create_collection(
				name=self._collection_name,
				metadata={"hnsw:space": "cosine"},
			)
			self._backend = "chromadb"
			count = self._collection.count()
			log_print(f"Memory store initialized (ChromaDB, {count} entries)")
		except Exception as e:
			log_print(f"ChromaDB unavailable ({e}), falling back to JSON memory store")
			self._backend = "json"
			self._load_json()
			log_print(f"Memory store initialized (JSON, {len(self._json_store)} entries)")

		self._initialized = True

	# ── CRUD ──────────────────────────────────────────────────────

	def add(self, content: str, type: str = "general", metadata: Optional[Dict[str, Any]] = None,
			importance: float = 0.5, session_id: Optional[str] = None) -> str:
		"""Add a memory entry. Returns the entry ID."""
		self._ensure_init()
		entry = MemoryEntry(
			type       = type,
			content    = content,
			metadata   = metadata or {},
			importance = importance,
			session_id = session_id,
		)

		if self._backend == "chromadb":
			self._collection.add(
				ids       = [entry.id],
				documents = [content],
				metadatas = [{
					"type":       entry.type,
					"importance": entry.importance,
					"timestamp":  entry.timestamp,
					"session_id": entry.session_id or "",
					**{k: str(v) for k, v in (metadata or {}).items()},
				}],
			)
		else:
			self._json_store.append(entry.model_dump())
			self._save_json()

		return entry.id

	def search(self, query: str, n_results: int = 5, type_filter: Optional[str] = None) -> List[MemorySearchResult]:
		"""Search memories by semantic similarity (ChromaDB) or keyword (JSON fallback)."""
		self._ensure_init()

		if self._backend == "chromadb":
			where = {"type": type_filter} if type_filter else None
			try:
				results = self._collection.query(
					query_texts = [query],
					n_results   = min(n_results, max(self._collection.count(), 1)),
					where       = where,
				)
			except Exception:
				return []

			entries = []
			if results and results["ids"] and results["ids"][0]:
				for i, doc_id in enumerate(results["ids"][0]):
					doc      = results["documents"][0][i] if results["documents"] else ""
					meta     = results["metadatas"][0][i] if results["metadatas"] else {}
					distance = results["distances"][0][i] if results["distances"] else 1.0
					score    = 1.0 - distance  # cosine distance → similarity

					entries.append(MemorySearchResult(
						entry = MemoryEntry(
							id         = doc_id,
							type       = meta.get("type", "general"),
							content    = doc,
							metadata   = {k: v for k, v in meta.items() if k not in ("type", "importance", "timestamp", "session_id")},
							timestamp  = meta.get("timestamp", ""),
							importance = float(meta.get("importance", 0.5)),
							session_id = meta.get("session_id") or None,
						),
						score = score,
					))
			return entries
		else:
			# JSON fallback: simple keyword matching
			query_lower = query.lower()
			scored = []
			for raw in self._json_store:
				entry = MemoryEntry(**raw)
				if type_filter and entry.type != type_filter:
					continue
				content_lower = entry.content.lower()
				# Simple scoring: count keyword matches
				words = query_lower.split()
				hits  = sum(1 for w in words if w in content_lower)
				if hits > 0:
					score = hits / len(words) * entry.importance
					scored.append(MemorySearchResult(entry=entry, score=score))
			scored.sort(key=lambda x: x.score, reverse=True)
			return scored[:n_results]

	def get_recent(self, n: int = 10, type_filter: Optional[str] = None) -> List[MemoryEntry]:
		"""Get the most recent memories."""
		self._ensure_init()

		if self._backend == "chromadb":
			where = {"type": type_filter} if type_filter else None
			try:
				results = self._collection.get(
					where  = where,
					limit  = n,
				)
			except Exception:
				return []

			entries = []
			if results and results["ids"]:
				for i, doc_id in enumerate(results["ids"]):
					doc  = results["documents"][i] if results["documents"] else ""
					meta = results["metadatas"][i] if results["metadatas"] else {}
					entries.append(MemoryEntry(
						id         = doc_id,
						type       = meta.get("type", "general"),
						content    = doc,
						metadata   = {k: v for k, v in meta.items() if k not in ("type", "importance", "timestamp", "session_id")},
						timestamp  = meta.get("timestamp", ""),
						importance = float(meta.get("importance", 0.5)),
						session_id = meta.get("session_id") or None,
					))
			# Sort by timestamp descending
			entries.sort(key=lambda e: e.timestamp, reverse=True)
			return entries[:n]
		else:
			entries = [MemoryEntry(**raw) for raw in self._json_store]
			if type_filter:
				entries = [e for e in entries if e.type == type_filter]
			entries.sort(key=lambda e: e.timestamp, reverse=True)
			return entries[:n]

	def delete(self, memory_id: str) -> bool:
		"""Delete a memory by ID."""
		self._ensure_init()

		if self._backend == "chromadb":
			try:
				self._collection.delete(ids=[memory_id])
				return True
			except Exception:
				return False
		else:
			before = len(self._json_store)
			self._json_store = [e for e in self._json_store if e.get("id") != memory_id]
			if len(self._json_store) < before:
				self._save_json()
				return True
			return False

	def clear(self):
		"""Clear all memories."""
		self._ensure_init()
		if self._backend == "chromadb":
			import chromadb
			client = chromadb.PersistentClient(path=os.path.join(self._storage_dir, "chromadb"))
			client.delete_collection(self._collection_name)
			self._collection = client.create_collection(
				name=self._collection_name,
				metadata={"hnsw:space": "cosine"},
			)
		else:
			self._json_store = []
			self._save_json()

	def count(self) -> int:
		"""Return total number of stored memories."""
		self._ensure_init()
		if self._backend == "chromadb":
			return self._collection.count()
		return len(self._json_store)

	def get_stats(self) -> dict:
		"""Return memory store statistics."""
		self._ensure_init()
		return {
			"backend":    self._backend,
			"total":      self.count(),
			"storage_dir": self._storage_dir,
		}

	# ── Conversation Summarization ────────────────────────────────

	def summarize_and_store(self, messages: List[dict], session_id: str,
							summary: Optional[str] = None) -> str:
		"""Store a conversation summary as a memory.
		If no summary provided, creates one from the messages."""
		if not summary:
			# Simple extractive summary: take user messages
			user_msgs = [m["content"] for m in messages if m.get("role") == "user"]
			asst_msgs = [m["content"] for m in messages if m.get("role") == "assistant"]
			topics = "; ".join(msg[:100] for msg in user_msgs[:5])
			summary = f"Conversation topics: {topics}"
			if asst_msgs:
				summary += f"\nKey responses: {asst_msgs[-1][:200]}"

		return self.add(
			content    = summary,
			type       = "conversation",
			metadata   = {"message_count": len(messages)},
			importance = 0.6,
			session_id = session_id,
		)

	# ── Context Retrieval for Agent ───────────────────────────────

	def get_context_for_query(self, query: str, max_entries: int = 3) -> str:
		"""Retrieve relevant memories formatted as context for the agent."""
		results = self.search(query, n_results=max_entries)
		if not results:
			return ""

		parts = ["[Relevant memories from previous sessions]"]
		for r in results:
			if r.score < 0.1:
				continue
			entry = r.entry
			age   = ""
			try:
				ts   = datetime.fromisoformat(entry.timestamp)
				diff = datetime.now() - ts
				if diff.days > 0:
					age = f" ({diff.days}d ago)"
				elif diff.seconds > 3600:
					age = f" ({diff.seconds // 3600}h ago)"
			except Exception:
				pass
			parts.append(f"- [{entry.type}]{age}: {entry.content[:300]}")

		return "\n".join(parts) if len(parts) > 1 else ""

	# ── Internal ──────────────────────────────────────────────────

	def _ensure_init(self):
		if not self._initialized:
			self.initialize()

	def _load_json(self):
		if os.path.exists(self._json_path):
			try:
				with open(self._json_path, "r") as f:
					self._json_store = json.load(f)
			except Exception:
				self._json_store = []
		else:
			self._json_store = []

	def _save_json(self):
		os.makedirs(os.path.dirname(self._json_path), exist_ok=True)
		with open(self._json_path, "w") as f:
			json.dump(self._json_store, f, indent=2)


# =============================================================================
# PER-USER MEMORY DATABASE MANAGER
# =============================================================================

_USER_MEMORY_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "storage", "user_memory")


class UserMemoryDB:
	"""Resolves user identities to per-user SQLite memory database paths.

	Framework-agnostic: only manages file paths and cleanup.  The caller
	(agno, langchain, etc.) creates its own DB wrapper around the path.

	File layout inside ``storage_dir``::

	    user_{user_id}.db      — authenticated users (shared across web + channels)
	    anon_{channel_key}.db  — anonymous channel users (no Numel account linked)
	    guest_{session_id}.db  — web guest sessions (ephemeral)
	"""

	def __init__(self, storage_dir: str = _USER_MEMORY_DIR):
		self._dir = storage_dir
		os.makedirs(storage_dir, exist_ok=True)

	# ── Path resolution ───────────────────────────────────────────

	def get_db_path(self, user_id: str, is_guest: bool = False) -> str:
		"""Return the SQLite db path for a given identity.

		Parameters
		----------
		user_id : str
		    For authenticated users: the Numel ``user.id``.
		    For anonymous channel users: ``"anon_{channel_type}_{sender_id}"``.
		    For guests: a session-scoped identifier.
		is_guest : bool
		    If True, the db is treated as ephemeral and subject to cleanup.
		"""
		if is_guest:
			safe = self._safe_name(user_id)
			return os.path.join(self._dir, f"guest_{safe}.db")
		safe = self._safe_name(user_id)
		# user_id for authenticated users is typically a UUID; for anon it
		# already starts with "anon_".
		if safe.startswith("anon_"):
			return os.path.join(self._dir, f"{safe}.db")
		return os.path.join(self._dir, f"user_{safe}.db")

	# ── Cleanup ───────────────────────────────────────────────────

	def cleanup_guest(self, session_id: str):
		"""Delete a specific guest db file."""
		path = self.get_db_path(session_id, is_guest=True)
		self._remove(path)

	def cleanup_expired_guests(self, max_age_s: float = 86400):
		"""Remove ``guest_*.db`` files older than *max_age_s* seconds."""
		now = time.time()
		for fname in os.listdir(self._dir):
			if not fname.startswith("guest_") or not fname.endswith(".db"):
				continue
			fpath = os.path.join(self._dir, fname)
			try:
				age = now - os.path.getmtime(fpath)
				if age > max_age_s:
					self._remove(fpath)
					log_print(f"UserMemoryDB: cleaned up expired guest db {fname}")
			except OSError:
				pass

	# ── Helpers ───────────────────────────────────────────────────

	@staticmethod
	def _safe_name(raw: str) -> str:
		"""Sanitize an identifier for use as a filename component."""
		return "".join(c if (c.isalnum() or c in "-_") else "_" for c in raw)

	@staticmethod
	def _remove(path: str):
		"""Remove a db file and its WAL/SHM companions."""
		for suffix in ("", "-wal", "-shm"):
			try:
				os.remove(path + suffix)
			except OSError:
				pass
