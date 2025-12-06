/*
========================================================================
NUMEL WORKFLOW - SchemaGraph Integration
========================================================================
*/

const WORKFLOW_SCHEMA_NAME = "workflow";

// Valid workflow node types from backend schema
const VALID_WORKFLOW_TYPES = new Set([
	'start', 'end', 'agent', 'prompt', 'tool', 
	'transform', 'decision', 'merge', 'user_input'
]);

// ========================================================================
// Register Workflow Node Types with SchemaGraph
// ========================================================================

function registerWorkflowNodeTypes(schemaGraph) {
	console.log('📝 Registering workflow node types with SchemaGraph...');
	
	// Unregister any existing workflow node types first (for hot reload)
	VALID_WORKFLOW_TYPES.forEach(type => {
		const nodeTypeName = `${WORKFLOW_SCHEMA_NAME}.${type}`;
		if (schemaGraph.graph.nodeTypes[nodeTypeName]) {
			delete schemaGraph.graph.nodeTypes[nodeTypeName];
			console.log(`🔄 Unregistered existing: ${nodeTypeName}`);
		}
	});
	
	// Register fresh node types
	VALID_WORKFLOW_TYPES.forEach(type => {
		const nodeTypeName = `${WORKFLOW_SCHEMA_NAME}.${type}`;
		
		// Create a node class for this workflow type
		class WorkflowNode {
			constructor() {
				// CRITICAL: Set type FIRST before anything else for SchemaGraph serialization
				this.type = nodeTypeName;
				this.isNative = false;
				
				// Initialize basic node properties
				this.id = Math.random().toString(36).substr(2, 9);
				this.title = `${WORKFLOW_SCHEMA_NAME}.${type}`;
				this.pos = [0, 0];
				this.size = [200, 60];
				this.inputs = [];
				this.outputs = [];
				this.properties = {};
				this.graph = null;
				
				// Mark as workflow node
				this.isWorkflowNode = true;
				this.workflowType = type;
				
				// Setup inputs/outputs based on type
				this.setupSlots(type);
			}
			
			setupSlots(type) {
				switch (type) {
					case 'start':
						this.addOutput('output', 'Any');
						break;
					
					case 'end':
						this.addInput('input', 'Any');
						break;
					
					case 'agent':
					case 'prompt':
					case 'tool':
					case 'transform':
						this.addInput('input', 'Any');
						this.addOutput('output', 'Any');
						break;
					
					case 'decision':
						this.addInput('input', 'Any');
						this.addOutput('default', 'Any');
						break;
					
					case 'merge':
						this.addInput('input_0', 'Any');
						this.addInput('input_1', 'Any');
						this.addOutput('output', 'Any');
						break;
					
					case 'user_input':
						this.addInput('input', 'Any');
						this.addOutput('output', 'Any');
						break;
					
					default:
						this.addInput('input', 'Any');
						this.addOutput('output', 'Any');
				}
			}
			
			addInput(name, type) {
				this.inputs.push({ name, type, link: null });
				return this.inputs.length - 1;
			}
			
			addOutput(name, type) {
				this.outputs.push({ name, type, links: [] });
				return this.outputs.length - 1;
			}
			
			onExecute() {
				// Workflow nodes don't execute like schema nodes
				// Execution is handled by the workflow engine
			}
		}
		
		// Register with SchemaGraph
		schemaGraph.graph.nodeTypes[nodeTypeName] = WorkflowNode;
		console.log(`✅ Registered: ${nodeTypeName}`);
	});
	
	return true;
}

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
		
		const schemaData = await response.json();
		console.log('✅ Received workflow schema from backend:', schemaData);
		
		// Register workflow node types with SchemaGraph
		if (!registerWorkflowNodeTypes(schemaGraph)) {
			throw new Error('Failed to register workflow node types');
		}
		
		// Verify registration
		console.log('🔍 Verifying node type registration...');
		const registeredTypes = [];
		const missingTypes = [];
		
		VALID_WORKFLOW_TYPES.forEach(type => {
			const nodeTypeName = `${WORKFLOW_SCHEMA_NAME}.${type}`;
			if (schemaGraph.graph.nodeTypes[nodeTypeName]) {
				registeredTypes.push(nodeTypeName);
			} else {
				missingTypes.push(nodeTypeName);
			}
		});
		
		if (missingTypes.length > 0) {
			console.error('❌ Missing node type registrations:', missingTypes);
			return false;
		}
		
		console.log('✅ All node types registered:', registeredTypes);
		console.log('✅ Workflow system initialized');
		return true;
		
	} catch (error) {
		console.error('❌ Error initializing workflow system:', error);
		return false;
	}
}

