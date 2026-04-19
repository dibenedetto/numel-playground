"""Abstract provider interfaces for the Numel platform domain."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict, List, Optional

from .models import (
    CredentialRecord,
    ExecutionRecord,
    ExecutionRequest,
    ExecutionState,
    Friendship,
    FriendshipStatus,
    PermissionPolicy,
    RefKind,
    RuntimeProfile,
    Space,
    SpaceAsset,
    SpaceCommit,
    SpaceRef,
    UsageQuota,
    UserAccount,
    UserProfile,
    Visibility,
)


class IdentityProvider(ABC):
    """Users, authentication, profiles, and quota management."""

    @abstractmethod
    async def authenticate(self, token: str) -> Optional[UserAccount]:
        """Validate a bearer token and return the associated user."""

    @abstractmethod
    async def login(self, username: str, password: str) -> Optional[str]:
        """Verify credentials and return a bearer token."""

    @abstractmethod
    async def logout(self, token: str) -> bool:
        """Invalidate a token and return whether it existed."""

    @abstractmethod
    async def change_password(self, user_id: str, current_password: str, new_password: str) -> bool:
        """Update a user's password and invalidate existing sessions when appropriate."""

    @abstractmethod
    async def create_user(self, username: str, email: str, password: str) -> UserAccount:
        """Create a new platform user."""

    @abstractmethod
    async def get_user(self, user_id: str) -> Optional[UserAccount]:
        """Load a user account by id."""

    @abstractmethod
    async def get_user_by_username(self, username: str) -> Optional[UserAccount]:
        """Load a user account by username."""

    @abstractmethod
    async def list_users(
        self, offset: int = 0, limit: int = 50, active_only: bool = True
    ) -> List[UserAccount]:
        """Paginated user listing."""

    @abstractmethod
    async def update_user(self, user_id: str, **fields) -> UserAccount:
        """Update mutable account fields."""

    @abstractmethod
    async def delete_user(self, user_id: str) -> bool:
        """Deactivate or remove a user account."""

    @abstractmethod
    async def get_profile(self, user_id: str) -> Optional[UserProfile]:
        """Load the product-facing user profile."""

    @abstractmethod
    async def update_profile(self, user_id: str, **fields) -> UserProfile:
        """Update display name, bio, avatar, and related metadata."""

    @abstractmethod
    async def get_quota(self, user_id: str) -> UsageQuota:
        """Return current user quota."""

    @abstractmethod
    async def update_quota(self, user_id: str, **fields) -> UsageQuota:
        """Update quota values for a user."""


class FriendGraphProvider(ABC):
    """Friend requests and accepted social links."""

    @abstractmethod
    async def send_request(self, requester_user_id: str, target_user_id: str) -> Friendship:
        """Create or refresh a friend request."""

    @abstractmethod
    async def accept_request(self, requester_user_id: str, target_user_id: str) -> Friendship:
        """Accept a pending friend request."""

    @abstractmethod
    async def reject_request(self, requester_user_id: str, target_user_id: str) -> Friendship:
        """Reject a pending friend request."""

    @abstractmethod
    async def remove_friend(self, user_id: str, friend_user_id: str) -> bool:
        """Remove an accepted friendship or pending relation."""

    @abstractmethod
    async def list_friendships(
        self, user_id: str, status: Optional[FriendshipStatus] = None
    ) -> List[Friendship]:
        """List friendships or requests for a user."""

    @abstractmethod
    async def are_friends(self, user_id: str, other_user_id: str) -> bool:
        """Return True when both users have an accepted friendship."""


class SecretsProvider(ABC):
    """Per-user or per-space secret metadata and value resolution."""

    @abstractmethod
    async def list_credentials(
        self, owner_user_id: str, space_id: Optional[str] = None
    ) -> List[CredentialRecord]:
        """List secret metadata visible to a user/scope."""

    @abstractmethod
    async def get_credential(
        self, owner_user_id: str, name: str, space_id: Optional[str] = None
    ) -> Optional[CredentialRecord]:
        """Load secret metadata by name."""

    @abstractmethod
    async def set_credential(
        self,
        owner_user_id: str,
        name: str,
        value: str,
        space_id: Optional[str] = None,
        metadata: Optional[Dict[str, str]] = None,
    ) -> CredentialRecord:
        """Create or update a secret without exposing storage details."""

    @abstractmethod
    async def delete_credential(
        self, owner_user_id: str, name: str, space_id: Optional[str] = None
    ) -> bool:
        """Delete a secret and return whether it existed."""

    @abstractmethod
    async def resolve_credentials(
        self,
        owner_user_id: str,
        names: Optional[List[str]] = None,
        space_id: Optional[str] = None,
    ) -> Dict[str, str]:
        """Resolve runtime values for env injection."""


