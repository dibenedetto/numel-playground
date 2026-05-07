# Technical Specification: The Proactive AI Agent Ecology

*Implementation companion to `proactive.md`. The conceptual blueprint describes what each component is for; this document specifies how it's built — interfaces, persistence, lifecycle, failure modes, and integration boundaries — so an engineer can read the code and understand both layers.*

**Audience:** engineers building, extending, or operating Numel's Proactive substrate.
**Prerequisites:** familiarity with `proactive.md` (the conceptual blueprint), Python 3.12, the workflow `transform_flow` model.
**Companion to:** `examples/proactive-CHANGELOG.md` (per-commit registry of changes since 2026-04-28) and `docs/transform-flow-scripts.md` (the in-repo reference for inline-script semantics).

---

## 1. Overview & Architecture

The Proactive substrate is a Python module tree under `app/proactive/` plus a set of HTTP endpoints in `app/api.py` plus a sidebar surface in `web/numel-proactive-vitals.js`. The implementation follows two rules:

* **Substrate logic lives in real Python modules.** Workflow `transform_flow` scripts are thin shims that import and call into the modules. Recursion, helpers, comprehensions referencing top-level names, and other engine-style-`exec` hazards (see `docs/transform-flow-scripts.md`) work normally inside the modules and never appear inline.
* **Persistence is a single layer.** Every component uses `proactive.persistence` for JSON and JSONL I/O. The state directory is one filesystem location resolved at runtime from `NUMEL_PROACTIVE_DIR` or defaulted to `app/storage/proactive/`. Tests, sandboxes, and integration smokes flip the env var to isolate state.

### 1.1 Component map

```
app/proactive/
  persistence.py    M3.1 — atomic JSON / append-only JSONL primitives, state_dir()
  middleware.py     M3.2 — Veracity / Privacy / Adversarial gates
  quarantine.py     M3.4 — failure tracker + filesystem snapshots
  evolution.py      M4.1 — feedback signals, User Constitution, validator chain
  optimization.py   M4.2 — sandbox + Self-Reflective strategies + simulator
  promotion.py      M4.3 — chained simulate → align → apply with Ledger trace
  mcp.py            M5.1 — MCP server-side export + client-side remote tools
  a2a.py            M5.2 — peer registry + trust tiers + share_state
  transports.py     M5.3 — OpenAI-compat / Anthropic LLM bridges as capabilities

app/api.py          ~40 POST endpoints under /proactive/*
web/numel-proactive-vitals.js  sidebar Vitals panel
web/numel-api.js    NumelAPI helpers for every endpoint
examples/           workflow JSON demos at every Phase
tools/              lint_transforms.py, smoke_proactive.py, git-hooks/
```

### 1.2 Data flow

```
inbound signal
   │
   ▼
Middleware: Veracity → Privacy → Adversarial   (proactive.middleware)
   │
   ▼
World Model write   (proactive.persistence: world_model.json)
   │
   ▼
[Conscious agent reads World Model + Goals, optionally emits intent]
   │
   ▼
Goal Hierarchy lookup    (proactive.persistence: goals.json)
Capability Registry lookup    (proactive.persistence: capabilities.json)
   │
   ▼
Governor: Decide                 (rules in workflow + proactive.quarantine)
   │           │
   │           ├── deny / consent_required / allow
   │
   ▼
Motor: Execute (if allowed) — handler dispatch via proactive.mcp.call_tool
   │
   ▼
Social: Pending Consent (if consent_required)
   │
   ▼
Ledger append   (proactive.persistence: ledger.jsonl)
   │
   ▼
Vitals sweep    (in-memory — recomputed on each /proactive/vitals call)
```

The bus is **the Ledger** (`ledger.jsonl`). Every layer that wants to react to past activity reads the ledger; every layer that wants to publish appends. Reads are cheap (file is normally < a few thousand lines) and we keep the contract additive — new event topics ship with new entries, never schema-breaking changes to existing ones.

---

## 2. Bus & Event Flow

### 2.1 Ledger entry shape

Every entry is a JSON object on a single line in `ledger.jsonl`. Fields are additive — older entries may lack newer fields.

