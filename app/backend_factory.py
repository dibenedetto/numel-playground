from __future__ import annotations

import copy

from typing import Any, Callable, Optional, Tuple

from nodes import ImplementedBackend
from schema import (
	ContentDBConfig,
	DEFAULT_BACKEND_NAME,
	Edge,
	EmbeddingConfig,
	IndexDBConfig,
	KnowledgeManagerConfig,
	Workflow,
)


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


def get_text_generation_models(
	model_source: Optional[str] = None,
	backend_name: Optional[str] = None,
) -> list[str]:
	name = normalize_backend_name(backend_name)
	if name == "agno":
		from impl_agno import get_text_generation_models_agno
		return get_text_generation_models_agno(model_source=model_source)
	raise ValueError(f"Unsupported backend: {name}")


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


def build_knowledge_runtime(
	knowledge_config: KnowledgeManagerConfig,
	*,
	backend_name: Optional[str] = None,
) -> Tuple[ImplementedBackend, Any]:
	"""Build a backend handle for one knowledge manager config without exposing backend internals."""
	if knowledge_config is None:
		raise ValueError("knowledge_config is required")
	if knowledge_config.content_db is None:
		raise ValueError("knowledge_config.content_db is required")
	if knowledge_config.index_db is None:
		raise ValueError("knowledge_config.index_db is required")

	knowledge_cfg = copy.deepcopy(knowledge_config)
	content_cfg = copy.deepcopy(knowledge_cfg.content_db or ContentDBConfig())
	index_cfg = copy.deepcopy(knowledge_cfg.index_db or IndexDBConfig())
	embedding_cfg = copy.deepcopy(index_cfg.embedding) if index_cfg.embedding is not None else None

	nodes = []
	edges = []

	if embedding_cfg is not None:
		embedding_idx = len(nodes)
		nodes.append(embedding_cfg)
	else:
		embedding_idx = None

	content_idx = len(nodes)
	nodes.append(content_cfg)
	index_idx = len(nodes)
	nodes.append(index_cfg)
	knowledge_idx = len(nodes)
	nodes.append(knowledge_cfg)

	if embedding_idx is not None:
		edges.append(
			Edge(
				source=embedding_idx,
				target=index_idx,
				source_slot="config",
				target_slot="embedding",
			)
		)
	knowledge_cfg.content_db = content_cfg
	knowledge_cfg.index_db = index_cfg
	edges.extend(
		[
			Edge(source=content_idx, target=knowledge_idx, source_slot="config", target_slot="content_db"),
			Edge(source=index_idx, target=knowledge_idx, source_slot="config", target_slot="index_db"),
		]
	)

	workflow = Workflow(type="workflow", nodes=nodes, edges=edges)
	workflow.link()

	builder = get_backend_builder(backend_name or DEFAULT_BACKEND_NAME)
	backend = builder(workflow, skill_mgr=None)
	return backend, backend.handles[knowledge_idx]
