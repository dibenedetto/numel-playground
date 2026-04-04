from __future__ import annotations

import asyncio
import json
import shutil
import sys
import time
import unittest
import uuid
from pathlib import Path

import httpx


PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = PROJECT_ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(1, str(PROJECT_ROOT))


from domain.models import (
    AssetKind,
    ExecutionRecord,
    ExecutionRequest,
    ExecutionState,
    PermissionPolicy,
    RuntimeProfile,
    SpaceAsset,
    Visibility,
)
from platform_local import ArtifactStorageConfig, DatabaseConfig, GitStorageConfig, SecretsConfig
from platform_local.config import DockerRuntimeConfig
from platform_local.db_audit import DbAuditLog
from platform_local.db_execution_registry import DbExecutionRegistry
from platform_local.db_friend_graph import DbFriendGraphProvider
from platform_local.db_git_spaces import DbGitSpaceProvider
from platform_local.db_secrets import DbSecretsProvider
from platform_local.git_space_store import GitSpaceStore
from platform_prod.docker_runtime import DockerApiRuntimeProvider
from platform_prod.runtime_contract import (
    DEFAULT_CONTAINER_COMMAND,
    ENV_CONTRACT_VERSION,
    ENV_OUTPUTS_PATH,
    ENV_STATUS_PATH,
    OUTPUTS_FILE_NAME,
    STATUS_FILE_NAME,
)


def _workflow_bytes() -> bytes:
    return json.dumps(
        {
            "type": "workflow",
            "options": {"name": "Prod Runtime Workflow"},
            "nodes": [
                {"type": "start_flow", "extra": {"pos": [40, 120], "name": "Start"}},
                {"type": "end_flow", "extra": {"pos": [280, 120], "name": "End"}},
            ],
            "edges": [
                {"source": 0, "target": 1, "source_slot": "flow_out", "target_slot": "flow_in"}
            ],
        }
    ).encode("utf-8")


class _QuotaIdentity:
    def __init__(
        self,
        *,
        max_concurrent_runs: int = 5,
        gpu_hours_remaining: float = 2.0,
        max_loop_hours: float = 24.0,
    ):
        self.max_concurrent_runs = max_concurrent_runs
        self.gpu_hours_remaining = gpu_hours_remaining
        self.max_loop_hours = max_loop_hours

    async def get_quota(self, user_id: str):
        return type(
            "Quota",
            (),
            {
                "user_id": user_id,
                "max_concurrent_runs": self.max_concurrent_runs,
                "gpu_hours_remaining": self.gpu_hours_remaining,
                "max_loop_hours": self.max_loop_hours,
            },
        )()


