# SchemaGraph Library Structure

This document describes how the SchemaGraph library has been organized into multiple files for better maintainability and selective inclusion.

## Overview

The original monolithic `schemagraph.js` (6666 lines) has been split into **7 JavaScript modules** and **1 combined CSS file**. All files are located in the `lib/` directory.

## File Structure

```
lib/
├── schemagraph-core.js         # Core classes and enums
├── schemagraph-workflow.js     # Workflow node system
├── schemagraph-graph.js        # SchemaGraph class
├── schemagraph-extensions.js   # Extension system
├── schemagraph-controllers.js  # Input controllers
├── schemagraph-drawing.js      # Drawing style manager
├── schemagraph-app.js          # Main application class
├── schemagraph-bundle.js       # Global integration file
├── schemagraph.css             # Combined stylesheet
├── schemagraph-demo.html       # Demo HTML file
└── SCHEMAGRAPH-LIBRARY-STRUCTURE.md  # This file
```

## Module Dependencies

The modules must be loaded in the following order:

```
1. schemagraph-core.js       (no dependencies)
2. schemagraph-workflow.js   (depends on core)
3. schemagraph-graph.js      (depends on core, workflow)
4. schemagraph-extensions.js (depends on core)
5. schemagraph-controllers.js (depends on core)
6. schemagraph-drawing.js    (no dependencies)
7. schemagraph-app.js        (depends on all above)
8. schemagraph-bundle.js     (optional, provides namespace)
```

## Module Contents

### 1. schemagraph-core.js (~350 lines)

Foundation classes and enums:

- **Enums:**
  - `FieldRole` - Field role types (INPUT, OUTPUT, PROPERTY, etc.)
  - `DataExportMode` - Export modes (FULL, COMPACT, MINIMAL)
  - `GraphEvents` - Event type constants
  - `DecoratorType` - Node decorator types (BUTTON, DROPZONE, CHAT, INFO)
  - `DropZoneArea` - Drop zone area types (FULL, CONTENT, HEADER, FOOTER)

- **Classes:**
  - `EventBus` - Event emission and subscription system
  - `Node` - Base node class
  - `Link` - Link between nodes
  - `Graph` - Base graph class with serialization

### 2. schemagraph-workflow.js (~450 lines)

Workflow-specific node system:

- `WorkflowNode` - Extended node class for workflows
- `WorkflowSchemaParser` - Parses Python schema files
- `WorkflowNodeFactory` - Creates nodes from schemas
- `WorkflowImporter` - Imports workflow configurations
- `WorkflowExporter` - Exports workflow configurations

### 3. schemagraph-graph.js (~150 lines)

Main graph class:

- `SchemaGraph` - Extends `Graph` with schema management
  - Node type registration
  - Schema-aware node creation
  - Multi-schema support

### 4. schemagraph-extensions.js (~380 lines)

Extension and plugin system:

- `ExtensionRegistry` - Manages extension registration
- `SchemaGraphExtension` - Base class for extensions
- `DrawUtils` - Drawing utility functions
- `NodeDecoratorParser` - Parses Python decorator syntax
- `AnalyticsService` - Usage analytics tracking
- `extensionRegistry` - Global registry instance

### 5. schemagraph-controllers.js (~180 lines)

Input handling controllers:

- `MouseTouchController` - Mouse and touch events
- `KeyboardController` - Keyboard events
- `VoiceController` - Web Speech API integration

### 6. schemagraph-drawing.js (~170 lines)

Visual style management:

- `DrawingStyleManager` - Manages drawing styles
  - Built-in styles: default, minimal, blueprint, neon, organic, wireframe
  - Custom style support
  - Style persistence

### 7. schemagraph-app.js (~2700 lines)

Main application class:

- `SchemaGraphApp` - Complete graph editor application
  - Canvas rendering
  - Node and link management
  - Event handling
  - Import/Export functionality
  - Theme support
  - Layout algorithms
  - Button stacks and drop zones
  - Completeness checking
  - Public API

### 8. schemagraph-bundle.js (~250 lines)

Global integration and namespace:

- `SchemaGraph` namespace with all classes
- Factory methods (`create`, `createGraph`, etc.)
- Dependency checking
- Version information
- `SG` shorthand alias

## CSS Structure

The `schemagraph.css` file combines three original CSS files:

