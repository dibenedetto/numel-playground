// ========================================================================
// SCHEMAGRAPH EXTENSIONS
// Extension system: Registry, Base Extension, DrawUtils, Decorators, Analytics
// Depends on: schemagraph-core.js
// ========================================================================

console.log('[SchemaGraph] Loading extensions module...');

// ========================================================================
// EXTENSION REGISTRY
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

		this._backwardCompatibility(app);

		for (const [name, ext] of this.extensions) {
			try {
				ext.instance = new ext.Class(app);
				ext.instance._name = name;
				console.log(`✔ Extension: ${name}`);
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

	_backwardCompatibility(app) {
		if (true) {
			const proto = Object.getPrototypeOf(app);

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
		}

		if (true) {
			const proto = Object.getPrototypeOf(app.graph);

			if (!proto.addLink) {
				proto.addLink = function(sourceNodeId, sourceSlot, targetNodeId, targetSlot, type) {
					const sourceNode = typeof sourceNodeId === 'object' ? sourceNodeId : this.getNodeById(sourceNodeId);
					const targetNode = typeof targetNodeId === 'object' ? targetNodeId : this.getNodeById(targetNodeId);
					
					if (!sourceNode || !targetNode) return null;
					
					const srcId = sourceNode.id;
					const tgtId = targetNode.id;
					
					if (this.last_link_id === undefined) this.last_link_id = 0;
					const linkId = ++this.last_link_id;
					
					const linkType = type || sourceNode.outputs?.[sourceSlot]?.type || 'Any';
					const link = new Link(linkId, srcId, sourceSlot, tgtId, targetSlot, linkType);
					
					this.links[linkId] = link;
					
					// Update source output
					if (sourceNode.outputs?.[sourceSlot]) {
						if (!sourceNode.outputs[sourceSlot].links) {
							sourceNode.outputs[sourceSlot].links = [];
						}
						sourceNode.outputs[sourceSlot].links.push(linkId);
					}
					
					// Update target input
					if (targetNode.inputs?.[targetSlot]) {
						targetNode.inputs[targetSlot].link = linkId;
					}
					
					app.eventBus.emit(GraphEvents.LINK_CREATED, {
						linkId, sourceNodeId: srcId, sourceSlot, targetNodeId: tgtId, targetSlot, link
					});
					
					return link;
				};
			}
		}
	}
}

// ========================================================================
// SCHEMAGRAPH EXTENSION BASE CLASS
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

	on(event, handler) {
		this.eventBus.on(event, handler);
		this._eventHandlers.push({ event, handler, isDOM: false });
	}

	onDOM(element, event, handler, options) {
		element.addEventListener(event, handler, options);
		this._eventHandlers.push({ element, event, handler, options, isDOM: true });
	}

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
// DRAW UTILITIES
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
	}
};

// ========================================================================
// NODE DECORATOR PARSER
// ========================================================================

class NodeDecoratorParser {
	constructor() {
		this.decorators = {};
	}

	parse(code) {
		this.decorators = {};
		const lines = code.split('\n');
		let pending = [];
		let accumulator = null;
		let accType = null;
		let depth = 0;

		for (const line of lines) {
			const trimmed = line.trim();

			if (accumulator !== null) {
				accumulator += ' ' + trimmed;
				for (const c of trimmed) {
					if (c === '(') depth++;
					else if (c === ')') depth--;
				}
				if (depth === 0) {
					const cfg = this._parseDecorator(accumulator, accType);
					if (cfg) pending.push({ type: accType, config: cfg });
					accumulator = null;
				}
				continue;
			}

			for (const [prefix, type] of [
				['@node_button', DecoratorType.BUTTON],
				['@node_dropzone', DecoratorType.DROPZONE],
				['@node_chat', DecoratorType.CHAT],
				['@node_info', DecoratorType.INFO]
			]) {
				if (trimmed.startsWith(prefix)) {
					depth = 0;
					for (const c of trimmed) {
						if (c === '(') depth++;
						else if (c === ')') depth--;
					}
					if (depth === 0) {
						const cfg = this._parseDecorator(trimmed, type);
						if (cfg) pending.push({ type, config: cfg });
					} else {
						accumulator = trimmed;
						accType = type;
					}
					break;
				}
			}

			const classMatch = trimmed.match(/^class\s+(\w+)\s*\(/);
			if (classMatch && pending.length) {
				this._apply(classMatch[1], pending);
				pending = [];
			} else if (trimmed && !trimmed.startsWith('#') && !trimmed.startsWith('@')) {
				pending = [];
			}
		}
		return this.decorators;
	}

	_parseDecorator(str, type) {
		const match = str.match(new RegExp(`^@${type}\\s*\\((.*)\\)\\s*$`));
		if (!match) return null;

		// Handle empty decorator like @node_info()
		if (!match[1].trim()) return {};

		const config = {};
		const regex = /(\w+)\s*=\s*(?:"([^"]*)"|'([^']*)'|([^,\)]+))/g;
		let m;
		while ((m = regex.exec(match[1])) !== null) {
			let val = m[2] ?? m[3] ?? m[4]?.trim();
			if (val === 'True' || val === 'true') val = true;
			else if (val === 'False' || val === 'false') val = false;
			else if (val === 'None' || val === 'null') val = null;
			else if (/^-?\d+$/.test(val)) val = parseInt(val);
			else if (/^-?\d+\.\d+$/.test(val)) val = parseFloat(val);
			config[m[1]] = val;
		}
		return config;
	}

