# Numel Local vs Prod Matrix

This document explains the practical difference between Numel's two slices:

- `local` = the public, fully working reference backend
- `prod` = the private, production-oriented backend in `app/platform_prod`

The goal is to answer questions like:

- what handles authentication?
- where do accounts live?
- what stores assets and runtime data?
- what is real versus mock?
- what exactly makes `prod` stronger than `local`?

This page is about the **current implementation**, not just the intended commercial boundary.

## Short Version

- `local` is **not fake**. It is a **fully working local/reference product**.
- `prod` is not a different product. It is the **same product surface** with stronger implementations and stronger guarantees.
- The biggest current differences are:
  - `local` uses **custom code + sqlite**
  - `prod` uses **Django + PostgreSQL**
  - `local` has a **partially working / mock-ish runtime isolation boundary**
  - `prod` has **real Docker-backed runtime isolation**

## Matrix

| Concern | Local slice | Production slice |
| --- | --- | --- |
| Authentication | **Custom code + sqlite**, via `LocalIdentityProvider`. **Fully working**. | **Django** service, via `DjangoIdentityProvider`. **Fully working production contract**. |
| Accounts / profiles / quotas | **Custom code + sqlite**. **Fully working**. Users, profiles, quotas, and auth semantics are real in local. | **Django identity deployment**, typically backed by **PostgreSQL**. **Fully working** at the Numel contract level. |
| Metadata database | **sqlite** (`storage/platform.db`). **Fully working** reference DB. | **PostgreSQL** is the real target. **Fully working / production-grade**. |
| Spaces / workflow metadata | **Git + sqlite metadata** through `GitSpaceStore` + `DbGitSpaceProvider`. **Fully working**. | **Git + PostgreSQL metadata** using the same product model. **Fully working**. |
| Space contents | **Git-backed**. **Fully working**. | **Git-backed**. **Fully working**. |
| Asset storage | Configured artifact storage, typically **filesystem** in local. **Fully working**. | Same product model, but meant for stronger production persistence and operations. **Fully working**. |
| Runtime state storage | Shared **filesystem runtime data** under `storage/` through `runtime_settings.py`. **Fully working**. | Same runtime-data contract. **Fully working**, but in a more production-oriented deployment shape. |
| Published app assets | **Filesystem runtime storage**. **Fully working**. | Same model. **Fully working**. |
| Secrets / credentials | `DbSecretsProvider`, usually on **sqlite**. **Fully working**. | Database-backed secrets on **PostgreSQL** or **Vault** via `VaultKvSecretsProvider`. **Fully working**, stronger than local. |
| Execution registry / audit | **Custom code + sqlite**. **Fully working**. | Same model on **PostgreSQL**. **Fully working**, more production-appropriate. |
| Runtime execution engine | `DockerRuntimeProvider`, but explicitly a **reference/mockup boundary**: it executes through `WorkspaceManager` + `WorkflowEngine`. So it is **fully working as a local runtime**, but **partially working / mock** as an isolation story. | `DockerApiRuntimeProvider` talking to the **Docker Engine API**. **Fully working real runtime boundary**. |
| Isolation | **Partially working / mock isolation**. Docker-shaped interface, but not real per-run container execution in the same sense as prod. | **Real Docker isolation**. One of the biggest real differentiators. |
| Startup validation | Light, mostly **reference-grade** validation. Good enough for local use, but not deep ops validation. | **Real external-service validation** for Django identity, secrets backend, and Docker runtime. |
| Backup / restore | [`app/platform_backup.py`](../app/platform_backup.py) for **sqlite + git + runtime files**. **Fully working** local backup flow. | [`app/platform_prod/backup.py`](../app/platform_prod/backup.py) for **PostgreSQL/sqlite + git + runtime data**. **Fully working**, much stronger operationally. |
| Deployment shape | Usually one local app process with local files and **sqlite**. **Fully working** for development, evaluation, and serious self-hosted reference use. | Multi-service deployment shape around **Django**, **PostgreSQL**, **Docker**, and stronger secrets/runtime ops. **Production-grade target**. |
| Product surface / UX | **Fully working**. Console, planner, spaces, deployments, published apps, and workflows are all real here. | Must stay **compatible** with local at the product level. Stronger underneath, same Numel surface. |

## What Is Real In `local`

These parts are not mock, fake, or placeholder:

- authentication
- accounts
- profiles
- quotas
- friendships
- spaces
- Git-backed workflows and assets
- credentials
- console
- planner
- assistant deployments
- published apps
- workflow execution as a product feature

That is why `local` should be described as a **fully working reference implementation**, not a demo shell.

## What Is Still Reference-Like In `local`

The main place where `local` remains intentionally lighter is runtime execution hardening.

In `local`:

- the runtime provider is Docker-shaped
- but the real execution path still goes through Numel's in-process workspace/engine machinery
- so the **product behavior is real**
- but the **runtime isolation story is only partially real**

That is why it is fair to describe local runtime isolation as:

- **partially working**
- **reference-oriented**
- **mock-ish at the container boundary**

but **not fake** as a user-facing feature.

## What Makes `prod` Stronger

The production slice is materially stronger in these areas:

- **Django** identity instead of in-process local auth code
- **PostgreSQL** instead of **sqlite**
- **real Docker runtime execution** instead of a reference/mock boundary
- stronger **secrets** backends
- stronger **startup validation**
- stronger **backup/restore**
- stronger deployment and operations posture overall

So the private value is not that `prod` invents a different Numel.
The private value is that it makes Numel **production-grade**.

## Where The Docker Files Fit

This is a common source of confusion.

### Root `Dockerfile` and `docker-compose.yml`

These are mainly for **containerized local bring-up** and developer convenience.

They package the **local/reference app** and, in compose, can also bring up helper services like **Ollama**.

They do **not** mean local has the same runtime isolation story as `prod`.

### `runtime/numel_runtime/Dockerfile`

This is the **reference production runtime image** for workflow executions.

It belongs to the runtime contract and production execution story, not to the simple root local app packaging story.

### Private Production Deployment Files

The production-oriented compose bundle and related deployment files should live
only in the **private production repo**, not in this public repo.

When that repo is mounted at the same `app/platform_prod` path, the deployable
bundle lives under:

- `app/platform_prod/deploy/`
- `app/platform_prod/services/identity_django/`

That private bundle is where the stronger deployment shape becomes concrete:

- app container
- identity service
- PostgreSQL
- runtime image build/update flow
- Docker-backed runtime wiring

## Best Mental Model

Use this distinction:

- `local` = **fully working product, lighter guarantees**
- `prod` = **same product, stronger guarantees**

Or more concretely:

- `local` = `custom code + sqlite + git + filesystem + reference runtime`
- `prod` = `Django + PostgreSQL + git + Docker + stronger secrets/ops`

## Related Docs

- [public-private-boundary.md](public-private-boundary.md)
- [feature-tier-matrix.md](feature-tier-matrix.md)
- [workflow-backed-surfaces.md](workflow-backed-surfaces.md)
- [assistant-deployments.md](assistant-deployments.md)
