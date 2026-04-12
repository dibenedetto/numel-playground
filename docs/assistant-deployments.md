Assistant Deployments turn Numel from “a workflow editor with channels” into “a deployable assistant platform.”

## What An Assistant Deployment Is

An assistant deployment is a persistent product object that binds:

- one named assistant identity
- one or more channels
- a model override
- selected toolkits and skills
- optional routing rules to specialist deployments
- optional proactive jobs
- safety rules for outgoing proactive messages and tool execution
- an optional linked workbench (space + workflow)

That means the same deployment can keep showing up in real channels with stable behavior, while still pointing back to the Numel workbench where its logic and supporting assets live.

## Why It Matters

This closes a gap between building an assistant and operating one:

- workflows and spaces remain the design surface
- channels become the runtime surface
- deployments become the durable operator surface

Instead of wiring channels ad hoc, you can now create named assistants such as:

- `Support Front Door`
- `Billing Specialist`
- `Operations Pulse`

Each one can have its own model, tools, skills, safety posture, and routing behavior.

## Current Capabilities

### Channel Binding

Deployments can bind one or more channels and start/stop them from the deployment panel.

### Linked Workbench

Each deployment can point to a space and workflow. This gives operators a concrete place to jump back to when they need to inspect or change the assistant’s workbench context.

### Multi-Agent Routing

A front-door deployment can route matching requests to specialist deployments through keyword-based routing rules.

### Proactive Jobs

Deployments can run recurring tasks on a timer and optionally deliver the resulting message to a channel recipient.

### Approval Flows

There are now two approval surfaces:

- **Proactive delivery approval**
  Pause before sending a proactive message.
- **Tool execution approval**
  Pause before the assistant executes a tool call, then resume or reject from the operator panel.

The tool execution path uses the active backend’s native paused-run mechanism and is surfaced through Numel’s deployment abstraction.

### Operator View

The Assistant Deployments panel now acts as a lightweight operator console:

- filters by status and attention
- summary chips for running and pending approvals
- recent activity and recent failures
- pending approval cards
- linked workbench navigation
- manual proactive-task execution
- runtime refresh

## Recommended Product Model

The cleanest setup is usually:

1. Create a workbench in a space.
2. Link a deployment to that workbench.
3. Bind the deployment to a real channel.
4. Add routing or proactive jobs if needed.
5. Enable approval modes where the assistant needs supervision.

This keeps the design surface and runtime surface separate but connected.

## Approval Philosophy

Approval modes are deliberately explicit:

- use `auto` when the deployment should behave independently
- use `approval` when an operator should stay in the loop

Right now, tool approval is deployment-wide: if enabled, tool calls from that deployment pause for operator approval before execution.

## Good Starter Patterns

### Front Door + Specialist

- `Support Front Door` bound to a customer-facing channel
- `Billing Specialist` as a routed specialist
- front door uses routing rules for keywords like `invoice`, `refund`, `billing`

### Proactive Ops Assistant

- deployment bound to an ops channel
- one or more proactive jobs
- proactive delivery approval enabled
- optional tool execution approval enabled for higher-risk tooling

## Related Assets

- Gallery:
  - `Assistant Deployments: Support Workbench`
  - `Assistant Deployments: Ops Workbench`
- Tutorial:
  - [tutorial-11-assistant-deployments.md](tutorial-11-assistant-deployments.md)
- Example deployment configs:
  - [assistant-deployment-front-door.json](../examples/assistant-deployment-front-door.json)
  - [assistant-deployment-ops-proactive.json](../examples/assistant-deployment-ops-proactive.json)
