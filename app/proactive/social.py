"""Substrate §4 Social — consent lifecycle (M5.11).

Until now the Social layer's `social_consent_flow` only *recorded*
pending-consent requests into the workflow's in-memory
`variables["pending_consents"]` — there was no operator-facing
approve/reject path. The technical spec §6.1 flagged this:
"Approval is not yet wired — the `awaiting_user` records sit until
cleaned up."

M5.11 wires it. Two storage surfaces work together:

  - workflow-local: `variables["pending_consents"]` (unchanged) for the
                    workflow's own bookkeeping during the run
  - durable:        `pending_consents.json` under `state_dir()` so the
                    operator can list / approve / reject between runs
                    and across processes

The Social flow node mirrors each record to the durable store on emit.
Approval / rejection updates the durable store + appends a Ledger
entry + records the matching implicit-feedback signal so the
Optimization sandbox learns from it.

Public API:

    list_pending(*, status=None)                       -> list[record]
    record_pending(record)                             -> record
    approve(consent_id, *, operator=None, note=None)   -> record
    reject(consent_id, *, operator=None, note=None)    -> record
    get(consent_id)                                    -> record | None

Record shape:

    {
      "id":              "consent_<n>",
      "capability":      str,
      "rationale":       str,
      "correlation_id":  str | None,
      "requested_at":    float,
      "status":          "awaiting_user" | "approved" | "rejected",
      "decided_at":      float | None,
      "operator":        str | None,
      "note":            str | None,
      "intent":          dict | None,   # carried over from the original envelope
    }
"""

from __future__ import annotations

import time
import uuid
from typing import Any, Dict, List, Optional

from . import evolution    as _evolution
from . import persistence  as _persistence


_PENDING_FILE = "pending_consents"   # → pending_consents.json

STATUS_AWAITING = "awaiting_user"
STATUS_APPROVED = "approved"
STATUS_REJECTED = "rejected"


# ============================================================================
# Storage
# ============================================================================

def _read_all() -> Dict[str, Dict[str, Any]]:
    data = _persistence.read_json(_PENDING_FILE, default={})
    return data if isinstance(data, dict) else {}


def _write_all(data: Dict[str, Dict[str, Any]]) -> None:
    _persistence.write_json(_PENDING_FILE, data)


def get(consent_id: str) -> Optional[Dict[str, Any]]:
    if not consent_id:
        return None
    return _read_all().get(consent_id)


def list_pending(*, status: Optional[str] = None) -> List[Dict[str, Any]]:
    """Return all consent records, optionally filtered by status.
    Most-recently-requested first."""
    rows = list(_read_all().values())
    if status:
        rows = [r for r in rows if r.get("status") == status]
    rows.sort(key=lambda r: r.get("requested_at") or 0.0, reverse=True)
    return rows


def record_pending(record: Dict[str, Any]) -> Dict[str, Any]:
    """Persist a `social_consent_request` record to the durable store. If
    no `id` is supplied a fresh one is minted. Idempotent on `id` — an
    existing record at that id is overwritten (the Social flow node may
    re-record on workflow re-entry, which is fine)."""
    if not isinstance(record, dict):
        raise ValueError("record must be a dict")
    record = dict(record)
    if not record.get("id"):
        record["id"] = f"consent_{uuid.uuid4().hex[:12]}"
    record.setdefault("status",       STATUS_AWAITING)
    record.setdefault("requested_at", time.time())
    data = _read_all()
    data[record["id"]] = record
    _write_all(data)
    return record


# ============================================================================
# Operator decisions
# ============================================================================

def _audit_ledger_append(topic: str, record: Dict[str, Any]) -> None:
    """Append a Ledger entry for the decision so the Why-chain stays
    complete. We don't fail the decision if Ledger append fails — the
    operator's intent is what matters for the consent state."""
    try:
        ledger = _persistence.read_jsonl("ledger")
        next_id = f"led_{len(ledger) + 1}"
        _persistence.append_jsonl("ledger", {
            "id":             next_id,
            "ts":             time.time(),
            "correlation_id": record.get("correlation_id"),
            "trigger":        {"topic": topic},
            "consent":        {
                "id":         record.get("id"),
                "capability": record.get("capability"),
                "status":     record.get("status"),
                "operator":   record.get("operator"),
                "note":       record.get("note"),
            },
            "expected_outcome": "consent_decision_recorded",
            "actual_outcome":   record.get("status"),
        })
    except Exception:
        pass


def _record_implicit_feedback(record: Dict[str, Any], signal: str) -> None:
    """Mirror the operator decision into the alignment_signals log so the
    Optimization sandbox learns from each approval / rejection."""
    try:
        cap = record.get("capability")
        _evolution.record_implicit_signal(
            target_id = record.get("id") or "",
            signal    = signal,
            context   = {"capability": cap} if cap else None,
        )
    except Exception:
        pass


def _decide(
    consent_id: str,
    *,
    new_status: str,
    operator:   Optional[str],
    note:       Optional[str],
) -> tuple:
    """Internal — returns `(record, changed)`. `changed` is False when the
    record was already decided (idempotent re-call), so callers can skip
    emitting a duplicate audit entry."""
    data = _read_all()
    record = data.get(consent_id)
    if not record:
        raise KeyError(f"unknown consent_id: {consent_id!r}")
    if record.get("status") in (STATUS_APPROVED, STATUS_REJECTED):
        return record, False
    record["status"]     = new_status
    record["decided_at"] = time.time()
    record["operator"]   = operator
    record["note"]       = note
    data[consent_id]     = record
    _write_all(data)
    return record, True


def approve(
    consent_id: str,
    *,
    operator: Optional[str] = None,
    note:     Optional[str] = None,
) -> Dict[str, Any]:
    """Mark a pending consent as approved. Side-effects on a *real* state
    change: a Ledger entry with topic `core.social.consent_approved`,
    an `implicit_accept` feedback signal so Optimization learns the
    operator is happy with this capability+intent. Idempotent re-calls
    return the existing record without re-emitting side-effects."""
    record, changed = _decide(consent_id, new_status=STATUS_APPROVED, operator=operator, note=note)
    if changed:
        _audit_ledger_append("core.social.consent_approved", record)
        _record_implicit_feedback(record, "consent_approved")
    return record


def reject(
    consent_id: str,
    *,
    operator: Optional[str] = None,
    note:     Optional[str] = None,
) -> Dict[str, Any]:
    """Mark a pending consent as rejected. Same idempotency semantics as
    `approve`. On a real state change: Ledger entry with topic
    `core.social.consent_rejected`, `implicit_reject` feedback signal."""
    record, changed = _decide(consent_id, new_status=STATUS_REJECTED, operator=operator, note=note)
    if changed:
        _audit_ledger_append("core.social.consent_rejected", record)
        _record_implicit_feedback(record, "consent_rejected")
    return record
