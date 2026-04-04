"""Configuration models for Numel's local reference backend."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class DatabaseConfig:
    url: str = "sqlite:///storage/platform.db"
    echo_sql: bool = False
    app_name: str = "numel"
    pool_size: int = 10


@dataclass
class LocalIdentityConfig:
    token_ttl_seconds: float = 604800.0
    password_iterations: int = 390000
    bootstrap_first_user_as_admin: bool = True


@dataclass
class GitStorageConfig:
    repos_root: str = "storage/spaces"
    default_branch: str = "main"
    bare_repositories: bool = False


@dataclass
class ArtifactStorageConfig:
    backend: str = "filesystem"
    root_path: str = "storage/artifacts"
    bucket_name: str = ""


@dataclass
class SecretsConfig:
    backend: str = "database"
    vault_url: str = ""
    key_prefix: str = "numel"


@dataclass
class DockerRuntimeConfig:
    base_url: str = "unix:///var/run/docker.sock"
    default_image: str = "numel-runtime:latest"
    default_gpu_image: str = "numel-runtime:cuda"
    network_name: str = ""
    workspace_mount_root: str = "/workspace"
    artifacts_mount_root: str = "/artifacts"
    api_version: str = "v1.41"
    healthcheck_path: str = "/_ping"
    timeout_seconds: float = 30.0
    verify_tls: bool = True
    require_available_on_startup: bool = True
    container_name_prefix: str = "numel-exec"
    default_command: str = ""
    auto_remove: bool = False
    gpu_driver: str = "nvidia"
    gpu_device_count: int = -1
