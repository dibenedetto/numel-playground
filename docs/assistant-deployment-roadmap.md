# Numel Assistant Deployment Roadmap

_Last updated: April 16, 2026_

This document defines the concrete roadmap slice for capturing the most useful
OpenClaw-style strengths inside Numel without turning Numel into a copy of
OpenClaw.

The core idea is:

> Numel should adopt **assistant deployment**, **multi-agent routing**,
> **proactive behavior**, and **operator controls** as first-class product
> features, while keeping its center of gravity on spaces, workflows,
> knowledge, and publishable apps.

This is not a parity roadmap. It is a **selective adoption roadmap**.

## Why This Matters

OpenClaw is strongest where assistants must:

- live in real messaging channels
- stay active over time
- react to events and schedules
- hand work to the right specialist
- be operated and supervised safely

Numel already has many of the primitives:

- channels
- workflows
- toolkits
- skills
- planners
- event sources
- background tasks
- user identity and quotas
- local and production runtime slices

What Numel lacks is not mainly raw capability. It lacks a **coherent product
layer for deployed assistants**.

That is what this roadmap provides.

## Product Goal

After these milestones, Numel should be able to say:

> Build an assistant in a space, connect it to tools and knowledge, deploy it
> to chat channels, let it run proactively, route work across specialists, and
> operate it safely from one product surface.

That is the OpenClaw-strength layer worth adding.

## What We Are Deliberately Not Trying To Do

This roadmap does **not** aim to make Numel primarily:

- a chat gateway
- a messaging-first product
- a replacement for the visual workflow model
- a reduction of spaces/projects into pure assistant threads

Numel should still remain strongest as:

- a visual workflow and agent workbench
- a space/project-centric product
- a workflow-to-app platform

## Design Rule

Every milestone must pass this test:

- if it strengthens assistant deployment while preserving workflows, spaces,
  knowledge, and apps, it is in scope
- if it pushes Numel toward being only a chat assistant shell, it is out of
  scope

## The 6 Milestones

## 1. Assistant Deployment Model

### Goal

Introduce a first-class product object that says:

- which assistant is being deployed
- from which space
- using which workflow or agent config
- with which tools, skills, channels, memory, and runtime settings

### Why It Matters

Right now, Numel has the underlying pieces, but not a durable object that feels
like “this is a deployed assistant”.

OpenClaw’s product coherence starts here.

### Deliverables

- a new **Assistant Deployment** concept
- persistent deployment records
- deployment status, target channels, enabled capabilities, and owner info
- explicit linkage to a space and workflow
- a clear distinction between:
  - editable assistant design
  - deployed assistant instance

### Public vs Prod

- public/local:
  - deployment model
  - local deployment records
  - basic lifecycle actions
- prod:
  - hardened execution/runtime policies
  - stronger channel/session reliability

### Worth

**Very high.**

This is the foundation for everything else.

## 2. Channel Deployment UX

### Goal

Make “deploy this assistant to Telegram/Discord/etc.” a top-level product flow,
not a low-level wiring exercise.

### Why It Matters

Numel already has channel primitives, but they do not yet feel like a first
class deployment experience.

### Deliverables

- “Deploy Assistant” flow in the UI
- per-channel deployment settings
- test/send/connect validation
- deployment health state
- channel-specific instructions and identity mapping

### User Outcome

A user can move from:

- space
- workflow
- assistant config

to:

- a reachable assistant in one or more real channels

without assembling the entire mental model manually.

### Public vs Prod

- public/local:
  - deployment UX
  - local/reference adapters
  - testable reference behavior
- prod:
  - stronger delivery guarantees
  - production secrets hardening
  - resilient connection and failure handling

### Worth

**Very high.**

This is the first milestone users will actually feel.

## 3. Multi-Agent Routing And Handoffs

### Goal

Allow one deployed assistant to delegate to specialist assistants or workflows.

### Why It Matters

This is one of the most valuable OpenClaw-like capabilities. It lets Numel move
from “one assistant with many tools” to “an assistant system”.

### Deliverables

- assistant roles and profiles
- routing rules based on:
  - channel
  - intent
  - user
  - event type
  - workflow context
- handoff records
- specialist assistants for distinct functions, for example:
  - research
  - scheduling
  - support triage
  - knowledge ingestion

### Product Constraint

Routing should stay visible and inspectable. Numel should not turn it into a
black box. A user should be able to understand:

- who handled the request
- why the handoff happened
- what specialist ran

### Public vs Prod

- public/local:
  - routing model
  - basic handoffs
  - inspectable traces
- prod:
  - stronger throughput and reliability
  - production governance and auditing depth

### Worth

**Very high.**

This creates real differentiation.

## 4. Proactive And Scheduled Assistant Behavior

### Goal

Make proactive assistants a core product feature rather than a scattered set of
event/task primitives.

### Why It Matters

