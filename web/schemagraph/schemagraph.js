console.log('=== SCHEMAGRAPH LOADING ===');


class EventBus {
	constructor() {
		this.listeners = new Map();
		this.eventHistory = [];
		this.maxHistory = 1000;
	}

	on(event, callback, context = null) {
		if (!this.listeners.has(event)) {
			this.listeners.set(event, []);
		}
		this.listeners.get(event).push({ callback, context });
		return () => this.off(event, callback);
	}

	off(event, callback) {
		if (!this.listeners.has(event)) return;
		const listeners = this.listeners.get(event);
		const index = listeners.findIndex(l => l.callback === callback);
		if (index > -1) {
			listeners.splice(index, 1);
		}
	}

	emit(event, data = null) {
		const eventData = { event, data, timestamp: Date.now() };
		this.eventHistory.push(eventData);
		if (this.eventHistory.length > this.maxHistory) {
			this.eventHistory.shift();
		}

		if (!this.listeners.has(event)) return;
		const listeners = this.listeners.get(event);
		for (const { callback, context } of listeners) {
			try {
				callback.call(context, data);
			} catch (e) {
				console.error(`Error in event listener for ${event}:`, e);
			}
		}
	}

	clear(event = null) {
		if (event) {
			this.listeners.delete(event);
		} else {
			this.listeners.clear();
		}
	}

	getHistory(event = null, limit = 100) {
		let history = this.eventHistory;
		if (event) {
			history = history.filter(e => e.event === event);
		}
		return history.slice(-limit);
	}
}


class AnalyticsService {
constructor(eventBus) {
		this.eventBus = eventBus;
		this.metrics = this.createMetrics();
		this.sessions = [];
		this.currentSession = this.createSession();
		this.setupListeners();
	}

	createMetrics() {
		return {
			nodeCreated: 0,
			nodeDeleted: 0,
			linkCreated: 0,
			linkDeleted: 0,
			schemaRegistered: 0,
			schemaRemoved: 0,
			graphExported: 0,
			graphImported: 0,
			configExported: 0,
			configImported: 0,
			layoutApplied: 0,
			errors: 0,
			interactions: 0
		};
	}

	createSession() {
		return {
			id: Math.random().toString(36).substr(2, 9),
			startTime: Date.now(),
			events: [],
			metrics: {}
		};
	}

	setupListeners() {
		this.eventBus.on('node:created', () => this.track('nodeCreated'));
		this.eventBus.on('node:deleted', () => this.track('nodeDeleted'));
		this.eventBus.on('link:created', () => this.track('linkCreated'));
		this.eventBus.on('link:deleted', () => this.track('linkDeleted'));
		this.eventBus.on('schema:registered', () => this.track('schemaRegistered'));
		this.eventBus.on('schema:removed', () => this.track('schemaRemoved'));
		this.eventBus.on('graph:exported', () => this.track('graphExported'));
		this.eventBus.on('graph:imported', () => this.track('graphImported'));
		this.eventBus.on('config:exported', () => this.track('configExported'));
		this.eventBus.on('config:imported', () => this.track('configImported'));
		this.eventBus.on('layout:applied', () => this.track('layoutApplied'));
		this.eventBus.on('error', () => this.track('errors'));
		this.eventBus.on('interaction', () => this.track('interactions'));
	}

	track(metric, value = 1) {
		if (this.metrics.hasOwnProperty(metric)) {
			this.metrics[metric] += value;
		}
		this.currentSession.events.push({
			metric,
			value,
			timestamp: Date.now()
		});
	}

getMetrics() {
		return { ...this.metrics };
	}

	getSessionMetrics() {
		return {
			sessionId: this.currentSession.id,
			duration: Date.now() - this.currentSession.startTime,
			events: this.currentSession.events.length,
			metrics: this.metrics
		};
	}

	endSession() {
		this.currentSession.endTime = Date.now();
		this.currentSession.metrics = { ...this.metrics };
		this.sessions.push(this.currentSession);
		
		this.metrics = this.createMetrics();
		this.currentSession = this.createSession();
	}

	log(message, data = null) {
		console.log(`[Analytics] ${message}`, data || '');
	}
}


class Node {
	constructor(title) {
		this.id = Math.random().toString(36).substr(2, 9);
		this.title = title || "Node";
		this.pos = [0, 0];
		this.size = [180, 60];
		this.inputs = [];
		this.outputs = [];
		this.properties = {};
		this.graph = null;
	}

	addInput(name, type) {
		this.inputs.push({ name, type, link: null });
		return this.inputs.length - 1;
	}

	addOutput(name, type) {
		this.outputs.push({ name, type, links: [] });
		return this.outputs.length - 1;
	}

	getInputData(slot) {
		if (!this.inputs[slot] || !this.inputs[slot].link) return null;
		const link = this.graph.links[this.inputs[slot].link];
		if (!link) return null;
		const originNode = this.graph.getNodeById(link.origin_id);
		if (!originNode || !originNode.outputs[link.origin_slot]) return null;
		return originNode.outputs[link.origin_slot].value;
	}

	setOutputData(slot, data) {
		if (this.outputs[slot]) {
			this.outputs[slot].value = data;
		}
	}

	onExecute() {}
}

class Link {
	constructor(id, origin_id, origin_slot, target_id, target_slot, type) {
		this.id = id;
		this.origin_id = origin_id;
		this.origin_slot = origin_slot;
		this.target_id = target_id;
		this.target_slot = target_slot;
		this.type = type;
	}
}

class Graph {
	constructor() {
		this.nodes = [];
		this.links = {};
		this._nodes_by_id = {};
		this.last_link_id = 0;
	}

	add(node) {
		this.nodes.push(node);
		this._nodes_by_id[node.id] = node;
		node.graph = this;
		return node;
	}

	getNodeById(id) {
		return this._nodes_by_id[id];
	}

	connect(originNode, originSlot, targetNode, targetSlot) {
		const outputType = originNode.outputs[originSlot].type;
		const inputType = targetNode.inputs[targetSlot].type;
		
		if (!this._areTypesCompatible(outputType, inputType)) {
			console.warn('Type mismatch:', outputType, '!=', inputType);
			return null;
		}
		
		const linkId = ++this.last_link_id;
		const link = new Link(linkId, originNode.id, originSlot, targetNode.id, targetSlot, outputType);
		
		this.links[linkId] = link;
		originNode.outputs[originSlot].links.push(linkId);
		targetNode.inputs[targetSlot].link = linkId;
		
		return link;
	}

	_areTypesCompatible(outputType, inputType) {
		if (!outputType || !inputType) return true;
		const output = outputType.trim();
		const input = inputType.trim();
		if (output === input) return true;
		if (input === 'Any' || output === 'Any') return true;
		
		const optMatch = input.match(/Optional\[(.+)\]/);
		if (optMatch) return this._areTypesCompatible(output, optMatch[1]);
		
		const unionMatch = input.match(/Union\[(.+)\]/);
		if (unionMatch) {
			const types = this._splitTypeString(unionMatch[1]);
			for (let i = 0; i < types.length; i++) {
				if (this._areTypesCompatible(output, types[i])) return true;
			}
			return false;
		}
		
		if (input.indexOf('|') !== -1) {
			const parts = input.split('|');
			for (let i = 0; i < parts.length; i++) {
				if (this._areTypesCompatible(output, parts[i].trim())) return true;
			}
			return false;
		}
		
		if (output.indexOf('.') !== -1) {
			const outModel = output.split('.').pop();
			return outModel === input || this._areTypesCompatible(outModel, input);
		}
		if (input.indexOf('.') !== -1) {
			const inModel = input.split('.').pop();
			return output === inModel || this._areTypesCompatible(output, inModel);
		}
		
		if (output === 'int' && (input === 'Index' || input === 'integer')) return true;
		if (input === 'int' && (output === 'Index' || output === 'integer')) return true;
		if (output === 'str' && input === 'string') return true;
		if (input === 'str' && output === 'string') return true;
		
		return false;
	}

	_splitTypeString(str) {
		const result = [];
		let depth = 0;
		let current = '';
		for (let i = 0; i < str.length; i++) {
			const c = str.charAt(i);
			if (c === '[') depth++;
			if (c === ']') depth--;
			if (c === ',' && depth === 0) {
				result.push(current.trim());
				current = '';
			} else {
				current += c;
			}
		}
		if (current) result.push(current.trim());
		return result;
	}
}


class SchemaGraph extends Graph {
	constructor(eventBus) {
		super();
		this.eventBus = eventBus;
		this.schemas = {};
		this.nodeTypes = {};
		this.enabledSchemas = new Set();
	}

	registerSchema(schemaName, schemaCode, indexType = 'int', rootType = null) {
		try {
			console.log('=== REGISTERING SCHEMA:', schemaName, '===');
			
			const parsed = this._parseSchema(schemaCode);
			const fieldMapping = this._createFieldMappingFromSchema(schemaCode, parsed, rootType);
			
			this.schemas[schemaName] = { 
				code: schemaCode, 
				parsed, 
				indexType,
				rootType,
				fieldMapping
			};
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
		if (this.enabledSchemas.has(schemaName)) {
			return this.disableSchema(schemaName);
		} else {
			return this.enableSchema(schemaName);
		}
	}

	isSchemaEnabled(schemaName) {
		return this.enabledSchemas.has(schemaName);
	}

	getEnabledSchemas() {
		return Array.from(this.enabledSchemas);
	}

	_createFieldMappingFromSchema(schemaCode, parsedModels, rootType) {
		const mapping = { modelToField: {}, fieldToModel: {} };
		
		if (!rootType || !parsedModels[rootType]) {
			return this._createFallbackMapping(parsedModels);
		}
		
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
		if (current.kind === 'list' || current.kind === 'set' || current.kind === 'tuple') {
			current = current.inner;
		}
		
		if (current.kind === 'dict') {
			const innerStr = current.inner;
			if (innerStr && innerStr.indexOf('Union[') !== -1) {
				const unionMatch = innerStr.match(/Union\[([^\]]+)\]/);
				if (unionMatch) {
					const types = unionMatch[1].split(',').map(t => t.trim());
					for (const type of types) {
						if (type.endsWith('Config')) return type;
					}
				}
			}
			return null;
		}
		
		if (current.kind === 'union') {
			for (const type of current.types) {
				if (type.kind === 'basic' && type.name && type.name.endsWith('Config')) {
					return type.name;
				}
			}
			return null;
		}
		
		if (current.kind === 'basic') {
			if (current.name && current.name.endsWith('Config')) return current.name;
			return null;
		}
		
		return null;
	}
	
	_createFallbackMapping(parsedModels) {
		const mapping = { modelToField: {}, fieldToModel: {} };
		
		for (const modelName in parsedModels) {
			if (!parsedModels.hasOwnProperty(modelName)) continue;
			
			const baseName = modelName.replace(/Config$/, '');
			let fieldName = baseName
				.replace(/([A-Z]+)([A-Z][a-z])/g, '$1_$2')
				.replace(/([a-z\d])([A-Z])/g, '$1_$2')
				.toLowerCase();
			
			if (!fieldName.endsWith('s')) {
				if (fieldName.endsWith('y') && !['ay', 'ey', 'iy', 'oy', 'uy'].some(end => fieldName.endsWith(end))) {
					fieldName = fieldName.slice(0, -1) + 'ies';
				} else {
					fieldName = fieldName + 's';
				}
			}
			
			mapping.modelToField[modelName] = fieldName;
			mapping.fieldToModel[fieldName] = modelName;
		}
		
		return mapping;
	}

	modelNameToFieldName(modelName) {
		const baseName = modelName.replace(/Config$/, '');
		let fieldName = baseName
			.replace(/([A-Z]+)([A-Z][a-z])/g, '$1_$2')
			.replace(/([a-z\d])([A-Z])/g, '$1_$2')
			.toLowerCase();
		
		if (!fieldName.endsWith('s')) {
			if (fieldName.endsWith('y') && !['ay', 'ey', 'iy', 'oy', 'uy'].some(end => fieldName.endsWith(end))) {
				fieldName = fieldName.slice(0, -1) + 'ies';
			} else if (fieldName.endsWith('x') || fieldName.endsWith('ch') || fieldName.endsWith('sh')) {
				fieldName = fieldName + 'es';
			} else {
				fieldName = fieldName + 's';
			}
		}
		
		return fieldName;
	}

