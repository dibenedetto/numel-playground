// ========================================================================
// SCHEMAGRAPH WORKFLOW EXTENSION
// Adds support for workflow-style schemas with FieldRole annotations
// and nodes/edges JSON format. Supports class inheritance and type aliases.
// 
// Multi-input/output fields are expanded into individual slots based on
// config values (e.g., sources: ["a1","a2"] → sources.a1, sources.a2)
// 
// Integrates with SchemaGraphExtension base class from extensions-core.js
// ========================================================================

const FieldRole = Object.freeze({
	ANNOTATION   : 'annotation',
	CONSTANT     : 'constant',
	INPUT        : 'input',
	OUTPUT       : 'output',
	MULTI_INPUT  : 'multi_input',
	MULTI_OUTPUT : 'multi_output'
});

const DataExportMode = Object.freeze({
	REFERENCE: 'reference',
	EMBEDDED: 'embedded'
});

// ========================================================================
// WorkflowNode
// ========================================================================

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
		this.multiInputSlots = {};
		this.multiOutputSlots = {};
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
			} else if (this.nativeInputs?.[i] !== undefined) {
				const nativeInput = this.nativeInputs[i];
				const val = nativeInput.value;
				const isEmpty = val === null || val === undefined || val === '';
				if (!isEmpty || nativeInput.type === 'bool') {
					data[fieldName] = this._convertNativeValue(val, nativeInput.type);
				}
			}
		}

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
						if (sourceNode?.outputs[linkObj.origin_slot]) {
							values[key] = sourceNode.outputs[linkObj.origin_slot].value;
						}
					}
				}
			}
			if (Object.keys(values).length > 0) data[baseName] = values;
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
					try { return JSON.parse(val); } catch { return type === 'dict' ? {} : []; }
				}
				return val;
			default: return val;
		}
	}
}

