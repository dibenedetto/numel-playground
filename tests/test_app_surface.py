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
</head>
<body>
  <main class="generated-shell">
    <section class="hero">
      <h1>{app_name}</h1>
      <p class="lede">AI-generated published app shell.</p>
    </section>
    <!-- NUMEL_APP_RUNTIME -->
  </main>
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
        self.assertIn("./assets/runtime.js", public_page.text)

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





