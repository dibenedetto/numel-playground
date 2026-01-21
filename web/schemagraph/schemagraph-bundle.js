// ========================================================================
// SCHEMAGRAPH BUNDLE
// Global integration file - loads all modules in correct order
// ========================================================================

(function(global) {
	'use strict';

	console.log('[SchemaGraph] Bundle initializing...');

	// ========================================================================
	// VERSION INFO
	// ========================================================================

	const SCHEMAGRAPH_VERSION = '1.0.0';
	const SCHEMAGRAPH_BUILD_DATE = new Date().toISOString().slice(0, 10);

	// Save reference to original SchemaGraph class before we override it
	const SchemaGraphClass = global.SchemaGraph;

	// ========================================================================
	// DEPENDENCY CHECK
	// ========================================================================

	function checkDependencies() {
		const required = [
			'FieldRole',
			'DataExportMode',
			'GraphEvents',
			'DecoratorType',
			'DropZoneArea',
			'EventBus',
			'Node',
			'Link',
			'Graph',
			'WorkflowNode',
			'WorkflowSchemaParser',
			'WorkflowNodeFactory',
			'WorkflowImporter',
			'WorkflowExporter',
			'SchemaGraph',
			'ExtensionRegistry',
			'SchemaGraphExtension',
			'DrawUtils',
			'NodeDecoratorParser',
			'AnalyticsService',
			'extensionRegistry',
			'MouseTouchController',
			'KeyboardController',
			'VoiceController',
			'DrawingStyleManager',
			'SchemaGraphApp'
		];

		const missing = required.filter(name => typeof global[name] === 'undefined');

		if (missing.length > 0) {
			console.warn('[SchemaGraph] Missing dependencies:', missing.join(', '));
			console.warn('[SchemaGraph] Make sure all script files are loaded in correct order:');
			console.warn('  1. schemagraph-core.js');
			console.warn('  2. schemagraph-workflow.js');
			console.warn('  3. schemagraph-graph.js');
			console.warn('  4. schemagraph-extensions.js');
			console.warn('  5. schemagraph-controllers.js');
			console.warn('  6. schemagraph-drawing.js');
			console.warn('  7. schemagraph-app.js');
			console.warn('  8. schemagraph-bundle.js (this file)');
			return false;
		}

		console.log('[SchemaGraph] All dependencies loaded successfully.');
		return true;
	}

	// ========================================================================
	// SCHEMAGRAPH NAMESPACE
	// ========================================================================

	const SchemaGraph = {
		// Version info
		version: SCHEMAGRAPH_VERSION,
		buildDate: SCHEMAGRAPH_BUILD_DATE,

		// Core classes
		EventBus: global.EventBus,
		Node: global.Node,
		Link: global.Link,
		Graph: global.Graph,

		// Enums
		FieldRole: global.FieldRole,
		DataExportMode: global.DataExportMode,
		GraphEvents: global.GraphEvents,
		DecoratorType: global.DecoratorType,
		DropZoneArea: global.DropZoneArea,

		// Workflow classes
		WorkflowNode: global.WorkflowNode,
		WorkflowSchemaParser: global.WorkflowSchemaParser,
		WorkflowNodeFactory: global.WorkflowNodeFactory,
		WorkflowImporter: global.WorkflowImporter,
		WorkflowExporter: global.WorkflowExporter,

		// Main graph class (saved reference to avoid circular reference after export)
		SchemaGraphClass: SchemaGraphClass,

		// Extension system
		ExtensionRegistry: global.ExtensionRegistry,
		SchemaGraphExtension: global.SchemaGraphExtension,
		DrawUtils: global.DrawUtils,
		NodeDecoratorParser: global.NodeDecoratorParser,
		AnalyticsService: global.AnalyticsService,
		extensionRegistry: global.extensionRegistry,

		// Controllers
		MouseTouchController: global.MouseTouchController,
		KeyboardController: global.KeyboardController,
		VoiceController: global.VoiceController,

		// Drawing
		DrawingStyleManager: global.DrawingStyleManager,

		// Main application
		App: global.SchemaGraphApp,

		// ====================================================================
		// FACTORY METHODS
		// ====================================================================

		/**
		 * Create a new SchemaGraph application instance
		 * @param {string|HTMLCanvasElement} canvasOrSelector - Canvas element or CSS selector
		 * @param {Object} options - Configuration options
		 * @returns {SchemaGraphApp} Application instance
		 */
		create: function(canvasOrSelector, options = {}) {
			let canvasId;
			if (typeof canvasOrSelector === 'string') {
				// If it starts with #, it's likely an ID selector
				if (canvasOrSelector.startsWith('#')) {
					canvasId = canvasOrSelector.substring(1);
				} else {
					// Otherwise treat it as a plain ID
					canvasId = canvasOrSelector;
				}
				// Verify the canvas exists
				const canvas = document.getElementById(canvasId);
				if (!canvas) {
					throw new Error(`Canvas not found: ${canvasOrSelector}`);
				}
			} else if (canvasOrSelector instanceof HTMLCanvasElement) {
				// If an element is passed, get its ID
				if (!canvasOrSelector.id) {
					throw new Error('Canvas element must have an ID');
				}
				canvasId = canvasOrSelector.id;
			} else {
				throw new Error('Invalid canvas parameter: must be a string ID or HTMLCanvasElement');
			}

			return new global.SchemaGraphApp(canvasId, options);
		},

		/**
		 * Create a new Graph instance (without UI)
		 * @returns {SchemaGraph} Graph instance
		 */
		createGraph: function() {
			return new SchemaGraphClass();
		},

		/**
		 * Create a new EventBus instance
		 * @returns {EventBus} EventBus instance
		 */
		createEventBus: function() {
			return new global.EventBus();
		},

		/**
		 * Parse a Python schema file content
		 * @param {string} pythonCode - Python schema code
		 * @returns {Object} Parsed schema
		 */
		parseSchema: function(pythonCode) {
			const parser = new global.WorkflowSchemaParser();
			return parser.parse(pythonCode);
		},

		/**
		 * Register a custom extension
		 * @param {string} name - Extension name
		 * @param {Function} ExtensionClass - Extension class
		 */
		registerExtension: function(name, ExtensionClass) {
			global.extensionRegistry.register(name, ExtensionClass);
		},

		/**
		 * Get a registered extension instance
		 * @param {string} name - Extension name
		 * @returns {SchemaGraphExtension|null} Extension instance
		 */
		getExtension: function(name) {
			return global.extensionRegistry.get(name);
		},

		/**
		 * List all registered extensions
		 * @returns {string[]} Extension names
		 */
		listExtensions: function() {
			return global.extensionRegistry.list();
		},

		// ====================================================================
		// UTILITY METHODS
		// ====================================================================

		/**
		 * Check if all dependencies are loaded
		 * @returns {boolean} True if all dependencies are available
		 */
		checkDependencies: checkDependencies,

		/**
		 * Get library info
		 * @returns {Object} Library information
		 */
		getInfo: function() {
			return {
				name: 'SchemaGraph',
				version: SCHEMAGRAPH_VERSION,
				buildDate: SCHEMAGRAPH_BUILD_DATE,
				modules: [
					'schemagraph-core.js',
					'schemagraph-workflow.js',
					'schemagraph-graph.js',
					'schemagraph-extensions.js',
					'schemagraph-controllers.js',
					'schemagraph-drawing.js',
					'schemagraph-app.js'
				],
				dependencies: {
					required: 'None (vanilla JavaScript)',
					optional: 'Web Speech API (for voice commands)'
				}
			};
		},

		/**
		 * Log library info to console
		 */
		logInfo: function() {
			const info = this.getInfo();
			console.log(`
╔════════════════════════════════════════════════════════════╗
║                      SCHEMAGRAPH                           ║
║                    Version ${info.version}                         ║
╠════════════════════════════════════════════════════════════╣
║  A node-based graph visualization library                  ║
║  for workflow and schema management                        ║
╠════════════════════════════════════════════════════════════╣
║  Modules:                                                  ║
║    - Core (EventBus, Node, Link, Graph)                    ║
║    - Workflow (Parser, Factory, Import/Export)             ║
║    - Extensions (Registry, DrawUtils, Analytics)           ║
║    - Controllers (Mouse, Keyboard, Voice)                  ║
║    - Drawing (Style Manager)                               ║
║    - App (Main Application)                                ║
╚════════════════════════════════════════════════════════════╝
			`);
		}
	};

	// ========================================================================
	// GLOBAL EXPORT
	// ========================================================================

	// Export to global namespace
	global.SchemaGraph = SchemaGraph;

	// Also export as SG shorthand
	global.SG = SchemaGraph;

	// Module exports for Node.js / CommonJS
	if (typeof module !== 'undefined' && module.exports) {
		module.exports = SchemaGraph;
	}

	// AMD support
	if (typeof define === 'function' && define.amd) {
		define('schemagraph', [], function() {
			return SchemaGraph;
		});
	}

	// ========================================================================
	// AUTO-INITIALIZATION
	// ========================================================================

	// Check dependencies when DOM is ready
	if (typeof document !== 'undefined') {
		if (document.readyState === 'loading') {
			document.addEventListener('DOMContentLoaded', function() {
				checkDependencies();
			});
		} else {
			// DOM already loaded
			checkDependencies();
		}
	}

	console.log('[SchemaGraph] Bundle loaded. Use SchemaGraph.create(canvas) to initialize.');

})(typeof window !== 'undefined' ? window : (typeof global !== 'undefined' ? global : this));