@unittest.skipUnless(shutil.which("git"), "git is required for production runtime tests")
class DockerApiRuntimeProviderTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._root = PROJECT_ROOT / "storage" / "_test_runs" / f"prod_runtime_{uuid.uuid4().hex[:8]}"
        self._root.mkdir(parents=True, exist_ok=True)
        self._db_path = self._root / "platform.db"
        self._spaces_root = self._root / "spaces"
        self._artifacts_root = self._root / "artifacts"

        self._db_config = DatabaseConfig(url=f"sqlite:///{self._db_path.as_posix()}")
        self._git_config = GitStorageConfig(repos_root=str(self._spaces_root))
        self._artifact_config = ArtifactStorageConfig(root_path=str(self._artifacts_root))
        self._audit_log = DbAuditLog(self._db_config)
        self._execution_registry = DbExecutionRegistry(self._db_config)
        self._git_store = GitSpaceStore(self._git_config)
        self._friend_graph = DbFriendGraphProvider(self._db_config, audit_log=self._audit_log)
        self._secrets = DbSecretsProvider(SecretsConfig(), db_config=self._db_config, audit_log=self._audit_log)
        self._identity = _QuotaIdentity()
        self._spaces = DbGitSpaceProvider(
            db_config=self._db_config,
            git_store=self._git_store,
            artifact_config=self._artifact_config,
            friend_graph=self._friend_graph,
            audit_log=self._audit_log,
        )

        self._container_state = {
            "Status": "running",
            "ExitCode": 0,
            "StartedAt": "2026-04-03T11:00:00Z",
            "FinishedAt": "0001-01-01T00:00:00Z",
            "Error": "",
        }
        self._created_spec = None
        self._created_name = None
        self._stopped = False
        self._deleted = False

        def _handler(request: httpx.Request) -> httpx.Response:
            path = request.url.path
            if path == "/_ping":
                return httpx.Response(200, text="OK")
            if path == "/v1.41/containers/create":
                self._created_name = request.url.params.get("name")
                self._created_spec = json.loads(request.content.decode("utf-8"))
                return httpx.Response(201, json={"Id": "container_1", "Warnings": []})
            if path == "/v1.41/containers/container_1/start":
                return httpx.Response(204)
            if path == "/v1.41/containers/container_1/json":
                return httpx.Response(200, json={"Id": "container_1", "State": dict(self._container_state)})
            if path == "/v1.41/containers/container_1/stop":
                self._stopped = True
                self._container_state = {
                    "Status": "exited",
                    "ExitCode": 137,
                    "StartedAt": "2026-04-03T11:00:00Z",
                    "FinishedAt": "2026-04-03T11:05:00Z",
                    "Error": "",
                }
                return httpx.Response(204)
            if path == "/v1.41/containers/container_1" and request.method == "DELETE":
                self._deleted = True
                return httpx.Response(204)
            if path == "/v1.41/containers/container_1/logs":
                return httpx.Response(200, text="runtime log line 1\nruntime log line 2\n")
            return httpx.Response(404, text=f"Unhandled path: {path}")

        self._runtime = DockerApiRuntimeProvider(
            config=DockerRuntimeConfig(
                base_url="http://docker.test",
                default_image="numel-runtime:test",
                default_gpu_image="numel-runtime:cuda",
                verify_tls=False,
                timeout_seconds=5.0,
                require_available_on_startup=True,
            ),
            git_store=self._git_store,
            execution_registry=self._execution_registry,
            artifact_config=self._artifact_config,
            audit_log=self._audit_log,
            space_provider=self._spaces,
            identity_provider=self._identity,
            secrets_provider=self._secrets,
            transport=httpx.MockTransport(_handler),
        )

        self._space = await self._spaces.create_space(
            owner_user_id="user_1",
            slug="home",
            title="Home",
            visibility=Visibility.PRIVATE,
        )
        self._asset = SpaceAsset(
            id="",
            space_id=self._space.id,
            path="workflow.json",
            kind=AssetKind.WORKFLOW,
            owner_user_id="user_1",
            title="Workflow",
            visibility=Visibility.PRIVATE,
            executable=True,
            policy=PermissionPolicy(owner_user_id="user_1", visibility=Visibility.PRIVATE),
        )
        await self._spaces.write_asset(
            "user_1",
            self._space.id,
            self._asset,
            _workflow_bytes(),
            message="Add workflow",
        )

    async def asyncTearDown(self) -> None:
        await self._runtime.aclose()
        shutil.rmtree(self._root, ignore_errors=True)

    async def test_start_execution_builds_container_contract_and_tracks_completion(self) -> None:
        status = await self._runtime.startup_validate()
        self.assertTrue(status["checked"])
        self.assertEqual(status["service_status"]["response"], "OK")

        runtime_profile = RuntimeProfile(
            id="runtime_1",
            owner_user_id="user_1",
            name="Prod",
            image="numel-runtime:test",
            network_enabled=False,
            max_memory_bytes=134217728,
            metadata={"container_command": ["python", "-m", "numel_runner"]},
        )
        record = await self._runtime.start_execution(
            ExecutionRequest(
                user_id="user_1",
                space_id=self._space.id,
                asset_path="workflow.json",
                credential_names=["API_KEY"],
                inputs={"foo": "bar"},
            ),
            runtime=runtime_profile,
            env={"API_KEY": "secret-value"},
        )

        self.assertEqual(record.status.value, "running")
        self.assertEqual(record.metadata["container_id"], "container_1")
        self.assertEqual(self._created_name, record.metadata["container_name"])
        self.assertEqual(self._created_spec["Image"], "numel-runtime:test")
        self.assertEqual(self._created_spec["HostConfig"]["NetworkMode"], "none")
        self.assertTrue(self._created_spec["HostConfig"]["ReadonlyRootfs"])
        self.assertEqual(self._created_spec["HostConfig"]["CapDrop"], ["ALL"])
        self.assertEqual(self._created_spec["HostConfig"]["SecurityOpt"], ["no-new-privileges"])
        self.assertEqual(self._created_spec["HostConfig"]["PidsLimit"], 256)
        self.assertEqual(
            self._created_spec["HostConfig"]["Tmpfs"],
            {
                "/tmp": "rw,noexec,nosuid,nodev,size=64m",
                "/run": "rw,noexec,nosuid,nodev,size=16m",
            },
        )
        self.assertIn("API_KEY=secret-value", self._created_spec["Env"])
        self.assertEqual(self._created_spec["Cmd"], ["python", "-m", "numel_runner"])
        self.assertTrue(any(item.startswith(f"{ENV_CONTRACT_VERSION}=") for item in self._created_spec["Env"]))
        self.assertIn(f"{ENV_OUTPUTS_PATH}=/artifacts/{OUTPUTS_FILE_NAME}", self._created_spec["Env"])
        self.assertIn(f"{ENV_STATUS_PATH}=/artifacts/{STATUS_FILE_NAME}", self._created_spec["Env"])
        self.assertTrue(Path(record.metadata["snapshot_dir"]).is_dir())
        self.assertTrue(Path(record.metadata["artifact_dir"]).is_dir())

        outputs_path = Path(record.metadata["artifact_dir"]) / OUTPUTS_FILE_NAME
        outputs_path.write_text(json.dumps({"result": {"value": 42}}), encoding="utf-8")
        (Path(record.metadata["artifact_dir"]) / STATUS_FILE_NAME).write_text(
            json.dumps({"state": "completed", "contract_version": "1"}),
            encoding="utf-8",
        )
        self._container_state = {
            "Status": "exited",
            "ExitCode": 0,
            "StartedAt": "2026-04-03T11:00:00Z",
            "FinishedAt": "2026-04-03T11:10:00Z",
            "Error": "",
        }

        completed = await self._runtime.get_execution(record.execution_id)
        self.assertIsNotNone(completed)
        self.assertEqual(completed.status.value, "completed")
        self.assertEqual(completed.outputs["result"]["value"], 42)
        self.assertEqual(completed.metadata["runtime_status"]["state"], "completed")
        self.assertTrue(self._deleted)
        self.assertFalse(Path(record.metadata["snapshot_dir"]).exists())

        logs = await self._runtime.get_logs(record.execution_id)
        self.assertTrue("runtime log line 1" in logs or "execution_id=" in logs)

    async def test_cancel_execution_stops_container_and_marks_record(self) -> None:
        record = await self._runtime.start_execution(
            ExecutionRequest(
                user_id="user_1",
                space_id=self._space.id,
                asset_path="workflow.json",
            )
        )
        cancelled = await self._runtime.cancel_execution(record.execution_id)
        self.assertTrue(cancelled)
        self.assertTrue(self._stopped)

        updated = await self._runtime.get_execution(record.execution_id)
        self.assertIsNotNone(updated)
        self.assertEqual(updated.status.value, "cancelled")
        self.assertEqual(updated.error, "Cancelled by user")
        self.assertTrue(self._deleted)

    async def test_start_execution_uses_contract_default_command_when_no_override_is_configured(self) -> None:
        record = await self._runtime.start_execution(
            ExecutionRequest(
                user_id="user_1",
                space_id=self._space.id,
                asset_path="workflow.json",
            )
        )
        self.assertEqual(record.status.value, "running")
        self.assertEqual(self._created_spec["Cmd"], list(DEFAULT_CONTAINER_COMMAND))

    async def test_gpu_enabled_runtime_requests_gpu_devices_and_uses_gpu_image(self) -> None:
        record = await self._runtime.start_execution(
            ExecutionRequest(
                user_id="user_1",
                space_id=self._space.id,
                asset_path="workflow.json",
            ),
            runtime=RuntimeProfile(
                id="runtime_gpu",
                owner_user_id="user_1",
                name="CUDA",
                gpu_enabled=True,
                network_enabled=False,
            ),
        )
        self.assertEqual(record.status.value, "running")
        self.assertEqual(self._created_spec["Image"], "numel-runtime:cuda")
        self.assertEqual(
            self._created_spec["HostConfig"]["DeviceRequests"],
            [{"Driver": "nvidia", "Count": -1, "Capabilities": [["gpu"]]}],
        )

    async def test_start_execution_resolves_and_redacts_credentials(self) -> None:
        await self._secrets.set_credential("user_1", "API_KEY", "user-secret")
        await self._secrets.set_credential("user_1", "SPACE_TOKEN", "space-secret", space_id=self._space.id)

        record = await self._runtime.start_execution(
            ExecutionRequest(
                user_id="user_1",
                space_id=self._space.id,
                asset_path="workflow.json",
                credential_names=["API_KEY", "SPACE_TOKEN"],
                metadata={"secret_space_id": self._space.id},
            )
        )

        self.assertEqual(record.status.value, "running")
        self.assertIn("API_KEY=user-secret", self._created_spec["Env"])
        self.assertIn("SPACE_TOKEN=space-secret", self._created_spec["Env"])
        self.assertEqual(sorted(record.metadata["resolved_credential_names"]), ["API_KEY", "SPACE_TOKEN"])

        job_spec = json.loads(
            (self._artifacts_root / "executions" / record.execution_id / "job_spec.json").read_text(encoding="utf-8")
        )
        self.assertIn("API_KEY=***REDACTED***", job_spec["Env"])
        self.assertIn("SPACE_TOKEN=***REDACTED***", job_spec["Env"])
        self.assertNotIn("API_KEY=user-secret", job_spec["Env"])
        self.assertNotIn("SPACE_TOKEN=space-secret", job_spec["Env"])

    async def test_start_execution_enforces_concurrent_quota(self) -> None:
        self._identity.max_concurrent_runs = 1
        first = await self._runtime.start_execution(
            ExecutionRequest(
                user_id="user_1",
                space_id=self._space.id,
                asset_path="workflow.json",
            )
        )
        self.assertEqual(first.status.value, "running")

        with self.assertRaises(PermissionError) as ctx:
            await self._runtime.start_execution(
                ExecutionRequest(
                    user_id="user_1",
                    space_id=self._space.id,
                    asset_path="workflow.json",
                )
            )
        self.assertIn("concurrent execution limit", str(ctx.exception))

    async def test_running_execution_times_out_and_is_cleaned_up(self) -> None:
        record = await self._runtime.start_execution(
            ExecutionRequest(
                user_id="user_1",
                space_id=self._space.id,
                asset_path="workflow.json",
            ),
            runtime=RuntimeProfile(
                id="runtime_timeout",
                owner_user_id="user_1",
                name="Short",
                max_duration_seconds=0.01,
                network_enabled=False,
            ),
        )
        await asyncio.sleep(0.05)
        timed_out = await self._runtime.get_execution(record.execution_id)
        self.assertIsNotNone(timed_out)
        self.assertEqual(timed_out.status.value, "failed")
        self.assertIn("time limit", timed_out.error or "")
        self.assertTrue(timed_out.metadata.get("timed_out"))
        self.assertTrue(self._stopped)
        self.assertTrue(self._deleted)
        self.assertFalse(Path(record.metadata["snapshot_dir"]).exists())

    async def test_list_executions_prunes_expired_artifacts(self) -> None:
        execution_id = "exec_old_artifacts"
        execution_root = self._artifacts_root / "executions" / execution_id
        artifact_dir = execution_root / "artifacts"
        artifact_dir.mkdir(parents=True, exist_ok=True)
        now = time.time()
        await self._execution_registry.create_execution(
            ExecutionRecord(
                execution_id=execution_id,
                user_id="user_1",
                space_id=self._space.id,
                asset_path="workflow.json",
                ref="main",
                status=ExecutionState.COMPLETED,
                started_at=now - 120.0,
                finished_at=now - 60.0,
                metadata={"artifact_expires_at": now - 1.0, "artifacts_present": True},
            )
        )

        executions = await self._runtime.list_executions(user_id="user_1", limit=20)
        pruned = next(record for record in executions if record.execution_id == execution_id)
        self.assertFalse(execution_root.exists())
        self.assertFalse(pruned.metadata.get("artifacts_present", True))
        self.assertIn("artifacts_pruned_at", pruned.metadata)

