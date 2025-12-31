// ========================================================================
// SCHEMAGRAPH NODE DECORATORS EXTENSION
// Parses @node_button and @node_dropzone decorators from schema
// and automatically applies them to created nodes
// ========================================================================

const DecoratorType = Object.freeze({
	BUTTON: 'node_button',
	DROPZONE: 'node_dropzone'
});

// ========================================================================
// Decorator Parser
// ========================================================================

class NodeDecoratorParser {
	constructor() {
		this.decorators = {}; // modelName -> { buttons: [], dropzone: null }
	}

	parse(code) {
		this.decorators = {};
		
		const lines = code.split('\n');
		let pendingDecorators = [];
		
		for (let i = 0; i < lines.length; i++) {
			const line = lines[i];
			const trimmed = line.trim();
			
			// Check for decorator
			const buttonMatch = trimmed.match(/^@node_button\s*\((.+)\)\s*$/);
			if (buttonMatch) {
				const config = this._parseDecoratorArgs(buttonMatch[1]);
				if (config) {
					pendingDecorators.push({ type: DecoratorType.BUTTON, config });
				}
				continue;
			}
			
			const dropzoneMatch = trimmed.match(/^@node_dropzone\s*\((.+)\)\s*$/);
			if (dropzoneMatch) {
				const config = this._parseDecoratorArgs(dropzoneMatch[1]);
				if (config) {
					pendingDecorators.push({ type: DecoratorType.DROPZONE, config });
				}
				continue;
			}
			
			// Check for class definition
			const classMatch = trimmed.match(/^class\s+(\w+)\s*\(/);
			if (classMatch && pendingDecorators.length > 0) {
				const modelName = classMatch[1];
				this._applyDecorators(modelName, pendingDecorators);
				pendingDecorators = [];
				continue;
			}
			
			// Non-decorator, non-class line clears pending (unless empty/comment)
			if (trimmed && !trimmed.startsWith('#') && !trimmed.startsWith('@')) {
				pendingDecorators = [];
			}
		}
		
		return this.decorators;
	}

	_parseDecoratorArgs(argsStr) {
		const config = {};
		
		// Match key=value pairs, handling quoted strings
		const regex = /(\w+)\s*=\s*(?:"([^"]*)"|'([^']*)'|([^,\)]+))/g;
		let match;
		
		while ((match = regex.exec(argsStr)) !== null) {
			const key = match[1];
			const value = match[2] ?? match[3] ?? match[4]?.trim();
			
			// Convert to appropriate type
			if (value === 'True' || value === 'true') {
				config[key] = true;
			} else if (value === 'False' || value === 'false') {
				config[key] = false;
			} else if (value === 'None' || value === 'null') {
				config[key] = null;
			} else if (/^-?\d+$/.test(value)) {
				config[key] = parseInt(value);
			} else if (/^-?\d+\.\d+$/.test(value)) {
				config[key] = parseFloat(value);
			} else {
				config[key] = value;
			}
		}
		
		return Object.keys(config).length > 0 ? config : null;
	}

	_applyDecorators(modelName, decorators) {
		if (!this.decorators[modelName]) {
			this.decorators[modelName] = { buttons: [], dropzone: null };
		}
		
		for (const dec of decorators) {
			if (dec.type === DecoratorType.BUTTON) {
				this.decorators[modelName].buttons.push(dec.config);
			} else if (dec.type === DecoratorType.DROPZONE) {
				this.decorators[modelName].dropzone = dec.config;
			}
		}
	}

	getDecoratorsForModel(modelName) {
		return this.decorators[modelName] || { buttons: [], dropzone: null };
	}
}

// ========================================================================
// Node Decorators Extension
// ========================================================================

class NodeDecoratorsExtension extends SchemaGraphExtension {
	constructor(app) {
		super(app);
		this.parser = new NodeDecoratorParser();
		this.schemaDecorators = {}; // schemaName -> { modelName -> decorators }
		this._callbackRegistry = {}; // callbackId -> function
	}

	_registerNodeTypes() {
		// No new node types
	}

	_setupEventListeners() {
		// Listen for schema registration to parse decorators
		this.on('schema:registered', (e) => {
			this._parseSchemaDecorators(e.schemaName);
		});
		
		// Listen for node creation to apply decorators
		this.on('node:created', (e) => {
			this._applyDecoratorsToNode(e.node);
		});
	}

