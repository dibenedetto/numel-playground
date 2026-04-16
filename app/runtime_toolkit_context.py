from __future__ import annotations

import uuid

from typing import Any, Dict, Optional


_RUNTIME_TOOLKIT_CONTEXTS: Dict[str, Dict[str, Any]] = {}


def register_runtime_toolkit_context(
	*,
	local_app=None,
	channel_registry=None,
) -> Optional[str]:
	"""Store live runtime objects outside workflow payloads and return a safe id."""
	if local_app is None and channel_registry is None:
		return None
	context_id = f"rtctx_{uuid.uuid4().hex}"
	_RUNTIME_TOOLKIT_CONTEXTS[context_id] = {
		"local_app": local_app,
		"channel_registry": channel_registry,
	}
	return context_id


def get_runtime_toolkit_context(context_id: Optional[str]) -> Dict[str, Any]:
	"""Resolve a previously registered runtime toolkit context."""
	if not context_id:
		return {}
	context = _RUNTIME_TOOLKIT_CONTEXTS.get(str(context_id)) or {}
	return dict(context)
