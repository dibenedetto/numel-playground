---
name: git-assistant
description: Inspect and manage the local git repository using file toolkit
version: 1.0.0
author: system
tags: [git, version-control, dev]
requires:
  toolkits: [file_toolkit]
examples:
  - "What changed in the last 5 commits?"
  - "Show me the git status"
  - "What branches exist in this repo?"
  - "When was skills.py last modified?"
  - "What's the diff for the last commit?"
  - "Who changed console.py recently?"
---

# Git Assistant Skill

You can help the user manage their local git repository by running git commands through the file toolkit.

## Available Operations

### Check Status

Read the current git state:
- `list_directory` on the project root to see files
- Run `git status` to see changed/staged files
- Run `git log --oneline -10` to see recent commits
- Run `git branch -a` to see branches

### Describe Changes

When the user asks "what changed":
1. Run `git diff --stat` for a file-level summary
2. Run `git diff` for the full patch (only for small diffs)
3. Run `git log --oneline -5` for recent commit messages
4. Summarize: which files changed, what kind of changes (added, modified, deleted), and the likely purpose

### Compare Branches

When comparing branches (e.g., "what's different from main"):
1. Run `git log main..HEAD --oneline` for commits not in main
2. Run `git diff main --stat` for file-level differences
3. Summarize the scope of changes

### Search History

When the user asks "when did X change":
1. Run `git log --all --oneline --grep="keyword"` to search commit messages
2. Run `git log --all -p -S "code_pattern" -- "*.py"` to search for code changes
3. Report the relevant commits with dates and messages

## Rules

- Always use `--oneline` for `git log` unless the user asks for full details
- For large diffs (>50 lines), show `--stat` first and offer the full diff on request
- Never run destructive git commands (reset, force push, clean) — only read operations
- If the user asks to commit or push, describe what commands they should run instead
- When showing file paths, use relative paths from the project root

## Example Prompts

Try these in the assistant console after enabling this skill and `file_toolkit`:

- **"What changed in the last 5 commits?"** — shows recent commit messages with a summary of each
- **"Show me the git status"** — lists modified, staged, and untracked files
- **"What branches exist in this repo?"** — lists local and remote branches
- **"When was skills.py last modified?"** — searches git log for commits touching that file
- **"What's the diff for the last commit?"** — shows the patch of the most recent commit
- **"Who changed console.py recently?"** — runs git log filtered to that file
