// ========================================================================
// SCHEMAGRAPH INTERACTIVE EXTENSION
// Adds buttons and file drop zones to nodes
// ========================================================================

const ButtonPosition = Object.freeze({
	HEADER_RIGHT: 'header-right',
	FOOTER: 'footer',
	FOOTER_LEFT: 'footer-left',
	FOOTER_RIGHT: 'footer-right',
	CONTENT: 'content',
	CUSTOM: 'custom'
});

const DropZoneArea = Object.freeze({
	FULL: 'full',
	CONTENT: 'content',
	CUSTOM: 'custom'
});

// ========================================================================
// InteractiveExtension Class
// ========================================================================

class InteractiveExtension extends SchemaGraphExtension {
	constructor(app) {
		super(app);
		this._buttonBounds = new Map(); // nodeId -> [{ id, bounds }]
		this._dropZones = new Map();    // nodeId -> dropZone config
		this._activeDropNode = null;
		this._hoveredButton = null;
	}

	_registerNodeTypes() {
		// No new node types
	}

	_setupEventListeners() {
		this.on('mouse:move', (data) => this._onMouseMove(data));
		this.on('mouse:down', (data) => this._onMouseDown(data));
		this._setupFileDrop();
	}

	_extendAPI() {
		const self = this;
		
		this.app.api = this.app.api || {};
		this.app.api.interactive = {
			// Button API
			addButton: (node, config) => self.addButton(node, config),
			removeButton: (node, buttonId) => self.removeButton(node, buttonId),
			getButtons: (node) => node._buttons || [],
			
			// Drop zone API
			setDropZone: (node, config) => self.setDropZone(node, config),
			removeDropZone: (node) => self.removeDropZone(node),
			getDropZone: (node) => node._dropZone || null,
			
			// Constants
			ButtonPosition,
			DropZoneArea
		};
		
		this.app.interactiveManager = this;
	}

	_injectStyles() {
		if (document.getElementById('sg-interactive-styles')) return;
		const style = document.createElement('style');
		style.id = 'sg-interactive-styles';
		style.textContent = `
			.sg-node-drop-active {
				outline: 2px dashed var(--sg-accent-green, #92d050) !important;
				outline-offset: -2px;
			}
		`;
		document.head.appendChild(style);
	}

	// ================================================================
	// Button Management
	// ================================================================

	addButton(node, config) {
		if (!node || !config) return false;
		
		const button = {
			id: config.id || `btn_${Date.now()}`,
			label: config.label || '',
			icon: config.icon || '',
			position: config.position || ButtonPosition.FOOTER,
			callback: config.callback || (() => {}),
			width: config.width || 60,
			height: config.height || 20,
			x: config.x,
			y: config.y,
			style: {
				bg: config.bg || 'rgba(255,255,255,0.1)',
				bgHover: config.bgHover || 'rgba(255,255,255,0.2)',
				text: config.text || '#fff',
				border: config.border || 'rgba(255,255,255,0.2)',
				radius: config.radius ?? 4,
				...config.style
			},
			enabled: config.enabled !== false,
			visible: config.visible !== false
		};
		
		if (!node._buttons) node._buttons = [];
		
		// Remove existing button with same id
		const existingIdx = node._buttons.findIndex(b => b.id === button.id);
		if (existingIdx !== -1) {
			node._buttons[existingIdx] = button;
		} else {
			node._buttons.push(button);
		}
		
		this.app.draw();
		return button.id;
	}

	removeButton(node, buttonId) {
		if (!node?._buttons) return false;
		
		const idx = node._buttons.findIndex(b => b.id === buttonId);
		if (idx !== -1) {
			node._buttons.splice(idx, 1);
			this.app.draw();
			return true;
		}
		return false;
	}

	// ================================================================
	// Drop Zone Management
	// ================================================================

	setDropZone(node, config) {
		if (!node || !config) return false;
		
		node._dropZone = {
			accept: config.accept || '*',  // mime types or extensions
			area: config.area || DropZoneArea.CONTENT,
			callback: config.callback || (() => {}),
			label: config.label || 'Drop file here',
			x: config.x,
			y: config.y,
			width: config.width,
			height: config.height,
			enabled: config.enabled !== false
		};
		
		this._dropZones.set(node.id, node._dropZone);
		return true;
	}

