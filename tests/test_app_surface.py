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
            "description": "A tiny first workflow that creates output and previews it.",
        },
        "nodes": [
            {
                "type": "start_flow",
                "extra": {"pos": [60, 180], "name": "Start"},
            },
            {
                "type": "transform_flow",
                "lang": "python",
                "script": "output = {'message': 'Hello from Numel!', 'next_step': 'Edit this transform or ask the assistant to expand it.'}",
                "extra": {"pos": [320, 180], "name": "Hello"},
            },
            {
                "type": "preview_flow",
                "extra": {"pos": [580, 180], "name": "Preview"},
            },
            {
                "type": "end_flow",
                "extra": {"pos": [840, 180], "name": "End"},
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
                "source_slot": "output",
                "target_slot": "flow_in",
            },
            {
                "source": 2,
                "target": 3,
                "source_slot": "flow_out",
                "target_slot": "flow_in",
            },
        ],
    }


def _toolkit_edge_workflow_payload(root: str) -> dict:
    return {
        "type": "workflow",
        "options": {
            "name": "Toolkit Edge Workflow",
            "description": "Uses toolkit_config wired into tool_flow via edges only.",
        },
        "nodes": [
            {
                "type": "start_flow",
                "extra": {"pos": [60, 180], "name": "Start"},
            },
            {
                "type": "toolkit_config",
                "args": {"root": root},
                "extra": {"pos": [60, 360], "name": "toolkits.file_toolkit"},
            },
            {
                "type": "tool_flow",
                "method": "list_directory",
                "args": {"path": "."},
                "extra": {"pos": [340, 180], "name": "List Directory"},
            },
            {
                "type": "end_flow",
                "extra": {"pos": [620, 180], "name": "End"},
            },
        ],
        "edges": [
            {
                "source": 0,
                "target": 2,
                "source_slot": "flow_out",
                "target_slot": "flow_in",
            },
            {
                "source": 1,
                "target": 2,
                "source_slot": "config",
                "target_slot": "config",
            },
            {
                "source": 2,
                "target": 3,
                "source_slot": "flow_out",
                "target_slot": "flow_in",
            },
        ],
    }


def _planner_slot_workflow_payload() -> dict:
    return {
        "type": "workflow",
        "options": {
            "name": "Planner Slot Workflow",
            "description": "Includes planner-style flow placeholders on a non-flow node.",
        },
        "nodes": [
            {
                "type": "start_flow",
                "extra": {"pos": [60, 180], "name": "Start"},
            },
            {
                "type": "native_string",
                "raw": "mesh.obj",
                "extra": {"pos": [60, 360], "name": "Mesh Path"},
            },
            {
                "type": "transform_flow",
                "script": "output = {'path': input}",
                "extra": {"pos": [340, 180], "name": "Wrap Path"},
            },
            {
                "type": "end_flow",
                "extra": {"pos": [620, 180], "name": "End"},
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
                "source": 0,
                "target": 2,
                "source_slot": "flow_out",
                "target_slot": "flow_in",
            },
            {
                "source": 1,
                "target": 2,
                "source_slot": "flow_out",
                "target_slot": "input",
            },
            {
                "source": 2,
                "target": 3,
                "source_slot": "output",
                "target_slot": "flow_in",
            },
        ],
    }


