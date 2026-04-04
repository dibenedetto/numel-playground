"""Execution registry backed by the local platform database."""

from __future__ import annotations

import json
from typing import List, Optional

from domain.models import ExecutionRecord, ExecutionState

from .config import DatabaseConfig
from .support import connect_database, is_sqlite_url, resolve_database_path


class DbExecutionRegistry:
    """Store execution metadata independently from the live runtime."""

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
                CREATE INDEX IF NOT EXISTS idx_executions_user ON executions(user_id);
                CREATE INDEX IF NOT EXISTS idx_executions_space ON executions(space_id);
                CREATE INDEX IF NOT EXISTS idx_executions_status ON executions(status);
                """
            )

    def _row_to_record(self, row) -> ExecutionRecord:
        return ExecutionRecord(
            execution_id=row["execution_id"],
            user_id=row["user_id"],
            space_id=row["space_id"],
            asset_path=row["asset_path"],
            ref=row["ref"],
            status=ExecutionState(row["status"]),
            runtime_profile_id=row["runtime_profile_id"],
            started_at=row["started_at"],
            finished_at=row["finished_at"],
            outputs=json.loads(row["outputs_json"]) if row["outputs_json"] else {},
            error=row["error"],
            metadata=json.loads(row["metadata_json"]) if row["metadata_json"] else {},
        )

    async def create_execution(self, record: ExecutionRecord) -> ExecutionRecord:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO executions (
                    execution_id, user_id, space_id, asset_path, ref, status,
                    runtime_profile_id, started_at, finished_at, outputs_json, error, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.execution_id,
                    record.user_id,
                    record.space_id,
                    record.asset_path,
                    record.ref,
                    record.status.value,
                    record.runtime_profile_id,
                    record.started_at,
                    record.finished_at,
                    json.dumps(record.outputs, separators=(",", ":"), sort_keys=True),
                    record.error,
                    json.dumps(record.metadata, separators=(",", ":"), sort_keys=True),
                ),
            )
            row = conn.execute(
                "SELECT * FROM executions WHERE execution_id = ?",
                (record.execution_id,),
            ).fetchone()
        if row is None:
            raise RuntimeError(f"Failed to create execution '{record.execution_id}'")
        return self._row_to_record(row)

    async def update_execution(self, execution_id: str, **fields) -> ExecutionRecord:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM executions WHERE execution_id = ?",
                (execution_id,),
            ).fetchone()
            if row is None:
                raise ValueError(f"Unknown execution '{execution_id}'")
            current = self._row_to_record(row)
            updated = ExecutionRecord(
                execution_id=current.execution_id,
                user_id=fields.get("user_id", current.user_id),
                space_id=fields.get("space_id", current.space_id),
                asset_path=fields.get("asset_path", current.asset_path),
                ref=fields.get("ref", current.ref),
                status=fields.get("status", current.status),
                runtime_profile_id=fields.get("runtime_profile_id", current.runtime_profile_id),
                started_at=fields.get("started_at", current.started_at),
                finished_at=fields.get("finished_at", current.finished_at),
                outputs=fields.get("outputs", current.outputs),
                error=fields.get("error", current.error),
                metadata=fields.get("metadata", current.metadata),
            )
            conn.execute(
                """
                UPDATE executions
                SET user_id = ?, space_id = ?, asset_path = ?, ref = ?, status = ?,
                    runtime_profile_id = ?, started_at = ?, finished_at = ?,
                    outputs_json = ?, error = ?, metadata_json = ?
                WHERE execution_id = ?
                """,
                (
                    updated.user_id,
                    updated.space_id,
                    updated.asset_path,
                    updated.ref,
                    updated.status.value,
                    updated.runtime_profile_id,
                    updated.started_at,
                    updated.finished_at,
                    json.dumps(updated.outputs, separators=(",", ":"), sort_keys=True),
                    updated.error,
                    json.dumps(updated.metadata, separators=(",", ":"), sort_keys=True),
                    execution_id,
                ),
            )
            row = conn.execute(
                "SELECT * FROM executions WHERE execution_id = ?",
                (execution_id,),
            ).fetchone()
        if row is None:
            raise RuntimeError(f"Failed to update execution '{execution_id}'")
        return self._row_to_record(row)

    async def get_execution(self, execution_id: str) -> Optional[ExecutionRecord]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM executions WHERE execution_id = ?",
                (execution_id,),
            ).fetchone()
        return self._row_to_record(row) if row is not None else None

    async def list_executions(
        self,
        user_id: Optional[str] = None,
        space_id: Optional[str] = None,
        status: Optional[ExecutionState] = None,
        offset: int = 0,
        limit: int = 50,
    ) -> List[ExecutionRecord]:
        query = "SELECT * FROM executions"
        clauses = []
        params: List[object] = []
        if user_id is not None:
            clauses.append("user_id = ?")
            params.append(user_id)
        if space_id is not None:
            clauses.append("space_id = ?")
            params.append(space_id)
        if status is not None:
            clauses.append("status = ?")
            params.append(status.value if isinstance(status, ExecutionState) else str(status))
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY started_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._row_to_record(row) for row in rows]
