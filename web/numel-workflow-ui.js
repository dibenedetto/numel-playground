/* ========================================================================
   NUMEL WORKFLOW UI - User Interface Logic
   ======================================================================== */

// Constants
const FORCE_PREVIEW_ON_SAME_DATA = true;


// Global State
let client             = null;
let visualizer         = null;
let agentChatManager   = null;
let schemaGraph        = null;
let currentExecutionId = null;
let pendingRemoveName  = null;
let singleMode         = true;
let workflowDirty      = true;
let fileUploadManager  = null;

// DOM Elements
const $ = id => document.getElementById(id);

// ========================================================================
// Initialization
// ========================================================================

document.addEventListener('DOMContentLoaded', () => {
	// Initialize SchemaGraph
	schemaGraph = new SchemaGraphApp('sg-main-canvas');

	// Register callback for context menu node creation
	schemaGraph.onAddWorkflowNode = (nodeType, wx, wy) => {
		if (visualizer) {
			visualizer.addNodeAtPosition(nodeType, wx, wy);
		}
	};

	// schemaGraph.api.events.enableDebug();
	schemaGraph.api.events.onGraphChanged((e) => {
		workflowDirty = true;
		updateClearButtonState();
		// console.log('Graph modified:', e.originalEvent);
	});

	// Handle link creation - trace upward for preview data
	schemaGraph.api.events.onLinkCreated((data) => {
		handleLinkCreatedForPreview(data);
	});

	// Handle link removal - refresh preview data for affected nodes
	schemaGraph.api.events.onLinkRemoved((data) => {
		handleLinkRemovedForPreview(data);
	});

	// Handle node removal - refresh downstream preview nodes after graph settles
	schemaGraph.api.events.onNodeRemoved(() => {
		// Delay to let preservePreviewLinks reconnect first
		setTimeout(() => refreshAllPreviewNodes(), 100);
	});

	schemaGraph.eventBus.on('node:buttonClicked', async (data) => {
		console.log('Button clicked:', data.buttonId, 'on node:', data.nodeId);

		// Handle tool call execute button
		if (data.buttonId === 'execute') {
			const node = schemaGraph.graph.getNodeById(data.nodeId);
			if (node && schemaGraph.api.schemaTypes.isToolCall(node)) {
				await executeToolCall(node);
			}
		}
	});

	schemaGraph.eventBus.on('node:fileDrop', (data) => {
		console.log('Files dropped on node:', data.nodeId, data.files);
	});

	// Listen for workflow options changes to trigger sync
	schemaGraph.eventBus.on('workflow:optionsChanged', (data) => {
		workflowDirty = true;
		console.log('Workflow options changed:', data.options);
	});

	// Refresh workflow options panel when a workflow is imported/loaded
	schemaGraph.eventBus.on(GraphEvents.WORKFLOW_IMPORTED, () => {
		populateWorkflowOptionsPanel();
	});

	if (true) {
		const sourceMetaTypeName  = `${WORKFLOW_SCHEMA_NAME}.SourceMeta` ;
		const dataTensorTypeName  = `${WORKFLOW_SCHEMA_NAME}.DataTensor` ;
		const previewFlowTypeName = `${WORKFLOW_SCHEMA_NAME}.PreviewFlow`;
		const startFlowTypeName   = `${WORKFLOW_SCHEMA_NAME}.StartFlow`  ;
		const endFlowTypeName     = `${WORKFLOW_SCHEMA_NAME}.EndFlow`    ;
		const agentChatTypeName   = `${WORKFLOW_SCHEMA_NAME}.AgentChat`  ;
		const toolCallTypeName    = `${WORKFLOW_SCHEMA_NAME}.ToolCall`   ;

		schemaGraph.api.schemaTypes.setTypes({
			sourceMeta               : sourceMetaTypeName,
			dataTensor               : dataTensorTypeName,
			preview                  : previewFlowTypeName,
			startNode                : startFlowTypeName,
			endNode                  : endFlowTypeName,
			agentChat                : agentChatTypeName,
			toolCall                 : toolCallTypeName,
			metaInputSlot            : "meta",
			workflowOptions          : "WorkflowOptions",
			workflowExecutionOptions : "WorkflowExecutionOptions",
			previewSlotMap           : { "flow_in": "flow_out" },
			hiddenFields             : ["extra"],
			pairedNodes              : [
				["loop_start_flow"    , "loop_end_flow"    ],
				["for_each_start_flow", "for_each_end_flow"],
			],
		});

		// Configure section-based node header colors
		schemaGraph.api.schemaTypes.setSectionColors({
			'Data Sources'   : '#4a7c59',  // Forest green
			'Native Types'   : '#9370db',  // Medium purple
			'Configurations' : '#5c7caa',  // Steel blue
			'Workflow'       : '#7a5c8a',  // Muted purple
			'Interactive'    : '#c2714f',  // Terracotta
			'Miscellanea'    : '#6b6b7a',  // Gray
			'Tutorial'       : '#e67e22',  // Orange (tutorial extension)
		});

		schemaGraph.api.canvasDrop.setAccept("image/*,audio/*,video/*,text/*,model/*,application/json,application/octet-stream,.glb,.gltf,.obj,.fbx,.stl");

		// schemaGraph.api.canvasDrop.setCreationCallback(async (file, x, y, app) => {
		// 	const metaNode = app.api.node.create(sourceMetaTypeName, x, y);

		// 	const setNativeInput = (node, slotName, value) => {
		// 		const idx = app._findInputSlotByName(node, slotName);
		// 		if (idx >= 0 && node.nativeInputs?.[idx]) {
		// 			node.nativeInputs[idx].value = value;
		// 		}
		// 	};

		// 	setNativeInput(metaNode, "name"     , file.name);
		// 	setNativeInput(metaNode, "mime_type", file.type);
		// 	setNativeInput(metaNode, "size"     , file.size);
		// 	setNativeInput(metaNode, "format"   , file.name.split(".").pop());
		// 	setNativeInput(metaNode, "source"   , "file://" + file.name);

		// 	const link = async (sourceNode, outputSlotName, targetNode, inputSlotName) => {
		// 		const srcIdx = app._findOutputSlotByName (sourceNode, outputSlotName);
		// 		const dstIdx = app._findInputSlotByName  (targetNode, inputSlotName );
		// 		await app.api.link.create(sourceNode, srcIdx, targetNode, dstIdx);
		// 	};

		// 	const dataNode = app.api.node.create(dataTensorTypeName, x + 1 * 240, y);
		// 	await link(metaNode, "get", dataNode, "meta");
			
		// 	const previewNode = app.api.node.create(previewFlowTypeName, x + 2 * 240, y);
		// 	await link(dataNode, "get", previewNode, "input");

		// 	await app._loadFileIntoDataNode(file, dataNode);

		// 	app.eventBus.emit("canvasDrop:nodeCreated", {
		// 		file          : {
		// 			name: file.name,
		// 			type: file.type,
		// 			size: file.size,
		// 		},
		// 		metaNodeId    : metaNode    .id,
		// 		dataNodeId    : dataNode    .id,
		// 		previewNodeId : previewNode .id,
		// 	});

		// 	return {
		// 		metaNode,
		// 		dataNode    : tensorNode,
		// 		totalHeight : Math.max(metaNode.size[1], dataNode.size[1], previewNode.size[1])
		// 	};
		// });

		schemaGraph.api.events.on("canvasDrop:nodeCreated", (data) => {
			console.log("Created nodes from file:", data.file.name);
			console.log("  Meta node ID:", data.metaNodeId);
			console.log("  Data node ID:", data.dataNodeId);
		});

		// When all files are processed
		schemaGraph.api.events.on("canvasDrop:complete", (data) => {
			console.log(`Processed ${data.fileCount} file(s)`);
		});

		// When file data is loaded into a node
		schemaGraph.api.events.on("node:dataLoaded", (data) => {
			console.log("Data loaded into node:", data.nodeId);
		});

		// When PreviewFlow mode is toggled
		schemaGraph.api.events.on("preview:modeToggled", (data) => {
			console.log("Preview mode:", data.expanded ? "expanded" : "collapsed");
		});

		schemaGraph.api.canvasDrop.setEnabled(true);
	}

	// Create visualizer
	visualizer = new WorkflowVisualizer(schemaGraph);
	visualizer.configure({
		defaultLayout: 'hierarchical-horizontal',
	});

	// Setup event listeners
	setupEventListeners();

	// Initial log
	addLog('info', '🚀 Numel Playground ready');
});

