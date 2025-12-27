// ========================================================================
// SCHEMAGRAPH EXTENSIONS CORE
// Base classes, registry, and shared utilities for all extensions
// Load AFTER schemagraph.js, BEFORE other extensions
// ========================================================================

// ========================================================================
// Extension Registry
// ========================================================================

class ExtensionRegistry {
	constructor() {
		this.extensions = new Map();
		this.initialized = false;
	}

	register(name, ExtensionClass) {
		if (this.extensions.has(name)) {
			console.warn(`[ExtensionRegistry] "${name}" already registered, replacing`);
		}
		this.extensions.set(name, { Class: ExtensionClass, instance: null });
	}

	initAll(app) {
		if (this.initialized) return;
		
		for (const [name, ext] of this.extensions) {
			try {
				ext.instance = new ext.Class(app);
				ext.instance._name = name;
				console.log(`✓ Extension: ${name}`);
			} catch (e) {
				console.error(`✗ Extension ${name} failed:`, e);
			}
		}
		this.initialized = true;
	}

	get(name) {
		return this.extensions.get(name)?.instance;
	}

	list() {
		return Array.from(this.extensions.keys());
	}

	has(name) {
		return this.extensions.has(name);
	}
}

const extensionRegistry = new ExtensionRegistry();

// ========================================================================
// Base Extension Class
// ========================================================================

class SchemaGraphExtension {
	constructor(app) {
		this.app = app;
		this.graph = app.graph;
		this.eventBus = app.eventBus;
		this._eventHandlers = [];
		this._name = 'unnamed';
		
		this._init();
	}

	_init() {
		this._registerNodeTypes();
		this._setupEventListeners();
		this._extendAPI();
		this._injectStyles();
	}

	// Override in subclasses
	_registerNodeTypes() {}
	_setupEventListeners() {}
	_extendAPI() {}
	_injectStyles() {}

	// Event helper with tracking
	on(event, handler) {
		this.eventBus.on(event, handler);
		this._eventHandlers.push({ event, handler, isDOM: false });
	}

	// DOM event helper with tracking
	onDOM(element, event, handler, options) {
		element.addEventListener(event, handler, options);
		this._eventHandlers.push({ element, event, handler, options, isDOM: true });
	}

	// Cleanup
	destroy() {
		for (const h of this._eventHandlers) {
			if (h.isDOM) {
				h.element.removeEventListener(h.event, h.handler, h.options);
			} else {
				this.eventBus.off?.(h.event, h.handler);
			}
		}
		this._eventHandlers = [];
	}

	// Namespaced preferences
	getPref(key, defaultVal = null) {
		const stored = localStorage.getItem(`sg-${this._name}-${key}`);
		if (stored === null) return defaultVal;
		try { return JSON.parse(stored); } catch { return stored; }
	}

	setPref(key, value) {
		localStorage.setItem(`sg-${this._name}-${key}`, JSON.stringify(value));
	}
}

// ========================================================================
// Shared Drawing Utilities
// ========================================================================

const DrawUtils = {
	roundRect(ctx, x, y, w, h, r) {
		ctx.moveTo(x + r, y);
		ctx.lineTo(x + w - r, y);
		ctx.quadraticCurveTo(x + w, y, x + w, y + r);
		ctx.lineTo(x + w, y + h - r);
		ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
		ctx.lineTo(x + r, y + h);
		ctx.quadraticCurveTo(x, y + h, x, y + h - r);
		ctx.lineTo(x, y + r);
		ctx.quadraticCurveTo(x, y, x + r, y);
		ctx.closePath();
	},

	roundRectTop(ctx, x, y, w, h, r) {
		ctx.moveTo(x + r, y);
		ctx.lineTo(x + w - r, y);
		ctx.quadraticCurveTo(x + w, y, x + w, y + r);
		ctx.lineTo(x + w, y + h);
		ctx.lineTo(x, y + h);
		ctx.lineTo(x, y + r);
		ctx.quadraticCurveTo(x, y, x + r, y);
		ctx.closePath();
	},

	darkenColor(hex, amount) {
		const num = parseInt(hex.replace('#', ''), 16);
		const r = Math.max(0, (num >> 16) - amount);
		const g = Math.max(0, ((num >> 8) & 0xFF) - amount);
		const b = Math.max(0, (num & 0xFF) - amount);
		return '#' + ((r << 16) | (g << 8) | b).toString(16).padStart(6, '0');
	},

	lightenColor(hex, amount) {
		const num = parseInt(hex.replace('#', ''), 16);
		const r = Math.min(255, (num >> 16) + amount);
		const g = Math.min(255, ((num >> 8) & 0xFF) + amount);
		const b = Math.min(255, (num & 0xFF) + amount);
		return '#' + ((r << 16) | (g << 8) | b).toString(16).padStart(6, '0');
	},

	formatSize(bytes) {
		if (!bytes) return '0 B';
		const units = ['B', 'KB', 'MB', 'GB'];
		let i = 0;
		while (bytes >= 1024 && i < units.length - 1) { bytes /= 1024; i++; }
		return `${bytes.toFixed(i > 0 ? 1 : 0)} ${units[i]}`;
	},

	wrapText(ctx, text, maxWidth) {
		const words = text.split(/(\s+)/);
		const lines = [];
		let current = '';
		for (const word of words) {
			const test = current + word;
			if (ctx.measureText(test).width > maxWidth && current) {
				lines.push(current.trim());
				current = word;
			} else {
				current = test;
			}
		}
		if (current.trim()) lines.push(current.trim());
		return lines;
	},

	formatDuration(seconds) {
		const mins = Math.floor(seconds / 60);
		const secs = Math.floor(seconds % 60);
		return `${mins}:${secs.toString().padStart(2, '0')}`;
	}
};

