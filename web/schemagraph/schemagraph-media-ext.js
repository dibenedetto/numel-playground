// ========================================================================
// SCHEMAGRAPH BROWSER MEDIA EXTENSION
// Adds live browser media capture (webcam, microphone, screen) for
// BrowserSourceFlow nodes. Shows HTML overlay with preview + controls.
// Depends on: schemagraph-extensions.js
// ========================================================================

console.log('[SchemaGraph] Loading browser media extension...');

const MediaState = Object.freeze({
	IDLE: 'idle',
	REQUESTING: 'requesting',
	ACTIVE: 'active',
	ERROR: 'error'
});

// ========================================================================
// Media Overlay Manager
// ========================================================================

class MediaOverlayManager {
	constructor(app, eventBus) {
		this.app = app;
		this.eventBus = eventBus;
		this.overlays = new Map();      // nodeId -> overlay DOM element
		this.nodeRefs = new Map();      // nodeId -> node reference
		this.streams = new Map();       // nodeId -> MediaStream
		this.captureTimers = new Map(); // nodeId -> interval ID
		this.audioCtx = new Map();      // nodeId -> { ctx, analyser, dataArray }
		this.states = new Map();        // nodeId -> MediaState

		this.Z_BASE = 1000;
		this.Z_SELECTED = 10000;
	}

	createOverlay(node) {
		const nodeId = node.id;

		if (this.overlays.has(nodeId)) {
			this.nodeRefs.set(nodeId, node);
			this._updateOverlayPosition(node, this.overlays.get(nodeId));
			return this.overlays.get(nodeId);
		}

		const overlay = document.createElement('div');
		overlay.className = 'sg-media-overlay';
		overlay.id = `sg-media-${nodeId}`;
		overlay.innerHTML = this._buildHTML(node);

		const container = this.app.canvas?.parentElement || document.body;
		container.appendChild(overlay);

		this.overlays.set(nodeId, overlay);
		this.nodeRefs.set(nodeId, node);
		this.states.set(nodeId, MediaState.IDLE);

		this._bindEvents(node, overlay);
		this._updateOverlayPosition(node, overlay);

		return overlay;
	}

	_buildHTML(node) {
		const deviceType = this._getFieldValue(node, 'device_type') || 'webcam';
		const isAudio = deviceType === 'microphone';

		return `
			<div class="sg-media-container sg-media-state-idle">
				<div class="sg-media-status">
					<span class="sg-media-status-indicator"></span>
					<span class="sg-media-status-text">Ready</span>
				</div>
				<div class="sg-media-preview">
					${isAudio
						? '<canvas class="sg-media-audio-canvas"></canvas>'
						: '<video class="sg-media-video" autoplay muted playsinline></video>'
					}
				</div>
				<div class="sg-media-controls">
					<button class="sg-media-btn sg-media-start-btn" title="Start capture">Start</button>
					<button class="sg-media-btn sg-media-stop-btn" title="Stop capture" style="display:none">Stop</button>
				</div>
			</div>`;
	}

	_bindEvents(node, overlay) {
		const nodeId = node.id;
		const getNode = () => this.nodeRefs.get(nodeId);

		const startBtn = overlay.querySelector('.sg-media-start-btn');
		const stopBtn = overlay.querySelector('.sg-media-stop-btn');

		startBtn?.addEventListener('click', (e) => {
			e.stopPropagation();
			const n = getNode();
			if (n) this._startCapture(n);
		});

		stopBtn?.addEventListener('click', (e) => {
			e.stopPropagation();
			const n = getNode();
			if (n) this._stopCapture(n);
		});

		// Prevent canvas events when interacting with overlay
		overlay.addEventListener('mousedown', (e) => {
			const rect = overlay.getBoundingClientRect();
			const x = e.clientX - rect.left;
			const y = e.clientY - rect.top;
			const edge = 8;
			if (x > edge && x < rect.width - edge && y > edge && y < rect.height - edge) {
				e.stopPropagation();
			}
		});
		overlay.addEventListener('wheel', (e) => e.stopPropagation(), { passive: true });
	}

