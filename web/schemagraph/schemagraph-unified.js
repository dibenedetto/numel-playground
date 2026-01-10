// ========================================================================
// SCHEMAGRAPH - Unified Version with Workflow Support
// Single-file graph editor for Pydantic workflow schemas
// ========================================================================

console.log('=== SCHEMAGRAPH LOADING ===');

// ========================================================================
// FIELD ROLES & ENUMS
// ========================================================================

const FieldRole = Object.freeze({
	ANNOTATION: 'annotation',
	CONSTANT: 'constant',
	INPUT: 'input',
	OUTPUT: 'output',
	MULTI_INPUT: 'multi_input',
	MULTI_OUTPUT: 'multi_output'
});

const DataExportMode = Object.freeze({
	REFERENCE: 'reference',
	EMBEDDED: 'embedded'
});

// ========================================================================
// GRAPH EVENTS
// ========================================================================

const GraphEvents = Object.freeze({
	SCHEMA_REGISTERED: 'schema:registered',
	SCHEMA_REMOVED: 'schema:removed',
	SCHEMA_ENABLED: 'schema:enabled',
	SCHEMA_DISABLED: 'schema:disabled',
	
	NODE_CREATED: 'node:created',
	NODE_REMOVED: 'node:removed',
	NODE_SELECTED: 'node:selected',
	NODE_DESELECTED: 'node:deselected',
	NODE_MOVED: 'node:moved',
	NODE_RESIZED: 'node:resized',
	NODE_TITLE_CHANGED: 'node:titleChanged',
	NODE_COLOR_CHANGED: 'node:colorChanged',
	
	FIELD_CHANGED: 'field:changed',
	FIELD_CONNECTED: 'field:connected',
	FIELD_DISCONNECTED: 'field:disconnected',
	PROPERTY_CHANGED: 'property:changed',
	
	LINK_CREATED: 'link:created',
	LINK_REMOVED: 'link:removed',
	
	PREVIEW_INSERTED: 'preview:inserted',
	PREVIEW_REMOVED: 'preview:removed',
	
	DATA_LOADED: 'data:loaded',
	DATA_CLEARED: 'data:cleared',
	DATA_SOURCE_CHANGED: 'data:sourceChanged',
	
	WORKFLOW_IMPORTED: 'workflow:imported',
	WORKFLOW_EXPORTED: 'workflow:exported',
	
	GRAPH_CLEARED: 'graph:cleared',
	GRAPH_LOADED: 'graph:loaded',
	GRAPH_SAVED: 'graph:saved',
	GRAPH_CHANGED: 'graph:changed',
	GRAPH_LOCKED: 'graph:locked',
	GRAPH_UNLOCKED: 'graph:unlocked',
	
	CAMERA_MOVED: 'camera:moved',
	CAMERA_ZOOMED: 'camera:zoomed',
	VIEW_CENTERED: 'view:centered',
	
	THEME_CHANGED: 'theme:changed',
	STYLE_CHANGED: 'style:changed',
	CONTEXT_MENU_OPENED: 'contextMenu:opened',
	
	SELECTION_CHANGED: 'selection:changed',
	SELECTION_CLEARED: 'selection:cleared',
	
	CLIPBOARD_COPY: 'clipboard:copy',
	CLIPBOARD_PASTE: 'clipboard:paste',
	
	UNDO: 'history:undo',
	REDO: 'history:redo',
	
	ERROR: 'error'
});

const DATA_CHANGE_EVENTS = new Set([
	GraphEvents.SCHEMA_REGISTERED, GraphEvents.SCHEMA_REMOVED,
	GraphEvents.NODE_CREATED, GraphEvents.NODE_REMOVED, GraphEvents.NODE_MOVED,
	GraphEvents.NODE_RESIZED, GraphEvents.NODE_TITLE_CHANGED, GraphEvents.NODE_COLOR_CHANGED,
	GraphEvents.FIELD_CHANGED, GraphEvents.FIELD_CONNECTED, GraphEvents.FIELD_DISCONNECTED,
	GraphEvents.PROPERTY_CHANGED, GraphEvents.LINK_CREATED, GraphEvents.LINK_REMOVED,
	GraphEvents.PREVIEW_INSERTED, GraphEvents.PREVIEW_REMOVED,
	GraphEvents.DATA_LOADED, GraphEvents.DATA_CLEARED, GraphEvents.DATA_SOURCE_CHANGED,
	GraphEvents.WORKFLOW_IMPORTED, GraphEvents.GRAPH_CLEARED,
	GraphEvents.UNDO, GraphEvents.REDO, GraphEvents.CLIPBOARD_PASTE
]);

const DecoratorType = Object.freeze({
	INFO: 'node_info',
	BUTTON: 'node_button',
	DROPZONE: 'node_dropzone',
	CHAT: 'node_chat'
});

const ButtonStack = Object.freeze({
	TOP: 'top',
	BOTTOM: 'bottom'
});

const DropZoneArea = Object.freeze({
	FULL: 'full',
	CONTENT: 'content',
	CUSTOM: 'custom'
});

// ========================================================================
// EVENT BUS
// ========================================================================

class EventBus {
	constructor() {
		this.listeners = new Map();
		this.onceListeners = new Map();
		this.eventHistory = [];
		this.maxHistory = 1000;
		this.debug = false;
	}

	on(event, callback, context = null) {
		if (!this.listeners.has(event)) this.listeners.set(event, []);
		this.listeners.get(event).push({ callback, context });
		return () => this.off(event, callback);
	}

	once(event, callback, context = null) {
		if (!this.onceListeners.has(event)) this.onceListeners.set(event, []);
		this.onceListeners.get(event).push({ callback, context });
		return () => {
			const arr = this.onceListeners.get(event);
			if (arr) {
				const idx = arr.findIndex(l => l.callback === callback);
				if (idx > -1) arr.splice(idx, 1);
			}
		};
	}

	off(event, callback) {
		if (this.listeners.has(event)) {
			const arr = this.listeners.get(event);
			const idx = arr.findIndex(l => l.callback === callback);
			if (idx > -1) arr.splice(idx, 1);
		}
		if (this.onceListeners.has(event)) {
			const arr = this.onceListeners.get(event);
			const idx = arr.findIndex(l => l.callback === callback);
			if (idx > -1) arr.splice(idx, 1);
		}
	}

	emit(event, data = null) {
		const eventData = { event, data, timestamp: Date.now() };
		this.eventHistory.push(eventData);
		if (this.eventHistory.length > this.maxHistory) this.eventHistory.shift();

		if (this.debug || (typeof window !== 'undefined' && window.DEBUG_GRAPH_EVENTS)) {
			console.log(`[GraphEvent] ${event}`, data);
		}

		// Regular listeners
		if (this.listeners.has(event)) {
			for (const { callback, context } of this.listeners.get(event)) {
				try { callback.call(context, data); }
				catch (e) { console.error(`Error in event listener for ${event}:`, e); }
			}
		}

		// Once listeners
		if (this.onceListeners.has(event)) {
			const onceArr = this.onceListeners.get(event).slice();
			this.onceListeners.set(event, []);
			for (const { callback, context } of onceArr) {
				try { callback.call(context, data); }
				catch (e) { console.error(`Error in once listener for ${event}:`, e); }
			}
		}

		// Emit GRAPH_CHANGED for data-changing events
		if (DATA_CHANGE_EVENTS.has(event) && event !== GraphEvents.GRAPH_CHANGED) {
			this.emit(GraphEvents.GRAPH_CHANGED, { originalEvent: event, ...data });
		}
	}

	clear(event = null) {
		if (event) {
			this.listeners.delete(event);
			this.onceListeners.delete(event);
		} else {
			this.listeners.clear();
			this.onceListeners.clear();
		}
	}

	removeAllListeners(event = null) {
		this.clear(event);
	}

	getHistory(event = null, limit = 100) {
		let history = this.eventHistory;
		if (event) history = history.filter(e => e.event === event);
		return history.slice(-limit);
	}

	enableDebug() { this.debug = true; }
	disableDebug() { this.debug = false; }
}

// ========================================================================
// EXTENSION SYSTEM
// ========================================================================

class ExtensionRegistry {
	constructor() {
		this.extensions = new Map();
		this.initialized = false;
	}

	register(name, ExtensionClass) {
		if (this.extensions.has(name)) {
			console.warn(`[ExtensionRegistry] "${name}" already registered, replacing`);
		}
		this.extensions.set(name, { Class: ExtensionClass, instance: null });
	}

	initAll(app) {
		if (this.initialized) return;
		
		for (const [name, ext] of this.extensions) {
			try {
				ext.instance = new ext.Class(app);
				ext.instance._name = name;
				console.log(`✔ Extension: ${name}`);
			} catch (e) {
				console.error(`✗ Extension ${name} failed:`, e);
			}
		}
		this.initialized = true;
	}

	get(name) {
		return this.extensions.get(name)?.instance;
	}

	list() {
		return Array.from(this.extensions.keys());
	}

	has(name) {
		return this.extensions.has(name);
	}
}

class SchemaGraphExtension {
	constructor(app) {
		this.app = app;
		this.graph = app.graph;
		this.eventBus = app.eventBus;
		this._eventHandlers = [];
		this._name = 'unnamed';
		
		this._init();
	}

	_init() {
		this._registerNodeTypes();
		this._setupEventListeners();
		this._extendAPI();
		this._injectStyles();
	}

	// Override in subclasses
	_registerNodeTypes() {}
	_setupEventListeners() {}
	_extendAPI() {}
	_injectStyles() {}

	on(event, handler) {
		this.eventBus.on(event, handler);
		this._eventHandlers.push({ event, handler, isDOM: false });
	}

	onDOM(element, event, handler, options) {
		element.addEventListener(event, handler, options);
		this._eventHandlers.push({ element, event, handler, options, isDOM: true });
	}

	destroy() {
		for (const h of this._eventHandlers) {
			if (h.isDOM) {
				h.element.removeEventListener(h.event, h.handler, h.options);
			} else {
				this.eventBus.off?.(h.event, h.handler);
			}
		}
		this._eventHandlers = [];
	}

	getPref(key, defaultVal = null) {
		const stored = localStorage.getItem(`sg-${this._name}-${key}`);
		if (stored === null) return defaultVal;
		try { return JSON.parse(stored); } catch { return stored; }
	}

	setPref(key, value) {
		localStorage.setItem(`sg-${this._name}-${key}`, JSON.stringify(value));
	}
}

// Drawing utilities for extensions
const DrawUtils = {
	roundRect(ctx, x, y, w, h, r) {
		ctx.moveTo(x + r, y);
		ctx.lineTo(x + w - r, y);
		ctx.quadraticCurveTo(x + w, y, x + w, y + r);
		ctx.lineTo(x + w, y + h - r);
		ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
		ctx.lineTo(x + r, y + h);
		ctx.quadraticCurveTo(x, y + h, x, y + h - r);
		ctx.lineTo(x, y + r);
		ctx.quadraticCurveTo(x, y, x + r, y);
		ctx.closePath();
	},

	darkenColor(hex, amount) {
		const num = parseInt(hex.replace('#', ''), 16);
		const r = Math.max(0, (num >> 16) - amount);
		const g = Math.max(0, ((num >> 8) & 0xFF) - amount);
		const b = Math.max(0, (num & 0xFF) - amount);
		return '#' + ((r << 16) | (g << 8) | b).toString(16).padStart(6, '0');
	},

	lightenColor(hex, amount) {
		const num = parseInt(hex.replace('#', ''), 16);
		const r = Math.min(255, (num >> 16) + amount);
		const g = Math.min(255, ((num >> 8) & 0xFF) + amount);
		const b = Math.min(255, (num & 0xFF) + amount);
		return '#' + ((r << 16) | (g << 8) | b).toString(16).padStart(6, '0');
	},

	formatSize(bytes) {
		if (!bytes) return '0 B';
		const units = ['B', 'KB', 'MB', 'GB'];
		let i = 0;
		while (bytes >= 1024 && i < units.length - 1) { bytes /= 1024; i++; }
		return `${bytes.toFixed(i > 0 ? 1 : 0)} ${units[i]}`;
	},

	wrapText(ctx, text, maxWidth) {
		const words = text.split(/(\s+)/);
		const lines = [];
		let current = '';
		for (const word of words) {
			const test = current + word;
			if (ctx.measureText(test).width > maxWidth && current) {
				lines.push(current.trim());
				current = word;
			} else {
				current = test;
			}
		}
		if (current.trim()) lines.push(current.trim());
		return lines;
	}
};

class NodeDecoratorParser {
	constructor() {
		this.decorators = {};
	}

	parse(code) {
		this.decorators = {};
		const lines = code.split('\n');
		let pending = [];
		let accumulator = null;
		let accType = null;
		let depth = 0;
		
		for (const line of lines) {
			const trimmed = line.trim();
			
			if (accumulator !== null) {
				accumulator += ' ' + trimmed;
				for (const c of trimmed) { if (c === '(') depth++; else if (c === ')') depth--; }
				if (depth === 0) {
					const cfg = this._parseDecorator(accumulator, accType);
					if (cfg) pending.push({ type: accType, config: cfg });
					accumulator = null;
				}
				continue;
			}
			
			for (const [prefix, type] of [
				['@node_button', DecoratorType.BUTTON], 
				['@node_dropzone', DecoratorType.DROPZONE],
				['@node_chat', DecoratorType.CHAT],
				['@node_info', DecoratorType.INFO]  // <-- Add
			]) {
				if (trimmed.startsWith(prefix)) {
					depth = 0;
					for (const c of trimmed) { if (c === '(') depth++; else if (c === ')') depth--; }
					if (depth === 0) {
						const cfg = this._parseDecorator(trimmed, type);
						if (cfg) pending.push({ type, config: cfg });
					} else {
						accumulator = trimmed;
						accType = type;
					}
					break;
				}
			}
			
			const classMatch = trimmed.match(/^class\s+(\w+)\s*\(/);
			if (classMatch && pending.length) {
				this._apply(classMatch[1], pending);
				pending = [];
			} else if (trimmed && !trimmed.startsWith('#') && !trimmed.startsWith('@')) {
				pending = [];
			}
		}
		return this.decorators;
	}

	_parseDecorator(str, type) {
		const match = str.match(new RegExp(`^@${type}\\s*\\((.*)\\)\\s*$`));
		if (!match) return null;
		
		// Handle empty decorator like @node_info()
		if (!match[1].trim()) return {};
		
		const config = {};
		const regex = /(\w+)\s*=\s*(?:"([^"]*)"|'([^']*)'|([^,\)]+))/g;
		let m;
		while ((m = regex.exec(match[1])) !== null) {
			let val = m[2] ?? m[3] ?? m[4]?.trim();
			if (val === 'True' || val === 'true') val = true;
			else if (val === 'False' || val === 'false') val = false;
			else if (val === 'None' || val === 'null') val = null;
			else if (/^-?\d+$/.test(val)) val = parseInt(val);
			else if (/^-?\d+\.\d+$/.test(val)) val = parseFloat(val);
			config[m[1]] = val;
		}
		return config;
	}

	_apply(modelName, decorators) {
		if (!this.decorators[modelName]) {
			this.decorators[modelName] = { buttons: [], dropzone: null, chat: null, info: null };
		}
		for (const d of decorators) {
			if (d.type === DecoratorType.BUTTON) this.decorators[modelName].buttons.push(d.config);
			else if (d.type === DecoratorType.DROPZONE) this.decorators[modelName].dropzone = d.config;
			else if (d.type === DecoratorType.CHAT) this.decorators[modelName].chat = d.config;
			else if (d.type === DecoratorType.INFO) this.decorators[modelName].info = d.config;
		}
	}
}

// Global extension registry instance
const extensionRegistry = new ExtensionRegistry();

// ========================================================================
// ANALYTICS SERVICE
// ========================================================================

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
			nodeCreated: 0, nodeDeleted: 0, linkCreated: 0, linkDeleted: 0,
			schemaRegistered: 0, schemaRemoved: 0, graphExported: 0, graphImported: 0,
			configExported: 0, configImported: 0, layoutApplied: 0, errors: 0, interactions: 0
		};
	}

	createSession() {
		return { id: Math.random().toString(36).substr(2, 9), startTime: Date.now(), events: [], metrics: {} };
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
		if (this.metrics.hasOwnProperty(metric)) this.metrics[metric] += value;
		this.currentSession.events.push({ metric, value, timestamp: Date.now() });
	}

	getMetrics() { return { ...this.metrics }; }

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
}

// ========================================================================
// NODE & LINK CLASSES
// ========================================================================

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
		if (this.outputs[slot]) this.outputs[slot].value = data;
	}

	onExecute() {}
}

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
		if ((valStr.startsWith('"') && valStr.endsWith('"')) || (valStr.startsWith("'") && valStr.endsWith("'"))) return valStr.slice(1, -1);
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
			if (typeStr.includes(alias)) typeStr = typeStr.replace(new RegExp(`\\b${alias}\\b`, 'g'), resolved);
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
		if ((valStr.startsWith('"') && valStr.endsWith('"')) || (valStr.startsWith("'") && valStr.endsWith("'"))) return valStr.slice(1, -1);
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
		if (typeStr.startsWith('Optional[')) return { kind: 'optional', inner: this._parseType(this._extractBracketContent(typeStr, 9)) };
		if (typeStr.startsWith('Union[')) {
			const inner = this._extractBracketContent(typeStr, 6);
			return { kind: 'union', types: this._splitUnionTypes(inner).map(t => this._parseType(t)), inner };
		}
		if (typeStr.startsWith('List[')) return { kind: 'list', inner: this._parseType(this._extractBracketContent(typeStr, 5)) };
		if (typeStr.startsWith('Dict[')) return { kind: 'dict', inner: this._extractBracketContent(typeStr, 5) };
		if (typeStr.startsWith('Message[')) return { kind: 'message', inner: this._parseType(this._extractBracketContent(typeStr, 8)) };
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
			// Use title for display, fallback to original name
			const displayName = field.title || field.name;
			node.addInput(displayName, field.rawType);
			
			node.inputMeta[inputIdx] = {
				name: field.name,  // Always store original name
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

		if (this.app?._applyDecoratorsToNode) {
			this.app._applyDecoratorsToNode(node);
		}

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
			} else current += c;
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

		this.eventBus.emit('workflow:imported', { nodeCount: this.graph.nodes.length, linkCount: Object.keys(this.graph.links).length });
		return true;
	}

	_createNativeNode(nodeData, index) {
		const typeMap = { 'native_string': 'String', 'native_integer': 'Integer', 'native_float': 'Float', 'native_boolean': 'Boolean', 'native_list': 'List', 'native_dict': 'Dict' };
		const nativeType = typeMap[nodeData.type] || 'String';
		const NodeClass = this.graph.nodeTypes[`Native.${nativeType}`];
		if (!NodeClass) { console.error(`Native node type not found: Native.${nativeType}`); return null; }

		const node = new NodeClass();
		if (nodeData.value !== undefined) { node.properties = node.properties || {}; node.properties.value = nodeData.value; }
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
			if (nodeData.extra.color) node.color = nodeData.extra.color;
		}

		this._populateNodeFields(node, nodeData);

		node.annotations = {};
		const roles = this.graph.schemas[schemaName]?.fieldRoles?.[modelName] || {};
		for (const [fieldName, role] of Object.entries(roles)) {
			if (role === FieldRole.ANNOTATION && nodeData[fieldName] !== undefined) node.annotations[fieldName] = nodeData[fieldName];
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
		if (schema?.defaults) for (const [key, value] of Object.entries(schema.defaults)) if (value?.type) typeMap[value.type] = key;
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

	_snakeToPascal(str) { return str.split('_').map(p => p.charAt(0).toUpperCase() + p.slice(1).toLowerCase()).join(''); }

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

		return this._createStandardEdge(sourceNode, sourceSlotIdx, targetNode, targetSlotIdx, edgeData.data, edgeData.extra);
	}

	_findOutputSlot(node, slotName) {
		for (let i = 0; i < node.outputs.length; i++) if (node.outputs[i].name === slotName) return i;
		const idx = parseInt(slotName);
		if (!isNaN(idx) && idx >= 0 && idx < node.outputs.length) return idx;
		if (node.isNative && node.outputs.length > 0) return 0;
		return -1;
	}

	_findInputSlot(node, slotName) {
		for (let i = 0; i < node.inputs.length; i++) if (node.inputs[i].name === slotName) return i;
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
		this.exportOptions = { dataExportMode: options.dataExportMode || DataExportMode.REFERENCE, includeLayout: options.includeLayout !== false };
		const workflow = { ...JSON.parse(JSON.stringify(workflowInfo)), type: 'workflow', nodes: [], edges: [] };
		const exportableNodes = this.graph.nodes.filter(n => !n.isPreviewNode);

		exportableNodes.sort((a, b) => {
			if (a.workflowIndex !== undefined && b.workflowIndex !== undefined) return a.workflowIndex - b.workflowIndex;
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
		const typeMap = { 'String': 'native_string', 'Integer': 'native_integer', 'Float': 'native_float', 'Boolean': 'native_boolean', 'List': 'native_list', 'Dict': 'native_dict' };
		const nativeType = node.title || 'String';
		let value = node.properties?.value;
		if (value === undefined) value = this._getDefaultNativeValue(nativeType);
		const nodeData = { type: typeMap[nativeType] || 'native_string', value };
		if (this.exportOptions?.includeLayout !== false) nodeData.extra = { pos: [...node.pos], size: [...node.size] };
		return nodeData;
	}

	_getDefaultNativeValue(nativeType) {
		switch (nativeType) { case 'Integer': return 0; case 'Float': return 0.0; case 'Boolean': return false; case 'List': return []; case 'Dict': return {}; default: return ''; }
	}

	_exportWorkflowNode(node) {
		const nodeData = { type: node.workflowType || node.constantFields?.type || node.modelName?.toLowerCase() || 'unknown' };
		if (node.workflowId) nodeData.id = node.workflowId;
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

		if (node.annotations) for (const [key, value] of Object.entries(node.annotations)) if (value !== null && value !== undefined) nodeData[key] = value;
		return nodeData;
	}

	_exportEdge(link, nodeToIndex) {
		const sourceNode = this.graph.getNodeById(link.origin_id), targetNode = this.graph.getNodeById(link.target_id);
		if (!sourceNode || !targetNode) return null;
		const sourceIdx = nodeToIndex.get(link.origin_id), targetIdx = nodeToIndex.get(link.target_id);
		if (sourceIdx === undefined || targetIdx === undefined) return null;

		const edge = { type: 'edge', source: sourceIdx, target: targetIdx, source_slot: sourceNode.outputs[link.origin_slot]?.name || 'output', target_slot: targetNode.inputs[link.target_slot]?.name || 'input' };
		if (link.data && Object.keys(link.data).length > 0) edge.data = JSON.parse(JSON.stringify(link.data));
		if (link.extra && Object.keys(link.extra).length > 0) edge.extra = JSON.parse(JSON.stringify(link.extra));
		return edge;
	}

	_convertExportValue(val, type) {
		if ((type === 'dict' || type === 'list') && typeof val === 'string') { try { return JSON.parse(val); } catch { return val; } }
		return val;
	}
}

// ========================================================================
// GRAPH BASE CLASS
// ========================================================================

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

	getNodeById(id) { return this._nodes_by_id[id]; }

	connect(originNode, originSlot, targetNode, targetSlot) {
		const outputType = originNode.outputs[originSlot]?.type;
		const inputType = targetNode.inputs[targetSlot]?.type;
		if (!this._areTypesCompatible(outputType, inputType)) { console.warn('Type mismatch:', outputType, '!=', inputType); return null; }

		const linkId = ++this.last_link_id;
		const link = new Link(linkId, originNode.id, originSlot, targetNode.id, targetSlot, outputType);
		this.links[linkId] = link;
		originNode.outputs[originSlot].links.push(linkId);
		targetNode.inputs[targetSlot].link = linkId;
		return link;
	}

	_areTypesCompatible(outputType, inputType) {
		if (!outputType || !inputType) return true;
		const output = outputType.trim(), input = inputType.trim();
		if (output === input || input === 'Any' || output === 'Any') return true;

		const optMatch = input.match(/Optional\[(.+)\]/);
		if (optMatch) return this._areTypesCompatible(output, optMatch[1]);

		const unionMatch = input.match(/Union\[(.+)\]/);
		if (unionMatch) {
			for (const t of this._splitTypeString(unionMatch[1])) if (this._areTypesCompatible(output, t)) return true;
			return false;
		}

		if (input.indexOf('|') !== -1) {
			for (const p of input.split('|')) if (this._areTypesCompatible(output, p.trim())) return true;
			return false;
		}

		if (output.indexOf('.') !== -1) { const outModel = output.split('.').pop(); return outModel === input || this._areTypesCompatible(outModel, input); }
		if (input.indexOf('.') !== -1) { const inModel = input.split('.').pop(); return output === inModel || this._areTypesCompatible(output, inModel); }

		if (output === 'int' && (input === 'Index' || input === 'integer')) return true;
		if (input === 'int' && (output === 'Index' || output === 'integer')) return true;
		if ((output === 'str' && input === 'string') || (input === 'str' && output === 'string')) return true;
		return false;
	}

	_splitTypeString(str) {
		const result = []; let depth = 0, current = '';
		for (let i = 0; i < str.length; i++) {
			const c = str.charAt(i);
			if (c === '[') depth++; if (c === ']') depth--;
			if (c === ',' && depth === 0) { result.push(current.trim()); current = ''; } else current += c;
		}
		if (current) result.push(current.trim());
		return result;
	}
}

