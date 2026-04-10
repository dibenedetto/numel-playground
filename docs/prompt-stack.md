# Prompt Stack

This document maps the prompt layers used by Numel's agents and explains the intended order.

## Design Rule

The model should see prompt layers in this order:

1. Capability contract
2. Behavioral contract
3. Current workspace state
4. Current user or planner request

In practice, that means:

- the workflow-generation contract and node catalog come before planner instructions
- backend-native skills and toolkits are attached by the active backend instead of being manually pasted into prompts
- the final user request comes last, after the model already knows what role it is playing and what it is allowed to build

## Console Assistant Stack

Normal console turns use this stack:

1. Base assistant instructions from [console_agent.json](/c:/devel/numel-playground/app/console_agent.json)
2. Current space state from [console.py](/c:/devel/numel-playground/app/console.py)
3. The current user message

Purpose of each layer:

- Base assistant instructions: define who Numel Assistant is and how it should generally behave
- Current space state: ground the assistant in the actual workflow, nodes, and recent execution status
- User message: the immediate task

Runtime note:

- Active skills and toolkits are attached natively through the active backend, not by manual prompt injection.

## `/gen` Stack

`/gen` is not a skill. It is a turn-specific workflow-generation contract.

Current order:

1. Base assistant instructions
2. Active skill packs
3. `[Workflow Generation Contract]`
4. `[Generation Request]`

The contract text itself comes from [api.py](/c:/devel/numel-playground/app/api.py) via `/generation-prompt`, and it includes:

- the workflow generator role
- the JSON response contract
- the runtime/slot model
- the tools catalog
- the node catalog

Purpose:

- Base instructions tell the model it is still Numel Assistant
- The workflow-generation contract overrides the turn and says: for this turn, act as a workflow compiler and return JSON only

## Planner Stack

Planner turns use the richest stack. The intended order is:

1. Base assistant instructions
2. Planner mode directive
3. `[Workflow Generation Contract]`
4. `[Planner Instructions]`
5. Current space state
6. Planner event or planner user message

Why this order:

- The workflow-generation contract defines the hard build constraints first
- Planner instructions then explain how to behave autonomously using those constraints
- The current space state arrives after those contracts so the planner can reason about the actual workflow/run context

Files involved:

- planner mode directive: [prompt_stack.py](/c:/devel/numel-playground/app/prompt_stack.py)
- planner instructions: [planner_instructions.txt](/c:/devel/numel-playground/app/planner_instructions.txt)
- assembly and injection: [console.py](/c:/devel/numel-playground/app/console.py)

## Workflow Agent Stack

Workflow agents created from graph nodes use this stack:

1. `agent_options_config.instructions`
2. Optional `prompt_override` as the system message

Files involved:

- assembly: [backend_factory.py](/c:/devel/numel-playground/app/backend_factory.py) plus the active backend implementation module
- skill source: [skills.py](/c:/devel/numel-playground/app/skills.py)

Intended meaning:

- `instructions`: role and task guidance for that specific workflow agent
- `prompt_override`: hard system-level override when the workflow author explicitly wants one

Runtime note:

- Connected toolkits are attached as backend-native tool containers.
- Connected skills are attached as backend-native skill bundles.
- Any extra toolkit guidance or skill metadata is injected by the backend itself, not by Numel's shared prompt assembly.

## What Belongs Where

Use the following rule of thumb:

- Base assistant instructions: stable product identity and general operating behavior
- Skills: reusable know-how that can apply across tasks and sessions, attached natively by the backend
- Toolkits: callable external capabilities, attached natively by the backend
- Workflow generation contract: exact JSON/schema/node-building rules for building workflows
- Planner instructions: autonomous strategy for deciding when and how to inspect, run, evaluate, and replace workflows

## What Should Not Be Mixed

- Do not treat the node catalog as a skill
- Do not let planner instructions redefine the workflow schema
- Do not bury the generation contract after planner behavior text
- Do not use skills for rapidly changing runtime-specific schema contracts

## Current Intent

The intended prompt semantics are now:

- normal assistant: helpful copilot
- `/gen`: workflow compiler
- planner: autonomous workflow architect
- workflow agent: task-specific runtime agent inside the graph