	async _startCapture(node) {
		const nodeId = node.id;
		const deviceType = this._getFieldValue(node, 'device_type') || 'webcam';
		const resolution = this._getFieldValue(node, 'resolution');

		this._setState(nodeId, MediaState.REQUESTING);

		try {
			let stream;
			const constraints = {};

			if (deviceType === 'webcam') {
				constraints.video = this._buildVideoConstraints(resolution);
				constraints.audio = false;
				stream = await navigator.mediaDevices.getUserMedia(constraints);
			} else if (deviceType === 'microphone') {
				constraints.audio = true;
				constraints.video = false;
				stream = await navigator.mediaDevices.getUserMedia(constraints);
			} else if (deviceType === 'screen') {
				stream = await navigator.mediaDevices.getDisplayMedia({ video: true });
			}

			this.streams.set(nodeId, stream);
			this._setState(nodeId, MediaState.ACTIVE);

			// Attach stream to preview element
			const overlay = this.overlays.get(nodeId);
			if (deviceType === 'microphone') {
				this._setupAudioVisualizer(nodeId, stream, overlay);
			} else {
				const video = overlay?.querySelector('.sg-media-video');
				if (video) {
					video.srcObject = stream;
				}
			}

			// Listen for track ended (user stops screen share via browser UI)
			stream.getTracks().forEach(track => {
				track.addEventListener('ended', () => {
					this._stopCapture(node);
				});
			});

			// Auto-register backend source if not yet registered, then start capture loop
			if (!node.extra?._browserSourceId && this._registerSourceCallback) {
				const sourceId = await this._registerSourceCallback(node);
				if (sourceId) {
					node.extra = node.extra || {};
					node.extra._browserSourceId = sourceId;
				}
			}
			this._startCaptureLoop(node);

			console.log(`[BrowserMedia] Capture started for node ${nodeId} (${deviceType})`);
		} catch (err) {
			console.error(`[BrowserMedia] Capture failed for node ${nodeId}:`, err);
			this._setState(nodeId, MediaState.ERROR, err.message);
		}
	}

	_buildVideoConstraints(resolution) {
		if (!resolution) return true;
		const match = resolution.match(/(\d+)x(\d+)/);
		if (match) {
			return { width: { ideal: parseInt(match[1]) }, height: { ideal: parseInt(match[2]) } };
		}
		return true;
	}

	_setupAudioVisualizer(nodeId, stream, overlay) {
		const canvas = overlay?.querySelector('.sg-media-audio-canvas');
		if (!canvas) return;

		const ctx = canvas.getContext('2d');
		const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
		const source = audioCtx.createMediaStreamSource(stream);
		const analyser = audioCtx.createAnalyser();
		analyser.fftSize = 64;
		source.connect(analyser);

		const bufferLength = analyser.frequencyBinCount;
		const dataArray = new Uint8Array(bufferLength);

		this.audioCtx.set(nodeId, { ctx: audioCtx, analyser, dataArray, source });

		const draw = () => {
			if (!this.audioCtx.has(nodeId)) return;
			requestAnimationFrame(draw);

			analyser.getByteFrequencyData(dataArray);

			const w = canvas.width = canvas.clientWidth;
			const h = canvas.height = canvas.clientHeight;

			ctx.fillStyle = getComputedStyle(document.documentElement).getPropertyValue('--sg-bg-primary').trim() || '#1e1e1e';
			ctx.fillRect(0, 0, w, h);

			const barWidth = Math.max(2, (w / bufferLength) - 1);
			const accentColor = getComputedStyle(document.documentElement).getPropertyValue('--sg-accent-blue').trim() || '#5bc0de';

			for (let i = 0; i < bufferLength; i++) {
				const barHeight = (dataArray[i] / 255) * h;
				const x = i * (barWidth + 1);
				ctx.fillStyle = accentColor;
				ctx.fillRect(x, h - barHeight, barWidth, barHeight);
			}
		};
		draw();
	}

