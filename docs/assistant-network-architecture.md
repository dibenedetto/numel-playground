Assistant Deployments are already one runtime layer of Numel. The next architectural step is to treat the whole set of active deployments as a **network of operable agents**.

This document explains:

- why that makes sense
- how remote agent protocols such as A2A fit
- why plain toolkits are not enough as the main abstraction
- how the deployment network can eventually become representable as a Numel workflow

## The Core Idea

There are really two different graphs in play:

1. **Workbench workflow**
   The graph inside a space, where you build logic with nodes.
2. **Deployment network**
   The runtime graph of named assistants, channels, routing rules, proactive jobs, approvals, and inter-agent calls.

These are related, but not identical.

A workbench workflow answers:

- how does this logic work?

A deployment network answers:

- which assistants are live?
- which channels reach them?
- how do they hand off work?
- which assistants can consult which others?
- where do approvals and proactive jobs sit?

So yes: it makes sense for the deployment network to become representable as a Numel workflow later, as long as we keep the distinction clear between:

- **logic graph**
- **operations graph**

## Why Toolkits Alone Are Not Enough

The runtime implementation of agent-to-agent communication will almost certainly use callable tools underneath.

But toolkits alone are too low-level to be the main product concept.

If inter-agent collaboration is modeled only as arbitrary tools, Numel loses:

- clear semantics
  Is this a consultation, a delegation, a handoff, or a notification?
- visibility
  Operators should be able to see which assistant asked which other assistant for help.
- policy
  Some assistants should be allowed to consult others but not hand off conversations or invoke sensitive specialists.
- portability
  Numel should not force all agent collaboration to look like one backend’s tool model.
- graphability
  It becomes harder to represent the network cleanly as a future workflow.

So the right shape is:

- **product abstraction first**
- **tool/toolkit implementation second**

## Proposed Numel Abstraction: Agent Endpoints

The clean shared abstraction is an **Agent Endpoint**.

An endpoint is any callable assistant target that a deployment or workflow can talk to.

### Endpoint Kinds

Numel should support at least these kinds:

- `deployment`
  Another Numel assistant deployment.
- `workflow_agent`
  A workflow-backed agent surface that is not itself a deployment.
- `a2a_remote`
  A remote agent exposed through the Agent2Agent protocol.
- `custom_remote`
  Reserved for future protocols or custom integrations.

### Endpoint Properties

An Agent Endpoint should carry metadata such as:

- `id`
- `name`
- `kind`
- `description`
- `owner`
- `capabilities`
- `auth requirements`
- `input modes`
- `output modes`
- `policy tags`
- `availability status`

For remote endpoints, this metadata may be discovered dynamically.
For local endpoints, Numel can derive it directly from deployment or workflow config.

## Interaction Modes

Numel should model assistant-to-assistant interactions explicitly.

The core modes should be:

- `consult`
  Ask another agent for advice or analysis, then continue locally.
- `delegate`
  Ask another agent to perform a subtask and return a result.
- `handoff`
  Transfer the user-facing conversation or active responsibility.
- `notify`
  Send information without expecting a full decision result.

These modes matter because they have different operator meaning:

- a consultation is not a handoff
- a delegated subtask is not a routed user conversation
- a notification may not require the same approvals or tracing

## Why A2A Is Useful

The Agent2Agent protocol is useful for **remote and cross-platform agent communication**.

It is a good fit because it already models things Numel needs for external agents:

- capability discovery via an Agent Card
- stateful tasks
- asynchronous work
- streaming
- multimodal parts and artifacts
- auth-aware remote collaboration

A2A should not replace local deployment routing.

Instead, it should be one transport behind the Agent Endpoint abstraction:

- local deployment endpoint -> direct Numel runtime call
- remote A2A endpoint -> A2A client call

That keeps Numel’s public model stable while allowing interoperability underneath.

## Relationship Between A2A And MCP

A2A and MCP should be treated as complementary:

- **MCP**: tools, APIs, resources
- **A2A**: peer agents

That maps well onto Numel:

- toolkits and MCP-style integrations remain the way agents reach tools and resources
- A2A becomes one way agents reach other agents

## Suggested Product Surfaces

The recommended sequence is:

### 1. First-Class Endpoint Model

Add a backend-neutral shared model such as:

- `AgentEndpointConfig`

This should live at the Numel abstraction layer, not inside a backend implementation.

Current status:

- Numel now has a visible shared-schema node named `AgentEndpointConfig`
- local/runtime code can now normalize and resolve it for `deployment` and `a2a_remote` endpoint kinds
- workflows can wire it directly into `agent_endpoint_flow`
- its purpose is to keep the public abstraction stable while already being usable in the graph today

### 2. Endpoint Toolkit

Add a dedicated toolkit, for example:

- `agent_endpoint_toolkit`

Example methods:

- `consult_endpoint(endpoint_id, prompt, ...)`
- `delegate_to_endpoint(endpoint_id, task, ...)`
- `handoff_to_endpoint(endpoint_id, reason, ...)`
- `notify_endpoint(endpoint_id, message, ...)`
- `list_available_endpoints(...)`
- `describe_endpoint(endpoint_id)`

Current status:

- Numel now has an `agent_endpoint_toolkit`
- deployment agents can use it to consult, delegate to, or notify local deployment endpoints
- the same toolkit can also describe and call remote `a2a_remote` endpoints through A2A HTTP+JSON discovery and direct message calls
- endpoint calls from a deployment now appear in deployment activity as operator-visible events

