/* ========================================================================
   NUMEL WORKFLOW UI - User Interface Logic
   ======================================================================== */

// Global State
let client = null;
let visualizer = null;
let schemaGraph = null;
let currentExecutionId = null;
let pendingRemoveName = null;
let singleMode = false;

// DOM Elements
const $ = id => document.getElementById(id);

// ========================================================================
// Initialization
// ========================================================================

document.addEventListener('DOMContentLoaded', () => {
	// Initialize SchemaGraph
	schemaGraph = new SchemaGraphApp('sg-main-canvas');

	// Register workflow extension
	// registerWorkflowExtension(schemaGraph);

	// Register callback for context menu node creation
	schemaGraph.onAddWorkflowNode = (nodeType, wx, wy) => {
		if (visualizer) {
			visualizer.addNodeAtPosition(nodeType, wx, wy);
		}
	};

	// Create visualizer
	visualizer = new WorkflowVisualizer(schemaGraph);

	// Setup event listeners
	setupEventListeners();

	// Initial log
	addLog('info', '🚀 Numel Workflow ready');
});

function setupEventListeners() {
	// Connection
	$('connectBtn').addEventListener('click', toggleConnection);

	// Workflow management
	$('refreshListBtn').addEventListener('click', refreshWorkflowList);
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
	$('singleUploadBtn').addEventListener('click', () => $('workflowFileInput').click());
	$('singleDownloadBtn').addEventListener('click', downloadWorkflow);

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
	$('cancelInputBtn').addEventListener('click', closeModal);
	$('closeModalBtn').addEventListener('click', closeModal);
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

		// visualizer.schemaGraph.api.workflow.debug();

		// Connect WebSocket
		client.connectWebSocket();
		setupClientEvents();

		// Refresh workflow list
		await refreshWorkflowList();

		$('connectBtn').textContent = 'Disconnect';
		$('workflowSelect').disabled = false;
		$('serverUrl').disabled = true;
		$('uploadWorkflowBtn').disabled = false;
		$('singleUploadBtn').disabled = false;
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
	if (client) {
		client.disconnectWebSocket();
		client = null;
	}

	currentExecutionId = null;
	$('connectBtn').textContent = 'Connect';
	$('workflowSelect').disabled = true;
	$('workflowSelect').innerHTML = '<option value="">-- Select workflow --</option>';
	$('loadWorkflowBtn').disabled = true;
	$('downloadWorkflowBtn').disabled = true;
	$('removeWorkflowBtn').disabled = true;
	$('serverUrl').disabled = false;
	$('uploadWorkflowBtn').disabled = true;
	$('startBtn').disabled = true;
	$('cancelBtn').disabled = true;
	$('singleUploadBtn').disabled = true;
	$('singleDownloadBtn').disabled = true;
	$('clearWorkflowBtn').disabled = true;
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
		$('startBtn').disabled = true;
		$('cancelBtn').disabled = false;
		visualizer?.clearNodeStates();
		addLog('info', `▶️ Workflow started`);
	});

	client.on('workflow.completed', (event) => {
		setExecStatus('completed', 'Completed');
		$('startBtn').disabled = false;
		$('cancelBtn').disabled = true;
		addLog('success', `✅ Workflow completed`);
	});

	client.on('workflow.failed', (event) => {
		setExecStatus('failed', 'Failed');
		$('startBtn').disabled = false;
		$('cancelBtn').disabled = true;
		addLog('error', `❌ Workflow failed: ${event.error || 'Unknown error'}`);
	});

	client.on('workflow.cancelled', (event) => {
		setExecStatus('idle', 'Cancelled');
		$('startBtn').disabled = false;
		$('cancelBtn').disabled = true;
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
		visualizer?.updateNodeState(idx, 'completed');
		addLog('success', `✅ [${idx}] ${label}`);
	});

	client.on('node.failed', (event) => {
		const idx = parseInt(event.node_id);
		const label = event.data?.node_label || `Node ${idx}`;
		visualizer?.updateNodeState(idx, 'failed');
		addLog('error', `❌ [${idx}] ${label}: ${event.error}`);
	});

	client.on('user_input.requested', (event) => {
		addLog('warning', `👤 User input requested`);
		showUserInputModal(event);
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
		$('startBtn').disabled = false;
		$('clearWorkflowBtn').disabled = false;
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
				addLog('success', `📂 Loaded workflow from file`);
			}
		}

		if (singleMode) {
			$('singleWorkflowName').textContent = visualizer.currentWorkflowName || 'Untitled';
			$('singleDownloadBtn').disabled = false;
		}
		$('clearWorkflowBtn').disabled = false;
	} catch (error) {
		addLog('error', `❌ Failed to upload: ${error.message}`);
	}

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
		$('startBtn').disabled = true;
		visualizer.currentWorkflow = null;
		visualizer.currentWorkflowName = null;

	} catch (error) {
		addLog('error', `❌ Failed to remove: ${error.message}`);
	} finally {
		$('removeWorkflowBtn').disabled = false;
	}
}

function clearWorkflow() {
	if (!visualizer.currentWorkflow) return;

	schemaGraph.api.graph.clear();
	schemaGraph.api.view.reset();
	
	visualizer.currentWorkflow = null;
	visualizer.currentWorkflowName = null;
	visualizer.graphNodes = [];
	
	$('downloadWorkflowBtn').disabled = true;
	$('singleDownloadBtn').disabled = true;
	$('startBtn').disabled = true;
	$('clearWorkflowBtn').disabled = true;
	
	if (singleMode) {
		$('singleWorkflowName').textContent = 'None';
	}
	
	addLog('info', '🧹 Graph cleared');
}

function toggleWorkflowMode() {
	singleMode = $('singleModeSwitch').checked;
	
	$('multiWorkflowControls').style.display = singleMode ? 'none' : 'block';
	$('singleWorkflowControls').style.display = singleMode ? 'block' : 'none';
	
	// Update button states based on connection
	if (client?.isConnected) {
		$('singleUploadBtn').disabled = false;
		$('singleDownloadBtn').disabled = !visualizer.currentWorkflow;
	} else {
		$('singleUploadBtn').disabled = true;
		$('singleDownloadBtn').disabled = true;
	}
	
	addLog('info', singleMode ? '📄 Single workflow mode' : '📚 Multi workflow mode');
}

// ========================================================================
// Execution Control
// ========================================================================

async function startExecution() {
	if (!client || !visualizer?.currentWorkflowName) {
		addLog('error', '⚠️ No workflow loaded');
		return;
	}

	try {
		$('startBtn').disabled = true;
		addLog('info', `⏳ Starting "${visualizer.currentWorkflowName}"...`);

		const response = await client.startWorkflow(visualizer.currentWorkflowName, {});

		if (response.status !== 'started') {
			throw new Error('Failed to start workflow');
		}

	} catch (error) {
		addLog('error', `❌ Start failed: ${error.message}`);
		$('startBtn').disabled = false;
	}
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

async function submitUserInput() {
	if (!pendingInputEvent || !client) return;

	const input = $('userInputField').value.trim();
	if (!input) {
		alert('Please enter a value');
		return;
	}

	try {
		await client.provideUserInput(
			pendingInputEvent.execution_id,
			pendingInputEvent.node_id,
			input
		);
		closeModal();
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
