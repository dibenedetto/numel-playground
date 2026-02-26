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

// ── Worker source (inlined as Blob) ──────────────────────────────────────────
// Using a Blob URL instead of a file path avoids the SecurityError that occurs
// when the page is opened via file:// protocol (origin = null).  All imports
// inside the worker use absolute CDN URLs, so module resolution works fine
// from a blob: base URL.

const _ML_WORKER_SOURCE = `
// Classic worker — MediaPipe loaded via dynamic import() to avoid Chrome's
// cross-origin redirect restriction on module worker static imports.
const MEDIAPIPE_CDN = 'https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.32/+esm';
let _mp = null;
async function _getMP() {
	if (!_mp) _mp = await import(MEDIAPIPE_CDN);
	return _mp;
}

const POSE_CONNECTIONS = [
	[11,12],[11,13],[13,15],[12,14],[14,16],
	[11,23],[12,24],[23,24],
	[23,25],[25,27],[24,26],[26,28],
	[27,29],[29,31],[28,30],[30,32],
	[0,1],[1,2],[2,3],[3,7],[0,4],[4,5],[5,6],[6,8],
	[9,10],
];

let detector  = null;
let offscreen = null;
let offCtx    = null;

self.onmessage = async ({ data }) => {
	const { type } = data;

	if (type === 'init') {
		try {
			const { PoseLandmarker, FilesetResolver } = await _getMP();
			const resolver = await FilesetResolver.forVisionTasks(
				'https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.32/wasm'
			);
			detector = await PoseLandmarker.createFromOptions(resolver, {
				baseOptions: {
					modelAssetPath: 'https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task',
					delegate: 'GPU',
				},
				runningMode: 'VIDEO',
				numPoses: 1,
				minPoseDetectionConfidence: 0.5,
				minPosePresenceConfidence:  0.5,
				minTrackingConfidence:      0.5,
			});
			console.log('[ML Worker] PoseLandmarker ready.');
			self.postMessage({ type: 'ready' });
		} catch (err) {
			console.error('[ML Worker] Init failed:', err);
			self.postMessage({ type: 'error', message: String(err) });
		}

	} else if (type === 'detect') {
		const { bitmap, ts, width, height } = data;
		if (!detector || !bitmap) return;

		let landmarks = null;
		try {
			const result = detector.detectForVideo(bitmap, ts);
			if (result.landmarks?.length > 0) {
				landmarks = result.landmarks[0].map(lm => ({
					x: lm.x, y: lm.y, z: lm.z, visibility: lm.visibility ?? 1,
				}));
			}
		} catch (_) {}

		if (!offscreen || offscreen.width !== width || offscreen.height !== height) {
			offscreen = new OffscreenCanvas(width, height);
			offCtx    = offscreen.getContext('2d');
		}
		offCtx.clearRect(0, 0, width, height);
		offCtx.drawImage(bitmap, 0, 0);
		bitmap.close();

		if (landmarks) _drawSkeleton(offCtx, landmarks, width, height);

		const frame = offscreen.transferToImageBitmap();
		self.postMessage({ type: 'result', landmarks, frame, width, height, ts }, [frame]);

	} else if (type === 'stop') {
		try { detector?.close(); } catch (_) {}
		detector = null; offscreen = null; offCtx = null;
		self.close();
	}
};

function _drawSkeleton(ctx, landmarks, w, h) {
	ctx.strokeStyle = 'rgba(0, 255, 100, 0.85)';
	ctx.lineWidth = 2;
	for (const [a, b] of POSE_CONNECTIONS) {
		const la = landmarks[a], lb = landmarks[b];
		if (!la || !lb) continue;
		ctx.beginPath();
		ctx.moveTo(la.x * w, la.y * h);
		ctx.lineTo(lb.x * w, lb.y * h);
		ctx.stroke();
	}
	ctx.fillStyle = 'rgba(255, 80, 80, 0.9)';
	for (const lm of landmarks) {
		ctx.beginPath();
		ctx.arc(lm.x * w, lm.y * h, 4, 0, Math.PI * 2);
		ctx.fill();
	}
}
`;


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
		this._workers      = new Map();   // nodeId -> Worker
		this._states       = new Map();   // nodeId -> MLState
		this._pending      = new Map();   // nodeId -> bool (backpressure: frame in-flight)
		this._captureRafs  = new Map();   // nodeId -> bool (capture RAF loop active)
		this._wsRefs       = new Map();   // nodeId -> WebSocket (ref from media ext)
		this._overlayMgr   = null;        // MediaOverlayManager ref (set after init)
		this._eventBus     = null;        // EventBus ref (set after init)
	}

	// ── Lifecycle ─────────────────────────────────────────────────────────────

	enableForNode(node, wsRef) {
		const nodeId = String(node.id);
		if (this._states.get(nodeId) === MLState.RUNNING ||
		    this._states.get(nodeId) === MLState.LOADING) return;

		this._states.set(nodeId, MLState.LOADING);
		this._wsRefs.set(nodeId, wsRef);
		this._log(nodeId, 'Starting ML Worker…');

		const blob      = new Blob([_ML_WORKER_SOURCE], { type: 'text/javascript' });
		const blobUrl   = URL.createObjectURL(blob);
		const worker    = new Worker(blobUrl);  // classic worker — uses dynamic import() internally
		worker._blobUrl = blobUrl;   // store for cleanup
		this._workers.set(nodeId, worker);

		worker.onmessage = ({ data }) => this._onWorkerMessage(nodeId, data);
		worker.onerror   = (err) => {
			console.error(`[ML:node-${nodeId}] Worker error:`, err);
			this._states.set(nodeId, MLState.ERROR);
		};

		worker.postMessage({ type: 'init' });
	}

	disableForNode(nodeId) {
		nodeId = String(nodeId);

		// Stop capture RAF loop
		this._captureRafs.delete(nodeId);
		this._pending.delete(nodeId);

		// Clear _mlRendering flag so video renderer takes back the display canvas
		const overlay = this._overlayMgr?.overlays.get(nodeId);
		if (overlay) overlay._mlRendering = false;

		// Tell worker to shut down (gives it a chance to close the detector cleanly)
		const worker = this._workers.get(nodeId);
		if (worker) {
			try { worker.postMessage({ type: 'stop' }); } catch (_) {}
			// Force-terminate after grace period in case worker hangs
			setTimeout(() => {
				try { worker.terminate(); } catch (_) {}
				if (worker._blobUrl) URL.revokeObjectURL(worker._blobUrl);
			}, 500);
			this._workers.delete(nodeId);
		}

		this._states.set(nodeId, MLState.IDLE);
		this._wsRefs.delete(nodeId);
		this._log(nodeId, 'Stopped.');
	}

	// ── Worker message handler ────────────────────────────────────────────────

	_onWorkerMessage(nodeId, data) {
		const { type } = data;

		if (type === 'ready') {
			this._states.set(nodeId, MLState.RUNNING);
			this._log(nodeId, 'Worker ready — starting capture loop.');

			// Signal media-ext to yield the display canvas to us
			const overlay = this._overlayMgr?.overlays.get(nodeId);
			if (overlay) overlay._mlRendering = true;

			this._startCaptureLoop(nodeId);

		} else if (type === 'error') {
			this._states.set(nodeId, MLState.ERROR);
			console.error(`[ML:node-${nodeId}] Worker error: ${data.message}`);

		} else if (type === 'result') {
			// Release backpressure — ready for next frame
			this._pending.set(nodeId, false);

			const { landmarks, frame, width, height, ts } = data;

			// Draw composed frame (video + skeleton) on the display canvas
			if (frame) {
				this._drawComposedFrame(nodeId, frame);  // closes frame internally
			}

			// Send keypoints to backend + emit on EventBus
			if (landmarks) {
				this._sendToWS(nodeId, landmarks, width, height);
				const sourceId = this._overlayMgr?.nodeRefs.get(nodeId)?.extra?._browserSourceId;
				this._eventBus?.emit('ml:pose:result', { nodeId, sourceId, landmarks, width, height, ts });
			}
		}
	}

	// ── Capture loop (main thread) ────────────────────────────────────────────
	// Grabs video frames via createImageBitmap (async, zero-copy) and sends
	// them to the Worker. Backpressure: only one frame in-flight at a time.

	_startCaptureLoop(nodeId) {
		const FPS    = 20;
		const minGap = 1000 / FPS;
		let lastInf  = 0;

		this._captureRafs.set(nodeId, true);
		this._pending.set(nodeId, false);

		const loop = (ts) => {
			if (!this._captureRafs.has(nodeId)) return;  // stopped
			requestAnimationFrame(loop);

			if (ts - lastInf < minGap) return;           // FPS throttle
			if (this._pending.get(nodeId)) return;        // backpressure

			const overlay = this._overlayMgr?.overlays.get(nodeId);
			if (!overlay) return;
			const video = overlay.querySelector('.sg-media-video');
			if (!video || video.readyState < 2 || video.paused) return;

			const worker = this._workers.get(nodeId);
			if (!worker) return;

			lastInf = ts;
			this._pending.set(nodeId, true);

			// Async grab — releases ownership to worker via transferable
			createImageBitmap(video).then(bitmap => {
				if (!this._captureRafs.has(nodeId)) {
					bitmap.close();  // loop was stopped while awaiting
					return;
				}
				worker.postMessage(
					{ type: 'detect', bitmap, ts, width: video.videoWidth, height: video.videoHeight },
					[bitmap]
				);
			}).catch(() => {
				this._pending.set(nodeId, false);  // release on error
			});
		};

		requestAnimationFrame(loop);
	}

	// ── Draw composed frame on display canvas ─────────────────────────────────

	_drawComposedFrame(nodeId, frame) {
		const overlay = this._overlayMgr?.overlays.get(nodeId);
		if (!overlay) { frame.close(); return; }

		const displayCanvas = overlay.querySelector('.sg-media-display-canvas');
		if (!displayCanvas) { frame.close(); return; }

		const ctx = displayCanvas.getContext('2d');
		const dpr = window.devicePixelRatio || 1;
		const cw  = displayCanvas.clientWidth  || 320;
		const ch  = displayCanvas.clientHeight || 240;
		const pw  = Math.round(cw * dpr);
		const ph  = Math.round(ch * dpr);

		if (displayCanvas.width !== pw || displayCanvas.height !== ph) {
			displayCanvas.width  = pw;
			displayCanvas.height = ph;
		}

		// Letterbox the composed frame to fit the display canvas
		const fw    = frame.width  || pw;
		const fh    = frame.height || ph;
		const scale = Math.min(pw / fw, ph / fh);
		const dw    = fw * scale;
		const dh    = fh * scale;
		const dx    = (pw - dw) / 2;
		const dy    = (ph - dh) / 2;

		ctx.fillStyle = '#000';
		ctx.fillRect(0, 0, pw, ph);
		ctx.drawImage(frame, dx, dy, dw, dh);
		frame.close();

		// Clear overlay canvas — skeleton is now baked into the composed frame
		const overlayCanvas = overlay.querySelector('.sg-media-overlay-canvas');
		if (overlayCanvas) {
			const octx = overlayCanvas.getContext('2d');
			octx.clearRect(0, 0, overlayCanvas.width, overlayCanvas.height);
		}
	}

	// ── Send keypoints to backend ─────────────────────────────────────────────

	_sendToWS(nodeId, landmarks, width, height) {
		const ws = this._wsRefs.get(nodeId);
		if (ws && ws.readyState === WebSocket.OPEN) {
			ws.send(JSON.stringify({
				type      : 'keypoints',
				inference : 'frontend_pose',
				landmarks,
				width,
				height,
				timestamp : Date.now(),
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
		if (!this.inferenceManager._eventBus && this.eventBus) {
			this.inferenceManager._eventBus = this.eventBus;
		}

		this._frontendInferenceEnabled.set(nodeId, true);
		this.inferenceManager.enableForNode(node, ws);
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
