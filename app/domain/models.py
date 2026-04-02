"""Framework-agnostic platform models for Numel.

These dataclasses describe the product concepts Numel wants to support even
when the current implementation is still a lightweight mockup. They are
deliberately higher-level than the current provider models in app/providers/.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class UserRole(str, Enum):
    ADMIN = "admin"
    USER = "user"
    VIEWER = "viewer"


class FriendshipStatus(str, Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    BLOCKED = "blocked"


class Visibility(str, Enum):
    PUBLIC = "public"
    PROTECTED = "protected"
    PRIVATE = "private"


class AssetKind(str, Enum):
    WORKFLOW = "workflow"
    TOOLKIT = "toolkit"
    SKILL = "skill"
    DATA = "data"
    APP = "app"
    TEMPLATE = "template"
    OTHER = "other"


class SecretScope(str, Enum):
    USER = "user"
    SPACE = "space"
    EXECUTION = "execution"


class RefKind(str, Enum):
    BRANCH = "branch"
    TAG = "tag"
    COMMIT = "commit"


class ExecutionState(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class SubjectType(str, Enum):
    OWNER = "owner"
    USER = "user"
    FRIENDS = "friends"
    PUBLIC = "public"
    ROLE = "role"


class Capability(str, Enum):
    READ = "read"
    WRITE = "write"
    DELETE = "delete"
    EXECUTE = "execute"
    SHARE = "share"
    ADMIN = "admin"


@dataclass
class UserAccount:
    id: str
    username: str
    email: str
    role: UserRole = UserRole.USER
    active: bool = True
    created_at: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class UserProfile:
    user_id: str
    display_name: str = ""
    bio: str = ""
    avatar_url: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class UsageQuota:
    user_id: str
    cpu_seconds_remaining: float = 36000.0
    max_concurrent_runs: int = 5
    storage_bytes_remaining: int = 1_073_741_824
    max_loop_hours: float = 24.0
    gpu_hours_remaining: float = 0.0
    max_spaces: int = 50
    max_assets_per_space: int = 10_000


@dataclass
class Friendship:
    requester_user_id: str
    target_user_id: str
    status: FriendshipStatus = FriendshipStatus.PENDING
    created_at: float = 0.0
    updated_at: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AclEntry:
    subject_type: SubjectType
    capabilities: List[Capability] = field(default_factory=list)
    subject_id: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PermissionPolicy:
    owner_user_id: str
    visibility: Visibility = Visibility.PRIVATE
    acl: List[AclEntry] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Space:
    id: str
    owner_user_id: str
    slug: str
    title: str
    description: str = ""
    visibility: Visibility = Visibility.PRIVATE
    default_ref: str = "main"
    head_commit_id: str = ""
    policy: Optional[PermissionPolicy] = None
    created_at: float = 0.0
    updated_at: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SpaceRef:
    space_id: str
    name: str
    kind: RefKind
    commit_id: str
    created_at: float = 0.0
    updated_at: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SpaceCommit:
    id: str
    space_id: str
    author_user_id: str
    message: str
    created_at: float = 0.0
    parent_ids: List[str] = field(default_factory=list)
    changed_paths: List[str] = field(default_factory=list)
    tree_hash: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SpaceAsset:
    id: str
    space_id: str
    path: str
    kind: AssetKind
    owner_user_id: str
    title: str = ""
    description: str = ""
    visibility: Visibility = Visibility.PRIVATE
    versioned: bool = True
    executable: bool = False
    size_bytes: int = 0
    content_hash: str = ""
    latest_commit_id: str = ""
    policy: Optional[PermissionPolicy] = None
    created_at: float = 0.0
    updated_at: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CredentialRecord:
    id: str
    owner_user_id: str
    name: str
    scope: SecretScope = SecretScope.USER
    space_id: Optional[str] = None
    secret_ref: str = ""
    value_present: bool = False
    created_at: float = 0.0
    updated_at: float = 0.0
    last_used_at: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RuntimeProfile:
    id: str
    owner_user_id: str
    name: str
    description: str = ""
    image: str = ""
    working_directory: str = "/workspace"
    network_enabled: bool = True
    gpu_enabled: bool = False
    max_cpu_seconds: float = 3600.0
    max_memory_bytes: int = 536_870_912
    max_duration_seconds: float = 3600.0
    allowed_mounts: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ExecutionRequest:
    user_id: str
    space_id: str
    asset_path: str
    ref: str = "main"
    runtime_profile_id: str = ""
    credential_names: List[str] = field(default_factory=list)
    inputs: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ExecutionRecord:
    execution_id: str
    user_id: str
    space_id: str
    asset_path: str
    ref: str = "main"
    status: ExecutionState = ExecutionState.PENDING
    runtime_profile_id: str = ""
    started_at: float = 0.0
    finished_at: Optional[float] = None
    outputs: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
