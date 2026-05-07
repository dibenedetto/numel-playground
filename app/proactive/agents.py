"""Phase 5 — External integrations / Agent capability bridge (M5.4).

Bridges that let local `agent_flow` and `agent_endpoint_flow` nodes,
plus A2A peer endpoints (M5.6), present themselves as first-class
entries in the Capability Registry. Every call routes through
`mcp.call_tool` so the same Adversarial → Alignment → Privacy chain
runs as for any other capability — collapsing the previously parallel
codepaths (agent_flow / agent_endpoint_flow / a2a / transports / mcp)
into one uniform invocation model.

Three classes of capability live in one Registry:

  agent.<alias>           — local in-process agent (M5.4)
                             Backed by an async callable that takes
                             (request, image=None) and returns the
                             agent's response dict.
  agent.endpoint.<alias>  — remote agent endpoint (M5.5)
                             Backed by an async callable that takes
                             (mode, prompt, ...) and returns the
                             endpoint's structured result.
  a2a.<peer>.<verb>       — A2A peer interaction (M5.6)
                             Backed by `a2a.send` / `a2a.share_state`
                             routed through the gate chain.

State (under proactive.persistence.state_dir()):

  capabilities.json      — shared with the rest of the Substrate.
  agent_configs.json     — operator-supplied bridge configs (alias,
                            kind, scopes, description, …) so the Vitals
                            UI / Governor can introspect them.
  agent_calls.jsonl      — append-only request/response log.

Public API:

  register_agent_handler(alias, handler, *, kind="local",
                         scopes=None, description=None,
                         input_schema=None, extra=None) -> entry
  list_agents()                                           -> list
  drop_agent(alias)                                       -> bool
  call_agent(alias, request, *, image=None,
             extra_args=None)                             -> dict
  list_calls(limit=50)                                    -> list

Design notes:

  - Registration is operator-controlled via an alias (mirroring
    `register_transport`) so capabilities are addressable across
    workflows. Multiple agent_flow nodes wired to the same alias share
    one Capability entry — the Governor sees one logical agent, not N
    nodes.
  - `call_agent` is synchronous from the caller's POV (it awaits the
    handler internally via asyncio.run when needed). The handler may
    be sync or async; both are tolerated.
  - Default scopes: `["llm"]` for local agents, `["external-network",
    "delegates-authority"]` for remote endpoints. `mode_scopes` lets
    the M5.5 layer add `delegate` → `["delegates-authority"]`,
    `notify` → `["affects-third-party"]`, etc.
  - Gating is opt-in via the `NUMEL_PROACTIVE_AGENT_GATING` env var
    (read at WFAgentFlow / WFAgentEndpointFlow execute time). When
    disabled, those nodes call their backend `ref` directly — no
    behaviour change for non-proactive deployments.
"""

from __future__ import annotations

import asyncio
import inspect
import time
import uuid
from typing import Any, Awaitable, Callable, Dict, List, Optional, Union

from . import mcp         as _mcp
from . import persistence as _persistence


_CFG_FILE   = "agent_configs"   # → agent_configs.json
_CALL_LOG   = "agent_calls"     # → agent_calls.jsonl
_CAP_PREFIX = "agent"           # capabilities are `agent.<alias>` or `agent.endpoint.<alias>`


KIND_LOCAL    = "local"      # in-process agent_flow
KIND_ENDPOINT = "endpoint"   # remote agent_endpoint_flow
KIND_A2A      = "a2a"        # A2A peer interaction
VALID_KINDS   = {KIND_LOCAL, KIND_ENDPOINT, KIND_A2A}


_DEFAULT_SCOPES_BY_KIND: Dict[str, List[str]] = {
    KIND_LOCAL:    ["llm"],
    KIND_ENDPOINT: ["external-network", "delegates-authority"],
    KIND_A2A:      ["external-network"],
}


HandlerCallable = Callable[[Dict[str, Any]], Union[Any, Awaitable[Any]]]


# ============================================================================
# Capability naming
# ============================================================================

def _cap_name(kind: str, alias: str) -> str:
    if kind == KIND_LOCAL:
        return f"{_CAP_PREFIX}.{alias}"
    if kind == KIND_ENDPOINT:
        return f"{_CAP_PREFIX}.endpoint.{alias}"
    if kind == KIND_A2A:
        # alias for A2A is `<peer_id>.<verb>` (e.g. "alpha.send", "alpha.share_state")
        return f"a2a.{alias}"
    raise ValueError(f"unknown agent kind: {kind!r}")


def _validate_alias(alias: str) -> None:
    if not alias:
        raise ValueError("alias must be non-empty")
    cleaned = alias.replace("_", "").replace("-", "").replace(".", "")
    if not cleaned.isalnum():
        raise ValueError("alias must be alphanumeric (underscore / dash / dot allowed)")


