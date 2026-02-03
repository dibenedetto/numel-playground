// ========================================================================
// SCHEMAGRAPH WORKFLOW
// WorkflowNode, Schema Parser, Factory, Importer, Exporter
// Depends on: schemagraph-core.js
// ========================================================================

console.log('[SchemaGraph] Loading workflow module...');

// ========================================================================
// WORKFLOW NODE CLASS
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
			const fieldName = input.name.split('.')[0];
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
// WORKFLOW SCHEMA PARSER
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

		// Pre-process: join multi-line Field() definitions
		code = this._joinMultiLineFields(code);

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
						isProperty: true,
						title: null,
						description: null
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
						rawType: fieldData.type,
						title: fieldData.title,
						description: fieldData.description
					});
					currentRoles[fieldData.name] = fieldData.role;
					if (fieldData.default !== undefined) currentDefaults[fieldData.name] = fieldData.default;
				}
			}
		}
		this._saveRawModel(currentModel, currentParent, currentFields, currentRoles, currentDefaults);
		for (const modelName in this.rawModels) this._resolveInheritance(modelName);
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
					mergedFields.push({
						name: field.name,
						displayName: field.displayName || field.name,
						type: field.type,
						rawType: field.rawType,
						title: field.title,
						description: field.description,
						isProperty: field.isProperty
					});
					seenFields.add(field.name);
				}
				mergedRoles[field.name] = roles[field.name];
				if (defaults[field.name] !== undefined) mergedDefaults[field.name] = defaults[field.name];
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
				if (!/^[A-Z_]+$/.test(name) && !name.startsWith('DEFAULT_')) aliases[name] = value;
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
			if (constMatch) constants[constMatch[1]] = this._parseConstantValue(constMatch[2].trim());
		}
		return constants;
	}

	_joinMultiLineFields(code) {
		const lines = code.split('\n');
		const result = [];
		let buffer = '';
		let parenDepth = 0;
		let bracketDepth = 0;

		for (const line of lines) {
			const trimmed = line.trim();

			// Count opening/closing parens and brackets
			for (const char of trimmed) {
				if (char === '(') parenDepth++;
				else if (char === ')') parenDepth--;
				else if (char === '[') bracketDepth++;
				else if (char === ']') bracketDepth--;
			}

			if (buffer) {
				// Continue accumulating
				buffer += ' ' + trimmed;
				if (parenDepth === 0 && bracketDepth === 0) {
					result.push(buffer);
					buffer = '';
				}
			} else if ((parenDepth > 0 || bracketDepth > 0) && trimmed.includes(':')) {
				// Start of multi-line field
				buffer = line;
			} else {
				result.push(line);
			}
		}

		if (buffer) result.push(buffer);
		return result.join('\n');
	}

	_parseConstantValue(valStr) {
		if (!valStr) return undefined;
		valStr = valStr.trim();
		if (valStr === 'None') return null;
		if (valStr === 'True') return true;
		if (valStr === 'False') return false;
		if ((valStr.startsWith('"') && valStr.endsWith('"')) || (valStr.startsWith("'") && valStr.endsWith("'")))
			return valStr.slice(1, -1);
		const num = parseFloat(valStr);
		if (!isNaN(num) && valStr.match(/^-?\d+\.?\d*$/)) return num;
		if (valStr === '[]') return '[]';
		if (valStr === '{}') return '{}';
		return valStr;
	}

	_resolveTypeAlias(typeStr) {
		if (!typeStr || !this.typeAliases) return typeStr;
		if (this.typeAliases[typeStr]) return this.typeAliases[typeStr];
		for (const [alias, resolved] of Object.entries(this.typeAliases)) {
			if (typeStr.includes(alias))
				typeStr = typeStr.replace(new RegExp(`\\b${alias}\\b`, 'g'), resolved);
		}
		return typeStr;
	}

	_parseFieldLine(line) {
		const fieldStart = line.match(/^(\w+)\s*:\s*/);
		if (!fieldStart) return null;
		const name = fieldStart[1];
		if (name.startsWith('_')) return null;
		const afterColon = line.substring(fieldStart[0].length);

		const fieldMeta = this._extractFieldMetadata(afterColon);

		if (afterColon.startsWith('Annotated[')) {
			const annotatedContent = this._extractBracketContent(afterColon, 10);
			const roleMatch = annotatedContent.match(/\s*,\s*FieldRole\.(\w+)\s*$/);
			if (!roleMatch) return null;
			const role = roleMatch[1].toLowerCase();
			const typeStr = annotatedContent.substring(0, roleMatch.index).trim();
			const resolvedType = this._resolveTypeAlias(typeStr);
			const afterAnnotated = afterColon.substring(10 + annotatedContent.length + 1);

			const defaultMatch = afterAnnotated.match(/^\s*=\s*(.+)$/);
			let defaultVal = fieldMeta.default;

			if (defaultVal === undefined && defaultMatch) {
				const assignedValue = defaultMatch[1].trim();
				if (!assignedValue.startsWith('Field(')) {
					defaultVal = this._parseDefaultValue(assignedValue);
				}
			}

			return {
				name,
				type: resolvedType,
				role,
				default: defaultVal,
				title: fieldMeta.title,
				description: fieldMeta.description
			};
		}

		const simpleMatch = afterColon.match(/^([^=]+?)(?:\s*=\s*(.+))?$/);
		if (simpleMatch) {
			const [, type, assignedValue] = simpleMatch;

			let defaultVal = fieldMeta.default;
			if (defaultVal === undefined && assignedValue) {
				const trimmedAssigned = assignedValue.trim();
				if (!trimmedAssigned.startsWith('Field(')) {
					defaultVal = this._parseDefaultValue(trimmedAssigned);
				}
			}

			return {
				name,
				type: this._resolveTypeAlias(type.trim()),
				role: FieldRole.INPUT,
				default: defaultVal,
				title: fieldMeta.title,
				description: fieldMeta.description
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
		if ((valStr.startsWith('"') && valStr.endsWith('"')) || (valStr.startsWith("'") && valStr.endsWith("'")))
			return valStr.slice(1, -1);
		const num = parseFloat(valStr);
		if (!isNaN(num) && valStr.match(/^-?\d+\.?\d*$/)) return num;
		if (valStr === '[]') return '[]';
		if (valStr === '{}') return '{}';
		const msgMatch = valStr.match(/Message\s*\(\s*type\s*=\s*["']([^"']*)["']\s*,\s*value\s*=\s*["']([^"']*)["']\s*\)/);
		if (msgMatch) return msgMatch[2];
		const msgMatch2 = valStr.match(/Message\s*\(\s*["']([^"']*)["']\s*,\s*["']([^"']*)["']\s*\)/);
		if (msgMatch2) return msgMatch2[2];
		if (this.moduleConstants && valStr.match(/^[A-Z][A-Z_0-9]*[A-Z0-9]?$|^DEFAULT_[A-Z_0-9]+$/)) {
			if (this.moduleConstants[valStr] !== undefined) return this.moduleConstants[valStr];
		}
		return valStr;
	}

	_extractFieldMetadata(str) {
		const meta = { title: null, description: null, default: undefined };

		const fieldMatch = str.match(/Field\s*\(([^)]*(?:\([^)]*\)[^)]*)*)\)/);
		if (!fieldMatch) return meta;

		const args = fieldMatch[1];

		// Extract title
		const titleMatch = args.match(/title\s*=\s*["']([^"']+)["']/);
		if (titleMatch) meta.title = titleMatch[1];

		// Extract description
		const descMatch = args.match(/description\s*=\s*["']([^"']+)["']/);
		if (descMatch) meta.description = descMatch[1];

		// Extract default
		const defaultStrMatch = args.match(/default\s*=\s*["']([^"']*)["']/);
		if (defaultStrMatch) {
			meta.default = defaultStrMatch[1];
		} else {
			const defaultValMatch = args.match(/default\s*=\s*([^,)]+)/);
			if (defaultValMatch) {
				meta.default = this._parseConstantValue(defaultValMatch[1].trim());
			}
		}

		return meta;
	}

	_parseType(typeStr) {
		typeStr = typeStr.trim();
		if (typeStr.startsWith('Optional['))
			return { kind: 'optional', inner: this._parseType(this._extractBracketContent(typeStr, 9)) };
		if (typeStr.startsWith('Union[')) {
			const inner = this._extractBracketContent(typeStr, 6);
			return { kind: 'union', types: this._splitUnionTypes(inner).map(t => this._parseType(t)), inner };
		}
		if (typeStr.startsWith('List['))
			return { kind: 'list', inner: this._parseType(this._extractBracketContent(typeStr, 5)) };
		if (typeStr.startsWith('Dict['))
			return { kind: 'dict', inner: this._extractBracketContent(typeStr, 5) };
		if (typeStr.startsWith('Message['))
			return { kind: 'message', inner: this._parseType(this._extractBracketContent(typeStr, 8)) };
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
			} else current += c;
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
// WORKFLOW NODE FACTORY
// ========================================================================

