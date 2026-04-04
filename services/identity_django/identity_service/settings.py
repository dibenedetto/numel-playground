from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import unquote, urlparse


BASE_DIR = Path(__file__).resolve().parent.parent


def _env(name: str, default: str = "") -> str:
    return str(os.getenv(name, default) or default)


SECRET_KEY = _env("NUMEL_IDENTITY_SECRET_KEY", "numel-django-identity-dev-key")
DEBUG = _env("NUMEL_IDENTITY_DEBUG", "0").strip().lower() in {"1", "true", "yes", "on"}
ALLOWED_HOSTS = [
    host.strip()
    for host in _env("NUMEL_IDENTITY_ALLOWED_HOSTS", "*").split(",")
    if host.strip()
]

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "platform_identity",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.common.CommonMiddleware",
]

ROOT_URLCONF = "identity_service.urls"
WSGI_APPLICATION = "identity_service.wsgi.application"
ASGI_APPLICATION = "identity_service.asgi.application"

AUTH_USER_MODEL = "platform_identity.PlatformUser"

USE_TZ = True
TIME_ZONE = "UTC"
LANGUAGE_CODE = "en-us"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
]

NUMEL_IDENTITY_BOOTSTRAP_FIRST_USER_AS_ADMIN = _env(
    "NUMEL_IDENTITY_BOOTSTRAP_FIRST_USER_AS_ADMIN",
    "1",
).strip().lower() in {"1", "true", "yes", "on"}


def _database_config() -> dict:
    database_url = _env("DATABASE_URL", "").strip()
    if database_url:
        normalized = database_url
        if normalized.startswith("postgres://"):
            normalized = "postgresql://" + normalized[len("postgres://"):]
        if normalized.startswith("postgresql+psycopg://"):
            normalized = "postgresql://" + normalized[len("postgresql+psycopg://"):]
        if normalized.startswith("postgresql://"):
            parsed = urlparse(normalized)
            return {
                "ENGINE": "django.db.backends.postgresql",
                "NAME": unquote((parsed.path or "/").lstrip("/")),
                "USER": unquote(parsed.username or ""),
                "PASSWORD": unquote(parsed.password or ""),
                "HOST": parsed.hostname or "",
                "PORT": str(parsed.port or "5432"),
            }
        if normalized.startswith("sqlite:///"):
            return {
                "ENGINE": "django.db.backends.sqlite3",
                "NAME": str(Path(normalized[len("sqlite:///"):]).resolve()),
            }

    default_sqlite = Path(_env("NUMEL_IDENTITY_SQLITE_PATH", str(BASE_DIR / "storage" / "identity.sqlite3"))).resolve()
    default_sqlite.parent.mkdir(parents=True, exist_ok=True)
    return {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": str(default_sqlite),
    }


DATABASES = {
    "default": _database_config(),
}
