# Shared Context Files

Use this document when you want to keep the original repo and a private fork
aligned from a project-memory point of view.

## Where To Put The Shared Files

To make chats in the two repos talk about the same project context, put the
shared files **inside both repos**, using the **same relative paths**.

Recommended rule:

- keep the docs in `docs/` in both repos
- keep backend/config files in `app/` and `deploy/` in both repos
- if `app/platform_prod` is a private git submodule, keep the submodule mounted
  at that same path in both repos
- do not move these files to arbitrary folders if you want the bootstrap prompt
  to keep working unchanged

At minimum, these two files should exist in both repos at these exact paths:

- `docs/fork-handoff.md`
- `docs/chat-bootstrap.md`

For the broader shared context, keep these files at the same repo-relative
paths in both repos:

- `docs/fork-handoff.md`
- `docs/chat-bootstrap.md`
- `docs/platform-domain.md`
- `docs/platform-db-git.md`
- `docs/runtime-container-contract.md`
- `docs/shared-context-files.md`
- `app/platform_backend.json`
- `deploy/platform_backend.prod.json`
- `deploy/docker-compose.prod.yml`
- `deploy/runtime-builder.sh`
- `deploy/Dockerfile.app`
- `deploy/Dockerfile.identity`
- `README.md`

## How This Helps Chats Stay Aligned

The important practical point is:

- the files must exist in both repos
- they should live at the same paths in both repos
- if `app/platform_prod` is a private submodule, it should stay at
  `app/platform_prod` in both repos
- when you start a new chat in either repo, tell the chat to read those files

That means the shared context is not automatic. The new chat still needs an
opening instruction such as:

```text
Please read docs/chat-bootstrap.md and docs/fork-handoff.md first, then continue from the current repo state.
```

If both repos contain the same files at the same paths, that opening prompt can
be reused unchanged and both chats will start from the same written context.

## Recommended Opening Instruction

This is the most useful short opening instruction to reuse in either repo:

```text
Please read docs/chat-bootstrap.md and docs/fork-handoff.md first, then inspect the current repo state, including the app/platform_prod submodule if present, and continue from there.
```

If you want a slightly stronger version that also pulls in the deeper
architecture docs, use:

```text
Please read docs/chat-bootstrap.md, docs/fork-handoff.md, docs/platform-domain.md, docs/platform-db-git.md, and docs/runtime-container-contract.md first, then inspect the current repo state, including the app/platform_prod submodule if present, and continue from there.
```

## Minimum Shared Set

These are the two most important files to share between repos.

- [fork-handoff.md](/c:/devel/numel-playground/docs/fork-handoff.md)
- [chat-bootstrap.md](/c:/devel/numel-playground/docs/chat-bootstrap.md)

This minimum set is enough to carry:

- the current architectural state
- the main decisions already made
- the current next-step direction
- a reusable prompt for resuming work in a new chat

## Recommended Shared Set

These files are worth sharing if you want the fork to preserve the current
architecture and deployment context, not just the high-level handoff.

- [fork-handoff.md](/c:/devel/numel-playground/docs/fork-handoff.md)
- [chat-bootstrap.md](/c:/devel/numel-playground/docs/chat-bootstrap.md)
- [platform-domain.md](/c:/devel/numel-playground/docs/platform-domain.md)
- [platform-db-git.md](/c:/devel/numel-playground/docs/platform-db-git.md)
- [runtime-container-contract.md](/c:/devel/numel-playground/docs/runtime-container-contract.md)
- [platform_backend.json](/c:/devel/numel-playground/app/platform_backend.json)
- [platform_backend.prod.json](/c:/devel/numel-playground/deploy/platform_backend.prod.json)
- [docker-compose.prod.yml](/c:/devel/numel-playground/deploy/docker-compose.prod.yml)
- [runtime-builder.sh](/c:/devel/numel-playground/deploy/runtime-builder.sh)
- [Dockerfile.app](/c:/devel/numel-playground/deploy/Dockerfile.app)
- [Dockerfile.identity](/c:/devel/numel-playground/deploy/Dockerfile.identity)
- [README.md](/c:/devel/numel-playground/README.md)

## What Each Group Is For

Minimum shared set:

- keeps the project memory portable
- helps resume work in a new chat
- is the lightest option if the fork will diverge quickly

Recommended shared set:

- keeps the architecture docs aligned
- keeps the backend-selection model aligned
- keeps the current production deployment story aligned
- keeps the submodule-based prod/backend split easier to explain in future chats
- is better if both repos will continue evolving in parallel

## Practical Sync Strategy

Simple approach:

1. Update the shared files in the repo where the decision changed.
2. Commit those files.
3. Copy or cherry-pick the same files into the other repo.

Good rule:

- always sync [fork-handoff.md](/c:/devel/numel-playground/docs/fork-handoff.md)
  and [chat-bootstrap.md](/c:/devel/numel-playground/docs/chat-bootstrap.md)
  whenever a major architectural or workflow decision changes

## Important Limitation

Sharing these files does not make one live chat session automatically span two
repo workspaces.

What it does give you is a durable, repo-native shared context layer that can
be used in both repos and pasted into future chats.
