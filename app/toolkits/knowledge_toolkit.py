# knowledge_toolkit.py

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from backend_factory import build_knowledge_runtime
from knowledge_runtime import normalize_knowledge_inputs
from schema import (
	ContentDBConfig,
	DEFAULT_BACKEND_NAME,
	DEFAULT_CONTENT_DB_URL,
	DEFAULT_EMBEDDING_NAME,
	DEFAULT_EMBEDDING_SOURCE,
	DEFAULT_INDEX_DB_URL,
	DEFAULT_KNOWLEDGE_MANAGER_MAX_RESULTS,
	DEFAULT_INDEX_DB_SEARCH_TYPE,
	EmbeddingConfig,
	IndexDBConfig,
	KnowledgeManagerConfig,
)


class KnowledgeToolkit:
	"""Toolkit for working with a shared knowledge base (RAG store).

	This toolkit wraps a Knowledge Manager configuration and exposes a small set of
	high-level operations for assistants:
	- add_text: ingest one text document
	- add_file: ingest one local file
	- add_items: ingest multiple normalized items
	- search: query the knowledge base
	- list_contents: inspect stored content ids and metadata
	- remove_contents: delete stored content by id

	Constructor args define where the knowledge base lives and which embedding model
	it should use. The active backend remains an implementation detail behind the
	shared backend dispatch layer."""

	__toolkit__ = True

	def __init__(
		self,
		backend_name: str = DEFAULT_BACKEND_NAME,
		content_db_url: str = DEFAULT_CONTENT_DB_URL,
		index_db_url: str = DEFAULT_INDEX_DB_URL,
		embedding_source: str = DEFAULT_EMBEDDING_SOURCE,
		embedding_name: str = DEFAULT_EMBEDDING_NAME,
		search_type: str = DEFAULT_INDEX_DB_SEARCH_TYPE,
		max_results: int = DEFAULT_KNOWLEDGE_MANAGER_MAX_RESULTS,
		description: str = "",
	):
		self._backend_name = backend_name
		self._content_db_url = content_db_url
		self._index_db_url = index_db_url
		self._embedding_source = embedding_source
		self._embedding_name = embedding_name
		self._search_type = search_type
		self._max_results = max_results
		self._description = description

		self._backend = None
		self._knowledge = None

	def _ensure_runtime(self):
		if self._backend is not None and self._knowledge is not None:
			return self._backend, self._knowledge

		embedding = EmbeddingConfig(
			source=self._embedding_source,
			name=self._embedding_name,
		)
		index_db = IndexDBConfig(
			url=self._index_db_url,
			search_type=self._search_type,
			embedding=embedding,
		)
		content_db = ContentDBConfig(
			url=self._content_db_url,
		)
		knowledge = KnowledgeManagerConfig(
			query=True,
			update=True,
			description=self._description or None,
			content_db=content_db,
			index_db=index_db,
			max_results=self._max_results,
		)
		self._backend, self._knowledge = build_knowledge_runtime(
			knowledge,
			backend_name=self._backend_name,
		)
		return self._backend, self._knowledge

	async def add_text(
		self,
		text: str,
		filename: str = "note.txt",
		metadata: Optional[Dict[str, Any]] = None,
	) -> Dict[str, Any]:
		"""Add one text item to the knowledge base.

		Args:
			text: Document body to ingest.
			filename: Logical source filename shown in metadata.
			metadata: Optional metadata dict stored with the content.
		"""
		backend, knowledge = self._ensure_runtime()
		items = normalize_knowledge_inputs(text, filename=filename, metadata=metadata)
		ids = await backend.add_contents(knowledge, items)
		return {"ids": ids, "count": len(ids)}

	async def add_file(self, path: str, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
		"""Add one local file into the knowledge base.

		Args:
			path: Local file path to ingest.
			metadata: Optional metadata dict merged into the stored content metadata.
		"""
		path_obj = Path(path)
		backend, knowledge = self._ensure_runtime()
		items = normalize_knowledge_inputs({"path": str(path_obj), "metadata": metadata or {}}, filename=path_obj.name)
		ids = await backend.add_contents(knowledge, items)
		return {"ids": ids, "count": len(ids)}

	async def add_items(
		self,
		items: List[Dict[str, Any]],
		metadata: Optional[Dict[str, Any]] = None,
	) -> Dict[str, Any]:
		"""Add multiple normalized items in one call.

		Each item can contain fields like:
		- content / text / body
		- filename
		- metadata
		- path
		"""
		backend, knowledge = self._ensure_runtime()
		normalized = normalize_knowledge_inputs(items, metadata=metadata)
		ids = await backend.add_contents(knowledge, normalized)
		return {"ids": ids, "count": len(ids)}

	async def search(
		self,
		query: str,
		max_results: Optional[int] = None,
		filters: Optional[Dict[str, Any]] = None,
		search_type: Optional[str] = None,
	) -> List[Dict[str, Any]]:
		"""Search the knowledge base and return matching documents."""
		backend, knowledge = self._ensure_runtime()
		return await backend.search_contents(
			knowledge,
			query=query,
			max_results=max_results or self._max_results,
			filters=filters,
			search_type=search_type or self._search_type,
		)

	async def list_contents(self) -> List[Dict[str, Any]]:
		"""List stored content ids and metadata without performing a semantic search."""
		backend, knowledge = self._ensure_runtime()
		rows = await backend.list_contents(knowledge)
		return [{"id": content_id, "metadata": metadata} for content_id, metadata in rows]

	async def remove_contents(self, ids: List[str]) -> List[bool]:
		"""Remove stored content rows by id."""
		backend, knowledge = self._ensure_runtime()
		return await backend.remove_contents(knowledge, ids)