	_extendAPI() {
		const self = this;
		
		this.app.api = this.app.api || {};
		this.app.api.decorators = {
			// Register callbacks that decorators can reference
			registerCallback: (id, fn) => self.registerCallback(id, fn),
			unregisterCallback: (id) => self.unregisterCallback(id),
			
			// Manual decorator application
			applyToNode: (node) => self._applyDecoratorsToNode(node),
			
			// Get parsed decorators
			getDecorators: (schemaName, modelName) => {
				return self.schemaDecorators[schemaName]?.[modelName] || null;
			},
			
			// Parse decorators from code
			parseDecorators: (code) => {
				const parser = new NodeDecoratorParser();
				return parser.parse(code);
			}
		};
		
		this.app.decoratorManager = this;
	}

	// ================================================================
	// Callback Registry
	// ================================================================

	registerCallback(id, fn) {
		if (typeof fn !== 'function') {
			console.warn(`[NodeDecorators] Callback "${id}" must be a function`);
			return false;
		}
		this._callbackRegistry[id] = fn;
		return true;
	}

	unregisterCallback(id) {
		delete this._callbackRegistry[id];
	}

	_resolveCallback(callbackId, fallbackAction) {
		// Check registry first
		if (this._callbackRegistry[callbackId]) {
			return this._callbackRegistry[callbackId];
		}
		
		// Built-in callbacks
		switch (callbackId) {
			case 'file_input':
				return (node, event, btn) => this._triggerFileInput(node, btn);
			case 'clear_data':
				return (node) => this._clearNodeData(node);
			case 'toggle_expand':
				return (node) => this._toggleNodeExpand(node);
			case 'emit_event':
				return (node, event, btn) => {
					this.eventBus.emit('node:buttonClicked', {
						nodeId: node.id,
						buttonId: btn.id,
						node, btn
					});
				};
			default:
				// Return a default that emits an event
				return (node, event, btn) => {
					this.eventBus.emit('node:buttonClicked', {
						nodeId: node.id,
						buttonId: btn?.id || callbackId,
						action: callbackId,
						node, btn
					});
				};
		}
	}

	_resolveDropCallback(callbackId) {
		if (this._callbackRegistry[callbackId]) {
			return this._callbackRegistry[callbackId];
		}
		
		// Built-in drop callbacks
		switch (callbackId) {
			case 'load_json':
				return (node, files) => this._loadJsonFile(node, files[0]);
			case 'load_text':
				return (node, files) => this._loadTextFile(node, files[0]);
			case 'load_data':
				return (node, files) => this._loadDataFile(node, files[0]);
			default:
				// Default: emit event
				return (node, files, event) => {
					this.eventBus.emit('node:fileDrop', {
						nodeId: node.id,
						files,
						action: callbackId,
						node
					});
				};
		}
	}

	// ================================================================
	// Built-in Actions
	// ================================================================

	_triggerFileInput(node, btn) {
		const input = document.createElement('input');
		input.type = 'file';
		input.accept = btn?.accept || node._dropZone?.accept || '*';
		input.onchange = (e) => {
			const files = Array.from(e.target.files);
			if (files.length > 0 && node._dropZone?.callback) {
				node._dropZone.callback(node, files, e);
			}
		};
		input.click();
	}

	_clearNodeData(node) {
		if (node.clear) {
			node.clear();
		} else if (node.isDataNode) {
			node.sourceType = 'none';
			node.sourceUrl = '';
			node.sourceData = null;
			node.sourceMeta = { filename: '', mimeType: '', size: 0 };
		}
		this.eventBus.emit('data:cleared', { nodeId: node.id });
		this.app.draw();
	}

	_toggleNodeExpand(node) {
		node.isExpanded = !node.isExpanded;
		if (node.isExpanded) {
			node._collapsedSize = [...node.size];
			node.size = [node.size[0] * 1.5, node.size[1] * 2];
		} else {
			node.size = node._collapsedSize || node.size;
		}
		this.app.draw();
	}

	_loadJsonFile(node, file) {
		const reader = new FileReader();
		reader.onload = (e) => {
			try {
				const data = JSON.parse(e.target.result);
				this.eventBus.emit('node:jsonLoaded', { nodeId: node.id, data, filename: file.name });
			} catch (err) {
				this.app.showError?.(`Failed to parse JSON: ${err.message}`);
			}
		};
		reader.readAsText(file);
	}

	_loadTextFile(node, file) {
		const reader = new FileReader();
		reader.onload = (e) => {
			this.eventBus.emit('node:textLoaded', { 
				nodeId: node.id, 
				text: e.target.result, 
				filename: file.name 
			});
		};
		reader.readAsText(file);
	}

	_loadDataFile(node, file) {
		const reader = new FileReader();
		reader.onload = (e) => {
			if (node.setFromFile) {
				node.setFromFile(file, e.target.result);
			}
			this.eventBus.emit('data:loaded', { nodeId: node.id, filename: file.name });
			this.app.draw();
		};
		
		// Decide read method based on node type or file type
		if (node.dataType === 'text' || file.type.startsWith('text/')) {
			reader.readAsText(file);
		} else {
			reader.readAsDataURL(file);
		}
	}

