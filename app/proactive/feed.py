"""User-facing feed — Phase 5 (M5.12).

Everything else in `proactive/` is the operator/engineer view: Ledger
lines, governor verdicts, scopes, confidence, Why-chains. This module
is the OTHER half — the translation layer that turns that machinery
into plain-language cards a normal user expects from a proactive
assistant:

    💡 "Weekly digest arrived — 5 stories."          (noticed / FYI)
    ❓ "Eve asked me to wire $5,000 — proceed?"       (asks / needs consent)
    ✅ "I added 'Design review, Thu 3pm' to reminders" (did / completed)

The feed merges two sources:

  1. Pending consents (`proactive.social.list_pending`) → `asks` cards.
     These need the user's decision, so they sort to the top.
  2. Recent Ledger entries (`ledger.jsonl`) → `did` / `noticed` cards.

A card is intentionally free of substrate vocabulary — no "scopes",
no "governor_verdict", no "confidence". The card's `actions` map to the
existing endpoints (consent approve/reject, motor undo, implicit
dismiss) so the feed is a pure presentation layer over what already
exists — no new persistence.

Public API:

    build_feed(*, limit=30, include_done=True) -> {cards, pending_count}

Card shape:

    {
      "id":       str,                 # consent id or ledger id
      "kind":     "asks"|"did"|"noticed",
      "icon":     str,                 # ❓ / ✅ / 💡
      "headline": str,                 # plain-language one-liner
      "detail":   str,                 # plain-language context / why
      "ts":       float,
      "source":   str | None,          # e.g. "eve@example.com", "timer"
      "status":   str | None,          # awaiting_user / executed / …
      "actions":  [ {label, action, consent_id?, action_id?} ],
    }
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from . import persistence as _persistence
from . import social      as _social


# ============================================================================
# Capability humanisation
# ============================================================================

# Map a capability name to (noun_phrase, did_phrase, ask_phrase). The feed
# never shows the raw `core.transfer_funds` string to the user.
_CAP_PHRASES: Dict[str, Dict[str, str]] = {
    "core.notify": {
        "noun": "a notification",
        "did":  "sent you a notification",
        "ask":  "send you a notification",
    },
    "core.send_email": {
        "noun": "an email",
        "did":  "sent an email",
        "ask":  "send an email",
    },
    "core.transfer_funds": {
        "noun": "a money transfer",
        "did":  "made a money transfer",
        "ask":  "make a money transfer",
    },
}


def _cap_phrases(capability: Optional[str]) -> Dict[str, str]:
    if capability and capability in _CAP_PHRASES:
        return _CAP_PHRASES[capability]
    # Reasonable defaults for unknown / bridged capabilities
    # (agent.*, transport.*, mcp.*, a2a.*).
    short = (capability or "an action").split(".")[-1].replace("_", " ")
    if capability and capability.startswith("agent."):
        return {"noun": "the assistant", "did": "used the assistant",  "ask": "ask the assistant"}
    if capability and capability.startswith("transport."):
        return {"noun": "an LLM",        "did": "queried an LLM",       "ask": "query an LLM"}
    if capability and capability.startswith("a2a."):
        return {"noun": "a peer",        "did": "contacted a peer",     "ask": "contact a peer"}
    return {"noun": short, "did": f"ran {short}", "ask": f"run {short}"}


def _humanise_amount(args: Any) -> str:
    """Pull a friendly amount/recipient string out of intent args, if any."""
    if not isinstance(args, dict):
        return ""
    bits: List[str] = []
    amount = args.get("amount")
    if amount is not None:
        try:
            bits.append(f"${float(amount):,.0f}")
        except (TypeError, ValueError):
            bits.append(str(amount))
    recipient = args.get("recipient") or args.get("to")
    if recipient:
        bits.append(f"to {recipient}")
    msg = args.get("message")
    if msg:
        bits.append(f"“{str(msg)[:80]}”")
    return " ".join(bits)


def _observation_source(entry: Dict[str, Any]) -> Optional[str]:
    obs = entry.get("observation") or {}
    if isinstance(obs, dict):
        return obs.get("sender") or obs.get("source")
    return entry.get("source")


def _observation_subject(entry: Dict[str, Any]) -> Optional[str]:
    obs = entry.get("observation") or {}
    if isinstance(obs, dict):
        return obs.get("subject") or obs.get("summary")
    return None


# ============================================================================
# Card builders
# ============================================================================

def _card_from_consent(rec: Dict[str, Any]) -> Dict[str, Any]:
    cap     = rec.get("capability")
    phrases = _cap_phrases(cap)
    intent  = rec.get("intent") or {}
    args    = intent.get("args") if isinstance(intent, dict) else None
    extra   = _humanise_amount(args)

    headline = f"Can I {phrases['ask']}?"
    if extra:
        headline = f"Can I {phrases['ask']} {extra}?"

    detail = str(rec.get("rationale") or "").strip()
    return {
        "id":       rec.get("id"),
        "kind":     "asks",
        "icon":     "❓",            # ❓
        "headline": headline,
        "detail":   detail,
        "ts":       rec.get("requested_at"),
        "source":   None,
        "status":   rec.get("status"),
        "actions":  [
            {"label": "Approve", "action": "approve", "consent_id": rec.get("id")},
            {"label": "Dismiss", "action": "reject",  "consent_id": rec.get("id")},
        ],
    }


def _card_from_ledger(entry: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    topic = (entry.get("trigger") or {}).get("topic", "")
    eid   = entry.get("id")
    ts    = entry.get("ts")

    # --- Completed actions (Motor executed) → "did" cards ----------------
    motor_status = entry.get("motor_status")
    intent       = entry.get("intent") or {}
    cap          = (intent.get("capability") if isinstance(intent, dict) else None)

    if topic == "core.motor.action_attempt" and motor_status == "executed" and cap:
        phrases = _cap_phrases(cap)
        args    = intent.get("args") if isinstance(intent, dict) else None
        extra   = _humanise_amount(args)
        headline = f"I {phrases['did']}"
        if extra:
            headline = f"I {phrases['did']} {extra}"
        action_id = (entry.get("motor_action") or {}).get("id")
        actions = [{"label": "OK", "action": "ok"}]
        # Only money / outbound things get an Undo affordance.
        if cap in ("core.transfer_funds", "core.send_email"):
            actions = [{"label": "Undo", "action": "undo", "action_id": action_id,
                        "capability": cap},
                       {"label": "OK",   "action": "ok"}]
        return {
            "id":       eid,
            "kind":     "did",
            "icon":     "✅",        # ✅
            "headline": headline,
            "detail":   str(intent.get("rationale") or "").strip(),
            "ts":       ts,
            "source":   _observation_source(entry),
            "status":   "executed",
            "actions":  actions,
        }

    # --- Consent decisions already made → quiet "did" cards --------------
    if topic in ("core.social.consent_approved", "core.social.consent_rejected"):
        consent = entry.get("consent") or {}
        decided = "approved" if topic.endswith("approved") else "dismissed"
        phrases = _cap_phrases(consent.get("capability"))
        return {
            "id":       eid,
            "kind":     "did",
            "icon":     "✅" if decided == "approved" else "✖",
            "headline": f"You {decided}: {phrases['ask']}",
            "detail":   str(consent.get("note") or "").strip(),
            "ts":       ts,
            "source":   consent.get("operator"),
            "status":   decided,
            "actions":  [{"label": "OK", "action": "ok"}],
        }

    # --- Observations the system recorded but took no action → "noticed" -
    if topic == "core.sensory.observation":
        subject = _observation_subject(entry)
        if not subject:
            return None
        return {
            "id":       eid,
            "kind":     "noticed",
            "icon":     "\U0001f4a1",    # 💡
            "headline": f"I noticed: {subject}",
            "detail":   "",
            "ts":       ts,
            "source":   _observation_source(entry),
            "status":   "noted",
            "actions":  [
                {"label": "Show me", "action": "show"},
                {"label": "Dismiss", "action": "dismiss"},
            ],
        }

    return None


# ============================================================================
# Feed assembly
# ============================================================================

def build_feed(*, limit: int = 30, include_done: bool = True) -> Dict[str, Any]:
    """Build the user-facing card feed. Pending consents (asks) always
    come first because they need a decision; the rest are time-sorted
    newest-first. `include_done=False` drops the already-completed
    `did` cards (used by the 'just show me what needs me' view)."""
    limit = max(1, min(200, int(limit)))

    # 1. Pending consents → asks (top priority).
    asks = [_card_from_consent(r) for r in _social.list_pending(status=_social.STATUS_AWAITING)]
    asks.sort(key=lambda c: c.get("ts") or 0.0, reverse=True)

    # 2. Ledger → did / noticed.
    others: List[Dict[str, Any]] = []
    seen_ids = set()
    ledger = _persistence.read_jsonl("ledger")
    for entry in reversed(ledger):           # newest first
        card = _card_from_ledger(entry)
        if not card:
            continue
        if card["id"] in seen_ids:
            continue
        if not include_done and card["kind"] == "did":
            continue
        seen_ids.add(card["id"])
        others.append(card)
        if len(others) >= limit:
            break

    cards = asks + others
    return {
        "cards":         cards[:limit + len(asks)],
        "pending_count": len(asks),
    }
