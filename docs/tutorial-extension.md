# SchemaGraph Extension Tutorial

This tutorial demonstrates how to create a custom node type with both backend (Python) and frontend (JavaScript) functionality. We'll build a simple **Counter** node that can be incremented, decremented, and reset.

## Overview

A complete SchemaGraph extension consists of:

| Component | File | Purpose |
|-----------|------|---------|
| Schema | `app/schema.py` | Node definition with decorators (add to existing file) |
| API | `app/tutorial_api.py` | Backend endpoint for node actions |
| Extension | `web/schemagraph/schemagraph-tutorial-ext.js` | Frontend event handling |
| Reference | `app/tutorial_schema.py` | Reference file showing the pattern |

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        Frontend                              │
│  ┌─────────────────┐    ┌──────────────────────────────┐    │
│  │  SchemaGraph    │    │  Tutorial Extension          │    │
│  │  Canvas         │───▶│  - Event listeners           │    │
│  │  (Counter node) │    │  - API calls                 │    │
│  └─────────────────┘    │  - Value updates             │    │
│                         └──────────────┬───────────────┘    │
└────────────────────────────────────────┼────────────────────┘
                                         │ HTTP POST /counter
                                         ▼
┌─────────────────────────────────────────────────────────────┐
│                        Backend                               │
│  ┌─────────────────┐    ┌──────────────────────────────┐    │
│  │  Tutorial API   │───▶│  Workflow Manager            │    │
│  │  /counter       │    │  - Get node by index         │    │
│  └─────────────────┘    │  - Update node value         │    │
│                         └──────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

---

## Part 1: Backend Schema (`tutorial_schema.py`)

The schema file defines the node's structure using Pydantic models and decorators.

### Key Decorators

#### `@node_info`
Defines the node's appearance in the palette and canvas:

```python
@node_info(
    title       = "Counter",           # Display name
    description = "A simple counter",  # Tooltip text
    icon        = "#",                 # Icon character
    section     = "Tutorial",          # Palette group
    visible     = True                 # Show in palette
)
```

#### `@node_button`
Adds interactive buttons to the node:

```python
@node_button(
    id       = "increment",  # Used in event handling
    label    = "+",          # Button text
    icon     = "+",          # Icon (if supported)
    position = "bottom"      # Where to show button
)
```

### Field Roles

Fields are annotated with `FieldRole` to define their behavior:

| Role | Purpose | Node Position |
|------|---------|---------------|
| `FieldRole.CONSTANT` | Fixed value, not a slot | Hidden |
| `FieldRole.INPUT` | Receives data from other nodes | Left side |
| `FieldRole.OUTPUT` | Sends data to other nodes | Right side |
| `FieldRole.PROPERTY` | Editable in properties panel | Panel only |

### Example

```python
class Counter(InteractiveType):
    # Hidden constant - identifies this node type
    type: Annotated[Literal["counter"], FieldRole.CONSTANT] = "counter"

    # Output slot - other nodes can read this value
    value: Annotated[int, FieldRole.OUTPUT] = 0

    # Input slot - can receive step from other nodes
    step: Annotated[int, FieldRole.INPUT] = 1
```

---

## Part 2: Backend API (`tutorial_api.py`)

The API file creates endpoints that handle node actions.

### Request Model

Define what the frontend can send:

```python
class CounterRequest(BaseModel):
    node_index: int       # Which node to modify
    action: str           # What to do
    step: Optional[int]   # Optional override
```

### Endpoint Pattern

```python
@app.post("/counter")
async def counter_action(request: CounterRequest):
    # 1. Get the workflow
    impl = await manager.impl()
    workflow = impl["workflow"]

    # 2. Validate and get the node
    node = workflow.nodes[request.node_index]

    # 3. Perform the action
    if request.action == 'increment':
        node.value += step

    # 4. Return result
    return {"status": "success", "new_value": node.value}
```

### Integration

Add to `api.py` inside `setup_api()`:

```python
from tutorial_api import setup_tutorial_api
setup_tutorial_api(app, manager)
```

---

## Part 3: Frontend Extension (`schemagraph-tutorial-ext.js`)

The extension handles user interactions and communicates with the backend.

### Extension Structure

```javascript
class TutorialExtension extends SchemaGraphExtension {
    constructor(app) {
        super(app);
        // Initialize extension state
    }

    _registerNodeTypes() {
        // Register custom node types (if any)
    }

    _setupEventListeners() {
        // Listen for node events
    }

    _extendAPI() {
        // Add methods to schemaGraph.api
    }

    _injectStyles() {
        // Add custom CSS
    }
}
```

