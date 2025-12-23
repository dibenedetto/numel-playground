// ========================================================================
// SCHEMAGRAPH PREVIEW EXTENSION
// Adds ability to click on edges and insert preview nodes to inspect
// data flowing through connections. Supports native types and media.
// ========================================================================

const PreviewType = Object.freeze({
	AUTO: 'auto',
	STRING: 'string',
	NUMBER: 'number',
	BOOLEAN: 'boolean',
	JSON: 'json',
	LIST: 'list',
	IMAGE: 'image',
	AUDIO: 'audio',
	VIDEO: 'video',
	MODEL3D: 'model3d',
	UNKNOWN: 'unknown'
});

class PreviewNode extends Node {
	constructor() {
		super('Preview');
		this.isPreviewNode = true;
		this.previewType = PreviewType.AUTO;
		this.previewData = null;
		this.previewError = null;
		this.isExpanded = false;
		this.mediaElement = null;
		
		// Single input and output for pass-through
		this.addInput('in', 'Any');
		this.addOutput('out', 'Any');
		
		// Larger size to show preview
		this.size = [220, 120];
		this.minSize = [180, 80];
		this.maxSize = [400, 400];
		
		// Preview-specific properties
		this.properties = {
			autoDetect: true,
			previewType: PreviewType.AUTO,
			maxStringLength: 200,
			maxArrayItems: 10,
			maxJsonDepth: 3
		};
	}

	onExecute() {
		const inputData = this.getInputData(0);
		this.previewData = inputData;
		this.previewError = null;
		
		// Auto-detect type if enabled
		if (this.properties.autoDetect) {
			this.previewType = this._detectType(inputData);
		} else {
			this.previewType = this.properties.previewType;
		}
		
		// Pass through unchanged
		this.setOutputData(0, inputData);
	}

	_detectType(data) {
		if (data === null || data === undefined) return PreviewType.STRING;
		
		if (typeof data === 'string') {
			// Check for media URLs/data
			if (this._isImageData(data)) return PreviewType.IMAGE;
			if (this._isAudioData(data)) return PreviewType.AUDIO;
			if (this._isVideoData(data)) return PreviewType.VIDEO;
			if (this._is3DModelData(data)) return PreviewType.MODEL3D;
			return PreviewType.STRING;
		}
		
		if (typeof data === 'number') return PreviewType.NUMBER;
		if (typeof data === 'boolean') return PreviewType.BOOLEAN;
		if (Array.isArray(data)) return PreviewType.LIST;
		if (typeof data === 'object') {
			// Check for typed media objects
			if (data.type === 'image' || data.mimeType?.startsWith('image/')) return PreviewType.IMAGE;
			if (data.type === 'audio' || data.mimeType?.startsWith('audio/')) return PreviewType.AUDIO;
			if (data.type === 'video' || data.mimeType?.startsWith('video/')) return PreviewType.VIDEO;
			if (data.type === 'model3d' || data.mimeType?.includes('model')) return PreviewType.MODEL3D;
			return PreviewType.JSON;
		}
		
		return PreviewType.UNKNOWN;
	}

	_isImageData(str) {
		if (!str) return false;
		const lower = str.toLowerCase();
		return lower.startsWith('data:image/') ||
			/\.(jpg|jpeg|png|gif|webp|svg|bmp|ico)(\?|$)/i.test(str) ||
			lower.includes('image/');
	}

	_isAudioData(str) {
		if (!str) return false;
		const lower = str.toLowerCase();
		return lower.startsWith('data:audio/') ||
			/\.(mp3|wav|ogg|m4a|flac|aac)(\?|$)/i.test(str) ||
			lower.includes('audio/');
	}

	_isVideoData(str) {
		if (!str) return false;
		const lower = str.toLowerCase();
		return lower.startsWith('data:video/') ||
			/\.(mp4|webm|ogg|mov|avi|mkv)(\?|$)/i.test(str) ||
			lower.includes('video/');
	}

	_is3DModelData(str) {
		if (!str) return false;
		return /\.(glb|gltf|obj|fbx|stl|3ds)(\?|$)/i.test(str);
	}

	getPreviewText() {
		if (this.previewError) return `Error: ${this.previewError}`;
		if (this.previewData === null) return 'null';
		if (this.previewData === undefined) return 'undefined';
		
		switch (this.previewType) {
			case PreviewType.STRING:
				const str = String(this.previewData);
				if (str.length > this.properties.maxStringLength) {
					return str.substring(0, this.properties.maxStringLength) + '...';
				}
				return str;
			
			case PreviewType.NUMBER:
				return String(this.previewData);
			
			case PreviewType.BOOLEAN:
				return this.previewData ? 'true' : 'false';
			
			case PreviewType.LIST:
				const arr = this.previewData;
				const maxItems = this.properties.maxArrayItems;
				if (arr.length <= maxItems) {
					return `[${arr.length}] ${JSON.stringify(arr).substring(0, 100)}`;
				}
				return `[${arr.length}] ${JSON.stringify(arr.slice(0, maxItems))}...`;
			
			case PreviewType.JSON:
				try {
					const json = JSON.stringify(this.previewData, null, 2);
					if (json.length > this.properties.maxStringLength) {
						return json.substring(0, this.properties.maxStringLength) + '...';
					}
					return json;
				} catch (e) {
					return '[Object]';
				}
			
			case PreviewType.IMAGE:
				return '🖼️ Image';
			
			case PreviewType.AUDIO:
				return '🔊 Audio';
			
			case PreviewType.VIDEO:
				return '🎬 Video';
			
			case PreviewType.MODEL3D:
				return '🧊 3D Model';
			
			default:
				return String(this.previewData);
		}
	}

	getMediaSource() {
		if (!this.previewData) return null;
		
		if (typeof this.previewData === 'string') {
			return this.previewData;
		}
		
		if (typeof this.previewData === 'object') {
			return this.previewData.url || this.previewData.src || this.previewData.data || null;
		}
		
		return null;
	}
}

// ========================================================================
// PreviewOverlay - Renders expanded previews as HTML overlays
// ========================================================================

class PreviewOverlay {
	constructor(app) {
		this.app = app;
		this.activeNode = null;
		this.overlayElement = null;
		this._createOverlayElement();
	}

	_createOverlayElement() {
		this.overlayElement = document.createElement('div');
		this.overlayElement.id = 'sg-preview-overlay';
		this.overlayElement.className = 'sg-preview-overlay';
		this.overlayElement.innerHTML = `
			<div class="sg-preview-overlay-header">
				<span class="sg-preview-overlay-title">Preview</span>
				<div class="sg-preview-overlay-actions">
					<select class="sg-preview-type-select">
						<option value="auto">Auto</option>
						<option value="string">String</option>
						<option value="number">Number</option>
						<option value="boolean">Boolean</option>
						<option value="json">JSON</option>
						<option value="list">List</option>
						<option value="image">Image</option>
						<option value="audio">Audio</option>
						<option value="video">Video</option>
						<option value="model3d">3D Model</option>
					</select>
					<button class="sg-preview-close-btn">✕</button>
				</div>
			</div>
			<div class="sg-preview-overlay-content"></div>
		`;
		
		document.body.appendChild(this.overlayElement);
		
		// Event handlers
		this.overlayElement.querySelector('.sg-preview-close-btn')
			.addEventListener('click', () => this.hide());
		
		this.overlayElement.querySelector('.sg-preview-type-select')
			.addEventListener('change', (e) => this._onTypeChange(e.target.value));
	}

	show(node, screenX, screenY) {
		if (!node || !node.isPreviewNode) return;
		
		this.activeNode = node;
		node.isExpanded = true;
		
		const content = this.overlayElement.querySelector('.sg-preview-overlay-content');
		const typeSelect = this.overlayElement.querySelector('.sg-preview-type-select');
		
		typeSelect.value = node.properties.autoDetect ? 'auto' : node.properties.previewType;
		
		this._renderContent(content, node);
		
		// Position overlay
		const rect = this.app.canvas.getBoundingClientRect();
		let x = screenX + rect.left;
		let y = screenY + rect.top;
		
		// Keep within viewport
		const overlayRect = this.overlayElement.getBoundingClientRect();
		if (x + 320 > window.innerWidth) x = window.innerWidth - 330;
		if (y + 200 > window.innerHeight) y = window.innerHeight - 210;
		
		this.overlayElement.style.left = x + 'px';
		this.overlayElement.style.top = y + 'px';
		this.overlayElement.classList.add('show');
	}

