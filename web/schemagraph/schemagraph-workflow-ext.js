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
			let keys = nodeData[field.name];
			const expandedIndices = [];

			if (keys?.constructor == Object) {
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

	/**
	 * Import workflow from JSON
	 * @param {Object} workflowData - Workflow JSON
	 * @param {string} schemaName - Schema name
	 * @param {Object} schema - Schema definition
	 * @param {Object} options - Import options
	 * @param {boolean} options.includeLayout - Restore node positions/sizes (default: true)
	 */
	import(workflowData, schemaName, schema, options = {}) {
		if (!workflowData?.nodes) {
			throw new Error('Invalid workflow data: missing nodes array');
		}

		this.importOptions = {
			includeLayout: options.includeLayout !== false  // Default true
		};

		this.graph.nodes = [];
		this.graph.links = {};
		this.graph._nodes_by_id = {};
		this.graph.last_link_id = 0;

		const typeMap = schema ? this._buildTypeMap(schema) : {};
		const factory = schema ? new WorkflowNodeFactory(this.graph, {
			models: schema.parsed,
			fieldRoles: schema.fieldRoles,
			defaults: schema.defaults
		}, schemaName) : null;

		const createdNodes = [];
		
		for (let i = 0; i < workflowData.nodes.length; i++) {
			const nodeData = workflowData.nodes[i];
			const nodeType = nodeData.type || '';
			let node = null;

			// Determine node class by type prefix
			if (nodeType.startsWith('native_')) {
				node = this._createNativeNode(nodeData, i);
			} else if (nodeType.startsWith('data_') || nodeType === 'data') {
				node = this._createDataNode(nodeData, i);
			} else {
				node = this._createWorkflowNode(factory, nodeData, i, schemaName, typeMap);
			}

			createdNodes.push(node);
		}

		// Create edges
		if (workflowData.edges) {
			for (const edgeData of workflowData.edges) {
				this._createEdge(edgeData, createdNodes);
			}
		}

		// Auto-layout if layout was not restored
		if (this.importOptions?.includeLayout === false) {
			this._autoLayoutNodes(createdNodes);
		}

		// Execute all nodes
		for (const node of this.graph.nodes) {
			if (node?.onExecute) node.onExecute();
		}

		this.eventBus.emit('workflow:imported', {
			nodeCount: this.graph.nodes.length,
			linkCount: Object.keys(this.graph.links).length
		});

		return true;
	}

	/**
	 * Create Native node from schema format
	 */
	_createNativeNode(nodeData, index) {
		// Map schema type to JS native type
		const typeMap = {
			'native_string': 'String',
			'native_integer': 'Integer',
			'native_float': 'Float',
			'native_boolean': 'Boolean',
			'native_list': 'List',
			'native_dict': 'Dict'
		};

		const nativeType = typeMap[nodeData.type] || 'String';
		const nodeTypeKey = `Native.${nativeType}`;
		const NodeClass = this.graph.nodeTypes[nodeTypeKey];

		if (!NodeClass) {
			console.error(`Native node type not found: ${nodeTypeKey}`);
			return null;
		}

		const node = new NodeClass();

		// Register with graph
		if (this.graph._last_node_id === undefined) this.graph._last_node_id = 1;
		node.id = this.graph._last_node_id++;
		node.graph = this.graph;
		this.graph.nodes.push(node);
		this.graph._nodes_by_id[node.id] = node;

		// Set value
		if (nodeData.value !== undefined) {
			node.properties = node.properties || {};
			node.properties.value = nodeData.value;
		}

		// Restore position/size from extra (if layout enabled)
		if (this.importOptions?.includeLayout !== false) {
			if (nodeData.extra?.pos) node.pos = [...nodeData.extra.pos];
			if (nodeData.extra?.size) node.size = [...nodeData.extra.size];
		} else {
			// Auto-layout position will be set after all nodes are created
			node.pos = [0, 0];
		}

		node.workflowIndex = index;
		return node;
	}

	/**
	 * Create Data node from schema format
	 * Supports: source_url, source_path, source_data
	 */
	_createDataNode(nodeData, index) {
		// Map schema type to JS dataType
		const typeMap = {
			'data_text': 'text',
			'data_document': 'document',
			'data_image': 'image',
			'data_audio': 'audio',
			'data_video': 'video',
			'data_model3d': 'model3d',
			'data': nodeData.data_type || 'text'  // Generic data node
		};

		const dataType = typeMap[nodeData.type] || 'text';
		const capitalizedType = dataType.charAt(0).toUpperCase() + dataType.slice(1);
		const nodeTypeKey = `Data.${capitalizedType}`;
		
		// Try to get the specific DataNode class
		const NodeClass = typeof DataNodeTypes !== 'undefined' ? DataNodeTypes[nodeTypeKey] : null;

		if (!NodeClass) {
			console.error(`Data node type not found: ${nodeTypeKey}`);
			return null;
		}

		const node = new NodeClass();

		// Register with graph
		if (this.graph._last_node_id === undefined) this.graph._last_node_id = 1;
		node.id = this.graph._last_node_id++;
		node.graph = this.graph;
		this.graph.nodes.push(node);
		this.graph._nodes_by_id[node.id] = node;

		// Restore source info
		node.sourceType = nodeData.source_type || 'none';
		
		// Handle different source types
		if (nodeData.source_url) {
			node.sourceUrl = nodeData.source_url;
			node.sourceType = 'url';
		} else if (nodeData.source_path) {
			// File path reference - store as URL for now, can be loaded later
			node.sourceUrl = nodeData.source_path;
			node.sourceType = 'file';
			// Mark that this needs loading from path
			node._sourcePath = nodeData.source_path;
		} else if (nodeData.source_data) {
			node.sourceData = nodeData.source_data;
			// Determine if it's inline or file based on content
			if (nodeData.source_type === 'inline' || 
				(typeof nodeData.source_data === 'string' && !nodeData.source_data.startsWith('data:'))) {
				node.sourceType = 'inline';
			} else {
				node.sourceType = 'file';
			}
		}
		
		// Restore source metadata
		if (nodeData.source_meta) {
			node.sourceMeta = {
				filename: nodeData.source_meta.filename || '',
				mimeType: nodeData.source_meta.mime_type || '',
				size: nodeData.source_meta.size || 0,
				lastModified: nodeData.source_meta.last_modified || null
			};
		}

		// Restore type-specific fields
		if (dataType === 'text') {
			node.properties = node.properties || {};
			if (nodeData.encoding) node.properties.encoding = nodeData.encoding;
			if (nodeData.language) node.properties.language = nodeData.language;
		}
		if (dataType === 'image' && nodeData.dimensions) {
			node.imageDimensions = { width: nodeData.dimensions.width, height: nodeData.dimensions.height };
		}
		if (dataType === 'audio' && nodeData.duration) {
			node.audioDuration = nodeData.duration;
		}
		if (dataType === 'video') {
			if (nodeData.dimensions) {
				node.videoDimensions = { width: nodeData.dimensions.width, height: nodeData.dimensions.height };
			}
			if (nodeData.duration) node.videoDuration = nodeData.duration;
		}

		// Restore position/size/expanded from extra (if layout enabled)
		if (this.importOptions?.includeLayout !== false) {
			if (nodeData.extra?.pos) node.pos = [...nodeData.extra.pos];
			if (nodeData.extra?.size) node.size = [...nodeData.extra.size];
		} else {
			node.pos = [0, 0];
		}
		node.isExpanded = nodeData.extra?.isExpanded || false;

		node.workflowIndex = index;
		return node;
	}

	/**
	 * Create Workflow node from schema format
	 */
	_createWorkflowNode(factory, nodeData, index, schemaName, typeMap) {
		if (!factory) {
			console.error('No factory available for workflow nodes');
			return null;
		}

		const nodeType = nodeData.type;
		const modelName = this._resolveModelName(nodeType, schemaName, typeMap);

		if (!modelName) {
			console.error(`Model not found for type: ${nodeType}`);
			return null;
		}

		const node = factory.createNode(modelName, nodeData);
		if (!node) return null;

		// Register with graph
		if (this.graph._last_node_id === undefined) this.graph._last_node_id = 1;
		node.id = this.graph._last_node_id++;
		node.graph = this.graph;
		this.graph.nodes.push(node);
		this.graph._nodes_by_id[node.id] = node;

		// Restore position/size from extra (if layout enabled)
		if (this.importOptions?.includeLayout !== false) {
			if (nodeData.extra?.pos) node.pos = [...nodeData.extra.pos];
			if (nodeData.extra?.size) node.size = [...nodeData.extra.size];
		} else {
			node.pos = [0, 0];
		}

		node.workflowIndex = index;

		// Restore extra metadata
		if (nodeData.extra) {
			node.extra = { ...nodeData.extra };
			delete node.extra.pos;
			delete node.extra.size;
			if (nodeData.extra.title) node.title = nodeData.extra.title;
			if (nodeData.extra.color) node.color = nodeData.extra.color;
		}

		this._populateNodeFields(node, nodeData);
		return node;
	}

	_buildTypeMap(schema) {
		const typeMap = {};
		if (schema?.defaults) {
			for (const [key, value] of Object.entries(schema.defaults)) {
				if (value?.type) typeMap[value.type] = key;
			}
		}
		return typeMap;
	}

	_resolveModelName(nodeType, schemaName, typeMap) {
		if (typeMap?.[nodeType]) return typeMap[nodeType];

		const pascalName = this._snakeToPascal(nodeType);
		if (this.graph.schemas[schemaName]?.parsed[pascalName]) return pascalName;

		const baseName = nodeType.replace(/_config$|_node$/, '');
		for (const suffix of ['Config', 'Node', '']) {
			const name = this._snakeToPascal(baseName) + suffix;
			if (this.graph.schemas[schemaName]?.parsed[name]) return name;
		}
		return null;
	}

	_snakeToPascal(str) {
		return str.split('_').map(p => p.charAt(0).toUpperCase() + p.slice(1).toLowerCase()).join('');
	}

	/**
	 * Auto-layout nodes in a grid pattern
	 */
	_autoLayoutNodes(nodes) {
		const validNodes = nodes.filter(n => n);
		const count = validNodes.length;
		if (count === 0) return;

		const cols = Math.ceil(Math.sqrt(count));
		const spacingX = 280;
		const spacingY = 200;
		const startX = 100;
		const startY = 100;

		for (let i = 0; i < validNodes.length; i++) {
			const node = validNodes[i];
			const col = i % cols;
			const row = Math.floor(i / cols);
			node.pos = [startX + col * spacingX, startY + row * spacingY];
		}
	}

	_populateNodeFields(node, nodeData) {
		for (let i = 0; i < node.inputs.length; i++) {
			const input = node.inputs[i];
			const fieldName = input.name.split('.')[0];
			const value = nodeData[fieldName];
			if (value === undefined || value === null) continue;
			if (node.multiInputSlots?.[fieldName]) continue;
			if (node.nativeInputs?.[i] !== undefined) {
				node.nativeInputs[i].value = typeof value === 'object' ? JSON.stringify(value) : value;
			}
		}
	}

	_createEdge(edgeData, createdNodes) {
		const { source, target, source_slot, target_slot, preview, data, extra } = edgeData;
		const sourceNode = createdNodes[source];
		const targetNode = createdNodes[target];

		if (!sourceNode || !targetNode) {
			console.warn(`Edge skipped: invalid node reference (${source} -> ${target})`);
			return null;
		}

		const sourceSlotIdx = this._findOutputSlot(sourceNode, source_slot);
		const targetSlotIdx = this._findInputSlot(targetNode, target_slot);

		if (sourceSlotIdx === -1 || targetSlotIdx === -1) {
			console.warn(`Edge skipped: slot not found (${source_slot} -> ${target_slot})`);
			return null;
		}

		if (preview === true && typeof PreviewNode !== 'undefined') {
			return this._createEdgeWithPreview(sourceNode, sourceSlotIdx, source_slot, 
				targetNode, targetSlotIdx, target_slot, edgeData);
		}

		return this._createStandardEdge(sourceNode, sourceSlotIdx, targetNode, targetSlotIdx, data, extra);
	}

	_findOutputSlot(node, slotName) {
		// By name
		for (let i = 0; i < node.outputs.length; i++) {
			if (node.outputs[i].name === slotName) return i;
		}
		// By index
		const idx = parseInt(slotName);
		if (!isNaN(idx) && idx >= 0 && idx < node.outputs.length) return idx;
		// Default for data/native nodes
		if ((node.isDataNode || node.isNative) && node.outputs.length > 0) return 0;
		return -1;
	}

	_findInputSlot(node, slotName) {
		for (let i = 0; i < node.inputs.length; i++) {
			if (node.inputs[i].name === slotName) return i;
		}
		const idx = parseInt(slotName);
		if (!isNaN(idx) && idx >= 0 && idx < node.inputs.length) return idx;
		if ((node.isDataNode || node.isNative) && node.inputs.length > 0) return 0;
		return -1;
	}

	_createStandardEdge(sourceNode, sourceSlotIdx, targetNode, targetSlotIdx, data, extra) {
		const linkId = ++this.graph.last_link_id;
		const link = new Link(linkId, sourceNode.id, sourceSlotIdx, targetNode.id, targetSlotIdx, 
			sourceNode.outputs[sourceSlotIdx]?.type || 'Any');

		if (data) link.data = JSON.parse(JSON.stringify(data));
		if (extra) link.extra = JSON.parse(JSON.stringify(extra));

		this.graph.links[linkId] = link;
		sourceNode.outputs[sourceSlotIdx].links.push(linkId);
		
		if (targetNode.multiInputs?.[targetSlotIdx]) {
			targetNode.multiInputs[targetSlotIdx].links.push(linkId);
		} else {
			targetNode.inputs[targetSlotIdx].link = linkId;
		}

		this.eventBus.emit('link:created', { linkId });
		return link;
	}

	_createEdgeWithPreview(sourceNode, sourceSlotIdx, sourceSlot, targetNode, targetSlotIdx, targetSlot, edgeData) {
		const midX = (sourceNode.pos[0] + sourceNode.size[0] + targetNode.pos[0]) / 2 - 110;
		const midY = (sourceNode.pos[1] + targetNode.pos[1]) / 2;
		const linkType = sourceNode.outputs[sourceSlotIdx]?.type || 'Any';

		const previewNode = new PreviewNode();
		if (this.graph._last_node_id === undefined) this.graph._last_node_id = 1;
		previewNode.id = this.graph._last_node_id++;
		previewNode.graph = this.graph;
		previewNode.pos = [midX, midY];
		previewNode._originalEdgeInfo = {
			sourceNodeId: sourceNode.id,
			sourceSlotIdx, sourceSlotName: sourceSlot,
			targetNodeId: targetNode.id,
			targetSlotIdx, targetSlotName: targetSlot,
			linkType,
			data: edgeData.data ? JSON.parse(JSON.stringify(edgeData.data)) : null,
			extra: edgeData.extra ? JSON.parse(JSON.stringify(edgeData.extra)) : null,
		};

		this.graph.nodes.push(previewNode);
		this.graph._nodes_by_id[previewNode.id] = previewNode;

		// Source -> Preview
		const link1Id = ++this.graph.last_link_id;
		const link1 = new Link(link1Id, sourceNode.id, sourceSlotIdx, previewNode.id, 0, linkType);
		link1.extra = { _isPreviewLink: true };
		this.graph.links[link1Id] = link1;
		sourceNode.outputs[sourceSlotIdx].links.push(link1Id);
		previewNode.inputs[0].link = link1Id;

		// Preview -> Target
		const link2Id = ++this.graph.last_link_id;
		const link2 = new Link(link2Id, previewNode.id, 0, targetNode.id, targetSlotIdx, linkType);
		link2.extra = { _isPreviewLink: true };
		this.graph.links[link2Id] = link2;
		previewNode.outputs[0].links.push(link2Id);
		targetNode.inputs[targetSlotIdx].link = link2Id;

		this.eventBus.emit('preview:inserted', { nodeId: previewNode.id });
		return { link1, link2, previewNode };
	}
}

