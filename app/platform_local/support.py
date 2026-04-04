"""Shared helpers for concrete platform database access."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterable, Optional

import psycopg
from psycopg.rows import dict_row


class ScaffoldComponent:
    """Mixin for concrete implementation stubs that are not wired yet."""

    def _not_ready(self, action: str):
        raise NotImplementedError(
            f"{self.__class__.__name__} is a scaffold for Numel's future "
            f"database+git platform and does not implement '{action}' yet."
        )


def normalize_database_url(url: str) -> str:
    """Normalize accepted database URLs to the forms our drivers expect."""
    raw = str(url or "").strip()
    if raw.startswith("postgres://"):
        return "postgresql://" + raw[len("postgres://"):]
    if raw.startswith("postgresql+psycopg://"):
        return "postgresql://" + raw[len("postgresql+psycopg://"):]
    return raw


def database_dialect(url: str) -> str:
    """Return the backend dialect name for a configured database URL."""
    normalized = normalize_database_url(url)
    if normalized.startswith("sqlite:///"):
        return "sqlite"
    if normalized.startswith("postgresql://"):
        return "postgresql"
    raise ValueError(
        "Unsupported database URL. Expected sqlite:/// or postgresql:// "
        "(optionally postgresql+psycopg://)."
    )


def is_sqlite_url(url: str) -> bool:
    return database_dialect(url) == "sqlite"


def resolve_sqlite_path(url: str) -> Path:
    """Resolve a sqlite:/// URL to an absolute filesystem path."""
    normalized = normalize_database_url(url)
    if not normalized.startswith("sqlite:///"):
        raise ValueError("Only sqlite:/// URLs can be resolved to a local filesystem path")
    return Path(normalized[len("sqlite:///"):]).resolve()


def resolve_database_path(url: str) -> Optional[Path]:
    """Return the local database path when the backend is SQLite, otherwise None."""
    return resolve_sqlite_path(url) if is_sqlite_url(url) else None


def _split_sql_script(script: str) -> list[str]:
    statements: list[str] = []
    buffer: list[str] = []
    in_single = False
    in_double = False
    escape = False

    for char in script:
        buffer.append(char)
        if escape:
            escape = False
            continue
        if char == "\\":
            escape = True
            continue
        if char == "'" and not in_double:
            in_single = not in_single
            continue
        if char == '"' and not in_single:
            in_double = not in_double
            continue
        if char == ";" and not in_single and not in_double:
            statement = "".join(buffer).strip()
            if statement:
                statements.append(statement)
            buffer = []

    trailing = "".join(buffer).strip()
    if trailing:
        statements.append(trailing)
    return statements


def _translate_postgres_sql(sql: str) -> str:
    return sql.replace("?", "%s")


class DatabaseConnection:
    """Small compatibility wrapper over sqlite3 / psycopg connections."""

    def __init__(self, raw, dialect: str):
        self._raw = raw
        self.dialect = dialect

    def __enter__(self) -> "DatabaseConnection":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        try:
            if exc_type is None:
                self._raw.commit()
            else:
                self._raw.rollback()
        finally:
            self._raw.close()

    def _sql(self, sql: str) -> str:
        return _translate_postgres_sql(sql) if self.dialect == "postgresql" else sql

    def execute(self, sql: str, params: Iterable | None = None):
        return self._raw.execute(self._sql(sql), tuple(params or ()))

    def executemany(self, sql: str, param_sets: Iterable[Iterable]):
        if self.dialect == "postgresql":
            cursor = self._raw.cursor(row_factory=dict_row)
            cursor.executemany(self._sql(sql), [tuple(values) for values in param_sets])
            return cursor
        return self._raw.executemany(sql, [tuple(values) for values in param_sets])

    def executescript(self, script: str) -> None:
        if self.dialect == "postgresql":
            for statement in _split_sql_script(script):
                self._raw.execute(statement)
            return
        self._raw.executescript(script)


def connect_database(url: str) -> DatabaseConnection:
    """Open a database connection suitable for SQLite or PostgreSQL."""
    normalized = normalize_database_url(url)
    dialect = database_dialect(normalized)
    if dialect == "sqlite":
        db_path = resolve_sqlite_path(normalized)
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
        return DatabaseConnection(conn, dialect="sqlite")

    conn = psycopg.connect(normalized, row_factory=dict_row)
    return DatabaseConnection(conn, dialect="postgresql")


def connect_sqlite(url: str) -> sqlite3.Connection:
    """Backward-compatible helper for the SQLite-only local identity path."""
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
