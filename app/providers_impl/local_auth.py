# providers_impl/local_auth.py — File-backed auth for development.
#
# Stores users, quotas, and permissions in a single JSON file.
# Tokens are HMAC-signed JWTs (no external auth server needed).
# NOT for production — no rate limiting, no password hashing upgrades.

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
import uuid
from typing import Any, Dict, List, Optional

from providers.auth   import AuthProvider
from providers.models import AccessLevel, Permission, Quota, Role, User

_DEFAULT_SECRET = "numel-dev-secret-change-in-production"


class LocalAuthProvider(AuthProvider):
    """JSON-file-backed auth provider for local development."""

    def __init__(self, path: str = "users.json", secret: str = _DEFAULT_SECRET):
        self._path   = path
        self._secret = secret
        self._data   = self._load()

    # ── Persistence ──────────────────────────────────────────────

    def _load(self) -> Dict[str, Any]:
        if os.path.exists(self._path):
            with open(self._path) as f:
                return json.load(f)
        return {"users": {}, "quotas": {}, "permissions": {}, "tokens": {}}

    def _save(self):
        with open(self._path, "w") as f:
            json.dump(self._data, f, indent=2)

    def _user_from_dict(self, d: dict) -> User:
        return User(
            id=d["id"], username=d["username"], email=d["email"],
            role=Role(d.get("role", "user")),
            active=d.get("active", True),
            created_at=d.get("created_at", 0.0),
            metadata=d.get("metadata", {}),
        )

    # ── Token helpers ────────────────────────────────────────────

    def _make_token(self, user_id: str) -> str:
        payload  = f"{user_id}:{time.time()}"
        sig      = hmac.new(self._secret.encode(), payload.encode(), hashlib.sha256).hexdigest()[:16]
        token    = f"{payload}:{sig}"
        self._data["tokens"][token] = user_id
        self._save()
        return token

    def _verify_token(self, token: str) -> Optional[str]:
        return self._data.get("tokens", {}).get(token)

    # ── Authentication ───────────────────────────────────────────

    async def authenticate(self, token: str) -> Optional[User]:
        user_id = self._verify_token(token)
        if not user_id:
            return None
        return await self.get_user(user_id)

    async def login(self, username: str, password: str) -> Optional[str]:
        for u in self._data["users"].values():
            if u["username"] == username:
                pw_hash = hashlib.sha256(password.encode()).hexdigest()
                if u.get("password_hash") == pw_hash:
                    return self._make_token(u["id"])
                return None
        return None

    async def logout(self, token: str) -> bool:
        if token in self._data.get("tokens", {}):
            del self._data["tokens"][token]
            self._save()
            return True
        return False

    # ── User CRUD ────────────────────────────────────────────────

    async def create_user(self, username: str, email: str, password: str) -> User:
        for u in self._data["users"].values():
            if u["username"] == username:
                raise ValueError(f"Username '{username}' already exists")

        user_id = uuid.uuid4().hex[:12]
        # First user gets admin role automatically
        role = "admin" if not self._data["users"] else "user"
        user_dict = {
            "id":            user_id,
            "username":      username,
            "email":         email,
            "role":          role,
            "active":        True,
            "created_at":    time.time(),
            "password_hash": hashlib.sha256(password.encode()).hexdigest(),
            "metadata":      {},
        }
        self._data["users"][user_id] = user_dict

        # Default quota
        self._data["quotas"][user_id] = {
            "user_id":                 user_id,
            "cpu_seconds_remaining":   36000.0,
            "max_concurrent_runs":     5,
            "storage_bytes_remaining": 1_073_741_824,
            "max_loop_hours":          24.0,
            "gpu_hours_remaining":     0.0,
            "max_repos":               50,
        }

        self._save()
        return self._user_from_dict(user_dict)

    async def get_user(self, user_id: str) -> Optional[User]:
        d = self._data["users"].get(user_id)
        return self._user_from_dict(d) if d else None

    async def get_user_by_username(self, username: str) -> Optional[User]:
        for u in self._data["users"].values():
            if u["username"] == username:
                return self._user_from_dict(u)
        return None

    async def list_users(self, offset: int = 0, limit: int = 50, active_only: bool = True) -> List[User]:
        users = list(self._data["users"].values())
        if active_only:
            users = [u for u in users if u.get("active", True)]
        return [self._user_from_dict(u) for u in users[offset:offset + limit]]

    async def update_user(self, user_id: str, **fields) -> User:
        u = self._data["users"].get(user_id)
        if not u:
            raise ValueError(f"User '{user_id}' not found")
        for k in ("email", "role", "active", "metadata"):
            if k in fields:
                u[k] = fields[k]
        self._save()
        return self._user_from_dict(u)

    async def delete_user(self, user_id: str) -> bool:
        if user_id in self._data["users"]:
            self._data["users"][user_id]["active"] = False
            self._save()
            return True
        return False

    # ── Quotas ───────────────────────────────────────────────────

    async def get_quota(self, user_id: str) -> Quota:
        q = self._data["quotas"].get(user_id, {})
        return Quota(
            user_id=user_id,
            cpu_seconds_remaining=q.get("cpu_seconds_remaining", 36000.0),
            max_concurrent_runs=q.get("max_concurrent_runs", 5),
            storage_bytes_remaining=q.get("storage_bytes_remaining", 1_073_741_824),
            max_loop_hours=q.get("max_loop_hours", 24.0),
            gpu_hours_remaining=q.get("gpu_hours_remaining", 0.0),
            max_repos=q.get("max_repos", 50),
        )

    async def update_quota(self, user_id: str, **fields) -> Quota:
        q = self._data["quotas"].setdefault(user_id, {"user_id": user_id})
        for k, v in fields.items():
            if hasattr(Quota, k):
                q[k] = v
        self._save()
        return await self.get_quota(user_id)

    async def debit_quota(self, user_id: str, cpu_seconds: float = 0, storage_bytes: int = 0) -> Quota:
        q = self._data["quotas"].setdefault(user_id, {"user_id": user_id})
        remaining_cpu = q.get("cpu_seconds_remaining", 36000.0) - cpu_seconds
        remaining_storage = q.get("storage_bytes_remaining", 1_073_741_824) - storage_bytes
        if remaining_cpu < 0:
            raise ValueError("CPU quota exceeded")
        if remaining_storage < 0:
            raise ValueError("Storage quota exceeded")
        q["cpu_seconds_remaining"]    = remaining_cpu
        q["storage_bytes_remaining"]  = remaining_storage
        self._save()
        return await self.get_quota(user_id)

    # ── Permissions ──────────────────────────────────────────────

    def _perm_key(self, user_id: str, resource: str) -> str:
        return f"{user_id}:{resource}"

    async def check_permission(self, user_id: str, resource: str, action: AccessLevel) -> bool:
        # Owners have all permissions
        perm = self._data["permissions"].get(self._perm_key(user_id, resource))
        if not perm:
            return False
        level = AccessLevel(perm["access"])
        hierarchy = [AccessLevel.NONE, AccessLevel.READ, AccessLevel.WRITE,
                     AccessLevel.EXECUTE, AccessLevel.OWNER]
        return hierarchy.index(level) >= hierarchy.index(action)

    async def grant_permission(self, user_id: str, resource: str, access: AccessLevel) -> Permission:
        key = self._perm_key(user_id, resource)
        self._data["permissions"][key] = {
            "resource": resource, "user_id": user_id, "access": access.value
        }
        self._save()
        return Permission(resource=resource, user_id=user_id, access=access)

    async def revoke_permission(self, user_id: str, resource: str) -> bool:
        key = self._perm_key(user_id, resource)
        if key in self._data["permissions"]:
            del self._data["permissions"][key]
            self._save()
            return True
        return False

    async def list_permissions(self, user_id: str) -> List[Permission]:
        return [
            Permission(resource=p["resource"], user_id=p["user_id"], access=AccessLevel(p["access"]))
            for p in self._data["permissions"].values()
            if p["user_id"] == user_id
        ]

    async def list_resource_permissions(self, resource: str) -> List[Permission]:
        return [
            Permission(resource=p["resource"], user_id=p["user_id"], access=AccessLevel(p["access"]))
            for p in self._data["permissions"].values()
            if p["resource"] == resource
        ]
