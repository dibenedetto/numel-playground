# Proactive Agent Ecology — Visual architecture

Eight Mermaid diagrams, each one capturing a different view of the system. Read in order for an end-to-end walkthrough; jump in by section if you already know the surface.

The conceptual blueprint is at `~/Desktop/proactive.md`; the engineer-facing spec is at `~/Desktop/proactive-technical.md`. This document is the picture-book companion.

---

## 1. Big picture — what's where

Everything the system contains, grouped by Phase. Boxes that touch the dotted "Storage" plate persist state on disk.

```mermaid
flowchart TB
    classDef substrate fill:#1d3557,stroke:#457b9d,color:#f1faee
    classDef layer     fill:#2a4d3a,stroke:#52b788,color:#ecf8f0
    classDef evo       fill:#553a78,stroke:#9d7ab9,color:#f4eef9
    classDef ext       fill:#6b3f2a,stroke:#c97a52,color:#fff1e7
    classDef store     fill:#262a35,stroke:#586478,color:#c5d0dc

    subgraph PH1["Phase 1 + 3 — Substrate"]
        direction TB
        MID["Middleware<br/>Veracity / Privacy / Adversarial"]:::substrate
        WM["World Model"]:::substrate
        GH["Goal Hierarchy"]:::substrate
        CR["Capability Registry"]:::substrate
        GOV["Governor"]:::substrate
        VIT["Vitals"]:::substrate
        QUAR["Quarantine + Snapshots"]:::substrate
        LED["Ledger (the bus)"]:::substrate
    end

    subgraph PH2["Phase 2 — Agent layers"]
        direction LR
        SEN["Sensory"]:::layer
        CON["Conscious"]:::layer
        MOT["Motor"]:::layer
        SOC["Social"]:::layer
    end

    subgraph PH4["Phase 4 — Evolution"]
        direction TB
        ALIGN["Alignment validators<br/>+ User Constitution"]:::evo
        OPT["Optimization sandbox<br/>+ strategies + simulator"]:::evo
        PROMO["Promotion gate"]:::evo
    end

    subgraph PH5["Phase 5 — External integrations"]
        direction TB
        MCP["MCP bridge"]:::ext
        A2A["A2A federation<br/>peer / partner / federated"]:::ext
        TRN["LLM transports<br/>OpenAI-compat + Anthropic"]:::ext
    end

    subgraph STORAGE["Persistence — app/storage/proactive/"]
        direction LR
        F1[("ledger.jsonl")]:::store
        F2[("world_model.json")]:::store
        F3[("goals / capabilities / quarantine .json")]:::store
        F4[("alignment_signals.jsonl<br/>user_constitution.json")]:::store
        F5[("mcp / a2a / transport logs")]:::store
        F6[("snapshots/<id>/")]:::store
    end

    PH2 --> PH1
    PH5 --> PH1
    PH4 --> PH1
    PH1 --> STORAGE
    PH4 --> STORAGE
    PH5 --> STORAGE
```

---

## 2. Signal flow — one inbound observation, end to end

Trace what happens to a single email arriving via the synthetic-inbox sensor. Solid edges = data; dashed edges = side reads from state files.

```mermaid
flowchart LR
    classDef gate    fill:#1d3557,stroke:#457b9d,color:#f1faee
    classDef store   fill:#262a35,stroke:#586478,color:#c5d0dc
    classDef sig     fill:#5a3939,stroke:#a05050,color:#ffeaea
    classDef act     fill:#2a4d3a,stroke:#52b788,color:#ecf8f0

    SIG["Inbound signal<br/>(email / webhook / timer / channel)"]:::sig

    SIG --> VER["Veracity gate<br/>+ provenance + confidence"]:::gate
    VER --> PRI["Privacy gate<br/>(redact PII / secrets)"]:::gate
    PRI --> ADV["Adversarial filter<br/>untrusted_content envelope"]:::gate
    ADV --> WM[("World Model")]:::store

    WM --> CON["Conscious<br/>(reads WM + goals)"]:::act
    GOALS[("goals.json")]:::store -.reads.-> CON
    VIT2[("vitals (computed)")]:::store -.reads.-> CON

    CON -- "intent envelope" --> CR["Capability Registry<br/>(scope folding)"]:::gate
    CAPS[("capabilities.json")]:::store -.reads.-> CR

    CR --> GOV["Governor<br/>(allow / consent / deny)"]:::gate
    QUAR[("quarantine.json")]:::store -.reads.-> GOV

    GOV -- allow --> MOT["Motor<br/>(execute capability)"]:::act
    GOV -- consent_required --> SOC["Social<br/>(park as pending)"]:::act
    GOV -- deny --> LED[("Ledger.jsonl")]:::store

    MOT --> LED
    SOC --> LED
    LED --> VIT["Vitals<br/>(computed lazily)"]:::act
```

