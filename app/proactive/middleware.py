"""Substrate Middleware — Phase 3 (M3.2).

Three gates that every signal entering or leaving an agent passes through.
Workflow `transform_flow` scripts call these functions; the functions are
pure (input dict → new dict) so they're trivially testable in isolation.

  - Veracity Gate    — provenance + heuristic confidence scoring.
                       Source-trust table + scan for social-engineering
                       red flags (act now, wire transfer, verify account, …).
  - Privacy Gate     — PII / secret redaction with a per-call policy
                       (email, SSN, card, phone, IBAN, JWT, common API keys).
                       Reports counts per redaction kind.
  - Adversarial Gate — wraps payload in a typed `untrusted_content` envelope
                       and scans for prompt-injection markers (ignore-previous,
                       chat-template tokens, system-prompt hijacks). Drops
                       confidence when injection is detected.

These remain heuristics — Phase 6 will swap in LLM-backed scorers — but
they're solid enough to be load-bearing in the substrate today.
"""

from __future__ import annotations

import re
import time
import uuid
from typing import Any, Dict, List, Optional


# ============================================================================
# Veracity Gate
# ============================================================================

# Per-source trust priors. Real implementation should learn these from the
# Ledger over time (per §11 Phase 1 Implicit Behavioral Analysis).
_SOURCE_TRUST: Dict[str, float] = {
    "user":     0.95,
    "internal": 0.95,
    "sensor":   0.85,
    "webhook":  0.70,
    "channel":  0.60,
    "rss":      0.55,
    "email":    0.50,
    "default":  0.60,
}

# Phrases that lower confidence — common social-engineering / spam markers.
_SUSPICION_PATTERNS: List[re.Pattern] = [
    re.compile(r"\bact (?:now|today|immediately|asap|urgently)\b", re.I),
    re.compile(r"\b(?:wire transfer|wire (?:funds?|money)|transfer funds?)\b", re.I),
    re.compile(r"\bclick (?:here|this link)\b", re.I),
    re.compile(r"\bverify (?:your )?(?:account|password|credentials?)\b", re.I),
    re.compile(r"\bone[- ]time (?:code|password|pin)\b", re.I),
    re.compile(r"\b(?:IRS|tax debt)\b", re.I),
    re.compile(r"\burgent\b.{0,30}\b(?:request|action|matter)\b", re.I),
]


def veracity_gate(envelope: Dict[str, Any]) -> Dict[str, Any]:
    """Annotate the envelope with provenance and a heuristic confidence score."""
    env = dict(envelope) if isinstance(envelope, dict) else {"raw": envelope}
    env.setdefault("correlation_id", f"corr_{uuid.uuid4().hex[:12]}")

    source_kind = _classify_source(env.get("source"))
    base_trust  = _SOURCE_TRUST.get(source_kind, _SOURCE_TRUST["default"])

    suspicion_hits    = _scan_suspicious_text(env)
    suspicion_penalty = min(0.40, 0.10 * len(suspicion_hits))

    explicit  = env.get("confidence")
    starting  = float(explicit) if explicit is not None else base_trust
    final     = max(0.0, min(1.0, starting - suspicion_penalty))

    env["confidence"] = final
    env.setdefault("scopes", env.get("scopes", ["read-only"]))
    env.setdefault("provenance", []).append({
        "stage":             "veracity",
        "source":            env.get("source"),
        "source_kind":       source_kind,
        "base_trust":        base_trust,
        "suspicion_hits":    suspicion_hits,
        "suspicion_penalty": suspicion_penalty,
        "ts":                time.time(),
    })
    return env


def _classify_source(source: Any) -> str:
    s = str(source or "").strip().lower()
    if not s:
        return "default"
    if ":" in s:
        s = s.split(":", 1)[0]
    if s in _SOURCE_TRUST:
        return s
    if "email"   in s: return "email"
    if "user"    in s: return "user"
    if "sensor"  in s: return "sensor"
    if "channel" in s: return "channel"
    if "webhook" in s: return "webhook"
    return "default"


def _walk_strings(value: Any):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for v in value.values():
            yield from _walk_strings(v)
    elif isinstance(value, list):
        for v in value:
            yield from _walk_strings(v)


def _scan_suspicious_text(env: Dict[str, Any]) -> List[str]:
    hits: List[str] = []
    for value in _walk_strings(env):
        for pat in _SUSPICION_PATTERNS:
            if pat.search(value):
                hits.append(pat.pattern)
                break
    return hits


# ============================================================================
# Privacy / Redaction Gate
# ============================================================================

