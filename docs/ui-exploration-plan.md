# Numel UI Exploration Plan

This document defines a bounded design-exploration step for making Numel feel
less "nerdy", more welcoming, and more product-like without losing the current
power of the platform.

Concrete exploration artifacts now live in:

- [ui-exploration-review.md](/c:/devel/numel-playground/docs/ui-exploration-review.md)
- [index.html](/c:/devel/numel-playground/web/prototypes/ui-exploration/index.html)
- [project-workbench.html](/c:/devel/numel-playground/web/prototypes/ui-exploration/project-workbench.html)
- [assistant-studio.html](/c:/devel/numel-playground/web/prototypes/ui-exploration/assistant-studio.html)
- [creative-agent-studio.html](/c:/devel/numel-playground/web/prototypes/ui-exploration/creative-agent-studio.html)

The goal is not a full redesign before we learn anything. The goal is to
explore a few strong interface directions, choose one quickly, and then use it
to guide the next product-roadmap slice.

## Recommendation

Do the UI exploration **now**, before continuing the next big product-roadmap
implementation wave.

Reason:

- the current roadmap is heavily product-facing
- onboarding, starter flows, planner-first UX, and stronger space/project
  framing are all strongly shaped by the visual system
- if we keep building those flows on top of the current UI language, we will
  probably redo them later

Recommended order:

1. explore 2-3 UI directions
2. choose one direction
3. implement one thin vertical slice
4. continue the roadmap using that chosen direction

## What Must Stay Stable

The exploration should change the **presentation**, not the core product model.

Keep these stable:

- spaces remain the top-level project/workbench concept
- one current workflow per current space
- the canvas remains the main editing surface
- the assistant console remains a first-class entry point
- local/prod platform switching remains invisible at the app interface level
- the product still supports advanced users and deep workflows

The exploration should **not** become:

- a rewrite of backend behavior
- a removal of advanced functionality
- a total rethinking of the platform model
- a generic "pretty dark dashboard"

## Why The Current UI Feels Too Nerdy

The current interface is powerful, but it still signals "engineering tool"
before it signals "useful product".

Main problems to solve:

- too much dense control surface at first glance
- weak distinction between beginner actions and expert controls
- too much system language exposed too early
- a visual tone closer to a console/workbench for developers than a guided tool
- the first-run experience still depends on the user understanding the product
  structure too quickly

## Exploration Goals

The exploration should improve these product qualities:

- clarity: users understand where to start
- warmth: the product feels less intimidating
- hierarchy: the most important next action is visually obvious
- guidance: the UI suggests outcomes, not just controls
- confidence: users can tell what space/workflow they are in and what will
  happen next

## Screens To Explore First

Do not redesign everything at once. Use the same four product slices for every
concept direction so comparison is meaningful.

### 1. First-Run Auth And Welcome

Focus:

- login / create-admin screen
- welcome framing
- first value proposition
- first action after login

Questions:

- does the screen feel like a product or a technical gateway?
- does a first user understand what Numel is for?

### 2. Empty Space / Starter State

Focus:

- current space section
- starter panel / starter modal
- gallery / assistant / hello workflow entry
- explanation of what a space is

Questions:

- does the empty state feel exciting instead of blank?
- is the user pushed toward a first successful run?

### 3. Main Left Panel / Workflow Control Surface

Focus:

- section hierarchy
- naming and copy
- density reduction
- distinction between core actions and advanced actions

Questions:

- what should a new user see immediately?
- what can be tucked away or softened visually?

### 4. Assistant Entry And Planner Surface

Focus:

- console open state
- prompt-first workflow generation
- planner explanation
- relationship between chat and graph

Questions:

- does the assistant feel like a natural front door?
- can a user understand "describe -> generate -> edit -> run" quickly?

## Candidate Directions

These are the three directions worth exploring first.

### Direction A: Project Workbench

Core feel:

- calmer
- clearer
- more structured
- less hacker-console energy

Product promise:

- "This is your project workspace for building and running AI workflows."

Characteristics:

