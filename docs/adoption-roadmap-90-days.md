# 90-Day Adoption Roadmap

This roadmap is the product-side follow-up to Numel's recent architecture work.

The goal is not to make Numel broader first.
The goal is to make Numel:

- easier to start
- easier to trust
- easier to share

That is the shortest path to a healthy adoption loop.

## Success Goal

At the end of 90 days, a new user should be able to:

1. run Numel locally in minutes
2. choose a strong starter instead of facing a blank workbench
3. reach a useful first run quickly
4. understand what happened during the run
5. fork, reuse, or publish the result

## Phase 1: First-Run Value

Target: days 1-30

Primary outcome:
- a user reaches first value fast through clear starter choices

Main work:
- flagship starter spaces
- onboarding improvements
- stronger empty states
- starter-specific docs and examples

Flagship starter set:
- Support front door
- Repo or file assistant
- Research assistant
- Event-driven ops watcher
- Publishable mini-app starter

Exit criteria:
- the starter surface highlights at least a few high-value use cases
- the workbench no longer feels blank on first run
- docs point users toward starters before deep architecture

## Phase 2: Trust And Iteration

Target: days 31-60

Primary outcome:
- users can understand and improve runs instead of guessing

Main work:
- execution replay
- run comparison and diff
- clearer per-run timeline
- better eval visibility
- better deployment analytics

Exit criteria:
- users can explain what changed between two runs
- users can inspect failures and handoffs more easily
- deployments feel more like operable systems than opaque cards

Progress so far:
- live run timeline added to the workbench Run panel
- latest-run replay added for the current space as a first trust-and-iteration slice
- latest-two-run comparison added to show status, duration, and output-node changes
- eval visibility added for live runs, replayed runs, and latest-two-run comparison
- failure drill-down added for live and replayed runs, with persisted failure metadata where available
- deployment and network analytics added to the operator inspect surfaces, derived from live counters plus recent runtime windows

## Phase 3: Sharing And Reuse

Target: days 61-90

Primary outcome:
- users can turn a good result into a repeatable growth loop

Main work:
- template publishing
- forkable spaces
- version notes and snapshots
- stronger publishable-app polish
- starter metadata and curated gallery improvements

Exit criteria:
- a successful workflow can become a reusable template
- users can fork and adapt an existing workbench cleanly
- the gallery supports reuse instead of only browsing

Progress so far:
- current spaces can now be forked directly from the workbench
- workflows can be saved with explicit snapshot notes
- workflow snapshot history is visible from the workbench
- current workflows can be published into the gallery as reusable templates
- the workbench now groups accessible spaces into **Mine**, **Shared**, and **Public**
- public spaces can be resolved by `namespace + slug`, which lays groundwork for Hugging Face-style repo discovery
- the space panel now exposes repo details and direct public-repo opening by `owner/slug`
- the app surface is now ref-aware, so the current workbench can switch branches or tags and the normal workflow save/load/run/history routes follow that active ref
- the repo details surface now exposes refs plus recent repo commits, moving Numel closer to a real repo-plus-playground model
- the repo details surface now also exposes visible repo assets plus namespace-level public repo browsing
- workflow assets on the active ref can now be opened directly into the current workbench, and the normal workflow save/load/run/history routes now follow that selected asset as well as the selected ref
- the public side now has fuller namespace pages and public repo pages, with inspect/open/fork flows that do not depend on switching the current workbench first
- repo history now supports compare and restore at the repo level: compare refs or commits against the active repo state, and restore the active branch from a selected historical commit with one new repo commit
- reusable template publishing can now target the current canvas, a chosen ref head, or a saved workflow snapshot, with source metadata attached to the published gallery item
- gallery cards published from public repos now surface their source locator and can jump back to the underlying public repo page, making the gallery feel more like a curated layer over public repos
- the Extensions panel now has a unified Registry tab that surfaces shared toolkits and skills together with creator, source, trust, featured, provenance, compatibility, and setup signals, plus search/filter/detail flows that make the registry feel more like a usable ecosystem surface than a static list
- the Public Hub now has creator pages that combine one creator's public repos with their published templates, and gallery cards can jump to either the source repo or the creator page, which makes the creator loop much more explicit
- published templates now carry computed provenance and discovery metadata, so Gallery and creator pages can show version labels, repo-backed/public-source signals, and curated or featured ordering instead of acting like flat template dumps
- the repo details surface now supports inline creation and editing of text assets on the active ref, which is the first practical multi-asset editing step beyond the workflow file itself
- the main Workflow section now exposes a repo-asset browser plus a "save canvas as workflow asset" flow, so multi-workflow repos are practical from the workbench instead of being trapped behind the Repo Details dialog
- assistant deployment proactive tasks can now preserve a real multi-source trigger fan-in through one `event_listener_flow`, including listener modes like `any`, `all`, and `race`, instead of flattening back to only one source during network export, apply, or runtime start
- graph-first operational visibility is now real instead of aspirational: the Run panel can open a runtime workflow graph, Assistant Deployments can open a live network graph, and the admin execution drawer can open an execution graph backed by stored runtime metadata
- workflow file and clipboard import now have a real interop path: native Numel JSON still loads directly, and a pragmatic subset of n8n workflow JSON, including common set, HTTP, branch, switch, merge, simple time-wait, and portable code-node shapes, is converted into runnable Numel graphs with explicit manual-review warnings where the mapping is not exact yet

Next execution order:
1. do the final end-of-roadmap UI validation and polish pass across the now-expanded repo, graph, deployment, registry, and ecosystem surfaces

Note:
- the main UI test pass can be deferred until the end of this roadmap implementation, so intermediate work should optimize for coherent end-state coverage rather than per-slice visual signoff

## Remaining Focus Areas

From the current starting point, the main remaining roadmap items are:

1. final end-of-roadmap UI validation and polish
- do one broader UI pass after the roadmap implementation is functionally in place
- use that pass to tune Public Hub, repo browser, registry, deployment/runtime graph views, and interop edges together

Future ecosystem work after this roadmap:

- broaden interop beyond the current n8n subset into harder code-heavy/loop-heavy shapes and later other external ecosystems

## Parallel Adoption Work

Do this during all three phases:

- one clear landing page or doc entry for each flagship starter
- one short demo or walkthrough for each flagship starter
- tighter product wording around space, workbench, deployment, and handoff
- stronger gallery presentation

## What Not To Prioritize First

- broad connector-count competition
- low-level primitives that do not improve adoption
- broad ad spend before the starter and trust loops are strong
- large ecosystem work before templates and sharing are solid

## Recommended Metrics

Watch these first:

- time to first successful run
- share of new spaces that load a starter
- share of users who reach a second run
- share of users who open Assistant Deployments after starting a support or ops workbench
- share of workflows that get forked, templated, or published

## Current Starting Point

Numel already has strong foundations:

- workflow-backed console and deployment surfaces
- deployment network export and apply
- handoff and proactive runtime
- local-to-prod continuity

So the next 90 days should convert those strengths into clearer user value.
