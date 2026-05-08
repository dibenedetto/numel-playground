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

from . import config      as _config
from . import evolution   as _evolution
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

# Default thresholds. Each propose() reads through proactive.config.cfg(...)
# so an operator can override any subset via state_dir()/proactive_config.json
# without code changes. The constants below are the *defaults* — they
# document the safe baseline and are returned when no override is set.
_DENY_RATE_THRESHOLD       = 0.50    # ≥50% of an action's verdicts are deny
_DENY_MIN_SAMPLES          = 4       # need at least N total verdicts
_QUARANTINE_FAILURE_FLOOR  = 5       # ≥N recorded failures → propose hard-ban
_THUMBS_UP_TO_RELAX        = 3       # ≥N thumbs-up to suggest relaxing a ban


def _opt_cfg() -> Dict[str, Any]:
    """Resolve the four Optimization thresholds in one call (saves four
    JSON loads when propose() runs all strategies in sequence)."""
    return {
        "deny_rate_threshold":       float(_config.cfg("optimization.deny_rate_threshold",       _DENY_RATE_THRESHOLD)),
        "deny_min_samples":          int  (_config.cfg("optimization.deny_min_samples",          _DENY_MIN_SAMPLES)),
        "quarantine_failure_floor":  int  (_config.cfg("optimization.quarantine_failure_floor",  _QUARANTINE_FAILURE_FLOOR)),
        "thumbs_up_to_relax":        float(_config.cfg("optimization.thumbs_up_to_relax",        _THUMBS_UP_TO_RELAX)),
    }


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
    IMPLICIT_WEIGHT = float(_config.cfg("evolution.implicit_weight", 0.5))
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
    cfg = _opt_cfg()
    deny_rate_threshold = cfg["deny_rate_threshold"]
    deny_min_samples    = cfg["deny_min_samples"]
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
        if total < deny_min_samples:
            continue
        denies = stats.get("deny", 0)
        if denies / total < deny_rate_threshold:
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
    failure_floor = int(_config.cfg("optimization.quarantine_failure_floor", _QUARANTINE_FAILURE_FLOOR))
    for cap, info in (quarantine_keys or {}).items():
        if cap in already_banned:
            continue
        if not isinstance(info, dict) or not info.get("quarantined"):
            continue
        fails = info.get("failures") or []
        if len(fails) < failure_floor:
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
    relax_threshold = float(_config.cfg("optimization.thumbs_up_to_relax", _THUMBS_UP_TO_RELAX))
    candidates: List[Dict[str, Any]] = []
    for rule in rules:
        cap = rule.get("target")
        if not cap:
            continue
        bucket  = per_cap.get(cap) or {}
        weight  = float(bucket.get("pos") or 0.0)
        if weight < relax_threshold:
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
    # M5.8-B — LLM-backed proposer joins the strategy mix when an
    # `agent.evolution_proposer` Capability is registered (operator
    # opt-in). When no proposer is registered the call returns []
    # and the live state is unchanged.
    out.extend(strategy_llm_propose(ledger, signals))

    # Stamp each candidate with a consistent surface for downstream layers.
    now = time.time()
    for c in out:
        c.setdefault("ts", now)
    return out


# ============================================================================
# LLM-backed proposer (M5.8-B)
# ============================================================================

LLM_PROPOSER_ALIAS  = "evolution_proposer"
_LLM_LEDGER_LIMIT   = 50    # most-recent N entries to summarise
_LLM_FEEDBACK_LIMIT = 30
_LLM_PROMPT_NAME    = "evolution_proposer"   # → app/proactive/prompts/evolution_proposer.txt
# Last-resort default if neither the package-shipped prompt file nor the
# state_dir overlay exists. Kept short — the real prompt lives in
# app/proactive/prompts/evolution_proposer.txt.
_LLM_PROMPT_FALLBACK = (
    "You are an Evolution proposer. Reply with "
    '{"proposals": [{"action": "ban"|"relax", '
    '"target": "<capability_name>", "rationale": "<one sentence>"}]}.'
)


def _llm_proposer_alias() -> str:
    return str(_config.cfg("llm_proposer.alias", LLM_PROPOSER_ALIAS))


