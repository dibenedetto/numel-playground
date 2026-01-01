// ========================================================================
// SCHEMAGRAPH MULTI-SLOT UI EXTENSION
// Adds graphical interface for managing multi-input/output slots
// ========================================================================

class MultiSlotUIExtension extends SchemaGraphExtension {
	constructor(app) {
		super(app);
		this._editingNode = null;
		this._editingField = null;
		this._hoveredAddButton = null;
		this._hoveredRemoveButton = null;
	}

	_registerNodeTypes() {
		// No new node types
	}

	_setupEventListeners() {
		this.on('mouse:move', (data) => this._onMouseMove(data));
		this.on('mouse:down', (data) => this._onMouseDown(data));
		this.on('contextmenu', (data) => this._onContextMenu(data));
	}

	_extendAPI() {
		const self = this;
		
		this.app.api = this.app.api || {};
		this.app.api.multiSlotUI = {
			showManager: (nodeOrId, fieldName, type) => self._showSlotManager(nodeOrId, fieldName, type),
			hideManager: () => self._hideSlotManager()
		};
	}

	_injectStyles() {
		if (document.getElementById('sg-multislot-ui-styles')) return;
		
		const style = document.createElement('style');
		style.id = 'sg-multislot-ui-styles';
		style.textContent = `
			/* Slot Manager Modal */
			.sg-slot-manager-overlay {
				position: fixed;
				top: 0;
				left: 0;
				right: 0;
				bottom: 0;
				background: rgba(0, 0, 0, 0.6);
				z-index: 10000;
				display: flex;
				align-items: center;
				justify-content: center;
			}
			
			.sg-slot-manager {
				background: #1a1d21;
				border: 1px solid #3a3f44;
				border-radius: 8px;
				min-width: 320px;
				max-width: 480px;
				max-height: 80vh;
				display: flex;
				flex-direction: column;
				box-shadow: 0 8px 32px rgba(0, 0, 0, 0.5);
			}
			
			.sg-slot-manager-header {
				display: flex;
				justify-content: space-between;
				align-items: center;
				padding: 12px 16px;
				border-bottom: 1px solid #3a3f44;
				background: linear-gradient(135deg, #2d5a7b, #1e3a5f);
				border-radius: 8px 8px 0 0;
			}
			
			.sg-slot-manager-title {
				font-weight: 600;
				color: #fff;
				font-size: 14px;
			}
			
			.sg-slot-manager-close {
				background: none;
				border: none;
				color: #888;
				font-size: 20px;
				cursor: pointer;
				padding: 0;
				width: 24px;
				height: 24px;
				display: flex;
				align-items: center;
				justify-content: center;
				border-radius: 4px;
			}
			
			.sg-slot-manager-close:hover {
				background: rgba(255, 255, 255, 0.1);
				color: #fff;
			}
			
			.sg-slot-manager-body {
				padding: 16px;
				overflow-y: auto;
				flex: 1;
			}
			
			.sg-slot-manager-list {
				display: flex;
				flex-direction: column;
				gap: 8px;
			}
			
			.sg-slot-item {
				display: flex;
				align-items: center;
				gap: 8px;
				padding: 8px 12px;
				background: rgba(255, 255, 255, 0.05);
				border: 1px solid rgba(255, 255, 255, 0.1);
				border-radius: 6px;
			}
			
			.sg-slot-item-key {
				flex: 1;
				background: rgba(0, 0, 0, 0.3);
				border: 1px solid rgba(255, 255, 255, 0.1);
				border-radius: 4px;
				padding: 6px 10px;
				color: #fff;
				font-size: 13px;
				font-family: 'Monaco', 'Menlo', monospace;
			}
			
			.sg-slot-item-key:focus {
				outline: none;
				border-color: #2d5a7b;
			}
			
			.sg-slot-item-connected {
				font-size: 10px;
				color: #5cb85c;
				padding: 2px 6px;
				background: rgba(92, 184, 92, 0.2);
				border-radius: 3px;
			}
			
			.sg-slot-item-btn {
				background: none;
				border: none;
				color: #888;
				font-size: 14px;
				cursor: pointer;
				padding: 4px;
				border-radius: 4px;
				display: flex;
				align-items: center;
				justify-content: center;
			}
			
			.sg-slot-item-btn:hover {
				background: rgba(255, 255, 255, 0.1);
				color: #fff;
			}
			
			.sg-slot-item-btn.delete:hover {
				background: rgba(217, 83, 79, 0.3);
				color: #f88;
			}
			
			.sg-slot-item-btn:disabled {
				opacity: 0.3;
				cursor: not-allowed;
			}
			
			.sg-slot-manager-footer {
				display: flex;
				justify-content: space-between;
				align-items: center;
				padding: 12px 16px;
				border-top: 1px solid #3a3f44;
				background: rgba(0, 0, 0, 0.2);
				border-radius: 0 0 8px 8px;
			}
			
			.sg-slot-add-row {
				display: flex;
				gap: 8px;
				flex: 1;
			}
			
			.sg-slot-add-input {
				flex: 1;
				background: rgba(0, 0, 0, 0.3);
				border: 1px solid rgba(255, 255, 255, 0.1);
				border-radius: 4px;
				padding: 8px 12px;
				color: #fff;
				font-size: 13px;
			}
			
			.sg-slot-add-input:focus {
				outline: none;
				border-color: #2d5a7b;
			}
			
			.sg-slot-add-input::placeholder {
				color: #555;
			}
			
			.sg-slot-add-btn {
				background: #2d5a7b;
				border: none;
				color: #fff;
				padding: 8px 16px;
				border-radius: 4px;
				cursor: pointer;
				font-size: 13px;
				font-weight: 500;
			}
			
			.sg-slot-add-btn:hover {
				background: #3d7a9b;
			}
			
			.sg-slot-empty {
				text-align: center;
				color: #666;
				padding: 20px;
				font-style: italic;
			}
			
			/* Context menu additions */
			.sg-context-menu-submenu {
				position: relative;
			}
			
			.sg-context-menu-submenu::after {
				content: '▶';
				position: absolute;
				right: 8px;
				font-size: 8px;
				color: #888;
			}
			
			.sg-context-submenu {
				position: absolute;
				left: 100%;
				top: 0;
				background: var(--sg-surface, #1a1a1a);
				border: 1px solid var(--sg-border-color, #333);
				border-radius: 6px;
				min-width: 160px;
				box-shadow: 0 4px 12px rgba(0, 0, 0, 0.4);
				display: none;
				z-index: 1001;
			}
			
			.sg-context-menu-submenu:hover .sg-context-submenu {
				display: block;
			}
		`;
		
		document.head.appendChild(style);
	}