	_startCaptureLoop(node) {
		const nodeId = node.id;
		const intervalMs = parseInt(this._getFieldValue(node, 'interval_ms')) || 1000;
		const deviceType = this._getFieldValue(node, 'device_type') || 'webcam';
		const mode = this._getFieldValue(node, 'mode') || 'event';

		// Clear existing timer
		if (this.captureTimers.has(nodeId)) {
			clearInterval(this.captureTimers.get(nodeId));
		}

		const sourceId = node.extra?._browserSourceId;

		const timer = setInterval(async () => {
			if (this.states.get(nodeId) !== MediaState.ACTIVE) {
				clearInterval(timer);
				return;
			}

			try {
				let data;
				if (deviceType === 'microphone') {
					// For audio, we'll send a status ping (actual audio streaming uses MediaRecorder)
					data = { type: 'audio_tick', timestamp: Date.now() };
				} else {
					// Capture video frame as base64 JPEG
					data = this._captureFrame(nodeId);
					if (!data) return;
				}

				// Push frame to node output so connected PreviewFlow nodes display it
				this._pushToNodeOutput(node, data);

				// Send to backend if source is registered
				if (sourceId) {
					const baseUrl = this._baseUrl || '';
					fetch(`${baseUrl}/event-sources/browser/${sourceId}/event`, {
						method: 'POST',
						headers: { 'Content-Type': 'application/json' },
						body: JSON.stringify({ ...data, client_id: `browser_${nodeId}` })
					}).catch(() => {}); // fire-and-forget
				}
			} catch (err) {
				console.warn(`[BrowserMedia] Failed to capture for node ${nodeId}:`, err.message);
			}
		}, intervalMs);

		this.captureTimers.set(nodeId, timer);
	}

	_captureFrame(nodeId) {
		const overlay = this.overlays.get(nodeId);
		const video = overlay?.querySelector('.sg-media-video');
		if (!video || video.readyState < 2) return null;

		const canvas = document.createElement('canvas');
		canvas.width = video.videoWidth || 320;
		canvas.height = video.videoHeight || 240;
		const ctx = canvas.getContext('2d');
		ctx.drawImage(video, 0, 0);

		const dataUrl = canvas.toDataURL('image/jpeg', 0.7);
		return {
			type: 'frame',
			format: 'jpeg',
			width: canvas.width,
			height: canvas.height,
			data: dataUrl,
			timestamp: Date.now()
		};
	}

	_pushToNodeOutput(node, data) {
		const frameData = data.type === 'frame' ? data.data : data;
		const graph = this.app?.graph;
		if (!graph || !node.outputs) return;

		// Set output slot value
		for (let i = 0; i < node.outputs.length; i++) {
			const meta = node.outputMeta?.[i];
			const slotName = meta?.name || node.outputs[i]?.name;
			if (slotName === 'output' || slotName === 'Output') {
				node.outputs[i].value = frameData;
				break;
			}
		}

		// Push live frames to all downstream preview nodes (traverses through intermediate nodes)
		this._pushToDownstreamPreviews(node, frameData, new Set());
	}

	_pushToDownstreamPreviews(node, frameData, visited, depth = 0) {
		const graph = this.app?.graph;
		if (!graph || visited.has(node.id) || depth > 10) return;
		visited.add(node.id);

		for (const output of (node.outputs || [])) {
			for (const linkId of (output.links || [])) {
				const link = graph.links[linkId];
				if (!link) continue;
				const target = graph.getNodeById(link.target_id);
				if (!target) continue;

				if (this.app._isPreviewFlowNode?.(target)) {
					this._updateLivePreview(target, frameData);
				} else {
					// Traverse through intermediate nodes (e.g. EventListenerFlow)
					this._pushToDownstreamPreviews(target, frameData, visited, depth + 1);
				}
			}
		}
	}

	_updateLivePreview(previewNode, frameData) {
		// Double-buffer: skip if previous frame is still loading
		if (previewNode._framePending) return;

		if (typeof frameData === 'string' && frameData.startsWith('data:image/')) {
			previewNode._framePending = true;
			const img = new Image();
			img.onload = () => {
				previewNode._liveFrameImg = img;
				previewNode.previewData = frameData;
				previewNode.previewType = 'image';
				previewNode._framePending = false;
				this.app?.draw?.();
			};
			img.onerror = () => { previewNode._framePending = false; };
			img.src = frameData;
		} else {
			previewNode.previewData = frameData;
			previewNode.previewType = null;
			this.app?.draw?.();
		}
	}