def llm_proposer_registered() -> bool:
    """True when the configured LLM proposer alias resolves to a registered
    Capability (i.e. an operator has called
    `proactive.agents.register_agent_handler(<alias>, …)` or
    `ensure_default_proposer()` has wired up the auto-registered bridge)."""
    cap_name = f"agent.{_llm_proposer_alias()}"
    caps = _persistence.read_json("capabilities", default={})
    return cap_name in caps


# Per-source defaults so config can stay terse — `llm_proposer.model.source`
# alone is enough for OpenAI-compat hosts running on conventional URLs.
_MODEL_SOURCE_DEFAULTS: Dict[str, Dict[str, Any]] = {
    "ollama":    {"kind": "openai",    "base_url": "http://localhost:11434/v1", "api_key_env": None},
    "openai":    {"kind": "openai",    "base_url": "https://api.openai.com/v1", "api_key_env": "OPENAI_API_KEY"},
    "anthropic": {"kind": "anthropic", "base_url": "https://api.anthropic.com",  "api_key_env": "ANTHROPIC_API_KEY"},
}


def _resolve_proposer_model() -> Dict[str, Any]:
    """Resolve {kind, alias, base_url, model, api_key_env} from the
    `llm_proposer.model.*` config block. The `source` field selects a
    canonical endpoint family (ollama / openai / anthropic), and any of
    the per-source defaults can be overridden in config — so an operator
    pointing at a self-hosted vLLM behind a custom URL just sets
    `source=openai` + `base_url=http://my-vllm:8000/v1`."""
    source = str(_config.cfg("llm_proposer.model.source", "ollama")).strip().lower()
    name   = str(_config.cfg("llm_proposer.model.name",   "llama3")).strip()
    base   = _config.cfg("llm_proposer.model.base_url",   None)
    api_env = _config.cfg("llm_proposer.model.api_key_env", None)

    defaults = _MODEL_SOURCE_DEFAULTS.get(source) or _MODEL_SOURCE_DEFAULTS["openai"]
    if base is None:
        base = defaults["base_url"]
    if api_env is None:
        api_env = defaults["api_key_env"]
    return {
        "source":      source,
        "kind":        defaults["kind"],
        "model":       name,
        "base_url":    str(base).rstrip("/"),
        "api_key_env": api_env,
        "alias":       _llm_proposer_alias(),
    }


def ensure_default_proposer(*, dry_run: bool = False) -> Dict[str, Any]:
    """Idempotent — make sure an `agent.<llm_proposer.alias>` Capability is
    registered. If one's already there (operator wired their own handler),
    do nothing. Otherwise register a transport-backed handler that
    forwards the prompt to whatever model the `llm_proposer.model.*`
    config block points at.

    `dry_run=True` makes the auto-registered handler call
    `proactive.transports.call_transport(..., dry_run=True)` so smoke
    tests can exercise the round-trip without hitting a real model.

    Returns a status dict: {alias, cap_name, source, model, registered_now}."""
    from . import agents     as _agents
    from . import transports as _tr

    spec     = _resolve_proposer_model()
    alias    = spec["alias"]
    cap_name = f"agent.{alias}"

    if llm_proposer_registered():
        return {**spec, "cap_name": cap_name, "registered_now": False}

    # Register the transport bridge (idempotent — drop+re-register keeps
    # the metadata in sync with the current config).
    transport_alias = f"proposer__{alias}"
    try:
        _tr.drop_transport(transport_alias)
    except Exception:
        pass
    _tr.register_transport(
        transport_alias,
        kind        = spec["kind"],
        base_url    = spec["base_url"],
        model       = spec["model"],
        api_key_env = spec["api_key_env"],
        scopes      = ["external-network", "llm"],
    )

    def _handler(args):
        prompt   = args.get("request") or args.get("prompt") or ""
        response = _tr.call_transport(transport_alias, str(prompt), dry_run=bool(dry_run))
        # call_transport returns the mcp.call_tool envelope. The
        # proposer's parser reads `result.text`/`result.content`, so we
        # surface whichever the transport emitted.
        if isinstance(response, dict) and response.get("ok"):
            inner = response.get("result")
            if isinstance(inner, dict):
                return {"content": inner.get("text") or inner.get("content") or "", "content_type": "text"}
            return {"content": str(inner or ""), "content_type": "text"}
        # Failure — the strategy will see ok=False and return [].
        return response

    _agents.register_agent_handler(
        alias, _handler,
        kind        = _agents.KIND_LOCAL,
        description = f"Auto-registered LLM proposer ({spec['source']}/{spec['model']})",
    )
    return {**spec, "cap_name": cap_name, "registered_now": True}


