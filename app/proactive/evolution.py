"""Phase 4 — Evolution / Alignment (M4.1).

Phase-1 Alignment is the always-on, online side of Evolution per §11 of
the conceptual blueprint. It captures user signals, maintains the User
Constitution, and runs a chain of validators over any candidate change
before it can flow to production. Validators are pluggable; each can
independently veto a Phase-2 output.

Storage (under proactive.persistence.state_dir()):

  alignment_signals.jsonl   — append-only log of feedback events
  user_constitution.json    — current preferences + standing rules

Public API:

  Feedback signals
  ----------------
  KIND_THUMBS, KIND_EDIT, KIND_PREFERENCE — valid `kind` values
  record_feedback(target_id, kind, value, context) -> entry
  list_feedback(since=None, kind=None, limit=100) -> list[entry]

  User Constitution
  -----------------
  read_constitution() -> dict
  update_constitution(patch) -> dict

  Validator chain
  ---------------
  Verdict — dataclass: decision in {"pass", "veto"}, reason, by
  register_validator(name, fn)
  unregister_validator(name) -> bool
  list_validators() -> list[str]
  run_alignment(candidate) -> dict   # aggregate verdict + per-validator trail
"""

from __future__ import annotations

import time
import uuid
from dataclasses import asdict, dataclass
from typing import Any, Callable, Dict, List, Optional

from .persistence import append_jsonl, read_json, read_jsonl, write_json


_SIGNALS_FILE      = "alignment_signals"   # → alignment_signals.jsonl
_CONSTITUTION_FILE = "user_constitution"   # → user_constitution.json


# ============================================================================
# Feedback signals
# ============================================================================

KIND_THUMBS          = "thumbs"            # user voted up/down on a Ledger entry
KIND_EDIT            = "edit"              # user modified a proposed intent before accepting
KIND_PREFERENCE      = "preference"        # user explicitly stated a preference
KIND_IMPLICIT_ACCEPT = "implicit_accept"   # user-action implies endorsement (consent approved, action allowed to stand)
KIND_IMPLICIT_REJECT = "implicit_reject"   # user-action implies rejection (consent rejected, action undone, notification dismissed)

VALID_KINDS = {
    KIND_THUMBS, KIND_EDIT, KIND_PREFERENCE,
    KIND_IMPLICIT_ACCEPT, KIND_IMPLICIT_REJECT,
}

# Operator-action signal vocabulary. Each maps to one of the implicit
# kinds above; the `signal` is preserved on the entry's `value` so the
# proposer / validators can tell *what kind* of implicit signal it was
# (a quick approval is weaker evidence than a manual undo, etc.).
_IMPLICIT_REJECT_SIGNALS = {
    "consent_rejected",         # operator rejected a Social-emitted consent request
    "action_undone",            # operator manually reversed a Motor action
    "notification_dismissed",   # operator dismissed a notify without engaging
    "agent_output_discarded",   # operator threw away an agent_flow draft
}
_IMPLICIT_ACCEPT_SIGNALS = {
    "consent_approved",         # operator approved a Social-emitted consent request
    "action_let_stand",         # operator saw the Motor action and didn't undo it within the grace window
    "notification_engaged",     # operator clicked through / acted on a notify
    "agent_output_accepted",    # operator used an agent_flow draft as-is
}