_DEFAULT_POLICY: Dict[str, bool] = {
    "redact_email":   True,
    "redact_ssn":     True,
    "redact_card":    True,
    "redact_phone":   True,
    "redact_iban":    True,
    "redact_jwt":     True,
    "redact_api_key": True,
}

_PRIVACY_PATTERNS: List[tuple] = [
    ("email",   re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"),                                 "[email]"),
    ("ssn",     re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),                                        "[ssn]"),
    ("card",    re.compile(r"\b(?:\d[ -]*?){13,19}\b"),                                       "[card]"),
    ("phone",   re.compile(r"\+?\d{1,3}[\s.-]?\(?\d{2,4}\)?[\s.-]?\d{3,4}[\s.-]?\d{3,4}\b"), "[phone]"),
    ("iban",    re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{10,30}\b"),                              "[iban]"),
    ("jwt",     re.compile(r"\beyJ[\w-]+\.[\w-]+\.[\w-]+\b"),                                "[jwt]"),
    ("api_key", re.compile(r"\b(?:sk|pk|ghp|github_pat)[_-][\w-]{16,}\b"),                   "[api_key]"),
]


def privacy_gate(
    envelope: Dict[str, Any],
    policy: Optional[Dict[str, bool]] = None,
) -> Dict[str, Any]:
    """Redact PII/secrets in payload-like fields per the active policy."""
    env    = dict(envelope) if isinstance(envelope, dict) else {"raw": envelope}
    pol    = {**_DEFAULT_POLICY, **(policy or {})}
    counts: Dict[str, int] = {}

    def _redact_str(text: str) -> str:
        if not isinstance(text, str):
            return text
        for kind, pat, repl in _PRIVACY_PATTERNS:
            if not pol.get(f"redact_{kind}", True):
                continue
            def _hit(_m, _kind=kind, _repl=repl):
                counts[_kind] = counts.get(_kind, 0) + 1
                return _repl
            text = pat.sub(_hit, text)
        return text

    def _walk(v):
        if isinstance(v, str):  return _redact_str(v)
        if isinstance(v, list): return [_walk(x) for x in v]
        if isinstance(v, dict): return {k: _walk(x) for k, x in v.items()}
        return v

    for key in ("payload", "raw", "body", "message", "observation"):
        if key in env:
            env[key] = _walk(env[key])

    env.setdefault("provenance", []).append({
        "stage":           "privacy",
        "redacted":        sum(counts.values()) > 0,
        "redaction_kinds": counts,
        "policy":          pol,
    })
    return env


# ============================================================================
# Adversarial-Input Filter
# ============================================================================

# Markers that suggest the inbound content is trying to escape the
# untrusted-content envelope and reach the system prompt. Detection is best-
# effort — primary defense is the structural envelope itself.
_INJECTION_MARKERS: List[re.Pattern] = [
    re.compile(r"\bignore (?:all |any |the )?(?:previous|prior|above) instructions?\b", re.I),
    re.compile(r"\bdisregard (?:all |any |the )?(?:previous|prior|above)", re.I),
    re.compile(r"\byou are (?:now|actually) (?:a |an )?\w+", re.I),
    re.compile(r"\bsystem (?:prompt|message|instructions?)[: ]", re.I),
    re.compile(r"\bact as (?:if you were |a |an )", re.I),
    re.compile(r"<\|im_start\|>|<\|im_end\|>"),
    re.compile(r"<\|system\|>|<\|user\|>|<\|assistant\|>"),
    re.compile(r"\[\[INST\]\]|\[\[/INST\]\]|<<SYS>>|<</SYS>>"),
]


def adversarial_gate(envelope: Dict[str, Any]) -> Dict[str, Any]:
    """Wrap payload in a typed untrusted_content envelope; flag injection hits."""
    env = dict(envelope) if isinstance(envelope, dict) else {"raw": envelope}

    payload = None
    for key in ("payload", "raw", "body", "message"):
        if key in env:
            payload = env.pop(key)
            break

    injection_hits = _scan_injection(payload)
    env["untrusted_content"] = {
        "value":          payload,
        "is_trusted":     False,
        "injection_hits": injection_hits,
    }
    if injection_hits:
        # Drop confidence sharply; downstream agents must treat content as
        # data only, never as instructions.
        env["confidence"] = max(0.0, float(env.get("confidence", 0.5)) - 0.30)

    env.setdefault("provenance", []).append({
        "stage":          "adversarial",
        "wrapped":        True,
        "injection_hits": injection_hits,
    })
    return env


def _scan_injection(value: Any) -> List[str]:
    hits: List[str] = []
    for s in _walk_strings(value):
        for pat in _INJECTION_MARKERS:
            if pat.search(s):
                hits.append(pat.pattern)
                break
    return hits
