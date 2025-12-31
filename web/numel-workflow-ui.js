/* ========================================================================
   NUMEL WORKFLOW UI - User Interface Logic
   ======================================================================== */

// Constants
const _FORCE_PREVIEW_ON_SAME_DATA = true;

// Global State
let client = null;
let visualizer = null;
let schemaGraph = null;
let currentExecutionId = null;
let pendingRemoveName = null;
let singleMode = true;
let workflowDirty = true;

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
		// console.log('Graph modified:', e.originalEvent);
	});

	// Create visualizer
	visualizer = new WorkflowVisualizer(schemaGraph);

	// Setup event listeners
	setupEventListeners();

	// Initial log
	addLog('info', '🚀 Numel Workflow ready');
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
	$('singleImportBtn').addEventListener('click', () => $('singleWorkflowFileInput').click());
	$('singleDownloadBtn').addEventListener('click', downloadWorkflow);
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
	$('cancelInputBtn').addEventListener('click', closeModal);
	$('closeModalBtn').addEventListener('click', closeModal);
}

function enableStart(enable) {
	$('singleModeSwitch' ).disabled = !enable;
	$('startBtn'         ).disabled = !enable;
	$('cancelBtn'        ).disabled = enable;
	$('singleImportBtn'  ).disabled = !enable;
	$('singleDownloadBtn').disabled = !enable;
	$('clearWorkflowBtn' ).disabled = !enable;
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

		// visualizer.schemaGraph.api.workflow.debug();

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
		$('downloadWorkflowBtn').disabled = false;
		$('singleImportBtn').disabled = false;
		$('singleDownloadBtn').disabled = false;
		$('clearWorkflowBtn').disabled = false;
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
	workflowDirty = true;
	
	$('connectBtn').textContent = 'Connect';
	$('connectBtn').classList.remove('nw-btn-danger');
	$('connectBtn').classList.add('nw-btn-primary');
	$('serverUrl').disabled = false;
	$('workflowSelect').disabled = true;
	$('workflowSelect').innerHTML = '<option value="">-- Select workflow --</option>';
	$('loadWorkflowBtn').disabled = true;
	$('uploadWorkflowBtn').disabled = true;
	$('downloadWorkflowBtn').disabled = true;
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
		
		addLog('info', `▶️ Workflow started`);
	});

	client.on('workflow.completed', (event) => {
		setExecStatus('completed', 'Completed');
		enableStart(true);
		
		// UNLOCK GRAPH after completion
		schemaGraph.api.lock.unlock();
		
		addLog('success', `✅ Workflow completed`);
	});

	client.on('workflow.failed', (event) => {
		setExecStatus('failed', 'Failed');
		enableStart(true);
		
		// UNLOCK GRAPH after failure
		schemaGraph.api.lock.unlock();
		
		addLog('error', `❌ Workflow failed: ${event.error || 'Unknown error'}`);
	});

	client.on('workflow.cancelled', (event) => {
		setExecStatus('idle', 'Cancelled');
		enableStart(true);
		
		// UNLOCK GRAPH after cancellation
		schemaGraph.api.lock.unlock();
		
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

	workflowDirty = true;

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

async function syncWorkflow() {
	const workflow = visualizer.exportWorkflow();
	addLog('info', '⏳ Syncing workflow to backend...');
	await client.removeWorkflow();
	const name = visualizer.currentWorkflowName || 'single_workflow';
	const response = await client.addWorkflow(workflow, name);
	if (response.status === 'added' || response.status === 'updated') {
		workflowDirty = false;
		visualizer.currentWorkflowName = response.name;
		$('singleWorkflowName').textContent = response.name;
		addLog('success', `✅ Synced "${response.name}"`);
	} else {
		throw new Error('Failed to sync workflow');
	}
}

async function handleSingleImport(event) {
	const file = event.target.files?.[0];
	if (!file) return;

	workflowDirty = true;

	try {
		const text = await file.text();
		const workflow = JSON.parse(text);

		// Clear current workflow
		schemaGraph.api.graph.clear();
		schemaGraph.api.view.reset();

		// Load into visualizer (memory only)
		const loaded = visualizer.loadWorkflow(workflow, file.name.replace('.json', ''));
		if (loaded) {
			enableStart(true);
			// $('singleWorkflowName').textContent = visualizer.currentWorkflowName || 'Untitled';
			addLog('success', `📂 Imported "${visualizer.currentWorkflowName}" (local)`);
			await syncWorkflow();
		}
	} catch (error) {
		addLog('error', `❌ Failed to import: ${error.message}`);
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

async function clearWorkflow() {
	if (!visualizer.currentWorkflow) return;

	workflowDirty = true;

	schemaGraph.api.graph.clear();
	schemaGraph.api.view.reset();
	await client.removeWorkflow();

	visualizer.currentWorkflow = null;
	visualizer.currentWorkflowName = null;
	visualizer.graphNodes = [];

	$('downloadWorkflowBtn').disabled = true;
	$('singleDownloadBtn'  ).disabled = true;
	$('startBtn'           ).disabled = true;
	$('clearWorkflowBtn'   ).disabled = true;
	
	if (singleMode) {
		$('singleWorkflowName').textContent = 'None';
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
		$('singleDownloadBtn').disabled = !visualizer.currentWorkflow;
	} else {
		$('singleImportBtn').disabled = true;
		$('singleDownloadBtn').disabled = true;
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

	try {
		enableStart(false);

		// In single mode, sync to backend if dirty
		if (singleMode) {
			if (workflowDirty) {
				await syncWorkflow();
			}
		}

		const workflowName = visualizer.currentWorkflowName;
		addLog('info', `⏳ Starting "${workflowName}"...`);

		const initialData = null;
		const response = await client.startWorkflow(workflowName, initialData);

		if (response.status !== 'started') {
			throw new Error('Failed to start workflow');
		}

	} catch (error) {
		enableStart(true);
		addLog('error', `❌ Start failed: ${error.message}`);
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
	for (const output of graphNode.outputs || []) {
		for (const linkId of output.links || []) {
			const link = graph.links[linkId];
			if (!link) continue;
			
			const targetNode = graph.getNodeById(link.target_id);
			if (!targetNode?.isPreviewNode) continue;
			
			// Determine which output data to use
			const slotName = output.name;
			let data;
			
			if (outputs && typeof outputs === 'object') {
				// Try exact slot name first
				if (slotName in outputs) {
					data = outputs[slotName];
				} 
				// Try base name for dotted slots
				else {
					const baseName = slotName.split('.')[0];
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
 * @param {any} data - New data to display
 * @param {EdgePreviewManager} previewManager - Preview manager instance
 */
function updatePreviewNode(previewNode, data, previewManager) {
	// Store previous data for comparison
	// const hadData = previewNode.previewData !== null && previewNode.previewData !== undefined;
	const dataChanged = _FORCE_PREVIEW_ON_SAME_DATA || !deepEqual(previewNode.previewData, data);
	
	// Update node data
	previewNode.previewData = data;
	previewNode.previewType = previewNode._detectType(data);
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
}

/**
 * Propagate data through chained preview nodes
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
			if (!targetNode?.isPreviewNode) continue;
			
			updatePreviewNode(targetNode, data, previewManager);
			propagateToDownstreamPreviews(targetNode, data, previewManager);
		}
	}
}

/**
 * Trigger flash animation on a preview node (canvas-based)
 * @param {Node} node - Preview node to flash
 */
function triggerPreviewFlash(node) {
	node._flashStart = performance.now();
	node._flashDuration = 600; // ms
	node._isFlashing = true;
	
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
