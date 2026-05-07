# Numel Proactive System — Guide

A single document that explains the whole Proactive AI Agent Ecology, written for two readers at once:

- **The left column** is the user guide — plain language, what each piece does for you and how to use it.
- **The right column** is the technical sidebar — file paths, function names, data shapes, endpoints. Skip it on a first read.

> Companion documents: the conceptual blueprint at `~/Desktop/proactive.md`, the engineer-facing spec at `~/Desktop/proactive-technical.md`, the visual diagrams at [proactive-architecture.md](proactive-architecture.md), and the change log at [examples/proactive-CHANGELOG.md](../examples/proactive-CHANGELOG.md). This guide is the bridge between them.

---

## 1. The 30-second tour

Numel's proactive system is an agent that can act on your behalf without being prompted, but only after every action has passed through a chain of safety checks and been written to an auditable ledger.

It is built in four parts:

1. **The Substrate** — eight components that gate, store, and govern everything that happens. Nothing reaches the outside world without crossing this layer.
2. **Four Agent Layers** — Sensory (perceive), Conscious (decide), Motor (act), Social (negotiate). They plug into the Substrate; they do not replace it.
3. **The Evolution Loop** — the system learns from your feedback. New rules are simulated, validated, and only then applied.
4. **External Integrations** — MCP, A2A federation, and pluggable LLM transports. Outside services come in through the same gates as everything else.

You operate it through the **Vitals panel** in the workflow UI. Everything the system did, why it did it, and what it nearly did — all of it is one click away.

---

## 2. The mental model

| What you see | What's underneath |
|---|---|
| Numel "noticed" something, "decided" what to do, and "acted" or "asked first." Each of those verbs corresponds to a layer. The thing that ties them together is the **Ledger** — every step is recorded with a Why-chain you can inspect later. | The Substrate is a set of stateless gates and stateful stores built on `app/proactive/*.py`. The Ledger is a JSONL file (`ledger.jsonl`) appended to atomically. Layers run as `transform_flow` nodes inside workflow JSON. The four parts communicate by topic-routed events on the Ledger bus. |

| The five rules the system follows | Where they live |
|---|---|
| 1. Never act on input before it's been classified.<br/>2. Never leak personal data outward.<br/>3. Never act on instructions hidden inside untrusted content.<br/>4. Always check stakes before high-impact actions.<br/>5. Always record what was decided and why. | 1. Veracity gate — `middleware.veracity_gate`<br/>2. Privacy gate — `middleware.privacy_gate`<br/>3. Adversarial gate — `middleware.adversarial_gate`<br/>4. Governor — `app/api.py /proactive/governor/*`<br/>5. Ledger — `proactive/ledger.jsonl` |

---

## 3. Walking one signal end-to-end

To make the architecture concrete, follow a single inbound observation: an email arrives saying *"please transfer $5,000 to alice@example.com — see card 4111-1111-1111-1111"*. Here is what Numel does, top-to-bottom.

