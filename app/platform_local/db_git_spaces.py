"""Database + Git implementation for Numel spaces.

This local-development implementation uses SQLite for metadata and Git for
versioned content. It now enforces the visibility and ACL rules that are
expressible through the current space interface, including friend-aware reads
for protected spaces.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import re
import time
import uuid
from pathlib import Path
from typing import List, Optional

from domain.interfaces import SpaceProvider
from domain.models import (
    AclEntry,
    AssetKind,
    Capability,
    PermissionPolicy,
    RefKind,
    Space,
    SpaceAsset,
    SpaceCommit,
    SpaceRef,
    SubjectType,
    Visibility,
)

from .config import ArtifactStorageConfig, DatabaseConfig
from .db_friend_graph import DbFriendGraphProvider
from .git_space_store import GitSpaceStore
from .support import (
    ScaffoldComponent,
    connect_database,
    is_sqlite_url,
    resolve_database_path,
)


class DbGitSpaceProvider(SpaceProvider, ScaffoldComponent):
    """Coordinate relational space metadata with Git-backed content."""

    def __init__(
        self,
        db_config: DatabaseConfig,
        git_store: GitSpaceStore,
        artifact_config: Optional[ArtifactStorageConfig] = None,
        friend_graph: Optional[DbFriendGraphProvider] = None,
        audit_log=None,
    ):
        self.db_config = db_config
        self.git_store = git_store
        self.artifact_config = artifact_config
        self.friend_graph = friend_graph
        self.audit_log = audit_log
        self._db_path = self._resolve_database_path(db_config.url)
        if self._db_path is not None:
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
        if is_sqlite_url(db_config.url):
            self._initialize_db()

    def _resolve_database_path(self, url: str) -> Optional[Path]:
        return resolve_database_path(url)

    def _connect(self):
        return connect_database(self.db_config.url)

    def _initialize_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
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

                CREATE INDEX IF NOT EXISTS idx_spaces_owner ON spaces(owner_user_id);
                CREATE INDEX IF NOT EXISTS idx_spaces_visibility ON spaces(visibility);
                CREATE INDEX IF NOT EXISTS idx_space_assets_space ON space_assets(space_id);
                CREATE INDEX IF NOT EXISTS idx_space_assets_path ON space_assets(space_id, path);
                """
            )

    def _normalize_relpath(self, path: str) -> str:
        rel = path.replace("\\", "/").strip("/")
        if not rel or rel.startswith("../") or "/../" in f"/{rel}/":
            raise ValueError(f"Invalid asset path: {path!r}")
        return rel

    def _normalize_space_slug(self, value: str) -> str:
        slug = re.sub(r"[^a-zA-Z0-9._-]+", "-", (value or "").strip().lower()).strip("-._")
        return slug or "space"

    def _ensure_unique_space_slug(
        self,
        conn,
        owner_user_id: str,
        slug: str,
        *,
        exclude_space_id: Optional[str] = None,
    ) -> str:
        base = self._normalize_space_slug(slug)
        candidate = base
        suffix = 2
        while True:
            params = [owner_user_id, candidate]
            sql = "SELECT 1 FROM spaces WHERE owner_user_id = ? AND slug = ?"
            if exclude_space_id:
                sql += " AND id <> ?"
                params.append(exclude_space_id)
            row = conn.execute(sql, tuple(params)).fetchone()
            if row is None:
                return candidate
            candidate = f"{base}-{suffix}"
            suffix += 1

    def _json_dumps(self, obj) -> str:
        return json.dumps(obj, separators=(",", ":"), sort_keys=True)

    def _policy_to_json(self, policy: Optional[PermissionPolicy]) -> Optional[str]:
        if policy is None:
            return None
        return self._json_dumps(
            {
                "owner_user_id": policy.owner_user_id,
                "visibility": policy.visibility.value,
                "acl": [
                    {
                        "subject_type": entry.subject_type.value,
                        "subject_id": entry.subject_id,
                        "capabilities": [cap.value for cap in entry.capabilities],
                        "metadata": entry.metadata,
                    }
                    for entry in policy.acl
                ],
                "metadata": policy.metadata,
            }
        )

    def _policy_from_json(
        self,
        raw: Optional[str],
        owner_user_id: str,
        visibility: Visibility,
    ) -> PermissionPolicy:
        if not raw:
            return PermissionPolicy(owner_user_id=owner_user_id, visibility=visibility)
        data = json.loads(raw)
        acl = [
            AclEntry(
                subject_type=SubjectType(item["subject_type"]),
                subject_id=item.get("subject_id", ""),
                capabilities=[Capability(cap) for cap in item.get("capabilities", [])],
                metadata=item.get("metadata", {}),
            )
            for item in data.get("acl", [])
        ]
        return PermissionPolicy(
            owner_user_id=data.get("owner_user_id", owner_user_id),
            visibility=Visibility(data.get("visibility", visibility.value)),
            acl=acl,
            metadata=data.get("metadata", {}),
        )

    def _space_from_row(self, row) -> Space:
        visibility = Visibility(row["visibility"])
        return Space(
            id=row["id"],
            owner_user_id=row["owner_user_id"],
            slug=row["slug"],
            title=row["title"],
            description=row["description"],
            visibility=visibility,
            default_ref=row["default_ref"],
            head_commit_id=row["head_commit_id"],
            policy=self._policy_from_json(row["policy_json"], row["owner_user_id"], visibility),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            metadata=json.loads(row["metadata_json"]) if row["metadata_json"] else {},
        )

    def _asset_from_row(self, row) -> SpaceAsset:
        visibility = Visibility(row["visibility"])
        return SpaceAsset(
            id=row["id"],
            space_id=row["space_id"],
            path=row["path"],
            kind=AssetKind(row["kind"]),
            owner_user_id=row["owner_user_id"],
            title=row["title"],
            description=row["description"],
            visibility=visibility,
            versioned=bool(row["versioned"]),
            executable=bool(row["executable"]),
            size_bytes=row["size_bytes"],
            content_hash=row["content_hash"],
            latest_commit_id=row["latest_commit_id"],
            policy=self._policy_from_json(row["policy_json"], row["owner_user_id"], visibility),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            metadata=json.loads(row["metadata_json"]) if row["metadata_json"] else {},
        )

    def _infer_kind(self, path: str, existing: Optional[SpaceAsset] = None) -> AssetKind:
        if existing is not None:
            return existing.kind
        lowered = path.lower()
        if lowered.endswith(".skill.md") or "/skills/" in f"/{lowered}/":
            return AssetKind.SKILL
        if lowered.endswith("_toolkit.py") or "/toolkits/" in f"/{lowered}/":
            return AssetKind.TOOLKIT
        if lowered.endswith(".json"):
            return AssetKind.WORKFLOW
        return AssetKind.DATA

    def _get_space_row(self, conn, space_id: str):
        return conn.execute("SELECT * FROM spaces WHERE id = ?", (space_id,)).fetchone()

    def _get_asset_row(self, conn, space_id: str, path: str):
        return conn.execute(
            "SELECT * FROM space_assets WHERE space_id = ? AND path = ?",
            (space_id, path),
        ).fetchone()

    def _require_space(self, conn, space_id: str):
        row = self._get_space_row(conn, space_id)
        if row is None:
            raise ValueError(f"Unknown space '{space_id}'")
        return row

    async def _entry_matches(
        self,
        entry: AclEntry,
        *,
        user_id: str,
        owner_user_id: str,
    ) -> bool:
        if entry.subject_type == SubjectType.OWNER:
            return user_id == owner_user_id
        if entry.subject_type == SubjectType.USER:
            return entry.subject_id == user_id
        if entry.subject_type == SubjectType.PUBLIC:
            return True
        if entry.subject_type == SubjectType.FRIENDS:
            return (
                self.friend_graph is not None
                and await self.friend_graph.are_friends(user_id, owner_user_id)
            )
        if entry.subject_type == SubjectType.ROLE:
            return False
        return False

    async def _policy_has_capability(
        self,
        policy: PermissionPolicy,
        *,
        user_id: str,
        capability: Capability,
    ) -> bool:
        owner_user_id = policy.owner_user_id
        if user_id == owner_user_id:
            return True
        for entry in policy.acl:
            if not await self._entry_matches(entry, user_id=user_id, owner_user_id=owner_user_id):
                continue
            if Capability.ADMIN in entry.capabilities or capability in entry.capabilities:
                return True
        if capability == Capability.READ:
            if policy.visibility == Visibility.PUBLIC:
                return True
            if (
                policy.visibility == Visibility.PROTECTED
                and self.friend_graph is not None
                and await self.friend_graph.are_friends(user_id, owner_user_id)
            ):
                return True
        return False

    async def _space_has_capability(
        self,
        user_id: str,
        row,
        capability: Capability,
    ) -> bool:
        policy = self._policy_from_json(
            row["policy_json"],
            row["owner_user_id"],
            Visibility(row["visibility"]),
        )
        return await self._policy_has_capability(policy, user_id=user_id, capability=capability)

    async def _asset_has_capability(
        self,
        user_id: str,
        asset: SpaceAsset,
        space_row,
        capability: Capability,
    ) -> bool:
        policy = asset.policy or PermissionPolicy(
            owner_user_id=asset.owner_user_id,
            visibility=asset.visibility,
        )
        allowed = await self._policy_has_capability(policy, user_id=user_id, capability=capability)
        if allowed:
            return True
        return await self._space_has_capability(user_id, space_row, capability)

    async def _ensure_space_access(
        self,
        user_id: str,
        row,
        capability: Capability,
    ) -> None:
        if not await self._space_has_capability(user_id, row, capability):
            raise PermissionError(
                f"User '{user_id}' does not have '{capability.value}' on space '{row['id']}'"
            )

    async def check_space_access(
        self,
        user_id: str,
        space_id: str,
        capability: Capability,
    ) -> bool:
        with self._connect() as conn:
            row = self._get_space_row(conn, space_id)
        if row is None:
            return False
        return await self._space_has_capability(user_id, row, capability)

    async def check_asset_access(
        self,
        user_id: str,
        space_id: str,
        path: str,
        capability: Capability,
    ) -> bool:
        rel = self._normalize_relpath(path)
        with self._connect() as conn:
            space_row = self._get_space_row(conn, space_id)
            if space_row is None:
                return False
            if not await self._space_has_capability(user_id, space_row, capability):
                return False
            asset_row = self._get_asset_row(conn, space_id, rel)
        if asset_row is None:
            return True
        return await self._asset_has_capability(
            user_id,
            self._asset_from_row(asset_row),
            space_row,
            capability,
        )

    def _upsert_asset(self, conn, asset: SpaceAsset) -> SpaceAsset:
        now = time.time()
        existing = conn.execute(
            "SELECT * FROM space_assets WHERE space_id = ? AND path = ?",
            (asset.space_id, asset.path),
        ).fetchone()
        created_at = existing["created_at"] if existing else (asset.created_at or now)
        asset_id = existing["id"] if existing else (asset.id or uuid.uuid4().hex[:16])
        conn.execute(
            """
            INSERT INTO space_assets (
                id, space_id, path, kind, owner_user_id, title, description, visibility,
                versioned, executable, size_bytes, content_hash, latest_commit_id,
                policy_json, metadata_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(space_id, path) DO UPDATE SET
                kind = excluded.kind,
                owner_user_id = excluded.owner_user_id,
                title = excluded.title,
                description = excluded.description,
                visibility = excluded.visibility,
                versioned = excluded.versioned,
                executable = excluded.executable,
                size_bytes = excluded.size_bytes,
                content_hash = excluded.content_hash,
                latest_commit_id = excluded.latest_commit_id,
                policy_json = excluded.policy_json,
                metadata_json = excluded.metadata_json,
                updated_at = excluded.updated_at
            """,
            (
                asset_id,
                asset.space_id,
                asset.path,
                asset.kind.value,
                asset.owner_user_id,
                asset.title,
                asset.description,
                asset.visibility.value,
                1 if asset.versioned else 0,
                1 if asset.executable else 0,
                asset.size_bytes,
                asset.content_hash,
                asset.latest_commit_id,
                self._policy_to_json(asset.policy),
                self._json_dumps(asset.metadata),
                created_at,
                now,
            ),
        )
        row = self._get_asset_row(conn, asset.space_id, asset.path)
        if row is None:
            raise RuntimeError(f"Failed to upsert asset {asset.space_id}:{asset.path}")
        return self._asset_from_row(row)

    def _update_space_head(self, conn, space_id: str, commit_id: str = "") -> None:
        conn.execute(
            "UPDATE spaces SET head_commit_id = ?, updated_at = ? WHERE id = ?",
            (commit_id, time.time(), space_id),
        )

    async def create_space(
        self,
        owner_user_id: str,
        slug: str,
        title: str,
        description: str = "",
        visibility: Visibility = Visibility.PRIVATE,
    ) -> Space:
        space_id = f"space_{uuid.uuid4().hex[:12]}"
        policy = PermissionPolicy(owner_user_id=owner_user_id, visibility=visibility)
        now = time.time()
        normalized_slug = self._normalize_space_slug(slug or title or "space")
        await self.git_store.create_space_repo(space_id)
        try:
            refs = await self.git_store.list_refs(space_id)
            head_commit_id = refs[0].commit_id if refs else ""
            with self._connect() as conn:
                candidate_slug = normalized_slug
                while True:
                    try:
                        conn.execute(
                            """
                            INSERT INTO spaces (
                                id, owner_user_id, slug, title, description, visibility, default_ref,
                                head_commit_id, policy_json, metadata_json, created_at, updated_at
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                space_id,
                                owner_user_id,
                                candidate_slug,
                                title,
                                description,
                                visibility.value,
                                self.git_store.config.default_branch,
                                head_commit_id,
                                self._policy_to_json(policy),
                                self._json_dumps({}),
                                now,
                                now,
                            ),
                        )
                        break
                    except sqlite3.IntegrityError as exc:
                        if "spaces.owner_user_id, spaces.slug" not in str(exc):
                            raise
                        candidate_slug = self._ensure_unique_space_slug(
                            conn,
                            owner_user_id,
                            normalized_slug,
                        )
                row = self._get_space_row(conn, space_id)
        except Exception:
            await self.git_store.delete_space_repo(space_id)
            raise
        if row is None:
            raise RuntimeError(f"Failed to create space '{space_id}'")
        return self._space_from_row(row)

    async def get_space(self, space_id: str) -> Optional[Space]:
        with self._connect() as conn:
            row = self._get_space_row(conn, space_id)
        return self._space_from_row(row) if row is not None else None

    async def list_owned_spaces(self, owner_user_id: str) -> List[Space]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM spaces WHERE owner_user_id = ? ORDER BY updated_at DESC",
                (owner_user_id,),
            ).fetchall()
        return [self._space_from_row(row) for row in rows]

    async def list_accessible_spaces(self, user_id: str) -> List[Space]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM spaces ORDER BY updated_at DESC",
            ).fetchall()
        spaces: List[Space] = []
        for row in rows:
            if await self._space_has_capability(user_id, row, Capability.READ):
                spaces.append(self._space_from_row(row))
        return spaces

    async def update_space(self, space_id: str, **fields) -> Space:
        allowed = {"slug", "title", "description", "visibility", "default_ref", "metadata"}
        updates = {k: v for k, v in fields.items() if k in allowed}
        with self._connect() as conn:
            row = self._require_space(conn, space_id)
            metadata = updates.get("metadata", json.loads(row["metadata_json"]) if row["metadata_json"] else {})
            visibility = updates.get("visibility", row["visibility"])
            visibility_value = visibility.value if isinstance(visibility, Visibility) else visibility
            next_slug = self._ensure_unique_space_slug(
                conn,
                row["owner_user_id"],
                str(updates.get("slug", row["slug"]) or row["slug"]),
                exclude_space_id=space_id,
            )
            policy = self._policy_from_json(
                row["policy_json"],
                row["owner_user_id"],
                Visibility(row["visibility"]),
            )
            policy.visibility = Visibility(visibility_value)
            conn.execute(
                """
                UPDATE spaces
                SET slug = ?, title = ?, description = ?, visibility = ?,
                    default_ref = ?, policy_json = ?, metadata_json = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    next_slug,
                    updates.get("title", row["title"]),
                    updates.get("description", row["description"]),
                    visibility_value,
                    updates.get("default_ref", row["default_ref"]),
                    self._policy_to_json(policy),
                    self._json_dumps(metadata),
                    time.time(),
                    space_id,
                ),
            )
            row = self._get_space_row(conn, space_id)
        if row is None:
            raise RuntimeError(f"Failed to update space '{space_id}'")
        return self._space_from_row(row)

    async def delete_space(self, space_id: str) -> bool:
        with self._connect() as conn:
            row = self._get_space_row(conn, space_id)
            if row is None:
                return False
            conn.execute("DELETE FROM space_assets WHERE space_id = ?", (space_id,))
            conn.execute("DELETE FROM spaces WHERE id = ?", (space_id,))
        await self.git_store.delete_space_repo(space_id)
        return True

    async def set_space_policy(self, space_id: str, policy: PermissionPolicy) -> Space:
        with self._connect() as conn:
            self._require_space(conn, space_id)
            conn.execute(
                "UPDATE spaces SET visibility = ?, policy_json = ?, updated_at = ? WHERE id = ?",
                (policy.visibility.value, self._policy_to_json(policy), time.time(), space_id),
            )
            row = self._get_space_row(conn, space_id)
        if row is None:
            raise RuntimeError(f"Failed to update policy for '{space_id}'")
        return self._space_from_row(row)

    async def fork_space(
        self, source_space_id: str, new_owner_user_id: str, slug: str, title: str = ""
    ) -> Space:
        with self._connect() as conn:
            source_row = self._require_space(conn, source_space_id)
            await self._ensure_space_access(new_owner_user_id, source_row, Capability.READ)
            source = self._space_from_row(source_row)
        forked = await self.create_space(
            owner_user_id=new_owner_user_id,
            slug=slug,
            title=title or f"{source.title} (fork)",
            description=source.description,
            visibility=Visibility.PRIVATE,
        )
        await self.git_store.delete_space_repo(forked.id)
        await self.git_store.clone_space_repo(source_space_id, forked.id)
        refs = await self.git_store.list_refs(forked.id)
        head_commit_id = refs[0].commit_id if refs else ""
        with self._connect() as conn:
            source_assets = conn.execute(
                "SELECT * FROM space_assets WHERE space_id = ?",
                (source_space_id,),
            ).fetchall()
            self._update_space_head(conn, forked.id, head_commit_id)
            metadata = source.metadata.copy()
            metadata["forked_from_space_id"] = source_space_id
            conn.execute(
                "UPDATE spaces SET metadata_json = ? WHERE id = ?",
                (self._json_dumps(metadata), forked.id),
            )
            for row in source_assets:
                now = time.time()
                asset_policy = self._policy_from_json(
                    row["policy_json"],
                    row["owner_user_id"],
                    Visibility(row["visibility"]),
                )
                asset_policy.owner_user_id = new_owner_user_id
                conn.execute(
                    """
                    INSERT INTO space_assets (
                        id, space_id, path, kind, owner_user_id, title, description, visibility,
                        versioned, executable, size_bytes, content_hash, latest_commit_id,
                        policy_json, metadata_json, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        uuid.uuid4().hex[:16],
                        forked.id,
                        row["path"],
                        row["kind"],
                        new_owner_user_id,
                        row["title"],
                        row["description"],
                        row["visibility"],
                        row["versioned"],
                        row["executable"],
                        row["size_bytes"],
                        row["content_hash"],
                        head_commit_id or row["latest_commit_id"],
                        self._policy_to_json(asset_policy),
                        row["metadata_json"],
                        now,
                        now,
                    ),
                )
        reloaded = await self.get_space(forked.id)
        if reloaded is None:
            raise RuntimeError(f"Failed to fork space '{source_space_id}'")
        return reloaded

    async def list_assets(
        self, user_id: str, space_id: str, ref: str = "main", prefix: str = ""
    ) -> List[SpaceAsset]:
        with self._connect() as conn:
            space_row = self._require_space(conn, space_id)
            await self._ensure_space_access(user_id, space_row, Capability.READ)
            db_rows = conn.execute(
                "SELECT * FROM space_assets WHERE space_id = ?",
                (space_id,),
            ).fetchall()
            db_map = {row["path"]: self._asset_from_row(row) for row in db_rows}
        prefix_norm = self._normalize_relpath(prefix) if prefix else ""
        assets: List[SpaceAsset] = []
        paths = await self.git_store.list_paths(space_id, ref=ref, prefix=prefix_norm)
        for raw_path in paths:
            existing = db_map.get(raw_path)
            if existing is None:
                content = await self.git_store.read_bytes(space_id, raw_path, ref=ref)
                existing = SpaceAsset(
                    id=uuid.uuid4().hex[:16],
                    space_id=space_id,
                    path=raw_path,
                    kind=self._infer_kind(raw_path),
                    owner_user_id=space_row["owner_user_id"],
                    visibility=Visibility(space_row["visibility"]),
                    size_bytes=len(content),
                    content_hash=hashlib.sha256(content).hexdigest(),
                    latest_commit_id=space_row["head_commit_id"],
                    policy=self._policy_from_json(
                        None,
                        space_row["owner_user_id"],
                        Visibility(space_row["visibility"]),
                    ),
            )
            if await self._asset_has_capability(user_id, existing, space_row, Capability.READ):
                assets.append(existing)
        assets.sort(key=lambda item: item.path)
        return assets

    async def get_asset(
        self, user_id: str, space_id: str, path: str, ref: str = "main"
    ) -> Optional[SpaceAsset]:
        rel = self._normalize_relpath(path)
        assets = await self.list_assets(user_id, space_id, ref=ref, prefix=rel)
        for asset in assets:
            if asset.path == rel:
                return asset
        return None

    async def read_asset(
        self, user_id: str, space_id: str, path: str, ref: str = "main"
    ) -> bytes:
        rel = self._normalize_relpath(path)
        with self._connect() as conn:
            space_row = self._require_space(conn, space_id)
            await self._ensure_space_access(user_id, space_row, Capability.READ)
            asset_row = self._get_asset_row(conn, space_id, rel)
            if asset_row is not None:
                asset = self._asset_from_row(asset_row)
                if not await self._asset_has_capability(user_id, asset, space_row, Capability.READ):
                    raise PermissionError(
                        f"User '{user_id}' does not have 'read' on asset '{space_id}:{rel}'"
                    )
        return await self.git_store.read_bytes(space_id, rel, ref=ref)

    async def write_asset(
        self,
        user_id: str,
        space_id: str,
        asset: SpaceAsset,
        content: bytes,
        message: str = "",
        ref: str = "main",
    ) -> SpaceCommit:
        rel = self._normalize_relpath(asset.path)
        with self._connect() as conn:
            space_row = self._require_space(conn, space_id)
            existing_row = self._get_asset_row(conn, space_id, rel)
            existing_asset = self._asset_from_row(existing_row) if existing_row is not None else None
            if existing_asset is None:
                await self._ensure_space_access(user_id, space_row, Capability.WRITE)
            elif not await self._asset_has_capability(user_id, existing_asset, space_row, Capability.WRITE):
                raise PermissionError(
                    f"User '{user_id}' does not have 'write' on asset '{space_id}:{rel}'"
                )
        commit = await self.git_store.write_bytes(
            space_id=space_id,
            path=rel,
            content=content,
            message=message,
            author_user_id=user_id,
            ref=ref,
        )
        with self._connect() as conn:
            stored = SpaceAsset(
                id=existing_asset.id if existing_asset else asset.id,
                space_id=space_id,
                path=rel,
                kind=asset.kind if asset.kind != AssetKind.OTHER else self._infer_kind(rel, existing_asset),
                owner_user_id=space_row["owner_user_id"],
                title=asset.title or (existing_asset.title if existing_asset else ""),
                description=asset.description or (existing_asset.description if existing_asset else ""),
                visibility=asset.visibility if asset.visibility else (existing_asset.visibility if existing_asset else Visibility(space_row["visibility"])),
                versioned=asset.versioned if asset.versioned is not None else True,
                executable=asset.executable if asset.executable is not None else (existing_asset.executable if existing_asset else False),
                size_bytes=len(content),
                content_hash=hashlib.sha256(content).hexdigest(),
                latest_commit_id=commit.id,
                policy=asset.policy or (existing_asset.policy if existing_asset else None),
                created_at=existing_asset.created_at if existing_asset else time.time(),
                metadata=asset.metadata or (existing_asset.metadata if existing_asset else {}),
            )
            self._upsert_asset(conn, stored)
            self._update_space_head(conn, space_id, commit.id)
        return commit

    async def delete_asset(
        self, user_id: str, space_id: str, path: str, message: str = "", ref: str = "main"
    ) -> SpaceCommit:
        rel = self._normalize_relpath(path)
        with self._connect() as conn:
            space_row = self._require_space(conn, space_id)
            existing_row = self._get_asset_row(conn, space_id, rel)
            if existing_row is None:
                await self._ensure_space_access(user_id, space_row, Capability.DELETE)
            else:
                existing_asset = self._asset_from_row(existing_row)
                if not await self._asset_has_capability(
                    user_id,
                    existing_asset,
                    space_row,
                    Capability.DELETE,
                ):
                    raise PermissionError(
                        f"User '{user_id}' does not have 'delete' on asset '{space_id}:{rel}'"
                    )
        commit = await self.git_store.delete_path(
            space_id=space_id,
            path=rel,
            message=message,
            author_user_id=user_id,
            ref=ref,
        )
        with self._connect() as conn:
            conn.execute("DELETE FROM space_assets WHERE space_id = ? AND path = ?", (space_id, rel))
            self._update_space_head(conn, space_id, commit.id)
        return commit

    async def list_refs(self, space_id: str) -> List[SpaceRef]:
        return await self.git_store.list_refs(space_id)

    async def create_ref(
        self, space_id: str, name: str, kind: RefKind, from_ref: str = "main"
    ) -> SpaceRef:
        return await self.git_store.create_ref(space_id, name, kind, from_ref=from_ref)

    async def delete_ref(self, space_id: str, name: str) -> bool:
        return await self.git_store.delete_ref(space_id, name)

    async def get_history(
        self, space_id: str, path: str = "", limit: int = 20
    ) -> List[SpaceCommit]:
        return await self.git_store.get_history(space_id, path=path, limit=limit)

    async def get_commit(self, space_id: str, commit_id: str) -> Optional[SpaceCommit]:
        return await self.git_store.get_commit(space_id, commit_id)
