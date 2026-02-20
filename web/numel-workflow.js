/* ========================================================================
   NUMEL WORKFLOW - Core Client & Visualizer
   ======================================================================== */

const WORKFLOW_SCHEMA_NAME    = "Workflow";
const DEFAULT_WORKFLOW_LAYOUT = 'hierarchical-horizontal';

// ========================================================================
// WorkflowClient - Backend Communication
// ========================================================================

class WorkflowClient {
	constructor(baseUrl) {
		this.baseUrl = baseUrl;
		this.websocket = null;
		this.eventHandlers = new Map();
		this.isConnected = false;
	}

	// --- HTTP Methods ---

	async _post(endpoint, body = null) {
		const response = await fetch(`${this.baseUrl}${endpoint}`, {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: body ? JSON.stringify(body) : null
		});
		if (!response.ok) {
			let detail = response.statusText;
			try { const err = await response.json(); detail = JSON.stringify(err.detail || err, null, 2); } catch {}
			throw new Error(`${endpoint} failed: ${detail}`);
		}
		return response.json();
	}

	async ping() {
		return this._post('/ping');
	}

	async getSchema() {
		return this._post('/schema');
	}

	async listWorkflows() {
		return this._post('/list');
	}

	async getWorkflow(name) {
		const tail = (name == null) ? '' : `/${encodeURIComponent(name)}`;
		return this._post(`/get${tail}`);
	}

	async addWorkflow(workflow, name = null) {
		return this._post('/add', { workflow, name });
	}

	async removeWorkflow(name) {
		const tail = (name == null) ? '' : `/${encodeURIComponent(name)}`;
		return this._post(`/remove${tail}`);
	}

	async startWorkflow(name, initialData = null) {
		return this._post('/start', { name, initial_data: initialData });
	}

	async getExecutionState(executionId) {
		const tail = (executionId == null) ? '' : `/${executionId}`;
		return this._post(`/exec_state${tail}`);
	}

	async cancelExecution(executionId) {
		const tail = (executionId == null) ? '' : `/${executionId}`;
		return this._post(`/exec_cancel${tail}`);
	}

	async listExecutions() {
		return this._post('/exec_list');
	}

	async provideUserInput(executionId, nodeId, inputData) {
		return this._post(`/exec_input/${executionId}`, { node_id: nodeId, input_data: inputData });
	}

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
		this.currentWorkflowName = null;
		this.graphNodes = [];
		this.isReady = false;
		this.defaultLayout = DEFAULT_WORKFLOW_LAYOUT;
	}

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
		}
		this.schemaGraph.api.view.center();

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
		// Update name if changed
		if (options.name) {
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
