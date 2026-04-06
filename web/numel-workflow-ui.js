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
let currentPlatformExecutionId = null;
let currentSpaceId    = null;
let currentSpaceInfo  = null;
let _pendingExecEvents = [];   // buffer events arriving before currentExecutionId is set
let workflowDirty      = true;
let fileUploadManager  = null;
let consoleManager     = null;
let galleryManager     = null;
let appsManager        = null;
let api                = null;  // NumelAPI instance, shared across all managers
let currentWorkflowHasContent = false;

// ── Task 2: Wire tooltip edge data store ─────────────────────────────────────
// Key: "workflowNodeIdx:fieldName" → last output value from that slot
let _edgeDataStore     = {};

// ── Task 6: Node groups ──────────────────────────────────────────────────────
const _nodeGroups      = []; // {id, label, nodeIds[]}

// DOM Elements
const $ = id => document.getElementById(id);
const STARTER_GALLERY_IDS = Object.freeze({
	research: 'planner05',
	media: '1d73d947',
});
const STARTER_ASSISTANT_PROMPT = '/gen A workflow that asks the user for input, transforms it into a short helpful response, and previews the result.';
const GLOBAL_LAYOUT_PRESET_STORAGE_KEY = 'numel_global_layout_preset_v1';
const GLOBAL_LAYOUT_PRESETS = Object.freeze(['project-workbench']);

function _normalizeGlobalLayoutPreset(preset) {
	const value = String(preset || '').trim().toLowerCase();
	return GLOBAL_LAYOUT_PRESETS.includes(value) ? value : 'project-workbench';
}

function _getStoredGlobalLayoutPreset() {
	try {
		return _normalizeGlobalLayoutPreset(localStorage.getItem(GLOBAL_LAYOUT_PRESET_STORAGE_KEY));
	} catch {
		return 'project-workbench';
	}
}

function _applyGlobalLayoutPreset(preset) {
	const normalized = _normalizeGlobalLayoutPreset(preset);
	const body = document.body;
	if (body) {
		Array.from(body.classList)
			.filter((className) => className.startsWith('nw-layout-'))
			.forEach((className) => body.classList.remove(className));
		body.classList.add(`nw-layout-${normalized}`);
	}
	const select = $('globalLayoutSelect');
	if (select) select.value = normalized;
	window._numelGlobalLayoutPreset = normalized;
	return normalized;
}

function _setGlobalLayoutPreset(preset) {
	const normalized = _applyGlobalLayoutPreset(preset);
	try {
		localStorage.setItem(GLOBAL_LAYOUT_PRESET_STORAGE_KEY, normalized);
	} catch {}
	return normalized;
}

function _starterStorageKey() {
	return `numel_starter_seen_v1_${window._numelUser?.id || 'guest'}`;
}

function _hasSeenStarterExperience() {
	try {
		return localStorage.getItem(_starterStorageKey()) === '1';
	} catch {
		return false;
	}
}

function _markStarterExperienceSeen() {
	try {
		localStorage.setItem(_starterStorageKey(), '1');
	} catch {}
}

function _hasWorkflowContent(workflow) {
	return Array.isArray(workflow?.nodes) && workflow.nodes.length > 0;
}

function _isCurrentWorkflowEmptyState() {
	const hasGraphNodes = !!schemaGraph?.graph?.nodes?.length;
	return !hasGraphNodes && !currentWorkflowHasContent;
}

function _starterHelloWorkflow() {
	return {
		options: {
			type: 'workflow_options',
			name: 'Hello Workflow',
			description: 'The simplest runnable workflow: Start, Preview, End.',
		},
		nodes: [
			{ type: 'start_flow', extra: { pos: [60, 180], name: 'Start' } },
			{ type: 'preview_flow', extra: { pos: [320, 180], name: 'Preview' } },
			{ type: 'end_flow', extra: { pos: [580, 180], name: 'End' } },
		],
		edges: [
			{ source: 0, target: 1, source_slot: 'flow_out', target_slot: 'flow_in' },
			{ source: 1, target: 2, source_slot: 'flow_out', target_slot: 'flow_in' },
		],
	};
}

function _closeStarterModal(markSeen = true) {
	const overlay = document.getElementById('nwStarterModal');
	if (!overlay) return;
	if (markSeen) _markStarterExperienceSeen();
	overlay.remove();
}

function _showStarterModal() {
	if (!_isAuthenticatedUser() || _hasSeenStarterExperience() || !_isCurrentWorkflowEmptyState()) return;
	if (document.getElementById('nwStarterModal')) return;

	const overlay = document.createElement('div');
	overlay.id = 'nwStarterModal';
	overlay.className = 'nw-modal';
	overlay.innerHTML = `
		<div class="nw-modal-content nw-starter-modal">
			<div class="nw-modal-header">
				<h3>Start Your First Workflow</h3>
				<button class="nw-modal-close" data-role="close">&times;</button>
			</div>
			<div class="nw-modal-body">
				<div class="nw-starter-modal-copy">
					Numel works best when each space starts from a concrete workflow, not a blank canvas.
					Choose the fastest path to a useful first run for <b>${currentSpaceInfo?.title || 'this workbench'}</b>.
				</div>
				<div class="nw-starter-modal-grid">
					<button class="nw-starter-action" data-starter-action="hello" type="button">
						<span class="nw-starter-action-title">Hello Workflow</span>
						<span class="nw-starter-action-copy">Load the smallest runnable graph and see the workflow surface immediately.</span>
					</button>
					<button class="nw-starter-action" data-starter-action="research" type="button">
						<span class="nw-starter-action-title">Research Starter</span>
						<span class="nw-starter-action-copy">Open a planner-style research and report pipeline.</span>
					</button>
					<button class="nw-starter-action" data-starter-action="media" type="button">
						<span class="nw-starter-action-title">Webcam Starter</span>
						<span class="nw-starter-action-copy">Try a browser-native webcam workflow with live media.</span>
					</button>
					<button class="nw-starter-action" data-starter-action="assistant" type="button">
						<span class="nw-starter-action-title">Ask Assistant</span>
						<span class="nw-starter-action-copy">Open Numel Assistant with a starter build prompt.</span>
					</button>
				</div>
			</div>
			<div class="nw-modal-footer">
				<div class="nw-starter-modal-actions">
					<button class="nw-btn nw-btn-secondary" data-starter-action="gallery" type="button">Browse Gallery</button>
				</div>
				<button class="nw-btn nw-btn-secondary" data-role="later" type="button">Later</button>
			</div>
		</div>`;
	document.body.appendChild(overlay);

	overlay.querySelector('[data-role="close"]')?.addEventListener('click', () => _closeStarterModal(true));
	overlay.querySelector('[data-role="later"]')?.addEventListener('click', () => _closeStarterModal(true));
	overlay.addEventListener('click', (e) => {
		if (e.target === overlay) _closeStarterModal(true);
	});
	overlay.querySelectorAll('[data-starter-action]').forEach((btn) => {
		btn.addEventListener('click', async () => {
			await _runStarterAction(btn.getAttribute('data-starter-action') || '');
		});
	});
}

function _updateStarterPanel() {
	const panel = $('spaceStarterPanel');
	const subtitle = $('spaceStarterSubtitle');
	_updateWorkbenchOverview();
	if (!panel) return;
	const visible = !!client?.isConnected && _isAuthenticatedUser() && _isCurrentWorkflowEmptyState();
	panel.style.display = visible ? '' : 'none';
	if (subtitle) {
		subtitle.textContent = currentSpaceInfo?.title
			? `"${currentSpaceInfo.title}" is empty. Start with a ready-made workflow, ask the assistant, or browse the gallery.`
			: 'Start with a ready-made workflow, ask the assistant, or browse the gallery.';
	}
	if (!visible) {
		_closeStarterModal(false);
	}
}

function _updateWorkbenchOverview() {
	const spaceEl = $('workbenchSpaceName');
	const workflowEl = $('workbenchWorkflowName');
	const summaryEl = $('workbenchSummary');
	const statusEl = $('workbenchStatusPill');
	const askBtn = $('workbenchAskAssistantBtn');
	const galleryBtn = $('workbenchBrowseGalleryBtn');
	const canvasSpaceEl = $('canvasWorkbenchSpaceName');
	const canvasWorkflowEl = $('canvasWorkbenchWorkflowName');
	const canvasSummaryEl = $('canvasWorkbenchSummary');
	const canvasAskBtn = $('canvasAskAssistantBtn');
	const canvasGalleryBtn = $('canvasBrowseGalleryBtn');
	const canvasRunBtn = $('canvasStartRunBtn');
	const spaceName = currentSpaceInfo?.title || currentSpaceInfo?.slug || 'Choose a space';
	const workflowName = visualizer?.currentWorkflowName || $('singleWorkflowName')?.textContent || 'None';
	const isReady = !!client?.isConnected && _isAuthenticatedUser();
	const isEmpty = _isCurrentWorkflowEmptyState();
	const startDisabled = $('startBtn')?.disabled ?? true;
	let overviewSummary = '';
	let canvasSummary = '';

	if (spaceEl) spaceEl.textContent = spaceName;
	if (workflowEl) workflowEl.textContent = `Workflow: ${workflowName || 'None'}`;
	if (statusEl) statusEl.textContent = isReady ? 'Connected' : 'Offline';

	if (!currentSpaceInfo) {
		overviewSummary = 'Create or select a space to start a focused workflow project.';
		canvasSummary = 'Choose a space to start shaping a tagged workflow on the canvas.';
	} else if (isEmpty) {
		overviewSummary = `"${spaceName}" is ready for its first useful run. Start from a template, open the gallery, or let the assistant draft the workflow.`;
		canvasSummary = `"${spaceName}" is empty. Drop in a starter, sketch nodes, and use workflow tags to keep the canvas organized as it grows.`;
	} else {
		overviewSummary = `You are working in "${spaceName}". "${workflowName || 'Current Workflow'}" is ready to edit, save, and run.`;
		canvasSummary = `"${workflowName || 'Current Workflow'}" is open in "${spaceName}". Edit nodes here, keep related areas tagged, and launch a run when you are ready.`;
	}

	if (summaryEl) summaryEl.textContent = overviewSummary;
	if (canvasSpaceEl) canvasSpaceEl.textContent = spaceName;
	if (canvasWorkflowEl) canvasWorkflowEl.textContent = `Workflow: ${workflowName || 'None'}`;
	if (canvasSummaryEl) canvasSummaryEl.textContent = canvasSummary;
	if (askBtn) askBtn.disabled = !isReady;
	if (galleryBtn) galleryBtn.disabled = !isReady;
	if (canvasAskBtn) canvasAskBtn.disabled = !isReady;
	if (canvasGalleryBtn) canvasGalleryBtn.disabled = !isReady;
	if (canvasRunBtn) canvasRunBtn.disabled = !isReady || startDisabled;
}