// ========================================================================
// WorkflowExporter
// ========================================================================

const DataExportMode = Object.freeze({
	REFERENCE : 'reference',  // Export by URL/path (default, smaller files)
	EMBEDDED  : 'embedded'     // Export with base64 data (larger but self-contained)
});

class WorkflowExporter {
	constructor(graph) {
		this.graph = graph;
	}

	/**
	 * Export workflow to JSON
	 * @param {string} schemaName - Schema name
	 * @param {Object} workflowInfo - Additional workflow metadata
	 * @param {Object} options - Export options
	 * @param {string} options.dataExportMode - 'reference' (default) or 'embedded'
	 * @param {string} options.dataBasePath - Base path for file references (e.g., 'assets/')
	 * @param {boolean} options.includeLayout - Include node position and size (default: true)
	 */
	export(schemaName, workflowInfo = {}, options = {}) {
		this.exportOptions = {
			dataExportMode: options.dataExportMode || DataExportMode.REFERENCE,
			dataBasePath: options.dataBasePath || '',
			includeLayout: options.includeLayout !== false  // Default true
		};
		const wf = JSON.parse(JSON.stringify(workflowInfo));
		const workflow = {
			...wf,
			type: 'workflow',
			nodes: [],
			edges: [],
		};

		// Collect exportable nodes (exclude preview nodes)
		const exportableNodes = [];
		const previewNodes = [];
		
		for (const node of this.graph.nodes) {
			if (node.isPreviewNode) {
				previewNodes.push(node);
			} else {
				exportableNodes.push(node);
			}
		}

		// Sort by workflowIndex if available
		exportableNodes.sort((a, b) => {
			if (a.workflowIndex !== undefined && b.workflowIndex !== undefined) {
				return a.workflowIndex - b.workflowIndex;
			}
			return (a.id || 0) - (b.id || 0);
		});

		// Build node ID to export index mapping
		const nodeToIndex = new Map();
		for (let i = 0; i < exportableNodes.length; i++) {
			nodeToIndex.set(exportableNodes[i].id, i);
			workflow.nodes.push(this._exportNode(exportableNodes[i]));
		}

		// Process edges (collapsing preview nodes)
		const previewNodeIds = new Set(previewNodes.map(n => n.id));
		const processedLinks = new Set();

		for (const linkId in this.graph.links) {
			if (processedLinks.has(linkId)) continue;
			
			const link = this.graph.links[linkId];
			const sourceNode = this.graph.getNodeById(link.origin_id);
			const targetNode = this.graph.getNodeById(link.target_id);

			if (!sourceNode || !targetNode) continue;

			// Source -> Preview: trace through chain
			if (!previewNodeIds.has(sourceNode.id) && previewNodeIds.has(targetNode.id)) {
				const edge = this._tracePreviewChain(link, sourceNode, targetNode, nodeToIndex, processedLinks);
				if (edge) workflow.edges.push(edge);
				continue;
			}

			// Normal edge
			if (!previewNodeIds.has(sourceNode.id) && !previewNodeIds.has(targetNode.id)) {
				const edge = this._exportEdge(link, nodeToIndex);
				if (edge) workflow.edges.push(edge);
				processedLinks.add(linkId);
			}
		}

		return workflow;
	}

