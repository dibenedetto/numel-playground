// ========================================================================
// SCHEMAGRAPH WORKFLOW EXTENSION
// Adds support for workflow-style schemas with FieldRole annotations
// and nodes/edges JSON format
// 
// Usage: Add this file after schemagraph.js
// ========================================================================

/**
 * FieldRole enum - matches Python schema annotations
 */
const FieldRole = Object.freeze({
  CONSTANT: 'constant',
  INPUT: 'input',
  OUTPUT: 'output',
  MULTI_INPUT: 'multi_input',
  MULTI_OUTPUT: 'multi_output'
});

/**
 * WorkflowNode - Extended node class for workflow schemas
 */
class WorkflowNode extends Node {
  constructor(title, config = {}) {
    super(title);
    this.isWorkflowNode = true;
    this.schemaName = config.schemaName || '';
    this.modelName = config.modelName || '';
    this.workflowType = config.workflowType || '';
    this.fieldRoles = config.fieldRoles || {};
    this.constantFields = config.constantFields || {};
    this.multiOutputs = {};
    this.workflowIndex = null;
    this.extra = {};
  }

  /**
   * Get slot index by field name for inputs
   */
  getInputSlotByName(name) {
    for (let i = 0; i < this.inputs.length; i++) {
      if (this.inputs[i].name === name) return i;
    }
    // Check for dotted notation (e.g., "tools.t1")
    const dotIdx = name.indexOf('.');
    if (dotIdx !== -1) {
      const baseName = name.substring(0, dotIdx);
      for (let i = 0; i < this.inputs.length; i++) {
        if (this.inputs[i].name === baseName) return i;
      }
    }
    return -1;
  }

  /**
   * Get slot index by field name for outputs
   */
  getOutputSlotByName(name) {
    for (let i = 0; i < this.outputs.length; i++) {
      if (this.outputs[i].name === name) return i;
    }
    // Check for dotted notation (e.g., "cases.c1")
    const dotIdx = name.indexOf('.');
    if (dotIdx !== -1) {
      const baseName = name.substring(0, dotIdx);
      for (let i = 0; i < this.outputs.length; i++) {
        if (this.outputs[i].name === baseName) return i;
      }
    }
    return -1;
  }

  /**
   * Execute node and build output data
   */
  onExecute() {
    const data = { ...this.constantFields };

    for (let i = 0; i < this.inputs.length; i++) {
      const input = this.inputs[i];
      const fieldName = input.name;
      const role = this.fieldRoles[fieldName];

      if (this.multiInputs && this.multiInputs[i]) {
        // Collect multi-input values with their keys
        const mi = this.multiInputs[i];
        if (mi.keys && Object.keys(mi.keys).length > 0) {
          const values = {};
          for (const key in mi.keys) {
            const linkId = mi.keys[key];
            const link = this.graph.links[linkId];
            if (link) {
              const sourceNode = this.graph.getNodeById(link.origin_id);
              if (sourceNode && sourceNode.outputs[link.origin_slot]) {
                values[key] = sourceNode.outputs[link.origin_slot].value;
              }
            }
          }
          if (Object.keys(values).length > 0) {
            data[fieldName] = values;
          }
        } else if (mi.links && mi.links.length > 0) {
          // Unnamed multi-inputs (array)
          const values = [];
          for (const linkId of mi.links) {
            const link = this.graph.links[linkId];
            if (link) {
              const sourceNode = this.graph.getNodeById(link.origin_id);
              if (sourceNode && sourceNode.outputs[link.origin_slot]) {
                values.push(sourceNode.outputs[link.origin_slot].value);
              }
            }
          }
          if (values.length > 0) {
            data[fieldName] = values;
          }
        }
      } else {
        // Regular input
        const connectedVal = this.getInputData(i);
        if (connectedVal !== null && connectedVal !== undefined) {
          data[fieldName] = connectedVal;
        } else if (this.nativeInputs && this.nativeInputs[i] !== undefined) {
          const nativeInput = this.nativeInputs[i];
          const val = nativeInput.value;
          const isEmpty = val === null || val === undefined || val === '';
          
          if (!isEmpty || nativeInput.type === 'bool') {
            data[fieldName] = this._convertNativeValue(val, nativeInput.type);
          }
        }
      }
    }

    // Set output data for all outputs
    for (let i = 0; i < this.outputs.length; i++) {
      this.setOutputData(i, data);
    }
  }

