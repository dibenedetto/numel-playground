/* ========================================================================
   NUMEL WORKFLOW - Core Client & Visualizer
   ======================================================================== */

const WORKFLOW_SCHEMA_NAME    = "Workflow";
const DEFAULT_WORKFLOW_LAYOUT = 'hierarchical-vertical';

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
			throw new Error(`${endpoint} failed: ${response.statusText}`);
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

	loadWorkflow(workflow, name = null, layout = DEFAULT_WORKFLOW_LAYOUT) {
		if (!this.isReady) {
			console.error('Schema not registered');
			return false;
		}

		if (!this._validateWorkflow(workflow)) {
			return false;
		}

		this.currentWorkflow = JSON.parse(JSON.stringify(workflow));
		this.currentWorkflowName = name || workflow.info?.name || 'Untitled';

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

		// Apply layout
		// setTimeout(() => {
		// 	this.schemaGraph.api.layout.apply(layout);
		// 	setTimeout(() => this.schemaGraph.api.view.center(), 50);
		// }, 0);
		if (layout) {
			this.schemaGraph.api.layout.apply(layout);
			this.schemaGraph.api.view.center();
		}

		console.log(`✅ Loaded workflow: ${this.currentWorkflowName}`);

		return true;
	}

	_validateWorkflow(workflow) {
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

	// --- Node State Updates ---

	updateNodeState(nodeIndex, status, data = {}) {
		const graphNode = this.graphNodes[nodeIndex];
		if (!graphNode) return;

		const colorMap = {
			'pending': '#4a5568',
			'ready': '#3182ce',
			'running': '#805ad5',
			'completed': '#38a169',
			'failed': '#e53e3e',
			'skipped': '#718096'
		};

		graphNode.color = colorMap[status] || graphNode.color;

		if (status === 'running') {
			this.schemaGraph.api.node.select(graphNode, false);
		}

		this.schemaGraph.api.util.redraw();
	}

	clearNodeStates() {
		this.graphNodes.forEach((node, idx) => {
			if (node) this.updateNodeState(idx, 'pending');
		});
		this.schemaGraph.api.node.clearSelection();
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