// ========================================================================
// Shared Constants
// ========================================================================

const NodeColors = {
	// Data types
	text: '#4a9eff', document: '#ff9f4a', image: '#00d4aa',
	audio: '#ffd700', video: '#ff4757', model3d: '#00bcd4', binary: '#9370db',
	// Native types
	string: '#4a9eff', number: '#ff9f4a', boolean: '#92d050',
	json: '#9370db', list: '#ff6b9d', dict: '#00bcd4',
	// Preview
	preview: '#46a2da', auto: '#46a2da',
	// Workflow status
	pending: '#4a5568', ready: '#3182ce', running: '#805ad5',
	completed: '#38a169', failed: '#e53e3e', skipped: '#718096'
};

const NodeIcons = {
	text: '📝', document: '📄', image: '🖼️', audio: '🔊',
	video: '🎬', model3d: '🧊', binary: '📦',
	string: '📝', number: '🔢', boolean: '⚡', json: '📋',
	list: '📚', dict: '📖', preview: '👁', auto: '🔄', unknown: '❓'
};

// ========================================================================
// Extend SchemaGraphApp
// ========================================================================

function initExtensionSystem(SchemaGraphAppClass) {
	// Add shared drawing methods to prototype (if not present)
	const proto = SchemaGraphAppClass.prototype;
	
	if (!proto._drawRoundRect) {
		proto._drawRoundRect = function(x, y, w, h, r) {
			DrawUtils.roundRect(this.ctx, x, y, w, h, r);
		};
	}
	if (!proto._drawRoundRectTop) {
		proto._drawRoundRectTop = function(x, y, w, h, r) {
			DrawUtils.roundRectTop(this.ctx, x, y, w, h, r);
		};
	}
	if (!proto._darkenColor) {
		proto._darkenColor = DrawUtils.darkenColor;
	}
	if (!proto._formatSize) {
		proto._formatSize = DrawUtils.formatSize;
	}
	if (!proto._wrapText) {
		proto._wrapText = function(text, maxWidth, ctx) {
			return DrawUtils.wrapText(ctx || this.ctx, text, maxWidth);
		};
	}

	// Hook into setupEventListeners to init extensions
	const originalSetup = proto.setupEventListeners;
	proto.setupEventListeners = function() {
		originalSetup.call(this);
		
		// Store references
		this.extensions = extensionRegistry;
		this._drawUtils = DrawUtils;
		
		// Initialize all registered extensions
		extensionRegistry.initAll(this);
	};

	// Extend API
	const originalCreateAPI = proto._createAPI;
	proto._createAPI = function() {
		const api = originalCreateAPI ? originalCreateAPI.call(this) : {};
		
		api.extensions = {
			get: (name) => this.extensions.get(name),
			list: () => this.extensions.list(),
			has: (name) => this.extensions.has(name),
			registry: this.extensions
		};
		
		return api;
	};
}

// ========================================================================
// Auto-init
// ========================================================================

if (typeof SchemaGraphApp !== 'undefined') {
	initExtensionSystem(SchemaGraphApp);
	console.log('✨ SchemaGraph Extensions Core loaded');
}

// ========================================================================
// Exports
// ========================================================================

if (typeof module !== 'undefined' && module.exports) {
	module.exports = {
		ExtensionRegistry, SchemaGraphExtension, DrawUtils,
		NodeColors, NodeIcons, extensionRegistry, initExtensionSystem
	};
}