	_exportNode(node) {
		if (node.isDataNode) return this._exportDataNode(node);
		if (node.isNative) return this._exportNativeNode(node);
		return this._exportWorkflowNode(node);
	}

	/**
	 * Export Data node per schema.py:
	 * type: "data_<dataType>" | "data"
	 * source_type, source_url, source_path, source_data, source_meta
	 * + type-specific fields (dimensions, duration, encoding, language)
	 * extra: { pos, size, isExpanded }
	 * 
	 * Export modes:
	 * - REFERENCE: exports URL/path only (smaller, requires external files)
	 * - EMBEDDED: exports base64 data inline (larger, self-contained)
	 */
	_exportDataNode(node) {
		const mode = this.exportOptions?.dataExportMode || DataExportMode.REFERENCE;
		const basePath = this.exportOptions?.dataBasePath || '';

		// Map JS dataType to schema type
		const typeMap = {
			'text': 'data_text',
			'document': 'data_document',
			'image': 'data_image',
			'audio': 'data_audio',
			'video': 'data_video',
			'model3d': 'data_model3d'
		};

		const nodeData = {
			type: typeMap[node.dataType] || 'data',
			source_type: node.sourceType || 'none'
		};

		// Generic data node: include data_type field
		if (!typeMap[node.dataType]) {
			nodeData.data_type = node.dataType || null;
		}

		// Source handling based on export mode
		if (node.sourceType === 'url') {
			// URL source: always export the URL
			nodeData.source_url = node.sourceUrl || '';
		} else if (node.sourceType === 'file') {
			if (mode === DataExportMode.EMBEDDED) {
				// Embedded mode: include base64 data
				if (node.sourceData) {
					nodeData.source_data = node.sourceData;
				}
			} else {
				// Reference mode: export file path
				const filename = node.sourceMeta?.filename || this._generateFilename(node);
				nodeData.source_path = basePath + filename;
			}
		} else if (node.sourceType === 'inline') {
			if (mode === DataExportMode.EMBEDDED) {
				// Embedded mode: include inline content
				if (node.sourceData) {
					nodeData.source_data = node.sourceData;
				}
			} else {
				// Reference mode for inline text: still embed (usually small)
				// But for binary data, use path reference
				if (node.dataType === 'text' && node.sourceData) {
					nodeData.source_data = node.sourceData;
				} else if (node.sourceData) {
					const filename = node.sourceMeta?.filename || this._generateFilename(node);
					nodeData.source_path = basePath + filename;
				}
			}
		}

		// Source metadata (always include for reference resolution)
		if (node.sourceMeta && Object.keys(node.sourceMeta).length > 0) {
			nodeData.source_meta = {
				filename: node.sourceMeta.filename || null,
				mime_type: node.sourceMeta.mimeType || null,
				size: node.sourceMeta.size || null,
				last_modified: node.sourceMeta.lastModified || null
			};
			// Remove null values
			for (const k in nodeData.source_meta) {
				if (nodeData.source_meta[k] === null) delete nodeData.source_meta[k];
			}
			if (Object.keys(nodeData.source_meta).length === 0) delete nodeData.source_meta;
		}

		// Type-specific fields
		if (node.dataType === 'text') {
			if (node.properties?.encoding) nodeData.encoding = node.properties.encoding;
			if (node.properties?.language) nodeData.language = node.properties.language;
		}
		if (node.dataType === 'image' && node.imageDimensions?.width) {
			nodeData.dimensions = { width: node.imageDimensions.width, height: node.imageDimensions.height };
		}
		if (node.dataType === 'audio' && node.audioDuration) {
			nodeData.duration = node.audioDuration;
		}
		if (node.dataType === 'video') {
			if (node.videoDimensions?.width) {
				nodeData.dimensions = { width: node.videoDimensions.width, height: node.videoDimensions.height };
			}
			if (node.videoDuration) nodeData.duration = node.videoDuration;
		}

		// Extra (position, size, expanded state)
		nodeData.extra = {};
		if (this.exportOptions?.includeLayout !== false) {
			nodeData.extra.pos = [...node.pos];
			nodeData.extra.size = [...node.size];
		}
		if (node.isExpanded) nodeData.extra.isExpanded = true;
		
		// Remove empty extra
		if (Object.keys(nodeData.extra).length === 0) delete nodeData.extra;

		return nodeData;
	}