window.addEventListener('beforeunload', (e) => {
	if (client?.isConnected) {
		disconnect();
	}
});

function setupEventListeners() {
	// Connection
	$('connectBtn').addEventListener('click', toggleConnection);

	// Workflow management
	$('refreshListBtn')?.addEventListener('click', refreshWorkflowList);
	$('loadWorkflowBtn').addEventListener('click', loadSelectedWorkflow);
	$('uploadWorkflowBtn').addEventListener('click', () => $('workflowFileInput').click());
	$('downloadWorkflowBtn').addEventListener('click', downloadWorkflow);
	$('removeWorkflowBtn').addEventListener('click', removeSelectedWorkflow);
	$('workflowFileInput').addEventListener('change', handleFileUpload);

	// Workflow remove modal
	$('confirmRemoveBtn').addEventListener('click', confirmRemoveWorkflow);
	$('cancelRemoveBtn').addEventListener('click', closeRemoveModal);
	$('closeRemoveModalBtn').addEventListener('click', closeRemoveModal);

	// Clear workflow
	$('clearWorkflowBtn').addEventListener('click', clearWorkflow);

	// Mode switch
	$('singleModeSwitch').addEventListener('change', toggleWorkflowMode);

	// Single mode buttons
	$('singleImportBtn').addEventListener('click', () => $('singleWorkflowFileInput').click());
	$('singlePasteBtn' ).addEventListener('click', pasteWorkflowFromClipboard);
	$('singleDownloadBtn').addEventListener('click', downloadWorkflow);
	$('singleCopyBtn'  ).addEventListener('click', copyWorkflowToClipboard);
	$('pasteWorkflowBtn').addEventListener('click', pasteWorkflowFromClipboard);
	$('copyWorkflowBtn' ).addEventListener('click', copyWorkflowToClipboard);
	$('singleWorkflowFileInput').addEventListener('change', handleSingleImport);

	// Execution
	$('startBtn').addEventListener('click', startExecution);
	$('cancelBtn').addEventListener('click', cancelExecution);

	// Event log
	$('clearLogBtn').addEventListener('click', () => {
		$('eventLog').innerHTML = '';
		addLog('info', 'Log cleared');
	});

	// User input modal
	$('submitInputBtn').addEventListener('click', submitUserInput);
	$('cancelInputBtn').addEventListener('click', cancelUserInput);
	$('closeModalBtn').addEventListener('click', cancelUserInput);

	// Collapsible sections
	document.querySelectorAll('.nw-collapsible-header').forEach(header => {
		header.addEventListener('click', () => {
			const section = header.closest('.nw-collapsible');
			const targetId = header.getAttribute('data-target');
			const content = document.getElementById(targetId);

			if (section.classList.contains('expanded')) {
				section.classList.remove('expanded');
				content.style.display = 'none';
			} else {
				section.classList.add('expanded');
				content.style.display = 'block';
			}
		});
	});
}

function enableStart(enable) {
	$('singleModeSwitch' ).disabled = !enable;
	$('startBtn'         ).disabled = !enable;
	$('cancelBtn'        ).disabled = enable;
	$('singleImportBtn'  ).disabled = !enable;
	$('singlePasteBtn'   ).disabled = !enable;
	$('singleDownloadBtn').disabled = !enable;
	$('singleCopyBtn'    ).disabled = !enable;
	updateClearButtonState();
}

function updateClearButtonState() {
	const hasNodes = schemaGraph?.graph?.nodes?.length > 0;
	const isConnected = client?.isConnected;
	$('clearWorkflowBtn').disabled = !hasNodes || !isConnected;
}

// ========================================================================
// Connection Management
// ========================================================================

async function toggleConnection() {
	if (client?.isConnected) {
		await disconnect();
	} else {
		await connect();
	}
}

async function connect() {
	const serverUrl = $('serverUrl').value.trim();
	if (!serverUrl) {
		addLog('error', '⚠️ Please enter a server URL');
		return;
	}

	$('connectBtn').disabled = true;
	$('connectBtn').textContent = 'Connecting...';
	$('connectBtn').classList.remove('nw-btn-primary');
	$('connectBtn').classList.add('nw-btn-danger');
	setWsStatus('connecting');
	addLog('info', `⏳ Connecting to ${serverUrl}...`);

	try {
		client = new WorkflowClient(serverUrl);

		// Test connection
		await client.ping();
		addLog('success', '✅ Server reachable');

		// Fetch and register schema
		const schemaResponse = await client.getSchema();
		if (!schemaResponse.schema) {
			throw new Error('No schema received from server');
		}

		const registered = await visualizer.registerSchema(schemaResponse.schema);
		if (!registered) {
			throw new Error('Failed to register workflow schema');
		}
		addLog('success', '✅ Schema registered');

		// Set API base URLs for dynamic options, templates, generate, and browser media
		schemaGraph.api.comboBox.setBaseUrl(serverUrl);
		schemaGraph.api.templates.setBaseUrl(serverUrl);
		schemaGraph.api.generate.setBaseUrl(serverUrl);
		schemaGraph.api.browserMedia?.setBaseUrl(serverUrl);
		schemaGraph.api.docs?.setBaseUrl(serverUrl);

		// Populate options panels now that schema is available
		populateWorkflowOptionsPanel();
		populateExecOptionsPanel();

		// visualizer.schemaGraph.api.workflow.debug();

		// Initialize file upload manager
		fileUploadManager = new FileUploadManager(serverUrl, schemaGraph, syncWorkflow, schemaGraph.eventBus);
		addLog('info', '📁 File upload manager initialized');

		// Update overlay positions on camera changes
		schemaGraph.eventBus.on('camera:moved', () => {
			fileUploadManager?.updateOverlayPositions();
		});
		schemaGraph.eventBus.on('camera:zoomed', () => {
			fileUploadManager?.updateOverlayPositions();
		});

		// Initialize chat manager
		agentChatManager = new AgentChatManager(serverUrl, schemaGraph, syncWorkflow);
		addLog('info', '💬 Agent chat manager initialized');

		// Connect WebSocket
		client.connectWebSocket();
		setupClientEvents();

		// Initialize empty workflow so download always works
		visualizer.initEmptyWorkflow();

		// Refresh workflow list
		await refreshWorkflowList();

		$('connectBtn').textContent = 'Disconnect';
		$('workflowSelect').disabled = false;
		$('serverUrl').disabled = true;
		$('uploadWorkflowBtn').disabled = false;
		$('pasteWorkflowBtn').disabled = false;
		$('downloadWorkflowBtn').disabled = false;
		$('copyWorkflowBtn').disabled = false;
		$('singleImportBtn').disabled = false;
		$('singlePasteBtn').disabled = false;
		$('singleDownloadBtn').disabled = false;
		$('singleCopyBtn').disabled = false;
		enableStart(true);

		if (singleMode) {
			$('singleWorkflowName').textContent = visualizer.currentWorkflowName;
		}

		addLog('success', `✅ Connected to ${serverUrl}`);
	} catch (error) {
		console.error('Connection error:', error);
		addLog('error', `❌ Connection failed: ${error.message}`);
		setWsStatus('disconnected');
		client = null;
		$('connectBtn').textContent = 'Connect';
	} finally {
		$('connectBtn').disabled = false;
	}
}

