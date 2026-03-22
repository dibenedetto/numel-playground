# providers/execution.py — Workflow execution interface.
#
# Abstracts HOW a workflow runs: in-process, subprocess, Docker, Kubernetes, etc.
# The provider receives a workflow dict + data mounts + resource limits and
# returns a handle that can be polled, cancelled, or inspected.
#
# Implementations: DockerExecutionProvider, LocalProcessExecutionProvider,
#                  KubernetesExecutionProvider.

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, AsyncIterator, Dict, List, Optional

from providers.models import (
    ExecutionHandle, ExecutionResult, ExecutionStatus, ResourceLimits,
)


class ExecutionProvider(ABC):
    """Run workflows in isolated environments with resource constraints."""

    # ── Lifecycle ────────────────────────────────────────────────

    @abstractmethod
    async def start(
        self,
        user_id:      str,
        workflow:      Dict[str, Any],
        workflow_name: str              = "",
        data_mounts:   Optional[Dict[str, str]] = None,
        limits:        Optional[ResourceLimits]  = None,
        env:           Optional[Dict[str, str]]  = None,
    ) -> ExecutionHandle:
        """Start a workflow execution.

        Args:
            user_id:       Owner of this execution (for quota/audit).
            workflow:       The workflow JSON dict.
            workflow_name:  Human-readable name (for logging/UI).
            data_mounts:    Mapping of repo paths → mount points inside the
                            execution environment.  e.g. {"user/data": "/data"}.
            limits:         CPU, memory, duration, network constraints.
            env:            Extra environment variables injected into the runtime.

        Returns:
            An ExecutionHandle with status 'pending' or 'running'.
        """

    @abstractmethod
    async def status(self, execution_id: str) -> ExecutionStatus:
        """Current status including progress, resource usage, active node."""

    @abstractmethod
    async def result(self, execution_id: str) -> ExecutionResult:
        """Final result after completion.  Raises if still running."""

    @abstractmethod
    async def cancel(self, execution_id: str) -> bool:
        """Request cancellation.  Returns True if the execution was running."""

    @abstractmethod
    async def cleanup(self, execution_id: str) -> bool:
        """Release resources (container, temp files, etc.).  Idempotent."""

    # ── Query ────────────────────────────────────────────────────

    @abstractmethod
    async def list_running(self, user_id: Optional[str] = None) -> List[ExecutionHandle]:
        """All currently running executions, optionally filtered by user."""

    @abstractmethod
    async def list_all(
        self, user_id: Optional[str] = None,
        status_filter: Optional[str] = None,
        offset: int = 0, limit: int = 50,
    ) -> List[ExecutionHandle]:
        """Paginated execution history with optional filters."""

    @abstractmethod
    async def logs(self, execution_id: str, tail: int = 100) -> str:
        """Last *tail* lines of execution logs (stdout + stderr)."""

    # ── Events (optional) ────────────────────────────────────────

    async def stream_events(
        self, execution_id: str
    ) -> AsyncIterator[Dict[str, Any]]:
        """Async iterator of execution events (node started, completed, etc.).
        Default: yields nothing (providers that don't support streaming)."""
        return
        yield  # make this a generator

    # ── Provider lifecycle ───────────────────────────────────────

    async def initialize(self) -> None:
        """Called once on server startup.  Set up pools, connections, etc."""

    async def shutdown(self) -> None:
        """Called on server shutdown.  Clean up resources."""

    async def health_check(self) -> Dict[str, Any]:
        """Return provider health info (connected, pool size, etc.)."""
        return {"status": "ok", "provider": self.__class__.__name__}
