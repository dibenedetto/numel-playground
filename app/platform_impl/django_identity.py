"""Django-backed identity provider scaffold."""

from __future__ import annotations

from typing import Optional

from domain.interfaces import IdentityProvider
from domain.models import UsageQuota, UserAccount, UserProfile

from .config import DatabaseConfig, DjangoIdentityConfig
from .support import ScaffoldComponent


class DjangoIdentityProvider(IdentityProvider, ScaffoldComponent):
    """Future identity adapter backed by Django auth/user services."""

    def __init__(
        self,
        config: DjangoIdentityConfig,
        db_config: Optional[DatabaseConfig] = None,
        audit_log=None,
    ):
        self.config = config
        self.db_config = db_config
        self.audit_log = audit_log

    async def authenticate(self, token: str) -> Optional[UserAccount]:
        self._not_ready("authenticate")

    async def login(self, username: str, password: str) -> Optional[str]:
        self._not_ready("login")

    async def logout(self, token: str) -> bool:
        self._not_ready("logout")

    async def create_user(self, username: str, email: str, password: str) -> UserAccount:
        self._not_ready("create_user")

    async def get_user(self, user_id: str) -> Optional[UserAccount]:
        self._not_ready("get_user")

    async def get_user_by_username(self, username: str) -> Optional[UserAccount]:
        self._not_ready("get_user_by_username")

    async def list_users(
        self, offset: int = 0, limit: int = 50, active_only: bool = True
    ):
        self._not_ready("list_users")

    async def update_user(self, user_id: str, **fields) -> UserAccount:
        self._not_ready("update_user")

    async def delete_user(self, user_id: str) -> bool:
        self._not_ready("delete_user")

    async def get_profile(self, user_id: str) -> Optional[UserProfile]:
        self._not_ready("get_profile")

    async def update_profile(self, user_id: str, **fields) -> UserProfile:
        self._not_ready("update_profile")

    async def get_quota(self, user_id: str) -> UsageQuota:
        self._not_ready("get_quota")

    async def update_quota(self, user_id: str, **fields) -> UsageQuota:
        self._not_ready("update_quota")
