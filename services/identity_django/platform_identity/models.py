from __future__ import annotations

import secrets
import uuid
from datetime import timedelta

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone


class PlatformUser(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = "admin", "Admin"
        USER = "user", "User"
        VIEWER = "viewer", "Viewer"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)
    role = models.CharField(max_length=16, choices=Role.choices, default=Role.USER)
    metadata = models.JSONField(default=dict, blank=True)

    def sync_role_flags(self) -> None:
        is_admin = self.role == self.Role.ADMIN
        self.is_staff = is_admin
        self.is_superuser = is_admin


class PlatformUserProfile(models.Model):
    user = models.OneToOneField(PlatformUser, on_delete=models.CASCADE, related_name="platform_profile")
    display_name = models.CharField(max_length=255, default="", blank=True)
    bio = models.TextField(default="", blank=True)
    avatar_url = models.URLField(default="", blank=True)
    metadata = models.JSONField(default=dict, blank=True)


class PlatformUserQuota(models.Model):
    user = models.OneToOneField(PlatformUser, on_delete=models.CASCADE, related_name="platform_quota")
    cpu_seconds_remaining = models.FloatField(default=36000.0)
    max_concurrent_runs = models.IntegerField(default=5)
    storage_bytes_remaining = models.BigIntegerField(default=1_073_741_824)
    max_loop_hours = models.FloatField(default=24.0)
    gpu_hours_remaining = models.FloatField(default=0.0)
    max_spaces = models.IntegerField(default=50)
    max_assets_per_space = models.IntegerField(default=10_000)


class PlatformAuthToken(models.Model):
    token = models.CharField(max_length=128, primary_key=True)
    user = models.ForeignKey(PlatformUser, on_delete=models.CASCADE, related_name="platform_tokens")
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    @classmethod
    def mint(cls, user: PlatformUser, ttl_seconds: float = 604800.0) -> "PlatformAuthToken":
        now = timezone.now()
        return cls.objects.create(
            token=f"django_{user.pk}_{secrets.token_urlsafe(24)}",
            user=user,
            expires_at=now + timedelta(seconds=float(ttl_seconds or 0.0)),
        )
