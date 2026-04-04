"""Load the active platform backend from a JSON config file."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Mapping

from platform_local import (
    ArtifactStorageConfig,
    DatabaseConfig,
    DockerRuntimeConfig,
    GitStorageConfig,
    LocalIdentityConfig,
    SecretsConfig,
    build_local_platform_stack,
)
from platform_prod import DjangoIdentityConfig, build_db_git_platform_stack
from runtime_settings import get_runtime_settings


DEFAULT_PLATFORM_CONFIG_FILENAME = "platform_backend.json"
DEFAULT_PLATFORM_BACKEND = "local"
_ENV_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


def resolve_platform_backend_config_path(path: str | None = None) -> str:
    """Resolve the JSON config path used to select the active platform backend."""
    if path:
        return str(Path(path).resolve())
    env_path = os.getenv("NUMEL_PLATFORM_CONFIG", "").strip()
    if env_path:
        return str(Path(env_path).resolve())
    return str((Path(__file__).resolve().parent / DEFAULT_PLATFORM_CONFIG_FILENAME).resolve())


def load_platform_backend_config(path: str | None = None) -> dict[str, Any]:
    """Load platform backend settings from disk."""
    resolved_path = resolve_platform_backend_config_path(path)
    config_path = Path(resolved_path)
    if not config_path.exists():
        raise FileNotFoundError(
            f"Platform backend config file not found: {resolved_path}"
        )
    raw = json.loads(config_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("Platform backend config must be a JSON object")
    raw = _expand_platform_env_values(raw)
    backend = str(raw.get("backend", DEFAULT_PLATFORM_BACKEND) or DEFAULT_PLATFORM_BACKEND).strip().lower()
    if backend not in {"local", "prod"}:
        raise ValueError(f"Unsupported platform backend '{backend}'")
    raw["backend"] = backend
    return _normalize_platform_backend_config(raw)


def _expand_platform_env_string(value: str) -> str:
    def replace(match: re.Match[str]) -> str:
        name = match.group(1)
        return os.getenv(name, "")

    return _ENV_PATTERN.sub(replace, value)


def _expand_platform_env_values(value: Any) -> Any:
    if isinstance(value, str):
        return _expand_platform_env_string(value)
    if isinstance(value, list):
        return [_expand_platform_env_values(item) for item in value]
    if isinstance(value, dict):
        return {key: _expand_platform_env_values(item) for key, item in value.items()}
    return value


def _resolve_platform_path(raw_path: str) -> str:
    settings = get_runtime_settings()
    candidate = Path(str(raw_path))
    if candidate.is_absolute():
        return str(candidate.resolve())

    parts = candidate.parts
    if parts and str(parts[0]).lower() == "storage":
        relative_parts = parts[1:]
        target = settings.data_root.joinpath(*relative_parts) if relative_parts else settings.data_root
        return str(target.resolve())
    return str((settings.project_root / candidate).resolve())


def _normalize_sqlite_url(url: str) -> str:
    prefix = "sqlite:///"
    if not isinstance(url, str) or not url.startswith(prefix):
        return url
    path_part = url[len(prefix):]
    if not path_part:
        return url
    normalized = _resolve_platform_path(path_part)
    return f"{prefix}{normalized.replace(os.sep, '/')}"


def _normalize_platform_backend_config(config: Mapping[str, Any]) -> dict[str, Any]:
    normalized = json.loads(json.dumps(config))
    for backend_name in ("local", "prod"):
        section = normalized.get(backend_name)
        if not isinstance(section, dict):
            continue
        database = section.get("database")
        if isinstance(database, dict) and "url" in database:
            database["url"] = _normalize_sqlite_url(str(database["url"]))
        git = section.get("git")
        if isinstance(git, dict) and git.get("repos_root"):
            git["repos_root"] = _resolve_platform_path(str(git["repos_root"]))
        artifacts = section.get("artifacts")
        if isinstance(artifacts, dict) and artifacts.get("root_path"):
            artifacts["root_path"] = _resolve_platform_path(str(artifacts["root_path"]))
    return normalized


def _section(config: Mapping[str, Any], name: str) -> Mapping[str, Any]:
    value = config.get(name, {})
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ValueError(f"Platform backend section '{name}' must be an object")
    return value


def _build_dataclass(cls, data: Mapping[str, Any]):
    return cls(**dict(data)) if data else cls()


def build_platform_stack_from_config(
    config: Mapping[str, Any],
    *,
    workspace_manager: Any = None,
):
    """Instantiate the configured backend using the shared platform contract."""
    backend = str(config.get("backend", DEFAULT_PLATFORM_BACKEND) or DEFAULT_PLATFORM_BACKEND).strip().lower()
    section = _section(config, backend)
    db_config = _build_dataclass(DatabaseConfig, _section(section, "database"))
    git_config = _build_dataclass(GitStorageConfig, _section(section, "git"))
    artifact_config = _build_dataclass(ArtifactStorageConfig, _section(section, "artifacts"))
    secrets_config = _build_dataclass(SecretsConfig, _section(section, "secrets"))
    runtime_config = _build_dataclass(DockerRuntimeConfig, _section(section, "runtime"))

    if backend == "local":
        identity_config = _build_dataclass(LocalIdentityConfig, _section(section, "identity"))
        return build_local_platform_stack(
            db_config=db_config,
            identity_config=identity_config,
            git_config=git_config,
            artifact_config=artifact_config,
            secrets_config=secrets_config,
            docker_config=runtime_config,
            workspace_manager=workspace_manager,
        )

    identity_config = _build_dataclass(DjangoIdentityConfig, _section(section, "identity"))
    return build_db_git_platform_stack(
        db_config=db_config,
        identity_config=identity_config,
        git_config=git_config,
        artifact_config=artifact_config,
        secrets_config=secrets_config,
        docker_config=runtime_config,
        workspace_manager=workspace_manager,
    )
