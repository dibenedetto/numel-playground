/* ========================================================================
   NUMEL WORKFLOW - Core Client & Visualizer
   ======================================================================== */

const WORKFLOW_SCHEMA_NAME    = "Workflow";
const DEFAULT_WORKFLOW_LAYOUT = 'hierarchical-horizontal';

// ─── Implicit Start/End helper ────────────────────────────────────────────────
// Strip start_flow / end_flow / sink_flow nodes and remap edge indices.
// Called by loadWorkflow when the implicitStartEnd feature is enabled.
function _stripBookendNodes(workflow) {
	const STRIP   = new Set(['start_flow', 'end_flow', 'sink_flow']);
	const nodes   = workflow.nodes || [];
	const edges   = workflow.edges || [];
	const removed = new Set(nodes.map((n, i) => STRIP.has(n.type) ? i : -1).filter(i => i >= 0));
	if (removed.size === 0) return workflow;

	// Build old-index → new-index map (-1 = removed)
	let shift = 0;
	const remap = nodes.map((_, i) => {
		if (removed.has(i)) { shift++; return -1; }
		return i - shift;
	});

	return {
		...workflow,
		nodes: nodes.filter((_, i) => !removed.has(i)),
		edges: edges
			.filter(e => remap[e.source] >= 0 && remap[e.target] >= 0)
			.map(e => ({ ...e, source: remap[e.source], target: remap[e.target] })),
	};
}

// ─── Strip preview_flow nodes ────────────────────────────────────────────────
// The backend may return preview_flow nodes created from preview:true edges.
// Strip them so the frontend can re-insert them via insertPreviewOnLink.
function _stripPreviewNodes(workflow) {
	const nodes = workflow.nodes || [];
	const edges = workflow.edges || [];
	const previewIndices = new Set();
	for (let i = 0; i < nodes.length; i++) {
		if (nodes[i].type === 'preview_flow') previewIndices.add(i);
	}
	if (previewIndices.size === 0) return workflow;

	// For each preview node, find its incoming and outgoing edges to reconstruct
	// the original direct edge with preview: true
	const bypassEdges = [];
	for (const pi of previewIndices) {
		const incoming = edges.filter(e => e.target === pi);
		const outgoing = edges.filter(e => e.source === pi);
		for (const inp of incoming) {
			for (const out of outgoing) {
				bypassEdges.push({
					type: 'edge',
					source: inp.source,
					target: out.target,
					source_slot: inp.source_slot,
					target_slot: out.target_slot,
					preview: true
				});
			}
		}
	}

	// Remap indices
	let shift = 0;
	const remap = nodes.map((_, i) => {
		if (previewIndices.has(i)) { shift++; return -1; }
		return i - shift;
	});

	// Filter edges: remove edges to/from preview nodes, add bypass edges
	const keptEdges = edges
		.filter(e => !previewIndices.has(e.source) && !previewIndices.has(e.target))
		.map(e => ({ ...e, source: remap[e.source], target: remap[e.target] }));

	// Remap bypass edges
	for (const be of bypassEdges) {
		be.source = remap[be.source];
		be.target = remap[be.target];
		if (be.source >= 0 && be.target >= 0) keptEdges.push(be);
	}

	return {
		...workflow,
		nodes: nodes.filter((_, i) => !previewIndices.has(i)),
		edges: keptEdges
	};
}

// ========================================================================
// WorkflowClient - Backend Communication
// ========================================================================

class WorkflowClient {
	constructor(baseUrl, api = null) {
		this.api = api || new NumelAPI(baseUrl);
		this.baseUrl = baseUrl;
		this.websocket = null;
		this.eventHandlers = new Map();
		this.isConnected = false;
	}

	// --- HTTP Methods (delegate to NumelAPI) ---

