"""Phase 5 — External integrations / A2A (M5.2).

Federation layer for inter-system collaboration with explicit trust
tiers, per the conceptual blueprint's Part V Federation:

  peer       — reads shared World-Model excerpts only.
  partner    — reads + writes shared excerpts.
  federated  — limited delegation under explicit scopes.

Every inbound federated message passes through the local Adversarial-
Input Filter; outbound shared excerpts pass through the Privacy gate.

State (under proactive.persistence.state_dir()):

  a2a_peers.json     — registered peer systems and their trust tier.
  a2a_inbox.jsonl    — append-only inbound message log (post-filter).
  a2a_outbox.jsonl   — append-only outbound send log.
  a2a_shared.jsonl   — append-only outbound state-excerpt log
                        (post-Privacy redaction).

Public API:

  Peers
    register_peer(peer_id, *, tier, name=None, contact=None) -> entry
    list_peers() -> list[entry]
    drop_peer(peer_id) -> bool

  Messaging
    receive(peer_id, message, *, kind="message") -> {accepted, …}
    send(peer_id, message, *, kind="message") -> {ok, sent, …}

  State sharing
    share_state(peer_id, namespaces) -> {excerpts, …}

  Inspection
    list_inbox(limit=50) -> list[message]
    list_outbox(limit=50) -> list[message]
    list_shared(limit=50) -> list[excerpt]

Design notes:

  - receive() runs every inbound payload through middleware.adversarial_gate;
    if injection_hits is non-empty, the message is recorded with a
    `quarantined: True` flag and the response is `{accepted: False,
    reason: "adversarial"}`. Per the §6 operational table.
  - send() is a stub for the actual transport — it logs to outbox and
    returns ok=True. A real implementation plugs in HTTP / SSE / etc.
    based on the peer's registered `transport`.
  - share_state() reads requested World Model namespaces, runs each
    excerpt through middleware.privacy_gate, logs the redacted
    excerpts, and returns them. Trust-tier gating: `peer` can only
    request public namespaces (those starting with `core.public.*`);
    `partner` can request any `core.*`; `federated` can request all.
"""

from __future__ import annotations

import time
import uuid
from typing import Any, Dict, List, Optional

from . import middleware  as _middleware
from . import persistence as _persistence


_PEERS_FILE  = "a2a_peers"      # → a2a_peers.json
_INBOX_FILE  = "a2a_inbox"      # → a2a_inbox.jsonl
_OUTBOX_FILE = "a2a_outbox"     # → a2a_outbox.jsonl
_SHARED_FILE = "a2a_shared"     # → a2a_shared.jsonl


# ============================================================================
# Trust tiers
# ============================================================================

TIER_PEER       = "peer"
TIER_PARTNER    = "partner"
TIER_FEDERATED  = "federated"

VALID_TIERS = {TIER_PEER, TIER_PARTNER, TIER_FEDERATED}

# Read-permission policy per tier. Returns True if the requesting tier
# may read the given World-Model namespace path.
_PUBLIC_PREFIX = "core.public."

def _can_read_namespace(tier: str, ns: str) -> bool:
    if tier == TIER_FEDERATED:
        return True
    if tier == TIER_PARTNER:
        return ns == "core" or ns.startswith("core.")
    if tier == TIER_PEER:
        return ns == "core.public" or ns.startswith(_PUBLIC_PREFIX)
    return False


# ============================================================================
# Peer registry
# ============================================================================

def register_peer(
    peer_id: str,
    *,
    tier: str,
    name:    Optional[str] = None,
    contact: Optional[str] = None,
) -> Dict[str, Any]:
    """Register or update a peer system. `tier` is one of peer / partner
    / federated. `contact` is freeform (URL, email, anything the
    operator needs to reach the peer)."""
    if not peer_id:
        raise ValueError("peer_id required")
    if tier not in VALID_TIERS:
        raise ValueError(f"tier must be one of {sorted(VALID_TIERS)}")
    peers = _persistence.read_json(_PEERS_FILE, default={})
    existing = peers.get(peer_id) or {}
    entry = {
        "peer_id":    peer_id,
        "tier":       tier,
        "name":       (name or existing.get("name") or peer_id),
        "contact":    (contact or existing.get("contact")),
        "created_at": existing.get("created_at", time.time()),
        "updated_at": time.time(),
    }
    peers[peer_id] = entry
    _persistence.write_json(_PEERS_FILE, peers)
    return entry


def list_peers() -> List[Dict[str, Any]]:
    peers = _persistence.read_json(_PEERS_FILE, default={})
    out = list(peers.values())
    out.sort(key=lambda p: p.get("updated_at", 0), reverse=True)
    return out


def get_peer(peer_id: str) -> Optional[Dict[str, Any]]:
    return _persistence.read_json(_PEERS_FILE, default={}).get(peer_id)


def drop_peer(peer_id: str) -> bool:
    peers = _persistence.read_json(_PEERS_FILE, default={})
    if peer_id not in peers:
        return False
    del peers[peer_id]
    _persistence.write_json(_PEERS_FILE, peers)
    return True


