This tutorial shows the current "everything in Numel is workflow-backed" direction in a practical way.

You will not build one big workflow from scratch here.
Instead, you will move between the main runtime surfaces and see how they now round-trip through the workbench.

## What You Will Learn

- how to export the Assistant console into the workbench
- how to apply a console-shaped workflow back into the live Assistant
- how to export the live assistant deployment network into the workbench
- how to apply that network graph back into the runtime
- how proactive tasks and handoff selectors now fit the same workflow-backed model

## Before You Start

You should already have:

- Numel running locally
- at least one user account
- at least one saved space
- basic familiarity with the Assistant and Assistant Deployments panels

If you have not used deployments before, do [tutorial-11-assistant-deployments.md](tutorial-11-assistant-deployments.md) first.

## Part 1: Turn The Assistant Console Into A Workflow

1. Open the Assistant panel.
2. Open the Assistant settings area.
3. Click **Open Assistant In Workbench**.

Numel will materialize the current console shape as a real workflow.

That exported workflow is now the same kind of thing you can inspect, save, and edit on the canvas.

Look for nodes such as:

- `model_config`
- `agent_options_config`
- `agent_config`
- `agent_chat`

If Numel exposes more than one backend in the future, an optional `backend_config` node can also appear in exported agent branches.

If the Assistant is using runtime-bound capabilities like `console_toolkit`, those now remain visible in the graph and are rebound by Numel at runtime instead of being silently omitted.

## Part 2: Apply A Console Workflow Back To The Assistant

1. Change something small in the exported workflow.
   Good examples:
   - assistant name
   - instructions
   - model source or model name
2. Save the space if you want.
3. Go back to the Assistant settings.
4. Click **Apply Workbench To Assistant**.

This applies the console-shaped workflow back to the live Assistant configuration.

So the direction now works both ways:

- console -> workbench
- workbench -> console

## Part 3: Open The Live Deployment Network In The Workbench

1. Open **Assistant Deployments**.
2. Click **Open Live Network In Workbench**.

Numel will export the live operational network into a workbench workflow.

This is different from a normal logic workflow.
It is an **operations graph** that represents things like:

- deployments
- bound channels
- routing rules
- proactive tasks
- approvals

That is why this graph matters: it lets you inspect live runtime structure using the same visual language as the rest of Numel.

## Part 4: Inspect What A Proactive Task Looks Like In The Graph

If one of your deployments has proactive tasks, inspect the graph around that deployment.

You should now see that a proactive task is represented through real source nodes and an event listener, not just hidden timer metadata.

Typical shapes include:

- `timer_source_flow`
- `webhook_source_flow`
- `channel_receive_flow`
- `fswatch_source_flow`
- `browser_source_flow`
- then one `event_listener_flow` that can fan in one or more of those sources with modes like `any`, `all`, or `race`
- then the proactive runtime node

This is important because proactive behavior is now part of the same graph vocabulary as the rest of the system.

## Part 5: Inspect Handoff Selection

Open one of the deployment runtime nodes in that network graph.

Look at the handoff selector fields.

You can now choose:

- `keyword`
- `hybrid`
- `workflow`

Recommended default:

- `hybrid`

Why:

- it keeps simple deterministic routing when the keywords are obvious
- but it also falls back to the workflow-backed selector when the user’s wording is more semantic than literal

This means the handoff decision itself is no longer limited to exact keyword matching.

## Part 6: Apply The Edited Network Back Into Runtime

1. Make a small safe change in the network workflow.
   Good examples:
   - change a deployment description
   - adjust a selector mode
   - update a linked workflow name
2. Return to **Assistant Deployments**.
3. Click **Apply Workbench To Network**.

This applies the edited network graph back into the live runtime.

That round-trip now covers:

- deployments
- channel bindings
- routing rules
- proactive tasks
- editable channel settings

It also prunes missing owned runtime objects when you apply the graph authoritatively.

## What Is Still Not Meant To Be A Graph

Some things are still runtime control-plane logic on purpose.

Examples:

- browser-tab debounce timing for planner reactions
- temporary planner pause windows after manual runs
- channel transport internals such as Telegram polling

Those are still important, but they are not the same thing as the computational or operational logic that belongs in a workflow.

So the practical rule is:

- if it is meaningful AI or system behavior, push it toward the graph
- if it is temporary UI/session/transport plumbing, keep it in the runtime unless a graph representation becomes clearly better

## What You Built

At the end of this tutorial, you have seen that Numel now has workflow-backed bridges for:

- the Assistant console
- planner turns
- proactive execution
- deployment handoff selection
- the live assistant deployment network

That is the current shape of the product direction:

- one shared workflow language
- multiple runtime surfaces built around it

## Where To Go Next

- [workflow-backed-surfaces.md](workflow-backed-surfaces.md)
- [assistant-deployments.md](assistant-deployments.md)
- [assistant-network-architecture.md](assistant-network-architecture.md)
- [tutorial-13-event-driven-proactive-deployments.md](tutorial-13-event-driven-proactive-deployments.md)