// ========================================================================
// WorkflowSchemaParser
// ========================================================================

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
		let currentModel = null, currentParent = null;
		let currentFields = [], currentRoles = {}, currentDefaults = {};
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

		return { models: this.models, fieldRoles: this.fieldRoles, defaults: this.defaults };
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

		const mergedFields = [], mergedRoles = {}, mergedDefaults = {};
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
		for (const line of code.split('\n')) {
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
		for (const line of code.split('\n')) {
			if (line.length > 0 && (line[0] === '\t' || line[0] === ' ')) continue;
			const trimmed = line.trim();
			const constMatch = trimmed.match(/^(DEFAULT_[A-Z_0-9]+|[A-Z][A-Z_0-9]*[A-Z0-9])\s*(?::\s*\w+)?\s*=\s*(.+)$/);
			if (constMatch) {
				constants[constMatch[1]] = this._parseConstantValue(constMatch[2].trim());
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
		if ((valStr.startsWith('"') && valStr.endsWith('"')) || (valStr.startsWith("'") && valStr.endsWith("'"))) {
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
		const fieldStart = line.match(/^(\w+)\s*:\s*/);
		if (!fieldStart) return null;

		const name = fieldStart[1];
		if (name.startsWith('_')) return null;

		const afterColon = line.substring(fieldStart[0].length);

		if (afterColon.startsWith('Annotated[')) {
			const annotatedContent = this._extractBracketContent(afterColon, 10);
			const roleMatch = annotatedContent.match(/\s*,\s*FieldRole\.(\w+)\s*$/);
			if (!roleMatch) return null;

			const role = roleMatch[1].toLowerCase();
			const typeStr = annotatedContent.substring(0, roleMatch.index).trim();
			const resolvedType = this._resolveTypeAlias(typeStr);

			const afterAnnotated = afterColon.substring(10 + annotatedContent.length + 1);
			const defaultMatch = afterAnnotated.match(/^\s*=\s*(.+)$/);
			const defaultVal = defaultMatch ? this._parseDefaultValue(defaultMatch[1].trim()) : undefined;

			return { name, type: resolvedType, role, default: defaultVal };
		}

		const simpleMatch = afterColon.match(/^([^=]+?)(?:\s*=\s*(.+))?$/);
		if (simpleMatch) {
			const [, type, defaultVal] = simpleMatch;
			return {
				name,
				type: this._resolveTypeAlias(type.trim()),
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
		if ((valStr.startsWith('"') && valStr.endsWith('"')) || (valStr.startsWith("'") && valStr.endsWith("'"))) {
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
			if (this.moduleConstants[valStr] !== undefined) return this.moduleConstants[valStr];
		}
		return valStr;
	}

	_parseType(typeStr) {
		typeStr = typeStr.trim();
		if (typeStr.startsWith('Optional[')) {
			return { kind: 'optional', inner: this._parseType(this._extractBracketContent(typeStr, 9)) };
		}
		if (typeStr.startsWith('Union[')) {
			const inner = this._extractBracketContent(typeStr, 6);
			return { kind: 'union', types: this._splitUnionTypes(inner).map(t => this._parseType(t)), inner };
		}
		if (typeStr.startsWith('List[')) {
			return { kind: 'list', inner: this._parseType(this._extractBracketContent(typeStr, 5)) };
		}
		if (typeStr.startsWith('Dict[')) {
			return { kind: 'dict', inner: this._extractBracketContent(typeStr, 5) };
		}
		if (typeStr.startsWith('Message[')) {
			return { kind: 'message', inner: this._parseType(this._extractBracketContent(typeStr, 8)) };
		}
		return { kind: 'basic', name: typeStr };
	}

	_splitUnionTypes(str) {
		const result = [];
		let depth = 0, current = '';
		for (const c of str) {
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
		let depth = 1, i = startIdx;
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
// WorkflowNodeFactory
// ========================================================================

class WorkflowNodeFactory {
	constructor(graph, parsed, schemaName) {
		this.graph = graph;
		this.parsed = parsed;
		this.schemaName = schemaName;
	}

	createNode(modelName, nodeData = {}) {
		const { models, fieldRoles, defaults } = this.parsed;
		const fields = models[modelName];
		const roles = fieldRoles[modelName] || {};
		const modelDefaults = defaults[modelName] || {};

		if (!fields) {
			console.error(`Model not found: ${modelName}`);
			return null;
		}

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

		const inputFields = [], outputFields = [], multiInputFields = [], multiOutputFields = [];

		for (const field of fields) {
			const role = roles[field.name] || FieldRole.INPUT;
			const defaultVal = modelDefaults[field.name];

			switch (role) {
				case FieldRole.ANNOTATION: break;
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

		const node = new WorkflowNode(`${this.schemaName}.${modelName}`, nodeConfig);
		node.nativeInputs = {};
		node.multiInputSlots = {};
		node.multiOutputSlots = {};

		let inputIdx = 0;

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

		for (const field of multiInputFields) {
			let keys = nodeData[field.name];
			const expandedIndices = [];
			if (keys?.constructor === Object) keys = Object.keys(keys);

			if (Array.isArray(keys) && keys.length > 0) {
				for (const key of keys) {
					node.addInput(`${field.name}.${key}`, field.rawType);
					expandedIndices.push(inputIdx++);
				}
			} else {
				node.addInput(field.name, field.rawType);
				expandedIndices.push(inputIdx++);
			}
			node.multiInputSlots[field.name] = expandedIndices;
		}

		let outputIdx = 0;

		for (const field of outputFields) {
			node.addOutput(field.name, field.rawType);
			outputIdx++;
		}

		for (const field of multiOutputFields) {
			let keys = nodeData[field.name];
			const expandedIndices = [];
			if (keys?.constructor === Object) keys = Object.keys(keys);

			if (Array.isArray(keys) && keys.length > 0) {
				for (const key of keys) {
					node.addOutput(`${field.name}.${key}`, field.rawType);
					expandedIndices.push(outputIdx++);
				}
			} else {
				node.addOutput(field.name, field.rawType);
				expandedIndices.push(outputIdx++);
			}
			node.multiOutputSlots[field.name] = expandedIndices;
		}

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
			for (const part of this._splitUnionTypes(unionContent)) {
				const trimmed = part.trim();
				if (trimmed.startsWith('Message')) return true;
				if (natives.includes(trimmed.split('[')[0])) return true;
			}
			return false;
		}
		if (typeStr.includes('Message')) return true;
		return natives.includes(base.split('[')[0].trim());
	}

	_splitUnionTypes(str) {
		const result = [];
		let depth = 0, current = '';
		for (const c of str) {
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
				if (!part.trim().startsWith('Message')) return this._getNativeBaseType(part.trim());
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
		switch (this._getNativeBaseType(typeStr)) {
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

	import(workflowData, schemaName, schema, options = {}) {
		if (!workflowData?.nodes) throw new Error('Invalid workflow data: missing nodes array');

		this.importOptions = { includeLayout: options.includeLayout !== false };

		// Clear existing graph data
		this.graph.nodes = [];
		this.graph.links = {};
		this.graph._nodes_by_id = {};
		this.graph.last_link_id = 0;
		if (this.graph._last_node_id === undefined) this.graph._last_node_id = 1;

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

			if (nodeType.startsWith('native_')) {
				node = this._createNativeNode(nodeData, i);
			} else if (nodeType.startsWith('data_') || nodeType === 'data') {
				node = this._createDataNode(nodeData, i);
			} else {
				node = this._createWorkflowNode(factory, nodeData, i, schemaName, typeMap);
			}
			createdNodes.push(node);
		}

		if (workflowData.edges) {
			for (const edgeData of workflowData.edges) {
				this._createEdge(edgeData, createdNodes);
			}
		}

		if (this.importOptions?.includeLayout === false) {
			this._autoLayoutNodes(createdNodes);
		}

		for (const node of this.graph.nodes) {
			if (node?.onExecute) node.onExecute();
		}

		this.eventBus.emit('workflow:imported', {
			nodeCount: this.graph.nodes.length,
			linkCount: Object.keys(this.graph.links).length
		});

		return true;
	}

	_createNativeNode(nodeData, index) {
		const typeMap = {
			'native_string': 'String', 'native_integer': 'Integer', 'native_float': 'Float',
			'native_boolean': 'Boolean', 'native_list': 'List', 'native_dict': 'Dict'
		};
		const nativeType = typeMap[nodeData.type] || 'String';
		const NodeClass = this.graph.nodeTypes[`Native.${nativeType}`];
		if (!NodeClass) { console.error(`Native node type not found: Native.${nativeType}`); return null; }

		const node = new NodeClass();
		
		if (nodeData.value !== undefined) {
			node.properties = node.properties || {};
			node.properties.value = nodeData.value;
		}

		this._applyLayout(node, nodeData);
		node.workflowIndex = index;
		
		// Use proper API - emits node:created
		this.graph.addNode(node);
		
		return node;
	}

	_createDataNode(nodeData, index) {
		const typeMap = {
			'data_text': 'text', 'data_document': 'document', 'data_image': 'image',
			'data_audio': 'audio', 'data_video': 'video', 'data_model3d': 'model3d',
			'data_binary': 'binary', 'data': nodeData.data_type || 'binary'
		};
		const dataType = typeMap[nodeData.type] || 'binary';
		const capitalizedType = dataType.charAt(0).toUpperCase() + dataType.slice(1);
		let NodeClass = typeof DataNodeTypes !== 'undefined' ? DataNodeTypes[`Data.${capitalizedType}`] : null;
		if (!NodeClass) NodeClass = typeof DataNodeTypes !== 'undefined' ? DataNodeTypes['Data.Binary'] : null;
		if (!NodeClass) { console.error('Binary fallback node type not found'); return null; }

		const node = new NodeClass();

		node.sourceType = nodeData.source_type || 'none';
		if (nodeData.source_url) { node.sourceUrl = nodeData.source_url; node.sourceType = 'url'; }
		else if (nodeData.source_path) { node.sourceUrl = nodeData.source_path; node.sourceType = 'file'; node._sourcePath = nodeData.source_path; }
		else if (nodeData.source_data) {
			node.sourceData = nodeData.source_data;
			node.sourceType = (nodeData.source_type === 'inline' || (typeof nodeData.source_data === 'string' && !nodeData.source_data.startsWith('data:'))) ? 'inline' : 'file';
		}

		if (nodeData.source_meta) {
			node.sourceMeta = {
				filename: nodeData.source_meta.filename || '',
				mimeType: nodeData.source_meta.mime_type || '',
				size: nodeData.source_meta.size || 0,
				lastModified: nodeData.source_meta.last_modified || null
			};
		}

		if (dataType === 'text') {
			node.properties = node.properties || {};
			if (nodeData.encoding) node.properties.encoding = nodeData.encoding;
			if (nodeData.language) node.properties.language = nodeData.language;
		}
		if (dataType === 'image' && nodeData.dimensions) node.imageDimensions = { width: nodeData.dimensions.width, height: nodeData.dimensions.height };
		if (dataType === 'audio' && nodeData.duration) node.audioDuration = nodeData.duration;
		if (dataType === 'video') {
			if (nodeData.dimensions) node.videoDimensions = { width: nodeData.dimensions.width, height: nodeData.dimensions.height };
			if (nodeData.duration) node.videoDuration = nodeData.duration;
		}

		this._applyLayout(node, nodeData);
		node.isExpanded = nodeData.extra?.isExpanded || false;
		node.workflowIndex = index;
		
		// Use proper API - emits node:created
		this.graph.addNode(node);
		
		return node;
	}

	_createWorkflowNode(factory, nodeData, index, schemaName, typeMap) {
		if (!factory) { console.error('No factory available'); return null; }

		const modelName = this._resolveModelName(nodeData.type, schemaName, typeMap);
		if (!modelName) { console.error(`Model not found for type: ${nodeData.type}`); return null; }

		const node = factory.createNode(modelName, nodeData);
		if (!node) return null;

		if (nodeData.id) {
			node.workflowId = nodeData.id;
		}

		this._applyLayout(node, nodeData);
		node.workflowIndex = index;

		if (nodeData.extra) {
			node.extra = { ...nodeData.extra };
			// delete node.extra.pos; delete node.extra.size;
			if (nodeData.extra.title) node.title = nodeData.extra.title;
			if (nodeData.extra.color) node.color = nodeData.extra.color;
		}

		this._populateNodeFields(node, nodeData);
		
		// Use proper API - emits node:created
		this.graph.addNode(node);
		
		return node;
	}

	_applyLayout(node, nodeData) {
		if (this.importOptions?.includeLayout !== false) {
			if (nodeData.extra?.pos) node.pos = [...nodeData.extra.pos];
			if (nodeData.extra?.size) node.size = [...nodeData.extra.size];
		} else {
			node.pos = [0, 0];
		}
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

	_autoLayoutNodes(nodes) {
		const validNodes = nodes.filter(n => n);
		if (validNodes.length === 0) return;
		const cols = Math.ceil(Math.sqrt(validNodes.length));
		const spacingX = 280, spacingY = 200, startX = 100, startY = 100;
		for (let i = 0; i < validNodes.length; i++) {
			validNodes[i].pos = [startX + (i % cols) * spacingX, startY + Math.floor(i / cols) * spacingY];
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
		const sourceNode = createdNodes[source], targetNode = createdNodes[target];
		if (!sourceNode || !targetNode) return null;

		const sourceSlotIdx = this._findOutputSlot(sourceNode, source_slot);
		const targetSlotIdx = this._findInputSlot(targetNode, target_slot);
		if (sourceSlotIdx === -1 || targetSlotIdx === -1) return null;

		if (preview === true && typeof PreviewNode !== 'undefined') {
			return this._createEdgeWithPreview(sourceNode, sourceSlotIdx, source_slot, targetNode, targetSlotIdx, target_slot, edgeData);
		}
		return this._createStandardEdge(sourceNode, sourceSlotIdx, targetNode, targetSlotIdx, data, extra);
	}

	_findOutputSlot(node, slotName) {
		for (let i = 0; i < node.outputs.length; i++) if (node.outputs[i].name === slotName) return i;
		const idx = parseInt(slotName);
		if (!isNaN(idx) && idx >= 0 && idx < node.outputs.length) return idx;
		if ((node.isDataNode || node.isNative) && node.outputs.length > 0) return 0;
		return -1;
	}

	_findInputSlot(node, slotName) {
		for (let i = 0; i < node.inputs.length; i++) if (node.inputs[i].name === slotName) return i;
		const idx = parseInt(slotName);
		if (!isNaN(idx) && idx >= 0 && idx < node.inputs.length) return idx;
		if ((node.isDataNode || node.isNative) && node.inputs.length > 0) return 0;
		return -1;
	}

	_createStandardEdge(sourceNode, sourceSlotIdx, targetNode, targetSlotIdx, data, extra) {
		const linkType = sourceNode.outputs[sourceSlotIdx]?.type || 'Any';
		
		// Use proper API - emits link:created
		const link = this.graph.addLink(sourceNode.id, sourceSlotIdx, targetNode.id, targetSlotIdx, linkType);
		
		if (link) {
			if (data) link.data = JSON.parse(JSON.stringify(data));
			if (extra) link.extra = JSON.parse(JSON.stringify(extra));
		}
		
		return link;
	}

	_createEdgeWithPreview(sourceNode, sourceSlotIdx, sourceSlot, targetNode, targetSlotIdx, targetSlot, edgeData) {
		const midX = (sourceNode.pos[0] + sourceNode.size[0] + targetNode.pos[0]) / 2 - 110;
		const midY = (sourceNode.pos[1] + targetNode.pos[1]) / 2;
		const linkType = sourceNode.outputs[sourceSlotIdx]?.type || 'Any';

		const previewNode = new PreviewNode();
		previewNode.pos = [midX, midY];
		previewNode._originalEdgeInfo = {
			sourceNodeId: sourceNode.id, sourceSlotIdx, sourceSlotName: sourceSlot,
			targetNodeId: targetNode.id, targetSlotIdx, targetSlotName: targetSlot, linkType,
			data: edgeData.data ? JSON.parse(JSON.stringify(edgeData.data)) : null,
			extra: edgeData.extra ? JSON.parse(JSON.stringify(edgeData.extra)) : null
		};
		
		// Use proper API - emits node:created
		this.graph.addNode(previewNode);

		// Use proper API - emits link:created
		const link1 = this.graph.addLink(sourceNode.id, sourceSlotIdx, previewNode.id, 0, linkType);
		if (link1) link1.extra = { _isPreviewLink: true };

		// Use proper API - emits link:created
		const link2 = this.graph.addLink(previewNode.id, 0, targetNode.id, targetSlotIdx, linkType);
		if (link2) link2.extra = { _isPreviewLink: true };

		this.eventBus.emit('preview:inserted', { nodeId: previewNode.id });
		return { link1, link2, previewNode };
	}
}

// ========================================================================
// WorkflowExporter
// ========================================================================

class WorkflowExporter {
	constructor(graph) {
		this.graph = graph;
	}

	export(schemaName, workflowInfo = {}, options = {}) {
		this.exportOptions = {
			dataExportMode: options.dataExportMode || DataExportMode.REFERENCE,
			dataBasePath: options.dataBasePath || '',
			includeLayout: options.includeLayout !== false
		};

		const workflow = { ...JSON.parse(JSON.stringify(workflowInfo)), type: 'workflow', nodes: [], edges: [] };
		const exportableNodes = [], previewNodes = [];

		for (const node of this.graph.nodes) {
			if (node.isPreviewNode) previewNodes.push(node);
			else exportableNodes.push(node);
		}

		exportableNodes.sort((a, b) => {
			if (a.workflowIndex !== undefined && b.workflowIndex !== undefined) return a.workflowIndex - b.workflowIndex;
			return (a.id || 0) - (b.id || 0);
		});

		const nodeToIndex = new Map();
		for (let i = 0; i < exportableNodes.length; i++) {
			nodeToIndex.set(exportableNodes[i].id, i);
			workflow.nodes.push(this._exportNode(exportableNodes[i]));
		}

		const previewNodeIds = new Set(previewNodes.map(n => n.id));
		const processedLinks = new Set();

		for (const linkId in this.graph.links) {
			if (processedLinks.has(linkId)) continue;
			const link = this.graph.links[linkId];
			const sourceNode = this.graph.getNodeById(link.origin_id);
			const targetNode = this.graph.getNodeById(link.target_id);
			if (!sourceNode || !targetNode) continue;

			if (!previewNodeIds.has(sourceNode.id) && previewNodeIds.has(targetNode.id)) {
				const edge = this._tracePreviewChain(link, sourceNode, targetNode, nodeToIndex, processedLinks);
				if (edge) workflow.edges.push(edge);
				continue;
			}

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

	_exportDataNode(node) {
		const mode = this.exportOptions?.dataExportMode || DataExportMode.REFERENCE;
		const basePath = this.exportOptions?.dataBasePath || '';
		const typeMap = { 'text': 'data_text', 'document': 'data_document', 'image': 'data_image', 'audio': 'data_audio', 'video': 'data_video', 'model3d': 'data_model3d', 'binary': 'data_binary' };

		const nodeData = { type: typeMap[node.dataType] || 'data', source_type: node.sourceType || 'none' };
		if (!typeMap[node.dataType]) nodeData.data_type = node.dataType || null;

		if (node.sourceType === 'url') nodeData.source_url = node.sourceUrl || '';
		else if (node.sourceType === 'file') {
			if (mode === DataExportMode.EMBEDDED && node.sourceData) nodeData.source_data = node.sourceData;
			else nodeData.source_path = basePath + (node.sourceMeta?.filename || this._generateFilename(node));
		} else if (node.sourceType === 'inline') {
			if (mode === DataExportMode.EMBEDDED && node.sourceData) nodeData.source_data = node.sourceData;
			else if (node.dataType === 'text' && node.sourceData) nodeData.source_data = node.sourceData;
			else if (node.sourceData) nodeData.source_path = basePath + (node.sourceMeta?.filename || this._generateFilename(node));
		}

		if (node.sourceMeta && Object.keys(node.sourceMeta).length > 0) {
			nodeData.source_meta = { filename: node.sourceMeta.filename || null, mime_type: node.sourceMeta.mimeType || null, size: node.sourceMeta.size || null, last_modified: node.sourceMeta.lastModified || null };
			for (const k in nodeData.source_meta) if (nodeData.source_meta[k] === null) delete nodeData.source_meta[k];
			if (Object.keys(nodeData.source_meta).length === 0) delete nodeData.source_meta;
		}

		if (node.dataType === 'text') {
			if (node.properties?.encoding) nodeData.encoding = node.properties.encoding;
			if (node.properties?.language) nodeData.language = node.properties.language;
		}
		if (node.dataType === 'image' && node.imageDimensions?.width) nodeData.dimensions = { width: node.imageDimensions.width, height: node.imageDimensions.height };
		if (node.dataType === 'audio' && node.audioDuration) nodeData.duration = node.audioDuration;
		if (node.dataType === 'video') {
			if (node.videoDimensions?.width) nodeData.dimensions = { width: node.videoDimensions.width, height: node.videoDimensions.height };
			if (node.videoDuration) nodeData.duration = node.videoDuration;
		}

		nodeData.extra = {};
		if (this.exportOptions?.includeLayout !== false) { nodeData.extra.pos = [...node.pos]; nodeData.extra.size = [...node.size]; }
		if (node.isExpanded) nodeData.extra.isExpanded = true;
		if (Object.keys(nodeData.extra).length === 0) delete nodeData.extra;

		return nodeData;
	}

	_generateFilename(node) {
		const extMap = { 'text': '.txt', 'document': '.pdf', 'image': '.png', 'audio': '.mp3', 'video': '.mp4', 'model3d': '.glb', 'binary': '.bin' };
		return `${node.dataType}_${node.id || Date.now()}${extMap[node.dataType] || '.bin'}`;
	}

	_exportNativeNode(node) {
		const typeMap = { 'String': 'native_string', 'Integer': 'native_integer', 'Float': 'native_float', 'Boolean': 'native_boolean', 'List': 'native_list', 'Dict': 'native_dict' };
		const nativeType = node.title || 'String';
		let value = node.properties?.value;
		if (value === undefined) value = this._getDefaultNativeValue(nativeType);
		const nodeData = { type: typeMap[nativeType] || 'native_string', value };
		if (this.exportOptions?.includeLayout !== false) nodeData.extra = { pos: [...node.pos], size: [...node.size] };
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

	_exportWorkflowNode(node) {
		const nodeData = { type: node.workflowType || node.constantFields?.type || node.modelName?.toLowerCase() || 'unknown' };

		if (node.workflowId) {
			nodeData.id = node.workflowId;
		}

		if (node.constantFields) for (const key in node.constantFields) if (key !== 'type') nodeData[key] = node.constantFields[key];

		for (const [baseName, slotIndices] of Object.entries(node.multiInputSlots || {})) {
			const keys = slotIndices.map(idx => { const n = node.inputs[idx].name; const d = n.indexOf('.'); return d !== -1 ? n.substring(d + 1) : null; }).filter(Boolean);
			if (keys.length > 0) nodeData[baseName] = keys;
		}
		for (const [baseName, slotIndices] of Object.entries(node.multiOutputSlots || {})) {
			const keys = slotIndices.map(idx => { const n = node.outputs[idx].name; const d = n.indexOf('.'); return d !== -1 ? n.substring(d + 1) : null; }).filter(Boolean);
			if (keys.length > 0) nodeData[baseName] = keys;
		}

		for (let i = 0; i < node.inputs.length; i++) {
			const input = node.inputs[i];
			if (input.link) continue;
			const baseName = input.name.split('.')[0];
			if (node.multiInputSlots?.[baseName]) continue;
			if (node.nativeInputs?.[i] !== undefined) {
				const val = node.nativeInputs[i].value;
				if (val !== null && val !== undefined && val !== '') nodeData[input.name] = this._convertExportValue(val, node.nativeInputs[i].type);
			}
		}

		nodeData.extra = {};
		if (this.exportOptions?.includeLayout !== false) { nodeData.extra.pos = [...node.pos]; nodeData.extra.size = [...node.size]; }
		if (node.extra) { const { pos, size, ...rest } = node.extra; nodeData.extra = { ...nodeData.extra, ...rest }; }
		if (node.title !== `${node.schemaName}.${node.modelName}`) nodeData.extra.title = node.title;
		if (node.color) nodeData.extra.color = node.color;
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
			const outLink = this.graph.links[outLinks[0]];
			if (!outLink) return null;
			processedLinks.add(outLink.id);
			const nextNode = this.graph.getNodeById(outLink.target_id);
			if (!nextNode) return null;

			if (nextNode.isPreviewNode) currentPreviewNode = nextNode;
			else {
				const sourceIdx = nodeToIndex.get(sourceNode.id), targetIdx = nodeToIndex.get(nextNode.id);
				if (sourceIdx === undefined || targetIdx === undefined) return null;
				const edge = {
					type: 'edge', source: sourceIdx, target: targetIdx,
					source_slot: originalEdgeInfo.sourceSlotName || sourceNode.outputs[startLink.origin_slot]?.name || 'output',
					target_slot: originalEdgeInfo.targetSlotName || nextNode.inputs[outLink.target_slot]?.name || 'input',
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
		const sourceNode = this.graph.getNodeById(link.origin_id), targetNode = this.graph.getNodeById(link.target_id);
		if (!sourceNode || !targetNode) return null;
		const sourceIdx = nodeToIndex.get(link.origin_id), targetIdx = nodeToIndex.get(link.target_id);
		if (sourceIdx === undefined || targetIdx === undefined) return null;

		const edge = {
			type: 'edge', source: sourceIdx, target: targetIdx,
			source_slot: sourceNode.outputs[link.origin_slot]?.name || 'output',
			target_slot: targetNode.inputs[link.target_slot]?.name || 'input'
		};
		if (link.data && Object.keys(link.data).length > 0) edge.data = JSON.parse(JSON.stringify(link.data));
		if (link.extra && Object.keys(link.extra).length > 0) {
			const cleanExtra = JSON.parse(JSON.stringify(link.extra));
			delete cleanExtra._isPreviewLink;
			if (Object.keys(cleanExtra).length > 0) edge.extra = cleanExtra;
		}
		return edge;
	}

	_convertExportValue(val, type) {
		if ((type === 'dict' || type === 'list') && typeof val === 'string') {
			try { return JSON.parse(val); } catch { return val; }
		}
		return val;
	}

	getDataFiles(schemaName, options = {}) {
		const basePath = options.dataBasePath || '';
		const files = [];
		for (const node of this.graph.nodes) {
			if (!node.isDataNode) continue;
			if (node.sourceType !== 'file' && node.sourceType !== 'inline') continue;
			if (!node.sourceData) continue;
			if (node.sourceType === 'inline' && node.dataType === 'text') continue;
			files.push({
				path: basePath + (node.sourceMeta?.filename || this._generateFilename(node)),
				data: node.sourceData,
				mimeType: node.sourceMeta?.mimeType || 'application/octet-stream',
				nodeId: node.id
			});
		}
		return files;
	}
}

// ========================================================================
// WorkflowExtension - Integrates with extensions-core.js
// ========================================================================

class WorkflowExtension extends SchemaGraphExtension {
	constructor(app) {
		super(app);
		this.parser = new WorkflowSchemaParser();
	}

	_registerNodeTypes() {
		// WorkflowNode types are registered dynamically via registerWorkflowSchema
	}

	_setupEventListeners() {
		// Listen for schema registration to auto-detect workflow schemas
		this.on('schema:register', (e) => {
			if (e.code?.includes('FieldRole.')) {
				e.preventDefault?.();
				this.registerWorkflowSchema(e.name, e.code);
			}
		});
	}

	_extendAPI() {
		const self = this;
		
		this.app.api = this.app.api || {};
		this.app.api.workflow = {
			// Existing methods...
			registerSchema: (name, code) => self.registerWorkflowSchema(name, code),
			import: (data, schemaName, options) => self.importWorkflow(data, schemaName, options),
			export: (schemaName, workflowInfo, options) => self.exportWorkflow(schemaName, workflowInfo, options),
			download: (schemaName, workflowInfo, options) => self.downloadWorkflow(schemaName, workflowInfo, options),
			getDataFiles: (schemaName, options) => self.getDataFiles(schemaName, options),
			isWorkflowSchema: (name) => self.graph.schemas[name]?.isWorkflow === true,
			
			// === NEW: Node lookup methods ===
			
			// Find graph nodes by workflow type
			findNodesByType: (type) => self._findNodesByType(type),
			
			// Find first graph node by workflow type
			findNodeByType: (type) => self._findNodesByType(type)[0] || null,
			
			// Find graph nodes by schema and model name
			findNodesByModel: (schemaName, modelName) => self._findNodesByModel(schemaName, modelName),
			
			// Convert graph node to workflow node data
			toWorkflowNode: (nodeOrId) => self._toWorkflowNode(nodeOrId),
			
			// Get graph node from workflow index
			getNodeByWorkflowIndex: (index) => self._getNodeByWorkflowIndex(index),
			
			// Get all workflow nodes as array (matches export format)
			getWorkflowNodes: () => self._getWorkflowNodes(),
			
			// Get workflow node by index
			getWorkflowNodeByIndex: (index) => self._getWorkflowNodes()[index] || null,
			
			// Find workflow node data by type
			findWorkflowNodesByType: (type) => self._getWorkflowNodes().filter(n => n.type === type),
			
			// Get graph node ID from workflow index
			getGraphNodeIdByWorkflowIndex: (index) => {
				const node = self._getNodeByWorkflowIndex(index);
				return node?.id || null;
			},
			
			// Get workflow index from graph node
			getWorkflowIndex: (nodeOrId) => {
				const node = typeof nodeOrId === 'object' ? nodeOrId : self.graph.getNodeById(nodeOrId);
				return node?.workflowIndex ?? null;
			},

			// === Multi-slot management ===
			
			// Add a sub-slot to a multi-input field
			addMultiInputSlot: (nodeOrId, fieldName, key) => {
				return self._addMultiSlot(nodeOrId, fieldName, key, 'input');
			},
			
			// Remove a sub-slot from a multi-input field
			removeMultiInputSlot: (nodeOrId, fieldName, key) => {
				return self._removeMultiSlot(nodeOrId, fieldName, key, 'input');
			},
			
			// Add a sub-slot to a multi-output field
			addMultiOutputSlot: (nodeOrId, fieldName, key) => {
				return self._addMultiSlot(nodeOrId, fieldName, key, 'output');
			},
			
			// Remove a sub-slot from a multi-output field
			removeMultiOutputSlot: (nodeOrId, fieldName, key) => {
				return self._removeMultiSlot(nodeOrId, fieldName, key, 'output');
			},
			
			// Get current keys for a multi-input field
			getMultiInputKeys: (nodeOrId, fieldName) => {
				return self._getMultiSlotKeys(nodeOrId, fieldName, 'input');
			},
			
			// Get current keys for a multi-output field
			getMultiOutputKeys: (nodeOrId, fieldName) => {
				return self._getMultiSlotKeys(nodeOrId, fieldName, 'output');
			},
			
			// Set all keys for a multi-input field (replaces existing)
			setMultiInputKeys: (nodeOrId, fieldName, keys) => {
				return self._setMultiSlotKeys(nodeOrId, fieldName, keys, 'input');
			},
			
			// Set all keys for a multi-output field (replaces existing)
			setMultiOutputKeys: (nodeOrId, fieldName, keys) => {
				return self._setMultiSlotKeys(nodeOrId, fieldName, keys, 'output');
			},
			
			// Rename a sub-slot key
			renameMultiInputSlot: (nodeOrId, fieldName, oldKey, newKey) => {
				return self._renameMultiSlot(nodeOrId, fieldName, oldKey, newKey, 'input');
			},
			
			renameMultiOutputSlot: (nodeOrId, fieldName, oldKey, newKey) => {
				return self._renameMultiSlot(nodeOrId, fieldName, oldKey, newKey, 'output');
			},
			
			// Get multi-field info for a node
			getMultiFields: (nodeOrId) => {
				return self._getMultiFields(nodeOrId);
			}
		};
		
		this.app.workflowManager = this;
	}

	// === Implementation methods ===

	_findNodesByType(type) {
		return this.graph.nodes.filter(node => {
			if (!node.isWorkflowNode) return false;
			const nodeType = node.workflowType || node.constantFields?.type || node.modelName?.toLowerCase();
			return nodeType === type;
		});
	}

	_findNodesByModel(schemaName, modelName) {
		return this.graph.nodes.filter(node => {
			return node.schemaName === schemaName && node.modelName === modelName;
		});
	}

	_getNodeByWorkflowIndex(index) {
		return this.graph.nodes.find(node => node.workflowIndex === index) || null;
	}

	_toWorkflowNode(nodeOrId) {
		const node = typeof nodeOrId === 'object' ? nodeOrId : this.graph.getNodeById(nodeOrId);
		if (!node) return null;
		
		// Handle different node types
		if (node.isDataNode) {
			return this._toWorkflowDataNode(node);
		}
		if (node.isNative) {
			return this._toWorkflowNativeNode(node);
		}
		if (node.isWorkflowNode) {
			return this._toWorkflowSchemaNode(node);
		}
		
		// Generic node
		return {
			type: node.type || node.title || 'unknown',
			id: node.id,
			index: node.workflowIndex
		};
	}

	_toWorkflowSchemaNode(node) {
		const workflowNode = {
			type: node.workflowType || node.constantFields?.type || node.modelName?.toLowerCase() || 'unknown',
			_graphId: node.id,
			_index: node.workflowIndex
		};
		
		// Add constant fields (except type which is already set)
		if (node.constantFields) {
			for (const key in node.constantFields) {
				if (key !== 'type') {
					workflowNode[key] = node.constantFields[key];
				}
			}
		}
		
		// Add multi-input slot keys
		for (const [baseName, slotIndices] of Object.entries(node.multiInputSlots || {})) {
			const keys = slotIndices.map(idx => {
				const name = node.inputs[idx].name;
				const dotIdx = name.indexOf('.');
				return dotIdx !== -1 ? name.substring(dotIdx + 1) : null;
			}).filter(Boolean);
			if (keys.length > 0) workflowNode[baseName] = keys;
		}
		
		// Add multi-output slot keys
		for (const [baseName, slotIndices] of Object.entries(node.multiOutputSlots || {})) {
			const keys = slotIndices.map(idx => {
				const name = node.outputs[idx].name;
				const dotIdx = name.indexOf('.');
				return dotIdx !== -1 ? name.substring(dotIdx + 1) : null;
			}).filter(Boolean);
			if (keys.length > 0) workflowNode[baseName] = keys;
		}
		
		// Add input values (both native and connected)
		for (let i = 0; i < node.inputs.length; i++) {
			const input = node.inputs[i];
			const baseName = input.name.split('.')[0];
			
			// Skip multi-input base names (already handled above)
			if (node.multiInputSlots?.[baseName]) continue;
			
			// Check for connected data first
			if (input.link) {
				const connectedData = node.getInputData(i);
				if (connectedData !== undefined && connectedData !== null) {
					workflowNode[input.name] = connectedData;
				}
			} 
			// Then check native input value
			else if (node.nativeInputs?.[i] !== undefined) {
				const nativeInput = node.nativeInputs[i];
				const val = nativeInput.value;
				if (val !== null && val !== undefined && val !== '') {
					workflowNode[input.name] = this._convertNativeValue(val, nativeInput.type);
				}
			}
		}
		
		return workflowNode;
	}

	_toWorkflowDataNode(node) {
		const typeMap = {
			'text': 'data_text',
			'document': 'data_document',
			'image': 'data_image',
			'audio': 'data_audio',
			'video': 'data_video',
			'model3d': 'data_model3d',
			'binary': 'data_binary'
		};
		
		const workflowNode = {
			type: typeMap[node.dataType] || 'data',
			source_type: node.sourceType || 'none',
			_graphId: node.id,
			_index: node.workflowIndex
		};
		
		if (node.sourceType === 'url') {
			workflowNode.source_url = node.sourceUrl || '';
		} else if (node.sourceType === 'file' || node.sourceType === 'inline') {
			if (node.sourceData) {
				workflowNode.source_data = node.sourceData;
			}
		}
		
		if (node.sourceMeta) {
			workflowNode.source_meta = {
				filename: node.sourceMeta.filename || null,
				mime_type: node.sourceMeta.mimeType || null,
				size: node.sourceMeta.size || null
			};
		}
		
		return workflowNode;
	}

	_toWorkflowNativeNode(node) {
		const typeMap = {
			'String': 'native_string',
			'Integer': 'native_integer',
			'Float': 'native_float',
			'Boolean': 'native_boolean',
			'List': 'native_list',
			'Dict': 'native_dict'
		};
		
		return {
			type: typeMap[node.title] || 'native_string',
			value: node.properties?.value,
			_graphId: node.id,
			_index: node.workflowIndex
		};
	}

	_getWorkflowNodes() {
		// Get all exportable nodes sorted by workflow index
		const nodes = this.graph.nodes
			.filter(n => !n.isPreviewNode)
			.sort((a, b) => {
				if (a.workflowIndex !== undefined && b.workflowIndex !== undefined) {
					return a.workflowIndex - b.workflowIndex;
				}
				return (a.id || 0) - (b.id || 0);
			});
		
		return nodes.map(node => this._toWorkflowNode(node));
	}

	_convertNativeValue(val, type) {
		if (val === null || val === undefined) return val;
		if ((type === 'dict' || type === 'list') && typeof val === 'string') {
			try { return JSON.parse(val); } catch { return val; }
		}
		return val;
	}

	// === Multi-slot implementation ===

	_getNode(nodeOrId) {
		return typeof nodeOrId === 'object' ? nodeOrId : this.graph.getNodeById(nodeOrId);
	}

	_getMultiFields(nodeOrId) {
		const node = this._getNode(nodeOrId);
		if (!node) return null;
		
		const result = {
			inputs: {},
			outputs: {}
		};
		
		for (const [fieldName, slotIndices] of Object.entries(node.multiInputSlots || {})) {
			result.inputs[fieldName] = slotIndices.map(idx => {
				const name = node.inputs[idx]?.name || '';
				const dotIdx = name.indexOf('.');
				return dotIdx !== -1 ? name.substring(dotIdx + 1) : name;
			});
		}
		
		for (const [fieldName, slotIndices] of Object.entries(node.multiOutputSlots || {})) {
			result.outputs[fieldName] = slotIndices.map(idx => {
				const name = node.outputs[idx]?.name || '';
				const dotIdx = name.indexOf('.');
				return dotIdx !== -1 ? name.substring(dotIdx + 1) : name;
			});
		}
		
		return result;
	}

	_getMultiSlotKeys(nodeOrId, fieldName, type) {
		const node = this._getNode(nodeOrId);
		if (!node) return [];
		
		const slotsMap = type === 'input' ? node.multiInputSlots : node.multiOutputSlots;
		const slots = type === 'input' ? node.inputs : node.outputs;
		const slotIndices = slotsMap?.[fieldName];
		
		if (!slotIndices) return [];
		
		return slotIndices.map(idx => {
			const name = slots[idx]?.name || '';
			const dotIdx = name.indexOf('.');
			return dotIdx !== -1 ? name.substring(dotIdx + 1) : name;
		});
	}

	_addMultiSlot(nodeOrId, fieldName, key, type) {
		const node = this._getNode(nodeOrId);
		if (!node) return false;
		
		const slotsMap = type === 'input' ? node.multiInputSlots : node.multiOutputSlots;
		const slots = type === 'input' ? node.inputs : node.outputs;
		
		if (!slotsMap?.[fieldName]) {
			console.warn(`[Workflow] Field "${fieldName}" is not a multi-${type} field`);
			return false;
		}
		
		// Check if key already exists
		const existingKeys = this._getMultiSlotKeys(node, fieldName, type);
		if (existingKeys.includes(key)) {
			console.warn(`[Workflow] Key "${key}" already exists in ${fieldName}`);
			return false;
		}
		
		// Get the type from existing slots or schema
		const existingSlotIdx = slotsMap[fieldName][0];
		const existingSlot = slots[existingSlotIdx];
		const slotType = existingSlot?.type || 'Any';
		
		// Find insertion position (after last slot of this field)
		const lastIdx = Math.max(...slotsMap[fieldName]);
		const insertIdx = lastIdx + 1;
		
		// Create new slot
		const slotName = `${fieldName}.${key}`;
		const newSlot = {
			name: slotName,
			type: slotType,
			link: null,
			links: type === 'output' ? [] : undefined
		};
		
		if (type === 'output') {
			newSlot.links = [];
			delete newSlot.link;
		}
		
		// Insert slot at correct position
		slots.splice(insertIdx, 0, newSlot);
		
		// Update slot indices for this field
		slotsMap[fieldName].push(insertIdx);
		
		// Update indices for other multi-fields that come after
		this._adjustSlotIndicesAfterInsert(node, insertIdx, type);
		
		// Update native inputs if applicable
		if (type === 'input' && node.nativeInputs) {
			this._adjustNativeInputsAfterInsert(node, insertIdx);
		}
		
		// Update link references
		this._adjustLinkIndicesAfterInsert(node, insertIdx, type);
		
		// Resize node
		this._resizeNode(node);
		
		// Emit event
		this.eventBus.emit('node:slotAdded', {
			nodeId: node.id,
			fieldName,
			key,
			type,
			slotIndex: insertIdx
		});
		
		this.app.draw?.();
		return true;
	}

	_removeMultiSlot(nodeOrId, fieldName, key, type) {
		const node = this._getNode(nodeOrId);
		if (!node) return false;
		
		const slotsMap = type === 'input' ? node.multiInputSlots : node.multiOutputSlots;
		const slots = type === 'input' ? node.inputs : node.outputs;
		
		if (!slotsMap?.[fieldName]) {
			console.warn(`[Workflow] Field "${fieldName}" is not a multi-${type} field`);
			return false;
		}
		
		// Find the slot index for this key
		const slotName = `${fieldName}.${key}`;
		const slotIdx = slotsMap[fieldName].find(idx => slots[idx]?.name === slotName);
		
		if (slotIdx === undefined) {
			console.warn(`[Workflow] Key "${key}" not found in ${fieldName}`);
			return false;
		}
		
		// Don't allow removing last slot
		if (slotsMap[fieldName].length <= 1) {
			console.warn(`[Workflow] Cannot remove last slot of ${fieldName}`);
			return false;
		}
		
		// Disconnect any links to this slot
		this._disconnectSlot(node, slotIdx, type);
		
		// Remove from slots array
		slots.splice(slotIdx, 1);
		
		// Remove from field's slot indices
		const fieldIdxPos = slotsMap[fieldName].indexOf(slotIdx);
		slotsMap[fieldName].splice(fieldIdxPos, 1);
		
		// Update indices for this field (slots after removed one shift down)
		slotsMap[fieldName] = slotsMap[fieldName].map(idx => idx > slotIdx ? idx - 1 : idx);
		
		// Update indices for other multi-fields
		this._adjustSlotIndicesAfterRemove(node, slotIdx, type);
		
		// Update native inputs
		if (type === 'input' && node.nativeInputs) {
			this._adjustNativeInputsAfterRemove(node, slotIdx);
		}
		
		// Update link references
		this._adjustLinkIndicesAfterRemove(node, slotIdx, type);
		
		// Resize node
		this._resizeNode(node);
		
		// Emit event
		this.eventBus.emit('node:slotRemoved', {
			nodeId: node.id,
			fieldName,
			key,
			type
		});
		
		this.app.draw?.();
		return true;
	}

	_setMultiSlotKeys(nodeOrId, fieldName, keys, type) {
		const node = this._getNode(nodeOrId);
		if (!node) return false;
		
		const slotsMap = type === 'input' ? node.multiInputSlots : node.multiOutputSlots;
		
		if (!slotsMap?.[fieldName]) {
			console.warn(`[Workflow] Field "${fieldName}" is not a multi-${type} field`);
			return false;
		}
		
		if (!Array.isArray(keys) || keys.length === 0) {
			console.warn(`[Workflow] Keys must be a non-empty array`);
			return false;
		}
		
		const currentKeys = this._getMultiSlotKeys(node, fieldName, type);
		
		// Remove keys that are no longer needed
		for (const key of currentKeys) {
			if (!keys.includes(key)) {
				this._removeMultiSlot(node, fieldName, key, type);
			}
		}
		
		// Add new keys
		for (const key of keys) {
			if (!currentKeys.includes(key)) {
				this._addMultiSlot(node, fieldName, key, type);
			}
		}
		
		// Reorder to match requested order
		this._reorderMultiSlots(node, fieldName, keys, type);
		
		return true;
	}

	_renameMultiSlot(nodeOrId, fieldName, oldKey, newKey, type) {
		const node = this._getNode(nodeOrId);
		if (!node) return false;
		
		const slotsMap = type === 'input' ? node.multiInputSlots : node.multiOutputSlots;
		const slots = type === 'input' ? node.inputs : node.outputs;
		
		if (!slotsMap?.[fieldName]) {
			console.warn(`[Workflow] Field "${fieldName}" is not a multi-${type} field`);
			return false;
		}
		
		const oldSlotName = `${fieldName}.${oldKey}`;
		const newSlotName = `${fieldName}.${newKey}`;
		
		// Find the slot
		const slotIdx = slotsMap[fieldName].find(idx => slots[idx]?.name === oldSlotName);
		
		if (slotIdx === undefined) {
			console.warn(`[Workflow] Key "${oldKey}" not found in ${fieldName}`);
			return false;
		}
		
		// Check new key doesn't exist
		const existingKeys = this._getMultiSlotKeys(node, fieldName, type);
		if (existingKeys.includes(newKey)) {
			console.warn(`[Workflow] Key "${newKey}" already exists in ${fieldName}`);
			return false;
		}
		
		// Rename
		slots[slotIdx].name = newSlotName;
		
		this.eventBus.emit('node:slotRenamed', {
			nodeId: node.id,
			fieldName,
			oldKey,
			newKey,
			type
		});
		
		this.app.draw?.();
		return true;
	}

	_disconnectSlot(node, slotIdx, type) {
		if (type === 'input') {
			const linkId = node.inputs[slotIdx]?.link;
			if (linkId) {
				this.graph.removeLink(linkId);
			}
		} else {
			const linkIds = node.outputs[slotIdx]?.links || [];
			for (const linkId of [...linkIds]) {
				this.graph.removeLink(linkId);
			}
		}
	}

	_adjustSlotIndicesAfterInsert(node, insertIdx, type) {
		const slotsMap = type === 'input' ? node.multiInputSlots : node.multiOutputSlots;
		
		for (const [fieldName, indices] of Object.entries(slotsMap)) {
			slotsMap[fieldName] = indices.map(idx => idx >= insertIdx && idx !== insertIdx ? idx + 1 : idx);
		}
	}

	_adjustSlotIndicesAfterRemove(node, removeIdx, type) {
		const slotsMap = type === 'input' ? node.multiInputSlots : node.multiOutputSlots;
		
		for (const [fieldName, indices] of Object.entries(slotsMap)) {
			slotsMap[fieldName] = indices.map(idx => idx > removeIdx ? idx - 1 : idx);
		}
	}

	_adjustNativeInputsAfterInsert(node, insertIdx) {
		const newNativeInputs = {};
		for (const [idx, value] of Object.entries(node.nativeInputs)) {
			const numIdx = parseInt(idx);
			if (numIdx >= insertIdx) {
				newNativeInputs[numIdx + 1] = value;
			} else {
				newNativeInputs[numIdx] = value;
			}
		}
		node.nativeInputs = newNativeInputs;
	}

	_adjustNativeInputsAfterRemove(node, removeIdx) {
		const newNativeInputs = {};
		for (const [idx, value] of Object.entries(node.nativeInputs)) {
			const numIdx = parseInt(idx);
			if (numIdx === removeIdx) {
				continue; // Skip removed
			} else if (numIdx > removeIdx) {
				newNativeInputs[numIdx - 1] = value;
			} else {
				newNativeInputs[numIdx] = value;
			}
		}
		node.nativeInputs = newNativeInputs;
	}

	_adjustLinkIndicesAfterInsert(node, insertIdx, type) {
		// Update all links that reference slots after insertIdx
		for (const linkId in this.graph.links) {
			const link = this.graph.links[linkId];
			
			if (type === 'input' && link.target_id === node.id) {
				if (link.target_slot >= insertIdx) {
					link.target_slot++;
				}
			} else if (type === 'output' && link.origin_id === node.id) {
				if (link.origin_slot >= insertIdx) {
					link.origin_slot++;
				}
			}
		}
	}

	_adjustLinkIndicesAfterRemove(node, removeIdx, type) {
		for (const linkId in this.graph.links) {
			const link = this.graph.links[linkId];
			
			if (type === 'input' && link.target_id === node.id) {
				if (link.target_slot > removeIdx) {
					link.target_slot--;
				}
			} else if (type === 'output' && link.origin_id === node.id) {
				if (link.origin_slot > removeIdx) {
					link.origin_slot--;
				}
			}
		}
	}

	_reorderMultiSlots(node, fieldName, keys, type) {
		// TODO: Implement slot reordering if needed
		// This is complex as it requires careful link and index management
	}

	_resizeNode(node) {
		const maxSlots = Math.max(node.inputs?.length || 0, node.outputs?.length || 0, 1);
		const minHeight = Math.max(80, 35 + maxSlots * 25);
		
		if (node.size[1] < minHeight) {
			node.size[1] = minHeight;
		}
		
		if (node.minSize) {
			node.minSize[1] = Math.max(node.minSize[1], minHeight);
		}
	}

	registerWorkflowSchema(schemaName, schemaCode) {
		try {
			const parsed = this.parser.parse(schemaCode);

			this.graph.schemas[schemaName] = {
				code: schemaCode,
				parsed: parsed.models,
				isWorkflow: true,
				fieldRoles: parsed.fieldRoles,
				defaults: parsed.defaults
			};

			if (!this.graph.nodeTypes) this.graph.nodeTypes = {};

			const self = this;
			for (const modelName in parsed.models) {
				const defaults = parsed.defaults[modelName] || {};
				if (!defaults.type) continue;

				const fullTypeName = `${schemaName}.${modelName}`;
				const capturedModelName = modelName;
				const capturedSchemaName = schemaName;
				const capturedFields = parsed.models[modelName];
				const capturedRoles = parsed.fieldRoles[modelName];
				const capturedDefaults = defaults;

				function WorkflowNodeType() {
					const factory = new WorkflowNodeFactory(self.graph, {
						models: { [capturedModelName]: capturedFields },
						fieldRoles: { [capturedModelName]: capturedRoles },
						defaults: { [capturedModelName]: capturedDefaults }
					}, capturedSchemaName);
					const node = factory.createNode(capturedModelName, {});
					Object.assign(this, node);
					Object.setPrototypeOf(this, node);
				}

				WorkflowNodeType.title = modelName.replace(/([A-Z])/g, ' $1').trim();
				WorkflowNodeType.type = fullTypeName;
				this.graph.nodeTypes[fullTypeName] = WorkflowNodeType;
			}

			this.graph.enabledSchemas.add(schemaName);
			this.eventBus.emit('schema:registered', { schemaName, isWorkflow: true });
			return true;
		} catch (e) {
			console.error('Workflow schema registration error:', e);
			this.eventBus.emit('error', { type: 'schema:register', error: e.message });
			return false;
		}
	}

	importWorkflow(workflowData, schemaName, options = {}) {
		try {
			const importer = new WorkflowImporter(this.graph, this.eventBus);
			importer.import(workflowData, schemaName, this.graph.schemas[schemaName], options);
			this.app.ui?.update?.schemaList?.();
			this.app.ui?.update?.nodeTypesList?.();
			this.app.draw?.();
			// this.app.centerView?.();
			return true;
		} catch (e) {
			this.app.showError?.('Workflow import failed: ' + e.message);
			return false;
		}
	}

	exportWorkflow(schemaName, workflowInfo = {}, options = {}) {
		const exporter = new WorkflowExporter(this.graph);
		return exporter.export(schemaName, workflowInfo, options);
	}

	downloadWorkflow(schemaName, workflowInfo = {}, options = {}) {
		const workflow = this.exportWorkflow(schemaName, workflowInfo, options);
		const jsonString = JSON.stringify(workflow, null, '\t');
		const blob = new Blob([jsonString], { type: 'application/json' });
		const url = URL.createObjectURL(blob);
		const a = document.createElement('a');
		a.href = url;
		a.download = options.filename || `workflow-${new Date().toISOString().slice(0, 10)}.json`;
		document.body.appendChild(a);
		a.click();
		document.body.removeChild(a);
		URL.revokeObjectURL(url);
		this.eventBus.emit('workflow:exported', {});
	}

	getDataFiles(schemaName, options = {}) {
		const exporter = new WorkflowExporter(this.graph);
		return exporter.getDataFiles(schemaName, options);
	}
}

// ========================================================================
// FALLBACK: Direct prototype extension (if extensions-core not available)
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
		const parser = new WorkflowSchemaParser();
		try {
			const parsed = parser.parse(schemaCode);
			this.schemas[schemaName] = {
				code: schemaCode,
				parsed: parsed.models,
				isWorkflow: true,
				fieldRoles: parsed.fieldRoles,
				defaults: parsed.defaults
			};

			if (!this.nodeTypes) this.nodeTypes = {};
			const self = this;

			for (const modelName in parsed.models) {
				const defaults = parsed.defaults[modelName] || {};
				if (!defaults.type) continue;

				const fullTypeName = `${schemaName}.${modelName}`;
				const capturedModelName = modelName;
				const capturedSchemaName = schemaName;
				const capturedFields = parsed.models[modelName];
				const capturedRoles = parsed.fieldRoles[modelName];
				const capturedDefaults = defaults;

				function WorkflowNodeType() {
					const factory = new WorkflowNodeFactory(self, {
						models: { [capturedModelName]: capturedFields },
						fieldRoles: { [capturedModelName]: capturedRoles },
						defaults: { [capturedModelName]: capturedDefaults }
					}, capturedSchemaName);
					const node = factory.createNode(capturedModelName, {});
					Object.assign(this, node);
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

	SchemaGraphClass.prototype.importWorkflow = function(workflowData, schemaName, options) {
		const importer = new WorkflowImporter(this, this.eventBus);
		return importer.import(workflowData, schemaName, this.schemas[schemaName], options);
	};

	SchemaGraphClass.prototype.exportWorkflow = function(schemaName, workflowInfo = {}, options = {}) {
		const exporter = new WorkflowExporter(this);
		return exporter.export(schemaName, workflowInfo, options);
	};

	SchemaGraphClass.prototype.isWorkflowSchema = function(schemaName) {
		return this.schemas[schemaName]?.isWorkflow === true;
	};
}

function extendSchemaGraphAppWithWorkflow(SchemaGraphAppClass) {
	const originalCreateAPI = SchemaGraphAppClass.prototype._createAPI;

	SchemaGraphAppClass.prototype._createAPI = function() {
		const api = originalCreateAPI ? originalCreateAPI.call(this) : {};

		api.workflow = {
			registerSchema: (name, code) => this.graph.registerWorkflowSchema(name, code),
			import: (data, schemaName, options) => {
				try {
					this.graph.importWorkflow(data, schemaName, options);
					this.ui?.update?.schemaList?.();
					this.ui?.update?.nodeTypesList?.();
					this.draw?.();
					this.centerView?.();
					return true;
				} catch (e) {
					this.showError?.('Workflow import failed: ' + e.message);
					return false;
				}
			},
			export: (schemaName, workflowInfo, options) => this.graph.exportWorkflow(schemaName, workflowInfo, options),
			download: (schemaName, workflowInfo = {}, options = {}) => {
				const workflow = this.graph.exportWorkflow(schemaName, workflowInfo, options);
				const jsonString = JSON.stringify(workflow, null, '\t');
				const blob = new Blob([jsonString], { type: 'application/json' });
				const url = URL.createObjectURL(blob);
				const a = document.createElement('a');
				a.href = url;
				a.download = options.filename || `workflow-${new Date().toISOString().slice(0, 10)}.json`;
				document.body.appendChild(a);
				a.click();
				document.body.removeChild(a);
				URL.revokeObjectURL(url);
				this.eventBus.emit('workflow:exported', {});
			},
			isWorkflowSchema: (name) => this.graph.isWorkflowSchema(name)
		};

		return api;
	};
}

// ========================================================================
// AUTO-INITIALIZATION
// ========================================================================

if (typeof SchemaGraphApp !== 'undefined') {
	extendSchemaGraphWithWorkflow(SchemaGraph);
	extendSchemaGraphAppWithWorkflow(SchemaGraphApp);
	
	// Register with extension system if available
	if (typeof extensionRegistry !== 'undefined') {
		extensionRegistry.register('workflow', WorkflowExtension);
	} else {
		// Fallback: hook into setupEventListeners directly
		const originalSetup = SchemaGraphApp.prototype.setupEventListeners;
		SchemaGraphApp.prototype.setupEventListeners = function() {
			originalSetup.call(this);
			this.workflowManager = new WorkflowExtension(this);
		};
	}
	
	console.log('✨ SchemaGraph Workflow extension loaded');
}

// ========================================================================
// EXPORTS
// ========================================================================

if (typeof module !== 'undefined' && module.exports) {
	module.exports = {
		FieldRole, DataExportMode, WorkflowNode, WorkflowSchemaParser,
		WorkflowNodeFactory, WorkflowImporter, WorkflowExporter, WorkflowExtension,
		extendSchemaGraphWithWorkflow, extendSchemaGraphAppWithWorkflow
	};
}

// Global exports for browser
if (typeof window !== 'undefined') {
	window.FieldRole = FieldRole;
	window.DataExportMode = DataExportMode;
	window.WorkflowNode = WorkflowNode;
	window.WorkflowSchemaParser = WorkflowSchemaParser;
	window.WorkflowNodeFactory = WorkflowNodeFactory;
	window.WorkflowImporter = WorkflowImporter;
	window.WorkflowExporter = WorkflowExporter;
	window.WorkflowExtension = WorkflowExtension;
}
