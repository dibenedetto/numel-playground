"""Concrete platform implementations and reference backends for Numel."""

from .config import (
    ArtifactStorageConfig,
    DatabaseConfig,
    DjangoIdentityConfig,
    DockerRuntimeConfig,
    GitStorageConfig,
    LocalIdentityConfig,
    SecretsConfig,
)
from .db_audit import DbAuditLog
from .db_execution_registry import DbExecutionRegistry
from .db_friend_graph import DbFriendGraphProvider
from .db_git_spaces import DbGitSpaceProvider
from .db_secrets import DbSecretsProvider, VaultSecretsProvider
from .django_identity import DjangoIdentityProvider
from .docker_runtime import DockerRuntimeProvider
from .git_space_store import GitSpaceStore
from .local_identity import LocalIdentityProvider
from .local_stack import LocalPlatformStack, build_local_platform_stack
from .stack import DbGitPlatformStack, build_db_git_platform_stack

__all__ = [
    "ArtifactStorageConfig",
    "DatabaseConfig",
    "DbAuditLog",
    "DbExecutionRegistry",
    "DbFriendGraphProvider",
    "DbGitPlatformStack",
    "DbGitSpaceProvider",
    "DbSecretsProvider",
    "DjangoIdentityConfig",
    "DjangoIdentityProvider",
    "DockerRuntimeConfig",
    "DockerRuntimeProvider",
    "GitSpaceStore",
    "GitStorageConfig",
    "LocalIdentityConfig",
    "LocalIdentityProvider",
    "LocalPlatformStack",
    "SecretsConfig",
    "VaultSecretsProvider",
    "build_db_git_platform_stack",
    "build_local_platform_stack",
]
