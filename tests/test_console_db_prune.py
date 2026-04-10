from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = PROJECT_ROOT / "app"
if str(APP_DIR) not in sys.path:
	sys.path.insert(0, str(APP_DIR))
if str(PROJECT_ROOT) not in sys.path:
	sys.path.insert(1, str(PROJECT_ROOT))


from console import _prepare_agno_memory_db_path


class ConsoleDbPruneTests(unittest.TestCase):
	def _temp_db_path(self) -> str:
		fd, path = tempfile.mkstemp(prefix="numel-agno-db-", suffix=".db")
		os.close(fd)
		self.addCleanup(lambda: os.path.exists(path) and os.remove(path))
		return path

	def test_prunes_old_agno_approvals_schema(self):
		path = self._temp_db_path()
		conn = sqlite3.connect(path)
		cur = conn.cursor()
		cur.execute(
			"""
			CREATE TABLE agno_approvals (
				id TEXT PRIMARY KEY,
				run_id TEXT NOT NULL,
				session_id TEXT NOT NULL,
				status TEXT NOT NULL
			)
			"""
		)
		conn.commit()
		conn.close()

		resolved = _prepare_agno_memory_db_path(path)

		self.assertEqual(resolved, path)
		self.assertFalse(os.path.exists(path))

	def test_keeps_current_agno_approvals_schema(self):
		path = self._temp_db_path()
		conn = sqlite3.connect(path)
		cur = conn.cursor()
		cur.execute(
			"""
			CREATE TABLE agno_approvals (
				id TEXT PRIMARY KEY,
				run_id TEXT NOT NULL,
				session_id TEXT NOT NULL,
				status TEXT NOT NULL,
				run_status TEXT
			)
			"""
		)
		conn.commit()
		conn.close()

		resolved = _prepare_agno_memory_db_path(path)

		self.assertEqual(resolved, path)
		self.assertTrue(os.path.exists(path))


if __name__ == "__main__":
	unittest.main()