	_stopCapture(node) {
		const nodeId = node.id;

		// Stop media stream tracks
		const stream = this.streams.get(nodeId);
		if (stream) {
			stream.getTracks().forEach(t => t.stop());
			this.streams.delete(nodeId);
		}

		// Clear capture timer
		const timer = this.captureTimers.get(nodeId);
		if (timer) {
			clearInterval(timer);
			this.captureTimers.delete(nodeId);
		}

		// Cleanup audio context
		const audio = this.audioCtx.get(nodeId);
		if (audio) {
			audio.source.disconnect();
			audio.ctx.close();
			this.audioCtx.delete(nodeId);
		}

		// Clear video element
		const overlay = this.overlays.get(nodeId);
		const video = overlay?.querySelector('.sg-media-video');
		if (video) video.srcObject = null;

		this._setState(nodeId, MediaState.IDLE);
		console.log(`[BrowserMedia] Capture stopped for node ${nodeId}`);
	}

	_setState(nodeId, state, errorMsg = null) {
		this.states.set(nodeId, state);
		const overlay = this.overlays.get(nodeId);
		if (!overlay) return;

		const container = overlay.querySelector('.sg-media-container');
		const statusText = overlay.querySelector('.sg-media-status-text');
		const startBtn = overlay.querySelector('.sg-media-start-btn');
		const stopBtn = overlay.querySelector('.sg-media-stop-btn');

		if (container) {
			container.className = `sg-media-container sg-media-state-${state}`;
		}

		const labels = {
			[MediaState.IDLE]: 'Ready',
			[MediaState.REQUESTING]: 'Requesting access...',
			[MediaState.ACTIVE]: 'Capturing',
			[MediaState.ERROR]: errorMsg || 'Error'
		};
		if (statusText) statusText.textContent = labels[state] || state;

		if (startBtn) startBtn.style.display = state === MediaState.ACTIVE ? 'none' : '';
		if (stopBtn) stopBtn.style.display = state === MediaState.ACTIVE ? '' : 'none';
	}

	_getFieldValue(node, fieldName) {
		// Check inputMeta for actual field name (inputs use display names which may be prettified)
		if (node.inputMeta && node.inputs) {
			for (let i = 0; i < node.inputs.length; i++) {
				const meta = node.inputMeta[i];
				if (meta?.name === fieldName) return node.inputs[i].value;
			}
		}
		// Fallback: direct name match on inputs
		if (node.inputs) {
			for (const inp of node.inputs) {
				if (inp.name === fieldName) return inp.value;
			}
		}
		// Fallback to properties
		return node.properties?.[fieldName];
	}

	// === Overlay positioning (same math as ChatOverlayManager) ===

	updateOverlayPosition(node) {
		const overlay = this.overlays.get(node.id);
		if (overlay) this._updateOverlayPosition(node, overlay);
	}

	updateAllPositions() {
		for (const [nodeId, overlay] of this.overlays) {
			const node = this.nodeRefs.get(nodeId);
			if (node) this._updateOverlayPosition(node, overlay);
		}
	}

	_updateOverlayPosition(node, overlay) {
		const camera = this.app.camera;

		const nodeScreenX = node.pos[0] * camera.scale + camera.x;
		const nodeScreenY = node.pos[1] * camera.scale + camera.y;
		const nodeScreenW = node.size[0] * camera.scale;
		const nodeScreenH = node.size[1] * camera.scale;

		const numInputs = node.inputs?.length || 0;
		const numOutputs = node.outputs?.length || 0;
		const maxSlots = Math.max(numInputs, numOutputs);

		const headerHeight = 30;
		const slotStartY = 33;
		const slotSpacing = 25;
		const footerHeight = 15;
		const horizontalPadding = 12;

		const slotsEndY = slotStartY + (maxSlots * slotSpacing);
		const contentStartY = Math.max(headerHeight, slotsEndY + 5);

		const scale = camera.scale;
		const overlayX = nodeScreenX + (horizontalPadding * scale);
		const overlayY = nodeScreenY + (contentStartY * scale);
		const overlayW = nodeScreenW - (horizontalPadding * 2 * scale);
		const overlayH = nodeScreenH - (contentStartY * scale) - (footerHeight * scale);

		overlay.style.left = `${overlayX}px`;
		overlay.style.top = `${overlayY}px`;
		overlay.style.width = `${Math.max(overlayW, 80)}px`;
		overlay.style.height = `${Math.max(overlayH, 60)}px`;
		overlay.style.zIndex = this.Z_BASE;
	}