class WorkflowNodeFactory {
	constructor(graph, parsed, schemaName) {
		this.app = graph?.app;
		this.graph = graph;
		this.parsed = parsed;
		this.schemaName = schemaName;
	}

	createNode(modelName, nodeData = {}) {
		const { models, fieldRoles, defaults } = this.parsed;
		const fields = models[modelName];
		const roles = fieldRoles[modelName] || {};
		const modelDefaults = defaults[modelName] || {};
		if (!fields) { console.error(`Model not found: ${modelName}`); return null; }

		let workflowType = modelName.toLowerCase();
		for (const field of fields) {
			if (field.name === 'type' && roles[field.name] === FieldRole.CONSTANT) {
				workflowType = modelDefaults[field.name] || workflowType;
				break;
			}
		}

		const nodeConfig = {
			schemaName: this.schemaName, modelName, workflowType,
			fieldRoles: { ...roles }, constantFields: {}
		};

		const inputFields = [], outputFields = [], multiInputFields = [], multiOutputFields = [];
		for (const field of fields) {
			const role = roles[field.name] || FieldRole.INPUT;
			const defaultVal = modelDefaults[field.name];
			const fieldWithDefault = { ...field, default: defaultVal !== undefined ? defaultVal : field.default };

			switch (role) {
				case FieldRole.ANNOTATION: break;
				case FieldRole.CONSTANT:
					nodeConfig.constantFields[field.name] = defaultVal !== undefined ? defaultVal : field.name;
					break;
				case FieldRole.INPUT: inputFields.push(fieldWithDefault); break;
				case FieldRole.OUTPUT: outputFields.push(fieldWithDefault); break;
				case FieldRole.MULTI_INPUT: multiInputFields.push(fieldWithDefault); break;
				case FieldRole.MULTI_OUTPUT: multiOutputFields.push(fieldWithDefault); break;
			}
		}

		const node = new WorkflowNode(`${this.schemaName}.${modelName}`, nodeConfig);
		node.nativeInputs = {};
		node.multiInputSlots = {};
		node.multiOutputSlots = {};
		node.inputMeta = {};
		node.outputMeta = {};

		// Process INPUT fields
		let inputIdx = 0;
		for (const field of inputFields) {
			const displayName = field.title || field.name;
			node.addInput(displayName, field.rawType);

			node.inputMeta[inputIdx] = {
				name: field.name,
				title: field.title,
				description: field.description,
				type: field.rawType
			};

			if (this._isNativeType(field.rawType)) {
				const defaultValue = field.default !== undefined
					? field.default
					: this._getDefaultForType(field.rawType);

				node.nativeInputs[inputIdx] = {
					type: this._getNativeBaseType(field.rawType),
					value: defaultValue,
					optional: field.rawType.includes('Optional')
				};
			}
			inputIdx++;
		}

		// Process MULTI_INPUT fields
		for (const field of multiInputFields) {
			let keys = nodeData[field.name];
			const expandedIndices = [];
			if (keys?.constructor === Object) keys = Object.keys(keys);

			if (Array.isArray(keys) && keys.length > 0) {
				for (const key of keys) {
					const displayName = field.title ? `${field.title}.${key}` : `${field.name}.${key}`;
					node.addInput(displayName, field.rawType);
					node.inputMeta[inputIdx] = {
						name: `${field.name}.${key}`,
						title: field.title,
						description: field.description,
						type: field.rawType,
						isMulti: true
					};
					expandedIndices.push(inputIdx++);
				}
			} else {
				const displayName = field.title || field.name;
				node.addInput(displayName, field.rawType);
				node.inputMeta[inputIdx] = {
					name: field.name,
					title: field.title,
					description: field.description,
					type: field.rawType,
					isMulti: true
				};
				expandedIndices.push(inputIdx++);
			}
			node.multiInputSlots[field.name] = expandedIndices;
		}

		// Process OUTPUT fields
		let outputIdx = 0;
		for (const field of outputFields) {
			const displayName = field.title || field.name;
			node.addOutput(displayName, field.rawType);

			node.outputMeta[outputIdx] = {
				name: field.name,
				title: field.title,
				description: field.description,
				type: field.rawType
			};

			// Store default value on output slot for preview access
			if (field.default !== undefined && node.outputs[outputIdx]) {
				node.outputs[outputIdx].defaultValue = field.default;
			}
			outputIdx++;
		}

		// Process MULTI_OUTPUT fields
		for (const field of multiOutputFields) {
			let keys = nodeData[field.name];
			const expandedIndices = [];
			if (keys?.constructor === Object) keys = Object.keys(keys);

			if (Array.isArray(keys) && keys.length > 0) {
				for (const key of keys) {
					const displayName = field.title ? `${field.title}.${key}` : `${field.name}.${key}`;
					node.addOutput(displayName, field.rawType);
					node.outputMeta[outputIdx] = {
						name: `${field.name}.${key}`,
						title: field.title,
						description: field.description,
						type: field.rawType,
						isMulti: true
					};
					expandedIndices.push(outputIdx++);
				}
			} else {
				const displayName = field.title || field.name;
				node.addOutput(displayName, field.rawType);
				node.outputMeta[outputIdx] = {
					name: field.name,
					title: field.title,
					description: field.description,
					type: field.rawType,
					isMulti: true
				};
				expandedIndices.push(outputIdx++);
			}
			node.multiOutputSlots[field.name] = expandedIndices;
		}

		const maxSlots = Math.max(node.inputs.length, node.outputs.length, 1);
		node.size = [220, Math.max(80, 35 + maxSlots * 25)];

		this.app?._applyDecoratorsToNode?.call(this.app, node);

		return node;
	}

