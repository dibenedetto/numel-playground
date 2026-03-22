# providers/auth.py — Authentication & authorization interface.
#
# Implementations: DjangoAuthProvider, KeycloakAuthProvider,
#                  LocalAuthProvider (dev/testing).

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional

from providers.models import AccessLevel, Permission, Quota, User


class AuthProvider(ABC):
    """Authenticate users, manage quotas, check permissions."""

    # ── Authentication ───────────────────────────────────────────

    @abstractmethod
    async def authenticate(self, token: str) -> Optional[User]:
        """Validate a bearer token and return the associated user, or None."""

    @abstractmethod
    async def login(self, username: str, password: str) -> Optional[str]:
        """Verify credentials and return a bearer token, or None."""

    @abstractmethod
    async def logout(self, token: str) -> bool:
        """Invalidate a token.  Returns True if it was valid."""

    # ── User CRUD ────────────────────────────────────────────────

    @abstractmethod
    async def create_user(self, username: str, email: str, password: str) -> User:
        """Register a new user.  Raises ValueError on duplicate."""

    @abstractmethod
    async def get_user(self, user_id: str) -> Optional[User]:
        """Look up a user by ID."""

    @abstractmethod
    async def get_user_by_username(self, username: str) -> Optional[User]:
        """Look up a user by username."""

    @abstractmethod
    async def list_users(
        self, offset: int = 0, limit: int = 50, active_only: bool = True
    ) -> List[User]:
        """Paginated user list."""

    @abstractmethod
    async def update_user(self, user_id: str, **fields) -> User:
        """Partial update.  Accepted fields: email, role, active, metadata."""

    @abstractmethod
    async def delete_user(self, user_id: str) -> bool:
        """Soft-delete (set active=False) or hard-delete depending on impl."""

    # ── Quotas ───────────────────────────────────────────────────

    @abstractmethod
    async def get_quota(self, user_id: str) -> Quota:
        """Current resource budget for the user."""

    @abstractmethod
    async def update_quota(self, user_id: str, **fields) -> Quota:
        """Admin override: set specific quota fields."""

    @abstractmethod
    async def debit_quota(
        self, user_id: str, cpu_seconds: float = 0, storage_bytes: int = 0
    ) -> Quota:
        """Subtract from the user's remaining quota.  Raises if insufficient."""

    # ── Permissions ──────────────────────────────────────────────

    @abstractmethod
    async def check_permission(
        self, user_id: str, resource: str, action: AccessLevel
    ) -> bool:
        """Does the user have at least *action* level on *resource*?"""

    @abstractmethod
    async def grant_permission(
        self, user_id: str, resource: str, access: AccessLevel
    ) -> Permission:
        """Grant or upgrade a permission."""

    @abstractmethod
    async def revoke_permission(
        self, user_id: str, resource: str
    ) -> bool:
        """Remove a permission.  Returns True if it existed."""

    @abstractmethod
    async def list_permissions(
        self, user_id: str
    ) -> List[Permission]:
        """All permissions for a user."""

    @abstractmethod
    async def list_resource_permissions(
        self, resource: str
    ) -> List[Permission]:
        """All users with access to a resource."""
