"""Internal HTTP client for the Numel platform contract."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import httpx

from domain.models import CredentialRecord, SecretScope, UsageQuota, UserAccount, UserProfile, UserRole


class PlatformRequestError(Exception):
    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class PlatformHttpClient:
    """Talk to the local platform backend strictly through HTTP."""

    def __init__(self, app, internal_token: str, base_url: str = "http://platform.local"):
        self._client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url=base_url,
            timeout=30.0,
        )
        self._internal_token = internal_token
        self._user_cache: Dict[str, UserAccount] = {}
        self._user_cache_by_username: Dict[str, UserAccount] = {}

    async def aclose(self) -> None:
        await self._client.aclose()

    def _headers(self) -> Dict[str, str]:
        return {"x-numel-platform-internal": self._internal_token}

    async def post_json(self, path: str, body: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        resp = await self._client.post(path, headers=self._headers(), json=body or {})
        if not resp.is_success:
            detail = ""
            try:
                data = resp.json()
                detail = str(data.get("detail", "")) if isinstance(data, dict) else ""
            except Exception:
                detail = resp.text
            raise PlatformRequestError(resp.status_code, detail or str(resp.status_code))
        data = resp.json()
        return data if isinstance(data, dict) else {}

    def _user_from_dict(self, data: Optional[Dict[str, Any]]) -> Optional[UserAccount]:
        if not data:
            return None
        user = UserAccount(
            id=str(data["id"]),
            username=str(data["username"]),
            email=str(data["email"]),
            role=UserRole(str(data.get("role", UserRole.USER.value))),
            active=bool(data.get("active", True)),
            created_at=float(data.get("created_at", 0.0) or 0.0),
            metadata=data.get("metadata", {}) or {},
        )
        self._user_cache[user.id] = user
        self._user_cache_by_username[user.username] = user
        return user

    def _profile_from_dict(self, data: Optional[Dict[str, Any]]) -> Optional[UserProfile]:
        if not data:
            return None
        return UserProfile(
            user_id=str(data["user_id"]),
            display_name=str(data.get("display_name", "") or ""),
            bio=str(data.get("bio", "") or ""),
            avatar_url=str(data.get("avatar_url", "") or ""),
            metadata=data.get("metadata", {}) or {},
        )

    def _quota_from_dict(self, data: Optional[Dict[str, Any]]) -> Optional[UsageQuota]:
        if not data:
            return None
        return UsageQuota(
            user_id=str(data["user_id"]),
            cpu_seconds_remaining=float(data.get("cpu_seconds_remaining", 0.0) or 0.0),
            max_concurrent_runs=int(data.get("max_concurrent_runs", 0) or 0),
            storage_bytes_remaining=int(data.get("storage_bytes_remaining", 0) or 0),
            max_loop_hours=float(data.get("max_loop_hours", 0.0) or 0.0),
            gpu_hours_remaining=float(data.get("gpu_hours_remaining", 0.0) or 0.0),
            max_spaces=int(data.get("max_spaces", 0) or 0),
            max_assets_per_space=int(data.get("max_assets_per_space", 0) or 0),
        )

    def _credential_from_dict(self, data: Optional[Dict[str, Any]]) -> Optional[CredentialRecord]:
        if not data:
            return None
        return CredentialRecord(
            id=str(data["id"]),
            owner_user_id=str(data["owner_user_id"]),
            name=str(data["name"]),
            scope=SecretScope(str(data.get("scope", SecretScope.USER.value))),
            space_id=data.get("space_id"),
            secret_ref=str(data.get("secret_ref", "") or ""),
            value_present=bool(data.get("value_present", False)),
            created_at=float(data.get("created_at", 0.0) or 0.0),
            updated_at=float(data.get("updated_at", 0.0) or 0.0),
            last_used_at=data.get("last_used_at"),
            metadata=data.get("metadata", {}) or {},
        )

    async def authenticate(self, token: str) -> Optional[UserAccount]:
        if not token:
            return None
        try:
            data = await self.post_json("/platform/auth/authenticate", {"token": token})
        except PlatformRequestError:
            return None
        return self._user_from_dict(data.get("user"))

    async def register(self, username: str, email: str, password: str) -> Dict[str, Any]:
        data = await self.post_json(
            "/platform/auth/register",
            {"username": username, "email": email, "password": password},
        )
        user = self._user_from_dict(data.get("user"))
        return {"token": data.get("token"), "user": user}

    async def create_user(self, username: str, email: str, password: str) -> UserAccount:
        try:
            data = await self.post_json(
                "/platform/users/create",
                {"username": username, "email": email, "password": password},
            )
        except PlatformRequestError as exc:
            raise ValueError(exc.detail)
        user = self._user_from_dict(data.get("user"))
        if user is None:
            raise RuntimeError("Platform did not return a user")
        return user

    async def login_result(self, username: str, password: str) -> Optional[Dict[str, Any]]:
        try:
            data = await self.post_json(
                "/platform/auth/login",
                {"username": username, "password": password},
            )
        except PlatformRequestError as exc:
            if exc.status_code == 401:
                return None
            raise
        user = self._user_from_dict(data.get("user"))
        return {"token": data.get("token"), "user": user}

    async def login(self, username: str, password: str) -> Optional[str]:
        result = await self.login_result(username, password)
        return None if result is None else result.get("token")

    async def logout(self, token: str) -> bool:
        try:
            data = await self.post_json("/platform/auth/logout", {"token": token})
        except PlatformRequestError:
            return False
        return bool(data.get("ok"))

    async def auth_status(self) -> Dict[str, Any]:
        return await self.post_json("/platform/auth/status", {})

    async def change_password(self, user_id: str, current_password: str, new_password: str) -> bool:
        try:
            data = await self.post_json(
                "/platform/auth/change-password",
                {
                    "user_id": user_id,
                    "current_password": current_password,
                    "new_password": new_password,
                },
            )
        except PlatformRequestError as exc:
            if exc.status_code == 403:
                return False
            raise
        return bool(data.get("ok"))

    async def get_user(self, user_id: str) -> Optional[UserAccount]:
        try:
            data = await self.post_json(f"/platform/users/{user_id}", {})
        except PlatformRequestError as exc:
            if exc.status_code == 404:
                return None
            raise
        return self._user_from_dict(data.get("user"))

    async def get_user_bundle(self, user_id: str) -> Dict[str, Any]:
        data = await self.post_json(f"/platform/users/{user_id}", {})
        return {
            "user": self._user_from_dict(data.get("user")),
            "profile": self._profile_from_dict(data.get("profile")),
            "quota": self._quota_from_dict(data.get("quota")),
        }

    async def get_user_by_username(self, username: str) -> Optional[UserAccount]:
        cached = self._user_cache_by_username.get(username)
        if cached is not None:
            return cached
        try:
            data = await self.post_json("/platform/users/by-username", {"username": username})
        except PlatformRequestError as exc:
            if exc.status_code == 404:
                return None
            raise
        return self._user_from_dict(data.get("user"))

    async def list_users(self, offset: int = 0, limit: int = 50, active_only: bool = True) -> List[UserAccount]:
        data = await self.post_json(
            "/platform/users/list",
            {"offset": offset, "limit": limit, "active_only": active_only},
        )
        users = []
        for item in data.get("users", []) or []:
            user = self._user_from_dict(item)
            if user is not None:
                users.append(user)
        return users

    async def list_user_rows(self, offset: int = 0, limit: int = 50, active_only: bool = True) -> Dict[str, Any]:
        return await self.post_json(
            "/platform/users/list",
            {"offset": offset, "limit": limit, "active_only": active_only},
        )

    async def update_user(self, user_id: str, **fields) -> UserAccount:
        data = await self.post_json(f"/platform/users/{user_id}/update", fields)
        user = self._user_from_dict(data.get("user"))
        if user is None:
            raise RuntimeError("Platform did not return a user")
        return user

    async def delete_user(self, user_id: str) -> bool:
        data = await self.post_json(f"/platform/users/{user_id}/delete", {})
        return bool(data.get("ok"))

    async def get_profile(self, user_id: str) -> Optional[UserProfile]:
        bundle = await self.get_user_bundle(user_id)
        return bundle.get("profile")

    async def update_profile(self, user_id: str, **fields) -> UserProfile:
        data = await self.post_json(f"/platform/users/{user_id}/profile", fields)
        profile = self._profile_from_dict(data.get("profile"))
        if profile is None:
            raise RuntimeError("Platform did not return a profile")
        return profile

    async def get_quota(self, user_id: str) -> UsageQuota:
        bundle = await self.get_user_bundle(user_id)
        quota = bundle.get("quota")
        if quota is None:
            raise RuntimeError("Platform did not return a quota")
        return quota

    async def update_quota(self, user_id: str, **fields) -> UsageQuota:
        data = await self.post_json(f"/platform/users/{user_id}/quota", fields)
        quota = self._quota_from_dict(data.get("quota"))
        if quota is None:
            raise RuntimeError("Platform did not return a quota")
        return quota

    async def list_credentials(self, owner_user_id: str, space_id: Optional[str] = None) -> List[CredentialRecord]:
        data = await self.post_json(
            "/platform/secrets/list",
            {"owner_user_id": owner_user_id, "space_id": space_id},
        )
        return [
            credential
            for credential in (self._credential_from_dict(item) for item in (data.get("credentials", []) or []))
            if credential is not None
        ]

    async def set_credential(
        self,
        owner_user_id: str,
        name: str,
        value: str,
        space_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> CredentialRecord:
        data = await self.post_json(
            "/platform/secrets/set",
            {
                "owner_user_id": owner_user_id,
                "name": name,
                "value": value,
                "space_id": space_id,
                "metadata": metadata or {},
            },
        )
        record = self._credential_from_dict(data.get("credential"))
        if record is None:
            raise RuntimeError("Platform did not return a credential")
        return record

    async def delete_credential(
        self,
        owner_user_id: str,
        name: str,
        space_id: Optional[str] = None,
    ) -> bool:
        data = await self.post_json(
            "/platform/secrets/delete",
            {"owner_user_id": owner_user_id, "name": name, "space_id": space_id},
        )
        return bool(data.get("ok"))