# ============================================================================
# Registration
# ============================================================================

def register_agent_handler(
    alias:        str,
    handler:      HandlerCallable,
    *,
    kind:         str = KIND_LOCAL,
    scopes:       Optional[List[str]] = None,
    description:  Optional[str] = None,
    input_schema: Optional[Dict[str, Any]] = None,
    extra:        Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Register an agent-class capability and wire the dispatch handler.

    `alias` is the operator-visible short name (e.g. "research_assistant",
    "deployment_alpha", "alice.send"). `handler` is invoked by
    `call_agent` after the gate chain runs; it receives the args dict
    that was passed to `call_agent` (`{request, image?, ...extra_args}`)
    and returns the agent's response.
    """
    _validate_alias(alias)
    if kind not in VALID_KINDS:
        raise ValueError(f"kind must be one of {sorted(VALID_KINDS)}")
    if not callable(handler):
        raise ValueError("handler must be callable")

    cap_name   = _cap_name(kind, alias)
    eff_scopes = list(scopes) if scopes else list(_DEFAULT_SCOPES_BY_KIND[kind])
    purpose    = description or _default_purpose(kind, alias)
    schema     = input_schema or _default_input_schema(kind)

    cfg = {
        "alias":         alias,
        "kind":          kind,
        "cap_name":      cap_name,
        "scopes":        eff_scopes,
        "description":   purpose,
        "input_schema":  schema,
        "extra":         dict(extra) if isinstance(extra, dict) else {},
        "registered_at": time.time(),
    }
    cfgs = _persistence.read_json(_CFG_FILE, default={})
    cfgs[cap_name] = cfg
    _persistence.write_json(_CFG_FILE, cfgs)

    caps = _persistence.read_json("capabilities", default={})
    caps[cap_name] = {
        "name":          cap_name,
        "purpose":       purpose,
        "scopes":        eff_scopes,
        "latency_tier":  "responsive",
        "cost_estimate": None,
        "input_schema":  schema,
        "agent_bridge":  cfg,    # back-pointer for introspection
    }
    _persistence.write_json("capabilities", caps)

    _mcp.register_handler(cap_name, _wrap_handler(handler))
    return cfg


def _default_purpose(kind: str, alias: str) -> str:
    if kind == KIND_LOCAL:
        return f"Local agent bridge → {alias!r}"
    if kind == KIND_ENDPOINT:
        return f"Remote agent endpoint bridge → {alias!r}"
    if kind == KIND_A2A:
        return f"A2A peer bridge → {alias!r}"
    return alias


def _default_input_schema(kind: str) -> Dict[str, Any]:
    if kind == KIND_ENDPOINT:
        return {
            "type":       "object",
            "properties": {
                "prompt":     {"type": "string"},
                "mode":       {"type": "string"},
                "session_id": {"type": "string"},
            },
            "required":   ["prompt"],
        }
    if kind == KIND_A2A:
        return {
            "type":       "object",
            "properties": {
                "message":    {"type": "object"},
                "namespaces": {"type": "array", "items": {"type": "string"}},
                "kind":       {"type": "string"},
            },
        }
    return {
        "type":       "object",
        "properties": {
            "request": {"type": "string", "description": "User message for the agent"},
            "image":   {"type": "string", "description": "Optional base64-encoded image"},
        },
        "required":   ["request"],
    }


def _wrap_handler(handler: HandlerCallable) -> Callable[[Dict[str, Any]], Any]:
    """Wrap a possibly-async handler for synchronous dispatch via mcp.call_tool.

    The wrapper detects coroutines and runs them on a fresh event loop if
    the caller isn't already in one; otherwise it returns the awaitable
    for the caller to await. mcp.call_tool's caller (the workflow engine
    or an HTTP endpoint) is responsible for awaiting if needed.
    """
    def wrapped(args: Dict[str, Any]) -> Any:
        result = handler(args)
        if inspect.iscoroutine(result):
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # We're inside an event loop already — return the
                    # coroutine for the engine to await externally. The
                    # engine's flow only has sync mcp.call_tool today;
                    # we run a nested loop here as a fallback.
                    return _run_nested(result)
                return loop.run_until_complete(result)
            except RuntimeError:
                return asyncio.run(result)
        return result
    return wrapped


def _run_nested(coro: Awaitable[Any]) -> Any:
    """Run a coroutine to completion from inside a running loop.

    Uses a new thread + new event loop because asyncio.run() can't be
    called when a loop is already running on the current thread. This
    is the same pattern numel uses in a few other backend bridges.
    """
    import threading
    out: Dict[str, Any] = {}

    def _runner() -> None:
        loop = asyncio.new_event_loop()
        try:
            out["value"] = loop.run_until_complete(coro)
        except Exception as exc:
            out["error"] = exc
        finally:
            loop.close()

    t = threading.Thread(target=_runner, daemon=True)
    t.start()
    t.join()
    if "error" in out:
        raise out["error"]
    return out.get("value")


# ============================================================================
# Listing / drop
# ============================================================================

def list_agents() -> List[Dict[str, Any]]:
    cfgs = _persistence.read_json(_CFG_FILE, default={})
    out  = list(cfgs.values())
    out.sort(key=lambda c: c.get("registered_at", 0), reverse=True)
    return out


def drop_agent(cap_name_or_alias: str, *, kind: str = KIND_LOCAL) -> bool:
    """Remove a registered agent capability. Accepts either the full
    capability name (`agent.foo`) or the bare alias (`foo`, in which
    case `kind` is used to construct the cap name)."""
    if not cap_name_or_alias:
        return False
    if cap_name_or_alias.startswith("agent.") or cap_name_or_alias.startswith("a2a."):
        cap_name = cap_name_or_alias
    else:
        cap_name = _cap_name(kind, cap_name_or_alias)

    cfgs = _persistence.read_json(_CFG_FILE, default={})
    if cap_name not in cfgs:
        return False
    del cfgs[cap_name]
    _persistence.write_json(_CFG_FILE, cfgs)

    caps = _persistence.read_json("capabilities", default={})
    if cap_name in caps:
        del caps[cap_name]
        _persistence.write_json("capabilities", caps)

    # Remove the in-memory handler too. mcp.register_handler doesn't
    # expose a deregister, so we set it to a stub that returns
    # not_implemented; cleaner than leaking the closure.
    _mcp.register_handler(cap_name, _make_dropped_stub(cap_name))
    return True


def _make_dropped_stub(cap_name: str) -> Callable[[Dict[str, Any]], Any]:
    def _stub(_args: Dict[str, Any]) -> Dict[str, Any]:
        return {"ok": False, "error": "agent_dropped", "cap_name": cap_name}
    return _stub


# ============================================================================
# Invocation
# ============================================================================

def call_agent(
    alias:      str,
    request:    Any,
    *,
    image:      Optional[str] = None,
    kind:       str = KIND_LOCAL,
    extra_args: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Invoke a registered agent capability through the Substrate gates.

    Routes through `mcp.call_tool` so the Adversarial → Alignment →
    handler → Privacy chain runs uniformly. `request` is the user
    message (string or dict); `image` is an optional base64 payload for
    multimodal agents; `extra_args` carries kind-specific knobs (e.g.
    `mode`, `session_id` for endpoints; `namespaces` for A2A).

    Response shape mirrors `mcp.call_tool`:
        {ok: True,  result: <handler output>, ...}
        {ok: False, error: ...}
    """
    cap_name = _cap_name(kind, alias)

    arguments: Dict[str, Any] = {"request": request}
    if image is not None:
        arguments["image"] = image
    if isinstance(extra_args, dict):
        for k, v in extra_args.items():
            if k not in arguments:
                arguments[k] = v

    response = _mcp.call_tool(cap_name, arguments)

    record = {
        "id":       f"agt_{uuid.uuid4().hex[:12]}",
        "ts":       time.time(),
        "alias":    alias,
        "kind":     kind,
        "cap_name": cap_name,
        "request":  _summarise(request),
        "image":    bool(image),
        "extra":    dict(extra_args) if isinstance(extra_args, dict) else {},
        "response": response,
    }
    _persistence.append_jsonl(_CALL_LOG, record)
    return response


def _summarise(request: Any, limit: int = 500) -> Any:
    if isinstance(request, str):
        return request[:limit]
    try:
        import json as _json
        return _json.dumps(request, ensure_ascii=False)[:limit]
    except Exception:
        return str(request)[:limit]


def list_calls(limit: int = 50) -> List[Dict[str, Any]]:
    rows = _persistence.read_jsonl(_CALL_LOG)
    return list(reversed(rows))[:max(1, min(500, int(limit)))]


# ============================================================================
# Gating policy — opt-in for WFAgentFlow / WFAgentEndpointFlow
# ============================================================================

import os


def gating_enabled() -> bool:
    """True when WFAgentFlow / WFAgentEndpointFlow should route their
    invocations through the Substrate gate chain.

    Opt-in via the `NUMEL_PROACTIVE_AGENT_GATING` env var so existing
    non-proactive deployments are not silently retrofitted with gating
    overhead. Set to "1" / "true" / "yes" (case-insensitive) to enable.
    """
    value = (os.environ.get("NUMEL_PROACTIVE_AGENT_GATING") or "").strip().lower()
    return value in {"1", "true", "yes", "on"}
