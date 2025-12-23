// ========================================================================
// SCHEMAGRAPH WORKFLOW EXTENSION
// Adds support for workflow-style schemas with FieldRole annotations
// and nodes/edges JSON format. Supports class inheritance and type aliases.
// 
// Multi-input/output fields are expanded into individual slots based on
// config values (e.g., sources: ["a1","a2"] → sources.a1, sources.a2)
// ========================================================================

const FieldRole = Object.freeze({
	ANNOTATION   : 'annotation',
	CONSTANT     : 'constant',
	INPUT        : 'input',
	OUTPUT       : 'output',
	MULTI_INPUT  : 'multi_input',
	MULTI_OUTPUT : 'multi_output'
});

class WorkflowNode extends Node {
	constructor(title, config = {}) {
		super(title);
		this.isWorkflowNode = true;
		this.schemaName = config.schemaName || '';
		this.modelName = config.modelName || '';
		this.workflowType = config.workflowType || '';
		this.fieldRoles = config.fieldRoles || {};
		this.constantFields = config.constantFields || {};
		this.nativeInputs = {};
		this.multiInputSlots = {};	// Maps base field name → list of expanded slot indices
		this.multiOutputSlots = {}; // Maps base field name → list of expanded slot indices
		this.workflowIndex = null;
		this.extra = {};
	}

	getInputSlotByName(name) {
		for (let i = 0; i < this.inputs.length; i++) {
			if (this.inputs[i].name === name) return i;
		}
		return -1;
	}

	getOutputSlotByName(name) {
		for (let i = 0; i < this.outputs.length; i++) {
			if (this.outputs[i].name === name) return i;
		}
		return -1;
	}

