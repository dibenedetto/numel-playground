// ========================================================================
// SCHEMAGRAPH EVENTS EXTENSION
// Adds proper node/link management API with event emission.
// Load AFTER schemagraph.js and schemagraph-extensions-core.js
// ========================================================================

const DEBUG_EVENTS = false;

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

// ========================================================================
// Event Emitter
// ========================================================================

class GraphEventEmitter {
	constructor() {
		this._listeners = new Map();
		this._onceListeners = new Map();
	}
	s
	on(event, callback) {
		if (!this._listeners.has(event)) this._listeners.set(event, new Set());
		this._listeners.get(event).add(callback);
		return () => this.off(event, callback);
	}
	
	once(event, callback) {
		if (!this._onceListeners.has(event)) this._onceListeners.set(event, new Set());
		this._onceListeners.get(event).add(callback);
		return () => this._onceListeners.get(event)?.delete(callback);
	}
	
	off(event, callback) {
		this._listeners.get(event)?.delete(callback);
		this._onceListeners.get(event)?.delete(callback);
	}
	
	emit(event, data = {}) {
		const eventData = { type: event, timestamp: Date.now(), ...data };
		
		if (DEBUG_EVENTS || (typeof window !== 'undefined' && window.DEBUG_GRAPH_EVENTS)) {
			console.log(`[GraphEvent] ${event}`, eventData);
		}
		
		this._listeners.get(event)?.forEach(cb => {
			try { cb(eventData); } catch (e) { console.error(`Event handler error [${event}]:`, e); }
		});
		
		const onceSet = this._onceListeners.get(event);
		if (onceSet) {
			onceSet.forEach(cb => {
				try { cb(eventData); } catch (e) { console.error(`Event handler error [${event}]:`, e); }
			});
			onceSet.clear();
		}
		
		if (DATA_CHANGE_EVENTS.has(event)) {
			this._listeners.get(GraphEvents.GRAPH_CHANGED)?.forEach(cb => {
				try { cb({ type: GraphEvents.GRAPH_CHANGED, originalEvent: event, ...eventData }); } catch (e) {}
			});
		}
	}
	
	removeAllListeners(event = null) {
		if (event) {
			this._listeners.delete(event);
			this._onceListeners.delete(event);
		} else {
			this._listeners.clear();
			this._onceListeners.clear();
		}
	}
}

// ========================================================================
// Extend SchemaGraph with proper node/link API
// ========================================================================

