// ========================================================================
// SCHEMAGRAPH DATA NODES EXTENSION
// Provides data source nodes for native values and media assets.
// Supports file upload, URL input, drag-drop, and inline preview.
// ========================================================================

const DataType = Object.freeze({
	TEXT: 'text',
	DOCUMENT: 'document',
	IMAGE: 'image',
	AUDIO: 'audio',
	VIDEO: 'video',
	MODEL3D: 'model3d',
	BINARY: 'binary'
});

const DataMimeTypes = {
	[DataType.TEXT]: ['text/plain', 'text/markdown', 'text/csv', 'application/json', 'text/html', 'text/css', 'text/javascript'],
	[DataType.DOCUMENT]: ['application/pdf', 'application/msword', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', 'text/csv', 'application/vnd.ms-excel', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'],
	[DataType.IMAGE]: ['image/png', 'image/jpeg', 'image/gif', 'image/webp', 'image/svg+xml', 'image/bmp', 'image/ico'],
	[DataType.AUDIO]: ['audio/mpeg', 'audio/wav', 'audio/ogg', 'audio/mp4', 'audio/flac', 'audio/aac'],
	[DataType.VIDEO]: ['video/mp4', 'video/webm', 'video/ogg', 'video/quicktime', 'video/x-msvideo'],
	[DataType.MODEL3D]: ['model/gltf-binary', 'model/gltf+json', 'model/obj', 'model/fbx', 'model/stl'],
	[DataType.BINARY]: ['application/octet-stream', 'application/zip', 'application/x-tar', 'application/gzip', 'application/x-7z-compressed']
};

const DataExtensions = {
	[DataType.TEXT]: ['.txt', '.md', '.markdown', '.json', '.html', '.css', '.js', '.ts', '.py', '.yaml', '.yml', '.xml', '.log'],
	[DataType.DOCUMENT]: ['.pdf', '.doc', '.docx', '.csv', '.xls', '.xlsx', '.rtf'],
	[DataType.IMAGE]: ['.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg', '.bmp', '.ico'],
	[DataType.AUDIO]: ['.mp3', '.wav', '.ogg', '.m4a', '.flac', '.aac'],
	[DataType.VIDEO]: ['.mp4', '.webm', '.ogv', '.mov', '.avi', '.mkv'],
	[DataType.MODEL3D]: ['.glb', '.gltf', '.obj', '.fbx', '.stl', '.3ds'],
	[DataType.BINARY]: ['.bin', '.dat', '.zip', '.tar', '.gz', '.7z', '.rar', '.exe', '.dll', '.so']
};

const DataNodeIcons = (typeof NodeIcons !== 'undefined') ? NodeIcons : {
	[DataType.TEXT]: '📝',
	[DataType.DOCUMENT]: '📄',
	[DataType.IMAGE]: '🖼️',
	[DataType.AUDIO]: '🔊',
	[DataType.VIDEO]: '🎬',
	[DataType.MODEL3D]: '🧊',
	[DataType.BINARY]: '📦'
};

const DataNodeColors = (typeof NodeColors !== 'undefined') ? NodeColors : {
	[DataType.TEXT]: '#4a9eff',
	[DataType.DOCUMENT]: '#ff9f4a',
	[DataType.IMAGE]: '#00d4aa',
	[DataType.AUDIO]: '#ffd700',
	[DataType.VIDEO]: '#ff4757',
	[DataType.MODEL3D]: '#00bcd4',
	[DataType.BINARY]: '#9370db'
};

// ========================================================================
// Base DataNode Class
// ========================================================================

class DataNode extends Node {
	constructor(title, dataType) {
		super(title);
		this.isDataNode = true;
		this.dataType = dataType;
		this.isExpanded = false;
		
		this.sourceType = 'none';
		this.sourceUrl = '';
		this.sourceData = null;
		this.sourceMeta = { filename: '', mimeType: '', size: 0, lastModified: null };
		
		this.addOutput('data', this._getOutputType());
		this.addOutput('meta', 'Object');
		
		this.size = [200, 100];
		this.minSize = [180, 90];
		this.maxSize = [400, 500];
		this.properties = { url: '', inline: '' };
	}

	_getOutputType() {
		return this.dataType.charAt(0).toUpperCase() + this.dataType.slice(1);
	}

	onExecute() {
		const output = {
			type: this.dataType,
			sourceType: this.sourceType,
			url: this.sourceUrl || null,
			data: this.sourceData || null,
			meta: { ...this.sourceMeta }
		};
		this.setOutputData(0, output);
		this.setOutputData(1, this.sourceMeta);
	}

	setFromUrl(url) {
		this.sourceType = 'url';
		this.sourceUrl = url;
		this.sourceData = null;
		this.sourceMeta.filename = url.split('/').pop().split('?')[0] || 'unknown';
		this.sourceMeta.mimeType = this._guessMimeType(url);
		this.properties.url = url;
		this.onExecute();
	}

	setFromFile(file, base64Data) {
		this.sourceType = 'file';
		this.sourceUrl = '';
		this.sourceData = base64Data;
		this.sourceMeta = {
			filename: file.name,
			mimeType: file.type || this._guessMimeType(file.name),
			size: file.size,
			lastModified: file.lastModified
		};
		this.properties.url = '';
		this.onExecute();
	}

