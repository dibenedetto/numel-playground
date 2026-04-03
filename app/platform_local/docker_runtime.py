"""Space-aware runtime for local development.

The architectural boundary remains "Docker runtime", but the current working
mockup executes workflows through Numel's existing per-user WorkspaceManager
and WorkflowEngine pair. This lets the db+git platform exercise real space
snapshots and permissions now, while keeping the future container boundary
explicit in the code.
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Union, get_args, get_origin

import credentials as _creds
from pydantic import BaseModel

from domain.interfaces import RuntimeProvider
from domain.models import (
    AssetKind,
    Capability,
    ExecutionRecord,
    ExecutionRequest,
    ExecutionState,
    RuntimeProfile,
)
from schema import FieldRole, Workflow, WorkflowNodeUnion, WorkflowOptions

from .config import ArtifactStorageConfig, DockerRuntimeConfig
from .db_execution_registry import DbExecutionRegistry
from .db_git_spaces import DbGitSpaceProvider
from .git_space_store import GitSpaceStore


_WORKFLOW_NODE_MODELS = {
    str(node_cls.model_fields["type"].default): node_cls
    for node_cls in get_args(WorkflowNodeUnion)
}


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


def _resolve_workflow_payload_inputs(
    payload: Dict[str, Any],
    runtime_vars: Optional[Dict[str, str]],
) -> Dict[str, Any]:
    return _resolve_model_inputs(payload, Workflow, runtime_vars)


class DockerRuntimeProvider(RuntimeProvider):
    """Run space assets using the current local workspace engine."""

    _TERMINAL_STATES = frozenset(
        {
            ExecutionState.COMPLETED,
            ExecutionState.FAILED,
            ExecutionState.CANCELLED,
        }
    )

    def __init__(
        self,
        config: DockerRuntimeConfig,
        git_store: GitSpaceStore,
        execution_registry: Optional[DbExecutionRegistry] = None,
        artifact_config: Optional[ArtifactStorageConfig] = None,
        audit_log=None,
        space_provider: Optional[DbGitSpaceProvider] = None,
        workspace_manager: Any = None,
    ):
        self.config = config
        self.git_store = git_store
        self.execution_registry = execution_registry
        self.artifact_config = artifact_config
        self.audit_log = audit_log
        self.space_provider = space_provider
        self.workspace_manager = workspace_manager
        self._records: Dict[str, ExecutionRecord] = {}
        self._engine_links: Dict[str, Dict[str, str]] = {}
        self._monitor_tasks: Dict[str, asyncio.Task] = {}

    def _ensure_ready(self) -> None:
        missing = []
        if self.space_provider is None:
            missing.append("space_provider")
        if self.workspace_manager is None:
            missing.append("workspace_manager")
        if missing:
            joined = ", ".join(missing)
            raise NotImplementedError(
                f"DockerRuntimeProvider requires {joined} for the local db+git mock runtime"
            )

    async def _create_record(self, record: ExecutionRecord) -> ExecutionRecord:
        self._records[record.execution_id] = record
        if self.execution_registry is not None:
            record = await self.execution_registry.create_execution(record)
            self._records[record.execution_id] = record
        return record

    async def _update_record(self, execution_id: str, **fields) -> ExecutionRecord:
        if self.execution_registry is not None:
            record = await self.execution_registry.update_execution(execution_id, **fields)
            self._records[execution_id] = record
            return record
        current = self._records.get(execution_id)
        if current is None:
            raise ValueError(f"Unknown execution '{execution_id}'")
        updated = ExecutionRecord(
            execution_id=current.execution_id,
            user_id=fields.get("user_id", current.user_id),
            space_id=fields.get("space_id", current.space_id),
            asset_path=fields.get("asset_path", current.asset_path),
            ref=fields.get("ref", current.ref),
            status=fields.get("status", current.status),
            runtime_profile_id=fields.get("runtime_profile_id", current.runtime_profile_id),
            started_at=fields.get("started_at", current.started_at),
            finished_at=fields.get("finished_at", current.finished_at),
            outputs=fields.get("outputs", current.outputs),
            error=fields.get("error", current.error),
            metadata=fields.get("metadata", current.metadata),
        )
        self._records[execution_id] = updated
        return updated

    async def _get_record(self, execution_id: str) -> Optional[ExecutionRecord]:
        if self.execution_registry is not None:
            record = await self.execution_registry.get_execution(execution_id)
            if record is not None:
                self._records[execution_id] = record
            return record
        return self._records.get(execution_id)

    async def _list_records(
        self,
        user_id: Optional[str] = None,
        space_id: Optional[str] = None,
        status: Optional[ExecutionState] = None,
        offset: int = 0,
        limit: int = 50,
    ) -> List[ExecutionRecord]:
        if self.execution_registry is not None:
            records = await self.execution_registry.list_executions(
                user_id=user_id,
                space_id=space_id,
                status=status,
                offset=offset,
                limit=limit,
            )
            for record in records:
                self._records[record.execution_id] = record
            return records
        records = list(self._records.values())
        if user_id is not None:
            records = [record for record in records if record.user_id == user_id]
        if space_id is not None:
            records = [record for record in records if record.space_id == space_id]
        if status is not None:
            records = [record for record in records if record.status == status]
        records.sort(key=lambda item: item.started_at, reverse=True)
        return records[offset:offset + limit]

    def _workflow_from_payload(self, payload: Dict[str, Any]) -> Workflow:
        if hasattr(Workflow, "model_validate"):
            return Workflow.model_validate(payload)
        if hasattr(Workflow, "parse_obj"):
            return Workflow.parse_obj(payload)
        return Workflow(**payload)

    def _derive_workflow_name(self, request: ExecutionRequest, execution_id: str) -> str:
        base = request.asset_path.replace("\\", "/").strip("/").replace("/", "_")
        if not base:
            base = "workflow"
        suffix = execution_id.split("_")[-1]
        return f"{request.space_id}_{base}_{suffix}"

    def _map_engine_status(self, raw_status: str, error: Optional[str]) -> ExecutionState:
        if raw_status in {"pending", "ready", "waiting", "running"}:
            return ExecutionState.RUNNING
        if raw_status == "completed":
            return ExecutionState.COMPLETED
        if raw_status == "cancelled" or (raw_status == "failed" and error == "Cancelled by user"):
            return ExecutionState.CANCELLED
        return ExecutionState.FAILED

    async def _materialize_snapshot(
        self,
        execution_id: str,
        request: ExecutionRequest,
    ) -> Optional[str]:
        if self.artifact_config is None:
            return None
        base = Path(self.artifact_config.root_path).resolve()
        snapshot_dir = base / "executions" / execution_id / "space"
        return await self.git_store.materialize_ref(
            request.space_id,
            request.ref,
            str(snapshot_dir),
        )

    async def _cleanup_workspace_entry(self, execution_id: str) -> None:
        link = self._engine_links.get(execution_id)
        if not link or self.workspace_manager is None:
            return
        workspace = await self.workspace_manager.get_workspace(link["workspace_id"])
        if workspace is None:
            return
        await workspace.manager.remove(link["workflow_name"])

    async def _monitor_execution(self, execution_id: str) -> None:
        try:
            while True:
                link = self._engine_links.get(execution_id)
                if not link or self.workspace_manager is None:
                    return
                workspace = await self.workspace_manager.get_workspace(link["workspace_id"])
                if workspace is None:
                    await self._update_record(
                        execution_id,
                        status=ExecutionState.FAILED,
                        finished_at=time.time(),
                        error=f"Workspace '{link['workspace_id']}' is no longer available",
                    )
                    return
                state = workspace.engine.get_execution_state(link["engine_execution_id"])
                if state is None:
                    record = await self._get_record(execution_id)
                    if record is not None and record.status in self._TERMINAL_STATES:
                        return
                    await asyncio.sleep(0.5)
                    continue

                raw_status = getattr(getattr(state, "status", None), "value", str(state.status))
                error = getattr(state, "error", None)
                mapped_status = self._map_engine_status(raw_status, error)
                if mapped_status in self._TERMINAL_STATES:
                    results = workspace.engine.get_execution_results(link["engine_execution_id"]) or {}
                    record = await self._get_record(execution_id)
                    metadata = dict(record.metadata if record is not None else {})
                    metadata.update(
                        {
                            "engine_status": raw_status,
                            "engine_end_time": getattr(state, "end_time", None),
                        }
                    )
                    await self._update_record(
                        execution_id,
                        status=mapped_status,
                        finished_at=time.time(),
                        outputs=results.get("node_outputs", {}),
                        error=results.get("error", error),
                        metadata=metadata,
                    )
                    return
                await asyncio.sleep(0.5)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            await self._update_record(
                execution_id,
                status=ExecutionState.FAILED,
                finished_at=time.time(),
                error=str(exc),
            )
        finally:
            self._monitor_tasks.pop(execution_id, None)
            await self._cleanup_workspace_entry(execution_id)

    async def start_execution(
        self,
        request: ExecutionRequest,
        runtime: Optional[RuntimeProfile] = None,
        env: Optional[Dict[str, str]] = None,
    ) -> ExecutionRecord:
        self._ensure_ready()
        if not await self.space_provider.check_asset_access(
            request.user_id,
            request.space_id,
            request.asset_path,
            capability=Capability.EXECUTE,
        ):
            raise PermissionError(
                f"User '{request.user_id}' does not have 'execute' on "
                f"asset '{request.space_id}:{request.asset_path}'"
            )

        execution_id = f"exec_{uuid.uuid4().hex[:12]}"
        workflow_name = self._derive_workflow_name(request, execution_id)
        runtime_profile_id = runtime.id if runtime is not None else request.runtime_profile_id
        metadata = dict(request.metadata)
        metadata.update(
            {
                "runtime_mode": "workspace_engine",
                "workflow_name": workflow_name,
                "requested_env_keys": sorted((env or {}).keys()),
                "env_injected": False,
                "credential_names": list(request.credential_names),
            }
        )
        if runtime is not None:
            metadata["runtime_profile_name"] = runtime.name
            metadata["runtime_image"] = runtime.image or self.config.default_image

        record = await self._create_record(
            ExecutionRecord(
                execution_id=execution_id,
                user_id=request.user_id,
                space_id=request.space_id,
                asset_path=request.asset_path,
                ref=request.ref,
                status=ExecutionState.PENDING,
                runtime_profile_id=runtime_profile_id,
                started_at=time.time(),
                metadata=metadata,
            )
        )

        workspace = None
        try:
            asset = await self.space_provider.get_asset(
                request.user_id,
                request.space_id,
                request.asset_path,
                ref=request.ref,
            )
            if asset is not None and asset.kind not in {AssetKind.WORKFLOW, AssetKind.OTHER}:
                raise ValueError(
                    f"Local runtime currently supports workflow assets only, got '{asset.kind.value}'"
                )

            raw_content = await self.space_provider.read_asset(
                request.user_id,
                request.space_id,
                request.asset_path,
                ref=request.ref,
            )
            try:
                payload = json.loads(raw_content.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ValueError(
                    f"Asset '{request.asset_path}' is not valid UTF-8 JSON workflow content"
                ) from exc
            if payload.get("type") != "workflow":
                raise ValueError(
                    f"Asset '{request.asset_path}' is not a workflow document"
                )
            payload = _resolve_workflow_payload_inputs(payload, env)
            workflow = self._workflow_from_payload(payload)
            if workflow.options is None:
                workflow.options = WorkflowOptions(name=workflow_name)
            elif not workflow.options.name:
                workflow.options.name = workflow_name

            snapshot_dir = await self._materialize_snapshot(execution_id, request)
            if snapshot_dir:
                metadata["snapshot_dir"] = snapshot_dir

            workspace = await self.workspace_manager.resolve_workspace(request.user_id)
            metadata["workspace_id"] = workspace.workspace_id

            await workspace.manager.add(workflow, name=workflow_name)
            impl = await workspace.manager.impl(workflow_name)
            if impl is None:
                raise RuntimeError(f"Unable to materialize workflow '{workflow_name}'")
            engine_execution_id = await workspace.engine.start_workflow(
                impl["workflow"],
                impl["backend"],
                initial_data=request.inputs or {},
            )

            self._engine_links[execution_id] = {
                "workspace_id": workspace.workspace_id,
                "workflow_name": workflow_name,
                "engine_execution_id": engine_execution_id,
            }
            metadata["engine_execution_id"] = engine_execution_id

            record = await self._update_record(
                execution_id,
                status=ExecutionState.RUNNING,
                metadata=metadata,
            )
            self._monitor_tasks[execution_id] = asyncio.create_task(
                self._monitor_execution(execution_id)
            )
            return record
        except Exception as exc:
            await self._update_record(
                execution_id,
                status=ExecutionState.FAILED,
                finished_at=time.time(),
                error=str(exc),
                metadata=metadata,
            )
            if workspace is not None and execution_id not in self._engine_links:
                await workspace.manager.remove(workflow_name)
            await self._cleanup_workspace_entry(execution_id)
            raise

    async def get_execution(self, execution_id: str) -> Optional[ExecutionRecord]:
        return await self._get_record(execution_id)

    async def list_executions(
        self,
        user_id: Optional[str] = None,
        space_id: Optional[str] = None,
        status: Optional[ExecutionState] = None,
        offset: int = 0,
        limit: int = 50,
    ) -> List[ExecutionRecord]:
        return await self._list_records(
            user_id=user_id,
            space_id=space_id,
            status=status,
            offset=offset,
            limit=limit,
        )

    async def cancel_execution(self, execution_id: str) -> bool:
        record = await self._get_record(execution_id)
        if record is None:
            return False
        link = self._engine_links.get(execution_id)
        cancelled = False
        if link and self.workspace_manager is not None:
            workspace = await self.workspace_manager.get_workspace(link["workspace_id"])
            if workspace is not None:
                await workspace.engine.cancel_execution(link["engine_execution_id"])
                cancelled = True
        if record.status not in self._TERMINAL_STATES:
            await self._update_record(
                execution_id,
                status=ExecutionState.CANCELLED,
                finished_at=time.time(),
                error="Cancelled by user",
            )
        return cancelled or True

    async def get_logs(self, execution_id: str, tail: int = 100) -> str:
        record = await self._get_record(execution_id)
        if record is None:
            return ""
        link = self._engine_links.get(execution_id, {})
        lines = [
            f"execution_id={record.execution_id}",
            f"status={record.status.value}",
            f"user_id={record.user_id}",
            f"space_id={record.space_id}",
            f"asset_path={record.asset_path}",
            f"ref={record.ref}",
        ]
        if link.get("workspace_id"):
            lines.append(f"workspace_id={link['workspace_id']}")
        if link.get("engine_execution_id"):
            lines.append(f"engine_execution_id={link['engine_execution_id']}")
        if record.error:
            lines.append(f"error={record.error}")
        if record.outputs:
            lines.append(f"output_keys={sorted(record.outputs.keys())}")
        return "\n".join(lines[-tail:])
