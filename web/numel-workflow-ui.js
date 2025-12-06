/* ========================================================================
NUMEL WORKFLOW UI - Clean Integration
======================================================================== */

// Global state
let workflowClient = null;
let workflowVisualizer = null;
let currentWorkflow = null;
let currentExecutionId = null;
let workflowLibrary = new Map();

// DOM elements
let chatModeBtn, workflowModeBtn;
let chatMode, workflowMode;
let workflowSelect;
let startWorkflowBtn, stopWorkflowBtn;
let workflowStatus, eventLog;
let userInputModal, userInputPrompt, userInputField;

// ========================================================================
// INITIALIZATION
// ========================================================================

function initWorkflowUI() {
	// Get DOM elements
	chatModeBtn = document.getElementById('chatModeBtn');
	workflowModeBtn = document.getElementById('workflowModeBtn');
	chatMode = document.getElementById('chatMode');
	workflowMode = document.getElementById('workflowMode');
	
	workflowSelect = document.getElementById('workflowSelect');
	startWorkflowBtn = document.getElementById('startWorkflowBtn');
	stopWorkflowBtn = document.getElementById('stopWorkflowBtn');
	
	workflowStatus = document.getElementById('workflowStatus');
	eventLog = document.getElementById('eventLog');
	
	userInputModal = document.getElementById('userInputModal');
	userInputPrompt = document.getElementById('userInputPrompt');
	userInputField = document.getElementById('userInputField');
	
	// Setup listeners
	setupWorkflowEventListeners();
	
	// Load sample workflows
	loadSampleWorkflows();
}

function setupWorkflowEventListeners() {
	// Mode switching
	chatModeBtn.addEventListener('click', () => switchMode('chat'));
	workflowModeBtn.addEventListener('click', () => switchMode('workflow'));
	
	// Workflow controls
	workflowSelect.addEventListener('change', onWorkflowSelected);
	startWorkflowBtn.addEventListener('click', startWorkflow);
	stopWorkflowBtn.addEventListener('click', stopWorkflow);
	
	// User input modal
	document.getElementById('submitInputBtn').addEventListener('click', submitUserInput);
	document.getElementById('cancelInputBtn').addEventListener('click', closeUserInputModal);
	document.getElementById('closeModalBtn').addEventListener('click', closeUserInputModal);
	
	// File upload
	document.getElementById('uploadWorkflowBtn').addEventListener('click', () => {
		document.getElementById('workflowFileInput').click();
	});
	
	document.getElementById('workflowFileInput').addEventListener('change', handleWorkflowUpload);
	
	// Download
	document.getElementById('downloadWorkflowBtn').addEventListener('click', downloadWorkflow);
	
	// New workflow
	document.getElementById('newWorkflowBtn').addEventListener('click', createNewWorkflow);
	
	// Clear events
	document.getElementById('clearEventsBtn').addEventListener('click', () => {
		eventLog.innerHTML = '';
		addEventLog('system', 'Event log cleared');
	});
}

// ========================================================================
// MODE SWITCHING
// ========================================================================

async function switchMode(mode) {
	if (mode === 'chat') {
		chatModeBtn.classList.add('active');
		workflowModeBtn.classList.remove('active');
		chatMode.style.display = 'flex';
		workflowMode.style.display = 'none';
		
		// Exit workflow mode
		if (workflowVisualizer?.isWorkflowMode) {
			workflowVisualizer.exitWorkflowMode();
		}
		
	} else {
		chatModeBtn.classList.remove('active');
		workflowModeBtn.classList.add('active');
		chatMode.style.display = 'none';
		workflowMode.style.display = 'flex';
		
		// CRITICAL: Initialize workflow system FIRST before entering mode
		if (!workflowClient && gGraph) {
			const initialized = await initWorkflowSystem();
			if (!initialized) {
				addEventLog('system', '❌ Failed to initialize workflow system');
				// Revert UI state
				chatModeBtn.classList.add('active');
				workflowModeBtn.classList.remove('active');
				chatMode.style.display = 'flex';
				workflowMode.style.display = 'none';
				return;
			}
		}
		
		// THEN enter workflow mode (node types are now registered)
		if (workflowVisualizer && !workflowVisualizer.isWorkflowMode) {
			workflowVisualizer.enterWorkflowMode();
		}
		
		// Finally reload current workflow if any
		if (currentWorkflow && workflowVisualizer) {
			workflowVisualizer.loadWorkflow(currentWorkflow);
		}
	}
}