	hide() {
		if (this.activeNode) {
			this.activeNode.isExpanded = false;
		}
		this.activeNode = null;
		this.overlayElement.classList.remove('show');
		
		// Clean up any media elements
		const content = this.overlayElement.querySelector('.sg-preview-overlay-content');
		content.innerHTML = '';
	}

	_onTypeChange(type) {
		if (!this.activeNode) return;
		
		if (type === 'auto') {
			this.activeNode.properties.autoDetect = true;
			this.activeNode.previewType = this.activeNode._detectType(this.activeNode.previewData);
		} else {
			this.activeNode.properties.autoDetect = false;
			this.activeNode.properties.previewType = type;
			this.activeNode.previewType = type;
		}
		
		const content = this.overlayElement.querySelector('.sg-preview-overlay-content');
		this._renderContent(content, this.activeNode);
		this.app.draw();
	}

	_renderContent(container, node) {
		container.innerHTML = '';
		
		const data = node.previewData;
		const type = node.previewType;
		
		switch (type) {
			case PreviewType.IMAGE:
				this._renderImage(container, node);
				break;
			
			case PreviewType.AUDIO:
				this._renderAudio(container, node);
				break;
			
			case PreviewType.VIDEO:
				this._renderVideo(container, node);
				break;
			
			case PreviewType.MODEL3D:
				this._render3DModel(container, node);
				break;
			
			case PreviewType.JSON:
			case PreviewType.LIST:
				this._renderJSON(container, data);
				break;
			
			case PreviewType.BOOLEAN:
				this._renderBoolean(container, data);
				break;
			
			default:
				this._renderText(container, node.getPreviewText());
		}
	}

	_renderText(container, text) {
		const pre = document.createElement('pre');
		pre.className = 'sg-preview-text';
		pre.textContent = text;
		container.appendChild(pre);
	}

	_renderJSON(container, data) {
		const pre = document.createElement('pre');
		pre.className = 'sg-preview-json';
		try {
			pre.textContent = JSON.stringify(data, null, 2);
		} catch (e) {
			pre.textContent = String(data);
		}
		container.appendChild(pre);
	}

	_renderBoolean(container, value) {
		const div = document.createElement('div');
		div.className = 'sg-preview-boolean ' + (value ? 'true' : 'false');
		div.innerHTML = `
			<span class="sg-preview-bool-icon">${value ? '✓' : '✗'}</span>
			<span class="sg-preview-bool-text">${value ? 'true' : 'false'}</span>
		`;
		container.appendChild(div);
	}

	_renderImage(container, node) {
		const src = node.getMediaSource();
		if (!src) {
			this._renderText(container, 'No image source');
			return;
		}
		
		const img = document.createElement('img');
		img.className = 'sg-preview-image';
		img.src = src;
		img.alt = 'Preview';
		img.onerror = () => {
			container.innerHTML = '<div class="sg-preview-error">Failed to load image</div>';
		};
		container.appendChild(img);
	}

	_renderAudio(container, node) {
		const src = node.getMediaSource();
		if (!src) {
			this._renderText(container, 'No audio source');
			return;
		}
		
		const wrapper = document.createElement('div');
		wrapper.className = 'sg-preview-audio-wrapper';
		wrapper.innerHTML = `
			<div class="sg-preview-audio-icon">🔊</div>
			<audio controls class="sg-preview-audio">
				<source src="${src}">
				Your browser does not support audio playback.
			</audio>
		`;
		container.appendChild(wrapper);
	}

	_renderVideo(container, node) {
		const src = node.getMediaSource();
		if (!src) {
			this._renderText(container, 'No video source');
			return;
		}
		
		const video = document.createElement('video');
		video.className = 'sg-preview-video';
		video.controls = true;
		video.src = src;
		video.onerror = () => {
			container.innerHTML = '<div class="sg-preview-error">Failed to load video</div>';
		};
		container.appendChild(video);
	}

	_render3DModel(container, node) {
		const src = node.getMediaSource();
		
		const wrapper = document.createElement('div');
		wrapper.className = 'sg-preview-3d-wrapper';
		wrapper.innerHTML = `
			<div class="sg-preview-3d-placeholder">
				<div class="sg-preview-3d-icon">🧊</div>
				<div class="sg-preview-3d-text">3D Model Preview</div>
				<div class="sg-preview-3d-info">${src ? 'Source: ' + src.substring(0, 50) + '...' : 'No source'}</div>
				<div class="sg-preview-3d-hint">Integration with Three.js viewer coming soon</div>
			</div>
		`;
		container.appendChild(wrapper);
	}

	update() {
		if (this.activeNode && this.overlayElement.classList.contains('show')) {
			const content = this.overlayElement.querySelector('.sg-preview-overlay-content');
			this._renderContent(content, this.activeNode);
		}
	}
}

// ========================================================================
// Edge Hit Detection & Preview Node Insertion
// ========================================================================

class EdgePreviewManager {
	constructor(app) {
		this.app = app;
		this.graph = app.graph;
		this.eventBus = app.eventBus;
		this.previewOverlay = new PreviewOverlay(app);
		this.hoveredLink = null;
		this.linkHitDistance = 10;
		
		this._registerPreviewNodeType();
		this._setupEventListeners();
		this._injectStyles();
	}

	_registerPreviewNodeType() {
		this.graph.nodeTypes['Native.Preview'] = PreviewNode;
	}

	_setupEventListeners() {
		this.eventBus.on('mouse:move'    , (data) => this._onMouseMove   (data));
		this.eventBus.on('mouse:down'    , (data) => this._onMouseDown   (data));
		this.eventBus.on('mouse:dblclick', (data) => this._onDoubleClick (data));
		this.eventBus.on('contextmenu'   , (data) => this._onContextMenu (data));
	}

	_onMouseMove(data) {
		if (this.app.connecting || this.app.dragNode || this.app.isPanning) {
			this.hoveredLink = null;
			return;
		}
		
		const [wx, wy] = this.app.screenToWorld(data.coords.screenX, data.coords.screenY);
		this.hoveredLink = this._findLinkAtPosition(wx, wy);
		
		if (this.hoveredLink) {
			this.app.canvas.style.cursor = 'pointer';
		}
	}

	_onMouseDown(data) {
		if (data.button !== 0) return;
		if (this.app.connecting || this.app.dragNode) return;
		
		const [wx, wy] = this.app.screenToWorld(data.coords.screenX, data.coords.screenY);
		const link = this._findLinkAtPosition(wx, wy);
		
		if (link && data.event.altKey) {
			data.event.preventDefault();
			data.event.stopPropagation();
			this.insertPreviewNode(link, wx, wy);
			return true;
		}
	}

	_onDoubleClick(data) {
		const [wx, wy] = this.app.screenToWorld(data.coords.screenX, data.coords.screenY);
		
		// Check if clicking on a preview node
		for (const node of this.graph.nodes) {
			if (!node.isPreviewNode) continue;
			
			if (wx >= node.pos[0] && wx <= node.pos[0] + node.size[0] &&
				wy >= node.pos[1] && wy <= node.pos[1] + node.size[1]) {
				
				// Calculate screen position for overlay
				const [sx, sy] = this.app.worldToScreen(node.pos[0] + node.size[0], node.pos[1]);
				this.previewOverlay.show(node, sx, sy);
				return;
			}
		}
	}

	_findLinkAtPosition(wx, wy) {
		const threshold = this.linkHitDistance / this.app.camera.scale;
		
		for (const linkId in this.graph.links) {
			const link = this.graph.links[linkId];
			const orig = this.graph.getNodeById(link.origin_id);
			const targ = this.graph.getNodeById(link.target_id);
			
			if (!orig || !targ) continue;
			
			const x1 = orig.pos[0] + orig.size[0];
			const y1 = orig.pos[1] + 33 + link.origin_slot * 25;
			const x2 = targ.pos[0];
			const y2 = targ.pos[1] + 33 + link.target_slot * 25;
			
			if (this._pointNearBezier(wx, wy, x1, y1, x2, y2, threshold)) {
				return link;
			}
		}
		
		return null;
	}

