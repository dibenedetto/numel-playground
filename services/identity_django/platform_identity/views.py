from __future__ import annotations

import json
from typing import Any

from django.conf import settings
from django.contrib.auth import authenticate
from django.db import IntegrityError
from django.http import HttpRequest, HttpResponseNotAllowed, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone

from .models import PlatformAuthToken, PlatformUser, PlatformUserProfile, PlatformUserQuota


def _json_body(request: HttpRequest) -> dict[str, Any]:
    if not request.body:
        return {}
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _error(detail: str, status: int) -> JsonResponse:
    return JsonResponse({"detail": detail}, status=status)


def _clean_expired_tokens() -> None:
    PlatformAuthToken.objects.filter(expires_at__lte=timezone.now()).delete()


def _token_from_request(request: HttpRequest, body: dict[str, Any] | None = None) -> str:
    auth_header = str(request.headers.get("Authorization", "") or "").strip()
    if auth_header.lower().startswith("bearer "):
        return auth_header[7:].strip()
    payload = body or {}
    return str(payload.get("token", "") or "").strip()


def _resolve_token_user(request: HttpRequest, body: dict[str, Any] | None = None) -> PlatformUser | None:
    _clean_expired_tokens()
    token = _token_from_request(request, body)
    if not token:
        return None
    auth_token = (
        PlatformAuthToken.objects.select_related("user")
        .filter(token=token, expires_at__gt=timezone.now())
        .first()
    )
    if auth_token is None or not auth_token.user.is_active:
        return None
    return auth_token.user


def _get_user_or_none(user_id: str) -> PlatformUser | None:
    try:
        return PlatformUser.objects.get(pk=user_id)
    except PlatformUser.DoesNotExist:
        return None


def _ensure_profile(user: PlatformUser) -> PlatformUserProfile:
    profile, _ = PlatformUserProfile.objects.get_or_create(
        user=user,
        defaults={"display_name": user.username},
    )
    return profile


def _ensure_quota(user: PlatformUser) -> PlatformUserQuota:
    quota, _ = PlatformUserQuota.objects.get_or_create(user=user)
    return quota


def _user_payload(user: PlatformUser) -> dict[str, Any]:
    return {
        "id": str(user.pk),
        "username": user.username,
        "email": user.email,
        "role": user.role,
        "active": bool(user.is_active),
        "created_at": user.date_joined.timestamp() if user.date_joined else 0.0,
        "metadata": user.metadata or {},
    }


def _profile_payload(profile: PlatformUserProfile) -> dict[str, Any]:
    return {
        "user_id": str(profile.user_id),
        "display_name": profile.display_name or "",
        "bio": profile.bio or "",
        "avatar_url": profile.avatar_url or "",
        "metadata": profile.metadata or {},
    }


def _quota_payload(quota: PlatformUserQuota) -> dict[str, Any]:
    return {
        "user_id": str(quota.user_id),
        "cpu_seconds_remaining": quota.cpu_seconds_remaining,
        "max_concurrent_runs": quota.max_concurrent_runs,
        "storage_bytes_remaining": quota.storage_bytes_remaining,
        "max_loop_hours": quota.max_loop_hours,
        "gpu_hours_remaining": quota.gpu_hours_remaining,
        "max_spaces": quota.max_spaces,
        "max_assets_per_space": quota.max_assets_per_space,
    }


def _bundle(user: PlatformUser) -> dict[str, Any]:
    profile = _ensure_profile(user)
    quota = _ensure_quota(user)
    return {
        "user": _user_payload(user),
        "profile": _profile_payload(profile),
        "quota": _quota_payload(quota),
    }


def _role_from_payload(raw_role: str) -> str:
    role = str(raw_role or PlatformUser.Role.USER).strip().lower()
    if role not in {choice for choice, _ in PlatformUser.Role.choices}:
        return PlatformUser.Role.USER
    return role


@csrf_exempt
def auth_status(request: HttpRequest) -> JsonResponse:
    if request.method not in {"GET", "POST"}:
        return HttpResponseNotAllowed(["GET", "POST"])
    has_users = PlatformUser.objects.filter(is_active=True).exists()
    return JsonResponse({"enabled": True, "provider": "django", "has_users": has_users})


@csrf_exempt
def auth_login(request: HttpRequest) -> JsonResponse:
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    body = _json_body(request)
    username = str(body.get("username", "") or "").strip()
    password = str(body.get("password", "") or "")
    user = authenticate(request, username=username, password=password)
    if user is None or not user.is_active:
        return _error("Invalid credentials", 401)
    token = PlatformAuthToken.mint(user)
    return JsonResponse({"token": token.token, "user": _user_payload(user)})


@csrf_exempt
def auth_authenticate(request: HttpRequest) -> JsonResponse:
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    body = _json_body(request)
    user = _resolve_token_user(request, body)
    if user is None:
        return _error("Not authenticated", 401)
    return JsonResponse({"user": _user_payload(user)})


@csrf_exempt
def auth_logout(request: HttpRequest) -> JsonResponse:
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    body = _json_body(request)
    token = _token_from_request(request, body)
    deleted, _ = PlatformAuthToken.objects.filter(token=token).delete()
    return JsonResponse({"ok": bool(deleted)})


