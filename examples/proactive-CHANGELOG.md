# Claude Changelog — Numel Playground

A registry of substantive changes Claude has made to this codebase, starting **2026-04-28**.

The focus is the **Proactive Agent Ecology** work, but the document also lists collateral edits made during the same sessions so reviewers and testers know the full surface to look at. Earlier history (before 2026-04-28) is in the git log.

> Format conventions: one date header per day; within a day, group by area; each line is a brief WHAT + (optional) WHY. File paths in backticks. Branch names in italics.

---

## 2026-04-28

### Proactive System (focus)

#### Documentation
- `~/Desktop/proactive.md` — redrafted from v1 (actor-only) → v2 (technical-leaning) → v3 (chained Evolution + Extension Model). User then refined v3 to a cleanly conceptual register; the technical specification was deferred to a separate companion document (TBD, scoped against the same v3).

#### Workflows
- `examples/proactive-substrate-stub.json` — **created.** Substrate-only scaffold. 13 nodes initially: webhook → Middleware (Veracity / Privacy / Adversarial) → World Model write → Governor → Ledger → preview. Each Substrate component is a `transform_flow` Python stub holding shared state in `variables`.
- `examples/proactive-sensory-slice.json` — **created.** First Sensory layer plug-in: timer-driven synthetic inbox + Sensory structuring stage upstream of the same Substrate pipeline. Demonstrates the Sensory contract (one transform per stage, observation envelope into Middleware).
- `examples/proactive-substrate-stub.json` — **expanded (Phase 1).** Added §3.3 Goal Hierarchy stub (lazy-seeded Standing Goal + active-goals lookup), §3.4 Capability Registry stub (built-in catalog `core.notify` / `core.send_email` / `core.transfer_funds` with declared scopes; folds `intent.capability` scopes into `env["scopes"]`), §3.6 Vitals stub (rolling Ledger sweep). Now 16 nodes / 26 edges.
- `examples/proactive-sensory-slice.json` — **expanded (Phase 1).** Same three new Substrate stages added so the slice stays in topological parity with the substrate scaffold. Now 18 nodes / 30 edges.
- Smoke tests confirmed: Capability Registry correctly folds `core.transfer_funds` scopes → Governor flips to `consent_required`; Vitals counts `allow:3 / consent_required:1` after four substrate signals.

#### Branch Lifecycle
- Created *proactive/substrate-stub*, *proactive/sensory-slice*, *testing/proactive-full* (initial naming experiment).
- User flagged "too many branches"; collapsed all three into a single *proactive* branch on top of `main`.
- Pushed to `origin/proactive`.

### Frontend — Console (collateral)

- AbortError suppression on the assistant console: window-level `unhandledrejection` listener guards against `BodyStreamBuffer` aborts surfacing in DevTools. Files: `web/numel-console.js`, `web/numel-agent-chat.js`.
- "Stopping agent…" / "Agent stopped." status messages now use a dedicated **STATUS** message role with amber styling, matching the assistant console pattern.
- Stop button in agent chat repositioned next to the send button, restyled as a 32×32 red square with a `pulse` animation while the run is active.
- **Model selection redesigned** to match the `ModelConfig` node pattern: replaced the hardcoded `<select>` with a paired `consoleModelSource` + `consoleModelName` dropdown driven by `/options/model_sources` and `/options/model_names`. Selection is cached in `localStorage` (`numel_console_model_v1`), seeded with sensible fallbacks before the API resolves, and shows a CSS spinner over the chevron while loading. Files: `web/index.html`, `web/numel-console.css`, `web/numel-console.js`.

### Frontend — Workflow UI (collateral)

- "Run" sub-panel: the **Advanced** subsection was a custom button + chevron; restyled to use the same `nw-collapsible nw-subsection nw-subsection-clean` pattern as the **Options** subsection in the same panel, so both subsections feel identical.
- Generic collapsible click handler now honors `data-persist-key` on the header — any subsection that opts in gets its open/closed state persisted in `localStorage` automatically. The Run > Advanced subsection uses `data-persist-key="numel_run_advanced_v1"`. Removed unused `.nw-run-advanced-*` CSS classes.

### Backend (collateral)

