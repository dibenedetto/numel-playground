/* ========================================================================
   SCHEMAGRAPH 3D MODEL PREVIEW EXTENSION
   Adds interactive Three.js 3D model preview for PreviewFlow nodes.
   Depends on: schemagraph-extensions.js, dist/threejs-bundle.js
   ======================================================================== */

console.log('[SchemaGraph] Loading 3D preview extension...');

// ========================================================================
// 3D Overlay Manager
// ========================================================================

class Model3DOverlayManager {
	constructor(app, eventBus) {
		this.app = app;
		this.eventBus = eventBus;
		this.overlays = new Map();      // nodeId -> overlay DOM element
		this.renderers = new Map();     // nodeId -> { scene, camera, renderer, controls, animFrameId }
		this.nodeRefs = new Map();      // nodeId -> node reference

		this.Z_BASE = 1000;
		this.Z_SELECTED = 10000;
	}

	// ================================================================
	// Overlay Creation
	// ================================================================

	createOverlay(node, data) {
		const nodeId = node.id;

		// If overlay already exists, just update position
		if (this.overlays.has(nodeId)) {
			this.nodeRefs.set(nodeId, node);
			this._updateOverlayPosition(node, this.overlays.get(nodeId));
			return this.overlays.get(nodeId);
		}

		const overlay = document.createElement('div');
		overlay.className = 'sg-3d-overlay';
		overlay.id = `sg-3d-${nodeId}`;
		overlay.innerHTML = this._buildHTML(node);

		const container = this.app.canvas?.parentElement || document.body;
		container.appendChild(overlay);

		this.overlays.set(nodeId, overlay);
		this.nodeRefs.set(nodeId, node);

		this._updateOverlayPosition(node, overlay);

		// Prevent mouse events from propagating to the graph canvas
		overlay.addEventListener('mousedown', (e) => e.stopPropagation());
		overlay.addEventListener('wheel', (e) => e.stopPropagation(), { passive: false });
		overlay.addEventListener('contextmenu', (e) => { e.preventDefault(); e.stopPropagation(); });

		// Reset button
		const resetBtn = overlay.querySelector('.sg-3d-reset-btn');
		if (resetBtn) {
			resetBtn.addEventListener('click', () => this._resetCamera(nodeId));
		}

		// Initialize Three.js scene
		const threeCanvas = overlay.querySelector('.sg-3d-canvas');
		if (threeCanvas && window.ThreeViewer) {
			this._initThreeScene(nodeId, threeCanvas, data);
		} else {
			const statusText = overlay.querySelector('.sg-3d-status-text');
			if (statusText) statusText.textContent = 'Three.js not loaded';
		}

		return overlay;
	}

	_buildHTML(node) {
		return `
			<div class="sg-3d-container">
				<div class="sg-3d-status">
					<span class="sg-3d-status-indicator"></span>
					<span class="sg-3d-status-text">Loading...</span>
				</div>
				<div class="sg-3d-viewport">
					<canvas class="sg-3d-canvas"></canvas>
				</div>
				<div class="sg-3d-controls">
					<button class="sg-3d-btn sg-3d-reset-btn" title="Reset camera">Reset</button>
				</div>
			</div>`;
	}

	// ================================================================
	// Three.js Scene
	// ================================================================