	setFromInline(content, mimeType = 'text/plain') {
		this.sourceType = 'inline';
		this.sourceUrl = '';
		this.sourceData = content;
		this.sourceMeta = {
			filename: 'inline',
			mimeType: mimeType,
			size: typeof content === 'string' ? content.length : 0,
			lastModified: Date.now()
		};
		this.properties.inline = typeof content === 'string' ? content : JSON.stringify(content);
		this.onExecute();
	}

	clear() {
		this.sourceType = 'none';
		this.sourceUrl = '';
		this.sourceData = null;
		this.sourceMeta = { filename: '', mimeType: '', size: 0, lastModified: null };
		this.properties.url = '';
		this.properties.inline = '';
		this.onExecute();
	}

	hasData() {
		return this.sourceType !== 'none';
	}

	_guessMimeType(filename) {
		if (!filename) return 'application/octet-stream';
		const ext = '.' + filename.split('.').pop().toLowerCase();
		for (const [type, extensions] of Object.entries(DataExtensions)) {
			if (extensions.includes(ext)) {
				const mimes = DataMimeTypes[type];
				return mimes[0] || 'application/octet-stream';
			}
		}
		return 'application/octet-stream';
	}

	getAcceptedExtensions() { return DataExtensions[this.dataType] || []; }
	getAcceptedMimeTypes() { return DataMimeTypes[this.dataType] || []; }

	getDisplaySummary() {
		if (!this.hasData()) return 'No data';
		const name = this.sourceMeta.filename || 'Unknown';
		const size = this._formatSize(this.sourceMeta.size);
		if (this.sourceType === 'url') return `🔗 ${name}`;
		if (this.sourceType === 'file') return `📁 ${name} (${size})`;
		if (this.sourceType === 'inline') return `✏️ Inline (${size})`;
		return name;
	}

	_formatSize(bytes) {
		if (typeof DrawUtils !== 'undefined') return DrawUtils.formatSize(bytes);
		if (!bytes) return '0 B';
		const units = ['B', 'KB', 'MB', 'GB'];
		let i = 0;
		while (bytes >= 1024 && i < units.length - 1) { bytes /= 1024; i++; }
		return `${bytes.toFixed(i > 0 ? 1 : 0)} ${units[i]}`;
	}
}

// ========================================================================
// Specific Data Node Types
// ========================================================================

class TextDataNode extends DataNode {
	constructor() {
		super('Text', DataType.TEXT);
		this.size = [200, 120];
		this.properties.encoding = 'utf-8';
		this.properties.language = 'plain';
	}
	_getOutputType() { return 'Text'; }
	setFromFile(file, textContent) {
		this.sourceType = 'file';
		this.sourceUrl = '';
		this.sourceData = textContent;
		this.sourceMeta = {
			filename: file.name,
			mimeType: file.type || this._guessMimeType(file.name),
			size: file.size,
			lastModified: file.lastModified
		};
		this.properties.url = '';
		this.onExecute();
	}
	getDisplaySummary() {
		if (!this.hasData()) return 'No text';
		if (this.sourceType === 'inline' && this.sourceData) {
			const preview = String(this.sourceData).substring(0, 50);
			return preview + (this.sourceData.length > 50 ? '...' : '');
		}
		return super.getDisplaySummary();
	}
}

class DocumentDataNode extends DataNode {
	constructor() { super('Document', DataType.DOCUMENT); }
	_getOutputType() { return 'Document'; }
}

class ImageDataNode extends DataNode {
	constructor() {
		super('Image', DataType.IMAGE);
		this.size = [200, 140];
		this.imageDimensions = { width: 0, height: 0 };
	}
	_getOutputType() { return 'Image'; }
	setFromFile(file, base64Data) {
		super.setFromFile(file, base64Data);
		if (base64Data && base64Data.startsWith('data:image/')) {
			const img = new Image();
			img.onload = () => {
				this.imageDimensions = { width: img.width, height: img.height };
				this.sourceMeta.width = img.width;
				this.sourceMeta.height = img.height;
			};
			img.src = base64Data;
		}
	}
	getDisplaySummary() {
		if (!this.hasData()) return 'No image';
		const base = super.getDisplaySummary();
		if (this.imageDimensions.width && this.imageDimensions.height) {
			return `${base} (${this.imageDimensions.width}×${this.imageDimensions.height})`;
		}
		return base;
	}
}

class AudioDataNode extends DataNode {
	constructor() {
		super('Audio', DataType.AUDIO);
		this.audioDuration = 0;
	}
	_getOutputType() { return 'Audio'; }
	getDisplaySummary() {
		if (!this.hasData()) return 'No audio';
		const base = super.getDisplaySummary();
		if (this.audioDuration) {
			const mins = Math.floor(this.audioDuration / 60);
			const secs = Math.floor(this.audioDuration % 60);
			return `${base} (${mins}:${secs.toString().padStart(2, '0')})`;
		}
		return base;
	}
}

