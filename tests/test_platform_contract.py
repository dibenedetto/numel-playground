from __future__ import annotations

import asyncio
import json
import shutil
import sys
import unittest
import uuid
from pathlib import Path

import httpx
from fastapi import FastAPI


PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = PROJECT_ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from event_bus import EventBus
from platform_http import setup_platform_api
from platform_local import (
    ArtifactStorageConfig,
    DatabaseConfig,
    GitStorageConfig,
    build_local_platform_stack,
)
from workspace import WorkspaceManager


def _minimal_workflow_payload() -> dict:
    return {
        "type": "workflow",
        "options": {
            "name": "Contract Workflow",
            "description": "Minimal workflow for platform contract tests",
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


@unittest.skipUnless(shutil.which("git"), "git is required for platform contract tests")
class PlatformContractTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._root = PROJECT_ROOT / "storage" / "_test_runs" / f"contract_{uuid.uuid4().hex[:8]}"
        self._root.mkdir(parents=True, exist_ok=True)
        self._workspace_root = self._root / "workspaces"
        self._db_path = self._root / "platform.db"
        self._spaces_root = self._root / "spaces"
        self._artifacts_root = self._root / "artifacts"

        self._event_bus = EventBus()
        self._workspace_mgr = WorkspaceManager(
            base_port=18600,
            event_bus=self._event_bus,
            storage_root=self._workspace_root,
        )
        await self._workspace_mgr.initialize()

        self._stack = build_local_platform_stack(
            db_config=DatabaseConfig(url=f"sqlite:///{self._db_path.as_posix()}"),
            git_config=GitStorageConfig(repos_root=str(self._spaces_root)),
            artifact_config=ArtifactStorageConfig(root_path=str(self._artifacts_root)),
            workspace_manager=self._workspace_mgr,
        )

        self._app = FastAPI()
        self._internal_token = "test-internal-token"
        setup_platform_api(self._app, self._stack, self._internal_token)
        self._client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self._app),
            base_url="http://platform.test",
        )

    async def asyncTearDown(self) -> None:
        await self._client.aclose()
        await self._stack.aclose()
        await self._workspace_mgr.shutdown()
        shutil.rmtree(self._root, ignore_errors=True)

    def _auth_headers(self, token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}"}

    async def _post(self, path: str, *, token: str | None = None, json_body: dict | None = None):
        headers = self._auth_headers(token) if token else None
        return await self._client.post(path, json=json_body or {}, headers=headers)

    async def _register(self, username: str, *, email: str | None = None, password: str = "pass1234"):
        response = await self._post(
            "/platform/auth/register",
            json_body={
                "username": username,
                "email": email or f"{username}@local",
                "password": password,
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        return payload["token"], payload["user"]

    async def _create_space(self, token: str, *, title: str, visibility: str = "private"):
        response = await self._post(
            "/platform/spaces/create",
            token=token,
            json_body={"title": title, "visibility": visibility},
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["space"]

    async def _write_workflow_asset(self, token: str, space_id: str, path: str = "workflow.json"):
        response = await self._post(
            f"/platform/spaces/{space_id}/assets/write",
            token=token,
            json_body={
                "path": path,
                "kind": "workflow",
                "visibility": "private",
                "executable": True,
                "text": json.dumps(_minimal_workflow_payload()),
                "message": "Add test workflow",
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["commit"]

    async def test_auth_bootstrap_and_login_contract(self) -> None:
        status_before = await self._post("/platform/auth/status")
        self.assertEqual(status_before.status_code, 200, status_before.text)
        self.assertFalse(status_before.json()["has_users"])

        token, user = await self._register("alice")
        self.assertEqual(user["role"], "admin")

        status_after = await self._post("/platform/auth/status")
        self.assertEqual(status_after.status_code, 200, status_after.text)
        self.assertTrue(status_after.json()["has_users"])

        login = await self._post(
            "/platform/auth/login",
            json_body={"username": "alice", "password": "pass1234"},
        )
        self.assertEqual(login.status_code, 200, login.text)
        self.assertEqual(login.json()["user"]["id"], user["id"])
        self.assertTrue(login.json()["token"])

        me = await self._post("/platform/users/me", token=token)
        self.assertEqual(me.status_code, 200, me.text)
        self.assertEqual(me.json()["user"]["username"], "alice")

    async def test_protected_spaces_follow_friendship_access(self) -> None:
        alice_token, alice = await self._register("alice")
        bob_token, bob = await self._register("bob")

        space = await self._create_space(alice_token, title="Shared Space", visibility="protected")

        before = await self._post("/platform/spaces/list-accessible", token=bob_token)
        self.assertEqual(before.status_code, 200, before.text)
        self.assertEqual(before.json()["spaces"], [])

        denied = await self._post(f"/platform/spaces/{space['id']}", token=bob_token)
        self.assertEqual(denied.status_code, 403, denied.text)

        request_resp = await self._post(
            "/platform/friends/request",
            token=alice_token,
            json_body={"target_user_id": bob["id"]},
        )
        self.assertEqual(request_resp.status_code, 200, request_resp.text)

        accept_resp = await self._post(
            "/platform/friends/accept",
            token=bob_token,
            json_body={"requester_user_id": alice["id"]},
        )
        self.assertEqual(accept_resp.status_code, 200, accept_resp.text)

        after = await self._post("/platform/spaces/list-accessible", token=bob_token)
        self.assertEqual(after.status_code, 200, after.text)
        space_ids = [item["id"] for item in after.json()["spaces"]]
        self.assertIn(space["id"], space_ids)

        allowed = await self._post(f"/platform/spaces/{space['id']}", token=bob_token)
        self.assertEqual(allowed.status_code, 200, allowed.text)
        self.assertEqual(allowed.json()["space"]["id"], space["id"])

    async def test_secrets_are_user_scoped_and_resolvable(self) -> None:
        alice_token, alice = await self._register("alice")
        bob_token, _bob = await self._register("bob")
        space = await self._create_space(alice_token, title="Secrets Space")

        set_user_secret = await self._post(
            "/platform/secrets/set",
            token=alice_token,
            json_body={"name": "API_KEY", "value": "alpha"},
        )
        self.assertEqual(set_user_secret.status_code, 200, set_user_secret.text)

        set_space_secret = await self._post(
            "/platform/secrets/set",
            token=alice_token,
            json_body={"name": "SPACE_TOKEN", "value": "beta", "space_id": space["id"]},
        )
        self.assertEqual(set_space_secret.status_code, 200, set_space_secret.text)

        user_resolve = await self._post(
            "/platform/secrets/resolve",
            token=alice_token,
            json_body={"names": ["API_KEY"]},
        )
        self.assertEqual(user_resolve.status_code, 200, user_resolve.text)
        self.assertEqual(user_resolve.json()["values"]["API_KEY"], "alpha")

        space_resolve = await self._post(
            "/platform/secrets/resolve",
            token=alice_token,
            json_body={"names": ["SPACE_TOKEN"], "space_id": space["id"]},
        )
        self.assertEqual(space_resolve.status_code, 200, space_resolve.text)
        self.assertEqual(space_resolve.json()["values"]["SPACE_TOKEN"], "beta")

        forbidden = await self._post(
            "/platform/secrets/list",
            token=bob_token,
            json_body={"owner_user_id": alice["id"]},
        )
        self.assertEqual(forbidden.status_code, 403, forbidden.text)

    async def test_execution_contract_can_start_and_complete_workflow(self) -> None:
        alice_token, _alice = await self._register("alice")
        space = await self._create_space(alice_token, title="Execution Space")
        await self._write_workflow_asset(alice_token, space["id"])

        start = await self._post(
            "/platform/executions/start",
            token=alice_token,
            json_body={"space_id": space["id"], "asset_path": "workflow.json"},
        )
        self.assertEqual(start.status_code, 200, start.text)
        execution = start.json()["execution"]
        execution_id = execution["execution_id"]
        self.assertEqual(execution["space_id"], space["id"])

        final_status = execution["status"]
        for _ in range(60):
            record_resp = await self._post(
                f"/platform/executions/{execution_id}",
                token=alice_token,
            )
            self.assertEqual(record_resp.status_code, 200, record_resp.text)
            final_status = record_resp.json()["execution"]["status"]
            if final_status in {"completed", "failed", "cancelled"}:
                break
            await asyncio.sleep(0.2)

        self.assertEqual(final_status, "completed")

        listing = await self._post(
            "/platform/executions/list",
            token=alice_token,
            json_body={"space_id": space["id"]},
        )
        self.assertEqual(listing.status_code, 200, listing.text)
        execution_ids = [item["execution_id"] for item in listing.json()["executions"]]
        self.assertIn(execution_id, execution_ids)
