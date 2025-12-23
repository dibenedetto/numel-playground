/*
========================================================================
NUMEL WORKFLOW - SchemaGraph Integration (Updated for FieldRole Schema)
========================================================================
Uses schemagraph-workflow-ext.js for schema parsing and node generation
*/

const WORKFLOW_SCHEMA_NAME = "Workflow";

// ========================================================================
// Fetch and Register Workflow Schema from Backend
// ========================================================================

async function fetchAndRegisterWorkflowSchema(schemaGraph, serverUrl) {
	try {
		console.log('📥 Fetching workflow schema from backend...');
		
		const response = await fetch(`${serverUrl}/workflow/schema`, {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' }
		});
		
		if (!response.ok) {
			throw new Error(`Failed to fetch workflow schema: ${response.statusText}`);
		}
		
		const data = await response.json();
		console.log('✅ Received workflow schema from backend');
		
		// Use the workflow extension to register schema
		if (schemaGraph.api && schemaGraph.api.workflow) {
			const success = schemaGraph.api.workflow.registerSchema(
				WORKFLOW_SCHEMA_NAME, 
				data.schema
			);
			
			if (!success) {
				throw new Error('Failed to register workflow schema');
			}
			
			console.log('✅ Workflow schema registered via extension');
		} else {
			throw new Error('Workflow extension not loaded - include schemagraph-workflow-ext.js');
		}
		
		// List registered node types
		const nodeTypes = Object.keys(schemaGraph.graph.nodeTypes)
			.filter(t => t.startsWith(WORKFLOW_SCHEMA_NAME + '.'));
		console.log('📋 Registered workflow node types:', nodeTypes);
		
		return true;
		
	} catch (error) {
		console.error('❌ Error initializing workflow system:', error);
		return false;
	}
}

// ========================================================================
// Helper: Check if node is a workflow node
// ========================================================================

function isWorkflowNode(graphNode) {
	if (!graphNode) return false;
	
	// Check for workflow node marker
	if (graphNode.isWorkflowNode) return true;
	
	// Check if type starts with workflow schema name
	if (graphNode.type && graphNode.type.startsWith(WORKFLOW_SCHEMA_NAME + '.')) {
		return true;
	}
	
	// Check schemaName property
	if (graphNode.schemaName === WORKFLOW_SCHEMA_NAME) {
		return true;
	}
	
	return false;
}

// ========================================================================
// WorkflowVisualizer - Graph Visualization
// ========================================================================

class WorkflowVisualizer {
	constructor(schemaGraphApp) {
		this.schemaGraph = schemaGraphApp;
		this.currentWorkflow = null;
		this.graphNodes = [];
		this.isWorkflowMode = false;
		
		// Saved states for mode switching
		this.savedChatState = null;
		this.savedWorkflowState = null;
	}
	
	// ====================================================================
	// Mode Management
	// ====================================================================
	
	enterWorkflowMode() {
		if (this.isWorkflowMode) return;
		
		console.log('🔄 Entering workflow mode...');
		
		// Save complete chat state
		this.savedChatState = {
			graph: this.schemaGraph.api.graph.export(false),
			view: this.schemaGraph.api.view.export(),
			enabledSchemas: this.schemaGraph.api.schema.listEnabled()
		};
		
		console.log('💾 Saved chat state:', {
			nodes: this.savedChatState.graph.nodes.length,
			links: this.savedChatState.graph.links.length,
			schemas: this.savedChatState.enabledSchemas
		});
		
		// Disable all non-workflow schemas
		const allSchemas = this.schemaGraph.api.schema.list();
		allSchemas.forEach(schemaName => {
			if (schemaName !== WORKFLOW_SCHEMA_NAME) {
				this.schemaGraph.api.schema.disable(schemaName);
			}
		});
		
		// Enable workflow schema
		this.schemaGraph.api.schema.enable(WORKFLOW_SCHEMA_NAME);
		
		// Clear graph for workflow
		this.schemaGraph.api.graph.clear();
		
		this.isWorkflowMode = true;
		console.log('✅ Entered workflow mode');
	}
	
