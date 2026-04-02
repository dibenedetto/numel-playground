"""HTTP contract for the Numel platform layer."""

from __future__ import annotations

import base64
from dataclasses import asdict, is_dataclass
from enum import Enum
from typing import Any, Dict

from fastapi import FastAPI, HTTPException, Request

from domain.models import (
    AclEntry,
    AssetKind,
    Capability,
    ExecutionRequest,
    ExecutionState,
    FriendshipStatus,
    PermissionPolicy,
    RefKind,
    SpaceAsset,
    SubjectType,
    UserRole,
    Visibility,
)


def setup_platform_api(app: FastAPI, stack, internal_token: str) -> None:
    """Expose the active platform backend on dedicated /platform routes."""

    def _jsonable(value: Any) -> Any:
        if is_dataclass(value):
            return _jsonable(asdict(value))
        if isinstance(value, Enum):
            return value.value
        if isinstance(value, dict):
            return {key: _jsonable(item) for key, item in value.items()}
        if isinstance(value, (list, tuple, set)):
            return [_jsonable(item) for item in value]
        return value

    async def _body(req: Request) -> Dict[str, Any]:
        try:
            raw = await req.json()
            return raw if isinstance(raw, dict) else {}
        except Exception:
            return {}

    def _bearer_token(req: Request) -> str:
        return req.headers.get("authorization", "").removeprefix("Bearer ").strip()

    def _is_internal(req: Request) -> bool:
        token = req.headers.get("x-numel-platform-internal", "")
        return bool(token) and token == internal_token

    def _role_value(user) -> str:
        if not user:
            return ""
        role = getattr(user, "role", "")
        return str(getattr(role, "value", role)).lower()

    async def _external_user(req: Request):
        token = _bearer_token(req)
        if not token:
            return None
        return await stack.identity.authenticate(token)

    async def _require_user(req: Request):
        user = await _external_user(req)
        if user is None:
            raise HTTPException(status_code=401, detail="Not authenticated")
        return user

    async def _require_admin(req: Request):
        if _is_internal(req):
            return None
        user = await _require_user(req)
        if _role_value(user) != UserRole.ADMIN.value:
            raise HTTPException(status_code=403, detail="Admin access required")
        return user

    async def _resolve_actor(
        req: Request,
        body: Dict[str, Any],
        *,
        field_name: str = "user_id",
        require_external_user: bool = True,
    ):
        if _is_internal(req):
            actor_user_id = str(body.get(field_name, "") or "").strip()
            if actor_user_id:
                actor = await stack.identity.get_user(actor_user_id)
                if actor is None:
                    raise HTTPException(status_code=404, detail=f"User '{actor_user_id}' not found")
                return actor
            if require_external_user:
                raise HTTPException(
                    status_code=400,
                    detail=f"{field_name} is required for internal platform calls",
                )
            return None
        return await _require_user(req)

    async def _space_or_404(space_id: str):
        space = await stack.spaces.get_space(space_id)
        if space is None:
            raise HTTPException(status_code=404, detail=f"Space '{space_id}' not found")
        return space

    async def _require_space_read(req: Request, body: Dict[str, Any], space_id: str):
        actor = await _resolve_actor(req, body)
        if not await stack.spaces.check_space_access(actor.id, space_id, Capability.READ):
            raise HTTPException(status_code=403, detail="Read access denied")
        return actor

    async def _require_space_owner_or_admin(req: Request, body: Dict[str, Any], space_id: str):
        space = await _space_or_404(space_id)
        if _is_internal(req):
            actor = await _resolve_actor(req, body, require_external_user=False)
            if actor is None:
                return None, space
            if actor.id == space.owner_user_id or _role_value(actor) == UserRole.ADMIN.value:
                return actor, space
        else:
            actor = await _require_user(req)
            if actor.id == space.owner_user_id or _role_value(actor) == UserRole.ADMIN.value:
                return actor, space
        raise HTTPException(status_code=403, detail="Only the owner or an admin may modify this space")

    def _parse_visibility(value: Any, default: Visibility = Visibility.PRIVATE) -> Visibility:
        if value in (None, ""):
            return default
        return value if isinstance(value, Visibility) else Visibility(str(value))

    def _parse_kind(value: Any, default: AssetKind = AssetKind.DATA) -> AssetKind:
        if value in (None, ""):
            return default
        return value if isinstance(value, AssetKind) else AssetKind(str(value))

    def _parse_policy(data: Any, owner_user_id: str, visibility: Visibility) -> PermissionPolicy:
        if not isinstance(data, dict):
            return PermissionPolicy(owner_user_id=owner_user_id, visibility=visibility)
        acl = []
        for item in data.get("acl", []) or []:
            if not isinstance(item, dict):
                continue
            acl.append(
                AclEntry(
                    subject_type=SubjectType(str(item.get("subject_type", SubjectType.USER.value))),
                    subject_id=str(item.get("subject_id", "") or ""),
                    capabilities=[
                        Capability(str(cap))
                        for cap in (item.get("capabilities", []) or [])
                    ],
                    metadata=item.get("metadata", {}) or {},
                )
            )
        return PermissionPolicy(
            owner_user_id=str(data.get("owner_user_id", owner_user_id) or owner_user_id),
            visibility=_parse_visibility(data.get("visibility"), visibility),
            acl=acl,
            metadata=data.get("metadata", {}) or {},
        )

    async def _credential_owner(req: Request, body: Dict[str, Any]) -> str:
        if _is_internal(req):
            owner = str(body.get("owner_user_id", "") or "").strip()
            if not owner:
                actor = await _resolve_actor(req, body)
                return actor.id
            return owner
        actor = await _require_user(req)
        requested_owner = str(body.get("owner_user_id", "") or "").strip()
        if requested_owner and requested_owner != actor.id and _role_value(actor) != UserRole.ADMIN.value:
            raise HTTPException(status_code=403, detail="Only admins may manage another user's credentials")
        return requested_owner or actor.id

    async def _serialize_user_bundle(user_id: str) -> Dict[str, Any]:
        user = await stack.identity.get_user(user_id)
        if user is None:
            raise HTTPException(status_code=404, detail=f"User '{user_id}' not found")
        profile = await stack.identity.get_profile(user_id)
        quota = await stack.identity.get_quota(user_id)
        return {
            "user": _jsonable(user),
            "profile": _jsonable(profile) if profile is not None else None,
            "quota": _jsonable(quota),
        }

    @app.post("/platform/auth/authenticate")
    async def platform_authenticate(req: Request):
        body = await _body(req)
        token = str(body.get("token", "") or "").strip() or _bearer_token(req)
        if not token:
            return {"authenticated": False, "user": None}
        user = await stack.identity.authenticate(token)
        return {"authenticated": user is not None, "user": _jsonable(user) if user else None}

    @app.post("/platform/auth/register")
    async def platform_register(req: Request):
        body = await _body(req)
        username = str(body.get("username", "") or "").strip()
        email = str(body.get("email", "") or "").strip() or f"{username}@local"
        password = str(body.get("password", "") or "")
        if not username or not password:
            raise HTTPException(status_code=400, detail="username and password are required")
        try:
            user = await stack.identity.create_user(username, email, password)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc))
        token = await stack.identity.login(username, password)
        return {"token": token, "user": _jsonable(user)}

    @app.post("/platform/auth/login")
    async def platform_login(req: Request):
        body = await _body(req)
        username = str(body.get("username", "") or "").strip()
        password = str(body.get("password", "") or "")
        if not username or not password:
            raise HTTPException(status_code=400, detail="username and password are required")
        token = await stack.identity.login(username, password)
        if not token:
            raise HTTPException(status_code=401, detail="Invalid credentials")
        user = await stack.identity.authenticate(token)
        return {"token": token, "user": _jsonable(user)}

    @app.post("/platform/auth/logout")
    async def platform_logout(req: Request):
        body = await _body(req)
        token = str(body.get("token", "") or "").strip() or _bearer_token(req)
        return {"ok": bool(token) and await stack.identity.logout(token)}

    @app.post("/platform/auth/status")
    async def platform_auth_status():
        users = await stack.identity.list_users(limit=1, active_only=False)
        return {
            "enabled": True,
            "provider": stack.identity.__class__.__name__,
            "has_users": len(users) > 0,
        }

    @app.post("/platform/auth/change-password")
    async def platform_change_password(req: Request):
        body = await _body(req)
        current_password = str(body.get("current_password", "") or "")
        new_password = str(body.get("new_password", "") or "")
        if len(new_password) < 4:
            raise HTTPException(status_code=400, detail="Password must be at least 4 characters")
        actor = await _resolve_actor(req, body)
        ok = await stack.identity.change_password(actor.id, current_password, new_password)
        if not ok:
            raise HTTPException(status_code=403, detail="Current password is incorrect")
        return {"ok": True}

    @app.post("/platform/users/create")
    async def platform_create_user(req: Request):
        body = await _body(req)
        username = str(body.get("username", "") or "").strip()
        email = str(body.get("email", "") or "").strip() or f"{username}@local"
        password = str(body.get("password", "") or "")
        if not username or not password:
            raise HTTPException(status_code=400, detail="username and password are required")
        try:
            user = await stack.identity.create_user(username, email, password)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc))
        return {"user": _jsonable(user)}

    @app.post("/platform/users/me")
    async def platform_user_me(req: Request):
        actor = await _require_user(req)
        return await _serialize_user_bundle(actor.id)

    @app.post("/platform/users/by-username")
    async def platform_user_by_username(req: Request):
        body = await _body(req)
        if not _is_internal(req):
            await _require_admin(req)
        username = str(body.get("username", "") or "").strip()
        if not username:
            raise HTTPException(status_code=400, detail="username is required")
        user = await stack.identity.get_user_by_username(username)
        if user is None:
            raise HTTPException(status_code=404, detail=f"User '{username}' not found")
        return {"user": _jsonable(user)}

    @app.post("/platform/users/list")
    async def platform_list_users(req: Request):
        body = await _body(req)
        await _require_admin(req)
        users = await stack.identity.list_users(
            offset=int(body.get("offset", 0) or 0),
            limit=int(body.get("limit", 50) or 50),
            active_only=bool(body.get("active_only", True)),
        )
        items = []
        for user in users:
            quota = await stack.identity.get_quota(user.id)
            items.append(
                {
                    "id": user.id,
                    "username": user.username,
                    "email": user.email,
                    "role": user.role.value,
                    "active": user.active,
                    "created_at": user.created_at,
                    "metadata": user.metadata,
                    "quota": _jsonable(quota),
                }
            )
        return {"users": items, "count": len(items)}

    @app.post("/platform/users/{user_id}")
    async def platform_get_user(user_id: str, req: Request):
        if not _is_internal(req):
            actor = await _require_user(req)
            if actor.id != user_id and _role_value(actor) != UserRole.ADMIN.value:
                raise HTTPException(status_code=403, detail="User access denied")
        return await _serialize_user_bundle(user_id)

    @app.post("/platform/users/{user_id}/update")
    async def platform_update_user(user_id: str, req: Request):
        body = await _body(req)
        await _require_admin(req)
        allowed = {k: v for k, v in body.items() if k in {"username", "email", "role", "active", "metadata"}}
        try:
            user = await stack.identity.update_user(user_id, **allowed)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        return {"user": _jsonable(user)}

    @app.post("/platform/users/{user_id}/delete")
    async def platform_delete_user(user_id: str, req: Request):
        await _require_admin(req)
        ok = await stack.identity.delete_user(user_id)
        if not ok:
            raise HTTPException(status_code=404, detail=f"User '{user_id}' not found")
        return {"ok": True}

    @app.post("/platform/users/{user_id}/profile")
    async def platform_update_profile(user_id: str, req: Request):
        body = await _body(req)
        if not _is_internal(req):
            actor = await _require_user(req)
            if actor.id != user_id and _role_value(actor) != UserRole.ADMIN.value:
                raise HTTPException(status_code=403, detail="Profile update denied")
        try:
            profile = await stack.identity.update_profile(
                user_id,
                **{k: v for k, v in body.items() if k in {"display_name", "bio", "avatar_url", "metadata"}},
            )
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        return {"profile": _jsonable(profile)}

    @app.post("/platform/users/{user_id}/quota")
    async def platform_update_quota(user_id: str, req: Request):
        body = await _body(req)
        await _require_admin(req)
        try:
            quota = await stack.identity.update_quota(user_id, **body)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        return {"quota": _jsonable(quota)}

    @app.post("/platform/friends/list")
    async def platform_list_friends(req: Request):
        body = await _body(req)
        actor = await _resolve_actor(req, body)
        status = body.get("status")
        friendships = await stack.friend_graph.list_friendships(
            actor.id,
            status=FriendshipStatus(str(status)) if status else None,
        )
        return {"friendships": _jsonable(friendships)}

    @app.post("/platform/friends/request")
    async def platform_friend_request(req: Request):
        body = await _body(req)
        actor = await _resolve_actor(req, body)
        target_user_id = str(body.get("target_user_id", "") or "").strip()
        if not target_user_id:
            raise HTTPException(status_code=400, detail="target_user_id is required")
        try:
            friendship = await stack.friend_graph.send_request(actor.id, target_user_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return {"friendship": _jsonable(friendship)}

    @app.post("/platform/friends/accept")
    async def platform_friend_accept(req: Request):
        body = await _body(req)
        actor = await _resolve_actor(req, body)
        requester_user_id = str(body.get("requester_user_id", "") or "").strip()
        if not requester_user_id:
            raise HTTPException(status_code=400, detail="requester_user_id is required")
        try:
            friendship = await stack.friend_graph.accept_request(requester_user_id, actor.id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        return {"friendship": _jsonable(friendship)}

    @app.post("/platform/friends/reject")
    async def platform_friend_reject(req: Request):
        body = await _body(req)
        actor = await _resolve_actor(req, body)
        requester_user_id = str(body.get("requester_user_id", "") or "").strip()
        if not requester_user_id:
            raise HTTPException(status_code=400, detail="requester_user_id is required")
        try:
            friendship = await stack.friend_graph.reject_request(requester_user_id, actor.id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        return {"friendship": _jsonable(friendship)}

    @app.post("/platform/friends/remove")
    async def platform_friend_remove(req: Request):
        body = await _body(req)
        actor = await _resolve_actor(req, body)
        friend_user_id = str(body.get("friend_user_id", "") or "").strip()
        if not friend_user_id:
            raise HTTPException(status_code=400, detail="friend_user_id is required")
        return {"ok": await stack.friend_graph.remove_friend(actor.id, friend_user_id)}

    @app.post("/platform/secrets/list")
    async def platform_list_secrets(req: Request):
        body = await _body(req)
        owner_user_id = await _credential_owner(req, body)
        space_id = str(body.get("space_id", "") or "").strip() or None
        records = await stack.secrets.list_credentials(owner_user_id, space_id=space_id)
        return {"credentials": _jsonable(records)}

    @app.post("/platform/secrets/get")
    async def platform_get_secret(req: Request):
        body = await _body(req)
        owner_user_id = await _credential_owner(req, body)
        name = str(body.get("name", "") or "").strip()
        if not name:
            raise HTTPException(status_code=400, detail="name is required")
        space_id = str(body.get("space_id", "") or "").strip() or None
        record = await stack.secrets.get_credential(owner_user_id, name, space_id=space_id)
        if record is None:
            raise HTTPException(status_code=404, detail=f"Credential '{name}' not found")
        return {"credential": _jsonable(record)}

    @app.post("/platform/secrets/set")
    async def platform_set_secret(req: Request):
        body = await _body(req)
        owner_user_id = await _credential_owner(req, body)
        name = str(body.get("name", "") or "").strip()
        if not name:
            raise HTTPException(status_code=400, detail="name is required")
        record = await stack.secrets.set_credential(
            owner_user_id,
            name,
            str(body.get("value", "") or ""),
            space_id=str(body.get("space_id", "") or "").strip() or None,
            metadata=body.get("metadata"),
        )
        return {"credential": _jsonable(record)}

    @app.post("/platform/secrets/delete")
    async def platform_delete_secret(req: Request):
        body = await _body(req)
        owner_user_id = await _credential_owner(req, body)
        name = str(body.get("name", "") or "").strip()
        if not name:
            raise HTTPException(status_code=400, detail="name is required")
        ok = await stack.secrets.delete_credential(
            owner_user_id,
            name,
            space_id=str(body.get("space_id", "") or "").strip() or None,
        )
        return {"ok": ok}

    @app.post("/platform/secrets/resolve")
    async def platform_resolve_secrets(req: Request):
        body = await _body(req)
        owner_user_id = await _credential_owner(req, body)
        values = await stack.secrets.resolve_credentials(
            owner_user_id,
            names=body.get("names"),
            space_id=str(body.get("space_id", "") or "").strip() or None,
        )
        return {"values": values}

    @app.post("/platform/spaces/create")
    async def platform_create_space(req: Request):
        body = await _body(req)
        actor = await _resolve_actor(req, body)
        owner_user_id = str(body.get("owner_user_id", "") or "").strip() or actor.id
        if owner_user_id != actor.id and not _is_internal(req) and _role_value(actor) != UserRole.ADMIN.value:
            raise HTTPException(status_code=403, detail="Only admins may create spaces for another user")
        try:
            space = await stack.spaces.create_space(
                owner_user_id=owner_user_id,
                slug=str(body.get("slug", "") or "").strip(),
                title=str(body.get("title", "") or "").strip(),
                description=str(body.get("description", "") or ""),
                visibility=_parse_visibility(body.get("visibility"), Visibility.PRIVATE),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return {"space": _jsonable(space)}

    @app.post("/platform/spaces/list-owned")
    async def platform_list_owned_spaces(req: Request):
        body = await _body(req)
        actor = await _resolve_actor(req, body)
        owner_user_id = str(body.get("owner_user_id", "") or "").strip() or actor.id
        if owner_user_id != actor.id and not _is_internal(req) and _role_value(actor) != UserRole.ADMIN.value:
            raise HTTPException(status_code=403, detail="Only admins may inspect another owner's spaces")
        spaces = await stack.spaces.list_owned_spaces(owner_user_id)
        return {"spaces": _jsonable(spaces)}

    @app.post("/platform/spaces/list-accessible")
    async def platform_list_accessible_spaces(req: Request):
        body = await _body(req)
        actor = await _resolve_actor(req, body)
        spaces = await stack.spaces.list_accessible_spaces(actor.id)
        return {"spaces": _jsonable(spaces)}

    @app.post("/platform/spaces/{space_id}")
    async def platform_get_space(space_id: str, req: Request):
        body = await _body(req)
        await _require_space_read(req, body, space_id)
        space = await _space_or_404(space_id)
        return {"space": _jsonable(space)}

    @app.post("/platform/spaces/{space_id}/update")
    async def platform_update_space(space_id: str, req: Request):
        body = await _body(req)
        await _require_space_owner_or_admin(req, body, space_id)
        try:
            space = await stack.spaces.update_space(space_id, **body)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return {"space": _jsonable(space)}

    @app.post("/platform/spaces/{space_id}/delete")
    async def platform_delete_space(space_id: str, req: Request):
        body = await _body(req)
        await _require_space_owner_or_admin(req, body, space_id)
        ok = await stack.spaces.delete_space(space_id)
        return {"ok": ok}

    @app.post("/platform/spaces/{space_id}/policy")
    async def platform_set_space_policy(space_id: str, req: Request):
        body = await _body(req)
        actor, space = await _require_space_owner_or_admin(req, body, space_id)
        owner_user_id = (
            space.owner_user_id
            if actor is None or actor.id != space.owner_user_id
            else actor.id
        )
        policy = _parse_policy(
            body.get("policy"),
            owner_user_id,
            _parse_visibility(body.get("visibility"), space.visibility),
        )
        updated = await stack.spaces.set_space_policy(space_id, policy)
        return {"space": _jsonable(updated)}

    @app.post("/platform/spaces/{space_id}/fork")
    async def platform_fork_space(space_id: str, req: Request):
        body = await _body(req)
        actor = await _resolve_actor(req, body)
        new_owner_user_id = str(body.get("new_owner_user_id", "") or "").strip() or actor.id
        if new_owner_user_id != actor.id and not _is_internal(req) and _role_value(actor) != UserRole.ADMIN.value:
            raise HTTPException(status_code=403, detail="Only admins may fork into another owner's scope")
        try:
            space = await stack.spaces.fork_space(
                source_space_id=space_id,
                new_owner_user_id=new_owner_user_id,
                slug=str(body.get("slug", "") or "").strip(),
                title=str(body.get("title", "") or "").strip(),
            )
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return {"space": _jsonable(space)}

    @app.post("/platform/spaces/{space_id}/assets/list")
    async def platform_list_assets(space_id: str, req: Request):
        body = await _body(req)
        actor = await _require_space_read(req, body, space_id)
        assets = await stack.spaces.list_assets(
            actor.id,
            space_id,
            ref=str(body.get("ref", "main") or "main"),
            prefix=str(body.get("prefix", "") or ""),
        )
        return {"assets": _jsonable(assets)}

    @app.post("/platform/spaces/{space_id}/assets/get")
    async def platform_get_asset(space_id: str, req: Request):
        body = await _body(req)
        actor = await _require_space_read(req, body, space_id)
        path = str(body.get("path", "") or "").strip()
        if not path:
            raise HTTPException(status_code=400, detail="path is required")
        asset = await stack.spaces.get_asset(actor.id, space_id, path, ref=str(body.get("ref", "main") or "main"))
        if asset is None:
            raise HTTPException(status_code=404, detail=f"Asset '{path}' not found")
        return {"asset": _jsonable(asset)}

    @app.post("/platform/spaces/{space_id}/assets/read")
    async def platform_read_asset(space_id: str, req: Request):
        body = await _body(req)
        actor = await _require_space_read(req, body, space_id)
        path = str(body.get("path", "") or "").strip()
        if not path:
            raise HTTPException(status_code=400, detail="path is required")
        try:
            raw = await stack.spaces.read_asset(
                actor.id,
                space_id,
                path,
                ref=str(body.get("ref", "main") or "main"),
            )
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail=f"Asset '{path}' not found")
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            text = None
        return {
            "path": path,
            "content_base64": base64.b64encode(raw).decode("ascii"),
            "text": text,
        }

    @app.post("/platform/spaces/{space_id}/assets/write")
    async def platform_write_asset(space_id: str, req: Request):
        body = await _body(req)
        actor = await _resolve_actor(req, body)
        path = str(body.get("path", "") or "").strip()
        if not path:
            raise HTTPException(status_code=400, detail="path is required")
        ref = str(body.get("ref", "main") or "main")
        existing = await stack.spaces.get_asset(actor.id, space_id, path, ref=ref)
        visibility = _parse_visibility(body.get("visibility"), existing.visibility if existing else Visibility.PRIVATE)
        owner_user_id = str(body.get("owner_user_id", "") or "").strip() or (existing.owner_user_id if existing else actor.id)
        payload_b64 = body.get("content_base64")
        if payload_b64 is not None:
            content = base64.b64decode(str(payload_b64))
        else:
            content = str(body.get("text", "") or "").encode("utf-8")
        asset = SpaceAsset(
            id=existing.id if existing else "",
            space_id=space_id,
            path=path,
            kind=_parse_kind(body.get("kind"), existing.kind if existing else AssetKind.DATA),
            owner_user_id=owner_user_id,
            title=str(body.get("title", existing.title if existing else "") or ""),
            description=str(body.get("description", existing.description if existing else "") or ""),
            visibility=visibility,
            versioned=bool(body.get("versioned", existing.versioned if existing else True)),
            executable=bool(body.get("executable", existing.executable if existing else False)),
            size_bytes=len(content),
            content_hash=existing.content_hash if existing else "",
            latest_commit_id=existing.latest_commit_id if existing else "",
            policy=_parse_policy(
                body.get("policy"),
                owner_user_id,
                visibility,
            ) if body.get("policy") is not None else (
                existing.policy if existing else PermissionPolicy(owner_user_id=owner_user_id, visibility=visibility)
            ),
            created_at=existing.created_at if existing else 0.0,
            metadata=body.get("metadata", existing.metadata if existing else {}) or {},
        )
        try:
            commit = await stack.spaces.write_asset(
                actor.id,
                space_id,
                asset,
                content,
                message=str(body.get("message", "") or ""),
                ref=ref,
            )
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return {"commit": _jsonable(commit)}

    @app.post("/platform/spaces/{space_id}/assets/delete")
    async def platform_delete_asset(space_id: str, req: Request):
        body = await _body(req)
        actor = await _resolve_actor(req, body)
        path = str(body.get("path", "") or "").strip()
        if not path:
            raise HTTPException(status_code=400, detail="path is required")
        try:
            commit = await stack.spaces.delete_asset(
                actor.id,
                space_id,
                path,
                message=str(body.get("message", "") or ""),
                ref=str(body.get("ref", "main") or "main"),
            )
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc))
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        return {"commit": _jsonable(commit)}

    @app.post("/platform/spaces/{space_id}/refs/list")
    async def platform_list_refs(space_id: str, req: Request):
        body = await _body(req)
        await _require_space_read(req, body, space_id)
        refs = await stack.spaces.list_refs(space_id)
        return {"refs": _jsonable(refs)}

    @app.post("/platform/spaces/{space_id}/refs/create")
    async def platform_create_ref(space_id: str, req: Request):
        body = await _body(req)
        await _require_space_owner_or_admin(req, body, space_id)
        ref = await stack.spaces.create_ref(
            space_id,
            str(body.get("name", "") or "").strip(),
            RefKind(str(body.get("kind", RefKind.BRANCH.value) or RefKind.BRANCH.value)),
            from_ref=str(body.get("from_ref", "main") or "main"),
        )
        return {"ref": _jsonable(ref)}

    @app.post("/platform/spaces/{space_id}/refs/delete")
    async def platform_delete_ref(space_id: str, req: Request):
        body = await _body(req)
        await _require_space_owner_or_admin(req, body, space_id)
        name = str(body.get("name", "") or "").strip()
        if not name:
            raise HTTPException(status_code=400, detail="name is required")
        return {"ok": await stack.spaces.delete_ref(space_id, name)}

    @app.post("/platform/spaces/{space_id}/history")
    async def platform_space_history(space_id: str, req: Request):
        body = await _body(req)
        await _require_space_read(req, body, space_id)
        commits = await stack.spaces.get_history(
            space_id,
            path=str(body.get("path", "") or ""),
            limit=int(body.get("limit", 20) or 20),
        )
        return {"commits": _jsonable(commits)}

    @app.post("/platform/spaces/{space_id}/commits/{commit_id}")
    async def platform_get_commit(space_id: str, commit_id: str, req: Request):
        body = await _body(req)
        await _require_space_read(req, body, space_id)
        commit = await stack.spaces.get_commit(space_id, commit_id)
        if commit is None:
            raise HTTPException(status_code=404, detail=f"Commit '{commit_id}' not found")
        return {"commit": _jsonable(commit)}

    @app.post("/platform/executions/start")
    async def platform_start_execution(req: Request):
        body = await _body(req)
        actor = await _resolve_actor(req, body)
        request = ExecutionRequest(
            user_id=actor.id,
            space_id=str(body.get("space_id", "") or "").strip(),
            asset_path=str(body.get("asset_path", "") or "").strip(),
            ref=str(body.get("ref", "main") or "main"),
            runtime_profile_id=str(body.get("runtime_profile_id", "") or ""),
            credential_names=list(body.get("credential_names", []) or []),
            inputs=body.get("inputs", {}) or {},
            metadata=body.get("metadata", {}) or {},
        )
        env = None
        if body.get("resolve_credentials", False):
            env = await stack.secrets.resolve_credentials(
                actor.id,
                names=request.credential_names,
                space_id=body.get("secret_space_id") or None,
            )
        try:
            record = await stack.runtime.start_execution(request, env=env)
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return {"execution": _jsonable(record)}

    @app.post("/platform/executions/list")
    async def platform_list_executions(req: Request):
        body = await _body(req)
        if _is_internal(req):
            user_id = str(body.get("user_id", "") or "").strip() or None
        else:
            actor = await _require_user(req)
            requested_user_id = str(body.get("user_id", "") or "").strip()
            if requested_user_id and requested_user_id != actor.id and _role_value(actor) != UserRole.ADMIN.value:
                raise HTTPException(status_code=403, detail="Execution listing denied")
            user_id = requested_user_id or (None if _role_value(actor) == UserRole.ADMIN.value else actor.id)
        status = body.get("status")
        executions = await stack.runtime.list_executions(
            user_id=user_id,
            space_id=str(body.get("space_id", "") or "").strip() or None,
            status=ExecutionState(str(status)) if status else None,
            offset=int(body.get("offset", 0) or 0),
            limit=int(body.get("limit", 50) or 50),
        )
        return {"executions": _jsonable(executions)}

    @app.post("/platform/executions/{execution_id}")
    async def platform_get_execution(execution_id: str, req: Request):
        body = await _body(req)
        record = await stack.runtime.get_execution(execution_id)
        if record is None:
            raise HTTPException(status_code=404, detail=f"Execution '{execution_id}' not found")
        if not _is_internal(req):
            actor = await _require_user(req)
            if record.user_id != actor.id and _role_value(actor) != UserRole.ADMIN.value:
                raise HTTPException(status_code=403, detail="Execution access denied")
        elif body.get("user_id"):
            actor = await _resolve_actor(req, body)
            if record.user_id != actor.id and _role_value(actor) != UserRole.ADMIN.value:
                raise HTTPException(status_code=403, detail="Execution access denied")
        return {"execution": _jsonable(record)}

    @app.post("/platform/executions/{execution_id}/cancel")
    async def platform_cancel_execution(execution_id: str, req: Request):
        body = await _body(req)
        record = await stack.runtime.get_execution(execution_id)
        if record is None:
            raise HTTPException(status_code=404, detail=f"Execution '{execution_id}' not found")
        if not _is_internal(req):
            actor = await _require_user(req)
            if record.user_id != actor.id and _role_value(actor) != UserRole.ADMIN.value:
                raise HTTPException(status_code=403, detail="Execution cancellation denied")
        elif body.get("user_id"):
            actor = await _resolve_actor(req, body)
            if record.user_id != actor.id and _role_value(actor) != UserRole.ADMIN.value:
                raise HTTPException(status_code=403, detail="Execution cancellation denied")
        return {"ok": await stack.runtime.cancel_execution(execution_id)}

    @app.post("/platform/executions/{execution_id}/logs")
    async def platform_execution_logs(execution_id: str, req: Request):
        body = await _body(req)
        record = await stack.runtime.get_execution(execution_id)
        if record is None:
            raise HTTPException(status_code=404, detail=f"Execution '{execution_id}' not found")
        if not _is_internal(req):
            actor = await _require_user(req)
            if record.user_id != actor.id and _role_value(actor) != UserRole.ADMIN.value:
                raise HTTPException(status_code=403, detail="Execution log access denied")
        elif body.get("user_id"):
            actor = await _resolve_actor(req, body)
            if record.user_id != actor.id and _role_value(actor) != UserRole.ADMIN.value:
                raise HTTPException(status_code=403, detail="Execution log access denied")
        logs = await stack.runtime.get_logs(execution_id, tail=int(body.get("tail", 100) or 100))
        return {"logs": logs}