```json
{
  "id":               "led_42",
  "ts":               1777731799.787,
  "trigger":          {"topic": "core.middleware.input_received"},
  "correlation_id":   "corr_a1b2c3d4e5f6",
  "provenance":       [{"stage": "veracity", "ts": 1777..., ...}, ...],
  "world_model_write":{"path": "core.observations.email.5", "revision": 5},
  "relevant_goals":   ["core.demo.standing"],
  "resolved_capability": {"name": "core.notify", "scopes": [...]},
  "governor_verdict": {"decision": "allow", "reason": "...", "scopes": [...], "confidence": 0.85, "capability": "..."},
  "motor_action":     {"id": "act_3", "capability": "core.notify", ...},
  "motor_status":     "executed",
  "social_consent_request": {"id": "consent_2", ...},
  "expected_outcome": "vertical_slice_complete",
  "actual_outcome":   "executed"
}
```

### 2.2 Trigger topics

| Topic | Producer | Notes |
|---|---|---|
| `core.middleware.input_received` | Substrate stub workflow | Inbound webhook signal recorded after Substrate pass-through |
| `core.sensory.observation` | Sensory layer | Structured observation in the World Model |
| `core.motor.action_attempt` | Vertical / agentic slices | Action proposed, may or may not have applied |
| `core.evolution.promotion` | M4.3 promotion gate | Records every `promote()` call regardless of outcome |

Adding a new topic is additive: pick a unique dotted path under your domain (`acme.feature.event_kind`), append entries with that `trigger.topic`, downstream consumers filter by it.

### 2.3 Persistence primitives

`proactive.persistence` provides:

* `state_dir() -> Path` — resolves `NUMEL_PROACTIVE_DIR` or defaults to `<repo>/app/storage/proactive/`. Creates the directory on first call.
* `read_json(name, default=None) -> Any` — reads `<state_dir>/<name>.json`. Returns `default` (or `{}`) on missing/corrupt.
* `write_json(name, data) -> None` — atomic write via `tmp.replace(path)`. Thread-safe via a module-level lock.
* `append_jsonl(name, entry) -> None` — appends one record per line. Thread-safe.
* `read_jsonl(name) -> List[Any]` — reads all records; skips malformed lines silently.
* `clear_state() -> None` — removes top-level files (snapshots/ subdir is preserved by design — operator history outlives test resets).

**Atomic-write semantics:** `write_json` writes to `<name>.json.tmp` first, then renames. On crash mid-write, the previous `<name>.json` is intact; the `.tmp` may be left behind and is overwritten on next write.

**Append semantics:** `append_jsonl` opens in `"a"` mode and writes one `json.dumps(entry) + "\n"`. No locking across processes — multi-process write is **not** supported. Single-process multi-thread is locked.

---

## 3. Substrate Components

### 3.1 Cross-Cutting Middleware (`middleware.py`)

Three pure functions: `veracity_gate(envelope) -> envelope`, `privacy_gate(envelope, policy=None) -> envelope`, `adversarial_gate(envelope) -> envelope`. Each takes a dict and returns a new dict (input is not mutated except for `setdefault('provenance', [])` — see §3.1.4 below).

#### 3.1.1 Veracity Gate

* Adds `correlation_id` (uuid hex prefix) if absent.
* Looks up `source_kind` in `_SOURCE_TRUST` (e.g. `user: 0.95, sensor: 0.85, webhook: 0.70, email: 0.50, default: 0.60`).
* Scans every string in the envelope against `_SUSPICION_PATTERNS` (act-now / wire transfer / click here / verify account / one-time-pin / IRS-tax / urgent…request). Each match deducts 0.10 from confidence (capped 0.40 total).
* Final `confidence` is bounded to `[0, 1]`.
* Appends a provenance entry `{stage: "veracity", source, source_kind, base_trust, suspicion_hits, suspicion_penalty, ts}`.

#### 3.1.2 Privacy Gate

* Walks payload-shaped fields (`payload`, `raw`, `body`, `message`, `observation`).
* Applies seven default redactions: email, SSN, credit card (13–19 digits), phone, IBAN, JWT, common API keys (`sk_…`, `pk_…`, `ghp_…`, `github_pat_…`).
* Per-call `policy` (dict with `redact_email: bool`, etc.) toggles each.
* Counts per-kind hits; appends provenance `{stage: "privacy", redacted: bool, redaction_kinds: {kind: count}, policy}`.

