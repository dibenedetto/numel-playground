# UI Exploration Review

Numel now includes three lightweight visual exploration prototypes under `web/prototypes/ui-exploration/`.

Open:

- `web/prototypes/ui-exploration/index.html`
- `web/prototypes/ui-exploration/project-workbench.html`
- `web/prototypes/ui-exploration/assistant-studio.html`
- `web/prototypes/ui-exploration/creative-agent-studio.html`

What these prototypes are for:

- compare overall tone and emotional feel
- compare first-run hierarchy
- compare how strongly the assistant should lead the experience
- compare how much Numel should lean into multimodal identity
- decide which direction should drive the next real frontend slice

Recommended evaluation criteria:

1. Which concept makes the product feel most understandable in under a minute?
2. Which one makes spaces feel useful instead of technical?
3. Which one best balances starter guidance, canvas editing, and execution?
4. Which one feels most commercially appealing without misrepresenting what Numel actually does?
5. Which one gives the strongest foundation for onboarding, templates, assistant generation, and debugging?

Current recommendation:

- Use `Project Workbench` as the base direction.
- Borrow the strongest onboarding and assistant-entry ideas from `Assistant Studio`.
- Borrow selected visual energy from `Creative Agent Studio` for multimodal and showcase surfaces, not as the default whole-product shell.

Suggested next implementation slice after choosing:

1. Auth and first-run welcome
2. Space/workflow left rail
3. Empty-space starter state
4. Assistant entry and planner handoff

This keeps the redesign focused on the parts of Numel that shape first impressions most strongly.