- `app/manager.py`: narrowed `except BaseException` → `except Exception` in `_serve_agent_server` (don't swallow `KeyboardInterrupt`/`SystemExit`); raised default `_wait_for_agent_servers` timeout from 2 s → 5 s and made `impl()` accept `startup_timeout_s` kwarg; fixed `get()` so the missing-name path emits the `MANAGER_WORKFLOW_GOT` event consistently with other branches.
- `app/platform_local/docker_runtime.py`: dropped Pydantic v1 `parse_obj` / `Workflow(**payload)` fallbacks (Pydantic v2-only codebase); fixed `cancel_execution` so it returns `False` on terminal records instead of always returning `True` (`return cancelled or True` was dead code); enforced `runtime.max_execution_duration_seconds` inside `_monitor_execution` with cancellation; added `_prune_retained_execution_roots` (mirrors prod's time-gated pattern) and called it on monitor finalize; added `aclose()` to cancel pending monitor tasks at shutdown; clarified the `AssetKind.OTHER` acceptance branch with an inline comment.
- `app/platform_prod/docker_runtime.py`: replaced `json.loads(json.dumps(spec))` with `copy.deepcopy(spec)` in `_redacted_container_spec`; `_request` now truncates response body to 512 chars and attaches `status_code` to the raised `RuntimeError`; `_load_outputs_payload` and `_load_status` now log parse/IO failures via `log_print` instead of silently returning `{}`.

### Docker (collateral)

- `Dockerfile` (root): replaced `pip install -e ".[all]" 2>/dev/null || pip install -e . || true` with a single `pip install -e .` (no `[all]` extra is defined; the `|| true` was masking real install failures).
- `app/platform_prod/deploy/runtime-builder.sh`: added `trap 'rm -f "$TMP_STAMP"' EXIT` so the hash stamp file no longer leaks in `/tmp` when `docker build` fails.
- Audit notes (no auto-change): `app/platform_prod/deploy/docker-compose.prod.yml` exposes Docker-in-Docker on `tcp://0.0.0.0:2375` with `--tls=false` — flagged as a deployment decision, not changed because TLS migration needs cert infrastructure.

### Proactive System — Phase 2 (vertical slice)

- `examples/proactive-vertical-slice.json` — **created.** End-to-end demo of all four agent layers over the Substrate. 22 nodes / 38 edges. Topology: `Sensor → Sensory:Structure → Veracity → Privacy → Adversarial → World Model:Observe → Ledger:Observation → Conscious:Anticipate → Goal Hierarchy → Capability Registry → Governor → Motor → Social → Ledger:Action → Vitals → Preview → loop`.
- **Conscious — Anticipatory slice** (§10): reads the latest observation from the World Model and maps subject keywords to capabilities (`wire`/`urgent`/`transfer` → `core.transfer_funds`; `calendar`/`meeting`/`reminder` → `core.notify`). Demonstrates the back-edge from Conscious into the Substrate via re-emitted intent envelopes.
- **Motor — Operative slice** (§8): executes the resolved capability when Governor verdict is `allow`; sets `motor_status="deferred_to_social"` on `consent_required`; no-op when there's no intent. Records executed actions in `variables["actions"]`.
- **Social — Clarification slice** (§9): when Governor demands consent, records a pending request in `variables["pending_consents"]` with rationale + correlation_id + `awaiting_user` status. Phase 3 will surface this in the assistant console (`AssistantApprovalRuntimeConfig`) and route the verdict back to the Governor.
- **Vitals** updated to bucket by trigger topic — observations (no Governor verdict) no longer pollute `governor_decisions` counts. New fields: `observation_count`, `action_attempt_count`, `motor_status_counts`.
- Smoke test (5 ticks): 5 observations recorded; Conscious emitted 2 intents; Motor executed 1 (`core.notify`, allowed); Social parked 1 (`core.transfer_funds`, consent_required). Vitals buckets: `{allow:1, consent_required:1}`, `motor_states={executed:1, deferred_to_social:1}`.

### Process

- `examples/proactive-CHANGELOG.md` — **created** (this file). Living registry of Claude's edits to the codebase from 2026-04-28 onward, requested by the user during Phase 2.

### Proactive System — Phase 3 (M3.1 substrate hardening: persistence)

- `app/proactive/__init__.py` — **new package** holding Substrate runtime support code that workflow `transform_flow` scripts import (kept separate from the `examples/` workflow JSONs).
- `app/proactive/persistence.py` — **created.** JSON-backed durable storage for the substrate. API: `state_dir()`, `read_json(name, default)`, `write_json(name, data)`, `append_jsonl(name, entry)`, `read_jsonl(name)`, `clear_state()`. Atomic writes via tempfile rename; thread-safe via module-level lock. State directory resolves from `NUMEL_PROACTIVE_DIR` env var or defaults to `app/storage/proactive/` (already gitignored under the global `storage/` rule). Files used by the persistent workflow: `goals.json`, `capabilities.json`, `world_model.json`, `ledger.jsonl`.
- `examples/proactive-substrate-persistent.json` — **created.** Phase 3 variant of the substrate stub. Identical 16-node topology to `proactive-substrate-stub.json`, but every stateful component (Goal Hierarchy, Capability Registry, World Model, Ledger, Vitals) reads from / writes to `proactive.persistence` instead of `variables`. Lazy-load pattern: each transform reads from disk on first access, caches in `variables` for the rest of the run, writes back on mutation.
- Smoke test verified state survives a "workflow restart" — two sequential runs with a fresh `variables` dict each time but a shared on-disk state directory: RUN 1 (3 signals) → ledger `[led_1, led_2, led_3]`, world_model rev=3; RUN 2 (2 signals, fresh `variables`) → ledger continues at `led_4`, `led_5`, world_model rev=5. Goals + capabilities loaded from disk in RUN 2 without re-seeding.
- Phase 1/2 in-memory workflows (`proactive-substrate-stub.json`, `proactive-sensory-slice.json`, `proactive-vertical-slice.json`) **kept unchanged** so the lighter-weight demos still run without a writable state dir.
- Remaining Phase 3 milestones (M3.2 real Middleware, M3.3 Vitals UI surface, M3.4 Quarantine + branch-restore) are **not yet implemented**; this commit covers M3.1 only.

### Proactive System — Phase 3 (M3.2 substrate hardening: real Middleware)

- `app/proactive/middleware.py` — **created.** Replaces the placeholder middleware logic with real heuristics.
  - **Veracity Gate** — per-source trust priors (`user`/`internal`: 0.95, `sensor`: 0.85, `webhook`: 0.70, `channel`: 0.60, `email`: 0.50) plus a regex-based suspicion scanner (act-now, wire-transfer, click-here, verify-account, one-time-pin, IRS/tax-debt, urgent…request). Each match deducts 0.10 (capped at 0.40) from confidence.
  - **Privacy / Redaction Gate** — policy-driven multi-pattern redactor: email, SSN, credit card, phone, IBAN, JWT, common API key formats (`sk_…`, `pk_…`, `ghp_…`, `github_pat_…`). Reports per-kind counts in provenance.
  - **Adversarial-Input Filter** — typed envelope: `{value, is_trusted=False, injection_hits}`. Scans for ignore-previous-instructions, you-are-now-X, system-prompt-style markers, OpenAI/Llama chat tokens (`<|im_start|>`, `<|system|>`, `[[INST]]`, etc.). Confidence drops 0.30 on any hit.
- `examples/proactive-substrate-persistent.json` — **updated.** Three middleware transforms shrunk from 20+ inline lines to thin shims (`from proactive.middleware import veracity_gate; output = veracity_gate(env)`). Description reflects M3.1 + M3.2.
- **Governor coordination** (still inline in the workflow): added two rules over the Phase-1 stub — `intent + injection_hits → deny` (untrusted-source actuation refused, per §6 operational table) and `intent + confidence < 0.40 → consent_required`. Promoting Governor itself to a module is M3.5.
- End-to-end smoke test (7 signals): clean observations → `allow`; PII → redacted, still `allow`; social-engineering email + `send_email` intent → `consent_required` (high-stake scope); prompt-injected `notify` intent → **`deny`** (adversarial actuation refused); clean `notify` → `allow`; clean `transfer_funds` → `consent_required`. Verdict matrix matches the spec table verbatim.

### Proactive System — Phase 3 (M3.3 substrate hardening: Vitals UI)

- `app/api.py` — **two new POST endpoints** wired into the existing FastAPI router (after the `/options/{provider_key}` block, following the project-wide POST-only convention):
  - `POST /proactive/vitals` — reads `app/storage/proactive/ledger.jsonl`, returns aggregates: `ledger_count`, `trigger_topics`, `governor_decisions`, `motor_status_counts`, `injection_hits_total`, `consent_pending`, `avg_pipeline_latency_s`, plus the resolved `state_dir` for diagnostics.
  - `POST /proactive/ledger` — body `{limit?: int (default 25, capped 500), since_id?: str}` returns the most recent N entries (most-recent-first); `since_id` cuts off everything up to and including that id for incremental polling.
- `web/numel-api.js` — added `proactiveVitals()` and `proactiveLedger(opts)` helpers on `NumelAPI`.
- `web/index.html` — new sidebar `<section id="proactiveVitalsSection">` between Activity and Experimental: title row with a heartbeat icon + last-update timestamp; auto-refresh toggle (persisted in `localStorage` under `numel_proactive_vitals_auto_v1`); manual Refresh button; 12-cell stat grid; recent-entries list. `numel-proactive-vitals.js` script include added before `numel-file-upload.js`.
- `web/numel-proactive-vitals.js` — **created.** `ProactiveVitalsPanel` class polls both endpoints in parallel every 5 s while the section is expanded; pauses polling when the section is collapsed (via `MutationObserver` on the section's class list) so it doesn't spam the backend. Stat cells colour-coded (`good`/`warn`/`bad`) for allow/consent/deny + pending consents + injection hits. Each ledger row renders id · verdict · topic + observation/intent/motor/confidence inline. Errors fall back to a single inline message instead of breaking the panel.
- `web/numel-workflow.css` — added `~80 lines` for `.nw-vitals-stats` (3-col grid), `.nw-vitals-cell` (good/warn/bad variants), `.nw-vitals-ledger-row` (id/verdict/topic columns), `.nw-vitals-empty` / `.nw-vitals-error`. Anchored above the existing event-log block.
- `web/numel-workflow-ui.js` — instantiates `new ProactiveVitalsPanel(api)` during `connect()`, after `GalleryManager`. Failure is non-fatal (`console.warn` + skip).
- Smoke test against a populated ledger (5 signals through the persistent workflow): vitals endpoint returned `{ledger_count:5, governor_decisions:{allow:3, consent_required:1, deny:1}, injection_hits_total:1}`; ledger endpoint returned the most-recent-first entries with verdict + confidence visible. JS and Python syntax validated.

### Proactive System — Phase 3 (M3.4 substrate hardening: Quarantine + Snapshots)

- `app/proactive/quarantine.py` — **created.** Two co-located concerns (both operator-facing recovery mechanisms):
  - **Quarantine** — per-key (capability) failure tracker with rolling window (default `threshold=3`, `window_s=600`). API: `is_quarantined(key)`, `record_failure(key, reason, threshold, window_s)`, `record_success(key)` (clears failure history but does NOT auto-release), `release(key, reason)`, `list_keys()`. State persisted to `quarantine.json`.
  - **Snapshots** — filesystem snapshots of the entire substrate state directory (excluding `snapshots/` itself). API: `take_snapshot(label)`, `list_snapshots()` (newest first), `restore_snapshot(id)`, `delete_snapshot(id)`. Each snapshot is a directory under `app/storage/proactive/snapshots/<snap_id>/` with copies of every top-level state file plus a `manifest.json` describing the contents.
- `examples/proactive-substrate-persistent.json` — **Governor transform updated** to consult quarantine and record failures/successes. New rule order: (a) `intent + quarantined(cap) → deny`, (b) `intent + injection_hits → deny`, (c) high-stake → consent, (d) write+lowconf → consent, (e) intent+verylowconf → consent, else allow. After deny on an intent: `record_failure(cap)`. After allow on an intent: `record_success(cap)`. Verdict shape extended with `capability` field.
- `app/api.py` — **six new POST endpoints**:
  - `POST /proactive/quarantine` → list keys
  - `POST /proactive/quarantine/release` (body `{key, reason?}`) → release a quarantined key
  - `POST /proactive/snapshots` → list manifests (newest first)
  - `POST /proactive/snapshot/take` (body `{label?}`) → take a new snapshot
  - `POST /proactive/snapshot/restore` (body `{snapshot_id}`) → restore live state from a snapshot
  - `POST /proactive/snapshot/delete` (body `{snapshot_id}`) → delete a snapshot dir
- `web/numel-api.js` — added `proactiveQuarantine()`, `proactiveQuarantineRelease(key, reason)`, `proactiveSnapshots()`, `proactiveSnapshotTake(label)`, `proactiveSnapshotRestore(id)`, `proactiveSnapshotDelete(id)`.
- `web/index.html` + `web/numel-proactive-vitals.js` + `web/numel-workflow.css` — extended the Vitals panel with two subsections:
  - **Quarantine** — one row per quarantined key (key + reason + Release button).
  - **Snapshots** — header has a label input + "Snapshot" button; list shows id + created-at + label + file count, each row with Restore / Delete actions. Restore + delete are gated by a `confirm()` prompt.
- End-to-end smoke test: 4 successive prompt-injected `core.notify` intents → attempts 1–2 deny + accumulating failures, attempt 3 trips quarantine, attempt 4 verdict reason changes from "adversarial input" to "capability 'core.notify' is quarantined". Snapshot taken, captures the bad state. Manual release → next clean intent allowed. Snapshot restore reinstates the quarantined state (`is_quarantined("core.notify") == True` again). Snapshot list/delete operations confirmed.

### Phase 3 status

All four hardening milestones complete:
| Milestone | Commit | Surface |
|---|---|---|
| M3.1 Persistence            | `db507a9` | `app/proactive/persistence.py` + `proactive-substrate-persistent.json` |
| M3.2 Real Middleware        | `1cb8419` | `app/proactive/middleware.py` (Veracity / Privacy / Adversarial heuristics) |
| M3.3 Vitals UI surface      | `12f03bc` | `app/api.py` `/proactive/vitals|/ledger` + sidebar panel |
| M3.4 Quarantine + Rollback  | `d649b66` | `app/proactive/quarantine.py` + 6 endpoints + Vitals subsections |

### Bug fixes (Phase 1/2/3 workflows — split-namespace `exec` compatibility)

- **Root cause.** `app/nodes.py:295` runs every `transform_flow` script via `exec(script, None, local_vars)` — Python's two-namespace mode where script-local names (`def`'d functions, top-level constants) live in `local_vars` but inside-function lookups go through the **module globals** (= `nodes.py`'s) instead. Any function-to-function reference, recursive function, or generator-expression body that references a top-level name from the script fails with `NameError`.
- **Visible symptom** (reported during integration testing): running `proactive-substrate-stub.json` in the actual engine — `Node 7 failed: name '_walk' is not defined` (the recursive `_walk` inside the inline Privacy gate).
- **Fix in three Phase 1/2 workflows** (`proactive-substrate-stub.json`, `proactive-sensory-slice.json`, `proactive-vertical-slice.json`): rewrote the inline Privacy transform with **all logic at top level** — pre-compiled regexes (`EMAIL`, `SSN`, `CARD`) referenced from a top-level `while`-loop walking an explicit stack of `(parent, key)` targets. No nested function defs.
- **Fix in all four Governor transforms** (above three plus `proactive-substrate-persistent.json`): the existing `any(s in HIGH_STAKE for s in scopes)` and `any(s in WRITE for s in scopes)` patterns were generator expressions whose body looked up `HIGH_STAKE` / `WRITE` against the engine's module globals (= not visible). Replaced with an explicit `for s in scopes:` loop that sets `has_high` / `has_write` booleans.
- **Verification.** All four workflows now run end-to-end under the engine's `exec(script, None, locals)` mode. Verdict matrix re-confirmed: `allow / allow / consent_required / deny / consent_required` for the 5-signal smoke, identical to the M3.2 commit's reference output.
- **Smoke-test scripts in the testing procedure** that used `exec(n.script, local)` (single-namespace) had been masking these bugs. Note for the user: re-run with `exec(n.script, None, ns)` to match engine semantics. The Phase 3 persistent workflow's middleware logic was already in `app/proactive/middleware.py` (a real Python module), so it was unaffected — the bug only existed in workflows whose middleware was inline in transform scripts.

### Documentation

- `docs/transform-flow-scripts.md` — **created.** Reference document explaining the `exec(script, None, locals)` two-namespace gotcha for anyone authoring inline Python in `transform_flow` nodes. Covers: the mechanism (LEGB lookup against `nodes.py` globals instead of script locals), what doesn't work (top-level constants from inside functions, helper-to-helper calls, direct recursion, generator-expression bodies), six patterns that do work (top-level only, self-contained functions, default-argument capture, in-function imports, closures, iterative + explicit stack), and the recommended escape hatch — move non-trivial logic into a module under `app/` and import it from a thin shim. Lists the Phase 3 modules (`proactive.middleware`, `proactive.persistence`, `proactive.quarantine`) as reference implementations.

### Tooling

- `tools/lint_transforms.py` — **created.** AST-based linter that scans every `transform_flow` script in a workflow JSON for the four split-namespace exec hazards documented in `docs/transform-flow-scripts.md`: `RECURSIVE-DEF` (function references its own name), `HELPER-CALL` (function calls another top-level function), `CAPTURE` (function reads a top-level constant or imported name), `COMPREHENSION-LEAK` (comp/genexp/lambda body reads a top-level name; the first generator's `iter` is correctly excluded since Python evaluates it eagerly in the enclosing scope). Also flags `SYNTAX` errors. Defaults to `examples/*.json` when no paths are given; emits one finding per line with file, node index/name, line/col, name, kind, and reason; exit 1 on findings, 0 when clean. Verified: scans the 19 `examples/*.json` workflows clean; on a synthetic bait workflow flags 5 findings across the four hazard classes.
- `tools/smoke_proactive.py` — **created.** End-to-end smoke runner for Phase 1–3 workflows that uses **the same `exec(script, None, locals)` mode the engine uses**, so split-namespace bugs surface here instead of in production. Runs four checks: Phase 1 substrate stub (governor decisions `{allow:3, consent_required:1}`), Phase 1 sensory slice (5 observations + Privacy redaction visible in tick 2/3 bodies), Phase 2 vertical slice (1 action executed + 1 consent parked + motor states `{executed:1, deferred_to_social:1}`), Phase 3 persistent stack (5-signal verdict matrix `allow/allow/consent_required/deny/consent_required` + quarantine→snapshot→release→restore round-trip). State directory cleared before and after the Phase 3 check so the smoke is deterministic. `--verbose` prints per-step details. Exit 1 on any failure, 0 when all four pass.

These two utilities close the loop: any future workflow merged into `examples/` gets caught at lint time if it falls into the same exec-scoping trap, and any future change that breaks Substrate behaviour gets caught at smoke time. Both run under the same Python the rest of the project uses (`.venv/Scripts/python.exe` on Windows; standard `python` everywhere else) — no extra dependencies.

- `tools/git-hooks/pre-commit` + `tools/git-hooks/README.md` — **created.** Tracked git hook that runs `tools/lint_transforms.py` over the `examples/*.json` files in the staged change set; blocks the commit if a `transform_flow` script contains any of the four hazards. Skips silently when no examples are staged. Picks the venv Python first, then system `python3` / `python`, then no-ops if no interpreter is available (so the hook doesn't break a fresh clone). Install once per clone with `git config core.hooksPath tools/git-hooks`. Bypassable for an emergency commit with `git commit --no-verify`. Verified: clean staging exits 0; a synthetic recursive-`def` workflow staged under `examples/` causes the hook to print the finding and block the commit (exit 123).
- `tools/smoke_proactive.py` — **extended with `--integration` and `--integration-only` flags.** When integration is requested, the runner additionally spawns `app/app.py` in a subprocess on an ephemeral port, sets `NUMEL_PROACTIVE_DIR` to a fresh temp dir, pre-seeds `ledger.jsonl` with three known fixtures (one allow / one consent_required / one deny with an injection hit), waits for `/ping` to respond (60s deadline; surfaces the subprocess's stderr tail if it dies early), and exercises every proactive HTTP endpoint:
  - `POST /proactive/vitals` — asserts `ledger_count=3`, `governor_decisions={allow:1, consent_required:1, deny:1}`, `injection_hits_total=1`.
  - `POST /proactive/ledger` — asserts most-recent-first ordering and the `since_id` cutoff (a request with `since_id=led_2` returns only `led_3`).
  - `POST /proactive/snapshot/take` + `/snapshots` — round-trip: take a labeled snapshot, list it, mutate live state by appending `led_4` to disk, restore the snapshot, confirm `ledger_count` returns to 3, then `/snapshot/delete`.
  - `POST /proactive/quarantine` + `/quarantine/release` — empty list initially; release of an un-quarantined key returns `released=False`.
  Cleanup is in `finally`: `terminate()` then `wait(timeout=10)`, with `kill()` fallback and tempdir removal regardless of outcome. Verified: full run (5/5 checks) under engine-style exec + a real subprocess takes ~10s on a warm Python venv and 30–40s cold.

### Proactive System — Phase 4 (M4.1: Alignment layer — Phase-1 of Evolution)

- `app/proactive/evolution.py` — **created.** Always-on Alignment surface per §11. Three pillars + a pluggable validator chain:
  - **Explicit Feedback** — `record_feedback(target_id, kind, value, context)` appends to `alignment_signals.jsonl`. Three valid kinds: `"thumbs"` (up/down on a Ledger entry), `"edit"` (the user modified a proposed intent before accepting), `"preference"` (an explicit setting). `list_feedback(since=None, kind=None, limit=100)` returns most-recent-first.
  - **Preference Vectoring** — User Constitution at `user_constitution.json` with shape `{version, created_at, updated_at, rules: [...], preferences: {...}}`. `read_constitution()` lazy-creates with defaults. `update_constitution(patch)` shallow-merges (preferences merge by key, rules append idempotently by id, other top-level keys replace), bumps `version`, stamps `updated_at`.
  - **Validator chain** — `Verdict` dataclass `{decision: "pass"|"veto", reason, by}`. `register_validator(name, fn)` / `unregister_validator(name)` / `list_validators()`. `run_alignment(candidate)` runs every registered validator over the candidate dict, returns aggregate `{decision, verdicts, ts, candidate}`. Aggregate is `pass` only if every validator passed; any veto produces a veto with the full per-validator trail. Validator exceptions are caught and converted to `veto` so a buggy plugin can't silently approve.
  - **Two built-ins** auto-registered on import:
    - `recent_thumbs_down` — vetoes if a candidate's capability has accumulated ≥ 3 recent `thumbs/down` signals.
    - `constitution_check` — vetoes if the candidate's capability matches a `{kind: "never", target: <cap>}` rule in the User Constitution.
- `app/api.py` — **six new POST endpoints** under `/proactive/*`:
  - `POST /proactive/feedback` (body `{target_id, kind, value, context?}`) → records a signal; 400 on missing target or unknown kind.
  - `POST /proactive/feedback/list` (body `{kind?, since?, limit?}`) → newest-first.
  - `POST /proactive/constitution` → returns the current constitution (lazy-creates).
  - `POST /proactive/constitution/update` (body `{patch}` or the patch as the body itself) → applies the merge and returns the new state.
  - `POST /proactive/alignment/validators` → `{validators: [name…]}`.
  - `POST /proactive/alignment/check` (body `{candidate}` or candidate-as-body) → runs the validator chain.
- `web/numel-api.js` — added `proactiveFeedback(target, kind, value, context)`, `proactiveFeedbackList(opts)`, `proactiveConstitution()`, `proactiveConstitutionUpdate(patch)`, `proactiveAlignmentValidators()`, `proactiveAlignmentCheck(candidate)` helpers.
- `web/numel-proactive-vitals.js` + `web/numel-workflow.css` — each Ledger row in the Vitals panel grows a thumbs-up / thumbs-down button pair. Clicking a thumb POSTs a `thumbs` feedback signal scoped to that entry's id and capability (read from `intent.capability` or `resolved_capability.name` or `governor_verdict.capability`), flashes the active state for ~800ms, then refreshes. CSS-only (no images) — uses Unicode glyphs with subtle hover/active states.
- `tools/smoke_proactive.py` — added an in-process **Phase 4 · alignment layer** check (asserts feedback round-trip, constitution version bump, both built-in vetoes fire correctly, custom validator plug-in works) and extended the integration check with M4.1 endpoint coverage (feedback record + list, constitution update + version bump, validators list, alignment-check pass and veto paths). Full run is now 6/6 (5 in-process + 1 integration subprocess).

This commit closes M4.1 — Phase-1 Alignment is in place, both as a Python API for downstream code (M4.2 Optimization will produce candidate changes that pass through this gate) and as a thin HTTP surface for the UI / external tools. M4.2 (Optimization sandbox) and M4.3 (Promotion gate) still pending.

### Proactive System — Phase 4 (M4.2: Optimization sandbox — Phase-2 of Evolution)

- `app/proactive/optimization.py` — **created.** Offline, sandboxed side of Evolution per §11. Three concerns:
  - **Sandbox** (`with sandbox(seed_files=...) as tmp:`) — context manager that flips `NUMEL_PROACTIVE_DIR` to a fresh temp directory for the duration of the block, restoring the previous value (or unsetting it) on exit. Anything written by `proactive.persistence.*` inside the block lives in the sandbox; the temp dir is removed on exit. `seed_files` is a `{filename: data}` map: `*.json` is JSON-encoded, `*.jsonl` accepts an iterable of records (one per line), other suffixes are written via `str()`. Verified: live ledger row count is unchanged before vs. after a sandbox block that wrote 2 seeded entries.
  - **Self-Reflective Debugging** strategies — each scans live state and emits zero-or-more candidate dicts (`{kind, target, payload, rationale, evidence, by, ts}`):
    - `tighten_governor` — vetoes-by-deny: capabilities whose Governor verdicts are ≥50% `deny` over ≥4 samples → propose a `constitution_rule_add` (`{kind: "never", target: <cap>}`). Skips capabilities already constitution-banned.
    - `prune_quarantine` — currently-quarantined capabilities with ≥5 recorded failures → propose the same `constitution_rule_add` to promote a soft block to a hard ban. Skips already-banned.
    - `relax_constitution` — constitution-banned capabilities with ≥3 thumbs-up signals → propose a `constitution_rule_remove`.
  - **Synthetic Self-Play / Simulation** — `simulate_candidate(candidate, ledger=None, signals=None)` dispatches on `candidate.kind`:
    - `constitution_rule_add` → replays the historical Ledger and reports how many entries would have been recoloured to `deny` (capability matches AND old verdict ≠ `deny`) plus up to 5 examples.
    - `constitution_rule_remove` → reports how many past `deny`s on that capability could relax + thumbs-up total backing the proposal.
    - Unknown kinds return `{kind: "unsupported", reason: ...}` instead of raising.
  - `propose_from_state()` runs all three strategies and returns the merged candidate list, each stamped with a consistent `ts`. Tunables (`_DENY_RATE_THRESHOLD=0.50`, `_DENY_MIN_SAMPLES=4`, `_QUARANTINE_FAILURE_FLOOR=5`, `_THUMBS_UP_TO_RELAX=3`) live as module constants — real implementation would learn these.
- `app/api.py` — **two new POST endpoints**:
  - `POST /proactive/optimization/propose` → `{candidates, count}` from running every built-in strategy against current live state.
  - `POST /proactive/optimization/simulate` (body `{candidate}` or candidate-as-body) → diff report; never applies the change. 400 on missing candidate.
- `web/numel-api.js` — added `proactiveOptimizationPropose()` and `proactiveOptimizationSimulate(candidate)` helpers.
- `web/index.html` + `web/numel-proactive-vitals.js` + `web/numel-workflow.css` — new **Proposed candidates** subsection in the Vitals panel, between snapshots and quarantine. Header has a `Propose` button that calls the propose endpoint and renders the result list. Each row shows the strategy that produced it (`tighten_governor` etc.), the kind (`add`/`remove`), the target capability, the rationale, and a `Simulate` button that POSTs to the simulate endpoint and reports a one-line summary inline (`Δ N entries  (unchanged: M)` for adds; `N past deny(ies) on … could relax  (thumbs-up: K)` for removes). Add candidates get a green left-border accent, remove candidates a violet one. The list survives panel auto-refresh (cached in `_candidates` until the next Propose click).
- `tools/smoke_proactive.py` — added an in-process **Phase 4 · optimization sandbox** check (sandbox isolation, all three strategies fire under appropriate seeds, simulator reports correct deltas, unsupported-kind path returns structured error) and extended the integration check with M4.2 endpoint coverage (propose returns a list; simulate of a `constitution_rule_add` candidate returns the expected shape). Full run is now **7 / 7** (6 in-process + 1 integration subprocess).

This commit closes M4.2 — Optimization can now propose and simulate candidate changes against the persistent state, in a properly isolated sandbox. The candidates flow into M4.1's `run_alignment()` as-is; M4.3 (Promotion gate) will wire them together and add the "apply if approved" path.

### Proactive System — Phase 4 (M4.3: Promotion gate — closes the Evolution loop)

- `app/proactive/promotion.py` — **created.** Single entry point: `promote(candidate, *, simulate=True)`. Walks the full chain — optional simulation (M4.2) → alignment validators (M4.1) → kind-specific applier — and writes a `core.evolution.promotion` Ledger entry capturing the Why-chain regardless of outcome. Possible `decision` values: `applied` / `noop` / `refused_by_validator` / `skipped_unknown_kind` / `apply_failed`. Pluggable applier registry — `register_applier(kind, fn)` / `list_appliers()` — with two built-ins:
  - `constitution_rule_add` — checks for an existing rule with matching `(kind, target)`; returns `noop` if present (idempotent), otherwise calls `evolution.update_constitution`.
  - `constitution_rule_remove` — calls `evolution.remove_rule(rule_id, match)`; returns `noop` if the rule isn't present, otherwise reports the removed rules and the new constitution version.
- `app/proactive/evolution.py` — **added `remove_rule(rule_id=None, match=None)`** — removes by id or by `kind+target` match (or both). Bumps the constitution version and writes the new state only when a rule was actually removed. Idempotent on absent rules.
- `app/proactive/evolution.py` — **fixed validator semantics** so governance candidates aren't self-referentially vetoed. `constitution_check` skips candidates whose `kind.startswith("constitution_rule_")` (those manage rules; checking them against the rules they manage produces a self-loop). `recent_thumbs_down` skips `constitution_rule_add` (banning a downvoted capability *aligns* with the signal) but still vetoes `constitution_rule_remove` (un-banning a downvoted capability would override the user signal). Both validators continue to apply normally to actuation candidates.
- `app/api.py` — **one new POST endpoint**: `POST /proactive/promotion/promote` (body `{candidate, simulate?: bool}`) — runs the full chain and returns `{id, ts, decision, candidate, simulation, alignment, applied, ledger}`. 400 on missing candidate.
- `web/numel-api.js` — added `proactivePromote(candidate, simulate=true)` helper.
- `web/numel-proactive-vitals.js` + `web/numel-workflow.css` — each candidate row in the Vitals panel grows a **Promote** button alongside Simulate. Click prompts a `confirm()` dialog, calls the endpoint, renders an inline result line: `<decision>  (alignment: <align>, apply: <status>) ← <vetoes>`. The result line is colour-coded per outcome (`applied`: green / bold, `noop`: secondary, `refused_by_validator`: red, `skipped_unknown_kind`: amber, `apply_failed`: red). On `applied` or `noop`, the panel re-runs `Propose` after a short delay (the constitution may have changed → some candidates may no longer apply).
- `tools/smoke_proactive.py` — added a **Phase 4 · promotion gate** in-process check exercising all five decision paths (applied / noop / refused_by_validator / skipped_unknown_kind / applied-remove + thumbs-down veto on a remove) and asserting the per-promotion Ledger entry shape. Extended the integration check with three promote-endpoint calls (apply / re-apply → noop / actuation hits banned cap → veto with `constitution_check` in `veto_by`). Full run is now **8 / 8** (7 in-process + 1 integration subprocess).

This commit closes **Phase 4 — Evolution**. Candidates produced by Self-Reflective Debugging in M4.2 flow through the M4.1 validator chain to the M4.3 applier, with every step recorded in the Ledger. The Operational Philosophy table's "Evolutionary updates → Ledger + Why-chain + Alignment-pass" row now has a real implementation behind it.

### Phase 4 status

| Milestone | Commit | Surface |
|---|---|---|
| M4.1 Alignment            | `f835469` | `app/proactive/evolution.py` (signals + constitution + validator chain), 6 endpoints, Vitals thumbs UI |
| M4.2 Optimization sandbox | `6e9b3d8` | `app/proactive/optimization.py` (sandbox + 3 strategies + simulator), 2 endpoints, Vitals candidate list |
| M4.3 Promotion gate       | `ab8a16a` | `app/proactive/promotion.py` (chained simulate→align→apply), 1 endpoint, Vitals Promote button |

### Proactive System — Phase 5 (M5.1: MCP bridge — external integrations)

- `app/proactive/mcp.py` — **created.** Bidirectional bridge between Numel's Capability Registry and the Model Context Protocol tool shape. Numel acts as both server (exposing built-in capabilities) and client (registering peers' tools as namespaced capabilities).
  - **Server side:**
    - `list_tools_as_mcp()` returns the local Capability Registry in MCP `{name, description, inputSchema, annotations}` shape. Annotations carry our scopes / latency_tier / cost_estimate / remote flags so MCP consumers can see the safety classification.
    - `register_handler(name, fn)` wires a Python callable to a capability; `core.notify` ships with a built-in handler that returns `{delivered: True, message}` (real implementations would surface a UI toast).
    - `call_tool(name, arguments)` runs the **full Substrate gate** in order: Adversarial filter on incoming `arguments` → Alignment chain (`evolution.run_alignment`) → handler dispatch → Privacy gate on the handler's response. Any veto short-circuits with the per-validator trail; missing handler returns a structured `not_implemented` instead of raising. Five terminal states: `ok=True` (with redacted result), `unknown_capability`, `alignment_veto`, `not_implemented`, `handler_error`.
    - Every call writes a full request/response/verdict trace to `mcp_calls.jsonl` so operators can audit what flowed through. `list_calls(limit=50)` returns the most-recent traces.
  - **Client side:**
    - `register_remote(server, tool_descriptor, *, scopes=None)` adds a peer's MCP tool to the local Capability Registry under `mcp.<server>.<tool.name>`, defaulting to `["external-network"]` scopes. The original descriptor + annotations are preserved on the entry under `remote_descriptor`.
    - `list_remote()` mirrors the imported tools from the index file.
    - `drop_remote(name)` removes from both the registry and the index. Idempotent.
  - Lazy-seeds the same three built-in capabilities (`core.notify` / `core.send_email` / `core.transfer_funds`) the persistent workflow seeds, plus an `input_schema` JSON Schema field on each so MCP consumers get a typed tool descriptor.
- `app/api.py` — **six new POST endpoints**: `/proactive/mcp/tools`, `/proactive/mcp/call`, `/proactive/mcp/register_remote`, `/proactive/mcp/remote_tools`, `/proactive/mcp/drop_remote`, `/proactive/mcp/calls`. All follow the existing project-wide POST convention.
- `web/numel-api.js` — added `proactiveMcpTools`, `proactiveMcpCall`, `proactiveMcpRegisterRemote`, `proactiveMcpRemoteTools`, `proactiveMcpDropRemote`, `proactiveMcpCalls` helpers.
- `web/index.html` + `web/numel-proactive-vitals.js` + `web/numel-workflow.css` — new **External integrations (MCP)** subsection in the Vitals panel, between Snapshots and Quarantine. Three-row summary: local tools (count + comma-sep names), remote tools (count + `name ← server`), and the 5 most recent MCP-call traces with status colour-coded by ok/error class. Auto-refreshes alongside the rest of the panel; **Refresh** button forces an immediate fetch.
- `tools/smoke_proactive.py` — added an in-process **Phase 5 · MCP bridge** check verifying all five `call_tool` decision paths (clean / unknown / alignment veto / not_implemented / privacy-redacted response with `[card]/[ssn]/[email]` substitutions in the handler output), the remote-tool round-trip (register → list → drop → re-drop returns False), and the call log captures every attempt. Extended the integration check with three MCP HTTP calls (tools list, register-remote, drop-remote, unknown-cap call). Full run is now **9 / 9** (8 in-process + 1 integration subprocess).

This commit closes M5.1 — Numel can now be discovered as an MCP server (with safety classification surfaced via annotations) and can extend its Capability Registry with imported peer tools (under a clean namespace, gated by the same Substrate). M5.2 (A2A federation) and M5.3 (generic transports for OpenAI/Claude API) still pending.

### Phase 5 status

| Milestone | Commit | Surface |
|---|---|---|
| M5.1 MCP bridge       | `cc2d9fd`   | `app/proactive/mcp.py` (server + client side), 6 endpoints, Vitals MCP subsection |
| M5.2 A2A federation   | this commit | `app/proactive/a2a.py` (peer registry + trust tiers + share_state), 9 endpoints, Vitals A2A subsection |
| M5.3 Generic transports | this commit | `app/proactive/transports.py` (OpenAI-compat + Anthropic bridges, dry-run mode), 5 endpoints, Vitals LLM-transports subsection |

### Proactive System — Phase 5 (M5.3: Generic LLM transports — closes Phase 5)

- `app/proactive/transports.py` — **created.** Bridges that let the Substrate present external LLM endpoints as first-class Capability Registry entries. Every call goes through the same gates as native capabilities — Adversarial filter on the prompt, Alignment chain over the candidate, Privacy gate on the response — so an LLM bridge gets the same safety classification and audit trail as `core.notify` or `core.send_email`.
- Two transport flavours ship built-in:
  - `openai` — OpenAI-compatible Chat Completions (`POST {base_url}/chat/completions`, Bearer auth). Works with OpenAI proper, Azure OpenAI, vLLM, llama.cpp's `openai_compatible` server, Together, Groq, Ollama in OpenAI-compat mode, etc.
  - `anthropic` — Anthropic Messages API (`POST {base_url}/v1/messages`, `x-api-key` auth). Works with the official Claude API and any compatible re-host.
- **Capabilities registered as `transport.<kind>.<alias>`** (e.g. `transport.openai.ollama_llama3`, `transport.anthropic.claude_haiku`) — visible in the Capability Registry the same way native caps are. `register_transport(alias, *, kind, base_url, model, api_key_env=None, scopes=None, extra=None)`. API keys are resolved from the named environment variable at call time — never persisted to disk.
- `call_transport(alias, prompt, *, dry_run=False)` routes through `mcp.call_tool` so the Adversarial → Alignment → Privacy chain runs uniformly. **`dry_run=True`** short-circuits the HTTP call and returns a synthetic echo response (used by smoke tests and by the UI's "Test" button so operators can verify a bridge is wired correctly without spending tokens).
- Default scopes are `["external-network", "spends-money"]` — high-stake on both axes, so the Governor routes any actuation through `consent_required` unless the operator explicitly downgrades scopes (e.g. for a self-hosted Ollama bridge: pass `scopes=["external-network"]`).
- HTTP itself is implemented with `urllib.request` so the module has no extra dependencies and is trivially mockable.
- Every call attempt — including unknown-alias and HTTP errors — is logged to `transport_calls.jsonl` for audit (mirrors how A2A logs unknown_peer attempts).
- `app/api.py` — **five new POST endpoints**: `/proactive/transports`, `/proactive/transports/register`, `/proactive/transports/drop`, `/proactive/transports/call` (with `dry_run` param), `/proactive/transports/calls`.
- `web/numel-api.js` — added five `proactiveTransports*` helpers.
- `web/index.html` + `web/numel-proactive-vitals.js` — new **LLM transports** subsection in the Vitals panel after A2A. Two-row summary: registered bridges (count + colour-coded `alias<sup>kind</sup>` chips), 4 most recent call traces (alias + status colour-coded). Auto-refreshes alongside the rest of the panel; manual **Refresh** button.
- `tools/smoke_proactive.py` — added in-process **Phase 5 · LLM transports** check using `dry_run=True` (no real network): registration across both kinds + validation guards (bad kind, alias with spaces); capability registry entry created under `transport.<kind>.<alias>`; clean dry-run call returns the synthetic echo; unknown-alias path; alignment veto when the cap is constitution-banned; **privacy gate redacts `[card]/[ssn]/[email]` in the dry-run echo of a leaky prompt**; call log captures every attempt; idempotent drop. Extended the integration check with three transport HTTP calls (register, list, dry-run call, drop). Full run: **11 / 11** (10 in-process + 1 integration subprocess).

This commit closes **Phase 5 — External integrations**. Numel can now (a) advertise its capabilities via MCP and consume peers' tools (M5.1), (b) federate with other systems through three trust tiers with adversarial-gated inbound and privacy-gated outbound (M5.2), and (c) bridge external LLMs (OpenAI-compatible + Claude) as first-class capabilities subject to the same Substrate gates (M5.3).

### Proactive System — Phase 5 (M5.6: A2A federation joins the unified Capability model — closes the staged migration)

Final stage. A2A `send` and `share_state` now route through `mcp.call_tool` so federation gets the same Adversarial → Alignment → handler → Privacy chain as every other capability. Trust tier becomes a **scope** (`tier:peer` / `tier:partner` / `tier:federated`) — declarative policy instead of buried if-branches.

- `app/proactive/a2a.py` — **register_peer / drop_peer / send / share_state rewritten.**
  - `register_peer(peer_id, *, tier, ...)` now auto-registers two capabilities: `a2a.<peer_id>.send` and `a2a.<peer_id>.share_state`. Both carry the trust tier as a scope so constitution rules can target a tier instead of naming peers individually (e.g. `{kind: never, target_scope: "tier:peer"}` would block any send to a peer-tier peer).
  - `drop_peer(peer_id)` now drops the per-peer caps too — no orphan registry entries after a peer is removed.
  - `send(peer_id, message, *, kind)` is now a thin public wrapper that (1) checks `unknown_peer` early, (2) lazy-ensures caps for peers that pre-date M5.6, (3) dispatches via `proactive.agents.call_agent(kind=KIND_A2A, alias=f"{peer_id}.send")`. The actual outbox-write logic moved to `_send_handler(args)` which runs after the gate chain has cleared the message. Return shape is preserved: outbox record on success, `{ok: False, reason}` on unknown_peer or gate veto.
  - `share_state(peer_id, namespaces)` similarly delegates to `_share_state_handler`. The per-namespace Privacy gate inside the handler stays (it's finer-grained than the chain's outer Privacy pass) — both run; inner is for audit detail, outer is defence-in-depth.
  - `receive(peer_id, message, *, kind)` is **unchanged** — inbound A2A is a different model. The existing inline `middleware.adversarial_gate` call is the right primitive there because there's no candidate to align over (the system is being acted upon, not deciding to act).
- **Scope set per A2A verb:**
  - `a2a.<peer>.send`        → `["external-network", "affects-third-party", "tier:<tier>"]`
  - `a2a.<peer>.share_state` → `["external-network", "shares-state",        "tier:<tier>"]`
- `tools/smoke_proactive.py` — extended **Phase 5 · A2A federation** check with M5.6 coverage: per-peer caps appear after `register_peer` for all three tiers (six caps total: 3 peers × 2 verbs); trust tier is on each cap as `tier:<tier>`; constitution rule banning ONLY `a2a.bob.partner.send` blocks Bob's send while Boss's send still works; `drop_peer` removes the per-peer caps from the registry. Outbox count adjusted from 1 → 2 to reflect that the gate-vetoed send doesn't append (verifies the gate is actually short-circuiting before `_send_handler`). Full run: **12 / 12** (11 in-process + 1 integration subprocess).

This commit closes M5.6 — and closes the M5.4 → M5.5 → M5.6 unification arc. The system now has **one** outbound model: every "thing the system does that touches an agent or an external system" goes through `mcp.call_tool`, runs the same gate chain, lands in the same audit pattern, shows up in the same Capability Registry with declared scopes that the Governor and constitution rules can target. The five formerly parallel codepaths (`agent_flow` / `agent_endpoint_flow` / `mcp` / `transports` / `a2a`) now share one invocation primitive.

### Proactive System — Phase 5 (M5.5: Remote agent endpoint as Capability — second stage of unification)

Second of three staged commits. Brings `agent_endpoint_flow` (the workflow primitive for "call another deployment or A2A remote agent") into the same Capability Registry + `mcp.call_tool` model as M5.4's local `agent_flow`. The new wrinkle here is **mode-specific scopes**: `consult` / `delegate` / `notify` / `handoff` represent very different stakes, so each (node, mode) pair gets its own Capability with mode-derived scopes.

- `app/nodes.py` — **`WFAgentEndpointFlow.execute` updated.** Same opt-in env var (`NUMEL_PROACTIVE_AGENT_GATING`); when set, routes through `proactive.agents.call_agent(kind=KIND_ENDPOINT)`. Each mode gets its own lazy-registered cap `agent.endpoint.node_<index>.<mode>` so the Governor and constitution rules see different scopes per mode. Cached on the node instance via `self._proactive_aliases: dict[mode -> alias]` to avoid re-registering on every call. Two new module-level helpers: `_scopes_for_endpoint_mode(mode)` (maps mode → scope set) and `_make_endpoint_handler(ref)` (wraps the engine's `_run_agent_endpoint` partial into a `proactive.agents` handler).
- **Mode → scopes map:**
  - `consult`  → `["external-network"]` (read-only conversation)
  - `delegate` → `["external-network", "delegates-authority"]` (give the remote agent decision-making power)
  - `handoff`  → `["external-network", "delegates-authority", "non-reversible"]` (transfer ownership of the conversation)
  - `notify`   → `["external-network", "affects-third-party"]` (one-way side-effect)
- `tools/smoke_proactive.py` — extended **Phase 5 · agent capabilities** check with endpoint-kind coverage: register three caps for one node across consult/delegate/notify; verify each cap appears with its mode-specific scopes; clean dispatch through consult; constitution rule banning ONLY `agent.endpoint.node_42.delegate` → consult survives, delegate is vetoed. Full run: **12 / 12** (11 in-process + 1 integration subprocess).
- **Constitution targeting works at mode granularity now.** Previously a rule banning a remote endpoint had to ban the whole endpoint or rely on transform-script logic. After M5.5 the operator can write `{kind: never, target: agent.endpoint.<id>.delegate}` and the same endpoint stays usable for consult — exactly the policy split the trust model needs.

This commit closes M5.5. Local `agent_flow` (M5.4) and remote `agent_endpoint_flow` (M5.5) now share one Capability Registry, one gate chain, one audit log. Next stage: M5.6 (A2A `send` / `share_state` route through `mcp.call_tool` so federation joins the same model and the inline `adversarial_gate` calls inside `a2a.py` can shed).

### Proactive System — Phase 5 (M5.4: Local agent capability bridge — first stage of unification)

This is the first of three staged commits (M5.4 → M5.5 → M5.6) that collapse the previously parallel codepaths (`agent_flow` / `agent_endpoint_flow` / `a2a` / `mcp` / `transports`) into one uniform Capability Registry + `mcp.call_tool` invocation model. After M5.6, every "thing the system does that touches an agent or an external system" goes through the same Adversarial → Alignment → handler → Privacy chain, lands in the same audit log, and shows up in the same Capability Registry with declared scopes.

- `app/proactive/agents.py` — **created.** New unification primitive. Exposes `register_agent_handler(alias, handler, *, kind, scopes, description, input_schema, extra)` (mirroring `register_transport`) and `call_agent(alias, request, *, image, kind, extra_args)` which routes through `mcp.call_tool` so the same Adversarial → Alignment → handler → Privacy chain runs as for any other capability. Three kinds in one Registry: `agent.<alias>` (local in-process — M5.4), `agent.endpoint.<alias>` (remote endpoint — M5.5), `a2a.<peer>.<verb>` (federation — M5.6). Default scopes per kind: local=`["llm"]`, endpoint=`["external-network", "delegates-authority"]`, a2a=`["external-network"]`. Async handlers are tolerated — `_wrap_handler` detects coroutines and runs them on a fresh loop or via a worker thread when the caller is already inside one. Persistence: `agent_configs.json` (operator-supplied bridge configs), `agent_calls.jsonl` (request/response audit log).
- `app/nodes.py` — **`WFAgentFlow.execute` updated** to opt-in route through `proactive.agents.call_agent` when the `NUMEL_PROACTIVE_AGENT_GATING` env var is set. On first gated call the node lazy-registers a per-node Capability `agent.node_<index>` whose handler is a closure over the existing `self.ref` partial (the backend's `run_agent`). When the env var is unset (the default), the node falls through to the original `await self.ref(...)` path — no behaviour change for non-proactive deployments. The proactive package is imported lazily inside `_proactive_agent_gating_enabled()` so non-proactive deployments don't pay the import cost.
- `app/api.py` — **four new POST endpoints**: `/proactive/agents` (list + gating flag), `/proactive/agents/drop`, `/proactive/agents/call`, `/proactive/agents/calls`. Note: there is no `/agents/register` endpoint by design — handlers are Python callables, not JSON-serialisable, so registration always goes through Python (workflow load, in-process import, etc.). The HTTP surface covers list / call / drop / audit.
- `tools/smoke_proactive.py` — added in-process **Phase 5 · agent capabilities** check covering: sync handler registration → cap appears in `capabilities.json` → clean dispatch → async handler dispatch (verifies `_wrap_handler`'s coroutine detection) → privacy gate redacts `[card]` / `[email]` in the agent's response → alignment veto when the cap is constitution-banned → unknown alias short-circuits to `unknown_capability` → validation guards (alias with spaces, invalid kind) → call log captures every call → idempotent drop + cap leaves the registry → drop by full cap_name also works → gating env var defaults off and honours `1`/`true`/`yes`/`on` for enabled. Extended the integration check with three new HTTP calls (agents list + gating_enabled flag, calls log shape, idempotent drop on unregistered alias). Full run: **12 / 12** (11 in-process + 1 integration subprocess).

This commit closes M5.4. Local `agent_flow` is now a first-class Capability when gating is enabled — Adversarial → Alignment → handler → Privacy chain runs around every LLM call, the agent appears in the Capability Registry alongside `core.notify` / `transport.openai.<alias>` / `mcp.<server>.<tool>`, the Governor sees declared scopes, and every call lands in `agent_calls.jsonl`. Next stages: M5.5 (`agent_endpoint_flow` joins the same primitive), M5.6 (A2A `send` / `share_state` route through `mcp.call_tool`).

### Post-Phase-5 follow-ups

- `examples/proactive-vertical-slice-agentic.json` — **created.** Phase 5 capstone demo: drop-in compatible with the deterministic `proactive-vertical-slice.json`, but the Conscious-layer transform routes its anticipatory decision through `proactive.transports.call_transport(...)` instead of pattern-matching subject keywords. Lazy-registers a default `smoke_bridge` transport on first tick. Operator knobs via env vars: `NUMEL_PROACTIVE_TRANSPORT` (alias to use, default `smoke_bridge`), `NUMEL_PROACTIVE_DRY_RUN` (`"0"` to make real network calls; default `"1"` keeps the demo offline). In dry-run mode, falls back to subject-keyword heuristics so the workflow demonstrates the LLM-bridged pipeline without a real model. Smoke (5 ticks): 5 transport_calls logged, tick 3 emits `core.transfer_funds → deferred_to_social`, tick 4 emits `core.notify → executed`. Linter clean.
- **Vitals Why-chain detail modal.** Clicking any Ledger row in the Vitals sidebar opens a CSS-only modal with the entry's full Why-chain pretty-printed (candidate, simulation, alignment.verdicts, applied, motor_status, social_consent_request, provenance, …). Closes on backdrop click, ✕ button, or Escape. One-line summary up top (verdict · reason · confidence · motor_status · timestamp) plus the full entry as monospaced JSON. Thumbs-up/down clicks now `stopPropagation()` so they still record feedback without opening the modal. Files: `web/index.html`, `web/numel-proactive-vitals.js`, `web/numel-workflow.css`.
- `~/Desktop/proactive-technical.md` — **rewritten as full v1 spec.** The conceptual blueprint (`~/Desktop/proactive.md`) describes what each component is for; this document specifies how it's built. Sections: Overview & Architecture, Bus & Event Flow (ledger entry shape + trigger topics + persistence primitives), Substrate Components (every gate + every store), Agent Layer Contracts, Lifecycle (Alignment / Optimization / Promotion), Operational Mechanics (consent flow, quarantine, audit), Storage & Persistence (file inventory + retention + migration), Concurrency / Failure Modes / Idempotency, Extension Surface, plus appendices (end-to-end Python example, regression-testing runbook, clean-slate recovery, module dependency graph). All cross-referenced to `examples/proactive-CHANGELOG.md` and `docs/transform-flow-scripts.md`.
- `docs/proactive-guide.md` — **enhanced** with eight Mermaid diagrams embedded inline at the section they belong to: big picture in §1, signal flow in §3, Substrate read/write contract in §4, Evolution loop in §6, External integrations in §7, Why-chain anatomy in §8 (with anchor `#anatomy-of-a-ledger-entry` linked from the operations table), module-dependency graph in §9.3, HTTP surface in §9.4. Same diagrams that live standalone in `docs/proactive-architecture.md` — duplicated inline so the guide reads as a single self-contained document. Subsections renumbered: glossary moved to §9.5, cross-reference index to §9.6.
- `docs/proactive-guide.md` — **created.** Unified user + technician guide. Layout pairs user-facing prose on the left with a technical sidebar on the right (two-column markdown tables) — same row, same concept, two reading levels. Sections: 30-second tour; mental model (the four parts + the five rules); a single signal walked end-to-end through every gate (the inbound `core.transfer_funds` example); the eight Substrate components (Middleware / World Model / Goal Hierarchy / Capability Registry / Governor / Vitals / Quarantine / Ledger), each with file path, API, and persistence shape in the sidebar; the four agent layers and their `transform_flow` contracts; the Evolution loop (feedback → optimization → alignment → promotion) with all five terminal states; the three external integration surfaces (MCP / A2A / LLM transports); the Vitals panel walk-through (which control wires to which endpoint); and a reference appendix with the file inventory, persistence inventory, ~40 endpoints, glossary, and a "how this doc relates to the other proactive docs" cross-reference. Designed to be read first by new operators, with the desktop blueprint and technical spec as deeper-dive companions.
- `docs/proactive-architecture.md` — **created.** Picture-book companion to the conceptual + technical specs. Eight Mermaid diagrams covering the system end-to-end: (1) Big picture by Phase (Substrate + Layers + Evolution + External + Storage), (2) Signal flow (one inbound observation traced through every gate to disk), (3) Substrate components read/write contract, (4) Evolution loop (propose → simulate → align → apply with all five terminal states from `promotion.py`), (5) External integrations (MCP / A2A / LLM transports through the same gate chain), (6) Module dependency graph (`persistence.py` is the only leaf; everything else fans in through Substrate), (7) HTTP surface organised by milestone (~40 endpoints, all POST), (8) Why-chain Ledger structure (a single entry's anatomy: candidate → simulation → alignment.verdicts → applied → provenance). Each diagram uses colour-coded `classDef` styling (substrate=blue, layer=green, evolution=purple, external=orange, storage=dark grey). Includes a "Reading guide" table at the end mapping use cases — onboarding / debugging a Ledger entry / auditing a transport call / planning an extension — to which sections to read. Renders inline on GitHub.

### Proactive System — Phase 5 (M5.2: A2A federation)

- `app/proactive/a2a.py` — **created.** Federation layer with explicit trust tiers per the conceptual blueprint's Part V Federation:
  - `peer` — reads shared World-Model excerpts only (anything under `core.public.*` plus the bare `core.public` path).
  - `partner` — reads + writes shared excerpts under `core.*`.
  - `federated` — reads any namespace; limited delegation under explicit scopes.
- **Peer registry** — `register_peer(peer_id, *, tier, name, contact)` validates the tier, persists to `a2a_peers.json`, and timestamps `created_at` / `updated_at`. `list_peers()`, `get_peer()`, `drop_peer()` complete the lifecycle.
- **Inbound messaging** — `receive(peer_id, message, *, kind)` runs the payload through `middleware.adversarial_gate`. If injection markers are detected, the message is recorded with `accepted=False, reason="adversarial"`, mirroring the §6 operational table's "Untrusted-source actuation → Refused" row. Unknown peers also short-circuit with `reason="unknown_peer"`. Every receive — accepted or refused — appends to `a2a_inbox.jsonl` so the operator can audit what was filtered.
- **Outbound messaging** — `send(peer_id, message, *, kind)` is a stub for the actual transport (HTTP / SSE / etc. as a future plug-in); it logs to `a2a_outbox.jsonl` and returns `ok=True`. Unknown peer returns `ok=False, reason="unknown_peer"` without logging.
- **State sharing** — `share_state(peer_id, namespaces)` reads requested World Model namespaces, gates by trust tier (refused namespaces returned in a separate list rather than silently dropped), runs each excerpt through `middleware.privacy_gate`, and logs the redacted excerpts to `a2a_shared.jsonl`. Verified: a partner asking for `core.observations` gets the data with `card 4111…` and `alice@example.com` substituted to `[card]` and `[email]` before leaving the system.
- `app/api.py` — **nine new POST endpoints** under `/proactive/a2a/*`: `peers` (list), `peers/register`, `peers/drop`, `receive`, `send`, `share_state`, `inbox`, `outbox`, `shared`.
- `web/numel-api.js` — added nine `proactiveA2a*` helpers.
- `web/index.html` + `web/numel-proactive-vitals.js` + `web/numel-workflow.css` — new **Federation (A2A)** subsection in the Vitals panel, after MCP. Shows: registered peers (count + colour-coded badges per tier with `peer` / `partner` / `federated` superscripts), inbox (3 most recent with status colour-coded), outbox (3 most recent), shared excerpts (3 most recent, with namespaces + refused count). Auto-refreshes alongside the rest of the panel; manual **Refresh** button.
- `tools/smoke_proactive.py` — added an in-process **Phase 5 · A2A federation** check covering: peer registration across all three tiers + invalid-tier rejection; inbound clean / adversarial (verifies injection_hits non-empty) / unknown_peer; outbound known + unknown_peer; trust-tier-gated share_state with the Privacy gate redacting `card`/`email` in shared observations; idempotent peer drop; logs accumulated correctly. Extended the integration check with five new HTTP calls (peers/register × 2, peers list, receive clean, receive adversarial, peers/drop). Full run: **10/10** (9 in-process + 1 integration subprocess).

This commit closes M5.2. Numel can now register external systems as peers across three trust tiers, accept inbound messages through the Adversarial filter, send outbound messages, and share World Model excerpts through the Privacy gate — exactly matching Part V of the conceptual blueprint. M5.3 (generic transports for OpenAI/Claude API as Capability Registry tools) still pending.