// ========================================================================
// SCHEMA GRAPH (with workflow support)
// ========================================================================

class SchemaGraph extends Graph {
	constructor(eventBus) {
		super();
		this.eventBus = eventBus;
		this.schemas = {};
		this.nodeTypes = {};
		this.enabledSchemas = new Set();
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
			this.schemas[schemaName] = { code: schemaCode, parsed: parsed.models, isWorkflow: true, fieldRoles: parsed.fieldRoles, defaults: parsed.defaults };

			const self = this;
			for (const modelName in parsed.models) {
				const defaults = parsed.defaults[modelName] || {};
				if (!defaults.type) continue;

				const fullTypeName = `${schemaName}.${modelName}`;
				const capturedModelName = modelName, capturedSchemaName = schemaName;
				const capturedFields = parsed.models[modelName], capturedRoles = parsed.fieldRoles[modelName], capturedDefaults = defaults;

				function WorkflowNodeType() {
					const factory = new WorkflowNodeFactory(self, { models: { [capturedModelName]: capturedFields }, fieldRoles: { [capturedModelName]: capturedRoles }, defaults: { [capturedModelName]: capturedDefaults } }, capturedSchemaName);
					const node = factory.createNode(capturedModelName, {});
					Object.assign(this, node); Object.setPrototypeOf(this, node);
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

	enableSchema(schemaName) { if (this.schemas[schemaName]) { this.enabledSchemas.add(schemaName); this.eventBus.emit('schema:enabled', { schemaName }); return true; } return false; }
	disableSchema(schemaName) { if (this.schemas[schemaName]) { this.enabledSchemas.delete(schemaName); this.eventBus.emit('schema:disabled', { schemaName }); return true; } return false; }
	toggleSchema(schemaName) { return this.enabledSchemas.has(schemaName) ? this.disableSchema(schemaName) : this.enableSchema(schemaName); }
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
			if (modelType && parsedModels[modelType]) { mapping.modelToField[modelType] = field.name; mapping.fieldToModel[field.name] = modelType; }
		}
		return mapping;
	}

	_extractModelTypeFromField(fieldType) {
		let current = fieldType;
		if (current.kind === 'optional') current = current.inner;
		if (current.kind === 'list' || current.kind === 'set' || current.kind === 'tuple') current = current.inner;
		if (current.kind === 'dict') return null;
		if (current.kind === 'union') { for (const type of current.types) if (type.kind === 'basic' && type.name?.endsWith('Config')) return type.name; return null; }
		if (current.kind === 'basic' && current.name?.endsWith('Config')) return current.name;
		return null;
	}

	_createFallbackMapping(parsedModels) {
		const mapping = { modelToField: {}, fieldToModel: {} };
		for (const modelName in parsedModels) {
			if (!parsedModels.hasOwnProperty(modelName)) continue;
			const baseName = modelName.replace(/Config$/, '');
			let fieldName = baseName.replace(/([A-Z]+)([A-Z][a-z])/g, '$1_$2').replace(/([a-z\d])([A-Z])/g, '$1_$2').toLowerCase();
			if (!fieldName.endsWith('s')) { fieldName = fieldName.endsWith('y') && !['ay', 'ey', 'iy', 'oy', 'uy'].some(end => fieldName.endsWith(end)) ? fieldName.slice(0, -1) + 'ies' : fieldName + 's'; }
			mapping.modelToField[modelName] = fieldName; mapping.fieldToModel[fieldName] = modelName;
		}
		return mapping;
	}

	_parseSchema(code) {
		const models = {}; const lines = code.split('\n'); let currentModel = null, currentFields = [];
		for (const line of lines) {
			const trimmed = line.trim();
			const classMatch = trimmed.match(/^class\s+(\w+)\s*\(/);
			if (classMatch) { if (currentModel) models[currentModel] = currentFields; currentModel = classMatch[1]; currentFields = []; continue; }
			if (currentModel && trimmed.indexOf(':') !== -1) {
				const fieldMatch = trimmed.match(/^(\w+)\s*:\s*(.+?)(?:\s*=|$)/);
				if (fieldMatch) currentFields.push({ name: fieldMatch[1], type: this._parseType(fieldMatch[2].trim()), rawType: fieldMatch[2].trim() });
			}
		}
		if (currentModel) models[currentModel] = currentFields;
		return models;
	}

	_parseType(str) {
		str = str.trim();
		if (str.indexOf('Optional[') === 0) return { kind: 'optional', inner: this._parseType(this._extractBracket(str, 9)) };
		if (str.indexOf('Union[') === 0) return { kind: 'union', types: this._splitTypes(this._extractBracket(str, 6)).map(t => this._parseType(t)) };
		if (str.indexOf('List[') === 0) return { kind: 'list', inner: this._parseType(this._extractBracket(str, 5)) };
		if (str.indexOf('Dict[') === 0 || str.indexOf('dict[') === 0) return { kind: 'dict', inner: this._extractBracket(str, str.indexOf('[') + 1) };
		return { kind: 'basic', name: str };
	}

	_extractBracket(str, start) { let depth = 1, i = start; while (i < str.length && depth > 0) { if (str.charAt(i) === '[') depth++; if (str.charAt(i) === ']') depth--; if (depth === 0) break; i++; } return str.substring(start, i); }
	_splitTypes(str) { const result = []; let depth = 0, current = ''; for (let i = 0; i < str.length; i++) { const c = str.charAt(i); if (c === '[') depth++; if (c === ']') depth--; if (c === ',' && depth === 0) { result.push(current.trim()); current = ''; } else current += c; } if (current) result.push(current.trim()); return result; }

	_generateNodes(schemaName, models, indexType) {
		for (const modelName in models) {
			if (!models.hasOwnProperty(modelName)) continue;
			const fields = models[modelName];
			const self = this, schemaInfo = this.schemas[schemaName], isRootType = schemaInfo && schemaInfo.rootType === modelName;

			class GeneratedNode extends Node {
				constructor() {
					super(schemaName + '.' + modelName);
					this.schemaName = schemaName; this.modelName = modelName; this.isRootType = isRootType;
					this.addOutput('self', modelName); this.nativeInputs = {}; this.multiInputs = {}; this.optionalFields = {};

					for (let i = 0; i < fields.length; i++) {
						const f = fields[i];
						const inputType = self._getInputType(f, indexType);
						const compactType = self.compactType(inputType);
						const isOptional = f.type.kind === 'optional';
						if (isOptional) this.optionalFields[i] = true;

						const isCollectionOfUnions = self._isCollectionOfUnions(f.type);
						const isListField = isRootType && self._isListFieldType(f.type);

						if (isCollectionOfUnions || isListField) { this.addInput(f.name, compactType); this.multiInputs[i] = { type: compactType, links: [] }; }
						else {
							this.addInput(f.name, compactType);
							if (self._isNativeType(compactType)) {
								const baseType = self._getNativeBaseType(compactType);
								this.nativeInputs[i] = { type: baseType, value: self._getDefaultValueForType(baseType), optional: isOptional };
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
								if (link) { const sourceNode = this.graph.getNodeById(link.origin_id); if (sourceNode?.outputs[link.origin_slot]) values.push(sourceNode.outputs[link.origin_slot].value); }
							}
							if (values.length > 0) data[this.inputs[i].name] = values;
							else if (this.optionalFields[i]) continue;
						} else {
							const connectedVal = this.getInputData(i);
							if (connectedVal !== null && connectedVal !== undefined) data[this.inputs[i].name] = connectedVal;
							else if (this.nativeInputs[i] !== undefined) {
								const val = this.nativeInputs[i].value, isOptional = this.nativeInputs[i].optional, baseType = this.nativeInputs[i].type;
								if (baseType === 'bool') { if (val === true || val === false) data[this.inputs[i].name] = val; else if (val === 'true') data[this.inputs[i].name] = true; else if (!isOptional && (val === 'false' || val === '')) data[this.inputs[i].name] = false; continue; }
								const isEmpty = val === null || val === undefined || val === '';
								if (isOptional && isEmpty) continue;
								if (!isEmpty) {
									if (baseType === 'dict' || baseType === 'list') { try { data[this.inputs[i].name] = JSON.parse(val); } catch { data[this.inputs[i].name] = baseType === 'dict' ? {} : []; } }
									else if (baseType === 'int') data[this.inputs[i].name] = parseInt(val) || 0;
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
		const base = typeStr.replace(/^Optional\[|\]$/g, '').split('|')[0].trim();
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

	_isListFieldType(fieldType) { let current = fieldType; if (current.kind === 'optional') current = current.inner; return current.kind === 'list'; }

	_getNativeBaseType(typeStr) {
		if (!typeStr) return 'str';
		const base = typeStr.replace(/^Optional\[|\]$/g, '').split('|')[0].trim();
		if (base === 'int' || base === 'integer' || base === 'Index') return 'int';
		if (base === 'bool') return 'bool';
		if (base === 'float') return 'float';
		if (base.indexOf('Dict[') === 0) return 'dict';
		if (base.indexOf('List[') === 0) return 'list';
		return 'str';
	}

	_getDefaultValueForType(baseType) {
		if (baseType === 'int') return 0; if (baseType === 'bool') return false; if (baseType === 'float') return 0.0;
		if (baseType === 'dict') return '{}'; if (baseType === 'list') return '[]'; return '';
	}

	_getInputType(field, indexType) {
		const t = field.type;
		if (t.kind === 'optional') return 'Optional[' + this._getInputType({ type: t.inner }, indexType) + ']';
		if (t.kind === 'union') {
			let hasIdx = false, modelType = null;
			for (const tp of t.types) { if (tp.kind === 'basic' && tp.name === indexType) hasIdx = true; else modelType = tp; }
			if (hasIdx && modelType && t.types.length === 2) return modelType.name || 'Model';
			return t.types.map(tp => tp.name || tp.kind).join('|');
		}
		if (t.kind === 'list') return 'List[' + this._getInputType({ type: t.inner }, indexType) + ']';
		if (t.kind === 'dict') return 'Dict[' + t.inner + ']';
		if (t.kind === 'basic') return t.name;
		return 'Any';
	}

	compactType(typeStr) { return typeStr ? typeStr.replace(/\s+/g, '') : typeStr; }

	getSchemaInfo(schemaName) { if (!this.schemas[schemaName]) return null; return { name: schemaName, indexType: this.schemas[schemaName].indexType, rootType: this.schemas[schemaName].rootType, models: Object.keys(this.schemas[schemaName].parsed), isWorkflow: this.schemas[schemaName].isWorkflow || false }; }

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
				for (let j = 0; j < node.inputs.length; j++) { if (node.inputs[j].link) { const linkId = node.inputs[j].link; const link = this.links[linkId]; if (link) { const originNode = this.getNodeById(link.origin_id); if (originNode) { const idx = originNode.outputs[link.origin_slot].links.indexOf(linkId); if (idx > -1) originNode.outputs[link.origin_slot].links.splice(idx, 1); } delete this.links[linkId]; } } }
				for (let j = 0; j < node.outputs.length; j++) { const links = node.outputs[j].links.slice(); for (const linkId of links) { const link = this.links[linkId]; if (link) { const targetNode = this.getNodeById(link.target_id); if (targetNode) targetNode.inputs[link.target_slot].link = null; delete this.links[linkId]; } } }
				this.nodes.splice(i, 1); delete this._nodes_by_id[node.id];
			}
		}
		for (const type in this.nodeTypes) if (this.nodeTypes.hasOwnProperty(type) && type.indexOf(schemaName + '.') === 0) delete this.nodeTypes[type];
		delete this.schemas[schemaName]; this.eventBus.emit('schema:removed', { schemaName }); return true;
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
			const nodeData = { id: node.id, type: node.title, pos: node.pos.slice(), size: node.size.slice(), properties: JSON.parse(JSON.stringify(node.properties || {})), schemaName: node.schemaName, modelName: node.modelName, isNative: node.isNative || false, isRootType: node.isRootType || false, isWorkflowNode: node.isWorkflowNode || false };
			if (node.nativeInputs) nodeData.nativeInputs = JSON.parse(JSON.stringify(node.nativeInputs));
			if (node.multiInputs) nodeData.multiInputs = JSON.parse(JSON.stringify(node.multiInputs));
			if (node.multiInputSlots) nodeData.multiInputSlots = JSON.parse(JSON.stringify(node.multiInputSlots));
			if (node.multiOutputSlots) nodeData.multiOutputSlots = JSON.parse(JSON.stringify(node.multiOutputSlots));
			if (node.constantFields) nodeData.constantFields = JSON.parse(JSON.stringify(node.constantFields));
			if (node.workflowType) nodeData.workflowType = node.workflowType;
			if (node.workflowIndex !== undefined) nodeData.workflowIndex = node.workflowIndex;
			if (node.color) nodeData.color = node.color;
			data.nodes.push(nodeData);
		}
		for (const linkId in this.links) { if (this.links.hasOwnProperty(linkId)) { const link = this.links[linkId]; data.links.push({ id: link.id, origin_id: link.origin_id, origin_slot: link.origin_slot, target_id: link.target_id, target_slot: link.target_slot, type: link.type }); } }
		if (includeCamera && camera) data.camera = { x: camera.x, y: camera.y, scale: camera.scale };
		return data;
	}

	deserialize(data, restoreCamera = false, camera = null) {
		this.nodes = []; this.links = {}; this._nodes_by_id = {}; this.last_link_id = 0;
		if (!data || !data.nodes) throw new Error('Invalid graph data');

		for (const nodeData of data.nodes) {
			let nodeTypeKey = nodeData.isNative ? 'Native.' + nodeData.type : (nodeData.schemaName && nodeData.modelName) ? nodeData.schemaName + '.' + nodeData.modelName : nodeData.type;
			if (!this.nodeTypes[nodeTypeKey]) { console.warn('Node type not found:', nodeTypeKey); continue; }

			const node = new (this.nodeTypes[nodeTypeKey])();
			node.id = nodeData.id; node.pos = nodeData.pos.slice(); node.size = nodeData.size.slice(); node.properties = JSON.parse(JSON.stringify(nodeData.properties || {}));
			if (nodeData.isRootType !== undefined) node.isRootType = nodeData.isRootType;
			if (nodeData.nativeInputs) node.nativeInputs = JSON.parse(JSON.stringify(nodeData.nativeInputs));
			if (nodeData.multiInputs) node.multiInputs = JSON.parse(JSON.stringify(nodeData.multiInputs));
			if (nodeData.multiInputSlots) node.multiInputSlots = JSON.parse(JSON.stringify(nodeData.multiInputSlots));
			if (nodeData.multiOutputSlots) node.multiOutputSlots = JSON.parse(JSON.stringify(nodeData.multiOutputSlots));
			if (nodeData.constantFields) node.constantFields = JSON.parse(JSON.stringify(nodeData.constantFields));
			if (nodeData.workflowType) node.workflowType = nodeData.workflowType;
			if (nodeData.workflowIndex !== undefined) node.workflowIndex = nodeData.workflowIndex;
			if (nodeData.color) node.color = nodeData.color;
			this.nodes.push(node); this._nodes_by_id[node.id] = node; node.graph = this;
		}

		if (data.links) {
			for (const linkData of data.links) {
				const originNode = this._nodes_by_id[linkData.origin_id], targetNode = this._nodes_by_id[linkData.target_id];
				if (originNode && targetNode) {
					const link = new Link(linkData.id, linkData.origin_id, linkData.origin_slot, linkData.target_id, linkData.target_slot, linkData.type);
					this.links[linkData.id] = link; originNode.outputs[linkData.origin_slot].links.push(linkData.id);
					if (targetNode.multiInputs && targetNode.multiInputs[linkData.target_slot]) targetNode.multiInputs[linkData.target_slot].links.push(linkData.id);
					else targetNode.inputs[linkData.target_slot].link = linkData.id;
					if (linkData.id > this.last_link_id) this.last_link_id = linkData.id;
				}
			}
		}

		if (restoreCamera && data.camera && camera) { camera.x = data.camera.x; camera.y = data.camera.y; camera.scale = data.camera.scale; }
		this.eventBus.emit('graph:deserialized', { nodeCount: this.nodes.length });
		return true;
	}
}

// ========================================================================
// CONTROLLERS
// ========================================================================

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

	handleMouseDown(e) { this.eventBus.emit('mouse:down', { button: e.button, coords: this.getCanvasCoordinates(e), event: e }); }
	handleMouseMove(e) { this.eventBus.emit('mouse:move', { coords: this.getCanvasCoordinates(e), event: e }); }
	handleMouseUp(e) { this.eventBus.emit('mouse:up', { button: e.button, coords: this.getCanvasCoordinates(e), event: e }); }
	handleDoubleClick(e) { this.eventBus.emit('mouse:dblclick', { coords: this.getCanvasCoordinates(e), event: e }); }
	handleWheel(e) { e.preventDefault(); this.eventBus.emit('mouse:wheel', { delta: e.deltaY, coords: this.getCanvasCoordinates(e), event: e }); }
	handleContextMenu(e) { e.preventDefault(); this.eventBus.emit('mouse:contextmenu', { coords: this.getCanvasCoordinates(e), event: e }); }

	getCanvasCoordinates(e) {
		const rect = this.canvas.getBoundingClientRect();
		return {
			screenX: ((e.clientX - rect.left) / rect.width) * this.canvas.width,
			screenY: ((e.clientY - rect.top) / rect.height) * this.canvas.height,
			clientX: e.clientX, clientY: e.clientY, rect
		};
	}
}

class KeyboardController {
	constructor(eventBus) {
		this.eventBus = eventBus;
		document.addEventListener('keydown', (e) => this.eventBus.emit('keyboard:down', { key: e.key, code: e.code, event: e }));
		document.addEventListener('keyup', (e) => this.eventBus.emit('keyboard:up', { key: e.key, code: e.code, event: e }));
	}
}

class VoiceController {
	constructor(eventBus) {
		this.eventBus = eventBus;
		this.recognition = null;
		this.isListening = false;
		if ('webkitSpeechRecognition' in window || 'SpeechRecognition' in window) {
			const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
			this.recognition = new SpeechRecognition();
			this.recognition.continuous = false;
			this.recognition.interimResults = false;
			this.recognition.onresult = (event) => this.eventBus.emit('voice:result', { transcript: event.results[0][0].transcript, confidence: event.results[0][0].confidence });
			this.recognition.onerror = (event) => this.eventBus.emit('voice:error', { error: event.error });
			this.recognition.onend = () => { this.isListening = false; this.eventBus.emit('voice:stopped', {}); };
		}
	}
	startListening() { if (this.recognition && !this.isListening) { this.recognition.start(); this.isListening = true; this.eventBus.emit('voice:started', {}); } }
	stopListening() { if (this.recognition && this.isListening) this.recognition.stop(); }
}

// ========================================================================
// DRAWING STYLE MANAGER
// ========================================================================

class DrawingStyleManager {
	constructor() {
		this.currentStyle = 'default';
		this.styles = {
			default: { name: 'Default', nodeCornerRadius: 6, nodeShadowBlur: 10, nodeShadowOffset: 2, linkWidth: 2.5, linkShadowBlur: 6, linkCurve: 0.5, slotRadius: 4, gridOpacity: 1.0, textFont: 'Arial, sans-serif', useGradient: false, useGlow: false, useDashed: false },
			minimal: { name: 'Minimal', nodeCornerRadius: 2, nodeShadowBlur: 0, nodeShadowOffset: 0, linkWidth: 1.5, linkShadowBlur: 0, linkCurve: 0.5, slotRadius: 3, gridOpacity: 0.3, textFont: 'Arial, sans-serif', useGradient: false, useGlow: false, useDashed: false },
			blueprint: { name: 'Blueprint', nodeCornerRadius: 0, nodeShadowBlur: 0, nodeShadowOffset: 0, linkWidth: 1.5, linkShadowBlur: 8, linkCurve: 0, slotRadius: 3, gridOpacity: 1.5, textFont: 'Courier New, monospace', useGradient: false, useGlow: true, useDashed: true },
			neon: { name: 'Neon', nodeCornerRadius: 8, nodeShadowBlur: 20, nodeShadowOffset: 0, linkWidth: 3, linkShadowBlur: 15, linkCurve: 0.6, slotRadius: 5, gridOpacity: 0.5, textFont: 'Arial, sans-serif', useGradient: true, useGlow: true, useDashed: false },
			organic: { name: 'Organic', nodeCornerRadius: 15, nodeShadowBlur: 12, nodeShadowOffset: 3, linkWidth: 4, linkShadowBlur: 8, linkCurve: 0.7, slotRadius: 6, gridOpacity: 0.7, textFont: 'Georgia, serif', useGradient: true, useGlow: false, useDashed: false },
			wireframe: { name: 'Wireframe', nodeCornerRadius: 0, nodeShadowBlur: 0, nodeShadowOffset: 0, linkWidth: 1, linkShadowBlur: 0, linkCurve: 0.5, slotRadius: 2, gridOpacity: 0.8, textFont: 'Courier New, monospace', useGradient: false, useGlow: false, useDashed: true }
		};
	}
	setStyle(styleName) { if (this.styles[styleName]) { this.currentStyle = styleName; localStorage.setItem('schemagraph-drawing-style', styleName); return true; } return false; }
	getStyle() { return this.styles[this.currentStyle]; }
	getCurrentStyleName() { return this.currentStyle; }
	loadSavedStyle() { const saved = localStorage.getItem('schemagraph-drawing-style'); if (saved && this.styles[saved]) this.currentStyle = saved; }
}

// ========================================================================
// SCHEMA GRAPH APP
// ========================================================================

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
		this.injectMultiSlotUIStyles();
		this.injectInteractiveStyles();

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
	}

	initializeState() {
		this.graph = new SchemaGraph(this.eventBus);
		this.extensions = extensionRegistry;
		this._drawUtils = DrawUtils;
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
		this.hoveredSlot = null;
		this.tooltipEl = null;

		this._hoveredAddButton = null;
		this._hoveredRemoveButton = null;
		this._editingMultiSlotNode = null;
		this._editingMultiSlotField = null;

		this.isLocked = false;
		this.lockReason = null;
		this.lockPending = null;
		this.lockInterval = null;

		this._hoveredButton = null;
		this._activeDropNode = null;
		this._callbackRegistry = {};
		this._decoratorParser = new NodeDecoratorParser();
		this._schemaDecorators = {};

		this._nodeTooltipsEnabled = true;
		this._fieldTooltipsEnabled = true;
		this._nodeHeaderTooltipEl = null;

		this.themes = ['dark', 'light', 'ocean'];
		this.currentThemeIndex = 0;
		this.loadTheme();

		this.drawingStyleManager = new DrawingStyleManager();
		this.drawingStyleManager.loadSavedStyle();

		this.textScalingMode = 'fixed';
		this.loadTextScalingMode();
	}

	// === LOCK METHODS ===
	lock(reason = 'Graph locked', pending = true) {
		this.lockReason = reason;
		if (!this.isLocked) {
			this.isLocked = true;
			this.connecting = null;
			this.selectionRect = null;
			this.selectionStart = null;
			this.editingNode = null;
			document.getElementById('sg-contextMenu')?.classList.remove('show');
			document.getElementById('sg-schemaDialog')?.classList.remove('show');
			this.canvas.classList.add('sg-locked');
		}
		if (pending) {
			this.lockPending = 0;
			this.lockInterval = setInterval(() => { this.lockPending = (this.lockPending + 1) % 3; this.draw(); }, 500);
		}
		this.eventBus.emit('graph:locked', { reason });
		this.draw();
	}

	unlock() {
		if (!this.isLocked) return;
		this.isLocked = false;
		this.lockReason = null;
		if (this.lockInterval) { clearInterval(this.lockInterval); this.lockInterval = null; this.lockPending = null; }
		this.canvas.classList.remove('sg-locked');
		this.eventBus.emit('graph:unlocked', {});
		this.draw();
	}

	isGraphLocked() { return this.isLocked; }

	// === HTML INJECTION ===
	injectDialogHTML() {
		if (document.getElementById('sg-messageDialog')) return;
		const messageDialog = document.createElement('div');
		messageDialog.id = 'sg-messageDialog';
		messageDialog.className = 'sg-dialog-overlay';
		messageDialog.innerHTML = `<div class="sg-dialog"><div class="sg-dialog-header" id="sg-messageDialogTitle">Message</div><div class="sg-dialog-body"><div id="sg-messageDialogContent"></div></div><div class="sg-dialog-footer"><button id="sg-messageDialogOk" class="sg-dialog-btn sg-dialog-btn-confirm">OK</button></div></div>`;
		document.body.appendChild(messageDialog);

		const confirmDialog = document.createElement('div');
		confirmDialog.id = 'sg-confirmDialog';
		confirmDialog.className = 'sg-dialog-overlay';
		confirmDialog.innerHTML = `<div class="sg-dialog"><div class="sg-dialog-header" id="sg-confirmDialogTitle">Confirm</div><div class="sg-dialog-body"><div id="sg-confirmDialogContent"></div></div><div class="sg-dialog-footer"><button id="sg-confirmDialogCancel" class="sg-dialog-btn sg-dialog-btn-cancel">Cancel</button><button id="sg-confirmDialogOk" class="sg-dialog-btn sg-dialog-btn-confirm">OK</button></div></div>`;
		document.body.appendChild(confirmDialog);
	}

	injectCanvasElementsHTML() {
		const canvasContainer = this.canvas.parentElement;
		if (!canvasContainer) return;

		if (!document.getElementById('sg-contextMenu')) {
			const contextMenu = document.createElement('div');
			contextMenu.id = 'sg-contextMenu';
			contextMenu.className = 'sg-context-menu';
			canvasContainer.appendChild(contextMenu);
		}

		if (!document.getElementById('sg-nodeInput')) {
			const nodeInput = document.createElement('input');
			nodeInput.type = 'text';
			nodeInput.id = 'sg-nodeInput';
			nodeInput.className = 'sg-node-input-overlay';
			canvasContainer.appendChild(nodeInput);
		}

		if (!document.getElementById('sg-schemaDialog')) {
			const schemaDialog = document.createElement('div');
			schemaDialog.id = 'sg-schemaDialog';
			schemaDialog.className = 'sg-dialog-overlay';
			schemaDialog.innerHTML = `<div class="sg-dialog"><div class="sg-dialog-header">Register Schema</div><div class="sg-dialog-body"><div class="sg-dialog-field"><label>Schema Name:</label><input type="text" id="sg-schemaNameInput" /></div><div class="sg-dialog-field"><label>Index Type:</label><input type="text" id="sg-schemaIndexTypeInput" placeholder="int" /></div><div class="sg-dialog-field"><label>Root Type:</label><input type="text" id="sg-schemaRootTypeInput" /></div></div><div class="sg-dialog-footer"><button id="sg-schemaDialogCancel" class="sg-dialog-btn sg-dialog-btn-cancel">Cancel</button><button id="sg-schemaDialogConfirm" class="sg-dialog-btn sg-dialog-btn-confirm">Register</button></div></div>`;
			document.body.appendChild(schemaDialog);
		}
	}

	injectToolbarHTML() {
		const canvasContainer = this.canvas.parentElement;
		if (!canvasContainer || document.getElementById('sg-toolbarToggle')) return;

		const toggleBtn = document.createElement('button');
		toggleBtn.id = 'sg-toolbarToggle';
		toggleBtn.className = 'sg-toolbar-toggle-corner';
		toggleBtn.title = 'Toggle toolbar';
		toggleBtn.innerHTML = '<span class="sg-toolbar-toggle-icon">⚙️</span>';

		const toolbarPanel = document.createElement('div');
		toolbarPanel.id = 'sg-toolbarPanel';
		toolbarPanel.className = 'sg-toolbar-panel';
		toolbarPanel.innerHTML = `
			<div class="sg-toolbar-header"><span class="sg-toolbar-title">⚙️ Toolbar</span><button id="sg-toolbarClose" class="sg-toolbar-close">✕</button></div>
			<div class="sg-toolbar-content" id="sg-toolbarContent">
				<div class="sg-toolbar-section"><span class="sg-toolbar-label">🎤 Voice</span><button id="sg-voiceStartBtn" class="sg-toolbar-btn">Start</button><button id="sg-voiceStopBtn" class="sg-toolbar-btn" style="display:none;">Stop</button><span id="sg-voiceStatus" class="sg-toolbar-status"></span></div>
				<div class="sg-toolbar-divider"></div>
				<div class="sg-toolbar-section"><button id="sg-analyticsToggleBtn" class="sg-toolbar-btn">📊 Analytics</button></div>
				<div class="sg-toolbar-divider"></div>
				<div class="sg-toolbar-section"><span class="sg-toolbar-label">Schema</span><button id="sg-uploadSchemaBtn" class="sg-toolbar-btn sg-toolbar-btn-primary">📤 Upload</button><button id="sg-exportBtn" class="sg-toolbar-btn">Export Graph</button><button id="sg-importBtn" class="sg-toolbar-btn">Import Graph</button><button id="sg-exportConfigBtn" class="sg-toolbar-btn">Export Config</button><button id="sg-importConfigBtn" class="sg-toolbar-btn">Import Config</button></div>
				<div class="sg-toolbar-divider"></div>
				<div class="sg-toolbar-section"><span class="sg-toolbar-label">Workflow</span><button id="sg-exportWorkflowBtn" class="sg-toolbar-btn">Export Workflow</button><button id="sg-importWorkflowBtn" class="sg-toolbar-btn">Import Workflow</button></div>
				<div class="sg-toolbar-divider"></div>
				<div class="sg-toolbar-section"><span class="sg-toolbar-label">View</span><button id="sg-centerViewBtn" class="sg-toolbar-btn">🎯 Center</button><select id="sg-layoutSelect" class="sg-toolbar-select"><option value="">🔧 Layout...</option><option value="hierarchical-vertical">Hierarchical ↓</option><option value="hierarchical-horizontal">Hierarchical →</option><option value="force-directed">Force-Directed</option><option value="grid">Grid</option><option value="circular">Circular</option></select></div>
				<div class="sg-toolbar-divider"></div>
				<div class="sg-toolbar-section"><span class="sg-toolbar-label">Style</span><select id="sg-drawingStyleSelect" class="sg-toolbar-select"><option value="default">🎨 Default</option><option value="minimal">✨ Minimal</option><option value="blueprint">📐 Blueprint</option><option value="neon">💫 Neon</option><option value="organic">🌿 Organic</option><option value="wireframe">📊 Wireframe</option></select><button id="sg-textScalingToggle" class="sg-toolbar-btn sg-toolbar-btn-toggle"><span class="sg-toolbar-toggle-label" id="sg-textScalingLabel">Text: Fixed</span></button><button id="sg-themeBtn" class="sg-toolbar-btn">🎨 Theme</button></div>
				<div class="sg-toolbar-divider"></div>
				<div class="sg-toolbar-section"><span class="sg-toolbar-label">Zoom</span><span class="sg-toolbar-zoom-value" id="sg-zoomLevel">100%</span><button id="sg-resetZoomBtn" class="sg-toolbar-btn">⟲</button></div>
			</div>`;

		canvasContainer.appendChild(toggleBtn);
		canvasContainer.appendChild(toolbarPanel);

		const closeBtn = document.getElementById('sg-toolbarClose');
		const showToolbar = () => { toolbarPanel.classList.add('show'); toggleBtn.classList.add('active'); };
		const hideToolbar = () => { toolbarPanel.classList.add('hiding'); toggleBtn.classList.remove('active'); setTimeout(() => toolbarPanel.classList.remove('show', 'hiding'), 300); };

		toggleBtn.addEventListener('click', (e) => { e.stopPropagation(); toolbarPanel.classList.contains('show') ? hideToolbar() : showToolbar(); });
		closeBtn?.addEventListener('click', (e) => { e.stopPropagation(); hideToolbar(); });
		document.addEventListener('click', (e) => { if (toolbarPanel.classList.contains('show') && !toolbarPanel.contains(e.target) && !toggleBtn.contains(e.target) && !e.target.closest('.sg-dialog-overlay') && !e.target.closest('#sg-analyticsPanel')) hideToolbar(); });

		const hiddenInputs = document.createElement('div');
		hiddenInputs.style.display = 'none';
		hiddenInputs.innerHTML = `<input type="file" id="sg-uploadSchemaFile" accept=".py" /><input type="file" id="sg-importFile" accept=".json" /><input type="file" id="sg-importConfigFile" accept=".json" /><input type="file" id="sg-importWorkflowFile" accept=".json" />`;
		document.body.appendChild(hiddenInputs);
	}

	injectAnalyticsPanelHTML() {
		if (document.getElementById('sg-analyticsPanel')) return;
		const panel = document.createElement('div');
		panel.id = 'sg-analyticsPanel';
		panel.className = 'sg-analytics-panel';
		panel.innerHTML = `
			<div class="sg-analytics-header"><div class="sg-analytics-title">📊 Analytics</div><button id="sg-analyticsCloseBtn" class="sg-analytics-close">✕</button></div>
			<div class="sg-analytics-section"><div class="sg-analytics-metric"><span>Session ID:</span><span id="sg-sessionId">-</span></div><div class="sg-analytics-metric"><span>Duration:</span><span id="sg-sessionDuration">-</span></div><div class="sg-analytics-metric"><span>Events:</span><span id="sg-totalEvents">-</span></div></div>
			<div class="sg-analytics-section"><div class="sg-analytics-metric"><span>Nodes Created:</span><span id="sg-nodesCreated">0</span></div><div class="sg-analytics-metric"><span>Nodes Deleted:</span><span id="sg-nodesDeleted">0</span></div><div class="sg-analytics-metric"><span>Links Created:</span><span id="sg-linksCreated">0</span></div><div class="sg-analytics-metric"><span>Links Deleted:</span><span id="sg-linksDeleted">0</span></div></div>
			<button id="sg-refreshAnalyticsBtn" class="sg-analytics-btn">🔄 Refresh</button><button id="sg-exportAnalyticsBtn" class="sg-analytics-btn">💾 Export</button>`;
		document.body.appendChild(panel);
	}

	injectMultiSlotUIStyles() {
		if (document.getElementById('sg-multislot-ui-styles')) return;
		
		const style = document.createElement('style');
		style.id = 'sg-multislot-ui-styles';
		style.textContent = `
			/* Input/Confirm Dialog */
			.sg-input-dialog-overlay {
				position: fixed;
				top: 0;
				left: 0;
				right: 0;
				bottom: 0;
				background: rgba(0, 0, 0, 0.6);
				z-index: 10000;
				display: flex;
				align-items: center;
				justify-content: center;
			}
			
			.sg-input-dialog {
				background: var(--sg-bg-secondary, #252540);
				border: 1px solid var(--sg-border-color, #404060);
				border-radius: 8px;
				min-width: 300px;
				max-width: 400px;
				box-shadow: 0 8px 32px rgba(0,0,0,0.5);
				animation: sg-dialog-appear 0.15s ease-out;
			}
			
			@keyframes sg-dialog-appear {
				from { opacity: 0; transform: scale(0.95); }
				to { opacity: 1; transform: scale(1); }
			}
			
			.sg-input-dialog-header {
				display: flex;
				justify-content: space-between;
				align-items: center;
				padding: 12px 16px;
				border-bottom: 1px solid var(--sg-border-color, #404060);
				background: var(--sg-node-header, #404060);
				border-radius: 8px 8px 0 0;
			}
			
			.sg-input-dialog-title {
				font-weight: 600;
				color: var(--sg-text-primary, #ffffff);
				font-size: 14px;
			}
			
			.sg-input-dialog-close {
				background: none;
				border: none;
				color: var(--sg-text-tertiary, #808090);
				font-size: 20px;
				cursor: pointer;
				padding: 0;
				width: 24px;
				height: 24px;
				display: flex;
				align-items: center;
				justify-content: center;
				border-radius: 4px;
				line-height: 1;
			}
			
			.sg-input-dialog-close:hover {
				background: rgba(255,255,255,0.1);
				color: var(--sg-text-primary, #ffffff);
			}
			
			.sg-input-dialog-body {
				padding: 16px;
			}
			
			.sg-input-dialog-label {
				display: block;
				color: var(--sg-text-secondary, #b0b0c0);
				font-size: 13px;
				margin-bottom: 8px;
			}
			
			.sg-input-dialog-input {
				width: 100%;
				background: var(--sg-canvas-bg, #1a1a2e);
				border: 1px solid var(--sg-border-color, #404060);
				border-radius: 4px;
				padding: 10px 12px;
				color: var(--sg-text-primary, #ffffff);
				font-size: 14px;
				font-family: 'Monaco', 'Menlo', monospace;
				box-sizing: border-box;
			}
			
			.sg-input-dialog-input:focus {
				outline: none;
				border-color: var(--sg-border-highlight, #46a2da);
				box-shadow: 0 0 0 2px rgba(70, 162, 218, 0.3);
			}
			
			.sg-input-dialog-input::placeholder {
				color: var(--sg-text-tertiary, #808090);
			}
			
			.sg-confirm-dialog-message {
				color: var(--sg-text-secondary, #b0b0c0);
				font-size: 14px;
				margin: 0;
				line-height: 1.5;
			}
			
			.sg-input-dialog-footer {
				display: flex;
				justify-content: flex-end;
				gap: 8px;
				padding: 12px 16px;
				border-top: 1px solid var(--sg-border-color, #404060);
				background: rgba(0,0,0,0.2);
				border-radius: 0 0 8px 8px;
			}
			
			.sg-input-dialog-btn {
				padding: 8px 16px;
				border-radius: 4px;
				font-size: 13px;
				font-weight: 500;
				cursor: pointer;
				border: 1px solid transparent;
				transition: all 0.15s;
			}
			
			.sg-input-dialog-cancel {
				background: rgba(255,255,255,0.1);
				color: var(--sg-text-secondary, #b0b0c0);
				border-color: var(--sg-border-color, #404060);
			}
			
			.sg-input-dialog-cancel:hover {
				background: rgba(255,255,255,0.15);
				color: var(--sg-text-primary, #ffffff);
			}
			
			.sg-input-dialog-confirm {
				background: var(--sg-border-highlight, #46a2da);
				color: #ffffff;
			}
			
			.sg-input-dialog-confirm:hover {
				background: #5bb0e5;
			}
			
			.sg-input-dialog-confirm.sg-confirm-danger {
				background: var(--sg-accent-red, #dc6068);
			}
			
			.sg-input-dialog-confirm.sg-confirm-danger:hover {
				background: #e57078;
			}
			
			/* Slot Manager Modal */
			.sg-slot-manager-overlay {
				position: fixed;
				top: 0;
				left: 0;
				right: 0;
				bottom: 0;
				background: rgba(0, 0, 0, 0.6);
				z-index: 10000;
				display: flex;
				align-items: center;
				justify-content: center;
			}
			
			.sg-slot-manager {
				background: var(--sg-bg-secondary, #252540);
				border: 1px solid var(--sg-border-color, #404060);
				border-radius: 8px;
				min-width: 320px;
				max-width: 480px;
				max-height: 80vh;
				display: flex;
				flex-direction: column;
				box-shadow: 0 8px 32px rgba(0,0,0,0.5);
			}
			
			.sg-slot-manager-header {
				display: flex;
				justify-content: space-between;
				align-items: center;
				padding: 12px 16px;
				border-bottom: 1px solid var(--sg-border-color, #404060);
				background: var(--sg-node-header, #404060);
				border-radius: 8px 8px 0 0;
			}
			
			.sg-slot-manager-title {
				font-weight: 600;
				color: var(--sg-text-primary, #ffffff);
				font-size: 14px;
			}
			
			.sg-slot-manager-close {
				background: none;
				border: none;
				color: var(--sg-text-tertiary, #808090);
				font-size: 20px;
				cursor: pointer;
				padding: 0;
				width: 24px;
				height: 24px;
				display: flex;
				align-items: center;
				justify-content: center;
				border-radius: 4px;
			}
			
			.sg-slot-manager-close:hover {
				background: rgba(255,255,255,0.1);
				color: var(--sg-text-primary, #ffffff);
			}
			
			.sg-slot-manager-body {
				padding: 16px;
				overflow-y: auto;
				flex: 1;
			}
			
			.sg-slot-manager-list {
				display: flex;
				flex-direction: column;
				gap: 8px;
			}
			
			.sg-slot-item {
				display: flex;
				align-items: center;
				gap: 8px;
				padding: 8px 12px;
				background: rgba(0,0,0,0.2);
				border: 1px solid var(--sg-border-color, #404060);
				border-radius: 6px;
			}
			
			.sg-slot-item-key {
				flex: 1;
				background: var(--sg-canvas-bg, #1a1a2e);
				border: 1px solid var(--sg-border-color, #404060);
				border-radius: 4px;
				padding: 6px 10px;
				color: var(--sg-text-primary, #ffffff);
				font-size: 13px;
				font-family: 'Monaco', 'Menlo', monospace;
			}
			
			.sg-slot-item-key:focus {
				outline: none;
				border-color: var(--sg-border-highlight, #46a2da);
			}
			
			.sg-slot-item-connected {
				font-size: 10px;
				color: var(--sg-accent-green, #50c878);
				padding: 2px 6px;
				background: rgba(80, 200, 120, 0.15);
				border-radius: 3px;
			}
			
			.sg-slot-item-btn {
				background: none;
				border: none;
				color: var(--sg-text-tertiary, #808090);
				font-size: 14px;
				cursor: pointer;
				padding: 4px;
				border-radius: 4px;
				display: flex;
				align-items: center;
				justify-content: center;
			}
			
			.sg-slot-item-btn:hover {
				background: rgba(255,255,255,0.1);
				color: var(--sg-text-primary, #ffffff);
			}
			
			.sg-slot-item-btn.delete:hover {
				background: rgba(220, 96, 104, 0.2);
				color: var(--sg-accent-red, #dc6068);
			}
			
			.sg-slot-item-btn:disabled {
				opacity: 0.3;
				cursor: not-allowed;
			}
			
			.sg-slot-manager-footer {
				display: flex;
				justify-content: space-between;
				align-items: center;
				padding: 12px 16px;
				border-top: 1px solid var(--sg-border-color, #404060);
				background: rgba(0,0,0,0.2);
				border-radius: 0 0 8px 8px;
			}
			
			.sg-slot-add-row {
				display: flex;
				gap: 8px;
				flex: 1;
			}
			
			.sg-slot-add-input {
				flex: 1;
				background: var(--sg-canvas-bg, #1a1a2e);
				border: 1px solid var(--sg-border-color, #404060);
				border-radius: 4px;
				padding: 8px 12px;
				color: var(--sg-text-primary, #ffffff);
				font-size: 13px;
			}
			
			.sg-slot-add-input:focus {
				outline: none;
				border-color: var(--sg-border-highlight, #46a2da);
			}
			
			.sg-slot-add-input::placeholder {
				color: var(--sg-text-tertiary, #808090);
			}
			
			.sg-slot-add-btn {
				background: var(--sg-border-highlight, #46a2da);
				border: none;
				color: #ffffff;
				padding: 8px 16px;
				border-radius: 4px;
				cursor: pointer;
				font-size: 13px;
				font-weight: 500;
			}
			
			.sg-slot-add-btn:hover {
				background: #5bb0e5;
			}
			
			.sg-slot-empty {
				text-align: center;
				color: var(--sg-text-tertiary, #808090);
				padding: 20px;
				font-style: italic;
			}
		`;
		
		document.head.appendChild(style);
	}

	injectInteractiveStyles() {
		if (document.getElementById('sg-interactive-styles')) return;
		const style = document.createElement('style');
		style.id = 'sg-interactive-styles';
		style.textContent = `
			.sg-file-drag-over { outline: 3px dashed #92d050 !important; outline-offset: -3px; }
			
			/* Field Tooltip */
			.sg-tooltip {
				position: fixed;
				z-index: 10000;
				background: var(--sg-node-bg, #252540);
				border: 1px solid var(--sg-border-color, #404060);
				border-radius: 6px;
				padding: 8px 12px;
				max-width: 280px;
				box-shadow: 0 4px 16px rgba(0,0,0,0.4);
				pointer-events: none;
				font-size: 12px;
				color: var(--sg-text-primary, #fff);
			}
			
			.sg-tooltip-title {
				font-weight: 600;
				color: var(--sg-text-primary, #fff);
				margin-bottom: 4px;
			}
			
			.sg-tooltip-desc {
				color: var(--sg-text-secondary, #b0b0c0);
				margin-bottom: 6px;
				line-height: 1.4;
			}
			
			.sg-tooltip-field {
				font-family: 'Monaco', 'Menlo', monospace;
				font-size: 11px;
				color: var(--sg-text-tertiary, #808090);
				margin-bottom: 4px;
			}
			
			.sg-tooltip-type {
				font-family: 'Monaco', 'Menlo', monospace;
				font-size: 10px;
				color: var(--sg-accent-purple, #9370db);
				background: rgba(147, 112, 219, 0.15);
				padding: 2px 6px;
				border-radius: 3px;
				display: inline-block;
				margin-right: 4px;
			}
			
			.sg-tooltip-badge {
				font-size: 10px;
				padding: 2px 6px;
				border-radius: 3px;
				display: inline-block;
				margin-right: 4px;
			}
			
			.sg-tooltip-badge.multi {
				background: rgba(147, 112, 219, 0.2);
				color: var(--sg-accent-purple, #9370db);
			}
			
			.sg-tooltip-badge.required {
				background: rgba(220, 96, 104, 0.2);
				color: var(--sg-accent-red, #dc6068);
			}
			
			.sg-tooltip-badge.optional {
				background: rgba(80, 200, 120, 0.2);
				color: var(--sg-accent-green, #50c878);
			}
			
			/* Node Header Tooltip */
			.sg-node-tooltip {
				position: fixed;
				z-index: 10000;
				background: var(--sg-node-bg, #252540);
				border: 1px solid var(--sg-border-color, #404060);
				border-radius: 8px;
				padding: 10px 14px;
				max-width: 320px;
				box-shadow: 0 6px 20px rgba(0,0,0,0.5);
				pointer-events: none;
				font-size: 12px;
				color: var(--sg-text-primary, #fff);
			}
			
			.sg-node-tooltip-header {
				display: flex;
				align-items: center;
				gap: 8px;
				margin-bottom: 6px;
			}
			
			.sg-node-tooltip-icon {
				font-size: 18px;
			}
			
			.sg-node-tooltip-title {
				font-weight: 600;
				font-size: 14px;
				color: var(--sg-text-primary, #fff);
			}
			
			.sg-node-tooltip-desc {
				color: var(--sg-text-secondary, #b0b0c0);
				line-height: 1.5;
			}
			
			.sg-node-tooltip-section {
				margin-top: 6px;
				font-size: 10px;
				color: var(--sg-text-tertiary, #808090);
				text-transform: uppercase;
				letter-spacing: 0.5px;
			}
			
			.sg-node-tooltip-meta {
				margin-top: 8px;
				padding-top: 8px;
				border-top: 1px solid var(--sg-border-color, #404060);
				font-size: 11px;
			}

			.sg-node-tooltip-meta-item {
				display: flex;
				gap: 6px;
				margin-bottom: 3px;
				color: var(--sg-text-secondary, #b0b0c0);
			}

			.sg-node-tooltip-meta-label {
				color: var(--sg-text-tertiary, #808090);
				min-width: 50px;
			}

			.sg-node-tooltip-incomplete {
				color: var(--sg-accent-red, #dc6068) !important;
			}

			.sg-node-tooltip-complete {
				color: var(--sg-accent-green, #50c878) !important;
			}

			.sg-node-tooltip-badge-row {
				margin-top: 6px;
			}

			.sg-node-tooltip-type-badge {
				font-size: 9px;
				padding: 2px 6px;
				border-radius: 3px;
				text-transform: uppercase;
				letter-spacing: 0.5px;
			}

			.sg-node-tooltip-type-badge.native {
				background: rgba(147, 112, 219, 0.2);
				color: var(--sg-accent-purple, #9370db);
			}

			.sg-node-tooltip-type-badge.root {
				background: rgba(245, 166, 35, 0.2);
				color: var(--sg-accent-orange, #f5a623);
			}
		`;
		document.head.appendChild(style);
	}

	// === EVENT SETUP ===
	setupEventListeners() {
		this.eventBus.on('mouse:down', (data) => this.handleMouseDown(data));
		this.eventBus.on('mouse:move', (data) => this.handleMouseMove(data));
		this.eventBus.on('mouse:up', (data) => this.handleMouseUp(data));
		this.eventBus.on('mouse:dblclick', (data) => this.handleDoubleClick(data));
		this.eventBus.on('mouse:wheel', (data) => this.handleWheel(data));
		this.eventBus.on('mouse:contextmenu', (data) => this.handleContextMenu(data));
		this.eventBus.on('keyboard:down', (data) => this.handleKeyDown(data));
		this.eventBus.on('keyboard:up', (data) => this.handleKeyUp(data));

		this.eventBus.on('node:created', () => { this.ui?.update?.schemaList?.(); this.ui?.update?.nodeTypesList?.(); this.draw(); });
		this.eventBus.on('node:deleted', () => { this.ui?.update?.schemaList?.(); this.draw(); });
		this.eventBus.on('link:created', () => this.draw());
		this.eventBus.on('link:deleted', () => this.draw());
		this.eventBus.on('schema:registered', () => { this.ui?.update?.schemaList?.(); this.ui?.update?.nodeTypesList?.(); this.draw(); });
		this.eventBus.on('schema:removed', () => { this.ui?.update?.schemaList?.(); this.ui?.update?.nodeTypesList?.(); this.draw(); });

		const nodeInput = document.getElementById('sg-nodeInput');
		nodeInput?.addEventListener('blur', () => this.handleInputBlur());
		nodeInput?.addEventListener('keydown', (e) => this.handleInputKeyDown(e));

		this._setupFileDrop();

		this.extensions.initAll(this);
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

	setupVoiceCommands() {
		this.eventBus.on('voice:result', (data) => {
			const transcript = data.transcript.toLowerCase().trim();
			if (transcript.includes('create') && transcript.includes('string')) this.executeVoiceCommand('create', 'Native.String');
			else if (transcript.includes('delete') && this.selectedNode) this.executeVoiceCommand('delete');
			else if (transcript.includes('center')) this.executeVoiceCommand('center-view');
			else if (transcript.includes('theme')) this.executeVoiceCommand('cycle-theme');
		});
	}

	executeVoiceCommand(command, param = null) {
		switch (command) {
			case 'create':
				if (param && this.graph.nodeTypes[param]) {
					const node = this.graph.createNode(param);
					const centerX = (-this.camera.x + this.canvas.width / 2) / this.camera.scale;
					const centerY = (-this.camera.y + this.canvas.height / 2) / this.camera.scale;
					node.pos = [centerX - 90, centerY - 40];
					this.draw();
				}
				break;
			case 'delete': if (this.selectedNode) this.removeNode(this.selectedNode); break;
			case 'center-view': this.centerView(); break;
			case 'cycle-theme': this.cycleTheme(); break;
		}
	}

	// === THEME & SETTINGS ===
	loadTheme() {
		const saved = localStorage.getItem('schemagraph-theme') || 'dark';
		this.currentThemeIndex = this.themes.indexOf(saved);
		if (this.currentThemeIndex === -1) this.currentThemeIndex = 0;
		this.applyTheme(this.themes[this.currentThemeIndex]);
	}

	applyTheme(theme) {
		if (theme === 'dark') document.documentElement.removeAttribute('data-theme');
		else document.documentElement.setAttribute('data-theme', theme);
	}

	cycleTheme() {
		this.currentThemeIndex = (this.currentThemeIndex + 1) % this.themes.length;
		const newTheme = this.themes[this.currentThemeIndex];
		this.applyTheme(newTheme);
		localStorage.setItem('schemagraph-theme', newTheme);
		this.draw();
	}

	loadTextScalingMode() {
		const saved = localStorage.getItem('schemagraph-text-scaling');
		if (saved === 'scaled' || saved === 'fixed') this.textScalingMode = saved;
	}

	saveTextScalingMode() { localStorage.setItem('schemagraph-text-scaling', this.textScalingMode); }
	getTextScale() { return this.textScalingMode === 'fixed' ? (1 / this.camera.scale) : 1; }

	registerNativeNodes() {
		const nativeNodes = [
			{ name: 'String', type: 'str', defaultValue: '', parser: (v) => v },
			{ name: 'Integer', type: 'int', defaultValue: 0, parser: (v) => parseInt(v) || 0 },
			{ name: 'Boolean', type: 'bool', defaultValue: false, parser: (v) => v === true || v === 'true' },
			{ name: 'Float', type: 'float', defaultValue: 0.0, parser: (v) => parseFloat(v) || 0.0 },
			{ name: 'List', type: 'List[Any]', defaultValue: '[]', parser: (v) => { try { return JSON.parse(v); } catch { return []; } } },
			{ name: 'Dict', type: 'Dict[str,Any]', defaultValue: '{}', parser: (v) => { try { return JSON.parse(v); } catch { return {}; } } }
		];

		for (const spec of nativeNodes) {
			const self = this;
			class NativeNode extends Node {
				constructor() {
					super(spec.name);
					this.addOutput('value', spec.type);
					this.properties.value = spec.defaultValue;
					this.size = [180, 80];
					this.isNative = true;
				}
				onExecute() { this.setOutputData(0, spec.parser(this.properties.value)); }
			}
			this.graph.nodeTypes['Native.' + spec.name] = NativeNode;
		}
	}

	// === SELECTION ===
	selectNode(node, addToSelection = false) {
		const prevSelection = new Set(this.selectedNodes);
		
		if (!addToSelection) this.selectedNodes.clear();
		if (node) { 
			this.selectedNodes.add(node); 
			this.selectedNode = node;
			
			if (!prevSelection.has(node)) {
				this.eventBus.emit(GraphEvents.NODE_SELECTED, { nodeId: node.id, node });
			}
		}
		
		// Emit deselection for nodes no longer selected
		prevSelection.forEach(n => {
			if (!this.selectedNodes.has(n)) {
				this.eventBus.emit(GraphEvents.NODE_DESELECTED, { nodeId: n.id, node: n });
			}
		});
		
		this.eventBus.emit(GraphEvents.SELECTION_CHANGED, {
			selectedNodes: Array.from(this.selectedNodes).map(n => n.id)
		});
		
		this.draw();
	}

	deselectNode(node) {
		this.selectedNodes.delete(node);
		if (this.selectedNode === node) this.selectedNode = this.selectedNodes.size > 0 ? Array.from(this.selectedNodes)[this.selectedNodes.size - 1] : null;
		this.draw();
	}

	toggleNodeSelection(node) { this.selectedNodes.has(node) ? this.deselectNode(node) : this.selectNode(node, true); }
	isNodeSelected(node) { return this.selectedNodes.has(node); }
	deleteSelectedNodes() { for (const node of Array.from(this.selectedNodes)) this.removeNode(node); this.clearSelection(); }

	clearSelection() {
		const hadSelection = this.selectedNodes.size > 0;
		this.selectedNodes.clear(); 
		this.selectedNode = null; 
		
		if (hadSelection) {
			this.eventBus.emit(GraphEvents.SELECTION_CLEARED, {});
			this.eventBus.emit(GraphEvents.SELECTION_CHANGED, { selectedNodes: [] });
		}
		
		this.draw();
	}

	// === MOUSE HANDLERS ===
	handleMouseDown(data) {
		this.isMouseDown = true;
		document.getElementById('sg-contextMenu')?.classList.remove('show');

		const [wx, wy] = this.screenToWorld(data.coords.screenX, data.coords.screenY);

		// Handle multi-slot button clicks
		if (data.button === 0 && !this.isLocked) {
			if (this._hoveredAddButton) {
				data.event.preventDefault();
				this._handleMultiSlotAddClick(this._hoveredAddButton);
				return;
			}
			
			if (this._hoveredRemoveButton) {
				data.event.preventDefault();
				this._handleMultiSlotRemoveClick(this._hoveredRemoveButton);
				return;
			}

			for (const node of this.graph.nodes) {
				const layout = this._getButtonStackLayout(node);
				for (const stack of [layout.top, layout.bottom]) {
					if (!stack) continue;
					for (const { btn, bounds } of stack.buttons) {
						if (wx >= bounds.x && wx <= bounds.x + bounds.w && wy >= bounds.y && wy <= bounds.y + bounds.h) {
							if (btn.enabled && btn.callback) {
								data.event.preventDefault();
								btn.callback(node, data.event, btn);
								return;
							}
						}
					}
				}
			}
		}

		if (data.button === 1 || (data.button === 0 && this.spacePressed)) {
			data.event.preventDefault();
			this.isPanning = true;
			this.panStart = [data.coords.screenX - this.camera.x, data.coords.screenY - this.camera.y];
			this.canvas.style.cursor = 'grabbing';
			return;
		}

		if (data.button !== 0 || this.spacePressed) return;

		if (!this.isLocked) {
			for (const node of this.graph.nodes) {
				for (let j = 0; j < node.outputs.length; j++) {
					const slotY = node.pos[1] + 30 + j * 25;
					if (Math.sqrt(Math.pow(wx - (node.pos[0] + node.size[0]), 2) + Math.pow(wy - slotY, 2)) < 10) {
						this.connecting = { node, slot: j, isOutput: true };
						this.canvas.classList.add('connecting');
						return;
					}
				}
			}

			for (const node of this.graph.nodes) {
				for (let j = 0; j < node.inputs.length; j++) {
					const slotY = node.pos[1] + 30 + j * 25;
					if (Math.sqrt(Math.pow(wx - node.pos[0], 2) + Math.pow(wy - slotY, 2)) < 10) {
						if (!node.multiInputs?.[j] && node.inputs[j].link) this.removeLink(node.inputs[j].link, node, j);
						this.connecting = { node, slot: j, isOutput: false };
						this.canvas.classList.add('connecting');
						return;
					}
				}
			}
		}

		let clickedNode = null;
		for (let i = this.graph.nodes.length - 1; i >= 0; i--) {
			const node = this.graph.nodes[i];
			if (wx >= node.pos[0] && wx <= node.pos[0] + node.size[0] && wy >= node.pos[1] && wy <= node.pos[1] + node.size[1]) {
				clickedNode = node;
				break;
			}
		}

		if (clickedNode) {
			if (data.event.ctrlKey || data.event.metaKey) this.toggleNodeSelection(clickedNode);
			else {
				if (!this.selectedNodes.has(clickedNode)) this.selectNode(clickedNode, false);
				this.dragNode = clickedNode;
				this.dragOffset = [wx - clickedNode.pos[0], wy - clickedNode.pos[1]];
				this.canvas.classList.add('dragging');
			}
			return;
		}

		if (!data.event.ctrlKey && !data.event.metaKey) this.clearSelection();
		this.selectionStart = [wx, wy];
	}

	handleMouseMove(data) {
		this.mousePos = [data.coords.screenX, data.coords.screenY];
		
		if (this.isPanning) {
			this.camera.x = data.coords.screenX - this.panStart[0];
			this.camera.y = data.coords.screenY - this.panStart[1];
			this._hideTooltip();
			this.draw();
			return;
		}
		
		if (this.dragNode && !this.connecting) {
			const [wx, wy] = this.screenToWorld(data.coords.screenX, data.coords.screenY);
			const dx = wx - this.dragOffset[0] - this.dragNode.pos[0];
			const dy = wy - this.dragOffset[1] - this.dragNode.pos[1];
			for (const node of this.selectedNodes) { 
				node.pos[0] += dx; 
				node.pos[1] += dy; 
			}
			this._hideTooltip();
			this.draw();
			return;
		}
		
		if (this.connecting) {
			this._hideTooltip();
			this.draw();
			return;
		}
		
		if (this.selectionStart && this.isMouseDown) {
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
					if (!(node.pos[0] > this.selectionRect.x + this.selectionRect.w || 
						node.pos[0] + node.size[0] < this.selectionRect.x || 
						node.pos[1] > this.selectionRect.y + this.selectionRect.h || 
						node.pos[1] + node.size[1] < this.selectionRect.y)) {
						this.previewSelection.add(node);
					}
				}
			}
			this._hideTooltip();
			this.draw();
			return;
		}
		
		// ================================================================
		// IDLE STATE - Check multi-slot buttons and tooltips
		// ================================================================
		
		const [wx, wy] = this.screenToWorld(data.coords.screenX, data.coords.screenY);
		
		// --- Multi-slot button hover detection ---
		let foundAdd = null;
		let foundRemove = null;
		
		for (const node of this.graph.nodes) {
			if (!node.isWorkflowNode) continue;
			
			const addButtons = this._getMultiSlotAddButtons(node);
			for (const btn of addButtons) {
				if (this._isPointInButton(wx, wy, btn)) {
					foundAdd = { nodeId: node.id, ...btn };
					break;
				}
			}
			
			if (!foundAdd) {
				const removeButtons = this._getMultiSlotRemoveButtons(node);
				for (const btn of removeButtons) {
					if (this._isPointInButton(wx, wy, btn)) {
						foundRemove = { nodeId: node.id, ...btn };
						break;
					}
				}
			}
			
			if (foundAdd || foundRemove) break;
		}
		
		const multiSlotChanged = (
			this._hoveredAddButton?.nodeId !== foundAdd?.nodeId ||
			this._hoveredAddButton?.fieldName !== foundAdd?.fieldName ||
			this._hoveredRemoveButton?.nodeId !== foundRemove?.nodeId ||
			this._hoveredRemoveButton?.key !== foundRemove?.key
		);
		
		this._hoveredAddButton = foundAdd;
		this._hoveredRemoveButton = foundRemove;
		
		// Set cursor for multi-slot buttons
		if (foundAdd || foundRemove) {
			this.canvas.style.cursor = 'pointer';
			this._hideTooltip();
			this.draw();
			return;
		}

		// Button hover detection
		let foundButton = null;
		for (const node of this.graph.nodes) {
			const layout = this._getButtonStackLayout(node);
			for (const stack of [layout.top, layout.bottom]) {
				if (!stack) continue;
				for (const { btn, bounds } of stack.buttons) {
					if (wx >= bounds.x && wx <= bounds.x + bounds.w && wy >= bounds.y && wy <= bounds.y + bounds.h) {
						if (btn.enabled && btn.visible) {
							foundButton = { nodeId: node.id, buttonId: btn.id };
							break;
						}
					}
				}
				if (foundButton) break;
			}
			if (foundButton) break;
		}

		if (this._hoveredButton?.buttonId !== foundButton?.buttonId || this._hoveredButton?.nodeId !== foundButton?.nodeId) {
			this._hoveredButton = foundButton;
			if (foundButton) {
				this.canvas.style.cursor = 'pointer';
				this._hideTooltip();
				this.draw();
				return;
			}
		}

		// --- Tooltip hover detection for slots ---
		let foundSlot = false;
		let foundNodeHeader = null;

		for (const node of this.graph.nodes) {
			const x = node.pos[0];
			const y = node.pos[1];
			const w = node.size[0];
			
			// Check node header hover (for node tooltip)
			if (wx >= x && wx <= x + w && wy >= y && wy <= y + 26) {
				foundNodeHeader = node;
			}
			
			// Check input slots
			for (let j = 0; j < node.inputs.length; j++) {
				const slotY = y + 38 + j * 25;
				
				const hasEditBox = !node.multiInputs?.[j] && !node.inputs[j].link && node.nativeInputs?.[j] !== undefined;
				
				const hitLeft = x - 10;
				const hitRight = x + (hasEditBox ? 85 : 100);
				const hitTop = slotY - 10;
				const hitBottom = hasEditBox ? slotY + 20 : slotY + 10;
				
				if (wx >= hitLeft && wx <= hitRight && wy >= hitTop && wy <= hitBottom) {
					const meta = node.inputMeta?.[j];
					if (meta) {
						const isRequired = this._isFieldRequired(node, j);
						this._showTooltip(data.coords.clientX, data.coords.clientY, meta, isRequired);
						foundSlot = true;
						break;
					}
				}
			}
			
			if (foundSlot) break;
			
			// Check output slots
			for (let j = 0; j < node.outputs.length; j++) {
				const slotY = y + 38 + j * 25;
				
				const hitLeft = x + w - 100;
				const hitRight = x + w + 10;
				const hitTop = slotY - 10;
				const hitBottom = slotY + 10;
				
				if (wx >= hitLeft && wx <= hitRight && wy >= hitTop && wy <= hitBottom) {
					const meta = node.outputMeta?.[j];
					if (meta) {
						this._showTooltip(data.coords.clientX, data.coords.clientY, meta, false);
						foundSlot = true;
						break;
					}
				}
			}
			
			if (foundSlot) break;
		}

		if (!foundSlot) {
			this._hideTooltip();
		}

		// Node header tooltip
		if (foundNodeHeader && !foundSlot) {
			this._showNodeHeaderTooltip(data.coords.clientX, data.coords.clientY, foundNodeHeader);
		} else {
			this._hideNodeHeaderTooltip();
		}

		// Reset cursor if not on any interactive element
		this.canvas.style.cursor = 'default';
		
		this.draw();
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
						if (Math.sqrt(Math.pow(wx - node.pos[0], 2) + Math.pow(wy - slotY, 2)) < 15 && node !== this.connecting.node) {
							if (!this.isSlotCompatible(node, j, false)) { this.showError('Type mismatch'); break; }
							if (node.multiInputs?.[j]) {
								const linkId = ++this.graph.last_link_id;
								const link = new Link(linkId, this.connecting.node.id, this.connecting.slot, node.id, j, this.connecting.node.outputs[this.connecting.slot].type);
								this.graph.links[linkId] = link;
								this.connecting.node.outputs[this.connecting.slot].links.push(linkId);
								node.multiInputs[j].links.push(linkId);
								this.eventBus.emit('link:created', { linkId });
							} else {
								if (node.inputs[j].link) this.removeLink(node.inputs[j].link, node, j);
								const link = this.graph.connect(this.connecting.node, this.connecting.slot, node, j);
								if (link) this.eventBus.emit('link:created', { linkId: link.id });
							}
							break;
						}
					}
				} else {
					for (let j = 0; j < node.outputs.length; j++) {
						const slotY = node.pos[1] + 30 + j * 25;
						if (Math.sqrt(Math.pow(wx - (node.pos[0] + node.size[0]), 2) + Math.pow(wy - slotY, 2)) < 15 && node !== this.connecting.node) {
							if (!this.isSlotCompatible(node, j, true)) { this.showError('Type mismatch'); break; }
							if (this.connecting.node.multiInputs?.[this.connecting.slot]) {
								const linkId = ++this.graph.last_link_id;
								const link = new Link(linkId, node.id, j, this.connecting.node.id, this.connecting.slot, node.outputs[j].type);
								this.graph.links[linkId] = link;
								node.outputs[j].links.push(linkId);
								this.connecting.node.multiInputs[this.connecting.slot].links.push(linkId);
								this.eventBus.emit('link:created', { linkId });
							} else {
								if (this.connecting.node.inputs[this.connecting.slot].link) this.removeLink(this.connecting.node.inputs[this.connecting.slot].link, this.connecting.node, this.connecting.slot);
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
			if (!data.event.ctrlKey && !data.event.metaKey) this.clearSelection();
			for (const node of this.graph.nodes) {
				if (!(node.pos[0] > this.selectionRect.x + this.selectionRect.w || node.pos[0] + node.size[0] < this.selectionRect.x || node.pos[1] > this.selectionRect.y + this.selectionRect.h || node.pos[1] + node.size[1] < this.selectionRect.y)) {
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
		if (this.isLocked) return;
		const [wx, wy] = this.screenToWorld(data.coords.screenX, data.coords.screenY);

		for (const node of this.graph.nodes) {
			if (node.nativeInputs) {
				for (let j = 0; j < node.inputs.length; j++) {
					if (!node.inputs[j].link && node.nativeInputs[j] !== undefined) {
						const slotY = node.pos[1] + 30 + j * 25;
						const boxX = node.pos[0] + 10, boxY = slotY + 6, boxW = 70, boxH = 12;
						if (wx >= boxX && wx <= boxX + boxW && wy >= boxY && wy <= boxY + boxH) {
							if (node.nativeInputs[j].type === 'bool') { node.nativeInputs[j].value = !node.nativeInputs[j].value; this.draw(); return; }
							this.showInputOverlay(node, j, boxX, boxY, data.coords.rect);
							return;
						}
					}
				}
			}
		}

		for (const node of this.graph.nodes) {
			if (!node.isNative) continue;
			const valueY = node.pos[1] + node.size[1] - 18;
			if (wx >= node.pos[0] + 8 && wx <= node.pos[0] + node.size[0] - 8 && wy >= valueY && wy <= valueY + 20) {
				if (node.title === 'Boolean') { node.properties.value = !node.properties.value; this.draw(); }
				else this.showInputOverlay(node, null, node.pos[0] + 8, valueY, data.coords.rect);
				return;
			}
		}
	}

	showInputOverlay(node, slot, x, y, rect) {
		const valueScreen = this.worldToScreen(x, y);
		this.editingNode = node;
		this.editingNode.editingSlot = slot;
		const nodeInput = document.getElementById('sg-nodeInput');
		nodeInput.value = slot !== null ? String(node.nativeInputs[slot].value) : String(node.properties.value);
		nodeInput.style.left = (valueScreen[0] * rect.width / this.canvas.width + rect.left) + 'px';
		nodeInput.style.top = (valueScreen[1] * rect.height / this.canvas.height + rect.top) + 'px';
		nodeInput.style.width = slot !== null ? '75px' : '160px';
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
		this.eventBus.emit('ui:update', { id: 'zoomLevel', content: Math.round(this.camera.scale * 100) + '%' });
		this.draw();
	}

	handleContextMenu(data) {
		if (this.isLocked) { data.event.preventDefault(); return; }
		const [wx, wy] = this.screenToWorld(data.coords.screenX, data.coords.screenY);
		let clickedNode = null;
		for (let i = this.graph.nodes.length - 1; i >= 0; i--) {
			const node = this.graph.nodes[i];
			if (wx >= node.pos[0] && wx <= node.pos[0] + node.size[0] && wy >= node.pos[1] && wy <= node.pos[1] + node.size[1]) {
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
			html += '<div class="sg-context-menu-category">Node Actions</div>';
			html += this.selectedNodes.size > 1 
				? `<div class="sg-context-menu-item sg-context-menu-delete" data-action="delete-all">✖ Delete ${this.selectedNodes.size} Nodes</div>` 
				: '<div class="sg-context-menu-item sg-context-menu-delete" data-action="delete">✖ Delete Node</div>';
		} else {
			// Native types submenu (leaf - scrollable)
			html += `<div class="sg-submenu-wrap">`;
			html += `<div class="sg-submenu-trigger">Native Types</div>`;
			html += `<div class="sg-submenu-panel sg-submenu-leaf">`;
			for (const type of ['Native.String', 'Native.Integer', 'Native.Boolean', 'Native.Float', 'Native.List', 'Native.Dict']) {
				html += `<div class="sg-context-menu-item" data-type="${type}">${type.split('.')[1]}</div>`;
			}
			html += '</div></div>';

			// Schema nodes
			for (const schemaName of Object.keys(this.graph.schemas)) {
				if (!this.graph.isSchemaEnabled?.(schemaName) && !this.graph.schemas[schemaName]?.enabled) continue;
				
				const schemaInfo = this.graph.schemas[schemaName];
				const decorators = this._schemaDecorators[schemaName] || {};
				
				const sections = {};
				const defaultSection = 'General';
				
				for (const type in this.graph.nodeTypes) {
					if (!type.startsWith(schemaName + '.')) continue;
					const modelName = type.split('.')[1];
					const info = decorators[modelName]?.info;
					if (info?.visible === false) continue;
					const section = info?.section || defaultSection;
					if (!sections[section]) sections[section] = [];
					sections[section].push({ type, modelName, info, isRoot: schemaInfo.rootType === modelName });
				}
				
				const sectionNames = Object.keys(sections).sort((a, b) => {
					if (a === defaultSection) return -1;
					if (b === defaultSection) return 1;
					return a.localeCompare(b);
				});
				
				if (sectionNames.length === 0) continue;
				
				html += `<div class="sg-submenu-wrap">`;
				html += `<div class="sg-submenu-trigger">${schemaName}</div>`;
				
				// If only one section, it's a leaf (scrollable)
				// If multiple sections, it's a branch (visible overflow)
				if (sectionNames.length === 1) {
					html += `<div class="sg-submenu-panel sg-submenu-leaf">`;
					const sectionNodes = sections[sectionNames[0]];
					sectionNodes.sort((a, b) => {
						if (a.isRoot) return -1;
						if (b.isRoot) return 1;
						return (a.info?.title || a.modelName).localeCompare(b.info?.title || b.modelName);
					});
					
					for (const item of sectionNodes) {
						const icon = item.info?.icon ? `<span class="sg-menu-icon">${item.info.icon}</span>` : '';
						const title = item.info?.title || item.modelName;
						const rootMark = item.isRoot ? '☆ ' : '';
						const rootClass = item.isRoot ? ' sg-menu-root' : '';
						html += `<div class="sg-context-menu-item${rootClass}" data-type="${item.type}">${icon}${rootMark}${title}</div>`;
					}
					html += '</div></div>';
				} else {
					// Multiple sections - branch with nested submenus
					html += `<div class="sg-submenu-panel sg-submenu-branch">`;
					
					for (const sectionName of sectionNames) {
						const sectionNodes = sections[sectionName];
						if (sectionNodes.length === 0) continue;
						
						html += `<div class="sg-submenu-wrap">`;
						html += `<div class="sg-submenu-trigger">${sectionName}</div>`;
						html += `<div class="sg-submenu-panel sg-submenu-leaf">`; // Innermost - scrollable
						
						sectionNodes.sort((a, b) => {
							if (a.isRoot) return -1;
							if (b.isRoot) return 1;
							return (a.info?.title || a.modelName).localeCompare(b.info?.title || b.modelName);
						});
						
						for (const item of sectionNodes) {
							const icon = item.info?.icon ? `<span class="sg-menu-icon">${item.info.icon}</span>` : '';
							const title = item.info?.title || item.modelName;
							const rootMark = item.isRoot ? '☆ ' : '';
							const rootClass = item.isRoot ? ' sg-menu-root' : '';
							html += `<div class="sg-context-menu-item${rootClass}" data-type="${item.type}">${icon}${rootMark}${title}</div>`;
						}
						
						html += '</div></div>';
					}
					
					html += '</div></div>';
				}
			}
		}

		contextMenu.innerHTML = html;

		// Position
		let menuX = coords.clientX;
		let menuY = coords.clientY;
		contextMenu.style.left = '0px';
		contextMenu.style.top = '0px';
		contextMenu.classList.add('show');
		
		const menuRect = contextMenu.getBoundingClientRect();
		if (menuX + menuRect.width > window.innerWidth) menuX = window.innerWidth - menuRect.width - 5;
		if (menuY + menuRect.height > window.innerHeight) menuY = window.innerHeight - menuRect.height - 5;
		menuX = Math.max(5, menuX);
		menuY = Math.max(5, menuY);
		
		contextMenu.style.left = menuX + 'px';
		contextMenu.style.top = menuY + 'px';
		contextMenu.dataset.worldX = wx;
		contextMenu.dataset.worldY = wy;

		// HOVER LOGIC
		contextMenu.querySelectorAll('.sg-submenu-wrap').forEach(wrap => {
			const trigger = wrap.querySelector(':scope > .sg-submenu-trigger');
			const panel = wrap.querySelector(':scope > .sg-submenu-panel');
			
			if (!trigger || !panel) return;

			wrap.addEventListener('mouseenter', () => {
				panel.style.display = 'block';
				
				// Flip if needed
				const rect = panel.getBoundingClientRect();
				if (rect.right > window.innerWidth) {
					panel.style.left = 'auto';
					panel.style.right = '100%';
				}
			});
			
			wrap.addEventListener('mouseleave', () => {
				panel.style.display = 'none';
			});
		});

		// Click handlers
		if (node) {
			contextMenu.querySelector('.sg-context-menu-delete')?.addEventListener('click', () => {
				this.selectedNodes.size > 1 ? this.deleteSelectedNodes() : this.removeNode(node);
				contextMenu.classList.remove('show');
			});
		}
		
		contextMenu.querySelectorAll('.sg-context-menu-item[data-type]').forEach(item => {
			item.addEventListener('click', (e) => {
				e.stopPropagation();
				const type = item.getAttribute('data-type');
				const n = this.graph.createNode(type);
				n.pos = [parseFloat(contextMenu.dataset.worldX) - 90, parseFloat(contextMenu.dataset.worldY) - 40];
				contextMenu.classList.remove('show');
				this.draw();
			});
		});
	}

	// === KEYBOARD HANDLERS ===
	handleKeyDown(data) {
		const isTyping = data.event.target.tagName === 'INPUT' || data.event.target.tagName === 'TEXTAREA';
		if (data.code === 'Space' && !this.spacePressed && !this.editingNode && !isTyping) {
			data.event.preventDefault();
			this.spacePressed = true;
			this.canvas.style.cursor = 'grab';
		}
		if ((data.key === 'Delete' || data.key === 'Backspace') && this.selectedNodes.size > 0 && !this.editingNode && !isTyping && !this.isLocked) {
			data.event.preventDefault();
			this.deleteSelectedNodes();
		}
		if ((data.event.ctrlKey || data.event.metaKey) && data.key === 'a' && !this.editingNode && !isTyping) {
			data.event.preventDefault();
			this.clearSelection();
			for (const node of this.graph.nodes) this.selectNode(node, true);
		}
		if (data.key === 'Escape' && !this.editingNode) this.clearSelection();
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
			let fieldName = null;
			
			if (this.editingNode.editingSlot !== null && this.editingNode.editingSlot !== undefined) {
				const slot = this.editingNode.editingSlot;
				fieldName = this.editingNode.inputs?.[slot]?.name;
				const inputType = this.editingNode.nativeInputs[slot].type;
				if (inputType === 'int') this.editingNode.nativeInputs[slot].value = parseInt(val) || 0;
				else if (inputType === 'float') this.editingNode.nativeInputs[slot].value = parseFloat(val) || 0.0;
				else if (inputType === 'bool') this.editingNode.nativeInputs[slot].value = val === 'true' || val === true;
				else this.editingNode.nativeInputs[slot].value = val;
				this.editingNode.editingSlot = null;
			} else {
				fieldName = 'value';
				if (this.editingNode.title === 'Integer') this.editingNode.properties.value = parseInt(val) || 0;
				else if (this.editingNode.title === 'Float') this.editingNode.properties.value = parseFloat(val) || 0.0;
				else if (this.editingNode.title === 'Boolean') this.editingNode.properties.value = val === 'true' || val === true;
				else this.editingNode.properties.value = val;
			}
			
			// Emit field changed event
			this.eventBus.emit(GraphEvents.FIELD_CHANGED, {
				nodeId: this.editingNode.id,
				fieldName: fieldName,
				value: val
			});
			
			// Refresh interactivity based on completeness
			this._refreshNodeInteractivity(this.editingNode);
		
			this.draw();
		}
		document.getElementById('sg-nodeInput')?.classList.remove('show');
		this.editingNode = null;
	}

	handleInputKeyDown(e) {
		if (e.key === 'Enter') document.getElementById('sg-nodeInput')?.blur();
		else if (e.key === 'Escape') { document.getElementById('sg-nodeInput')?.classList.remove('show'); this.editingNode = null; }
	}

	// === HELPER METHODS ===
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

	removeNode(node) {
		if (!node) return;
		for (let j = 0; j < node.inputs.length; j++) {
			if (node.multiInputs?.[j]) {
				for (const linkId of node.multiInputs[j].links.slice()) this.removeLink(linkId, node, j);
			} else if (node.inputs[j].link) {
				this.removeLink(node.inputs[j].link, node, j);
			}
		}
		for (let j = 0; j < node.outputs.length; j++) {
			for (const linkId of node.outputs[j].links.slice()) {
				const link = this.graph.links[linkId];
				if (link) {
					const targetNode = this.graph.getNodeById(link.target_id);
					if (targetNode) {
						if (targetNode.multiInputs?.[link.target_slot]) {
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
		if (idx > -1) { this.graph.nodes.splice(idx, 1); delete this.graph._nodes_by_id[node.id]; }
		if (this.selectedNode === node) this.selectedNode = null;
		this.eventBus.emit('node:deleted', { nodeId: node.id });
	}

	isSlotCompatible(node, slotIdx, isOutput) {
		if (!this.connecting || node === this.connecting.node) return false;
		if (this.connecting.isOutput && !isOutput) return this.graph._areTypesCompatible(this.connecting.node.outputs[this.connecting.slot].type, node.inputs[slotIdx].type);
		if (!this.connecting.isOutput && isOutput) return this.graph._areTypesCompatible(node.outputs[slotIdx].type, this.connecting.node.inputs[this.connecting.slot].type);
		return false;
	}

	showError(text) {
		const errorEl = document.getElementById('sg-errorBanner');
		if (errorEl) { errorEl.textContent = '⚠️ ' + text; errorEl.style.display = 'block'; setTimeout(() => errorEl.style.display = 'none', 3000); }
		this.eventBus.emit('error', { message: text });
	}

	_showTooltip(clientX, clientY, meta, isRequired) {
		if (!this._fieldTooltipsEnabled) return;
		
		if (!this.tooltipEl) {
			this.tooltipEl = document.createElement('div');
			this.tooltipEl.className = 'sg-tooltip';
			document.body.appendChild(this.tooltipEl);
		}
		
		let html = '';
		
		if (meta.title) {
			html += `<div class="sg-tooltip-title">${meta.title}</div>`;
		}
		
		if (meta.description) {
			html += `<div class="sg-tooltip-desc">${meta.description}</div>`;
		}
		
		html += `<div class="sg-tooltip-field"><code>${meta.name}</code></div>`;
		
		// Type and badges row
		html += '<div style="display:flex;flex-wrap:wrap;gap:4px;align-items:center;">';
		
		if (meta.type) {
			html += `<span class="sg-tooltip-type">${meta.type}</span>`;
		}
		
		if (meta.isMulti) {
			html += `<span class="sg-tooltip-badge multi">Multi-Slot</span>`;
		}
		
		// Required/Optional badge
		if (isRequired) {
			html += `<span class="sg-tooltip-badge required">Required</span>`;
		} else {
			html += `<span class="sg-tooltip-badge optional">Optional</span>`;
		}
		
		html += '</div>';
		
		this.tooltipEl.innerHTML = html;
		
		let x = clientX + 15;
		let y = clientY + 15;
		
		if (x + 280 > window.innerWidth) x = clientX - 290;
		if (y + 120 > window.innerHeight) y = clientY - 130;
		
		this.tooltipEl.style.left = x + 'px';
		this.tooltipEl.style.top = y + 'px';
		this.tooltipEl.style.display = 'block';
	}

	_hideTooltip() {
		if (this.tooltipEl) {
			this.tooltipEl.style.display = 'none';
		}
	}

	_showNodeHeaderTooltip(clientX, clientY, node) {
		if (!this._nodeTooltipsEnabled) return;
		
		const info = this._schemaDecorators[node.schemaName]?.[node.modelName]?.info || {};
		
		if (!this._nodeHeaderTooltipEl) {
			this._nodeHeaderTooltipEl = document.createElement('div');
			this._nodeHeaderTooltipEl.className = 'sg-node-tooltip';
			document.body.appendChild(this._nodeHeaderTooltipEl);
		}
		
		// Build tooltip content - always show basic info
		let html = '<div class="sg-node-tooltip-header">';
		
		if (info.icon) {
			html += `<span class="sg-node-tooltip-icon">${info.icon}</span>`;
		}
		
		// Use info.title, fallback to modelName
		const displayTitle = info.title || node.modelName || node.title;
		html += `<span class="sg-node-tooltip-title">${displayTitle}</span>`;
		html += '</div>';
		
		// Description if available
		if (info.description) {
			html += `<div class="sg-node-tooltip-desc">${info.description}</div>`;
		}
		
		// Always show schema/model info
		html += '<div class="sg-node-tooltip-meta">';
		
		if (node.schemaName) {
			html += `<div class="sg-node-tooltip-meta-item"><span class="sg-node-tooltip-meta-label">Schema:</span> ${node.schemaName}</div>`;
		}
		
		if (node.modelName) {
			html += `<div class="sg-node-tooltip-meta-item"><span class="sg-node-tooltip-meta-label">Model:</span> ${node.modelName}</div>`;
		}
		
		if (node.workflowType) {
			html += `<div class="sg-node-tooltip-meta-item"><span class="sg-node-tooltip-meta-label">Type:</span> ${node.workflowType}</div>`;
		}
		
		// Section if available
		if (info.section) {
			html += `<div class="sg-node-tooltip-meta-item"><span class="sg-node-tooltip-meta-label">Section:</span> ${info.section}</div>`;
		}
		
		// Completeness status
		const completeness = this._getNodeCompleteness(node);
		if (completeness.missingFields.length > 0) {
			html += `<div class="sg-node-tooltip-meta-item sg-node-tooltip-incomplete">`;
			html += `<span class="sg-node-tooltip-meta-label">Missing:</span> ${completeness.missingFields.join(', ')}`;
			html += `</div>`;
		} else {
			html += `<div class="sg-node-tooltip-meta-item sg-node-tooltip-complete">✓ All required fields filled</div>`;
		}
		
		html += '</div>';
		
		// Native node indicator
		if (node.isNative) {
			html += '<div class="sg-node-tooltip-badge-row"><span class="sg-node-tooltip-type-badge native">Native</span></div>';
		}
		
		// Root node indicator
		if (node.isRootType) {
			html += '<div class="sg-node-tooltip-badge-row"><span class="sg-node-tooltip-type-badge root">★ Root</span></div>';
		}
		
		this._nodeHeaderTooltipEl.innerHTML = html;
		
		// Position tooltip
		let x = clientX + 15;
		let y = clientY + 15;
		
		const tooltipRect = this._nodeHeaderTooltipEl.getBoundingClientRect();
		if (x + 320 > window.innerWidth) x = clientX - 330;
		if (y + 200 > window.innerHeight) y = clientY - 210;
		
		this._nodeHeaderTooltipEl.style.left = x + 'px';
		this._nodeHeaderTooltipEl.style.top = y + 'px';
		this._nodeHeaderTooltipEl.style.display = 'block';
	}

	_hideNodeHeaderTooltip() {
		if (this._nodeHeaderTooltipEl) {
			this._nodeHeaderTooltipEl.style.display = 'none';
		}
	}

	// ================================================================
	// Dialog Helpers
	// ================================================================

	_showInputDialog(options) {
		const { title, label, value, placeholder, onConfirm, onCancel } = options;
		
		const existing = document.getElementById('sg-input-dialog-overlay');
		if (existing) existing.remove();
		
		const overlay = document.createElement('div');
		overlay.id = 'sg-input-dialog-overlay';
		overlay.className = 'sg-input-dialog-overlay';
		
		overlay.innerHTML = `
			<div class="sg-input-dialog">
				<div class="sg-input-dialog-header">
					<span class="sg-input-dialog-title">${title || 'Input'}</span>
					<button class="sg-input-dialog-close">&times;</button>
				</div>
				<div class="sg-input-dialog-body">
					<label class="sg-input-dialog-label">${label || 'Value:'}</label>
					<input type="text" class="sg-input-dialog-input" value="${value || ''}" placeholder="${placeholder || ''}">
				</div>
				<div class="sg-input-dialog-footer">
					<button class="sg-input-dialog-btn sg-input-dialog-cancel">Cancel</button>
					<button class="sg-input-dialog-btn sg-input-dialog-confirm">OK</button>
				</div>
			</div>
		`;
		
		document.body.appendChild(overlay);
		
		const input = overlay.querySelector('.sg-input-dialog-input');
		const closeBtn = overlay.querySelector('.sg-input-dialog-close');
		const cancelBtn = overlay.querySelector('.sg-input-dialog-cancel');
		const confirmBtn = overlay.querySelector('.sg-input-dialog-confirm');
		
		const close = (confirmed = false) => {
			if (confirmed && onConfirm) onConfirm(input.value);
			else if (!confirmed && onCancel) onCancel();
			overlay.remove();
		};
		
		setTimeout(() => { input.focus(); input.select(); }, 10);
		
		closeBtn.onclick = () => close(false);
		cancelBtn.onclick = () => close(false);
		confirmBtn.onclick = () => close(true);
		
		input.onkeydown = (e) => {
			if (e.key === 'Enter') close(true);
			if (e.key === 'Escape') close(false);
		};
		
		overlay.onclick = (e) => { if (e.target === overlay) close(false); };
	}

	_showConfirmDialog(options) {
		const { title, message, confirmText, onConfirm, onCancel } = options;
		
		const existing = document.getElementById('sg-confirm-dialog-overlay');
		if (existing) existing.remove();
		
		const overlay = document.createElement('div');
		overlay.id = 'sg-confirm-dialog-overlay';
		overlay.className = 'sg-input-dialog-overlay';
		
		overlay.innerHTML = `
			<div class="sg-input-dialog">
				<div class="sg-input-dialog-header">
					<span class="sg-input-dialog-title">${title || 'Confirm'}</span>
					<button class="sg-input-dialog-close">&times;</button>
				</div>
				<div class="sg-input-dialog-body">
					<p class="sg-confirm-dialog-message">${message || 'Are you sure?'}</p>
				</div>
				<div class="sg-input-dialog-footer">
					<button class="sg-input-dialog-btn sg-input-dialog-cancel">Cancel</button>
					<button class="sg-input-dialog-btn sg-input-dialog-confirm sg-confirm-danger">${confirmText || 'Remove'}</button>
				</div>
			</div>
		`;
		
		document.body.appendChild(overlay);
		
		const closeBtn = overlay.querySelector('.sg-input-dialog-close');
		const cancelBtn = overlay.querySelector('.sg-input-dialog-cancel');
		const confirmBtn = overlay.querySelector('.sg-input-dialog-confirm');
		
		const close = (confirmed = false) => {
			if (confirmed && onConfirm) onConfirm();
			else if (!confirmed && onCancel) onCancel();
			overlay.remove();
		};
		
		closeBtn.onclick = () => close(false);
		cancelBtn.onclick = () => close(false);
		confirmBtn.onclick = () => close(true);
		overlay.onclick = (e) => { if (e.target === overlay) close(false); };
		
		setTimeout(() => confirmBtn.focus(), 10);
		
		const escHandler = (e) => {
			if (e.key === 'Escape') { close(false); document.removeEventListener('keydown', escHandler); }
		};
		document.addEventListener('keydown', escHandler);
	}

	// ================================================================
	// Multi-Slot UI Helpers
	// ================================================================

	_getMultiSlotAddButtons(node) {
		if (!node.isWorkflowNode) return [];
		
		const buttons = [];
		const x = node.pos[0];
		const y = node.pos[1];
		const w = node.size[0];
		
		// Multi-input add buttons
		for (const [fieldName, slotIndices] of Object.entries(node.multiInputSlots || {})) {
			if (slotIndices.length === 0) continue;
			const lastIdx = Math.max(...slotIndices);
			const slotY = y + 38 + lastIdx * 25;
			
			buttons.push({
				fieldName,
				type: 'input',
				x: x + 2,
				y: slotY + 8,
				w: 14,
				h: 14
			});
		}
		
		// Multi-output add buttons
		for (const [fieldName, slotIndices] of Object.entries(node.multiOutputSlots || {})) {
			if (slotIndices.length === 0) continue;
			const lastIdx = Math.max(...slotIndices);
			const slotY = y + 38 + lastIdx * 25;
			
			buttons.push({
				fieldName,
				type: 'output',
				x: x + w - 16,
				y: slotY + 8,
				w: 14,
				h: 14
			});
		}
		
		return buttons;
	}

	_getMultiSlotRemoveButtons(node) {
		if (!node.isWorkflowNode) return [];
		
		const buttons = [];
		const x = node.pos[0];
		const y = node.pos[1];
		const w = node.size[0];
		
		// Multi-input remove buttons
		for (const [fieldName, slotIndices] of Object.entries(node.multiInputSlots || {})) {
			if (slotIndices.length <= 1) continue;
			
			for (const slotIdx of slotIndices) {
				const slotName = node.inputs[slotIdx]?.name || '';
				const dotIdx = slotName.indexOf('.');
				const key = dotIdx !== -1 ? slotName.substring(dotIdx + 1) : slotName;
				const slotY = y + 38 + slotIdx * 25;
				const isConnected = !!node.inputs[slotIdx]?.link;
				
				buttons.push({
					fieldName, type: 'input', key, slotIdx, isConnected,
					x: x + 2, y: slotY - 6, w: 12, h: 12
				});
			}
		}
		
		// Multi-output remove buttons
		for (const [fieldName, slotIndices] of Object.entries(node.multiOutputSlots || {})) {
			if (slotIndices.length <= 1) continue;
			
			for (const slotIdx of slotIndices) {
				const slotName = node.outputs[slotIdx]?.name || '';
				const dotIdx = slotName.indexOf('.');
				const key = dotIdx !== -1 ? slotName.substring(dotIdx + 1) : slotName;
				const slotY = y + 38 + slotIdx * 25;
				const isConnected = (node.outputs[slotIdx]?.links?.length || 0) > 0;
				
				buttons.push({
					fieldName, type: 'output', key, slotIdx, isConnected,
					x: x + w - 14, y: slotY - 6, w: 12, h: 12
				});
			}
		}
		
		return buttons;
	}

	_isPointInButton(wx, wy, btn) {
		return wx >= btn.x && wx <= btn.x + btn.w && wy >= btn.y && wy <= btn.y + btn.h;
	}

	_isMouseNearNode(node) {
		const [mx, my] = this.screenToWorld(this.mousePos[0], this.mousePos[1]);
		const margin = 20;
		return mx >= node.pos[0] - margin && mx <= node.pos[0] + node.size[0] + margin &&
			my >= node.pos[1] - margin && my <= node.pos[1] + node.size[1] + margin;
	}

	_handleMultiSlotAddClick(btn) {
		const node = this.graph.getNodeById(btn.nodeId);
		if (!node) return;
		
		this.dragNode = null;
		this.isPanning = false;
		
		const existingKeys = btn.type === 'input'
			? this._getMultiInputKeys(node, btn.fieldName)
			: this._getMultiOutputKeys(node, btn.fieldName);
		
		let newKey = `${btn.fieldName}_${existingKeys.length + 1}`;
		let counter = existingKeys.length + 1;
		while (existingKeys.includes(newKey)) {
			counter++;
			newKey = `${btn.fieldName}_${counter}`;
		}
		
		this._showInputDialog({
			title: `Add ${btn.type} slot`,
			label: `Enter name for new ${btn.type}:`,
			value: newKey,
			placeholder: 'slot_name',
			onConfirm: (key) => {
				if (!key || !key.trim()) return;
				const trimmedKey = key.trim().replace(/[^a-zA-Z0-9_]/g, '_');
				
				if (btn.type === 'input') {
					this._addMultiInputSlot(node, btn.fieldName, trimmedKey);
				} else {
					this._addMultiOutputSlot(node, btn.fieldName, trimmedKey);
				}
			}
		});
	}

	_handleMultiSlotRemoveClick(btn) {
		const node = this.graph.getNodeById(btn.nodeId);
		if (!node) return;
		
		this.dragNode = null;
		this.isPanning = false;
		
		if (btn.isConnected) {
			this._showConfirmDialog({
				title: 'Remove connected slot',
				message: `"${btn.key}" is connected. Remove anyway?`,
				onConfirm: () => {
					if (btn.type === 'input') {
						this._removeMultiInputSlot(node, btn.fieldName, btn.key);
					} else {
						this._removeMultiOutputSlot(node, btn.fieldName, btn.key);
					}
				}
			});
		} else {
			if (btn.type === 'input') {
				this._removeMultiInputSlot(node, btn.fieldName, btn.key);
			} else {
				this._removeMultiOutputSlot(node, btn.fieldName, btn.key);
			}
		}
	}

	// ================================================================
	// Multi-Slot Manipulation
	// ================================================================

	_getMultiInputKeys(node, fieldName) {
		const indices = node.multiInputSlots?.[fieldName] || [];
		return indices.map(idx => {
			const name = node.inputs[idx]?.name || '';
			const dotIdx = name.indexOf('.');
			return dotIdx !== -1 ? name.substring(dotIdx + 1) : name;
		});
	}

	_getMultiOutputKeys(node, fieldName) {
		const indices = node.multiOutputSlots?.[fieldName] || [];
		return indices.map(idx => {
			const name = node.outputs[idx]?.name || '';
			const dotIdx = name.indexOf('.');
			return dotIdx !== -1 ? name.substring(dotIdx + 1) : name;
		});
	}

	_addMultiInputSlot(node, fieldName, key) {
		if (!node.multiInputSlots?.[fieldName]) return false;
		
		const existingKeys = this._getMultiInputKeys(node, fieldName);
		if (existingKeys.includes(key)) return false;
		
		// Get type from existing slots
		const existingIdx = node.multiInputSlots[fieldName][0];
		const slotType = node.inputs[existingIdx]?.type || 'Any';
		const meta = node.inputMeta?.[existingIdx];
		
		// Add new input slot
		const newIdx = node.inputs.length;
		const displayName = meta?.title ? `${meta.title}.${key}` : `${fieldName}.${key}`;
		node.addInput(displayName, slotType);
		node.multiInputSlots[fieldName].push(newIdx);
		
		// Add metadata
		if (node.inputMeta) {
			node.inputMeta[newIdx] = {
				name: `${fieldName}.${key}`,
				title: meta?.title,
				description: meta?.description,
				type: slotType,
				isMulti: true
			};
		}
		
		// Resize node
		const maxSlots = Math.max(node.inputs.length, node.outputs.length, 1);
		node.size[1] = Math.max(80, 35 + maxSlots * 25);
		
		this.eventBus.emit(GraphEvents.FIELD_CHANGED, { nodeId: node.id, fieldName, action: 'addSlot', key });
		this.draw();
		return true;
	}

	_removeMultiInputSlot(node, fieldName, key) {
		if (!node.multiInputSlots?.[fieldName]) return false;
		
		const indices = node.multiInputSlots[fieldName];
		if (indices.length <= 1) return false;
		
		// Find slot index
		let targetIdx = -1;
		for (const idx of indices) {
			const name = node.inputs[idx]?.name || '';
			const dotIdx = name.indexOf('.');
			const slotKey = dotIdx !== -1 ? name.substring(dotIdx + 1) : name;
			if (slotKey === key) { targetIdx = idx; break; }
		}
		
		if (targetIdx === -1) return false;
		
		// Remove any connected links
		if (node.inputs[targetIdx]?.link) {
			this.removeLink(node.inputs[targetIdx].link, node, targetIdx);
		}
		
		// Remove from multiInputSlots array
		const arrIdx = indices.indexOf(targetIdx);
		if (arrIdx !== -1) indices.splice(arrIdx, 1);
		
		// Remove the slot
		node.inputs.splice(targetIdx, 1);
		
		// Update indices in multiInputSlots
		for (const [fn, idxArr] of Object.entries(node.multiInputSlots)) {
			for (let i = 0; i < idxArr.length; i++) {
				if (idxArr[i] > targetIdx) idxArr[i]--;
			}
		}
		
		// Update nativeInputs indices
		if (node.nativeInputs) {
			const newNativeInputs = {};
			for (const [idx, val] of Object.entries(node.nativeInputs)) {
				const numIdx = parseInt(idx);
				if (numIdx < targetIdx) newNativeInputs[numIdx] = val;
				else if (numIdx > targetIdx) newNativeInputs[numIdx - 1] = val;
			}
			node.nativeInputs = newNativeInputs;
		}
		
		// Update inputMeta indices
		if (node.inputMeta) {
			const newMeta = {};
			for (const [idx, val] of Object.entries(node.inputMeta)) {
				const numIdx = parseInt(idx);
				if (numIdx < targetIdx) newMeta[numIdx] = val;
				else if (numIdx > targetIdx) newMeta[numIdx - 1] = val;
			}
			node.inputMeta = newMeta;
		}
		
		// Resize node
		const maxSlots = Math.max(node.inputs.length, node.outputs.length, 1);
		node.size[1] = Math.max(80, 35 + maxSlots * 25);
		
		this.eventBus.emit(GraphEvents.FIELD_CHANGED, { nodeId: node.id, fieldName, action: 'removeSlot', key });
		this.draw();
		return true;
	}

	_addMultiOutputSlot(node, fieldName, key) {
		if (!node.multiOutputSlots?.[fieldName]) return false;
		
		const existingKeys = this._getMultiOutputKeys(node, fieldName);
		if (existingKeys.includes(key)) return false;
		
		const existingIdx = node.multiOutputSlots[fieldName][0];
		const slotType = node.outputs[existingIdx]?.type || 'Any';
		const meta = node.outputMeta?.[existingIdx];
		
		const newIdx = node.outputs.length;
		const displayName = meta?.title ? `${meta.title}.${key}` : `${fieldName}.${key}`;
		node.addOutput(displayName, slotType);
		node.multiOutputSlots[fieldName].push(newIdx);
		
		if (node.outputMeta) {
			node.outputMeta[newIdx] = {
				name: `${fieldName}.${key}`,
				title: meta?.title,
				description: meta?.description,
				type: slotType,
				isMulti: true
			};
		}
		
		const maxSlots = Math.max(node.inputs.length, node.outputs.length, 1);
		node.size[1] = Math.max(80, 35 + maxSlots * 25);
		
		this.eventBus.emit(GraphEvents.FIELD_CHANGED, { nodeId: node.id, fieldName, action: 'addSlot', key });
		this.draw();
		return true;
	}

	_removeMultiOutputSlot(node, fieldName, key) {
		if (!node.multiOutputSlots?.[fieldName]) return false;
		
		const indices = node.multiOutputSlots[fieldName];
		if (indices.length <= 1) return false;
		
		let targetIdx = -1;
		for (const idx of indices) {
			const name = node.outputs[idx]?.name || '';
			const dotIdx = name.indexOf('.');
			const slotKey = dotIdx !== -1 ? name.substring(dotIdx + 1) : name;
			if (slotKey === key) { targetIdx = idx; break; }
		}
		
		if (targetIdx === -1) return false;
		
		// Remove connected links
		const links = node.outputs[targetIdx]?.links?.slice() || [];
		for (const linkId of links) {
			const link = this.graph.links[linkId];
			if (link) {
				const targetNode = this.graph.getNodeById(link.target_id);
				if (targetNode) this.removeLink(linkId, targetNode, link.target_slot);
			}
		}
		
		const arrIdx = indices.indexOf(targetIdx);
		if (arrIdx !== -1) indices.splice(arrIdx, 1);
		
		node.outputs.splice(targetIdx, 1);
		
		// Update indices
		for (const [fn, idxArr] of Object.entries(node.multiOutputSlots)) {
			for (let i = 0; i < idxArr.length; i++) {
				if (idxArr[i] > targetIdx) idxArr[i]--;
			}
		}
		
		// Update outputMeta indices
		if (node.outputMeta) {
			const newMeta = {};
			for (const [idx, val] of Object.entries(node.outputMeta)) {
				const numIdx = parseInt(idx);
				if (numIdx < targetIdx) newMeta[numIdx] = val;
				else if (numIdx > targetIdx) newMeta[numIdx - 1] = val;
			}
			node.outputMeta = newMeta;
		}
		
		// Update link references
		for (const linkId in this.graph.links) {
			const link = this.graph.links[linkId];
			if (link.origin_id === node.id && link.origin_slot > targetIdx) {
				link.origin_slot--;
			}
		}
		
		const maxSlots = Math.max(node.inputs.length, node.outputs.length, 1);
		node.size[1] = Math.max(80, 35 + maxSlots * 25);
		
		this.eventBus.emit(GraphEvents.FIELD_CHANGED, { nodeId: node.id, fieldName, action: 'removeSlot', key });
		this.draw();
		return true;
	}

	_renameMultiInputSlot(node, fieldName, oldKey, newKey) {
		if (!node.multiInputSlots?.[fieldName]) return false;
		
		const existingKeys = this._getMultiInputKeys(node, fieldName);
		if (existingKeys.includes(newKey)) return false;
		
		for (const idx of node.multiInputSlots[fieldName]) {
			const name = node.inputs[idx]?.name || '';
			const dotIdx = name.indexOf('.');
			const slotKey = dotIdx !== -1 ? name.substring(dotIdx + 1) : name;
			
			if (slotKey === oldKey) {
				const meta = node.inputMeta?.[idx];
				const newDisplayName = meta?.title ? `${meta.title}.${newKey}` : `${fieldName}.${newKey}`;
				node.inputs[idx].name = newDisplayName;
				if (node.inputMeta?.[idx]) {
					node.inputMeta[idx].name = `${fieldName}.${newKey}`;
				}
				this.eventBus.emit(GraphEvents.FIELD_CHANGED, { nodeId: node.id, fieldName, action: 'renameSlot', oldKey, newKey });
				this.draw();
				return true;
			}
		}
		return false;
	}

	_renameMultiOutputSlot(node, fieldName, oldKey, newKey) {
		if (!node.multiOutputSlots?.[fieldName]) return false;
		
		const existingKeys = this._getMultiOutputKeys(node, fieldName);
		if (existingKeys.includes(newKey)) return false;
		
		for (const idx of node.multiOutputSlots[fieldName]) {
			const name = node.outputs[idx]?.name || '';
			const dotIdx = name.indexOf('.');
			const slotKey = dotIdx !== -1 ? name.substring(dotIdx + 1) : name;
			
			if (slotKey === oldKey) {
				const meta = node.outputMeta?.[idx];
				const newDisplayName = meta?.title ? `${meta.title}.${newKey}` : `${fieldName}.${newKey}`;
				node.outputs[idx].name = newDisplayName;
				if (node.outputMeta?.[idx]) {
					node.outputMeta[idx].name = `${fieldName}.${newKey}`;
				}
				this.eventBus.emit(GraphEvents.FIELD_CHANGED, { nodeId: node.id, fieldName, action: 'renameSlot', oldKey, newKey });
				this.draw();
				return true;
			}
		}
		return false;
	}

	_getSlotUnderMouse(wx, wy) {
		for (const node of this.graph.nodes) {
			for (let j = 0; j < node.inputs.length; j++) {
				const slotY = node.pos[1] + 38 + j * 25;
				if (Math.abs(wx - node.pos[0]) < 15 && Math.abs(wy - slotY) < 12) {
					return { node, slotIdx: j, isInput: true };
				}
			}
			for (let j = 0; j < node.outputs.length; j++) {
				const slotY = node.pos[1] + 38 + j * 25;
				if (Math.abs(wx - (node.pos[0] + node.size[0])) < 15 && Math.abs(wy - slotY) < 12) {
					return { node, slotIdx: j, isInput: false };
				}
			}
		}
		return null;
	}

	screenToWorld(sx, sy) { return [(sx - this.camera.x) / this.camera.scale, (sy - this.camera.y) / this.camera.scale]; }
	worldToScreen(wx, wy) { return [wx * this.camera.scale + this.camera.x, wy * this.camera.scale + this.camera.y]; }

	centerView() {
		if (this.graph.nodes.length === 0) return;
		let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
		for (const node of this.graph.nodes) {
			minX = Math.min(minX, node.pos[0]);
			minY = Math.min(minY, node.pos[1]);
			maxX = Math.max(maxX, node.pos[0] + node.size[0]);
			maxY = Math.max(maxY, node.pos[1] + node.size[1]);
		}
		const graphCenterX = minX + (maxX - minX) / 2;
		const graphCenterY = minY + (maxY - minY) / 2;
		const scaleX = (this.canvas.width - 200) / (maxX - minX);
		const scaleY = (this.canvas.height - 200) / (maxY - minY);
		this.camera.scale = Math.max(0.1, Math.min(5, Math.min(scaleX, scaleY, 1.5)));
		this.camera.x = this.canvas.width / 2 - graphCenterX * this.camera.scale;
		this.camera.y = this.canvas.height / 2 - graphCenterY * this.camera.scale;
		this.eventBus.emit('ui:update', { id: 'zoomLevel', content: Math.round(this.camera.scale * 100) + '%' });
		this.draw();
	}

	resetZoom() {
		const worldCenter = this.screenToWorld(this.canvas.width / 2, this.canvas.height / 2);
		this.camera.scale = 1.0;
		this.camera.x = this.canvas.width / 2 - worldCenter[0];
		this.camera.y = this.canvas.height / 2 - worldCenter[1];
		this.eventBus.emit('ui:update', { id: 'zoomLevel', content: '100%' });
		this.draw();
	}

	// === LAYOUT ===
	applyLayout(layoutType) {
		if (this.graph.nodes.length === 0) return;
		switch (layoutType) {
			case 'hierarchical-vertical': this.applyHierarchicalLayout(true); break;
			case 'hierarchical-horizontal': this.applyHierarchicalLayout(false); break;
			case 'force-directed': this.applyForceDirectedLayout(); break;
			case 'grid': this.applyGridLayout(); break;
			case 'circular': this.applyCircularLayout(); break;
		}
		this.eventBus.emit('layout:applied', { layoutType });
		this.draw();
		this.centerView();
	}

	applyHierarchicalLayout(vertical = false) {
		const rootNodes = this.graph.nodes.filter(n => !n.inputs.some(inp => inp.link) || n.isRootType);
		if (rootNodes.length === 0) rootNodes.push(...this.graph.nodes);
		const layers = [], processedNodes = new Set();
		const queue = rootNodes.map(n => { processedNodes.add(n); return { node: n, layer: 0 }; });
		while (queue.length > 0) {
			const { node, layer } = queue.shift();
			if (!layers[layer]) layers[layer] = [];
			layers[layer].push(node);
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
				if (!layers[layers.length]) layers.push([]);
				layers[layers.length - 1].push(node);
			}
		}
		for (let i = 0; i < layers.length; i++) {
			for (let j = 0; j < layers[i].length; j++) {
				const node = layers[i][j];
				if (vertical) { node.pos[0] = 100 + i * 300; node.pos[1] = 100 + j * 150 - (layers[i].length * 150) / 2; }
				else { node.pos[0] = 100 + j * 250 - (layers[i].length * 250) / 2; node.pos[1] = 100 + i * 200; }
			}
		}
	}

	applyForceDirectedLayout() {
		const velocities = new Map();
		for (const node of this.graph.nodes) {
			velocities.set(node, { x: 0, y: 0 });
			if (node.pos[0] === 0 && node.pos[1] === 0) { node.pos[0] = Math.random() * 400; node.pos[1] = Math.random() * 400; }
		}
		for (let iter = 0; iter < 100; iter++) {
			for (let i = 0; i < this.graph.nodes.length; i++) {
				const nodeA = this.graph.nodes[i], vel = velocities.get(nodeA);
				for (let j = i + 1; j < this.graph.nodes.length; j++) {
					const nodeB = this.graph.nodes[j];
					const dx = nodeB.pos[0] - nodeA.pos[0], dy = nodeB.pos[1] - nodeA.pos[1];
					const distSq = dx * dx + dy * dy, dist = Math.sqrt(distSq);
					if (dist < 0.1) continue;
					const force = 50000 / distSq, fx = (dx / dist) * force, fy = (dy / dist) * force;
					vel.x -= fx; vel.y -= fy;
					velocities.get(nodeB).x += fx;
					velocities.get(nodeB).y += fy;
				}
			}
			for (const linkId in this.graph.links) {
				const link = this.graph.links[linkId];
				const nodeA = this.graph.getNodeById(link.origin_id), nodeB = this.graph.getNodeById(link.target_id);
				if (!nodeA || !nodeB) continue;
				const dx = nodeB.pos[0] - nodeA.pos[0], dy = nodeB.pos[1] - nodeA.pos[1], dist = Math.sqrt(dx * dx + dy * dy);
				if (dist < 0.1) continue;
				const force = (dist - 200) * 0.01, fx = (dx / dist) * force, fy = (dy / dist) * force;
				velocities.get(nodeA).x += fx; velocities.get(nodeA).y += fy;
				velocities.get(nodeB).x -= fx; velocities.get(nodeB).y -= fy;
			}
			for (const node of this.graph.nodes) {
				const vel = velocities.get(node);
				node.pos[0] += vel.x; node.pos[1] += vel.y;
				vel.x *= 0.9; vel.y *= 0.9;
			}
		}
	}

	applyGridLayout() {
		const cols = Math.ceil(Math.sqrt(this.graph.nodes.length));
		for (let i = 0; i < this.graph.nodes.length; i++) {
			this.graph.nodes[i].pos = [100 + (i % cols) * 250, 100 + Math.floor(i / cols) * 200];
		}
	}

	applyCircularLayout() {
		const radius = Math.max(300, this.graph.nodes.length * 30);
		const angleStep = (2 * Math.PI) / this.graph.nodes.length;
		for (let i = 0; i < this.graph.nodes.length; i++) {
			this.graph.nodes[i].pos = [Math.cos(i * angleStep) * radius, Math.sin(i * angleStep) * radius];
		}
	}

	// === DRAWING ===
	getCanvasColors() {
		const style = getComputedStyle(document.documentElement);
		return {
			canvasBg: style.getPropertyValue('--sg-canvas-bg').trim() || '#1a1a2e',
			nodeBg: style.getPropertyValue('--sg-node-bg').trim() || '#252540',
			nodeBgSelected: style.getPropertyValue('--sg-node-bg-selected').trim() || '#303050',
			nodeHeader: style.getPropertyValue('--sg-node-header').trim() || '#404060',
			nodeShadow: style.getPropertyValue('--sg-node-shadow').trim() || 'rgba(0,0,0,0.3)',
			borderColor: style.getPropertyValue('--sg-border-color').trim() || '#404060',
			borderHighlight: style.getPropertyValue('--sg-border-highlight').trim() || '#46a2da',
			textPrimary: style.getPropertyValue('--sg-text-primary').trim() || '#ffffff',
			textSecondary: style.getPropertyValue('--sg-text-secondary').trim() || '#b0b0c0',
			textTertiary: style.getPropertyValue('--sg-text-tertiary').trim() || '#808090',
			accentPurple: style.getPropertyValue('--sg-accent-purple').trim() || '#9370db',
			accentOrange: style.getPropertyValue('--sg-accent-orange').trim() || '#f5a623',
			accentGreen: style.getPropertyValue('--sg-accent-green').trim() || '#50c878',
			accentRed: style.getPropertyValue('--sg-accent-red').trim() || '#dc6068',
			slotInput: style.getPropertyValue('--sg-slot-input').trim() || '#6495ed',
			slotOutput: style.getPropertyValue('--sg-slot-output').trim() || '#98d982',
			slotConnected: style.getPropertyValue('--sg-slot-connected').trim() || '#ffd700',
			linkColor: style.getPropertyValue('--sg-link-color').trim() || '#7090b0',
			gridColor: style.getPropertyValue('--sg-grid-color').trim() || '#303050'
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

		this.drawGrid(colors);
		this.drawLinks(colors);
		this.drawNodes(colors);

		if (this.connecting) this.drawConnecting(colors);
		if (this.selectionRect) {
			this.ctx.strokeStyle = colors.borderHighlight;
			this.ctx.fillStyle = 'rgba(70,162,218,0.1)';
			this.ctx.lineWidth = 1 / this.camera.scale;
			this.ctx.setLineDash([5 / this.camera.scale, 5 / this.camera.scale]);
			this.ctx.fillRect(this.selectionRect.x, this.selectionRect.y, this.selectionRect.w, this.selectionRect.h);
			this.ctx.strokeRect(this.selectionRect.x, this.selectionRect.y, this.selectionRect.w, this.selectionRect.h);
			this.ctx.setLineDash([]);
		}

		this.ctx.restore();

		if (this.isLocked) {
			this.ctx.save();
			const text = `🔒 ${(this.lockReason || 'Locked') + (this.lockInterval ? '.'.repeat(this.lockPending + 1) : '')}`;
			this.ctx.font = 'bold 12px Arial';
			const tw = this.ctx.measureText(text).width;
			this.ctx.fillStyle = 'rgba(220,100,100,0.9)';
			this.ctx.beginPath();
			this.ctx.roundRect(10, 10, tw + 16, 28, 6);
			this.ctx.fill();
			this.ctx.fillStyle = '#fff';
			this.ctx.textAlign = 'left';
			this.ctx.textBaseline = 'middle';
			this.ctx.fillText(text, 18, 24);
			this.ctx.restore();
		}
	}

	drawGrid(colors) {
		const style = this.drawingStyleManager.getStyle(), gridSize = 50;
		const worldRect = {
			x: -this.camera.x / this.camera.scale,
			y: -this.camera.y / this.camera.scale,
			width: this.canvas.width / this.camera.scale,
			height: this.canvas.height / this.camera.scale
		};
		const startX = Math.floor(worldRect.x / gridSize) * gridSize;
		const startY = Math.floor(worldRect.y / gridSize) * gridSize;

		this.ctx.strokeStyle = colors.gridColor;
		this.ctx.globalAlpha = style.gridOpacity;
		this.ctx.lineWidth = 1 / this.camera.scale;
		if (style.useDashed) this.ctx.setLineDash([4 / this.camera.scale, 4 / this.camera.scale]);
		this.ctx.beginPath();
		for (let x = startX; x <= worldRect.x + worldRect.width; x += gridSize) { this.ctx.moveTo(x, worldRect.y); this.ctx.lineTo(x, worldRect.y + worldRect.height); }
		for (let y = startY; y <= worldRect.y + worldRect.height; y += gridSize) { this.ctx.moveTo(worldRect.x, y); this.ctx.lineTo(worldRect.x + worldRect.width, y); }
		this.ctx.stroke();
		if (style.useDashed) this.ctx.setLineDash([]);
		this.ctx.globalAlpha = 1.0;
	}

	drawLinks(colors) {
		const style = this.drawingStyleManager.getStyle();
		for (const linkId in this.graph.links) {
			const link = this.graph.links[linkId];
			const orig = this.graph.getNodeById(link.origin_id);
			const targ = this.graph.getNodeById(link.target_id);
			if (!orig || !targ) continue;

			const x1 = orig.pos[0] + orig.size[0], y1 = orig.pos[1] + 33 + link.origin_slot * 25;
			const x2 = targ.pos[0], y2 = targ.pos[1] + 33 + link.target_slot * 25;
			const controlOffset = Math.min(Math.abs(x2 - x1) * style.linkCurve, 400);

			this.ctx.strokeStyle = colors.linkColor;
			this.ctx.lineWidth = style.linkWidth / this.camera.scale;
			if (style.useDashed) this.ctx.setLineDash([8 / this.camera.scale, 4 / this.camera.scale]);
			this.ctx.beginPath();
			if (style.linkCurve > 0) {
				this.ctx.moveTo(x1, y1);
				this.ctx.bezierCurveTo(x1 + controlOffset, y1, x2 - controlOffset, y2, x2, y2);
			} else {
				this.ctx.moveTo(x1, y1);
				this.ctx.lineTo(x2, y2);
			}
			this.ctx.stroke();
			if (style.useDashed) this.ctx.setLineDash([]);
		}
	}

	drawNodes(colors) {
		const unsel = [], sel = [];
		for (const node of this.graph.nodes) (this.isNodeSelected(node) ? sel : unsel).push(node);
		for (const node of unsel) this.drawNode(node, colors);
		for (const node of sel) this.drawNode(node, colors);
	}

	drawNode(node, colors) {
		const style = this.drawingStyleManager.getStyle();
		const x = node.pos[0], y = node.pos[1], w = node.size[0], h = node.size[1];
		const radius = style.nodeCornerRadius, textScale = this.getTextScale();
		const isSelected = this.isNodeSelected(node);
		const isPreviewSelected = this.previewSelection.has(node);
		const bodyColor = isSelected ? colors.nodeBgSelected : (isPreviewSelected ? this.adjustColorBrightness(colors.nodeBg, 20) : colors.nodeBg);

		if (style.nodeShadowBlur > 0) {
			this.ctx.shadowColor = colors.nodeShadow;
			this.ctx.shadowBlur = style.nodeShadowBlur / this.camera.scale;
			this.ctx.shadowOffsetY = style.nodeShadowOffset / this.camera.scale;
		}

		this.ctx.fillStyle = style.currentStyle === 'wireframe' ? 'transparent' : bodyColor;
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
		if (style.currentStyle !== 'wireframe') this.ctx.fill();

		this.ctx.shadowBlur = 0;
		this.ctx.shadowOffsetY = 0;
		this.ctx.strokeStyle = isSelected ? colors.borderHighlight : colors.borderColor;
		this.ctx.lineWidth = (isSelected ? 2 : 1) / this.camera.scale;
		if (isPreviewSelected && !isSelected) this.ctx.setLineDash([5 / this.camera.scale, 5 / this.camera.scale]);
		this.ctx.stroke();
		if (isPreviewSelected && !isSelected) this.ctx.setLineDash([]);

		const headerColor = node.color || (node.isNative ? colors.accentPurple : (node.isRootType ? colors.accentOrange : colors.nodeHeader));
		this.ctx.fillStyle = style.currentStyle === 'wireframe' ? 'transparent' : headerColor;
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
		if (style.currentStyle !== 'wireframe') this.ctx.fill();

		this.ctx.save();
		this.ctx.beginPath();
		this.ctx.rect(x + 4, y, w - 8, 26);
		this.ctx.clip();
		this.ctx.fillStyle = colors.textPrimary;
		this.ctx.font = (11 * textScale) + 'px ' + style.textFont;
		this.ctx.textBaseline = 'middle';
		this.ctx.textAlign = 'left';
		let titleText = node.isRootType ? '★ ' + node.title : node.title;
		const maxWidth = w - 16;
		let displayTitle = titleText;
		if (this.ctx.measureText(displayTitle).width > maxWidth) {
			let left = 0, right = displayTitle.length;
			while (left < right) {
				const mid = Math.floor((left + right + 1) / 2);
				if (this.ctx.measureText(displayTitle.substring(0, mid) + '...').width <= maxWidth) left = mid;
				else right = mid - 1;
			}
			displayTitle = displayTitle.substring(0, left) + '...';
		}
		this.ctx.fillText(displayTitle, x + 8, y + 13);
		this.ctx.restore();

		const worldMouse = this.screenToWorld(this.mousePos[0], this.mousePos[1]);
		for (let j = 0; j < node.inputs.length; j++) this.drawInputSlot(node, j, x, y, w, worldMouse, colors, textScale, style);
		for (let j = 0; j < node.outputs.length; j++) this.drawOutputSlot(node, j, x, y, w, worldMouse, colors, textScale, style);

		if (node.isNative && node.properties.value !== undefined) {
			const valueY = y + h - 18, valueX = x + 8, valueW = w - 16, valueH = 18;
			this.ctx.fillStyle = 'rgba(0,0,0,0.4)';
			this.ctx.beginPath();
			this.ctx.roundRect(valueX, valueY - 10, valueW, valueH, 4);
			this.ctx.fill();
			this.ctx.strokeStyle = colors.borderColor;
			this.ctx.lineWidth = 1.5 / this.camera.scale;
			this.ctx.stroke();
			this.ctx.fillStyle = colors.textPrimary;
			this.ctx.font = (10 * textScale) + 'px ' + style.textFont;
			this.ctx.textAlign = 'center';
			this.ctx.textBaseline = 'middle';
			let displayValue = String(node.properties.value);
			if (displayValue.length > 20) displayValue = displayValue.substring(0, 20) + '...';
			this.ctx.fillText(displayValue, valueX + valueW / 2, valueY);
		}

		if (node.isWorkflowNode) {
			this._drawMultiSlotButtons(node, colors);
		}

		this._drawDropZoneHighlight(node);
		this._drawButtonStacks(node, colors);
	}

	_drawMultiSlotButtons(node, colors) {
		const textScale = this.getTextScale();
		
		// Draw add buttons
		const addButtons = this._getMultiSlotAddButtons(node);
		for (const btn of addButtons) {
			const isHovered = this._hoveredAddButton?.nodeId === node.id &&
							this._hoveredAddButton?.fieldName === btn.fieldName &&
							this._hoveredAddButton?.type === btn.type;
			
			this.ctx.fillStyle = isHovered ? 'rgba(92, 184, 92, 0.9)' : 'rgba(92, 184, 92, 0.5)';
			this.ctx.beginPath();
			this.ctx.arc(btn.x + btn.w/2, btn.y + btn.h/2, btn.w/2, 0, Math.PI * 2);
			this.ctx.fill();
			
			this.ctx.fillStyle = '#fff';
			this.ctx.font = `bold ${10 * textScale}px sans-serif`;
			this.ctx.textAlign = 'center';
			this.ctx.textBaseline = 'middle';
			this.ctx.fillText('+', btn.x + btn.w/2, btn.y + btn.h/2);
		}
		
		// Draw remove buttons (only when near node)
		const removeButtons = this._getMultiSlotRemoveButtons(node);
		for (const btn of removeButtons) {
			const isHovered = this._hoveredRemoveButton?.nodeId === node.id &&
							this._hoveredRemoveButton?.key === btn.key;
			
			if (!isHovered && !this._isMouseNearNode(node)) continue;
			
			this.ctx.fillStyle = isHovered ? 'rgba(217, 83, 79, 0.9)' : 'rgba(217, 83, 79, 0.4)';
			this.ctx.beginPath();
			this.ctx.arc(btn.x + btn.w/2, btn.y + btn.h/2, btn.w/2, 0, Math.PI * 2);
			this.ctx.fill();
			
			this.ctx.fillStyle = '#fff';
			this.ctx.font = `bold ${8 * textScale}px sans-serif`;
			this.ctx.textAlign = 'center';
			this.ctx.textBaseline = 'middle';
			this.ctx.fillText('−', btn.x + btn.w/2, btn.y + btn.h/2);
		}
	}

	drawInputSlot(node, j, x, y, w, worldMouse, colors, textScale, style) {
		const inp = node.inputs[j], sy = y + 38 + j * 25;
		const isMulti = node.multiInputs?.[j];
		const hasConnections = isMulti ? node.multiInputs[j].links.length > 0 : inp.link;
		const compat = this.isSlotCompatible(node, j, false);
		
		const isRequired = this._isFieldRequired(node, j);
		const isFilled = this._isFieldFilled(node, j);
		const showRequiredHighlight = isRequired && !isFilled;
		
		let color = hasConnections ? colors.slotConnected : colors.slotInput;
		
		// Highlight required unfilled slots
		if (showRequiredHighlight) {
			color = colors.accentRed;
		}

		if (this.connecting && (compat || (
			this.connecting.node === node
			&& this.connecting.slot === j
			&& !this.connecting.isOutput
		))) {
			color = colors.accentGreen;
			this.ctx.fillStyle = color;
			this.ctx.globalAlpha = 0.3;
			this.ctx.beginPath();
			this.ctx.arc(x - 1, sy, 8, 0, Math.PI * 2);
			this.ctx.fill();
			this.ctx.globalAlpha = 1.0;
		}

		this.ctx.fillStyle = color;
		this.ctx.beginPath();
		this.ctx.arc(x - 1, sy, style.slotRadius || 4, 0, Math.PI * 2);
		this.ctx.fill();
		
		// Required unfilled indicator ring
		if (showRequiredHighlight) {
			this.ctx.strokeStyle = colors.accentRed;
			this.ctx.lineWidth = 2 / this.camera.scale;
			this.ctx.beginPath();
			this.ctx.arc(x - 1, sy, 7, 0, Math.PI * 2);
			this.ctx.stroke();
		}
		
		if (isMulti) {
			this.ctx.strokeStyle = colors.accentPurple;
			this.ctx.lineWidth = 1.5 / this.camera.scale;
			this.ctx.beginPath();
			this.ctx.arc(x - 1, sy, 6, 0, Math.PI * 2);
			this.ctx.stroke();
		}

		// Slot label - highlight required unfilled
		this.ctx.fillStyle = showRequiredHighlight ? colors.accentRed : colors.textSecondary;
		this.ctx.font = (10 * textScale) + 'px Arial';
		this.ctx.textAlign = 'left';
		this.ctx.textBaseline = 'middle';
		this.ctx.fillText(inp.name, x + 10, sy);

		const hasEditBox = !isMulti && !inp.link && node.nativeInputs?.[j] !== undefined;
		if (hasEditBox) {
			const boxX = x + 10, boxY = sy + 6, boxW = 70, boxH = 12;
			
			// Highlight box border if required and empty
			this.ctx.fillStyle = 'rgba(0,0,0,0.4)';
			this.ctx.beginPath();
			this.ctx.roundRect(boxX, boxY, boxW, boxH, 2);
			this.ctx.fill();
			
			this.ctx.strokeStyle = showRequiredHighlight ? colors.accentRed : 'rgba(255,255,255,0.15)';
			this.ctx.lineWidth = (showRequiredHighlight ? 1.5 : 1) / this.camera.scale;
			this.ctx.stroke();
			
			const val = node.nativeInputs[j].value;
			const isEmpty = val === '' || val === null || val === undefined;
			this.ctx.fillStyle = isEmpty ? (showRequiredHighlight ? colors.accentRed : colors.textTertiary) : colors.textPrimary;
			this.ctx.font = (8 * textScale) + 'px Courier New';
			this.ctx.textAlign = 'left';
			this.ctx.textBaseline = 'middle';
			this.ctx.fillText(isEmpty ? (node.nativeInputs[j].optional ? 'null' : 'required') : String(val).substring(0, 10), boxX + 4, boxY + boxH / 2);
		}
	}

	drawOutputSlot(node, j, x, y, w, worldMouse, colors, textScale, style) {
		const out = node.outputs[j], sy = y + 38 + j * 25;
		const hasConnections = out.links.length > 0;
		const compat = this.isSlotCompatible(node, j, true);
		let color = hasConnections ? colors.slotConnected : colors.slotOutput;

		if (this.connecting && (compat || (
			this.connecting.node === node
			&& this.connecting.slot === j
			&& this.connecting.isOutput
		))) {
			color = colors.accentPurple;
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
		this.ctx.fillStyle = colors.textSecondary;
		this.ctx.font = (10 * textScale) + 'px Arial';
		this.ctx.textAlign = 'right';
		this.ctx.textBaseline = 'middle';
		this.ctx.fillText(out.name, x + w - 10, sy);
	}

	drawConnecting(colors) {
		const node = this.connecting.node;
		const worldMouse = this.screenToWorld(this.mousePos[0], this.mousePos[1]);
		const x1 = this.connecting.isOutput ? node.pos[0] + node.size[0] : node.pos[0];
		const y1 = node.pos[1] + 33 + this.connecting.slot * 25;
		const controlOffset = Math.min(Math.abs(worldMouse[0] - x1) * 0.5, 400);
		const cx1 = x1 + (this.connecting.isOutput ? controlOffset : -controlOffset);
		const cx2 = worldMouse[0] + (this.connecting.isOutput ? -controlOffset : controlOffset);

		this.ctx.strokeStyle = colors.accentGreen;
		this.ctx.lineWidth = 2.5 / this.camera.scale;
		this.ctx.setLineDash([10 / this.camera.scale, 5 / this.camera.scale]);
		this.ctx.beginPath();
		this.ctx.moveTo(x1, y1);
		this.ctx.bezierCurveTo(cx1, y1, cx2, worldMouse[1], worldMouse[0], worldMouse[1]);
		this.ctx.stroke();
		this.ctx.setLineDash([]);
	}

	adjustColorBrightness(color, amount) {
		const hex = color.replace('#', ''), num = parseInt(hex, 16);
		const r = Math.max(0, Math.min(255, (num >> 16) + amount));
		const g = Math.max(0, Math.min(255, ((num >> 8) & 0x00FF) + amount));
		const b = Math.max(0, Math.min(255, (num & 0x0000FF) + amount));
		return '#' + ((r << 16) | (g << 8) | b).toString(16).padStart(6, '0');
	}

	// === EXPORT/IMPORT ===
	exportGraph() {
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
	}

	exportConfig() {
		const schemas = Object.keys(this.graph.schemas);
		if (schemas.length === 0) { this.showError('No schemas registered'); return; }
		let targetSchema = schemas.find(s => this.graph.schemas[s].rootType) || schemas[0];
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
	}

	buildConfig(schemaName) {
		const schemaInfo = this.graph.schemas[schemaName];
		const config = {}, nodesByType = {}, nodeToIndex = new Map();
		const fieldMapping = schemaInfo.fieldMapping;

		for (const node of this.graph.nodes) {
			if (node.schemaName !== schemaName) continue;
			if (!nodesByType[node.modelName]) nodesByType[node.modelName] = [];
			nodeToIndex.set(node, { modelName: node.modelName, index: nodesByType[node.modelName].length });
			nodesByType[node.modelName].push(node);
		}

		for (const modelName in nodesByType) {
			const fieldName = fieldMapping.modelToField[modelName];
			config[fieldName] = nodesByType[modelName].map(node => {
				node.onExecute();
				const data = node.outputs[0].value || {};
				return this.processNodeDataWithIndices(data, nodeToIndex, fieldMapping);
			});
		}
		return config;
	}

	processNodeDataWithIndices(data, nodeToIndex, fieldMapping) {
		const result = {};
		for (const key in data) {
			if (!data.hasOwnProperty(key)) continue;
			const value = data[key];
			result[key] = Array.isArray(value) ? value.map(v => this.valueToIndexOrData(v, nodeToIndex)) : this.valueToIndexOrData(value, nodeToIndex);
		}
		return result;
	}

	valueToIndexOrData(value, nodeToIndex) {
		if (value === null || value === undefined || typeof value !== 'object' || Array.isArray(value)) return value;
		for (const [node, info] of nodeToIndex.entries()) if (node.outputs?.[0]?.value === value) return info.index;
		if (typeof value === 'string' && ((value.startsWith('{') && value.endsWith('}')) || (value.startsWith('[') && value.endsWith(']')))) {
			try { return JSON.parse(value); } catch { return value; }
		}
		const processed = {};
		for (const k in value) if (value.hasOwnProperty(k)) processed[k] = this.valueToIndexOrData(value[k], nodeToIndex);
		return processed;
	}

	// ================================================================
	// BUTTON STACK MANAGEMENT
	// ================================================================

	addNodeButton(node, stack, config) {
		if (!node || !config) return false;
		
		const button = {
			id: config.id || `btn_${Date.now()}`,
			label: config.label || '',
			icon: config.icon || '',
			callback: config.callback || (() => {}),
			enabled: config.enabled !== false,
			visible: config.visible !== false,
			style: {
				bg: config.bg || 'rgba(70,162,218,0.3)',
				bgHover: config.bgHover || 'rgba(70,162,218,0.5)',
				text: config.text || '#fff',
				border: config.border || 'rgba(70,162,218,0.6)'
			}
		};
		
		if (!node._buttonStacks) node._buttonStacks = { top: [], bottom: [] };
		
		const stackArr = node._buttonStacks[stack] || node._buttonStacks.bottom;
		const idx = stackArr.findIndex(b => b.id === button.id);
		if (idx !== -1) stackArr[idx] = button;
		else stackArr.push(button);
		
		this._recalculateNodeSize(node);
		this.draw();
		return button.id;
	}

	removeNodeButton(node, buttonId) {
		if (!node?._buttonStacks) return false;
		for (const stack of ['top', 'bottom']) {
			const idx = node._buttonStacks[stack].findIndex(b => b.id === buttonId);
			if (idx !== -1) {
				node._buttonStacks[stack].splice(idx, 1);
				this._recalculateNodeSize(node);
				this.draw();
				return true;
			}
		}
		return false;
	}

	_recalculateNodeSize(node) {
		const baseHeight = 35;
		const slotHeight = 25;
		const stackHeight = 28;
		
		const maxSlots = Math.max(node.inputs?.length || 0, node.outputs?.length || 0, 1);
		let height = baseHeight + maxSlots * slotHeight;
		
		if (node._buttonStacks?.top?.length) height += stackHeight;
		if (node._buttonStacks?.bottom?.length) height += stackHeight;
		if (node._dropZone?.enabled) height += 10;
		
		node.size[1] = Math.max(80, height);
	}

	_getButtonStackLayout(node) {
		const x = node.pos[0];
		const y = node.pos[1];
		const w = node.size[0];
		const h = node.size[1];
		const padding = 4;
		const stackHeight = 24;
		const headerHeight = 28;
		
		const hasTop = node._buttonStacks?.top?.length > 0;
		const hasBottom = node._buttonStacks?.bottom?.length > 0;
		
		return {
			top: hasTop ? {
				area: { x: x + padding, y: y + headerHeight, w: w - padding * 2, h: stackHeight },
				buttons: this._layoutButtonsInStack(node._buttonStacks.top, x + padding, y + headerHeight, w - padding * 2, stackHeight)
			} : null,
			bottom: hasBottom ? {
				area: { x: x + padding, y: y + h - stackHeight - padding, w: w - padding * 2, h: stackHeight },
				buttons: this._layoutButtonsInStack(node._buttonStacks.bottom, x + padding, y + h - stackHeight - padding, w - padding * 2, stackHeight)
			} : null,
			contentY: y + headerHeight + (hasTop ? stackHeight + 2 : 0)
		};
	}

	_layoutButtonsInStack(buttons, areaX, areaY, areaW, areaH) {
		if (!buttons?.length) return [];
		
		const padding = 3;
		const gap = 4;
		const btnHeight = areaH - padding * 2;
		
		// Calculate total width needed
		const visibleBtns = buttons.filter(b => b.visible);
		const totalGaps = (visibleBtns.length - 1) * gap;
		const availableWidth = areaW - padding * 2 - totalGaps;
		const btnWidth = Math.min(70, availableWidth / visibleBtns.length);
		
		// Center the buttons
		const totalWidth = visibleBtns.length * btnWidth + totalGaps;
		let startX = areaX + (areaW - totalWidth) / 2;
		
		return visibleBtns.map((btn, i) => ({
			btn,
			bounds: {
				x: startX + i * (btnWidth + gap),
				y: areaY + padding,
				w: btnWidth,
				h: btnHeight
			}
		}));
	}

	// ================================================================
	// DROP ZONE MANAGEMENT
	// ================================================================

	setNodeDropZone(node, config) {
		if (!node || !config) return false;
		node._dropZone = {
			accept: config.accept || '*',
			area: config.area || DropZoneArea.CONTENT,
			callback: config.callback || (() => {}),
			label: config.label || 'Drop file here',
			enabled: config.enabled !== false
		};
		this._recalculateNodeSize(node);
		return true;
	}

	removeNodeDropZone(node) {
		if (!node) return false;
		delete node._dropZone;
		this._recalculateNodeSize(node);
		return true;
	}

	_getDropZoneBounds(node) {
		const layout = this._getButtonStackLayout(node);
		const x = node.pos[0], y = node.pos[1];
		const w = node.size[0], h = node.size[1];
		const hasBottom = node._buttonStacks?.bottom?.length > 0;
		
		if (node._dropZone?.area === DropZoneArea.FULL) {
			return { x, y, w, h };
		}
		// Content area between stacks
		const topY = layout.contentY;
		const bottomY = hasBottom ? layout.bottom.area.y : y + h;
		return { x: x + 4, y: topY, w: w - 8, h: bottomY - topY - 4 };
	}

	_findDropTargetNode(wx, wy) {
		for (const node of this.graph.nodes) {
			if (!node._dropZone?.enabled) continue;
			const b = this._getDropZoneBounds(node);
			if (wx >= b.x && wx <= b.x + b.w && wy >= b.y && wy <= b.y + b.h) return node;
		}
		return null;
	}

	_filterFilesByAccept(files, accept) {
		if (!accept || accept === '*' || accept === '*/*') return files;
		const acceptList = Array.isArray(accept) ? accept : accept.split(',').map(s => s.trim());
		return files.filter(file => {
			for (const acc of acceptList) {
				if (acc.startsWith('.') && file.name.toLowerCase().endsWith(acc.toLowerCase())) return true;
				if (acc.includes('/')) {
					if (acc.endsWith('/*') && file.type.startsWith(acc.slice(0, -1))) return true;
					if (file.type === acc) return true;
				}
			}
			return false;
		});
	}

	// ================================================================
	// CALLBACK REGISTRY
	// ================================================================

	registerCallback(id, fn) {
		if (typeof fn !== 'function') return false;
		this._callbackRegistry[id] = fn;
		return true;
	}

	unregisterCallback(id) {
		delete this._callbackRegistry[id];
	}

	_resolveCallback(callbackId) {
		if (this._callbackRegistry[callbackId]) return this._callbackRegistry[callbackId];
		
		const builtins = {
			'file_input': (node) => {
				const input = document.createElement('input');
				input.type = 'file';
				input.accept = node._dropZone?.accept || '*';
				input.onchange = (e) => {
					const files = Array.from(e.target.files);
					if (files.length && node._dropZone?.callback) node._dropZone.callback(node, files, e);
				};
				input.click();
			},
			'clear_data': (node) => {
				this.eventBus.emit('data:cleared', { nodeId: node.id });
				this.draw();
			}
		};
		
		return builtins[callbackId] || ((node, event, btn) => {
			this.eventBus.emit('node:buttonClicked', { nodeId: node.id, buttonId: btn?.id || callbackId, node, btn });
		});
	}

	_resolveDropCallback(callbackId) {
		if (this._callbackRegistry[callbackId]) return this._callbackRegistry[callbackId];
		return (node, files) => {
			this.eventBus.emit('node:fileDrop', { nodeId: node.id, files, action: callbackId, node });
		};
	}

	_setupFileDrop() {
		const canvas = this.canvas;
		
		canvas.addEventListener('dragover', (e) => {
			if (this.isLocked) return;
			const rect = canvas.getBoundingClientRect();
			const [wx, wy] = this.screenToWorld(
				(e.clientX - rect.left) / rect.width * canvas.width,
				(e.clientY - rect.top) / rect.height * canvas.height
			);
			const node = this._findDropTargetNode(wx, wy);
			
			if (node && node._dropZone?.enabled) {
				e.preventDefault();
				e.stopImmediatePropagation();  // <-- Stop other handlers
				e.dataTransfer.dropEffect = 'copy';
				
				// Remove canvas-level highlight
				canvas.classList.remove('sg-file-drag-over');
				
				if (this._activeDropNode !== node) {
					this._activeDropNode = node;
					this.draw();
				}
			} else if (this._activeDropNode) {
				this._activeDropNode = null;
				this.draw();
			}
		}, true);  // capture phase

		canvas.addEventListener('dragleave', (e) => {
			const rect = canvas.getBoundingClientRect();
			if (e.clientX < rect.left || e.clientX > rect.right || 
				e.clientY < rect.top || e.clientY > rect.bottom) {
				if (this._activeDropNode) { 
					this._activeDropNode = null; 
					this.draw(); 
				}
			}
		});
		
		canvas.addEventListener('drop', (e) => {
			if (this.isLocked) return;
			
			const rect = canvas.getBoundingClientRect();
			const [wx, wy] = this.screenToWorld(
				(e.clientX - rect.left) / rect.width * canvas.width,
				(e.clientY - rect.top) / rect.height * canvas.height
			);
			const node = this._findDropTargetNode(wx, wy);
			
			if (node && node._dropZone?.enabled) {
				e.preventDefault();
				e.stopImmediatePropagation();  // <-- Stop other handlers
				
				// Remove canvas-level highlight
				canvas.classList.remove('sg-file-drag-over');
				
				const files = this._filterFilesByAccept(
					Array.from(e.dataTransfer.files), 
					node._dropZone.accept
				);
				
				if (files.length && node._dropZone.callback) {
					node._dropZone.callback(node, files, e);
				}
				
				this._activeDropNode = null;
				this.draw();
				return;  // Don't let other handlers process this
			}
			
			this._activeDropNode = null;
			this.draw();
		}, true);  // capture phase
	}

	_drawButtonStacks(node, colors) {
		const layout = this._getButtonStackLayout(node);
		if (!layout.top && !layout.bottom) return;
		
		const ctx = this.ctx;
		const textScale = this.getTextScale();
		const style = this.drawingStyleManager.getStyle();
		
		for (const stackName of ['top', 'bottom']) {
			const stack = layout[stackName];
			if (!stack) continue;
			
			// Draw stack area background
			ctx.fillStyle = 'rgba(0,0,0,0.2)';
			ctx.beginPath();
			ctx.roundRect(stack.area.x, stack.area.y, stack.area.w, stack.area.h, 4);
			ctx.fill();
			
			// Draw buttons
			for (const { btn, bounds } of stack.buttons) {
				const isHovered = this._hoveredButton?.nodeId === node.id && this._hoveredButton?.buttonId === btn.id;
				
				ctx.fillStyle = isHovered ? btn.style.bgHover : btn.style.bg;
				ctx.beginPath();
				ctx.roundRect(bounds.x, bounds.y, bounds.w, bounds.h, 3);
				ctx.fill();
				
				ctx.strokeStyle = btn.style.border;
				ctx.lineWidth = 1 / this.camera.scale;
				ctx.stroke();
				
				ctx.fillStyle = btn.enabled ? btn.style.text : 'rgba(255,255,255,0.3)';
				ctx.font = `${9 * textScale}px ${style.textFont}`;
				ctx.textAlign = 'center';
				ctx.textBaseline = 'middle';
				ctx.fillText(btn.icon ? `${btn.icon} ${btn.label}` : btn.label, bounds.x + bounds.w / 2, bounds.y + bounds.h / 2);
			}
		}
	}

	_drawDropZoneHighlight(node) {
		if (!node._dropZone) return;
		
		const ctx = this.ctx;
		const bounds = this._getDropZoneBounds(node);
		const textScale = this.getTextScale();
		const isActive = this._activeDropNode === node;
		const isEnabled = node._dropZone.enabled;
		
		// Always show a subtle indicator for disabled dropzones
		if (!isEnabled) {
			ctx.fillStyle = 'rgba(220, 96, 104, 0.08)';
			ctx.beginPath();
			ctx.roundRect(bounds.x, bounds.y, bounds.w, bounds.h, 4);
			ctx.fill();
			
			ctx.strokeStyle = 'rgba(220, 96, 104, 0.3)';
			ctx.lineWidth = 1 / this.camera.scale;
			ctx.setLineDash([4 / this.camera.scale, 4 / this.camera.scale]);
			ctx.stroke();
			ctx.setLineDash([]);
			
			ctx.fillStyle = 'rgba(220, 96, 104, 0.6)';
			ctx.font = `${9 * textScale}px sans-serif`;
			ctx.textAlign = 'center';
			ctx.textBaseline = 'middle';
			ctx.fillText(node._dropZone.label, bounds.x + bounds.w / 2, bounds.y + bounds.h / 2);
			return;
		}
		
		if (!isActive) return;
		
		ctx.fillStyle = 'rgba(146, 208, 80, 0.15)';
		ctx.beginPath();
		ctx.roundRect(bounds.x, bounds.y, bounds.w, bounds.h, 4);
		ctx.fill();
		
		ctx.strokeStyle = '#92d050';
		ctx.lineWidth = 2 / this.camera.scale;
		ctx.setLineDash([6 / this.camera.scale, 4 / this.camera.scale]);
		ctx.stroke();
		ctx.setLineDash([]);
		
		ctx.fillStyle = '#92d050';
		ctx.font = `bold ${11 * textScale}px sans-serif`;
		ctx.textAlign = 'center';
		ctx.textBaseline = 'middle';
		ctx.fillText(node._dropZone.label, bounds.x + bounds.w / 2, bounds.y + bounds.h / 2);
	}

	_applyDecoratorsToNode(node) {
		if (!node?.schemaName || !node?.modelName) return;
		
		const decorators = this._schemaDecorators[node.schemaName]?.[node.modelName];
		if (!decorators) return;
		
		// Apply node info
		if (decorators.info) {
			node.nodeInfo = decorators.info;
			// Use custom title if provided
			if (decorators.info.title) {
				node.displayTitle = decorators.info.title;
			}
		}
		
		// Check completeness before applying interactive elements
		const completeness = this._getNodeCompleteness(node);
		const isComplete = completeness.complete;
		
		// Apply buttons
		for (const cfg of decorators.buttons || []) {
			const stack = (cfg.position === 'top' || cfg.position === 'header') ? 'top' : 'bottom';
			this.addNodeButton(node, stack, {
				id: cfg.id,
				label: cfg.label || '',
				icon: cfg.icon || '',
				enabled: cfg.enabled !== false && isComplete,  // Disable if incomplete
				callback: this._resolveCallback(cfg.callback || cfg.id)
			});
		}
		
		// Apply dropzone - disable if incomplete
		if (decorators.dropzone) {
			this.setNodeDropZone(node, {
				accept: decorators.dropzone.accept || '*',
				area: decorators.dropzone.area || 'content',
				label: isComplete ? (decorators.dropzone.label || 'Drop file here') : 'Complete required fields first',
				enabled: isComplete,
				callback: this._resolveDropCallback(decorators.dropzone.callback || 'emit_event')
			});
		}
		
		// Mark chat nodes
		if (decorators.chat) {
			node.isChat = true;
			node.chatConfig = decorators.chat;
		}
	}

	// ================================================================
	// NODE COMPLETENESS
	// ================================================================

	_isFieldRequired(node, slotIdx) {
		const meta = node.inputMeta?.[slotIdx];
		if (!meta) return false;
		
		// Check if type contains Optional
		const typeStr = meta.type || '';
		if (typeStr.includes('Optional[')) return false;
		
		// Check nativeInputs for optional flag
		if (node.nativeInputs?.[slotIdx]?.optional) return false;
		
		return true;
	}

	_isFieldFilled(node, slotIdx) {
		const input = node.inputs[slotIdx];
		if (!input) return true;
		
		// Connected = filled
		if (input.link) return true;
		
		// Multi-input with connections = filled
		if (node.multiInputs?.[slotIdx]?.links?.length > 0) return true;
		
		// Check native value
		if (node.nativeInputs?.[slotIdx] !== undefined) {
			const val = node.nativeInputs[slotIdx].value;
			if (val === null || val === undefined || val === '') return false;
			return true;
		}
		
		// Not a native input, no connection = not filled
		return false;
	}

	_getNodeCompleteness(node) {
		const result = {
			complete: true,
			missingFields: [],
			filledFields: [],
			optionalEmpty: []
		};
		
		for (let i = 0; i < node.inputs.length; i++) {
			const fieldName = node.inputMeta?.[i]?.name || node.inputs[i]?.name || `input_${i}`;
			const required = this._isFieldRequired(node, i);
			const filled = this._isFieldFilled(node, i);
			
			if (filled) {
				result.filledFields.push(fieldName);
			} else if (required) {
				result.complete = false;
				result.missingFields.push(fieldName);
			} else {
				result.optionalEmpty.push(fieldName);
			}
		}
		
		return result;
	}

	_checkAllNodesCompleteness() {
		const results = {};
		for (const node of this.graph.nodes) {
			results[node.id] = this._getNodeCompleteness(node);
		}
		return results;
	}

	_emitCompletenessChanged(node) {
		const completeness = this._getNodeCompleteness(node);
		this.eventBus.emit('node:completenessChanged', {
			nodeId: node.id,
			...completeness
		});
	}

	_refreshNodeInteractivity(node) {
		const decorators = this._schemaDecorators[node.schemaName]?.[node.modelName];
		if (!decorators) return;
		
		const completeness = this._getNodeCompleteness(node);
		const isComplete = completeness.complete;
		
		// Update button enabled states
		if (node._buttonStacks) {
			for (const stack of ['top', 'bottom']) {
				for (const btn of node._buttonStacks[stack] || []) {
					// Find original config to check if it should be enabled
					const originalConfig = decorators.buttons?.find(b => b.id === btn.id);
					btn.enabled = (originalConfig?.enabled !== false) && isComplete;
				}
			}
		}
		
		// Update dropzone
		if (node._dropZone && decorators.dropzone) {
			node._dropZone.enabled = isComplete;
			node._dropZone.label = isComplete 
				? (decorators.dropzone.label || 'Drop file here') 
				: 'Complete required fields first';
		}
		
		this._emitCompletenessChanged(node);
		this.draw();
	}

	// === API ===
	_createAPI() {
		const self = this;
		return {
			lock: {
				lock: (r, p) => self.lock(r, p),
				unlock: () => self.unlock(),
				isLocked: () => self.isLocked,
				getReason: () => self.lockReason
			},
			schema: {
				// register: (name, code, indexType = 'int', rootType = null) => {
				// 	self.graph.removeSchema(name);
				// 	const success = self.graph.registerSchema(name, code, indexType, rootType);
				// 	if (success) { self.ui?.update?.schemaList?.(); self.ui?.update?.nodeTypesList?.(); self.draw(); }
				// 	return success;
				// },
				// remove: (name) => {
				// 	const success = self.graph.removeSchema(name);
				// 	if (success) { self.ui?.update?.schemaList?.(); self.ui?.update?.nodeTypesList?.(); self.draw(); }
				// 	return success;
				// },
				list: () => self.graph.getRegisteredSchemas(),
				info: (name) => self.graph.getSchemaInfo(name),
				isWorkflow: (name) => self.graph.isWorkflowSchema(name),
				enable: (name) => self.graph.enableSchema(name),
				disable: (name) => self.graph.disableSchema(name),
				toggle: (name) => self.graph.toggleSchema(name),
				isEnabled: (name) => self.graph.isSchemaEnabled(name),
				getEnabled: () => self.graph.getEnabledSchemas()
			},
			node: {
				create: (type, x = 0, y = 0) => { try { const node = self.graph.createNode(type); node.pos = [x, y]; self.draw(); return node; } catch (e) { self.showError('Failed to create node: ' + e.message); return null; } },
				delete: (nodeOrId) => { const node = typeof nodeOrId === 'string' ? self.graph.getNodeById(nodeOrId) : nodeOrId; if (!node) return false; self.removeNode(node); return true; },
				select: (nodeOrId, add = false) => { const node = typeof nodeOrId === 'string' ? self.graph.getNodeById(nodeOrId) : nodeOrId; if (!node) return false; self.selectNode(node, add); return true; },
				list: () => [...self.graph.nodes],
				getById: (id) => self.graph.getNodeById(id),
				getSelected: () => Array.from(self.selectedNodes),
				clearSelection: () => self.clearSelection()
			},
			link: {
				create: (sourceOrId, sourceSlot, targetOrId, targetSlot) => {
					const sourceNode = typeof sourceOrId === 'string' ? self.graph.getNodeById(sourceOrId) : sourceOrId;
					const targetNode = typeof targetOrId === 'string' ? self.graph.getNodeById(targetOrId) : targetOrId;
					if (!sourceNode || !targetNode) return null;
					const link = self.graph.connect(sourceNode, sourceSlot, targetNode, targetSlot);
					if (link) { self.eventBus.emit('link:created', { linkId: link.id }); self.draw(); }
					return link;
				},
				delete: (linkId) => { const link = self.graph.links[linkId]; if (!link) return false; const targetNode = self.graph.getNodeById(link.target_id); if (targetNode) self.removeLink(linkId, targetNode, link.target_slot); return true; },
				list: () => ({ ...self.graph.links })
			},
			graph: {
				export: (includeCamera = true) => self.graph.serialize(includeCamera, self.camera),
				import: (data, restoreCamera = true) => { try { self.graph.deserialize(data, restoreCamera, self.camera); self.ui?.update?.schemaList?.(); self.ui?.update?.nodeTypesList?.(); if (restoreCamera) self.eventBus.emit('ui:update', { id: 'zoomLevel', content: Math.round(self.camera.scale * 100) + '%' }); self.draw(); self.eventBus.emit('graph:imported', {}); return true; } catch (e) { self.showError('Import failed: ' + e.message); return false; } },
				download: () => self.exportGraph(),
				clear: () => { self.graph.nodes = []; self.graph.links = {}; self.graph._nodes_by_id = {}; self.graph.last_link_id = 0; self.clearSelection(); self.draw(); }
			},
			workflow: {
				registerSchema: (name, code) => {
					// Parse workflow schema
					const parser = new WorkflowSchemaParser();
					const parsed = parser.parse(code);
					
					// Parse decorators
					const decorators = self._decoratorParser.parse(code);
					self._schemaDecorators[name] = decorators;
					
					// Store schema
					if (!self.graph.schemas) self.graph.schemas = {};
					self.graph.schemas[name] = { 
						code, 
						parsed: parsed.models,
						isWorkflow: true, 
						fieldRoles: parsed.fieldRoles, 
						defaults: parsed.defaults,
						enabled: false 
					};
					
					// Create factory
					if (!self.graph.workflowFactories) self.graph.workflowFactories = {};
					const factory = new WorkflowNodeFactory(self.graph, parsed, name);
					factory.app = self;
					self.graph.workflowFactories[name] = factory;
					
					// Register node types as constructors (not plain functions)
					for (const modelName of Object.keys(parsed.models)) {
						const fullType = `${name}.${modelName}`;
						
						// Capture variables for closure
						const capturedFactory = factory;
						const capturedModelName = modelName;
						
						// Create a constructor function
						function WorkflowNodeType(nodeData = {}) {
							const node = capturedFactory.createNode(capturedModelName, nodeData);
							Object.assign(this, node);
							Object.setPrototypeOf(this, node);
						}
						
						WorkflowNodeType.title = modelName.replace(/([A-Z])/g, ' $1').trim();
						WorkflowNodeType.type = fullType;
						
						self.graph.nodeTypes[fullType] = WorkflowNodeType;
					}
					
					self.eventBus.emit(GraphEvents.SCHEMA_REGISTERED, { schemaName: name });
					console.log(`✔ Schema registered: ${name} (${Object.keys(parsed.models).length} models, ${Object.keys(decorators).length} decorated)`);
					return true;
				},

				import: (data, schemaName, options) => { try { self.graph.importWorkflow(data, schemaName, options); self.ui?.update?.schemaList?.(); self.ui?.update?.nodeTypesList?.(); self.draw(); return true; } catch (e) { self.showError('Workflow import failed: ' + e.message); return false; } },
				export: (schemaName, workflowInfo, options) => self.graph.exportWorkflow(schemaName, workflowInfo, options),
				download: (schemaName, workflowInfo = {}, options = {}) => {
					const workflow = self.graph.exportWorkflow(schemaName, workflowInfo, options);
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
					self.eventBus.emit('workflow:exported', {});
				},
				isWorkflowSchema: (name) => self.graph.isWorkflowSchema(name),

				getMultiInputKeys: (node, fieldName) => self._getMultiInputKeys(node, fieldName),
				getMultiOutputKeys: (node, fieldName) => self._getMultiOutputKeys(node, fieldName),
				addMultiInputSlot: (node, fieldName, key) => self._addMultiInputSlot(node, fieldName, key),
				removeMultiInputSlot: (node, fieldName, key) => self._removeMultiInputSlot(node, fieldName, key),
				addMultiOutputSlot: (node, fieldName, key) => self._addMultiOutputSlot(node, fieldName, key),
				removeMultiOutputSlot: (node, fieldName, key) => self._removeMultiOutputSlot(node, fieldName, key),
				renameMultiInputSlot: (node, fieldName, oldKey, newKey) => self._renameMultiInputSlot(node, fieldName, oldKey, newKey),
				renameMultiOutputSlot: (node, fieldName, oldKey, newKey) => self._renameMultiOutputSlot(node, fieldName, oldKey, newKey),
			},
			view: {
				center: () => self.centerView(),
				resetZoom: () => self.resetZoom(),
				setZoom: (scale) => { self.camera.scale = Math.max(0.1, Math.min(5, scale)); self.eventBus.emit('ui:update', { id: 'zoomLevel', content: Math.round(self.camera.scale * 100) + '%' }); self.draw(); },
				getZoom: () => self.camera.scale,
				setPosition: (x, y) => { self.camera.x = x; self.camera.y = y; self.draw(); },
				getPosition: () => { return { ...this.camera }; },
				pan: (dx, dy) => { self.camera.x += dx; self.camera.y += dy; self.draw(); },
				reset: () => { self.api.view.setPosition(0, 0); self.resetZoom(); }

			},
			layout: { apply: (type) => self.applyLayout(type) },
			theme: { cycle: () => self.cycleTheme(), get: () => self.themes[self.currentThemeIndex], set: (t) => { const idx = self.themes.indexOf(t); if (idx !== -1) { self.currentThemeIndex = idx; self.applyTheme(t); localStorage.setItem('schemagraph-theme', t); self.draw(); } } },
			style: { set: (s) => { self.drawingStyleManager.setStyle(s); self.draw(); }, get: () => self.drawingStyleManager.getCurrentStyleName(), list: () => Object.keys(self.drawingStyleManager.styles) },
			analytics: { getMetrics: () => self.analytics.getMetrics(), getSession: () => self.analytics.getSessionMetrics(), endSession: () => self.analytics.endSession() },
			voice: { start: () => self.voiceController.startListening(), stop: () => self.voiceController.stopListening(), isListening: () => self.voiceController.isListening },

			events: {
				on: (event, cb) => self.eventBus.on(event, cb),
				once: (event, cb) => self.eventBus.once(event, cb),
				off: (event, cb) => self.eventBus.off(event, cb),
				emit: (event, data) => self.eventBus.emit(event, data),
				types: GraphEvents,
				enableDebug: () => self.eventBus.enableDebug(),
				disableDebug: () => self.eventBus.disableDebug(),
				onNodeCreated: (cb) => self.eventBus.on(GraphEvents.NODE_CREATED, cb),
				onNodeRemoved: (cb) => self.eventBus.on(GraphEvents.NODE_REMOVED, cb),
				onNodeMoved: (cb) => self.eventBus.on(GraphEvents.NODE_MOVED, cb),
				onLinkCreated: (cb) => self.eventBus.on(GraphEvents.LINK_CREATED, cb),
				onLinkRemoved: (cb) => self.eventBus.on(GraphEvents.LINK_REMOVED, cb),
				onGraphChanged: (cb) => self.eventBus.on(GraphEvents.GRAPH_CHANGED, cb),
				onFieldChanged: (cb) => self.eventBus.on(GraphEvents.FIELD_CHANGED, cb),
				onSelectionChanged: (cb) => self.eventBus.on(GraphEvents.SELECTION_CHANGED, cb)
			},

			interactive: {
				addButton: (node, stack, config) => self.addNodeButton(node, stack, config),
				removeButton: (node, buttonId) => self.removeNodeButton(node, buttonId),
				setDropZone: (node, config) => self.setNodeDropZone(node, config),
				removeDropZone: (node) => self.removeNodeDropZone(node),
				registerCallback: (id, fn) => self.registerCallback(id, fn),
				ButtonStack,
				DropZoneArea
			},

			decorators: {
				parse: (code) => self._decoratorParser.parse(code),
				getForModel: (schema, model) => self._schemaDecorators[schema]?.[model],
				applyToNode: (node) => self._applyDecoratorsToNode(node)
			},

			tooltips: {
				enableNodeTooltips: () => { self._nodeTooltipsEnabled = true; },
				disableNodeTooltips: () => { self._nodeTooltipsEnabled = false; self._hideNodeHeaderTooltip(); },
				isNodeTooltipsEnabled: () => self._nodeTooltipsEnabled,
				
				enableFieldTooltips: () => { self._fieldTooltipsEnabled = true; },
				disableFieldTooltips: () => { self._fieldTooltipsEnabled = false; self._hideTooltip(); },
				isFieldTooltipsEnabled: () => self._fieldTooltipsEnabled,
				
				enableAll: () => { self._nodeTooltipsEnabled = true; self._fieldTooltipsEnabled = true; },
				disableAll: () => { 
					self._nodeTooltipsEnabled = false; 
					self._fieldTooltipsEnabled = false; 
					self._hideTooltip(); 
					self._hideNodeHeaderTooltip(); 
				}
			},
			
			completeness: {
				check: (nodeOrId) => {
					const node = typeof nodeOrId === 'string' ? self.graph.getNodeById(nodeOrId) : nodeOrId;
					return node ? self._getNodeCompleteness(node) : null;
				},
				checkAll: () => self._checkAllNodesCompleteness(),
				isComplete: (nodeOrId) => {
					const node = typeof nodeOrId === 'string' ? self.graph.getNodeById(nodeOrId) : nodeOrId;
					return node ? self._getNodeCompleteness(node).complete : false;
				},
				refresh: (nodeOrId) => {
					const node = typeof nodeOrId === 'string' ? self.graph.getNodeById(nodeOrId) : nodeOrId;
					if (node) self._refreshNodeInteractivity(node);
				},
				refreshAll: () => {
					for (const node of self.graph.nodes) {
						self._refreshNodeInteractivity(node);
					}
				}
			},
		
			extensions: {
				get: (name) => self.extensions.get(name),
				list: () => self.extensions.list(),
				has: (name) => self.extensions.has(name),
				registry: self.extensions
			},
		};
	}

	_createUI() {
		const self = this;
		return {
			init: () => {
				self.ui.buttons.setupAll();
				self.ui.update.schemaList();
				self.ui.update.nodeTypesList();
				self.ui.update.textScaling();
				self.ui.update.drawingStyle();
			},
			util: {
				resizeCanvas: () => {
					const container = self.canvas.parentElement;
					if (container) {
						self.canvas.width = container.clientWidth;
						self.canvas.height = container.clientHeight;
						self.draw();
					}
				}
			},
			update: {
				schemaList: () => {
					const listEl = document.getElementById('sg-schemaList');
					if (listEl) listEl.textContent = self.graph.getRegisteredSchemas().join(', ') || 'None';
				},
				nodeTypesList: () => {
					const listEl = document.getElementById('sg-nodeTypesList');
					if (listEl) listEl.textContent = Object.keys(self.graph.nodeTypes).join(', ') || 'None';
				},
				textScaling: () => {
					const label = document.getElementById('sg-textScalingLabel');
					const btn = document.getElementById('sg-textScalingToggle');
					if (label) label.textContent = self.textScalingMode === 'scaled' ? 'Text: Scaled' : 'Text: Fixed';
					if (btn) btn.classList.toggle('active', self.textScalingMode === 'scaled');
				},
				drawingStyle: () => {
					const select = document.getElementById('sg-drawingStyleSelect');
					if (select) select.value = self.drawingStyleManager.getCurrentStyleName();
				},
				analytics: () => {
					const metrics = self.analytics.getSessionMetrics();
					const m = self.analytics.getMetrics();
					document.getElementById('sg-sessionId') && (document.getElementById('sg-sessionId').textContent = metrics.sessionId);
					document.getElementById('sg-sessionDuration') && (document.getElementById('sg-sessionDuration').textContent = Math.round(metrics.duration / 1000) + 's');
					document.getElementById('sg-totalEvents') && (document.getElementById('sg-totalEvents').textContent = metrics.events);
					document.getElementById('sg-nodesCreated') && (document.getElementById('sg-nodesCreated').textContent = m.nodeCreated);
					document.getElementById('sg-nodesDeleted') && (document.getElementById('sg-nodesDeleted').textContent = m.nodeDeleted);
					document.getElementById('sg-linksCreated') && (document.getElementById('sg-linksCreated').textContent = m.linkCreated);
					document.getElementById('sg-linksDeleted') && (document.getElementById('sg-linksDeleted').textContent = m.linkDeleted);
				}
			},
			buttons: {
				setupAll: () => {
					// Upload Schema
					document.getElementById('sg-uploadSchemaBtn')?.addEventListener('click', () => document.getElementById('sg-uploadSchemaFile')?.click());
					document.getElementById('sg-uploadSchemaFile')?.addEventListener('change', (e) => {
						const file = e.target.files?.[0];
						if (!file) return;
						const reader = new FileReader();
						reader.onload = (ev) => {
							self.pendingSchemaCode = ev.target.result;
							document.getElementById('sg-schemaNameInput').value = file.name.replace('.py', '');
							document.getElementById('sg-schemaDialog')?.classList.add('show');
						};
						reader.readAsText(file);
						e.target.value = '';
					});

					// Schema Dialog
					document.getElementById('sg-schemaDialogCancel')?.addEventListener('click', () => { document.getElementById('sg-schemaDialog')?.classList.remove('show'); self.pendingSchemaCode = null; });
					document.getElementById('sg-schemaDialogConfirm')?.addEventListener('click', () => {
						const name = document.getElementById('sg-schemaNameInput')?.value?.trim();
						const indexType = document.getElementById('sg-schemaIndexTypeInput')?.value?.trim() || 'int';
						const rootType = document.getElementById('sg-schemaRootTypeInput')?.value?.trim() || null;
						if (!name || !self.pendingSchemaCode) { self.showError('Name and code required'); return; }
						self.api.schema.register(name, self.pendingSchemaCode, indexType, rootType);
						document.getElementById('sg-schemaDialog')?.classList.remove('show');
						self.pendingSchemaCode = null;
					});

					// Export/Import Graph
					document.getElementById('sg-exportBtn')?.addEventListener('click', () => self.exportGraph());
					document.getElementById('sg-importBtn')?.addEventListener('click', () => document.getElementById('sg-importFile')?.click());
					document.getElementById('sg-importFile')?.addEventListener('change', (e) => {
						const file = e.target.files?.[0];
						if (!file) return;
						const reader = new FileReader();
						reader.onload = (ev) => { try { self.api.graph.import(JSON.parse(ev.target.result), true); } catch (err) { self.showError('Import failed: ' + err.message); } };
						reader.readAsText(file);
						e.target.value = '';
					});

					// Export/Import Config
					document.getElementById('sg-exportConfigBtn')?.addEventListener('click', () => self.exportConfig());
					document.getElementById('sg-importConfigBtn')?.addEventListener('click', () => document.getElementById('sg-importConfigFile')?.click());

					// Export/Import Workflow
					document.getElementById('sg-exportWorkflowBtn')?.addEventListener('click', () => {
						const schemas = self.graph.getRegisteredSchemas().filter(s => self.graph.isWorkflowSchema(s));
						if (schemas.length === 0) { self.showError('No workflow schema registered'); return; }
						self.api.workflow.download(schemas[0]);
					});
					document.getElementById('sg-importWorkflowBtn')?.addEventListener('click', () => document.getElementById('sg-importWorkflowFile')?.click());
					document.getElementById('sg-importWorkflowFile')?.addEventListener('change', (e) => {
						const file = e.target.files?.[0];
						if (!file) return;
						const reader = new FileReader();
						reader.onload = (ev) => {
							try {
								const data = JSON.parse(ev.target.result);
								const schemas = self.graph.getRegisteredSchemas().filter(s => self.graph.isWorkflowSchema(s));
								if (schemas.length === 0) { self.showError('No workflow schema registered'); return; }
								self.api.workflow.import(data, schemas[0], {});
								self.centerView();
							} catch (err) { self.showError('Import failed: ' + err.message); }
						};
						reader.readAsText(file);
						e.target.value = '';
					});

					// View
					document.getElementById('sg-centerViewBtn')?.addEventListener('click', () => self.centerView());
					document.getElementById('sg-resetZoomBtn')?.addEventListener('click', () => self.resetZoom());
					document.getElementById('sg-layoutSelect')?.addEventListener('change', (e) => { if (e.target.value) { self.applyLayout(e.target.value); e.target.value = ''; } });

					// Style
					document.getElementById('sg-drawingStyleSelect')?.addEventListener('change', (e) => { self.drawingStyleManager.setStyle(e.target.value); self.draw(); });
					document.getElementById('sg-textScalingToggle')?.addEventListener('click', () => { self.textScalingMode = self.textScalingMode === 'fixed' ? 'scaled' : 'fixed'; self.saveTextScalingMode(); self.ui.update.textScaling(); self.draw(); });
					document.getElementById('sg-themeBtn')?.addEventListener('click', () => self.cycleTheme());

					// Voice
					document.getElementById('sg-voiceStartBtn')?.addEventListener('click', () => { self.voiceController.startListening(); document.getElementById('sg-voiceStartBtn').style.display = 'none'; document.getElementById('sg-voiceStopBtn').style.display = ''; document.getElementById('sg-voiceStatus').textContent = '🎤 Listening...'; });
					document.getElementById('sg-voiceStopBtn')?.addEventListener('click', () => { self.voiceController.stopListening(); document.getElementById('sg-voiceStopBtn').style.display = 'none'; document.getElementById('sg-voiceStartBtn').style.display = ''; document.getElementById('sg-voiceStatus').textContent = ''; });
					self.eventBus.on('voice:stopped', () => { document.getElementById('sg-voiceStopBtn').style.display = 'none'; document.getElementById('sg-voiceStartBtn').style.display = ''; document.getElementById('sg-voiceStatus').textContent = ''; });

					// Analytics
					document.getElementById('sg-analyticsToggleBtn')?.addEventListener('click', () => { const panel = document.getElementById('sg-analyticsPanel'); panel?.classList.toggle('show'); if (panel?.classList.contains('show')) self.ui.update.analytics(); });
					document.getElementById('sg-analyticsCloseBtn')?.addEventListener('click', () => document.getElementById('sg-analyticsPanel')?.classList.remove('show'));
					document.getElementById('sg-refreshAnalyticsBtn')?.addEventListener('click', () => self.ui.update.analytics());
					document.getElementById('sg-exportAnalyticsBtn')?.addEventListener('click', () => {
						const data = { session: self.analytics.getSessionMetrics(), metrics: self.analytics.getMetrics(), history: self.eventBus.getHistory(null, 500) };
						const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
						const url = URL.createObjectURL(blob);
						const a = document.createElement('a');
						a.href = url;
						a.download = 'analytics-' + new Date().toISOString().slice(0, 10) + '.json';
						document.body.appendChild(a);
						a.click();
						document.body.removeChild(a);
						URL.revokeObjectURL(url);
					});

					// Resize
					window.addEventListener('resize', () => self.ui.util.resizeCanvas());
				}
			}
		};
	}
}

// Export for module systems
if (typeof module !== 'undefined' && module.exports) {
	module.exports = { 
		SchemaGraphApp, SchemaGraph, EventBus, AnalyticsService, 
		Node, WorkflowNode, Link, 
		FieldRole, DataExportMode, GraphEvents, DATA_CHANGE_EVENTS,
		WorkflowSchemaParser, WorkflowNodeFactory, WorkflowImporter, WorkflowExporter, 
		DrawingStyleManager,
		DecoratorType, ButtonStack, DropZoneArea, NodeDecoratorParser,
		ExtensionRegistry, SchemaGraphExtension, DrawUtils, extensionRegistry
	};
}

// Global exports for browser
if (typeof window !== 'undefined') {
	window.GraphEvents = GraphEvents;
	window.extensionRegistry = extensionRegistry;
	window.SchemaGraphExtension = SchemaGraphExtension;
	window.DrawUtils = DrawUtils;
	window.DecoratorType = DecoratorType;
	window.ButtonStack = ButtonStack;
	window.DropZoneArea = DropZoneArea;
}

console.log('=== SCHEMAGRAPH READY ===');
