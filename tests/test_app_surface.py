from __future__ import annotations

import asyncio
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
from unittest.mock import patch

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


def _n8n_set_workflow_payload() -> dict:
    return {
        "name": "n8n Surface Import",
        "nodes": [
            {
                "id": "1",
                "name": "Manual Trigger",
                "type": "n8n-nodes-base.manualTrigger",
                "position": [80, 180],
                "parameters": {},
            },
            {
                "id": "2",
                "name": "Set Fields",
                "type": "n8n-nodes-base.set",
                "position": [360, 180],
                "parameters": {
                    "keepOnlySet": True,
                    "values": {
                        "string": [{"name": "message", "value": "Hello from imported n8n"}],
                        "number": [{"name": "count", "value": 2}],
                    },
                },
            },
        ],
        "connections": {
            "Manual Trigger": {
                "main": [[{"node": "Set Fields", "type": "main", "index": 0}]],
            },
        },
    }


def _n8n_if_workflow_payload() -> dict:
    return {
        "name": "n8n Branch Import",
        "nodes": [
            {
                "id": "1",
                "name": "Manual Trigger",
                "type": "n8n-nodes-base.manualTrigger",
                "position": [80, 200],
                "parameters": {},
            },
            {
                "id": "2",
                "name": "Set Status",
                "type": "n8n-nodes-base.set",
                "position": [320, 200],
                "parameters": {
                    "keepOnlySet": True,
                    "values": {
                        "string": [{"name": "status", "value": "ok"}],
                    },
                },
            },
            {
                "id": "3",
                "name": "Status Check",
                "type": "n8n-nodes-base.if",
                "position": [600, 200],
                "parameters": {
                    "conditions": {
                        "conditions": [
                            {
                                "leftValue": "={{$json.status}}",
                                "rightValue": "ok",
                                "operator": {"operation": "equal"},
                            },
                        ],
                        "combinator": "and",
                    },
                },
            },
            {
                "id": "4",
                "name": "True Branch",
                "type": "n8n-nodes-base.set",
                "position": [900, 100],
                "parameters": {
                    "keepOnlySet": False,
                    "values": {
                        "string": [{"name": "decision", "value": "approved"}],
                    },
                },
            },
            {
                "id": "5",
                "name": "False Branch",
                "type": "n8n-nodes-base.set",
                "position": [900, 300],
                "parameters": {
                    "keepOnlySet": False,
                    "values": {
                        "string": [{"name": "decision", "value": "rejected"}],
                    },
                },
            },
        ],
        "connections": {
            "Manual Trigger": {
                "main": [[{"node": "Set Status", "type": "main", "index": 0}]],
            },
            "Set Status": {
                "main": [[{"node": "Status Check", "type": "main", "index": 0}]],
            },
            "Status Check": {
                "main": [
                    [{"node": "True Branch", "type": "main", "index": 0}],
                    [{"node": "False Branch", "type": "main", "index": 0}],
                ],
            },
        },
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


def _agent_edge_workflow_payload() -> dict:
    return {
        "type": "workflow",
        "options": {
            "name": "Agent Edge Workflow",
            "description": "Uses the implicit default backend plus model_config wired into agent_config.",
        },
        "nodes": [
            {
                "type": "model_config",
                "source": "ollama",
                "name": "mistral:latest",
                "extra": {"pos": [40, 100], "name": "Model"},
            },
            {
                "type": "agent_config",
                "extra": {"pos": [340, 100], "name": "Agent"},
            },
            {
                "type": "start_flow",
                "extra": {"pos": [40, 340], "name": "Start"},
            },
            {
                "type": "agent_flow",
                "request": "Say hello in one short sentence.",
                "extra": {"pos": [640, 340], "name": "Ask Agent"},
            },
            {
                "type": "end_flow",
                "extra": {"pos": [940, 340], "name": "End"},
            },
        ],
        "edges": [
            {
                "source": 0,
                "target": 1,
                "source_slot": "config",
                "target_slot": "model",
            },
            {
                "source": 1,
                "target": 3,
                "source_slot": "config",
                "target_slot": "config",
            },
            {
                "source": 2,
                "target": 3,
                "source_slot": "flow_out",
                "target_slot": "flow_in",
            },
            {
                "source": 3,
                "target": 4,
                "source_slot": "flow_out",
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

        pref_update = await self._client.post(
            "/auth/preferences/update",
            json={"ui_preferences": {"show_starter_on_login": False}},
            headers=self._auth_headers(payload["token"]),
        )
        self.assertEqual(pref_update.status_code, 200, pref_update.text)
        self.assertFalse(pref_update.json()["ui_preferences"]["show_starter_on_login"])

        me_after = await self._client.post("/auth/me", json={}, headers=self._auth_headers(payload["token"]))
        self.assertEqual(me_after.status_code, 200, me_after.text)
        self.assertFalse(
            me_after.json()["profile"]["metadata"]["ui_preferences"]["show_starter_on_login"]
        )

    async def test_ping_with_session_header_returns_promptly(self) -> None:
        response = await asyncio.wait_for(
            self._client.post("/ping", json={}, headers={"X-Session-Id": "sess_smoke"}),
            timeout=2.0,
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["message"], "pong")

    async def test_workflow_save_emits_workspace_changed_with_source_session_id(self) -> None:
        register = await self._client.post(
            "/auth/register",
            json={"username": "eventuser", "email": "eventuser@local", "password": "pass1234"},
        )
        self.assertEqual(register.status_code, 200, register.text)
        headers = self._auth_headers(register.json()["token"])
        headers["X-Session-Id"] = "sess_surface_ui"

        save = await self._client.post(
            "/workflow/save",
            json={"workflow": _minimal_workflow_payload()},
            headers=headers,
        )
        self.assertEqual(save.status_code, 200, save.text)

        history = self._app.state.event_bus.get_event_history(limit=50)
        event = next(
            (item for item in reversed(history) if item.event_type.value == "workspace.changed"),
            None,
        )
        self.assertIsNotNone(event)
        self.assertEqual(event.data.get("name"), "Surface Workflow")
        self.assertEqual(event.data.get("source_session_id"), "sess_surface_ui")

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

    async def test_spaces_surface_groups_mine_and_public_spaces(self) -> None:
        alice = await self._client.post(
            "/auth/register",
            json={"username": "alice", "email": "alice@local", "password": "pass1234"},
        )
        self.assertEqual(alice.status_code, 200, alice.text)
        alice_headers = self._auth_headers(alice.json()["token"])

        create_public = await self._client.post(
            "/spaces/create",
            json={
                "title": "Alice Public Repo",
                "slug": "alice-public",
                "visibility": "public",
            },
            headers=alice_headers,
        )
        self.assertEqual(create_public.status_code, 200, create_public.text)
        public_space_id = create_public.json()["space"]["id"]

        bob = await self._client.post(
            "/auth/register",
            json={"username": "bob", "email": "bob@local", "password": "pass1234"},
        )
        self.assertEqual(bob.status_code, 200, bob.text)
        bob_headers = self._auth_headers(bob.json()["token"])

        listing = await self._client.post("/spaces/list", json={}, headers=bob_headers)
        self.assertEqual(listing.status_code, 200, listing.text)
        payload = listing.json()

        self.assertTrue(payload["mine"])
        self.assertEqual(payload["shared"], [])
        public_space = next((item for item in payload["public"] if item["id"] == public_space_id), None)
        self.assertIsNotNone(public_space)
        self.assertEqual(public_space["space_view"], "public")
        self.assertEqual(public_space["namespace"], "alice")
        self.assertEqual(public_space["namespace_slug"], "alice/alice-public")
        self.assertFalse(public_space["is_owned"])
        self.assertTrue(public_space["is_public"])

        resolve = await self._client.post(
            "/spaces/public/resolve",
            json={"namespace": "alice", "slug": "alice-public"},
            headers=bob_headers,
        )
        self.assertEqual(resolve.status_code, 200, resolve.text)
        self.assertEqual(resolve.json()["space"]["id"], public_space_id)

        namespace_listing = await self._client.post(
            "/spaces/public/namespace",
            json={"namespace": "alice"},
            headers=bob_headers,
        )
        self.assertEqual(namespace_listing.status_code, 200, namespace_listing.text)
        self.assertEqual(namespace_listing.json()["namespace"], "alice")
        self.assertEqual(
            [item["id"] for item in namespace_listing.json()["spaces"]],
            [public_space_id],
        )

        select = await self._client.post(
            "/spaces/select",
            json={"space_id": public_space_id},
            headers=bob_headers,
        )
        self.assertEqual(select.status_code, 200, select.text)
        self.assertEqual(select.json()["space"]["space_view"], "public")
        self.assertEqual(select.json()["space"]["namespace_slug"], "alice/alice-public")

        current = await self._client.post("/spaces/current", json={}, headers=bob_headers)
        self.assertEqual(current.status_code, 200, current.text)
        self.assertEqual(current.json()["space"]["id"], public_space_id)
        self.assertEqual(current.json()["space"]["space_view"], "public")

    async def test_public_repo_page_exposes_refs_history_assets_and_preview(self) -> None:
        alice = await self._client.post(
            "/auth/register",
            json={"username": "alice", "email": "alice@local", "password": "pass1234"},
        )
        self.assertEqual(alice.status_code, 200, alice.text)
        alice_headers = self._auth_headers(alice.json()["token"])

        create_public = await self._client.post(
            "/spaces/create",
            json={
                "title": "Alice Public Repo",
                "slug": "alice-public",
                "visibility": "public",
            },
            headers=alice_headers,
        )
        self.assertEqual(create_public.status_code, 200, create_public.text)

        save = await self._client.post(
            "/workflow/save",
            json={"workflow": _minimal_workflow_payload()},
            headers=alice_headers,
        )
        self.assertEqual(save.status_code, 200, save.text)

        create_ref = await self._client.post(
            "/spaces/repo/refs/create",
            json={"name": "preview", "kind": "branch"},
            headers=alice_headers,
        )
        self.assertEqual(create_ref.status_code, 200, create_ref.text)

        switch_preview = await self._client.post(
            "/spaces/repo/ref/set",
            json={"name": "preview"},
            headers=alice_headers,
        )
        self.assertEqual(switch_preview.status_code, 200, switch_preview.text)

        preview_workflow = _minimal_workflow_payload()
        preview_workflow["options"] = dict(preview_workflow["options"])
        preview_workflow["options"]["name"] = "Preview Workflow"
        preview_workflow["options"]["description"] = "Saved on the preview branch"
        save_preview = await self._client.post(
            "/workflow/save",
            json={"workflow": preview_workflow},
            headers=alice_headers,
        )
        self.assertEqual(save_preview.status_code, 200, save_preview.text)

        switch_main = await self._client.post(
            "/spaces/repo/ref/set",
            json={"name": "main"},
            headers=alice_headers,
        )
        self.assertEqual(switch_main.status_code, 200, switch_main.text)

        bob = await self._client.post(
            "/auth/register",
            json={"username": "bob", "email": "bob@local", "password": "pass1234"},
        )
        self.assertEqual(bob.status_code, 200, bob.text)
        bob_headers = self._auth_headers(bob.json()["token"])

        repo_page = await self._client.post(
            "/spaces/public/repo",
            json={"namespace": "alice", "slug": "alice-public"},
            headers=bob_headers,
        )
        self.assertEqual(repo_page.status_code, 200, repo_page.text)
        page_data = repo_page.json()
        self.assertEqual(page_data["space"]["namespace_slug"], "alice/alice-public")
        self.assertEqual(page_data["default_ref"], "main")
        self.assertEqual(page_data["active_ref"], "main")
        self.assertEqual(page_data["namespace_repo_count"], 1)
        self.assertEqual(
            {item["name"] for item in page_data["refs"]},
            {"main", "preview"},
        )
        self.assertEqual(
            [item["path"] for item in page_data["assets"]],
            ["workflow.json"],
        )
        self.assertTrue(page_data["commits"])
        self.assertEqual(
            [item["id"] for item in page_data["namespace_spaces"]],
            [page_data["space"]["id"]],
        )

        preview = await self._client.post(
            "/spaces/public/repo/assets/read",
            json={"namespace": "alice", "slug": "alice-public", "path": "workflow.json"},
            headers=bob_headers,
        )
        self.assertEqual(preview.status_code, 200, preview.text)
        self.assertEqual(preview.json()["path"], "workflow.json")
        self.assertEqual(preview.json()["active_ref"], "main")
        self.assertIn("Surface Workflow", preview.json()["text"])

        compare = await self._client.post(
            "/spaces/public/repo/compare",
            json={"namespace": "alice", "slug": "alice-public", "left": "preview", "right": "main"},
            headers=bob_headers,
        )
        self.assertEqual(compare.status_code, 200, compare.text)
        compare_data = compare.json()["comparison"]
        self.assertEqual(compare_data["summary"]["total"], 1)
        self.assertEqual(compare_data["changed_paths"][0]["path"], "workflow.json")
        self.assertEqual(compare_data["changed_paths"][0]["status"], "modified")

    async def test_public_creator_page_exposes_repos_and_published_templates(self) -> None:
        alice = await self._client.post(
            "/auth/register",
            json={"username": "alice", "email": "alice@local", "password": "pass1234"},
        )
        self.assertEqual(alice.status_code, 200, alice.text)
        alice_headers = self._auth_headers(alice.json()["token"])

        create_public = await self._client.post(
            "/spaces/create",
            json={
                "title": "Alice Public Repo",
                "slug": "alice-public",
                "visibility": "public",
            },
            headers=alice_headers,
        )
        self.assertEqual(create_public.status_code, 200, create_public.text)

        save = await self._client.post(
            "/workflow/save",
            json={"workflow": _minimal_workflow_payload()},
            headers=alice_headers,
        )
        self.assertEqual(save.status_code, 200, save.text)

        publish = await self._client.post(
            "/workflow/publish-template",
            json={
                "title": "Alice Public Template",
                "description": "Published from a public repo",
                "source_kind": "ref",
                "ref": "main",
            },
            headers=alice_headers,
        )
        self.assertEqual(publish.status_code, 200, publish.text)

        bob = await self._client.post(
            "/auth/register",
            json={"username": "bob", "email": "bob@local", "password": "pass1234"},
        )
        self.assertEqual(bob.status_code, 200, bob.text)
        bob_headers = self._auth_headers(bob.json()["token"])

        creator_page = await self._client.post(
            "/spaces/public/creator",
            json={"creator": "alice", "limit": 10},
            headers=bob_headers,
        )
        self.assertEqual(creator_page.status_code, 200, creator_page.text)
        payload = creator_page.json()
        self.assertEqual(payload["creator"], "alice")
        self.assertEqual(payload["repo_count"], 1)
        self.assertEqual(payload["template_count"], 1)
        self.assertEqual(payload["featured_template_count"], 1)
        self.assertEqual(payload["curated_template_count"], 1)
        self.assertEqual(
            [item["namespace_slug"] for item in payload["spaces"]],
            ["alice/alice-public"],
        )
        template = payload["gallery_items"][0]
        self.assertEqual(template["title"], "Alice Public Template")
        self.assertEqual(template["author"], "alice")
        self.assertEqual(template["metadata"]["source"]["namespace"], "alice")
        self.assertEqual(template["metadata"]["source"]["slug"], "alice-public")
        self.assertEqual(template["metadata"]["source"]["ref"], "main")
        self.assertEqual(template["provenance"]["version_label"], "main")
        self.assertTrue(template["provenance"]["repo_backed"])
        self.assertTrue(template["provenance"]["public_source"])
        self.assertTrue(template["provenance"]["featured"])
        self.assertTrue(template["provenance"]["curated"])
        self.assertIn("alice/alice-public", template["provenance"]["source_label"])

    async def test_space_repo_refs_drive_branch_specific_current_workflow(self) -> None:
        register = await self._client.post(
            "/auth/register",
            json={"username": "alice", "email": "alice@local", "password": "pass1234"},
        )
        self.assertEqual(register.status_code, 200, register.text)
        headers = self._auth_headers(register.json()["token"])

        save_main = await self._client.post(
            "/workflow/save",
            json={"workflow": _minimal_workflow_payload()},
            headers=headers,
        )
        self.assertEqual(save_main.status_code, 200, save_main.text)
        self.assertEqual(save_main.json()["ref"], "main")

        refs_before = await self._client.post("/spaces/repo/refs", json={}, headers=headers)
        self.assertEqual(refs_before.status_code, 200, refs_before.text)
        self.assertEqual(refs_before.json()["active_ref"], "main")
        self.assertIn("main", {item["name"] for item in refs_before.json()["refs"]})

        create_ref = await self._client.post(
            "/spaces/repo/refs/create",
            json={"name": "experiment", "kind": "branch"},
            headers=headers,
        )
        self.assertEqual(create_ref.status_code, 200, create_ref.text)

        switch_ref = await self._client.post(
            "/spaces/repo/ref/set",
            json={"name": "experiment"},
            headers=headers,
        )
        self.assertEqual(switch_ref.status_code, 200, switch_ref.text)
        self.assertEqual(switch_ref.json()["active_ref"], "experiment")
        self.assertEqual(switch_ref.json()["space"]["active_ref"], "experiment")

        experiment_workflow = _minimal_workflow_payload()
        experiment_workflow["options"] = dict(experiment_workflow["options"])
        experiment_workflow["options"]["name"] = "Experiment Workflow"
        experiment_workflow["options"]["description"] = "Saved on the experiment branch"

        save_experiment = await self._client.post(
            "/workflow/save",
            json={"workflow": experiment_workflow},
            headers=headers,
        )
        self.assertEqual(save_experiment.status_code, 200, save_experiment.text)
        self.assertEqual(save_experiment.json()["ref"], "experiment")

        experiment_loaded = await self._client.post("/workflow/get", json={}, headers=headers)
        self.assertEqual(experiment_loaded.status_code, 200, experiment_loaded.text)
        self.assertEqual(experiment_loaded.json()["ref"], "experiment")
        self.assertEqual(experiment_loaded.json()["workflow"]["options"]["name"], "Experiment Workflow")

        experiment_assets = await self._client.post("/spaces/repo/assets", json={}, headers=headers)
        self.assertEqual(experiment_assets.status_code, 200, experiment_assets.text)
        self.assertEqual(experiment_assets.json()["active_ref"], "experiment")
        self.assertEqual(
            [item["path"] for item in experiment_assets.json()["assets"]],
            ["workflow.json"],
        )

        experiment_asset_read = await self._client.post(
            "/spaces/repo/assets/read",
            json={"path": "workflow.json"},
            headers=headers,
        )
        self.assertEqual(experiment_asset_read.status_code, 200, experiment_asset_read.text)
        self.assertEqual(experiment_asset_read.json()["active_ref"], "experiment")
        self.assertIn("Experiment Workflow", experiment_asset_read.json()["text"])

        experiment_history = await self._client.post(
            "/spaces/repo/history",
            json={"limit": 10},
            headers=headers,
        )
        self.assertEqual(experiment_history.status_code, 200, experiment_history.text)
        self.assertEqual(experiment_history.json()["active_ref"], "experiment")
        self.assertTrue(experiment_history.json()["commits"])
        self.assertIn("Experiment Workflow", experiment_history.json()["commits"][0]["message"])

        switch_main = await self._client.post(
            "/spaces/repo/ref/set",
            json={"name": "main"},
            headers=headers,
        )
        self.assertEqual(switch_main.status_code, 200, switch_main.text)
        self.assertEqual(switch_main.json()["active_ref"], "main")

        reloaded_main = await self._client.post("/workflow/get", json={}, headers=headers)
        self.assertEqual(reloaded_main.status_code, 200, reloaded_main.text)
        self.assertEqual(reloaded_main.json()["ref"], "main")
        self.assertEqual(reloaded_main.json()["workflow"]["options"]["name"], "Surface Workflow")

        main_asset_read = await self._client.post(
            "/spaces/repo/assets/read",
            json={"path": "workflow.json"},
            headers=headers,
        )
        self.assertEqual(main_asset_read.status_code, 200, main_asset_read.text)
        self.assertEqual(main_asset_read.json()["active_ref"], "main")
        self.assertIn("Surface Workflow", main_asset_read.json()["text"])

        refs_after = await self._client.post("/spaces/repo/refs", json={}, headers=headers)
        self.assertEqual(refs_after.status_code, 200, refs_after.text)
        self.assertEqual(
            {item["name"] for item in refs_after.json()["refs"]},
            {"experiment", "main"},
        )

        delete_ref = await self._client.post(
            "/spaces/repo/refs/delete",
            json={"name": "experiment"},
            headers=headers,
        )
        self.assertEqual(delete_ref.status_code, 200, delete_ref.text)
        self.assertTrue(delete_ref.json()["ok"])
        self.assertEqual(delete_ref.json()["active_ref"], "main")
        self.assertEqual(
            {item["name"] for item in delete_ref.json()["refs"]},
            {"main"},
        )

    async def test_space_repo_asset_open_switches_current_workflow_asset(self) -> None:
        register = await self._client.post(
            "/auth/register",
            json={"username": "alice", "email": "alice@local", "password": "pass1234"},
        )
        self.assertEqual(register.status_code, 200, register.text)
        payload = register.json()
        headers = self._auth_headers(payload["token"])
        user_id = payload["user"]["id"]

        save_main = await self._client.post(
            "/workflow/save",
            json={"workflow": _minimal_workflow_payload()},
            headers=headers,
        )
        self.assertEqual(save_main.status_code, 200, save_main.text)
        self.assertEqual(save_main.json()["asset_path"], "workflow.json")

        current_space = await self._client.post("/spaces/current", json={}, headers=headers)
        self.assertEqual(current_space.status_code, 200, current_space.text)
        space_id = current_space.json()["space"]["id"]

        alt_workflow = _minimal_workflow_payload()
        alt_workflow["options"] = dict(alt_workflow["options"])
        alt_workflow["options"]["name"] = "Alternate Workflow"
        alt_workflow["options"]["description"] = "Lives at a non-default repo path"

        write_alt = await self._client.post(
            f"/platform/spaces/{space_id}/assets/write",
            json={
                "user_id": user_id,
                "path": "workflows/alternate.json",
                "kind": "workflow",
                "title": "Alternate Workflow",
                "description": "Lives at a non-default repo path",
                "executable": True,
                "text": json.dumps(alt_workflow, indent=2),
                "message": "Add alternate workflow asset",
                "ref": "main",
            },
            headers=headers,
        )
        self.assertEqual(write_alt.status_code, 200, write_alt.text)

        assets = await self._client.post("/spaces/repo/assets", json={}, headers=headers)
        self.assertEqual(assets.status_code, 200, assets.text)
        self.assertEqual(
            [item["path"] for item in assets.json()["assets"]],
            ["workflow.json", "workflows/alternate.json"],
        )

        open_alt = await self._client.post(
            "/spaces/repo/assets/open",
            json={"path": "workflows/alternate.json"},
            headers=headers,
        )
        self.assertEqual(open_alt.status_code, 200, open_alt.text)
        self.assertEqual(open_alt.json()["asset_path"], "workflows/alternate.json")
        self.assertEqual(open_alt.json()["space"]["active_asset_path"], "workflows/alternate.json")
        self.assertEqual(open_alt.json()["workflow"]["options"]["name"], "Alternate Workflow")

        loaded_alt = await self._client.post("/workflow/get", json={}, headers=headers)
        self.assertEqual(loaded_alt.status_code, 200, loaded_alt.text)
        self.assertEqual(loaded_alt.json()["asset_path"], "workflows/alternate.json")
        self.assertEqual(loaded_alt.json()["workflow"]["options"]["name"], "Alternate Workflow")

        alt_history = await self._client.post("/workflow/history", json={"limit": 10}, headers=headers)
        self.assertEqual(alt_history.status_code, 200, alt_history.text)
        self.assertEqual(alt_history.json()["path"], "workflows/alternate.json")

        alt_workflow_saved = json.loads(json.dumps(alt_workflow))
        alt_workflow_saved["options"]["name"] = "Alternate Workflow Saved"
        alt_workflow_saved["options"]["description"] = "Updated through the active repo asset"

        save_alt = await self._client.post(
            "/workflow/save",
            json={"workflow": alt_workflow_saved},
            headers=headers,
        )
        self.assertEqual(save_alt.status_code, 200, save_alt.text)
        self.assertEqual(save_alt.json()["asset_path"], "workflows/alternate.json")

        alt_asset_read = await self._client.post(
            "/spaces/repo/assets/read",
            json={"path": "workflows/alternate.json"},
            headers=headers,
        )
        self.assertEqual(alt_asset_read.status_code, 200, alt_asset_read.text)
        self.assertIn("Alternate Workflow Saved", alt_asset_read.json()["text"])

        main_asset_read = await self._client.post(
            "/spaces/repo/assets/read",
            json={"path": "workflow.json"},
            headers=headers,
        )
        self.assertEqual(main_asset_read.status_code, 200, main_asset_read.text)
        self.assertIn("Surface Workflow", main_asset_read.json()["text"])

        start_alt = await self._client.post("/workflow/start", json={}, headers=headers)
        self.assertEqual(start_alt.status_code, 200, start_alt.text)
        self.assertEqual(start_alt.json()["asset_path"], "workflows/alternate.json")

        executions = await self._client.post("/executions/list", json={}, headers=headers)
        self.assertEqual(executions.status_code, 200, executions.text)
        self.assertEqual(executions.json()["executions"][0]["asset_path"], "workflows/alternate.json")

    async def test_space_repo_compare_and_restore_follow_active_branch(self) -> None:
        register = await self._client.post(
            "/auth/register",
            json={"username": "alice", "email": "alice@local", "password": "pass1234"},
        )
        self.assertEqual(register.status_code, 200, register.text)
        headers = self._auth_headers(register.json()["token"])

        save_main = await self._client.post(
            "/workflow/save",
            json={"workflow": _minimal_workflow_payload()},
            headers=headers,
        )
        self.assertEqual(save_main.status_code, 200, save_main.text)

        create_ref = await self._client.post(
            "/spaces/repo/refs/create",
            json={"name": "experiment", "kind": "branch"},
            headers=headers,
        )
        self.assertEqual(create_ref.status_code, 200, create_ref.text)

        switch_experiment = await self._client.post(
            "/spaces/repo/ref/set",
            json={"name": "experiment"},
            headers=headers,
        )
        self.assertEqual(switch_experiment.status_code, 200, switch_experiment.text)

        experiment_workflow = _minimal_workflow_payload()
        experiment_workflow["options"] = dict(experiment_workflow["options"])
        experiment_workflow["options"]["name"] = "Experiment Workflow"
        experiment_workflow["options"]["description"] = "Saved on the experiment branch"
        save_experiment = await self._client.post(
            "/workflow/save",
            json={"workflow": experiment_workflow},
            headers=headers,
        )
        self.assertEqual(save_experiment.status_code, 200, save_experiment.text)

        experiment_history = await self._client.post(
            "/spaces/repo/history",
            json={"limit": 5},
            headers=headers,
        )
        self.assertEqual(experiment_history.status_code, 200, experiment_history.text)
        experiment_commit_id = experiment_history.json()["commits"][0]["id"]
        self.assertTrue(experiment_commit_id)

        switch_main = await self._client.post(
            "/spaces/repo/ref/set",
            json={"name": "main"},
            headers=headers,
        )
        self.assertEqual(switch_main.status_code, 200, switch_main.text)

        compare = await self._client.post(
            "/spaces/repo/compare",
            json={"left": experiment_commit_id},
            headers=headers,
        )
        self.assertEqual(compare.status_code, 200, compare.text)
        compare_data = compare.json()["comparison"]
        self.assertEqual(compare_data["right"]["selector"], "main")
        self.assertEqual(compare_data["summary"]["total"], 1)
        self.assertEqual(compare_data["changed_paths"][0]["path"], "workflow.json")
        self.assertEqual(compare_data["changed_paths"][0]["status"], "modified")

        restore = await self._client.post(
            "/spaces/repo/restore",
            json={"source": experiment_commit_id, "note": "Restore main from experiment"},
            headers=headers,
        )
        self.assertEqual(restore.status_code, 200, restore.text)
        restore_data = restore.json()
        self.assertEqual(restore_data["ref"], "main")
        self.assertEqual(restore_data["asset_path"], "workflow.json")
        self.assertEqual(restore_data["workflow"]["options"]["name"], "Experiment Workflow")
        self.assertEqual(restore_data["commit"]["message"], "Restore main from experiment")

        reloaded = await self._client.post("/workflow/get", json={}, headers=headers)
        self.assertEqual(reloaded.status_code, 200, reloaded.text)
        self.assertEqual(reloaded.json()["ref"], "main")
        self.assertEqual(reloaded.json()["workflow"]["options"]["name"], "Experiment Workflow")

    async def test_extensions_registry_unifies_toolkits_and_skills(self) -> None:
        registry = await self._client.post("/extensions/registry", json={})
        self.assertEqual(registry.status_code, 200, registry.text)
        payload = registry.json()
        self.assertGreater(payload["counts"]["total"], 0)
        self.assertGreater(payload["counts"]["toolkits"], 0)
        self.assertGreater(payload["counts"]["skills"], 0)
        self.assertIn("shared", payload["counts"])
        self.assertIn("setup_pending", payload["counts"])
        self.assertIn("enabled", payload["counts"])

        entries = payload["entries"]
        self.assertTrue(any(item["kind"] == "toolkit" for item in entries))
        self.assertTrue(any(item["kind"] == "skill" for item in entries))

        file_toolkit = next(item for item in entries if item["id"] == "toolkit:toolkits.file_toolkit")
        self.assertEqual(file_toolkit["title"], "File Toolkit")
        self.assertEqual(file_toolkit["source"], "builtin")
        self.assertEqual(file_toolkit["trust"], "core")
        self.assertEqual(file_toolkit["author"], "Numel")
        self.assertEqual(file_toolkit["module_name"], "toolkits.file_toolkit")
        self.assertFalse(file_toolkit["setup_pending"])
        self.assertIn("local", file_toolkit["platforms"])
        self.assertIn("prod", file_toolkit["platforms"])
        self.assertIn("inspect", file_toolkit["actions"])
        self.assertFalse(file_toolkit["removable"])

        git_skill = next(item for item in entries if item["id"] == "skill:git-assistant")
        self.assertEqual(git_skill["source"], "builtin")
        self.assertEqual(git_skill["trust"], "core")
        self.assertEqual(git_skill["author"], "system")
        self.assertIn("git", git_skill["tags"])
        self.assertIn("scripts", git_skill)
        self.assertIn("install", git_skill)
        self.assertIn("requires", git_skill)
        self.assertIn("view", git_skill["actions"])
        self.assertIn("setup", git_skill["actions"])

    async def test_workflow_template_publish_can_target_ref_or_snapshot(self) -> None:
        register = await self._client.post(
            "/auth/register",
            json={"username": "alice", "email": "alice@local", "password": "pass1234"},
        )
        self.assertEqual(register.status_code, 200, register.text)
        headers = self._auth_headers(register.json()["token"])

        save_main = await self._client.post(
            "/workflow/save",
            json={"workflow": _minimal_workflow_payload()},
            headers=headers,
        )
        self.assertEqual(save_main.status_code, 200, save_main.text)

        create_ref = await self._client.post(
            "/spaces/repo/refs/create",
            json={"name": "preview", "kind": "branch"},
            headers=headers,
        )
        self.assertEqual(create_ref.status_code, 200, create_ref.text)

        switch_preview = await self._client.post(
            "/spaces/repo/ref/set",
            json={"name": "preview"},
            headers=headers,
        )
        self.assertEqual(switch_preview.status_code, 200, switch_preview.text)

        preview_v1 = _minimal_workflow_payload()
        preview_v1["options"] = dict(preview_v1["options"])
        preview_v1["options"]["name"] = "Preview Workflow One"
        preview_v1["options"]["description"] = "First preview branch revision"
        save_preview_v1 = await self._client.post(
            "/workflow/save",
            json={"workflow": preview_v1, "message": "Preview snapshot one"},
            headers=headers,
        )
        self.assertEqual(save_preview_v1.status_code, 200, save_preview_v1.text)

        preview_history = await self._client.post(
            "/workflow/history",
            json={"limit": 10},
            headers=headers,
        )
        self.assertEqual(preview_history.status_code, 200, preview_history.text)
        preview_commit_v1 = preview_history.json()["commits"][0]["id"]
        self.assertTrue(preview_commit_v1)

        preview_v2 = json.loads(json.dumps(preview_v1))
        preview_v2["options"]["name"] = "Preview Workflow Two"
        preview_v2["options"]["description"] = "Second preview branch revision"
        save_preview_v2 = await self._client.post(
            "/workflow/save",
            json={"workflow": preview_v2, "message": "Preview snapshot two"},
            headers=headers,
        )
        self.assertEqual(save_preview_v2.status_code, 200, save_preview_v2.text)

        switch_main = await self._client.post(
            "/spaces/repo/ref/set",
            json={"name": "main"},
            headers=headers,
        )
        self.assertEqual(switch_main.status_code, 200, switch_main.text)

        publish_ref = await self._client.post(
            "/workflow/publish-template",
            json={
                "title": "Preview Ref Template",
                "description": "Publishes the preview branch head.",
                "source_kind": "ref",
                "ref": "preview",
            },
            headers=headers,
        )
        self.assertEqual(publish_ref.status_code, 200, publish_ref.text)
        publish_ref_data = publish_ref.json()
        self.assertEqual(publish_ref_data["source_kind"], "ref")
        self.assertEqual(publish_ref_data["ref"], "preview")
        self.assertEqual(publish_ref_data["asset_path"], "workflow.json")
        self.assertEqual(
            publish_ref_data["item"]["metadata"]["source"]["namespace_slug"],
            "alice/home",
        )
        self.assertEqual(
            publish_ref_data["item"]["metadata"]["source"]["ref"],
            "preview",
        )
        self.assertEqual(
            publish_ref_data["item"]["workflow"]["options"]["name"],
            "Preview Workflow Two",
        )
        self.assertEqual(publish_ref_data["item"]["author"], "alice")

        published_ref = await self._client.post(
            "/gallery/get",
            json={"id": publish_ref_data["item"]["id"]},
            headers=headers,
        )
        self.assertEqual(published_ref.status_code, 200, published_ref.text)
        self.assertEqual(
            published_ref.json()["workflow"]["options"]["name"],
            "Preview Workflow Two",
        )

        publish_snapshot = await self._client.post(
            "/workflow/publish-template",
            json={
                "title": "Preview Snapshot Template",
                "source_kind": "commit",
                "commit_id": preview_commit_v1,
            },
            headers=headers,
        )
        self.assertEqual(publish_snapshot.status_code, 200, publish_snapshot.text)
        publish_snapshot_data = publish_snapshot.json()
        self.assertEqual(publish_snapshot_data["source_kind"], "commit")
        self.assertEqual(publish_snapshot_data["commit_id"], preview_commit_v1)
        self.assertIsNone(publish_snapshot_data["ref"])
        self.assertEqual(
            publish_snapshot_data["item"]["metadata"]["source"]["commit_id"],
            preview_commit_v1,
        )
        self.assertEqual(
            publish_snapshot_data["item"]["workflow"]["options"]["name"],
            "Preview Workflow One",
        )

        published_snapshot = await self._client.post(
            "/gallery/get",
            json={"id": publish_snapshot_data["item"]["id"]},
            headers=headers,
        )
        self.assertEqual(published_snapshot.status_code, 200, published_snapshot.text)
        self.assertEqual(
            published_snapshot.json()["workflow"]["options"]["name"],
            "Preview Workflow One",
        )

    async def test_workflow_interop_import_accepts_n8n_json_and_runs(self) -> None:
        register = await self._client.post(
            "/auth/register",
            json={"username": "interop", "email": "interop@local", "password": "pass1234"},
        )
        self.assertEqual(register.status_code, 200, register.text)
        headers = self._auth_headers(register.json()["token"])

        imported = await self._client.post(
            "/workflow/interop/import",
            json={"document": _n8n_set_workflow_payload(), "file_name": "surface-import.json"},
            headers=headers,
        )
        self.assertEqual(imported.status_code, 200, imported.text)
        payload = imported.json()
        self.assertEqual(payload["source_format"], "n8n")
        self.assertEqual(payload["name"], "n8n Surface Import")
        self.assertIn("Converted n8n workflow", payload["summary"])
        self.assertTrue(any(node["type"] == "transform_flow" for node in payload["workflow"]["nodes"]))

        save = await self._client.post(
            "/workflow/save",
            json={"workflow": payload["workflow"]},
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

    async def test_workflow_interop_import_accepts_n8n_branch_json_and_runs(self) -> None:
        register = await self._client.post(
            "/auth/register",
            json={"username": "interop_branch", "email": "interop_branch@local", "password": "pass1234"},
        )
        self.assertEqual(register.status_code, 200, register.text)
        headers = self._auth_headers(register.json()["token"])

        imported = await self._client.post(
            "/workflow/interop/import",
            json={"document": _n8n_if_workflow_payload(), "file_name": "branch-import.json"},
            headers=headers,
        )
        self.assertEqual(imported.status_code, 200, imported.text)
        payload = imported.json()
        self.assertEqual(payload["source_format"], "n8n")
        self.assertTrue(any(node["type"] == "route_flow" for node in payload["workflow"]["nodes"]))

        save = await self._client.post(
            "/workflow/save",
            json={"workflow": payload["workflow"]},
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

    async def test_agent_edge_config_workflow_saves_with_wired_backend_and_model(self) -> None:
        register = await self._client.post(
            "/auth/register",
            json={"username": "agentedge", "email": "agentedge@local", "password": "pass1234"},
        )
        self.assertEqual(register.status_code, 200, register.text)
        headers = self._auth_headers(register.json()["token"])

        save = await self._client.post(
            "/workflow/save",
            json={"workflow": _agent_edge_workflow_payload()},
            headers=headers,
        )
        self.assertEqual(save.status_code, 200, save.text)
        self.assertEqual(save.json()["status"], "saved")

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
        self.assertEqual(deployment["status"], "disabled")
        self.assertFalse(deployment["enabled"])
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

    async def test_assistant_deployment_network_workflow_exports_live_network(self) -> None:
        register = await self._client.post(
            "/auth/register",
            json={"username": "deploynet", "email": "deploynet@local", "password": "pass1234"},
        )
        self.assertEqual(register.status_code, 200, register.text)
        headers = self._auth_headers(register.json()["token"])

        channel_resp = await self._client.post(
            "/channels/add",
            json={"name": "Network Webhook", "channel_type": "webhook", "auto_start": False},
            headers=headers,
        )
        self.assertEqual(channel_resp.status_code, 200, channel_resp.text)
        channel_id = channel_resp.json()["id"]

        specialist_resp = await self._client.post(
            "/assistant-deployments/create",
            json={
                "name": "Billing Specialist",
                "profile": "billing",
                "channel_ids": [],
                "routing_rules": [],
                "proactive_tasks": [],
            },
            headers=headers,
        )
        self.assertEqual(specialist_resp.status_code, 200, specialist_resp.text)
        specialist_id = specialist_resp.json()["id"]

        frontdoor_resp = await self._client.post(
            "/assistant-deployments/create",
            json={
                "name": "Support Front Door",
                "profile": "triage",
                "handoff_selector_mode": "workflow",
                "handoff_selector_prompt": "Prefer billing for invoice, refund, and charge dispute requests.",
                "channel_ids": [channel_id],
                "routing_rules": [
                    {
                        "name": "Billing Route",
                        "keywords": ["invoice", "refund"],
                        "target_deployment_id": specialist_id,
                        "enabled": True,
                    }
                ],
                "proactive_tasks": [
                    {
                        "name": "Morning Summary",
                        "prompt": "Summarize the top overnight issues.",
                        "interval_sec": 0,
                        "trigger_kind": "channel",
                        "trigger": {"channel_id": channel_id, "sender_filter": "^ops_"},
                        "channel_id": channel_id,
                        "enabled": True,
                        "send_response": True,
                    }
                ],
            },
            headers=headers,
        )
        self.assertEqual(frontdoor_resp.status_code, 200, frontdoor_resp.text)

        network_resp = await self._client.post(
            "/assistant-deployments/network-workflow",
            json={},
            headers=headers,
        )
        self.assertEqual(network_resp.status_code, 200, network_resp.text)
        workflow = network_resp.json()["workflow"]

        validate_resp = await self._client.post(
            "/workflow/validate",
            json={"workflow": workflow},
            headers=headers,
        )
        self.assertEqual(validate_resp.status_code, 200, validate_resp.text)

        node_types = [node["type"] for node in workflow["nodes"]]
        self.assertIn("assistant_deployment_runtime_config", node_types)
        self.assertIn("channel_runtime_config", node_types)
        self.assertIn("assistant_route_runtime_config", node_types)
        self.assertIn("assistant_proactive_runtime_config", node_types)
        self.assertIn("channel_receive_flow", node_types)
        self.assertIn("event_listener_flow", node_types)
        self.assertNotIn("assistant_approval_runtime_config", node_types)
        deployment_node = next(
            node
            for node in workflow["nodes"]
            if node["type"] == "assistant_deployment_runtime_config" and node["deployment_id"] == frontdoor_resp.json()["id"]
        )
        self.assertEqual(deployment_node["handoff_selector_mode"], "workflow")
        self.assertEqual(
            deployment_node["handoff_selector_prompt"],
            "Prefer billing for invoice, refund, and charge dispute requests.",
        )
        proactive_node = next(node for node in workflow["nodes"] if node["type"] == "assistant_proactive_runtime_config")
        self.assertEqual(proactive_node["trigger_kind"], "channel")
        self.assertEqual(proactive_node["trigger"], {"channel_id": channel_id, "sender_filter": "^ops_"})
        self.assertEqual(proactive_node["interval_sec"], 0)

        target_slots = [edge["target_slot"] for edge in workflow["edges"]]
        self.assertTrue(any(slot.startswith("bound_channels.") for slot in target_slots))
        self.assertTrue(any(slot.startswith("outgoing_routes.") for slot in target_slots))
        self.assertTrue(any(slot.startswith("incoming_routes.") for slot in target_slots))
        self.assertTrue(any(slot.startswith("proactive_tasks.") for slot in target_slots))

    async def test_assistant_deployment_network_workflow_apply_round_trips_back_to_runtime(self) -> None:
        register = await self._client.post(
            "/auth/register",
            json={"username": "networkapply", "email": "networkapply@local", "password": "pass1234"},
        )
        self.assertEqual(register.status_code, 200, register.text)
        headers = self._auth_headers(register.json()["token"])

        channel_resp = await self._client.post(
            "/channels/add",
            json={"name": "Support Webhook", "channel_type": "webhook", "auto_start": False},
            headers=headers,
        )
        self.assertEqual(channel_resp.status_code, 200, channel_resp.text)
        channel_id = channel_resp.json()["id"]

        deployment_resp = await self._client.post(
            "/assistant-deployments/create",
            json={
                "name": "Support Front Door",
                "profile": "general",
                "channel_ids": [channel_id],
            },
            headers=headers,
        )
        self.assertEqual(deployment_resp.status_code, 200, deployment_resp.text)
        frontdoor_id = deployment_resp.json()["id"]

        network_resp = await self._client.post(
            "/assistant-deployments/network-workflow",
            json={},
            headers=headers,
        )
        self.assertEqual(network_resp.status_code, 200, network_resp.text)
        workflow = network_resp.json()["workflow"]

        frontdoor_index = next(
            index
            for index, node in enumerate(workflow["nodes"])
            if node.get("type") == "assistant_deployment_runtime_config" and node.get("deployment_id") == frontdoor_id
        )
        channel_index = next(
            index
            for index, node in enumerate(workflow["nodes"])
            if node.get("type") == "channel_runtime_config" and node.get("channel_id") == channel_id
        )

        workflow["nodes"][frontdoor_index]["profile"] = "triage"
        workflow["nodes"][frontdoor_index]["instructions"] = "Route billing traffic to the billing specialist."
        workflow["nodes"][frontdoor_index]["auto_start"] = True
        workflow["nodes"][frontdoor_index]["enabled"] = True
        workflow["nodes"][frontdoor_index]["linked_space_id"] = "space_support"
        workflow["nodes"][frontdoor_index]["linked_space_title"] = "Support"
        workflow["nodes"][frontdoor_index]["linked_workflow_name"] = "Support Front Door"
        workflow["nodes"][frontdoor_index]["toolkit_names"] = ["file_toolkit"]
        workflow["nodes"][frontdoor_index]["skill_names"] = ["faq"]
        workflow["nodes"][frontdoor_index]["handoff_selector_mode"] = "workflow"
        workflow["nodes"][frontdoor_index]["handoff_selector_prompt"] = "Route charge disputes and refund requests to billing."
        workflow["nodes"][frontdoor_index]["proactive_delivery_mode"] = "approval"
        workflow["nodes"][frontdoor_index]["tool_execution_mode"] = "approval"

        workflow["nodes"][channel_index]["name"] = "Primary Support Webhook"
        workflow["nodes"][channel_index]["auto_start"] = True
        workflow["nodes"][channel_index]["session_id"] = "shared_support_session"
        workflow["nodes"][channel_index]["allowed_users"] = ["customer_1", "customer_2"]

        specialist_id = "deploy_billing_manual"
        route_id = "route_billing_manual"
        task_id = "proactive_digest_manual"
        specialist_index = len(workflow["nodes"])
        workflow["nodes"].append(
            {
                "type": "assistant_deployment_runtime_config",
                "deployment_id": specialist_id,
                "name": "Billing Specialist",
                "profile": "billing",
                "description": "Handles invoices and refunds.",
                "instructions": "Focus on billing and refunds.",
                "enabled": False,
                "auto_start": False,
                "model_source": "openai",
                "model_name": "gpt-4o-mini",
                "toolkit_names": ["file_toolkit"],
                "skill_names": [],
                "proactive_delivery_mode": "auto",
                "tool_execution_mode": "auto",
                "pending_approval_count": 0,
                "extra": {"pos": [920, 120], "name": "Billing Specialist"},
            }
        )
        route_index = len(workflow["nodes"])
        workflow["nodes"].append(
            {
                "type": "assistant_route_runtime_config",
                "route_id": route_id,
                "name": "Billing Route",
                "keywords": "invoice, refund",
                "target_deployment_id": specialist_id,
                "enabled": True,
                "extra": {"pos": [720, 220], "name": "Billing Route"},
            }
        )
        task_index = len(workflow["nodes"])
        workflow["nodes"].append(
            {
                "type": "assistant_proactive_runtime_config",
                "task_id": task_id,
                "name": "Daily Digest",
                "prompt": "Summarize open support requests.",
                "interval_sec": 0,
                "channel_id": channel_id,
                "recipient_id": "ops-room",
                "enabled": True,
                "send_response": True,
                "extra": {"pos": [760, 340], "name": "Daily Digest"},
            }
        )
        source_index = len(workflow["nodes"])
        workflow["nodes"].append(
            {
                "type": "webhook_source_flow",
                "source_id": "deploy_proactive_manual",
                "endpoint": "/hook/support-digest",
                "methods": "POST",
                "extra": {"pos": [280, 340], "name": "Daily Digest Trigger"},
            }
        )
        listener_index = len(workflow["nodes"])
        workflow["nodes"].append(
            {
                "type": "event_listener_flow",
                "mode": "any",
                "extra": {"pos": [520, 340], "name": "Daily Digest Listener"},
            }
        )
        workflow["edges"].append(
            {
                "source": route_index,
                "target": frontdoor_index,
                "source_slot": "config",
                "target_slot": "outgoing_routes.billing_route",
            }
        )
        workflow["edges"].append(
            {
                "source": route_index,
                "target": specialist_index,
                "source_slot": "config",
                "target_slot": "incoming_routes.billing_route",
            }
        )
        workflow["edges"].append(
            {
                "source": task_index,
                "target": frontdoor_index,
                "source_slot": "config",
                "target_slot": "proactive_tasks.daily_digest",
            }
        )
        workflow["edges"].append(
            {
                "source": source_index,
                "target": listener_index,
                "source_slot": "registered_id",
                "target_slot": "sources.trigger",
            }
        )
        workflow["edges"].append(
            {
                "source": source_index,
                "target": listener_index,
                "source_slot": "flow_out",
                "target_slot": "flow_in",
            }
        )
        workflow["edges"].append(
            {
                "source": listener_index,
                "target": task_index,
                "source_slot": "event",
                "target_slot": "trigger_event",
            }
        )
        workflow["edges"].append(
            {
                "source": listener_index,
                "target": task_index,
                "source_slot": "source_id",
                "target_slot": "trigger_source_id",
            }
        )

        apply_resp = await self._client.post(
            "/assistant-deployments/network-workflow/apply",
            json={"workflow": workflow},
            headers=headers,
        )
        self.assertEqual(apply_resp.status_code, 200, apply_resp.text)
        payload = apply_resp.json()
        self.assertTrue(payload["applied"])
        self.assertIn(frontdoor_id, payload["updated_deployments"])
        self.assertIn(specialist_id, payload["created_deployments"])
        self.assertIn(channel_id, payload["updated_channels"])

        frontdoor_get = await self._client.post(
            "/assistant-deployments/get",
            json={"id": frontdoor_id},
            headers=headers,
        )
        self.assertEqual(frontdoor_get.status_code, 200, frontdoor_get.text)
        frontdoor = frontdoor_get.json()
        self.assertEqual(frontdoor["profile"], "triage")
        self.assertEqual(frontdoor["instructions"], "Route billing traffic to the billing specialist.")
        self.assertTrue(frontdoor["enabled"])
        self.assertTrue(frontdoor["auto_start"])
        self.assertEqual(frontdoor["linked_space_id"], "space_support")
        self.assertEqual(frontdoor["linked_space_title"], "Support")
        self.assertEqual(frontdoor["linked_workflow_name"], "Support Front Door")
        self.assertEqual(frontdoor["toolkit_names"], ["file_toolkit"])
        self.assertEqual(frontdoor["skill_names"], ["faq"])
        self.assertEqual(frontdoor["handoff_selector_mode"], "workflow")
        self.assertEqual(frontdoor["handoff_selector_prompt"], "Route charge disputes and refund requests to billing.")
        self.assertEqual(frontdoor["safety"]["proactive_delivery_mode"], "approval")
        self.assertEqual(frontdoor["safety"]["tool_execution_mode"], "approval")
        self.assertEqual(len(frontdoor["routing_rules"]), 1)
        self.assertEqual(frontdoor["routing_rules"][0]["target_deployment_id"], specialist_id)
        self.assertEqual(frontdoor["routing_rules"][0]["keywords"], ["invoice", "refund"])
        self.assertEqual(len(frontdoor["proactive_tasks"]), 1)
        self.assertEqual(frontdoor["proactive_tasks"][0]["name"], "Daily Digest")
        self.assertEqual(frontdoor["proactive_tasks"][0]["trigger_kind"], "webhook")
        self.assertEqual(frontdoor["proactive_tasks"][0]["trigger"], {"endpoint": "/hook/support-digest", "methods": "POST"})
        self.assertEqual(frontdoor["proactive_tasks"][0]["interval_sec"], 0)
        self.assertEqual(frontdoor["proactive_tasks"][0]["recipient_id"], "ops-room")
        self.assertEqual(frontdoor["status"], "stopped")

        specialist_get = await self._client.post(
            "/assistant-deployments/get",
            json={"id": specialist_id},
            headers=headers,
        )
        self.assertEqual(specialist_get.status_code, 200, specialist_get.text)
        specialist = specialist_get.json()
        self.assertEqual(specialist["name"], "Billing Specialist")
        self.assertEqual(specialist["profile"], "billing")
        self.assertEqual(specialist["model_source"], "openai")
        self.assertEqual(specialist["model_name"], "gpt-4o-mini")
        self.assertEqual(specialist["toolkit_names"], ["file_toolkit"])

        channels_list = await self._client.post("/channels/list", json={}, headers=headers)
        self.assertEqual(channels_list.status_code, 200, channels_list.text)
        channel_rows = {row["id"]: row for row in channels_list.json()}
        self.assertEqual(channel_rows[channel_id]["name"], "Primary Support Webhook")
        self.assertTrue(channel_rows[channel_id]["auto_start"])
        self.assertEqual(channel_rows[channel_id]["session_id"], "shared_support_session")
        self.assertEqual(channel_rows[channel_id]["allowed_users"], ["customer_1", "customer_2"])

    async def test_assistant_deployment_network_workflow_apply_deletes_missing_runtime_objects(self) -> None:
        register = await self._client.post(
            "/auth/register",
            json={"username": "networkdelete", "email": "networkdelete@local", "password": "pass1234"},
        )
        self.assertEqual(register.status_code, 200, register.text)
        headers = self._auth_headers(register.json()["token"])

        channel_front = await self._client.post(
            "/channels/add",
            json={"name": "Front Webhook", "channel_type": "webhook", "auto_start": False},
            headers=headers,
        )
        self.assertEqual(channel_front.status_code, 200, channel_front.text)
        front_channel_id = channel_front.json()["id"]

        channel_extra = await self._client.post(
            "/channels/add",
            json={"name": "Extra Webhook", "channel_type": "webhook", "auto_start": False},
            headers=headers,
        )
        self.assertEqual(channel_extra.status_code, 200, channel_extra.text)
        extra_channel_id = channel_extra.json()["id"]

        frontdoor = await self._client.post(
            "/assistant-deployments/create",
            json={"name": "Front Door", "channel_ids": [front_channel_id]},
            headers=headers,
        )
        self.assertEqual(frontdoor.status_code, 200, frontdoor.text)
        frontdoor_id = frontdoor.json()["id"]

        specialist = await self._client.post(
            "/assistant-deployments/create",
            json={"name": "Specialist", "channel_ids": []},
            headers=headers,
        )
        self.assertEqual(specialist.status_code, 200, specialist.text)
        specialist_id = specialist.json()["id"]

        network_resp = await self._client.post(
            "/assistant-deployments/network-workflow",
            json={},
            headers=headers,
        )
        self.assertEqual(network_resp.status_code, 200, network_resp.text)
        workflow = network_resp.json()["workflow"]

        removed_indexes = {
            index
            for index, node in enumerate(workflow["nodes"])
            if (node.get("type") == "assistant_deployment_runtime_config" and node.get("deployment_id") == specialist_id)
            or (node.get("type") == "channel_runtime_config" and node.get("channel_id") == extra_channel_id)
        }
        remap = {}
        filtered_nodes = []
        for index, node in enumerate(workflow["nodes"]):
            if index in removed_indexes:
                continue
            remap[index] = len(filtered_nodes)
            filtered_nodes.append(node)
        filtered_edges = []
        for edge in workflow["edges"]:
            source = edge.get("source")
            target = edge.get("target")
            if source not in remap or target not in remap:
                continue
            filtered_edges.append(
                {
                    **edge,
                    "source": remap[source],
                    "target": remap[target],
                }
            )
        workflow["nodes"] = filtered_nodes
        workflow["edges"] = filtered_edges

        apply_resp = await self._client.post(
            "/assistant-deployments/network-workflow/apply",
            json={"workflow": workflow},
            headers=headers,
        )
        self.assertEqual(apply_resp.status_code, 200, apply_resp.text)
        payload = apply_resp.json()
        self.assertTrue(payload["prune_missing"])
        self.assertIn(specialist_id, payload["deleted_deployments"])
        self.assertIn(extra_channel_id, payload["deleted_channels"])
        self.assertNotIn(frontdoor_id, payload["deleted_deployments"])
        self.assertNotIn(front_channel_id, payload["deleted_channels"])

        specialist_get = await self._client.post(
            "/assistant-deployments/get",
            json={"id": specialist_id},
            headers=headers,
        )
        self.assertEqual(specialist_get.status_code, 200, specialist_get.text)
        self.assertEqual(specialist_get.json(), {"error": "not found"})

        channels_list = await self._client.post("/channels/list", json={}, headers=headers)
        self.assertEqual(channels_list.status_code, 200, channels_list.text)
        channel_rows = {row["id"]: row for row in channels_list.json()}
        self.assertIn(front_channel_id, channel_rows)
        self.assertNotIn(extra_channel_id, channel_rows)

    async def test_assistant_deployment_lifecycle_does_not_control_bound_channels(self) -> None:
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
        self.assertEqual(started.json()["status"], "stopped")

        channel_status = await self._client.post("/channels/status", json={"channel_id": channel_id}, headers=headers)
        self.assertEqual(channel_status.status_code, 200, channel_status.text)
        self.assertEqual(channel_status.json()["status"], "stopped")

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

    async def test_stopping_deployment_does_not_stop_channel_already_running(self) -> None:
        register = await self._client.post(
            "/auth/register",
            json={"username": "deploykeep", "email": "deploykeep@local", "password": "pass1234"},
        )
        self.assertEqual(register.status_code, 200, register.text)
        headers = self._auth_headers(register.json()["token"])

        channel = await self._client.post(
            "/channels/add",
            json={"name": "Already Running Webhook", "channel_type": "webhook", "auto_start": False},
            headers=headers,
        )
        self.assertEqual(channel.status_code, 200, channel.text)
        channel_id = channel.json()["id"]

        channel_started = await self._client.post(
            "/channels/start",
            json={"channel_id": channel_id},
            headers=headers,
        )
        self.assertEqual(channel_started.status_code, 200, channel_started.text)
        self.assertEqual(channel_started.json()["status"], "running")

        created = await self._client.post(
            "/assistant-deployments/create",
            json={"name": "Keep Channel Alive", "channel_ids": [channel_id]},
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

        stopped = await self._client.post(
            "/assistant-deployments/stop",
            json={"id": deployment_id},
            headers=headers,
        )
        self.assertEqual(stopped.status_code, 200, stopped.text)
        self.assertEqual(stopped.json()["status"], "disabled")

        channel_status = await self._client.post("/channels/status", json={"channel_id": channel_id}, headers=headers)
        self.assertEqual(channel_status.status_code, 200, channel_status.text)
        self.assertEqual(channel_status.json()["status"], "running")

    async def test_assistant_deployment_channel_conflict_requires_explicit_rebind(self) -> None:
        register = await self._client.post(
            "/auth/register",
            json={"username": "deploybind", "email": "deploybind@local", "password": "pass1234"},
        )
        self.assertEqual(register.status_code, 200, register.text)
        headers = self._auth_headers(register.json()["token"])

        channel = await self._client.post(
            "/channels/add",
            json={"name": "Shared Webhook", "channel_type": "webhook", "auto_start": False},
            headers=headers,
        )
        self.assertEqual(channel.status_code, 200, channel.text)
        channel_id = channel.json()["id"]

        first = await self._client.post(
            "/assistant-deployments/create",
            json={"name": "First Owner", "channel_ids": [channel_id]},
            headers=headers,
        )
        self.assertEqual(first.status_code, 200, first.text)
        first_id = first.json()["id"]

        conflict = await self._client.post(
            "/assistant-deployments/create",
            json={"name": "Second Owner", "channel_ids": [channel_id]},
            headers=headers,
        )
        self.assertEqual(conflict.status_code, 409, conflict.text)
        detail = conflict.json()["detail"]
        self.assertEqual(detail["code"], "channel_conflict")
        self.assertEqual(detail["conflicts"][0]["channel_id"], channel_id)
        self.assertEqual(detail["conflicts"][0]["existing_deployment_id"], first_id)

        rebound = await self._client.post(
            "/assistant-deployments/create",
            json={"name": "Second Owner", "channel_ids": [channel_id], "force_rebind_channels": True},
            headers=headers,
        )
        self.assertEqual(rebound.status_code, 200, rebound.text)
        rebound_id = rebound.json()["id"]
        self.assertEqual(rebound.json()["channel_ids"], [channel_id])

        first_get = await self._client.post(
            "/assistant-deployments/get",
            json={"id": first_id},
            headers=headers,
        )
        self.assertEqual(first_get.status_code, 200, first_get.text)
        self.assertEqual(first_get.json()["channel_ids"], [])

        rebound_get = await self._client.post(
            "/assistant-deployments/get",
            json={"id": rebound_id},
            headers=headers,
        )
        self.assertEqual(rebound_get.status_code, 200, rebound_get.text)
        self.assertEqual(rebound_get.json()["channel_ids"], [channel_id])

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

    async def test_assistant_deployment_event_driven_proactive_task_starts_cleanly(self) -> None:
        register = await self._client.post(
            "/auth/register",
            json={"username": "deployevent", "email": "deployevent@local", "password": "pass1234"},
        )
        self.assertEqual(register.status_code, 200, register.text)
        headers = self._auth_headers(register.json()["token"])

        channel = await self._client.post(
            "/channels/add",
            json={"name": "Event Webhook", "channel_type": "webhook", "auto_start": False},
            headers=headers,
        )
        self.assertEqual(channel.status_code, 200, channel.text)
        channel_id = channel.json()["id"]

        created = await self._client.post(
            "/assistant-deployments/create",
            json={
                "name": "Event Assistant",
                "channel_ids": [channel_id],
                "proactive_tasks": [
                    {
                        "name": "Webhook Draft",
                        "prompt": "Prepare a concise response for the trigger event.",
                        "interval_sec": 0,
                        "trigger_kind": "webhook",
                        "trigger": {"endpoint": "/hook/event-assistant", "methods": "POST"},
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
        self.assertEqual(started_task["trigger_kind"], "webhook")
        self.assertEqual(started_task["interval_sec"], 0)
        self.assertEqual(started_task["runtime"]["status"], "scheduled")
        self.assertIsNone(started_task["runtime"]["next_run_at"])

        stopped = await self._client.post(
            "/assistant-deployments/stop",
            json={"id": deployment_id},
            headers=headers,
        )
        self.assertEqual(stopped.status_code, 200, stopped.text)

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

        async def _fake_workflow_run(**kwargs):
            captured.update(kwargs)
            return {
                "response": "Pulse: all quiet",
                "tool_calls": [],
                "workflow_name": "Deployment Proactive Task: Pulse Assistant",
                "engine_execution_id": "exec_test_proactive",
                "workflow_backed": True,
            }

        async def _fake_send(recipient_id, text, **kwargs):
            deliveries.append((recipient_id, text))
            return True

        import assistant_deployments as assistant_deployments_module

        adapter = self._app.state.channel_registry.get(channel_id)
        original_workflow_run = assistant_deployments_module.run_workflow_backed_agent_turn
        original_send = adapter.send
        assistant_deployments_module.run_workflow_backed_agent_turn = _fake_workflow_run
        adapter.send = _fake_send
        try:
            run_now = await self._client.post(
                "/assistant-deployments/run-proactive",
                json={"id": deployment_id, "task_id": task_id},
                headers=headers,
            )
        finally:
            assistant_deployments_module.run_workflow_backed_agent_turn = original_workflow_run
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
        self.assertEqual(captured["workflow_name"], "Deployment Proactive Task: Pulse Assistant")
        self.assertIn("file_toolkit", list(captured.get("toolkit_names") or []))
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
        self.assertTrue(deployment["recent_proactive_runs"][0]["workflow_backed"])
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

        async def _fake_workflow_run(**kwargs):
            captured.update(kwargs)
            return {
                "response": "Approval pulse ready",
                "tool_calls": [],
                "workflow_name": "Deployment Proactive Task: Approval Assistant",
                "engine_execution_id": "exec_test_approval",
                "workflow_backed": True,
            }

        async def _fake_send(recipient_id, text, **kwargs):
            deliveries.append((recipient_id, text))
            return True

        import assistant_deployments as assistant_deployments_module

        adapter = self._app.state.channel_registry.get(channel_id)
        original_workflow_run = assistant_deployments_module.run_workflow_backed_agent_turn
        original_send = adapter.send
        assistant_deployments_module.run_workflow_backed_agent_turn = _fake_workflow_run
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
            assistant_deployments_module.run_workflow_backed_agent_turn = original_workflow_run
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
        deployment_id = created.json()["id"]

        started = await self._client.post(
            "/assistant-deployments/start",
            json={"id": deployment_id},
            headers=headers,
        )
        self.assertEqual(started.status_code, 200, started.text)

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

        specialist_started = await self._client.post(
            "/assistant-deployments/start",
            json={"id": specialist_id},
            headers=headers,
        )
        self.assertEqual(specialist_started.status_code, 200, specialist_started.text)

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

        front_started = await self._client.post(
            "/assistant-deployments/start",
            json={"id": front_door_id},
            headers=headers,
        )
        self.assertEqual(front_started.status_code, 200, front_started.text)

        captured_calls: list[dict[str, object]] = []

        async def _fake_chat(message, session_id, **kwargs):
            captured_calls.append(
                {
                    "message": message,
                    "session_id": session_id,
                    **kwargs,
                }
            )
            return {"response": "handled by specialist", "tool_calls": []}

        channel_pool = self._app.state.console_mgr._channel_pool
        original_chat = channel_pool.chat
        channel_pool.chat = _fake_chat
        try:
            first_response = await self._client.post(
                f"/channels/webhook/{channel_id}",
                json={"text": "Can you help with an invoice discrepancy?", "sender_id": "customer_1", "sender_name": "Customer"},
            )
            second_response = await self._client.post(
                f"/channels/webhook/{channel_id}",
                json={"text": "Thanks. What documents do you need from me?", "sender_id": "customer_1", "sender_name": "Customer"},
            )
        finally:
            channel_pool.chat = original_chat

        self.assertEqual(first_response.status_code, 200, first_response.text)
        self.assertEqual(second_response.status_code, 200, second_response.text)
        self.assertEqual(len(captured_calls), 2)
        first_call = captured_calls[0]
        second_call = captured_calls[1]
        self.assertEqual(first_call["assistant_name"], "Billing Specialist")
        self.assertEqual(first_call["model_source"], "openai")
        self.assertEqual(first_call["model_name"], "gpt-4o-mini")
        self.assertEqual(first_call["toolkits"], ["file_toolkit"])
        self.assertTrue(str(first_call["session_id"]).startswith(f"deploy_{specialist_id}"))
        self.assertEqual(second_call["assistant_name"], "Billing Specialist")
        self.assertEqual(second_call["session_id"], first_call["session_id"])
        extra_instructions = first_call.get("extra_instructions") or []
        self.assertTrue(any("[Assistant Handoff]" in str(item) for item in extra_instructions))
        self.assertTrue(any("invoice" in str(item).lower() for item in extra_instructions))
        active_handoff_instructions = second_call.get("extra_instructions") or []
        self.assertTrue(any("[Assistant Handoff]" in str(item) for item in active_handoff_instructions))

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
        self.assertEqual(front_data["recent_handoffs"][0]["selector_mode"], "keyword")
        self.assertTrue(any(row["kind"] == "handoff" for row in front_data["recent_activity"]))

        specialist_get = await self._client.post(
            "/assistant-deployments/get",
            json={"id": specialist_id},
            headers=headers,
        )
        self.assertEqual(specialist_get.status_code, 200, specialist_get.text)
        specialist_data = specialist_get.json()
        self.assertEqual(specialist_data["runtime"]["message_count"], 2)
        self.assertEqual(specialist_data["runtime"]["last_handoff_from"], front_door_id)
        self.assertEqual(len(specialist_data["recent_handoffs"]), 1)
        self.assertTrue(any(row["kind"] == "routed_message" for row in specialist_data["recent_activity"]))

    async def test_assistant_deployment_hybrid_selector_routes_without_keyword_match(self) -> None:
        register = await self._client.post(
            "/auth/register",
            json={"username": "hybridroute", "email": "hybridroute@local", "password": "pass1234"},
        )
        self.assertEqual(register.status_code, 200, register.text)
        headers = self._auth_headers(register.json()["token"])

        channel = await self._client.post(
            "/channels/add",
            json={"name": "Hybrid Routing Webhook", "channel_type": "webhook", "auto_start": False},
            headers=headers,
        )
        self.assertEqual(channel.status_code, 200, channel.text)
        channel_id = channel.json()["id"]

        specialist = await self._client.post(
            "/assistant-deployments/create",
            json={
                "name": "Billing Specialist",
                "profile": "billing",
                "description": "Handles invoices, refunds, and charge disputes.",
            },
            headers=headers,
        )
        self.assertEqual(specialist.status_code, 200, specialist.text)
        specialist_id = specialist.json()["id"]

        route_id = "route_semantic_billing"
        front_door = await self._client.post(
            "/assistant-deployments/create",
            json={
                "name": "Support Front Door",
                "profile": "triage",
                "description": "Routes support traffic to specialists.",
                "channel_ids": [channel_id],
                "routing_rules": [
                    {
                        "id": route_id,
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
        self.assertEqual(front_door.json()["handoff_selector_mode"], "hybrid")

        specialist_started = await self._client.post(
            "/assistant-deployments/start",
            json={"id": specialist_id},
            headers=headers,
        )
        self.assertEqual(specialist_started.status_code, 200, specialist_started.text)
        front_started = await self._client.post(
            "/assistant-deployments/start",
            json={"id": front_door_id},
            headers=headers,
        )
        self.assertEqual(front_started.status_code, 200, front_started.text)

        captured_calls: list[dict[str, object]] = []

        async def _fake_chat(message, session_id, **kwargs):
            captured_calls.append(
                {
                    "message": message,
                    "session_id": session_id,
                    **kwargs,
                }
            )
            return {"response": "handled by semantic billing specialist", "tool_calls": []}

        async def _fake_selector_turn(*args, **kwargs):
            return {
                "response": json.dumps(
                    {
                        "route_id": route_id,
                        "reason": "Charge disputes should be handled by billing even without explicit invoice keywords.",
                        "matched_keywords": ["charge dispute"],
                    }
                )
            }

        channel_pool = self._app.state.console_mgr._channel_pool
        original_chat = channel_pool.chat
        channel_pool.chat = _fake_chat
        try:
            with patch("assistant_deployments.run_workflow_backed_agent_turn", _fake_selector_turn):
                first_response = await self._client.post(
                    f"/channels/webhook/{channel_id}",
                    json={"text": "There is a charge dispute on my account.", "sender_id": "customer_3", "sender_name": "Customer"},
                )
                second_response = await self._client.post(
                    f"/channels/webhook/{channel_id}",
                    json={"text": "What details do you need from me?", "sender_id": "customer_3", "sender_name": "Customer"},
                )
        finally:
            channel_pool.chat = original_chat

        self.assertEqual(first_response.status_code, 200, first_response.text)
        self.assertEqual(second_response.status_code, 200, second_response.text)
        self.assertEqual(len(captured_calls), 2)
        self.assertEqual(captured_calls[0]["assistant_name"], "Billing Specialist")
        self.assertEqual(captured_calls[1]["assistant_name"], "Billing Specialist")
        self.assertEqual(captured_calls[1]["session_id"], captured_calls[0]["session_id"])

        front_door_get = await self._client.post(
            "/assistant-deployments/get",
            json={"id": front_door_id},
            headers=headers,
        )
        self.assertEqual(front_door_get.status_code, 200, front_door_get.text)
        front_data = front_door_get.json()
        self.assertEqual(front_data["handoff_selector_mode"], "hybrid")
        self.assertEqual(len(front_data["recent_handoffs"]), 1)
        self.assertEqual(front_data["recent_handoffs"][0]["selector_mode"], "workflow")
        self.assertEqual(front_data["recent_handoffs"][0]["target_deployment_id"], specialist_id)

    async def test_assistant_deployment_handoff_can_return_to_front_door(self) -> None:
        register = await self._client.post(
            "/auth/register",
            json={"username": "handoffreturn", "email": "handoffreturn@local", "password": "pass1234"},
        )
        self.assertEqual(register.status_code, 200, register.text)
        headers = self._auth_headers(register.json()["token"])

        channel = await self._client.post(
            "/channels/add",
            json={"name": "Return Webhook", "channel_type": "webhook", "auto_start": False},
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

        specialist_update = await self._client.post(
            "/assistant-deployments/update",
            json={
                "id": specialist_id,
                "routing_rules": [
                    {
                        "name": "return",
                        "target_deployment_id": front_door_id,
                        "keywords": ["general"],
                    }
                ],
            },
            headers=headers,
        )
        self.assertEqual(specialist_update.status_code, 200, specialist_update.text)

        specialist_started = await self._client.post(
            "/assistant-deployments/start",
            json={"id": specialist_id},
            headers=headers,
        )
        self.assertEqual(specialist_started.status_code, 200, specialist_started.text)
        front_started = await self._client.post(
            "/assistant-deployments/start",
            json={"id": front_door_id},
            headers=headers,
        )
        self.assertEqual(front_started.status_code, 200, front_started.text)

        captured_calls: list[dict[str, object]] = []

        async def _fake_chat(message, session_id, **kwargs):
            captured_calls.append(
                {
                    "message": message,
                    "session_id": session_id,
                    **kwargs,
                }
            )
            return {"response": "ok", "tool_calls": []}

        channel_pool = self._app.state.console_mgr._channel_pool
        original_chat = channel_pool.chat
        channel_pool.chat = _fake_chat
        try:
            first_response = await self._client.post(
                f"/channels/webhook/{channel_id}",
                json={"text": "I need help with an invoice", "sender_id": "customer_2", "sender_name": "Customer"},
            )
            second_response = await self._client.post(
                f"/channels/webhook/{channel_id}",
                json={"text": "Actually this is a general support question.", "sender_id": "customer_2", "sender_name": "Customer"},
            )
        finally:
            channel_pool.chat = original_chat

        self.assertEqual(first_response.status_code, 200, first_response.text)
        self.assertEqual(second_response.status_code, 200, second_response.text)
        self.assertEqual(len(captured_calls), 2)
        self.assertEqual(captured_calls[0]["assistant_name"], "Billing Specialist")
        self.assertTrue(str(captured_calls[0]["session_id"]).startswith(f"deploy_{specialist_id}"))
        self.assertEqual(captured_calls[1]["assistant_name"], "Support Front Door")
        self.assertTrue(str(captured_calls[1]["session_id"]).startswith(f"deploy_{front_door_id}"))
        self.assertNotEqual(captured_calls[0]["session_id"], captured_calls[1]["session_id"])

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

    async def test_agent_endpoint_options_are_user_scoped_and_context_aware(self) -> None:
        kinds_response = await self._client.post("/options/agent_endpoint_kinds", json={})
        self.assertEqual(kinds_response.status_code, 200, kinds_response.text)
        self.assertEqual(kinds_response.json()["options"], ["deployment", "a2a_remote"])

        modes_response = await self._client.post("/options/agent_endpoint_modes", json={})
        self.assertEqual(modes_response.status_code, 200, modes_response.text)
        self.assertEqual(modes_response.json()["options"], ["consult", "delegate", "notify"])

        bootstrap = await self._client.post(
            "/auth/register",
            json={"username": "endpointadmin", "email": "endpointadmin@local", "password": "pass1234"},
        )
        self.assertEqual(bootstrap.status_code, 200, bootstrap.text)

        alice_register = await self._client.post(
            "/auth/register",
            json={"username": "endpointalice", "email": "endpointalice@local", "password": "pass1234"},
        )
        self.assertEqual(alice_register.status_code, 200, alice_register.text)
        alice_headers = self._auth_headers(alice_register.json()["token"])

        bob_register = await self._client.post(
            "/auth/register",
            json={"username": "endpointbob", "email": "endpointbob@local", "password": "pass1234"},
        )
        self.assertEqual(bob_register.status_code, 200, bob_register.text)
        bob_headers = self._auth_headers(bob_register.json()["token"])

        alice_deploy = await self._client.post(
            "/assistant-deployments/create",
            json={"name": "Alice Specialist", "description": "Alice-only deployment."},
            headers=alice_headers,
        )
        self.assertEqual(alice_deploy.status_code, 200, alice_deploy.text)
        alice_id = alice_deploy.json()["id"]

        bob_deploy = await self._client.post(
            "/assistant-deployments/create",
            json={"name": "Bob Specialist", "description": "Bob-only deployment."},
            headers=bob_headers,
        )
        self.assertEqual(bob_deploy.status_code, 200, bob_deploy.text)
        bob_id = bob_deploy.json()["id"]

        anonymous_targets = await self._client.post("/options/agent_endpoint_targets", json={"kind": "deployment"})
        self.assertEqual(anonymous_targets.status_code, 200, anonymous_targets.text)
        self.assertEqual(anonymous_targets.json()["options"], [])

        alice_targets = await self._client.post(
            "/options/agent_endpoint_targets",
            json={"kind": "deployment"},
            headers=alice_headers,
        )
        self.assertEqual(alice_targets.status_code, 200, alice_targets.text)
        alice_options = alice_targets.json()["options"]
        self.assertEqual(len(alice_options), 1)
        self.assertEqual(alice_options[0]["value"], alice_id)
        self.assertIn("Alice Specialist", alice_options[0]["label"])

        bob_targets = await self._client.post(
            "/options/agent_endpoint_targets",
            json={"kind": "deployment"},
            headers=bob_headers,
        )
        self.assertEqual(bob_targets.status_code, 200, bob_targets.text)
        bob_options = bob_targets.json()["options"]
        self.assertEqual(len(bob_options), 1)
        self.assertEqual(bob_options[0]["value"], bob_id)
        self.assertIn("Bob Specialist", bob_options[0]["label"])

        remote_targets = await self._client.post(
            "/options/agent_endpoint_targets",
            json={"kind": "a2a_remote"},
            headers=alice_headers,
        )
        self.assertEqual(remote_targets.status_code, 200, remote_targets.text)
        self.assertEqual(remote_targets.json()["options"], [])

    async def test_console_workflow_endpoint_exports_current_console_shape(self) -> None:
        response = await self._client.post("/console/workflow", json={})
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()
        workflow = data["workflow"]
        node_types = [node["type"] for node in workflow["nodes"]]
        self.assertNotIn("backend_config", node_types)
        self.assertIn("model_config", node_types)
        self.assertIn("agent_options_config", node_types)
        self.assertIn("agent_config", node_types)
        self.assertIn("agent_chat", node_types)
        toolkit_names = [node.get("name") for node in workflow["nodes"] if node.get("type") == "toolkit_config"]
        self.assertIn("console_toolkit", toolkit_names)
        self.assertIn("console_toolkit", data["runtime_bound_toolkits"])

    async def test_console_workflow_endpoint_can_include_active_planner_branch(self) -> None:
        register = await self._client.post(
            "/auth/register",
            json={"username": "plannergraph", "email": "plannergraph@local", "password": "pass1234"},
        )
        self.assertEqual(register.status_code, 200, register.text)
        headers = self._auth_headers(register.json()["token"])

        enabled = await self._client.post(
            "/console/planner/enable",
            json={"session_id": "tab_planner_export", "profile": "workflow"},
            headers=headers,
        )
        self.assertEqual(enabled.status_code, 200, enabled.text)

        response = await self._client.post(
            "/console/workflow",
            json={"include_planner": True, "session_id": "tab_planner_export"},
            headers=headers,
        )
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()
        workflow = data["workflow"]
        node_types = [node["type"] for node in workflow["nodes"]]

        self.assertTrue(data["planner_requested"])
        self.assertTrue(data["planner_available"])
        self.assertTrue(data["planner_included"])
        self.assertIn("agent_chat", node_types)
        self.assertIn("agent_flow", node_types)
        self.assertIn("loop_start_flow", node_types)
        planner_turn = next(
            node for node in workflow["nodes"]
            if node.get("type") == "agent_flow" and node.get("extra", {}).get("name") == "Planner Turn · current workbench"
        )
        self.assertIn("[Planner Export]", planner_turn.get("request") or "")
        planner_loop = next(
            node for node in workflow["nodes"]
            if node.get("type") == "loop_start_flow" and "Planner Loop" in (node.get("extra", {}).get("name") or "")
        )
        self.assertEqual(planner_loop.get("max_iter"), 10)

    async def test_console_workflow_apply_endpoint_reconfigures_console(self) -> None:
        exported = await self._client.post("/console/workflow", json={})
        self.assertEqual(exported.status_code, 200, exported.text)
        workflow = exported.json()["workflow"]

        for node in workflow["nodes"]:
            if node.get("type") == "model_config":
                node["source"] = "openai"
                node["name"] = "gpt-4o-mini"
            elif node.get("type") == "agent_options_config":
                node["name"] = "Workbench Assistant"
                node["description"] = "Imported from a workflow-backed console."
                node["instructions"] = ["Stay focused on the current workbench."]
            elif node.get("type") == "session_manager_config":
                node["history_size"] = 9

        apply_response = await self._client.post("/console/workflow/apply", json={"workflow": workflow})
        self.assertEqual(apply_response.status_code, 200, apply_response.text)
        payload = apply_response.json()
        self.assertTrue(payload["started"])
        self.assertEqual(payload["model_source"], "openai")
        self.assertEqual(payload["model_name"], "gpt-4o-mini")
        self.assertEqual(payload["options"]["name"], "Workbench Assistant")
        self.assertEqual(payload["options"]["description"], "Imported from a workflow-backed console.")
        self.assertEqual(payload["options"]["instructions"], ["Stay focused on the current workbench."])
        self.assertEqual(payload["memory_override"]["session_history"], 9)
        self.assertEqual(payload["memory_override"]["history_size"], 5)

        exported_again = await self._client.post("/console/workflow", json={})
        self.assertEqual(exported_again.status_code, 200, exported_again.text)
        roundtrip = exported_again.json()["workflow"]
        option_nodes = [node for node in roundtrip["nodes"] if node.get("type") == "agent_options_config"]
        self.assertEqual(len(option_nodes), 1)
        self.assertEqual(option_nodes[0]["name"], "Workbench Assistant")

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