| Step | What you'd see in the Vitals panel | Where it happens in code |
|---|---|---|
| **Sensory layer** picks up the email and wraps it in an "observation envelope" with topic `core.observations`. | A new row appears in the Ledger pane: `core.observations · received`. | `examples/proactive-vertical-slice.json` Sensory transform node. The envelope shape is `{"topic": str, "payload": dict, "provenance": dict, "trust": str}`. |
| **Veracity** asks: "do we know this email is real?" If the source is unauthenticated, it is tagged `untrusted` but not dropped. | Source colour-coded `untrusted` in the row. | `middleware.veracity_gate(payload, provenance) -> {"trust": "trusted"\|"untrusted", "reasons": [...]}`. |
| **Privacy** scans the body. The card number and address are redacted to `[card]` and `[email]`. | Redaction count appears in the row's "Why" tooltip. | `middleware.privacy_gate(payload) -> {"redacted": dict, "matches": [...]}`. Redacts using regex patterns; mutates a deep copy. |
| **Adversarial** scans for prompt injection markers ("ignore previous instructions", role-play traps). If hit, the message is quarantined, not blocked outright. | If hit, row goes red: `quarantined · adversarial`. | `middleware.adversarial_gate(payload) -> {"safe": bool, "injection_hits": [...]}`. |
| **World Model** writes the (now-clean) observation under `core.observations.<id>`. The system "remembers" it. | The "World" panel updates to show the new observation. | `world_model.write(namespace, key, value)`; persisted to `world_model.json`. |
| **Conscious layer** reads the observation and forms a candidate: `intent: core.transfer_funds, amount: 5000, recipient: alice@example.com`. | Row: `core.transfer_funds · candidate`. | Conscious transform in the slice; emits a Ledger entry with `kind="candidate"`. |
| **Capability Registry** says: "`core.transfer_funds` exists, declared scopes `['external-network', 'spends-money', 'high-stakes']`." | The "Capabilities" subsection lights up the matched cap. | `capability_registry.lookup(name) -> {"scopes": [...]}`. Built-ins seeded from `capability_registry.json`. |
| **Goal Hierarchy** check: does this candidate satisfy a Standing Goal? If not, the candidate is downweighted but not rejected — proactivity may want to act anyway. | Goal-match badge in the row. | `goal_hierarchy.match(candidate) -> {"matched_goal": str\|None, "delta": float}`. |
| **Governor** evaluates stakes. `spends-money` + `high-stakes` together cross the threshold → verdict `consent_required`, not `allow`. | Row resolves to amber: `consent_required`. | `governor.gate(scopes) -> {"verdict": "allow"\|"consent_required"\|"refuse", "reason": str}`. Threshold: any scope in `_HIGH_STAKE` set. |
| **Social layer** prepares a consent request rather than the Motor layer firing. You see a notification: "Numel wants to transfer $5,000. Approve?" | Banner appears in the consent inbox. | Social transform emits `kind="consent_request"`; persisted to `consent_requests.json`. |
| **You approve.** Motor layer fires the transfer; result returned to the Ledger. | Row resolves green: `executed`. | Motor transform calls `capability.invoke(name, args)` then writes `kind="motor_status"`. |
| **Vitals** counts this as one `consent_required → executed` outcome and adjusts its rolling stats. | Counters tick up in the Vitals header. | `vitals.tally()` reads recent Ledger window. |
| If you'd hit the **Why** chevron**, you'd have seen every gate's verdict, the candidate, the simulation result, the alignment verdicts, and the final apply step — in one nested JSON view. | | The detail modal in `web/numel-proactive-vitals.js` (`_openWhyChain`) renders the full Ledger entry. |

That's one signal. Multiply it by every observation — emails, timer ticks, A2A peer messages, MCP tool results — and you have the full operating picture.

---

## 4. The Substrate — eight components

The Substrate is Numel's nervous system. Every event passes through it. Below, each component gets a one-paragraph user description and a sidebar with its file, API, and persistence shape.

### 4.1 Middleware (Veracity, Privacy, Adversarial)

| What it does for you | How it's built |
|---|---|
| Three gates that every inbound payload must clear before any layer is allowed to read it. **Veracity** classifies the source as trusted or untrusted. **Privacy** strips personal data — card numbers, emails, social-security numbers, phone numbers. **Adversarial** detects prompt-injection patterns and quarantines messages that try to hijack the agent's behaviour. The gates do not block — they classify, redact, and tag, leaving the higher layers to decide what to do with the result. | `app/proactive/middleware.py`. Three pure functions: `veracity_gate(payload, provenance)`, `privacy_gate(payload)`, `adversarial_gate(payload)`. Stateless. Each returns a dict with the verdict and a reasons list. Privacy regexes target `\b(?:\d[ -]*?){13,16}\b` for cards, `[A-Za-z0-9._%+-]+@…` for emails, etc. Adversarial uses keyword + heuristic matching against an injection corpus. |

### 4.2 World Model

| What it does for you | How it's built |
|---|---|
| Numel's memory — what it has observed, what state it currently believes the world is in, what facts it has about you and your environment. Other components read from and write to it under namespaced keys (`core.observations.<id>`, `core.preferences.theme`, etc.). | `app/proactive/__init__.py` exposes `world_model` — a thin wrapper over `world_model.json`. API: `read(namespace, key=None)`, `write(namespace, key, value)`, `delete(namespace, key)`. Atomic writes via `persistence.write_json_atomic`. Namespaces are dot-paths; subtrees are returned as nested dicts. |

