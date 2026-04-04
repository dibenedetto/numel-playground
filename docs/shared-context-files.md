# Shared Context Files

Use this document when you want to keep the original repo and a private fork
aligned from a project-memory point of view.

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
