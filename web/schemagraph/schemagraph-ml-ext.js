// ============================================================================
// SCHEMAGRAPH ML EXTENSION — Frontend MediaPipe Inference
//
// When a graph contains a ComputerVisionFlow node (inference_location=frontend)
// connected downstream from a BrowserSourceFlow node, this extension:
//   1. Spins up a Web Worker that runs MediaPipe PoseLandmarker
//   2. Feeds live video frames from the BrowserSource overlay (zero-copy ImageBitmap)
//   3. Receives rendered frames (video + skeleton) back from the Worker
//   4. Pushes each rendered frame to the downstream preview_flow node canvas
//      (sets node._liveFrameImg / previewData so the graph draws it inline)
//   5. Sends keypoint JSON to the backend via the stream WebSocket
//
// Depends on: schemagraph-media-ext.js, schemagraph-extensions.js
// CDN: @mediapipe/tasks-vision loaded dynamically on first use inside Worker
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
		const minConf = data.min_confidence ?? 0.5;
		const modelMap = {
			lite  : 'https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task',
			full  : 'https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_full/float16/1/pose_landmarker_full.task',
			heavy : 'https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_heavy/float16/1/pose_landmarker_heavy.task',
		};
		const modelAssetPath = modelMap[data.model_size] || modelMap.lite;
		try {
			const { PoseLandmarker, FilesetResolver } = await _getMP();
			const resolver = await FilesetResolver.forVisionTasks(
				'https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.32/wasm'
			);
			detector = await PoseLandmarker.createFromOptions(resolver, {
				baseOptions: { modelAssetPath, delegate: 'GPU' },
				runningMode: 'VIDEO',
				numPoses: 1,
				minPoseDetectionConfidence: minConf,
				minPosePresenceConfidence:  minConf,
				minTrackingConfidence:      minConf,
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
	IDLE    : 'idle',
	LOADING : 'loading',
	RUNNING : 'running',
	ERROR   : 'error',
});


// ── FrontendInferenceManager ─────────────────────────────────────────────────
// Workers are keyed by CVFlow node ID.
// Video is read from the BrowserSource overlay.
// Rendered frames are pushed to the downstream preview_flow graph node so the
// graph draws them inline (same mechanism used by stream_display_flow).

class FrontendInferenceManager {
	constructor() {
		this._workers     = new Map();  // cvNodeId -> Worker
		this._states      = new Map();  // cvNodeId -> MLState
		this._pending     = new Map();  // cvNodeId -> bool (backpressure)
		this._captureRafs = new Map();  // cvNodeId -> bool (RAF loop active)
		this._wsRefs      = new Map();  // cvNodeId -> WebSocket
		this._browserRefs = new Map();  // cvNodeId -> browserNode (graph node)
		this._previewRefs = new Map();  // cvNodeId -> previewNode (graph node)
		this._overlayMgr  = null;       // MediaOverlayManager (set by MLStreamExtension)
		this._app         = null;       // SchemaGraphApp ref (for app.draw())
		this._eventBus    = null;
	}

	// cvNode      : ComputerVisionFlow graph node
	// browserNode : BrowserSourceFlow graph node (has the live video element)
	// wsRef       : stream WebSocket for sending keypoints to backend
	// previewNode : preview_flow graph node to push rendered frames to (may be null)
	// cvConfig    : { task, model_size, min_confidence }
	enableForCVNode(cvNode, browserNode, wsRef, previewNode, cvConfig = {}) {
		const cvNodeId = String(cvNode.id);
		if (this._states.get(cvNodeId) === MLState.RUNNING ||
		    this._states.get(cvNodeId) === MLState.LOADING) return;

		this._states.set(cvNodeId, MLState.LOADING);
		this._wsRefs.set(cvNodeId, wsRef);
		this._browserRefs.set(cvNodeId, browserNode);
		this._previewRefs.set(cvNodeId, previewNode ?? null);
		this._log(cvNodeId, `Starting CV Worker (task=${cvConfig.task || 'pose'}, model=${cvConfig.model_size || 'lite'})…`);

		const blob    = new Blob([_ML_WORKER_SOURCE], { type: 'text/javascript' });
		const blobUrl = URL.createObjectURL(blob);
		const worker  = new Worker(blobUrl);
		worker._blobUrl = blobUrl;
		this._workers.set(cvNodeId, worker);

		worker.onmessage = ({ data }) => this._onWorkerMessage(cvNodeId, data);
		worker.onerror   = (err) => {
			console.error(`[CV:${cvNodeId}] Worker error:`, err);
			this._states.set(cvNodeId, MLState.ERROR);
		};

		worker.postMessage({
			type           : 'init',
			task           : cvConfig.task           || 'pose',
			model_size     : cvConfig.model_size     || 'lite',
			min_confidence : cvConfig.min_confidence ?? 0.5,
		});
	}

	disableForCVNode(cvNodeId) {
		cvNodeId = String(cvNodeId);
		this._captureRafs.delete(cvNodeId);
		this._pending.delete(cvNodeId);

		const worker = this._workers.get(cvNodeId);
		if (worker) {
			try { worker.postMessage({ type: 'stop' }); } catch (_) {}
			setTimeout(() => {
				try { worker.terminate(); } catch (_) {}
				if (worker._blobUrl) URL.revokeObjectURL(worker._blobUrl);
			}, 500);
			this._workers.delete(cvNodeId);
		}

		this._states.set(cvNodeId, MLState.IDLE);
		this._wsRefs.delete(cvNodeId);
		this._browserRefs.delete(cvNodeId);
		this._previewRefs.delete(cvNodeId);
		this._log(cvNodeId, 'Stopped.');
	}

	// ── Worker message handler ────────────────────────────────────────────────

	_onWorkerMessage(cvNodeId, data) {
		const { type } = data;

		if (type === 'ready') {
			this._states.set(cvNodeId, MLState.RUNNING);
			this._log(cvNodeId, 'Worker ready — starting capture loop.');
			this._startCaptureLoop(cvNodeId);

		} else if (type === 'error') {
			this._states.set(cvNodeId, MLState.ERROR);
			console.error(`[CV:${cvNodeId}] Worker error: ${data.message}`);

		} else if (type === 'result') {
			this._pending.set(cvNodeId, false);
			const { landmarks, frame, width, height, ts } = data;

			if (frame) this._drawToPreviewNode(cvNodeId, frame);

			if (landmarks) {
				this._sendToWS(cvNodeId, landmarks, width, height);
				this._eventBus?.emit('cv:pose:result', { cvNodeId, landmarks, width, height, ts });
			}
		}
	}

	// ── Capture loop — reads from BrowserSource video, sends to Worker ────────

	_startCaptureLoop(cvNodeId) {
		const minGap = 1000 / 20;  // 20 FPS cap
		let lastInf  = 0;

		this._captureRafs.set(cvNodeId, true);
		this._pending.set(cvNodeId, false);

		const loop = (ts) => {
			if (!this._captureRafs.has(cvNodeId)) return;
			requestAnimationFrame(loop);
			if (ts - lastInf < minGap) return;
			if (this._pending.get(cvNodeId)) return;

			// Locate video via the BrowserSource's media overlay
			const browserNode   = this._browserRefs.get(cvNodeId);
			if (!browserNode) return;
			const mediaOverlay  = this._overlayMgr?.overlays.get(browserNode.id);
			if (!mediaOverlay) return;
			const video = mediaOverlay.querySelector('.sg-media-video');
			if (!video || video.readyState < 2 || video.paused) return;

			const worker = this._workers.get(cvNodeId);
			if (!worker) return;

			lastInf = ts;
			this._pending.set(cvNodeId, true);

			createImageBitmap(video).then(bitmap => {
				if (!this._captureRafs.has(cvNodeId)) { bitmap.close(); return; }
				worker.postMessage(
					{ type: 'detect', bitmap, ts, width: video.videoWidth, height: video.videoHeight },
					[bitmap]
				);
			}).catch(() => { this._pending.set(cvNodeId, false); });
		};

		requestAnimationFrame(loop);
	}

	// ── Push rendered frame into the downstream preview_flow node ─────────────
	// Converts the ImageBitmap → JPEG data URL, then sets the preview node's
	// _liveFrameImg so the graph draws it inline on the next frame.

	_drawToPreviewNode(cvNodeId, frame) {
		const previewNode = this._previewRefs.get(cvNodeId);
		if (!previewNode) {
			console.warn(`[CV:${cvNodeId}] No preview node — wire CVFlow.rendered_image → preview_flow.input`);
			frame.close();
			return;
		}
		if (previewNode._framePending) { frame.close(); return; }  // backpressure

		// Draw into a temporary canvas to get a data URL
		const tmp = document.createElement('canvas');
		tmp.width  = frame.width;
		tmp.height = frame.height;
		tmp.getContext('2d').drawImage(frame, 0, 0);
		frame.close();

		previewNode._framePending = true;
		const dataUrl = tmp.toDataURL('image/jpeg', 0.75);

		const img = new Image();
		img.onload = () => {
			previewNode._liveFrameImg = img;
			previewNode.previewData   = dataUrl;
			previewNode.previewType   = 'image';
			previewNode._framePending = false;

			// Auto-expand on first frame so the image is immediately visible
			if (!previewNode._mlAutoExpanded) {
				previewNode._mlAutoExpanded = true;
				previewNode.extra = previewNode.extra || {};
				previewNode.extra.previewExpanded = true;
				this._app?._recalculatePreviewNodeSize?.(previewNode);
			}

			this._app?.draw?.();
		};
		img.onerror = () => { previewNode._framePending = false; };
		img.src = dataUrl;
	}

	// ── Send keypoints to backend via BrowserSource stream WebSocket ──────────

	_sendToWS(cvNodeId, landmarks, width, height) {
		const ws = this._wsRefs.get(cvNodeId);
		if (ws?.readyState === WebSocket.OPEN) {
			ws.send(JSON.stringify({ type: 'keypoints', inference: 'frontend_pose',
				landmarks, width, height, timestamp: Date.now() }));
		}
	}

	_log(id, msg) { console.log(`[CV:${id}] ${msg}`); }
	getState(cvNodeId) { return this._states.get(String(cvNodeId)) ?? MLState.IDLE; }
}


// ── MLStreamExtension ─────────────────────────────────────────────────────────

class MLStreamExtension extends SchemaGraphExtension {
	constructor(app) {
		super(app);
	}

	_registerNodeTypes() {
		// Must be initialized here (before _setupEventListeners) because super()
		// calls _init() → _registerNodeTypes() → _setupEventListeners() before the
		// constructor body after super() would run.
		this.inferenceManager = new FrontendInferenceManager();
		this._cvBrowserMap    = new Map();  // cvNodeId -> browserNode
	}

	_setupEventListeners() {
		this.on('node:created', (e) => {
			const node = e.node || this.graph.getNodeById(e.nodeId);
			if (!node) return;
			if (this._isCVFrontend(node)) this._onCVNodeAdded(node);
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
			for (const cvNodeId of [...this.inferenceManager._workers.keys()]) {
				this.inferenceManager.disableForCVNode(cvNodeId);
			}
			this._cvBrowserMap.clear();
		});

		// Auto-start/stop when camera becomes active/idle.
		this.on('media:state:changed', ({ nodeId, state }) => {
			if (state === 'active') this._onSourceActive(nodeId);
			if (state === 'idle')   this._onSourceInactive(nodeId);
		});

		// Wire inference manager to MediaOverlayManager and app.
		const mediaExt = this.app?.extensions?.get?.('browser-media');
		if (mediaExt?.overlayManager) {
			this.inferenceManager._overlayMgr = mediaExt.overlayManager;
		}
		this.inferenceManager._app      = this.app;
		this.inferenceManager._eventBus = this.eventBus;
	}

	_extendAPI() {
		this.app.api = this.app.api || {};
		this.app.api.mlStream = {
			getState: (cvNodeOrId) => {
				const id = typeof cvNodeOrId === 'string' ? cvNodeOrId : cvNodeOrId?.id;
				return this.inferenceManager.getState(id);
			},
		};
	}

	// ── CV node helpers ───────────────────────────────────────────────────────

	_isCVNode(node) {
		return node.workflowType === 'computer_vision_flow';
	}

	_isCVFrontend(node) {
		return this._isCVNode(node) &&
			(this._getNodeField(node, 'inference_location') ?? 'frontend') === 'frontend';
	}

	_isBrowserSource(node) {
		return node.workflowType === 'browser_source_flow';
	}

	// Read a named input field (native input value, falls back to properties).
	_getNodeField(node, fieldName) {
		if (node.inputMeta) {
			for (let i = 0; i < node.inputMeta.length; i++) {
				if (node.inputMeta[i]?.name === fieldName) {
					return node.nativeInputs?.[i]?.value;
				}
			}
		}
		return node.properties?.[fieldName];
	}

	_cvConfigFromNode(cvNode) {
		return {
			task           : this._getNodeField(cvNode, 'task')           || 'pose',
			model_size     : this._getNodeField(cvNode, 'model_size')     || 'lite',
			min_confidence : parseFloat(this._getNodeField(cvNode, 'min_confidence') ?? 0.5),
		};
	}

	_findBrowserSourceBySourceId(sourceId) {
		if (!sourceId) return null;
		for (const node of this.graph.nodes) {
			if (!this._isBrowserSource(node)) continue;
			const nid = this._getNodeField(node, 'source_id') ?? node.extra?._browserSourceId;
			if (nid === sourceId) return node;
		}
		return null;
	}

	// Find any CV frontend node connected to the given BrowserSource.
	_findCVNodeForBrowserSource(browserNode) {
		const bSourceId = this._getNodeField(browserNode, 'source_id')
			?? browserNode.extra?._browserSourceId;
		for (const node of this.graph.nodes) {
			if (!this._isCVFrontend(node)) continue;
			if (bSourceId && this._getNodeField(node, 'source_id') === bSourceId) return node;
			if (this._hasEdgeFrom(browserNode, node)) return node;
		}
		return null;
	}

	// Find the BrowserSource connected to the given CV node via graph edges.
	_findBrowserSourceForCVNode(cvNode) {
		if (!cvNode.inputs) return null;
		for (const input of cvNode.inputs) {
			if (!input?.link) continue;
			const link = this.graph.links?.[input.link];
			if (!link) continue;
			const origin = this.graph.getNodeById(link.origin_id);
			if (origin && this._isBrowserSource(origin)) return origin;
		}
		return null;
	}

	// Find the preview_flow node wired to any output of the CVFlow node.
	_findPreviewNodeForCV(cvNode) {
		if (!cvNode.outputs) return null;
		for (const output of cvNode.outputs) {
			const linkIds = output.links || (output.link != null ? [output.link] : []);
			for (const linkId of linkIds) {
				const link = this.graph.links?.[linkId];
				if (!link) continue;
				const target = this.graph.getNodeById(link.target_id);
				if (target?.workflowType === 'preview_flow') return target;
			}
		}
		return null;
	}

	// True when toNode has at least one input edge from fromNode.
	_hasEdgeFrom(fromNode, toNode) {
		if (!toNode.inputs) return false;
		for (const input of toNode.inputs) {
			if (!input?.link) continue;
			const link = this.graph.links?.[input.link];
			if (link?.origin_id === fromNode.id) return true;
		}
		return false;
	}

	// ── Lifecycle ─────────────────────────────────────────────────────────────

	_setupCVNode(cvNode, browserNode) {
		const cvNodeId = String(cvNode.id);

		// Ensure managers are wired (may have been missed if mediaExt wasn't ready yet).
		const mediaExt = this.app?.extensions?.get?.('browser-media');
		if (mediaExt?.overlayManager && !this.inferenceManager._overlayMgr) {
			this.inferenceManager._overlayMgr = mediaExt.overlayManager;
		}
		if (!this.inferenceManager._app) {
			this.inferenceManager._app = this.app;
		}
		if (this.eventBus && !this.inferenceManager._eventBus) {
			this.inferenceManager._eventBus = this.eventBus;
		}

		// Store the preview node reference (may be null if not yet connected).
		const previewNode = this._findPreviewNodeForCV(cvNode);
		this.inferenceManager._previewRefs.set(cvNodeId, previewNode ?? null);

		this._cvBrowserMap.set(cvNodeId, browserNode);

		// If the camera is already active, start inference immediately.
		if (mediaExt?.overlayManager?.states.get(browserNode.id) === 'active') {
			this._startCV(cvNode, browserNode);
		}
	}

	_startCV(cvNode, browserNode) {
		const mediaExt = this.app?.extensions?.get?.('browser-media');
		const ws = mediaExt?.overlayManager?.streamWSockets?.get(browserNode.id) ?? null;
		const cvConfig = this._cvConfigFromNode(cvNode);
		const previewNode = this._findPreviewNodeForCV(cvNode);

		this.inferenceManager.enableForCVNode(cvNode, browserNode, ws, previewNode, cvConfig);
	}

	_onCVNodeAdded(cvNode) {
		setTimeout(() => {
			if (!this._isCVFrontend(cvNode)) return;
			const browserNode = this._findBrowserSourceForCVNode(cvNode)
				?? this._findBrowserSourceBySourceId(this._getNodeField(cvNode, 'source_id'));
			if (!browserNode) return;
			this._setupCVNode(cvNode, browserNode);
		}, 300);
	}

	_onSourceActive(nodeId) {
		const browserNode = this.graph.getNodeById(nodeId);
		if (!browserNode || !this._isBrowserSource(browserNode)) return;
		const cvNode = this._findCVNodeForBrowserSource(browserNode);
		if (!cvNode) return;
		this._setupCVNode(cvNode, browserNode);
		this._startCV(cvNode, browserNode);
	}

	_onSourceInactive(nodeId) {
		for (const [cvNodeId, browserNode] of this._cvBrowserMap) {
			if (String(browserNode.id) === String(nodeId)) {
				this.inferenceManager.disableForCVNode(cvNodeId);
			}
		}
	}

	_onNodeRemoved(nodeId) {
		const nodeIdStr = String(nodeId);
		// CVFlow node removed.
		this.inferenceManager.disableForCVNode(nodeIdStr);
		this._cvBrowserMap.delete(nodeIdStr);
		// BrowserSource node removed — stop any CV node that used it.
		for (const [cvNodeId, browserNode] of this._cvBrowserMap) {
			if (String(browserNode.id) === nodeIdStr) {
				this.inferenceManager.disableForCVNode(cvNodeId);
				this._cvBrowserMap.delete(cvNodeId);
			}
		}
	}

	_reapplyAll() {
		setTimeout(() => {
			for (const node of this.graph.nodes) {
				if (!this._isBrowserSource(node)) continue;
				const cvNode = this._findCVNodeForBrowserSource(node);
				if (cvNode) this._setupCVNode(cvNode, node);
			}
		}, 350);
	}

	_injectStyles() {}
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
