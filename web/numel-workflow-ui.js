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
let availableSpaces   = [];
let _pendingExecEvents = [];   // buffer events arriving before currentExecutionId is set
let workflowDirty      = true;
let fileUploadManager  = null;
let consoleManager     = null;
let galleryManager     = null;
let appsManager        = null;
let api                = null;  // NumelAPI instance, shared across all managers
let currentWorkflowHasContent = false;
let _supportedBackends = ['agno'];
let _executionReplayView = null;
let _latestReplayExecutionId = null;
const _executionReplayCache = new Map();
let _executionComparisonView = null;
let _executionEvalView = null;
let _executionFailureView = null;

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
	repo: 'repo_file_assistant',
	miniapp: 'publishable_mini_app_starter',
	support: 'assistant_support_workbench',
	ops: 'assistant_ops_workbench',
});
const STARTER_ASSISTANT_PROMPT = '/gen A workflow that asks the user for input, transforms it into a short helpful response, and previews the result.';
const STARTER_FOLLOWTHROUGH_CONFIGS = Object.freeze({
	hello: {
		title: 'Quick start is ready',
		summary: 'Run it once to see the full edit-save-run loop, then ask the assistant to adapt it into your real first workflow.',
		assistantPrompt: 'Review the current workflow and adapt it into a more useful starter for my real task. Keep it compact, runnable, and easy to understand.',
		actions: ['run', 'assistant', 'gallery'],
	},
	research: {
		title: 'Research starter loaded',
		summary: 'Run the workflow to inspect the reporting path, then refine it with the assistant for your own research process.',
		assistantPrompt: 'Review the current research workflow and suggest the smallest set of changes to make it more useful for my own research and reporting workflow.',
		actions: ['run', 'assistant', 'gallery'],
	},
	media: {
		title: 'Webcam starter loaded',
		summary: 'Run it once to confirm browser media access, then tailor the flow if you want a more specific capture or analysis workflow.',
		assistantPrompt: 'Review the current browser-media workflow and help me adapt it for my real camera or media use case while keeping it easy to run locally.',
		actions: ['run', 'assistant', 'gallery'],
	},
	repo: {
		title: 'Repo assistant ready',
		summary: 'Run it to inspect the current workspace and file-access flow, then refine it for the repo or project questions you want to answer first.',
		assistantPrompt: 'Review the current repo and file assistant starter and suggest the smallest set of changes to make it more useful for my actual project or repository.',
		actions: ['run', 'assistant', 'gallery'],
	},
	miniapp: {
		title: 'Mini app starter ready',
		summary: 'Run it once to inspect the end-user flow, then open Published Apps when you are ready to turn it into a lightweight standalone app.',
		assistantPrompt: 'Review the current publishable mini app starter and suggest the smallest set of changes to make it more useful and polished before I publish it.',
		actions: ['run', 'assistant', 'apps'],
	},
	support: {
		title: 'Support workbench ready',
		summary: 'Run the workbench to inspect the assistant flow, then open Assistant Deployments when you are ready to bind it to channels and specialist handoffs.',
		assistantPrompt: 'Review the current support workbench and propose the smallest set of improvements before I connect it to a real assistant deployment and channel.',
		actions: ['run', 'assistant', 'deployments'],
	},
	ops: {
		title: 'Ops workbench ready',
		summary: 'Run the workbench to inspect the operator path, then open Assistant Deployments when you are ready to add proactive tasks or bind channels.',
		assistantPrompt: 'Review the current ops workbench and propose the smallest set of improvements before I use it for proactive operational assistant deployments.',
		actions: ['run', 'assistant', 'deployments'],
	},
});
let _starterFollowthroughState = null;
const GLOBAL_LAYOUT_PRESET_STORAGE_KEY = 'numel_global_layout_preset_v1';
const PANEL_COLLAPSED_STORAGE_KEY = 'numel_left_panel_collapsed_v1';
const SECTION_COLLAPSE_STORAGE_KEY = 'numel_left_panel_section_state_v1';
const ADVANCED_VISIBLE_STORAGE_KEY = 'numel_show_advanced_v1';
const GLOBAL_LAYOUT_PRESETS = Object.freeze([
	'workbench',
	'project-workbench',
	'project-workbench-assistant',
	'project-workbench-canvas',
	'project-workbench-studio',
]);

// Layouts that dock the Numel Assistant below the canvas. These share the
// 'project-workbench' base class so all existing workbench styling still
// applies, and add 'nw-layout-assistant-dock' as a modifier.
const ASSISTANT_DOCK_LAYOUTS = new Set(['workbench', 'project-workbench-assistant', 'project-workbench-studio']);

function _currentWorkflowLabel() {
	return visualizer?.currentWorkflowName || $('singleWorkflowName')?.textContent || 'Workflow';
}