	_parseSchema(code) {
		const models = {};
		const lines = code.split('\n');
		let currentModel = null;
		let currentFields = [];
		
		for (let i = 0; i < lines.length; i++) {
			const line = lines[i].trim();
			const classMatch = line.match(/^class\s+(\w+)\s*\(/);
			if (classMatch) {
				if (currentModel) models[currentModel] = currentFields;
				currentModel = classMatch[1];
				currentFields = [];
				continue;
			}
			if (currentModel && line.indexOf(':') !== -1) {
				const fieldMatch = line.match(/^(\w+)\s*:\s*(.+?)(?:\s*=|$)/);
				if (fieldMatch) {
					currentFields.push({
						name: fieldMatch[1],
						type: this._parseType(fieldMatch[2].trim()),
						rawType: fieldMatch[2].trim()
					});
				}
			}
		}
		if (currentModel) models[currentModel] = currentFields;
		return models;
	}

	_parseType(str) {
		str = str.trim();
		if (str.indexOf('Optional[') === 0) {
			const inner = this._extractBracket(str, 9);
			return { kind: 'optional', inner: this._parseType(inner) };
		}
		if (str.indexOf('Union[') === 0) {
			const inner = this._extractBracket(str, 6);
			const types = this._splitTypes(inner);
			return { kind: 'union', types: types.map(t => this._parseType(t)) };
		}
		if (str.indexOf('List[') === 0) {
			const inner = this._extractBracket(str, 5);
			return { kind: 'list', inner: this._parseType(inner) };
		}
		if (str.indexOf('Set[') === 0) {
			const inner = this._extractBracket(str, 4);
			return { kind: 'set', inner: this._parseType(inner) };
		}
		if (str.indexOf('Tuple[') === 0) {
			const inner = this._extractBracket(str, 6);
			return { kind: 'tuple', inner: this._parseType(inner) };
		}
		if (str.indexOf('Dict[') === 0 || str.indexOf('dict[') === 0) {
			const startIdx = str.indexOf('[') + 1;
			const inner = this._extractBracket(str, startIdx);
			return { kind: 'dict', inner: inner };
		}
		return { kind: 'basic', name: str };
	}

	_extractBracket(str, start) {
		let depth = 1;
		let i = start;
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
		let depth = 0;
		let current = '';
		for (let i = 0; i < str.length; i++) {
			const c = str.charAt(i);
			if (c === '[') depth++;
			if (c === ']') depth--;
			if (c === ',' && depth === 0) {
				result.push(current.trim());
				current = '';
			} else {
				current += c;
			}
		}
		if (current) result.push(current.trim());
		return result;
	}

	_generateNodes(schemaName, models, indexType) {
		for (const modelName in models) {
			if (!models.hasOwnProperty(modelName)) continue;
			const fields = models[modelName];
			
			const self = this;
			const schemaInfo = this.schemas[schemaName];
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
						if (isOptional) {
							this.optionalFields[i] = true;
						}
						
						const isCollectionOfUnions = self._isCollectionOfUnions(f.type);
						const isListField = isRootType && self._isListFieldType(f.type);
						
						if (isCollectionOfUnions || isListField) {
							this.addInput(f.name, compactType);
							this.multiInputs[i] = { type: compactType, links: [] };
						} else {
							this.addInput(f.name, compactType);
							
							const isNative = self._isNativeType(compactType);
							if (isNative) {
								const baseType = self._getNativeBaseType(compactType);
								const defaultValue = self._getDefaultValueForType(baseType);
								this.nativeInputs[i] = {
									type: baseType,
									value: defaultValue,
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
									if (sourceNode && sourceNode.outputs[link.origin_slot]) {
										values.push(sourceNode.outputs[link.origin_slot].value);
									}
								}
							}
							if (values.length > 0) {
								data[this.inputs[i].name] = values;
							} else if (this.optionalFields[i]) {
								continue;
							}
						} else {
							const connectedVal = this.getInputData(i);
							if (connectedVal !== null && connectedVal !== undefined) {
								data[this.inputs[i].name] = connectedVal;
							} else if (this.nativeInputs[i] !== undefined) {
								const val = this.nativeInputs[i].value;
								const isOptional = this.nativeInputs[i].optional;
								const baseType = this.nativeInputs[i].type;
								
								if (baseType === 'bool') {
									if (val === true || val === false) {
										data[this.inputs[i].name] = val;
									} else if (val === 'true') {
										data[this.inputs[i].name] = true;
									} else if (val === 'false' || val === '') {
										if (!isOptional) {
											data[this.inputs[i].name] = false;
										}
									}
									continue;
								}
								
								const isEmpty = val === null || val === undefined || val === '';
								
								if (isOptional && isEmpty) {
									continue;
								}
								
								if (!isEmpty) {
									if (baseType === 'dict' || baseType === 'list' || baseType === 'set' || baseType === 'tuple') {
										try {
											data[this.inputs[i].name] = JSON.parse(val);
										} catch (e) {
											data[this.inputs[i].name] = baseType === 'dict' ? {} : [];
										}
									} else if (baseType === 'int') {
										data[this.inputs[i].name] = parseInt(val) || 0;
									} else if (baseType === 'float') {
										data[this.inputs[i].name] = parseFloat(val) || 0.0;
									} else {
										data[this.inputs[i].name] = val;
									}
								} else if (!isOptional) {
									if (baseType === 'int') data[this.inputs[i].name] = 0;
									else if (baseType === 'float') data[this.inputs[i].name] = 0.0;
									else if (baseType === 'dict') data[this.inputs[i].name] = {};
									else if (baseType === 'list' || baseType === 'set' || baseType === 'tuple') {
										data[this.inputs[i].name] = [];
									} else {
										data[this.inputs[i].name] = '';
									}
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
		const base = typeStr.replace(/^Optional\[|\]$/g, '').split('|')[0].trim();
		const nativeTypes = ['str', 'int', 'bool', 'float', 'string', 'integer', 'Index'];
		if (nativeTypes.indexOf(base) !== -1) return true;
		if (base.indexOf('Dict[') === 0 || base.indexOf('dict[') === 0) return true;
		if (base.indexOf('List[') === 0 || base.indexOf('list[') === 0) return true;
		if (base.indexOf('Set[') === 0 || base.indexOf('set[') === 0) return true;
		if (base.indexOf('Tuple[') === 0 || base.indexOf('tuple[') === 0) return true;
		return false;
	}

	_isCollectionOfUnions(fieldType) {
		let current = fieldType;
		if (current.kind === 'optional') current = current.inner;
		if (current.kind === 'list' || current.kind === 'set' || current.kind === 'tuple') {
			return current.inner && current.inner.kind === 'union';
		}
		if (current.kind === 'dict') {
			const innerStr = current.inner;
			if (innerStr && (innerStr.indexOf('Union[') !== -1 || innerStr.indexOf('union[') !== -1)) {
				return true;
			}
		}
		if (current.kind === 'basic' && current.name) {
			const name = current.name;
			if (name.indexOf('Dict[') === 0 || name.indexOf('dict[') === 0) {
				return name.indexOf('Union[') !== -1 || name.indexOf('union[') !== -1;
			}
		}
		return false;
	}

	_isListFieldType(fieldType) {
		let current = fieldType;
		if (current.kind === 'optional') current = current.inner;
		return current.kind === 'list';
	}

	_getNativeBaseType(typeStr) {
		if (!typeStr) return 'str';
		const base = typeStr.replace(/^Optional\[|\]$/g, '').split('|')[0].trim();
		if (base === 'int' || base === 'integer' || base === 'Index') return 'int';
		if (base === 'bool') return 'bool';
		if (base === 'float') return 'float';
		if (base.indexOf('Dict[') === 0 || base.indexOf('dict[') === 0) return 'dict';
		if (base.indexOf('List[') === 0 || base.indexOf('list[') === 0) return 'list';
		if (base.indexOf('Set[') === 0 || base.indexOf('set[') === 0) return 'set';
		if (base.indexOf('Tuple[') === 0 || base.indexOf('tuple[') === 0) return 'tuple';
		return 'str';
	}

	_getDefaultValueForType(baseType) {
		if (baseType === 'int') return 0;
		if (baseType === 'bool') return false;
		if (baseType === 'float') return 0.0;
		if (baseType === 'dict') return '{}';
		if (baseType === 'list') return '[]';
		if (baseType === 'set') return '[]';
		if (baseType === 'tuple') return '[]';
		return '';
	}

	_getInputType(field, indexType) {
		const t = field.type;
		if (t.kind === 'optional') {
			const innerType = this._getInputType({ type: t.inner }, indexType);
			return 'Optional[' + innerType + ']';
		}
		if (t.kind === 'union') {
			let hasIdx = false;
			let modelType = null;
			
			for (let i = 0; i < t.types.length; i++) {
				if (t.types[i].kind === 'basic' && t.types[i].name === indexType) {
					hasIdx = true;
				} else {
					modelType = t.types[i];
				}
			}
			
			if (hasIdx && modelType && t.types.length === 2) {
				return modelType.name || 'Model';
			}
			
			const names = t.types.map(tp => tp.name || tp.kind);
			return names.join('|');
		}
		if (t.kind === 'list') {
			const innerType = this._getInputType({ type: t.inner }, indexType);
			return 'List[' + innerType + ']';
		}
		if (t.kind === 'set') {
			const innerType = this._getInputType({ type: t.inner }, indexType);
			return 'Set[' + innerType + ']';
		}
		if (t.kind === 'tuple') {
			const innerType = this._getInputType({ type: t.inner }, indexType);
			return 'Tuple[' + innerType + ',...]';
		}
		if (t.kind === 'dict') {
			return 'Dict[' + t.inner + ']';
		}
		if (t.kind === 'basic') return t.name;
		return 'Any';
	}

	compactType(typeStr) {
		if (!typeStr) return typeStr;
		return typeStr.replace(/\s+/g, '');
	}

	getSchemaInfo(schemaName) {
		if (!this.schemas[schemaName]) return null;
		return {
			name: schemaName,
			indexType: this.schemas[schemaName].indexType,
			rootType: this.schemas[schemaName].rootType,
			models: Object.keys(this.schemas[schemaName].parsed)
		};
	}

	createNode(type) {
		const NodeClass = this.nodeTypes[type];
		if (!NodeClass) throw new Error('Unknown node type: ' + type);
		const node = new NodeClass();
		this.add(node);
		this.eventBus.emit('node:created', { type, nodeId: node.id });
		return node;
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
					for (let k = 0; k < links.length; k++) {
						const linkId = links[k];
						const link = this.links[linkId];
						if (link) {
							const targetNode = this.getNodeById(link.target_id);
							if (targetNode) {
								targetNode.inputs[link.target_slot].link = null;
							}
							delete this.links[linkId];
						}
					}
				}
				
				this.nodes.splice(i, 1);
				delete this._nodes_by_id[node.id];
			}
		}
		
		for (const type in this.nodeTypes) {
			if (this.nodeTypes.hasOwnProperty(type) && type.indexOf(schemaName + '.') === 0) {
				delete this.nodeTypes[type];
			}
		}
		
		delete this.schemas[schemaName];
		this.eventBus.emit('schema:removed', { schemaName });
		return true;
	}

	getRegisteredSchemas() {
		return Object.keys(this.schemas);
	}

	serialize(includeCamera = false, camera = null) {
		const data = {
			version: '1.0',
			nodes: [],
			links: []
		};
		
		for (const node of this.nodes) {
			const nodeData = {
				id: node.id,
				type: node.title,
				pos: node.pos.slice(),
				size: node.size.slice(),
				properties: JSON.parse(JSON.stringify(node.properties)),
				schemaName: node.schemaName,
				modelName: node.modelName,
				isNative: node.isNative || false,
				isRootType: node.isRootType || false
			};
			
			if (node.nativeInputs) {
				nodeData.nativeInputs = JSON.parse(JSON.stringify(node.nativeInputs));
			}
			
			if (node.multiInputs) {
				nodeData.multiInputs = JSON.parse(JSON.stringify(node.multiInputs));
			}
			
			if (node.color) {
				nodeData.color = node.color;
			}
			if (node.workflowData) {
				nodeData.workflowData = JSON.parse(JSON.stringify(node.workflowData));
			}
			
			data.nodes.push(nodeData);
		}
		
		for (const linkId in this.links) {
			if (this.links.hasOwnProperty(linkId)) {
				const link = this.links[linkId];
				const linkData = {
					id: link.id,
					origin_id: link.origin_id,
					origin_slot: link.origin_slot,
					target_id: link.target_id,
					target_slot: link.target_slot,
					type: link.type
				};
				
				if (link.workflowData) {
					linkData.workflowData = JSON.parse(JSON.stringify(link.workflowData));
				}
				if (link.conditionType) {
					linkData.conditionType = link.conditionType;
				}
				if (link.conditionInfo) {
					linkData.conditionInfo = JSON.parse(JSON.stringify(link.conditionInfo));
				}
				if (link.isConditional) {
					linkData.isConditional = link.isConditional;
				}
				if (link.conditionLabel) {
					linkData.conditionLabel = link.conditionLabel;
				}
				
				data.links.push(linkData);
			}
		}
		
		if (includeCamera && camera) {
			data.camera = {
				x: camera.x,
				y: camera.y,
				scale: camera.scale
			};
		}
		
		return data;
	}

	deserialize(data, restoreCamera = false, camera = null) {
		this.nodes = [];
		this.links = {};
		this._nodes_by_id = {};
		this.last_link_id = 0;
		
		if (!data || !data.nodes) {
			throw new Error('Invalid graph data');
		}
		
		for (const nodeData of data.nodes) {
			let nodeTypeKey;
			if (nodeData.isNative) {
				nodeTypeKey = 'Native.' + nodeData.type;
			} else if (nodeData.schemaName && nodeData.modelName) {
				nodeTypeKey = nodeData.schemaName + '.' + nodeData.modelName;
			} else {
				nodeTypeKey = nodeData.type;
			}
			
			if (!this.nodeTypes[nodeTypeKey]) {
				console.warn('Node type not found:', nodeTypeKey);
				continue;
			}
			
			const node = new (this.nodeTypes[nodeTypeKey])();
			node.id = nodeData.id;
			node.pos = nodeData.pos.slice();
			node.size = nodeData.size.slice();
			node.properties = JSON.parse(JSON.stringify(nodeData.properties));
			
			if (nodeData.isRootType !== undefined) {
				node.isRootType = nodeData.isRootType;
			}
			
			if (nodeData.nativeInputs) {
				node.nativeInputs = JSON.parse(JSON.stringify(nodeData.nativeInputs));
			}
			
			if (nodeData.multiInputs) {
				node.multiInputs = JSON.parse(JSON.stringify(nodeData.multiInputs));
			}
			
			if (nodeData.color) {
				node.color = nodeData.color;
			}
			if (nodeData.workflowData) {
				node.workflowData = JSON.parse(JSON.stringify(nodeData.workflowData));
			}
			
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
					
					if (targetNode.multiInputs && targetNode.multiInputs[linkData.target_slot]) {
						targetNode.multiInputs[linkData.target_slot].links.push(linkData.id);
					} else {
						targetNode.inputs[linkData.target_slot].link = linkData.id;
					}
					
					if (linkData.workflowData) {
						link.workflowData = JSON.parse(JSON.stringify(linkData.workflowData));
					}
					if (linkData.conditionType) {
						link.conditionType = linkData.conditionType;
					}
					if (linkData.conditionInfo) {
						link.conditionInfo = JSON.parse(JSON.stringify(linkData.conditionInfo));
					}
					if (linkData.isConditional) {
						link.isConditional = linkData.isConditional;
					}
					if (linkData.conditionLabel) {
						link.conditionLabel = linkData.conditionLabel;
					}
					
					if (linkData.id > this.last_link_id) {
						this.last_link_id = linkData.id;
					}
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


class MouseTouchController {
	constructor(canvas, eventBus) {
		this.canvas = canvas;
		this.eventBus = eventBus;
		this.setupListeners();
	}

	setupListeners() {
		this.canvas.addEventListener('mousedown', (e) => this.handleMouseDown(e));
		this.canvas.addEventListener('mousemove', (e) => this.handleMouseMove(e));
		this.canvas.addEventListener('mouseup', (e) => this.handleMouseUp(e));
		this.canvas.addEventListener('dblclick', (e) => this.handleDoubleClick(e));
		this.canvas.addEventListener('wheel', (e) => this.handleWheel(e));
		this.canvas.addEventListener('contextmenu', (e) => this.handleContextMenu(e));
	}

	handleMouseDown(e) {
		const coords = this.getCanvasCoordinates(e);
		this.eventBus.emit('mouse:down', { button: e.button, coords, event: e });
		this.eventBus.emit('interaction', { type: 'mouse:down' });
	}

	handleMouseMove(e) {
		const coords = this.getCanvasCoordinates(e);
		this.eventBus.emit('mouse:move', { coords, event: e });
	}

	handleMouseUp(e) {
		const coords = this.getCanvasCoordinates(e);
		this.eventBus.emit('mouse:up', { button: e.button, coords, event: e });
		this.eventBus.emit('interaction', { type: 'mouse:up' });
	}

	handleDoubleClick(e) {
		const coords = this.getCanvasCoordinates(e);
		this.eventBus.emit('mouse:dblclick', { coords, event: e });
		this.eventBus.emit('interaction', { type: 'mouse:dblclick' });
	}

	handleWheel(e) {
		e.preventDefault();
		const coords = this.getCanvasCoordinates(e);
		this.eventBus.emit('mouse:wheel', { delta: e.deltaY, coords, event: e });
		this.eventBus.emit('interaction', { type: 'mouse:wheel' });
	}

	handleContextMenu(e) {
		e.preventDefault();
		const coords = this.getCanvasCoordinates(e);
		this.eventBus.emit('mouse:contextmenu', { coords, event: e });
		this.eventBus.emit('interaction', { type: 'contextmenu' });
	}

	getCanvasCoordinates(e) {
		const rect = this.canvas.getBoundingClientRect();
		const sx = e.clientX - rect.left;
		const sy = e.clientY - rect.top;
		return {
			screenX: (sx / rect.width) * this.canvas.width,
			screenY: (sy / rect.height) * this.canvas.height,
			clientX: e.clientX,
			clientY: e.clientY,
			rect: rect
		};
	}
}

class KeyboardController {
	constructor(eventBus) {
		this.eventBus = eventBus;
		this.setupListeners();
	}

	setupListeners() {
		document.addEventListener('keydown', (e) => this.handleKeyDown(e));
		document.addEventListener('keyup', (e) => this.handleKeyUp(e));
	}

	handleKeyDown(e) {
		this.eventBus.emit('keyboard:down', { key: e.key, code: e.code, event: e });
		this.eventBus.emit('interaction', { type: 'keyboard:down' });
	}

	handleKeyUp(e) {
		this.eventBus.emit('keyboard:up', { key: e.key, code: e.code, event: e });
		this.eventBus.emit('interaction', { type: 'keyboard:up' });
	}
}

class VoiceController {
	constructor(eventBus) {
		this.eventBus = eventBus;
		this.recognition = null;
		this.isListening = false;
		this.setupRecognition();
	}

	setupRecognition() {
		if ('webkitSpeechRecognition' in window || 'SpeechRecognition' in window) {
			const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
			this.recognition = new SpeechRecognition();
			this.recognition.continuous = false;
			this.recognition.interimResults = false;
			
			this.recognition.onresult = (event) => {
				const transcript = event.results[0][0].transcript;
				this.eventBus.emit('voice:result', { transcript, confidence: event.results[0][0].confidence });
				this.eventBus.emit('interaction', { type: 'voice:result' });
			};
			
			this.recognition.onerror = (event) => {
				this.eventBus.emit('voice:error', { error: event.error });
			};
			
			this.recognition.onend = () => {
				this.isListening = false;
				this.eventBus.emit('voice:stopped', {});
			};
		} else {
			console.warn('Speech recognition not supported');
		}
	}

	startListening() {
		if (this.recognition && !this.isListening) {
			this.recognition.start();
			this.isListening = true;
			this.eventBus.emit('voice:started', {});
		}
	}

	stopListening() {
		if (this.recognition && this.isListening) {
			this.recognition.stop();
		}
	}
}

class DrawingStyleManager {
	constructor() {
		this.currentStyle = 'default';
		this.styles = {
			default: {
				name: 'Default',
				nodeCornerRadius: 6,
				nodeShadowBlur: 10,
				nodeShadowOffset: 2,
				linkWidth: 2.5,
				linkShadowBlur: 6,
				linkCurve: 0.5,
				slotRadius: 4,
				slotHighlightRadius: 8,
				gridOpacity: 1.0,
				textFont: 'Arial, sans-serif',
				useGradient: false,
				useGlow: false,
				useDashed: false
			},
			minimal: {
				name: 'Minimal',
				nodeCornerRadius: 2,
				nodeShadowBlur: 0,
				nodeShadowOffset: 0,
				linkWidth: 1.5,
				linkShadowBlur: 0,
				linkCurve: 0.5,
				slotRadius: 3,
				slotHighlightRadius: 6,
				gridOpacity: 0.3,
				textFont: 'Arial, sans-serif',
				useGradient: false,
				useGlow: false,
				useDashed: false
			},
			blueprint: {
				name: 'Blueprint',
				nodeCornerRadius: 0,
				nodeShadowBlur: 0,
				nodeShadowOffset: 0,
				linkWidth: 1.5,
				linkShadowBlur: 8,
				linkCurve: 0,
				slotRadius: 3,
				slotHighlightRadius: 7,
				gridOpacity: 1.5,
				textFont: 'Courier New, monospace',
				useGradient: false,
				useGlow: true,
				useDashed: true
			},
			neon: {
				name: 'Neon',
				nodeCornerRadius: 8,
				nodeShadowBlur: 20,
				nodeShadowOffset: 0,
				linkWidth: 3,
				linkShadowBlur: 15,
				linkCurve: 0.6,
				slotRadius: 5,
				slotHighlightRadius: 12,
				gridOpacity: 0.5,
				textFont: 'Arial, sans-serif',
				useGradient: true,
				useGlow: true,
				useDashed: false
			},
			organic: {
				name: 'Organic',
				nodeCornerRadius: 15,
				nodeShadowBlur: 12,
				nodeShadowOffset: 3,
				linkWidth: 4,
				linkShadowBlur: 8,
				linkCurve: 0.7,
				slotRadius: 6,
				slotHighlightRadius: 10,
				gridOpacity: 0.7,
				textFont: 'Georgia, serif',
				useGradient: true,
				useGlow: false,
				useDashed: false
			},
			wireframe: {
				name: 'Wireframe',
				nodeCornerRadius: 0,
				nodeShadowBlur: 0,
				nodeShadowOffset: 0,
				linkWidth: 1,
				linkShadowBlur: 0,
				linkCurve: 0.5,
				slotRadius: 2,
				slotHighlightRadius: 5,
				gridOpacity: 0.8,
				textFont: 'Courier New, monospace',
				useGradient: false,
				useGlow: false,
				useDashed: true
			}
		};
	}

	setStyle(styleName) {
		if (this.styles[styleName]) {
			this.currentStyle = styleName;
			localStorage.setItem('schemagraph-drawing-style', styleName);
			return true;
		}
		return false;
	}

	getStyle() {
		return this.styles[this.currentStyle];
	}

	getCurrentStyleName() {
		return this.currentStyle;
	}

	loadSavedStyle() {
		const saved = localStorage.getItem('schemagraph-drawing-style');
		if (saved && this.styles[saved]) {
			this.currentStyle = saved;
		}
	}
}


class SchemaGraphApp {
	constructor(canvasId) {
		this.eventBus = new EventBus();
		this.analytics = new AnalyticsService(this.eventBus);
		
		this.canvas = document.getElementById(canvasId);
		this.ctx = this.canvas.getContext('2d');
		
		this.mouseController = new MouseTouchController(this.canvas, this.eventBus);
		this.keyboardController = new KeyboardController(this.eventBus);
		this.voiceController = new VoiceController(this.eventBus);
		
		this.initializeState();
		
		this.injectDialogHTML();
		this.injectCanvasElementsHTML();
		this.injectToolbarHTML();
		this.injectAnalyticsPanelHTML();

		this.api = this._createAPI();
		this.ui = this._createUI();
		
		this.setupEventListeners();
		this.setupCanvasLeaveHandler();
		this.setupVoiceCommands();
		this.registerNativeNodes();
		
		this.ui.init();
		
		this.ui.util.resizeCanvas();
		this.draw();
		
		this.eventBus.emit('app:ready', {});
		console.log('=== SCHEMAGRAPH READY ===');
	}

	initializeState() {
		this.graph = new SchemaGraph(this.eventBus);
		this.camera = { x: 0, y: 0, scale: 1.0 };
		
		this.selectedNodes = new Set();
		this.selectedNode = null;
		this.selectionRect = null;
		this.selectionStart = null;
		this.isMouseDown = false;
		this.previewSelection = new Set();
		this.dragNode = null;
		this.dragOffset = [0, 0];
		this.connecting = null;
		this.mousePos = [0, 0];
		this.isPanning = false;
		this.panStart = [0, 0];
		this.spacePressed = false;
		this.editingNode = null;
		this.pendingSchemaCode = null;
		this.customContextMenuHandler = null;
		
		this.themes = ['dark', 'light', 'ocean'];
		this.currentThemeIndex = 0;
		this.loadTheme();
		
		this.drawingStyleManager = new DrawingStyleManager();
		this.drawingStyleManager.loadSavedStyle();
		
		this.textScalingMode = 'fixed';
		this.loadTextScalingMode();

		// Add lock mode state
		this.isLocked     = false;
		this.lockReason   = null;
		this.lockPending  = null;
		this.lockInterval = null;
	}

	/**
	 * Lock the graph to prevent modifications (only node movement allowed)
	 * @param {string} reason - Reason for locking (shown in UI)
	 */
	lock(reason = 'Graph locked', pending = true) {
		this.lockReason  = reason;

		if (!this.isLocked) {
			this.isLocked = true;
			
			// Cancel any in-progress operations
			this.connecting = null;
			this.selectionRect = null;
			this.selectionStart = null;
			this.editingNode = null;
			
			// Hide context menu
			document.getElementById('sg-contextMenu')?.classList.remove('show');
			
			// Hide any open dialogs
			document.getElementById('sg-schemaDialog')?.classList.remove('show');
			document.getElementById('sg-schemaRemovalDialog')?.classList.remove('show');
			
			// Update cursor
			this.canvas.classList.add('sg-locked');
		}

		if (pending) {
			const self = this;
			this.lockPending  = 0;
			this.lockInterval = setInterval(() => {
				self.lockPending = (self.lockPending + 1) % 3;
				self.draw();
			}, 500);
		}

		this.eventBus.emit('graph:locked', { reason });
		this.draw();
	}

	/**
	 * Unlock the graph to allow modifications
	 */
	unlock() {
		if (!this.isLocked) return;

		this.isLocked   = false;
		this.lockReason = null;
		
		if (this.lockInterval) {
			clearInterval(this.lockInterval);
			this.lockInterval = null;
			this.lockPending  = null;
		}
		
		this.canvas.classList.remove('sg-locked');
		
		this.eventBus.emit('graph:unlocked', {});
		this.draw();
	}

	/**
	 * Check if graph is locked
	 * @returns {boolean}
	 */
	isGraphLocked() {
		return this.isLocked;
	}

	injectDialogHTML() {
		if (document.getElementById('sg-messageDialog')) {
			return;
		}

		const messageDialog = document.createElement('div');
		messageDialog.id = 'sg-messageDialog';
		messageDialog.className = 'sg-dialog-overlay';
		messageDialog.innerHTML = `
			<div class="sg-dialog">
				<div class="sg-dialog-header" id="sg-messageDialogTitle">Message</div>
				<div class="sg-dialog-body">
					<div id="sg-messageDialogContent" style="white-space: pre-line; line-height: 1.6;"></div>
				</div>
				<div class="sg-dialog-footer">
					<button id="sg-messageDialogOk" class="sg-dialog-btn sg-dialog-btn-confirm">OK</button>
				</div>
			</div>
		`;

		const confirmDialog = document.createElement('div');
		confirmDialog.id = 'sg-confirmDialog';
		confirmDialog.className = 'sg-dialog-overlay';
		confirmDialog.innerHTML = `
			<div class="sg-dialog">
				<div class="sg-dialog-header" id="sg-confirmDialogTitle">Confirm</div>
				<div class="sg-dialog-body">
					<div id="sg-confirmDialogContent" style="white-space: pre-line; line-height: 1.6;"></div>
				</div>
				<div class="sg-dialog-footer">
					<button id="sg-confirmDialogCancel" class="sg-dialog-btn sg-dialog-btn-cancel">Cancel</button>
					<button id="sg-confirmDialogOk" class="sg-dialog-btn sg-dialog-btn-confirm">OK</button>
				</div>
			</div>
		`;

		document.body.appendChild(messageDialog);
		document.body.appendChild(confirmDialog);

		messageDialog.addEventListener('click', (e) => {
			if (e.target === messageDialog) {
				const okBtn = document.getElementById('sg-messageDialogOk');
				okBtn?.click();
			}
		});

		confirmDialog.addEventListener('click', (e) => {
			if (e.target === confirmDialog) {
				const cancelBtn = document.getElementById('sg-confirmDialogCancel');
				cancelBtn?.click();
			}
		});

		console.log('✨ SchemaGraph dialogs injected');
	}

	/**
	 * Inject canvas overlay elements (context menu, node input, schema dialogs)
	 * @private
	 */
	injectCanvasElementsHTML() {
		const canvasContainer = this.canvas.parentElement;
		if (!canvasContainer) {
			console.warn('Cannot inject canvas elements: container not found');
			return;
		}

		// Context Menu
		if (!document.getElementById('sg-contextMenu')) {
			const contextMenu = document.createElement('div');
			contextMenu.id = 'sg-contextMenu';
			contextMenu.className = 'sg-context-menu';
			canvasContainer.appendChild(contextMenu);
		}

		// Node Input Overlay
		if (!document.getElementById('sg-nodeInput')) {
			const nodeInput = document.createElement('input');
			nodeInput.type = 'text';
			nodeInput.id = 'sg-nodeInput';
			nodeInput.className = 'sg-node-input-overlay';
			canvasContainer.appendChild(nodeInput);
		}

		// Schema Registration Dialog
		if (!document.getElementById('sg-schemaDialog')) {
			const schemaDialog = document.createElement('div');
			schemaDialog.id = 'sg-schemaDialog';
			schemaDialog.className = 'sg-dialog-overlay';
			schemaDialog.innerHTML = `
				<div class="sg-dialog">
					<div class="sg-dialog-header">Register Pydantic Schema</div>
					<div class="sg-dialog-body">
						<div class="sg-dialog-field">
							<label for="sg-schemaNameInput">Schema Name:</label>
							<input type="text" id="sg-schemaNameInput" placeholder="e.g., MySchema" />
						</div>
						<div class="sg-dialog-field">
							<label for="sg-schemaIndexTypeInput">Index Type:</label>
							<input type="text" id="sg-schemaIndexTypeInput" placeholder="e.g., Index, int" />
							<small>The type used for index references (default: int)</small>
						</div>
						<div class="sg-dialog-field">
							<label for="sg-schemaRootTypeInput">Root Type:</label>
							<input type="text" id="sg-schemaRootTypeInput" placeholder="e.g., AppConfig" />
							<small>The main config class that contains lists of other models</small>
						</div>
					</div>
					<div class="sg-dialog-footer">
						<button id="sg-schemaDialogCancel" class="sg-dialog-btn sg-dialog-btn-cancel">Cancel</button>
						<button id="sg-schemaDialogConfirm" class="sg-dialog-btn sg-dialog-btn-confirm">Register</button>
					</div>
				</div>
			`;
			document.body.appendChild(schemaDialog);
		}

		// Schema Removal Dialog
		if (!document.getElementById('sg-schemaRemovalDialog')) {
			const schemaRemovalDialog = document.createElement('div');
			schemaRemovalDialog.id = 'sg-schemaRemovalDialog';
			schemaRemovalDialog.className = 'sg-dialog-overlay';
			schemaRemovalDialog.innerHTML = `
				<div class="sg-dialog">
					<div class="sg-dialog-header">⚠️ Remove Schema</div>
					<div class="sg-dialog-body">
						<div class="sg-dialog-field">
							<label for="sg-schemaRemovalNameInput">Schema to Remove:</label>
							<select id="sg-schemaRemovalNameInput" class="sg-dialog-select"></select>
							<small style="color: var(--sg-accent-red); margin-top: 8px;">Warning: This will permanently delete all nodes of this schema type from the graph!</small>
						</div>
					</div>
					<div class="sg-dialog-footer">
						<button id="sg-schemaRemovalCancel" class="sg-dialog-btn sg-dialog-btn-cancel">Cancel</button>
						<button id="sg-schemaRemovalConfirm" class="sg-dialog-btn sg-dialog-btn-confirm" style="background: var(--sg-accent-red);">Remove Schema</button>
					</div>
				</div>
			`;
			document.body.appendChild(schemaRemovalDialog);
		}

		console.log('✨ SchemaGraph canvas elements injected');
	}

	/**
	 * Inject toolbar HTML into the canvas container (self-contained library)
	 * Creates a compact corner toggle with expandable toolbar
	 * @private
	 */
	injectToolbarHTML() {
		const canvasContainer = this.canvas.parentElement;
		if (!canvasContainer) {
			console.warn('Cannot inject toolbar: canvas container not found');
			return;
		}
	
		if (document.getElementById('sg-toolbarToggle')) {
			return;
		}
	
		const toggleBtn = document.createElement('button');
		toggleBtn.id = 'sg-toolbarToggle';
		toggleBtn.className = 'sg-toolbar-toggle-corner';
		toggleBtn.title = 'Toggle toolbar';
		toggleBtn.innerHTML = `
			<span class="sg-toolbar-toggle-icon">⚙️</span>
		`;
	
		const toolbarPanel = document.createElement('div');
		toolbarPanel.id = 'sg-toolbarPanel';
		toolbarPanel.className = 'sg-toolbar-panel';
		toolbarPanel.innerHTML = `
			<div class="sg-toolbar-header">
				<span class="sg-toolbar-title">⚙️ Toolbar</span>
				<button id="sg-toolbarClose" class="sg-toolbar-close">✕</button>
			</div>
			
			<div class="sg-toolbar-content" id="sg-toolbarContent">
				<div class="sg-toolbar-section">
					<span class="sg-toolbar-label">🎤 Voice</span>
					<button id="sg-voiceStartBtn" class="sg-toolbar-btn">Start</button>
					<button id="sg-voiceStopBtn" class="sg-toolbar-btn" style="display: none;">Stop</button>
					<span id="sg-voiceStatus" class="sg-toolbar-status"></span>
				</div>
				
				<div class="sg-toolbar-divider"></div>
				
				<div class="sg-toolbar-section">
					<button id="sg-analyticsToggleBtn" class="sg-toolbar-btn">📊 Analytics</button>
				</div>
				
				<div class="sg-toolbar-divider"></div>
				
				<div class="sg-toolbar-section">
					<span class="sg-toolbar-label">Schema</span>
					<button id="sg-uploadSchemaBtn" class="sg-toolbar-btn sg-toolbar-btn-primary">📤 Upload</button>
					<button id="sg-exportBtn" class="sg-toolbar-btn">Export Graph</button>
					<button id="sg-importBtn" class="sg-toolbar-btn">Import Graph</button>
					<button id="sg-exportConfigBtn" class="sg-toolbar-btn">Export Config</button>
					<button id="sg-importConfigBtn" class="sg-toolbar-btn">Import Config</button>
				</div>
				
				<div class="sg-toolbar-divider"></div>
				
				<div class="sg-toolbar-section">
					<span class="sg-toolbar-label">View</span>
					<button id="sg-centerViewBtn" class="sg-toolbar-btn" title="Center view">🎯 Center</button>
					<select id="sg-layoutSelect" class="sg-toolbar-select">
						<option value="">🔧 Layout...</option>
						<option value="hierarchical-vertical">Hierarchical ↓</option>
						<option value="hierarchical-horizontal">Hierarchical →</option>
						<option value="force-directed">Force-Directed</option>
						<option value="grid">Grid</option>
						<option value="circular">Circular</option>
					</select>
				</div>
				
				<div class="sg-toolbar-divider"></div>
				
				<div class="sg-toolbar-section">
					<span class="sg-toolbar-label">Style</span>
					<select id="sg-drawingStyleSelect" class="sg-toolbar-select">
						<option value="default">🎨 Default</option>
						<option value="minimal">✨ Minimal</option>
						<option value="blueprint">📐 Blueprint</option>
						<option value="neon">💫 Neon</option>
						<option value="organic">🌿 Organic</option>
						<option value="wireframe">📊 Wireframe</option>
					</select>
					<button id="sg-textScalingToggle" class="sg-toolbar-btn sg-toolbar-btn-toggle">
						<span class="sg-toolbar-toggle-label" id="sg-textScalingLabel">Text: Fixed</span>
					</button>
					<button id="sg-themeBtn" class="sg-toolbar-btn" title="Switch theme">🎨 Theme</button>
				</div>
				
				<div class="sg-toolbar-divider"></div>
				
				<div class="sg-toolbar-section">
					<span class="sg-toolbar-label">Zoom</span>
					<span class="sg-toolbar-zoom-value" id="sg-zoomLevel">100%</span>
					<button id="sg-resetZoomBtn" class="sg-toolbar-btn" title="Reset zoom">⟲</button>
				</div>
			</div>
		`;
	
		canvasContainer.appendChild(toggleBtn);
		canvasContainer.appendChild(toolbarPanel);
	
		const closeBtn = document.getElementById('sg-toolbarClose');
		
		const showToolbar = () => {
			toolbarPanel.classList.add('show');
			toggleBtn.classList.add('active');
		};
		
		const hideToolbar = () => {
			toolbarPanel.classList.add('hiding');
			toggleBtn.classList.remove('active');
			setTimeout(() => {
				toolbarPanel.classList.remove('show', 'hiding');
			}, 300);
		};
	
		toggleBtn.addEventListener('click', (e) => {
			e.stopPropagation();
			if (toolbarPanel.classList.contains('show')) {
				hideToolbar();
			} else {
				showToolbar();
			}
		});
	
		closeBtn?.addEventListener('click', (e) => {
			e.stopPropagation();
			hideToolbar();
		});
	
		document.addEventListener('click', (e) => {
			const isVisible = toolbarPanel.classList.contains('show');
			if (!isVisible) return;
			
			const clickedInsidePanel = toolbarPanel.contains(e.target);
			const clickedToggle = toggleBtn.contains(e.target);
			const clickedDialog = e.target.closest('.sg-dialog-overlay');
			const clickedAnalytics = e.target.closest('#sg-analyticsPanel');
			
			if (!clickedInsidePanel && !clickedToggle && !clickedDialog && !clickedAnalytics) {
				hideToolbar();
			}
		});
	
		const hiddenInputs = document.createElement('div');
		hiddenInputs.style.display = 'none';
		hiddenInputs.innerHTML = `
			<input type="file" id="sg-uploadSchemaFile" accept=".py" />
			<input type="file" id="sg-importFile" accept=".json" />
			<input type="file" id="sg-importConfigFile" accept=".json" />
		`;
		document.body.appendChild(hiddenInputs);
	
		console.log('✨ SchemaGraph toolbar injected');
	}

	/**
	 * Inject analytics panel HTML into the DOM (self-contained library)
	 * Creates the analytics dashboard
	 * @private
	 */
	injectAnalyticsPanelHTML() {
		if (document.getElementById('sg-analyticsPanel')) {
			return;
		}
	
		const panel = document.createElement('div');
		panel.id = 'sg-analyticsPanel';
		panel.className = 'sg-analytics-panel';
		panel.innerHTML = `
			<div class="sg-analytics-header">
				<div class="sg-analytics-title">📊 Analytics Dashboard</div>
				<button id="sg-analyticsCloseBtn" class="sg-analytics-close">✕</button>
			</div>
			
			<div class="sg-analytics-section">
				<div class="sg-analytics-section-title">Session Info</div>
				<div class="sg-analytics-metric">
					<span class="sg-analytics-metric-name">Session ID:</span>
					<span class="sg-analytics-metric-value" id="sg-sessionId">-</span>
				</div>
				<div class="sg-analytics-metric">
					<span class="sg-analytics-metric-name">Duration:</span>
					<span class="sg-analytics-metric-value" id="sg-sessionDuration">-</span>
				</div>
				<div class="sg-analytics-metric">
					<span class="sg-analytics-metric-name">Total Events:</span>
					<span class="sg-analytics-metric-value" id="sg-totalEvents">-</span>
				</div>
			</div>
			
			<div class="sg-analytics-section">
				<div class="sg-analytics-section-title">Graph Operations</div>
				<div class="sg-analytics-metric">
					<span class="sg-analytics-metric-name">Nodes Created:</span>
					<span class="sg-analytics-metric-value" id="sg-nodesCreated">0</span>
				</div>
				<div class="sg-analytics-metric">
					<span class="sg-analytics-metric-name">Nodes Deleted:</span>
					<span class="sg-analytics-metric-value" id="sg-nodesDeleted">0</span>
				</div>
				<div class="sg-analytics-metric">
					<span class="sg-analytics-metric-name">Links Created:</span>
					<span class="sg-analytics-metric-value" id="sg-linksCreated">0</span>
				</div>
				<div class="sg-analytics-metric">
					<span class="sg-analytics-metric-name">Links Deleted:</span>
					<span class="sg-analytics-metric-value" id="sg-linksDeleted">0</span>
				</div>
			</div>
			
			<div class="sg-analytics-section">
				<div class="sg-analytics-section-title">Schema Operations</div>
				<div class="sg-analytics-metric">
					<span class="sg-analytics-metric-name">Schemas Registered:</span>
					<span class="sg-analytics-metric-value" id="sg-schemasRegistered">0</span>
				</div>
				<div class="sg-analytics-metric">
					<span class="sg-analytics-metric-name">Schemas Removed:</span>
					<span class="sg-analytics-metric-value" id="sg-schemasRemoved">0</span>
				</div>
			</div>
			
			<div class="sg-analytics-section">
				<div class="sg-analytics-section-title">File Operations</div>
				<div class="sg-analytics-metric">
					<span class="sg-analytics-metric-name">Graphs Exported:</span>
					<span class="sg-analytics-metric-value" id="sg-graphsExported">0</span>
				</div>
				<div class="sg-analytics-metric">
					<span class="sg-analytics-metric-name">Graphs Imported:</span>
					<span class="sg-analytics-metric-value" id="sg-graphsImported">0</span>
				</div>
				<div class="sg-analytics-metric">
					<span class="sg-analytics-metric-name">Configs Exported:</span>
					<span class="sg-analytics-metric-value" id="sg-configsExported">0</span>
				</div>
				<div class="sg-analytics-metric">
					<span class="sg-analytics-metric-name">Configs Imported:</span>
					<span class="sg-analytics-metric-value" id="sg-configsImported">0</span>
				</div>
			</div>
			
			<div class="sg-analytics-section">
				<div class="sg-analytics-section-title">User Interactions</div>
				<div class="sg-analytics-metric">
					<span class="sg-analytics-metric-name">Total Interactions:</span>
					<span class="sg-analytics-metric-value" id="sg-totalInteractions">0</span>
				</div>
				<div class="sg-analytics-metric">
					<span class="sg-analytics-metric-name">Layouts Applied:</span>
					<span class="sg-analytics-metric-value" id="sg-layoutsApplied">0</span>
				</div>
				<div class="sg-analytics-metric">
					<span class="sg-analytics-metric-name">Errors:</span>
					<span class="sg-analytics-metric-value" id="sg-errorCount">0</span>
				</div>
			</div>
			
			<button id="sg-refreshAnalyticsBtn" class="sg-analytics-btn">🔄 Refresh</button>
			<button id="sg-exportAnalyticsBtn" class="sg-analytics-btn">💾 Export Analytics</button>
			<button id="sg-resetAnalyticsBtn" class="sg-analytics-btn">🗑️ Reset Session</button>
		`;
	
		document.body.appendChild(panel);
	
		console.log('✨ SchemaGraph analytics panel injected');
	}

	setupEventListeners() {
		this.eventBus.on('mouse:down', (data) => this.handleMouseDown(data));
		this.eventBus.on('mouse:move', (data) => this.handleMouseMove(data));
		this.eventBus.on('mouse:up', (data) => this.handleMouseUp(data));
		this.eventBus.on('mouse:dblclick', (data) => this.handleDoubleClick(data));
		this.eventBus.on('mouse:wheel', (data) => this.handleWheel(data));
		this.eventBus.on('mouse:contextmenu', (data) => this.handleContextMenu(data));
		
		this.eventBus.on('keyboard:down', (data) => this.handleKeyDown(data));
		this.eventBus.on('keyboard:up', (data) => this.handleKeyUp(data));
		
		this.eventBus.on('ui:update', (data) => {
			const element = document.getElementById('sg-' + data.id);
			if (element && data.content !== undefined) {
				element.textContent = data.content;
			}
		});
		
		this.eventBus.on('node:created', () => {
			this.ui.update.schemaList();
			this.ui.update.nodeTypesList();
			this.draw();
		});
		
		this.eventBus.on('node:deleted', () => {
			this.ui.update.schemaList();
			this.draw();
		});
		
		this.eventBus.on('link:created', () => this.draw());
		this.eventBus.on('link:deleted', () => this.draw());
		
		this.eventBus.on('schema:registered', () => {
			this.ui.update.schemaList();
			this.ui.update.nodeTypesList();
			this.draw();
		});
		
		this.eventBus.on('schema:removed', () => {
			this.ui.update.schemaList();
			this.ui.update.nodeTypesList();
			this.draw();
		});
		
		const nodeInput = document.getElementById('sg-nodeInput');
		nodeInput.addEventListener('blur', () => this.handleInputBlur());
		nodeInput.addEventListener('keydown', (e) => this.handleInputKeyDown(e));
	}

	setupCanvasLeaveHandler() {
		this.canvas.addEventListener('mouseleave', () => {
			if (this.selectionRect) {
				this.selectionRect = null;
				this.selectionStart = null;
				this.isMouseDown = false;
				this.previewSelection.clear();
				this.draw();
			}
		});
	}

	updateTextScalingUI() {
		this.ui.update.textScaling();
	}

	loadTextScalingMode() {
		const saved = localStorage.getItem('schemagraph-text-scaling');
		if (saved === 'scaled' || saved === 'fixed') {
			this.textScalingMode = saved;
		}
	}

	saveTextScalingMode() {
		localStorage.setItem('schemagraph-text-scaling', this.textScalingMode);
	}

	getTextScale() {
		return this.textScalingMode === 'fixed' ? (1 / this.camera.scale) : 1;
	}

	updateAnalyticsDisplay() {
		if (!this.analytics) return;
		
		const metrics = this.analytics.getMetrics();
		const sessionMetrics = this.analytics.getSessionMetrics();
		
		document.getElementById('sg-sessionId').textContent = sessionMetrics.sessionId.substring(0, 8);
		document.getElementById('sg-sessionDuration').textContent = this.formatDuration(sessionMetrics.duration);
		document.getElementById('sg-totalEvents').textContent = sessionMetrics.events;
		
		document.getElementById('sg-nodesCreated').textContent = metrics.nodeCreated;
		document.getElementById('sg-nodesDeleted').textContent = metrics.nodeDeleted;
		document.getElementById('sg-linksCreated').textContent = metrics.linkCreated;
		document.getElementById('sg-linksDeleted').textContent = metrics.linkDeleted;
		
		document.getElementById('sg-schemasRegistered').textContent = metrics.schemaRegistered;
		document.getElementById('sg-schemasRemoved').textContent = metrics.schemaRemoved;
		
		document.getElementById('sg-graphsExported').textContent = metrics.graphExported;
		document.getElementById('sg-graphsImported').textContent = metrics.graphImported;
		document.getElementById('sg-configsExported').textContent = metrics.configExported;
		document.getElementById('sg-configsImported').textContent = metrics.configImported;
		
		document.getElementById('sg-totalInteractions').textContent = metrics.interactions;
		document.getElementById('sg-layoutsApplied').textContent = metrics.layoutApplied;
		document.getElementById('sg-errorCount').textContent = metrics.errors;
	}

	formatDuration(ms) {
		const seconds = Math.floor(ms / 1000);
		const minutes = Math.floor(seconds / 60);
		const hours = Math.floor(minutes / 60);
		
		if (hours > 0) {
			return `${hours}h ${minutes % 60}m ${seconds % 60}s`;
		} else if (minutes > 0) {
			return `${minutes}m ${seconds % 60}s`;
		} else {
			return `${seconds}s`;
		}
	}

	setupVoiceCommands() {
		this.eventBus.on('voice:result', (data) => {
			const transcript = data.transcript.toLowerCase().trim();
			console.log('Voice command received:', transcript);
			
			if (transcript.includes('create') || transcript.includes('add')) {
				if (transcript.includes('string')) {
					this.executeVoiceCommand('create', 'Native.String');
				} else if (transcript.includes('integer') || transcript.includes('number')) {
					this.executeVoiceCommand('create', 'Native.Integer');
				} else if (transcript.includes('boolean')) {
					this.executeVoiceCommand('create', 'Native.Boolean');
				} else if (transcript.includes('float')) {
					this.executeVoiceCommand('create', 'Native.Float');
				} else if (transcript.includes('list')) {
					this.executeVoiceCommand('create', 'Native.List');
				} else if (transcript.includes('dict') || transcript.includes('dictionary')) {
					this.executeVoiceCommand('create', 'Native.Dict');
				} else if (transcript.includes('node')) {
					this.showContextMenu(null, 0, 0, { clientX: this.canvas.width / 2, clientY: this.canvas.height / 2 });
				}
			}
			else if (transcript.includes('delete') || transcript.includes('remove')) {
				if (this.selectedNode) {
					this.executeVoiceCommand('delete');
				} else {
					this.showError('No node selected');
				}
			}
			else if (transcript.includes('export')) {
				if (transcript.includes('config')) {
					this.executeVoiceCommand('export-config');
				} else {
					this.executeVoiceCommand('export-graph');
				}
			}
			else if (transcript.includes('import')) {
				if (transcript.includes('config')) {
					this.executeVoiceCommand('import-config');
				} else {
					this.executeVoiceCommand('import-graph');
				}
			}
			else if (transcript.includes('center') || transcript.includes('focus')) {
				this.executeVoiceCommand('center-view');
			}
			else if (transcript.includes('zoom')) {
				if (transcript.includes('in')) {
					this.executeVoiceCommand('zoom-in');
				} else if (transcript.includes('out')) {
					this.executeVoiceCommand('zoom-out');
				} else if (transcript.includes('reset')) {
					this.executeVoiceCommand('reset-zoom');
				}
			}
			else if (transcript.includes('layout')) {
				if (transcript.includes('hierarchical') || transcript.includes('hierarchy')) {
					if (transcript.includes('horizontal')) {
						this.executeVoiceCommand('layout', 'hierarchical-horizontal');
					} else {
						this.executeVoiceCommand('layout', 'hierarchical-vertical');
					}
				} else if (transcript.includes('force')) {
					this.executeVoiceCommand('layout', 'force-directed');
				} else if (transcript.includes('grid')) {
					this.executeVoiceCommand('layout', 'grid');
				} else if (transcript.includes('circular') || transcript.includes('circle')) {
					this.executeVoiceCommand('layout', 'circular');
				}
			}
			else if (transcript.includes('theme') || transcript.includes('color')) {
				this.executeVoiceCommand('cycle-theme');
			}
			else if (transcript.includes('help') || transcript.includes('commands')) {
				this.showVoiceHelp();
			}
			else if (transcript.includes('layout')) {
				if (transcript.includes('hierarchical') || transcript.includes('hierarchy')) {
					if (transcript.includes('horizontal')) {
						this.executeVoiceCommand('layout', 'hierarchical-horizontal');
					} else {
						this.executeVoiceCommand('layout', 'hierarchical-vertical');
					}
				} else if (transcript.includes('force')) {
					this.executeVoiceCommand('layout', 'force-directed');
				} else if (transcript.includes('grid')) {
					this.executeVoiceCommand('layout', 'grid');
				} else if (transcript.includes('circular') || transcript.includes('circle')) {
					this.executeVoiceCommand('layout', 'circular');
				}
			}
			else {
				this.showError('Unknown voice command: ' + transcript);
			}
		});
	}

	executeVoiceCommand(command, param = null) {
		console.log('Executing voice command:', command, param);
		
		switch (command) {
			case 'create':
				if (param && this.graph.nodeTypes[param]) {
					const node = this.graph.createNode(param);
					const centerX = (-this.camera.x + this.canvas.width / 2) / this.camera.scale;
					const centerY = (-this.camera.y + this.canvas.height / 2) / this.camera.scale;
					node.pos = [centerX - 90, centerY - 40];
					this.draw();
					this.eventBus.emit('ui:update', { id: 'status', content: 'Created ' + param + ' node' });
				}
				break;
				
			case 'delete':
				if (this.selectedNode) {
					const nodeName = this.selectedNode.title;
					this.removeNode(this.selectedNode);
					this.eventBus.emit('ui:update', { id: 'status', content: 'Deleted ' + nodeName });
				}
				break;
				
			case 'export-graph':
				this.exportGraph();
				break;
				
			case 'export-config':
				this.exportConfig();
				break;
				
			case 'import-graph':
				document.getElementById('sg-importFile').click();
				break;
				
			case 'import-config':
				document.getElementById('sg-importConfigFile').click();
				break;
				
			case 'center-view':
				this.centerView();
				this.eventBus.emit('ui:update', { id: 'status', content: 'Centered view' });
				break;
				
			case 'zoom-in':
				const beforeIn = this.screenToWorld(this.canvas.width / 2, this.canvas.height / 2);
				this.camera.scale *= 1.2;
				this.camera.scale = Math.min(5, this.camera.scale);
				const afterIn = this.screenToWorld(this.canvas.width / 2, this.canvas.height / 2);
				this.camera.x += (afterIn[0] - beforeIn[0]) * this.camera.scale;
				this.camera.y += (afterIn[1] - beforeIn[1]) * this.camera.scale;
				this.eventBus.emit('ui:update', { id: 'zoomLevel', content: Math.round(this.camera.scale * 100) + '%' });
				this.draw();
				break;
				
			case 'zoom-out':
				const beforeOut = this.screenToWorld(this.canvas.width / 2, this.canvas.height / 2);
				this.camera.scale *= 0.8;
				this.camera.scale = Math.max(0.1, this.camera.scale);
				const afterOut = this.screenToWorld(this.canvas.width / 2, this.canvas.height / 2);
				this.camera.x += (afterOut[0] - beforeOut[0]) * this.camera.scale;
				this.camera.y += (afterOut[1] - beforeOut[1]) * this.camera.scale;
				this.eventBus.emit('ui:update', { id: 'zoomLevel', content: Math.round(this.camera.scale * 100) + '%' });
				this.draw();
				break;
				
			case 'reset-zoom':
				this.resetZoom();
				this.eventBus.emit('ui:update', { id: 'status', content: 'Reset zoom to 100%' });
				break;
				
			case 'layout':
				if (param) {
					this.applyLayout(param);
					this.eventBus.emit('ui:update', { id: 'status', content: 'Applied ' + param + ' layout' });
				}
				break;
				
			case 'cycle-theme':
				this.cycleTheme();
				this.eventBus.emit('ui:update', { id: 'status', content: 'Changed theme' });
				break;
				
			default:
				console.warn('Unknown command:', command);
		}
	}

	showVoiceHelp() {
		const helpMessage = `Voice Commands:
	- "Create [string/integer/boolean/float/list/dict]" - Create native node
	- "Delete" - Delete selected node
	- "Export [graph/config]" - Export graph or config
	- "Center" or "Focus" - Center view
	- "Zoom [in/out/reset]" - Control zoom
	- "Layout [hierarchical/grid/circular/force]" - Apply layout
	- "Theme" - Change theme
	- "Help" - Show this message`;
		
		this.ui.dialogs.showMessage(helpMessage, '🎤 Voice Commands');
	}

	loadTheme() {
		const saved = localStorage.getItem('schemagraph-theme') || 'dark';
		this.currentThemeIndex = this.themes.indexOf(saved);
		if (this.currentThemeIndex === -1) this.currentThemeIndex = 0;
		this.applyTheme(this.themes[this.currentThemeIndex]);
	}

	applyTheme(theme) {
		if (theme === 'dark') {
			document.documentElement.removeAttribute('data-theme');
		} else {
			document.documentElement.setAttribute('data-theme', theme);
		}
	}

	cycleTheme() {
		this.currentThemeIndex = (this.currentThemeIndex + 1) % this.themes.length;
		const newTheme = this.themes[this.currentThemeIndex];
		this.applyTheme(newTheme);
		localStorage.setItem('schemagraph-theme', newTheme);
		this.draw();
	}

	registerNativeNodes() {
		const nativeNodes = [
			{ name: 'String', type: 'str', defaultValue: '', parser: (v) => v },
			{ name: 'Integer', type: 'int', defaultValue: 0, parser: (v) => parseInt(v) || 0 },
			{ name: 'Boolean', type: 'bool', defaultValue: false, parser: (v) => v === true || v === 'true' },
			{ name: 'Float', type: 'float', defaultValue: 0.0, parser: (v) => parseFloat(v) || 0.0 },
			{ name: 'List', type: 'List[Any]', defaultValue: '[]', parser: (v) => {
				try { return JSON.parse(v); } catch (e) { return []; }
			}},
			{ name: 'Dict', type: 'Dict[str,Any]', defaultValue: '{}', parser: (v) => {
				try { return JSON.parse(v); } catch (e) { return {}; }
			}},
		];

		for (const nodeSpec of nativeNodes) {
			class NativeNode extends Node {
				constructor() {
					super(nodeSpec.name);
					this.addOutput('value', nodeSpec.type);
					this.properties.value = nodeSpec.defaultValue;
					this.size = [180, 80];
					this.isNative = true;
				}

				onExecute() {
					this.setOutputData(0, nodeSpec.parser(this.properties.value));
				}
			}

			this.graph.nodeTypes['Native.' + nodeSpec.name] = NativeNode;
		}
	}

	selectNode(node, addToSelection = false) {
		if (!addToSelection) {
			this.selectedNodes.clear();
		}
		
		if (node) {
			this.selectedNodes.add(node);
			this.selectedNode = node;
		}
		
		this.draw();
	}

	deselectNode(node) {
		this.selectedNodes.delete(node);
		if (this.selectedNode === node) {
			this.selectedNode = this.selectedNodes.size > 0 ? 
				Array.from(this.selectedNodes)[this.selectedNodes.size - 1] : null;
		}
		this.draw();
	}

	toggleNodeSelection(node) {
		if (this.selectedNodes.has(node)) {
			this.deselectNode(node);
		} else {
			this.selectNode(node, true);
		}
	}

	clearSelection() {
		this.selectedNodes.clear();
		this.selectedNode = null;
		this.draw();
	}

	isNodeSelected(node) {
		return this.selectedNodes.has(node);
	}

	deleteSelectedNodes() {
		const nodesToDelete = Array.from(this.selectedNodes);
		for (const node of nodesToDelete) {
			this.removeNode(node);
		}
		this.clearSelection();
	}

	handleMouseDown(data) {
		this.isMouseDown = true;
		document.getElementById('sg-contextMenu').classList.remove('show');
		
		const [wx, wy] = this.screenToWorld(data.coords.screenX, data.coords.screenY);
		
		// Allow panning even when locked
		if (data.button === 1 || (data.button === 0 && this.spacePressed)) {
			data.event.preventDefault();
			this.isPanning = true;
			this.panStart = [data.coords.screenX - this.camera.x, data.coords.screenY - this.camera.y];
			this.canvas.style.cursor = 'grabbing';
			return;
		}
		
		if (data.button !== 0 || this.spacePressed) return;
		
		// LOCK CHECK: Block connection creation when locked
		if (this.isLocked) {
			// Skip slot detection for connection creation
			// Fall through to node selection/dragging only
		} else {
			// Output slot detection (connection start)
			for (const node of this.graph.nodes) {
				for (let j = 0; j < node.outputs.length; j++) {
					const slotY = node.pos[1] + 30 + j * 25;
					const dist = Math.sqrt(Math.pow(wx - (node.pos[0] + node.size[0]), 2) + Math.pow(wy - slotY, 2));
					if (dist < 10) {
						this.connecting = { node, slot: j, isOutput: true };
						this.canvas.classList.add('connecting');
						return;
					}
				}
			}
			
			// Input slot detection (connection start / disconnect)
			for (const node of this.graph.nodes) {
				for (let j = 0; j < node.inputs.length; j++) {
					const slotY = node.pos[1] + 30 + j * 25;
					const dist = Math.sqrt(Math.pow(wx - node.pos[0], 2) + Math.pow(wy - slotY, 2));
					if (dist < 10) {
						if (!node.multiInputs || !node.multiInputs[j]) {
							if (node.inputs[j].link) {
								this.removeLink(node.inputs[j].link, node, j);
							}
						}
						this.connecting = { node, slot: j, isOutput: false };
						this.canvas.classList.add('connecting');
						return;
					}
				}
			}
		}
		
		// Node selection and dragging (ALLOWED when locked)
		let clickedNode = null;
		for (let i = this.graph.nodes.length - 1; i >= 0; i--) {
			const node = this.graph.nodes[i];
			if (wx >= node.pos[0] && wx <= node.pos[0] + node.size[0] &&
					wy >= node.pos[1] && wy <= node.pos[1] + node.size[1]) {
				clickedNode = node;
				break;
			}
		}
		
		if (clickedNode) {
			if (data.event.ctrlKey || data.event.metaKey) {
				this.toggleNodeSelection(clickedNode);
			} else {
				if (!this.selectedNodes.has(clickedNode)) {
					this.selectNode(clickedNode, false);
				}
				this.dragNode = clickedNode;
				this.dragOffset = [wx - clickedNode.pos[0], wy - clickedNode.pos[1]];
				this.canvas.classList.add('dragging');
			}
			return;
		}
		
		// Box selection (ALLOWED when locked - just for viewing)
		if (!data.event.ctrlKey && !data.event.metaKey) {
			this.clearSelection();
		}
		this.selectionStart = [wx, wy];
	}

	handleMouseMove(data) {
		this.mousePos = [data.coords.screenX, data.coords.screenY];
		
		if (this.isPanning) {
			this.camera.x = data.coords.screenX - this.panStart[0];
			this.camera.y = data.coords.screenY - this.panStart[1];
			this.draw();
		} else if (this.dragNode && !this.connecting) {
			const [wx, wy] = this.screenToWorld(data.coords.screenX, data.coords.screenY);
			const dx = wx - this.dragOffset[0] - this.dragNode.pos[0];
			const dy = wy - this.dragOffset[1] - this.dragNode.pos[1];
			
			for (const node of this.selectedNodes) {
				node.pos[0] += dx;
				node.pos[1] += dy;
			}
			
			this.draw();
		} else if (this.connecting) {
			this.draw();
		} else if (this.selectionStart && this.isMouseDown) {
			const [wx, wy] = this.screenToWorld(data.coords.screenX, data.coords.screenY);
			const dx = Math.abs(wx - this.selectionStart[0]);
			const dy = Math.abs(wy - this.selectionStart[1]);
			
			if (dx > 5 || dy > 5) {
				this.selectionRect = {
					x: Math.min(this.selectionStart[0], wx),
					y: Math.min(this.selectionStart[1], wy),
					w: dx,
					h: dy
				};
				
				this.previewSelection.clear();
				for (const node of this.graph.nodes) {
					const nodeRect = {
						x: node.pos[0],
						y: node.pos[1],
						w: node.size[0],
						h: node.size[1]
					};
					
					if (!(nodeRect.x > this.selectionRect.x + this.selectionRect.w ||
								nodeRect.x + nodeRect.w < this.selectionRect.x ||
								nodeRect.y > this.selectionRect.y + this.selectionRect.h ||
								nodeRect.y + nodeRect.h < this.selectionRect.y)) {
						this.previewSelection.add(node);
					}
				}
			}
			this.draw();
		} else {
			this.draw();
		}
	}

	handleMouseUp(data) {
		this.isMouseDown = false;
		const [wx, wy] = this.screenToWorld(data.coords.screenX, data.coords.screenY);
		
		if (this.isPanning) {
			this.isPanning = false;
			this.canvas.style.cursor = this.spacePressed ? 'grab' : 'default';
			return;
		}
		
		if (this.connecting) {
			for (const node of this.graph.nodes) {
				if (this.connecting.isOutput) {
					for (let j = 0; j < node.inputs.length; j++) {
						const slotY = node.pos[1] + 30 + j * 25;
						const dist = Math.sqrt(Math.pow(wx - node.pos[0], 2) + Math.pow(wy - slotY, 2));
						if (dist < 15 && node !== this.connecting.node) {
							if (!this.isSlotCompatible(node, j, false)) {
								this.showError('Type mismatch');
								break;
							}
							
							if (node.multiInputs && node.multiInputs[j]) {
								const linkId = ++this.graph.last_link_id;
								const link = new Link(
									linkId,
									this.connecting.node.id,
									this.connecting.slot,
									node.id,
									j,
									this.connecting.node.outputs[this.connecting.slot].type
								);
								this.graph.links[linkId] = link;
								this.connecting.node.outputs[this.connecting.slot].links.push(linkId);
								node.multiInputs[j].links.push(linkId);
								this.eventBus.emit('link:created', { linkId });
							} else {
								if (node.inputs[j].link) {
									this.removeLink(node.inputs[j].link, node, j);
								}
								const link = this.graph.connect(this.connecting.node, this.connecting.slot, node, j);
								if (link) this.eventBus.emit('link:created', { linkId: link.id });
							}
							break;
						}
					}
				} else {
					for (let j = 0; j < node.outputs.length; j++) {
						const slotY = node.pos[1] + 30 + j * 25;
						const dist = Math.sqrt(Math.pow(wx - (node.pos[0] + node.size[0]), 2) + Math.pow(wy - slotY, 2));
						if (dist < 15 && node !== this.connecting.node) {
							if (!this.isSlotCompatible(node, j, true)) {
								this.showError('Type mismatch');
								break;
							}
							
							if (this.connecting.node.multiInputs && this.connecting.node.multiInputs[this.connecting.slot]) {
								const linkId = ++this.graph.last_link_id;
								const link = new Link(
									linkId,
									node.id,
									j,
									this.connecting.node.id,
									this.connecting.slot,
									node.outputs[j].type
								);
								this.graph.links[linkId] = link;
								node.outputs[j].links.push(linkId);
								this.connecting.node.multiInputs[this.connecting.slot].links.push(linkId);
								this.eventBus.emit('link:created', { linkId });
							} else {
								if (this.connecting.node.inputs[this.connecting.slot].link) {
									this.removeLink(this.connecting.node.inputs[this.connecting.slot].link, 
																	this.connecting.node, this.connecting.slot);
								}
								const link = this.graph.connect(node, j, this.connecting.node, this.connecting.slot);
								if (link) this.eventBus.emit('link:created', { linkId: link.id });
							}
							break;
						}
					}
				}
			}
			
			this.connecting = null;
			this.canvas.classList.remove('connecting');
			this.draw();
			return;
		}
		
		if (this.selectionStart && this.selectionRect) {
			const rect = this.selectionRect;
			
			if (!data.event.ctrlKey && !data.event.metaKey) {
				this.clearSelection();
			}
			
			for (const node of this.graph.nodes) {
				const nodeRect = {
					x: node.pos[0],
					y: node.pos[1],
					w: node.size[0],
					h: node.size[1]
				};
				
				if (!(nodeRect.x > rect.x + rect.w ||
							nodeRect.x + nodeRect.w < rect.x ||
							nodeRect.y > rect.y + rect.h ||
							nodeRect.y + nodeRect.h < rect.y)) {
					this.selectNode(node, true);
				}
			}
		}
		
		this.selectionStart = null;
		this.selectionRect = null;
		this.previewSelection.clear();
		
		this.dragNode = null;
		this.canvas.classList.remove('dragging');
		
		this.draw();
	}

	handleDoubleClick(data) {
		if (this.isLocked) {
			return;
		}
	
		const [wx, wy] = this.screenToWorld(data.coords.screenX, data.coords.screenY);
		
		for (const node of this.graph.nodes) {
			if (node.nativeInputs) {
				for (let j = 0; j < node.inputs.length; j++) {
					if (!node.inputs[j].link && node.nativeInputs[j] !== undefined) {
						const slotY = node.pos[1] + 30 + j * 25;
						
						// Edit box on type label row
						const boxX = node.pos[0] + 10;
						const boxY = slotY + 6;
						const boxW = 70;
						const boxH = 12;
						
						if (wx >= boxX && wx <= boxX + boxW && wy >= boxY && wy <= boxY + boxH) {
							if (node.nativeInputs[j].type === 'bool') {
								node.nativeInputs[j].value = !node.nativeInputs[j].value;
								document.getElementById('sg-nodeInput')?.dispatchEvent(new Event('change'));
								this.draw();
								return;
							}
							
							this.showInputOverlay(node, j, boxX, boxY, data.coords.rect);
							return;
						}
					}
				}
			}
		}
		
		// Native node value editing (unchanged)
		for (const node of this.graph.nodes) {
			if (!node.isNative) continue;
			const valueY = node.pos[1] + node.size[1] - 18;
			const valueHeight = 20;
			
			if (wx >= node.pos[0] + 8 && wx <= node.pos[0] + node.size[0] - 8 &&
					wy >= valueY && wy <= valueY + valueHeight) {
				if (node.title === 'Boolean') {
					node.properties.value = !node.properties.value;
					document.getElementById('sg-nodeInput')?.dispatchEvent(new Event('change'));
					this.draw();
				} else {
					this.showInputOverlay(node, null, node.pos[0] + 8, valueY, data.coords.rect);
				}
				return;
			}
		}
	}

	showInputOverlay(node, slot, x, y, rect) {
		const valueScreen = this.worldToScreen(x, y);
		this.editingNode = node;
		this.editingNode.editingSlot = slot;
		
		const nodeInput = document.getElementById('sg-nodeInput');
		if (slot !== null) {
			nodeInput.value = String(node.nativeInputs[slot].value);
		} else {
			nodeInput.value = String(node.properties.value);
		}
		
		nodeInput.style.left = (valueScreen[0] * rect.width / this.canvas.width + rect.left) + 'px';
		nodeInput.style.top = (valueScreen[1] * rect.height / this.canvas.height + rect.top) + 'px';
		nodeInput.style.width = (slot !== null ? '75px' : '160px');
		nodeInput.classList.add('show');
		nodeInput.focus();
		nodeInput.select();
	}

	handleWheel(data) {
		const before = this.screenToWorld(data.coords.screenX, data.coords.screenY);
		this.camera.scale *= data.delta > 0 ? 0.9 : 1.1;
		this.camera.scale = Math.max(0.1, Math.min(5, this.camera.scale));
		const after = this.screenToWorld(data.coords.screenX, data.coords.screenY);
		this.camera.x += (after[0] - before[0]) * this.camera.scale;
		this.camera.y += (after[1] - before[1]) * this.camera.scale;
		
		this.eventBus.emit('ui:update', { 
			id: 'zoomLevel', 
			content: Math.round(this.camera.scale * 100) + '%' 
		});
		this.draw();
	}

	handleContextMenu(data) {
		if (this.isLocked) {
			data.event.preventDefault();
			return;
		}
	
		const [wx, wy] = this.screenToWorld(data.coords.screenX, data.coords.screenY);
		
		let clickedNode = null;
		for (let i = this.graph.nodes.length - 1; i >= 0; i--) {
			const node = this.graph.nodes[i];
			if (wx >= node.pos[0] && wx <= node.pos[0] + node.size[0] &&
					wy >= node.pos[1] && wy <= node.pos[1] + node.size[1]) {
				clickedNode = node;
				break;
			}
		}
		
		if (this.customContextMenuHandler) {
			const handled = this.customContextMenuHandler(clickedNode, wx, wy, data.coords);
			if (handled) return;
		}
		
		this.showContextMenu(clickedNode, wx, wy, data.coords);
	}

	showContextMenu(node, wx, wy, coords) {
		const contextMenu = document.getElementById('sg-contextMenu');
		let html = '';
		
		if (node) {
			console.log('📋 Opening context menu for node:', node.title);
			const selectionCount = this.selectedNodes.size;
			
			html += '<div class="sg-context-menu-category">Node Actions</div>';
			
			if (selectionCount > 1) {
				html += '<div class="sg-context-menu-item sg-context-menu-delete" data-action="delete-all">❌ Delete ' + selectionCount + ' Nodes</div>';
			} else {
				html += '<div class="sg-context-menu-item sg-context-menu-delete" data-action="delete">❌ Delete Node</div>';
			}
			
			let hasMultiInputs = false;
			let multiInputCount = 0;
			if (node.multiInputs) {
				console.log('	 Checking multiInputs:', Object.keys(node.multiInputs));
				for (const slotIdx in node.multiInputs) {
					if (node.multiInputs.hasOwnProperty(slotIdx)) {
						const links = node.multiInputs[slotIdx].links;
						console.log(`	 Slot ${slotIdx} (${node.inputs[slotIdx]?.name}):`, links ? links.length : 0, 'links');
						if (links && links.length > 0) {
							hasMultiInputs = true;
							multiInputCount += links.length;
						}
					}
				}
			} else {
				console.log('	 No multiInputs property on this node');
			}
			
			console.log('	 hasMultiInputs:', hasMultiInputs, 'total count:', multiInputCount);
			
			if (hasMultiInputs) {
				html += '<div class="sg-context-menu-item" data-action="clear-multi-inputs">🗑️ Clear ' + multiInputCount + ' Multi-Input Link(s)</div>';
			}
			
			contextMenu.innerHTML = html;
			contextMenu.style.left = coords.clientX + 'px';
			contextMenu.style.top = coords.clientY + 'px';
			contextMenu.classList.add('show');
			
			const deleteBtn = contextMenu.querySelector('.sg-context-menu-delete');
			if (deleteBtn) {
				deleteBtn.addEventListener('click', () => {
					if (this.selectedNodes.size > 1) {
						this.deleteSelectedNodes();
					} else {
						this.removeNode(node);
					}
					contextMenu.classList.remove('show');
				});
			}
			
			if (hasMultiInputs) {
				const clearBtn = contextMenu.querySelector('[data-action="clear-multi-inputs"]');
				if (clearBtn) {
					clearBtn.addEventListener('click', () => {
						console.log('🗑️ Clear multi-inputs clicked');
						this.clearAllMultiInputLinks(node);
						contextMenu.classList.remove('show');
					});
				}
			}
		} else {
			html += '<div class="sg-context-menu-category">Native Types</div>';
			const natives = ['Native.String', 'Native.Integer', 'Native.Boolean', 'Native.Float', 'Native.List', 'Native.Dict'];
			for (const nativeType of natives) {
				const name = nativeType.split('.')[1];
				html += '<div class="sg-context-menu-item" data-type="' + nativeType + '">' + name + '</div>';
			}
			
			const registeredSchemas = Object.keys(this.graph.schemas);
			for (const schemaName of registeredSchemas) {
				if (!this.graph.isSchemaEnabled(schemaName)) {
					console.log('Skipping disabled schema in context menu:', schemaName);
					continue;
				}
				
				const schemaTypes = [];
				const schemaInfo = this.graph.schemas[schemaName];
				let rootNodeType = null;
				
				for (const type in this.graph.nodeTypes) {
					if (type.indexOf(schemaName + '.') === 0) {
						schemaTypes.push(type);
						if (schemaInfo.rootType && type === schemaName + '.' + schemaInfo.rootType) {
							rootNodeType = type;
						}
					}
				}
				
				if (schemaTypes.length > 0) {
					html += '<div class="sg-context-menu-category">' + schemaName + ' Schema</div>';
					
					if (rootNodeType) {
						const name = rootNodeType.split('.')[1];
						html += '<div class="sg-context-menu-item" data-type="' + rootNodeType + '" style="font-weight: bold; color: var(--sg-accent-orange);">★ ' + name + ' (Root)</div>';
					}
					
					for (const schemaType of schemaTypes) {
						if (schemaType !== rootNodeType) {
							const name = schemaType.split('.')[1];
							html += '<div class="sg-context-menu-item" data-type="' + schemaType + '">' + name + '</div>';
						}
					}
				}
			}
			
			contextMenu.innerHTML = html;
			contextMenu.style.left = coords.clientX + 'px';
			contextMenu.style.top = coords.clientY + 'px';
			contextMenu.classList.add('show');
			contextMenu.dataset.worldX = wx;
			contextMenu.dataset.worldY = wy;
			
			const items = contextMenu.querySelectorAll('.sg-context-menu-item');
			for (const item of items) {
				item.addEventListener('click', () => {
					const type = item.getAttribute('data-type');
					const wx = parseFloat(contextMenu.dataset.worldX);
					const wy = parseFloat(contextMenu.dataset.worldY);
					const node = this.graph.createNode(type);
					node.pos = [wx - 90, wy - 40];
					contextMenu.classList.remove('show');
					this.draw();
				});
			}
		}
	}

	handleKeyDown(data) {
		const isTyping = data.event.target.tagName === 'INPUT' || 
										data.event.target.tagName === 'TEXTAREA' ||
										data.event.target.isContentEditable;
		
		if (data.code === 'Space' && !this.spacePressed && !this.editingNode && !isTyping) {
			data.event.preventDefault();
			this.spacePressed = true;
			this.canvas.style.cursor = 'grab';
		}
		
		// LOCK CHECK: Block delete when locked
		if ((data.key === 'Delete' || data.key === 'Backspace') && 
				this.selectedNodes.size > 0 && !this.editingNode && !isTyping) {
			if (this.isLocked) {
				return; // Block deletion
			}
			data.event.preventDefault();
			this.deleteSelectedNodes();
		}
		
		// Ctrl+A select all - still allowed when locked (for viewing)
		if ((data.event.ctrlKey || data.event.metaKey) && data.key === 'a' && !this.editingNode && !isTyping) {
			data.event.preventDefault();
			this.clearSelection();
			for (const node of this.graph.nodes) {
				this.selectNode(node, true);
			}
		}
		
		if (data.key === 'Escape' && !this.editingNode) {
			this.clearSelection();
		}
		
		// LOCK CHECK: Block save/export shortcuts when locked (optional)
		if ((data.event.ctrlKey || data.event.metaKey) && data.key === 's' && !isTyping) {
			data.event.preventDefault();
			this.eventBus.emit('ui:export-graph', {});
		}
		
		if ((data.event.ctrlKey || data.event.metaKey) && data.key === 'o' && !isTyping) {
			if (this.isLocked) return; // Block import when locked
			data.event.preventDefault();
			this.eventBus.emit('ui:import-graph', {});
		}
	}

	handleKeyUp(data) {
		if (data.code === 'Space') {
			this.spacePressed = false;
			this.canvas.style.cursor = this.isPanning ? 'grabbing' : 'default';
		}
	}

	handleInputBlur() {
		if (this.editingNode) {
			const nodeInput = document.getElementById('sg-nodeInput');
			const val = nodeInput.value;
			
			if (this.editingNode.editingSlot !== null && this.editingNode.editingSlot !== undefined) {
				const slot = this.editingNode.editingSlot;
				const inputType = this.editingNode.nativeInputs[slot].type;
				
				if (inputType === 'int') {
					this.editingNode.nativeInputs[slot].value = parseInt(val) || 0;
				} else if (inputType === 'float') {
					this.editingNode.nativeInputs[slot].value = parseFloat(val) || 0.0;
				} else if (inputType === 'bool') {
					this.editingNode.nativeInputs[slot].value = val === 'true' || val === true;
				} else {
					this.editingNode.nativeInputs[slot].value = val;
				}
				
				this.editingNode.editingSlot = null;
			} else {
				if (this.editingNode.title === 'Integer') {
					this.editingNode.properties.value = parseInt(val) || 0;
				} else if (this.editingNode.title === 'Float') {
					this.editingNode.properties.value = parseFloat(val) || 0.0;
				} else if (this.editingNode.title === 'Boolean') {
					this.editingNode.properties.value = val === 'true' || val === true;
				} else {
					this.editingNode.properties.value = val;
				}
			}
			
			this.draw();
		}
		document.getElementById('sg-nodeInput').classList.remove('show');
		this.editingNode = null;
	}

	handleInputKeyDown(e) {
		if (e.key === 'Enter') {
			document.getElementById('sg-nodeInput').blur();
		} else if (e.key === 'Escape') {
			document.getElementById('sg-nodeInput').classList.remove('show');
			this.editingNode = null;
		}
	}

	handleSchemaFileUpload(data) {
		const reader = new FileReader();
		reader.onload = (event) => {
			this.pendingSchemaCode = event.target.result;

			const fileName = data.file.name.replace(/\.py$/, '');
			const suggestedName = fileName.charAt(0).toUpperCase() + fileName.slice(1);

			const rootTypeRegex = /class\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(/g;
			let reMatch = null;
			let rootTypeMatch = null;
			while ((reMatch = rootTypeRegex.exec(this.pendingSchemaCode)) !== null) {
				rootTypeMatch = reMatch;
			}

			const suggestedRootType = rootTypeMatch ? rootTypeMatch[1] : '';

			document.getElementById('sg-schemaNameInput').value = suggestedName;
			document.getElementById('sg-schemaIndexTypeInput').value = 'Index';
			document.getElementById('sg-schemaRootTypeInput').value = suggestedRootType;

			this.eventBus.emit('ui:show', { id: 'schemaDialog' });
			document.getElementById('sg-schemaNameInput').focus();
			document.getElementById('sg-schemaNameInput').select();
		};
		reader.readAsText(data.file);
		data.element.value = '';
	}

	handleImportGraph(data) {
		const reader = new FileReader();
		reader.onload = (event) => {
			try {
				const jsonData = JSON.parse(event.target.result);
				this.graph.deserialize(jsonData, true, this.camera);
				this.updateSchemaList();
				this.updateNodeTypesList();
				this.eventBus.emit('ui:update', { 
					id: 'zoomLevel', 
					content: Math.round(this.camera.scale * 100) + '%' 
				});
				this.draw();
				this.eventBus.emit('graph:imported', {});
				this.eventBus.emit('ui:update', { id: 'status', content: 'Graph imported successfully!' });
				setTimeout(() => {
					this.eventBus.emit('ui:update', { id: 'status', content: 'Right-click to add nodes.' });
				}, 2000);
			} catch (e) {
				this.showError('Import failed: ' + e.message);
			}
		};
		reader.readAsText(data.file);
		data.element.value = '';
	}

	handleImportConfig(data) {
		const reader = new FileReader();
		reader.onload = (event) => {
			try {
				const configData = JSON.parse(event.target.result);
				this.importConfigData(configData);
				this.eventBus.emit('config:imported', {});
			} catch (e) {
				this.showError('Import config failed: ' + e.message);
			}
		};
		reader.readAsText(data.file);
		data.element.value = '';
	}

	confirmSchemaRegistration() {
		if (!this.pendingSchemaCode) return;
		
		const schemaName = document.getElementById('sg-schemaNameInput').value.trim();
		const indexType = document.getElementById('sg-schemaIndexTypeInput').value.trim() || 'int';
		const rootType = document.getElementById('sg-schemaRootTypeInput').value.trim() || null;
		
		if (!schemaName) {
			this.showError('Schema name is required');
			return;
		}
		
		if (this.graph.schemas[schemaName]) {
			this.ui.dialogs.showConfirm(
				`Schema "${schemaName}" already exists. Replace it?`,
				'⚠️ Replace Schema'
			).then(confirmed => {
				if (!confirmed) return;
				
				this.graph.removeSchema(schemaName);
				this._completeSchemaRegistration(schemaName, indexType, rootType);
			});
			return;
		}
		
		this._completeSchemaRegistration(schemaName, indexType, rootType);
	}

	_completeSchemaRegistration(schemaName, indexType, rootType) {
		if (this.graph.registerSchema(schemaName, this.pendingSchemaCode, indexType, rootType)) {
			this.eventBus.emit('ui:hide', { id: 'schemaDialog' });
			this.pendingSchemaCode = null;
			
			this.eventBus.emit('ui:update', { 
				id: 'status', 
				content: `Schema "${schemaName}" registered successfully!` 
			});
			setTimeout(() => {
				this.eventBus.emit('ui:update', { id: 'status', content: 'Right-click to add nodes.' });
			}, 3000);
		} else {
			this.showError('Failed to register schema. Check console.');
		}
	}

	cancelSchemaRegistration() {
		this.eventBus.emit('ui:hide', { id: 'schemaDialog' });
		this.pendingSchemaCode = null;
	}

	confirmSchemaRemoval() {
		const schemaName = document.getElementById('sg-schemaRemovalNameInput').value;
		if (!schemaName) {
			this.showError('Please select a schema');
			return;
		}
		
		if (this.graph.removeSchema(schemaName)) {
			this.eventBus.emit('ui:hide', { id: 'schemaRemovalDialog' });
			this.eventBus.emit('ui:update', { 
				id: 'status', 
				content: `Schema "${schemaName}" removed successfully` 
			});
			setTimeout(() => {
				this.eventBus.emit('ui:update', { id: 'status', content: 'Right-click to add nodes.' });
			}, 2000);
		} else {
			this.showError('Failed to remove schema: ' + schemaName);
		}
	}

	cancelSchemaRemoval() {
		this.eventBus.emit('ui:hide', { id: 'schemaRemovalDialog' });
	}

	exportGraph() {
		try {
			const data = this.graph.serialize(true, this.camera);
			const jsonString = JSON.stringify(data, null, 2);
			
			const blob = new Blob([jsonString], { type: 'application/json' });
			const url = URL.createObjectURL(blob);
			const a = document.createElement('a');
			a.href = url;
			a.download = 'schemagraph-' + new Date().toISOString().slice(0, 10) + '.json';
			document.body.appendChild(a);
			a.click();
			document.body.removeChild(a);
			URL.revokeObjectURL(url);
			
			this.eventBus.emit('graph:exported', {});
			this.eventBus.emit('ui:update', { id: 'status', content: 'Graph exported successfully!' });
			setTimeout(() => {
				this.eventBus.emit('ui:update', { id: 'status', content: 'Right-click to add nodes.' });
			}, 2000);
		} catch (e) {
			this.showError('Export failed: ' + e.message);
		}
	}

	exportConfig() {
		try {
			const schemas = Object.keys(this.graph.schemas);
			if (schemas.length === 0) {
				this.showError('No schemas registered');
				return;
			}

			let targetSchema = null;
			for (const schemaName of schemas) {
				const info = this.graph.schemas[schemaName];
				if (info && info.rootType) {
					targetSchema = schemaName;
					break;
				}
			}

			if (!targetSchema) targetSchema = schemas[0];

			const config = this.buildConfig(targetSchema);
			const jsonString = JSON.stringify(config, null, 2);

			const blob = new Blob([jsonString], { type: 'application/json' });
			const url = URL.createObjectURL(blob);
			const a = document.createElement('a');
			a.href = url;
			a.download = 'config-' + new Date().toISOString().slice(0, 10) + '.json';
			document.body.appendChild(a);
			a.click();
			document.body.removeChild(a);
			URL.revokeObjectURL(url);

			this.eventBus.emit('config:exported', {});
			this.eventBus.emit('ui:update', { id: 'status', content: 'Config exported successfully!' });
			setTimeout(() => {
				this.eventBus.emit('ui:update', { id: 'status', content: 'Right-click to add nodes.' });
			}, 2000);
		} catch (e) {
			this.showError('Export config failed: ' + e.message);
		}
	}

	buildConfig(schemaName) {
		const schemaInfo = this.graph.schemas[schemaName];
		const config = {};
		const nodesByType = {};
		const nodeToIndex = new Map();
		
		let fieldMapping = schemaInfo.fieldMapping;
	
		for (const node of this.graph.nodes) {
			if (node.schemaName !== schemaName) continue;
			if (!nodesByType[node.modelName]) {
				nodesByType[node.modelName] = [];
			}
			const index = nodesByType[node.modelName].length;
			nodesByType[node.modelName].push(node);
			nodeToIndex.set(node, { modelName: node.modelName, index });
		}
	
		for (const modelName in nodesByType) {
			const nodes = nodesByType[modelName];
			const fieldName = fieldMapping.modelToField[modelName];
			
			config[fieldName] = [];
			for (const node of nodes) {
				node.onExecute();
				const nodeData = node.outputs[0].value || {};
				const processedData = this.processNodeDataWithIndices(nodeData, nodeToIndex, fieldMapping);
				config[fieldName].push(processedData);
			}
		}
	
		return config;
	}

	processValueForConfig(value, nodeToIndex) {
		if (value === null || value === undefined) return value;
		if (typeof value !== 'object') return value;
		
		if (Array.isArray(value)) {
			return value.map(v => this.processValueForConfig(v, nodeToIndex));
		}
		
		for (const [node, info] of nodeToIndex.entries()) {
			if (node.outputs && node.outputs[0] && node.outputs[0].value === value) {
				return info.index;
			}
		}
		
		const processed = {};
		for (const key in value) {
			if (value.hasOwnProperty(key)) {
				processed[key] = this.processValueForConfig(value[key], nodeToIndex);
			}
		}
		
		return processed;
	}

	_extractModelTypeFromUnionField(fieldType) {
		if (!fieldType) return null;
		
		let workingType = fieldType;
		console.log('					Extracting model type from:', workingType);
		
		if (workingType.kind === 'optional') {
			workingType = workingType.inner;
			console.log('					After stripping Optional:', workingType);
		}
		
		if (workingType.kind === 'basic' && workingType.name) {
			const primitives = ['str', 'int', 'bool', 'float', 'Any', 'Index', 'string', 'integer'];
			if (primitives.indexOf(workingType.name) === -1) {
				console.log('					Direct model reference:', workingType.name);
				return workingType.name;
			}
		}
		
		if (workingType.kind === 'list' || workingType.kind === 'set' || workingType.kind === 'tuple') {
			workingType = workingType.inner;
			console.log('					After stripping collection:', workingType);
		}
		
		const dictMatch = workingType.kind === 'dict';
		if (dictMatch) {
			return null;
		}
		
		if (workingType.kind === 'union') {
			const types = workingType.types;
			console.log('					Union contains types:', types.map(t => t.name || t.kind));
			
			for (const t of types) {
				if (t.kind === 'basic' && t.name) {
					const trimmed = t.name.trim();
					if (trimmed !== 'Index' && trimmed !== 'int' && !trimmed.startsWith('int ')) {
						console.log('					 Selected model type from union:', trimmed);
						return trimmed;
					}
				}
			}
			console.warn('					 No model type found in union, only Index/int');
			return null;
		}
		
		console.log('					 Type is primitive or unsupported:', workingType);
		return null;
	}

	processNodeDataWithIndices(data, nodeToIndex, fieldMapping) {
		const result = {};
		
		for (const key in data) {
			if (!data.hasOwnProperty(key)) continue;
			const value = data[key];
	
			if (Array.isArray(value)) {
				result[key] = value.map(v => this.valueToIndexOrData(v, nodeToIndex));
			} else {
				result[key] = this.valueToIndexOrData(value, nodeToIndex);
			}
		}
		
		return result;
	}

	valueToIndexOrData(value, nodeToIndex) {
		if (value === null || value === undefined) return value;
		if (typeof value !== 'object') return value;
		if (Array.isArray(value)) return value;
		
		for (const [node, info] of nodeToIndex.entries()) {
			if (node.outputs && node.outputs[0] && node.outputs[0].value === value) {
				return info.index;
			}
		}
		
		if (typeof value === 'string') {
			if ((value.startsWith('{') && value.endsWith('}')) || 
					(value.startsWith('[') && value.endsWith(']'))) {
				try {
					return JSON.parse(value);
				} catch (e) {
					return value;
				}
			}
			return value;
		}
		
		const processed = {};
		for (const k in value) {
			if (value.hasOwnProperty(k)) {
				processed[k] = this.valueToIndexOrData(value[k], nodeToIndex);
			}
		}
		
		return processed;
	}

	importConfigData(configData, schemaName = null) {
		console.log('=== IMPORT CONFIG STARTED ===');
		console.log('Config data:', configData);
		
		const schemas = this.graph.getRegisteredSchemas();
		if (schemas.length === 0) {
			this.showError('No schemas registered. Upload a schema first.');
			return;
		}
	
		let targetSchema = schemaName;
		if (!targetSchema) {
			for (const schema of schemas) {
				const info = this.graph.getSchemaInfo(schema);
				if (info && info.rootType) {
					targetSchema = schema;
					break;
				}
			}
		}
	
		if (!targetSchema) {
			targetSchema = schemas[0];
		}
	
		console.log('Target schema:', targetSchema);
		const schemaInfo = this.graph.schemas[targetSchema];
		
		let fieldMapping = schemaInfo.fieldMapping;
		if (!fieldMapping) {
			console.log('Generating field mapping for schema:', targetSchema);
			fieldMapping = this.graph._createFieldMappingFromSchema(schemaInfo.code, schemaInfo.parsed, schemaInfo.rootType);
			schemaInfo.fieldMapping = fieldMapping;
		}
	
		console.log('Field mapping:', fieldMapping);
	
		this.graph.nodes = [];
		this.graph.links = {};
		this.graph._nodes_by_id = {};
		this.graph.last_link_id = 0;
	
		const createdNodes = {};
		const alNodesForField = {};
		let xOffset = 50;
		const yOffset = 100;
		const xSpacing = 250;
	
		let rootType = schemaInfo.rootType;
		let rootListFields = new Set();
		let singleReferenceFields = {};
		
		if (rootType && schemaInfo.parsed[rootType]) {
			const rootFields = schemaInfo.parsed[rootType];
			
			const modelTypeToListField = {};
			
			for (const field of rootFields) {
				const fieldType = field.type;
				if (this.graph._isListFieldType(fieldType)) {
					const modelType = this.graph._extractModelTypeFromField(fieldType);
					if (modelType) {
						rootListFields.add(field.name);
						modelTypeToListField[modelType] = field.name;
						console.log(`List field: ${field.name} contains model type ${modelType}`);
					}
				}
			}
			
			for (const field of rootFields) {
				const fieldType = field.type;
				if (!this.graph._isListFieldType(fieldType)) {
					const modelType = this._extractModelTypeFromUnionField(fieldType);
					if (modelType) {
						const listFieldName = modelTypeToListField[modelType];
						if (listFieldName) {
							singleReferenceFields[field.name] = listFieldName;
							console.log(`Single reference: ${field.name} (${modelType}) → ${listFieldName}`);
						} else {
							console.log(`âš ï¸ No list field found for model type ${modelType} from field ${field.name}`);
						}
					}
				}
			}
		}
		
		console.log('Root list fields:', Array.from(rootListFields));
		console.log('Single reference mappings:', singleReferenceFields);

		for (const fieldName in configData) {
			if (!configData.hasOwnProperty(fieldName)) continue;
			const items = configData[fieldName];
			
			if (singleReferenceFields[fieldName]) {
				console.log(`Skipping single reference field: ${fieldName} (will be added to ${singleReferenceFields[fieldName]})`);
				continue;
			}
			
			const modelName = fieldMapping.fieldToModel[fieldName];
			console.log('📦 Field:', fieldName, '→ Model:', modelName);
			
			if (!modelName) {
				console.warn('⚠️ Unknown field name:', fieldName, '- cannot map to model type');
				continue;
			}
			
			const nodeType = targetSchema + '.' + modelName;
			console.log('	 Node type:', nodeType);
	
			if (!this.graph.nodeTypes[nodeType]) {
				console.warn('⚠️ Node type not found:', nodeType);
				continue;
			}
	
			if (!createdNodes[fieldName]) {
				createdNodes[fieldName] = [];
			}
			
			if (!alNodesForField[fieldName]) {
				alNodesForField[fieldName] = [];
			}
	
			const isListField = Array.isArray(items);
			
			if (isListField) {
				console.log('	 Creating', items.length, 'nodes for list field');
				for (let i = 0; i < items.length; i++) {
					const node = this.graph.createNode(nodeType);
					node.pos = [xOffset, yOffset + i * 150];
					createdNodes[fieldName].push(node);
					alNodesForField[fieldName].push(node);
					console.log('	 ✔ Created', nodeType, 'at index', i, '- node ID:', node.id);
				}
			} else {
				console.log('	 Creating 1 node for single field');
				const node = this.graph.createNode(nodeType);
				node.pos = [xOffset, yOffset];
				createdNodes[fieldName].push(node);
				alNodesForField[fieldName].push(node);
				console.log('	 ✔ Created', nodeType, '- node ID:', node.id);
			}
	
			xOffset += xSpacing;
		}
		
		for (const singleField in singleReferenceFields) {
			if (!configData[singleField]) continue;
			
			const arrayField = singleReferenceFields[singleField];
			const item = configData[singleField];
			
			console.log(`Moving ${singleField} to ${arrayField} array`);
			
			const modelName = fieldMapping.fieldToModel[arrayField];
			const nodeType = targetSchema + '.' + modelName;
			
			if (!this.graph.nodeTypes[nodeType]) {
				console.warn('⚠️ Node type not found:', nodeType);
				continue;
			}
			
			const node = this.graph.createNode(nodeType);
			node.pos = [xOffset, yOffset];
			
			if (!createdNodes[arrayField]) {
				createdNodes[arrayField] = [];
			}
			if (!alNodesForField[arrayField]) {
				alNodesForField[arrayField] = [];
			}
			
			createdNodes[arrayField].unshift(node);
			alNodesForField[arrayField].unshift(node);
			
			console.log(`	 ✔ Added ${singleField} to ${arrayField} at index 0`);
			
			xOffset += xSpacing;
		}
		
		console.log('📦 Top-level node creation complete');
		console.log('	 Created nodes for fields:', Object.keys(createdNodes).join(', '));
		for (const fieldName in alNodesForField) {
			if (alNodesForField.hasOwnProperty(fieldName)) {
				const nodeIds = alNodesForField[fieldName].map(n => n.id).join(', ');
				console.log('	 ', fieldName + ':', alNodesForField[fieldName].length, 'nodes - IDs:', nodeIds);
			}
		}
	
		const nodesBefore = this.graph.nodes.length;
		
		for (const fieldName in configData) {
			if (!configData.hasOwnProperty(fieldName)) continue;
			
			if (singleReferenceFields[fieldName]) {
				const arrayField = singleReferenceFields[fieldName];
				const item = configData[fieldName];
				if (createdNodes[arrayField] && createdNodes[arrayField][0]) {
					this.populateNodeFromConfig(createdNodes[arrayField][0], item, createdNodes, fieldMapping);
				}
				continue;
			}
			
			const items = configData[fieldName];
			const isListField = Array.isArray(items);
			
			if (isListField) {
				for (let i = 0; i < items.length; i++) {
					const item = items[i];
					const node = createdNodes[fieldName][i];
					this.populateNodeFromConfig(node, item, createdNodes, fieldMapping);
				}
			} else {
				if (createdNodes[fieldName] && createdNodes[fieldName][0]) {
					const node = createdNodes[fieldName][0];
					if (typeof items === 'number') {
						console.log('Single field with index reference:', fieldName, '→', items);
					} else if (typeof items === 'object' && items !== null) {
						this.populateNodeFromConfig(node, items, createdNodes, fieldMapping);
					}
				}
			}
		}
		
		const nodesAfter = this.graph.nodes.length;
		console.log('Nodes created during population:', nodesAfter - nodesBefore, '(embedded nodes)');
	
		if (schemaInfo && schemaInfo.rootType) {
			const rootNodeType = targetSchema + '.' + schemaInfo.rootType;
			if (this.graph.nodeTypes[rootNodeType]) {
				const rootNode = this.graph.createNode(rootNodeType);
				rootNode.pos = [-300, yOffset];
				console.log('Created root node:', rootNodeType, 'at', rootNode.pos);
				
				console.log('🔗 Connecting root node to field nodes...');
				console.log('	 Root node has', rootNode.inputs.length, 'inputs');
				console.log('	 Config has', Object.keys(configData).length, 'fields');
				
				for (const fieldName in configData) {
					if (!configData.hasOwnProperty(fieldName)) continue;
					
					console.log('');
					console.log('🔌 Processing field:', fieldName);
					
					const inputIdx = rootNode.inputs.findIndex(inp => inp.name === fieldName);
					if (inputIdx === -1) {
						console.warn('⚠️ No input slot found on root node for field:', fieldName);
						console.warn('	 Available inputs:', rootNode.inputs.map(inp => inp.name).join(', '));
						continue;
					}
					
					console.log('	 ✔ Found input slot:', inputIdx, '(type:', rootNode.inputs[inputIdx].type + ')');
					
					let targetFieldName = fieldName;
					let useIndex = null;
					
					if (singleReferenceFields[fieldName]) {
						targetFieldName = singleReferenceFields[fieldName];
						useIndex = 0;
						console.log(`	 Single reference field - using ${targetFieldName}[0]`);
					}
					
					const items = configData[fieldName];
					const isListField = Array.isArray(items);
					
					console.log('	 Value is', isListField ? 'array with ' + items.length + ' items' : typeof items);
					
					const fieldNodes = alNodesForField[targetFieldName] || [];
					
					console.log('	 Looking for nodes in alNodesForField["' + targetFieldName + '"]');
					console.log('	 Found:', fieldNodes.length, 'nodes');
					
					if (fieldNodes.length === 0) {
						console.warn('⚠️ No nodes in alNodesForField for:', targetFieldName);
						console.warn('	 Available field keys:', Object.keys(alNodesForField).join(', '));
						if (rootNode.nativeInputs && rootNode.nativeInputs[inputIdx] !== undefined) {
							console.log('	 → Field is a native input, setting value directly');
							if (typeof items === 'object') {
								rootNode.nativeInputs[inputIdx].value = JSON.stringify(items);
							} else {
								rootNode.nativeInputs[inputIdx].value = items;
							}
							console.log('	 ✅ Set native value:', items);
						}
						continue;
					}
					
					const nodeInfo = fieldNodes.map(n => n.id + ':' + n.title).join(', ');
					console.log('	 Node details:', nodeInfo);
					
					if (useIndex !== null) {
						console.log('	 ✔ Connecting single reference to index', useIndex);
						const refNode = fieldNodes[useIndex];
						if (refNode) {
							this.graph.connect(refNode, 0, rootNode, inputIdx);
							console.log('	 ✅ Connected', refNode.title, 'to root at slot', inputIdx);
						}
					}
					else if (isListField) {
						if (rootNode.multiInputs && rootNode.multiInputs[inputIdx]) {
							console.log('	 ✔ Field is multi-input (list field)');
							for (const node of fieldNodes) {
								const linkId = ++this.graph.last_link_id;
								const link = new Link(
									linkId,
									node.id,
									0,
									rootNode.id,
									inputIdx,
									node.outputs[0].type
								);
								this.graph.links[linkId] = link;
								node.outputs[0].links.push(linkId);
								rootNode.multiInputs[inputIdx].links.push(linkId);
								console.log('	 ✅ Connected', node.title, 'to root at slot', inputIdx);
							}
						} else {
							console.warn('	 ⚠️ Expected multi-input but not found for field:', fieldName);
						}
					}
					else {
						console.log('	 ✔ Field is single-input');
						if (typeof items === 'number') {
							console.log('	 → Value is an index reference:', items);
							const modelName = fieldMapping.fieldToModel[fieldName];
							const refNode = this.findNodeByTypeAndIndex(modelName, items, createdNodes, fieldMapping);
							if (refNode) {
								this.graph.connect(refNode, 0, rootNode, inputIdx);
								console.log('	 ✅ Connected indexed node', refNode.title, 'to root');
							} else {
								console.warn('	 ⚠️ Could not find referenced node at index', items);
							}
						} else if (fieldNodes[0]) {
							this.graph.connect(fieldNodes[0], 0, rootNode, inputIdx);
							console.log('	 ✅ Connected', fieldNodes[0].title, 'to root at slot', inputIdx);
						} else if (rootNode.nativeInputs && rootNode.nativeInputs[inputIdx] !== undefined) {
							console.log('	 → Setting native value');
							if (typeof items === 'object') {
								rootNode.nativeInputs[inputIdx].value = JSON.stringify(items);
							} else {
								rootNode.nativeInputs[inputIdx].value = items;
							}
							console.log('	 ✅ Set native value');
						}
					}
				}
				
				console.log('🎯 Root node connection summary:');
				console.log('	 Total inputs:', rootNode.inputs.length);
				
				let connectedCount = 0;
				for (let i = 0; i < rootNode.inputs.length; i++) {
					const input = rootNode.inputs[i];
					const fieldName = input.name;
					const isInConfig = configData.hasOwnProperty(fieldName);
					
					if (rootNode.multiInputs && rootNode.multiInputs[i]) {
						const links = rootNode.multiInputs[i].links.length;
						if (links > 0) {
							console.log('	 ✔', fieldName, '(multi):', links, 'connections', isInConfig ? '' : '⚠️ NOT IN CONFIG');
							connectedCount++;
						} else {
							console.log('	 ✗', fieldName, '(multi): no connections', isInConfig ? '❌ WAS IN CONFIG!' : '(not in config)');
						}
					} else if (input.link) {
						console.log('	 ✔', fieldName, ': connected', isInConfig ? '' : '⚠️ NOT IN CONFIG');
						connectedCount++;
					} else if (rootNode.nativeInputs && rootNode.nativeInputs[i]) {
						const val = rootNode.nativeInputs[i].value;
						const isEmpty = val === null || val === undefined || val === '';
						const hasValue = !isEmpty || typeof val === 'boolean' || typeof val === 'number';
						
						if (hasValue) {
							console.log('	 ✔', fieldName, '(native):', JSON.stringify(val), '(type: ' + typeof val + ')', isInConfig ? '' : '⚠️ NOT IN CONFIG');
							connectedCount++;
						} else {
							console.log('	 ◯', fieldName, '(native): empty', rootNode.nativeInputs[i].optional ? '(optional)' : '❌ REQUIRED!', isInConfig ? '❌ WAS IN CONFIG!' : '');
						}
					} else {
						console.log('	 ✗', fieldName, ': not connected', isInConfig ? '❌ WAS IN CONFIG!' : '(not in config)');
					}
				}
				console.log('	 Connected:', connectedCount, '/', rootNode.inputs.length);
			}
		}
	
		for (const node of this.graph.nodes) {
			node.onExecute();
		}
	
		this.updateSchemaList();
		this.updateNodeTypesList();
		this.draw();
	
		console.log('=== IMPORT CONFIG COMPLETE ===');
		const statusEl = document.getElementById('sg-status');
		if (statusEl) {
			statusEl.textContent = 'Config imported successfully!';
			setTimeout(() => {
				statusEl.textContent = 'Right-click to add nodes.';
			}, 2000);
		}
	}

	populateNodeFromConfig(node, configItem, createdNodes, fieldMapping) {
		for (let i = 0; i < node.inputs.length; i++) {
			const input = node.inputs[i];
			const fieldName = input.name;
			const value = configItem[fieldName];
	
			if ((value === undefined || value === null) && node.nativeInputs && node.nativeInputs[i]) {
				if (node.nativeInputs[i].optional) {
					node.nativeInputs[i].value = '';
					continue;
				}
			}
	
			if (value === undefined || value === null) continue;
	
			const expectedType = input.type;
			const isDictType = expectedType && (expectedType.indexOf('Dict[') === 0 || expectedType.indexOf('dict[') === 0);
	
			if (typeof value === 'number' && !Array.isArray(value)) {
				const refNode = this.findNodeByTypeAndIndex(expectedType, value, createdNodes, fieldMapping);
				if (refNode) {
					this.graph.connect(refNode, 0, node, i);
				} else {
					if (node.nativeInputs && node.nativeInputs[i] !== undefined) {
						node.nativeInputs[i].value = value;
					}
				}
			} else if (Array.isArray(value)) {
				for (const item of value) {
					if (typeof item === 'number') {
						const refNode = this.findNodeByTypeAndIndex(expectedType, item, createdNodes, fieldMapping);
						if (refNode) {
							if (node.multiInputs && node.multiInputs[i]) {
								const linkId = ++this.graph.last_link_id;
								const link = new Link(
									linkId,
									refNode.id,
									0,
									node.id,
									i,
									refNode.outputs[0].type
								);
								this.graph.links[linkId] = link;
								refNode.outputs[0].links.push(linkId);
								node.multiInputs[i].links.push(linkId);
							} else {
								this.graph.connect(refNode, 0, node, i);
							}
						}
					} else if (typeof item === 'object' && item !== null) {
						const embeddedNode = this.createEmbeddedNode(item, node.schemaName, createdNodes, fieldMapping, expectedType);
						if (embeddedNode) {
							if (node.multiInputs && node.multiInputs[i]) {
								const linkId = ++this.graph.last_link_id;
								const link = new Link(
									linkId,
									embeddedNode.id,
									0,
									node.id,
									i,
									embeddedNode.outputs[0].type
								);
								this.graph.links[linkId] = link;
								embeddedNode.outputs[0].links.push(linkId);
								node.multiInputs[i].links.push(linkId);
							} else {
								this.graph.connect(embeddedNode, 0, node, i);
							}
						}
					}
				}
			} else if (typeof value === 'object' && value !== null && !isDictType) {
				const embeddedNode = this.createEmbeddedNode(value, node.schemaName, createdNodes, fieldMapping, expectedType);
				if (embeddedNode) {
					this.graph.connect(embeddedNode, 0, node, i);
				}
			} else {
				if (node.nativeInputs && node.nativeInputs[i] !== undefined) {
					if (typeof value === 'object') {
						node.nativeInputs[i].value = JSON.stringify(value);
					} else if (typeof value === 'boolean') {
						node.nativeInputs[i].value = value;
					} else {
						node.nativeInputs[i].value = value;
					}
				}
			}
		}
	}

	findNodeByTypeAndIndex(expectedType, index, createdNodes, fieldMapping) {
		let targetType = expectedType;
		
		const listMatch = targetType.match(/List\[(.+)\]/);
		if (listMatch) {
			targetType = listMatch[1];
		}
		
		const optionalMatch = targetType.match(/Optional\[(.+)\]/);
		if (optionalMatch) {
			targetType = optionalMatch[1];
		}
		
		const unionMatch = targetType.match(/Union\[([^\]]+)\]/);
		if (unionMatch) {
			const types = unionMatch[1].split(',').map(t => t.trim());
			for (const t of types) {
				if (t.endsWith('Config') || (!t.includes('Index') && t !== 'int')) {
					targetType = t;
					break;
				}
			}
		}
		
		const modelName = targetType;
		console.log('Finding node by index:', { originalType: expectedType, extractedModel: modelName, index });
		
		if (!fieldMapping || !fieldMapping.modelToField) {
			console.warn('Field mapping not available for', modelName);
			return null;
		}
		
		const fieldName = fieldMapping.modelToField[modelName] || this.graph.modelNameToFieldName(modelName);
		console.log('	Mapped to field:', fieldName);
		
		if (createdNodes[fieldName] && index >= 0 && index < createdNodes[fieldName].length) {
			console.log('	✓ Found node at', fieldName + '[' + index + ']');
			return createdNodes[fieldName][index];
		}
		
		for (const field in createdNodes) {
			if (!createdNodes.hasOwnProperty(field)) continue;
			const nodes = createdNodes[field];
			if (nodes.length > 0 && nodes[0].modelName === modelName) {
				if (index >= 0 && index < nodes.length) {
					console.log('	✓ Found node via fallback at', field + '[' + index + ']');
					return nodes[index];
				}
			}
		}
		
		console.warn('	✗ Node not found for', modelName, 'at index', index);
		return null;
	}

	isNativeCollectionType(typeString) {
		if (!typeString) return false;
		
		const collectionMatch = typeString.match(/^(Optional\[)?(List|Set|Tuple|Dict|dict)\[(.+)\]$/);
		if (!collectionMatch) return false;
		
		const innerType = collectionMatch[3];
		
		if (collectionMatch[2] === 'Dict' || collectionMatch[2] === 'dict') {
			if (innerType.indexOf('Union[') !== -1 && innerType.match(/[A-Z][a-zA-Z]*Config/)) {
				return false;
			}
			return true;
		}
		
		const primitives = ['str', 'int', 'bool', 'float', 'Any', 'string', 'integer'];
		
		let checkType = innerType;
		const optMatch = checkType.match(/^Optional\[(.+)\]$/);
		if (optMatch) checkType = optMatch[1];
		
		if (primitives.indexOf(checkType) !== -1) {
			return true;
		}
		
		const unionMatch = checkType.match(/^Union\[(.+)\]$/);
		if (unionMatch) {
			if (unionMatch[1].match(/[A-Z][a-zA-Z]*Config/)) {
				return false;
			}
			return true;
		}
		
		return false;
	}

	extractModelTypeFromUnionOrOptional(typeString) {
		if (!typeString) return null;
		
		let workingType = typeString.trim();
		console.log('					Extracting model type from:', workingType);
		
		const optionalMatch = workingType.match(/^Optional\[(.+)\]$/);
		if (optionalMatch) {
			workingType = optionalMatch[1].trim();
			console.log('					After stripping Optional:', workingType);
		}
		
		const listMatch = workingType.match(/^(List|Set|Tuple)\[(.+)\]$/);
		if (listMatch) {
			workingType = listMatch[2].trim();
			console.log('					After stripping ' + listMatch[1] + ':', workingType);
		}
		
		const dictMatch = workingType.match(/^(Dict|dict)\[(.+)\]$/);
		if (dictMatch) {
			const dictContent = dictMatch[2];
			const parts = this.splitTypeParameters(dictContent);
			if (parts.length >= 2) {
				workingType = parts[1].trim();
				console.log('					After stripping Dict, got value type:', workingType);
			}
		}
		
		const unionMatch = workingType.match(/^Union\[(.+)\]$/);
		if (unionMatch) {
			const unionContent = unionMatch[1];
			const types = this.splitTypeParameters(unionContent);
			console.log('					Union contains types:', types);
			
			for (const t of types) {
				const trimmed = t.trim();
				if (trimmed !== 'Index' && trimmed !== 'int' && !trimmed.startsWith('int ')) {
					console.log('					✅ Selected model type from union:', trimmed);
					return trimmed;
				}
			}
			console.warn('					⚠️ No model type found in union, only Index/int');
			return null;
		}
		
		const primitives = ['str', 'int', 'bool', 'float', 'Any', 'Index', 'string', 'integer'];
		if (primitives.indexOf(workingType) === -1) {
			console.log('					✅ Direct model type:', workingType);
			return workingType;
		}
		
		console.log('					→ Type is primitive:', workingType);
		return null;
	}

	splitTypeParameters(str) {
		const result = [];
		let current = '';
		let depth = 0;
		
		for (let i = 0; i < str.length; i++) {
			const char = str[i];
			if (char === '[') depth++;
			if (char === ']') depth--;
			
			if (char === ',' && depth === 0) {
				if (current.trim()) result.push(current.trim());
				current = '';
			} else {
				current += char;
			}
		}
		
		if (current.trim()) result.push(current.trim());
		return result;
	}

	createEmbeddedNode(configItem, schemaName, createdNodes, fieldMapping, expectedType) {
		console.log('			🔨 Creating embedded node');
		console.log('				 Expected type from schema:', expectedType);
		console.log('				 Config item keys:', Object.keys(configItem).join(', '));
		
		if (this.isNativeCollectionType(expectedType)) {
			console.log('				 ℹ️ Skipping node creation - native collection type:', expectedType);
			return null;
		}
		
		const targetModelType = this.extractModelTypeFromUnionOrOptional(expectedType);
		
		if (targetModelType) {
			const nodeType = schemaName + '.' + targetModelType;
			console.log('				 Attempting to create:', nodeType);
			
			if (this.graph.nodeTypes[nodeType]) {
				const node = this.graph.createNode(nodeType);
				node.pos = [Math.random() * 400 + 100, Math.random() * 400 + 100];
				console.log('				 ✅ Created:', nodeType);
				this.populateNodeFromConfig(node, configItem, createdNodes, fieldMapping);
				return node;
			} else {
				console.error('				 ❌ Node type does not exist:', nodeType);
				console.error('				 Available types:', Object.keys(this.graph.nodeTypes).filter(t => t.indexOf(schemaName) === 0).join(', '));
			}
		} else {
			console.warn('				 ⚠️ Could not extract model type from:', expectedType);
		}
		
		console.log('				 ⚠️ FALLBACK: Trying field matching (ambiguous!)');
		let bestMatch = null;
		let bestMatchScore = 0;
		const itemKeys = Object.keys(configItem);
		
		for (const nodeType in this.graph.nodeTypes) {
			if (!this.graph.nodeTypes.hasOwnProperty(nodeType)) continue;
			if (nodeType.indexOf(schemaName + '.') !== 0) continue;
			
			const tempNode = new (this.graph.nodeTypes[nodeType])();
			const tempInputNames = tempNode.inputs.map(inp => inp.name);
			
			let matchScore = 0;
			for (const key of itemKeys) {
				if (tempInputNames.indexOf(key) !== -1) {
					matchScore++;
				}
			}
			
			if (matchScore === itemKeys.length && matchScore > bestMatchScore) {
				bestMatch = nodeType;
				bestMatchScore = matchScore;
			}
		}
		
		if (bestMatch) {
			console.log('				 ⚠️ Using best field match:', bestMatch, '(score:', bestMatchScore + ')');
			const node = this.graph.createNode(bestMatch);
			node.pos = [Math.random() * 400 + 100, Math.random() * 400 + 100];
			this.populateNodeFromConfig(node, configItem, createdNodes, fieldMapping);
			return node;
		}

		console.error('				 ❌ Complete failure - could not create node!');
		return null;
	}

	removeLink(linkId, targetNode, targetSlot) {
		const link = this.graph.links[linkId];
		if (link) {
			const originNode = this.graph.getNodeById(link.origin_id);
			if (originNode) {
				const idx = originNode.outputs[link.origin_slot].links.indexOf(linkId);
				if (idx > -1) originNode.outputs[link.origin_slot].links.splice(idx, 1);
			}
			delete this.graph.links[linkId];
			targetNode.inputs[targetSlot].link = null;
			this.eventBus.emit('link:deleted', { linkId });
		}
	}

	disconnectLink(linkId) {
		const link = this.graph.links[linkId];
		if (!link) {
			console.warn('❌ Link not found:', linkId);
			return false;
		}

		const originNode = this.graph.getNodeById(link.origin_id);
		const targetNode = this.graph.getNodeById(link.target_id);

		console.log(`🔗 Disconnecting link ${linkId}: ${originNode?.title} → ${targetNode?.title}`);

		if (originNode) {
			const idx = originNode.outputs[link.origin_slot].links.indexOf(linkId);
			if (idx > -1) {
				originNode.outputs[link.origin_slot].links.splice(idx, 1);
			}
		}

		if (targetNode) {
			if (targetNode.multiInputs && targetNode.multiInputs[link.target_slot]) {
				const multiIdx = targetNode.multiInputs[link.target_slot].links.indexOf(linkId);
				if (multiIdx > -1) {
					targetNode.multiInputs[link.target_slot].links.splice(multiIdx, 1);
				}
			} else {
				targetNode.inputs[link.target_slot].link = null;
			}
		}

		delete this.graph.links[linkId];
		this.eventBus.emit('link:deleted', { linkId });
		return true;
	}

	clearMultiInputLinks(node, slotIdx) {
		if (!node || !node.multiInputs || !node.multiInputs[slotIdx]) {
			console.warn('❌ Not a multi-input slot');
			return false;
		}

		const links = node.multiInputs[slotIdx].links.slice();
		const slotName = node.inputs[slotIdx] ? node.inputs[slotIdx].name : 'slot' + slotIdx;
		let cleared = 0;

		for (const linkId of links) {
			if (this.disconnectLink(linkId)) {
				cleared++;
			}
		}

		console.log(`✅ Cleared ${cleared} links from slot "${slotName}" on node "${node.title}"`);
		
		if (cleared > 0) {
			this.eventBus.emit('ui:update', { 
				id: 'status', 
				content: `Cleared ${cleared} link(s) from ${slotName}` 
			});
			setTimeout(() => {
				this.eventBus.emit('ui:update', { id: 'status', content: 'Right-click to add nodes.' });
			}, 2000);
		}
		
		this.draw();
		return cleared > 0;
	}

	clearAllMultiInputLinks(node) {
		if (!node || !node.multiInputs) {
			console.warn('❌ Node has no multi-input slots', node);
			return false;
		}

		let totalCleared = 0;
		const slotInfo = [];
		
		for (const slotIdx in node.multiInputs) {
			if (node.multiInputs.hasOwnProperty(slotIdx)) {
				const links = node.multiInputs[slotIdx].links.slice();
				const slotName = node.inputs[slotIdx] ? node.inputs[slotIdx].name : 'slot' + slotIdx;
				slotInfo.push(`${slotName}: ${links.length} links`);
				
				for (const linkId of links) {
					if (this.disconnectLink(linkId)) {
						totalCleared++;
					}
				}
			}
		}

		console.log(`✅ Cleared ${totalCleared} total links from node "${node.title}"`, slotInfo);
		
		if (totalCleared > 0) {
			this.eventBus.emit('ui:update', { 
				id: 'status', 
				content: `Cleared ${totalCleared} multi-input link(s) from ${node.title}` 
			});
			setTimeout(() => {
				this.eventBus.emit('ui:update', { id: 'status', content: 'Right-click to add nodes.' });
			}, 2000);
		}
		
		this.draw();
		return totalCleared > 0;
	}

	removeNode(node) {
		if (!node) return;
		
		for (let j = 0; j < node.inputs.length; j++) {
			if (node.multiInputs && node.multiInputs[j]) {
				const links = node.multiInputs[j].links.slice();
				for (const linkId of links) {
					this.removeLink(linkId, node, j);
				}
			} else if (node.inputs[j].link) {
				this.removeLink(node.inputs[j].link, node, j);
			}
		}
		
		for (let j = 0; j < node.outputs.length; j++) {
			const links = node.outputs[j].links.slice();
			for (const linkId of links) {
				const link = this.graph.links[linkId];
				if (link) {
					const targetNode = this.graph.getNodeById(link.target_id);
					if (targetNode) {
						if (targetNode.multiInputs && targetNode.multiInputs[link.target_slot]) {
							const idx = targetNode.multiInputs[link.target_slot].links.indexOf(linkId);
							if (idx > -1) targetNode.multiInputs[link.target_slot].links.splice(idx, 1);
						} else {
							targetNode.inputs[link.target_slot].link = null;
						}
					}
					delete this.graph.links[linkId];
				}
			}
		}
		
		const idx = this.graph.nodes.indexOf(node);
		if (idx > -1) {
			this.graph.nodes.splice(idx, 1);
			delete this.graph._nodes_by_id[node.id];
		}
		
		if (this.selectedNode === node) {
			this.selectedNode = null;
		}
		
		this.eventBus.emit('node:deleted', { nodeId: node.id });
	}

	isSlotCompatible(node, slotIdx, isOutput) {
		if (!this.connecting || node === this.connecting.node) return false;
		if (this.connecting.isOutput && !isOutput) {
			const outType = this.connecting.node.outputs[this.connecting.slot].type;
			const inType = node.inputs[slotIdx].type;
			return this.graph._areTypesCompatible(outType, inType);
		}
		if (!this.connecting.isOutput && isOutput) {
			const inType = this.connecting.node.inputs[this.connecting.slot].type;
			const outType = node.outputs[slotIdx].type;
			return this.graph._areTypesCompatible(outType, inType);
		}
		return false;
	}

	showError(text) {
		const errorEl = document.getElementById('sg-errorBanner');
		if (!errorEl) return;
		errorEl.textContent = '⚠️ ' + text;
		errorEl.style.display = 'block';
		setTimeout(() => { errorEl.style.display = 'none'; }, 3000);
		this.eventBus.emit('error', { message: text });
	}

	updateNodeTypesList() {
		const listEl = document.getElementById('sg-nodeTypesList');
		if (!listEl) return;
		const types = Object.keys(this.graph.nodeTypes);
		listEl.textContent = types.length > 0 ? types.join(', ') : 'None';
	}

	updateSchemaList() {
		const listEl = document.getElementById('sg-schemaList');
		if (!listEl) return;
		
		const schemas = Object.keys(this.graph.schemas);
		if (schemas.length === 0) {
			listEl.innerHTML = '<div style="color: var(--sg-text-tertiary); font-size: 11px; padding: 8px;">No schemas registered</div>';
			return;
		}
		
		let html = '';
		for (const schemaName of schemas) {
			let nodeCount = 0;
			for (const node of this.graph.nodes) {
				if (node.schemaName === schemaName) nodeCount++;
			}
			
			let typeCount = 0;
			for (const type in this.graph.nodeTypes) {
				if (type.indexOf(schemaName + '.') === 0) typeCount++;
			}
			
			const isEnabled = this.graph.isSchemaEnabled(schemaName);
			
			html += '<div class="sg-schema-item">';
			html += '<div><span class="sg-schema-item-name">' + schemaName + '</span>';
			html += '<span class="sg-schema-item-count">(' + typeCount + ' types, ' + nodeCount + ' nodes)</span></div>';
			html += '<div style="display: flex; gap: 4px;">';
			html += '<button class="sg-schema-toggle-btn ' + (isEnabled ? 'enabled' : 'disabled') + '" data-schema="' + schemaName + '" title="' + (isEnabled ? 'Disable schema' : 'Enable schema') + '">';
			html += (isEnabled ? '👁️ Enabled' : '🚫 Disabled');
			html += '</button>';
			html += '<button class="sg-schema-remove-btn" data-schema="' + schemaName + '">Remove</button>';
			html += '</div>';
			html += '</div>';
		}
		
		listEl.innerHTML = html;
		
		const toggleButtons = listEl.querySelectorAll('.sg-schema-toggle-btn');
		for (const button of toggleButtons) {
			button.addEventListener('click', (e) => {
				e.stopPropagation();
				const schemaName = button.getAttribute('data-schema');
				this.graph.toggleSchema(schemaName);
				this.updateSchemaList();
				this.eventBus.emit('ui:update', { 
					id: 'status', 
					content: `Schema "${schemaName}" ${this.graph.isSchemaEnabled(schemaName) ? 'enabled' : 'disabled'}` 
				});
				setTimeout(() => {
					this.eventBus.emit('ui:update', { id: 'status', content: 'Right-click to add nodes.' });
				}, 2000);
			});
		}
		
		const removeButtons = listEl.querySelectorAll('.sg-schema-remove-btn');
		for (const button of removeButtons) {
			button.addEventListener('click', () => {
				this.openSchemaRemovalDialog();
			});
		}
	}

	openSchemaRemovalDialog() {
		const schemas = Object.keys(this.graph.schemas);
		if (schemas.length === 0) {
			this.showError('No schemas to remove');
			return;
		}
		
		let options = '';
		for (const schemaName of schemas) {
			options += '<option value="' + schemaName + '">' + schemaName + '</option>';
		}
		document.getElementById('sg-schemaRemovalNameInput').innerHTML = options;
		
		this.eventBus.emit('ui:show', { id: 'schemaRemovalDialog' });
		document.getElementById('sg-schemaRemovalNameInput').focus();
	}

	screenToWorld(sx, sy) {
		return [(sx - this.camera.x) / this.camera.scale, (sy - this.camera.y) / this.camera.scale];
	}

	worldToScreen(wx, wy) {
		return [wx * this.camera.scale + this.camera.x, wy * this.camera.scale + this.camera.y];
	}

	resizeCanvas() {
		const container = this.canvas.parentElement;
		const rect = container.getBoundingClientRect();
		this.canvas.width = rect.width;
		this.canvas.height = rect.height;
		this.draw();
	}

	centerView() {
		if (this.graph.nodes.length === 0) return;
		
		let minX = Infinity, minY = Infinity;
		let maxX = -Infinity, maxY = -Infinity;
		
		for (const node of this.graph.nodes) {
			minX = Math.min(minX, node.pos[0]);
			minY = Math.min(minY, node.pos[1]);
			maxX = Math.max(maxX, node.pos[0] + node.size[0]);
			maxY = Math.max(maxY, node.pos[1] + node.size[1]);
		}
		
		const graphWidth = maxX - minX;
		const graphHeight = maxY - minY;
		const graphCenterX = minX + graphWidth / 2;
		const graphCenterY = minY + graphHeight / 2;
		
		const canvasCenterX = this.canvas.width / 2;
		const canvasCenterY = this.canvas.height / 2;
		
		const padding = 100;
		const scaleX = (this.canvas.width - padding * 2) / graphWidth;
		const scaleY = (this.canvas.height - padding * 2) / graphHeight;
		const targetScale = Math.min(scaleX, scaleY, 1.5);
		
		this.camera.scale = Math.max(0.1, Math.min(5, targetScale));
		this.camera.x = canvasCenterX - graphCenterX * this.camera.scale;
		this.camera.y = canvasCenterY - graphCenterY * this.camera.scale;
		
		this.eventBus.emit('ui:update', { 
			id: 'zoomLevel', 
			content: Math.round(this.camera.scale * 100) + '%' 
		});
		this.draw();
	}

	resetZoom() {
		const canvasCenterX = this.canvas.width / 2;
		const canvasCenterY = this.canvas.height / 2;
		const worldCenter = this.screenToWorld(canvasCenterX, canvasCenterY);
		
		this.camera.scale = 1.0;
		this.camera.x = canvasCenterX - worldCenter[0] * this.camera.scale;
		this.camera.y = canvasCenterY - worldCenter[1] * this.camera.scale;
		
		this.eventBus.emit('ui:update', { id: 'zoomLevel', content: '100%' });
		this.draw();
	}

	applyLayout(layoutType) {
		if (this.graph.nodes.length === 0) {
			this.showError('No nodes to layout');
			return;
		}
		
		console.log('Applying layout:', layoutType);
		
		switch (layoutType) {
			case 'hierarchical-vertical':
				this.applyHierarchicalLayout(true);
				break;
			case 'hierarchical-horizontal':
				this.applyHierarchicalLayout(false);
				break;
			case 'force-directed':
				this.applyForceDirectedLayout();
				break;
			case 'grid':
				this.applyGridLayout();
				break;
			case 'circular':
				this.applyCircularLayout();
				break;
			default:
				this.showError('Unknown layout type: ' + layoutType);
				return;
		}
		
		this.eventBus.emit('layout:applied', { layoutType });
		this.draw();
		this.centerView();
	}

	applyHierarchicalLayout(vertical = false) {
		const rootNodes = [];
		const processedNodes = new Set();
		
		for (const node of this.graph.nodes) {
			let hasInputConnection = false;
			for (const input of node.inputs) {
				if (input.link !== null && input.link !== undefined) {
					hasInputConnection = true;
					break;
				}
			}
			if (!hasInputConnection || node.isRootType) {
				rootNodes.push(node);
			}
		}
		
		if (rootNodes.length === 0) {
			rootNodes.push(...this.graph.nodes);
		}
		
		const layers = [];
		const nodeToLayer = new Map();
		
		const queue = [];
		for (const root of rootNodes) {
			queue.push({ node: root, layer: 0 });
			processedNodes.add(root);
		}
		
		while (queue.length > 0) {
			const { node, layer } = queue.shift();
			
			if (!layers[layer]) {
				layers[layer] = [];
			}
			layers[layer].push(node);
			nodeToLayer.set(node, layer);
			
			for (const output of node.outputs) {
				for (const linkId of output.links) {
					const link = this.graph.links[linkId];
					if (link) {
						const targetNode = this.graph.getNodeById(link.target_id);
						if (targetNode && !processedNodes.has(targetNode)) {
							processedNodes.add(targetNode);
							queue.push({ node: targetNode, layer: layer + 1 });
						}
					}
				}
			}
		}
		
		for (const node of this.graph.nodes) {
			if (!processedNodes.has(node)) {
				const lastLayer = layers.length;
				if (!layers[lastLayer]) {
					layers[lastLayer] = [];
				}
				layers[lastLayer].push(node);
			}
		}
		
		const layerSpacing = vertical ? 300 : 200;
		const nodeSpacing = vertical ? 150 : 250;
		const startX = 100;
		const startY = 100;
		
		for (let i = 0; i < layers.length; i++) {
			const layer = layers[i];
			const layerHeight = layer.length * nodeSpacing;
			
			for (let j = 0; j < layer.length; j++) {
				const node = layer[j];
				if (vertical) {
					node.pos[0] = startX + i * layerSpacing;
					node.pos[1] = startY + j * nodeSpacing - layerHeight / 2;
				} else {
					node.pos[0] = startX + j * nodeSpacing - layerHeight / 2;
					node.pos[1] = startY + i * layerSpacing;
				}
			}
		}
	}

	applyForceDirectedLayout() {
		const iterations = 100;
		const repulsionStrength = 50000;
		const attractionStrength = 0.01;
		const damping = 0.9;
		const minDistance = 200;
		
		const velocities = new Map();
		for (const node of this.graph.nodes) {
			velocities.set(node, { x: 0, y: 0 });
		}
		
		const spread = 400;
		for (const node of this.graph.nodes) {
			if (node.pos[0] === 0 && node.pos[1] === 0) {
				node.pos[0] = Math.random() * spread;
				node.pos[1] = Math.random() * spread;
			}
		}
		
		for (let iter = 0; iter < iterations; iter++) {
			for (let i = 0; i < this.graph.nodes.length; i++) {
				const nodeA = this.graph.nodes[i];
				const vel = velocities.get(nodeA);
				
				for (let j = i + 1; j < this.graph.nodes.length; j++) {
					const nodeB = this.graph.nodes[j];
					const dx = nodeB.pos[0] - nodeA.pos[0];
					const dy = nodeB.pos[1] - nodeA.pos[1];
					const distSq = dx * dx + dy * dy;
					const dist = Math.sqrt(distSq);
					
					if (dist < 0.1) continue;
					
					const force = repulsionStrength / distSq;
					const fx = (dx / dist) * force;
					const fy = (dy / dist) * force;
					
					vel.x -= fx;
					vel.y -= fy;
					
					const velB = velocities.get(nodeB);
					velB.x += fx;
					velB.y += fy;
				}
			}
			
			for (const linkId in this.graph.links) {
				const link = this.graph.links[linkId];
				const nodeA = this.graph.getNodeById(link.origin_id);
				const nodeB = this.graph.getNodeById(link.target_id);
				
				if (!nodeA || !nodeB) continue;
				
				const dx = nodeB.pos[0] - nodeA.pos[0];
				const dy = nodeB.pos[1] - nodeA.pos[1];
				const dist = Math.sqrt(dx * dx + dy * dy);
				
				if (dist < 0.1) continue;
				
				const force = (dist - minDistance) * attractionStrength;
				const fx = (dx / dist) * force;
				const fy = (dy / dist) * force;
				
				const velA = velocities.get(nodeA);
				const velB = velocities.get(nodeB);
				
				velA.x += fx;
				velA.y += fy;
				velB.x -= fx;
				velB.y -= fy;
			}
			
			for (const node of this.graph.nodes) {
				const vel = velocities.get(node);
				node.pos[0] += vel.x;
				node.pos[1] += vel.y;
				vel.x *= damping;
				vel.y *= damping;
			}
		}
	}

	applyGridLayout() {
		const cols = Math.ceil(Math.sqrt(this.graph.nodes.length));
		const cellWidth = 250;
		const cellHeight = 200;
		const startX = 100;
		const startY = 100;
		
		for (let i = 0; i < this.graph.nodes.length; i++) {
			const node = this.graph.nodes[i];
			const col = i % cols;
			const row = Math.floor(i / cols);
			
			node.pos[0] = startX + col * cellWidth;
			node.pos[1] = startY + row * cellHeight;
		}
	}

	applyCircularLayout() {
		const centerX = 0;
		const centerY = 0;
		const radius = Math.max(300, this.graph.nodes.length * 30);
		const angleStep = (2 * Math.PI) / this.graph.nodes.length;
		
		const rootNodes = [];
		const regularNodes = [];
		
		for (const node of this.graph.nodes) {
			if (node.isRootType) {
				rootNodes.push(node);
			} else {
				regularNodes.push(node);
			}
		}
		
		if (rootNodes.length > 0) {
			const rootRadius = 100;
			const rootAngleStep = (2 * Math.PI) / rootNodes.length;
			for (let i = 0; i < rootNodes.length; i++) {
				const angle = i * rootAngleStep;
				rootNodes[i].pos[0] = centerX + Math.cos(angle) * rootRadius;
				rootNodes[i].pos[1] = centerY + Math.sin(angle) * rootRadius;
			}
		}
		
		for (let i = 0; i < regularNodes.length; i++) {
			const angle = i * angleStep;
			regularNodes[i].pos[0] = centerX + Math.cos(angle) * radius;
			regularNodes[i].pos[1] = centerY + Math.sin(angle) * radius;
		}
	}

	getCanvasColors() {
		const style = getComputedStyle(document.documentElement);
		return {
			canvasBg: style.getPropertyValue('--sg-canvas-bg').trim(),
			nodeBg: style.getPropertyValue('--sg-node-bg').trim(),
			nodeBgSelected: style.getPropertyValue('--sg-node-bg-selected').trim(),
			nodeHeader: style.getPropertyValue('--sg-node-header').trim(),
			nodeShadow: style.getPropertyValue('--sg-node-shadow').trim(),
			borderColor: style.getPropertyValue('--sg-border-color').trim(),
			borderHighlight: style.getPropertyValue('--sg-border-highlight').trim(),
			textPrimary: style.getPropertyValue('--sg-text-primary').trim(),
			textSecondary: style.getPropertyValue('--sg-text-secondary').trim(),
			textTertiary: style.getPropertyValue('--sg-text-tertiary').trim(),
			accentPurple: style.getPropertyValue('--sg-accent-purple').trim(),
			accentOrange: style.getPropertyValue('--sg-accent-orange').trim(),
			accentGreen: style.getPropertyValue('--sg-accent-green').trim(),
			accentRed: style.getPropertyValue('--sg-accent-red').trim(),
			slotInput: style.getPropertyValue('--sg-slot-input').trim(),
			slotOutput: style.getPropertyValue('--sg-slot-output').trim(),
			slotConnected: style.getPropertyValue('--sg-slot-connected').trim(),
			linkColor: style.getPropertyValue('--sg-link-color').trim(),
			gridColor: style.getPropertyValue('--sg-grid-color').trim()
		};
	}

	draw() {
		const colors = this.getCanvasColors();
		
		this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
		this.ctx.fillStyle = colors.canvasBg;
		this.ctx.fillRect(0, 0, this.canvas.width, this.canvas.height);
		
		this.ctx.save();
		this.ctx.translate(this.camera.x, this.camera.y);
		this.ctx.scale(this.camera.scale, this.camera.scale);
		
		if (!this.connecting && !this.dragNode && !this.isPanning) {
			this.canvas.style.cursor = 'default';
		}
		
		this.drawGrid(colors);
		this.drawLinks(colors);
		this.drawNodes(colors);
		// this.drawLinksAndNodes(colors);
		
		if (this.connecting) {
			this.drawConnecting(colors);
		}
		
		if (this.selectionRect) {
			this.ctx.strokeStyle = colors.borderHighlight;
			this.ctx.fillStyle = 'rgba(70, 162, 218, 0.1)';
			this.ctx.lineWidth = 1 / this.camera.scale;
			this.ctx.setLineDash([5 / this.camera.scale, 5 / this.camera.scale]);
			this.ctx.fillRect(this.selectionRect.x, this.selectionRect.y, this.selectionRect.w, this.selectionRect.h);
			this.ctx.strokeRect(this.selectionRect.x, this.selectionRect.y, this.selectionRect.w, this.selectionRect.h);
			this.ctx.setLineDash([]);
		}
		
		this.ctx.restore();

		if (this.isLocked) {
			// Draw lock indicator in corner
			this.ctx.save();
			
			let pending = '';
			if (this.lockInterval) {
				pending = '.'.repeat(this.lockPending + 1);
			}

			const padding = 10;
			const text = `🔒 ${(this.lockReason || 'Locked') + pending}`;
			const textScale = 1;
			
			this.ctx.font = `bold ${12 * textScale}px Arial, sans-serif`;
			const textWidth = this.ctx.measureText(text).width;
			
			// Background
			this.ctx.fillStyle = 'rgba(220, 100, 100, 0.9)';
			this.ctx.beginPath();
			this.ctx.roundRect(padding, padding, textWidth + 16, 28, 6);
			this.ctx.fill();
			
			// Text
			this.ctx.fillStyle = '#fff';
			this.ctx.textAlign = 'left';
			this.ctx.textBaseline = 'middle';
			this.ctx.fillText(text, padding + 8, padding + 14);
			
			this.ctx.restore();
		}
	}

	drawGrid(colors) {
		const style = this.drawingStyleManager.getStyle();
		const gridSize = 50;
		const worldRect = {
			x: -this.camera.x / this.camera.scale,
			y: -this.camera.y / this.camera.scale,
			width: this.canvas.width / this.camera.scale,
			height: this.canvas.height / this.camera.scale
		};
		
		const startX = Math.floor(worldRect.x / gridSize) * gridSize;
		const startY = Math.floor(worldRect.y / gridSize) * gridSize;
		const endX = worldRect.x + worldRect.width;
		const endY = worldRect.y + worldRect.height;
		
		this.ctx.strokeStyle = colors.gridColor;
		this.ctx.globalAlpha = style.gridOpacity;
		this.ctx.lineWidth = 1 / this.camera.scale;
		
		if (style.useDashed && style.currentStyle === 'blueprint') {
			this.ctx.setLineDash([4 / this.camera.scale, 4 / this.camera.scale]);
		}
		
		this.ctx.beginPath();
		
		for (let x = startX; x <= endX; x += gridSize) {
			this.ctx.moveTo(x, worldRect.y);
			this.ctx.lineTo(x, endY);
		}
		
		for (let y = startY; y <= endY; y += gridSize) {
			this.ctx.moveTo(worldRect.x, y);
			this.ctx.lineTo(endX, y);
		}
		
		this.ctx.stroke();
		
		if (style.useDashed && style.currentStyle === 'blueprint') {
			this.ctx.setLineDash([]);
		}
		
		this.ctx.globalAlpha = 1.0;
	}

	drawLinks(colors) {
		const style = this.drawingStyleManager.getStyle();
		
		for (const linkId in this.graph.links) {
			const link = this.graph.links[linkId];
			const orig = this.graph.getNodeById(link.origin_id);
			const targ = this.graph.getNodeById(link.target_id);
			if (orig && targ) {
				const x1 = orig.pos[0] + orig.size[0];
				const y1 = orig.pos[1] + 33 + link.origin_slot * 25;
				const x2 = targ.pos[0];
				const y2 = targ.pos[1] + 33 + link.target_slot * 25;
				
				const distance = Math.abs(x2 - x1);
				const maxControlDistance = 400;
				const controlOffset = Math.min(distance * style.linkCurve, maxControlDistance);
				const cx1 = x1 + controlOffset;
				const cx2 = x2 - controlOffset;
				
				if (style.linkShadowBlur > 0) {
					this.ctx.strokeStyle = colors.linkColor;
					this.ctx.lineWidth = (style.linkWidth + 3) / this.camera.scale;
					this.ctx.globalAlpha = 0.15;
					
					if (style.useGlow) {
						this.ctx.shadowColor = colors.linkColor;
						this.ctx.shadowBlur = style.linkShadowBlur / this.camera.scale;
					}
					
					this.ctx.beginPath();
					if (style.linkCurve > 0) {
						this.ctx.moveTo(x1, y1);
						this.ctx.bezierCurveTo(cx1, y1, cx2, y2, x2, y2);
					} else {
						this.ctx.moveTo(x1, y1);
						this.ctx.lineTo(x2, y2);
					}
					this.ctx.stroke();
				}
				
				this.ctx.strokeStyle = colors.linkColor;
				this.ctx.lineWidth = style.linkWidth / this.camera.scale;
				this.ctx.globalAlpha = 1.0;
				this.ctx.shadowBlur = 0;
				
				if (style.useDashed) {
					this.ctx.setLineDash([8 / this.camera.scale, 4 / this.camera.scale]);
				}
				
				this.ctx.beginPath();
				if (style.linkCurve > 0) {
					this.ctx.moveTo(x1, y1);
					this.ctx.bezierCurveTo(cx1, y1, cx2, y2, x2, y2);
				} else {
					this.ctx.moveTo(x1, y1);
					this.ctx.lineTo(x2, y2);
				}
				this.ctx.stroke();
				
				if (style.useDashed) {
					this.ctx.setLineDash([]);
				}
			}
		}
		this.ctx.globalAlpha = 1.0;
		this.ctx.shadowBlur = 0;
	}

	drawNodes(colors) {
		// for (const node of this.graph.nodes) {
		// 	this.drawNode(node, colors);
		// }
		const unselectedNodes = [];
		const selectedNodes   = [];
		for (const node of this.graph.nodes) {
			if (this.isNodeSelected(node)) {
				selectedNodes.push(node);
			} else {
				unselectedNodes.push(node);
			}
		}
		for (const node of unselectedNodes) {
			this.drawNode(node, colors);
		}
		for (const node of selectedNodes) {
			this.drawNode(node, colors);
		}
	}

	// drawLinksAndNodes(colors) {
	// 	const style = this.drawingStyleManager.getStyle();
		
	// 	// Separate nodes by selection
	// 	const unselectedNodes = [];
	// 	const selectedNodes = [];
	// 	const selectedNodeIds = new Set();
		
	// 	for (const node of this.graph.nodes) {
	// 		if (this.isNodeSelected(node)) {
	// 			selectedNodes.push(node);
	// 			selectedNodeIds.add(node.id);
	// 		} else {
	// 			unselectedNodes.push(node);
	// 		}
	// 	}
		
	// 	// Separate links by whether they connect to selected nodes
	// 	const unselectedLinks = [];
	// 	const selectedLinks = [];
		
	// 	for (const linkId in this.graph.links) {
	// 		const link = this.graph.links[linkId];
	// 		if (selectedNodeIds.has(link.origin_id) || selectedNodeIds.has(link.target_id)) {
	// 			selectedLinks.push(link);
	// 		} else {
	// 			unselectedLinks.push(link);
	// 		}
	// 	}
		
	// 	// Layer 1: Unselected links
	// 	for (const link of unselectedLinks) {
	// 		this._drawLink(link, colors, style);
	// 	}
		
	// 	// Layer 2: Unselected nodes
	// 	for (const node of unselectedNodes) {
	// 		this.drawNode(node, colors);
	// 	}
		
	// 	// Layer 3: Selected links (on top of unselected nodes)
	// 	for (const link of selectedLinks) {
	// 		this._drawLink(link, colors, style);
	// 	}
		
	// 	// Layer 4: Selected nodes (on top)
	// 	for (const node of selectedNodes) {
	// 		this.drawNode(node, colors);
	// 	}
	// }

	// _drawLink(link, colors, style) {
	// 	const orig = this.graph.getNodeById(link.origin_id);
	// 	const targ = this.graph.getNodeById(link.target_id);
	// 	if (!orig || !targ) return;
		
	// 	const x1 = orig.pos[0] + orig.size[0];
	// 	const y1 = orig.pos[1] + 33 + link.origin_slot * 25;
	// 	const x2 = targ.pos[0];
	// 	const y2 = targ.pos[1] + 33 + link.target_slot * 25;
		
	// 	const distance = Math.abs(x2 - x1);
	// 	const maxControlDistance = 400;
	// 	const controlOffset = Math.min(distance * style.linkCurve, maxControlDistance);
	// 	const cx1 = x1 + controlOffset;
	// 	const cx2 = x2 - controlOffset;
		
	// 	if (style.linkShadowBlur > 0) {
	// 		this.ctx.strokeStyle = colors.linkColor;
	// 		this.ctx.lineWidth = (style.linkWidth + 3) / this.camera.scale;
	// 		this.ctx.globalAlpha = 0.15;
			
	// 		if (style.useGlow) {
	// 			this.ctx.shadowColor = colors.linkColor;
	// 			this.ctx.shadowBlur = style.linkShadowBlur / this.camera.scale;
	// 		}
			
	// 		this.ctx.beginPath();
	// 		if (style.linkCurve > 0) {
	// 			this.ctx.moveTo(x1, y1);
	// 			this.ctx.bezierCurveTo(cx1, y1, cx2, y2, x2, y2);
	// 		} else {
	// 			this.ctx.moveTo(x1, y1);
	// 			this.ctx.lineTo(x2, y2);
	// 		}
	// 		this.ctx.stroke();
	// 	}
		
	// 	this.ctx.strokeStyle = colors.linkColor;
	// 	this.ctx.lineWidth = style.linkWidth / this.camera.scale;
	// 	this.ctx.globalAlpha = 1.0;
	// 	this.ctx.shadowBlur = 0;
		
	// 	if (style.useDashed) {
	// 		this.ctx.setLineDash([8 / this.camera.scale, 4 / this.camera.scale]);
	// 	}
		
	// 	this.ctx.beginPath();
	// 	if (style.linkCurve > 0) {
	// 		this.ctx.moveTo(x1, y1);
	// 		this.ctx.bezierCurveTo(cx1, y1, cx2, y2, x2, y2);
	// 	} else {
	// 		this.ctx.moveTo(x1, y1);
	// 		this.ctx.lineTo(x2, y2);
	// 	}
	// 	this.ctx.stroke();
		
	// 	if (style.useDashed) {
	// 		this.ctx.setLineDash([]);
	// 	}
		
	// 	this.ctx.globalAlpha = 1.0;
	// 	this.ctx.shadowBlur = 0;
	// }

	drawNode(node, colors) {
		const style = this.drawingStyleManager.getStyle();
		const x = node.pos[0];
		const y = node.pos[1];
		const w = node.size[0];
		const h = node.size[1];
		const radius = style.nodeCornerRadius;
		const textScale = this.getTextScale();
		
		if (style.nodeShadowBlur > 0) {
			this.ctx.shadowColor = colors.nodeShadow;
			this.ctx.shadowBlur = style.nodeShadowBlur / this.camera.scale;
			this.ctx.shadowOffsetX = 0;
			this.ctx.shadowOffsetY = style.nodeShadowOffset / this.camera.scale;
		}
		
		const isSelected = this.isNodeSelected(node);
		const isPreviewSelected = this.previewSelection.has(node);
		const bodyColor = isSelected ? colors.nodeBgSelected : 
											(isPreviewSelected ? this.adjustColorBrightness(colors.nodeBg, 20) : colors.nodeBg);
		
		if (style.useGradient && style.currentStyle !== 'wireframe') {
			const gradient = this.ctx.createLinearGradient(x, y, x, y + h);
			gradient.addColorStop(0, bodyColor);
			gradient.addColorStop(1, this.adjustColorBrightness(bodyColor, -20));
			this.ctx.fillStyle = gradient;
		} else {
			this.ctx.fillStyle = style.currentStyle === 'wireframe' ? 'transparent' : bodyColor;
		}
		
		this.ctx.beginPath();
		if (radius > 0) {
			this.ctx.moveTo(x + radius, y);
			this.ctx.lineTo(x + w - radius, y);
			this.ctx.quadraticCurveTo(x + w, y, x + w, y + radius);
			this.ctx.lineTo(x + w, y + h - radius);
			this.ctx.quadraticCurveTo(x + w, y + h, x + w - radius, y + h);
			this.ctx.lineTo(x + radius, y + h);
			this.ctx.quadraticCurveTo(x, y + h, x, y + h - radius);
			this.ctx.lineTo(x, y + radius);
			this.ctx.quadraticCurveTo(x, y, x + radius, y);
			this.ctx.closePath();
		} else {
			this.ctx.rect(x, y, w, h);
		}
		
		if (style.currentStyle !== 'wireframe') {
			this.ctx.fill();
		}
		
		if (isPreviewSelected && !isSelected) {
			this.ctx.strokeStyle = colors.accentGreen;
			this.ctx.lineWidth = 2 / this.camera.scale;
			this.ctx.setLineDash([5 / this.camera.scale, 5 / this.camera.scale]);
		} else {
			this.ctx.strokeStyle = isSelected ? colors.borderHighlight : colors.borderColor;
			this.ctx.lineWidth = (isSelected ? 2 : 1) / this.camera.scale;
		}
		
		if (style.useGlow && (isSelected || isPreviewSelected)) {
			this.ctx.shadowColor = isSelected ? colors.borderHighlight : colors.accentGreen;
			this.ctx.shadowBlur = 15 / this.camera.scale;
		} else {
			this.ctx.shadowBlur = 0;
		}
		
		this.ctx.shadowOffsetX = 0;
		this.ctx.shadowOffsetY = 0;
		this.ctx.stroke();
		
		if (isPreviewSelected && !isSelected) {
			this.ctx.setLineDash([]);
		}
		
		const hasOwnColor = node.hasOwnProperty('color') && (node.color !== null) && (node.color !== undefined);
		const headerColor = hasOwnColor ? node.color : (node.isNative ? colors.accentPurple : 
												(node.isRootType ? colors.accentOrange : colors.nodeHeader));
		
		if (style.useGradient && style.currentStyle !== 'wireframe') {
			const headerGradient = this.ctx.createLinearGradient(x, y, x, y + 26);
			headerGradient.addColorStop(0, headerColor);
			headerGradient.addColorStop(1, this.adjustColorBrightness(headerColor, -30));
			this.ctx.fillStyle = headerGradient;
		} else {
			this.ctx.fillStyle = style.currentStyle === 'wireframe' ? 'transparent' : headerColor;
		}
		
		this.ctx.beginPath();
		if (radius > 0) {
			this.ctx.moveTo(x + radius, y);
			this.ctx.lineTo(x + w - radius, y);
			this.ctx.quadraticCurveTo(x + w, y, x + w, y + radius);
			this.ctx.lineTo(x + w, y + 26);
			this.ctx.lineTo(x, y + 26);
			this.ctx.lineTo(x, y + radius);
			this.ctx.quadraticCurveTo(x, y, x + radius, y);
		} else {
			this.ctx.rect(x, y, w, 26);
		}
		this.ctx.closePath();
		
		if (style.currentStyle !== 'wireframe') {
			this.ctx.fill();
		}
		
		if (style.currentStyle === 'wireframe' || style.currentStyle === 'blueprint') {
			this.ctx.stroke();
		}
		
		this.ctx.save();
		this.ctx.beginPath();
		this.ctx.rect(x + 4, y, w - 8, 26);
		this.ctx.clip();
		
		this.ctx.fillStyle = colors.textPrimary;
		this.ctx.font = (11 * textScale) + 'px ' + style.textFont;
		this.ctx.textBaseline = 'middle';
		this.ctx.textAlign = 'left';
		
		if (style.useGlow && (node.isRootType || node.isNative)) {
			this.ctx.shadowColor = headerColor;
			this.ctx.shadowBlur = (8 * textScale);
		}
		
		let titleText = node.title;
		if (node.isRootType) titleText = '★ ' + titleText;
		
		const maxWidth = w - 16;
		let displayTitle = titleText;
		const textWidth = this.ctx.measureText(displayTitle).width;
		
		if (textWidth > maxWidth) {
			let left = 0;
			let right = displayTitle.length;
			while (left < right) {
				const mid = Math.floor((left + right + 1) / 2);
				const testText = displayTitle.substring(0, mid) + '...';
				if (this.ctx.measureText(testText).width <= maxWidth) {
					left = mid;
				} else {
					right = mid - 1;
				}
			}
			displayTitle = displayTitle.substring(0, left) + '...';
		}
		
		this.ctx.fillText(displayTitle, x + 8, y + 13);
		this.ctx.restore();
		
		this.ctx.shadowColor = 'transparent';
		this.ctx.shadowBlur = 0;
		
		const worldMouse = this.screenToWorld(this.mousePos[0], this.mousePos[1]);
		if (node.inputs) {
				for (let j = 0; j < node.inputs.length; j++) {
					this.drawInputSlot(node, j, x, y, w, worldMouse, colors);
				}
		}
		if (node.inputs) {
				for (let j = 0; j < node.outputs.length; j++) {
						this.drawOutputSlot(node, j, x, y, w, worldMouse, colors);
				}
		}
		
		if (node.isNative && node.properties.value !== undefined) {
			const valueY = y + h - 18;
			const valueX = x + 8;
			const valueW = w - 16;
			const valueH = 18;
			const valueRadius = 4;
			
			const isValueHovered = !this.connecting && 
				worldMouse[0] >= valueX && worldMouse[0] <= valueX + valueW &&
				worldMouse[1] >= valueY - 10 && worldMouse[1] <= valueY - 10 + valueH;
			
			if (style.currentStyle !== 'wireframe') {
				this.ctx.fillStyle = isValueHovered ? 'rgba(0, 0, 0, 0.5)' : 'rgba(0, 0, 0, 0.4)';
				this.ctx.beginPath();
				this.ctx.moveTo(valueX + valueRadius, valueY - 10);
				this.ctx.lineTo(valueX + valueW - valueRadius, valueY - 10);
				this.ctx.quadraticCurveTo(valueX + valueW, valueY - 10, valueX + valueW, valueY - 10 + valueRadius);
				this.ctx.lineTo(valueX + valueW, valueY - 10 + valueH - valueRadius);
				this.ctx.quadraticCurveTo(valueX + valueW, valueY - 10 + valueH, valueX + valueW - valueRadius, valueY - 10 + valueH);
				this.ctx.lineTo(valueX + valueRadius, valueY - 10 + valueH);
				this.ctx.quadraticCurveTo(valueX, valueY - 10 + valueH, valueX, valueY - 10 + valueH - valueRadius);
				this.ctx.lineTo(valueX, valueY - 10 + valueRadius);
				this.ctx.quadraticCurveTo(valueX, valueY - 10, valueX + valueRadius, valueY - 10);
				this.ctx.closePath();
				this.ctx.fill();
			}
			
			this.ctx.strokeStyle = isValueHovered ? colors.borderHighlight : colors.borderColor;
			this.ctx.lineWidth = (isValueHovered ? 2 : 1.5) / this.camera.scale;
			this.ctx.stroke();
			
			if (isValueHovered) {
				this.ctx.strokeStyle = 'rgba(70, 162, 218, 0.3)';
				this.ctx.lineWidth = 2.5 / this.camera.scale;
				this.ctx.stroke();
			} else {
				this.ctx.strokeStyle = 'rgba(255, 255, 255, 0.1)';
				this.ctx.lineWidth = 1 / this.camera.scale;
				this.ctx.stroke();
			}
			
			this.ctx.fillStyle = colors.textPrimary;
			this.ctx.font = (10 * textScale) + 'px ' + style.textFont;
			this.ctx.textAlign = 'center';
			this.ctx.textBaseline = 'middle';
			let displayValue = String(node.properties.value);
			if (displayValue.length > 20) displayValue = displayValue.substring(0, 20) + '...';
			this.ctx.fillText(displayValue, valueX + valueW / 2, valueY);
			
			if (isValueHovered) {
				this.canvas.style.cursor = 'text';
			}
		}
	}

	drawInputSlot(node, j, x, y, w, worldMouse, colors) {
		const style = this.drawingStyleManager.getStyle();
		const textScale = this.getTextScale();
		
		if (!node.inputs || !node.inputs[j]) {
				return;
		}
		
		const inp = node.inputs[j];
		const sy = y + 38 + j * 25;
		const hovered = this.connecting && !this.connecting.isOutput && 
			Math.abs(worldMouse[0] - x) < 10 && Math.abs(worldMouse[1] - sy) < 10;
		const compat = this.isSlotCompatible(node, j, false);
		
		const isMulti = node.multiInputs && node.multiInputs[j];
		const hasConnections = isMulti ? node.multiInputs[j].links.length > 0 : inp.link;
		
		let color;
		if (hovered && compat) color = colors.accentGreen;
		else if (hovered && !compat) color = colors.accentRed;
		else if (hasConnections) color = colors.slotConnected;
		else color = colors.slotInput;
		
		// Slot highlight when connecting
		if (this.connecting && compat) {
			this.ctx.fillStyle = color;
			this.ctx.globalAlpha = 0.3;
			this.ctx.beginPath();
			this.ctx.arc(x - 1, sy, 8, 0, Math.PI * 2);
			this.ctx.fill();
			this.ctx.globalAlpha = 1.0;
		}
		
		// Slot circle
		this.ctx.fillStyle = color;
		this.ctx.beginPath();
		this.ctx.arc(x - 1, sy, style.slotRadius || 4, 0, Math.PI * 2);
		this.ctx.fill();
		
		// Slot highlight dot
		this.ctx.fillStyle = 'rgba(255, 255, 255, 0.4)';
		this.ctx.beginPath();
		this.ctx.arc(x - 2, sy - 1, 1.5, 0, Math.PI * 2);
		this.ctx.fill();
		
		// Multi-input indicator
		if (isMulti) {
			this.ctx.strokeStyle = colors.accentPurple || '#9370db';
			this.ctx.lineWidth = 1.5 / this.camera.scale;
			this.ctx.beginPath();
			this.ctx.arc(x - 1, sy, 6, 0, Math.PI * 2);
			this.ctx.stroke();
			
			if (node.multiInputs[j].links.length > 0) {
				this.ctx.fillStyle = colors.accentPurple || '#9370db';
				this.ctx.font = 'bold ' + (8 * textScale) + 'px Arial, sans-serif';
				this.ctx.textAlign = 'left';
				this.ctx.fillText(node.multiInputs[j].links.length, x + 10, sy - 10);
			}
		}
		
		// Field name
		this.ctx.fillStyle = colors.textSecondary;
		this.ctx.font = (10 * textScale) + 'px Arial, sans-serif';
		this.ctx.textAlign = 'left';
		this.ctx.textBaseline = 'middle';
		this.ctx.fillText(inp.name, x + 10, sy);
		
		// Check if this slot has a native input edit box
		const hasEditBox = !isMulti && !inp.link && node.nativeInputs && node.nativeInputs[j] !== undefined;
		
		// Type label (only show if no edit box, or for non-native nodes)
		if (!hasEditBox && (!node.isNative || (!!node.nativeInputs && node.nativeInputs[j] === undefined))) {
			const compactType = this.graph.compactType(inp.type);
			let typeText = compactType.length > 20 ? compactType.substring(0, 20) + '...' : compactType;
			
			this.ctx.font = (8 * textScale) + 'px "Courier New", monospace';
			const textWidth = this.ctx.measureText(typeText).width;
			const typeBoxX = x + 10;
			const typeBoxY = sy + 6;
			const typeBoxW = textWidth + 8;
			const typeBoxH = 12;
			const typeBoxRadius = 2;
			
			this.ctx.fillStyle = 'rgba(0, 0, 0, 0.3)';
			this.ctx.beginPath();
			this.ctx.moveTo(typeBoxX + typeBoxRadius, typeBoxY);
			this.ctx.lineTo(typeBoxX + typeBoxW - typeBoxRadius, typeBoxY);
			this.ctx.quadraticCurveTo(typeBoxX + typeBoxW, typeBoxY, typeBoxX + typeBoxW, typeBoxY + typeBoxRadius);
			this.ctx.lineTo(typeBoxX + typeBoxW, typeBoxY + typeBoxH - typeBoxRadius);
			this.ctx.quadraticCurveTo(typeBoxX + typeBoxW, typeBoxY + typeBoxH, typeBoxX + typeBoxW - typeBoxRadius, typeBoxY + typeBoxH);
			this.ctx.lineTo(typeBoxX + typeBoxRadius, typeBoxY + typeBoxH);
			this.ctx.quadraticCurveTo(typeBoxX, typeBoxY + typeBoxH, typeBoxX, typeBoxY + typeBoxH - typeBoxRadius);
			this.ctx.lineTo(typeBoxX, typeBoxY + typeBoxRadius);
			this.ctx.quadraticCurveTo(typeBoxX, typeBoxY, typeBoxX + typeBoxRadius, typeBoxY);
			this.ctx.closePath();
			this.ctx.fill();
			
			this.ctx.strokeStyle = 'rgba(255, 255, 255, 0.1)';
			this.ctx.lineWidth = 0.5 / this.camera.scale;
			this.ctx.stroke();
			
			this.ctx.fillStyle = colors.textTertiary;
			this.ctx.textAlign = 'left';
			this.ctx.textBaseline = 'middle';
			this.ctx.fillText(typeText, typeBoxX + 4, typeBoxY + typeBoxH / 2);
		}
		
		// Native input edit box (on same row where type label would be)
		if (hasEditBox) {
			const boxX = x + 10;
			const boxY = sy + 6;
			const boxW = 70;
			const boxH = 12;
			const boxRadius = 2;
			const isOptional = node.nativeInputs[j].optional;
			
			const isBoxHovered = !this.connecting && 
				worldMouse[0] >= boxX && worldMouse[0] <= boxX + boxW &&
				worldMouse[1] >= boxY && worldMouse[1] <= boxY + boxH;
			
			this.ctx.fillStyle = isBoxHovered 
				? (isOptional ? 'rgba(0, 120, 180, 0.4)' : 'rgba(0, 0, 0, 0.6)')
				: (isOptional ? 'rgba(0, 100, 150, 0.3)' : 'rgba(0, 0, 0, 0.4)');
			this.ctx.beginPath();
			this.ctx.moveTo(boxX + boxRadius, boxY);
			this.ctx.lineTo(boxX + boxW - boxRadius, boxY);
			this.ctx.quadraticCurveTo(boxX + boxW, boxY, boxX + boxW, boxY + boxRadius);
			this.ctx.lineTo(boxX + boxW, boxY + boxH - boxRadius);
			this.ctx.quadraticCurveTo(boxX + boxW, boxY + boxH, boxX + boxW - boxRadius, boxY + boxH);
			this.ctx.lineTo(boxX + boxRadius, boxY + boxH);
			this.ctx.quadraticCurveTo(boxX, boxY + boxH, boxX, boxY + boxH - boxRadius);
			this.ctx.lineTo(boxX, boxY + boxRadius);
			this.ctx.quadraticCurveTo(boxX, boxY, boxX + boxRadius, boxY);
			this.ctx.closePath();
			this.ctx.fill();
			
			this.ctx.strokeStyle = isBoxHovered
				? (isOptional ? 'rgba(100, 180, 230, 0.8)' : colors.borderHighlight)
				: (isOptional ? 'rgba(70, 162, 218, 0.5)' : 'rgba(255, 255, 255, 0.15)');
			this.ctx.lineWidth = (isBoxHovered ? 1.5 : 1) / this.camera.scale;
			this.ctx.stroke();
			
			const displayVal = node.nativeInputs[j].value;
			const isEmpty = displayVal === '' || displayVal === null || displayVal === undefined;
			const textY = boxY + boxH / 2;
			
			this.ctx.textBaseline = 'middle';
			
			if (isEmpty) {
				this.ctx.fillStyle = colors.textTertiary;
				this.ctx.font = 'italic ' + (8 * textScale) + 'px Arial, sans-serif';
				this.ctx.textAlign = 'left';
				this.ctx.fillText(isOptional ? 'null' : 'empty', boxX + 4, textY);
			} else {
				this.ctx.fillStyle = colors.textPrimary;
				this.ctx.font = (8 * textScale) + 'px "Courier New", monospace';
				this.ctx.textAlign = 'left';
				let displayValue = String(displayVal);
				if (displayValue.length > 10) {
					displayValue = displayValue.substring(0, 10) + '..';
				}
				this.ctx.fillText(displayValue, boxX + 4, textY);
			}
			
			// Optional badge (small, top-right of edit box)
			if (isOptional) {
				const badgeX = boxX + boxW + 4;
				const badgeY = boxY + boxH / 2;
				
				this.ctx.fillStyle = 'rgba(70, 162, 218, 0.8)';
				this.ctx.font = 'bold ' + (7 * textScale) + 'px Arial, sans-serif';
				this.ctx.textAlign = 'left';
				this.ctx.textBaseline = 'middle';
				this.ctx.fillText('?', badgeX, badgeY);
			}
			
			if (isBoxHovered) {
				this.canvas.style.cursor = 'text';
			}
		}
	}

	drawOutputSlot(node, j, x, y, w, worldMouse, colors) {
		const style = this.drawingStyleManager.getStyle();
		const textScale = this.getTextScale();
		
		if (!node.outputs || !node.outputs[j]) {
				return;
		}
		
		const out = node.outputs[j];
		const sy = y + 38 + j * 25;
		const hovered = this.connecting && this.connecting.isOutput && 
			Math.abs(worldMouse[0] - (x + w)) < 10 && Math.abs(worldMouse[1] - sy) < 10;
		const compat = this.isSlotCompatible(node, j, true);
		
		const hasConnections = out.links.length > 0;
		
		let color;
		if (hovered && compat) color = colors.accentGreen;
		else if (hovered && !compat) color = colors.accentRed;
		else if (hasConnections) color = colors.slotConnected;
		else color = colors.slotOutput;
		
		if (this.connecting && compat) {
			this.ctx.fillStyle = color;
			this.ctx.globalAlpha = 0.3;
			this.ctx.beginPath();
			this.ctx.arc(x + w + 1, sy, 8, 0, Math.PI * 2);
			this.ctx.fill();
			this.ctx.globalAlpha = 1.0;
		}
		
		this.ctx.fillStyle = color;
		this.ctx.beginPath();
		this.ctx.arc(x + w + 1, sy, style.slotRadius || 4, 0, Math.PI * 2);
		this.ctx.fill();
		
		this.ctx.fillStyle = 'rgba(255, 255, 255, 0.4)';
		this.ctx.beginPath();
		this.ctx.arc(x + w, sy - 1, 1.5, 0, Math.PI * 2);
		this.ctx.fill();
		
		this.ctx.fillStyle = colors.textSecondary;
		this.ctx.font = (10 * textScale) + 'px Arial, sans-serif';
		this.ctx.textAlign = 'right';
		this.ctx.textBaseline = 'middle';
		this.ctx.fillText(out.name, x + w - 10, sy);
		
		if (!node.isNative) {
			const compactType = this.graph.compactType(out.type);
			let typeText = compactType.length > 20 ? compactType.substring(0, 20) + '...' : compactType;
			
			this.ctx.font = (8 * textScale) + 'px "Courier New", monospace';
			const textWidth = this.ctx.measureText(typeText).width;
			const typeBoxX = x + w - 10 - textWidth - 8;
			const typeBoxY = sy + 6;        // Changed from sy + 10 - 5
			const typeBoxW = textWidth + 8;
			const typeBoxH = 12;            // Changed from 10
			const typeBoxRadius = 2;
			
			this.ctx.fillStyle = 'rgba(0, 0, 0, 0.3)';
			this.ctx.beginPath();
			this.ctx.moveTo(typeBoxX + typeBoxRadius, typeBoxY);
			this.ctx.lineTo(typeBoxX + typeBoxW - typeBoxRadius, typeBoxY);
			this.ctx.quadraticCurveTo(typeBoxX + typeBoxW, typeBoxY, typeBoxX + typeBoxW, typeBoxY + typeBoxRadius);
			this.ctx.lineTo(typeBoxX + typeBoxW, typeBoxY + typeBoxH - typeBoxRadius);
			this.ctx.quadraticCurveTo(typeBoxX + typeBoxW, typeBoxY + typeBoxH, typeBoxX + typeBoxW - typeBoxRadius, typeBoxY + typeBoxH);
			this.ctx.lineTo(typeBoxX + typeBoxRadius, typeBoxY + typeBoxH);
			this.ctx.quadraticCurveTo(typeBoxX, typeBoxY + typeBoxH, typeBoxX, typeBoxY + typeBoxH - typeBoxRadius);
			this.ctx.lineTo(typeBoxX, typeBoxY + typeBoxRadius);
			this.ctx.quadraticCurveTo(typeBoxX, typeBoxY, typeBoxX + typeBoxRadius, typeBoxY);
			this.ctx.closePath();
			this.ctx.fill();
			
			this.ctx.strokeStyle = 'rgba(255, 255, 255, 0.1)';
			this.ctx.lineWidth = 0.5 / this.camera.scale;
			this.ctx.stroke();
			
			this.ctx.fillStyle = colors.textTertiary;
			this.ctx.textAlign = 'right';
			this.ctx.textBaseline = 'middle';  // Added for consistency
			this.ctx.fillText(typeText, x + w - 10 - 4, typeBoxY + typeBoxH / 2);  // Centered vertically
		}
	}

	drawConnecting(colors) {
		const node = this.connecting.node;
		const worldMouse = this.screenToWorld(this.mousePos[0], this.mousePos[1]);
		let x1, y1;
		
		if (this.connecting.isOutput) {
			x1 = node.pos[0] + node.size[0];
			y1 = node.pos[1] + 33 + this.connecting.slot * 25;
		} else {
			x1 = node.pos[0];
			y1 = node.pos[1] + 33 + this.connecting.slot * 25;
		}
		
		const distance = Math.abs(worldMouse[0] - x1);
		const maxControlDistance = 400;
		const controlOffset = Math.min(distance * 0.5, maxControlDistance);
		const cx1 = x1 + (this.connecting.isOutput ? controlOffset : -controlOffset);
		const cx2 = worldMouse[0] + (this.connecting.isOutput ? -controlOffset : controlOffset);
		
		this.ctx.strokeStyle = colors.accentGreen;
		this.ctx.lineWidth = 2.5 / this.camera.scale;
		this.ctx.globalAlpha = 1.0;
		this.ctx.setLineDash([10 / this.camera.scale, 5 / this.camera.scale]);
		this.ctx.beginPath();
		this.ctx.moveTo(x1, y1);
		this.ctx.bezierCurveTo(cx1, y1, cx2, worldMouse[1], worldMouse[0], worldMouse[1]);
		this.ctx.stroke();
		this.ctx.setLineDash([]);
		this.ctx.globalAlpha = 1.0;
	}

	adjustColorBrightness(color, amount) {
		const hex = color.replace('#', '');
		const num = parseInt(hex, 16);
		const r = Math.max(0, Math.min(255, (num >> 16) + amount));
		const g = Math.max(0, Math.min(255, ((num >> 8) & 0x00FF) + amount));
		const b = Math.max(0, Math.min(255, (num & 0x0000FF) + amount));
		return '#' + ((r << 16) | (g << 8) | b).toString(16).padStart(6, '0');
	}

	/**
	 * Create the SchemaGraph API object
	 * Called once during initialization
	 * @private
	 */
	_createAPI() {
		return {
			lock: {
				/**
				 * Lock the graph
				 * @param {string} reason - Lock reason
				 */
				lock: (reason, pending = true) => {
					this.lock(reason, pending);
				},
				
				/**
				 * Unlock the graph
				 */
				unlock: () => {
					this.unlock();
				},
				
				/**
				 * Check if locked
				 * @returns {boolean}
				 */
				isLocked: () => {
					return this.isLocked;
				},
				
				/**
				 * Get lock reason
				 * @returns {string|null}
				 */
				getReason: () => {
					return this.lockReason;
				}
			},

			schema: {
				/**
				 * Register a schema from code string
				 * @param {string} name - Schema name
				 * @param {string} code - Pydantic schema code
				 * @param {string} indexType - Index type (default: 'int')
				 * @param {string} rootType - Root config class name
				 * @returns {boolean} Success status
				 */
				register: (name, code, indexType = 'int', rootType = null) => {
					this.api.schema.remove(name);
					const success = this.graph.registerSchema(name, code, indexType, rootType);
					if (success) {
						this.updateSchemaList();
						this.updateNodeTypesList();
						this.draw();
					}
					return success;
				},

				/**
				 * Remove a registered schema
				 * @param {string} name - Schema name to remove
				 * @returns {boolean} Success status
				 */
				remove: (name) => {
					const success = this.graph.removeSchema(name);
					if (success) {
						this.updateSchemaList();
						this.updateNodeTypesList();
						this.draw();
					}
					return success;
				},

				/**
				 * Get list of registered schemas
				 * @returns {string[]} Array of schema names
				 */
				list: () => {
					return this.graph.getRegisteredSchemas();
				},

				/**
				 * Get detailed info about a schema
				 * @param {string} name - Schema name
				 * @returns {Object|null} Schema info or null if not found
				 */
				info: (name) => {
					return this.graph.getSchemaInfo(name);
				},

				/**
				 * Enable a schema (show in context menu)
				 * @param {string} name - Schema name
				 * @returns {boolean} Success status
				 */
				enable: (name) => {
					const success = this.graph.enableSchema(name);
					if (success) {
						this.updateSchemaList();
					}
					return success;
				},

				/**
				 * Disable a schema (hide from context menu)
				 * @param {string} name - Schema name
				 * @returns {boolean} Success status
				 */
				disable: (name) => {
					const success = this.graph.disableSchema(name);
					if (success) {
						this.updateSchemaList();
					}
					return success;
				},

				/**
				 * Toggle schema enabled/disabled state
				 * @param {string} name - Schema name
				 * @returns {boolean} New enabled state
				 */
				toggle: (name) => {
					this.graph.toggleSchema(name);
					this.updateSchemaList();
					return this.graph.isSchemaEnabled(name);
				},

				/**
				 * Check if schema is enabled
				 * @param {string} name - Schema name
				 * @returns {boolean} Enabled status
				 */
				isEnabled: (name) => {
					return this.graph.isSchemaEnabled(name);
				},

				/**
				 * Get list of enabled schemas
				 * @returns {string[]} Array of enabled schema names
				 */
				listEnabled: () => {
					return this.graph.getEnabledSchemas();
				}
			},

			node: {
				/**
				 * Create a new node
				 * @param {string} type - Node type (e.g., 'Native.String', 'Schema.ModelName')
				 * @param {number} x - X position in world coordinates
				 * @param {number} y - Y position in world coordinates
				 * @returns {Node|null} Created node or null on failure
				 */
				create: (type, x = 0, y = 0) => {
					try {
						const node = this.graph.createNode(type);
						node.pos = [x, y];
						this.draw();
						return node;
					} catch (e) {
						this.showError('Failed to create node: ' + e.message);
						return null;
					}
				},

				/**
				 * Delete a node by reference or ID
				 * @param {Node|string} nodeOrId - Node object or node ID
				 * @returns {boolean} Success status
				 */
				delete: (nodeOrId) => {
					const node = typeof nodeOrId === 'string' 
						? this.graph.getNodeById(nodeOrId) 
						: nodeOrId;
					
					if (!node) return false;
					
					this.removeNode(node);
					return true;
				},

				/**
				 * Select a node
				 * @param {Node|string} nodeOrId - Node object or node ID
				 * @param {boolean} addToSelection - Add to existing selection
				 * @returns {boolean} Success status
				 */
				select: (nodeOrId, addToSelection = false) => {
					const node = typeof nodeOrId === 'string' 
						? this.graph.getNodeById(nodeOrId) 
						: nodeOrId;
					
					if (!node) return false;
					
					this.selectNode(node, addToSelection);
					return true;
				},

				/**
				 * Get all nodes
				 * @returns {Node[]} Array of all nodes
				 */
				list: () => {
					return [...this.graph.nodes];
				},

				/**
				 * Get node by ID
				 * @param {string} id - Node ID
				 * @returns {Node|null} Node or null if not found
				 */
				getById: (id) => {
					return this.graph.getNodeById(id);
				},

				/**
				 * Get selected nodes
				 * @returns {Node[]} Array of selected nodes
				 */
				getSelected: () => {
					return Array.from(this.selectedNodes);
				},

				/**
				 * Clear selection
				 * @returns {void}
				 */
				clearSelection: () => {
					this.clearSelection();
				},

				/**
				 * Set node property value
				 * @param {Node|string} nodeOrId - Node object or node ID
				 * @param {string} property - Property name
				 * @param {any} value - Property value
				 * @returns {boolean} Success status
				 */
				setProperty: (nodeOrId, property, value) => {
					const node = typeof nodeOrId === 'string' 
						? this.graph.getNodeById(nodeOrId) 
						: nodeOrId;
					
					if (!node) return false;
					
					node.properties[property] = value;
					this.draw();
					return true;
				},

				/**
				 * Set native input value
				 * @param {Node|string} nodeOrId - Node object or node ID
				 * @param {number} slotIndex - Input slot index
				 * @param {any} value - Input value
				 * @returns {boolean} Success status
				 */
				setInputValue: (nodeOrId, slotIndex, value) => {
					const node = typeof nodeOrId === 'string' 
						? this.graph.getNodeById(nodeOrId) 
						: nodeOrId;
					
					if (!node || !node.nativeInputs || node.nativeInputs[slotIndex] === undefined) {
						return false;
					}
					
					node.nativeInputs[slotIndex].value = value;
					this.draw();
					return true;
				}
			},

			link: {
				/**
				 * Create a link between nodes
				 * @param {Node|string} sourceNodeOrId - Source node or ID
				 * @param {number} sourceSlot - Source output slot index
				 * @param {Node|string} targetNodeOrId - Target node or ID
				 * @param {number} targetSlot - Target input slot index
				 * @returns {Link|null} Created link or null on failure
				 */
				create: (sourceNodeOrId, sourceSlot, targetNodeOrId, targetSlot) => {
					const sourceNode = typeof sourceNodeOrId === 'string' 
						? this.graph.getNodeById(sourceNodeOrId) 
						: sourceNodeOrId;
					
					const targetNode = typeof targetNodeOrId === 'string' 
						? this.graph.getNodeById(targetNodeOrId) 
						: targetNodeOrId;
					
					if (!sourceNode || !targetNode) return null;
					
					const link = this.graph.connect(sourceNode, sourceSlot, targetNode, targetSlot);
					if (link) {
						this.eventBus.emit('link:created', { linkId: link.id });
						this.draw();
					}
					return link;
				},

				/**
				 * Delete a link by ID
				 * @param {number} linkId - Link ID
				 * @returns {boolean} Success status
				 */
				delete: (linkId) => {
					return this.disconnectLink(linkId);
				},

				/**
				 * Clear all multi-input links from a node's slot
				 * @param {Node|string} nodeOrId - Node object or ID
				 * @param {number} slotIndex - Input slot index
				 * @returns {boolean} Success status
				 */
				clearMultiInput: (nodeOrId, slotIndex) => {
					const node = typeof nodeOrId === 'string' 
						? this.graph.getNodeById(nodeOrId) 
						: nodeOrId;
					
					if (!node) return false;
					
					return this.clearMultiInputLinks(node, slotIndex);
				},

				/**
				 * Clear all multi-input links from a node
				 * @param {Node|string} nodeOrId - Node object or ID
				 * @returns {boolean} Success status
				 */
				clearAllMultiInputs: (nodeOrId) => {
					const node = typeof nodeOrId === 'string' 
						? this.graph.getNodeById(nodeOrId) 
						: nodeOrId;
					
					if (!node) return false;
					
					return this.clearAllMultiInputLinks(node);
				},

				/**
				 * Get all links
				 * @returns {Object} Links object keyed by link ID
				 */
				list: () => {
					return { ...this.graph.links };
				}
			},

			graph: {
				/**
				 * Export graph to JSON
				 * @param {boolean} includeCamera - Include camera position/zoom
				 * @returns {Object} Graph data
				 */
				export: (includeCamera = true) => {
					return this.graph.serialize(includeCamera, this.camera);
				},

				/**
				 * Import graph from JSON
				 * @param {Object} data - Graph data
				 * @param {boolean} restoreCamera - Restore camera position/zoom
				 * @returns {boolean} Success status
				 */
				import: (data, restoreCamera = true) => {
					try {
						this.graph.deserialize(data, restoreCamera, this.camera);
						this.updateSchemaList();
						this.updateNodeTypesList();
						if (restoreCamera) {
							this.eventBus.emit('ui:update', { 
								id: 'zoomLevel', 
								content: Math.round(this.camera.scale * 100) + '%' 
							});
						}
						this.draw();
						this.eventBus.emit('graph:imported', {});
						return true;
					} catch (e) {
						this.showError('Import failed: ' + e.message);
						return false;
					}
				},

				/**
				 * Download graph as JSON file
				 * @param {string} filename - Optional filename
				 * @returns {void}
				 */
				download: (filename = null) => {
					const data = this.graph.serialize(true, this.camera);
					const jsonString = JSON.stringify(data, null, 2);
					const blob = new Blob([jsonString], { type: 'application/json' });
					const url = URL.createObjectURL(blob);
					const a = document.createElement('a');
					a.href = url;
					a.download = filename || ('schemagraph-' + new Date().toISOString().slice(0, 10) + '.json');
					document.body.appendChild(a);
					a.click();
					document.body.removeChild(a);
					URL.revokeObjectURL(url);
					this.eventBus.emit('graph:exported', {});
				},

				/**
				 * Clear entire graph
				 * @returns {void}
				 */
				clear: () => {
					this.graph.nodes = [];
					this.graph.links = {};
					this.graph._nodes_by_id = {};
					this.graph.last_link_id = 0;
					this.clearSelection();
					this.draw();
				}
			},

			config: {
				/**
				 * Build config from current graph
				 * @param {string} schemaName - Schema to use for config
				 * @returns {Object} Config data
				 */
				build: (schemaName = null) => {
					const schemas = Object.keys(this.graph.schemas);
					if (schemas.length === 0) {
						throw new Error('No schemas registered');
					}

					let targetSchema = schemaName;
					if (!targetSchema) {
						for (const name of schemas) {
							const info = this.graph.schemas[name];
							if (info && info.rootType) {
								targetSchema = name;
								break;
							}
						}
					}

					if (!targetSchema) targetSchema = schemas[0];

					return this.buildConfig(targetSchema);
				},

				/**
				 * Export config from current graph - alias for build()
				 * @param {string} schemaName - Schema to use for config
				 * @returns {Object} Config data
				 */
				export: (schemaName = null) => {
					return this.api.config.build(schemaName);
				},

				/**
				 * Import config into graph
				 * @param {Object} configData - Config data
				 * @param {string} schemaName - Optional schema name
				 * @returns {boolean} Success status
				 */
				import: (configData, schemaName = null) => {
					try {
						this.importConfigData(configData, schemaName);
						this.eventBus.emit('config:imported', {});
						return true;
					} catch (e) {
						this.showError('Config import failed: ' + e.message);
						return false;
					}
				},

				/**
				 * Download config as JSON file
				 * @param {string} filename - Optional filename
				 * @returns {void}
				 */
				download: (filename = null) => {
					const schemas = Object.keys(this.graph.schemas);
					if (schemas.length === 0) {
						this.showError('No schemas registered');
						return;
					}

					let targetSchema = null;
					for (const schemaName of schemas) {
						const info = this.graph.schemas[schemaName];
						if (info && info.rootType) {
							targetSchema = schemaName;
							break;
						}
					}

					if (!targetSchema) targetSchema = schemas[0];

					const config = this.buildConfig(targetSchema);
					const jsonString = JSON.stringify(config, null, 2);
					const blob = new Blob([jsonString], { type: 'application/json' });
					const url = URL.createObjectURL(blob);
					const a = document.createElement('a');
					a.href = url;
					a.download = filename || ('config-' + new Date().toISOString().slice(0, 10) + '.json');
					document.body.appendChild(a);
					a.click();
					document.body.removeChild(a);
					URL.revokeObjectURL(url);
					this.eventBus.emit('config:exported', {});
				},

				/**
				 * Visualize config structure (for debugging)
				 * Shows which fields use index references vs. embedded objects
				 * @param {string} schemaName - Optional schema name
				 * @returns {void}
				 */
				visualize: (schemaName = null) => {
					const schemas = Object.keys(this.graph.schemas);
					if (schemas.length === 0) {
						console.error('No schemas registered');
						return;
					}

					let targetSchema = schemaName;
					if (!targetSchema) {
						for (const name of schemas) {
							const info = this.graph.schemas[name];
							if (info && info.rootType) {
								targetSchema = name;
								break;
							}
						}
					}

					if (!targetSchema) targetSchema = schemas[0];

					console.log('%c📋 Config Structure Visualization', 'color: #46a2da; font-weight: bold; font-size: 14px;');
					console.log(`Schema: ${targetSchema}\n`);

					const config = this.buildConfig(targetSchema);
					
					console.log('%cRoot-level collections (shared resources):', 'color: #92d050; font-weight: bold;');
					for (const key in config) {
						if (Array.isArray(config[key])) {
							console.log(`	${key}: [${config[key].length} items]`);
						}
					}

					console.log('\n%cIndex references found:', 'color: #9370db; font-weight: bold;');
					let referenceCount = 0;
					
					const findReferences = (obj, path = '') => {
						if (typeof obj === 'number' && Number.isInteger(obj) && obj >= 0) {
							referenceCount++;
							console.log(`	${path} = ${obj} (index reference)`);
							return;
						}
						
						if (Array.isArray(obj)) {
							obj.forEach((item, idx) => {
								if (typeof item === 'number' && Number.isInteger(item) && item >= 0) {
									referenceCount++;
									console.log(`	${path}[${idx}] = ${item} (index reference)`);
								} else if (typeof item === 'object' && item !== null) {
									findReferences(item, `${path}[${idx}]`);
								}
							});
						} else if (typeof obj === 'object' && obj !== null) {
							for (const key in obj) {
								if (obj.hasOwnProperty(key)) {
									findReferences(obj[key], path ? `${path}.${key}` : key);
								}
							}
						}
					};

					findReferences(config);
					
					if (referenceCount === 0) {
						console.log('	(none found - all objects are embedded)');
					}

					console.log('\n%cFull config structure:', 'color: #46a2da;');
					console.log(config);
					
					console.log('\n💡 How index references work:');
					console.log('	- Root collections contain the full objects');
					console.log('	- Child objects reference shared resources by index');
					console.log('	- Example: agent.backend = 0 refers to backends[0]');
				}
			},

			view: {
				/**
				 * Center view on all nodes
				 * @returns {void}
				 */
				center: () => {
					this.centerView();
				},

				/**
				 * Reset zoom to 100%
				 * @returns {void}
				 */
				resetZoom: () => {
					this.resetZoom();
				},

				/**
				 * Reset position and zoom
				 * @returns {void}
				 */
				reset: () => {
					this.api.view.setPosition(0, 0);
					this.resetZoom();
				},

				/**
				 * Set zoom level
				 * @param {number} scale - Zoom scale (0.1 to 5.0)
				 * @returns {void}
				 */
				setZoom: (scale) => {
					this.camera.scale = Math.max(0.1, Math.min(5, scale));
					this.eventBus.emit('ui:update', { 
						id: 'zoomLevel', 
						content: Math.round(this.camera.scale * 100) + '%' 
					});
					this.draw();
				},

				/**
				 * Get current zoom level
				 * @returns {number} Current zoom scale
				 */
				getZoom: () => {
					return this.camera.scale;
				},

				/**
				 * Set camera position
				 * @param {number} x - X position
				 * @param {number} y - Y position
				 * @returns {void}
				 */
				setPosition: (x, y) => {
					this.camera.x = x;
					this.camera.y = y;
					this.draw();
				},

				/**
				 * Get camera position
				 * @returns {Object} Camera {x, y, scale}
				 */
				getPosition: () => {
					return { ...this.camera };
				},

				/**
				 * Pan camera by offset
				 * @param {number} dx - X offset
				 * @param {number} dy - Y offset
				 * @returns {void}
				 */
				pan: (dx, dy) => {
					this.camera.x += dx;
					this.camera.y += dy;
					this.draw();
				},

				/**
				 * Export current view (camera position and zoom)
				 * @returns {Object} View data {x, y, scale}
				 */
				export: () => {
					const viewData = {
						x: this.camera.x,
						y: this.camera.y,
						scale: this.camera.scale
					};
					this.eventBus.emit('view:exported', viewData);
					return viewData;
				},

				/**
				 * Import view (camera position and zoom)
				 * @param {Object} viewData - View data {x, y, scale}
				 * @returns {boolean} Success status
				 */
				import: (viewData) => {
					if (!viewData || typeof viewData !== 'object') {
						return false;
					}
					
					if (typeof viewData.x === 'number') this.camera.x = viewData.x;
					if (typeof viewData.y === 'number') this.camera.y = viewData.y;
					if (typeof viewData.scale === 'number') {
						this.camera.scale = Math.max(0.1, Math.min(5, viewData.scale));
					}
					
					this.eventBus.emit('ui:update', { 
						id: 'zoomLevel', 
						content: Math.round(this.camera.scale * 100) + '%' 
					});
					this.draw();
					this.eventBus.emit('view:imported', viewData);
					return true;
				},

				/**
				 * Download view as JSON file
				 * @param {string} filename - Optional filename
				 * @returns {void}
				 */
				download: (filename = null) => {
					const viewData = this.api.view.export();
					const jsonString = JSON.stringify(viewData, null, 2);
					const blob = new Blob([jsonString], { type: 'application/json' });
					const url = URL.createObjectURL(blob);
					const a = document.createElement('a');
					a.href = url;
					a.download = filename || ('view-' + new Date().toISOString().slice(0, 10) + '.json');
					document.body.appendChild(a);
					a.click();
					document.body.removeChild(a);
					URL.revokeObjectURL(url);
					this.eventBus.emit('interaction', { type: 'view:downloaded' });
				},

				/**
				 * Copy view to clipboard
				 * @returns {Promise<boolean>} Success status
				 */
				copyToClipboard: async () => {
					try {
						const viewData = this.api.view.export();
						await navigator.clipboard.writeText(JSON.stringify(viewData, null, 2));
						this.eventBus.emit('ui:update', { 
							id: 'status', 
							content: 'View copied to clipboard!' 
						});
						setTimeout(() => {
							this.eventBus.emit('ui:update', { id: 'status', content: 'Right-click to add nodes.' });
						}, 2000);
						return true;
					} catch (e) {
						this.showError('Failed to copy view to clipboard');
						return false;
					}
				}
			},

			layout: {
				/**
				 * Apply a layout algorithm
				 * @param {string} type - Layout type ('hierarchical-vertical', 'hierarchical-horizontal', 'force-directed', 'grid', 'circular')
				 * @returns {boolean} Success status
				 */
				apply: (type) => {
					if (this.graph.nodes.length === 0) {
						return false;
					}
					this.applyLayout(type);
					return true;
				},

				/**
				 * Available layout types
				 * @returns {string[]} Array of layout type names
				 */
				types: () => {
					return [
						'hierarchical-vertical',
						'hierarchical-horizontal',
						'force-directed',
						'grid',
						'circular'
					];
				}
			},

			theme: {
				/**
				 * Set theme
				 * @param {string} theme - Theme name ('dark', 'light', 'ocean')
				 * @returns {boolean} Success status
				 */
				set: (theme) => {
					if (!this.themes.includes(theme)) return false;
					this.applyTheme(theme);
					localStorage.setItem('schemagraph-theme', theme);
					this.draw();
					return true;
				},

				/**
				 * Get current theme
				 * @returns {string} Current theme name
				 */
				get: () => {
					return this.themes[this.currentThemeIndex];
				},

				/**
				 * Cycle to next theme
				 * @returns {string} New theme name
				 */
				cycle: () => {
					this.cycleTheme();
					return this.themes[this.currentThemeIndex];
				},

				/**
				 * Available themes
				 * @returns {string[]} Array of theme names
				 */
				list: () => {
					return [...this.themes];
				}
			},

			style: {
				/**
				 * Set drawing style
				 * @param {string} styleName - Style name
				 * @returns {boolean} Success status
				 */
				set: (styleName) => {
					if (this.drawingStyleManager.setStyle(styleName)) {
						this.draw();
						return true;
					}
					return false;
				},

				/**
				 * Get current style name
				 * @returns {string} Current style name
				 */
				get: () => {
					return this.drawingStyleManager.getCurrentStyleName();
				},

				/**
				 * Get current style properties
				 * @returns {Object} Style properties
				 */
				getProperties: () => {
					return this.drawingStyleManager.getStyle();
				},

				/**
				 * Available styles
				 * @returns {string[]} Array of style names
				 */
				list: () => {
					return Object.keys(this.drawingStyleManager.styles);
				}
			},

			textScaling: {
				/**
				 * Set text scaling mode
				 * @param {string} mode - Mode ('fixed' or 'scaled')
				 * @returns {boolean} Success status
				 */
				set: (mode) => {
					if (mode !== 'fixed' && mode !== 'scaled') return false;
					this.textScalingMode = mode;
					this.saveTextScalingMode();
					this.updateTextScalingUI();
					this.draw();
					return true;
				},
			
				/**
				 * Get current text scaling mode
				 * @returns {string} Current mode
				 */
				get: () => {
					return this.textScalingMode;
				},
			
				/**
				 * Toggle text scaling mode
				 * @returns {string} New mode
				 */
				toggle: () => {
					this.textScalingMode = this.textScalingMode === 'fixed' ? 'scaled' : 'fixed';
					this.saveTextScalingMode();
					this.updateTextScalingUI();
					this.draw();
					return this.textScalingMode;
				}
			},

			voice: {
				/**
				 * Start voice recognition
				 * @returns {boolean} Success status
				 */
				start: () => {
					if (!this.voiceController.recognition) return false;
					this.voiceController.startListening();
					return true;
				},

				/**
				 * Stop voice recognition
				 * @returns {void}
				 */
				stop: () => {
					this.voiceController.stopListening();
				},

				/**
				 * Check if voice is listening
				 * @returns {boolean} Listening status
				 */
				isListening: () => {
					return this.voiceController.isListening;
				},

				/**
				 * Check if voice is available
				 * @returns {boolean} Availability status
				 */
				isAvailable: () => {
					return this.voiceController.recognition !== null;
				}
			},

			analytics: {
				/**
				 * Get current metrics
				 * @returns {Object} Metrics object
				 */
				getMetrics: () => {
					return this.analytics.getMetrics();
				},

				/**
				 * Get session metrics
				 * @returns {Object} Session metrics
				 */
				getSession: () => {
					return this.analytics.getSessionMetrics();
				},

				/**
				 * End current session and start new one
				 * @returns {void}
				 */
				endSession: () => {
					this.analytics.endSession();
				},

				/**
				 * Download analytics as JSON file
				 * @param {string} filename - Optional filename
				 * @returns {void}
				 */
				download: (filename = null) => {
					const metrics = this.analytics.getSessionMetrics();
					const jsonString = JSON.stringify(metrics, null, 2);
					const blob = new Blob([jsonString], { type: 'application/json' });
					const url = URL.createObjectURL(blob);
					const a = document.createElement('a');
					a.href = url;
					a.download = filename || ('analytics-' + new Date().toISOString().slice(0, 10) + '.json');
					document.body.appendChild(a);
					a.click();
					document.body.removeChild(a);
					URL.revokeObjectURL(url);
				}
			},

			util: {
				/**
				 * Convert screen coordinates to world coordinates
				 * @param {number} sx - Screen X
				 * @param {number} sy - Screen Y
				 * @returns {Array} [worldX, worldY]
				 */
				screenToWorld: (sx, sy) => {
					return this.screenToWorld(sx, sy);
				},

				/**
				 * Convert world coordinates to screen coordinates
				 * @param {number} wx - World X
				 * @param {number} wy - World Y
				 * @returns {Array} [screenX, screenY]
				 */
				worldToScreen: (wx, wy) => {
					return this.worldToScreen(wx, wy);
				},

				/**
				 * Redraw the canvas
				 * @returns {void}
				 */
				redraw: () => {
					this.draw();
				},

				/**
				 * Show error message
				 * @param {string} message - Error message
				 * @returns {void}
				 */
				showError: (message) => {
					this.showError(message);
				},

				/**
				 * Get event bus for custom event handling
				 * @returns {EventBus} Event bus instance
				 */
				getEventBus: () => {
					return this.eventBus;
				},

				/**
				 * Set custom context menu handler
				 * @param {Function} handler - Handler function (clickedNode, wx, wy, coords) => boolean
				 * @returns {void}
				 */
				setContextMenuHandler: (handler) => {
					this.customContextMenuHandler = handler;
				},
				
				/**
				 * Clear custom context menu handler
				 * @returns {void}
				 */
				clearContextMenuHandler: () => {
					this.customContextMenuHandler = null;
				}
			},

			help: {
				/**
				 * Print help for all modules or a specific module
				 * @param {string} module - Optional module name
				 * @returns {void}
				 */
				print: (module = null) => {
					if (module) {
						if (!this.api[module]) {
							console.error(`Module "${module}" not found. Available modules:`, Object.keys(this.api));
							return;
						}
						
						console.log(`%c📘 ${module.toUpperCase()} API`, 'color: #46a2da; font-weight: bold; font-size: 14px;');
						console.log(`\nMethods: ${Object.keys(this.api[module]).join(', ')}`);
						console.log('\nExamples:');
						
						const examples = {
							schema: [
								'gApp.api.schema.register("MySchema", schemaCode, "int", "AppConfig")',
								'gApp.api.schema.list()',
								'gApp.api.schema.info("MySchema")',
								'gApp.api.schema.remove("MySchema")'
							],
							node: [
								'const node = gApp.api.node.create("Native.String", 100, 100)',
								'gApp.api.node.setProperty(node, "value", "Hello")',
								'gApp.api.node.select(node)',
								'gApp.api.node.list()',
								'gApp.api.node.delete(node)'
							],
							link: [
								'const link = gApp.api.link.create(sourceNode, 0, targetNode, 0)',
								'gApp.api.link.delete(linkId)',
								'gApp.api.link.clearMultiInput(node, 0)',
								'gApp.api.link.list()'
							],
							graph: [
								'const data = gApp.api.graph.export()',
								'gApp.api.graph.import(data)',
								'gApp.api.graph.download("my-graph.json")',
								'gApp.api.graph.clear()'
							],
							config: [
								'const config = gApp.api.config.build("MySchema")',
								'gApp.api.config.visualize() // Show structure with index references',
								'gApp.api.config.import(configData)',
								'gApp.api.config.download("my-config.json")',
								'// Config export uses index references:',
								'// - Root node contains full lists (agents, models, etc.)',
								'// - Child nodes reference shared resources by index',
								'// - Example: agent.backend = 0 (refers to backends[0])'
							],
							view: [
								'gApp.api.view.center()',
								'gApp.api.view.setZoom(1.5)',
								'gApp.api.view.resetZoom()',
								'gApp.api.view.pan(50, 50)',
								'const viewData = gApp.api.view.export()',
								'gApp.api.view.import(viewData)',
								'gApp.api.view.download("my-view.json")',
								'gApp.api.view.copyToClipboard()'
							],
							layout: [
								'gApp.api.layout.apply("hierarchical-vertical")',
								'gApp.api.layout.apply("force-directed")',
								'gApp.api.layout.types()'
							],
							theme: [
								'gApp.api.theme.set("ocean")',
								'gApp.api.theme.cycle()',
								'gApp.api.theme.list()'
							],
							style: [
								'gApp.api.style.set("neon")',
								'gApp.api.style.get()',
								'gApp.api.style.list()'
							],
							textScaling: [
								'gApp.api.textScaling.set("fixed")',
								'gApp.api.textScaling.toggle()'
							],
							voice: [
								'gApp.api.voice.start()',
								'gApp.api.voice.stop()',
								'gApp.api.voice.isListening()'
							],
							analytics: [
								'gApp.api.analytics.getMetrics()',
								'gApp.api.analytics.getSession()',
								'gApp.api.analytics.download()'
							],
							util: [
								'const [wx, wy] = gApp.api.util.screenToWorld(100, 100)',
								'gApp.api.util.redraw()',
								'const eventBus = gApp.api.util.getEventBus()'
							]
						};
						
						if (examples[module]) {
							examples[module].forEach(ex => console.log(`	${ex}`));
						}
					} else {
						console.log('%c📚 SchemaGraph API Reference', 'color: #46a2da; font-weight: bold; font-size: 16px;');
						console.log('\nAvailable modules:');
						Object.keys(this.api).forEach(mod => {
							if (mod !== 'help') {
								const methods = Object.keys(this.api[mod]);
								console.log(`\n	%c${mod}%c - ${methods.length} methods`, 'color: #92d050; font-weight: bold;', 'color: inherit;');
								console.log(`		${methods.join(', ')}`);
							}
						});
						console.log('\n💡 Usage:');
						console.log('	gApp.api.help.print("schema") - Get help for specific module');
						console.log('	gApp.api.help.example() - Run a complete example');
						console.log('\n📖 Quick start:');
						console.log('	1. Upload a schema: gApp.api.schema.register(name, code)');
						console.log('	2. Create nodes: gApp.api.node.create(type, x, y)');
						console.log('	3. Connect nodes: gApp.api.link.create(source, 0, target, 0)');
						console.log('	4. Export: gApp.api.config.download()');
					}
				},

				/**
				 * Run a complete example demonstrating the API
				 * @returns {void}
				 */
				example: () => {
					console.log('%c🎯 Running API Example...', 'color: #46a2da; font-weight: bold; font-size: 14px;');
					
					try {
						console.log('\n1. Creating nodes...');
						const str1 = this.api.node.create('Native.String', 100, 100);
						const str2 = this.api.node.create('Native.String', 100, 200);
						const int1 = this.api.node.create('Native.Integer', 400, 150);
						console.log('	✓ Created 3 nodes');
						
						console.log('\n2. Setting node values...');
						this.api.node.setProperty(str1, 'value', 'Hello');
						this.api.node.setProperty(str2, 'value', 'World');
						this.api.node.setProperty(int1, 'value', 42);
						console.log('	✓ Values set');
						
						console.log('\n3. Selecting nodes...');
						this.api.node.select(str1);
						this.api.node.select(str2, true);
						console.log('	✓ Selected 2 nodes');
						
						console.log('\n4. Applying layout...');
						this.api.layout.apply('grid');
						console.log('	✓ Grid layout applied');
						
						console.log('\n5. Centering view...');
						this.api.view.center();
						console.log('	✓ View centered');
						
						console.log('\n6. Getting analytics...');
						const metrics = this.api.analytics.getMetrics();
						console.log('	✓ Metrics:', metrics);
						
						console.log('\n%c✨ Example complete! Check the canvas.', 'color: #92d050; font-weight: bold;');
						console.log('\n💡 Try: gApp.api.node.list() to see all nodes');
					} catch (e) {
						console.error('Example failed:', e);
					}
				},

				/**
				 * List all available methods across all modules
				 * @returns {Object} Object with module names as keys and method arrays as values
				 */
				list: () => {
					const allMethods = {};
					Object.keys(this.api).forEach(module => {
						if (module !== 'help') {
							allMethods[module] = Object.keys(this.api[module]);
						}
					});
					return allMethods;
				}
			},
		};
	}

	/**
	 * Create the UI management object
	 * Connects HTML elements to API methods
	 * Called once during initialization
	 * @private
	 */
	_createUI() {
		return {
			buttons: {
				/**
				 * Setup upload schema button
				 * @returns {void}
				 */
				setupUploadSchema: () => {
					const btn = document.getElementById('sg-uploadSchemaBtn');
					const fileInput = document.getElementById('sg-uploadSchemaFile');
					
					btn?.addEventListener('click', () => {
						fileInput?.click();
					});
					
					fileInput?.addEventListener('change', (e) => {
						const file = e.target.files[0];
						if (!file) return;
						
						const reader = new FileReader();
						reader.onload = (event) => {
							this.pendingSchemaCode = event.target.result;
							
							const fileName = file.name.replace(/\.py$/, '');
							const suggestedName = fileName.charAt(0).toUpperCase() + fileName.slice(1);
							
							const rootTypeRegex = /class\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(/g;
							let lastMatch = null;
							let match;
							while ((match = rootTypeRegex.exec(this.pendingSchemaCode)) !== null) {
								lastMatch = match;
							}
							const suggestedRootType = lastMatch ? lastMatch[1] : '';
							
							document.getElementById('sg-schemaNameInput').value = suggestedName;
							document.getElementById('sg-schemaIndexTypeInput').value = 'Index';
							document.getElementById('sg-schemaRootTypeInput').value = suggestedRootType;
							
							this.ui.dialogs.showSchemaDialog();
						};
						reader.readAsText(file);
						e.target.value = '';
					});
				},
	
				/**
				 * Setup export graph button
				 * @returns {void}
				 */
				setupExportGraph: () => {
					const btn = document.getElementById('sg-exportBtn');
					btn?.addEventListener('click', () => {
						this.api.graph.download();
					});
				},
	
				/**
				 * Setup import graph button
				 * @returns {void}
				 */
				setupImportGraph: () => {
					const btn = document.getElementById('sg-importBtn');
					const fileInput = document.getElementById('sg-importFile');
					
					btn?.addEventListener('click', () => {
						fileInput?.click();
					});
					
					fileInput?.addEventListener('change', (e) => {
						const file = e.target.files[0];
						if (!file) return;
						
						const reader = new FileReader();
						reader.onload = (event) => {
							try {
								const data = JSON.parse(event.target.result);
								this.api.graph.import(data, true);
								this.ui.messages.showSuccess('Graph imported successfully!');
							} catch (err) {
								this.ui.messages.showError('Import failed: ' + err.message);
							}
						};
						reader.readAsText(file);
						e.target.value = '';
					});
				},
	
				/**
				 * Setup export config button
				 * @returns {void}
				 */
				setupExportConfig: () => {
					const btn = document.getElementById('sg-exportConfigBtn');
					btn?.addEventListener('click', () => {
						this.api.config.download();
					});
				},
	
				/**
				 * Setup import config button
				 * @returns {void}
				 */
				setupImportConfig: () => {
					const btn = document.getElementById('sg-importConfigBtn');
					const fileInput = document.getElementById('sg-importConfigFile');
					
					btn?.addEventListener('click', () => {
						fileInput?.click();
					});
					
					fileInput?.addEventListener('change', (e) => {
						const file = e.target.files[0];
						if (!file) return;
						
						const reader = new FileReader();
						reader.onload = (event) => {
							try {
								const data = JSON.parse(event.target.result);
								this.api.config.import(data);
								this.ui.messages.showSuccess('Config imported successfully!');
							} catch (err) {
								this.ui.messages.showError('Config import failed: ' + err.message);
							}
						};
						reader.readAsText(file);
						e.target.value = '';
					});
				},
	
				/**
				 * Setup center view button
				 * @returns {void}
				 */
				setupCenterView: () => {
					const btn = document.getElementById('sg-centerViewBtn');
					btn?.addEventListener('click', () => {
						this.api.view.center();
						this.ui.messages.showSuccess('View centered', 1500);
					});
				},
	
				/**
				 * Setup reset zoom button
				 * @returns {void}
				 */
				setupResetZoom: () => {
					const btn = document.getElementById('sg-resetZoomBtn');
					btn?.addEventListener('click', () => {
						this.api.view.resetZoom();
						this.ui.messages.showSuccess('Zoom reset to 100%', 1500);
					});
				},
	
				/**
				 * Setup theme button
				 * @returns {void}
				 */
				setupTheme: () => {
					const btn = document.getElementById('sg-themeBtn');
					btn?.addEventListener('click', () => {
						const newTheme = this.api.theme.cycle();
						this.ui.messages.showSuccess(`Theme: ${newTheme}`, 1500);
					});
				},
	
				/**
				 * Setup layout selector
				 * @returns {void}
				 */
				setupLayout: () => {
					const select = document.getElementById('sg-layoutSelect');
					select?.addEventListener('change', (e) => {
						const value = e.target.value;
						if (value) {
							this.api.layout.apply(value);
							this.ui.messages.showSuccess(`Applied ${value} layout`, 1500);
							e.target.value = '';
						}
					});
				},
	
				/**
				 * Setup drawing style selector
				 * @returns {void}
				 */
				setupDrawingStyle: () => {
					const select = document.getElementById('sg-drawingStyleSelect');
					if (!select) return;
					
					select.value = this.api.style.get();
					
					select.addEventListener('change', (e) => {
						const styleName = e.target.value;
						if (this.api.style.set(styleName)) {
							this.ui.messages.showSuccess(`Style: ${styleName}`, 1500);
						}
					});
				},
	
				/**
				 * Setup text scaling toggle
				 * @returns {void}
				 */
				setupTextScaling: () => {
					const btn = document.getElementById('sg-textScalingToggle');
					btn?.addEventListener('click', () => {
						const newMode = this.api.textScaling.toggle();
						this.ui.update.textScaling();
						const modeText = newMode === 'fixed' ? 'Fixed Size' : 'Scaled with Zoom';
						this.ui.messages.showSuccess(`Text: ${modeText}`, 1500);
						this.draw();
					});
				},
	
				/**
				 * Setup all buttons
				 * @returns {void}
				 */
				setupAll: () => {
					this.ui.buttons.setupUploadSchema();
					this.ui.buttons.setupExportGraph();
					this.ui.buttons.setupImportGraph();
					this.ui.buttons.setupExportConfig();
					this.ui.buttons.setupImportConfig();
					this.ui.buttons.setupCenterView();
					this.ui.buttons.setupResetZoom();
					this.ui.buttons.setupTheme();
					this.ui.buttons.setupLayout();
					this.ui.buttons.setupDrawingStyle();
					this.ui.buttons.setupTextScaling();
				}
			},
	
			dialogs: {
				/**
				 * Show schema registration dialog
				 * @returns {void}
				 */
				showSchemaDialog: () => {
					const dialog = document.getElementById('sg-schemaDialog');
					dialog?.classList.add('show');
					document.getElementById('sg-schemaNameInput')?.focus();
				},
	
				/**
				 * Hide schema registration dialog
				 * @returns {void}
				 */
				hideSchemaDialog: () => {
					const dialog = document.getElementById('sg-schemaDialog');
					dialog?.classList.remove('show');
					this.pendingSchemaCode = null;
				},
	
				/**
				 * Setup schema registration dialog handlers
				 * @returns {void}
				 */
				setupSchemaDialog: () => {
					const confirmBtn = document.getElementById('sg-schemaDialogConfirm');
					const cancelBtn = document.getElementById('sg-schemaDialogCancel');
					
					confirmBtn?.addEventListener('click', () => {
						if (!this.pendingSchemaCode) return;
						
						const name = document.getElementById('sg-schemaNameInput').value.trim();
						const indexType = document.getElementById('sg-schemaIndexTypeInput').value.trim() || 'int';
						const rootType = document.getElementById('sg-schemaRootTypeInput').value.trim() || null;
						
						if (!name) {
							this.ui.messages.showError('Schema name is required');
							return;
						}
						
						if (this.api.schema.register(name, this.pendingSchemaCode, indexType, rootType)) {
							this.ui.dialogs.hideSchemaDialog();
							this.ui.messages.showSuccess(`Schema "${name}" registered!`, 3000);
						} else {
							this.ui.messages.showError('Failed to register schema. Check console.');
						}
					});
					
					cancelBtn?.addEventListener('click', () => {
						this.ui.dialogs.hideSchemaDialog();
					});
				},
	
				/**
				 * Show schema removal dialog
				 * @returns {void}
				 */
				showSchemaRemovalDialog: () => {
					const schemas = this.api.schema.list();
					if (schemas.length === 0) {
						this.ui.messages.showError('No schemas to remove');
						return;
					}
					
					const select = document.getElementById('sg-schemaRemovalNameInput');
					if (!select) return;
					
					select.innerHTML = schemas.map(name => 
						`<option value="${name}">${name}</option>`
					).join('');
					
					const dialog = document.getElementById('sg-schemaRemovalDialog');
					dialog?.classList.add('show');
					select.focus();
				},
	
				/**
				 * Hide schema removal dialog
				 * @returns {void}
				 */
				hideSchemaRemovalDialog: () => {
					const dialog = document.getElementById('sg-schemaRemovalDialog');
					dialog?.classList.remove('show');
				},
	
				/**
				 * Setup schema removal dialog handlers
				 * @returns {void}
				 */
				setupSchemaRemovalDialog: () => {
					const confirmBtn = document.getElementById('sg-schemaRemovalConfirm');
					const cancelBtn = document.getElementById('sg-schemaRemovalCancel');
					
					confirmBtn?.addEventListener('click', () => {
						const select = document.getElementById('sg-schemaRemovalNameInput');
						const schemaName = select?.value;
						
						if (!schemaName) {
							this.ui.messages.showError('Please select a schema');
							return;
						}
						
						if (this.api.schema.remove(schemaName)) {
							this.ui.dialogs.hideSchemaRemovalDialog();
							this.ui.messages.showSuccess(`Schema "${schemaName}" removed`, 2000);
						} else {
							this.ui.messages.showError('Failed to remove schema');
						}
					});
					
					cancelBtn?.addEventListener('click', () => {
						this.ui.dialogs.hideSchemaRemovalDialog();
					});
				},
	
				/**
				 * Show context menu
				 * @param {MouseEvent} e - Mouse event
				 * @param {Node|null} node - Node clicked (null for canvas)
				 * @returns {void}
				 */
				showContextMenu: (e, node = null) => {
					const [wx, wy] = this.api.util.screenToWorld(e.clientX, e.clientY);
					
					const menu = document.getElementById('sg-contextMenu');
					if (!menu) return;
					
					let html = '';
					
					if (node) {
						const selectionCount = this.api.node.getSelected().length;
						
						html += '<div class="sg-context-menu-category">Node Actions</div>';
						
						if (selectionCount > 1) {
							html += `<div class="sg-context-menu-item sg-context-menu-delete" data-action="delete-all">✖ Delete ${selectionCount} Nodes</div>`;
						} else {
							html += '<div class="sg-context-menu-item sg-context-menu-delete" data-action="delete">✖ Delete Node</div>';
						}
						
						if (node.multiInputs) {
							let totalLinks = 0;
							for (const slotIdx in node.multiInputs) {
								if (node.multiInputs.hasOwnProperty(slotIdx)) {
									const links = node.multiInputs[slotIdx].links;
									if (links && links.length > 0) {
										totalLinks += links.length;
									}
								}
							}
							
							if (totalLinks > 0) {
								html += `<div class="sg-context-menu-item" data-action="clear-multi">🗑️ Clear ${totalLinks} Multi-Input Link(s)</div>`;
							}
						}
					} else {
						html += '<div class="sg-context-menu-category">Native Types</div>';
						const natives = ['Native.String', 'Native.Integer', 'Native.Boolean', 'Native.Float', 'Native.List', 'Native.Dict'];
						for (const type of natives) {
							const name = type.split('.')[1];
							html += `<div class="sg-context-menu-item" data-type="${type}">${name}</div>`;
						}
						
						const schemas = this.api.schema.list();
						for (const schemaName of schemas) {
							const info = this.api.schema.info(schemaName);
							if (!info) continue;
							
							html += `<div class="sg-context-menu-category">${schemaName} Schema</div>`;
							
							if (info.rootType) {
								const rootType = `${schemaName}.${info.rootType}`;
								html += `<div class="sg-context-menu-item" data-type="${rootType}" style="font-weight: bold; color: var(--sg-accent-orange);">★ ${info.rootType} (Root)</div>`;
							}
							
							for (const model of info.models) {
								if (model !== info.rootType) {
									const type = `${schemaName}.${model}`;
									html += `<div class="sg-context-menu-item" data-type="${type}">${model}</div>`;
								}
							}
						}
					}
					
					menu.innerHTML = html;
					menu.style.left = e.clientX + 'px';
					menu.style.top = e.clientY + 'px';
					menu.classList.add('show');
					menu.dataset.worldX = wx;
					menu.dataset.worldY = wy;
					
					if (node) {
						menu.querySelector('[data-action="delete"]')?.addEventListener('click', () => {
							this.api.node.delete(node);
							menu.classList.remove('show');
						});
						
						menu.querySelector('[data-action="delete-all"]')?.addEventListener('click', () => {
							const selected = this.api.node.getSelected();
							selected.forEach(n => this.api.node.delete(n));
							menu.classList.remove('show');
						});
						
						menu.querySelector('[data-action="clear-multi"]')?.addEventListener('click', () => {
							this.api.link.clearAllMultiInputs(node);
							menu.classList.remove('show');
						});
					} else {
						menu.querySelectorAll('[data-type]').forEach(item => {
							item.addEventListener('click', () => {
								const type = item.getAttribute('data-type');
								const wx = parseFloat(menu.dataset.worldX);
								const wy = parseFloat(menu.dataset.worldY);
								this.api.node.create(type, wx - 90, wy - 40);
								menu.classList.remove('show');
							});
						});
					}
				},
	
				/**
				 * Hide context menu
				 * @returns {void}
				 */
				hideContextMenu: () => {
					const menu = document.getElementById('sg-contextMenu');
					menu?.classList.remove('show');
				},
	
				/**
				 * Show message dialog (replaces alert)
				 * @param {string} message - Message text
				 * @param {string} title - Dialog title (optional)
				 * @returns {Promise<void>} Resolves when OK is clicked
				 */
				showMessage: (message, title = 'Message') => {
					return new Promise((resolve) => {
						const dialog = document.getElementById('sg-messageDialog');
						const titleEl = document.getElementById('sg-messageDialogTitle');
						const contentEl = document.getElementById('sg-messageDialogContent');
						const okBtn = document.getElementById('sg-messageDialogOk');
						
						if (!dialog || !titleEl || !contentEl || !okBtn) {
							console.warn('Message dialog elements not found, falling back to alert');
							alert(message);
							resolve();
							return;
						}
						
						titleEl.textContent = title;
						contentEl.textContent = message;
						dialog.classList.add('show');
						
						const handleOk = () => {
							dialog.classList.remove('show');
							okBtn.removeEventListener('click', handleOk);
							resolve();
						};
						
						okBtn.addEventListener('click', handleOk);
						
						setTimeout(() => okBtn.focus(), 100);
					});
				},
	
				/**
				 * Show confirm dialog (replaces confirm)
				 * @param {string} message - Message text
				 * @param {string} title - Dialog title (optional)
				 * @returns {Promise<boolean>} Resolves to true if OK, false if Cancel
				 */
				showConfirm: (message, title = 'Confirm') => {
					return new Promise((resolve) => {
						const dialog = document.getElementById('sg-confirmDialog');
						const titleEl = document.getElementById('sg-confirmDialogTitle');
						const contentEl = document.getElementById('sg-confirmDialogContent');
						const okBtn = document.getElementById('sg-confirmDialogOk');
						const cancelBtn = document.getElementById('sg-confirmDialogCancel');
						
						if (!dialog || !titleEl || !contentEl || !okBtn || !cancelBtn) {
							console.warn('Confirm dialog elements not found, falling back to confirm');
							resolve(confirm(message));
							return;
						}
						
						titleEl.textContent = title;
						contentEl.textContent = message;
						dialog.classList.add('show');
						
						const cleanup = (result) => {
							dialog.classList.remove('show');
							okBtn.removeEventListener('click', handleOk);
							cancelBtn.removeEventListener('click', handleCancel);
							resolve(result);
						};
						
						const handleOk = () => cleanup(true);
						const handleCancel = () => cleanup(false);
						
						okBtn.addEventListener('click', handleOk);
						cancelBtn.addEventListener('click', handleCancel);
						
						setTimeout(() => cancelBtn.focus(), 100);
					});
				},
	
				setupAll: () => {
					this.ui.dialogs.setupSchemaDialog();
					this.ui.dialogs.setupSchemaRemovalDialog();
					
					document.addEventListener('click', (e) => {
						if (!e.target.closest('#sg-contextMenu')) {
							this.ui.dialogs.hideContextMenu();
						}
					});
					
					document.addEventListener('keydown', (e) => {
						if (e.key === 'Escape') {
							const messageDialog = document.getElementById('sg-messageDialog');
							if (messageDialog?.classList.contains('show')) {
								document.getElementById('sg-messageDialogOk')?.click();
							}
							
							const confirmDialog = document.getElementById('sg-confirmDialog');
							if (confirmDialog?.classList.contains('show')) {
								document.getElementById('sg-confirmDialogCancel')?.click();
							}
						}
					});
				}
			},
	
			update: {
				/**
				 * Update node types list in header
				 * @returns {void}
				 */
				nodeTypesList: () => {
					const types = Object.keys(this.graph.nodeTypes);
					const listEl = document.getElementById('sg-nodeTypesList');
					if (listEl) {
						listEl.textContent = types.length > 0 ? types.join(', ') : 'None';
					}
				},
	
				/**
				 * Update schema list in manager
				 * @returns {void}
				 */
				schemaList: () => {
					const schemas = this.api.schema.list();
					const listEl = document.getElementById('sg-schemaList');
					if (!listEl) return;
					
					if (schemas.length === 0) {
						listEl.innerHTML = '<div style="color: var(--sg-text-tertiary); font-size: 11px; padding: 8px;">No schemas registered</div>';
						return;
					}
					
					let html = '';
					for (const schemaName of schemas) {
						const info = this.api.schema.info(schemaName);
						if (!info) continue;
						
						let nodeCount = 0;
						for (const node of this.api.node.list()) {
							if (node.schemaName === schemaName) nodeCount++;
						}
						
						html += '<div class="sg-schema-item">';
						html += `<div><span class="sg-schema-item-name">${schemaName}</span>`;
						html += `<span class="sg-schema-item-count">(${info.models.length} types, ${nodeCount} nodes)</span></div>`;
						html += `<button class="sg-schema-remove-btn" data-schema="${schemaName}">Remove</button>`;
						html += '</div>';
					}
					
					listEl.innerHTML = html;
					
					listEl.querySelectorAll('.sg-schema-remove-btn').forEach(btn => {
						btn.addEventListener('click', () => {
							this.ui.dialogs.showSchemaRemovalDialog();
						});
					});
				},
	
				/**
				 * Update text scaling UI
				 * @returns {void}
				 */
				textScaling: () => {
					const btn = document.getElementById('sg-textScalingToggle');
					const label = document.getElementById('sg-textScalingLabel');
					
					if (!btn || !label) {
						console.warn('Text scaling UI elements not found');
						return;
					}
					
					const mode = this.api.textScaling.get();
					
					if (mode === 'scaled') {
						btn.classList.add('active');
						label.textContent = 'Text: Scaled';
						btn.title = 'Text scales with zoom (click for fixed size)';
					} else {
						btn.classList.remove('active');
						label.textContent = 'Text: Fixed';
						btn.title = 'Text stays readable (click to scale with zoom)';
					}
				},
	
				/**
				 * Update analytics display
				 * @returns {void}
				 */
				analytics: () => {
					const metrics = this.api.analytics.getMetrics();
					const session = this.api.analytics.getSession();
					
					const updateEl = (id, value) => {
						const el = document.getElementById(id);
						if (el) el.textContent = value;
					};
					
					updateEl('sg-sessionId', session.sessionId.substring(0, 8));
					updateEl('sg-sessionDuration', this.ui.util.formatDuration(session.duration));
					updateEl('sg-totalEvents', session.events);
					
					updateEl('sg-nodesCreated', metrics.nodeCreated);
					updateEl('sg-nodesDeleted', metrics.nodeDeleted);
					updateEl('sg-linksCreated', metrics.linkCreated);
					updateEl('sg-linksDeleted', metrics.linkDeleted);
					
					updateEl('sg-schemasRegistered', metrics.schemaRegistered);
					updateEl('sg-schemasRemoved', metrics.schemaRemoved);
					
					updateEl('sg-graphsExported', metrics.graphExported);
					updateEl('sg-graphsImported', metrics.graphImported);
					updateEl('sg-configsExported', metrics.configExported);
					updateEl('sg-configsImported', metrics.configImported);
					
					updateEl('sg-totalInteractions', metrics.interactions);
					updateEl('sg-layoutsApplied', metrics.layoutApplied);
					updateEl('sg-errorCount', metrics.errors);
				},
	
				/**
				 * Update status message
				 * @param {string} message - Status message
				 * @returns {void}
				 */
				status: (message) => {
					const statusEl = document.getElementById('sg-status');
					if (statusEl) statusEl.textContent = message;
				},
	
				/**
				 * Update zoom display
				 * @returns {void}
				 */
				zoom: () => {
					const zoomEl = document.getElementById('sg-zoomLevel');
					if (zoomEl) {
						zoomEl.textContent = Math.round(this.api.view.getZoom() * 100) + '%';
					}
				}
			},
	
			voice: {
				/**
				 * Setup voice controls
				 * @returns {void}
				 */
				setup: () => {
					const startBtn = document.getElementById('sg-voiceStartBtn');
					const stopBtn = document.getElementById('sg-voiceStopBtn');
					const status = document.getElementById('sg-voiceStatus');
					
					startBtn?.addEventListener('click', () => {
						if (this.api.voice.start()) {
							startBtn.style.display = 'none';
							stopBtn.style.display = 'inline-block';
							stopBtn.classList.add('active');
							if (status) status.textContent = 'Listening...';
						}
					});
					
					stopBtn?.addEventListener('click', () => {
						this.api.voice.stop();
						stopBtn.style.display = 'none';
						startBtn.style.display = 'inline-block';
						stopBtn.classList.remove('active');
						if (status) status.textContent = '';
					});
					
					this.eventBus.on('voice:result', (data) => {
						if (status) {
							status.textContent = `Heard: "${data.transcript}"`;
							setTimeout(() => {
								if (this.api.voice.isListening()) {
									status.textContent = 'Listening...';
								}
							}, 3000);
						}
					});
					
					this.eventBus.on('voice:stopped', () => {
						stopBtn.style.display = 'none';
						startBtn.style.display = 'inline-block';
						stopBtn.classList.remove('active');
						if (status) status.textContent = '';
					});
					
					this.eventBus.on('voice:error', (data) => {
						if (status) status.textContent = `Error: ${data.error}`;
						stopBtn.style.display = 'none';
						startBtn.style.display = 'inline-block';
						stopBtn.classList.remove('active');
					});
				}
			},
	
			analytics: {
				setup: () => {
					const toggleBtn = document.getElementById('sg-analyticsToggleBtn');
					const panel = document.getElementById('sg-analyticsPanel');
					const closeBtn = document.getElementById('sg-analyticsCloseBtn');
					const refreshBtn = document.getElementById('sg-refreshAnalyticsBtn');
					const exportBtn = document.getElementById('sg-exportAnalyticsBtn');
					const resetBtn = document.getElementById('sg-resetAnalyticsBtn');

					toggleBtn?.addEventListener('click', (e) => {
						e.stopPropagation();
						if (!panel) return;
						
						if (panel.classList.contains('show')) {
							panel.classList.add('hiding');
							setTimeout(() => {
								panel.classList.remove('show', 'hiding');
							}, 300);
						} else {
							panel.classList.add('show');
							this.ui.update.analytics();
						}
					});

					closeBtn?.addEventListener('click', () => {
						if (!panel) return;
						
						panel.classList.add('hiding');
						
						setTimeout(() => {
							panel.classList.remove('show', 'hiding');
						}, 300);
					});
					
					refreshBtn?.addEventListener('click', () => {
						this.ui.update.analytics();
					});
					
					exportBtn?.addEventListener('click', () => {
						this.api.analytics.download();
					});
					
					resetBtn?.addEventListener('click', async () => {
						const confirmed = await this.ui.dialogs.showConfirm(
							'Reset analytics for current session? This cannot be undone.',
							'⚠️ Reset Analytics'
						);
						
						if (confirmed) {
							this.api.analytics.endSession();
							this.ui.update.analytics();
						}
					});
					
					document.addEventListener('click', (e) => {
						if (!panel) return;
						
						const isVisible = panel.classList.contains('show');
						const clickedInsidePanel = panel.contains(e.target);
						const clickedToggleBtn = toggleBtn?.contains(e.target);
						
						if (isVisible && !clickedInsidePanel && !clickedToggleBtn) {
							panel.classList.add('hiding');
							
							setTimeout(() => {
								panel.classList.remove('show', 'hiding');
							}, 300);
						}
					});
					
					setInterval(() => {
						if (panel?.classList.contains('show')) {
							this.ui.update.analytics();
						}
					}, 5000);
				}
			},
	
			messages: {
				/**
				 * Show error message
				 * @param {string} text - Error message
				 * @param {number} duration - Duration in ms
				 * @returns {void}
				 */
				showError: (text, duration = 3000) => {
					const errorEl = document.getElementById('sg-errorBanner');
					if (errorEl) {
						errorEl.textContent = '⚠️ ' + text;
						errorEl.style.display = 'block';
						setTimeout(() => { errorEl.style.display = 'none'; }, duration);
					}
					this.eventBus.emit('error', { message: text });
				},
	
				/**
				 * Show success message
				 * @param {string} text - Success message
				 * @param {number} duration - Duration in ms
				 * @returns {void}
				 */
				showSuccess: (text, duration = 2000) => {
					this.ui.update.status(text);
					setTimeout(() => {
						this.ui.update.status('Right-click to add nodes.');
					}, duration);
				}
			},
	
			util: {
				/**
				 * Format duration
				 * @param {number} ms - Duration in milliseconds
				 * @returns {string} Formatted duration
				 */
				formatDuration: (ms) => {
					const seconds = Math.floor(ms / 1000);
					const minutes = Math.floor(seconds / 60);
					const hours = Math.floor(minutes / 60);
					
					if (hours > 0) {
						return `${hours}h ${minutes % 60}m ${seconds % 60}s`;
					} else if (minutes > 0) {
						return `${minutes}m ${seconds % 60}s`;
					} else {
						return `${seconds}s`;
					}
				},
	
				/**
				 * Resize canvas to fit container
				 * @returns {void}
				 */
				resizeCanvas: () => {
					const container = this.canvas.parentElement;
					const rect = container.getBoundingClientRect();
					this.canvas.width = rect.width;
					this.canvas.height = rect.height;
					this.api.util.redraw();
				}
			},
	
			/**
			 * Initialize all UI components
			 * @returns {void}
			 */
			init: () => {
				this.ui.buttons.setupAll();
				this.ui.dialogs.setupAll();
				this.ui.voice.setup();
				this.ui.analytics.setup();
				
				window.addEventListener('resize', () => this.ui.util.resizeCanvas());
				
				this.ui.update.textScaling();
				this.ui.update.nodeTypesList();
				this.ui.update.schemaList();
				this.ui.update.status('Ready. Upload a schema to begin.');
				this.ui.update.zoom();
			}
		};
	}
}
