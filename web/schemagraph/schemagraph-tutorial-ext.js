// ========================================================================
// SCHEMAGRAPH TUTORIAL EXTENSION
// Demonstrates how to create a frontend extension for custom node types
// Depends on: schemagraph-extensions.js
// ========================================================================

console.log('[SchemaGraph] Loading tutorial extension...');

// ========================================================================
// TUTORIAL EXTENSION CLASS
// ========================================================================

/**
 * TutorialExtension demonstrates the extension pattern for SchemaGraph.
 *
 * This extension handles the Counter node type, showing how to:
 * - Listen for node events (button clicks, value changes)
 * - Make API calls to the backend
 * - Update node values dynamically
 * - Add custom styles
 */
class TutorialExtension extends SchemaGraphExtension {
	constructor(app) {
		super(app);

		// Store reference to the API base URL
		this.apiBase = window.API_BASE || '';
	}

	// ====================================================================
	// NODE TYPE REGISTRATION
	// ====================================================================

	/**
	 * Register custom node types with the graph.
	 * For Counter, we don't need custom registration since it's defined
	 * in the Python schema and loaded automatically.
	 */
	_registerNodeTypes() {
		// Counter node is registered via Python schema, no action needed here
		// For fully custom nodes, you would call:
		// this.graph.registerNodeType('Counter', CounterNodeClass);
	}

	// ====================================================================
	// EVENT LISTENERS
	// ====================================================================

	/**
	 * Set up event listeners for node interactions.
	 * This is where we handle button clicks and other events.
	 */
	_setupEventListeners() {
		// Listen for button clicks on any node
		this.on('node:buttonClick', (e) => {
			const { node, buttonId, button } = e;

			// Check if this is a Counter node
			if (this._isCounterNode(node)) {
				this._handleCounterButton(node, buttonId);
			}
		});

		// Listen for node value changes (optional - for syncing with backend)
		this.on('node:valueChanged', (e) => {
			const { node, field, value } = e;

			if (this._isCounterNode(node)) {
				// Could sync changes to backend here if needed
			}
		});

		// Listen for workflow loaded to initialize counter displays
		this.on('workflow:loaded', () => {
			this._initializeCounterDisplays();
		});
	}

	// ====================================================================
	// API EXTENSION
	// ====================================================================

	/**
	 * Extend the SchemaGraph API with tutorial-specific methods.
	 * These become available via schemaGraph.api.tutorial.*
	 */
	_extendAPI() {
		const self = this;

		// Add tutorial namespace to the API
		this.app.api.tutorial = {
			/**
			 * Increment a counter node by its step value
			 * @param {Object|string} nodeOrId - Node object or node ID
			 * @returns {Promise<Object>} API response
			 */
			increment: (nodeOrId) => self._counterAction(nodeOrId, 'increment'),

			/**
			 * Decrement a counter node by its step value
			 * @param {Object|string} nodeOrId - Node object or node ID
			 * @returns {Promise<Object>} API response
			 */
			decrement: (nodeOrId) => self._counterAction(nodeOrId, 'decrement'),

			/**
			 * Reset a counter node to zero
			 * @param {Object|string} nodeOrId - Node object or node ID
			 * @returns {Promise<Object>} API response
			 */
			reset: (nodeOrId) => self._counterAction(nodeOrId, 'reset'),

			/**
			 * Get current counter value
			 * @param {Object|string} nodeOrId - Node object or node ID
			 * @returns {number} Current value
			 */
			getValue: (nodeOrId) => {
				const node = self._getNode(nodeOrId);
				return node ? self._getNodeValue(node, 'value') : 0;
			}
		};
	}

	// ====================================================================
	// STYLES
	// ====================================================================

	/**
	 * Inject custom CSS styles for the extension.
	 * Counter nodes use default styling, but this shows the pattern.
	 */
	_injectStyles() {
		const styleId = 'schemagraph-tutorial-styles';
		if (document.getElementById(styleId)) return;

		const style = document.createElement('style');
		style.id = styleId;
		style.textContent = `
			/* Tutorial Extension Styles */

			/* Counter value display enhancement (applied via canvas, not CSS) */
			/* This is a placeholder showing where you'd add DOM-based styles */

			.sg-counter-tooltip {
				background: var(--sg-panel-bg, #1e1e2e);
				color: var(--sg-text, #cdd6f4);
				padding: 4px 8px;
				border-radius: 4px;
				font-size: 12px;
			}
		`;
		document.head.appendChild(style);
	}

	// ====================================================================
	// HELPER METHODS
	// ====================================================================

