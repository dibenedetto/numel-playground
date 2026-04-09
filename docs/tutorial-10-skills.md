# Tutorial 10: Skills

Wire a **Skill Config** node to an Agent to inject natural language instructions into its system prompt. Unlike toolkits (Python code), skills are markdown instruction packages that teach the agent *how* to use existing tools for specific tasks.

## What You Will Learn

- How to use a **Skill Config** node to attach skill instructions to an agent
- The difference between skills (instructions) and toolkits (callable tools)
- Wiring a skill to `agent_config.skills.<key>` via the graph editor
- How skills and toolkits work together — the skill teaches, the toolkit provides tools

## Prerequisites

- [Ollama](https://ollama.com) running locally with the `mistral` model
- The built-in `web-search` skill in `app/skills/web-search/`
- The built-in `http_toolkit` (provides the `get` tool the skill instructs the agent to use)

## The Workflow

```
Backend ──────┐
Model ────────┤
Options ──────┤──> Agent Config ──> Agent Flow ──> Preview ──> End
Skill ────────┤                     ^   ^
HTTP Toolkit ─┘               flow  │   │ request (data)
                    User Input ─────┘───┘
                        ^
Start ──────────────────┘
```

Two layers:

1. **Config layer** (top): Backend, Model, Options, Skill, and Toolkit all feed into Agent Config. The Skill injects web-search instructions into the agent's system prompt. The Toolkit gives the agent the HTTP `get` tool.
2. **Flow layer** (bottom): Start triggers User Input, which prompts "What would you like to research?". The user's answer flows as `request` to Agent Flow, which runs the agent. The agent follows the skill instructions to search DuckDuckGo using the HTTP toolkit's `get` tool. The response is previewed.

## Node Breakdown

| # | Node | Type | Purpose |
|---|------|------|---------|
| 0 | Backend (Agno) | `backend_config` | Agent framework |
| 1 | Model (Ollama/Mistral) | `model_config` | LLM provider |
| 2 | Agent Options | `agent_options_config` | Base instructions |
| 3 | Skill: Web Search | `skill_config` | Injects web search instructions |
| 4 | HTTP Toolkit | `toolkit_config` | Provides HTTP `get` tool |
| 5 | Research Agent | `agent_config` | Combines all config |
| 6 | Start | `start_flow` | Flow entry point |
| 7 | User Question | `user_input_flow` | Prompts for a research topic |
| 8 | Research | `agent_flow` | Runs the agent |
| 9 | Result Preview | `preview_flow` | Shows the agent's response |
| 10 | End | `end_flow` | Flow exit |

## Key Concepts

### Skills vs Toolkits

Skills and toolkits serve complementary roles:

| | Toolkits | Skills |
|---|---|---|
| **What they are** | Python classes with callable methods | Markdown instruction packages |
| **What they provide** | Tools the agent can call (`get`, `read_file`, etc.) | Instructions added to the system prompt |
| **Who executes** | The backend runs the tool function | The LLM follows the instructions |
| **Schema node** | `toolkit_config` | `skill_config` |
| **Wires to** | `agent_config.toolkits.<key>` | `agent_config.skills.<key>` |

In this tutorial, the **HTTP Toolkit** gives the agent a `get` tool (it can make HTTP requests), but the agent doesn't inherently know *how to search the web*. The **Web Search Skill** teaches it:
- Which DuckDuckGo API URL to call
- How to format the query
- How to parse the JSON response
- How to present results with source links

Together: the toolkit provides the **capability**, the skill provides the **knowledge**.

### Skill Config Wiring

A Skill Config has one input and one output:

| Slot | Direction | Description |
|------|-----------|-------------|
| `name` | INPUT | Skill ID (e.g. `"web-search"`) — matches a directory in `app/skills/` |
| `config` | OUTPUT | Wires to `agent_config.skills.<key>` |

The `<key>` in `skills.<key>` is an arbitrary label (like `"search"` in this tutorial). It identifies the edge in the graph — you can name it anything.

```json
{ "source": 3, "target": 5, "source_slot": "config", "target_slot": "skills.search" }
```

At build time, the engine resolves the skill name via the SkillManager, reads its `SKILL.md` body, and appends it to the agent's instructions list.

### Multiple Skills

You can wire multiple Skill Config nodes to the same Agent Config — each with a different `target_slot` key:

```
skill_config("web-search")   → agent_config.skills.search
skill_config("git-assistant") → agent_config.skills.git
skill_config("api-tester")    → agent_config.skills.api
```

All skill instructions are merged into the agent's instruction stack under an `## Active Skill Packs` section.

## Steps

1. Choose a space, then **Import** `tutorial-10-skills.json`.
2. Click **Start**. A prompt appears: "What would you like to research?"
3. Type a search query, e.g.: `What is FastAPI?`
4. The agent uses the web-search skill instructions to call the DuckDuckGo API via the HTTP toolkit.
5. Check the **Result Preview** — the agent's response should include a summary with source URLs.

## Experimenting

- **Swap skills**: Change the Skill Config's `name` from `"web-search"` to `"git-assistant"` and swap the toolkit to `"toolkits.file_toolkit"`. Now the agent inspects git repos instead of searching the web.
- **Add a second skill**: Add another Skill Config (`"api-tester"`) and wire it to `agent_config.skills.api`. The agent now knows how to both search the web and test APIs.
- **Create your own skill**: Make a new directory under `app/skills/my-skill/` with a `SKILL.md` file. Restart the server, and the new skill appears in the Skill Config dropdown.
- **Chain with transforms**: Add a Transform Flow after the Agent Flow to post-process the search results (e.g., extract URLs into a list).
- **Remove the skill**: Delete the skill edge and re-run — notice the agent no longer knows how to format DuckDuckGo queries, even though it still has the HTTP toolkit.

## Creating a Skill

A skill is a directory under `app/skills/` with a `SKILL.md` file:

```
app/skills/
  my-skill/
    SKILL.md          # Required: YAML frontmatter + markdown body
    scripts/          # Optional: helper scripts (.py, .sh, .js)
    requirements.txt  # Optional: pip dependencies
```

Minimal `SKILL.md`:

```markdown
---
name: my-skill
description: What this skill teaches the agent to do
tags: [tag1, tag2]
requires:
  toolkits: [http_toolkit]
examples:
  - "Example prompt the user can try"
---

# My Skill

Step-by-step instructions for the agent...
```

After adding the directory, restart the server. The skill appears in:
- The assistant console settings (as a toggleable pill)
- The Skill Config node dropdown in the graph editor

## What's Next

You now know how to teach agents new abilities via skills without writing Python code. Skills are portable markdown files — share them, version them, or import OpenClaw-compatible skills from the community. Combine skills with toolkits to build agents that know both *what tools are available* and *how to use them effectively*.
