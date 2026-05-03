"""Phase 5 — External integrations / MCP (M5.1).

Bidirectional bridge between Numel's Capability Registry and the
Model Context Protocol tool shape. Numel can act as both:

  Server side  — exposes built-in capabilities (e.g. core.notify,
                 core.send_email) as MCP-style {name, description,
                 inputSchema} descriptors that an MCP client can
                 fetch and invoke. Every inbound `arguments` payload
                 passes through the Adversarial filter; every call
                 first runs the Alignment chain; every outbound
                 response passes through the Privacy gate.

  Client side  — accepts external tool descriptors (typically
                 fetched from a peer MCP server) and registers each
                 as a capability in the local registry under a
                 namespaced name `mcp.<server>.<tool>`. The remote
                 catalogue is also kept in `mcp_remote_tools.json`
                 so the operator can see what's been federated in.

State (under proactive.persistence.state_dir()):
  capabilities.json             — local Capability Registry (shared
                                   with the Substrate)
  mcp_remote_tools.json         — descriptors for tools imported
                                   from peer servers
  mcp_calls.jsonl               — append-only log of every MCP call
                                   (request + response + verdicts),
                                   parallel to the Ledger.

Public API:

  Server-side
    list_tools_as_mcp() -> list of MCP tool descriptors
    call_tool(name, arguments) -> {ok, result, ...} | {error, ...}
    register_handler(name, fn) — wire a Python callable to a
                                  capability so call_tool can run it

  Client-side
    register_remote(server, tool_descriptor, *, scopes=None) -> entry
    list_remote() -> [{server, name, original_name, description,
                        scopes, ts}, ...]
    drop_remote(name) -> bool

Design notes:

  - call_tool always goes through evolution.run_alignment() with a
    candidate dict shaped like `{kind: "actuation", target: name,
    payload: {capability: name, args: scrubbed_args}}`. A veto
    short-circuits the call with the validator trail in the response.
  - The remote-tool descriptors we accept follow MCP's
    `{name, description, inputSchema}` shape. Anything richer (e.g.
    annotations, danger flags) is preserved on the registry entry
    under `extra` and surfaced unchanged to operators.
"""

from __future__ import annotations

import time
from typing import Any, Callable, Dict, List, Optional

from . import evolution    as _evolution
from . import middleware   as _middleware
from . import persistence  as _persistence


_CAPS_FILE          = "capabilities"        # shared with the substrate
_REMOTE_FILE        = "mcp_remote_tools"    # descriptors of imported tools
_CALL_LOG_FILE      = "mcp_calls"           # JSONL


# ============================================================================
# Server side — export the local Capability Registry as MCP tools
# ============================================================================

def _seed_local_capabilities_if_empty() -> Dict[str, Any]:
    """Mirror the workflow's lazy-seed so call_tool works even when no
    workflow has run yet."""
    caps = _persistence.read_json(_CAPS_FILE, default={})
    if caps:
        return caps
    caps = {
        "core.notify": {
            "name":          "core.notify",
            "purpose":       "Surface a UI notification to the user",
            "scopes":        ["read-only"],
            "latency_tier":  "interactive",
            "cost_estimate": 0.0,
            "input_schema":  {
                "type":       "object",
                "properties": {"message": {"type": "string"}},
            },
        },
        "core.send_email": {
            "name":          "core.send_email",
            "purpose":       "Send an outbound email",
            "scopes":        ["write", "external-network", "affects-third-party"],
            "latency_tier":  "responsive",
            "cost_estimate": 0.001,
            "input_schema":  {
                "type":       "object",
                "properties": {
                    "to":      {"type": "string"},
                    "subject": {"type": "string"},
                    "body":    {"type": "string"},
                },
            },
        },
        "core.transfer_funds": {
            "name":          "core.transfer_funds",
            "purpose":       "Initiate a money transfer",
            "scopes":        ["spends-money", "write", "affects-third-party"],
            "latency_tier":  "responsive",
            "cost_estimate": 0.5,
            "input_schema":  {
                "type":       "object",
                "properties": {
                    "amount":    {"type": "number"},
                    "recipient": {"type": "string"},
                },
            },
        },
    }
    _persistence.write_json(_CAPS_FILE, caps)
    return caps