**Key invariants:**

* Inbound signals **never bypass** Middleware — Sensory writes through it.
* Conscious-emitted intents re-enter the Substrate at Capability-Registry; they're treated like any other envelope.
* Governor reads quarantine state on every decision; quarantined capabilities are denied without further checks.
* Every terminal branch (allow / consent / deny) writes to the Ledger. Vitals reads it back on demand.

---

## 3. Substrate components — read/write contract

Compact reference for "who reads what, who writes what." Each component is a JSON file or computed view.

```mermaid
flowchart TB
    classDef store  fill:#262a35,stroke:#586478,color:#c5d0dc
    classDef gate   fill:#1d3557,stroke:#457b9d,color:#f1faee

    subgraph PER["proactive.persistence (atomic JSON / append-only JSONL)"]
        WM[("world_model.json")]:::store
        GOALS[("goals.json")]:::store
        CAPS[("capabilities.json")]:::store
        LED[("ledger.jsonl")]:::store
        QUAR[("quarantine.json")]:::store
        SIGS[("alignment_signals.jsonl")]:::store
        CONST[("user_constitution.json")]:::store
        SNAPS[("snapshots/<id>/")]:::store
    end

    MID["Middleware<br/>(stateless gates)"]:::gate
    GOV["Governor<br/>(decision logic)"]:::gate
    VIT["Vitals<br/>(lazy computation)"]:::gate

    MID -- writes provenance --> LED
    MID -- writes payload --> WM

    GOV -- reads --> CAPS
    GOV -- reads --> QUAR
    GOV -- writes verdict --> LED
    GOV -- record_failure / record_success --> QUAR

    VIT -- aggregates --> LED

    SNAPS -. take/restore .- WM
    SNAPS -. take/restore .- GOALS
    SNAPS -. take/restore .- CAPS
    SNAPS -. take/restore .- LED
    SNAPS -. take/restore .- QUAR
    SNAPS -. take/restore .- SIGS
    SNAPS -. take/restore .- CONST
```

---

## 4. Evolution loop — Phase 4 in motion

How a candidate change gets from "the system thinks something should change" to "the change actually shipped or got refused." The whole flow runs offline (sandboxed); the only side-effect on production is a Ledger entry.

```mermaid
flowchart LR
    classDef evo    fill:#553a78,stroke:#9d7ab9,color:#f4eef9
    classDef store  fill:#262a35,stroke:#586478,color:#c5d0dc
    classDef gate   fill:#1d3557,stroke:#457b9d,color:#f1faee
    classDef out    fill:#2a4d3a,stroke:#52b788,color:#ecf8f0
    classDef bad    fill:#5a3939,stroke:#a05050,color:#ffeaea

    LED1[("ledger.jsonl")]:::store --> STRAT["Self-Reflective strategies<br/>tighten_governor<br/>prune_quarantine<br/>relax_constitution"]:::evo
    QUAR1[("quarantine.json")]:::store --> STRAT
    SIGS[("alignment_signals.jsonl")]:::store --> STRAT
    CONST1[("user_constitution.json")]:::store --> STRAT

    STRAT --> CAND["Candidate<br/>{kind, target, payload, rationale}"]:::evo

    CAND --> SIM["simulate_candidate()<br/>replay ledger under hypothesis"]:::evo
    SIM --> GATE["Promotion gate<br/>promote(candidate)"]:::evo

    GATE --> RUNALIGN["run_alignment()<br/>every registered validator"]:::gate
    RUNALIGN -- pass --> APPLIER["Kind-specific applier<br/>constitution_rule_add<br/>constitution_rule_remove"]:::evo
    RUNALIGN -- veto --> REFUSED["refused_by_validator"]:::bad

    APPLIER -- writes --> CONST2[("user_constitution.json (v+1)")]:::store
    APPLIER --> APPLIED["applied / noop / apply_failed"]:::out

    APPLIED --> LED2[("Ledger entry<br/>topic: core.evolution.promotion")]:::store
    REFUSED --> LED2
```

**Five terminal `decision` states** every promotion lands on:

| State | Meaning |
|---|---|
| `applied` | Alignment passed, change took effect, constitution version bumped |
| `noop` | Alignment passed, but the change was already in effect (idempotent) |
| `refused_by_validator` | At least one validator vetoed; nothing applied |
| `skipped_unknown_kind` | Alignment passed but no applier is registered for `candidate.kind` |
| `apply_failed` | Applier raised or returned failure |