	async ping()                                        { return this.api.ping(); }
	async getSchema()                                   { return this.api.getSchema(); }
	async listWorkflows()                               { return this.api.listWorkflows(); }
	async getWorkflow(name)                             { return this.api.getWorkflow(name); }
	async addWorkflow(workflow, name = null)             { return this.api.addWorkflow(workflow, name); }
	async removeWorkflow(name)                          { return this.api.removeWorkflow(name); }
	async startWorkflow(name, initialData = null)       { return this.api.startWorkflow(name, initialData); }
	async getExecutionState(executionId)                { return this.api.getExecState(executionId); }
	async cancelExecution(executionId)                  { return this.api.cancelExecution(executionId); }
	async listExecutions()                              { return this.api.listExecutions(); }
	async provideUserInput(executionId, nodeId, data)   { return this.api.provideUserInput(executionId, nodeId, data); }

	// --- WebSocket ---

	connectWebSocket() {
		const wsUrl = this.baseUrl.replace(/^http/, 'ws') + '/events';
		this.websocket = new WebSocket(wsUrl);

		this.websocket.onopen = () => {
			this.isConnected = true;
			this.emit('ws:connected', {});
		};

		this.websocket.onmessage = (event) => {
			try {
				const data = JSON.parse(event.data);
				if (data.type === 'workflow_event') {
					this.emit('workflow:event', data.event);
					this.emit(data.event.event_type, data.event);
				} else if (data.type === 'event_history') {
					this.emit('workflow:history', data.events);
				}
			} catch (e) {
				console.error('WebSocket parse error:', e);
			}
		};

		this.websocket.onerror = (error) => {
			console.error('WebSocket error:', error);
			this.emit('ws:error', { error });
		};

		this.websocket.onclose = () => {
			this.isConnected = false;
			this.emit('ws:disconnected', {});
			// Auto-reconnect after 3s
			// setTimeout(() => {
			// 	if (!this.isConnected) this.connectWebSocket();
			// }, 3000);
		};
	}

	disconnectWebSocket() {
		if (this.websocket) {
			this.websocket.close();
			this.websocket = null;
		}
	}

	// --- Event Emitter ---

	on(eventType, handler) {
		if (!this.eventHandlers.has(eventType)) {
			this.eventHandlers.set(eventType, []);
		}
		this.eventHandlers.get(eventType).push(handler);
	}

	off(eventType, handler) {
		const handlers = this.eventHandlers.get(eventType);
		if (handlers) {
			const idx = handlers.indexOf(handler);
			if (idx !== -1) handlers.splice(idx, 1);
		}
	}

	emit(eventType, data) {
		const handlers = this.eventHandlers.get(eventType);
		if (handlers) {
			handlers.forEach(h => {
				try { h(data); } catch (e) { console.error(`Event handler error [${eventType}]:`, e); }
			});
		}
	}
}

// ========================================================================
// WorkflowVisualizer - Graph Management
// ========================================================================

class WorkflowVisualizer {
	constructor(schemaGraphApp) {
		this.schemaGraph = schemaGraphApp;
		this.currentWorkflow = null;
		this._workflowName = null;
		this._nameChangeCallbacks = [];
		this.graphNodes = [];
		this.isReady = false;
		this.defaultLayout = DEFAULT_WORKFLOW_LAYOUT;

		// Per-tab workflow state: tabId → { workflow, workflowName, graphNodes }
		this._tabWorkflowState = {};

		// Save workflow state before tab switch
		schemaGraphApp.eventBus.on('tab:beforeSwitch', (data) => {
			if (data.fromTabId) {
				this._tabWorkflowState[data.fromTabId] = {
					workflow: this.currentWorkflow,
					workflowName: this._workflowName,
					graphNodes: this.graphNodes,
				};
			}
		});

		// Discard saved state when the last tab is cleared
		schemaGraphApp.eventBus.on('tab:cleared', (data) => {
			delete this._tabWorkflowState[data.tabId];
		});

		// Restore workflow state after tab switch
		schemaGraphApp.eventBus.on('tab:switched', (data) => {
			const saved = this._tabWorkflowState[data.tabId];
			if (saved) {
				this.currentWorkflow = saved.workflow;
				this.graphNodes = saved.graphNodes;
				// Use setter to sync UI (tab label, panel, callbacks)
				this.currentWorkflowName = saved.workflowName;
			} else {
				// New/empty tab — use the tab name as the workflow name
				this.currentWorkflow = null;
				this.graphNodes = [];
				this.currentWorkflowName = data.name || 'Untitled';
			}
		});
	}

