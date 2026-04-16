Numel is moving toward a simple architectural promise:

**major runtime surfaces should be representable as workflows, not only as hidden special-case code paths.**

This document explains what that means today, what is already workflow-backed, and what still remains runtime control-plane logic on purpose.

## The Goal

Different parts of Numel used to feel like separate worlds:

- the workbench canvas
- the assistant console
- assistant deployments
- proactive jobs
- the live deployment network

The current direction is to make those surfaces converge on one shared graph language.

That does not mean every tiny behavior becomes a visible node immediately.
It means the meaningful computational and operational parts should have a workflow representation.

## What Is Already Workflow-Backed

### 1. The Workbench

This is the obvious one:

- spaces hold workflows
- the canvas edits them
- executions run them

This remains the core design surface.

### 2. The Assistant Console

The console is no longer only a separate runtime shell.

It now supports:

- **Open Assistant In Workbench**
  Export the current console configuration as a real workflow.
- **Apply Workbench To Assistant**
  Apply a console-shaped workflow back into the live Assistant settings.

So the console now has a real workflow bridge in both directions.

### 3. Planner Turns

The planner still has runtime session control such as:

- browser-tab ownership
- debounce timing
- pause/suppress windows

But the actual planner reasoning turn is now workflow-backed.

That means:

- planner user turns run through a transient workflow-backed execution path
- planner autonomous event turns also run through a transient workflow-backed execution path

So the meaningful AI computation is workflow-backed even if the tab/session orchestration is still runtime control-plane logic.

### 4. Assistant Deployments

A deployment is still a runtime product object, but it is no longer trapped there.

The deployment model can now be represented through the assistant-network workflow export/import path, including:

- deployment identity
- channels
- routing
- proactive tasks
- approvals
- linked workbench context

### 5. Proactive Tasks

Proactive tasks are no longer just timer metadata hanging off a deployment.

Their graph representation now uses real source nodes plus `event_listener_flow`, for example:

- `timer_source_flow`
- `webhook_source_flow`
- `channel_receive_flow`
- `fswatch_source_flow`
- `browser_source_flow`
- then `event_listener_flow`
- then the proactive runtime node

That is important because it keeps proactive behavior inside the same workflow vocabulary as the rest of Numel.

### 6. Handoff Selection

Conversation-level handoff is now a real deployment capability, and the selector can be:

- `keyword`
- `hybrid`
- `workflow`

The default is now `hybrid`:

- try deterministic keywords first
- fall back to a workflow-backed semantic selector if keywords do not decide

So even routing decisions are no longer limited to literal keyword matching.

### 7. The Assistant Deployment Network

The live deployment network can now be:

- exported into the workbench
- edited there
- applied back into the runtime

That round-trip currently covers:

- deployments
- channel bindings
- routing rules
- proactive tasks
- pending approvals
- editable channel settings

This is the strongest current example of Numel’s “everything is workflow-backed” direction.

## What Still Stays Runtime Control-Plane Logic

Some behavior is intentionally not forced into the graph.

Examples:

- browser-tab debounce timing for the planner
- temporary pause/suppression windows after a manual run or planner apply
- channel transport internals such as a Telegram poller or webhook adapter lifecycle
- ephemeral UI state

These are still real parts of the product, but they are closer to:

- session coordination
- transport management
- operator safety rails

than to meaningful business or agent logic.

So the practical rule is:

- put **computational and operational behavior** in workflows
- keep **ephemeral transport/UI/session mechanics** in the runtime unless a graph representation becomes clearly better

## A Simple Mental Model

Use this distinction:

- **Logic workflow**
  The graph that defines what the system does.
- **Operations workflow**
  The graph that defines how live assistants, channels, routing, approvals, and proactive behavior are wired together.

Numel is moving toward supporting both clearly.

## Practical User Value

This direction matters because it gives users:

- one shared mental model instead of many separate product islands
- better inspectability
- easier round-trip editing
- more reusable patterns between console, deployments, and workflows
- less hidden behavior

It also makes it easier to explain Numel:

- build in the workbench
- run in deployments or apps
- inspect the live network as a workflow when needed

## Good Things To Try

If you want to feel this model directly, try these in order:

1. Open the Assistant console and use **Open Assistant In Workbench**.
2. Edit the resulting workflow, then use **Apply Workbench To Assistant** to apply it back to the Assistant.
3. Open **Assistant Deployments** and use **Open Live Network In Workbench**.
4. Edit the operational graph and use **Apply Workbench To Network** there too.
5. Create a proactive task with a non-timer trigger and inspect how it appears in the network workflow.
6. Switch a deployment handoff selector between `keyword`, `hybrid`, and `workflow`.

## Related Docs

- [assistant-deployments.md](assistant-deployments.md)
- [assistant-network-architecture.md](assistant-network-architecture.md)
- [tutorial-11-assistant-deployments.md](tutorial-11-assistant-deployments.md)
- [tutorial-12-workflow-backed-runtime.md](tutorial-12-workflow-backed-runtime.md)