function extendSchemaGraphWithAPI(SchemaGraphClass) {
	const ensureEventBus = (graph) => {
		if (!graph.eventBus) graph.eventBus = new GraphEventEmitter();
		return graph.eventBus;
	};

	// --- addNode: Add node to graph ---
	SchemaGraphClass.prototype.addNode = function(node) {
		if (!node) return null;
		
		if (this._last_node_id === undefined) this._last_node_id = 1;
		if (node.id === undefined || node.id === null) {
			node.id = this._last_node_id++;
		} else {
			this._last_node_id = Math.max(this._last_node_id, node.id + 1);
		}
		
		node.graph = this;
		this.nodes.push(node);
		this._nodes_by_id[node.id] = node;
		
		ensureEventBus(this).emit(GraphEvents.NODE_CREATED, {
			nodeId: node.id,
			nodeType: node.type || node.title || node.constructor?.name,
			node
		});
		
		return node;
	};

	// --- removeNode: Remove node and its links ---
	SchemaGraphClass.prototype.removeNode = function(node) {
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
		
		ensureEventBus(this).emit(GraphEvents.NODE_REMOVED, { nodeId, nodeType });
		
		return true;
	};

	// --- addLink: Add link between nodes ---
	SchemaGraphClass.prototype.addLink = function(sourceNodeId, sourceSlot, targetNodeId, targetSlot, type) {
		const sourceNode = typeof sourceNodeId === 'object' ? sourceNodeId : this.getNodeById(sourceNodeId);
		const targetNode = typeof targetNodeId === 'object' ? targetNodeId : this.getNodeById(targetNodeId);
		
		if (!sourceNode || !targetNode) return null;
		
		const srcId = sourceNode.id;
		const tgtId = targetNode.id;
		
		if (this.last_link_id === undefined) this.last_link_id = 0;
		const linkId = ++this.last_link_id;
		
		const linkType = type || sourceNode.outputs?.[sourceSlot]?.type || 'Any';
		const link = new Link(linkId, srcId, sourceSlot, tgtId, targetSlot, linkType);
		
		this.links[linkId] = link;
		
		// Update source output
		if (sourceNode.outputs?.[sourceSlot]) {
			if (!sourceNode.outputs[sourceSlot].links) {
				sourceNode.outputs[sourceSlot].links = [];
			}
			sourceNode.outputs[sourceSlot].links.push(linkId);
		}
		
		// Update target input
		if (targetNode.inputs?.[targetSlot]) {
			targetNode.inputs[targetSlot].link = linkId;
		}
		
		ensureEventBus(this).emit(GraphEvents.LINK_CREATED, {
			linkId, sourceNodeId: srcId, sourceSlot, targetNodeId: tgtId, targetSlot, link
		});
		
		return link;
	};

	// --- removeLink: Remove link ---
	SchemaGraphClass.prototype.removeLink = function(linkOrId) {
		const linkId = typeof linkOrId === 'object' ? linkOrId.id : linkOrId;
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
		if (targetNode?.inputs?.[link.target_slot]?.link === linkId) {
			targetNode.inputs[link.target_slot].link = null;
		}
		
		delete this.links[linkId];
		
		ensureEventBus(this).emit(GraphEvents.LINK_REMOVED, {
			linkId,
			sourceNodeId: link.origin_id,
			sourceSlot: link.origin_slot,
			targetNodeId: link.target_id,
			targetSlot: link.target_slot
		});
		
		return true;
	};

	// --- Wrap existing methods to emit events ---
	
	const originalRegisterSchema = SchemaGraphClass.prototype.registerSchema;
	if (originalRegisterSchema) {
		SchemaGraphClass.prototype.registerSchema = function(...args) {
			const result = originalRegisterSchema.apply(this, args);
			if (result) {
				ensureEventBus(this).emit(GraphEvents.SCHEMA_REGISTERED, { 
					schemaName: args[0], isWorkflow: args[1]?.includes?.('FieldRole.') 
				});
			}
			return result;
		};
	}
	
	const originalRemoveSchema = SchemaGraphClass.prototype.removeSchema;
	if (originalRemoveSchema) {
		SchemaGraphClass.prototype.removeSchema = function(schemaName) {
			const result = originalRemoveSchema.call(this, schemaName);
			ensureEventBus(this).emit(GraphEvents.SCHEMA_REMOVED, { schemaName });
			return result;
		};
	}
	
	const originalToggleSchema = SchemaGraphClass.prototype.toggleSchema;
	if (originalToggleSchema) {
		SchemaGraphClass.prototype.toggleSchema = function(schemaName) {
			const wasEnabled = this.isSchemaEnabled?.(schemaName);
			const result = originalToggleSchema.call(this, schemaName);
			const isEnabled = this.isSchemaEnabled?.(schemaName);
			if (wasEnabled !== isEnabled) {
				ensureEventBus(this).emit(isEnabled ? GraphEvents.SCHEMA_ENABLED : GraphEvents.SCHEMA_DISABLED, { schemaName });
			}
			return result;
		};
	}
	
	const originalClear = SchemaGraphClass.prototype.clear;
	if (originalClear) {
		SchemaGraphClass.prototype.clear = function(...args) {
			const result = originalClear.apply(this, args);
			ensureEventBus(this).emit(GraphEvents.GRAPH_CLEARED, {});
			return result;
		};
	}
	
	const originalDeserialize = SchemaGraphClass.prototype.deserialize;
	if (originalDeserialize) {
		SchemaGraphClass.prototype.deserialize = function(data, ...args) {
			const result = originalDeserialize.call(this, data, ...args);
			ensureEventBus(this).emit(GraphEvents.GRAPH_LOADED, { 
				nodeCount: this.nodes?.length || 0, linkCount: Object.keys(this.links || {}).length
			});
			return result;
		};
	}
	
	const originalSerialize = SchemaGraphClass.prototype.serialize;
	if (originalSerialize) {
		SchemaGraphClass.prototype.serialize = function(...args) {
			const result = originalSerialize.apply(this, args);
			ensureEventBus(this).emit(GraphEvents.GRAPH_SAVED, { 
				nodeCount: this.nodes?.length || 0, linkCount: Object.keys(this.links || {}).length
			});
			return result;
		};
	}
	
	// Wrap createNode if it exists (emits event after original logic)
	const originalCreateNode = SchemaGraphClass.prototype.createNode;
	if (originalCreateNode) {
		SchemaGraphClass.prototype.createNode = function(type, ...args) {
			const node = originalCreateNode.call(this, type, ...args);
			if (node) {
				ensureEventBus(this).emit(GraphEvents.NODE_CREATED, { nodeId: node.id, nodeType: type, node });
			}
			return node;
		};
	}
	
	// Wrap connect if it exists
	const originalConnect = SchemaGraphClass.prototype.connect;
	if (originalConnect) {
		SchemaGraphClass.prototype.connect = function(srcNode, srcSlot, dstNode, dstSlot, ...args) {
			const link = originalConnect.call(this, srcNode, srcSlot, dstNode, dstSlot, ...args);
			if (link) {
				ensureEventBus(this).emit(GraphEvents.LINK_CREATED, { 
					linkId: link.id, sourceNodeId: srcNode?.id || srcNode, sourceSlot: srcSlot,
					targetNodeId: dstNode?.id || dstNode, targetSlot: dstSlot, link
				});
			}
			return link;
		};
	}
}

