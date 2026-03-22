# providers_impl/none_auth.py — No-auth provider (single-user mode).
#
# All operations succeed.  No tokens, no passwords, no restrictions.
# This is the default when auth is not configured, preserving the
# current single-user Numel experience.

from __future__ import annotations

from typing import List, Optional

from providers.auth   import AuthProvider
from providers.models import AccessLevel, Permission, Quota, Role, User

_SINGLE_USER = User(
    id="local", username="local", email="local@localhost",
    role=Role.ADMIN, active=True,
)

_UNLIMITED_QUOTA = Quota(
    user_id="local",
    cpu_seconds_remaining=float("inf"),
    max_concurrent_runs=999,
    storage_bytes_remaining=2**40,
    max_loop_hours=float("inf"),
    gpu_hours_remaining=float("inf"),
    max_repos=9999,
)


class NoneAuthProvider(AuthProvider):
    """No authentication — single-user mode.  Everything is allowed."""

    async def authenticate(self, token: str) -> Optional[User]:
        return _SINGLE_USER

    async def login(self, username: str, password: str) -> Optional[str]:
        return "local-token"

    async def logout(self, token: str) -> bool:
        return True

    async def create_user(self, username: str, email: str, password: str) -> User:
        return _SINGLE_USER

    async def get_user(self, user_id: str) -> Optional[User]:
        return _SINGLE_USER

    async def get_user_by_username(self, username: str) -> Optional[User]:
        return _SINGLE_USER

    async def list_users(self, offset=0, limit=50, active_only=True) -> List[User]:
        return [_SINGLE_USER]

    async def update_user(self, user_id: str, **fields) -> User:
        return _SINGLE_USER

    async def delete_user(self, user_id: str) -> bool:
        return False

    async def get_quota(self, user_id: str) -> Quota:
        return _UNLIMITED_QUOTA

    async def update_quota(self, user_id: str, **fields) -> Quota:
        return _UNLIMITED_QUOTA

    async def debit_quota(self, user_id: str, cpu_seconds=0, storage_bytes=0) -> Quota:
        return _UNLIMITED_QUOTA

    async def check_permission(self, user_id: str, resource: str, action: AccessLevel) -> bool:
        return True

    async def grant_permission(self, user_id: str, resource: str, access: AccessLevel) -> Permission:
        return Permission(resource=resource, user_id=user_id, access=access)

    async def revoke_permission(self, user_id: str, resource: str) -> bool:
        return True

    async def list_permissions(self, user_id: str) -> List[Permission]:
        return []

    async def list_resource_permissions(self, resource: str) -> List[Permission]:
        return []