function _syncSpaceControls() {
	const select = $('spaceSelect');
	const createBtn = $('createSpaceBtn');
	const removeBtn = $('removeSpaceBtn');
	const hasApi = !!api;
	const optionCount = select ? Array.from(select.options || []).filter((option) => !!option.value).length : 0;

	if (select) {
		select.disabled = !hasApi || optionCount === 0;
	}
	if (createBtn) {
		createBtn.disabled = !hasApi;
	}
	if (removeBtn) {
		removeBtn.disabled = !hasApi || !currentSpaceId || optionCount <= 1;
	}
}

function _closeSidePanelDom(id) {
	document.getElementById(id)?.classList.remove('open');
}

window.closeNumelSidePanels = function(except = []) {
	const keep = new Set(Array.isArray(except) ? except : [except]);
	if (!keep.has('console')) {
		try { consoleManager?.close?.(); } catch {}
		_closeSidePanelDom('consolePanel');
	}
	if (!keep.has('gallery')) {
		try { galleryManager?.close?.(); } catch {}
		_closeSidePanelDom('galleryPanel');
	}
	if (!keep.has('apps')) {
		try { appsManager?.close?.(); } catch {}
		_closeSidePanelDom('appsPanel');
	}
	if (!keep.has('admin')) {
		try { if (typeof NumelAdmin !== 'undefined') NumelAdmin.close(); } catch {}
		_closeSidePanelDom('adminPanel');
	}
	if (!keep.has('channels')) {
		try { if (typeof NumelChannels !== 'undefined') NumelChannels.close(); } catch {}
		_closeSidePanelDom('channelPanel');
	}
	if (!keep.has('extensions')) {
		try { if (typeof NumelExtensions !== 'undefined') NumelExtensions.close(); } catch {}
		_closeSidePanelDom('extensionsPanel');
	}
	if (!keep.has('user')) {
		try { if (typeof NumelUserPanel !== 'undefined') NumelUserPanel.close(); } catch {}
		_closeSidePanelDom('userPanel');
	}
};

function _updateStarterExperience(showModal = false) {
	_updateStarterPanel();
	if (showModal) {
		_showStarterModal();
	}
}

async function _loadStarterGalleryItem(id) {
	if (!api) return;
	const item = await api.galleryGet(id);
	if (!item?.workflow) throw new Error(`Starter workflow "${id}" is unavailable`);
	await window.loadAndSyncWorkflow(item.workflow, item.title || item.id);
}

async function _runStarterAction(action) {
	try {
		switch (action) {
			case 'hello':
				await window.loadAndSyncWorkflow(_starterHelloWorkflow(), 'Hello Workflow');
				addLog('success', '✨ Loaded Hello Workflow starter');
				break;
			case 'research':
				await _loadStarterGalleryItem(STARTER_GALLERY_IDS.research);
				addLog('success', '✨ Loaded Research Starter');
				break;
			case 'media':
				await _loadStarterGalleryItem(STARTER_GALLERY_IDS.media);
				addLog('success', '✨ Loaded Webcam Starter');
				break;
			case 'assistant':
				if (!consoleManager) throw new Error('Assistant is not ready yet');
				if (typeof consoleManager.isOpen === 'function' && consoleManager.isOpen()) {
					consoleManager.close();
					addLog('info', '🧩 Assistant closed');
					break;
				}
				await consoleManager.launchStarterPrompt(STARTER_ASSISTANT_PROMPT, { enablePlanner: false, autoSend: false });
				addLog('info', '🤖 Assistant opened with a starter build prompt');
				break;
			case 'gallery':
				if (!galleryManager) throw new Error('Gallery is not ready yet');
				if (typeof galleryManager.isOpen === 'function' && galleryManager.isOpen()) {
					galleryManager.close();
					addLog('info', '🖼 Closed workflow gallery');
				} else {
					await galleryManager.open();
					addLog('info', '🖼 Opened workflow gallery');
				}
				break;
			default:
				return;
		}
		_markStarterExperienceSeen();
		_closeStarterModal(false);
		_updateStarterExperience(false);
	} catch (error) {
		addLog('error', `❌ Starter action failed: ${error.message}`);
		await NumelAlert('Starter Flow', error.message || 'Failed to load starter flow.');
	}
}

function _isAdminUser() {
	return !!(window._numelUser && String(window._numelUser.role || '').toLowerCase() === 'admin');
}

function _isAuthenticatedUser() {
	return !!window._numelUser;
}

function _credentialsAccessMessage() {
	if (!_isAuthenticatedUser()) {
		return 'Sign in to manage your credentials.';
	}
	return 'Credentials are scoped to your account and are used only for your executions.';
}

function _renderCredentialAccessState() {
	const canManageCredentials = _isAuthenticatedUser();
	const addBtn   = $('addCredentialBtn');
	const form     = $('credentialForm');
	const list     = $('credentialsList');
	const note     = $('credentialsAccessNote');
	const noteText = $('credentialsAccessText');

	if (addBtn) addBtn.style.display = canManageCredentials ? '' : 'none';
	if (list) list.style.display = canManageCredentials ? '' : 'none';
	if (!canManageCredentials && form) form.style.display = 'none';
	if (note) note.style.display = canManageCredentials ? 'none' : 'flex';
	if (noteText) noteText.textContent = _credentialsAccessMessage();

	if (!list || !canManageCredentials) return canManageCredentials;
	if (list.dataset.locked === 'true') {
		delete list.dataset.locked;
	}
	return true;
}

function _applyPermissionVisibility() {
	_renderCredentialAccessState();

	if (typeof NumelAdmin !== 'undefined') NumelAdmin.checkAdminAccess(window._numelUser);
}

// ========================================================================
// Workflow name sync helper — keeps singleWorkflowName div, currentWorkflowName,
// and the active tab label all in sync.
// syncTab=false skips updating the tab (used when the change originated from the tab).
// ========================================================================
function _setWorkflowName(name) {
	if (!visualizer) return;
	// The setter auto-syncs tab label, workflow options, and fires onNameChanged callbacks.
	visualizer.currentWorkflowName = name || null;
}

// ========================================================================
// Initialization
// ========================================================================