def record_implicit_signal(
    target_id: str,
    signal:    str,
    *,
    context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Append an implicit feedback signal to the alignment log.

    Implicit signals are derived from operator actions on the running
    system rather than from explicit thumbs / edits. The `signal` value
    is one of the controlled vocabulary in `_IMPLICIT_*_SIGNALS` and is
    used to decide whether the entry is recorded as an `implicit_accept`
    or `implicit_reject`.

    The optimization strategies and the `recent_thumbs_down` validator
    weight implicit signals lower than explicit ones (noisier — an
    operator dismissing a notification doesn't necessarily mean "I hate
    this kind of notification") but they still count.
    """
    if signal in _IMPLICIT_REJECT_SIGNALS:
        kind = KIND_IMPLICIT_REJECT
    elif signal in _IMPLICIT_ACCEPT_SIGNALS:
        kind = KIND_IMPLICIT_ACCEPT
    else:
        raise ValueError(
            f"unknown implicit signal {signal!r}; expected one of "
            f"{sorted(_IMPLICIT_REJECT_SIGNALS | _IMPLICIT_ACCEPT_SIGNALS)}"
        )
    return record_feedback(target_id, kind, value=signal, context=context)


def record_feedback(
    target_id: str,
    kind: str,
    value: Any,
    context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Append a feedback signal to the alignment log.

    target_id  — usually a Ledger entry id; can also be a capability name
                 or a goal id depending on what the user is reacting to.
    kind       — one of KIND_THUMBS / KIND_EDIT / KIND_PREFERENCE.
    value      — kind-specific: 'up' / 'down' for thumbs, the edited
                 dict for edit, an arbitrary {key: value} for preference.
    context    — optional structured context (capability, scope, etc.)
                 — used by built-in validators to scope their checks.
    """
    if kind not in VALID_KINDS:
        raise ValueError(f"unknown feedback kind: {kind!r}")
    entry = {
        "id":        f"sig_{uuid.uuid4().hex[:12]}",
        "ts":        time.time(),
        "target_id": str(target_id or ""),
        "kind":      kind,
        "value":     value,
        "context":   context or {},
    }
    append_jsonl(_SIGNALS_FILE, entry)
    return entry


def list_feedback(
    since: Optional[float] = None,
    kind:  Optional[str]   = None,
    limit: int             = 100,
) -> List[Dict[str, Any]]:
    """Return recent feedback signals, most-recent first."""
    sigs = read_jsonl(_SIGNALS_FILE)
    if since is not None:
        sigs = [s for s in sigs if s.get("ts", 0) >= since]
    if kind:
        sigs = [s for s in sigs if s.get("kind") == kind]
    return list(reversed(sigs))[:max(1, min(1000, int(limit)))]


# ============================================================================
# User Constitution — preference vectoring
# ============================================================================

def _empty_constitution() -> Dict[str, Any]:
    return {
        "version":     1,
        "created_at":  time.time(),
        "updated_at":  time.time(),
        "rules":       [],   # list of {id, kind, target, ...}
        "preferences": {},   # arbitrary key/value map
    }


def read_constitution() -> Dict[str, Any]:
    """Return the User Constitution; lazy-create with defaults if missing."""
    cur = read_json(_CONSTITUTION_FILE, default=None)
    if not cur or not isinstance(cur, dict):
        cur = _empty_constitution()
        write_json(_CONSTITUTION_FILE, cur)
    return cur


def remove_rule(
    rule_id: Optional[str]            = None,
    match:   Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Remove rules from the constitution by id or by kind+target match.

    `rule_id` removes exactly the rule with that id.
    `match` removes every rule whose `kind` and `target` both equal those
    in `match`. Either or both may be supplied; both filters are OR'd.

    Returns `{removed: [rule, ...], version, updated}`. Never raises if a
    rule isn't present — callers can treat absence as a no-op.
    """
    cur = read_constitution()
    rules = list(cur.get("rules") or [])
    keep:    List[Dict[str, Any]] = []
    removed: List[Dict[str, Any]] = []

    def _hits(rule: Dict[str, Any]) -> bool:
        if rule_id and rule.get("id") == rule_id:
            return True
        if match and isinstance(match, dict):
            if rule.get("kind")   == match.get("kind") \
               and rule.get("target") == match.get("target"):
                return True
        return False

    for rule in rules:
        if isinstance(rule, dict) and _hits(rule):
            removed.append(rule)
        else:
            keep.append(rule)

    if removed:
        cur["rules"]      = keep
        cur["version"]    = int(cur.get("version", 1)) + 1
        cur["updated_at"] = time.time()
        write_json(_CONSTITUTION_FILE, cur)

    return {
        "removed": removed,
        "version": cur.get("version"),
        "updated": bool(removed),
    }


def update_constitution(patch: Dict[str, Any]) -> Dict[str, Any]:
    """Apply a shallow patch to the constitution.

      - `preferences` is merged key-by-key.
      - `rules` is APPENDED (use a separate replace_rules if you need to
        prune; alignment intentionally keeps history).
      - other top-level keys are replaced.

    Bumps `version` and `updated_at`. Returns the new constitution.
    """
    if not isinstance(patch, dict):
        raise ValueError("constitution patch must be a dict")

    cur = read_constitution()
    if "preferences" in patch and isinstance(patch["preferences"], dict):
        cur.setdefault("preferences", {}).update(patch["preferences"])
    if "rules" in patch and isinstance(patch["rules"], list):
        existing_ids = {r.get("id") for r in (cur.get("rules") or [])}
        for rule in patch["rules"]:
            if not isinstance(rule, dict):
                continue
            rule = dict(rule)
            rule.setdefault("id", f"rule_{uuid.uuid4().hex[:8]}")
            if rule["id"] in existing_ids:
                continue
            rule.setdefault("created_at", time.time())
            cur.setdefault("rules", []).append(rule)
            existing_ids.add(rule["id"])

    for k, v in patch.items():
        if k in ("preferences", "rules", "version", "created_at", "updated_at"):
            continue
        cur[k] = v

    cur["version"]    = int(cur.get("version", 0)) + 1
    cur["updated_at"] = time.time()
    write_json(_CONSTITUTION_FILE, cur)
    return cur


# ============================================================================
# Validator chain
# ============================================================================

@dataclass
class Verdict:
    """A single validator's response to a candidate change."""
    decision: str   # "pass" | "veto"
    reason:   str
    by:       str   # validator name

    def is_pass(self) -> bool:
        return self.decision == "pass"


_validators: Dict[str, Callable[[Dict[str, Any]], Verdict]] = {}


def register_validator(name: str, fn: Callable[[Dict[str, Any]], Verdict]) -> None:
    """Register an Alignment validator.

    `fn(candidate)` should return a `Verdict`. `candidate` is a dict:
        {kind, target, payload, rationale, ...}
    """
    if not name or not callable(fn):
        raise ValueError("register_validator needs a non-empty name and a callable")
    _validators[name] = fn


def unregister_validator(name: str) -> bool:
    return _validators.pop(name, None) is not None


def list_validators() -> List[str]:
    return sorted(_validators.keys())


def run_alignment(candidate: Dict[str, Any]) -> Dict[str, Any]:
    """Run every registered validator over the candidate.

    Aggregate decision: "pass" iff every validator passed; otherwise "veto".
    Returns the full per-validator verdict trail so the operator can see
    which validator objected and why.
    """
    if not isinstance(candidate, dict):
        candidate = {"raw": candidate}

    verdicts: List[Verdict] = []
    for name in sorted(_validators.keys()):
        fn = _validators[name]
        try:
            v = fn(candidate)
        except Exception as exc:
            v = Verdict(decision="veto",
                        reason=f"validator raised: {type(exc).__name__}: {exc}",
                        by=name)
        if not isinstance(v, Verdict):
            v = Verdict(decision="veto",
                        reason=f"validator returned {type(v).__name__}, expected Verdict",
                        by=name)
        verdicts.append(v)

    decision = "pass" if all(v.is_pass() for v in verdicts) else "veto"
    return {
        "decision":  decision,
        "verdicts":  [asdict(v) for v in verdicts],
        "ts":        time.time(),
        "candidate": candidate,
    }


# ============================================================================
# Built-in validators
# ============================================================================

def _candidate_capability(candidate: Dict[str, Any]) -> Optional[str]:
    payload = candidate.get("payload") or {}
    if isinstance(payload, dict):
        cap = payload.get("capability") or payload.get("name")
        if isinstance(cap, str) and cap:
            return cap
    target = candidate.get("target")
    if isinstance(target, str) and target:
        return target
    return None


def _validator_recent_thumbs_down(candidate: Dict[str, Any]) -> Verdict:
    """Veto if the candidate's capability has accumulated recent negative
    user signal — explicit thumbs-down or implicit rejections.

    Skipped for `constitution_rule_add` candidates — banning a capability
    *aligns* with thumbs-down signal rather than contradicting it.
    Still applied to `constitution_rule_remove` (un-banning a downvoted
    capability would override the user signal) and to actuation kinds.

    Weighting: each explicit thumbs-down counts 1.0; each implicit
    rejection counts 0.5 (noisier — operator dismissing a single
    notification isn't as strong as them explicitly thumbs-downing it).
    Veto fires at >= 3.0 weighted negative signals.
    """
    if str(candidate.get("kind") or "") == "constitution_rule_add":
        return Verdict("pass",
                       "constitution_rule_add aligns with thumbs-down — not subject",
                       "recent_thumbs_down")
    cap = _candidate_capability(candidate)
    if not cap:
        return Verdict("pass", "no capability to check", "recent_thumbs_down")

    sigs = read_jsonl(_SIGNALS_FILE)
    explicit = sum(
        1 for s in sigs
        if s.get("kind") == KIND_THUMBS
        and s.get("value") == "down"
        and (s.get("context") or {}).get("capability") == cap
    )
    implicit = sum(
        1 for s in sigs
        if s.get("kind") == KIND_IMPLICIT_REJECT
        and (s.get("context") or {}).get("capability") == cap
    )
    weighted = float(explicit) + 0.5 * float(implicit)
    if weighted >= 3.0:
        return Verdict("veto",
                       f"{explicit} thumbs-down + {implicit} implicit rejections on '{cap}' "
                       f"(weighted={weighted:.1f})",
                       "recent_thumbs_down")
    return Verdict("pass",
                   f"weighted negative signal {weighted:.1f} below threshold",
                   "recent_thumbs_down")


def _validator_constitution_check(candidate: Dict[str, Any]) -> Verdict:
    """Veto if the candidate would invoke a capability banned by a
    User Constitution rule.

    Skipped for governance kinds (`constitution_rule_add` /
    `constitution_rule_remove`) — those candidates change the rules
    themselves rather than invoking any capability, so checking them
    against the rules they're managing produces a self-loop.

    Rule schema honored here:
        {id, kind: 'never', target: <capability name>, ...}
    """
    kind = str(candidate.get("kind") or "")
    if kind.startswith("constitution_rule_"):
        return Verdict("pass",
                       "governance action — manages rules rather than invoking a capability",
                       "constitution_check")
    cap = _candidate_capability(candidate)
    constitution = read_constitution()
    for rule in constitution.get("rules") or []:
        if not isinstance(rule, dict):
            continue
        if rule.get("kind") != "never":
            continue
        target = rule.get("target")
        if cap and target == cap:
            return Verdict(
                "veto",
                f"User Constitution rule {rule.get('id')!r} bans capability '{cap}'",
                "constitution_check",
            )
    return Verdict("pass", "no constitutional conflicts", "constitution_check")


# Auto-register built-ins on import.
register_validator("recent_thumbs_down", _validator_recent_thumbs_down)
register_validator("constitution_check", _validator_constitution_check)
