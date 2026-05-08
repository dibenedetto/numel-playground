"""Proactive runtime config — overlay file on top of in-code defaults.

Every tunable in the proactive stack (Optimization thresholds, the
recent_thumbs_down veto threshold, LLM-proposer alias / window sizes /
prompt, default scopes for transports and agents, etc.) used to be a
module-level constant. M5.9 keeps the constants as the *defaults* but
adds a single overlay file — `state_dir() / "proactive_config.json"`
— that can override any subset by dotted path.

Resolution rule for `cfg(path, default)`:

  1. If the dotted path is set in `proactive_config.json`, return that value.
  2. Otherwise return `default` (the value reading code's hardcoded constant).

This keeps developers in control of safe defaults (you can read the
constant in code and know what the system does without consulting a
file), while letting operators tune behaviour without touching code.
The pattern matches the rest of the proactive state's storage idiom
(JSON in `state_dir()`).

Public API:

    cfg(path, default)               -> any                resolve a single path
    get_overrides()                  -> dict               raw overlay file contents
    set_override(path, value)        -> dict               persist a value, return new overlay
    clear_override(path=None)        -> dict               clear one path or all overrides
    list_known_paths()               -> list[str]          paths the modules call into

`set_override` / `clear_override` rewrite `proactive_config.json`
atomically (uses persistence.write_json under the hood).
"""

from __future__ import annotations

from pathlib import Path
from typing  import Any, Dict, List, Optional

from . import persistence as _persistence


_OVERRIDE_FILE = "proactive_config"   # → proactive_config.json
_PROMPTS_SUBDIR = "prompts"            # state_dir()/prompts/<name>.txt overrides
_PACKAGE_PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"


# Centralised registry of dotted paths the proactive modules read. Modules
# also pass their hardcoded default into `cfg(...)`, so this list is for
# *introspection* (HTTP endpoint, docs) — never the source of truth for the
# default values themselves.
_KNOWN_PATHS: List[str] = [
    # Optimization strategies
    "optimization.deny_rate_threshold",
    "optimization.deny_min_samples",
    "optimization.quarantine_failure_floor",
    "optimization.thumbs_up_to_relax",
    # Implicit feedback weighting (read in two places — kept consistent here)
    "evolution.implicit_weight",
    "evolution.thumbs_down_veto_threshold",
    # LLM-backed proposer
    "llm_proposer.alias",
    "llm_proposer.ledger_limit",
    "llm_proposer.feedback_limit",
    # Model identity for the auto-registered default proposer (ollama by
    # default — set source / name / base_url / api_key_env to point at
    # any OpenAI-compat or Anthropic endpoint without writing Python).
    "llm_proposer.model.source",
    "llm_proposer.model.name",
    "llm_proposer.model.base_url",
    "llm_proposer.model.api_key_env",
    # Default scopes for newly registered Capabilities
    "transports.default_scopes",
    "agents.default_scopes.local",
    "agents.default_scopes.endpoint",
    "agents.default_scopes.a2a",
]


def list_known_paths() -> List[str]:
    """Return the dotted paths the proactive modules consult. Operators can
    use this list as a discovery surface — every entry is a knob they can
    set in `proactive_config.json` to override the in-code default."""
    return list(_KNOWN_PATHS)


def get_overrides() -> Dict[str, Any]:
    """Return the raw contents of `proactive_config.json` (empty dict when
    the file doesn't exist or is unreadable). The structure is nested by
    dotted-path segments — e.g. `{"optimization": {"deny_rate_threshold":
    0.40}}` overrides `optimization.deny_rate_threshold`."""
    data = _persistence.read_json(_OVERRIDE_FILE, default={})
    return data if isinstance(data, dict) else {}


def cfg(path: str, default: Any) -> Any:
    """Resolve a single dotted-path tunable.

    Returns the overlay-file value if present at the path, else `default`.
    Reading is fast (single JSON load + dict descent) so callers don't
    need to memoise — propose() etc. can call this on every invocation
    without measurable overhead."""
    if not path:
        return default
    overrides = get_overrides()
    cur: Any = overrides
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return default
        cur = cur[part]
    return cur


def set_override(path: str, value: Any) -> Dict[str, Any]:
    """Persist a single dotted-path override into `proactive_config.json`.
    Creates intermediate dicts as needed. Returns the new overlay dict.

    Note: setting a path that's not in `_KNOWN_PATHS` is allowed (forward
    compat) — but it has no effect unless some module reads the path."""
    if not path:
        raise ValueError("path must be non-empty")
    parts = path.split(".")
    overrides = get_overrides()
    cur: Dict[str, Any] = overrides
    for part in parts[:-1]:
        nxt = cur.get(part)
        if not isinstance(nxt, dict):
            nxt = {}
            cur[part] = nxt
        cur = nxt
    cur[parts[-1]] = value
    _persistence.write_json(_OVERRIDE_FILE, overrides)
    return overrides


def load_prompt(name: str, *, default: Optional[str] = None) -> str:
    """Load a named prompt as plain text.

    Resolution: `state_dir()/prompts/<name>.txt` (operator override) wins
    over `app/proactive/prompts/<name>.txt` (package-shipped default)
    wins over the `default` parameter (caller-supplied last-resort).

    Returns the file contents stripped of a single trailing newline so
    the caller can format the prompt without worrying about an extra
    blank line at the end. Empty files return "" (not the default — an
    empty file is an explicit "I want no prompt" choice)."""
    if not name:
        raise ValueError("prompt name must be non-empty")

    overlay = _persistence.state_dir() / _PROMPTS_SUBDIR / f"{name}.txt"
    pkg     = _PACKAGE_PROMPTS_DIR / f"{name}.txt"

    for path in (overlay, pkg):
        if path.is_file():
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                continue
            return text.rstrip("\n")

    if default is None:
        raise FileNotFoundError(
            f"prompt {name!r} not found at {overlay} or {pkg} and no default supplied"
        )
    return default


def list_prompt_overrides() -> List[Dict[str, Any]]:
    """Return the catalogue of {name, source: 'overlay'|'package', path} for
    every prompt the system can resolve. Useful for the discovery
    endpoint and the docs."""
    out: Dict[str, Dict[str, Any]] = {}
    pkg_dir = _PACKAGE_PROMPTS_DIR
    overlay_dir = _persistence.state_dir() / _PROMPTS_SUBDIR
    if pkg_dir.is_dir():
        for p in sorted(pkg_dir.glob("*.txt")):
            out[p.stem] = {"name": p.stem, "source": "package", "path": str(p)}
    if overlay_dir.is_dir():
        for p in sorted(overlay_dir.glob("*.txt")):
            out[p.stem] = {"name": p.stem, "source": "overlay", "path": str(p)}
    return list(out.values())


def clear_override(path: Optional[str] = None) -> Dict[str, Any]:
    """Clear a single override path, or all overrides when `path` is None.
    Returns the resulting overlay dict (empty when cleared all)."""
    if path is None:
        _persistence.write_json(_OVERRIDE_FILE, {})
        return {}
    parts = path.split(".")
    overrides = get_overrides()
    # Walk to the parent dict, then pop the leaf.
    cur: Any = overrides
    for part in parts[:-1]:
        if not isinstance(cur, dict) or part not in cur:
            return overrides   # nothing to clear
        cur = cur[part]
    if isinstance(cur, dict):
        cur.pop(parts[-1], None)
    _persistence.write_json(_OVERRIDE_FILE, overrides)
    return overrides
