// ============================================================================
// SCHEMAGRAPH ML EXTENSION — Frontend MediaPipe Inference
//
// Adds optional client-side MediaPipe Tasks Vision inference to BrowserSource
// nodes. When enabled (mode = 'stream' + frontend inference toggle), frames
// are processed locally in the browser using WebAssembly — no round-trip to
// the backend for pose detection — then the keypoints are both:
//   1. Drawn on the overlay canvas immediately (zero-latency display)
//   2. Sent to the backend via the stream WebSocket as JSON (for workflow use)
//
// Depends on: schemagraph-media-ext.js, schemagraph-extensions.js
// CDN: @mediapipe/tasks-vision loaded dynamically on first use
// ============================================================================

console.log('[SchemaGraph] Loading ML extension...');

// ── MediaPipe CDN ────────────────────────────────────────────────────────────

const MEDIAPIPE_CDN = 'https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.32/+esm';

let _mpVisionLoaded   = false;
let _mpVisionLoading  = null;   // Promise while loading
let _mpVisionModule   = null;   // Cached ES module object

async function loadMediaPipeVision() {
	if (_mpVisionLoaded && _mpVisionModule) return _mpVisionModule;
	if (_mpVisionLoading) return _mpVisionLoading;

	// Use dynamic import() — required when the CDN serves an ES module (/+esm).
	// Dynamic import() works from classic scripts in all modern browsers.
	_mpVisionLoading = import(MEDIAPIPE_CDN)
		.then(module => {
			_mpVisionLoaded  = true;
			_mpVisionModule  = module;
			_mpVisionLoading = null;
			console.log('[ML] MediaPipe Tasks Vision loaded from CDN.');
			return module;
		})
		.catch(err => {
			_mpVisionLoading = null;
			throw new Error('Failed to load MediaPipe Tasks Vision from CDN: ' + err);
		});

	return _mpVisionLoading;
}


// ── Per-node inference state ──────────────────────────────────────────────────

const MLState = Object.freeze({
	IDLE     : 'idle',
	LOADING  : 'loading',
	RUNNING  : 'running',
	ERROR    : 'error',
});


// ── FrontendInferenceManager ─────────────────────────────────────────────────

class FrontendInferenceManager {
	constructor() {
		this._detectors  = new Map();    // nodeId -> PoseLandmarker instance
		this._states     = new Map();    // nodeId -> MLState
		this._rafHandles = new Map();    // nodeId -> bool (rAF loop active)
		this._wsRefs     = new Map();    // nodeId -> WebSocket (ref from media ext)
		this._overlayMgr = null;         // MediaOverlayManager ref (set after init)
	}

	// ── Lifecycle ─────────────────────────────────────────────────────────────

	async enableForNode(node, wsRef) {
		const nodeId = node.id;
		if (this._states.get(nodeId) === MLState.RUNNING) return;

		this._states.set(nodeId, MLState.LOADING);
		this._wsRefs.set(nodeId, wsRef);
		this._log(nodeId, 'Loading MediaPipe…');

		try {
			const mp = await loadMediaPipeVision();
			const { PoseLandmarker, FilesetResolver } = mp;

			const filesetResolver = await FilesetResolver.forVisionTasks(
				'https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.32/wasm'
			);

			const detector = await PoseLandmarker.createFromOptions(filesetResolver, {
				baseOptions: {
					modelAssetPath: 'https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task',
					delegate: 'GPU',
				},
				runningMode        : 'VIDEO',
				numPoses           : 1,
				minPoseDetectionConfidence : 0.5,
				minPosePresenceConfidence  : 0.5,
				minTrackingConfidence      : 0.5,
			});

			this._detectors.set(nodeId, detector);
			this._states.set(nodeId, MLState.RUNNING);
			this._log(nodeId, 'Detector ready — starting inference loop.');
			this._startLoop(node);

		} catch (err) {
			this._states.set(nodeId, MLState.ERROR);
			console.error(`[ML] Failed to init detector for node ${nodeId}:`, err);
		}
	}

	disableForNode(nodeId) {
		this._rafHandles.delete(nodeId);
		const det = this._detectors.get(nodeId);
		if (det) { try { det.close(); } catch(e) {} }
		this._detectors.delete(nodeId);
		this._states.set(nodeId, MLState.IDLE);
		this._wsRefs.delete(nodeId);
	}

	// ── Inference loop ────────────────────────────────────────────────────────

