from __future__ import annotations

from typing import Callable, Optional

from nodes import ImplementedBackend
from schema import DEFAULT_BACKEND_NAME, Workflow


def normalize_backend_name(name: Optional[str]) -> str:
	value = str(name or "").strip().lower()
	return value or DEFAULT_BACKEND_NAME


def get_workflow_backend_name(workflow: Workflow) -> str:
	for node in getattr(workflow, "nodes", []) or []:
		if getattr(node, "type", None) != "backend_config":
			continue
		return normalize_backend_name(getattr(node, "name", None))
	return DEFAULT_BACKEND_NAME


def get_backend_builder(name: Optional[str] = None) -> Callable[..., ImplementedBackend]:
	backend_name = normalize_backend_name(name)
	if backend_name == "agno":
		from impl_agno import build_backend_agno
		return build_backend_agno
	raise ValueError(f"Unsupported backend: {backend_name}")


def build_backend_skills(skill_definitions, backend_name: Optional[str] = None):
	name = normalize_backend_name(backend_name)
	if name == "agno":
		from impl_agno import build_native_skills_agno
		return build_native_skills_agno(skill_definitions)
	raise ValueError(f"Unsupported backend: {name}")


def build_backend_toolkit(toolkit_record, backend_name: Optional[str] = None):
	name = normalize_backend_name(backend_name)
	if name == "agno":
		from impl_agno import build_native_toolkit_agno
		return build_native_toolkit_agno(toolkit_record)
	raise ValueError(f"Unsupported backend: {name}")


def get_text_generation_sources(name: Optional[str] = None) -> list[str]:
	backend_name = normalize_backend_name(name)
	if backend_name == "agno":
		from impl_agno import get_text_generation_sources_agno
		return get_text_generation_sources_agno()
	raise ValueError(f"Unsupported backend: {backend_name}")


async def generate_text(
	*,
	system_message: str,
	user_message: str,
	model_source: str,
	model_name: str,
	temperature: Optional[float] = None,
	max_tokens: Optional[int] = None,
	backend_name: Optional[str] = None,
) -> str:
	name = normalize_backend_name(backend_name)
	if name == "agno":
		from impl_agno import generate_text_agno
		return await generate_text_agno(
			system_message=system_message,
			user_message=user_message,
			model_source=model_source,
			model_name=model_name,
			temperature=temperature,
			max_tokens=max_tokens,
		)
	raise ValueError(f"Unsupported backend: {name}")


def build_backend(workflow: Workflow, skill_mgr=None) -> ImplementedBackend:
	builder = get_backend_builder(get_workflow_backend_name(workflow))
	return builder(workflow, skill_mgr=skill_mgr)
