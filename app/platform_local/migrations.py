"""Versioned schema migrations for Numel's database-backed platform state."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import List

from .support import connect_database, database_dialect, is_sqlite_url, resolve_sqlite_path


@dataclass(frozen=True)
class MigrationStatus:
    current_version: int
    target_version: int
    applied_versions: List[int]
    applied_now: List[int]


@dataclass(frozen=True)
class SchemaMigration:
    version: int
    name: str
    sql: str


_MIGRATIONS: List[SchemaMigration] = [
    SchemaMigration(
        version=1,
        name="initial_platform_schema",
        sql="""
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            username TEXT NOT NULL UNIQUE,
            email TEXT NOT NULL UNIQUE,
            password_salt TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 1,
            created_at REAL NOT NULL,
            metadata_json TEXT
        );

        CREATE TABLE IF NOT EXISTS user_profiles (
            user_id TEXT PRIMARY KEY,
            display_name TEXT NOT NULL DEFAULT '',
            bio TEXT NOT NULL DEFAULT '',
            avatar_url TEXT NOT NULL DEFAULT '',
            metadata_json TEXT,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS quotas (
            user_id TEXT PRIMARY KEY,
            cpu_seconds_remaining REAL NOT NULL,
            max_concurrent_runs INTEGER NOT NULL,
            storage_bytes_remaining INTEGER NOT NULL,
            max_loop_hours REAL NOT NULL,
            gpu_hours_remaining REAL NOT NULL,
            max_spaces INTEGER NOT NULL,
            max_assets_per_space INTEGER NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS auth_tokens (
            token TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            created_at REAL NOT NULL,
            expires_at REAL NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS friendships (
            requester_user_id TEXT NOT NULL,
            target_user_id TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            metadata_json TEXT,
            PRIMARY KEY(requester_user_id, target_user_id)
        );

        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL,
            actor_user_id TEXT NOT NULL DEFAULT '',
            resource TEXT NOT NULL DEFAULT '',
            action TEXT NOT NULL DEFAULT '',
            metadata_json TEXT,
            created_at REAL NOT NULL
        );

        CREATE TABLE IF NOT EXISTS spaces (
            id TEXT PRIMARY KEY,
            owner_user_id TEXT NOT NULL,
            slug TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            visibility TEXT NOT NULL,
            default_ref TEXT NOT NULL DEFAULT 'main',
            head_commit_id TEXT NOT NULL DEFAULT '',
            policy_json TEXT,
            metadata_json TEXT,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            UNIQUE(owner_user_id, slug)
        );

        CREATE TABLE IF NOT EXISTS space_assets (
            id TEXT PRIMARY KEY,
            space_id TEXT NOT NULL,
            path TEXT NOT NULL,
            kind TEXT NOT NULL,
            owner_user_id TEXT NOT NULL,
            title TEXT NOT NULL DEFAULT '',
            description TEXT NOT NULL DEFAULT '',
            visibility TEXT NOT NULL,
            versioned INTEGER NOT NULL DEFAULT 1,
            executable INTEGER NOT NULL DEFAULT 0,
            size_bytes INTEGER NOT NULL DEFAULT 0,
            content_hash TEXT NOT NULL DEFAULT '',
            latest_commit_id TEXT NOT NULL DEFAULT '',
            policy_json TEXT,
            metadata_json TEXT,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            UNIQUE(space_id, path)
        );

        CREATE TABLE IF NOT EXISTS credentials (
            id TEXT PRIMARY KEY,
            owner_user_id TEXT NOT NULL,
            name TEXT NOT NULL,
            scope TEXT NOT NULL,
            space_id TEXT NOT NULL DEFAULT '',
            secret_value TEXT NOT NULL DEFAULT '',
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            last_used_at REAL,
            metadata_json TEXT,
            UNIQUE(owner_user_id, name, scope, space_id)
        );

        CREATE TABLE IF NOT EXISTS executions (
            execution_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            space_id TEXT NOT NULL,
            asset_path TEXT NOT NULL,
            ref TEXT NOT NULL,
            status TEXT NOT NULL,
            runtime_profile_id TEXT NOT NULL DEFAULT '',
            started_at REAL NOT NULL,
            finished_at REAL,
            outputs_json TEXT,
            error TEXT,
            metadata_json TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
        CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
        CREATE INDEX IF NOT EXISTS idx_auth_tokens_user ON auth_tokens(user_id);
        CREATE INDEX IF NOT EXISTS idx_friendships_target ON friendships(target_user_id);
        CREATE INDEX IF NOT EXISTS idx_friendships_status ON friendships(status);
        CREATE INDEX IF NOT EXISTS idx_audit_category ON audit_log(category);
        CREATE INDEX IF NOT EXISTS idx_audit_actor ON audit_log(actor_user_id);
        CREATE INDEX IF NOT EXISTS idx_audit_resource ON audit_log(resource);
        CREATE INDEX IF NOT EXISTS idx_audit_created_at ON audit_log(created_at);
        CREATE INDEX IF NOT EXISTS idx_spaces_owner ON spaces(owner_user_id);
        CREATE INDEX IF NOT EXISTS idx_spaces_visibility ON spaces(visibility);
        CREATE INDEX IF NOT EXISTS idx_space_assets_space ON space_assets(space_id);
        CREATE INDEX IF NOT EXISTS idx_space_assets_path ON space_assets(space_id, path);
        CREATE INDEX IF NOT EXISTS idx_credentials_owner ON credentials(owner_user_id);
        CREATE INDEX IF NOT EXISTS idx_credentials_scope ON credentials(scope);
        CREATE INDEX IF NOT EXISTS idx_credentials_space ON credentials(space_id);
        CREATE INDEX IF NOT EXISTS idx_executions_user ON executions(user_id);
        CREATE INDEX IF NOT EXISTS idx_executions_space ON executions(space_id);
        CREATE INDEX IF NOT EXISTS idx_executions_status ON executions(status);
        """,
    ),
]


def _ensure_migrations_table(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS platform_migrations (
            version INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            applied_at DOUBLE PRECISION NOT NULL
        )
        """
    )


def _migration_sql_for_dialect(sql: str, dialect: str) -> str:
    if dialect != "postgresql":
        return sql
    return sql.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "BIGSERIAL PRIMARY KEY")


def get_platform_schema_status(db_url: str) -> MigrationStatus:
    if is_sqlite_url(db_url):
        db_path = resolve_sqlite_path(db_url)
        if not db_path.exists():
            return MigrationStatus(
                current_version=0,
                target_version=_MIGRATIONS[-1].version if _MIGRATIONS else 0,
                applied_versions=[],
                applied_now=[],
            )
    with connect_database(db_url) as conn:
        _ensure_migrations_table(conn)
        rows = conn.execute(
            "SELECT version FROM platform_migrations ORDER BY version ASC"
        ).fetchall()
    applied_versions = [int(row["version"]) for row in rows]
    current_version = applied_versions[-1] if applied_versions else 0
    return MigrationStatus(
        current_version=current_version,
        target_version=_MIGRATIONS[-1].version if _MIGRATIONS else 0,
        applied_versions=applied_versions,
        applied_now=[],
    )


def ensure_platform_schema(db_url: str) -> MigrationStatus:
    applied_now: List[int] = []
    dialect = database_dialect(db_url)
    with connect_database(db_url) as conn:
        _ensure_migrations_table(conn)
        existing_rows = conn.execute(
            "SELECT version FROM platform_migrations ORDER BY version ASC"
        ).fetchall()
        applied_versions = {int(row["version"]) for row in existing_rows}
        for migration in _MIGRATIONS:
            if migration.version in applied_versions:
                continue
            conn.executescript(_migration_sql_for_dialect(migration.sql, dialect))
            conn.execute(
                """
                INSERT INTO platform_migrations (version, name, applied_at)
                VALUES (?, ?, ?)
                """,
                (migration.version, migration.name, time.time()),
            )
            applied_now.append(migration.version)
            applied_versions.add(migration.version)
        rows = conn.execute(
            "SELECT version FROM platform_migrations ORDER BY version ASC"
        ).fetchall()
    applied_versions_list = [int(row["version"]) for row in rows]
    current_version = applied_versions_list[-1] if applied_versions_list else 0
    return MigrationStatus(
        current_version=current_version,
        target_version=_MIGRATIONS[-1].version if _MIGRATIONS else 0,
        applied_versions=applied_versions_list,
        applied_now=applied_now,
    )