	_startLoop(node) {
		const nodeId  = node.id;
		const FPS     = 20;
		const minGap  = 1000 / FPS;
		let   lastTs  = 0;
		let   lastInf = 0;

		this._rafHandles.set(nodeId, true);

		const loop = (ts) => {
			if (!this._rafHandles.has(nodeId)) return;   // stopped
			if (this._states.get(nodeId) !== MLState.RUNNING) return;

			requestAnimationFrame(loop);

			if (ts - lastInf < minGap) return;
			lastInf = ts;

			const overlay  = this._overlayMgr?.overlays.get(nodeId);
			const video    = overlay?.querySelector('.sg-media-video');
			if (!video || video.readyState < 2 || video.paused) return;

			const detector = this._detectors.get(nodeId);
			if (!detector) return;

			try {
				const result = detector.detectForVideo(video, ts);
				this._onResult(nodeId, result, video);
			} catch (e) {
				// GPU context lost or other transient error — ignore single frame
			}
		};

		requestAnimationFrame(loop);
	}

	_onResult(nodeId, result, video) {
		if (!result.landmarks || result.landmarks.length === 0) return;

		const landmarks = result.landmarks[0].map(lm => ({
			x          : lm.x,
			y          : lm.y,
			z          : lm.z,
			visibility : lm.visibility ?? 1,
		}));

		const w = video.videoWidth  || 320;
		const h = video.videoHeight || 240;

		// 1. Draw skeleton on the overlay canvas directly (zero latency)
		const overlay = this._overlayMgr?.overlays.get(nodeId);
		if (overlay) {
			const canvas = overlay.querySelector('.sg-media-overlay-canvas');
			if (canvas) {
				// Use the CSS display size for the pixel buffer so drawing primitives
				// (dot radius, line width) are correctly sized at any camera zoom level.
				// Using the video's native resolution (640x480) when displayed at e.g.
				// 191x97 CSS px makes 2px lines render as sub-pixel and invisible.
				const dpr  = window.devicePixelRatio || 1;
				const dw   = canvas.clientWidth  || w;
				const dh   = canvas.clientHeight || h;
				canvas.width  = dw * dpr;
				canvas.height = dh * dpr;
				const ctx = canvas.getContext('2d');
				if (dpr !== 1) ctx.scale(dpr, dpr);
				ctx.clearRect(0, 0, dw, dh);
				// Reuse the drawing helper from MediaOverlayManager if available
				if (this._overlayMgr?._drawPoseLandmarks) {
					this._overlayMgr._drawPoseLandmarks(ctx, landmarks, dw, dh, true);
				} else {
					_drawPoseFallback(ctx, landmarks, dw, dh);
				}
			}
		}

		// 2. Send keypoints to backend via stream WebSocket so the workflow can use them
		const ws = this._wsRefs.get(nodeId);
		if (ws && ws.readyState === WebSocket.OPEN) {
			ws.send(JSON.stringify({
				type       : 'keypoints',
				inference  : 'frontend_pose',
				landmarks,
				width      : w,
				height     : h,
				timestamp  : Date.now(),
			}));
		}
	}

	// ── Helpers ───────────────────────────────────────────────────────────────

	_log(nodeId, msg) {
		console.log(`[ML:node-${nodeId}] ${msg}`);
	}

	getState(nodeId) {
		return this._states.get(nodeId) ?? MLState.IDLE;
	}
}

// Simple fallback pose drawing (used if MediaOverlayManager._drawPoseLandmarks not available)
function _drawPoseFallback(ctx, landmarks, w, h) {
	ctx.fillStyle = 'rgba(255, 80, 80, 0.9)';
	for (const lm of landmarks) {
		if ((lm.visibility ?? 1) < 0.4) continue;
		ctx.beginPath();
		ctx.arc(lm.x * w, lm.y * h, 4, 0, Math.PI * 2);
		ctx.fill();
	}
}


// ── MLStreamExtension ─────────────────────────────────────────────────────────

class MLStreamExtension extends SchemaGraphExtension {
	constructor(app) {
		super(app);
		this.inferenceManager = new FrontendInferenceManager();
		// Toggled per-node via the UI button added below
		this._frontendInferenceEnabled = new Map();   // nodeId -> bool
	}

	_registerNodeTypes() {
		// No new node types — we augment existing BrowserSource overlays
	}

	_setupEventListeners() {
		this.on('node:created', (e) => {
			const node = e.node || this.graph.getNodeById(e.nodeId);
			if (node && this._isBrowserSource(node)) {
				this._addInferenceToggle(node);
			}
		});

		this.on('workflow:imported', () => this._reapplyAll());
		this.on('workflow:synced',   () => this._reapplyAll());

		const onRemoved = (e) => {
			const nodeId = e.nodeId ?? e.node?.id;
			if (nodeId) this._onNodeRemoved(nodeId);
		};
		this.on('node:removed', onRemoved);
		this.on('node:deleted', onRemoved);

		this.on('graph:cleared', () => {
			for (const nodeId of [...this._frontendInferenceEnabled.keys()]) {
				this._stopFrontendInference(nodeId);
			}
		});

		// Attach to MediaOverlayManager so the inference loop can access overlays.
		// Guard: inferenceManager is assigned after super() returns, so it may be
		// undefined here if _setupEventListeners is called from the base constructor.
		// The attachment is also done lazily in _startFrontendInference.
		if (this.inferenceManager) {
			const mediaExt = this.app?.extensions?.get?.('browser-media');
			if (mediaExt?.overlayManager) {
				this.inferenceManager._overlayMgr = mediaExt.overlayManager;
			}
		}
	}