@csrf_exempt
def auth_change_password(request: HttpRequest) -> JsonResponse:
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    body = _json_body(request)
    user = _get_user_or_none(str(body.get("user_id", "") or "").strip())
    if user is None:
        return _error("Not found", 404)
    current_password = str(body.get("current_password", "") or "")
    new_password = str(body.get("new_password", "") or "")
    if not current_password or not new_password or not user.check_password(current_password):
        return _error("Current password is incorrect", 403)
    user.set_password(new_password)
    user.save(update_fields=["password"])
    PlatformAuthToken.objects.filter(user=user).delete()
    return JsonResponse({"ok": True})


@csrf_exempt
def users_create(request: HttpRequest) -> JsonResponse:
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    body = _json_body(request)
    username = str(body.get("username", "") or "").strip()
    email = str(body.get("email", "") or "").strip()
    password = str(body.get("password", "") or "")
    if not username or not email or not password:
        return _error("Missing required fields", 400)
    if PlatformUser.objects.filter(username=username).exists():
        return _error("Username already exists", 409)
    if PlatformUser.objects.filter(email=email).exists():
        return _error("Email already exists", 409)

    active_user_count = PlatformUser.objects.filter(is_active=True).count()
    role = (
        PlatformUser.Role.ADMIN
        if active_user_count == 0 and settings.NUMEL_IDENTITY_BOOTSTRAP_FIRST_USER_AS_ADMIN
        else PlatformUser.Role.USER
    )
    user = PlatformUser(username=username, email=email, role=role, metadata={})
    user.sync_role_flags()
    user.set_password(password)
    try:
        user.save()
    except IntegrityError:
        return _error("Username or email already exists", 409)
    _ensure_profile(user)
    _ensure_quota(user)
    return JsonResponse({"user": _user_payload(user)})


@csrf_exempt
def users_by_username(request: HttpRequest) -> JsonResponse:
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    body = _json_body(request)
    username = str(body.get("username", "") or "").strip()
    try:
        user = PlatformUser.objects.get(username=username)
    except PlatformUser.DoesNotExist:
        return _error("Not found", 404)
    return JsonResponse({"user": _user_payload(user)})


@csrf_exempt
def users_list(request: HttpRequest) -> JsonResponse:
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    body = _json_body(request)
    offset = max(int(body.get("offset", 0) or 0), 0)
    limit = max(int(body.get("limit", 50) or 50), 1)
    active_only = bool(body.get("active_only", True))
    queryset = PlatformUser.objects.all().order_by("date_joined")
    if active_only:
        queryset = queryset.filter(is_active=True)
    users = list(queryset[offset:offset + limit])
    return JsonResponse({"users": [_user_payload(user) for user in users], "count": queryset.count()})


@csrf_exempt
def users_get(request: HttpRequest, user_id) -> JsonResponse:
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    user = _get_user_or_none(str(user_id))
    if user is None:
        return _error("Not found", 404)
    return JsonResponse(_bundle(user))


@csrf_exempt
def users_update(request: HttpRequest, user_id) -> JsonResponse:
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    user = _get_user_or_none(str(user_id))
    if user is None:
        return _error("Not found", 404)
    body = _json_body(request)
    if "username" in body:
        user.username = str(body.get("username", "") or user.username).strip() or user.username
    if "email" in body:
        user.email = str(body.get("email", "") or user.email).strip() or user.email
    if "role" in body:
        user.role = _role_from_payload(str(body.get("role", "") or user.role))
        user.sync_role_flags()
    if "active" in body:
        user.is_active = bool(body.get("active", user.is_active))
    if "metadata" in body and isinstance(body.get("metadata"), dict):
        user.metadata = body["metadata"]
    try:
        user.save()
    except IntegrityError:
        return _error("Username or email already exists", 409)
    return JsonResponse({"user": _user_payload(user)})


@csrf_exempt
def users_delete(request: HttpRequest, user_id) -> JsonResponse:
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    user = _get_user_or_none(str(user_id))
    if user is None:
        return _error("Not found", 404)
    user.is_active = False
    user.save(update_fields=["is_active"])
    PlatformAuthToken.objects.filter(user=user).delete()
    return JsonResponse({"ok": True})


@csrf_exempt
def users_profile(request: HttpRequest, user_id) -> JsonResponse:
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    user = _get_user_or_none(str(user_id))
    if user is None:
        return _error("Not found", 404)
    body = _json_body(request)
    profile = _ensure_profile(user)
    if "display_name" in body:
        profile.display_name = str(body.get("display_name", "") or "")
    if "bio" in body:
        profile.bio = str(body.get("bio", "") or "")
    if "avatar_url" in body:
        profile.avatar_url = str(body.get("avatar_url", "") or "")
    if "metadata" in body and isinstance(body.get("metadata"), dict):
        profile.metadata = body["metadata"]
    profile.save()
    return JsonResponse({"profile": _profile_payload(profile)})


@csrf_exempt
def users_quota(request: HttpRequest, user_id) -> JsonResponse:
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    user = _get_user_or_none(str(user_id))
    if user is None:
        return _error("Not found", 404)
    body = _json_body(request)
    quota = _ensure_quota(user)
    for field_name in (
        "cpu_seconds_remaining",
        "max_concurrent_runs",
        "storage_bytes_remaining",
        "max_loop_hours",
        "gpu_hours_remaining",
        "max_spaces",
        "max_assets_per_space",
    ):
        if field_name in body:
            setattr(quota, field_name, body[field_name])
    quota.save()
    return JsonResponse({"quota": _quota_payload(quota)})