// ========================================================================
// Extend SchemaGraphApp with event hooks
// ========================================================================

function extendSchemaGraphAppWithEvents(SchemaGraphAppClass) {
	// Propagate eventBus to graph
	const originalSetupEventListeners = SchemaGraphAppClass.prototype.setupEventListeners;
	if (originalSetupEventListeners) {
		SchemaGraphAppClass.prototype.setupEventListeners = function() {
			if (this.graph && this.eventBus) this.graph.eventBus = this.eventBus;
			originalSetupEventListeners.call(this);
			if (this.graph && this.eventBus) this.graph.eventBus = this.eventBus;
		};
	}
	
	// Selection events
	const originalSelectNode = SchemaGraphAppClass.prototype.selectNode;
	if (originalSelectNode) {
		SchemaGraphAppClass.prototype.selectNode = function(node, addToSelection = false) {
			const prevSelection = new Set(this.selectedNodes || []);
			const result = originalSelectNode.call(this, node, addToSelection);
			if (node && !prevSelection.has(node)) {
				this.eventBus?.emit(GraphEvents.NODE_SELECTED, { nodeId: node.id, node });
			}
			prevSelection.forEach(n => {
				if (!this.selectedNodes?.has(n)) {
					this.eventBus?.emit(GraphEvents.NODE_DESELECTED, { nodeId: n.id, node: n });
				}
			});
			this.eventBus?.emit(GraphEvents.SELECTION_CHANGED, { 
				selectedNodes: Array.from(this.selectedNodes || []).map(n => n.id)
			});
			return result;
		};
	}
	
	const originalClearSelection = SchemaGraphAppClass.prototype.clearSelection;
	if (originalClearSelection) {
		SchemaGraphAppClass.prototype.clearSelection = function() {
			const hadSelection = (this.selectedNodes?.size || 0) > 0;
			const result = originalClearSelection.call(this);
			if (hadSelection) {
				this.eventBus?.emit(GraphEvents.SELECTION_CLEARED, {});
				this.eventBus?.emit(GraphEvents.SELECTION_CHANGED, { selectedNodes: [] });
			}
			return result;
		};
	}
	
	// Camera events
	const originalSetCamera = SchemaGraphAppClass.prototype.setCamera;
	if (originalSetCamera) {
		SchemaGraphAppClass.prototype.setCamera = function(x, y, scale) {
			const prevCamera = this.camera ? { ...this.camera } : null;
			const result = originalSetCamera.call(this, x, y, scale);
			if (prevCamera) {
				if (prevCamera.x !== x || prevCamera.y !== y) {
					this.eventBus?.emit(GraphEvents.CAMERA_MOVED, { x, y, prevX: prevCamera.x, prevY: prevCamera.y });
				}
				if (prevCamera.scale !== scale) {
					this.eventBus?.emit(GraphEvents.CAMERA_ZOOMED, { scale, prevScale: prevCamera.scale });
				}
			}
			return result;
		};
	}
	
	const originalCenterView = SchemaGraphAppClass.prototype.centerView;
	if (originalCenterView) {
		SchemaGraphAppClass.prototype.centerView = function(...args) {
			const result = originalCenterView.apply(this, args);
			this.eventBus?.emit(GraphEvents.VIEW_CENTERED, { camera: { ...this.camera } });
			return result;
		};
	}
	
	// Theme events
	const originalSetTheme = SchemaGraphAppClass.prototype.setTheme;
	if (originalSetTheme) {
		SchemaGraphAppClass.prototype.setTheme = function(theme) {
			const prevTheme = this.currentTheme || this.theme;
			const result = originalSetTheme.call(this, theme);
			this.eventBus?.emit(GraphEvents.THEME_CHANGED, { theme, prevTheme });
			return result;
		};
	}
	
	// Context menu
	const originalShowContextMenu = SchemaGraphAppClass.prototype.showContextMenu;
	if (originalShowContextMenu) {
		SchemaGraphAppClass.prototype.showContextMenu = function(node, wx, wy, coords) {
			const result = originalShowContextMenu.call(this, node, wx, wy, coords);
			this.eventBus?.emit(GraphEvents.CONTEXT_MENU_OPENED, { nodeId: node?.id, worldX: wx, worldY: wy });
			return result;
		};
	}
	
	// Node move/resize tracking
	const originalOnMouseUp = SchemaGraphAppClass.prototype.onMouseUp;
	if (originalOnMouseUp) {
		SchemaGraphAppClass.prototype.onMouseUp = function(e) {
			const draggedNode = this.dragNode;
			const resizedNode = this.resizingNode;
			const result = originalOnMouseUp.call(this, e);
			
			if (draggedNode && this._dragStartPos) {
				const dx = draggedNode.pos[0] - this._dragStartPos[0];
				const dy = draggedNode.pos[1] - this._dragStartPos[1];
				if (Math.abs(dx) > 1 || Math.abs(dy) > 1) {
					this.eventBus?.emit(GraphEvents.NODE_MOVED, { 
						nodeId: draggedNode.id, pos: [...draggedNode.pos],
						prevPos: this._dragStartPos, delta: [dx, dy]
					});
				}
			}
			
			if (resizedNode && this._resizeStartSize) {
				const dw = resizedNode.size[0] - this._resizeStartSize[0];
				const dh = resizedNode.size[1] - this._resizeStartSize[1];
				if (Math.abs(dw) > 1 || Math.abs(dh) > 1) {
					this.eventBus?.emit(GraphEvents.NODE_RESIZED, { 
						nodeId: resizedNode.id, size: [...resizedNode.size], prevSize: this._resizeStartSize
					});
				}
			}
			return result;
		};
	}
	
	const originalOnMouseDown = SchemaGraphAppClass.prototype.onMouseDown;
	if (originalOnMouseDown) {
		SchemaGraphAppClass.prototype.onMouseDown = function(e) {
			const result = originalOnMouseDown.call(this, e);
			if (this.dragNode) this._dragStartPos = [...this.dragNode.pos];
			if (this.resizingNode) this._resizeStartSize = [...this.resizingNode.size];
			return result;
		};
	}
}

