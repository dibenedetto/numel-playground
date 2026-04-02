"""Abstract platform domain for Numel.

This package defines the product-level concepts that the current local
implementation only approximates: users, profiles, friendships, spaces,
assets, permissions, credentials, and runtime executions.

Concrete backends such as local JSON/filesystem mocks, Django services,
PostgreSQL stores, or Docker-based runtimes should implement these
interfaces without leaking their own storage model into the rest of Numel.
"""

from .interfaces import (
    FriendGraphProvider,
    IdentityProvider,
    RuntimeProvider,
    SecretsProvider,
    SpaceProvider,
)
from .concrete import ConcretePlatformComponent, DbGitPlatformSpec, build_db_git_platform_spec
from .mock import MockPlatformLayer, MockPlatformStack, build_mock_platform_stack
from .models import (
    AclEntry,
    Capability,
    CredentialRecord,
    ExecutionRecord,
    ExecutionState,
    ExecutionRequest,
    Friendship,
    FriendshipStatus,
    PermissionPolicy,
    RefKind,
    RuntimeProfile,
    SecretScope,
    Space,
    SpaceAsset,
    SpaceCommit,
    SpaceRef,
    SubjectType,
    UsageQuota,
    UserAccount,
    UserProfile,
    UserRole,
    Visibility,
    AssetKind,
)

__all__ = [
    "AclEntry",
    "AssetKind",
    "Capability",
    "ConcretePlatformComponent",
    "CredentialRecord",
    "DbGitPlatformSpec",
    "ExecutionRecord",
    "ExecutionRequest",
    "ExecutionState",
    "FriendGraphProvider",
    "Friendship",
    "FriendshipStatus",
    "IdentityProvider",
    "MockPlatformLayer",
    "MockPlatformStack",
    "PermissionPolicy",
    "RefKind",
    "RuntimeProfile",
    "RuntimeProvider",
    "SecretScope",
    "SecretsProvider",
    "Space",
    "SpaceAsset",
    "SpaceCommit",
    "SpaceProvider",
    "SpaceRef",
    "SubjectType",
    "UsageQuota",
    "UserAccount",
    "UserProfile",
    "UserRole",
    "Visibility",
    "build_mock_platform_stack",
    "build_db_git_platform_spec",
]
