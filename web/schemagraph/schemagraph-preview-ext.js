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
		
		if (this.properties.autoDetect) {
			this.previewType = this._detectType(inputData);
		} else {
			this.previewType = this.properties.previewType;
		}
		
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
		if (!str) return false;
		const lower = str.toLowerCase();
		return lower.startsWith('data:image/') ||
			/\.(jpg|jpeg|png|gif|webp|svg|bmp|ico)(\?|$)/i.test(str);
	}

	_isAudioData(str) {
		if (!str) return false;
		const lower = str.toLowerCase();
		return lower.startsWith('data:audio/') ||
			/\.(mp3|wav|ogg|m4a|flac|aac)(\?|$)/i.test(str);
	}

	_isVideoData(str) {
		if (!str) return false;
		const lower = str.toLowerCase();
		return lower.startsWith('data:video/') ||
			/\.(mp4|webm|ogg|mov|avi|mkv)(\?|$)/i.test(str);
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
					return JSON.stringify(arr, null, 2);
				}
				return JSON.stringify(arr.slice(0, maxItems), null, 2) + '\n...';
			
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
// Edge Hit Detection & Preview Node Insertion
// ========================================================================

class EdgePreviewManager {
	constructor(app) {
		this.app = app;
		this.graph = app.graph;
		this.eventBus = app.eventBus;
		this.hoveredLink = null;
		this.linkHitDistance = 10;
		
		this._registerPreviewNodeType();
		this._setupEventListeners();
		this._injectStyles();
	}

	canInsertPreview(link) {
		if (!link) {
			return { allowed: false, reason: 'Invalid link' };
		}

		const sourceNode = this.graph.getNodeById(link.origin_id);
		const targetNode = this.graph.getNodeById(link.target_id);

		if (!sourceNode || !targetNode) {
			return { allowed: false, reason: 'Invalid source or target node' };
		}

		if (sourceNode.isPreviewNode) {
			return { allowed: false, reason: 'Source is already a preview node' };
		}

		if (targetNode.isPreviewNode) {
			return { allowed: false, reason: 'Target is already a preview node' };
		}

		return { allowed: true, reason: null };
	}

	_registerPreviewNodeType() {
		this.graph.nodeTypes['Native.Preview'] = PreviewNode;
	}

	_setupEventListeners() {
		this.eventBus.on('mouse:move', (data) => this._onMouseMove(data));
		this.eventBus.on('mouse:down', (data) => this._onMouseDown(data));
		this.eventBus.on('mouse:dblclick', (data) => this._onDoubleClick(data));
		this.eventBus.on('contextmenu', (data) => this._onContextMenu(data));
		this._setupKeyboardHandler();
	}

	_setupKeyboardHandler() {
		document.addEventListener('keydown', (e) => {
			if (this.app.isLocked) return;
			
			if (e.key === 'Delete' || e.key === 'Backspace') {
				const selectedNodes = Array.from(this.app.selectedNodes || []);
				const previewNodesToRemove = selectedNodes.filter(n => n.isPreviewNode);
				if (previewNodesToRemove.length > 0) {
					e.preventDefault();
					e.stopPropagation();
					
					for (const node of previewNodesToRemove) {
						this.removePreviewNode(node);
					}
					
					this.app.selectedNodes = new Set(selectedNodes.filter(n => !n.isPreviewNode));
				}
			}
		});
	}

	_onMouseMove(data) {
		if (this.app.connecting || this.app.dragNode || this.app.isPanning) {
			this.hoveredLink = null;
			return;
		}
		
		if (this.app.isLocked) {
			this.hoveredLink = null;
			return;
		}
		
		const [wx, wy] = this.app.screenToWorld(data.coords.screenX, data.coords.screenY);
		const link = this._findLinkAtPosition(wx, wy);
		
		if (link) {
			const check = this.canInsertPreview(link);
			if (check.allowed) {
				this.hoveredLink = link;
				this.app.canvas.style.cursor = 'pointer';
			} else {
				this.hoveredLink = null;
			}
		} else {
			this.hoveredLink = null;
		}
	}

	_onMouseDown(data) {
		if (data.button !== 0) return;
		if (this.app.connecting || this.app.dragNode) return;
		if (this.app.isLocked) return;
		
		const [wx, wy] = this.app.screenToWorld(data.coords.screenX, data.coords.screenY);
		const link = this._findLinkAtPosition(wx, wy);
		
		if (link && data.event.altKey) {
			const check = this.canInsertPreview(link);
			if (check.allowed) {
				data.event.preventDefault();
				data.event.stopPropagation();
				this.insertPreviewNode(link, wx, wy);
				return true;
			}
		}
	}

