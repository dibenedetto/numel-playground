# providers — Abstract interfaces for Numel's multi-tenant layer.
#
# These ABCs define the contracts for authentication, data storage, and
# workflow execution.  Concrete implementations live in providers_impl/.
# Numel's FastAPI routes depend ONLY on these interfaces, so swapping
# Django→Keycloak or Gitea→GitLab is a one-line config change.

from providers.auth      import AuthProvider
from providers.data      import DataProvider
from providers.execution import ExecutionProvider
from providers.models    import (
    User, Quota, Permission, AccessLevel, Role,
    Repo, FileEntry, Commit, Lock,
    ExecutionHandle, ExecutionStatus, ExecutionResult, ResourceLimits,
)

__all__ = [
    "AuthProvider", "DataProvider", "ExecutionProvider",
    "User", "Quota", "Permission", "AccessLevel", "Role",
    "Repo", "FileEntry", "Commit", "Lock",
    "ExecutionHandle", "ExecutionStatus", "ExecutionResult", "ResourceLimits",
]