	// ================================================================
	// Mouse Handling for Inline Buttons
	// ================================================================

	_onMouseMove(data) {
		if (this.app.isLocked || this.app.connecting) return;
		
		const [wx, wy] = this.app.screenToWorld(data.coords.screenX, data.coords.screenY);
		
		let foundAdd = null;
		let foundRemove = null;
		
		for (const node of this.graph.nodes) {
			if (!node.isWorkflowNode) continue;
			
			// Check add buttons
			const addButtons = this._getAddButtonPositions(node);
			for (const btn of addButtons) {
				if (this._isPointInButton(wx, wy, btn)) {
					foundAdd = { nodeId: node.id, ...btn };
					break;
				}
			}
			
			// Check remove buttons
			if (!foundAdd) {
				const removeButtons = this._getRemoveButtonPositions(node);
				for (const btn of removeButtons) {
					if (this._isPointInButton(wx, wy, btn)) {
						foundRemove = { nodeId: node.id, ...btn };
						break;
					}
				}
			}
			
			if (foundAdd || foundRemove) break;
		}
		
		const changed = (
			this._hoveredAddButton?.nodeId !== foundAdd?.nodeId ||
			this._hoveredAddButton?.fieldName !== foundAdd?.fieldName ||
			this._hoveredRemoveButton?.nodeId !== foundRemove?.nodeId ||
			this._hoveredRemoveButton?.key !== foundRemove?.key
		);
		
		this._hoveredAddButton = foundAdd;
		this._hoveredRemoveButton = foundRemove;
		
		if (foundAdd || foundRemove) {
			this.app.canvas.style.cursor = 'pointer';
		}
		
		if (changed) {
			this.app.draw?.();
		}
	}

