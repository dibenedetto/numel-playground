"""Database-backed friendship provider for local development."""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import List, Optional

from domain.interfaces import FriendGraphProvider
from domain.models import Friendship, FriendshipStatus

from .config import DatabaseConfig
from .support import connect_sqlite, resolve_sqlite_path


class DbFriendGraphProvider(FriendGraphProvider):
    """Relational implementation for friend requests and accepted links."""

    def __init__(self, db_config: DatabaseConfig, audit_log=None):
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
                CREATE TABLE IF NOT EXISTS friendships (
                    requester_user_id TEXT NOT NULL,
                    target_user_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    metadata_json TEXT,
                    PRIMARY KEY(requester_user_id, target_user_id)
                );
                CREATE INDEX IF NOT EXISTS idx_friendships_target ON friendships(target_user_id);
                CREATE INDEX IF NOT EXISTS idx_friendships_status ON friendships(status);
                """
            )

    def _row_to_friendship(self, row: sqlite3.Row) -> Friendship:
        return Friendship(
            requester_user_id=row["requester_user_id"],
            target_user_id=row["target_user_id"],
            status=FriendshipStatus(row["status"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            metadata={},
        )

    def _get_direct(self, conn: sqlite3.Connection, requester_user_id: str, target_user_id: str):
        return conn.execute(
            """
            SELECT requester_user_id, target_user_id, status, created_at, updated_at, metadata_json
            FROM friendships
            WHERE requester_user_id = ? AND target_user_id = ?
            """,
            (requester_user_id, target_user_id),
        ).fetchone()

    def _get_either_direction(self, conn: sqlite3.Connection, user_a: str, user_b: str):
        return conn.execute(
            """
            SELECT requester_user_id, target_user_id, status, created_at, updated_at, metadata_json
            FROM friendships
            WHERE (requester_user_id = ? AND target_user_id = ?)
               OR (requester_user_id = ? AND target_user_id = ?)
            ORDER BY created_at ASC
            LIMIT 1
            """,
            (user_a, user_b, user_b, user_a),
        ).fetchone()

    async def send_request(self, requester_user_id: str, target_user_id: str) -> Friendship:
        if requester_user_id == target_user_id:
            raise ValueError("Users cannot friend themselves")
        now = time.time()
        with self._connect() as conn:
            existing = self._get_either_direction(conn, requester_user_id, target_user_id)
            if existing is not None:
                status = FriendshipStatus(existing["status"])
                if status == FriendshipStatus.ACCEPTED:
                    return self._row_to_friendship(existing)
                if (
                    existing["requester_user_id"] == target_user_id
                    and status == FriendshipStatus.PENDING
                ):
                    conn.execute(
                        """
                        UPDATE friendships
                        SET status = ?, updated_at = ?
                        WHERE requester_user_id = ? AND target_user_id = ?
                        """,
                        (FriendshipStatus.ACCEPTED.value, now, target_user_id, requester_user_id),
                    )
                    row = self._get_direct(conn, target_user_id, requester_user_id)
                    return self._row_to_friendship(row)
                conn.execute(
                    """
                    UPDATE friendships
                    SET status = ?, updated_at = ?
                    WHERE requester_user_id = ? AND target_user_id = ?
                    """,
                    (
                        FriendshipStatus.PENDING.value,
                        now,
                        requester_user_id,
                        target_user_id,
                    ),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO friendships (
                        requester_user_id, target_user_id, status, created_at, updated_at, metadata_json
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        requester_user_id,
                        target_user_id,
                        FriendshipStatus.PENDING.value,
                        now,
                        now,
                        "{}",
                    ),
                )
            row = self._get_direct(conn, requester_user_id, target_user_id)
        if row is None:
            raise RuntimeError("Failed to create friend request")
        return self._row_to_friendship(row)

    async def accept_request(self, requester_user_id: str, target_user_id: str) -> Friendship:
        now = time.time()
        with self._connect() as conn:
            row = self._get_direct(conn, requester_user_id, target_user_id)
            if row is None:
                raise ValueError("Friend request not found")
            conn.execute(
                """
                UPDATE friendships SET status = ?, updated_at = ?
                WHERE requester_user_id = ? AND target_user_id = ?
                """,
                (FriendshipStatus.ACCEPTED.value, now, requester_user_id, target_user_id),
            )
            row = self._get_direct(conn, requester_user_id, target_user_id)
        return self._row_to_friendship(row)

    async def reject_request(self, requester_user_id: str, target_user_id: str) -> Friendship:
        now = time.time()
        with self._connect() as conn:
            row = self._get_direct(conn, requester_user_id, target_user_id)
            if row is None:
                raise ValueError("Friend request not found")
            conn.execute(
                """
                UPDATE friendships SET status = ?, updated_at = ?
                WHERE requester_user_id = ? AND target_user_id = ?
                """,
                (FriendshipStatus.REJECTED.value, now, requester_user_id, target_user_id),
            )
            row = self._get_direct(conn, requester_user_id, target_user_id)
        return self._row_to_friendship(row)

    async def remove_friend(self, user_id: str, friend_user_id: str) -> bool:
        with self._connect() as conn:
            result = conn.execute(
                """
                DELETE FROM friendships
                WHERE (requester_user_id = ? AND target_user_id = ?)
                   OR (requester_user_id = ? AND target_user_id = ?)
                """,
                (user_id, friend_user_id, friend_user_id, user_id),
            )
            return result.rowcount > 0

    async def list_friendships(
        self, user_id: str, status: Optional[FriendshipStatus] = None
    ) -> List[Friendship]:
        with self._connect() as conn:
            if status is None:
                rows = conn.execute(
                    """
                    SELECT requester_user_id, target_user_id, status, created_at, updated_at, metadata_json
                    FROM friendships
                    WHERE requester_user_id = ? OR target_user_id = ?
                    ORDER BY updated_at DESC
                    """,
                    (user_id, user_id),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT requester_user_id, target_user_id, status, created_at, updated_at, metadata_json
                    FROM friendships
                    WHERE (requester_user_id = ? OR target_user_id = ?)
                      AND status = ?
                    ORDER BY updated_at DESC
                    """,
                    (user_id, user_id, status.value),
                ).fetchall()
        return [self._row_to_friendship(row) for row in rows]

    async def are_friends(self, user_id: str, other_user_id: str) -> bool:
        if user_id == other_user_id:
            return True
        with self._connect() as conn:
            row = self._get_either_direction(conn, user_id, other_user_id)
        return row is not None and row["status"] == FriendshipStatus.ACCEPTED.value
