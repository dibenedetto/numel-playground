"""Low-level Git-backed store for versioned space content."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Dict, List, Optional

from domain.models import RefKind, SpaceCommit, SpaceRef

from .config import GitStorageConfig
from .support import ScaffoldComponent


class GitSpaceStore(ScaffoldComponent):
    """Manage one Git repository per space."""

    def __init__(self, config: GitStorageConfig):
        self.config = config
        self._repos_root = Path(config.repos_root).resolve()
        self._repos_root.mkdir(parents=True, exist_ok=True)

    def _repo_dir(self, space_id: str) -> Path:
        return (self._repos_root / space_id).resolve()

    def _ensure_repo_path(self, repo_dir: Path) -> None:
        if self._repos_root not in (repo_dir, *repo_dir.parents):
            raise ValueError(f"Repo path escapes configured root: {repo_dir}")

    def _normalize_relpath(self, path: str) -> str:
        rel = path.replace("\\", "/").strip("/")
        if not rel or rel.startswith("../") or "/../" in f"/{rel}/":
            raise ValueError(f"Invalid asset path: {path!r}")
        return rel

    def _git(self, repo_dir: Path, *args: str, capture_output: bool = True) -> str:
        self._ensure_repo_path(repo_dir)
        proc = subprocess.run(
            ["git", "-c", f"safe.directory={repo_dir.as_posix()}", *args],
            cwd=str(repo_dir),
            check=True,
            text=True,
            capture_output=capture_output,
        )
        return proc.stdout.strip() if capture_output else ""

    def _git_bin(self, repo_dir: Path, *args: str) -> bytes:
        self._ensure_repo_path(repo_dir)
        proc = subprocess.run(
            ["git", "-c", f"safe.directory={repo_dir.as_posix()}", *args],
            cwd=str(repo_dir),
            check=True,
            capture_output=True,
        )
        return proc.stdout

    def _require_repo(self, space_id: str) -> Path:
        repo_dir = self._repo_dir(space_id)
        if not (repo_dir / ".git").exists():
            raise FileNotFoundError(f"Space repo '{space_id}' not found")
        return repo_dir

    def _commit_from_id(self, space_id: str, commit_id: str) -> Optional[SpaceCommit]:
        repo_dir = self._require_repo(space_id)
        try:
            info = self._git(
                repo_dir,
                "show",
                "-s",
                "--format=%H%n%P%n%ct%n%an%n%s",
                commit_id,
            )
        except subprocess.CalledProcessError:
            return None
        parts = info.splitlines()
        if len(parts) != 5:
            return None
        commit_hash, parents, ts, author, message = parts
        changed = self._git(repo_dir, "show", "--pretty=", "--name-only", commit_hash)
        tree_hash = self._git(repo_dir, "rev-parse", f"{commit_hash}^{{tree}}")
        return SpaceCommit(
            id=commit_hash,
            space_id=space_id,
            author_user_id=author,
            message=message,
            created_at=float(ts or 0.0),
            parent_ids=[p for p in parents.split() if p],
            changed_paths=[line.strip() for line in changed.splitlines() if line.strip()],
            tree_hash=tree_hash,
        )

    def _commit_or_head(
        self,
        repo_dir: Path,
        *,
        space_id: str,
        author_user_id: str,
        message: str,
    ) -> SpaceCommit:
        try:
            self._git(
                repo_dir,
                "-c",
                f"user.name={author_user_id}",
                "-c",
                f"user.email={author_user_id}@numel.local",
                "commit",
                "-m",
                message,
            )
        except subprocess.CalledProcessError as exc:
            combined = ((exc.stderr or "") + (exc.stdout or "")).lower()
            if "nothing to commit" not in combined and "nothing added to commit" not in combined:
                raise
        commit_id = self._git(repo_dir, "rev-parse", "HEAD")
        commit = self._commit_from_id(space_id, commit_id)
        if commit is None:
            raise RuntimeError(f"Unable to load commit '{commit_id}'")
        return commit

    async def create_space_repo(self, space_id: str) -> None:
        repo_dir = self._repo_dir(space_id)
        self._ensure_repo_path(repo_dir)
        repo_dir.mkdir(parents=True, exist_ok=True)
        if (repo_dir / ".git").exists():
            return
        self._git(repo_dir, "init", "-b", self.config.default_branch)
        self._git(
            repo_dir,
            "-c",
            "user.name=numel",
            "-c",
            "user.email=numel@local",
            "commit",
            "--allow-empty",
            "-m",
            "Initialize space",
        )

    async def delete_space_repo(self, space_id: str) -> None:
        repo_dir = self._repo_dir(space_id)
        if not repo_dir.exists():
            return
        self._ensure_repo_path(repo_dir)
        shutil.rmtree(repo_dir)

    async def clone_space_repo(self, source_space_id: str, target_space_id: str) -> None:
        source_dir = self._require_repo(source_space_id)
        target_dir = self._repo_dir(target_space_id)
        self._ensure_repo_path(target_dir)
        if target_dir.exists():
            raise ValueError(f"Target space repo '{target_space_id}' already exists")
        target_dir.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["git", "clone", "--quiet", "--no-hardlinks", str(source_dir), str(target_dir)],
            check=True,
            capture_output=True,
            text=True,
        )

    async def list_refs(self, space_id: str) -> List[SpaceRef]:
        repo_dir = self._require_repo(space_id)
        refs_out = self._git(
            repo_dir,
            "for-each-ref",
            "--format=%(refname)|%(objectname)|%(creatordate:unix)",
            "refs/heads",
            "refs/tags",
        )
        refs: List[SpaceRef] = []
        for line in refs_out.splitlines():
            if not line.strip():
                continue
            parts = line.split("|", 2)
            if len(parts) != 3:
                continue
            refname, commit_id, ts = parts
            if refname.startswith("refs/heads/"):
                name = refname[len("refs/heads/"):]
                kind = RefKind.BRANCH
            elif refname.startswith("refs/tags/"):
                name = refname[len("refs/tags/"):]
                kind = RefKind.TAG
            else:
                continue
            created_at = float(ts or 0.0)
            refs.append(
                SpaceRef(
                    space_id=space_id,
                    name=name,
                    kind=kind,
                    commit_id=commit_id,
                    created_at=created_at,
                    updated_at=created_at,
                )
            )
        refs.sort(key=lambda item: (item.kind.value, item.name))
        return refs

    async def create_ref(
        self, space_id: str, name: str, kind: str, from_ref: str = "main"
    ) -> SpaceRef:
        repo_dir = self._require_repo(space_id)
        ref_kind = kind if isinstance(kind, RefKind) else RefKind(kind)
        if ref_kind == RefKind.BRANCH:
            self._git(repo_dir, "branch", name, from_ref)
        elif ref_kind == RefKind.TAG:
            self._git(repo_dir, "tag", name, from_ref)
        else:
            raise ValueError("Only branch and tag refs can be created")
        for ref in await self.list_refs(space_id):
            if ref.name == name and ref.kind == ref_kind:
                return ref
        raise RuntimeError(f"Failed to create ref '{name}'")

    async def delete_ref(self, space_id: str, name: str) -> bool:
        repo_dir = self._require_repo(space_id)
        if name == self.config.default_branch:
            return False
        try:
            self._git(repo_dir, "show-ref", "--verify", f"refs/heads/{name}")
            self._git(repo_dir, "branch", "-D", name)
            return True
        except subprocess.CalledProcessError:
            pass
        try:
            self._git(repo_dir, "show-ref", "--verify", f"refs/tags/{name}")
            self._git(repo_dir, "tag", "-d", name)
            return True
        except subprocess.CalledProcessError:
            return False

    async def read_bytes(self, space_id: str, path: str, ref: str = "main") -> bytes:
        repo_dir = self._require_repo(space_id)
        rel = self._normalize_relpath(path)
        try:
            return self._git_bin(repo_dir, "show", f"{ref}:{rel}")
        except subprocess.CalledProcessError as exc:
            raise FileNotFoundError(f"{space_id}:{ref}:{rel}") from exc

    async def write_bytes(
        self,
        space_id: str,
        path: str,
        content: bytes,
        message: str,
        author_user_id: str,
        ref: str = "main",
    ) -> SpaceCommit:
        repo_dir = self._require_repo(space_id)
        rel = self._normalize_relpath(path)
        active_branch = self._git(repo_dir, "rev-parse", "--abbrev-ref", "HEAD")
        switched = False
        if active_branch != ref:
            self._git(repo_dir, "checkout", ref)
            switched = True
        try:
            target = repo_dir / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
            self._git(repo_dir, "add", "--", rel)
            return self._commit_or_head(
                repo_dir,
                space_id=space_id,
                author_user_id=author_user_id,
                message=message or f"Update {rel}",
            )
        finally:
            if switched:
                self._git(repo_dir, "checkout", active_branch)

    async def delete_path(
        self,
        space_id: str,
        path: str,
        message: str,
        author_user_id: str,
        ref: str = "main",
    ) -> SpaceCommit:
        repo_dir = self._require_repo(space_id)
        rel = self._normalize_relpath(path)
        active_branch = self._git(repo_dir, "rev-parse", "--abbrev-ref", "HEAD")
        switched = False
        if active_branch != ref:
            self._git(repo_dir, "checkout", ref)
            switched = True
        try:
            target = repo_dir / rel
            if not target.exists():
                raise FileNotFoundError(f"{space_id}:{ref}:{rel}")
            if target.is_dir():
                shutil.rmtree(target)
            else:
                target.unlink()
            self._git(repo_dir, "add", "-A", "--", rel)
            return self._commit_or_head(
                repo_dir,
                space_id=space_id,
                author_user_id=author_user_id,
                message=message or f"Delete {rel}",
            )
        finally:
            if switched:
                self._git(repo_dir, "checkout", active_branch)

    async def list_paths(self, space_id: str, ref: str = "main", prefix: str = "") -> List[str]:
        repo_dir = self._require_repo(space_id)
        prefix_norm = self._normalize_relpath(prefix) if prefix else ""
        out = self._git(repo_dir, "ls-tree", "-r", "--name-only", ref)
        paths = [line.strip() for line in out.splitlines() if line.strip()]
        if not prefix_norm:
            return paths
        return [
            path for path in paths
            if path == prefix_norm or path.startswith(prefix_norm + "/")
        ]

    async def get_history(
        self, space_id: str, path: str = "", limit: int = 20, ref: str = "main"
    ) -> List[SpaceCommit]:
        repo_dir = self._require_repo(space_id)
        rel = self._normalize_relpath(path) if path else ""
        cmd = ["log", ref, f"-n{limit}", "--format=%H"]
        if rel:
            cmd.extend(["--", rel])
        commit_ids = self._git(repo_dir, *cmd)
        commits: List[SpaceCommit] = []
        for commit_id in [line.strip() for line in commit_ids.splitlines() if line.strip()]:
            commit = self._commit_from_id(space_id, commit_id)
            if commit:
                commits.append(commit)
        return commits

    async def get_commit(self, space_id: str, commit_id: str) -> Optional[SpaceCommit]:
        return self._commit_from_id(space_id, commit_id)

    async def compare_snapshots(
        self,
        space_id: str,
        left: str,
        right: str,
        path: str = "",
        limit: int = 200,
    ) -> Dict[str, object]:
        repo_dir = self._require_repo(space_id)
        left_selector = str(left or "").strip()
        right_selector = str(right or "").strip()
        if not left_selector or not right_selector:
            raise ValueError("Both left and right selectors are required")
        limit = max(1, min(int(limit or 200), 1000))
        try:
            left_commit_id = self._git(repo_dir, "rev-parse", left_selector)
            right_commit_id = self._git(repo_dir, "rev-parse", right_selector)
        except subprocess.CalledProcessError as exc:
            raise ValueError(f"Unknown ref or commit in comparison: {left_selector} vs {right_selector}") from exc
        rel = self._normalize_relpath(path) if path else ""
        diff_cmd = [
            "diff",
            "--name-status",
            "--find-renames",
            "--find-copies",
            left_commit_id,
            right_commit_id,
        ]
        if rel:
            diff_cmd.extend(["--", rel])
        diff_out = self._git(repo_dir, *diff_cmd)
        entries: List[Dict[str, object]] = []
        counts = {
            "added": 0,
            "modified": 0,
            "deleted": 0,
            "renamed": 0,
            "copied": 0,
            "other": 0,
        }
        for line in diff_out.splitlines():
            if not line.strip():
                continue
            parts = [part.strip() for part in line.split("\t") if part.strip()]
            if not parts:
                continue
            raw_status = parts[0]
            kind = (raw_status[:1] or "M").upper()
            status = {
                "A": "added",
                "M": "modified",
                "D": "deleted",
                "R": "renamed",
                "C": "copied",
            }.get(kind, "other")
            entry: Dict[str, object] = {
                "status": status,
                "raw_status": raw_status,
            }
            if status in {"renamed", "copied"} and len(parts) >= 3:
                entry["old_path"] = parts[1]
                entry["path"] = parts[2]
            elif len(parts) >= 2:
                entry["path"] = parts[1]
            counts[status] = int(counts.get(status, 0) or 0) + 1
            entries.append(entry)
        total = len(entries)
        truncated = total > limit
        left_commit = self._commit_from_id(space_id, left_commit_id)
        right_commit = self._commit_from_id(space_id, right_commit_id)
        return {
            "left": {
                "selector": left_selector,
                "commit_id": left_commit_id,
                "commit": left_commit,
            },
            "right": {
                "selector": right_selector,
                "commit_id": right_commit_id,
                "commit": right_commit,
            },
            "path": rel,
            "changed_paths": entries[:limit],
            "summary": {
                **counts,
                "total": total,
                "truncated": truncated,
            },
            "has_changes": total > 0,
        }

    async def restore_snapshot(
        self,
        space_id: str,
        source: str,
        target_ref: str = "main",
        author_user_id: str = "numel",
        message: str = "",
    ) -> SpaceCommit:
        repo_dir = self._require_repo(space_id)
        source_selector = str(source or "").strip()
        target_branch = str(target_ref or "").strip()
        if not source_selector:
            raise ValueError("source is required")
        if not target_branch:
            raise ValueError("target_ref is required")
        try:
            self._git(repo_dir, "show-ref", "--verify", f"refs/heads/{target_branch}")
            source_commit_id = self._git(repo_dir, "rev-parse", source_selector)
        except subprocess.CalledProcessError as exc:
            raise ValueError(f"Unknown branch or commit for restore: {target_branch} <- {source_selector}") from exc
        active_branch = self._git(repo_dir, "rev-parse", "--abbrev-ref", "HEAD")
        switched = False
        if active_branch != target_branch:
            self._git(repo_dir, "checkout", target_branch)
            switched = True
        try:
            current_paths = set(await self.list_paths(space_id, ref=target_branch))
            source_paths = set(await self.list_paths(space_id, ref=source_commit_id))
            for rel in sorted(current_paths - source_paths, reverse=True):
                target = repo_dir / rel
                if target.exists():
                    if target.is_dir():
                        shutil.rmtree(target)
                    else:
                        target.unlink()
            for rel in sorted(source_paths):
                target = repo_dir / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(await self.read_bytes(space_id, rel, ref=source_commit_id))
            self._git(repo_dir, "add", "-A")
            commit_message = message or f"Restore {target_branch} from {source_selector}"
            return self._commit_or_head(
                repo_dir,
                space_id=space_id,
                author_user_id=author_user_id,
                message=commit_message,
            )
        finally:
            if switched:
                self._git(repo_dir, "checkout", active_branch)

    async def materialize_ref(self, space_id: str, ref: str, target_dir: str) -> str:
        target = Path(target_dir).resolve()
        if target.exists() and any(target.iterdir()):
            raise ValueError(f"Target directory is not empty: {target}")
        target.mkdir(parents=True, exist_ok=True)
        for rel in await self.list_paths(space_id, ref=ref):
            destination = (target / rel).resolve()
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(await self.read_bytes(space_id, rel, ref=ref))
        return str(target)