	removeOverlay(nodeId) {
		this._stopCapture({ id: nodeId });
		const overlay = this.overlays.get(nodeId);
		if (overlay) {
			overlay.remove();
			this.overlays.delete(nodeId);
		}
		this.nodeRefs.delete(nodeId);
	}

	removeAllOverlays() {
		for (const nodeId of [...this.overlays.keys()]) {
			this.removeOverlay(nodeId);
		}
	}

	stopAllCaptures() {
		for (const nodeId of [...this.streams.keys()]) {
			const node = this.nodeRefs.get(nodeId);
			if (node) this._stopCapture(node);
		}
	}

	setBaseUrl(url) {
		this._baseUrl = url;
	}
}

// ========================================================================
// Browser Media Extension
// ========================================================================

class BrowserMediaExtension extends SchemaGraphExtension {
	constructor(app) {
		super(app);
		this.overlayManager = new MediaOverlayManager(app, this.eventBus);
		// Wire the registration callback so overlay manager can auto-register backend sources
		this.overlayManager._registerSourceCallback = (node) => this._registerBackendSource(node);
	}

	_registerNodeTypes() {
		// No new node types — we enhance existing BrowserSourceFlow nodes
	}

	_setupEventListeners() {

		this.on('node:created', (e) => {
			const node = e.node || this.graph.getNodeById(e.nodeId);
			if (node) this._applyMediaToNode(node);
		});

		// App emits 'node:deleted', graph emits 'node:removed' — listen on both
		const onNodeRemoved = (e) => {
			const nodeId = e.nodeId || e.node?.id;
			if (nodeId) this.overlayManager.removeOverlay(nodeId);
		};
		this.on('node:removed', onNodeRemoved);
		this.on('node:deleted', onNodeRemoved);

		this.on('graph:cleared', () => {
			this.overlayManager.removeAllOverlays();
		});

		this.on('workflow:imported', () => {
			this._reapplyAll();
		});

		this.on('workflow:synced', () => {
			this._reapplyAll();
		});

		this.on('camera:moved', () => this.overlayManager.updateAllPositions());
		this.on('camera:zoomed', () => this.overlayManager.updateAllPositions());

		this.on('node:moved', (e) => {
			const node = this.graph.getNodeById(e.nodeId);
			if (node && this._isBrowserSource(node)) {
				this.overlayManager.updateOverlayPosition(node);
			}
		});

		this.on('node:resized', (e) => {
			const node = this.graph.getNodeById(e.nodeId);
			if (node && this._isBrowserSource(node)) {
				this.overlayManager.updateOverlayPosition(node);
			}
		});

		this.on('node:selected', () => this.overlayManager.updateAllPositions());
		this.on('node:deselected', () => this.overlayManager.updateAllPositions());

		// Hook into draw to keep overlays in sync
		const originalDraw = this.app.draw?.bind(this.app);
		if (originalDraw) {
			const self = this;
			this.app.draw = function () {
				originalDraw();
				self.overlayManager.updateAllPositions();
			};
		}

		// Cleanup when app graph is cleared via API
		if (this.app.api?.graph?.clear) {
			const originalClear = this.app.api.graph.clear.bind(this.app.api.graph);
			const self = this;
			this.app.api.graph.clear = function (...args) {
				self.overlayManager.removeAllOverlays();
				return originalClear(...args);
			};
		}
	}