def _summarise_ledger_for_llm(
    ledger: List[Dict[str, Any]],
    limit:  Optional[int] = None,
) -> str:
    """Build a compact, deterministic ledger summary for the LLM prompt.

    One line per entry: `<topic>  <decision>  <capability>  <motor_status>`.
    Only the last `limit` entries (most-recent first). When `limit` is
    None it's read from `llm_proposer.ledger_limit` config."""
    if limit is None:
        limit = int(_config.cfg("llm_proposer.ledger_limit", _LLM_LEDGER_LIMIT))
    rows: List[str] = []
    for entry in list(reversed(ledger))[:max(1, limit)]:
        topic    = (entry.get("trigger") or {}).get("topic", "?")
        verdict  = entry.get("governor_verdict") or {}
        decision = verdict.get("decision") or "-"
        cap      = verdict.get("capability") or "-"
        motor    = entry.get("motor_status") or "-"
        rows.append(f"{topic:35s} {decision:18s} {cap:30s} {motor}")
    return "\n".join(rows) if rows else "(no ledger entries)"


def _summarise_feedback_for_llm(
    signals: List[Dict[str, Any]],
    limit:   Optional[int] = None,
) -> str:
    """Compact feedback summary — kind, value, and the targeted capability."""
    if limit is None:
        limit = int(_config.cfg("llm_proposer.feedback_limit", _LLM_FEEDBACK_LIMIT))
    rows: List[str] = []
    for s in list(reversed(signals))[:max(1, limit)]:
        kind  = s.get("kind") or "-"
        value = s.get("value")
        cap   = (s.get("context") or {}).get("capability") or "-"
        rows.append(f"{kind:18s} {str(value)[:25]:25s} {cap}")
    return "\n".join(rows) if rows else "(no feedback signals)"


def _summarise_constitution_for_llm() -> str:
    cur   = _evolution.read_constitution()
    rules = cur.get("rules") or []
    if not rules:
        return "(no rules)"
    return "\n".join(
        f"- {r.get('kind') or '?'}  {r.get('target') or '?'}"
        for r in rules if isinstance(r, dict)
    )


def _parse_llm_proposals(text: Any, *, allowed_targets: set) -> List[Dict[str, Any]]:
    """Extract Constitution rule candidates from the LLM's response.

    The LLM is instructed to return `{"proposals": [...]}`. We tolerate
    leading / trailing prose by extracting the first balanced JSON
    object. Each proposal must reference a capability that's in
    `allowed_targets` (the visible capability set) — proposals against
    unknown targets are dropped to prevent the LLM from inventing
    capability names.
    """
    if not text:
        return []
    s = str(text).strip()
    # Find the first '{' and matching '}' — the prompt asks for a single
    # JSON object so this is robust to LLM padding like "Here's the JSON:".
    start = s.find("{")
    if start < 0:
        return []
    depth, end = 0, -1
    for i in range(start, len(s)):
        c = s[i]
        if c == "{": depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    if end < 0:
        return []
    try:
        obj = json.loads(s[start:end])
    except Exception:
        return []
    proposals = obj.get("proposals") if isinstance(obj, dict) else None
    if not isinstance(proposals, list):
        return []

    out: List[Dict[str, Any]] = []
    for p in proposals:
        if not isinstance(p, dict):
            continue
        action = str(p.get("action") or "").strip().lower()
        target = str(p.get("target") or "").strip()
        if not target or target not in allowed_targets:
            # LLM hallucinated a capability — drop silently. The Why-chain
            # records the raw response so the operator can audit.
            continue
        rationale = str(p.get("rationale") or "").strip()[:200]
        if action == "ban":
            out.append({
                "kind":      "constitution_rule_add",
                "target":    target,
                "payload":   {"rule": {"kind": "never", "target": target}},
                "rationale": rationale or f"LLM proposer suggested banning '{target}'",
                "evidence":  {"source": "llm_proposer", "raw": p},
                "by":        "llm_propose",
            })
        elif action == "relax":
            # Find an existing `never` rule we'd be undoing.
            constitution = _evolution.read_constitution()
            rule = next(
                (r for r in (constitution.get("rules") or [])
                 if isinstance(r, dict)
                 and r.get("kind") == "never"
                 and r.get("target") == target),
                None,
            )
            if not rule:
                # No matching rule to relax — skip.
                continue
            out.append({
                "kind":      "constitution_rule_remove",
                "target":    target,
                "payload":   {"rule_id": rule.get("id"), "rule": rule},
                "rationale": rationale or f"LLM proposer suggested relaxing '{target}'",
                "evidence":  {"source": "llm_proposer", "raw": p},
                "by":        "llm_propose",
            })
    return out