	_isNativeType(typeStr) {
		if (!typeStr) return false;
		const natives = ['str', 'int', 'bool', 'float', 'string', 'integer', 'Any', 'List', 'Dict', 'list', 'dict'];
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
			} else current += c;
		}
		if (current.trim()) result.push(current.trim());
		return result;
	}

	_getNativeBaseType(typeStr) {
		if (!typeStr) return 'str';
		if (typeStr.startsWith('Message[')) {
			const match = typeStr.match(/Message\[([^\]]+)\]/);
			if (match) return this._getNativeBaseType(match[1]);
		}
		// Only process Union if it's at the top level (starts with Union[ or contains |)
		if (typeStr.startsWith('Union[')) {
			const inner = typeStr.slice(6, -1); // Remove "Union[" and trailing "]"
			const parts = this._splitUnionTypes(inner);
			for (const part of parts) {
				if (!part.trim().startsWith('Message')) return this._getNativeBaseType(part.trim());
			}
			if (parts.length > 0 && parts[0].startsWith('Message[')) {
				const match = parts[0].match(/Message\[([^\]]+)\]/);
				if (match) return this._getNativeBaseType(match[1]);
			}
		} else if (typeStr.includes('|') && !typeStr.includes('[')) {
			// Simple union with | (e.g., "int | str") but not nested in brackets
			const parts = typeStr.split('|').map(p => p.trim());
			for (const part of parts) {
				if (!part.startsWith('Message')) return this._getNativeBaseType(part);
			}
		}
		if (typeStr.includes('Dict') || typeStr.includes('dict')) return 'dict';
		if (typeStr.includes('List') || typeStr.includes('list')) return 'list';
		if (typeStr.includes('int') || typeStr.includes('Int')) return 'int';
		if (typeStr.includes('bool') || typeStr.includes('Bool')) return 'bool';
		if (typeStr.includes('float') || typeStr.includes('Float')) return 'float';
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
// WORKFLOW IMPORTER
// ========================================================================