  _convertNativeValue(val, type) {
    if (val === null || val === undefined) return val;
    switch (type) {
      case 'int': return parseInt(val) || 0;
      case 'float': return parseFloat(val) || 0.0;
      case 'bool': return val === true || val === 'true';
      case 'dict':
      case 'list':
        if (typeof val === 'string') {
          try { return JSON.parse(val); } catch (e) { return type === 'dict' ? {} : []; }
        }
        return val;
      default: return val;
    }
  }
}

/**
 * WorkflowSchemaParser - Parses Python schemas with FieldRole annotations
 */
class WorkflowSchemaParser {
  constructor() {
    this.models = {};
    this.fieldRoles = {};
    this.defaults = {};
  }

  /**
   * Parse schema code and extract models with field roles
   */
  parse(code) {
    this.models = {};
    this.fieldRoles = {};
    this.defaults = {};

    const lines = code.split('\n');
    let currentModel = null;
    let currentFields = [];
    let currentRoles = {};
    let currentDefaults = {};
    let inPropertyDef = false;

    for (let i = 0; i < lines.length; i++) {
      const line = lines[i];
      const trimmed = line.trim();

      // Skip empty lines and comments
      if (!trimmed || trimmed.startsWith('#')) continue;

      // Match class definition
      const classMatch = trimmed.match(/^class\s+(\w+)\s*\(/);
      if (classMatch) {
        this._saveCurrentModel(currentModel, currentFields, currentRoles, currentDefaults);
        currentModel = classMatch[1];
        currentFields = [];
        currentRoles = {};
        currentDefaults = {};
        inPropertyDef = false;
        continue;
      }

      // Match @property decorator
      if (trimmed === '@property') {
        inPropertyDef = true;
        continue;
      }

      // Match property definition with FieldRole annotation
      if (inPropertyDef && currentModel) {
        const propMatch = trimmed.match(/def\s+(\w+)\s*\([^)]*\)\s*->\s*Annotated\[([^,\]]+),\s*FieldRole\.(\w+)\]/);
        if (propMatch) {
          const [, propName, propType, role] = propMatch;
          currentFields.push({
            name: propName,
            type: this._parseType(propType.trim()),
            rawType: propType.trim(),
            isProperty: true
          });
          currentRoles[propName] = role.toLowerCase();
        }
        inPropertyDef = false;
        continue;
      }

      // Match field with Annotated type and FieldRole
      if (currentModel && trimmed.includes(':') && !trimmed.startsWith('def ')) {
        const fieldData = this._parseFieldLine(trimmed);
        if (fieldData) {
          currentFields.push({
            name: fieldData.name,
            type: this._parseType(fieldData.type),
            rawType: fieldData.type
          });
          currentRoles[fieldData.name] = fieldData.role;
          if (fieldData.default !== undefined) {
            currentDefaults[fieldData.name] = fieldData.default;
          }
        }
      }
    }

    // Save last model
    this._saveCurrentModel(currentModel, currentFields, currentRoles, currentDefaults);