async function disconnect() {
	if (schemaGraph?.api?.lock?.isLocked()) {
		schemaGraph.api.lock.unlock();
	}

	// Close all preview text overlays
	schemaGraph.closeAllPreviewTextOverlays?.();

	fileUploadManager?.destroy();
	fileUploadManager = null;

	agentChatManager?.disconnectAll();
	agentChatManager = null;

	if (client) {
		await client.removeWorkflow();
		client.disconnectWebSocket();
		client = null;
	}

	// Clear graph
	schemaGraph.api.graph.clear();
	schemaGraph.api.view.reset();
	
	visualizer.currentWorkflow = null;
	visualizer.currentWorkflowName = null;
	visualizer.graphNodes = [];

	currentExecutionId = null;
	
	$('connectBtn').textContent = 'Connect';
	$('connectBtn').classList.remove('nw-btn-danger');
	$('connectBtn').classList.add('nw-btn-primary');
	$('serverUrl').disabled = false;
	$('workflowSelect').disabled = true;
	$('workflowSelect').innerHTML = '<option value="">-- Select workflow --</option>';
	$('loadWorkflowBtn').disabled = true;
	$('uploadWorkflowBtn').disabled = true;
	$('pasteWorkflowBtn').disabled = true;
	$('downloadWorkflowBtn').disabled = true;
	$('copyWorkflowBtn').disabled = true;
	$('removeWorkflowBtn').disabled = true;

	enableStart(false);
	$('cancelBtn').disabled = true;
	$('singleWorkflowName').textContent = 'None';
	
	setWsStatus('disconnected');
	setExecStatus('idle', 'Not running');
	$('execId').textContent = '-';

	addLog('info', '🔌 Disconnected');
}

function setupClientEvents() {
	client.on('ws:connected', () => {
		setWsStatus('connected');
		addLog('success', '🔗 WebSocket connected');
	});

	client.on('ws:disconnected', () => {
		setWsStatus('disconnected');
		addLog('warning', '🔌 WebSocket disconnected');
	});

	client.on('workflow.started', (event) => {
		currentExecutionId = event.execution_id;
		setExecStatus('running', 'Running');
		$('execId').textContent = event.execution_id.substring(0, 8) + '...';
		enableStart(false);
		visualizer?.clearNodeStates();

		// LOCK GRAPH during execution
		schemaGraph.api.lock.lock('Workflow running');
		schemaGraph.eventBus.emit('workflow:started', event);

		addLog('info', `▶️ Workflow started`);
	});

	client.on('workflow.completed', (event) => {
		setExecStatus('completed', 'Completed');
		enableStart(true);

		// UNLOCK GRAPH after completion
		schemaGraph.api.lock.unlock();
		schemaGraph.eventBus.emit('workflow:completed', event);

		addLog('success', `✅ Workflow completed`);
	});

	client.on('workflow.failed', (event) => {
		setExecStatus('failed', 'Failed');
		enableStart(true);

		// UNLOCK GRAPH after failure
		schemaGraph.api.lock.unlock();
		schemaGraph.eventBus.emit('workflow:failed', event);

		addLog('error', `❌ Workflow failed: ${event.error || 'Unknown error'}`);
	});

	client.on('workflow.cancelled', (event) => {
		setExecStatus('idle', 'Cancelled');
		enableStart(true);

		// Close any pending user-input dialog
		closeModal();

		// UNLOCK GRAPH after cancellation
		schemaGraph.api.lock.unlock();
		schemaGraph.eventBus.emit('workflow:cancelled', event);

		addLog('warning', `⏹️ Workflow cancelled`);
	});

	client.on('node.started', (event) => {
		const idx = parseInt(event.node_id);
		const label = event.data?.node_label || `Node ${idx}`;
		visualizer?.updateNodeState(idx, 'running');
		addLog('info', `▶️ [${idx}] ${label}`);
	});

	client.on('node.completed', (event) => {
		const idx = parseInt(event.node_id);
		const label = event.data?.node_label || `Node ${idx}`;
		const outputs = event.data?.outputs;
		visualizer?.updateNodeState(idx, 'completed');
		if (outputs) {
			updateConnectedPreviews(idx, outputs);
		}
		addLog('success', `✅ [${idx}] ${label}`);
	});

	client.on('node.failed', (event) => {
		const idx = parseInt(event.node_id);
		const label = event.data?.node_label || `Node ${idx}`;
		visualizer?.updateNodeState(idx, 'failed');
		addLog('error', `❌ [${idx}] ${label}: ${event.error}`);
	});

	client.on('node.waiting', (event) => {
		const idx = parseInt(event.node_id);
		const label = event.data?.node_label || `Node ${idx}`;
		const waitType = event.data?.wait_type || 'unknown';
		visualizer?.updateNodeState(idx, 'waiting');
		addLog('info', `⏳ [${idx}] ${label} waiting (${waitType})`);
	});

	client.on('node.resumed', (event) => {
		const idx = parseInt(event.node_id);
		const label = event.data?.node_label || `Node ${idx}`;
		visualizer?.updateNodeState(idx, 'running');
		addLog('info', `▶️ [${idx}] ${label} resumed`);
	});

	client.on('user_input.requested', (event) => {
		addLog('warning', `👤 User input requested`);
		showUserInputModal(event);
	});

	// Forward file upload events to local eventBus
	client.on('upload.started', (event) => {
		schemaGraph.eventBus.emit('upload.started', event);
		const files = event.data?.filenames?.join(', ') || '';
		addLog('info', `⬆️ [${event.node_id}] Uploading: ${files}`);
	});

	client.on('upload.completed', (event) => {
		schemaGraph.eventBus.emit('upload.completed', event);
		addLog('info', `📦 [${event.node_id}] Upload complete`);
	});

	client.on('upload.failed', (event) => {
		schemaGraph.eventBus.emit('upload.failed', event);
		addLog('error', `❌ [${event.node_id}] Upload failed: ${event.error}`);
	});

	client.on('processing.started', (event) => {
		schemaGraph.eventBus.emit('processing.started', event);
		addLog('info', `⚙️ [${event.node_id}] Processing files...`);
	});

	client.on('processing.completed', (event) => {
		schemaGraph.eventBus.emit('processing.completed', event);
		addLog('success', `✅ [${event.node_id}] Processing complete`);
	});

	client.on('processing.failed', (event) => {
		schemaGraph.eventBus.emit('processing.failed', event);
		addLog('error', `❌ [${event.node_id}] Processing failed: ${event.error}`);
	});
}

// ========================================================================
// Workflow Management
// ========================================================================

async function refreshWorkflowList() {
	if (!client) return;

	try {
		const response = await client.listWorkflows();
		const names = response.names || [];

		const select = $('workflowSelect');
		select.innerHTML = '<option value="">-- Select workflow --</option>';

		names.forEach(name => {
			const option = document.createElement('option');
			option.value = name;
			option.textContent = name;
			select.appendChild(option);
		});

		const disabled = names.length === 0
		$('loadWorkflowBtn').disabled = disabled;
		$('removeWorkflowBtn').disabled = disabled;
		addLog('info', `📋 Found ${names.length} workflow(s)`);
	} catch (error) {
		addLog('error', `❌ Failed to list workflows: ${error.message}`);
	}
}

