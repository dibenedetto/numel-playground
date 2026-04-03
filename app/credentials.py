# credentials.py - file-backed credential / secret store
#
# All JSON config files support ${VAR_NAME} variable substitution.
# Lookup order:
#   1. Credential store (credentials.json)
#   2. Environment variables (os.environ — includes .env via load_dotenv)
#   3. Unchanged (no match)
#
# Use load_json(path) to load any JSON file with variable resolution.

import json
import os
import re
import threading
from typing import Any, Dict, List, Optional

from runtime_settings import get_runtime_settings

_SETTINGS = get_runtime_settings()
_CREDS_FILE = str(_SETTINGS.process_credentials_path)
_lock = threading.Lock()
_VAR_PATTERN = re.compile(r'\$\{([^}]+)\}')


def _load() -> Dict[str, str]:
    if not os.path.exists(_CREDS_FILE):
        return {}
    try:
        with open(_CREDS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save(data: Dict[str, str]) -> None:
    os.makedirs(os.path.dirname(_CREDS_FILE), exist_ok=True)
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


def resolve_with_overrides(value: str, overrides: Optional[Dict[str, Any]] = None) -> str:
    """Resolve ${VAR_NAME} with optional high-priority override values.

    Lookup order:
      1. overrides
      2. Credential store (credentials.json)
      3. Environment variables (os.environ)
      4. Keep the original ${VAR_NAME} unchanged (no match)
    """
    if not isinstance(value, str) or "${" not in value:
        return value
    data = _load()
    override_data = {
        str(key): "" if val is None else str(val)
        for key, val in (overrides or {}).items()
    }

    def _sub(match):
        name = match.group(1)
        if name in override_data:
            return override_data[name]
        if name in data:
            return data[name]
        return os.environ.get(name, match.group(0))

    return _VAR_PATTERN.sub(_sub, value)


def resolve(value: str) -> str:
    """Replace ${VAR_NAME} references with credential or environment variable values.

    Lookup order:
      1. Credential store (credentials.json)
      2. Environment variables (os.environ)
      3. Keep the original ${VAR_NAME} unchanged (no match)
    """
    return resolve_with_overrides(value)


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
            result[k] = _resolve_list(v)
        else:
            result[k] = v
    return result


def _resolve_list(lst: list) -> list:
    """Recursively resolve ${CRED_NAME} references in a list."""
    out = []
    for item in lst:
        if isinstance(item, str):
            out.append(resolve(item))
        elif isinstance(item, dict):
            out.append(resolve_dict(item))
        elif isinstance(item, list):
            out.append(_resolve_list(item))
        else:
            out.append(item)
    return out


def load_json(path: str) -> dict | list:
    """Load a JSON file and resolve all ${CRED_NAME} references in string values."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict):
        return resolve_dict(data)
    if isinstance(data, list):
        return _resolve_list(data)
    return data