    return {
      models: this.models,
      fieldRoles: this.fieldRoles,
      defaults: this.defaults
    };
  }

  _saveCurrentModel(name, fields, roles, defaults) {
    if (name && fields.length > 0) {
      this.models[name] = fields;
      this.fieldRoles[name] = roles;
      this.defaults[name] = defaults;
    }
  }

  _parseFieldLine(line) {
    // Pattern: field_name : Annotated[Type, FieldRole.ROLE] = default
    const annotatedMatch = line.match(
      /^(\w+)\s*:\s*Annotated\[\s*([^,\]]+(?:\[[^\]]*\])?)\s*,\s*FieldRole\.(\w+)\s*\](?:\s*=\s*(.+))?$/
    );

    if (annotatedMatch) {
      const [, name, type, role, defaultVal] = annotatedMatch;
      return {
        name,
        type: type.trim(),
        role: role.toLowerCase(),
        default: defaultVal ? this._parseDefaultValue(defaultVal.trim()) : undefined
      };
    }

    // Simple field without Annotated (treat as INPUT)
    const simpleMatch = line.match(/^(\w+)\s*:\s*([^=]+?)(?:\s*=\s*(.+))?$/);
    if (simpleMatch && !simpleMatch[1].startsWith('_')) {
      const [, name, type, defaultVal] = simpleMatch;
      return {
        name,
        type: type.trim(),
        role: FieldRole.INPUT,
        default: defaultVal ? this._parseDefaultValue(defaultVal.trim()) : undefined
      };
    }

    return null;
  }

  _parseDefaultValue(valStr) {
    if (!valStr) return undefined;
    valStr = valStr.trim();

    if (valStr === 'None') return null;
    if (valStr === 'True') return true;
    if (valStr === 'False') return false;

    // String literals
    if ((valStr.startsWith('"') && valStr.endsWith('"')) ||
        (valStr.startsWith("'") && valStr.endsWith("'"))) {
      return valStr.slice(1, -1);
    }

    // Numbers
    const num = parseFloat(valStr);
    if (!isNaN(num) && valStr.match(/^-?\d+\.?\d*$/)) return num;

    // Empty collections
    if (valStr === '[]') return [];
    if (valStr === '{}') return {};

    // Message type: Message("type", "value")
    const msgMatch = valStr.match(/Message\s*\(\s*["']([^"']*)["']\s*,\s*["']([^"']*)["']\s*\)/);
    if (msgMatch) return msgMatch[2];

    // Reference to constant
    if (valStr.match(/^[A-Z_]+$/)) return { _ref: valStr };

    return valStr;
  }

  _parseType(typeStr) {
    typeStr = typeStr.trim();

    if (typeStr.startsWith('Optional[')) {
      const inner = this._extractBracketContent(typeStr, 9);
      return { kind: 'optional', inner: this._parseType(inner) };
    }
    if (typeStr.startsWith('List[')) {
      const inner = this._extractBracketContent(typeStr, 5);
      return { kind: 'list', inner: this._parseType(inner) };
    }
    if (typeStr.startsWith('Dict[')) {
      const inner = this._extractBracketContent(typeStr, 5);
      return { kind: 'dict', inner };
    }
    if (typeStr.startsWith('Message[')) {
      const inner = this._extractBracketContent(typeStr, 8);
      return { kind: 'message', inner: this._parseType(inner) };
    }

    return { kind: 'basic', name: typeStr };
  }

  _extractBracketContent(str, startIdx) {
    let depth = 1;
    let i = startIdx;
    while (i < str.length && depth > 0) {
      if (str[i] === '[') depth++;
      if (str[i] === ']') depth--;
      if (depth === 0) break;
      i++;
    }
    return str.substring(startIdx, i);
  }
}

/**
 * WorkflowNodeGenerator - Generates node types from parsed schema
 */
class WorkflowNodeGenerator {
  constructor(graph) {
    this.graph = graph;
  }

  /**
   * Generate node types for all models in parsed schema
   */
  generate(schemaName, parsed) {
    const { models, fieldRoles, defaults } = parsed;

    for (const modelName in models) {
      if (!models.hasOwnProperty(modelName)) continue;

      const fields = models[modelName];
      const roles = fieldRoles[modelName] || {};
      const modelDefaults = defaults[modelName] || {};

      this._createNodeType(schemaName, modelName, fields, roles, modelDefaults);
    }
  }

