// ========================================================================
// SCHEMAGRAPH PREVIEW EXTENSION
// Adds ability to click on edges and insert preview nodes to inspect
// data flowing through connections. Supports native types and media.
// ========================================================================

const PreviewType = Object.freeze({
	AUTO: 'auto', STRING: 'string', NUMBER: 'number', BOOLEAN: 'boolean',
	JSON: 'json', LIST: 'list', IMAGE: 'image', AUDIO: 'audio',
	VIDEO: 'video', MODEL3D: 'model3d', UNKNOWN: 'unknown'
});

// ========================================================================
// PreviewNode Class
// ========================================================================

class PreviewNode extends Node {
	constructor() {
		super('Preview');
		this.isPreviewNode = true;
		this.previewType = PreviewType.AUTO;
		this.previewData = null;
		this.previewError = null;
		this.isExpanded = false;
		
		this.addInput('in', 'Any');
		this.addOutput('out', 'Any');
		
		this.size = [200, 110];
		this.minSize = [180, 100];
		this.maxSize = [400, 500];
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
		this.previewType = this.properties.autoDetect 
			? this._detectType(inputData) 
			: this.properties.previewType;
		this.setOutputData(0, inputData);
	}

	_detectType(data) {
		if (data === null || data === undefined) return PreviewType.STRING;
		
		if (typeof data === 'string') {
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
			if (data.type === 'image' || data.mimeType?.startsWith('image/')) return PreviewType.IMAGE;
			if (data.type === 'audio' || data.mimeType?.startsWith('audio/')) return PreviewType.AUDIO;
			if (data.type === 'video' || data.mimeType?.startsWith('video/')) return PreviewType.VIDEO;
			if (data.type === 'model3d' || data.mimeType?.includes('model')) return PreviewType.MODEL3D;
			return PreviewType.JSON;
		}
		
		return PreviewType.UNKNOWN;
	}

	_isImageData(str) {
		return str?.toLowerCase().startsWith('data:image/') || 
			/\.(jpg|jpeg|png|gif|webp|svg|bmp|ico)(\?|$)/i.test(str);
	}

	_isAudioData(str) {
		return str?.toLowerCase().startsWith('data:audio/') || 
			/\.(mp3|wav|ogg|m4a|flac|aac)(\?|$)/i.test(str);
	}

	_isVideoData(str) {
		return str?.toLowerCase().startsWith('data:video/') || 
			/\.(mp4|webm|ogg|mov|avi|mkv)(\?|$)/i.test(str);
	}

	_is3DModelData(str) {
		return /\.(glb|gltf|obj|fbx|stl|3ds)(\?|$)/i.test(str);
	}

	getPreviewText() {
		if (this.previewError) return `Error: ${this.previewError}`;
		if (this.previewData === null) return 'null';
		if (this.previewData === undefined) return 'undefined';
		
		switch (this.previewType) {
			case PreviewType.STRING: {
				const str = String(this.previewData);
				return str.length > this.properties.maxStringLength 
					? str.substring(0, this.properties.maxStringLength) + '...' : str;
			}
			case PreviewType.NUMBER:
			case PreviewType.BOOLEAN:
				return String(this.previewData);
			case PreviewType.LIST: {
				const arr = this.previewData;
				const max = this.properties.maxArrayItems;
				return JSON.stringify(arr.slice(0, max), null, 2) + (arr.length > max ? '\n...' : '');
			}
			case PreviewType.JSON:
				try {
					const json = JSON.stringify(this.previewData, null, 2);
					return json.length > this.properties.maxStringLength 
						? json.substring(0, this.properties.maxStringLength) + '...' : json;
				} catch { return '[Object]'; }
			case PreviewType.IMAGE: return '🖼️ Image';
			case PreviewType.AUDIO: return '🔊 Audio';
			case PreviewType.VIDEO: return '🎬 Video';
			case PreviewType.MODEL3D: return '🧊 3D Model';
			default: return String(this.previewData);
		}
	}

	getMediaSource() {
		if (!this.previewData) return null;
		if (typeof this.previewData === 'string') return this.previewData;
		if (typeof this.previewData === 'object') {
			return this.previewData.url || this.previewData.src || this.previewData.data;
		}
		return null;
	}
}

// ========================================================================
// Preview Extension Class
// ========================================================================

class PreviewExtension extends SchemaGraphExtension {
	constructor(app) {
		super(app);
		this.hoveredLink = null;
		this.linkHitDistance = 10;
		this._contextMenuData = null;
	}

	_registerNodeTypes() {
		this.graph.nodeTypes['Native.Preview'] = PreviewNode;
	}

	_setupEventListeners() {
		this.on('mouse:move', (data) => this._onMouseMove(data));
		this.on('mouse:down', (data) => this._onMouseDown(data));
		this.on('mouse:dblclick', (data) => this._onDoubleClick(data));
		this.on('contextmenu', (data) => this._onContextMenu(data));
		this.onDOM(document, 'keydown', (e) => this._onKeyDown(e));
	}