	_onMouseDown(data) {
		if (data.button !== 0 || this.app.isLocked) return;
		
		// Handle add button click
		if (this._hoveredAddButton) {
			data.event.preventDefault();
			data.event.stopPropagation();
			this._handleAddButtonClick(this._hoveredAddButton);
			return true;
		}
		
		// Handle remove button click
		if (this._hoveredRemoveButton) {
			data.event.preventDefault();
			data.event.stopPropagation();
			this._handleRemoveButtonClick(this._hoveredRemoveButton);
			return true;
		}
	}

	_isPointInButton(wx, wy, btn) {
		return wx >= btn.x && wx <= btn.x + btn.w &&
			wy >= btn.y && wy <= btn.y + btn.h;
	}

	_getAddButtonPositions(node) {
		const buttons = [];
		const x = node.pos[0];
		const y = node.pos[1];
		const w = node.size[0];
		
		// Multi-input add buttons
		for (const [fieldName, slotIndices] of Object.entries(node.multiInputSlots || {})) {
			const lastIdx = Math.max(...slotIndices);
			const slotY = y + 33 + lastIdx * 25;
			
			buttons.push({
				fieldName,
				type: 'input',
				x: x + 2,
				y: slotY + 10,
				w: 14,
				h: 14
			});
		}
		
		// Multi-output add buttons
		for (const [fieldName, slotIndices] of Object.entries(node.multiOutputSlots || {})) {
			const lastIdx = Math.max(...slotIndices);
			const slotY = y + 33 + lastIdx * 25;
			
			buttons.push({
				fieldName,
				type: 'output',
				x: x + w - 16,
				y: slotY + 10,
				w: 14,
				h: 14
			});
		}
		
		return buttons;
	}

	_getRemoveButtonPositions(node) {
		const buttons = [];
		const x = node.pos[0];
		const y = node.pos[1];
		const w = node.size[0];
		
		// Multi-input remove buttons (only if more than 1 slot)
		for (const [fieldName, slotIndices] of Object.entries(node.multiInputSlots || {})) {
			if (slotIndices.length <= 1) continue;
			
			for (const slotIdx of slotIndices) {
				const slotName = node.inputs[slotIdx]?.name || '';
				const dotIdx = slotName.indexOf('.');
				const key = dotIdx !== -1 ? slotName.substring(dotIdx + 1) : slotName;
				
				const slotY = y + 33 + slotIdx * 25;
				
				// Check if connected
				const isConnected = !!node.inputs[slotIdx]?.link;
				
				buttons.push({
					fieldName,
					type: 'input',
					key,
					slotIdx,
					isConnected,
					x: x + 2,
					y: slotY - 6,
					w: 12,
					h: 12
				});
			}
		}
		
		// Multi-output remove buttons
		for (const [fieldName, slotIndices] of Object.entries(node.multiOutputSlots || {})) {
			if (slotIndices.length <= 1) continue;
			
			for (const slotIdx of slotIndices) {
				const slotName = node.outputs[slotIdx]?.name || '';
				const dotIdx = slotName.indexOf('.');
				const key = dotIdx !== -1 ? slotName.substring(dotIdx + 1) : slotName;
				
				const slotY = y + 33 + slotIdx * 25;
				
				// Check if connected
				const isConnected = (node.outputs[slotIdx]?.links?.length || 0) > 0;
				
				buttons.push({
					fieldName,
					type: 'output',
					key,
					slotIdx,
					isConnected,
					x: x + w - 14,
					y: slotY - 6,
					w: 12,
					h: 12
				});
			}
		}
		
		return buttons;
	}