  _createNodeType(schemaName, modelName, fields, roles, modelDefaults) {
    const graph = this.graph;
    const fullTypeName = `${schemaName}.${modelName}`;

    // Determine the workflow type from constant 'type' field
    let workflowType = modelName.toLowerCase();
    for (const field of fields) {
      if (field.name === 'type' && roles[field.name] === FieldRole.CONSTANT) {
        workflowType = modelDefaults[field.name] || workflowType;
        break;
      }
    }

    // Create node class dynamically
    const nodeConfig = {
      schemaName,
      modelName,
      workflowType,
      fieldRoles: { ...roles },
      constantFields: {}
    };

    // Separate fields by role
    const inputFields = [];
    const outputFields = [];
    const multiInputFields = [];
    const multiOutputFields = [];

    for (const field of fields) {
      const role = roles[field.name] || FieldRole.INPUT;
      const defaultVal = modelDefaults[field.name];

      switch (role) {
        case FieldRole.CONSTANT:
          nodeConfig.constantFields[field.name] = defaultVal !== undefined ? defaultVal : field.name;
          break;
        case FieldRole.INPUT:
          inputFields.push({ ...field, default: defaultVal });
          break;
        case FieldRole.OUTPUT:
          outputFields.push({ ...field, default: defaultVal });
          break;
        case FieldRole.MULTI_INPUT:
          multiInputFields.push({ ...field, default: defaultVal });
          break;
        case FieldRole.MULTI_OUTPUT:
          multiOutputFields.push({ ...field, default: defaultVal });
          break;
      }
    }

    // Create the node class
    const GeneratedWorkflowNode = class extends WorkflowNode {
      constructor() {
        super(`${schemaName}.${modelName}`, nodeConfig);

        let inputIdx = 0;

        // Add regular inputs
        for (const field of inputFields) {
          this.addInput(field.name, field.rawType);
          
          if (this._isNativeType(field.rawType)) {
            this.nativeInputs[inputIdx] = {
              type: this._getNativeBaseType(field.rawType),
              value: field.default !== undefined ? field.default : this._getDefaultForType(field.rawType),
              optional: field.rawType.includes('Optional')
            };
          }
          inputIdx++;
        }

        // Add multi-inputs
        for (const field of multiInputFields) {
          this.addInput(field.name, field.rawType);
          this.multiInputs[inputIdx] = {
            type: field.rawType,
            links: [],
            keys: {}
          };
          inputIdx++;
        }

        // Add regular outputs
        let outputIdx = 0;
        for (const field of outputFields) {
          this.addOutput(field.name, field.rawType);
          outputIdx++;
        }

        // Add multi-outputs
        for (const field of multiOutputFields) {
          this.addOutput(field.name, field.rawType);
          this.multiOutputs[outputIdx] = {
            type: field.rawType,
            links: [],
            keys: {}
          };
          outputIdx++;
        }

        // Calculate node size
        const maxSlots = Math.max(this.inputs.length, this.outputs.length, 1);
        this.size = [220, Math.max(80, 35 + maxSlots * 25)];
      }

      _isNativeType(typeStr) {
        if (!typeStr) return false;
        const natives = ['str', 'int', 'bool', 'float', 'string', 'integer', 'Any'];
        const base = typeStr.replace(/Optional\[|\]/g, '').split('[')[0].trim();
        
        // Check Message types
        if (typeStr.includes('Message')) {
          const msgMatch = typeStr.match(/Message\w*$/);
          if (msgMatch) return true;
        }
        
        return natives.includes(base);
      }

      _getNativeBaseType(typeStr) {
        if (typeStr.includes('int') || typeStr.includes('Int')) return 'int';
        if (typeStr.includes('bool') || typeStr.includes('Bool')) return 'bool';
        if (typeStr.includes('float') || typeStr.includes('Float')) return 'float';
        if (typeStr.includes('Dict') || typeStr.includes('dict')) return 'dict';
        if (typeStr.includes('List') || typeStr.includes('list')) return 'list';
        return 'str';
      }

      _getDefaultForType(typeStr) {
        const base = this._getNativeBaseType(typeStr);
        switch (base) {
          case 'int': return 0;
          case 'bool': return false;
          case 'float': return 0.0;
          case 'dict': return '{}';
          case 'list': return '[]';
          default: return '';
        }
      }
    };

    // Register the node type
    graph.nodeTypes[fullTypeName] = GeneratedWorkflowNode;
    console.log(`  ✓ Registered workflow node type: ${fullTypeName}`);
  }
}

/**
 * WorkflowImporter - Imports workflow JSON with nodes/edges format
 */
class WorkflowImporter {
  constructor(graph, eventBus) {
    this.graph = graph;
    this.eventBus = eventBus;
  }

  /**
   * Import workflow from JSON data
   */
  import(workflowData, schemaName, camera = null) {
    console.log('=== WORKFLOW IMPORT STARTED ===');
    console.log('Schema:', schemaName);
    console.log('Nodes:', workflowData.nodes?.length || 0);
    console.log('Edges:', workflowData.edges?.length || 0);

    if (!workflowData || !workflowData.nodes) {
      throw new Error('Invalid workflow data: missing nodes array');
    }

    // Clear current graph
    this.graph.nodes = [];
    this.graph.links = {};
    this.graph._nodes_by_id = {};
    this.graph.last_link_id = 0;

    // Calculate layout positions
    const positions = this._calculateLayout(workflowData);

    // Create nodes
    const createdNodes = [];
    for (let i = 0; i < workflowData.nodes.length; i++) {
      const nodeData = workflowData.nodes[i];
      const node = this._createNode(nodeData, i, schemaName, positions[i]);
      createdNodes.push(node);
      
      if (node) {
        console.log(`  ✓ Node ${i}: ${node.title} (${nodeData.type})`);
      } else {
        console.warn(`  ✗ Node ${i}: Failed to create (${nodeData.type})`);
      }
    }

    // Create edges
    if (workflowData.edges) {
      for (const edgeData of workflowData.edges) {
        this._createEdge(edgeData, createdNodes);
      }
    }

    // Execute all nodes to propagate data
    for (const node of this.graph.nodes) {
      if (node) node.onExecute();
    }

    console.log('=== WORKFLOW IMPORT COMPLETE ===');
    console.log(`Created ${this.graph.nodes.length} nodes, ${Object.keys(this.graph.links).length} links`);

    this.eventBus.emit('workflow:imported', { 
      nodeCount: this.graph.nodes.length,
      linkCount: Object.keys(this.graph.links).length
    });

    return true;
  }

