# Fork Handoff

This file is the durable handoff for continuing Numel in a fork or in a new
chat session.

## Current State

Numel now runs on a shared platform abstraction with two selectable backends:

- `platform_local`
  The working local/reference backend used by the app today.
- `platform_prod`
  The production-oriented backend built around PostgreSQL, Django identity, and
  Docker runtime execution.

Backend selection is config-only:

- local/dev default: [app/platform_backend.json](/c:/devel/numel-playground/app/platform_backend.json)
- production deploy config: [deploy/platform_backend.prod.json](/c:/devel/numel-playground/deploy/platform_backend.prod.json)

From the app and frontend point of view, switching between `local` and `prod`
does not change the public product surface.

## Product Surface

The active app model is:

- authenticated users only
- one current workflow per current space
- current space selected through `/spaces/current`
- current workflow loaded and saved through `/workflow/get` and `/workflow/save`
- execution started through `/workflow/start`
- execution tracked through `/executions/*`

The old legacy multi-workflow surface has been removed.

## Platform Architecture

Core split:

- [app/platform_local](/c:/devel/numel-playground/app/platform_local)
  Full local/reference backend.
- [app/platform_prod](/c:/devel/numel-playground/app/platform_prod)
  Production-oriented adapters.
- [app/platform_loader.py](/c:/devel/numel-playground/app/platform_loader.py)
  Config-driven backend loader.
- [app/platform_http.py](/c:/devel/numel-playground/app/platform_http.py)
  Shared HTTP contract for platform operations.
- [app/platform_client.py](/c:/devel/numel-playground/app/platform_client.py)
  App-facing client for the platform HTTP layer.

Data model direction:

- database for platform metadata
- git repos for versioned space contents
- docker for isolated prod execution
- django for identity/auth and related user-management concerns

Submodule note:

- `app/platform_prod` may be mounted as a private git submodule
- if so, keep that submodule at the same path in every repo where you want the
  shared chat/bootstrap docs to remain accurate

## What Works Now

Local/reference path:

- local auth and admin bootstrap
- users, profiles, quotas, friendships
- spaces, git-backed assets, refs, history
- credentials/secrets through the platform layer
- one-current-workflow-per-space UI and API
- console, planner, `/gen`, toolkit/skill management

Production path:

- PostgreSQL-backed platform metadata
- in-repo Django identity service under
  [services/identity_django](/c:/devel/numel-playground/services/identity_django)
- Docker Engine API runtime adapter
- CPU and CUDA runtime images under
  [runtime/numel_runtime](/c:/devel/numel-playground/runtime/numel_runtime)
- real live prod compose stack under
  [deploy/docker-compose.prod.yml](/c:/devel/numel-playground/deploy/docker-compose.prod.yml)

## Verified Milestones

These are already verified in this repo:

- full app works on `platform_local`
- `platform_prod` boots with PostgreSQL + Django identity + Docker runtime
- `numel-runtime:latest` executes a real workflow in-container
- `numel-runtime:cuda` builds and smoke-runs
- live prod compose smoke succeeded through:
  auth, current space, workflow save, credential save, workflow start,
  execution polling, and result retrieval

Important deployment detail:

- [deploy/runtime-builder.sh](/c:/devel/numel-playground/deploy/runtime-builder.sh)
  now rebuilds inner runtime images when runtime-relevant sources change,
  instead of only when the image is missing

## Key Decisions

- Keep Django for identity/auth and adjacent account concerns, not for the whole
  Numel product.
- Keep the local/reference implementation fully working and keep prod as a
  backend swap beneath the same interface.
- Use database + git, not one in place of the other.
- Keep `${VAR_NAME}` substitution at execution time for runtime-input node
  fields, not as a save-time mutation.
- Default production secrets backend is database-backed, not Vault.
- Runtime images are pinned to:
  `torch==2.10.0`, `torchvision==0.25.0`, `torchaudio==2.10.0`
  with CUDA `12.8.1` / `cu128` for the GPU image.

## Known Follow-Ups

Strong next candidates after the current state:

- continue production hardening and operational tooling
- add stronger observability and admin diagnostics
- keep refining the platform domain around ownership, sharing, and permissions
- extend the prod deployment story if you want a more turnkey setup than the
  current compose bundle

## If You Fork

Recommended files to copy or keep in sync across both repos:

- [docs/fork-handoff.md](/c:/devel/numel-playground/docs/fork-handoff.md)
- [docs/chat-bootstrap.md](/c:/devel/numel-playground/docs/chat-bootstrap.md)
- [docs/platform-domain.md](/c:/devel/numel-playground/docs/platform-domain.md)
- [docs/platform-db-git.md](/c:/devel/numel-playground/docs/platform-db-git.md)
- [docs/runtime-container-contract.md](/c:/devel/numel-playground/docs/runtime-container-contract.md)

If `app/platform_prod` is private, keep the submodule path itself aligned too:

- `app/platform_prod`

This does not make one live chat session automatically span two repos, but it
does give both repos the same durable working context.