### Event Handling

Listen for button clicks on Counter nodes:

```javascript
_setupEventListeners() {
    this.on('node:buttonClick', (e) => {
        const { node, buttonId } = e;

        if (this._isCounterNode(node)) {
            this._handleCounterButton(node, buttonId);
        }
    });
}
```

### API Calls

Make requests to the backend:

```javascript
async _counterAction(node, action) {
    const response = await fetch('/counter', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            node_index: this._getNodeIndex(node),
            action: action
        })
    });

    return await response.json();
}
```

### Update Node Values

After API success, update the display:

```javascript
if (result.status === 'success') {
    this._setNodeValue(node, 'value', result.new_value);
}
```

### Registration

Register the extension:

```javascript
extensionRegistry.register('tutorial', TutorialExtension);
```

---

## Part 4: Integration

### 1. Add Node to Schema

In `schema.py`, add your node class directly (not as an import) so it's transmitted to the frontend:

```python
@node_button(id="reset", label="Reset", icon="0", position="bottom")
@node_button(id="decrement", label="-", icon="-", position="bottom")
@node_button(id="increment", label="+", icon="+", position="bottom")
@node_info(title="Counter", description="...", icon="#", section="Tutorial", visible=True)
class Counter(InteractiveType):
    type  : Annotated[Literal["counter"], FieldRole.CONSTANT] = "counter"
    value : Annotated[int               , FieldRole.OUTPUT  ] = 0
    step  : Annotated[int               , FieldRole.INPUT   ] = 1
```

> **Important**: Node classes must be defined in `schema.py` (not imported from other files) to be included in the schema export sent to the frontend.

### 2. Setup API

In `api.py`, inside `setup_api()`:

```python
from tutorial_api import setup_tutorial_api
setup_tutorial_api(app, manager)
```

### 3. Load Extension

In your HTML file, add:

```html
<script src="/schemagraph/schemagraph-tutorial-ext.js"></script>
```

### 4. Section Color (Optional)

In `numel-workflow-ui.js`, add to section colors:

```javascript
schemaGraph.api.schemaTypes.setSectionColors({
    // ... existing colors ...
    'Tutorial': '#e67e22'  // Orange for tutorial nodes
});
```

---

## Available Events

Your extension can listen to these events:

| Event | Data | Description |
|-------|------|-------------|
| `node:buttonClick` | `{node, buttonId, button}` | Button clicked on node |
| `node:valueChanged` | `{node, field, value}` | Node property changed |
| `node:created` | `{node, nodeId}` | New node added |
| `node:removed` | `{nodeId}` | Node deleted |
| `workflow:loaded` | `{workflow}` | Workflow opened |
| `schema:registered` | `{schemaName}` | Schema loaded |

---

## Best Practices

1. **Validate on backend**: Always validate node type and index server-side
2. **Handle errors gracefully**: Show user-friendly error messages
3. **Update UI after API calls**: Don't assume success, update after confirmation
4. **Use node properties**: Store runtime values in `node.properties`
5. **Clean up on destroy**: Remove event listeners when extension is destroyed

---

## Extending Further

### Custom Rendering

To draw custom content on the node:

```javascript
// In extension constructor
this.app.registerNodeRenderer('Counter', (node, ctx, colors) => {
    // Custom canvas drawing
    ctx.fillStyle = '#fff';
    ctx.font = '24px monospace';
    ctx.fillText(node.value, node.x + 50, node.y + 60);
});
```

### Persistent State

To save/load extension state:

```javascript
_extendAPI() {
    this.app.api.tutorial = {
        saveState: () => localStorage.setItem('tutorial', JSON.stringify(this.state)),
        loadState: () => this.state = JSON.parse(localStorage.getItem('tutorial') || '{}')
    };
}
```

### WebSocket Updates

For real-time updates, connect to the event WebSocket:

```javascript
const ws = new WebSocket('ws://localhost:8000/events');
ws.onmessage = (e) => {
    const event = JSON.parse(e.data);
    if (event.type === 'counter:updated') {
        this._refreshCounterNode(event.nodeId);
    }
};
```

---

## File Summary

| File | Lines | Purpose |
|------|-------|---------|
| `app/schema.py` | +20 | Counter class added at the end |
| `app/tutorial_schema.py` | ~70 | Reference file showing the pattern |
| `app/tutorial_api.py` | ~120 | /counter API endpoint |
| `web/schemagraph/schemagraph-tutorial-ext.js` | ~280 | Frontend extension |
| `docs/tutorial-extension.md` | This file | Documentation |