  _createNode(nodeData, index, schemaName, position) {
    const nodeType = nodeData.type;
    const fullType = this._resolveNodeType(nodeType, schemaName);

    if (!fullType || !this.graph.nodeTypes[fullType]) {
      console.error(`Node type not found: ${nodeType}`);
      return null;
    }

    try {
      const node = this.graph.createNode(fullType);
      node.pos = [position.x, position.y];
      node.workflowIndex = index;

      // Apply extra properties
      if (nodeData.extra) {
        node.extra = { ...nodeData.extra };
        if (nodeData.extra.title || nodeData.extra.name) {
          node.title = nodeData.extra.title || nodeData.extra.name;
        }
        if (nodeData.extra.color) {
          node.color = nodeData.extra.color;
        }
      }

      // Populate field values
      this._populateNodeFields(node, nodeData);

      return node;
    } catch (e) {
      console.error(`Failed to create node ${index}:`, e);
      return null;
    }
  }

  _resolveNodeType(nodeType, schemaName) {
    // Try direct match
    let fullType = `${schemaName}.${this._snakeToPascal(nodeType)}`;
    if (this.graph.nodeTypes[fullType]) return fullType;

    // Try without _config/_node suffix
    const baseName = nodeType.replace(/_config$|_node$/, '');
    fullType = `${schemaName}.${this._snakeToPascal(baseName)}Config`;
    if (this.graph.nodeTypes[fullType]) return fullType;

    fullType = `${schemaName}.${this._snakeToPascal(baseName)}Node`;
    if (this.graph.nodeTypes[fullType]) return fullType;

    // Try exact pascal case
    fullType = `${schemaName}.${this._snakeToPascal(nodeType)}`;
    if (this.graph.nodeTypes[fullType]) return fullType;

    return null;
  }

  _snakeToPascal(str) {
    return str.split('_')
      .map(part => part.charAt(0).toUpperCase() + part.slice(1).toLowerCase())
      .join('');
  }

  _populateNodeFields(node, nodeData) {
    for (let i = 0; i < node.inputs.length; i++) {
      const input = node.inputs[i];
      const fieldName = input.name;
      const value = nodeData[fieldName];

      if (value === undefined || value === null) continue;

      if (node.nativeInputs && node.nativeInputs[i] !== undefined) {
        if (typeof value === 'object') {
          node.nativeInputs[i].value = JSON.stringify(value);
        } else {
          node.nativeInputs[i].value = value;
        }
      }
    }
  }

  _createEdge(edgeData, createdNodes) {
    const { source, target, source_slot, target_slot, extra } = edgeData;

    const sourceNode = createdNodes[source];
    const targetNode = createdNodes[target];

    if (!sourceNode || !targetNode) {
      console.warn(`Edge skipped: invalid node reference (${source} -> ${target})`);
      return;
    }

    // Resolve slot indices
    const sourceSlotIdx = this._resolveOutputSlot(sourceNode, source_slot);
    const targetSlotIdx = this._resolveInputSlot(targetNode, target_slot);

    if (sourceSlotIdx === -1) {
      console.warn(`Edge skipped: output slot "${source_slot}" not found on node ${source}`);
      return;
    }
    if (targetSlotIdx === -1) {
      console.warn(`Edge skipped: input slot "${target_slot}" not found on node ${target}`);
      return;
    }

    // Create the link
    const linkId = ++this.graph.last_link_id;
    const link = new Link(
      linkId,
      sourceNode.id,
      sourceSlotIdx,
      targetNode.id,
      targetSlotIdx,
      sourceNode.outputs[sourceSlotIdx]?.type || 'Any'
    );

    // Store extra info on link
    if (extra) {
      link.extra = { ...extra };
    }

    this.graph.links[linkId] = link;
    sourceNode.outputs[sourceSlotIdx].links.push(linkId);

    // Handle multi-input with key
    const slotKey = this._extractSlotKey(target_slot);
    if (targetNode.multiInputs && targetNode.multiInputs[targetSlotIdx]) {
      targetNode.multiInputs[targetSlotIdx].links.push(linkId);
      if (slotKey) {
        targetNode.multiInputs[targetSlotIdx].keys[slotKey] = linkId;
      }
    } else {
      targetNode.inputs[targetSlotIdx].link = linkId;
    }

    // Handle multi-output with key
    const sourceKey = this._extractSlotKey(source_slot);
    if (sourceNode.multiOutputs && sourceNode.multiOutputs[sourceSlotIdx]) {
      if (sourceKey) {
        if (!sourceNode.multiOutputs[sourceSlotIdx].keys[sourceKey]) {
          sourceNode.multiOutputs[sourceSlotIdx].keys[sourceKey] = [];
        }
        sourceNode.multiOutputs[sourceSlotIdx].keys[sourceKey].push(linkId);
      }
    }

    this.eventBus.emit('link:created', { linkId });
    console.log(`  ✓ Edge: ${source}:${source_slot} -> ${target}:${target_slot}`);
  }

