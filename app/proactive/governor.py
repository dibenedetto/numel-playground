"""Substrate §3.5 — Governor decision module (M5.11).

Promoted from inline logic in `WFGovernorDecideFlow.execute()` to a
dedicated module per the technical-spec note. Same decision contract,
same defaults; future budget enforcement / attention throttling will
live here next to the existing scope-policy decision.

Public API:

    gate(envelope, *, high_stake_scopes=None, write_scopes=None,
                       write_confidence_threshold=0.85) -> envelope

    decide(scopes, confidence, *, high_stake_scopes=None,
                                   write_scopes=None,
                                   write_confidence_threshold=0.85)
        -> {"decision", "reason"}

`gate` mutates the envelope (sets `governor_verdict`) and returns it,
matching the rest of `proactive.middleware`'s in/out convention.
`decide` is the pure-logic kernel — useful when the caller wants the
verdict without the envelope wrapping.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple


DEFAULT_HIGH_STAKE_SCOPES: List[str] = ["spends-money", "impersonates-user", "affects-third-party"]
DEFAULT_WRITE_SCOPES:       List[str] = ["write"]
DEFAULT_WRITE_CONF_THRESHOLD: float    = 0.85


def decide(
    scopes:                     List[str],
    confidence:                 float,
    *,
    high_stake_scopes:          Optional[List[str]] = None,
    write_scopes:               Optional[List[str]] = None,
    write_confidence_threshold: float = DEFAULT_WRITE_CONF_THRESHOLD,
) -> Tuple[str, str]:
    """Pure decision logic — returns (decision, reason).

    `decision` is one of `"allow"`, `"consent_required"`. (`"refuse"` is
    reserved for future constitution-driven blocks; today the alignment
    chain handles refusals upstream.)"""
    hs = set(high_stake_scopes if high_stake_scopes is not None else DEFAULT_HIGH_STAKE_SCOPES)
    ws = set(write_scopes      if write_scopes      is not None else DEFAULT_WRITE_SCOPES)
    has_high  = any(s in hs for s in (scopes or []))
    has_write = any(s in ws for s in (scopes or []))

    if has_high:
        return "consent_required", "high-stake scope present"
    if has_write and float(confidence) < float(write_confidence_threshold):
        return "consent_required", "write at low confidence"
    return "allow", "low-class action"


def gate(
    envelope:                   Dict[str, Any],
    *,
    high_stake_scopes:          Optional[List[str]] = None,
    write_scopes:               Optional[List[str]] = None,
    write_confidence_threshold: float = DEFAULT_WRITE_CONF_THRESHOLD,
) -> Dict[str, Any]:
    """Run the Governor over the envelope's `scopes` + `confidence`. Sets
    `envelope["governor_verdict"] = {decision, reason, scopes, confidence}`
    and returns the same envelope (mutated in place, matching the
    middleware gates' convention). Tolerates non-dict envelopes by
    wrapping them as `{"raw": value}`."""
    env = dict(envelope) if isinstance(envelope, dict) else {"raw": envelope}
    scopes = list(env.get("scopes", ["read-only"]))
    try:
        conf = float(env.get("confidence", 1.0))
    except (TypeError, ValueError):
        conf = 1.0
    decision, reason = decide(
        scopes, conf,
        high_stake_scopes          = high_stake_scopes,
        write_scopes               = write_scopes,
        write_confidence_threshold = write_confidence_threshold,
    )
    env["governor_verdict"] = {
        "decision":   decision,
        "reason":     reason,
        "scopes":     scopes,
        "confidence": conf,
    }
    return env