class VideoDataNode extends DataNode {
	constructor() {
		super('Video', DataType.VIDEO);
		this.videoDimensions = { width: 0, height: 0 };
		this.videoDuration = 0;
	}
	_getOutputType() { return 'Video'; }
	getDisplaySummary() {
		if (!this.hasData()) return 'No video';
		const base = super.getDisplaySummary();
		const parts = [];
		if (this.videoDimensions.width && this.videoDimensions.height) {
			parts.push(`${this.videoDimensions.width}×${this.videoDimensions.height}`);
		}
		if (this.videoDuration) {
			const mins = Math.floor(this.videoDuration / 60);
			const secs = Math.floor(this.videoDuration % 60);
			parts.push(`${mins}:${secs.toString().padStart(2, '0')}`);
		}
		return parts.length > 0 ? `${base} (${parts.join(', ')})` : base;
	}
}

class Model3DDataNode extends DataNode {
	constructor() { super('Model3D', DataType.MODEL3D); }
	_getOutputType() { return 'Model3D'; }
}

class BinaryDataNode extends DataNode {
	constructor() { super('Binary', DataType.BINARY); }
	_getOutputType() { return 'Binary'; }
	getAcceptedExtensions() { return ['*']; }
	getAcceptedMimeTypes() { return ['*/*']; }
	getDisplaySummary() {
		if (!this.hasData()) return 'No file';
		const name = this.sourceMeta.filename || 'Unknown';
		const size = this._formatSize(this.sourceMeta.size);
		const ext = name.includes('.') ? name.split('.').pop().toUpperCase() : 'BIN';
		if (this.sourceType === 'url') return `🔗 ${name}`;
		if (this.sourceType === 'file') return `📦 ${ext} (${size})`;
		return `📦 ${name}`;
	}
}

// ========================================================================
// Data Node Registry
// ========================================================================

const DataNodeTypes = {
	'Data.Text': TextDataNode,
	'Data.Document': DocumentDataNode,
	'Data.Image': ImageDataNode,
	'Data.Audio': AudioDataNode,
	'Data.Video': VideoDataNode,
	'Data.Model3D': Model3DDataNode,
	'Data.Binary': BinaryDataNode
};

// ========================================================================
// Data Nodes Extension Class
// ========================================================================

class DataNodesExtension extends SchemaGraphExtension {
	_registerNodeTypes() {
		for (const [typeName, NodeClass] of Object.entries(DataNodeTypes)) {
			this.graph.nodeTypes[typeName] = NodeClass;
		}
	}

	_setupEventListeners() {
		this.on('mouse:dblclick', (data) => this._onDoubleClick(data));
		this.on('mouse:contextmenu', (data) => this._onContextMenu(data));
		this._setupFileDrop();
	}

	_extendAPI() {
		const self = this;
		const app = this.app;
		
		app.dataNodesEnabled = this.getPref('enabled', true);
		
		app.api = app.api || {};
		app.api.dataNodes = {
			enable: () => {
				app.dataNodesEnabled = true;
				self.setPref('enabled', true);
				app.updateSchemaList?.();
				return true;
			},
			disable: () => {
				app.dataNodesEnabled = false;
				self.setPref('enabled', false);
				app.updateSchemaList?.();
				return true;
			},
			toggle: () => {
				app.dataNodesEnabled = !app.dataNodesEnabled;
				self.setPref('enabled', app.dataNodesEnabled);
				app.updateSchemaList?.();
				return app.dataNodesEnabled;
			},
			isEnabled: () => app.dataNodesEnabled,
			list: () => app.graph.nodes.filter(n => n.isDataNode),
			create: (dataType, x = 0, y = 0) => self._createDataNode(dataType, x, y),
			types: () => Object.keys(DataNodeTypes).map(t => t.replace('Data.', '').toLowerCase())
		};
		
		app.dataNodeManager = this;
	}

	_injectStyles() {
		if (document.getElementById('sg-data-node-styles')) return;
		const style = document.createElement('style');
		style.id = 'sg-data-node-styles';
		style.textContent = `
			.sg-file-drag-over {
				outline: 3px dashed var(--sg-accent-green, #92d050) !important;
				outline-offset: -3px;
			}
			.sg-context-menu-divider {
				height: 1px;
				background: var(--sg-border-color, #333);
				margin: 4px 0;
			}
		`;
		document.head.appendChild(style);
	}

	_setupFileDrop() {
		const canvas = this.app.canvas;
		
		this.onDOM(canvas, 'dragover', (e) => {
			e.preventDefault();
			e.dataTransfer.dropEffect = 'copy';
			canvas.classList.add('sg-file-drag-over');
		});
		
		this.onDOM(canvas, 'dragleave', () => {
			canvas.classList.remove('sg-file-drag-over');
		});
		
		this.onDOM(canvas, 'drop', (e) => {
			e.preventDefault();
			canvas.classList.remove('sg-file-drag-over');
			if (this.app.isLocked) return;
			
			const files = e.dataTransfer.files;
			if (files.length === 0) return;
			
			const rect = canvas.getBoundingClientRect();
			const screenX = (e.clientX - rect.left) / rect.width * canvas.width;
			const screenY = (e.clientY - rect.top) / rect.height * canvas.height;
			const [wx, wy] = this.app.screenToWorld(screenX, screenY);
			
			this._handleFileDrop(files, wx, wy);
		});
	}

