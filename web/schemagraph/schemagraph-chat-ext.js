// ========================================================================
// SCHEMAGRAPH CHAT EXTENSION
// Adds @node_chat decorator support for interactive chat nodes
// ========================================================================

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
		this.isChat = true;
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
			headerOffset: 30,  // Space for node header
			footerOffset: 20,  // Space for node footer
			slotWidth: 16,     // Space for input/output slots
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
		this._sendCallbacks = new Map();
	}

	createOverlay(node) {
		if (this.overlays.has(node.id)) {
			return this.overlays.get(node.id);
		}

		const overlay = document.createElement('div');
		overlay.className = 'sg-chat-overlay';
		overlay.id = `sg-chat-${node.id}`;
		overlay.innerHTML = this._buildChatHTML(node);
		
		document.body.appendChild(overlay);
		this.overlays.set(node.id, overlay);
		
		this._bindOverlayEvents(node, overlay);
		this._updateOverlayPosition(node, overlay);
		
		return overlay;
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
						<button class="sg-chat-btn sg-chat-clear-btn" title="Clear chat">🗑</button>
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
						<span class="sg-chat-send-icon">➤</span>
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

	_bindOverlayEvents(node, overlay) {
		const input = overlay.querySelector('.sg-chat-input');
		const sendBtn = overlay.querySelector('.sg-chat-send-btn');
		const clearBtn = overlay.querySelector('.sg-chat-clear-btn');

		// Send on button click
		sendBtn?.addEventListener('click', () => this._handleSend(node, input));

		// Send on Enter (Shift+Enter for newline)
		input?.addEventListener('keydown', (e) => {
			if (e.key === 'Enter' && !e.shiftKey) {
				e.preventDefault();
				this._handleSend(node, input);
			}
		});

		// Auto-resize textarea
		input?.addEventListener('input', () => {
			input.style.height = 'auto';
			input.style.height = Math.min(input.scrollHeight, 100) + 'px';
			node._chatInputValue = input.value;
		});

		// Clear messages
		clearBtn?.addEventListener('click', () => {
			node.clearMessages();
			this.updateMessages(node);
			this.eventBus.emit('chat:cleared', { nodeId: node.id });
		});

		// Prevent canvas drag when interacting with chat content
		// But allow events on edges for node interaction
		overlay.addEventListener('mousedown', (e) => {
			// Only stop propagation if clicking inside the chat area
			const rect = overlay.getBoundingClientRect();
			const x = e.clientX - rect.left;
			const y = e.clientY - rect.top;
			
			// Allow clicks near edges to pass through for node dragging/resizing
			const edgeThreshold = 8;
			if (x > edgeThreshold && x < rect.width - edgeThreshold &&
			    y > edgeThreshold && y < rect.height - edgeThreshold) {
				e.stopPropagation();
			}
		});
		
		overlay.addEventListener('wheel', (e) => e.stopPropagation(), { passive: true });
	}

	_handleSend(node, input) {
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
			message: text,
			config: node.getAgentConfig(),
			systemPrompt: node.getSystemPrompt(),
			history: node.chatMessages.slice(0, -1),
			node
		});

		const callback = this._sendCallbacks.get(node.id);
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

	updateOverlayPosition(node) {
		const overlay = this.overlays.get(node.id);
		if (overlay) {
			this._updateOverlayPosition(node, overlay);
		}
	}

	_updateOverlayPosition(node, overlay) {
		const canvas = this.app.canvas;
		const rect = canvas.getBoundingClientRect();
		const camera = this.app.camera;
		const config = node.chatConfig || {};
		
		// Calculate node position in screen coordinates
		const scaleX = rect.width / canvas.width;
		const scaleY = rect.height / canvas.height;
		
		const nodeScreenX = (node.pos[0] * camera.scale + camera.x) * scaleX + rect.left;
		const nodeScreenY = (node.pos[1] * camera.scale + camera.y) * scaleY + rect.top;
		const nodeScreenW = node.size[0] * camera.scale * scaleX;
		const nodeScreenH = node.size[1] * camera.scale * scaleY;
		
		// Calculate slot space needed
		const numInputs = node.inputs?.length || 0;
		const numOutputs = node.outputs?.length || 0;
		const maxSlots = Math.max(numInputs, numOutputs);
		
		// Node layout constants (in world units, will be scaled)
		const headerHeight = 30;
		const slotStartY = 33;
		const slotSpacing = 25;
		const slotRadius = 8;
		const footerHeight = 15;
		const horizontalPadding = 12; // Space from edges for slots
		
		// Calculate content area bounds
		const slotsEndY = slotStartY + (maxSlots * slotSpacing);
		const contentStartY = Math.max(headerHeight, slotsEndY + 5);
		
		// Apply scaling
		const scale = camera.scale;
		const overlayX = nodeScreenX + (horizontalPadding * scale * scaleX);
		const overlayY = nodeScreenY + (contentStartY * scale * scaleY);
		const overlayW = nodeScreenW - (horizontalPadding * 2 * scale * scaleX);
		const overlayH = nodeScreenH - (contentStartY * scale * scaleY) - (footerHeight * scale * scaleY);
		
		overlay.style.left = `${overlayX}px`;
		overlay.style.top = `${overlayY}px`;
		overlay.style.width = `${Math.max(overlayW, 80)}px`;
		overlay.style.height = `${Math.max(overlayH, 60)}px`;
		
		// Hide if too small or off-screen
		const minVisibleSize = 50;
		const visible = camera.scale > 0.25 && 
			overlayW > minVisibleSize &&
			overlayH > minVisibleSize &&
			nodeScreenX + nodeScreenW > rect.left && 
			nodeScreenX < rect.right &&
			nodeScreenY + nodeScreenH > rect.top && 
			nodeScreenY < rect.bottom;
		
		overlay.style.display = visible ? 'block' : 'none';
		overlay.style.opacity = Math.min(1, (camera.scale - 0.25) * 3);
	}

	updateMessages(node) {
		const overlay = this.overlays.get(node.id);
		if (!overlay) return;
		
		const container = overlay.querySelector('.sg-chat-messages');
		if (!container) return;
		
		container.innerHTML = node.chatMessages.map(msg => this._renderMessage(msg, node)).join('');
		container.scrollTop = container.scrollHeight;
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

	updateStatus(node) {
		const overlay = this.overlays.get(node.id);
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

	removeOverlay(nodeId) {
		const overlay = this.overlays.get(nodeId);
		if (overlay) {
			overlay.remove();
			this.overlays.delete(nodeId);
		}
		this._sendCallbacks.delete(nodeId);
	}

	removeAllOverlays() {
		for (const [nodeId, overlay] of this.overlays) {
			overlay.remove();
		}
		this.overlays.clear();
		this._sendCallbacks.clear();
	}

	updateAllPositions() {
		for (const [nodeId, overlay] of this.overlays) {
			const node = this.app.graph.getNodeById(nodeId);
			if (node) {
				this._updateOverlayPosition(node, overlay);
			}
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
		// No new node types
	}

	_setupEventListeners() {
		// Parse chat decorators on schema registration
		this.on('schema:registered', (e) => {
			this._parseSchemaChats(e.schemaName);
		});
		
		// Apply chat mixin on node creation
		this.on('node:created', (e) => {
			this._applyChatToNode(e.node);
		});
		
		// Remove overlay on node removal
		this.on('node:removed', (e) => {
			this.overlayManager.removeOverlay(e.nodeId);
		});
		
		// Listen for graph:cleared event
		this.on('graph:cleared', () => {
			this.overlayManager.removeAllOverlays();
		});
		
		// Wrap api.graph.clear() - this is what's actually called
		if (this.app.api?.graph?.clear) {
			const originalApiClear = this.app.api.graph.clear.bind(this.app.api.graph);
			const self = this;
			this.app.api.graph.clear = function(...args) {
				self.overlayManager.removeAllOverlays();
				return originalApiClear(...args);
			};
		}
		
		// Also wrap workflow import since it replaces nodes
		this.on('workflow:imported', () => {
			this._cleanupOrphanedOverlays();
		});
		
		// Update positions on camera/node changes
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
		
		// Update positions on every draw
		const originalDraw = this.app.draw?.bind(this.app);
		if (originalDraw) {
			const self = this;
			this.app.draw = function() {
				originalDraw();
				self.overlayManager.updateAllPositions();
			};
		}
	}

	_cleanupOrphanedOverlays() {
		const toRemove = [];
		for (const nodeId of this.overlayManager.overlays.keys()) {
			if (!this.graph.getNodeById(nodeId)) {
				toRemove.push(nodeId);
			}
		}
		for (const nodeId of toRemove) {
			this.overlayManager.removeOverlay(nodeId);
		}
	}

	_extendAPI() {
		const self = this;
		
		this.app.api = this.app.api || {};
		this.app.api.chat = {
			onSend: (nodeOrId, callback) => {
				const nodeId = typeof nodeOrId === 'object' ? nodeOrId.id : nodeOrId;
				self.overlayManager.registerSendCallback(nodeId, callback);
			},
			offSend: (nodeOrId) => {
				const nodeId = typeof nodeOrId === 'object' ? nodeOrId.id : nodeOrId;
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
				position: fixed;
				z-index: 100;
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
				background: rgba(20, 24, 28, 0.95);
				border: 1px solid rgba(255, 255, 255, 0.1);
				border-radius: 4px;
				overflow: hidden;
			}
			
			.sg-chat-status {
				display: flex;
				align-items: center;
				gap: 6px;
				padding: 4px 8px;
				background: rgba(0, 0, 0, 0.3);
				font-size: 10px;
				color: #888;
				border-bottom: 1px solid rgba(255, 255, 255, 0.05);
			}
			
			.sg-chat-status-indicator {
				width: 6px;
				height: 6px;
				border-radius: 50%;
				background: #666;
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
			
			.sg-chat-state-idle .sg-chat-status-indicator { background: #666; }
			.sg-chat-state-connecting .sg-chat-status-indicator { background: #f0ad4e; animation: sg-chat-pulse 1s infinite; }
			.sg-chat-state-ready .sg-chat-status-indicator { background: #5cb85c; }
			.sg-chat-state-sending .sg-chat-status-indicator { background: #5bc0de; animation: sg-chat-pulse 0.5s infinite; }
			.sg-chat-state-streaming .sg-chat-status-indicator { background: #5bc0de; animation: sg-chat-pulse 0.3s infinite; }
			.sg-chat-state-error .sg-chat-status-indicator { background: #d9534f; }
			
			@keyframes sg-chat-pulse {
				0%, 100% { opacity: 1; }
				50% { opacity: 0.4; }
			}
			
			.sg-chat-btn {
				background: transparent;
				border: none;
				color: #888;
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
				background: rgba(255, 255, 255, 0.1);
				color: #fff;
			}
			
			.sg-chat-messages {
				flex: 1;
				overflow-y: auto;
				padding: 8px;
				display: flex;
				flex-direction: column;
				gap: 8px;
				min-height: 0;
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
				background: #2d5a7b;
				color: #fff;
				border-bottom-right-radius: 2px;
			}
			
			.sg-chat-msg-assistant {
				align-self: flex-start;
				background: #2d3136;
				color: #e0e0e0;
				border-bottom-left-radius: 2px;
			}
			
			.sg-chat-msg-system {
				align-self: center;
				background: rgba(255, 255, 255, 0.05);
				color: #888;
				font-style: italic;
				font-size: 11px;
			}
			
			.sg-chat-msg-error {
				align-self: center;
				background: rgba(217, 83, 79, 0.2);
				color: #f88;
				border: 1px solid rgba(217, 83, 79, 0.3);
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
				background: rgba(0, 0, 0, 0.4);
				padding: 6px;
				border-radius: 3px;
				overflow-x: auto;
				margin: 6px 0;
				font-size: 11px;
				font-family: 'Monaco', 'Menlo', monospace;
			}
			
			.sg-chat-msg-content code.sg-chat-inline-code {
				background: rgba(0, 0, 0, 0.3);
				padding: 1px 4px;
				border-radius: 2px;
				font-size: 11px;
				font-family: 'Monaco', 'Menlo', monospace;
			}
			
			.sg-chat-input-container {
				display: flex;
				gap: 6px;
				padding: 8px;
				background: rgba(0, 0, 0, 0.2);
				border-top: 1px solid rgba(255, 255, 255, 0.05);
			}
			
			.sg-chat-input {
				flex: 1;
				background: rgba(0, 0, 0, 0.3);
				border: 1px solid rgba(255, 255, 255, 0.1);
				border-radius: 6px;
				padding: 6px 10px;
				color: #fff;
				font-size: 12px;
				resize: none;
				min-height: 18px;
				max-height: 100px;
				font-family: inherit;
				line-height: 1.4;
			}
			
			.sg-chat-input:focus {
				outline: none;
				border-color: rgba(45, 90, 123, 0.8);
			}
			
			.sg-chat-input::placeholder {
				color: #555;
			}
			
			.sg-chat-send-btn {
				background: #2d5a7b;
				border: none;
				color: #fff;
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
				background: #3d7a9b;
			}
			
			.sg-chat-send-btn:disabled {
				background: #3a3f44;
				cursor: not-allowed;
				opacity: 0.5;
			}
			
			/* Scrollbar */
			.sg-chat-messages::-webkit-scrollbar {
				width: 4px;
			}
			
			.sg-chat-messages::-webkit-scrollbar-track {
				background: transparent;
			}
			
			.sg-chat-messages::-webkit-scrollbar-thumb {
				background: rgba(255, 255, 255, 0.1);
				border-radius: 2px;
			}
			
			.sg-chat-messages::-webkit-scrollbar-thumb:hover {
				background: rgba(255, 255, 255, 0.2);
			}
		`;
		
		document.head.appendChild(style);
	}

	// ================================================================
	// Schema Parsing
	// ================================================================

	_parseSchemaChats(schemaName) {
		const schema = this.graph.schemas[schemaName];
		if (!schema?.code) return;
		
		const chats = this._parseChatDecorators(schema.code);
		this.schemaChats[schemaName] = chats;
		
		if (Object.keys(chats).length > 0) {
			console.log(`[ChatExtension] Parsed chat decorators for ${schemaName}:`, chats);
		}
	}

	_parseChatDecorators(code) {
		const chats = {};
		const lines = code.split('\n');
		let pendingChat = null;
		let accumulatingDecorator = null;
		let bracketDepth = 0;
		
		for (let i = 0; i < lines.length; i++) {
			const line = lines[i];
			const trimmed = line.trim();
			
			// If accumulating multi-line decorator
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
			
			// Check for @node_chat decorator start
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
			
			// Check for class definition
			const classMatch = trimmed.match(/^class\s+(\w+)\s*\(/);
			if (classMatch && pendingChat) {
				chats[classMatch[1]] = pendingChat;
				pendingChat = null;
				continue;
			}
			
			// Non-decorator line clears pending
			if (trimmed && !trimmed.startsWith('#') && !trimmed.startsWith('@')) {
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
		
		if (!schemaName || !modelName) return;
		
		const chatConfig = this.schemaChats[schemaName]?.[modelName];
		if (!chatConfig) return;
		
		// Apply mixin
		Object.assign(node, ChatNodeMixin);
		node.initChat(chatConfig);
		
		// Calculate minimum height based on slots + chat area
		const numInputs = node.inputs?.length || 0;
		const numOutputs = node.outputs?.length || 0;
		const maxSlots = Math.max(numInputs, numOutputs);
		const slotsHeight = 33 + (maxSlots * 25) + 10; // slot area
		const chatMinHeight = 150; // minimum chat area
		const footerHeight = 15;
		
		const minW = chatConfig.minWidth || 300;
		const minH = Math.max(chatConfig.minHeight || 400, slotsHeight + chatMinHeight + footerHeight);
		
		node.size = [Math.max(node.size[0], minW), Math.max(node.size[1], minH)];
		node.minSize = [minW, minH];
		
		// Create overlay
		setTimeout(() => {
			this.overlayManager.createOverlay(node);
		}, 0);
		
		console.log(`[ChatExtension] Applied chat to node ${node.id} (${modelName})`);
	}
}

// ========================================================================
// AUTO-INITIALIZATION
// Note: Chat nodes now render normally like other nodes.
// The overlay is positioned inside the node's content area.
// ========================================================================

if (typeof SchemaGraphApp !== 'undefined') {
	if (typeof extensionRegistry !== 'undefined') {
		extensionRegistry.register('chat', ChatExtension);
	} else {
		const originalSetup = SchemaGraphApp.prototype.setupEventListeners;
		SchemaGraphApp.prototype.setupEventListeners = function() {
			originalSetup.call(this);
			this.chatManager = new ChatExtension(this);
		};
	}
	
	console.log('✨ SchemaGraph Chat extension loaded');
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