	/**
	 * Generate a filename for data nodes without one
	 */
	_generateFilename(node) {
		const extMap = {
			'text': '.txt',
			'document': '.pdf',
			'image': '.png',
			'audio': '.mp3',
			'video': '.mp4',
			'model3d': '.glb'
		};
		const ext = extMap[node.dataType] || '.bin';
		const timestamp = Date.now();
		return `${node.dataType}_${node.id || timestamp}${ext}`;
	}

	/**
	 * Export Native node per schema.py:
	 * type: "native_<type>"
	 * value: the actual value
	 * extra: { pos, size }
	 */
	_exportNativeNode(node) {
		// Map JS native type to schema type
		const typeMap = {
			'String': 'native_string',
			'Integer': 'native_integer',
			'Float': 'native_float',
			'Boolean': 'native_boolean',
			'List': 'native_list',
			'Dict': 'native_dict'
		};

		const nativeType = node.title || 'String';
		
		// Get value
		let value = node.properties?.value;
		if (value === undefined) value = this._getDefaultNativeValue(nativeType);

		const nodeData = {
			type: typeMap[nativeType] || 'native_string',
			value: value
		};

		// Layout info
		if (this.exportOptions?.includeLayout !== false) {
			nodeData.extra = {
				pos: [...node.pos],
				size: [...node.size]
			};
		}

		return nodeData;
	}

