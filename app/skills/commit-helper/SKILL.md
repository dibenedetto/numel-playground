---
name: commit-helper
description: Helps draft conventional commit messages from git diffs
version: 1.0.0
tags: [git, writing, productivity]
requires:
  toolkits: [code_toolkit]
examples:
  - "Draft a commit message for my staged changes"
  - "Summarize what I changed since last commit"
  - "Write a conventional commit for this diff"
---

# Commit Message Helper

When the user asks you to draft a commit message, follow these steps:

## Workflow

1. **Inspect changes** — Use the available tools to read the current git diff (staged or unstaged).
2. **Categorize** — Determine the change type:
   - `feat` — new feature or capability
   - `fix` — bug fix
   - `refactor` — code restructure without behavior change
   - `docs` — documentation only
   - `test` — adding or updating tests
   - `chore` — build, tooling, config changes
   - `style` — formatting, whitespace, no logic change
3. **Identify scope** — Look at which module, component, or area was modified (e.g., `auth`, `api`, `ui`).
4. **Write the message** using Conventional Commits format:

```
type(scope): short description (max 50 chars)

- Bullet point explaining what changed and why
- Another bullet if multiple logical changes
```

## Rules

- Subject line: imperative mood ("add", not "added"), max 50 characters
- Body: wrapped at 72 characters, explain *why* not just *what*
- If the diff is large, group related changes under sub-headings
- If there are unrelated changes, suggest splitting into multiple commits

## Example Prompts

- **"Draft a commit message for my staged changes"** — Inspect the diff and write a conventional commit
- **"Summarize what I changed since last commit"** — Read the diff and provide a plain-English summary
- **"Write a conventional commit for this diff"** — Format the message following the rules above