	exitWorkflowMode() {
		if (!this.isWorkflowMode) return;
		
		console.log('🔄 Exiting workflow mode...');
		
		// Save workflow state before exiting
		if (this.currentWorkflow) {
			this.syncWorkflowFromGraph();
			
			this.savedWorkflowState = {
				workflow: JSON.parse(JSON.stringify(this.currentWorkflow)),
				view: this.schemaGraph.api.view.export()
			};
			
			console.log('💾 Saved workflow state:', {
				nodes: this.savedWorkflowState.workflow.nodes.length,
				edges: this.savedWorkflowState.workflow.edges.length
			});
		}
		
		// Restore chat state
		if (this.savedChatState) {
			console.log('📂 Restoring chat state...');
			
			// Disable workflow schema
			this.schemaGraph.api.schema.disable(WORKFLOW_SCHEMA_NAME);
			
			// Import graph state
			this.schemaGraph.api.graph.import(this.savedChatState.graph, false);
			
			// Restore view
			this.schemaGraph.api.view.import(this.savedChatState.view);
			
			// Re-enable previously enabled schemas
			this.savedChatState.enabledSchemas.forEach(schemaName => {
				this.schemaGraph.api.schema.enable(schemaName);
			});
			
			console.log('✅ Restored chat state');
		}
		
		this.isWorkflowMode = false;
		this.currentWorkflow = null;
		this.graphNodes = [];
		
		console.log('✅ Exited workflow mode');
	}
	
	// ====================================================================
	// Workflow Loading
	// ====================================================================
	
	loadWorkflow(workflow) {
		if (!this.isWorkflowMode) {
			this.enterWorkflowMode();
		}
		
		// Validate workflow structure
		if (!this.validateWorkflow(workflow)) {
			console.error('❌ Invalid workflow structure');
			return false;
		}
		
		// Check if we have saved state for this workflow
		const isSameWorkflow = this.savedWorkflowState && 
			this.savedWorkflowState.workflow.info?.name === workflow.info?.name;
		
		if (isSameWorkflow) {
			console.log('📂 Restoring saved workflow state...');
			this.currentWorkflow = JSON.parse(JSON.stringify(this.savedWorkflowState.workflow));
		} else {
			console.log('📋 Loading fresh workflow:', workflow.info?.name);
			this.currentWorkflow = JSON.parse(JSON.stringify(workflow));
		}
		
		// Use the workflow extension importer
		if (this.schemaGraph.api && this.schemaGraph.api.workflow) {
			this.schemaGraph.api.graph.clear();
			this.schemaGraph.api.workflow.import(this.currentWorkflow, WORKFLOW_SCHEMA_NAME);
			
			// Build graphNodes array from imported nodes
			this.graphNodes = [];
			const allNodes = this.schemaGraph.api.node.list();
			allNodes.forEach((node, idx) => {
				if (isWorkflowNode(node)) {
					node.workflowIndex = idx;
					this.graphNodes[idx] = node;
				}
			});
			
			console.log('✅ Workflow loaded via extension:', this.graphNodes.filter(n => n).length, 'nodes');
		} else {
			// Fallback: manual creation
			this.schemaGraph.api.graph.clear();
			this.graphNodes = [];
			
			workflow.nodes.forEach((node, index) => {
				this.createNode(node, index);
			});
			
			workflow.edges.forEach(edge => {
				this.createEdge(edge);
			});
			
			console.log('✅ Workflow loaded manually:', this.graphNodes.filter(n => n).length, 'nodes');
		}
		
		// Restore view or apply layout
		if (isSameWorkflow && this.savedWorkflowState.view) {
			this.schemaGraph.api.view.import(this.savedWorkflowState.view);
		} else {
			setTimeout(() => {
				this.schemaGraph.api.layout.apply('hierarchical-vertical');
				setTimeout(() => this.schemaGraph.api.view.center(), 50);
			}, 0);
		}
		
		return true;
	}
	
	// ====================================================================
	// Validation
	// ====================================================================
	