	_getDefaultNativeValue(nativeType) {
		switch (nativeType) {
			case 'Integer': return 0;
			case 'Float': return 0.0;
			case 'Boolean': return false;
			case 'List': return [];
			case 'Dict': return {};
			default: return '';
		}
	}

	/**
	 * Export Workflow node (schema-defined nodes)
	 */
	_exportWorkflowNode(node) {
		const nodeData = {
			type: node.workflowType || node.constantFields?.type || 
				  node.modelName?.toLowerCase() || 'unknown'
		};

		// Constant fields (except type)
		if (node.constantFields) {
			for (const key in node.constantFields) {
				if (key !== 'type') nodeData[key] = node.constantFields[key];
			}
		}

		// Multi-input keys
		for (const [baseName, slotIndices] of Object.entries(node.multiInputSlots || {})) {
			const keys = slotIndices.map(idx => {
				const slotName = node.inputs[idx].name;
				const dotIdx = slotName.indexOf('.');
				return dotIdx !== -1 ? slotName.substring(dotIdx + 1) : null;
			}).filter(Boolean);
			if (keys.length > 0) nodeData[baseName] = keys;
		}

		// Multi-output keys
		for (const [baseName, slotIndices] of Object.entries(node.multiOutputSlots || {})) {
			const keys = slotIndices.map(idx => {
				const slotName = node.outputs[idx].name;
				const dotIdx = slotName.indexOf('.');
				return dotIdx !== -1 ? slotName.substring(dotIdx + 1) : null;
			}).filter(Boolean);
			if (keys.length > 0) nodeData[baseName] = keys;
		}

		// Native input values (non-connected)
		for (let i = 0; i < node.inputs.length; i++) {
			const input = node.inputs[i];
			if (input.link) continue;
			const baseName = input.name.split('.')[0];
			if (node.multiInputSlots?.[baseName]) continue;
			if (node.nativeInputs?.[i] !== undefined) {
				const val = node.nativeInputs[i].value;
				if (val !== null && val !== undefined && val !== '') {
					nodeData[input.name] = this._convertExportValue(val, node.nativeInputs[i].type);
				}
			}
		}

		// Extra
		nodeData.extra = {};
		if (this.exportOptions?.includeLayout !== false) {
			nodeData.extra.pos = [...node.pos];
			nodeData.extra.size = [...node.size];
		}
		if (node.extra) {
			const { pos, size, ...rest } = node.extra;
			nodeData.extra = { ...nodeData.extra, ...rest };
		}
		if (node.title !== `${node.schemaName}.${node.modelName}`) {
			nodeData.extra.title = node.title;
		}
		if (node.color) nodeData.extra.color = node.color;
		
		// Remove empty extra
		if (Object.keys(nodeData.extra).length === 0) delete nodeData.extra;

		return nodeData;
	}

