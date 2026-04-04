from __future__ import annotations

import importlib
import shutil
import sys
import unittest
import uuid
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Request


PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = PROJECT_ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(1, str(PROJECT_ROOT))


from platform_local import DatabaseConfig, SecretsConfig
from platform_prod.secrets import ProdDbSecretsProvider, VaultKvSecretsProvider, build_prod_secrets_provider


def _build_mock_vault() -> FastAPI:
    app = FastAPI()
    storage: dict[str, dict] = {}

    def _check_token(request: Request) -> None:
        if request.headers.get("x-vault-token", "") != "dev-token":
            raise HTTPException(status_code=403, detail="missing token")

    @app.get("/v1/sys/health")
    async def sys_health(request: Request):
        _check_token(request)
        return {"initialized": True, "sealed": False, "standby": False}

    @app.get("/v1/secret/metadata/{secret_path:path}")
    async def list_metadata(secret_path: str, request: Request):
        _check_token(request)
        if request.query_params.get("list") != "true":
            raise HTTPException(status_code=400, detail="list=true required")
        prefix = secret_path.strip("/")
        keys = sorted(
            {
                key[len(prefix) + 1 :].split("/", 1)[0]
                for key in storage
                if key.startswith(prefix + "/") and key[len(prefix) + 1 :]
            }
        )
        if not keys:
            raise HTTPException(status_code=404, detail="no keys")
        return {"data": {"keys": keys}}

    @app.get("/v1/secret/data/{secret_path:path}")
    async def get_secret(secret_path: str, request: Request):
        _check_token(request)
        payload = storage.get(secret_path)
        if payload is None:
            raise HTTPException(status_code=404, detail="not found")
        return {"data": {"data": payload}}

    @app.post("/v1/secret/data/{secret_path:path}")
    async def set_secret(secret_path: str, request: Request):
        _check_token(request)
        body = await request.json()
        payload = body.get("data") if isinstance(body, dict) else None
        if not isinstance(payload, dict):
            raise HTTPException(status_code=400, detail="invalid payload")
        storage[secret_path] = payload
        return {"data": {"written": True}}

    @app.delete("/v1/secret/metadata/{secret_path:path}")
    async def delete_secret(secret_path: str, request: Request):
        _check_token(request)
        existed = storage.pop(secret_path, None) is not None
        if not existed:
            raise HTTPException(status_code=404, detail="not found")
        return {"data": {"deleted": True}}

    return app


class ProdSecretsProviderTests(unittest.IsolatedAsyncioTestCase):
    async def test_build_provider_selects_database_backend(self) -> None:
        root = PROJECT_ROOT / "storage" / "_test_runs" / f"prod_secrets_db_{uuid.uuid4().hex[:8]}"
        root.mkdir(parents=True, exist_ok=True)
        try:
            provider = build_prod_secrets_provider(
                SecretsConfig(backend="database"),
                db_config=DatabaseConfig(url=f"sqlite:///{(root / 'platform.db').as_posix()}"),
            )
            self.assertIsInstance(provider, ProdDbSecretsProvider)
            status = await provider.startup_validate()
            self.assertIn("provider", status)
        finally:
            close = getattr(provider, "aclose", None)
            if callable(close):
                result = close()
                if hasattr(result, "__await__"):
                    await result
            shutil.rmtree(root, ignore_errors=True)

    async def test_vault_provider_supports_crud_and_resolution(self) -> None:
        vault_app = _build_mock_vault()
        provider = VaultKvSecretsProvider(
            SecretsConfig(
                backend="vault",
                vault_url="http://vault.test",
                token="dev-token",
                kv_mount="secret",
                key_prefix="numel",
                require_available_on_startup=True,
            ),
            transport=httpx.ASGITransport(app=vault_app),
        )
        try:
            status = await provider.startup_validate()
            self.assertTrue(status["checked"])
            self.assertEqual(status["provider"], "vault")

            user_cred = await provider.set_credential("user_1", "API_KEY", "user-secret")
            space_cred = await provider.set_credential("user_1", "SPACE_TOKEN", "space-secret", space_id="space_1")
            self.assertEqual(user_cred.name, "API_KEY")
            self.assertEqual(space_cred.space_id, "space_1")

            loaded = await provider.get_credential("user_1", "API_KEY")
            self.assertIsNotNone(loaded)
            self.assertTrue(loaded.value_present)

            user_records = await provider.list_credentials("user_1")
            self.assertEqual([item.name for item in user_records], ["API_KEY"])
            space_records = await provider.list_credentials("user_1", space_id="space_1")
            self.assertEqual([item.name for item in space_records], ["SPACE_TOKEN"])

            resolved_user = await provider.resolve_credentials("user_1")
            resolved_space = await provider.resolve_credentials("user_1", space_id="space_1")
            self.assertEqual(resolved_user, {"API_KEY": "user-secret"})
            self.assertEqual(resolved_space, {"SPACE_TOKEN": "space-secret"})

            deleted = await provider.delete_credential("user_1", "API_KEY")
            self.assertTrue(deleted)
            self.assertIsNone(await provider.get_credential("user_1", "API_KEY"))
        finally:
            await provider.aclose()
