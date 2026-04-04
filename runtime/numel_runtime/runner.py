"""Headless production runtime runner for executing a workflow asset in-container."""

from __future__ import annotations

import json
from pathlib import Path, PurePosixPath
from typing import Any, Dict

from runtime_workflow import run_workflow_in_process

from platform_prod.runtime_contract import (
    CONTRACT_VERSION,
    ENV_ARTIFACTS_DIR,
    ENV_ASSET_KIND,
    ENV_ASSET_PATH,
    ENV_CONTRACT_VERSION,
    ENV_REF,
    ENV_SPACE_ID,
    ENV_USER_ID,
    ENV_WORKSPACE_DIR,
)


def resolve_asset_path(workspace_dir: str, asset_path: str) -> Path:
    """Resolve a relative asset path against the mounted workspace safely."""
    workspace_root = Path(workspace_dir).resolve()
    relative = PurePosixPath(asset_path)
    if relative.is_absolute():
        raise ValueError(f"{ENV_ASSET_PATH} must be relative, got '{asset_path}'")
    resolved = (workspace_root / Path(*relative.parts)).resolve()
    if resolved != workspace_root and workspace_root not in resolved.parents:
        raise ValueError(f"{ENV_ASSET_PATH} escapes the mounted workspace: '{asset_path}'")
    return resolved


def load_workflow_payload(asset_file: Path) -> Dict[str, Any]:
    """Load a workflow JSON document from disk."""
    payload = json.loads(asset_file.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Workflow payload must be a JSON object")
    if payload.get("type") != "workflow":
        raise ValueError(f"Asset '{asset_file.name}' is not a workflow document")
    return payload


def workflow_summary(payload: Dict[str, Any], asset_file: Path) -> Dict[str, Any]:
    """Return a small summary of a workflow payload."""
    nodes = payload.get("nodes")
    edges = payload.get("edges")
    options = payload.get("options") if isinstance(payload.get("options"), dict) else {}
    return {
        "type": str(payload.get("type", "") or ""),
        "name": str(options.get("name", "") or asset_file.stem),
        "node_count": len(nodes) if isinstance(nodes, list) else 0,
        "edge_count": len(edges) if isinstance(edges, list) else 0,
    }


async def execute_runtime_workflow(
    *,
    execution_id: str,
    user_id: str,
    space_id: str,
    asset_path: str,
    asset_kind: str,
    ref: str,
    inputs: Dict[str, Any],
    workspace_dir: str,
    artifacts_dir: str,
    runtime_vars: Dict[str, str],
) -> Dict[str, Any]:
    """Run a workflow asset through the in-process Numel engine."""
    asset_file = resolve_asset_path(workspace_dir, asset_path)
    if not asset_file.is_file():
        raise FileNotFoundError(f"Asset file not found: {asset_file}")

    payload = load_workflow_payload(asset_file)
    summary = workflow_summary(payload, asset_file)
    workflow_name = f"{summary['name']}_{execution_id}"
    run = await run_workflow_in_process(
        payload,
        workflow_name=workflow_name,
        initial_data=inputs,
        runtime_vars=runtime_vars,
        storage_dir=str(Path(artifacts_dir) / "runtime_state"),
    )

    results = run.get("results", {})
    return {
        "runtime": {
            "contract_version": runtime_vars.get(ENV_CONTRACT_VERSION, CONTRACT_VERSION),
            "execution_id": execution_id,
            "user_id": user_id,
            "space_id": space_id,
            "asset_path": asset_path,
            "asset_kind": asset_kind,
            "ref": ref,
            "workspace_dir": workspace_dir,
            "artifacts_dir": artifacts_dir,
            "input_keys": sorted(inputs.keys()),
            "event_count": int(run.get("event_count", 0) or 0),
        },
        "workflow": summary,
        "execution": {
            "workflow_name": run.get("workflow_name", workflow_name),
            "engine_execution_id": run.get("engine_execution_id", ""),
            "status": run.get("status", results.get("status", "")),
            "start_time": results.get("start_time"),
            "end_time": results.get("end_time"),
            "error": results.get("error"),
        },
        "node_outputs": results.get("node_outputs", {}),
    }