async function loadSelectedWorkflow() {
	const name = $('workflowSelect').value;
	if (!name || !client) return;

	try {
		addLog('info', `📂 Loading "${name}"...`);
		const response = await client.getWorkflow(name);

		if (!response.workflow) {
			throw new Error('Workflow not found');
		}

		const loaded = visualizer.loadWorkflow(response.workflow, name);
		if (!loaded) {
			throw new Error('Failed to load workflow into graph');
		}

		$('downloadWorkflowBtn').disabled = false;
		$('copyWorkflowBtn').disabled = false;
		enableStart(true);
		addLog('success', `✅ Loaded "${name}"`);

	} catch (error) {
		addLog('error', `❌ Failed to load workflow: ${error.message}`);
	}
}

async function handleFileUpload(event) {
	const file = event.target.files?.[0];
	if (!file) return;

	try {
		const text = await file.text();
		const workflow = JSON.parse(text);

		// If connected, upload to server
		if (client) {
			const response = await client.addWorkflow(workflow);
			if (response.status === 'added') {
				addLog('success', `📤 Uploaded "${response.name}"`);
				await refreshWorkflowList();
				$('workflowSelect').value = response.name;
				await loadSelectedWorkflow();
			} else {
				throw new Error('Upload failed');
			}
		} else {
			// Load locally
			const loaded = visualizer.loadWorkflow(workflow);
			if (loaded) {
				$('downloadWorkflowBtn').disabled = false;
				$('copyWorkflowBtn').disabled = false;
				addLog('success', `📂 Loaded workflow from file`);
			}
		}

		if (singleMode) {
			$('singleWorkflowName').textContent = visualizer.currentWorkflowName || 'Untitled';
			$('singleDownloadBtn').disabled = false;
		}
		updateClearButtonState();
	} catch (error) {
		addLog('error', `❌ Failed to upload: ${error.message}`);
	}

	event.target.value = '';
}

async function syncWorkflow(workflow = null, name = null, force = false) {
	if (!force && !workflowDirty) return;

	schemaGraph.api.lock.lock('Syncing workflow');

	try {
		// Save chat state before reload
		const chatState = saveChatState();

		// Close all preview text overlays (node IDs will change)
		schemaGraph.closeAllPreviewTextOverlays?.();

		const workflowEmpty = workflow == null;
		if (workflowEmpty) {
			workflow = visualizer.exportWorkflow();
		}
		
		if (!name) {
			name = workflow?.options?.name || visualizer.currentWorkflowName || 'custom_workflow';
		}

		await client.removeWorkflow();
		const response = await client.addWorkflow(workflow, name);
		
		if (response.status === 'added' || response.status === 'updated') {
			// Clear handlers (node IDs will change)
			agentChatManager?.disconnectAll();
			
			// Reload entire workflow from backend
			if (response.workflow) {
				const layout = workflowEmpty ? null : visualizer.defaultLayout;
				visualizer.loadWorkflow(response.workflow, response.name, layout, true);
			}
			
			// Restore chat messages
			restoreChatState(chatState);
			
			workflowDirty = false;
			schemaGraph.eventBus.emit('workflow:synced');
			addLog('success', `✅ Synced "${response.name}"`);
		} else {
			throw new Error('Sync failed');
		}
	} finally {
		schemaGraph.api.lock.unlock();
	}
}

function saveChatState() {
	const state = new Map();
	
	for (const node of schemaGraph.graph.nodes) {
		if (!node?.isChat) continue;
		
		// Use chatId as the stable key
		const key = node.chatId;
		if (!key) continue;
		
		state.set(key, {
			messages: [...(node.chatMessages || [])],
			inputValue: node._chatInputValue || ''
		});
	}
	
	return state;
}

function restoreChatState(state) {
	if (!state?.size) return;
	
	for (const node of schemaGraph.graph.nodes) {
		if (!node?.isChat) continue;
		
		// Use chatId as the stable key
		const key = node.chatId;
		const saved = state.get(key);
		if (!saved) continue;
		
		node.chatMessages = saved.messages;
		node._chatInputValue = saved.inputValue;
		
		// Update overlay - it will use the current node reference
		schemaGraph.chatManager?.overlayManager?.updateMessages(node);
		
		const overlay = schemaGraph.chatManager?.overlayManager?.overlays?.get(key);
		const input = overlay?.querySelector('.sg-chat-input');
		if (input && saved.inputValue) {
			input.value = saved.inputValue;
		}
	}
}

async function handleSingleImport(event) {
	const file = event.target.files?.[0];
	if (!file) return;

	try {
		schemaGraph.api.lock.lock('Importing content');

		const text = await file.text();
		const workflow = JSON.parse(text);

		// Clear current workflow
		schemaGraph.api.graph.clear();
		schemaGraph.api.view.reset();

		// Validate
		// const validated = visualizer.validateWorkflow(workflow);
		const name      = workflow?.options?.name || file.name.replace('.json', '');
		const validated = visualizer.loadWorkflow(workflow, name);
		if (validated) {
			await syncWorkflow(workflow, name, true);
			enableStart(true);
			addLog('success', `📂 Imported "${visualizer.currentWorkflowName}" (local)`);
		}
	} catch (error) {
		addLog('error', `❌ Failed to import: ${error.message}`);
	}

	schemaGraph.api.lock.unlock();

	event.target.value = '';
}

function downloadWorkflow() {
	const workflow = visualizer?.exportWorkflow();
	if (!workflow) {
		addLog('error', '⚠️ No workflow to download');
		return;
	}

	const json = JSON.stringify(workflow, null, '\t');
	const blob = new Blob([json], { type: 'application/json' });
	const url = URL.createObjectURL(blob);

	const a = document.createElement('a');
	a.href = url;
	a.download = `${visualizer.currentWorkflowName || 'workflow'}.json`;
	a.click();

	URL.revokeObjectURL(url);
	addLog('info', '💾 Workflow downloaded');
}

async function copyWorkflowToClipboard() {
	const workflow = visualizer?.exportWorkflow();
	if (!workflow) {
		addLog('error', '⚠️ No workflow to copy');
		return;
	}
	try {
		await navigator.clipboard.writeText(JSON.stringify(workflow, null, '\t'));
		addLog('info', '📋 Workflow copied to clipboard');
	} catch (err) {
		addLog('error', `❌ Failed to copy: ${err.message}`);
	}
}

async function pasteWorkflowFromClipboard() {
	let workflow;
	try {
		const text = await navigator.clipboard.readText();
		workflow = JSON.parse(text);
	} catch (err) {
		addLog('error', `❌ Failed to read clipboard: ${err.message}`);
		return;
	}

	try {
		if (client) {
			const response = await client.addWorkflow(workflow);
			if (response.status === 'added') {
				addLog('success', `📋 Uploaded "${response.name}" from clipboard`);
				await refreshWorkflowList();
				$('workflowSelect').value = response.name;
				await loadSelectedWorkflow();
			} else {
				throw new Error('Upload failed');
			}
		} else {
			const loaded = visualizer.loadWorkflow(workflow);
			if (loaded) {
				$('downloadWorkflowBtn').disabled = false;
				$('copyWorkflowBtn').disabled = false;
				addLog('success', '📋 Loaded workflow from clipboard');
			}
		}

		if (singleMode) {
			$('singleWorkflowName').textContent = visualizer.currentWorkflowName || 'Untitled';
			$('singleDownloadBtn').disabled = false;
			$('singleCopyBtn').disabled = false;
		}
		updateClearButtonState();
	} catch (err) {
		addLog('error', `❌ Failed to paste workflow: ${err.message}`);
	}
}

async function removeSelectedWorkflow() {
	const name = $('workflowSelect').value;
	if (!name || !client) return;

	pendingRemoveName = name;
	$('removeModalPrompt').textContent = `Are you sure you want to remove "${name}"?`;
	$('removeModal').style.display = 'flex';
}

