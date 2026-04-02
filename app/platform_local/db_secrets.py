"""Secrets providers for the local and future platform stacks."""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from typing import Dict, List, Optional

from domain.interfaces import SecretsProvider
from domain.models import CredentialRecord, SecretScope

from .config import DatabaseConfig, SecretsConfig
from .support import ScaffoldComponent, connect_sqlite, resolve_sqlite_path


class DbSecretsProvider(SecretsProvider):
    """Store secret metadata and values in the local platform database."""

    def __init__(self, config: SecretsConfig, db_config: DatabaseConfig, audit_log=None):
        self.config = config
        self.db_config = db_config
        self.audit_log = audit_log
        self._db_path = resolve_sqlite_path(db_config.url)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize_db()

    def _connect(self) -> sqlite3.Connection:
        return connect_sqlite(self.db_config.url)

    def _initialize_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
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
                CREATE INDEX IF NOT EXISTS idx_credentials_owner ON credentials(owner_user_id);
                CREATE INDEX IF NOT EXISTS idx_credentials_scope ON credentials(scope);
                CREATE INDEX IF NOT EXISTS idx_credentials_space ON credentials(space_id);
                """
            )

    def _json_loads(self, raw: Optional[str]) -> Dict[str, str]:
        if not raw:
            return {}
        return json.loads(raw)

    def _scope_for(self, space_id: Optional[str]) -> SecretScope:
        return SecretScope.SPACE if space_id else SecretScope.USER

    def _row_to_record(self, row: sqlite3.Row) -> CredentialRecord:
        return CredentialRecord(
            id=row["id"],
            owner_user_id=row["owner_user_id"],
            name=row["name"],
            scope=SecretScope(row["scope"]),
            space_id=row["space_id"] or None,
            secret_ref=f"{self.config.key_prefix}:{row['id']}",
            value_present=bool(row["secret_value"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            last_used_at=row["last_used_at"],
            metadata=self._json_loads(row["metadata_json"]),
        )

    async def list_credentials(
        self, owner_user_id: str, space_id: Optional[str] = None
    ) -> List[CredentialRecord]:
        scope = self._scope_for(space_id)
        scope_space_id = space_id or ""
        with self._connect() as conn:
            if space_id is None:
                rows = conn.execute(
                    """
                    SELECT * FROM credentials
                    WHERE owner_user_id = ? AND scope = ?
                    ORDER BY name ASC
                    """,
                    (owner_user_id, scope.value),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM credentials
                    WHERE owner_user_id = ? AND scope = ? AND space_id = ?
                    ORDER BY name ASC
                    """,
                    (owner_user_id, scope.value, scope_space_id),
                ).fetchall()
        return [self._row_to_record(row) for row in rows]

    async def get_credential(
        self, owner_user_id: str, name: str, space_id: Optional[str] = None
    ) -> Optional[CredentialRecord]:
        scope = self._scope_for(space_id)
        scope_space_id = space_id or ""
        with self._connect() as conn:
            if space_id is None:
                row = conn.execute(
                    """
                    SELECT * FROM credentials
                    WHERE owner_user_id = ? AND name = ? AND scope = ?
                    """,
                    (owner_user_id, name, scope.value),
                ).fetchone()
            else:
                row = conn.execute(
                    """
                    SELECT * FROM credentials
                    WHERE owner_user_id = ? AND name = ? AND scope = ? AND space_id = ?
                    """,
                    (owner_user_id, name, scope.value, scope_space_id),
                ).fetchone()
        return self._row_to_record(row) if row is not None else None

    async def set_credential(
        self,
        owner_user_id: str,
        name: str,
        value: str,
        space_id: Optional[str] = None,
        metadata: Optional[Dict[str, str]] = None,
    ) -> CredentialRecord:
        now = time.time()
        scope = self._scope_for(space_id)
        scope_space_id = space_id or ""
        with self._connect() as conn:
            if space_id is None:
                existing = conn.execute(
                    """
                    SELECT * FROM credentials
                    WHERE owner_user_id = ? AND name = ? AND scope = ?
                    """,
                    (owner_user_id, name, scope.value),
                ).fetchone()
            else:
                existing = conn.execute(
                    """
                    SELECT * FROM credentials
                    WHERE owner_user_id = ? AND name = ? AND scope = ? AND space_id = ?
                    """,
                    (owner_user_id, name, scope.value, scope_space_id),
                ).fetchone()
            if existing is None:
                credential_id = f"cred_{uuid.uuid4().hex[:12]}"
                conn.execute(
                    """
                    INSERT INTO credentials (
                        id, owner_user_id, name, scope, space_id, secret_value,
                        created_at, updated_at, last_used_at, metadata_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        credential_id,
                        owner_user_id,
                        name,
                        scope.value,
                        scope_space_id,
                        value,
                        now,
                        now,
                        None,
                        json.dumps(metadata or {}, separators=(",", ":"), sort_keys=True),
                    ),
                )
            else:
                credential_id = existing["id"]
                conn.execute(
                    """
                    UPDATE credentials
                    SET secret_value = ?, updated_at = ?, metadata_json = ?
                    WHERE id = ?
                    """,
                    (
                        value,
                        now,
                        json.dumps(
                            metadata or self._json_loads(existing["metadata_json"]),
                            separators=(",", ":"),
                            sort_keys=True,
                        ),
                        credential_id,
                    ),
                )
            row = conn.execute(
                "SELECT * FROM credentials WHERE id = ?",
                (credential_id,),
            ).fetchone()
        if row is None:
            raise RuntimeError(f"Failed to store credential '{name}'")
        if self.audit_log is not None:
            await self.audit_log.record_event(
                category="secrets",
                actor_user_id=owner_user_id,
                resource=f"credential:{credential_id}",
                action="set_credential",
                metadata={"name": name, "scope": scope.value, "space_id": scope_space_id},
            )
        return self._row_to_record(row)

    async def delete_credential(
        self, owner_user_id: str, name: str, space_id: Optional[str] = None
    ) -> bool:
        scope = self._scope_for(space_id)
        scope_space_id = space_id or ""
        with self._connect() as conn:
            if space_id is None:
                row = conn.execute(
                    """
                    SELECT id FROM credentials
                    WHERE owner_user_id = ? AND name = ? AND scope = ?
                    """,
                    (owner_user_id, name, scope.value),
                ).fetchone()
                result = conn.execute(
                    """
                    DELETE FROM credentials
                    WHERE owner_user_id = ? AND name = ? AND scope = ?
                    """,
                    (owner_user_id, name, scope.value),
                )
            else:
                row = conn.execute(
                    """
                    SELECT id FROM credentials
                    WHERE owner_user_id = ? AND name = ? AND scope = ? AND space_id = ?
                    """,
                    (owner_user_id, name, scope.value, scope_space_id),
                ).fetchone()
                result = conn.execute(
                    """
                    DELETE FROM credentials
                    WHERE owner_user_id = ? AND name = ? AND scope = ? AND space_id = ?
                    """,
                    (owner_user_id, name, scope.value, scope_space_id),
                )
        if result.rowcount > 0 and row is not None and self.audit_log is not None:
            await self.audit_log.record_event(
                category="secrets",
                actor_user_id=owner_user_id,
                resource=f"credential:{row['id']}",
                action="delete_credential",
                metadata={"name": name, "scope": scope.value, "space_id": scope_space_id},
            )
        return result.rowcount > 0

    async def resolve_credentials(
        self,
        owner_user_id: str,
        names: Optional[List[str]] = None,
        space_id: Optional[str] = None,
    ) -> Dict[str, str]:
        scope = self._scope_for(space_id)
        scope_space_id = space_id or ""
        now = time.time()
        with self._connect() as conn:
            if space_id is None:
                rows = conn.execute(
                    """
                    SELECT * FROM credentials
                    WHERE owner_user_id = ? AND scope = ?
                    ORDER BY name ASC
                    """,
                    (owner_user_id, scope.value),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM credentials
                    WHERE owner_user_id = ? AND scope = ? AND space_id = ?
                    ORDER BY name ASC
                    """,
                    (owner_user_id, scope.value, scope_space_id),
                ).fetchall()
            filtered = [
                row for row in rows
                if names is None or row["name"] in names
            ]
            if filtered:
                conn.executemany(
                    "UPDATE credentials SET last_used_at = ? WHERE id = ?",
                    [(now, row["id"]) for row in filtered],
                )
        resolved = {row["name"]: row["secret_value"] for row in filtered}
        if resolved and self.audit_log is not None:
            await self.audit_log.record_event(
                category="secrets",
                actor_user_id=owner_user_id,
                resource=f"scope:{scope.value}",
                action="resolve_credentials",
                metadata={
                    "names": sorted(resolved.keys()),
                    "space_id": scope_space_id,
                },
            )
        return resolved


class VaultSecretsProvider(DbSecretsProvider, ScaffoldComponent):
    """Alternative secrets backend for a future vault-based deployment."""

    async def list_credentials(
        self, owner_user_id: str, space_id: Optional[str] = None
    ) -> List[CredentialRecord]:
        self._not_ready("list_credentials[vault]")

    async def get_credential(
        self, owner_user_id: str, name: str, space_id: Optional[str] = None
    ) -> Optional[CredentialRecord]:
        self._not_ready("get_credential[vault]")

    async def set_credential(
        self,
        owner_user_id: str,
        name: str,
        value: str,
        space_id: Optional[str] = None,
        metadata: Optional[Dict[str, str]] = None,
    ) -> CredentialRecord:
        self._not_ready("set_credential[vault]")

    async def delete_credential(
        self, owner_user_id: str, name: str, space_id: Optional[str] = None
    ) -> bool:
        self._not_ready("delete_credential[vault]")

    async def resolve_credentials(
        self,
        owner_user_id: str,
        names: Optional[List[str]] = None,
        space_id: Optional[str] = None,
    ) -> Dict[str, str]:
        self._not_ready("resolve_credentials[vault]")