	/**
	 * Check if a node is a Counter node.
	 * @param {Object} node - The node to check
	 * @returns {boolean} True if this is a Counter node
	 */
	_isCounterNode(node) {
		if (!node) return false;
		return node.modelName === 'Counter' ||
		       node.workflowType === 'counter' ||
		       node.type === 'counter';
	}

	/**
	 * Get a node object from an ID or node reference.
	 * @param {Object|string} nodeOrId - Node object or node ID
	 * @returns {Object|null} The node object
	 */
	_getNode(nodeOrId) {
		if (!nodeOrId) return null;
		if (typeof nodeOrId === 'object') return nodeOrId;
		return this.graph.getNodeById(nodeOrId);
	}

	/**
	 * Get a value from a node's properties.
	 * @param {Object} node - The node
	 * @param {string} fieldName - The field name to get
	 * @returns {*} The field value
	 */
	_getNodeValue(node, fieldName) {
		// Check node.properties first (runtime values)
		if (node.properties && fieldName in node.properties) {
			return node.properties[fieldName];
		}
		// Fall back to direct property
		return node[fieldName];
	}

	/**
	 * Set a value on a node and trigger update.
	 * @param {Object} node - The node
	 * @param {string} fieldName - The field name to set
	 * @param {*} value - The new value
	 */
	_setNodeValue(node, fieldName, value) {
		// Update properties object
		if (!node.properties) node.properties = {};
		node.properties[fieldName] = value;

		// Also update direct property for compatibility
		node[fieldName] = value;

		// Trigger redraw
		this.app.draw();

		// Emit value changed event
		this.eventBus.emit('node:valueChanged', {
			node,
			nodeId: node.id,
			field: fieldName,
			value
		});
	}

	/**
	 * Get the node index in the workflow (needed for API calls).
	 * @param {Object} node - The node
	 * @returns {number} Node index, or -1 if not found
	 */
	_getNodeIndex(node) {
		return this.graph.nodes.indexOf(node);
	}

	// ====================================================================
	// COUNTER-SPECIFIC METHODS
	// ====================================================================

	/**
	 * Handle counter button click.
	 * @param {Object} node - The counter node
	 * @param {string} buttonId - The button ID ('increment', 'decrement', 'reset')
	 */
	async _handleCounterButton(node, buttonId) {
		const validActions = ['increment', 'decrement', 'reset'];
		if (!validActions.includes(buttonId)) {
			console.warn(`[Tutorial] Unknown counter action: ${buttonId}`);
			return;
		}

		try {
			const result = await this._counterAction(node, buttonId);

			if (result.status === 'success') {
				// Update the node's value display
				this._setNodeValue(node, 'value', result.new_value);
			}
		} catch (error) {
			console.error(`[Tutorial] Counter ${buttonId} failed:`, error);
			this.app.showError?.(`Counter ${buttonId} failed: ${error.message}`);
		}
	}

	/**
	 * Perform a counter action via API.
	 * @param {Object|string} nodeOrId - The node or node ID
	 * @param {string} action - The action ('increment', 'decrement', 'reset')
	 * @returns {Promise<Object>} API response
	 */
	async _counterAction(nodeOrId, action) {
		const node = this._getNode(nodeOrId);
		if (!node) {
			throw new Error('Node not found');
		}

		const nodeIndex = this._getNodeIndex(node);
		if (nodeIndex < 0) {
			throw new Error('Node not in workflow');
		}

		// Get step value from node
		const step = this._getNodeValue(node, 'step') || 1;

		// Make API call
		const response = await fetch(`${this.apiBase}/counter`, {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({
				node_index: nodeIndex,
				action: action,
				step: step
			})
		});

		if (!response.ok) {
			const error = await response.json().catch(() => ({ detail: response.statusText }));
			throw new Error(error.detail || 'API request failed');
		}

		return await response.json();
	}

	/**
	 * Initialize counter displays when workflow loads.
	 * Ensures all Counter nodes show their current values.
	 */
	_initializeCounterDisplays() {
		for (const node of this.graph.nodes) {
			if (this._isCounterNode(node)) {
				// Ensure value property is set for display
				const value = this._getNodeValue(node, 'value') || 0;
				this._setNodeValue(node, 'value', value);
			}
		}
	}
}

// ========================================================================
// EXTENSION REGISTRATION
// ========================================================================

// Register with the extension registry if available
if (typeof extensionRegistry !== 'undefined') {
	extensionRegistry.register('tutorial', TutorialExtension);
}

// Also make available globally for manual instantiation
if (typeof window !== 'undefined') {
	window.TutorialExtension = TutorialExtension;
}

console.log('[SchemaGraph] Tutorial extension loaded');