	_extendAPI() {
		const self = this;

		this.app.api = this.app.api || {};
		this.app.api.browserMedia = {
			setBaseUrl: (url) => {
				self.overlayManager.setBaseUrl(url);
			},
			startCapture: (nodeOrId) => {
				const node = typeof nodeOrId === 'string' ? self.graph.getNodeById(nodeOrId) : nodeOrId;
				if (node && self._isBrowserSource(node)) {
					self.overlayManager._startCapture(node);
				}
			},
			stopCapture: (nodeOrId) => {
				const node = typeof nodeOrId === 'string' ? self.graph.getNodeById(nodeOrId) : nodeOrId;
				if (node && self._isBrowserSource(node)) {
					self.overlayManager._stopCapture(node);
				}
			},
			stopAll: () => {
				self.overlayManager.stopAllCaptures();
			},
			getState: (nodeOrId) => {
				const node = typeof nodeOrId === 'string' ? self.graph.getNodeById(nodeOrId) : nodeOrId;
				return self.overlayManager.states.get(node?.id) || MediaState.IDLE;
			},
			registerSource: async (nodeOrId) => {
				const node = typeof nodeOrId === 'string' ? self.graph.getNodeById(nodeOrId) : nodeOrId;
				if (node && self._isBrowserSource(node)) {
					return self._registerBackendSource(node);
				}
				return null;
			}
		};
	}

	_isBrowserSource(node) {
		return node.workflowType === 'browser_source_flow';
	}

	_applyMediaToNode(node) {
		if (!node) return;
		if (!this._isBrowserSource(node)) return;


		// Ensure node is large enough for the overlay
		// BrowserSourceFlow has 7 inputs → slots take ~210px, so node needs to be tall
		if (node.size[0] < 350) node.size[0] = 350;
		if (node.size[1] < 520) node.size[1] = 520;

		this.overlayManager.createOverlay(node);
	}

	_reapplyAll() {
		// Cleanup orphaned overlays
		const nodeIds = new Set(this.graph.nodes.filter(n => this._isBrowserSource(n)).map(n => n.id));
		for (const id of [...this.overlayManager.overlays.keys()]) {
			if (!nodeIds.has(id)) {
				this.overlayManager.removeOverlay(id);
			}
		}

		// Apply to all matching nodes
		for (const node of this.graph.nodes) {
			if (this._isBrowserSource(node) && !this.overlayManager.overlays.has(node.id)) {
				this._applyMediaToNode(node);
			}
		}
	}

	async _registerBackendSource(node) {
		const baseUrl = this.overlayManager._baseUrl || '';
		const deviceType = this.overlayManager._getFieldValue(node, 'device_type') || 'webcam';
		const mode = this.overlayManager._getFieldValue(node, 'mode') || 'event';
		const intervalMs = parseInt(this.overlayManager._getFieldValue(node, 'interval_ms')) || 1000;
		const resolution = this.overlayManager._getFieldValue(node, 'resolution') || null;
		const audioFormat = this.overlayManager._getFieldValue(node, 'audio_format') || null;
		const sourceId = this.overlayManager._getFieldValue(node, 'source_id') || `browser_${node.id}`;

		try {
			const resp = await fetch(`${baseUrl}/event-sources/browser`, {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({
					id: sourceId,
					device_type: deviceType,
					mode: mode,
					interval_ms: intervalMs,
					resolution: resolution,
					audio_format: audioFormat
				})
			});

			if (!resp.ok) {
				const text = await resp.text();
				console.warn(`[BrowserMedia] Failed to register source: ${text}`);
				return null;
			}

			const data = await resp.json();
			// Store source_id on node for capture loop
			node.extra = node.extra || {};
			node.extra._browserSourceId = data.source?.id || sourceId;

			// Start the source
			const startResp = await fetch(`${baseUrl}/event-sources/${node.extra._browserSourceId}/start`, { method: 'POST' });
			if (!startResp.ok) {
				console.warn(`[BrowserMedia] Failed to start source: ${await startResp.text()}`);
			}

			console.log(`[BrowserMedia] Backend source registered and started: ${node.extra._browserSourceId}`);
			return node.extra._browserSourceId;
		} catch (err) {
			console.error(`[BrowserMedia] Source registration failed:`, err);
			return null;
		}
	}