	validateWorkflow(workflow) {
		if (!workflow || !workflow.nodes || !Array.isArray(workflow.nodes)) {
			console.error('❌ Invalid workflow: missing nodes array');
			return false;
		}
		
		if (!workflow.edges || !Array.isArray(workflow.edges)) {
			console.error('❌ Invalid workflow: missing edges array');
			return false;
		}
		
		// Validate node types exist
		for (let i = 0; i < workflow.nodes.length; i++) {
			const node = workflow.nodes[i];
			if (!node.type) {
				console.error(`❌ Invalid node at index ${i}: missing type`);
				return false;
			}
		}
		
		// Validate edge indices
		for (const edge of workflow.edges) {
			if (edge.source < 0 || edge.source >= workflow.nodes.length) {
				console.error(`❌ Invalid edge source: ${edge.source}`);
				return false;
			}
			if (edge.target < 0 || edge.target >= workflow.nodes.length) {
				console.error(`❌ Invalid edge target: ${edge.target}`);
				return false;
			}
		}
		
		return true;
	}
	
	// ====================================================================
	// Manual Node Creation (fallback)
	// ====================================================================
	
	createNode(workflowNode, index) {
		// Determine node type name
		const nodeTypeName = `${WORKFLOW_SCHEMA_NAME}.${workflowNode.type}`;
		
		// Check if type is registered
		if (!this.schemaGraph.graph.nodeTypes[nodeTypeName]) {
			console.warn(`⚠️ Node type not registered: ${nodeTypeName}, skipping`);
			return null;
		}
		
		const pos = workflowNode.position || this.calculatePosition(index);
		
		try {
			const graphNode = this.schemaGraph.api.node.create(nodeTypeName, pos.x, pos.y);
			
			if (!graphNode) {
				console.error('❌ Failed to create node:', index, nodeTypeName);
				return null;
			}
			
			// Apply extra metadata
			if (workflowNode.extra) {
				if (workflowNode.extra.name) {
					graphNode.title = workflowNode.extra.name;
				}
				if (workflowNode.extra.color) {
					graphNode.color = workflowNode.extra.color;
				}
				graphNode.extra = { ...workflowNode.extra };
			}
			
			// Store workflow metadata
			graphNode.workflowIndex = index;
			graphNode.workflowData = {
				index: index,
				type: workflowNode.type,
				config: { ...workflowNode },
				status: 'pending'
			};
			
			this.graphNodes[index] = graphNode;
			return graphNode;
			
		} catch (e) {
			console.error('❌ Error creating node:', e);
			return null;
		}
	}
	
	calculatePosition(index) {
		const col = index % 5;
		const row = Math.floor(index / 5);
		return {
			x: 100 + col * 250,
			y: 100 + row * 150
		};
	}
	
	// ====================================================================
	// Manual Edge Creation (fallback)
	// ====================================================================
	
	createEdge(edge) {
		const sourceNode = this.graphNodes[edge.source];
		const targetNode = this.graphNodes[edge.target];
		
		if (!sourceNode || !targetNode) {
			console.error('❌ Invalid edge - missing nodes:', edge);
			return null;
		}
		
		// Find slot indices by name
		let sourceSlot = this.findOutputSlot(sourceNode, edge.source_slot);
		let targetSlot = this.findInputSlot(targetNode, edge.target_slot);
		
		if (sourceSlot === -1) sourceSlot = 0;
		if (targetSlot === -1) targetSlot = 0;
		
		const link = this.schemaGraph.api.link.create(
			sourceNode, sourceSlot,
			targetNode, targetSlot
		);
		
		if (link) {
			link.workflowData = {
				source: edge.source,
				target: edge.target,
				source_slot: edge.source_slot,
				target_slot: edge.target_slot
			};
			if (edge.extra) {
				link.extra = { ...edge.extra };
			}
		}
		
		return link;
	}
	
	findOutputSlot(node, slotName) {
		if (!slotName || !node.outputs) return 0;
		
		// Try exact match
		for (let i = 0; i < node.outputs.length; i++) {
			if (node.outputs[i].name === slotName) return i;
		}
		
		// Try base name for dotted notation (cases.c1 -> cases)
		const dotIdx = slotName.indexOf('.');
		if (dotIdx !== -1) {
			const baseName = slotName.substring(0, dotIdx);
			for (let i = 0; i < node.outputs.length; i++) {
				if (node.outputs[i].name === baseName) return i;
			}
		}
		
		return -1;
	}
	