class WorkflowImporter {
	constructor(graph, eventBus) {
		this.graph = graph;
		this.eventBus = eventBus;
	}

	import(workflowData, schemaName, schema, options = {}) {
		if (!workflowData?.nodes) throw new Error('Invalid workflow data: missing nodes array');
		this.importOptions = { includeLayout: options.includeLayout !== false };

		this.graph.nodes = [];
		this.graph.links = {};
		this.graph._nodes_by_id = {};
		this.graph.last_link_id = 0;

		const typeMap = schema ? this._buildTypeMap(schema) : {};
		const factory = schema ? new WorkflowNodeFactory(this.graph, {
			models: schema.parsed, fieldRoles: schema.fieldRoles, defaults: schema.defaults
		}, schemaName) : null;

		const createdNodes = [];
		for (let i = 0; i < workflowData.nodes.length; i++) {
			const nodeData = workflowData.nodes[i];
			const nodeType = nodeData.type || '';
			let node = null;

			if (nodeType.startsWith('native_')) node = this._createNativeNode(nodeData, i);
			else node = this._createWorkflowNode(factory, nodeData, i, schemaName, typeMap);
			createdNodes.push(node);
		}

		if (workflowData.edges) {
			for (const edgeData of workflowData.edges) this._createEdge(edgeData, createdNodes);
		}

		if (this.importOptions?.includeLayout === false) this._autoLayoutNodes(createdNodes);

		for (const node of this.graph.nodes) if (node?.onExecute) node.onExecute();

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
		this.graph.add(node);
		return node;
	}

