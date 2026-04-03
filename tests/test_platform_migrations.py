from __future__ import annotations

import sqlite3
import shutil
import unittest
from pathlib import Path
import sys
import uuid


PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = PROJECT_ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from platform_local.migrations import ensure_platform_schema, get_platform_schema_status
from platform_local.support import resolve_sqlite_path


class PlatformMigrationTests(unittest.TestCase):
    def test_schema_migrations_are_applied_and_idempotent(self) -> None:
        root = PROJECT_ROOT / "storage" / "_test_runs" / f"migrations_{uuid.uuid4().hex[:8]}"
        root.mkdir(parents=True, exist_ok=True)
        try:
            db_url = f"sqlite:///{(root / 'platform.db').as_posix()}"

            initial = get_platform_schema_status(db_url)
            self.assertEqual(initial.current_version, 0)
            self.assertGreaterEqual(initial.target_version, 1)
            self.assertEqual(initial.applied_versions, [])

            applied = ensure_platform_schema(db_url)
            self.assertEqual(applied.current_version, applied.target_version)
            self.assertEqual(applied.applied_now, [1])
            self.assertEqual(applied.applied_versions, [1])

            again = ensure_platform_schema(db_url)
            self.assertEqual(again.current_version, applied.current_version)
            self.assertEqual(again.applied_now, [])
            self.assertEqual(again.applied_versions, [1])

            db_path = resolve_sqlite_path(db_url)
            with sqlite3.connect(str(db_path)) as conn:
                tables = {
                    row[0]
                    for row in conn.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table'"
                    ).fetchall()
                }

            for table_name in {
                "platform_migrations",
                "users",
                "user_profiles",
                "quotas",
                "auth_tokens",
                "friendships",
                "audit_log",
                "spaces",
                "space_assets",
                "credentials",
                "executions",
            }:
                self.assertIn(table_name, tables)
        finally:
            shutil.rmtree(root, ignore_errors=True)