#### 3.1.3 Adversarial-Input Filter

* Pops the first matching key from `("payload", "raw", "body", "message")` and wraps the value as `untrusted_content: {value, is_trusted: False, injection_hits: [...]}`.
* Scans for prompt-injection markers: `ignore previous instructions`, `you are now …`, `system prompt:`, `act as …`, OpenAI chat tokens (`<|im_start|>`, `<|system|>`, `<|user|>`), Llama markers (`[[INST]]`, `<<SYS>>`).
* On any hit, drops `confidence` by 0.30 (floored at 0).
* Appends provenance `{stage: "adversarial", wrapped: True, injection_hits: [...]}`.

#### 3.1.4 Side-effect contract

The three gates **return new envelope dicts** (callers should `output = privacy_gate(env)`, not assume in-place mutation). They DO mutate the inner `provenance` list in place because that's how the chain accumulates the trail across stages. Callers must therefore pass a fresh list (via `setdefault`) on the first stage.

### 3.2 World Model

Single JSON file: `world_model.json`. Shape: a flat dict keyed by dotted-path namespace (`core.public.weather`, `core.observations.email.3`, etc.). Each value is freeform JSON.

* **No schema.** Producers and consumers agree on namespaces by convention. `core.*` is reserved for built-ins.
* **Revisions** are per-path counters maintained by the producer (the substrate's `World Model: Write` transform uses `revision` and bumps on each write).
* **Indexed paths** (`core.observations.email.__index__`) are append-only lists of paths; consumers use them to enumerate without scanning the whole dict.

### 3.3 Goal Hierarchy

Single JSON file: `goals.json`. Shape: `{<goal_id>: {id, tier, title, lifecycle, created_at, ...}}`. Tiers: `Tasks` / `Projects` / `Standing Goals`. Lifecycle: `active` / `paused` / `abandoned` / `done`.

The substrate's `Goal Hierarchy: Lookup` transform attaches `relevant_goals: [id, ...]` to every envelope (currently: all `active` goals; production should filter by domain/tier).

### 3.4 Capability Registry

Single JSON file: `capabilities.json`. Shape: `{<cap_name>: {name, purpose, scopes, latency_tier, cost_estimate, input_schema?, remote?, transport?}}`.

* **Built-in capabilities** are seeded by `mcp._seed_local_capabilities_if_empty()`: `core.notify`, `core.send_email`, `core.transfer_funds` with their respective scope sets.
* **Remote capabilities** (registered via M5.1's `register_remote`) are namespaced `mcp.<server>.<original_name>` and carry a `remote: True` flag plus a `remote_descriptor: {server, original_name, annotations}` block.
* **Transport-bridged capabilities** (M5.3) are namespaced `transport.<kind>.<alias>` and carry a `transport: {alias, kind, base_url, model, api_key_env, ...}` block.

The Substrate's `Capability Registry: Lookup` transform reads this file, resolves an envelope's `intent.capability`, and folds the registered scopes into `env["scopes"]` so the Governor sees a complete picture.

### 3.5 Governor

The Governor decision lives **inline in the workflow's transform_flow** (not in a real Python module — yet). The decision logic is:

```
intent + is_quarantined(cap)              → deny
intent + injection_hits                   → deny
high-stake scope present                  → consent_required
write scope + confidence < 0.85           → consent_required
intent + confidence < 0.40                → consent_required
otherwise                                  → allow
```

After every verdict, the Governor calls into `proactive.quarantine`:

* `record_failure(cap)` on `deny` (so repeated denies eventually trip the quarantine flag).
* `record_success(cap)` on `allow` (clears the failure history but does not auto-release a quarantined key).

Promoting the Governor itself to `app/proactive/governor.py` is left as a future refactor; it's the smallest module that will eventually carry budget enforcement and attention-throttling.

### 3.6 Vitals

Computed lazily on every `POST /proactive/vitals`. Reads `ledger.jsonl`, buckets entries by `trigger.topic`, counts per-decision and per-motor-status outcomes, computes mean pipeline latency from the per-stage provenance timestamps. Returns:

```json
{
  "updated_at":             1777...,
  "state_dir":              "<absolute path>",
  "ledger_count":           N,
  "trigger_topics":         {"core.sensory.observation": x, "core.motor.action_attempt": y, ...},
  "governor_decisions":     {"allow": ..., "consent_required": ..., "deny": ...},
  "motor_status_counts":    {"executed": ..., "deferred_to_social": ..., ...},
  "injection_hits_total":   z,
  "consent_pending":        c,
  "avg_pipeline_latency_s": f
}
```

---

## 4. Agent Layer Contracts

The four layers are conventions, not enforced contracts. Each layer is a `transform_flow` script in a workflow JSON. Their interaction model:

| Layer | Reads | Writes | Where it lives |
|---|---|---|---|
| **Sensory** | external sources, World Model | World Model namespaces under its domain | upstream of Middleware |
| **Motor** | resolved_capability, governor_verdict | actions log, MCP handler invocations | downstream of Governor |
| **Social** | governor_verdict (consent_required) | pending_consents | downstream of Motor |
| **Conscious** | World Model, Goals, Vitals | re-emits envelopes with `intent` set | mid-pipeline (Probe-Sensory back-edge) |

Contracts:

* Sensory must run its outputs through Middleware before reaching the World Model — the substrate enforces this by topology, not by check.
* Motor must consult `governor_verdict.decision` before acting — execution on `consent_required` is forbidden by convention.
* Social must record a `pending_consents` entry for every `consent_required` it sees that has an `intent` — otherwise the user has no surface to approve from.
* Conscious-emitted intents must carry a `capability` field that exists in the Capability Registry — otherwise downstream resolution will fail.

For LLM-backed Conscious reasoning the canonical pattern since M5.4 is to wire an `agent_flow` node into the Conscious slot — every turn auto-registers as `agent.<id>` in the Capability Registry and runs through the same Adversarial → Alignment → handler → Privacy chain as any other capability, with no extra setup. The legacy pattern, where a `transform_flow` calls `proactive.transports.call_transport(alias, prompt, dry_run=True)`, is preserved in `examples/proactive-vertical-slice-agentic.json` as the **offline / dry-run** variant — useful when you don't have a model backend running, but no longer the recommended path for real workflows.

---

## 5. Lifecycle: Evolution

### 5.1 Phase 1 — Alignment (`evolution.py`)

* `record_feedback(target_id, kind, value, context)` appends to `alignment_signals.jsonl`. Three valid `kind` values: `thumbs` / `edit` / `preference`.
* `read_constitution() / update_constitution(patch)` maintain `user_constitution.json`. Patches merge `preferences` by key, append `rules` idempotently by id, replace other top-level keys, bump `version`.
* `register_validator(name, fn) / unregister_validator / list_validators` maintain a process-local registry of `(candidate) -> Verdict`.
* `run_alignment(candidate) -> {decision, verdicts, ts, candidate}` runs every registered validator. Aggregate is `pass` only if every validator passed; any veto produces a veto with the full per-validator trail.

Built-in validators (auto-registered on import):
* `recent_thumbs_down` — vetoes if a non-`constitution_rule_add` candidate's capability has ≥3 recent thumbs-down signals. Skips `constitution_rule_add` (banning a downvoted cap aligns with the user signal).
* `constitution_check` — vetoes if a non-governance candidate's capability matches a `{kind: "never", target: <cap>}` rule. Skips `constitution_rule_*` (governance actions manage rules, can't self-loop).

Validator exceptions are caught and converted to `veto` so a buggy plugin can't silently approve.

### 5.2 Phase 2 — Optimization (`optimization.py`)

* `sandbox(seed_files=...)` is a context manager that flips `NUMEL_PROACTIVE_DIR` to a temp directory for its lifetime. Anything `proactive.persistence.*` writes inside the block is local; the temp dir is removed on exit.
* `propose_from_state() -> [candidate, ...]` runs three built-in strategies:
  * `tighten_governor` — capabilities with ≥50% deny verdicts over ≥4 samples → propose `constitution_rule_add` (`{kind: "never", target: <cap>}`).
  * `prune_quarantine` — currently-quarantined capabilities with ≥5 recorded failures → propose the same hard-ban rule.
  * `relax_constitution` — banned capabilities with ≥3 thumbs-up signals → propose `constitution_rule_remove`.
* `simulate_candidate(candidate, ledger=None, signals=None)` dispatches by `candidate.kind`; for `constitution_rule_add` it counts how many ledger entries on that capability would have flipped to `deny`; for `constitution_rule_remove` it reports how many past denies could relax + thumbs-up backing the proposal.

Tunable thresholds live as module constants (`_DENY_RATE_THRESHOLD = 0.50`, `_DENY_MIN_SAMPLES = 4`, `_QUARANTINE_FAILURE_FLOOR = 5`, `_THUMBS_UP_TO_RELAX = 3`).

### 5.3 Phase 3 — Promotion (`promotion.py`)

Single entry point: `promote(candidate, *, simulate=True)`. Walks:

1. Optional `simulate_candidate` (M4.2).
2. `run_alignment(candidate)` (M4.1).
3. If aligned, dispatch to a registered applier; otherwise refuse.
4. Append a structured `core.evolution.promotion` Ledger entry capturing the full Why-chain.

Five terminal `decision` states: `applied` / `noop` / `refused_by_validator` / `skipped_unknown_kind` / `apply_failed`.

Pluggable appliers via `register_applier(kind, fn)`. Two built-ins:

* `constitution_rule_add` — idempotent: returns `noop` if a rule with the same `(kind, target)` already exists.
* `constitution_rule_remove` — calls `evolution.remove_rule`; returns `noop` if not present.

Adding a new candidate kind is a `register_applier("my_kind", fn)` away — the applier returns `{status: "applied"|"noop"|"failed", ...}` and the gate handles the rest.

---

## 6. Operational Mechanics

### 6.1 Consent flow

When the Governor returns `consent_required` and the envelope has an `intent`, the Social layer records a `pending_consents` entry: `{id, capability, rationale, correlation_id, requested_at, status: "awaiting_user"}`. The user surface (Vitals UI today; the assistant console tomorrow) presents these to the operator. Approval is **not yet wired** — the `awaiting_user` records sit until cleaned up. Adding approval is a future commit: a `POST /proactive/social/consent/{id}/{approve|reject}` endpoint that writes back into the workflow's variables, with a Ledger record of the human decision.

### 6.2 Quarantine + Snapshots (`quarantine.py`)

* `record_failure(key, *, reason, threshold=3, window_s=600)` — rolling-window failure tracker. After `threshold` failures within `window_s` seconds, sets `quarantined: True`.
* `record_success(key)` — clears the failure history but does not release.
* `release(key, reason)` — explicit release (operator-only).
* `is_quarantined(key)` — Governor consults this before deciding.
* `take_snapshot(label)` / `list_snapshots()` / `restore_snapshot(id)` / `delete_snapshot(id)` — filesystem snapshots of the entire state directory (excluding the `snapshots/` subdir itself). Each snapshot is a directory under `app/storage/proactive/snapshots/<id>/` with copies of every top-level state file plus a `manifest.json`.

### 6.3 Audit trail

Every operator-facing surface ends in the Ledger. Inspect via:

* UI: Vitals sidebar → Recent ledger entries → click a row to open the Why-chain modal.
* HTTP: `POST /proactive/ledger {limit, since_id}`.
* Disk: `tail -f app/storage/proactive/ledger.jsonl | python -m json.tool`.

For promotion-specific entries: `grep '"core.evolution.promotion"' app/storage/proactive/ledger.jsonl`.

---

## 7. Storage & Persistence

### 7.1 File inventory

Under `app/storage/proactive/` (or `$NUMEL_PROACTIVE_DIR`):

| File | Producer | Notes |
|---|---|---|
| `world_model.json` | Substrate | Atomic snapshot per write |
| `goals.json` | Substrate / operator | Atomic snapshot per mutation |
| `capabilities.json` | Substrate / `mcp.register_remote` / `transports.register_transport` | Atomic snapshot per mutation |
| `ledger.jsonl` | Substrate / `promotion.promote` / others | Append-only |
| `quarantine.json` | `quarantine.record_failure` / `release` | Atomic snapshot per change |
| Vitals | n/a | Computed lazily — never persisted |
| `alignment_signals.jsonl` | `evolution.record_feedback` | Append-only |
| `user_constitution.json` | `evolution.update_constitution` | Atomic snapshot per patch; version bumps |
| `mcp_remote_tools.json` | `mcp.register_remote` | Mirror of remote-tool registry |
| `mcp_calls.jsonl` | `mcp.call_tool` | Append-only |
| `a2a_peers.json` | `a2a.register_peer` | |
| `a2a_inbox.jsonl` / `a2a_outbox.jsonl` / `a2a_shared.jsonl` | `a2a.receive` / `send` / `share_state` | Append-only |
| `transport_configs.json` | `transports.register_transport` | API keys are NOT here — resolved from env at call time |
| `transport_calls.jsonl` | `transports.call_transport` | Append-only |
| `snapshots/<id>/` | `quarantine.take_snapshot` | Each snapshot is a sibling directory containing copies + a manifest |

### 7.2 Retention

Currently no automatic retention. JSONL files grow unbounded. For production:

* `ledger.jsonl` — needs a rotation/archival strategy (copy to cold storage at N entries, truncate, keep a pointer).
* Append-only logs (`alignment_signals.jsonl`, `mcp_calls.jsonl`, etc.) — same.
* Snapshots — operator-driven cleanup via `delete_snapshot` already exists.

### 7.3 Migration

State files are versioned implicitly by their schema. The Constitution file has an explicit `version` integer. Adding a new field is additive. Removing a field requires a migration script in a new module — not yet provided.

---

## 8. Concurrency, Failure Modes, Idempotency

### 8.1 Concurrency assumptions

* **Single process, multi-thread** — the persistence module locks correctly for this case.
* **Multi-process** — not supported. The atomic-write rename plus append-mode writes happen to be ordered correctly under POSIX with single writers, but there's no cross-process coordination. Don't run two app instances against the same `NUMEL_PROACTIVE_DIR`.

### 8.2 Idempotency

The four critical "apply" paths are idempotent by design:

* `constitution_rule_add` — `noop` if a rule with the same `(kind, target)` already exists.
* `constitution_rule_remove` — `noop` if the rule is gone.
* `quarantine.release` — returns `False` (not raise) on un-quarantined keys.
* `mcp.drop_remote` / `transports.drop_transport` / `a2a.drop_peer` — same.

### 8.3 Failure modes

| Failure | Impact | Recovery |
|---|---|---|
| Disk full mid-write | `write_json` raises `OSError` to caller; `.tmp` file may persist | Free disk, retry. Live `<name>.json` is unchanged from the previous successful write. |
| Disk full mid-append | `append_jsonl` raises; partial line may be on disk | `read_jsonl` skips malformed lines silently. Manual `tail` cleanup if you want a clean file. |
| Corrupt JSON | `read_json` returns `default` (or `{}`) — never raises | Investigate via filesystem; restore via snapshot. |
| Quarantine sticks | Rolling window prevents stale failures from blocking forever — they age out after `window_s` | Or `release(key)` explicitly. |
| Validator raises | Exception is caught; converted to `veto` with the message | Buggy plugin can never silently approve. |
| Applier raises | Exception caught; `decision = "apply_failed"` with detail | Operator inspects the Ledger entry. |
| Subprocess (integration test) hangs | `subprocess.terminate()` then `wait(timeout=10)` then `kill()` | Tempdir cleaned up in `finally` regardless. |

### 8.4 Test isolation

* The `proactive.optimization.sandbox()` context manager flips `NUMEL_PROACTIVE_DIR` to a temp directory and restores it on exit. Use this for any test that mutates state.
* `tools/smoke_proactive.py` clears `state_dir()` and removes `snapshots/` before and after each Phase check. Tests that share an interpreter must not interleave.

---

## 9. Extension Surface

The substrate is designed to grow without forking. Stable extension points:

* **New Alignment validator** — `register_validator(name, fn)` where `fn(candidate) -> Verdict`. Veto exceptions auto-handled.
* **New applier kind** — `promotion.register_applier(kind, fn)` where `fn(candidate) -> {status, ...}`.
* **New optimization strategy** — write a function that scans live state and emits candidates; call from `propose_from_state` (or your own propose endpoint).
* **New MCP tool handler** — `mcp.register_handler(cap_name, fn)` where `fn(args) -> result`.
* **New trust tier** — extend `a2a.VALID_TIERS` and `_can_read_namespace`. Tier name is opaque to the rest of the system.
* **New transport flavour** — extend `transports.VALID_KINDS` plus a `_build_<kind>_request` and `_extract_<kind>_text` pair.
* **New ledger trigger topic** — pick a unique dotted path; producers append, consumers filter on it.

A complete formal extension model (manifest schema, semver rules, lifecycle stages, federation transports) is deferred to a separate spec when the surface is stable enough to warrant the constraint.

---

## 10. Appendices

### A. Minimal end-to-end example

```python
# In a Python shell with `app/` on the path
from proactive.persistence import clear_state
from proactive import evolution as ev, optimization as opt, promotion as pr

clear_state()

# Alignment: explicit feedback
ev.record_feedback("led_42", "thumbs", "down", {"capability": "core.transfer_funds"})

# Constitution: ban a capability
ev.update_constitution({"rules": [{"kind": "never", "target": "core.transfer_funds"}]})

# Optimization: a strategy emits a candidate
candidates = opt.propose_from_state()        # might be empty unless thresholds tripped
print(candidates)

# Promotion: a manually-constructed candidate flows through the gate
result = pr.promote({
    "kind":      "constitution_rule_add",
    "target":    "core.notify",
    "payload":   {"rule": {"kind": "never", "target": "core.notify"}},
    "rationale": "operator-initiated lock",
})
print(result["decision"])     # "applied"
```

### B. Runbook: regression-testing the substrate

```bash
PY=/c/devel/numel-playground/.venv/Scripts/python.exe

# 1. Lint every workflow for split-namespace exec hazards.
$PY tools/lint_transforms.py

# 2. In-process smoke (Phase 1-5, ~3 s).
$PY tools/smoke_proactive.py -v

# 3. Full integration (spawns app/app.py, exercises HTTP endpoints, ~30 s cold).
$PY tools/smoke_proactive.py --integration -v
```

Expected: lint clean, all 11 smoke checks pass.

### C. Runbook: clean-slate recovery

```bash
# Reset all live state, keeping snapshots.
$PY -c "import sys, shutil; sys.path.insert(0,'app'); from proactive.persistence import clear_state; clear_state(); print('clean')"

# Reset everything including snapshot history.
$PY -c "import sys, shutil; sys.path.insert(0,'app'); from proactive.persistence import clear_state, state_dir; clear_state(); shutil.rmtree(state_dir()/'snapshots', ignore_errors=True); print('full reset')"
```

### D. Module dependency graph (top-down)

```
api.py / numel-proactive-vitals.js
   │
   ├── promotion.py
   │      ├── evolution.py
   │      ├── optimization.py
   │      └── persistence.py
   ├── optimization.py
   │      ├── evolution.py
   │      ├── quarantine.py
   │      └── persistence.py
   ├── evolution.py
   │      └── persistence.py
   ├── quarantine.py
   │      └── persistence.py
   ├── mcp.py
   │      ├── evolution.py
   │      ├── middleware.py
   │      └── persistence.py
   ├── a2a.py
   │      ├── middleware.py
   │      └── persistence.py
   ├── transports.py
   │      ├── mcp.py
   │      └── persistence.py
   ├── middleware.py    (no internal dependencies)
   └── persistence.py   (no internal dependencies)
```

`persistence.py` is the only module with no internal dependencies. Every other module imports it; everything else stacks on top.

---

**End.** Companion to the blueprint at [proactive.md](proactive.md) (v3+). Generated and maintained alongside the implementation; [`examples/proactive-CHANGELOG.md`](../examples/proactive-CHANGELOG.md) is the per-commit registry of what changed and why.