	_extendAPI() {
		this.app.api = this.app.api || {};
		this.app.api.mlStream = {
			enableFrontendInference : (nodeOrId) => {
				const node = this._resolveNode(nodeOrId);
				if (node) this._startFrontendInference(node);
			},
			disableFrontendInference: (nodeOrId) => {
				const id = typeof nodeOrId === 'string' ? nodeOrId : nodeOrId?.id;
				if (id) this._stopFrontendInference(id);
			},
			getState: (nodeOrId) => {
				const id = typeof nodeOrId === 'string' ? nodeOrId : nodeOrId?.id;
				return this.inferenceManager.getState(id);
			},
		};
	}

	// ── Per-node inference toggle ─────────────────────────────────────────────

	_addInferenceToggle(node) {
		// Wait a tick for the media overlay to render, then inject the button
		setTimeout(() => {
			const mediaExt = this.app?.extensions?.get?.('browser-media');
			const overlay  = mediaExt?.overlayManager?.overlays.get(node.id);
			if (!overlay) return;

			if (overlay.querySelector('.sg-ml-toggle-btn')) return; // already added

			const controls = overlay.querySelector('.sg-media-controls');
			if (!controls) return;

			const btn = document.createElement('button');
			btn.className   = 'sg-media-btn sg-ml-toggle-btn';
			btn.textContent = '🧠 ML Off';
			btn.title       = 'Toggle frontend MediaPipe inference';
			btn.style.background = 'var(--sg-accent-orange, #e6872a)';

			btn.addEventListener('click', (e) => {
				e.stopPropagation();
				const enabled = this._frontendInferenceEnabled.get(node.id);
				if (enabled) {
					this._stopFrontendInference(node.id);
					btn.textContent = '🧠 ML Off';
					btn.style.background = 'var(--sg-accent-orange, #e6872a)';
				} else {
					const mediaState = mediaExt?.overlayManager?.states.get(node.id);
					if (mediaState !== 'active') {
						alert('Start the camera first, then enable ML inference.');
						return;
					}
					this._startFrontendInference(node);
					btn.textContent = '🧠 ML On';
					btn.style.background = 'var(--sg-accent-green, #5cb85c)';
				}
			});

			controls.appendChild(btn);
		}, 200);
	}

	_startFrontendInference(node) {
		const nodeId  = node.id;
		const mediaExt= this.app?.extensions?.get?.('browser-media');
		const ws      = mediaExt?.overlayManager?.streamWSockets?.get(nodeId) ?? null;

		// Lazy-attach overlayMgr in case it was skipped during construction
		if (!this.inferenceManager._overlayMgr && mediaExt?.overlayManager) {
			this.inferenceManager._overlayMgr = mediaExt.overlayManager;
		}

		this._frontendInferenceEnabled.set(nodeId, true);
		this.inferenceManager.enableForNode(node, ws).catch(err => {
			console.error('[ML] Error enabling inference:', err);
		});
	}

	_stopFrontendInference(nodeId) {
		this._frontendInferenceEnabled.set(nodeId, false);
		this.inferenceManager.disableForNode(nodeId);
	}

	_onNodeRemoved(nodeId) {
		this._stopFrontendInference(nodeId);
		this._frontendInferenceEnabled.delete(nodeId);
	}

	_isBrowserSource(node) {
		return node.workflowType === 'browser_source_flow';
	}

	_resolveNode(nodeOrId) {
		return typeof nodeOrId === 'string' ? this.graph.getNodeById(nodeOrId) : nodeOrId;
	}

	_reapplyAll() {
		for (const node of this.graph.nodes) {
			if (this._isBrowserSource(node)) this._addInferenceToggle(node);
		}
	}

	_injectStyles() {
		if (document.getElementById('sg-ml-styles')) return;
		const s = document.createElement('style');
		s.id = 'sg-ml-styles';
		s.textContent = `
			.sg-ml-toggle-btn {
				min-width: 72px;
			}
		`;
		document.head.appendChild(s);
	}
}


// ── Register ─────────────────────────────────────────────────────────────────

if (typeof extensionRegistry !== 'undefined') {
	extensionRegistry.register('ml-stream', MLStreamExtension);
	console.log('[SchemaGraph] ML stream extension registered.');
}

if (typeof module !== 'undefined' && module.exports) {
	module.exports = { FrontendInferenceManager, MLStreamExtension };
}

if (typeof window !== 'undefined') {
	window.FrontendInferenceManager = FrontendInferenceManager;
	window.MLStreamExtension = MLStreamExtension;
}