	/**
	 * The workflow name — setting it auto-syncs the left panel label,
	 * the active tab, and the workflow options model.
	 * Register listeners via onNameChanged(fn).
	 */
	get currentWorkflowName() { return this._workflowName; }
	set currentWorkflowName(name) {
		const prev = this._workflowName;
		this._workflowName = name || null;
		if (prev === this._workflowName) return;

		// Sync the active tab label
		const sg = this.schemaGraph;
		if (name && sg) {
			const tab = sg.tabs?.find(t => t.id === sg.activeTabId);
			if (tab && tab.name !== name) {
				tab.name = name;
				sg._renderTabs?.();
			}
		}

		// Sync workflow options model (if a workflow is loaded)
		if (this.currentWorkflow) {
			if (!this.currentWorkflow.options) this.currentWorkflow.options = { type: 'workflow_options' };
			this.currentWorkflow.options.name = this._workflowName;
		}

		// Notify listeners
		for (const cb of this._nameChangeCallbacks) {
			try { cb(this._workflowName, prev); } catch (e) { console.error('onNameChanged callback error:', e); }
		}
	}

	/** Register a callback invoked whenever the workflow name changes: fn(newName, oldName) */
	onNameChanged(fn) { this._nameChangeCallbacks.push(fn); }

	/** Remove a previously registered name-change callback */
	offNameChanged(fn) { this._nameChangeCallbacks = this._nameChangeCallbacks.filter(cb => cb !== fn); }

	configure(options = {}) {
		if (options.defaultLayout !== undefined) this.defaultLayout = options.defaultLayout;
	}

	// --- Schema Registration ---

	async registerSchema(schemaCode) {
		if (!this.schemaGraph.api?.workflow) {
			console.error('Workflow extension not loaded');
			return false;
		}

		const success = this.schemaGraph.api.workflow.registerSchema(WORKFLOW_SCHEMA_NAME, schemaCode);
		if (!success) {
			console.error('Failed to register workflow schema');
			return false;
		}

		this.schemaGraph.api.schema.enable(WORKFLOW_SCHEMA_NAME);
		this.isReady = true;

		const nodeTypes = Object.keys(this.schemaGraph.graph.nodeTypes)
			.filter(t => t.startsWith(WORKFLOW_SCHEMA_NAME + '.'));
		console.log(`✅ Registered ${nodeTypes.length} workflow node types`);

		return true;
	}

	// --- Workflow Initialization ---

	initEmptyWorkflow(name = 'Untitled') {
		this.currentWorkflow = {
			type: 'workflow',
			nodes: [],
			edges: []
		};
		this.currentWorkflowName = name;
		this.graphNodes = [];
		return this.currentWorkflow;
	}

	ensureWorkflow() {
		if (!this.currentWorkflow) {
			this.initEmptyWorkflow();
		}
		return this.currentWorkflow;
	}
	
	// --- Workflow Loading ---

	loadWorkflow(workflow, name = null, layout = undefined, sync = false) {
		if (layout === undefined) layout = this.defaultLayout;
		if (!this.isReady) {
			console.error('Schema not registered');
			return false;
		}

		if (!this.validateWorkflow(workflow)) {
			return false;
		}

		this.currentWorkflow = JSON.parse(JSON.stringify(workflow));
		this.currentWorkflow = _stripPreviewNodes(this.currentWorkflow);
		if (this.schemaGraph._features?.implicitStartEnd) {
			this.currentWorkflow = _stripBookendNodes(this.currentWorkflow);
		}
		this.currentWorkflowName = name || workflow.options?.name || 'Untitled';

		this.schemaGraph.api.graph.clear();

		if (this.schemaGraph.api.workflow) {
			this.schemaGraph.api.workflow.import(this.currentWorkflow, WORKFLOW_SCHEMA_NAME);
		}

		// Build graphNodes index
		this.graphNodes = [];
		const allNodes = this.schemaGraph.api.node.list();
		allNodes.forEach((node, idx) => {
			if (this._isWorkflowNode(node)) {
				node.workflowIndex = idx;
				this.graphNodes[idx] = node;
			}
		});

		// Apply layout.
		// When autoLayoutOnImport is enabled: apply defaultLayout unless the workflow
		// has at least one node with a non-zero saved position (treat all-[0,0] as unset).
		// When the feature is disabled: fall back to the caller-supplied layout arg.
		let effectiveLayout = layout;
		if (this.schemaGraph._features?.autoLayoutOnImport) {
			const hasPositions = workflow.nodes?.some(n => {
				if (!n.extra?.pos) return false;
				const [x, y] = n.extra.pos;
				return x !== 0 || y !== 0;
			});
			effectiveLayout = hasPositions ? null : this.defaultLayout;
		}
		if (effectiveLayout) {
			this.schemaGraph.api.layout.apply(effectiveLayout);
			// Layout may reposition preview nodes — restore their saved positions
			this._restorePreviewPositionsFromEdges(workflow);
		}
		// Don't reset camera/zoom when syncing — preserve user's current view
		if (!sync) {
			this.schemaGraph.api.view.center();
		}

		// Update implicit role badges after the full graph is loaded
		this.schemaGraph._updateImplicitRoles?.();

		console.log(`${sync ? '🔄 Synced' : '✅ Loaded'} workflow: ${this.currentWorkflowName}`);

		return true;
	}