	findInputSlot(node, slotName) {
		if (!slotName || !node.inputs) return 0;
		
		// Try exact match
		for (let i = 0; i < node.inputs.length; i++) {
			if (node.inputs[i].name === slotName) return i;
		}
		
		// Try base name for dotted notation (tools.t1 -> tools)
		const dotIdx = slotName.indexOf('.');
		if (dotIdx !== -1) {
			const baseName = slotName.substring(0, dotIdx);
			for (let i = 0; i < node.inputs.length; i++) {
				if (node.inputs[i].name === baseName) return i;
			}
		}
		
		return -1;
	}
	
	// ====================================================================
	// State Updates
	// ====================================================================
	
	updateNodeState(nodeIndex, status, data = {}) {
		const graphNode = this.graphNodes[nodeIndex];
		if (!graphNode) return;
		
		if (graphNode.workflowData) {
			graphNode.workflowData.status = status;
			graphNode.workflowData.output = data.output;
			graphNode.workflowData.error = data.error;
		}
		
		// Update color based on status
		const colorMap = {
			'pending': '#4a5568',
			'ready': '#3182ce',
			'running': '#805ad5',
			'completed': '#38a169',
			'failed': '#e53e3e',
			'skipped': '#718096'
		};
		graphNode.color = colorMap[status] || graphNode.color;
		
		// Highlight if running
		if (status === 'running') {
			this.schemaGraph.api.node.select(graphNode, false);
		}
		
		this.schemaGraph.api.util.redraw();
	}
	
	clearState() {
		this.graphNodes.forEach((node, index) => {
			if (node) {
				this.updateNodeState(index, 'pending');
			}
		});
		this.schemaGraph.api.node.clearSelection();
	}
	
	// ====================================================================
	// Export/Sync
	// ====================================================================
	
	exportWorkflow() {
		if (!this.currentWorkflow) return null;
		
		// Use workflow extension exporter if available
		if (this.schemaGraph.api && this.schemaGraph.api.workflow) {
			const exported = this.schemaGraph.api.workflow.export(WORKFLOW_SCHEMA_NAME, this.currentWorkflow);
			if (exported) {
				this.currentWorkflow = exported;
				return JSON.parse(JSON.stringify(exported));
			}
		}
		
		// Fallback: manual sync
		this.syncWorkflowFromGraph();
		return JSON.parse(JSON.stringify(this.currentWorkflow));
	}
	
