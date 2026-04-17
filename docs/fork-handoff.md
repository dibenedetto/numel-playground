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
- production deploy config: private production repo only, typically at
  `app/platform_prod/deploy/platform_backend.prod.json`

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
- [docs/public-private-boundary.md](/c:/devel/numel-playground/docs/public-private-boundary.md)
  Recommended commercial boundary between the public repo and the private prod slice.
- [docs/feature-tier-matrix.md](/c:/devel/numel-playground/docs/feature-tier-matrix.md)
  Concrete recommendation for what should stay shared/public and what should move to `prod`.
- [docs/product-roadmap.md](/c:/devel/numel-playground/docs/product-roadmap.md)
  Current product direction and prioritization for making Numel more compelling.
- [docs/ui-exploration-plan.md](/c:/devel/numel-playground/docs/ui-exploration-plan.md)
  Current UI/product design exploration plan for making Numel feel less intimidating and more product-like.

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
- Docker Engine API runtime adapter
- CPU and CUDA runtime images under
  [runtime/numel_runtime](/c:/devel/numel-playground/runtime/numel_runtime)
- production deployment assets and compose stack in
  `app/platform_prod/deploy/` in the private prod repo

## Verified Milestones

These are already verified across the local repo plus the private prod slice:

- full app works on `platform_local`
- `platform_prod` boots with PostgreSQL + Django identity + Docker runtime
- `numel-runtime:latest` executes a real workflow in-container
- `numel-runtime:cuda` builds and smoke-runs
- live prod deployment smoke succeeded through:
  auth, current space, workflow save, credential save, workflow start,
  execution polling, and result retrieval

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
- extend the private prod deployment story if you want a more turnkey setup
- follow [docs/product-roadmap.md](/c:/devel/numel-playground/docs/product-roadmap.md) for product-facing priorities like onboarding, templates, planner-first UX, and stronger space/project framing
- use [docs/ui-exploration-plan.md](/c:/devel/numel-playground/docs/ui-exploration-plan.md)
  before the next major product-facing UI implementation wave

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