function closeRemoveModal() {
	$('removeModal').style.display = 'none';
	pendingRemoveName = null;
}

async function confirmRemoveWorkflow() {
	if (!pendingRemoveName || !client) {
		closeRemoveModal();
		return;
	}

	const name = pendingRemoveName;
	closeRemoveModal();

	try {
		$('removeWorkflowBtn').disabled = true;
		addLog('info', `🗑️ Removing "${name}"...`);

		await client.removeWorkflow(name);

		// Clear graph if removed workflow was loaded
		if (visualizer.currentWorkflowName === name) {
			schemaGraph.api.graph.clear();
			schemaGraph.api.view.reset();
			visualizer.currentWorkflow = null;
			visualizer.currentWorkflowName = null;
			visualizer.graphNodes = [];
		}

		addLog('success', `✅ Removed "${name}"`);
		await refreshWorkflowList();

		$('downloadWorkflowBtn').disabled = true;
		$('copyWorkflowBtn').disabled = true;
		$('startBtn').disabled = true;
		visualizer.currentWorkflow = null;
		visualizer.currentWorkflowName = null;

	} catch (error) {
		addLog('error', `❌ Failed to remove: ${error.message}`);
	} finally {
		$('removeWorkflowBtn').disabled = false;
	}
}

async function clearWorkflow() {
	if (!visualizer.currentWorkflow) return;

	// Close all preview text overlays before clearing
	schemaGraph.closeAllPreviewTextOverlays?.();

	schemaGraph.api.graph.clear();
	schemaGraph.api.view.reset();
	await client.removeWorkflow();

	visualizer.initEmptyWorkflow();
	visualizer.graphNodes = [];

	$('startBtn').disabled = true;
	updateClearButtonState();

	if (singleMode) {
		$('singleWorkflowName').textContent = visualizer.currentWorkflowName;
	}
	
	addLog('info', '🧹 Graph cleared');
}

function toggleWorkflowMode() {
	singleMode = $('singleModeSwitch').checked;
	workflowDirty = true;
	
	$('multiWorkflowControls').style.display = singleMode ? 'none' : 'block';
	$('singleWorkflowControls').style.display = singleMode ? 'block' : 'none';
	
	if (client?.isConnected) {
		$('singleImportBtn').disabled = false;
		$('singlePasteBtn').disabled = false;
		$('singleDownloadBtn').disabled = !visualizer.currentWorkflow;
		$('singleCopyBtn').disabled = !visualizer.currentWorkflow;
	} else {
		$('singleImportBtn').disabled = true;
		$('singlePasteBtn').disabled = true;
		$('singleDownloadBtn').disabled = true;
		$('singleCopyBtn').disabled = true;
	}
	
	addLog('info', singleMode ? '📄 Single workflow mode' : '📚 Multi workflow mode');
}

// ========================================================================
// Execution Control
// ========================================================================

async function startExecution() {
	if (!client || !visualizer?.currentWorkflow) {
		addLog('error', '⚠️ No workflow loaded');
		return;
	}

	// Validate workflow before starting
	const validation = schemaGraph.api.workflow.validate();
	if (!validation.valid) {
		for (const error of validation.errors) {
			addLog('error', `⚠️ ${error}`);
		}
		return;
	}

	// Show warnings but don't block
	for (const warning of validation.warnings || []) {
		addLog('warning', `⚠️ ${warning}`);
	}

	try {
		enableStart(false);

		// In single mode, sync to backend if dirty
		if (singleMode) {
			await syncWorkflow();
		}

		const workflowName = visualizer.currentWorkflowName;
		addLog('info', `⏳ Starting "${workflowName}"...`);

		// Collect execution options from panel
		const initialData = collectExecOptions();
		const response = await client.startWorkflow(workflowName, initialData);

		if (response.status !== 'started') {
			throw new Error('Failed to start workflow');
		}

	} catch (error) {
		enableStart(true);
		addLog('error', `❌ Start failed: ${error.message}`);
	}
}

// ========================================================================
// Options Panel Population
// ========================================================================

function populateWorkflowOptionsPanel() {
	const form = $('workflowOptionsForm');
	if (!form) return;
	form.innerHTML = '';

	// Get workflow options schema info
	const optionsInfo = schemaGraph.api.schemaTypes.getWorkflowOptionsInfo(WORKFLOW_SCHEMA_NAME);

	if (!optionsInfo || !optionsInfo.fields) {
		form.innerHTML = '<p class="nw-options-empty">No workflow options available.</p>';
		return;
	}

	// Get current workflow options values
	const currentOptions = visualizer?.getWorkflowOptions() || {};

	for (const field of optionsInfo.fields) {
		const role = optionsInfo.fieldRoles[field.name];
		// Skip constant and annotation fields
		if (role === 'constant' || role === 'annotation') continue;

		// Use current value if set, otherwise use default
		const currentVal = currentOptions[field.name];
		const defaultVal = optionsInfo.defaults[field.name];
		const value = currentVal !== undefined ? currentVal : defaultVal;

		const fieldDiv = document.createElement('div');
		fieldDiv.className = 'nw-field';

		const label = document.createElement('label');
		label.textContent = field.title || field.name;
		label.setAttribute('for', `wfOpt_${field.name}`);
		fieldDiv.appendChild(label);

		const input = createInputForField(field, value);
		input.id = `wfOpt_${field.name}`;
		input.name = field.name;
		input.dataset.optionType = 'workflow';

		// Add change listener to update workflow options
		input.addEventListener('change', () => {
			const options = collectWorkflowOptions();
			visualizer?.setWorkflowOptions(options);
		});

		fieldDiv.appendChild(input);

		if (field.description) {
			const hint = document.createElement('small');
			hint.className = 'nw-field-hint';
			hint.textContent = field.description;
			fieldDiv.appendChild(hint);
		}

		form.appendChild(fieldDiv);
	}

	if (form.children.length === 0) {
		form.innerHTML = '<p class="nw-options-empty">No workflow options available.</p>';
	}
}

function populateExecOptionsPanel() {
	const form = $('execOptionsForm');
	if (!form) return;
	form.innerHTML = '';

	// Get execution options schema info
	const execOptionsInfo = schemaGraph.api.schemaTypes.getWorkflowExecutionOptionsInfo(WORKFLOW_SCHEMA_NAME);

	if (!execOptionsInfo || !execOptionsInfo.fields) {
		form.innerHTML = '<p class="nw-options-empty">No execution options available.</p>';
		return;
	}

	for (const field of execOptionsInfo.fields) {
		const role = execOptionsInfo.fieldRoles[field.name];
		// Skip constant and annotation fields
		if (role === 'constant' || role === 'annotation') continue;

		const defaultVal = execOptionsInfo.defaults[field.name];
		const fieldDiv = document.createElement('div');
		fieldDiv.className = 'nw-field';

		const label = document.createElement('label');
		label.textContent = field.title || field.name;
		label.setAttribute('for', `execOpt_${field.name}`);
		fieldDiv.appendChild(label);

		const input = createInputForField(field, defaultVal);
		input.id = `execOpt_${field.name}`;
		input.name = field.name;
		fieldDiv.appendChild(input);

		if (field.description) {
			const hint = document.createElement('small');
			hint.className = 'nw-field-hint';
			hint.textContent = field.description;
			fieldDiv.appendChild(hint);
		}

		form.appendChild(fieldDiv);
	}

	if (form.children.length === 0) {
		form.innerHTML = '<p class="nw-options-empty">No execution options available.</p>';
	}
}