1. **Themes** - CSS variables for dark, light, and ocean themes
2. **Canvas** - Canvas container, context menu, toolbar, tooltips
3. **UI** - Application chrome, dialogs, analytics panel, controls

## Usage

### Full Application (All Features)

```html
<!DOCTYPE html>
<html>
<head>
    <link rel="stylesheet" href="lib/schemagraph.css">
</head>
<body>
    <canvas id="canvas"></canvas>

    <!-- Load in order -->
    <script src="lib/schemagraph-core.js"></script>
    <script src="lib/schemagraph-workflow.js"></script>
    <script src="lib/schemagraph-graph.js"></script>
    <script src="lib/schemagraph-extensions.js"></script>
    <script src="lib/schemagraph-controllers.js"></script>
    <script src="lib/schemagraph-drawing.js"></script>
    <script src="lib/schemagraph-app.js"></script>
    <script src="lib/schemagraph-bundle.js"></script>

    <script>
        const app = SchemaGraph.create('#canvas');
    </script>
</body>
</html>
```

### Minimal Setup (Core Only)

If you only need the graph data structure without UI:

```html
<script src="lib/schemagraph-core.js"></script>
<script src="lib/schemagraph-graph.js"></script>

<script>
    const graph = new SchemaGraph();
    graph.registerNodeType('myNode', { title: 'My Node', ... });
    const node = graph.createNode('myNode', 0, 0);
</script>
```

### With Workflow Support

For workflow parsing and import/export:

```html
<script src="lib/schemagraph-core.js"></script>
<script src="lib/schemagraph-workflow.js"></script>
<script src="lib/schemagraph-graph.js"></script>

<script>
    const parser = new WorkflowSchemaParser();
    const schema = parser.parse(pythonCode);
</script>
```

## Global Exports

All classes are exported to the `window` object for standard JavaScript compatibility:

```javascript
// Available globally after loading scripts:
window.EventBus
window.Node
window.Link
window.Graph
window.SchemaGraph
window.WorkflowNode
window.WorkflowSchemaParser
window.SchemaGraphApp
// ... and more

// Or use the namespace (after loading bundle):
SchemaGraph.App
SchemaGraph.EventBus
SchemaGraph.create(canvas)
```

## Module Exports

For Node.js/CommonJS environments, each file exports its classes:

```javascript
// In Node.js:
const { EventBus, Node, Link, Graph } = require('./schemagraph-core.js');
const { SchemaGraph } = require('./schemagraph-graph.js');
const { SchemaGraphApp } = require('./schemagraph-app.js');
```

## Selective Inclusion Guide

| Use Case | Required Files |
|----------|---------------|
| Data structure only | core |
| Graph with schemas | core, graph |
| Workflow parsing | core, workflow, graph |
| Full editor (no extensions) | core, workflow, graph, controllers, drawing, app |
| Full application | All files |

## API Reference

### SchemaGraph Namespace (from bundle)

```javascript
// Create application
const app = SchemaGraph.create('#canvas', options);

// Create graph only
const graph = SchemaGraph.createGraph();

// Parse Python schema
const schema = SchemaGraph.parseSchema(pythonCode);

// Register extension
SchemaGraph.registerExtension('myExt', MyExtensionClass);

// Get info
SchemaGraph.logInfo();
```

### SchemaGraphApp API

```javascript
const app = new SchemaGraphApp(canvas, options);

// Access via app.api:
app.api.createNode(type, x, y, data);
app.api.createLink(source, sourceSlot, target, targetSlot);
app.api.removeNode(node);
app.api.removeLink(link);
app.api.selectNode(node);
app.api.clearSelection();
app.api.exportGraph();
app.api.importGraph(data);
app.api.setTheme('dark' | 'light' | 'ocean');
app.api.applyLayout('hierarchical' | 'force' | 'grid' | 'circular');
app.api.lock();
app.api.unlock();
app.api.draw();
```

## Migration from Original File

If migrating from the original `schemagraph.js`:

1. Replace the single script tag with multiple script tags (in order)
2. Replace individual CSS files with `schemagraph.css`
3. Code using global classes continues to work unchanged
4. Optionally use `SchemaGraph.create()` instead of `new SchemaGraphApp()`

## Notes

- All files use standard JavaScript (no ES6 modules required)
- Optional `module.exports` for Node.js compatibility
- All functionality is preserved from the original file
- Themes: dark (default), light, ocean
- Drawing styles: default, minimal, blueprint, neon, organic, wireframe
