# Numel git hooks

Tracked pre-commit hooks that run alongside the project. Install once per
clone with:

```bash
git config core.hooksPath tools/git-hooks
```

That points git's hook search at this directory. Uninstall with
`git config --unset core.hooksPath`. The setting is per-clone (lives in
`.git/config`) so it doesn't ripple to teammates who haven't opted in.

## Hooks

### `pre-commit`

Runs `tools/lint_transforms.py` over any `examples/*.json` files in the
staged change set, blocking the commit if a `transform_flow` script
contains the four split-namespace exec hazards documented in
[`docs/transform-flow-scripts.md`](../../docs/transform-flow-scripts.md):
recursive `def`, helper-to-helper call, top-level constant captured into
a function body, and comprehension/genexp/lambda body referencing a
top-level name.

* Skips silently when no `examples/*.json` are staged.
* Picks a Python in this order: project `.venv`, system `python3`, system
  `python`. Skips silently if none is available (so the hook never
  becomes the single point of failure on a fresh clone).
* Bypass once with `git commit --no-verify` if you genuinely need to
  ship a hazard (the lint output names exact files / lines / hazard
  classes, so a bypass should be a deliberate decision, not a workaround).
