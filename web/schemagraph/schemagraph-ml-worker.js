// ============================================================================
// SCHEMAGRAPH ML WORKER — MediaPipe Inference in Web Worker
//
// Runs PoseLandmarker inference off the main thread via ImageBitmap transfer.
// Receives video frames as zero-copy ImageBitmaps, returns landmarks + a
// composed ImageBitmap (video frame with skeleton overlay baked in).
//
// Message protocol:
//   Main → Worker:
//     { type: 'init' }
//     { type: 'detect', bitmap: ImageBitmap, ts: number, width: number, height: number }
//     { type: 'stop' }
//
//   Worker → Main:
//     { type: 'ready' }
//     { type: 'error', message: string }
//     { type: 'result', landmarks: Landmark[]|null, frame: ImageBitmap, width, height, ts }
//       (frame transferred as transferable — caller must call frame.close() after use)
// ============================================================================

// Classic worker — load MediaPipe via dynamic import() to avoid Chrome's
// cross-origin redirect restriction on module worker static imports.
const MEDIAPIPE_CDN = 'https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.32/+esm';
let _mp = null;
async function _getMP() {
	if (!_mp) _mp = await import(MEDIAPIPE_CDN);
	return _mp;
}

// ── Pose skeleton connections (MediaPipe Pose 33-landmark model) ──────────────

const POSE_CONNECTIONS = [
	[11, 12], [11, 13], [13, 15], [12, 14], [14, 16],  // arms
	[11, 23], [12, 24], [23, 24],                       // torso
	[23, 25], [25, 27], [24, 26], [26, 28],             // legs
	[27, 29], [29, 31], [28, 30], [30, 32],             // feet
	[0, 1],   [1, 2],   [2, 3],   [3, 7],               // face (right)
	[0, 4],   [4, 5],   [5, 6],   [6, 8],               // face (left)
	[9, 10],                                             // mouth
];

// ── State ─────────────────────────────────────────────────────────────────────

let detector   = null;
let offscreen  = null;   // OffscreenCanvas for composed rendering
let offCtx     = null;   // 2d context for offscreen

// ── Message handler ───────────────────────────────────────────────────────────

self.onmessage = async ({ data }) => {
	const { type } = data;

	// ── init: load MediaPipe and create PoseLandmarker ───────────────────────
	if (type === 'init') {
		try {
			const { PoseLandmarker, FilesetResolver } = await _getMP();
			const resolver = await FilesetResolver.forVisionTasks(
				'https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.32/wasm'
			);
			detector = await PoseLandmarker.createFromOptions(resolver, {
				baseOptions: {
					modelAssetPath: 'https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task',
					delegate: 'GPU',  // GPU preferred; falls back to CPU WASM in workers
				},
				runningMode               : 'VIDEO',
				numPoses                  : 1,
				minPoseDetectionConfidence: 0.5,
				minPosePresenceConfidence : 0.5,
				minTrackingConfidence     : 0.5,
			});
			console.log('[ML Worker] PoseLandmarker ready.');
			self.postMessage({ type: 'ready' });
		} catch (err) {
			console.error('[ML Worker] Init failed:', err);
			self.postMessage({ type: 'error', message: String(err) });
		}

	// ── detect: run inference on received ImageBitmap ────────────────────────
	} else if (type === 'detect') {
		const { bitmap, ts, width, height } = data;
		if (!detector || !bitmap) return;

		// Run pose detection
		let landmarks = null;
		try {
			const result = detector.detectForVideo(bitmap, ts);
			if (result.landmarks?.length > 0) {
				landmarks = result.landmarks[0].map(lm => ({
					x          : lm.x,
					y          : lm.y,
					z          : lm.z,
					visibility : lm.visibility ?? 1,
				}));
			}
		} catch (_) {
			// GPU context lost or transient error — skip this frame
		}

		// Compose output frame: video + skeleton drawn on OffscreenCanvas
		if (!offscreen || offscreen.width !== width || offscreen.height !== height) {
			offscreen = new OffscreenCanvas(width, height);
			offCtx    = offscreen.getContext('2d');
		}
		offCtx.clearRect(0, 0, width, height);
		offCtx.drawImage(bitmap, 0, 0);  // blit received video frame
		bitmap.close();                  // release transferred bitmap

		if (landmarks) {
			_drawSkeleton(offCtx, landmarks, width, height);
		}

		// Transfer composed frame back to main thread (zero-copy)
		const frame = offscreen.transferToImageBitmap();
		self.postMessage({ type: 'result', landmarks, frame, width, height, ts }, [frame]);

	// ── stop: tear down and exit ─────────────────────────────────────────────
	} else if (type === 'stop') {
		try { detector?.close(); } catch (_) {}
		detector  = null;
		offscreen = null;
		offCtx    = null;
		self.close();
	}
};

// ── Skeleton drawing ──────────────────────────────────────────────────────────

function _drawSkeleton(ctx, landmarks, w, h) {
	// Connections (green lines)
	ctx.strokeStyle = 'rgba(0, 255, 100, 0.85)';
	ctx.lineWidth   = 2;
	for (const [a, b] of POSE_CONNECTIONS) {
		const la = landmarks[a];
		const lb = landmarks[b];
		if (!la || !lb) continue;
		ctx.beginPath();
		ctx.moveTo(la.x * w, la.y * h);
		ctx.lineTo(lb.x * w, lb.y * h);
		ctx.stroke();
	}

	// Joints (red dots)
	ctx.fillStyle = 'rgba(255, 80, 80, 0.9)';
	for (const lm of landmarks) {
		ctx.beginPath();
		ctx.arc(lm.x * w, lm.y * h, 4, 0, Math.PI * 2);
		ctx.fill();
	}
}
