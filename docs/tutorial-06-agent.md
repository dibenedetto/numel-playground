# Tutorial 6: AI Agent with Tools

Wire together configuration nodes to build a complete AI agent, then interact with it through the chat interface.

## What You Will Learn

- How config nodes wire into an Agent Config
- Setting up a model provider (Ollama)
- Registering tools for the agent to use
- Interactive chat with streaming responses
- The difference between config edges (`"get"`) and flow edges (`"output"/"input"`)

## Prerequisites

This tutorial requires [Ollama](https://ollama.com) running locally with the `mistral` model:

```bash
ollama pull mistral
ollama serve
```

## The Workflow

The workflow has two layers: **configuration** (top) and **flow** (bottom).

```
Backend ──┐
Model ────┤
Tool 1 ───┤──> Agent Config ──> Agent Chat
Tool 2 ───┤                        ^
Options ──┘                        │
                          Start ───┘──> End
```

### Configuration Layer

Five config nodes feed into the Agent Config:

| Node | Type | Purpose |
|------|------|---------|
| Backend (Agno) | `backend_config` | Selects the agent framework |
| Model (Ollama/Mistral) | `model_config` | Selects the LLM provider and model |
| Tool: List Dir | `tool_config` | Registers `app.tools.list_directory` |
| Tool: Read File | `tool_config` | Registers `app.tools.read_file` |
| Agent Options | `agent_options_config` | Instructions, markdown rendering |

### Flow Layer

```
Start ──> Agent Chat ──> End
```

The Agent Chat node receives its configuration from Agent Config and provides an interactive chat interface.

## Key Concepts

### Config Edges vs Flow Edges

Config edges use `"get"` as the source slot and the config field name as the target slot:

```json
{ "source": 0, "target": 5, "source_slot": "get", "target_slot": "backend" }
```

Flow edges use field names like `"output"` and `"input"`:

```json
{ "source": 6, "target": 7, "source_slot": "output", "target_slot": "input" }
```

### Multi-Slot Tool Wiring

When an Agent Config has multiple tools, each tool connects to a named sub-slot using dot notation:

```json
{ "source": 2, "target": 5, "source_slot": "get", "target_slot": "tools.list_dir" }
{ "source": 3, "target": 5, "source_slot": "get", "target_slot": "tools.read_file" }
```

The part after `tools.` is an arbitrary key name — it just needs to be unique.

### Tool Config

Each Tool Config node references a Python function by its module path:

```
app.tools.list_directory
app.tools.read_file
```

The engine imports the function and registers it with the agent framework. The function's docstring is used as the tool description.

### Agent Options

The `instructions` field is a list of strings that guide the agent's behavior:

```json
{
  "instructions": [
    "You are a helpful file assistant.",
    "Use the list_directory and read_file tools to explore files.",
    "Always confirm before taking actions."
  ]
}
```

## Steps

1. **Start Ollama** if it's not already running.
2. **Import** `tutorial-06-agent.json`.
3. Observe the two layers: config nodes (no flow connections between them) and flow nodes.
4. Click **Start**. The Agent Chat panel opens.
5. Type: `List the files in the current directory`
6. Watch the agent call the `list_directory` tool and return results.
7. Try: `Read the contents of README.md` — the agent uses `read_file`.

## Experimenting

- **Change the model**: Edit the Model Config to use a different provider (`openai`, `anthropic`, `groq`, `google`) and model name. You'll need the appropriate API key set as an environment variable.
- **Add more tools**: Create additional Tool Config nodes for `app.tools.search_files` or `app.tools.file_info` and wire them to the Agent Config.
- **Customize instructions**: Edit the Agent Options to change the agent's personality or restrict its behavior.
- **Add memory**: Wire a Memory Manager Config node to the Agent Config's `memory_mgr` slot for persistent conversation memory.

## Available Tools

| Tool Reference | What It Does |
|----------------|--------------|
| `app.tools.list_directory` | List files and folders in a directory |
| `app.tools.read_file` | Read the contents of a text file |
| `app.tools.write_file` | Write content to a file |
| `app.tools.file_info` | Get file metadata (size, dates, type) |
| `app.tools.search_files` | Recursive glob search for files |
| `app.tools.send_email` | Send email via SMTP |
| `app.tools.retrieve_emails` | Retrieve emails via IMAP |

## What's Next

In [Tutorial 7](tutorial-07-preview-media.md), you'll explore the Preview node's support for different data and media types.
