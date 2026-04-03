"""Local reference backend for Numel's platform abstractions."""

from .config import (
    ArtifactStorageConfig,
    DatabaseConfig,
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
from .docker_runtime import DockerRuntimeProvider
from .git_space_store import GitSpaceStore
from .local_identity import LocalIdentityProvider
from .local_stack import LocalPlatformStack, build_local_platform_stack
from .migrations import MigrationStatus, ensure_platform_schema, get_platform_schema_status

__all__ = [
    "ArtifactStorageConfig",
    "DatabaseConfig",
    "DbAuditLog",
    "DbExecutionRegistry",
    "DbFriendGraphProvider",
    "DbGitSpaceProvider",
    "DbSecretsProvider",
    "DockerRuntimeConfig",
    "DockerRuntimeProvider",
    "GitSpaceStore",
    "GitStorageConfig",
    "LocalIdentityConfig",
    "LocalIdentityProvider",
    "LocalPlatformStack",
    "MigrationStatus",
    "SecretsConfig",
    "VaultSecretsProvider",
    "build_local_platform_stack",
    "ensure_platform_schema",
    "get_platform_schema_status",
]
