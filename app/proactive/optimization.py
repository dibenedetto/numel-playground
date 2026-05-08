"""Phase 4 — Optimization (M4.2). Phase-2 of Evolution.

Phase-2 Optimization is the offline, sandboxed side of Evolution per §11.
It proposes candidate changes to the substrate by analyzing live state
(Self-Reflective Debugging), runs hypothetical changes against the
historical Ledger (Synthetic Self-Play / Simulation), and returns
candidates in the same shape `proactive.evolution.run_alignment()`
consumes. Promotion is M4.3's job; this module only proposes and
simulates.

Concepts:

  Sandbox
    A context manager that flips `NUMEL_PROACTIVE_DIR` to a temp dir
    for its lifetime, restoring the previous value on exit. Anything
    written by `proactive.persistence.*` inside the block lives in the
    sandbox and is wiped at exit. Use for synthetic play that mustn't
    pollute live state.

  Strategy
    A function that scans live state and emits zero or more candidate
    dicts. Built-ins:
      tighten_governor          → propose constitution `never` rules for
                                  capabilities with persistently high
                                  deny rates.
      prune_quarantine          → propose constitution `never` rules for
                                  capabilities currently quarantined with
                                  many failures (promote a soft block to
                                  a hard ban).
      relax_constitution        → propose removing a constitution `never`
                                  rule when a capability has accumulated
                                  thumbs-up but is currently banned.

  Candidate (output shape)
    {
      "kind":      "constitution_rule_add" | "constitution_rule_remove",
      "target":    capability name,
      "payload":   { ... kind-specific ... },
      "rationale": human-readable string,
      "evidence":  { ... summary stats from the analysis ... },
    }

  Simulation
    `simulate_candidate(candidate, ledger=None)` replays the historical
    Ledger against the candidate's effect. For `constitution_rule_add`,
    every entry whose capability matches the rule's target is recoloured
    to `deny`; the diff reports how many entries changed and a sample.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

from . import evolution as _evolution
from . import persistence as _persistence
from . import quarantine  as _quarantine


# ============================================================================
# Sandbox
# ============================================================================

@contextmanager
def sandbox(seed_files: Optional[Dict[str, Any]] = None) -> Iterator[Path]:
    """Switch `state_dir()` to a fresh temp directory for the lifetime of
    this context. The previous `NUMEL_PROACTIVE_DIR` is restored on exit
    and the temp dir is removed.

    `seed_files` is a `{filename: data}` mapping written into the sandbox
    before yielding:

        - `*.json`  → `data` is JSON-encoded
        - `*.jsonl` → `data` is an iterable of records, one per line
        - other     → `data` is `str()`-cast and written as-is
    """
    tmp = Path(tempfile.mkdtemp(prefix="numel_sandbox_"))
    prev = os.environ.get("NUMEL_PROACTIVE_DIR")
    os.environ["NUMEL_PROACTIVE_DIR"] = str(tmp)
    try:
        if seed_files:
            for name, data in seed_files.items():
                target = tmp / name
                target.parent.mkdir(parents=True, exist_ok=True)
                if name.endswith(".json"):
                    target.write_text(json.dumps(data, indent=2, ensure_ascii=False),
                                      encoding="utf-8")
                elif name.endswith(".jsonl"):
                    lines = "\n".join(json.dumps(e, ensure_ascii=False) for e in (data or []))
                    target.write_text(lines + ("\n" if lines else ""), encoding="utf-8")
                else:
                    target.write_text(str(data), encoding="utf-8")
        yield tmp
    finally:
        if prev is None:
            os.environ.pop("NUMEL_PROACTIVE_DIR", None)
        else:
            os.environ["NUMEL_PROACTIVE_DIR"] = prev
        shutil.rmtree(tmp, ignore_errors=True)


# ============================================================================
# Self-Reflective Debugging — strategies that scan live state
# ============================================================================

# Tunable thresholds. Real implementation would learn these.
_DENY_RATE_THRESHOLD       = 0.50    # ≥50% of an action's verdicts are deny
_DENY_MIN_SAMPLES          = 4       # need at least N total verdicts
_QUARANTINE_FAILURE_FLOOR  = 5       # ≥N recorded failures → propose hard-ban
_THUMBS_UP_TO_RELAX        = 3       # ≥N thumbs-up to suggest relaxing a ban


def _per_cap_decisions(ledger: List[Dict[str, Any]]) -> Dict[str, Dict[str, int]]:
    out: Dict[str, Dict[str, int]] = {}
    for entry in ledger:
        v = entry.get("governor_verdict") or {}
        cap = v.get("capability")
        if not cap:
            continue
        d = v.get("decision") or "unknown"
        bucket = out.setdefault(cap, {})
        bucket[d] = bucket.get(d, 0) + 1
    return out


def _per_cap_thumbs(signals: List[Dict[str, Any]]) -> Dict[str, Dict[str, int]]:
    out: Dict[str, Dict[str, int]] = {}
    for s in signals:
        if s.get("kind") != _evolution.KIND_THUMBS:
            continue
        cap = (s.get("context") or {}).get("capability")
        if not cap:
            continue
        v = s.get("value") or "?"
        bucket = out.setdefault(cap, {})
        bucket[v] = bucket.get(v, 0) + 1
    return out


def _per_cap_signals(signals: List[Dict[str, Any]]) -> Dict[str, Dict[str, float]]:
    """Aggregate per-capability positive / negative signal weights.

    Explicit thumbs count 1.0; implicit signals count 0.5 (noisier — an
    operator dismissing a notification carries less information than them
    explicitly thumbing-down). Returns `{cap: {pos: float, neg: float,
    explicit_up: int, explicit_down: int, implicit_accept: int,
    implicit_reject: int}}` so strategies can choose how to read the data.
    """
    IMPLICIT_WEIGHT = 0.5
    out: Dict[str, Dict[str, float]] = {}
    for s in signals:
        cap = (s.get("context") or {}).get("capability")
        if not cap:
            continue
        bucket = out.setdefault(cap, {
            "pos":             0.0,
            "neg":             0.0,
            "explicit_up":     0,
            "explicit_down":   0,
            "implicit_accept": 0,
            "implicit_reject": 0,
        })
        kind = s.get("kind")
        if kind == _evolution.KIND_THUMBS:
            v = s.get("value")
            if v == "up":
                bucket["pos"] += 1.0
                bucket["explicit_up"] += 1
            elif v == "down":
                bucket["neg"] += 1.0
                bucket["explicit_down"] += 1
        elif kind == _evolution.KIND_IMPLICIT_ACCEPT:
            bucket["pos"] += IMPLICIT_WEIGHT
            bucket["implicit_accept"] += 1
        elif kind == _evolution.KIND_IMPLICIT_REJECT:
            bucket["neg"] += IMPLICIT_WEIGHT
            bucket["implicit_reject"] += 1
    return out


def strategy_tighten_governor(ledger: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Capabilities the Governor keeps denying → propose a hard ban."""
    candidates: List[Dict[str, Any]] = []
    constitution = _evolution.read_constitution()
    already_banned = {
        r.get("target")
        for r in (constitution.get("rules") or [])
        if isinstance(r, dict) and r.get("kind") == "never"
    }
    for cap, stats in _per_cap_decisions(ledger).items():
        if cap in already_banned:
            continue
        total = sum(stats.values())
        if total < _DENY_MIN_SAMPLES:
            continue
        denies = stats.get("deny", 0)
        if denies / total < _DENY_RATE_THRESHOLD:
            continue
        candidates.append({
            "kind":      "constitution_rule_add",
            "target":    cap,
            "payload":   {"rule": {"kind": "never", "target": cap}},
            "rationale": (
                f"{denies}/{total} verdicts on '{cap}' were deny — "
                "promote the soft block to a User Constitution rule."
            ),
            "evidence":  {"capability": cap, "verdict_counts": stats},
            "by":        "tighten_governor",
        })
    return candidates


