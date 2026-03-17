# credentials.py - file-backed credential / secret store
# Values are referenced in node fields as ${CRED_NAME}.

import json
import os
import re
import threading
from typing import Dict, List, Optional

_CREDS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "credentials.json")
_lock       = threading.Lock()


def _load() -> Dict[str, str]:
	if not os.path.exists(_CREDS_FILE):
		return {}
	try:
		with open(_CREDS_FILE, "r", encoding="utf-8") as f:
			return json.load(f)
	except Exception:
		return {}


def _save(data: Dict[str, str]) -> None:
	with open(_CREDS_FILE, "w", encoding="utf-8") as f:
		json.dump(data, f, indent=2)


def list_names() -> List[str]:
	with _lock:
		return sorted(_load().keys())


def get(name: str) -> Optional[str]:
	with _lock:
		return _load().get(name)


def set(name: str, value: str) -> None:
	with _lock:
		data = _load()
		data[name] = value
		_save(data)


def delete(name: str) -> bool:
	with _lock:
		data = _load()
		if name not in data:
			return False
		del data[name]
		_save(data)
		return True


def resolve(value: str) -> str:
	"""Replace ${CRED_NAME} references with stored credential values."""
	if not isinstance(value, str) or "${" not in value:
		return value
	data = _load()
	return re.sub(r'\$\{([^}]+)\}', lambda m: data.get(m.group(1), m.group(0)), value)


def resolve_dict(d: dict) -> dict:
	"""Recursively resolve ${CRED_NAME} references in a dict."""
	if not isinstance(d, dict):
		return d
	result = {}
	for k, v in d.items():
		if isinstance(v, str):
			result[k] = resolve(v)
		elif isinstance(v, dict):
			result[k] = resolve_dict(v)
		elif isinstance(v, list):
			result[k] = [resolve(i) if isinstance(i, str) else i for i in v]
		else:
			result[k] = v
	return result