---

## 5. External integrations — Phase 5 surface

Three protocol bridges, all routed through the Substrate's Adversarial → Alignment → Privacy chain.

```mermaid
flowchart LR
    classDef ext    fill:#6b3f2a,stroke:#c97a52,color:#fff1e7
    classDef gate   fill:#1d3557,stroke:#457b9d,color:#f1faee
    classDef store  fill:#262a35,stroke:#586478,color:#c5d0dc
    classDef peer   fill:#1e3a5f,stroke:#5085c0,color:#dbe9ff

    PEER1["External MCP client"]:::peer --> MCP_OUT["MCP bridge<br/>list_tools_as_mcp / call_tool"]:::ext
    PEER2["External MCP server"]:::peer --> MCP_IN["MCP bridge<br/>register_remote"]:::ext
    PEER3["Federated peer (peer/partner/federated)"]:::peer --> A2A_IN["A2A bridge<br/>receive / share_state"]:::ext
    LLM["External LLM<br/>(OpenAI-compat / Anthropic)"]:::peer --> TRN["Transports<br/>register_transport / call_transport"]:::ext

    MCP_OUT --> ADV["Adversarial filter on args"]:::gate
    A2A_IN  --> ADV
    TRN     --> ADV

    ADV --> ALIGN["Alignment chain<br/>(every validator)"]:::gate
    ALIGN --> HANDLER["Handler dispatch<br/>(MCP handler / A2A receive log /<br/>transport HTTP call or dry-run)"]:::ext
    HANDLER --> PRI["Privacy gate on response"]:::gate
    PRI --> CALLER["Response back to caller"]:::ext

    MCP_IN --> CAPS[("capabilities.json<br/>mcp.<server>.<tool>")]:::store
    TRN    --> CAPS2[("capabilities.json<br/>transport.<kind>.<alias>")]:::store

    A2A_IN -. reads .-> WM[("world_model.json")]:::store
    A2A_IN --> SHARED[("a2a_shared.jsonl<br/>(redacted excerpts)")]:::store
```

**Trust tier reading rules (A2A):**

| Tier | World Model namespaces visible |
|---|---|
| `peer` | `core.public.*` only |
| `partner` | any `core.*` |
| `federated` | any namespace |

All shared excerpts pass through Privacy gate before leaving the system.

---

## 6. Module dependency graph

Top-down view of the Python module tree under `app/proactive/`. Every module imports `persistence`; nothing else has cycles.

```mermaid
flowchart TB
    classDef root  fill:#262a35,stroke:#586478,color:#c5d0dc
    classDef mod   fill:#1d3557,stroke:#457b9d,color:#f1faee

    PER["persistence.py<br/>state_dir / read/write JSON+JSONL"]:::root

    MID["middleware.py<br/>Veracity / Privacy / Adversarial"]:::mod
    QUAR["quarantine.py<br/>failure tracker + snapshots"]:::mod
    EV["evolution.py<br/>signals + constitution + validator chain"]:::mod
    OPT["optimization.py<br/>sandbox + strategies + simulator"]:::mod
    PROMO["promotion.py<br/>chained simulate→align→apply"]:::mod
    MCP["mcp.py<br/>tool list/call/remote"]:::mod
    A2A["a2a.py<br/>peers + trust tiers + share_state"]:::mod
    TRN["transports.py<br/>OpenAI-compat + Anthropic bridges"]:::mod

    MID --> PER
    QUAR --> PER
    EV --> PER
    OPT --> PER
    OPT --> EV
    OPT --> QUAR
    PROMO --> PER
    PROMO --> EV
    PROMO --> OPT
    MCP --> PER
    MCP --> MID
    MCP --> EV
    A2A --> PER
    A2A --> MID
    TRN --> PER
    TRN --> MCP
```

`persistence.py` is the only leaf. Everything stacks on top.

---

## 7. HTTP surface — endpoints under `/proactive/*`

The full API surface, grouped by milestone. All POST. All gate-routed where relevant.

