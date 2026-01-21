// ========================================================================
// SCHEMAGRAPH CORE
// Foundation: Enums, EventBus, Node, Link, Graph base classes
// ========================================================================

console.log('[SchemaGraph] Loading core module...');

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
// NODE CLASS
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

// ========================================================================
// LINK CLASS
// ========================================================================

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
		const output = outputType.trim(), input = inputType.trim();
		if (output === input || input === 'Any' || output === 'Any') return true;

		const optMatch = input.match(/Optional\[(.+)\]/);
		if (optMatch) return this._areTypesCompatible(output, optMatch[1]);

		const unionMatch = input.match(/Union\[(.+)\]/);
		if (unionMatch) {
			for (const t of this._splitTypeString(unionMatch[1]))
				if (this._areTypesCompatible(output, t)) return true;
			return false;
		}

		if (input.indexOf('|') !== -1) {
			for (const p of input.split('|'))
				if (this._areTypesCompatible(output, p.trim())) return true;
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
		if ((output === 'str' && input === 'string') || (input === 'str' && output === 'string')) return true;
		return false;
	}

	_splitTypeString(str) {
		const result = []; let depth = 0, current = '';
		for (let i = 0; i < str.length; i++) {
			const c = str.charAt(i);
			if (c === '[') depth++; if (c === ']') depth--;
			if (c === ',' && depth === 0) { result.push(current.trim()); current = ''; }
			else current += c;
		}
		if (current) result.push(current.trim());
		return result;
	}
}

// ========================================================================
// EXPORTS
// ========================================================================

// Module exports
if (typeof module !== 'undefined' && module.exports) {
	module.exports = {
		FieldRole, DataExportMode, GraphEvents, DATA_CHANGE_EVENTS,
		DecoratorType, ButtonStack, DropZoneArea,
		EventBus, Node, Link, Graph
	};
}

// Global exports for browser (standard JS)
if (typeof window !== 'undefined') {
	window.FieldRole = FieldRole;
	window.DataExportMode = DataExportMode;
	window.GraphEvents = GraphEvents;
	window.DATA_CHANGE_EVENTS = DATA_CHANGE_EVENTS;
	window.DecoratorType = DecoratorType;
	window.ButtonStack = ButtonStack;
	window.DropZoneArea = DropZoneArea;
	window.EventBus = EventBus;
	window.Node = Node;
	window.Link = Link;
	window.Graph = Graph;
}

console.log('[SchemaGraph] Core module loaded.');