async def _fake_published_app_bundle(**kwargs) -> dict:
    app_name = kwargs.get("app_name", "Published App")
    return {
        "summary": "Generated app shell for the selected workflow.",
        "workflow_summary": {
            "name": app_name,
            "node_count": len((kwargs.get("workflow") or {}).get("nodes", [])),
            "edge_count": len((kwargs.get("workflow") or {}).get("edges", [])),
            "inputs": list(kwargs.get("inputs") or []),
        },
        "files": [
            {
                "path": "index.html",
                "content": f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{app_name}</title>
  <link rel="stylesheet" href="styles.css">
</head>
<body>
  <main class="generated-shell">
    <section class="hero">
      <h1>{app_name}</h1>
      <p class="lede">AI-generated published app shell.</p>
    </section>
    <!-- NUMEL_APP_RUNTIME -->
  </main>
  <script src="app.js"></script>
</body>
</html>""",
            },
            {
                "path": "styles.css",
                "content": ".generated-shell{padding:24px}.hero{margin-bottom:18px}",
            },
            {
                "path": "app.js",
                "content": "window.__publishedAppCustomLoaded = true;",
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
        self._app.state.published_app_page_generator = _fake_published_app_bundle
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

    async def test_admin_execution_list_can_filter_by_status_local(self) -> None:
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

        completed_items = []
        for _ in range(20):
            completed = await self._client.post(
                "/admin/executions",
                json={"status": "completed"},
                headers=headers,
            )
            self.assertEqual(completed.status_code, 200, completed.text)
            completed_items = completed.json()["executions"]
            if any(item["execution_id"] == execution_id for item in completed_items):
                break
            await asyncio.sleep(0.1)
        self.assertTrue(any(item["display_name"] == "Surface Workflow" for item in completed_items))
        self.assertTrue(all(item["status"] == "completed" for item in completed_items))

        running = await self._client.post(
            "/admin/executions",
            json={"status": "running"},
            headers=headers,
        )
        self.assertEqual(running.status_code, 200, running.text)
        running_items = running.json()["executions"]
        self.assertFalse(any(item["display_name"] == "Surface Workflow" for item in running_items))

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
        self.assertEqual(
            [node["type"] for node in workflow["nodes"]],
            ["start_flow", "transform_flow", "preview_flow", "end_flow"],
        )

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

    async def test_create_space_reuses_title_with_unique_slug(self) -> None:
        register = await self._client.post(
            "/auth/register",
            json={"username": "spaces", "email": "spaces@local", "password": "pass1234"},
        )
        self.assertEqual(register.status_code, 200, register.text)
        headers = self._auth_headers(register.json()["token"])

        first = await self._client.post(
            "/spaces/create",
            json={"title": "New Space"},
            headers=headers,
        )
        self.assertEqual(first.status_code, 200, first.text)

        second = await self._client.post(
            "/spaces/create",
            json={"title": "New Space"},
            headers=headers,
        )
        self.assertEqual(second.status_code, 200, second.text)

        first_space = first.json()["space"]
        second_space = second.json()["space"]
        self.assertNotEqual(first_space["id"], second_space["id"])
        self.assertEqual(first_space["slug"], "new-space")
        self.assertEqual(second_space["slug"], "new-space-2")

    async def test_toolkit_edge_config_workflow_saves_and_runs(self) -> None:
        register = await self._client.post(
            "/auth/register",
            json={"username": "toolkit", "email": "toolkit@local", "password": "pass1234"},
        )
        self.assertEqual(register.status_code, 200, register.text)
        headers = self._auth_headers(register.json()["token"])

        save = await self._client.post(
            "/workflow/save",
            json={"workflow": _toolkit_edge_workflow_payload(str(self._root))},
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

    async def test_workflow_validate_repairs_planner_style_toolkit_name(self) -> None:
        register = await self._client.post(
            "/auth/register",
            json={"username": "validator", "email": "validator@local", "password": "pass1234"},
        )
        self.assertEqual(register.status_code, 200, register.text)
        headers = self._auth_headers(register.json()["token"])

        payload = _toolkit_edge_workflow_payload(str(self._root))
        payload["nodes"][1].pop("name", None)

        response = await self._client.post(
            "/workflow/validate",
            json={"workflow": payload, "apply_repairs": True},
            headers=headers,
        )
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()
        self.assertTrue(data["valid"])
        self.assertTrue(data["repaired"])
        self.assertEqual(data["workflow"]["nodes"][1]["name"], "toolkits.file_toolkit")

    async def test_console_planner_apply_rejects_invalid_toolkit_method(self) -> None:
        register = await self._client.post(
            "/auth/register",
            json={"username": "planner", "email": "planner@local", "password": "pass1234"},
        )
        self.assertEqual(register.status_code, 200, register.text)
        headers = self._auth_headers(register.json()["token"])

        payload = _toolkit_edge_workflow_payload(str(self._root))
        payload["nodes"][1].pop("name", None)
        payload["nodes"][2]["method"] = "not_a_real_method"

        response = await self._client.post(
            "/console/planner/apply",
            json={"workflow": payload},
            headers=headers,
        )
        self.assertEqual(response.status_code, 400, response.text)
        self.assertIn("unknown toolkit method", response.text.lower())

    async def test_console_planner_apply_repairs_invalid_non_flow_edges(self) -> None:
        register = await self._client.post(
            "/auth/register",
            json={"username": "plannerfix", "email": "plannerfix@local", "password": "pass1234"},
        )
        self.assertEqual(register.status_code, 200, register.text)
        headers = self._auth_headers(register.json()["token"])

        response = await self._client.post(
            "/console/planner/apply",
            json={"workflow": _planner_slot_workflow_payload()},
            headers=headers,
        )
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()
        self.assertTrue(data["ok"])
        self.assertTrue(data["validation"]["repaired"])
        self.assertIn("workflow", data["result"])
        self.assertIsInstance(data["result"]["workflow"]["nodes"], list)
        self.assertTrue(
            any("removed invalid flow edge into non-flow node" in item for item in data["validation"]["repairs"])
        )

    async def test_generation_prompt_can_be_filtered_to_selected_toolkits(self) -> None:
        response = await self._client.post(
            "/generation-prompt",
            json={"toolkit_names": ["file_toolkit"]},
        )
        self.assertEqual(response.status_code, 200, response.text)
        prompt = response.json()["prompt"]
        self.assertIn("toolkits.file_toolkit", prompt)
        self.assertNotIn("toolkits.console_toolkit", prompt)
        self.assertIn("Only the following toolkits are enabled for this turn: file_toolkit.", prompt)

    async def test_generation_prompt_mesh_scope_excludes_unselected_toolkits(self) -> None:
        response = await self._client.post(
            "/generation-prompt",
            json={"toolkit_names": ["mesh_toolkit"]},
        )
        self.assertEqual(response.status_code, 200, response.text)
        prompt = response.json()["prompt"]
        self.assertIn("contrib.toolkits.mesh_toolkit", prompt)
        self.assertIn("Only the following toolkits are enabled for this turn: mesh_toolkit.", prompt)
        self.assertNotIn("toolkits.file_toolkit", prompt)
        self.assertNotIn("toolkits.workspace_toolkit", prompt)

    async def test_assistant_deployments_are_user_owned_and_bind_channels(self) -> None:
        register = await self._client.post(
            "/auth/register",
            json={"username": "deploy", "email": "deploy@local", "password": "pass1234"},
        )
        self.assertEqual(register.status_code, 200, register.text)
        headers = self._auth_headers(register.json()["token"])

        channel = await self._client.post(
            "/channels/add",
            json={"name": "Support Webhook", "channel_type": "webhook", "auto_start": False},
            headers=headers,
        )
        self.assertEqual(channel.status_code, 200, channel.text)
        channel_id = channel.json()["id"]

        created = await self._client.post(
            "/assistant-deployments/create",
            json={
                "name": "Support Assistant",
                "description": "Handles inbound support requests.",
                "instructions": "Be concise and helpful.",
                "model_source": "openai",
                "model_name": "gpt-4o-mini",
                "toolkit_names": ["file_toolkit", "channel_toolkit"],
                "skill_names": [],
                "channel_ids": [channel_id],
            },
            headers=headers,
        )
        self.assertEqual(created.status_code, 200, created.text)
        deployment = created.json()
        self.assertEqual(deployment["name"], "Support Assistant")
        self.assertEqual(deployment["created_by"], register.json()["user"]["id"])
        self.assertEqual(deployment["channel_ids"], [channel_id])
        self.assertEqual(deployment["toolkit_names"], ["file_toolkit", "channel_toolkit"])
        self.assertEqual(deployment["status"], "stopped")
        self.assertEqual(deployment["channels"][0]["id"], channel_id)

        listing = await self._client.post("/assistant-deployments/list", json={}, headers=headers)
        self.assertEqual(listing.status_code, 200, listing.text)
        self.assertEqual(len(listing.json()["deployments"]), 1)

        second = await self._client.post(
            "/auth/register",
            json={"username": "deploy2", "email": "deploy2@local", "password": "pass1234"},
        )
        self.assertEqual(second.status_code, 200, second.text)
        second_headers = self._auth_headers(second.json()["token"])
        second_listing = await self._client.post("/assistant-deployments/list", json={}, headers=second_headers)
        self.assertEqual(second_listing.status_code, 200, second_listing.text)
        self.assertEqual(second_listing.json()["deployments"], [])

    async def test_assistant_deployment_can_link_workbench_metadata(self) -> None:
        register = await self._client.post(
            "/auth/register",
            json={"username": "deployctx", "email": "deployctx@local", "password": "pass1234"},
        )
        self.assertEqual(register.status_code, 200, register.text)
        headers = self._auth_headers(register.json()["token"])

        current_space = await self._client.post("/spaces/current", json={}, headers=headers)
        self.assertEqual(current_space.status_code, 200, current_space.text)
        space = current_space.json()["space"]

        created = await self._client.post(
            "/assistant-deployments/create",
            json={
                "name": "Knowledge Assistant",
                "linked_space_id": space["id"],
                "linked_space_title": space["title"],
                "linked_workflow_name": "Ask Your Docs",
            },
            headers=headers,
        )
        self.assertEqual(created.status_code, 200, created.text)
        deployment = created.json()
        self.assertEqual(deployment["linked_space_id"], space["id"])
        self.assertEqual(deployment["linked_space_title"], space["title"])
        self.assertEqual(deployment["linked_workflow_name"], "Ask Your Docs")

    async def test_assistant_deployment_start_stop_controls_bound_channels(self) -> None:
        register = await self._client.post(
            "/auth/register",
            json={"username": "deployrun", "email": "deployrun@local", "password": "pass1234"},
        )
        self.assertEqual(register.status_code, 200, register.text)
        headers = self._auth_headers(register.json()["token"])

        channel = await self._client.post(
            "/channels/add",
            json={"name": "Ops Webhook", "channel_type": "webhook", "auto_start": False},
            headers=headers,
        )
        self.assertEqual(channel.status_code, 200, channel.text)
        channel_id = channel.json()["id"]

        created = await self._client.post(
            "/assistant-deployments/create",
            json={"name": "Ops Assistant", "channel_ids": [channel_id]},
            headers=headers,
        )
        self.assertEqual(created.status_code, 200, created.text)
        deployment_id = created.json()["id"]

        started = await self._client.post(
            "/assistant-deployments/start",
            json={"id": deployment_id},
            headers=headers,
        )
        self.assertEqual(started.status_code, 200, started.text)
        self.assertEqual(started.json()["status"], "running")

        channel_status = await self._client.post("/channels/status", json={"channel_id": channel_id}, headers=headers)
        self.assertEqual(channel_status.status_code, 200, channel_status.text)
        self.assertEqual(channel_status.json()["status"], "running")

        stopped = await self._client.post(
            "/assistant-deployments/stop",
            json={"id": deployment_id},
            headers=headers,
        )
        self.assertEqual(stopped.status_code, 200, stopped.text)
        self.assertEqual(stopped.json()["status"], "disabled")

        channel_status = await self._client.post("/channels/status", json={"channel_id": channel_id}, headers=headers)
        self.assertEqual(channel_status.status_code, 200, channel_status.text)
        self.assertEqual(channel_status.json()["status"], "stopped")

    async def test_assistant_deployment_proactive_tasks_start_and_stop_with_deployment(self) -> None:
        register = await self._client.post(
            "/auth/register",
            json={"username": "deployjobs", "email": "deployjobs@local", "password": "pass1234"},
        )
        self.assertEqual(register.status_code, 200, register.text)
        headers = self._auth_headers(register.json()["token"])

        channel = await self._client.post(
            "/channels/add",
            json={"name": "Jobs Webhook", "channel_type": "webhook", "auto_start": False},
            headers=headers,
        )
        self.assertEqual(channel.status_code, 200, channel.text)
        channel_id = channel.json()["id"]

        created = await self._client.post(
            "/assistant-deployments/create",
            json={
                "name": "Operations Assistant",
                "channel_ids": [channel_id],
                "proactive_tasks": [
                    {
                        "name": "Morning Summary",
                        "prompt": "Summarize the important overnight items.",
                        "interval_sec": 300,
                        "channel_id": channel_id,
                        "enabled": True,
                        "send_response": False,
                    }
                ],
            },
            headers=headers,
        )
        self.assertEqual(created.status_code, 200, created.text)
        deployment_id = created.json()["id"]

        started = await self._client.post(
            "/assistant-deployments/start",
            json={"id": deployment_id},
            headers=headers,
        )
        self.assertEqual(started.status_code, 200, started.text)
        started_task = started.json()["proactive_tasks"][0]
        self.assertEqual(started_task["runtime"]["status"], "scheduled")
        self.assertTrue(started_task["runtime"]["next_run_at"])

        stopped = await self._client.post(
            "/assistant-deployments/stop",
            json={"id": deployment_id},
            headers=headers,
        )
        self.assertEqual(stopped.status_code, 200, stopped.text)
        stopped_task = stopped.json()["proactive_tasks"][0]
        self.assertEqual(stopped_task["runtime"]["status"], "stopped")
        self.assertIsNone(stopped_task["runtime"]["next_run_at"])

    async def test_assistant_deployment_run_proactive_tasks_records_runtime_and_delivery(self) -> None:
        register = await self._client.post(
            "/auth/register",
            json={"username": "deploypulse", "email": "deploypulse@local", "password": "pass1234"},
        )
        self.assertEqual(register.status_code, 200, register.text)
        headers = self._auth_headers(register.json()["token"])

        channel = await self._client.post(
            "/channels/add",
            json={"name": "Pulse Webhook", "channel_type": "webhook", "auto_start": False},
            headers=headers,
        )
        self.assertEqual(channel.status_code, 200, channel.text)
        channel_id = channel.json()["id"]

        created = await self._client.post(
            "/assistant-deployments/create",
            json={
                "name": "Pulse Assistant",
                "profile": "ops",
                "description": "Sends a concise operational pulse.",
                "instructions": "Keep updates short and concrete.",
                "model_source": "openai",
                "model_name": "gpt-4o-mini",
                "toolkit_names": ["file_toolkit"],
                "channel_ids": [channel_id],
                "proactive_tasks": [
                    {
                        "name": "Pulse",
                        "prompt": "Summarize the current state in one short message.",
                        "interval_sec": 300,
                        "channel_id": channel_id,
                        "recipient_id": "ops_room",
                        "enabled": True,
                        "send_response": True,
                    }
                ],
            },
            headers=headers,
        )
        self.assertEqual(created.status_code, 200, created.text)
        deployment_id = created.json()["id"]
        task_id = created.json()["proactive_tasks"][0]["id"]

        start = await self._client.post(
            "/assistant-deployments/start",
            json={"id": deployment_id},
            headers=headers,
        )
        self.assertEqual(start.status_code, 200, start.text)

        captured: dict[str, object] = {}
        deliveries: list[tuple[str, str]] = []

        async def _fake_chat(message, session_id, **kwargs):
            captured["message"] = message
            captured["session_id"] = session_id
            captured.update(kwargs)
            return {"response": "Pulse: all quiet", "tool_calls": []}

        async def _fake_send(recipient_id, text, **kwargs):
            deliveries.append((recipient_id, text))
            return True

        channel_pool = self._app.state.console_mgr._channel_pool
        adapter = self._app.state.channel_registry.get(channel_id)
        original_chat = channel_pool.chat
        original_send = adapter.send
        channel_pool.chat = _fake_chat
        adapter.send = _fake_send
        try:
            run_now = await self._client.post(
                "/assistant-deployments/run-proactive",
                json={"id": deployment_id, "task_id": task_id},
                headers=headers,
            )
        finally:
            channel_pool.chat = original_chat
            adapter.send = original_send
            await self._client.post(
                "/assistant-deployments/stop",
                json={"id": deployment_id},
                headers=headers,
            )

        self.assertEqual(run_now.status_code, 200, run_now.text)
        payload = run_now.json()
        self.assertEqual(len(payload["results"]), 1)
        self.assertEqual(payload["results"][0]["status"], "ok")
        self.assertTrue(payload["results"][0]["delivered"])
        self.assertEqual(captured["assistant_name"], "Pulse Assistant")
        self.assertEqual(captured["model_source"], "openai")
        self.assertEqual(captured["model_name"], "gpt-4o-mini")
        self.assertEqual(captured["toolkits"], ["file_toolkit"])
        self.assertTrue(str(captured["session_id"]).startswith(f"deploytask_{deployment_id}_{task_id}"))
        extra_instructions = captured.get("extra_instructions") or []
        self.assertTrue(any("[Proactive Task]" in str(item) for item in extra_instructions))
        self.assertEqual(deliveries, [("ops_room", "Pulse: all quiet")])

        fetched = await self._client.post(
            "/assistant-deployments/get",
            json={"id": deployment_id},
            headers=headers,
        )
        self.assertEqual(fetched.status_code, 200, fetched.text)
        deployment = fetched.json()
        self.assertEqual(deployment["runtime"]["proactive_run_count"], 1)
        self.assertEqual(deployment["runtime"]["last_proactive_task_name"], "Pulse")
        self.assertEqual(len(deployment["recent_proactive_runs"]), 1)
        self.assertTrue(any(row["kind"] == "proactive_run" for row in deployment["recent_activity"]))
        task_runtime = deployment["proactive_tasks"][0]["runtime"]
        self.assertEqual(task_runtime["run_count"], 1)
        self.assertEqual(task_runtime["last_status"], "ok")
        self.assertEqual(task_runtime["last_delivery_recipient_id"], "ops_room")

    async def test_assistant_deployment_proactive_approval_queue_and_approve(self) -> None:
        register = await self._client.post(
            "/auth/register",
            json={"username": "deployapprove", "email": "deployapprove@local", "password": "pass1234"},
        )
        self.assertEqual(register.status_code, 200, register.text)
        headers = self._auth_headers(register.json()["token"])

        channel = await self._client.post(
            "/channels/add",
            json={"name": "Approval Webhook", "channel_type": "webhook", "auto_start": False},
            headers=headers,
        )
        self.assertEqual(channel.status_code, 200, channel.text)
        channel_id = channel.json()["id"]

        created = await self._client.post(
            "/assistant-deployments/create",
            json={
                "name": "Approval Assistant",
                "channel_ids": [channel_id],
                "safety": {"proactive_delivery_mode": "approval"},
                "proactive_tasks": [
                    {
                        "name": "Approval Pulse",
                        "prompt": "Draft the pulse update.",
                        "interval_sec": 300,
                        "channel_id": channel_id,
                        "recipient_id": "ops_room",
                        "enabled": True,
                        "send_response": True,
                    }
                ],
            },
            headers=headers,
        )
        self.assertEqual(created.status_code, 200, created.text)
        deployment_id = created.json()["id"]
        task_id = created.json()["proactive_tasks"][0]["id"]

        started = await self._client.post(
            "/assistant-deployments/start",
            json={"id": deployment_id},
            headers=headers,
        )
        self.assertEqual(started.status_code, 200, started.text)

        captured: dict[str, object] = {}
        deliveries: list[tuple[str, str]] = []

        async def _fake_chat(message, session_id, **kwargs):
            captured["message"] = message
            captured["session_id"] = session_id
            captured.update(kwargs)
            return {"response": "Approval pulse ready", "tool_calls": []}

        async def _fake_send(recipient_id, text, **kwargs):
            deliveries.append((recipient_id, text))
            return True

        channel_pool = self._app.state.console_mgr._channel_pool
        adapter = self._app.state.channel_registry.get(channel_id)
        original_chat = channel_pool.chat
        original_send = adapter.send
        channel_pool.chat = _fake_chat
        adapter.send = _fake_send
        try:
            run_now = await self._client.post(
                "/assistant-deployments/run-proactive",
                json={"id": deployment_id, "task_id": task_id},
                headers=headers,
            )
            self.assertEqual(run_now.status_code, 200, run_now.text)
            payload = run_now.json()
            self.assertEqual(payload["results"][0]["status"], "pending_approval")
            self.assertFalse(payload["results"][0]["delivered"])
            approval_id = payload["results"][0]["approval_id"]
            self.assertTrue(approval_id)
            self.assertEqual(deliveries, [])

            fetched = await self._client.post(
                "/assistant-deployments/get",
                json={"id": deployment_id},
                headers=headers,
            )
            self.assertEqual(fetched.status_code, 200, fetched.text)
            deployment = fetched.json()
            self.assertEqual(deployment["runtime"]["pending_approval_count"], 1)
            self.assertEqual(len(deployment["pending_proactive_approvals"]), 1)
            self.assertEqual(deployment["proactive_tasks"][0]["runtime"]["last_status"], "pending_approval")

            approved = await self._client.post(
                "/assistant-deployments/approve-proactive",
                json={"id": approval_id},
                headers=headers,
            )
            self.assertEqual(approved.status_code, 200, approved.text)
            self.assertEqual(approved.json()["status"], "approved")
            self.assertEqual(deliveries, [("ops_room", "Approval pulse ready")])
        finally:
            channel_pool.chat = original_chat
            adapter.send = original_send
            await self._client.post(
                "/assistant-deployments/stop",
                json={"id": deployment_id},
                headers=headers,
            )

        fetched_after = await self._client.post(
            "/assistant-deployments/get",
            json={"id": deployment_id},
            headers=headers,
        )
        self.assertEqual(fetched_after.status_code, 200, fetched_after.text)
        deployment_after = fetched_after.json()
        self.assertEqual(deployment_after["runtime"]["pending_approval_count"], 0)
        self.assertEqual(deployment_after["runtime"]["last_approval_status"], "approved")
        self.assertEqual(len(deployment_after["pending_proactive_approvals"]), 0)
        self.assertTrue(any(row["status"] == "approved" for row in deployment_after["recent_approvals"]))
        self.assertTrue(any(row["kind"] == "approval" for row in deployment_after["recent_activity"]))

    async def test_assistant_deployment_tool_approval_queue_and_approve(self) -> None:
        from agno.models.response import ToolExecution
        from agno.run.requirement import RunRequirement

        register = await self._client.post(
            "/auth/register",
            json={"username": "deploytoolapprove", "email": "deploytoolapprove@local", "password": "pass1234"},
        )
        self.assertEqual(register.status_code, 200, register.text)
        headers = self._auth_headers(register.json()["token"])

        channel = await self._client.post(
            "/channels/add",
            json={"name": "Tool Approval Webhook", "channel_type": "webhook", "auto_start": False},
            headers=headers,
        )
        self.assertEqual(channel.status_code, 200, channel.text)
        channel_id = channel.json()["id"]

        created = await self._client.post(
            "/assistant-deployments/create",
            json={
                "name": "Tool Approval Assistant",
                "channel_ids": [channel_id],
                "safety": {"tool_execution_mode": "approval"},
            },
            headers=headers,
        )
        self.assertEqual(created.status_code, 200, created.text)
        deployment_id = created.json()["id"]
        self.assertEqual(created.json()["safety"]["tool_execution_mode"], "approval")

        started = await self._client.post(
            "/assistant-deployments/start",
            json={"id": deployment_id},
            headers=headers,
        )
        self.assertEqual(started.status_code, 200, started.text)

        class _FakeRunResponse:
            def __init__(self, *, content: str = "", requirements=None):
                self.content = content
                self.messages = []
                self.requirements = list(requirements or [])

            @property
            def active_requirements(self):
                return [requirement for requirement in self.requirements if not requirement.is_resolved()]

            @property
            def is_paused(self):
                return bool(self.active_requirements)

        class _FakeAgent:
            async def arun(self, message, **kwargs):
                tool_execution = ToolExecution(
                    tool_name="delete_file",
                    tool_args={"path": "secret.txt"},
                    requires_confirmation=True,
                    approval_type="required",
                )
                requirement = RunRequirement(tool_execution)
                return _FakeRunResponse(requirements=[requirement])

            async def acontinue_run(self, *, requirements=None, **kwargs):
                requirement = list(requirements or [])[0]
                if requirement.confirmation is True:
                    return _FakeRunResponse(content="Tool approved and completed.")
                return _FakeRunResponse(content="Tool request was rejected.")

        captured: dict[str, object] = {}
        deliveries: list[tuple[str, str]] = []

        async def _fake_get_or_create(session_id, **kwargs):
            captured["session_id"] = session_id
            captured.update(kwargs)
            agent = _FakeAgent()
            channel_pool._agents[session_id] = agent
            return agent

        async def _fake_send(recipient_id, text, **kwargs):
            deliveries.append((recipient_id, text))
            return True

        channel_pool = self._app.state.console_mgr._channel_pool
        adapter = self._app.state.channel_registry.get(channel_id)
        original_get_or_create = channel_pool._get_or_create
        original_send = adapter.send
        channel_pool._get_or_create = _fake_get_or_create
        adapter.send = _fake_send
        try:
            response = await self._client.post(
                f"/channels/webhook/{channel_id}",
                json={"text": "please clean up the uploaded file", "sender_id": "external_user", "sender_name": "External User"},
            )
            self.assertEqual(response.status_code, 200, response.text)
            self.assertIn("Approval requested before running tool", response.text)

            fetched = await self._client.post(
                "/assistant-deployments/get",
                json={"id": deployment_id},
                headers=headers,
            )
            self.assertEqual(fetched.status_code, 200, fetched.text)
            deployment = fetched.json()
            self.assertEqual(deployment["runtime"]["pending_tool_approval_count"], 1)
            self.assertEqual(deployment["runtime"]["pending_approval_count"], 1)
            self.assertEqual(len(deployment["pending_tool_approvals"]), 1)
            self.assertTrue(any(row["kind"] == "tool_approval_pending" for row in deployment["recent_activity"]))
            approval_id = deployment["pending_tool_approvals"][0]["id"]

            approved = await self._client.post(
                "/assistant-deployments/approve-tool-call",
                json={"id": approval_id},
                headers=headers,
            )
            self.assertEqual(approved.status_code, 200, approved.text)
            self.assertEqual(approved.json()["status"], "approved")
            self.assertEqual(approved.json()["response_text"], "Tool approved and completed.")
            self.assertEqual(deliveries, [("external_user", "Tool approved and completed.")])
        finally:
            channel_pool._get_or_create = original_get_or_create
            adapter.send = original_send
            await self._client.post(
                "/assistant-deployments/stop",
                json={"id": deployment_id},
                headers=headers,
            )

        self.assertEqual(captured["tool_confirmation_mode"], "approval")
        fetched_after = await self._client.post(
            "/assistant-deployments/get",
            json={"id": deployment_id},
            headers=headers,
        )
        self.assertEqual(fetched_after.status_code, 200, fetched_after.text)
        deployment_after = fetched_after.json()
        self.assertEqual(deployment_after["runtime"]["pending_tool_approval_count"], 0)
        self.assertEqual(deployment_after["runtime"]["pending_approval_count"], 0)
        self.assertEqual(deployment_after["runtime"]["last_approval_kind"], "tool")
        self.assertEqual(len(deployment_after["pending_tool_approvals"]), 0)
        self.assertTrue(any(row["status"] == "approved" for row in deployment_after["recent_tool_approvals"]))
        self.assertTrue(any(row["kind"] == "tool_approval" for row in deployment_after["recent_activity"]))

    async def test_channel_messages_use_assistant_deployment_overrides(self) -> None:
        register = await self._client.post(
            "/auth/register",
            json={"username": "deploymsg", "email": "deploymsg@local", "password": "pass1234"},
        )
        self.assertEqual(register.status_code, 200, register.text)
        headers = self._auth_headers(register.json()["token"])

        channel = await self._client.post(
            "/channels/add",
            json={"name": "Inbound Webhook", "channel_type": "webhook", "auto_start": False},
            headers=headers,
        )
        self.assertEqual(channel.status_code, 200, channel.text)
        channel_id = channel.json()["id"]

        created = await self._client.post(
            "/assistant-deployments/create",
            json={
                "name": "Finance Assistant",
                "description": "Keeps answers tied to the finance deployment.",
                "instructions": "Stay focused on finance operations.",
                "model_source": "anthropic",
                "model_name": "claude-sonnet-4-20250514",
                "toolkit_names": ["file_toolkit"],
                "skill_names": ["finance_review"],
                "channel_ids": [channel_id],
            },
            headers=headers,
        )
        self.assertEqual(created.status_code, 200, created.text)

        captured: dict[str, object] = {}

        async def _fake_chat(message, session_id, **kwargs):
            captured["message"] = message
            captured["session_id"] = session_id
            captured.update(kwargs)
            return {"response": "ok", "tool_calls": []}

        channel_pool = self._app.state.console_mgr._channel_pool
        original_chat = channel_pool.chat
        channel_pool.chat = _fake_chat
        try:
            response = await self._client.post(
                f"/channels/webhook/{channel_id}",
                json={"text": "hello", "sender_id": "external_user", "sender_name": "External User"},
            )
        finally:
            channel_pool.chat = original_chat

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(captured["toolkits"], ["file_toolkit"])
        self.assertEqual(captured["model_source"], "anthropic")
        self.assertEqual(captured["model_name"], "claude-sonnet-4-20250514")
        self.assertEqual(captured["skill_names"], ["finance_review"])
        self.assertEqual(captured["assistant_name"], "Finance Assistant")
        self.assertTrue(str(captured["session_id"]).startswith("deploy_"))
        extra_instructions = captured.get("extra_instructions") or []
        self.assertTrue(any("Stay focused on finance operations." in str(item) for item in extra_instructions))

    async def test_assistant_deployment_routes_messages_to_specialist(self) -> None:
        register = await self._client.post(
            "/auth/register",
            json={"username": "routeuser", "email": "routeuser@local", "password": "pass1234"},
        )
        self.assertEqual(register.status_code, 200, register.text)
        headers = self._auth_headers(register.json()["token"])

        channel = await self._client.post(
            "/channels/add",
            json={"name": "Routing Webhook", "channel_type": "webhook", "auto_start": False},
            headers=headers,
        )
        self.assertEqual(channel.status_code, 200, channel.text)
        channel_id = channel.json()["id"]

        specialist = await self._client.post(
            "/assistant-deployments/create",
            json={
                "name": "Billing Specialist",
                "profile": "billing",
                "description": "Handles invoices and billing issues.",
                "model_source": "openai",
                "model_name": "gpt-4o-mini",
                "toolkit_names": ["file_toolkit"],
            },
            headers=headers,
        )
        self.assertEqual(specialist.status_code, 200, specialist.text)
        specialist_id = specialist.json()["id"]

        front_door = await self._client.post(
            "/assistant-deployments/create",
            json={
                "name": "Support Front Door",
                "profile": "triage",
                "description": "Routes support traffic to specialists.",
                "instructions": "Route to specialists when needed.",
                "channel_ids": [channel_id],
                "routing_rules": [
                    {
                        "name": "billing",
                        "target_deployment_id": specialist_id,
                        "keywords": ["invoice", "billing"],
                    }
                ],
            },
            headers=headers,
        )
        self.assertEqual(front_door.status_code, 200, front_door.text)
        front_door_id = front_door.json()["id"]

        captured: dict[str, object] = {}

        async def _fake_chat(message, session_id, **kwargs):
            captured["message"] = message
            captured["session_id"] = session_id
            captured.update(kwargs)
            return {"response": "handled by specialist", "tool_calls": []}

        channel_pool = self._app.state.console_mgr._channel_pool
        original_chat = channel_pool.chat
        channel_pool.chat = _fake_chat
        try:
            response = await self._client.post(
                f"/channels/webhook/{channel_id}",
                json={"text": "Can you help with an invoice discrepancy?", "sender_id": "customer_1", "sender_name": "Customer"},
            )
        finally:
            channel_pool.chat = original_chat

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(captured["assistant_name"], "Billing Specialist")
        self.assertEqual(captured["model_source"], "openai")
        self.assertEqual(captured["model_name"], "gpt-4o-mini")
        self.assertEqual(captured["toolkits"], ["file_toolkit"])
        self.assertTrue(str(captured["session_id"]).startswith(f"deploy_{specialist_id}"))
        extra_instructions = captured.get("extra_instructions") or []
        self.assertTrue(any("[Assistant Handoff]" in str(item) for item in extra_instructions))
        self.assertTrue(any("invoice" in str(item).lower() for item in extra_instructions))

        front_door_get = await self._client.post(
            "/assistant-deployments/get",
            json={"id": front_door_id},
            headers=headers,
        )
        self.assertEqual(front_door_get.status_code, 200, front_door_get.text)
        front_data = front_door_get.json()
        self.assertEqual(front_data["runtime"]["message_count"], 1)
        self.assertEqual(front_data["runtime"]["last_handoff_target"], specialist_id)
        self.assertEqual(len(front_data["recent_handoffs"]), 1)
        self.assertTrue(any(row["kind"] == "handoff" for row in front_data["recent_activity"]))

        specialist_get = await self._client.post(
            "/assistant-deployments/get",
            json={"id": specialist_id},
            headers=headers,
        )
        self.assertEqual(specialist_get.status_code, 200, specialist_get.text)
        specialist_data = specialist_get.json()
        self.assertEqual(specialist_data["runtime"]["message_count"], 1)
        self.assertEqual(specialist_data["runtime"]["last_handoff_from"], front_door_id)
        self.assertEqual(len(specialist_data["recent_handoffs"]), 1)
        self.assertTrue(any(row["kind"] == "routed_message" for row in specialist_data["recent_activity"]))

    async def test_published_app_model_options_are_available(self) -> None:
        source_response = await self._client.post("/options/published_app_model_sources", json={})
        self.assertEqual(source_response.status_code, 200, source_response.text)
        source_options = source_response.json()["options"]
        self.assertTrue(source_options)
        self.assertIn("ollama", source_options)

        name_response = await self._client.post("/options/published_app_model_names", json={"source": "ollama"})
        self.assertEqual(name_response.status_code, 200, name_response.text)
        name_options = name_response.json()["options"]
        self.assertTrue(name_options)
        self.assertIn("qwen3.5:cloud", name_options)

        openai_names = await self._client.post("/options/published_app_model_names", json={"source": "openai"})
        self.assertEqual(openai_names.status_code, 200, openai_names.text)
        self.assertIn("gpt-4o", openai_names.json()["options"])

    async def test_published_apps_are_user_owned_and_store_generated_assets(self) -> None:
        register = await self._client.post(
            "/auth/register",
            json={"username": "alice", "email": "alice@local", "password": "pass1234"},
        )
        self.assertEqual(register.status_code, 200, register.text)
        payload = register.json()
        headers = self._auth_headers(payload["token"])

        publish = await self._client.post(
            "/apps/publish",
            json={
                "title": "Alice Demo App",
                "slug": "alice-demo-app",
                "description": "Published from a workflow",
                "workflow": _minimal_workflow_payload(),
                "page_generation": {
                    "model_source": "ollama",
                    "model_name": "qwen3.5:cloud",
                    "temperature": 0.3,
                    "max_tokens": 2048,
                    "page_prompt": "Make it clean and focused.",
                },
            },
            headers=headers,
        )
        self.assertEqual(publish.status_code, 200, publish.text)
        self.assertEqual(publish.json()["url"], "/apps/alice/alice-demo-app")

        listing = await self._client.post("/apps/list", json={}, headers=headers)
        self.assertEqual(listing.status_code, 200, listing.text)
        apps = listing.json()
        self.assertEqual(len(apps), 1)
        self.assertEqual(apps[0]["owner_username"], "alice")
        self.assertEqual(apps[0]["url"], "/apps/alice/alice-demo-app")
        self.assertEqual(apps[0]["generation"]["model_name"], "qwen3.5:cloud")

        public_page = await self._client.get("/apps/alice/alice-demo-app")
        self.assertEqual(public_page.status_code, 200, public_page.text)
        self.assertIn("numel-runtime-root", public_page.text)
        self.assertIn('/apps/alice/alice-demo-app/assets/runtime.js', public_page.text)
        self.assertIn('/apps/alice/alice-demo-app/assets/runtime.css', public_page.text)
        self.assertIn('/apps/alice/alice-demo-app/assets/styles.css', public_page.text)
        self.assertIn('/apps/alice/alice-demo-app/assets/app.js', public_page.text)
        self.assertNotIn("./assets/runtime.js", public_page.text)

        css_asset = await self._client.get("/apps/alice/alice-demo-app/assets/styles.css")
        self.assertEqual(css_asset.status_code, 200, css_asset.text)
        self.assertIn("generated-shell", css_asset.text)

        asset_dir = self._runtime_root / "published_apps" / payload["user"]["id"] / "alice-demo-app"
        self.assertTrue((asset_dir / "index.html").exists())
        self.assertTrue((asset_dir / "workflow.json").exists())

        second_user = await self._client.post(
            "/auth/register",
            json={"username": "bob", "email": "bob@local", "password": "pass1234"},
        )
        self.assertEqual(second_user.status_code, 200, second_user.text)
        second_headers = self._auth_headers(second_user.json()["token"])
        second_listing = await self._client.post("/apps/list", json={}, headers=second_headers)
        self.assertEqual(second_listing.status_code, 200, second_listing.text)
        self.assertEqual(second_listing.json(), [])

    async def test_public_published_app_can_run_saved_workflow_snapshot(self) -> None:
        register = await self._client.post(
            "/auth/register",
            json={"username": "alice", "email": "alice@local", "password": "pass1234"},
        )
        self.assertEqual(register.status_code, 200, register.text)
        headers = self._auth_headers(register.json()["token"])

        publish = await self._client.post(
            "/apps/publish",
            json={
                "title": "Public Runner",
                "slug": "public-runner",
                "workflow": _minimal_workflow_payload(),
            },
            headers=headers,
        )
        self.assertEqual(publish.status_code, 200, publish.text)

        start = await self._client.post("/apps/alice/public-runner/start", json={})
        self.assertEqual(start.status_code, 200, start.text)
        execution_id = start.json()["execution_id"]
        self.assertTrue(execution_id)

        final_status = None
        for _ in range(60):
            state = await self._client.post(f"/apps/alice/public-runner/executions/{execution_id}", json={})
            self.assertEqual(state.status_code, 200, state.text)
            final_status = state.json()["state"]["status"]
            if final_status in {"completed", "failed"}:
                break
            await asyncio.sleep(0.1)

        self.assertEqual(final_status, "completed")





