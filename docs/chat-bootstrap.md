# Chat Bootstrap

Use this file to resume work in a new chat, including in a private fork.

## Important Limitation

A live Codex/chat session is usually tied to the current workspace, not to the
Git repository graph. So one exact live thread usually cannot be shared across
two different repo workspaces automatically.

What *does* work well is:

- keep this file in both repos
- keep [fork-handoff.md](/c:/devel/numel-playground/docs/fork-handoff.md) in both repos
- if `app/platform_prod` is private, keep it mounted at the same
  `app/platform_prod` submodule path
- paste the prompt below into a new chat when you switch repos

## Resume Prompt

Paste something like this into a new chat:

```text
Please continue working on Numel from the current repo state.

Before making changes, read:
- docs/fork-handoff.md
- docs/chat-bootstrap.md
- docs/platform-domain.md
- docs/platform-db-git.md
- docs/runtime-container-contract.md

Important project context:
- Numel has a config-selected platform split: platform_local for the fully working local/reference backend, platform_prod for the production-oriented backend.
- app/platform_prod may be provided as a private git submodule and should be inspected when present.
- The app/interface should stay seamless across local and prod: same frontend and same public /platform, /spaces, /workflow, and /executions surface.
- The product model is space-centric with one current workflow per current space.
- Production currently uses PostgreSQL + Django identity + Docker runtime containers.
- Runtime images live under runtime/numel_runtime.
- deploy/runtime-builder.sh is responsible for content-aware inner runtime image rebuilds in prod compose.
- Database-backed secrets are the current default production choice.
- Legacy provider-era code and legacy workflow routes were intentionally removed.

Please inspect the current repo state first, then continue from there.
```

## Suggested Shared Context Policy

If you want two repos to stay aligned while you work in both:

- treat this file and `docs/fork-handoff.md` as the shared memory layer
- update them whenever a major architectural decision changes
- avoid relying on unstated chat memory for long-lived decisions

## What To Update When A Major Decision Changes

Update these when needed:

- backend architecture or deploy model
- local vs prod interface guarantees
- runtime image policy
- identity/secrets strategy
- workflow/space model
- highest-priority next steps
