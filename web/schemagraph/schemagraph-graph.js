// ========================================================================
// SCHEMAGRAPH GRAPH
// SchemaGraph class with workflow support
// Depends on: schemagraph-core.js, schemagraph-workflow.js
// ========================================================================

console.log('[SchemaGraph] Loading graph module...');

// ========================================================================
// SCHEMA GRAPH (with workflow support)
// ========================================================================

class SchemaGraph extends Graph {
	constructor(app, eventBus) {
		super();
		this.app = app;
		this.eventBus = eventBus;
		this.schemas = {};
		this.nodeTypes = {};
		this.nodeSchemas = {};  // Store raw schema configs for retrieval
		this.enabledSchemas = new Set();
	}

	getNodeSchema(typeName) {
		return this.nodeSchemas[typeName] || null;
	}

	registerSchema(schemaName, schemaCode, indexType = 'int', rootType = null) {
		if (schemaCode.includes('FieldRole.')) return this.registerWorkflowSchema(schemaName, schemaCode);

		try {
			const parsed = this._parseSchema(schemaCode);
			const fieldMapping = this._createFieldMappingFromSchema(schemaCode, parsed, rootType);
			this.schemas[schemaName] = { code: schemaCode, parsed, indexType, rootType, fieldMapping };
			this._generateNodes(schemaName, parsed, indexType);
			this.enabledSchemas.add(schemaName);
			this.eventBus.emit('schema:registered', { schemaName, rootType });
			return true;
		} catch (e) {
			console.error('Schema error:', e);
			this.eventBus.emit('error', { type: 'schema:register', error: e.message });
			return false;
		}
	}

