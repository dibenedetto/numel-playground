# Architectural Blueprint: The Proactive AI Agent Ecology (v3)

A multi-layered system that observes, acts, talks, and anticipates — built on a shared substrate that enforces safety, budget, and alignment, and whose every component is designed to be extended later without forking the core.

*This document is the **conceptual blueprint** — it describes roles, intent, and behavior. Implementation details (interfaces, schemas, runtime model, persistence, protocol integration) are in the companion technical specification.*

---

## Part I — Substrate

*Cross-cutting machinery every agent depends on. Each section ends with an **Open:** note flagging where the system is designed to grow.*

### 1. Cross-Cutting Middleware

Every signal entering or leaving an agent passes through this row.

* **Provenance / Veracity Gate** — truth scoring + source attribution.
* **Privacy / Redaction Gate** — strips PII/secrets per per-source policy *before* any LLM call.
* **Adversarial-Input Filter** — wraps sensed content in an *untrusted-content envelope*; instructions inside it are never executed.

**Open:** new gates can be inserted into the pipeline (e.g. compliance, legal review, data-loss prevention). Order is declared, not hardcoded.

### 2. Shared World Model

A single, queryable belief store all Sensory agents write into and all other layers read from. Tracks identity, location, calendar state, focus mode, mood, attention availability.

**Open:** new namespaces for new domains live alongside the built-ins without colliding with them.

### 3. Goal Hierarchy

Three tiers (`Tasks`, `Projects`, `Standing Goals`), each with lifecycle (`active` / `paused` / `abandoned` / `done`). All Proactive behavior is anchored here.

**Open:** new goal *types* (recurring, conditional, joint) and new lifecycle states can be introduced without disturbing the existing tree.

### 4. Capability Registry

Authoritative catalog of every tool. Each entry declares its purpose, surface, scopes (`read-only` / `write` / `external-network` / `spends-money` / `impersonates-user` / `affects-third-party`), latency tier, and cost.

**Open:** tools register at runtime; orgs and partners contribute new tools alongside built-ins.

### 5. Governor

Single budget and safety enforcement point in front of every action.

* **Cost & latency budgets** (per task / per day / per scope).
* **Action-class × Confidence gate** — high-stake scopes require consent regardless of confidence.
* **Attention budget / throttling** — caps notifications, respects quiet-hours and focus-mode, coalesces queued items.
* **Quarantine / Freeze** — pauses a subgraph indefinitely after repeated failure.

**Open:** action classes, throttling policies, and quarantine triggers are pluggable rule sets — orgs can add `regulatory.medical`, `personal.financial`, etc.

### 6. Vitals (Self-Monitoring)

Live health surface: per-agent latency, tool error rate, agent disagreement, hallucination rate, drift. Consumed by the Conscious layer's Self-Reflective Agent and by the Governor for quarantine.

**Open:** new metrics and dashboards can be added at any time; no metric is hardcoded.

---

## Part II — Agent Layers

*The four layers are a **convention**, not a closed list. New layers may be inserted (e.g. an `Embodiment` layer for robotics, a `Financial` layer for spending control) provided they declare their position and what World Model namespaces they read/write.*

### 7. Sensory Layer (Passive)

Observe, ingest, organize. Outputs flow through Middleware before reaching the World Model.

* RAG · Recommender · Summarizer · Search · Context-Aware · Pattern Recognition · Sentiment / State

**Open:** new sensors register here.

### 8. Motor Layer (Active)

Execute and manipulate environments. Every action passes through the Governor.

* Operative · Orchestrator · Self-Healing · Scheduling / Trigger

**Open:** new actuators register here.

### 9. Social Layer (Interactive)

* User-Interactive · Clarification · Multi-Party Mediator · Persona / Adaptive

**Open:** new social agents (e.g. `negotiator`, `coach`, `tutor`) register here.

### 10. Conscious Layer (Proactive)

* Anticipatory · Self-Reflective · Probe-Sensory (back-edge: tasks Sensory on demand)

**Open:** new metacognitive agents (e.g. `risk-forecaster`, `goal-conflict-resolver`) register here.

---

## Part III — Lifecycle

### 11. Evolution Strategy (Chained)

Autonomous change is never independent of user signal.

#### Phase 1 — Alignment (always-on, online)

* Explicit Feedback · Implicit Behavioral Analysis · Preference Vectoring (User Constitution)

**Open:** new Alignment validators (e.g. org-policy check, safety classifier) plug in; each can independently veto a Phase-2 output.

#### Phase 2 — Optimization (offline, sandboxed)

* Self-Reflective Debugging · Synthetic Self-Play / Simulation · Modular Upgrading

**Gate:** No Phase-2 output ships to production without an Alignment-pass record from *every registered* Phase-1 validator.

---

## Part IV — Operational Philosophy: Silent but Traceable

| Feature                    | Execution Style          | Visibility                           | Gate                                                |
| :------------------------- | :----------------------- | :----------------------------------- | :-------------------------------------------------- |
| Routine optimization       | Silent / background      | Ledger entry                         | Confidence ≥ threshold **and** low-class action     |
| Evolutionary updates       | Silent / background      | Ledger + Why-chain + Alignment-pass  | Every Phase-1 validator must approve                |
| High-stake actions         | Active (requires consent)| Full UI notification                 | Action-class gate triggers regardless of confidence |
| System errors              | Self-healing first       | Ledger; alert if persistent          | Auto-quarantine after N retries                     |
| Untrusted-source actuation | Refused                  | Ledger + flag                        | Adversarial-Input Filter blocks                     |
| Outside attention budget   | Deferred / coalesced     | Single digest at next allowed window | Throttling rule (Governor)                          |

### The Agent Ledger (Observability)

* **Traceable Logs** — every autonomous change recorded.
* **Why-Chain** — each entry: trigger, alternatives considered, decision rationale, expected outcome, actual outcome (filled post-hoc).
* **Audit & Rollback** — branch-restore to any prior Known Good State.
* **Confidence-and-Class Threshold** — falls back to Interactive layer when *either* confidence is low *or* action class is high-stake.
* **Bidirectional Flow** — Conscious tasks Sensory (probe), Vitals pauses any layer via Governor, Governor refuses any layer's request.

**Open:** new ledger event types and downstream consumers (audit dashboards, compliance exporters) can be added over time.

---

**Summary of changes from v2**

* Each Substrate section ends with a short, conceptual **Open:** note describing where the system is designed to grow.
* Agent layers reframed as *conventions* — new layers may be inserted with a declared position on the bus.
* Implementation details (manifests, schemas, versioning rules, namespacing, deployment lifecycle, federation transports) are deferred to a separate technical specification, so this document stays focused on intent and behavior.