	_handleAddButtonClick(btn) {
		const node = this.graph.getNodeById(btn.nodeId);
		if (!node) return;
		
		// Generate unique key
		const existingKeys = btn.type === 'input'
			? this.app.api.workflow.getMultiInputKeys(node, btn.fieldName)
			: this.app.api.workflow.getMultiOutputKeys(node, btn.fieldName);
		
		let newKey = `${btn.fieldName}_${existingKeys.length + 1}`;
		let counter = existingKeys.length + 1;
		while (existingKeys.includes(newKey)) {
			counter++;
			newKey = `${btn.fieldName}_${counter}`;
		}
		
		// Show prompt for custom key name
		const key = prompt(`Enter name for new ${btn.type}:`, newKey);
		if (!key || !key.trim()) return;
		
		const trimmedKey = key.trim().replace(/[^a-zA-Z0-9_]/g, '_');
		
		if (btn.type === 'input') {
			this.app.api.workflow.addMultiInputSlot(node, btn.fieldName, trimmedKey);
		} else {
			this.app.api.workflow.addMultiOutputSlot(node, btn.fieldName, trimmedKey);
		}
	}

	_handleRemoveButtonClick(btn) {
		const node = this.graph.getNodeById(btn.nodeId);
		if (!node) return;
		
		// Confirm if connected
		if (btn.isConnected) {
			if (!confirm(`"${btn.key}" is connected. Remove anyway?`)) {
				return;
			}
		}
		
		if (btn.type === 'input') {
			this.app.api.workflow.removeMultiInputSlot(node, btn.fieldName, btn.key);
		} else {
			this.app.api.workflow.removeMultiOutputSlot(node, btn.fieldName, btn.key);
		}
	}

	// ================================================================
	// Context Menu
	// ================================================================

	_onContextMenu(data) {
		if (this.app.isLocked) return;
		
		const [wx, wy] = this.app.screenToWorld(data.coords.screenX, data.coords.screenY);
		
		for (const node of this.graph.nodes) {
			if (!node.isWorkflowNode) continue;
			
			// Check if clicking on node
			if (wx >= node.pos[0] && wx <= node.pos[0] + node.size[0] &&
				wy >= node.pos[1] && wy <= node.pos[1] + node.size[1]) {
				
				// Check if node has multi-slots
				const hasMultiInputs = Object.keys(node.multiInputSlots || {}).length > 0;
				const hasMultiOutputs = Object.keys(node.multiOutputSlots || {}).length > 0;
				
				if (hasMultiInputs || hasMultiOutputs) {
					// Check if clicking on a specific slot
					const slotInfo = this._getSlotAtPosition(node, wx, wy);
					
					if (slotInfo) {
						data.event.preventDefault();
						this._showSlotContextMenu(node, slotInfo, data.coords);
						return true;
					}
				}
			}
		}
	}

	_getSlotAtPosition(node, wx, wy) {
		const x = node.pos[0];
		const y = node.pos[1];
		const w = node.size[0];
		
		// Check inputs
		for (let i = 0; i < node.inputs.length; i++) {
			const slotY = y + 33 + i * 25;
			const slotX = x;
			
			if (wx >= slotX && wx <= slotX + 60 &&
				wy >= slotY - 10 && wy <= slotY + 15) {
				
				// Find which multi-field this belongs to
				for (const [fieldName, indices] of Object.entries(node.multiInputSlots || {})) {
					if (indices.includes(i)) {
						const slotName = node.inputs[i].name;
						const dotIdx = slotName.indexOf('.');
						const key = dotIdx !== -1 ? slotName.substring(dotIdx + 1) : slotName;
						
						return {
							type: 'input',
							fieldName,
							key,
							slotIdx: i,
							isConnected: !!node.inputs[i].link
						};
					}
				}
			}
		}
		
		// Check outputs
		for (let i = 0; i < node.outputs.length; i++) {
			const slotY = y + 33 + i * 25;
			const slotX = x + w - 60;
			
			if (wx >= slotX && wx <= slotX + 60 &&
				wy >= slotY - 10 && wy <= slotY + 15) {
				
				for (const [fieldName, indices] of Object.entries(node.multiOutputSlots || {})) {
					if (indices.includes(i)) {
						const slotName = node.outputs[i].name;
						const dotIdx = slotName.indexOf('.');
						const key = dotIdx !== -1 ? slotName.substring(dotIdx + 1) : slotName;
						
						return {
							type: 'output',
							fieldName,
							key,
							slotIdx: i,
							isConnected: (node.outputs[i].links?.length || 0) > 0
						};
					}
				}
			}
		}
		
		return null;
	}

