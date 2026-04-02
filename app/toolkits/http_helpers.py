"""Shared HTTP helpers for toolkits that talk to Numel routes."""

from __future__ import annotations

from typing import Any, Dict, Optional

import httpx


class ToolkitHttpSession:
    """POST JSON to Numel routes using either a local ASGI app or loopback HTTP."""

    def __init__(
        self,
        *,
        base_url: str = "http://localhost:11360",
        auth_token: str = "",
        internal_token: str = "",
        user_id: Optional[str] = None,
        local_app=None,
        timeout: float = 60.0,
    ):
        self._base = base_url.rstrip("/")
        self._auth_token = auth_token or ""
        self._internal_token = internal_token or ""
        self._user_id = user_id or ""
        self._timeout = timeout
        self._client = None
        if local_app is not None:
            from fastapi.testclient import TestClient

            self._client = TestClient(local_app, base_url=self._base)

    def _headers(self) -> Dict[str, str]:
        headers: Dict[str, str] = {}
        if self._auth_token:
            headers["Authorization"] = f"Bearer {self._auth_token}"
        elif self._internal_token and self._user_id:
            headers["x-numel-platform-internal"] = self._internal_token
            headers["x-numel-acting-user"] = self._user_id
        return headers

    def post_json(self, path: str, data: Any = None) -> Dict[str, Any]:
        body = data or {}
        headers = self._headers()
        if self._client is not None:
            response = self._client.post(path, json=body, headers=headers)
        else:
            response = httpx.post(
                f"{self._base}{path}",
                json=body,
                headers=headers,
                timeout=self._timeout,
            )
        response.raise_for_status()
        payload = response.json()
        return payload if isinstance(payload, dict) else {}
