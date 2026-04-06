# Numel Feature Tier Matrix

This document makes the commercial boundary concrete.

The goal is to keep the public repo as a strong local/reference product without
making the private production slice feel unnecessary.

Use this matrix **before committing or pushing new features** that touch admin,
operations, deployment, observability, backup, identity, or runtime behavior.

## Core Rule

Keep these things public:

- the Numel product model
- the local/reference implementation
- enough admin and operational capability for a serious local user

Keep these things private:

- production guarantees
- operational hardening
- advanced deploy/support tooling
- anything that would make the private production slice look like a trivial swap

## Three Buckets

### 1. Shared In Both `local` And `prod`

These should remain visible and usable in both slices.

- users, profiles, quotas, friendships
- spaces and current-workflow model
- Git-backed space contents and history model
- credentials/secrets at the app layer
- workflow execution model
- planner, console, `/gen`, and toolkit/skill usage
- basic admin users view
- basic admin executions list
- basic health/readiness checks
- basic diagnostics summary
  - active backend
  - startup status
  - path existence
  - recent execution count/state
- local-safe backup/restore for reference installs
  - sqlite database
  - git-backed spaces
  - local runtime data/files

These are part of understanding and using Numel itself. If they disappear from
public, the public repo stops feeling like a real product.

### 2. Public But Intentionally Limited In `local`

These can exist publicly, but the local/reference implementation should stay
lighter than the production one.

- admin diagnostics
  - keep summary cards and simple recent activity public
  - avoid turning the public UI into a full production operations console
- execution drill-down
  - keep basic status/metadata visibility
  - keep local logs simple and reference-oriented
- backup/restore tooling
  - keep local filesystem/sqlite workflows public
  - keep the CLI operationally useful for self-hosters
- secrets handling
  - keep database-backed local secrets
  - do not expose every production hardening path publicly

This bucket is the "real but not enterprise-complete" zone.

### 3. `prod`-Only / Private

These should live in the private production slice or be significantly stronger
there than in public.

- Django identity deployment and operational contract
- PostgreSQL production deployment and database operations
- Docker-isolated runtime behavior and hardening
- GPU/runtime image operations and production runtime policies
- advanced support/ops tooling
  - exportable support bundles
  - richer incident/debug bundles
  - advanced operational runbooks
- production-grade observability depth
  - app log ring buffer intended for support operations
  - deeper runtime/container troubleshooting views
  - operational audit surfaces meant for live deployments
- production backup/restore
  - PostgreSQL dump/restore
  - production restore procedures
  - deployment-oriented backup runbooks
- deploy bundle hardening
  - compose/deploy orchestration details
  - production secrets hardening
  - production retention/cleanup policies

These are the places where the private slice should feel materially stronger.

## Current Recommendation For Recent Work

This is the practical recommendation for the work we were just doing.

### Keep Public

- basic `/admin/diagnostics`
- basic `/admin/executions`
- basic execution detail visibility
- local backup/restore CLI for sqlite + filesystem data

### Prefer Private Or Reduced In Public

- support bundle export
- app-log support views
- deeper execution log drilling meant for operations/support
- PostgreSQL backup/restore logic
- production runbooks and deploy-time recovery flows

## Safe-To-Commit Public Surface

This is the current recommendation for what is safe to keep in the public repo
before committing or pushing.

### Keep In Public Now

- `/admin/diagnostics` with compact summary information only
  - active backend
  - startup checks
  - runtime paths and disk usage
  - auth/provider summary
  - recent executions with status, ids, output keys, and sanitized metadata
- `/admin/executions` list
- `/admin/executions/{id}` detail view
  - display name
  - status
  - user/space/asset/ref identifiers
  - sanitized metadata
  - outputs
- `app/platform_backup.py`
  - local-only backup/restore CLI
  - sqlite + Git-backed spaces + local runtime files
- shared health/readiness endpoints
- local/reference admin users and quota management
- local/reference execution visibility needed to understand and operate Numel

### Keep Out Of Public For Now

- support bundle export/download
- app-level recent log buffers intended for support operations
- execution log tails or deeper log-drilling in the public admin surface
- container/runtime troubleshooting views aimed at production support
- PostgreSQL backup/restore tooling
- production recovery runbooks

### Reintroduce Later Only In Reduced Form

These may still belong in the public repo later, but only in a clearly limited
local/reference form.

- local backup/restore CLI
  - sqlite only
  - Git-backed spaces only
  - local filesystem/runtime data only
  - no PostgreSQL dump/restore
  - no production-grade recovery workflow

### Review Conclusion

After trimming the recent admin/ops additions, the current public diagnostics
surface is acceptable because it is informative without becoming a full support
console. The remaining public admin visibility is product-facing rather than
support-heavy.

The next commit/push should avoid reintroducing:

- exportable support bundles
- app-log operational views
- deeper execution/container log tooling
- production backup/restore behavior

## Decision Tests

When a new feature is proposed, ask:

### Product Test

Does removing this make public Numel stop feeling like a real product?

If yes, keep it public.

### Operations Test

Does this primarily help operate, support, recover, or harden a live
deployment?

If yes, it likely belongs in `prod` or in a reduced public form.

### Commercial Test

If this stays fully public, does the private production slice become visibly
less differentiated?

If yes, move the stronger version to `prod`.

## Suggested Immediate Boundary

If we want to avoid exposing too much of the paid/productized ops layer right
now, the simplest immediate policy is:

- keep local/reference admin and diagnostics useful but compact
- keep local backup/restore limited to sqlite + filesystem state
- move advanced support export and production backup/restore into the private
  prod slice

That gives Numel a clean distinction:

- `local`: real, understandable, self-hostable, limited
- `prod`: hardened, operable, supportable, commercially stronger
