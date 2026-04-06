from __future__ import annotations

import asyncio
import importlib
import json
import os
import shutil
import sys
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import PlainTextResponse


PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = PROJECT_ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(1, str(PROJECT_ROOT))


from platform_prod.runtime_contract import (
    ENV_ASSET_PATH,
    ENV_EXECUTION_ID,
    OUTPUTS_FILE_NAME,
    STATUS_FILE_NAME,
)


def _minimal_workflow_payload() -> dict:
    return {
        "type": "workflow",
        "options": {
            "name": "Prod Surface Workflow",
            "description": "Minimal workflow for full-app prod surface tests",
        },
        "nodes": [
            {
                "type": "start_flow",
                "extra": {"pos": [40, 120], "name": "Start"},
            },
            {
                "type": "end_flow",
                "extra": {"pos": [280, 120], "name": "End"},
            },
        ],
        "edges": [
            {
                "source": 0,
                "target": 1,
                "source_slot": "flow_out",
                "target_slot": "flow_in",
            }
        ],
    }


def _build_mock_identity_service() -> FastAPI:
    app = FastAPI()

    users_by_id: dict[str, dict] = {}
    user_ids_by_name: dict[str, str] = {}
    active_tokens: dict[str, str] = {}
    passwords: dict[str, str] = {}
    profiles: dict[str, dict] = {}
    quotas: dict[str, dict] = {}

    def _bundle(user_id: str) -> dict:
        return {
            "user": users_by_id[user_id],
            "profile": profiles[user_id],
            "quota": quotas[user_id],
        }

    def _authorized_user_id(request: Request) -> str | None:
        header = request.headers.get("authorization", "").strip()
        if not header.startswith("Bearer "):
            return None
        token = header.removeprefix("Bearer ").strip()
        return active_tokens.get(token)

    @app.post("/api/platform/auth/status")
    async def auth_status():
        return {"enabled": True, "provider": "django-mock", "has_users": bool(users_by_id)}

    @app.post("/api/platform/auth/login")
    async def auth_login(request: Request):
        body = await request.json()
        username = str(body.get("username", "") or "").strip()
        password = str(body.get("password", "") or "")
        user_id = user_ids_by_name.get(username)
        if not user_id or passwords.get(user_id) != password:
            raise HTTPException(status_code=401, detail="Invalid credentials")
        token = f"django-token-{user_id}"
        active_tokens[token] = user_id
        return {"token": token, "user": users_by_id[user_id]}

    @app.post("/api/platform/auth/authenticate")
    async def auth_authenticate(request: Request):
        user_id = _authorized_user_id(request)
        if not user_id:
            raise HTTPException(status_code=401, detail="Not authenticated")
        return {"user": users_by_id[user_id]}

    @app.post("/api/platform/auth/logout")
    async def auth_logout(request: Request):
        body = await request.json()
        token = str(body.get("token", "") or "").strip()
        existed = token in active_tokens
        active_tokens.pop(token, None)
        return {"ok": existed}

    @app.post("/api/platform/auth/change-password")
    async def auth_change_password(request: Request):
        body = await request.json()
        user_id = str(body.get("user_id", "") or "").strip()
        current_password = str(body.get("current_password", "") or "")
        new_password = str(body.get("new_password", "") or "")
        if not user_id or passwords.get(user_id) != current_password:
            raise HTTPException(status_code=403, detail="Current password is incorrect")
        passwords[user_id] = new_password
        active_tokens.clear()
        return {"ok": True}

    @app.post("/api/platform/users/create")
    async def users_create(request: Request):
        body = await request.json()
        username = str(body.get("username", "") or "").strip()
        email = str(body.get("email", "") or "").strip()
        password = str(body.get("password", "") or "")
        if not username or not email or not password:
            raise HTTPException(status_code=400, detail="Missing required fields")
        if username in user_ids_by_name:
            raise HTTPException(status_code=409, detail="Username already exists")

        user_id = f"user_{len(users_by_id) + 1}"
        user = {
            "id": user_id,
            "username": username,
            "email": email,
            "role": "admin" if not users_by_id else "user",
            "active": True,
            "created_at": float(len(users_by_id) + 1),
            "metadata": {},
        }
        users_by_id[user_id] = user
        user_ids_by_name[username] = user_id
        passwords[user_id] = password
        profiles[user_id] = {
            "user_id": user_id,
            "display_name": username,
            "bio": "",
            "avatar_url": "",
            "metadata": {},
        }
        quotas[user_id] = {
            "user_id": user_id,
            "cpu_seconds_remaining": 36000.0,
            "max_concurrent_runs": 5,
            "storage_bytes_remaining": 1073741824,
            "max_loop_hours": 24.0,
            "gpu_hours_remaining": 2.0,
            "max_spaces": 50,
            "max_assets_per_space": 10000,
        }
        return {"user": user}

    @app.post("/api/platform/users/by-username")
    async def users_by_username(request: Request):
        body = await request.json()
        username = str(body.get("username", "") or "").strip()
        user_id = user_ids_by_name.get(username)
        if not user_id:
            raise HTTPException(status_code=404, detail="Not found")
        return {"user": users_by_id[user_id]}

    @app.post("/api/platform/users/list")
    async def users_list(request: Request):
        body = await request.json()
        limit = int(body.get("limit", 50) or 50)
        active_only = bool(body.get("active_only", True))
        users = [user for user in users_by_id.values() if (user.get("active", True) or not active_only)]
        return {"users": users[:limit], "count": min(len(users), limit)}

    @app.post("/api/platform/users/{user_id}")
    async def users_get(user_id: str):
        if user_id not in users_by_id:
            raise HTTPException(status_code=404, detail="Not found")
        return _bundle(user_id)

    @app.post("/api/platform/users/{user_id}/update")
    async def users_update(user_id: str, request: Request):
        if user_id not in users_by_id:
            raise HTTPException(status_code=404, detail="Not found")
        body = await request.json()
        user = users_by_id[user_id]
        for key in ("username", "email", "role", "active", "metadata"):
            if key in body:
                user[key] = body[key]
        return {"user": user}

    @app.post("/api/platform/users/{user_id}/delete")
    async def users_delete(user_id: str):
        if user_id not in users_by_id:
            raise HTTPException(status_code=404, detail="Not found")
        users_by_id[user_id]["active"] = False
        return {"ok": True}

    @app.post("/api/platform/users/{user_id}/profile")
    async def users_profile(user_id: str, request: Request):
        if user_id not in users_by_id:
            raise HTTPException(status_code=404, detail="Not found")
        body = await request.json()
        profile = profiles[user_id]
        for key in ("display_name", "bio", "avatar_url", "metadata"):
            if key in body:
                profile[key] = body[key]
        return {"profile": profile}

    @app.post("/api/platform/users/{user_id}/quota")
    async def users_quota(user_id: str, request: Request):
        if user_id not in users_by_id:
            raise HTTPException(status_code=404, detail="Not found")
        body = await request.json()
        quota = quotas[user_id]
        quota.update(body)
        return {"quota": quota}

    return app