	_onDoubleClick(data) {
		const [wx, wy] = this.app.screenToWorld(data.coords.screenX, data.coords.screenY);
		
		for (const node of this.graph.nodes) {
			if (!node.isPreviewNode) continue;
			
			if (wx >= node.pos[0] && wx <= node.pos[0] + node.size[0] &&
				wy >= node.pos[1] && wy <= node.pos[1] + node.size[1]) {
				
				// Toggle expanded state inline
				node.isExpanded = !node.isExpanded;
				
				if (node.isExpanded) {
					node._collapsedSize = [...node.size];
					node.size = [280, 200];
				} else {
					node.size = node._collapsedSize || [220, 80];
				}
				
				this.app.draw();
				return;
			}
		}
	}

	_onContextMenu(data) {
		if (this.app.isLocked) return;
	
		const [wx, wy] = this.app.screenToWorld(data.coords.screenX, data.coords.screenY);
		
		const link = this._findLinkAtPosition(wx, wy);
		if (link) {
			data.event.preventDefault();
			this._showEdgeContextMenu(link, data.coords.screenX, data.coords.screenY, wx, wy);
			return true;
		}
		
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
			
			const bx = mt3 * x1 + 3 * mt2 * t * cx1 + 3 * mt * t2 * cx2 + t3 * x2;
			const by = mt3 * y1 + 3 * mt2 * t * y1 + 3 * mt * t2 * y2 + t3 * y2;
			
			const dist = Math.sqrt((px - bx) ** 2 + (py - by) ** 2);
			if (dist < threshold) return true;
		}
		
