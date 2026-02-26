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
		this.streamWSockets = new Map();// nodeId -> WebSocket (binary stream)
		this._overlayTimers = new Map();// nodeId -> setTimeout handle (overlay auto-clear)

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

		document.body.appendChild(overlay);

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
						: `<div class="sg-media-video-wrapper">
							<video class="sg-media-video" autoplay muted playsinline></video>
							<canvas class="sg-media-display-canvas"></canvas>
							<canvas class="sg-media-overlay-canvas"></canvas>
						</div>`
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
					video.play().catch(e => console.warn('[BrowserMedia] video.play() failed:', e));
					const displayCanvas = overlay?.querySelector('.sg-media-display-canvas');
					if (displayCanvas) this._startVideoRenderer(nodeId, video, displayCanvas);
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
		const nodeId    = node.id;
		const mode      = this._getFieldValue(node, 'mode') || 'event';
		const deviceType= this._getFieldValue(node, 'device_type') || 'webcam';
		const sourceId  = node.extra?._browserSourceId;

		// Clear any existing timer
		if (this.captureTimers.has(nodeId)) {
			clearInterval(this.captureTimers.get(nodeId));
			this.captureTimers.delete(nodeId);
		}

		if (mode === 'stream') {
			// ── High-frequency binary WebSocket streaming ──────────────────
			this._startStreamingWS(node);
		} else {
			// ── Periodic HTTP-POST snapshot (event mode) ───────────────────
			// Also open the display WebSocket so stream_display_flow results
			// (pose overlays, text, etc.) can be routed back to the browser.
			this._startStreamingWS(node, false);   // display-only, no binary frame loop
			const intervalMs = parseInt(this._getFieldValue(node, 'interval_ms')) || 1000;

			const timer = setInterval(async () => {
				if (this.states.get(nodeId) !== MediaState.ACTIVE) {
					clearInterval(timer);
					return;
				}
				try {
					let data;
					if (deviceType === 'microphone') {
						data = { type: 'audio_tick', timestamp: Date.now() };
					} else {
						data = this._captureFrame(nodeId);
						if (!data) return;
					}
					this._pushToNodeOutput(node, data);

					if (sourceId && !this._sendingFrame?.get(nodeId)) {
						this._sendingFrame = this._sendingFrame || new Map();
						this._sendingFrame.set(nodeId, true);
						const baseUrl = this._baseUrl || '';
						fetch(`${baseUrl}/event-sources/browser/${sourceId}/event`, {
							method: 'POST',
							headers: { 'Content-Type': 'application/json' },
							body: JSON.stringify({ ...data, client_id: `browser_${nodeId}` })
						}).then(resp => {
							this._sendingFrame.set(nodeId, false);
							if (resp.status === 400) this._stopCapture(this.nodeRefs.get(nodeId) || node);
						}).catch(() => {
							this._sendingFrame.set(nodeId, false);
						});
					}
				} catch (err) {
					console.warn(`[BrowserMedia] Failed to capture for node ${nodeId}:`, err.message);
				}
			}, intervalMs);

			this.captureTimers.set(nodeId, timer);
		}
	}

	// ── WebSocket binary streaming ────────────────────────────────────────────

	_startStreamingWS(node, startBinaryStream = true) {
		const nodeId   = node.id;
		const sourceId = node.extra?._browserSourceId;
		if (!sourceId || !this._baseUrl) return;

		// Close any existing socket for this node
		const old = this.streamWSockets.get(nodeId);
		if (old && old.readyState < WebSocket.CLOSING) old.close();

		const wsUrl = this._baseUrl.replace(/^http/, 'ws') + `/ws/stream/${sourceId}`;
		const ws    = new WebSocket(wsUrl);

		ws.onopen = () => {
			this.streamWSockets.set(nodeId, ws);
			console.log(`[BrowserMedia] Stream WebSocket open for node ${nodeId}${startBinaryStream ? '' : ' (display-only)'}`);
			if (startBinaryStream) this._startBinaryStreamLoop(node, ws);
		};

		ws.onmessage = (event) => {
			if (typeof event.data === 'string') {
				try {
					const msg = JSON.parse(event.data);
					if (msg.type === 'stream.display') {
						this._renderDisplay(nodeId, msg);
					}
				} catch (e) { /* ignore */ }
			}
		};

		ws.onclose = () => {
			if (this.streamWSockets.get(nodeId) === ws) {
				this.streamWSockets.delete(nodeId);
			}
		};

		ws.onerror = (e) => {
			console.warn(`[BrowserMedia] Stream WebSocket error for node ${nodeId}:`, e);
		};
	}

	_startBinaryStreamLoop(node, ws) {
		const nodeId   = node.id;
		const overlay  = this.overlays.get(nodeId);
		const video    = overlay?.querySelector('.sg-media-video');
		const capCanvas= document.createElement('canvas');
		const FPS      = 15;
		const minGap   = 1000 / FPS;
		let   last     = 0;

		const loop = (ts) => {
			if (this.states.get(nodeId) !== MediaState.ACTIVE) return;
			if (ts - last >= minGap && video?.readyState >= 2 && ws.readyState === WebSocket.OPEN) {
				last = ts;
				capCanvas.width  = video.videoWidth  || 320;
				capCanvas.height = video.videoHeight || 240;
				capCanvas.getContext('2d').drawImage(video, 0, 0);
				capCanvas.toBlob(blob => {
					if (blob && ws.readyState === WebSocket.OPEN) {
						blob.arrayBuffer().then(buf => ws.send(buf)).catch(() => {});
					}
				}, 'image/jpeg', 0.7);
				// Also push to downstream preview nodes
				this._pushToNodeOutput(node, { type: 'frame', data: null /* live */ });
			}
			requestAnimationFrame(loop);
		};
		requestAnimationFrame(loop);
	}

	// ── Overlay rendering ─────────────────────────────────────────────────────

	_renderDisplay(nodeId, msg) {
		const overlay = this.overlays.get(nodeId);
		if (!overlay) return;

		const canvas = overlay.querySelector('.sg-media-overlay-canvas');
		if (!canvas) return;

		// Use CSS display size for the pixel buffer — same reasoning as ML ext:
		// the canvas is displayed at a zoom-dependent CSS size; using the video's
		// native resolution makes drawing primitives sub-pixel and invisible.
		const dpr = window.devicePixelRatio || 1;
		const dw  = canvas.clientWidth  || 320;
		const dh  = canvas.clientHeight || 240;
		canvas.width  = dw * dpr;
		canvas.height = dh * dpr;

		const ctx = canvas.getContext('2d');
		if (dpr !== 1) ctx.scale(dpr, dpr);
		ctx.clearRect(0, 0, dw, dh);

		const { render_type, payload } = msg;

		if ((render_type === 'pose' || render_type === 'landmarks') && payload?.landmarks) {
			this._drawPoseLandmarks(ctx, payload.landmarks, dw, dh, render_type === 'pose');
		} else if (render_type === 'text' && payload != null) {
			ctx.fillStyle = 'rgba(0,0,0,0.55)';
			ctx.fillRect(0, 0, dw, 28);
			ctx.fillStyle = '#00ff88';
			ctx.font      = '13px monospace';
			ctx.fillText(typeof payload === 'string' ? payload : JSON.stringify(payload), 8, 18);
		} else if (render_type === 'custom' && payload) {
			// Raw JSON dump in top-left for debugging
			ctx.fillStyle = '#ffcc00';
			ctx.font      = '11px monospace';
			const lines   = JSON.stringify(payload, null, 2).split('\n').slice(0, 12);
			lines.forEach((l, i) => ctx.fillText(l, 8, 16 + i * 14));
		}

		// Auto-clear stale overlays after 600 ms (use pixel buffer dimensions)
		clearTimeout(this._overlayTimers.get(nodeId));
		this._overlayTimers.set(nodeId, setTimeout(() => {
			const c = overlay.querySelector('.sg-media-overlay-canvas');
			if (c) c.getContext('2d').clearRect(0, 0, c.width, c.height);
		}, 600));
	}

	_drawPoseLandmarks(ctx, landmarks, w, h, drawSkeleton = true) {
		// MediaPipe Pose 33-landmark connections
		const CONNECTIONS = [
			[11,12],[11,13],[13,15],[12,14],[14,16],   // arms
			[11,23],[12,24],[23,24],                    // torso
			[23,25],[25,27],[27,29],[29,31],            // left leg
			[24,26],[26,28],[28,30],[30,32],            // right leg
			[0,1],[1,2],[2,3],[3,7],                    // face left
			[0,4],[4,5],[5,6],[6,8],                    // face right
			[9,10],                                     // mouth
		];

		// Visibility threshold: use 0 — the model-level minPosePresenceConfidence
		// already guards detection quality; some MediaPipe configurations return
		// near-zero visibility scores even for valid landmarks (NORM_RECT warning).
		const VIS_THRESHOLD = 0;

		if (drawSkeleton) {
			ctx.strokeStyle = 'rgba(0, 255, 136, 0.85)';
			ctx.lineWidth   = 2;
			for (const [a, b] of CONNECTIONS) {
				if (a >= landmarks.length || b >= landmarks.length) continue;
				const la = landmarks[a], lb = landmarks[b];
				if ((la.visibility ?? 1) < VIS_THRESHOLD || (lb.visibility ?? 1) < VIS_THRESHOLD) continue;
				ctx.beginPath();
				ctx.moveTo(la.x * w, la.y * h);
				ctx.lineTo(lb.x * w, lb.y * h);
				ctx.stroke();
			}
		}

		// Joints
		for (const lm of landmarks) {
			if ((lm.visibility ?? 1) < VIS_THRESHOLD) continue;
			ctx.fillStyle = 'rgba(255, 80, 80, 0.9)';
			ctx.beginPath();
			ctx.arc(lm.x * w, lm.y * h, 4, 0, Math.PI * 2);
			ctx.fill();
		}
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

		// Push live frames to all downstream preview nodes (traverses through intermediate nodes).
		// Gated by livePreviewOnlyWhenRunning feature flag.
		const ext = this.app?.extensions?.get?.('browser-media');
		if (!ext || !ext._livePreviewOnlyWhenRunning || ext._workflowRunning) {
			this._pushToDownstreamPreviews(node, frameData, new Set());
		}
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



	_startVideoRenderer(nodeId, video, displayCanvas) {
		const ctx = displayCanvas.getContext('2d');
		this._videoRafHandles = this._videoRafHandles || new Map();
		let lastPW = 0, lastPH = 0;

		const render = () => {
			if (this.states.get(nodeId) !== MediaState.ACTIVE) return;

			// Yield to ML Worker when it is rendering composed frames
			const overlay = this.overlays.get(nodeId);
			if (overlay?._mlRendering) {
				this._videoRafHandles.set(nodeId, requestAnimationFrame(render));
				return;
			}

			const dpr = window.devicePixelRatio || 1;
			const cw  = displayCanvas.clientWidth  || 320;
			const ch  = displayCanvas.clientHeight || 240;
			const pw  = Math.round(cw * dpr);
			const ph  = Math.round(ch * dpr);

			if (pw !== lastPW || ph !== lastPH) {
				displayCanvas.width  = pw;
				displayCanvas.height = ph;
				lastPW = pw; lastPH = ph;
			}

			ctx.fillStyle = '#000';
			ctx.fillRect(0, 0, pw, ph);

			if (video.readyState >= 2) {
				const vw = video.videoWidth  || cw;
				const vh = video.videoHeight || ch;
				const scale = Math.min(pw / vw, ph / vh);
				const dw = vw * scale, dh = vh * scale;
				const dx = (pw - dw) / 2, dy = (ph - dh) / 2;
				ctx.drawImage(video, dx, dy, dw, dh);
			}

			this._videoRafHandles.set(nodeId, requestAnimationFrame(render));
		};

		this._videoRafHandles.set(nodeId, requestAnimationFrame(render));
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

		// Close streaming WebSocket
		const ws = this.streamWSockets.get(nodeId);
		if (ws && ws.readyState < WebSocket.CLOSING) ws.close();
		this.streamWSockets.delete(nodeId);

		// Clear overlay auto-clear timer and canvas
		clearTimeout(this._overlayTimers.get(nodeId));
		this._overlayTimers.delete(nodeId);
		const ovCanvas = this.overlays.get(nodeId)?.querySelector('.sg-media-overlay-canvas');
		if (ovCanvas) ovCanvas.getContext('2d').clearRect(0, 0, ovCanvas.width, ovCanvas.height);

		// Cleanup audio context and clear canvas
		const audio = this.audioCtx.get(nodeId);
		if (audio) {
			audio.source.disconnect();
			audio.ctx.close();
			this.audioCtx.delete(nodeId);
		}

		// Stop video canvas renderer
		const vidRaf = this._videoRafHandles?.get(nodeId);
		if (vidRaf) { cancelAnimationFrame(vidRaf); this._videoRafHandles.delete(nodeId); }

		// Clear video element or audio canvas
		const overlay = this.overlays.get(nodeId);
		const video = overlay?.querySelector('.sg-media-video');
		if (video) video.srcObject = null;
		const displayCanvas = overlay?.querySelector('.sg-media-display-canvas');
		if (displayCanvas) { const c = displayCanvas.getContext('2d'); c?.clearRect(0, 0, displayCanvas.width, displayCanvas.height); }
		const audioCanvas = overlay?.querySelector('.sg-media-audio-canvas');
		if (audioCanvas) {
			const ctx = audioCanvas.getContext('2d');
			ctx.clearRect(0, 0, audioCanvas.width, audioCanvas.height);
		}

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
		// Native input values are stored in nativeInputs[i].value, not inputs[i].value.
		// Check inputMeta for actual field name (inputs use display names which may be prettified).
		if (node.inputMeta && node.inputs) {
			for (let i = 0; i < node.inputs.length; i++) {
				const meta = node.inputMeta[i];
				if (meta?.name === fieldName) return node.nativeInputs?.[i]?.value ?? node.inputs[i]?.value;
			}
		}
		// Fallback: direct name match on inputs
		if (node.inputs) {
			for (let i = 0; i < node.inputs.length; i++) {
				if (node.inputs[i].name === fieldName) return node.nativeInputs?.[i]?.value ?? node.inputs[i]?.value;
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

		// Convert canvas-local coords to viewport coords for position:fixed
		const canvasRect = this.app.canvas?.getBoundingClientRect();
		const vpX = overlayX + (canvasRect?.left || 0);
		const vpY = overlayY + (canvasRect?.top  || 0);
		overlay.style.left = `${vpX}px`;
		overlay.style.top = `${vpY}px`;
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
		// When true, live preview updates are suppressed while no workflow is running.
		this._livePreviewOnlyWhenRunning = true;
		this._workflowRunning = false;
	}

	_registerNodeTypes() {
		// No new node types — we enhance existing BrowserSourceFlow nodes
	}

	_setupEventListeners() {

		// Track workflow running state for live-preview gating
		this.on('workflow:started',   () => { this._workflowRunning = true;  });
		this.on('workflow:completed', () => { this._workflowRunning = false; });
		this.on('workflow:failed',    () => { this._workflowRunning = false; });
		this.on('workflow:cancelled', () => { this._workflowRunning = false; });

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
			},
			// Feature toggle: when true, live preview updates are suppressed while
			// no workflow is running. Default: true.
			getLivePreviewOnlyWhenRunning: () => self._livePreviewOnlyWhenRunning,
			setLivePreviewOnlyWhenRunning: (value) => { self._livePreviewOnlyWhenRunning = !!value; },
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
				position: fixed;
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

			.sg-media-video-wrapper {
				position: relative;
				width: 100%;
				height: 100%;
				isolation: isolate;
			}

			.sg-media-video {
				position: absolute;
				top: 0; left: 0;
				width: 100%; height: 100%;
				visibility: hidden;
				pointer-events: none;
			}

			.sg-media-display-canvas {
				width: 100%;
				height: 100%;
				display: block;
				background: #000;
			}

			.sg-media-overlay-canvas {
				position: absolute;
				top: 0; left: 0;
				width: 100%;
				height: 100%;
				pointer-events: none;
				z-index: 1;
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
