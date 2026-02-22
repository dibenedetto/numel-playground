# Numel Playground

Numel Playground is a visual workflow editor for building and running agentic AI workflows. It combines an interactive node graph canvas with a framework-agnostic[^1] Python backend, enabling you to design, test, and execute complex data pipelines and AI agent configurations without writing boilerplate code.

[^1]: Currently [Agno](https://www.agno.com) is supported.

![Numel Playground - Teaser](teaser.jpg)

## Architecture

```
+-----------------+       WebSocket / REST       +-------------------+
|    Frontend     | <------------------------->  |     Backend       |
|  (Browser)      |                              |  (Python)         |
|                 |                              |                   |
| Canvas Editor   |   POST /schema               | FastAPI Server    |
| Node Palette    | <-- Python source ---------- | Pydantic Schema   |
| Event Log       |                              | Agno Framework    |
| Chat Panel      |   WS /events                 | Workflow Engine   |
+-----------------+ <-- real-time events -------- +-------------------+
```

- **Backend**: FastAPI server (`app/`) with Pydantic models defining every node type. The schema source code is sent to the frontend, which parses it to build the node palette dynamically.
- **Frontend**: Vanilla JavaScript canvas-based graph editor (`web/schemagraph/`). No build step required for the core UI.
- **Communication**: REST API for commands (upload, start, cancel), WebSocket for real-time events (node status changes, execution progress, streaming output).

## Getting Started

### Prerequisites

- Python 3.12+
- ```pip install -r requirements.txt```
- For AI agent features: [Ollama](https://ollama.com) running locally, or API keys for OpenAI/Anthropic/Groq/Google
- A modern web browser (Chrome, Firefox, Edge)

### Starting the Server

```bash
cd app
python app.py
```

The server starts on port 8000 by default.

### Connecting the Frontend

1. Open `web/index.html` in your browser (serve via any static file server, or open directly)
2. Enter the server URL (default: `http://localhost:8000`) in the connection panel
3. Click **Connect** — the status indicator turns green when connected

### Importing a Workflow

1. Click the **Import** button in the left panel, or drag a `.json` file onto the canvas
2. The workflow nodes appear on the canvas with their connections
3. Click **Start** to execute the workflow

## The Canvas

| Action | How |
|--------|-----|
| **Pan** | Click and drag on empty canvas |
| **Zoom** | Mouse wheel |
| **Add node** | Right-click canvas, or use the node palette |
| **Connect** | Drag from an output slot (right side) to an input slot (left side) |
| **Select** | Click a node; Ctrl+A to select all |
| **Delete** | Select node(s), press Delete or Backspace |
| **Preview data** | Alt+click on an edge to insert a preview node |
| **Edit fields** | Click on a node's input field to edit values inline |
| **Code editor** | Click the code icon on script fields to open a full editor |

## Node Types Reference

### Endpoints

| Node | Icon | Description |
|------|------|-------------|
| **Start** | ▶ | Entry point of a workflow. Outputs workflow variables. |
| **End** | 🏁 | Exit point. Receives final output. |
| **Sink** | 🚧 | Dead end — terminates a branch without producing output. |

### Data Flow

| Node | Icon | Description |
|------|------|-------------|
| **Preview** | ➠ | Displays data flowing through it. Supports text, JSON, images, audio, video, and 3D models. Has a `hint` field to override auto-detection. |
| **Transform** | 🏗️ | Transforms data using Python or Jinja2 scripts. Fields: `lang`, `script`, `context`, `input`. The script sets `output` to define what flows downstream. |
| **Route** | 🔁 | Conditional branching. Reads a `target` field and routes data to the matching named output. Unmatched targets go to `default`. |
| **Combine** | 🔀 | Combines multiple named inputs into a single output with a mapping dictionary. |
| **Merge** | 🪢 | Takes multiple inputs and outputs the first non-null value (strategy: `first`). |

### Loops

| Node | Icon | Description |
|------|------|-------------|
| **Loop Start** | 🔁 | While-style loop. Fields: `condition` (boolean), `max_iter` (safety limit). Outputs `iteration` count. |
| **Loop End** | ↩️ | Marks the end of a loop body. Connect back to Loop Start with a `"loop": true` edge. |
| **ForEach Start** | 📋 | Iterates over a list. Field: `items`. Outputs `current` item and `index`. |
| **ForEach End** | ↩️ | End of for-each body. Connect back to ForEach Start with a `"loop": true` edge. |
| **Break** | ⏹️ | Exit the current loop immediately. |
| **Continue** | ⏭️ | Skip to the next iteration. |

### Timing & Gates

| Node | Icon | Description |
|------|------|-------------|
| **Timer** | ⏱️ | Fires periodically. Fields: `interval_ms`, `max_triggers`. Outputs `count` and `elapsed_ms`. |
| **Delay** | ⏸️ | Pauses execution for `duration_ms` milliseconds. |
| **Gate** | 🚧 | Accumulates inputs until a threshold/condition is met, then fires. |

### Event Sources

| Node | Icon | Description |
|------|------|-------------|
| **Event Listener** | 📡 | Waits for events from registered sources. Modes: `any`, `all`, `race`. |
| **Timer Source** | 🕐 | Registers a timer that emits events at intervals. |
| **FS Watch Source** | 📂 | Watches a filesystem path for changes. |
| **Webhook Source** | 🔗 | Creates an HTTP endpoint that triggers events on incoming requests. |
| **Browser Source** | 🎥 | Captures webcam, microphone, or screen from the browser. |

### Interactive

| Node | Icon | Description |
|------|------|-------------|
| **User Input** | 👤 | Pauses the workflow and prompts the user for text input. |
| **Tool Call** | ☎️ | Interactive tool invocation with an Execute button. |
| **Agent Chat** | 🗪 | Full chat interface with streaming, message history, and timestamps. |

### Agent Configuration

These nodes wire together to define an AI agent:

| Node | Purpose |
|------|---------|
| **Backend** | Framework selection (default: Agno) |
| **Model** | LLM provider and model name (Ollama, OpenAI, Anthropic, Groq, Google) |
| **Embedding** | Embedding model for RAG |
| **Content DB** | Raw content storage (SQLite) |
| **Index DB** | Vector database for semantic search (LanceDB) |
| **Memory Manager** | Agent memory (query, update, managed flags) |
| **Session Manager** | Conversation session tracking |
| **Knowledge Manager** | RAG pipeline (file upload, URL import, search) |
| **Tool** | Tool function reference (e.g., `app.tools.list_directory`) |
| **Agent Options** | Name, description, instructions, prompt override |
| **Agent** | Main agent node — connects all config nodes together |

### Native Types

Direct value nodes for constants: **String**, **Integer**, **Real**, **Boolean**, **List**, **Dictionary**.

## Workflow JSON Format

A workflow is defined as a JSON file with three sections:

```json
{
  "options": {
	"type": "workflow_options",
	"name": "My Workflow",
	"description": "What this workflow does"
  },
  "nodes": [
	{ "type": "start_flow", "extra": { "name": "Start" } },
	{ "type": "end_flow", "extra": { "name": "End" } }
  ],
  "edges": [
	{
	  "source": 0,
	  "target": 1,
	  "source_slot": "output",
	  "target_slot": "input"
	}
  ]
}
```

- **nodes**: Array of node objects. Each has a `type` field matching the schema class. Additional fields are the node's input values. The `extra` object holds visual metadata (`name`, `pos`, `size`, `color`).
- **edges**: Array of connections. `source`/`target` are node indices (0-based). Slot names match the schema field names. Loop-back edges include `"loop": true`.
- **options**: Optional workflow-level settings (name, description, seed).

### Config Node Wiring

Config nodes use `"get"` as `source_slot` and the target field name as `target_slot`:

```json
{ "source": 0, "target": 2, "source_slot": "get", "target_slot": "backend" }
```

Multi-slot fields use dot notation:

```json
{ "source": 3, "target": 5, "source_slot": "get", "target_slot": "tools.my_tool" }
```

## Available Tools

Tools are Python functions in `app/tools.py`, referenced as `app.tools.<function_name>` in ToolConfig nodes.

| Tool | Signature | Description |
|------|-----------|-------------|
| `square_tool` | `(n: int) -> int` | Returns n squared |
| `list_directory` | `(path, root) -> str` | List directory contents |
| `read_file` | `(path, root) -> str` | Read a text file |
| `write_file` | `(path, content, root) -> str` | Write content to a file |
| `file_info` | `(path, root) -> str` | Get file metadata |
| `search_files` | `(pattern, path, root) -> str` | Recursive glob search |
| `send_email` | `(to, subject, body, ...) -> str` | Send email via SMTP |
| `retrieve_emails` | `(folder, limit, ...) -> str` | Retrieve emails via IMAP |

All filesystem tools accept a `root` parameter that constrains operations to prevent path traversal.

## Tutorials

1. [Hello Workflow](docs/tutorial-01-hello-workflow.md) — Your first workflow: Start, Preview, End
2. [Data Transformation](docs/tutorial-02-transform.md) — Transform data with Python scripts
3. [Routing and Merging](docs/tutorial-03-routing.md) — Conditional branching and merging
4. [Loops and Iteration](docs/tutorial-04-loops.md) — While loops and for-each iteration
5. [Events and Timers](docs/tutorial-05-events.md) — Timer sources and event listeners
6. [AI Agent with Tools](docs/tutorial-06-agent.md) — Full agent setup with chat
7. [Preview and Media Types](docs/tutorial-07-preview-media.md) — All supported preview formats
8. [Generating Workflows with /gen](docs/tutorial-08-generate.md) — AI-powered workflow generation from natural language