	_pointNearBezier(px, py, x1, y1, x2, y2, threshold) {
		// Sample bezier curve and check distance
		const samples = 20;
		const dx = x2 - x1;
		const controlOffset = Math.min(Math.abs(dx) * 0.5, 200);
		const cx1 = x1 + controlOffset;
		const cx2 = x2 - controlOffset;
		
		for (let i = 0; i <= samples; i++) {
			const t = i / samples;
			const t2 = t * t;
			const t3 = t2 * t;
			const mt = 1 - t;
			const mt2 = mt * mt;
			const mt3 = mt2 * mt;
			
			// Cubic bezier
			const bx = mt3 * x1 + 3 * mt2 * t * cx1 + 3 * mt * t2 * cx2 + t3 * x2;
			const by = mt3 * y1 + 3 * mt2 * t * y1 + 3 * mt * t2 * y2 + t3 * y2;
			
			const dist = Math.sqrt((px - bx) ** 2 + (py - by) ** 2);
			if (dist < threshold) return true;
		}
		
		return false;
	}

	insertPreviewNode(link, wx, wy) {
		const orig = this.graph.getNodeById(link.origin_id);
		const targ = this.graph.getNodeById(link.target_id);
		
		if (!orig || !targ) return null;
		
		// Create preview node
		const previewNode = this.graph.createNode('Native.Preview');
		previewNode.pos = [wx - previewNode.size[0] / 2, wy - previewNode.size[1] / 2];
		
		// Store original link info
		const origSlot = link.origin_slot;
		const targSlot = link.target_slot;
		const linkType = link.type;
		
		// Remove original link
		this._removeLink(link);
		
		// Create new links through preview node
		// Original -> Preview
		const link1Id = ++this.graph.last_link_id;
		const link1 = new Link(link1Id, orig.id, origSlot, previewNode.id, 0, linkType);
		this.graph.links[link1Id] = link1;
		orig.outputs[origSlot].links.push(link1Id);
		previewNode.inputs[0].link = link1Id;
		
		// Preview -> Target
		const link2Id = ++this.graph.last_link_id;
		const link2 = new Link(link2Id, previewNode.id, 0, targ.id, targSlot, linkType);
		this.graph.links[link2Id] = link2;
		previewNode.outputs[0].links.push(link2Id);
		
		// Handle multi-input target slots
		if (targ.multiInputs && targ.multiInputs[targSlot]) {
			targ.multiInputs[targSlot].links.push(link2Id);
		} else {
			targ.inputs[targSlot].link = link2Id;
		}
		
		// Execute to get data
		previewNode.onExecute();
		
		this.eventBus.emit('preview:inserted', { nodeId: previewNode.id, linkId: link.id });
		this.app.draw();
		
		return previewNode;
	}

	_removeLink(link) {
		const orig = this.graph.getNodeById(link.origin_id);
		const targ = this.graph.getNodeById(link.target_id);
		
		if (orig) {
			const idx = orig.outputs[link.origin_slot].links.indexOf(link.id);
			if (idx > -1) orig.outputs[link.origin_slot].links.splice(idx, 1);
		}
		
		if (targ) {
			if (targ.multiInputs && targ.multiInputs[link.target_slot]) {
				const idx = targ.multiInputs[link.target_slot].links.indexOf(link.id);
				if (idx > -1) targ.multiInputs[link.target_slot].links.splice(idx, 1);
			} else {
				targ.inputs[link.target_slot].link = null;
			}
		}
		
		delete this.graph.links[link.id];
		this.eventBus.emit('link:deleted', { linkId: link.id });
	}

	removePreviewNode(node) {
		if (!node || !node.isPreviewNode) return false;
		
		// Get incoming and outgoing links
		const inLink = node.inputs[0]?.link ? this.graph.links[node.inputs[0].link] : null;
		const outLinks = node.outputs[0]?.links.map(id => this.graph.links[id]).filter(Boolean) || [];
		
		if (inLink && outLinks.length > 0) {
			const orig = this.graph.getNodeById(inLink.origin_id);
			const origSlot = inLink.origin_slot;
			
			// Reconnect each output target to original source
			for (const outLink of outLinks) {
				const targ = this.graph.getNodeById(outLink.target_id);
				const targSlot = outLink.target_slot;
				
				if (orig && targ) {
					const newLinkId = ++this.graph.last_link_id;
					const newLink = new Link(newLinkId, orig.id, origSlot, targ.id, targSlot, inLink.type);
					this.graph.links[newLinkId] = newLink;
					orig.outputs[origSlot].links.push(newLinkId);
					
					if (targ.multiInputs && targ.multiInputs[targSlot]) {
						targ.multiInputs[targSlot].links.push(newLinkId);
					} else {
						targ.inputs[targSlot].link = newLinkId;
					}
				}
			}
		}
		
		// Remove the preview node
		this.app.removeNode(node);
		this.previewOverlay.hide();
		
		return true;
	}

