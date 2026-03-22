# providers/data.py — Data repository interface.
#
# Models data storage as repositories containing files, with versioning,
# permissions, and advisory locks.
#
# Implementations: GiteaDataProvider, GitLabDataProvider,
#                  LocalFSDataProvider (dev/testing).

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional

from providers.models import Commit, FileEntry, Lock, Repo


class DataProvider(ABC):
    """Versioned data storage with per-repo permissions and locking."""

    # ── Repository management ────────────────────────────────────

    @abstractmethod
    async def create_repo(
        self, user_id: str, name: str, private: bool = True, description: str = ""
    ) -> Repo:
        """Create a new data repository owned by *user_id*."""

    @abstractmethod
    async def delete_repo(self, user_id: str, name: str) -> bool:
        """Delete a repo.  Returns True if it existed."""

    @abstractmethod
    async def get_repo(self, user_id: str, name: str) -> Optional[Repo]:
        """Repo metadata, or None."""

    @abstractmethod
    async def list_repos(self, user_id: str) -> List[Repo]:
        """All repos the user owns."""

    @abstractmethod
    async def list_accessible_repos(self, user_id: str) -> List[Repo]:
        """All repos the user can access (owned + shared + public)."""

    # ── File operations ──────────────────────────────────────────

    @abstractmethod
    async def read_file(
        self, user_id: str, repo: str, path: str, ref: str = "main"
    ) -> bytes:
        """Read file content.  *ref* is a branch or commit hash."""

    @abstractmethod
    async def write_file(
        self, user_id: str, repo: str, path: str, content: bytes,
        message: str = "", ref: str = "main"
    ) -> Commit:
        """Write (create or overwrite) a file.  Returns the new commit."""

    @abstractmethod
    async def delete_file(
        self, user_id: str, repo: str, path: str,
        message: str = "", ref: str = "main"
    ) -> Commit:
        """Delete a file.  Returns the new commit."""

    @abstractmethod
    async def list_files(
        self, user_id: str, repo: str, path: str = "", ref: str = "main"
    ) -> List[FileEntry]:
        """List directory contents.  Empty *path* = repo root."""

    @abstractmethod
    async def file_exists(
        self, user_id: str, repo: str, path: str, ref: str = "main"
    ) -> bool:
        """Check if a file exists without reading it."""

    # ── Versioning ───────────────────────────────────────────────

    @abstractmethod
    async def get_history(
        self, user_id: str, repo: str, path: str = "", limit: int = 20
    ) -> List[Commit]:
        """Commit history for a file or entire repo."""

    @abstractmethod
    async def read_file_at(
        self, user_id: str, repo: str, path: str, commit_id: str
    ) -> bytes:
        """Read a file at a specific historical commit."""

    # ── Branches ─────────────────────────────────────────────────

    @abstractmethod
    async def list_branches(self, user_id: str, repo: str) -> List[str]:
        """List branch names."""

    @abstractmethod
    async def create_branch(
        self, user_id: str, repo: str, name: str, from_ref: str = "main"
    ) -> bool:
        """Create a new branch."""

    @abstractmethod
    async def delete_branch(self, user_id: str, repo: str, name: str) -> bool:
        """Delete a branch."""

    # ── Sharing ──────────────────────────────────────────────────

    @abstractmethod
    async def share_repo(
        self, owner_id: str, repo: str, target_user_id: str, access: str = "read"
    ) -> bool:
        """Grant another user access to a repo.  access: 'read' | 'write' | 'admin'."""

    @abstractmethod
    async def unshare_repo(
        self, owner_id: str, repo: str, target_user_id: str
    ) -> bool:
        """Revoke a user's access."""

    @abstractmethod
    async def set_repo_visibility(
        self, user_id: str, repo: str, private: bool
    ) -> bool:
        """Toggle public/private."""

    # ── Locking ──────────────────────────────────────────────────

    @abstractmethod
    async def lock(
        self, user_id: str, repo: str, path: str,
        ttl: float = 300.0, execution_id: str = ""
    ) -> Lock:
        """Acquire an advisory lock.  Raises if already locked by another user."""

    @abstractmethod
    async def unlock(
        self, user_id: str, repo: str, path: str
    ) -> bool:
        """Release a lock.  Returns True if it was held."""

    @abstractmethod
    async def get_lock(
        self, repo: str, path: str
    ) -> Optional[Lock]:
        """Check lock status without acquiring."""

    @abstractmethod
    async def list_locks(
        self, repo: str
    ) -> List[Lock]:
        """All active locks in a repo."""

    @abstractmethod
    async def force_unlock(
        self, repo: str, path: str
    ) -> bool:
        """Admin: break a lock regardless of holder."""