	removeDropZone(node) {
		if (!node) return false;
		delete node._dropZone;
		this._dropZones.delete(node.id);
		return true;
	}

	// ================================================================
	// Event Handling
	// ================================================================

	_onMouseMove(data) {
		if (this.app.isLocked) return;
		
		const [wx, wy] = this.app.screenToWorld(data.coords.screenX, data.coords.screenY);
		
		let newHovered = null;
		
		for (const node of this.graph.nodes) {
			if (!node._buttons?.length) continue;
			
			const bounds = this._buttonBounds.get(node.id) || [];
			for (const { id, bounds: b } of bounds) {
				if (wx >= b.x && wx <= b.x + b.w && wy >= b.y && wy <= b.y + b.h) {
					const btn = node._buttons.find(bt => bt.id === id);
					if (btn?.enabled && btn?.visible) {
						newHovered = { nodeId: node.id, buttonId: id };
						break;
					}
				}
			}
			if (newHovered) break;
		}
		
		if (this._hoveredButton?.buttonId !== newHovered?.buttonId ||
		    this._hoveredButton?.nodeId !== newHovered?.nodeId) {
			this._hoveredButton = newHovered;
			this.app.canvas.style.cursor = newHovered ? 'pointer' : '';
			this.app.draw();
		}
	}

	_onMouseDown(data) {
		if (data.button !== 0 || this.app.isLocked) return;
		
		const [wx, wy] = this.app.screenToWorld(data.coords.screenX, data.coords.screenY);
		
		for (const node of this.graph.nodes) {
			if (!node._buttons?.length) continue;
			
			const bounds = this._buttonBounds.get(node.id) || [];
			for (const { id, bounds: b } of bounds) {
				if (wx >= b.x && wx <= b.x + b.w && wy >= b.y && wy <= b.y + b.h) {
					const btn = node._buttons.find(bt => bt.id === id);
					if (btn?.enabled && btn?.visible && btn.callback) {
						data.event.preventDefault();
						data.event.stopPropagation();
						btn.callback(node, data.event, btn);
						return true;
					}
				}
			}
		}
	}

	_setupFileDrop() {
		const canvas = this.app.canvas;
		
		this.onDOM(canvas, 'dragover', (e) => {
			if (this.app.isLocked) return;
			
			const rect = canvas.getBoundingClientRect();
			const screenX = (e.clientX - rect.left) / rect.width * canvas.width;
			const screenY = (e.clientY - rect.top) / rect.height * canvas.height;
			const [wx, wy] = this.app.screenToWorld(screenX, screenY);
			
			const node = this._findDropTargetNode(wx, wy);
			
			if (node && node._dropZone?.enabled) {
				e.preventDefault();
				e.dataTransfer.dropEffect = 'copy';
				
				if (this._activeDropNode !== node) {
					this._activeDropNode = node;
					this.app.draw();
				}
			} else if (this._activeDropNode) {
				this._activeDropNode = null;
				this.app.draw();
			}
		});
		
		this.onDOM(canvas, 'dragleave', (e) => {
			// Check if actually leaving canvas
			const rect = canvas.getBoundingClientRect();
			if (e.clientX < rect.left || e.clientX > rect.right ||
			    e.clientY < rect.top || e.clientY > rect.bottom) {
				if (this._activeDropNode) {
					this._activeDropNode = null;
					this.app.draw();
				}
			}
		});
		
		this.onDOM(canvas, 'drop', (e) => {
			if (this.app.isLocked) return;
			
			const rect = canvas.getBoundingClientRect();
			const screenX = (e.clientX - rect.left) / rect.width * canvas.width;
			const screenY = (e.clientY - rect.top) / rect.height * canvas.height;
			const [wx, wy] = this.app.screenToWorld(screenX, screenY);
			
			const node = this._findDropTargetNode(wx, wy);
			
			if (node && node._dropZone?.enabled) {
				e.preventDefault();
				e.stopPropagation();
				
				const files = Array.from(e.dataTransfer.files);
				const dropZone = node._dropZone;
				
				// Filter files by accept
				const filteredFiles = this._filterFilesByAccept(files, dropZone.accept);
				
				if (filteredFiles.length > 0 && dropZone.callback) {
					dropZone.callback(node, filteredFiles, e);
				}
			}
			
			this._activeDropNode = null;
			this.app.draw();
		});
	}