	syncWorkflowFromGraph() {
		if (!this.currentWorkflow) return;
		
		console.log('🔄 Syncing workflow from graph...');
		
		const graphNodes = this.schemaGraph.graph.nodes;
		const graphLinks = this.schemaGraph.graph.links;
		
		// Build new nodes array
		const newNodes = [];
		const nodeIndexMap = new Map();
		
		graphNodes.forEach((graphNode) => {
			if (!isWorkflowNode(graphNode)) return;
			
			const newIndex = newNodes.length;
			
			// Extract type from node
			let nodeType = graphNode.modelName || graphNode.workflowType;
			if (!nodeType && graphNode.type) {
				const parts = graphNode.type.split('.');
				nodeType = parts[parts.length - 1];
			}
			
			const node = {
				type: nodeType,
				position: {
					x: Math.round(graphNode.pos[0]),
					y: Math.round(graphNode.pos[1])
				}
			};
			
			// Preserve config fields
			if (graphNode.workflowData?.config) {
				Object.assign(node, graphNode.workflowData.config);
				node.position = {
					x: Math.round(graphNode.pos[0]),
					y: Math.round(graphNode.pos[1])
				};
			}
			
			// Preserve extra metadata
			if (graphNode.extra) {
				node.extra = { ...graphNode.extra };
			}
			
			newNodes.push(node);
			nodeIndexMap.set(graphNode.id, newIndex);
		});
		
		// Build new edges array
		const newEdges = [];
		
		for (const linkId in graphLinks) {
			if (!graphLinks.hasOwnProperty(linkId)) continue;
			
			const link = graphLinks[linkId];
			const sourceNode = this.schemaGraph.graph.getNodeById(link.origin_id);
			const targetNode = this.schemaGraph.graph.getNodeById(link.target_id);
			
			if (!sourceNode || !targetNode) continue;
			if (!isWorkflowNode(sourceNode) || !isWorkflowNode(targetNode)) continue;
			
			const sourceIndex = nodeIndexMap.get(link.origin_id);
			const targetIndex = nodeIndexMap.get(link.target_id);
			
			if (sourceIndex === undefined || targetIndex === undefined) continue;
			
			// Get slot names
			const sourceSlot = sourceNode.outputs?.[link.origin_slot]?.name || 'output';
			const targetSlot = targetNode.inputs?.[link.target_slot]?.name || 'input';
			
			const edge = {
				source: sourceIndex,
				target: targetIndex,
				source_slot: sourceSlot,
				target_slot: targetSlot
			};
			
			// Preserve extra metadata
			if (link.extra) {
				edge.extra = { ...link.extra };
			} else if (link.workflowData) {
				if (link.workflowData.extra) edge.extra = { ...link.workflowData.extra };
			}
			
			newEdges.push(edge);
		}
		
		// Update workflow
		this.currentWorkflow.nodes = newNodes;
		this.currentWorkflow.edges = newEdges;
		
		// Rebuild graphNodes array
		this.graphNodes = [];
		graphNodes.forEach((graphNode, idx) => {
			if (isWorkflowNode(graphNode)) {
				const newIndex = nodeIndexMap.get(graphNode.id);
				if (newIndex !== undefined) {
					this.graphNodes[newIndex] = graphNode;
					graphNode.workflowIndex = newIndex;
				}
			}
		});
		
		console.log('✅ Synced workflow:', newNodes.length, 'nodes,', newEdges.length, 'edges');
	}
	
	// ====================================================================
	// Node Addition (for context menu)
	// ====================================================================
	
	addNodeAtPosition(nodeType, x, y) {
		if (!this.isWorkflowMode || !this.currentWorkflow) {
			console.warn('⚠️ Not in workflow mode');
			return null;
		}
		
		const nodeTypeName = nodeType.includes('.') ? nodeType : `${WORKFLOW_SCHEMA_NAME}.${nodeType}`;
		
		// Check if type is registered
		if (!this.schemaGraph.graph.nodeTypes[nodeTypeName]) {
			console.error('❌ Node type not registered:', nodeTypeName);
			return null;
		}
		
		const index = this.currentWorkflow.nodes.length;
		const workflowNode = {
			type: nodeType.includes('.') ? nodeType.split('.').pop() : nodeType,
			position: { x, y }
		};
		
		// Add to workflow
		this.currentWorkflow.nodes.push(workflowNode);
		
		// Create graph node
		const graphNode = this.createNode(workflowNode, index);
		
		if (graphNode) {
			console.log('✅ Added workflow node:', nodeType, 'at index', index);
			return graphNode;
		} else {
			this.currentWorkflow.nodes.pop();
			return null;
		}
	}
}

// ========================================================================
// Context Menu Integration
// ========================================================================

function addWorkflowNodeAtPosition(nodeType, wx, wy) {
	if (!workflowVisualizer || !workflowVisualizer.isWorkflowMode) {
		console.warn('⚠️ Not in workflow mode');
		return;
	}
	
	workflowVisualizer.addNodeAtPosition(nodeType, wx, wy);
}

// ========================================================================
// WorkflowClient - Backend Communication
// ========================================================================

class WorkflowClient {
	constructor(baseUrl) {
		this.baseUrl = baseUrl;
		this.websocket = null;
		this.eventHandlers = new Map();
	}
	
	// ====================================================================
	// WebSocket Connection
	// ====================================================================
	