	_showSlotContextMenu(node, slotInfo, coords) {
		const menu = this._getOrCreateContextMenu();
		
		const keys = slotInfo.type === 'input'
			? this.app.api.workflow.getMultiInputKeys(node, slotInfo.fieldName)
			: this.app.api.workflow.getMultiOutputKeys(node, slotInfo.fieldName);
		
		const canRemove = keys.length > 1;
		
		menu.innerHTML = `
			<div class="sg-context-menu-title">${slotInfo.fieldName}.${slotInfo.key}</div>
			<div class="sg-context-menu-item" data-action="rename">✏️ Rename</div>
			<div class="sg-context-menu-item" data-action="add">➕ Add Slot</div>
			${canRemove ? `
				<div class="sg-context-menu-item sg-context-menu-delete" data-action="remove">
					➖ Remove${slotInfo.isConnected ? ' (connected)' : ''}
				</div>
			` : ''}
			<div class="sg-context-menu-divider"></div>
			<div class="sg-context-menu-item" data-action="manage">⚙️ Manage All Slots...</div>
		`;
		
		menu.style.left = coords.clientX + 'px';
		menu.style.top = coords.clientY + 'px';
		menu.style.display = 'block';
		
		menu.querySelectorAll('.sg-context-menu-item').forEach(item => {
			item.onclick = () => {
				this._handleSlotContextAction(item.dataset.action, node, slotInfo);
				menu.style.display = 'none';
			};
		});
		
		setTimeout(() => {
			document.addEventListener('click', () => {
				menu.style.display = 'none';
			}, { once: true });
		}, 0);
	}

	_handleSlotContextAction(action, node, slotInfo) {
		switch (action) {
			case 'rename':
				const newKey = prompt(`Rename "${slotInfo.key}" to:`, slotInfo.key);
				if (newKey && newKey.trim() && newKey !== slotInfo.key) {
					const trimmedKey = newKey.trim().replace(/[^a-zA-Z0-9_]/g, '_');
					if (slotInfo.type === 'input') {
						this.app.api.workflow.renameMultiInputSlot(node, slotInfo.fieldName, slotInfo.key, trimmedKey);
					} else {
						this.app.api.workflow.renameMultiOutputSlot(node, slotInfo.fieldName, slotInfo.key, trimmedKey);
					}
				}
				break;
				
			case 'add':
				this._handleAddButtonClick({
					nodeId: node.id,
					fieldName: slotInfo.fieldName,
					type: slotInfo.type
				});
				break;
				
			case 'remove':
				if (slotInfo.isConnected) {
					if (!confirm(`"${slotInfo.key}" is connected. Remove anyway?`)) return;
				}
				if (slotInfo.type === 'input') {
					this.app.api.workflow.removeMultiInputSlot(node, slotInfo.fieldName, slotInfo.key);
				} else {
					this.app.api.workflow.removeMultiOutputSlot(node, slotInfo.fieldName, slotInfo.key);
				}
				break;
				
			case 'manage':
				this._showSlotManager(node, slotInfo.fieldName, slotInfo.type);
				break;
		}
	}

	_getOrCreateContextMenu() {
		let menu = document.getElementById('sg-multislot-context-menu');
		if (!menu) {
			menu = document.createElement('div');
			menu.id = 'sg-multislot-context-menu';
			menu.className = 'sg-context-menu';
			document.body.appendChild(menu);
		}
		return menu;
	}

	// ================================================================
	// Slot Manager Modal
	// ================================================================

	_showSlotManager(nodeOrId, fieldName, type) {
		const node = typeof nodeOrId === 'object' ? nodeOrId : this.graph.getNodeById(nodeOrId);
		if (!node) return;
		
		this._editingNode = node;
		this._editingField = { fieldName, type };
		
		// Remove existing modal
		this._hideSlotManager();
		
		// Create modal
		const overlay = document.createElement('div');
		overlay.id = 'sg-slot-manager-overlay';
		overlay.className = 'sg-slot-manager-overlay';
		
		overlay.innerHTML = this._buildSlotManagerHTML(node, fieldName, type);
		document.body.appendChild(overlay);
		
		this._bindSlotManagerEvents(overlay, node, fieldName, type);
	}

