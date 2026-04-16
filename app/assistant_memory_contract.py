from __future__ import annotations

import os

from typing import Any, Dict, Optional

from backend_factory import prepare_chat_memory_db_path
from runtime_settings import get_runtime_settings
from schema import (
	ContentDBConfig,
	DEFAULT_BACKEND_NAME,
	HistoryManagerConfig,
	MemoryManagerConfig,
	ModelConfig,
	SessionManagerConfig,
)


DEFAULT_ASSISTANT_MEMORY_CONFIG: Dict[str, Any] = {
	"backend": True,
	"history_query": True,
	"history_size": 5,
	"session_query": True,
	"session_update": True,
	"session_history": 5,
	"session_prompt": None,
	"memory_query": True,
	"memory_update": False,
	"memory_managed": True,
	"memory_prompt": None,
	"memory_instructions": None,
}


def normalize_assistant_memory_config(memory_cfg: Optional[Dict[str, Any]]) -> Dict[str, Any]:
	raw_cfg = dict(memory_cfg or {})
	normalized = dict(DEFAULT_ASSISTANT_MEMORY_CONFIG)
	for key, value in raw_cfg.items():
		if value is not None:
			normalized[key] = value
	normalized["backend"] = True
	normalized["history_query"] = bool(normalized.get("history_query", True))
	normalized["session_query"] = bool(normalized.get("session_query", True))
	normalized["session_update"] = bool(normalized.get("session_update", True))
	normalized["memory_query"] = bool(normalized.get("memory_query", True))
	normalized["memory_update"] = bool(normalized.get("memory_update", False))
	normalized["memory_managed"] = bool(normalized.get("memory_managed", True))
	normalized["session_history"] = max(1, int(normalized.get("session_history") or 5))
	history_size_value = raw_cfg.get("history_size") if raw_cfg.get("history_size") is not None else normalized["session_history"]
	normalized["history_size"] = max(1, int(history_size_value or normalized["session_history"]))
	return normalized


def resolve_assistant_memory_db_path(
	*,
	user_memory_db=None,
	identity: Optional[str] = None,
	is_guest: bool = False,
	fallback_config_path: Optional[str] = None,
	backend_name: str = DEFAULT_BACKEND_NAME,
) -> Optional[str]:
	if user_memory_db is not None and identity:
		db_path = user_memory_db.get_db_path(identity, is_guest=is_guest)
	elif fallback_config_path:
		db_path = os.path.join(os.path.dirname(fallback_config_path), "console_memory.db")
	else:
		db_path = str(get_runtime_settings().user_memory_dir / "assistant_console.db")
	return prepare_chat_memory_db_path(db_path, backend_name=backend_name)


def build_assistant_memory_components(
	*,
	memory_cfg: Optional[Dict[str, Any]],
	model_source: str,
	model_name: str,
	memory_db_path: Optional[str],
) -> Dict[str, Any]:
	settings = normalize_assistant_memory_config(memory_cfg)
	db_path = memory_db_path or str(get_runtime_settings().user_memory_dir / "assistant_console.db")
	model_ref = ModelConfig(source=model_source, name=model_name)
	return {
		"settings": settings,
		"content_db": ContentDBConfig(engine="sqlite", url=db_path),
		"history_mgr": HistoryManagerConfig(
			query=settings["history_query"],
			size=settings["history_size"],
		),
		"memory_mgr": MemoryManagerConfig(
			query=settings["memory_query"],
			update=settings["memory_update"],
			managed=settings["memory_managed"],
			model=model_ref,
			prompt=settings.get("memory_prompt"),
			instructions=settings.get("memory_instructions"),
		),
		"session_mgr": SessionManagerConfig(
			query=settings["session_query"],
			update=settings["session_update"],
			history_size=settings["session_history"],
			model=model_ref,
			prompt=settings.get("session_prompt"),
		),
	}