- clearer section hierarchy
- stronger labels and summaries
- softened technical chrome
- more visible project/space identity
- practical, professional tone

Good for:

- making spaces feel real
- helping new users orient themselves
- preserving trust for technical users

Risk:

- can become too plain or too enterprise if not kept lively

### Direction B: Assistant Studio

Core feel:

- assistant-first
- guided
- conversational
- creation-oriented

Product promise:

- "Describe what you want and shape it into a workflow."

Characteristics:

- chat/prompt entry becomes visually primary
- starter actions feel like guided missions
- planner is framed as help, not hidden capability
- graph editor remains central but not the first thing shouting at the user

Good for:

- differentiating Numel from node tools
- making `/gen` and planner central
- improving approachability

Risk:

- can underplay the power of the visual canvas if pushed too far

### Direction C: Creative Agent Studio

Core feel:

- more expressive
- more atmospheric
- more distinctive
- less utilitarian

Product promise:

- "Build live multimodal agents in a studio, not a control panel."

Characteristics:

- stronger typography and visual identity
- a more cinematic empty state
- richer starter cards and visual storytelling
- more visible multimodal value

Good for:

- making Numel memorable
- highlighting webcam/browser/media strengths
- separating the product from generic workflow UIs

Risk:

- can drift into style-first design without enough clarity

## Recommended Direction

If only one direction is pursued first, start with:

**Direction A: Project Workbench**

Why:

- it solves the clarity and intimidation problem fastest
- it fits the current product structure well
- it reduces rework for onboarding and space/project UX
- it is the safest foundation for later layering in more of Direction B

Practical recommendation:

- use **Direction A** as the base system
- borrow selected ideas from **Direction B** for onboarding and assistant entry

In other words:

- overall product = Project Workbench
- first-run and planning moments = Assistant Studio

## What To Keep From The Current UI

These are worth preserving:

- the canvas itself as the center of real work
- the current theme system as a base for iteration
- the assistant console as a first-class panel
- the starter flow concept
- the space selector as a top-level product control
- strong admin and power-user access for expert users

These are candidates for softening or reorganizing:

- left-panel density
- terminology that appears before it is needed
- equal visual weight for too many controls
- technical-feeling empty states
- the sense that every panel is equally important

## Exploration Deliverables

Keep the exploration small and comparable.

For each direction, produce:

- one auth/welcome screen concept
- one empty-space starter state concept
- one main left-panel concept
- one assistant-entry/planner concept

For each concept, include:

- a short visual rationale
- what changes from the current UI
- what stays the same
- tradeoffs

The output can be:

- HTML/CSS mock screens
- lightweight frontend prototypes
- or static design boards captured in repo docs

The important thing is that the concepts are concrete enough to compare.

## Decision Criteria

Choose the winning direction based on:

- which one makes first-run actions clearest
- which one best explains spaces and current workflow
- which one makes the assistant/planner feel useful rather than obscure
- which one preserves expert power without scaring off new users
- which one can be implemented incrementally without rewriting the whole app

## First Implementation Slice After Exploration

Once a direction is chosen, implement only this first:

- auth / welcome
- empty space starter state
- left panel top section
- assistant entry affordance

Do **not** redesign the whole product in the same pass.

Success criteria for that first slice:

- a new user understands what Numel is for
- a new user sees one obvious next action
- the empty space feels like an invitation, not a blank editor
- the assistant feels like a real entry point

## Relationship To The Product Roadmap

This exploration directly supports the top roadmap priorities in
[product-roadmap.md](/c:/devel/numel-playground/docs/product-roadmap.md):

- first-run success in 10 minutes
- starter spaces and templates
- planner as the front door
- better execution clarity
- stronger product language

So the recommended sequence is:

1. UI exploration
2. direction choice
3. first implementation slice
4. continue roadmap execution

## Suggested Next Step

The next concrete step should be:

1. create 2-3 exploration concepts for the same four screens
2. choose one direction quickly
3. implement the first vertical slice in the live frontend

If time is tight, explore only these two:

- Project Workbench
- Assistant Studio
