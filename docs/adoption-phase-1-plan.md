# Phase 1 Implementation Plan

Phase 1 is about first-run value.

The shortest practical objective is:

> a new user should see a few strong starter choices, load one quickly, and understand why it matters.

## Phase 1 Deliverables

### 1. Flagship Starter Surface

Turn the starter panel and starter modal into a stronger product entry point.

Initial starter set for this phase:
- Quick start
- Research starter
- Webcam starter
- Support assistant workbench
- Ops assistant workbench
- Ask the assistant

Why:
- this gives Numel obvious first use cases instead of generic examples only
- support and ops directly showcase deployments, handoff, and proactive work

### 2. Starter-Specific Messaging

Make starter copy explain what each starter is for in plain product terms.

Examples:
- support starter -> linked workbench for a channel-facing support assistant
- ops starter -> linked workbench for a proactive operational assistant

### 3. Better First-Run Guidance

Improve empty-state and onboarding guidance so a user sees:
- create a space
- choose a starter
- run it
- optionally open Assistant Deployments later

### 4. Starter Docs

Add roadmap docs and keep product docs aligned with the flagship starter strategy.

## Phase 1 Progress

Completed in this phase so far:

- support and ops workbenches exposed as first-class starter actions
- starter modal and inline starter panel improved
- post-starter follow-through guidance added
- per-user `Show on login` preference added for the starter modal
- repo and file assistant starter added
- publishable mini-app starter added
- starter walkthrough doc added

Still remaining in Phase 1:

- tighter starter messaging and polish pass after end-to-end testing
- any final empty-state and first-run tuning we discover during real UX testing

## Current Slice To Build First

The first concrete implementation slice is:

- expose the existing support and ops workbench gallery items as first-class starter actions
- wire them into both:
  - the inline starter panel
  - the first-run starter modal

This is intentionally small and high-signal.

It turns already-existing gallery value into visible onboarding value.

## Acceptance Criteria For This Slice

- support and ops appear as starter actions in the workbench
- support and ops appear in the starter modal
- both actions load the correct gallery workflow
- the starter system still works for hello, research, webcam, assistant, and gallery
- starter copy clearly signals what the support and ops starters are for

## Next Slice After This One

After support and ops starters are visible, the next likely Phase 1 slice should be:

- add a repo or file-assistant starter
or
- add a publishable mini-app starter

The choice should depend on which one feels more complete and demo-worthy in the current repo.

Current status:

- both of those next-slice candidates are now implemented
- the next best Phase 1 follow-up is end-to-end starter testing and polish