def strategy_llm_propose(
    ledger:  List[Dict[str, Any]],
    signals: List[Dict[str, Any]],
    *,
    alias:   Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Ask a registered LLM agent (`agent.<alias>`) to propose Constitution
    rule changes. The agent reads a compact summary of recent activity
    and returns JSON proposals. Each proposal becomes a candidate the
    rest of the Evolution loop (simulator, validators, promotion gate)
    treats identically to a heuristic-strategy candidate.

    The `alias`, the prompt body, and the model behind the alias are all
    operator-tunable through `proactive_config.json` and the
    `prompts/evolution_proposer.txt` overlay. When the alias is not
    registered, this strategy is a clean no-op."""
    effective_alias = alias or _llm_proposer_alias()
    if not llm_proposer_registered():
        return []

    # Lazy import — proactive.agents pulls in mcp + middleware. Importing
    # at module top would force every optimization caller to take the
    # whole gate-chain dependency.
    from . import agents as _agents

    # Capabilities the LLM is allowed to propose against:
    #  - everything in capabilities.json (formally registered)
    #  - everything seen in the Ledger's governor_verdict.capability
    #    (real activity, even if the cap was registered in-memory only)
    #  - every target a Constitution rule already references
    #    (so `relax` proposals can name caps not in capabilities.json)
    caps = _persistence.read_json("capabilities", default={})
    allowed_targets: set = set(caps.keys())
    for entry in ledger:
        cap = (entry.get("governor_verdict") or {}).get("capability")
        if isinstance(cap, str) and cap:
            allowed_targets.add(cap)
    for rule in (_evolution.read_constitution().get("rules") or []):
        if isinstance(rule, dict):
            tgt = rule.get("target")
            if isinstance(tgt, str) and tgt:
                allowed_targets.add(tgt)

    # The prompt body is loaded from app/proactive/prompts/evolution_proposer.txt
    # (or its state_dir overlay) so operators can tune wording / policy
    # without touching code. _LLM_PROMPT_FALLBACK is the last-resort
    # in-code default — used only if both the package file and the
    # overlay file are missing.
    prompt_guard = _config.load_prompt(_LLM_PROMPT_NAME, default=_LLM_PROMPT_FALLBACK)

    prompt = (
        f"## Recent ledger activity (newest first)\n"
        f"{_summarise_ledger_for_llm(ledger)}\n\n"
        f"## Recent feedback (newest first)\n"
        f"{_summarise_feedback_for_llm(signals)}\n\n"
        f"## Current Constitution rules\n"
        f"{_summarise_constitution_for_llm()}\n\n"
        f"{prompt_guard}"
    )

    try:
        response = _agents.call_agent(effective_alias, prompt, kind=_agents.KIND_LOCAL)
    except Exception:
        return []

    if not isinstance(response, dict) or not response.get("ok"):
        # Gate veto, alignment refusal, handler error — nothing to add.
        return []

    result = response.get("result")
    if isinstance(result, dict):
        text = result.get("content") or result.get("text") or ""
    elif isinstance(result, str):
        text = result
    else:
        text = str(result or "")

    return _parse_llm_proposals(text, allowed_targets=allowed_targets)


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