	// ================================================================
	// CSS Injection
	// ================================================================

	_injectStyles() {
		if (document.getElementById('sg-media-styles')) return;

		const style = document.createElement('style');
		style.id = 'sg-media-styles';
		style.textContent = `
			.sg-media-overlay {
				position: absolute;
				pointer-events: auto;
				font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
				font-size: 12px;
				border-radius: 4px;
				overflow: hidden;
				transition: opacity 0.15s ease;
			}

			.sg-media-container {
				display: flex;
				flex-direction: column;
				height: 100%;
				background: var(--sg-bg-secondary, #2a2a2a);
				border: 1px solid var(--sg-border-color, #1a1a1a);
				border-radius: 4px;
				overflow: hidden;
			}

			.sg-media-status {
				display: flex;
				align-items: center;
				gap: 6px;
				padding: 4px 8px;
				background: var(--sg-bg-tertiary, #353535);
				font-size: 10px;
				color: var(--sg-text-tertiary, #707070);
				border-bottom: 1px solid var(--sg-border-color, #1a1a1a);
			}

			.sg-media-status-indicator {
				width: 6px;
				height: 6px;
				border-radius: 50%;
				background: var(--sg-text-tertiary, #666);
				flex-shrink: 0;
			}

			.sg-media-status-text {
				flex: 1;
				overflow: hidden;
				text-overflow: ellipsis;
				white-space: nowrap;
			}

			.sg-media-state-idle .sg-media-status-indicator { background: var(--sg-text-tertiary, #666); }
			.sg-media-state-requesting .sg-media-status-indicator { background: var(--sg-accent-orange, #f0ad4e); animation: sg-media-pulse 1s infinite; }
			.sg-media-state-active .sg-media-status-indicator { background: var(--sg-accent-green, #5cb85c); }
			.sg-media-state-error .sg-media-status-indicator { background: var(--sg-accent-red, #d9534f); }

			@keyframes sg-media-pulse {
				0%, 100% { opacity: 1; }
				50% { opacity: 0.4; }
			}

			.sg-media-preview {
				flex: 1;
				min-height: 0;
				background: var(--sg-bg-primary, #1e1e1e);
				display: flex;
				align-items: center;
				justify-content: center;
				overflow: hidden;
			}

			.sg-media-video {
				width: 100%;
				height: 100%;
				object-fit: contain;
				background: #000;
			}

			.sg-media-audio-canvas {
				width: 100%;
				height: 100%;
			}

			.sg-media-controls {
				display: flex;
				gap: 6px;
				padding: 6px 8px;
				background: var(--sg-bg-tertiary, rgba(0, 0, 0, 0.2));
				border-top: 1px solid var(--sg-border-color, rgba(255, 255, 255, 0.05));
				justify-content: center;
			}

			.sg-media-btn {
				background: var(--sg-accent-blue, #2d5a7b);
				border: none;
				color: var(--sg-text-primary, #fff);
				padding: 4px 12px;
				border-radius: 4px;
				cursor: pointer;
				font-size: 11px;
				font-family: inherit;
			}

			.sg-media-btn:hover {
				filter: brightness(1.2);
			}

			.sg-media-stop-btn {
				background: var(--sg-accent-red, #d9534f);
			}

			.sg-media-state-requesting .sg-media-start-btn {
				opacity: 0.5;
				pointer-events: none;
			}
		`;
		document.head.appendChild(style);
	}
}

// ========================================================================
// Register Extension
// ========================================================================

if (typeof extensionRegistry !== 'undefined') {
	extensionRegistry.register('browser-media', BrowserMediaExtension);
	console.log('[SchemaGraph] Browser media extension registered.');
}

// ========================================================================
// Exports
// ========================================================================

if (typeof module !== 'undefined' && module.exports) {
	module.exports = { MediaOverlayManager, BrowserMediaExtension, MediaState };
}

if (typeof window !== 'undefined') {
	window.MediaOverlayManager = MediaOverlayManager;
	window.BrowserMediaExtension = BrowserMediaExtension;
	window.MediaState = MediaState;
}
