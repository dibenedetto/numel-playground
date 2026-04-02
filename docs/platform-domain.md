# Numel Platform Domain

This document defines Numel's product-level platform model independently from
the current local implementation. The goal is to keep the architecture honest:
today's JSON/filesystem/workspace setup is a working mockup, while future
implementations can swap in Django, PostgreSQL, Git-like storage, Docker, or
other concrete backends without changing the rest of the product model.

## Core Domain

Numel should reason about these concepts first:

- `UserAccount`: identity, login, role, lifecycle
- `UserProfile`: display-facing user data
- `Friendship`: accepted or pending friend relationships
- `UsageQuota`: limits and budget
- `Space`: a user-owned repo-like container
- `SpaceRef`: branch, tag, or commit-like ref
- `SpaceCommit`: immutable history entry
- `SpaceAsset`: typed item inside a space tree
- `PermissionPolicy`: owner + visibility + ACL rules
- `CredentialRecord`: metadata for per-user or per-space secrets
- `RuntimeProfile`: execution isolation and resource policy
- `ExecutionRequest` / `ExecutionRecord`: a run pinned to user + space + ref + runtime

## Visibility Model

The target visibility model is:

- `public`: world-readable
- `protected`: readable by accepted friends
- `private`: readable only by the owner

Visibility is only the baseline. Execution and mutation should remain explicit
capabilities in the ACL model, so "readable by friends" does not automatically
mean "executable by friends".

## Space Model

A `Space` is the main product abstraction. It should behave more like a versioned
repository than a loose workspace folder:

- it has an owner
- it has visibility and policy
- it contains a typed asset tree
- it has refs, commits, and history
- it can eventually support branching, forking, publishing, and rollback

Workflows, toolkits, skills, data files, and published apps should eventually
all become `SpaceAsset` records rather than separate ad hoc systems.

## Runtime Model

Executions should be scoped to:

- a `user`
- a `space`
- a `ref` or commit
- an `asset_path`
- a `runtime profile`
- a resolved set of secrets

This is the clean bridge to future container-based isolation.

## Current Mockup Mapping

The codebase already contains useful lower-level abstractions, but they do not
yet line up one-to-one with the desired product model:

- `AuthProvider` in `app/providers/auth.py`
  Handles auth, users, quotas, and coarse permissions.
- `DataProvider` in `app/providers/data.py`
  Models repo-like versioned storage, but not full spaces/assets/ACL semantics.
- `ExecutionProvider` in `app/providers/execution.py`
  Models how a run executes, but not yet fully as `space + ref + runtime`.
- `WorkspaceManager` in `app/workspace.py`
  Models the live in-memory/runtime side of user isolation today.
- `credentials.py`
  Still acts as a shared server credential store and must later be replaced by a
  true per-user/per-space secrets backend.

Because of this, the current implementation is best understood as a working
mockup of the future platform:

- identity: mostly implemented
- spaces: partially implemented
- resources: partially implemented
- runtime isolation: partially implemented
- secrets: still mock/shared
- friends/social graph: planned

## Migration Direction

The intended long-term split is:

- Django (or another auth service): users, profiles, friendships, roles, quotas
- PostgreSQL: spaces, assets, refs, commits, ACLs, execution metadata
- object storage / filesystem: blobs and large assets
- Docker or similar runtime: isolated executions with user-scoped env injection

The important rule is that these are implementations of the domain, not the
domain itself.
