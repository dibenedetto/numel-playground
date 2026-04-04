# Numel Concrete Platform: Database + Git

This document defines the chosen concrete direction for Numel's future platform
implementation:

- relational database for platform metadata and permissions
- Git for versioned space contents
- Docker for isolated execution

The rule is simple:

- the database is the source of truth for platform state
- Git is the source of truth for versioned space contents

## Why Both

Git is excellent at:

- commits
- branches
- tags
- diffs
- forks
- rollback
- versioned workflows, skills, toolkits, and files

A relational database is excellent at:

- users
- profiles
- friendships
- visibility and ACLs
- quotas
- sessions/tokens
- secret metadata
- runtime metadata
- execution history
- audit records

Trying to replace the database with Git would make identity, permissions,
friendship, quotas, and runtime bookkeeping awkward. Trying to replace Git with
only database rows would make branching, history, diffs, and forking much less
natural.

## Concrete Components

The intended concrete stack is:

- `DjangoIdentityProvider`
  Handles auth, users, profiles, roles, quotas.
- `DbFriendGraphProvider`
  Handles friend requests and accepted friendships.
- `DbGitSpaceProvider`
  Coordinates database metadata with Git-backed space content.
- `GitSpaceStore`
  One repository per space for versioned contents.
- `ProdDbSecretsProvider`
  The current production default for per-user or per-space secret metadata and runtime resolution.
- `VaultKvSecretsProvider`
  Optional alternative when deploying against a dedicated external secrets service.
- `DockerRuntimeProvider`
  Executes a space snapshot in isolation.
- `DbExecutionRegistry`
  Persists execution metadata and history.
- `DbAuditLog`
  Persists security and change events.

The codebase now separates the working local backend and the future production
backend explicitly:

- `app/platform_local/` for the reference local implementation
- `app/platform_prod/` for production-oriented adapters like Django

Backend selection is now config-driven through `app/platform_backend.json`.
That file selects `local` or `prod`, and `app/platform_loader.py` builds the
matching stack at startup.

For deployment, the repo now also includes a dedicated production bundle under
`deploy/`, with:

- `deploy/platform_backend.prod.json` using PostgreSQL + the prod adapters
- `deploy/docker-compose.prod.yml` for PostgreSQL + Docker runtime wiring
- `deploy/.env.prod.example` for environment-driven config values
- `deploy/Dockerfile.identity` plus `services/identity_django/` for the in-repo Django identity service
- `deploy/runtime-builder.sh` for content-aware inner runtime image rebuilds inside the production Docker daemon

The app-facing interface is intentionally unchanged across `local` and `prod`;
the backend swap happens beneath the shared platform HTTP contract.

## Implementation Status Matrix

| Component | Current state | What exists now | Next step | Eventual backend |
| --- | --- | --- | --- | --- |
| Platform domain model | abstract | `app/domain/models.py`, `app/domain/interfaces.py` | keep refining actor and permission boundaries | stable app-level contract |
| Concrete target architecture | abstract | `app/domain/concrete.py` | use it to drive adapter work | db + git + docker |
| Local identity adapter | concrete local implementation | `app/platform_local/local_identity.py` | migrate auth-facing app code toward the domain identity layer | SQLite in dev, Django in prod |
| Git space content store | concrete local implementation | `app/platform_local/git_space_store.py` | add more content/history tooling as needed | Git repos per space |
| Space catalog + ACLs | concrete local implementation | `app/platform_local/db_git_spaces.py` | add actor-aware mutations and richer ACLs | PostgreSQL in prod, SQLite in dev |
| Friend graph | concrete local implementation | `app/platform_local/db_friend_graph.py` | wire into real identity records | PostgreSQL in prod, SQLite in dev |
| Secrets adapter | concrete external adapter | `app/platform_prod/secrets.py` plus `app/platform_local/db_secrets.py` for the local/reference path | finalize the production deployment choice between database-backed and Vault-backed secrets | PostgreSQL or Vault |
| Audit log | concrete local implementation | `app/platform_local/db_audit.py` | enrich event categories and API exposure | PostgreSQL |
| Execution registry | concrete local implementation | `app/platform_local/db_execution_registry.py` | extend events and log indexing | PostgreSQL in prod, SQLite in dev |
| Runtime | concrete local mock-runtime | `app/platform_local/docker_runtime.py` running through `WorkspaceManager + WorkflowEngine` | keep as the local reference path | local workspace engine |
| Local platform assembly | concrete local implementation | `app/platform_local/local_stack.py`, `app.state.platform_stack` | start consuming this stack from APIs incrementally | main platform composition root |
| Future db+git assembly | partial mock | `app/platform_prod/stack.py` | replace remaining secrets and finalize deployment integration | db + git + docker |
| Django identity adapter | concrete prod implementation | `app/platform_prod/django_identity.py` plus `services/identity_django/` | keep the Django contract aligned with the local identity semantics | Django |
| Docker runtime adapter | concrete external adapter | `app/platform_prod/docker_runtime.py`, `app/platform_prod/runtime_contract.py`, `runtime/numel_runtime/` | connect to the real Docker deployment and keep hardening the final image policy | Docker Engine API |
| Role-based ACL subjects | not implementable correctly yet | modeled in the domain, not enforced in the local space provider | wire role resolution from the identity layer | Django + DB |
| Owner/admin mutation enforcement inside `SpaceProvider` | structurally incomplete | limitation of the current interface shape | pass acting user through the interface | domain and API refactor |
| Real per-user env and secret injection | partial mock | prod runtime now injects merged user/space execution env vars and redacts saved job specs; the local runtime still only tracks metadata | finish the final production secret backend and isolation policy | Docker + secrets backend |