	_injectStyles() {
		if (document.getElementById('sg-preview-styles')) return;
		
		const style = document.createElement('style');
		style.id = 'sg-preview-styles';
		style.textContent = `
			.sg-preview-overlay {
				position: fixed;
				width: 320px;
				max-height: 400px;
				background: var(--sg-bg-secondary, #2a2a2a);
				border: 1px solid var(--sg-border-highlight, #46a2da);
				border-radius: 8px;
				box-shadow: 0 8px 32px rgba(0, 0, 0, 0.6);
				z-index: 2000;
				display: none;
				flex-direction: column;
				overflow: hidden;
			}
			
			.sg-preview-overlay.show {
				display: flex;
				animation: sg-previewFadeIn 0.2s ease;
			}
			
			@keyframes sg-previewFadeIn {
				from { opacity: 0; transform: translateY(-10px) scale(0.95); }
				to { opacity: 1; transform: translateY(0) scale(1); }
			}
			
			.sg-preview-overlay-header {
				display: flex;
				justify-content: space-between;
				align-items: center;
				padding: 8px 12px;
				background: var(--sg-bg-tertiary, #353535);
				border-bottom: 1px solid var(--sg-border-color, #1a1a1a);
			}
			
			.sg-preview-overlay-title {
				font-size: 12px;
				font-weight: 600;
				color: var(--sg-text-primary, #fff);
				text-transform: uppercase;
				letter-spacing: 0.5px;
			}
			
			.sg-preview-overlay-actions {
				display: flex;
				gap: 8px;
				align-items: center;
			}
			
			.sg-preview-type-select {
				background: var(--sg-bg-quaternary, #404040);
				color: var(--sg-text-primary, #fff);
				border: 1px solid var(--sg-border-color, #1a1a1a);
				border-radius: 4px;
				padding: 2px 6px;
				font-size: 11px;
				cursor: pointer;
			}
			
			.sg-preview-close-btn {
				background: var(--sg-accent-red, #dc6464);
				color: white;
				border: none;
				border-radius: 4px;
				padding: 2px 8px;
				cursor: pointer;
				font-size: 12px;
				font-weight: bold;
			}
			
			.sg-preview-close-btn:hover {
				background: #ff4444;
			}
			
			.sg-preview-overlay-content {
				flex: 1;
				overflow: auto;
				padding: 12px;
				max-height: 340px;
			}
			
			.sg-preview-text,
			.sg-preview-json {
				margin: 0;
				padding: 8px;
				background: var(--sg-bg-tertiary, #353535);
				border-radius: 4px;
				font-family: 'Courier New', monospace;
				font-size: 11px;
				color: var(--sg-text-primary, #fff);
				white-space: pre-wrap;
				word-break: break-all;
				max-height: 300px;
				overflow: auto;
			}
			
			.sg-preview-boolean {
				display: flex;
				align-items: center;
				justify-content: center;
				gap: 12px;
				padding: 20px;
				border-radius: 8px;
				font-size: 24px;
				font-weight: bold;
			}
			
			.sg-preview-boolean.true {
				background: rgba(146, 208, 80, 0.2);
				color: var(--sg-accent-green, #92d050);
			}
			
			.sg-preview-boolean.false {
				background: rgba(220, 100, 100, 0.2);
				color: var(--sg-accent-red, #dc6464);
			}
			
			.sg-preview-bool-icon {
				font-size: 32px;
			}
			
			.sg-preview-image {
				max-width: 100%;
				max-height: 280px;
				border-radius: 4px;
				object-fit: contain;
			}
			
			.sg-preview-audio-wrapper {
				display: flex;
				flex-direction: column;
				align-items: center;
				gap: 12px;
				padding: 20px;
			}
			
			.sg-preview-audio-icon {
				font-size: 48px;
			}
			
			.sg-preview-audio {
				width: 100%;
			}
			
			.sg-preview-video {
				max-width: 100%;
				max-height: 280px;
				border-radius: 4px;
			}
			
			.sg-preview-3d-wrapper {
				padding: 20px;
			}
			
			.sg-preview-3d-placeholder {
				display: flex;
				flex-direction: column;
				align-items: center;
				justify-content: center;
				padding: 30px;
				background: var(--sg-bg-tertiary, #353535);
				border: 2px dashed var(--sg-border-color, #1a1a1a);
				border-radius: 8px;
				text-align: center;
			}
			
			.sg-preview-3d-icon {
				font-size: 48px;
				margin-bottom: 12px;
			}
			
			.sg-preview-3d-text {
				font-size: 14px;
				font-weight: 600;
				color: var(--sg-text-primary, #fff);
				margin-bottom: 8px;
			}
			
			.sg-preview-3d-info {
				font-size: 10px;
				color: var(--sg-text-tertiary, #707070);
				margin-bottom: 8px;
				word-break: break-all;
			}
			
			.sg-preview-3d-hint {
				font-size: 10px;
				color: var(--sg-accent-blue, #46a2da);
				font-style: italic;
			}
			
			.sg-preview-error {
				padding: 20px;
				text-align: center;
				color: var(--sg-accent-red, #dc6464);
				font-size: 12px;
			}

			/* ========================================================================
			   PREVIEW FLASH ANIMATIONS - Add to existing preview styles
			   ======================================================================== */

			/* Overlay flash animation */
			.sg-preview-overlay.flash {
				animation: sg-overlayFlash 0.5s ease-out;
			}

			.sg-preview-overlay.flash .sg-preview-overlay-content {
				animation: sg-contentFlash 0.5s ease-out;
			}

			@keyframes sg-overlayFlash {
				0% {
					box-shadow: 0 8px 32px rgba(0, 0, 0, 0.6),
								0 0 30px rgba(70, 162, 218, 0.8),
								inset 0 0 20px rgba(70, 162, 218, 0.3);
					border-color: #82c4ec;
				}
				50% {
					box-shadow: 0 8px 32px rgba(0, 0, 0, 0.6),
								0 0 50px rgba(146, 208, 80, 0.9),
								inset 0 0 30px rgba(146, 208, 80, 0.4);
					border-color: #92d050;
				}
				100% {
					box-shadow: 0 8px 32px rgba(0, 0, 0, 0.6);
					border-color: var(--sg-border-highlight, #46a2da);
				}
			}

			@keyframes sg-contentFlash {
				0% {
					background: rgba(70, 162, 218, 0.2);
				}
				50% {
					background: rgba(146, 208, 80, 0.3);
				}
				100% {
					background: transparent;
				}
			}

			/* Data update indicator badge */
			.sg-preview-overlay-header::after {
				content: '';
				position: absolute;
				top: 8px;
				right: 80px;
				width: 8px;
				height: 8px;
				background: transparent;
				border-radius: 50%;
				transition: all 0.3s ease;
			}

			.sg-preview-overlay.flash .sg-preview-overlay-header::after {
				animation: sg-updatePulse 0.5s ease-out;
			}

			@keyframes sg-updatePulse {
				0% {
					background: #92d050;
					box-shadow: 0 0 10px #92d050;
					transform: scale(1.5);
				}
				100% {
					background: transparent;
					box-shadow: none;
					transform: scale(1);
				}
			}

			/* Live indicator for streaming data */
			.sg-preview-live-indicator {
				display: inline-flex;
				align-items: center;
				gap: 6px;
				padding: 2px 8px;
				background: rgba(146, 208, 80, 0.2);
				border: 1px solid #92d050;
				border-radius: 10px;
				font-size: 10px;
				font-weight: 600;
				color: #92d050;
				margin-left: 8px;
			}

			.sg-preview-live-indicator::before {
				content: '';
				width: 6px;
				height: 6px;
				background: #92d050;
				border-radius: 50%;
				animation: sg-livePulse 1s ease-in-out infinite;
			}

			@keyframes sg-livePulse {
				0%, 100% {
					opacity: 1;
					transform: scale(1);
				}
				50% {
					opacity: 0.5;
					transform: scale(0.8);
				}
			}

			/* Timestamp display */
			.sg-preview-timestamp {
				font-size: 9px;
				color: var(--sg-text-tertiary, #707070);
				margin: 0;
				padding: 8px 12px;
				border-top: 1px solid var(--sg-border-color, #1a1a1a);
				text-align: right;
				background: var(--sg-bg-tertiary, #353535);
			}

			.sg-preview-timestamp:empty {
				display: none;
			}

			/* Ripple effect for content updates */
			.sg-preview-overlay-content {
				position: relative;
				overflow: hidden;
			}

			.sg-preview-overlay.flash .sg-preview-overlay-content::before {
				content: '';
				position: absolute;
				top: 50%;
				left: 50%;
				width: 10px;
				height: 10px;
				background: rgba(146, 208, 80, 0.6);
				border-radius: 50%;
				transform: translate(-50%, -50%) scale(0);
				animation: sg-ripple 0.5s ease-out forwards;
				pointer-events: none;
			}

			@keyframes sg-ripple {
				0% {
					transform: translate(-50%, -50%) scale(0);
					opacity: 1;
				}
				100% {
					transform: translate(-50%, -50%) scale(40);
					opacity: 0;
				}
			}

			/* Context menu styles for preview */
			.sg-preview-context-menu {
				min-width: 180px;
			}

			.sg-preview-context-menu .sg-context-menu-divider {
				height: 1px;
				background: var(--sg-border-color, #1a1a1a);
				margin: 4px 0;
				padding: 0;
				pointer-events: none;
			}

			.sg-preview-context-menu .sg-context-menu-item:hover {
				background: var(--sg-accent-blue);
				color: #fff;
			}
		`;
		
		document.head.appendChild(style);
	}

	// ========================================================================
	// EDGE PREVIEW CONTEXT MENU
	// Add right-click menu option to toggle preview on edges
	// Add to EdgePreviewManager in schemagraph-preview-ext.js
	// ========================================================================

	/**
	 * Add to EdgePreviewManager._setupEventListeners
	 */
	_setupEventListeners() {
		// Track mouse for edge hover
		this.eventBus.on('mouse:move', (data) => this._onMouseMove(data));
		
		// Handle edge click (Alt+Click to add preview)
		this.eventBus.on('mouse:down', (data) => this._onMouseDown(data));
		
		// Handle double-click on preview node to expand
		this.eventBus.on('mouse:dblclick', (data) => this._onDoubleClick(data));
		
		// Handle right-click for context menu
		this.eventBus.on('contextmenu', (data) => this._onContextMenu(data));
	}

	/**
	 * Handle right-click context menu on edges
	 */
	_onContextMenu(data) {
		const [wx, wy] = this.app.screenToWorld(data.coords.screenX, data.coords.screenY);
		
		// Check if clicking on an edge
		const link = this._findLinkAtPosition(wx, wy);
		if (link) {
			data.event.preventDefault();
			this._showEdgeContextMenu(link, data.coords.screenX, data.coords.screenY, wx, wy);
			return true;
		}
		
		// Check if clicking on a preview node
		for (const node of this.graph.nodes) {
			if (!node.isPreviewNode) continue;
			
			if (wx >= node.pos[0] && wx <= node.pos[0] + node.size[0] &&
				wy >= node.pos[1] && wy <= node.pos[1] + node.size[1]) {
				data.event.preventDefault();
				this._showPreviewNodeContextMenu(node, data.coords.screenX, data.coords.screenY);
				return true;
			}
		}
	}

