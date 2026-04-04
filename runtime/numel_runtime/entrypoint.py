"""Reference entrypoint for the first `numel-runtime` container image."""

from __future__ import annotations

import asyncio
import json
import os
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from platform_prod.runtime_contract import (
    CONTRACT_VERSION,
    ENV_ARTIFACTS_DIR,
    ENV_ASSET_KIND,
    ENV_ASSET_PATH,
    ENV_CONTRACT_VERSION,
    ENV_ERROR_PATH,
    ENV_EXECUTION_ID,
    ENV_INPUTS_JSON,
    ENV_OUTPUTS_PATH,
    ENV_REF,
    ENV_RUNTIME_PROFILE_ID,
    ENV_RUNTIME_PROFILE_NAME,
    ENV_SPACE_ID,
    ENV_STATUS_PATH,
    ENV_USER_ID,
    ENV_WORKSPACE_DIR,
    ERROR_FILE_NAME,
    OUTPUTS_FILE_NAME,
    STATUS_FILE_NAME,
)
from runtime.numel_runtime.runner import execute_runtime_workflow


def _env(name: str, default: str = "") -> str:
    return str(os.getenv(name, default) or default)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    _ensure_parent(path)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    _ensure_parent(path)
    path.write_text(text, encoding="utf-8")


def _parse_inputs() -> Dict[str, Any]:
    raw = _env(ENV_INPUTS_JSON, "{}").strip() or "{}"
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{ENV_INPUTS_JSON} is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"{ENV_INPUTS_JSON} must decode to an object")
    return data


def _status_payload(state: str, *, inputs: Dict[str, Any] | None = None, error: str = "") -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "contract_version": _env(ENV_CONTRACT_VERSION, CONTRACT_VERSION),
        "state": state,
        "execution_id": _env(ENV_EXECUTION_ID),
        "user_id": _env(ENV_USER_ID),
        "space_id": _env(ENV_SPACE_ID),
        "asset_path": _env(ENV_ASSET_PATH),
        "asset_kind": _env(ENV_ASSET_KIND),
        "ref": _env(ENV_REF, "main"),
        "runtime_profile_id": _env(ENV_RUNTIME_PROFILE_ID),
        "runtime_profile_name": _env(ENV_RUNTIME_PROFILE_NAME),
        "started_at": _utc_now(),
        "input_keys": sorted((inputs or {}).keys()),
    }
    if error:
        payload["error"] = error
    return payload


async def _amain() -> int:
    workspace_dir = _env(ENV_WORKSPACE_DIR, "/workspace")
    artifacts_dir = _env(ENV_ARTIFACTS_DIR, "/artifacts")
    outputs_path = Path(_env(ENV_OUTPUTS_PATH, str(Path(artifacts_dir) / OUTPUTS_FILE_NAME)))
    error_path = Path(_env(ENV_ERROR_PATH, str(Path(artifacts_dir) / ERROR_FILE_NAME)))
    status_path = Path(_env(ENV_STATUS_PATH, str(Path(artifacts_dir) / STATUS_FILE_NAME)))

    inputs: Dict[str, Any] = {}
    try:
        inputs = _parse_inputs()
        running_status = _status_payload("running", inputs=inputs)
        _write_json(status_path, running_status)

        outputs = await execute_runtime_workflow(
            execution_id=_env(ENV_EXECUTION_ID),
            user_id=_env(ENV_USER_ID),
            space_id=_env(ENV_SPACE_ID),
            asset_path=_env(ENV_ASSET_PATH),
            asset_kind=_env(ENV_ASSET_KIND),
            ref=_env(ENV_REF, "main"),
            inputs=inputs,
            workspace_dir=workspace_dir,
            artifacts_dir=artifacts_dir,
            runtime_vars=dict(os.environ),
        )
        _write_json(outputs_path, outputs)

        status = _status_payload("completed", inputs=inputs)
        status["finished_at"] = _utc_now()
        status["workflow_name"] = outputs.get("execution", {}).get("workflow_name", "")
        status["engine_execution_id"] = outputs.get("execution", {}).get("engine_execution_id", "")
        status["event_count"] = outputs.get("runtime", {}).get("event_count", 0)
        status["node_output_keys"] = sorted((outputs.get("node_outputs") or {}).keys())
        _write_json(status_path, status)
        print(f"numel-runtime completed execution {_env(ENV_EXECUTION_ID)}")
        return 0
    except Exception as exc:
        message = "".join(traceback.format_exception_only(type(exc), exc)).strip()
        _write_text(error_path, message + "\n")
        status = _status_payload("failed", inputs=inputs, error=message)
        status["finished_at"] = _utc_now()
        _write_json(status_path, status)
        print(f"numel-runtime failed execution {_env(ENV_EXECUTION_ID)}: {message}")
        return 1


def main() -> int:
    return asyncio.run(_amain())


if __name__ == "__main__":
    raise SystemExit(main())