	_tracePreviewChain(startLink, sourceNode, firstPreviewNode, nodeToIndex, processedLinks) {
		processedLinks.add(startLink.id);
		let currentPreviewNode = firstPreviewNode;
		const originalEdgeInfo = firstPreviewNode._originalEdgeInfo || {};
		
		while (currentPreviewNode?.isPreviewNode) {
			const outLinks = currentPreviewNode.outputs[0]?.links || [];
			if (outLinks.length === 0) return null;
			
			const outLinkId = outLinks[0];
			const outLink = this.graph.links[outLinkId];
			if (!outLink) return null;
			
			processedLinks.add(outLinkId);
			const nextNode = this.graph.getNodeById(outLink.target_id);
			if (!nextNode) return null;
			
			if (nextNode.isPreviewNode) {
				currentPreviewNode = nextNode;
			} else {
				const sourceIdx = nodeToIndex.get(sourceNode.id);
				const targetIdx = nodeToIndex.get(nextNode.id);
				if (sourceIdx === undefined || targetIdx === undefined) return null;
				
				const edge = {
					type: 'edge',
					source: sourceIdx,
					target: targetIdx,
					source_slot: originalEdgeInfo.sourceSlotName || 
						sourceNode.outputs[startLink.origin_slot]?.name || 'output',
					target_slot: originalEdgeInfo.targetSlotName || 
						nextNode.inputs[outLink.target_slot]?.name || 'input',
					preview: true
				};
				
				if (originalEdgeInfo.data) edge.data = JSON.parse(JSON.stringify(originalEdgeInfo.data));
				if (originalEdgeInfo.extra) {
					const cleanExtra = JSON.parse(JSON.stringify(originalEdgeInfo.extra));
					delete cleanExtra._isPreviewLink;
					if (Object.keys(cleanExtra).length > 0) edge.extra = cleanExtra;
				}
				
				return edge;
			}
		}
		return null;
	}

