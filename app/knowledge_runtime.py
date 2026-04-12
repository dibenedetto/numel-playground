from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


_CONTENT_KEYS = ("content", "text", "body", "message", "value", "input")
_SKIP_METADATA_KEYS = {
	"content",
	"text",
	"body",
	"message",
	"value",
	"input",
	"filename",
	"name",
	"title",
	"subject",
	"metadata",
	"path",
	"file",
}


def _ensure_bytes_content(value: Any) -> bytes:
	if value is None:
		return b""
	if isinstance(value, bytes):
		return value
	if isinstance(value, bytearray):
		return bytes(value)
	if isinstance(value, (dict, list, tuple)):
		return json.dumps(value, ensure_ascii=False, indent=2).encode("utf-8")
	return str(value).encode("utf-8")


def _sanitize_filename(value: Optional[str], *, default: str, binary: bool = False) -> str:
	name = str(value or "").strip()
	if not name:
		name = default
	name = name.replace("\\", "/").split("/")[-1].strip() or default
	if not Path(name).suffix:
		name += ".bin" if binary else ".txt"
	return name


def _derive_metadata(item: Dict[str, Any], base_metadata: Dict[str, Any]) -> Dict[str, Any]:
	metadata = dict(base_metadata)
	item_metadata = item.get("metadata")
	if isinstance(item_metadata, dict):
		metadata.update(item_metadata)
	for key, value in item.items():
		if key in _SKIP_METADATA_KEYS or value is None:
			continue
		if isinstance(value, (str, int, float, bool)):
			metadata[key] = value
	return metadata


def _iter_knowledge_items(value: Any) -> Iterable[Any]:
	if isinstance(value, dict) and isinstance(value.get("items"), list):
		return value["items"]
	if isinstance(value, list):
		return value
	return [value]


def normalize_knowledge_inputs(
	value: Any,
	*,
	filename: Optional[str] = None,
	metadata: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
	"""Normalize workflow/toolkit input into backend-ready knowledge items.

	Each returned item contains:
	- filename: str
	- content: bytes
	- metadata: dict
	"""
	base_metadata = dict(metadata or {})
	result: List[Dict[str, Any]] = []

	for idx, item in enumerate(_iter_knowledge_items(value), start=1):
		default_name = f"knowledge_item_{idx}.txt"

		if item is None:
			continue

		if isinstance(item, (str, bytes, bytearray)):
			binary = isinstance(item, (bytes, bytearray))
			result.append(
				{
					"filename": _sanitize_filename(filename, default=default_name, binary=binary),
					"content": _ensure_bytes_content(item),
					"metadata": dict(base_metadata),
				}
			)
			continue

		if isinstance(item, Path):
			content = item.read_bytes()
			metadata_out = dict(base_metadata)
			metadata_out.setdefault("path", str(item))
			result.append(
				{
					"filename": _sanitize_filename(filename or item.name, default=item.name, binary=True),
					"content": content,
					"metadata": metadata_out,
				}
			)
			continue

		if isinstance(item, dict):
			path_value = item.get("path")
			if path_value:
				path = Path(str(path_value))
				content = path.read_bytes()
				metadata_out = _derive_metadata(item, base_metadata)
				metadata_out.setdefault("path", str(path))
				result.append(
					{
						"filename": _sanitize_filename(
							item.get("filename") or path.name or filename,
							default=path.name or default_name,
							binary=True,
						),
						"content": content,
						"metadata": metadata_out,
					}
				)
				continue

			content_value = None
			for key in _CONTENT_KEYS:
				if item.get(key) is not None:
					content_value = item.get(key)
					break
			if content_value is None:
				content_value = item

			filename_value = (
				item.get("filename")
				or item.get("name")
				or item.get("title")
				or item.get("subject")
				or filename
			)
			result.append(
				{
					"filename": _sanitize_filename(filename_value, default=default_name),
					"content": _ensure_bytes_content(content_value),
					"metadata": _derive_metadata(item, base_metadata),
				}
			)
			continue

		result.append(
			{
				"filename": _sanitize_filename(filename, default=default_name),
				"content": _ensure_bytes_content(item),
				"metadata": dict(base_metadata),
			}
		)

	return result


def serialize_knowledge_documents(documents: Optional[Iterable[Any]]) -> List[Dict[str, Any]]:
	items: List[Dict[str, Any]] = []
	for doc in documents or []:
		items.append(
			{
				"id": getattr(doc, "id", None),
				"name": getattr(doc, "name", None),
				"content": getattr(doc, "content", None),
				"metadata": getattr(doc, "meta_data", None) or {},
				"score": getattr(doc, "reranking_score", None),
				"content_id": getattr(doc, "content_id", None),
				"content_origin": getattr(doc, "content_origin", None),
				"size": getattr(doc, "size", None),
			}
		)
	return items