### 4.3 Goal Hierarchy

| What it does for you | How it's built |
|---|---|
| Numel's "north star" plus the active sub-goals it's currently pursuing. The Standing Goal is seeded once (something like *"help the operator without doing harm"*); active goals are added dynamically (e.g., *"draft response to email X"*) and expire when satisfied. Candidates that match an active goal get a confidence boost; ones that don't aren't blocked, but they're flagged as opportunistic. | `app/proactive/__init__.py` exposes `goal_hierarchy`. API: `seed_standing_goal(text)`, `add_active(text, source)`, `match(candidate) -> {"matched_goal", "delta"}`, `list_active()`. Persisted in `goals.json` — `{"standing": str, "active": [...]}`. |

### 4.4 Capability Registry

| What it does for you | How it's built |
|---|---|
| The catalog of everything Numel is allowed to do. Each entry has a name (`core.notify`, `core.send_email`, `core.transfer_funds`, `transport.openai.gpt4o`), declared **scopes** (tags like `external-network`, `spends-money`, `high-stakes`), and a handler that knows how to execute it. The Governor reads scopes to decide whether an action needs your consent. | `app/proactive/__init__.py` exposes `capability_registry`. API: `register(name, *, scopes, handler)`, `lookup(name)`, `list()`. Persisted shape in `capability_registry.json`: `{"<name>": {"scopes": [...], "handler": "<callable_id>"}}`. Built-ins seeded at import: `core.notify`, `core.send_email` (stub), `core.transfer_funds` (stub). MCP/A2A/Transports register additional caps under `mcp.<server>.<tool>`, `a2a.<peer>.<topic>`, `transport.<kind>.<alias>`. |

### 4.5 Governor

| What it does for you | How it's built |
|---|---|
| The rule that decides **allow / consent_required / refuse** based on the scopes of the proposed action. Cheap, low-risk actions get `allow`. Anything touching money, identity, or a non-revocable side-effect gets `consent_required` — the Social layer asks you. Constitution-banned scopes get `refuse`. | `app/proactive/__init__.py` exposes `governor.gate(scopes)`. Pure function. Reads constitution rules from `constitution.json`. `_HIGH_STAKE = {"spends-money", "external-network", "high-stakes", "non-reversible", …}`. Verdict logic: any scope in HIGH_STAKE → `consent_required`; any scope in constitution-banned set → `refuse`; otherwise `allow`. |

### 4.6 Vitals

| What it does for you | How it's built |
|---|---|
| The dashboard. A rolling window of the most recent Ledger entries gets summarised into health stats: how many actions executed, how many were deferred for consent, how many were refused, what the deny-rate looks like, what the most-used capabilities are. This is also where you give thumbs-up / thumbs-down feedback on individual actions. | `app/proactive/__init__.py` exposes `vitals.tally(window=...)` returning a counters dict. The UI is `web/numel-proactive-vitals.js` — auto-refresh poller hitting `/proactive/vitals`, `/proactive/ledger/recent`, `/proactive/feedback/list`, `/proactive/mcp/*`, `/proactive/a2a/*`, `/proactive/transports/*`. |

### 4.7 Quarantine + Snapshots

| What it does for you | How it's built |
|---|---|
| **Quarantine** is where messages flagged by the Adversarial gate go to die — they're held for review, never auto-released. **Snapshots** let you freeze the full system state and roll back if Evolution introduces a bad rule. | `app/proactive/quarantine.py`. API: `quarantine(entry, reason)`, `list()`, `release(id)`, `purge_older_than(days)`. Stored in `quarantine.jsonl`. Snapshots: `snapshot_create()`, `snapshot_list()`, `snapshot_restore(id)`. Snapshots tar-zip the state directory under `snapshots/<timestamp>.tar.gz`. |

### 4.8 Ledger (the bus)