	/**
	 * Show context menu for edge
	 */
	_showEdgeContextMenu(link, screenX, screenY, worldX, worldY) {
		const menu = this._getOrCreateContextMenu();
		
		// Check if this edge already has preview
		const targetNode = this.graph.getNodeById(link.target_id);
		const hasPreview = targetNode?.isPreviewNode;
		
		menu.innerHTML = `
			<div class="sg-context-menu-title">Edge Options</div>
			<div class="sg-context-menu-item" data-action="add-preview">
				${hasPreview ? '🔄 Move Preview Here' : '👁 Add Preview'}
			</div>
			${hasPreview ? `
			<div class="sg-context-menu-item" data-action="remove-preview">
				❌ Remove Preview
			</div>
			` : ''}
			<div class="sg-context-menu-item" data-action="delete-edge">
				🗑️ Delete Edge
			</div>
		`;
		
		// Position menu
		menu.style.left = screenX + 'px';
		menu.style.top = screenY + 'px';
		menu.style.display = 'block';
		
		// Store context for handlers
		this._contextMenuData = { link, worldX, worldY, hasPreview, targetNode };
		
		// Add click handlers
		menu.querySelectorAll('.sg-context-menu-item').forEach(item => {
			item.onclick = (e) => {
				const action = item.dataset.action;
				this._handleEdgeContextAction(action);
				this._hideContextMenu();
			};
		});
		
		// Close on click outside
		setTimeout(() => {
			document.addEventListener('click', this._hideContextMenuBound, { once: true });
		}, 0);
	}

	/**
	 * Show context menu for preview node
	 */
	_showPreviewNodeContextMenu(node, screenX, screenY) {
		const menu = this._getOrCreateContextMenu();
		
		menu.innerHTML = `
			<div class="sg-context-menu-title">Preview Node</div>
			<div class="sg-context-menu-item" data-action="expand">
				🔍 Expand Preview
			</div>
			<div class="sg-context-menu-item" data-action="remove">
				❌ Remove Preview
			</div>
			<div class="sg-context-menu-item sg-context-menu-divider"></div>
			<div class="sg-context-menu-item" data-action="type-auto">
				🔄 Auto-detect Type
			</div>
			<div class="sg-context-menu-item" data-action="type-json">
				📋 Force JSON
			</div>
			<div class="sg-context-menu-item" data-action="type-string">
				📝 Force String
			</div>
		`;
		
		// Position menu
		menu.style.left = screenX + 'px';
		menu.style.top = screenY + 'px';
		menu.style.display = 'block';
		
		// Store context
		this._contextMenuData = { previewNode: node };
		
		// Add click handlers
		menu.querySelectorAll('.sg-context-menu-item').forEach(item => {
			item.onclick = (e) => {
				const action = item.dataset.action;
				this._handlePreviewNodeContextAction(action);
				this._hideContextMenu();
			};
		});
		
		// Close on click outside
		setTimeout(() => {
			document.addEventListener('click', this._hideContextMenuBound, { once: true });
		}, 0);
	}

	/**
	 * Handle edge context menu action
	 */
	_handleEdgeContextAction(action) {
		const { link, worldX, worldY, hasPreview, targetNode } = this._contextMenuData || {};
		if (!link) return;
		
		switch (action) {
			case 'add-preview':
				if (hasPreview && targetNode) {
					// Move existing preview to new position
					targetNode.pos = [worldX - targetNode.size[0] / 2, worldY - targetNode.size[1] / 2];
				} else {
					this.insertPreviewNode(link, worldX, worldY);
				}
				break;
				
			case 'remove-preview':
				if (targetNode?.isPreviewNode) {
					this.removePreviewNode(targetNode);
				}
				break;
				
			case 'delete-edge':
				this._removeLink(link);
				break;
		}
		
		this.app.draw();
	}

	/**
	 * Handle preview node context menu action
	 */
	_handlePreviewNodeContextAction(action) {
		const { previewNode } = this._contextMenuData || {};
		if (!previewNode) return;
		
		switch (action) {
			case 'expand':
				const [sx, sy] = this.app.worldToScreen(
					previewNode.pos[0] + previewNode.size[0], 
					previewNode.pos[1]
				);
				this.previewOverlay.show(previewNode, sx, sy);
				break;
				
			case 'remove':
				this.removePreviewNode(previewNode);
				break;
				
			case 'type-auto':
				previewNode.properties.autoDetect = true;
				previewNode.previewType = previewNode._detectType(previewNode.previewData);
				break;
				
			case 'type-json':
				previewNode.properties.autoDetect = false;
				previewNode.properties.previewType = PreviewType.JSON;
				previewNode.previewType = PreviewType.JSON;
				break;
				
			case 'type-string':
				previewNode.properties.autoDetect = false;
				previewNode.properties.previewType = PreviewType.STRING;
				previewNode.previewType = PreviewType.STRING;
				break;
		}
		
		this.app.draw();
		
		// Update overlay if open
		if (this.previewOverlay.activeNode === previewNode) {
			this.previewOverlay.update();
		}
	}

	/**
	 * Get or create context menu element
	 */
	_getOrCreateContextMenu() {
		let menu = document.getElementById('sg-preview-context-menu');
		
		if (!menu) {
			menu = document.createElement('div');
			menu.id = 'sg-preview-context-menu';
			menu.className = 'sg-context-menu sg-preview-context-menu';
			document.body.appendChild(menu);
			
			// Bind hide function
			this._hideContextMenuBound = () => this._hideContextMenu();
		}
		
		return menu;
	}

	/**
	 * Hide context menu
	 */
	_hideContextMenu() {
		const menu = document.getElementById('sg-preview-context-menu');
		if (menu) {
			menu.style.display = 'none';
		}
		this._contextMenuData = null;
	}
}

// ========================================================================
// Custom Drawing for Preview Nodes
// ========================================================================