	_createWorkflowNode(factory, nodeData, index, schemaName, typeMap) {
		if (!factory) { console.error('No factory available'); return null; }
		const modelName = this._resolveModelName(nodeData.type, schemaName, typeMap);
		if (!modelName) { console.error(`Model not found for type: ${nodeData.type}`); return null; }

		const node = factory.createNode(modelName, nodeData);
		if (!node) return null;
		if (nodeData.id) node.workflowId = nodeData.id;
		this._applyLayout(node, nodeData);
		node.workflowIndex = index;

		if (nodeData.extra) {
			node.extra = { ...nodeData.extra };
			if (nodeData.extra.title) node.title = nodeData.extra.title;
			if (nodeData.extra.name) node.displayTitle = nodeData.extra.name;
			if (nodeData.extra.color) node.color = nodeData.extra.color;
		}

		this._populateNodeFields(node, nodeData);

		node.annotations = {};
		const roles = this.graph.schemas[schemaName]?.fieldRoles?.[modelName] || {};
		for (const [fieldName, role] of Object.entries(roles)) {
			if (role === FieldRole.ANNOTATION && nodeData[fieldName] !== undefined)
				node.annotations[fieldName] = nodeData[fieldName];
		}

		this.graph.add(node);
		return node;
	}

	_applyLayout(node, nodeData) {
		if (this.importOptions?.includeLayout !== false) {
			if (nodeData.extra?.pos) node.pos = [...nodeData.extra.pos];
			if (nodeData.extra?.size) node.size = [...nodeData.extra.size];
		} else node.pos = [0, 0];
	}

