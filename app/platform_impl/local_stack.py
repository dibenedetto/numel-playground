"""Assembly helpers for the fully working local platform reference backend."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

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
from .db_secrets import DbSecretsProvider
from .docker_runtime import DockerRuntimeProvider
from .git_space_store import GitSpaceStore
from .local_identity import LocalIdentityProvider


@dataclass
class LocalPlatformStack:
    db_config: DatabaseConfig
    identity_config: LocalIdentityConfig
    git_config: GitStorageConfig
    artifact_config: ArtifactStorageConfig
    secrets_config: SecretsConfig
    docker_config: DockerRuntimeConfig
    audit_log: DbAuditLog
    execution_registry: DbExecutionRegistry
    git_store: GitSpaceStore
    identity: LocalIdentityProvider
    friend_graph: DbFriendGraphProvider
    spaces: DbGitSpaceProvider
    secrets: DbSecretsProvider
    runtime: DockerRuntimeProvider
    workspace_manager: Any = None

    def describe(self) -> Dict[str, str]:
        return {
            "identity": self.identity.__class__.__name__,
            "friend_graph": self.friend_graph.__class__.__name__,
            "spaces": self.spaces.__class__.__name__,
            "git_store": self.git_store.__class__.__name__,
            "secrets": self.secrets.__class__.__name__,
            "runtime": self.runtime.__class__.__name__,
            "execution_registry": self.execution_registry.__class__.__name__,
            "audit_log": self.audit_log.__class__.__name__,
        }


def build_local_platform_stack(
    db_config: DatabaseConfig | None = None,
    identity_config: LocalIdentityConfig | None = None,
    git_config: GitStorageConfig | None = None,
    artifact_config: ArtifactStorageConfig | None = None,
    secrets_config: SecretsConfig | None = None,
    docker_config: DockerRuntimeConfig | None = None,
    workspace_manager: Any = None,
) -> LocalPlatformStack:
    """Create the fully working local reference backend."""
    db_config = db_config or DatabaseConfig()
    identity_config = identity_config or LocalIdentityConfig()
    git_config = git_config or GitStorageConfig()
    artifact_config = artifact_config or ArtifactStorageConfig()
    secrets_config = secrets_config or SecretsConfig()
    docker_config = docker_config or DockerRuntimeConfig()

    audit_log = DbAuditLog(db_config)
    execution_registry = DbExecutionRegistry(db_config)
    git_store = GitSpaceStore(git_config)
    identity = LocalIdentityProvider(identity_config, db_config=db_config, audit_log=audit_log)
    friend_graph = DbFriendGraphProvider(db_config, audit_log=audit_log)
    spaces = DbGitSpaceProvider(
        db_config=db_config,
        git_store=git_store,
        artifact_config=artifact_config,
        friend_graph=friend_graph,
        audit_log=audit_log,
    )
    secrets = DbSecretsProvider(secrets_config, db_config=db_config, audit_log=audit_log)
    runtime = DockerRuntimeProvider(
        config=docker_config,
        git_store=git_store,
        execution_registry=execution_registry,
        artifact_config=artifact_config,
        audit_log=audit_log,
        space_provider=spaces,
        workspace_manager=workspace_manager,
    )

    return LocalPlatformStack(
        db_config=db_config,
        identity_config=identity_config,
        git_config=git_config,
        artifact_config=artifact_config,
        secrets_config=secrets_config,
        docker_config=docker_config,
        audit_log=audit_log,
        execution_registry=execution_registry,
        git_store=git_store,
        identity=identity,
        friend_graph=friend_graph,
        spaces=spaces,
        secrets=secrets,
        runtime=runtime,
        workspace_manager=workspace_manager,
    )
