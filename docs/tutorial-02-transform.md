# Tutorial 2: Data Transformation

Transform data using Python scripts inside the workflow.

## What You Will Learn

- How the Transform node works
- The relationship between `input`, `context`, `script`, and `output`
- How to edit node fields inline and with the code editor

## The Workflow

```
Start ──> Transform ──> Preview ──> End
```

The Transform node runs a Python script that builds an output dictionary from the context and input data.

## How Transform Works

The Transform node has four key fields:

| Field | Role |
|-------|------|
| **lang** | Script language (`python` or `jinja2`) |
| **script** | The code to execute |
| **context** | A dictionary of extra data available to the script |
| **input** | Data arriving from the upstream connection |

In Python mode, the script runs with these variables in scope:

- `input` — data from the input slot
- `context` — data from the context field
- `variables` — workflow-level variables from Start
- `output` — set this to define what flows downstream

The default script is simply `output = input` (pass-through).

## This Tutorial's Script

```python
output = {
    "message": "Hello from Numel!",
    "tag_count": len(context.get("tags", [])),
    "tags": context.get("tags", [])
}
```

The `context` field is set to `{"tags": ["alpha", "beta", "gamma"]}`. When executed, the Preview shows:

```json
{
  "message": "Hello from Numel!",
  "tag_count": 3,
  "tags": ["alpha", "beta", "gamma"]
}
```

## Steps

1. **Import** `tutorial-02-transform.json`.
2. Click the Transform node to inspect its fields — you'll see `lang`, `script`, `context`, and `input`.
3. Click the code icon next to `script` to open the code editor. The script reads data from `context` and builds the output dictionary.
4. The `context` field is pre-filled with `{"tags": ["alpha", "beta", "gamma"]}`.
5. Click **Start** to execute. The Preview node shows the computed result.

## Experimenting

- **Change the context**: Edit the `context` field to `{"tags": ["x", "y"]}` and re-run. The `tag_count` updates to 2.
- **Use the input slot**: Connect a native String node to the Transform's `input` slot. Modify the script to `output = input.upper()` to transform the string.
- **Try Jinja2**: Change `lang` to `jinja2` and `script` to `Hello {{ context.tags | join(', ') }}!` — the output becomes a rendered template string.

## Security Note

Python scripts run with `__builtins__` disabled. Only basic operations are available — no file I/O, imports, or network access from within scripts. For those capabilities, use Tool nodes instead.

## What's Next

In [Tutorial 3](tutorial-03-routing.md), you'll learn conditional routing to send data down different branches.