	_buildSlotManagerHTML(node, fieldName, type) {
		const keys = type === 'input'
			? this.app.api.workflow.getMultiInputKeys(node, fieldName)
			: this.app.api.workflow.getMultiOutputKeys(node, fieldName);
		
		const slots = type === 'input' ? node.inputs : node.outputs;
		const slotsMap = type === 'input' ? node.multiInputSlots : node.multiOutputSlots;
		const slotIndices = slotsMap[fieldName] || [];
		
		let listHTML = '';
		
		if (keys.length === 0) {
			listHTML = '<div class="sg-slot-empty">No slots defined</div>';
		} else {
			for (let i = 0; i < keys.length; i++) {
				const key = keys[i];
				const slotIdx = slotIndices[i];
				const slot = slots[slotIdx];
				
				const isConnected = type === 'input' 
					? !!slot?.link 
					: (slot?.links?.length || 0) > 0;
				
				listHTML += `
					<div class="sg-slot-item" data-key="${key}" data-index="${slotIdx}">
						<input type="text" class="sg-slot-item-key" value="${key}" data-original="${key}">
						${isConnected ? '<span class="sg-slot-item-connected">connected</span>' : ''}
						<button class="sg-slot-item-btn" data-action="move-up" title="Move up" ${i === 0 ? 'disabled' : ''}>↑</button>
						<button class="sg-slot-item-btn" data-action="move-down" title="Move down" ${i === keys.length - 1 ? 'disabled' : ''}>↓</button>
						<button class="sg-slot-item-btn delete" data-action="remove" title="Remove" ${keys.length <= 1 ? 'disabled' : ''}>✕</button>
					</div>
				`;
			}
		}
		
		return `
			<div class="sg-slot-manager">
				<div class="sg-slot-manager-header">
					<span class="sg-slot-manager-title">
						${type === 'input' ? '📥' : '📤'} ${fieldName} (${type})
					</span>
					<button class="sg-slot-manager-close">&times;</button>
				</div>
				<div class="sg-slot-manager-body">
					<div class="sg-slot-manager-list">
						${listHTML}
					</div>
				</div>
				<div class="sg-slot-manager-footer">
					<div class="sg-slot-add-row">
						<input type="text" class="sg-slot-add-input" placeholder="New slot name...">
						<button class="sg-slot-add-btn">Add</button>
					</div>
				</div>
			</div>
		`;
	}

	_bindSlotManagerEvents(overlay, node, fieldName, type) {
		// Close button
		overlay.querySelector('.sg-slot-manager-close').onclick = () => {
			this._hideSlotManager();
		};
		
		// Click outside to close
		overlay.onclick = (e) => {
			if (e.target === overlay) {
				this._hideSlotManager();
			}
		};
		
		// Escape to close
		const escHandler = (e) => {
			if (e.key === 'Escape') {
				this._hideSlotManager();
				document.removeEventListener('keydown', escHandler);
			}
		};
		document.addEventListener('keydown', escHandler);
		
		// Add slot
		const addInput = overlay.querySelector('.sg-slot-add-input');
		const addBtn = overlay.querySelector('.sg-slot-add-btn');
		
		const addSlot = () => {
			const key = addInput.value.trim().replace(/[^a-zA-Z0-9_]/g, '_');
			if (!key) return;
			
			const success = type === 'input'
				? this.app.api.workflow.addMultiInputSlot(node, fieldName, key)
				: this.app.api.workflow.addMultiOutputSlot(node, fieldName, key);
			
			if (success) {
				addInput.value = '';
				this._refreshSlotManager(overlay, node, fieldName, type);
			} else {
				addInput.classList.add('error');
				setTimeout(() => addInput.classList.remove('error'), 500);
			}
		};
		
		addBtn.onclick = addSlot;
		addInput.onkeydown = (e) => {
			if (e.key === 'Enter') addSlot();
		};
		
		// Bind item events
		this._bindSlotItemEvents(overlay, node, fieldName, type);
	}