		return false;
	}

	insertPreviewNode(link, wx, wy) {
		if (this.app.isLocked) {
			console.warn('Cannot insert preview: graph is locked');
			return null;
		}

		const check = this.canInsertPreview(link);
		if (!check.allowed) {
			console.warn(`Cannot insert preview: ${check.reason}`);
			return null;
		}
	
		const sourceNode = this.graph.getNodeById(link.origin_id);
		const targetNode = this.graph.getNodeById(link.target_id);

		const originalEdgeInfo = {
			sourceNodeId: link.origin_id,
			sourceSlotIdx: link.origin_slot,
			sourceSlotName: sourceNode.outputs[link.origin_slot]?.name || 'output',
			targetNodeId: link.target_id,
			targetSlotIdx: link.target_slot,
			targetSlotName: targetNode.inputs[link.target_slot]?.name || 'input',
			linkType: link.type,
			linkId: link.id,
			data: link.data ? JSON.parse(JSON.stringify(link.data)) : null,
			extra: link.extra ? JSON.parse(JSON.stringify(link.extra)) : null,
		};

		const previewNode = new PreviewNode();
		previewNode.pos = [wx - previewNode.size[0] / 2, wy - previewNode.size[1] / 2];
		previewNode._originalEdgeInfo = originalEdgeInfo;

		if (this.graph._last_node_id === undefined) {
			this.graph._last_node_id = 1;
		}
		previewNode.id = this.graph._last_node_id++;
		previewNode.graph = this.graph;
		this.graph.nodes.push(previewNode);
		this.graph._nodes_by_id[previewNode.id] = previewNode;

		this._removeLink(link);

		const link1Id = ++this.graph.last_link_id;
		const link1 = new Link(
			link1Id,
			sourceNode.id,
			originalEdgeInfo.sourceSlotIdx,
			previewNode.id,
			0,
			originalEdgeInfo.linkType
		);
		link1.extra = { _isPreviewLink: true };

		this.graph.links[link1Id] = link1;
		sourceNode.outputs[originalEdgeInfo.sourceSlotIdx].links.push(link1Id);
		previewNode.inputs[0].link = link1Id;

		const link2Id = ++this.graph.last_link_id;
		const link2 = new Link(
			link2Id,
			previewNode.id,
			0,
			targetNode.id,
			originalEdgeInfo.targetSlotIdx,
			originalEdgeInfo.linkType
		);
		link2.extra = { _isPreviewLink: true };

		this.graph.links[link2Id] = link2;
		previewNode.outputs[0].links.push(link2Id);

		if (targetNode.multiInputs && targetNode.multiInputs[originalEdgeInfo.targetSlotIdx]) {
			targetNode.multiInputs[originalEdgeInfo.targetSlotIdx].links.push(link2Id);
		} else {
			targetNode.inputs[originalEdgeInfo.targetSlotIdx].link = link2Id;
		}

		previewNode.onExecute();

		this.eventBus.emit('preview:inserted', { 
			nodeId: previewNode.id, 
			originalEdgeInfo: originalEdgeInfo 
		});
		
		this.app.draw();
		return previewNode;
	}

	removePreviewNode(node) {
		if (this.app.isLocked) {
			console.warn('Cannot remove preview: graph is locked');
			return null;
		}

		if (!node || !node.isPreviewNode) {
			return null;
		}

		const originalEdgeInfo = node._originalEdgeInfo;
		const inLinkId = node.inputs[0]?.link;
		const outLinkIds = node.outputs[0]?.links || [];

		const inLink = inLinkId ? this.graph.links[inLinkId] : null;
		const outLinks = outLinkIds.map(id => this.graph.links[id]).filter(Boolean);

		let restoredLink = null;

		if (inLink && outLinks.length > 0) {
			const sourceNode = this.graph.getNodeById(inLink.origin_id);
			const sourceSlotIdx = inLink.origin_slot;

			for (const outLink of outLinks) {
				const targetNode = this.graph.getNodeById(outLink.target_id);
				const targetSlotIdx = outLink.target_slot;

				if (sourceNode && targetNode) {
					const newLinkId = ++this.graph.last_link_id;
					const newLink = new Link(
						newLinkId,
						sourceNode.id,
						sourceSlotIdx,
						targetNode.id,
						targetSlotIdx,
						originalEdgeInfo?.linkType || inLink.type
					);

					if (originalEdgeInfo) {
						if (originalEdgeInfo.data) {
							newLink.data = JSON.parse(JSON.stringify(originalEdgeInfo.data));
						}
						if (originalEdgeInfo.extra) {
							const restoredExtra = JSON.parse(JSON.stringify(originalEdgeInfo.extra));
							delete restoredExtra._isPreviewLink;
							if (Object.keys(restoredExtra).length > 0) {
								newLink.extra = restoredExtra;
							}
						}
					}

					this.graph.links[newLinkId] = newLink;
					sourceNode.outputs[sourceSlotIdx].links.push(newLinkId);

					if (targetNode.multiInputs && targetNode.multiInputs[targetSlotIdx]) {
						targetNode.multiInputs[targetSlotIdx].links.push(newLinkId);
					} else {
						targetNode.inputs[targetSlotIdx].link = newLinkId;
					}

					this.eventBus.emit('link:created', { linkId: newLinkId });
					restoredLink = newLink;
				}
			}
		}

		if (inLink) {
			this._removeLinkById(inLinkId);
		}
		for (const outLinkId of outLinkIds) {
			this._removeLinkById(outLinkId);
		}

		const nodeIdx = this.graph.nodes.indexOf(node);
		if (nodeIdx !== -1) {
			this.graph.nodes.splice(nodeIdx, 1);
		}
		delete this.graph._nodes_by_id[node.id];

		this.eventBus.emit('preview:removed', { 
			nodeId: node.id,
			restoredLinkId: restoredLink?.id,
			originalEdgeInfo: originalEdgeInfo
		});

		this.app.draw();
		return restoredLink;
	}

	_removeLinkById(linkId) {
		const link = this.graph.links[linkId];
		if (!link) return;

		const sourceNode = this.graph.getNodeById(link.origin_id);
		const targetNode = this.graph.getNodeById(link.target_id);

		if (sourceNode && sourceNode.outputs[link.origin_slot]) {
			const idx = sourceNode.outputs[link.origin_slot].links.indexOf(linkId);
			if (idx > -1) {
				sourceNode.outputs[link.origin_slot].links.splice(idx, 1);
			}
		}

		if (targetNode) {
			if (targetNode.multiInputs && targetNode.multiInputs[link.target_slot]) {
				const idx = targetNode.multiInputs[link.target_slot].links.indexOf(linkId);
				if (idx > -1) {
					targetNode.multiInputs[link.target_slot].links.splice(idx, 1);
				}
			} else if (targetNode.inputs[link.target_slot]) {
				if (targetNode.inputs[link.target_slot].link === linkId) {
					targetNode.inputs[link.target_slot].link = null;
				}
			}
		}

		delete this.graph.links[linkId];
		this.eventBus.emit('link:deleted', { linkId });
	}

	_removeLink(link) {
		if (link && link.id !== undefined) {
			this._removeLinkById(link.id);
		}
	}

	_showEdgeContextMenu(link, screenX, screenY, worldX, worldY) {
		const menu = this._getOrCreateContextMenu();
		const targetNode = this.graph.getNodeById(link.target_id);
		const hasPreview = targetNode?.isPreviewNode;
		
		menu.innerHTML = `
			<div class="sg-context-menu-title">Edge Options</div>
			<div class="sg-context-menu-item" data-action="add-preview">
				${hasPreview ? '🔄 Move Preview Here' : '👁 Add Preview'}
			</div>
			${hasPreview ? `<div class="sg-context-menu-item" data-action="remove-preview">❌ Remove Preview</div>` : ''}
			<div class="sg-context-menu-item" data-action="delete-edge">🗑️ Delete Edge</div>
		`;
		
		menu.style.left = screenX + 'px';
		menu.style.top = screenY + 'px';
		menu.style.display = 'block';
		
		this._contextMenuData = { link, worldX, worldY, hasPreview, targetNode };
		
		menu.querySelectorAll('.sg-context-menu-item').forEach(item => {
			item.onclick = () => {
				this._handleEdgeContextAction(item.dataset.action);
				this._hideContextMenu();
			};
		});
		
		setTimeout(() => {
			document.addEventListener('click', this._hideContextMenuBound, { once: true });
		}, 0);
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
		
		menu.style.left = screenX + 'px';
		menu.style.top = screenY + 'px';
		menu.style.display = 'block';
		
		this._contextMenuData = { previewNode: node };
		
		menu.querySelectorAll('.sg-context-menu-item').forEach(item => {
			item.onclick = () => {
				this._handlePreviewNodeContextAction(item.dataset.action);
				this._hideContextMenu();
			};
		});
		
		setTimeout(() => {
			document.addEventListener('click', this._hideContextMenuBound, { once: true });
		}, 0);
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

	_handlePreviewNodeContextAction(action) {
		const { previewNode } = this._contextMenuData || {};
		if (!previewNode) return;
		
		switch (action) {
			case 'toggle-expand':
				previewNode.isExpanded = !previewNode.isExpanded;
				if (previewNode.isExpanded) {
					previewNode._collapsedSize = [...previewNode.size];
					previewNode.size = [280, 200];
				} else {
					previewNode.size = previewNode._collapsedSize || [220, 80];
				}
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
			this._hideContextMenuBound = () => this._hideContextMenu();
		}
		
		return menu;
	}

	_hideContextMenu() {
		const menu = document.getElementById('sg-preview-context-menu');
		if (menu) {
			menu.style.display = 'none';
		}
		this._contextMenuData = null;
	}

	_injectStyles() {
		if (document.getElementById('sg-preview-styles')) return;
		
		const style = document.createElement('style');
		style.id = 'sg-preview-styles';
		style.textContent = `
			.sg-preview-context-menu {
				min-width: 180px;
			}
			.sg-preview-context-menu .sg-context-menu-divider {
				height: 1px;
				background: var(--sg-border-color, #1a1a1a);
				margin: 4px 0;
			}
		`;
		document.head.appendChild(style);
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
		const x = node.pos[0];
		const y = node.pos[1];
		const w = node.size[0];
		const h = node.size[1];
		const radius = style.nodeCornerRadius;
		const textScale = this.getTextScale();
		
		// Flash intensity
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
		
		const isSelected = this.isNodeSelected(node);
		
		// Shadow
		if (style.nodeShadowBlur > 0 || flashIntensity > 0) {
			this.ctx.shadowColor = flashIntensity > 0 
				? `rgba(${flashColor.r}, ${flashColor.g}, ${flashColor.b}, ${0.8 * flashIntensity})`
				: colors.nodeShadow;
			this.ctx.shadowBlur = Math.max(style.nodeShadowBlur, flashIntensity * 25) / this.camera.scale;
			this.ctx.shadowOffsetY = flashIntensity > 0 ? 0 : style.nodeShadowOffset / this.camera.scale;
		}
		
		// Body
		const gradient = this.ctx.createLinearGradient(x, y, x, y + h);
		gradient.addColorStop(0, isSelected ? '#3a5a7a' : '#2d3d4d');
		gradient.addColorStop(1, isSelected ? '#2a4a6a' : '#1d2d3d');
		this.ctx.fillStyle = gradient;
		
		this.ctx.beginPath();
		this._roundRect(x, y, w, h, radius);
		this.ctx.fill();
		
		this.ctx.strokeStyle = flashIntensity > 0 ? colorStr : (isSelected ? colors.borderHighlight : '#46a2da');
		this.ctx.lineWidth = ((isSelected ? 2 : 1.5) + flashIntensity * 1.5) / this.camera.scale;
		this.ctx.stroke();
		
		this.ctx.shadowBlur = 0;
		this.ctx.shadowOffsetY = 0;
		
		// Header
		const headerH = 26;
		const headerGradient = this.ctx.createLinearGradient(x, y, x, y + headerH);
		headerGradient.addColorStop(0, flashIntensity > 0 ? colorStr : '#46a2da');
		headerGradient.addColorStop(1, flashIntensity > 0 
			? `rgb(${Math.round(currentColor.r * 0.7)}, ${Math.round(currentColor.g * 0.7)}, ${Math.round(currentColor.b * 0.7)})`
			: '#2a7ab8');
		this.ctx.fillStyle = headerGradient;
		
		this.ctx.beginPath();
		this._roundRectTop(x, y, w, headerH, radius);
		this.ctx.fill();
		
		// Title
		this.ctx.fillStyle = colors.textPrimary;
		this.ctx.font = `bold ${11 * textScale}px ${style.textFont}`;
		this.ctx.textBaseline = 'middle';
		this.ctx.textAlign = 'left';
		this.ctx.fillText('Preview 👁', x + 8, y + 13);
		
		// Type badge
		const typeText = node.previewType.toUpperCase();
		this.ctx.font = `bold ${8 * textScale}px ${style.textFont}`;
		const badgeWidth = this.ctx.measureText(typeText).width + 8;
		
		this.ctx.fillStyle = this._getTypeColor(node.previewType);
		this.ctx.beginPath();
		this._roundRect(x + w - badgeWidth - 8, y + 6, badgeWidth, 14, 3);
		this.ctx.fill();
		
		this.ctx.fillStyle = '#fff';
		this.ctx.textAlign = 'center';
		this.ctx.fillText(typeText, x + w - badgeWidth / 2 - 8, y + 13);
		
		// Content area - placed below the header AND below the slot pins
		const contentX = x + 8;
		const contentW = w - 16;
		const contentY = node.isExpanded ? y + 65 : y + 55;
		const contentH = node.isExpanded ? h - 85 : h - 75;
		
		if (node.isExpanded) {
			this._drawExpandedPreview(node, contentX, contentY, contentW, contentH, colors, textScale, style);
		} else {
			this._drawCollapsedPreview(node, contentX, contentY, contentW, contentH, colors, textScale, style);
		}
		
		// Draw slots
		const worldMouse = this.screenToWorld(this.mousePos[0], this.mousePos[1]);
		this.drawInputSlot(node, 0, x, y, w, worldMouse, colors);
		this.drawOutputSlot(node, 0, x, y, w, worldMouse, colors);
		
		// Footer hint
		this.ctx.fillStyle = colors.textTertiary;
		this.ctx.font = `${8 * textScale}px ${style.textFont}`;
		this.ctx.textAlign = 'center';
		this.ctx.fillText(node.isExpanded ? 'Dbl-click to collapse' : 'Dbl-click to expand', x + w / 2, y + h - 8);
	};

	// Collapsed: icon + one-line summary (below slots, full width available)
	SchemaGraphAppClass.prototype._drawCollapsedPreview = function(node, x, y, w, h, colors, textScale, style) {
		const icon = this._getTypeIcon(node.previewType);
		const summary = this._getPreviewSummary(node);
		
		const centerY = y + h / 2;
		
		// Icon
		this.ctx.font = `${18 * textScale}px ${style.textFont}`;
		this.ctx.textAlign = 'center';
		this.ctx.textBaseline = 'middle';
		this.ctx.fillStyle = this._getTypeColor(node.previewType);
		this.ctx.fillText(icon, x + 14, centerY);
		
		// Summary text
		this.ctx.font = `${10 * textScale}px ${style.textFont}`;
		this.ctx.textAlign = 'left';
		this.ctx.fillStyle = colors.textPrimary;
		
		const textX = x + 32;
		const maxTextW = w - 36;
		let displayText = summary;
		if (this.ctx.measureText(displayText).width > maxTextW) {
			while (displayText.length > 3 && this.ctx.measureText(displayText + '...').width > maxTextW) {
				displayText = displayText.slice(0, -1);
			}
			displayText += '...';
		}
		this.ctx.fillText(displayText, textX, centerY);
	};

	// Expanded: full content preview
	SchemaGraphAppClass.prototype._drawExpandedPreview = function(node, x, y, w, h, colors, textScale, style) {
		const radius = 6;
		
		// Background with rounded corners
		this.ctx.fillStyle = 'rgba(0, 0, 0, 0.3)';
		this.ctx.beginPath();
		this.ctx.roundRect(x, y, w, h, radius);
		this.ctx.fill();
		
		this.ctx.strokeStyle = 'rgba(255, 255, 255, 0.1)';
		this.ctx.lineWidth = 1 / this.camera.scale;
		this.ctx.stroke();
		
		const padding = 6;
		const innerX = x + padding;
		const innerY = y + padding;
		const innerW = w - padding * 2;
		const innerH = h - padding * 2;
		
		// Clip to content area with rounded corners
		this.ctx.save();
		this.ctx.beginPath();
		this.ctx.roundRect(innerX, innerY, innerW, innerH, radius - 2);
		this.ctx.clip();
		
		const data = node.previewData;
		const type = node.previewType;
		
		switch (type) {
			case PreviewType.BOOLEAN:
				this._drawBooleanPreview(data, innerX, innerY, innerW, innerH, textScale, style);
				break;
			case PreviewType.NUMBER:
				this._drawNumberPreview(data, innerX, innerY, innerW, innerH, textScale, style);
				break;
			case PreviewType.IMAGE:
				this._drawImagePlaceholder(node, innerX, innerY, innerW, innerH, textScale, style);
				break;
			case PreviewType.AUDIO:
			case PreviewType.VIDEO:
			case PreviewType.MODEL3D:
				this._drawMediaPlaceholder(type, innerX, innerY, innerW, innerH, textScale, style);
				break;
			default:
				this._drawTextPreview(node, innerX, innerY, innerW, innerH, colors, textScale, style);
		}
		
		this.ctx.restore();
	};

	SchemaGraphAppClass.prototype._drawBooleanPreview = function(value, x, y, w, h, textScale, style) {
		const centerX = x + w / 2;
		const centerY = y + h / 2;
		const color = value ? '#92d050' : '#dc6464';
		const icon = value ? '✓' : '✗';
		const text = value ? 'true' : 'false';
		
		this.ctx.font = `bold ${28 * textScale}px ${style.textFont}`;
		this.ctx.textAlign = 'center';
		this.ctx.textBaseline = 'middle';
		this.ctx.fillStyle = color;
		this.ctx.fillText(icon, centerX, centerY - 12);
		
		this.ctx.font = `bold ${14 * textScale}px ${style.textFont}`;
		this.ctx.fillText(text, centerX, centerY + 16);
	};

	SchemaGraphAppClass.prototype._drawNumberPreview = function(value, x, y, w, h, textScale, style) {
		const centerX = x + w / 2;
		const centerY = y + h / 2;
		
		this.ctx.font = `bold ${24 * textScale}px ${style.textFont}`;
		this.ctx.textAlign = 'center';
		this.ctx.textBaseline = 'middle';
		this.ctx.fillStyle = '#ff9f4a';
		this.ctx.fillText(String(value), centerX, centerY);
	};

	SchemaGraphAppClass.prototype._drawTextPreview = function(node, x, y, w, h, colors, textScale, style) {
		const text = node.getPreviewText();
		
		// Split by newlines first to preserve JSON formatting
		const rawLines = text.split('\n');
		const lines = [];
		
		this.ctx.font = `${9 * textScale}px 'Courier New', monospace`;
		
		// Wrap each line if needed
		for (const rawLine of rawLines) {
			if (this.ctx.measureText(rawLine).width <= w) {
				lines.push(rawLine);
			} else {
				// Wrap long lines
				const wrapped = this._wrapText(rawLine, w, this.ctx);
				lines.push(...wrapped);
			}
		}
		
		const lineHeight = 11 * textScale;
		const maxLines = Math.floor(h / lineHeight);
		
		this.ctx.textAlign = 'left';
		this.ctx.textBaseline = 'top';
		this.ctx.fillStyle = colors.textSecondary;
		
		for (let i = 0; i < Math.min(lines.length, maxLines); i++) {
			this.ctx.fillText(lines[i], x, y + i * lineHeight);
		}
		
		if (lines.length > maxLines) {
			this.ctx.fillStyle = colors.textTertiary;
			this.ctx.fillText('...', x, y + maxLines * lineHeight);
		}
	};

	SchemaGraphAppClass.prototype._drawImagePlaceholder = function(node, x, y, w, h, textScale, style) {
		const src = node.getMediaSource();
		const centerX = x + w / 2;
		const centerY = y + h / 2;
		
		this.ctx.font = `${28 * textScale}px ${style.textFont}`;
		this.ctx.textAlign = 'center';
		this.ctx.textBaseline = 'middle';
		this.ctx.fillStyle = '#00d4aa';
		this.ctx.fillText('🖼️', centerX, centerY - 10);
		
		this.ctx.font = `${9 * textScale}px ${style.textFont}`;
		this.ctx.fillStyle = '#707070';
		const urlText = src ? (src.length > 30 ? src.slice(0, 30) + '...' : src) : 'No source';
		this.ctx.fillText(urlText, centerX, centerY + 18);
	};

	SchemaGraphAppClass.prototype._drawMediaPlaceholder = function(type, x, y, w, h, textScale, style) {
		const centerX = x + w / 2;
		const centerY = y + h / 2;
		
		const icons = {
			[PreviewType.AUDIO]: '🔊',
			[PreviewType.VIDEO]: '🎬',
			[PreviewType.MODEL3D]: '🧊'
		};
		
		this.ctx.font = `${28 * textScale}px ${style.textFont}`;
		this.ctx.textAlign = 'center';
		this.ctx.textBaseline = 'middle';
		this.ctx.fillStyle = this._getTypeColor(type);
		this.ctx.fillText(icons[type] || '📄', centerX, centerY);
	};

	SchemaGraphAppClass.prototype._getTypeIcon = function(type) {
		const icons = {
			[PreviewType.STRING]: '📝',
			[PreviewType.NUMBER]: '🔢',
			[PreviewType.BOOLEAN]: '⚡',
			[PreviewType.JSON]: '📋',
			[PreviewType.LIST]: '📚',
			[PreviewType.IMAGE]: '🖼️',
			[PreviewType.AUDIO]: '🔊',
			[PreviewType.VIDEO]: '🎬',
			[PreviewType.MODEL3D]: '🧊',
			[PreviewType.UNKNOWN]: '❓'
		};
		return icons[type] || '📄';
	};

	SchemaGraphAppClass.prototype._getPreviewSummary = function(node) {
		const data = node.previewData;
		const type = node.previewType;
		
		if (data === null) return 'null';
		if (data === undefined) return 'undefined';
		
		switch (type) {
			case PreviewType.STRING:
				return `"${String(data)}"`;
			case PreviewType.NUMBER:
				return String(data);
			case PreviewType.BOOLEAN:
				return data ? 'true' : 'false';
			case PreviewType.LIST:
				return `Array (${data.length} items)`;
			case PreviewType.JSON:
				const keys = Object.keys(data);
				return `Object (${keys.length} keys)`;
			case PreviewType.IMAGE:
				return 'Image';
			case PreviewType.AUDIO:
				return 'Audio';
			case PreviewType.VIDEO:
				return 'Video';
			case PreviewType.MODEL3D:
				return '3D Model';
			default:
				return String(data).slice(0, 50);
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
// Draw hovered edge highlight - hint drawn on top via post-render
// ========================================================================

function extendDrawLinksForPreview(SchemaGraphAppClass) {
	const originalDrawLinks = SchemaGraphAppClass.prototype.drawLinks;
	
	SchemaGraphAppClass.prototype.drawLinks = function(colors) {
		originalDrawLinks.call(this, colors);
		
		this._pendingPreviewHint = null;
		
		if (this.edgePreviewManager?.hoveredLink) {
			const link = this.edgePreviewManager.hoveredLink;
			const orig = this.graph.getNodeById(link.origin_id);
			const targ = this.graph.getNodeById(link.target_id);
			
			if (orig && targ) {
				const style = this.drawingStyleManager.getStyle();
				
				const x1 = orig.pos[0] + orig.size[0];
				const y1 = orig.pos[1] + 33 + link.origin_slot * 25;
				const x2 = targ.pos[0];
				const y2 = targ.pos[1] + 33 + link.target_slot * 25;
				
				const distance = Math.abs(x2 - x1);
				const maxControlDistance = 400;
				const controlOffset = Math.min(distance * style.linkCurve, maxControlDistance);
				const cx1 = x1 + controlOffset;
				const cx2 = x2 - controlOffset;
				
				// Glow effect
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
				
				// Highlight line
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
				
				if (style.useDashed) {
					this.ctx.setLineDash([]);
				}
				
				// Calculate midpoint for hint
				const midT = 0.5;
				const mt = 1 - midT;
				let midX, midY;
				
				if (style.linkCurve > 0) {
					midX = mt*mt*mt*x1 + 3*mt*mt*midT*cx1 + 3*mt*midT*midT*cx2 + midT*midT*midT*x2;
					midY = mt*mt*mt*y1 + 3*mt*mt*midT*y1 + 3*mt*midT*midT*y2 + midT*midT*midT*y2;
				} else {
					midX = (x1 + x2) / 2;
					midY = (y1 + y2) / 2;
				}
				
				// Store hint for post-render
				this._pendingPreviewHint = { midX, midY, style };
			}
		}
	};
	
	// Draw preview hint on top of everything
	SchemaGraphAppClass.prototype._drawPreviewHint = function() {
		if (!this._pendingPreviewHint) return;

		// Apply camera transform (same as main draw)
		this.ctx.save();
		this.ctx.translate(this.camera.x, this.camera.y);
		this.ctx.scale(this.camera.scale, this.camera.scale);

		const { midX, midY, style } = this._pendingPreviewHint;
		const hintText = 'Alt+Click to add Preview';
		const fixedSizeHint = true;

		this.ctx.textAlign = 'center';
		this.ctx.textBaseline = 'middle';
			
		// Background for text
		this.ctx.fillStyle = 'rgba(0, 0, 0, 0.8)';
		this.ctx.beginPath();

		if (fixedSizeHint) {
			const fontSize = 16 / this.camera.scale;
			const padX = 10 / this.camera.scale;
			const padY = 14 / this.camera.scale;
			const offX = 0 / this.camera.scale;
			const offY = -2 / this.camera.scale;
			const radius = 4 / this.camera.scale;

			this.ctx.font = `bold ${fontSize}px ${style.textFont}`;
			const textWidth = this.ctx.measureText(hintText).width;

			this.ctx.roundRect(
				midX - textWidth/2 - padX + offX, 
				midY - padY + offY, 
				textWidth + padX * 2, 
				padY * 2, 
				radius
			);
		} else {
			const textScale = this.getTextScale();
			this.ctx.font = `bold ${10 * textScale}px ${style.textFont}`;
			const textWidth = this.ctx.measureText(hintText).width;

			this.ctx.roundRect(
				midX - textWidth/2 - 6, 
				midY - 10, 
				textWidth + 12, 
				20, 
				4
			);
		}

		this.ctx.fill();

		this.ctx.strokeStyle = '#46a2da';
		this.ctx.lineWidth = 1 / this.camera.scale;
		this.ctx.stroke();

		this.ctx.fillStyle = '#82c4ec';
		this.ctx.fillText(hintText, midX, midY);

		this.ctx.restore();
		this._pendingPreviewHint = null;
	};

	// Hook into main draw to render hint last
	const originalDraw = SchemaGraphAppClass.prototype.draw;
	SchemaGraphAppClass.prototype.draw = function() {
		originalDraw.call(this);
		this._drawPreviewHint();
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
			list: () => {
				return this.graph.nodes.filter(n => n.isPreviewNode);
			},
			
			expand: (nodeOrId) => {
				const node = typeof nodeOrId === 'string' 
					? this.graph.getNodeById(nodeOrId) 
					: nodeOrId;
				if (node?.isPreviewNode && !node.isExpanded) {
					node._collapsedSize = [...node.size];
					node.size = [260, 250];
					node.isExpanded = true;
					this.draw();
				}
			},
			
			collapse: (nodeOrId) => {
				const node = typeof nodeOrId === 'string' 
					? this.graph.getNodeById(nodeOrId) 
					: nodeOrId;
				if (node?.isPreviewNode && node.isExpanded) {
					node.size = node._collapsedSize || [200, 110];
					node.isExpanded = false;
					this.draw();
				}
			},

			canInsertOnLink: (linkId) => {
				const link = this.graph.links[linkId];
				return this.edgePreviewManager.canInsertPreview(link);
			},

			insertOnLink: (linkId) => {
				if (this.isLocked) return null;
				
				const link = this.graph.links[linkId];
				if (!link) return null;
				
				const orig = this.graph.getNodeById(link.origin_id);
				const targ = this.graph.getNodeById(link.target_id);
				if (!orig || !targ) return null;
				
				const midX = (orig.pos[0] + orig.size[0] + targ.pos[0]) / 2;
				const midY = (orig.pos[1] + targ.pos[1]) / 2;
				
				return this.edgePreviewManager.insertPreviewNode(link, midX, midY);
			},

			remove: (nodeOrId) => {
				if (this.isLocked) return null;
				
				const node = typeof nodeOrId === 'string' 
					? this.graph.getNodeById(nodeOrId) 
					: nodeOrId;
				
				if (!node?.isPreviewNode) return null;
				
				return this.edgePreviewManager.removePreviewNode(node);
			},

			removeAll: () => {
				if (this.isLocked) return 0;
				
				const previewNodes = this.graph.nodes.filter(n => n.isPreviewNode);
				let count = 0;
				for (const node of previewNodes) {
					if (this.edgePreviewManager.removePreviewNode(node)) count++;
				}
				return count;
			},

			getOriginalEdgeInfo: (nodeOrId) => {
				const node = typeof nodeOrId === 'string' 
					? this.graph.getNodeById(nodeOrId) 
					: nodeOrId;
				
				return node?.isPreviewNode ? node._originalEdgeInfo : null;
			}
		};
		
		return api;
	};
	
	const originalSetupEventListeners = SchemaGraphAppClass.prototype.setupEventListeners;
	SchemaGraphAppClass.prototype.setupEventListeners = function() {
		originalSetupEventListeners.call(this);
		this.edgePreviewManager = new EdgePreviewManager(this);
	};

	const originalRemoveNode = SchemaGraphAppClass.prototype.removeNode;
	SchemaGraphAppClass.prototype.removeNode = function(node) {
		if (!node) return;
		
		if (node.isPreviewNode && this.edgePreviewManager) {
			this.edgePreviewManager.removePreviewNode(node);
			return;
		}
		
		if (originalRemoveNode) {
			originalRemoveNode.call(this, node);
		}
	};
}

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
		EdgePreviewManager,
		extendDrawNodeForPreview,
		extendDrawLinksForPreview,
		extendSchemaGraphAppWithPreview
	};
}