// ========================================================================
// Events Extension Class
// ========================================================================

const BaseExtension = (typeof SchemaGraphExtension !== 'undefined') ? SchemaGraphExtension : class {
	constructor(app) {
		this.app = app;
		this.graph = app.graph;
		this.eventBus = app.eventBus;
	}
	destroy() {}
};

class EventsExtension extends BaseExtension {
	constructor(app) {
		super(app);
		this._enhanceEventBus();
		this._setupAutoRedraw();
		this._wrapAppLinkMethods();
		this._wrapFieldChanges();
		this._extendAPI();
	}

	_enhanceEventBus() {
		if (this.eventBus._enhanced) return;
		
		const eventBus = this.eventBus;
		const originalEmit = eventBus.emit.bind(eventBus);
		
		eventBus.emit = (event, data = {}) => {
			if (DEBUG_EVENTS || window.DEBUG_GRAPH_EVENTS) {
				console.log(`[GraphEvent] ${event}`, data);
			}
			
			originalEmit(event, data);
			
			if (DATA_CHANGE_EVENTS.has(event) && event !== GraphEvents.GRAPH_CHANGED) {
				originalEmit(GraphEvents.GRAPH_CHANGED, { 
					originalEvent: event, 
					...data 
				});
			}
		};
		
		if (!eventBus.once) {
			eventBus.once = (event, callback, context = null) => {
				const wrapper = (data) => {
					eventBus.off(event, wrapper);
					callback.call(context, data);
				};
				return eventBus.on(event, wrapper, context);
			};
		}
		
		if (!eventBus.removeAllListeners) {
			eventBus.removeAllListeners = (event = null) => eventBus.clear(event);
		}
		
		eventBus._enhanced = true;
	}
	
