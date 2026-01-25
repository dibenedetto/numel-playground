// ========================================================================
// SCHEMAGRAPH CHAT EXTENSION
// Adds @node_chat decorator support for interactive chat nodes
// Depends on: schemagraph-extensions.js
// ========================================================================

console.log('[SchemaGraph] Loading chat extension...');

const ChatState = Object.freeze({
	IDLE: 'idle',
	CONNECTING: 'connecting',
	READY: 'ready',
	SENDING: 'sending',
	STREAMING: 'streaming',
	ERROR: 'error'
});

const MessageRole = Object.freeze({
	USER: 'user',
	ASSISTANT: 'assistant',
	SYSTEM: 'system',
	ERROR: 'error'
});

// ========================================================================
// Chat Node Mixin
// ========================================================================

const ChatNodeMixin = {
	initChat(config = {}) {
		this.extra = this.extra || {};
		if (!this.extra.chat_id) {
			this.extra.chat_id = this.workflowId || `chat_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
		}

		this.isChat = true;
		this.chatId = this.extra.chat_id;
		this.chatConfig = {
			title: config.title || 'Chat',
			placeholder: config.placeholder || 'Type a message...',
			configField: config.config_field || config.configField || 'config',
			systemPromptField: config.system_prompt_field || config.systemPromptField || null,
			maxMessages: config.max_messages || config.maxMessages || 100,
			showTimestamps: config.show_timestamps ?? config.showTimestamps ?? false,
			streamResponse: config.stream_response ?? config.streamResponse ?? true,
			minWidth: config.min_width || config.minWidth || 300,
			minHeight: config.min_height || config.minHeight || 400,
			headerOffset: 30,
			footerOffset: 20,
			slotWidth: 16,
			...config
		};

		this.chatState = ChatState.IDLE;
		this.chatMessages = [];
		this.chatError = null;
		this._chatOverlay = null;
		this._chatInputValue = '';
		this._chatMinimized = false;
	},

	addMessage(role, content, meta = {}) {
		const message = {
			id: `msg_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
			role,
			content,
			timestamp: Date.now(),
			...meta
		};

		this.chatMessages.push(message);

		if (this.chatMessages.length > this.chatConfig.maxMessages) {
			this.chatMessages = this.chatMessages.slice(-this.chatConfig.maxMessages);
		}

		return message;
	},

	updateLastMessage(content, append = false) {
		if (this.chatMessages.length === 0) return;
		const last = this.chatMessages[this.chatMessages.length - 1];
		last.content = append ? last.content + content : content;
		return last;
	},

	clearMessages() {
		this.chatMessages = [];
	},

	getAgentConfig() {
		const fieldName = this.chatConfig.configField;
		const slotIdx = this.getInputSlotByName?.(fieldName);
		if (slotIdx >= 0) {
			return this.getInputData(slotIdx);
		}
		return null;
	},

	getSystemPrompt() {
		if (!this.chatConfig.systemPromptField) return null;
		const slotIdx = this.getInputSlotByName?.(this.chatConfig.systemPromptField);
		if (slotIdx >= 0) {
			return this.getInputData(slotIdx);
		}
		return null;
	}
};

// ========================================================================
// Chat Overlay Manager
// ========================================================================

class ChatOverlayManager {
	constructor(app, eventBus) {
		this.app = app;
		this.eventBus = eventBus;
		this.overlays = new Map();
		this.nodeRefs = new Map();
		this._sendCallbacks = new Map();

		// Z-index constants - coordinated with other overlays
		this.Z_BASE = 1000;
		this.Z_SELECTED = 10000;
	}

	createOverlay(node) {
		const chatId = node.chatId;
		console.log(`[ChatOverlay] Creating overlay for node ${node.id}, chatId=${chatId}`);

		if (this.overlays.has(chatId)) {
			console.log(`[ChatOverlay] Overlay already exists for chatId=${chatId}, rebinding`);
			this.nodeRefs.set(chatId, node);
			const overlay = this.overlays.get(chatId);
			this._rebindOverlayEvents(node, overlay);
			this._updateOverlayPosition(node, overlay);
			return overlay;
		}

		const overlay = document.createElement('div');
		overlay.className = 'sg-chat-overlay';
		overlay.id = `sg-chat-${chatId}`;
		overlay.innerHTML = this._buildChatHTML(node);

		const container = this.app.canvas?.parentElement || document.body;
		container.appendChild(overlay);

		this.overlays.set(chatId, overlay);
		this.nodeRefs.set(chatId, node);

		this._bindOverlayEvents(node, overlay);
		this._updateOverlayPosition(node, overlay);

		return overlay;
	}

