"""Concrete implementation targets for the abstract Numel platform domain.

This module does not implement the platform. Instead, it captures the chosen
deployment architecture so the rest of the codebase can consistently refer to
the intended concrete stack.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class ConcretePlatformComponent:
    name: str
    abstract_roles: List[str] = field(default_factory=list)
    implementation_hint: str = ""
    source_of_truth: str = ""
    responsibilities: List[str] = field(default_factory=list)
    notes: str = ""


@dataclass
class DbGitPlatformSpec:
    """Chosen concrete target: database-backed metadata + Git-backed content."""

    architecture_id: str = "db+git"
    production_database: str = "postgresql"
    development_database: str = "sqlite"
    git_layout: str = "one git repository per space"
    runtime_target: str = "docker"
    components: Dict[str, ConcretePlatformComponent] = field(default_factory=dict)

    def describe(self) -> Dict[str, Dict[str, Any]]:
        """Return a serializable summary of the selected concrete architecture."""
        return {
            key: {
                "abstract_roles": component.abstract_roles,
                "implementation_hint": component.implementation_hint,
                "source_of_truth": component.source_of_truth,
                "responsibilities": component.responsibilities,
                "notes": component.notes,
            }
            for key, component in self.components.items()
        }


def build_db_git_platform_spec() -> DbGitPlatformSpec:
    """Return the agreed concrete architecture for the next platform phase."""
    components = {
        "identity": ConcretePlatformComponent(
            name="identity",
            abstract_roles=["IdentityProvider"],
            implementation_hint="DjangoIdentityProvider",
            source_of_truth="database",
            responsibilities=[
                "user accounts",
                "authentication",
                "profiles",
                "roles",
                "quotas",
            ],
            notes="Production target is Django-backed auth; local development can keep a lighter mock implementation.",
        ),
        "friend_graph": ConcretePlatformComponent(
            name="friend_graph",
            abstract_roles=["FriendGraphProvider"],
            implementation_hint="DbFriendGraphProvider",
            source_of_truth="database",
            responsibilities=[
                "friend requests",
                "accepted friendships",
                "blocking",
                "protected visibility resolution",
            ],
            notes="Friendship is relational data and should not live in Git.",
        ),
        "space_catalog": ConcretePlatformComponent(
            name="space_catalog",
            abstract_roles=["SpaceProvider"],
            implementation_hint="DbGitSpaceProvider",
            source_of_truth="database",
            responsibilities=[
                "space metadata",
                "space visibility",
                "ACL policy",
                "default refs",
                "fork relationships",
                "asset index metadata",
            ],
            notes="The database is the source of truth for ownership, visibility, and sharing semantics.",
        ),
        "space_content": ConcretePlatformComponent(
            name="space_content",
            abstract_roles=["SpaceProvider"],
            implementation_hint="GitSpaceStore",
            source_of_truth="git",
            responsibilities=[
                "versioned files",
                "branches",
                "tags",
                "commits",
                "diffs",
                "history",
            ],
            notes="Each space should map to a dedicated Git repository or Git-compatible store.",
        ),
        "artifacts": ConcretePlatformComponent(
            name="artifacts",
            abstract_roles=["SpaceProvider", "RuntimeProvider"],
            implementation_hint="LocalArtifactStore or ObjectStorageArtifactStore",
            source_of_truth="filesystem/object storage",
            responsibilities=[
                "large binary assets",
                "execution artifacts",
                "derived outputs",
            ],
            notes="Large files can be referenced from Git/history metadata without forcing everything into the repo.",
        ),
        "secrets": ConcretePlatformComponent(
            name="secrets",
            abstract_roles=["SecretsProvider"],
            implementation_hint="DbSecretsProvider or VaultSecretsProvider",
            source_of_truth="database or vault",
            responsibilities=[
                "per-user credentials",
                "per-space credentials",
                "secret metadata",
                "runtime secret resolution",
                "audit metadata",
            ],
            notes="Credentials are outside Git and injected only into authorized executions.",
        ),
        "runtime": ConcretePlatformComponent(
            name="runtime",
            abstract_roles=["RuntimeProvider"],
            implementation_hint="DockerRuntimeProvider",
            source_of_truth="database for metadata, container runtime for live state",
            responsibilities=[
                "materialize space snapshot at a ref",
                "mount user data and artifacts",
                "inject resolved secrets",
                "enforce CPU/memory/network policies",
                "run workflows in isolation",
            ],
            notes="Executions should run against immutable space refs, not mutable live folders.",
        ),
        "execution_registry": ConcretePlatformComponent(
            name="execution_registry",
            abstract_roles=["RuntimeProvider"],
            implementation_hint="DbExecutionRegistry",
            source_of_truth="database",
            responsibilities=[
                "execution metadata",
                "status history",
                "logs index",
                "runtime profile linkage",
                "audit linkage to user, space, and commit",
            ],
            notes="Execution history remains queryable even after containers are gone.",
        ),
        "audit": ConcretePlatformComponent(
            name="audit",
            abstract_roles=["IdentityProvider", "SpaceProvider", "RuntimeProvider", "SecretsProvider"],
            implementation_hint="DbAuditLog",
            source_of_truth="database",
            responsibilities=[
                "who changed what",
                "who ran what",
                "share and permission changes",
                "secret usage metadata",
            ],
            notes="Useful both for debugging and for future multi-user governance.",
        ),
    }
    return DbGitPlatformSpec(components=components)