Many valuable assistants are not only reactive. They:

- check inboxes
- poll systems
- react to file changes
- follow up on timers
- trigger workflows on events

Numel already has the ingredients. It needs a clearer product layer.

### Deliverables

- assistant-level schedules
- assistant-level event subscriptions
- proactive task definitions attached to deployments
- proactive triggers expressed as real workflow source nodes plus `event_listener_flow`, not hidden timer-only config
- deployment UI support for both scheduled and event-driven proactive tasks
- pause/resume controls
- basic recurrence summaries visible in the UI

### Example Use Cases

- check an email inbox every 15 minutes
- watch a folder and ingest relevant files into knowledge
- follow up on overdue tasks daily
- summarize channel activity every morning

### Public vs Prod

- public/local:
  - schedules and event bindings
  - local/reference execution
- prod:
  - stronger runtime durability
  - hardened retry policies
  - stronger retention and observability

### Worth

**Very high.**

This makes assistants feel alive instead of purely conversational.

## 5. Approval, Interruption, And Safety Controls

### Goal

Make it safe to let assistants act, especially outside the web console.

### Why It Matters

As soon as assistants can:

- run proactively
- use tools
- operate across channels
- perform delegated actions

they need explicit control points.

### Deliverables

- approval-required tool call flows
- per-deployment safety policies
- interrupt/stop controls
- pending approval queue
- explainable action summaries before execution

### Product Principle

The assistant should feel powerful but never opaque.

Users should know:

- what it wants to do
- why
- whether approval is required
- how to stop it cleanly

### Public vs Prod

- public/local:
  - visible approval and interruption model
  - reference-grade safety UX
- prod:
  - stronger audit depth
  - support and operational controls
  - production-grade policy enforcement

### Worth

**Very high.**

This is required, not optional, if the other milestones succeed.

## 6. Assistant Operator Console

### Goal

Provide one place to operate deployed assistants.

### Why It Matters

Once assistant deployments exist, users and admins need to see:

- what is running
- what failed
- what is waiting
- what channel it is connected to
- what tasks are scheduled
- what approvals are pending

### Deliverables

- assistant deployment list
- status and health
- per-channel state
- pending approvals
- recent actions and failures
- quick jump to related executions and workflows

### Product Position

This should not become a giant support console in the public slice. The public
version should remain useful and understandable. The stronger operational depth
belongs in `prod`.

### Public vs Prod

- public/local:
  - compact operator view
  - assistant status and recent activity
- prod:
  - stronger observability
  - deeper incident tooling
  - support-focused operational surfaces

### Worth

**High.**

This turns the assistant layer into something teams can actually trust.

## Recommended Order

The best order is:

1. **Assistant Deployment Model**
2. **Channel Deployment UX**
3. **Approval, Interruption, And Safety Controls**
4. **Proactive And Scheduled Assistant Behavior**
5. **Multi-Agent Routing And Handoffs**
6. **Assistant Operator Console**

Why this order:

- deployment model is the foundation
- channel UX makes the concept real
- safety must arrive early
- proactive behavior becomes much more valuable after deployment exists
- routing is more powerful once one assistant can already operate well
- operator console becomes much more useful once the other behavior exists

## What To Keep Public vs What To Keep Prod

This roadmap must respect Numel’s local/prod boundary.

### Keep Public

- assistant deployment concept
- reference deployment UX
- channel deployment model
- basic proactive scheduling and event bindings
- visible approval and interruption behavior
- compact operator console

### Keep Stronger In Prod

- deployment hardening and delivery guarantees
- production secrets posture
- deeper runtime reliability behavior
- stronger observability and support tooling
- richer operational auditing
- production incident workflows

That keeps the public repo real and useful while preserving a meaningful
commercial production layer.

## Is It Worth Implementing?

Yes, **selectively**.

This roadmap is worth doing because it strengthens Numel in areas where the
market comparison shows real upside:

- assistant deployment
- proactive assistants
- multi-agent systems
- channel usefulness
- operator trust

It would **not** be worth implementing if it caused Numel to drift into being:

- mainly a chat product
- mainly a channel gateway
- mainly an assistant shell with weak workflow identity

So the answer is:

> It is worth matching OpenClaw where that makes Numel a better assistant
> platform, but not where it would weaken Numel’s identity as a visual AI
> workflow and app platform.

## Success Criteria

This roadmap is succeeding if, after implementation, a user can:

1. build an assistant in a space
2. deploy it to one or more channels
3. connect it to tools and shared knowledge
4. let it run on schedules or events
5. supervise actions with approvals and stop controls
6. understand what it did and why

without needing to think in terms of low-level internal primitives.

## Related Documents

- [competitive-landscape.md](competitive-landscape.md)
- [product-roadmap.md](product-roadmap.md)
- [public-private-boundary.md](public-private-boundary.md)
- [feature-tier-matrix.md](feature-tier-matrix.md)