def _build_mock_docker_service(state: dict) -> FastAPI:
    app = FastAPI()
    containers: dict[str, dict] = {}

    def _env_map(items: list[str]) -> dict[str, str]:
        result = {}
        for item in items or []:
            if "=" not in item:
                continue
            key, value = item.split("=", 1)
            result[key] = value
        return result

    def _host_bind(spec: dict, container_mount: str, mode: str) -> Path:
        suffix = f":{container_mount}:{mode}"
        for bind in (spec.get("HostConfig", {}) or {}).get("Binds", []) or []:
            if isinstance(bind, str) and bind.endswith(suffix):
                return Path(bind[: -len(suffix)]).resolve()
        raise AssertionError(f"Bind for {container_mount} with mode {mode} not found")

    def _write_success_artifacts(spec: dict) -> None:
        env = _env_map(spec.get("Env", []))
        artifact_root = _host_bind(spec, "/artifacts", "rw")
        artifact_root.mkdir(parents=True, exist_ok=True)
        execution_id = env.get(ENV_EXECUTION_ID, "")
        asset_path = env.get(ENV_ASSET_PATH, "workflow.json")
        engine_execution_id = f"engine_{execution_id}"

        outputs = {
            "execution": {
                "status": "completed",
                "engine_execution_id": engine_execution_id,
                "workflow_name": f"Prod Surface Workflow_{execution_id}",
                "start_time": "2026-04-04T10:00:00",
                "end_time": "2026-04-04T10:00:01",
                "error": None,
            },
            "node_outputs": {
                "0": {"flow_out": None},
                "1": {"flow_out": {}},
            },
            "runtime": {
                "execution_id": execution_id,
                "asset_path": asset_path,
                "workspace_dir": "/workspace",
                "artifacts_dir": "/artifacts",
            },
            "workflow": {
                "type": "workflow",
                "name": "Prod Surface Workflow",
                "node_count": 2,
                "edge_count": 1,
            },
        }
        status = {
            "state": "completed",
            "contract_version": "1",
            "execution_id": execution_id,
            "engine_execution_id": engine_execution_id,
            "node_output_keys": ["0", "1"],
        }
        (artifact_root / OUTPUTS_FILE_NAME).write_text(json.dumps(outputs), encoding="utf-8")
        (artifact_root / STATUS_FILE_NAME).write_text(json.dumps(status), encoding="utf-8")

    @app.get("/_ping")
    async def ping():
        return PlainTextResponse("OK")

    @app.post("/v1.41/containers/create")
    async def containers_create(request: Request):
        spec = await request.json()
        container_id = f"container_{len(containers) + 1}"
        containers[container_id] = {
            "id": container_id,
            "name": request.query_params.get("name", container_id),
            "spec": spec,
            "state": {
                "Status": "created",
                "ExitCode": 0,
                "StartedAt": "2026-04-04T10:00:00Z",
                "FinishedAt": "0001-01-01T00:00:00Z",
                "Error": "",
            },
        }
        state["last_created_spec"] = spec
        state["last_container_id"] = container_id
        return {"Id": container_id, "Warnings": []}

    @app.post("/v1.41/containers/{container_id}/start")
    async def container_start(container_id: str):
        container = containers[container_id]
        _write_success_artifacts(container["spec"])
        container["state"] = {
            "Status": "exited",
            "ExitCode": 0,
            "StartedAt": "2026-04-04T10:00:00Z",
            "FinishedAt": "2026-04-04T10:00:01Z",
            "Error": "",
        }
        return PlainTextResponse("", status_code=204)

    @app.get("/v1.41/containers/{container_id}/json")
    async def container_json(container_id: str):
        container = containers.get(container_id)
        if container is None:
            raise HTTPException(status_code=404, detail="Not found")
        return {"Id": container_id, "State": dict(container["state"])}

    @app.post("/v1.41/containers/{container_id}/stop")
    async def container_stop(container_id: str):
        container = containers.get(container_id)
        if container is None:
            raise HTTPException(status_code=404, detail="Not found")
        container["state"] = {
            "Status": "exited",
            "ExitCode": 137,
            "StartedAt": "2026-04-04T10:00:00Z",
            "FinishedAt": "2026-04-04T10:00:02Z",
            "Error": "",
        }
        return PlainTextResponse("", status_code=204)

    @app.delete("/v1.41/containers/{container_id}")
    async def container_delete(container_id: str):
        state.setdefault("deleted_container_ids", []).append(container_id)
        containers.pop(container_id, None)
        return PlainTextResponse("", status_code=204)

    @app.get("/v1.41/containers/{container_id}/logs")
    async def container_logs(container_id: str):
        if container_id not in containers:
            raise HTTPException(status_code=404, detail="Not found")
        return PlainTextResponse("prod runtime log line 1\nprod runtime log line 2\n")

    return app