	_extendAPI() {
		const self = this;
		
		this.app.api = this.app.api || {};
		this.app.api.preview = {
			list: () => self.graph.nodes.filter(n => n.isPreviewNode),
			expand: (nodeOrId) => {
				const node = typeof nodeOrId === 'object' ? nodeOrId : self.graph.getNodeById(nodeOrId);
				if (node?.isPreviewNode) self._setExpanded(node, true);
			},
			collapse: (nodeOrId) => {
				const node = typeof nodeOrId === 'object' ? nodeOrId : self.graph.getNodeById(nodeOrId);
				if (node?.isPreviewNode) self._setExpanded(node, false);
			},
			canInsertOnLink: (linkId) => self._canInsertPreview(self.graph.links[linkId]),
			insertOnLink: (linkId) => {
				const link = self.graph.links[linkId];
				if (!link) return null;
				const src = self.graph.getNodeById(link.origin_id);
				const tgt = self.graph.getNodeById(link.target_id);
				if (!src || !tgt) return null;
				const midX = (src.pos[0] + src.size[0] + tgt.pos[0]) / 2;
				const midY = (src.pos[1] + tgt.pos[1]) / 2;
				return self.insertPreviewNode(link, midX, midY);
			},
			remove: (nodeOrId) => {
				const node = typeof nodeOrId === 'object' ? nodeOrId : self.graph.getNodeById(nodeOrId);
				return node?.isPreviewNode ? self.removePreviewNode(node) : null;
			},
			removeAll: () => {
				let count = 0;
				for (const n of [...self.graph.nodes]) {
					if (n.isPreviewNode && self.removePreviewNode(n)) count++;
				}
				return count;
			},
			getOriginalEdgeInfo: (nodeOrId) => {
				const node = typeof nodeOrId === 'object' ? nodeOrId : self.graph.getNodeById(nodeOrId);
				return node?.isPreviewNode ? node._originalEdgeInfo : null;
			}
		};
		
		this.app.edgePreviewManager = this;
	}

	_injectStyles() {
		if (document.getElementById('sg-preview-styles')) return;
		const style = document.createElement('style');
		style.id = 'sg-preview-styles';
		style.textContent = `
			.sg-preview-context-menu { min-width: 180px; }
			.sg-preview-context-menu .sg-context-menu-divider {
				height: 1px; background: var(--sg-border-color, #1a1a1a); margin: 4px 0;
			}
		`;
		document.head.appendChild(style);
	}

	// --- Event Handlers ---

	_onMouseMove(data) {
		if (this.app.connecting || this.app.dragNode || this.app.isPanning || this.app.isLocked) {
			this.hoveredLink = null;
			return;
		}
		
		const [wx, wy] = this.app.screenToWorld(data.coords.screenX, data.coords.screenY);
		const link = this._findLinkAtPosition(wx, wy);
		
		if (link && this._canInsertPreview(link).allowed) {
			this.hoveredLink = link;
			this.app.canvas.style.cursor = 'pointer';
		} else {
			this.hoveredLink = null;
		}
	}

	_onMouseDown(data) {
		if (data.button !== 0 || this.app.connecting || this.app.dragNode || this.app.isLocked) return;
		
		const [wx, wy] = this.app.screenToWorld(data.coords.screenX, data.coords.screenY);
		const link = this._findLinkAtPosition(wx, wy);
		
		if (link && data.event.altKey && this._canInsertPreview(link).allowed) {
			data.event.preventDefault();
			data.event.stopPropagation();
			this.insertPreviewNode(link, wx, wy);
			return true;
		}
	}

	_onDoubleClick(data) {
		const [wx, wy] = this.app.screenToWorld(data.coords.screenX, data.coords.screenY);
		
		for (const node of this.graph.nodes) {
			if (!node.isPreviewNode) continue;
			if (wx >= node.pos[0] && wx <= node.pos[0] + node.size[0] &&
				wy >= node.pos[1] && wy <= node.pos[1] + node.size[1]) {
				this._setExpanded(node, !node.isExpanded);
				return;
			}
		}
	}

	_onContextMenu(data) {
		if (this.app.isLocked) return;
		
		const [wx, wy] = this.app.screenToWorld(data.coords.screenX, data.coords.screenY);
		
		for (const node of this.graph.nodes) {
			if (!node.isPreviewNode) continue;
			if (wx >= node.pos[0] && wx <= node.pos[0] + node.size[0] &&
				wy >= node.pos[1] && wy <= node.pos[1] + node.size[1]) {
				data.event.preventDefault();
				this._showPreviewNodeContextMenu(node, data.coords.screenX, data.coords.screenY);
				return true;
			}
		}
		
		const link = this._findLinkAtPosition(wx, wy);
		if (link) {
			data.event.preventDefault();
			this._showEdgeContextMenu(link, data.coords.screenX, data.coords.screenY, wx, wy);
			return true;
		}
	}

