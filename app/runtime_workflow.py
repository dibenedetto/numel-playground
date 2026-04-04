"""Shared helpers for loading and executing Numel workflows in-process."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Union, get_args, get_origin

import credentials as _creds
from pydantic import BaseModel

from engine import WorkflowEngine
from event_bus import EventBus
from manager import WorkflowManager
from schema import FieldRole, Workflow, WorkflowNodeUnion, WorkflowOptions


_WORKFLOW_NODE_MODELS = {
    str(node_cls.model_fields["type"].default): node_cls
    for node_cls in get_args(WorkflowNodeUnion)
}

_RUNNING_STATUSES = frozenset({"pending", "ready", "waiting", "running"})


def _unwrap_annotation(annotation: Any) -> Any:
    origin = get_origin(annotation)
    if origin is Union:
        args = [arg for arg in get_args(annotation) if arg is not type(None)]
        if len(args) == 1:
            return _unwrap_annotation(args[0])
    return annotation


def _field_is_runtime_input(field_info: Any) -> bool:
    return any(meta in {FieldRole.INPUT, FieldRole.MULTI_INPUT} for meta in field_info.metadata)


def _coerce_resolved_string(value: str, annotation: Any) -> Any:
    target = _unwrap_annotation(annotation)
    origin = get_origin(target)

    if target is bool:
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes", "on"}:
            return True
        if lowered in {"false", "0", "no", "off"}:
            return False
        return value
    if target is int:
        try:
            return int(value)
        except ValueError:
            return value
    if target is float:
        try:
            return float(value)
        except ValueError:
            return value
    if origin in {list, List, dict, Dict}:
        try:
            parsed = json.loads(value)
        except Exception:
            return value
        if origin in {list, List} and isinstance(parsed, list):
            return parsed
        if origin in {dict, Dict} and isinstance(parsed, dict):
            return parsed
    return value


def _resolve_payload_value(value: Any, annotation: Any, runtime_vars: Optional[Dict[str, str]]) -> Any:
    target = _unwrap_annotation(annotation)
    origin = get_origin(target)

    if isinstance(value, str):
        resolved = _creds.resolve_with_overrides(value, overrides=runtime_vars)
        return _coerce_resolved_string(resolved, target)

    if isinstance(value, list):
        item_annotation = Any
        if origin in {list, List}:
            args = get_args(target)
            item_annotation = args[0] if args else Any
        return [
            _resolve_payload_value(item, item_annotation, runtime_vars)
            for item in value
        ]

    if isinstance(value, dict):
        if isinstance(target, type) and issubclass(target, BaseModel):
            return _resolve_model_inputs(value, target, runtime_vars)
        if "type" in value and str(value.get("type", "")) in _WORKFLOW_NODE_MODELS:
            return _resolve_model_inputs(
                value,
                _WORKFLOW_NODE_MODELS[str(value["type"])],
                runtime_vars,
            )
        if origin in {dict, Dict}:
            args = get_args(target)
            value_annotation = args[1] if len(args) > 1 else Any
            return {
                key: _resolve_payload_value(item, value_annotation, runtime_vars)
                for key, item in value.items()
            }
        return {
            key: _resolve_payload_value(item, Any, runtime_vars)
            for key, item in value.items()
        }

    return value


def _resolve_model_inputs(
    payload: Dict[str, Any],
    model_cls: type[BaseModel],
    runtime_vars: Optional[Dict[str, str]],
) -> Dict[str, Any]:
    resolved = dict(payload)
    for field_name, field_info in model_cls.model_fields.items():
        if field_name not in payload:
            continue
        if not _field_is_runtime_input(field_info):
            continue
        resolved[field_name] = _resolve_payload_value(
            payload[field_name],
            field_info.annotation,
            runtime_vars,
        )
    return resolved


def resolve_workflow_payload_inputs(
    payload: Dict[str, Any],
    runtime_vars: Optional[Dict[str, str]],
) -> Dict[str, Any]:
    """Resolve `${VAR}` placeholders in runtime-input workflow fields."""
    return _resolve_model_inputs(payload, Workflow, runtime_vars)


def workflow_from_payload(payload: Dict[str, Any]) -> Workflow:
    """Validate and construct a workflow model from a resolved payload."""
    if hasattr(Workflow, "model_validate"):
        return Workflow.model_validate(payload)
    if hasattr(Workflow, "parse_obj"):
        return Workflow.parse_obj(payload)
    return Workflow(**payload)


async def run_workflow_in_process(
    payload: Dict[str, Any],
    *,
    workflow_name: str,
    initial_data: Optional[Dict[str, Any]] = None,
    runtime_vars: Optional[Dict[str, str]] = None,
    storage_dir: Optional[str] = None,
    base_port: int = 19000,
    poll_interval: float = 0.2,
) -> Dict[str, Any]:
    """Execute a workflow through WorkflowManager + WorkflowEngine and wait for completion."""
    resolved_payload = resolve_workflow_payload_inputs(payload, runtime_vars)
    workflow = workflow_from_payload(resolved_payload)
    if workflow.options is None:
        workflow.options = WorkflowOptions(name=workflow_name)
    elif not workflow.options.name:
        workflow.options.name = workflow_name

    event_bus = EventBus()
    manager = WorkflowManager(
        base_port,
        event_bus,
        storage_dir=Path(storage_dir) if storage_dir else None,
    )
    await manager.initialize()
    engine = WorkflowEngine(event_bus)

    engine_execution_id: Optional[str] = None
    added_name: Optional[str] = None
    try:
        added_name = await manager.add(workflow, name=workflow_name)
        impl = await manager.impl(added_name)
        if impl is None:
            raise RuntimeError(f"Unable to materialize workflow '{added_name}'")
        engine_execution_id = await engine.start_workflow(
            impl["workflow"],
            impl["backend"],
            initial_data=initial_data or {},
        )

        while True:
            state = engine.get_execution_state(engine_execution_id)
            if state is None:
                raise RuntimeError(
                    f"Workflow engine lost execution state for '{engine_execution_id}'"
                )
            raw_status = getattr(getattr(state, "status", None), "value", str(state.status))
            if raw_status not in _RUNNING_STATUSES:
                break
            await asyncio.sleep(poll_interval)

        results = engine.get_execution_results(engine_execution_id) or {}
        final_state = engine.get_execution_state(engine_execution_id)
        raw_status = getattr(getattr(final_state, "status", None), "value", str(final_state.status))
        if raw_status == "failed":
            raise RuntimeError(results.get("error") or getattr(final_state, "error", None) or "Workflow failed")

        return {
            "workflow_name": added_name,
            "engine_execution_id": engine_execution_id,
            "status": raw_status,
            "results": results,
            "event_count": len(event_bus.get_event_history(limit=10_000)),
        }
    finally:
        if added_name:
            await manager.remove(added_name)
