"""Configuration models for Numel's local reference backend."""

from __future__ import annotations

from dataclasses import dataclass, field


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
    healthcheck_path: str = "/v1/sys/health"
    timeout_seconds: float = 10.0
    verify_tls: bool = True
    token: str = ""
    token_env_var: str = "NUMEL_VAULT_TOKEN"
    kv_mount: str = "secret"
    kv_api_prefix: str = "/v1"
    require_available_on_startup: bool = False


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
    max_execution_duration_seconds: float = 3600.0
    stop_grace_seconds: int = 5
    remove_containers_on_completion: bool = True
    cleanup_snapshots_on_completion: bool = True
    artifact_retention_seconds: float = 604800.0
    retention_scan_interval_seconds: float = 60.0
    read_only_root_filesystem: bool = True
    drop_capabilities: list[str] = field(default_factory=lambda: ["ALL"])
    security_opts: list[str] = field(default_factory=lambda: ["no-new-privileges"])
    pids_limit: int = 256
    shm_size_bytes: int = 67108864
    tmpfs_mounts: dict[str, str] = field(default_factory=lambda: {
        "/tmp": "rw,noexec,nosuid,nodev,size=64m",
        "/run": "rw,noexec,nosuid,nodev,size=16m",
    })
    run_as_user: str = ""