	_initThreeScene(nodeId, canvas, data) {
		const { THREE, OrbitControls } = window.ThreeViewer;

		const scene = new THREE.Scene();
		scene.background = new THREE.Color(0x1a1a2e);

		const w = canvas.clientWidth || 200;
		const h = canvas.clientHeight || 200;

		const camera = new THREE.PerspectiveCamera(45, w / h, 0.01, 1000);
		camera.position.set(2, 1.5, 3);

		const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: false });
		renderer.setSize(w, h);
		renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
		renderer.toneMapping = THREE.ACESFilmicToneMapping;
		renderer.toneMappingExposure = 1.0;

		const controls = new OrbitControls(camera, canvas);
		controls.enableDamping = true;
		controls.dampingFactor = 0.1;
		controls.target.set(0, 0, 0);

		// Lighting
		const ambientLight = new THREE.AmbientLight(0xffffff, 0.6);
		scene.add(ambientLight);

		const dirLight = new THREE.DirectionalLight(0xffffff, 1.0);
		dirLight.position.set(5, 10, 7);
		scene.add(dirLight);

		const fillLight = new THREE.DirectionalLight(0xffffff, 0.3);
		fillLight.position.set(-3, 2, -5);
		scene.add(fillLight);

		// Grid helper
		const grid = new THREE.GridHelper(4, 8, 0x444466, 0x333355);
		scene.add(grid);

		const ctx = { scene, camera, renderer, controls, animFrameId: null };
		this.renderers.set(nodeId, ctx);

		this._loadModel(nodeId, data);
		this._startRenderLoop(nodeId);
	}

	_loadModel(nodeId, data) {
		const ctx = this.renderers.get(nodeId);
		if (!ctx) return;

		const { THREE, GLTFLoader } = window.ThreeViewer;
		const overlay = this.overlays.get(nodeId);
		const statusText = overlay?.querySelector('.sg-3d-status-text');
		const statusIndicator = overlay?.querySelector('.sg-3d-status-indicator');

		const value = data?.value;
		if (!value) {
			if (statusText) statusText.textContent = 'No model data';
			this._addPlaceholderCube(ctx.scene);
			return;
		}

		const loader = new GLTFLoader();

		const onLoad = (gltf) => {
			const model = gltf.scene;

			// Center and scale model to fit viewport
			const box = new THREE.Box3().setFromObject(model);
			const size = box.getSize(new THREE.Vector3());
			const center = box.getCenter(new THREE.Vector3());
			const maxDim = Math.max(size.x, size.y, size.z);
			const scale = maxDim > 0 ? 2 / maxDim : 1;

			model.scale.setScalar(scale);
			model.position.sub(center.multiplyScalar(scale));
			// Sit on ground plane
			const newBox = new THREE.Box3().setFromObject(model);
			model.position.y -= newBox.min.y;

			ctx.scene.add(model);

			// Point camera at model center
			const modelCenter = new THREE.Box3().setFromObject(model).getCenter(new THREE.Vector3());
			ctx.controls.target.copy(modelCenter);
			ctx.controls.update();

			if (statusText) statusText.textContent = 'Model loaded';
			if (statusIndicator) statusIndicator.classList.add('sg-3d-loaded');
		};

		const onError = (err) => {
			console.error('[3DPreview] Load error:', err);
			if (statusText) statusText.textContent = 'Load error';
			this._addPlaceholderCube(ctx.scene);
		};

		if (typeof value === 'string') {
			if (value.startsWith('data:')) {
				// Data URL — convert to ArrayBuffer
				try {
					const parts = value.split(',');
					const byteString = atob(parts[1]);
					const ab = new ArrayBuffer(byteString.length);
					const ia = new Uint8Array(ab);
					for (let i = 0; i < byteString.length; i++) {
						ia[i] = byteString.charCodeAt(i);
					}
					loader.parse(ab, '', onLoad, onError);
				} catch (e) {
					onError(e);
				}
			} else {
				// URL path
				loader.load(value, onLoad, undefined, onError);
			}
		} else if (value instanceof ArrayBuffer) {
			loader.parse(value, '', onLoad, onError);
		} else {
			if (statusText) statusText.textContent = 'Unsupported format';
			this._addPlaceholderCube(ctx.scene);
		}
	}

	_addPlaceholderCube(scene) {
		const { THREE } = window.ThreeViewer;
		const geometry = new THREE.BoxGeometry(1, 1, 1);
		const material = new THREE.MeshStandardMaterial({ color: 0x4a90d9, wireframe: true });
		const cube = new THREE.Mesh(geometry, material);
		cube.position.y = 0.5;
		scene.add(cube);
	}

	// ================================================================
	// Render Loop
	// ================================================================

	_startRenderLoop(nodeId) {
		const ctx = this.renderers.get(nodeId);
		if (!ctx) return;

		const animate = () => {
			ctx.animFrameId = requestAnimationFrame(animate);
			ctx.controls.update();
			ctx.renderer.render(ctx.scene, ctx.camera);
		};
		animate();
	}

	_stopRenderLoop(nodeId) {
		const ctx = this.renderers.get(nodeId);
		if (ctx?.animFrameId) {
			cancelAnimationFrame(ctx.animFrameId);
			ctx.animFrameId = null;
		}
	}

	_resetCamera(nodeId) {
		const ctx = this.renderers.get(nodeId);
		if (!ctx) return;
		ctx.camera.position.set(2, 1.5, 3);
		ctx.controls.target.set(0, 0, 0);
		ctx.controls.update();
	}

	// ================================================================
	// Overlay Positioning
	// ================================================================

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
		const bounds = node._previewBounds;

		if (bounds) {
			overlay.style.left = (bounds.x * camera.scale + camera.x) + 'px';
			overlay.style.top = (bounds.y * camera.scale + camera.y) + 'px';
			overlay.style.width = Math.max(120, bounds.w * camera.scale) + 'px';
			overlay.style.height = Math.max(60, bounds.h * camera.scale) + 'px';
		} else {
			// Fallback: cover node area below header
			const sx = node.pos[0] * camera.scale + camera.x;
			const sy = node.pos[1] * camera.scale + camera.y + 30 * camera.scale;
			const sw = node.size[0] * camera.scale;
			const sh = node.size[1] * camera.scale - 30 * camera.scale;
			overlay.style.left = sx + 'px';
			overlay.style.top = sy + 'px';
			overlay.style.width = Math.max(120, sw) + 'px';
			overlay.style.height = Math.max(60, sh) + 'px';
		}

		overlay.style.zIndex = this.Z_BASE;

		// Resize Three.js renderer to match new overlay size
		this._resizeRenderer(node.id, overlay);
	}

	_resizeRenderer(nodeId, overlay) {
		const ctx = this.renderers.get(nodeId);
		if (!ctx) return;

		const viewport = overlay.querySelector('.sg-3d-viewport');
		if (!viewport) return;

		const w = viewport.clientWidth;
		const h = viewport.clientHeight;
		if (w > 0 && h > 0) {
			ctx.camera.aspect = w / h;
			ctx.camera.updateProjectionMatrix();
			ctx.renderer.setSize(w, h, false);
		}
	}

	// ================================================================
	// Cleanup
	// ================================================================

	removeOverlay(nodeId) {
		this._disposeThreeResources(nodeId);
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

	_disposeThreeResources(nodeId) {
		this._stopRenderLoop(nodeId);
		const ctx = this.renderers.get(nodeId);
		if (!ctx) return;

		// Dispose all geometries, materials, and textures in the scene
		ctx.scene.traverse((obj) => {
			if (obj.geometry) obj.geometry.dispose();
			if (obj.material) {
				const materials = Array.isArray(obj.material) ? obj.material : [obj.material];
				for (const mat of materials) {
					if (mat.map) mat.map.dispose();
					if (mat.normalMap) mat.normalMap.dispose();
					if (mat.roughnessMap) mat.roughnessMap.dispose();
					if (mat.metalnessMap) mat.metalnessMap.dispose();
					if (mat.emissiveMap) mat.emissiveMap.dispose();
					if (mat.aoMap) mat.aoMap.dispose();
					mat.dispose();
				}
			}
		});

		ctx.controls.dispose();
		ctx.renderer.dispose();
		ctx.renderer.forceContextLoss();

		this.renderers.delete(nodeId);
	}
}