def list_tools_as_mcp() -> List[Dict[str, Any]]:
    """Return the local Capability Registry in MCP tool-descriptor shape."""
    caps  = _seed_local_capabilities_if_empty()
    tools: List[Dict[str, Any]] = []
    for name, cap in caps.items():
        if not isinstance(cap, dict):
            continue
        descriptor = {
            "name":        name,
            "description": str(cap.get("purpose") or ""),
            "inputSchema": cap.get("input_schema") or {"type": "object", "properties": {}},
            "annotations": {
                "scopes":        list(cap.get("scopes") or []),
                "latency_tier":  cap.get("latency_tier"),
                "cost_estimate": cap.get("cost_estimate"),
                "remote":        bool(cap.get("remote")),
            },
        }
        tools.append(descriptor)
    return tools


# ----------------------------------------------------------------------------
# Handler registry — actual Python callables for capability execution
# ----------------------------------------------------------------------------

_handlers: Dict[str, Callable[[Dict[str, Any]], Any]] = {}


def register_handler(name: str, fn: Callable[[Dict[str, Any]], Any]) -> None:
    if not name or not callable(fn):
        raise ValueError("register_handler needs a non-empty name and a callable")
    _handlers[name] = fn


def list_handlers() -> List[str]:
    return sorted(_handlers.keys())


def _builtin_notify_handler(args: Dict[str, Any]) -> Dict[str, Any]:
    """Demo-only built-in handler for `core.notify`. Real implementation
    would surface a UI toast via the assistant console."""
    return {
        "delivered": True,
        "message":   str((args or {}).get("message") or ""),
    }


register_handler("core.notify", _builtin_notify_handler)


# ----------------------------------------------------------------------------
# Tool invocation — Substrate-routed
# ----------------------------------------------------------------------------