	_rebindOverlayEvents(node, overlay) {
		const input = overlay.querySelector('.sg-chat-input');
		const sendBtn = overlay.querySelector('.sg-chat-send-btn');
		const clearBtn = overlay.querySelector('.sg-chat-clear-btn');

		const newSendBtn = sendBtn?.cloneNode(true);
		const newClearBtn = clearBtn?.cloneNode(true);
		const newInput = input?.cloneNode(true);

		sendBtn?.parentNode?.replaceChild(newSendBtn, sendBtn);
		clearBtn?.parentNode?.replaceChild(newClearBtn, clearBtn);
		input?.parentNode?.replaceChild(newInput, input);

		this._bindOverlayEvents(node, overlay);
	}

	_bindOverlayEvents(node, overlay) {
		const chatId = node.chatId;
		const input = overlay.querySelector('.sg-chat-input');
		const sendBtn = overlay.querySelector('.sg-chat-send-btn');
		const clearBtn = overlay.querySelector('.sg-chat-clear-btn');

		const getNode = () => this.nodeRefs.get(chatId);

		sendBtn?.addEventListener('click', () => {
			const currentNode = getNode();
			if (currentNode) this._handleSend(currentNode, input);
		});

		input?.addEventListener('keydown', (e) => {
			if (e.key === 'Enter' && !e.shiftKey) {
				e.preventDefault();
				const currentNode = getNode();
				if (currentNode) this._handleSend(currentNode, input);
			}
		});

		input?.addEventListener('input', () => {
			input.style.height = 'auto';
			input.style.height = Math.min(input.scrollHeight, 100) + 'px';
			const currentNode = getNode();
			if (currentNode) currentNode._chatInputValue = input.value;
		});

		clearBtn?.addEventListener('click', () => {
			const currentNode = getNode();
			if (currentNode) {
				currentNode.clearMessages();
				this.updateMessages(currentNode);
				this.eventBus.emit('chat:cleared', { nodeId: currentNode.id, chatId });
			}
		});

		overlay.addEventListener('mousedown', (e) => {
			const currentNode = getNode();
			if (currentNode) {
				this.app.graph.selectedNode = currentNode;
				currentNode.is_selected = true;
			}
			this.updateAllPositions();

			const rect = overlay.getBoundingClientRect();
			const x = e.clientX - rect.left;
			const y = e.clientY - rect.top;
			const edgeThreshold = 8;
			if (x > edgeThreshold && x < rect.width - edgeThreshold &&
				y > edgeThreshold && y < rect.height - edgeThreshold) {
				e.stopPropagation();
			}
		});

		overlay.addEventListener('wheel', (e) => e.stopPropagation(), { passive: true });
	}

	getNodeByChatId(chatId) {
		return this.nodeRefs.get(chatId);
	}

	updateOverlayPosition(node) {
		const overlay = this.overlays.get(node.chatId);
		if (overlay) {
			this._updateOverlayPosition(node, overlay);
		}
	}

	updateMessages(node) {
		const overlay = this.overlays.get(node.chatId);
		if (!overlay) return;

		const container = overlay.querySelector('.sg-chat-messages');
		if (!container) return;

		container.innerHTML = node.chatMessages.map(msg => this._renderMessage(msg, node)).join('');
		container.scrollTop = container.scrollHeight;
	}

	updateStatus(node) {
		const overlay = this.overlays.get(node.chatId);
		if (!overlay) return;

		const container = overlay.querySelector('.sg-chat-container');
		const statusText = overlay.querySelector('.sg-chat-status-text');
		const sendBtn = overlay.querySelector('.sg-chat-send-btn');

		if (container) {
			container.className = `sg-chat-container sg-chat-state-${node.chatState}`;
		}
		if (statusText) {
			statusText.textContent = this._getStatusText(node);
		}
		if (sendBtn) {
			const isBusy = node.chatState === ChatState.SENDING || node.chatState === ChatState.STREAMING;
			sendBtn.disabled = isBusy;
		}
	}

	removeOverlay(chatId) {
		const overlay = this.overlays.get(chatId);
		if (overlay) {
			overlay.remove();
			this.overlays.delete(chatId);
		}
		this.nodeRefs.delete(chatId);
		this._sendCallbacks.delete(chatId);
	}

	removeAllOverlays() {
		for (const overlay of this.overlays.values()) {
			overlay.remove();
		}
		this.overlays.clear();
		this.nodeRefs.clear();
		this._sendCallbacks.clear();
	}

	updateAllPositions() {
		for (const [chatId, overlay] of this.overlays) {
			const node = this.nodeRefs.get(chatId);
			if (node) {
				this._updateOverlayPosition(node, overlay);
			} else {
				console.warn(`[ChatOverlay] No node ref found for chatId=${chatId}`);
			}
		}
	}

