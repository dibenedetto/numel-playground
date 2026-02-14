# Tutorial 8: Generating Workflows with /gen

Use the `/gen` command inside an Agent Chat node to describe a workflow in plain English and have the AI generate it for you.

## What You Will Learn

- How to use the `/gen` command in the chat panel
- How the generation prompt and node catalog work
- Importing generated workflows into the canvas
- Tips for writing effective generation prompts

## Prerequisites

This tutorial requires an AI agent running. You need either:

- [Ollama](https://ollama.com) running locally with a capable model (e.g., `mistral`, `llama3`)
- Or API keys for OpenAI, Anthropic, Groq, or Google set as environment variables

## Setup

You need an Agent Chat node connected to an Agent Config (same setup as [Tutorial 6](tutorial-06-agent.md)):

```
Backend ──┐
Model ────┤──> Agent Config ──> Agent Chat
Options ──┘         ^
              Start ─┘──> End
```

Import `tutorial-06-agent.json` as a starting point, or build your own agent configuration.

## Using /gen

1. **Start the workflow** so the Agent Chat becomes active.
2. In the chat input, type:

   ```
   /gen A workflow that takes user input, transforms it to uppercase, and shows the result in a preview
   ```

3. The agent generates a workflow JSON and streams it back as a chat message.
4. Two controls appear below the response:
   - **Import to Canvas** — replaces the current canvas with the generated workflow
   - **Preview JSON** — expandable section showing the raw JSON

5. Click **Import to Canvas** to load the workflow.
6. The canvas updates with the new nodes and edges, auto-laid out.

## How It Works

When you type `/gen [description]`, the following happens:

1. The frontend intercepts the `/gen` prefix and extracts the description
2. It fetches a **generation prompt** from the backend containing:
   - A system prompt with output format rules
   - A **node catalog** listing every available node type with its inputs and outputs
3. The description is combined with the generation prompt and sent to the connected agent
4. The agent's LLM generates a workflow JSON following the format rules
5. The frontend extracts the JSON from the response (handles raw JSON, markdown code blocks, or embedded JSON)
6. The "Import to Canvas" button is rendered alongside the response

### The Node Catalog

The generation prompt includes a catalog of all registered node types, automatically built from the Python schema. Each entry lists:

- The node type identifier (e.g., `transform_flow`)
- Input fields and their types
- Output fields and their types

This gives the LLM the information it needs to construct valid workflows.

### The Output Format

The LLM is instructed to return JSON in this format:

```json
{
  "type": "workflow",
  "nodes": [
    { "type": "start_flow" },
    { "type": "transform_flow", "lang": "python", "script": "output = str(input).upper()" },
    { "type": "preview_flow" },
    { "type": "end_flow" }
  ],
  "edges": [
    { "source": 0, "target": 1, "source_slot": "output", "target_slot": "input" },
    { "source": 1, "target": 2, "source_slot": "output", "target_slot": "input" },
    { "source": 2, "target": 3, "source_slot": "output", "target_slot": "input" }
  ]
}
```

## Example Prompts

Here are some prompts to try:

### Simple pipeline
```
/gen Start, ask the user for their name, then greet them with "Hello, [name]!" in a preview
```

### Branching logic
```
/gen A workflow that asks the user to pick a color (red, blue, green), routes to different branches that each format a message about the color, then merges and previews the result
```

### Loop with processing
```
/gen A for-each loop that iterates over the list ["apple", "banana", "cherry"], transforms each item to uppercase, and previews each one
```

### Multi-step data pipeline
```
/gen A workflow with two transforms: the first creates a dictionary with name="Test" and values=[1,2,3,4,5], the second computes the sum and average of the values list. Preview the final result.
```

## Tips for Better Results

1. **Be specific about node types**: Mention "preview", "transform", "user input", "route", "loop" explicitly — these map directly to node types the LLM knows.

2. **Describe the data flow**: Say what each step should produce, not just what it should do. "Transform that outputs a dictionary with keys x, y, z" is better than "process the data".

3. **Include script logic**: If you need specific Python logic, describe it: "a transform that splits the input string on commas and returns a list".

4. **Mention connections**: If the flow isn't linear, describe branching: "route to branch A if the value is positive, branch B otherwise".

5. **Start simple**: Generate a basic workflow first, then modify it manually or generate additions.

6. **Iterate**: If the first result isn't right, describe what to change: `/gen Same as before but add a delay of 1 second between each loop iteration`.

## Troubleshooting

| Problem | Solution |
|---------|----------|
| No response | Check that the agent is connected and the LLM is running |
| Invalid JSON | The model may have included explanation text — try a more capable model |
| Missing connections | The model may have used wrong slot names — check edges manually |
| Unknown node types | The model may have invented types — ensure it's using the catalog |
| Import button missing | The JSON extraction failed — check "Preview JSON" or copy from chat |

## What's Next

Combine `/gen` with manual editing for rapid prototyping:

1. Generate a skeleton workflow with `/gen`
2. Import it to the canvas
3. Fine-tune node properties, add connections, or insert additional nodes manually
4. Use the workflow immediately or export it as JSON for reuse