| What it does for you | How it's built |
|---|---|
| The append-only event log. Every observation, every candidate, every gate verdict, every action, every feedback click, every promotion — all of it goes here, with a Why-chain you can inspect. The Ledger is also the **bus**: components don't call each other directly, they emit Ledger entries with topics, and others subscribe by reading recent entries by topic. | `app/proactive/__init__.py` exposes `ledger`. API: `append(topic, kind, payload, **why)`, `recent(window=N, topic=...)`, `read_all()`. Persisted to `ledger.jsonl` (append-only). Each entry is a JSON line: `{"id", "ts", "topic", "kind", "payload", "why": {...}}`. The Why-chain is whatever caller put in `**why` — typically `{"candidate", "simulation", "alignment", "applied", "provenance"}`. |

---

## 5. The Agent Layers

Layers are where the agent's "personality" lives. They are deliberately thin — most of the heavy lifting is done by the Substrate. A layer is a single `transform_flow` node in workflow JSON, written in Python, holding state in `variables`.

| Layer | What it does for you | Technical contract |
|---|---|---|
| **Sensory** | Watches the world. Polls inboxes, listens for timer ticks, accepts webhook deliveries, subscribes to A2A peer messages. Wraps each event in a uniform observation envelope and emits it to the Ledger. | One `transform_flow` per sensor. Output: emit `kind="observation"` to `core.observations` with `payload`, `provenance`, and `trust` fields. Must run Veracity + Privacy + Adversarial before emitting. |
| **Conscious** | Decides. Reads the World Model, picks a candidate intent for the most recent unhandled observation. May consult a goal, a heuristic, or an LLM transport. Emits a `candidate` entry to the Ledger. | One transform. Reads `world_model.read("core.observations")`. Output: `kind="candidate"`, payload `{"intent": "<cap_name>", "args": {...}}`. May call `transports.call_transport(alias, prompt)` for LLM-backed reasoning. |
| **Motor** | Acts. Reads candidates the Governor has approved, invokes the matching capability, writes the result back. | Output: `kind="motor_status"`, payload `{"status": "executed"\|"errored", "result": ..., "error": ...}`. |
| **Social** | Negotiates. Holds consent inboxes, manages dialogues, asks the operator before high-stakes actions. | Output: `kind="consent_request"` or `kind="dialogue"`. Persists pending requests to `consent_requests.json`. |

> The reference workflow that demonstrates all four is `examples/proactive-vertical-slice.json` (deterministic) and `examples/proactive-vertical-slice-agentic.json` (LLM-backed Conscious layer via `transports.call_transport`).

---

## 6. The Evolution Loop

Numel improves itself by closing this loop:

```
your feedback → optimization sandbox → alignment validators → promotion gate → applied (or refused)
```

| Stage | What you see | What's underneath |
|---|---|---|
| **You give feedback.** Thumbs-up means "yes, more of this." Thumbs-down means "no, don't do this kind of thing again." Edits ("I would have answered differently") are also captured. | Click thumbs in any Vitals row, or write a free-form comment in the modal. | `app/proactive/evolution.py` — `record_feedback(kind, target, payload)`. Kinds: `KIND_THUMBS`, `KIND_EDIT`, `KIND_PREFERENCE`. Stored in `feedback.jsonl`. |
| **Optimization sandbox proposes a change.** Periodically (or on demand) the system reads the recent feedback + Ledger window and proposes a candidate constitution rule — e.g., "tighten the Governor for `external-network` because the deny-rate exceeds 50%." | Candidates appear in the "Pending evolution" subsection of Vitals. | `app/proactive/optimization.py` — `propose()` → list of candidates. Three built-in strategies: `tighten_governor`, `prune_quarantine`, `relax_constitution`. Tunables: `_DENY_RATE_THRESHOLD = 0.50`, `_DENY_MIN_SAMPLES = 4`, `_QUARANTINE_FAILURE_FLOOR = 5`, `_THUMBS_UP_TO_RELAX = 3`. |
| **Simulation.** Before applying, the candidate is replayed against a sandbox copy of state to estimate its effect. | "Predicted effect: 12 fewer auto-allows, 3 more consent requests" appears alongside the candidate. | `optimization.simulate_candidate(candidate, ledger, signals)` runs the candidate against a frozen state snapshot. |
| **Alignment validators run.** Each registered validator returns `accept` / `veto` / `abstain` with a reason. A single veto blocks the candidate. | Validator verdicts appear under the candidate. | `evolution.run_alignment(candidate) -> Verdict`. Built-ins: `recent_thumbs_down` (vetoes if recent thumbs-down on same target), `constitution_check` (vetoes if conflicts with existing rules — but skips governance kinds). Validators can be registered with `register_validator(name, fn)`. |
| **Promotion gate** is the apply step. Five terminal states: `applied` (success), `noop` (already in effect), `refused_by_validator`, `skipped_unknown_kind`, `apply_failed`. | The candidate row resolves to one of these; the result is written to the Ledger as `core.evolution.promotion`. | `app/proactive/promotion.py` — `promote(candidate, *, simulate=True)` chains simulate → run_alignment → apply. Built-in appliers: `constitution_rule_add` (idempotent), `constitution_rule_remove`. Custom appliers register via `register_applier(kind, fn)`. |

