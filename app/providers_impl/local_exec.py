# providers_impl/local_exec.py — In-process execution provider for development.
#
# Wraps Numel's existing engine.py execution directly — no containers, no
# subprocesses.  This is equivalent to current Numel single-user behavior,
# just behind the ExecutionProvider interface.
#
# NOT for production — no isolation, no resource limits, no sandboxing.

from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any, AsyncIterator, Dict, List, Optional

from providers.execution import ExecutionProvider
from providers.models    import (
    ExecutionHandle, ExecutionResult, ExecutionStatus, ResourceLimits,
)


class LocalProcessExecProvider(ExecutionProvider):
    """In-process workflow execution using the existing Numel engine.

    Args:
        manager: The WorkflowManager instance (app/manager.py).
        api_url: Base URL for the Numel API (default http://localhost:11360).
    """

    def __init__(self, manager=None, api_url: str = "http://localhost:11360", auth_token: str = ""):
        self._manager  = manager
        self._api_url  = api_url.rstrip("/")
        self._auth_token = auth_token
        self._handles: Dict[str, ExecutionHandle] = {}
        self._results: Dict[str, ExecutionResult] = {}
        self._tasks:   Dict[str, asyncio.Task]    = {}

    # ── Lifecycle ────────────────────────────────────────────────

    async def start(
        self,
        user_id:      str,
        workflow:      Dict[str, Any],
        workflow_name: str              = "",
        data_mounts:   Optional[Dict[str, str]] = None,
        limits:        Optional[ResourceLimits]  = None,
        env:           Optional[Dict[str, str]]  = None,
    ) -> ExecutionHandle:
        execution_id = uuid.uuid4().hex[:12]
        handle = ExecutionHandle(
            execution_id=execution_id,
            user_id=user_id,
            workflow_name=workflow_name or "unnamed",
            status="running",
            started_at=time.time(),
        )
        self._handles[execution_id] = handle

        # Use the current HTTP workflow/execution routes.
        task = asyncio.create_task(self._run(execution_id, workflow_name, workflow, limits))
        self._tasks[execution_id] = task
        return handle

    async def _run(self, execution_id: str, name: str, workflow: dict, limits: Optional[ResourceLimits]):
        import httpx
        start_time = time.time()
        timeout = limits.max_duration_seconds if limits else 3600.0
        headers = {}
        if self._auth_token:
            headers["Authorization"] = f"Bearer {self._auth_token}"

        try:
            async with httpx.AsyncClient(base_url=self._api_url, timeout=timeout + 10) as client:
                # Save into the caller's current space/current workflow.
                save_resp = await client.post("/workflow/save", json={"workflow": workflow}, headers=headers)
                save_resp.raise_for_status()

                # Start execution
                resp = await client.post("/workflow/start", json={}, headers=headers)
                resp.raise_for_status()
                data = resp.json()
                if "error" in data:
                    raise RuntimeError(data["error"])

                exec_id_engine = data.get("execution_id", "")

                # Poll until done
                deadline = time.time() + timeout
                while time.time() < deadline:
                    state_resp = await client.post(f"/executions/{exec_id_engine}", headers=headers)
                    state_resp.raise_for_status()
                    state = state_resp.json()
                    status = (state.get("state", {}) or {}).get("status", "unknown")

                    if status in ("completed", "failed", "cancelled"):
                        # Fetch results
                        results_resp = await client.post(f"/executions/{exec_id_engine}/results", headers=headers)
                        results_resp.raise_for_status()
                        results = results_resp.json()

                        self._results[execution_id] = ExecutionResult(
                            execution_id=execution_id,
                            status=status,
                            outputs=results.get("node_outputs", {}),
                            duration_seconds=time.time() - start_time,
                            cpu_seconds_used=time.time() - start_time,
                            error=results.get("error"),
                        )
                        self._handles[execution_id].status = status
                        return

                    await asyncio.sleep(1.0)

                # Timeout
                self._handles[execution_id].status = "failed"
                self._results[execution_id] = ExecutionResult(
                    execution_id=execution_id, status="failed",
                    duration_seconds=time.time() - start_time,
                    error=f"Execution timed out after {timeout}s",
                )

        except asyncio.CancelledError:
            self._handles[execution_id].status = "cancelled"
            self._results[execution_id] = ExecutionResult(
                execution_id=execution_id, status="cancelled",
                duration_seconds=time.time() - start_time,
            )
        except Exception as e:
            self._handles[execution_id].status = "failed"
            self._results[execution_id] = ExecutionResult(
                execution_id=execution_id, status="failed",
                duration_seconds=time.time() - start_time,
                error=str(e),
            )

    async def status(self, execution_id: str) -> ExecutionStatus:
        handle = self._handles.get(execution_id)
        if not handle:
            return ExecutionStatus(execution_id=execution_id, status="unknown")
        return ExecutionStatus(
            execution_id=execution_id,
            status=handle.status,
            cpu_seconds_used=time.time() - handle.started_at if handle.status == "running" else 0,
        )

    async def result(self, execution_id: str) -> ExecutionResult:
        r = self._results.get(execution_id)
        if not r:
            raise ValueError(f"No result for execution '{execution_id}' (still running or unknown)")
        return r

    async def cancel(self, execution_id: str) -> bool:
        task = self._tasks.get(execution_id)
        if task and not task.done():
            task.cancel()
            self._handles[execution_id].status = "cancelled"
            return True
        return False

    async def cleanup(self, execution_id: str) -> bool:
        self._tasks.pop(execution_id, None)
        self._handles.pop(execution_id, None)
        self._results.pop(execution_id, None)
        return True

    # ── Query ────────────────────────────────────────────────────

    async def list_running(self, user_id: Optional[str] = None) -> List[ExecutionHandle]:
        handles = [h for h in self._handles.values() if h.status == "running"]
        if user_id:
            handles = [h for h in handles if h.user_id == user_id]
        return handles

    async def list_all(
        self, user_id: Optional[str] = None,
        status_filter: Optional[str] = None,
        offset: int = 0, limit: int = 50,
    ) -> List[ExecutionHandle]:
        handles = list(self._handles.values())
        if user_id:
            handles = [h for h in handles if h.user_id == user_id]
        if status_filter:
            handles = [h for h in handles if h.status == status_filter]
        handles.sort(key=lambda h: h.started_at, reverse=True)
        return handles[offset:offset + limit]

    async def logs(self, execution_id: str, tail: int = 100) -> str:
        return f"[LocalProcessExec] No separate logs for in-process execution {execution_id}"

    async def stream_events(self, execution_id: str) -> AsyncIterator[Dict[str, Any]]:
        return
        yield

    # ── Provider lifecycle ───────────────────────────────────────

    async def health_check(self) -> Dict[str, Any]:
        return {
            "status": "ok",
            "provider": "LocalProcessExecProvider",
            "running": len([h for h in self._handles.values() if h.status == "running"]),
            "total":   len(self._handles),
        }