# ============================================================================
# Messaging
# ============================================================================

def receive(
    peer_id: str,
    message: Any,
    *,
    kind: str = "message",
) -> Dict[str, Any]:
    """Accept an inbound message from a peer. Runs through Adversarial
    filter; quarantines if injection markers detected.

    Returns `{accepted, message_id, peer_id, kind, injection_hits, ...}`.
    Records to a2a_inbox.jsonl in every case so the operator can see
    what was rejected."""
    peer = get_peer(peer_id)
    if peer is None:
        record = {
            "id":              f"a2a_{uuid.uuid4().hex[:12]}",
            "ts":              time.time(),
            "peer_id":         peer_id,
            "kind":            kind,
            "accepted":        False,
            "reason":          "unknown_peer",
            "injection_hits":  [],
        }
        _persistence.append_jsonl(_INBOX_FILE, record)
        return record

    env = _middleware.adversarial_gate({
        "source":  f"a2a:{peer_id}",
        "payload": message,
    })
    inj = (env.get("untrusted_content") or {}).get("injection_hits") or []

    record = {
        "id":              f"a2a_{uuid.uuid4().hex[:12]}",
        "ts":              time.time(),
        "peer_id":         peer_id,
        "peer_tier":       peer.get("tier"),
        "kind":            kind,
        "untrusted_content": env.get("untrusted_content"),
        "injection_hits":  inj,
        "accepted":        not inj,
        "reason":          "adversarial" if inj else "ok",
    }
    _persistence.append_jsonl(_INBOX_FILE, record)
    return record


def send(
    peer_id: str,
    message: Any,
    *,
    kind: str = "message",
) -> Dict[str, Any]:
    """Stub for the actual outbound transport. Logs to outbox and returns
    ok=True. Real implementation plugs in HTTP / SSE / etc.
    """
    peer = get_peer(peer_id)
    if peer is None:
        return {"ok": False, "reason": "unknown_peer", "peer_id": peer_id}

    record = {
        "id":      f"a2a_{uuid.uuid4().hex[:12]}",
        "ts":      time.time(),
        "peer_id": peer_id,
        "tier":    peer.get("tier"),
        "kind":    kind,
        "message": message,
        "ok":      True,
    }
    _persistence.append_jsonl(_OUTBOX_FILE, record)
    return record


# ============================================================================
# Shared World Model excerpts
# ============================================================================

def share_state(
    peer_id:    str,
    namespaces: List[str],
) -> Dict[str, Any]:
    """Read requested World Model namespaces, gate by trust tier, run
    each excerpt through the Privacy gate, log the redacted excerpts,
    and return them. Refused paths (tier doesn't permit) are listed
    in `refused`.
    """
    peer = get_peer(peer_id)
    if peer is None:
        return {"ok": False, "reason": "unknown_peer", "peer_id": peer_id,
                 "excerpts": {}, "refused": list(namespaces or [])}

    tier = peer.get("tier") or TIER_PEER
    wm   = _persistence.read_json("world_model", default={})

    excerpts: Dict[str, Any] = {}
    refused:  List[str]      = []
    for ns in (namespaces or []):
        if not _can_read_namespace(tier, ns):
            refused.append(ns)
            continue
        # Match exact path or prefix (anything under `ns.*`).
        slice_ = {k: v for k, v in wm.items() if k == ns or k.startswith(ns + ".")}
        if not slice_:
            slice_ = {ns: None}
        # Pass through Privacy gate as a synthetic envelope.
        env = _middleware.privacy_gate({"source": f"a2a:{peer_id}", "payload": slice_})
        excerpts[ns] = env.get("payload")

    record = {
        "id":         f"a2a_{uuid.uuid4().hex[:12]}",
        "ts":         time.time(),
        "peer_id":    peer_id,
        "tier":       tier,
        "namespaces": list(namespaces or []),
        "refused":    refused,
        "excerpts":   excerpts,
    }
    _persistence.append_jsonl(_SHARED_FILE, record)
    return {
        "ok":         True,
        "peer_id":    peer_id,
        "tier":       tier,
        "excerpts":   excerpts,
        "refused":    refused,
        "share_id":   record["id"],
    }


# ============================================================================
# Inspection
# ============================================================================

def list_inbox(limit: int = 50) -> List[Dict[str, Any]]:
    rows = _persistence.read_jsonl(_INBOX_FILE)
    return list(reversed(rows))[:max(1, min(500, int(limit)))]


def list_outbox(limit: int = 50) -> List[Dict[str, Any]]:
    rows = _persistence.read_jsonl(_OUTBOX_FILE)
    return list(reversed(rows))[:max(1, min(500, int(limit)))]


def list_shared(limit: int = 50) -> List[Dict[str, Any]]:
    rows = _persistence.read_jsonl(_SHARED_FILE)
    return list(reversed(rows))[:max(1, min(500, int(limit)))]