	_findDropTargetNode(wx, wy) {
		for (const node of this.graph.nodes) {
			if (!node._dropZone?.enabled) continue;
			
			const bounds = this._getDropZoneBounds(node);
			if (wx >= bounds.x && wx <= bounds.x + bounds.w &&
			    wy >= bounds.y && wy <= bounds.y + bounds.h) {
				return node;
			}
		}
		return null;
	}

	_getDropZoneBounds(node) {
		const dz = node._dropZone;
		const x = node.pos[0], y = node.pos[1];
		const w = node.size[0], h = node.size[1];
		
		if (dz.area === DropZoneArea.FULL) {
			return { x, y, w, h };
		} else if (dz.area === DropZoneArea.CONTENT) {
			// Content area (below header, above footer)
			return { x: x + 4, y: y + 30, w: w - 8, h: h - 50 };
		} else if (dz.area === DropZoneArea.CUSTOM) {
			return {
				x: x + (dz.x || 0),
				y: y + (dz.y || 0),
				w: dz.width || w,
				h: dz.height || h
			};
		}
		return { x, y, w, h };
	}

	_filterFilesByAccept(files, accept) {
		if (!accept || accept === '*' || accept === '*/*') return files;
		
		const acceptList = Array.isArray(accept) ? accept : accept.split(',').map(s => s.trim());
		
		return files.filter(file => {
			for (const acc of acceptList) {
				// Extension match
				if (acc.startsWith('.')) {
					if (file.name.toLowerCase().endsWith(acc.toLowerCase())) return true;
				}
				// MIME type match
				else if (acc.includes('/')) {
					if (acc.endsWith('/*')) {
						const prefix = acc.slice(0, -1);
						if (file.type.startsWith(prefix)) return true;
					} else if (file.type === acc) {
						return true;
					}
				}
			}
			return false;
		});
	}

	// ================================================================
	// Rendering
	// ================================================================

	drawNodeButtons(node, colors) {
		if (!node._buttons?.length) return;
		
		const ctx = this.app.ctx;
		const style = this.app.drawingStyleManager.getStyle();
		const textScale = this.app.getTextScale();
		const x = node.pos[0], y = node.pos[1];
		const w = node.size[0], h = node.size[1];
		
		const nodeBounds = [];
		
		for (const btn of node._buttons) {
			if (!btn.visible) continue;
			
			const bounds = this._calculateButtonBounds(btn, x, y, w, h);
			nodeBounds.push({ id: btn.id, bounds });
			
			const isHovered = this._hoveredButton?.nodeId === node.id && 
			                  this._hoveredButton?.buttonId === btn.id;
			
			// Background
			ctx.fillStyle = isHovered ? btn.style.bgHover : btn.style.bg;
			ctx.beginPath();
			ctx.roundRect(bounds.x, bounds.y, bounds.w, bounds.h, btn.style.radius);
			ctx.fill();
			
			// Border
			if (btn.style.border) {
				ctx.strokeStyle = btn.style.border;
				ctx.lineWidth = 1 / this.app.camera.scale;
				ctx.stroke();
			}
			
			// Text/Icon
			ctx.fillStyle = btn.enabled ? btn.style.text : 'rgba(255,255,255,0.3)';
			ctx.font = `${10 * textScale}px ${style.textFont}`;
			ctx.textAlign = 'center';
			ctx.textBaseline = 'middle';
			
			const label = btn.icon ? `${btn.icon} ${btn.label}` : btn.label;
			ctx.fillText(label, bounds.x + bounds.w / 2, bounds.y + bounds.h / 2);
		}
		
		this._buttonBounds.set(node.id, nodeBounds);
	}