This gives current agents a usable bridge without waiting for new workflow nodes.

### 3. Endpoint Nodes

Expose the same concept visually through workflow nodes.

Current status:

- Numel now has a general `agent_endpoint_flow`
- it uses one explicit `mode` field instead of proliferating specialized node types
- today the supported modes are `consult`, `delegate`, and `notify`
- `handoff` is intentionally left out for now because it has deeper channel/session semantics than a simple endpoint call

This is the point where the deployment network starts to become naturally representable as a workflow without over-specializing the node catalog.

### 5. Workflow-Backed Operations Graph

The deployment network should not stay only as an internal runtime structure.

Current status:

- the live assistant deployment network can now be exported into the workbench as an operational workflow
- that exported graph includes deployments, bound channels, routing rules, proactive tasks, and pending approvals
- the same operational graph can now be applied back into the runtime to upsert deployments, bindings, routes, proactive tasks, and editable channel settings
- channel credentials are intentionally preserved in backend storage rather than round-tripped through the workflow graph
- existing deployments or channels that are not represented in the current graph are preserved for now instead of being deleted implicitly

This gives Numel a real read/write bridge between the live deployment network and the workflow surface, which is an important step toward “everything in Numel is workflow-backed.”

### 5. Operator Tracing

Every endpoint interaction should be visible as a first-class event:

- source deployment
- target endpoint
- interaction mode
- timestamp
- outcome
- approval status
- summary/result

Without this, inter-agent networking becomes hard to supervise.

## How This Fits The Current Deployment Model

Current assistant deployments already provide:

- channel binding
- routing rules for inbound user messages
- proactive tasks
- tool approvals
- linked workbench context

What they do not yet provide elegantly is:

- lateral collaboration with non-routed agents
- structured consultation with remote agents
- protocol-neutral peer-agent addressing

Agent Endpoints are the missing middle layer.

## How The Whole Deployment Network Can Become A Workflow

The final goal of representing the deployment network as a Numel workflow makes sense if we model the network as an **operational workflow**.

One possible future representation:

- `channel_source_flow`
  Inbound transport nodes.
- `deployment_agent_flow`
  A runtime deployment node.
- `route_flow`
  Deterministic routing decision.
- `agent_endpoint_flow`
  Ask another endpoint for help, delegate a subtask, or send a notification through one shared primitive.
- `approval_flow`
  Pause for operator approval.
- `timer_source_flow`
  Trigger proactive runs.
- `send_message_flow`
  Deliver outward to a channel.

In that model:

- channels become ingress and egress nodes
- deployments become runtime service nodes
- specialists become internal branches or endpoint calls
- remote A2A agents become external service nodes
- approvals become explicit control points

This would make the deployment network inspectable, editable, and simulatable using the same core visual language as the rest of Numel.

## Important Design Rule

Do not collapse the two graphs too early.

The right relationship is:

- the **workbench workflow** defines logic and assets
- the **deployment network workflow** defines runtime collaboration and operations

One deployment may point back to one workbench, but the deployment network can still be its own graph.

That separation keeps the model understandable.

## North Star: Workflow-Backed Runtime Surfaces

The longer-term direction is broader than assistant networking.

Numel should move toward a model where its major runtime surfaces are all representable as workflows:

- the assistant console
- assistant deployments
- the deployment network
- channels and channel-facing ingress/egress
- proactive jobs and approvals

That does not mean every current runtime surface should be naively flattened into one giant graph immediately.
It means the product should converge toward a shared workflow language underneath its different operational faces.

So the current assistant console should eventually stop feeling like a separate special runtime and start feeling like:

- a user-facing workflow surface
- backed by the same underlying graph vocabulary as deployments and deployment networks

This is one reason the general `agent_endpoint_flow` matters: it is not just a deployment feature. It is a reusable workflow primitive that can participate in that broader convergence.

Current status:

- the assistant console can now materialize its current configuration as a real workflow and load it into the workbench
- the same bridge now also works in reverse: a console-shaped workflow in the workbench can be applied back to the live Assistant
- this is still a bridge, not full convergence
- but it gives Numel a concrete workflow-backed starting point for the console instead of treating it as a permanently separate runtime

## Recommended Implementation Order

1. Add `AgentEndpointConfig` as a Numel abstraction.
2. Implement `deployment` endpoints first.
3. Add an `agent_endpoint_toolkit`.
4. Add `a2a_remote` endpoints as the first external protocol-backed kind.
5. Add operator tracing for endpoint interactions.
6. Add a general `agent_endpoint_flow`.
7. Only then consider a full deployment-network workflow editor.

Current status:

- steps 1 through 6 now exist in a first usable form
- the missing higher-order pieces are richer policy controls, a more explicit handoff model, and better workflow/gallery surfaces for assistant-network design

There is already a simple built-in gallery starter you can inspect:

- `Assistant Network: Consult Specialist`

## Bottom Line

Yes, the final goal makes sense.

The clean path is:

- keep routing for simple channel ingress
- add a first-class Agent Endpoint abstraction for general inter-agent collaboration
- use A2A for remote/interoperable endpoints
- implement the runtime through tools/toolkits
- eventually expose the operational assistant network itself as a Numel workflow

That gives Numel a coherent way to move from:

- assistant deployments as isolated runtime objects

to:

- assistant deployments as a visible, operable, and eventually graphable agent network