// ========================================================================
// WORKFLOW SYSTEM INITIALIZATION
// ========================================================================

async function initWorkflowSystem() {
	const serverUrl = document.getElementById('serverUrl').value.trim();
	
	if (!serverUrl) {
		addEventLog('system', '⚠️ No server URL configured');
		return false;
	}
	
	addEventLog('system', '🔄 Initializing workflow system...');
	
	// Step 1: Fetch and register workflow schema from backend
	const schemaRegistered = await fetchAndRegisterWorkflowSchema(gGraph, serverUrl);
	
	if (!schemaRegistered) {
		addEventLog('system', '❌ Failed to register workflow schema');
		return false;
	}
	
	// Verify node types are registered
	const registeredCount = VALID_WORKFLOW_TYPES.size;
	let foundCount = 0;
	VALID_WORKFLOW_TYPES.forEach(type => {
		const nodeTypeName = `${WORKFLOW_SCHEMA_NAME}.${type}`;
		if (gGraph.graph.nodeTypes[nodeTypeName]) {
			foundCount++;
		}
	});
	
	if (foundCount !== registeredCount) {
		addEventLog('system', `❌ Node registration incomplete: ${foundCount}/${registeredCount}`);
		return false;
	}
	
	addEventLog('system', `✅ Registered ${foundCount} workflow node types`);
	
	// Step 2: Create workflow client and visualizer
	workflowClient = new WorkflowClient(serverUrl);
	workflowVisualizer = new WorkflowVisualizer(gGraph);
	
	// Step 3: Connect WebSocket
	workflowClient.connectWebSocket();
	
	// Step 4: Setup event handlers
	setupWorkflowEvents();
	
	// Step 5: Refresh SchemaGraph context menu to include workflow nodes
	// SchemaGraph should automatically pick up registered node types
	if (gGraph && gGraph.graph) {
		// Force a context menu refresh if there's an API for it
		// The context menu should now show workflow.start, workflow.end, etc.
		console.log('✅ Workflow nodes available in context menu');
	}
	
	addEventLog('system', '✅ Workflow system initialized');
	return true;
}

function setupWorkflowEvents() {
	// Connection events
	workflowClient.on('connected', () => {
		addEventLog('system', '✅ WebSocket connected');
		// updateWorkflowStatus('connected', 'Connected');
		updateWorkflowStatus('idle', 'Ready');
	});
	
	workflowClient.on('disconnected', () => {
		addEventLog('system', '🔌 WebSocket disconnected');
		updateWorkflowStatus('disconnected', 'Disconnected');
	});
	
	// Workflow events
	workflowClient.on('workflow.started', (event) => {
		addEventLog('workflow-started', `▶️ Workflow started`);
		currentExecutionId = event.execution_id;
		updateWorkflowControls('running');
		workflowVisualizer.clearState();
	});
	
	// workflowClient.on('workflow.paused', (event) => {
	// 	addEventLog('workflow-paused', `⏸️ Workflow paused`);
	// 	currentExecutionId = event.execution_id;
	// 	updateWorkflowControls('running');
	// 	workflowVisualizer.clearState();
	// });
	
	// workflowClient.on('workflow.resumed', (event) => {
	// 	addEventLog('workflow-resumed', `▶️ Workflow resumed`);
	// 	currentExecutionId = event.execution_id;
	// 	updateWorkflowControls('running');
	// 	workflowVisualizer.clearState();
	// });
	
	workflowClient.on('workflow.cancelled', (event) => {
		addEventLog('workflow-cancelled', `⏹️ Workflow cancelled`);
		currentExecutionId = event.execution_id;
		updateWorkflowControls('running');
		workflowVisualizer.clearState();
	});
	
	workflowClient.on('workflow.completed', (event) => {
		addEventLog('workflow-completed', `✅ Workflow completed`);
		updateWorkflowControls('idle');
		updateWorkflowStatus('idle', 'Ready');
	});
	
	workflowClient.on('workflow.failed', (event) => {
		addEventLog('workflow-failed', `❌ Workflow failed: ${event.error || 'Unknown'}`);
		updateWorkflowControls('idle');
		updateWorkflowStatus('idle', 'Failed');
	});
	
	// Node events
	workflowClient.on('node.started', (event) => {
		const idx = parseInt(event.node_id);
		const label = event.data?.node_label || `Node ${idx}`;
		addEventLog('node-started', `▶️ [${idx}] ${label}`);
		workflowVisualizer.updateNodeState(idx, 'running');
	});
	
	workflowClient.on('node.completed', (event) => {
		const idx = parseInt(event.node_id);
		const label = event.data?.node_label || `Node ${idx}`;
		addEventLog('node-completed', `✅ [${idx}] ${label}`);
		workflowVisualizer.updateNodeState(idx, 'completed', event.data);
	});
	
	workflowClient.on('node.failed', (event) => {
		const idx = parseInt(event.node_id);
		const label = event.data?.node_label || `Node ${idx}`;
		addEventLog('node-failed', `❌ [${idx}] ${label}: ${event.error}`);
		workflowVisualizer.updateNodeState(idx, 'failed', { error: event.error });
	});
	
	// User input
	workflowClient.on('user_input.requested', (event) => {
		const idx = parseInt(event.node_id);
		addEventLog('user-input-requested', `👤 User input requested: [${idx}]`);
		showUserInputModal(event);
	});
}