	_calculateButtonBounds(btn, nodeX, nodeY, nodeW, nodeH) {
		let x, y;
		const w = btn.width;
		const h = btn.height;
		const padding = 6;
		
		switch (btn.position) {
			case ButtonPosition.HEADER_RIGHT:
				x = nodeX + nodeW - w - padding;
				y = nodeY + 3;
				break;
			case ButtonPosition.FOOTER:
				x = nodeX + (nodeW - w) / 2;
				y = nodeY + nodeH - h - padding;
				break;
			case ButtonPosition.FOOTER_LEFT:
				x = nodeX + padding;
				y = nodeY + nodeH - h - padding;
				break;
			case ButtonPosition.FOOTER_RIGHT:
				x = nodeX + nodeW - w - padding;
				y = nodeY + nodeH - h - padding;
				break;
			case ButtonPosition.CONTENT:
				x = nodeX + (nodeW - w) / 2;
				y = nodeY + 30 + (nodeH - 60 - h) / 2;
				break;
			case ButtonPosition.CUSTOM:
			default:
				x = nodeX + (btn.x ?? padding);
				y = nodeY + (btn.y ?? padding);
				break;
		}
		
		return { x, y, w, h };
	}

	drawDropZoneHighlight(node, colors) {
		if (!node._dropZone?.enabled) return;
		if (this._activeDropNode !== node) return;
		
		const ctx = this.app.ctx;
		const bounds = this._getDropZoneBounds(node);
		const style = this.app.drawingStyleManager.getStyle();
		const textScale = this.app.getTextScale();
		
		// Highlight overlay
		ctx.fillStyle = 'rgba(146, 208, 80, 0.15)';
		ctx.beginPath();
		ctx.roundRect(bounds.x, bounds.y, bounds.w, bounds.h, 4);
		ctx.fill();
		
		// Dashed border
		ctx.strokeStyle = '#92d050';
		ctx.lineWidth = 2 / this.app.camera.scale;
		ctx.setLineDash([6 / this.app.camera.scale, 4 / this.app.camera.scale]);
		ctx.stroke();
		ctx.setLineDash([]);
		
		// Label
		if (node._dropZone.label) {
			ctx.fillStyle = '#92d050';
			ctx.font = `bold ${11 * textScale}px ${style.textFont}`;
			ctx.textAlign = 'center';
			ctx.textBaseline = 'middle';
			ctx.fillText(node._dropZone.label, bounds.x + bounds.w / 2, bounds.y + bounds.h / 2);
		}
	}
}

// ========================================================================
// Extend drawNode to include buttons and drop zones
// ========================================================================

function extendDrawNodeForInteractive(SchemaGraphAppClass) {
	const originalDrawNode = SchemaGraphAppClass.prototype.drawNode;
	
	SchemaGraphAppClass.prototype.drawNode = function(node, colors) {
		// Draw the node normally
		originalDrawNode.call(this, node, colors);
		
		// Draw interactive elements
		if (this.interactiveManager) {
			this.interactiveManager.drawDropZoneHighlight(node, colors);
			this.interactiveManager.drawNodeButtons(node, colors);
		}
	};
}

// ========================================================================
// AUTO-INITIALIZATION
// ========================================================================

if (typeof SchemaGraphApp !== 'undefined') {
	extendDrawNodeForInteractive(SchemaGraphApp);
	
	if (typeof extensionRegistry !== 'undefined') {
		extensionRegistry.register('interactive', InteractiveExtension);
	} else {
		const originalSetup = SchemaGraphApp.prototype.setupEventListeners;
		SchemaGraphApp.prototype.setupEventListeners = function() {
			originalSetup.call(this);
			this.interactiveManager = new InteractiveExtension(this);
		};
	}
	
	console.log('✨ SchemaGraph Interactive extension loaded');
}

// ========================================================================
// EXPORTS
// ========================================================================

if (typeof module !== 'undefined' && module.exports) {
	module.exports = {
		ButtonPosition, DropZoneArea, InteractiveExtension,
		extendDrawNodeForInteractive
	};
}

if (typeof window !== 'undefined') {
	window.ButtonPosition = ButtonPosition;
	window.DropZoneArea = DropZoneArea;
	window.InteractiveExtension = InteractiveExtension;
}