	_buildChatHTML(node) {
		const config = node.chatConfig || {};
		const stateClass = `sg-chat-state-${node.chatState || 'idle'}`;

		return `
			<div class="sg-chat-container ${stateClass}">
				<div class="sg-chat-status">
					<span class="sg-chat-status-indicator"></span>
					<span class="sg-chat-status-text">${this._getStatusText(node)}</span>
					<div class="sg-chat-status-actions">
						<button class="sg-chat-btn sg-chat-clear-btn" title="Clear chat">&#128465;</button>
					</div>
				</div>
				<div class="sg-chat-messages"></div>
				<div class="sg-chat-input-container">
					<textarea
						class="sg-chat-input"
						placeholder="${config.placeholder || 'Type a message...'}"
						rows="1"
					></textarea>
					<button class="sg-chat-send-btn" title="Send">
						<span class="sg-chat-send-icon">&#10148;</span>
					</button>
				</div>
			</div>
		`;
	}

	_getStatusText(node) {
		switch (node.chatState) {
			case ChatState.IDLE: return 'Not connected';
			case ChatState.CONNECTING: return 'Connecting...';
			case ChatState.READY: return 'Ready';
			case ChatState.SENDING: return 'Sending...';
			case ChatState.STREAMING: return 'Receiving...';
			case ChatState.ERROR: return node.chatError || 'Error';
			default: return '';
		}
	}

	_handleSend(node, input) {
		if (this.app.isLocked) return;

		const text = input?.value?.trim();
		if (!text) return;

		if (node.chatState === ChatState.SENDING || node.chatState === ChatState.STREAMING) {
			return;
		}

		node.addMessage(MessageRole.USER, text);
		this.updateMessages(node);

		input.value = '';
		input.style.height = 'auto';
		node._chatInputValue = '';

		this.eventBus.emit('chat:send', {
			nodeId: node.id,
			chatId: node.chatId,
			message: text,
			config: node.getAgentConfig(),
			systemPrompt: node.getSystemPrompt(),
			history: node.chatMessages.slice(0, -1),
			node
		});

		const callback = this._sendCallbacks.get(node.chatId);
		if (callback) {
			node.chatState = ChatState.SENDING;
			this.updateStatus(node);

			try {
				callback(node, text, {
					config: node.getAgentConfig(),
					systemPrompt: node.getSystemPrompt(),
					history: node.chatMessages.slice(0, -1)
				});
			} catch (err) {
				node.chatState = ChatState.ERROR;
				node.chatError = err.message;
				this.updateStatus(node);
			}
		}
	}

	registerSendCallback(nodeId, callback) {
		this._sendCallbacks.set(nodeId, callback);
	}

	unregisterSendCallback(nodeId) {
		this._sendCallbacks.delete(nodeId);
	}

	_updateOverlayPosition(node, overlay) {
		const camera = this.app.camera;

		const nodeScreenX = node.pos[0] * camera.scale + camera.x;
		const nodeScreenY = node.pos[1] * camera.scale + camera.y;
		const nodeScreenW = node.size[0] * camera.scale;
		const nodeScreenH = node.size[1] * camera.scale;

		const numInputs = node.inputs?.length || 0;
		const numOutputs = node.outputs?.length || 0;
		const maxSlots = Math.max(numInputs, numOutputs);

		const headerHeight = 30;
		const slotStartY = 33;
		const slotSpacing = 25;
		const footerHeight = 15;
		const horizontalPadding = 12;

		const slotsEndY = slotStartY + (maxSlots * slotSpacing);
		const contentStartY = Math.max(headerHeight, slotsEndY + 5);

		const scale = camera.scale;
		const overlayX = nodeScreenX + (horizontalPadding * scale);
		const overlayY = nodeScreenY + (contentStartY * scale);
		const overlayW = nodeScreenW - (horizontalPadding * 2 * scale);
		const overlayH = nodeScreenH - (contentStartY * scale) - (footerHeight * scale);

		overlay.style.left = `${overlayX}px`;
		overlay.style.top = `${overlayY}px`;
		overlay.style.width = `${Math.max(overlayW, 80)}px`;
		overlay.style.height = `${Math.max(overlayH, 60)}px`;

		// Z-index management
		const isSelected = this._isNodeSelected(node);
		overlay.style.zIndex = isSelected ? this.Z_SELECTED : this.Z_BASE;

		// Hide if too small
		const minVisibleSize = 50;
		const visible = camera.scale > 0.25 &&
			overlayW > minVisibleSize &&
			overlayH > minVisibleSize;

		overlay.style.display = visible ? 'block' : 'none';
		overlay.style.opacity = Math.min(1, (camera.scale - 0.25) * 3);
	}

	_isNodeSelected(node) {
		const graph = this.app.graph;

		if (graph.selectedNodes?.has?.(node.id)) return true;
		if (graph.selectedNodes?.has?.(node)) return true;
		if (graph.selected_nodes?.includes?.(node)) return true;
		if (Array.isArray(graph.selectedNodes) && graph.selectedNodes.includes(node)) return true;
		if (this.app.selectedNode === node) return true;
		if (graph.selectedNode === node) return true;
		if (node.is_selected) return true;

		return false;
	}