	onExecute() {
		const data = { ...this.constantFields };

		for (let i = 0; i < this.inputs.length; i++) {
			const input = this.inputs[i];
			const fieldName = input.name;
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

		// Collect multi-input values by base field name
		for (const [baseName, slotIndices] of Object.entries(this.multiInputSlots)) {
			const values = {};
			for (const idx of slotIndices) {
				const slotName = this.inputs[idx].name;
				const key = slotName.split('.')[1];
				const link = this.inputs[idx].link;
				if (link) {
					const linkObj = this.graph.links[link];
					if (linkObj) {
						const sourceNode = this.graph.getNodeById(linkObj.origin_id);
						if (sourceNode && sourceNode.outputs[linkObj.origin_slot]) {
							values[key] = sourceNode.outputs[linkObj.origin_slot].value;
						}
					}
				}
			}
			if (Object.keys(values).length > 0) {
				data[baseName] = values;
			}
		}

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

class WorkflowSchemaParser {
	constructor() {
		this.models = {};
		this.fieldRoles = {};
		this.defaults = {};
		this.parents = {};
		this.rawModels = {};
		this.rawRoles = {};
		this.rawDefaults = {};
		this.typeAliases = {};
		this.moduleConstants = {};
	}

	parse(code) {
		this.models = {};
		this.fieldRoles = {};
		this.defaults = {};
		this.parents = {};
		this.rawModels = {};
		this.rawRoles = {};
		this.rawDefaults = {};

		this.typeAliases = this._extractTypeAliases(code);
		this.moduleConstants = this._extractModuleConstants(code);

		const lines = code.split('\n');
		let currentModel = null;
		let currentParent = null;
		let currentFields = [];
		let currentRoles = {};
		let currentDefaults = {};
		let inPropertyDef = false;

		for (let i = 0; i < lines.length; i++) {
			const line = lines[i];
			const trimmed = line.trim();

			if (!trimmed || trimmed.startsWith('#')) continue;

			const isIndented = line.length > 0 && (line[0] === '\t' || line[0] === ' ');

			const classMatch = trimmed.match(/^class\s+(\w+)\s*\(([^)]+)\)/);
			if (classMatch) {
				this._saveRawModel(currentModel, currentParent, currentFields, currentRoles, currentDefaults);
				currentModel = classMatch[1];
				const parentStr = classMatch[2].trim();
				const parentParts = parentStr.split(',').map(p => p.trim());
				currentParent = null;
				for (const p of parentParts) {
					const cleanParent = p.split('[')[0].trim();
					if (!['BaseModel', 'Generic', 'Enum', 'str'].includes(cleanParent)) {
						currentParent = cleanParent;
						break;
					}
				}
				currentFields = [];
				currentRoles = {};
				currentDefaults = {};
				inPropertyDef = false;
				continue;
			}

			if (!isIndented && currentModel && !classMatch) {
				this._saveRawModel(currentModel, currentParent, currentFields, currentRoles, currentDefaults);
				currentModel = null;
				currentParent = null;
				currentFields = [];
				currentRoles = {};
				currentDefaults = {};
				inPropertyDef = false;
				continue;
			}

			if (!currentModel || !isIndented) continue;

			if (trimmed === '@property') {
				inPropertyDef = true;
				continue;
			}

			if (inPropertyDef) {
				const propMatch = trimmed.match(/def\s+(\w+)\s*\([^)]*\)\s*->\s*Annotated\[([^,\]]+),\s*FieldRole\.(\w+)\]/);
				if (propMatch) {
					const [, propName, propType, role] = propMatch;
					const resolvedType = this._resolveTypeAlias(propType.trim());
					currentFields.push({
						name: propName,
						type: this._parseType(resolvedType),
						rawType: resolvedType,
						isProperty: true
					});
					currentRoles[propName] = role.toLowerCase();
				}
				inPropertyDef = false;
				continue;
			}

			if (trimmed.includes(':') && !trimmed.startsWith('def ') && !trimmed.startsWith('return ')) {
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

		this._saveRawModel(currentModel, currentParent, currentFields, currentRoles, currentDefaults);

		for (const modelName in this.rawModels) {
			this._resolveInheritance(modelName);
		}

		return {
			models: this.models,
			fieldRoles: this.fieldRoles,
			defaults: this.defaults
		};
	}

	_saveRawModel(name, parent, fields, roles, defaults) {
		if (name && fields.length > 0) {
			this.rawModels[name] = fields;
			this.rawRoles[name] = roles;
			this.rawDefaults[name] = defaults;
			this.parents[name] = parent;
		}
	}

	_resolveInheritance(modelName) {
		if (this.models[modelName]) return;

		const chain = [];
		let current = modelName;
		while (current && this.rawModels[current]) {
			chain.push(current);
			current = this.parents[current];
		}

		const mergedFields = [];
		const mergedRoles = {};
		const mergedDefaults = {};
		const seenFields = new Set();

		for (let i = chain.length - 1; i >= 0; i--) {
			const className = chain[i];
			const fields = this.rawModels[className] || [];
			const roles = this.rawRoles[className] || {};
			const defaults = this.rawDefaults[className] || {};

			for (const field of fields) {
				if (seenFields.has(field.name)) {
					const idx = mergedFields.findIndex(f => f.name === field.name);
					if (idx !== -1) mergedFields[idx] = { ...field };
				} else {
					mergedFields.push({ ...field });
					seenFields.add(field.name);
				}
				mergedRoles[field.name] = roles[field.name];
				if (defaults[field.name] !== undefined) {
					mergedDefaults[field.name] = defaults[field.name];
				}
			}
		}

		this.models[modelName] = mergedFields;
		this.fieldRoles[modelName] = mergedRoles;
		this.defaults[modelName] = mergedDefaults;
	}

	_extractTypeAliases(code) {
		const aliases = {};
		const lines = code.split('\n');
		for (const line of lines) {
			if (line.length > 0 && (line[0] === '\t' || line[0] === ' ')) continue;
			const trimmed = line.trim();
			const aliasMatch = trimmed.match(/^(\w+)\s*=\s*(Union\[.+\]|[A-Z]\w+(?:\[.+\])?)$/);
			if (aliasMatch) {
				const [, name, value] = aliasMatch;
				if (!/^[A-Z_]+$/.test(name) && !name.startsWith('DEFAULT_')) {
					aliases[name] = value;
				}
			}
		}
		return aliases;
	}

	_extractModuleConstants(code) {
		const constants = {};
		const lines = code.split('\n');
		for (const line of lines) {
			if (line.length > 0 && (line[0] === '\t' || line[0] === ' ')) continue;
			const trimmed = line.trim();
			const constMatch = trimmed.match(/^(DEFAULT_[A-Z_0-9]+|[A-Z][A-Z_0-9]*[A-Z0-9])\s*(?::\s*\w+)?\s*=\s*(.+)$/);
			if (constMatch) {
				const [, name, value] = constMatch;
				constants[name] = this._parseConstantValue(value.trim());
			}
		}
		return constants;
	}

	_parseConstantValue(valStr) {
		if (!valStr) return undefined;
		valStr = valStr.trim();
		if (valStr === 'None') return null;
		if (valStr === 'True') return true;
		if (valStr === 'False') return false;
		if ((valStr.startsWith('"') && valStr.endsWith('"')) ||
				(valStr.startsWith("'") && valStr.endsWith("'"))) {
			return valStr.slice(1, -1);
		}
		const num = parseFloat(valStr);
		if (!isNaN(num) && valStr.match(/^-?\d+\.?\d*$/)) return num;
		if (valStr === '[]') return [];
		if (valStr === '{}') return {};
		return valStr;
	}

	_resolveTypeAlias(typeStr) {
		if (!typeStr || !this.typeAliases) return typeStr;
		if (this.typeAliases[typeStr]) return this.typeAliases[typeStr];
		for (const [alias, resolved] of Object.entries(this.typeAliases)) {
			if (typeStr.includes(alias)) {
				typeStr = typeStr.replace(new RegExp(`\\b${alias}\\b`, 'g'), resolved);
			}
		}
		return typeStr;
	}

	_parseFieldLine(line) {
		// Match field name and check for Annotated
		const fieldStart = line.match(/^(\w+)\s*:\s*/);
		if (!fieldStart) return null;

		const name = fieldStart[1];
		if (name.startsWith('_')) return null;

		const afterColon = line.substring(fieldStart[0].length);

		// Check if it's an Annotated field
		if (afterColon.startsWith('Annotated[')) {
			// Extract content inside Annotated[...]
			const annotatedContent = this._extractBracketContent(afterColon, 10);
			
			// Find the FieldRole part (last comma-separated item, handling whitespace)
			const roleMatch = annotatedContent.match(/\s*,\s*FieldRole\.(\w+)\s*$/);
			if (!roleMatch) return null;

			const role = roleMatch[1].toLowerCase();
			const typeStr = annotatedContent.substring(0, roleMatch.index).trim();
			const resolvedType = this._resolveTypeAlias(typeStr);

			// Check for default value after the Annotated[...]
			const afterAnnotated = afterColon.substring(10 + annotatedContent.length + 1); // +1 for closing ]
			const defaultMatch = afterAnnotated.match(/^\s*=\s*(.+)$/);
			const defaultVal = defaultMatch ? this._parseDefaultValue(defaultMatch[1].trim()) : undefined;

			return { name, type: resolvedType, role, default: defaultVal };
		}

		// Simple field without Annotated
		const simpleMatch = afterColon.match(/^([^=]+?)(?:\s*=\s*(.+))?$/);
		if (simpleMatch) {
			const [, type, defaultVal] = simpleMatch;
			const resolvedType = this._resolveTypeAlias(type.trim());
			return {
				name,
				type: resolvedType,
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
		if ((valStr.startsWith('"') && valStr.endsWith('"')) ||
				(valStr.startsWith("'") && valStr.endsWith("'"))) {
			return valStr.slice(1, -1);
		}
		const num = parseFloat(valStr);
		if (!isNaN(num) && valStr.match(/^-?\d+\.?\d*$/)) return num;
		if (valStr === '[]') return [];
		if (valStr === '{}') return {};
		const msgMatch = valStr.match(/Message\s*\(\s*type\s*=\s*["']([^"']*)["']\s*,\s*value\s*=\s*["']([^"']*)["']\s*\)/);
		if (msgMatch) return msgMatch[2];
		const msgMatch2 = valStr.match(/Message\s*\(\s*["']([^"']*)["']\s*,\s*["']([^"']*)["']\s*\)/);
		if (msgMatch2) return msgMatch2[2];
		if (this.moduleConstants && valStr.match(/^[A-Z][A-Z_0-9]*[A-Z0-9]?$|^DEFAULT_[A-Z_0-9]+$/)) {
			if (this.moduleConstants[valStr] !== undefined) {
				return this.moduleConstants[valStr];
			}
		}
		return valStr;
	}

	_parseType(typeStr) {
		typeStr = typeStr.trim();
		if (typeStr.startsWith('Optional[')) {
			const inner = this._extractBracketContent(typeStr, 9);
			return { kind: 'optional', inner: this._parseType(inner) };
		}
		if (typeStr.startsWith('Union[')) {
			const inner = this._extractBracketContent(typeStr, 6);
			const types = this._splitUnionTypes(inner);
			return { kind: 'union', types: types.map(t => this._parseType(t)), inner };
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

	_splitUnionTypes(str) {
		const result = [];
		let depth = 0;
		let current = '';
		for (let i = 0; i < str.length; i++) {
			const c = str[i];
			if (c === '[') depth++;
			if (c === ']') depth--;
			if (c === ',' && depth === 0) {
				if (current.trim()) result.push(current.trim());
				current = '';
			} else {
				current += c;
			}
		}
		if (current.trim()) result.push(current.trim());
		return result;
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

// ========================================================================
// WorkflowNodeFactory - Creates nodes with expanded multi-slots
// ========================================================================

class WorkflowNodeFactory {
	constructor(graph, parsed, schemaName) {
		this.graph = graph;
		this.parsed = parsed;
		this.schemaName = schemaName;
	}

	/**
	 * Create a node instance with multi-input/output fields expanded
	 * based on the provided nodeData from the workflow config.
	 */
	createNode(modelName, nodeData = {}) {
		const { models, fieldRoles, defaults } = this.parsed;
		const fields = models[modelName];
		const roles = fieldRoles[modelName] || {};
		const modelDefaults = defaults[modelName] || {};

		if (!fields) {
			console.error(`Model not found: ${modelName}`);
			return null;
		}

		// Determine workflow type from constant fields
		let workflowType = modelName.toLowerCase();
		for (const field of fields) {
			if (field.name === 'type' && roles[field.name] === FieldRole.CONSTANT) {
				workflowType = modelDefaults[field.name] || workflowType;
				break;
			}
		}

		const nodeConfig = {
			schemaName: this.schemaName,
			modelName,
			workflowType,
			fieldRoles: { ...roles },
			constantFields: {}
		};

		// Categorize fields
		const inputFields = [];
		const outputFields = [];
		const multiInputFields = [];
		const multiOutputFields = [];

		for (const field of fields) {
			const role = roles[field.name] || FieldRole.INPUT;
			const defaultVal = modelDefaults[field.name];

			switch (role) {
				case FieldRole.ANNOTATION:
					// Annotation fields don't create slots - skip
					break;
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

		// Create node instance
		const node = new WorkflowNode(`${this.schemaName}.${modelName}`, nodeConfig);
		node.nativeInputs = {};
		node.multiInputSlots = {};
		node.multiOutputSlots = {};

		let inputIdx = 0;

		// Add regular inputs
		for (const field of inputFields) {
			node.addInput(field.name, field.rawType);
			if (this._isNativeType(field.rawType)) {
				node.nativeInputs[inputIdx] = {
					type: this._getNativeBaseType(field.rawType),
					value: field.default !== undefined ? field.default : this._getDefaultForType(field.rawType),
					optional: field.rawType.includes('Optional')
				};
			}
			inputIdx++;
		}

		// Add expanded multi-inputs based on nodeData
		for (const field of multiInputFields) {
			let	 keys = nodeData[field.name];
			const expandedIndices = [];

			if (keys.constructor == Object) {
				keys = Object.keys(keys);
			}

			if (Array.isArray(keys) && keys.length > 0) {
				for (const key of keys) {
					const slotName = `${field.name}.${key}`;
					node.addInput(slotName, field.rawType);
					expandedIndices.push(inputIdx);
					inputIdx++;
				}
			} else {
				node.addInput(field.name, field.rawType);
				expandedIndices.push(inputIdx);
				inputIdx++;
			}
			node.multiInputSlots[field.name] = expandedIndices;
		}

		let outputIdx = 0;

		// Add regular outputs
		for (const field of outputFields) {
			node.addOutput(field.name, field.rawType);
			outputIdx++;
		}

		// Add expanded multi-outputs based on nodeData
		for (const field of multiOutputFields) {
			let	 keys = nodeData[field.name];
			const expandedIndices = [];

			if (keys.constructor == Object) {
				keys = Object.keys(keys);
			}

			if (Array.isArray(keys) && keys.length > 0) {
				for (const key of keys) {
					const slotName = `${field.name}.${key}`;
					node.addOutput(slotName, field.rawType);
					expandedIndices.push(outputIdx);
					outputIdx++;
				}
			} else {
				node.addOutput(field.name, field.rawType);
				expandedIndices.push(outputIdx);
				outputIdx++;
			}
			node.multiOutputSlots[field.name] = expandedIndices;
		}

		// Size node based on slot count
		const maxSlots = Math.max(node.inputs.length, node.outputs.length, 1);
		node.size = [220, Math.max(80, 35 + maxSlots * 25)];

		return node;
	}

	_isNativeType(typeStr) {
		if (!typeStr) return false;
		const natives = ['str', 'int', 'bool', 'float', 'string', 'integer', 'Any'];
		let base = typeStr.replace(/Optional\[|\]/g, '').trim();
		if (base.startsWith('Union[') || base.includes('|')) {
			const unionContent = base.startsWith('Union[') ? base.slice(6, -1) : base;
			const parts = this._splitUnionTypes(unionContent);
			for (const part of parts) {
				const trimmed = part.trim();
				if (trimmed.startsWith('Message')) return true;
				if (natives.includes(trimmed.split('[')[0])) return true;
			}
			return false;
		}
		if (typeStr.includes('Message')) return true;
		base = base.split('[')[0].trim();
		return natives.includes(base);
	}

	_splitUnionTypes(str) {
		const result = [];
		let depth = 0;
		let current = '';
		for (let i = 0; i < str.length; i++) {
			const c = str[i];
			if (c === '[') depth++;
			if (c === ']') depth--;
			if ((c === ',' || c === '|') && depth === 0) {
				if (current.trim()) result.push(current.trim());
				current = '';
			} else {
				current += c;
			}
		}
		if (current.trim()) result.push(current.trim());
		return result;
	}

	_getNativeBaseType(typeStr) {
		if (!typeStr) return 'str';
		if (typeStr.includes('Message[')) {
			const match = typeStr.match(/Message\[([^\]]+)\]/);
			if (match) return this._getNativeBaseType(match[1]);
		}
		if (typeStr.includes('Union[') || typeStr.includes('|')) {
			const parts = this._splitUnionTypes(typeStr.replace(/^Union\[|\]$/g, ''));
			for (const part of parts) {
				const trimmed = part.trim();
				if (!trimmed.startsWith('Message')) return this._getNativeBaseType(trimmed);
			}
			if (parts.length > 0 && parts[0].includes('Message[')) {
				const match = parts[0].match(/Message\[([^\]]+)\]/);
				if (match) return this._getNativeBaseType(match[1]);
			}
		}
		if (typeStr.includes('int') || typeStr.includes('Int')) return 'int';
		if (typeStr.includes('bool') || typeStr.includes('Bool')) return 'bool';
		if (typeStr.includes('float') || typeStr.includes('Float')) return 'float';
		if (typeStr.includes('Dict') || typeStr.includes('dict')) return 'dict';
		if (typeStr.includes('List') || typeStr.includes('list')) return 'list';
		if (typeStr.includes('Any')) return 'str';
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
}

// ========================================================================
// WorkflowImporter
// ========================================================================

class WorkflowImporter {
	constructor(graph, eventBus) {
		this.graph = graph;
		this.eventBus = eventBus;
	}

	import(workflowData, schemaName, schema) {
		if (!workflowData || !workflowData.nodes) {
			throw new Error('Invalid workflow data: missing nodes array');
		}

		this.graph.nodes = [];
		this.graph.links = {};
		this.graph._nodes_by_id = {};
		this.graph.last_link_id = 0;

		const positions = this._calculateLayout(workflowData);
		const typeMap = this._buildTypeMap(schema);

		const factory = new WorkflowNodeFactory(this.graph, {
			models: schema.parsed,
			fieldRoles: schema.fieldRoles,
			defaults: schema.defaults
		}, schemaName);

		const createdNodes = [];
		for (let i = 0; i < workflowData.nodes.length; i++) {
			const nodeData = workflowData.nodes[i];
			const node = this._createNode(factory, nodeData, i, schemaName, typeMap, positions[i]);
			createdNodes.push(node);
		}

		if (workflowData.edges) {
			for (const edgeData of workflowData.edges) {
				this._createEdge(edgeData, createdNodes);
			}
		}

		for (const node of this.graph.nodes) {
			if (node) node.onExecute();
		}

		this.eventBus.emit('workflow:imported', {
			nodeCount: this.graph.nodes.length,
			linkCount: Object.keys(this.graph.links).length
		});

		return true;
	}

	_buildTypeMap(schema) {
		const typeMap = {};
		if (schema && schema.defaults) {
			for (let [key, value] of Object.entries(schema.defaults)) {
				if (value && value.type) {
					typeMap[value.type] = key;
				}
			}
		}
		return typeMap;
	}

	_createNode(factory, nodeData, index, schemaName, typeMap, position) {
		const nodeType = nodeData.type;
		const modelName = this._resolveModelName(nodeType, schemaName, typeMap);

		if (!modelName) {
			console.error(`Model not found for type: ${nodeType}`);
			return null;
		}

		try {
			const node = factory.createNode(modelName, nodeData);
			if (!node) return null;

			// Register node with graph
			if (this.graph._last_node_id === undefined) {
				this.graph._last_node_id = 1;
			}
			node.id = this.graph._last_node_id++;
			node.graph = this.graph;
			this.graph.nodes.push(node);
			this.graph._nodes_by_id[node.id] = node;

			node.pos = [position.x, position.y];
			node.workflowIndex = index;

			if (nodeData.extra) {
				node.extra = { ...nodeData.extra };
				if (nodeData.extra.title || nodeData.extra.name) {
					node.title = nodeData.extra.title || nodeData.extra.name;
				}
				if (nodeData.extra.color) {
					node.color = nodeData.extra.color;
				}
			}

			this._populateNodeFields(node, nodeData);

			return node;
		} catch (e) {
			console.error(`Failed to create node ${index}:`, e);
			return null;
		}
	}

	_resolveModelName(nodeType, schemaName, typeMap) {
		// Try type map first (type value → model name)
		if (typeMap && typeMap[nodeType]) {
			return typeMap[nodeType];
		}

		// Try PascalCase conversion
		const pascalName = this._snakeToPascal(nodeType);
		if (this.graph.schemas[schemaName]?.parsed[pascalName]) {
			return pascalName;
		}

		// Try common suffixes
		const baseName = nodeType.replace(/_config$|_node$/, '');
		for (const suffix of ['Config', 'Node', '']) {
			const name = this._snakeToPascal(baseName) + suffix;
			if (this.graph.schemas[schemaName]?.parsed[name]) {
				return name;
			}
		}

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
			const fieldName = input.name.split('.')[0]; // Get base name for dotted slots
			const value = nodeData[fieldName];

			if (value === undefined || value === null) continue;

			// Skip if this is a multi-input slot (handled by edges)
			if (node.multiInputSlots[fieldName]) continue;

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
		const { source, target, source_slot, target_slot, preview, extra } = edgeData;

		const sourceNode = createdNodes[source];
		const targetNode = createdNodes[target];

		if (!sourceNode || !targetNode) {
			console.warn(`Edge skipped: invalid node reference (${source} -> ${target})`);
			return null;
		}

		const sourceSlotIdx = sourceNode.getOutputSlotByName(source_slot);
		const targetSlotIdx = targetNode.getInputSlotByName(target_slot);

		if (sourceSlotIdx === -1) {
			console.warn(`Edge skipped: output slot "${source_slot}" not found on node ${source}`);
			return null;
		}
		if (targetSlotIdx === -1) {
			console.warn(`Edge skipped: input slot "${target_slot}" not found on node ${target}`);
			return null;
		}

		// If preview is enabled, insert a preview node
		if (preview === true) {
			return this._createEdgeWithPreview(
				sourceNode, sourceSlotIdx, source_slot,
				targetNode, targetSlotIdx, target_slot,
				extra
			);
		}

		// Standard edge creation
		const linkId = ++this.graph.last_link_id;
		const link = new Link(
			linkId,
			sourceNode.id,
			sourceSlotIdx,
			targetNode.id,
			targetSlotIdx,
			sourceNode.outputs[sourceSlotIdx]?.type || 'Any'
		);

		if (extra) {
			link.extra = { ...extra };
		}

		this.graph.links[linkId] = link;
		sourceNode.outputs[sourceSlotIdx].links.push(linkId);
		targetNode.inputs[targetSlotIdx].link = linkId;

		this.eventBus.emit('link:created', { linkId });
		
		return link;
	}

	/**
	 * Create an edge with a preview node inserted in the middle
	 */
	_createEdgeWithPreview(
		sourceNode, sourceSlotIdx, sourceSlot,
		targetNode, targetSlotIdx, targetSlot,
		extra
	) {
		// Calculate position for preview node (midpoint between source and target)
		const sourceX = sourceNode.pos[0] + sourceNode.size[0];
		const sourceY = sourceNode.pos[1] + 33 + sourceSlotIdx * 25;
		const targetX = targetNode.pos[0];
		const targetY = targetNode.pos[1] + 33 + targetSlotIdx * 25;
		
		const midX = (sourceX + targetX) / 2 - 110; // Center the preview node
		const midY = (sourceY + targetY) / 2 - 60;

		// Create preview node
		const previewNode = new PreviewNode();
		
		if (this.graph._last_node_id === undefined) {
			this.graph._last_node_id = 1;
		}
		previewNode.id = this.graph._last_node_id++;
		previewNode.graph = this.graph;
		previewNode.pos = [midX, midY];
		
		// Mark as auto-inserted from edge preview
		previewNode._fromEdgePreview = true;
		previewNode._originalSourceSlot = sourceSlot;
		previewNode._originalTargetSlot = targetSlot;
		
		this.graph.nodes.push(previewNode);
		this.graph._nodes_by_id[previewNode.id] = previewNode;

		const linkType = sourceNode.outputs[sourceSlotIdx]?.type || 'Any';

		// Create link: Source -> Preview
		const link1Id = ++this.graph.last_link_id;
		const link1 = new Link(
			link1Id,
			sourceNode.id,
			sourceSlotIdx,
			previewNode.id,
			0, // Preview input slot
			linkType
		);
		
		if (extra) {
			link1.extra = { ...extra, _isPreviewLink: true };
		} else {
			link1.extra = { _isPreviewLink: true };
		}
		
		this.graph.links[link1Id] = link1;
		sourceNode.outputs[sourceSlotIdx].links.push(link1Id);
		previewNode.inputs[0].link = link1Id;

		// Create link: Preview -> Target
		const link2Id = ++this.graph.last_link_id;
		const link2 = new Link(
			link2Id,
			previewNode.id,
			0, // Preview output slot
			targetNode.id,
			targetSlotIdx,
			linkType
		);
		
		link2.extra = { _isPreviewLink: true };
		
		this.graph.links[link2Id] = link2;
		previewNode.outputs[0].links.push(link2Id);
		targetNode.inputs[targetSlotIdx].link = link2Id;

		this.eventBus.emit('link:created', { linkId: link1Id });
		this.eventBus.emit('link:created', { linkId: link2Id });
		this.eventBus.emit('preview:inserted', { 
			nodeId: previewNode.id, 
			fromEdgePreview: true 
		});

		return { link1, link2, previewNode };
	}

	_calculateLayout(workflowData) {
		const positions = [];
		const nodeCount = workflowData.nodes.length;
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

// ========================================================================
// WorkflowExporter
// ========================================================================

class WorkflowExporter {
	constructor(graph) {
		this.graph = graph;
	}

	export(schemaName, workflowInfo = {}) {
		const workflow = {
			type: 'workflow',
			info: workflowInfo.info || null,
			options: workflowInfo.options || null,
			nodes: [],
			edges: []
		};

		// Separate workflow nodes from preview nodes
		const workflowNodes = [];
		const previewNodes = [];
		
		for (const node of this.graph.nodes) {
			if (node.isPreviewNode) {
				previewNodes.push(node);
			} else if (node.schemaName === schemaName || node.isWorkflowNode) {
				workflowNodes.push(node);
			}
		}

		// Sort workflow nodes by original index
		workflowNodes.sort((a, b) => {
			if (a.workflowIndex !== undefined && b.workflowIndex !== undefined) {
				return a.workflowIndex - b.workflowIndex;
			}
			return 0;
		});

		// Build node ID to export index mapping
		const nodeToIndex = new Map();
		for (let i = 0; i < workflowNodes.length; i++) {
			nodeToIndex.set(workflowNodes[i].id, i);
			workflow.nodes.push(this._exportNode(workflowNodes[i]));
		}

		// Build set of preview node IDs for quick lookup
		const previewNodeIds = new Set(previewNodes.map(n => n.id));

		// Track which links have been processed (to avoid duplicates)
		const processedLinks = new Set();

		// Process all links, collapsing preview nodes back to single edges
		for (const linkId in this.graph.links) {
			if (processedLinks.has(linkId)) continue;
			
			const link = this.graph.links[linkId];
			const sourceNode = this.graph.getNodeById(link.origin_id);
			const targetNode = this.graph.getNodeById(link.target_id);

			if (!sourceNode || !targetNode) continue;

			// Case 1: Source is workflow node, target is preview node
			if (!previewNodeIds.has(sourceNode.id) && previewNodeIds.has(targetNode.id)) {
				const edge = this._tracePreviewChain(link, sourceNode, targetNode, nodeToIndex, processedLinks);
				if (edge) {
					workflow.edges.push(edge);
				}
				continue;
			}

			// Case 2: Both are workflow nodes (normal edge)
			if (!previewNodeIds.has(sourceNode.id) && !previewNodeIds.has(targetNode.id)) {
				const edge = this._exportEdge(link, nodeToIndex);
				if (edge) {
					workflow.edges.push(edge);
				}
				processedLinks.add(linkId);
			}
			
			// Case 3: Source is preview node - skip (handled by tracing from workflow node)
		}

		return workflow;
	}

	/**
	 * Trace through a chain of preview nodes and create a single edge with preview: true
	 */
	_tracePreviewChain(startLink, sourceNode, firstPreviewNode, nodeToIndex, processedLinks) {
		processedLinks.add(startLink.id);
		
		let currentPreviewNode = firstPreviewNode;
		let hasPreview = true;
		let accumulatedExtra = startLink.extra ? { ...startLink.extra } : {};
		
		// Remove internal tracking fields
		delete accumulatedExtra._isPreviewLink;
		
		// Trace through chain of preview nodes
		while (currentPreviewNode && currentPreviewNode.isPreviewNode) {
			const outLinks = currentPreviewNode.outputs[0]?.links || [];
			
			if (outLinks.length === 0) {
				// Preview node with no output - edge terminates here
				return null;
			}
			
			// Get the outgoing link
			const outLinkId = outLinks[0];
			const outLink = this.graph.links[outLinkId];
			
			if (!outLink) {
				return null;
			}
			
			processedLinks.add(outLinkId);
			
			const nextNode = this.graph.getNodeById(outLink.target_id);
			
			if (!nextNode) {
				return null;
			}
			
			if (nextNode.isPreviewNode) {
				// Continue tracing through preview chain
				currentPreviewNode = nextNode;
			} else {
				// Reached a workflow node - create the final edge
				const sourceIdx = nodeToIndex.get(sourceNode.id);
				const targetIdx = nodeToIndex.get(nextNode.id);
				
				if (sourceIdx === undefined || targetIdx === undefined) {
					return null;
				}
				
				// Get slot names
				const sourceSlot = firstPreviewNode._originalSourceSlot || 
					sourceNode.outputs[startLink.origin_slot]?.name || 'output';
				const targetSlot = firstPreviewNode._originalTargetSlot ||
					nextNode.inputs[outLink.target_slot]?.name || 'input';
				
				const edge = {
					source: sourceIdx,
					target: targetIdx,
					source_slot: sourceSlot,
					target_slot: targetSlot,
					preview: hasPreview
				};
				
				if (Object.keys(accumulatedExtra).length > 0) {
					edge.extra = accumulatedExtra;
				}
				
				return edge;
			}
		}
		
		return null;
	}

	/**
	 * Export a standard edge (no preview nodes involved)
	 */
	_exportEdge(link, nodeToIndex) {
		const sourceNode = this.graph.getNodeById(link.origin_id);
		const targetNode = this.graph.getNodeById(link.target_id);

		if (!sourceNode || !targetNode) return null;

		const sourceIdx = nodeToIndex.get(link.origin_id);
		const targetIdx = nodeToIndex.get(link.target_id);

		if (sourceIdx === undefined || targetIdx === undefined) return null;

		const sourceSlot = sourceNode.outputs[link.origin_slot]?.name || 'output';
		const targetSlot = targetNode.inputs[link.target_slot]?.name || 'input';

		const edge = {
			source: sourceIdx,
			target: targetIdx,
			source_slot: sourceSlot,
			target_slot: targetSlot
			// preview: false is the default, so we omit it
		};

		if (link.extra && Object.keys(link.extra).length > 0) {
			// Filter out internal tracking fields
			const cleanExtra = { ...link.extra };
			delete cleanExtra._isPreviewLink;
			
			if (Object.keys(cleanExtra).length > 0) {
				edge.extra = cleanExtra;
			}
		}

		return edge;
	}

	_exportNode(node) {
		const nodeData = {
			type: node.workflowType || node.constantFields?.type || node.modelName?.toLowerCase() || 'unknown'
		};

		// Export constant fields
		if (node.constantFields) {
			for (const key in node.constantFields) {
				if (key !== 'type') {
					nodeData[key] = node.constantFields[key];
				}
			}
		}

		// Export multi-input keys
		for (const [baseName, slotIndices] of Object.entries(node.multiInputSlots || {})) {
			const keys = [];
			for (const idx of slotIndices) {
				const slotName = node.inputs[idx].name;
				const dotIdx = slotName.indexOf('.');
				if (dotIdx !== -1) {
					keys.push(slotName.substring(dotIdx + 1));
				}
			}
			if (keys.length > 0) {
				nodeData[baseName] = keys;
			}
		}

		// Export multi-output keys
		for (const [baseName, slotIndices] of Object.entries(node.multiOutputSlots || {})) {
			const keys = [];
			for (const idx of slotIndices) {
				const slotName = node.outputs[idx].name;
				const dotIdx = slotName.indexOf('.');
				if (dotIdx !== -1) {
					keys.push(slotName.substring(dotIdx + 1));
				}
			}
			if (keys.length > 0) {
				nodeData[baseName] = keys;
			}
		}

		// Export native input values (non-connected)
		for (let i = 0; i < node.inputs.length; i++) {
			const input = node.inputs[i];
			if (input.link) continue; // Skip connected inputs

			const baseName = input.name.split('.')[0];
			if (node.multiInputSlots[baseName]) continue; // Skip multi-input slots

			if (node.nativeInputs && node.nativeInputs[i] !== undefined) {
				const val = node.nativeInputs[i].value;
				if (val !== null && val !== undefined && val !== '') {
					nodeData[input.name] = this._convertExportValue(val, node.nativeInputs[i].type);
				}
			}
		}

		// Export extra metadata
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

		const sourceSlot = sourceNode.outputs[link.origin_slot]?.name || 'output';
		const targetSlot = targetNode.inputs[link.target_slot]?.name || 'input';

		const edge = {
			source: sourceIdx,
			target: targetIdx,
			source_slot: sourceSlot,
			target_slot: targetSlot
		};

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

function extendSchemaGraphWithWorkflow(SchemaGraphClass) {
	const originalRegisterSchema = SchemaGraphClass.prototype.registerSchema;

	SchemaGraphClass.prototype.registerSchema = function(schemaName, schemaCode, indexType = 'int', rootType = null) {
		if (schemaCode.includes('FieldRole.')) {
			return this.registerWorkflowSchema(schemaName, schemaCode);
		}
		return originalRegisterSchema.call(this, schemaName, schemaCode, indexType, rootType);
	};

	SchemaGraphClass.prototype.registerWorkflowSchema = function(schemaName, schemaCode) {
		try {
			const parser = new WorkflowSchemaParser();
			const parsed = parser.parse(schemaCode);

			this.schemas[schemaName] = {
				code: schemaCode,
				parsed: parsed.models,
				isWorkflow: true,
				fieldRoles: parsed.fieldRoles,
				defaults: parsed.defaults
			};

			// Register node types for context menu
			if (!this.nodeTypes) this.nodeTypes = {};

			const self = this;

			for (const modelName in parsed.models) {
				const defaults = parsed.defaults[modelName] || {};
				
				// Skip models without a type constant (abstract base classes)
				if (!defaults.type) continue;
				
				const fullTypeName = `${schemaName}.${modelName}`;
				
				// Capture values for closure
				const capturedModelName = modelName;
				const capturedSchemaName = schemaName;
				const capturedFields = parsed.models[modelName];
				const capturedRoles = parsed.fieldRoles[modelName];
				const capturedDefaults = defaults;
				
				// Create constructor function
				function WorkflowNodeType() {
					const factory = new WorkflowNodeFactory(self, {
						models: { [capturedModelName]: capturedFields },
						fieldRoles: { [capturedModelName]: capturedRoles },
						defaults: { [capturedModelName]: capturedDefaults }
					}, capturedSchemaName);
					
					const node = factory.createNode(capturedModelName, {});
					
					// Copy all properties to this instance
					Object.assign(this, node);
					
					// Copy prototype chain methods
					Object.setPrototypeOf(this, node);
				}
				
				WorkflowNodeType.title = modelName.replace(/([A-Z])/g, ' $1').trim();
				WorkflowNodeType.type = fullTypeName;
				
				this.nodeTypes[fullTypeName] = WorkflowNodeType;
			}

			this.enabledSchemas.add(schemaName);
			this.eventBus.emit('schema:registered', { schemaName, isWorkflow: true });
			return true;
		} catch (e) {
			console.error('Workflow schema registration error:', e);
			this.eventBus.emit('error', { type: 'schema:register', error: e.message });
			return false;
		}
	};

	SchemaGraphClass.prototype._formatNodeTitle = function(modelName) {
		return modelName
			.replace(/([A-Z])/g, ' $1')
			.replace(/^./, s => s.toUpperCase())
			.trim();
	};

	SchemaGraphClass.prototype.importWorkflow = function(workflowData, schemaName) {
		const importer = new WorkflowImporter(this, this.eventBus);
		return importer.import(workflowData, schemaName, this.schemas[schemaName]);
	};

	SchemaGraphClass.prototype.exportWorkflow = function(schemaName, workflowInfo = {}) {
		const exporter = new WorkflowExporter(this);
		return exporter.export(schemaName, workflowInfo);
	};

	SchemaGraphClass.prototype.isWorkflowSchema = function(schemaName) {
		return this.schemas[schemaName]?.isWorkflow === true;
	};
}

function extendSchemaGraphAppWithWorkflow(SchemaGraphAppClass) {
	const originalCreateAPI = SchemaGraphAppClass.prototype._createAPI;

	SchemaGraphAppClass.prototype._createAPI = function() {
		const api = originalCreateAPI.call(this);

		api.workflow = {
			registerSchema: (name, code) => {
				return this.graph.registerWorkflowSchema(name, code);
			},

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

			export: (schemaName, workflowInfo = {}) => {
				return this.graph.exportWorkflow(schemaName, workflowInfo);
			},

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

if (typeof SchemaGraph !== 'undefined') {
	extendSchemaGraphWithWorkflow(SchemaGraph);
}

if (typeof SchemaGraphApp !== 'undefined') {
	extendSchemaGraphAppWithWorkflow(SchemaGraphApp);
}

if (typeof module !== 'undefined' && module.exports) {
	module.exports = {
		FieldRole,
		WorkflowNode,
		WorkflowSchemaParser,
		WorkflowNodeFactory,
		WorkflowImporter,
		WorkflowExporter,
		extendSchemaGraphWithWorkflow,
		extendSchemaGraphAppWithWorkflow
	};
}
