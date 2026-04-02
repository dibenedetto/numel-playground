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
    network_name: str = ""
    workspace_mount_root: str = "/workspace"
    artifacts_mount_root: str = "/artifacts"
