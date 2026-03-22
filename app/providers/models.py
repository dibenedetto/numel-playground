# providers/models.py — Framework-agnostic data models for the multi-tenant layer.
#
# These are plain dataclasses, not Pydantic models, so they carry no
# framework dependency.  Provider implementations convert to/from these
# when talking to their backing stores.

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


# ── Enums ────────────────────────────────────────────────────────

class Role(str, Enum):
    ADMIN   = "admin"
    USER    = "user"
    VIEWER  = "viewer"


class AccessLevel(str, Enum):
    """Permission level on a resource (data repo, workflow, etc.)."""
    NONE    = "none"
    READ    = "read"
    WRITE   = "write"
    EXECUTE = "execute"
    OWNER   = "owner"


# ── Auth models ──────────────────────────────────────────────────

@dataclass
class User:
    id:         str
    username:   str
    email:      str
    role:       Role        = Role.USER
    active:     bool        = True
    created_at: float       = 0.0
    metadata:   Dict[str, Any] = field(default_factory=dict)


@dataclass
class Quota:
    """Resource budget for a user.  Providers debit on usage."""
    user_id:                  str
    cpu_seconds_remaining:    float  = 36000.0    # 10 hours default
    max_concurrent_runs:      int    = 5
    storage_bytes_remaining:  int    = 1_073_741_824  # 1 GB default
    max_loop_hours:           float  = 24.0
    gpu_hours_remaining:      float  = 0.0         # 0 = no GPU
    max_repos:                int    = 50


@dataclass
class Permission:
    """A single permission entry on a resource."""
    resource:   str          # e.g. "repo:user/data" or "workflow:my-flow"
    user_id:    str
    access:     AccessLevel


# ── Data models ──────────────────────────────────────────────────

@dataclass
class Repo:
    name:        str
    owner_id:    str
    private:     bool       = True
    description: str        = ""
    created_at:  float      = 0.0
    size_bytes:  int        = 0


@dataclass
class FileEntry:
    path:          str
    size:          int       = 0
    is_dir:        bool      = False
    last_modified: float     = 0.0
    content_hash:  str       = ""


@dataclass
class Commit:
    id:         str
    message:    str
    author_id:  str
    timestamp:  float
    files:      List[str]   = field(default_factory=list)


@dataclass
class Lock:
    path:         str
    repo:         str
    holder_id:    str         # user_id
    execution_id: str    = "" # optional: which execution holds the lock
    acquired_at:  float  = 0.0
    ttl:          float  = 300.0  # seconds, 0 = indefinite


# ── Execution models ─────────────────────────────────────────────

@dataclass
class ResourceLimits:
    """Constraints applied to a single workflow execution."""
    max_cpu_seconds:      float = 3600.0
    max_memory_bytes:     int   = 536_870_912  # 512 MB
    max_duration_seconds: float = 3600.0
    network_enabled:      bool  = True
    gpu_enabled:          bool  = False
    filesystem_root:      str   = ""  # mount point inside container


@dataclass
class ExecutionHandle:
    execution_id:   str
    user_id:        str
    workflow_name:  str
    status:         str     = "pending"  # pending | running | completed | failed | cancelled
    started_at:     float   = 0.0
    container_id:   str     = ""         # provider-specific (Docker ID, k8s pod, PID, etc.)


@dataclass
class ExecutionStatus:
    execution_id:    str
    status:          str          = "pending"
    progress:        float        = 0.0   # 0.0–1.0
    current_node:    Optional[str] = None
    cpu_seconds_used: float       = 0.0
    memory_bytes:    int          = 0
    error:           Optional[str] = None


@dataclass
class ExecutionResult:
    execution_id:   str
    status:         str                    # completed | failed | cancelled
    outputs:        Dict[str, Any]         = field(default_factory=dict)
    eval_scores:    Dict[str, float]       = field(default_factory=dict)
    duration_seconds: float                = 0.0
    cpu_seconds_used: float                = 0.0
    error:          Optional[str]          = None
