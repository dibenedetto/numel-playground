// ========================================================================
// SCHEMAGRAPH APP
// Main application class for SchemaGraph
// Depends on: schemagraph-core.js, schemagraph-graph.js, schemagraph-workflow.js,
//             schemagraph-extensions.js, schemagraph-controllers.js, schemagraph-drawing.js
// ========================================================================

console.log('[SchemaGraph] Loading app module...');

// ========================================================================
// SCHEMA GRAPH APP CLASS
// ========================================================================

class SchemaGraphApp {
	constructor(canvasId) {
		this.eventBus = new EventBus();
		this.analytics = new AnalyticsService(this.eventBus);
		this.canvas = document.getElementById(canvasId);
		this.ctx = this.canvas.getContext('2d');

		this.mouseController = new MouseTouchController(this.canvas, this.eventBus);
		this.keyboardController = new KeyboardController(this.eventBus);
		this.voiceController = new VoiceController(this.eventBus);

		this.initializeState();
		this.injectDialogHTML();
		this.injectCanvasElementsHTML();
		this.injectToolbarHTML();
		this.injectAnalyticsPanelHTML();
		this.injectFeaturesPanelHTML();
		this.injectTemplatePanelHTML();
		this.injectGenerateWorkflowHTML();
		this.injectMultiSlotUIStyles();
		this.injectInteractiveStyles();
		this.injectPreviewOverlayStyles();

		this.api = this._createAPI();
		this.ui = this._createUI();

		this.setupEventListeners();
		this.setupCanvasLeaveHandler();
		this.setupVoiceCommands();
		this.registerNativeNodes();

		this.ui.init();
		this.ui.util.resizeCanvas();
		this.draw();

		this.eventBus.emit('app:ready', {});
	}

	initializeState() {
		const self = this;

		this.graph = new SchemaGraph(self, this.eventBus);
		this.extensions = extensionRegistry;
		this._drawUtils = DrawUtils;
		this.camera = { x: 0, y: 0, scale: 1.0 };
		this.selectedNodes = new Set();
		this.selectedNode = null;
		this.selectionRect = null;
		this.selectionStart = null;
		this.isMouseDown = false;
		this.previewSelection = new Set();
		this.dragNode = null;
		this.dragOffset = [0, 0];
		this.connecting = null;
		this.mousePos = [0, 0];
		this.isPanning = false;
		this.panStart = [0, 0];
		this.spacePressed = false;
		this.editingNode = null;
		this.pendingSchemaCode = null;
		this.customContextMenuHandler = null;
		this.hoveredSlot = null;
		this.tooltipEl = null;

		this._hoveredAddButton = null;
		this._hoveredRemoveButton = null;
		this._editingMultiSlotNode = null;
		this._editingMultiSlotField = null;

		this.isLocked = false;
		this.lockReason = null;
		this.lockPending = false;

		this._hiddenFieldNames = [];

		this._hoveredButton = null;
		this._activeDropNode = null;
		this._callbackRegistry = {};
		this._decoratorParser = new NodeDecoratorParser();
		this._schemaDecorators = {};

		// Section-based header colors for nodes (configured via api.schemaTypes.setSectionColors)
		this._sectionColors = {};

		this._nodeTooltipsEnabled = true;
		this._fieldTooltipsEnabled = true;
		this._nodeHeaderTooltipEl = null;

		// Schema type roles configuration - defines which node types serve which purposes
		this._schemaTypeRoles = {
			dataTensor: [],    // Node types that hold data (e.g., ['schema.DataTensor', 'schema.TensorType'])
			sourceMeta: [],    // Node types that hold metadata (e.g., ['schema.SourceMeta'])
			preview: [],       // Node types that display previews (e.g., ['schema.PreviewFlow'])
			startNode: [],     // Node types that represent workflow start (e.g., ['schema.StartFlow'])
			endNode: [],       // Node types that represent workflow end (e.g., ['schema.EndFlow'])
			agentChat: [],     // Node types that display agent chat (e.g., ['schema.AgentChat'])
			toolCall: [],      // Node types that make interactive tool calls (e.g., ['schema.ToolCall'])
			metaInputSlot: 'meta',  // Default slot name for meta connection on data nodes
			workflowOptions: null,          // Model name for workflow options (e.g., 'WorkflowOptions')
			workflowExecutionOptions: null, // Model name for workflow execution options (e.g., 'WorkflowExecutionOptions')
			previewSlotMap: {}              // Maps preview input slot names to output slot names (e.g., { 'input': 'get' })
		};

		// Set types: paired nodes that must be created/removed together with a loop-back edge
		// Each entry maps a start workflowType to its end workflowType (and vice versa)
		// Format: { startType: endType, ... } — both directions are auto-derived
		this._setTypes = {};
		this._creatingPairedNode = false;
		this._removingPairedNode = false;

		// Canvas drop configuration (node types come from _schemaTypeRoles)
		this._canvasDropConfig = {
			enabled: true,
			accept: '*'  // MIME filter: '*', 'image/*', 'audio/*,video/*', or function
		};
		this._canvasDropCreationCallback = null;
		this._canvasDropHighlight = false;

		// Edge preview configuration
		this._edgePreviewConfig = {
			enabled: true,
			linkHitDistance: 10  // Pixels for detecting link hover
		};
		this._hoveredLink = null;

		// Feature flags for enabling/disabling UI components
		this._features = {
			// Toolbar sections
			toolbar: true,
			toolbarVoice: true,
			toolbarAnalytics: true,
			toolbarSchema: true,
			toolbarWorkflow: true,
			toolbarTemplates: true,
			toolbarView: true,
			toolbarLayout: true,
			toolbarZoom: true,
			toolbarStyle: true,
			// Interactions
			nodeSelection: true,
			multiSelection: true,
			nodeDragging: true,
			linkCreation: true,
			linkDeletion: true,
			panning: true,
			zooming: true,
			contextMenu: true,
			// Tooltips
			nodeTooltips: true,
			fieldTooltips: true,
			// Visual features
			completenessIndicators: true,
			analytics: true,
			textScaling: true,
			themeSwitch: true,
			autoPreview: true,
			edgePreview: true,
			sectionColors: true,
			preservePreviewLinks: true,
			previewFlash: true,  // Flash animation when preview data updates
			lockOverlay: true,  // Show lock status overlay when graph is locked
			hiddenFields: true,  // Hide fields listed in _hiddenFieldNames from nodes
			prettyFieldNames: true,  // Convert snake_case/camelCase field names to Title Case
			loopEdgeOrthogonal: true,  // Use orthogonal routing for loop-back edges
			// Node types
			nativeTypes: true
		};
		this.loadFeatures();

		this.themes = ['dark', 'light', 'ocean'];
		this.currentThemeIndex = 0;
		this.loadTheme();

		this.drawingStyleManager = new DrawingStyleManager();
		this.drawingStyleManager.loadSavedStyle();

		this.textScalingMode = 'fixed';
		this.loadTextScalingMode();
	}

	// === LOCK METHODS ===
	lock(reason = 'Graph locked', pending = true) {
		this.lockReason = reason;
		this.lockPending = pending;
		if (!this.isLocked) {
			this.isLocked = true;
			this.connecting = null;
			this.selectionRect = null;
			this.selectionStart = null;
			this.editingNode = null;
			document.getElementById('sg-contextMenu')?.classList.remove('show');
			document.getElementById('sg-schemaDialog')?.classList.remove('show');
			this.canvas.classList.add('sg-locked');
		}
		const overlay = document.getElementById('sg-lockOverlay');
		if (overlay && this._features.lockOverlay) {
			document.getElementById('sg-lockText').textContent = reason || 'Locked';
			overlay.classList.toggle('pending', pending);
			overlay.classList.add('show');
		}
		this.eventBus.emit('graph:locked', { reason });
		this.draw();
	}

	unlock() {
		if (!this.isLocked) return;
		this.isLocked = false;
		this.lockReason = null;
		this.lockPending = false;
		document.getElementById('sg-lockOverlay')?.classList.remove('show', 'pending');
		this.canvas.classList.remove('sg-locked');
		this.eventBus.emit('graph:unlocked', {});
		this.draw();
	}

	isGraphLocked() { return this.isLocked; }

	// === HTML INJECTION ===
	injectDialogHTML() {
		if (document.getElementById('sg-messageDialog')) return;
		const messageDialog = document.createElement('div');
		messageDialog.id = 'sg-messageDialog';
		messageDialog.className = 'sg-dialog-overlay';
		messageDialog.innerHTML = `<div class="sg-dialog"><div class="sg-dialog-header" id="sg-messageDialogTitle">Message</div><div class="sg-dialog-body"><div id="sg-messageDialogContent"></div></div><div class="sg-dialog-footer"><button id="sg-messageDialogOk" class="sg-dialog-btn sg-dialog-btn-confirm">OK</button></div></div>`;
		document.body.appendChild(messageDialog);

		const confirmDialog = document.createElement('div');
		confirmDialog.id = 'sg-confirmDialog';
		confirmDialog.className = 'sg-dialog-overlay';
		confirmDialog.innerHTML = `<div class="sg-dialog"><div class="sg-dialog-header" id="sg-confirmDialogTitle">Confirm</div><div class="sg-dialog-body"><div id="sg-confirmDialogContent"></div></div><div class="sg-dialog-footer"><button id="sg-confirmDialogCancel" class="sg-dialog-btn sg-dialog-btn-cancel">Cancel</button><button id="sg-confirmDialogOk" class="sg-dialog-btn sg-dialog-btn-confirm">OK</button></div></div>`;
		document.body.appendChild(confirmDialog);
	}

	injectCanvasElementsHTML() {
		const canvasContainer = this.canvas.parentElement;
		if (!canvasContainer) return;

		if (!document.getElementById('sg-contextMenu')) {
			const contextMenu = document.createElement('div');
			contextMenu.id = 'sg-contextMenu';
			contextMenu.className = 'sg-context-menu';
			canvasContainer.appendChild(contextMenu);
		}

		if (!document.getElementById('sg-nodeInput')) {
			const nodeInput = document.createElement('input');
			nodeInput.type = 'text';
			nodeInput.id = 'sg-nodeInput';
			nodeInput.className = 'sg-node-input-overlay';
			canvasContainer.appendChild(nodeInput);
		}

		if (!document.getElementById('sg-nodeSelectWrapper')) {
			const nodeSelectWrapper = document.createElement('div');
			nodeSelectWrapper.id = 'sg-nodeSelectWrapper';
			nodeSelectWrapper.className = 'sg-node-select-overlay-wrapper';

			const nodeSelect = document.createElement('select');
			nodeSelect.id = 'sg-nodeSelect';
			nodeSelect.className = 'sg-node-input-overlay sg-node-select-overlay';

			nodeSelectWrapper.appendChild(nodeSelect);
			canvasContainer.appendChild(nodeSelectWrapper);
		}

		if (!document.getElementById('sg-comboBoxWrapper')) {
			const wrapper = document.createElement('div');
			wrapper.id = 'sg-comboBoxWrapper';
			wrapper.className = 'sg-combo-box-wrapper';

			const input = document.createElement('input');
			input.type = 'text';
			input.id = 'sg-comboBoxInput';
			input.className = 'sg-node-input-overlay sg-combo-box-input';
			input.autocomplete = 'off';

			const refreshBtn = document.createElement('button');
			refreshBtn.id = 'sg-comboBoxRefresh';
			refreshBtn.className = 'sg-combo-box-refresh';
			refreshBtn.title = 'Refresh options';
			refreshBtn.textContent = '\u21BB';

			const spinner = document.createElement('div');
			spinner.id = 'sg-comboBoxSpinner';
			spinner.className = 'sg-combo-box-spinner';

			const dropdown = document.createElement('div');
			dropdown.id = 'sg-comboBoxDropdown';
			dropdown.className = 'sg-combo-box-dropdown';

			wrapper.appendChild(input);
			wrapper.appendChild(refreshBtn);
			wrapper.appendChild(spinner);
			wrapper.appendChild(dropdown);
			canvasContainer.appendChild(wrapper);
		}

		if (!document.getElementById('sg-codeEditorModal')) {
			const modal = document.createElement('div');
			modal.id = 'sg-codeEditorModal';
			modal.className = 'sg-code-editor-modal';
			modal.innerHTML = `
				<div class="sg-code-editor-container">
					<div class="sg-code-editor-header">
						<span class="sg-code-editor-title">Edit Script</span>
						<div class="sg-code-editor-lang">
							<select id="sg-codeEditorLang">
								<option value="python">Python</option>
								<option value="jinja2">Jinja2</option>
							</select>
						</div>
						<div class="sg-code-editor-actions">
							<button id="sg-codeEditorSave" class="sg-code-editor-btn save">Save</button>
							<button id="sg-codeEditorCancel" class="sg-code-editor-btn cancel">Cancel</button>
						</div>
					</div>
					<div id="sg-codeEditorBody"></div>
					<div class="sg-code-editor-footer">
						<span id="sg-codeEditorStatus"></span>
					</div>
				</div>`;
			document.body.appendChild(modal);
		}

		if (!document.getElementById('sg-lockOverlay')) {
			const lockOverlay = document.createElement('div');
			lockOverlay.id = 'sg-lockOverlay';
			lockOverlay.className = 'sg-lock-overlay';
			lockOverlay.innerHTML = '<span class="sg-lock-spinner"></span><span id="sg-lockText"></span>';
			canvasContainer.appendChild(lockOverlay);
		}

		if (!document.getElementById('sg-schemaDialog')) {
			const schemaDialog = document.createElement('div');
			schemaDialog.id = 'sg-schemaDialog';
			schemaDialog.className = 'sg-dialog-overlay';
			schemaDialog.innerHTML = `<div class="sg-dialog"><div class="sg-dialog-header">Register Schema</div><div class="sg-dialog-body"><div class="sg-dialog-field"><label>Schema Name:</label><input type="text" id="sg-schemaNameInput" /></div><div class="sg-dialog-field"><label>Index Type:</label><input type="text" id="sg-schemaIndexTypeInput" placeholder="int" /></div><div class="sg-dialog-field"><label>Root Type:</label><input type="text" id="sg-schemaRootTypeInput" /></div></div><div class="sg-dialog-footer"><button id="sg-schemaDialogCancel" class="sg-dialog-btn sg-dialog-btn-cancel">Cancel</button><button id="sg-schemaDialogConfirm" class="sg-dialog-btn sg-dialog-btn-confirm">Register</button></div></div>`;
			document.body.appendChild(schemaDialog);
		}
	}

	injectToolbarHTML() {
		const canvasContainer = this.canvas.parentElement;
		if (!canvasContainer || document.getElementById('sg-toolbarToggle')) return;

		const toggleBtn = document.createElement('button');
		toggleBtn.id = 'sg-toolbarToggle';
		toggleBtn.className = 'sg-toolbar-toggle-corner';
		toggleBtn.title = 'Toggle toolbar';
		toggleBtn.innerHTML = '<span class="sg-toolbar-toggle-icon">⚙️</span>';

		const toolbarPanel = document.createElement('div');
		toolbarPanel.id = 'sg-toolbarPanel';
		toolbarPanel.className = 'sg-toolbar-panel';
		toolbarPanel.innerHTML = `
			<div class="sg-toolbar-header"><span class="sg-toolbar-title">⚙️ Toolbar</span><button id="sg-toolbarClose" class="sg-toolbar-close">✕</button></div>
			<div class="sg-toolbar-content" id="sg-toolbarContent">
				<div class="sg-toolbar-section" id="sg-toolbar-voice"><span class="sg-toolbar-label">🎤 Voice</span><button id="sg-voiceStartBtn" class="sg-toolbar-btn">Start</button><button id="sg-voiceStopBtn" class="sg-toolbar-btn" style="display:none;">Stop</button><span id="sg-voiceStatus" class="sg-toolbar-status"></span></div>
				<div class="sg-toolbar-divider" id="sg-toolbar-voice-divider"></div>
				<div class="sg-toolbar-section" id="sg-toolbar-analytics"><button id="sg-analyticsToggleBtn" class="sg-toolbar-btn">📊 Analytics</button></div>
				<div class="sg-toolbar-divider" id="sg-toolbar-analytics-divider"></div>
				<div class="sg-toolbar-section" id="sg-toolbar-schema"><span class="sg-toolbar-label">Schema</span><button id="sg-uploadSchemaBtn" class="sg-toolbar-btn sg-toolbar-btn-primary">📤 Upload</button><button id="sg-exportBtn" class="sg-toolbar-btn">Export Graph</button><button id="sg-importBtn" class="sg-toolbar-btn">Import Graph</button><button id="sg-exportConfigBtn" class="sg-toolbar-btn">Export Config</button><button id="sg-importConfigBtn" class="sg-toolbar-btn">Import Config</button></div>
				<div class="sg-toolbar-divider" id="sg-toolbar-schema-divider"></div>
				<div class="sg-toolbar-section" id="sg-toolbar-workflow"><span class="sg-toolbar-label">Workflow</span><button id="sg-exportWorkflowBtn" class="sg-toolbar-btn">Export Workflow</button><button id="sg-importWorkflowBtn" class="sg-toolbar-btn">Import Workflow</button><button id="sg-generateWorkflowBtn" class="sg-toolbar-btn sg-toolbar-btn-primary">Generate</button></div>
				<div class="sg-toolbar-divider" id="sg-toolbar-workflow-divider"></div>
				<div class="sg-toolbar-section" id="sg-toolbar-templates"><span class="sg-toolbar-label">Templates</span><button id="sg-templatesBtn" class="sg-toolbar-btn">Templates</button></div>
				<div class="sg-toolbar-divider" id="sg-toolbar-templates-divider"></div>
				<div class="sg-toolbar-section" id="sg-toolbar-view"><span class="sg-toolbar-label">View</span><button id="sg-centerViewBtn" class="sg-toolbar-btn">🎯 Center</button></div>
				<div class="sg-toolbar-divider" id="sg-toolbar-view-divider"></div>
				<div class="sg-toolbar-section" id="sg-toolbar-layout"><span class="sg-toolbar-label">Layout</span><select id="sg-layoutSelect" class="sg-toolbar-select"><option value="">🔧 Layout...</option><option value="hierarchical-vertical">Hierarchical ↓</option><option value="hierarchical-horizontal">Hierarchical →</option><option value="force-directed">Force-Directed</option><option value="grid">Grid</option><option value="circular">Circular</option></select></div>
				<div class="sg-toolbar-divider" id="sg-toolbar-layout-divider"></div>
				<div class="sg-toolbar-section" id="sg-toolbar-style"><span class="sg-toolbar-label">Style</span><select id="sg-drawingStyleSelect" class="sg-toolbar-select"><option value="default">🎨 Default</option><option value="minimal">✨ Minimal</option><option value="blueprint">📐 Blueprint</option><option value="neon">💫 Neon</option><option value="organic">🌿 Organic</option><option value="wireframe">📊 Wireframe</option></select><button id="sg-textScalingToggle" class="sg-toolbar-btn sg-toolbar-btn-toggle"><span class="sg-toolbar-toggle-label" id="sg-textScalingLabel">Text: Fixed</span></button><button id="sg-themeBtn" class="sg-toolbar-btn">🎨 Theme</button></div>
				<div class="sg-toolbar-divider" id="sg-toolbar-style-divider"></div>
				<div class="sg-toolbar-section" id="sg-toolbar-features"><button id="sg-featuresToggleBtn" class="sg-toolbar-btn">⚙️ Features</button></div>
				<div class="sg-toolbar-divider" id="sg-toolbar-features-divider"></div>
				<div class="sg-toolbar-section" id="sg-toolbar-zoom"><span class="sg-toolbar-label">Zoom</span><span class="sg-toolbar-zoom-value" id="sg-zoomLevel">100%</span><button id="sg-resetZoomBtn" class="sg-toolbar-btn">⟲</button></div>
			</div>`;

		canvasContainer.appendChild(toggleBtn);
		canvasContainer.appendChild(toolbarPanel);

		const closeBtn = document.getElementById('sg-toolbarClose');
		const showToolbar = () => { toolbarPanel.classList.add('show'); toggleBtn.classList.add('active'); };
		const hideToolbar = () => { toolbarPanel.classList.add('hiding'); toggleBtn.classList.remove('active'); setTimeout(() => toolbarPanel.classList.remove('show', 'hiding'), 300); };

		toggleBtn.addEventListener('click', (e) => { e.stopPropagation(); toolbarPanel.classList.contains('show') ? hideToolbar() : showToolbar(); });
		closeBtn?.addEventListener('click', (e) => { e.stopPropagation(); hideToolbar(); });
		document.addEventListener('click', (e) => {
			// Hide toolbar when clicking outside
			if (toolbarPanel.classList.contains('show') && !toolbarPanel.contains(e.target) && !toggleBtn.contains(e.target) && !e.target.closest('.sg-dialog-overlay') && !e.target.closest('#sg-analyticsPanel') && !e.target.closest('#sg-featuresPanel') && !e.target.closest('#sg-templatePanel')) hideToolbar();
			// Hide analytics panel when clicking outside (with animation)
			const analyticsPanel = document.getElementById('sg-analyticsPanel');
			const analyticsToggleBtn = document.getElementById('sg-analyticsToggleBtn');
			if (analyticsPanel?.classList.contains('show') && !analyticsPanel.contains(e.target) && !analyticsToggleBtn?.contains(e.target) && !e.target.closest('.sg-dialog-overlay') && !e.target.closest('#sg-toolbarPanel')) {
				analyticsPanel.classList.add('hiding');
				setTimeout(() => analyticsPanel.classList.remove('show', 'hiding'), 300);
			}
			// Hide features panel when clicking outside (with animation)
			const featuresPanel = document.getElementById('sg-featuresPanel');
			const featuresToggleBtn = document.getElementById('sg-featuresToggleBtn');
			if (featuresPanel?.classList.contains('show') && !featuresPanel.contains(e.target) && !featuresToggleBtn?.contains(e.target) && !e.target.closest('.sg-dialog-overlay') && !e.target.closest('#sg-toolbarPanel')) {
				featuresPanel.classList.add('hiding');
				setTimeout(() => featuresPanel.classList.remove('show', 'hiding'), 300);
			}
			// Hide template panel when clicking outside (with animation)
			const templatePanel = document.getElementById('sg-templatePanel');
			const templatesBtn = document.getElementById('sg-templatesBtn');
			if (templatePanel?.classList.contains('show') && !templatePanel.contains(e.target) && !templatesBtn?.contains(e.target) && !e.target.closest('.sg-dialog-overlay') && !e.target.closest('#sg-toolbarPanel')) {
				templatePanel.classList.add('hiding');
				setTimeout(() => templatePanel.classList.remove('show', 'hiding'), 300);
			}
		});

		const hiddenInputs = document.createElement('div');
		hiddenInputs.style.display = 'none';
		hiddenInputs.innerHTML = `<input type="file" id="sg-uploadSchemaFile" accept=".py" /><input type="file" id="sg-importFile" accept=".json" /><input type="file" id="sg-importConfigFile" accept=".json" /><input type="file" id="sg-importWorkflowFile" accept=".json" />`;
		document.body.appendChild(hiddenInputs);
	}

	_updateToolbarVisibility() {
		const toggleBtn = document.getElementById('sg-toolbarToggle');
		const toolbarPanel = document.getElementById('sg-toolbarPanel');

		// Show/hide entire toolbar
		if (toggleBtn) toggleBtn.style.display = this._features.toolbar ? '' : 'none';
		if (toolbarPanel && !this._features.toolbar) toolbarPanel.classList.remove('show');

		// Toolbar section visibility mapping
		const sectionMap = {
			toolbarVoice: ['sg-toolbar-voice', 'sg-toolbar-voice-divider'],
			toolbarAnalytics: ['sg-toolbar-analytics', 'sg-toolbar-analytics-divider'],
			toolbarSchema: ['sg-toolbar-schema', 'sg-toolbar-schema-divider'],
			toolbarWorkflow: ['sg-toolbar-workflow', 'sg-toolbar-workflow-divider'],
			toolbarTemplates: ['sg-toolbar-templates', 'sg-toolbar-templates-divider'],
			toolbarView: ['sg-toolbar-view', 'sg-toolbar-view-divider'],
			toolbarLayout: ['sg-toolbar-layout', 'sg-toolbar-layout-divider'],
			toolbarZoom: ['sg-toolbar-zoom'],
			toolbarStyle: ['sg-toolbar-style', 'sg-toolbar-style-divider'],
		};

		// Individual element visibility (textScaling, themeSwitch)
		const elementMap = {
			textScaling: 'sg-textScalingToggle',
			themeSwitch: 'sg-themeBtn',
		};
		for (const [feature, id] of Object.entries(elementMap)) {
			const el = document.getElementById(id);
			if (el) el.style.display = this._features[feature] ? '' : 'none';
		}

		for (const [feature, elementIds] of Object.entries(sectionMap)) {
			const isVisible = this._features[feature];
			for (const id of elementIds) {
				const el = document.getElementById(id);
				if (el) el.style.display = isVisible ? '' : 'none';
			}
		}

		// Analytics panel visibility
		const analyticsPanel = document.getElementById('sg-analyticsPanel');
		if (analyticsPanel && !this._features.analytics) {
			analyticsPanel.classList.remove('show');
		}

		// Sync feature toggle checkboxes with current state
		this._syncFeatureCheckboxes();
	}

	_syncFeatureCheckboxes() {
		// Basic (grouped) checkboxes
		const basicCheckboxMap = {
			'sg-feature-tooltips': this._features.nodeTooltips && this._features.fieldTooltips,
			'sg-feature-completeness': this._features.completenessIndicators,
			'sg-feature-selection': this._features.nodeSelection,
			'sg-feature-dragging': this._features.nodeDragging,
			'sg-feature-linking': this._features.linkCreation && this._features.linkDeletion,
			'sg-feature-contextmenu': this._features.contextMenu,
			'sg-feature-zooming': this._features.zooming,
			'sg-feature-panning': this._features.panning,
			'sg-feature-sectioncolors': this._features.sectionColors,
			'sg-feature-preservepreviewlinks': this._features.preservePreviewLinks,
			'sg-feature-previewflash': this._features.previewFlash,
			'sg-feature-lockoverlay': this._features.lockOverlay,
			'sg-feature-hiddenfields': this._features.hiddenFields,
			'sg-feature-prettyfieldnames': this._features.prettyFieldNames
		};

		for (const [id, checked] of Object.entries(basicCheckboxMap)) {
			const el = document.getElementById(id);
			if (el) el.checked = checked;
		}

		// Advanced (individual) checkboxes - map each feature flag to its checkbox
		for (const [feature, enabled] of Object.entries(this._features)) {
			const el = document.getElementById('sg-feature-adv-' + feature);
			if (el) el.checked = enabled;
		}
	}

	injectAnalyticsPanelHTML() {
		if (document.getElementById('sg-analyticsPanel')) return;
		const panel = document.createElement('div');
		panel.id = 'sg-analyticsPanel';
		panel.className = 'sg-analytics-panel';
		panel.innerHTML = `
			<div class="sg-analytics-header"><div class="sg-analytics-title">📊 Analytics</div><button id="sg-analyticsCloseBtn" class="sg-analytics-close">✕</button></div>
			<div class="sg-analytics-section"><div class="sg-analytics-metric"><span>Session ID:</span><span id="sg-sessionId">-</span></div><div class="sg-analytics-metric"><span>Duration:</span><span id="sg-sessionDuration">-</span></div><div class="sg-analytics-metric"><span>Events:</span><span id="sg-totalEvents">-</span></div></div>
			<div class="sg-analytics-section"><div class="sg-analytics-metric"><span>Nodes Created:</span><span id="sg-nodesCreated">0</span></div><div class="sg-analytics-metric"><span>Nodes Deleted:</span><span id="sg-nodesDeleted">0</span></div><div class="sg-analytics-metric"><span>Links Created:</span><span id="sg-linksCreated">0</span></div><div class="sg-analytics-metric"><span>Links Deleted:</span><span id="sg-linksDeleted">0</span></div></div>
			<button id="sg-refreshAnalyticsBtn" class="sg-analytics-btn">🔄 Refresh</button><button id="sg-exportAnalyticsBtn" class="sg-analytics-btn">💾 Export</button>`;
		document.body.appendChild(panel);
	}

	injectFeaturesPanelHTML() {
		if (document.getElementById('sg-featuresPanel')) return;
		const panel = document.createElement('div');
		panel.id = 'sg-featuresPanel';
		panel.className = 'sg-features-panel';
		panel.innerHTML = `
			<div class="sg-features-header">
				<div class="sg-features-title">⚙️ Features</div>
				<button id="sg-featuresCloseBtn" class="sg-features-close">✕</button>
			</div>
			<div class="sg-features-section">
				<div class="sg-features-category-label">Quick Toggles</div>
				<div class="sg-features-grid">
					<label class="sg-toolbar-toggle-switch" title="Enable/disable tooltips on nodes and fields">
						<input type="checkbox" id="sg-feature-tooltips" checked>
						<span class="sg-toolbar-toggle-slider"></span>
						<span class="sg-toolbar-toggle-text">Tooltips</span>
					</label>
					<label class="sg-toolbar-toggle-switch" title="Show completeness badges and link indicators">
						<input type="checkbox" id="sg-feature-completeness" checked>
						<span class="sg-toolbar-toggle-slider"></span>
						<span class="sg-toolbar-toggle-text">Completeness</span>
					</label>
					<label class="sg-toolbar-toggle-switch" title="Allow selecting nodes">
						<input type="checkbox" id="sg-feature-selection" checked>
						<span class="sg-toolbar-toggle-slider"></span>
						<span class="sg-toolbar-toggle-text">Selection</span>
					</label>
					<label class="sg-toolbar-toggle-switch" title="Allow dragging nodes to reposition">
						<input type="checkbox" id="sg-feature-dragging" checked>
						<span class="sg-toolbar-toggle-slider"></span>
						<span class="sg-toolbar-toggle-text">Dragging</span>
					</label>
					<label class="sg-toolbar-toggle-switch" title="Allow creating and removing links">
						<input type="checkbox" id="sg-feature-linking" checked>
						<span class="sg-toolbar-toggle-slider"></span>
						<span class="sg-toolbar-toggle-text">Linking</span>
					</label>
					<label class="sg-toolbar-toggle-switch" title="Enable right-click context menu">
						<input type="checkbox" id="sg-feature-contextmenu" checked>
						<span class="sg-toolbar-toggle-slider"></span>
						<span class="sg-toolbar-toggle-text">Context Menu</span>
					</label>
					<label class="sg-toolbar-toggle-switch" title="Allow zooming with mouse wheel">
						<input type="checkbox" id="sg-feature-zooming" checked>
						<span class="sg-toolbar-toggle-slider"></span>
						<span class="sg-toolbar-toggle-text">Zooming</span>
					</label>
					<label class="sg-toolbar-toggle-switch" title="Allow panning the canvas">
						<input type="checkbox" id="sg-feature-panning" checked>
						<span class="sg-toolbar-toggle-slider"></span>
						<span class="sg-toolbar-toggle-text">Panning</span>
					</label>
					<label class="sg-toolbar-toggle-switch" title="Color node headers by section">
						<input type="checkbox" id="sg-feature-sectioncolors" checked>
						<span class="sg-toolbar-toggle-slider"></span>
						<span class="sg-toolbar-toggle-text">Section Colors</span>
					</label>
					<label class="sg-toolbar-toggle-switch" title="Preserve connections when deleting preview nodes">
						<input type="checkbox" id="sg-feature-preservepreviewlinks" checked>
						<span class="sg-toolbar-toggle-slider"></span>
						<span class="sg-toolbar-toggle-text">Preserve Links</span>
					</label>
					<label class="sg-toolbar-toggle-switch" title="Flash animation when preview data updates">
						<input type="checkbox" id="sg-feature-previewflash" checked>
						<span class="sg-toolbar-toggle-slider"></span>
						<span class="sg-toolbar-toggle-text">Preview Flash</span>
					</label>
					<label class="sg-toolbar-toggle-switch" title="Show lock status overlay when graph is locked">
						<input type="checkbox" id="sg-feature-lockoverlay" checked>
						<span class="sg-toolbar-toggle-slider"></span>
						<span class="sg-toolbar-toggle-text">Lock Overlay</span>
					</label>
					<label class="sg-toolbar-toggle-switch" title="Hide specified fields (e.g. extra) from nodes">
						<input type="checkbox" id="sg-feature-hiddenfields" checked>
						<span class="sg-toolbar-toggle-slider"></span>
						<span class="sg-toolbar-toggle-text">Hidden Fields</span>
					</label>
					<label class="sg-toolbar-toggle-switch" title="Convert snake_case/camelCase field names to Title Case">
						<input type="checkbox" id="sg-feature-prettyfieldnames" checked>
						<span class="sg-toolbar-toggle-slider"></span>
						<span class="sg-toolbar-toggle-text">Pretty Names</span>
					</label>
				</div>
			</div>
			<button id="sg-features-advanced-toggle" class="sg-features-advanced-btn">▼ Advanced Options</button>
			<div class="sg-features-advanced" id="sg-features-advanced-panel">
				<div class="sg-features-section">
					<div class="sg-features-category-label">Toolbar Sections</div>
					<div class="sg-features-grid">
						<label class="sg-toolbar-toggle-switch" title="Show/hide entire toolbar">
							<input type="checkbox" id="sg-feature-adv-toolbar" checked>
							<span class="sg-toolbar-toggle-slider"></span>
							<span class="sg-toolbar-toggle-text">Toolbar</span>
						</label>
						<label class="sg-toolbar-toggle-switch" title="Voice controls section">
							<input type="checkbox" id="sg-feature-adv-toolbarVoice" checked>
							<span class="sg-toolbar-toggle-slider"></span>
							<span class="sg-toolbar-toggle-text">Voice</span>
						</label>
						<label class="sg-toolbar-toggle-switch" title="Analytics section">
							<input type="checkbox" id="sg-feature-adv-toolbarAnalytics" checked>
							<span class="sg-toolbar-toggle-slider"></span>
							<span class="sg-toolbar-toggle-text">Analytics</span>
						</label>
						<label class="sg-toolbar-toggle-switch" title="Schema section">
							<input type="checkbox" id="sg-feature-adv-toolbarSchema" checked>
							<span class="sg-toolbar-toggle-slider"></span>
							<span class="sg-toolbar-toggle-text">Schema</span>
						</label>
						<label class="sg-toolbar-toggle-switch" title="Workflow section">
							<input type="checkbox" id="sg-feature-adv-toolbarWorkflow" checked>
							<span class="sg-toolbar-toggle-slider"></span>
							<span class="sg-toolbar-toggle-text">Workflow</span>
						</label>
						<label class="sg-toolbar-toggle-switch" title="View section">
							<input type="checkbox" id="sg-feature-adv-toolbarView" checked>
							<span class="sg-toolbar-toggle-slider"></span>
							<span class="sg-toolbar-toggle-text">View</span>
						</label>
						<label class="sg-toolbar-toggle-switch" title="Layout section">
							<input type="checkbox" id="sg-feature-adv-toolbarLayout" checked>
							<span class="sg-toolbar-toggle-slider"></span>
							<span class="sg-toolbar-toggle-text">Layout</span>
						</label>
						<label class="sg-toolbar-toggle-switch" title="Zoom section">
							<input type="checkbox" id="sg-feature-adv-toolbarZoom" checked>
							<span class="sg-toolbar-toggle-slider"></span>
							<span class="sg-toolbar-toggle-text">Zoom</span>
						</label>
						<label class="sg-toolbar-toggle-switch" title="Style section">
							<input type="checkbox" id="sg-feature-adv-toolbarStyle" checked>
							<span class="sg-toolbar-toggle-slider"></span>
							<span class="sg-toolbar-toggle-text">Style</span>
						</label>
					</div>
				</div>
				<div class="sg-features-section">
					<div class="sg-features-category-label">Interactions</div>
					<div class="sg-features-grid">
						<label class="sg-toolbar-toggle-switch" title="Allow selecting individual nodes">
							<input type="checkbox" id="sg-feature-adv-nodeSelection" checked>
							<span class="sg-toolbar-toggle-slider"></span>
							<span class="sg-toolbar-toggle-text">Node Selection</span>
						</label>
						<label class="sg-toolbar-toggle-switch" title="Allow selecting multiple nodes">
							<input type="checkbox" id="sg-feature-adv-multiSelection" checked>
							<span class="sg-toolbar-toggle-slider"></span>
							<span class="sg-toolbar-toggle-text">Multi Selection</span>
						</label>
						<label class="sg-toolbar-toggle-switch" title="Allow dragging nodes">
							<input type="checkbox" id="sg-feature-adv-nodeDragging" checked>
							<span class="sg-toolbar-toggle-slider"></span>
							<span class="sg-toolbar-toggle-text">Node Dragging</span>
						</label>
						<label class="sg-toolbar-toggle-switch" title="Allow creating links between nodes">
							<input type="checkbox" id="sg-feature-adv-linkCreation" checked>
							<span class="sg-toolbar-toggle-slider"></span>
							<span class="sg-toolbar-toggle-text">Link Creation</span>
						</label>
						<label class="sg-toolbar-toggle-switch" title="Allow deleting links">
							<input type="checkbox" id="sg-feature-adv-linkDeletion" checked>
							<span class="sg-toolbar-toggle-slider"></span>
							<span class="sg-toolbar-toggle-text">Link Deletion</span>
						</label>
						<label class="sg-toolbar-toggle-switch" title="Allow panning the canvas">
							<input type="checkbox" id="sg-feature-adv-panning" checked>
							<span class="sg-toolbar-toggle-slider"></span>
							<span class="sg-toolbar-toggle-text">Panning</span>
						</label>
						<label class="sg-toolbar-toggle-switch" title="Allow zooming with mouse wheel">
							<input type="checkbox" id="sg-feature-adv-zooming" checked>
							<span class="sg-toolbar-toggle-slider"></span>
							<span class="sg-toolbar-toggle-text">Zooming</span>
						</label>
						<label class="sg-toolbar-toggle-switch" title="Enable right-click context menu">
							<input type="checkbox" id="sg-feature-adv-contextMenu" checked>
							<span class="sg-toolbar-toggle-slider"></span>
							<span class="sg-toolbar-toggle-text">Context Menu</span>
						</label>
					</div>
				</div>
				<div class="sg-features-section">
					<div class="sg-features-category-label">Tooltips & Visual</div>
					<div class="sg-features-grid">
						<label class="sg-toolbar-toggle-switch" title="Show tooltips on node headers">
							<input type="checkbox" id="sg-feature-adv-nodeTooltips" checked>
							<span class="sg-toolbar-toggle-slider"></span>
							<span class="sg-toolbar-toggle-text">Node Tooltips</span>
						</label>
						<label class="sg-toolbar-toggle-switch" title="Show tooltips on input/output fields">
							<input type="checkbox" id="sg-feature-adv-fieldTooltips" checked>
							<span class="sg-toolbar-toggle-slider"></span>
							<span class="sg-toolbar-toggle-text">Field Tooltips</span>
						</label>
						<label class="sg-toolbar-toggle-switch" title="Show completeness badges and indicators">
							<input type="checkbox" id="sg-feature-adv-completenessIndicators" checked>
							<span class="sg-toolbar-toggle-slider"></span>
							<span class="sg-toolbar-toggle-text">Completeness</span>
						</label>
						<label class="sg-toolbar-toggle-switch" title="Enable analytics tracking">
							<input type="checkbox" id="sg-feature-adv-analytics" checked>
							<span class="sg-toolbar-toggle-slider"></span>
							<span class="sg-toolbar-toggle-text">Analytics</span>
						</label>
						<label class="sg-toolbar-toggle-switch" title="Enable text scaling toggle">
							<input type="checkbox" id="sg-feature-adv-textScaling" checked>
							<span class="sg-toolbar-toggle-slider"></span>
							<span class="sg-toolbar-toggle-text">Text Scaling</span>
						</label>
						<label class="sg-toolbar-toggle-switch" title="Enable theme switch button">
							<input type="checkbox" id="sg-feature-adv-themeSwitch" checked>
							<span class="sg-toolbar-toggle-slider"></span>
							<span class="sg-toolbar-toggle-text">Theme Switch</span>
						</label>
						<label class="sg-toolbar-toggle-switch" title="Automatic preview on media content">
							<input type="checkbox" id="sg-feature-adv-autoPreview" checked>
							<span class="sg-toolbar-toggle-slider"></span>
							<span class="sg-toolbar-toggle-text">Auto Preview</span>
						</label>
						<label class="sg-toolbar-toggle-switch" title="Alt+Click on links to insert preview nodes">
							<input type="checkbox" id="sg-feature-adv-edgePreview" checked>
							<span class="sg-toolbar-toggle-slider"></span>
							<span class="sg-toolbar-toggle-text">Edge Preview</span>
						</label>
						<label class="sg-toolbar-toggle-switch" title="Use orthogonal routing for loop-back edges">
							<input type="checkbox" id="sg-feature-adv-loopEdgeOrthogonal" checked>
							<span class="sg-toolbar-toggle-slider"></span>
							<span class="sg-toolbar-toggle-text">Orthogonal Loop Edges</span>
						</label>
					</div>
				</div>
				<div class="sg-features-section">
					<div class="sg-features-category-label">Node Types</div>
					<div class="sg-features-grid">
						<label class="sg-toolbar-toggle-switch" title="Show native types (String, Integer, Boolean, Float, List, Dict) in node menu">
							<input type="checkbox" id="sg-feature-adv-nativeTypes" checked>
							<span class="sg-toolbar-toggle-slider"></span>
							<span class="sg-toolbar-toggle-text">Native Types</span>
						</label>
					</div>
				</div>
				<div class="sg-features-actions">
					<button id="sg-features-enable-all" class="sg-features-btn">Enable All</button>
					<button id="sg-features-disable-all" class="sg-features-btn">Disable All</button>
					<button id="sg-features-reset" class="sg-features-btn">Reset</button>
				</div>
			</div>`;
		document.body.appendChild(panel);
	}

	injectTemplatePanelHTML() {
		if (document.getElementById('sg-templatePanel')) return;
		const panel = document.createElement('div');
		panel.id = 'sg-templatePanel';
		panel.className = 'sg-template-panel';
		panel.innerHTML = `
			<div class="sg-template-header">
				<div class="sg-template-title">Templates</div>
				<button id="sg-templateCloseBtn" class="sg-template-close">\u2715</button>
			</div>
			<div class="sg-template-list" id="sg-templateList"></div>
			<div class="sg-template-empty" id="sg-templateEmpty">
				No templates saved yet.<br>Select multiple nodes and right-click to save as template.
			</div>`;
		document.body.appendChild(panel);

		document.getElementById('sg-templateCloseBtn').addEventListener('click', () => this.toggleTemplatePanel());
	}

	// === GENERATE WORKFLOW MODAL ===

	injectGenerateWorkflowHTML() {
		if (document.getElementById('sg-generateModal')) return;
		const modal = document.createElement('div');
		modal.id = 'sg-generateModal';
		modal.className = 'sg-generate-modal';
		modal.innerHTML = `
			<div class="sg-generate-container">
				<div class="sg-generate-header">
					<span class="sg-generate-title">Generate Workflow</span>
					<div class="sg-generate-config">
						<select id="sg-generateProvider">
							<option value="ollama">Ollama</option>
							<option value="openai">OpenAI</option>
							<option value="anthropic">Anthropic</option>
						</select>
						<input id="sg-generateModel" type="text" placeholder="model name" value="mistral">
					</div>
					<button id="sg-generateClose" class="sg-generate-close">\u2715</button>
				</div>
				<div class="sg-generate-body">
					<div class="sg-generate-messages" id="sg-generateMessages"></div>
					<div class="sg-generate-input-row">
						<textarea id="sg-generatePrompt" rows="3" placeholder="Describe your workflow..."></textarea>
						<button id="sg-generateBtn" class="sg-generate-btn">Generate</button>
					</div>
				</div>
				<div class="sg-generate-preview" id="sg-generatePreview" style="display:none">
					<div class="sg-generate-preview-header">Generated Workflow</div>
					<pre id="sg-generatePreviewJson"></pre>
					<div class="sg-generate-preview-actions">
						<button id="sg-generateImport" class="sg-generate-btn">Import to Canvas</button>
						<button id="sg-generateRetry" class="sg-generate-btn secondary">Retry</button>
					</div>
				</div>
				<div class="sg-generate-status" id="sg-generateStatus"></div>
			</div>`;
		document.body.appendChild(modal);

		// Wire close
		document.getElementById('sg-generateClose').addEventListener('click', () => this._closeGenerateWorkflow());
		modal.addEventListener('click', (e) => { if (e.target === modal) this._closeGenerateWorkflow(); });

		// Wire generate button
		document.getElementById('sg-generateBtn').addEventListener('click', () => this._handleGenerate());

		// Wire import button
		document.getElementById('sg-generateImport').addEventListener('click', () => this._handleGenerateImport());

		// Wire retry button
		document.getElementById('sg-generateRetry').addEventListener('click', () => this._handleGenerate());

		// Enter key in textarea sends (Shift+Enter for newline)
		document.getElementById('sg-generatePrompt').addEventListener('keydown', (e) => {
			if (e.key === 'Enter' && !e.shiftKey) {
				e.preventDefault();
				this._handleGenerate();
			}
		});
	}

	showGenerateWorkflow() {
		const modal = document.getElementById('sg-generateModal');
		if (!modal) return;
		modal.classList.add('show');
		// Focus the prompt textarea
		setTimeout(() => document.getElementById('sg-generatePrompt')?.focus(), 100);
	}

	_closeGenerateWorkflow() {
		const modal = document.getElementById('sg-generateModal');
		if (!modal) return;
		modal.classList.remove('show');
	}

	_addGenerateMessage(role, content) {
		const messagesEl = document.getElementById('sg-generateMessages');
		if (!messagesEl) return;
		const msg = document.createElement('div');
		msg.className = `sg-generate-msg sg-generate-msg-${role}`;
		const roleLabel = document.createElement('div');
		roleLabel.className = 'sg-generate-msg-role';
		roleLabel.textContent = role === 'user' ? 'You' : role === 'assistant' ? 'Assistant' : 'Error';
		msg.appendChild(roleLabel);
		const text = document.createElement('div');
		text.textContent = content;
		msg.appendChild(text);
		messagesEl.appendChild(msg);
		messagesEl.scrollTop = messagesEl.scrollHeight;
	}

	async _handleGenerate() {
		const promptEl = document.getElementById('sg-generatePrompt');
		const statusEl = document.getElementById('sg-generateStatus');
		const generateBtn = document.getElementById('sg-generateBtn');
		const previewEl = document.getElementById('sg-generatePreview');
		const previewJsonEl = document.getElementById('sg-generatePreviewJson');
		const providerEl = document.getElementById('sg-generateProvider');
		const modelEl = document.getElementById('sg-generateModel');

		const userText = promptEl?.value?.trim();
		if (!userText) return;

		// Add user message to chat
		this._addGenerateMessage('user', userText);
		promptEl.value = '';

		// Initialize conversation history
		this._generateHistory = this._generateHistory || [];
		this._generateHistory.push({ role: 'user', content: userText });

		// Show loading state
		generateBtn.disabled = true;
		generateBtn.textContent = 'Generating...';
		statusEl.textContent = 'Sending to LLM...';
		previewEl.style.display = 'none';

		try {
			const baseUrl = this._generateBaseUrl || '';
			const resp = await fetch(baseUrl + '/generate-workflow', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({
					prompt: userText,
					provider: providerEl?.value || 'ollama',
					model: modelEl?.value || 'mistral',
					temperature: 0.3,
					max_tokens: 4096,
					history: this._generateHistory.slice(0, -1) // Send history before current message
				})
			});

			if (!resp.ok) {
				const errText = await resp.text();
				throw new Error(errText || `HTTP ${resp.status}`);
			}

			const data = await resp.json();
			this._lastGeneratedWorkflow = data.workflow;

			// Add assistant message
			const summary = data.message || `Generated ${data.workflow?.nodes?.length || 0} nodes, ${data.workflow?.edges?.length || 0} edges`;
			this._addGenerateMessage('assistant', summary);
			this._generateHistory.push({ role: 'assistant', content: summary });

			// Show preview
			previewJsonEl.textContent = JSON.stringify(data.workflow, null, 2);
			previewEl.style.display = 'block';
			statusEl.textContent = summary;
		} catch (err) {
			this._addGenerateMessage('error', err.message);
			statusEl.textContent = 'Generation failed';
			// Remove the failed user message from history so retry is clean
			this._generateHistory.pop();
			console.error('[GenerateWorkflow] Error:', err);
		} finally {
			generateBtn.disabled = false;
			generateBtn.textContent = 'Generate';
		}
	}

	_handleGenerateImport() {
		if (!this._lastGeneratedWorkflow) {
			this.showError('No generated workflow to import');
			return;
		}

		const schemas = this.graph.getRegisteredSchemas().filter(s => this.graph.isWorkflowSchema(s));
		if (schemas.length === 0) {
			this.showError('No workflow schema registered');
			return;
		}

		try {
			this.api.workflow.import(this._lastGeneratedWorkflow, schemas[0], {});
			this.centerView();
			this._closeGenerateWorkflow();

			// Clear conversation state for next session
			this._generateHistory = [];
			document.getElementById('sg-generateMessages').innerHTML = '';
			document.getElementById('sg-generatePreview').style.display = 'none';
			document.getElementById('sg-generateStatus').textContent = '';
		} catch (err) {
			this.showError('Import failed: ' + err.message);
		}
	}

	toggleTemplatePanel() {
		const panel = document.getElementById('sg-templatePanel');
		if (!panel) return;
		if (panel.classList.contains('show')) {
			panel.classList.add('hiding');
			setTimeout(() => panel.classList.remove('show', 'hiding'), 300);
		} else {
			panel.classList.add('show');
			this.refreshTemplateList();
		}
	}

	async refreshTemplateList() {
		const listEl = document.getElementById('sg-templateList');
		const emptyEl = document.getElementById('sg-templateEmpty');
		if (!listEl || !emptyEl) return;

		let templates = [];
		try {
			const url = (this._templateBaseUrl || '') + '/templates/list';
			const resp = await fetch(url, { method: 'POST' });
			if (resp.ok) {
				const data = await resp.json();
				templates = data.templates || [];
			}
		} catch (e) {
			console.warn('[Templates] Failed to fetch list:', e);
		}

		if (templates.length === 0) {
			listEl.innerHTML = '';
			emptyEl.style.display = 'block';
			return;
		}

		emptyEl.style.display = 'none';
		listEl.innerHTML = templates.map(t => {
			const badge = t.builtIn ? '<span class="sg-template-item-badge">built-in</span>' : '';
			const actions = t.builtIn
				? `<button class="sg-template-item-btn sg-template-insert" data-id="${t.id}" title="Insert">+</button>`
				: `<button class="sg-template-item-btn sg-template-insert" data-id="${t.id}" title="Insert">+</button>
				   <button class="sg-template-item-btn sg-template-rename" data-id="${t.id}" title="Rename">\u270E</button>
				   <button class="sg-template-item-btn sg-template-delete" data-id="${t.id}" title="Delete">\u2715</button>`;
			return `<div class="sg-template-item" data-template-id="${t.id}">
				<div class="sg-template-item-info">
					<div class="sg-template-item-name">${t.name || 'Untitled'}${badge}</div>
					<div class="sg-template-item-meta">${t.nodeCount} nodes, ${t.edgeCount} edges</div>
				</div>
				<div class="sg-template-item-actions">${actions}</div>
			</div>`;
		}).join('');

		// Wire handlers
		listEl.querySelectorAll('.sg-template-insert').forEach(btn => {
			btn.addEventListener('click', (e) => {
				e.stopPropagation();
				this._handleTemplateInsert(btn.dataset.id);
			});
		});
		listEl.querySelectorAll('.sg-template-rename').forEach(btn => {
			btn.addEventListener('click', (e) => {
				e.stopPropagation();
				this._handleTemplateRename(btn.dataset.id);
			});
		});
		listEl.querySelectorAll('.sg-template-delete').forEach(btn => {
			btn.addEventListener('click', (e) => {
				e.stopPropagation();
				this._handleTemplateDelete(btn.dataset.id);
			});
		});
	}

	_handleTemplateInsert(templateId) {
		// Compute viewport center in world coordinates
		const centerX = (-this.camera.x + this.canvas.width / 2) / this.camera.scale;
		const centerY = (-this.camera.y + this.canvas.height / 2) / this.camera.scale;
		this.instantiateTemplate(templateId, centerX, centerY);
	}

	async _handleTemplateRename(templateId) {
		const newName = await this._showInputDialog('Rename Template', 'New name:', '');
		if (!newName) return;
		try {
			const url = (this._templateBaseUrl || '') + '/templates/rename/' + templateId;
			const resp = await fetch(url, {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ name: newName })
			});
			if (!resp.ok) throw new Error(await resp.text());
			this.refreshTemplateList();
		} catch (e) {
			this.showError('Failed to rename template: ' + e.message);
		}
	}

	async _handleTemplateDelete(templateId) {
		const confirm = await this._showConfirmDialog('Delete Template', 'Are you sure you want to delete this template?', 'Delete', true);
		if (!confirm) return;
		try {
			const url = (this._templateBaseUrl || '') + '/templates/delete/' + templateId;
			const resp = await fetch(url, { method: 'POST' });
			if (!resp.ok) throw new Error(await resp.text());
			this.refreshTemplateList();
		} catch (e) {
			this.showError('Failed to delete template: ' + e.message);
		}
	}

	injectMultiSlotUIStyles() {
		if (document.getElementById('sg-multislot-ui-styles')) return;

		const style = document.createElement('style');
		style.id = 'sg-multislot-ui-styles';
		style.textContent = `
			.sg-input-dialog-overlay { position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0, 0, 0, 0.6); z-index: 10000; display: flex; align-items: center; justify-content: center; }
			.sg-input-dialog { background: var(--sg-bg-secondary, #252540); border: 1px solid var(--sg-border-color, #404060); border-radius: 8px; min-width: 300px; max-width: 400px; box-shadow: 0 8px 32px rgba(0,0,0,0.5); animation: sg-dialog-appear 0.15s ease-out; }
			@keyframes sg-dialog-appear { from { opacity: 0; transform: scale(0.95); } to { opacity: 1; transform: scale(1); } }
			.sg-input-dialog-header { display: flex; justify-content: space-between; align-items: center; padding: 12px 16px; border-bottom: 1px solid var(--sg-border-color, #404060); background: var(--sg-node-header, #404060); border-radius: 8px 8px 0 0; }
			.sg-input-dialog-title { font-weight: 600; color: var(--sg-text-primary, #ffffff); font-size: 14px; }
			.sg-input-dialog-close { background: none; border: none; color: var(--sg-text-tertiary, #808090); font-size: 20px; cursor: pointer; padding: 0; width: 24px; height: 24px; display: flex; align-items: center; justify-content: center; border-radius: 4px; line-height: 1; }
			.sg-input-dialog-close:hover { background: rgba(255,255,255,0.1); color: var(--sg-text-primary, #ffffff); }
			.sg-input-dialog-body { padding: 16px; }
			.sg-input-dialog-label { display: block; color: var(--sg-text-secondary, #b0b0c0); font-size: 13px; margin-bottom: 8px; }
			.sg-input-dialog-input { width: 100%; background: var(--sg-canvas-bg, #1a1a2e); border: 1px solid var(--sg-border-color, #404060); border-radius: 4px; padding: 10px 12px; color: var(--sg-text-primary, #ffffff); font-size: 14px; font-family: 'Monaco', 'Menlo', monospace; box-sizing: border-box; }
			.sg-input-dialog-input:focus { outline: none; border-color: var(--sg-border-highlight, #46a2da); box-shadow: 0 0 0 2px rgba(70, 162, 218, 0.3); }
			.sg-input-dialog-input::placeholder { color: var(--sg-text-tertiary, #808090); }
			.sg-confirm-dialog-message { color: var(--sg-text-secondary, #b0b0c0); font-size: 14px; margin: 0; line-height: 1.5; }
			.sg-input-dialog-footer { display: flex; justify-content: flex-end; gap: 8px; padding: 12px 16px; border-top: 1px solid var(--sg-border-color, #404060); background: rgba(0,0,0,0.2); border-radius: 0 0 8px 8px; }
			.sg-input-dialog-btn { padding: 8px 16px; border-radius: 4px; font-size: 13px; font-weight: 500; cursor: pointer; border: 1px solid transparent; transition: all 0.15s; }
			.sg-input-dialog-cancel { background: rgba(255,255,255,0.1); color: var(--sg-text-secondary, #b0b0c0); border-color: var(--sg-border-color, #404060); }
			.sg-input-dialog-cancel:hover { background: rgba(255,255,255,0.15); color: var(--sg-text-primary, #ffffff); }
			.sg-input-dialog-confirm { background: var(--sg-border-highlight, #46a2da); color: #ffffff; }
			.sg-input-dialog-confirm:hover { background: #5bb0e5; }
			.sg-input-dialog-confirm.sg-confirm-danger { background: var(--sg-accent-red, #dc6068); }
			.sg-input-dialog-confirm.sg-confirm-danger:hover { background: #e57078; }
			.sg-slot-manager-overlay { position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0, 0, 0, 0.6); z-index: 10000; display: flex; align-items: center; justify-content: center; }
			.sg-slot-manager { background: var(--sg-bg-secondary, #252540); border: 1px solid var(--sg-border-color, #404060); border-radius: 8px; min-width: 320px; max-width: 480px; max-height: 80vh; display: flex; flex-direction: column; box-shadow: 0 8px 32px rgba(0,0,0,0.5); }
			.sg-slot-manager-header { display: flex; justify-content: space-between; align-items: center; padding: 12px 16px; border-bottom: 1px solid var(--sg-border-color, #404060); background: var(--sg-node-header, #404060); border-radius: 8px 8px 0 0; }
			.sg-slot-manager-title { font-weight: 600; color: var(--sg-text-primary, #ffffff); font-size: 14px; }
			.sg-slot-manager-close { background: none; border: none; color: var(--sg-text-tertiary, #808090); font-size: 20px; cursor: pointer; padding: 0; width: 24px; height: 24px; display: flex; align-items: center; justify-content: center; border-radius: 4px; }
			.sg-slot-manager-close:hover { background: rgba(255,255,255,0.1); color: var(--sg-text-primary, #ffffff); }
			.sg-slot-manager-body { padding: 16px; overflow-y: auto; flex: 1; }
			.sg-slot-manager-list { display: flex; flex-direction: column; gap: 8px; }
			.sg-slot-item { display: flex; align-items: center; gap: 8px; padding: 8px 12px; background: rgba(0,0,0,0.2); border: 1px solid var(--sg-border-color, #404060); border-radius: 6px; }
			.sg-slot-item-key { flex: 1; background: var(--sg-canvas-bg, #1a1a2e); border: 1px solid var(--sg-border-color, #404060); border-radius: 4px; padding: 6px 10px; color: var(--sg-text-primary, #ffffff); font-size: 13px; font-family: 'Monaco', 'Menlo', monospace; }
			.sg-slot-item-key:focus { outline: none; border-color: var(--sg-border-highlight, #46a2da); }
			.sg-slot-item-connected { font-size: 10px; color: var(--sg-accent-green, #50c878); padding: 2px 6px; background: rgba(80, 200, 120, 0.15); border-radius: 3px; }
			.sg-slot-item-btn { background: none; border: none; color: var(--sg-text-tertiary, #808090); font-size: 14px; cursor: pointer; padding: 4px; border-radius: 4px; display: flex; align-items: center; justify-content: center; }
			.sg-slot-item-btn:hover { background: rgba(255,255,255,0.1); color: var(--sg-text-primary, #ffffff); }
			.sg-slot-item-btn.delete:hover { background: rgba(220, 96, 104, 0.2); color: var(--sg-accent-red, #dc6068); }
			.sg-slot-item-btn:disabled { opacity: 0.3; cursor: not-allowed; }
			.sg-slot-manager-footer { display: flex; justify-content: space-between; align-items: center; padding: 12px 16px; border-top: 1px solid var(--sg-border-color, #404060); background: rgba(0,0,0,0.2); border-radius: 0 0 8px 8px; }
			.sg-slot-add-row { display: flex; gap: 8px; flex: 1; }
			.sg-slot-add-input { flex: 1; background: var(--sg-canvas-bg, #1a1a2e); border: 1px solid var(--sg-border-color, #404060); border-radius: 4px; padding: 8px 12px; color: var(--sg-text-primary, #ffffff); font-size: 13px; }
			.sg-slot-add-input:focus { outline: none; border-color: var(--sg-border-highlight, #46a2da); }
			.sg-slot-add-input::placeholder { color: var(--sg-text-tertiary, #808090); }
			.sg-slot-add-btn { background: var(--sg-border-highlight, #46a2da); border: none; color: #ffffff; padding: 8px 16px; border-radius: 4px; cursor: pointer; font-size: 13px; font-weight: 500; }
			.sg-slot-add-btn:hover { background: #5bb0e5; }
			.sg-slot-empty { text-align: center; color: var(--sg-text-tertiary, #808090); padding: 20px; font-style: italic; }
		`;
		document.head.appendChild(style);
	}

	injectInteractiveStyles() {
		if (document.getElementById('sg-interactive-styles')) return;
		const style = document.createElement('style');
		style.id = 'sg-interactive-styles';
		style.textContent = `
			.sg-file-drag-over { outline: 3px dashed #92d050 !important; outline-offset: -3px; }
			.sg-tooltip { position: fixed; z-index: 10000; background: var(--sg-node-bg, #252540); border: 1px solid var(--sg-border-color, #404060); border-radius: 6px; padding: 8px 12px; max-width: 280px; box-shadow: 0 4px 16px rgba(0,0,0,0.4); pointer-events: none; font-size: 12px; color: var(--sg-text-primary, #fff); }
			.sg-tooltip-title { font-weight: 600; color: var(--sg-text-primary, #fff); margin-bottom: 4px; }
			.sg-tooltip-desc { color: var(--sg-text-secondary, #b0b0c0); margin-bottom: 6px; line-height: 1.4; }
			.sg-tooltip-field { font-family: 'Monaco', 'Menlo', monospace; font-size: 11px; color: var(--sg-text-tertiary, #808090); margin-bottom: 4px; }
			.sg-tooltip-type { font-family: 'Monaco', 'Menlo', monospace; font-size: 10px; color: var(--sg-accent-purple, #9370db); background: rgba(147, 112, 219, 0.15); padding: 2px 6px; border-radius: 3px; display: inline-block; margin-right: 4px; }
			.sg-tooltip-badge { font-size: 10px; padding: 2px 6px; border-radius: 3px; display: inline-block; margin-right: 4px; }
			.sg-tooltip-badge.multi { background: rgba(147, 112, 219, 0.2); color: var(--sg-accent-purple, #9370db); }
			.sg-tooltip-badge.required { background: rgba(220, 96, 104, 0.2); color: var(--sg-accent-red, #dc6068); }
			.sg-tooltip-badge.optional { background: rgba(80, 200, 120, 0.2); color: var(--sg-accent-green, #50c878); }
			.sg-node-tooltip { position: fixed; z-index: 10000; background: var(--sg-node-bg, #252540); border: 1px solid var(--sg-border-color, #404060); border-radius: 8px; padding: 10px 14px; max-width: 320px; box-shadow: 0 6px 20px rgba(0,0,0,0.5); pointer-events: none; font-size: 12px; color: var(--sg-text-primary, #fff); }
			.sg-node-tooltip-header { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }
			.sg-node-tooltip-icon { font-size: 18px; }
			.sg-node-tooltip-title { font-weight: 600; font-size: 14px; color: var(--sg-text-primary, #fff); }
			.sg-node-tooltip-desc { color: var(--sg-text-secondary, #b0b0c0); line-height: 1.5; }
			.sg-node-tooltip-section { margin-top: 6px; font-size: 10px; color: var(--sg-text-tertiary, #808090); text-transform: uppercase; letter-spacing: 0.5px; }
			.sg-node-tooltip-meta { margin-top: 8px; padding-top: 8px; border-top: 1px solid var(--sg-border-color, #404060); font-size: 11px; }
			.sg-node-tooltip-meta-item { display: flex; gap: 6px; margin-bottom: 3px; color: var(--sg-text-secondary, #b0b0c0); }
			.sg-node-tooltip-meta-label { color: var(--sg-text-tertiary, #808090); min-width: 50px; }
			.sg-node-tooltip-incomplete { color: var(--sg-accent-red, #dc6068) !important; }
			.sg-node-tooltip-complete { color: var(--sg-accent-green, #50c878) !important; }
			.sg-node-tooltip-badge-row { margin-top: 6px; }
			.sg-node-tooltip-type-badge { font-size: 9px; padding: 2px 6px; border-radius: 3px; text-transform: uppercase; letter-spacing: 0.5px; }
			.sg-node-tooltip-type-badge.native { background: rgba(147, 112, 219, 0.2); color: var(--sg-accent-purple, #9370db); }
			.sg-node-tooltip-type-badge.root { background: rgba(245, 166, 35, 0.2); color: var(--sg-accent-orange, #f5a623); }
		`;
		document.head.appendChild(style);
	}

	injectPreviewOverlayStyles() {
		if (document.getElementById('sg-preview-overlay-styles')) return;
		const style = document.createElement('style');
		style.id = 'sg-preview-overlay-styles';
		style.textContent = `
			.sg-preview-text-overlay {
				position: absolute;
				pointer-events: auto;
				font-family: 'Monaco', 'Menlo', 'Courier New', monospace;
				font-size: 12px;
				border-radius: var(--sg-node-radius, 6px);
				overflow: hidden;
				box-shadow: 0 4px 20px var(--sg-node-shadow, rgba(0,0,0,0.4));
				z-index: 100;
				display: flex;
				flex-direction: column;
				background: var(--sg-node-bg, var(--sg-bg-secondary, #2a2a2a));
				border: 1px solid var(--sg-border-color, #1a1a1a);
			}
			.sg-preview-text-header {
				display: flex;
				justify-content: space-between;
				align-items: center;
				padding: 4px 8px;
				background: var(--sg-node-header, #4a5568);
				border-bottom: 1px solid var(--sg-border-color, #1a1a1a);
				cursor: default;
				user-select: none;
			}
			.sg-preview-text-title {
				font-size: 11px;
				font-weight: 600;
				color: var(--sg-text-primary, #ffffff);
				font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
				overflow: hidden;
				text-overflow: ellipsis;
				white-space: nowrap;
			}
			.sg-preview-text-actions {
				display: flex;
				gap: 4px;
				flex-shrink: 0;
			}
			.sg-preview-text-btn {
				background: transparent;
				border: none;
				color: var(--sg-text-tertiary, #707070);
				width: 20px;
				height: 20px;
				border-radius: 3px;
				cursor: pointer;
				font-size: 12px;
				display: flex;
				align-items: center;
				justify-content: center;
				padding: 0;
			}
			.sg-preview-text-btn:hover {
				background: var(--sg-bg-tertiary, rgba(255,255,255,0.1));
				color: var(--sg-text-primary, #ffffff);
			}
			.sg-preview-text-content {
				flex: 1;
				overflow: auto;
				padding: 8px;
				color: var(--sg-text-primary, #ffffff);
				white-space: pre-wrap;
				word-break: break-word;
				line-height: 1.4;
				font-size: 11px;
			}
			.sg-preview-text-content::-webkit-scrollbar {
				width: 6px;
				height: 6px;
			}
			.sg-preview-text-content::-webkit-scrollbar-track {
				background: transparent;
			}
			.sg-preview-text-content::-webkit-scrollbar-thumb {
				background: var(--sg-text-quaternary, rgba(255,255,255,0.15));
				border-radius: 3px;
			}
			.sg-preview-text-content::-webkit-scrollbar-thumb:hover {
				background: var(--sg-text-tertiary, rgba(255,255,255,0.25));
			}
			.sg-preview-text-footer {
				padding: 3px 8px;
				background: var(--sg-bg-tertiary, rgba(0,0,0,0.2));
				border-top: 1px solid var(--sg-border-color, #1a1a1a);
				font-size: 10px;
				color: var(--sg-text-tertiary, #707070);
				font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
			}
			.sg-preview-text-resize {
				display: none;
			}
		`;
		document.head.appendChild(style);
	}

	// === PREVIEW TEXT OVERLAY MANAGEMENT ===

	_createPreviewTextOverlay(node) {
		const previewData = this._getPreviewData(node);
		if (!previewData) return null;

		// Format the data based on type
		let text;
		const value = previewData.value;
		if (value === null || value === undefined) {
			text = String(value);
		} else if (typeof value === 'object') {
			text = JSON.stringify(value, null, 2);
		} else {
			text = String(value);
		}
		const title = node.displayTitle || node.title || 'Preview';

		const overlay = document.createElement('div');
		overlay.className = 'sg-preview-text-overlay';
		overlay.id = `sg-preview-overlay-${node.id}`;
		overlay.innerHTML = `
			<div class="sg-preview-text-header">
				<span class="sg-preview-text-title">${this._escapeHtml(title)}</span>
				<div class="sg-preview-text-actions">
					<button class="sg-preview-text-btn sg-preview-copy-btn" title="Copy to clipboard">📋</button>
					<button class="sg-preview-text-btn sg-preview-close-btn" title="Collapse">▲</button>
				</div>
			</div>
			<div class="sg-preview-text-content">${this._escapeHtml(text)}</div>
			<div class="sg-preview-text-footer">${text.length} chars, ${text.split('\n').length} lines</div>
		`;

		const container = this.canvas?.parentElement || document.body;
		container.appendChild(overlay);

		// Bind events
		const closeBtn = overlay.querySelector('.sg-preview-close-btn');
		const copyBtn = overlay.querySelector('.sg-preview-copy-btn');
		const header = overlay.querySelector('.sg-preview-text-header');

		// Clicking header or close button collapses back
		closeBtn?.addEventListener('click', () => this._closePreviewTextOverlay(node));
		header?.addEventListener('dblclick', () => this._closePreviewTextOverlay(node));

		copyBtn?.addEventListener('click', (e) => {
			e.stopPropagation();
			navigator.clipboard.writeText(text).then(() => {
				copyBtn.textContent = '✓';
				setTimeout(() => { copyBtn.textContent = '📋'; }, 1000);
			});
		});

		// Position overlay fixed over the node content area
		this._updatePreviewTextOverlayPosition(node, overlay);

		// Store reference
		if (!this._previewTextOverlays) this._previewTextOverlays = new Map();
		this._previewTextOverlays.set(node.id, overlay);

		return overlay;
	}

	_updatePreviewTextOverlayPosition(node, overlay) {
		if (!overlay) return;

		const camera = this.camera;
		// Align with the node's content area (below header + slots)
		const bounds = node._previewBounds;
		if (bounds) {
			overlay.style.left = (bounds.x * camera.scale + camera.x) + 'px';
			overlay.style.top = (bounds.y * camera.scale + camera.y) + 'px';
			overlay.style.width = Math.max(120, bounds.w * camera.scale) + 'px';
			overlay.style.height = Math.max(60, bounds.h * camera.scale) + 'px';
		} else {
			// Fallback: cover the node area below header
			const sx = node.pos[0] * camera.scale + camera.x;
			const sy = node.pos[1] * camera.scale + camera.y + 30 * camera.scale;
			const sw = node.size[0] * camera.scale;
			const sh = node.size[1] * camera.scale - 30 * camera.scale;
			overlay.style.left = sx + 'px';
			overlay.style.top = sy + 'px';
			overlay.style.width = Math.max(120, sw) + 'px';
			overlay.style.height = Math.max(60, sh) + 'px';
		}
	}

	_closePreviewTextOverlay(node) {
		const overlay = this._previewTextOverlays?.get(node.id);
		if (overlay) {
			overlay.remove();
			this._previewTextOverlays.delete(node.id);
		}
		// Collapse the node
		if (node.extra) node.extra.previewExpanded = false;
		this._recalculatePreviewNodeSize(node);
		this.draw();
	}

	_updatePreviewTextOverlayContent(node) {
		const overlay = this._previewTextOverlays?.get(node.id);
		if (!overlay) return;

		const previewData = this._getPreviewData(node);
		const value = previewData?.value;
		let text;
		if (value === null || value === undefined) {
			text = String(value);
		} else if (typeof value === 'object') {
			text = JSON.stringify(value, null, 2);
		} else {
			text = String(value);
		}

		const content = overlay.querySelector('.sg-preview-text-content');
		const footer = overlay.querySelector('.sg-preview-text-footer');

		if (content) content.textContent = text;
		if (footer) footer.textContent = `${text.length} chars, ${text.split('\n').length} lines`;
	}

	updateAllPreviewTextOverlayPositions() {
		if (!this._previewTextOverlays) return;
		for (const [nodeId, overlay] of this._previewTextOverlays) {
			const node = this.graph.getNodeById(nodeId);
			if (node) {
				this._updatePreviewTextOverlayPosition(node, overlay);
			}
		}
	}

	closeAllPreviewTextOverlays() {
		if (!this._previewTextOverlays) return;
		for (const [nodeId, overlay] of this._previewTextOverlays) {
			// Clean up event listeners
			overlay._cleanupDrag?.();
			overlay._cleanupResize?.();
			overlay.remove();
			// Also reset the node's expanded state
			const node = this.graph.getNodeById(nodeId);
			if (node?.extra) {
				node.extra.previewExpanded = false;
			}
		}
		this._previewTextOverlays.clear();
	}

	_escapeHtml(text) {
		const div = document.createElement('div');
		div.textContent = text;
		return div.innerHTML;
	}

	// === EVENT SETUP ===
	setupEventListeners() {
		this.eventBus.on('mouse:down', (data) => this.handleMouseDown(data));
		this.eventBus.on('mouse:move', (data) => this.handleMouseMove(data));
		this.eventBus.on('mouse:up', (data) => this.handleMouseUp(data));
		this.eventBus.on('mouse:dblclick', (data) => this.handleDoubleClick(data));
		this.eventBus.on('mouse:wheel', (data) => this.handleWheel(data));
		this.eventBus.on('mouse:contextmenu', (data) => this.handleContextMenu(data));
		this.eventBus.on('keyboard:down', (data) => this.handleKeyDown(data));
		this.eventBus.on('keyboard:up', (data) => this.handleKeyUp(data));

		this.eventBus.on('ui:update', (data) => {
			const element = document.getElementById('sg-' + data.id);
			if (element && data.content !== undefined) {
				element.textContent = data.content;
			}
		});

		this.eventBus.on('node:created', (data) => {
			this.ui?.update?.schemaList?.(); this.ui?.update?.nodeTypesList?.();
			if (!this._creatingPairedNode && data?.nodeId) {
				// Defer so the caller has time to set node.pos before we position the partner
				setTimeout(() => this._maybeCreatePairedNode(data.nodeId), 0);
			}
			this.draw();
		});
		this.eventBus.on('node:deleted', () => { this.ui?.update?.schemaList?.(); this.draw(); });
		this.eventBus.on('link:created', () => this.draw());
		this.eventBus.on('link:deleted', () => this.draw());
		this.eventBus.on('schema:registered', () => { this.ui?.update?.schemaList?.(); this.ui?.update?.nodeTypesList?.(); this.draw(); });
		this.eventBus.on('schema:removed', () => { this.ui?.update?.schemaList?.(); this.ui?.update?.nodeTypesList?.(); this.draw(); });

		const nodeInput = document.getElementById('sg-nodeInput');
		nodeInput?.addEventListener('blur', () => this.handleInputBlur());
		nodeInput?.addEventListener('keydown', (e) => this.handleInputKeyDown(e));

		const nodeSelect = document.getElementById('sg-nodeSelect');
		nodeSelect?.addEventListener('change', () => this.handleSelectChange());
		nodeSelect?.addEventListener('blur', () => this.handleSelectBlur());
		nodeSelect?.addEventListener('keydown', (e) => this.handleSelectKeyDown(e));

		const comboInput = document.getElementById('sg-comboBoxInput');
		comboInput?.addEventListener('blur', () => {
			// Delay to allow dropdown option mousedown to fire before blur hides everything
			setTimeout(() => {
				if (this.editingNode && document.getElementById('sg-comboBoxWrapper')?.classList.contains('show')) {
					this._applyComboBoxValue(comboInput.value);
					this._hideComboBox();
				}
			}, 150);
		});
		comboInput?.addEventListener('keydown', (e) => {
			if (e.key === 'Enter') {
				this._applyComboBoxValue(comboInput.value);
				this._hideComboBox();
			} else if (e.key === 'Escape') {
				this._hideComboBox();
			}
		});

		document.getElementById('sg-codeEditorSave')?.addEventListener('click', () => this._saveCodeEditor());
		document.getElementById('sg-codeEditorCancel')?.addEventListener('click', () => this._closeCodeEditor());
		document.getElementById('sg-codeEditorModal')?.addEventListener('keydown', (e) => {
			if (e.key === 'Escape') this._closeCodeEditor();
		});

		this._setupFileDrop();
		this._setupCompletenessListeners();

		this.extensions.initAll(this);
	}

	setupCanvasLeaveHandler() {
		this.canvas.addEventListener('mouseleave', () => {
			if (this.selectionRect) {
				this.selectionRect = null;
				this.selectionStart = null;
				this.isMouseDown = false;
				this.previewSelection.clear();
				this.draw();
			}
		});
	}

	setupVoiceCommands() {
		this.eventBus.on('voice:result', (data) => {
			const transcript = data.transcript.toLowerCase().trim();
			if (transcript.includes('create') && transcript.includes('string')) this.executeVoiceCommand('create', 'Native.String');
			else if (transcript.includes('delete') && this.selectedNode) this.executeVoiceCommand('delete');
			else if (transcript.includes('center')) this.executeVoiceCommand('center-view');
			else if (transcript.includes('theme')) this.executeVoiceCommand('cycle-theme');
		});
	}

	executeVoiceCommand(command, param = null) {
		switch (command) {
			case 'create':
				if (param && this.graph.nodeTypes[param]) {
					const node = this.graph.createNode(param);
					const centerX = (-this.camera.x + this.canvas.width / 2) / this.camera.scale;
					const centerY = (-this.camera.y + this.canvas.height / 2) / this.camera.scale;
					node.pos = [centerX - 90, centerY - 40];
					this.draw();
				}
				break;
			case 'delete': if (this.selectedNode) this.removeNode(this.selectedNode); break;
			case 'center-view': this.centerView(); break;
			case 'cycle-theme': this.cycleTheme(); break;
		}
	}

	// === THEME & SETTINGS ===
	loadTheme() {
		const saved = localStorage.getItem('schemagraph-theme') || 'dark';
		this.currentThemeIndex = this.themes.indexOf(saved);
		if (this.currentThemeIndex === -1) this.currentThemeIndex = 0;
		this.applyTheme(this.themes[this.currentThemeIndex]);
	}

	applyTheme(theme) {
		if (theme === 'dark') document.documentElement.removeAttribute('data-theme');
		else document.documentElement.setAttribute('data-theme', theme);
	}

	cycleTheme() {
		this.currentThemeIndex = (this.currentThemeIndex + 1) % this.themes.length;
		const newTheme = this.themes[this.currentThemeIndex];
		this.applyTheme(newTheme);
		localStorage.setItem('schemagraph-theme', newTheme);
		this.draw();
	}

	loadTextScalingMode() {
		const saved = localStorage.getItem('schemagraph-text-scaling');
		if (saved === 'scaled' || saved === 'fixed') this.textScalingMode = saved;
	}

	saveTextScalingMode() { localStorage.setItem('schemagraph-text-scaling', this.textScalingMode); }
	getTextScale() { return this.textScalingMode === 'fixed' ? (1 / this.camera.scale) : 1; }

	loadFeatures() {
		try {
			const saved = localStorage.getItem('schemagraph-features');
			if (saved) {
				const parsed = JSON.parse(saved);
				// Only apply valid feature keys that exist in _features
				for (const key of Object.keys(this._features)) {
					if (key in parsed && typeof parsed[key] === 'boolean') {
						this._features[key] = parsed[key];
					}
				}
			}
		} catch (e) {
			console.warn('[SchemaGraph] Failed to load features from localStorage:', e);
		}
	}

	saveFeatures() {
		try {
			localStorage.setItem('schemagraph-features', JSON.stringify(this._features));
		} catch (e) {
			console.warn('[SchemaGraph] Failed to save features to localStorage:', e);
		}
	}

	registerNativeNodes() {
		const nativeNodes = [
			{ name: 'String', type: 'str', defaultValue: '', parser: (v) => v },
			{ name: 'Integer', type: 'int', defaultValue: 0, parser: (v) => parseInt(v) || 0 },
			{ name: 'Boolean', type: 'bool', defaultValue: false, parser: (v) => v === true || v === 'true' },
			{ name: 'Float', type: 'float', defaultValue: 0.0, parser: (v) => parseFloat(v) || 0.0 },
			{ name: 'List', type: 'List[Any]', defaultValue: '[]', parser: (v) => { try { return JSON.parse(v); } catch { return []; } } },
			{ name: 'Dict', type: 'Dict[str,Any]', defaultValue: '{}', parser: (v) => { try { return JSON.parse(v); } catch { return {}; } } }
		];

		for (const spec of nativeNodes) {
			const self = this;
			class NativeNode extends Node {
				constructor() {
					super(spec.name);
					this.addOutput('value', spec.type);
					this.properties.value = spec.defaultValue;
					this.size = [180, 80];
					this.isNative = true;
				}
				onExecute() { this.setOutputData(0, spec.parser(this.properties.value)); }
			}
			this.graph.nodeTypes['Native.' + spec.name] = NativeNode;
		}
	}

	// === SELECTION ===
	selectNode(node, addToSelection = false) {
		if (!this._features.nodeSelection) return;
		if (addToSelection && !this._features.multiSelection) addToSelection = false;

		const prevSelection = new Set(this.selectedNodes);

		if (!addToSelection) this.selectedNodes.clear();
		if (node) {
			this.selectedNodes.add(node);
			this.selectedNode = node;

			if (!prevSelection.has(node)) {
				this.eventBus.emit(GraphEvents.NODE_SELECTED, { nodeId: node.id, node });
			}
		}

		prevSelection.forEach(n => {
			if (!this.selectedNodes.has(n)) {
				this.eventBus.emit(GraphEvents.NODE_DESELECTED, { nodeId: n.id, node: n });
			}
		});

		this.eventBus.emit(GraphEvents.SELECTION_CHANGED, {
			selectedNodes: Array.from(this.selectedNodes).map(n => n.id)
		});

		this.draw();
	}

	deselectNode(node) {
		this.selectedNodes.delete(node);
		if (this.selectedNode === node) this.selectedNode = this.selectedNodes.size > 0 ? Array.from(this.selectedNodes)[this.selectedNodes.size - 1] : null;
		this.draw();
	}

	toggleNodeSelection(node) { this.selectedNodes.has(node) ? this.deselectNode(node) : this.selectNode(node, true); }
	isNodeSelected(node) { return this.selectedNodes.has(node); }
	deleteSelectedNodes() { for (const node of Array.from(this.selectedNodes)) this.removeNode(node); this.clearSelection(); }

	clearSelection() {
		const hadSelection = this.selectedNodes.size > 0;
		this.selectedNodes.clear();
		this.selectedNode = null;

		if (hadSelection) {
			this.eventBus.emit(GraphEvents.SELECTION_CLEARED, {});
			this.eventBus.emit(GraphEvents.SELECTION_CHANGED, { selectedNodes: [] });
		}

		this.draw();
	}

	// =========================================================================
	// SUB-GRAPH TEMPLATES
	// =========================================================================

	async saveSelectionAsTemplate() {
		if (this.selectedNodes.size < 2) {
			this.showError('Select at least 2 nodes to create a template');
			return;
		}

		const name = await this._showInputDialog('Save as Template', 'Template name:', 'My Template');
		if (!name) return;

		const selectedIds = new Set();
		for (const node of this.selectedNodes) selectedIds.add(node.id);

		// Serialize selected nodes (same pattern as Graph.serialize)
		const nodes = [];
		let minX = Infinity, minY = Infinity;
		for (const node of this.selectedNodes) {
			minX = Math.min(minX, node.pos[0]);
			minY = Math.min(minY, node.pos[1]);
		}

		for (const node of this.selectedNodes) {
			const nodeData = {
				id: node.id,
				type: node.title,
				pos: [node.pos[0] - minX, node.pos[1] - minY],
				size: node.size.slice(),
				properties: JSON.parse(JSON.stringify(node.properties || {})),
				schemaName: node.schemaName,
				modelName: node.modelName,
				isNative: node.isNative || false,
				isRootType: node.isRootType || false,
				isWorkflowNode: node.isWorkflowNode || false
			};
			if (node.nativeInputs) nodeData.nativeInputs = JSON.parse(JSON.stringify(node.nativeInputs));
			if (node.multiInputs) nodeData.multiInputs = JSON.parse(JSON.stringify(node.multiInputs));
			if (node.multiInputSlots) nodeData.multiInputSlots = JSON.parse(JSON.stringify(node.multiInputSlots));
			if (node.multiOutputSlots) nodeData.multiOutputSlots = JSON.parse(JSON.stringify(node.multiOutputSlots));
			if (node.constantFields) nodeData.constantFields = JSON.parse(JSON.stringify(node.constantFields));
			if (node.workflowType) nodeData.workflowType = node.workflowType;
			if (node.workflowIndex !== undefined) nodeData.workflowIndex = node.workflowIndex;
			if (node.color) nodeData.color = node.color;
			nodes.push(nodeData);
		}

		// Collect only links where both endpoints are in the selection
		const links = [];
		for (const linkId in this.graph.links) {
			if (!this.graph.links.hasOwnProperty(linkId)) continue;
			const link = this.graph.links[linkId];
			if (selectedIds.has(link.origin_id) && selectedIds.has(link.target_id)) {
				links.push({
					id: link.id,
					origin_id: link.origin_id,
					origin_slot: link.origin_slot,
					target_id: link.target_id,
					target_slot: link.target_slot,
					type: link.type
				});
			}
		}

		const template = {
			id: 'tpl_' + Math.random().toString(36).substr(2, 9),
			name: name,
			description: '',
			builtIn: false,
			createdAt: new Date().toISOString(),
			nodeCount: nodes.length,
			edgeCount: links.length,
			nodes: nodes,
			links: links
		};

		// Save to backend
		try {
			const url = (this._templateBaseUrl || '') + '/templates/save';
			const resp = await fetch(url, {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ template })
			});
			if (!resp.ok) throw new Error(await resp.text());
			this.eventBus.emit('template:saved', { id: template.id, name: template.name });
			this.refreshTemplateList();
		} catch (e) {
			this.showError('Failed to save template: ' + e.message);
		}
	}

	async instantiateTemplate(templateId, worldX, worldY) {
		// Fetch full template from backend
		let template;
		try {
			const url = (this._templateBaseUrl || '') + '/templates/get/' + templateId;
			const resp = await fetch(url, { method: 'POST' });
			if (!resp.ok) throw new Error(await resp.text());
			const data = await resp.json();
			template = data.template;
		} catch (e) {
			this.showError('Failed to load template: ' + e.message);
			return;
		}

		if (!template || !template.nodes || template.nodes.length === 0) {
			this.showError('Template is empty');
			return;
		}

		// Build ID remap table
		const idRemap = {};
		for (const nodeData of template.nodes) {
			idRemap[nodeData.id] = Math.random().toString(36).substr(2, 9);
		}

		// Instantiate nodes (same pattern as Graph.deserialize)
		const newNodes = [];
		for (const nodeData of template.nodes) {
			const nodeTypeKey = nodeData.isNative
				? 'Native.' + nodeData.type
				: (nodeData.schemaName && nodeData.modelName)
					? nodeData.schemaName + '.' + nodeData.modelName
					: nodeData.type;

			if (!this.graph.nodeTypes[nodeTypeKey]) {
				console.warn('[Templates] Node type not found:', nodeTypeKey);
				continue;
			}

			const node = new (this.graph.nodeTypes[nodeTypeKey])();
			node.id = idRemap[nodeData.id];
			node.pos = [nodeData.pos[0] + worldX, nodeData.pos[1] + worldY];
			node.size = nodeData.size.slice();
			node.properties = JSON.parse(JSON.stringify(nodeData.properties || {}));
			if (nodeData.isRootType !== undefined) node.isRootType = nodeData.isRootType;
			if (nodeData.nativeInputs) node.nativeInputs = JSON.parse(JSON.stringify(nodeData.nativeInputs));
			if (nodeData.multiInputs) node.multiInputs = JSON.parse(JSON.stringify(nodeData.multiInputs));
			if (nodeData.multiInputSlots) node.multiInputSlots = JSON.parse(JSON.stringify(nodeData.multiInputSlots));
			if (nodeData.multiOutputSlots) node.multiOutputSlots = JSON.parse(JSON.stringify(nodeData.multiOutputSlots));
			if (nodeData.constantFields) node.constantFields = JSON.parse(JSON.stringify(nodeData.constantFields));
			if (nodeData.workflowType) node.workflowType = nodeData.workflowType;
			if (nodeData.workflowIndex !== undefined) node.workflowIndex = nodeData.workflowIndex;
			if (nodeData.color) node.color = nodeData.color;

			this.graph.nodes.push(node);
			this.graph._nodes_by_id[node.id] = node;
			node.graph = this.graph;
			newNodes.push(node);
		}

		// Recreate links with remapped IDs
		if (template.links) {
			for (const linkData of template.links) {
				const newOriginId = idRemap[linkData.origin_id];
				const newTargetId = idRemap[linkData.target_id];
				const originNode = this.graph._nodes_by_id[newOriginId];
				const targetNode = this.graph._nodes_by_id[newTargetId];
				if (!originNode || !targetNode) continue;

				const newLinkId = ++this.graph.last_link_id;
				const link = new Link(
					newLinkId,
					newOriginId,
					linkData.origin_slot,
					newTargetId,
					linkData.target_slot,
					linkData.type
				);
				this.graph.links[newLinkId] = link;
				if (originNode.outputs[linkData.origin_slot])
					originNode.outputs[linkData.origin_slot].links.push(newLinkId);
				if (targetNode.multiInputs && targetNode.multiInputs[linkData.target_slot])
					targetNode.multiInputs[linkData.target_slot].links.push(newLinkId);
				else if (targetNode.inputs[linkData.target_slot])
					targetNode.inputs[linkData.target_slot].link = newLinkId;
			}
		}

		// Select newly created nodes
		this.clearSelection();
		for (const node of newNodes) this.selectNode(node, true);
		this.draw();
		this.eventBus.emit('template:instantiated', { templateId, nodeCount: newNodes.length });
	}

	// === MOUSE HANDLERS ===
	handleMouseDown(data) {
		this.isMouseDown = true;
		document.getElementById('sg-contextMenu')?.classList.remove('show');
		this._hideComboBox();

		const [wx, wy] = this.screenToWorld(data.coords.screenX, data.coords.screenY);

		if (data.button === 0 && !this.isLocked) {
			if (this._hoveredAddButton) {
				data.event.preventDefault();
				this._handleMultiSlotAddClick(this._hoveredAddButton);
				return;
			}

			if (this._hoveredRemoveButton) {
				data.event.preventDefault();
				this._handleMultiSlotRemoveClick(this._hoveredRemoveButton);
				return;
			}

			for (const node of this.graph.nodes) {
				const layout = this._getButtonStackLayout(node);
				for (const stack of [layout.top, layout.bottom]) {
					if (!stack) continue;
					for (const { btn, bounds } of stack.buttons) {
						if (wx >= bounds.x && wx <= bounds.x + bounds.w && wy >= bounds.y && wy <= bounds.y + bounds.h) {
							if (btn.enabled && btn.callback) {
								data.event.preventDefault();
								btn.callback(node, data.event, btn);
								return;
							}
						}
					}
				}
			}
		}

		if ((data.button === 1 || (data.button === 0 && this.spacePressed)) && this._features.panning) {
			data.event.preventDefault();
			this.isPanning = true;
			this.panStart = [data.coords.screenX - this.camera.x, data.coords.screenY - this.camera.y];
			this.canvas.style.cursor = 'grabbing';
			return;
		}

		if (data.button !== 0 || this.spacePressed) return;

		if (!this.isLocked && this._features.linkCreation) {
			for (const node of this.graph.nodes) {
				let visIdx = 0;
				for (let j = 0; j < node.outputs.length; j++) {
					if (this._isFieldHidden(node, j, true)) continue;
					const slotY = node.pos[1] + 30 + visIdx * 25;
					if (Math.sqrt(Math.pow(wx - (node.pos[0] + node.size[0]), 2) + Math.pow(wy - slotY, 2)) < 10) {
						this.connecting = { node, slot: j, isOutput: true };
						this.canvas.classList.add('connecting');
						return;
					}
					visIdx++;
				}
			}

			for (const node of this.graph.nodes) {
				let visIdx = 0;
				for (let j = 0; j < node.inputs.length; j++) {
					if (this._isFieldHidden(node, j, false)) continue;
					const slotY = node.pos[1] + 30 + visIdx * 25;
					if (Math.sqrt(Math.pow(wx - node.pos[0], 2) + Math.pow(wy - slotY, 2)) < 10) {
						if (!node.multiInputs?.[j] && node.inputs[j].link && this._features.linkDeletion) this.removeLink(node.inputs[j].link, node, j);
						this.connecting = { node, slot: j, isOutput: false };
						this.canvas.classList.add('connecting');
						return;
					}
					visIdx++;
				}
			}
		}

		// Edge preview: Alt+Click on a link to insert a preview node
		if (!this.isLocked && this._features.edgePreview && this._edgePreviewConfig.enabled && data.event.altKey) {
			const link = this._findLinkAtPosition(wx, wy);
			if (link && this._canInsertPreviewOnLink(link).allowed) {
				data.event.preventDefault();
				data.event.stopPropagation();
				this._hoveredLink = null;
				this.insertPreviewOnLink(link, wx, wy);
				return;
			}
		}

		let clickedNode = null;
		for (let i = this.graph.nodes.length - 1; i >= 0; i--) {
			const node = this.graph.nodes[i];
			if (wx >= node.pos[0] && wx <= node.pos[0] + node.size[0] && wy >= node.pos[1] && wy <= node.pos[1] + node.size[1]) {
				clickedNode = node;
				break;
			}
		}

		if (clickedNode) {
			if (data.event.ctrlKey || data.event.metaKey) this.toggleNodeSelection(clickedNode);
			else {
				if (!this.selectedNodes.has(clickedNode)) this.selectNode(clickedNode, false);
				if (this._features.nodeDragging) {
					this.dragNode = clickedNode;
					this.dragOffset = [wx - clickedNode.pos[0], wy - clickedNode.pos[1]];
					this.canvas.classList.add('dragging');
				}
			}
			return;
		}

		if (!data.event.ctrlKey && !data.event.metaKey) this.clearSelection();
		if (this._features.multiSelection) this.selectionStart = [wx, wy];
	}

	handleMouseMove(data) {
		this.mousePos = [data.coords.screenX, data.coords.screenY];

		if (this.isPanning) {
			this.camera.x = data.coords.screenX - this.panStart[0];
			this.camera.y = data.coords.screenY - this.panStart[1];
			this._hideTooltip();
			this.updateAllPreviewTextOverlayPositions();
			this.draw();
			return;
		}

		if (this.dragNode && !this.connecting) {
			const [wx, wy] = this.screenToWorld(data.coords.screenX, data.coords.screenY);
			const dx = wx - this.dragOffset[0] - this.dragNode.pos[0];
			const dy = wy - this.dragOffset[1] - this.dragNode.pos[1];
			for (const node of this.selectedNodes) {
				node.pos[0] += dx;
				node.pos[1] += dy;
			}
			this._hideTooltip();
			this.updateAllPreviewTextOverlayPositions();
			this.draw();
			return;
		}

		if (this.connecting) {
			this._hideTooltip();
			this.draw();
			return;
		}

		if (this.selectionStart && this.isMouseDown) {
			const [wx, wy] = this.screenToWorld(data.coords.screenX, data.coords.screenY);
			const dx = Math.abs(wx - this.selectionStart[0]);
			const dy = Math.abs(wy - this.selectionStart[1]);
			if (dx > 5 || dy > 5) {
				this.selectionRect = {
					x: Math.min(this.selectionStart[0], wx),
					y: Math.min(this.selectionStart[1], wy),
					w: dx,
					h: dy
				};
				this.previewSelection.clear();
				for (const node of this.graph.nodes) {
					if (!(node.pos[0] > this.selectionRect.x + this.selectionRect.w ||
						node.pos[0] + node.size[0] < this.selectionRect.x ||
						node.pos[1] > this.selectionRect.y + this.selectionRect.h ||
						node.pos[1] + node.size[1] < this.selectionRect.y)) {
						this.previewSelection.add(node);
					}
				}
			}
			this._hideTooltip();
			this.draw();
			return;
		}

		const [wx, wy] = this.screenToWorld(data.coords.screenX, data.coords.screenY);

		let foundAdd = null;
		let foundRemove = null;

		for (const node of this.graph.nodes) {
			if (!node.isWorkflowNode) continue;

			const addButtons = this._getMultiSlotAddButtons(node);
			for (const btn of addButtons) {
				if (this._isPointInButton(wx, wy, btn)) {
					foundAdd = { nodeId: node.id, ...btn };
					break;
				}
			}

			if (!foundAdd) {
				const removeButtons = this._getMultiSlotRemoveButtons(node);
				for (const btn of removeButtons) {
					if (this._isPointInButton(wx, wy, btn)) {
						foundRemove = { nodeId: node.id, ...btn };
						break;
					}
				}
			}

			if (foundAdd || foundRemove) break;
		}

		this._hoveredAddButton = foundAdd;
		this._hoveredRemoveButton = foundRemove;

		if (foundAdd || foundRemove) {
			this.canvas.style.cursor = 'pointer';
			this._hideTooltip();
			this.draw();
			return;
		}

		let foundButton = null;
		for (const node of this.graph.nodes) {
			const layout = this._getButtonStackLayout(node);
			for (const stack of [layout.top, layout.bottom]) {
				if (!stack) continue;
				for (const { btn, bounds } of stack.buttons) {
					if (wx >= bounds.x && wx <= bounds.x + bounds.w && wy >= bounds.y && wy <= bounds.y + bounds.h) {
						if (btn.enabled && btn.visible) {
							foundButton = { nodeId: node.id, buttonId: btn.id };
							break;
						}
					}
				}
				if (foundButton) break;
			}
			if (foundButton) break;
		}

		if (this._hoveredButton?.buttonId !== foundButton?.buttonId || this._hoveredButton?.nodeId !== foundButton?.nodeId) {
			this._hoveredButton = foundButton;
			if (foundButton) {
				this.canvas.style.cursor = 'pointer';
				this._hideTooltip();
				this.draw();
				return;
			}
		}

		let foundSlot = false;
		let foundNodeHeader = null;

		for (const node of this.graph.nodes) {
			const x = node.pos[0];
			const y = node.pos[1];
			const w = node.size[0];

			if (wx >= x && wx <= x + w && wy >= y && wy <= y + 26) {
				foundNodeHeader = node;
			}

			let inVisIdx = 0;
			for (let j = 0; j < node.inputs.length; j++) {
				if (this._isFieldHidden(node, j, false)) continue;
				const slotY = y + 38 + inVisIdx * 25;
				const hasEditBox = !node.multiInputs?.[j] && !node.inputs[j].link && node.nativeInputs?.[j] !== undefined;
				const hitLeft = x - 10;
				const hitRight = x + (hasEditBox ? 85 : 100);
				const hitTop = slotY - 10;
				const hitBottom = hasEditBox ? slotY + 20 : slotY + 10;

				if (wx >= hitLeft && wx <= hitRight && wy >= hitTop && wy <= hitBottom) {
					const meta = node.inputMeta?.[j];
					if (meta) {
						const isRequired = this._isFieldRequired(node, j);
						this._showTooltip(data.coords.clientX, data.coords.clientY, meta, isRequired);
						foundSlot = true;
						break;
					}
				}
				inVisIdx++;
			}

			if (foundSlot) break;

			let outVisIdx = 0;
			for (let j = 0; j < node.outputs.length; j++) {
				if (this._isFieldHidden(node, j, true)) continue;
				const slotY = y + 38 + outVisIdx * 25;
				const hitLeft = x + w - 100;
				const hitRight = x + w + 10;
				const hitTop = slotY - 10;
				const hitBottom = slotY + 10;

				if (wx >= hitLeft && wx <= hitRight && wy >= hitTop && wy <= hitBottom) {
					const meta = node.outputMeta?.[j];
					if (meta) {
						this._showTooltip(data.coords.clientX, data.coords.clientY, meta, false);
						foundSlot = true;
						break;
					}
				}
				outVisIdx++;
			}

			if (foundSlot) break;
		}

		if (!foundSlot) {
			this._hideTooltip();
		}

		if (foundNodeHeader && !foundSlot) {
			this._showNodeHeaderTooltip(data.coords.clientX, data.coords.clientY, foundNodeHeader);
		} else {
			this._hideNodeHeaderTooltip();
		}

		// Edge preview: check for link hover (Alt key shows hint)
		if (this._features.edgePreview && this._edgePreviewConfig.enabled && !this.connecting && !this.dragNode) {
			const link = this._findLinkAtPosition(wx, wy);
			if (link && this._canInsertPreviewOnLink(link).allowed) {
				this._hoveredLink = link;
				this.canvas.style.cursor = 'pointer';
				this.draw();
				return;
			} else {
				this._hoveredLink = null;
			}
		}

		this.canvas.style.cursor = 'default';
		this.draw();
	}

	handleMouseUp(data) {
		this.isMouseDown = false;
		const [wx, wy] = this.screenToWorld(data.coords.screenX, data.coords.screenY);

		if (this.isPanning) {
			this.isPanning = false;
			this.canvas.style.cursor = this.spacePressed ? 'grab' : 'default';
			return;
		}

		if (this.connecting) {
			for (const node of this.graph.nodes) {
				if (this.connecting.isOutput) {
					let visIdx = 0;
					for (let j = 0; j < node.inputs.length; j++) {
						if (this._isFieldHidden(node, j, false)) continue;
						const slotY = node.pos[1] + 30 + visIdx * 25;
						if (Math.sqrt(Math.pow(wx - node.pos[0], 2) + Math.pow(wy - slotY, 2)) < 15 && node !== this.connecting.node) {
							if (!this.isSlotCompatible(node, j, false)) { this.showError('Type mismatch'); break; }
							if (node.multiInputs?.[j]) {
								const linkId = ++this.graph.last_link_id;
								const link = new Link(linkId, this.connecting.node.id, this.connecting.slot, node.id, j, this.connecting.node.outputs[this.connecting.slot].type);
								this.graph.links[linkId] = link;
								this.connecting.node.outputs[this.connecting.slot].links.push(linkId);
								node.multiInputs[j].links.push(linkId);
								this.eventBus.emit('link:created', { linkId });
							} else {
								if (node.inputs[j].link) this.removeLink(node.inputs[j].link, node, j);
								const link = this.graph.connect(this.connecting.node, this.connecting.slot, node, j);
								if (link) this.eventBus.emit('link:created', { linkId: link.id });
							}
							break;
						}
						visIdx++;
					}
				} else {
					let visIdx = 0;
					for (let j = 0; j < node.outputs.length; j++) {
						if (this._isFieldHidden(node, j, true)) continue;
						const slotY = node.pos[1] + 30 + visIdx * 25;
						if (Math.sqrt(Math.pow(wx - (node.pos[0] + node.size[0]), 2) + Math.pow(wy - slotY, 2)) < 15 && node !== this.connecting.node) {
							if (!this.isSlotCompatible(node, j, true)) { this.showError('Type mismatch'); break; }
							if (this.connecting.node.multiInputs?.[this.connecting.slot]) {
								const linkId = ++this.graph.last_link_id;
								const link = new Link(linkId, node.id, j, this.connecting.node.id, this.connecting.slot, node.outputs[j].type);
								this.graph.links[linkId] = link;
								node.outputs[j].links.push(linkId);
								this.connecting.node.multiInputs[this.connecting.slot].links.push(linkId);
								this.eventBus.emit('link:created', { linkId });
							} else {
								if (this.connecting.node.inputs[this.connecting.slot].link) this.removeLink(this.connecting.node.inputs[this.connecting.slot].link, this.connecting.node, this.connecting.slot);
								const link = this.graph.connect(node, j, this.connecting.node, this.connecting.slot);
								if (link) this.eventBus.emit('link:created', { linkId: link.id });
							}
							break;
						}
						visIdx++;
					}
				}
			}
			this.connecting = null;
			this.canvas.classList.remove('connecting');
			this.draw();
			return;
		}

		if (this.selectionStart && this.selectionRect) {
			if (!data.event.ctrlKey && !data.event.metaKey) this.clearSelection();
			for (const node of this.graph.nodes) {
				if (!(node.pos[0] > this.selectionRect.x + this.selectionRect.w || node.pos[0] + node.size[0] < this.selectionRect.x || node.pos[1] > this.selectionRect.y + this.selectionRect.h || node.pos[1] + node.size[1] < this.selectionRect.y)) {
					this.selectNode(node, true);
				}
			}
		}

		this.selectionStart = null;
		this.selectionRect = null;
		this.previewSelection.clear();
		this.dragNode = null;
		this.canvas.classList.remove('dragging');
		this.draw();
	}

	handleDoubleClick(data) {
		const [wx, wy] = this.screenToWorld(data.coords.screenX, data.coords.screenY);

		// Check for PreviewFlow node double-click on preview area (allowed even when locked)
		for (const node of this.graph.nodes) {
			if (!this._isPreviewFlowNode(node)) continue;

			const bounds = node._previewBounds;
			if (bounds && wx >= bounds.x && wx <= bounds.x + bounds.w &&
				wy >= bounds.y && wy <= bounds.y + bounds.h) {
				// Toggle preview mode
				if (!node.extra) node.extra = {};
				const wasExpanded = node.extra.previewExpanded;
				node.extra.previewExpanded = !wasExpanded;

				if (!node.extra.previewExpanded) {
					// Collapsing — close overlay first
					this._closePreviewTextOverlay(node);
				}

				// Resize node and redraw so _previewBounds is recalculated
				this._recalculatePreviewNodeSize(node);
				this.draw();

				if (node.extra.previewExpanded) {
					// Expanding — create overlay after draw so _previewBounds is fresh
					const previewData = this._getPreviewData(node);
					const textTypes = ['text', 'json', 'list', 'dict', 'integer', 'float', 'boolean'];
					if (previewData && textTypes.includes(previewData.type)) {
						this._createPreviewTextOverlay(node);
					}
				}

				this.eventBus.emit('preview:modeToggled', {
					nodeId: node.id,
					expanded: node.extra.previewExpanded
				});
				return;
			}
		}

		// Block other double-click actions when locked
		if (this.isLocked) return;

		for (const node of this.graph.nodes) {
			if (node.nativeInputs) {
				let visIdx = 0;
				for (let j = 0; j < node.inputs.length; j++) {
					if (this._isFieldHidden(node, j, false)) continue;
					if (!node.inputs[j].link && node.nativeInputs[j] !== undefined) {
						const slotY = node.pos[1] + 30 + visIdx * 25;
						const boxX = node.pos[0] + 10, boxY = slotY + 6, boxW = 70, boxH = 12;
						if (wx >= boxX && wx <= boxX + boxW && wy >= boxY && wy <= boxY + boxH) {
							if (node.nativeInputs[j].type === 'bool') { node.nativeInputs[j].value = !node.nativeInputs[j].value; this.draw(); return; }
							this.showInputOverlay(node, j, boxX, boxY, data.coords.rect);
							return;
						}
					}
					visIdx++;
				}
			}
		}

		for (const node of this.graph.nodes) {
			if (!node.isNative) continue;
			const valueY = node.pos[1] + node.size[1] - 18;
			if (wx >= node.pos[0] + 8 && wx <= node.pos[0] + node.size[0] - 8 && wy >= valueY && wy <= valueY + 20) {
				if (node.title === 'Boolean') { node.properties.value = !node.properties.value; this.draw(); }
				else this.showInputOverlay(node, null, node.pos[0] + 8, valueY, data.coords.rect);
				return;
			}
		}
	}

	showInputOverlay(node, slot, x, y, rect) {
		const valueScreen = this.worldToScreen(x, y);
		this.editingNode = node;
		this.editingNode.editingSlot = slot;

		const currentValue = slot !== null ? node.nativeInputs[slot].value : node.properties.value;
		const options = slot !== null ? node.nativeInputs[slot].options : null;
		const optionsSource = slot !== null ? node.nativeInputs[slot]?.optionsSource : null;
		const editorType = slot !== null ? node.nativeInputs[slot]?.editor : null;

		// Code editor gets its own modal — no need for positioning
		if (editorType === 'code') {
			this._showCodeEditor(node, slot, currentValue);
			return;
		}

		const leftPos = (valueScreen[0] * rect.width / this.canvas.width + rect.left) + 'px';
		const topPos = (valueScreen[1] * rect.height / this.canvas.height + rect.top) + 'px';
		const width = slot !== null ? '75px' : '160px';

		// Hide all overlays first
		document.getElementById('sg-nodeInput')?.classList.remove('show');
		document.getElementById('sg-nodeSelectWrapper')?.classList.remove('show');
		document.getElementById('sg-nodeSelect')?.classList.remove('show');
		document.getElementById('sg-comboBoxWrapper')?.classList.remove('show');
		document.getElementById('sg-comboBoxDropdown')?.classList.remove('show');

		if (optionsSource) {
			// Dynamic combo-box mode
			this._showComboBox(leftPos, topPos, width, currentValue, options, optionsSource);
		} else if (options && Array.isArray(options) && options.length > 0) {
			// Static Literal select mode
			const nodeSelectWrapper = document.getElementById('sg-nodeSelectWrapper');
			const nodeSelect = document.getElementById('sg-nodeSelect');

			nodeSelect.innerHTML = options.map(opt => {
				const selected = String(opt) === String(currentValue) ? ' selected' : '';
				const displayValue = opt === null ? 'null' : String(opt);
				return `<option value="${opt}"${selected}>${displayValue}</option>`;
			}).join('');

			nodeSelectWrapper.style.left = leftPos;
			nodeSelectWrapper.style.top = topPos;
			nodeSelect.style.width = width;
			nodeSelectWrapper.classList.add('show');
			nodeSelect.classList.add('show');
			nodeSelect.focus();
		} else {
			// Plain text input mode
			const nodeInput = document.getElementById('sg-nodeInput');

			nodeInput.value = String(currentValue);
			nodeInput.style.left = leftPos;
			nodeInput.style.top = topPos;
			nodeInput.style.width = width;
			nodeInput.classList.add('show');
			nodeInput.focus();
			nodeInput.select();
		}
	}

	// === COMBO-BOX ===

	_showComboBox(leftPos, topPos, width, currentValue, staticOptions, optionsSource) {
		const wrapper = document.getElementById('sg-comboBoxWrapper');
		const input = document.getElementById('sg-comboBoxInput');
		const dropdown = document.getElementById('sg-comboBoxDropdown');
		const refreshBtn = document.getElementById('sg-comboBoxRefresh');
		const spinner = document.getElementById('sg-comboBoxSpinner');

		// Use a comfortable width for the combo-box (wider than the tiny slot width)
		const comboWidth = Math.max(parseInt(width) || 75, 140) + 'px';
		wrapper.style.left = leftPos;
		wrapper.style.top = topPos;
		input.style.width = comboWidth;
		input.value = String(currentValue ?? '');

		// Check session cache
		const cacheKey = `_comboCache_${optionsSource}`;
		const cached = this[cacheKey];

		if (cached) {
			this._populateComboDropdown(dropdown, cached, input.value);
		} else if (staticOptions && staticOptions.length > 0) {
			this._populateComboDropdown(dropdown, staticOptions, input.value);
			// Also fetch from API to get fresh options
			this._fetchComboOptions(optionsSource, dropdown, spinner, input.value);
		} else {
			this._fetchComboOptions(optionsSource, dropdown, spinner, input.value);
		}

		refreshBtn.onclick = () => {
			delete this[cacheKey];
			this._fetchComboOptions(optionsSource, dropdown, spinner, input.value);
		};

		input.oninput = () => {
			const allOptions = this[cacheKey] || staticOptions || [];
			this._populateComboDropdown(dropdown, allOptions, input.value);
		};

		wrapper.classList.add('show');
		dropdown.classList.add('show');
		input.focus();
		input.select();
	}

	async _fetchComboOptions(optionsSource, dropdown, spinner, filterValue) {
		spinner.classList.add('show');
		dropdown.innerHTML = '<div class="sg-combo-box-loading">Loading...</div>';
		dropdown.classList.add('show');

		try {
			const baseUrl = this._comboBoxBaseUrl || '';
			const response = await fetch(`${baseUrl}/options/${optionsSource}`, {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: null
			});
			if (!response.ok) throw new Error(`Failed: ${response.statusText}`);
			const data = await response.json();
			const options = data.options || [];

			this[`_comboCache_${optionsSource}`] = options;
			this._populateComboDropdown(dropdown, options, filterValue);
		} catch (e) {
			console.error(`[ComboBox] Failed to fetch options for ${optionsSource}:`, e);
			dropdown.innerHTML = '<div class="sg-combo-box-error">Failed to load options</div>';
		} finally {
			spinner.classList.remove('show');
		}
	}

	_populateComboDropdown(dropdown, options, filterValue) {
		const filter = (filterValue || '').toLowerCase();
		const filtered = filter
			? options.filter(opt => String(opt).toLowerCase().includes(filter))
			: options;

		if (filtered.length === 0) {
			dropdown.innerHTML = '<div class="sg-combo-box-empty">No matching options</div>';
			dropdown.classList.add('show');
			return;
		}

		dropdown.innerHTML = filtered.map(opt => {
			const displayValue = opt === null ? 'null' : String(opt);
			return `<div class="sg-combo-box-option" data-value="${opt}">${displayValue}</div>`;
		}).join('');

		dropdown.querySelectorAll('.sg-combo-box-option').forEach(el => {
			el.addEventListener('mousedown', (e) => {
				e.preventDefault();
				const input = document.getElementById('sg-comboBoxInput');
				input.value = el.dataset.value;
				this._applyComboBoxValue(el.dataset.value);
				this._hideComboBox();
			});
		});

		dropdown.classList.add('show');
	}

	_applyComboBoxValue(val) {
		if (!this.editingNode) return;
		let fieldName = null;

		if (this.editingNode.editingSlot !== null && this.editingNode.editingSlot !== undefined) {
			const slot = this.editingNode.editingSlot;
			fieldName = this.editingNode.inputs?.[slot]?.name;
			const inputInfo = this.editingNode.nativeInputs[slot];
			const inputType = inputInfo.type;
			if (inputType === 'int') inputInfo.value = parseInt(val) || 0;
			else if (inputType === 'float') inputInfo.value = parseFloat(val) || 0.0;
			else inputInfo.value = val;
		} else {
			fieldName = 'value';
			this.editingNode.properties.value = val;
		}

		const changedNode = this.editingNode;
		this.eventBus.emit(GraphEvents.FIELD_CHANGED, { nodeId: changedNode.id, fieldName, value: val });
		this.draw();
	}

	_hideComboBox() {
		const wrapper = document.getElementById('sg-comboBoxWrapper');
		const dropdown = document.getElementById('sg-comboBoxDropdown');
		const wasVisible = wrapper?.classList.contains('show');
		wrapper?.classList.remove('show');
		dropdown?.classList.remove('show');
		if (wasVisible && this.editingNode) {
			this.editingNode.editingSlot = null;
			this.editingNode = null;
		}
	}

	// === CODE EDITOR ===

	_showCodeEditor(node, slot, value) {
		const modal = document.getElementById('sg-codeEditorModal');
		const body = document.getElementById('sg-codeEditorBody');
		const langSelect = document.getElementById('sg-codeEditorLang');
		const status = document.getElementById('sg-codeEditorStatus');

		this._codeEditorNode = node;
		this._codeEditorSlot = slot;

		// Detect language from sibling 'lang' field
		const lang = this._getNodeLangValue(node);
		langSelect.value = lang;

		// Clear previous editor
		body.innerHTML = '';

		// Create CodeMirror instance
		if (window.CodeEditor) {
			const CE = window.CodeEditor;
			const langExtension = lang === 'jinja2' ? CE.javascript() : CE.python();

			const saveKeymap = CE.keymap.of([{
				key: 'Mod-s',
				run: () => { this._saveCodeEditor(); return true; }
			}]);

			this._codeEditorView = new CE.EditorView({
				state: CE.EditorState.create({
					doc: String(value ?? ''),
					extensions: [
						CE.basicSetup,
						langExtension,
						CE.oneDark,
						CE.keymap.of([CE.indentWithTab]),
						saveKeymap,
						CE.EditorView.updateListener.of((update) => {
							if (update.docChanged) {
								const lines = update.state.doc.lines;
								const pos = update.state.selection.main.head;
								const line = update.state.doc.lineAt(pos);
								status.textContent = `Ln ${line.number}, Col ${pos - line.from + 1} | ${lines} lines`;
							}
						})
					]
				}),
				parent: body
			});

			// Initial status
			const lines = this._codeEditorView.state.doc.lines;
			status.textContent = `Ln 1, Col 1 | ${lines} lines`;
		} else {
			// Fallback: plain textarea
			const textarea = document.createElement('textarea');
			textarea.id = 'sg-codeEditorFallback';
			textarea.className = 'sg-code-editor-fallback';
			textarea.value = String(value ?? '');
			textarea.addEventListener('keydown', (e) => {
				if (e.key === 'Tab') {
					e.preventDefault();
					const start = textarea.selectionStart;
					textarea.value = textarea.value.substring(0, start) + '\t' + textarea.value.substring(textarea.selectionEnd);
					textarea.selectionStart = textarea.selectionEnd = start + 1;
				}
			});
			body.appendChild(textarea);
			textarea.focus();
			status.textContent = 'CodeMirror not loaded - using fallback editor';
		}

		// Language change handler
		langSelect.onchange = () => {
			if (this._codeEditorView && window.CodeEditor) {
				const doc = this._codeEditorView.state.doc.toString();
				this._codeEditorView.destroy();
				body.innerHTML = '';
				const currentValue = doc;
				// Recreate with new language
				const savedSlot = this._codeEditorSlot;
				const savedNode = this._codeEditorNode;
				this._showCodeEditor(savedNode, savedSlot, currentValue);
			}
		};

		modal.classList.add('show');
		if (this._codeEditorView) this._codeEditorView.focus();
	}

	_getNodeLangValue(node) {
		for (let i = 0; i < node.inputs.length; i++) {
			if (node.inputs[i]?.name === 'lang' && node.nativeInputs[i]) {
				return node.nativeInputs[i].value || 'python';
			}
		}
		return 'python';
	}

	_saveCodeEditor() {
		const node = this._codeEditorNode;
		const slot = this._codeEditorSlot;
		if (!node || slot === null || slot === undefined) { this._closeCodeEditor(); return; }

		let val;
		if (this._codeEditorView) {
			val = this._codeEditorView.state.doc.toString();
		} else {
			const fallback = document.getElementById('sg-codeEditorFallback');
			val = fallback ? fallback.value : '';
		}

		// Also update the lang field if changed
		const langSelect = document.getElementById('sg-codeEditorLang');
		if (langSelect) {
			const newLang = langSelect.value;
			for (let i = 0; i < node.inputs.length; i++) {
				if (node.inputs[i]?.name === 'lang' && node.nativeInputs[i]) {
					if (node.nativeInputs[i].value !== newLang) {
						node.nativeInputs[i].value = newLang;
						const fieldName = node.inputs[i].name;
						this.eventBus.emit(GraphEvents.FIELD_CHANGED, { nodeId: node.id, fieldName, value: newLang });
					}
					break;
				}
			}
		}

		node.nativeInputs[slot].value = val;
		const fieldName = node.inputs?.[slot]?.name;
		this.eventBus.emit(GraphEvents.FIELD_CHANGED, { nodeId: node.id, fieldName, value: val });
		this.draw();
		this._closeCodeEditor();
	}

	_closeCodeEditor() {
		const modal = document.getElementById('sg-codeEditorModal');
		modal?.classList.remove('show');
		if (this._codeEditorView) {
			this._codeEditorView.destroy();
			this._codeEditorView = null;
		}
		this._codeEditorNode = null;
		this._codeEditorSlot = null;
	}

	handleWheel(data) {
		if (!this._features.zooming) return;
		const before = this.screenToWorld(data.coords.screenX, data.coords.screenY);
		this.camera.scale *= data.delta > 0 ? 0.9 : 1.1;
		this.camera.scale = Math.max(0.1, Math.min(5, this.camera.scale));
		const after = this.screenToWorld(data.coords.screenX, data.coords.screenY);
		this.camera.x += (after[0] - before[0]) * this.camera.scale;
		this.camera.y += (after[1] - before[1]) * this.camera.scale;
		this.eventBus.emit('ui:update', { id: 'zoomLevel', content: Math.round(this.camera.scale * 100) + '%' });
		this.updateAllPreviewTextOverlayPositions();
		this.draw();
	}

	handleContextMenu(data) {
		if (this.isLocked || !this._features.contextMenu) { data.event.preventDefault(); return; }
		const [wx, wy] = this.screenToWorld(data.coords.screenX, data.coords.screenY);
		let clickedNode = null;
		for (let i = this.graph.nodes.length - 1; i >= 0; i--) {
			const node = this.graph.nodes[i];
			if (wx >= node.pos[0] && wx <= node.pos[0] + node.size[0] && wy >= node.pos[1] && wy <= node.pos[1] + node.size[1]) {
				clickedNode = node;
				break;
			}
		}
		if (this.customContextMenuHandler) {
			const handled = this.customContextMenuHandler(clickedNode, wx, wy, data.coords);
			if (handled) return;
		}
		this.showContextMenu(clickedNode, wx, wy, data.coords);
	}

	showContextMenu(node, wx, wy, coords) {
		const contextMenu = document.getElementById('sg-contextMenu');
		let html = '';

		if (node) {
			html += '<div class="sg-context-menu-category">Node Actions</div>';
			html += this.selectedNodes.size > 1
				? `<div class="sg-context-menu-item sg-context-menu-delete" data-action="delete-all">❌ Delete ${this.selectedNodes.size} Nodes</div>`
				: '<div class="sg-context-menu-item sg-context-menu-delete" data-action="delete">❌ Delete Node</div>';
			if (this.selectedNodes.size >= 2) {
				html += '<div class="sg-context-menu-item sg-context-menu-template" data-action="save-template">Save as Template</div>';
			}
		} else {
			// Native types submenu (only if feature is enabled)
			if (this._features.nativeTypes) {
				html += `<div class="sg-submenu-wrap"><div class="sg-submenu-trigger">Native Types</div><div class="sg-submenu-panel sg-submenu-leaf">`;
				for (const type of ['Native.String', 'Native.Integer', 'Native.Boolean', 'Native.Float', 'Native.List', 'Native.Dict']) {
					html += `<div class="sg-context-menu-item" data-type="${type}">${type.split('.')[1]}</div>`;
				}
				html += '</div></div>';
			}

			for (const schemaName of Object.keys(this.graph.schemas)) {
				if (!this.graph.isSchemaEnabled?.(schemaName) && !this.graph.schemas[schemaName]?.enabled) continue;
				const schemaInfo = this.graph.schemas[schemaName];
				const decorators = this._schemaDecorators[schemaName] || {};
				const sections = {};
				const defaultSection = 'General';

				for (const type in this.graph.nodeTypes) {
					if (!type.startsWith(schemaName + '.')) continue;
					const modelName = type.split('.')[1];
					const info = decorators[modelName]?.info;
					if (info?.visible === false) continue;
					const section = info?.section || defaultSection;
					if (!sections[section]) sections[section] = [];
					sections[section].push({ type, modelName, info, isRoot: schemaInfo.rootType === modelName });
				}

				const sectionNames = Object.keys(sections).sort((a, b) => {
					if (a === defaultSection) return -1;
					if (b === defaultSection) return 1;
					return a.localeCompare(b);
				});

				if (sectionNames.length === 0) continue;

				html += `<div class="sg-submenu-wrap"><div class="sg-submenu-trigger">${schemaName}</div>`;

				if (sectionNames.length === 1) {
					html += `<div class="sg-submenu-panel sg-submenu-leaf">`;
					const sectionNodes = sections[sectionNames[0]];
					sectionNodes.sort((a, b) => {
						if (a.isRoot) return -1;
						if (b.isRoot) return 1;
						return (a.info?.title || a.modelName).localeCompare(b.info?.title || b.modelName);
					});

					for (const item of sectionNodes) {
						const icon = item.info?.icon ? `<span class="sg-menu-icon">${item.info.icon}</span>` : '';
						const title = item.info?.title || item.modelName;
						const rootMark = item.isRoot ? '☆ ' : '';
						const rootClass = item.isRoot ? ' sg-menu-root' : '';
						html += `<div class="sg-context-menu-item${rootClass}" data-type="${item.type}">${icon}${rootMark}${title}</div>`;
					}
					html += '</div></div>';
				} else {
					html += `<div class="sg-submenu-panel sg-submenu-branch">`;
					for (const sectionName of sectionNames) {
						const sectionNodes = sections[sectionName];
						if (sectionNodes.length === 0) continue;
						html += `<div class="sg-submenu-wrap"><div class="sg-submenu-trigger">${sectionName}</div><div class="sg-submenu-panel sg-submenu-leaf">`;
						sectionNodes.sort((a, b) => {
							if (a.isRoot) return -1;
							if (b.isRoot) return 1;
							return (a.info?.title || a.modelName).localeCompare(b.info?.title || b.modelName);
						});
						for (const item of sectionNodes) {
							const icon = item.info?.icon ? `<span class="sg-menu-icon">${item.info.icon}</span>` : '';
							const title = item.info?.title || item.modelName;
							const rootMark = item.isRoot ? '☆ ' : '';
							const rootClass = item.isRoot ? ' sg-menu-root' : '';
							html += `<div class="sg-context-menu-item${rootClass}" data-type="${item.type}">${icon}${rootMark}${title}</div>`;
						}
						html += '</div></div>';
					}
					html += '</div></div>';
				}
			}
		}

		contextMenu.innerHTML = html;
		let menuX = coords.clientX;
		let menuY = coords.clientY;
		contextMenu.style.left = '0px';
		contextMenu.style.top = '0px';
		contextMenu.classList.add('show');

		const menuRect = contextMenu.getBoundingClientRect();
		if (menuX + menuRect.width > window.innerWidth) menuX = window.innerWidth - menuRect.width - 5;
		if (menuY + menuRect.height > window.innerHeight) menuY = window.innerHeight - menuRect.height - 5;
		menuX = Math.max(5, menuX);
		menuY = Math.max(5, menuY);

		contextMenu.style.left = menuX + 'px';
		contextMenu.style.top = menuY + 'px';
		contextMenu.dataset.worldX = wx;
		contextMenu.dataset.worldY = wy;

		contextMenu.querySelectorAll('.sg-submenu-wrap').forEach(wrap => {
			const trigger = wrap.querySelector(':scope > .sg-submenu-trigger');
			const panel = wrap.querySelector(':scope > .sg-submenu-panel');
			if (!trigger || !panel) return;
			wrap.addEventListener('mouseenter', () => {
				panel.style.display = 'block';
				const rect = panel.getBoundingClientRect();
				if (rect.right > window.innerWidth) { panel.style.left = 'auto'; panel.style.right = '100%'; }
			});
			wrap.addEventListener('mouseleave', () => { panel.style.display = 'none'; });
		});

		if (node) {
			contextMenu.querySelector('.sg-context-menu-delete')?.addEventListener('click', () => {
				this.selectedNodes.size > 1 ? this.deleteSelectedNodes() : this.removeNode(node);
				contextMenu.classList.remove('show');
			});
			contextMenu.querySelector('[data-action="save-template"]')?.addEventListener('click', () => {
				contextMenu.classList.remove('show');
				this.saveSelectionAsTemplate();
			});
		}

		contextMenu.querySelectorAll('.sg-context-menu-item[data-type]').forEach(item => {
			item.addEventListener('click', (e) => {
				e.stopPropagation();
				const type = item.getAttribute('data-type');

				// Validate Start/End node constraints
				const canCreate = this._canCreateNodeType(type);
				if (!canCreate.allowed) {
					this.showError(canCreate.reason);
					contextMenu.classList.remove('show');
					return;
				}

				const n = this.graph.createNode(type);
				n.pos = [parseFloat(contextMenu.dataset.worldX) - 90, parseFloat(contextMenu.dataset.worldY) - 40];
				contextMenu.classList.remove('show');
				this.draw();
			});
		});
	}

	// === KEYBOARD HANDLERS ===
	handleKeyDown(data) {
		const isTyping = data.event.target.tagName === 'INPUT' || data.event.target.tagName === 'TEXTAREA';
		if (data.code === 'Space' && !this.spacePressed && !this.editingNode && !isTyping) {
			data.event.preventDefault();
			this.spacePressed = true;
			this.canvas.style.cursor = 'grab';
		}
		if ((data.key === 'Delete' || data.key === 'Backspace') && this.selectedNodes.size > 0 && !this.editingNode && !isTyping && !this.isLocked) {
			data.event.preventDefault();
			this.deleteSelectedNodes();
		}
		if ((data.event.ctrlKey || data.event.metaKey) && data.key === 'a' && !this.editingNode && !isTyping) {
			data.event.preventDefault();
			this.clearSelection();
			for (const node of this.graph.nodes) this.selectNode(node, true);
		}
		if (data.key === 'Escape' && !this.editingNode) this.clearSelection();
	}

	handleKeyUp(data) {
		if (data.code === 'Space') {
			this.spacePressed = false;
			this.canvas.style.cursor = this.isPanning ? 'grabbing' : 'default';
		}
	}

	handleInputBlur() {
		if (this.editingNode) {
			const nodeInput = document.getElementById('sg-nodeInput');
			const val = nodeInput.value;
			let fieldName = null;

			if (this.editingNode.editingSlot !== null && this.editingNode.editingSlot !== undefined) {
				const slot = this.editingNode.editingSlot;
				fieldName = this.editingNode.inputs?.[slot]?.name;
				const inputType = this.editingNode.nativeInputs[slot].type;
				if (inputType === 'int') this.editingNode.nativeInputs[slot].value = parseInt(val) || 0;
				else if (inputType === 'float') this.editingNode.nativeInputs[slot].value = parseFloat(val) || 0.0;
				else if (inputType === 'bool') this.editingNode.nativeInputs[slot].value = val === 'true' || val === true;
				else this.editingNode.nativeInputs[slot].value = val;
				this.editingNode.editingSlot = null;
			} else {
				fieldName = 'value';
				if (this.editingNode.title === 'Integer') this.editingNode.properties.value = parseInt(val) || 0;
				else if (this.editingNode.title === 'Float') this.editingNode.properties.value = parseFloat(val) || 0.0;
				else if (this.editingNode.title === 'Boolean') this.editingNode.properties.value = val === 'true' || val === true;
				else this.editingNode.properties.value = val;
			}

			const changedNode = this.editingNode;
			this.eventBus.emit(GraphEvents.FIELD_CHANGED, { nodeId: changedNode.id, fieldName: fieldName, value: val });
		}

		document.getElementById('sg-nodeInput')?.classList.remove('show');
		this.editingNode = null;
	}

	handleInputKeyDown(e) {
		if (e.key === 'Enter') document.getElementById('sg-nodeInput')?.blur();
		else if (e.key === 'Escape') { document.getElementById('sg-nodeInput')?.classList.remove('show'); this.editingNode = null; }
	}

	handleSelectChange() {
		// Apply the selection immediately on change
		if (this.editingNode) {
			const nodeSelect = document.getElementById('sg-nodeSelect');
			const val = nodeSelect.value;
			let fieldName = null;

			if (this.editingNode.editingSlot !== null && this.editingNode.editingSlot !== undefined) {
				const slot = this.editingNode.editingSlot;
				fieldName = this.editingNode.inputs?.[slot]?.name;
				// For literal types, store the value as-is (it's already the correct type from options)
				const inputInfo = this.editingNode.nativeInputs[slot];
				if (inputInfo.options) {
					// Find the original typed value from options
					const typedValue = inputInfo.options.find(opt => String(opt) === val);
					inputInfo.value = typedValue !== undefined ? typedValue : val;
				} else {
					inputInfo.value = val;
				}
			} else {
				fieldName = 'value';
				this.editingNode.properties.value = val;
			}

			const changedNode = this.editingNode;
			this.eventBus.emit(GraphEvents.FIELD_CHANGED, { nodeId: changedNode.id, fieldName: fieldName, value: val });
			this.draw();
		}
	}

	handleSelectBlur() {
		document.getElementById('sg-nodeSelectWrapper')?.classList.remove('show');
		document.getElementById('sg-nodeSelect')?.classList.remove('show');
		if (this.editingNode) {
			this.editingNode.editingSlot = null;
		}
		this.editingNode = null;
	}

	handleSelectKeyDown(e) {
		if (e.key === 'Enter' || e.key === 'Escape') {
			document.getElementById('sg-nodeSelectWrapper')?.classList.remove('show');
			document.getElementById('sg-nodeSelect')?.classList.remove('show');
			if (this.editingNode) this.editingNode.editingSlot = null;
			this.editingNode = null;
		}
	}

	// === HELPER METHODS ===
	removeLink(linkId, targetNode, targetSlot) {
		const link = this.graph.links[linkId];
		if (!link) return;
		// Prevent removal of loop-back edges unless removing paired nodes
		if (link.loop && !this._removingPairedNode) return;
		const originNode = this.graph.getNodeById(link.origin_id);
		if (originNode) {
			const idx = originNode.outputs[link.origin_slot].links.indexOf(linkId);
			if (idx > -1) originNode.outputs[link.origin_slot].links.splice(idx, 1);
		}
		delete this.graph.links[linkId];
		targetNode.inputs[targetSlot].link = null;
		this.eventBus.emit(GraphEvents.LINK_REMOVED, {
			linkId, targetNodeId: targetNode.id, targetSlot,
			sourceNodeId: link.origin_id, sourceSlot: link.origin_slot
		});
	}

	removeNode(node) {
		if (!node) return;

		// If this is an edge preview node, use the restore method instead
		if (node.extra?._isEdgePreview && this._isPreviewFlowNode(node)) {
			this.removePreviewNodeAndRestore(node);
			if (this.selectedNode === node) this.selectedNode = null;
			this.selectedNodes.delete(node);
			return;
		}

		// If this node has a paired node (loop start/end), remove the partner too
		if (!this._removingPairedNode) {
			const partner = this._findPairedNode(node);
			if (partner) {
				this._removingPairedNode = true;
				try {
					this.removeNode(partner);
					this.selectedNodes.delete(partner);
				} finally {
					this._removingPairedNode = false;
				}
			}
		}

		// If preserve preview links is enabled and this is a preview node, reconnect underlying nodes
		if (this._features.preservePreviewLinks && this._isPreviewFlowNode(node)) {
			this._preservePreviewNodeLinks(node);
		}

		for (let j = 0; j < node.inputs.length; j++) {
			if (node.multiInputs?.[j]) {
				for (const linkId of node.multiInputs[j].links.slice()) this.removeLink(linkId, node, j);
			} else if (node.inputs[j].link) {
				this.removeLink(node.inputs[j].link, node, j);
			}
		}
		for (let j = 0; j < node.outputs.length; j++) {
			for (const linkId of node.outputs[j].links.slice()) {
				const link = this.graph.links[linkId];
				if (link) {
					const targetNode = this.graph.getNodeById(link.target_id);
					if (targetNode) {
						if (targetNode.multiInputs?.[link.target_slot]) {
							const idx = targetNode.multiInputs[link.target_slot].links.indexOf(linkId);
							if (idx > -1) targetNode.multiInputs[link.target_slot].links.splice(idx, 1);
						} else {
							// Only clear the link if it's the same link being removed
							// (preservePreviewLinks may have already created a new link to this slot)
							if (targetNode.inputs[link.target_slot].link === linkId) {
								targetNode.inputs[link.target_slot].link = null;
							}
						}
					}
					delete this.graph.links[linkId];
				}
			}
		}
		const idx = this.graph.nodes.indexOf(node);
		if (idx > -1) { this.graph.nodes.splice(idx, 1); delete this.graph._nodes_by_id[node.id]; }
		if (this.selectedNode === node) this.selectedNode = null;
		this.eventBus.emit('node:deleted', { nodeId: node.id });
	}

	isSlotCompatible(node, slotIdx, isOutput) {
		if (!this.connecting || node === this.connecting.node) return false;
		if (this.connecting.isOutput && !isOutput) return this.graph._areTypesCompatible(this.connecting.node.outputs[this.connecting.slot].type, node.inputs[slotIdx].type);
		if (!this.connecting.isOutput && isOutput) return this.graph._areTypesCompatible(node.outputs[slotIdx].type, this.connecting.node.inputs[this.connecting.slot].type);
		return false;
	}

	showError(text) {
		const errorEl = document.getElementById('sg-errorBanner');
		if (errorEl) { errorEl.textContent = '⚠️ ' + text; errorEl.style.display = 'block'; setTimeout(() => errorEl.style.display = 'none', 3000); }
		this.eventBus.emit('error', { message: text });
	}

	_showTooltip(clientX, clientY, meta, isRequired) {
		if (!this._fieldTooltipsEnabled) return;
		if (!this.tooltipEl) {
			this.tooltipEl = document.createElement('div');
			this.tooltipEl.className = 'sg-tooltip';
			document.body.appendChild(this.tooltipEl);
		}
		let html = '';
		if (meta.title) html += `<div class="sg-tooltip-title">${meta.title}</div>`;
		if (meta.description) html += `<div class="sg-tooltip-desc">${meta.description}</div>`;
		html += `<div class="sg-tooltip-field"><code>${meta.name}</code></div>`;
		html += '<div style="display:flex;flex-wrap:wrap;gap:4px;align-items:center;">';
		if (meta.type) html += `<span class="sg-tooltip-type">${meta.type}</span>`;
		if (meta.isMulti) html += `<span class="sg-tooltip-badge multi">Multi-Slot</span>`;
		if (isRequired) html += `<span class="sg-tooltip-badge required">Required</span>`;
		else html += `<span class="sg-tooltip-badge optional">Optional</span>`;
		html += '</div>';
		this.tooltipEl.innerHTML = html;
		let x = clientX + 15, y = clientY + 15;
		if (x + 280 > window.innerWidth) x = clientX - 290;
		if (y + 120 > window.innerHeight) y = clientY - 130;
		this.tooltipEl.style.left = x + 'px';
		this.tooltipEl.style.top = y + 'px';
		this.tooltipEl.style.display = 'block';
	}

	_hideTooltip() { if (this.tooltipEl) this.tooltipEl.style.display = 'none'; }

	_showNodeHeaderTooltip(clientX, clientY, node) {
		if (!this._nodeTooltipsEnabled) return;

		const info = this._schemaDecorators[node.schemaName]?.[node.modelName]?.info || {};

		if (!this._nodeHeaderTooltipEl) {
			this._nodeHeaderTooltipEl = document.createElement('div');
			this._nodeHeaderTooltipEl.className = 'sg-node-tooltip';
			document.body.appendChild(this._nodeHeaderTooltipEl);
		}

		// Always compute fresh
		const selfCompleteness = this._getNodeCompleteness(node);
		const chainCompleteness = this._getChainCompleteness(node);

		let html = '<div class="sg-node-tooltip-header">';
		if (info.icon) {
			html += `<span class="sg-node-tooltip-icon">${info.icon}</span>`;
		}
		const displayTitle = info.title || node.modelName || node.title;
		html += `<span class="sg-node-tooltip-title">${displayTitle}</span>`;
		html += '</div>';

		if (info.description) {
			html += `<div class="sg-node-tooltip-desc">${info.description}</div>`;
		}

		html += '<div class="sg-node-tooltip-meta">';
		if (node.schemaName) {
			html += `<div class="sg-node-tooltip-meta-item"><span class="sg-node-tooltip-meta-label">Schema:</span> ${node.schemaName}</div>`;
		}
		if (node.modelName) {
			html += `<div class="sg-node-tooltip-meta-item"><span class="sg-node-tooltip-meta-label">Model:</span> ${node.modelName}</div>`;
		}
		if (info.section) {
			html += `<div class="sg-node-tooltip-meta-item"><span class="sg-node-tooltip-meta-label">Section:</span> ${info.section}</div>`;
		}
		html += '</div>';

		// Self completeness
		const missingLen = selfCompleteness.missingFields.length;
		if (missingLen > 0) {
			html += '<div class="sg-node-tooltip-chain-missing">';
			html += `⛔ ${missingLen} missing required field${missingLen > 1 ? 's' : ''}`;
			html += `<br><small style="opacity:0.8">${selfCompleteness.missingFields.slice(0, 3).join(', ')}${missingLen > 3 ? '...' : ''}</small>`;
			html += '</div>';
		} else {
			html += `<div class="sg-node-tooltip-meta-item sg-node-tooltip-complete">✓ All required fields filled</div>`;
		}

		// Chain completeness - only show if upstream nodes are incomplete
		const upstreamIncomplete = chainCompleteness.incompleteNodes.filter(id => id !== node.id);
		if (upstreamIncomplete.length > 0) {
			html += '<div class="sg-node-tooltip-chain-warning">';
			html += `⚠ ${upstreamIncomplete.length} upstream node${upstreamIncomplete.length > 1 ? 's' : ''} incomplete`;
			const incompleteNames = upstreamIncomplete.slice(0, 3).map(id => {
				const n = this.graph.getNodeById(id);
				return n ? (n.modelName || n.title) : id;
			});
			html += `<br><small style="opacity:0.8">${incompleteNames.join(', ')}${upstreamIncomplete.length > 3 ? '...' : ''}</small>`;
			html += '</div>';
		} else if (selfCompleteness.complete && chainCompleteness.complete) {
			html += '<div class="sg-node-tooltip-chain-ok">✓ Chain complete - ready</div>';
		}

		if (node.isNative) {
			html += '<div class="sg-node-tooltip-badge-row"><span class="sg-node-tooltip-type-badge native">Native</span></div>';
		}
		if (node.isRootType) {
			html += '<div class="sg-node-tooltip-badge-row"><span class="sg-node-tooltip-type-badge root">★ Root</span></div>';
		}

		this._nodeHeaderTooltipEl.innerHTML = html;

		let x = clientX + 15;
		let y = clientY + 15;
		if (x + 320 > window.innerWidth) x = clientX - 330;
		if (y + 250 > window.innerHeight) y = clientY - 260;

		this._nodeHeaderTooltipEl.style.left = x + 'px';
		this._nodeHeaderTooltipEl.style.top = y + 'px';
		this._nodeHeaderTooltipEl.style.display = 'block';
	}

	_hideNodeHeaderTooltip() { if (this._nodeHeaderTooltipEl) this._nodeHeaderTooltipEl.style.display = 'none'; }

	_showInputDialog(title, label, defaultValue = '') {
		return new Promise((resolve) => {
			const overlay = document.createElement('div');
			overlay.className = 'sg-input-dialog-overlay';
			overlay.innerHTML = `<div class="sg-input-dialog"><div class="sg-input-dialog-header"><span class="sg-input-dialog-title">${title}</span><button class="sg-input-dialog-close">✕</button></div><div class="sg-input-dialog-body"><label class="sg-input-dialog-label">${label}</label><input class="sg-input-dialog-input" type="text" value="${defaultValue}"></div><div class="sg-input-dialog-footer"><button class="sg-input-dialog-btn sg-input-dialog-cancel">Cancel</button><button class="sg-input-dialog-btn sg-input-dialog-confirm">OK</button></div></div>`;
			document.body.appendChild(overlay);
			const input = overlay.querySelector('.sg-input-dialog-input');
			const close = () => { overlay.remove(); };
			overlay.querySelector('.sg-input-dialog-close').onclick = () => { close(); resolve(null); };
			overlay.querySelector('.sg-input-dialog-cancel').onclick = () => { close(); resolve(null); };
			overlay.querySelector('.sg-input-dialog-confirm').onclick = () => { close(); resolve(input.value); };
			input.onkeydown = (e) => { if (e.key === 'Enter') { close(); resolve(input.value); } else if (e.key === 'Escape') { close(); resolve(null); } };
			setTimeout(() => { input.focus(); input.select(); }, 50);
		});
	}

	_showConfirmDialog(title, message, confirmText = 'Confirm', danger = false) {
		return new Promise((resolve) => {
			const overlay = document.createElement('div');
			overlay.className = 'sg-input-dialog-overlay';
			const dangerClass = danger ? ' sg-confirm-danger' : '';
			overlay.innerHTML = `<div class="sg-input-dialog"><div class="sg-input-dialog-header"><span class="sg-input-dialog-title">${title}</span><button class="sg-input-dialog-close">✕</button></div><div class="sg-input-dialog-body"><p class="sg-confirm-dialog-message">${message}</p></div><div class="sg-input-dialog-footer"><button class="sg-input-dialog-btn sg-input-dialog-cancel">Cancel</button><button class="sg-input-dialog-btn sg-input-dialog-confirm${dangerClass}">${confirmText}</button></div></div>`;
			document.body.appendChild(overlay);
			const close = () => { overlay.remove(); };
			overlay.querySelector('.sg-input-dialog-close').onclick = () => { close(); resolve(false); };
			overlay.querySelector('.sg-input-dialog-cancel').onclick = () => { close(); resolve(false); };
			overlay.querySelector('.sg-input-dialog-confirm').onclick = () => { close(); resolve(true); };
		});
	}

	// === MULTI-SLOT UI HELPERS ===
	_getMultiSlotAddButtons(node) {
		const buttons = [];
		if (!node.isWorkflowNode) return buttons;
		const schemaInfo = this.graph.schemas?.[node.schemaName];
		// fieldRoles is keyed by modelName, so we need to get the roles for this specific model
		const fieldRoles = schemaInfo?.fieldRoles?.[node.modelName];
		if (!fieldRoles) return buttons;
		for (const [fieldName, role] of Object.entries(fieldRoles)) {
			if (role === FieldRole.MULTI_INPUT) {
				const indices = node.multiInputSlots?.[fieldName] || [];
				// Find the base slot (the one without a dot in the name - the main multi-field slot)
				let baseSlotIdx = -1;
				for (const idx of indices) {
					const name = node.inputs[idx]?.name || '';
					if (!name.includes('.')) { baseSlotIdx = idx; break; }
				}
				if (baseSlotIdx === -1 && indices.length > 0) baseSlotIdx = indices[0];
				if (baseSlotIdx === -1) continue;
				if (this._isFieldHidden(node, baseSlotIdx, false)) continue;
				const visIdx = this._getVisibleSlotIndex(node, baseSlotIdx, false);
				const slotY = node.pos[1] + 38 + visIdx * 25;
				buttons.push({ fieldName, type: 'input', slotIdx: baseSlotIdx, x: node.pos[0] - 7, y: slotY - 6, w: 12, h: 12 });
			}
			if (role === FieldRole.MULTI_OUTPUT) {
				const indices = node.multiOutputSlots?.[fieldName] || [];
				// Find the base slot (the one without a dot in the name - the main multi-field slot)
				let baseSlotIdx = -1;
				for (const idx of indices) {
					const name = node.outputs[idx]?.name || '';
					if (!name.includes('.')) { baseSlotIdx = idx; break; }
				}
				if (baseSlotIdx === -1 && indices.length > 0) baseSlotIdx = indices[0];
				if (baseSlotIdx === -1) continue;
				if (this._isFieldHidden(node, baseSlotIdx, true)) continue;
				const visIdx = this._getVisibleSlotIndex(node, baseSlotIdx, true);
				const slotY = node.pos[1] + 38 + visIdx * 25;
				buttons.push({ fieldName, type: 'output', slotIdx: baseSlotIdx, x: node.pos[0] + node.size[0] - 5, y: slotY - 6, w: 12, h: 12 });
			}
		}
		return buttons;
	}

	_getMultiSlotRemoveButtons(node) {
		const buttons = [];
		if (!node.isWorkflowNode) return buttons;
		for (const [fieldName, indices] of Object.entries(node.multiInputSlots || {})) {
			for (const idx of indices) {
				if (this._isFieldHidden(node, idx, false)) continue;
				const visIdx = this._getVisibleSlotIndex(node, idx, false);
				const slotY = node.pos[1] + 38 + visIdx * 25;
				const metaName = node.inputMeta?.[idx]?.name || node.inputs[idx]?.name || '';
				const dotIdx = metaName.indexOf('.');
				// Only show remove button for actual sub-fields (name contains a dot like "fieldName.key")
				if (dotIdx === -1) continue;
				const key = metaName.substring(dotIdx + 1);
				const hasConnection = node.multiInputs?.[idx]?.links?.length > 0;
				// Place at beginning of field name (left side, just after the pin)
				buttons.push({ fieldName, type: 'input', slotIdx: idx, key, x: node.pos[0] + 8, y: slotY - 5, w: 10, h: 10, hasConnection });
			}
		}
		for (const [fieldName, indices] of Object.entries(node.multiOutputSlots || {})) {
			for (const idx of indices) {
				if (this._isFieldHidden(node, idx, true)) continue;
				const visIdx = this._getVisibleSlotIndex(node, idx, true);
				const slotY = node.pos[1] + 38 + visIdx * 25;
				const metaName = node.outputMeta?.[idx]?.name || node.outputs[idx]?.name || '';
				const dotIdx = metaName.indexOf('.');
				// Only show remove button for actual sub-fields (name contains a dot like "fieldName.key")
				if (dotIdx === -1) continue;
				const key = metaName.substring(dotIdx + 1);
				const hasConnection = node.outputs[idx]?.links?.length > 0;
				// Place at end of field name (right side, just before the pin)
				buttons.push({ fieldName, type: 'output', slotIdx: idx, key, x: node.pos[0] + node.size[0] - 18, y: slotY - 5, w: 10, h: 10, hasConnection });
			}
		}
		return buttons;
	}

	_isPointInButton(wx, wy, btn) { return wx >= btn.x && wx <= btn.x + btn.w && wy >= btn.y && wy <= btn.y + btn.h; }
	_isMouseNearNode(node) {
		const [wx, wy] = this.screenToWorld(this.mousePos[0], this.mousePos[1]);
		const margin = 30;
		return wx >= node.pos[0] - margin && wx <= node.pos[0] + node.size[0] + margin && wy >= node.pos[1] - margin && wy <= node.pos[1] + node.size[1] + margin;
	}

	async _handleMultiSlotAddClick(btn) {
		const node = this.graph.getNodeById(btn.nodeId);
		if (!node) return;
		const key = await this._showInputDialog('Add Slot', `Enter key for new ${btn.fieldName} slot:`, `key_${Date.now() % 1000}`);
		if (!key) return;
		if (btn.type === 'input') this._addMultiInputSlot(node, btn.fieldName, key);
		else this._addMultiOutputSlot(node, btn.fieldName, key);
	}

	async _handleMultiSlotRemoveClick(btn) {
		const node = this.graph.getNodeById(btn.nodeId);
		if (!node) return;
		if (btn.hasConnection) {
			const confirm = await this._showConfirmDialog('Remove Slot', `Slot "${btn.key}" has connections. Remove anyway?`, 'Remove', true);
			if (!confirm) return;
		}
		if (btn.type === 'input') this._removeMultiInputSlot(node, btn.fieldName, btn.key);
		else this._removeMultiOutputSlot(node, btn.fieldName, btn.key);
	}

	_getMultiInputKeys(node, fieldName) {
		if (!node.multiInputSlots?.[fieldName]) return [];
		return node.multiInputSlots[fieldName].map(idx => {
			const name = node.inputs[idx]?.name || '';
			const dotIdx = name.indexOf('.');
			return dotIdx !== -1 ? name.substring(dotIdx + 1) : name;
		});
	}

	_getMultiOutputKeys(node, fieldName) {
		if (!node.multiOutputSlots?.[fieldName]) return [];
		return node.multiOutputSlots[fieldName].map(idx => {
			const name = node.outputs[idx]?.name || '';
			const dotIdx = name.indexOf('.');
			return dotIdx !== -1 ? name.substring(dotIdx + 1) : name;
		});
	}

	_addMultiInputSlot(node, fieldName, key) {
		if (!node.multiInputSlots) node.multiInputSlots = {};
		if (!node.multiInputSlots[fieldName]) node.multiInputSlots[fieldName] = [];
		const existingKeys = this._getMultiInputKeys(node, fieldName);
		if (existingKeys.includes(key)) return false;
		const schemaInfo = this.graph.schemas?.[node.schemaName];
		const fieldRoles = schemaInfo?.fieldRoles?.[node.modelName] || {};
		const baseType = fieldRoles[fieldName + '_type'] || 'Any';
		const newIdx = node.inputs.length;
		node.inputs.push({ name: `${fieldName}.${key}`, type: baseType, link: null });
		if (!node.multiInputs) node.multiInputs = {};
		node.multiInputs[newIdx] = { links: [] };
		if (!node.inputMeta) node.inputMeta = {};
		node.inputMeta[newIdx] = { name: `${fieldName}.${key}`, type: baseType, title: key, isMulti: true };
		node.multiInputSlots[fieldName].push(newIdx);
		this._recalculateNodeSize(node);
		this.eventBus.emit(GraphEvents.FIELD_CHANGED, { nodeId: node.id, fieldName, action: 'addSlot', key });
		this.draw();
		return true;
	}

	_removeMultiInputSlot(node, fieldName, key) {
		if (!node.multiInputSlots?.[fieldName]) return false;
		for (const idx of node.multiInputSlots[fieldName].slice()) {
			const name = node.inputs[idx]?.name || '';
			const dotIdx = name.indexOf('.');
			const slotKey = dotIdx !== -1 ? name.substring(dotIdx + 1) : name;
			if (slotKey === key) {
				// Capture the slot type before removal for potential base slot restoration
				const slotType = node.inputMeta?.[idx]?.type || node.inputs[idx]?.type || 'Any';

				// Remove any multi-input connections to this slot
				if (node.multiInputs?.[idx]?.links) {
					for (const linkId of node.multiInputs[idx].links.slice()) {
						const link = this.graph.links[linkId];
						if (link) {
							const originNode = this.graph.getNodeById(link.origin_id);
							if (originNode) {
								const lidx = originNode.outputs[link.origin_slot].links.indexOf(linkId);
								if (lidx > -1) originNode.outputs[link.origin_slot].links.splice(lidx, 1);
							}
							delete this.graph.links[linkId];
						}
					}
				}
				// Remove any regular input connection to this slot
				if (node.inputs[idx]?.link) {
					const linkId = node.inputs[idx].link;
					const link = this.graph.links[linkId];
					if (link) {
						const originNode = this.graph.getNodeById(link.origin_id);
						if (originNode) {
							const lidx = originNode.outputs[link.origin_slot].links.indexOf(linkId);
							if (lidx > -1) originNode.outputs[link.origin_slot].links.splice(lidx, 1);
						}
						delete this.graph.links[linkId];
					}
					node.inputs[idx].link = null;
				}

				// Actually remove the input from the node
				node.inputs.splice(idx, 1);

				// Update inputMeta indices
				if (node.inputMeta) {
					const newMeta = {};
					for (const [i, meta] of Object.entries(node.inputMeta)) {
						const iNum = parseInt(i);
						if (iNum < idx) newMeta[iNum] = meta;
						else if (iNum > idx) newMeta[iNum - 1] = meta;
					}
					node.inputMeta = newMeta;
				}

				// Update multiInputs indices
				if (node.multiInputs) {
					const newMultiInputs = {};
					for (const [i, data] of Object.entries(node.multiInputs)) {
						const iNum = parseInt(i);
						if (iNum < idx) newMultiInputs[iNum] = data;
						else if (iNum > idx) newMultiInputs[iNum - 1] = data;
					}
					node.multiInputs = newMultiInputs;
				}

				// Update nativeInputs indices
				if (node.nativeInputs) {
					const newNativeInputs = {};
					for (const [i, data] of Object.entries(node.nativeInputs)) {
						const iNum = parseInt(i);
						if (iNum < idx) newNativeInputs[iNum] = data;
						else if (iNum > idx) newNativeInputs[iNum - 1] = data;
					}
					node.nativeInputs = newNativeInputs;
				}

				// Update multiInputSlots indices for all fields
				for (const [fn, indices] of Object.entries(node.multiInputSlots)) {
					node.multiInputSlots[fn] = indices.filter(i => i !== idx).map(i => i > idx ? i - 1 : i);
				}

				// Update all links targeting this node's inputs
				for (const link of Object.values(this.graph.links)) {
					if (link.target_id === node.id && link.target_slot > idx) {
						link.target_slot--;
					}
				}

				// If all sub-slots were removed, restore a base slot so the "+" button remains
				if (node.multiInputSlots[fieldName].length === 0) {
					const baseIdx = node.inputs.length;
					node.inputs.push({ name: fieldName, type: slotType, link: null });
					if (!node.inputMeta) node.inputMeta = {};
					node.inputMeta[baseIdx] = { name: fieldName, type: slotType, isMulti: true };
					node.multiInputSlots[fieldName] = [baseIdx];
				}

				this._recalculateNodeSize(node);
				this.eventBus.emit(GraphEvents.FIELD_CHANGED, { nodeId: node.id, fieldName, action: 'removeSlot', key });
				this.draw();
				return true;
			}
		}
		return false;
	}

	_addMultiOutputSlot(node, fieldName, key) {
		if (!node.multiOutputSlots) node.multiOutputSlots = {};
		if (!node.multiOutputSlots[fieldName]) node.multiOutputSlots[fieldName] = [];
		const existingKeys = this._getMultiOutputKeys(node, fieldName);
		if (existingKeys.includes(key)) return false;
		const schemaInfo = this.graph.schemas?.[node.schemaName];
		const fieldRoles = schemaInfo?.fieldRoles?.[node.modelName] || {};
		const baseType = fieldRoles[fieldName + '_type'] || 'Any';
		const newIdx = node.outputs.length;
		node.outputs.push({ name: `${fieldName}.${key}`, type: baseType, links: [] });
		if (!node.outputMeta) node.outputMeta = {};
		node.outputMeta[newIdx] = { name: `${fieldName}.${key}`, type: baseType, title: key };
		node.multiOutputSlots[fieldName].push(newIdx);
		this._recalculateNodeSize(node);
		this.eventBus.emit(GraphEvents.FIELD_CHANGED, { nodeId: node.id, fieldName, action: 'addSlot', key });
		this.draw();
		return true;
	}

	_removeMultiOutputSlot(node, fieldName, key) {
		if (!node.multiOutputSlots?.[fieldName]) return false;
		for (const idx of node.multiOutputSlots[fieldName].slice()) {
			const name = node.outputs[idx]?.name || '';
			const dotIdx = name.indexOf('.');
			const slotKey = dotIdx !== -1 ? name.substring(dotIdx + 1) : name;
			if (slotKey === key) {
				// Capture the slot type before removal for potential base slot restoration
				const slotType = node.outputMeta?.[idx]?.type || node.outputs[idx]?.type || 'Any';

				// Remove any connections from this slot
				for (const linkId of node.outputs[idx].links.slice()) {
					const link = this.graph.links[linkId];
					if (link) {
						const targetNode = this.graph.getNodeById(link.target_id);
						if (targetNode) {
							if (targetNode.multiInputs?.[link.target_slot]) {
								const lidx = targetNode.multiInputs[link.target_slot].links.indexOf(linkId);
								if (lidx > -1) targetNode.multiInputs[link.target_slot].links.splice(lidx, 1);
							} else {
								targetNode.inputs[link.target_slot].link = null;
							}
						}
						delete this.graph.links[linkId];
					}
				}

				// Actually remove the output from the node
				node.outputs.splice(idx, 1);

				// Update outputMeta indices
				if (node.outputMeta) {
					const newMeta = {};
					for (const [i, meta] of Object.entries(node.outputMeta)) {
						const iNum = parseInt(i);
						if (iNum < idx) newMeta[iNum] = meta;
						else if (iNum > idx) newMeta[iNum - 1] = meta;
					}
					node.outputMeta = newMeta;
				}

				// Update multiOutputSlots indices for all fields
				for (const [fn, indices] of Object.entries(node.multiOutputSlots)) {
					node.multiOutputSlots[fn] = indices.filter(i => i !== idx).map(i => i > idx ? i - 1 : i);
				}

				// Update all links originating from this node's outputs
				for (const link of Object.values(this.graph.links)) {
					if (link.origin_id === node.id && link.origin_slot > idx) {
						link.origin_slot--;
					}
				}

				// If all sub-slots were removed, restore a base slot so the "+" button remains
				if (node.multiOutputSlots[fieldName].length === 0) {
					const baseIdx = node.outputs.length;
					node.outputs.push({ name: fieldName, type: slotType, links: [] });
					if (!node.outputMeta) node.outputMeta = {};
					node.outputMeta[baseIdx] = { name: fieldName, type: slotType, isMulti: true };
					node.multiOutputSlots[fieldName] = [baseIdx];
				}

				this._recalculateNodeSize(node);
				this.eventBus.emit(GraphEvents.FIELD_CHANGED, { nodeId: node.id, fieldName, action: 'removeSlot', key });
				this.draw();
				return true;
			}
		}
		return false;
	}

	_renameMultiInputSlot(node, fieldName, oldKey, newKey) {
		if (!node.multiInputSlots?.[fieldName]) return false;
		const existingKeys = this._getMultiInputKeys(node, fieldName);
		if (existingKeys.includes(newKey)) return false;
		for (const idx of node.multiInputSlots[fieldName]) {
			const name = node.inputs[idx]?.name || '';
			const dotIdx = name.indexOf('.');
			const slotKey = dotIdx !== -1 ? name.substring(dotIdx + 1) : name;
			if (slotKey === oldKey) {
				const meta = node.inputMeta?.[idx];
				const newDisplayName = meta?.title ? `${meta.title}.${newKey}` : `${fieldName}.${newKey}`;
				node.inputs[idx].name = newDisplayName;
				if (node.inputMeta?.[idx]) node.inputMeta[idx].name = `${fieldName}.${newKey}`;
				this.eventBus.emit(GraphEvents.FIELD_CHANGED, { nodeId: node.id, fieldName, action: 'renameSlot', oldKey, newKey });
				this.draw();
				return true;
			}
		}
		return false;
	}

	_renameMultiOutputSlot(node, fieldName, oldKey, newKey) {
		if (!node.multiOutputSlots?.[fieldName]) return false;
		const existingKeys = this._getMultiOutputKeys(node, fieldName);
		if (existingKeys.includes(newKey)) return false;
		for (const idx of node.multiOutputSlots[fieldName]) {
			const name = node.outputs[idx]?.name || '';
			const dotIdx = name.indexOf('.');
			const slotKey = dotIdx !== -1 ? name.substring(dotIdx + 1) : name;
			if (slotKey === oldKey) {
				const meta = node.outputMeta?.[idx];
				const newDisplayName = meta?.title ? `${meta.title}.${newKey}` : `${fieldName}.${newKey}`;
				node.outputs[idx].name = newDisplayName;
				if (node.outputMeta?.[idx]) node.outputMeta[idx].name = `${fieldName}.${newKey}`;
				this.eventBus.emit(GraphEvents.FIELD_CHANGED, { nodeId: node.id, fieldName, action: 'renameSlot', oldKey, newKey });
				this.draw();
				return true;
			}
		}
		return false;
	}

	_isFieldHidden(node, slotIdx, isOutput) {
		if (!this._features.hiddenFields) return false;
		const meta = isOutput ? node.outputMeta?.[slotIdx] : node.inputMeta?.[slotIdx];
		const name = meta?.name || (isOutput ? node.outputs[slotIdx]?.name : node.inputs[slotIdx]?.name);
		return this._hiddenFieldNames.includes(name);
	}

	_getVisibleSlotIndex(node, slotIdx, isOutput) {
		let vis = 0;
		for (let j = 0; j < slotIdx; j++) {
			if (!this._isFieldHidden(node, j, isOutput)) vis++;
		}
		return vis;
	}

	_prettifyName(name) {
		if (name.includes('_')) {
			return name.split('_').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');
		}
		return name.replace(/([a-z])([A-Z])/g, '$1 $2')
			.replace(/([A-Z]+)([A-Z][a-z])/g, '$1 $2')
			.replace(/^./, c => c.toUpperCase());
	}

	_getSlotDisplayName(node, slotIdx, isOutput) {
		const meta = isOutput ? node.outputMeta?.[slotIdx] : node.inputMeta?.[slotIdx];
		const slot = isOutput ? node.outputs[slotIdx] : node.inputs[slotIdx];
		if (!meta) return slot?.name;
		const origName = meta.name || slot?.name;
		const dotIdx = origName.indexOf('.');
		if (dotIdx >= 0) {
			const parentName = origName.substring(0, dotIdx);
			const key = origName.substring(dotIdx + 1);
			if (meta.title) return `${meta.title}.${key}`;
			if (this._features.prettyFieldNames) return `${this._prettifyName(parentName)}.${key}`;
			return origName;
		}
		if (meta.title) return meta.title;
		if (this._features.prettyFieldNames) return this._prettifyName(origName);
		return origName;
	}

	_getVisibleSlotCount(node, isOutput) {
		const slots = isOutput ? node.outputs : node.inputs;
		let count = 0;
		for (let j = 0; j < slots.length; j++) {
			if (!this._isFieldHidden(node, j, isOutput)) count++;
		}
		return count;
	}

	_getSlotUnderMouse(wx, wy) {
		for (const node of this.graph.nodes) {
			let visIdx = 0;
			for (let j = 0; j < node.inputs.length; j++) {
				if (this._isFieldHidden(node, j, false)) continue;
				const slotY = node.pos[1] + 38 + visIdx * 25;
				if (Math.abs(wx - node.pos[0]) < 15 && Math.abs(wy - slotY) < 12) return { node, slotIdx: j, isInput: true };
				visIdx++;
			}
			visIdx = 0;
			for (let j = 0; j < node.outputs.length; j++) {
				if (this._isFieldHidden(node, j, true)) continue;
				const slotY = node.pos[1] + 38 + visIdx * 25;
				if (Math.abs(wx - (node.pos[0] + node.size[0])) < 15 && Math.abs(wy - slotY) < 12) return { node, slotIdx: j, isInput: false };
				visIdx++;
			}
		}
		return null;
	}

	// === COORDINATE CONVERSION ===
	screenToWorld(sx, sy) { return [(sx - this.camera.x) / this.camera.scale, (sy - this.camera.y) / this.camera.scale]; }
	worldToScreen(wx, wy) { return [wx * this.camera.scale + this.camera.x, wy * this.camera.scale + this.camera.y]; }

	centerView() {
		if (this.graph.nodes.length === 0) return;
		let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
		for (const node of this.graph.nodes) {
			minX = Math.min(minX, node.pos[0]);
			minY = Math.min(minY, node.pos[1]);
			maxX = Math.max(maxX, node.pos[0] + node.size[0]);
			maxY = Math.max(maxY, node.pos[1] + node.size[1]);
		}
		const graphCenterX = minX + (maxX - minX) / 2;
		const graphCenterY = minY + (maxY - minY) / 2;
		const scaleX = (this.canvas.width - 200) / (maxX - minX);
		const scaleY = (this.canvas.height - 200) / (maxY - minY);
		this.camera.scale = Math.max(0.1, Math.min(5, Math.min(scaleX, scaleY, 1.5)));
		this.camera.x = this.canvas.width / 2 - graphCenterX * this.camera.scale;
		this.camera.y = this.canvas.height / 2 - graphCenterY * this.camera.scale;
		this.eventBus.emit('ui:update', { id: 'zoomLevel', content: Math.round(this.camera.scale * 100) + '%' });
		this.draw();
	}

	resetZoom() {
		const worldCenter = this.screenToWorld(this.canvas.width / 2, this.canvas.height / 2);
		this.camera.scale = 1.0;
		this.camera.x = this.canvas.width / 2 - worldCenter[0];
		this.camera.y = this.canvas.height / 2 - worldCenter[1];
		this.eventBus.emit('ui:update', { id: 'zoomLevel', content: '100%' });
		this.draw();
	}

	// === LAYOUT ===
	applyLayout(layoutType) {
		if (this.graph.nodes.length === 0) return;
		switch (layoutType) {
			case 'hierarchical-vertical': this.applyHierarchicalLayout(true); break;
			case 'hierarchical-horizontal': this.applyHierarchicalLayout(false); break;
			case 'force-directed': this.applyForceDirectedLayout(); break;
			case 'grid': this.applyGridLayout(); break;
			case 'circular': this.applyCircularLayout(); break;
		}
		this.eventBus.emit('layout:applied', { layoutType });
		this.draw();
		this.centerView();
	}

	applyHierarchicalLayout(vertical = false) {
		const rootNodes = this.graph.nodes.filter(n => !n.inputs.some(inp => inp.link) || n.isRootType);
		if (rootNodes.length === 0) rootNodes.push(...this.graph.nodes);
		const layers = [], processedNodes = new Set();
		const queue = rootNodes.map(n => { processedNodes.add(n); return { node: n, layer: 0 }; });
		while (queue.length > 0) {
			const { node, layer } = queue.shift();
			if (!layers[layer]) layers[layer] = [];
			layers[layer].push(node);
			for (const output of node.outputs) {
				for (const linkId of output.links) {
					const link = this.graph.links[linkId];
					if (link) {
						const targetNode = this.graph.getNodeById(link.target_id);
						if (targetNode && !processedNodes.has(targetNode)) {
							processedNodes.add(targetNode);
							queue.push({ node: targetNode, layer: layer + 1 });
						}
					}
				}
			}
		}
		for (const node of this.graph.nodes) {
			if (!processedNodes.has(node)) {
				if (!layers[layers.length]) layers.push([]);
				layers[layers.length - 1].push(node);
			}
		}
		for (let i = 0; i < layers.length; i++) {
			for (let j = 0; j < layers[i].length; j++) {
				const node = layers[i][j];
				if (vertical) { node.pos[0] = 100 + i * 300; node.pos[1] = 100 + j * 150 - (layers[i].length * 150) / 2; }
				else { node.pos[0] = 100 + j * 250 - (layers[i].length * 250) / 2; node.pos[1] = 100 + i * 200; }
			}
		}
	}

	applyForceDirectedLayout() {
		const velocities = new Map();
		for (const node of this.graph.nodes) {
			velocities.set(node, { x: 0, y: 0 });
			if (node.pos[0] === 0 && node.pos[1] === 0) { node.pos[0] = Math.random() * 400; node.pos[1] = Math.random() * 400; }
		}
		for (let iter = 0; iter < 100; iter++) {
			for (let i = 0; i < this.graph.nodes.length; i++) {
				const nodeA = this.graph.nodes[i], vel = velocities.get(nodeA);
				for (let j = i + 1; j < this.graph.nodes.length; j++) {
					const nodeB = this.graph.nodes[j];
					const dx = nodeB.pos[0] - nodeA.pos[0], dy = nodeB.pos[1] - nodeA.pos[1];
					const distSq = dx * dx + dy * dy, dist = Math.sqrt(distSq);
					if (dist < 0.1) continue;
					const force = 50000 / distSq, fx = (dx / dist) * force, fy = (dy / dist) * force;
					vel.x -= fx; vel.y -= fy;
					velocities.get(nodeB).x += fx;
					velocities.get(nodeB).y += fy;
				}
			}
			for (const linkId in this.graph.links) {
				const link = this.graph.links[linkId];
				const nodeA = this.graph.getNodeById(link.origin_id), nodeB = this.graph.getNodeById(link.target_id);
				if (!nodeA || !nodeB) continue;
				const dx = nodeB.pos[0] - nodeA.pos[0], dy = nodeB.pos[1] - nodeA.pos[1], dist = Math.sqrt(dx * dx + dy * dy);
				if (dist < 0.1) continue;
				const force = (dist - 200) * 0.01, fx = (dx / dist) * force, fy = (dy / dist) * force;
				velocities.get(nodeA).x += fx; velocities.get(nodeA).y += fy;
				velocities.get(nodeB).x -= fx; velocities.get(nodeB).y -= fy;
			}
			for (const node of this.graph.nodes) {
				const vel = velocities.get(node);
				node.pos[0] += vel.x; node.pos[1] += vel.y;
				vel.x *= 0.9; vel.y *= 0.9;
			}
		}
	}

	applyGridLayout() {
		const cols = Math.ceil(Math.sqrt(this.graph.nodes.length));
		for (let i = 0; i < this.graph.nodes.length; i++) {
			this.graph.nodes[i].pos = [100 + (i % cols) * 250, 100 + Math.floor(i / cols) * 200];
		}
	}

	applyCircularLayout() {
		const radius = Math.max(300, this.graph.nodes.length * 30);
		const angleStep = (2 * Math.PI) / this.graph.nodes.length;
		for (let i = 0; i < this.graph.nodes.length; i++) {
			this.graph.nodes[i].pos = [Math.cos(i * angleStep) * radius, Math.sin(i * angleStep) * radius];
		}
	}

	// === DRAWING ===
	getCanvasColors() {
		const style = getComputedStyle(document.documentElement);
		return {
			canvasBg: style.getPropertyValue('--sg-canvas-bg').trim() || '#1a1a2e',
			nodeBg: style.getPropertyValue('--sg-node-bg').trim() || '#252540',
			nodeBgSelected: style.getPropertyValue('--sg-node-bg-selected').trim() || '#303050',
			nodeHeader: style.getPropertyValue('--sg-node-header').trim() || '#404060',
			nodeShadow: style.getPropertyValue('--sg-node-shadow').trim() || 'rgba(0,0,0,0.3)',
			borderColor: style.getPropertyValue('--sg-border-color').trim() || '#404060',
			borderHighlight: style.getPropertyValue('--sg-border-highlight').trim() || '#46a2da',
			textPrimary: style.getPropertyValue('--sg-text-primary').trim() || '#ffffff',
			textSecondary: style.getPropertyValue('--sg-text-secondary').trim() || '#b0b0c0',
			textTertiary: style.getPropertyValue('--sg-text-tertiary').trim() || '#808090',
			accentPurple: style.getPropertyValue('--sg-accent-purple').trim() || '#9370db',
			accentOrange: style.getPropertyValue('--sg-accent-orange').trim() || '#f5a623',
			accentGreen: style.getPropertyValue('--sg-accent-green').trim() || '#50c878',
			accentRed: style.getPropertyValue('--sg-accent-red').trim() || '#dc6068',
			slotInput: style.getPropertyValue('--sg-slot-input').trim() || '#6495ed',
			slotOutput: style.getPropertyValue('--sg-slot-output').trim() || '#98d982',
			slotConnected: style.getPropertyValue('--sg-slot-connected').trim() || '#ffd700',
			linkColor: style.getPropertyValue('--sg-link-color').trim() || '#7090b0',
			gridColor: style.getPropertyValue('--sg-grid-color').trim() || '#303050'
		};
	}

	draw() {
		const colors = this.getCanvasColors();
		this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
		this.ctx.fillStyle = colors.canvasBg;
		this.ctx.fillRect(0, 0, this.canvas.width, this.canvas.height);
		this.ctx.save();
		this.ctx.translate(this.camera.x, this.camera.y);
		this.ctx.scale(this.camera.scale, this.camera.scale);
		this.drawGrid(colors);
		this.drawLinks(colors);
		this.drawNodes(colors);
		if (this.connecting) this.drawConnecting(colors);
		if (this.selectionRect) {
			this.ctx.strokeStyle = colors.borderHighlight;
			this.ctx.fillStyle = 'rgba(70,162,218,0.1)';
			this.ctx.lineWidth = 1 / this.camera.scale;
			this.ctx.setLineDash([5 / this.camera.scale, 5 / this.camera.scale]);
			this.ctx.fillRect(this.selectionRect.x, this.selectionRect.y, this.selectionRect.w, this.selectionRect.h);
			this.ctx.strokeRect(this.selectionRect.x, this.selectionRect.y, this.selectionRect.w, this.selectionRect.h);
			this.ctx.setLineDash([]);
		}
		this.ctx.restore();

		// Canvas drop highlight overlay
		if (this._canvasDropHighlight) {
			this._drawCanvasDropHighlight(colors);
		}
	}

	/**
	 * Draw canvas drop highlight overlay when dragging files over canvas
	 * @param {Object} colors - Theme colors
	 */
	_drawCanvasDropHighlight(colors) {
		const w = this.canvas.width;
		const h = this.canvas.height;
		const borderWidth = 4;
		const cornerRadius = 0;

		this.ctx.save();

		// Semi-transparent overlay
		this.ctx.fillStyle = 'rgba(74, 158, 255, 0.08)';
		this.ctx.fillRect(0, 0, w, h);

		// Animated dashed border
		const time = performance.now() / 1000;
		const dashOffset = (time * 30) % 20;

		this.ctx.strokeStyle = colors.accentBlue || '#4a9eff';
		this.ctx.lineWidth = borderWidth;
		this.ctx.setLineDash([10, 10]);
		this.ctx.lineDashOffset = -dashOffset;

		// Draw border inset by half the border width
		const inset = borderWidth / 2;
		if (cornerRadius > 0) {
			this.ctx.beginPath();
			this.ctx.roundRect(inset, inset, w - borderWidth, h - borderWidth, cornerRadius);
			this.ctx.stroke();
		} else {
			this.ctx.strokeRect(inset, inset, w - borderWidth, h - borderWidth);
		}

		this.ctx.setLineDash([]);

		// Drop hint text
		const text = '📁 Drop files to create nodes';
		this.ctx.font = 'bold 16px Arial, sans-serif';
		const textWidth = this.ctx.measureText(text).width;

		// Background pill for text
		const pillPadding = 16;
		const pillHeight = 36;
		const pillWidth = textWidth + pillPadding * 2;
		const pillX = (w - pillWidth) / 2;
		const pillY = h - 60;

		this.ctx.fillStyle = 'rgba(74, 158, 255, 0.9)';
		this.ctx.beginPath();
		this.ctx.roundRect(pillX, pillY, pillWidth, pillHeight, 18);
		this.ctx.fill();

		// Text
		this.ctx.fillStyle = '#ffffff';
		this.ctx.textAlign = 'center';
		this.ctx.textBaseline = 'middle';
		this.ctx.fillText(text, w / 2, pillY + pillHeight / 2);

		this.ctx.restore();

		// Request animation frame for continuous border animation
		if (this._canvasDropHighlight) {
			requestAnimationFrame(() => {
				if (this._canvasDropHighlight) this.draw();
			});
		}
	}

	drawGrid(colors) {
		const style = this.drawingStyleManager.getStyle(), gridSize = 50;
		const worldRect = { x: -this.camera.x / this.camera.scale, y: -this.camera.y / this.camera.scale, width: this.canvas.width / this.camera.scale, height: this.canvas.height / this.camera.scale };
		const startX = Math.floor(worldRect.x / gridSize) * gridSize;
		const startY = Math.floor(worldRect.y / gridSize) * gridSize;
		this.ctx.strokeStyle = colors.gridColor;
		this.ctx.globalAlpha = style.gridOpacity;
		this.ctx.lineWidth = 1 / this.camera.scale;
		if (style.useDashed) this.ctx.setLineDash([4 / this.camera.scale, 4 / this.camera.scale]);
		this.ctx.beginPath();
		for (let x = startX; x <= worldRect.x + worldRect.width; x += gridSize) { this.ctx.moveTo(x, worldRect.y); this.ctx.lineTo(x, worldRect.y + worldRect.height); }
		for (let y = startY; y <= worldRect.y + worldRect.height; y += gridSize) { this.ctx.moveTo(worldRect.x, y); this.ctx.lineTo(worldRect.x + worldRect.width, y); }
		this.ctx.stroke();
		if (style.useDashed) this.ctx.setLineDash([]);
		this.ctx.globalAlpha = 1.0;
	}

	drawLinks(colors) {
		const style = this.drawingStyleManager.getStyle();
		const showCompleteness = this._features.completenessIndicators;
		const hoveredLinkId = this._hoveredLink?.id;

		for (const linkId in this.graph.links) {
			const link = this.graph.links[linkId];
			const orig = this.graph.getNodeById(link.origin_id);
			const targ = this.graph.getNodeById(link.target_id);
			if (!orig || !targ) continue;
			const x1 = orig.pos[0] + orig.size[0], y1 = orig.pos[1] + 38 + this._getVisibleSlotIndex(orig, link.origin_slot, true) * 25;
			const x2 = targ.pos[0], y2 = targ.pos[1] + 38 + this._getVisibleSlotIndex(targ, link.target_slot, false) * 25;
			const controlOffset = Math.min(Math.abs(x2 - x1) * style.linkCurve, 400);
			const incompleteLinks = showCompleteness ? (targ._incompleteChainLinks || []) : [];
			const isIncompleteLink = incompleteLinks.some(lid => String(lid) === String(link.id) || lid === link.id);
			const isHovered = String(link.id) === String(hoveredLinkId);

			// Check if this is a loop-back edge
			const isLoopEdge = link.loop === true;

			// Determine link color and width
			let strokeColor = isLoopEdge ? (colors.loopColor || '#9b59b6') : (isIncompleteLink ? colors.accentOrange : colors.linkColor);
			let lineWidth = (isIncompleteLink ? style.linkWidth + 1 : style.linkWidth) / this.camera.scale;

			// Apply hover highlight
			if (isHovered) {
				strokeColor = colors.accentBlue || '#4a9eff';
				lineWidth = (style.linkWidth + 3) / this.camera.scale;
				// Draw glow effect for hovered link
				this.ctx.save();
				this.ctx.strokeStyle = strokeColor;
				this.ctx.lineWidth = (style.linkWidth + 8) / this.camera.scale;
				this.ctx.globalAlpha = 0.3;
				this.ctx.beginPath();
				if (style.linkCurve > 0) {
					this.ctx.moveTo(x1, y1);
					this.ctx.bezierCurveTo(x1 + controlOffset, y1, x2 - controlOffset, y2, x2, y2);
				} else {
					this.ctx.moveTo(x1, y1);
					this.ctx.lineTo(x2, y2);
				}
				this.ctx.stroke();
				this.ctx.restore();
			}

			this.ctx.strokeStyle = strokeColor;
			this.ctx.lineWidth = lineWidth;
			if (isLoopEdge || isIncompleteLink || style.useDashed) this.ctx.setLineDash([8 / this.camera.scale, 4 / this.camera.scale]);
			this.ctx.beginPath();

			// Use orthogonal routing for loop-back edges when feature is enabled
			if (isLoopEdge && this._features.loopEdgeOrthogonal) {
				// Orthogonal routing: right → down → left → up pattern
				const margin = 40;  // Distance from nodes
				const loopOffset = (link.origin_slot + 1) * 15;  // Stagger multiple loop edges

				// Calculate routing points
				const rightX = Math.max(x1, x2) + margin + loopOffset;
				const bottomY = Math.max(orig.pos[1] + orig.size[1], targ.pos[1] + targ.size[1]) + margin + loopOffset;
				const leftX = Math.min(orig.pos[0], targ.pos[0]) - margin - loopOffset;

				// Draw orthogonal path: source → right → down → left → up → target
				this.ctx.moveTo(x1, y1);
				this.ctx.lineTo(rightX, y1);           // Go right
				this.ctx.lineTo(rightX, bottomY);       // Go down
				this.ctx.lineTo(leftX, bottomY);        // Go left
				this.ctx.lineTo(leftX, y2);             // Go up
				this.ctx.lineTo(x2, y2);                // Go to target
			} else if (style.linkCurve > 0) {
				this.ctx.moveTo(x1, y1);
				this.ctx.bezierCurveTo(x1 + controlOffset, y1, x2 - controlOffset, y2, x2, y2);
			} else {
				this.ctx.moveTo(x1, y1);
				this.ctx.lineTo(x2, y2);
			}
			this.ctx.stroke();
			this.ctx.setLineDash([]);

			// Draw loop indicator icon for loop-back edges
			if (isLoopEdge) {
				// Position icon at the bottom-left corner of the orthogonal path
				let iconX, iconY;
				if (this._features.loopEdgeOrthogonal) {
					const margin = 40;
					const loopOffset = (link.origin_slot + 1) * 15;
					const leftX = Math.min(orig.pos[0], targ.pos[0]) - margin - loopOffset;
					const bottomY = Math.max(orig.pos[1] + orig.size[1], targ.pos[1] + targ.size[1]) + margin + loopOffset;
					iconX = leftX;
					iconY = bottomY;
				} else {
					iconX = (x1 + x2) / 2;
					iconY = (y1 + y2) / 2;
				}
				this.ctx.fillStyle = colors.loopColor || '#9b59b6';
				this.ctx.beginPath();
				this.ctx.arc(iconX, iconY, 10 / this.camera.scale, 0, Math.PI * 2);
				this.ctx.fill();
				this.ctx.fillStyle = '#fff';
				this.ctx.font = `${12 / this.camera.scale}px sans-serif`;
				this.ctx.textAlign = 'center';
				this.ctx.textBaseline = 'middle';
				this.ctx.fillText('↺', iconX, iconY);
			}

			// Draw hover hint icon at midpoint (skip for loop-back edges)
			if (isHovered && !isLoopEdge) {
				const midX = (x1 + x2) / 2;
				const midY = (y1 + y2) / 2;
				// Draw preview icon background
				this.ctx.fillStyle = colors.accentBlue || '#4a9eff';
				this.ctx.beginPath();
				this.ctx.arc(midX, midY, 12 / this.camera.scale, 0, Math.PI * 2);
				this.ctx.fill();
				// Draw eye icon
				this.ctx.fillStyle = '#fff';
				this.ctx.font = `${10 / this.camera.scale}px sans-serif`;
				this.ctx.textAlign = 'center';
				this.ctx.textBaseline = 'middle';
				this.ctx.fillText('👁', midX, midY);
			}

			// Skip incomplete link indicator for loop-back edges
			if (isIncompleteLink && !isLoopEdge) {
				const midX = (x1 + x2) / 2, midY = (y1 + y2) / 2;
				this.ctx.fillStyle = colors.accentOrange;
				this.ctx.beginPath();
				this.ctx.arc(midX, midY, 6 / this.camera.scale, 0, Math.PI * 2);
				this.ctx.fill();
				this.ctx.fillStyle = '#fff';
				this.ctx.font = `bold ${8 / this.camera.scale}px sans-serif`;
				this.ctx.textAlign = 'center';
				this.ctx.textBaseline = 'middle';
				this.ctx.fillText('!', midX, midY);
			}
		}
	}

	drawNodes(colors) {
		const unsel = [], sel = [];
		for (const node of this.graph.nodes) (this.isNodeSelected(node) ? sel : unsel).push(node);
		for (const node of unsel) this.drawNode(node, colors);
		for (const node of sel) this.drawNode(node, colors);
	}

	drawNode(node, colors) {
		// Check for PreviewFlow node - use specialized rendering
		if (this._isPreviewFlowNode(node)) {
			this._drawPreviewFlowNode(node, colors);
			return;
		}

		const style = this.drawingStyleManager.getStyle();
		const x = node.pos[0], y = node.pos[1], w = node.size[0], h = node.size[1];
		const radius = style.nodeCornerRadius, textScale = this.getTextScale();
		const isSelected = this.isNodeSelected(node);
		const isPreviewSelected = this.previewSelection.has(node);
		const bodyColor = isSelected ? colors.nodeBgSelected : (isPreviewSelected ? this.adjustColorBrightness(colors.nodeBg, 20) : colors.nodeBg);

		if (style.nodeShadowBlur > 0) {
			this.ctx.shadowColor = colors.nodeShadow;
			this.ctx.shadowBlur = style.nodeShadowBlur / this.camera.scale;
			this.ctx.shadowOffsetY = style.nodeShadowOffset / this.camera.scale;
		}

		if (style.useGradient && style.currentStyle !== 'wireframe') {
			const gradient = this.ctx.createLinearGradient(x, y, x, y + h);
			gradient.addColorStop(0, bodyColor);
			gradient.addColorStop(1, this.adjustColorBrightness(bodyColor, -20));
			this.ctx.fillStyle = gradient;
		} else {
			this.ctx.fillStyle = style.currentStyle === 'wireframe' ? 'transparent' : bodyColor;
		}

		this.ctx.beginPath();
		if (radius > 0) {
			this.ctx.moveTo(x + radius, y); this.ctx.lineTo(x + w - radius, y);
			this.ctx.quadraticCurveTo(x + w, y, x + w, y + radius);
			this.ctx.lineTo(x + w, y + h - radius);
			this.ctx.quadraticCurveTo(x + w, y + h, x + w - radius, y + h);
			this.ctx.lineTo(x + radius, y + h);
			this.ctx.quadraticCurveTo(x, y + h, x, y + h - radius);
			this.ctx.lineTo(x, y + radius);
			this.ctx.quadraticCurveTo(x, y, x + radius, y);
			this.ctx.closePath();
		} else { this.ctx.rect(x, y, w, h); }
		if (style.currentStyle !== 'wireframe') this.ctx.fill();

		this.ctx.shadowBlur = 0; this.ctx.shadowOffsetY = 0;
		this.ctx.strokeStyle = isSelected ? colors.borderHighlight : colors.borderColor;
		this.ctx.lineWidth = (isSelected ? 2 : 1) / this.camera.scale;
		if (isPreviewSelected && !isSelected) this.ctx.setLineDash([5 / this.camera.scale, 5 / this.camera.scale]);
		this.ctx.stroke();
		if (isPreviewSelected && !isSelected) this.ctx.setLineDash([]);

		const headerColor = node.color || (node.isNative ? colors.accentPurple : (node.isRootType ? colors.accentOrange : colors.nodeHeader));
		if (style.useGradient && style.currentStyle !== 'wireframe') {
			const headerGradient = this.ctx.createLinearGradient(x, y, x, y + 26);
			headerGradient.addColorStop(0, headerColor); headerGradient.addColorStop(1, this.adjustColorBrightness(headerColor, -30));
			this.ctx.fillStyle = headerGradient;
		} else { this.ctx.fillStyle = style.currentStyle === 'wireframe' ? 'transparent' : headerColor; }

		this.ctx.beginPath();
		if (radius > 0) {
			this.ctx.moveTo(x + radius, y); this.ctx.lineTo(x + w - radius, y);
			this.ctx.quadraticCurveTo(x + w, y, x + w, y + radius);
			this.ctx.lineTo(x + w, y + 26); this.ctx.lineTo(x, y + 26);
			this.ctx.lineTo(x, y + radius);
			this.ctx.quadraticCurveTo(x, y, x + radius, y);
		} else { this.ctx.rect(x, y, w, 26); }
		this.ctx.closePath();
		if (style.currentStyle !== 'wireframe') this.ctx.fill();

		this.ctx.save();
		this.ctx.beginPath(); this.ctx.rect(x + 4, y, w - 8, 26); this.ctx.clip();
		this.ctx.fillStyle = colors.textPrimary;
		this.ctx.font = (11 * textScale) + 'px ' + style.textFont;
		this.ctx.textBaseline = 'middle'; this.ctx.textAlign = 'left';
		const infoTitle = node.displayTitle || node.nodeInfo?.title || node.title;
		const icon = node.nodeInfo?.icon || '';
		let displayTitle = (node.isRootType ? '☆ ' : '') + (icon ? `${icon} ${infoTitle}` : infoTitle);
		const maxWidth = w - 16;
		if (this.ctx.measureText(displayTitle).width > maxWidth) {
			let left = 0, right = displayTitle.length;
			while (left < right) {
				const mid = Math.floor((left + right + 1) / 2);
				if (this.ctx.measureText(displayTitle.substring(0, mid) + '...').width <= maxWidth) left = mid;
				else right = mid - 1;
			}
			displayTitle = displayTitle.substring(0, left) + '...';
		}
		this.ctx.fillText(displayTitle, x + 8, y + 13);
		this.ctx.restore();

		// Draw execution state indicator (animated spinner for running nodes)
		if (node.executionState) {
			if (node.executionState === 'running') {
				this._drawExecutionSpinner(x + w - 16, y + 13, 6, colors);
			} else if (node.executionState === 'waiting') {
				this._drawWaitingClock(x + w - 16, y + 13, 6, colors);
			} else if (node.executionState === 'completed') {
				this._drawExecutionCheck(x + w - 16, y + 13, 6, colors);
			} else if (node.executionState === 'failed') {
				this._drawExecutionX(x + w - 16, y + 13, 6, colors);
			}
		}

		if (this._features.completenessIndicators) {
			this._drawCompletenessIndicator(node, colors);
		}

		const worldMouse = this.screenToWorld(this.mousePos[0], this.mousePos[1]);
		{ let vi = 0; for (let j = 0; j < node.inputs.length; j++) { if (!this._isFieldHidden(node, j, false)) this.drawInputSlot(node, j, x, y, w, worldMouse, colors, textScale, style, vi++); } }
		{ let vi = 0; for (let j = 0; j < node.outputs.length; j++) { if (!this._isFieldHidden(node, j, true)) this.drawOutputSlot(node, j, x, y, w, worldMouse, colors, textScale, style, vi++); } }

		if (node.isNative && node.properties.value !== undefined) {
			const valueY = y + h - 18, valueX = x + 8, valueW = w - 16, valueH = 18;
			this.ctx.fillStyle = 'rgba(0,0,0,0.4)';
			this.ctx.beginPath(); this.ctx.roundRect(valueX, valueY - 10, valueW, valueH, 4); this.ctx.fill();
			this.ctx.strokeStyle = colors.borderColor; this.ctx.lineWidth = 1.5 / this.camera.scale; this.ctx.stroke();
			this.ctx.fillStyle = colors.textPrimary;
			this.ctx.font = (10 * textScale) + 'px ' + style.textFont;
			this.ctx.textAlign = 'center'; this.ctx.textBaseline = 'middle';
			let displayValue = String(node.properties.value);
			if (displayValue.length > 20) displayValue = displayValue.substring(0, 20) + '...';
			this.ctx.fillText(displayValue, valueX + valueW / 2, valueY);
		}

		if (node.isWorkflowNode) this._drawMultiSlotButtons(node, colors);
		this._drawDropZoneHighlight(node);
		this._drawButtonStacks(node, colors);
	}

	_drawMultiSlotButtons(node, colors) {
		const textScale = this.getTextScale();
		const addButtons = this._getMultiSlotAddButtons(node);
		for (const btn of addButtons) {
			const isHovered = this._hoveredAddButton?.nodeId === node.id && this._hoveredAddButton?.fieldName === btn.fieldName && this._hoveredAddButton?.type === btn.type;
			this.ctx.fillStyle = isHovered ? 'rgba(92, 184, 92, 0.9)' : 'rgba(92, 184, 92, 0.5)';
			this.ctx.beginPath(); this.ctx.arc(btn.x + btn.w/2, btn.y + btn.h/2, btn.w/2, 0, Math.PI * 2); this.ctx.fill();
			this.ctx.fillStyle = '#fff'; this.ctx.font = `bold ${10 * textScale}px sans-serif`;
			this.ctx.textAlign = 'center'; this.ctx.textBaseline = 'middle';
			this.ctx.fillText('+', btn.x + btn.w/2, btn.y + btn.h/2);
		}
		const removeButtons = this._getMultiSlotRemoveButtons(node);
		for (const btn of removeButtons) {
			const isHovered = this._hoveredRemoveButton?.nodeId === node.id && this._hoveredRemoveButton?.key === btn.key;
			if (!isHovered && !this._isMouseNearNode(node)) continue;
			this.ctx.fillStyle = isHovered ? 'rgba(217, 83, 79, 0.9)' : 'rgba(217, 83, 79, 0.4)';
			this.ctx.beginPath(); this.ctx.arc(btn.x + btn.w/2, btn.y + btn.h/2, btn.w/2, 0, Math.PI * 2); this.ctx.fill();
			this.ctx.fillStyle = '#fff'; this.ctx.font = `bold ${8 * textScale}px sans-serif`;
			this.ctx.textAlign = 'center'; this.ctx.textBaseline = 'middle';
			this.ctx.fillText('−', btn.x + btn.w/2, btn.y + btn.h/2);
		}
	}

	drawInputSlot(node, j, x, y, w, worldMouse, colors, textScale, style, visIdx) {
		const inp = node.inputs[j], sy = y + 38 + (visIdx !== undefined ? visIdx : j) * 25;
		const isMulti = node.multiInputs?.[j];
		const hasConnections = isMulti ? node.multiInputs[j].links.length > 0 : inp.link;
		const compat = this.isSlotCompatible(node, j, false);
		const isRequired = this._isFieldRequired(node, j);
		const isFilled = this._isFieldFilled(node, j);
		const showRequiredHighlight = isRequired && !isFilled;
		// Check if this is a base multi-field slot (no dot in name and tracked in multiInputSlots)
		const isBaseMultiSlot = !inp.name.includes('.') && Object.values(node.multiInputSlots || {}).some(indices => indices.includes(j));
		let color = hasConnections ? colors.slotConnected : colors.slotInput;
		if (showRequiredHighlight) color = colors.accentRed;
		if (this.connecting && (compat || (this.connecting.node === node && this.connecting.slot === j && !this.connecting.isOutput))) {
			color = colors.accentGreen;
			if (!isBaseMultiSlot) {
				this.ctx.fillStyle = color; this.ctx.globalAlpha = 0.3;
				this.ctx.beginPath(); this.ctx.arc(x - 1, sy, 8, 0, Math.PI * 2); this.ctx.fill();
				this.ctx.globalAlpha = 1.0;
			}
		}
		// Skip drawing pin for base multi-field slots (plus button covers it)
		if (!isBaseMultiSlot) {
			this.ctx.fillStyle = color;
			this.ctx.beginPath(); this.ctx.arc(x - 1, sy, style.slotRadius || 4, 0, Math.PI * 2); this.ctx.fill();
			if (showRequiredHighlight) {
				this.ctx.strokeStyle = colors.accentRed; this.ctx.lineWidth = 2 / this.camera.scale;
				this.ctx.beginPath(); this.ctx.arc(x - 1, sy, 7, 0, Math.PI * 2); this.ctx.stroke();
			}
			if (isMulti) {
				this.ctx.strokeStyle = colors.accentPurple; this.ctx.lineWidth = 1.5 / this.camera.scale;
				this.ctx.beginPath(); this.ctx.arc(x - 1, sy, 6, 0, Math.PI * 2); this.ctx.stroke();
			}
		}
		this.ctx.fillStyle = showRequiredHighlight ? colors.accentRed : colors.textSecondary;
		this.ctx.font = (10 * textScale) + 'px Arial'; this.ctx.textAlign = 'left'; this.ctx.textBaseline = 'middle';
		this.ctx.fillText(this._getSlotDisplayName(node, j, false), x + 10, sy);
		const hasEditBox = !isMulti && !inp.link && node.nativeInputs?.[j] !== undefined;
		if (hasEditBox) {
			const boxX = x + 10, boxY = sy + 6, boxW = 70, boxH = 12;
			this.ctx.fillStyle = 'rgba(0,0,0,0.4)';
			this.ctx.beginPath(); this.ctx.roundRect(boxX, boxY, boxW, boxH, 2); this.ctx.fill();
			this.ctx.strokeStyle = showRequiredHighlight ? colors.accentRed : 'rgba(255,255,255,0.15)';
			this.ctx.lineWidth = (showRequiredHighlight ? 1.5 : 1) / this.camera.scale; this.ctx.stroke();
			const val = node.nativeInputs[j].value;
			const isUnset = val === null || val === undefined;
			this.ctx.fillStyle = isUnset ? (showRequiredHighlight ? colors.accentRed : colors.textTertiary) : colors.textPrimary;
			this.ctx.font = (8 * textScale) + 'px Courier New'; this.ctx.textAlign = 'left'; this.ctx.textBaseline = 'middle';
			const displayVal = isUnset ? (node.nativeInputs[j].optional ? 'null' : 'required') : (val === '' ? '""' : String(val).substring(0, 10));
			this.ctx.fillText(displayVal, boxX + 4, boxY + boxH / 2);
		}
	}

	drawOutputSlot(node, j, x, y, w, worldMouse, colors, textScale, style, visIdx) {
		const out = node.outputs[j], sy = y + 38 + (visIdx !== undefined ? visIdx : j) * 25;
		const hasConnections = out.links.length > 0;
		const compat = this.isSlotCompatible(node, j, true);
		// Check if this is a base multi-field slot (no dot in name and tracked in multiOutputSlots)
		const isBaseMultiSlot = !out.name.includes('.') && Object.values(node.multiOutputSlots || {}).some(indices => indices.includes(j));
		let color = hasConnections ? colors.slotConnected : colors.slotOutput;
		if (this.connecting && (compat || (this.connecting.node === node && this.connecting.slot === j && this.connecting.isOutput))) {
			color = colors.accentPurple;
			if (!isBaseMultiSlot) {
				this.ctx.fillStyle = color; this.ctx.globalAlpha = 0.3;
				this.ctx.beginPath(); this.ctx.arc(x + w + 1, sy, 8, 0, Math.PI * 2); this.ctx.fill();
				this.ctx.globalAlpha = 1.0;
			}
		}
		// Skip drawing pin for base multi-field slots (plus button covers it)
		if (!isBaseMultiSlot) {
			this.ctx.fillStyle = color;
			this.ctx.beginPath(); this.ctx.arc(x + w + 1, sy, style.slotRadius || 4, 0, Math.PI * 2); this.ctx.fill();
		}
		this.ctx.fillStyle = colors.textSecondary;
		this.ctx.font = (10 * textScale) + 'px Arial'; this.ctx.textAlign = 'right'; this.ctx.textBaseline = 'middle';
		this.ctx.fillText(this._getSlotDisplayName(node, j, true), x + w - 10, sy);
	}

	drawConnecting(colors) {
		const node = this.connecting.node;
		const worldMouse = this.screenToWorld(this.mousePos[0], this.mousePos[1]);
		const x1 = this.connecting.isOutput ? node.pos[0] + node.size[0] : node.pos[0];
		const y1 = node.pos[1] + 38 + this._getVisibleSlotIndex(node, this.connecting.slot, this.connecting.isOutput) * 25;
		const controlOffset = Math.min(Math.abs(worldMouse[0] - x1) * 0.5, 400);
		const cx1 = x1 + (this.connecting.isOutput ? controlOffset : -controlOffset);
		const cx2 = worldMouse[0] + (this.connecting.isOutput ? -controlOffset : controlOffset);
		this.ctx.strokeStyle = colors.accentGreen;
		this.ctx.lineWidth = 2.5 / this.camera.scale;
		this.ctx.setLineDash([10 / this.camera.scale, 5 / this.camera.scale]);
		this.ctx.beginPath();
		this.ctx.moveTo(x1, y1);
		this.ctx.bezierCurveTo(cx1, y1, cx2, worldMouse[1], worldMouse[0], worldMouse[1]);
		this.ctx.stroke();
		this.ctx.setLineDash([]);
	}

	adjustColorBrightness(color, amount) {
		const hex = color.replace('#', ''), num = parseInt(hex, 16);
		const r = Math.max(0, Math.min(255, (num >> 16) + amount));
		const g = Math.max(0, Math.min(255, ((num >> 8) & 0x00FF) + amount));
		const b = Math.max(0, Math.min(255, (num & 0x0000FF) + amount));
		return '#' + ((r << 16) | (g << 8) | b).toString(16).padStart(6, '0');
	}

	// === EXPORT/IMPORT ===
	exportGraph() {
		const data = this.graph.serialize(true, this.camera);
		const jsonString = JSON.stringify(data, null, 2);
		const blob = new Blob([jsonString], { type: 'application/json' });
		const url = URL.createObjectURL(blob);
		const a = document.createElement('a');
		a.href = url;
		a.download = 'schemagraph-' + new Date().toISOString().slice(0, 10) + '.json';
		document.body.appendChild(a);
		a.click();
		document.body.removeChild(a);
		URL.revokeObjectURL(url);
		this.eventBus.emit('graph:exported', {});
	}

	exportConfig() {
		const schemas = Object.keys(this.graph.schemas);
		if (schemas.length === 0) { this.showError('No schemas registered'); return; }
		let targetSchema = schemas.find(s => this.graph.schemas[s].rootType) || schemas[0];
		const config = this.buildConfig(targetSchema);
		const jsonString = JSON.stringify(config, null, 2);
		const blob = new Blob([jsonString], { type: 'application/json' });
		const url = URL.createObjectURL(blob);
		const a = document.createElement('a');
		a.href = url;
		a.download = 'config-' + new Date().toISOString().slice(0, 10) + '.json';
		document.body.appendChild(a);
		a.click();
		document.body.removeChild(a);
		URL.revokeObjectURL(url);
		this.eventBus.emit('config:exported', {});
	}

	importGraph(data) {
		try {
			const graphData = typeof data === 'string' ? JSON.parse(data) : data;
			this.graph.deserialize(graphData);
			if (graphData.camera) {
				this.camera = { ...this.camera, ...graphData.camera };
			}
			this._refreshAllCompleteness();
			this.eventBus.emit('graph:imported', { data: graphData });
		} catch (e) {
			this.showError('Failed to import graph: ' + e.message);
		}
	}

	importConfig(config) {
		try {
			const configData = typeof config === 'string' ? JSON.parse(config) : config;
			const schemas = Object.keys(this.graph.schemas);
			if (schemas.length === 0) { this.showError('No schemas registered'); return; }
			const targetSchema = schemas.find(s => this.graph.schemas[s].rootType) || schemas[0];
			const schemaInfo = this.graph.schemas[targetSchema];
			if (!schemaInfo) { this.showError('Schema not found'); return; }
			// Clear existing nodes of this schema
			this.graph.nodes = this.graph.nodes.filter(n => n.schemaName !== targetSchema);
			this.graph.links = this.graph.links.filter(l => l.source.schemaName !== targetSchema && l.target.schemaName !== targetSchema);
			// Create nodes from config
			let yOffset = 0;
			for (const fieldName in configData) {
				const modelName = schemaInfo.fieldMapping?.fieldToModel?.[fieldName];
				if (!modelName) continue;
				const items = Array.isArray(configData[fieldName]) ? configData[fieldName] : [configData[fieldName]];
				for (const item of items) {
					const nodeType = `${targetSchema}.${modelName}`;
					const node = this.graph.createNode(nodeType, 100, yOffset);
					if (node && item) {
						node.fields = { ...item };
						node.onExecute();
					}
					yOffset += 150;
				}
			}
			this._refreshAllCompleteness();
			this.applyLayout('hierarchical');
			this.eventBus.emit('config:imported', { config: configData });
		} catch (e) {
			this.showError('Failed to import config: ' + e.message);
		}
	}

	buildConfig(schemaName) {
		const schemaInfo = this.graph.schemas[schemaName];
		const config = {}, nodesByType = {}, nodeToIndex = new Map();
		const fieldMapping = schemaInfo.fieldMapping;
		for (const node of this.graph.nodes) {
			if (node.schemaName !== schemaName) continue;
			if (!nodesByType[node.modelName]) nodesByType[node.modelName] = [];
			nodeToIndex.set(node, { modelName: node.modelName, index: nodesByType[node.modelName].length });
			nodesByType[node.modelName].push(node);
		}
		for (const modelName in nodesByType) {
			const fieldName = fieldMapping.modelToField[modelName];
			config[fieldName] = nodesByType[modelName].map(node => {
				node.onExecute();
				const data = node.outputs[0].value || {};
				return this.processNodeDataWithIndices(data, nodeToIndex, fieldMapping);
			});
		}
		return config;
	}

	processNodeDataWithIndices(data, nodeToIndex, fieldMapping) {
		const result = {};
		for (const key in data) {
			if (!data.hasOwnProperty(key)) continue;
			const value = data[key];
			result[key] = Array.isArray(value) ? value.map(v => this.valueToIndexOrData(v, nodeToIndex)) : this.valueToIndexOrData(value, nodeToIndex);
		}
		return result;
	}

	valueToIndexOrData(value, nodeToIndex) {
		if (value === null || value === undefined || typeof value !== 'object' || Array.isArray(value)) return value;
		for (const [node, info] of nodeToIndex.entries()) if (node.outputs?.[0]?.value === value) return info.index;
		if (typeof value === 'string' && ((value.startsWith('{') && value.endsWith('}')) || (value.startsWith('[') && value.endsWith(']')))) {
			try { return JSON.parse(value); } catch { return value; }
		}
		const processed = {};
		for (const k in value) if (value.hasOwnProperty(k)) processed[k] = this.valueToIndexOrData(value[k], nodeToIndex);
		return processed;
	}

	// === BUTTON STACK MANAGEMENT ===
	addNodeButton(node, stack, config) {
		if (!node || !config) return false;
		const button = {
			id: config.id || `btn_${Date.now()}`,
			label: config.label || '',
			icon: config.icon || '',
			callback: config.callback || (() => {}),
			enabled: config.enabled !== false,
			visible: config.visible !== false,
			style: { bg: config.bg || 'rgba(70,162,218,0.3)', bgHover: config.bgHover || 'rgba(70,162,218,0.5)', text: config.text || '#fff', border: config.border || 'rgba(70,162,218,0.6)' }
		};
		if (!node._buttonStacks) node._buttonStacks = { top: [], bottom: [] };
		const stackArr = node._buttonStacks[stack] || node._buttonStacks.bottom;
		const idx = stackArr.findIndex(b => b.id === button.id);
		if (idx !== -1) stackArr[idx] = button;
		else stackArr.push(button);
		this._recalculateNodeSize(node);
		this.draw();
		return button.id;
	}

	removeNodeButton(node, buttonId) {
		if (!node?._buttonStacks) return false;
		for (const stack of ['top', 'bottom']) {
			const idx = node._buttonStacks[stack].findIndex(b => b.id === buttonId);
			if (idx !== -1) { node._buttonStacks[stack].splice(idx, 1); this._recalculateNodeSize(node); this.draw(); return true; }
		}
		return false;
	}

	_recalculateNodeSize(node) {
		const baseHeight = 35, slotHeight = 25, stackHeight = 28;
		const maxSlots = Math.max(this._getVisibleSlotCount(node, false), this._getVisibleSlotCount(node, true), 1);
		let height = baseHeight + maxSlots * slotHeight;
		if (node._buttonStacks?.top?.length) height += stackHeight;
		if (node._buttonStacks?.bottom?.length) height += stackHeight;
		if (node._dropZone?.enabled) height += 10;
		node.size[1] = Math.max(80, height);
	}

	_getButtonStackLayout(node) {
		const x = node.pos[0], y = node.pos[1], w = node.size[0], h = node.size[1];
		const padding = 4, stackHeight = 24, headerHeight = 28;
		const hasTop = node._buttonStacks?.top?.length > 0;
		const hasBottom = node._buttonStacks?.bottom?.length > 0;
		return {
			top: hasTop ? { area: { x: x + padding, y: y + headerHeight, w: w - padding * 2, h: stackHeight }, buttons: this._layoutButtonsInStack(node._buttonStacks.top, x + padding, y + headerHeight, w - padding * 2, stackHeight) } : null,
			bottom: hasBottom ? { area: { x: x + padding, y: y + h - stackHeight - padding, w: w - padding * 2, h: stackHeight }, buttons: this._layoutButtonsInStack(node._buttonStacks.bottom, x + padding, y + h - stackHeight - padding, w - padding * 2, stackHeight) } : null,
			contentY: y + headerHeight + (hasTop ? stackHeight + 2 : 0)
		};
	}

	_layoutButtonsInStack(buttons, areaX, areaY, areaW, areaH) {
		if (!buttons?.length) return [];
		const padding = 3, gap = 4, btnHeight = areaH - padding * 2;
		const visibleBtns = buttons.filter(b => b.visible);
		const totalGaps = (visibleBtns.length - 1) * gap;
		const availableWidth = areaW - padding * 2 - totalGaps;
		const btnWidth = Math.min(70, availableWidth / visibleBtns.length);
		const totalWidth = visibleBtns.length * btnWidth + totalGaps;
		let startX = areaX + (areaW - totalWidth) / 2;
		return visibleBtns.map((btn, i) => ({ btn, bounds: { x: startX + i * (btnWidth + gap), y: areaY + padding, w: btnWidth, h: btnHeight } }));
	}

	_drawButtonStacks(node, colors) {
		const layout = this._getButtonStackLayout(node);
		if (!layout.top && !layout.bottom) return;
		const ctx = this.ctx, textScale = this.getTextScale(), style = this.drawingStyleManager.getStyle();
		for (const stackName of ['top', 'bottom']) {
			const stack = layout[stackName];
			if (!stack) continue;
			ctx.fillStyle = 'rgba(0,0,0,0.2)';
			ctx.beginPath(); ctx.roundRect(stack.area.x, stack.area.y, stack.area.w, stack.area.h, 4); ctx.fill();
			for (const { btn, bounds } of stack.buttons) {
				const isHovered = this._hoveredButton?.nodeId === node.id && this._hoveredButton?.buttonId === btn.id;
				ctx.fillStyle = isHovered ? btn.style.bgHover : btn.style.bg;
				ctx.beginPath(); ctx.roundRect(bounds.x, bounds.y, bounds.w, bounds.h, 3); ctx.fill();
				ctx.strokeStyle = btn.style.border; ctx.lineWidth = 1 / this.camera.scale; ctx.stroke();
				ctx.fillStyle = btn.enabled ? btn.style.text : 'rgba(255,255,255,0.3)';
				ctx.font = `${9 * textScale}px ${style.textFont}`; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
				ctx.fillText(btn.icon ? `${btn.icon} ${btn.label}` : btn.label, bounds.x + bounds.w / 2, bounds.y + bounds.h / 2);
			}
		}
	}

	// === DROP ZONE MANAGEMENT ===
	setNodeDropZone(node, config) {
		if (!node || !config) return false;
		node._dropZone = { accept: config.accept || '*', area: config.area || DropZoneArea.CONTENT, callback: config.callback || (() => {}), label: config.label || 'Drop file here', reject: config.reject || 'File type not accepted', enabled: config.enabled !== false };
		this._recalculateNodeSize(node);
		return true;
	}

	removeNodeDropZone(node) {
		if (!node) return false;
		delete node._dropZone;
		this._recalculateNodeSize(node);
		return true;
	}

	clearNodeDropZone(node) {
		return this.removeNodeDropZone(node);
	}

	_getDropZoneBounds(node) {
		const layout = this._getButtonStackLayout(node);
		const x = node.pos[0], y = node.pos[1], w = node.size[0], h = node.size[1];
		const hasBottom = node._buttonStacks?.bottom?.length > 0;
		if (node._dropZone?.area === DropZoneArea.FULL) return { x, y, w, h };
		const topY = layout.contentY;
		const bottomY = hasBottom ? layout.bottom.area.y : y + h;
		return { x: x + 4, y: topY, w: w - 8, h: bottomY - topY - 4 };
	}

	_findDropTargetNode(wx, wy) {
		for (const node of this.graph.nodes) {
			if (!node._dropZone?.enabled) continue;
			const b = this._getDropZoneBounds(node);
			if (wx >= b.x && wx <= b.x + b.w && wy >= b.y && wy <= b.y + b.h) return node;
		}
		return null;
	}

	_filterFilesByAccept(files, accept) {
		if (!accept || accept === '*' || accept === '*/*') return files;
		const acceptList = Array.isArray(accept) ? accept : accept.split(',').map(s => s.trim());
		return files.filter(file => {
			for (const acc of acceptList) {
				if (acc.startsWith('.') && file.name.toLowerCase().endsWith(acc.toLowerCase())) return true;
				if (acc.includes('/')) {
					if (acc.endsWith('/*') && file.type.startsWith(acc.slice(0, -1))) return true;
					if (file.type === acc) return true;
				}
			}
			return false;
		});
	}

	_drawDropZoneHighlight(node) {
		if (!node._dropZone) return;
		const ctx = this.ctx, bounds = this._getDropZoneBounds(node), textScale = this.getTextScale();
		const isActive = this._activeDropNode === node, isEnabled = node._dropZone.enabled;

		// Animated dash offset
		const time = performance.now() / 1000;
		const dashOffset = (time * 30) % 20;

		if (!isEnabled) {
			ctx.fillStyle = 'rgba(220, 96, 104, 0.08)';
			ctx.beginPath(); ctx.roundRect(bounds.x, bounds.y, bounds.w, bounds.h, 4); ctx.fill();
			ctx.strokeStyle = 'rgba(220, 96, 104, 0.3)'; ctx.lineWidth = 1 / this.camera.scale;
			ctx.setLineDash([4 / this.camera.scale, 4 / this.camera.scale]); ctx.stroke(); ctx.setLineDash([]);
			ctx.fillStyle = 'rgba(220, 96, 104, 0.6)'; ctx.font = `${9 * textScale}px sans-serif`;
			ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
			ctx.fillText(node._dropZone.label, bounds.x + bounds.w / 2, bounds.y + bounds.h / 2);
			return;
		}
		if (!isActive) return;

		// Semi-transparent fill
		ctx.fillStyle = 'rgba(146, 208, 80, 0.15)';
		ctx.beginPath(); ctx.roundRect(bounds.x, bounds.y, bounds.w, bounds.h, 4); ctx.fill();

		// Animated dashed border
		ctx.strokeStyle = '#92d050'; ctx.lineWidth = 2 / this.camera.scale;
		ctx.setLineDash([6 / this.camera.scale, 4 / this.camera.scale]);
		ctx.lineDashOffset = -dashOffset / this.camera.scale;
		ctx.stroke(); ctx.setLineDash([]);
		ctx.lineDashOffset = 0;

		// Label text
		ctx.fillStyle = '#92d050'; ctx.font = `bold ${11 * textScale}px sans-serif`;
		ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
		ctx.fillText(node._dropZone.label, bounds.x + bounds.w / 2, bounds.y + bounds.h / 2);

		// Request animation frame for continuous border animation
		if (!this._dropZoneAnimating) {
			this._dropZoneAnimating = true;
			requestAnimationFrame(() => {
				this._dropZoneAnimating = false;
				if (this._activeDropNode) this.draw();
			});
		}
	}

	// === CALLBACK REGISTRY ===
	registerCallback(id, fn) { if (typeof fn !== 'function') return false; this._callbackRegistry[id] = fn; return true; }
	unregisterCallback(id) { delete this._callbackRegistry[id]; }

	_resolveCallback(callbackId) {
		if (this._callbackRegistry[callbackId]) return this._callbackRegistry[callbackId];
		const builtins = {
			'file_input': (node) => {
				const input = document.createElement('input'); input.type = 'file';
				input.accept = node._dropZone?.accept || '*';
				input.onchange = (e) => { const files = Array.from(e.target.files); if (files.length && node._dropZone?.callback) node._dropZone.callback(node, files, e); };
				input.click();
			},
			'clear_data': (node) => { this.eventBus.emit('data:cleared', { nodeId: node.id }); this.draw(); }
		};
		return builtins[callbackId] || ((node, event, btn) => { this.eventBus.emit('node:buttonClicked', { nodeId: node.id, buttonId: btn?.id || callbackId, node, btn }); });
	}

	_resolveDropCallback(callbackId) {
		if (this._callbackRegistry[callbackId]) return this._callbackRegistry[callbackId];
		return (node, files) => { this.eventBus.emit('node:fileDrop', { nodeId: node.id, files, action: callbackId, node }); };
	}

	_setupFileDrop() {
		const canvas = this.canvas;
		canvas.addEventListener('dragover', (e) => {
			if (this.isLocked) return;
			const rect = canvas.getBoundingClientRect();
			const [wx, wy] = this.screenToWorld((e.clientX - rect.left) / rect.width * canvas.width, (e.clientY - rect.top) / rect.height * canvas.height);
			const node = this._findDropTargetNode(wx, wy);
			if (node && node._dropZone?.enabled) {
				e.preventDefault(); e.stopImmediatePropagation(); e.dataTransfer.dropEffect = 'copy';
				canvas.classList.remove('sg-file-drag-over');
				this._canvasDropHighlight = false;
				if (this._activeDropNode !== node) { this._activeDropNode = node; this.draw(); }
			} else if (this._canvasDropConfig.enabled && this.api.canvasDrop.getStatus().isReady) {
				// Canvas-level drop allowed
				e.preventDefault(); e.dataTransfer.dropEffect = 'copy';
				if (this._activeDropNode) { this._activeDropNode = null; }
				if (!this._canvasDropHighlight) { this._canvasDropHighlight = true; this.draw(); }
			} else {
				if (this._activeDropNode) { this._activeDropNode = null; this.draw(); }
				if (this._canvasDropHighlight) { this._canvasDropHighlight = false; this.draw(); }
			}
		}, true);
		canvas.addEventListener('dragleave', (e) => {
			const rect = canvas.getBoundingClientRect();
			if (e.clientX < rect.left || e.clientX > rect.right || e.clientY < rect.top || e.clientY > rect.bottom) {
				if (this._activeDropNode) { this._activeDropNode = null; this.draw(); }
				if (this._canvasDropHighlight) { this._canvasDropHighlight = false; this.draw(); }
			}
		});
		canvas.addEventListener('drop', (e) => {
			if (this.isLocked) return;
			const rect = canvas.getBoundingClientRect();
			const [wx, wy] = this.screenToWorld((e.clientX - rect.left) / rect.width * canvas.width, (e.clientY - rect.top) / rect.height * canvas.height);
			const node = this._findDropTargetNode(wx, wy);

			// Node-level drop (existing behavior)
			if (node && node._dropZone?.enabled) {
				e.preventDefault(); e.stopImmediatePropagation();
				canvas.classList.remove('sg-file-drag-over');
				const files = this._filterFilesByAccept(Array.from(e.dataTransfer.files), node._dropZone.accept);
				if (files.length && node._dropZone.callback) node._dropZone.callback(node, files, e);
				this._activeDropNode = null; this._canvasDropHighlight = false; this.draw(); return;
			}

			// Canvas-level drop (new behavior)
			if (this._canvasDropConfig.enabled && this.api.canvasDrop.getStatus().isReady) {
				e.preventDefault(); e.stopImmediatePropagation();
				const files = Array.from(e.dataTransfer.files);
				const filtered = this._filterCanvasDropFiles(files);
				if (filtered.length > 0) {
					this._handleCanvasFileDrop(filtered, wx, wy);
				}
			}

			this._activeDropNode = null; this._canvasDropHighlight = false; this.draw();
		}, true);
	}

	// ========================================================================
	// CANVAS DROP HELPERS
	// ========================================================================

	/**
	 * Filter files based on canvas drop accept configuration
	 * @param {File[]} files - Array of files to filter
	 * @returns {File[]} Filtered files
	 */
	_filterCanvasDropFiles(files) {
		const accept = this._canvasDropConfig.accept;
		if (!accept || accept === '*') return files;

		// Custom filter function
		if (typeof accept === 'function') {
			return files.filter(accept);
		}

		// MIME pattern matching
		const patterns = Array.isArray(accept) ? accept : accept.split(',').map(s => s.trim());
		return files.filter(file => {
			for (const pattern of patterns) {
				// Extension match (e.g., '.png', '.jpg')
				if (pattern.startsWith('.') && file.name.toLowerCase().endsWith(pattern.toLowerCase())) {
					return true;
				}
				// MIME type match
				if (pattern.includes('/')) {
					// Wildcard match (e.g., 'image/*')
					if (pattern.endsWith('/*')) {
						const prefix = pattern.slice(0, -1); // 'image/'
						if (file.type.startsWith(prefix)) return true;
					}
					// Exact match (e.g., 'image/png')
					if (file.type === pattern) return true;
				}
			}
			return false;
		});
	}

	/**
	 * Handle files dropped on the canvas (not on a specific node)
	 * @param {File[]} files - Array of files to process
	 * @param {number} wx - World X coordinate of drop location
	 * @param {number} wy - World Y coordinate of drop location
	 */
	async _handleCanvasFileDrop(files, wx, wy) {
		let offsetY = 0;
		for (const file of files) {
			const result = await this._createNodesFromFile(file, wx, wy + offsetY);
			if (result) {
				offsetY += result.totalHeight + 30;
			}
		}
		this.draw();
		this.eventBus.emit('canvasDrop:complete', { fileCount: files.length });
	}

	/**
	 * Create data and meta nodes from a dropped file
	 * @param {File} file - The dropped file
	 * @param {number} x - World X coordinate
	 * @param {number} y - World Y coordinate
	 * @returns {Object|null} Result with created nodes and totalHeight, or null on failure
	 */
	async _createNodesFromFile(file, x, y) {
		// Use custom callback if provided
		if (this._canvasDropCreationCallback) {
			try {
				return await this._canvasDropCreationCallback(file, x, y, this);
			} catch (err) {
				console.error('[SchemaGraph] Custom canvas drop callback error:', err);
				return null;
			}
		}

		// Use configured node types from schemaTypeRoles
		const roles = this._schemaTypeRoles;
		const dataNodeType = roles.dataTensor[0];
		const metaNodeType = roles.sourceMeta[0];
		const previewNodeType = roles.preview[0];

		if (!dataNodeType) {
			console.warn('[SchemaGraph] Canvas drop: no dataTensor type configured');
			return null;
		}

		// 1. Create meta node (if configured)
		let metaNode = null;
		if (metaNodeType && this.graph.nodeTypes[metaNodeType]) {
			metaNode = this.graph.createNode(metaNodeType);
			if (metaNode) {
				metaNode.pos = [x, y];
				this._populateSourceMeta(metaNode, file);
			}
		}

		const spacingX = 30;

		// 2. Create data node
		const dataNodeX = metaNode ? x + (metaNode.size?.[0] || 200) + spacingX : x;
		const dataNode = this.graph.createNode(dataNodeType);
		if (!dataNode) {
			console.warn('[SchemaGraph] Canvas drop: failed to create data node');
			return null;
		}
		dataNode.pos = [dataNodeX, y];

		// 3. Connect meta to data node (if both exist)
		if (metaNode && roles.metaInputSlot) {
			const metaOutputIdx = this._findOutputSlotByName(metaNode, 'get') ?? 0;
			const dataMetaInputIdx = this._findInputSlotByName(dataNode, roles.metaInputSlot);
			if (metaOutputIdx >= 0 && dataMetaInputIdx >= 0) {
				this.graph.connect(metaNode, metaOutputIdx, dataNode, dataMetaInputIdx);
			}
		}

		let previewNode = null;
		if (previewNodeType && this._features.autoPreview && this.graph.nodeTypes[previewNodeType]) {
			previewNode = this.graph.createNode(previewNodeType);
			if (previewNode) {
				// Find correct slot indices - 'get' is typically the last output on workflow nodes
				let dataOutputIdx = this._findOutputSlotByName(dataNode, 'get');
				if (dataOutputIdx < 0) {
					// Fallback: use last output slot (usually 'get' property)
					dataOutputIdx = (dataNode.outputs?.length || 1) - 1;
				}
				let previewInputIdx = this._findInputSlotByName(previewNode, 'input');
				if (previewInputIdx < 0) {
					// Fallback: try first non-extra input or just use index 1
					previewInputIdx = this._findInputSlotByName(previewNode, 'extra') >= 0 ? 1 : 0;
				}

				if (dataOutputIdx >= 0 && previewInputIdx >= 0) {
					this.graph.connect(dataNode, dataOutputIdx, previewNode, previewInputIdx);
				}
				const previewNodeX = dataNode.pos[0] + dataNode.size[0] + spacingX;
				previewNode.pos = [previewNodeX, y];
			} else {
				console.warn('[SchemaGraph] Canvas drop: failed to create preview node');
			}
		}

		// 4. Load file data into data node
		await this._loadFileIntoDataNode(file, dataNode);

		const height = Math.max(metaNode?.size?.[1] || 0, dataNode.size?.[1] || 100, previewNode?.size?.[1] || 0);

		this.eventBus.emit('canvasDrop:nodeCreated', {
			file: { name: file.name, type: file.type, size: file.size },
			metaNodeId: metaNode?.id,
			dataNodeId: dataNode.id
		});

		return { metaNode, dataNode, totalHeight: height };
	}

	/**
	 * Populate a SourceMeta node with file metadata
	 * @param {Object} node - The SourceMeta node
	 * @param {File} file - The file to extract metadata from
	 */
	_populateSourceMeta(node, file) {
		const setNativeInput = (slotName, value) => {
			const idx = this._findInputSlotByName(node, slotName);
			if (idx >= 0 && node.nativeInputs?.[idx]) {
				node.nativeInputs[idx].value = value;
			}
		};

		setNativeInput('name', file.name);
		setNativeInput('mime_type', file.type);
		setNativeInput('size', file.size);
		setNativeInput('source', 'file://' + file.name);

		// Detect format from extension
		const ext = file.name.split('.').pop()?.toLowerCase() || '';
		setNativeInput('format', ext);

		// For media files, try to extract additional metadata
		if (file.type.startsWith('audio/') || file.type.startsWith('video/')) {
			this._extractMediaMetadata(file, node);
		}
	}

	/**
	 * Extract media metadata (duration, etc.) from audio/video files
	 * @param {File} file - The media file
	 * @param {Object} node - The SourceMeta node to populate
	 */
	_extractMediaMetadata(file, node) {
		const url = URL.createObjectURL(file);
		const element = file.type.startsWith('audio/') ? new Audio() : document.createElement('video');
		element.preload = 'metadata';
		element.onloadedmetadata = () => {
			const setNativeInput = (slotName, value) => {
				const idx = this._findInputSlotByName(node, slotName);
				if (idx >= 0 && node.nativeInputs?.[idx]) {
					node.nativeInputs[idx].value = value;
				}
			};
			setNativeInput('duration', element.duration);
			URL.revokeObjectURL(url);
			this.draw();
		};
		element.src = url;
	}

	/**
	 * Load file content into a data node
	 * @param {File} file - The file to load
	 * @param {Object} node - The data node to populate
	 */
	async _loadFileIntoDataNode(file, node) {
		return new Promise((resolve) => {
			const reader = new FileReader();
			reader.onload = (e) => {
				if (!node.extra) node.extra = {};
				node.extra.fileData = e.target.result;
				node.extra.fileName = file.name;
				node.extra.mimeType = file.type;
				node.extra.fileSize = file.size;

				this.eventBus.emit('node:dataLoaded', {
					nodeId: node.id,
					file: { name: file.name, type: file.type, size: file.size },
					dataLength: typeof e.target.result === 'string' ? e.target.result.length : 0
				});
				resolve();
			};
			reader.onerror = () => {
				console.error('[SchemaGraph] Failed to read file:', file.name);
				resolve();
			};

			// Read as appropriate format based on type
			if (file.type.startsWith('text/') || file.type === 'application/json') {
				reader.readAsText(file);
			} else {
				reader.readAsDataURL(file);
			}
		});
	}

	/**
	 * Find an input slot index by name
	 * @param {Object} node - The node to search
	 * @param {string} slotName - The slot name to find
	 * @returns {number} Slot index or -1 if not found
	 */
	_findInputSlotByName(node, slotName) {
		if (!node?.inputs) return -1;
		for (let i = 0; i < node.inputs.length; i++) {
			const name = node.inputMeta?.[i]?.name || node.inputs[i]?.name || '';
			if (name === slotName || name.toLowerCase() === slotName.toLowerCase()) {
				return i;
			}
		}
		return -1;
	}

	/**
	 * Find an output slot index by name
	 * @param {Object} node - The node to search
	 * @param {string} slotName - The slot name to find
	 * @returns {number} Slot index or -1 if not found
	 */
	_findOutputSlotByName(node, slotName) {
		if (!node?.outputs) return -1;
		for (let i = 0; i < node.outputs.length; i++) {
			const name = node.outputMeta?.[i]?.name || node.outputs[i]?.name || '';
			if (name === slotName || name.toLowerCase() === slotName.toLowerCase()) {
				return i;
			}
		}
		return -1;
	}

	// ========================================================================
	// PREVIEWFLOW NODE RENDERING
	// ========================================================================

	/**
	 * Check if a node is a PreviewFlow node
	 * @param {Object} node - The node to check
	 * @returns {boolean} True if this is a PreviewFlow node
	 */
	/**
	 * Check if a node matches any of the configured type names
	 * @param {Object} node - The node to check
	 * @param {string[]} typeNames - Array of full type names to match
	 * @returns {boolean} True if node matches any type
	 */
	_nodeMatchesTypes(node, typeNames) {
		if (!node || !typeNames || typeNames.length === 0) return false;
		const nodeType = node.type || `${node.schemaName}.${node.modelName}`;
		for (const typeName of typeNames) {
			if (nodeType === typeName) return true;
			if (node.modelName === typeName.split('.').pop()) return true;
			if (node.workflowType === typeName.split('.').pop()?.toLowerCase()) return true;
		}
		return false;
	}

	_getPairedWorkflowType(workflowType) {
		return this._setTypes[workflowType] || null;
	}

	_findFullNodeType(workflowType) {
		for (const [schemaName, schema] of Object.entries(this.graph.schemas)) {
			if (!schema.defaults) continue;
			for (const [modelName, defaults] of Object.entries(schema.defaults)) {
				if (defaults.type === workflowType) return `${schemaName}.${modelName}`;
			}
		}
		return null;
	}

	_maybeCreatePairedNode(nodeId) {
		const node = this.graph.getNodeById(nodeId);
		if (!node?.workflowType) return;
		const partnerWorkflowType = this._getPairedWorkflowType(node.workflowType);
		if (!partnerWorkflowType) return;
		const partnerFullType = this._findFullNodeType(partnerWorkflowType);
		if (!partnerFullType) return;

		this._creatingPairedNode = true;
		try {
			const partner = this.graph.createNode(partnerFullType);
			partner.pos = [node.pos[0] + node.size[0] + 80, node.pos[1]];

			// Create loop-back edge: from end's output to start's input
			// Determine which is start and which is end
			const startNode = this._isLoopStartType(node.workflowType) ? node : partner;
			const endNode = this._isLoopStartType(node.workflowType) ? partner : node;

			// Find 'output' slot on end node and 'input' slot on start node
			let endOutIdx = -1;
			for (let i = 0; i < endNode.outputs.length; i++) {
				const name = endNode.outputMeta?.[i]?.name || endNode.outputs[i]?.name;
				if (name === 'output') { endOutIdx = i; break; }
			}
			let startInIdx = -1;
			for (let i = 0; i < startNode.inputs.length; i++) {
				const name = startNode.inputMeta?.[i]?.name || startNode.inputs[i]?.name;
				if (name === 'input') { startInIdx = i; break; }
			}
			if (endOutIdx >= 0 && startInIdx >= 0) {
				const prevLink = startNode.inputs[startInIdx].link;
				const link = this.graph.connect(endNode, endOutIdx, startNode, startInIdx);
				if (link) {
					link.loop = true;
					// Loop-back edges don't occupy the target input slot so normal connections can coexist
					startNode.inputs[startInIdx].link = prevLink;
				}
			}
		} finally {
			this._creatingPairedNode = false;
		}
	}

	_isLoopStartType(workflowType) {
		// A start type has a partner that ends with the same suffix but 'end' instead of 'start'
		return workflowType.includes('start');
	}

	_findPairedNode(node) {
		if (!node?.workflowType) return null;
		const partnerType = this._getPairedWorkflowType(node.workflowType);
		if (!partnerType) return null;
		// Find partner via loop-back edge
		for (const link of Object.values(this.graph.links)) {
			if (!link.loop) continue;
			if (link.origin_id === node.id) {
				const target = this.graph.getNodeById(link.target_id);
				if (target?.workflowType === partnerType) return target;
			}
			if (link.target_id === node.id) {
				const origin = this.graph.getNodeById(link.origin_id);
				if (origin?.workflowType === partnerType) return origin;
			}
		}
		return null;
	}

	_isPreviewFlowNode(node) {
		if (!node) return false;
		// Check configured types first
		if (this._schemaTypeRoles.preview.length > 0) {
			return this._nodeMatchesTypes(node, this._schemaTypeRoles.preview);
		}
		// Fallback to pattern matching
		return node.workflowType === 'preview_flow' ||
			   node.modelName === 'PreviewFlow' ||
			   node.type?.includes('PreviewFlow') ||
			   (node.title?.toLowerCase().includes('preview') && node.isWorkflowNode);
	}

	/**
	 * Preserve preview node links by connecting source to targets directly
	 * Called before removing a preview node when preservePreviewLinks feature is enabled
	 * Uses previewSlotMap from schemaTypeRoles to determine which input->output pairs to preserve
	 * @param {Object} node - The preview node being removed
	 */
	_preservePreviewNodeLinks(node) {
		if (!node) return;

		// Get the configured slot map (e.g., { 'input': 'get', 'data': 'output' })
		const slotMap = this._schemaTypeRoles.previewSlotMap;
		if (!slotMap || Object.keys(slotMap).length === 0) return;

		// Process each configured input->output mapping
		for (const [inputSlotName, outputSlotName] of Object.entries(slotMap)) {
			// Find input slot index by name
			const inputIdx = this._findInputSlotByName(node, inputSlotName);
			if (inputIdx === null || inputIdx === undefined) continue;

			// Find output slot index by name
			const outputIdx = this._findOutputSlotByName(node, outputSlotName);
			if (outputIdx === null || outputIdx === undefined) continue;

			// Get incoming links for this input (handle both single and multi-input)
			const inLinkIds = node.multiInputs?.[inputIdx]?.links ||
				(node.inputs[inputIdx]?.link ? [node.inputs[inputIdx].link] : []);

			// Get outgoing links for this output
			const outLinkIds = node.outputs?.[outputIdx]?.links || [];

			// Create bypass links: source -> target (skipping preview node)
			for (const inLinkId of inLinkIds) {
				const inLink = this.graph.links[inLinkId];
				if (!inLink) continue;

				const src = this.graph.getNodeById(inLink.origin_id);
				if (!src) continue;

				for (const outLinkId of outLinkIds) {
					const outLink = this.graph.links[outLinkId];
					if (!outLink) continue;

					const tgt = this.graph.getNodeById(outLink.target_id);
					if (!tgt) continue;

					// Create direct link bypassing the preview node
					this.graph.addLink(src.id, inLink.origin_slot, tgt.id, outLink.target_slot, inLink.type);
				}
			}
		}
	}

	/**
	 * Check if a node is a ToolCall type
	 * @param {Object} node - The node to check
	 * @returns {boolean} True if this is a tool call node
	 */
	_isToolCallNode(node) {
		if (!node) return false;
		// Check configured types first
		if (this._schemaTypeRoles.toolCall.length > 0) {
			return this._nodeMatchesTypes(node, this._schemaTypeRoles.toolCall);
		}
		// Fallback to pattern matching
		return node.workflowType === 'tool_call' ||
			   node.modelName === 'ToolCall' ||
			   node.type?.includes('ToolCall');
	}

	/**
	 * Check if a node is a DataTensor type
	 * @param {Object} node - The node to check
	 * @returns {boolean} True if this is a data tensor node
	 */
	_isDataTensorNode(node) {
		if (!node) return false;
		// Check configured types first
		if (this._schemaTypeRoles.dataTensor.length > 0) {
			return this._nodeMatchesTypes(node, this._schemaTypeRoles.dataTensor);
		}
		// Fallback to pattern matching
		return node.modelName === 'DataTensor' || node.modelName === 'TensorType' ||
			   node.workflowType === 'data_tensor' || node.workflowType === 'tensor_type' ||
			   node.title?.includes('Tensor');
	}

	/**
	 * Check if a node is a SourceMeta type
	 * @param {Object} node - The node to check
	 * @returns {boolean} True if this is a source meta node
	 */
	_isSourceMetaNode(node) {
		if (!node) return false;
		// Check configured types first
		if (this._schemaTypeRoles.sourceMeta.length > 0) {
			return this._nodeMatchesTypes(node, this._schemaTypeRoles.sourceMeta);
		}
		// Fallback to pattern matching
		return node.modelName === 'SourceMeta' ||
			   node.workflowType === 'source_meta' ||
			   node.title?.includes('Meta');
	}

	/**
	 * Check if a node is a workflow Start node
	 * @param {Object} node - The node to check
	 * @returns {boolean} True if this is a Start node
	 */
	_isStartNode(node) {
		if (!node) return false;
		// Check configured types first
		if (this._schemaTypeRoles.startNode.length > 0) {
			return this._nodeMatchesTypes(node, this._schemaTypeRoles.startNode);
		}
		// Fallback to pattern matching
		return node.modelName === 'StartFlow' ||
			   node.workflowType === 'start_flow' ||
			   node.type === 'start_flow';
	}

	/**
	 * Check if a node is a workflow End node
	 * @param {Object} node - The node to check
	 * @returns {boolean} True if this is an End node
	 */
	_isEndNode(node) {
		if (!node) return false;
		// Check configured types first
		if (this._schemaTypeRoles.endNode.length > 0) {
			return this._nodeMatchesTypes(node, this._schemaTypeRoles.endNode);
		}
		// Fallback to pattern matching
		return node.modelName === 'EndFlow' ||
			   node.workflowType === 'end_flow' ||
			   node.type === 'end_flow';
	}

	// ========================================================================
	// WORKFLOW VALIDATION
	// ========================================================================

	/**
	 * Count Start nodes in the current graph
	 * @returns {number} Number of Start nodes
	 */
	_countStartNodes() {
		return this.graph.nodes.filter(n => this._isStartNode(n)).length;
	}

	/**
	 * Count End nodes in the current graph
	 * @returns {number} Number of End nodes
	 */
	_countEndNodes() {
		return this.graph.nodes.filter(n => this._isEndNode(n)).length;
	}

	/**
	 * Get Start node(s) in the graph
	 * @returns {Array} Array of Start nodes
	 */
	_getStartNodes() {
		return this.graph.nodes.filter(n => this._isStartNode(n));
	}

	/**
	 * Get End node(s) in the graph
	 * @returns {Array} Array of End nodes
	 */
	_getEndNodes() {
		return this.graph.nodes.filter(n => this._isEndNode(n));
	}

	/**
	 * Check if a node type can be created (validates Start/End constraints)
	 * @param {string} nodeType - The node type to check
	 * @returns {{allowed: boolean, reason: string|null}}
	 */
	_canCreateNodeType(nodeType) {
		// Extract model name from full type (e.g., "Workflow.StartFlow" -> "StartFlow")
		const modelName = nodeType.includes('.') ? nodeType.split('.').pop() : nodeType;

		// Check if this would be a Start node (exact match only — don't match LoopStartFlow etc.)
		const isStartType = this._schemaTypeRoles.startNode.some(t =>
			nodeType === t || nodeType.endsWith('.' + t.split('.').pop())
		) || (this._schemaTypeRoles.startNode.length === 0 && (
			modelName === 'StartFlow' || nodeType === 'start_flow'));

		if (isStartType && this._countStartNodes() >= 1) {
			return { allowed: false, reason: 'Only one Start node allowed per workflow' };
		}

		// Check if this would be an End node (exact match only — don't match LoopEndFlow etc.)
		const isEndType = this._schemaTypeRoles.endNode.some(t =>
			nodeType === t || nodeType.endsWith('.' + t.split('.').pop())
		) || (this._schemaTypeRoles.endNode.length === 0 && (
			modelName === 'EndFlow' || nodeType === 'end_flow'));

		if (isEndType && this._countEndNodes() >= 1) {
			return { allowed: false, reason: 'Only one End node allowed per workflow' };
		}

		return { allowed: true, reason: null };
	}

	/**
	 * Check if there's a path from Start to End node using BFS
	 * @returns {{valid: boolean, reason: string|null, path: number[]|null}}
	 */
	_validateStartToEndPath() {
		const startNodes = this._getStartNodes();
		const endNodes = this._getEndNodes();

		// Check for Start node
		if (startNodes.length === 0) {
			return { valid: false, reason: 'No Start node found', path: null };
		}
		if (startNodes.length > 1) {
			return { valid: false, reason: 'Multiple Start nodes found (only one allowed)', path: null };
		}

		// Check for End node
		if (endNodes.length === 0) {
			return { valid: false, reason: 'No End node found', path: null };
		}
		if (endNodes.length > 1) {
			return { valid: false, reason: 'Multiple End nodes found (only one allowed)', path: null };
		}

		const startNode = startNodes[0];
		const endNode = endNodes[0];

		// Build adjacency list from links
		const adjacency = new Map();
		for (const node of this.graph.nodes) {
			adjacency.set(node.id, []);
		}

		for (const linkId in this.graph.links) {
			const link = this.graph.links[linkId];
			const sourceId = link.origin_id;
			const targetId = link.target_id;
			if (adjacency.has(sourceId)) {
				adjacency.get(sourceId).push(targetId);
			}
		}

		// BFS from Start to End
		const visited = new Set();
		const queue = [{ nodeId: startNode.id, path: [startNode.id] }];
		visited.add(startNode.id);

		while (queue.length > 0) {
			const { nodeId, path } = queue.shift();

			if (nodeId === endNode.id) {
				return { valid: true, reason: null, path };
			}

			const neighbors = adjacency.get(nodeId) || [];
			for (const neighborId of neighbors) {
				if (!visited.has(neighborId)) {
					visited.add(neighborId);
					queue.push({ nodeId: neighborId, path: [...path, neighborId] });
				}
			}
		}

		return { valid: false, reason: 'No path exists from Start to End node', path: null };
	}

	/**
	 * Full workflow validation
	 * @returns {{valid: boolean, errors: string[], warnings: string[]}}
	 */
	validateWorkflow() {
		const errors = [];
		const warnings = [];

		// Check Start node
		const startCount = this._countStartNodes();
		if (startCount === 0) {
			errors.push('Workflow requires a Start node');
		} else if (startCount > 1) {
			errors.push('Workflow can only have one Start node');
		}

		// Check End node
		const endCount = this._countEndNodes();
		if (endCount === 0) {
			errors.push('Workflow requires an End node');
		} else if (endCount > 1) {
			errors.push('Workflow can only have one End node');
		}

		// Check path if both nodes exist
		if (startCount === 1 && endCount === 1) {
			const pathResult = this._validateStartToEndPath();
			if (!pathResult.valid) {
				errors.push(pathResult.reason);
			}
		}

		// Check for disconnected nodes (warning, not error)
		const connectedNodes = new Set();
		for (const linkId in this.graph.links) {
			const link = this.graph.links[linkId];
			connectedNodes.add(link.origin_id);
			connectedNodes.add(link.target_id);
		}

		const flowNodes = this.graph.nodes.filter(n => n.isWorkflowNode || n.isFlowType);
		const disconnected = flowNodes.filter(n => !connectedNodes.has(n.id));
		if (disconnected.length > 0) {
			warnings.push(`${disconnected.length} workflow node(s) are not connected`);
		}

		return {
			valid: errors.length === 0,
			errors,
			warnings
		};
	}

	/**
	 * Draw a PreviewFlow node with live data preview
	 * @param {Object} node - The PreviewFlow node
	 * @param {Object} colors - Theme colors
	 */
	_drawPreviewFlowNode(node, colors) {
		const style = this.drawingStyleManager.getStyle();
		const textScale = this.getTextScale();
		const x = node.pos[0], y = node.pos[1], w = node.size[0], h = node.size[1];
		const radius = style.nodeCornerRadius;
		const isSelected = this.isNodeSelected(node);
		const isPreviewSelected = this.previewSelection.has(node);

		// Calculate flash intensity (0 to 1) for animation
		let flashIntensity = 0;
		if (this._features.previewFlash && node._isFlashing && node._flashProgress !== undefined) {
			// Quadratic ease-out for smooth fade
			flashIntensity = 1 - (node._flashProgress * node._flashProgress);
		}

		// Flash colors
		const flashColor = { r: 146, g: 208, b: 80 };  // Green flash
		const baseColor = { r: 74, g: 144, b: 217 };   // Blue base (accentBlue)

		// Interpolate header color based on flash intensity
		const currentColor = {
			r: Math.round(baseColor.r + (flashColor.r - baseColor.r) * flashIntensity),
			g: Math.round(baseColor.g + (flashColor.g - baseColor.g) * flashIntensity),
			b: Math.round(baseColor.b + (flashColor.b - baseColor.b) * flashIntensity)
		};
		const headerColorStr = `rgb(${currentColor.r}, ${currentColor.g}, ${currentColor.b})`;

		// Ensure minimum size based on preview mode
		const isExpanded = node.extra?.previewExpanded ?? false;
		const minW = isExpanded ? 280 : 200;
		const minH = isExpanded ? 180 : 120;
		if (node.size[0] < minW) node.size[0] = minW;
		if (node.size[1] < minH) node.size[1] = minH;

		// Draw base node body
		const bodyColor = isSelected ? colors.nodeBgSelected : (isPreviewSelected ? this.adjustColorBrightness(colors.nodeBg, 20) : colors.nodeBg);

		// Enhanced shadow/glow during flash
		if (style.nodeShadowBlur > 0 || flashIntensity > 0) {
			this.ctx.shadowColor = flashIntensity > 0
				? `rgba(${flashColor.r}, ${flashColor.g}, ${flashColor.b}, ${0.8 * flashIntensity})`
				: colors.nodeShadow;
			this.ctx.shadowBlur = Math.max(style.nodeShadowBlur, flashIntensity * 25) / this.camera.scale;
			this.ctx.shadowOffsetY = flashIntensity > 0 ? 0 : style.nodeShadowOffset / this.camera.scale;
		}

		this.ctx.fillStyle = style.currentStyle === 'wireframe' ? 'transparent' : bodyColor;
		this.ctx.beginPath();
		if (radius > 0) {
			this.ctx.moveTo(x + radius, y); this.ctx.lineTo(x + w - radius, y);
			this.ctx.quadraticCurveTo(x + w, y, x + w, y + radius);
			this.ctx.lineTo(x + w, y + h - radius);
			this.ctx.quadraticCurveTo(x + w, y + h, x + w - radius, y + h);
			this.ctx.lineTo(x + radius, y + h);
			this.ctx.quadraticCurveTo(x, y + h, x, y + h - radius);
			this.ctx.lineTo(x, y + radius);
			this.ctx.quadraticCurveTo(x, y, x + radius, y);
			this.ctx.closePath();
		} else { this.ctx.rect(x, y, w, h); }
		if (style.currentStyle !== 'wireframe') this.ctx.fill();

		this.ctx.shadowBlur = 0; this.ctx.shadowOffsetY = 0;
		// Border color affected by flash
		this.ctx.strokeStyle = flashIntensity > 0 ? headerColorStr : (isSelected ? colors.borderHighlight : colors.borderColor);
		this.ctx.lineWidth = ((isSelected ? 2 : 1) + flashIntensity * 1.5) / this.camera.scale;
		this.ctx.stroke();

		// Draw header with preview icon (color affected by flash)
		const headerColor = flashIntensity > 0 ? headerColorStr : (colors.accentBlue || '#4a90d9');
		this.ctx.fillStyle = style.currentStyle === 'wireframe' ? 'transparent' : headerColor;
		this.ctx.beginPath();
		if (radius > 0) {
			this.ctx.moveTo(x + radius, y); this.ctx.lineTo(x + w - radius, y);
			this.ctx.quadraticCurveTo(x + w, y, x + w, y + radius);
			this.ctx.lineTo(x + w, y + 26); this.ctx.lineTo(x, y + 26);
			this.ctx.lineTo(x, y + radius);
			this.ctx.quadraticCurveTo(x, y, x + radius, y);
		} else { this.ctx.rect(x, y, w, 26); }
		this.ctx.closePath();
		if (style.currentStyle !== 'wireframe') this.ctx.fill();

		// Header title - use displayTitle from extra.name if available
		this.ctx.fillStyle = colors.textPrimary;
		this.ctx.font = (11 * textScale) + 'px ' + style.textFont;
		this.ctx.textBaseline = 'middle'; this.ctx.textAlign = 'left';
		const modeIcon = isExpanded ? '▼' : '▶';
		const previewTitle = node.displayTitle || 'Preview';
		this.ctx.fillText(`${modeIcon} ${previewTitle}`, x + 8, y + 13);

		// Draw input/output slots
		const worldMouse = this.screenToWorld(this.mousePos[0], this.mousePos[1]);
		{ let vi = 0; for (let j = 0; j < node.inputs.length; j++) { if (!this._isFieldHidden(node, j, false)) this.drawInputSlot(node, j, x, y, w, worldMouse, colors, textScale, style, vi++); } }
		{ let vi = 0; for (let j = 0; j < node.outputs.length; j++) { if (!this._isFieldHidden(node, j, true)) this.drawOutputSlot(node, j, x, y, w, worldMouse, colors, textScale, style, vi++); } }

		// Calculate preview content area
		const slotHeight = Math.max(this._getVisibleSlotCount(node, false), this._getVisibleSlotCount(node, true)) * 25 + 10;
		const contentY = y + 30 + slotHeight;
		const contentH = h - 36 - slotHeight;
		const contentX = x + 8;
		const contentW = w - 16;

		// Store preview bounds for double-click detection
		node._previewBounds = { x: contentX, y: contentY, w: contentW, h: contentH };

		// Get and draw preview data
		const previewData = this._getPreviewData(node);
		if (previewData && contentH > 10) {
			if (isExpanded) {
				this._drawPreviewFull(node, previewData, contentX, contentY, contentW, contentH, colors);
			} else {
				this._drawPreviewSimple(node, previewData, contentX, contentY, contentW, contentH, colors);
			}
		} else if (contentH > 10) {
			this._drawPreviewPlaceholder(contentX, contentY, contentW, contentH, colors);
		}

		// Draw button stacks if any
		this._drawButtonStacks(node, colors);
	}

	/**
	 * Trigger flash animation on a preview node
	 * Called when preview data is updated
	 * @param {Object} node - The preview node to flash
	 */
	triggerPreviewFlash(node) {
		if (!node || !this._features.previewFlash) return;
		if (!this._isPreviewFlowNode(node)) return;

		// Start flash animation (using same property names as numel-workflow-ui.js)
		node._flashStart = performance.now();
		node._flashDuration = 600; // ms
		node._isFlashing = true;
		node._flashProgress = 0;

		// Start animation if not already running
		if (!this._previewFlashAnimating) {
			this._previewFlashAnimating = true;
			this._runPreviewFlashAnimation();
		}
	}

	/**
	 * Run the preview flash animation loop
	 * @private
	 */
	_runPreviewFlashAnimation() {
		const self = this;

		const animate = () => {
			const now = performance.now();
			let hasActiveFlash = false;

			// Update all flashing nodes
			for (const node of self.graph.nodes) {
				if (!node._isFlashing) continue;

				const elapsed = now - node._flashStart;
				const duration = node._flashDuration || 600;

				if (elapsed < duration) {
					node._flashProgress = elapsed / duration;
					hasActiveFlash = true;
				} else {
					node._isFlashing = false;
					node._flashProgress = 0;
				}
			}

			// Redraw and continue animation if needed
			self.draw();

			if (hasActiveFlash) {
				requestAnimationFrame(animate);
			} else {
				self._previewFlashAnimating = false;
			}
		};

		requestAnimationFrame(animate);
	}

	/**
	 * Get preview data from connected source
	 * @param {Object} node - The PreviewFlow node
	 * @returns {Object|null} Preview data or null
	 */
	_getPreviewData(node) {
		// 1. Find the 'input' slot by name (not at fixed index due to inheritance)
		const inputSlotIdx = this._findInputSlotByName(node, 'input');
		if (inputSlotIdx >= 0) {
			const inputSlot = node.inputs?.[inputSlotIdx];
			if (inputSlot?.link) {
				const link = this.graph.links[inputSlot.link];
				if (link) {
					const sourceNode = this.graph.getNodeById(link.origin_id);
					if (sourceNode) {
						return this._extractPreviewDataFromNode(sourceNode, link.origin_slot);
					}
				}
			}
		}

		// 2. Fallback: check all input slots for any connection
		for (let i = 0; i < (node.inputs?.length || 0); i++) {
			const inputSlot = node.inputs[i];
			if (inputSlot?.link) {
				const link = this.graph.links[inputSlot.link];
				if (link) {
					const sourceNode = this.graph.getNodeById(link.origin_id);
					if (sourceNode) {
						return this._extractPreviewDataFromNode(sourceNode, link.origin_slot);
					}
				}
			}
		}

		// 3. Check node's directly cached previewData (set by workflow execution)
		if (node.previewData !== undefined && node.previewData !== null) {
			return {
				type: node.previewType || this._guessTypeFromData(node.previewData),
				value: node.previewData,
				source: 'cached'
			};
		}

		// 4. Check node.extra.previewData
		if (node.extra?.previewData) {
			return node.extra.previewData;
		}

		return null;
	}

	/**
	 * Extract preview data from a source node
	 * @param {Object} sourceNode - The source node
	 * @param {number} outputSlot - The output slot index
	 * @param {Set} visited - Set of visited node IDs to prevent cycles
	 * @returns {Object} Preview data object
	 */
	_extractPreviewDataFromNode(sourceNode, outputSlot, visited = new Set()) {
		// Prevent infinite loops
		if (visited.has(sourceNode.id)) {
			return { type: 'unknown', value: null, source: 'cycle' };
		}
		visited.add(sourceNode.id);

		// For PreviewFlow nodes, traverse upstream to find the actual data source
		if (this._isPreviewFlowNode(sourceNode)) {
			// Check if this preview has cached data
			if (sourceNode.previewData !== undefined && sourceNode.previewData !== null) {
				return {
					type: sourceNode.previewType || this._guessTypeFromData(sourceNode.previewData),
					value: sourceNode.previewData,
					source: 'preview_cached'
				};
			}
			// Traverse upstream through the preview's input
			const upstreamData = this._traverseUpstreamForData(sourceNode, visited);
			if (upstreamData) return upstreamData;
		}

		// For native nodes
		if (sourceNode.isNative) {
			return {
				type: this._detectNativeType(sourceNode),
				value: sourceNode.properties?.value,
				source: 'native'
			};
		}

		// For DataTensor/TensorType nodes
		if (this._isDataTensorNode(sourceNode)) {
			return this._extractDataTensorPreview(sourceNode);
		}

		// For other workflow nodes, try to get stored data
		if (sourceNode.extra?.fileData) {
			return {
				type: this._guessTypeFromMime(sourceNode.extra.mimeType),
				value: sourceNode.extra.fileData,
				meta: {
					name: sourceNode.extra.fileName,
					mimeType: sourceNode.extra.mimeType,
					size: sourceNode.extra.fileSize
				},
				source: 'file'
			};
		}

		// Try to get output data (runtime value)
		const outputData = sourceNode.outputs?.[outputSlot]?.value;
		if (outputData !== undefined) {
			return {
				type: this._guessTypeFromData(outputData),
				value: outputData,
				source: 'workflow'
			};
		}

		// Try to get output default value (from schema)
		const outputDefault = sourceNode.outputs?.[outputSlot]?.defaultValue;
		if (outputDefault !== undefined) {
			return {
				type: this._guessTypeFromData(outputDefault),
				value: outputDefault,
				source: 'default'
			};
		}

		// Return basic info about the node
		return {
			type: 'node',
			value: sourceNode.title || sourceNode.modelName,
			source: 'reference'
		};
	}

	/**
	 * Traverse upstream from a node to find the actual data source
	 * Follows connections through PreviewFlow and other pass-through nodes
	 * @param {Object} node - Starting node
	 * @param {Set} visited - Set of visited node IDs to prevent cycles
	 * @returns {Object|null} Preview data or null
	 */
	_traverseUpstreamForData(node, visited = new Set()) {
		if (visited.has(node.id)) return null;
		visited.add(node.id);

		// Find connected input - prefer 'input' slot, then check all slots
		let connectedInput = null;
		let connectedLink = null;

		// Try to find the 'input' slot first
		const inputSlotIdx = this._findInputSlotByName(node, 'input');
		if (inputSlotIdx >= 0 && node.inputs?.[inputSlotIdx]?.link) {
			connectedInput = node.inputs[inputSlotIdx];
			connectedLink = this.graph.links[connectedInput.link];
		}

		// Fallback: find any connected input
		if (!connectedLink) {
			for (let i = 0; i < (node.inputs?.length || 0); i++) {
				if (node.inputs[i]?.link) {
					connectedInput = node.inputs[i];
					connectedLink = this.graph.links[connectedInput.link];
					break;
				}
			}
		}

		if (!connectedLink) return null;

		const upstreamNode = this.graph.getNodeById(connectedLink.origin_id);
		if (!upstreamNode) return null;

		// Recursively extract data from upstream node
		return this._extractPreviewDataFromNode(upstreamNode, connectedLink.origin_slot, visited);
	}

	/**
	 * Extract preview data from a DataTensor node
	 * @param {Object} dataTensorNode - The DataTensor node
	 * @returns {Object} Preview data object
	 */
	_extractDataTensorPreview(dataTensorNode) {
		const result = {
			type: 'unknown',
			value: null,
			meta: null,
			source: 'data_tensor'
		};

		// Get meta from connected SourceMeta
		const metaInputIdx = this._findInputSlotByName(dataTensorNode, 'meta');
		if (metaInputIdx >= 0) {
			const metaLink = dataTensorNode.inputs[metaInputIdx]?.link;
			if (metaLink) {
				const link = this.graph.links[metaLink];
				const sourceMetaNode = this.graph.getNodeById(link?.origin_id);
				if (sourceMetaNode) {
					result.meta = this._extractSourceMetaInfo(sourceMetaNode);
					result.type = this._detectTypeFromMeta(result.meta);
				}
			}
		}

		// Get data
		result.value = dataTensorNode.extra?.fileData ||
					   dataTensorNode.properties?.data;

		// If no meta type, guess from data
		if (result.type === 'unknown' && result.value) {
			result.type = this._guessTypeFromData(result.value);
		}

		return result;
	}

	/**
	 * Extract metadata info from a SourceMeta node
	 * @param {Object} sourceMetaNode - The SourceMeta node
	 * @returns {Object} Metadata info
	 */
	_extractSourceMetaInfo(sourceMetaNode) {
		const getInputValue = (slotName) => {
			const idx = this._findInputSlotByName(sourceMetaNode, slotName);
			if (idx >= 0 && sourceMetaNode.nativeInputs?.[idx]) {
				return sourceMetaNode.nativeInputs[idx].value;
			}
			return null;
		};

		return {
			name: getInputValue('name'),
			mimeType: getInputValue('mime_type'),
			format: getInputValue('format'),
			size: getInputValue('size'),
			duration: getInputValue('duration'),
			source: getInputValue('source')
		};
	}

	/**
	 * Detect data type from SourceMeta info
	 * @param {Object} meta - Metadata info
	 * @returns {string} Detected type
	 */
	_detectTypeFromMeta(meta) {
		if (!meta) return 'unknown';

		const mimeType = meta.mimeType || '';
		if (mimeType.startsWith('image/')) return 'image';
		if (mimeType.startsWith('audio/')) return 'audio';
		if (mimeType.startsWith('video/')) return 'video';
		if (mimeType.startsWith('text/')) return 'text';
		if (mimeType === 'application/json') return 'json';
		if (mimeType === 'application/pdf') return 'pdf';

		const format = (meta.format || '').toLowerCase();
		const imageExts = ['png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp', 'svg'];
		const audioExts = ['mp3', 'wav', 'ogg', 'flac', 'aac', 'm4a'];
		const videoExts = ['mp4', 'webm', 'mov', 'avi', 'mkv'];
		const textExts = ['txt', 'md', 'csv', 'xml', 'html'];

		if (imageExts.includes(format)) return 'image';
		if (audioExts.includes(format)) return 'audio';
		if (videoExts.includes(format)) return 'video';
		if (textExts.includes(format)) return 'text';
		if (format === 'json') return 'json';

		return 'unknown';
	}

	/**
	 * Guess type from MIME type string
	 * @param {string} mimeType - MIME type
	 * @returns {string} Guessed type
	 */
	_guessTypeFromMime(mimeType) {
		if (!mimeType) return 'unknown';
		if (mimeType.startsWith('image/')) return 'image';
		if (mimeType.startsWith('audio/')) return 'audio';
		if (mimeType.startsWith('video/')) return 'video';
		if (mimeType.startsWith('text/')) return 'text';
		if (mimeType === 'application/json') return 'json';
		return 'unknown';
	}

	/**
	 * Guess type from actual data value
	 * @param {*} data - The data value
	 * @returns {string} Guessed type
	 */
	_guessTypeFromData(data) {
		if (data === null || data === undefined) return 'null';
		if (typeof data === 'boolean') return 'boolean';
		if (typeof data === 'number') return Number.isInteger(data) ? 'integer' : 'float';
		if (typeof data === 'string') {
			// Check if it's a data URL
			if (data.startsWith('data:image/')) return 'image';
			if (data.startsWith('data:audio/')) return 'audio';
			if (data.startsWith('data:video/')) return 'video';
			// Check if it's JSON
			try {
				const parsed = JSON.parse(data);
				if (Array.isArray(parsed)) return 'list';
				if (typeof parsed === 'object') return 'dict';
			} catch (e) { /* not JSON */ }
			return 'text';
		}
		if (Array.isArray(data)) return 'list';
		if (typeof data === 'object') return 'dict';
		return 'unknown';
	}

	/**
	 * Detect native node type
	 * @param {Object} node - Native node
	 * @returns {string} Type name
	 */
	_detectNativeType(node) {
		const title = (node.title || '').toLowerCase();
		if (title.includes('string') || title.includes('str')) return 'text';
		if (title.includes('int') || title.includes('integer')) return 'integer';
		if (title.includes('float') || title.includes('real')) return 'float';
		if (title.includes('bool')) return 'boolean';
		if (title.includes('list')) return 'list';
		if (title.includes('dict')) return 'dict';
		return 'unknown';
	}

	/**
	 * Draw simple (thumbnail) preview
	 * @param {Object} node - PreviewFlow node
	 * @param {Object} data - Preview data
	 * @param {number} x - Content area X
	 * @param {number} y - Content area Y
	 * @param {number} w - Content area width
	 * @param {number} h - Content area height
	 * @param {Object} colors - Theme colors
	 */
	_drawPreviewSimple(node, data, x, y, w, h, colors) {
		// Draw preview background
		this.ctx.fillStyle = 'rgba(0,0,0,0.3)';
		this.ctx.beginPath();
		this.ctx.roundRect(x, y, w, h, 4);
		this.ctx.fill();

		// Clip to content area so text doesn't overflow the node
		this.ctx.save();
		this.ctx.beginPath();
		this.ctx.rect(x, y, w, h);
		this.ctx.clip();

		const textScale = this.getTextScale();

		switch (data.type) {
			case 'text':
				this._drawTextPreviewSimple(data.value, x, y, w, h, colors, textScale);
				break;
			case 'integer':
			case 'float':
				this._drawNumberPreview(data.value, x, y, w, h, colors, textScale);
				break;
			case 'boolean':
				this._drawBooleanPreview(data.value, x, y, w, h, colors, textScale);
				break;
			case 'list':
			case 'dict':
			case 'json':
				this._drawJsonPreviewSimple(data.value, x, y, w, h, colors, textScale);
				break;
			case 'image':
				this._drawImagePreviewSimple(data.value, x, y, w, h, colors);
				break;
			case 'audio':
				this._drawAudioPreviewSimple(data, x, y, w, h, colors, textScale);
				break;
			case 'video':
				this._drawVideoPreviewSimple(data, x, y, w, h, colors, textScale);
				break;
			case 'node':
				this._drawNodeReferencePreview(data.value, x, y, w, h, colors, textScale);
				break;
			default:
				this._drawUnknownPreview(data, x, y, w, h, colors, textScale);
		}

		this.ctx.restore();
	}

	/**
	 * Draw full (expanded) preview
	 * @param {Object} node - PreviewFlow node
	 * @param {Object} data - Preview data
	 * @param {number} x - Content area X
	 * @param {number} y - Content area Y
	 * @param {number} w - Content area width
	 * @param {number} h - Content area height
	 * @param {Object} colors - Theme colors
	 */
	_drawPreviewFull(node, data, x, y, w, h, colors) {
		// Draw preview background
		this.ctx.fillStyle = 'rgba(0,0,0,0.3)';
		this.ctx.beginPath();
		this.ctx.roundRect(x, y, w, h, 4);
		this.ctx.fill();

		// If an HTML text overlay is active for this node, skip canvas text rendering
		// to avoid showing two areas with duplicate content
		if (this._previewTextOverlays?.has(node.id)) return;

		// Clip to content area
		this.ctx.save();
		this.ctx.beginPath();
		this.ctx.rect(x, y, w, h);
		this.ctx.clip();

		const textScale = this.getTextScale();

		switch (data.type) {
			case 'text':
				this._drawTextPreviewFull(data.value, x, y, w, h, colors, textScale);
				break;
			case 'integer':
			case 'float':
				this._drawNumberPreview(data.value, x, y, w, h, colors, textScale, true);
				break;
			case 'boolean':
				this._drawBooleanPreview(data.value, x, y, w, h, colors, textScale, true);
				break;
			case 'list':
			case 'dict':
			case 'json':
				this._drawJsonPreviewFull(data.value, x, y, w, h, colors, textScale);
				break;
			case 'image':
				this._drawImagePreviewFull(data.value, x, y, w, h, colors);
				break;
			case 'audio':
				this._drawAudioPreviewFull(data, x, y, w, h, colors, textScale);
				break;
			case 'video':
				this._drawVideoPreviewFull(data, x, y, w, h, colors, textScale);
				break;
			default:
				this._drawUnknownPreview(data, x, y, w, h, colors, textScale, true);
		}

		this.ctx.restore();
	}

	/**
	 * Draw placeholder when no data is available
	 */
	_drawPreviewPlaceholder(x, y, w, h, colors) {
		// Draw background
		this.ctx.fillStyle = 'rgba(0,0,0,0.2)';
		this.ctx.beginPath();
		this.ctx.roundRect(x, y, w, h, 4);
		this.ctx.fill();

		// Draw dashed border
		this.ctx.strokeStyle = colors.textTertiary || 'rgba(255,255,255,0.3)';
		this.ctx.lineWidth = 1 / this.camera.scale;
		this.ctx.setLineDash([4 / this.camera.scale, 4 / this.camera.scale]);
		this.ctx.stroke();
		this.ctx.setLineDash([]);

		// Draw placeholder text
		const textScale = this.getTextScale();
		this.ctx.fillStyle = colors.textTertiary || 'rgba(255,255,255,0.4)';
		this.ctx.font = (10 * textScale) + 'px Arial';
		this.ctx.textAlign = 'center';
		this.ctx.textBaseline = 'middle';
		this.ctx.fillText('No data', x + w / 2, y + h / 2);
	}

	// --- Preview type-specific renderers ---

	_drawTextPreviewSimple(value, x, y, w, h, colors, textScale) {
		const text = String(value || '');
		const lines = text.split('\n').slice(0, 3);

		this.ctx.fillStyle = colors.textPrimary;
		this.ctx.font = (9 * textScale) + 'px Courier New';
		this.ctx.textAlign = 'left';
		this.ctx.textBaseline = 'top';

		const lineHeight = 12 * textScale;
		const maxChars = Math.floor((w - 8) / (5 * textScale));

		for (let i = 0; i < lines.length && i * lineHeight < h - 8; i++) {
			let line = lines[i];
			if (line.length > maxChars) line = line.substring(0, maxChars - 3) + '...';
			this.ctx.fillText(line, x + 4, y + 4 + i * lineHeight);
		}

		if (text.split('\n').length > 3) {
			this.ctx.fillStyle = colors.textTertiary;
			this.ctx.fillText('...', x + 4, y + 4 + 3 * lineHeight);
		}
	}

	_drawTextPreviewFull(value, x, y, w, h, colors, textScale) {
		const text = String(value || '');
		const lines = text.split('\n');

		this.ctx.fillStyle = colors.textPrimary;
		this.ctx.font = (9 * textScale) + 'px Courier New';
		this.ctx.textAlign = 'left';
		this.ctx.textBaseline = 'top';

		const lineHeight = 12 * textScale;
		const maxChars = Math.floor((w - 8) / (5 * textScale));
		const maxLines = Math.floor((h - 8) / lineHeight);

		for (let i = 0; i < lines.length && i < maxLines; i++) {
			let line = lines[i];
			if (line.length > maxChars) line = line.substring(0, maxChars - 3) + '...';
			this.ctx.fillText(line, x + 4, y + 4 + i * lineHeight);
		}

		if (lines.length > maxLines) {
			this.ctx.fillStyle = colors.textTertiary;
			const moreCount = lines.length - maxLines;
			this.ctx.fillText(`... ${moreCount} more lines`, x + 4, y + h - 14);
		}
	}

	_drawNumberPreview(value, x, y, w, h, colors, textScale, isFull = false) {
		const numStr = typeof value === 'number' ? value.toLocaleString() : String(value);

		this.ctx.fillStyle = colors.accentBlue || '#4a90d9';
		this.ctx.font = `bold ${(isFull ? 16 : 12) * textScale}px Arial`;
		this.ctx.textAlign = 'center';
		this.ctx.textBaseline = 'middle';
		this.ctx.fillText(numStr, x + w / 2, y + h / 2);
	}

	_drawBooleanPreview(value, x, y, w, h, colors, textScale, isFull = false) {
		const boolVal = Boolean(value);
		const size = (isFull ? 24 : 16) * textScale;
		const cx = x + w / 2;
		const cy = y + h / 2;

		// Draw circle
		this.ctx.fillStyle = boolVal ? (colors.accentGreen || '#5cb85c') : (colors.accentRed || '#d9534f');
		this.ctx.beginPath();
		this.ctx.arc(cx, cy, size / 2, 0, Math.PI * 2);
		this.ctx.fill();

		// Draw check or X
		this.ctx.strokeStyle = '#fff';
		this.ctx.lineWidth = 2 / this.camera.scale;
		this.ctx.beginPath();
		if (boolVal) {
			this.ctx.moveTo(cx - size / 4, cy);
			this.ctx.lineTo(cx - size / 10, cy + size / 4);
			this.ctx.lineTo(cx + size / 4, cy - size / 4);
		} else {
			const offset = size / 4;
			this.ctx.moveTo(cx - offset, cy - offset);
			this.ctx.lineTo(cx + offset, cy + offset);
			this.ctx.moveTo(cx + offset, cy - offset);
			this.ctx.lineTo(cx - offset, cy + offset);
		}
		this.ctx.stroke();
	}

	_drawJsonPreviewSimple(value, x, y, w, h, colors, textScale) {
		let data = value;
		if (typeof value === 'string') {
			try { data = JSON.parse(value); } catch (e) { /* use as-is */ }
		}

		const isArray = Array.isArray(data);
		const label = isArray ? `Array[${data.length}]` : `Object{${Object.keys(data || {}).length}}`;

		this.ctx.fillStyle = colors.accentPurple || '#9b59b6';
		this.ctx.font = `bold ${10 * textScale}px Arial`;
		this.ctx.textAlign = 'center';
		this.ctx.textBaseline = 'middle';
		this.ctx.fillText(label, x + w / 2, y + h / 2);
	}

	_drawJsonPreviewFull(value, x, y, w, h, colors, textScale) {
		let data = value;
		if (typeof value === 'string') {
			try { data = JSON.parse(value); } catch (e) { /* use as-is */ }
		}

		const jsonStr = JSON.stringify(data, null, 2);
		this._drawTextPreviewFull(jsonStr, x, y, w, h, colors, textScale);
	}

	_drawImagePreviewSimple(value, x, y, w, h, colors) {
		if (!value || typeof value !== 'string') {
			this._drawMediaPlaceholder('🖼', x, y, w, h, colors);
			return;
		}

		// Create or get cached image
		const cacheKey = 'img_' + value.substring(0, 50);
		if (!this._previewImageCache) this._previewImageCache = {};

		if (!this._previewImageCache[cacheKey]) {
			const img = new Image();
			img.onload = () => { this._previewImageCache[cacheKey] = img; this.draw(); };
			img.onerror = () => { this._previewImageCache[cacheKey] = 'error'; };
			img.src = value;
			this._previewImageCache[cacheKey] = 'loading';
		}

		const cached = this._previewImageCache[cacheKey];
		if (cached === 'loading') {
			this._drawMediaPlaceholder('...', x, y, w, h, colors);
		} else if (cached === 'error' || !cached) {
			this._drawMediaPlaceholder('!', x, y, w, h, colors);
		} else {
			// Draw image scaled to fit
			const img = cached;
			const scale = Math.min((w - 4) / img.width, (h - 4) / img.height, 1);
			const imgW = img.width * scale;
			const imgH = img.height * scale;
			const imgX = x + (w - imgW) / 2;
			const imgY = y + (h - imgH) / 2;
			this.ctx.drawImage(img, imgX, imgY, imgW, imgH);
		}
	}

	_drawImagePreviewFull(value, x, y, w, h, colors) {
		// Same as simple but with larger area
		this._drawImagePreviewSimple(value, x, y, w, h, colors);
	}

	_drawAudioPreviewSimple(data, x, y, w, h, colors, textScale) {
		// Draw audio icon
		this._drawMediaPlaceholder('🔊', x, y, w, h, colors);

		// Show duration if available
		if (data.meta?.duration) {
			const duration = Math.round(data.meta.duration);
			const mins = Math.floor(duration / 60);
			const secs = duration % 60;
			const durStr = `${mins}:${secs.toString().padStart(2, '0')}`;

			this.ctx.fillStyle = colors.textSecondary;
			this.ctx.font = (8 * textScale) + 'px Arial';
			this.ctx.textAlign = 'center';
			this.ctx.textBaseline = 'bottom';
			this.ctx.fillText(durStr, x + w / 2, y + h - 4);
		}
	}

	_drawAudioPreviewFull(data, x, y, w, h, colors, textScale) {
		// Draw audio waveform placeholder
		this.ctx.fillStyle = colors.accentBlue || '#4a90d9';
		const barCount = Math.floor(w / 6);
		const barMaxH = h - 20;

		for (let i = 0; i < barCount; i++) {
			const barH = (Math.sin(i * 0.5) * 0.5 + 0.5) * barMaxH * 0.8 + barMaxH * 0.2;
			const barX = x + 2 + i * 6;
			const barY = y + (h - barH) / 2;
			this.ctx.fillRect(barX, barY, 4, barH);
		}

		// Show duration
		if (data.meta?.duration) {
			const duration = Math.round(data.meta.duration);
			const mins = Math.floor(duration / 60);
			const secs = duration % 60;
			const durStr = `${mins}:${secs.toString().padStart(2, '0')}`;

			this.ctx.fillStyle = colors.textPrimary;
			this.ctx.font = (10 * textScale) + 'px Arial';
			this.ctx.textAlign = 'right';
			this.ctx.textBaseline = 'bottom';
			this.ctx.fillText(durStr, x + w - 4, y + h - 4);
		}
	}

	_drawVideoPreviewSimple(data, x, y, w, h, colors, textScale) {
		// Draw video icon
		this._drawMediaPlaceholder('🎬', x, y, w, h, colors);

		if (data.meta?.duration) {
			const duration = Math.round(data.meta.duration);
			const mins = Math.floor(duration / 60);
			const secs = duration % 60;
			const durStr = `${mins}:${secs.toString().padStart(2, '0')}`;

			this.ctx.fillStyle = colors.textSecondary;
			this.ctx.font = (8 * textScale) + 'px Arial';
			this.ctx.textAlign = 'center';
			this.ctx.textBaseline = 'bottom';
			this.ctx.fillText(durStr, x + w / 2, y + h - 4);
		}
	}

	_drawVideoPreviewFull(data, x, y, w, h, colors, textScale) {
		// Same as simple for now - could show video frame
		this._drawVideoPreviewSimple(data, x, y, w, h, colors, textScale);
	}

	_drawNodeReferencePreview(value, x, y, w, h, colors, textScale) {
		this.ctx.fillStyle = colors.textSecondary;
		this.ctx.font = (9 * textScale) + 'px Arial';
		this.ctx.textAlign = 'center';
		this.ctx.textBaseline = 'middle';
		this.ctx.fillText('→ ' + String(value), x + w / 2, y + h / 2);
	}

	_drawUnknownPreview(data, x, y, w, h, colors, textScale, isFull = false) {
		const typeLabel = `Type: ${data.type}`;
		this.ctx.fillStyle = colors.textTertiary;
		this.ctx.font = (9 * textScale) + 'px Arial';
		this.ctx.textAlign = 'center';
		this.ctx.textBaseline = 'middle';
		this.ctx.fillText(typeLabel, x + w / 2, y + h / 2);
	}

	_drawMediaPlaceholder(icon, x, y, w, h, colors) {
		const textScale = this.getTextScale();
		this.ctx.fillStyle = colors.textSecondary || 'rgba(255,255,255,0.6)';
		this.ctx.font = (20 * textScale) + 'px Arial';
		this.ctx.textAlign = 'center';
		this.ctx.textBaseline = 'middle';
		this.ctx.fillText(icon, x + w / 2, y + h / 2);
	}

	/**
	 * Recalculate PreviewFlow node size based on mode
	 * @param {Object} node - The PreviewFlow node
	 */
	_recalculatePreviewNodeSize(node) {
		const isExpanded = node.extra?.previewExpanded ?? false;
		const previewData = this._getPreviewData(node);

		if (isExpanded && previewData) {
			// Expanded sizes based on content type
			switch (previewData.type) {
				case 'image':
				case 'video':
					node.size = [400, 350];
					break;
				case 'text':
					// Calculate size based on text length
					const text = String(previewData.value || '');
					const lines = text.split('\n');
					const maxLineLen = Math.max(...lines.map(l => l.length), 20);
					const width = Math.min(Math.max(280, maxLineLen * 6 + 20), 600);
					const height = Math.min(Math.max(180, lines.length * 14 + 40), 500);
					node.size = [width, height];
					break;
				case 'list':
				case 'dict':
				case 'json':
					node.size = [400, 350];
					break;
				case 'audio':
					node.size = [280, 160];
					break;
				default:
					node.size = [280, 200];
			}
		} else {
			// Compact size
			node.size = [200, 120];
		}
	}

	// ========================================================================
	// EDGE PREVIEW - Insert/remove preview nodes on links
	// ========================================================================

	/**
	 * Find a link at the given world position
	 * @param {number} wx - World X coordinate
	 * @param {number} wy - World Y coordinate
	 * @returns {Object|null} The link object if found, null otherwise
	 */
	_findLinkAtPosition(wx, wy) {
		if (!this._features.edgePreview || !this._edgePreviewConfig.enabled) return null;

		const threshold = this._edgePreviewConfig.linkHitDistance / this.camera.scale;

		for (const linkId in this.graph.links) {
			const link = this.graph.links[linkId];
			const src = this.graph.getNodeById(link.origin_id);
			const tgt = this.graph.getNodeById(link.target_id);
			if (!src || !tgt) continue;

			// Calculate slot positions
			const x1 = src.pos[0] + src.size[0];
			const y1 = src.pos[1] + 38 + link.origin_slot * 25;
			const x2 = tgt.pos[0];
			const y2 = tgt.pos[1] + 38 + link.target_slot * 25;

			if (this._pointNearBezier(wx, wy, x1, y1, x2, y2, threshold)) {
				return link;
			}
		}
		return null;
	}

	/**
	 * Check if a point is near a bezier curve (used for link hit detection)
	 * @param {number} px - Point X
	 * @param {number} py - Point Y
	 * @param {number} x1 - Start X
	 * @param {number} y1 - Start Y
	 * @param {number} x2 - End X
	 * @param {number} y2 - End Y
	 * @param {number} threshold - Distance threshold
	 * @returns {boolean}
	 */
	_pointNearBezier(px, py, x1, y1, x2, y2, threshold) {
		const dx = x2 - x1;
		const controlOffset = Math.min(Math.abs(dx) * 0.5, 200);
		const cx1 = x1 + controlOffset;
		const cx2 = x2 - controlOffset;

		// Sample 20 points along the bezier curve
		for (let i = 0; i <= 20; i++) {
			const t = i / 20;
			const mt = 1 - t;
			const bx = mt**3 * x1 + 3 * mt**2 * t * cx1 + 3 * mt * t**2 * cx2 + t**3 * x2;
			const by = mt**3 * y1 + 3 * mt**2 * t * y1 + 3 * mt * t**2 * y2 + t**3 * y2;
			if (Math.sqrt((px - bx)**2 + (py - by)**2) < threshold) {
				return true;
			}
		}
		return false;
	}

	/**
	 * Check if a preview node can be inserted on a link
	 * @param {Object} link - The link object
	 * @returns {{allowed: boolean, reason: string|null}}
	 */
	_canInsertPreviewOnLink(link) {
		if (!link) return { allowed: false, reason: 'Invalid link' };
		if (!this._features.edgePreview) return { allowed: false, reason: 'Edge preview disabled' };

		// Disallow preview insertion on loop-back edges
		if (link.loop) return { allowed: false, reason: 'Cannot insert preview on loop-back edge' };

		const src = this.graph.getNodeById(link.origin_id);
		const tgt = this.graph.getNodeById(link.target_id);

		if (!src || !tgt) return { allowed: false, reason: 'Invalid source or target node' };
		if (this._isPreviewFlowNode(src)) return { allowed: false, reason: 'Source is already a preview node' };
		if (this._isPreviewFlowNode(tgt)) return { allowed: false, reason: 'Target is already a preview node' };

		// Check if we have a preview node type configured
		const previewTypes = this._schemaTypeRoles.preview;
		if (!previewTypes || previewTypes.length === 0) {
			return { allowed: false, reason: 'No preview node type configured' };
		}

		// Check if the preview node type exists
		const previewType = previewTypes[0];
		if (!this.graph.nodeTypes[previewType]) {
			return { allowed: false, reason: `Preview node type '${previewType}' not found` };
		}

		return { allowed: true, reason: null };
	}

	/**
	 * Insert a preview node on a link
	 * @param {Object} link - The link to insert preview on
	 * @param {number} wx - World X position for the preview node
	 * @param {number} wy - World Y position for the preview node
	 * @returns {Object|null} The created preview node, or null on failure
	 */
	insertPreviewOnLink(link, wx, wy) {
		if (this.isLocked) return null;

		const check = this._canInsertPreviewOnLink(link);
		if (!check.allowed) {
			console.warn(`Cannot insert preview: ${check.reason}`);
			return null;
		}

		const src = this.graph.getNodeById(link.origin_id);
		const tgt = this.graph.getNodeById(link.target_id);

		// Store original edge info for restoration later
		const originalEdgeInfo = {
			sourceNodeId: link.origin_id,
			sourceSlotIdx: link.origin_slot,
			sourceSlotName: src.outputs[link.origin_slot]?.name || 'output',
			targetNodeId: link.target_id,
			targetSlotIdx: link.target_slot,
			targetSlotName: tgt.inputs[link.target_slot]?.name || 'input',
			linkType: link.type,
			linkId: link.id,
			data: link.data ? JSON.parse(JSON.stringify(link.data)) : null,
			extra: link.extra ? JSON.parse(JSON.stringify(link.extra)) : null
		};

		// Create preview node using configured type
		const previewType = this._schemaTypeRoles.preview[0];
		const preview = this.graph.createNode(previewType, wx - 100, wy - 60);
		if (!preview) {
			console.warn('Failed to create preview node');
			return null;
		}

		// Store original edge info in the preview node
		if (!preview.extra) preview.extra = {};
		preview.extra._originalEdgeInfo = originalEdgeInfo;
		preview.extra._isEdgePreview = true;

		// Remove original link
		this.graph.removeLink(link.id);

		// Find the input slot on the preview node (usually named 'input' or at index 0)
		const previewInputIdx = this._findInputSlotByName(preview, 'input') ?? 0;
		// Find the output slot on the preview node (usually named 'get' for workflow nodes)
		const previewOutputIdx = this._findOutputSlotByName(preview, 'get') ?? 0;

		// Create source -> preview link
		const link1 = this.graph.addLink(
			src.id, originalEdgeInfo.sourceSlotIdx,
			preview.id, previewInputIdx,
			originalEdgeInfo.linkType
		);
		if (link1) {
			if (!link1.extra) link1.extra = {};
			link1.extra._isPreviewLink = true;
		}

		// Create preview -> target link
		const link2 = this.graph.addLink(
			preview.id, previewOutputIdx,
			tgt.id, originalEdgeInfo.targetSlotIdx,
			originalEdgeInfo.linkType
		);
		if (link2) {
			if (!link2.extra) link2.extra = {};
			link2.extra._isPreviewLink = true;
		}

		this.eventBus.emit('edgePreview:inserted', {
			nodeId: preview.id,
			originalEdgeInfo
		});

		this.draw();
		return preview;
	}

	/**
	 * Remove a preview node and restore the original connection
	 * @param {Object} node - The preview node to remove
	 * @returns {Object|null} The restored link, or null if no restoration was possible
	 */
	removePreviewNodeAndRestore(node) {
		if (this.isLocked) return null;
		if (!this._isPreviewFlowNode(node)) return null;

		const originalEdgeInfo = node.extra?._originalEdgeInfo;

		// Find incoming link to preview
		const inputSlotIdx = this._findInputSlotByName(node, 'input') ?? 0;
		const inLinkId = node.inputs?.[inputSlotIdx]?.link;

		// Find outgoing links from preview
		const outputSlotIdx = this._findOutputSlotByName(node, 'get') ?? 0;
		const outLinkIds = node.outputs?.[outputSlotIdx]?.links || [];

		const inLink = inLinkId ? this.graph.links[inLinkId] : null;
		const outLinks = outLinkIds.map(id => this.graph.links[id]).filter(Boolean);

		let restoredLink = null;

		// Restore original connections
		if (inLink && outLinks.length > 0) {
			const src = this.graph.getNodeById(inLink.origin_id);
			const srcSlot = inLink.origin_slot;

			for (const outLink of outLinks) {
				const tgt = this.graph.getNodeById(outLink.target_id);
				const tgtSlot = outLink.target_slot;

				if (src && tgt) {
					// Create restored link
					const newLink = this.graph.addLink(
						src.id, srcSlot,
						tgt.id, tgtSlot,
						originalEdgeInfo?.linkType || inLink.type
					);

					if (newLink) {
						// Restore original link data/extra if available
						if (originalEdgeInfo?.data) {
							newLink.data = JSON.parse(JSON.stringify(originalEdgeInfo.data));
						}
						if (originalEdgeInfo?.extra) {
							const restoredExtra = JSON.parse(JSON.stringify(originalEdgeInfo.extra));
							delete restoredExtra._isPreviewLink;
							if (Object.keys(restoredExtra).length > 0) {
								newLink.extra = restoredExtra;
							}
						}
						restoredLink = newLink;
					}
				}
			}
		}

		// Remove preview links
		if (inLinkId) this.graph.removeLink(inLinkId);
		for (const id of outLinkIds) this.graph.removeLink(id);

		// Remove preview node
		this.graph.removeNode(node);

		this.eventBus.emit('edgePreview:removed', {
			nodeId: node.id,
			restoredLinkId: restoredLink?.id,
			originalEdgeInfo
		});

		this.draw();
		return restoredLink;
	}

	_applyDecoratorsToNode(node) {
		if (!node?.schemaName || !node?.modelName) return;
		const decorators = this._schemaDecorators[node.schemaName]?.[node.modelName];
		if (!decorators) return;
		if (decorators.info) {
			node.nodeInfo = decorators.info;
			// Only set displayTitle from decorator if not already set (e.g., from extra.name)
			if (decorators.info.title && !node.displayTitle) node.displayTitle = decorators.info.title;
			// Apply section-based header color if feature is enabled and color is configured
			if (this._features.sectionColors && decorators.info.section && this._sectionColors[decorators.info.section]) {
				node.color = this._sectionColors[decorators.info.section];
			}
		}
		const completeness = this._getNodeCompleteness(node);
		const isComplete = completeness.complete;
		for (const cfg of decorators.buttons || []) {
			const stack = (cfg.position === 'top' || cfg.position === 'header') ? 'top' : 'bottom';
			this.addNodeButton(node, stack, { id: cfg.id, label: cfg.label || '', icon: cfg.icon || '', enabled: cfg.enabled !== false && isComplete, callback: this._resolveCallback(cfg.callback || cfg.id) });
		}
		if (decorators.dropzone) {
			this.setNodeDropZone(node, { accept: decorators.dropzone.accept || '*', area: decorators.dropzone.area || 'content', label: isComplete ? (decorators.dropzone.label || 'Drop file here') : 'Complete required fields first', reject: decorators.dropzone.reject || 'File type not accepted', enabled: isComplete, callback: this._resolveDropCallback(decorators.dropzone.callback || 'emit_event') });
		}
		if (decorators.chat) { node.isChat = true; node.chatConfig = decorators.chat; }
	}

	_reapplySectionColorsToAllNodes() {
		for (const node of this.graph.nodes) {
			if (!node?.schemaName || !node?.modelName) continue;
			const decorators = this._schemaDecorators[node.schemaName]?.[node.modelName];
			if (!decorators?.info?.section) continue;

			if (this._features.sectionColors && this._sectionColors[decorators.info.section]) {
				node.color = this._sectionColors[decorators.info.section];
			} else {
				// Clear the color so default coloring takes over
				delete node.color;
			}
		}
		this.draw();
	}

	// ========================================================================
	// COMPLETENESS CHECKING
	// ========================================================================

	_isFieldRequired(node, slotIdx) {
		const meta = node.inputMeta?.[slotIdx];
		if (!meta) return false;

		const typeStr = meta.type || '';
		if (typeStr.includes('Optional[')) return false;
		if (node.nativeInputs?.[slotIdx]?.optional) return false;

		return true;
	}

	_isFieldFilled(node, slotIdx) {
		const input = node.inputs[slotIdx];
		if (!input) return true;

		// Connected via link
		if (input.link) return true;

		// Multi-input with connections
		if (node.multiInputs?.[slotIdx]?.links?.length > 0) return true;

		// Base multi-field slot: filled if any sub-slot has a connection
		const metaName = node.inputMeta?.[slotIdx]?.name || '';
		if (!metaName.includes('.')) {
			for (const [fieldName, indices] of Object.entries(node.multiInputSlots || {})) {
				if (fieldName === metaName && indices.includes(slotIdx)) {
					for (const sibIdx of indices) {
						if (sibIdx === slotIdx) continue;
						if (node.inputs[sibIdx]?.link) return true;
						if (node.multiInputs?.[sibIdx]?.links?.length > 0) return true;
					}
					break;
				}
			}
		}

		// Native input with value (empty string is valid for string types)
		if (node.nativeInputs?.[slotIdx] !== undefined) {
			const val = node.nativeInputs[slotIdx].value;
			if (val === null || val === undefined) return false;
			return true;
		}

		// No native input and no connection = not filled (but might not be required)
		return false;
	}

	_getNodeCompleteness(node) {
		const result = {
			complete: true,
			missingFields: [],
			filledFields: [],
			optionalEmpty: []
		};

		if (!node.inputs) return result;

		for (let i = 0; i < node.inputs.length; i++) {
			const fieldName = node.inputMeta?.[i]?.name || node.inputs[i]?.name || `input_${i}`;
			const required = this._isFieldRequired(node, i);
			const filled = this._isFieldFilled(node, i);

			if (filled) {
				result.filledFields.push(fieldName);
			} else if (required) {
				result.complete = false;
				result.missingFields.push(fieldName);
			} else {
				result.optionalEmpty.push(fieldName);
			}
		}

		return result;
	}

	_checkAllNodesCompleteness() {
		const results = {};
		for (const node of this.graph.nodes) {
			results[node.id] = this._getNodeCompleteness(node);
		}
		return results;
	}

	_emitCompletenessChanged(node) {
		const completeness = this._getNodeCompleteness(node);
		this.eventBus.emit('node:completenessChanged', {
			nodeId: node.id,
			...completeness
		});
	}

	_getChainCompleteness(node, visited = new Set()) {
		if (!node) {
			return { complete: true, nodeComplete: true, missingFields: [], incompleteNodes: [], incompleteLinks: [] };
		}

		// Cycle detection
		if (visited.has(node.id)) {
			return { complete: true, nodeComplete: true, missingFields: [], incompleteNodes: [], incompleteLinks: [] };
		}
		visited.add(node.id);

		// Always compute node completeness fresh
		const nodeCompleteness = this._getNodeCompleteness(node);

		const result = {
			complete: nodeCompleteness.complete,
			nodeComplete: nodeCompleteness.complete,
			missingFields: [...nodeCompleteness.missingFields],
			incompleteNodes: nodeCompleteness.complete ? [] : [node.id],
			incompleteLinks: []
		};

		if (!node.inputs) return result;

		// Check all input connections recursively
		for (let i = 0; i < node.inputs.length; i++) {
			const input = node.inputs[i];

			// Collect all link IDs for this input
			let linkIds = [];
			if (node.multiInputs?.[i]?.links) {
				linkIds = [...node.multiInputs[i].links];
			} else if (input.link) {
				linkIds = [input.link];
			}

			for (const linkId of linkIds) {
				const link = this.graph.links[linkId];
				if (!link) continue;

				const sourceNode = this.graph.getNodeById(link.origin_id);
				if (!sourceNode) continue;

				// Recursive call - creates new visited set branch
				const sourceCompleteness = this._getChainCompleteness(sourceNode, new Set(visited));

				if (!sourceCompleteness.complete) {
					result.complete = false;

					// Add this link as incomplete if source is incomplete
					if (!result.incompleteLinks.includes(linkId)) {
						result.incompleteLinks.push(linkId);
					}

					// Merge upstream incomplete nodes
					for (const id of sourceCompleteness.incompleteNodes) {
						if (!result.incompleteNodes.includes(id)) {
							result.incompleteNodes.push(id);
						}
					}

					// Merge upstream incomplete links
					for (const lid of sourceCompleteness.incompleteLinks) {
						if (!result.incompleteLinks.includes(lid)) {
							result.incompleteLinks.push(lid);
						}
					}
				}
			}
		}

		return result;
	}

	_refreshAllCompleteness() {
		// Clear all cached state first to avoid stale data
		for (const node of this.graph.nodes) {
			node._nodeComplete = undefined;
			node._chainComplete = undefined;
			node._incompleteChainNodes = undefined;
			node._incompleteChainLinks = undefined;
		}

		// Now recompute for all nodes
		for (const node of this.graph.nodes) {
			this._updateNodeCompletenessState(node);
		}

		this.draw();
	}

	_updateNodeCompletenessState(node) {
		// Clear this node's cached state before recomputing
		node._nodeComplete = undefined;
		node._chainComplete = undefined;
		node._incompleteChainNodes = undefined;
		node._incompleteChainLinks = undefined;

		// Compute fresh
		const chainCompleteness = this._getChainCompleteness(node);

		// Store on node
		node._nodeComplete = chainCompleteness.nodeComplete;
		node._chainComplete = chainCompleteness.complete;
		node._incompleteChainNodes = chainCompleteness.incompleteNodes;
		node._incompleteChainLinks = chainCompleteness.incompleteLinks;

		// Update interactive elements (buttons, dropzones)
		this._updateNodeInteractiveElements(node, chainCompleteness);

		return chainCompleteness;
	}

	_updateNodeInteractiveElements(node, chainCompleteness) {
		const decorators = this._schemaDecorators[node.schemaName]?.[node.modelName];
		if (!decorators) return;

		const isChainComplete = chainCompleteness.complete;

		// Update buttons
		if (node._buttonStacks) {
			for (const stack of ['top', 'bottom']) {
				for (const btn of node._buttonStacks[stack] || []) {
					const originalConfig = decorators.buttons?.find(b => b.id === btn.id);
					btn.enabled = (originalConfig?.enabled !== false) && isChainComplete;
				}
			}
		}

		// Update dropzone
		if (node._dropZone && decorators.dropzone) {
			node._dropZone.enabled = isChainComplete;
			node._dropZone.label = isChainComplete
				? (decorators.dropzone.label || 'Drop file here')
				: this._getIncompleteChainMessage(chainCompleteness);
		}
	}

	_getIncompleteChainMessage(chainCompleteness) {
		if (!chainCompleteness.nodeComplete) {
			const fields = chainCompleteness.missingFields.slice(0, 2).join(', ');
			return `Fill required: ${fields}${chainCompleteness.missingFields.length > 2 ? '...' : ''}`;
		}
		const count = chainCompleteness.incompleteNodes.length;
		return count === 1 ? 'Complete upstream node' : `${count} upstream nodes incomplete`;
	}

	// Legacy compatibility - keep old method signatures working
	_updateNodeChainState(node) {
		return this._updateNodeCompletenessState(node);
	}

	_emitCompletenessChanged(node) {
		const completeness = this._getNodeCompleteness(node);
		this.eventBus.emit('node:completenessChanged', {
			nodeId: node.id,
			...completeness
		});
	}

	_setupCompletenessListeners() {
		// Field changed - refresh immediately
		this.eventBus.on(GraphEvents.FIELD_CHANGED, (data) => {
			const node = data?.nodeId ? this.graph.getNodeById(data.nodeId) : null;
			if (node) {
				this._propagateCompletenessDownstream(node);
				this.draw();
			} else {
				this._refreshAllCompleteness();
			}
		});

		// Link created - refresh both endpoints and downstream
		this.eventBus.on(GraphEvents.LINK_CREATED, (data) => {
			const link = this.graph.links[data.linkId];
			if (link) {
				const targetNode = this.graph.getNodeById(link.target_id);
				if (targetNode) {
					this._propagateCompletenessDownstream(targetNode);
				}
			}
		});

		// Link removed - refresh affected nodes
		this.eventBus.on(GraphEvents.LINK_REMOVED, (data) => {
			const targetNode = data.targetNodeId ? this.graph.getNodeById(data.targetNodeId) : null;
			if (targetNode) {
				this._propagateCompletenessDownstream(targetNode);
			} else {
				this._refreshAllCompleteness();
			}
		});

		// Node created - just update that node
		this.eventBus.on(GraphEvents.NODE_CREATED, (data) => {
			const node = data?.node || (data?.nodeId ? this.graph.getNodeById(data.nodeId) : null);
			if (node) {
				this._updateNodeCompletenessState(node);
				this.draw();
			}
		});

		// Node removed - refresh all (connections may have changed)
		this.eventBus.on(GraphEvents.NODE_REMOVED, () => {
			this._refreshAllCompleteness();
		});

		// Workflow imported - delayed to ensure nodes are ready
		this.eventBus.on(GraphEvents.WORKFLOW_IMPORTED, () => {
			setTimeout(() => this._refreshAllCompleteness(), 50);
		});

		// Graph loaded/deserialized
		this.eventBus.on(GraphEvents.GRAPH_LOADED, () => {
			setTimeout(() => this._refreshAllCompleteness(), 50);
		});

		// Data loaded
		this.eventBus.on(GraphEvents.DATA_LOADED, () => {
			setTimeout(() => this._refreshAllCompleteness(), 50);
		});
	}

	_propagateCompletenessDownstream(startNode) {
		if (!startNode) return;

		// First update the changed node
		this._updateNodeCompletenessState(startNode);

		// BFS to find all downstream nodes
		const visited = new Set([startNode.id]);
		const queue = [startNode];

		while (queue.length > 0) {
			const node = queue.shift();

			// Find all nodes that receive input from this node
			for (const output of node.outputs || []) {
				for (const linkId of output.links || []) {
					const link = this.graph.links[linkId];
					if (!link) continue;

					const targetNode = this.graph.getNodeById(link.target_id);
					if (targetNode && !visited.has(targetNode.id)) {
						visited.add(targetNode.id);
						this._updateNodeCompletenessState(targetNode);
						queue.push(targetNode);
					}
				}
			}
		}

		// Draw once at the end
		this.draw();
	}

	_drawCompletenessIndicator(node, colors) {
		const ctx = this.ctx;
		const x = node.pos[0];
		const y = node.pos[1];
		const w = node.size[0];
		const textScale = this.getTextScale();

		// Use stored state (updated by _refreshAllCompleteness)
		const selfComplete = node._nodeComplete !== undefined ? node._nodeComplete : true;
		const chainComplete = node._chainComplete !== undefined ? node._chainComplete : true;

		if (!selfComplete || !chainComplete) {
			const badgeX = x + w - 18;
			const badgeY = y + 6;
			const badgeR = 7;

			ctx.fillStyle = !selfComplete ? colors.accentRed : colors.accentOrange;
			ctx.beginPath();
			ctx.arc(badgeX, badgeY + 7, badgeR, 0, Math.PI * 2);
			ctx.fill();

			ctx.fillStyle = '#fff';
			ctx.font = `bold ${9 * textScale}px sans-serif`;
			ctx.textAlign = 'center';
			ctx.textBaseline = 'middle';
			ctx.fillText(!selfComplete ? '!' : '⋯', badgeX, badgeY + 7);
		}
	}

	_drawExecutionSpinner(cx, cy, r, colors) {
		const ctx = this.ctx;
		const time = performance.now() / 1000;
		const rotation = (time * 3) % (Math.PI * 2); // 3 rotations per second

		ctx.save();
		ctx.translate(cx, cy);
		ctx.rotate(rotation);

		// Draw spinning arc
		ctx.strokeStyle = '#ffffff';
		ctx.lineWidth = 2 / this.camera.scale;
		ctx.lineCap = 'round';
		ctx.beginPath();
		ctx.arc(0, 0, r, 0, Math.PI * 1.5);
		ctx.stroke();

		// Draw dot at the end
		ctx.fillStyle = '#ffffff';
		ctx.beginPath();
		ctx.arc(r * Math.cos(Math.PI * 1.5), r * Math.sin(Math.PI * 1.5), 1.5 / this.camera.scale, 0, Math.PI * 2);
		ctx.fill();

		ctx.restore();
	}

	_drawExecutionCheck(cx, cy, r, colors) {
		const ctx = this.ctx;
		ctx.save();
		ctx.strokeStyle = '#ffffff';
		ctx.lineWidth = 2 / this.camera.scale;
		ctx.lineCap = 'round';
		ctx.lineJoin = 'round';
		ctx.beginPath();
		ctx.moveTo(cx - r * 0.5, cy);
		ctx.lineTo(cx - r * 0.1, cy + r * 0.5);
		ctx.lineTo(cx + r * 0.6, cy - r * 0.4);
		ctx.stroke();
		ctx.restore();
	}

	_drawExecutionX(cx, cy, r, colors) {
		const ctx = this.ctx;
		ctx.save();
		ctx.strokeStyle = '#ffffff';
		ctx.lineWidth = 2 / this.camera.scale;
		ctx.lineCap = 'round';
		ctx.beginPath();
		ctx.moveTo(cx - r * 0.5, cy - r * 0.5);
		ctx.lineTo(cx + r * 0.5, cy + r * 0.5);
		ctx.moveTo(cx + r * 0.5, cy - r * 0.5);
		ctx.lineTo(cx - r * 0.5, cy + r * 0.5);
		ctx.stroke();
		ctx.restore();
	}

	_drawWaitingClock(cx, cy, r, colors) {
		const ctx = this.ctx;
		const time = performance.now() / 1000;

		// Pulsing effect (opacity oscillates)
		const pulse = 0.5 + 0.5 * Math.sin(time * 4);

		ctx.save();
		ctx.globalAlpha = 0.5 + pulse * 0.5;

		// Draw clock circle
		ctx.strokeStyle = '#ffffff';
		ctx.lineWidth = 1.5 / this.camera.scale;
		ctx.beginPath();
		ctx.arc(cx, cy, r, 0, Math.PI * 2);
		ctx.stroke();

		// Draw clock hands (animated)
		const minuteAngle = (time * 0.5) % (Math.PI * 2) - Math.PI / 2;
		const hourAngle = (time * 0.05) % (Math.PI * 2) - Math.PI / 2;

		ctx.lineWidth = 1.5 / this.camera.scale;
		ctx.lineCap = 'round';

		// Hour hand (shorter)
		ctx.beginPath();
		ctx.moveTo(cx, cy);
		ctx.lineTo(cx + Math.cos(hourAngle) * r * 0.4, cy + Math.sin(hourAngle) * r * 0.4);
		ctx.stroke();

		// Minute hand (longer)
		ctx.beginPath();
		ctx.moveTo(cx, cy);
		ctx.lineTo(cx + Math.cos(minuteAngle) * r * 0.7, cy + Math.sin(minuteAngle) * r * 0.7);
		ctx.stroke();

		ctx.restore();
	}

	_refreshNodeInteractivity(node) {
		// Always update chain state first
		const chainCompleteness = this._updateNodeChainState(node);
		const isChainComplete = chainCompleteness.complete;

		// Only process decorators if they exist
		const decorators = this._schemaDecorators[node.schemaName]?.[node.modelName];
		if (decorators) {
			// Update button enabled states
			if (node._buttonStacks) {
				for (const stack of ['top', 'bottom']) {
					for (const btn of node._buttonStacks[stack] || []) {
						const originalConfig = decorators.buttons?.find(b => b.id === btn.id);
						btn.enabled = (originalConfig?.enabled !== false) && isChainComplete;
					}
				}
			}

			// Update dropzone
			if (node._dropZone && decorators.dropzone) {
				node._dropZone.enabled = isChainComplete;
				node._dropZone.label = isChainComplete
					? (decorators.dropzone.label || 'Drop file here')
					: this._getIncompleteChainMessage(chainCompleteness);
			}
		}

		this.draw();
	}

	// ========================================================================
	// PUBLIC API
	// ========================================================================

	_createAPI() {
		const self = this;
		return {
			lock: {
				lock: (r, p) => self.lock(r, p),
				unlock: () => self.unlock(),
				isLocked: () => self.isLocked,
				getReason: () => self.lockReason
			},

			schema: {
				list: () => self.graph.getRegisteredSchemas(),
				info: (name) => self.graph.getSchemaInfo(name),
				isWorkflow: (name) => self.graph.isWorkflowSchema(name),
				enable: (name) => self.graph.enableSchema(name),
				disable: (name) => self.graph.disableSchema(name),
				toggle: (name) => self.graph.toggleSchema(name),
				isEnabled: (name) => self.graph.isSchemaEnabled(name),
				getEnabled: () => self.graph.getEnabledSchemas()
			},

			node: {
				create: (type, x = 0, y = 0) => {
					// Validate Start/End node constraints
					const canCreate = self._canCreateNodeType(type);
					if (!canCreate.allowed) {
						self.showError(canCreate.reason);
						return null;
					}
					try { const node = self.graph.createNode(type); node.pos = [x, y]; self.draw(); return node; } catch (e) { self.showError('Failed to create node: ' + e.message); return null; }
				},
				delete: (nodeOrId) => { const node = typeof nodeOrId === 'string' ? self.graph.getNodeById(nodeOrId) : nodeOrId; if (!node) return false; self.removeNode(node); return true; },
				select: (nodeOrId, add = false) => { const node = typeof nodeOrId === 'string' ? self.graph.getNodeById(nodeOrId) : nodeOrId; if (!node) return false; self.selectNode(node, add); return true; },
				list: () => [...self.graph.nodes],
				getById: (id) => self.graph.getNodeById(id),
				getSelected: () => Array.from(self.selectedNodes),
				clearSelection: () => self.clearSelection()
			},

			link: {
				create: (sourceOrId, sourceSlot, targetOrId, targetSlot) => {
					const sourceNode = typeof sourceOrId === 'string' ? self.graph.getNodeById(sourceOrId) : sourceOrId;
					const targetNode = typeof targetOrId === 'string' ? self.graph.getNodeById(targetOrId) : targetOrId;
					if (!sourceNode || !targetNode) return null;
					const link = self.graph.connect(sourceNode, sourceSlot, targetNode, targetSlot);
					if (link) { self.eventBus.emit('link:created', { linkId: link.id }); self.draw(); }
					return link;
				},
				delete: (linkId) => { const link = self.graph.links[linkId]; if (!link) return false; const targetNode = self.graph.getNodeById(link.target_id); if (targetNode) self.removeLink(linkId, targetNode, link.target_slot); return true; },
				list: () => ({ ...self.graph.links })
			},

			graph: {
				export: (includeCamera = true) => self.graph.serialize(includeCamera, self.camera),
				import: (data, restoreCamera = true) => { try { self.graph.deserialize(data, restoreCamera, self.camera); self.ui?.update?.schemaList?.(); self.ui?.update?.nodeTypesList?.(); if (restoreCamera) self.eventBus.emit('ui:update', { id: 'zoomLevel', content: Math.round(self.camera.scale * 100) + '%' }); self._refreshAllCompleteness(); self.eventBus.emit('graph:imported', {}); return true; } catch (e) { self.showError('Import failed: ' + e.message); return false; } },
				download: () => self.exportGraph(),
				clear: () => { self.graph.nodes = []; self.graph.links = {}; self.graph._nodes_by_id = {}; self.graph.last_link_id = 0; self.clearSelection(); self.draw(); }
			},

			workflow: {
				registerSchema: (name, code) => {
					// Parse workflow schema
					const parser = new WorkflowSchemaParser();
					const parsed = parser.parse(code);

					// Parse decorators
					const decorators = self._decoratorParser.parse(code);
					self._schemaDecorators[name] = decorators;

					// Store schema
					if (!self.graph.schemas) self.graph.schemas = {};
					self.graph.schemas[name] = {
						code,
						parsed: parsed.models,
						isWorkflow: true,
						fieldRoles: parsed.fieldRoles,
						defaults: parsed.defaults,
						enabled: false
					};

					// Create factory
					if (!self.graph.workflowFactories) self.graph.workflowFactories = {};
					const factory = new WorkflowNodeFactory(self.graph, parsed, name);
					factory.app = self;
					self.graph.workflowFactories[name] = factory;

					// Register node types as constructors (not plain functions)
					for (const modelName of Object.keys(parsed.models)) {
						const fullType = `${name}.${modelName}`;

						// Capture variables for closure
						const capturedFactory = factory;
						const capturedModelName = modelName;

						// Create a constructor function
						function WorkflowNodeType(nodeData = {}) {
							const node = capturedFactory.createNode(capturedModelName, nodeData);
							Object.assign(this, node);
							Object.setPrototypeOf(this, node);
						}

						WorkflowNodeType.title = modelName.replace(/([A-Z])/g, ' $1').trim();
						WorkflowNodeType.type = fullType;

						self.graph.nodeTypes[fullType] = WorkflowNodeType;
					}

					self.eventBus.emit(GraphEvents.SCHEMA_REGISTERED, { schemaName: name });
					console.log(`✔ Schema registered: ${name} (${Object.keys(parsed.models).length} models, ${Object.keys(decorators).length} decorated)`);
					return true;
				},

				import: (data, schemaName, options) => { try { self.graph.importWorkflow(data, schemaName, options); self.ui?.update?.schemaList?.(); self.ui?.update?.nodeTypesList?.(); self._refreshAllCompleteness(); return true; } catch (e) { self.showError('Workflow import failed: ' + e.message); return false; } },
				export: (schemaName, workflowInfo, options) => self.graph.exportWorkflow(schemaName, workflowInfo, options),
				download: (schemaName, workflowInfo = {}, options = {}) => {
					const workflow = self.graph.exportWorkflow(schemaName, workflowInfo, options);
					const jsonString = JSON.stringify(workflow, null, '\t');
					const blob = new Blob([jsonString], { type: 'application/json' });
					const url = URL.createObjectURL(blob);
					const a = document.createElement('a');
					a.href = url;
					a.download = options.filename || `workflow-${new Date().toISOString().slice(0, 10)}.json`;
					document.body.appendChild(a);
					a.click();
					document.body.removeChild(a);
					URL.revokeObjectURL(url);
					self.eventBus.emit('workflow:exported', {});
				},
				isWorkflowSchema: (name) => self.graph.isWorkflowSchema(name),

				getMultiInputKeys: (node, fieldName) => self._getMultiInputKeys(node, fieldName),
				getMultiOutputKeys: (node, fieldName) => self._getMultiOutputKeys(node, fieldName),
				addMultiInputSlot: (node, fieldName, key) => self._addMultiInputSlot(node, fieldName, key),
				removeMultiInputSlot: (node, fieldName, key) => self._removeMultiInputSlot(node, fieldName, key),
				addMultiOutputSlot: (node, fieldName, key) => self._addMultiOutputSlot(node, fieldName, key),
				removeMultiOutputSlot: (node, fieldName, key) => self._removeMultiOutputSlot(node, fieldName, key),
				renameMultiInputSlot: (node, fieldName, oldKey, newKey) => self._renameMultiInputSlot(node, fieldName, oldKey, newKey),
				renameMultiOutputSlot: (node, fieldName, oldKey, newKey) => self._renameMultiOutputSlot(node, fieldName, oldKey, newKey),

				/**
				 * Workflow Validation API - Validate workflow structure
				 */

				/**
				 * Validate the current workflow
				 * @returns {{valid: boolean, errors: string[], warnings: string[]}}
				 */
				validate: () => self.validateWorkflow(),

				/**
				 * Check if a path exists from Start to End
				 * @returns {{valid: boolean, reason: string|null, path: number[]|null}}
				 */
				validatePath: () => self._validateStartToEndPath(),

				/**
				 * Check if a node type can be created (validates Start/End constraints)
				 * @param {string} nodeType - The node type to check
				 * @returns {{allowed: boolean, reason: string|null}}
				 */
				canCreateNodeType: (nodeType) => self._canCreateNodeType(nodeType),

				/**
				 * Get Start node(s) in the graph
				 * @returns {Array} Array of Start nodes
				 */
				getStartNodes: () => self._getStartNodes(),

				/**
				 * Get End node(s) in the graph
				 * @returns {Array} Array of End nodes
				 */
				getEndNodes: () => self._getEndNodes(),

				/**
				 * Count Start nodes
				 * @returns {number}
				 */
				countStartNodes: () => self._countStartNodes(),

				/**
				 * Count End nodes
				 * @returns {number}
				 */
				countEndNodes: () => self._countEndNodes(),

				/**
				 * Check if workflow is ready to run (has Start, End, and path)
				 * @returns {{ready: boolean, reason: string|null}}
				 */
				isReady: () => {
					const validation = self.validateWorkflow();
					if (!validation.valid) {
						return { ready: false, reason: validation.errors[0] || 'Validation failed' };
					}
					return { ready: true, reason: null };
				}
			},

			view: {
				center: () => self.centerView(),
				resetZoom: () => self.resetZoom(),
				setZoom: (scale) => { self.camera.scale = Math.max(0.1, Math.min(5, scale)); self.eventBus.emit('ui:update', { id: 'zoomLevel', content: Math.round(self.camera.scale * 100) + '%' }); self.draw(); },
				getZoom: () => self.camera.scale,
				setPosition: (x, y) => { self.camera.x = x; self.camera.y = y; self.draw(); },
				getPosition: () => { return { ...self.camera }; },
				pan: (dx, dy) => { self.camera.x += dx; self.camera.y += dy; self.draw(); },
				reset: () => { self.api.view.setPosition(0, 0); self.resetZoom(); }
			},

			layout: { apply: (type) => self.applyLayout(type) },
			theme: { cycle: () => self.cycleTheme(), get: () => self.themes[self.currentThemeIndex], set: (t) => { const idx = self.themes.indexOf(t); if (idx !== -1) { self.currentThemeIndex = idx; self.applyTheme(t); localStorage.setItem('schemagraph-theme', t); self.draw(); } } },
			style: { set: (s) => { self.drawingStyleManager.setStyle(s); self.draw(); }, get: () => self.drawingStyleManager.getCurrentStyleName(), list: () => Object.keys(self.drawingStyleManager.styles) },
			analytics: { getMetrics: () => self.analytics.getMetrics(), getSession: () => self.analytics.getSessionMetrics(), endSession: () => self.analytics.endSession() },
			voice: { start: () => self.voiceController.startListening(), stop: () => self.voiceController.stopListening(), isListening: () => self.voiceController.isListening },

			events: {
				on: (event, cb) => self.eventBus.on(event, cb),
				once: (event, cb) => self.eventBus.once(event, cb),
				off: (event, cb) => self.eventBus.off(event, cb),
				emit: (event, data) => self.eventBus.emit(event, data),
				types: GraphEvents,
				enableDebug: () => self.eventBus.enableDebug(),
				disableDebug: () => self.eventBus.disableDebug(),
				onNodeCreated: (cb) => self.eventBus.on(GraphEvents.NODE_CREATED, cb),
				onNodeRemoved: (cb) => self.eventBus.on(GraphEvents.NODE_REMOVED, cb),
				onNodeMoved: (cb) => self.eventBus.on(GraphEvents.NODE_MOVED, cb),
				onLinkCreated: (cb) => self.eventBus.on(GraphEvents.LINK_CREATED, cb),
				onLinkRemoved: (cb) => self.eventBus.on(GraphEvents.LINK_REMOVED, cb),
				onGraphChanged: (cb) => self.eventBus.on(GraphEvents.GRAPH_CHANGED, cb),
				onFieldChanged: (cb) => self.eventBus.on(GraphEvents.FIELD_CHANGED, cb),
				onSelectionChanged: (cb) => self.eventBus.on(GraphEvents.SELECTION_CHANGED, cb)
			},

			interactive: {
				addButton: (node, stack, config) => self.addNodeButton(node, stack, config),
				removeButton: (node, buttonId) => self.removeNodeButton(node, buttonId),
				setDropZone: (node, config) => self.setNodeDropZone(node, config),
				removeDropZone: (node) => self.removeNodeDropZone(node),
				registerCallback: (id, fn) => self.registerCallback(id, fn),
				ButtonStack,
				DropZoneArea
			},

			decorators: {
				parse: (code) => self._decoratorParser.parse(code),
				getForModel: (schema, model) => self._schemaDecorators[schema]?.[model],
				applyToNode: (node) => self._applyDecoratorsToNode(node)
			},

			tooltips: {
				enableNodeTooltips: () => { self._nodeTooltipsEnabled = true; },
				disableNodeTooltips: () => { self._nodeTooltipsEnabled = false; self._hideNodeHeaderTooltip(); },
				isNodeTooltipsEnabled: () => self._nodeTooltipsEnabled,

				enableFieldTooltips: () => { self._fieldTooltipsEnabled = true; },
				disableFieldTooltips: () => { self._fieldTooltipsEnabled = false; self._hideTooltip(); },
				isFieldTooltipsEnabled: () => self._fieldTooltipsEnabled,

				enableAll: () => { self._nodeTooltipsEnabled = true; self._fieldTooltipsEnabled = true; },
				disableAll: () => {
					self._nodeTooltipsEnabled = false;
					self._fieldTooltipsEnabled = false;
					self._hideTooltip();
					self._hideNodeHeaderTooltip();
				}
			},

			comboBox: {
				setBaseUrl: (url) => { self._comboBoxBaseUrl = url; },
				clearCache: (provider) => {
					if (provider) {
						delete self[`_comboCache_${provider}`];
					} else {
						for (const key of Object.keys(self)) {
							if (key.startsWith('_comboCache_')) delete self[key];
						}
					}
				}
			},

			templates: {
				setBaseUrl: (url) => { self._templateBaseUrl = url; },
			},

			generate: {
				setBaseUrl: (url) => { self._generateBaseUrl = url; },
			},

			completeness: {
				check: (nodeOrId) => {
					const node = typeof nodeOrId === 'string' ? self.graph.getNodeById(nodeOrId) : nodeOrId;
					return node ? self._getNodeCompleteness(node) : null;
				},
				checkChain: (nodeOrId) => {
					const node = typeof nodeOrId === 'string' ? self.graph.getNodeById(nodeOrId) : nodeOrId;
					return node ? self._getChainCompleteness(node) : null;
				},
				checkAll: () => {
					const results = {};
					for (const node of self.graph.nodes) {
						results[node.id] = {
							self: self._getNodeCompleteness(node),
							chain: self._getChainCompleteness(node)
						};
					}
					return results;
				},
				isComplete: (nodeOrId) => {
					const node = typeof nodeOrId === 'string' ? self.graph.getNodeById(nodeOrId) : nodeOrId;
					return node ? self._getNodeCompleteness(node).complete : false;
				},
				isChainComplete: (nodeOrId) => {
					const node = typeof nodeOrId === 'string' ? self.graph.getNodeById(nodeOrId) : nodeOrId;
					return node ? self._getChainCompleteness(node).complete : false;
				},
				refresh: (nodeOrId) => {
					if (nodeOrId) {
						const node = typeof nodeOrId === 'string' ? self.graph.getNodeById(nodeOrId) : nodeOrId;
						if (node) self._updateNodeCompletenessState(node);
					}
					self.draw();
				},
				refreshAll: () => {
					self._refreshAllCompleteness();
				}
			},

			extensions: {
				get: (name) => self.extensions.get(name),
				list: () => self.extensions.list(),
				has: (name) => self.extensions.has(name),
				registry: self.extensions
			},

			features: {
				/**
				 * Get the current feature configuration
				 * @returns {Object} Current feature states
				 */
				get: () => ({ ...self._features }),

				/**
				 * Set feature configuration options
				 * @param {Object} options - Dictionary of feature flags to set
				 * @returns {Object} Updated feature states
				 */
				set: (options) => {
					if (!options || typeof options !== 'object') return self._features;

					for (const [key, value] of Object.entries(options)) {
						if (key in self._features && typeof value === 'boolean') {
							self._features[key] = value;
						}
					}

					// Sync tooltip flags with internal state
					self._nodeTooltipsEnabled = self._features.nodeTooltips;
					self._fieldTooltipsEnabled = self._features.fieldTooltips;

					// Hide tooltips if disabled
					if (!self._features.nodeTooltips) self._hideNodeHeaderTooltip?.();
					if (!self._features.fieldTooltips) self._hideTooltip?.();

					// Update toolbar visibility
					self._updateToolbarVisibility();

					// Update node types list (for nativeTypes feature)
					self.ui?.update?.nodeTypesList?.();

					// Save features to localStorage for persistence
					self.saveFeatures();

					self.draw();
					self.eventBus.emit('features:changed', { features: { ...self._features } });

					return { ...self._features };
				},

				/**
				 * Enable specific features
				 * @param {...string} featureNames - Names of features to enable
				 */
				enable: (...featureNames) => {
					const options = {};
					for (const name of featureNames) {
						if (name in self._features) options[name] = true;
					}
					return self.api.features.set(options);
				},

				/**
				 * Disable specific features
				 * @param {...string} featureNames - Names of features to disable
				 */
				disable: (...featureNames) => {
					const options = {};
					for (const name of featureNames) {
						if (name in self._features) options[name] = false;
					}
					return self.api.features.set(options);
				},

				/**
				 * Check if a specific feature is enabled
				 * @param {string} featureName - Name of the feature to check
				 * @returns {boolean} Whether the feature is enabled
				 */
				isEnabled: (featureName) => self._features[featureName] === true,

				/**
				 * Get list of available feature names
				 * @returns {string[]} Array of feature names
				 */
				list: () => Object.keys(self._features),

				/**
				 * Reset all features to default (all enabled)
				 * @returns {Object} Updated feature states
				 */
				reset: () => {
					const defaults = {};
					for (const key of Object.keys(self._features)) {
						defaults[key] = true;
					}
					return self.api.features.set(defaults);
				}
			},

			canvasDrop: {
				/**
				 * Get the current canvas drop configuration
				 * @returns {Object} Current config (includes schema types)
				 */
				getConfig: () => ({
					...self._canvasDropConfig,
					metaNodeType: self._schemaTypeRoles.sourceMeta[0] || null,
					dataNodeType: self._schemaTypeRoles.dataTensor[0] || null,
					previewNodeType: self._schemaTypeRoles.preview[0] || null,
					metaInputSlot: self._schemaTypeRoles.metaInputSlot
				}),

				/**
				 * Enable or disable canvas-level file drops
				 * @param {boolean} enabled - Whether to enable canvas drops
				 */
				setEnabled: (enabled) => {
					self._canvasDropConfig.enabled = !!enabled;
				},

				/**
				 * Set the accept filter for dropped files
				 * @param {string|string[]|Function} accept - MIME pattern(s) or filter function
				 */
				setAccept: (accept) => {
					self._canvasDropConfig.accept = accept;
				},

				/**
				 * Configure node types - redirects to schemaTypes.setTypes
				 * @deprecated Use schemaTypes.setTypes() instead
				 */
				setNodeTypes: (config) => {
					self.api.schemaTypes.setTypes({
						sourceMeta: config.metaNode,
						dataTensor: config.dataNode,
						preview: config.previewNode,
						metaInputSlot: config.metaSlot
					});
				},

				/**
				 * Set a custom creation callback to override default node creation
				 * @param {Function|null} callback - Custom callback or null to use default
				 */
				setCreationCallback: (callback) => {
					self._canvasDropCreationCallback = typeof callback === 'function' ? callback : null;
				},

				/**
				 * Auto-detect node types - redirects to schemaTypes.autoDetectFromSchema
				 * @deprecated Use schemaTypes.autoDetectFromSchema() instead
				 */
				autoDetectFromSchema: (schemaName) => {
					return self.api.schemaTypes.autoDetectFromSchema(schemaName);
				},

				/**
				 * Check if canvas drop is properly configured
				 * @returns {Object} Status with isReady flag and details
				 */
				getStatus: () => {
					const roles = self._schemaTypeRoles;
					const metaType = roles.sourceMeta[0];
					const dataType = roles.dataTensor[0];
					const previewType = roles.preview[0];

					const hasMetaType = !metaType || !!self.graph.nodeTypes[metaType];
					const hasDataType = !!dataType && !!self.graph.nodeTypes[dataType];
					const hasPreviewType = !previewType || !!self.graph.nodeTypes[previewType];
					const hasCallback = !!self._canvasDropCreationCallback;

					return {
						isReady: self._canvasDropConfig.enabled && (hasCallback || hasDataType),
						enabled: self._canvasDropConfig.enabled,
						metaNodeType: metaType,
						metaNodeValid: hasMetaType,
						dataNodeType: dataType,
						dataNodeValid: hasDataType,
						previewNodeType: previewType,
						previewNodeValid: hasPreviewType,
						hasCustomCallback: hasCallback,
						accept: self._canvasDropConfig.accept
					};
				}
			},

			schemaTypes: {
				/**
				 * Get the current schema type roles configuration
				 * @returns {Object} Current configuration
				 */
				getConfig: () => ({ ...self._schemaTypeRoles }),

				/**
				 * Configure node type roles for the schema
				 * @param {Object} config - Type role configuration
				 * @param {string|string[]} config.dataTensor - Node type(s) that hold data
				 * @param {string|string[]} config.sourceMeta - Node type(s) that hold metadata
				 * @param {string|string[]} config.preview - Node type(s) that display previews
				 * @param {string|string[]} config.startNode - Node type(s) for workflow start
				 * @param {string|string[]} config.endNode - Node type(s) for workflow end
				 * @param {string} config.metaInputSlot - Slot name for meta connection (default: 'meta')
				 */
				setTypes: (config) => {
					if (config.dataTensor) {
						self._schemaTypeRoles.dataTensor = Array.isArray(config.dataTensor)
							? config.dataTensor : [config.dataTensor];
					}
					if (config.sourceMeta) {
						self._schemaTypeRoles.sourceMeta = Array.isArray(config.sourceMeta)
							? config.sourceMeta : [config.sourceMeta];
					}
					if (config.preview) {
						self._schemaTypeRoles.preview = Array.isArray(config.preview)
							? config.preview : [config.preview];
					}
					if (config.startNode) {
						self._schemaTypeRoles.startNode = Array.isArray(config.startNode)
							? config.startNode : [config.startNode];
					}
					if (config.endNode) {
						self._schemaTypeRoles.endNode = Array.isArray(config.endNode)
							? config.endNode : [config.endNode];
					}
					if (config.agentChat) {
						self._schemaTypeRoles.agentChat = Array.isArray(config.agentChat)
							? config.agentChat : [config.agentChat];
					}
					if (config.toolCall) {
						self._schemaTypeRoles.toolCall = Array.isArray(config.toolCall)
							? config.toolCall : [config.toolCall];
					}
					if (config.metaInputSlot) {
						self._schemaTypeRoles.metaInputSlot = config.metaInputSlot;
					}
					if (config.workflowOptions) {
						self._schemaTypeRoles.workflowOptions = config.workflowOptions;
					}
					if (config.workflowExecutionOptions) {
						self._schemaTypeRoles.workflowExecutionOptions = config.workflowExecutionOptions;
					}
					if (config.previewSlotMap) {
						// Map of input slot names to output slot names for preview link preservation
						// e.g., { 'input': 'get', 'data': 'output' }
						self._schemaTypeRoles.previewSlotMap = { ...config.previewSlotMap };
					}
					if (config.hiddenFields) {
						self._hiddenFieldNames = Array.isArray(config.hiddenFields)
							? config.hiddenFields : [config.hiddenFields];
					}
					if (config.pairedNodes) {
						// Array of [startType, endType] pairs, e.g. [['loop_start_flow', 'loop_end_flow']]
						// Both directions are registered automatically
						self._setTypes = {};
						for (const [startType, endType] of config.pairedNodes) {
							self._setTypes[startType] = endType;
							self._setTypes[endType] = startType;
						}
					}
				},

				/**
				 * Configure section-based header colors for nodes
				 * Colors are applied based on the 'section' field in @node_info decorator
				 * @param {Object<string, string>} colors - Map of section name to hex color
				 * @example
				 * schemaTypes.setSectionColors({
				 *   'Data Sources': '#4a7c59',
				 *   'Configurations': '#5c7caa',
				 *   'Workflow': '#7a5c8a'
				 * });
				 */
				setSectionColors: (colors) => {
					Object.assign(self._sectionColors, colors);
				},

				/**
				 * Get the configured section colors
				 * @returns {Object<string, string>} Map of section name to hex color
				 */
				getSectionColors: () => ({ ...self._sectionColors }),

				/**
				 * Check if a node is a data tensor type
				 * @param {Object} node - The node to check
				 * @returns {boolean} True if node is a data tensor type
				 */
				isDataTensor: (node) => self._isDataTensorNode(node),

				/**
				 * Check if a node is a source meta type
				 * @param {Object} node - The node to check
				 * @returns {boolean} True if node is a source meta type
				 */
				isSourceMeta: (node) => self._isSourceMetaNode(node),

				/**
				 * Check if a node is a preview type
				 * @param {Object} node - The node to check
				 * @returns {boolean} True if node is a preview type
				 */
				isPreview: (node) => self._isPreviewFlowNode(node),

				/**
				 * Check if a node is a start node type
				 * @param {Object} node - The node to check
				 * @returns {boolean} True if node is a start node type
				 */
				isStartNode: (node) => self._isStartNode(node),

				/**
				 * Check if a node is an end node type
				 * @param {Object} node - The node to check
				 * @returns {boolean} True if node is an end node type
				 */
				isEndNode: (node) => self._isEndNode(node),

				/**
				 * Check if a node is a tool call type
				 * @param {Object} node - The node to check
				 * @returns {boolean} True if node is a tool call type
				 */
				isToolCall: (node) => self._isToolCallNode(node),

				/**
				 * Auto-detect type roles from a registered schema
				 * @param {string} schemaName - Name of the registered schema
				 * @returns {boolean} Whether types were detected
				 */
				autoDetectFromSchema: (schemaName) => {
					const schema = self.graph.schemas?.[schemaName];
					if (!schema?.parsed) return false;

					const models = Object.keys(schema.parsed);

					// Look for meta nodes
					const metaNodes = models.filter(m =>
						m.includes('Meta') || m === 'SourceMeta'
					).map(m => `${schemaName}.${m}`);

					// Look for data tensor nodes
					const dataNodes = models.filter(m =>
						m.includes('Tensor') || m.includes('Data') ||
						m === 'DataTensor' || m === 'TensorType'
					).map(m => `${schemaName}.${m}`);

					// Look for preview nodes
					const previewNodes = models.filter(m =>
						m.includes('Preview') || m === 'PreviewFlow'
					).map(m => `${schemaName}.${m}`);

					// Look for start nodes
					const startNodes = models.filter(m =>
						m === 'StartFlow' || m.includes('Start')
					).map(m => `${schemaName}.${m}`);

					// Look for end nodes
					const endNodes = models.filter(m =>
						m === 'EndFlow' || (m.includes('End') && !m.includes('Backend'))
					).map(m => `${schemaName}.${m}`);

					// Look for workflow options
					const workflowOptionsModel = models.find(m => m === 'WorkflowOptions');

					// Look for workflow execution options
					const workflowExecOptionsModel = models.find(m => m === 'WorkflowExecutionOptions');

					if (metaNodes.length > 0) self._schemaTypeRoles.sourceMeta = metaNodes;
					if (dataNodes.length > 0) self._schemaTypeRoles.dataTensor = dataNodes;
					if (previewNodes.length > 0) self._schemaTypeRoles.preview = previewNodes;
					if (startNodes.length > 0) self._schemaTypeRoles.startNode = startNodes;
					if (endNodes.length > 0) self._schemaTypeRoles.endNode = endNodes;
					if (workflowOptionsModel) self._schemaTypeRoles.workflowOptions = workflowOptionsModel;
					if (workflowExecOptionsModel) self._schemaTypeRoles.workflowExecutionOptions = workflowExecOptionsModel;

					console.log(`[SchemaGraph] Schema types auto-detect: meta=${metaNodes.join(',') || 'none'}, data=${dataNodes.join(',') || 'none'}, preview=${previewNodes.join(',') || 'none'}, start=${startNodes.join(',') || 'none'}, end=${endNodes.join(',') || 'none'}, workflowOptions=${workflowOptionsModel || 'none'}, workflowExecOptions=${workflowExecOptionsModel || 'none'}`);
					return metaNodes.length > 0 || dataNodes.length > 0 || previewNodes.length > 0 || startNodes.length > 0 || endNodes.length > 0;
				},

				/**
				 * Get model information from a registered schema
				 * @param {string} schemaName - Name of the registered schema
				 * @param {string} modelName - Name of the model to retrieve
				 * @returns {Object|null} Model info with fields, fieldRoles, and defaults
				 */
				getModelInfo: (schemaName, modelName) => {
					const schema = self.graph.schemas?.[schemaName];
					if (!schema?.parsed) return null;

					const fields = schema.parsed[modelName];
					if (!fields) return null;

					return {
						name: modelName,
						fields: fields,
						fieldRoles: schema.fieldRoles?.[modelName] || {},
						defaults: schema.defaults?.[modelName] || {}
					};
				},

				/**
				 * Get workflow options model info
				 * @param {string} schemaName - Name of the registered schema
				 * @returns {Object|null} WorkflowOptions model info
				 */
				getWorkflowOptionsInfo: (schemaName) => {
					const modelName = self._schemaTypeRoles.workflowOptions;
					if (!modelName) return null;
					return self.api.schemaTypes.getModelInfo(schemaName, modelName);
				},

				/**
				 * Get workflow execution options model info
				 * @param {string} schemaName - Name of the registered schema
				 * @returns {Object|null} WorkflowExecutionOptions model info
				 */
				getWorkflowExecutionOptionsInfo: (schemaName) => {
					const modelName = self._schemaTypeRoles.workflowExecutionOptions;
					if (!modelName) return null;
					return self.api.schemaTypes.getModelInfo(schemaName, modelName);
				}
			},

			/**
			 * Edge Preview API - Insert/remove preview nodes on links
			 */
			edgePreview: {
				/**
				 * Enable or disable edge preview functionality
				 * @param {boolean} enabled - Whether to enable edge preview
				 */
				setEnabled: (enabled) => {
					self._edgePreviewConfig.enabled = enabled;
				},

				/**
				 * Check if edge preview is enabled
				 * @returns {boolean}
				 */
				isEnabled: () => self._features.edgePreview && self._edgePreviewConfig.enabled,

				/**
				 * Set the hit distance for detecting link hover
				 * @param {number} distance - Distance in pixels
				 */
				setHitDistance: (distance) => {
					self._edgePreviewConfig.linkHitDistance = distance;
				},

				/**
				 * Get the currently hovered link (if any)
				 * @returns {Object|null} The hovered link or null
				 */
				getHoveredLink: () => self._hoveredLink,

				/**
				 * Check if a preview can be inserted on a link
				 * @param {Object|number} linkOrId - Link object or link ID
				 * @returns {{allowed: boolean, reason: string|null}}
				 */
				canInsertOnLink: (linkOrId) => {
					const link = typeof linkOrId === 'object' ? linkOrId : self.graph.links[linkOrId];
					return self._canInsertPreviewOnLink(link);
				},

				/**
				 * Insert a preview node on a link
				 * @param {Object|number} linkOrId - Link object or link ID
				 * @param {number} [x] - X position (optional, uses midpoint if not provided)
				 * @param {number} [y] - Y position (optional, uses midpoint if not provided)
				 * @returns {Object|null} The created preview node or null
				 */
				insertOnLink: (linkOrId, x, y) => {
					const link = typeof linkOrId === 'object' ? linkOrId : self.graph.links[linkOrId];
					if (!link) return null;

					// Calculate midpoint if position not provided
					if (x === undefined || y === undefined) {
						const src = self.graph.getNodeById(link.origin_id);
						const tgt = self.graph.getNodeById(link.target_id);
						if (!src || !tgt) return null;
						x = (src.pos[0] + src.size[0] + tgt.pos[0]) / 2;
						y = (src.pos[1] + tgt.pos[1]) / 2;
					}

					return self.insertPreviewOnLink(link, x, y);
				},

				/**
				 * Remove a preview node and restore the original connection
				 * @param {Object|number} nodeOrId - Preview node or node ID
				 * @returns {Object|null} The restored link or null
				 */
				remove: (nodeOrId) => {
					const node = typeof nodeOrId === 'object' ? nodeOrId : self.graph.getNodeById(nodeOrId);
					return self.removePreviewNodeAndRestore(node);
				},

				/**
				 * Remove all edge preview nodes and restore connections
				 * @returns {number} Number of preview nodes removed
				 */
				removeAll: () => {
					let count = 0;
					for (const node of [...self.graph.nodes]) {
						if (node.extra?._isEdgePreview && self._isPreviewFlowNode(node)) {
							if (self.removePreviewNodeAndRestore(node)) count++;
						}
					}
					return count;
				},

				/**
				 * Get the original edge info stored in a preview node
				 * @param {Object|number} nodeOrId - Preview node or node ID
				 * @returns {Object|null} Original edge info or null
				 */
				getOriginalEdgeInfo: (nodeOrId) => {
					const node = typeof nodeOrId === 'object' ? nodeOrId : self.graph.getNodeById(nodeOrId);
					return self._isPreviewFlowNode(node) ? node.extra?._originalEdgeInfo : null;
				},

				/**
				 * List all edge preview nodes
				 * @returns {Array} Array of edge preview nodes
				 */
				list: () => self.graph.nodes.filter(n => n.extra?._isEdgePreview && self._isPreviewFlowNode(n)),

				/**
				 * Get the current configuration
				 * @returns {Object} Current edge preview configuration
				 */
				getConfig: () => ({
					enabled: self._edgePreviewConfig.enabled,
					linkHitDistance: self._edgePreviewConfig.linkHitDistance,
					featureEnabled: self._features.edgePreview
				})
			},
		};
	}

	// ========================================================================
	// UI CREATION
	// ========================================================================

	_createUI() {
		const self = this;
		return {
			init: () => {
				self.ui.buttons.setupAll();
				self.ui.update.schemaList();
				self.ui.update.nodeTypesList();
				self.ui.update.textScaling();
				self.ui.update.drawingStyle();
				// Apply saved feature settings
				self._updateToolbarVisibility();
			},
			util: {
				resizeCanvas: () => {
					const container = self.canvas.parentElement;
					if (container) {
						self.canvas.width = container.clientWidth;
						self.canvas.height = container.clientHeight;
						self.draw();
					}
				}
			},
			update: {
				schemaList: () => {
					const listEl = document.getElementById('sg-schemaList');
					if (listEl) listEl.textContent = self.graph.getRegisteredSchemas().join(', ') || 'None';
				},
				nodeTypesList: () => {
					const listEl = document.getElementById('sg-nodeTypesList');
					if (listEl) {
						let types = Object.keys(self.graph.nodeTypes);
						// Filter out native types if feature is disabled
						if (!self._features.nativeTypes) {
							types = types.filter(t => !t.startsWith('Native.'));
						}
						listEl.textContent = types.join(', ') || 'None';
					}
				},
				textScaling: () => {
					const label = document.getElementById('sg-textScalingLabel');
					const btn = document.getElementById('sg-textScalingToggle');
					if (label) label.textContent = self.textScalingMode === 'scaled' ? 'Text: Scaled' : 'Text: Fixed';
					if (btn) btn.classList.toggle('active', self.textScalingMode === 'scaled');
				},
				drawingStyle: () => {
					const select = document.getElementById('sg-drawingStyleSelect');
					if (select) select.value = self.drawingStyleManager.getCurrentStyleName();
				},
				analytics: () => {
					const metrics = self.analytics.getSessionMetrics();
					const m = self.analytics.getMetrics();
					document.getElementById('sg-sessionId') && (document.getElementById('sg-sessionId').textContent = metrics.sessionId);
					document.getElementById('sg-sessionDuration') && (document.getElementById('sg-sessionDuration').textContent = Math.round(metrics.duration / 1000) + 's');
					document.getElementById('sg-totalEvents') && (document.getElementById('sg-totalEvents').textContent = metrics.events);
					document.getElementById('sg-nodesCreated') && (document.getElementById('sg-nodesCreated').textContent = m.nodeCreated);
					document.getElementById('sg-nodesDeleted') && (document.getElementById('sg-nodesDeleted').textContent = m.nodeDeleted);
					document.getElementById('sg-linksCreated') && (document.getElementById('sg-linksCreated').textContent = m.linkCreated);
					document.getElementById('sg-linksDeleted') && (document.getElementById('sg-linksDeleted').textContent = m.linkDeleted);
				}
			},
			buttons: {
				setupAll: () => {
					// Upload Schema
					document.getElementById('sg-uploadSchemaBtn')?.addEventListener('click', () => document.getElementById('sg-uploadSchemaFile')?.click());
					document.getElementById('sg-uploadSchemaFile')?.addEventListener('change', (e) => {
						const file = e.target.files?.[0];
						if (!file) return;
						const reader = new FileReader();
						reader.onload = (ev) => {
							self.pendingSchemaCode = ev.target.result;
							document.getElementById('sg-schemaNameInput').value = file.name.replace('.py', '');
							document.getElementById('sg-schemaDialog')?.classList.add('show');
						};
						reader.readAsText(file);
						e.target.value = '';
					});

					// Schema Dialog
					document.getElementById('sg-schemaDialogCancel')?.addEventListener('click', () => { document.getElementById('sg-schemaDialog')?.classList.remove('show'); self.pendingSchemaCode = null; });
					document.getElementById('sg-schemaDialogConfirm')?.addEventListener('click', () => {
						const name = document.getElementById('sg-schemaNameInput')?.value?.trim();
						const indexType = document.getElementById('sg-schemaIndexTypeInput')?.value?.trim() || 'int';
						const rootType = document.getElementById('sg-schemaRootTypeInput')?.value?.trim() || null;
						if (!name || !self.pendingSchemaCode) { self.showError('Name and code required'); return; }
						self.api.schema.register(name, self.pendingSchemaCode, indexType, rootType);
						document.getElementById('sg-schemaDialog')?.classList.remove('show');
						self.pendingSchemaCode = null;
					});

					// Export/Import Graph
					document.getElementById('sg-exportBtn')?.addEventListener('click', () => self.exportGraph());
					document.getElementById('sg-importBtn')?.addEventListener('click', () => document.getElementById('sg-importFile')?.click());
					document.getElementById('sg-importFile')?.addEventListener('change', (e) => {
						const file = e.target.files?.[0];
						if (!file) return;
						const reader = new FileReader();
						reader.onload = (ev) => { try { self.api.graph.import(JSON.parse(ev.target.result), true); } catch (err) { self.showError('Import failed: ' + err.message); } };
						reader.readAsText(file);
						e.target.value = '';
					});

					// Export/Import Config
					document.getElementById('sg-exportConfigBtn')?.addEventListener('click', () => self.exportConfig());
					document.getElementById('sg-importConfigBtn')?.addEventListener('click', () => document.getElementById('sg-importConfigFile')?.click());

					// Export/Import Workflow
					document.getElementById('sg-exportWorkflowBtn')?.addEventListener('click', () => {
						const schemas = self.graph.getRegisteredSchemas().filter(s => self.graph.isWorkflowSchema(s));
						if (schemas.length === 0) { self.showError('No workflow schema registered'); return; }
						self.api.workflow.download(schemas[0]);
					});
					document.getElementById('sg-importWorkflowBtn')?.addEventListener('click', () => document.getElementById('sg-importWorkflowFile')?.click());
					document.getElementById('sg-importWorkflowFile')?.addEventListener('change', (e) => {
						const file = e.target.files?.[0];
						if (!file) return;
						const reader = new FileReader();
						reader.onload = (ev) => {
							try {
								const data = JSON.parse(ev.target.result);
								const schemas = self.graph.getRegisteredSchemas().filter(s => self.graph.isWorkflowSchema(s));
								if (schemas.length === 0) { self.showError('No workflow schema registered'); return; }
								self.api.workflow.import(data, schemas[0], {});
								self.centerView();
							} catch (err) { self.showError('Import failed: ' + err.message); }
						};
						reader.readAsText(file);
						e.target.value = '';
					});

					// Templates
					document.getElementById('sg-templatesBtn')?.addEventListener('click', () => self.toggleTemplatePanel());

					// Generate Workflow
					document.getElementById('sg-generateWorkflowBtn')?.addEventListener('click', () => self.showGenerateWorkflow());

					// View
					document.getElementById('sg-centerViewBtn')?.addEventListener('click', () => self.centerView());
					document.getElementById('sg-resetZoomBtn')?.addEventListener('click', () => self.resetZoom());
					document.getElementById('sg-layoutSelect')?.addEventListener('change', (e) => { if (e.target.value) { self.applyLayout(e.target.value); e.target.value = ''; } });

					// Style
					document.getElementById('sg-drawingStyleSelect')?.addEventListener('change', (e) => { self.drawingStyleManager.setStyle(e.target.value); self.draw(); });
					document.getElementById('sg-textScalingToggle')?.addEventListener('click', () => { self.textScalingMode = self.textScalingMode === 'fixed' ? 'scaled' : 'fixed'; self.saveTextScalingMode(); self.ui.update.textScaling(); self.draw(); });
					document.getElementById('sg-themeBtn')?.addEventListener('click', () => self.cycleTheme());

					// Voice
					document.getElementById('sg-voiceStartBtn')?.addEventListener('click', () => { self.voiceController.startListening(); document.getElementById('sg-voiceStartBtn').style.display = 'none'; document.getElementById('sg-voiceStopBtn').style.display = ''; document.getElementById('sg-voiceStatus').textContent = '🎤 Listening...'; });
					document.getElementById('sg-voiceStopBtn')?.addEventListener('click', () => { self.voiceController.stopListening(); document.getElementById('sg-voiceStopBtn').style.display = 'none'; document.getElementById('sg-voiceStartBtn').style.display = ''; document.getElementById('sg-voiceStatus').textContent = ''; });
					self.eventBus.on('voice:stopped', () => { document.getElementById('sg-voiceStopBtn').style.display = 'none'; document.getElementById('sg-voiceStartBtn').style.display = ''; document.getElementById('sg-voiceStatus').textContent = ''; });

					// Analytics
					const hideAnalyticsPanel = () => {
						const panel = document.getElementById('sg-analyticsPanel');
						if (panel?.classList.contains('show')) {
							panel.classList.add('hiding');
							setTimeout(() => panel.classList.remove('show', 'hiding'), 300);
						}
					};
					const showAnalyticsPanel = () => {
						const panel = document.getElementById('sg-analyticsPanel');
						if (panel) {
							panel.classList.add('show');
							self.ui.update.analytics();
						}
					};
					document.getElementById('sg-analyticsToggleBtn')?.addEventListener('click', () => {
						const panel = document.getElementById('sg-analyticsPanel');
						panel?.classList.contains('show') ? hideAnalyticsPanel() : showAnalyticsPanel();
					});
					document.getElementById('sg-analyticsCloseBtn')?.addEventListener('click', () => hideAnalyticsPanel());
					document.getElementById('sg-refreshAnalyticsBtn')?.addEventListener('click', () => self.ui.update.analytics());
					document.getElementById('sg-exportAnalyticsBtn')?.addEventListener('click', () => {
						const data = { session: self.analytics.getSessionMetrics(), metrics: self.analytics.getMetrics(), history: self.eventBus.getHistory?.(null, 500) || [] };
						const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
						const url = URL.createObjectURL(blob);
						const a = document.createElement('a');
						a.href = url;
						a.download = 'analytics-' + new Date().toISOString().slice(0, 10) + '.json';
						document.body.appendChild(a);
						a.click();
						document.body.removeChild(a);
						URL.revokeObjectURL(url);
					});

					// Feature toggles
					document.getElementById('sg-feature-tooltips')?.addEventListener('change', (e) => {
						self.api.features.set({ nodeTooltips: e.target.checked, fieldTooltips: e.target.checked });
					});
					document.getElementById('sg-feature-completeness')?.addEventListener('change', (e) => {
						self.api.features.set({ completenessIndicators: e.target.checked });
					});
					document.getElementById('sg-feature-selection')?.addEventListener('change', (e) => {
						self.api.features.set({ nodeSelection: e.target.checked, multiSelection: e.target.checked });
					});
					document.getElementById('sg-feature-dragging')?.addEventListener('change', (e) => {
						self.api.features.set({ nodeDragging: e.target.checked });
					});
					document.getElementById('sg-feature-linking')?.addEventListener('change', (e) => {
						self.api.features.set({ linkCreation: e.target.checked, linkDeletion: e.target.checked });
					});
					document.getElementById('sg-feature-contextmenu')?.addEventListener('change', (e) => {
						self.api.features.set({ contextMenu: e.target.checked });
					});
					document.getElementById('sg-feature-zooming')?.addEventListener('change', (e) => {
						self.api.features.set({ zooming: e.target.checked });
					});
					document.getElementById('sg-feature-panning')?.addEventListener('change', (e) => {
						self.api.features.set({ panning: e.target.checked });
					});
					document.getElementById('sg-feature-sectioncolors')?.addEventListener('change', (e) => {
						self.api.features.set({ sectionColors: e.target.checked });
						self._reapplySectionColorsToAllNodes();
					});
					document.getElementById('sg-feature-preservepreviewlinks')?.addEventListener('change', (e) => {
						self.api.features.set({ preservePreviewLinks: e.target.checked });
					});
					document.getElementById('sg-feature-previewflash')?.addEventListener('change', (e) => {
						self.api.features.set({ previewFlash: e.target.checked });
					});
					document.getElementById('sg-feature-lockoverlay')?.addEventListener('change', (e) => {
						self.api.features.set({ lockOverlay: e.target.checked });
						const overlay = document.getElementById('sg-lockOverlay');
						if (overlay) {
							if (!e.target.checked) overlay.classList.remove('show');
							else if (self.isLocked) {
								overlay.classList.toggle('pending', self.lockPending);
								overlay.classList.add('show');
							}
						}
					});
					document.getElementById('sg-feature-hiddenfields')?.addEventListener('change', (e) => {
						self.api.features.set({ hiddenFields: e.target.checked });
						for (const node of self.graph.nodes) self._recalculateNodeSize(node);
						self.draw();
					});
					document.getElementById('sg-feature-prettyfieldnames')?.addEventListener('change', (e) => {
						self.api.features.set({ prettyFieldNames: e.target.checked });
						self.draw();
					});

					// Features panel toggle (show/hide with animation)
					const hideFeaturesPanel = () => {
						const panel = document.getElementById('sg-featuresPanel');
						if (panel?.classList.contains('show')) {
							panel.classList.add('hiding');
							setTimeout(() => panel.classList.remove('show', 'hiding'), 300);
						}
					};
					const showFeaturesPanel = () => {
						const panel = document.getElementById('sg-featuresPanel');
						if (panel) {
							panel.classList.add('show');
							self._syncFeatureCheckboxes();
						}
					};
					document.getElementById('sg-featuresToggleBtn')?.addEventListener('click', () => {
						const panel = document.getElementById('sg-featuresPanel');
						panel?.classList.contains('show') ? hideFeaturesPanel() : showFeaturesPanel();
					});
					document.getElementById('sg-featuresCloseBtn')?.addEventListener('click', () => hideFeaturesPanel());

					// Advanced options toggle within features panel
					document.getElementById('sg-features-advanced-toggle')?.addEventListener('click', () => {
						const panel = document.getElementById('sg-features-advanced-panel');
						const btn = document.getElementById('sg-features-advanced-toggle');
						if (panel && btn) {
							panel.classList.toggle('show');
							btn.textContent = panel.classList.contains('show') ? '▲ Hide Advanced' : '▼ Advanced Options';
						}
					});

					// Advanced feature checkboxes - Toolbar sections
					const advToolbarFeatures = ['toolbar', 'toolbarVoice', 'toolbarAnalytics', 'toolbarSchema', 'toolbarWorkflow', 'toolbarView', 'toolbarLayout', 'toolbarZoom', 'toolbarStyle'];
					advToolbarFeatures.forEach(feat => {
						document.getElementById('sg-feature-adv-' + feat)?.addEventListener('change', (e) => {
							self.api.features.set({ [feat]: e.target.checked });
						});
					});

					// Advanced feature checkboxes - Interactions
					const advInteractionFeatures = ['nodeSelection', 'multiSelection', 'nodeDragging', 'linkCreation', 'linkDeletion', 'panning', 'zooming', 'contextMenu'];
					advInteractionFeatures.forEach(feat => {
						document.getElementById('sg-feature-adv-' + feat)?.addEventListener('change', (e) => {
							self.api.features.set({ [feat]: e.target.checked });
						});
					});

					// Advanced feature checkboxes - Tooltips & Visual
					const advVisualFeatures = ['nodeTooltips', 'fieldTooltips', 'completenessIndicators', 'analytics', 'textScaling', 'themeSwitch', 'autoPreview', 'edgePreview', 'loopEdgeOrthogonal', 'nativeTypes'];
					advVisualFeatures.forEach(feat => {
						document.getElementById('sg-feature-adv-' + feat)?.addEventListener('change', (e) => {
							self.api.features.set({ [feat]: e.target.checked });
						});
					});

					// Advanced action buttons
					document.getElementById('sg-features-enable-all')?.addEventListener('click', () => {
						const allFeatures = {};
						Object.keys(self._features).forEach(k => allFeatures[k] = true);
						self.api.features.set(allFeatures);
					});
					document.getElementById('sg-features-disable-all')?.addEventListener('click', () => {
						const allFeatures = {};
						Object.keys(self._features).forEach(k => allFeatures[k] = false);
						self.api.features.set(allFeatures);
					});
					document.getElementById('sg-features-reset')?.addEventListener('click', () => {
						self.api.features.reset();
					});

					// Resize
					window.addEventListener('resize', () => self.ui.util.resizeCanvas());
				}
			}
		};
	}

	// ========================================================================
	// DESTROY
	// ========================================================================

	destroy() {
		// Remove event listeners
		this.canvas.removeEventListener('mousedown', this._boundHandlers?.mouseDown);
		this.canvas.removeEventListener('mousemove', this._boundHandlers?.mouseMove);
		this.canvas.removeEventListener('mouseup', this._boundHandlers?.mouseUp);
		this.canvas.removeEventListener('wheel', this._boundHandlers?.wheel);
		this.canvas.removeEventListener('dblclick', this._boundHandlers?.dblClick);
		this.canvas.removeEventListener('contextmenu', this._boundHandlers?.contextMenu);
		document.removeEventListener('keydown', this._boundHandlers?.keyDown);
		document.removeEventListener('keyup', this._boundHandlers?.keyUp);

		// Clear graph
		this.graph.nodes = [];
		this.graph.links = [];

		// Clear canvas
		const ctx = this.canvas.getContext('2d');
		ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);

		// Emit destroy event
		this.eventBus.emit('app:destroyed', {});
	}
}

// ========================================================================
// EXPORTS
// ========================================================================

// Module exports
if (typeof module !== 'undefined' && module.exports) {
	module.exports = { SchemaGraphApp };
}

// Global exports for browser (standard JS)
if (typeof window !== 'undefined') {
	window.SchemaGraphApp = SchemaGraphApp;
}

console.log('[SchemaGraph] App module loaded.');