document.addEventListener('DOMContentLoaded', () => {
	_applyPermissionVisibility();
	_applyGlobalLayoutPreset(_getStoredGlobalLayoutPreset());

	// Initialize SchemaGraph
	schemaGraph = new SchemaGraphApp('sg-main-canvas');
	window.schemaGraph = schemaGraph;  // expose for console planner lock

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
		_updateStarterExperience(false);
		// console.log('Graph modified:', e.originalEvent);
	});

	// Handle link creation - trace upward for preview data
	schemaGraph.api.events.onLinkCreated((data) => {
		handleLinkCreatedForPreview(data);
		_onLinkChangedToolkitMethods(data, true);
	});

	// Handle link removal - refresh preview data for affected nodes
	schemaGraph.api.events.onLinkRemoved((data) => {
		handleLinkRemovedForPreview(data);
		_onLinkChangedToolkitMethods(data, false);
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

	// Tab rename → sync to currentWorkflowName and singleWorkflowName
	schemaGraph.eventBus.on('tab:renamed', (data) => {
		if (!data.active) return;
		_setWorkflowName(data.name);
	});

	// Tab switch → refresh options panel and button states for the new tab's workflow
	schemaGraph.eventBus.on('tab:switched', () => {
		populateWorkflowOptionsPanel();
		updateClearButtonState();
	});

	// Refresh workflow options panel when a workflow is imported/loaded
	schemaGraph.eventBus.on(GraphEvents.WORKFLOW_IMPORTED, () => {
		populateWorkflowOptionsPanel();
		_updateStarterExperience(false);
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
			// pairedNodes              : [
			// 	["start_flow"    , "end_flow"    ],
			// 	["loop_start_flow"    , "loop_end_flow"    ],
			// 	["for_each_start_flow", "for_each_end_flow"],
			// ],
			pairedNodes: [
				{
					start    : 'start_flow',
					end      : 'end_flow'
				},
				{
					start    : 'loop_start_flow',
					end      : 'loop_end_flow',
					loopEdge : {
						fromSlot : 'flow_out',
						toSlot   : 'flow_in'
					}
				},
				{
					start    : 'for_each_start_flow',
					end      : 'for_each_end_flow',
					loopEdge : {
						fromSlot : 'flow_out',
						toSlot   : 'flow_in'
					}
				},
			],
		});

		// Configure section-based node header colors
		schemaGraph.api.schemaTypes.setSectionColors({
			'Data Sources'   : '#3d8b6e',  // Emerald
			'Native Types'   : '#7c6caf',  // Soft violet
			'Configurations' : '#4a7fa5',  // Ocean blue
			'Endpoints'      : '#8b5e3c',  // Warm bronze
			'Workflow'       : '#5c6d8e',  // Slate blue
			'Loops'          : '#2e86ab',  // Cerulean
			'Event Sources'  : '#a0522d',  // Sienna
			'Interactive'    : '#c06050',  // Coral red
			'Tutorial'       : '#d4882a',  // Amber
			'Miscellanea'    : '#606070',  // Cool gray
		});

		schemaGraph.api.canvasDrop.setAccept("image/*,audio/*,video/*,text/*,model/*,application/json,application/octet-stream,.glb,.gltf,.obj,.fbx,.stl,.ply");

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

	// After workflow load, resolve toolkit→tool_flow method dropdowns
	const _origLoadWorkflow = visualizer.loadWorkflow.bind(visualizer);
	visualizer.loadWorkflow = function(...args) {
		const result = _origLoadWorkflow(...args);
		if (result) setTimeout(_resolveAllToolkitMethods, 0);
		return result;
	};

	// Keep left-panel label and options input in sync with the workflow name
	visualizer.onNameChanged((name) => {
		const el = $('singleWorkflowName');
		if (el && !el._editing) el.textContent = name || 'None';
		const nameInput = $('wfOpt_name');
		if (nameInput && nameInput.value !== (name || '')) nameInput.value = name || '';
		_updateWorkbenchOverview();
	});

	// Sync initial workflow name from the startup tab
	const initTab = schemaGraph.tabs?.find(t => t.id === schemaGraph.activeTabId);
	if (initTab) visualizer.currentWorkflowName = initTab.name;

	// Click-to-edit workflow name on left panel label
	{
		const nameEl = $('singleWorkflowName');
		if (nameEl) {
			nameEl.style.cursor = 'text';
			nameEl.title = 'Click to rename workflow';
			nameEl.addEventListener('click', () => {
				if (nameEl._editing) return;
				nameEl._editing = true;
				const current = visualizer?.currentWorkflowName || '';
				const input = document.createElement('input');
				input.type = 'text';
				input.className = 'nw-input';
				input.value = current;
				input.placeholder = 'Workflow name...';
				input.style.margin = '0';
				input.style.padding = '2px 4px';
				input.style.fontSize = 'inherit';
				input.style.fontFamily = 'inherit';
				nameEl.textContent = '';
				nameEl.appendChild(input);
				input.focus();
				input.select();
				const commit = () => {
					if (!nameEl._editing) return;
					nameEl._editing = false;
					const newName = input.value.trim();
					input.remove();
					if (newName) {
						_setWorkflowName(newName);
					}
					nameEl.textContent = visualizer?.currentWorkflowName || 'None';
				};
				input.addEventListener('blur', commit);
				input.addEventListener('keydown', (e) => {
					if (e.key === 'Enter') input.blur();
					if (e.key === 'Escape') { nameEl._editing = false; input.remove(); nameEl.textContent = visualizer?.currentWorkflowName || 'None'; }
				});
			});
		}
	}

	// Setup event listeners
	setupEventListeners();
	_updateWorkbenchOverview();

	// Panel collapse toggle — button lives inside the title
	const _panel = document.querySelector('.nw-panel');
	if (_panel) {
		const h1 = _panel.querySelector('.nw-title');
		const wsBadge = h1.querySelector('#wsStatus');
		// Wrap existing title content (except status badge) in a span for collapse
		const titleText = document.createElement('span');
		titleText.className = 'nw-title-text';
		Array.from(h1.childNodes).forEach(n => {
			if (n !== wsBadge) titleText.appendChild(n);
		});
		h1.appendChild(titleText);
		if (wsBadge) h1.appendChild(wsBadge);

		const panelToggle = document.createElement('button');
		panelToggle.id = 'nw-panel-toggle';
		panelToggle.title = 'Toggle panel';
		h1.insertBefore(panelToggle, h1.firstChild);

		panelToggle.addEventListener('click', (e) => {
			e.stopPropagation();
			_panel.classList.toggle('nw-panel-collapsed');
			// Pump resize + camera:moved during CSS transition so overlays follow canvas
			const animEnd = Date.now() + 300;
			const pump = () => {
				window.dispatchEvent(new Event('resize'));    // resizeCanvas → draw → media overlays
				schemaGraph?.eventBus?.emit('camera:moved'); // 3D and other position-dependent overlays
				if (Date.now() < animEnd) requestAnimationFrame(pump);
			};
			requestAnimationFrame(pump);
		});
	}

	// Make each panel section collapsible via header click
	document.querySelectorAll('.nw-panel .nw-section').forEach(section => {
		const header = section.querySelector('.nw-section-header');
		if (!header) return;

		// Wrap all content after the header in a body div
		const body = document.createElement('div');
		body.className = 'nw-section-body';
		const children = Array.from(section.children);
		children.slice(children.indexOf(header) + 1).forEach(child => body.appendChild(child));
		section.appendChild(body);

		// Collapse icon prepended to header
		const icon = document.createElement('span');
		icon.className = 'nw-section-collapse-icon';
		header.insertBefore(icon, header.firstChild);

		header.addEventListener('click', (e) => {
			if (e.target.closest('button, select, input, a')) return;
			section.classList.toggle('nw-section-collapsed');
		});
	});

	// Initial log
	addLog('info', '🚀 Numel Playground ready');

	// ── Task 2: Wire tooltip ──────────────────────────────────────────────
	initWireTooltip();

	// ── Task 3: Node search (/) ───────────────────────────────────────────
	initNodeSearch();

	// ── Task 5: Mini-map ──────────────────────────────────────────────────
	initMinimap();

	// ── Task 6: Node groups (Ctrl+G) keyboard shortcut ────────────────────
	initNodeGroups();

	// Auto-connect: derive server URL from the page origin (same host:port)
	$('serverUrl').value = window.location.origin;

	// ── Auth gate ─────────────────────────────────────────────────────────
	_initAuth().then(() => {
		document.body.classList.remove('nw-auth-pending');
		autoConnect();
	});
});

async function _initAuth() {
	const baseUrl = $('serverUrl').value || window.location.origin;
	let authEnabled = false;
	let hasUsers    = true;
	try {
		const resp = await fetch(`${baseUrl}/auth/status`, { method: 'POST' });
		const data = await resp.json();
		authEnabled = data.enabled;
		hasUsers    = data.has_users !== false;
	} catch {
		// Server unreachable — skip auth, let autoConnect handle it
		return;
	}

	if (!authEnabled) {
		_applyPermissionVisibility();
		return;  // auth disabled — proceed normally
	}

	// Auth is enabled — check for stored token
	const token = localStorage.getItem('numel_token');
	if (token) {
		try {
			const resp = await fetch(`${baseUrl}/auth/me`, {
				method: 'POST',
				headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
			});
			if (resp.ok) {
				window._numelToken = token;
				window._numelUser = (await resp.json()).user;
				_showUserBar(window._numelUser);
				_applyPermissionVisibility();
				return;  // valid session
			}
		} catch {}
		localStorage.removeItem('numel_token');
	}

	// Show login modal and wait for auth
	return new Promise((resolve) => {
		const modal         = document.getElementById('authModal');
		const loginForm     = document.getElementById('authLoginForm');
		const registerForm  = document.getElementById('authRegisterForm');
		const showRegister  = document.getElementById('authShowRegister');
		const showLogin     = document.getElementById('authShowLogin');
		const loginBtn      = document.getElementById('authLoginBtn');
		const registerBtn   = document.getElementById('authRegisterBtn');
		const errorEl       = document.getElementById('authError');
		const regErrorEl    = document.getElementById('authRegError');

		modal.style.display = '';

		// If no users exist yet, show registration form first with admin hint
		if (!hasUsers) {
			loginForm.style.display    = 'none';
			registerForm.style.display = '';
			// Update the register button and title to indicate admin creation
			registerBtn.textContent = 'Create Admin Account';
			const switchText = registerForm.querySelector('.nw-auth-switch');
			if (switchText) switchText.style.display = 'none';  // hide "Already have an account?" — there are none
		}

		showRegister.onclick = (e) => { e.preventDefault(); loginForm.style.display = 'none'; registerForm.style.display = ''; };
		showLogin.onclick    = (e) => { e.preventDefault(); registerForm.style.display = 'none'; loginForm.style.display = ''; };

		const finish = (token, user) => {
			if (token) localStorage.setItem('numel_token', token);
			window._numelToken = token;
			window._numelUser  = user;
			modal.style.display = 'none';
			if (user) _showUserBar(user);
			_applyPermissionVisibility();
			resolve();
		};

		const showError = (el, msg) => { el.textContent = msg; el.style.display = ''; };

		loginBtn.onclick = async () => {
			errorEl.style.display = 'none';
			const username = document.getElementById('authUsername').value.trim();
			const password = document.getElementById('authPassword').value;
			if (!username || !password) return showError(errorEl, 'Username and password required');
			try {
				const resp = await fetch(`${baseUrl}/auth/login`, {
					method: 'POST',
					headers: { 'Content-Type': 'application/json' },
					body: JSON.stringify({ username, password }),
				});
				const data = await resp.json();
				if (!resp.ok) return showError(errorEl, data.detail || 'Login failed');
				finish(data.token, data.user);
			} catch (e) {
				showError(errorEl, `Connection error: ${e.message}`);
			}
		};

		registerBtn.onclick = async () => {
			regErrorEl.style.display = 'none';
			const username = document.getElementById('authRegUsername').value.trim();
			const email    = document.getElementById('authRegEmail').value.trim();
			const password = document.getElementById('authRegPassword').value;
			const confirm  = document.getElementById('authRegPasswordConfirm').value;
			if (!username || !password) return showError(regErrorEl, 'Username and password required');
			if (password !== confirm)   return showError(regErrorEl, 'Passwords do not match');
			try {
				const resp = await fetch(`${baseUrl}/auth/register`, {
					method: 'POST',
					headers: { 'Content-Type': 'application/json' },
					body: JSON.stringify({ username, email, password }),
				});
				const data = await resp.json();
				if (!resp.ok) return showError(regErrorEl, data.detail || 'Registration failed');
				finish(data.token, data.user);
			} catch (e) {
				showError(regErrorEl, `Connection error: ${e.message}`);
			}
		};

		// Enter key submits
		for (const id of ['authUsername', 'authPassword']) {
			document.getElementById(id).addEventListener('keydown', (e) => { if (e.key === 'Enter') loginBtn.click(); });
		}
		for (const id of ['authRegUsername', 'authRegEmail', 'authRegPassword', 'authRegPasswordConfirm']) {
			document.getElementById(id).addEventListener('keydown', (e) => { if (e.key === 'Enter') registerBtn.click(); });
		}
	});
}

