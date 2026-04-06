# Numel Product Roadmap

This document turns the current product advice into a concrete roadmap.

For the design/product layer that should guide the next implementation slice,
see [ui-exploration-plan.md](/c:/devel/numel-playground/docs/ui-exploration-plan.md)
and [ui-exploration-review.md](/c:/devel/numel-playground/docs/ui-exploration-review.md).

The goal is not to make Numel "bigger". The goal is to make Numel feel more
useful, more focused, and more compelling to real users.

## Product Thesis

Numel should aim to become the best **visual studio for live multimodal
agents**.

That means users should be able to:

- describe what they want
- get a working graph quickly
- inspect what the agent is doing
- iterate visually
- turn the result into a reusable workflow or app

Numel is strongest when it combines:

- graph-based workflow editing
- chat and planner-driven generation
- agents, toolkits, and skills
- browser-native media capture and preview
- self-hosted local-to-prod continuity

## Who Numel Is For

Best-fit users today:

- technical builders who want a visual layer over Python/agent workflows
- self-hosters who want control over local and production deployment
- users building assistants that need tools, memory, browser media, or sharing
- teams that want a space-centric workflow product rather than a code library

Less ideal fits today:

- users who only want enterprise automation connectors
- users who want a pure no-code business workflow tool
- users who only care about image-generation node graphs

## Flagship Promise

The product should feel like this:

> Build assistants that can think, use tools, see and hear the browser, and
> become reusable apps, all from one visual workspace.

If a roadmap item does not strengthen that promise, it is probably not a top
priority.

## Immediate Priorities

These are the highest-leverage changes to make Numel feel stronger quickly.

### 1. First-Run Success In 10 Minutes

Deliver a clearer first session:

- guide the user through admin bootstrap, first space, and first run
- open with a starter experience instead of a blank product
- suggest one-click import of a few flagship workflows

Desired user outcome:

- a new user reaches a successful execution without reading much documentation

### 2. Starter Spaces And High-Value Templates

Ship a small set of strong defaults:

- research assistant
- file/repo assistant
- browser media capture workflow
- prompt-to-workflow assistant
- publishable mini-app starter

Desired user outcome:

- the user immediately sees concrete value, not just features

### 3. Planner As The Front Door

Lean harder into the assistant/planner:

- make "describe what you want" the primary entry path
- improve `/gen` and planner onboarding copy
- help users move from prompt to editable graph to runnable result

Desired user outcome:

- Numel feels faster than hand-building graphs from scratch

### 4. Better Execution Clarity

Improve the run/debug experience:

- clearer per-node outputs and failures
- easier run summary and "what changed" visibility
- stronger empty/error states
- more obvious current space/current workflow context

Desired user outcome:

- users trust the system and can diagnose failures quickly

### 5. Stronger Product Language

Make the UI and docs easier to understand:

- explain spaces as projects/workbenches
- reduce internal jargon where possible
- sharpen the product copy around live multimodal agents

Desired user outcome:

- people understand what Numel is for without needing architecture knowledge

## Near-Term Priorities

These make Numel feel more complete and product-like after the first wave.

### 1. Spaces That Feel Like Real Projects

Make spaces more tangible:

- clearer project metadata and summaries
- richer asset lists within a space
- better current-space switching and context visibility
- stronger execution/artifact history at the space level

### 2. Share, Fork, And Publish Flows

Turn the Git-like model into visible user value:

- easy sharing and visibility controls
- visible history and versions
- forkable spaces and templates
- cleaner publish-to-app workflow

### 3. Multimodal Vertical Workflows

Double down on what is distinctive:

- browser screen/webcam/microphone flows
- preview-driven debugging
- multimodal agent examples
- stronger capture-to-agent and capture-to-app stories

### 4. Extensions That Feel Safe And Useful

Improve the toolkit/skill story:

- clearer extension discovery
- install/use/remove guidance
- trust and provenance messaging
- better examples showing skills + toolkits working together

### 5. Better Admin And Operations Diagnostics

Make the product easier to operate:

- clearer health and readiness visibility
- better execution diagnostics
- better quota/admin feedback
- clearer deploy troubleshooting

## Strategic Priorities

These are the areas that can make Numel commercially stronger over time.

### 1. Collaborative, Versioned Agent Spaces

Turn the space model into a real differentiator:

- history, refs, and forks surfaced in product UX
- clearer visibility and permission controls
- collaboration around spaces instead of ad hoc files

### 2. Strong Production Offering

Keep the public/local product real, and make the commercial value come from:

- hardened production deployment
- identity, quotas, and admin controls
- Docker/runtime isolation
- operational tooling and supportability

### 3. A Real Extension Ecosystem

Grow beyond built-ins:

- curated skills/toolkits
- versioning and compatibility guidance
- installable community packages
- a trustworthy extension workflow

### 4. Replay, Evaluation, And Optimization

Make Numel especially strong for iterative agent work:

- compare runs
- inspect eval scores
- replay and branch from prior results
- optimize workflows with planner support

### 5. From Workflow To User-Facing App

Strengthen the last mile:

- easier publishing
- clearer app templates
- stronger app runtime and lifecycle controls
- better handoff from builder mode to end-user mode

## What Not To Chase

To stay sharp, Numel should avoid trying to win on the wrong axes:

- do not chase maximum connector count like a business automation platform
- do not chase pure library ecosystem breadth
- do not chase creator-media depth in the same way as image-first node tools
- do not center the product message on infrastructure details

## Success Signals

Good signs that the roadmap is working:

- new users reach a first successful run quickly
- more workflows begin from planner or templates rather than a blank canvas
- users understand what spaces are for
- the product's multimodal and agent strengths become easier to explain
- the public repo still feels like a real product, not a teaser
- the private production slice remains valuable because of guarantees, not because basic usefulness is hidden

## Recommended Order

If prioritization is tight, the order should be:

1. first-run onboarding
2. starter templates and starter spaces
3. planner-first experience
4. execution clarity and debugging
5. stronger space/project UX
6. share/fork/publish polish
7. extension ecosystem polish
8. deeper production and collaboration differentiators

## Commercial Interpretation

The strongest open-core/product split remains:

- public repo: fully working local/reference Numel
- private prod slice: hardened deployment and operational guarantees

That keeps adoption high while making the commercial value legible.