> No constitution rule is added without crossing every stage of this loop. If at any step the candidate is refused, it goes to the Ledger with the refusal reason — visible to you in the Vitals panel.

---

## 7. External integrations

The same gate-chain that protects internal actions protects external ones. Three integration surfaces:

### 7.1 MCP (Model Context Protocol)

| What it does for you | How it's built |
|---|---|
| Lets Numel **expose** its capabilities to other MCP-aware tools, and lets it **consume** tools other systems advertise. Either direction goes through the Substrate gates. | `app/proactive/mcp.py`. Server side: `list_tools_as_mcp()`, `call_tool(name, arguments)` chains Adversarial → Alignment → handler → Privacy. Five terminal states: `ok=True`, `unknown_capability`, `alignment_veto`, `not_implemented`, `handler_error`. Client side: `register_remote(server, tool_descriptor, scopes)` → registers as cap `mcp.<server>.<tool>`. Built-in handler for `core.notify`. |

### 7.2 A2A (Agent-to-Agent federation)

| What it does for you | How it's built |
|---|---|
| Lets Numel federate with other agents. Each peer is registered with a **trust tier**: *peer* (read-only access to public state), *partner* (read/write public state), *federated* (any namespace, with scoped delegation). Inbound messages run through the Adversarial gate; outbound state-shares run through the Privacy gate. | `app/proactive/a2a.py`. Trust gates: peer reads `core.public.*` only; partner reads/writes `core.*`; federated reads any. API: `register_peer(peer_id, *, tier, name, contact)`, `receive(peer_id, message, *, kind)` (with adversarial gate), `send(peer_id, message, *, kind)`, `share_state(peer_id, namespaces)` (with privacy gate). Logs: `a2a_inbox.jsonl`, `a2a_outbox.jsonl`, `a2a_shared.jsonl`. |

### 7.3 LLM transports

| What it does for you | How it's built |
|---|---|
| Lets Numel use external LLMs (OpenAI-compatible, Anthropic) as first-class capabilities. The Conscious layer can route a decision through Claude Sonnet by calling the bridge alias; the response goes back through the same Adversarial → Alignment → handler → Privacy chain that any internal capability does. API keys are loaded from environment variables at call time, never persisted. | `app/proactive/transports.py`. Two flavours: `openai` (Chat Completions, Bearer auth) + `anthropic` (Messages API, x-api-key auth). API: `register_transport(alias, *, kind, base_url, model, api_key_env, scopes, extra)`, `call_transport(alias, prompt, *, dry_run=False)`. Caps registered as `transport.<kind>.<alias>`. Default scopes: `["external-network", "spends-money"]` (high-stake on both axes). HTTP via `urllib.request` (no extra deps). `dry_run=True` returns a synthetic echo. |

---

## 8. Operating Numel — the Vitals panel walk-through

The Vitals panel (right sidebar of the workflow UI when a proactive workflow is loaded) is the operator's window into the system. Sections:

