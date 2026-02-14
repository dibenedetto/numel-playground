# Tutorial 3: Routing and Merging

Route data to different branches based on conditions, then merge the results.

## What You Will Learn

- How User Input pauses a workflow for interactive input
- How Route sends data to different named outputs
- How Merge collects results from multiple branches
- Conditional logic with Transform scripts

## The Workflow

```
Start ──> User Input ──> Classifier ──> Route ──┬── Support Branch ──┐
                                                 ├── Sales Branch ────┤──> Merge ──> Preview ──> End
                                                 └── Default Branch ──┘
```

1. **User Input** prompts the user for a message
2. **Classifier** (Transform) examines the text and sets a `target` variable
3. **Route** sends data to the matching named output
4. Three **branch transforms** each format a different response
5. **Merge** picks the first result that arrives

## Key Concepts

### Route Node

The Route node has dynamic output slots. Each slot has a name (e.g., `support`, `sales`). The Route reads a `target` field from its input and sends data to the matching slot. If no match is found, data goes to `default`.

### Merge Node

The Merge node has dynamic input slots. With `strategy: "first"`, it outputs the first non-null value it receives. Since only one route branch executes per run, exactly one value arrives.

### Classification Script

```python
text = str(input).lower()
if "help" in text or "broken" in text or "error" in text:
    target = "support"
elif "buy" in text or "price" in text or "order" in text:
    target = "sales"
else:
    target = "default"
output = input
```

The script sets both `target` (for routing) and `output` (the data to pass along).

## Steps

1. **Import** `tutorial-03-routing.json`.
2. Click **Start**. A dialog appears asking for input.
3. Type `my printer is broken` and press Enter.
4. Watch the Route node send data to the `support` branch.
5. The Preview shows: `"Support: We'll help with your issue: my printer is broken"`
6. Re-run with `I want to buy a widget` — the `sales` branch activates.
7. Re-run with `hello there` — the `default` branch activates.

## What's Next

In [Tutorial 4](tutorial-04-loops.md), you'll learn to repeat operations with loops.
