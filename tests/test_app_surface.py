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


PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = PROJECT_ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(1, str(PROJECT_ROOT))


def _minimal_workflow_payload() -> dict:
    return {
        "type": "workflow",
        "options": {
            "name": "Surface Workflow",
            "description": "Minimal workflow for full-app surface tests",
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


def _starter_hello_workflow_payload() -> dict:
    return {
        "type": "workflow",
        "options": {
            "type": "workflow_options",
            "name": "Hello Workflow",
            "description": "The simplest workflow: Start, Preview, End.",
        },
        "nodes": [
            {
                "type": "start_flow",
                "extra": {"pos": [60, 180], "name": "Start"},
            },
            {
                "type": "preview_flow",
                "extra": {"pos": [320, 180], "name": "Preview"},
            },
            {
                "type": "end_flow",
                "extra": {"pos": [580, 180], "name": "End"},
            },
        ],
        "edges": [
            {
                "source": 0,
                "target": 1,
                "source_slot": "flow_out",
                "target_slot": "flow_in",
            },
            {
                "source": 1,
                "target": 2,
                "source_slot": "flow_out",
                "target_slot": "flow_in",
            },
        ],
    }
class AppSurfaceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._root = PROJECT_ROOT / "storage" / "_test_runs" / f"app_{uuid.uuid4().hex[:8]}"
        self._root.mkdir(parents=True, exist_ok=True)
        self._runtime_root = self._root / "runtime"
        self._platform_config = self._root / "platform_backend.json"
        self._db_path = self._root / "platform.db"
        self._spaces_root = self._root / "spaces"
        self._artifacts_root = self._root / "artifacts"

        self._platform_config.write_text(
            json.dumps(
                {
                    "backend": "local",
                    "local": {
                        "database": {"url": f"sqlite:///{self._db_path.as_posix()}"},
                        "git": {"repos_root": str(self._spaces_root)},
                        "artifacts": {"root_path": str(self._artifacts_root)},
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

        if "app" in sys.modules:
            del sys.modules["app"]
        self._app_module = importlib.import_module("app")
        self._app = await self._app_module.build_app(
            SimpleNamespace(port=18700, seed=0, tunnel=False)
        )
        self._client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self._app),
            base_url="http://numel.test",
        )

    async def asyncTearDown(self) -> None:
        await self._client.aclose()
        await self._app.state.shutdown_runtime()

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

    async def test_health_and_auth_bootstrap_surface(self) -> None:
        live = await self._client.get("/health/live")
        self.assertEqual(live.status_code, 200, live.text)
        self.assertEqual(live.json()["status"], "alive")

        ready = await self._client.get("/health/ready")
        self.assertEqual(ready.status_code, 200, ready.text)
        self.assertEqual(ready.json()["status"], "ready")

        status_before = await self._client.post("/auth/status", json={})
        self.assertEqual(status_before.status_code, 200, status_before.text)
        self.assertFalse(status_before.json()["has_users"])

        register = await self._client.post(
            "/auth/register",
            json={"username": "alice", "email": "alice@local", "password": "pass1234"},
        )
        self.assertEqual(register.status_code, 200, register.text)
        payload = register.json()
        self.assertEqual(payload["user"]["role"], "admin")

        status_after = await self._client.post("/auth/status", json={})
        self.assertEqual(status_after.status_code, 200, status_after.text)
        self.assertTrue(status_after.json()["has_users"])

        me = await self._client.post("/auth/me", json={}, headers=self._auth_headers(payload["token"]))
        self.assertEqual(me.status_code, 200, me.text)
        self.assertEqual(me.json()["user"]["username"], "alice")

    async def test_spaces_workflow_and_execution_surface(self) -> None:
        register = await self._client.post(
            "/auth/register",
            json={"username": "alice", "email": "alice@local", "password": "pass1234"},
        )
        self.assertEqual(register.status_code, 200, register.text)
        token = register.json()["token"]
        headers = self._auth_headers(token)

        current_space = await self._client.post("/spaces/current", json={}, headers=headers)
        self.assertEqual(current_space.status_code, 200, current_space.text)
        space = current_space.json()["space"]
        self.assertTrue(space["id"])

        initial_workflow = await self._client.post("/workflow/get", json={}, headers=headers)
        self.assertEqual(initial_workflow.status_code, 200, initial_workflow.text)
        self.assertIsNone(initial_workflow.json()["workflow"])

        save = await self._client.post(
            "/workflow/save",
            json={"workflow": _minimal_workflow_payload()},
            headers=headers,
        )
        self.assertEqual(save.status_code, 200, save.text)
        self.assertEqual(save.json()["status"], "saved")

        reloaded = await self._client.post("/workflow/get", json={}, headers=headers)
        self.assertEqual(reloaded.status_code, 200, reloaded.text)
        self.assertEqual(reloaded.json()["workflow"]["options"]["name"], "Surface Workflow")

        start = await self._client.post("/workflow/start", json={}, headers=headers)
        self.assertEqual(start.status_code, 200, start.text)
        execution_id = start.json()["execution_id"]
        self.assertTrue(execution_id)

        final_status = start.json()["status"]
        for _ in range(60):
            state = await self._client.post(f"/executions/{execution_id}", json={}, headers=headers)
            self.assertEqual(state.status_code, 200, state.text)
            final_status = state.json()["state"]["status"]
            if final_status in {"completed", "failed", "cancelled"}:
                break
            await asyncio.sleep(0.2)

        self.assertEqual(final_status, "completed")

        listing = await self._client.post("/executions/list", json={}, headers=headers)
        self.assertEqual(listing.status_code, 200, listing.text)
        execution_ids = listing.json()["execution_ids"]
        self.assertIn(execution_id, execution_ids)

    async def test_admin_diagnostics_surface_local(self) -> None:
        register = await self._client.post(
            "/auth/register",
            json={"username": "admin", "email": "admin@local", "password": "pass1234"},
        )
        self.assertEqual(register.status_code, 200, register.text)
        payload = register.json()
        self.assertEqual(payload["user"]["role"], "admin")
        headers = self._auth_headers(payload["token"])

        save = await self._client.post(
            "/workflow/save",
            json={"workflow": _minimal_workflow_payload()},
            headers=headers,
        )
        self.assertEqual(save.status_code, 200, save.text)

        start = await self._client.post("/workflow/start", json={}, headers=headers)
        self.assertEqual(start.status_code, 200, start.text)
        execution_id = start.json()["execution_id"]
        self.assertTrue(execution_id)

        final_status = start.json()["status"]
        for _ in range(60):
            state = await self._client.post(f"/executions/{execution_id}", json={}, headers=headers)
            self.assertEqual(state.status_code, 200, state.text)
            final_status = state.json()["state"]["status"]
            if final_status in {"completed", "failed", "cancelled"}:
                break
            await asyncio.sleep(0.2)

        diagnostics = await self._client.post("/admin/diagnostics", json={}, headers=headers)
        self.assertEqual(diagnostics.status_code, 200, diagnostics.text)
        data = diagnostics.json()

        self.assertEqual(data["backend"], "local")
        self.assertEqual(data["status"], "ready")
        self.assertEqual(data["platform_config_path"], str(self._platform_config))
        self.assertIn("process", data)
        self.assertIn("platform", data)
        self.assertIn("runtime", data)
        self.assertIn("executions", data)
        self.assertTrue(data["runtime"]["paths"])
        self.assertEqual(data["platform"]["auth"]["has_users"], True)
        self.assertEqual(data["backend_config"]["database"]["url"], f"sqlite:///{self._db_path.as_posix()}")
        self.assertTrue(data["executions"]["available"])
        self.assertTrue(data["executions"]["recent"])
        self.assertTrue(data["executions"]["recent"][0]["execution_id"].startswith("exec_"))
        self.assertEqual(data["executions"]["recent"][0]["asset_path"], "workflow.json")
        self.assertEqual(data["executions"]["recent"][0]["status"], "completed")

    async def test_admin_execution_detail_surface_local(self) -> None:
        register = await self._client.post(
            "/auth/register",
            json={"username": "admin", "email": "admin@local", "password": "pass1234"},
        )
        self.assertEqual(register.status_code, 200, register.text)
        headers = self._auth_headers(register.json()["token"])

        save = await self._client.post(
            "/workflow/save",
            json={"workflow": _minimal_workflow_payload()},
            headers=headers,
        )
        self.assertEqual(save.status_code, 200, save.text)

        start = await self._client.post("/workflow/start", json={}, headers=headers)
        self.assertEqual(start.status_code, 200, start.text)
        execution_id = start.json()["execution_id"]
        self.assertTrue(execution_id)

        final_status = start.json()["status"]
        for _ in range(60):
            state = await self._client.post(f"/executions/{execution_id}", json={}, headers=headers)
            self.assertEqual(state.status_code, 200, state.text)
            final_status = state.json()["state"]["status"]
            if final_status in {"completed", "failed", "cancelled"}:
                break
            await asyncio.sleep(0.2)

        self.assertEqual(final_status, "completed")

        listing = await self._client.post("/admin/executions", json={}, headers=headers)
        self.assertEqual(listing.status_code, 200, listing.text)
        listing_data = listing.json()
        self.assertEqual(listing_data["source"], "platform")
        self.assertTrue(listing_data["executions"])
        first_execution = listing_data["executions"][0]
        self.assertEqual(first_execution["display_name"], "Surface Workflow")

        detail = await self._client.post(
            f"/admin/executions/{first_execution['execution_id']}",
            json={},
            headers=headers,
        )
        self.assertEqual(detail.status_code, 200, detail.text)
        detail_data = detail.json()["execution"]
        self.assertEqual(detail_data["source"], "platform")
        self.assertEqual(detail_data["display_name"], "Surface Workflow")
        self.assertEqual(detail_data["metadata"]["workflow_name"], "Surface Workflow")
        self.assertEqual(detail_data["asset_path"], "workflow.json")
        self.assertEqual(detail_data["status"], "completed")

    async def test_first_run_space_accepts_hello_starter_and_completes(self) -> None:
        register = await self._client.post(
            "/auth/register",
            json={"username": "starter", "email": "starter@local", "password": "pass1234"},
        )
        self.assertEqual(register.status_code, 200, register.text)
        payload = register.json()
        self.assertEqual(payload["user"]["role"], "admin")
        headers = self._auth_headers(payload["token"])

        current_space = await self._client.post("/spaces/current", json={}, headers=headers)
        self.assertEqual(current_space.status_code, 200, current_space.text)
        space = current_space.json()["space"]
        self.assertTrue(space["id"])

        initial_workflow = await self._client.post("/workflow/get", json={}, headers=headers)
        self.assertEqual(initial_workflow.status_code, 200, initial_workflow.text)
        self.assertIsNone(initial_workflow.json()["workflow"])

        save = await self._client.post(
            "/workflow/save",
            json={"workflow": _starter_hello_workflow_payload()},
            headers=headers,
        )
        self.assertEqual(save.status_code, 200, save.text)
        self.assertEqual(save.json()["status"], "saved")
        self.assertEqual(save.json()["name"], "Hello Workflow")

        reloaded = await self._client.post("/workflow/get", json={}, headers=headers)
        self.assertEqual(reloaded.status_code, 200, reloaded.text)
        workflow = reloaded.json()["workflow"]
        self.assertEqual(workflow["options"]["name"], "Hello Workflow")
        self.assertEqual([node["type"] for node in workflow["nodes"]], ["start_flow", "preview_flow", "end_flow"])

        start = await self._client.post("/workflow/start", json={}, headers=headers)
        self.assertEqual(start.status_code, 200, start.text)
        execution_id = start.json()["execution_id"]
        self.assertTrue(execution_id)

        final_status = start.json()["status"]
        for _ in range(60):
            state = await self._client.post(f"/executions/{execution_id}", json={}, headers=headers)
            self.assertEqual(state.status_code, 200, state.text)
            final_status = state.json()["state"]["status"]
            if final_status in {"completed", "failed", "cancelled"}:
                break
            await asyncio.sleep(0.2)

        self.assertEqual(final_status, "completed")





