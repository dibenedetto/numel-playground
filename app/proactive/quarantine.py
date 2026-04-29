"""Substrate Quarantine + Snapshots — Phase 3 (M3.4).

Two responsibilities, intentionally co-located because they're both
operator-facing recovery mechanisms:

QUARANTINE
  Tracks per-key failure counts within a rolling window and flips a
  `quarantined` flag once the threshold is hit. Quarantined keys
  refuse subsequent actuation requests until an operator releases
  them. The Governor consults `is_quarantined(capability)` before
  emitting a verdict; failures (deny / error) call `record_failure`.

SNAPSHOTS
  Filesystem snapshots of the proactive state directory — the
  Substrate's own "Known Good State" implementation. Mirrors the
  existing workflow-snapshot pattern: take_snapshot() copies all
  state files into a versioned subdir; restore_snapshot(id) overwrites
  the live files. The snapshots/ directory is excluded from
  snapshots themselves (no recursion).

State directory comes from proactive.persistence.state_dir().
"""

from __future__ import annotations

import json
import shutil
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List

from .persistence import read_json, state_dir, write_json


# ============================================================================
# Quarantine
# ============================================================================

DEFAULT_FAILURE_THRESHOLD = 3
DEFAULT_FAILURE_WINDOW_S  = 600.0  # 10 minutes


def _load_quarantine() -> Dict[str, Any]:
    return read_json("quarantine", default={"keys": {}})


def _save_quarantine(data: Dict[str, Any]) -> None:
    write_json("quarantine", data)


def is_quarantined(key: str) -> bool:
    if not key:
        return False
    entry = (_load_quarantine().get("keys") or {}).get(key) or {}
    return bool(entry.get("quarantined"))


def record_failure(
    key: str,
    *,
    reason: str = "",
    threshold: int   = DEFAULT_FAILURE_THRESHOLD,
    window_s:  float = DEFAULT_FAILURE_WINDOW_S,
) -> Dict[str, Any]:
    """Increment failure count for `key`; quarantine if threshold reached
    within the rolling window. Returns the resulting state for `key`."""
    if not key:
        return {}
    data  = _load_quarantine()
    keys  = data.setdefault("keys", {})
    entry = keys.setdefault(key, {"failures": [], "quarantined": False})

    now    = time.time()
    cutoff = now - window_s
    entry["failures"] = [f for f in entry["failures"] if f.get("ts", 0) >= cutoff]
    entry["failures"].append({"ts": now, "reason": reason})

    if not entry["quarantined"] and len(entry["failures"]) >= threshold:
        entry["quarantined"]        = True
        entry["quarantined_at"]     = now
        entry["quarantined_reason"] = (
            f"{len(entry['failures'])} failures in last {int(window_s)}s"
        )

    _save_quarantine(data)
    return entry


def record_success(key: str) -> None:
    """Reset failure history on a clean pass-through. Does NOT auto-release
    a quarantined key — release is operator-driven."""
    if not key:
        return
    data = _load_quarantine()
    keys = data.get("keys") or {}
    if key in keys:
        keys[key]["failures"] = []
        _save_quarantine(data)


def release(key: str, reason: str = "manual") -> bool:
    """Explicit release. Returns True only if the key was actually
    quarantined."""
    if not key:
        return False
    data  = _load_quarantine()
    keys  = data.get("keys") or {}
    entry = keys.get(key)
    if not entry or not entry.get("quarantined"):
        return False
    entry["quarantined"]    = False
    entry["released_at"]    = time.time()
    entry["release_reason"] = reason
    entry["failures"]       = []
    _save_quarantine(data)
    return True


def list_keys() -> Dict[str, Any]:
    return _load_quarantine().get("keys") or {}


# ============================================================================
# Snapshots
# ============================================================================

_SNAPSHOTS_SUBDIR = "snapshots"


def _snapshots_root() -> Path:
    root = state_dir() / _SNAPSHOTS_SUBDIR
    root.mkdir(parents=True, exist_ok=True)
    return root


def take_snapshot(label: str = "") -> Dict[str, Any]:
    """Copy every top-level state file (excluding the snapshots/ dir
    itself) into a new snapshot subdir. Returns the manifest."""
    src    = state_dir()
    dst_id = f"snap_{int(time.time())}_{uuid.uuid4().hex[:6]}"
    dst    = _snapshots_root() / dst_id
    dst.mkdir(parents=True, exist_ok=False)

    files: List[str] = []
    for child in src.iterdir():
        if child.name == _SNAPSHOTS_SUBDIR:
            continue
        if not child.is_file():
            continue
        shutil.copy2(child, dst / child.name)
        files.append(child.name)

    manifest = {
        "id":         dst_id,
        "created_at": time.time(),
        "label":      str(label or "").strip(),
        "files":      files,
    }
    with (dst / "manifest.json").open("w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    return manifest


def list_snapshots() -> List[Dict[str, Any]]:
    """Return all snapshot manifests, newest first."""
    out: List[Dict[str, Any]] = []
    for entry in _snapshots_root().iterdir():
        if not entry.is_dir():
            continue
        manifest_path = entry / "manifest.json"
        if not manifest_path.is_file():
            continue
        try:
            with manifest_path.open(encoding="utf-8") as f:
                out.append(json.load(f))
        except (OSError, json.JSONDecodeError):
            continue
    out.sort(key=lambda m: m.get("created_at", 0), reverse=True)
    return out


def restore_snapshot(snapshot_id: str) -> Dict[str, Any]:
    """Overwrite live state files with the snapshot's contents. Files
    in the live state that aren't in the snapshot are preserved."""
    src = _snapshots_root() / snapshot_id
    if not src.is_dir():
        raise FileNotFoundError(f"snapshot '{snapshot_id}' not found")
    manifest_path = src / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"snapshot '{snapshot_id}' is missing manifest.json")
    with manifest_path.open(encoding="utf-8") as f:
        manifest = json.load(f)

    dst    = state_dir()
    copied: List[str] = []
    for name in manifest.get("files") or []:
        sf = src / name
        if sf.is_file():
            shutil.copy2(sf, dst / name)
            copied.append(name)

    return {
        "snapshot_id":      snapshot_id,
        "restored_files":   copied,
        "manifest":         manifest,
    }


def delete_snapshot(snapshot_id: str) -> bool:
    """Remove a snapshot subdirectory. Returns True if removed."""
    target = _snapshots_root() / snapshot_id
    if not target.is_dir():
        return False
    shutil.rmtree(target, ignore_errors=True)
    return not target.exists()
