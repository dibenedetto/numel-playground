from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import unittest
import uuid
import zipfile
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = PROJECT_ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from platform_prod.backup import build_backup_plan, create_backup_archive, restore_backup_archive
from runtime_settings import get_runtime_settings


class PlatformProdBackupTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = PROJECT_ROOT / "storage" / "_test_runs" / f"backup_prod_{uuid.uuid4().hex[:8]}"
        self.root.mkdir(parents=True, exist_ok=True)
        self._env_backup = {"NUMEL_DATA_ROOT": os.environ.get("NUMEL_DATA_ROOT")}
        os.environ["NUMEL_DATA_ROOT"] = str((self.root / "runtime").resolve())
        get_runtime_settings.cache_clear()
        self.settings = get_runtime_settings()
        self.settings.ensure_directories()
        self.config_path = self.root / "platform_backend.prod.json"
        self.spaces_root = self.root / "spaces"
        self.artifacts_root = self.root / "artifacts"
        self.database_url = "postgresql://user:pass@db:5432/numel"
        self.config_path.write_text(
            json.dumps(
                {
                    "backend": "prod",
                    "prod": {
                        "database": {"url": self.database_url},
                        "git": {"repos_root": str(self.spaces_root)},
                        "artifacts": {"root_path": str(self.artifacts_root)},
                    },
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        (self.spaces_root / "space_demo").mkdir(parents=True, exist_ok=True)
        (self.spaces_root / "space_demo" / "workflow.json").write_text('{"name":"prod"}', encoding="utf-8")
        (self.artifacts_root / "executions" / "exec1").mkdir(parents=True, exist_ok=True)
        (self.artifacts_root / "executions" / "exec1" / "result.txt").write_text("artifact", encoding="utf-8")
        (self.settings.workspace_storage_dir / "workspace.txt").write_text("workspace", encoding="utf-8")
        self.settings.process_credentials_path.write_text('{"API_KEY":"abc"}', encoding="utf-8")
        self.settings.channel_users_path.write_text("{}", encoding="utf-8")
        self.settings.channels_config_path.write_text("{}", encoding="utf-8")
        self.settings.agent_tasks_path.write_text("[]", encoding="utf-8")
        self.settings.published_apps_path.write_text("[]", encoding="utf-8")
        self._calls: list[list[str]] = []

    def tearDown(self) -> None:
        for key, value in self._env_backup.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        get_runtime_settings.cache_clear()
        shutil.rmtree(self.root, ignore_errors=True)

    def _fake_run(self, args, check=True):
        self._calls.append(list(args))
        command = args[0]
        if command == "pg_dump":
            output_arg = next(item for item in args if item.startswith("--file="))
            dump_path = Path(output_arg.split("=", 1)[1])
            dump_path.write_text("-- prod dump --", encoding="utf-8")
        return subprocess.CompletedProcess(args, 0)

    def test_prod_backup_archive_round_trip(self) -> None:
        plan = build_backup_plan(str(self.config_path))
        self.assertEqual(plan["backend"], "prod")
        self.assertIn("postgresql://user@db:5432/numel", plan["database_url"])
        labels = {item["label"] for item in plan["included"]}
        self.assertIn("database", labels)
        self.assertIn("spaces", labels)
        self.assertIn("artifacts", labels)

        archive_path = self.root / "backup-prod.zip"
        with patch("platform_prod.backup.subprocess.run", side_effect=self._fake_run):
            result = create_backup_archive(str(self.config_path), str(archive_path))
        self.assertEqual(result["backend"], "prod")
        self.assertTrue(archive_path.exists())
        self.assertTrue(any(call[0] == "pg_dump" for call in self._calls))

        with zipfile.ZipFile(archive_path, "r") as archive:
            names = set(archive.namelist())
        self.assertIn("manifest.json", names)
        self.assertIn("config/platform_backend.json", names)
        self.assertIn("data/postgresql.sql", names)
        self.assertIn("data/spaces/space_demo/workflow.json", names)

        shutil.rmtree(self.spaces_root, ignore_errors=True)
        shutil.rmtree(self.artifacts_root, ignore_errors=True)
        shutil.rmtree(self.settings.workspace_storage_dir, ignore_errors=True)
        for file_path in (
            self.settings.process_credentials_path,
            self.settings.channel_users_path,
            self.settings.channels_config_path,
            self.settings.agent_tasks_path,
            self.settings.published_apps_path,
        ):
            if file_path.exists():
                file_path.unlink()

        with patch("platform_prod.backup.subprocess.run", side_effect=self._fake_run):
            restore = restore_backup_archive(str(archive_path), config_path=str(self.config_path), overwrite=True)
        self.assertEqual(restore["backend"], "prod")
        self.assertIn("database", restore["restored_labels"])
        self.assertTrue(any(call[0] == "psql" for call in self._calls))
        self.assertEqual((self.spaces_root / "space_demo" / "workflow.json").read_text(encoding="utf-8"), '{"name":"prod"}')
        self.assertEqual((self.artifacts_root / "executions" / "exec1" / "result.txt").read_text(encoding="utf-8"), "artifact")
        self.assertEqual(self.settings.process_credentials_path.read_text(encoding="utf-8"), '{"API_KEY":"abc"}')

    def test_prod_restore_requires_overwrite(self) -> None:
        archive_path = self.root / "backup-prod.zip"
        with patch("platform_prod.backup.subprocess.run", side_effect=self._fake_run):
            create_backup_archive(str(self.config_path), str(archive_path))
        with self.assertRaises(FileExistsError):
            with patch("platform_prod.backup.subprocess.run", side_effect=self._fake_run):
                restore_backup_archive(str(archive_path), config_path=str(self.config_path), overwrite=False)