## First Implemented Slice

The first concrete local-development slice is now implemented for:

- `LocalIdentityProvider`
- `GitSpaceStore`
- `DbGitSpaceProvider`
- `DbFriendGraphProvider`
- `DbSecretsProvider`
- `DbAuditLog`
- `DbExecutionRegistry`
- `DockerRuntimeProvider`
- `LocalPlatformStack`

Supported behavior in this first slice:

- create users, profiles, quotas, and login sessions in SQLite
- create a space
- store space metadata in SQLite
- create one Git repository per space
- write versioned assets
- read assets from a selected ref
- list assets from the Git tree
- list branches and tags
- inspect commit history
- fork a space by cloning its Git repo and metadata
- enforce `public`, `protected`, and `private` reads for spaces
- evaluate ACL capabilities for `read`, `write`, `delete`, and `execute`
- resolve protected visibility through the friend graph
- store, list, resolve, and delete per-user or per-space credentials in SQLite
- persist audit events in SQLite
- execute a workflow asset from `space + ref` through the current local workspace engine
- materialize a ref snapshot into execution artifacts for local runs

Current limitations of this first slice:

- owner/admin mutations such as `update_space`, `delete_space`, `set_space_policy`, and ref management still rely on higher API layers to provide the acting user, because the current abstract interface does not yet pass that actor explicitly
- `ROLE` ACL subjects are modeled but not enforced in the local implementation, because the identity-role bridge is still future work
- execution runs through the existing in-process workspace engine, not real Docker isolation yet
- requested env vars and credentials are tracked in execution metadata, but the local mock runtime does not inject them into an isolated per-run environment
- assets are indexed as current metadata in SQLite, while Git remains the source of truth for content/history

## Source of Truth Split

### Database

The database should own:

- user accounts
- user profiles
- friend graph
- quotas
- spaces
- space visibility
- ACL and sharing policy
- fork lineage
- runtime profiles
- execution metadata
- audit records
- secret metadata

Suggested first table groups:

- `users`
- `user_profiles`
- `friendships`
- `quotas`
- `spaces`
- `space_policies`
- `space_refs`
- `space_assets`
- `runtime_profiles`
- `executions`
- `execution_events`
- `credentials`
- `audit_logs`

### Git

Git should own the actual versioned tree of a space:

- workflows
- toolkits
- skills
- user files
- published app definitions
- templates
- any future versioned asset

Recommended layout:

- one Git repository per `space`
- `main` as default branch
- optional feature branches per user task or collaboration flow
- tags for published or stable versions

## Execution Flow

The intended execution flow is:

1. Authenticate the user through the identity layer.
2. Resolve whether the user can read or execute the target asset.
3. Resolve `space_id + ref + asset_path`.
4. Materialize the corresponding Git snapshot.
5. Resolve only the credentials available to that user and scope.
6. Start a Docker run with the selected runtime profile.
7. Persist execution metadata in the database.
8. Write artifacts to artifact storage and link them back to the execution.

In the current local-development mockup, step 6 is approximated by the existing
`WorkspaceManager + WorkflowEngine` pair. The production adapter now also has a
shared container contract in `app/platform_prod/runtime_contract.py`, a
production secrets layer in `app/platform_prod/secrets.py`, and a runtime image
under `runtime/numel_runtime/`. The current production path runs the Numel
engine inside the container, injects merged user/space execution secrets,
redacts host-side job specs, enforces timeout/concurrency limits, and applies a
stricter Docker isolation profile by default. The main remaining production work
is the final external deployment policy for secrets and image contents.

## Important Rules

- Credentials are never versioned in Git.
- Permissions are never derived only from Git history.
- Executions should run against immutable refs or commit ids when possible.
- Git tracks content history; the database tracks platform truth.

## Local Mockup Compatibility

For development, this same architecture can still be approximated with:

- SQLite instead of PostgreSQL
- local Git repos on disk
- local filesystem artifact storage
- local mock auth instead of Django
- local process execution before Docker is ready

That keeps the same architecture while swapping only the concrete backend.

## Status Label Meanings

- `abstract`
  The concept is defined clearly enough to code against, but there is no operational backend behind it yet. This is the level of interfaces, dataclasses, and architecture specs.

- `working mock`
  A real, usable implementation exists today, but it is intentionally not the final architecture. It is good enough to keep the app working and to validate product behavior.

- `partial mock`
  Some of the target behavior exists, but the abstraction is still split across unrelated systems or only partly modeled. It works in slices, not as one coherent platform layer.

- `mock/shared`
  The feature exists in a simplified form, but it still uses shared server state where the target design requires per-user or per-space isolation.

- `concrete local implementation`
  A real implementation exists and runs locally now, with storage, logic, and verification behind it. It may still be a dev-mode backend, but it is not just a sketch.

- `concrete local mock-runtime`
  A special case of concrete local implementation where the runtime boundary is still simulated locally. The system really executes, but it does so through a stand-in for the future isolation layer.

- `not implementable correctly yet`
  You could hack something in, but it would be misleading or architecturally wrong because a required dependency or upstream model does not exist yet.

- `structurally incomplete`
  The blocker is not just a missing backend. The current abstraction or interface shape is missing information needed to enforce the rule correctly, so the design itself must change first.