function createInputForField(field, defaultVal) {
	const rawType = field.rawType || '';
	let baseType = rawType.trim();
	if (baseType.startsWith('Optional[') && baseType.endsWith(']')) baseType = baseType.slice(9, -1).trim();

	let input;

	if (baseType === 'bool' || baseType === 'boolean') {
		input = document.createElement('select');
		input.className = 'nw-select';
		const optTrue = document.createElement('option');
		optTrue.value = 'true';
		optTrue.textContent = 'True';
		const optFalse = document.createElement('option');
		optFalse.value = 'false';
		optFalse.textContent = 'False';
		input.appendChild(optFalse);
		input.appendChild(optTrue);
		input.value = defaultVal === true ? 'true' : 'false';
	} else if (baseType === 'int' || baseType === 'integer') {
		input = document.createElement('input');
		input.type = 'number';
		input.step = '1';
		input.className = 'nw-input';
		input.value = defaultVal !== null && defaultVal !== undefined ? defaultVal : '';
	} else if (baseType === 'float' || baseType === 'number') {
		input = document.createElement('input');
		input.type = 'number';
		input.step = '0.01';
		input.className = 'nw-input';
		input.value = defaultVal !== null && defaultVal !== undefined ? defaultVal : '';
	} else {
		input = document.createElement('input');
		input.type = 'text';
		input.className = 'nw-input';
		input.value = defaultVal !== null && defaultVal !== undefined ? defaultVal : '';
	}

	return input;
}

function collectWorkflowOptions() {
	const form = $('workflowOptionsForm');
	if (!form) return {};

	const options = {};
	const inputs = form.querySelectorAll('input, select');

	for (const input of inputs) {
		const name = input.name;
		if (!name) continue;

		let value = input.value;

		// Convert types based on input type
		if (input.type === 'number') {
			value = input.step === '1' ? parseInt(value) : parseFloat(value);
			if (isNaN(value)) value = null;
		} else if (input.tagName === 'SELECT' && (value === 'true' || value === 'false')) {
			value = value === 'true';
		}

		if (value !== null && value !== undefined && value !== '') {
			options[name] = value;
		}
	}

	return options;
}

function collectExecOptions() {
	const form = $('execOptionsForm');
	if (!form) return { type: 'workflow_execution_options' };

	const options = { type: 'workflow_execution_options' };
	const inputs = form.querySelectorAll('input, select');

	for (const input of inputs) {
		const name = input.name;
		if (!name) continue;

		let value = input.value;

		// Convert types based on input type
		if (input.type === 'number') {
			value = input.step === '1' ? parseInt(value) : parseFloat(value);
			if (isNaN(value)) value = null;
		} else if (input.tagName === 'SELECT' && (value === 'true' || value === 'false')) {
			value = value === 'true';
		}

		if (value !== null && value !== undefined && value !== '') {
			options[name] = value;
		}
	}

	return options;
}

async function cancelExecution() {
	if (!client || !currentExecutionId) return;

	try {
		$('cancelBtn').disabled = true;
		await client.cancelExecution(currentExecutionId);
	} catch (error) {
		addLog('error', `❌ Cancel failed: ${error.message}`);
		$('cancelBtn').disabled = false;
	}
}

// ========================================================================
// TOOL CALL EXECUTION
// ========================================================================

/**
 * Get the connected ToolConfig node from a ToolCall node
 * @param {Object} toolCallNode - The ToolCall node
 * @returns {Object|null} The connected ToolConfig node data or null
 */
function getConnectedToolConfig(toolCallNode) {
	if (!toolCallNode || !schemaGraph) return null;

	const configSlotIdx = toolCallNode.getInputSlotByName?.('config');
	if (configSlotIdx < 0) return null;

	const input = toolCallNode.inputs?.[configSlotIdx];
	if (!input?.link) return null;

	const link = schemaGraph.graph.links[input.link];
	if (!link) return null;

	const configNode = schemaGraph.graph.getNodeById(link.origin_id);
	if (!configNode) return null;

	// Return config node data including workflow index
	return {
		node: configNode,
		workflowIndex: configNode.workflowIndex
	};
}

/**
 * Execute a tool call via the ToolCall node
 * @param {Object} toolCallNode - The ToolCall node to execute
 */
async function executeToolCall(toolCallNode) {
	if (!client || !visualizer?.currentWorkflowName) {
		addLog('error', '❌ Not connected or no workflow loaded');
		return;
	}

	const toolConfig = getConnectedToolConfig(toolCallNode);
	if (!toolConfig) {
		addLog('error', '❌ ToolCall node must be connected to a ToolConfig');
		schemaGraph.showError('ToolCall must be connected to a ToolConfig node');
		return;
	}

	// Get args from the ToolCall node's native input
	let args = {};
	const argsSlotIdx = toolCallNode.getInputSlotByName?.('args');
	if (argsSlotIdx >= 0 && toolCallNode.nativeInputs?.[argsSlotIdx]) {
		const argsValue = toolCallNode.nativeInputs[argsSlotIdx].value;
		if (argsValue) {
			try {
				args = typeof argsValue === 'string' ? JSON.parse(argsValue) : argsValue;
			} catch (e) {
				addLog('warning', '⚠️ Could not parse args as JSON, using empty args');
			}
		}
	}

	try {
		// Sync workflow first to ensure server has latest state
		await syncWorkflow();

		addLog('info', `🔧 Executing tool at node ${toolConfig.workflowIndex}...`);

		const serverUrl = client.baseUrl;
		// const response = await fetch(`${serverUrl}/tool_call/${visualizer.currentWorkflowName}`, {
		const response = await fetch(`${serverUrl}/tool_call`, {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({
				node_index: toolConfig.workflowIndex,
				args: args
			})
		});

		const result = await response.json();

		if (!response.ok) {
			throw new Error(result.detail || 'Tool call failed');
		}

		addLog('success', `✅ Tool "${result.tool_name}" executed successfully`);

		// Update the result output on the ToolCall node
		const resultContent = result.result?.content;
		if (resultContent !== undefined) {
			// Store result in node for display
			toolCallNode.extra = toolCallNode.extra || {};
			toolCallNode.extra.toolResult = resultContent;

			// Update any connected preview nodes
			if (toolCallNode.workflowIndex !== undefined) {
				updateConnectedPreviews(toolCallNode.workflowIndex, { result: resultContent });
			}
		}

		// Show result in a dialog
		const resultStr = typeof resultContent === 'object'
			? JSON.stringify(resultContent, null, 2)
			: String(resultContent ?? 'No result');

		schemaGraph.showNotification?.(`Tool Result:\n${resultStr.substring(0, 500)}${resultStr.length > 500 ? '...' : ''}`, 'success', 5000);

		schemaGraph.draw();

	} catch (error) {
		console.error('Tool call error:', error);
		addLog('error', `❌ Tool call failed: ${error.message}`);
		schemaGraph.showError?.(`Tool call failed: ${error.message}`);
	}
}

// ========================================================================
// PREVIEW LIVE UPDATE - Add to numel-workflow-ui.js
// Integrates workflow execution events with preview node updates
// ========================================================================

// ========================================================================
// Preview Update Functions
// ========================================================================

/**
 * Find and update all preview nodes connected to a workflow node's outputs
 * @param {number} workflowNodeIdx - Index of the completed workflow node
 * @param {Object} outputs - Output data from the node
 */