// ========================================================================
// 3D Model Preview Extension
// ========================================================================

class Model3DExtension extends SchemaGraphExtension {
	constructor(app) {
		super(app);
		this._name = 'model3d';
		this.overlayManager = new Model3DOverlayManager(app, this.eventBus);
	}

	_registerNodeTypes() {
		// No new node types — we enhance existing PreviewFlow nodes with model3d data
	}

	_setupEventListeners() {
		// Core event: preview expand/collapse
		this.on('preview:modeToggled', (e) => {
			const node = this.graph.getNodeById(e.nodeId);
			if (!node) return;

			if (e.expanded) {
				const previewData = this.app._getPreviewData(node);
				if (previewData?.type === 'model3d') {
					// Small delay to let _previewBounds update after resize
					requestAnimationFrame(() => {
						this.overlayManager.createOverlay(node, previewData);
					});
				}
			} else {
				this.overlayManager.removeOverlay(e.nodeId);
			}
		});

		// Node lifecycle
		const onNodeRemoved = (e) => {
			const nodeId = e.nodeId || e.node?.id;
			if (nodeId) this.overlayManager.removeOverlay(nodeId);
		};
		this.on('node:removed', onNodeRemoved);
		this.on('node:deleted', onNodeRemoved);

		// Graph lifecycle
		this.on('graph:cleared', () => this.overlayManager.removeAllOverlays());
		this.on('workflow:imported', () => this.overlayManager.removeAllOverlays());
		this.on('workflow:synced', () => this.overlayManager.removeAllOverlays());

		// Position sync
		this.on('camera:moved', () => this.overlayManager.updateAllPositions());
		this.on('camera:zoomed', () => this.overlayManager.updateAllPositions());

		this.on('node:moved', (e) => {
			const node = this.graph.getNodeById(e.nodeId);
			if (node && this.overlayManager.overlays.has(e.nodeId)) {
				this.overlayManager.updateOverlayPosition(node);
			}
		});

		this.on('node:resized', (e) => {
			const node = this.graph.getNodeById(e.nodeId);
			if (node && this.overlayManager.overlays.has(e.nodeId)) {
				this.overlayManager.updateOverlayPosition(node);
			}
		});

		this.on('node:selected', () => this.overlayManager.updateAllPositions());
		this.on('node:deselected', () => this.overlayManager.updateAllPositions());

		// Hook into draw cycle for position sync (same pattern as media extension)
		const originalDraw = this.app.draw?.bind(this.app);
		if (originalDraw) {
			const self = this;
			this.app.draw = function () {
				originalDraw();
				self.overlayManager.updateAllPositions();
			};
		}
	}

