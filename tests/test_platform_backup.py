from __future__ import annotations

import json
import os
import shutil
import sys
import unittest
import uuid
import zipfile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = PROJECT_ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from platform_backup import build_backup_plan, create_backup_archive, restore_backup_archive
from runtime_settings import get_runtime_settings


class PlatformBackupTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = PROJECT_ROOT / "storage" / "_test_runs" / f"backup_local_{uuid.uuid4().hex[:8]}"
        self.root.mkdir(parents=True, exist_ok=True)
        self._env_backup = {"NUMEL_DATA_ROOT": os.environ.get("NUMEL_DATA_ROOT")}
        os.environ["NUMEL_DATA_ROOT"] = str((self.root / "runtime").resolve())
        get_runtime_settings.cache_clear()
        self.settings = get_runtime_settings()
        self.settings.ensure_directories()
        self.config_path = self.root / "platform_backend.local.json"
        self.db_path = self.root / "platform.db"
        self.spaces_root = self.root / "spaces"
        self.artifacts_root = self.root / "artifacts"
        self.config_path.write_text(
            json.dumps(
                {
                    "backend": "local",
                    "local": {
                        "database": {"url": f"sqlite:///{self.db_path.as_posix()}"},
                        "git": {"repos_root": str(self.spaces_root)},
                        "artifacts": {"root_path": str(self.artifacts_root)},
                    },
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        self.db_path.write_text('local-backup-db', encoding='utf-8')
        (self.spaces_root / "space_demo").mkdir(parents=True, exist_ok=True)
        (self.spaces_root / "space_demo" / "workflow.json").write_text('{"name":"demo"}', encoding="utf-8")
        (self.artifacts_root / "executions" / "exec1").mkdir(parents=True, exist_ok=True)
        (self.artifacts_root / "executions" / "exec1" / "result.txt").write_text("artifact", encoding="utf-8")
        (self.settings.workspace_storage_dir / "workspace.txt").write_text("workspace", encoding="utf-8")
        (self.settings.memory_storage_dir / "memory.txt").write_text("memory", encoding="utf-8")
        (self.settings.user_memory_dir / "user-memory.txt").write_text("user-memory", encoding="utf-8")
        (self.settings.gallery_dir / "gallery.txt").write_text("gallery", encoding="utf-8")
        (self.settings.user_skills_dir / "skill.md").write_text("# skill", encoding="utf-8")
        (self.settings.published_apps_dir / "user_1" / "demo").mkdir(parents=True, exist_ok=True)
        (self.settings.published_apps_dir / "user_1" / "demo" / "index.html").write_text("<html></html>", encoding="utf-8")
        self.settings.process_credentials_path.write_text('{"API_KEY":"abc"}', encoding="utf-8")
        self.settings.channel_users_path.write_text("{}", encoding="utf-8")
        self.settings.channels_config_path.write_text("{}", encoding="utf-8")
        self.settings.agent_tasks_path.write_text("[]", encoding="utf-8")
        self.settings.published_apps_path.write_text("[]", encoding="utf-8")

    def tearDown(self) -> None:
        for key, value in self._env_backup.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        get_runtime_settings.cache_clear()
        shutil.rmtree(self.root, ignore_errors=True)

    def test_local_backup_archive_round_trip(self) -> None:
        plan = build_backup_plan(str(self.config_path))
        self.assertEqual(plan["backend"], "local")
        labels = {item["label"] for item in plan["included"]}
        self.assertIn("database", labels)
        self.assertIn("spaces", labels)
        self.assertIn("artifacts", labels)
        self.assertIn("credentials_file", labels)

        archive_path = self.root / "backup-local.zip"
        result = create_backup_archive(str(self.config_path), str(archive_path))
        self.assertEqual(result["backend"], "local")
        self.assertTrue(archive_path.exists())

        with zipfile.ZipFile(archive_path, "r") as archive:
            names = set(archive.namelist())
        self.assertIn("manifest.json", names)
        self.assertIn("config/platform_backend.json", names)
        self.assertIn("data/platform.db", names)
        self.assertIn("data/spaces/space_demo/workflow.json", names)
        self.assertIn("data/runtime/published_apps/user_1/demo/index.html", names)

        shutil.rmtree(self.spaces_root, ignore_errors=True)
        shutil.rmtree(self.artifacts_root, ignore_errors=True)
        shutil.rmtree(self.settings.workspace_storage_dir, ignore_errors=True)
        shutil.rmtree(self.settings.memory_storage_dir, ignore_errors=True)
        shutil.rmtree(self.settings.user_memory_dir, ignore_errors=True)
        shutil.rmtree(self.settings.gallery_dir, ignore_errors=True)
        shutil.rmtree(self.settings.user_skills_dir, ignore_errors=True)
        shutil.rmtree(self.settings.published_apps_dir, ignore_errors=True)
        if self.db_path.exists():
            self.db_path.unlink()
        for file_path in (
            self.settings.process_credentials_path,
            self.settings.channel_users_path,
            self.settings.channels_config_path,
            self.settings.agent_tasks_path,
            self.settings.published_apps_path,
        ):
            if file_path.exists():
                file_path.unlink()

        restore = restore_backup_archive(str(archive_path), config_path=str(self.config_path), overwrite=True)
        self.assertEqual(restore["backend"], "local")
        self.assertIn("database", restore["restored_labels"])
        self.assertTrue(self.db_path.exists())
        self.assertEqual((self.spaces_root / "space_demo" / "workflow.json").read_text(encoding="utf-8"), '{"name":"demo"}')
        self.assertEqual((self.artifacts_root / "executions" / "exec1" / "result.txt").read_text(encoding="utf-8"), "artifact")
        self.assertEqual((self.settings.published_apps_dir / "user_1" / "demo" / "index.html").read_text(encoding="utf-8"), "<html></html>")
        self.assertEqual(self.settings.process_credentials_path.read_text(encoding="utf-8"), '{"API_KEY":"abc"}')

    def test_local_backup_rejects_prod_backend(self) -> None:
        prod_config = self.root / "platform_backend.prod.json"
        prod_config.write_text(
            json.dumps({"backend": "prod", "prod": {"database": {"url": "postgresql://user:pass@db:5432/numel"}}}),
            encoding="utf-8",
        )
        with self.assertRaises(ValueError):
            build_backup_plan(str(prod_config))