	_handleFileDrop(files, wx, wy) {
		let offsetY = 0;
		for (const file of files) {
			const dataType = this._detectDataType(file);
			const node = this._createDataNode(dataType, wx, wy + offsetY);
			if (node) {
				this._loadFileIntoNode(file, node);
				offsetY += node.size[1] + 20;
			}
		}
		this.app.draw();
	}

	_createDataNode(dataType, x, y) {
		const typeName = `Data.${dataType.charAt(0).toUpperCase() + dataType.slice(1)}`;
		let NodeClass = DataNodeTypes[typeName];
		if (!NodeClass) {
			console.warn(`Node class not found: ${typeName}, using Binary`);
			NodeClass = BinaryDataNode;
		}
		
		const node = new NodeClass();
		node.pos = [x, y];
		
		// Use proper API - emits node:created event
		this.graph.addNode(node);
		
		this.app.draw();
		return node;
	}

	_loadFileIntoNode(file, node) {
		const reader = new FileReader();
		reader.onload = (e) => {
			if (node.dataType === DataType.TEXT) {
				node.setFromFile(file, e.target.result);
			} else {
				node.setFromFile(file, e.target.result);
			}
			this.app.draw();
		};
		reader.onerror = () => {
			console.error('File read error');
			this.app.showError?.(`Failed to read file: ${file.name}`);
		};
		
		if (node.dataType === DataType.TEXT) {
			reader.readAsText(file);
		} else {
			reader.readAsDataURL(file);
		}
	}

	_detectDataType(file) {
		const mimeType = file.type;
		const filename = file.name;
		
		for (const [dataType, mimes] of Object.entries(DataMimeTypes)) {
			if (dataType === DataType.BINARY) continue;
			if (mimes.some(m => mimeType.startsWith(m.split('/')[0] + '/') || mimeType === m)) {
				return dataType;
			}
		}
		
		const ext = '.' + filename.split('.').pop().toLowerCase();
		for (const [dataType, extensions] of Object.entries(DataExtensions)) {
			if (dataType === DataType.BINARY) continue;
			if (extensions.includes(ext)) return dataType;
		}
		
		return DataType.BINARY;
	}

	_onDoubleClick(data) {
		if (this.app.isLocked) return;
		
		const [wx, wy] = this.app.screenToWorld(data.coords.screenX, data.coords.screenY);
		
		for (const node of this.graph.nodes) {
			if (!node.isDataNode) continue;
			
			if (wx >= node.pos[0] && wx <= node.pos[0] + node.size[0] &&
				wy >= node.pos[1] && wy <= node.pos[1] + node.size[1]) {
				
				const headerY = node.pos[1] + 26;
				const contentY = node.pos[1] + 50;
				const footerY = node.pos[1] + node.size[1] - 20;
				
				if (wy < headerY) {
					this._toggleExpand(node);
					return;
				}
				
				if (wy >= contentY && wy < footerY) {
					if (!node.hasData()) {
						this._triggerFileInput(node);
					} else {
						this._toggleExpand(node);
					}
					return;
				}
				
				if (wy >= footerY) {
					this._triggerFileInput(node);
					return;
				}
			}
		}
	}

	_toggleExpand(node) {
		node.isExpanded = !node.isExpanded;
		if (node.isExpanded) {
			node._collapsedSize = [...node.size];
			node.size = [280, this._getExpandedHeight(node)];
		} else {
			node.size = node._collapsedSize || [200, 100];
		}
		this.app.draw();
	}

	_getExpandedHeight(node) {
		switch (node.dataType) {
			case DataType.IMAGE: return 280;
			case DataType.VIDEO: return 300;
			case DataType.TEXT: return 250;
			default: return 200;
		}
	}

	_onContextMenu(data) {
		if (this.app.isLocked) return;
		
		const [wx, wy] = this.app.screenToWorld(data.coords.screenX, data.coords.screenY);
		
		for (const node of this.graph.nodes) {
			if (!node.isDataNode) continue;
			
			if (wx >= node.pos[0] && wx <= node.pos[0] + node.size[0] &&
				wy >= node.pos[1] && wy <= node.pos[1] + node.size[1]) {
				
				data.event.preventDefault();
				this._showDataNodeContextMenu(node, data.coords);
				return true;
			}
		}
	}