  _resolveOutputSlot(node, slotName) {
    // Direct match
    for (let i = 0; i < node.outputs.length; i++) {
      if (node.outputs[i].name === slotName) return i;
    }
    // Dotted notation (e.g., "cases.c1")
    const baseName = slotName.split('.')[0];
    for (let i = 0; i < node.outputs.length; i++) {
      if (node.outputs[i].name === baseName) return i;
    }
    return -1;
  }

  _resolveInputSlot(node, slotName) {
    // Direct match
    for (let i = 0; i < node.inputs.length; i++) {
      if (node.inputs[i].name === slotName) return i;
    }
    // Dotted notation (e.g., "sources.a1")
    const baseName = slotName.split('.')[0];
    for (let i = 0; i < node.inputs.length; i++) {
      if (node.inputs[i].name === baseName) return i;
    }
    return -1;
  }

  _extractSlotKey(slotName) {
    const dotIdx = slotName.indexOf('.');
    return dotIdx !== -1 ? slotName.substring(dotIdx + 1) : null;
  }

  _calculateLayout(workflowData) {
    const positions = [];
    const nodeCount = workflowData.nodes.length;

    // Simple grid layout, can be improved with DAG layout
    const cols = Math.ceil(Math.sqrt(nodeCount));
    const spacingX = 280;
    const spacingY = 180;

    for (let i = 0; i < nodeCount; i++) {
      const col = i % cols;
      const row = Math.floor(i / cols);
      positions.push({
        x: 100 + col * spacingX,
        y: 100 + row * spacingY
      });
    }

    return positions;
  }
}

/**
 * WorkflowExporter - Exports graph to workflow JSON format
 */
class WorkflowExporter {
  constructor(graph) {
    this.graph = graph;
  }

  /**
   * Export graph to workflow JSON format
   */
  export(schemaName, workflowInfo = {}) {
    console.log('=== WORKFLOW EXPORT STARTED ===');

    const workflow = {
      type: 'workflow',
      info: workflowInfo.info || null,
      options: workflowInfo.options || null,
      nodes: [],
      edges: []
    };

    // Build node index map
    const nodeToIndex = new Map();
    const workflowNodes = this.graph.nodes.filter(n => 
      n.schemaName === schemaName || n.isWorkflowNode
    );

    // Sort by workflowIndex if available, otherwise by creation order
    workflowNodes.sort((a, b) => {
      if (a.workflowIndex !== undefined && b.workflowIndex !== undefined) {
        return a.workflowIndex - b.workflowIndex;
      }
      return 0;
    });

    // Export nodes
    for (let i = 0; i < workflowNodes.length; i++) {
      const node = workflowNodes[i];
      nodeToIndex.set(node.id, i);
      workflow.nodes.push(this._exportNode(node));
    }

    // Export edges
    for (const linkId in this.graph.links) {
      const link = this.graph.links[linkId];
      const edge = this._exportEdge(link, nodeToIndex);
      if (edge) {
        workflow.edges.push(edge);
      }
    }

    console.log('=== WORKFLOW EXPORT COMPLETE ===');
    console.log(`Exported ${workflow.nodes.length} nodes, ${workflow.edges.length} edges`);

    return workflow;
  }