	_setupAutoRedraw() {
		// Auto-redraw on data changes
		const redrawEvents = [
			GraphEvents.NODE_CREATED,
			GraphEvents.NODE_REMOVED,
			GraphEvents.LINK_CREATED,
			GraphEvents.LINK_REMOVED,
			GraphEvents.PREVIEW_INSERTED,
			GraphEvents.PREVIEW_REMOVED
		];
		
		for (const event of redrawEvents) {
			this.eventBus.on(event, () => {
				this.app.draw?.();
			});
		}
	}
	
	_wrapAppLinkMethods() {
		const app = this.app;
		const graph = this.graph;
		const eventBus = this.eventBus;
		
		// Wrap removeLink
		const originalRemoveLink = app.removeLink?.bind(app);
		if (originalRemoveLink) {
			app.removeLink = function(linkId, targetNode, targetSlot) {
				const link = graph.links[linkId];
				const originId = link?.origin_id;
				const originSlot = link?.origin_slot;
				const targetId = link?.target_id;
				
				originalRemoveLink(linkId, targetNode, targetSlot);
				
				// Emit proper event (original emits 'link:deleted')
				eventBus.emit(GraphEvents.LINK_REMOVED, {
					linkId,
					sourceNodeId: originId,
					sourceSlot: originSlot,
					targetNodeId: targetId,
					targetSlot
				});
			};
		}
		
		// Wrap disconnectLink
		const originalDisconnectLink = app.disconnectLink?.bind(app);
		if (originalDisconnectLink) {
			app.disconnectLink = function(linkId) {
				const link = graph.links[linkId];
				const originId = link?.origin_id;
				const originSlot = link?.origin_slot;
				const targetId = link?.target_id;
				const targetSlot = link?.target_slot;
				
				const result = originalDisconnectLink(linkId);
				
				if (result) {
					eventBus.emit(GraphEvents.LINK_REMOVED, {
						linkId,
						sourceNodeId: originId,
						sourceSlot: originSlot,
						targetNodeId: targetId,
						targetSlot
					});
				}
				
				return result;
			};
		}
	}

