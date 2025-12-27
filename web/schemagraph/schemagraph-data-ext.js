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

// ========================================================================
// Base DataNode Class
// ========================================================================

class DataNode extends Node {
	constructor(title, dataType) {
		super(title);
		this.isDataNode = true;
		this.dataType = dataType;
		this.isExpanded = false;
		
		// Data storage
		this.sourceType = 'none'; // 'none', 'url', 'file', 'inline'
		this.sourceUrl = '';
		this.sourceData = null; // Base64 or raw content
		this.sourceMeta = {
			filename: '',
			mimeType: '',
			size: 0,
			lastModified: null
		};
		
		// Output
		this.addOutput('data', this._getOutputType());
		this.addOutput('meta', 'Object');
		
		this.size = [200, 100];
		this.minSize = [180, 90];
		this.maxSize = [400, 500];
		
		this.properties = {
			url: '',
			inline: ''
		};
	}

	_getOutputType() {
		return this.dataType.charAt(0).toUpperCase() + this.dataType.slice(1);
	}

	onExecute() {
		// Build output data object
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

	getAcceptedExtensions() {
		return DataExtensions[this.dataType] || [];
	}

	getAcceptedMimeTypes() {
		return DataMimeTypes[this.dataType] || [];
	}

	getDisplaySummary() {
		if (!this.hasData()) return 'No data';
		
		const name = this.sourceMeta.filename || 'Unknown';
		const size = this._formatSize(this.sourceMeta.size);
		
		if (this.sourceType === 'url') {
			return `🔗 ${name}`;
		} else if (this.sourceType === 'file') {
			return `📁 ${name} (${size})`;
		} else if (this.sourceType === 'inline') {
			return `✏️ Inline (${size})`;
		}
		return name;
	}

	_formatSize(bytes) {
		if (!bytes) return '0 B';
		const units = ['B', 'KB', 'MB', 'GB'];
		let i = 0;
		while (bytes >= 1024 && i < units.length - 1) {
			bytes /= 1024;
			i++;
		}
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
		
		// Text-specific properties
		this.properties.encoding = 'utf-8';
		this.properties.language = 'plain'; // plain, markdown, json, etc.
	}

	_getOutputType() { return 'Text'; }

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
	constructor() {
		super('Document', DataType.DOCUMENT);
		this.size = [200, 100];
	}

	_getOutputType() { return 'Document'; }
}

class ImageDataNode extends DataNode {
	constructor() {
		super('Image', DataType.IMAGE);
		this.size = [200, 140];
		
		// Image-specific metadata
		this.imageDimensions = { width: 0, height: 0 };
	}

	_getOutputType() { return 'Image'; }

	setFromFile(file, base64Data) {
		super.setFromFile(file, base64Data);
		
		// Try to get image dimensions
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
		this.size = [200, 100];
		
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
		this.size = [200, 100];
		
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
	constructor() {
		super('Model3D', DataType.MODEL3D);
		this.size = [200, 100];
	}

	_getOutputType() { return 'Model3D'; }
}

class BinaryDataNode extends DataNode {
	constructor() {
		super('Binary', DataType.BINARY);
		this.size = [200, 100];
	}

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

const DataNodeIcons = {
	[DataType.TEXT]: '📝',
	[DataType.DOCUMENT]: '📄',
	[DataType.IMAGE]: '🖼️',
	[DataType.AUDIO]: '🔊',
	[DataType.VIDEO]: '🎬',
	[DataType.MODEL3D]: '🧊',
	[DataType.BINARY]: '📦'
};

const DataNodeColors = {
	[DataType.TEXT]: '#4a9eff',
	[DataType.DOCUMENT]: '#ff9f4a',
	[DataType.IMAGE]: '#00d4aa',
	[DataType.AUDIO]: '#ffd700',
	[DataType.VIDEO]: '#ff4757',
	[DataType.MODEL3D]: '#00bcd4',
	[DataType.BINARY]: '#9370db'
};

// ========================================================================
// Data Node Manager - Handles file drops, dialogs, etc.
// ========================================================================

class DataNodeManager {
	constructor(app) {
		this.app = app;
		this.graph = app.graph;
		this.eventBus = app.eventBus;
		
		this._registerNodeTypes();
		this._setupEventListeners();
		this._setupFileDrop();
		this._injectStyles();
		
		// Load preference
		const saved = localStorage.getItem('schemagraph-data-nodes-enabled');
		this.app.dataNodesEnabled = saved !== 'false';
	}

	_registerNodeTypes() {
		for (const [typeName, NodeClass] of Object.entries(DataNodeTypes)) {
			this.graph.nodeTypes[typeName] = NodeClass;
		}
	}

	_setupEventListeners() {
		// Double-click to edit/expand data nodes
		this.eventBus.on('mouse:dblclick', (data) => this._onDoubleClick(data));
		
		// Context menu for data nodes
		this.eventBus.on('mouse:contextmenu', (data) => this._onContextMenu(data));
	}

