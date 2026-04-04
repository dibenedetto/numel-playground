from __future__ import annotations

import sys
import unittest
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Request


PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = PROJECT_ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(1, str(PROJECT_ROOT))


from platform_prod import DjangoIdentityConfig, DjangoIdentityProvider


def _build_mock_identity_service() -> FastAPI:
    app = FastAPI()

    users_by_id: dict[str, dict] = {}
    user_ids_by_name: dict[str, str] = {}
    active_tokens: dict[str, str] = {}
    passwords: dict[str, str] = {}

    def _bundle(user_id: str) -> dict:
        user = users_by_id[user_id]
        return {
            "user": user,
            "profile": {
                "user_id": user_id,
                "display_name": user["username"],
                "bio": "",
                "avatar_url": "",
                "metadata": {},
            },
            "quota": {
                "user_id": user_id,
                "cpu_seconds_remaining": 36000.0,
                "max_concurrent_runs": 5,
                "storage_bytes_remaining": 1073741824,
                "max_loop_hours": 24.0,
                "gpu_hours_remaining": 0.0,
                "max_spaces": 50,
                "max_assets_per_space": 10000,
            },
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
        users = list(users_by_id.values())[:limit]
        return {"users": users, "count": len(users)}

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
        bundle = _bundle(user_id)
        profile = bundle["profile"]
        for key in ("display_name", "bio", "avatar_url", "metadata"):
            if key in body:
                profile[key] = body[key]
        return {"profile": profile}

    @app.post("/api/platform/users/{user_id}/quota")
    async def users_quota(user_id: str, request: Request):
        if user_id not in users_by_id:
            raise HTTPException(status_code=404, detail="Not found")
        body = await request.json()
        bundle = _bundle(user_id)
        quota = bundle["quota"]
        quota.update(body)
        return {"quota": quota}

    return app


class DjangoIdentityProviderTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._service = _build_mock_identity_service()
        self._provider = DjangoIdentityProvider(
            DjangoIdentityConfig(
                base_url="http://django.test",
                identity_prefix="/api/platform",
                healthcheck_path="/auth/status",
                verify_tls=False,
            ),
            transport=httpx.ASGITransport(app=self._service),
        )

    async def asyncTearDown(self) -> None:
        await self._provider.aclose()

    async def test_crud_auth_and_password_change_contract(self) -> None:
        status = await self._provider.startup_validate()
        self.assertTrue(status["checked"])
        self.assertTrue(status["service_status"]["enabled"])

        user = await self._provider.create_user("alice", "alice@local", "pass1234")
        self.assertEqual(user.username, "alice")
        self.assertEqual(user.role.value, "admin")

        token = await self._provider.login("alice", "pass1234")
        self.assertTrue(token)

        authenticated = await self._provider.authenticate(token)
        self.assertIsNotNone(authenticated)
        self.assertEqual(authenticated.username, "alice")

        by_name = await self._provider.get_user_by_username("alice")
        self.assertIsNotNone(by_name)
        self.assertEqual(by_name.id, user.id)

        listed = await self._provider.list_users()
        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0].id, user.id)

        updated = await self._provider.update_user(user.id, email="alice+1@local")
        self.assertEqual(updated.email, "alice+1@local")

        profile = await self._provider.update_profile(user.id, bio="hello")
        self.assertEqual(profile.bio, "hello")

        quota = await self._provider.update_quota(user.id, max_spaces=99)
        self.assertEqual(quota.max_spaces, 99)

        changed = await self._provider.change_password(user.id, "pass1234", "pass5678")
        self.assertTrue(changed)

        old_login = await self._provider.login("alice", "pass1234")
        self.assertIsNone(old_login)
        new_login = await self._provider.login("alice", "pass5678")
        self.assertTrue(new_login)

        logged_out = await self._provider.logout(new_login)
        self.assertTrue(logged_out)

        deleted = await self._provider.delete_user(user.id)
        self.assertTrue(deleted)

    async def test_startup_validation_fails_clearly_when_service_is_unavailable(self) -> None:
        def _handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/auth/status"):
                return httpx.Response(503, text="service unavailable")
            return httpx.Response(404, text="not found")

        provider = DjangoIdentityProvider(
            DjangoIdentityConfig(
                base_url="http://django.test",
                identity_prefix="/api/platform",
                healthcheck_path="/auth/status",
                verify_tls=False,
            ),
            transport=httpx.MockTransport(_handler),
        )
        try:
            with self.assertRaises(RuntimeError) as ctx:
                await provider.startup_validate()
            self.assertIn("Django identity service returned 503", str(ctx.exception))
        finally:
            await provider.aclose()