	_renderMessage(msg, node) {
		const roleClass = `sg-chat-msg-${msg.role}`;
		const timestamp = node.chatConfig?.showTimestamps
			? `<span class="sg-chat-msg-time">${new Date(msg.timestamp).toLocaleTimeString()}</span>`
			: '';

		const content = this._renderContent(msg.content);

		return `
			<div class="sg-chat-msg ${roleClass}">
				<div class="sg-chat-msg-header">
					<span class="sg-chat-msg-role">${this._getRoleName(msg.role)}</span>
					${timestamp}
				</div>
				<div class="sg-chat-msg-content">${content}</div>
			</div>
		`;
	}

	_getRoleName(role) {
		switch (role) {
			case MessageRole.USER: return 'You';
			case MessageRole.ASSISTANT: return 'Assistant';
			case MessageRole.SYSTEM: return 'System';
			case MessageRole.ERROR: return 'Error';
			default: return role;
		}
	}

	_renderContent(content) {
		if (!content) return '';

		let html = content
			.replace(/&/g, '&amp;')
			.replace(/</g, '&lt;')
			.replace(/>/g, '&gt;');

		html = html.replace(/```(\w*)\n?([\s\S]*?)```/g,
			'<pre class="sg-chat-code"><code>$2</code></pre>');
		html = html.replace(/`([^`]+)`/g, '<code class="sg-chat-inline-code">$1</code>');
		html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
		html = html.replace(/\*([^*]+)\*/g, '<em>$1</em>');
		html = html.replace(/\n/g, '<br>');

		return html;
	}

	bringToFront(chatId) {
		const overlay = this.overlays.get(chatId);
		if (overlay) {
			overlay.style.zIndex = this.Z_SELECTED;
		}
	}

	sendToBack(chatId) {
		const overlay = this.overlays.get(chatId);
		if (overlay) {
			overlay.style.zIndex = this.Z_BASE;
		}
	}
}

// ========================================================================
// Chat Extension
// ========================================================================

class ChatExtension extends SchemaGraphExtension {
	constructor(app) {
		super(app);
		this.overlayManager = new ChatOverlayManager(app, this.eventBus);
		this.schemaChats = {};
	}

	_registerNodeTypes() {
		// No new node types - we enhance existing nodes
	}

	_setupEventListeners() {
		this.on('schema:registered', (e) => {
			this._parseSchemaChats(e.schemaName);
		});

		this.on('node:created', (e) => {
			const node = e.node || this.graph.getNodeById(e.nodeId);
			if (node) {
				this._applyChatToNode(node);
			} else {
				console.warn('[ChatExtension] Could not find node for node:created event', e);
			}
		});

		// Also listen for workflow:loaded to apply chat to loaded nodes
		this.on('workflow:loaded', (e) => {
			for (const node of this.graph.nodes) {
				if (!node.isChat) {
					this._applyChatToNode(node);
				}
			}
		});

		// Listen for workflow imported/synced - this might fire instead of workflow:loaded
		this.on('workflow:imported', (e) => {
			this._reapplyChatToAllNodes();
		});

		this.on('workflow:synced', (e) => {
			this._reapplyChatToAllNodes();
		});

		this.on('node:removed', (e) => {
			this.overlayManager.removeOverlay(e.nodeId);
		});

		this.on('graph:cleared', () => {
			this.overlayManager.removeAllOverlays();
		});

		if (this.app.api?.graph?.clear) {
			const originalApiClear = this.app.api.graph.clear.bind(this.app.api.graph);
			const self = this;
			this.app.api.graph.clear = function (...args) {
				self.overlayManager.removeAllOverlays();
				return originalApiClear(...args);
			};
		}

		this.on('workflow:imported', () => {
			this._cleanupOrphanedOverlays();
		});

		this.on('camera:moved', () => this.overlayManager.updateAllPositions());
		this.on('camera:zoomed', () => this.overlayManager.updateAllPositions());
		this.on('node:moved', (e) => {
			const node = this.graph.getNodeById(e.nodeId);
			if (node?.isChat) {
				this.overlayManager.updateOverlayPosition(node);
			}
		});
		this.on('node:resized', (e) => {
			const node = this.graph.getNodeById(e.nodeId);
			if (node?.isChat) {
				this.overlayManager.updateOverlayPosition(node);
			}
		});

		const originalDraw = this.app.draw?.bind(this.app);
		if (originalDraw) {
			const self = this;
			this.app.draw = function () {
				originalDraw();
				self.overlayManager.updateAllPositions();
			};
		}

		this.on('node:selected', () => {
			this.overlayManager.updateAllPositions();
		});

		this.on('node:deselected', () => {
			this.overlayManager.updateAllPositions();
		});

		this.on('node:clicked', () => {
			this.overlayManager.updateAllPositions();
		});
	}

	_cleanupOrphanedOverlays() {
		const toRemove = [];
		const chatIds = new Set(this.graph.nodes.filter(n => n.isChat).map(n => n.chatId));
		for (const chatId of this.overlayManager.overlays.keys()) {
			if (!chatIds.has(chatId)) {
				toRemove.push(chatId);
			}
		}
		for (const chatId of toRemove) {
			this.overlayManager.removeOverlay(chatId);
		}
	}

	_reapplyChatToAllNodes() {
		for (const node of this.graph.nodes) {
			const schemaName = node.schemaName;
			const modelName = node.modelName;

			if (schemaName && modelName) {
				const chatConfig = this.schemaChats[schemaName]?.[modelName];

				if (chatConfig) {
					try {
						// If node is marked as chat, ensure it's properly initialized
						if (node.isChat) {
							// If chatId is missing but node was marked as chat, reinitialize
							if (!node.chatId && node.extra?.chat_id) {
								Object.assign(node, ChatNodeMixin);
								node.chatId = node.extra.chat_id;
								// Restore other properties if they're missing
								if (!node.chatConfig) {
									node.chatConfig = chatConfig;
								}
							}

							// Check if overlay exists
							const chatId = node.chatId || node.extra?.chat_id;
							if (chatId) {
								const hasOverlay = this.overlayManager.overlays.has(chatId);
								if (!hasOverlay) {
									this.overlayManager.createOverlay(node);
								}
							}
						} else {
							// Node doesn't have chat yet, apply it
							this._applyChatToNode(node);
						}
					} catch (err) {
						console.error(`[ChatExtension] Error processing chat for node ${node.id}:`, err);
					}
				}
			}
		}
	}

	_extendAPI() {
		const self = this;

		this.app.api = this.app.api || {};
		this.app.api.chat = {
			onSend: (nodeOrId, callback) => {
				const nodeId = typeof nodeOrId === 'object' ? nodeOrId.chatId : nodeOrId;
				self.overlayManager.registerSendCallback(nodeId, callback);
			},
			offSend: (nodeOrId) => {
				const nodeId = typeof nodeOrId === 'object' ? nodeOrId.chatId : nodeOrId;
				self.overlayManager.unregisterSendCallback(nodeId);
			},

			addMessage: (nodeOrId, role, content, meta) => {
				const node = typeof nodeOrId === 'object' ? nodeOrId : self.graph.getNodeById(nodeOrId);
				if (node?.isChat) {
					const msg = node.addMessage(role, content, meta);
					self.overlayManager.updateMessages(node);
					return msg;
				}
			},
			updateLastMessage: (nodeOrId, content, append = false) => {
				const node = typeof nodeOrId === 'object' ? nodeOrId : self.graph.getNodeById(nodeOrId);
				if (node?.isChat) {
					node.updateLastMessage(content, append);
					self.overlayManager.updateMessages(node);
				}
			},
			clearMessages: (nodeOrId) => {
				const node = typeof nodeOrId === 'object' ? nodeOrId : self.graph.getNodeById(nodeOrId);
				if (node?.isChat) {
					node.clearMessages();
					self.overlayManager.updateMessages(node);
				}
			},
			getMessages: (nodeOrId) => {
				const node = typeof nodeOrId === 'object' ? nodeOrId : self.graph.getNodeById(nodeOrId);
				return node?.chatMessages || [];
			},
			setSendEnabled: (enabled, nodeOrId) => {
				function isEmpty(value) {
					return (value == null || (typeof value === 'string' && value.trim().length === 0));
				}
				let sendBtns = null;
				if (isEmpty(nodeOrId)) {
					sendBtns = Array.from(document.querySelectorAll('.sg-chat-send-btn'));
				} else {
					const node = typeof nodeOrId === 'object' ? nodeOrId : self.graph.getNodeById(nodeOrId);
					const overlay = self.overlayManager.overlays.get(node?.chatId);
					const sendBtn = overlay?.querySelector('.sg-chat-send-btn');
					sendBtns = [];
					if (sendBtn) sendBtns.push(sendBtn);
				}
				sendBtns.forEach((sendBtn) => {
					sendBtn.disabled = !enabled;
				});
			},

			setState: (nodeOrId, state, error = null) => {
				const node = typeof nodeOrId === 'object' ? nodeOrId : self.graph.getNodeById(nodeOrId);
				if (node?.isChat) {
					node.chatState = state;
					node.chatError = error;
					self.overlayManager.updateStatus(node);
				}
			},
			getState: (nodeOrId) => {
				const node = typeof nodeOrId === 'object' ? nodeOrId : self.graph.getNodeById(nodeOrId);
				return node?.chatState || ChatState.IDLE;
			},

			startStreaming: (nodeOrId) => {
				const node = typeof nodeOrId === 'object' ? nodeOrId : self.graph.getNodeById(nodeOrId);
				if (node?.isChat) {
					node.chatState = ChatState.STREAMING;
					node.addMessage(MessageRole.ASSISTANT, '');
					self.overlayManager.updateStatus(node);
					self.overlayManager.updateMessages(node);
				}
			},
			appendStream: (nodeOrId, chunk) => {
				const node = typeof nodeOrId === 'object' ? nodeOrId : self.graph.getNodeById(nodeOrId);
				if (node?.isChat) {
					node.updateLastMessage(chunk, true);
					self.overlayManager.updateMessages(node);
				}
			},
			endStreaming: (nodeOrId) => {
				const node = typeof nodeOrId === 'object' ? nodeOrId : self.graph.getNodeById(nodeOrId);
				if (node?.isChat) {
					node.chatState = ChatState.READY;
					self.overlayManager.updateStatus(node);
				}
			},

			ChatState,
			MessageRole
		};

		this.app.chatManager = this;
	}

	_injectStyles() {
		if (document.getElementById('sg-chat-styles')) return;

		const style = document.createElement('style');
		style.id = 'sg-chat-styles';
		style.textContent = `
			.sg-chat-overlay {
				position: absolute;
				pointer-events: auto;
				font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
				font-size: 12px;
				border-radius: 4px;
				overflow: hidden;
				transition: opacity 0.15s ease;
			}