	_buildTypeMap(schema) {
		const typeMap = {};
		if (schema?.defaults)
			for (const [key, value] of Object.entries(schema.defaults))
				if (value?.type) typeMap[value.type] = key;
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
		for (let i = 0; i < validNodes.length; i++) {
			validNodes[i].pos = [100 + (i % cols) * 280, 100 + Math.floor(i / cols) * 200];
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
		const { source, target, source_slot, target_slot } = edgeData;
		const sourceNode = createdNodes[source], targetNode = createdNodes[target];
		if (!sourceNode || !targetNode) return null;

		const sourceSlotIdx = this._findOutputSlot(sourceNode, source_slot);
		const targetSlotIdx = this._findInputSlot(targetNode, target_slot);
		if (sourceSlotIdx === -1 || targetSlotIdx === -1) return null;

		const link = this._createStandardEdge(sourceNode, sourceSlotIdx, targetNode, targetSlotIdx, edgeData.data, edgeData.extra);
		if (link && edgeData.loop) link.loop = true;  // Mark as loop-back edge
		return link;
	}

	_findOutputSlot(node, slotName) {
		for (let i = 0; i < node.outputs.length; i++)
			if (node.outputs[i].name === slotName) return i;
		const idx = parseInt(slotName);
		if (!isNaN(idx) && idx >= 0 && idx < node.outputs.length) return idx;
		if (node.isNative && node.outputs.length > 0) return 0;
		return -1;
	}

	_findInputSlot(node, slotName) {
		for (let i = 0; i < node.inputs.length; i++)
			if (node.inputs[i].name === slotName) return i;
		const idx = parseInt(slotName);
		if (!isNaN(idx) && idx >= 0 && idx < node.inputs.length) return idx;
		if (node.isNative && node.inputs.length > 0) return 0;
		return -1;
	}

	_createStandardEdge(sourceNode, sourceSlotIdx, targetNode, targetSlotIdx, data, extra) {
		const link = this.graph.connect(sourceNode, sourceSlotIdx, targetNode, targetSlotIdx);
		if (link) {
			if (data) link.data = JSON.parse(JSON.stringify(data));
			if (extra) link.extra = JSON.parse(JSON.stringify(extra));
		}
		return link;
	}
}

// ========================================================================
// WORKFLOW EXPORTER
// ========================================================================

class WorkflowExporter {
	constructor(graph) { this.graph = graph; }

	export(schemaName, workflowInfo = {}, options = {}) {
		this.exportOptions = {
			dataExportMode: options.dataExportMode || DataExportMode.REFERENCE,
			includeLayout: options.includeLayout !== false
		};
		const workflow = { ...JSON.parse(JSON.stringify(workflowInfo)), type: 'workflow', nodes: [], edges: [] };
		const exportableNodes = this.graph.nodes.filter(n => !n.isPreviewNode);

		exportableNodes.sort((a, b) => {
			if (a.workflowIndex !== undefined && b.workflowIndex !== undefined)
				return a.workflowIndex - b.workflowIndex;
			return (a.id || 0) - (b.id || 0);
		});

		const nodeToIndex = new Map();
		for (let i = 0; i < exportableNodes.length; i++) {
			nodeToIndex.set(exportableNodes[i].id, i);
			workflow.nodes.push(this._exportNode(exportableNodes[i]));
		}

		for (const linkId in this.graph.links) {
			const link = this.graph.links[linkId];
			const edge = this._exportEdge(link, nodeToIndex);
			if (edge) workflow.edges.push(edge);
		}

		return workflow;
	}

	_exportNode(node) {
		if (node.isNative) return this._exportNativeNode(node);
		return this._exportWorkflowNode(node);
	}

