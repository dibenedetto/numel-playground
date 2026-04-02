"""Load the active platform backend from a JSON config file."""

from __future__ import annotations

import json
import os
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


DEFAULT_PLATFORM_CONFIG_FILENAME = "platform_backend.json"
DEFAULT_PLATFORM_BACKEND = "local"


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
    backend = str(raw.get("backend", DEFAULT_PLATFORM_BACKEND) or DEFAULT_PLATFORM_BACKEND).strip().lower()
    if backend not in {"local", "prod"}:
        raise ValueError(f"Unsupported platform backend '{backend}'")
    raw["backend"] = backend
    return raw


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
