"""Phase 4 — Promotion gate (M4.3). Closes the Evolution loop.

The promotion gate ties together M4.1 (Alignment) and M4.2 (Optimization).
It takes a candidate change, optionally simulates it, runs every
registered Phase-1 Alignment validator, and — if the aggregate verdict
is `pass` — applies the candidate to live state. A structured Ledger
entry records the full Why-chain regardless of outcome.

Per §11 of the conceptual blueprint:

    Gate: No Phase-2 output ships to production without an Alignment-
    pass record from every registered Phase-1 validator.

Public API:

    promote(candidate, *, simulate=True) -> dict

    Returns a dict capturing every step of the chain:
        {
            id:          ledger entry id of the promotion record,
            ts:          float,
            decision:    "applied" | "refused_by_validator" | "noop" |
                         "apply_failed" | "skipped_unknown_kind",
            candidate:   <input>,
            simulation:  <simulate_candidate result>  | None,
            alignment:   <run_alignment result>       | None,
            applied:     <kind-specific apply result> | None,
            ledger:      the entry written to the Ledger,
        }

The candidate kinds currently supported by the apply step are
`constitution_rule_add` and `constitution_rule_remove` — the same shapes
M4.2 strategies emit. New kinds register through `register_applier`.
"""

from __future__ import annotations

import time
import uuid
from typing import Any, Callable, Dict, List, Optional

from . import evolution     as _evolution
from . import optimization  as _optimization
from . import persistence   as _persistence


# ============================================================================
# Applier registry — one function per candidate kind
# ============================================================================

# An applier returns {status: "applied"|"noop"|"failed", ...kind-specific}.
_appliers: Dict[str, Callable[[Dict[str, Any]], Dict[str, Any]]] = {}


def register_applier(kind: str, fn: Callable[[Dict[str, Any]], Dict[str, Any]]) -> None:
    if not kind or not callable(fn):
        raise ValueError("register_applier needs a non-empty kind and a callable")
    _appliers[kind] = fn


def list_appliers() -> List[str]:
    return sorted(_appliers.keys())


def _apply_constitution_rule_add(candidate: Dict[str, Any]) -> Dict[str, Any]:
    rule = (candidate.get("payload") or {}).get("rule") or {}
    if not isinstance(rule, dict) or not rule.get("kind") or not rule.get("target"):
        return {"status": "failed", "reason": "candidate.payload.rule.{kind,target} required"}

    cur = _evolution.read_constitution()
    for existing in (cur.get("rules") or []):
        if (isinstance(existing, dict)
            and existing.get("kind")   == rule.get("kind")
            and existing.get("target") == rule.get("target")):
            return {
                "status":  "noop",
                "reason":  "rule already in effect",
                "rule_id": existing.get("id"),
                "version": cur.get("version"),
            }

    new_state = _evolution.update_constitution({"rules": [dict(rule)]})
    return {
        "status":             "applied",
        "constitution_version": new_state.get("version"),
    }


def _apply_constitution_rule_remove(candidate: Dict[str, Any]) -> Dict[str, Any]:
    payload = candidate.get("payload") or {}
    rule_id = payload.get("rule_id")
    rule    = payload.get("rule") or {}
    if not rule_id and not (rule.get("kind") and rule.get("target")):
        return {"status": "failed",
                "reason": "candidate.payload.rule_id or {kind,target} required"}

    res = _evolution.remove_rule(rule_id=rule_id, match=rule if rule else None)
    if not res.get("updated"):
        return {"status": "noop", "reason": "rule not present"}
    return {
        "status":             "applied",
        "removed":            res.get("removed"),
        "constitution_version": res.get("version"),
    }


# Auto-register the built-in appliers.
register_applier("constitution_rule_add",    _apply_constitution_rule_add)
register_applier("constitution_rule_remove", _apply_constitution_rule_remove)


# ============================================================================
# The gate
# ============================================================================

def promote(candidate: Dict[str, Any], *, simulate: bool = True) -> Dict[str, Any]:
    """Run the full Promotion chain and either apply the candidate to
    live state (on aligned pass) or refuse it (on veto / unknown kind /
    apply failure). A Ledger entry is written in every case.
    """
    if not isinstance(candidate, dict):
        raise ValueError("candidate must be a dict")
    candidate = dict(candidate)
    ts = time.time()

    # 1. Optional simulation.
    sim_result: Optional[Dict[str, Any]] = None
    if simulate:
        try:
            sim_result = _optimization.simulate_candidate(candidate)
        except Exception as exc:
            sim_result = {"kind": "simulation_error",
                          "reason": f"{type(exc).__name__}: {exc}"}

    # 2. Alignment chain — every registered Phase-1 validator runs.
    alignment = _evolution.run_alignment(candidate)

    # 3. Apply if aligned, otherwise refuse.
    apply_result: Optional[Dict[str, Any]] = None
    if alignment["decision"] != "pass":
        decision = "refused_by_validator"
    else:
        kind    = candidate.get("kind")
        applier = _appliers.get(str(kind or ""))
        if applier is None:
            decision     = "skipped_unknown_kind"
            apply_result = {"status": "skipped",
                            "reason": f"no applier registered for kind={kind!r}"}
        else:
            try:
                apply_result = applier(candidate)
            except Exception as exc:
                apply_result = {"status": "failed",
                                "reason": f"{type(exc).__name__}: {exc}"}
            status = (apply_result or {}).get("status")
            if   status == "applied": decision = "applied"
            elif status == "noop":    decision = "noop"
            else:                     decision = "apply_failed"

    # 4. Record the Why-chain to the Ledger so the operator (and future
    #    Self-Reflective Conscious agents) can replay the decision.
    led_count = len(_persistence.read_jsonl("ledger"))
    entry = {
        "id":               f"led_{led_count + 1}",
        "ts":               ts,
        "trigger":          {"topic": "core.evolution.promotion"},
        "candidate":        candidate,
        "simulation":       sim_result,
        "alignment":        alignment,
        "applied":          apply_result,
        "decision":         decision,
        "rationale":        candidate.get("rationale", ""),
        "expected_outcome": "promoted" if decision == "applied" else "refused",
        "actual_outcome":   decision,
        "promotion_id":     f"promo_{uuid.uuid4().hex[:12]}",
    }
    _persistence.append_jsonl("ledger", entry)

    return {
        "id":         entry["id"],
        "ts":         ts,
        "decision":   decision,
        "candidate":  candidate,
        "simulation": sim_result,
        "alignment":  alignment,
        "applied":    apply_result,
        "ledger":     entry,
    }