// ========================================================================
// WORKFLOW MANAGEMENT
// ========================================================================

function loadSampleWorkflows() {
	// Simple test workflow
	const simple = {
		info: { name: 'Simple Test', version: '1.0.0' },
		nodes: [
			{ id: 'start', type: 'start', label: 'Start', position: {x: 100, y: 100} },
			{ id: 'transform', type: 'transform', label: 'Transform', 
			config: { type: 'python', script: 'output = {"result": "Hello Workflow!"}' },
			position: {x: 100, y: 250} },
			{ id: 'end', type: 'end', label: 'End', position: {x: 100, y: 400} }
		],
		edges: [
			{ source: 0, target: 1, source_slot: 'output', target_slot: 'input' },
			{ source: 1, target: 2, source_slot: 'output', target_slot: 'input' }
		],
		variables: {}
	};
	
	workflowLibrary.set('simple', simple);
	updateWorkflowSelect();
}

function updateWorkflowSelect() {
	workflowSelect.innerHTML = '<option value="">Select workflow...</option>';
	
	for (const [key, workflow] of workflowLibrary.entries()) {
		const option = document.createElement('option');
		option.value = key;
		option.textContent = workflow.info?.name || key;
		workflowSelect.appendChild(option);
	}
}

function onWorkflowSelected() {
	const key = workflowSelect.value;
	if (!key) return;
	
	currentWorkflow = workflowLibrary.get(key);
	
	if (currentWorkflow && workflowVisualizer) {
		workflowVisualizer.loadWorkflow(currentWorkflow);
		startWorkflowBtn.disabled = false;
		updateWorkflowStatus('idle', 'Ready');
		addEventLog('system', `📂 Loaded: ${currentWorkflow.info?.name || key}`);
	}
}

function downloadWorkflow() {
	if (!currentWorkflow) {
		alert('No workflow selected');
		return;
	}
	
	// Sync positions from graph
	if (workflowVisualizer) {
		currentWorkflow = workflowVisualizer.exportWorkflow();
	}
	
	const json = JSON.stringify(currentWorkflow, null, 2);
	const blob = new Blob([json], { type: 'application/json' });
	const url = URL.createObjectURL(blob);
	
	const a = document.createElement('a');
	a.href = url;
	a.download = `${currentWorkflow.info?.name || 'workflow'}.json`;
	a.click();
	
	URL.revokeObjectURL(url);
	addEventLog('system', '💾 Workflow downloaded');
}

function handleWorkflowUpload(event) {
	const file = event.target.files[0];
	if (!file) return;
	
	const reader = new FileReader();
	reader.onload = (e) => {
		try {
			const workflow = JSON.parse(e.target.result);
			const key = workflow.info?.name || `workflow_${Date.now()}`;
			
			workflowLibrary.set(key, workflow);
			updateWorkflowSelect();
			workflowSelect.value = key;
			onWorkflowSelected();
			
			addEventLog('system', `📂 Uploaded: ${key}`);
		} catch (error) {
			addEventLog('workflow-failed', `❌ Upload failed: ${error.message}`);
		}
	};
	reader.readAsText(file);
	
	event.target.value = '';
}

