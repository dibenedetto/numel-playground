Assistant Deployments now have enough operator surface area that it helps to treat them like a small control plane, not just a config form.

This guide is about operating them day to day.

## What The Panel Is For

The Assistant Deployments panel is where you:

- start and stop deployments
- inspect runtime state
- review recent activity and failures
- approve or reject paused tool calls and proactive deliveries
- run proactive tasks manually
- open the linked workbench
- inspect the full live network as one system
- inspect the live deployment network as a graph when you want the topology, not only the textual status view

The important shift is:

- the **workbench** is where you design and improve the intelligence
- the **deployment panel** is where you operate the live assistant

## The Two Status Signals

Every deployment shows two related but different status signals.

### Lifecycle

- `active`
- `inactive`

This answers:

- is this deployment enabled as a live assistant at all?

### Runtime State

- `running`
- `stopped`
- `error`
- `partial`
- `starting`
- `stopping`

This answers:

- what is the current runtime condition of this deployment and its live behavior?

So a deployment can be:

- `active` but not healthy
- `inactive` and therefore not expected to handle traffic

## What “Needs Attention” Means

The panel now flags deployments when at least one of these is true:

- runtime is in `error`
- runtime is in `partial`
- pending approvals exist
- recent failures exist

The card now shows short reason chips such as:

- `runtime error`
- `2 pending approvals`
- `1 recent failure`

That is meant to reduce guessing. You should not have to open a deployment just to learn why it is flagged.

## Inspecting One Deployment

Use `Inspect` on a deployment card when you want the full operator view for that one assistant.

The inspect dialog groups the live traces into:

- `Runtime Snapshot`
- `Deployment Shape`
- `Recent Messages`
- `Recent Activity`
- `Endpoint Calls`
- `Handoffs`
- `Proactive Runs`
- `Approvals`
- `Failures`

This is the fastest way to answer questions like:

- what happened most recently?
- did it hand off to a specialist?
- did a tool call pause for approval?
- did a proactive task fail?
- which endpoint did it consult?

### Copy Snapshot

The deployment inspector also has `Copy Snapshot`.

That copies a clean text summary of:

- identity and linkage
- channels
- runtime counters
- attention reasons
- failures
- endpoint calls
- handoffs
- proactive runs
- recent activity

This is useful for:

- incident notes
- issues
- operator handoff
- pasting into the assistant or another tool for analysis

## Inspecting The Whole Network

Use `Inspect Network` from the panel toolbar when you want the live system view across all deployments.

It shows:

- `Network Snapshot`
- `Busiest Deployments`
- `Needs Attention`
- `Pending Approvals`
- `Recent Failures`
- `Recent Network Activity`

This is the right place to start when the question is:

- what is happening in the network right now?

rather than:

- what is happening in one deployment?

### Drill-Down

Rows in the network inspector now include `Inspect` buttons.

That means the operator loop is:

1. open the network inspector
2. find the noisy or urgent deployment
3. jump straight into that deployment’s detailed inspector

### Copy Snapshot

The network inspector also has `Copy Snapshot`.

That gives you a compact network summary with:

- deployment totals
- active/running counts
- attention counts
- pending approvals
- the current attention set
- busiest deployments

This is useful for shift handoff and incident updates.

## First-Run Operator Path

If you are starting from scratch, the clean sequence is:

1. create a channel
2. add a deployment
3. bind it to the channel
4. save it inactive
5. start it
6. send a real message through the channel
7. inspect activity, approvals, and failures if something feels off

The panel now has:

- a richer empty state
- direct actions for `+ Add Deployment`
- direct action for `Open Channels`
- a built-in `Status Guide`

So the first-run path should be easier to follow without leaving the panel.

## What To Do In Common Situations

### A deployment is active but not answering

Check:

- runtime state
- bound channels
- recent failures
- recent activity

Then use `Refresh State` if the panel feels stale.

### A conversation seems to have gone to the wrong specialist

Check:

- `Handoffs`
- `Recent Messages`
- handoff selector mode
- routing rules and selector guidance

Remember:

- routing chooses a likely target
- handoff transfers conversation ownership

### A deployment looks “stuck”

Check:

- pending approvals
- recent tool approvals
- proactive approvals

Many “stuck” cases are actually:

- the assistant is waiting for approval

not:

- the runtime is frozen

### The network feels noisy

Open `Inspect Network` first, then look at:

- `Needs Attention`
- `Recent Failures`
- `Recent Network Activity`

That is usually faster than opening cards one by one.

## Relationship To The Workbench

When you need to change the live assistant’s design rather than just operate it:

- use `Open Workbench`
- or `Open Live Network In Workbench`
- or `Apply Workbench To Network`

The control loop becomes:

- inspect in the operator surface
- jump to the workbench if a design/runtime change is needed
- apply the updated network back into runtime

## Best Mental Model

- deployment card = quick health and action surface
- deployment inspector = one-assistant operator console
- network inspector = whole-system operator console
- workbench = design and change surface

## Related Reading

- [assistant-deployments.md](assistant-deployments.md)
- [tutorial-11-assistant-deployments.md](tutorial-11-assistant-deployments.md)
- [workflow-backed-surfaces.md](workflow-backed-surfaces.md)
- [assistant-network-architecture.md](assistant-network-architecture.md)