	connectWebSocket() {
		const wsUrl = this.baseUrl.replace('http://', 'ws://').replace('https://', 'wss://');
		const endpoint = `${wsUrl}/workflow/events`;
		
		this.websocket = new WebSocket(endpoint);
		
		this.websocket.onopen = () => {
			console.log('✅ Workflow WebSocket connected');
			this.emit('connected', {});
		};
		
		this.websocket.onmessage = (event) => {
			try {
				const data = JSON.parse(event.data);
				this.handleMessage(data);
			} catch (error) {
				console.error('❌ WebSocket parse error:', error);
			}
		};
		
		this.websocket.onerror = (error) => {
			console.error('❌ WebSocket error:', error);
			this.emit('error', { error });
		};
		
		this.websocket.onclose = () => {
			console.log('🔌 WebSocket disconnected');
			this.emit('disconnected', {});
			
			// Reconnect after delay
			setTimeout(() => this.connectWebSocket(), 2000);
		};
	}
	
	disconnectWebSocket() {
		if (this.websocket) {
			this.websocket.close();
			this.websocket = null;
		}
	}
	
	handleMessage(data) {
		if (data.type === 'workflow_event') {
			const event = data.event;
			this.emit('workflow_event', event);
			this.emit(event.event_type, event);
		}
	}
	
	// ====================================================================
	// Event System
	// ====================================================================
	
	on(eventType, handler) {
		if (!this.eventHandlers.has(eventType)) {
			this.eventHandlers.set(eventType, []);
		}
		this.eventHandlers.get(eventType).push(handler);
	}
	
	off(eventType, handler) {
		if (this.eventHandlers.has(eventType)) {
			const handlers = this.eventHandlers.get(eventType);
			const idx = handlers.indexOf(handler);
			if (idx !== -1) handlers.splice(idx, 1);
		}
	}
	
	emit(eventType, data) {
		if (this.eventHandlers.has(eventType)) {
			this.eventHandlers.get(eventType).forEach(handler => {
				try {
					handler(data);
				} catch (error) {
					console.error(`❌ Event handler error [${eventType}]:`, error);
				}
			});
		}
	}
	
	// ====================================================================
	// API Methods
	// ====================================================================
	
	async startWorkflow(workflow, initialData = null) {
		const wf = JSON.stringify({ workflow: workflow, initial_data: initialData });
		const response = await fetch(`${this.baseUrl}/workflow/start`, {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: wf
		});
		
		if (!response.ok) {
			throw new Error(`Failed to start workflow: ${response.statusText}`);
		}
		
		return await response.json();
	}
	
	async cancelWorkflow(executionId) {
		const response = await fetch(`${this.baseUrl}/workflow/${executionId}/cancel`, {
			method: 'POST'
		});
		
		if (!response.ok) {
			throw new Error(`Failed to cancel workflow: ${response.statusText}`);
		}
		
		return await response.json();
	}
	
	async getWorkflowStatus(executionId) {
		const response = await fetch(`${this.baseUrl}/workflow/${executionId}/status`, {
			method: 'POST'
		});
		
		if (!response.ok) {
			throw new Error(`Failed to get status: ${response.statusText}`);
		}
		
		return await response.json();
	}
	
	async listWorkflows() {
		const response = await fetch(`${this.baseUrl}/workflow/list`, {
			method: 'POST'
		});
		
		if (!response.ok) {
			throw new Error(`Failed to list workflows: ${response.statusText}`);
		}
		
		return await response.json();
	}
	
	async provideUserInput(executionId, nodeId, inputData) {
		const response = await fetch(`${this.baseUrl}/workflow/${executionId}/input`, {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ node_id: nodeId, input_data: inputData })
		});
		
		if (!response.ok) {
			throw new Error(`Failed to provide input: ${response.statusText}`);
		}
		
		return await response.json();
	}
}

// ========================================================================
// Exports
// ========================================================================

if (typeof module !== 'undefined' && module.exports) {
	module.exports = { 
		WorkflowClient, 
		WorkflowVisualizer, 
		fetchAndRegisterWorkflowSchema,
		addWorkflowNodeAtPosition,
		isWorkflowNode,
		WORKFLOW_SCHEMA_NAME
	};
}
