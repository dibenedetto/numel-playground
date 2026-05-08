"""Phase 5 — External integrations / Generic transports (M5.3).

Bridges that let the Substrate present external LLM endpoints as
first-class entries in the Capability Registry. Every call goes through
the same gates as native capabilities — Adversarial filter on the
prompt, Alignment chain over a candidate envelope, Privacy gate on the
response — so an LLM bridge gets the same safety classification and
audit trail as `core.notify` or `core.send_email`.

Two transport flavours ship built-in:

  openai   — OpenAI-compatible Chat Completions
              (POST {base_url}/chat/completions, Bearer auth, JSON
              body `{model, messages, ...}`). Works with OpenAI proper,
              Azure OpenAI, vLLM, llama.cpp's openai_compatible server,
              Together, Groq, Ollama in OpenAI-compat mode, etc.
  anthropic — Anthropic Messages API
              (POST {base_url}/v1/messages, x-api-key auth, JSON body
              `{model, max_tokens, messages, system?}`). Works with the
              official Claude API and any compatible re-host.

Capabilities are registered under `transport.<flavour>.<alias>` so the
operator (and the Capability Registry's UI) can see at a glance which
endpoint each capability hits. Calls always route through `mcp.call_tool`
so the Adversarial → Alignment → Privacy chain runs uniformly.

State (under proactive.persistence.state_dir()):

  capabilities.json            — shared with the Substrate; transport-
                                  bridged tools live alongside the
                                  built-in capabilities.
  transport_configs.json       — bridge configs (kind, base_url, model,
                                  api_key_env, etc.). API keys are
                                  resolved from environment variables at
                                  call time — never persisted to disk.
  transport_calls.jsonl        — append-only request/response log
                                  (paralleling mcp_calls.jsonl).

Public API:

  register_transport(alias, *, kind, base_url, model, api_key_env=None,
                     scopes=None, extra=None) -> entry
  list_transports() -> list[entry]
  drop_transport(alias) -> bool
  call_transport(alias, prompt, *, dry_run=False) -> dict

Design notes:

  - `dry_run=True` short-circuits the HTTP call and returns a synthetic
    response. Used by smoke tests and by the UI's "Test" button so the
    operator can verify a bridge is wired correctly without spending
    tokens or hitting rate limits.
  - The registered capability's scopes default to
    `["external-network", "spends-money"]` — high-stake on both axes,
    so the Governor will route any actuation through `consent_required`
    unless the operator explicitly downgrades the scopes (e.g. for a
    self-hosted Ollama bridge that costs no money: pass
    `scopes=["external-network"]`).
  - HTTP itself is implemented with `urllib.request` so the module has
    no extra dependencies — the project already pins httpx for
    elsewhere, but a stdlib client keeps this bridge self-contained
    and trivially mockable.
"""

from __future__ import annotations

import json
import os
import time
import uuid
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

from . import mcp           as _mcp
from . import persistence   as _persistence


_CFG_FILE     = "transport_configs"   # → transport_configs.json
_CALL_LOG     = "transport_calls"     # → transport_calls.jsonl
_CAP_PREFIX   = "transport"           # capabilities are `transport.<kind>.<alias>`


KIND_OPENAI    = "openai"
KIND_ANTHROPIC = "anthropic"
VALID_KINDS    = {KIND_OPENAI, KIND_ANTHROPIC}


_DEFAULT_SCOPES = ["external-network", "spends-money"]


def _default_scopes() -> List[str]:
    """Resolve transport default scopes through proactive.config so
    `transports.default_scopes` in proactive_config.json overrides the
    in-code default without requiring callers to pass scopes at every
    register_transport()."""
    from . import config as _config
    val = _config.cfg("transports.default_scopes", _DEFAULT_SCOPES)
    return list(val) if isinstance(val, list) else list(_DEFAULT_SCOPES)


# ============================================================================
# Configuration registry
# ============================================================================

def _cap_name(kind: str, alias: str) -> str:
    return f"{_CAP_PREFIX}.{kind}.{alias}"