	validateWorkflow(workflow) {
		if (!workflow?.nodes || !Array.isArray(workflow.nodes)) {
			console.error('Invalid workflow: missing nodes array');
			return false;
		}
		if (!workflow?.edges || !Array.isArray(workflow.edges)) {
			console.error('Invalid workflow: missing edges array');
			return false;
		}
		return true;
	}

	_isWorkflowNode(node) {
		if (!node) return false;
		if (node.isWorkflowNode) return true;
		if (node.type?.startsWith(WORKFLOW_SCHEMA_NAME + '.')) return true;
		if (node.schemaName === WORKFLOW_SCHEMA_NAME) return true;
		return false;
	}

	/**
	 * After layout, restore preview node positions from edge preview_pos data.
	 * Preview nodes store _originalEdgeInfo which links back to source/target.
	 * We match by iterating preview edges in workflow order (same order they were created).
	 */
	_restorePreviewPositionsFromEdges(workflow) {
		if (!workflow?.edges) return;
		const previewEdges = workflow.edges.filter(e => e.preview && e.preview_pos);
		if (!previewEdges.length) return;

		// Collect preview nodes in graph order
		const previewNodes = this.schemaGraph.graph.nodes.filter(n => n?.extra?._isEdgePreview);
		// Match by order (preview edges and preview nodes are created in the same sequence)
		const count = Math.min(previewEdges.length, previewNodes.length);
		for (let i = 0; i < count; i++) {
			const pos = previewEdges[i].preview_pos;
			if (pos && pos.length === 2) {
				previewNodes[i].pos[0] = pos[0];
				previewNodes[i].pos[1] = pos[1];
			}
		}
	}

	// --- Export ---

	exportWorkflow() {
		if (!this.currentWorkflow) return null;

		if (this.schemaGraph.api?.workflow) {
			const exported = this.schemaGraph.api.workflow.export(WORKFLOW_SCHEMA_NAME, this.currentWorkflow);
			if (exported) {
				this.currentWorkflow = exported;
			}
		}

		return JSON.parse(JSON.stringify(this.currentWorkflow));
	}

	// --- Workflow Options ---

	/**
	 * Get the current workflow options
	 * @returns {Object|null} Workflow options or null if no workflow loaded
	 */
	getWorkflowOptions() {
		if (!this.currentWorkflow) return null;
		return this.currentWorkflow.options || null;
	}

	/**
	 * Set/update workflow options
	 * @param {Object} options - Options to set (merged with existing)
	 * @returns {boolean} True if options were changed
	 */
	setWorkflowOptions(options) {
		if (!this.currentWorkflow) return false;
		this.currentWorkflow.options = {
			type: 'workflow_options',
			...(this.currentWorkflow.options || {}),
			...options
		};
		// Sync name via the setter (updates panel, tab, and fires callbacks)
		if (options.name !== undefined) {
			this.currentWorkflowName = options.name;
		}
		// Emit event to notify UI that options changed (triggers sync)
		this.schemaGraph.eventBus.emit('workflow:optionsChanged', {
			options: this.currentWorkflow.options
		});
		return true;
	}

