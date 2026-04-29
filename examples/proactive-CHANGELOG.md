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

