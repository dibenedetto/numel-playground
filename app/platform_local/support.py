"""Shared helpers for concrete platform scaffolds."""

from __future__ import annotations

import sqlite3
from pathlib import Path


class ScaffoldComponent:
    """Mixin for concrete implementation stubs that are not wired yet."""

    def _not_ready(self, action: str):
        raise NotImplementedError(
            f"{self.__class__.__name__} is a scaffold for Numel's future "
            f"database+git platform and does not implement '{action}' yet."
        )


def resolve_sqlite_path(url: str) -> Path:
    """Resolve a sqlite:/// URL to an absolute filesystem path."""
    if not url.startswith("sqlite:///"):
        raise ValueError("Only sqlite:/// URLs are supported by the local platform implementation")
    return Path(url[len("sqlite:///"):]).resolve()


def connect_sqlite(url: str) -> sqlite3.Connection:
    """Open a sqlite connection with row access and foreign keys enabled."""
    db_path = resolve_sqlite_path(url)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    try:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
    except sqlite3.DatabaseError:
        pass
    return conn