	_exportNativeNode(node) {
		const typeMap = {
			'String': 'native_string', 'Integer': 'native_integer', 'Float': 'native_float',
			'Boolean': 'native_boolean', 'List': 'native_list', 'Dict': 'native_dict'
		};
		const nativeType = node.title || 'String';
		let value = node.properties?.value;
		if (value === undefined) value = this._getDefaultNativeValue(nativeType);
		const nodeData = { type: typeMap[nativeType] || 'native_string', value };
		if (this.exportOptions?.includeLayout !== false)
			nodeData.extra = { pos: [...node.pos], size: [...node.size] };
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
		const nodeData = {
			type: node.workflowType || node.constantFields?.type || node.modelName?.toLowerCase() || 'unknown'
		};
		if (node.workflowId) nodeData.id = node.workflowId;
		if (node.constantFields)
			for (const key in node.constantFields)
				if (key !== 'type') nodeData[key] = node.constantFields[key];

		for (const [baseName, slotIndices] of Object.entries(node.multiInputSlots || {})) {
			const keys = slotIndices.map(idx => {
				const n = node.inputs[idx].name;
				const d = n.indexOf('.');
				return d !== -1 ? n.substring(d + 1) : null;
			}).filter(Boolean);
			if (keys.length > 0) nodeData[baseName] = keys;
		}
		for (const [baseName, slotIndices] of Object.entries(node.multiOutputSlots || {})) {
			const keys = slotIndices.map(idx => {
				const n = node.outputs[idx].name;
				const d = n.indexOf('.');
				return d !== -1 ? n.substring(d + 1) : null;
			}).filter(Boolean);
			if (keys.length > 0) nodeData[baseName] = keys;
		}

		for (let i = 0; i < node.inputs.length; i++) {
			const input = node.inputs[i];
			if (input.link) continue;
			const baseName = input.name.split('.')[0];
			if (node.multiInputSlots?.[baseName]) continue;
			if (node.nativeInputs?.[i] !== undefined) {
				const val = node.nativeInputs[i].value;
				if (val !== null && val !== undefined && val !== '')
					nodeData[input.name] = this._convertExportValue(val, node.nativeInputs[i].type);
			}
		}

		nodeData.extra = {};
		if (this.exportOptions?.includeLayout !== false) {
			nodeData.extra.pos = [...node.pos];
			nodeData.extra.size = [...node.size];
		}
		if (node.extra) {
			const { pos, size, ...rest } = node.extra;
			nodeData.extra = { ...nodeData.extra, ...rest };
		}
		if (node.title !== `${node.schemaName}.${node.modelName}`) nodeData.extra.title = node.title;
		if (node.displayTitle) nodeData.extra.name = node.displayTitle;
		if (node.color) nodeData.extra.color = node.color;
		if (Object.keys(nodeData.extra).length === 0) delete nodeData.extra;

		if (node.annotations)
			for (const [key, value] of Object.entries(node.annotations))
				if (value !== null && value !== undefined) nodeData[key] = value;
		return nodeData;
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
		if (link.loop) edge.loop = true;  // Preserve loop-back edge marker
		if (link.data && Object.keys(link.data).length > 0)
			edge.data = JSON.parse(JSON.stringify(link.data));
		if (link.extra && Object.keys(link.extra).length > 0)
			edge.extra = JSON.parse(JSON.stringify(link.extra));
		return edge;
	}

	_convertExportValue(val, type) {
		if ((type === 'dict' || type === 'list') && typeof val === 'string') {
			try { return JSON.parse(val); } catch { return val; }
		}
		return val;
	}
}

// ========================================================================
// EXPORTS
// ========================================================================

// Module exports
if (typeof module !== 'undefined' && module.exports) {
	module.exports = {
		WorkflowNode, WorkflowSchemaParser, WorkflowNodeFactory,
		WorkflowImporter, WorkflowExporter
	};
}

// Global exports for browser (standard JS)
if (typeof window !== 'undefined') {
	window.WorkflowNode = WorkflowNode;
	window.WorkflowSchemaParser = WorkflowSchemaParser;
	window.WorkflowNodeFactory = WorkflowNodeFactory;
	window.WorkflowImporter = WorkflowImporter;
	window.WorkflowExporter = WorkflowExporter;
}

console.log('[SchemaGraph] Workflow module loaded.');
