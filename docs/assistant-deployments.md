Assistant Deployments add a durable operating layer to Numel's AI workflow and workbench platform.

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

This closes a gap between building an AI workflow and operating it as a real service:

- workflows and spaces remain the design surface
- channels become the runtime surface
- deployments become the durable operator surface

Instead of wiring channels ad hoc, you can now create named assistants such as:

- `Support Front Door`
- `Billing Specialist`
- `Operations Pulse`

Each one can have its own model, tools, skills, safety posture, and routing behavior.

## Why This Helps Different Kinds Of Users

Assistant deployments are not only for highly technical builders.

- **Technical users** get a cleaner operating model for routing, proactive jobs, approvals, and linked workbenches.
- **Product and operations users** get a named AI service they can run, supervise, and improve without needing to rewire the whole workflow graph every time.
- **Less technical users** can start from an existing workbench, bind it to a channel, and operate it from one panel instead of learning the internal graph structure first.

So the feature should not be read as:

- "Numel is mainly a visual assistant tool"

It should be read as:

- "Numel is an AI workflow/workbench platform, and assistant deployments are one way to put that work into real operation"

## User Memory vs Assistant Deployments

These two ideas are related, but they solve different problems.

- **User memory** answers:
  what does this assistant remember about a person?
- **Assistant deployment** answers:
  what named AI service is this, where does it run, and how is it operated?

So:

- memory gives an assistant **personal continuity**
- deployment gives an assistant **runtime identity and operator control**

### Practical Comparison

| Case | User Memory Only | Assistant Deployment Only | Both Together |
|---|---|---|---|
| Personal helper in the web console | Remembers your preferences, habits, and previous chats | Gives the AI helper a fixed identity, but may be more than you need for a private helper | A named personal assistant that remembers you across sessions |
| Customer support assistant | Can remember returning customers | Can be `Support Front Door`, bound to channels, linked to a workbench, supervised by operators | A real support assistant that also remembers each customer |
| Same user talking to multiple services | The user can be remembered, but the services may still feel generic | `Support`, `Billing`, and `Ops` can exist as distinct runtime identities | Different specialist assistants that each keep useful user continuity |
| Specialist routing | Memory helps with context, but not with service organization | A front door can route to `Billing Specialist` or another specialist | Routed specialists that also retain per-user continuity |
| Proactive summaries and alerts | Memory does not define schedules or delivery behavior | A deployment can own recurring jobs, delivery channels, recipients, and approval rules | A scheduled assistant that also remembers operator or user context |
| Risky tool usage | Memory may remember preferences, but it does not supervise runtime actions | A deployment can require approval before tool execution | A supervised assistant that still adapts to user history |
| Shared knowledge use | Remembers what one user asked before | Carries shared channels, shared workbench context, knowledge, tools, and skills | Shared assistant role plus personalized interaction history |

### Short Version

- **Memory only**: a remembering assistant
- **Deployment only**: an operable AI service
- **Both together**: an operable AI service that also remembers people

## Current Capabilities

### Channel Binding

Deployments can bind one or more channels.

Important nuance:

- deployments decide whether they are active
- channels decide whether their transport is running

So the deployment panel no longer owns channel start/stop directly. A deployment uses its bound channels, but channel lifecycle is a separate concern.

### Linked Workbench

Each deployment can point to a space and workflow. This gives operators a concrete place to jump back to when they need to inspect or change the deployment's workbench context.

Useful distinction:

- a **space** is the container for the work
- a **workflow** is the graph inside that space
- the **workbench** is the full Numel working surface around that space and workflow

So when a deployment says it is linked to a workbench, it really means:

- "this deployment points back to this space and this workflow, and operators can jump there to work on it"

### Routing And Handoff

A front-door deployment can send conversations to specialist deployments.

There are two related ideas here:

- **routing** chooses the likely target
- **handoff** transfers conversation ownership to that target

This matters because Numel now supports sticky conversation ownership. After a handoff, later messages in the same conversation keep going to the specialist until another handoff happens.

Deployments can now choose different selector policies for deciding that handoff:

- `keyword`
  Use deterministic keyword rules only.
- `hybrid`
  Try keyword rules first, then use a workflow-backed semantic selector if keywords do not decide the route.
- `workflow`
  Use the workflow-backed selector directly.

`hybrid` is now the default because it gives a good balance between predictability and flexibility.

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

For non-technical teams, this separation is useful because it means someone else can prepare the workbench, while the day-to-day user mainly interacts with:

- the named deployment
- its channels
- its approvals
- and its operator view

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
- Architecture:
  - [assistant-network-architecture.md](assistant-network-architecture.md)
  - [workflow-backed-surfaces.md](workflow-backed-surfaces.md)
- Tutorial:
  - [tutorial-11-assistant-deployments.md](tutorial-11-assistant-deployments.md)
  - [tutorial-12-workflow-backed-runtime.md](tutorial-12-workflow-backed-runtime.md)
- Example deployment configs:
  - [assistant-deployment-front-door.json](../examples/assistant-deployment-front-door.json)
  - [assistant-deployment-ops-proactive.json](../examples/assistant-deployment-ops-proactive.json)
