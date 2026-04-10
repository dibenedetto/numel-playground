from __future__ import annotations

from importlib import import_module
from inspect import getmembers, ismethod
from typing import Any, Dict, Optional

from utils import log_print


def toolkit_candidates(module_name: str) -> list[str]:
	value = module_name.replace("/", ".").replace("\\", ".")
	candidates = [value]
	if "." not in value:
		candidates.append(f"toolkits.{value}")
		candidates.append(f"contrib.toolkits.{value}")
	elif value.startswith("toolkits.") and not value.startswith("contrib."):
		candidates.append(f"contrib.{value}")
	return candidates


def resolve_toolkit_module(module_name: str):
	candidates = toolkit_candidates(module_name)
	for candidate in candidates:
		try:
			module = import_module(candidate)
			return module, candidate, candidates
		except (ImportError, ModuleNotFoundError):
			continue
	return None, None, candidates


def find_toolkit_class(module) -> Optional[type]:
	for attr_name in dir(module):
		attr = getattr(module, attr_name)
		if isinstance(attr, type) and getattr(attr, "__toolkit__", False):
			return attr
	for attr_name in dir(module):
		attr = getattr(module, attr_name)
		if isinstance(attr, type) and attr.__module__ == module.__name__ and attr.__doc__:
			return attr
	return None


def build_toolkit_record_from_instance(instance, *, name: Optional[str] = None, module_name: Optional[str] = None) -> Dict[str, Any]:
	toolkit_name = str(name or instance.__class__.__name__)
	description = str(instance.__class__.__doc__ or "").strip()
	tools = []
	for method_name, method in getmembers(instance, predicate=ismethod):
		if method_name.startswith("_"):
			continue
		tools.append(method)
	return {
		"name": toolkit_name,
		"module_name": module_name or instance.__class__.__module__,
		"instance": instance,
		"description": description,
		"tools": tools,
	}


def load_numel_toolkit(
	module_name: str,
	args: Optional[Dict[str, Any]] = None,
	*,
	log_prefix: str = "Toolkit",
	quiet: bool = False,
):
	module, resolved_name, candidates = resolve_toolkit_module(module_name)
	if module is None:
		if not quiet:
			log_print(f"⚠️  {log_prefix} not found: {module_name} (tried: {', '.join(candidates)})")
		return None

	toolkit_cls = find_toolkit_class(module)
	if toolkit_cls is None:
		if not quiet:
			log_print(f"⚠️  {log_prefix} class not found in module: {module_name}")
		return None

	try:
		import credentials as _creds
		resolved_args = _creds.resolve_dict(args or {})
		instance = toolkit_cls(**resolved_args)
	except Exception as exc:
		if not quiet:
			log_print(f"⚠️  {log_prefix} instantiation failed: {toolkit_cls.__name__} ({exc})")
		return None

	record = build_toolkit_record_from_instance(
		instance,
		name=resolved_name or module_name,
		module_name=resolved_name or module_name,
	)
	if not quiet:
		log_print(f"  {log_prefix} loaded: {record['module_name']} ({len(record['tools'])} tools)")
	return record