	_extendAPI() {
		this.app.api = this.app.api || {};
		this.app.api.model3d = {
			show: (nodeOrId, data) => {
				const node = typeof nodeOrId === 'string'
					? this.graph.getNodeById(nodeOrId) : nodeOrId;
				if (node) this.overlayManager.createOverlay(node, data);
			},
			hide: (nodeOrId) => {
				const nodeId = typeof nodeOrId === 'string' ? nodeOrId : nodeOrId?.id;
				if (nodeId) this.overlayManager.removeOverlay(nodeId);
			},
			hideAll: () => this.overlayManager.removeAllOverlays()
		};
	}

	_injectStyles() {
		if (document.getElementById('sg-3d-styles')) return;
		const style = document.createElement('style');
		style.id = 'sg-3d-styles';
		style.textContent = `
			.sg-3d-overlay {
				position: absolute;
				pointer-events: auto;
				font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
				font-size: 12px;
				border-radius: 4px;
				overflow: hidden;
				transition: opacity 0.15s ease;
			}

			.sg-3d-container {
				display: flex;
				flex-direction: column;
				height: 100%;
				background: var(--sg-bg-secondary, #2a2a2a);
				border: 1px solid var(--sg-border-color, #1a1a1a);
				border-radius: 4px;
				overflow: hidden;
			}

			.sg-3d-status {
				display: flex;
				align-items: center;
				gap: 6px;
				padding: 3px 8px;
				background: var(--sg-bg-tertiary, #353535);
				font-size: 10px;
				color: var(--sg-text-tertiary, #707070);
				border-bottom: 1px solid var(--sg-border-color, #1a1a1a);
				flex-shrink: 0;
			}

			.sg-3d-status-indicator {
				width: 6px;
				height: 6px;
				border-radius: 50%;
				background: var(--sg-accent-orange, #f0ad4e);
				animation: sg-3d-pulse 1s infinite;
				flex-shrink: 0;
			}

			.sg-3d-status-indicator.sg-3d-loaded {
				background: var(--sg-accent-green, #5cb85c);
				animation: none;
			}

			@keyframes sg-3d-pulse {
				0%, 100% { opacity: 1; }
				50% { opacity: 0.4; }
			}

			.sg-3d-viewport {
				flex: 1;
				min-height: 0;
				background: #1a1a2e;
				display: flex;
				align-items: center;
				justify-content: center;
				overflow: hidden;
			}

			.sg-3d-canvas {
				width: 100%;
				height: 100%;
				display: block;
			}

			.sg-3d-controls {
				display: flex;
				gap: 4px;
				padding: 3px 6px;
				background: var(--sg-bg-tertiary, #353535);
				border-top: 1px solid var(--sg-border-color, #1a1a1a);
				flex-shrink: 0;
			}

			.sg-3d-btn {
				padding: 2px 8px;
				border: 1px solid var(--sg-border-color, #555);
				background: var(--sg-bg-secondary, #3a3a3a);
				color: var(--sg-text-secondary, #aaa);
				border-radius: 3px;
				cursor: pointer;
				font-size: 10px;
			}

			.sg-3d-btn:hover {
				background: var(--sg-bg-hover, #4a4a4a);
				color: var(--sg-text-primary, #ddd);
			}
		`;
		document.head.appendChild(style);
	}
}

// ========================================================================
// REGISTRATION
// ========================================================================

if (typeof extensionRegistry !== 'undefined') {
	extensionRegistry.register('model3d', Model3DExtension);
	console.log('[SchemaGraph] 3D model preview extension registered.');
}

if (typeof window !== 'undefined') {
	window.Model3DOverlayManager = Model3DOverlayManager;
	window.Model3DExtension = Model3DExtension;
}

console.log('[SchemaGraph] 3D model preview extension loaded.');