	_wrapDisconnectHandling() {
		const app = this.app;
		const graph = this.graph;
		const originalOnMouseUp = app.onMouseUp?.bind(app);
		
		if (!originalOnMouseUp) return;
		
		app.onMouseUp = function(e) {
			// Capture link state before original handler
			const linksBefore = new Set(Object.keys(graph.links));
			
			// Call original
			const result = originalOnMouseUp(e);
			
			// Check for removed links that bypassed API
			const linksAfter = new Set(Object.keys(graph.links));
			for (const linkId of linksBefore) {
				if (!linksAfter.has(linkId)) {
					// Link was removed directly - emit the event manually
					graph.eventBus?.emit(GraphEvents.LINK_REMOVED, {
						linkId: parseInt(linkId),
						bypassedAPI: true
					});
				}
			}
			
			return result;
		};
	}
	
	_wrapFieldChanges() {
		const app = this.app;
		const eventBus = this.eventBus;
		
		// Listen to the node input overlay
		const nodeInput = document.getElementById('sg-nodeInput');
		if (nodeInput) {
			nodeInput.addEventListener('change', (e) => {
				// The app should track which node/field is being edited
				eventBus.emit(GraphEvents.FIELD_CHANGED, {
					nodeId: app.editingNode?.id,
					// fieldIndex: app._editingFieldIndex,
					fieldIndex: 0,
					fieldName: app.editingNode?.editingSlot,
					value: e.target?.value
				});
			});
			
			// Also listen for blur in case change doesn't fire
			nodeInput.addEventListener('blur', (e) => {
				eventBus.emit(GraphEvents.FIELD_CHANGED, {
					nodeId: app.editingNode?.id,
					// fieldIndex: app._editingFieldIndex,
					fieldIndex: 0,
					fieldName: app.editingNode?.editingSlot,
					value: e.target?.value
				});
			});
		}
	}

	_extendAPI() {
		this.app.api = this.app.api || {};
		this.app.api.events = {
			on: (event, cb) => this.eventBus.on(event, cb),
			once: (event, cb) => this.eventBus.once?.(event, cb),
			off: (event, cb) => this.eventBus.off?.(event, cb),
			emit: (event, data) => this.eventBus.emit(event, data),
			types: GraphEvents,
			enableDebug: () => { window.DEBUG_GRAPH_EVENTS = true; },
			disableDebug: () => { window.DEBUG_GRAPH_EVENTS = false; },
			onNodeCreated: (cb) => this.eventBus.on(GraphEvents.NODE_CREATED, cb),
			onNodeRemoved: (cb) => this.eventBus.on(GraphEvents.NODE_REMOVED, cb),
			onNodeMoved: (cb) => this.eventBus.on(GraphEvents.NODE_MOVED, cb),
			onLinkCreated: (cb) => this.eventBus.on(GraphEvents.LINK_CREATED, cb),
			onLinkRemoved: (cb) => this.eventBus.on(GraphEvents.LINK_REMOVED, cb),
			onGraphChanged: (cb) => this.eventBus.on(GraphEvents.GRAPH_CHANGED, cb),
			onFieldChanged: (cb) => this.eventBus.on(GraphEvents.FIELD_CHANGED, cb)
		};
	}
}

// ========================================================================
// AUTO-INITIALIZATION
// ========================================================================

if (typeof SchemaGraph !== 'undefined') {
	extendSchemaGraphWithAPI(SchemaGraph);
}

if (typeof SchemaGraphApp !== 'undefined') {
	extendSchemaGraphAppWithEvents(SchemaGraphApp);
	
	if (typeof extensionRegistry !== 'undefined') {
		extensionRegistry.register('events', EventsExtension);
	} else {
		const originalSetup = SchemaGraphApp.prototype.setupEventListeners;
		SchemaGraphApp.prototype.setupEventListeners = function() {
			originalSetup.call(this);
			new EventsExtension(this);
		};
	}
	console.log('✨ SchemaGraph Events extension loaded');
}

// ========================================================================
// EXPORTS
// ========================================================================

if (typeof module !== 'undefined' && module.exports) {
	module.exports = { GraphEvents, GraphEventEmitter, EventsExtension };
}

if (typeof window !== 'undefined') {
	window.GraphEvents = GraphEvents;
	window.GraphEventEmitter = GraphEventEmitter;
}