function extendDrawNodeForPreview(SchemaGraphAppClass) {
	const originalDrawNode = SchemaGraphAppClass.prototype.drawNode;
	
	SchemaGraphAppClass.prototype.drawNode = function(node, colors) {
		if (node.isPreviewNode) {
			this._drawPreviewNode(node, colors);
		} else {
			originalDrawNode.call(this, node, colors);
		}
	};

	SchemaGraphApp.prototype._drawPreviewNode = function(node, colors) {
		const style = this.drawingStyleManager.getStyle();
		const x = node.pos[0];
		const y = node.pos[1];
		const w = node.size[0];
		const h = node.size[1];
		const radius = style.nodeCornerRadius;
		const textScale = this.getTextScale();
		
		// Calculate flash intensity (0 to 1, eases out)
		let flashIntensity = 0;
		if (node._isFlashing && node._flashProgress !== undefined) {
			// Ease out curve
			const t = node._flashProgress;
			flashIntensity = 1 - (t * t);
		}
		
		// Flash colors
		const flashColor = { r: 146, g: 208, b: 80 }; // Green
		const baseColor = { r: 70, g: 162, b: 218 };  // Blue
		
		// Interpolate colors based on flash
		const currentColor = {
			r: Math.round(baseColor.r + (flashColor.r - baseColor.r) * flashIntensity),
			g: Math.round(baseColor.g + (flashColor.g - baseColor.g) * flashIntensity),
			b: Math.round(baseColor.b + (flashColor.b - baseColor.b) * flashIntensity)
		};
		const colorStr = `rgb(${currentColor.r}, ${currentColor.g}, ${currentColor.b})`;
		
		// Node shadow with flash glow
		if (style.nodeShadowBlur > 0 || flashIntensity > 0) {
			const glowIntensity = Math.max(style.nodeShadowBlur, flashIntensity * 25);
			this.ctx.shadowColor = flashIntensity > 0 
				? `rgba(${flashColor.r}, ${flashColor.g}, ${flashColor.b}, ${0.8 * flashIntensity})`
				: colors.nodeShadow;
			this.ctx.shadowBlur = glowIntensity / this.camera.scale;
			this.ctx.shadowOffsetY = flashIntensity > 0 ? 0 : style.nodeShadowOffset / this.camera.scale;
		}
		
		const isSelected = this.isNodeSelected(node);
		
		// Body with flash effect
		const bodyAlpha = 0.1 * flashIntensity;
		const gradient = this.ctx.createLinearGradient(x, y, x, y + h);
		if (flashIntensity > 0) {
			gradient.addColorStop(0, `rgba(${flashColor.r}, ${flashColor.g}, ${flashColor.b}, ${0.3 + bodyAlpha})`);
			gradient.addColorStop(1, `rgba(${flashColor.r * 0.7}, ${flashColor.g * 0.7}, ${flashColor.b * 0.7}, ${0.2 + bodyAlpha})`);
		} else {
			gradient.addColorStop(0, isSelected ? '#3a5a7a' : '#2d3d4d');
			gradient.addColorStop(1, isSelected ? '#2a4a6a' : '#1d2d3d');
		}
		this.ctx.fillStyle = gradient;
		
		this.ctx.beginPath();
		this._roundRect(x, y, w, h, radius);
		this.ctx.fill();
		
		// Border with flash
		this.ctx.strokeStyle = flashIntensity > 0 ? colorStr : (isSelected ? colors.borderHighlight : '#46a2da');
		this.ctx.lineWidth = ((isSelected ? 2 : 1.5) + flashIntensity * 1.5) / this.camera.scale;
		this.ctx.stroke();
		
		this.ctx.shadowBlur = 0;
		this.ctx.shadowOffsetY = 0;
		
		// Header with flash
		const headerGradient = this.ctx.createLinearGradient(x, y, x, y + 26);
		if (flashIntensity > 0) {
			headerGradient.addColorStop(0, colorStr);
			headerGradient.addColorStop(1, `rgb(${Math.round(currentColor.r * 0.7)}, ${Math.round(currentColor.g * 0.7)}, ${Math.round(currentColor.b * 0.7)})`);
		} else {
			headerGradient.addColorStop(0, '#46a2da');
			headerGradient.addColorStop(1, '#2a7ab8');
		}
		this.ctx.fillStyle = headerGradient;
		
		this.ctx.beginPath();
		this._roundRectTop(x, y, w, 26, radius);
		this.ctx.fill();
		
		// Title with live indicator during flash
		this.ctx.fillStyle = colors.textPrimary;
		this.ctx.font = `bold ${11 * textScale}px ${style.textFont}`;
		this.ctx.textBaseline = 'middle';
		this.ctx.textAlign = 'left';
		
		const title = flashIntensity > 0.5 ? '🔄 Preview' : '👁 Preview';
		this.ctx.fillText(title, x + 8, y + 13);
		
		// Live pulse indicator during flash
		if (flashIntensity > 0) {
			const pulseRadius = 4 + flashIntensity * 2;
			const pulseX = x + w - 20;
			const pulseY = y + 13;
			
			this.ctx.beginPath();
			this.ctx.arc(pulseX, pulseY, pulseRadius / this.camera.scale, 0, Math.PI * 2);
			this.ctx.fillStyle = `rgba(255, 255, 255, ${0.8 * flashIntensity})`;
			this.ctx.fill();
			
			// Outer ring
			this.ctx.beginPath();
			this.ctx.arc(pulseX, pulseY, (pulseRadius + 3) / this.camera.scale, 0, Math.PI * 2);
			this.ctx.strokeStyle = `rgba(255, 255, 255, ${0.4 * flashIntensity})`;
			this.ctx.lineWidth = 1 / this.camera.scale;
			this.ctx.stroke();
		}
		
		// Preview content area
		const contentY = y + 32;
		const contentH = h - 60;
		
		// Content background with flash
		if (flashIntensity > 0) {
			this.ctx.fillStyle = `rgba(${flashColor.r}, ${flashColor.g}, ${flashColor.b}, ${0.15 * flashIntensity})`;
		} else {
			this.ctx.fillStyle = 'rgba(0, 0, 0, 0.3)';
		}
		this.ctx.fillRect(x + 8, contentY, w - 16, contentH);
		
		this.ctx.strokeStyle = flashIntensity > 0 
			? `rgba(${flashColor.r}, ${flashColor.g}, ${flashColor.b}, ${0.5 * flashIntensity})`
			: 'rgba(255, 255, 255, 0.1)';
		this.ctx.lineWidth = (1 + flashIntensity) / this.camera.scale;
		this.ctx.strokeRect(x + 8, contentY, w - 16, contentH);
		
		// Preview text
		this.ctx.fillStyle = flashIntensity > 0 
			? `rgba(255, 255, 255, ${0.7 + 0.3 * flashIntensity})`
			: colors.textSecondary;
		this.ctx.font = `${9 * textScale}px 'Courier New', monospace`;
		this.ctx.textAlign = 'left';
		
		const previewText = node.getPreviewText();
		const lines = this._wrapText(previewText, w - 24, this.ctx);
		const lineHeight = 12 * textScale;
		const maxLines = Math.floor(contentH / lineHeight) - 1;
		
		for (let i = 0; i < Math.min(lines.length, maxLines); i++) {
			this.ctx.fillText(lines[i], x + 12, contentY + 12 + i * lineHeight);
		}
		
		if (lines.length > maxLines) {
			this.ctx.fillText('...', x + 12, contentY + 12 + maxLines * lineHeight);
		}
		
		// Type badge
		const typeText = node.previewType.toUpperCase();
		this.ctx.font = `bold ${8 * textScale}px ${style.textFont}`;
		const badgeWidth = this.ctx.measureText(typeText).width + 8;
		
		this.ctx.fillStyle = this._getTypeColor(node.previewType);
		this.ctx.beginPath();
		this._roundRect(x + w - badgeWidth - 8, y + 4, badgeWidth, 14, 3);
		this.ctx.fill();
		
		this.ctx.fillStyle = '#fff';
		this.ctx.textAlign = 'center';
		this.ctx.fillText(typeText, x + w - badgeWidth / 2 - 8, y + 12);
		
		// Draw slots
		const worldMouse = this.screenToWorld(this.mousePos[0], this.mousePos[1]);
		this.drawInputSlot(node, 0, x, y, w, worldMouse, colors);
		this.drawOutputSlot(node, 0, x, y, w, worldMouse, colors);
		
		// Expand hint / timestamp
		this.ctx.fillStyle = colors.textTertiary;
		this.ctx.font = `${8 * textScale}px ${style.textFont}`;
		this.ctx.textAlign = 'center';
		
		if (node._lastUpdateTime) {
			const elapsed = Math.floor((Date.now() - node._lastUpdateTime) / 1000);
			const timeStr = elapsed < 60 ? `${elapsed}s ago` : `${Math.floor(elapsed / 60)}m ago`;
			this.ctx.fillText(`Updated ${timeStr} • Dbl-click to expand`, x + w / 2, y + h - 8);
		} else {
			this.ctx.fillText('Double-click to expand', x + w / 2, y + h - 8);
		}
	};

	SchemaGraphAppClass.prototype._getTypeColor = function(type) {
		const typeColors = {
			[PreviewType.STRING]: '#4a9eff',
			[PreviewType.NUMBER]: '#ff9f4a',
			[PreviewType.BOOLEAN]: '#92d050',
			[PreviewType.JSON]: '#9370db',
			[PreviewType.LIST]: '#ff6b9d',
			[PreviewType.IMAGE]: '#00d4aa',
			[PreviewType.AUDIO]: '#ffd700',
			[PreviewType.VIDEO]: '#ff4757',
			[PreviewType.MODEL3D]: '#00bcd4',
			[PreviewType.UNKNOWN]: '#888888'
		};
		return typeColors[type] || typeColors[PreviewType.UNKNOWN];
	};
	
	SchemaGraphAppClass.prototype._roundRect = function(x, y, w, h, r) {
		this.ctx.moveTo(x + r, y);
		this.ctx.lineTo(x + w - r, y);
		this.ctx.quadraticCurveTo(x + w, y, x + w, y + r);
		this.ctx.lineTo(x + w, y + h - r);
		this.ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
		this.ctx.lineTo(x + r, y + h);
		this.ctx.quadraticCurveTo(x, y + h, x, y + h - r);
		this.ctx.lineTo(x, y + r);
		this.ctx.quadraticCurveTo(x, y, x + r, y);
		this.ctx.closePath();
	};
	
	SchemaGraphAppClass.prototype._roundRectTop = function(x, y, w, h, r) {
		this.ctx.moveTo(x + r, y);
		this.ctx.lineTo(x + w - r, y);
		this.ctx.quadraticCurveTo(x + w, y, x + w, y + r);
		this.ctx.lineTo(x + w, y + h);
		this.ctx.lineTo(x, y + h);
		this.ctx.lineTo(x, y + r);
		this.ctx.quadraticCurveTo(x, y, x + r, y);
		this.ctx.closePath();
	};
	
	SchemaGraphAppClass.prototype._wrapText = function(text, maxWidth, ctx) {
		const words = text.split(/(\s+)/);
		const lines = [];
		let currentLine = '';
		
		for (const word of words) {
			const testLine = currentLine + word;
			if (ctx.measureText(testLine).width > maxWidth && currentLine) {
				lines.push(currentLine.trim());
				currentLine = word;
			} else {
				currentLine = testLine;
			}
		}
		
		if (currentLine.trim()) {
			lines.push(currentLine.trim());
		}
		
		return lines;
	};
}