def register_transport(
    alias:       str,
    *,
    kind:        str,
    base_url:    str,
    model:       str,
    api_key_env: Optional[str] = None,
    scopes:      Optional[List[str]] = None,
    extra:       Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Register an external LLM endpoint as a Capability Registry entry.

    `alias` is a short human name (e.g. "claude_haiku", "ollama_llama3").
    `api_key_env` names an environment variable that holds the bearer
    token / x-api-key — never the key itself. `extra` carries
    transport-specific knobs (e.g. `max_tokens`, `temperature`).
    """
    if not alias or not alias.replace("_", "").replace("-", "").isalnum():
        raise ValueError("alias must be alphanumeric (underscore/dash allowed)")
    if kind not in VALID_KINDS:
        raise ValueError(f"kind must be one of {sorted(VALID_KINDS)}")
    if not base_url or not model:
        raise ValueError("base_url and model are required")

    eff_scopes = list(scopes) if scopes else _default_scopes()
    cfg = {
        "alias":       alias,
        "kind":        kind,
        "base_url":    base_url.rstrip("/"),
        "model":       model,
        "api_key_env": api_key_env,
        "scopes":      eff_scopes,
        "extra":       dict(extra) if isinstance(extra, dict) else {},
        "registered_at": time.time(),
    }
    cfgs = _persistence.read_json(_CFG_FILE, default={})
    cfgs[alias] = cfg
    _persistence.write_json(_CFG_FILE, cfgs)

    # Register in the shared Capability Registry so the rest of the
    # Substrate (Governor, MCP export, simulator) sees it.
    caps = _persistence.read_json("capabilities", default={})
    cap_name = _cap_name(kind, alias)
    caps[cap_name] = {
        "name":          cap_name,
        "purpose":       f"LLM bridge ({kind}) → model {model!r} at {cfg['base_url']}",
        "scopes":        eff_scopes,
        "latency_tier":  "responsive",
        "cost_estimate": None,
        "input_schema":  {
            "type":       "object",
            "properties": {
                "prompt": {"type": "string", "description": "User prompt to send"},
            },
            "required":   ["prompt"],
        },
        "transport":     cfg,    # back-pointer for invocation
    }
    _persistence.write_json("capabilities", caps)
    return cfg


def list_transports() -> List[Dict[str, Any]]:
    cfgs = _persistence.read_json(_CFG_FILE, default={})
    out = list(cfgs.values())
    out.sort(key=lambda c: c.get("registered_at", 0), reverse=True)
    return out


def drop_transport(alias: str) -> bool:
    cfgs = _persistence.read_json(_CFG_FILE, default={})
    cfg  = cfgs.get(alias)
    if not cfg:
        return False
    del cfgs[alias]
    _persistence.write_json(_CFG_FILE, cfgs)

    caps     = _persistence.read_json("capabilities", default={})
    cap_name = _cap_name(cfg["kind"], alias)
    if cap_name in caps:
        del caps[cap_name]
        _persistence.write_json("capabilities", caps)
    return True


# ============================================================================
# Invocation
# ============================================================================

def _post_json(url: str, body: Dict[str, Any], headers: Dict[str, str], timeout: float = 30.0) -> Dict[str, Any]:
    data = json.dumps(body).encode("utf-8")
    req  = urllib.request.Request(url, data=data, method="POST")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _build_openai_request(cfg: Dict[str, Any], prompt: str) -> Dict[str, Any]:
    extra = cfg.get("extra") or {}
    body = {
        "model":    cfg["model"],
        "messages": [{"role": "user", "content": prompt}],
    }
    for k in ("max_tokens", "temperature", "top_p", "stop"):
        if k in extra:
            body[k] = extra[k]
    return body


def _build_anthropic_request(cfg: Dict[str, Any], prompt: str) -> Dict[str, Any]:
    extra = cfg.get("extra") or {}
    body = {
        "model":      cfg["model"],
        "max_tokens": int(extra.get("max_tokens", 1024)),
        "messages":   [{"role": "user", "content": prompt}],
    }
    for k in ("temperature", "system", "top_p"):
        if k in extra:
            body[k] = extra[k]
    return body


def _extract_openai_text(resp: Dict[str, Any]) -> str:
    try:
        return resp["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError):
        return ""


def _extract_anthropic_text(resp: Dict[str, Any]) -> str:
    try:
        parts = resp["content"]
        if isinstance(parts, list):
            return "".join(p.get("text", "") for p in parts if isinstance(p, dict))
    except (KeyError, TypeError):
        pass
    return ""


def call_transport(
    alias:   str,
    prompt:  str,
    *,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Invoke a registered LLM transport through the Substrate gates.

    Routes through `mcp.call_tool` so the same Adversarial → Alignment
    → Privacy chain runs as for any other capability. The MCP handler
    we register here knows how to dispatch to the OpenAI-compatible or
    Anthropic endpoint, or — if `dry_run=True` — return a synthetic
    response without any HTTP traffic.

    Response shape mirrors `mcp.call_tool`:
        {ok: True,  result: {text, raw, transport, dry_run}, ...}
        {ok: False, error: ...}
    """
    cfgs = _persistence.read_json(_CFG_FILE, default={})
    cfg  = cfgs.get(alias)
    if not cfg:
        # Log the attempt — operators auditing transport_calls.jsonl
        # need to see calls to unregistered aliases too.
        response = {"ok": False, "error": "unknown_transport", "alias": alias}
        _persistence.append_jsonl(_CALL_LOG, {
            "id":       f"trn_{uuid.uuid4().hex[:12]}",
            "ts":       time.time(),
            "alias":    alias,
            "cap_name": None,
            "dry_run":  bool(dry_run),
            "prompt":   str(prompt or "")[:500],
            "response": response,
        })
        return response

    cap_name = _cap_name(cfg["kind"], alias)

    # Make sure the handler is registered — it dispatches to the actual
    # HTTP call and tags the response so the call log can render it.
    if cap_name not in _mcp.list_handlers():
        _mcp.register_handler(cap_name, _make_handler(alias))

    arguments = {"prompt": str(prompt or ""), "_dry_run": bool(dry_run)}
    response  = _mcp.call_tool(cap_name, arguments)

    # Mirror the call to our own log so transport-specific operators
    # don't have to grep mcp_calls.jsonl for every bridge.
    record = {
        "id":        f"trn_{uuid.uuid4().hex[:12]}",
        "ts":        time.time(),
        "alias":     alias,
        "cap_name":  cap_name,
        "dry_run":   bool(dry_run),
        "prompt":    str(prompt or "")[:500],
        "response":  response,
    }
    _persistence.append_jsonl(_CALL_LOG, record)
    return response


def _make_handler(alias: str):
    """Build an MCP handler closure for a specific transport alias."""
    def _handler(args: Dict[str, Any]) -> Dict[str, Any]:
        cfgs = _persistence.read_json(_CFG_FILE, default={})
        cfg  = cfgs.get(alias)
        if not cfg:
            return {"ok": False, "error": "unknown_transport", "alias": alias}

        prompt   = str((args or {}).get("prompt") or "")
        dry_run  = bool((args or {}).get("_dry_run", False))
        kind     = cfg["kind"]

        if dry_run:
            return {
                "ok":        True,
                "text":      f"[dry-run from {alias} ({kind})] echo: {prompt[:200]}",
                "raw":       {"dry_run": True, "model": cfg["model"]},
                "transport": {"alias": alias, "kind": kind, "model": cfg["model"]},
                "dry_run":   True,
            }

        # Resolve API key from env (never persisted).
        api_key = None
        env_var = cfg.get("api_key_env")
        if env_var:
            api_key = os.environ.get(env_var)
            if not api_key:
                return {
                    "ok":      False,
                    "error":   "missing_api_key",
                    "detail":  f"environment variable {env_var!r} not set",
                }

        try:
            if kind == KIND_OPENAI:
                url     = cfg["base_url"] + "/chat/completions"
                headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
                body    = _build_openai_request(cfg, prompt)
                raw     = _post_json(url, body, headers)
                text    = _extract_openai_text(raw)
            elif kind == KIND_ANTHROPIC:
                url     = cfg["base_url"] + "/v1/messages"
                headers = {
                    "x-api-key":         api_key or "",
                    "anthropic-version": cfg.get("extra", {}).get("anthropic_version", "2023-06-01"),
                }
                body    = _build_anthropic_request(cfg, prompt)
                raw     = _post_json(url, body, headers)
                text    = _extract_anthropic_text(raw)
            else:
                return {"ok": False, "error": "unsupported_kind", "kind": kind}
        except urllib.error.HTTPError as exc:
            return {
                "ok":     False,
                "error":  "transport_http_error",
                "status": exc.code,
                "detail": exc.read().decode("utf-8", errors="replace")[:500],
            }
        except urllib.error.URLError as exc:
            return {"ok": False, "error": "transport_url_error", "detail": str(exc)}
        except Exception as exc:
            return {"ok": False, "error": "transport_error",
                    "detail": f"{type(exc).__name__}: {exc}"}

        return {
            "ok":        True,
            "text":      text,
            "raw":       raw,
            "transport": {"alias": alias, "kind": kind, "model": cfg["model"]},
            "dry_run":   False,
        }
    return _handler


def list_calls(limit: int = 50) -> List[Dict[str, Any]]:
    rows = _persistence.read_jsonl(_CALL_LOG)
    return list(reversed(rows))[:max(1, min(500, int(limit)))]
