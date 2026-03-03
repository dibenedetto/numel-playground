# Tutorial 9: File Tools & Agent Prompting

Use Tool Config + Tool Flow to read a file from disk and send its content as a request to an Agent Chat node. The agent's response is previewed via the `response` slot.

## What You Will Learn

- How to use a **Tool Flow** node to call a tool function inside a workflow
- Wiring a **Tool Config** to a **Tool Flow** (config edge)
- Sending file content as a **request** to an Agent Chat
- Using Agent Chat's **request** and **response** slots to programmatically send and receive messages
- Using `tools.read_file` and `tools.write_file` from the built-in tool library

## Prerequisites

- [Ollama](https://ollama.com) running locally with the `mistral` model
- A text file called `prompt.txt` in the server's working directory

Create `prompt.txt` before running:

```
Summarize yourself in three bullet points. Who are you? What can you do? What are your limitations?
```

## The Workflow

```
Backend ──┐
Model ────┤
Options ──┤──> Agent Config ──> Agent Chat ──> Preview ──> End
Write ────┘                     ^   ^
                          flow  │   │ request (data)
Read File ──> Tool Flow (Load) ─┘───┘
                  ^
Start ────────────┘
```

Two layers:

1. **Config layer** (top): Backend, Model, Options, and Write File tool feed into Agent Config, which wires to Agent Chat.
2. **Flow layer** (bottom): Start triggers a Tool Flow that reads `prompt.txt`. The Tool Flow connects to Agent Chat with both a flow edge (execution chain) and a data edge (`output` → `request`). When the engine reaches Agent Chat, the request is auto-sent. The engine waits for the agent's reply, then continues: the `response` output feeds into Preview's `flow_in`, and the flow chain continues to End.

## Node Breakdown

| # | Node | Type | Purpose |
|---|------|------|---------|
| 0 | Backend (Agno) | `backend_config` | Agent framework |
| 1 | Model (Ollama/Mistral) | `model_config` | LLM provider |
| 2 | Agent Options | `agent_options_config` | Base instructions |
| 3 | Tool: Read File | `tool_config` | Declares `tools.read_file` |
| 4 | Tool: Write File | `tool_config` | Registers `tools.write_file` as agent tool |
| 5 | Agent Config | `agent_config` | Combines all config |
| 6 | Start | `start_flow` | Flow entry point |
| 7 | Load Prompt File | `tool_flow` | Calls `read_file(path="prompt.txt")` |
| 8 | Agent Chat | `agent_chat` | Interactive chat UI with request/response |
| 9 | Response Preview | `preview_flow` | Shows the agent's last response |
| 10 | End | `end_flow` | Flow exit |

## Key Concepts

### Agent Chat Request & Response

Agent Chat is a flow node — it participates in the execution chain like any other flow node. It also has two data slots for programmatic interaction:

| Slot | Direction | What It Does |
|------|-----------|--------------|
| `request` | INPUT | When wired, the message is automatically sent to the agent as if the user typed it. Displayed in the chat overlay as a user message. |
| `response` | OUTPUT | Contains the agent's last response text. Updates after each reply. Can be wired to Preview, Transform, or any other node. |

When the engine reaches Agent Chat during workflow execution, it:
1. Sends the `request` message (if wired) to the agent
2. **Waits** for the agent to respond
3. Outputs the response on the `response` slot and continues the flow

Without a running workflow, Agent Chat still works interactively — the user types in the chat overlay and the agent responds as usual.

### Tool Config vs Tool Flow

These are two different ways to use tools:

| | Tool Config | Tool Flow |
|---|---|---|
| **Purpose** | Registers a tool for an **agent** to call | Calls a tool **directly** in the flow |
| **Who calls it** | The LLM decides when | The workflow always calls it |
| **Wires to** | `agent_config.tools.<key>` | Standalone flow node |
| **Use case** | "Agent, here's a tool you can use" | "Read this file before the chat starts" |

In this tutorial we use **both**:
- `Tool: Read File` as a **Tool Config** wired to `Tool Flow` — the workflow calls `read_file` directly to load the file
- `Tool: Write File` as a **Tool Config** wired to `Agent Config.tools` — the agent can call `write_file` when it decides to

### Tool Flow Wiring

A Tool Flow needs two things:

1. **Config edge**: A Tool Config wired to its `config` input (tells it which function to call)
2. **Args**: The `args` field contains keyword arguments passed to the tool function

```json
{
  "type": "tool_flow",
  "args": { "path": "prompt.txt" }
}
```

This calls `tools.read_file(path="prompt.txt")` and outputs the file content on the `output` slot.

### Request from File

The Tool Flow's `output` slot is wired to Agent Chat's `request` input, and `flow_out` to `flow_in` for the execution chain:

```json
{ "source": 7, "target": 8, "source_slot": "flow_out", "target_slot": "flow_in" },
{ "source": 7, "target": 8, "source_slot": "output", "target_slot": "request" }
```

When the engine reaches Agent Chat, whatever text was in `prompt.txt` is automatically sent as the first chat message. The engine then waits for the agent to respond before continuing the flow.

### Response Preview

Agent Chat's `response` slot carries the last agent response. It's wired directly to Preview's `flow_in` — the data flows through the same slot used for execution ordering:

```json
{ "source": 8, "target": 9, "source_slot": "response", "target_slot": "flow_in" }
```

The Preview node displays the agent's reply text in a formatted panel, useful for debugging or inspecting responses.

## Steps

1. Create `prompt.txt` in the server's working directory with the prompt above.
2. **Import** `tutorial-09-file-tools.json`.
3. Click **Start**. The Tool Flow reads the file and sends the content as a request to the Agent Chat.
4. The agent responds to the file content automatically.
5. Check the **Response Preview** node — it shows the agent's reply.
6. Continue the conversation by typing in the chat: `Write your response to response.txt` — the agent uses the `write_file` tool.

## Experimenting

- **Change the prompt file**: Edit `prompt.txt` to ask a different question and re-run — the agent gets a different request without modifying the workflow.
- **Add a system prompt**: Wire a `native_string` node to Agent Chat's `system_prompt` input to set the agent's personality separately from the request.
- **Dynamic paths**: Wire a `native_string` node into the Tool Flow's `args` input to make the file path configurable.
- **Chain tools**: Add a second Tool Flow after the Preview to save the agent's response to a file via `write_file`.
- **Read multiple files**: Add more Tool Flow nodes reading different files, combine them with a Combine or Transform node, and wire the merged text to `request`.

## Available File Tools

| Tool Reference | Signature | What It Does |
|----------------|-----------|--------------|
| `tools.read_file` | `(path, root=".")` | Read text file contents |
| `tools.write_file` | `(path, content, root=".")` | Write text to a file |
| `tools.list_directory` | `(path=".", root=".")` | List directory contents |
| `tools.file_info` | `(path, root=".")` | Get file metadata |
| `tools.search_files` | `(pattern="*", path=".", root=".")` | Recursive glob search |

All file tools use `root` for path-traversal safety — resolved paths must stay within `root`.

## What's Next

You now know how to use Tool Flow to run tools as workflow steps, wire Agent Chat's request/response for programmatic interaction, and preview agent responses. This pattern works for any tool — not just file operations.
