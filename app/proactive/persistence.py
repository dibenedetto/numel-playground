"""Substrate persistence for the Proactive Agent Ecology — Phase 3 (M3.1).

Provides JSON-backed durable storage for the substrate:
  - World Model              → world_model.json
  - Goals                    → goals.json
  - Capability Registry      → capabilities.json
  - Pending Consents (Social)→ pending_consents.json
  - Motor Actions            → actions.jsonl    (append-only)
  - Ledger                   → ledger.jsonl     (append-only)

State directory resolution:
  1. NUMEL_PROACTIVE_DIR environment variable, if set
  2. <repo_root>/app/storage/proactive/   (default; gitignored via storage/)

Workflow `transform_flow` scripts import the helpers below directly.
A typical pattern is:

    from proactive.persistence import read_json, write_json, append_jsonl
    goals = variables.get("goals")
    if goals is None:
        goals = read_json("goals", default={})
        variables["goals"] = goals
    # ... mutate ...
    write_json("goals", goals)

`variables` is used as an in-memory cache within a single workflow run;
the JSON file is the durable source of truth across runs.
"""

from __future__ import annotations

import contextlib
import contextvars
import json
import os
import threading
from pathlib import Path
from typing import Any, Iterator, List, Optional


_DEFAULT_REL = "app/storage/proactive"
_lock = threading.Lock()


# Per-task override. Set by `use_state_dir(path)` (or by integrations like
# the HTTP `X-Proactive-Dir` middleware / workflow options /
# proactive_state_dir_flow node). Innermost-set value wins because the
# `use_state_dir` context manager stacks. None means "fall through to env
# var, then to the package default".
_STATE_DIR_OVERRIDE: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "proactive_state_dir_override", default=None,
)


def _project_root() -> Path:
    # app/proactive/persistence.py → up 3 levels to repo root
    return Path(__file__).resolve().parents[2]


def state_dir() -> Path:
    """Resolve the proactive state directory; create if missing.

    Resolution order (most-local wins):
      1. `use_state_dir(...)` context var override — set by the HTTP
         middleware, workflow runner, or the proactive_state_dir_flow node.
      2. `NUMEL_PROACTIVE_DIR` env var — process-wide default
         (settable via `app.py --proactive-dir <path>`).
      3. `<repo>/app/storage/proactive` — package default.
    """
    override = _STATE_DIR_OVERRIDE.get()
    if override:
        root = Path(override).resolve()
    else:
        env = os.environ.get("NUMEL_PROACTIVE_DIR", "").strip()
        root = Path(env).resolve() if env else (_project_root() / _DEFAULT_REL).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def state_dir_source() -> str:
    """Return how the current `state_dir()` value was resolved:
    `"override"`, `"env"`, or `"default"`. Useful for the
    `/proactive/state_dir` introspection endpoint and for the docs."""
    if _STATE_DIR_OVERRIDE.get():
        return "override"
    if (os.environ.get("NUMEL_PROACTIVE_DIR") or "").strip():
        return "env"
    return "default"


@contextlib.contextmanager
def use_state_dir(path: Any) -> Iterator[Path]:
    """Override the proactive state directory for the duration of this
    block (and any awaited tasks that inherit this `contextvars.Context`).
    Falsy `path` is a no-op — useful for `with use_state_dir(maybe_dir):`
    patterns where the override may or may not be configured.

    Stacking works naturally — nested `use_state_dir` blocks set the
    innermost path while the block is active and restore the outer one
    on exit. Concurrent async tasks each see their own override because
    `ContextVar` is task-scoped."""
    if not path:
        yield state_dir()
        return
    token = _STATE_DIR_OVERRIDE.set(str(path))
    try:
        yield state_dir()
    finally:
        _STATE_DIR_OVERRIDE.reset(token)


def set_state_dir_override(path: Any) -> contextvars.Token:
    """Lower-level than `use_state_dir` — set the override and return the
    token so the caller can `reset()` it later. Used by the HTTP
    middleware (which can't easily wrap downstream handlers in a `with`)
    and by the `proactive_state_dir_flow` node (which sets the override
    that downstream nodes inherit, never resets it — the engine cleans up
    when the workflow's task ends)."""
    if path:
        return _STATE_DIR_OVERRIDE.set(str(path))
    return _STATE_DIR_OVERRIDE.set(None)


def reset_state_dir_override(token: contextvars.Token) -> None:
    """Companion to `set_state_dir_override` — restore the previous value."""
    _STATE_DIR_OVERRIDE.reset(token)


def read_json(name: str, default: Optional[Any] = None) -> Any:
    """Read a JSON file under state_dir(); return default (or {}) if missing."""
    path = state_dir() / f"{name}.json"
    if not path.is_file():
        return default if default is not None else {}
    try:
        with path.open(encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        # Corrupt or unreadable — surface a fresh default rather than crash
        # the substrate. Real impl would log and quarantine.
        return default if default is not None else {}


def write_json(name: str, data: Any) -> None:
    """Atomically write a JSON file under state_dir()."""
    path = state_dir() / f"{name}.json"
    tmp  = path.with_suffix(".json.tmp")
    with _lock:
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        tmp.replace(path)


def append_jsonl(name: str, entry: Any) -> None:
    """Append a single record to a JSONL file under state_dir()."""
    path = state_dir() / f"{name}.jsonl"
    line = json.dumps(entry, ensure_ascii=False)
    with _lock:
        with path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")


def read_jsonl(name: str) -> List[Any]:
    """Read all records from a JSONL file under state_dir()."""
    path = state_dir() / f"{name}.jsonl"
    if not path.is_file():
        return []
    out: List[Any] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def clear_state() -> None:
    """Remove every state file under state_dir(). Useful for demo resets."""
    root = state_dir()
    for child in root.iterdir():
        if child.is_file():
            try:
                child.unlink()
            except OSError:
                pass