def call_tool(name: str, arguments: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Invoke a registered capability through the Substrate gates.

    Pipeline:
      1. Lookup in the local Capability Registry (404 if missing).
      2. Adversarial filter over `arguments` so any prompt-injection
         markers are flagged in the call log.
      3. Build an `actuation` candidate; run evolution.run_alignment().
         A veto short-circuits with the validator trail in the
         response (status 200 with `{error: "alignment_veto", ...}`,
         not an HTTP error).
      4. Dispatch to the registered handler (or report
         `not_implemented` if no handler is wired).
      5. Privacy gate over the response payload before returning.
      6. Append the full request/response/verdict trace to
         mcp_calls.jsonl so operators can audit what flowed through.

    Returns one of:
      {ok: True,  result: <handler output>,  call_id: ...}
      {ok: False, error: "unknown_capability"|"alignment_veto"|"not_implemented"|"handler_error",
                  ...}
    """
    args = dict(arguments) if isinstance(arguments, dict) else {}
    caps = _seed_local_capabilities_if_empty()
    cap  = caps.get(name)

    call_id = f"mcp_{int(time.time() * 1000)}"
    trace: Dict[str, Any] = {
        "id":         call_id,
        "ts":         time.time(),
        "tool":       name,
        "arguments":  args,
        "remote":     False,
    }

    if cap is None:
        response = {"ok": False, "error": "unknown_capability", "tool": name, "call_id": call_id}
        trace["response"] = response
        _persistence.append_jsonl(_CALL_LOG_FILE, trace)
        return response

    # 2. Adversarial filter on incoming args. We wrap `args` as a synthetic
    #    payload so the filter can scan strings inside.
    env = _middleware.adversarial_gate({"source": "mcp", "payload": args})
    inj = ((env.get("untrusted_content") or {}).get("injection_hits") or [])
    trace["injection_hits"] = inj

    # 3. Alignment chain.
    candidate = {
        "kind":      "actuation",
        "target":    name,
        "payload":   {"capability": name, "args": args},
        "rationale": f"MCP tool call: {name}",
        "by":        "mcp_call",
    }
    alignment = _evolution.run_alignment(candidate)
    trace["alignment"] = alignment
    if alignment["decision"] != "pass":
        response = {
            "ok":         False,
            "error":      "alignment_veto",
            "tool":       name,
            "call_id":    call_id,
            "verdicts":   alignment["verdicts"],
        }
        trace["response"] = response
        _persistence.append_jsonl(_CALL_LOG_FILE, trace)
        return response

    # 4. Dispatch.
    handler = _handlers.get(name)
    if handler is None:
        response = {
            "ok":      False,
            "error":   "not_implemented",
            "tool":    name,
            "call_id": call_id,
            "reason":  f"no Python handler registered for capability {name!r}",
        }
        trace["response"] = response
        _persistence.append_jsonl(_CALL_LOG_FILE, trace)
        return response

    try:
        raw_result = handler(args)
    except Exception as exc:
        response = {
            "ok":      False,
            "error":   "handler_error",
            "tool":    name,
            "call_id": call_id,
            "detail":  f"{type(exc).__name__}: {exc}",
        }
        trace["response"] = response
        _persistence.append_jsonl(_CALL_LOG_FILE, trace)
        return response

    # 5. Privacy gate over the response payload.
    redacted = _middleware.privacy_gate({"source": "mcp", "payload": raw_result})
    result   = redacted.get("payload", raw_result)

    response = {
        "ok":          True,
        "result":      result,
        "tool":        name,
        "call_id":     call_id,
        "alignment":   alignment["decision"],
        "verdicts":    alignment["verdicts"],
    }
    trace["response"] = response
    _persistence.append_jsonl(_CALL_LOG_FILE, trace)
    return response


def list_calls(limit: int = 50) -> List[Dict[str, Any]]:
    """Return the most recent MCP-call traces (newest first)."""
    rows = _persistence.read_jsonl(_CALL_LOG_FILE)
    return list(reversed(rows))[:max(1, min(500, int(limit)))]


# ============================================================================
# Client side — register external tools as namespaced capabilities
# ============================================================================

_DEFAULT_REMOTE_SCOPES = ["external-network"]


def register_remote(
    server: str,
    tool: Dict[str, Any],
    *,
    scopes: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Add an external MCP tool to the local Capability Registry under
    `mcp.<server>.<tool.name>`. The original descriptor is preserved
    on the entry under `remote_descriptor` so a handler can find the
    routing info later.

    `scopes` defaults to `["external-network"]`. Callers should pass a
    more specific list when the tool is known to write or affect third
    parties — those scopes flow into the Governor's gate.
    """
    if not server or not isinstance(tool, dict):
        raise ValueError("server name and tool descriptor required")
    original = str(tool.get("name") or "").strip()
    if not original:
        raise ValueError("tool descriptor must have a non-empty 'name'")

    cap_name = f"mcp.{server}.{original}"
    caps     = _seed_local_capabilities_if_empty()
    eff_scopes = list(scopes) if scopes else list(_DEFAULT_REMOTE_SCOPES)

    entry = {
        "name":              cap_name,
        "purpose":           str(tool.get("description") or f"MCP tool {original} on {server}"),
        "scopes":            eff_scopes,
        "latency_tier":      "external-network",
        "cost_estimate":     None,
        "input_schema":      tool.get("inputSchema") or {"type": "object", "properties": {}},
        "remote":            True,
        "remote_descriptor": {
            "server":         server,
            "original_name":  original,
            "annotations":    tool.get("annotations") or {},
        },
    }
    caps[cap_name] = entry
    _persistence.write_json(_CAPS_FILE, caps)

    # Mirror in the remote-tools index for easy listing.
    remote_idx = _persistence.read_json(_REMOTE_FILE, default={})
    remote_idx[cap_name] = {
        "server":        server,
        "original_name": original,
        "description":   entry["purpose"],
        "scopes":        eff_scopes,
        "ts":            time.time(),
    }
    _persistence.write_json(_REMOTE_FILE, remote_idx)
    return entry


def list_remote() -> List[Dict[str, Any]]:
    idx = _persistence.read_json(_REMOTE_FILE, default={})
    out: List[Dict[str, Any]] = []
    for cap_name, info in idx.items():
        row = {"name": cap_name, **info}
        out.append(row)
    out.sort(key=lambda r: r.get("ts", 0), reverse=True)
    return out


def drop_remote(cap_name: str) -> bool:
    """Remove an imported remote tool from both the registry and the
    remote-tools index. Returns True if anything was removed."""
    if not cap_name:
        return False
    removed = False

    caps = _persistence.read_json(_CAPS_FILE, default={})
    if cap_name in caps and caps[cap_name].get("remote"):
        del caps[cap_name]
        _persistence.write_json(_CAPS_FILE, caps)
        removed = True

    idx = _persistence.read_json(_REMOTE_FILE, default={})
    if cap_name in idx:
        del idx[cap_name]
        _persistence.write_json(_REMOTE_FILE, idx)
        removed = True

    return removed