	_showDataNodeContextMenu(node, coords) {
		const menu = document.getElementById('sg-contextMenu');
		if (!menu) return;
		
		const hasData = node.hasData();
		const icon = DataNodeIcons[node.dataType] || '📦';
		
		let html = `
			<div class="sg-context-menu-category">${icon} ${node.title} Node</div>
			<div class="sg-context-menu-item" data-action="load-url">🔗 Load from URL</div>
			<div class="sg-context-menu-item" data-action="load-file">📁 Load from File</div>
		`;
		
		if (node.dataType === DataType.TEXT) {
			html += `<div class="sg-context-menu-item" data-action="edit-inline">✏️ Edit Inline</div>`;
		}
		
		if (hasData) {
			html += `
				<div class="sg-context-menu-divider"></div>
				<div class="sg-context-menu-item" data-action="clear">🗑️ Clear Data</div>
			`;
		}
		
		html += `
			<div class="sg-context-menu-divider"></div>
			<div class="sg-context-menu-item" data-action="toggle-expand">
				${node.isExpanded ? '🔽 Collapse' : '🔼 Expand'}
			</div>
			<div class="sg-context-menu-item sg-context-menu-delete" data-action="delete">❌ Delete Node</div>
		`;
		
		menu.innerHTML = html;
		menu.style.left = coords.clientX + 'px';
		menu.style.top = coords.clientY + 'px';
		menu.classList.add('show');
		
		menu.querySelectorAll('.sg-context-menu-item').forEach(item => {
			item.onclick = () => {
				this._handleContextAction(item.dataset.action, node);
				menu.classList.remove('show');
			};
		});
	}

	_handleContextAction(action, node) {
		switch (action) {
			case 'load-url':
				this._showUrlInputDialog(node);
				break;
			case 'load-file':
				this._triggerFileInput(node);
				break;
			case 'edit-inline':
				this._showDataEditDialog(node);
				break;
			case 'clear':
				node.clear();
				this.app.draw();
				break;
			case 'toggle-expand':
				this._toggleExpand(node);
				break;
			case 'delete':
				this.app.removeNode(node);
				break;
		}
	}

	_showUrlInputDialog(node) {
		const url = prompt(`Enter URL for ${node.title}:`, node.properties.url || '');
		if (url !== null && url.trim()) {
			node.setFromUrl(url.trim());
			this.app.draw();
		}
	}

	_triggerFileInput(node) {
		const input = document.createElement('input');
		input.type = 'file';
		const extensions = node.getAcceptedExtensions();
		input.accept = (extensions.length === 1 && extensions[0] === '*') ? '' : extensions.join(',');
		input.onchange = (e) => {
			const file = e.target.files[0];
			if (file) this._loadFileIntoNode(file, node);
		};
		input.click();
	}

	_showDataEditDialog(node) {
		if (node.dataType !== DataType.TEXT) return;
		const currentValue = node.sourceType === 'inline' ? (node.sourceData || '') : '';
		const newValue = prompt('Edit text content:', currentValue);
		if (newValue !== null) {
			node.setFromInline(newValue, 'text/plain');
			this.app.draw();
		}
	}
}

// ========================================================================
// Custom Drawing for Data Nodes
// ========================================================================