	_onKeyDown(e) {
		if (this.app.isLocked) return;
		
		if (e.key === 'Delete' || e.key === 'Backspace') {
			const selected = Array.from(this.app.selectedNodes || []);
			const previews = selected.filter(n => n.isPreviewNode);
			if (previews.length > 0) {
				e.preventDefault();
				e.stopPropagation();
				for (const node of previews) this.removePreviewNode(node);
				this.app.selectedNodes = new Set(selected.filter(n => !n.isPreviewNode));
			}
		}
	}

	// --- Core Logic ---

	_canInsertPreview(link) {
		if (!link) return { allowed: false, reason: 'Invalid link' };
		const src = this.graph.getNodeById(link.origin_id);
		const tgt = this.graph.getNodeById(link.target_id);
		if (!src || !tgt) return { allowed: false, reason: 'Invalid source or target node' };
		if (src.isPreviewNode) return { allowed: false, reason: 'Source is already a preview node' };
		if (tgt.isPreviewNode) return { allowed: false, reason: 'Target is already a preview node' };
		return { allowed: true, reason: null };
	}

	insertPreviewNode(link, wx, wy) {
		if (this.app.isLocked) return null;
		
		const check = this._canInsertPreview(link);
		if (!check.allowed) {
			console.warn(`Cannot insert preview: ${check.reason}`);
			return null;
		}

		const src = this.graph.getNodeById(link.origin_id);
		const tgt = this.graph.getNodeById(link.target_id);

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
			extra: link.extra ? JSON.parse(JSON.stringify(link.extra)) : null,
		};

		// Create preview node
		const preview = new PreviewNode();
		preview.pos = [wx - preview.size[0] / 2, wy - preview.size[1] / 2];
		preview._originalEdgeInfo = originalEdgeInfo;

		// Use proper API - emits node:created
		this.graph.addNode(preview);

		// Remove original link using proper API - emits link:removed
		this.graph.removeLink(link.id);

		// Create source -> preview link using proper API - emits link:created
		const link1 = this.graph.addLink(src.id, originalEdgeInfo.sourceSlotIdx, preview.id, 0, originalEdgeInfo.linkType);
		if (link1) link1.extra = { _isPreviewLink: true };

		// Create preview -> target link using proper API - emits link:created
		const link2 = this.graph.addLink(preview.id, 0, tgt.id, originalEdgeInfo.targetSlotIdx, originalEdgeInfo.linkType);
		if (link2) link2.extra = { _isPreviewLink: true };