// ========================================================================
// Draw hovered edge highlight
// ========================================================================

function extendDrawLinksForPreview(SchemaGraphAppClass) {
	const originalDrawLinks = SchemaGraphAppClass.prototype.drawLinks;
	
	SchemaGraphAppClass.prototype.drawLinks = function(colors) {
		originalDrawLinks.call(this, colors);
		
		// Draw hovered link highlight
		if (this.edgePreviewManager?.hoveredLink) {
			const link = this.edgePreviewManager.hoveredLink;
			const orig = this.graph.getNodeById(link.origin_id);
			const targ = this.graph.getNodeById(link.target_id);
			
			if (orig && targ) {
				const x1 = orig.pos[0] + orig.size[0];
				const y1 = orig.pos[1] + 33 + link.origin_slot * 25;
				const x2 = targ.pos[0];
				const y2 = targ.pos[1] + 33 + link.target_slot * 25;
				
				const dx = x2 - x1;
				const controlOffset = Math.min(Math.abs(dx) * 0.5, 200);
				
				// Glow effect
				this.ctx.strokeStyle = '#46a2da';
				this.ctx.lineWidth = 6 / this.camera.scale;
				this.ctx.globalAlpha = 0.3;
				
				this.ctx.beginPath();
				this.ctx.moveTo(x1, y1);
				this.ctx.bezierCurveTo(x1 + controlOffset, y1, x2 - controlOffset, y2, x2, y2);
				this.ctx.stroke();
				
				// Highlight
				this.ctx.strokeStyle = '#82c4ec';
				this.ctx.lineWidth = 3 / this.camera.scale;
				this.ctx.globalAlpha = 1.0;
				
				this.ctx.beginPath();
				this.ctx.moveTo(x1, y1);
				this.ctx.bezierCurveTo(x1 + controlOffset, y1, x2 - controlOffset, y2, x2, y2);
				this.ctx.stroke();
				
				// Draw hint text
				const midT = 0.5;
				const mt = 1 - midT;
				const midX = mt*mt*mt*x1 + 3*mt*mt*midT*(x1+controlOffset) + 3*mt*midT*midT*(x2-controlOffset) + midT*midT*midT*x2;
				const midY = mt*mt*mt*y1 + 3*mt*mt*midT*y1 + 3*mt*midT*midT*y2 + midT*midT*midT*y2;
				
				const textScale = this.getTextScale();
				this.ctx.fillStyle = 'rgba(70, 162, 218, 0.9)';
				this.ctx.font = `bold ${10 * textScale}px Arial`;
				this.ctx.textAlign = 'center';
				this.ctx.textBaseline = 'middle';
				
				// Background for text
				const hintText = 'Alt+Click to add Preview';
				const textWidth = this.ctx.measureText(hintText).width;
				this.ctx.fillStyle = 'rgba(0, 0, 0, 0.7)';
				this.ctx.fillRect(midX - textWidth/2 - 4, midY - 8, textWidth + 8, 16);
				
				this.ctx.fillStyle = '#82c4ec';
				this.ctx.fillText(hintText, midX, midY);
			}
		}
	};
}

// ========================================================================
// Extend SchemaGraphApp with Preview API
// ========================================================================

function extendSchemaGraphAppWithPreview(SchemaGraphAppClass) {
	const originalCreateAPI = SchemaGraphAppClass.prototype._createAPI;
	
	SchemaGraphAppClass.prototype._createAPI = function() {
		const api = originalCreateAPI.call(this);
		
		api.preview = {
			/**
			 * Insert a preview node on a link
			 * @param {number} linkId - Link ID
			 * @returns {Node|null} Created preview node
			 */
			insertOnLink: (linkId) => {
				const link = this.graph.links[linkId];
				if (!link) return null;
				
				const orig = this.graph.getNodeById(link.origin_id);
				const targ = this.graph.getNodeById(link.target_id);
				if (!orig || !targ) return null;
				
				const midX = (orig.pos[0] + orig.size[0] + targ.pos[0]) / 2;
				const midY = (orig.pos[1] + targ.pos[1]) / 2;
				
				return this.edgePreviewManager.insertPreviewNode(link, midX, midY);
			},
			
			/**
			 * Remove a preview node and reconnect the original link
			 * @param {Node|string} nodeOrId - Preview node or ID
			 * @returns {boolean} Success
			 */
			remove: (nodeOrId) => {
				const node = typeof nodeOrId === 'string' 
					? this.graph.getNodeById(nodeOrId) 
					: nodeOrId;
				return this.edgePreviewManager.removePreviewNode(node);
			},
			
			/**
			 * Get all preview nodes
			 * @returns {Node[]} Array of preview nodes
			 */
			list: () => {
				return this.graph.nodes.filter(n => n.isPreviewNode);
			},
			
			/**
			 * Remove all preview nodes
			 * @returns {number} Count of removed nodes
			 */
			removeAll: () => {
				const previewNodes = this.graph.nodes.filter(n => n.isPreviewNode);
				let count = 0;
				for (const node of previewNodes) {
					if (this.edgePreviewManager.removePreviewNode(node)) count++;
				}
				return count;
			},
			
			/**
			 * Show expanded preview for a node
			 * @param {Node|string} nodeOrId - Preview node or ID
			 */
			expand: (nodeOrId) => {
				const node = typeof nodeOrId === 'string' 
					? this.graph.getNodeById(nodeOrId) 
					: nodeOrId;
				if (node?.isPreviewNode) {
					const [sx, sy] = this.worldToScreen(node.pos[0] + node.size[0], node.pos[1]);
					this.edgePreviewManager.previewOverlay.show(node, sx, sy);
				}
			},
			
			/**
			 * Hide expanded preview
			 */
			collapse: () => {
				this.edgePreviewManager.previewOverlay.hide();
			},

			/**
			 * Toggle preview on an edge (insert or remove preview node)
			 * @param {number} linkId - Link ID
			 * @returns {Node|null} Preview node if inserted, null if removed
			 */
			toggleOnLink: (linkId) => {
				const link = this.graph.links[linkId];
				if (!link) return null;

				const targetNode = this.graph.getNodeById(link.target_id);
				
				// If target is a preview node, remove it
				if (targetNode?.isPreviewNode) {
					this.edgePreviewManager.removePreviewNode(targetNode);
					return null;
				}
				
				// Otherwise insert preview
				return api.preview.insertOnLink(linkId);
			},

			/**
			 * Check if a link has preview enabled
			 * @param {number} linkId - Link ID
			 * @returns {boolean} True if preview node exists on this edge
			 */
			hasPreview: (linkId) => {
				const link = this.graph.links[linkId];
				if (!link) return false;
				
				const targetNode = this.graph.getNodeById(link.target_id);
				return targetNode?.isPreviewNode === true;
			},

			/**
			 * Get preview node for a link (if exists)
			 * @param {number} linkId - Link ID
			 * @returns {Node|null} Preview node or null
			 */
			getForLink: (linkId) => {
				const link = this.graph.links[linkId];
				if (!link) return null;
				
				const targetNode = this.graph.getNodeById(link.target_id);
				return targetNode?.isPreviewNode ? targetNode : null;
			},

			/**
			 * Set preview state on edge (used during import)
			 * @param {number} linkId - Link ID  
			 * @param {boolean} enabled - Whether preview should be enabled
			 * @returns {Node|null} Preview node if enabled, null otherwise
			 */
			setOnLink: (linkId, enabled) => {
				const hasPreview = api.preview.hasPreview(linkId);
				
				if (enabled && !hasPreview) {
					return api.preview.insertOnLink(linkId);
				} else if (!enabled && hasPreview) {
					const previewNode = api.preview.getForLink(linkId);
					if (previewNode) {
						this.edgePreviewManager.removePreviewNode(previewNode);
					}
					return null;
				}
				
				return hasPreview ? api.preview.getForLink(linkId) : null;
			},

			/**
			 * Get all edges that have preview enabled
			 * @returns {Array} Array of {linkId, previewNode} objects
			 */
			listEdgesWithPreview: () => {
				const result = [];
				
				for (const node of this.graph.nodes) {
					if (!node.isPreviewNode) continue;
					
					const inputLink = node.inputs[0]?.link;
					if (inputLink) {
						result.push({
							linkId: inputLink,
							previewNode: node
						});
					}
				}
				
				return result;
			},

			/**
			 * Insert preview node at specific position on link
			 * @param {number} linkId - Link ID
			 * @param {number} x - World X position
			 * @param {number} y - World Y position
			 * @returns {Node|null} Created preview node
			 */
			insertOnLinkAt: (linkId, x, y) => {
				const link = this.graph.links[linkId];
				if (!link) return null;
				
				return this.edgePreviewManager.insertPreviewNode(link, x, y);
			}
		};
		
		return api;
	};
	
	// Initialize preview manager after app init
	const originalInit = SchemaGraphAppClass.prototype.ui ? null : undefined;
	
	const originalSetupEventListeners = SchemaGraphAppClass.prototype.setupEventListeners;
	SchemaGraphAppClass.prototype.setupEventListeners = function() {
		originalSetupEventListeners.call(this);
		
		// Initialize preview manager
		this.edgePreviewManager = new EdgePreviewManager(this);
	};
}

