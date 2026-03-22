# providers_impl/local_data.py — Filesystem-backed data provider for development.
#
# Each user gets a directory under a root path.  "Repos" are subdirectories.
# Versioning is simulated with a _history.json metadata file per repo
# (not real git — just enough for the interface contract).
# Locks are advisory, stored in _locks.json at the root.
#
# NOT for production — no atomic writes, no real branching, no merge.

from __future__ import annotations

import json
import os
import shutil
import time
import uuid
from typing import Dict, List, Optional

from providers.data   import DataProvider
from providers.models import Commit, FileEntry, Lock, Repo


class LocalFSDataProvider(DataProvider):
    """Plain-filesystem data provider for local development."""

    def __init__(self, root: str = "storage/repos"):
        self._root = os.path.abspath(root)
        os.makedirs(self._root, exist_ok=True)
        self._locks_path = os.path.join(self._root, "_locks.json")
        self._meta_path  = os.path.join(self._root, "_repos.json")
        self._meta  = self._load_json(self._meta_path, {})
        self._locks = self._load_json(self._locks_path, {})

    # ── Helpers ──────────────────────────────────────────────────

    @staticmethod
    def _load_json(path: str, default):
        if os.path.exists(path):
            with open(path) as f:
                return json.load(f)
        return default

    def _save_meta(self):
        with open(self._meta_path, "w") as f:
            json.dump(self._meta, f, indent=2)

    def _save_locks(self):
        with open(self._locks_path, "w") as f:
            json.dump(self._locks, f, indent=2)

    def _repo_dir(self, user_id: str, name: str) -> str:
        return os.path.join(self._root, user_id, name)

    def _repo_key(self, user_id: str, name: str) -> str:
        return f"{user_id}/{name}"

    def _history_path(self, user_id: str, name: str) -> str:
        return os.path.join(self._repo_dir(user_id, name), "_history.json")

    def _append_commit(self, user_id: str, repo: str, files: list, message: str) -> Commit:
        hpath = self._history_path(user_id, repo)
        history = self._load_json(hpath, [])
        commit = Commit(
            id=uuid.uuid4().hex[:8],
            message=message or "update",
            author_id=user_id,
            timestamp=time.time(),
            files=files,
        )
        history.append({
            "id": commit.id, "message": commit.message,
            "author_id": commit.author_id, "timestamp": commit.timestamp,
            "files": commit.files,
        })
        os.makedirs(os.path.dirname(hpath), exist_ok=True)
        with open(hpath, "w") as f:
            json.dump(history, f, indent=2)
        return commit

    # ── Repository management ────────────────────────────────────

    async def create_repo(self, user_id: str, name: str, private: bool = True, description: str = "") -> Repo:
        key = self._repo_key(user_id, name)
        if key in self._meta:
            raise ValueError(f"Repo '{key}' already exists")
        repo_dir = self._repo_dir(user_id, name)
        os.makedirs(repo_dir, exist_ok=True)
        repo = Repo(name=name, owner_id=user_id, private=private,
                     description=description, created_at=time.time())
        self._meta[key] = {
            "name": name, "owner_id": user_id, "private": private,
            "description": description, "created_at": repo.created_at,
        }
        self._save_meta()
        return repo

    async def delete_repo(self, user_id: str, name: str) -> bool:
        key = self._repo_key(user_id, name)
        if key not in self._meta:
            return False
        repo_dir = self._repo_dir(user_id, name)
        if os.path.exists(repo_dir):
            shutil.rmtree(repo_dir)
        del self._meta[key]
        self._save_meta()
        return True

    async def get_repo(self, user_id: str, name: str) -> Optional[Repo]:
        d = self._meta.get(self._repo_key(user_id, name))
        if not d:
            return None
        return Repo(**{k: d[k] for k in ("name", "owner_id", "private", "description", "created_at") if k in d})

    async def list_repos(self, user_id: str) -> List[Repo]:
        return [
            Repo(**{k: d[k] for k in ("name", "owner_id", "private", "description", "created_at") if k in d})
            for d in self._meta.values() if d["owner_id"] == user_id
        ]

    async def list_accessible_repos(self, user_id: str) -> List[Repo]:
        result = []
        for d in self._meta.values():
            if d["owner_id"] == user_id or not d.get("private", True):
                result.append(Repo(**{k: d[k] for k in ("name", "owner_id", "private", "description", "created_at") if k in d}))
        return result

    # ── File operations ──────────────────────────────────────────

    async def read_file(self, user_id: str, repo: str, path: str, ref: str = "main") -> bytes:
        fpath = os.path.join(self._repo_dir(user_id, repo), path)
        if not os.path.isfile(fpath):
            raise FileNotFoundError(f"{user_id}/{repo}/{path}")
        with open(fpath, "rb") as f:
            return f.read()

    async def write_file(self, user_id: str, repo: str, path: str, content: bytes,
                         message: str = "", ref: str = "main") -> Commit:
        fpath = os.path.join(self._repo_dir(user_id, repo), path)
        os.makedirs(os.path.dirname(fpath), exist_ok=True)
        with open(fpath, "wb") as f:
            f.write(content)
        return self._append_commit(user_id, repo, [path], message or f"write {path}")

    async def delete_file(self, user_id: str, repo: str, path: str,
                          message: str = "", ref: str = "main") -> Commit:
        fpath = os.path.join(self._repo_dir(user_id, repo), path)
        if os.path.exists(fpath):
            os.remove(fpath)
        return self._append_commit(user_id, repo, [path], message or f"delete {path}")

    async def list_files(self, user_id: str, repo: str, path: str = "", ref: str = "main") -> List[FileEntry]:
        base = os.path.join(self._repo_dir(user_id, repo), path)
        if not os.path.isdir(base):
            return []
        entries = []
        for name in sorted(os.listdir(base)):
            if name.startswith("_") and name.endswith(".json"):
                continue  # skip metadata files
            full = os.path.join(base, name)
            rel  = os.path.join(path, name) if path else name
            stat = os.stat(full)
            entries.append(FileEntry(
                path=rel, size=stat.st_size,
                is_dir=os.path.isdir(full),
                last_modified=stat.st_mtime,
            ))
        return entries

    async def file_exists(self, user_id: str, repo: str, path: str, ref: str = "main") -> bool:
        return os.path.exists(os.path.join(self._repo_dir(user_id, repo), path))

    # ── Versioning ───────────────────────────────────────────────

    async def get_history(self, user_id: str, repo: str, path: str = "", limit: int = 20) -> List[Commit]:
        history = self._load_json(self._history_path(user_id, repo), [])
        if path:
            history = [h for h in history if path in h.get("files", [])]
        return [
            Commit(id=h["id"], message=h["message"], author_id=h["author_id"],
                   timestamp=h["timestamp"], files=h.get("files", []))
            for h in history[-limit:]
        ]

    async def read_file_at(self, user_id: str, repo: str, path: str, commit_id: str) -> bytes:
        # Local FS doesn't have real versioning — just read current
        return await self.read_file(user_id, repo, path)

    # ── Branches (stubs — local FS has no branching) ─────────────

    async def list_branches(self, user_id: str, repo: str) -> List[str]:
        return ["main"]

    async def create_branch(self, user_id: str, repo: str, name: str, from_ref: str = "main") -> bool:
        return True  # no-op for local FS

    async def delete_branch(self, user_id: str, repo: str, name: str) -> bool:
        return name != "main"

    # ── Sharing (stubs — local FS uses meta flags) ───────────────

    async def share_repo(self, owner_id: str, repo: str, target_user_id: str, access: str = "read") -> bool:
        key = self._repo_key(owner_id, repo)
        meta = self._meta.get(key)
        if not meta:
            return False
        shares = meta.setdefault("shares", {})
        shares[target_user_id] = access
        self._save_meta()
        return True

    async def unshare_repo(self, owner_id: str, repo: str, target_user_id: str) -> bool:
        key = self._repo_key(owner_id, repo)
        meta = self._meta.get(key)
        if not meta:
            return False
        shares = meta.get("shares", {})
        if target_user_id in shares:
            del shares[target_user_id]
            self._save_meta()
            return True
        return False

    async def set_repo_visibility(self, user_id: str, repo: str, private: bool) -> bool:
        key = self._repo_key(user_id, repo)
        if key in self._meta:
            self._meta[key]["private"] = private
            self._save_meta()
            return True
        return False

    # ── Locking ──────────────────────────────────────────────────

    def _lock_key(self, repo: str, path: str) -> str:
        return f"{repo}:{path}"

    def _expire_locks(self):
        now = time.time()
        expired = [k for k, v in self._locks.items()
                   if v.get("ttl", 0) > 0 and now - v.get("acquired_at", 0) > v["ttl"]]
        for k in expired:
            del self._locks[k]
        if expired:
            self._save_locks()

    async def lock(self, user_id: str, repo: str, path: str,
                   ttl: float = 300.0, execution_id: str = "") -> Lock:
        self._expire_locks()
        key = self._lock_key(repo, path)
        existing = self._locks.get(key)
        if existing and existing["holder_id"] != user_id:
            raise ValueError(f"Path '{repo}/{path}' is locked by user '{existing['holder_id']}'")
        lock_data = {
            "path": path, "repo": repo, "holder_id": user_id,
            "execution_id": execution_id,
            "acquired_at": time.time(), "ttl": ttl,
        }
        self._locks[key] = lock_data
        self._save_locks()
        return Lock(**lock_data)

    async def unlock(self, user_id: str, repo: str, path: str) -> bool:
        key = self._lock_key(repo, path)
        if key in self._locks and self._locks[key]["holder_id"] == user_id:
            del self._locks[key]
            self._save_locks()
            return True
        return False

    async def get_lock(self, repo: str, path: str) -> Optional[Lock]:
        self._expire_locks()
        d = self._locks.get(self._lock_key(repo, path))
        return Lock(**d) if d else None

    async def list_locks(self, repo: str) -> List[Lock]:
        self._expire_locks()
        return [Lock(**d) for d in self._locks.values() if d["repo"] == repo]

    async def force_unlock(self, repo: str, path: str) -> bool:
        key = self._lock_key(repo, path)
        if key in self._locks:
            del self._locks[key]
            self._save_locks()
            return True
        return False