	_exportEdge(link, nodeToIndex) {
		const sourceNode = this.graph.getNodeById(link.origin_id);
		const targetNode = this.graph.getNodeById(link.target_id);
		if (!sourceNode || !targetNode) return null;

		const sourceIdx = nodeToIndex.get(link.origin_id);
		const targetIdx = nodeToIndex.get(link.target_id);
		if (sourceIdx === undefined || targetIdx === undefined) return null;

		const edge = {
			type: 'edge',
			source: sourceIdx,
			target: targetIdx,
			source_slot: sourceNode.outputs[link.origin_slot]?.name || 'output',
			target_slot: targetNode.inputs[link.target_slot]?.name || 'input'
		};

		if (link.data && Object.keys(link.data).length > 0) {
			edge.data = JSON.parse(JSON.stringify(link.data));
		}
		if (link.extra && Object.keys(link.extra).length > 0) {
			const cleanExtra = JSON.parse(JSON.stringify(link.extra));
			delete cleanExtra._isPreviewLink;
			if (Object.keys(cleanExtra).length > 0) edge.extra = cleanExtra;
		}

		return edge;
	}

	_convertExportValue(val, type) {
		if ((type === 'dict' || type === 'list') && typeof val === 'string') {
			try { return JSON.parse(val); } catch (e) { return val; }
		}
		return val;
	}

	/**
	 * Get list of data files that need to be saved alongside the workflow JSON
	 * (for reference-mode exports)
	 * @returns {Array<{path: string, data: string, mimeType: string}>}
	 */
	getDataFiles(schemaName, options = {}) {
		const basePath = options.dataBasePath || '';
		const files = [];

		for (const node of this.graph.nodes) {
			if (!node.isDataNode) continue;
			if (node.sourceType !== 'file' && node.sourceType !== 'inline') continue;
			if (!node.sourceData) continue;

			// Skip inline text (embedded in JSON)
			if (node.sourceType === 'inline' && node.dataType === 'text') continue;

			const filename = node.sourceMeta?.filename || this._generateFilename(node);
			const path = basePath + filename;
			
			files.push({
				path: path,
				data: node.sourceData,
				mimeType: node.sourceMeta?.mimeType || 'application/octet-stream',
				nodeId: node.id
			});
		}

		return files;
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
		DataExportMode,
		WorkflowExporter,
		extendSchemaGraphWithWorkflow,
		extendSchemaGraphAppWithWorkflow
	};
}