def strategy_prune_quarantine(quarantine_keys: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Currently-quarantined capabilities with a long failure history →
    promote the quarantine to a hard constitution rule."""
    candidates: List[Dict[str, Any]] = []
    constitution = _evolution.read_constitution()
    already_banned = {
        r.get("target")
        for r in (constitution.get("rules") or [])
        if isinstance(r, dict) and r.get("kind") == "never"
    }
    for cap, info in (quarantine_keys or {}).items():
        if cap in already_banned:
            continue
        if not isinstance(info, dict) or not info.get("quarantined"):
            continue
        fails = info.get("failures") or []
        if len(fails) < _QUARANTINE_FAILURE_FLOOR:
            continue
        candidates.append({
            "kind":      "constitution_rule_add",
            "target":    cap,
            "payload":   {"rule": {"kind": "never", "target": cap}},
            "rationale": (
                f"'{cap}' is quarantined with {len(fails)} recorded failures — "
                "propose a hard ban via the User Constitution."
            ),
            "evidence":  {"capability": cap, "failure_count": len(fails),
                          "quarantined_reason": info.get("quarantined_reason")},
            "by":        "prune_quarantine",
        })
    return candidates


def strategy_relax_constitution(
    ledger: List[Dict[str, Any]],
    signals: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Constitution-banned capabilities that have accumulated positive user
    signal (explicit thumbs-up + implicit acceptance) → suggest removing
    the rule. Implicit signals count half (per `_per_cap_signals`) so an
    operator letting an action stand isn't treated as the same evidence
    as them explicitly thumbing-up."""
    constitution = _evolution.read_constitution()
    rules = [r for r in (constitution.get("rules") or [])
             if isinstance(r, dict) and r.get("kind") == "never"]
    if not rules:
        return []
    per_cap = _per_cap_signals(signals)
    candidates: List[Dict[str, Any]] = []
    for rule in rules:
        cap = rule.get("target")
        if not cap:
            continue
        bucket  = per_cap.get(cap) or {}
        weight  = float(bucket.get("pos") or 0.0)
        if weight < float(_THUMBS_UP_TO_RELAX):
            continue
        candidates.append({
            "kind":      "constitution_rule_remove",
            "target":    cap,
            "payload":   {"rule_id": rule.get("id"), "rule": rule},
            "rationale": (
                f"'{cap}' is constitution-banned but has accumulated positive signal "
                f"(weighted={weight:.1f}; explicit thumbs-up: {bucket.get('explicit_up', 0)}, "
                f"implicit accept: {bucket.get('implicit_accept', 0)}) — "
                "user signal contradicts the rule; suggest removal."
            ),
            "evidence":  {
                "capability":      cap,
                "weighted_pos":    weight,
                "explicit_up":     bucket.get("explicit_up", 0),
                "implicit_accept": bucket.get("implicit_accept", 0),
                "rule_id":         rule.get("id"),
            },
            "by":        "relax_constitution",
        })
    return candidates


def propose_from_state() -> List[Dict[str, Any]]:
    """Run every built-in strategy against current live state.

    Reads from `state_dir()` — either the live state or, if invoked
    inside a `sandbox()` block, the sandbox state.
    """
    ledger = _persistence.read_jsonl("ledger")
    signals = _persistence.read_jsonl("alignment_signals")
    quar = _quarantine.list_keys()

    out: List[Dict[str, Any]] = []
    out.extend(strategy_tighten_governor(ledger))
    out.extend(strategy_prune_quarantine(quar))
    out.extend(strategy_relax_constitution(ledger, signals))

    # Stamp each candidate with a consistent surface for downstream layers.
    now = time.time()
    for c in out:
        c.setdefault("ts", now)
    return out


# ============================================================================
# Synthetic Self-Play / Simulation — replay against the historical Ledger
# ============================================================================

def simulate_constitution_rule_add(
    ledger: List[Dict[str, Any]],
    rule:   Dict[str, Any],
) -> Dict[str, Any]:
    """If a `never` rule on `target` had been in place, every Ledger entry
    on that capability whose verdict was NOT already `deny` would have
    been recoloured to `deny`."""
    target = (rule or {}).get("target")
    if (rule or {}).get("kind") != "never" or not target:
        return {"changed": 0, "unchanged": len(ledger), "examples": []}

    changed   = 0
    unchanged = 0
    examples: List[Dict[str, Any]] = []
    for entry in ledger:
        v = entry.get("governor_verdict") or {}
        cap = v.get("capability")
        if cap == target and v.get("decision") not in ("deny", None):
            changed += 1
            if len(examples) < 5:
                examples.append({
                    "id":  entry.get("id"),
                    "cap": cap,
                    "old": v.get("decision"),
                    "new": "deny",
                })
        else:
            unchanged += 1
    return {"changed": changed, "unchanged": unchanged, "examples": examples}


def simulate_constitution_rule_remove(
    ledger:  List[Dict[str, Any]],
    signals: List[Dict[str, Any]],
    rule:    Dict[str, Any],
) -> Dict[str, Any]:
    """Removing a `never` rule lifts the auto-deny for that capability.
    Without rerunning the Governor we can't predict what each entry
    *would* have decided — so the simulation reports the count of past
    `deny`s on that capability that *might* relax."""
    target = (rule or {}).get("target")
    relaxable: List[Dict[str, Any]] = []
    for entry in ledger:
        v = entry.get("governor_verdict") or {}
        if v.get("capability") == target and v.get("decision") == "deny":
            relaxable.append({"id": entry.get("id"), "old": "deny",
                              "reason_was": v.get("reason")})
    thumbs_up = sum(
        1 for s in signals
        if s.get("kind") == _evolution.KIND_THUMBS
        and (s.get("context") or {}).get("capability") == target
        and s.get("value") == "up"
    )
    return {
        "rule_target":      target,
        "relaxable_denies": len(relaxable),
        "examples":         relaxable[:5],
        "thumbs_up_total":  thumbs_up,
    }


def simulate_candidate(
    candidate: Dict[str, Any],
    ledger:    Optional[List[Dict[str, Any]]] = None,
    signals:   Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Top-level dispatch — runs the appropriate simulation for the
    candidate's `kind`. Returns a diff report; never applies the change.
    Reads ledger / signals from current state when not supplied."""
    if not isinstance(candidate, dict):
        return {"kind": "invalid", "reason": "candidate must be a dict"}
    kind = candidate.get("kind")

    if ledger is None:
        ledger = _persistence.read_jsonl("ledger")
    if signals is None:
        signals = _persistence.read_jsonl("alignment_signals")

    payload = candidate.get("payload") or {}
    if kind == "constitution_rule_add":
        rule = payload.get("rule") or {}
        return {
            "kind":      "constitution_rule_add_simulation",
            "candidate": candidate,
            "diff":      simulate_constitution_rule_add(ledger, rule),
        }
    if kind == "constitution_rule_remove":
        rule = payload.get("rule") or {}
        return {
            "kind":      "constitution_rule_remove_simulation",
            "candidate": candidate,
            "diff":      simulate_constitution_rule_remove(ledger, signals, rule),
        }

    return {
        "kind":      "unsupported",
        "candidate": candidate,
        "reason":    f"no simulator for kind={kind!r}",
    }