	/**
	 * Get workflow options schema info for building UI forms
	 * @returns {Object|null} Schema info with fields, fieldRoles, and defaults
	 */
	getWorkflowOptionsInfo() {
		return this.schemaGraph.api?.schemaTypes?.getWorkflowOptionsInfo(WORKFLOW_SCHEMA_NAME) || null;
	}

	/**
	 * Get workflow execution options schema info for building UI forms
	 * @returns {Object|null} Schema info with fields, fieldRoles, and defaults
	 */
	getWorkflowExecutionOptionsInfo() {
		return this.schemaGraph.api?.schemaTypes?.getWorkflowExecutionOptionsInfo(WORKFLOW_SCHEMA_NAME) || null;
	}

	// --- Node State Updates ---

	updateNodeState(nodeIndex, status, data = {}) {
		const graphNode = this.graphNodes[nodeIndex];
		if (!graphNode) return;

		const colorMap = {
			'pending': '#4a5568',
			'ready': '#3182ce',
			'running': '#805ad5',
			'waiting': '#d69e2e',
			'completed': '#38a169',
			'failed': '#e53e3e',
			'skipped': '#718096'
		};

		// Save original color before first execution override
		if (!graphNode._originalColor) graphNode._originalColor = graphNode.color;
		graphNode.color = colorMap[status] || graphNode.color;
		graphNode.executionState = status;

		if (status === 'running' || status === 'waiting') {
			this.schemaGraph.api.node.select(graphNode, false);
			// Start execution animation if not already running
			this._startExecutionAnimation();
		}

		// Skip draw if we're in batch update mode
		if (!this._batchUpdate) {
			this.schemaGraph.draw();
		}
	}

	_startExecutionAnimation() {
		if (this._animationIntervalId) return;

		const self = this;
		this._animationIntervalId = setInterval(() => {
			// Check if any node is still running or waiting
			const hasActiveNode = self.graphNodes?.some(n =>
				n?.executionState === 'running' || n?.executionState === 'waiting'
			);
			if (!hasActiveNode) {
				self._stopExecutionAnimation();
				return;
			}
			self.schemaGraph?.draw();
		}, 50); // 20fps for smooth spinner animation
	}

	_stopExecutionAnimation() {
		if (this._animationIntervalId) {
			clearInterval(this._animationIntervalId);
			this._animationIntervalId = null;
		}
	}

	clearNodeStates() {
		// Stop any running animation
		this._stopExecutionAnimation();

		// Batch update to avoid multiple draw calls
		this._batchUpdate = true;
		this.graphNodes.forEach((node, idx) => {
			if (node) {
				node.executionState = null;
				if (node._originalColor) {
					node.color = node._originalColor;
					delete node._originalColor;
				}
			}
		});
		this._batchUpdate = false;

		this.schemaGraph.api.node.clearSelection();
		this.schemaGraph.draw();
	}

	// --- Node Addition ---

	addNodeAtPosition(nodeType, x, y) {
		if (!this.isReady || !this.currentWorkflow) return null;

		const fullType = nodeType.includes('.') ? nodeType : `${WORKFLOW_SCHEMA_NAME}.${nodeType}`;

		if (!this.schemaGraph.graph.nodeTypes[fullType]) {
			console.error('Node type not registered:', fullType);
			return null;
		}

		const graphNode = this.schemaGraph.api.node.create(fullType, x, y);
		if (!graphNode) return null;

		const index = this.currentWorkflow.nodes.length;
		const workflowNode = {
			type: nodeType.includes('.') ? nodeType.split('.').pop() : nodeType,
			extra: { name: graphNode.title || nodeType }
		};

		this.currentWorkflow.nodes.push(workflowNode);
		graphNode.workflowIndex = index;
		this.graphNodes[index] = graphNode;

		return graphNode;
	}
}

// ========================================================================
// Global Exports
// ========================================================================

window.WorkflowClient = WorkflowClient;
window.WorkflowVisualizer = WorkflowVisualizer;
window.WORKFLOW_SCHEMA_NAME = WORKFLOW_SCHEMA_NAME;
