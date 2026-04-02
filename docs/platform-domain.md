# Numel Platform Domain

This document defines Numel's product-level platform model independently from
the current implementation. The goal is to keep the architecture honest:
today's SQLite + Git + in-process runtime stack is the local reference backend,
while future implementations can swap in Django, PostgreSQL, Docker, or other
concrete services without changing the rest of the product model.

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

## Current Reference Backend

The current codebase now centers on one coherent local backend under
`app/platform_local/`:

- `LocalIdentityProvider`
  Users, profiles, quotas, login sessions.
- `DbFriendGraphProvider`
  Friend requests and accepted friendships.
- `DbGitSpaceProvider`
  Space metadata, visibility, ACLs, and typed assets.
- `GitSpaceStore`
  Versioned space contents and history.
- `DbSecretsProvider`
  Per-user or per-space credentials.
- `DbExecutionRegistry` and `DbAuditLog`
  Execution metadata and audit events.
- `DockerRuntimeProvider`
  Current local execution bridge, to be replaced later by real container isolation.

The remaining historical split is mostly in runtime behavior:

- `WorkspaceManager` in `app/workspace.py`
  Still provides the live in-process execution surface used by the local runtime bridge.

Backend selection itself now happens through `app/platform_backend.json`.
That file chooses the active backend (`local` or `prod`) and provides the
constructor settings for the selected implementation. The app reads it at
startup through `app/platform_loader.py`.

## Migration Direction

The intended long-term split is:

- `app/platform_local/`: the full local/reference backend used by the app today
- `app/platform_prod/`: future production-oriented adapters and composition
- Django (or another auth service): users, profiles, friendships, roles, quotas
- PostgreSQL: spaces, assets, refs, commits, ACLs, execution metadata
- object storage / filesystem: blobs and large assets
- Docker or similar runtime: isolated executions with user-scoped env injection

The important rule is that these are implementations of the domain, not the
domain itself.