	// ================================================================
	// Schema Parsing
	// ================================================================

	_parseSchemaDecorators(schemaName) {
		const schema = this.graph.schemas[schemaName];
		if (!schema?.code) return;
		
		const decorators = this.parser.parse(schema.code);
		this.schemaDecorators[schemaName] = decorators;
		
		console.log(`[NodeDecorators] Parsed decorators for ${schemaName}:`, decorators);
	}

	// ================================================================
	// Apply Decorators to Node
	// ================================================================

	_applyDecoratorsToNode(node) {
		if (!node) return;
		
		// Get schema and model name
		const schemaName = node.schemaName;
		const modelName = node.modelName;
		
		if (!schemaName || !modelName) return;
		
		const decorators = this.schemaDecorators[schemaName]?.[modelName];
		if (!decorators) return;
		
		const interactive = this.app.interactiveManager;
		if (!interactive) {
			console.warn('[NodeDecorators] InteractiveExtension not loaded');
			return;
		}
		
		// Apply buttons
		for (const btnConfig of decorators.buttons || []) {
			const callbackId = btnConfig.callback || btnConfig.action || btnConfig.id;
			
			interactive.addButton(node, {
				id: btnConfig.id,
				label: btnConfig.label || '',
				icon: btnConfig.icon || '',
				position: this._mapPosition(btnConfig.position),
				width: btnConfig.width,
				height: btnConfig.height,
				x: btnConfig.x,
				y: btnConfig.y,
				bg: btnConfig.bg,
				bgHover: btnConfig.bg_hover,
				text: btnConfig.text_color,
				border: btnConfig.border,
				enabled: btnConfig.enabled !== false,
				callback: this._resolveCallback(callbackId, btnConfig.action)
			});
		}
		
		// Apply dropzone
		if (decorators.dropzone) {
			const dzConfig = decorators.dropzone;
			const callbackId = dzConfig.callback || dzConfig.action || 'emit_event';
			
			interactive.setDropZone(node, {
				accept: dzConfig.accept || '*',
				area: this._mapDropArea(dzConfig.area),
				label: dzConfig.label || 'Drop file here',
				x: dzConfig.x,
				y: dzConfig.y,
				width: dzConfig.width,
				height: dzConfig.height,
				enabled: dzConfig.enabled !== false,
				callback: this._resolveDropCallback(callbackId)
			});
		}
	}

	_mapPosition(pos) {
		if (!pos) return ButtonPosition.FOOTER;
		
		const map = {
			'header_right': ButtonPosition.HEADER_RIGHT,
			'header-right': ButtonPosition.HEADER_RIGHT,
			'footer': ButtonPosition.FOOTER,
			'footer_left': ButtonPosition.FOOTER_LEFT,
			'footer-left': ButtonPosition.FOOTER_LEFT,
			'footer_right': ButtonPosition.FOOTER_RIGHT,
			'footer-right': ButtonPosition.FOOTER_RIGHT,
			'content': ButtonPosition.CONTENT,
			'custom': ButtonPosition.CUSTOM
		};
		
		return map[pos.toLowerCase()] || ButtonPosition.FOOTER;
	}

	_mapDropArea(area) {
		if (!area) return DropZoneArea.CONTENT;
		
		const map = {
			'full': DropZoneArea.FULL,
			'content': DropZoneArea.CONTENT,
			'custom': DropZoneArea.CUSTOM
		};
		
		return map[area.toLowerCase()] || DropZoneArea.CONTENT;
	}
}

// ========================================================================
// AUTO-INITIALIZATION
// ========================================================================

if (typeof SchemaGraphApp !== 'undefined') {
	if (typeof extensionRegistry !== 'undefined') {
		extensionRegistry.register('decorators', NodeDecoratorsExtension);
	} else {
		const originalSetup = SchemaGraphApp.prototype.setupEventListeners;
		SchemaGraphApp.prototype.setupEventListeners = function() {
			originalSetup.call(this);
			this.decoratorManager = new NodeDecoratorsExtension(this);
		};
	}
	
	console.log('✨ SchemaGraph Node Decorators extension loaded');
}

// ========================================================================
// EXPORTS
// ========================================================================

if (typeof module !== 'undefined' && module.exports) {
	module.exports = {
		DecoratorType, NodeDecoratorParser, NodeDecoratorsExtension
	};
}

if (typeof window !== 'undefined') {
	window.DecoratorType = DecoratorType;
	window.NodeDecoratorParser = NodeDecoratorParser;
	window.NodeDecoratorsExtension = NodeDecoratorsExtension;
}
