from __future__ import annotations

import django.contrib.auth.models
import django.contrib.auth.validators
import django.utils.timezone
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.CreateModel(
            name="PlatformUser",
            fields=[
                ("password", models.CharField(max_length=128, verbose_name="password")),
                ("last_login", models.DateTimeField(blank=True, null=True, verbose_name="last login")),
                ("is_superuser", models.BooleanField(default=False, help_text="Designates that this user has all permissions without explicitly assigning them.", verbose_name="superuser status")),
                ("username", models.CharField(
                    error_messages={"unique": "A user with that username already exists."},
                    help_text="Required. 150 characters or fewer. Letters, digits and @/./+/-/_ only.",
                    max_length=150,
                    unique=True,
                    validators=[django.contrib.auth.validators.UnicodeUsernameValidator()],
                    verbose_name="username",
                )),
                ("first_name", models.CharField(blank=True, max_length=150, verbose_name="first name")),
                ("last_name", models.CharField(blank=True, max_length=150, verbose_name="last name")),
                ("is_staff", models.BooleanField(default=False, help_text="Designates whether the user can log into this admin site.", verbose_name="staff status")),
                ("is_active", models.BooleanField(default=True, help_text="Designates whether this user should be treated as active. Unselect this instead of deleting accounts.", verbose_name="active")),
                ("date_joined", models.DateTimeField(default=django.utils.timezone.now, verbose_name="date joined")),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("email", models.EmailField(max_length=254, unique=True)),
                ("role", models.CharField(choices=[("admin", "Admin"), ("user", "User"), ("viewer", "Viewer")], default="user", max_length=16)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("groups", models.ManyToManyField(blank=True, help_text="The groups this user belongs to. A user will get all permissions granted to each of their groups.", related_name="platformuser_set", related_query_name="platformuser", to="auth.group", verbose_name="groups")),
                ("user_permissions", models.ManyToManyField(blank=True, help_text="Specific permissions for this user.", related_name="platformuser_set", related_query_name="platformuser", to="auth.permission", verbose_name="user permissions")),
            ],
            options={
                "verbose_name": "user",
                "verbose_name_plural": "users",
                "abstract": False,
            },
            managers=[
                ("objects", django.contrib.auth.models.UserManager()),
            ],
        ),
        migrations.CreateModel(
            name="PlatformUserProfile",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("display_name", models.CharField(blank=True, default="", max_length=255)),
                ("bio", models.TextField(blank=True, default="")),
                ("avatar_url", models.URLField(blank=True, default="")),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("user", models.OneToOneField(on_delete=models.deletion.CASCADE, related_name="platform_profile", to="platform_identity.platformuser")),
            ],
        ),
        migrations.CreateModel(
            name="PlatformUserQuota",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("cpu_seconds_remaining", models.FloatField(default=36000.0)),
                ("max_concurrent_runs", models.IntegerField(default=5)),
                ("storage_bytes_remaining", models.BigIntegerField(default=1073741824)),
                ("max_loop_hours", models.FloatField(default=24.0)),
                ("gpu_hours_remaining", models.FloatField(default=0.0)),
                ("max_spaces", models.IntegerField(default=50)),
                ("max_assets_per_space", models.IntegerField(default=10000)),
                ("user", models.OneToOneField(on_delete=models.deletion.CASCADE, related_name="platform_quota", to="platform_identity.platformuser")),
            ],
        ),
        migrations.CreateModel(
            name="PlatformAuthToken",
            fields=[
                ("token", models.CharField(max_length=128, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("expires_at", models.DateTimeField()),
                ("user", models.ForeignKey(on_delete=models.deletion.CASCADE, related_name="platform_tokens", to="platform_identity.platformuser")),
            ],
        ),
    ]