  _exportNode(node) {
    const nodeData = {
      type: node.workflowType || node.constantFields?.type || node.modelName?.toLowerCase() || 'unknown'
    };

    // Add constant fields
    if (node.constantFields) {
      for (const key in node.constantFields) {
        if (key !== 'type') {
          nodeData[key] = node.constantFields[key];
        }
      }
    }

    // Add input field values
    for (let i = 0; i < node.inputs.length; i++) {
      const input = node.inputs[i];
      const fieldName = input.name;

      // Skip if it's a multi-input with connections (handled via edges)
      if (node.multiInputs && node.multiInputs[i]) {
        const mi = node.multiInputs[i];
        if (mi.links.length > 0 || Object.keys(mi.keys).length > 0) {
          // Export the keys as field names for reference
          if (Object.keys(mi.keys).length > 0) {
            nodeData[fieldName] = Object.keys(mi.keys);
          }
          continue;
        }
      }

      // Skip if it has a connection (value comes from edge)
      if (input.link) continue;

      // Export native input value
      if (node.nativeInputs && node.nativeInputs[i] !== undefined) {
        const val = node.nativeInputs[i].value;
        if (val !== null && val !== undefined && val !== '') {
          nodeData[fieldName] = this._convertExportValue(val, node.nativeInputs[i].type);
        }
      }
    }

    // Add extra properties
    if (node.extra && Object.keys(node.extra).length > 0) {
      nodeData.extra = { ...node.extra };
    } else if (node.color || node.title !== `${node.schemaName}.${node.modelName}`) {
      nodeData.extra = {};
      if (node.color) nodeData.extra.color = node.color;
      if (node.title !== `${node.schemaName}.${node.modelName}`) {
        nodeData.extra.name = node.title;
      }
    }

    return nodeData;
  }

  _exportEdge(link, nodeToIndex) {
    const sourceNode = this.graph.getNodeById(link.origin_id);
    const targetNode = this.graph.getNodeById(link.target_id);

    if (!sourceNode || !targetNode) return null;

    const sourceIdx = nodeToIndex.get(link.origin_id);
    const targetIdx = nodeToIndex.get(link.target_id);

    if (sourceIdx === undefined || targetIdx === undefined) return null;

    // Get slot names
    let sourceSlot = sourceNode.outputs[link.origin_slot]?.name || 'output';
    let targetSlot = targetNode.inputs[link.target_slot]?.name || 'input';

    // Add key suffix for multi-outputs
    if (sourceNode.multiOutputs && sourceNode.multiOutputs[link.origin_slot]) {
      const mo = sourceNode.multiOutputs[link.origin_slot];
      for (const key in mo.keys) {
        if (mo.keys[key].includes(link.id)) {
          sourceSlot = `${sourceSlot}.${key}`;
          break;
        }
      }
    }

    // Add key suffix for multi-inputs
    if (targetNode.multiInputs && targetNode.multiInputs[link.target_slot]) {
      const mi = targetNode.multiInputs[link.target_slot];
      for (const key in mi.keys) {
        if (mi.keys[key] === link.id) {
          targetSlot = `${targetSlot}.${key}`;
          break;
        }
      }
    }

    const edge = {
      source: sourceIdx,
      target: targetIdx,
      source_slot: sourceSlot,
      target_slot: targetSlot
    };

    // Add extra if present
    if (link.extra && Object.keys(link.extra).length > 0) {
      edge.extra = { ...link.extra };
    }

    return edge;
  }

  _convertExportValue(val, type) {
    if (type === 'dict' || type === 'list') {
      if (typeof val === 'string') {
        try { return JSON.parse(val); } catch (e) { return val; }
      }
    }
    return val;
  }
}

// ========================================================================
// INTEGRATION WITH SCHEMAGRAPH
// ========================================================================

/**
 * Extend SchemaGraph with workflow capabilities
 */