function updateConnectedPreviews(workflowNodeIdx, outputs) {
	if (!visualizer || !schemaGraph) return;

	const graphNode = visualizer.graphNodes[workflowNodeIdx];
	if (!graphNode) return;

	const graph = schemaGraph.graph;
	const previewManager = schemaGraph.edgePreviewManager;
	let needsRedraw = false;

	// Check each output slot
	for (let slotIdx = 0; slotIdx < (graphNode.outputs || []).length; slotIdx++) {
		const output = graphNode.outputs[slotIdx];
		for (const linkId of output.links || []) {
			const link = graph.links[linkId];
			if (!link) continue;

			const targetNode = graph.getNodeById(link.target_id);
			if (!isPreviewNode(targetNode)) continue;

			// Determine which output data to use
			// Try outputMeta name (original field name) first, then display name
			const metaName = graphNode.outputMeta?.[slotIdx]?.name;
			const slotName = output.name;
			let data;

			if (outputs && typeof outputs === 'object') {
				if (metaName && metaName in outputs) {
					data = outputs[metaName];
				} else if (slotName in outputs) {
					data = outputs[slotName];
				}
				// Try base name for dotted slots
				else {
					const baseName = (metaName || slotName).split('.')[0];
					data = (baseName in outputs) ? outputs[baseName] : outputs;
				}
			} else {
				data = outputs;
			}
			
			// Update preview node with flash
			updatePreviewNode(targetNode, data, previewManager);
			needsRedraw = true;
			
			// Recursively update downstream preview nodes
			propagateToDownstreamPreviews(targetNode, data, previewManager);
		}
	}
	
	if (needsRedraw) {
		schemaGraph.draw();
	}
}

/**
 * Update a single preview node with new data and trigger flash animation
 * @param {Node} previewNode - The preview node to update
 * @param {any} data - New data to display (or object with {data, type})
 * @param {EdgePreviewManager} previewManager - Preview manager instance
 */
function updatePreviewNode(previewNode, data, previewManager) {
	// Handle both raw data and {data, type} objects
	let actualData = data;
	let dataType = null;
	if (data && typeof data === 'object' && 'data' in data && 'type' in data) {
		actualData = data.data;
		dataType = data.type;
	}

	// Store previous data for comparison
	const dataChanged = FORCE_PREVIEW_ON_SAME_DATA || !deepEqual(previewNode.previewData, actualData);

	// Update node data
	previewNode.previewData = actualData;
	// Use provided type, schemaGraph's method, or node's method as fallback
	if (dataType) {
		previewNode.previewType = dataType;
	} else if (schemaGraph?._guessTypeFromData) {
		previewNode.previewType = schemaGraph._guessTypeFromData(actualData);
	} else if (typeof previewNode._detectType === 'function') {
		previewNode.previewType = previewNode._detectType(actualData);
	}
	previewNode.previewError = null;
	previewNode._lastUpdateTime = Date.now();

	// Trigger flash animation if data changed
	if (dataChanged) {
		triggerPreviewFlash(previewNode);
	}

	// Update overlay if this preview is currently expanded
	if (previewManager?.previewOverlay?.activeNode === previewNode) {
		previewManager.previewOverlay.update();

		// Flash the overlay too
		if (dataChanged) {
			triggerOverlayFlash(previewManager.previewOverlay);
		}
	}

	// Update scrollable text overlay if it exists
	if (schemaGraph?._updatePreviewTextOverlayContent) {
		schemaGraph._updatePreviewTextOverlayContent(previewNode);
	}
}

/**
 * Check if a node is a preview node
 * @param {Object} node - The node to check
 * @returns {boolean} True if this is a preview node
 */
function isPreviewNode(node) {
	if (!node) return false;
	// Use the schemaGraph's method if available, otherwise check type
	if (schemaGraph?._isPreviewFlowNode) {
		return schemaGraph._isPreviewFlowNode(node);
	}
	// Fallback check
	return node.type?.includes('PreviewFlow') ||
	       node.modelName === 'PreviewFlow' ||
	       (node.title?.toLowerCase().includes('preview') && node.isWorkflowNode);
}

/**
 * Propagate data through chained preview nodes (downstream)
 * @param {Node} previewNode - Source preview node
 * @param {any} data - Data to propagate
 * @param {EdgePreviewManager} previewManager - Preview manager instance
 */
function propagateToDownstreamPreviews(previewNode, data, previewManager) {
	const graph = schemaGraph.graph;

	for (const output of previewNode.outputs || []) {
		for (const linkId of output.links || []) {
			const link = graph.links[linkId];
			if (!link) continue;

			const targetNode = graph.getNodeById(link.target_id);
			if (!isPreviewNode(targetNode)) continue;

			updatePreviewNode(targetNode, data, previewManager);
			propagateToDownstreamPreviews(targetNode, data, previewManager);
		}
	}
}

/**
 * Trace upward from a preview node to find source data
 * Finds the upstream preview node that has actual data and extracts it
 * Also stores previewData on intermediate preview nodes for rendering
 * @param {Node} previewNode - The preview node to trace from
 * @param {Set} visited - Set of visited node IDs to prevent infinite loops
 * @returns {Object|null} Object with {data, type} or null if not found
 */
function traceUpwardForPreviewData(previewNode, visited = new Set()) {
	if (!previewNode || !schemaGraph || visited.has(previewNode.id)) return null;
	visited.add(previewNode.id);

	const graph = schemaGraph.graph;

	// Check input slots for incoming links
	for (const input of previewNode.inputs || []) {
		if (!input.link) continue;

		const link = graph.links[input.link];
		if (!link) continue;

		const sourceNode = graph.getNodeById(link.origin_id);
		if (!sourceNode) continue;

		// If source is a preview node, get its preview data using _getPreviewData
		if (isPreviewNode(sourceNode)) {
			// Call _getPreviewData on the SOURCE preview node (which already shows data)
			if (schemaGraph._getPreviewData) {
				const previewResult = schemaGraph._getPreviewData(sourceNode);
				// Check various data properties the result might have
				const data = previewResult?.data ?? previewResult?.value;
				if (data !== undefined && data !== null && previewResult?.type !== 'node') {
					// IMPORTANT: Store previewData on the source node so _extractPreviewDataFromNode finds it
					if (sourceNode.previewData === undefined || sourceNode.previewData === null) {
						sourceNode.previewData = data;
						sourceNode.previewType = previewResult.type;
					}
					// Return object with data and type
					return { data, type: previewResult.type };
				}
			}
			// Also check stored previewData
			if (sourceNode.previewData !== undefined && sourceNode.previewData !== null) {
				return { data: sourceNode.previewData, type: sourceNode.previewType };
			}
			// Recursively trace further upstream
			const upstreamResult = traceUpwardForPreviewData(sourceNode, visited);
			if (upstreamResult !== null) {
				// Store on this intermediate node too
				if (sourceNode.previewData === undefined || sourceNode.previewData === null) {
					sourceNode.previewData = upstreamResult.data;
					sourceNode.previewType = upstreamResult.type;
				}
				return upstreamResult;
			}
		}
		// Non-preview node - use _extractPreviewDataFromNode if available
		else {
			if (schemaGraph._extractPreviewDataFromNode) {
				const result = schemaGraph._extractPreviewDataFromNode(sourceNode, link.origin_slot);
				const data = result?.data ?? result?.value;
				if (data !== undefined && data !== null) {
					return { data, type: result?.type };
				}
			}
		}
	}

	return null;
}

/**
 * Handle link creation - update preview nodes by tracing upward for data
 * @param {Object} data - Event data containing linkId and optionally link object
 */
function handleLinkCreatedForPreview(data) {
	if (!schemaGraph?.graph) return;

	// Get link from data (could be passed directly or via linkId)
	let link = data.link || schemaGraph.graph.links[data.linkId];
	if (!link) {
		console.warn('handleLinkCreatedForPreview: link not found', data);
		return;
	}

	// Get target node - could be target_id or targetNodeId depending on source
	const targetId = link.target_id ?? data.targetNodeId;
	const targetNode = schemaGraph.graph.getNodeById(targetId);

	if (!isPreviewNode(targetNode)) {
		return;
	}

	// Trace upward to find source data (returns {data, type} or null)
	const result = traceUpwardForPreviewData(targetNode);

	if (result !== null) {
		const previewManager = schemaGraph.edgePreviewManager;
		// Pass the result object which contains {data, type}
		updatePreviewNode(targetNode, result, previewManager);
		// Also propagate to any downstream preview nodes
		propagateToDownstreamPreviews(targetNode, result, previewManager);
		schemaGraph.draw();
	}
}