	_bindSlotItemEvents(overlay, node, fieldName, type) {
		const items = overlay.querySelectorAll('.sg-slot-item');
		
		items.forEach(item => {
			const keyInput = item.querySelector('.sg-slot-item-key');
			const originalKey = keyInput.dataset.original;
			
			// Rename on blur
			keyInput.onblur = () => {
				const newKey = keyInput.value.trim().replace(/[^a-zA-Z0-9_]/g, '_');
				if (newKey && newKey !== originalKey) {
					const success = type === 'input'
						? this.app.api.workflow.renameMultiInputSlot(node, fieldName, originalKey, newKey)
						: this.app.api.workflow.renameMultiOutputSlot(node, fieldName, originalKey, newKey);
					
					if (success) {
						keyInput.dataset.original = newKey;
					} else {
						keyInput.value = originalKey;
					}
				} else {
					keyInput.value = originalKey;
				}
			};
			
			keyInput.onkeydown = (e) => {
				if (e.key === 'Enter') keyInput.blur();
				if (e.key === 'Escape') {
					keyInput.value = originalKey;
					keyInput.blur();
				}
			};
			
			// Button actions
			item.querySelectorAll('.sg-slot-item-btn').forEach(btn => {
				btn.onclick = () => {
					const action = btn.dataset.action;
					const key = item.dataset.key;
					
					switch (action) {
						case 'remove':
							if (type === 'input') {
								this.app.api.workflow.removeMultiInputSlot(node, fieldName, key);
							} else {
								this.app.api.workflow.removeMultiOutputSlot(node, fieldName, key);
							}
							this._refreshSlotManager(overlay, node, fieldName, type);
							break;
							
						case 'move-up':
						case 'move-down':
							// TODO: Implement reordering
							console.log('Reordering not yet implemented');
							break;
					}
				};
			});
		});
	}

	_refreshSlotManager(overlay, node, fieldName, type) {
		const body = overlay.querySelector('.sg-slot-manager-body');
		
		const keys = type === 'input'
			? this.app.api.workflow.getMultiInputKeys(node, fieldName)
			: this.app.api.workflow.getMultiOutputKeys(node, fieldName);
		
		const slots = type === 'input' ? node.inputs : node.outputs;
		const slotsMap = type === 'input' ? node.multiInputSlots : node.multiOutputSlots;
		const slotIndices = slotsMap[fieldName] || [];
		
		let listHTML = '';
		
		if (keys.length === 0) {
			listHTML = '<div class="sg-slot-empty">No slots defined</div>';
		} else {
			for (let i = 0; i < keys.length; i++) {
				const key = keys[i];
				const slotIdx = slotIndices[i];
				const slot = slots[slotIdx];
				
				const isConnected = type === 'input' 
					? !!slot?.link 
					: (slot?.links?.length || 0) > 0;
				
				listHTML += `
					<div class="sg-slot-item" data-key="${key}" data-index="${slotIdx}">
						<input type="text" class="sg-slot-item-key" value="${key}" data-original="${key}">
						${isConnected ? '<span class="sg-slot-item-connected">connected</span>' : ''}
						<button class="sg-slot-item-btn" data-action="move-up" title="Move up" ${i === 0 ? 'disabled' : ''}>↑</button>
						<button class="sg-slot-item-btn" data-action="move-down" title="Move down" ${i === keys.length - 1 ? 'disabled' : ''}>↓</button>
						<button class="sg-slot-item-btn delete" data-action="remove" title="Remove" ${keys.length <= 1 ? 'disabled' : ''}>✕</button>
					</div>
				`;
			}
		}
		
		body.innerHTML = `<div class="sg-slot-manager-list">${listHTML}</div>`;
		this._bindSlotItemEvents(overlay.closest('.sg-slot-manager-overlay'), node, fieldName, type);
	}

	_hideSlotManager() {
		const overlay = document.getElementById('sg-slot-manager-overlay');
		if (overlay) {
			overlay.remove();
		}
		this._editingNode = null;
		this._editingField = null;
	}
}

// ========================================================================
// Extend drawNode to show multi-slot buttons
// ========================================================================