function _escHtml(value) {
	return String(value ?? '')
		.replace(/&/g, '&amp;')
		.replace(/</g, '&lt;')
		.replace(/>/g, '&gt;')
		.replace(/"/g, '&quot;')
		.replace(/'/g, '&#39;');
}

function _slugFromTitle(value, fallback = 'space') {
	const text = String(value || '')
		.trim()
		.toLowerCase()
		.replace(/[^a-z0-9._-]+/g, '-')
		.replace(/^-+|-+$/g, '');
	return text || fallback;
}

function _formatLocalTimestamp(value) {
	const num = Number(value);
	const date = Number.isFinite(num) ? new Date(num * 1000) : new Date(value);
	if (!(date instanceof Date) || Number.isNaN(date.getTime())) return 'Unknown time';
	return date.toLocaleString();
}

function _extractWorkflowDisplayName(workflow = null) {
	if (!workflow || typeof workflow !== 'object') return '';
	const options = workflow.options;
	if (options && typeof options === 'object') {
		return _sanitizeExecutionWorkflowLabel(options.name || '');
	}
	return '';
}

function _hideStarterFollowthrough() {
	const card = $('starterFollowthrough');
	if (!card || card.style.display === 'none') return;
	card.style.display = 'none';
	_starterFollowthroughState = null;
	_pumpCanvasLayoutRefresh();
}

function _showStarterFollowthrough(starterKey) {
	const config = STARTER_FOLLOWTHROUGH_CONFIGS[starterKey];
	const card = $('starterFollowthrough');
	const titleEl = $('starterFollowthroughTitle');
	const summaryEl = $('starterFollowthroughSummary');
	const actionsEl = $('starterFollowthroughActions');
	if (!config || !card || !titleEl || !summaryEl || !actionsEl) return;
	const actionMap = {
		run: { label: 'Run Now', className: 'nw-btn nw-btn-success' },
		assistant: { label: 'Refine With Assistant', className: 'nw-btn nw-btn-secondary' },
		deployments: { label: 'Open Assistant Deployments', className: 'nw-btn nw-btn-secondary' },
		apps: { label: 'Open Published Apps', className: 'nw-btn nw-btn-secondary' },
		gallery: { label: 'Browse More Starters', className: 'nw-btn nw-btn-secondary' },
	};
	titleEl.textContent = config.title;
	summaryEl.textContent = config.summary;
	actionsEl.innerHTML = '';
	for (const actionId of config.actions || []) {
		const meta = actionMap[actionId];
		if (!meta) continue;
		const btn = document.createElement('button');
		btn.type = 'button';
		btn.className = meta.className;
		btn.textContent = meta.label;
		btn.setAttribute('data-guide-action', actionId);
		actionsEl.appendChild(btn);
	}
	_starterFollowthroughState = {
		starterKey,
		assistantPrompt: config.assistantPrompt || '',
	};
	card.style.display = '';
	_pumpCanvasLayoutRefresh();
}

async function _handleStarterFollowthroughAction(actionId) {
	try {
		switch (actionId) {
			case 'run':
				if ($('startBtn')?.disabled) throw new Error('This workflow is not ready to run yet.');
				$('startBtn')?.click();
				addLog('info', '▶ Started the current starter workflow');
				break;
			case 'assistant':
				if (!consoleManager) throw new Error('Assistant is not ready yet');
				await consoleManager.launchStarterPrompt(
					_starterFollowthroughState?.assistantPrompt || 'Review the current workflow and help me improve it.',
					{ enablePlanner: false, autoSend: false },
				);
				addLog('info', '🤖 Assistant opened with a refinement prompt for the current starter');
				break;
			case 'deployments':
				if (typeof NumelAssistantDeployments === 'undefined') throw new Error('Assistant Deployments is not available yet');
				NumelAssistantDeployments.open();
				addLog('info', '🧭 Opened Assistant Deployments');
				break;
			case 'apps':
				if (!appsManager) throw new Error('Published Apps is not ready yet');
				await appsManager.open();
				addLog('info', '📦 Opened Published Apps');
				break;
			case 'gallery':
				if (!galleryManager) throw new Error('Gallery is not ready yet');
				await galleryManager.open();
				addLog('info', '🖼 Opened workflow gallery');
				break;
			default:
				return;
		}
		_hideStarterFollowthrough();
	} catch (error) {
		addLog('error', `❌ Starter guide action failed: ${error.message}`);
		await NumelAlert('Starter Guide', error.message || 'Failed to continue from starter guide.');
	}
}

function _readJsonStorage(key, fallback = {}) {
	try {
		const raw = localStorage.getItem(key);
		if (!raw) return fallback;
		const parsed = JSON.parse(raw);
		return parsed && typeof parsed === 'object' ? parsed : fallback;
	} catch {
		return fallback;
	}
}

function _writeJsonStorage(key, value) {
	try {
		localStorage.setItem(key, JSON.stringify(value));
	} catch {}
}

function _readStorageFlag(key, fallback = false) {
	try {
		const raw = localStorage.getItem(key);
		if (raw == null) return fallback;
		return raw === '1';
	} catch {
		return fallback;
	}
}

function _setPanelCollapsed(collapsed) {
	const panel = document.querySelector('.nw-panel');
	if (!panel) return;
	const next = !!collapsed;
	panel.classList.toggle('nw-panel-collapsed', next);
	const toggle = $('nw-panel-toggle');
	if (toggle) {
		toggle.setAttribute('aria-expanded', next ? 'false' : 'true');
		toggle.setAttribute('aria-label', next ? 'Expand left panel' : 'Collapse left panel');
		toggle.title = next ? 'Expand panel' : 'Collapse panel';
	}
	try {
		localStorage.setItem(PANEL_COLLAPSED_STORAGE_KEY, next ? '1' : '0');
	} catch {}
}

function _setSectionCollapsed(section, collapsed) {
	if (!section) return;
	const next = !!collapsed;
	section.classList.toggle('nw-section-collapsed', next);
	const header = section.querySelector('.nw-section-header');
	if (header) {
		header.setAttribute('aria-expanded', next ? 'false' : 'true');
	}
}

function _saveSectionCollapseState() {
	const state = {};
	document.querySelectorAll('.nw-panel .nw-section[id]').forEach((section) => {
		state[section.id] = section.classList.contains('nw-section-collapsed');
	});
	_writeJsonStorage(SECTION_COLLAPSE_STORAGE_KEY, state);
}

function _restoreSectionCollapseState() {
	const state = _readJsonStorage(SECTION_COLLAPSE_STORAGE_KEY, null);
	if (!state || typeof state !== 'object') return;
	document.querySelectorAll('.nw-panel .nw-section[id]').forEach((section) => {
		if (!Object.prototype.hasOwnProperty.call(state, section.id)) return;
		_setSectionCollapsed(section, !!state[section.id]);
	});
}

function _setAdvancedSectionsVisible(visible) {
	const next = !!visible;
	document.body.classList.toggle('nw-show-advanced', next);
	const label = $('advancedToggleLabel');
	if (label) label.textContent = next ? 'Show less' : 'Show more';
	try {
		localStorage.setItem(ADVANCED_VISIBLE_STORAGE_KEY, next ? '1' : '0');
	} catch {}
}

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

const ASSISTANT_DOCK_HEIGHT_KEY = 'numel_assistant_dock_height_v1';
const ASSISTANT_DOCK_CONFIG_COLLAPSED_KEY = 'numel_assistant_dock_config_collapsed_v1';
const ASSISTANT_DOCK_HEIGHT_MIN = 160;
const ASSISTANT_DOCK_HEIGHT_MAX_FRACTION = 0.85; // of canvas-panel height

function _setAssistantDockHeight(panel, canvasPanel, px) {
	const cpRect = canvasPanel.getBoundingClientRect();
	const max = Math.max(ASSISTANT_DOCK_HEIGHT_MIN, cpRect.height * ASSISTANT_DOCK_HEIGHT_MAX_FRACTION);
	const clamped = Math.max(ASSISTANT_DOCK_HEIGHT_MIN, Math.min(max, px));
	panel.style.setProperty('--nw-assistant-dock-height', `${clamped}px`);
	return clamped;
}

function _pumpCanvasLayoutRefresh(durationMs = 280) {
	const endAt = Date.now() + durationMs;
	const pump = () => {
		window.dispatchEvent(new Event('resize'));
		schemaGraph?.eventBus?.emit('camera:moved');
		if (schemaGraph?.draw) schemaGraph.draw();
		if (Date.now() < endAt) requestAnimationFrame(pump);
	};
	requestAnimationFrame(pump);
}

function _ensureAssistantDockChrome(panel) {
	// Resize handle (top of panel) — drag to resize console height.
	let handle = panel.querySelector(':scope > .nw-assistant-dock-resize');
	if (!handle) {
		handle = document.createElement('div');
		handle.className = 'nw-assistant-dock-resize';
		handle.setAttribute('role', 'separator');
		handle.setAttribute('aria-label', 'Resize assistant console');
		handle.setAttribute('title', 'Drag to resize');
		panel.insertBefore(handle, panel.firstChild);

		let dragging = false;
		const onPointerMove = (ev) => {
			if (!dragging) return;
			const canvasPanel = panel.parentElement;
			if (!canvasPanel) return;
			const cpRect = canvasPanel.getBoundingClientRect();
			// Mouse Y relative to canvas-panel bottom → desired panel height.
			const newH = cpRect.bottom - ev.clientY;
			const applied = _setAssistantDockHeight(panel, canvasPanel, newH);
			window._numelAssistantDockHeight = applied;
			window.dispatchEvent(new Event('resize'));
		};
		const onPointerUp = (ev) => {
			if (!dragging) return;
			dragging = false;
			handle.releasePointerCapture?.(ev.pointerId);
			document.body.classList.remove('nw-assistant-dock-resizing');
			try {
				localStorage.setItem(ASSISTANT_DOCK_HEIGHT_KEY,
					String(window._numelAssistantDockHeight || ''));
			} catch {}
			// Final resize pump so the canvas re-reads container size.
			const animEnd = Date.now() + 200;
			const pump = () => {
				window.dispatchEvent(new Event('resize'));
				if (Date.now() < animEnd) requestAnimationFrame(pump);
			};
			requestAnimationFrame(pump);
		};
		handle.addEventListener('pointerdown', (ev) => {
			dragging = true;
			handle.setPointerCapture?.(ev.pointerId);
			document.body.classList.add('nw-assistant-dock-resizing');
			ev.preventDefault();
		});
		handle.addEventListener('pointermove', onPointerMove);
		handle.addEventListener('pointerup', onPointerUp);
		handle.addEventListener('pointercancel', onPointerUp);
	}

	// Settings collapse toggle — sits on the divider between the messages
	// area and the right config column. Click to collapse/expand.
	let toggle = panel.querySelector(':scope > .nw-assistant-dock-config-toggle');
	if (!toggle) {
		toggle = document.createElement('button');
		toggle.type = 'button';
		toggle.className = 'nw-assistant-dock-config-toggle';
		toggle.setAttribute('aria-label', 'Toggle config panel');
		toggle.setAttribute('title', 'Show / hide config');
		toggle.innerHTML = '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 18 15 12 9 6"/></svg>';
		toggle.addEventListener('click', (ev) => {
			ev.stopPropagation();
			const collapsed = panel.classList.toggle('assistant-config-collapsed');
			try {
				localStorage.setItem(ASSISTANT_DOCK_CONFIG_COLLAPSED_KEY, collapsed ? '1' : '0');
			} catch {}
			window.dispatchEvent(new Event('resize'));
		});
		panel.appendChild(toggle);
	}
}

function _applyAssistantDock(enabled) {
	const panel = document.getElementById('consolePanel');
	const canvasPanel = document.querySelector('.nw-canvas-panel');
	if (!panel || !canvasPanel) return;

	if (enabled) {
		// Move the assistant panel into the canvas panel so it docks below
		// the canvas as a flex sibling. The id is stable so ConsoleAgent
		// references still resolve.
		if (panel.parentElement !== canvasPanel) {
			canvasPanel.appendChild(panel);
		}
		panel.classList.add('open');
		// Force the settings body open — the dock layout shows the config
		// column on the right so there's no need to collapse it.
		const settingsBody = document.getElementById('consoleSettingsBody');
		if (settingsBody) settingsBody.style.display = '';
		const settingsHeader = document.getElementById('consoleSettingsHeader');
		if (settingsHeader) settingsHeader.setAttribute('aria-expanded', 'true');

		// Inject the resize handle and config-collapse toggle.
		_ensureAssistantDockChrome(panel);

		// Restore persisted height + collapsed state.
		try {
			const stored = parseFloat(localStorage.getItem(ASSISTANT_DOCK_HEIGHT_KEY));
			if (Number.isFinite(stored) && stored > 0) {
				_setAssistantDockHeight(panel, canvasPanel, stored);
			}
		} catch {}
		try {
			const collapsed = localStorage.getItem(ASSISTANT_DOCK_CONFIG_COLLAPSED_KEY) === '1';
			panel.classList.toggle('assistant-config-collapsed', collapsed);
		} catch {}

		// If the console manager already exists, trigger its open() so the
		// agent starts. Safe to call when already open — the method no-ops.
		if (typeof consoleManager !== 'undefined' && consoleManager?.open) {
			consoleManager.open().catch(() => {});
		}
	} else {
		// Restore the panel as a body-level fixed slide-out overlay.
		if (panel.parentElement !== document.body) {
			document.body.appendChild(panel);
		}
		panel.classList.remove('open');
		// Clear inline height override so the slide-out CSS rules apply.
		panel.style.removeProperty('--nw-assistant-dock-height');
		if (typeof consoleManager !== 'undefined' && consoleManager?.close) {
			consoleManager.close();
		}
	}

	// The docked panel changes the canvas-panel available height, which
	// the schemagraph canvas only picks up on a resize event. Pump a few
	// resize events across the CSS transition window so the canvas buffer
	// and overlays stay in sync with the new layout.
	const animEnd = Date.now() + 300;
	const pump = () => {
		window.dispatchEvent(new Event('resize'));
		if (typeof schemaGraph !== 'undefined') {
			schemaGraph?.eventBus?.emit('camera:moved');
		}
		if (Date.now() < animEnd) requestAnimationFrame(pump);
	};
	requestAnimationFrame(pump);
}

function _applyGlobalLayoutPreset(preset) {
	const normalized = _normalizeGlobalLayoutPreset(preset);
	const body = document.body;
	if (body) {
		Array.from(body.classList)
			.filter((className) => className.startsWith('nw-layout-'))
			.forEach((className) => body.classList.remove(className));
		// Project-workbench variants share the base workbench class so the
		// current shell remains the common structural foundation, while each
		// preset can layer a stronger visual direction on top.
		if (normalized === 'workbench' || normalized.startsWith('project-workbench')) {
			body.classList.add('nw-layout-project-workbench');
		}
		// Assistant-dock variants also add a modifier class used to trigger
		// the docked assistant rules.
		if (ASSISTANT_DOCK_LAYOUTS.has(normalized)) {
			body.classList.add('nw-layout-assistant-dock');
		} else {
			body.classList.remove('nw-layout-assistant-dock');
		}
		body.classList.add(`nw-layout-${normalized}`);
	}
	_applyAssistantDock(ASSISTANT_DOCK_LAYOUTS.has(normalized));
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

function _starterLoginSessionKey() {
	const userId = window._numelUser?.id || 'guest';
	const tokenSeed = String(window._numelToken || 'guest')
		.replace(/[^a-zA-Z0-9_-]/g, '')
		.slice(0, 16) || 'guest';
	return `numel_starter_login_seen_v1_${userId}_${tokenSeed}`;
}

function _hasShownStarterThisLogin() {
	try {
		return sessionStorage.getItem(_starterLoginSessionKey()) === '1';
	} catch {
		return false;
	}
}

function _markStarterShownThisLogin() {
	try {
		sessionStorage.setItem(_starterLoginSessionKey(), '1');
	} catch {}
}

function _showStarterOnLoginPreference() {
	const prefs = window._numelUserProfile?.metadata?.ui_preferences;
	if (prefs && Object.prototype.hasOwnProperty.call(prefs, 'show_starter_on_login')) {
		return prefs.show_starter_on_login !== false;
	}
	return true;
}

function _applyBackendSchemaVisibility() {
	if (!schemaGraph?.api?.schemaTypes?.setTypes) return;
	const showBackendConfig = _supportedBackends.length > 1;
	schemaGraph.api.schemaTypes.setTypes({
		hiddenFields: showBackendConfig ? ['extra'] : ['extra', 'backend'],
		hiddenWorkflowTypes: showBackendConfig ? [] : ['backend_config'],
	});
}

async function _updateUserUiPreferences(patch = {}) {
	if (!_isAuthenticatedUser()) throw new Error('Not authenticated');
	const token = window._numelToken || localStorage.getItem('numel_token');
	const resp = await fetch(`${$('serverUrl').value || window.location.origin}/auth/preferences/update`, {
		method: 'POST',
		headers: {
			'Content-Type': 'application/json',
			'Authorization': `Bearer ${token}`,
		},
		body: JSON.stringify({ ui_preferences: patch }),
	});
	const data = await resp.json().catch(() => ({}));
	if (!resp.ok) throw new Error(data.detail || 'Failed to update preferences');
	const profile = data.profile && typeof data.profile === 'object' ? data.profile : {};
	window._numelUserProfile = profile;
	window.dispatchEvent(new CustomEvent('numel:user-profile-updated', { detail: { profile } }));
	return profile;
}

window.getNumelUserUiPreferences = function() {
	return { ...(window._numelUserProfile?.metadata?.ui_preferences || {}) };
};

window.updateNumelUserUiPreferences = _updateUserUiPreferences;

function _hasWorkflowContent(workflow) {
	return Array.isArray(workflow?.nodes) && workflow.nodes.length > 0;
}

function _isCurrentWorkflowEmptyState() {
	const workflowNodeCount = Array.isArray(visualizer?.graphNodes)
		? visualizer.graphNodes.filter((node) => !!node).length
		: 0;
	const canvasNodeCount = Array.isArray(schemaGraph?.graph?.nodes)
		? schemaGraph.graph.nodes.filter((node) => !!node).length
		: 0;
	const hasWorkflowNodes = workflowNodeCount > 0 || canvasNodeCount > 0;
	return !hasWorkflowNodes && !currentWorkflowHasContent;
}

function _starterHelloWorkflow() {
	return {
		options: {
			type: 'workflow_options',
			name: 'Hello Workflow',
			description: 'A tiny first workflow that creates output and previews it.',
		},
		nodes: [
			{ type: 'start_flow', extra: { pos: [60, 180], name: 'Start' } },
			{
				type: 'transform_flow',
				lang: 'python',
				script: 'output = {"message": "Hello from Numel!", "next_step": "Edit this transform or ask the assistant to expand it."}',
				extra: { pos: [320, 180], name: 'Hello' },
			},
			{ type: 'preview_flow', extra: { pos: [580, 180], name: 'Preview' } },
			{ type: 'end_flow', extra: { pos: [840, 180], name: 'End' } },
		],
		edges: [
			{ source: 0, target: 1, source_slot: 'flow_out', target_slot: 'flow_in' },
			{ source: 1, target: 2, source_slot: 'output', target_slot: 'flow_in' },
			{ source: 2, target: 3, source_slot: 'flow_out', target_slot: 'flow_in' },
		],
	};
}

function _closeStarterModal(markSeen = true) {
	const overlay = document.getElementById('nwStarterModal');
	if (!overlay) return;
	if (markSeen) _markStarterShownThisLogin();
	overlay.remove();
}

function _showStarterModal() {
	if (!_isAuthenticatedUser() || !_showStarterOnLoginPreference() || _hasShownStarterThisLogin() || !_isCurrentWorkflowEmptyState()) return;
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
						<span class="nw-starter-action-title">Quick Start</span>
						<span class="nw-starter-action-copy">Load a tiny runnable flow you can inspect right away.</span>
					</button>
					<button class="nw-starter-action" data-starter-action="research" type="button">
						<span class="nw-starter-action-title">Research Starter</span>
						<span class="nw-starter-action-copy">Open a planner-style workflow for research and reporting.</span>
					</button>
					<button class="nw-starter-action" data-starter-action="media" type="button">
						<span class="nw-starter-action-title">Webcam Starter</span>
						<span class="nw-starter-action-copy">Try a browser-media workflow with live camera input.</span>
					</button>
					<button class="nw-starter-action" data-starter-action="repo" type="button">
						<span class="nw-starter-action-title">Repo Assistant</span>
						<span class="nw-starter-action-copy">Open a local workspace assistant for file inspection and repo questions.</span>
					</button>
					<button class="nw-starter-action" data-starter-action="miniapp" type="button">
						<span class="nw-starter-action-title">Mini App Starter</span>
						<span class="nw-starter-action-copy">Open a compact assistant flow that is easy to publish as a standalone app.</span>
					</button>
					<button class="nw-starter-action" data-starter-action="support" type="button">
						<span class="nw-starter-action-title">Support Workbench</span>
						<span class="nw-starter-action-copy">Open a deployment-ready support assistant with knowledge and file access.</span>
					</button>
					<button class="nw-starter-action" data-starter-action="ops" type="button">
						<span class="nw-starter-action-title">Ops Workbench</span>
						<span class="nw-starter-action-copy">Open an operator assistant workbench for proactive and diagnostic flows.</span>
					</button>
					<button class="nw-starter-action" data-starter-action="assistant" type="button">
						<span class="nw-starter-action-title">Ask Assistant</span>
						<span class="nw-starter-action-copy">Open Assistant with a prompt to draft a first workflow.</span>
					</button>
				</div>
			</div>
			<div class="nw-modal-footer">
				<label class="nw-starter-modal-pref" title="Show this starter picker after you log in whenever the current workbench is still empty.">
					<input id="nwStarterShowOnLoginToggle" type="checkbox" ${_showStarterOnLoginPreference() ? 'checked' : ''}>
					<span>Show on login</span>
				</label>
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
	overlay.querySelector('#nwStarterShowOnLoginToggle')?.addEventListener('change', async (event) => {
		const checked = !!event.target?.checked;
		try {
			await _updateUserUiPreferences({ show_starter_on_login: checked });
			if (!checked) _markStarterShownThisLogin();
		} catch (error) {
			event.target.checked = !checked;
			addLog('error', `❌ Failed to save starter preference: ${error.message}`);
			await NumelAlert('Starter Preference', error.message || 'Failed to save starter preference.');
		}
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
	const hero = document.querySelector('.nw-canvas-hero');
	const stageBar = document.querySelector('.nw-canvas-stagebar');
	_updateWorkbenchOverview();
	if (!panel) return;
	const visible = !!api && _isAuthenticatedUser() && _isCurrentWorkflowEmptyState();
	panel.style.display = visible ? '' : 'none';
	if (visible) _hideStarterFollowthrough();
	if (visible) {
		const heroChanged = !!hero && hero.classList.contains('nw-hero-hidden');
		const stageChanged = !!stageBar && !stageBar.classList.contains('nw-stagebar-hidden');
		hero?.classList.remove('nw-hero-hidden');
		stageBar?.classList.add('nw-stagebar-hidden');
		if (heroChanged || stageChanged) {
			_pumpCanvasLayoutRefresh();
		}
	}
	if (subtitle) {
		subtitle.textContent = currentSpaceInfo?.title
			? `"${currentSpaceInfo.title}" is ready — choose a starter below.`
			: 'Choose a starter to begin.';
	}
	if (!visible) {
		_closeStarterModal(false);
	}
}

function _renderWorkbenchSpaces() {
	const list = $('workbenchSpacesList');
	if (!list) return;
	if (!availableSpaces.length) {
		list.innerHTML = '<div class="nw-space-pill"><div class="nw-space-pill-bullet"></div><div class="nw-space-pill-meta"><div class="nw-space-pill-title">No spaces yet</div><div class="nw-space-pill-copy">Create a space to get started.</div></div></div>';
		return;
	}
	list.innerHTML = availableSpaces.map((space) => {
		const title = space.title || space.slug || space.id;
		const isActive = space.id === currentSpaceId;
		let copy = 'Space';
		if (isActive && _isCurrentWorkflowEmptyState()) {
			copy = 'Active · ready for a first workflow';
		} else if (isActive) {
			copy = 'Active · ready to edit and run';
		} else if (space?.metadata?.forked_from_space_id) {
			copy = 'Fork · ready to adapt';
		} else if (space.visibility) {
			copy = `${String(space.visibility).charAt(0).toUpperCase()}${String(space.visibility).slice(1)} space`;
		}
		const safeTitle = String(title)
			.replace(/&/g, '&amp;')
			.replace(/</g, '&lt;')
			.replace(/>/g, '&gt;')
			.replace(/"/g, '&quot;');
		const safeCopy = String(copy)
			.replace(/&/g, '&amp;')
			.replace(/</g, '&lt;')
			.replace(/>/g, '&gt;');
		return `
			<button class="nw-space-pill${isActive ? ' is-active' : ''}" type="button" data-space-id="${space.id}">
				<div class="nw-space-pill-bullet"></div>
				<div class="nw-space-pill-meta">
					<div class="nw-space-pill-title">${safeTitle}</div>
					<div class="nw-space-pill-copy">${safeCopy}</div>
				</div>
			</button>
		`;
	}).join('');
}

function _updateWorkbenchOverview() {
	const spaceEl = $('workbenchSpaceName');
	const workflowEl = $('workbenchWorkflowName');
	const summaryEl = $('workbenchSummary');
	const statusEl = $('workbenchStatusPill');
	const nextTitleEl = $('workbenchNextTitle');
	const nextCopyEl = $('workbenchNextCopy');
	const askBtn = $('workbenchAskAssistantBtn');
	const galleryBtn = $('workbenchBrowseGalleryBtn');
	const runBtn = $('workbenchRunBtn');
	const heroKickerEl = $('canvasHeroKicker');
	const heroTitleEl = $('canvasHeroTitle');
	const heroSummaryEl = $('canvasHeroSummary');
	const canvasSpaceEl = $('canvasWorkbenchSpaceName');
	const canvasWorkflowEl = $('canvasWorkbenchWorkflowName');
	const canvasSummaryEl = $('canvasWorkbenchSummary');
	const canvasAskBtn = $('canvasAskAssistantBtn');
	const canvasGalleryBtn = $('canvasBrowseGalleryBtn');
	const canvasRunBtn = $('canvasStartRunBtn');
	const canvasSaveBtn = $('canvasSaveWorkflowBtn');
	const spaceName = currentSpaceInfo?.title || currentSpaceInfo?.slug || 'Choose a space';
	const workflowName = visualizer?.currentWorkflowName || $('singleWorkflowName')?.textContent || 'None';
	const isReady = !!client?.isConnected && _isAuthenticatedUser();
	const isEmpty = _isCurrentWorkflowEmptyState();
	const startDisabled = $('startBtn')?.disabled ?? true;
	let overviewSummary = '';
	let canvasSummary = '';
	let nextTitle = '';
	let nextCopy = '';
	let heroKicker = 'Start here';
	let heroTitle = 'Start with a space, then build something runnable.';
	let heroSummary = 'Choose a space, pick a starter or ask the assistant, and get to a first run quickly.';

	if (spaceEl) spaceEl.textContent = spaceName;
	if (workflowEl) workflowEl.textContent = `Workflow: ${workflowName || 'None'}`;
	if (statusEl) statusEl.textContent = isReady ? 'Connected' : 'Offline';

	if (!currentSpaceInfo) {
		overviewSummary = 'Create or pick a space to open a workbench.';
		canvasSummary = 'Choose a space to start building.';
		nextTitle = 'Create your first space.';
		nextCopy = 'A space keeps one current workflow, its runs, and the resources it needs.';
		heroTitle = 'Pick a space to begin.';
		heroSummary = 'Each space is a project workbench. Create one, choose a starter, and run it.';
	} else if (isEmpty) {
		overviewSummary = `"${spaceName}" is ready for its first workflow. Pick a starter, open a repo, mini app, support, or ops workbench, or ask the assistant for a draft.`;
		canvasSummary = `"${spaceName}" is ready. Choose a starter, load a workbench, or ask for a first draft.`;
		nextTitle = 'Choose a starting point.';
		nextCopy = 'Use a ready-made workflow, open a repo, mini app, support, or ops workbench, ask the assistant, or browse the gallery.';
		heroTitle = `"${spaceName}" is ready for its first workflow.`;
		heroSummary = 'Choose a starter, open a repo, mini app, support, or ops workbench, ask the assistant to draft one, or browse the gallery.';
	} else {
		overviewSummary = `Working in "${spaceName}" — "${workflowName || 'Current Workflow'}" is ready to shape and run.`;
		canvasSummary = `"${workflowName || 'Current Workflow'}" in "${spaceName}". Edit steps, save, and run when ready.`;
		nextTitle = 'Edit or run the workflow.';
		nextCopy = 'Add steps on the canvas, save your changes, and run.';
		heroKicker = 'Current workflow';
		heroTitle = `"${workflowName || 'Current Workflow'}"`;
		heroSummary = 'Edit steps, save your changes, and run. Open the assistant if you want help refining it.';
	}

	if (summaryEl) summaryEl.textContent = overviewSummary;
	if (nextTitleEl) nextTitleEl.textContent = nextTitle;
	if (nextCopyEl) nextCopyEl.textContent = nextCopy;
	if (heroKickerEl) heroKickerEl.textContent = heroKicker;
	if (heroTitleEl) heroTitleEl.textContent = heroTitle;
	if (heroSummaryEl) heroSummaryEl.textContent = heroSummary;
	if (canvasSpaceEl) canvasSpaceEl.textContent = spaceName;
	if (canvasWorkflowEl) canvasWorkflowEl.textContent = workflowName || 'Current Workflow';
	if (canvasSummaryEl) canvasSummaryEl.textContent = canvasSummary;
	if (askBtn) askBtn.disabled = !isReady;
	if (galleryBtn) galleryBtn.disabled = !isReady;
	if (runBtn) runBtn.disabled = !isReady || startDisabled;
	if (canvasAskBtn) canvasAskBtn.disabled = !isReady;
	if (canvasGalleryBtn) canvasGalleryBtn.disabled = !isReady;
	if (canvasRunBtn) canvasRunBtn.disabled = !isReady || startDisabled;
	if (canvasSaveBtn) canvasSaveBtn.disabled = !isReady;
	if (canvasAskBtn) {
		canvasAskBtn.title = isReady
			? (isEmpty ? 'Ask Assistant to draft a first workflow' : 'Ask Assistant to help edit this workflow')
			: 'Connect first to use the assistant';
	}
	if (canvasGalleryBtn) {
		canvasGalleryBtn.title = isReady
			? 'Browse example workflows and starters'
			: 'Connect first to browse the gallery';
	}
	if (canvasRunBtn) {
		canvasRunBtn.title = (!isReady || startDisabled)
			? 'Save or finish connecting before you run'
			: 'Run the current workflow';
	}
	if (canvasSaveBtn) {
		canvasSaveBtn.title = isReady ? 'Save the current workflow' : 'Connect first to save changes';
	}
	// Stage bar shows when workflow is loaded; hero shows when empty
	const stageBar = document.querySelector('.nw-canvas-stagebar');
	let layoutChanged = false;
	if (stageBar) {
		const nextStageHidden = isEmpty;
		if (stageBar.classList.contains('nw-stagebar-hidden') !== nextStageHidden) {
			layoutChanged = true;
		}
		stageBar.classList.toggle('nw-stagebar-hidden', nextStageHidden);
	}
	const hero = document.querySelector('.nw-canvas-hero');
	if (hero) {
		// Per-space dismissal: hero re-appears for new spaces.
		let dismissedSet = {};
		try { dismissedSet = JSON.parse(localStorage.getItem('numel-hero-dismissed') || '{}') || {}; } catch (_) {}
		const dismissed = currentSpaceId ? !!dismissedSet[currentSpaceId] : false;
		const nextHeroHidden = dismissed || (!isEmpty && !!currentSpaceInfo);
		if (hero.classList.contains('nw-hero-hidden') !== nextHeroHidden) {
			layoutChanged = true;
		}
		hero.classList.toggle('nw-hero-hidden', nextHeroHidden);
	}
	// Hide the "useful next step" card once there's a workflow loaded
	const nextCard = document.querySelector('.nw-workbench-next-card');
	if (nextCard) {
		nextCard.classList.toggle('nw-next-hidden', !isEmpty && !!currentSpaceInfo);
	}
	if (layoutChanged) {
		_pumpCanvasLayoutRefresh();
	}
	_renderWorkbenchSpaces();
}

function _syncSpaceControls() {
	const select = $('spaceSelect');
	const createBtn = $('createSpaceBtn');
	const forkBtn = $('forkSpaceBtn');
	const removeBtn = $('removeSpaceBtn');
	const hasApi = !!api;
	const optionCount = select ? Array.from(select.options || []).filter((option) => !!option.value).length : 0;

	if (select) {
		select.disabled = !hasApi || optionCount === 0;
	}
	if (createBtn) {
		createBtn.disabled = !hasApi;
	}
	if (forkBtn) {
		forkBtn.disabled = !hasApi || !currentSpaceId;
	}
	if (removeBtn) {
		removeBtn.disabled = !hasApi || !currentSpaceId || optionCount <= 1;
	}
}

function _syncReuseControls() {
	const hasApi = !!api;
	const hasWorkflow = !!visualizer?.currentWorkflow && currentWorkflowHasContent;
	const snapshotBtn = $('saveSnapshotBtn');
	const historyBtn = $('workflowHistoryBtn');
	const publishBtn = $('publishTemplateBtn');
	if (snapshotBtn) snapshotBtn.disabled = !hasApi || !hasWorkflow;
	if (historyBtn) historyBtn.disabled = !hasApi || !currentSpaceId;
	if (publishBtn) publishBtn.disabled = !hasApi || !hasWorkflow;
}

function _closeSidePanelDom(id) {
	document.getElementById(id)?.classList.remove('open');
}

window.closeNumelSidePanels = function(except = []) {
	const keep = new Set(Array.isArray(except) ? except : [except]);
	const assistantDocked = document.body.classList.contains('nw-layout-assistant-dock');
	if (!keep.has('console') && !assistantDocked) {
		try { consoleManager?.close?.(); } catch {}
		_closeSidePanelDom('consolePanel');
	} else if (assistantDocked) {
		document.getElementById('consolePanel')?.classList.add('open');
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
	if (!keep.has('assistantDeployments')) {
		try { if (typeof NumelAssistantDeployments !== 'undefined') NumelAssistantDeployments.close(); } catch {}
		_closeSidePanelDom('assistantDeploymentPanel');
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
	let followthrough = null;
	try {
		switch (action) {
			case 'hello':
				await window.loadAndSyncWorkflow(_starterHelloWorkflow(), 'Hello Workflow');
				addLog('success', '✨ Loaded Hello Workflow starter');
				followthrough = 'hello';
				break;
			case 'research':
				await _loadStarterGalleryItem(STARTER_GALLERY_IDS.research);
				addLog('success', '✨ Loaded Research Starter');
				followthrough = 'research';
				break;
			case 'media':
				await _loadStarterGalleryItem(STARTER_GALLERY_IDS.media);
				addLog('success', '✨ Loaded Webcam Starter');
				followthrough = 'media';
				break;
			case 'repo':
				await _loadStarterGalleryItem(STARTER_GALLERY_IDS.repo);
				addLog('success', '✨ Loaded Repo Assistant Starter');
				followthrough = 'repo';
				break;
			case 'miniapp':
				await _loadStarterGalleryItem(STARTER_GALLERY_IDS.miniapp);
				addLog('success', '✨ Loaded Publishable Mini App Starter');
				followthrough = 'miniapp';
				break;
			case 'support':
				await _loadStarterGalleryItem(STARTER_GALLERY_IDS.support);
				addLog('success', '✨ Loaded Support Workbench');
				followthrough = 'support';
				break;
			case 'ops':
				await _loadStarterGalleryItem(STARTER_GALLERY_IDS.ops);
				addLog('success', '✨ Loaded Ops Workbench');
				followthrough = 'ops';
				break;
			case 'assistant':
				if (!consoleManager) throw new Error('Assistant is not ready yet');
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
		_markStarterShownThisLogin();
		_closeStarterModal(false);
		_updateStarterExperience(false);
		if (followthrough) _showStarterFollowthrough(followthrough);
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

async function _loadAuthBundle(baseUrl, token) {
	const resp = await fetch(`${baseUrl}/auth/me`, {
		method: 'POST',
		headers: {
			'Authorization': `Bearer ${token}`,
			'Content-Type': 'application/json',
		},
	});
	if (!resp.ok) throw new Error('Failed to load authenticated user bundle');
	return resp.json();
}

function _applyAuthenticatedBundle(token, bundle) {
	window._numelToken = token;
	window._numelUser = bundle?.user || null;
	window._numelUserProfile = bundle?.profile || { metadata: {} };
	window.dispatchEvent(new CustomEvent('numel:user-profile-updated', { detail: { profile: window._numelUserProfile } }));
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
		updateClearButtonState();
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
		_applyBackendSchemaVisibility();

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
		h1.insertBefore(panelToggle, h1.firstChild);

		panelToggle.addEventListener('click', (e) => {
			e.stopPropagation();
			_setPanelCollapsed(!_panel.classList.contains('nw-panel-collapsed'));
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

	// Tooltip labels for the collapsed-panel rail icons. The icon SVGs
	// themselves are cloned from each section's title <svg>, so the rail
	// always matches the in-header icon.
	const _sectionLabels = {
		authUserBar:              'Account',
		workbenchOverviewSection: 'Space',
		workflowSection:          'Workflow',
		executionSection:         'Run',
		channelsSection:          'Channels',
		credentialsSection:       'Credentials',
		eventLogSection:          'Activity',
		experimentalSection:      'Experimental',
	};

	// Make each panel section collapsible via header click
	document.querySelectorAll('.nw-panel .nw-section').forEach(section => {
		const header = section.querySelector('.nw-section-header');
		if (!header) return;
		header.setAttribute('role', 'button');
		header.setAttribute('tabindex', '0');

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

		// Section glyph shown when panel is collapsed (vertical icon rail).
		// Clones the SVG from the section's <h3> so the rail icon always
		// matches the in-header icon. Tooltip uses the static label; the
		// auth bar's tooltip is refreshed with the username once the user
		// is known (see _showUserBar).
		const label = _sectionLabels[section.id];
		const titleSvg = section.querySelector('.nw-section-title svg');
		if (label && titleSvg) {
			const rail = document.createElement('span');
			rail.className = 'nw-section-rail-icon';
			const svgClone = titleSvg.cloneNode(true);
			svgClone.setAttribute('width', '18');
			svgClone.setAttribute('height', '18');
			rail.appendChild(svgClone);
			rail.setAttribute('title', label);
			rail.setAttribute('aria-label', label);
			header.insertBefore(rail, header.firstChild);
		}
		_setSectionCollapsed(section, section.classList.contains('nw-section-collapsed'));

		const toggleSection = () => {
			const panel = document.querySelector('.nw-panel');
			// When panel is collapsed, clicking a section icon expands the panel
			// AND ensures the clicked section is expanded. Other sections keep
			// whatever state they had before the panel was collapsed.
			if (panel && panel.classList.contains('nw-panel-collapsed')) {
				_setPanelCollapsed(false);
				_setSectionCollapsed(section, false);
				_saveSectionCollapseState();
				// Pump resize so canvas + overlays follow the new layout
				const animEnd = Date.now() + 300;
				const pump = () => {
					window.dispatchEvent(new Event('resize'));
					if (Date.now() < animEnd) requestAnimationFrame(pump);
				};
				requestAnimationFrame(pump);
				return;
			}
			_setSectionCollapsed(section, !section.classList.contains('nw-section-collapsed'));
			_saveSectionCollapseState();
		};

		header.addEventListener('click', (e) => {
			if (e.target.closest('button, select, input, a')) return;
			toggleSection();
		});
		header.addEventListener('keydown', (e) => {
			if (e.key !== 'Enter' && e.key !== ' ') return;
			if (e.target.closest('button, select, input, a') && e.target !== header) return;
			e.preventDefault();
			toggleSection();
		});
	});

	// Expand-all / Collapse-all toolbar below the panel title
	const _panelForToolbar = document.querySelector('.nw-panel');
	if (_panelForToolbar && !document.getElementById('nw-section-toolbar')) {
		const toolbar = document.createElement('div');
		toolbar.id = 'nw-section-toolbar';
		toolbar.className = 'nw-section-toolbar';
		toolbar.innerHTML = `
			<button type="button" id="nw-expand-all-btn" class="nw-section-toolbar-btn" title="Expand all sub-panels">Expand all</button>
			<button type="button" id="nw-collapse-all-btn" class="nw-section-toolbar-btn" title="Collapse all sub-panels">Collapse all</button>
		`;
		// Insert right after the title (and its subtitle if any)
		const firstSection = _panelForToolbar.querySelector('.nw-section');
		if (firstSection) {
			_panelForToolbar.insertBefore(toolbar, firstSection);
		} else {
			_panelForToolbar.appendChild(toolbar);
		}
		document.getElementById('nw-expand-all-btn').addEventListener('click', () => {
			document.querySelectorAll('.nw-panel .nw-section').forEach(s => {
				_setSectionCollapsed(s, false);
			});
			_saveSectionCollapseState();
		});
		document.getElementById('nw-collapse-all-btn').addEventListener('click', () => {
			document.querySelectorAll('.nw-panel .nw-section').forEach(s => {
				_setSectionCollapsed(s, true);
			});
			_saveSectionCollapseState();
		});
	}

	_restoreSectionCollapseState();
	_setPanelCollapsed(_readStorageFlag(PANEL_COLLAPSED_STORAGE_KEY, false));
	_setAdvancedSectionsVisible(_readStorageFlag(ADVANCED_VISIBLE_STORAGE_KEY, false));
	_resetExecutionReplayView();
	_resetExecutionEvalView();
	_resetExecutionFailureView();
	_resetExecutionComparisonView();
	_syncReplayButtonState();

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
			const bundle = await _loadAuthBundle(baseUrl, token);
			if (bundle?.user) {
				_applyAuthenticatedBundle(token, bundle);
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

		const finish = async (token, user) => {
			if (token) localStorage.setItem('numel_token', token);
			let bundle = { user, profile: { metadata: {} } };
			if (token && user) {
				try {
					bundle = await _loadAuthBundle(baseUrl, token);
				} catch {
					bundle = { user, profile: { metadata: {} } };
				}
			}
			_applyAuthenticatedBundle(token, bundle);
			modal.style.display = 'none';
			if (window._numelUser) _showUserBar(window._numelUser);
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
				await finish(data.token, data.user);
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
				await finish(data.token, data.user);
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
	// Refresh the collapsed-panel rail icon tooltip with the username
	const railIcon = bar.querySelector('.nw-section-rail-icon');
	if (railIcon) {
		const tip = user.username ? `Account — ${user.username}` : 'Account';
		railIcon.setAttribute('title', tip);
		railIcon.setAttribute('aria-label', tip);
	}
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
		window._numelUserProfile = null;
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
	$('workbenchSpacesList')?.addEventListener('click', (event) => {
		const button = event.target.closest('.nw-space-pill[data-space-id]');
		if (!button) return;
		const nextSpaceId = button.getAttribute('data-space-id');
		const select = $('spaceSelect');
		if (select && nextSpaceId) {
			select.value = nextSpaceId;
			selectCurrentSpace();
		}
	});
	$('createSpaceBtn').addEventListener('click', createSpace);
	$('forkSpaceBtn')?.addEventListener('click', forkCurrentSpace);
	$('removeSpaceBtn').addEventListener('click', removeCurrentSpace);
	$('workbenchRunBtn')?.addEventListener('click', () => {
		if (!$('workbenchRunBtn')?.disabled) $('startBtn')?.click();
	});
	$('workbenchAskAssistantBtn')?.addEventListener('click', () => _runStarterAction('assistant'));
	$('workbenchBrowseGalleryBtn')?.addEventListener('click', () => _runStarterAction('gallery'));
	$('canvasAskAssistantBtn')?.addEventListener('click', () => _runStarterAction('assistant'));
	$('canvasBrowseGalleryBtn')?.addEventListener('click', () => _runStarterAction('gallery'));
	$('canvasSaveWorkflowBtn')?.addEventListener('click', async () => {
		if ($('canvasSaveWorkflowBtn')?.disabled) return;
		await syncWorkflow();
	});
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
	$('starterRepoBtn')?.addEventListener('click', () => _runStarterAction('repo'));
	$('starterMiniAppBtn')?.addEventListener('click', () => _runStarterAction('miniapp'));
	$('starterSupportBtn')?.addEventListener('click', () => _runStarterAction('support'));
	$('starterOpsBtn')?.addEventListener('click', () => _runStarterAction('ops'));
	$('starterAssistantBtn')?.addEventListener('click', () => _runStarterAction('assistant'));
	$('starterBrowseBtn')?.addEventListener('click', () => _runStarterAction('gallery'));
	$('starterFollowthroughCloseBtn')?.addEventListener('click', () => _hideStarterFollowthrough());
	$('starterFollowthroughActions')?.addEventListener('click', (event) => {
		const button = event.target.closest('button[data-guide-action]');
		if (!button) return;
		_handleStarterFollowthroughAction(button.getAttribute('data-guide-action') || '');
	});

	// Hero close button — persist per-space dismissal
	$('canvasHeroCloseBtn')?.addEventListener('click', () => {
		try {
			const raw = localStorage.getItem('numel-hero-dismissed') || '{}';
			const set = JSON.parse(raw) || {};
			if (currentSpaceId) set[currentSpaceId] = 1;
			localStorage.setItem('numel-hero-dismissed', JSON.stringify(set));
		} catch (_) {}
		const hero = document.querySelector('.nw-canvas-hero');
		if (hero) hero.classList.add('nw-hero-hidden');
		_pumpCanvasLayoutRefresh();
	});

	// Advanced sections toggle
	$('advancedToggleBtn')?.addEventListener('click', () => {
		_setAdvancedSectionsVisible(!document.body.classList.contains('nw-show-advanced'));
	});

	// Workflow management
	$('clearWorkflowBtnSingle').addEventListener('click', clearWorkflow);
	$('clearWorkflowHeaderBtn')?.addEventListener('click', clearWorkflow);

	// Single mode buttons
	$('singleImportBtn').addEventListener('click', () => $('singleWorkflowFileInput').click());
	$('singlePasteBtn' ).addEventListener('click', pasteWorkflowFromClipboard);
	$('singleDownloadBtn').addEventListener('click', downloadWorkflow);
	$('singleCopyBtn'  ).addEventListener('click', copyWorkflowToClipboard);
	$('singleWorkflowFileInput').addEventListener('change', handleSingleImport);
	$('saveSnapshotBtn')?.addEventListener('click', saveWorkflowSnapshot);
	$('workflowHistoryBtn')?.addEventListener('click', showWorkflowSnapshots);
	$('publishTemplateBtn')?.addEventListener('click', publishCurrentWorkflowTemplate);

	// Execution
	$('startBtn').addEventListener('click', startExecution);
	$('cancelBtn').addEventListener('click', cancelExecution);
	$('replayLatestRunBtn')?.addEventListener('click', replayLatestExecution);
	$('compareLatestRunsBtn')?.addEventListener('click', compareLatestExecutions);

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
	// A workflow is "clearable" if there's a workflow object AND we have
	// either nodes on the canvas OR content was loaded from disk. We
	// intentionally do NOT gate on client.isConnected — the WebSocket may
	// still be settling when a workflow first loads, and clear is mostly
	// a local operation. clearWorkflow() handles sync failures itself.
	const hasWorkflow = !!visualizer?.currentWorkflow;
	const hasNodes = schemaGraph?.graph?.nodes?.length > 0;
	const hasContent = hasWorkflow && (hasNodes || currentWorkflowHasContent);
	const disabled = !hasContent;
	$('clearWorkflowBtnSingle').disabled = disabled;
	const headerBtn = $('clearWorkflowHeaderBtn');
	if (headerBtn) headerBtn.disabled = disabled;
	_syncReuseControls();
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

		// Hook WebSocket events before opening the socket so we do not miss a
		// very fast onopen during local first-load startup.
		setupClientEvents();
		client.connectWebSocket();

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
		_supportedBackends = Array.isArray(schemaResponse.supported_backends) && schemaResponse.supported_backends.length
			? schemaResponse.supported_backends
			: ['agno'];
		_applyBackendSchemaVisibility();

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
		agentChatManager = new AgentChatManager(serverUrl, schemaGraph, saveWorkflowToBackend, api);
		addLog('info', '💬 Agent chat manager initialized');

		// Initialize console manager
		consoleManager = new AgentConsoleManager(serverUrl, syncWorkflow, api);
		$('consoleToggleBtn').style.display = '';
		// In the docked-assistant layout the panel is always visible, so
		// open the console immediately to start the agent and avoid the
		// user needing a hidden FAB to do it.
		if (ASSISTANT_DOCK_LAYOUTS.has(window._numelGlobalLayoutPreset)) {
			consoleManager.open().catch(() => {});
		}
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

		// Initialize the local workflow surface immediately, then load the
		// current space/workflow in the background so the UI is usable sooner.
		visualizer.initEmptyWorkflow();
		currentWorkflowHasContent = false;
		updateClearButtonState();
		_updateStarterExperience(true);
		_updateWorkbenchOverview();
		_syncReplayButtonState();
		$('singleImportBtn').disabled = false;
		$('singlePasteBtn').disabled = false;
		_syncSpaceControls();

		addLog('info', '🧭 Loading current space...');
		void refreshSpaceList(true).finally(() => {
			// Refresh channel summary once the initial space bootstrap settles.
			if (typeof NumelChannels !== 'undefined') NumelChannels.refreshSummary();
		});

		addLog('success', `✅ Connected to ${serverUrl}`);
	} catch (error) {
		console.error('Connection error:', error);
		_syncReplayButtonState();
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
	availableSpaces = [];
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
		_clearExecutionIssue();
		_executionReplayView = _executionReplayView?.executionId === event.execution_id
			? _executionReplayView
			: {
				..._createEmptyExecutionReplayView(),
				executionId: event.execution_id,
				platformExecutionId: currentPlatformExecutionId || event.execution_id,
				workflowName: visualizer?.currentWorkflowName || 'Workflow',
				source: 'live',
			};
		_executionReplayView.status = 'running';
		_executionReplayView.startedAt = _executionReplayView.startedAt || new Date().toISOString();
		_executionReplayView.summary = _describeExecutionReplaySummary(_executionReplayView);
		setExecStatus('running', 'Running');
		const shownId = currentPlatformExecutionId || event.execution_id;
		$('execId').textContent = shownId.substring(0, 8) + '...';
		enableStart(false);
		visualizer?.clearNodeStates();

		// LOCK GRAPH during execution
		schemaGraph.api.lock.lock('Workflow running');
		schemaGraph.eventBus.emit('workflow:started', event);

		_appendExecutionReplayEvent('info', 'Workflow started', _executionReplayView.workflowName, { time: _executionReplayView.startedAt });
		addLog('info', `▶️ Workflow started`);
	});

	client.on('workflow.completed', (event) => {
		if (event.execution_id !== currentExecutionId) return;
		const executionId = event.execution_id;
		const finishedAt = new Date().toISOString();
		if (_executionReplayView) {
			_executionReplayView.status = 'completed';
			_executionReplayView.endedAt = finishedAt;
			_executionReplayView.summary = _describeExecutionReplaySummary(_executionReplayView);
		}
		_appendExecutionReplayEvent('success', 'Workflow completed', _formatExecutionReplayDuration(_executionReplayView?.startedAt, finishedAt) || '', { time: finishedAt });
		_cacheCurrentExecutionReplay(executionId);
		void _hydrateExecutionReplay(executionId, { useCurrentView: true });
		currentExecutionId = null;
		currentPlatformExecutionId = null;
		_clearExecutionIssue();
		setExecStatus('completed', 'Completed');
		enableStart(true);

		// UNLOCK GRAPH after completion
		schemaGraph.api.lock.unlock();
		schemaGraph.eventBus.emit('workflow:completed', event);

		addLog('success', `✅ Workflow completed`);
	});

	client.on('workflow.failed', (event) => {
		if (event.execution_id !== currentExecutionId) return;
		const executionId = event.execution_id;
		const finishedAt = new Date().toISOString();
		if (_executionReplayView) {
			_executionReplayView.status = 'failed';
			_executionReplayView.endedAt = finishedAt;
			_executionReplayView.error = event.error || 'Unknown error';
			_executionReplayView.summary = _describeExecutionReplaySummary(_executionReplayView);
		}
		_appendExecutionReplayEvent('error', 'Workflow failed', event.error || 'Unknown error', { time: finishedAt });
		_cacheCurrentExecutionReplay(executionId);
		void _hydrateExecutionReplay(executionId, { useCurrentView: true });
		currentExecutionId = null;
		currentPlatformExecutionId = null;
		setExecStatus('failed', 'Failed');
		enableStart(true);
		_revealExecutionIssue('error', event.error || 'Unknown error');

		// UNLOCK GRAPH after failure
		schemaGraph.api.lock.unlock();
		schemaGraph.eventBus.emit('workflow:failed', event);

		addLog('error', `❌ Workflow failed: ${event.error || 'Unknown error'}`);
	});

	client.on('workflow.cancelled', (event) => {
		if (event.execution_id !== currentExecutionId) return;
		const executionId = event.execution_id;
		const finishedAt = new Date().toISOString();
		if (_executionReplayView) {
			_executionReplayView.status = 'cancelled';
			_executionReplayView.endedAt = finishedAt;
			_executionReplayView.summary = _describeExecutionReplaySummary(_executionReplayView);
		}
		_appendExecutionReplayEvent('warning', 'Workflow cancelled', _formatExecutionReplayDuration(_executionReplayView?.startedAt, finishedAt) || '', { time: finishedAt });
		_cacheCurrentExecutionReplay(executionId);
		void _hydrateExecutionReplay(executionId, { useCurrentView: true });
		currentExecutionId = null;
		currentPlatformExecutionId = null;
		_clearExecutionIssue();
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
		const sourceSessionId = event?.data?.source_session_id || null;
		if (sourceSessionId && sourceSessionId === api?.sessionId) {
			return;
		}

		// Another tab or assistant modified the current workflow — reload it from the server
		try {
			const resp = await api.getWorkflow();
			if (resp?.workflow) {
				if (typeof window.loadWorkflowFromServer === 'function') {
					await window.loadWorkflowFromServer(
						resp.workflow,
						resp.name || visualizer?.currentWorkflowName || 'Workflow',
						{ source: 'assistant' },
					);
				} else {
					await visualizer?.loadWorkflow(resp.workflow, resp.name || visualizer?.currentWorkflowName || 'Workflow');
					addLog('info', `🔄 Current workflow updated by assistant`);
				}
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
		'workflow.started',
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
		_appendExecutionReplayEvent('info', `Node ${idx} started`, label);
		addLog('info', `▶️ [${idx}] ${label}`);
	});

	client.on('node.completed', (event) => {
		if (event.execution_id !== currentExecutionId) return;
		const idx = parseInt(event.node_id);
		const label = event.data?.node_label || `Node ${idx}`;
		const outputs = event.data?.outputs;
		visualizer?.updateNodeState(idx, 'completed');
		if (outputs) {
			if (_executionReplayView) {
				_executionReplayView.nodeOutputs = {
					...(_executionReplayView?.nodeOutputs || {}),
					[String(idx)]: outputs,
				};
			}
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
		if (_executionReplayView) {
			_executionReplayView.summary = _describeExecutionReplaySummary(_executionReplayView);
		}
		_appendExecutionReplayEvent('success', `Node ${idx} completed`, outputs ? `Outputs captured for ${label}` : label);
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
		_appendExecutionReplayEvent('error', `Node ${idx} failed`, `${label}: ${event.error || 'Unknown error'}`, { nodeId: String(idx) });
		addLog('error', `❌ [${idx}] ${label}: ${event.error}`);
	});

	client.on('node.waiting', (event) => {
		if (event.execution_id !== currentExecutionId) return;
		const idx = parseInt(event.node_id);
		const label = event.data?.node_label || `Node ${idx}`;
		const waitType = event.data?.wait_type || 'unknown';
		visualizer?.updateNodeState(idx, 'waiting');
		_appendExecutionReplayEvent('warning', `Node ${idx} waiting`, `${label} (${waitType})`);
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
		_appendExecutionReplayEvent('info', `Node ${idx} resumed`, label);
		addLog('info', `▶️ [${idx}] ${label} resumed`);
	});

	client.on('user_input.requested', (event) => {
		if (!currentExecutionId || event.execution_id !== currentExecutionId) return;
		_appendExecutionReplayEvent('warning', 'User input requested', 'The workflow is waiting for manual input.');
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
		const activeApi = api;
		const [currentResp, listResp] = await Promise.all([
			activeApi.getCurrentSpace(),
			activeApi.listSpaces(),
		]);
		if (!api || api !== activeApi) return;
		const spaces = listResp.spaces || [];
		availableSpaces = spaces;
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
		_syncReuseControls();

		if (loadWorkflow) {
			await loadCurrentWorkflow();
		}
		_updateWorkbenchOverview();
	} catch (error) {
		availableSpaces = [];
		addLog('error', `❌ Failed to refresh spaces: ${error.message}`);
		_updateWorkbenchOverview();
	}
}

async function loadCurrentWorkflow() {
	if (!api) return;

	try {
		const activeApi = api;
		const response = await activeApi.getWorkflow();
		if (!api || api !== activeApi) return;
		const workflow = response?.workflow || null;
		const name = response?.name || 'Untitled';

		// Close transient overlays before replacing the graph.
		schemaGraph.closeAllPreviewTextOverlays?.();
		agentChatManager?.disconnectAll();

		currentExecutionId = null;
		currentPlatformExecutionId = null;
		_latestReplayExecutionId = null;
		$('execId').textContent = '-';
		setExecStatus('idle', 'Not running');
		_resetExecutionReplayView();
		_resetExecutionEvalView();
		_resetExecutionFailureView();
		_resetExecutionComparisonView();

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
		_syncReuseControls();
		_updateStarterExperience(!currentWorkflowHasContent);
		_updateWorkbenchOverview();
	} catch (error) {
		addLog('error', `❌ Failed to load workflow: ${error.message}`);
		_syncReuseControls();
		_updateWorkbenchOverview();
	}
}

window.getNumelWorkbenchContext = function() {
	return {
		space_id: currentSpaceId || '',
		space_title: currentSpaceInfo?.title || currentSpaceInfo?.slug || '',
		workflow_name: _currentWorkflowLabel(),
	};
};

window.openLinkedWorkbench = async function(spaceId, workflowName = '') {
	if (!api || !spaceId) return false;
	try {
		if (workflowDirty && visualizer?.currentWorkflow) {
			await syncWorkflow();
		}
		const response = await api.selectSpace(spaceId);
		currentSpaceInfo = response.space || null;
		currentSpaceId = currentSpaceInfo?.id || spaceId;
		await refreshSpaceList(true);
		addLog('info', `🧭 Opened linked workbench "${currentSpaceInfo?.title || currentSpaceId}"${workflowName ? ` for "${workflowName}"` : ''}`);
		return true;
	} catch (error) {
		addLog('error', `❌ Failed to open linked workbench: ${error.message}`);
		return false;
	}
};

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

async function forkCurrentSpace() {
	if (!api || !currentSpaceId || !currentSpaceInfo) return;
	const sourceTitle = currentSpaceInfo.title || currentSpaceInfo.slug || currentSpaceId;
	const title = await NumelPrompt(
		'Fork Space',
		`Choose a name for the fork of "${_escHtml(sourceTitle)}".`,
		`${sourceTitle} Copy`,
		'Fork',
		`${sourceTitle} Copy`,
	);
	if (title === null || !title.trim()) return;

	try {
		if (workflowDirty && visualizer?.currentWorkflow) {
			await syncWorkflow();
		}
		const nextTitle = title.trim();
		const response = await api.forkSpace(currentSpaceId, nextTitle, _slugFromTitle(nextTitle));
		currentSpaceInfo = response.space || null;
		currentSpaceId = currentSpaceInfo?.id || null;
		await refreshSpaceList(true);
		addLog('success', `🍴 Forked "${sourceTitle}" into "${currentSpaceInfo?.title || nextTitle}"`);
	} catch (error) {
		addLog('error', `❌ Failed to fork space: ${error.message}`);
		await NumelAlert('Fork Space', error.message || 'Failed to fork the current space.');
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
		_syncReuseControls();
		addLog('info', `🧭 Switched to "${currentSpaceInfo?.title || currentSpaceId}"`);
	} catch (error) {
		addLog('error', `❌ Failed to switch space: ${error.message}`);
		await refreshSpaceList(false);
	}
}

async function syncWorkflow(workflow = null, _name = null, force = false, saveOptions = null) {
	if (!force && !workflowDirty) return null;

	schemaGraph.api.lock.lock('Syncing workflow', true, { lockMovement: true, lockOverlays: true });

	try {
		// Save chat state before reload
		const chatState = saveChatState();
		const cameraState = schemaGraph?.api?.view?.getPosition?.() || null;

		// Close all preview text overlays (node IDs will change)
		schemaGraph.closeAllPreviewTextOverlays?.();

		// When an explicit workflow is supplied (starters/import/gallery), preserve
		// that payload for saving so stripped frontend-only display transforms do not
		// collapse the saved workflow into an empty graph.
		const hasExplicitWorkflow = !!workflow;
		const exported = visualizer.exportWorkflow();
		const localWorkflowName = _sanitizeExecutionWorkflowLabel(_name)
			|| _extractWorkflowDisplayName(workflow)
			|| _extractWorkflowDisplayName(exported)
			|| _sanitizeExecutionWorkflowLabel(visualizer?.currentWorkflowName)
			|| _sanitizeExecutionWorkflowLabel($('singleWorkflowName')?.textContent)
			|| '';
		if (!hasExplicitWorkflow && exported) workflow = exported;

		const response = await api.saveWorkflow(workflow, saveOptions || {});

		if (response.status === 'saved') {
			// Clear handlers (node IDs will change)
			agentChatManager?.disconnectAll();

			// Reload entire workflow from backend
			const resolvedWorkflowName = _sanitizeExecutionWorkflowLabel(response?.name)
				|| localWorkflowName
				|| _extractWorkflowDisplayName(response?.workflow)
				|| 'Current workflow';
			if (response.workflow) {
				visualizer.loadWorkflow(response.workflow, resolvedWorkflowName, visualizer.defaultLayout, true);
			}
			_setWorkflowName(resolvedWorkflowName);

			// Restore chat messages
			restoreChatState(chatState);
			if (cameraState && schemaGraph?.api?.view?.setPosition) {
				schemaGraph.api.view.setPosition(cameraState.x, cameraState.y);
				if (typeof cameraState.scale === 'number' && schemaGraph.api.view.setZoom) {
					schemaGraph.api.view.setZoom(cameraState.scale);
				}
				schemaGraph.eventBus.emit('camera:moved');
				schemaGraph.eventBus.emit('camera:zoomed');
			}
			
			currentWorkflowHasContent = _hasWorkflowContent(response.workflow || workflow);
			workflowDirty = false;
			schemaGraph.eventBus.emit('workflow:synced');
			_syncReuseControls();
			_updateStarterExperience(false);
			addLog('success', `✅ Saved "${resolvedWorkflowName}"`);
			return response;
		} else {
			throw new Error('Save failed');
		}
	} finally {
		schemaGraph.api.lock.unlock();
	}
}

async function saveWorkflowToBackend(workflow = null, _name = null, force = false, saveOptions = null) {
	if (!force && !workflowDirty) return null;

	const hasExplicitWorkflow = !!workflow;
	const exported = visualizer?.exportWorkflow?.();
	if (!hasExplicitWorkflow && exported) workflow = exported;
	if (!workflow) return null;

	const response = await api.saveWorkflow(workflow, saveOptions || {});
	if (response?.status !== 'saved') {
		throw new Error('Save failed');
	}

	currentWorkflowHasContent = _hasWorkflowContent(response.workflow || workflow);
	workflowDirty = false;
	_syncReuseControls();
	_updateStarterExperience(false);
	return response;
}

function _currentWorkflowForReuse() {
	const exported = visualizer?.exportWorkflow?.();
	if (exported && _hasWorkflowContent(exported)) return exported;
	return null;
}

function _snapshotHistoryHtml(commits = []) {
	if (!Array.isArray(commits) || !commits.length) {
		return '<div class="nw-snapshot-empty">No workflow snapshots yet. Save a snapshot to start building a reusable history.</div>';
	}
	return `<div class="nw-snapshot-list">${commits.map((commit) => {
		const message = _escHtml(commit?.message || 'Snapshot');
		const commitId = _escHtml(String(commit?.id || '').slice(0, 8) || 'unknown');
		const createdAt = _escHtml(_formatLocalTimestamp(commit?.created_at));
		const changedPaths = Array.isArray(commit?.changed_paths) && commit.changed_paths.length
			? commit.changed_paths.map((path) => `<span class="nw-snapshot-path">${_escHtml(path)}</span>`).join('')
			: '<span class="nw-snapshot-path">workflow.json</span>';
		return `
			<div class="nw-snapshot-card">
				<div class="nw-snapshot-head">
					<div class="nw-snapshot-message">${message}</div>
					<div class="nw-snapshot-id">${commitId}</div>
				</div>
				<div class="nw-snapshot-meta">${createdAt}</div>
				<div class="nw-snapshot-paths">${changedPaths}</div>
			</div>
		`;
	}).join('')}</div>`;
}

function _showWorkflowSnapshotsDialog(commits = []) {
	return new Promise((resolve) => {
		const overlay = document.createElement('div');
		overlay.className = 'sg-input-dialog-overlay';
		overlay.innerHTML = `
			<div class="sg-input-dialog nw-snapshot-dialog">
				<div class="sg-input-dialog-header">
					<span class="sg-input-dialog-title">Workflow Snapshots</span>
					<button class="sg-input-dialog-close">✕</button>
				</div>
				<div class="sg-input-dialog-body">
					<p class="sg-confirm-dialog-message">Review recent workflow snapshots for the current space. Restore one when you want to bring that version back into the workbench.</p>
					${Array.isArray(commits) && commits.length ? `<div class="nw-snapshot-list">${commits.map((commit) => {
						const message = _escHtml(commit?.message || 'Snapshot');
						const commitId = String(commit?.id || '').trim();
						const shortCommitId = _escHtml(commitId.slice(0, 8) || 'unknown');
						const createdAt = _escHtml(_formatLocalTimestamp(commit?.created_at));
						const changedPaths = Array.isArray(commit?.changed_paths) && commit.changed_paths.length
							? commit.changed_paths.map((path) => `<span class="nw-snapshot-path">${_escHtml(path)}</span>`).join('')
							: '<span class="nw-snapshot-path">workflow.json</span>';
						return `
							<div class="nw-snapshot-card">
								<div class="nw-snapshot-head">
									<div class="nw-snapshot-message">${message}</div>
									<div class="nw-snapshot-id">${shortCommitId}</div>
								</div>
								<div class="nw-snapshot-meta">${createdAt}</div>
								<div class="nw-snapshot-paths">${changedPaths}</div>
								<div class="nw-snapshot-actions">
									<button class="nw-btn nw-btn-sm nw-btn-secondary" type="button" data-action="restore-snapshot" data-commit-id="${_escHtml(commitId)}" data-message="${message}">Restore</button>
								</div>
							</div>
						`;
					}).join('')}</div>` : '<div class="nw-snapshot-empty">No workflow snapshots yet. Save a snapshot to start building a reusable history.</div>'}
				</div>
				<div class="sg-input-dialog-footer">
					<button class="sg-input-dialog-btn sg-input-dialog-confirm">Close</button>
				</div>
			</div>
		`;
		document.body.appendChild(overlay);

		const close = (value = null) => {
			overlay.remove();
			resolve(value);
		};

		overlay.querySelector('.sg-input-dialog-close')?.addEventListener('click', () => close(null));
		overlay.querySelector('.sg-input-dialog-confirm')?.addEventListener('click', () => close(null));
		overlay.addEventListener('click', (event) => {
			if (event.target === overlay) close(null);
		});
		overlay.addEventListener('keydown', (event) => {
			if (event.key === 'Escape') {
				event.preventDefault();
				close(null);
			}
		});
		overlay.querySelectorAll('[data-action="restore-snapshot"]').forEach((button) => {
			button.addEventListener('click', () => close({
				action: 'restore',
				commitId: button.getAttribute('data-commit-id') || '',
				message: button.getAttribute('data-message') || 'Snapshot',
			}));
		});
		queueMicrotask(() => {
			overlay.querySelector('.sg-input-dialog-confirm')?.focus();
		});
	});
}

async function _restoreWorkflowSnapshot(commitId, snapshotLabel = 'Snapshot') {
	if (!api || !currentSpaceId || !commitId) return false;
	const warning = workflowDirty
		? 'Current unsaved edits will be saved first, then the selected snapshot will replace the current workflow.'
		: 'The selected snapshot will replace the current workflow in this space.';
	const ok = await NumelConfirm(
		'Restore Snapshot',
		`Restore "${_escHtml(snapshotLabel)}"? ${warning}`,
		'Restore Snapshot',
		false,
		'Keep Current Workflow',
	);
	if (!ok) return false;

	try {
		if (workflowDirty && visualizer?.currentWorkflow) {
			await syncWorkflow();
		}
		const response = await api.restoreWorkflowSnapshot(commitId);
		const restoredName = response?.name || _currentWorkflowLabel() || 'Restored Workflow';
		const workflow = response?.workflow || null;
		if (workflow) {
			agentChatManager?.disconnectAll();
			visualizer.loadWorkflow(workflow, restoredName, visualizer.defaultLayout, true);
			_setWorkflowName(restoredName);
		}
		currentExecutionId = null;
		currentPlatformExecutionId = null;
		_latestReplayExecutionId = null;
		$('execId').textContent = '-';
		setExecStatus('idle', 'Not running');
		_resetExecutionReplayView();
		_resetExecutionEvalView();
		_resetExecutionFailureView();
		_resetExecutionComparisonView();
		currentWorkflowHasContent = _hasWorkflowContent(workflow);
		workflowDirty = false;
		enableStart(true);
		updateClearButtonState();
		_updateStarterExperience(false);
		_updateWorkbenchOverview();
		addLog('success', `↩ Restored snapshot "${snapshotLabel}"`);
		await NumelAlert('Snapshot Restored', `"${_escHtml(restoredName)}" is now back in the current workbench.`);
		return true;
	} catch (error) {
		addLog('error', `❌ Failed to restore snapshot: ${error.message}`);
		await NumelAlert('Restore Snapshot', error.message || 'Failed to restore workflow snapshot.');
		return false;
	}
}

async function saveWorkflowSnapshot() {
	if (!api) return;
	const workflow = _currentWorkflowForReuse();
	if (!workflow) {
		await NumelAlert('Save Snapshot', 'Load or build a workflow first, then save a snapshot with a version note.');
		return;
	}
	const defaultNote = `Snapshot · ${new Date().toLocaleString()}`;
	const note = await NumelPrompt(
		'Save Snapshot',
		'Add a short version note for this workflow snapshot.',
		defaultNote,
		'Save Snapshot',
		'Snapshot · describe what changed',
	);
	if (note === null) return;
	const trimmedNote = note.trim();
	if (!trimmedNote) {
		await NumelAlert('Save Snapshot', 'Please enter a short snapshot note.');
		return;
	}
	try {
		const response = await syncWorkflow(workflow, _currentWorkflowLabel(), true, { message: trimmedNote });
		addLog('success', `🧷 Snapshot saved: ${trimmedNote}`);
		if (response?.message) {
			await NumelAlert('Snapshot Saved', `Saved a new workflow snapshot for "${_escHtml(response.name || _currentWorkflowLabel())}".`);
		}
	} catch (error) {
		addLog('error', `❌ Failed to save snapshot: ${error.message}`);
		await NumelAlert('Save Snapshot', error.message || 'Failed to save workflow snapshot.');
	}
}

async function showWorkflowSnapshots() {
	if (!api || !currentSpaceId) return;
	try {
		const response = await api.workflowHistory(20);
		const commits = response?.commits || [];
		const action = await _showWorkflowSnapshotsDialog(commits);
		if (action?.action === 'restore' && action.commitId) {
			await _restoreWorkflowSnapshot(action.commitId, action.message || 'Snapshot');
		}
		addLog('info', `🕘 Reviewed ${commits.length} workflow snapshot${commits.length === 1 ? '' : 's'}`);
	} catch (error) {
		addLog('error', `❌ Failed to load workflow snapshots: ${error.message}`);
		await NumelAlert('Workflow Snapshots', error.message || 'Failed to load workflow snapshots.');
	}
}

async function publishCurrentWorkflowTemplate() {
	if (!api) return;
	const workflow = _currentWorkflowForReuse();
	if (!workflow) {
		await NumelAlert('Publish Template', 'Load or build a workflow first, then publish it as a reusable template.');
		return;
	}
	const defaultTitle = _currentWorkflowLabel() || currentSpaceInfo?.title || 'Untitled Template';
	const title = await NumelPrompt(
		'Publish Template',
		'Choose the gallery title for this reusable workflow template.',
		defaultTitle,
		'Publish',
		'Template title',
	);
	if (title === null) return;
	const trimmedTitle = title.trim();
	if (!trimmedTitle) {
		await NumelAlert('Publish Template', 'Please enter a template title.');
		return;
	}
	try {
		const description = currentSpaceInfo?.title
			? `Reusable workflow template published from the "${currentSpaceInfo.title}" workbench.`
			: 'Reusable workflow template published from the current workbench.';
		const item = await api.galleryPublish({
			workflow,
			title: trimmedTitle,
			description,
			category: 'templates',
			tags: ['template', 'reusable'],
		});
		addLog('success', `📚 Published template "${trimmedTitle}"`);
		await NumelAlert(
			'Template Published',
			`"${_escHtml(trimmedTitle)}" is now available in the gallery as a reusable template.`,
		);
		if (galleryManager?.open) {
			await galleryManager.open();
		}
		return item;
	} catch (error) {
		addLog('error', `❌ Failed to publish template: ${error.message}`);
		await NumelAlert('Publish Template', error.message || 'Failed to publish template.');
		return null;
	}
}

// Global helper for console /gen — load + sync a workflow JSON object
window.loadAndSyncWorkflow = async function(workflow, name) {
	if (!visualizer || !schemaGraph) return;
	_hideStarterFollowthrough();
	let preparedWorkflow = workflow;
	if (api?.validateWorkflow) {
		const validation = await api.validateWorkflow(workflow, { apply_repairs: true });
		preparedWorkflow = validation.workflow || workflow;
		for (const repair of validation.repairs || []) {
			addLog('info', `🛠 ${repair}`);
		}
		for (const warning of validation.warnings || []) {
			addLog('warning', `⚠️ ${warning}`);
		}
	}
	schemaGraph.api.graph.clear();
	schemaGraph.api.view.reset();
	const n = name || preparedWorkflow?.options?.name || 'Generated Workflow';
	const loaded = visualizer.loadWorkflow(preparedWorkflow, n);
	if (loaded) {
		_latestReplayExecutionId = null;
		_resetExecutionReplayView();
		_resetExecutionEvalView();
		_resetExecutionFailureView();
		_resetExecutionComparisonView();
		currentWorkflowHasContent = _hasWorkflowContent(preparedWorkflow);
		await syncWorkflow(preparedWorkflow, n, true);
		enableStart(true);
		_updateStarterExperience(false);
		addLog('success', `✅ Loaded "${visualizer.currentWorkflowName}"`);
	}
};

window.loadWorkflowFromServer = async function(workflow, name, { source = 'assistant' } = {}) {
	if (!visualizer || !schemaGraph || !workflow) return false;
	_hideStarterFollowthrough();
	const chatState = saveChatState();
	schemaGraph.closeAllPreviewTextOverlays?.();
	agentChatManager?.disconnectAll();
	const workflowName = name || workflow?.options?.name || visualizer.currentWorkflowName || 'Workflow';
	const loaded = visualizer.loadWorkflow(workflow, workflowName, visualizer.defaultLayout, true);
	if (!loaded) return false;
	restoreChatState(chatState);
	_latestReplayExecutionId = null;
	_resetExecutionReplayView();
	_resetExecutionEvalView();
	_resetExecutionFailureView();
	_resetExecutionComparisonView();
	currentWorkflowHasContent = _hasWorkflowContent(workflow);
	workflowDirty = false;
	enableStart(true);
	_updateStarterExperience(false);
	addLog('info', `🔄 Current workflow updated by ${source}`);
	return true;
};

window.exportCurrentWorkflowForAssistant = function() {
	if (!visualizer?.exportWorkflow) return null;
	return visualizer.exportWorkflow();
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
			inputValue: node._chatInputValue || '',
			chatState: node.chatState || 'idle',
			chatError: node.chatError || null,
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
		node.chatState = saved.chatState || node.chatState || 'idle';
		node.chatError = saved.chatError || null;
		
		// Update overlay - it will use the current node reference
		schemaGraph.chatManager?.overlayManager?.updateMessages(node);
		schemaGraph.chatManager?.overlayManager?.updateStatus(node);
		
		const overlay = schemaGraph.chatManager?.overlayManager?.overlays?.get(key);
		const input = overlay?.querySelector('.sg-chat-input');
		if (input) {
			input.value = saved.inputValue || '';
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
		const validation = api?.validateWorkflow
			? await api.validateWorkflow(workflow, { apply_repairs: true })
			: { workflow, repairs: [], warnings: [] };
		const preparedWorkflow = validation.workflow || workflow;
		for (const repair of validation.repairs || []) {
			addLog('info', `🛠 ${repair}`);
		}
		for (const warning of validation.warnings || []) {
			addLog('warning', `⚠️ ${warning}`);
		}

		// Clear current workflow
		schemaGraph.api.graph.clear();
		schemaGraph.api.view.reset();

		// Validate
		const name      = preparedWorkflow?.options?.name || file.name.replace('.json', '');
		const validated = visualizer.loadWorkflow(preparedWorkflow, name);
		if (validated) {
			await syncWorkflow(preparedWorkflow, name, true);
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
			await syncWorkflow(workflow, name, true);
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
	const hasNodes = schemaGraph?.graph?.nodes?.length > 0;
	const hasContent = !!(visualizer?.currentWorkflow && (hasNodes || currentWorkflowHasContent));
	if (!hasContent) return;

	const confirmClear = typeof window.NumelConfirm === 'function'
		? await window.NumelConfirm(
			'Clear Workflow',
			'This will clear the current workflow from this workbench and save the empty result. Continue?',
			'Clear Workflow',
			true,
			'Keep Workflow',
		)
		: window.confirm('Clear the current workflow from this workbench?');
	if (!confirmClear) return;

	// Snapshot the pre-clear graph state AND camera so a single undo
	// restores both the workflow and the original view.
	const beforeSnapshot = schemaGraph?._captureCurrentSnapshot?.();
	const cameraBefore = schemaGraph?.camera
		? { x: schemaGraph.camera.x, y: schemaGraph.camera.y, scale: schemaGraph.camera.scale }
		: null;

	// Snapshot the existing undo/redo stacks so we can fully restore them
	// after clear+sync, wiping any intermediate entries the subsystem added,
	// then push exactly ONE 'Clear Workflow' command on top.
	const histMgr = schemaGraph?.history;
	const savedUndoStack = histMgr ? histMgr.undoStack.slice() : null;
	const savedRedoStack = histMgr ? histMgr.redoStack.slice() : null;

	try {
		schemaGraph.api.lock.lock('Clearing workflow');
		schemaGraph.closeAllPreviewTextOverlays?.();
		// Suppress all event-bus-driven commits during clear+sync.
		schemaGraph._historyIgnore = true;
		schemaGraph.api.graph.clear();
		schemaGraph.api.view.reset();
		visualizer.initEmptyWorkflow();
		visualizer.graphNodes = [];
		_setWorkflowName(visualizer.currentWorkflowName || 'Untitled');
		currentWorkflowHasContent = false;
		workflowDirty = true;
		await syncWorkflow(visualizer.exportWorkflow(), null, true);

		// Flush any pending field-change debounce so it can't fire a
		// delayed history.push after we restore.
		if (schemaGraph?._fieldChangeTimer) {
			clearTimeout(schemaGraph._fieldChangeTimer);
			schemaGraph._fieldChangeTimer = null;
			schemaGraph._fieldChangeBefore = null;
		}
		schemaGraph._historyIgnore = false;

		const afterSnapshot = schemaGraph?._captureCurrentSnapshot?.();
		const cameraAfter = schemaGraph?.camera
			? { x: schemaGraph.camera.x, y: schemaGraph.camera.y, scale: schemaGraph.camera.scale }
			: null;

		// Hard reset the stacks to their pre-clear state — this discards
		// any phantom entries added by graph.clear / loadWorkflow /
		// layout apply / deferred 50ms completeness refreshes — then push
		// exactly one 'Clear Workflow' command.
		if (histMgr && beforeSnapshot && afterSnapshot) {
			histMgr.undoStack = savedUndoStack;
			histMgr.redoStack = savedRedoStack;
			const cmd = {
				label: 'Clear Workflow',
				undo(app) {
					app._historyRestore(beforeSnapshot);
					if (cameraBefore && app.camera) {
						app.camera.x = cameraBefore.x;
						app.camera.y = cameraBefore.y;
						app.camera.scale = cameraBefore.scale;
					}
					app.draw?.();
				},
				redo(app) {
					app._historyRestore(afterSnapshot);
					if (cameraAfter && app.camera) {
						app.camera.x = cameraAfter.x;
						app.camera.y = cameraAfter.y;
						app.camera.scale = cameraAfter.scale;
					}
					app.draw?.();
				},
			};
			histMgr.push(cmd);
			schemaGraph._currentStateSnapshot = afterSnapshot;
			schemaGraph._updateHistoryButtons?.();
		}

		// Schedule one more stack repair on the next macrotask so any
		// setTimeout-deferred pushes (e.g. 50ms completeness refresh,
		// async import follow-ups) that slip past _historyIgnore still
		// get scrubbed — keep our single 'Clear Workflow' entry on top.
		if (histMgr) {
			const expectedTop = histMgr.undoStack[histMgr.undoStack.length - 1];
			setTimeout(() => {
				if (!histMgr) return;
				const idx = histMgr.undoStack.indexOf(expectedTop);
				if (idx >= 0 && idx < histMgr.undoStack.length - 1) {
					// Extra entries were appended after our cmd — drop them.
					histMgr.undoStack = histMgr.undoStack.slice(0, idx + 1);
					histMgr.redoStack = [];
					schemaGraph._updateHistoryButtons?.();
				}
			}, 100);
		}

		enableStart(true);
		updateClearButtonState();
		_updateStarterExperience(!_hasShownStarterThisLogin());
		_latestReplayExecutionId = null;
		_resetExecutionReplayView('Workflow cleared. Run a workflow again or replay the latest run in this space.');
		_resetExecutionEvalView('Workflow cleared. Run a workflow again or replay a past run to see eval scores.');
		_resetExecutionFailureView('Workflow cleared. Run a workflow again or replay a failed run to inspect failure context.');
		_resetExecutionComparisonView('Workflow cleared. Compare runs again after you run a workflow more than once.');
		addLog('info', '🧹 Workflow cleared');
	} finally {
		schemaGraph._historyIgnore = false;
		schemaGraph.api.lock.unlock();
	}
}

// ========================================================================
// Execution Control
// ========================================================================

async function startExecution() {
	if (!client || !visualizer?.currentWorkflow) {
		_revealExecutionIssue('error', 'No workflow loaded');
		addLog('error', '⚠️ No workflow loaded');
		return;
	}

	// Validate workflow before starting
	const validation = schemaGraph.api.workflow.validate();
	if (!validation.valid) {
		setExecStatus('failed', 'Validation failed');
		_revealExecutionIssue('error', validation.errors.join('\n'));
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
		_clearExecutionIssue();

		if (consoleManager?.isPlannerEnabled?.()) {
			const paused = await consoleManager.disablePlannerForManualRun();
			if (paused) {
				addLog('info', '🧠 Planner paused for manual run');
			}
		}

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
		_beginExecutionReplay(currentExecutionId, currentPlatformExecutionId, workflowName);

		// Replay any events that arrived during the POST
		_flushPendingExecEvents();

	} catch (error) {
		_pendingExecEvents = [];
		currentExecutionId = null;
		currentPlatformExecutionId = null;
		_resetExecutionReplayView(`Could not start "${visualizer?.currentWorkflowName || 'Workflow'}": ${error.message}`);
		enableStart(true);
		setExecStatus('failed', 'Start failed');
		_revealExecutionIssue('error', error.message || 'Unknown error');
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
		_appendExecutionReplayEvent('warning', 'Cancellation requested', 'Waiting for the workflow to stop.');
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

function _executionReplayTypeForStatus(status) {
	switch (String(status || '').toLowerCase()) {
		case 'completed':
			return 'success';
		case 'failed':
			return 'error';
		case 'cancelled':
			return 'warning';
		case 'running':
		case 'starting':
			return 'info';
		default:
			return 'info';
	}
}

function _createEmptyExecutionReplayView(message = 'Run the current workflow to build a live timeline, or replay the latest run in this space.') {
	return {
		executionId: null,
		platformExecutionId: null,
		workflowName: '',
		status: 'idle',
		startedAt: null,
		endedAt: null,
		error: '',
		nodeOutputs: {},
		events: [],
		source: 'empty',
		summary: message,
	};
}

function _createEmptyExecutionComparisonView(message = 'Compare the latest two runs in this space to see what changed.') {
	return {
		latestExecutionId: null,
		previousExecutionId: null,
		type: 'empty',
		summary: message,
		items: [],
	};
}

function _createEmptyExecutionEvalView(message = 'Any eval scores from the current or replayed run will appear here.') {
	return {
		type: 'empty',
		summary: message,
		items: [],
		source: 'empty',
	};
}

function _createEmptyExecutionFailureView(message = 'If a run fails, Numel will summarize the failing step and the most useful nearby context here.') {
	return {
		type: 'empty',
		summary: message,
		items: [],
		source: 'empty',
	};
}

function _cloneExecutionReplayView(view) {
	return {
		...view,
		metadata: { ...(view?.metadata || {}) },
		nodeOutputs: { ...(view?.nodeOutputs || {}) },
		events: Array.isArray(view?.events) ? view.events.map((entry) => ({ ...entry })) : [],
	};
}

function _cloneExecutionEvalView(view) {
	return {
		...view,
		items: Array.isArray(view?.items) ? view.items.map((entry) => ({ ...entry })) : [],
	};
}

function _cloneExecutionFailureView(view) {
	return {
		...view,
		items: Array.isArray(view?.items) ? view.items.map((entry) => ({ ...entry })) : [],
	};
}

function _cloneExecutionComparisonView(view) {
	return {
		...view,
		items: Array.isArray(view?.items) ? view.items.map((entry) => ({ ...entry })) : [],
	};
}

function _formatExecutionReplayTime(value) {
	if (!value) return '--:--:--';
	const timeMs = _coerceExecutionTimeMs(value);
	if (timeMs === null) return String(value);
	const date = new Date(timeMs);
	return date.toLocaleTimeString('en-US', { hour12: false });
}

function _formatExecutionDurationMs(diffMs) {
	if (!Number.isFinite(diffMs)) return '';
	const safeMs = Math.max(0, diffMs);
	if (safeMs < 1000) return `${Math.round(safeMs)}ms`;
	const totalSeconds = safeMs / 1000;
	if (totalSeconds < 60) return `${totalSeconds.toFixed(totalSeconds >= 10 ? 0 : 1)}s`;
	const minutes = Math.floor(totalSeconds / 60);
	const seconds = Math.round(totalSeconds % 60);
	if (minutes < 60) return `${minutes}m ${seconds}s`;
	const hours = Math.floor(minutes / 60);
	return `${hours}h ${minutes % 60}m`;
}

function _coerceExecutionTimeMs(value) {
	if (value === null || value === undefined || value === '') return null;
	if (value instanceof Date) {
		const time = value.getTime();
		return Number.isFinite(time) ? time : null;
	}
	if (typeof value === 'number' && Number.isFinite(value)) {
		return value < 1e12 ? value * 1000 : value;
	}
	if (typeof value === 'string') {
		const text = value.trim();
		if (!text) return null;
		const numeric = Number(text);
		if (Number.isFinite(numeric)) {
			return numeric < 1e12 ? numeric * 1000 : numeric;
		}
		const parsed = Date.parse(text);
		return Number.isFinite(parsed) ? parsed : null;
	}
	return null;
}

function _isExecutionTerminalStatus(status) {
	return ['completed', 'failed', 'cancelled'].includes(String(status || '').toLowerCase());
}

function _normalizeExecutionStatus(status, { endTime = null, error = '' } = {}) {
	const normalized = String(status || '').toLowerCase() || 'idle';
	if ((normalized === 'running' || normalized === 'starting') && _coerceExecutionTimeMs(endTime) !== null) {
		return String(error || '').trim() ? 'failed' : 'completed';
	}
	return normalized;
}

function _formatExecutionReplayDuration(startValue, endValue = null) {
	if (startValue === null || startValue === undefined || startValue === '') return '';
	const startMs = _coerceExecutionTimeMs(startValue);
	const endMs = endValue === null || endValue === undefined || endValue === ''
		? Date.now()
		: _coerceExecutionTimeMs(endValue);
	if (startMs === null || endMs === null) return '';
	return _formatExecutionDurationMs(endMs - startMs);
}

function _executionNodeLabel(nodeId, fallbackLabel = '') {
	const idx = Number.parseInt(nodeId, 10);
	if (Number.isFinite(idx)) {
		const graphNode = visualizer?.graphNodes?.[idx];
		const directLabel = graphNode?.title || graphNode?.label || graphNode?.data?.label || graphNode?.data?.title;
		if (directLabel) return String(directLabel);
		return fallbackLabel || `Node ${idx}`;
	}
	return fallbackLabel || String(nodeId || 'Node');
}

function _summarizeExecutionOutputs(nodeOutputs = {}) {
	const entries = Object.entries(nodeOutputs || {});
	if (!entries.length) {
		return { count: 0, text: 'No node outputs were captured.' };
	}
	const labels = entries.slice(0, 4).map(([nodeId]) => `[${nodeId}] ${_executionNodeLabel(nodeId)}`);
	const extra = entries.length > labels.length ? `, +${entries.length - labels.length} more` : '';
	return {
		count: entries.length,
		text: `${entries.length} node${entries.length === 1 ? '' : 's'} produced outputs: ${labels.join(', ')}${extra}`,
	};
}

function _describeExecutionReplaySummary(view) {
	if (!view?.executionId) {
		return view?.summary || 'Run the current workflow to build a live timeline, or replay the latest run in this space.';
	}
	const status = String(view.status || 'idle').toLowerCase();
	const statusLabels = {
		starting: 'Preparing live timeline',
		running: 'Running',
		completed: 'Completed',
		failed: 'Failed',
		cancelled: 'Cancelled',
		idle: 'Idle',
	};
	const scope = view.source === 'replay' ? 'Latest replay' : 'Live timeline';
	const parts = [`${scope}: ${statusLabels[status] || view.status || 'Run'}`];
	if (view.workflowName) parts.push(view.workflowName);
	const duration = _formatExecutionReplayDuration(view.startedAt, view.endedAt);
	if (duration) parts.push(duration);
	const outputSummary = _summarizeExecutionOutputs(view.nodeOutputs);
	if (outputSummary.count) parts.push(`${outputSummary.count} node output${outputSummary.count === 1 ? '' : 's'}`);
	if (view.error) parts.push(view.error);
	return parts.join(' · ');
}

function _stableExecutionValue(value) {
	if (Array.isArray(value)) {
		return value.map((item) => _stableExecutionValue(item));
	}
	if (value && typeof value === 'object') {
		return Object.keys(value)
			.sort()
			.reduce((acc, key) => {
				acc[key] = _stableExecutionValue(value[key]);
				return acc;
			}, {});
	}
	return value;
}

function _stringifyExecutionValue(value) {
	try {
		return JSON.stringify(_stableExecutionValue(value));
	} catch (_error) {
		return String(value);
	}
}

function _previewExecutionValue(value, maxLength = 160) {
	const text = _stringifyExecutionValue(value);
	if (text.length <= maxLength) return text;
	return `${text.slice(0, maxLength - 1)}…`;
}

function _parseExecutionTimeValue(value) {
	return _coerceExecutionTimeMs(value);
}

function _looksInternalWorkflowName(value) {
	const text = String(value || '').trim();
	if (!text) return false;
	return /^space_[a-f0-9]+_workflow(?:\.json)?_[a-f0-9]+$/i.test(text)
		|| /^workflow_exec_[a-f0-9]+$/i.test(text);
}

function _sanitizeExecutionWorkflowLabel(value) {
	const text = String(value || '').trim();
	if (!text) return '';
	if (_looksInternalWorkflowName(text)) return '';
	if (['workflow', 'untitled', 'none'].includes(text.toLowerCase())) return '';
	return text;
}

function _executionWorkflowLabel(results, fallback = '') {
	const metadata = results?.metadata || {};
	const metadataLabel = _sanitizeExecutionWorkflowLabel(metadata?.workflow_name);
	if (metadataLabel) return metadataLabel;
	const fallbackLabel = _sanitizeExecutionWorkflowLabel(fallback);
	if (fallbackLabel) return fallbackLabel;
	const currentLabel = _sanitizeExecutionWorkflowLabel(_currentWorkflowLabel());
	if (currentLabel) {
		const workflowId = String(results?.workflow_id || '').trim().replace(/\\/g, '/');
		if (!workflowId || workflowId.toLowerCase() === 'current_workflow.json') {
			return currentLabel;
		}
	}
	const workflowId = String(results?.workflow_id || '').trim();
	if (!workflowId) return 'Current workflow';
	const normalized = workflowId.replace(/\\/g, '/');
	const pieces = normalized.split('/').filter(Boolean);
	const assetLabel = pieces[pieces.length - 1] || workflowId;
	if (assetLabel.toLowerCase() === 'current_workflow.json') return 'Current workflow';
	return _sanitizeExecutionWorkflowLabel(assetLabel) || 'Current workflow';
}

function _mergeExecutionResultsWithReplayView(results, existingView) {
	if (!existingView) return results || {};
	const merged = { ...(results || {}) };
	const cachedStatus = _normalizeExecutionStatus(existingView.status, {
		endTime: existingView.endedAt,
		error: existingView.error,
	});
	const resultStatus = _normalizeExecutionStatus(merged.status, {
		endTime: merged.end_time,
		error: merged.error,
	});
	if (_isExecutionTerminalStatus(cachedStatus) && !_isExecutionTerminalStatus(resultStatus)) {
		merged.status = cachedStatus;
	}
	if ((merged.start_time === null || merged.start_time === undefined || merged.start_time === '') && existingView.startedAt != null) {
		merged.start_time = existingView.startedAt;
	}
	if ((merged.end_time === null || merged.end_time === undefined || merged.end_time === '') && existingView.endedAt != null) {
		merged.end_time = existingView.endedAt;
	}
	if (!merged.error && existingView.error) {
		merged.error = existingView.error;
	}
	if ((!merged.node_outputs || !Object.keys(merged.node_outputs).length) && Object.keys(existingView.nodeOutputs || {}).length) {
		merged.node_outputs = { ...(existingView.nodeOutputs || {}) };
	}
	merged.metadata = {
		...(existingView.metadata || {}),
		...(merged.metadata || {}),
	};
	if (!merged.workflow_id && existingView.workflowId) {
		merged.workflow_id = existingView.workflowId;
	}
	if (!merged.execution_id && existingView.executionId) {
		merged.execution_id = existingView.executionId;
	}
	if (!merged.platform_execution_id && existingView.platformExecutionId) {
		merged.platform_execution_id = existingView.platformExecutionId;
	}
	return merged;
}

function _formatExecutionStatusLabel(status) {
	const labels = {
		completed: 'Completed',
		failed: 'Failed',
		cancelled: 'Cancelled',
		running: 'Running',
		starting: 'Starting',
		idle: 'Idle',
	};
	return labels[String(status || '').toLowerCase()] || String(status || 'Unknown');
}

function _coerceExecutionScore(score) {
	if (typeof score === 'number' && Number.isFinite(score)) return score;
	if (typeof score === 'string' && score.trim()) {
		const parsed = Number.parseFloat(score);
		return Number.isFinite(parsed) ? parsed : null;
	}
	return null;
}

function _executionEvalTypeForScore(score) {
	if (score === null || score === undefined) return 'info';
	if (score >= 0.8) return 'success';
	if (score >= 0.6) return 'info';
	if (score >= 0.4) return 'warning';
	return 'error';
}

function _extractExecutionEvalItems(nodeOutputs = {}) {
	return Object.entries(nodeOutputs || {})
		.filter(([, outputs]) => outputs && typeof outputs === 'object' && Object.prototype.hasOwnProperty.call(outputs, 'score'))
		.map(([nodeId, outputs]) => {
			const score = _coerceExecutionScore(outputs?.score);
			const feedback = String(outputs?.feedback || '')
				.replace(/\s+/g, ' ')
				.trim();
			return {
				nodeId: String(nodeId),
				label: _executionNodeLabel(nodeId),
				score,
				scoreText: score === null ? 'n/a' : score.toFixed(3),
				feedback,
				type: _executionEvalTypeForScore(score),
			};
		})
		.sort((a, b) => Number(a.nodeId) - Number(b.nodeId));
}

function _describeExecutionEvalSummary(view) {
	if (!view?.items?.length) {
		return view?.summary || 'Any eval scores from the current or replayed run will appear here.';
	}
	const numericScores = view.items.map((item) => item.score).filter((score) => typeof score === 'number');
	const average = numericScores.length
		? numericScores.reduce((total, score) => total + score, 0) / numericScores.length
		: null;
	const sourceLabel = view.source === 'replay' ? 'Replayed run' : 'Current run';
	const parts = [`${sourceLabel}: ${view.items.length} eval result${view.items.length === 1 ? '' : 's'}`];
	if (average !== null) {
		parts.push(`avg ${average.toFixed(3)}`);
	}
	const needsAttention = view.items.filter((item) => item.score !== null && item.score < 0.6).length;
	if (needsAttention) {
		parts.push(`${needsAttention} below 0.600`);
	}
	return parts.join(' · ');
}

function _describeExecutionFailureSummary(view) {
	if (!view?.items?.length) {
		return view?.summary || 'If a run fails, Numel will summarize the failing step and the most useful nearby context here.';
	}
	const sourceLabel = view.source === 'replay' ? 'Replayed failure' : 'Current failure';
	const parts = [sourceLabel];
	const primary = view.items[0];
	if (primary?.title) parts.push(primary.title);
	if (primary?.detail) parts.push(primary.detail);
	return parts.join(' · ');
}

function _formatExecutionComparisonDurationDelta(latestResults, previousResults) {
	const latestStart = _parseExecutionTimeValue(latestResults?.start_time);
	const latestEnd = _parseExecutionTimeValue(latestResults?.end_time);
	const previousStart = _parseExecutionTimeValue(previousResults?.start_time);
	const previousEnd = _parseExecutionTimeValue(previousResults?.end_time);
	if (latestStart === null || latestEnd === null || previousStart === null || previousEnd === null) {
		return '';
	}
	const latestMs = Math.max(0, latestEnd - latestStart);
	const previousMs = Math.max(0, previousEnd - previousStart);
	const deltaMs = latestMs - previousMs;
	if (!deltaMs) {
		return `Both runs took ${_formatExecutionReplayDuration(latestResults.start_time, latestResults.end_time)}.`;
	}
	const direction = deltaMs > 0 ? 'slower' : 'faster';
	const absDelta = Math.abs(deltaMs);
	const latestText = _formatExecutionReplayDuration(latestResults.start_time, latestResults.end_time);
	const previousText = _formatExecutionReplayDuration(previousResults.start_time, previousResults.end_time);
	return `Latest run was ${_formatExecutionDurationMs(absDelta)} ${direction} (${latestText} vs ${previousText}).`;
}

function _syncReplayButtonState() {
	for (const id of ['replayLatestRunBtn', 'compareLatestRunsBtn']) {
		const button = $(id);
		if (!button) continue;
		button.disabled = !api;
	}
}

function _renderExecutionReplayView() {
	const summaryEl = $('execReplaySummary');
	const timelineEl = $('execTimeline');
	if (!summaryEl || !timelineEl) return;
	const view = _executionReplayView || _createEmptyExecutionReplayView();
	const summaryType = _executionReplayTypeForStatus(view.status);
	summaryEl.className = view.executionId
		? `nw-run-summary ${summaryType}`
		: 'nw-run-summary empty';
	summaryEl.textContent = _describeExecutionReplaySummary(view);

	timelineEl.innerHTML = '';
	const events = Array.isArray(view.events) ? view.events : [];
	if (!events.length) {
		const empty = document.createElement('div');
		empty.className = 'nw-exec-timeline-empty';
		empty.textContent = view.executionId
			? 'Waiting for execution events...'
			: 'No run timeline yet.';
		timelineEl.appendChild(empty);
		return;
	}

	for (const entry of events) {
		const item = document.createElement('div');
		item.className = `nw-exec-timeline-item ${entry.type || 'info'}`;

		const marker = document.createElement('div');
		marker.className = 'nw-exec-timeline-marker';
		item.appendChild(marker);

		const body = document.createElement('div');
		body.className = 'nw-exec-timeline-body';

		const head = document.createElement('div');
		head.className = 'nw-exec-timeline-head';

		const time = document.createElement('span');
		time.className = 'nw-exec-timeline-time';
		time.textContent = _formatExecutionReplayTime(entry.time);
		head.appendChild(time);

		const title = document.createElement('span');
		title.className = 'nw-exec-timeline-title';
		title.textContent = entry.title || 'Execution event';
		head.appendChild(title);

		body.appendChild(head);

		if (entry.detail) {
			const detail = document.createElement('div');
			detail.className = 'nw-exec-timeline-detail';
			detail.textContent = entry.detail;
			body.appendChild(detail);
		}

		item.appendChild(body);
		timelineEl.appendChild(item);
	}

	timelineEl.scrollTop = timelineEl.scrollHeight;
}

function _renderExecutionEvalView() {
	const summaryEl = $('execEvalSummary');
	const listEl = $('execEvalList');
	if (!summaryEl || !listEl) return;
	const view = _executionEvalView || _createEmptyExecutionEvalView();
	summaryEl.className = view.items?.length
		? `nw-run-summary ${view.type || 'info'}`
		: 'nw-run-summary empty';
	summaryEl.textContent = _describeExecutionEvalSummary(view);

	listEl.innerHTML = '';
	const items = Array.isArray(view.items) ? view.items : [];
	if (!items.length) {
		const empty = document.createElement('div');
		empty.className = 'nw-run-eval-empty';
		empty.textContent = view.summary || 'No eval scores yet.';
		listEl.appendChild(empty);
		return;
	}

	for (const itemData of items) {
		const item = document.createElement('div');
		item.className = `nw-run-eval-item ${itemData.type || 'info'}`;

		const head = document.createElement('div');
		head.className = 'nw-run-eval-head';

		const title = document.createElement('div');
		title.className = 'nw-run-eval-title';
		title.textContent = `[${itemData.nodeId}] ${itemData.label}`;
		head.appendChild(title);

		const score = document.createElement('div');
		score.className = `nw-run-eval-score ${itemData.type || 'info'}`;
		score.textContent = itemData.scoreText;
		head.appendChild(score);

		item.appendChild(head);

		if (itemData.feedback) {
			const feedback = document.createElement('div');
			feedback.className = 'nw-run-eval-feedback';
			feedback.textContent = itemData.feedback;
			item.appendChild(feedback);
		}

		listEl.appendChild(item);
	}

	listEl.scrollTop = listEl.scrollHeight;
}

function _renderExecutionFailureView() {
	const summaryEl = $('execFailureSummary');
	const listEl = $('execFailureList');
	if (!summaryEl || !listEl) return;
	const view = _executionFailureView || _createEmptyExecutionFailureView();
	summaryEl.className = view.items?.length
		? `nw-run-summary ${view.type || 'warning'}`
		: 'nw-run-summary empty';
	summaryEl.textContent = _describeExecutionFailureSummary(view);

	listEl.innerHTML = '';
	const items = Array.isArray(view.items) ? view.items : [];
	if (!items.length) {
		const empty = document.createElement('div');
		empty.className = 'nw-run-failure-empty';
		empty.textContent = view.summary || 'No failure context yet.';
		listEl.appendChild(empty);
		return;
	}

	for (const itemData of items) {
		const item = document.createElement('div');
		item.className = `nw-run-failure-item ${itemData.type || 'warning'}`;

		const title = document.createElement('div');
		title.className = 'nw-run-failure-item-title';
		title.textContent = itemData.title || 'Failure detail';
		item.appendChild(title);

		if (itemData.detail) {
			const detail = document.createElement('div');
			detail.className = 'nw-run-failure-item-detail';
			detail.textContent = itemData.detail;
			item.appendChild(detail);
		}

		listEl.appendChild(item);
	}

	listEl.scrollTop = listEl.scrollHeight;
}

function _renderExecutionComparisonView() {
	const summaryEl = $('execComparisonSummary');
	const listEl = $('execComparisonList');
	if (!summaryEl || !listEl) return;
	const view = _executionComparisonView || _createEmptyExecutionComparisonView();
	summaryEl.className = view.latestExecutionId
		? `nw-run-summary ${view.type || 'info'}`
		: 'nw-run-summary empty';
	summaryEl.textContent = view.summary || 'Compare the latest two runs in this space to see what changed.';

	listEl.innerHTML = '';
	const items = Array.isArray(view.items) ? view.items : [];
	if (!items.length) {
		const empty = document.createElement('div');
		empty.className = 'nw-run-comparison-empty';
		empty.textContent = view.latestExecutionId
			? 'No major differences were found.'
			: 'No run comparison yet.';
		listEl.appendChild(empty);
		return;
	}

	for (const entry of items) {
		const item = document.createElement('div');
		item.className = `nw-run-comparison-item ${entry.type || 'info'}`;

		const title = document.createElement('div');
		title.className = 'nw-run-comparison-item-title';
		title.textContent = entry.title || 'Difference';
		item.appendChild(title);

		if (entry.detail) {
			const detail = document.createElement('div');
			detail.className = 'nw-run-comparison-item-detail';
			detail.textContent = entry.detail;
			item.appendChild(detail);
		}

		listEl.appendChild(item);
	}

	listEl.scrollTop = listEl.scrollHeight;
}

function _resetExecutionReplayView(message = 'Run the current workflow to build a live timeline, or replay the latest run in this space.') {
	_executionReplayView = _createEmptyExecutionReplayView(message);
	_renderExecutionReplayView();
}

function _resetExecutionEvalView(message = 'Any eval scores from the current or replayed run will appear here.') {
	_executionEvalView = _createEmptyExecutionEvalView(message);
	_renderExecutionEvalView();
}

function _resetExecutionFailureView(message = 'If a run fails, Numel will summarize the failing step and the most useful nearby context here.') {
	_executionFailureView = _createEmptyExecutionFailureView(message);
	_renderExecutionFailureView();
}

function _resetExecutionComparisonView(message = 'Compare the latest two runs in this space to see what changed.') {
	_executionComparisonView = _createEmptyExecutionComparisonView(message);
	_renderExecutionComparisonView();
}

function _replaceExecutionReplayView(view) {
	_executionReplayView = _cloneExecutionReplayView(view || _createEmptyExecutionReplayView());
	_executionReplayView.summary = _describeExecutionReplaySummary(_executionReplayView);
	_renderExecutionReplayView();
	_syncExecutionEvalFromReplayView(_executionReplayView);
	_syncExecutionFailureFromReplayView(_executionReplayView);
}

function _replaceExecutionEvalView(view) {
	_executionEvalView = _cloneExecutionEvalView(view || _createEmptyExecutionEvalView());
	_renderExecutionEvalView();
}

function _replaceExecutionFailureView(view) {
	_executionFailureView = _cloneExecutionFailureView(view || _createEmptyExecutionFailureView());
	_renderExecutionFailureView();
}

function _replaceExecutionComparisonView(view) {
	_executionComparisonView = _cloneExecutionComparisonView(view || _createEmptyExecutionComparisonView());
	_renderExecutionComparisonView();
}

function _syncExecutionEvalFromReplayView(view) {
	const items = _extractExecutionEvalItems(view?.nodeOutputs || {});
	if (!items.length) {
		_resetExecutionEvalView(view?.executionId
			? 'This run did not produce any eval scores.'
			: 'Any eval scores from the current or replayed run will appear here.');
		return;
	}
	const average = items
		.map((item) => item.score)
		.filter((score) => typeof score === 'number')
		.reduce((total, score) => total + score, 0) / Math.max(1, items.filter((item) => typeof item.score === 'number').length);
	const type = _executionEvalTypeForScore(Number.isFinite(average) ? average : null);
	_replaceExecutionEvalView({
		type,
		items,
		source: view?.source || 'live',
		summary: '',
	});
}

function _syncExecutionFailureFromReplayView(view) {
	const status = String(view?.status || '').toLowerCase();
	const isFailure = status === 'failed';
	const isCancelled = status === 'cancelled';
	if (!isFailure && !isCancelled) {
		_resetExecutionFailureView(view?.executionId
			? 'This run did not fail, so there is no failure drill-down to show.'
			: 'If a run fails, Numel will summarize the failing step and the most useful nearby context here.');
		return;
	}

	const items = [];
	const metadata = view?.metadata || {};
	const errorEvents = (view?.events || []).filter((entry) => entry.type === 'error');
	const latestErrorEvent = errorEvents[errorEvents.length - 1] || null;
	const failureType = isCancelled ? 'warning' : 'error';
	const topLevelError = String(view?.error || '').trim();
	if (topLevelError) {
		items.push({
			type: failureType,
			title: isCancelled ? 'Run stopped' : 'Run error',
			detail: topLevelError,
		});
	}

	const failedNodes = Array.isArray(metadata?.failed_nodes)
		? metadata.failed_nodes.map((value) => String(value))
		: [];
	const lastFailedNode = metadata?.last_failed_node !== undefined && metadata?.last_failed_node !== null
		? String(metadata.last_failed_node)
		: (failedNodes.length ? failedNodes[failedNodes.length - 1] : '');
	if (lastFailedNode) {
		items.push({
			type: failureType,
			title: 'Failed node',
			detail: `[${lastFailedNode}] ${_executionNodeLabel(lastFailedNode)}`,
		});
	} else if (failedNodes.length) {
		items.push({
			type: failureType,
			title: 'Failed nodes',
			detail: failedNodes.map((nodeId) => `[${nodeId}] ${_executionNodeLabel(nodeId)}`).join(', '),
		});
	}

	if (latestErrorEvent) {
		items.push({
			type: 'error',
			title: 'Latest failing step',
			detail: latestErrorEvent.detail || latestErrorEvent.title,
		});
		const failureIndex = (view?.events || []).lastIndexOf(latestErrorEvent);
		const contextItems = (view?.events || [])
			.slice(Math.max(0, failureIndex - 3), failureIndex)
			.filter((entry) => entry && entry.title)
			.map((entry) => `${entry.title}${entry.detail ? ` — ${entry.detail}` : ''}`);
		if (contextItems.length) {
			items.push({
				type: 'info',
				title: 'Leading context',
				detail: contextItems.join(' | '),
			});
		}
	}

	const runtimeStatus = metadata?.runtime_status;
	if (runtimeStatus && typeof runtimeStatus === 'object') {
		const runtimeParts = [];
		if (runtimeStatus.state) runtimeParts.push(`state=${runtimeStatus.state}`);
		if (runtimeStatus.error) runtimeParts.push(`error=${runtimeStatus.error}`);
		if (runtimeStatus.reason) runtimeParts.push(`reason=${runtimeStatus.reason}`);
		if (runtimeParts.length) {
			items.push({
				type: failureType,
				title: 'Runtime status',
				detail: runtimeParts.join(' · '),
			});
		}
	}

	if (!items.length && isCancelled) {
		items.push({
			type: 'warning',
			title: 'Run stopped',
			detail: 'The run was cancelled before completion.',
		});
	}

	if (!items.length) {
		items.push({
			type: 'error',
			title: 'Failure summary',
			detail: 'The run failed, but only the top-level error was retained.',
		});
	}

	_replaceExecutionFailureView({
		type: failureType,
		items,
		source: view?.source || 'live',
		summary: '',
	});
}

function _appendExecutionReplayEvent(type, title, detail = '', opts = {}) {
	if (!_executionReplayView?.executionId) return;
	_executionReplayView.events.push({
		type: type || 'info',
		title: title || 'Execution event',
		detail: detail || '',
		time: opts.time || new Date().toISOString(),
		nodeId: opts.nodeId || '',
	});
	while (_executionReplayView.events.length > 120) {
		_executionReplayView.events.shift();
	}
	_executionReplayView.summary = _describeExecutionReplaySummary(_executionReplayView);
	_renderExecutionReplayView();
	if (type === 'error' || type === 'warning') {
		_syncExecutionFailureFromReplayView(_executionReplayView);
	}
}

function _beginExecutionReplay(executionId, platformExecutionId, workflowName) {
	_executionReplayView = {
		executionId: executionId || null,
		platformExecutionId: platformExecutionId || executionId || null,
		workflowName: _sanitizeExecutionWorkflowLabel(workflowName || visualizer?.currentWorkflowName || '') || 'Current workflow',
		metadata: {},
		status: 'starting',
		startedAt: null,
		endedAt: null,
		error: '',
		nodeOutputs: {},
		events: [],
		source: 'live',
		summary: '',
	};
	_executionReplayView.summary = _describeExecutionReplaySummary(_executionReplayView);
	_renderExecutionReplayView();
}

function _cacheCurrentExecutionReplay(executionId = _executionReplayView?.executionId) {
	if (!executionId || !_executionReplayView?.executionId) return;
	const snapshot = _cloneExecutionReplayView(_executionReplayView);
	snapshot.summary = _describeExecutionReplaySummary(snapshot);
	_executionReplayCache.set(executionId, snapshot);
	_latestReplayExecutionId = executionId;
}

function _executionPublicIdFromRecord(record) {
	return String(record?.metadata?.engine_execution_id || record?.execution_id || '').trim();
}

function _compareExecutionRecordsDesc(a, b) {
	const aTime = _coerceExecutionTimeMs(a?.started_at || a?.finished_at || '') || 0;
	const bTime = _coerceExecutionTimeMs(b?.started_at || b?.finished_at || '') || 0;
	return bTime - aTime;
}

function _buildExecutionComparisonView(latestResults, previousResults) {
	const latestId = latestResults?.execution_id || '';
	const previousId = previousResults?.execution_id || '';
	const latestStatus = _normalizeExecutionStatus(latestResults?.status || 'unknown', {
		endTime: latestResults?.end_time,
		error: latestResults?.error,
	});
	const previousStatus = _normalizeExecutionStatus(previousResults?.status || 'unknown', {
		endTime: previousResults?.end_time,
		error: previousResults?.error,
	});
	const latestOutputs = latestResults?.node_outputs || {};
	const previousOutputs = previousResults?.node_outputs || {};
	const latestEvalItems = _extractExecutionEvalItems(latestOutputs);
	const previousEvalItems = _extractExecutionEvalItems(previousOutputs);
	const latestEvalMap = new Map(latestEvalItems.map((item) => [item.nodeId, item]));
	const previousEvalMap = new Map(previousEvalItems.map((item) => [item.nodeId, item]));
	const latestNodeIds = new Set(Object.keys(latestOutputs));
	const previousNodeIds = new Set(Object.keys(previousOutputs));
	const addedNodes = [...latestNodeIds].filter((nodeId) => !previousNodeIds.has(nodeId));
	const removedNodes = [...previousNodeIds].filter((nodeId) => !latestNodeIds.has(nodeId));
	const changedNodes = [];
	const unchangedNodes = [];

	for (const nodeId of [...latestNodeIds].filter((id) => previousNodeIds.has(id)).sort((a, b) => Number(a) - Number(b))) {
		const latestValue = _stringifyExecutionValue(latestOutputs[nodeId]);
		const previousValue = _stringifyExecutionValue(previousOutputs[nodeId]);
		if (latestValue === previousValue) {
			unchangedNodes.push(nodeId);
		} else {
			changedNodes.push(nodeId);
		}
	}

	const changeCount = addedNodes.length + removedNodes.length + changedNodes.length;
	const statusChanged = latestStatus !== previousStatus;
	const summaryParts = [
		`Latest ${latestId ? latestId.substring(0, 8) : 'run'} vs previous ${previousId ? previousId.substring(0, 8) : 'run'}`,
		statusChanged
			? `${_formatExecutionStatusLabel(previousStatus)} -> ${_formatExecutionStatusLabel(latestStatus)}`
			: _formatExecutionStatusLabel(latestStatus),
		changeCount
			? `${changeCount} output change${changeCount === 1 ? '' : 's'}`
			: 'No output differences',
	];
	const items = [];
	let evalChangeCount = 0;
	let evalScoreChangeCount = 0;

	if (statusChanged) {
		items.push({
			type: latestStatus === 'failed' ? 'error' : 'warning',
			title: 'Run status changed',
			detail: `${_formatExecutionStatusLabel(previousStatus)} -> ${_formatExecutionStatusLabel(latestStatus)}`,
		});
	} else {
		items.push({
			type: 'info',
			title: 'Run status stayed the same',
			detail: _formatExecutionStatusLabel(latestStatus),
		});
	}

	const durationDelta = _formatExecutionComparisonDurationDelta(latestResults, previousResults);
	if (durationDelta) {
		items.push({
			type: 'info',
			title: 'Duration',
			detail: durationDelta,
		});
	}

	if ((latestResults?.workflow_id || '') !== (previousResults?.workflow_id || '')) {
		items.push({
			type: 'warning',
			title: 'Workflow asset changed',
			detail: `${previousResults?.workflow_id || 'unknown'} -> ${latestResults?.workflow_id || 'unknown'}`,
		});
	}

	if (latestEvalItems.length || previousEvalItems.length) {
		const latestAvg = latestEvalItems.length
			? latestEvalItems.reduce((total, item) => total + (item.score || 0), 0) / latestEvalItems.length
			: null;
		const previousAvg = previousEvalItems.length
			? previousEvalItems.reduce((total, item) => total + (item.score || 0), 0) / previousEvalItems.length
			: null;
		if (latestAvg !== null || previousAvg !== null) {
			const latestText = latestAvg === null ? 'n/a' : latestAvg.toFixed(3);
			const previousText = previousAvg === null ? 'n/a' : previousAvg.toFixed(3);
			items.push({
				type: 'info',
				title: 'Eval average',
				detail: `${previousText} -> ${latestText}`,
			});
		}
		for (const [nodeId, latestEval] of latestEvalMap.entries()) {
			const previousEval = previousEvalMap.get(nodeId);
			if (!previousEval) {
				evalChangeCount += 1;
				evalScoreChangeCount += 1;
				items.push({
					type: latestEval.type,
					title: `Eval added for [${nodeId}] ${latestEval.label}`,
					detail: `Score ${latestEval.scoreText}${latestEval.feedback ? ` · ${latestEval.feedback}` : ''}`,
				});
				continue;
			}
			const latestScoreText = latestEval.scoreText;
			const previousScoreText = previousEval.scoreText;
			const scoreChanged = latestScoreText !== previousScoreText;
			const feedbackChanged = latestEval.feedback !== previousEval.feedback;
			if (scoreChanged || feedbackChanged) {
				evalChangeCount += 1;
				if (scoreChanged) evalScoreChangeCount += 1;
				items.push({
					type: latestEval.type,
					title: `${scoreChanged ? 'Eval score changed' : 'Eval feedback changed'} for [${nodeId}] ${latestEval.label}`,
					detail: scoreChanged
						? `Score ${previousScoreText} -> ${latestScoreText}${latestEval.feedback || previousEval.feedback ? ` · ${previousEval.feedback || 'no feedback'} -> ${latestEval.feedback || 'no feedback'}` : ''}`
						: `${previousEval.feedback || 'no feedback'} -> ${latestEval.feedback || 'no feedback'}`,
				});
			}
		}
		for (const [nodeId, previousEval] of previousEvalMap.entries()) {
			if (!latestEvalMap.has(nodeId)) {
				evalChangeCount += 1;
				evalScoreChangeCount += 1;
				items.push({
					type: 'warning',
					title: `Eval removed for [${nodeId}] ${previousEval.label}`,
					detail: `Previous score ${previousEval.scoreText}${previousEval.feedback ? ` · ${previousEval.feedback}` : ''}`,
				});
			}
		}
		if (evalScoreChangeCount) {
			summaryParts.push(`${evalScoreChangeCount} eval score change${evalScoreChangeCount === 1 ? '' : 's'}`);
		} else if (evalChangeCount) {
			summaryParts.push('eval scores stable');
		} else {
			summaryParts.push('eval stable');
		}
	}

	if (addedNodes.length) {
		const detail = addedNodes
			.slice(0, 6)
			.map((nodeId) => `[${nodeId}] ${_executionNodeLabel(nodeId)}`)
			.join(', ');
		items.push({
			type: 'success',
			title: `${addedNodes.length} node output${addedNodes.length === 1 ? '' : 's'} added`,
			detail: detail + (addedNodes.length > 6 ? `, +${addedNodes.length - 6} more` : ''),
		});
	}

	if (removedNodes.length) {
		const detail = removedNodes
			.slice(0, 6)
			.map((nodeId) => `[${nodeId}] ${_executionNodeLabel(nodeId)}`)
			.join(', ');
		items.push({
			type: 'warning',
			title: `${removedNodes.length} node output${removedNodes.length === 1 ? '' : 's'} removed`,
			detail: detail + (removedNodes.length > 6 ? `, +${removedNodes.length - 6} more` : ''),
		});
	}

	for (const nodeId of changedNodes.slice(0, 6)) {
		items.push({
			type: 'info',
			title: `Output changed for [${nodeId}] ${_executionNodeLabel(nodeId)}`,
			detail: `Previous: ${_previewExecutionValue(previousOutputs[nodeId], 100)} | Latest: ${_previewExecutionValue(latestOutputs[nodeId], 100)}`,
		});
	}

	if (changedNodes.length > 6) {
		items.push({
			type: 'info',
			title: `${changedNodes.length - 6} more changed node output${changedNodes.length - 6 === 1 ? '' : 's'}`,
			detail: 'Open the timeline and replay again if you want to inspect the latest run in more detail.',
		});
	}

	if (!changeCount && unchangedNodes.length) {
		items.push({
			type: 'success',
			title: 'Outputs stayed stable',
			detail: `${unchangedNodes.length} node output${unchangedNodes.length === 1 ? '' : 's'} matched exactly between the latest two runs.`,
		});
	}

	return {
		latestExecutionId: latestId,
		previousExecutionId: previousId,
		type: changeCount ? (statusChanged && latestStatus === 'failed' ? 'error' : 'info') : 'success',
		summary: summaryParts.join(' · '),
		items,
	};
}

function _buildExecutionReplayFromResults(results, baseView = null) {
	const view = baseView ? _cloneExecutionReplayView(baseView) : _createEmptyExecutionReplayView();
	view.executionId = results?.execution_id || view.executionId;
	view.platformExecutionId = results?.platform_execution_id || view.platformExecutionId || view.executionId;
	view.workflowId = results?.workflow_id || view.workflowId || '';
	view.metadata = { ...(results?.metadata || view.metadata || {}) };
	const baseStatus = String(view.status || '').toLowerCase();
	const resultsStatus = _normalizeExecutionStatus(results?.status || view.status || 'idle', {
		endTime: results?.end_time,
		error: results?.error,
	});
	view.status = _isExecutionTerminalStatus(baseStatus) && !_isExecutionTerminalStatus(resultsStatus)
		? baseStatus
		: resultsStatus;
	view.workflowName = _executionWorkflowLabel(results, view.workflowName || '') || view.workflowName || 'Workflow';
	view.startedAt = results?.start_time || view.startedAt || null;
	view.endedAt = results?.end_time || view.endedAt || null;
	view.error = results?.error || view.error || '';
	view.nodeOutputs = { ...(results?.node_outputs || view.nodeOutputs || {}) };
	view.source = baseView?.source || 'replay';

	if (!view.events.length) {
		const synthetic = [];
		if (view.startedAt) {
			synthetic.push({
				type: 'info',
				time: view.startedAt,
				title: 'Workflow started',
				detail: results?.workflow_id ? String(results.workflow_id) : '',
			});
		}
		const outputSummary = _summarizeExecutionOutputs(view.nodeOutputs);
		if (outputSummary.count) {
			synthetic.push({
				type: 'info',
				time: view.endedAt || view.startedAt || new Date().toISOString(),
				title: 'Outputs captured',
				detail: outputSummary.text,
			});
		}
		const finalTitles = {
			completed: 'Workflow completed',
			failed: 'Workflow failed',
			cancelled: 'Workflow cancelled',
		};
		synthetic.push({
			type: _executionReplayTypeForStatus(view.status),
			time: view.endedAt || view.startedAt || new Date().toISOString(),
			title: finalTitles[view.status] || 'Workflow finished',
			detail: view.error || outputSummary.text,
		});
		view.events = synthetic;
	}

	view.summary = _describeExecutionReplaySummary(view);
	return view;
}

async function _getExecutionResultsCached(executionId, { source = 'replay' } = {}) {
	const existingView = _executionReplayCache.get(executionId);
	const results = _mergeExecutionResultsWithReplayView(await api.getExecutionResults(executionId), existingView);
	const replayView = _buildExecutionReplayFromResults(results, existingView ? { ...existingView, source } : { source });
	replayView.workflowId = results?.workflow_id || '';
	_executionReplayCache.set(executionId, _cloneExecutionReplayView(replayView));
	return results;
}

async function _hydrateExecutionReplay(executionId, { useCurrentView = false } = {}) {
	if (!api || !executionId) return null;
	const cached = _executionReplayCache.get(executionId);
	const results = _mergeExecutionResultsWithReplayView(await api.getExecutionResults(executionId), cached);
	const baseView = useCurrentView && _executionReplayView?.executionId === executionId
		? _executionReplayView
		: cached;
	const view = _buildExecutionReplayFromResults(results, baseView);
	_executionReplayCache.set(executionId, _cloneExecutionReplayView(view));
	_latestReplayExecutionId = executionId;
	if (_executionReplayView?.executionId === executionId || view.source === 'replay') {
		_replaceExecutionReplayView(view);
	}
	return view;
}

async function replayLatestExecution() {
	if (!api) return;
	const button = $('replayLatestRunBtn');
	const previousLabel = button?.textContent || 'Replay Latest Run';
	if (button) {
		button.disabled = true;
		button.textContent = 'Loading...';
	}
	try {
		let executionId = _latestReplayExecutionId;
		if (!executionId) {
			const response = await api.listExecutions();
			const records = [...(response?.executions || [])].sort(_compareExecutionRecordsDesc);
			const latest = records[0];
			executionId = _executionPublicIdFromRecord(latest);
		}

		if (!executionId) {
			_resetExecutionReplayView('No runs in this space yet. Run the current workflow first.');
			addLog('info', '🕘 No runs available yet in the current space');
			return;
		}

		const cached = _executionReplayCache.get(executionId);
		if (cached) {
			const replayView = _cloneExecutionReplayView(cached);
			replayView.source = 'replay';
			replayView.summary = _describeExecutionReplaySummary(replayView);
			_replaceExecutionReplayView(replayView);
		} else {
			await _hydrateExecutionReplay(executionId);
		}
		addLog('info', `🕘 Replayed latest run ${executionId.substring(0, 8)}...`);
	} catch (error) {
		_resetExecutionReplayView(`Could not replay the latest run: ${error.message}`);
		addLog('error', `❌ Could not replay latest run: ${error.message}`);
	} finally {
		if (button) {
			button.textContent = previousLabel;
		}
		_syncReplayButtonState();
	}
}

async function compareLatestExecutions() {
	if (!api) return;
	const button = $('compareLatestRunsBtn');
	const previousLabel = button?.textContent || 'Compare Latest Two Runs';
	if (button) {
		button.disabled = true;
		button.textContent = 'Comparing...';
	}
	try {
		const response = await api.listExecutions();
		const records = [...(response?.executions || [])].sort(_compareExecutionRecordsDesc);
		if (records.length < 2) {
			_resetExecutionComparisonView('You need at least two runs in this space before Numel can compare them.');
			addLog('info', '🧪 Need at least two runs before comparison is available');
			return;
		}

		const latestId = _executionPublicIdFromRecord(records[0]);
		const previousId = _executionPublicIdFromRecord(records[1]);
		const [latestResults, previousResults] = await Promise.all([
			_getExecutionResultsCached(latestId, { source: 'replay' }),
			_getExecutionResultsCached(previousId, { source: 'replay' }),
		]);

		const latestReplay = _buildExecutionReplayFromResults(latestResults, _executionReplayCache.get(latestId) || { source: 'replay' });
		latestReplay.workflowId = latestResults?.workflow_id || '';
		_executionReplayCache.set(latestId, _cloneExecutionReplayView(latestReplay));
		_latestReplayExecutionId = latestId;

		const previousReplay = _buildExecutionReplayFromResults(previousResults, _executionReplayCache.get(previousId) || { source: 'replay' });
		previousReplay.workflowId = previousResults?.workflow_id || '';
		_executionReplayCache.set(previousId, _cloneExecutionReplayView(previousReplay));

		_replaceExecutionComparisonView(_buildExecutionComparisonView(latestResults, previousResults));
		addLog('info', `🧪 Compared latest two runs ${latestId.substring(0, 8)}... and ${previousId.substring(0, 8)}...`);
	} catch (error) {
		_resetExecutionComparisonView(`Could not compare the latest runs: ${error.message}`);
		addLog('error', `❌ Could not compare latest runs: ${error.message}`);
	} finally {
		if (button) {
			button.textContent = previousLabel;
		}
		_syncReplayButtonState();
	}
}

function setWsStatus(status) {
	const badge = $('wsStatus');
	badge.className = `nw-ws-badge ${status}`;
}

function setExecStatus(type, text) {
	const status = $('execStatus');
	status.className = `nw-status ${type}`;
	status.textContent = text;
	const pill = $('execStatusPill');
	if (pill) {
		pill.className = `nw-exec-status-pill ${type}`;
		pill.setAttribute('title', text);
	}
}

function _setExecutionAlert(type, message) {
	const alert = $('execAlert');
	if (!alert) return;
	const text = String(message || '').trim();
	if (!text) {
		alert.hidden = true;
		alert.textContent = '';
		alert.className = 'nw-inline-alert';
		return;
	}
	alert.hidden = false;
	alert.textContent = text;
	alert.className = `nw-inline-alert ${type || 'error'}`;
}

function _clearExecutionIssue() {
	_setExecutionAlert('', '');
}

function _revealExecutionIssue(type, message) {
	_setExecutionAlert(type, message);
	_setPanelCollapsed(false);
	_setSectionCollapsed($('executionSection'), false);
	_setSectionCollapsed($('eventLogSection'), false);
	_saveSectionCollapseState();
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
					labelSpan.textContent = n.displayTitle || n.modelName || n.title || `step ${n.id}`;

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
		// One-shot check: tunnel state is fixed at server start (set via --tunnel flag).
		// If no URL is configured we bail immediately rather than polling forever.
		try {
			const r = await fetch(`${this._base}/tunnel/url`, { method: 'POST' });
			const d = await r.json();
			if (d && d.url) {
				urlEl.textContent = d.url;
				urlEl.href        = d.url;
				info.style.display = 'flex';
			}
		} catch (_) {}
	}
}

// ============================================================================
// END: Frontend editor enhancements
// ============================================================================