function _showUserBar(user) {
	const bar = document.getElementById('authUserBar');
	if (!bar || !user) return;
	document.getElementById('authUserName').textContent = user.username;
	bar.style.display = '';
	// Populate expanded info
	const roleEl   = document.getElementById('authUserRole');
	const emailEl  = document.getElementById('authUserEmail');
	const serverEl = document.getElementById('authUserServer');
	if (roleEl)   roleEl.textContent   = user.role || 'user';
	if (emailEl)  emailEl.textContent  = user.email || '—';
	if (serverEl) serverEl.textContent = ($('serverUrl').value || window.location.origin).replace(/^https?:\/\//, '');
	_applyPermissionVisibility();
	_updateWorkbenchOverview();
	document.getElementById('authLogoutBtn').onclick = async () => {
		const ok = await NumelConfirm('Log Out', 'Are you sure you want to log out?', 'Log Out');
		if (!ok) return;
		try {
			await fetch(`${$('serverUrl').value || window.location.origin}/auth/logout`, {
				method: 'POST',
				headers: { 'Authorization': `Bearer ${window._numelToken}` },
			});
		} catch {}
		localStorage.removeItem('numel_token');
		window._numelToken = null;
		window._numelUser  = null;
		window.location.reload();
	};
}

window.addEventListener('beforeunload', (e) => {
	if (client?.isConnected) {
		disconnect();
	}
});

function setupEventListeners() {
	// Space management
	$('spaceSelect').addEventListener('change', selectCurrentSpace);
	$('createSpaceBtn').addEventListener('click', createSpace);
	$('removeSpaceBtn').addEventListener('click', removeCurrentSpace);
	$('workbenchAskAssistantBtn')?.addEventListener('click', () => _runStarterAction('assistant'));
	$('workbenchBrowseGalleryBtn')?.addEventListener('click', () => _runStarterAction('gallery'));
	$('canvasAskAssistantBtn')?.addEventListener('click', () => _runStarterAction('assistant'));
	$('canvasBrowseGalleryBtn')?.addEventListener('click', () => _runStarterAction('gallery'));
	$('canvasStartRunBtn')?.addEventListener('click', () => {
		if (!$('canvasStartRunBtn')?.disabled) $('startBtn')?.click();
	});
	$('globalLayoutSelect')?.addEventListener('change', (e) => {
		const preset = _setGlobalLayoutPreset(e.target.value || 'project-workbench');
		addLog('info', `🎛 Workspace layout set to "${preset.replace(/-/g, ' ')}"`);
		_updateWorkbenchOverview();
	});
	$('starterHelloBtn')?.addEventListener('click', () => _runStarterAction('hello'));
	$('starterResearchBtn')?.addEventListener('click', () => _runStarterAction('research'));
	$('starterMediaBtn')?.addEventListener('click', () => _runStarterAction('media'));
	$('starterAssistantBtn')?.addEventListener('click', () => _runStarterAction('assistant'));
	$('starterBrowseBtn')?.addEventListener('click', () => _runStarterAction('gallery'));

	// Workflow management
	$('clearWorkflowBtnSingle').addEventListener('click', clearWorkflow);

	// Single mode buttons
	$('singleImportBtn').addEventListener('click', () => $('singleWorkflowFileInput').click());
	$('singlePasteBtn' ).addEventListener('click', pasteWorkflowFromClipboard);
	$('singleDownloadBtn').addEventListener('click', downloadWorkflow);
	$('singleCopyBtn'  ).addEventListener('click', copyWorkflowToClipboard);
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
	$('startBtn'         ).disabled = !enable;
	$('cancelBtn'        ).disabled = enable;
	$('singleImportBtn'  ).disabled = !enable;
	$('singlePasteBtn'   ).disabled = !enable;
	$('singleDownloadBtn').disabled = !enable;
	$('singleCopyBtn'    ).disabled = !enable;
	updateClearButtonState();
	_syncSpaceControls();
	_updateWorkbenchOverview();
}

function updateClearButtonState() {
	const hasNodes = schemaGraph?.graph?.nodes?.length > 0;
	const isConnected = client?.isConnected;
	const disabled = !hasNodes || !isConnected;
	$('clearWorkflowBtnSingle').disabled = disabled;
}

// ========================================================================
// Connection Management
// ========================================================================

const AUTO_CONNECT_MAX_RETRIES = 10;
const AUTO_CONNECT_RETRY_DELAY = 2000;  // ms

async function autoConnect(attempt = 1) {
	if (client?.isConnected) return;
	try {
		await connect();
	} catch (err) {
		if (attempt < AUTO_CONNECT_MAX_RETRIES) {
			addLog('info', `⏳ Retry ${attempt}/${AUTO_CONNECT_MAX_RETRIES} in ${AUTO_CONNECT_RETRY_DELAY / 1000}s...`);
			setTimeout(() => autoConnect(attempt + 1), AUTO_CONNECT_RETRY_DELAY);
		} else {
			addLog('error', `❌ Could not connect after ${AUTO_CONNECT_MAX_RETRIES} attempts`);
		}
	}
}

async function connect() {
	const serverUrl = $('serverUrl').value.trim();
	if (!serverUrl) throw new Error('No server URL');

	setWsStatus('connecting');
	addLog('info', `⏳ Connecting to ${serverUrl}...`);

	try {
		api = new NumelAPI(serverUrl);
		window._numelAPI = api;  // expose for schemagraph library helpers
		client = new WorkflowClient(serverUrl, api);

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
		schemaGraph.api.chat?.setBaseUrl(serverUrl);

		// Populate options panels now that schema is available
		populateWorkflowOptionsPanel();
		populateExecOptionsPanel();

		// visualizer.schemaGraph.api.workflow.debug();

		// Initialize file upload manager
		fileUploadManager = new FileUploadManager(serverUrl, schemaGraph, syncWorkflow, schemaGraph.eventBus, api);
		addLog('info', '📁 File upload manager initialized');

		// Update overlay positions on camera changes
		schemaGraph.eventBus.on('camera:moved', () => {
			fileUploadManager?.updateOverlayPositions();
		});
		schemaGraph.eventBus.on('camera:zoomed', () => {
			fileUploadManager?.updateOverlayPositions();
		});

		// Initialize chat manager
		agentChatManager = new AgentChatManager(serverUrl, schemaGraph, syncWorkflow, api);
		addLog('info', '💬 Agent chat manager initialized');

		// Initialize console manager
		consoleManager = new AgentConsoleManager(serverUrl, syncWorkflow, api);
		$('consoleToggleBtn').style.display = '';
		addLog('info', '🤖 Console assistant initialized');

		// Initialize gallery manager
		galleryManager = new GalleryManager(serverUrl, api, window.loadAndSyncWorkflow);
		$('galleryToggleBtn').style.display = '';

		// Initialize published apps manager
		appsManager = new AppsManager(serverUrl, api, () => ({
			name: visualizer?.currentWorkflowName || '',
			workflow: visualizer?.exportWorkflow?.() || null,
		}));
		$('appsToggleBtn').style.display = '';

		// Initialize credential manager
		const credMgr = new CredentialManager(serverUrl);
		credMgr.init();

		// Connect WebSocket
		client.connectWebSocket();
		setupClientEvents();

		// Initialize workflow surface and current space
		visualizer.initEmptyWorkflow();
		await refreshSpaceList(true);

		_syncSpaceControls();
		$('singleImportBtn').disabled = false;
		$('singlePasteBtn').disabled = false;
		$('singleDownloadBtn').disabled = false;
		$('singleCopyBtn').disabled = false;
		enableStart(true);

		addLog('success', `✅ Connected to ${serverUrl}`);

		// Refresh channel summary in left panel
		if (typeof NumelChannels !== 'undefined') NumelChannels.refreshSummary();
	} catch (error) {
		console.error('Connection error:', error);
		addLog('error', `❌ Connection failed: ${error.message}`);
		setWsStatus('disconnected');
		client = null;
		throw error;  // propagate to autoConnect for retry
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

	consoleManager?.destroy();
	consoleManager = null;
	$('consoleToggleBtn').style.display = 'none';

	if (client) {
		client.disconnectWebSocket();
		client = null;
	}

	api = null;
	window._numelAPI = null;

	// Clear graph
	schemaGraph.api.graph.clear();
	schemaGraph.api.view.reset();

	visualizer.currentWorkflow = null;
	visualizer.currentWorkflowName = null;
	visualizer.graphNodes = [];

	currentExecutionId = null;
	currentPlatformExecutionId = null;
	currentSpaceId = null;
	currentSpaceInfo = null;
	currentWorkflowHasContent = false;

	$('spaceSelect').disabled = true;
	$('spaceSelect').innerHTML = '<option value="">Loading spaces...</option>';
	_syncSpaceControls();

	enableStart(false);
	$('cancelBtn').disabled = true;
	_setWorkflowName(null);
	
	setWsStatus('disconnected');
	setExecStatus('idle', 'Not running');
	$('execId').textContent = '-';
	_updateStarterExperience(false);

	addLog('info', '🔌 Disconnected');
}

function setupClientEvents() {
	client.on('ws:connected', () => {
		setWsStatus('connected');
		addLog('success', '🔗 WebSocket connected');
		_updateStarterExperience(false);
	});

	client.on('ws:disconnected', () => {
		setWsStatus('disconnected');
		addLog('warning', '🔌 WebSocket disconnected');
		_updateStarterExperience(false);
	});

	client.on('workflow.started', (event) => {
		if (currentExecutionId !== event.execution_id) return;
		setExecStatus('running', 'Running');
		const shownId = currentPlatformExecutionId || event.execution_id;
		$('execId').textContent = shownId.substring(0, 8) + '...';
		enableStart(false);
		visualizer?.clearNodeStates();

		// LOCK GRAPH during execution
		schemaGraph.api.lock.lock('Workflow running');
		schemaGraph.eventBus.emit('workflow:started', event);

		addLog('info', `▶️ Workflow started`);
	});

	client.on('workflow.completed', (event) => {
		if (event.execution_id !== currentExecutionId) return;
		currentExecutionId = null;
		currentPlatformExecutionId = null;
		setExecStatus('completed', 'Completed');
		enableStart(true);

		// UNLOCK GRAPH after completion
		schemaGraph.api.lock.unlock();
		schemaGraph.eventBus.emit('workflow:completed', event);

		addLog('success', `✅ Workflow completed`);
	});

	client.on('workflow.failed', (event) => {
		if (event.execution_id !== currentExecutionId) return;
		currentExecutionId = null;
		currentPlatformExecutionId = null;
		setExecStatus('failed', 'Failed');
		enableStart(true);

		// UNLOCK GRAPH after failure
		schemaGraph.api.lock.unlock();
		schemaGraph.eventBus.emit('workflow:failed', event);

		addLog('error', `❌ Workflow failed: ${event.error || 'Unknown error'}`);
	});

	client.on('workflow.cancelled', (event) => {
		if (event.execution_id !== currentExecutionId) return;
		currentExecutionId = null;
		currentPlatformExecutionId = null;
		setExecStatus('idle', 'Cancelled');
		enableStart(true);

		// Close any pending user-input dialog
		closeModal();

		// Clear all node execution states (spinners, colors)
		visualizer?.clearNodeStates();

		// UNLOCK GRAPH after cancellation
		schemaGraph.api.lock.unlock();
		schemaGraph.eventBus.emit('workflow:cancelled', event);

		addLog('warning', `⏹️ Workflow cancelled`);
	});

	client.on('workspace.changed', async (event) => {
		// Agent modified the current workflow — reload it from the server
		try {
			const resp = await api.getWorkflow();
			if (resp?.workflow) {
				await visualizer?.loadWorkflow(resp.workflow, resp.name || visualizer?.currentWorkflowName || 'Workflow');
				addLog('info', `🔄 Current workflow updated by assistant`);
			}
		} catch (e) {
			addLog('warning', `⚠️ workflow reload failed after workspace.changed — ${e}`);
		}
	});

	// ── Execution event buffering ──────────────────────────────
	// Events may arrive via WebSocket before the /start POST returns
	// and sets currentExecutionId.  Buffer them and replay once the
	// id is known.
	const _execEventTypes = new Set([
		'node.started', 'node.completed', 'node.failed',
		'node.waiting', 'node.resumed', 'user_input.requested',
		'workflow.completed', 'workflow.failed', 'workflow.cancelled',
		'variable.changed',
	]);

	// Intercept ALL workflow events for buffering
	client.on('workflow:event', (event) => {
		if (!event.event_type || !_execEventTypes.has(event.event_type)) return;
		if (!currentExecutionId && _pendingExecEvents !== null) {
			_pendingExecEvents.push(event);
		}
	});

	client.on('node.started', (event) => {
		if (event.execution_id !== currentExecutionId) return;
		const idx = parseInt(event.node_id);
		const label = event.data?.node_label || `Node ${idx}`;
		visualizer?.updateNodeState(idx, 'running');
		// Clear any previous error text when the node re-runs
		try {
			const graphNode = visualizer?.graphNodes[idx];
			if (graphNode) graphNode.executionErrorText = null;
		} catch (_e) {}
		addLog('info', `▶️ [${idx}] ${label}`);
	});

	client.on('node.completed', (event) => {
		if (event.execution_id !== currentExecutionId) return;
		const idx = parseInt(event.node_id);
		const label = event.data?.node_label || `Node ${idx}`;
		const outputs = event.data?.outputs;
		visualizer?.updateNodeState(idx, 'completed');
		if (outputs) {
			storeNodeOutputs(idx, outputs);
			updateConnectedPreviews(idx, outputs);
			agentChatManager?.notifyInputsChanged();
			// Store edge data for wire tooltip (Task 2)
			try {
				const graphNode = visualizer?.graphNodes[idx];
				if (graphNode) {
					_edgeDataStore = _edgeDataStore || {};
					for (const [fieldName, value] of Object.entries(outputs)) {
						_edgeDataStore[`${idx}:${fieldName}`] = value;
					}
				}
			} catch (_e) {}
		}
		addLog('success', `✅ [${idx}] ${label}`);
	});

	client.on('node.failed', (event) => {
		if (event.execution_id !== currentExecutionId) return;
		const idx = parseInt(event.node_id);
		const label = event.data?.node_label || `Node ${idx}`;
		visualizer?.updateNodeState(idx, 'failed');
		// Store error text on the graph node so the header tooltip can display it
		try {
			const graphNode = visualizer?.graphNodes[idx];
			if (graphNode) {
				graphNode.executionErrorText = event.error || null;
			}
		} catch (_e) {}
		addLog('error', `❌ [${idx}] ${label}: ${event.error}`);
	});

	client.on('node.waiting', (event) => {
		if (event.execution_id !== currentExecutionId) return;
		const idx = parseInt(event.node_id);
		const label = event.data?.node_label || `Node ${idx}`;
		const waitType = event.data?.wait_type || 'unknown';
		visualizer?.updateNodeState(idx, 'waiting');
		addLog('info', `⏳ [${idx}] ${label} waiting (${waitType})`);

		// Auto-activate agent chat when engine reaches it
		if (waitType === 'agent_chat' && agentChatManager) {
			const graphNode = visualizer?.graphNodes[idx];
			if (graphNode) {
				agentChatManager.activateForExecution(graphNode, event.data?.request);
			}
		}
	});

	client.on('node.resumed', (event) => {
		if (event.execution_id !== currentExecutionId) return;
		const idx = parseInt(event.node_id);
		const label = event.data?.node_label || `Node ${idx}`;
		visualizer?.updateNodeState(idx, 'running');
		addLog('info', `▶️ [${idx}] ${label} resumed`);
	});

	client.on('user_input.requested', (event) => {
		if (!currentExecutionId || event.execution_id !== currentExecutionId) return;
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

async function refreshSpaceList(loadWorkflow = false) {
	if (!api) return;

	try {
		const currentResp = await api.getCurrentSpace();
		const listResp = await api.listSpaces();
		const spaces = listResp.spaces || [];
		currentSpaceInfo = currentResp.space || spaces.find(space => space.id === listResp.current_space_id) || null;
		currentSpaceId = currentSpaceInfo?.id || listResp.current_space_id || null;

		const select = $('spaceSelect');
		select.innerHTML = '';
		for (const space of spaces) {
			const option = document.createElement('option');
			option.value = space.id;
			option.textContent = space.title || space.slug || space.id;
			select.appendChild(option);
		}
		if (currentSpaceId) select.value = currentSpaceId;
		_syncSpaceControls();

		if (loadWorkflow) {
			await loadCurrentWorkflow();
		}
		_updateWorkbenchOverview();
	} catch (error) {
		addLog('error', `❌ Failed to refresh spaces: ${error.message}`);
		_updateWorkbenchOverview();
	}
}

async function loadCurrentWorkflow() {
	if (!api) return;

	try {
		const response = await api.getWorkflow();
		const workflow = response?.workflow || null;
		const name = response?.name || 'Untitled';

		// Close transient overlays before replacing the graph.
		schemaGraph.closeAllPreviewTextOverlays?.();
		agentChatManager?.disconnectAll();

		currentExecutionId = null;
		currentPlatformExecutionId = null;
		$('execId').textContent = '-';
		setExecStatus('idle', 'Not running');

		currentWorkflowHasContent = _hasWorkflowContent(workflow);

		if (workflow) {
			const loaded = visualizer.loadWorkflow(workflow, name);
			if (!loaded) throw new Error('Failed to load workflow into graph');
			addLog('success', `✅ Loaded "${name}"`);
		} else {
			schemaGraph.api.graph.clear();
			schemaGraph.api.view.reset();
			visualizer.initEmptyWorkflow();
			visualizer.graphNodes = [];
			_setWorkflowName(name);
			addLog('info', currentSpaceInfo?.title
				? `🧭 "${currentSpaceInfo.title}" is ready for a workflow`
				: '🧭 Current space is ready for a workflow');
		}

		workflowDirty = false;
		enableStart(true);
		updateClearButtonState();
		_updateStarterExperience(!currentWorkflowHasContent);
		_updateWorkbenchOverview();
	} catch (error) {
		addLog('error', `❌ Failed to load workflow: ${error.message}`);
		_updateWorkbenchOverview();
	}
}

async function createSpace() {
	if (!api) return;
	const title = await NumelPrompt(
		'Create Space',
		'Choose a name for the new space.',
		'New Space',
		'Create',
		'New Space'
	);
	if (title === null || !title.trim()) return;

	try {
		if (workflowDirty && visualizer?.currentWorkflow) {
			await syncWorkflow();
		}
		const response = await api.createSpace(title.trim());
		currentSpaceInfo = response.space || null;
		currentSpaceId = currentSpaceInfo?.id || null;
		await refreshSpaceList(true);
		addLog('success', `✅ Created space "${currentSpaceInfo?.title || title.trim()}"`);
	} catch (error) {
		addLog('error', `❌ Failed to create space: ${error.message}`);
	}
}

async function removeCurrentSpace() {
	if (!api || !currentSpaceId || !currentSpaceInfo) return;
	const ok = await NumelConfirm(
		'Delete Space',
		`Delete space "${currentSpaceInfo.title || currentSpaceInfo.slug || currentSpaceId}"? This will remove its saved workflow from the current UI surface.`,
		'Delete',
		true
	);
	if (!ok) return;

	try {
		await api.deleteSpace(currentSpaceId);
		currentSpaceId = null;
		currentSpaceInfo = null;
		await refreshSpaceList(true);
		addLog('success', '✅ Space deleted');
	} catch (error) {
		addLog('error', `❌ Failed to delete space: ${error.message}`);
	}
}

async function selectCurrentSpace() {
	const nextSpaceId = $('spaceSelect').value;
	if (!api || !nextSpaceId || nextSpaceId === currentSpaceId) return;

	try {
		if (workflowDirty && visualizer?.currentWorkflow) {
			await syncWorkflow();
		}
		const response = await api.selectSpace(nextSpaceId);
		currentSpaceInfo = response.space || null;
		currentSpaceId = currentSpaceInfo?.id || nextSpaceId;
		await loadCurrentWorkflow();
		addLog('info', `🧭 Switched to "${currentSpaceInfo?.title || currentSpaceId}"`);
	} catch (error) {
		addLog('error', `❌ Failed to switch space: ${error.message}`);
		await refreshSpaceList(false);
	}
}

async function syncWorkflow(workflow = null, _name = null, force = false) {
	if (!force && !workflowDirty) return;

	schemaGraph.api.lock.lock('Syncing workflow', true, { lockMovement: true, lockOverlays: true });

	try {
		// Save chat state before reload
		const chatState = saveChatState();

		// Close all preview text overlays (node IDs will change)
		schemaGraph.closeAllPreviewTextOverlays?.();

		// Always re-export from graph to strip frontend-only nodes (e.g. preview_flow)
		const exported = visualizer.exportWorkflow();
		if (exported) workflow = exported;

		const response = await api.saveWorkflow(workflow);

		if (response.status === 'saved') {
			// Clear handlers (node IDs will change)
			agentChatManager?.disconnectAll();

			// Reload entire workflow from backend
			if (response.workflow) {
				visualizer.loadWorkflow(response.workflow, response.name, visualizer.defaultLayout, true);
			}

			// Restore chat messages
			restoreChatState(chatState);
			
			currentWorkflowHasContent = _hasWorkflowContent(response.workflow || workflow);
			workflowDirty = false;
			schemaGraph.eventBus.emit('workflow:synced');
			_updateStarterExperience(false);
			addLog('success', `✅ Saved "${response.name}"`);
		} else {
			throw new Error('Save failed');
		}
	} finally {
		schemaGraph.api.lock.unlock();
	}
}

// Global helper for console /gen — load + sync a workflow JSON object
window.loadAndSyncWorkflow = async function(workflow, name) {
	if (!visualizer || !schemaGraph) return;
	schemaGraph.api.graph.clear();
	schemaGraph.api.view.reset();
	const n = name || workflow?.options?.name || 'Generated Workflow';
	const loaded = visualizer.loadWorkflow(workflow, n);
	if (loaded) {
		currentWorkflowHasContent = _hasWorkflowContent(workflow);
		await syncWorkflow(workflow, null, true);
		enableStart(true);
		_updateStarterExperience(false);
		addLog('success', `✅ Loaded "${visualizer.currentWorkflowName}"`);
	}
};

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
		const name      = workflow?.options?.name || file.name.replace('.json', '');
		const validated = visualizer.loadWorkflow(workflow, name);
		if (validated) {
			await syncWorkflow(workflow, null, true);
			enableStart(true);
			addLog('success', `📂 Imported "${visualizer.currentWorkflowName}"`);
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

	schemaGraph.api.lock.lock('Pasting workflow');

	try {
		schemaGraph.api.graph.clear();
		schemaGraph.api.view.reset();

		const name = workflow?.options?.name || 'Pasted Workflow';
		const loaded = visualizer.loadWorkflow(workflow, name);
		if (loaded) {
			await syncWorkflow(workflow, null, true);
			enableStart(true);
			addLog('success', `📋 Pasted "${visualizer.currentWorkflowName}"`);
		}
		updateClearButtonState();
	} catch (err) {
		addLog('error', `❌ Failed to paste workflow: ${err.message}`);
	} finally {
		schemaGraph.api.lock.unlock();
	}
}

async function clearWorkflow() {
	if (!visualizer.currentWorkflow) return;

	try {
		schemaGraph.api.lock.lock('Clearing workflow');
		schemaGraph.closeAllPreviewTextOverlays?.();
		schemaGraph.api.graph.clear();
		schemaGraph.api.view.reset();
		visualizer.initEmptyWorkflow();
		visualizer.graphNodes = [];
		_setWorkflowName(visualizer.currentWorkflowName || 'Untitled');
		currentWorkflowHasContent = false;
		workflowDirty = true;
		await syncWorkflow(visualizer.exportWorkflow(), null, true);
		enableStart(true);
		updateClearButtonState();
		_updateStarterExperience(!_hasSeenStarterExperience());
		addLog('info', '🧹 Workflow cleared');
	} finally {
		schemaGraph.api.lock.unlock();
	}
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

		await syncWorkflow();

		const workflowName = visualizer.currentWorkflowName;
		addLog('info', `⏳ Starting "${workflowName}"...`);

		// Collect execution options from panel
		const initialData = collectExecOptions();

		// Start buffering events before the POST so nothing is lost
		_pendingExecEvents = [];

		const response = await api.startWorkflow(initialData);

		if (response.status !== 'started') {
			_pendingExecEvents = [];
			throw new Error('Failed to start workflow');
		}

		currentExecutionId = response.execution_id;
		currentPlatformExecutionId = response.platform_execution_id || response.execution_id;

		// Replay any events that arrived during the POST
		_flushPendingExecEvents();

	} catch (error) {
		_pendingExecEvents = [];
		currentExecutionId = null;
		currentPlatformExecutionId = null;
		enableStart(true);
		addLog('error', `❌ Start failed: ${error.message}`);
	}
}

function _flushPendingExecEvents() {
	if (!_pendingExecEvents || !_pendingExecEvents.length) { _pendingExecEvents = []; return; }
	const buffered = _pendingExecEvents;
	_pendingExecEvents = [];
	for (const event of buffered) {
		if (event.execution_id === currentExecutionId) {
			// Re-emit so the individual handlers pick it up
			client.emit(event.event_type, event);
		}
	}
}

// ========================================================================
// Options Panel Population
// ========================================================================

function populateWorkflowOptionsPanel() {
	const form = $('workflowOptionsForm');
	if (!form) return;
	form.innerHTML = '';

	// Always add workflow name input as first field
	{
		const nameDiv = document.createElement('div');
		nameDiv.className = 'nw-field';
		const nameLabel = document.createElement('label');
		nameLabel.textContent = 'Name';
		nameLabel.setAttribute('for', 'wfOpt_name');
		nameDiv.appendChild(nameLabel);
		const nameInput = document.createElement('input');
		nameInput.type = 'text';
		nameInput.id = 'wfOpt_name';
		nameInput.className = 'nw-input';
		nameInput.autocomplete = 'off';
		nameInput.placeholder = 'Workflow name...';
		nameInput.value = visualizer?.currentWorkflowName || '';
		nameInput.addEventListener('blur', () => {
			const newName = nameInput.value.trim();
			if (newName) {
				_setWorkflowName(newName);
				visualizer?.setWorkflowOptions({ name: newName });
			}
		});
		nameInput.addEventListener('keydown', (e) => {
			if (e.key === 'Enter') nameInput.blur();
		});
		nameDiv.appendChild(nameInput);
		form.appendChild(nameDiv);
	}

	// Get workflow options schema info
	const optionsInfo = schemaGraph.api.schemaTypes.getWorkflowOptionsInfo(WORKFLOW_SCHEMA_NAME);

	if (!optionsInfo || !optionsInfo.fields) {
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
		input.autocomplete = 'off';
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
	if (!api || !currentExecutionId) return;

	try {
		$('cancelBtn').disabled = true;
		await api.cancelExecution(currentPlatformExecutionId || currentExecutionId);
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

		const result = await client.api.toolCall(toolConfig.workflowIndex, args);

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
/**
 * Store node outputs on the graph node's output slots so downstream nodes
 * (including InteractiveType nodes like agent_chat) can read them via getInputData().
 */
function storeNodeOutputs(workflowNodeIdx, outputs) {
	if (!visualizer) return;
	const graphNode = visualizer.graphNodes[workflowNodeIdx];
	if (!graphNode || !outputs || typeof outputs !== 'object') return;

	for (let slotIdx = 0; slotIdx < (graphNode.outputs || []).length; slotIdx++) {
		const metaName = graphNode.outputMeta?.[slotIdx]?.name;
		const slotName = graphNode.outputs[slotIdx].name;
		let data;

		if (metaName && metaName in outputs) {
			data = outputs[metaName];
		} else if (slotName in outputs) {
			data = outputs[slotName];
		} else {
			const baseName = (metaName || slotName).split('.')[0];
			if (baseName in outputs) data = outputs[baseName];
		}

		if (data !== undefined) {
			graphNode.setOutputData(slotIdx, data);
		}
	}
}

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
// ========================================================================
// Toolkit → ToolFlow: Dynamic method options
// ========================================================================

function _resolveAllToolkitMethods() {
	if (!schemaGraph?.graph) return;
	for (const [, link] of Object.entries(schemaGraph.graph.links)) {
		if (!link) continue;
		_onLinkChangedToolkitMethods({ link }, true);
	}
}

async function _onLinkChangedToolkitMethods(data, created) {
	if (!schemaGraph?.graph) return;
	const link = data.link || schemaGraph.graph.links[data.linkId];
	if (!link) return;

	// Identify source and target graph nodes
	const sourceNode = schemaGraph.graph.getNodeById(link.origin_id);
	const targetNode = schemaGraph.graph.getNodeById(link.target_id);
	if (!sourceNode || !targetNode) return;

	// We care about: toolkit_config → tool_flow.config
	const srcType = sourceNode.workflowType;
	const tgtType = targetNode.workflowType;
	if (tgtType !== 'tool_flow') return;

	// Check the target slot name is 'config'
	const tgtSlotName = targetNode.inputMeta?.[link.target_slot]?.name;
	if (tgtSlotName !== 'config') return;

	// Find the 'method' native input slot on the tool_flow node
	let methodSlot = null;
	for (const [idx, meta] of Object.entries(targetNode.inputMeta)) {
		if (meta.name === 'method') { methodSlot = parseInt(idx); break; }
	}
	if (methodSlot === null || !targetNode.nativeInputs?.[methodSlot]) return;

	if (!created || srcType !== 'toolkit_config') {
		// Link removed or source isn't a toolkit — clear method options
		targetNode.nativeInputs[methodSlot].options = null;
		targetNode.nativeInputs[methodSlot].optionsSource = null;
		schemaGraph.draw();
		return;
	}

	// Get toolkit name from the source node's 'name' native input
	let toolkitName = null;
	for (const [idx, meta] of Object.entries(sourceNode.inputMeta)) {
		if (meta.name === 'name' && sourceNode.nativeInputs?.[idx]) {
			toolkitName = sourceNode.nativeInputs[idx].value;
			break;
		}
	}
	if (!toolkitName) return;

	// Fetch toolkit methods from /toolkits/inspect
	try {
		const baseUrl = api?.baseUrl || $('serverUrl').value || '';
		const resp = await fetch(`${baseUrl}/toolkits/inspect`, {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ name: toolkitName }),
		});
		if (!resp.ok) return;
		const info = await resp.json();
		const methods = (info.methods || []).map(m => m.name);
		if (methods.length > 0) {
			targetNode.nativeInputs[methodSlot].options = methods;
			targetNode.nativeInputs[methodSlot].optionsSource = null;  // use static options
			schemaGraph.draw();
		}
	} catch (e) {
		console.warn('Failed to fetch toolkit methods:', e);
	}
}

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
			await api.cancelExecution(savedEvent.execution_id);
		} catch (err) {
			addLog('error', `❌ Failed to cancel execution: ${err.message}`);
		}
	}
}

async function submitUserInput() {
	if (!pendingInputEvent || !client) return;

	const input = $('userInputField').value.trim();
	if (!input) {
		await NumelAlert('Input Required', 'Please enter a value.');
		return;
	}

	// Save event reference and close the modal BEFORE the POST.
	// The server resolves the input future and may immediately emit
	// USER_INPUT_REQUESTED for the next node — if closeModal() ran
	// after the POST, it would hide that new dialog.
	const savedEvent = pendingInputEvent;
	closeModal();

	try {
		await api.provideUserInput(
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

// ============================================================================
// Task 2: Wire (edge) data tooltip
// Shows last output value when hovering near a wire on the canvas.
// ============================================================================

function initWireTooltip() {
	try {
		const canvas = schemaGraph?.canvas;
		if (!canvas) return;

		// Create the tooltip div
		const tooltip = document.createElement('div');
		tooltip.id = 'sg-wire-tooltip';
		tooltip.style.cssText = [
			'position:fixed',
			'background:rgba(0,0,0,0.88)',
			'color:#e0e0e0',
			'font-size:11px',
			'font-family:monospace',
			'padding:4px 8px',
			'border-radius:4px',
			'border:1px solid rgba(255,255,255,0.12)',
			'pointer-events:none',
			'display:none',
			'max-width:320px',
			'word-break:break-all',
			'z-index:9999',
			'white-space:pre-wrap',
		].join(';');
		document.body.appendChild(tooltip);

		let _lastHoveredLinkId = null;

		canvas.addEventListener('mousemove', (e) => {
			try {
				if (!schemaGraph || !schemaGraph.graph) return;

				const rect = canvas.getBoundingClientRect();
				const sx   = e.clientX - rect.left;
				const sy   = e.clientY - rect.top;
				const wx   = (sx - schemaGraph.camera.x) / schemaGraph.camera.scale;
				const wy   = (sy - schemaGraph.camera.y) / schemaGraph.camera.scale;

				// Find the nearest link using the app's own method
				let foundLink = null;
				if (typeof schemaGraph._findLinkAtPosition === 'function') {
					const savedDist = schemaGraph._edgePreviewConfig?.linkHitDistance;
					if (schemaGraph._edgePreviewConfig) schemaGraph._edgePreviewConfig.linkHitDistance = 8;
					foundLink = schemaGraph._findLinkAtPosition(wx, wy);
					if (schemaGraph._edgePreviewConfig && savedDist !== undefined) {
						schemaGraph._edgePreviewConfig.linkHitDistance = savedDist;
					}
				}

				if (!foundLink) {
					tooltip.style.display = 'none';
					_lastHoveredLinkId = null;
					return;
				}

				// Reposition tooltip on every frame when link is the same
				if (foundLink.id === _lastHoveredLinkId) {
					let tx = e.clientX + 14;
					let ty = e.clientY + 14;
					if (tx + 330 > window.innerWidth)  tx = e.clientX - 335;
					if (ty + 120 > window.innerHeight) ty = e.clientY - 60;
					tooltip.style.left = tx + 'px';
					tooltip.style.top  = ty + 'px';
					return;
				}
				_lastHoveredLinkId = foundLink.id;

				// Find source node's output field name
				const srcNode = schemaGraph.graph.getNodeById(foundLink.origin_id);
				if (!srcNode) { tooltip.style.display = 'none'; return; }

				const slotIdx  = foundLink.origin_slot;
				const slotName = srcNode.outputMeta?.[slotIdx]?.name
					|| srcNode.outputs?.[slotIdx]?.name
					|| null;
				const wfIdx = srcNode.workflowIndex;

				let value = undefined;
				if (wfIdx !== undefined && slotName) {
					value = _edgeDataStore[`${wfIdx}:${slotName}`];
					if (value === undefined) {
						const base = slotName.split('.')[0];
						value = _edgeDataStore[`${wfIdx}:${base}`];
					}
				}
				// Fall back to slot's stored data
				if (value === undefined && srcNode.outputs?.[slotIdx]?.data !== undefined) {
					value = srcNode.outputs[slotIdx].data;
				}

				if (value === undefined) {
					tooltip.style.display = 'none';
					return;
				}

				let display;
				try {
					display = JSON.stringify(value, null, 2);
					if (display && display.length > 280) display = display.substring(0, 280) + '...';
				} catch (_) {
					display = String(value).substring(0, 280);
				}

				tooltip.textContent = display;
				tooltip.style.display = 'block';
				let tx = e.clientX + 14;
				let ty = e.clientY + 14;
				if (tx + 330 > window.innerWidth)  tx = e.clientX - 335;
				if (ty + 120 > window.innerHeight) ty = e.clientY - 60;
				tooltip.style.left = tx + 'px';
				tooltip.style.top  = ty + 'px';
			} catch (_e) {}
		});

		canvas.addEventListener('mouseleave', () => {
			tooltip.style.display = 'none';
			_lastHoveredLinkId = null;
		});
	} catch (_e) {
		console.warn('[initWireTooltip] Error:', _e);
	}
}

// ============================================================================
// Task 3: Node search overlay (/)
// ============================================================================

function initNodeSearch() {
	try {
		const overlay  = document.getElementById('nodeSearchOverlay');
		const input    = document.getElementById('nodeSearchInput');
		const results  = document.getElementById('nodeSearchResults');
		const countEl  = document.getElementById('nodeSearchCount');
		const closeBtn = document.getElementById('nodeSearchClose');

		if (!overlay || !input) return;

		document.addEventListener('keydown', (e) => {
			const isCtrlF = (e.ctrlKey || e.metaKey) && e.key === 'f';
			const isSlash = e.key === '/' && !e.ctrlKey && !e.metaKey && !e.altKey;
			if (isCtrlF || isSlash) {
				const tag = document.activeElement?.tagName;
				if (!isCtrlF && (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT')) return;
				e.preventDefault();
				overlay.style.display = '';
				input.focus();
				input.select();
			}
			if (e.key === 'Escape' && overlay.style.display !== 'none') {
				overlay.style.display = 'none';
			}
		});

		closeBtn?.addEventListener('click', () => { overlay.style.display = 'none'; });

		input.addEventListener('input', () => {
			try {
				const q = input.value.trim().toLowerCase();
				results.innerHTML = '';
				if (!q) { countEl.textContent = ''; return; }

				const nodes = schemaGraph?.graph?.nodes || [];
				const matches = nodes.filter(n => {
					const label = (n.displayTitle || n.modelName || n.title || '').toLowerCase();
					const type  = (n.workflowType || n.modelName || n.title || '').toLowerCase();
					return label.includes(q) || type.includes(q);
				});

				countEl.textContent = `${matches.length} found`;

				matches.slice(0, 50).forEach((n) => {
					const row = document.createElement('div');
					row.className = 'sg-node-search-result';

					const typeSpan = document.createElement('span');
					typeSpan.className = 'sg-node-search-result-type';
					typeSpan.textContent = n.workflowType || n.modelName || '?';

					const labelSpan = document.createElement('span');
					labelSpan.className = 'sg-node-search-result-label';
					labelSpan.textContent = n.displayTitle || n.modelName || n.title || `node ${n.id}`;

					row.appendChild(typeSpan);
					row.appendChild(labelSpan);

					row.addEventListener('click', () => {
						overlay.style.display = 'none';
						_jumpToNode(n);
					});

					results.appendChild(row);
				});
			} catch (_e) {}
		});
	} catch (_e) {
		console.warn('[initNodeSearch] Error:', _e);
	}
}

function _jumpToNode(node) {
	try {
		if (!schemaGraph || !node) return;
		const x = (node.pos?.[0] ?? 0) + (node.size?.[0] ?? 160) / 2;
		const y = (node.pos?.[1] ?? 0) + (node.size?.[1] ?? 80)  / 2;
		schemaGraph.camera.x = schemaGraph.canvas.width  / 2 - x * schemaGraph.camera.scale;
		schemaGraph.camera.y = schemaGraph.canvas.height / 2 - y * schemaGraph.camera.scale;
		schemaGraph.draw();
		// Highlight via selection then clear after a moment
		if (typeof schemaGraph.selectNode === 'function') {
			schemaGraph.selectNode(node, false);
			setTimeout(() => {
				if (schemaGraph.selectedNode === node) schemaGraph.clearSelection?.();
			}, 1800);
		}
	} catch (_e) {}
}

// ============================================================================
// Task 5: Mini-map
// ============================================================================

function initMinimap() {
	try {
		const minimapCanvas = document.getElementById('sg-minimap');
		if (!minimapCanvas) return;

		const ctx = minimapCanvas.getContext('2d');
		const W = 160;
		const H = 100;
		minimapCanvas.width  = W * devicePixelRatio;
		minimapCanvas.height = H * devicePixelRatio;
		ctx.scale(devicePixelRatio, devicePixelRatio);

		function renderMinimap() {
			try {
				ctx.clearRect(0, 0, W, H);

				const nodes = schemaGraph?.graph?.nodes;
				if (!nodes || nodes.length === 0) return;

				// Compute bounding box of all nodes
				let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
				for (const n of nodes) {
					const x = n.pos?.[0] ?? 0;
					const y = n.pos?.[1] ?? 0;
					const w = n.size?.[0] ?? 160;
					const h = n.size?.[1] ?? 80;
					if (x     < minX) minX = x; if (y     < minY) minY = y;
					if (x + w > maxX) maxX = x+w; if (y + h > maxY) maxY = y+h;
				}

				const pad    = 20;
				const bw     = maxX - minX + pad * 2;
				const bh     = maxY - minY + pad * 2;
				const scaleF = Math.min(W / bw, H / bh);
				const ox     = (W - bw * scaleF) / 2 - (minX - pad) * scaleF;
				const oy     = (H - bh * scaleF) / 2 - (minY - pad) * scaleF;

				// Draw edges
				const links = schemaGraph?.graph?.links || {};
				ctx.strokeStyle = 'rgba(255,255,255,0.15)';
				ctx.lineWidth   = 0.7;
				for (const linkId in links) {
					const lk  = links[linkId];
					const src = schemaGraph.graph.getNodeById(lk.origin_id);
					const tgt = schemaGraph.graph.getNodeById(lk.target_id);
					if (!src || !tgt) continue;
					const sx = (src.pos[0] + src.size[0]) * scaleF + ox;
					const sy = (src.pos[1] + src.size[1] / 2) * scaleF + oy;
					const tx = tgt.pos[0] * scaleF + ox;
					const ty = (tgt.pos[1] + tgt.size[1] / 2) * scaleF + oy;
					ctx.beginPath();
					ctx.moveTo(sx, sy);
					ctx.lineTo(tx, ty);
					ctx.stroke();
				}

				// Draw nodes
				const stateColors = {
					running   : 'rgba(128,90,213,0.65)',
					completed : 'rgba(56,161,105,0.65)',
					failed    : 'rgba(229,62,62,0.65)',
					waiting   : 'rgba(214,158,46,0.65)',
				};
				for (const n of nodes) {
					const nx = n.pos[0] * scaleF + ox;
					const ny = n.pos[1] * scaleF + oy;
					const nw = Math.max((n.size?.[0] ?? 160) * scaleF, 2);
					const nh = Math.max((n.size?.[1] ?? 80)  * scaleF, 2);
					ctx.fillStyle   = stateColors[n.executionState] || 'rgba(45,90,123,0.55)';
					ctx.strokeStyle = 'rgba(100,160,220,0.5)';
					ctx.lineWidth   = 0.5;
					ctx.beginPath();
					if (ctx.roundRect) { ctx.roundRect(nx, ny, nw, nh, 1.5); }
					else { ctx.rect(nx, ny, nw, nh); }
					ctx.fill();
					ctx.stroke();
				}

				// Viewport rect
				const cam = schemaGraph?.camera;
				if (cam) {
					const cw = schemaGraph.canvas.width  / devicePixelRatio;
					const ch = schemaGraph.canvas.height / devicePixelRatio;
					const vpx = (-cam.x / cam.scale) * scaleF + ox;
					const vpy = (-cam.y / cam.scale) * scaleF + oy;
					const vpw = (cw / cam.scale) * scaleF;
					const vph = (ch / cam.scale) * scaleF;
					ctx.strokeStyle = 'rgba(255,210,60,0.7)';
					ctx.lineWidth   = 1;
					ctx.strokeRect(vpx, vpy, vpw, vph);
				}
			} catch (_e) {}
		}

		setInterval(renderMinimap, 100);

		// Click on minimap to navigate
		minimapCanvas.addEventListener('click', (e) => {
			try {
				const rect  = minimapCanvas.getBoundingClientRect();
				const nodes = schemaGraph?.graph?.nodes;
				if (!nodes || nodes.length === 0) return;

				let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
				for (const n of nodes) {
					const x = n.pos?.[0] ?? 0; const y = n.pos?.[1] ?? 0;
					const w = n.size?.[0] ?? 160; const h = n.size?.[1] ?? 80;
					if (x     < minX) minX = x; if (y     < minY) minY = y;
					if (x + w > maxX) maxX = x+w; if (y + h > maxY) maxY = y+h;
				}
				const pad    = 20;
				const bw     = maxX - minX + pad * 2;
				const bh     = maxY - minY + pad * 2;
				const scaleF = Math.min(W / bw, H / bh);
				const ox     = (W - bw * scaleF) / 2 - (minX - pad) * scaleF;
				const oy     = (H - bh * scaleF) / 2 - (minY - pad) * scaleF;

				const mx     = e.clientX - rect.left;
				const my     = e.clientY - rect.top;
				const worldX = (mx - ox) / scaleF;
				const worldY = (my - oy) / scaleF;

				const cam = schemaGraph.camera;
				cam.x = schemaGraph.canvas.width  / 2 - worldX * cam.scale;
				cam.y = schemaGraph.canvas.height / 2 - worldY * cam.scale;
				schemaGraph.draw();
			} catch (_e) {}
		});
	} catch (_e) {
		console.warn('[initMinimap] Error:', _e);
	}
}

// ============================================================================
// Task 6: Node Groups (Ctrl+G)
// ============================================================================

function initNodeGroups() {
	try {
		document.addEventListener('keydown', (e) => {
			if ((e.ctrlKey || e.metaKey) && e.key === 'g') {
				const tag = document.activeElement?.tagName;
				if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return;
				e.preventDefault();
				NumelPrompt('Create Group', 'Choose a label for this node group.', 'Group', 'Create', 'Group')
					.then((name) => {
						if (name !== null) createNodeGroup(name);
					});
			}
		});
		// Refresh groups at ~10fps
		setInterval(renderNodeGroups, 100);
	} catch (_e) {
		console.warn('[initNodeGroups] Error:', _e);
	}
}

function createNodeGroup(label) {
	try {
		const selected = schemaGraph ? Array.from(schemaGraph.selectedNodes || []) : [];
		if (!selected || selected.length < 2) {
			NumelAlert('Create Group', 'Select at least 2 nodes to create a group.');
			return;
		}
		_nodeGroups.push({
			id      : 'grp_' + Date.now(),
			label   : label || 'Group',
			nodeIds : selected.map(n => n.id),
		});
		renderNodeGroups();
	} catch (_e) {
		console.warn('[createNodeGroup] Error:', _e);
	}
}

function renderNodeGroups() {
	try {
		document.querySelectorAll('.sg-node-group').forEach(el => el.remove());
		if (_nodeGroups.length === 0) return;

		const container = schemaGraph?.canvas?.parentElement;
		if (!container) return;
		const cam = schemaGraph?.camera;
		if (!cam) return;

		for (const grp of _nodeGroups) {
			const nodes = (schemaGraph?.graph?.nodes || [])
				.filter(n => grp.nodeIds.includes(n.id));
			if (nodes.length === 0) continue;

			let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
			for (const n of nodes) {
				const x = n.pos?.[0] ?? 0; const y = n.pos?.[1] ?? 0;
				const w = n.size?.[0] ?? 160; const h = n.size?.[1] ?? 80;
				if (x - 12     < minX) minX = x - 12;
				if (y - 28     < minY) minY = y - 28;
				if (x + w + 12 > maxX) maxX = x + w + 12;
				if (y + h + 12 > maxY) maxY = y + h + 12;
			}

			const z  = cam.scale ?? 1;
			const el = document.createElement('div');
			el.className = 'sg-node-group';
			el.style.left   = `${minX * z + (cam.x ?? 0)}px`;
			el.style.top    = `${minY * z + (cam.y ?? 0)}px`;
			el.style.width  = `${(maxX - minX) * z}px`;
			el.style.height = `${(maxY - minY) * z}px`;

			const lbl = document.createElement('div');
			lbl.className   = 'sg-node-group-label';
			lbl.textContent = grp.label;
			el.appendChild(lbl);
			container.appendChild(el);
		}
	} catch (_e) {}
}

// ============================================================================
// Credential Manager
// ============================================================================

class CredentialManager {
	constructor(serverUrl) {
		this._base = serverUrl;
		this._names = [];
	}

	_canManage() {
		return _isAuthenticatedUser();
	}

	_headers(includeJson = false) {
		const headers = {};
		if (includeJson) headers['Content-Type'] = 'application/json';
		const token = window._numelToken || localStorage.getItem('numel_token');
		if (token) headers['Authorization'] = `Bearer ${token}`;
		const sessionId = window._numelAPI?.sessionId || sessionStorage.getItem('numel_session_id');
		if (sessionId) headers['X-Session-Id'] = sessionId;
		return headers;
	}

	_syncAccess() {
		return _renderCredentialAccessState();
	}

	async init() {
		if (this._syncAccess()) {
			await this._refresh();
		} else {
			this._render();
		}
		this._bindEvents();
		// Poll tunnel URL until available (only if server started with --tunnel)
		this._pollTunnel();
	}

	async _refresh() {
		if (!this._syncAccess()) {
			this._names = [];
			this._render();
			return;
		}
		try {
			const r = await fetch(`${this._base}/credentials`, {
				method: 'POST',
				headers: this._headers(),
			});
			if (!r.ok) throw new Error(`${r.status}`);
			const d = await r.json();
			this._names = d.names || [];
		} catch (_) { this._names = []; }
		this._render();
	}

	_render() {
		const list = $('credentialsList');
		if (!list) return;
		if (!this._syncAccess()) return;
		if (!this._names.length) {
			list.innerHTML = '<div class="nw-credentials-empty">No credentials stored</div>';
			return;
		}
		list.innerHTML = this._names.map(name => `
			<div class="nw-credential-item">
				<span class="nw-credential-name" title="Reference as \${${name}}">${name}</span>
				<span class="nw-credential-hint">\${${name}}</span>
				<div class="nw-credential-actions">
					<button class="nw-btn-icon nw-cred-edit" data-name="${name}" title="Edit">✎</button>
					<button class="nw-btn-icon nw-cred-delete" data-name="${name}" title="Delete">✕</button>
				</div>
			</div>`).join('');
	}

	_bindEvents() {
		const addBtn    = $('addCredentialBtn');
		const form      = $('credentialForm');
		const nameInput = $('credentialName');
		const valInput  = $('credentialValue');
		const saveBtn   = $('saveCredentialBtn');
		const cancelBtn = $('cancelCredentialBtn');
		const list      = $('credentialsList');

		const showForm = (name = '') => {
			nameInput.value = name;
			valInput.value  = '';
			form.style.display = 'flex';
			(name ? valInput : nameInput).focus();
		};
		const hideForm = () => { form.style.display = 'none'; };

		addBtn?.addEventListener('click', (e) => { e.stopPropagation(); showForm(); });
		cancelBtn?.addEventListener('click', hideForm);

		saveBtn?.addEventListener('click', async () => {
			if (!this._canManage()) return;
			const raw  = nameInput.value.trim();
			const name = raw.replace(/\s+/g, '_').toUpperCase();
			const val  = valInput.value;
			if (!name) return;
			await fetch(`${this._base}/credentials/${encodeURIComponent(name)}`, {
				method: 'POST',
				headers: this._headers(true),
				body: JSON.stringify({ value: val }),
			});
			hideForm();
			await this._refresh();
		});

		nameInput?.addEventListener('keydown', (e) => { if (e.key === 'Enter') valInput?.focus(); });
		valInput?.addEventListener('keydown',  (e) => { if (e.key === 'Enter') saveBtn?.click(); });

		list?.addEventListener('click', async (e) => {
			if (!this._canManage()) return;
			const edit = e.target.closest('.nw-cred-edit');
			const del  = e.target.closest('.nw-cred-delete');
			if (edit) { showForm(edit.dataset.name); }
			if (del) {
				await fetch(`${this._base}/credentials/${encodeURIComponent(del.dataset.name)}`, {
					method: 'DELETE',
					headers: this._headers(),
				});
				await this._refresh();
			}
		});
	}

	async _pollTunnel() {
		const info   = $('tunnelInfo');
		const urlEl  = $('tunnelUrl');
		if (!info || !urlEl) return;
		for (let i = 0; i < 20; i++) {
			await new Promise(r => setTimeout(r, 3000));
			try {
				const r = await fetch(`${this._base}/tunnel/url`, { method: 'POST' });
				const d = await r.json();
				if (d.url) {
					urlEl.textContent = d.url;
					urlEl.href        = d.url;
					info.style.display = 'flex';
					return;
				}
			} catch (_) {}
		}
	}
}

// ============================================================================
// END: Frontend editor enhancements
// ============================================================================