function extendDrawNodeForData(SchemaGraphAppClass) {
	const originalDrawNode = SchemaGraphAppClass.prototype.drawNode;
	
	SchemaGraphAppClass.prototype.drawNode = function(node, colors) {
		if (node.isDataNode) {
			this._drawDataNode(node, colors);
		} else {
			originalDrawNode.call(this, node, colors);
		}
	};

	SchemaGraphAppClass.prototype._drawDataNode = function(node, colors) {
		const style = this.drawingStyleManager.getStyle();
		const x = node.pos[0], y = node.pos[1];
		const w = node.size[0], h = node.size[1];
		const radius = style.nodeCornerRadius;
		const textScale = this.getTextScale();
		const isSelected = this.isNodeSelected(node);
		const nodeColor = DataNodeColors[node.dataType] || '#46a2da';
		
		if (style.nodeShadowBlur > 0) {
			this.ctx.shadowColor = colors.nodeShadow;
			this.ctx.shadowBlur = style.nodeShadowBlur / this.camera.scale;
			this.ctx.shadowOffsetY = style.nodeShadowOffset / this.camera.scale;
		}
		
		const bodyGradient = this.ctx.createLinearGradient(x, y, x, y + h);
		bodyGradient.addColorStop(0, isSelected ? '#3a4a5a' : '#2a3a4a');
		bodyGradient.addColorStop(1, isSelected ? '#2a3a4a' : '#1a2a3a');
		this.ctx.fillStyle = bodyGradient;
		
		this.ctx.beginPath();
		this._drawRoundRect(x, y, w, h, radius);
		this.ctx.fill();
		
		this.ctx.strokeStyle = isSelected ? colors.borderHighlight : nodeColor;
		this.ctx.lineWidth = (isSelected ? 2 : 1.5) / this.camera.scale;
		this.ctx.stroke();
		
		this.ctx.shadowBlur = 0;
		this.ctx.shadowOffsetY = 0;
		
		const headerH = 26;
		const headerGradient = this.ctx.createLinearGradient(x, y, x, y + headerH);
		headerGradient.addColorStop(0, nodeColor);
		headerGradient.addColorStop(1, this._darkenColor(nodeColor, 30));
		this.ctx.fillStyle = headerGradient;
		
		this.ctx.beginPath();
		this._drawRoundRectTop(x, y, w, headerH, radius);
		this.ctx.fill();
		
		const icon = DataNodeIcons[node.dataType] || '📦';
		this.ctx.fillStyle = colors.textPrimary;
		this.ctx.font = `bold ${11 * textScale}px ${style.textFont}`;
		this.ctx.textBaseline = 'middle';
		this.ctx.textAlign = 'left';
		this.ctx.fillText(`${icon} ${node.title}`, x + 8, y + 13);
		
		const worldMouse = this.screenToWorld(this.mousePos[0], this.mousePos[1]);
		for (let i = 0; i < node.outputs.length; i++) {
			this.drawOutputSlot(node, i, x, y, w, worldMouse, colors);
		}
		
		const contentY = y + 50;
		const contentH = h - 70;
		const contentX = x + 8;
		const contentW = w - 16;
		
		if (node.isExpanded) {
			this._drawDataNodeExpanded(node, contentX, contentY, contentW, contentH, colors, textScale, style);
		} else {
			this._drawDataNodeCollapsed(node, contentX, contentY, contentW, contentH, colors, textScale, style);
		}
		
		this.ctx.fillStyle = colors.textTertiary;
		this.ctx.font = `${8 * textScale}px ${style.textFont}`;
		this.ctx.textAlign = 'center';

		let hint = null;
		if (!node.hasData()) {
		} else if (node.isExpanded) {
			hint = 'Dbl-click header to collapse';
		} else {
			hint = 'Dbl-click to expand • Right-click for options';
		}
		if (hint) this.ctx.fillText(hint, x + w / 2, y + h - 8);
	};

	SchemaGraphAppClass.prototype._drawDataNodeCollapsed = function(node, x, y, w, h, colors, textScale, style) {
		if (!node.hasData()) {
			const icon = DataNodeIcons[node.dataType];
			this.ctx.font = `${20 * textScale}px ${style.textFont}`;
			this.ctx.textAlign = 'center';
			this.ctx.textBaseline = 'middle';
			this.ctx.fillStyle = colors.textTertiary;
			this.ctx.fillText(icon, x + w / 2, y + h / 2 - 8);
			this.ctx.font = `${9 * textScale}px ${style.textFont}`;
			this.ctx.fillText('Double-click to select file', x + w / 2, y + h / 2 + 12);
			return;
		}

		const summary = node.getDisplaySummary();
		if (typeof MediaPreviewRenderer !== 'undefined') {
			MediaPreviewRenderer.drawCollapsedPreview(
				this.ctx, node.dataType, summary, x, y, w, h,
				{ textScale, font: style.textFont, colors }
			);
		} else {
			this.ctx.fillStyle = colors.textSecondary;
			this.ctx.font = `${10 * textScale}px ${style.textFont}`;
			this.ctx.textAlign = 'center';
			this.ctx.textBaseline = 'middle';
			this.ctx.fillText(summary, x + w / 2, y + h / 2);
		}
	};

	SchemaGraphAppClass.prototype._drawDataNodeExpanded = function(node, x, y, w, h, colors, textScale, style) {
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

		const opts = { textScale, font: style.textFont, colors, onLoad: () => this.draw() };

		if (typeof MediaPreviewRenderer !== 'undefined') {
			switch (node.dataType) {
				case DataType.IMAGE:
					const imgSrc = node.sourceData || node.sourceUrl;
					if (imgSrc) {
						MediaPreviewRenderer.drawCachedImage(this.ctx, imgSrc, innerX, innerY, innerW, innerH, { ...opts, contain: true });
					} else {
						MediaPreviewRenderer.drawMediaPlaceholder(this.ctx, 'image', innerX, innerY, innerW, innerH, opts);
					}
					break;
				case DataType.VIDEO:
					const vidSrc = node.sourceData || node.sourceUrl;
					if (vidSrc) {
						MediaPreviewRenderer.drawCachedVideoFrame(this.ctx, vidSrc, innerX, innerY, innerW, innerH, opts);
					} else {
						MediaPreviewRenderer.drawMediaPlaceholder(this.ctx, 'video', innerX, innerY, innerW, innerH, opts);
					}
					break;
				case DataType.TEXT:
					MediaPreviewRenderer.drawTextPreview(this.ctx, node.sourceData || '', innerX, innerY, innerW, innerH, opts);
					break;
				default:
					MediaPreviewRenderer.drawDetailedInfoPreview(this.ctx, node.dataType, {
						filename: node.sourceMeta?.filename,
						size: node.sourceMeta?.size,
						mimeType: node.sourceMeta?.mimeType
					}, innerX, innerY, innerW, innerH, opts);
			}
		}

		this.ctx.restore();
	};
}

// ========================================================================
// Extend Context Menu for Data Nodes
// ========================================================================