class SpaceProvider(ABC):
    """Repo-like user spaces with assets, refs, history, and permissions."""

    @abstractmethod
    async def create_space(
        self,
        owner_user_id: str,
        slug: str,
        title: str,
        description: str = "",
        visibility: Visibility = Visibility.PRIVATE,
    ) -> Space:
        """Create a new space."""

    @abstractmethod
    async def get_space(self, space_id: str) -> Optional[Space]:
        """Load space metadata."""

    @abstractmethod
    async def list_owned_spaces(self, owner_user_id: str) -> List[Space]:
        """List spaces owned by a user."""

    @abstractmethod
    async def list_accessible_spaces(self, user_id: str) -> List[Space]:
        """List spaces the user can read."""

    @abstractmethod
    async def update_space(self, space_id: str, **fields) -> Space:
        """Update mutable space metadata."""

    @abstractmethod
    async def delete_space(self, space_id: str) -> bool:
        """Delete a space."""

    @abstractmethod
    async def set_space_policy(self, space_id: str, policy: PermissionPolicy) -> Space:
        """Replace the space-level permission policy."""

    @abstractmethod
    async def fork_space(
        self, source_space_id: str, new_owner_user_id: str, slug: str, title: str = ""
    ) -> Space:
        """Fork a space into a new owner scope."""

    @abstractmethod
    async def list_assets(
        self, user_id: str, space_id: str, ref: str = "main", prefix: str = ""
    ) -> List[SpaceAsset]:
        """List assets in a space snapshot."""

    @abstractmethod
    async def get_asset(
        self, user_id: str, space_id: str, path: str, ref: str = "main"
    ) -> Optional[SpaceAsset]:
        """Load asset metadata."""

    @abstractmethod
    async def read_asset(
        self, user_id: str, space_id: str, path: str, ref: str = "main"
    ) -> bytes:
        """Read the asset payload at a given ref."""

    @abstractmethod
    async def write_asset(
        self,
        user_id: str,
        space_id: str,
        asset: SpaceAsset,
        content: bytes,
        message: str = "",
        ref: str = "main",
    ) -> SpaceCommit:
        """Write an asset and create a new commit."""

    @abstractmethod
    async def delete_asset(
        self, user_id: str, space_id: str, path: str, message: str = "", ref: str = "main"
    ) -> SpaceCommit:
        """Delete an asset and create a new commit."""

    @abstractmethod
    async def list_refs(self, space_id: str) -> List[SpaceRef]:
        """List branches and tags."""

    @abstractmethod
    async def create_ref(
        self, space_id: str, name: str, kind: RefKind, from_ref: str = "main"
    ) -> SpaceRef:
        """Create a branch or tag."""

    @abstractmethod
    async def delete_ref(self, space_id: str, name: str) -> bool:
        """Delete a branch or tag."""

    @abstractmethod
    async def get_history(
        self, space_id: str, path: str = "", limit: int = 20, ref: str = "main"
    ) -> List[SpaceCommit]:
        """Get history for a whole space or a single asset path."""

    @abstractmethod
    async def get_commit(self, space_id: str, commit_id: str) -> Optional[SpaceCommit]:
        """Load one historical commit."""


class RuntimeProvider(ABC):
    """Run a space asset against an isolated or mock runtime."""

    @abstractmethod
    async def start_execution(
        self,
        request: ExecutionRequest,
        runtime: Optional[RuntimeProfile] = None,
        env: Optional[Dict[str, str]] = None,
    ) -> ExecutionRecord:
        """Start a new execution for an asset within a space."""

    @abstractmethod
    async def get_execution(self, execution_id: str) -> Optional[ExecutionRecord]:
        """Load execution state."""

    @abstractmethod
    async def list_executions(
        self,
        user_id: Optional[str] = None,
        space_id: Optional[str] = None,
        status: Optional[ExecutionState] = None,
        offset: int = 0,
        limit: int = 50,
    ) -> List[ExecutionRecord]:
        """List executions with optional filters."""

    @abstractmethod
    async def cancel_execution(self, execution_id: str) -> bool:
        """Cancel a running execution."""

    @abstractmethod
    async def get_logs(self, execution_id: str, tail: int = 100) -> str:
        """Return recent logs for an execution."""
