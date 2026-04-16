import os
import time

from typing import Optional

from runtime_settings import get_runtime_settings
from utils import log_print


_SETTINGS = get_runtime_settings()
_USER_MEMORY_DIR = str(_SETTINGS.user_memory_dir)


class UserMemoryDB:
	"""Resolve assistant identities to backend-managed SQLite memory files."""

	def __init__(self, storage_dir: str = _USER_MEMORY_DIR):
		self._dir = storage_dir
		os.makedirs(storage_dir, exist_ok=True)

	def get_db_path(self, user_id: str, is_guest: bool = False) -> str:
		"""Return the SQLite db path for a given assistant identity."""
		if is_guest:
			safe = self._safe_name(user_id)
			return os.path.join(self._dir, f"guest_{safe}.db")
		safe = self._safe_name(user_id)
		if safe.startswith("anon_"):
			return os.path.join(self._dir, f"{safe}.db")
		return os.path.join(self._dir, f"user_{safe}.db")

	def cleanup_guest(self, session_id: str):
		"""Delete a specific guest db file."""
		path = self.get_db_path(session_id, is_guest=True)
		self._remove(path)

	def cleanup_expired_guests(self, max_age_s: float = 86400):
		"""Remove ``guest_*.db`` files older than *max_age_s* seconds."""
		now = time.time()
		for fname in os.listdir(self._dir):
			if not fname.startswith("guest_") or not fname.endswith(".db"):
				continue
			fpath = os.path.join(self._dir, fname)
			try:
				age = now - os.path.getmtime(fpath)
				if age > max_age_s:
					self._remove(fpath)
					log_print(f"UserMemoryDB: cleaned up expired guest db {fname}")
			except OSError:
				pass

	@staticmethod
	def _safe_name(raw: str) -> str:
		"""Sanitize an identifier for use as a filename component."""
		return "".join(c if (c.isalnum() or c in "-_") else "_" for c in raw)

	@staticmethod
	def _remove(path: str):
		"""Remove a db file and its WAL/SHM companions."""
		for suffix in ("", "-wal", "-shm"):
			try:
				os.remove(path + suffix)
			except OSError:
				pass