function extendContextMenuForData(SchemaGraphAppClass) {
	const originalShowContextMenu = SchemaGraphAppClass.prototype.showContextMenu;
	
	SchemaGraphAppClass.prototype.showContextMenu = function(node, wx, wy, coords) {
		if (node) return originalShowContextMenu.call(this, node, wx, wy, coords);
		
		const contextMenu = document.getElementById('sg-contextMenu');
		let html = '';
		
		if (this.nativeTypesEnabled) {
			html += '<div class="sg-context-menu-category">Native Types</div>';
			const natives = ['Native.String', 'Native.Integer', 'Native.Boolean', 'Native.Float', 'Native.List', 'Native.Dict'];
			for (const nativeType of natives) {
				const name = nativeType.split('.')[1];
				html += `<div class="sg-context-menu-item" data-type="${nativeType}">${name}</div>`;
			}
		}
		
		if (this.dataNodesEnabled) {
			html += '<div class="sg-context-menu-category">Data Sources</div>';
			for (const typeName of Object.keys(DataNodeTypes)) {
				const displayName = typeName.split('.')[1];
				const dataType = displayName.toLowerCase();
				const icon = DataNodeIcons[dataType] || '📦';
				html += `<div class="sg-context-menu-item" data-type="${typeName}">${icon} ${displayName}</div>`;
			}
		}
		
		for (const schemaName of Object.keys(this.graph.schemas)) {
			if (!this.graph.isSchemaEnabled(schemaName)) continue;
			
			const schemaTypes = [];
			const schemaInfo = this.graph.schemas[schemaName];
			let rootNodeType = null;
			
			for (const type in this.graph.nodeTypes) {
				if (type.indexOf(schemaName + '.') === 0) {
					schemaTypes.push(type);
					if (schemaInfo.rootType && type === schemaName + '.' + schemaInfo.rootType) {
						rootNodeType = type;
					}
				}
			}
			
			if (schemaTypes.length > 0) {
				html += `<div class="sg-context-menu-category">${schemaName} Schema</div>`;
				if (rootNodeType) {
					const name = rootNodeType.split('.')[1];
					html += `<div class="sg-context-menu-item" data-type="${rootNodeType}" style="font-weight: bold; color: var(--sg-accent-orange);">★ ${name} (Root)</div>`;
				}
				for (const schemaType of schemaTypes) {
					if (schemaType !== rootNodeType) {
						const name = schemaType.split('.')[1];
						html += `<div class="sg-context-menu-item" data-type="${schemaType}">${name}</div>`;
					}
				}
			}
		}
		
		if (!html) {
			html = '<div class="sg-context-menu-category" style="color: var(--sg-text-tertiary);">No node types available</div>';
		}
		
		contextMenu.innerHTML = html;
		contextMenu.style.left = coords.clientX + 'px';
		contextMenu.style.top = coords.clientY + 'px';
		contextMenu.classList.add('show');
		contextMenu.dataset.worldX = wx;
		contextMenu.dataset.worldY = wy;
		
		const items = contextMenu.querySelectorAll('.sg-context-menu-item[data-type]');
		for (const item of items) {
			item.addEventListener('click', () => {
				const type = item.getAttribute('data-type');
				const posX = parseFloat(contextMenu.dataset.worldX);
				const posY = parseFloat(contextMenu.dataset.worldY);
				
				if (type.startsWith('Data.')) {
					const NodeClass = DataNodeTypes[type];
					if (NodeClass) {
						const node = new NodeClass();
						node.pos = [posX - 90, posY - 40];
						// Use proper API
						this.graph.addNode(node);
					}
				} else {
					const node = this.graph.createNode(type);
					node.pos = [posX - 90, posY - 40];
				}
				
				contextMenu.classList.remove('show');
				this.draw();
			});
		}
	};
}

// ========================================================================
// Extend Schema List UI
// ========================================================================