		preview.onExecute();
		this.eventBus.emit('preview:inserted', { nodeId: preview.id, originalEdgeInfo });
		this.app.draw();
		return preview;
	}

	removePreviewNode(node) {
		if (this.app.isLocked || !node?.isPreviewNode) return null;

		const originalEdgeInfo = node._originalEdgeInfo;
		const inLinkId = node.inputs[0]?.link;
		const outLinkIds = node.outputs[0]?.links || [];

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
					// Use proper API - emits link:created
					const newLink = this.graph.addLink(src.id, srcSlot, tgt.id, tgtSlot, originalEdgeInfo?.linkType || inLink.type);

					if (newLink) {
						if (originalEdgeInfo?.data) {
							newLink.data = JSON.parse(JSON.stringify(originalEdgeInfo.data));
						}
						if (originalEdgeInfo?.extra) {
							const restoredExtra = JSON.parse(JSON.stringify(originalEdgeInfo.extra));
							delete restoredExtra._isPreviewLink;
							if (Object.keys(restoredExtra).length > 0) newLink.extra = restoredExtra;
						}
						restoredLink = newLink;
					}
				}
			}
		}

		// Remove preview links using proper API - emits link:removed
		if (inLinkId) this.graph.removeLink(inLinkId);
		for (const id of outLinkIds) this.graph.removeLink(id);

		// Remove preview node using proper API - emits node:removed
		this.graph.removeNode(node);

		this.eventBus.emit('preview:removed', { nodeId: node.id, restoredLinkId: restoredLink?.id, originalEdgeInfo });
		this.app.draw();
		return restoredLink;
	}

	// --- Helpers ---

	_setExpanded(node, expanded) {
		node.isExpanded = expanded;
		if (expanded) {
			node._collapsedSize = [...node.size];
			node.size = [280, 200];
		} else {
			node.size = node._collapsedSize || [200, 110];
		}
		this.app.draw();
	}

	_findLinkAtPosition(wx, wy) {
		const threshold = this.linkHitDistance / this.app.camera.scale;
		
		for (const linkId in this.graph.links) {
			const link = this.graph.links[linkId];
			const src = this.graph.getNodeById(link.origin_id);
			const tgt = this.graph.getNodeById(link.target_id);
			if (!src || !tgt) continue;
			
			const x1 = src.pos[0] + src.size[0];
			const y1 = src.pos[1] + 33 + link.origin_slot * 25;
			const x2 = tgt.pos[0];
			const y2 = tgt.pos[1] + 33 + link.target_slot * 25;
			
			if (this._pointNearBezier(wx, wy, x1, y1, x2, y2, threshold)) return link;
		}
		return null;
	}

	_pointNearBezier(px, py, x1, y1, x2, y2, threshold) {
		const dx = x2 - x1;
		const controlOffset = Math.min(Math.abs(dx) * 0.5, 200);
		const cx1 = x1 + controlOffset, cx2 = x2 - controlOffset;
		
		for (let i = 0; i <= 20; i++) {
			const t = i / 20;
			const mt = 1 - t;
			const bx = mt**3*x1 + 3*mt**2*t*cx1 + 3*mt*t**2*cx2 + t**3*x2;
			const by = mt**3*y1 + 3*mt**2*t*y1 + 3*mt*t**2*y2 + t**3*y2;
			if (Math.sqrt((px - bx)**2 + (py - by)**2) < threshold) return true;
		}
		return false;
	}

	// --- Context Menus ---

	_showEdgeContextMenu(link, screenX, screenY, worldX, worldY) {
		const menu = this._getOrCreateContextMenu();
		const tgt = this.graph.getNodeById(link.target_id);
		const hasPreview = tgt?.isPreviewNode;
		
		menu.innerHTML = `
			<div class="sg-context-menu-title">Edge Options</div>
			<div class="sg-context-menu-item" data-action="add-preview">
				${hasPreview ? '🔄 Move Preview Here' : '👁 Add Preview'}
			</div>
			${hasPreview ? '<div class="sg-context-menu-item" data-action="remove-preview">❌ Remove Preview</div>' : ''}
			<div class="sg-context-menu-item" data-action="delete-edge">🗑️ Delete Edge</div>
		`;
		
		this._showMenu(menu, screenX, screenY);
		this._contextMenuData = { link, worldX, worldY, hasPreview, targetNode: tgt };
		
		menu.querySelectorAll('.sg-context-menu-item').forEach(item => {
			item.onclick = () => {
				this._handleEdgeContextAction(item.dataset.action);
				this._hideContextMenu();
			};
		});
	}

	_showPreviewNodeContextMenu(node, screenX, screenY) {
		const menu = this._getOrCreateContextMenu();
		
		menu.innerHTML = `
			<div class="sg-context-menu-title">Preview Node</div>
			<div class="sg-context-menu-item" data-action="toggle-expand">
				${node.isExpanded ? '🔽 Collapse' : '🔼 Expand'}
			</div>
			<div class="sg-context-menu-item" data-action="remove">❌ Remove Preview</div>
			<div class="sg-context-menu-divider"></div>
			<div class="sg-context-menu-item" data-action="type-auto">🔄 Auto-detect Type</div>
			<div class="sg-context-menu-item" data-action="type-json">📋 Force JSON</div>
			<div class="sg-context-menu-item" data-action="type-string">📝 Force String</div>
		`;
		
		this._showMenu(menu, screenX, screenY);
		this._contextMenuData = { previewNode: node };
		
		menu.querySelectorAll('.sg-context-menu-item').forEach(item => {
			item.onclick = () => {
				this._handlePreviewNodeContextAction(item.dataset.action);
				this._hideContextMenu();
			};
		});
	}

	_handleEdgeContextAction(action) {
		const { link, worldX, worldY, hasPreview, targetNode } = this._contextMenuData || {};
		if (!link) return;
		
		switch (action) {
			case 'add-preview':
				if (hasPreview && targetNode) {
					targetNode.pos = [worldX - targetNode.size[0] / 2, worldY - targetNode.size[1] / 2];
				} else {
					this.insertPreviewNode(link, worldX, worldY);
				}
				break;
			case 'remove-preview':
				if (targetNode?.isPreviewNode) this.removePreviewNode(targetNode);
				break;
			case 'delete-edge':
				this.graph.removeLink(link.id);
				break;
		}
		this.app.draw();
	}

	_handlePreviewNodeContextAction(action) {
		const { previewNode } = this._contextMenuData || {};
		if (!previewNode) return;
		
		switch (action) {
			case 'toggle-expand':
				this._setExpanded(previewNode, !previewNode.isExpanded);
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
	}

	_getOrCreateContextMenu() {
		let menu = document.getElementById('sg-preview-context-menu');
		if (!menu) {
			menu = document.createElement('div');
			menu.id = 'sg-preview-context-menu';
			menu.className = 'sg-context-menu sg-preview-context-menu';
			document.body.appendChild(menu);
		}
		return menu;
	}

	_showMenu(menu, x, y) {
		menu.style.left = x + 'px';
		menu.style.top = y + 'px';
		menu.style.display = 'block';
		setTimeout(() => {
			document.addEventListener('click', () => this._hideContextMenu(), { once: true });
		}, 0);
	}

	_hideContextMenu() {
		const menu = document.getElementById('sg-preview-context-menu');
		if (menu) menu.style.display = 'none';
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

	SchemaGraphAppClass.prototype._drawPreviewNode = function(node, colors) {
		const style = this.drawingStyleManager.getStyle();
		const x = node.pos[0], y = node.pos[1];
		const w = node.size[0], h = node.size[1];
		const radius = style.nodeCornerRadius;
		const textScale = this.getTextScale();
		const isSelected = this.isNodeSelected(node);
		
		let flashIntensity = 0;
		if (node._isFlashing && node._flashProgress !== undefined) {
			flashIntensity = 1 - (node._flashProgress * node._flashProgress);
		}
		
		const flashColor = { r: 146, g: 208, b: 80 };
		const baseColor = { r: 70, g: 162, b: 218 };
		const currentColor = {
			r: Math.round(baseColor.r + (flashColor.r - baseColor.r) * flashIntensity),
			g: Math.round(baseColor.g + (flashColor.g - baseColor.g) * flashIntensity),
			b: Math.round(baseColor.b + (flashColor.b - baseColor.b) * flashIntensity)
		};
		const colorStr = `rgb(${currentColor.r}, ${currentColor.g}, ${currentColor.b})`;
		
		if (style.nodeShadowBlur > 0 || flashIntensity > 0) {
			this.ctx.shadowColor = flashIntensity > 0 
				? `rgba(${flashColor.r}, ${flashColor.g}, ${flashColor.b}, ${0.8 * flashIntensity})`
				: colors.nodeShadow;
			this.ctx.shadowBlur = Math.max(style.nodeShadowBlur, flashIntensity * 25) / this.camera.scale;
			this.ctx.shadowOffsetY = flashIntensity > 0 ? 0 : style.nodeShadowOffset / this.camera.scale;
		}
		
		const gradient = this.ctx.createLinearGradient(x, y, x, y + h);
		gradient.addColorStop(0, isSelected ? '#3a5a7a' : '#2d3d4d');
		gradient.addColorStop(1, isSelected ? '#2a4a6a' : '#1d2d3d');
		this.ctx.fillStyle = gradient;
		
		this.ctx.beginPath();
		this._drawRoundRect(x, y, w, h, radius);
		this.ctx.fill();
		
		this.ctx.strokeStyle = flashIntensity > 0 ? colorStr : (isSelected ? colors.borderHighlight : '#46a2da');
		this.ctx.lineWidth = ((isSelected ? 2 : 1.5) + flashIntensity * 1.5) / this.camera.scale;
		this.ctx.stroke();
		
		this.ctx.shadowBlur = 0;
		this.ctx.shadowOffsetY = 0;
		
		const headerH = 26;
		const headerGradient = this.ctx.createLinearGradient(x, y, x, y + headerH);
		headerGradient.addColorStop(0, flashIntensity > 0 ? colorStr : '#46a2da');
		headerGradient.addColorStop(1, flashIntensity > 0 
			? `rgb(${Math.round(currentColor.r * 0.7)}, ${Math.round(currentColor.g * 0.7)}, ${Math.round(currentColor.b * 0.7)})`
			: '#2a7ab8');
		this.ctx.fillStyle = headerGradient;
		
		this.ctx.beginPath();
		this._drawRoundRectTop(x, y, w, headerH, radius);
		this.ctx.fill();
		
		this.ctx.fillStyle = colors.textPrimary;
		this.ctx.font = `bold ${11 * textScale}px ${style.textFont}`;
		this.ctx.textBaseline = 'middle';
		this.ctx.textAlign = 'left';
		this.ctx.fillText('Preview 👁', x + 8, y + 13);
		
		const typeText = node.previewType.toUpperCase();
		this.ctx.font = `bold ${8 * textScale}px ${style.textFont}`;
		const badgeWidth = this.ctx.measureText(typeText).width + 8;
		
		this.ctx.fillStyle = this._getPreviewTypeColor(node.previewType);
		this.ctx.beginPath();
		this._drawRoundRect(x + w - badgeWidth - 8, y + 6, badgeWidth, 14, 3);
		this.ctx.fill();
		
		this.ctx.fillStyle = '#fff';
		this.ctx.textAlign = 'center';
		this.ctx.fillText(typeText, x + w - badgeWidth / 2 - 8, y + 13);
		
		const worldMouse = this.screenToWorld(this.mousePos[0], this.mousePos[1]);
		this.drawInputSlot(node, 0, x, y, w, worldMouse, colors);
		this.drawOutputSlot(node, 0, x, y, w, worldMouse, colors);
		
		const contentY = node.isExpanded ? y + 65 : y + 55;
		const contentH = node.isExpanded ? h - 85 : h - 75;
		
		if (node.isExpanded) {
			this._drawPreviewExpanded(node, x + 8, contentY, w - 16, contentH, colors, textScale, style);
		} else {
			this._drawPreviewCollapsed(node, x + 8, contentY, w - 16, contentH, colors, textScale, style);
		}
		
		this.ctx.fillStyle = colors.textTertiary;
		this.ctx.font = `${8 * textScale}px ${style.textFont}`;
		this.ctx.textAlign = 'center';
		this.ctx.fillText(node.isExpanded ? 'Dbl-click to collapse' : 'Dbl-click to expand', x + w / 2, y + h - 8);
	};

	SchemaGraphAppClass.prototype._drawPreviewCollapsed = function(node, x, y, w, h, colors, textScale, style) {
		const data = node.previewData;
		const type = node.previewType;

		if (data && typeof data === 'object' && data.type && data.sourceType) {
			const summary = data.meta?.filename || `${data.type} data`;
			if (typeof MediaPreviewRenderer !== 'undefined') {
				MediaPreviewRenderer.drawCollapsedPreview(this.ctx, data.type, summary, x, y, w, h, 
					{ textScale, font: style.textFont, colors });
			}
			return;
		}

		const summary = this._getPreviewSummary(node);
		if (typeof MediaPreviewRenderer !== 'undefined') {
			MediaPreviewRenderer.drawCollapsedPreview(this.ctx, type, summary, x, y, w, h,
				{ textScale, font: style.textFont, colors });
		} else {
			this.ctx.fillStyle = colors.textSecondary;
			this.ctx.font = `${10 * textScale}px ${style.textFont}`;
			this.ctx.textAlign = 'center';
			this.ctx.textBaseline = 'middle';
			this.ctx.fillText(summary.substring(0, 40), x + w / 2, y + h / 2);
		}
	};

	SchemaGraphAppClass.prototype._drawPreviewExpanded = function(node, x, y, w, h, colors, textScale, style) {
		const padding = 6;
		const innerX = x + padding, innerY = y + padding;
		const innerW = w - padding * 2, innerH = h - padding * 2;

		if (typeof MediaPreviewRenderer !== 'undefined') {
			MediaPreviewRenderer.drawExpandedBackground(this.ctx, x, y, w, h, { scale: this.camera.scale });
		}

		this.ctx.save();
		this.ctx.beginPath();
		this.ctx.roundRect(innerX, innerY, innerW, innerH, 4);
		this.ctx.clip();

		const data = node.previewData;
		const type = node.previewType;
		const opts = { textScale, font: style.textFont, colors, onLoad: () => this.draw() };

		if (data && typeof data === 'object' && data.type && data.sourceType) {
			this._drawDataPreviewContent(data, innerX, innerY, innerW, innerH, opts);
			this.ctx.restore();
			return;
		}

		if (typeof MediaPreviewRenderer !== 'undefined') {
			switch (type) {
				case PreviewType.BOOLEAN:
					MediaPreviewRenderer.drawBooleanPreview(this.ctx, data, innerX, innerY, innerW, innerH, opts);
					break;
				case PreviewType.NUMBER:
					MediaPreviewRenderer.drawNumberPreview(this.ctx, data, innerX, innerY, innerW, innerH, opts);
					break;
				case PreviewType.IMAGE:
					const imgSrc = node.getMediaSource();
					if (imgSrc) MediaPreviewRenderer.drawCachedImage(this.ctx, imgSrc, innerX, innerY, innerW, innerH, { ...opts, contain: true });
					else MediaPreviewRenderer.drawMediaPlaceholder(this.ctx, 'image', innerX, innerY, innerW, innerH, opts);
					break;
				case PreviewType.AUDIO:
				case PreviewType.VIDEO:
				case PreviewType.MODEL3D:
					MediaPreviewRenderer.drawMediaPlaceholder(this.ctx, type, innerX, innerY, innerW, innerH, opts);
					break;
				default:
					MediaPreviewRenderer.drawTextPreview(this.ctx, node.getPreviewText(), innerX, innerY, innerW, innerH, opts);
			}
		}

		this.ctx.restore();
	};

	SchemaGraphAppClass.prototype._drawDataPreviewContent = function(data, x, y, w, h, opts) {
		const src = data.data || data.url;
		if (typeof MediaPreviewRenderer === 'undefined') return;

		switch (data.type) {
			case 'image':
				if (src) MediaPreviewRenderer.drawCachedImage(this.ctx, src, x, y, w, h, { ...opts, contain: true });
				else MediaPreviewRenderer.drawMediaPlaceholder(this.ctx, 'image', x, y, w, h, opts);
				break;
			case 'video':
				if (src) MediaPreviewRenderer.drawCachedVideoFrame(this.ctx, src, x, y, w, h, opts);
				else MediaPreviewRenderer.drawMediaPlaceholder(this.ctx, 'video', x, y, w, h, opts);
				break;
			case 'text':
				MediaPreviewRenderer.drawTextPreview(this.ctx, data.data || '', x, y, w, h, opts);
				break;
			default:
				MediaPreviewRenderer.drawDetailedInfoPreview(this.ctx, data.type, {
					filename: data.meta?.filename, size: data.meta?.size, mimeType: data.meta?.mimeType
				}, x, y, w, h, opts);
		}
	};

	SchemaGraphAppClass.prototype._getPreviewTypeColor = function(type) {
		if (typeof MediaPreviewRenderer !== 'undefined') return MediaPreviewRenderer.getTypeColor(type);
		const colors = { string: '#4a9eff', number: '#ff9f4a', boolean: '#92d050', json: '#9370db', list: '#ff6b9d' };
		return colors[type] || '#888888';
	};

	SchemaGraphAppClass.prototype._getPreviewSummary = function(node) {
		const data = node.previewData;
		if (data === null) return 'null';
		if (data === undefined) return 'undefined';
		
		switch (node.previewType) {
			case PreviewType.STRING: return `"${String(data)}"`;
			case PreviewType.NUMBER: return String(data);
			case PreviewType.BOOLEAN: return data ? 'true' : 'false';
			case PreviewType.LIST: return `Array (${data.length} items)`;
			case PreviewType.JSON: return `Object (${Object.keys(data).length} keys)`;
			case PreviewType.IMAGE: return 'Image';
			case PreviewType.AUDIO: return 'Audio';
			case PreviewType.VIDEO: return 'Video';
			case PreviewType.MODEL3D: return '3D Model';
			default: return String(data).slice(0, 50);
		}
	};
}

// ========================================================================
// Draw Edge Highlight for Hover
// ========================================================================

function extendDrawLinksForPreview(SchemaGraphAppClass) {
	const originalDrawLinks = SchemaGraphAppClass.prototype.drawLinks;
	
	SchemaGraphAppClass.prototype.drawLinks = function(colors) {
		originalDrawLinks.call(this, colors);
		
		this._pendingPreviewHint = null;
		
		if (!this.edgePreviewManager?.hoveredLink) return;
		
		const link = this.edgePreviewManager.hoveredLink;
		const src = this.graph.getNodeById(link.origin_id);
		const tgt = this.graph.getNodeById(link.target_id);
		if (!src || !tgt) return;
		
		const style = this.drawingStyleManager.getStyle();
		const x1 = src.pos[0] + src.size[0];
		const y1 = src.pos[1] + 33 + link.origin_slot * 25;
		const x2 = tgt.pos[0];
		const y2 = tgt.pos[1] + 33 + link.target_slot * 25;
		
		const distance = Math.abs(x2 - x1);
		const controlOffset = Math.min(distance * style.linkCurve, 400);
		const cx1 = x1 + controlOffset, cx2 = x2 - controlOffset;
		
		this.ctx.strokeStyle = '#46a2da';
		this.ctx.lineWidth = (style.linkWidth + 4) / this.camera.scale;
		this.ctx.globalAlpha = 0.3;
		
		if (style.useGlow) {
			this.ctx.shadowColor = '#46a2da';
			this.ctx.shadowBlur = 10 / this.camera.scale;
		}
		
		this.ctx.beginPath();
		if (style.linkCurve > 0) {
			this.ctx.moveTo(x1, y1);
			this.ctx.bezierCurveTo(cx1, y1, cx2, y2, x2, y2);
		} else {
			this.ctx.moveTo(x1, y1);
			this.ctx.lineTo(x2, y2);
		}
		this.ctx.stroke();
		
		this.ctx.strokeStyle = '#82c4ec';
		this.ctx.lineWidth = (style.linkWidth + 1) / this.camera.scale;
		this.ctx.globalAlpha = 1.0;
		this.ctx.shadowBlur = 0;
		
		if (style.useDashed) {
			this.ctx.setLineDash([8 / this.camera.scale, 4 / this.camera.scale]);
		}
		
		this.ctx.beginPath();
		if (style.linkCurve > 0) {
			this.ctx.moveTo(x1, y1);
			this.ctx.bezierCurveTo(cx1, y1, cx2, y2, x2, y2);
		} else {
			this.ctx.moveTo(x1, y1);
			this.ctx.lineTo(x2, y2);
		}
		this.ctx.stroke();
		
		if (style.useDashed) this.ctx.setLineDash([]);
		
		const t = 0.5, mt = 1 - t;
		let midX, midY;
		if (style.linkCurve > 0) {
			midX = mt**3*x1 + 3*mt**2*t*cx1 + 3*mt*t**2*cx2 + t**3*x2;
			midY = mt**3*y1 + 3*mt**2*t*y1 + 3*mt*t**2*y2 + t**3*y2;
		} else {
			midX = (x1 + x2) / 2;
			midY = (y1 + y2) / 2;
		}
		
		this._pendingPreviewHint = { midX, midY, style };
	};
	
	SchemaGraphAppClass.prototype._drawPreviewHint = function() {
		if (!this._pendingPreviewHint) return;

		this.ctx.save();
		this.ctx.translate(this.camera.x, this.camera.y);
		this.ctx.scale(this.camera.scale, this.camera.scale);

		const { midX, midY, style } = this._pendingPreviewHint;
		const hintText = 'Alt+Click to add Preview';
		const fontSize = 16 / this.camera.scale;
		const padX = 10 / this.camera.scale;
		const padY = 14 / this.camera.scale;
		const radius = 4 / this.camera.scale;

		this.ctx.font = `bold ${fontSize}px ${style.textFont}`;
		this.ctx.textAlign = 'center';
		this.ctx.textBaseline = 'middle';
		const textWidth = this.ctx.measureText(hintText).width;

		this.ctx.fillStyle = 'rgba(0, 0, 0, 0.8)';
		this.ctx.beginPath();
		this.ctx.roundRect(midX - textWidth/2 - padX, midY - padY, textWidth + padX * 2, padY * 2, radius);
		this.ctx.fill();

		this.ctx.strokeStyle = '#46a2da';
		this.ctx.lineWidth = 1 / this.camera.scale;
		this.ctx.stroke();

		this.ctx.fillStyle = '#82c4ec';
		this.ctx.fillText(hintText, midX, midY);

		this.ctx.restore();
		this._pendingPreviewHint = null;
	};

	const originalDraw = SchemaGraphAppClass.prototype.draw;
	SchemaGraphAppClass.prototype.draw = function() {
		originalDraw.call(this);
		this._drawPreviewHint();
	};
}

// ========================================================================
// Extend removeNode to handle preview nodes
// ========================================================================

function extendRemoveNodeForPreview(SchemaGraphAppClass) {
	const originalRemoveNode = SchemaGraphAppClass.prototype.removeNode;
	
	SchemaGraphAppClass.prototype.removeNode = function(node) {
		if (!node) return;
		
		if (node.isPreviewNode && this.edgePreviewManager) {
			this.edgePreviewManager.removePreviewNode(node);
			return;
		}
		
		if (this.edgePreviewManager) {
			const previewsToRemove = [];
			
			for (const linkId in this.graph.links) {
				const link = this.graph.links[linkId];
				if (link.origin_id === node.id || link.target_id === node.id) {
					const otherId = link.origin_id === node.id ? link.target_id : link.origin_id;
					const otherNode = this.graph.getNodeById(otherId);
					if (otherNode?.isPreviewNode && !previewsToRemove.includes(otherNode)) {
						previewsToRemove.push(otherNode);
					}
				}
			}
			
			for (const preview of previewsToRemove) {
				this._removePreviewNodeWithoutRestore(preview);
			}
		}
		
		// Use graph's removeNode API (emits events)
		if (this.graph?.removeNode) {
			this.graph.removeNode(node);
		} else if (originalRemoveNode) {
			originalRemoveNode.call(this, node);
		}
	};

	SchemaGraphAppClass.prototype._removePreviewNodeWithoutRestore = function(node) {
		if (!node?.isPreviewNode) return;
		
		const inLinkId = node.inputs[0]?.link;
		const outLinkIds = node.outputs[0]?.links || [];
		
		// Remove links using proper API
		if (inLinkId) this.graph.removeLink(inLinkId);
		for (const id of outLinkIds) this.graph.removeLink(id);
		
		// Remove node using proper API
		this.graph.removeNode(node);
		
		this.eventBus.emit('preview:removed', { nodeId: node.id, restored: false });
	};
}

// ========================================================================
// Media Player Manager
// ========================================================================

class PreviewMediaManager {
	constructor(app) {
		this.app = app;
		this.audioElement = null;
		this.activeAudioNode = null;
	}

	toggleAudio(node, src) {
		if (node._isPlaying) {
			this.stopAudio();
		} else {
			this.playAudio(node, src);
		}
	}

	playAudio(node, src) {
		this.stopAudio();
		
		this.audioElement = new Audio(src);
		this.audioElement.onended = () => {
			node._isPlaying = false;
			this.activeAudioNode = null;
			this.app.draw();
		};
		this.audioElement.onerror = () => {
			node._isPlaying = false;
			this.activeAudioNode = null;
			this.app.showError?.('Failed to play audio');
			this.app.draw();
		};
		
		this.audioElement.play();
		node._isPlaying = true;
		this.activeAudioNode = node;
		this.app.draw();
	}

	stopAudio() {
		if (this.audioElement) {
			this.audioElement.pause();
			this.audioElement.src = '';
			this.audioElement = null;
		}
		if (this.activeAudioNode) {
			this.activeAudioNode._isPlaying = false;
			this.activeAudioNode = null;
		}
		this.app.draw();
	}
}

// ========================================================================
// AUTO-INITIALIZATION
// ========================================================================

if (typeof SchemaGraphApp !== 'undefined') {
	extendDrawNodeForPreview(SchemaGraphApp);
	extendDrawLinksForPreview(SchemaGraphApp);
	extendRemoveNodeForPreview(SchemaGraphApp);
	
	if (typeof extensionRegistry !== 'undefined') {
		extensionRegistry.register('preview', PreviewExtension);
	} else {
		const originalSetup = SchemaGraphApp.prototype.setupEventListeners;
		SchemaGraphApp.prototype.setupEventListeners = function() {
			originalSetup.call(this);
			this.edgePreviewManager = new PreviewExtension(this);
			this.previewMediaManager = new PreviewMediaManager(this);
		};
	}
	
	console.log('✨ SchemaGraph Preview extension loaded');
}

// ========================================================================
// Exports
// ========================================================================

if (typeof module !== 'undefined' && module.exports) {
	module.exports = {
		PreviewType, PreviewNode, PreviewExtension, PreviewMediaManager,
		extendDrawNodeForPreview, extendDrawLinksForPreview, extendRemoveNodeForPreview
	};
}