function createNewWorkflow() {
	const name = prompt('Enter workflow name:');
	if (!name) return;
	
	const workflow = {
		info: { name, version: '1.0.0' },
		nodes: [],
		edges: [],
		variables: {}
	};
	
	const key = name.toLowerCase().replace(/\s+/g, '_');
	workflowLibrary.set(key, workflow);
	updateWorkflowSelect();
	workflowSelect.value = key;
	onWorkflowSelected();
	
	addEventLog('system', `📄 New workflow: ${name}`);
}

// ========================================================================
// WORKFLOW EXECUTION
// ========================================================================

async function startWorkflow() {
	if (!currentWorkflow || !workflowClient) {
		alert('No workflow loaded');
		return;
	}
	
	try {
		startWorkflowBtn.disabled = true;
		updateWorkflowStatus('running', 'Starting...');
		
		const result = await workflowClient.startWorkflow(currentWorkflow, {});
		currentExecutionId = result.execution_id;
		
		updateWorkflowStatus('running', 'Running');
		
	} catch (error) {
		addEventLog('workflow-failed', `❌ Start failed: ${error.message}`);
		updateWorkflowStatus('failed', 'Failed');
		startWorkflowBtn.disabled = false;
	}
}

async function stopWorkflow() {
	if (!currentExecutionId || !workflowClient) return;
	
	try {
		stopWorkflowBtn.disabled = true;
		await workflowClient.cancelWorkflow(currentExecutionId);
		addEventLog('system', '⏹️ Workflow stopped');
	} catch (error) {
		addEventLog('workflow-failed', `❌ Stop failed: ${error.message}`);
	} finally {
		stopWorkflowBtn.disabled = false;
	}
}

function updateWorkflowControls(state) {
	if (state === 'running') {
		startWorkflowBtn.disabled = true;
		stopWorkflowBtn.disabled = false;
	} else {
		startWorkflowBtn.disabled = !currentWorkflow;
		stopWorkflowBtn.disabled = true;
	}
}

// ========================================================================
// USER INPUT MODAL
// ========================================================================

let pendingInputEvent = null;

function showUserInputModal(event) {
	pendingInputEvent = event;
	userInputPrompt.textContent = event.data?.prompt || 'Please provide input:';
	userInputField.value = '';
	userInputModal.style.display = 'flex';
	userInputField.focus();
}

function closeUserInputModal() {
	userInputModal.style.display = 'none';
	pendingInputEvent = null;
}

async function submitUserInput() {
	if (!pendingInputEvent || !workflowClient) return;
	
	const input = userInputField.value.trim();
	if (!input) {
		alert('Please enter a value');
		return;
	}
	
	try {
		await workflowClient.provideUserInput(
			pendingInputEvent.execution_id,
			pendingInputEvent.node_id,
			input
		);
		closeUserInputModal();
	} catch (error) {
		alert(`Failed: ${error.message}`);
	}
}

// ========================================================================
// UI HELPERS
// ========================================================================

function updateWorkflowStatus(type, message) {
	workflowStatus.className = `numel-status numel-status-${type}`;
	workflowStatus.textContent = message;
}

function addEventLog(type, message) {
	const item = document.createElement('div');
	item.className = `numel-event-item ${type}`;
	
	const time = new Date().toLocaleTimeString();
	
	item.innerHTML = `
		<span class="numel-event-time">${time}</span>
		<span class="numel-event-message">${message}</span>
	`;
	
	eventLog.appendChild(item);
	eventLog.scrollTop = eventLog.scrollHeight;
	
	// Limit log size
	while (eventLog.children.length > 100) {
		eventLog.removeChild(eventLog.firstChild);
	}
}

// ========================================================================
// INITIALIZATION
// ========================================================================

if (document.readyState === 'loading') {
	document.addEventListener('DOMContentLoaded', initWorkflowUI);
} else {
	initWorkflowUI();
}