// ========================================================================
// PREVIEW OVERLAY UPDATE PATCH
// Add these modifications to schemagraph-preview-ext.js PreviewOverlay
// ========================================================================

// Replace _createOverlayElement to include live indicator
PreviewOverlay.prototype._createOverlayElement = function() {
	this.overlayElement = document.createElement('div');
	this.overlayElement.id = 'sg-preview-overlay';
	this.overlayElement.className = 'sg-preview-overlay';
	this.overlayElement.innerHTML = `
		<div class="sg-preview-overlay-header">
			<span class="sg-preview-overlay-title">Preview</span>
			<span class="sg-preview-live-indicator" style="display: none;">LIVE</span>
			<div class="sg-preview-overlay-actions">
				<select class="sg-preview-type-select">
					<option value="auto">Auto</option>
					<option value="string">String</option>
					<option value="number">Number</option>
					<option value="boolean">Boolean</option>
					<option value="json">JSON</option>
					<option value="list">List</option>
					<option value="image">Image</option>
					<option value="audio">Audio</option>
					<option value="video">Video</option>
					<option value="model3d">3D Model</option>
				</select>
				<button class="sg-preview-close-btn">✕</button>
			</div>
		</div>
		<div class="sg-preview-overlay-content"></div>
		<div class="sg-preview-timestamp"></div>
	`;
	
	document.body.appendChild(this.overlayElement);
	
	// Store references
	this.liveIndicator = this.overlayElement.querySelector('.sg-preview-live-indicator');
	this.timestampElement = this.overlayElement.querySelector('.sg-preview-timestamp');
	
	// Event handlers
	this.overlayElement.querySelector('.sg-preview-close-btn')
		.addEventListener('click', () => this.hide());
	
	this.overlayElement.querySelector('.sg-preview-type-select')
		.addEventListener('change', (e) => this._onTypeChange(e.target.value));
};

// Enhanced update method with timestamp
PreviewOverlay.prototype.update = function() {
	if (!this.activeNode || !this.overlayElement.classList.contains('show')) return;
	
	const content = this.overlayElement.querySelector('.sg-preview-overlay-content');
	this._renderContent(content, this.activeNode);
	
	// Update timestamp
	this._updateTimestamp();
	
	// Show live indicator briefly
	this._showLiveIndicator();
};

// Show live indicator with auto-hide
PreviewOverlay.prototype._showLiveIndicator = function() {
	if (!this.liveIndicator) return;
	
	this.liveIndicator.style.display = 'inline-flex';
	
	// Clear existing timeout
	if (this._liveIndicatorTimeout) {
		clearTimeout(this._liveIndicatorTimeout);
	}
	
	// Hide after 3 seconds of no updates
	this._liveIndicatorTimeout = setTimeout(() => {
		if (this.liveIndicator) {
			this.liveIndicator.style.display = 'none';
		}
	}, 3000);
};

// Update timestamp display
PreviewOverlay.prototype._updateTimestamp = function() {
	if (!this.timestampElement || !this.activeNode) return;
	
	const lastUpdate = this.activeNode._lastUpdateTime;
	if (!lastUpdate) {
		this.timestampElement.textContent = '';
		return;
	}
	
	const now = Date.now();
	const elapsed = Math.floor((now - lastUpdate) / 1000);
	
	let timeStr;
	if (elapsed < 1) {
		timeStr = 'just now';
	} else if (elapsed < 60) {
		timeStr = `${elapsed} second${elapsed !== 1 ? 's' : ''} ago`;
	} else if (elapsed < 3600) {
		const mins = Math.floor(elapsed / 60);
		timeStr = `${mins} minute${mins !== 1 ? 's' : ''} ago`;
	} else {
		const hours = Math.floor(elapsed / 3600);
		timeStr = `${hours} hour${hours !== 1 ? 's' : ''} ago`;
	}
	
	this.timestampElement.textContent = `Last updated: ${timeStr}`;
	
	// Auto-refresh timestamp every second while visible
	if (!this._timestampInterval && this.overlayElement.classList.contains('show')) {
		this._timestampInterval = setInterval(() => this._updateTimestamp(), 1000);
	}
};

// Clean up on hide
const originalHide = PreviewOverlay.prototype.hide;
PreviewOverlay.prototype.hide = function() {
	// Clear intervals
	if (this._liveIndicatorTimeout) {
		clearTimeout(this._liveIndicatorTimeout);
		this._liveIndicatorTimeout = null;
	}
	if (this._timestampInterval) {
		clearInterval(this._timestampInterval);
		this._timestampInterval = null;
	}
	
	// Call original
	originalHide.call(this);
};

// Enhanced show method
const originalShow = PreviewOverlay.prototype.show;
PreviewOverlay.prototype.show = function(node, screenX, screenY) {
	originalShow.call(this, node, screenX, screenY);
	
	// Initialize timestamp updating
	this._updateTimestamp();
};

// ========================================================================
// AUTO-INITIALIZATION
// ========================================================================

if (typeof SchemaGraphApp !== 'undefined') {
	extendDrawNodeForPreview(SchemaGraphApp);
	extendDrawLinksForPreview(SchemaGraphApp);
	extendSchemaGraphAppWithPreview(SchemaGraphApp);
}

if (typeof module !== 'undefined' && module.exports) {
	module.exports = {
		PreviewType,
		PreviewNode,
		PreviewOverlay,
		EdgePreviewManager,
		extendDrawNodeForPreview,
		extendDrawLinksForPreview,
		extendSchemaGraphAppWithPreview
	};
}