function extendSchemaGraphWithWorkflow(SchemaGraphClass) {
  const originalRegisterSchema = SchemaGraphClass.prototype.registerSchema;

  /**
   * Enhanced registerSchema that detects workflow schemas
   */
  SchemaGraphClass.prototype.registerSchema = function(schemaName, schemaCode, indexType = 'int', rootType = null) {
    // Check if this is a workflow schema (contains FieldRole annotations)
    if (schemaCode.includes('FieldRole.')) {
      return this.registerWorkflowSchema(schemaName, schemaCode);
    }
    // Fall back to original method
    return originalRegisterSchema.call(this, schemaName, schemaCode, indexType, rootType);
  };

  /**
   * Register a workflow schema with FieldRole annotations
   */
  SchemaGraphClass.prototype.registerWorkflowSchema = function(schemaName, schemaCode) {
    try {
      console.log('=== REGISTERING WORKFLOW SCHEMA:', schemaName, '===');

      const parser = new WorkflowSchemaParser();
      const parsed = parser.parse(schemaCode);

      console.log('Parsed models:', Object.keys(parsed.models).length);

      this.schemas[schemaName] = {
        code: schemaCode,
        parsed: parsed.models,
        isWorkflow: true,
        fieldRoles: parsed.fieldRoles,
        defaults: parsed.defaults
      };

      const generator = new WorkflowNodeGenerator(this);
      generator.generate(schemaName, parsed);

      this.enabledSchemas.add(schemaName);

      this.eventBus.emit('schema:registered', { schemaName, isWorkflow: true });
      console.log('=== WORKFLOW SCHEMA REGISTERED ===');
      return true;
    } catch (e) {
      console.error('Workflow schema registration error:', e);
      this.eventBus.emit('error', { type: 'schema:register', error: e.message });
      return false;
    }
  };

  /**
   * Import workflow JSON
   */
  SchemaGraphClass.prototype.importWorkflow = function(workflowData, schemaName) {
    const importer = new WorkflowImporter(this, this.eventBus);
    return importer.import(workflowData, schemaName);
  };

  /**
   * Export to workflow JSON format
   */
  SchemaGraphClass.prototype.exportWorkflow = function(schemaName, workflowInfo = {}) {
    const exporter = new WorkflowExporter(this);
    return exporter.export(schemaName, workflowInfo);
  };

  /**
   * Check if schema is a workflow schema
   */
  SchemaGraphClass.prototype.isWorkflowSchema = function(schemaName) {
    return this.schemas[schemaName]?.isWorkflow === true;
  };
}

/**
 * Extend SchemaGraphApp with workflow UI support
 */
function extendSchemaGraphAppWithWorkflow(SchemaGraphAppClass) {
  const originalCreateAPI = SchemaGraphAppClass.prototype._createAPI;

  SchemaGraphAppClass.prototype._createAPI = function() {
    const api = originalCreateAPI.call(this);

    // Add workflow API methods
    api.workflow = {
      /**
       * Register a workflow schema
       */
      registerSchema: (name, code) => {
        return this.graph.registerWorkflowSchema(name, code);
      },

      /**
       * Import workflow from JSON
       */
      import: (workflowData, schemaName) => {
        try {
          this.graph.importWorkflow(workflowData, schemaName);
          this.ui.update.schemaList();
          this.ui.update.nodeTypesList();
          this.draw();
          this.centerView();
          return true;
        } catch (e) {
          this.showError('Workflow import failed: ' + e.message);
          return false;
        }
      },

      /**
       * Export graph to workflow JSON
       */
      export: (schemaName, workflowInfo = {}) => {
        return this.graph.exportWorkflow(schemaName, workflowInfo);
      },

      /**
       * Download workflow as JSON file
       */
      download: (schemaName, workflowInfo = {}, filename = null) => {
        const workflow = this.graph.exportWorkflow(schemaName, workflowInfo);
        const jsonString = JSON.stringify(workflow, null, '\t');
        const blob = new Blob([jsonString], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename || `workflow-${new Date().toISOString().slice(0, 10)}.json`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
        this.eventBus.emit('workflow:exported', {});
      },

      /**
       * Check if schema is workflow type
       */
      isWorkflowSchema: (schemaName) => {
        return this.graph.isWorkflowSchema(schemaName);
      }
    };

    return api;
  };
}

// ========================================================================
// AUTO-INITIALIZATION
// ========================================================================

// Apply extensions when SchemaGraph classes are available
if (typeof SchemaGraph !== 'undefined') {
  extendSchemaGraphWithWorkflow(SchemaGraph);
  console.log('✓ SchemaGraph workflow extension loaded');
}

if (typeof SchemaGraphApp !== 'undefined') {
  extendSchemaGraphAppWithWorkflow(SchemaGraphApp);
  console.log('✓ SchemaGraphApp workflow extension loaded');
}

// Export for module usage
if (typeof module !== 'undefined' && module.exports) {
  module.exports = {
    FieldRole,
    WorkflowNode,
    WorkflowSchemaParser,
    WorkflowNodeGenerator,
    WorkflowImporter,
    WorkflowExporter,
    extendSchemaGraphWithWorkflow,
    extendSchemaGraphAppWithWorkflow
  };
}
