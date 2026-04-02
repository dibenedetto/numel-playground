"""Local identity provider for the platform reference backend."""

from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
import time
import uuid
from typing import List, Optional

from domain.interfaces import IdentityProvider
from domain.models import UsageQuota, UserAccount, UserProfile, UserRole

from .config import DatabaseConfig, LocalIdentityConfig
from .support import connect_sqlite, resolve_sqlite_path


class LocalIdentityProvider(IdentityProvider):
    """SQLite-backed identity provider for the fully working local stack."""

    def __init__(
        self,
        config: Optional[LocalIdentityConfig] = None,
        db_config: Optional[DatabaseConfig] = None,
        audit_log=None,
    ):
        self.config = config or LocalIdentityConfig()
        self.db_config = db_config or DatabaseConfig()
        self.audit_log = audit_log
        self._db_path = resolve_sqlite_path(self.db_config.url)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize_db()

    def _connect(self) -> sqlite3.Connection:
        return connect_sqlite(self.db_config.url)

    def _initialize_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
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

                CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
                CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
                CREATE INDEX IF NOT EXISTS idx_auth_tokens_user ON auth_tokens(user_id);
                """
            )

    def _json_loads(self, raw: Optional[str]) -> dict:
        if not raw:
            return {}
        return json.loads(raw)

    def _json_dumps(self, value: dict) -> str:
        return json.dumps(value or {}, separators=(",", ":"), sort_keys=True)

    def _hash_password(self, password: str, salt: str) -> str:
        digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt.encode("utf-8"),
            self.config.password_iterations,
        )
        return digest.hex()

    def _user_from_row(self, row: sqlite3.Row) -> UserAccount:
        return UserAccount(
            id=row["id"],
            username=row["username"],
            email=row["email"],
            role=UserRole(row["role"]),
            active=bool(row["active"]),
            created_at=row["created_at"],
            metadata=self._json_loads(row["metadata_json"]),
        )

    def _profile_from_row(self, row: sqlite3.Row) -> UserProfile:
        return UserProfile(
            user_id=row["user_id"],
            display_name=row["display_name"],
            bio=row["bio"],
            avatar_url=row["avatar_url"],
            metadata=self._json_loads(row["metadata_json"]),
        )

    def _quota_from_row(self, row: sqlite3.Row) -> UsageQuota:
        return UsageQuota(
            user_id=row["user_id"],
            cpu_seconds_remaining=row["cpu_seconds_remaining"],
            max_concurrent_runs=row["max_concurrent_runs"],
            storage_bytes_remaining=row["storage_bytes_remaining"],
            max_loop_hours=row["max_loop_hours"],
            gpu_hours_remaining=row["gpu_hours_remaining"],
            max_spaces=row["max_spaces"],
            max_assets_per_space=row["max_assets_per_space"],
        )

    def _make_token(self, user_id: str) -> str:
        return f"local_{user_id}_{secrets.token_urlsafe(24)}"

    async def authenticate(self, token: str) -> Optional[UserAccount]:
        now = time.time()
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT users.*
                FROM auth_tokens
                JOIN users ON users.id = auth_tokens.user_id
                WHERE auth_tokens.token = ? AND auth_tokens.expires_at > ?
                """,
                (token, now),
            ).fetchone()
            conn.execute("DELETE FROM auth_tokens WHERE expires_at <= ?", (now,))
        return self._user_from_row(row) if row is not None else None

    async def login(self, username: str, password: str) -> Optional[str]:
        now = time.time()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE username = ? AND active = 1",
                (username,),
            ).fetchone()
            if row is None:
                return None
            expected = self._hash_password(password, row["password_salt"])
            if not secrets.compare_digest(expected, row["password_hash"]):
                return None
            token = self._make_token(row["id"])
            conn.execute(
                """
                INSERT INTO auth_tokens (token, user_id, created_at, expires_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    token,
                    row["id"],
                    now,
                    now + self.config.token_ttl_seconds,
                ),
            )
        if self.audit_log is not None:
            await self.audit_log.record_event(
                category="identity",
                actor_user_id=row["id"],
                resource=f"user:{row['id']}",
                action="login",
                metadata={"username": username},
            )
        return token

    async def logout(self, token: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT user_id FROM auth_tokens WHERE token = ?",
                (token,),
            ).fetchone()
            result = conn.execute(
                "DELETE FROM auth_tokens WHERE token = ?",
                (token,),
            )
        if row is not None and self.audit_log is not None:
            await self.audit_log.record_event(
                category="identity",
                actor_user_id=row["user_id"],
                resource=f"user:{row['user_id']}",
                action="logout",
                metadata={},
            )
        return result.rowcount > 0

    async def create_user(self, username: str, email: str, password: str) -> UserAccount:
        user_id = f"user_{uuid.uuid4().hex[:12]}"
        salt = secrets.token_hex(16)
        now = time.time()
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT id FROM users WHERE username = ? OR email = ?",
                (username, email),
            ).fetchone()
            if existing is not None:
                raise ValueError("Username or email already exists")
            user_count = conn.execute("SELECT COUNT(*) AS count FROM users").fetchone()["count"]
            role = (
                UserRole.ADMIN
                if user_count == 0 and self.config.bootstrap_first_user_as_admin
                else UserRole.USER
            )
            conn.execute(
                """
                INSERT INTO users (
                    id, username, email, password_salt, password_hash,
                    role, active, created_at, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    username,
                    email,
                    salt,
                    self._hash_password(password, salt),
                    role.value,
                    1,
                    now,
                    self._json_dumps({}),
                ),
            )
            conn.execute(
                """
                INSERT INTO user_profiles (user_id, display_name, bio, avatar_url, metadata_json)
                VALUES (?, ?, '', '', ?)
                """,
                (user_id, username, self._json_dumps({})),
            )
            conn.execute(
                """
                INSERT INTO quotas (
                    user_id, cpu_seconds_remaining, max_concurrent_runs,
                    storage_bytes_remaining, max_loop_hours, gpu_hours_remaining,
                    max_spaces, max_assets_per_space
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    36000.0,
                    5,
                    1_073_741_824,
                    24.0,
                    0.0,
                    50,
                    10_000,
                ),
            )
            row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if row is None:
            raise RuntimeError(f"Failed to create user '{username}'")
        if self.audit_log is not None:
            await self.audit_log.record_event(
                category="identity",
                actor_user_id=user_id,
                resource=f"user:{user_id}",
                action="create_user",
                metadata={"username": username, "email": email},
            )
        return self._user_from_row(row)

    async def get_user(self, user_id: str) -> Optional[UserAccount]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return self._user_from_row(row) if row is not None else None

    async def get_user_by_username(self, username: str) -> Optional[UserAccount]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE username = ?",
                (username,),
            ).fetchone()
        return self._user_from_row(row) if row is not None else None

    async def list_users(
        self, offset: int = 0, limit: int = 50, active_only: bool = True
    ) -> List[UserAccount]:
        query = "SELECT * FROM users"
        params: List[object] = []
        if active_only:
            query += " WHERE active = 1"
        query += " ORDER BY created_at ASC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._user_from_row(row) for row in rows]

    async def update_user(self, user_id: str, **fields) -> UserAccount:
        allowed = {"username", "email", "role", "active", "metadata"}
        updates = {key: value for key, value in fields.items() if key in allowed}
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
            if row is None:
                raise ValueError(f"Unknown user '{user_id}'")
            conn.execute(
                """
                UPDATE users
                SET username = ?, email = ?, role = ?, active = ?, metadata_json = ?
                WHERE id = ?
                """,
                (
                    updates.get("username", row["username"]),
                    updates.get("email", row["email"]),
                    (updates.get("role", UserRole(row["role"]))).value
                    if isinstance(updates.get("role", UserRole(row["role"])), UserRole)
                    else str(updates.get("role", row["role"])),
                    1 if bool(updates.get("active", bool(row["active"]))) else 0,
                    self._json_dumps(updates.get("metadata", self._json_loads(row["metadata_json"]))),
                    user_id,
                ),
            )
            row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return self._user_from_row(row)

    async def delete_user(self, user_id: str) -> bool:
        with self._connect() as conn:
            result = conn.execute(
                "UPDATE users SET active = 0 WHERE id = ? AND active = 1",
                (user_id,),
            )
            conn.execute("DELETE FROM auth_tokens WHERE user_id = ?", (user_id,))
        if result.rowcount > 0 and self.audit_log is not None:
            await self.audit_log.record_event(
                category="identity",
                actor_user_id=user_id,
                resource=f"user:{user_id}",
                action="deactivate_user",
                metadata={},
            )
        return result.rowcount > 0

    async def get_profile(self, user_id: str) -> Optional[UserProfile]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM user_profiles WHERE user_id = ?",
                (user_id,),
            ).fetchone()
        return self._profile_from_row(row) if row is not None else None

    async def update_profile(self, user_id: str, **fields) -> UserProfile:
        allowed = {"display_name", "bio", "avatar_url", "metadata"}
        updates = {key: value for key, value in fields.items() if key in allowed}
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM user_profiles WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            if row is None:
                raise ValueError(f"Unknown profile for user '{user_id}'")
            conn.execute(
                """
                UPDATE user_profiles
                SET display_name = ?, bio = ?, avatar_url = ?, metadata_json = ?
                WHERE user_id = ?
                """,
                (
                    updates.get("display_name", row["display_name"]),
                    updates.get("bio", row["bio"]),
                    updates.get("avatar_url", row["avatar_url"]),
                    self._json_dumps(updates.get("metadata", self._json_loads(row["metadata_json"]))),
                    user_id,
                ),
            )
            row = conn.execute(
                "SELECT * FROM user_profiles WHERE user_id = ?",
                (user_id,),
            ).fetchone()
        return self._profile_from_row(row)

    async def get_quota(self, user_id: str) -> UsageQuota:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM quotas WHERE user_id = ?",
                (user_id,),
            ).fetchone()
        if row is None:
            raise ValueError(f"Unknown quota for user '{user_id}'")
        return self._quota_from_row(row)

    async def update_quota(self, user_id: str, **fields) -> UsageQuota:
        allowed = {
            "cpu_seconds_remaining",
            "max_concurrent_runs",
            "storage_bytes_remaining",
            "max_loop_hours",
            "gpu_hours_remaining",
            "max_spaces",
            "max_assets_per_space",
        }
        updates = {key: value for key, value in fields.items() if key in allowed}
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM quotas WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            if row is None:
                raise ValueError(f"Unknown quota for user '{user_id}'")
            conn.execute(
                """
                UPDATE quotas
                SET cpu_seconds_remaining = ?, max_concurrent_runs = ?,
                    storage_bytes_remaining = ?, max_loop_hours = ?,
                    gpu_hours_remaining = ?, max_spaces = ?,
                    max_assets_per_space = ?
                WHERE user_id = ?
                """,
                (
                    updates.get("cpu_seconds_remaining", row["cpu_seconds_remaining"]),
                    updates.get("max_concurrent_runs", row["max_concurrent_runs"]),
                    updates.get("storage_bytes_remaining", row["storage_bytes_remaining"]),
                    updates.get("max_loop_hours", row["max_loop_hours"]),
                    updates.get("gpu_hours_remaining", row["gpu_hours_remaining"]),
                    updates.get("max_spaces", row["max_spaces"]),
                    updates.get("max_assets_per_space", row["max_assets_per_space"]),
                    user_id,
                ),
            )
            row = conn.execute(
                "SELECT * FROM quotas WHERE user_id = ?",
                (user_id,),
            ).fetchone()
        return self._quota_from_row(row)

    async def change_password(self, user_id: str, current_password: str, new_password: str) -> bool:
        if not current_password or not new_password:
            return False
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT id, username, password_salt, password_hash
                FROM users
                WHERE id = ? AND active = 1
                """,
                (user_id,),
            ).fetchone()
            if row is None:
                return False
            expected = self._hash_password(current_password, row["password_salt"])
            if not secrets.compare_digest(expected, row["password_hash"]):
                return False
            conn.execute(
                """
                UPDATE users
                SET password_hash = ?
                WHERE id = ?
                """,
                (self._hash_password(new_password, row["password_salt"]), user_id),
            )
            conn.execute("DELETE FROM auth_tokens WHERE user_id = ?", (user_id,))
        if self.audit_log is not None:
            await self.audit_log.record_event(
                category="identity",
                actor_user_id=user_id,
                resource=f"user:{user_id}",
                action="change_password",
                metadata={},
            )
        return True