/**
 * Refresh all preview nodes in the graph by re-tracing their data sources
 */
function refreshAllPreviewNodes() {
	if (!schemaGraph?.graph) return;

	const previewManager = schemaGraph.edgePreviewManager;
	let refreshed = 0;

	for (const node of schemaGraph.graph.nodes) {
		if (!isPreviewNode(node)) continue;

		// Check if node has an input connection
		const hasInputConnection = node.inputs?.some(input => input.link != null);
		if (!hasInputConnection) continue;

		// Re-trace upward to find source data
		const result = traceUpwardForPreviewData(node, new Set());
		if (result !== null) {
			updatePreviewNode(node, result, previewManager);
			refreshed++;
		}
	}

	if (refreshed > 0) {
		if (schemaGraph._refreshAllCompleteness) {
			schemaGraph._refreshAllCompleteness();
		}
		schemaGraph.draw();
	}
}

/**
 * Handle link removal - refresh preview data for affected preview nodes
 * @param {Object} data - Event data containing link info
 */
function handleLinkRemovedForPreview(data) {
	if (!schemaGraph?.graph) return;

	// Get the target node that lost its connection
	const targetId = data.targetNodeId ?? data.target_id;
	if (!targetId) return;

	const targetNode = schemaGraph.graph.getNodeById(targetId);

	// Skip if node doesn't exist (was deleted) or isn't a preview node
	if (!targetNode || !isPreviewNode(targetNode)) return;

	// Check if this node still has an input connection BEFORE clearing data
	// This handles the case where preservePreviewLinks creates a new connection before removing the old one
	const hasInputConnection = targetNode.inputs?.some(input => input.link != null);

	// Only clear data if the node has no more input connections
	if (!hasInputConnection) {
		targetNode.previewData = null;
		targetNode.previewType = null;
	}

	// Always refresh to ensure visual state is correct
	setTimeout(() => {
		// Recheck input connection status
		const stillHasInput = targetNode.inputs?.some(input => input.link != null);

		if (stillHasInput) {
			// Re-trace upward to find source data
			const result = traceUpwardForPreviewData(targetNode, new Set());
			if (result !== null) {
				const previewManager = schemaGraph.edgePreviewManager;
				updatePreviewNode(targetNode, result, previewManager);
				propagateToDownstreamPreviews(targetNode, result, previewManager);
			}
		}

		// Force a complete visual refresh
		if (schemaGraph._refreshAllCompleteness) {
			schemaGraph._refreshAllCompleteness();
		}
		schemaGraph.draw();
	}, 50);
}

/**
 * Trigger flash animation on a preview node (canvas-based)
 * @param {Node} node - Preview node to flash
 */
function triggerPreviewFlash(node) {
	// Check if preview flash feature is enabled
	if (!schemaGraph._features?.previewFlash) return;

	node._flashStart = performance.now();
	node._flashDuration = 600; // ms
	node._isFlashing = true;
	node._flashProgress = 0;

	// Start animation loop if not already running
	if (!schemaGraph._previewFlashAnimating) {
		schemaGraph._previewFlashAnimating = true;
		animatePreviewFlash();
	}
}

/**
 * Animation loop for preview node flashes
 */
function animatePreviewFlash() {
	const now = performance.now();
	let anyFlashing = false;
	
	for (const node of schemaGraph.graph.nodes) {
		if (!node._isFlashing) continue;
		
		const elapsed = now - node._flashStart;
		if (elapsed < node._flashDuration) {
			node._flashProgress = elapsed / node._flashDuration;
			anyFlashing = true;
		} else {
			node._isFlashing = false;
			node._flashProgress = 0;
		}
	}
	
	schemaGraph.draw();
	
	if (anyFlashing) {
		requestAnimationFrame(animatePreviewFlash);
	} else {
		schemaGraph._previewFlashAnimating = false;
	}
}

/**
 * Trigger flash animation on the preview overlay
 * @param {PreviewOverlay} overlay - Overlay to flash
 */
function triggerOverlayFlash(overlay) {
	const element = overlay.overlayElement;
	if (!element) return;
	
	element.classList.remove('flash');
	// Force reflow to restart animation
	void element.offsetWidth;
	element.classList.add('flash');
	
	// Remove class after animation completes
	setTimeout(() => {
		element.classList.remove('flash');
	}, 500);
}

/**
 * Deep equality check for data comparison
 * @param {any} a - First value
 * @param {any} b - Second value
 * @returns {boolean} True if equal
 */
function deepEqual(a, b) {
	if (a === b) return true;
	if (a == null || b == null) return false;
	if (typeof a !== typeof b) return false;
	
	if (typeof a === 'object') {
		if (Array.isArray(a) !== Array.isArray(b)) return false;
		
		const keysA = Object.keys(a);
		const keysB = Object.keys(b);
		
		if (keysA.length !== keysB.length) return false;
		
		for (const key of keysA) {
			if (!keysB.includes(key)) return false;
			if (!deepEqual(a[key], b[key])) return false;
		}
		
		return true;
	}
	
	return false;
}

// ========================================================================
// User Input Modal
// ========================================================================

let pendingInputEvent = null;

function showUserInputModal(event) {
	pendingInputEvent = event;
	$('userInputPrompt').textContent = event.data?.prompt || 'Please provide input:';
	$('userInputField').value = '';
	$('userInputModal').style.display = 'flex';
	$('userInputField').focus();
}

function closeModal() {
	$('userInputModal').style.display = 'none';
	pendingInputEvent = null;
}

async function cancelUserInput() {
	if (!pendingInputEvent) { closeModal(); return; }
	const savedEvent = pendingInputEvent;
	closeModal();
	if (client) {
		try {
			await client.cancelExecution(savedEvent.execution_id);
		} catch (err) {
			addLog('error', `❌ Failed to cancel execution: ${err.message}`);
		}
	}
}

async function submitUserInput() {
	if (!pendingInputEvent || !client) return;

	const input = $('userInputField').value.trim();
	if (!input) {
		alert('Please enter a value');
		return;
	}

	// Save event reference and close the modal BEFORE the POST.
	// The server resolves the input future and may immediately emit
	// USER_INPUT_REQUESTED for the next node — if closeModal() ran
	// after the POST, it would hide that new dialog.
	const savedEvent = pendingInputEvent;
	closeModal();

	try {
		await client.provideUserInput(
			savedEvent.execution_id,
			savedEvent.node_id,
			input
		);
	} catch (error) {
		addLog('error', `❌ Failed to submit input: ${error.message}`);
	}
}

// ========================================================================
// UI Helpers
// ========================================================================

function setWsStatus(status) {
	const badge = $('wsStatus');
	badge.className = `nw-ws-badge ${status}`;
}

function setExecStatus(type, text) {
	const status = $('execStatus');
	status.className = `nw-status ${type}`;
	status.textContent = text;
}

function addLog(type, message) {
	const log = $('eventLog');
	const item = document.createElement('div');
	item.className = `nw-event-item ${type}`;

	const time = new Date().toLocaleTimeString('en-US', { hour12: false });

	item.innerHTML = `
		<span class="nw-event-time">${time}</span>
		<span class="nw-event-msg">${message}</span>
	`;

	log.appendChild(item);
	log.scrollTop = log.scrollHeight;

	// Limit log size
	while (log.children.length > 100) {
		log.removeChild(log.firstChild);
	}
}

$('uploadWorkflowBtn').disabled = true;
	$('pasteWorkflowBtn').disabled = true;