	_setupFileDrop() {
		const canvas = this.app.canvas;
		
		canvas.addEventListener('dragover', (e) => {
			e.preventDefault();
			e.dataTransfer.dropEffect = 'copy';
			canvas.classList.add('sg-file-drag-over');
		});
		
		canvas.addEventListener('dragleave', (e) => {
			canvas.classList.remove('sg-file-drag-over');
		});
		
		canvas.addEventListener('drop', (e) => {
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
			const nodeType = `Data.${dataType.charAt(0).toUpperCase() + dataType.slice(1)}`;
			let NodeClass = DataNodeTypes[nodeType];
			
			if (!NodeClass) {
				console.warn(`Node class not found: ${nodeType}, using Binary`);
				NodeClass = BinaryDataNode;
			}
			
			const node = new NodeClass();
			node.pos = [wx, wy + offsetY];
			
			if (this.graph._last_node_id === undefined) this.graph._last_node_id = 1;
			node.id = this.graph._last_node_id++;
			node.graph = this.graph;
			this.graph.nodes.push(node);
			this.graph._nodes_by_id[node.id] = node;
			
			this._loadFileIntoNode(file, node);
			offsetY += node.size[1] + 20;
			this.eventBus.emit('node:created', { type: nodeType, nodeId: node.id });
		}
		this.app.draw();
	}

	_loadFileIntoNode(file, node) {
		const reader = new FileReader();
		
		reader.onload = (e) => {
			const base64 = e.target.result;
			node.setFromFile(file, base64);
			this.app.draw();
		};
		
		reader.onerror = (e) => {
			console.error('File read error:', e);
			this.app.showError(`Failed to read file: ${file.name}`);
		};
		
		// Read as data URL (base64)
		reader.readAsDataURL(file);
	}

	_detectDataType(file) {
		const mimeType = file.type;
		const filename = file.name;
		
		// Check by MIME type first
		for (const [dataType, mimes] of Object.entries(DataMimeTypes)) {
			if (dataType === DataType.BINARY) continue;
			if (mimes.some(m => mimeType.startsWith(m.split('/')[0] + '/') || mimeType === m)) {
				return dataType;
			}
		}
		
		// Fall back to extension
		const ext = '.' + filename.split('.').pop().toLowerCase();
		for (const [dataType, extensions] of Object.entries(DataExtensions)) {
			if (dataType === DataType.BINARY) continue;
			if (extensions.includes(ext)) {
				return dataType;
			}
		}
		
		// Default to binary (instead of null)
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
				
				// Header: toggle expand
				if (wy < headerY) {
					node.isExpanded = !node.isExpanded;
					if (node.isExpanded) {
						node._collapsedSize = [...node.size];
						node.size = [280, this._getExpandedHeight(node)];
					} else {
						node.size = node._collapsedSize || [200, 100];
					}
					this.app.draw();
					return;
				}
				
				// Content area
				if (wy >= contentY && wy < footerY) {
					if (!node.hasData()) {
						this._triggerFileInput(node);
						return;
					}
					if (node.dataType === 'text') {
						this._showDataEditDialog(node);
					} else {
						node.isExpanded = !node.isExpanded;
						if (node.isExpanded) {
							node._collapsedSize = [...node.size];
							node.size = [280, this._getExpandedHeight(node)];
						} else {
							node.size = node._collapsedSize || [200, 100];
						}
						this.app.draw();
					}
					return;
				}
				
				// Footer: open file picker
				if (wy >= footerY) {
					this._triggerFileInput(node);
					return;
				}
			}
		}
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
		const icon = DataNodeIcons[node.dataType];
		
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
		
		// Setup handlers
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
				node.isExpanded = !node.isExpanded;
				if (node.isExpanded) {
					node._collapsedSize = [...node.size];
					node.size = [280, this._getExpandedHeight(node)];
				} else {
					node.size = node._collapsedSize || [200, 100];
				}
				this.app.draw();
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