	_apply(modelName, decorators) {
		if (!this.decorators[modelName]) {
			this.decorators[modelName] = { buttons: [], dropzone: null, chat: null, info: null };
		}
		for (const d of decorators) {
			if (d.type === DecoratorType.BUTTON) this.decorators[modelName].buttons.push(d.config);
			else if (d.type === DecoratorType.DROPZONE) this.decorators[modelName].dropzone = d.config;
			else if (d.type === DecoratorType.CHAT) this.decorators[modelName].chat = d.config;
			else if (d.type === DecoratorType.INFO) this.decorators[modelName].info = d.config;
		}
	}
}

// ========================================================================
// ANALYTICS SERVICE
// ========================================================================

class AnalyticsService {
	constructor(eventBus) {
		this.eventBus = eventBus;
		this.metrics = this.createMetrics();
		this.sessions = [];
		this.currentSession = this.createSession();
		this.setupListeners();
	}

	createMetrics() {
		return {
			nodeCreated: 0, nodeDeleted: 0, linkCreated: 0, linkDeleted: 0,
			schemaRegistered: 0, schemaRemoved: 0, graphExported: 0, graphImported: 0,
			configExported: 0, configImported: 0, layoutApplied: 0, errors: 0, interactions: 0
		};
	}

	createSession() {
		return {
			id: Math.random().toString(36).substr(2, 9),
			startTime: Date.now(),
			events: [],
			metrics: {}
		};
	}

	setupListeners() {
		this.eventBus.on('node:created', () => this.track('nodeCreated'));
		this.eventBus.on('node:deleted', () => this.track('nodeDeleted'));
		this.eventBus.on('link:created', () => this.track('linkCreated'));
		this.eventBus.on('link:deleted', () => this.track('linkDeleted'));
		this.eventBus.on('schema:registered', () => this.track('schemaRegistered'));
		this.eventBus.on('schema:removed', () => this.track('schemaRemoved'));
		this.eventBus.on('graph:exported', () => this.track('graphExported'));
		this.eventBus.on('graph:imported', () => this.track('graphImported'));
		this.eventBus.on('config:exported', () => this.track('configExported'));
		this.eventBus.on('config:imported', () => this.track('configImported'));
		this.eventBus.on('layout:applied', () => this.track('layoutApplied'));
		this.eventBus.on('error', () => this.track('errors'));
		this.eventBus.on('interaction', () => this.track('interactions'));
	}

	track(metric, value = 1) {
		if (this.metrics.hasOwnProperty(metric)) this.metrics[metric] += value;
		this.currentSession.events.push({ metric, value, timestamp: Date.now() });
	}

	getMetrics() { return { ...this.metrics }; }

	getSessionMetrics() {
		return {
			sessionId: this.currentSession.id,
			duration: Date.now() - this.currentSession.startTime,
			events: this.currentSession.events.length,
			metrics: this.metrics
		};
	}

	endSession() {
		this.currentSession.endTime = Date.now();
		this.currentSession.metrics = { ...this.metrics };
		this.sessions.push(this.currentSession);
		this.metrics = this.createMetrics();
		this.currentSession = this.createSession();
	}
}

// ========================================================================
// GLOBAL EXTENSION REGISTRY INSTANCE
// ========================================================================

const extensionRegistry = new ExtensionRegistry();

// ========================================================================
// EXPORTS
// ========================================================================

// Module exports
if (typeof module !== 'undefined' && module.exports) {
	module.exports = {
		ExtensionRegistry, SchemaGraphExtension, DrawUtils,
		NodeDecoratorParser, AnalyticsService, extensionRegistry
	};
}

// Global exports for browser (standard JS)
if (typeof window !== 'undefined') {
	window.ExtensionRegistry = ExtensionRegistry;
	window.SchemaGraphExtension = SchemaGraphExtension;
	window.DrawUtils = DrawUtils;
	window.NodeDecoratorParser = NodeDecoratorParser;
	window.AnalyticsService = AnalyticsService;
	window.extensionRegistry = extensionRegistry;
}

console.log('[SchemaGraph] Extensions module loaded.');