```mermaid
flowchart LR
    classDef hdr   fill:#1d3557,stroke:#457b9d,color:#f1faee,font-weight:bold
    classDef ep    fill:#262a35,stroke:#586478,color:#c5d0dc

    M3["M3.3 Vitals UI"]:::hdr
    M3 --> e1["/vitals"]:::ep
    M3 --> e2["/ledger"]:::ep

    M34["M3.4 Quarantine + Snapshots"]:::hdr
    M34 --> e3["/quarantine"]:::ep
    M34 --> e4["/quarantine/release"]:::ep
    M34 --> e5["/snapshots"]:::ep
    M34 --> e6["/snapshot/take"]:::ep
    M34 --> e7["/snapshot/restore"]:::ep
    M34 --> e8["/snapshot/delete"]:::ep

    M41["M4.1 Alignment"]:::hdr
    M41 --> e9["/feedback"]:::ep
    M41 --> e10["/feedback/list"]:::ep
    M41 --> e11["/constitution"]:::ep
    M41 --> e12["/constitution/update"]:::ep
    M41 --> e13["/alignment/validators"]:::ep
    M41 --> e14["/alignment/check"]:::ep

    M42["M4.2 Optimization"]:::hdr
    M42 --> e15["/optimization/propose"]:::ep
    M42 --> e16["/optimization/simulate"]:::ep

    M43["M4.3 Promotion"]:::hdr
    M43 --> e17["/promotion/promote"]:::ep

    M51["M5.1 MCP"]:::hdr
    M51 --> e18["/mcp/tools"]:::ep
    M51 --> e19["/mcp/call"]:::ep
    M51 --> e20["/mcp/register_remote"]:::ep
    M51 --> e21["/mcp/remote_tools"]:::ep
    M51 --> e22["/mcp/drop_remote"]:::ep
    M51 --> e23["/mcp/calls"]:::ep

    M52["M5.2 A2A"]:::hdr
    M52 --> e24["/a2a/peers"]:::ep
    M52 --> e25["/a2a/peers/register"]:::ep
    M52 --> e26["/a2a/peers/drop"]:::ep
    M52 --> e27["/a2a/receive"]:::ep
    M52 --> e28["/a2a/send"]:::ep
    M52 --> e29["/a2a/share_state"]:::ep
    M52 --> e30["/a2a/inbox /outbox /shared"]:::ep

    M53["M5.3 Transports"]:::hdr
    M53 --> e31["/transports"]:::ep
    M53 --> e32["/transports/register"]:::ep
    M53 --> e33["/transports/drop"]:::ep
    M53 --> e34["/transports/call"]:::ep
    M53 --> e35["/transports/calls"]:::ep
```

---

## 8. The Why-chain — what the Ledger captures

Every entry in `ledger.jsonl` is a complete audit record. Different topics carry different field sets, but they all share the spine: `id` · `ts` · `correlation_id` · `trigger.topic` · `provenance[]`. Promotion entries additionally carry the full `simulation` + `alignment.verdicts` + `applied` chain.

```mermaid
flowchart LR
    classDef trig   fill:#1d3557,stroke:#457b9d,color:#f1faee
    classDef field  fill:#262a35,stroke:#586478,color:#c5d0dc
    classDef extra  fill:#553a78,stroke:#9d7ab9,color:#f4eef9

    LED["Ledger entry"]:::trig

    LED --> id["id (led_N)"]:::field
    LED --> ts["ts"]:::field
    LED --> corr["correlation_id"]:::field
    LED --> trig["trigger.topic"]:::field
    LED --> prov["provenance[]<br/>{stage, ...} per gate"]:::field

    trig --> T1["core.middleware.input_received"]:::extra
    trig --> T2["core.sensory.observation"]:::extra
    trig --> T3["core.motor.action_attempt"]:::extra
    trig --> T4["core.evolution.promotion"]:::extra

    T3 --> verdict["governor_verdict<br/>{decision, reason, scopes,<br/>confidence, capability}"]:::field
    T3 --> motor["motor_status<br/>(executed / deferred / no_action)"]:::field
    T3 --> social["social_consent_request<br/>(if consent_required)"]:::field

    T4 --> cand["candidate"]:::field
    T4 --> sim["simulation"]:::field
    T4 --> align["alignment{decision, verdicts[]}"]:::field
    T4 --> appl["applied{status, ...}"]:::field
    T4 --> dec["decision (applied/noop/refused/skipped/apply_failed)"]:::field

    LED --> outc["expected_outcome / actual_outcome"]:::field
```

Click any Ledger row in the **Vitals** sidebar to see one of these entries pretty-printed in full.

---

## Reading guide

If you want… | start at
---|---
A 30-second mental model | §1 (big picture)
"How does a webhook turn into an action?" | §2 (signal flow)
"What's persisted, who writes it?" | §3 (substrate read/write contract) + §7.1 of `proactive-technical.md`
"How does the system improve itself?" | §4 (Evolution loop)
"How do I plug an external LLM in?" | §5 (External integrations) + §3.4 of `proactive-technical.md`
"What can I extend?" | §6 (module deps) + §9 of `proactive-technical.md`
"What endpoint should I call?" | §7 (HTTP surface)
"What's in a Ledger entry?" | §8 (Why-chain) + a click on any row in Vitals