function extendDrawNodeForMultiSlot(SchemaGraphAppClass) {
	const originalDrawNode = SchemaGraphAppClass.prototype.drawNode;
	
	SchemaGraphAppClass.prototype.drawNode = function(node, colors) {
		originalDrawNode.call(this, node, colors);
		
		// Draw multi-slot UI elements
		if (this.multiSlotUI && node.isWorkflowNode) {
			this.multiSlotUI._drawMultiSlotButtons(node, colors);
		}
	};
}

// Add drawing method to extension
MultiSlotUIExtension.prototype._drawMultiSlotButtons = function(node, colors) {
	const ctx = this.app.ctx;
	const scale = this.app.camera.scale;
	const textScale = this.app.getTextScale();
	
	// Draw add buttons
	const addButtons = this._getAddButtonPositions(node);
	for (const btn of addButtons) {
		const isHovered = this._hoveredAddButton?.nodeId === node.id &&
						this._hoveredAddButton?.fieldName === btn.fieldName &&
						this._hoveredAddButton?.type === btn.type;
		
		ctx.fillStyle = isHovered ? 'rgba(92, 184, 92, 0.8)' : 'rgba(92, 184, 92, 0.4)';
		ctx.beginPath();
		ctx.arc(btn.x + btn.w/2, btn.y + btn.h/2, btn.w/2, 0, Math.PI * 2);
		ctx.fill();
		
		ctx.fillStyle = '#fff';
		ctx.font = `bold ${10 * textScale}px sans-serif`;
		ctx.textAlign = 'center';
		ctx.textBaseline = 'middle';
		ctx.fillText('+', btn.x + btn.w/2, btn.y + btn.h/2);
	}
	
	// Draw remove buttons (only when hovering near them)
	const removeButtons = this._getRemoveButtonPositions(node);
	for (const btn of removeButtons) {
		const isHovered = this._hoveredRemoveButton?.nodeId === node.id &&
						this._hoveredRemoveButton?.key === btn.key;
		
		// Only show if hovering
		if (!isHovered && !this._isMouseNearNode(node)) continue;
		
		ctx.fillStyle = isHovered ? 'rgba(217, 83, 79, 0.8)' : 'rgba(217, 83, 79, 0.3)';
		ctx.beginPath();
		ctx.arc(btn.x + btn.w/2, btn.y + btn.h/2, btn.w/2, 0, Math.PI * 2);
		ctx.fill();
		
		ctx.fillStyle = '#fff';
		ctx.font = `bold ${8 * textScale}px sans-serif`;
		ctx.textAlign = 'center';
		ctx.textBaseline = 'middle';
		ctx.fillText('−', btn.x + btn.w/2, btn.y + btn.h/2);
	}
};

MultiSlotUIExtension.prototype._isMouseNearNode = function(node) {
	const [mx, my] = this.app.screenToWorld(this.app.mousePos[0], this.app.mousePos[1]);
	const margin = 20;
	
	return mx >= node.pos[0] - margin &&
		mx <= node.pos[0] + node.size[0] + margin &&
		my >= node.pos[1] - margin &&
		my <= node.pos[1] + node.size[1] + margin;
};

// ========================================================================
// AUTO-INITIALIZATION
// ========================================================================

if (typeof SchemaGraphApp !== 'undefined') {
	extendDrawNodeForMultiSlot(SchemaGraphApp);
	
	if (typeof extensionRegistry !== 'undefined') {
		extensionRegistry.register('multiSlotUI', MultiSlotUIExtension);
	} else {
		const originalSetup = SchemaGraphApp.prototype.setupEventListeners;
		SchemaGraphApp.prototype.setupEventListeners = function() {
			originalSetup.call(this);
			this.multiSlotUI = new MultiSlotUIExtension(this);
		};
	}
	
	console.log('✨ SchemaGraph Multi-Slot UI extension loaded');
}

// ========================================================================
// EXPORTS
// ========================================================================

if (typeof module !== 'undefined' && module.exports) {
	module.exports = { MultiSlotUIExtension, extendDrawNodeForMultiSlot };
}

if (typeof window !== 'undefined') {
	window.MultiSlotUIExtension = MultiSlotUIExtension;
}