function extendSchemaListForData(SchemaGraphAppClass) {
	const originalUpdateSchemaList = SchemaGraphAppClass.prototype.updateSchemaList;
	
	SchemaGraphAppClass.prototype.updateSchemaList = function() {
		const listEl = document.getElementById('sg-schemaList');
		if (!listEl) return originalUpdateSchemaList?.call(this);
		
		let html = '';
		
		const isNativeEnabled = this.nativeTypesEnabled !== false;
		html += `
			<div class="sg-schema-item">
				<div>
					<span class="sg-schema-item-name">Native Types</span>
					<span class="sg-schema-item-count">(6 types)</span>
				</div>
				<button class="sg-schema-toggle-btn ${isNativeEnabled ? 'enabled' : 'disabled'}" id="sg-nativeTypesToggle">
					${isNativeEnabled ? '👁 Visible' : '🚫 Hidden'}
				</button>
			</div>
		`;
		
		const isDataEnabled = this.dataNodesEnabled !== false;
		html += `
			<div class="sg-schema-item">
				<div>
					<span class="sg-schema-item-name">Data Sources</span>
					<span class="sg-schema-item-count">(7 types)</span>
				</div>
				<button class="sg-schema-toggle-btn ${isDataEnabled ? 'enabled' : 'disabled'}" id="sg-dataNodesToggle">
					${isDataEnabled ? '👁 Visible' : '🚫 Hidden'}
				</button>
			</div>
		`;
		
		const schemas = Object.keys(this.graph.schemas);
		if (schemas.length > 0) {
			html += '<div style="border-top: 1px solid var(--sg-border-color); margin: 8px 0;"></div>';
		}
		
		for (const schemaName of schemas) {
			let nodeCount = 0, typeCount = 0;
			for (const node of this.graph.nodes) {
				if (node.schemaName === schemaName) nodeCount++;
			}
			for (const type in this.graph.nodeTypes) {
				if (type.indexOf(schemaName + '.') === 0) typeCount++;
			}
			
			const isEnabled = this.graph.isSchemaEnabled(schemaName);
			html += `
				<div class="sg-schema-item">
					<div>
						<span class="sg-schema-item-name">${schemaName}</span>
						<span class="sg-schema-item-count">(${typeCount} types, ${nodeCount} nodes)</span>
					</div>
					<div style="display: flex; gap: 4px;">
						<button class="sg-schema-toggle-btn ${isEnabled ? 'enabled' : 'disabled'}" data-schema="${schemaName}">
							${isEnabled ? '👁 Enabled' : '🚫 Disabled'}
						</button>
						<button class="sg-schema-remove-btn" data-schema="${schemaName}">Remove</button>
					</div>
				</div>
			`;
		}
		
		if (schemas.length === 0) {
			html += '<div style="color: var(--sg-text-tertiary); font-size: 11px; padding: 8px 0;">No schemas registered</div>';
		}
		
		listEl.innerHTML = html;
		
		document.getElementById('sg-nativeTypesToggle')?.addEventListener('click', (e) => {
			e.stopPropagation();
			this.nativeTypesEnabled = !this.nativeTypesEnabled;
			localStorage.setItem('schemagraph-native-types-enabled', String(this.nativeTypesEnabled));
			this.updateSchemaList();
		});
		
		document.getElementById('sg-dataNodesToggle')?.addEventListener('click', (e) => {
			e.stopPropagation();
			this.dataNodesEnabled = !this.dataNodesEnabled;
			localStorage.setItem('schemagraph-data-nodes-enabled', String(this.dataNodesEnabled));
			this.updateSchemaList();
		});
		
		listEl.querySelectorAll('.sg-schema-toggle-btn[data-schema]').forEach(btn => {
			btn.addEventListener('click', (e) => {
				e.stopPropagation();
				this.graph.toggleSchema(btn.getAttribute('data-schema'));
				this.updateSchemaList();
			});
		});
		
		listEl.querySelectorAll('.sg-schema-remove-btn').forEach(btn => {
			btn.addEventListener('click', () => this.openSchemaRemovalDialog?.());
		});
	};
}

// ========================================================================
// Serialization Extension
// ========================================================================

function extendSerializationForDataNodes(SchemaGraphClass) {
	const originalSerialize = SchemaGraphClass.prototype.serialize;
	
	SchemaGraphClass.prototype.serialize = function(includeCamera = false, camera = null) {
		const data = originalSerialize ? originalSerialize.call(this, includeCamera, camera) : { version: '1.1', nodes: [], links: [] };
		
		for (let i = 0; i < this.nodes.length; i++) {
			const node = this.nodes[i];
			if (node.isDataNode && data.nodes[i]) {
				data.nodes[i].isDataNode = true;
				data.nodes[i].dataType = node.dataType;
				data.nodes[i].sourceType = node.sourceType;
				data.nodes[i].sourceUrl = node.sourceUrl || '';
				data.nodes[i].sourceData = node.sourceData || null;
				data.nodes[i].sourceMeta = JSON.parse(JSON.stringify(node.sourceMeta || {}));
				data.nodes[i].isExpanded = node.isExpanded || false;
				
				if (node.imageDimensions) data.nodes[i].imageDimensions = { ...node.imageDimensions };
				if (node.audioDuration) data.nodes[i].audioDuration = node.audioDuration;
				if (node.videoDimensions) data.nodes[i].videoDimensions = { ...node.videoDimensions };
				if (node.videoDuration) data.nodes[i].videoDuration = node.videoDuration;
			}
		}
		
		return data;
	};
}

// ========================================================================
// AUTO-INITIALIZATION
// ========================================================================

if (typeof SchemaGraphApp !== 'undefined') {
	extendDrawNodeForData(SchemaGraphApp);
	extendContextMenuForData(SchemaGraphApp);
	extendSchemaListForData(SchemaGraphApp);
	
	if (typeof extensionRegistry !== 'undefined') {
		extensionRegistry.register('dataNodes', DataNodesExtension);
	} else {
		const originalSetup = SchemaGraphApp.prototype.setupEventListeners;
		SchemaGraphApp.prototype.setupEventListeners = function() {
			originalSetup.call(this);
			this.dataNodeManager = new DataNodesExtension(this);
		};
	}
	
	console.log('✨ SchemaGraph Data Nodes extension loaded');
}

if (typeof SchemaGraph !== 'undefined') {
	extendSerializationForDataNodes(SchemaGraph);
}

// ========================================================================
// Exports
// ========================================================================

if (typeof module !== 'undefined' && module.exports) {
	module.exports = {
		DataType, DataMimeTypes, DataExtensions,
		DataNode, TextDataNode, DocumentDataNode, ImageDataNode,
		AudioDataNode, VideoDataNode, Model3DDataNode, BinaryDataNode,
		DataNodeTypes, DataNodeIcons, DataNodeColors,
		DataNodesExtension, extendDrawNodeForData, extendContextMenuForData
	};
}