| Section | What you do with it | Wired to |
|---|---|---|
| **Header counters** | Glance the deny-rate, executed-count, consent-required count, refused count over the rolling window. Red means investigate. | `/proactive/vitals` |
| **Ledger (recent)** | Click any row to open the Why-chain detail modal. Thumbs-up / thumbs-down buttons inline. | `/proactive/ledger/recent`, `/proactive/feedback/record` |
| **World** | Browse what Numel currently believes. Namespaces collapse/expand. | `/proactive/world` |
| **Capabilities** | What's registered, what's allowed, what was used recently. | `/proactive/capabilities` |
| **Constitution** | The current rule set. Add a rule manually here (it goes through the same promotion gate as auto-proposals). | `/proactive/constitution`, `/proactive/promotion/promote` |
| **Pending evolution** | Auto-proposed changes awaiting promotion. Approve / reject inline. | `/proactive/optimization/propose`, `/proactive/promotion/promote` |
| **MCP** | Connected MCP tools (server + client side). Recent tool calls. | `/proactive/mcp/*` |
| **Federation (A2A)** | Registered peers. Inbox / outbox / shared excerpts (3 most recent each). | `/proactive/a2a/*` |
| **LLM transports** | Registered bridges. Recent call traces. **"Test"** button does a `dry_run=True` round-trip. | `/proactive/transports/*` |

### Common operations, end-to-end

| You want to… | What to click | What happens under the hood |
|---|---|---|
| **Approve a pending action.** | The Approve button on a `consent_required` row. | Social layer pulls the request from `consent_requests.json`, marks it approved, emits a Ledger entry; Motor layer, on its next pass, picks it up and invokes the capability. |
| **Reject a pending action.** | Reject button. | Social layer marks rejected; Motor never sees it; Ledger gets a `consent_rejected` entry. |
| **Inspect why something happened.** | Click any Ledger row. | Modal opens showing the entry's full Why-chain (candidate → simulation → alignment.verdicts → applied → motor_status → social_consent_request → provenance). |
| **Give feedback on an action.** | Thumbs-up or thumbs-down on a Ledger row. | `record_feedback(kind=KIND_THUMBS, target=<entry_id>, payload={"value": ±1})`. Used by Optimization sandbox to propose tightening / relaxing rules. |
| **Add a constitution rule manually.** | "Add rule" in Constitution section. | Goes through `promote(candidate=..., simulate=True)` like any auto-proposal. |
| **Roll back a bad evolution.** | Snapshots → Restore. | Restores the full state directory from a tar-zipped snapshot. |
| **Quarantine cleanup.** | Quarantine subsection → Release / Purge. | `quarantine.release(id)` re-injects to the Ledger; `purge_older_than(days)` deletes expired entries. |
| **Test an LLM bridge without spending tokens.** | LLM transports → Test on the bridge row. | Calls `call_transport(alias, prompt, dry_run=True)` — synthetic echo, no network. |

---

## 9. Reference

### 9.1 File inventory

| File | Purpose |
|---|---|
| `app/proactive/middleware.py` | Veracity / Privacy / Adversarial gates |
| `app/proactive/__init__.py` | World Model, Goal Hierarchy, Capability Registry, Governor, Vitals, Ledger (the eight Substrate facets) |
| `app/proactive/quarantine.py` | Quarantine + Snapshots |
| `app/proactive/evolution.py` | Feedback + Constitution + Validators + `Verdict` |
| `app/proactive/optimization.py` | Sandbox + propose + simulate_candidate |
| `app/proactive/promotion.py` | Promotion gate (5 terminal states) |
| `app/proactive/mcp.py` | MCP server + client |
| `app/proactive/a2a.py` | A2A federation (3 trust tiers) |
| `app/proactive/transports.py` | OpenAI + Anthropic LLM bridges |
| `app/proactive/persistence.py` | Atomic JSON write, JSONL append (the only leaf module) |
| `web/numel-proactive-vitals.js` | The Vitals panel |
| `examples/proactive-substrate-stub.json` | Substrate-only scaffold (no agent layers) |
| `examples/proactive-substrate-persistent.json` | Substrate stub with disk persistence |
| `examples/proactive-sensory-slice.json` | Sensory layer + Substrate |
| `examples/proactive-vertical-slice.json` | All four layers, deterministic Conscious |
| `examples/proactive-vertical-slice-agentic.json` | All four layers, LLM-backed Conscious via transport bridge |
| `tools/lint_transforms.py` | AST linter for `transform_flow` script hazards |
| `tools/smoke_proactive.py` | 11-check smoke suite (in-process + integration) |
| `tools/git-hooks/pre-commit` | Runs the linter on staged transforms |
| `docs/transform-flow-scripts.md` | Reference for the `exec()` split-namespace gotchas |
| `docs/proactive-architecture.md` | Eight Mermaid diagrams of the system |
| `examples/proactive-CHANGELOG.md` | Living change log of the Proactive work |

