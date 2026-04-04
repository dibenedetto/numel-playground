from __future__ import annotations

import importlib
import json
import os
import shutil
import sys
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace


PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = PROJECT_ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(1, str(PROJECT_ROOT))


class ProdBackendAppBootTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._root = PROJECT_ROOT / "storage" / "_test_runs" / f"prod_app_{uuid.uuid4().hex[:8]}"
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
                            "timeout_seconds": 1.0,
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
                            "require_available_on_startup": True,
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

        self._stack_module = importlib.import_module("platform_prod.stack")
        self._runtime_module = importlib.import_module("platform_prod.docker_runtime")
        self._original_identity_validate = self._stack_module.DjangoIdentityProvider.startup_validate
        self._original_runtime_validate = self._runtime_module.DockerApiRuntimeProvider.startup_validate

    async def asyncTearDown(self) -> None:
        self._stack_module.DjangoIdentityProvider.startup_validate = self._original_identity_validate
        self._runtime_module.DockerApiRuntimeProvider.startup_validate = self._original_runtime_validate
        for key, value in self._env_backup.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

        runtime_settings = importlib.import_module("runtime_settings")
        runtime_settings.get_runtime_settings.cache_clear()
        shutil.rmtree(self._root, ignore_errors=True)

    async def test_build_app_accepts_prod_backend_when_startup_validation_passes(self) -> None:
        async def _fake_identity_validate(self):
            return {"checked": True, "provider": "django", "service_status": {"enabled": True}}

        async def _fake_runtime_validate(self):
            return {"checked": True, "provider": "docker_api", "service_status": {"healthy": True}}

        self._stack_module.DjangoIdentityProvider.startup_validate = _fake_identity_validate
        self._runtime_module.DockerApiRuntimeProvider.startup_validate = _fake_runtime_validate
        if "app" in sys.modules:
            del sys.modules["app"]
        app_module = importlib.import_module("app")
        app = await app_module.build_app(SimpleNamespace(port=18800, seed=0, tunnel=False))
        try:
            self.assertEqual(app.state.platform_backend, "prod")
            self.assertTrue(app.state.platform_startup_status["identity"]["checked"])
            self.assertTrue(app.state.platform_startup_status["runtime"]["checked"])
        finally:
            await app.state.shutdown_runtime()

    async def test_build_app_fails_fast_when_prod_startup_validation_fails(self) -> None:
        async def _failing_validate(self):
            raise RuntimeError("prod runtime unavailable")

        self._stack_module.DjangoIdentityProvider.startup_validate = _failing_validate
        self._runtime_module.DockerApiRuntimeProvider.startup_validate = _failing_validate
        if "app" in sys.modules:
            del sys.modules["app"]
        app_module = importlib.import_module("app")
        with self.assertRaises(RuntimeError) as ctx:
            await app_module.build_app(SimpleNamespace(port=18801, seed=0, tunnel=False))
        self.assertIn("prod runtime unavailable", str(ctx.exception))