			.sg-chat-container {
				display: flex;
				flex-direction: column;
				height: 100%;
				background: var(--sg-bg-secondary, #2a2a2a);
				border: 1px solid var(--sg-border-color, #1a1a1a);
				border-radius: 4px;
				overflow: hidden;
			}

			.sg-chat-status {
				display: flex;
				align-items: center;
				gap: 6px;
				padding: 4px 8px;
				background: var(--sg-bg-tertiary, #353535);
				font-size: 10px;
				color: var(--sg-text-tertiary, #707070);
				border-bottom: 1px solid var(--sg-border-color, #1a1a1a);
			}

			.sg-chat-status-indicator {
				width: 6px;
				height: 6px;
				border-radius: 50%;
				background: var(--sg-text-tertiary, #666);
				flex-shrink: 0;
			}

			.sg-chat-status-text {
				flex: 1;
				overflow: hidden;
				text-overflow: ellipsis;
				white-space: nowrap;
			}

			.sg-chat-status-actions {
				display: flex;
				gap: 2px;
			}

			.sg-chat-state-idle .sg-chat-status-indicator { background: var(--sg-text-tertiary, #666); }
			.sg-chat-state-connecting .sg-chat-status-indicator { background: var(--sg-accent-orange, #f0ad4e); animation: sg-chat-pulse 1s infinite; }
			.sg-chat-state-ready .sg-chat-status-indicator { background: var(--sg-accent-green, #5cb85c); }
			.sg-chat-state-sending .sg-chat-status-indicator { background: var(--sg-accent-blue, #5bc0de); animation: sg-chat-pulse 0.5s infinite; }
			.sg-chat-state-streaming .sg-chat-status-indicator { background: var(--sg-accent-blue, #5bc0de); animation: sg-chat-pulse 0.3s infinite; }
			.sg-chat-state-error .sg-chat-status-indicator { background: var(--sg-accent-red, #d9534f); }

			@keyframes sg-chat-pulse {
				0%, 100% { opacity: 1; }
				50% { opacity: 0.4; }
			}

			.sg-chat-btn {
				background: transparent;
				border: none;
				color: var(--sg-text-tertiary, #888);
				width: 18px;
				height: 18px;
				border-radius: 3px;
				cursor: pointer;
				font-size: 10px;
				display: flex;
				align-items: center;
				justify-content: center;
				padding: 0;
			}

			.sg-chat-btn:hover {
				background: var(--sg-bg-quaternary, rgba(255, 255, 255, 0.1));
				color: var(--sg-text-primary, #fff);
			}

			.sg-chat-messages {
				flex: 1;
				overflow-y: auto;
				padding: 8px;
				display: flex;
				flex-direction: column;
				gap: 8px;
				min-height: 0;
				background: var(--sg-bg-primary, #1e1e1e);
			}

			.sg-chat-msg {
				max-width: 90%;
				padding: 6px 10px;
				border-radius: 8px;
				word-wrap: break-word;
				line-height: 1.4;
			}

			.sg-chat-msg-user {
				align-self: flex-end;
				background: var(--sg-accent-blue, #2d5a7b);
				color: var(--sg-text-primary, #fff);
				border-bottom-right-radius: 2px;
			}

			.sg-chat-msg-assistant {
				align-self: flex-start;
				background: var(--sg-bg-tertiary, #2d3136);
				color: var(--sg-text-secondary, #e0e0e0);
				border-bottom-left-radius: 2px;
			}

			.sg-chat-msg-system {
				align-self: center;
				background: var(--sg-bg-quaternary, rgba(255, 255, 255, 0.05));
				color: var(--sg-text-tertiary, #888);
				font-style: italic;
				font-size: 11px;
			}

			.sg-chat-msg-error {
				align-self: center;
				background: var(--sg-error-bg, rgba(217, 83, 79, 0.2));
				color: var(--sg-error-text, #f88);
				border: 1px solid var(--sg-error-border, rgba(217, 83, 79, 0.3));
			}

			.sg-chat-msg-header {
				display: flex;
				justify-content: space-between;
				align-items: center;
				margin-bottom: 2px;
				font-size: 9px;
				opacity: 0.6;
			}

			.sg-chat-msg-role {
				font-weight: 600;
				text-transform: uppercase;
			}

			.sg-chat-msg-content {
				font-size: 12px;
			}

			.sg-chat-msg-content pre.sg-chat-code {
				background: var(--sg-bg-primary, rgba(0, 0, 0, 0.4));
				padding: 6px;
				border-radius: 3px;
				overflow-x: auto;
				margin: 6px 0;
				font-size: 11px;
				font-family: 'Monaco', 'Menlo', monospace;
			}

			.sg-chat-msg-content code.sg-chat-inline-code {
				background: var(--sg-bg-primary, rgba(0, 0, 0, 0.3));
				padding: 1px 4px;
				border-radius: 2px;
				font-size: 11px;
				font-family: 'Monaco', 'Menlo', monospace;
			}

			.sg-chat-input-container {
				display: flex;
				gap: 6px;
				padding: 8px;
				background: var(--sg-bg-tertiary, rgba(0, 0, 0, 0.2));
				border-top: 1px solid var(--sg-border-color, rgba(255, 255, 255, 0.05));
			}

			.sg-chat-input {
				flex: 1;
				background: var(--sg-bg-primary, rgba(0, 0, 0, 0.3));
				border: 1px solid var(--sg-border-color, rgba(255, 255, 255, 0.1));
				border-radius: 6px;
				padding: 6px 10px;
				color: var(--sg-text-primary, #fff);
				font-size: 12px;
				resize: none;
				min-height: 18px;
				max-height: 100px;
				font-family: inherit;
				line-height: 1.4;
			}

			.sg-chat-input:focus {
				outline: none;
				border-color: var(--sg-accent-blue, rgba(45, 90, 123, 0.8));
			}

			.sg-chat-input::placeholder {
				color: var(--sg-text-quaternary, #555);
			}

			.sg-chat-send-btn {
				background: var(--sg-accent-blue, #2d5a7b);
				border: none;
				color: var(--sg-text-primary, #fff);
				width: 32px;
				height: 32px;
				border-radius: 6px;
				cursor: pointer;
				font-size: 14px;
				display: flex;
				align-items: center;
				justify-content: center;
				transition: background 0.15s;
				flex-shrink: 0;
			}

			.sg-chat-send-btn:hover:not(:disabled) {
				background: var(--sg-accent-blue-light, #3d7a9b);
			}

			.sg-chat-send-btn:disabled {
				background: var(--sg-bg-quaternary, #3a3f44);
				cursor: not-allowed;
				opacity: 0.5;
			}

			.sg-chat-messages::-webkit-scrollbar {
				width: 4px;
			}

			.sg-chat-messages::-webkit-scrollbar-track {
				background: transparent;
			}

			.sg-chat-messages::-webkit-scrollbar-thumb {
				background: var(--sg-bg-quaternary, rgba(255, 255, 255, 0.1));
				border-radius: 2px;
			}

			.sg-chat-messages::-webkit-scrollbar-thumb:hover {
				background: var(--sg-text-tertiary, rgba(255, 255, 255, 0.2));
			}
		`;

		document.head.appendChild(style);
	}

	// ================================================================
	// Schema Parsing
	// ================================================================

	_parseSchemaChats(schemaName) {
		console.log(`[ChatExtension] Parsing schema: ${schemaName}`);
		const schema = this.graph.schemas[schemaName];
		if (!schema?.code) {
			console.log(`[ChatExtension] No schema code found for ${schemaName}`);
			return;
		}

		const chats = this._parseChatDecorators(schema.code);
		this.schemaChats[schemaName] = chats;

		if (Object.keys(chats).length > 0) {
			console.log(`[ChatExtension] Found ${Object.keys(chats).length} chat node(s) in ${schemaName}`);

			// Apply chat to existing nodes that match this schema
			for (const node of this.graph.nodes) {
				if (node.schemaName === schemaName && !node.isChat) {
					const chatConfig = chats[node.modelName];
					if (chatConfig) {
						this._applyChatToNode(node);
					}
				}
			}
		}
	}

	_parseChatDecorators(code) {
		const chats = {};
		const lines = code.split('\n');
		let pendingChat = null;
		let accumulatingDecorator = null;
		let insideAnyDecorator = false;
		let bracketDepth = 0;

		for (let i = 0; i < lines.length; i++) {
			const line = lines[i];
			const trimmed = line.trim();

			if (accumulatingDecorator !== null) {
				accumulatingDecorator += ' ' + trimmed;

				for (const char of trimmed) {
					if (char === '(') bracketDepth++;
					else if (char === ')') bracketDepth--;
				}

				if (bracketDepth === 0) {
					const match = accumulatingDecorator.match(/^@node_chat\s*\((.+)\)\s*$/);
					if (match) {
						pendingChat = this._parseDecoratorArgs(match[1]);
					}
					accumulatingDecorator = null;
				}
				continue;
			}

			if (insideAnyDecorator) {
				for (const char of trimmed) {
					if (char === '(') bracketDepth++;
					else if (char === ')') bracketDepth--;
				}

				if (bracketDepth === 0) {
					insideAnyDecorator = false;
				}
				continue;
			}

			if (trimmed.startsWith('@node_chat')) {
				bracketDepth = 0;
				for (const char of trimmed) {
					if (char === '(') bracketDepth++;
					else if (char === ')') bracketDepth--;
				}

				if (bracketDepth === 0) {
					const match = trimmed.match(/^@node_chat\s*\((.+)\)\s*$/);
					if (match) {
						pendingChat = this._parseDecoratorArgs(match[1]);
					}
				} else {
					accumulatingDecorator = trimmed;
				}
				continue;
			}

			if (trimmed.startsWith('@')) {
				bracketDepth = 0;
				for (const char of trimmed) {
					if (char === '(') bracketDepth++;
					else if (char === ')') bracketDepth--;
				}

				if (bracketDepth > 0) {
					insideAnyDecorator = true;
				}
				continue;
			}

			const classMatch = trimmed.match(/^class\s+(\w+)\s*\(/);
			if (classMatch && pendingChat) {
				chats[classMatch[1]] = pendingChat;
				pendingChat = null;
				continue;
			}

			if (trimmed && !trimmed.startsWith('#')) {
				pendingChat = null;
			}
		}

		return chats;
	}

	_parseDecoratorArgs(argsStr) {
		const config = {};
		const regex = /(\w+)\s*=\s*(?:"([^"]*)"|'([^']*)'|([^,\)]+))/g;
		let match;

		while ((match = regex.exec(argsStr)) !== null) {
			const key = match[1];
			const value = match[2] ?? match[3] ?? match[4]?.trim();

			if (value === 'True' || value === 'true') config[key] = true;
			else if (value === 'False' || value === 'false') config[key] = false;
			else if (value === 'None' || value === 'null') config[key] = null;
			else if (/^-?\d+$/.test(value)) config[key] = parseInt(value);
			else if (/^-?\d+\.\d+$/.test(value)) config[key] = parseFloat(value);
			else config[key] = value;
		}

		return config;
	}

	// ================================================================
	// Apply Chat to Node
	// ================================================================

	_applyChatToNode(node) {
		if (!node) return;

		const schemaName = node.schemaName;
		const modelName = node.modelName;

		if (!schemaName || !modelName) {
			return;
		}

		const chatConfig = this.schemaChats[schemaName]?.[modelName];
		if (!chatConfig) {
			return;
		}

		Object.assign(node, ChatNodeMixin);
		node.initChat(chatConfig);

		const numInputs = node.inputs?.length || 0;
		const numOutputs = node.outputs?.length || 0;
		const maxSlots = Math.max(numInputs, numOutputs);
		const slotsHeight = 33 + (maxSlots * 25) + 10;
		const chatMinHeight = 150;
		const footerHeight = 15;

		const minW = chatConfig.minWidth || 300;
		const minH = Math.max(chatConfig.minHeight || 400, slotsHeight + chatMinHeight + footerHeight);

		node.size = [Math.max(node.size[0], minW), Math.max(node.size[1], minH)];
		node.minSize = [minW, minH];

		this.overlayManager.createOverlay(node);

		console.log(`[ChatExtension] Applied chat to node ${node.id} (${modelName})`);
	}
}

// ========================================================================
// AUTO-INITIALIZATION
// ========================================================================

if (typeof SchemaGraphApp !== 'undefined') {
	if (typeof extensionRegistry !== 'undefined') {
		extensionRegistry.register('chat', ChatExtension);
	} else {
		const originalSetup = SchemaGraphApp.prototype.setupEventListeners;
		SchemaGraphApp.prototype.setupEventListeners = function () {
			originalSetup.call(this);
			this.chatManager = new ChatExtension(this);
		};
	}

	console.log('[SchemaGraph] Chat extension loaded');
}

// ========================================================================
// EXPORTS
// ========================================================================

if (typeof module !== 'undefined' && module.exports) {
	module.exports = {
		ChatState, MessageRole, ChatNodeMixin,
		ChatOverlayManager, ChatExtension
	};
}

if (typeof window !== 'undefined') {
	window.ChatState = ChatState;
	window.MessageRole = MessageRole;
	window.ChatExtension = ChatExtension;
}