@unittest.skipUnless(shutil.which("git"), "git is required for prod app surface tests")
class ProdAppSurfaceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._root = PROJECT_ROOT / "storage" / "_test_runs" / f"prod_surface_{uuid.uuid4().hex[:8]}"
        self._root.mkdir(parents=True, exist_ok=True)
        self._runtime_root = self._root / "runtime"
        self._platform_config = self._root / "platform_backend.json"
        self._db_path = self._root / "platform.db"
        self._spaces_root = self._root / "spaces"
        self._artifacts_root = self._root / "artifacts"

        self._platform_config.write_text(
            json.dumps(
                {
                    "backend": "prod",
                    "prod": {
                        "database": {"url": f"sqlite:///{self._db_path.as_posix()}"},
                        "identity": {
                            "base_url": "http://django.test",
                            "identity_prefix": "/api/platform",
                            "healthcheck_path": "/auth/status",
                            "timeout_seconds": 5.0,
                            "verify_tls": False,
                            "token_header": "Authorization",
                            "token_scheme": "Bearer",
                            "require_available_on_startup": True,
                        },
                        "git": {"repos_root": str(self._spaces_root)},
                        "artifacts": {"root_path": str(self._artifacts_root)},
                        "runtime": {
                            "base_url": "http://docker.test",
                            "healthcheck_path": "/_ping",
                            "verify_tls": False,
                            "timeout_seconds": 5.0,
                            "require_available_on_startup": True,
                            "default_image": "numel-runtime:prod-test",
                        },
                    },
                },
                indent=2,
            ),
            encoding="utf-8",
        )

        self._env_backup = {
            "NUMEL_DATA_ROOT": os.environ.get("NUMEL_DATA_ROOT"),
            "NUMEL_PLATFORM_CONFIG": os.environ.get("NUMEL_PLATFORM_CONFIG"),
        }
        os.environ["NUMEL_DATA_ROOT"] = str(self._runtime_root)
        os.environ["NUMEL_PLATFORM_CONFIG"] = str(self._platform_config)

        runtime_settings = importlib.import_module("runtime_settings")
        runtime_settings.get_runtime_settings.cache_clear()

        self._identity_service = _build_mock_identity_service()
        self._docker_state: dict[str, object] = {}
        self._docker_service = _build_mock_docker_service(self._docker_state)
        self._identity_transport = httpx.ASGITransport(app=self._identity_service)
        self._docker_transport = httpx.ASGITransport(app=self._docker_service)

        self._identity_module = importlib.import_module("platform_prod.django_identity")
        self._runtime_module = importlib.import_module("platform_prod.docker_runtime")
        self._original_identity_init = self._identity_module.DjangoIdentityProvider.__init__
        self._original_runtime_init = self._runtime_module.DockerApiRuntimeProvider.__init__

        identity_transport = self._identity_transport
        runtime_transport = self._docker_transport
        original_identity_init = self._original_identity_init
        original_runtime_init = self._original_runtime_init

        def _patched_identity_init(instance, config, db_config=None, audit_log=None, *, transport=None):
            return original_identity_init(
                instance,
                config,
                db_config=db_config,
                audit_log=audit_log,
                transport=transport or identity_transport,
            )

        def _patched_runtime_init(
            instance,
            config,
            git_store,
            execution_registry=None,
            artifact_config=None,
            audit_log=None,
            space_provider=None,
            identity_provider=None,
            secrets_provider=None,
            *,
            transport=None,
        ):
            return original_runtime_init(
                instance,
                config,
                git_store,
                execution_registry=execution_registry,
                artifact_config=artifact_config,
                audit_log=audit_log,
                space_provider=space_provider,
                identity_provider=identity_provider,
                secrets_provider=secrets_provider,
                transport=transport or runtime_transport,
            )

        self._identity_module.DjangoIdentityProvider.__init__ = _patched_identity_init
        self._runtime_module.DockerApiRuntimeProvider.__init__ = _patched_runtime_init

        if "app" in sys.modules:
            del sys.modules["app"]
        self._app_module = importlib.import_module("app")
        self._app = await self._app_module.build_app(
            SimpleNamespace(port=18900, seed=0, tunnel=False)
        )
        self._client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self._app),
            base_url="http://numel.test",
        )

    async def asyncTearDown(self) -> None:
        await self._client.aclose()
        await self._app.state.shutdown_runtime()

        self._identity_module.DjangoIdentityProvider.__init__ = self._original_identity_init
        self._runtime_module.DockerApiRuntimeProvider.__init__ = self._original_runtime_init

        for key, value in self._env_backup.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

        runtime_settings = importlib.import_module("runtime_settings")
        runtime_settings.get_runtime_settings.cache_clear()
        shutil.rmtree(self._root, ignore_errors=True)

    def _auth_headers(self, token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}"}

    async def test_prod_backend_runs_workflow_through_app_surface(self) -> None:
        ready = await self._client.get("/health/ready")
        self.assertEqual(ready.status_code, 200, ready.text)
        self.assertEqual(ready.json()["status"], "ready")
        self.assertEqual(self._app.state.platform_backend, "prod")

        register = await self._client.post(
            "/auth/register",
            json={"username": "alice", "email": "alice@local", "password": "pass1234"},
        )
        self.assertEqual(register.status_code, 200, register.text)
        payload = register.json()
        token = payload["token"]
        headers = self._auth_headers(token)
        self.assertEqual(payload["user"]["role"], "admin")

        current_space = await self._client.post("/spaces/current", json={}, headers=headers)
        self.assertEqual(current_space.status_code, 200, current_space.text)
        space = current_space.json()["space"]
        self.assertTrue(space["id"])

        save = await self._client.post(
            "/workflow/save",
            json={"workflow": _minimal_workflow_payload()},
            headers=headers,
        )
        self.assertEqual(save.status_code, 200, save.text)
        self.assertEqual(save.json()["status"], "saved")

        user_secret = await self._client.post(
            "/credentials/API_KEY",
            json={"value": "user-secret"},
            headers=headers,
        )
        self.assertEqual(user_secret.status_code, 200, user_secret.text)
        space_secret = await self._client.post(
            "/credentials/SPACE_TOKEN",
            json={"value": "space-secret", "space_id": space["id"]},
            headers=headers,
        )
        self.assertEqual(space_secret.status_code, 200, space_secret.text)

        start = await self._client.post("/workflow/start", json={}, headers=headers)
        self.assertEqual(start.status_code, 200, start.text)
        execution_id = start.json()["execution_id"]
        self.assertTrue(execution_id)

        final_status = start.json()["status"]
        for _ in range(10):
            state = await self._client.post(f"/executions/{execution_id}", json={}, headers=headers)
            self.assertEqual(state.status_code, 200, state.text)
            final_status = state.json()["state"]["status"]
            if final_status in {"completed", "failed", "cancelled"}:
                break
            await asyncio.sleep(0.05)

        self.assertEqual(final_status, "completed")

        results = await self._client.post(f"/executions/{execution_id}/results", json={}, headers=headers)
        self.assertEqual(results.status_code, 200, results.text)
        self.assertEqual(results.json()["status"], "completed")
        self.assertIn("1", results.json()["node_outputs"])

        listing = await self._client.post("/executions/list", json={}, headers=headers)
        self.assertEqual(listing.status_code, 200, listing.text)
        self.assertIn(execution_id, listing.json()["execution_ids"])

        created_spec = self._docker_state.get("last_created_spec")
        self.assertIsInstance(created_spec, dict)
        self.assertEqual(created_spec["Image"], "numel-runtime:prod-test")
        self.assertIn(f"{ENV_ASSET_PATH}=workflow.json", created_spec["Env"])
        self.assertTrue(any(item.startswith(f"{ENV_EXECUTION_ID}=") for item in created_spec["Env"]))
        self.assertIn("API_KEY=user-secret", created_spec["Env"])
        self.assertIn("SPACE_TOKEN=space-secret", created_spec["Env"])

        artifact_status_files = list((self._artifacts_root / "executions").glob("*/artifacts/status.json"))
        self.assertTrue(artifact_status_files)
        artifact_payload = json.loads(artifact_status_files[0].read_text(encoding="utf-8"))
        self.assertEqual(artifact_payload["state"], "completed")

        job_spec_files = list((self._artifacts_root / "executions").glob("*/job_spec.json"))
        self.assertTrue(job_spec_files)
        job_spec = json.loads(job_spec_files[0].read_text(encoding="utf-8"))
        self.assertIn("API_KEY=***REDACTED***", job_spec["Env"])
        self.assertIn("SPACE_TOKEN=***REDACTED***", job_spec["Env"])
        self.assertNotIn("API_KEY=user-secret", job_spec["Env"])
        self.assertNotIn("SPACE_TOKEN=space-secret", job_spec["Env"])

    async def test_admin_diagnostics_surface_prod(self) -> None:
        register = await self._client.post(
            "/auth/register",
            json={"username": "opsadmin", "email": "opsadmin@local", "password": "pass1234"},
        )
        self.assertEqual(register.status_code, 200, register.text)
        payload = register.json()
        self.assertEqual(payload["user"]["role"], "admin")
        headers = self._auth_headers(payload["token"])

        user_secret = await self._client.post(
            "/credentials/API_KEY",
            json={"value": "user-secret"},
            headers=headers,
        )
        self.assertEqual(user_secret.status_code, 200, user_secret.text)

        diagnostics = await self._client.post("/admin/diagnostics", json={}, headers=headers)
        self.assertEqual(diagnostics.status_code, 200, diagnostics.text)
        data = diagnostics.json()

        self.assertEqual(data["backend"], "prod")
        self.assertEqual(data["status"], "ready")
        self.assertEqual(data["platform"]["auth"]["provider"], "DjangoIdentityProvider")
        self.assertEqual(data["backend_config"]["runtime"]["default_image"], "numel-runtime:prod-test")
        self.assertTrue(data["runtime"]["paths"])
        self.assertNotIn("user-secret", json.dumps(data))