### 9.2 Persistence inventory

| File on disk | Owner | Shape |
|---|---|---|
| `world_model.json` | World Model | nested dict by namespace |
| `goals.json` | Goal Hierarchy | `{"standing", "active": [...]}` |
| `capability_registry.json` | Capability Registry | `{"<name>": {"scopes", "handler"}}` |
| `constitution.json` | Evolution | `{"rules": [{"id", "kind", "payload"}]}` |
| `consent_requests.json` | Social | pending requests |
| `ledger.jsonl` | Ledger | append-only event log |
| `feedback.jsonl` | Evolution | append-only feedback log |
| `quarantine.jsonl` | Quarantine | append-only |
| `snapshots/<ts>.tar.gz` | Snapshots | full state tarball |
| `mcp_calls.jsonl` | MCP | call audit log |
| `a2a_peers.json` | A2A | peer registry |
| `a2a_inbox.jsonl` / `outbox.jsonl` / `shared.jsonl` | A2A | message logs |
| `transport_calls.jsonl` | Transports | call audit log |

State directory is rooted at `NUMEL_PROACTIVE_DIR` (default `./proactive_state/`).

### 9.3 HTTP endpoints (POST, all of them)

Approximately 40 endpoints; see `docs/proactive-architecture.md` §7 for a milestone-grouped diagram. Highlights:

- Substrate: `/proactive/world`, `/proactive/capabilities`, `/proactive/governor/gate`, `/proactive/ledger/recent`, `/proactive/vitals`
- Quarantine: `/proactive/quarantine/list`, `/release`, `/purge`
- Evolution: `/proactive/feedback/record`, `/list`, `/proactive/constitution`, `/proactive/optimization/propose`, `/proactive/promotion/promote`
- External: `/proactive/mcp/*`, `/proactive/a2a/*`, `/proactive/transports/*`

### 9.4 Glossary

| Term | Meaning |
|---|---|
| **Candidate** | A proposed intent emitted by the Conscious layer. Not yet acted on. |
| **Capability** | A named, scoped, gated action Numel can take. |
| **Constitution** | The set of declarative rules Numel enforces. Mutable only through Evolution. |
| **Gate** | A pure function that classifies or transforms a payload (Veracity / Privacy / Adversarial / Governor). |
| **Ledger** | The append-only event log; also the implicit bus. |
| **Scope** | A tag attached to a capability; the Governor reads scopes to decide consent. |
| **Standing Goal** | The seeded long-lived goal the system pursues. |
| **Trust tier** | A2A peer classification: peer / partner / federated. |
| **Verdict** | An alignment-validator result: accept / veto / abstain (+ reason). |
| **Why-chain** | The full reasoning trace attached to a Ledger entry. |

### 9.5 How this guide relates to the other proactive docs

- **`~/Desktop/proactive.md`** — *what* the system is and *why* it's shaped this way (conceptual blueprint).
- **`~/Desktop/proactive-technical.md`** — *exhaustive* engineer-facing spec (every API, every persistence file, every endpoint).
- **[docs/proactive-architecture.md](proactive-architecture.md)** — visual: eight Mermaid diagrams.
- **This document** — *bridge*: user-prose spine + technical sidebars, walks through what you actually see and do.
- **[examples/proactive-CHANGELOG.md](../examples/proactive-CHANGELOG.md)** — what changed when, since 2026-04-28.

Read in this order on a first pass: this guide → the architecture diagrams → the conceptual blueprint → (only if you're building on top of it) the technical spec.