// ========================================================================
// Helper: Node Type Validation
// ========================================================================

function isValidWorkflowType(type) {
	return VALID_WORKFLOW_TYPES.has(type);
}

function isWorkflowGraphNode(graphNode) {
	// Must have workflow type marker
	if (!graphNode.workflowType) return false;
	
	// Must be a valid type
	if (!isValidWorkflowType(graphNode.workflowType)) return false;
	
	// Must be explicitly marked as workflow node
	if (!graphNode.isWorkflowNode) return false;
	
	return true;
}

// ========================================================================
// Helper: Create Workflow Node ID
// ========================================================================

function createWorkflowNodeId(type, index) {
	return `${type}_${index}_${Date.now()}`;
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
		
		// Save complete chat state (including graph and view)
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
		
		// Disable all non-native schemas
		const allSchemas = this.schemaGraph.api.schema.list();
		allSchemas.forEach(schemaName => {
			this.schemaGraph.api.schema.disable(schemaName);
		});
		
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
			
			// Save workflow definition and view state (not SchemaGraph's graph state)
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
			
			// Import graph state
			this.schemaGraph.api.graph.import(this.savedChatState.graph, false);
			
			// Restore view
			this.schemaGraph.api.view.import(this.savedChatState.view);
			
			// Re-enable previously enabled schemas
			this.savedChatState.enabledSchemas.forEach(schemaName => {
				this.schemaGraph.api.schema.enable(schemaName);
			});
			
			console.log('✅ Restored chat state:', {
				nodes: this.schemaGraph.api.node.list().length,
				schemas: this.schemaGraph.api.schema.listEnabled()
			});
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
		
		// CRITICAL: Verify all required node types are registered
		const missingTypes = [];
		workflow.nodes.forEach(node => {
			const nodeTypeName = `${WORKFLOW_SCHEMA_NAME}.${node.type}`;
			if (!this.schemaGraph.graph.nodeTypes[nodeTypeName]) {
				missingTypes.push(nodeTypeName);
			}
		});
		
		if (missingTypes.length > 0) {
			console.error('❌ Missing node type registrations:', missingTypes);
			console.error('Available types:', Object.keys(this.schemaGraph.graph.nodeTypes));
			return false;
		}
		
		// Check if we have saved state for this workflow
		const isSameWorkflow = this.savedWorkflowState && 
							this.savedWorkflowState.workflow.info?.name === workflow.info?.name;
		
		if (isSameWorkflow) {
			console.log('📂 Restoring saved workflow state...');
			
			// Use the saved workflow definition (which has updated positions from sync)
			this.currentWorkflow = JSON.parse(JSON.stringify(this.savedWorkflowState.workflow));
			
			// IMPORTANT: Don't use SchemaGraph's saved graph state because it doesn't 
			// properly preserve node types. Instead, recreate nodes from workflow definition.
			this.schemaGraph.api.graph.clear();
			this.graphNodes = [];
			
			// Recreate nodes from workflow definition (has saved positions)
			this.currentWorkflow.nodes.forEach((node, index) => {
				this.createNode(node, index);
			});
			
			// Recreate edges
			this.currentWorkflow.edges.forEach(edge => {
				this.createEdge(edge);
			});
			
			// Restore view (zoom/pan) only
			if (this.savedWorkflowState.view) {
				this.schemaGraph.api.view.import(this.savedWorkflowState.view);
			}
			
			console.log('✅ Restored workflow state:', {
				workflowNodes: this.graphNodes.filter(n => n).length,
				allNodes: this.schemaGraph.api.node.list().length
			});
			
		} else {
			console.log('📋 Loading fresh workflow:', workflow.info?.name);
			
			this.currentWorkflow = JSON.parse(JSON.stringify(workflow));
			
			this.schemaGraph.api.graph.clear();
			this.graphNodes = [];
			
			// Create nodes
			workflow.nodes.forEach((node, index) => {
				this.createNode(node, index);
			});
			
			// Create edges
			workflow.edges.forEach(edge => {
				this.createEdge(edge);
			});
			
			// Apply layout and center
			setTimeout(() => {
				this.schemaGraph.api.layout.apply('hierarchical-vertical');
				setTimeout(() => {
					this.schemaGraph.api.view.center();
				}, 50);
			}, 0);
			
			console.log('✅ Workflow loaded:', this.graphNodes.filter(n => n).length, 'nodes');
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
		
		// Validate node types
		for (let i = 0; i < workflow.nodes.length; i++) {
			const node = workflow.nodes[i];
			if (!node.type || (!node.isNative && !isValidWorkflowType(node.type))) {
				console.error(`❌ Invalid node type at index ${i}: ${node.type}`);
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
	// Node Creation
	// ====================================================================
	
	createNode(workflowNode, index) {
		// Validate node type
		if (!workflowNode.isNative && !isValidWorkflowType(workflowNode.type)) {
			console.error('❌ Invalid workflow node type:', workflowNode.type);
			return null;
		}

		const nodeType = `${workflowNode.isNative ? "Native" : WORKFLOW_SCHEMA_NAME}.${workflowNode.type}`;
		const pos = workflowNode.position || this.calculatePosition(index);
		
		try {
			const graphNode = this.schemaGraph.api.node.create(nodeType, pos.x, pos.y);
			
			if (!graphNode) {
				console.error('❌ Failed to create node:', index, nodeType);
				return null;
			}
			
			// Mark as workflow node
			graphNode.isWorkflowNode = true;
			graphNode.isNative = !!workflowNode.isNative;

			// Handle native nodes
			if (workflowNode.isNative) {
				graphNode.workflowData = {
					index: index,
					id: workflowNode.id,
					type: workflowNode.type,
					nodeType: nodeType,
					isNative: true,
					status: 'pending'
				};
				
				this.graphNodes[index] = graphNode;
				return graphNode;
			}
			
			// Handle workflow nodes
			const workflowType = workflowNode.type;
			graphNode.workflowType = workflowType;
			
			// Set schemaName and modelName for proper serialization
			graphNode.schemaName = 'Workflow';
			graphNode.modelName = workflowType;
			
			// Customize label with emoji and index
			const emoji = this.getNodeEmoji(workflowType);
			const label = workflowNode.label || workflowType;
			graphNode.title = `${emoji} [${index}] ${label}`;
			graphNode.color = this.getNodeColor(workflowType);
			
			// Handle special cases - decision node branches
			if (workflowType === 'decision' && workflowNode.config?.branches) {
				graphNode.outputs = [];
				Object.keys(workflowNode.config.branches).forEach(branchName => {
					graphNode.addOutput(branchName, 'Any');
				});
			}
			
			// Handle merge node - multiple inputs
			if (workflowType === 'merge') {
				// Count incoming edges to this node
				const incomingCount = this.currentWorkflow.edges.filter(e => e.target === index).length;
				graphNode.inputs = [];
				for (let i = 0; i < Math.max(incomingCount, 2); i++) {
					graphNode.addInput(`input_${i}`, 'Any');
				}
			}
			
			// Store workflow metadata
			graphNode.workflowData = {
				index: index,
				id: workflowNode.id,
				type: workflowType,
				nodeType: nodeType,
				config: workflowNode.config,
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
	// Edge Creation
	// ====================================================================
	
	createEdge(edge) {
		const sourceNode = this.graphNodes[edge.source];
		const targetNode = this.graphNodes[edge.target];
		
		if (!sourceNode || !targetNode) {
			console.error('❌ Invalid edge - missing nodes:', edge);
			return null;
		}
		
		// Find slot indices
		let sourceSlot = 0;
		if (edge.source_slot !== 'output') {
			sourceSlot = sourceNode.outputs?.findIndex(o => o.name === edge.source_slot);
			if (sourceSlot === -1) sourceSlot = 0;
		}
		
		let targetSlot = 0;
		if (edge.target_slot !== 'input') {
			targetSlot = targetNode.inputs?.findIndex(i => i.name === edge.target_slot);
			if (targetSlot === -1) targetSlot = 0;
		}
		
		// Create link using SchemaGraph's API
		const link = this.schemaGraph.api.link.create(
			sourceNode, sourceSlot,
			targetNode, targetSlot
		);
		
		if (link) {
			link.workflowData = {
				source: edge.source,
				target: edge.target,
				source_slot: edge.source_slot || 'output',
				target_slot: edge.target_slot || 'input',
				filter: edge.filter,
				label: edge.label
			};
			
			console.log('✅ Created edge:', edge.source, '→', edge.target);
		}
		
		return link;
	}
	
	// ====================================================================
	// State Updates
	// ====================================================================
	
	updateNodeState(nodeIndex, status, data = {}) {
		const graphNode = this.graphNodes[nodeIndex];
		if (!graphNode || !graphNode.workflowData) return;
		
		graphNode.workflowData.status = status;
		graphNode.workflowData.output = data.output;
		graphNode.workflowData.error = data.error;
		
		// Update visual state
		const emoji = this.getStatusEmoji(status);
		const baseLabel = graphNode.workflowData.label || graphNode.workflowData.type;
		graphNode.title = `${emoji} [${nodeIndex}] ${baseLabel}`;
		
		// Update color based on status
		const colorMap = {
			'pending': '#4a5568',
			'ready': '#3182ce',
			'running': '#805ad5',
			'completed': '#38a169',
			'failed': '#e53e3e',
			'skipped': '#718096'
		};
		graphNode.color = colorMap[status] || '#4a5568';
		
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
		
		this.syncWorkflowFromGraph();
		
		// Final validation before export
		if (!this.validateWorkflow(this.currentWorkflow)) {
			console.error('❌ Workflow validation failed before export');
			return null;
		}
		
		return JSON.parse(JSON.stringify(this.currentWorkflow));
	}
	
	syncWorkflowFromGraph() {
		if (!this.currentWorkflow) return;
		
		console.log('🔄 Syncing workflow from graph...');
		
		// Access nodes and links directly from the graph
		const graphNodes = this.schemaGraph.graph.nodes;
		const graphLinks = this.schemaGraph.graph.links;
		
		// Build new nodes array - STRICT FILTERING
		const newNodes = [];
		const nodeIndexMap = new Map(); // graphNode.id -> new index
		
		graphNodes.forEach((graphNode) => {
			// Include both workflow and native nodes
			if (!isWorkflowGraphNode(graphNode) && !graphNode.isNative) {
				return; // Skip non-workflow and non-native nodes
			}
			
			const newIndex = newNodes.length;
			let nodeType, label, nodeId, config;
			
			if (graphNode.isNative) {
				// Handle native nodes
				nodeType = graphNode.title || 'native';
				label = graphNode.title;
				nodeId = graphNode.id || `native_${newIndex}`;
				config = graphNode.properties || {};
			} else {
				// Handle workflow nodes
				const workflowData = graphNode.workflowData || {};
				nodeType = graphNode.workflowType;
				
				// STRICT: Validate type
				if (!isValidWorkflowType(nodeType)) {
					console.warn('⚠️ Skipping node with invalid type:', nodeType);
					return;
				}
				
				// Extract label (remove emoji and index prefix)
				label = graphNode.title || nodeType;
				label = label.replace(/^[^\]]*\]\s*/, '').replace(/^[^\s]+\s+/, '');

				nodeId = workflowData.id || createWorkflowNodeId(nodeType, newIndex);
				config = workflowData.config || {};
			}

			const node = {
				id: nodeId,
				type: nodeType,
				label: label,
				position: {
					x: Math.round(graphNode.pos[0]),
					y: Math.round(graphNode.pos[1])
				},
				config: config,
				isNative: !!graphNode.isNative
			};
			
			newNodes.push(node);
			nodeIndexMap.set(graphNode.id, newIndex);
		});
		
		// Build new edges array - STRICT FILTERING
		const newEdges = [];
		
		for (const linkId in graphLinks) {
			if (!graphLinks.hasOwnProperty(linkId)) continue;
			
			const link = graphLinks[linkId];
			const sourceNode = this.schemaGraph.graph.getNodeById(link.origin_id);
			const targetNode = this.schemaGraph.graph.getNodeById(link.target_id);
			
			if (!sourceNode || !targetNode) continue;
			
			// Include edges between workflow nodes and/or native nodes
			if ((!sourceNode.isNative && !isWorkflowGraphNode(sourceNode)) ||
			    (!targetNode.isNative && !isWorkflowGraphNode(targetNode))) {
				continue;
			}
			
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
			
			// Preserve additional edge data if it exists
			if (link.workflowData) {
				if (link.workflowData.filter) edge.filter = link.workflowData.filter;
				if (link.workflowData.label) edge.label = link.workflowData.label;
			}
			
			newEdges.push(edge);
		}
		
		// Update workflow
		this.currentWorkflow.nodes = newNodes;
		this.currentWorkflow.edges = newEdges;
		
		// Rebuild graphNodes array to match new indices
		const newGraphNodes = [];
		let workflowNodeIndex = 0;
		graphNodes.forEach((graphNode) => {
			if (isWorkflowGraphNode(graphNode)) {
				newGraphNodes[workflowNodeIndex] = graphNode;
				if (graphNode.workflowData) {
					graphNode.workflowData.index = workflowNodeIndex;
				}
				workflowNodeIndex++;
			}
		});
		this.graphNodes = newGraphNodes;
		
		console.log('✅ Synced workflow:', newNodes.length, 'nodes,', newEdges.length, 'edges');
		
		// Validate result
		if (!this.validateWorkflow(this.currentWorkflow)) {
			console.error('❌ Sync produced invalid workflow!');
		}
	}
	
	// ====================================================================
	// Helpers
	// ====================================================================
	
	getNodeColor(type) {
		const map = {
			'start'      : '#4ade80',
			'end'        : '#f87171',
			'agent'      : '#60a5fa',
			'prompt'     : '#a78bfa',
			'tool'       : '#fb923c',
			'transform'  : '#fbbf24',
			'decision'   : '#ec4899',
			'merge'      : '#14b8a6',
			'user_input' : '#f472b6'
		};
		return map[type] || '#94a3b8';
	}

	getNodeEmoji(type) {
		const map = {
			'start'      : '🎬',
			'end'        : '🏁',
			'agent'      : '🤖',
			'prompt'     : '💭',
			'tool'       : '🔧',
			'transform'  : '🔄',
			'decision'   : '🔀', 
			'merge'      : '🔗',
			'user_input' : '👤'
		};
		return map[type] || '⚪';
	}
	
	getStatusEmoji(status) {
		const map = {
			'pending'   : '⏳',
			'ready'     : '▶️',
			'running'   : '▶️',
			'completed' : '✅',
			'failed'    : '❌',
			'skipped'   : '⭕'
		};
		return map[status] || '⚪';
	}
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
		const response = await fetch(`${this.baseUrl}/workflow/start`, {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ workflow, initial_data: initialData })
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
// Context Menu Integration - Add Workflow Node
// ========================================================================

function addWorkflowNodeAtPosition(nodeType, wx, wy) {
	if (!workflowVisualizer || !workflowVisualizer.isWorkflowMode) {
		console.warn('⚠️ Not in workflow mode');
		return;
	}
	
	// Validate type
	if (!isValidWorkflowType(nodeType)) {
		console.error('❌ Invalid workflow node type:', nodeType);
		return;
	}
	
	// Create workflow node config
	const index = workflowVisualizer.currentWorkflow.nodes.length;
	const workflowNode = {
		id: createWorkflowNodeId(nodeType, index),
		type: nodeType,
		label: nodeType,
		position: { x: wx, y: wy },
		config: {}
	};
	
	// Add to workflow
	workflowVisualizer.currentWorkflow.nodes.push(workflowNode);
	
	// Create graph node
	const graphNode = workflowVisualizer.createNode(workflowNode, index);
	
	if (graphNode) {
		console.log('✅ Added workflow node:', nodeType, 'at index', index);
	} else {
		// Remove from workflow if creation failed
		workflowVisualizer.currentWorkflow.nodes.pop();
	}
}

// Export for use in other scripts
if (typeof module !== 'undefined' && module.exports) {
	module.exports = { 
		WorkflowClient, 
		WorkflowVisualizer, 
		fetchAndRegisterWorkflowSchema,
		addWorkflowNodeAtPosition,
		isValidWorkflowType
	};
}
