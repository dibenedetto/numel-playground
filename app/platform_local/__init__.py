"""Local reference backend for Numel's platform abstractions.

Keep package imports lazy so shared modules can import local config/model code
without pulling in the whole local backend and its optional DB dependencies.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any


_EXPORTS = {
    "ArtifactStorageConfig": (".config", "ArtifactStorageConfig"),
    "DatabaseConfig": (".config", "DatabaseConfig"),
    "DockerRuntimeConfig": (".config", "DockerRuntimeConfig"),
    "GitStorageConfig": (".config", "GitStorageConfig"),
    "LocalIdentityConfig": (".config", "LocalIdentityConfig"),
    "SecretsConfig": (".config", "SecretsConfig"),
    "DbAuditLog": (".db_audit", "DbAuditLog"),
    "DbExecutionRegistry": (".db_execution_registry", "DbExecutionRegistry"),
    "DbFriendGraphProvider": (".db_friend_graph", "DbFriendGraphProvider"),
    "DbGitSpaceProvider": (".db_git_spaces", "DbGitSpaceProvider"),
    "DbSecretsProvider": (".db_secrets", "DbSecretsProvider"),
    "VaultSecretsProvider": (".db_secrets", "VaultSecretsProvider"),
    "DockerRuntimeProvider": (".docker_runtime", "DockerRuntimeProvider"),
    "GitSpaceStore": (".git_space_store", "GitSpaceStore"),
    "LocalIdentityProvider": (".local_identity", "LocalIdentityProvider"),
    "LocalPlatformStack": (".local_stack", "LocalPlatformStack"),
    "build_local_platform_stack": (".local_stack", "build_local_platform_stack"),
    "MigrationStatus": (".migrations", "MigrationStatus"),
    "ensure_platform_schema": (".migrations", "ensure_platform_schema"),
    "get_platform_schema_status": (".migrations", "get_platform_schema_status"),
}

__all__ = list(_EXPORTS)


def __getattr__(name: str) -> Any:
    target = _EXPORTS.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attr_name = target
    module = import_module(module_name, __name__)
    value = getattr(module, attr_name)
    globals()[name] = value
    return value
