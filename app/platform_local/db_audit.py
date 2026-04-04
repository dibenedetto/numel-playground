"""Database-backed audit log for the local and future platform stacks."""

from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Optional

from .config import DatabaseConfig
from .support import connect_database, is_sqlite_url, resolve_database_path


class DbAuditLog:
    """Persist platform audit events in the relational metadata store."""

    def __init__(self, db_config: DatabaseConfig):
        self.db_config = db_config
        self._db_path = resolve_database_path(db_config.url)
        if self._db_path is not None:
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
        if is_sqlite_url(db_config.url):
            self._initialize_db()

    def _connect(self):
        return connect_database(self.db_config.url)

    def _initialize_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    category TEXT NOT NULL,
                    actor_user_id TEXT NOT NULL DEFAULT '',
                    resource TEXT NOT NULL DEFAULT '',
                    action TEXT NOT NULL DEFAULT '',
                    metadata_json TEXT,
                    created_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_audit_category ON audit_log(category);
                CREATE INDEX IF NOT EXISTS idx_audit_actor ON audit_log(actor_user_id);
                CREATE INDEX IF NOT EXISTS idx_audit_resource ON audit_log(resource);
                CREATE INDEX IF NOT EXISTS idx_audit_created_at ON audit_log(created_at);
                """
            )

    def _json_loads(self, raw: Optional[str]) -> Dict[str, Any]:
        if not raw:
            return {}
        return json.loads(raw)

    async def record_event(
        self,
        category: str,
        actor_user_id: str = "",
        resource: str = "",
        action: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO audit_log (
                    category, actor_user_id, resource, action, metadata_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    category,
                    actor_user_id,
                    resource,
                    action,
                    json.dumps(metadata or {}, separators=(",", ":"), sort_keys=True),
                    time.time(),
                ),
            )

    async def list_events(
        self,
        category: str = "",
        actor_user_id: str = "",
        resource: str = "",
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        query = "SELECT * FROM audit_log"
        clauses = []
        params: List[object] = []
        if category:
            clauses.append("category = ?")
            params.append(category)
        if actor_user_id:
            clauses.append("actor_user_id = ?")
            params.append(actor_user_id)
        if resource:
            clauses.append("resource = ?")
            params.append(resource)
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [
            {
                "id": row["id"],
                "category": row["category"],
                "actor_user_id": row["actor_user_id"],
                "resource": row["resource"],
                "action": row["action"],
                "metadata": self._json_loads(row["metadata_json"]),
                "created_at": row["created_at"],
            }
            for row in rows
        ]