	registerWorkflowSchema(schemaName, schemaCode) {
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

			const self = this;
			for (const modelName in parsed.models) {
				const defaults = parsed.defaults[modelName] || {};
				if (!defaults.type) continue;

				const fullTypeName = `${schemaName}.${modelName}`;
				const capturedModelName = modelName, capturedSchemaName = schemaName;
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
	}

	enableSchema(schemaName) {
		if (this.schemas[schemaName]) {
			this.enabledSchemas.add(schemaName);
			this.eventBus.emit('schema:enabled', { schemaName });
			return true;
		}
		return false;
	}

	disableSchema(schemaName) {
		if (this.schemas[schemaName]) {
			this.enabledSchemas.delete(schemaName);
			this.eventBus.emit('schema:disabled', { schemaName });
			return true;
		}
		return false;
	}

	toggleSchema(schemaName) {
		return this.enabledSchemas.has(schemaName) ? this.disableSchema(schemaName) : this.enableSchema(schemaName);
	}

	isSchemaEnabled(schemaName) { return this.enabledSchemas.has(schemaName); }
	getEnabledSchemas() { return Array.from(this.enabledSchemas); }
	isWorkflowSchema(schemaName) { return this.schemas[schemaName]?.isWorkflow === true; }

	importWorkflow(workflowData, schemaName, options) {
		const importer = new WorkflowImporter(this, this.eventBus);
		return importer.import(workflowData, schemaName, this.schemas[schemaName], options);
	}

	exportWorkflow(schemaName, workflowInfo = {}, options = {}) {
		const exporter = new WorkflowExporter(this);
		return exporter.export(schemaName, workflowInfo, options);
	}

	_createFieldMappingFromSchema(schemaCode, parsedModels, rootType) {
		const mapping = { modelToField: {}, fieldToModel: {} };
		if (!rootType || !parsedModels[rootType]) return this._createFallbackMapping(parsedModels);
		const rootFields = parsedModels[rootType];
		for (const field of rootFields) {
			const modelType = this._extractModelTypeFromField(field.type);
			if (modelType && parsedModels[modelType]) {
				mapping.modelToField[modelType] = field.name;
				mapping.fieldToModel[field.name] = modelType;
			}
		}
		return mapping;
	}

	_extractModelTypeFromField(fieldType) {
		let current = fieldType;
		if (current.kind === 'optional') current = current.inner;
		if (current.kind === 'list' || current.kind === 'set' || current.kind === 'tuple') current = current.inner;
		if (current.kind === 'dict') return null;
		if (current.kind === 'union') {
			for (const type of current.types)
				if (type.kind === 'basic' && type.name?.endsWith('Config')) return type.name;
			return null;
		}
		if (current.kind === 'basic' && current.name?.endsWith('Config')) return current.name;
		return null;
	}

	_createFallbackMapping(parsedModels) {
		const mapping = { modelToField: {}, fieldToModel: {} };
		for (const modelName in parsedModels) {
			if (!parsedModels.hasOwnProperty(modelName)) continue;
			const baseName = modelName.replace(/Config$/, '');
			let fieldName = baseName.replace(/([A-Z]+)([A-Z][a-z])/g, '$1_$2')
				.replace(/([a-z\d])([A-Z])/g, '$1_$2').toLowerCase();
			if (!fieldName.endsWith('s')) {
				fieldName = fieldName.endsWith('y') &&
					!['ay', 'ey', 'iy', 'oy', 'uy'].some(end => fieldName.endsWith(end))
					? fieldName.slice(0, -1) + 'ies' : fieldName + 's';
			}
			mapping.modelToField[modelName] = fieldName;
			mapping.fieldToModel[fieldName] = modelName;
		}
		return mapping;
	}

	_parseSchema(code) {
		const models = {};
		const lines = code.split('\n');
		let currentModel = null, currentFields = [];
		for (const line of lines) {
			const trimmed = line.trim();
			const classMatch = trimmed.match(/^class\s+(\w+)\s*\(/);
			if (classMatch) {
				if (currentModel) models[currentModel] = currentFields;
				currentModel = classMatch[1];
				currentFields = [];
				continue;
			}
			if (currentModel && trimmed.indexOf(':') !== -1) {
				const fieldMatch = trimmed.match(/^(\w+)\s*:\s*(.+?)(?:\s*=|$)/);
				if (fieldMatch) currentFields.push({
					name: fieldMatch[1],
					type: this._parseType(fieldMatch[2].trim()),
					rawType: fieldMatch[2].trim()
				});
			}
		}
		if (currentModel) models[currentModel] = currentFields;
		return models;
	}

	_parseType(str) {
		str = str.trim();
		if (str.indexOf('Optional[') === 0)
			return { kind: 'optional', inner: this._parseType(this._extractBracket(str, 9)) };
		if (str.indexOf('Union[') === 0)
			return { kind: 'union', types: this._splitTypes(this._extractBracket(str, 6)).map(t => this._parseType(t)) };
		if (str.indexOf('List[') === 0)
			return { kind: 'list', inner: this._parseType(this._extractBracket(str, 5)) };
		if (str.indexOf('Dict[') === 0 || str.indexOf('dict[') === 0)
			return { kind: 'dict', inner: this._extractBracket(str, str.indexOf('[') + 1) };
		return { kind: 'basic', name: str };
	}

	_extractBracket(str, start) {
		let depth = 1, i = start;
		while (i < str.length && depth > 0) {
			if (str.charAt(i) === '[') depth++;
			if (str.charAt(i) === ']') depth--;
			if (depth === 0) break;
			i++;
		}
		return str.substring(start, i);
	}

	_splitTypes(str) {
		const result = [];
		let depth = 0, current = '';
		for (let i = 0; i < str.length; i++) {
			const c = str.charAt(i);
			if (c === '[') depth++;
			if (c === ']') depth--;
			if (c === ',' && depth === 0) { result.push(current.trim()); current = ''; }
			else current += c;
		}
		if (current) result.push(current.trim());
		return result;
	}

	_generateNodes(schemaName, models, indexType) {
		for (const modelName in models) {
			if (!models.hasOwnProperty(modelName)) continue;
			const fields = models[modelName];
			const self = this, schemaInfo = this.schemas[schemaName];
			const isRootType = schemaInfo && schemaInfo.rootType === modelName;

			class GeneratedNode extends Node {
				constructor() {
					super(schemaName + '.' + modelName);
					this.schemaName = schemaName;
					this.modelName = modelName;
					this.isRootType = isRootType;
					this.addOutput('self', modelName);
					this.nativeInputs = {};
					this.multiInputs = {};
					this.optionalFields = {};

					for (let i = 0; i < fields.length; i++) {
						const f = fields[i];
						const inputType = self._getInputType(f, indexType);
						const compactType = self.compactType(inputType);
						const isOptional = f.type.kind === 'optional';
						if (isOptional) this.optionalFields[i] = true;

						const isCollectionOfUnions = self._isCollectionOfUnions(f.type);
						const isListField = isRootType && self._isListFieldType(f.type);

						if (isCollectionOfUnions || isListField) {
							this.addInput(f.name, compactType);
							this.multiInputs[i] = { type: compactType, links: [] };
						} else {
							this.addInput(f.name, compactType);
							if (self._isNativeType(compactType)) {
								const baseType = self._getNativeBaseType(compactType);
								this.nativeInputs[i] = {
									type: baseType,
									value: self._getDefaultValueForType(baseType),
									optional: isOptional
								};
							}
						}
					}
					this.size = [200, Math.max(80, 40 + fields.length * 25)];
				}

				onExecute() {
					const data = {};
					for (let i = 0; i < this.inputs.length; i++) {
						if (this.multiInputs[i]) {
							const values = [];
							for (const linkId of this.multiInputs[i].links) {
								const link = this.graph.links[linkId];
								if (link) {
									const sourceNode = this.graph.getNodeById(link.origin_id);
									if (sourceNode?.outputs[link.origin_slot])
										values.push(sourceNode.outputs[link.origin_slot].value);
								}
							}
							if (values.length > 0) data[this.inputs[i].name] = values;
							else if (this.optionalFields[i]) continue;
						} else {
							const connectedVal = this.getInputData(i);
							if (connectedVal !== null && connectedVal !== undefined) {
								data[this.inputs[i].name] = connectedVal;
							} else if (this.nativeInputs[i] !== undefined) {
								const val = this.nativeInputs[i].value;
								const isOptional = this.nativeInputs[i].optional;
								const baseType = this.nativeInputs[i].type;
								if (baseType === 'bool') {
									if (val === true || val === false) data[this.inputs[i].name] = val;
									else if (val === 'true') data[this.inputs[i].name] = true;
									else if (!isOptional && (val === 'false' || val === ''))
										data[this.inputs[i].name] = false;
									continue;
								}
								const isEmpty = val === null || val === undefined || val === '';
								if (isOptional && isEmpty) continue;
								if (!isEmpty) {
									if (baseType === 'dict' || baseType === 'list') {
										try { data[this.inputs[i].name] = JSON.parse(val); }
										catch { data[this.inputs[i].name] = baseType === 'dict' ? {} : []; }
									} else if (baseType === 'int') data[this.inputs[i].name] = parseInt(val) || 0;
									else if (baseType === 'float') data[this.inputs[i].name] = parseFloat(val) || 0.0;
									else data[this.inputs[i].name] = val;
								} else if (!isOptional) {
									if (baseType === 'int') data[this.inputs[i].name] = 0;
									else if (baseType === 'float') data[this.inputs[i].name] = 0.0;
									else if (baseType === 'dict') data[this.inputs[i].name] = {};
									else if (baseType === 'list') data[this.inputs[i].name] = [];
									else data[this.inputs[i].name] = '';
								}
							}
						}
					}
					this.setOutputData(0, data);
				}
			}

			this.nodeTypes[schemaName + '.' + modelName] = GeneratedNode;
		}
	}

	_isNativeType(typeStr) {
		if (!typeStr) return false;
		let base = typeStr.trim();
		if (base.startsWith('Optional[') && base.endsWith(']')) base = base.slice(9, -1).trim();
		if (base.startsWith('Literal[')) return true;
		base = base.split('|')[0].trim();
		const nativeTypes = ['str', 'int', 'bool', 'float', 'string', 'integer', 'Index'];
		if (nativeTypes.indexOf(base) !== -1) return true;
		if (base.indexOf('Dict[') === 0 || base.indexOf('List[') === 0) return true;
		return false;
	}

	_isCollectionOfUnions(fieldType) {
		let current = fieldType;
		if (current.kind === 'optional') current = current.inner;
		if (current.kind === 'list' && current.inner?.kind === 'union') return true;
		if (current.kind === 'dict' && current.inner?.indexOf('Union[') !== -1) return true;
		return false;
	}

	_isListFieldType(fieldType) {
		let current = fieldType;
		if (current.kind === 'optional') current = current.inner;
		return current.kind === 'list';
	}

	_getNativeBaseType(typeStr) {
		if (!typeStr) return 'str';
		let base = typeStr.trim();
		if (base.startsWith('Optional[') && base.endsWith(']')) base = base.slice(9, -1).trim();
		if (base.startsWith('Literal[')) return 'literal';
		base = base.split('|')[0].trim();
		if (base === 'int' || base === 'integer' || base === 'Index') return 'int';
		if (base === 'bool') return 'bool';
		if (base === 'float') return 'float';
		if (base.indexOf('Dict[') === 0) return 'dict';
		if (base.indexOf('List[') === 0) return 'list';
		return 'str';
	}

	_getDefaultValueForType(baseType) {
		if (baseType === 'int') return 0;
		if (baseType === 'bool') return false;
		if (baseType === 'float') return 0.0;
		if (baseType === 'dict') return '{}';
		if (baseType === 'list') return '[]';
		return '';
	}

	_getInputType(field, indexType) {
		const t = field.type;
		if (t.kind === 'optional')
			return 'Optional[' + this._getInputType({ type: t.inner }, indexType) + ']';
		if (t.kind === 'union') {
			let hasIdx = false, modelType = null;
			for (const tp of t.types) {
				if (tp.kind === 'basic' && tp.name === indexType) hasIdx = true;
				else modelType = tp;
			}
			if (hasIdx && modelType && t.types.length === 2) return modelType.name || 'Model';
			return t.types.map(tp => tp.name || tp.kind).join('|');
		}
		if (t.kind === 'list') return 'List[' + this._getInputType({ type: t.inner }, indexType) + ']';
		if (t.kind === 'dict') return 'Dict[' + t.inner + ']';
		if (t.kind === 'basic') return t.name;
		return 'Any';
	}

	compactType(typeStr) { return typeStr ? typeStr.replace(/\s+/g, '') : typeStr; }

	getSchemaInfo(schemaName) {
		if (!this.schemas[schemaName]) return null;
		return {
			name: schemaName,
			indexType: this.schemas[schemaName].indexType,
			rootType: this.schemas[schemaName].rootType,
			models: Object.keys(this.schemas[schemaName].parsed),
			isWorkflow: this.schemas[schemaName].isWorkflow || false
		};
	}

	// Register a node type directly with a config object (convenience method)
	registerNodeType(typeName, config) {
		const schema = config;
		const schemaName = typeName.split('.')[0] || 'custom';
		const modelName = typeName.split('.').pop();

		// Create a node class using ES6 class syntax
		class GeneratedNode extends Node {
			constructor() {
				super(schema.title || modelName);
				this.type = typeName;
				this.title = schema.title || modelName;
				this.color = schema.color || '#666666';
				this.bgcolor = schema.bgcolor || '#333333';
				this.schemaName = schemaName;
				this.modelName = modelName;
				this.nativeInputs = {};

				// Setup inputs
				if (schema.inputs) {
					for (const inp of schema.inputs) {
						this.addInput(inp.name, inp.type || 'any');
					}
				}

				// Setup outputs (with defaults stored on slots)
				if (schema.outputs) {
					for (let i = 0; i < schema.outputs.length; i++) {
						const out = schema.outputs[i];
						this.addOutput(out.name, out.type || 'any');
						// Store default value on the output slot for preview access
						if (out.default !== undefined && this.outputs[i]) {
							this.outputs[i].defaultValue = out.default;
						}
					}
				}

				// Setup fields
				this.fields = {};
				this._fieldDefs = schema.fields || [];
				for (const field of this._fieldDefs) {
					this.fields[field.name] = field.default !== undefined ? field.default : '';
				}

				// Properties for rendering
				this.size = [180, Math.max(80, 40 + (this.inputs.length + this.outputs.length) * 20 + this._fieldDefs.length * 25)];
				this.pos = [0, 0];
			}

			onExecute() {
				const data = { ...this.fields };
				this.setOutputData(0, data);
			}
		}

		GeneratedNode.title = schema.title || modelName;
		GeneratedNode.type = typeName;

		this.nodeTypes[typeName] = GeneratedNode;
		this.nodeSchemas[typeName] = config;  // Store for getNodeSchema()
		return true;
	}

	createNode(type, x, y, data) {
		const NodeClass = this.nodeTypes[type];
		if (!NodeClass) throw new Error('Unknown node type: ' + type);
		const node = new NodeClass();
		if (x !== undefined) node.pos[0] = x;
		if (y !== undefined) node.pos[1] = y;
		if (data) {
			for (const key in data) {
				if (data.hasOwnProperty(key)) {
					node.fields[key] = data[key];
				}
			}
		}
		this.add(node);
		this.eventBus.emit('node:created', { type, nodeId: node.id });
		return node;
	}

	createLink(sourceNode, sourceSlotName, targetNode, targetSlotName) {
		// Find slot indices by name
		let sourceSlotIdx = -1;
		let targetSlotIdx = -1;

		for (let i = 0; i < sourceNode.outputs.length; i++) {
			if (sourceNode.outputs[i].name === sourceSlotName) {
				sourceSlotIdx = i;
				break;
			}
		}

		for (let i = 0; i < targetNode.inputs.length; i++) {
			if (targetNode.inputs[i].name === targetSlotName) {
				targetSlotIdx = i;
				break;
			}
		}

		if (sourceSlotIdx === -1) {
			console.warn('Source slot not found:', sourceSlotName);
			return null;
		}
		if (targetSlotIdx === -1) {
			console.warn('Target slot not found:', targetSlotName);
			return null;
		}

		return this.connect(sourceNode, sourceSlotIdx, targetNode, targetSlotIdx);
	}

	removeSchema(schemaName) {
		if (!this.schemas[schemaName]) return false;
		for (let i = this.nodes.length - 1; i >= 0; i--) {
			const node = this.nodes[i];
			if (node.schemaName === schemaName) {
				for (let j = 0; j < node.inputs.length; j++) {
					if (node.inputs[j].link) {
						const linkId = node.inputs[j].link;
						const link = this.links[linkId];
						if (link) {
							const originNode = this.getNodeById(link.origin_id);
							if (originNode) {
								const idx = originNode.outputs[link.origin_slot].links.indexOf(linkId);
								if (idx > -1) originNode.outputs[link.origin_slot].links.splice(idx, 1);
							}
							delete this.links[linkId];
						}
					}
				}
				for (let j = 0; j < node.outputs.length; j++) {
					const links = node.outputs[j].links.slice();
					for (const linkId of links) {
						const link = this.links[linkId];
						if (link) {
							const targetNode = this.getNodeById(link.target_id);
							if (targetNode) targetNode.inputs[link.target_slot].link = null;
							delete this.links[linkId];
						}
					}
				}
				this.nodes.splice(i, 1);
				delete this._nodes_by_id[node.id];
			}
		}
		for (const type in this.nodeTypes)
			if (this.nodeTypes.hasOwnProperty(type) && type.indexOf(schemaName + '.') === 0)
				delete this.nodeTypes[type];
		delete this.schemas[schemaName];
		this.eventBus.emit('schema:removed', { schemaName });
		return true;
	}

	getRegisteredSchemas() { return Object.keys(this.schemas); }

	addNode(node) {
		if (!node) return null;
		node.graph = this;
		this.nodes.push(node);
		this._nodes_by_id[node.id] = node;
		this.eventBus.emit(GraphEvents.NODE_CREATED, {
			nodeId: node.id,
			nodeType: node.type || node.title,
			node
		});
		return node;
	}

	removeNode(node) {
		if (!node) return false;
		const nodeId = node.id;
		const nodeType = node.type || node.title;

		// Remove connected links first
		const linksToRemove = [];
		for (const linkId in this.links) {
			const link = this.links[linkId];
			if (link.origin_id === nodeId || link.target_id === nodeId) {
				linksToRemove.push(linkId);
			}
		}
		for (const linkId of linksToRemove) {
			this.removeLink(linkId);
		}

		// Remove from array
		const idx = this.nodes.indexOf(node);
		if (idx !== -1) this.nodes.splice(idx, 1);
		delete this._nodes_by_id[nodeId];

		this.eventBus.emit(GraphEvents.NODE_REMOVED, { nodeId, nodeType });
		return true;
	}

	removeLink(linkId) {
		const link = this.links[linkId];
		if (!link) return false;

		const sourceNode = this.getNodeById(link.origin_id);
		const targetNode = this.getNodeById(link.target_id);

		// Remove from source output
		if (sourceNode?.outputs?.[link.origin_slot]?.links) {
			const idx = sourceNode.outputs[link.origin_slot].links.indexOf(linkId);
			if (idx !== -1) sourceNode.outputs[link.origin_slot].links.splice(idx, 1);
		}

		// Remove from target input
		if (targetNode?.inputs?.[link.target_slot]) {
			if (targetNode.inputs[link.target_slot].link === linkId) {
				targetNode.inputs[link.target_slot].link = null;
			}
			// Handle multi-inputs
			if (targetNode.multiInputs?.[link.target_slot]?.links) {
				const idx = targetNode.multiInputs[link.target_slot].links.indexOf(linkId);
				if (idx !== -1) targetNode.multiInputs[link.target_slot].links.splice(idx, 1);
			}
		}

		delete this.links[linkId];

		this.eventBus.emit(GraphEvents.LINK_REMOVED, {
			linkId,
			sourceNodeId: link.origin_id,
			sourceSlot: link.origin_slot,
			targetNodeId: link.target_id,
			targetSlot: link.target_slot
		});

		return true;
	}

	serialize(includeCamera = false, camera = null) {
		const data = { version: '1.0', nodes: [], links: [] };
		for (const node of this.nodes) {
			const nodeData = {
				id: node.id,
				type: node.title,
				pos: node.pos.slice(),
				size: node.size.slice(),
				properties: JSON.parse(JSON.stringify(node.properties || {})),
				schemaName: node.schemaName,
				modelName: node.modelName,
				isNative: node.isNative || false,
				isRootType: node.isRootType || false,
				isWorkflowNode: node.isWorkflowNode || false
			};
			if (node.nativeInputs) nodeData.nativeInputs = JSON.parse(JSON.stringify(node.nativeInputs));
			if (node.multiInputs) nodeData.multiInputs = JSON.parse(JSON.stringify(node.multiInputs));
			if (node.multiInputSlots) nodeData.multiInputSlots = JSON.parse(JSON.stringify(node.multiInputSlots));
			if (node.multiOutputSlots) nodeData.multiOutputSlots = JSON.parse(JSON.stringify(node.multiOutputSlots));
			if (node.constantFields) nodeData.constantFields = JSON.parse(JSON.stringify(node.constantFields));
			if (node.workflowType) nodeData.workflowType = node.workflowType;
			if (node.workflowIndex !== undefined) nodeData.workflowIndex = node.workflowIndex;
			if (node.color) nodeData.color = node.color;
			if (node.displayTitle) nodeData.displayTitle = node.displayTitle;
			data.nodes.push(nodeData);
		}
		for (const linkId in this.links) {
			if (this.links.hasOwnProperty(linkId)) {
				const link = this.links[linkId];
				data.links.push({
					id: link.id,
					origin_id: link.origin_id,
					origin_slot: link.origin_slot,
					target_id: link.target_id,
					target_slot: link.target_slot,
					type: link.type
				});
			}
		}
		if (includeCamera && camera)
			data.camera = { x: camera.x, y: camera.y, scale: camera.scale };
		return data;
	}

	deserialize(data, restoreCamera = false, camera = null) {
		this.nodes = [];
		this.links = {};
		this._nodes_by_id = {};
		this.last_link_id = 0;
		if (!data || !data.nodes) throw new Error('Invalid graph data');

		for (const nodeData of data.nodes) {
			let nodeTypeKey = nodeData.isNative ? 'Native.' + nodeData.type
				: (nodeData.schemaName && nodeData.modelName)
					? nodeData.schemaName + '.' + nodeData.modelName
					: nodeData.type;
			if (!this.nodeTypes[nodeTypeKey]) {
				console.warn('Node type not found:', nodeTypeKey);
				continue;
			}

			const node = new (this.nodeTypes[nodeTypeKey])();
			node.id = nodeData.id;
			node.pos = nodeData.pos.slice();
			node.size = nodeData.size.slice();
			node.properties = JSON.parse(JSON.stringify(nodeData.properties || {}));
			if (nodeData.isRootType !== undefined) node.isRootType = nodeData.isRootType;
			if (nodeData.nativeInputs) node.nativeInputs = JSON.parse(JSON.stringify(nodeData.nativeInputs));
			if (nodeData.multiInputs) node.multiInputs = JSON.parse(JSON.stringify(nodeData.multiInputs));
			if (nodeData.multiInputSlots) node.multiInputSlots = JSON.parse(JSON.stringify(nodeData.multiInputSlots));
			if (nodeData.multiOutputSlots) node.multiOutputSlots = JSON.parse(JSON.stringify(nodeData.multiOutputSlots));
			if (nodeData.constantFields) node.constantFields = JSON.parse(JSON.stringify(nodeData.constantFields));
			if (nodeData.workflowType) node.workflowType = nodeData.workflowType;
			if (nodeData.workflowIndex !== undefined) node.workflowIndex = nodeData.workflowIndex;
			if (nodeData.color) node.color = nodeData.color;
			if (nodeData.displayTitle) node.displayTitle = nodeData.displayTitle;
			this.nodes.push(node);
			this._nodes_by_id[node.id] = node;
			node.graph = this;
		}

		if (data.links) {
			for (const linkData of data.links) {
				const originNode = this._nodes_by_id[linkData.origin_id];
				const targetNode = this._nodes_by_id[linkData.target_id];
				if (originNode && targetNode) {
					const link = new Link(
						linkData.id,
						linkData.origin_id,
						linkData.origin_slot,
						linkData.target_id,
						linkData.target_slot,
						linkData.type
					);
					this.links[linkData.id] = link;
					originNode.outputs[linkData.origin_slot].links.push(linkData.id);
					if (targetNode.multiInputs && targetNode.multiInputs[linkData.target_slot])
						targetNode.multiInputs[linkData.target_slot].links.push(linkData.id);
					else targetNode.inputs[linkData.target_slot].link = linkData.id;
					if (linkData.id > this.last_link_id) this.last_link_id = linkData.id;
				}
			}
		}

		if (restoreCamera && data.camera && camera) {
			camera.x = data.camera.x;
			camera.y = data.camera.y;
			camera.scale = data.camera.scale;
		}
		this.eventBus.emit('graph:deserialized', { nodeCount: this.nodes.length });
		return true;
	}
}

// ========================================================================
// EXPORTS
// ========================================================================

// Module exports
if (typeof module !== 'undefined' && module.exports) {
	module.exports = { SchemaGraph };
}

// Global exports for browser (standard JS)
if (typeof window !== 'undefined') {
	window.SchemaGraph = SchemaGraph;
}

console.log('[SchemaGraph] Graph module loaded.');