	_triggerFileInput(node, callback) {
		const input = document.createElement('input');
		input.type = 'file';
		
		const extensions = node.getAcceptedExtensions();
		input.accept = (extensions.length === 1 && extensions[0] === '*') ? '' : extensions.join(',');
		
		input.onchange = (e) => {
			const file = e.target.files[0];
			if (file) {
				this._loadFileIntoNode(file, node);
				if (callback) callback(file);
			}
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
		const x = node.pos[0];
		const y = node.pos[1];
		const w = node.size[0];
		const h = node.size[1];
		const radius = style.nodeCornerRadius;
		const textScale = this.getTextScale();
		
		const isSelected = this.isNodeSelected(node);
		const nodeColor = DataNodeColors[node.dataType] || '#46a2da';
		
		// Shadow
		if (style.nodeShadowBlur > 0) {
			this.ctx.shadowColor = colors.nodeShadow;
			this.ctx.shadowBlur = style.nodeShadowBlur / this.camera.scale;
			this.ctx.shadowOffsetY = style.nodeShadowOffset / this.camera.scale;
		}
		
		// Body gradient
		const bodyGradient = this.ctx.createLinearGradient(x, y, x, y + h);
		bodyGradient.addColorStop(0, isSelected ? '#3a4a5a' : '#2a3a4a');
		bodyGradient.addColorStop(1, isSelected ? '#2a3a4a' : '#1a2a3a');
		this.ctx.fillStyle = bodyGradient;
		
		this.ctx.beginPath();
		this._drawRoundRect(x, y, w, h, radius);
		this.ctx.fill();
		
		// Border
		this.ctx.strokeStyle = isSelected ? colors.borderHighlight : nodeColor;
		this.ctx.lineWidth = (isSelected ? 2 : 1.5) / this.camera.scale;
		this.ctx.stroke();
		
		this.ctx.shadowBlur = 0;
		this.ctx.shadowOffsetY = 0;
		
		// Header
		const headerH = 26;
		const headerGradient = this.ctx.createLinearGradient(x, y, x, y + headerH);
		headerGradient.addColorStop(0, nodeColor);
		headerGradient.addColorStop(1, this._darkenColor(nodeColor, 30));
		this.ctx.fillStyle = headerGradient;
		
		this.ctx.beginPath();
		this._drawRoundRectTop(x, y, w, headerH, radius);
		this.ctx.fill();
		
		// Title with icon
		const icon = DataNodeIcons[node.dataType] || '📦';
		this.ctx.fillStyle = colors.textPrimary;
		this.ctx.font = `bold ${11 * textScale}px ${style.textFont}`;
		this.ctx.textBaseline = 'middle';
		this.ctx.textAlign = 'left';
		this.ctx.fillText(`${icon} ${node.title}`, x + 8, y + 13);
		
		// Draw slots
		const worldMouse = this.screenToWorld(this.mousePos[0], this.mousePos[1]);
		for (let i = 0; i < node.outputs.length; i++) {
			this.drawOutputSlot(node, i, x, y, w, worldMouse, colors);
		}
		
		// Content area
		const contentY = y + 50;
		const contentH = h - 70;
		const contentX = x + 8;
		const contentW = w - 16;
		
		if (node.isExpanded) {
			this._drawDataNodeExpanded(node, contentX, contentY, contentW, contentH, colors, textScale, style);
		} else {
			this._drawDataNodeCollapsed(node, contentX, contentY, contentW, contentH, colors, textScale, style);
		}
		
		// Footer hint
		this.ctx.fillStyle = colors.textTertiary;
		this.ctx.font = `${8 * textScale}px ${style.textFont}`;
		this.ctx.textAlign = 'center';

		let hint = null;
		if (!node.hasData()) {
			// hint = 'Drop file or double-click';
		} else if (node.isExpanded) {
			hint = 'Dbl-click header to collapse';
		} else {
			hint = 'Dbl-click to expand • Right-click for options';
		}
		if (hint != null) {
			this.ctx.fillText(hint, x + w / 2, y + h - 8);
		}
	};

	SchemaGraphAppClass.prototype._drawDataNodeCollapsed = function(node, x, y, w, h, colors, textScale, style) {
		if (!node.hasData()) {
			// No data prompt
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
		MediaPreviewRenderer.drawCollapsedPreview(
			this.ctx, node.dataType, summary, x, y, w, h,
			{ textScale, font: style.textFont, colors }
		);
	};

	SchemaGraphAppClass.prototype._drawDataNodeExpanded = function(node, x, y, w, h, colors, textScale, style) {
		const padding = 6;
		const innerX = x + padding, innerY = y + padding;
		const innerW = w - padding * 2, innerH = h - padding * 2;

		MediaPreviewRenderer.drawExpandedBackground(this.ctx, x, y, w, h, { scale: this.camera.scale });

		this.ctx.save();
		this.ctx.beginPath();
		this.ctx.roundRect(innerX, innerY, innerW, innerH, 4);
		this.ctx.clip();

		const opts = { textScale, font: style.textFont, colors, onLoad: () => this.draw() };

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

			case DataType.DOCUMENT:
			case DataType.BINARY:
			case DataType.MODEL3D:
				MediaPreviewRenderer.drawDetailedInfoPreview(this.ctx, node.dataType, {
					filename: node.sourceMeta?.filename,
					size: node.sourceMeta?.size,
					mimeType: node.sourceMeta?.mimeType
				}, innerX, innerY, innerW, innerH, opts);
				break;

			default:
				MediaPreviewRenderer.drawMediaPlaceholder(this.ctx, node.dataType, innerX, innerY, innerW, innerH, {
					...opts, label: node.getDisplaySummary()
				});
		}

		this.ctx.restore();
	};

	SchemaGraphAppClass.prototype._drawImagePreview = function(node, x, y, w, h, textScale, style) {
		const centerX = x + w / 2;
		const centerY = y + h / 2;
		
		if (node.sourceData && node.sourceData.startsWith('data:image/')) {
			// Would need cached image loading for actual display
			// For now, show placeholder with dimensions
			this.ctx.fillStyle = DataNodeColors[DataType.IMAGE];
			this.ctx.font = `${24 * textScale}px ${style.textFont}`;
			this.ctx.textAlign = 'center';
			this.ctx.textBaseline = 'middle';
			this.ctx.fillText('🖼️', centerX, centerY - 15);
			
			this.ctx.font = `${10 * textScale}px ${style.textFont}`;
			this.ctx.fillStyle = '#888';
			const dimText = node.imageDimensions.width 
				? `${node.imageDimensions.width} × ${node.imageDimensions.height}`
				: node.sourceMeta.filename;
			this.ctx.fillText(dimText, centerX, centerY + 15);
		} else if (node.sourceUrl) {
			this.ctx.fillStyle = DataNodeColors[DataType.IMAGE];
			this.ctx.font = `${24 * textScale}px ${style.textFont}`;
			this.ctx.textAlign = 'center';
			this.ctx.textBaseline = 'middle';
			this.ctx.fillText('🔗', centerX, centerY - 15);
			
			this.ctx.font = `${9 * textScale}px ${style.textFont}`;
			this.ctx.fillStyle = '#888';
			const urlText = node.sourceUrl.length > 35 ? node.sourceUrl.slice(0, 35) + '...' : node.sourceUrl;
			this.ctx.fillText(urlText, centerX, centerY + 15);
		} else {
			this.ctx.fillStyle = '#555';
			this.ctx.font = `${24 * textScale}px ${style.textFont}`;
			this.ctx.textAlign = 'center';
			this.ctx.textBaseline = 'middle';
			this.ctx.fillText('🖼️', centerX, centerY);
		}
	};

	SchemaGraphAppClass.prototype._drawTextPreviewInData = function(node, x, y, w, h, colors, textScale, style) {
		if (!node.hasData()) {
			this.ctx.fillStyle = '#555';
			this.ctx.font = `${12 * textScale}px ${style.textFont}`;
			this.ctx.textAlign = 'center';
			this.ctx.textBaseline = 'middle';
			this.ctx.fillText('No text content', x + w / 2, y + h / 2);
			return;
		}
		
		const text = node.sourceData || '';
		const lines = text.split('\n');
		const lineHeight = 11 * textScale;
		const maxLines = Math.floor(h / lineHeight);
		
		this.ctx.font = `${9 * textScale}px 'Courier New', monospace`;
		this.ctx.textAlign = 'left';
		this.ctx.textBaseline = 'top';
		this.ctx.fillStyle = colors.textSecondary;
		
		for (let i = 0; i < Math.min(lines.length, maxLines); i++) {
			let line = lines[i];
			if (this.ctx.measureText(line).width > w) {
				while (line.length > 3 && this.ctx.measureText(line + '...').width > w) {
					line = line.slice(0, -1);
				}
				line += '...';
			}
			this.ctx.fillText(line, x, y + i * lineHeight);
		}
		
		if (lines.length > maxLines) {
			this.ctx.fillStyle = colors.textTertiary;
			this.ctx.fillText('...', x, y + maxLines * lineHeight);
		}
	};

	SchemaGraphAppClass.prototype._drawGenericPreview = function(node, x, y, w, h, colors, textScale, style) {
		const centerX = x + w / 2;
		const centerY = y + h / 2;
		const icon = DataNodeIcons[node.dataType];
		
		this.ctx.fillStyle = DataNodeColors[node.dataType];
		this.ctx.font = `${28 * textScale}px ${style.textFont}`;
		this.ctx.textAlign = 'center';
		this.ctx.textBaseline = 'middle';
		this.ctx.fillText(icon, centerX, centerY - 15);
		
		this.ctx.font = `${10 * textScale}px ${style.textFont}`;
		this.ctx.fillStyle = node.hasData() ? colors.textSecondary : colors.textTertiary;
		this.ctx.fillText(node.getDisplaySummary(), centerX, centerY + 20);
	};

	SchemaGraphAppClass.prototype._drawBinaryPreview = function(node, x, y, w, h, colors, textScale, style) {
		const centerX = x + w / 2;
		const centerY = y + h / 2;
		
		this.ctx.font = `${28 * textScale}px ${style.textFont}`;
		this.ctx.textAlign = 'center';
		this.ctx.textBaseline = 'middle';
		this.ctx.fillStyle = DataNodeColors[DataType.BINARY];
		this.ctx.fillText('📦', centerX, centerY - 20);
		
		this.ctx.font = `${10 * textScale}px ${style.textFont}`;
		this.ctx.fillStyle = colors.textPrimary;
		this.ctx.fillText(node.sourceMeta?.filename || 'Unknown file', centerX, centerY + 10);
		
		this.ctx.font = `${9 * textScale}px ${style.textFont}`;
		this.ctx.fillStyle = colors.textSecondary;
		const size = node._formatSize(node.sourceMeta?.size || 0);
		const mimeType = node.sourceMeta?.mimeType || 'application/octet-stream';
		this.ctx.fillText(`${size} • ${mimeType}`, centerX, centerY + 28);
	};

	SchemaGraphAppClass.prototype._drawRoundRect = function(x, y, w, h, r) {
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

	SchemaGraphAppClass.prototype._drawRoundRectTop = function(x, y, w, h, r) {
		this.ctx.moveTo(x + r, y);
		this.ctx.lineTo(x + w - r, y);
		this.ctx.quadraticCurveTo(x + w, y, x + w, y + r);
		this.ctx.lineTo(x + w, y + h);
		this.ctx.lineTo(x, y + h);
		this.ctx.lineTo(x, y + r);
		this.ctx.quadraticCurveTo(x, y, x + r, y);
		this.ctx.closePath();
	};

	SchemaGraphAppClass.prototype._darkenColor = function(hex, amount) {
		const num = parseInt(hex.replace('#', ''), 16);
		const r = Math.max(0, (num >> 16) - amount);
		const g = Math.max(0, ((num >> 8) & 0x00FF) - amount);
		const b = Math.max(0, (num & 0x0000FF) - amount);
		return '#' + ((r << 16) | (g << 8) | b).toString(16).padStart(6, '0');
	};
}

// ========================================================================
// Extend Context Menu for Data Nodes
// ========================================================================

function extendContextMenuForData(SchemaGraphAppClass) {
	const originalShowContextMenu = SchemaGraphAppClass.prototype.showContextMenu;
	
	SchemaGraphAppClass.prototype.showContextMenu = function(node, wx, wy, coords) {
		if (node) {
			return originalShowContextMenu.call(this, node, wx, wy, coords);
		}
		
		const contextMenu = document.getElementById('sg-contextMenu');
		let html = '';
		
		// Native types (if enabled)
		if (this.nativeTypesEnabled) {
			html += '<div class="sg-context-menu-category">Native Types</div>';
			const natives = ['Native.String', 'Native.Integer', 'Native.Boolean', 'Native.Float', 'Native.List', 'Native.Dict'];
			for (const nativeType of natives) {
				const name = nativeType.split('.')[1];
				html += `<div class="sg-context-menu-item" data-type="${nativeType}">${name}</div>`;
			}
		}
		
		// Data nodes (if enabled)
		if (this.dataNodesEnabled) {
			html += '<div class="sg-context-menu-category">Data Sources</div>';
			for (const [typeName, NodeClass] of Object.entries(DataNodeTypes)) {
				const displayName = typeName.split('.')[1];
				const dataType = displayName.toLowerCase();
				const icon = DataNodeIcons[dataType] || '📦';
				html += `<div class="sg-context-menu-item" data-type="${typeName}">${icon} ${displayName}</div>`;
			}
		}
		
		// Schema types
		const registeredSchemas = Object.keys(this.graph.schemas);
		for (const schemaName of registeredSchemas) {
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
				
				// Handle Data nodes specially
				if (type.startsWith('Data.')) {
					const NodeClass = DataNodeTypes[type];
					if (NodeClass) {
						const node = new NodeClass();
						node.pos = [posX - 90, posY - 40];
						
						if (this.graph._last_node_id === undefined) {
							this.graph._last_node_id = 1;
						}
						node.id = this.graph._last_node_id++;
						node.graph = this.graph;
						this.graph.nodes.push(node);
						this.graph._nodes_by_id[node.id] = node;
						
						this.eventBus.emit('node:created', { type, nodeId: node.id });
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
// Extend API and Schema List
// ========================================================================

function extendSchemaGraphAppWithData(SchemaGraphAppClass) {
	const originalCreateAPI = SchemaGraphAppClass.prototype._createAPI;
	
	SchemaGraphAppClass.prototype._createAPI = function() {
		const api = originalCreateAPI.call(this);
		
		api.dataNodes = {
			enable: () => {
				this.dataNodesEnabled = true;
				localStorage.setItem('schemagraph-data-nodes-enabled', 'true');
				this.updateSchemaList();
				return true;
			},
			
			disable: () => {
				this.dataNodesEnabled = false;
				localStorage.setItem('schemagraph-data-nodes-enabled', 'false');
				this.updateSchemaList();
				return true;
			},
			
			toggle: () => {
				this.dataNodesEnabled = !this.dataNodesEnabled;
				localStorage.setItem('schemagraph-data-nodes-enabled', String(this.dataNodesEnabled));
				this.updateSchemaList();
				return this.dataNodesEnabled;
			},
			
			isEnabled: () => this.dataNodesEnabled,
			
			list: () => this.graph.nodes.filter(n => n.isDataNode),
			
			create: (dataType, x = 0, y = 0) => {
				const typeName = `Data.${dataType.charAt(0).toUpperCase() + dataType.slice(1)}`;
				const NodeClass = DataNodeTypes[typeName];
				
				if (!NodeClass) {
					this.showError(`Unknown data type: ${dataType}`);
					return null;
				}
				
				const node = new NodeClass();
				node.pos = [x, y];
				
				if (this.graph._last_node_id === undefined) {
					this.graph._last_node_id = 1;
				}
				node.id = this.graph._last_node_id++;
				node.graph = this.graph;
				this.graph.nodes.push(node);
				this.graph._nodes_by_id[node.id] = node;
				
				this.eventBus.emit('node:created', { type: typeName, nodeId: node.id });
				this.draw();
				
				return node;
			},
			
			types: () => Object.keys(DataNodeTypes).map(t => t.replace('Data.', '').toLowerCase())
		};
		
		return api;
	};

	// Extend updateSchemaList to include data nodes toggle
	const originalUpdateSchemaList = SchemaGraphAppClass.prototype.updateSchemaList;
	
	SchemaGraphAppClass.prototype.updateSchemaList = function() {
		const listEl = document.getElementById('sg-schemaList');
		if (!listEl) {
			return originalUpdateSchemaList?.call(this);
		}
		
		let html = '';
		
		// Native Types toggle
		const isNativeEnabled = this.nativeTypesEnabled !== false;
		html += `
			<div class="sg-schema-item">
				<div>
					<span class="sg-schema-item-name">Native Types</span>
					<span class="sg-schema-item-count">(6 types)</span>
				</div>
				<button class="sg-schema-toggle-btn ${isNativeEnabled ? 'enabled' : 'disabled'}" 
						id="sg-nativeTypesToggle" 
						title="${isNativeEnabled ? 'Hide native types' : 'Show native types'}">
					${isNativeEnabled ? '👁️ Visible' : '🚫 Hidden'}
				</button>
			</div>
		`;
		
		// Data Sources toggle
		const isDataEnabled = this.dataNodesEnabled !== false;
		html += `
			<div class="sg-schema-item">
				<div>
					<span class="sg-schema-item-name">Data Sources</span>
					<span class="sg-schema-item-count">(6 types)</span>
				</div>
				<button class="sg-schema-toggle-btn ${isDataEnabled ? 'enabled' : 'disabled'}" 
						id="sg-dataNodesToggle" 
						title="${isDataEnabled ? 'Hide data nodes' : 'Show data nodes'}">
					${isDataEnabled ? '👁️ Visible' : '🚫 Hidden'}
				</button>
			</div>
		`;
		
		// Separator if there are schemas
		const schemas = Object.keys(this.graph.schemas);
		if (schemas.length > 0) {
			html += '<div style="border-top: 1px solid var(--sg-border-color); margin: 8px 0;"></div>';
		}
		
		// Schema entries
		for (const schemaName of schemas) {
			let nodeCount = 0;
			for (const node of this.graph.nodes) {
				if (node.schemaName === schemaName) nodeCount++;
			}
			
			let typeCount = 0;
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
						<button class="sg-schema-toggle-btn ${isEnabled ? 'enabled' : 'disabled'}" 
								data-schema="${schemaName}" 
								title="${isEnabled ? 'Disable schema' : 'Enable schema'}">
							${isEnabled ? '👁️ Enabled' : '🚫 Disabled'}
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
		
		// Native types toggle handler
		const nativeToggle = document.getElementById('sg-nativeTypesToggle');
		nativeToggle?.addEventListener('click', (e) => {
			e.stopPropagation();
			this.nativeTypesEnabled = !this.nativeTypesEnabled;
			localStorage.setItem('schemagraph-native-types-enabled', String(this.nativeTypesEnabled));
			this.updateSchemaList();
			this.eventBus.emit('ui:update', { 
				id: 'status', 
				content: `Native types ${this.nativeTypesEnabled ? 'shown' : 'hidden'}` 
			});
		});
		
		// Data nodes toggle handler
		const dataToggle = document.getElementById('sg-dataNodesToggle');
		dataToggle?.addEventListener('click', (e) => {
			e.stopPropagation();
			this.dataNodesEnabled = !this.dataNodesEnabled;
			localStorage.setItem('schemagraph-data-nodes-enabled', String(this.dataNodesEnabled));
			this.updateSchemaList();
			this.eventBus.emit('ui:update', { 
				id: 'status', 
				content: `Data sources ${this.dataNodesEnabled ? 'shown' : 'hidden'}` 
			});
		});
		
		// Schema toggle handlers
		const toggleButtons = listEl.querySelectorAll('.sg-schema-toggle-btn[data-schema]');
		for (const button of toggleButtons) {
			button.addEventListener('click', (e) => {
				e.stopPropagation();
				const schemaName = button.getAttribute('data-schema');
				this.graph.toggleSchema(schemaName);
				this.updateSchemaList();
			});
		}
		
		// Remove handlers
		const removeButtons = listEl.querySelectorAll('.sg-schema-remove-btn');
		for (const button of removeButtons) {
			button.addEventListener('click', () => {
				this.openSchemaRemovalDialog();
			});
		}
	};
}

// ========================================================================
// SERIALIZATION EXTENSION
// Extends SchemaGraph serialize/deserialize to handle Native, Data, and Preview nodes
// ========================================================================

function extendSerializationForAllNodes(SchemaGraphClass) {
	const originalSerialize = SchemaGraphClass.prototype.serialize;
	
	SchemaGraphClass.prototype.serialize = function(includeCamera = false, camera = null) {
		const data = {
			version: '1.1',
			nodes: [],
			links: []
		};
		
		for (const node of this.nodes) {
			const nodeData = {
				id: node.id,
				type: node.title,
				pos: node.pos.slice(),
				size: node.size.slice(),
				properties: JSON.parse(JSON.stringify(node.properties || {}))
			};
			
			// Native nodes
			if (node.isNative) {
				nodeData.isNative = true;
				nodeData.nativeType = node.title; // String, Integer, etc.
			}
			
			// Schema nodes
			if (node.schemaName) {
				nodeData.schemaName = node.schemaName;
			}
			if (node.modelName) {
				nodeData.modelName = node.modelName;
			}
			if (node.isRootType) {
				nodeData.isRootType = true;
			}
			
			// Native inputs (for schema nodes with editable fields)
			if (node.nativeInputs && Object.keys(node.nativeInputs).length > 0) {
				nodeData.nativeInputs = JSON.parse(JSON.stringify(node.nativeInputs));
			}
			
			// Multi inputs
			if (node.multiInputs && Object.keys(node.multiInputs).length > 0) {
				nodeData.multiInputs = JSON.parse(JSON.stringify(node.multiInputs));
			}
			
			// Data nodes
			if (node.isDataNode) {
				nodeData.isDataNode = true;
				nodeData.dataType = node.dataType;
				nodeData.sourceType = node.sourceType;
				nodeData.sourceUrl = node.sourceUrl || '';
				nodeData.sourceData = node.sourceData || null;
				nodeData.sourceMeta = JSON.parse(JSON.stringify(node.sourceMeta || {}));
				nodeData.isExpanded = node.isExpanded || false;
				
				// Type-specific data
				if (node.imageDimensions) {
					nodeData.imageDimensions = { ...node.imageDimensions };
				}
				if (node.audioDuration) {
					nodeData.audioDuration = node.audioDuration;
				}
				if (node.videoDimensions) {
					nodeData.videoDimensions = { ...node.videoDimensions };
				}
				if (node.videoDuration) {
					nodeData.videoDuration = node.videoDuration;
				}
			}
			
			// Preview nodes
			if (node.isPreviewNode) {
				nodeData.isPreviewNode = true;
				nodeData.previewType = node.previewType;
				nodeData.isExpanded = node.isExpanded || false;
				
				// Store original edge info for proper restoration
				if (node._originalEdgeInfo) {
					nodeData._originalEdgeInfo = JSON.parse(JSON.stringify(node._originalEdgeInfo));
				}
			}
			
			// Workflow nodes
			if (node.isWorkflowNode) {
				nodeData.isWorkflowNode = true;
				nodeData.workflowType = node.workflowType;
				nodeData.workflowIndex = node.workflowIndex;
				if (node.fieldRoles) {
					nodeData.fieldRoles = JSON.parse(JSON.stringify(node.fieldRoles));
				}
				if (node.constantFields) {
					nodeData.constantFields = JSON.parse(JSON.stringify(node.constantFields));
				}
				if (node.multiInputSlots) {
					nodeData.multiInputSlots = JSON.parse(JSON.stringify(node.multiInputSlots));
				}
				if (node.multiOutputSlots) {
					nodeData.multiOutputSlots = JSON.parse(JSON.stringify(node.multiOutputSlots));
				}
				if (node.extra && Object.keys(node.extra).length > 0) {
					nodeData.extra = JSON.parse(JSON.stringify(node.extra));
				}
			}
			
			// Common optional properties
			if (node.color) {
				nodeData.color = node.color;
			}
			if (node.workflowData) {
				nodeData.workflowData = JSON.parse(JSON.stringify(node.workflowData));
			}
			
			data.nodes.push(nodeData);
		}
		
		// Serialize links
		for (const linkId in this.links) {
			if (this.links.hasOwnProperty(linkId)) {
				const link = this.links[linkId];
				const linkData = {
					id: link.id,
					origin_id: link.origin_id,
					origin_slot: link.origin_slot,
					target_id: link.target_id,
					target_slot: link.target_slot,
					type: link.type
				};
				
				if (link.data) {
					linkData.data = JSON.parse(JSON.stringify(link.data));
				}
				if (link.extra) {
					linkData.extra = JSON.parse(JSON.stringify(link.extra));
				}
				if (link.workflowData) {
					linkData.workflowData = JSON.parse(JSON.stringify(link.workflowData));
				}
				if (link.conditionType) {
					linkData.conditionType = link.conditionType;
				}
				if (link.conditionInfo) {
					linkData.conditionInfo = JSON.parse(JSON.stringify(link.conditionInfo));
				}
				if (link.isConditional) {
					linkData.isConditional = link.isConditional;
				}
				if (link.conditionLabel) {
					linkData.conditionLabel = link.conditionLabel;
				}
				
				data.links.push(linkData);
			}
		}
		
		if (includeCamera && camera) {
			data.camera = {
				x: camera.x,
				y: camera.y,
				scale: camera.scale
			};
		}
		
		return data;
	};

	const originalDeserialize = SchemaGraphClass.prototype.deserialize;
	
	SchemaGraphClass.prototype.deserialize = function(data, restoreCamera = false, camera = null) {
		this.nodes = [];
		this.links = {};
		this._nodes_by_id = {};
		this.last_link_id = 0;
		
		if (!data || !data.nodes) {
			throw new Error('Invalid graph data');
		}
		
		// First pass: create all nodes
		for (const nodeData of data.nodes) {
			let node = null;
			
			// Determine node type and create appropriate instance
			if (nodeData.isDataNode) {
				// Data node
				const typeName = `Data.${nodeData.dataType.charAt(0).toUpperCase() + nodeData.dataType.slice(1)}`;
				const NodeClass = DataNodeTypes[typeName];
				
				if (NodeClass) {
					node = new NodeClass();
					node.sourceType = nodeData.sourceType || 'none';
					node.sourceUrl = nodeData.sourceUrl || '';
					node.sourceData = nodeData.sourceData || null;
					node.sourceMeta = nodeData.sourceMeta || {};
					node.isExpanded = nodeData.isExpanded || false;
					node.properties = nodeData.properties || {};
					
					// Type-specific restoration
					if (nodeData.imageDimensions) {
						node.imageDimensions = { ...nodeData.imageDimensions };
					}
					if (nodeData.audioDuration) {
						node.audioDuration = nodeData.audioDuration;
					}
					if (nodeData.videoDimensions) {
						node.videoDimensions = { ...nodeData.videoDimensions };
					}
					if (nodeData.videoDuration) {
						node.videoDuration = nodeData.videoDuration;
					}
				} else {
					console.warn('Data node type not found:', typeName);
					continue;
				}
			} else if (nodeData.isPreviewNode) {
				// Preview node
				if (typeof PreviewNode !== 'undefined') {
					node = new PreviewNode();
					node.previewType = nodeData.previewType || 'auto';
					node.isExpanded = nodeData.isExpanded || false;
					node.properties = nodeData.properties || {};
					
					if (nodeData._originalEdgeInfo) {
						node._originalEdgeInfo = JSON.parse(JSON.stringify(nodeData._originalEdgeInfo));
					}
				} else {
					console.warn('PreviewNode class not found - skipping preview node');
					continue;
				}
			} else if (nodeData.isNative) {
				// Native node
				const nodeTypeKey = 'Native.' + (nodeData.nativeType || nodeData.type);
				
				if (this.nodeTypes[nodeTypeKey]) {
					node = new (this.nodeTypes[nodeTypeKey])();
					node.properties = JSON.parse(JSON.stringify(nodeData.properties || {}));
				} else {
					console.warn('Native node type not found:', nodeTypeKey);
					continue;
				}
			} else if (nodeData.isWorkflowNode && nodeData.schemaName) {
				// Workflow node - needs special handling with factory
				const nodeTypeKey = `${nodeData.schemaName}.${nodeData.modelName}`;
				
				if (this.nodeTypes[nodeTypeKey]) {
					node = new (this.nodeTypes[nodeTypeKey])();
					node.workflowType = nodeData.workflowType;
					node.workflowIndex = nodeData.workflowIndex;
					
					if (nodeData.fieldRoles) {
						node.fieldRoles = JSON.parse(JSON.stringify(nodeData.fieldRoles));
					}
					if (nodeData.constantFields) {
						node.constantFields = JSON.parse(JSON.stringify(nodeData.constantFields));
					}
					if (nodeData.extra) {
						node.extra = JSON.parse(JSON.stringify(nodeData.extra));
					}
				} else {
					console.warn('Workflow node type not found:', nodeTypeKey);
					continue;
				}
			} else if (nodeData.schemaName && nodeData.modelName) {
				// Schema node
				const nodeTypeKey = nodeData.schemaName + '.' + nodeData.modelName;
				
				if (this.nodeTypes[nodeTypeKey]) {
					node = new (this.nodeTypes[nodeTypeKey])();
				} else {
					console.warn('Schema node type not found:', nodeTypeKey);
					continue;
				}
			} else {
				// Try direct type lookup
				const nodeTypeKey = nodeData.type;
				
				if (this.nodeTypes[nodeTypeKey]) {
					node = new (this.nodeTypes[nodeTypeKey])();
				} else {
					console.warn('Node type not found:', nodeTypeKey);
					continue;
				}
			}
			
			if (!node) continue;
			
			// Common properties
			node.id = nodeData.id;
			node.pos = nodeData.pos.slice();
			node.size = nodeData.size.slice();
			
			if (nodeData.isRootType) {
				node.isRootType = true;
			}
			if (nodeData.color) {
				node.color = nodeData.color;
			}
			if (nodeData.workflowData) {
				node.workflowData = JSON.parse(JSON.stringify(nodeData.workflowData));
			}
			
			// Restore native inputs
			if (nodeData.nativeInputs) {
				node.nativeInputs = JSON.parse(JSON.stringify(nodeData.nativeInputs));
			}
			
			// Restore multi inputs structure (links will be connected later)
			if (nodeData.multiInputs) {
				node.multiInputs = {};
				for (const key in nodeData.multiInputs) {
					node.multiInputs[key] = {
						type: nodeData.multiInputs[key].type,
						links: [] // Will be populated when deserializing links
					};
				}
			}
			
			// Restore multi slots for workflow nodes
			if (nodeData.multiInputSlots) {
				node.multiInputSlots = JSON.parse(JSON.stringify(nodeData.multiInputSlots));
			}
			if (nodeData.multiOutputSlots) {
				node.multiOutputSlots = JSON.parse(JSON.stringify(nodeData.multiOutputSlots));
			}
			
			this.nodes.push(node);
			this._nodes_by_id[node.id] = node;
			node.graph = this;
		}
		
		// Second pass: restore links
		if (data.links) {
			for (const linkData of data.links) {
				const originNode = this._nodes_by_id[linkData.origin_id];
				const targetNode = this._nodes_by_id[linkData.target_id];
				
				if (!originNode || !targetNode) {
					console.warn('Link skipped - missing node:', linkData.origin_id, '->', linkData.target_id);
					continue;
				}
				
				const link = new Link(
					linkData.id,
					linkData.origin_id,
					linkData.origin_slot,
					linkData.target_id,
					linkData.target_slot,
					linkData.type
				);
				
				// Restore link metadata
				if (linkData.data) {
					link.data = JSON.parse(JSON.stringify(linkData.data));
				}
				if (linkData.extra) {
					link.extra = JSON.parse(JSON.stringify(linkData.extra));
				}
				if (linkData.workflowData) {
					link.workflowData = JSON.parse(JSON.stringify(linkData.workflowData));
				}
				if (linkData.conditionType) {
					link.conditionType = linkData.conditionType;
				}
				if (linkData.conditionInfo) {
					link.conditionInfo = JSON.parse(JSON.stringify(linkData.conditionInfo));
				}
				if (linkData.isConditional) {
					link.isConditional = linkData.isConditional;
				}
				if (linkData.conditionLabel) {
					link.conditionLabel = linkData.conditionLabel;
				}
				
				this.links[linkData.id] = link;
				
				// Connect to origin output
				if (originNode.outputs[linkData.origin_slot]) {
					originNode.outputs[linkData.origin_slot].links.push(linkData.id);
				}
				
				// Connect to target input
				if (targetNode.multiInputs && targetNode.multiInputs[linkData.target_slot]) {
					targetNode.multiInputs[linkData.target_slot].links.push(linkData.id);
				} else if (targetNode.inputs[linkData.target_slot]) {
					targetNode.inputs[linkData.target_slot].link = linkData.id;
				}
				
				if (linkData.id > this.last_link_id) {
					this.last_link_id = linkData.id;
				}
			}
		}
		
		// Restore camera
		if (restoreCamera && data.camera && camera) {
			camera.x = data.camera.x;
			camera.y = data.camera.y;
			camera.scale = data.camera.scale;
		}
		
		// Execute all nodes to update their outputs
		for (const node of this.nodes) {
			if (node.onExecute) {
				node.onExecute();
			}
		}
		
		this.eventBus.emit('graph:deserialized', { nodeCount: this.nodes.length });
		return true;
	};
}

// ========================================================================
// AUTO-INITIALIZATION
// ========================================================================

function initializeDataNodesExtension(SchemaGraphAppClass) {
	extendDrawNodeForData(SchemaGraphAppClass);
	extendContextMenuForData(SchemaGraphAppClass);
	extendSchemaGraphAppWithData(SchemaGraphAppClass);
	
	// Hook into app initialization
	const originalSetupEventListeners = SchemaGraphAppClass.prototype.setupEventListeners;
	SchemaGraphAppClass.prototype.setupEventListeners = function() {
		originalSetupEventListeners.call(this);
		
		// Initialize data node manager
		this.dataNodeManager = new DataNodeManager(this);
		
		// Load native types preference
		const savedNative = localStorage.getItem('schemagraph-native-types-enabled');
		this.nativeTypesEnabled = savedNative !== 'false';
	};
	
	console.log('✨ SchemaGraph Data Nodes extension loaded');
}

// Extend serialization on SchemaGraph class
if (typeof SchemaGraph !== 'undefined') {
	extendSerializationForAllNodes(SchemaGraph);
}

if (typeof SchemaGraphApp !== 'undefined') {
	initializeDataNodesExtension(SchemaGraphApp);
}

// Export for module usage
if (typeof module !== 'undefined' && module.exports) {
	module.exports = {
		DataType,
		DataMimeTypes,
		DataExtensions,
		DataNode,
		TextDataNode,
		DocumentDataNode,
		ImageDataNode,
		AudioDataNode,
		VideoDataNode,
		Model3DDataNode,
		DataNodeTypes,
		DataNodeIcons,
		DataNodeColors,
		DataNodeManager,
		initializeDataNodesExtension,
		extendSerializationForAllNodes
	};
}
