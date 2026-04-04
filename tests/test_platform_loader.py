from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest
import uuid
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = PROJECT_ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from platform_loader import load_platform_backend_config


class PlatformLoaderTests(unittest.TestCase):
    def setUp(self) -> None:
        self._root = PROJECT_ROOT / "storage" / "_test_runs" / f"loader_{uuid.uuid4().hex[:8]}"
        self._root.mkdir(parents=True, exist_ok=True)
        self._config_path = PROJECT_ROOT / f"_tmp_platform_loader_{uuid.uuid4().hex[:8]}.json"
        self._previous_env = {
            "NUMEL_TEST_DB_URL": os.environ.get("NUMEL_TEST_DB_URL"),
            "NUMEL_TEST_IDENTITY_URL": os.environ.get("NUMEL_TEST_IDENTITY_URL"),
            "NUMEL_TEST_DATA_ROOT": os.environ.get("NUMEL_TEST_DATA_ROOT"),
        }
        os.environ["NUMEL_TEST_DB_URL"] = "postgresql+psycopg://user:pass@db:5432/numel"
        os.environ["NUMEL_TEST_IDENTITY_URL"] = "http://identity:8000"
        os.environ["NUMEL_TEST_DATA_ROOT"] = str((self._root / "data").resolve())

    def tearDown(self) -> None:
        for key, value in self._previous_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        shutil.rmtree(self._root, ignore_errors=True)
        try:
            self._config_path.unlink(missing_ok=True)
        except TypeError:
            if self._config_path.exists():
                self._config_path.unlink()

    def test_loader_expands_environment_values_for_prod_config(self) -> None:
        self._config_path.write_text(
            json.dumps(
                {
                    "backend": "prod",
                    "prod": {
                        "database": {"url": "${NUMEL_TEST_DB_URL}"},
                        "identity": {"base_url": "${NUMEL_TEST_IDENTITY_URL}"},
                        "git": {"repos_root": "${NUMEL_TEST_DATA_ROOT}/spaces"},
                        "artifacts": {"root_path": "${NUMEL_TEST_DATA_ROOT}/artifacts"},
                    },
                }
            ),
            encoding="utf-8",
        )

        config = load_platform_backend_config(str(self._config_path))

        self.assertEqual(config["backend"], "prod")
        self.assertEqual(
            config["prod"]["database"]["url"],
            "postgresql+psycopg://user:pass@db:5432/numel",
        )
        self.assertEqual(config["prod"]["identity"]["base_url"], "http://identity:8000")
        self.assertEqual(
            config["prod"]["git"]["repos_root"],
            str((self._root / "data" / "spaces").resolve()),
        )
        self.assertEqual(
            config["prod"]["artifacts"]["root_path"],
            str((self._root / "data" / "artifacts").resolve()),
        )
