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
// Helpers
// ========================================================================

const _CHAT_PREVIEW_EXT_MAP = {
	png: 'image', jpg: 'image', jpeg: 'image', gif: 'image', bmp: 'image', webp: 'image', svg: 'image',
	mp3: 'audio', wav: 'audio', ogg: 'audio', flac: 'audio', aac: 'audio', m4a: 'audio',
	mp4: 'video', webm: 'video', mov: 'video', avi: 'video', mkv: 'video',
	glb: 'model3d', gltf: 'model3d', obj: 'model3d', fbx: 'model3d', stl: 'model3d', ply: 'model3d',
	txt: 'text', md: 'text', log: 'text', csv: 'text', json: 'text', xml: 'text',
	py: 'text', js: 'text', html: 'text', css: 'text', yaml: 'text', yml: 'text',
};

function _chatPreviewTypeFromExt(ext) {
	return _CHAT_PREVIEW_EXT_MAP[ext] || 'file';
}

/** Map MIME type → file extension for preview format detection. */
function _mimeToExt(mime) {
	const m = {
		'image/png': 'png', 'image/jpeg': 'jpg', 'image/webp': 'webp',
		'image/gif': 'gif', 'image/bmp': 'bmp', 'image/svg+xml': 'svg',
		'audio/wav': 'wav', 'audio/x-wav': 'wav', 'audio/mpeg': 'mp3',
		'audio/ogg': 'ogg', 'audio/flac': 'flac', 'audio/aac': 'aac', 'audio/mp4': 'm4a',
		'video/mp4': 'mp4', 'video/webm': 'webm', 'video/quicktime': 'mov',
		'model/gltf-binary': 'glb', 'model/gltf+json': 'gltf',
		'model/obj': 'obj', 'model/stl': 'stl', 'model/ply': 'ply', 'model/fbx': 'fbx',
		'application/json': 'json', 'text/plain': 'txt',
	};
	return m[mime] || null;
}

// Temporary cache for large preview data (data URLs) to avoid embedding in chat messages
const _previewDataCache = new Map();
function _storePreviewData(data) {
	const id = `pdc_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`;
	_previewDataCache.set(id, data);
	return id;
}
function _getPreviewData(id) {
	return _previewDataCache.get(id);
}
// Store FileSystemFileHandles keyed by cache ID for disk re-read on refresh
const _previewHandleCache = new Map();
function _storePreviewHandle(cacheId, handle) {
	if (handle) _previewHandleCache.set(cacheId, handle);
}
function _getPreviewHandle(cacheId) {
	return _previewHandleCache.get(cacheId);
}

/**
 * Fetch a URL via POST and return a blob URL suitable for element src.
 * For data: URLs, returns the URL as-is (no server call needed).
 * Uses window._numelAPI.fetchBlobUrl if available, otherwise raw fetch.
 */
async function _fetchBlobUrl(url) {
	if (url.startsWith('data:')) return url;
	if (window._numelAPI?.fetchBlobUrl) return window._numelAPI.fetchBlobUrl(url);
	const resp = await fetch(url, { method: 'POST' });
	if (!resp.ok) throw new Error(`Fetch failed: ${resp.status}`);
	const blob = await resp.blob();
	return URL.createObjectURL(blob);
}

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
			inputField: config.input_field || config.inputField || null,
			outputField: config.output_field || config.outputField || null,
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
			this.updateStatus(node);
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

		// Auto-scroll when async content (images, video) finishes loading inside messages
		const msgContainer = overlay.querySelector('.sg-chat-messages');
		if (msgContainer) {
			msgContainer.addEventListener('load', () => {
				const threshold = 80;
				if ((msgContainer.scrollHeight - msgContainer.scrollTop - msgContainer.clientHeight) < threshold) {
					msgContainer.scrollTop = msgContainer.scrollHeight;
				}
			}, true); // capture phase to catch img/video/audio load events
		}

		this._bindOverlayEvents(node, overlay);
		this._updateOverlayPosition(node, overlay);
		this.updateStatus(node);

		return overlay;
	}

	_rebindOverlayEvents(node, overlay) {
		const input = overlay.querySelector('.sg-chat-input');
		const sendBtn = overlay.querySelector('.sg-chat-send-btn');
		const clearBtn = overlay.querySelector('.sg-chat-clear-btn');
		const toggleSysBtn = overlay.querySelector('.sg-chat-toggle-sys-btn');

		const newSendBtn = sendBtn?.cloneNode(true);
		const newClearBtn = clearBtn?.cloneNode(true);
		const newInput = input?.cloneNode(true);
		const newToggleSysBtn = toggleSysBtn?.cloneNode(true);

		sendBtn?.parentNode?.replaceChild(newSendBtn, sendBtn);
		clearBtn?.parentNode?.replaceChild(newClearBtn, clearBtn);
		input?.parentNode?.replaceChild(newInput, input);
		toggleSysBtn?.parentNode?.replaceChild(newToggleSysBtn, toggleSysBtn);

		// Abort previous overlay-level listeners before re-adding
		if (overlay._chatAbort) overlay._chatAbort.abort();

		this._bindOverlayEvents(node, overlay);
	}

	_bindOverlayEvents(node, overlay) {
		const chatId = node.chatId;
		const input = overlay.querySelector('.sg-chat-input');
		const sendBtn = overlay.querySelector('.sg-chat-send-btn');
		const clearBtn = overlay.querySelector('.sg-chat-clear-btn');

		const getNode = () => this.nodeRefs.get(chatId);

		// AbortController for overlay-level listeners (so rebind can remove them)
		const ac = new AbortController();
		overlay._chatAbort = ac;
		const sig = { signal: ac.signal };

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

		const toggleSysBtn = overlay.querySelector('.sg-chat-toggle-sys-btn');
		toggleSysBtn?.addEventListener('click', () => {
			const msgContainer = overlay.querySelector('.sg-chat-messages');
			if (msgContainer) {
				msgContainer.classList.toggle('sg-chat-hide-system');
				toggleSysBtn.classList.toggle('sg-chat-btn-active');
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
		}, sig);

		overlay.addEventListener('wheel', (e) => e.stopPropagation(), { passive: true, signal: ac.signal });

		// Workflow import/merge button delegation (for /gen results)
		overlay.addEventListener('click', (e) => {
			const importBtn = e.target.closest('.sg-chat-workflow-import-btn');
			if (importBtn) {
				e.stopPropagation();
				const msgId = importBtn.dataset.msgId;
				const currentNode = getNode();
				if (currentNode) this._handleWorkflowImport(currentNode, msgId);
				return;
			}
			const mergeBtn = e.target.closest('.sg-chat-workflow-merge-btn');
			if (mergeBtn) {
				e.stopPropagation();
				const msgId = mergeBtn.dataset.msgId;
				const currentNode = getNode();
				if (currentNode) this._handleWorkflowMerge(currentNode, msgId);
				return;
			}
			const copyBtn = e.target.closest('.sg-chat-workflow-copy-btn');
			if (copyBtn) {
				e.stopPropagation();
				const currentNode = getNode();
				if (currentNode) this._handleWorkflowCopy(currentNode, copyBtn.dataset.msgId, copyBtn);
				return;
			}
			const openBtn = e.target.closest('.sg-chat-workflow-open-btn');
			if (openBtn) {
				e.stopPropagation();
				const currentNode = getNode();
				if (currentNode) this._handleWorkflowOpenTab(currentNode, openBtn.dataset.msgId);
				return;
			}
			const retryBtn = e.target.closest('.sg-chat-workflow-retry-btn');
			if (retryBtn) {
				e.stopPropagation();
				const currentNode = getNode();
				if (currentNode) {
					// Find the last /gen user message and re-send it
					const msgs = currentNode.chatMessages || [];
					const lastGen = [...msgs].reverse().find(m => m.role === 'user' && /^\/gen\s/.test(m.content));
					if (lastGen) {
						const sendCb = this._sendCallbacks.get(currentNode.chatId);
						if (sendCb) sendCb(currentNode, lastGen.content, {});
					}
				}
				return;
			}
			const handle = e.target.closest('.sg-chat-preview-drag-handle');
			if (handle) {
				e.stopPropagation();
				let url = handle.dataset.fileUrl;
				if (!url && handle.dataset.cacheId) {
					url = _getPreviewData(handle.dataset.cacheId) || '';
				}
				this._handleOpenOnGraph(url, handle.dataset.fileName);
				return;
			}
			const refreshBtn = e.target.closest('.sg-chat-preview-refresh-btn');
			if (refreshBtn) {
				e.stopPropagation();
				this._refreshChatPreview(refreshBtn);
			}
		}, sig);

		// Drag from chat to graph canvas
		overlay.addEventListener('dragstart', (e) => {
			// Preview drag handle
			const handle = e.target.closest('.sg-chat-preview-drag-handle');
			if (handle) {
				const fileUrl = handle.dataset.fileUrl;
				const cacheId = handle.dataset.cacheId;
				const fileName = handle.dataset.fileName;
				// For cached data URLs, store in app temp slot (DataTransfer has size limits)
				if (cacheId) {
					const dataUrl = _getPreviewData(cacheId);
					if (dataUrl) {
						this.app._pendingChatPreviewDrag = { fileUrl: dataUrl, fileName };
						e.dataTransfer.setData('text/x-sg-chat-preview', JSON.stringify({
							fileName, _usePending: true,
						}));
						e.dataTransfer.effectAllowed = 'copy';
						return;
					}
				}
				e.dataTransfer.setData('text/x-sg-chat-preview', JSON.stringify({
					fileUrl, fileName,
				}));
				e.dataTransfer.effectAllowed = 'copy';
				return;
			}
			// Message drag (text, numbers, etc.)
			const msgEl = e.target.closest('.sg-chat-msg');
			if (msgEl) {
				const text = msgEl.dataset.msgText || '';
				if (!text) { e.preventDefault(); return; }
				e.dataTransfer.setData('text/x-sg-chat-message', text);
				e.dataTransfer.setData('text/plain', text);
				e.dataTransfer.effectAllowed = 'copy';
			}
		}, sig);

		// Drop from graph onto chat (import preview into chat)
		overlay.addEventListener('dragover', (e) => {
			if (e.dataTransfer.types.includes('text/x-sg-graph-preview') || e.dataTransfer.types.includes('Files')) {
				e.preventDefault();
				e.dataTransfer.dropEffect = 'copy';
				this._showDropHighlight(overlay);
			}
		}, sig);
		overlay.addEventListener('dragleave', (e) => {
			const rect = overlay.getBoundingClientRect();
			if (e.clientX < rect.left || e.clientX > rect.right || e.clientY < rect.top || e.clientY > rect.bottom) {
				this._hideDropHighlight(overlay);
			}
		}, sig);
		overlay.addEventListener('drop', (e) => {
			this._hideDropHighlight(overlay);
			const currentNode = getNode();
			if (!currentNode) return;

			// Drop from graph preview node
			const graphData = e.dataTransfer.getData('text/x-sg-graph-preview');
			if (graphData) {
				e.preventDefault();
				try {
					let info = JSON.parse(graphData);
					// Resolve pending large data from app temp slot
					if (info._usePending && this.app._pendingPreviewDrag) {
						info = this.app._pendingPreviewDrag;
						this.app._pendingPreviewDrag = null;
					}
					this._handleGraphToChat(currentNode, info);
				} catch (err) {
					console.error('[ChatOverlay] Graph drop parse error:', err);
				}
				return;
			}

			// Drop external files
			if (e.dataTransfer.files?.length) {
				e.preventDefault();
				const files = Array.from(e.dataTransfer.files);
				// Capture FileSystemFileHandles for disk re-read on refresh (Chromium only)
				const items = Array.from(e.dataTransfer.items || []);
				Promise.all(items.map(item =>
					item.getAsFileSystemHandle ? item.getAsFileSystemHandle().catch(() => null) : Promise.resolve(null)
				)).then(handles => {
					for (let i = 0; i < files.length && i < handles.length; i++) {
						if (handles[i]?.kind === 'file') files[i]._fileHandle = handles[i];
					}
					this._handleFileDropOnChat(currentNode, files);
				}).catch(() => {
					this._handleFileDropOnChat(currentNode, files);
				});
			}
		}, sig);
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

	updateMessages(node, lastOnly = false) {
		const overlay = this.overlays.get(node.chatId);
		if (!overlay) return;

		const container = overlay.querySelector('.sg-chat-messages');
		if (!container) return;

		const scrollThreshold = 40;
		const wasAtBottom = (container.scrollHeight - container.scrollTop - container.clientHeight) < scrollThreshold;

		const messages = node.chatMessages || [];
		const domCount = container.children.length;

		if (lastOnly && messages.length > 0 && domCount === messages.length) {
			// Incremental: only update the last message element's content
			const lastEl = container.lastElementChild;
			const lastMsg = messages[messages.length - 1];
			if (lastEl && lastMsg) {
				const contentEl = lastEl.querySelector('.sg-chat-msg-content');
				if (contentEl) {
					contentEl.innerHTML = this._renderContent(lastMsg.content);
				}
				// Add workflow actions if the message now has a workflow (e.g. after /gen post-processing)
				if (lastMsg.workflow && !lastEl.querySelector('.sg-chat-workflow-actions')) {
					const jsonPreview = JSON.stringify(lastMsg.workflow, null, 2)
						.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
					const actionsHtml = `
						<div class="sg-chat-workflow-actions">
							<button class="sg-chat-workflow-import-btn" data-msg-id="${lastMsg.id}">Import to Canvas</button>
							<button class="sg-chat-workflow-merge-btn" data-msg-id="${lastMsg.id}">Merge into Canvas</button>
							<button class="sg-chat-workflow-copy-btn" data-msg-id="${lastMsg.id}">Copy JSON</button>
							<button class="sg-chat-workflow-open-btn" data-msg-id="${lastMsg.id}">Open in new Tab</button>
							<button class="sg-chat-workflow-retry-btn" data-msg-id="${lastMsg.id}">Retry</button>
							<details class="sg-chat-workflow-preview">
								<summary>Preview JSON</summary>
								<pre class="sg-chat-workflow-json">${jsonPreview}</pre>
							</details>
						</div>
					`;
					lastEl.insertAdjacentHTML('beforeend', actionsHtml);
				}
				// Keep drag data in sync with streamed content
				const rawText = (lastMsg.content || '').replace(/<<preview:\w+:.+?>>/g, '').replace(/<<file_content:.+?>>\n?/g, '').trim();
				lastEl.dataset.msgText = rawText;
			}
		} else if (messages.length > domCount && domCount > 0) {
			// Append only new messages (preserves existing DOM including previews)
			const newMessages = messages.slice(domCount);
			const frag = document.createRange().createContextualFragment(
				newMessages.map(msg => this._renderMessage(msg, node)).join('')
			);
			container.appendChild(frag);
		} else {
			// Full rebuild (first render, clear, or message count decreased)
			container.innerHTML = messages.map(msg => this._renderMessage(msg, node)).join('');
		}

		if (wasAtBottom) {
			container.scrollTop = container.scrollHeight;
			// Previews (images, fetched text, 3D) load asynchronously and add height
			// after the initial DOM update. Re-scroll after they settle.
			requestAnimationFrame(() => { container.scrollTop = container.scrollHeight; });
			setTimeout(() => { container.scrollTop = container.scrollHeight; }, 150);
			setTimeout(() => { container.scrollTop = container.scrollHeight; }, 500);
		}
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
		const isReady = node.chatState === ChatState.READY;
		const isBusy  = node.chatState === ChatState.SENDING || node.chatState === ChatState.STREAMING;
		const canType = isReady || isBusy;  // allow typing while streaming, but not before connected

		if (sendBtn) sendBtn.disabled = !isReady;

		const chatInput = overlay.querySelector('.sg-chat-input');
		if (chatInput) {
			chatInput.disabled = !canType;
			chatInput.placeholder = canType ? 'Type a message...' : this._getStatusText(node);
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
						<button class="sg-chat-btn sg-chat-toggle-sys-btn" title="Show system messages">S</button>
						<button class="sg-chat-btn sg-chat-clear-btn" title="Clear chat">&#128465;</button>
					</div>
				</div>
				<div class="sg-chat-messages sg-chat-hide-system"></div>
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

		if (node.chatState !== ChatState.READY) {
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

		// Workflow actions (for /gen results)
		let actions = '';
		if (msg.workflow) {
			const jsonPreview = JSON.stringify(msg.workflow, null, 2)
				.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
			actions = `
				<div class="sg-chat-workflow-actions">
					<button class="sg-chat-workflow-import-btn" data-msg-id="${msg.id}">Import to Canvas</button>
					<button class="sg-chat-workflow-merge-btn" data-msg-id="${msg.id}">Merge into Canvas</button>
					<button class="sg-chat-workflow-copy-btn" data-msg-id="${msg.id}">Copy JSON</button>
					<button class="sg-chat-workflow-open-btn" data-msg-id="${msg.id}">Open in new Tab</button>
					<button class="sg-chat-workflow-retry-btn" data-msg-id="${msg.id}">Retry</button>
					<details class="sg-chat-workflow-preview">
						<summary>Preview JSON</summary>
						<pre class="sg-chat-workflow-json">${jsonPreview}</pre>
					</details>
				</div>
			`;
		}

		// Escape raw content for data attribute (strip preview markers for plain text drag)
		const rawText = (msg.content || '').replace(/<<preview:\w+:.+?>>/g, '').replace(/<<file_content:.+?>>\n?/g, '').trim();
		const escapedRaw = rawText.replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
		const hasPreview = /<<preview:\w+:.+?>>|<<file_content:.+?>>/.test(msg.content || '');
		const previewClass = hasPreview ? ' sg-chat-msg-has-preview' : '';

		return `
			<div class="sg-chat-msg ${roleClass}${previewClass}" data-msg-id="${msg.id}" draggable="true" data-msg-text="${escapedRaw}">
				<div class="sg-chat-msg-header">
					<span class="sg-chat-msg-role">${this._getRoleName(msg.role)}</span>
					${timestamp}
				</div>
				<div class="sg-chat-msg-content">${content}</div>
				${actions}
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

		// Inline preview markers: <<preview:type:path>>
		html = html.replace(/&lt;&lt;preview:(\w+):(.+?)&gt;&gt;/g, (match, type, filePath) => {
			// Unescape HTML entities that were applied earlier
			const raw = filePath.replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>');
			let fileUrl, displayPath;
			// Cached data URL reference: cached:ID:filename
			const cachedMatch = raw.match(/^cached:([^:]+):(.+)$/);
			if (cachedMatch) {
				const cachedData = _getPreviewData(cachedMatch[1]);
				fileUrl = cachedData || '';
				displayPath = cachedMatch[2]; // filename for display & format detection
			} else if (raw.startsWith('data:')) {
				fileUrl = raw;
				displayPath = raw;
			} else {
				const baseUrl = this.app?.chatManager?._baseUrl || '';
				fileUrl = `${baseUrl}/file/${raw}`;
				displayPath = raw;
			}
			const ts = Date.now();
			return this._renderPreviewEmbed(type, fileUrl, displayPath, ts);
		});

		// Inline file content markers: <<file_content:filename>>\ncontent
		html = html.replace(/&lt;&lt;file_content:(.+?)&gt;&gt;\n([\s\S]*)$/, (match, fileName, fileContent) => {
			const name = fileName.replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>');
			return `<div class="sg-chat-preview">`
				+ `<div class="sg-chat-preview-header"><span class="sg-chat-preview-filename">${name}</span></div>`
				+ `<div class="sg-chat-preview-text-body"><pre class="sg-chat-preview-text-content">${fileContent}</pre></div>`
				+ `</div>`;
		});

		html = html.replace(/\n/g, '<br>');

		return html;
	}

	_renderPreviewEmbed(type, fileUrl, filePath, ts) {
		const isDataUrl = fileUrl.startsWith('data:');
		const fileName = filePath.startsWith('data:') ? `preview.${type}` : filePath.split('/').pop().split('\\').pop();
		const bustUrl = isDataUrl ? fileUrl : `${fileUrl}?t=${ts}`;
		const previewId = `sgpv_${ts}_${Math.random().toString(36).slice(2, 6)}`;

		// For data URLs, don't embed them in HTML attributes — store in cache
		const headerUrl = isDataUrl ? '' : fileUrl;
		const cacheId = isDataUrl ? _storePreviewData(fileUrl) : '';

		// Header with refresh + draggable export handle
		const hdr = `<div class="sg-chat-preview-header">`
			+ `<span class="sg-chat-preview-filename">${fileName}</span>`
			+ `<span class="sg-chat-preview-actions">`
			+ `<span class="sg-chat-preview-refresh-btn" data-file-url="${headerUrl}" data-file-name="${fileName}" data-preview-type="${type}" data-cache-id="${cacheId}" title="Refresh preview">&#8635;</span>`
			+ `<span class="sg-chat-preview-drag-handle" draggable="true" data-file-url="${headerUrl}" data-file-name="${fileName}" data-cache-id="${cacheId}" title="Drag to graph or click to open on graph">&#8663;</span>`
			+ `</span></div>`;

		let body = '';
		switch (type) {
			case 'image':
				body = `<img class="sg-chat-preview-img" id="${previewId}" alt="${fileName}" loading="lazy">`;
				setTimeout(() => {
					const img = document.getElementById(previewId);
					if (!img) return;
					_fetchBlobUrl(bustUrl).then(blobUrl => { img.src = blobUrl; })
						.catch(() => { img.alt = 'Failed to load'; });
				}, 0);
				break;
			case 'audio':
				body = `<audio class="sg-chat-preview-audio" id="${previewId}" controls></audio>`;
				setTimeout(() => {
					const audio = document.getElementById(previewId);
					if (!audio) return;
					_fetchBlobUrl(bustUrl).then(blobUrl => { audio.src = blobUrl; audio.load(); })
						.catch(() => {});
				}, 0);
				break;
			case 'video':
				body = `<video class="sg-chat-preview-video" id="${previewId}" controls></video>`;
				setTimeout(() => {
					const video = document.getElementById(previewId);
					if (!video) return;
					_fetchBlobUrl(bustUrl).then(blobUrl => { video.src = blobUrl; video.load(); })
						.catch(() => {});
				}, 0);
				break;
			case 'model3d': {
				const resetId = `${previewId}_reset`;
				setTimeout(async () => {
					const canvasEl = document.getElementById(previewId);
					if (!canvasEl || !window.ThreeViewer) return;
					// For server URLs, POST-fetch to blob URL so Three.js loaders don't use GET
					let modelUrl;
					if (isDataUrl) {
						modelUrl = fileName ? `${bustUrl}#${encodeURIComponent(fileName)}` : bustUrl;
					} else {
						try {
							const blobUrl = await _fetchBlobUrl(bustUrl);
							modelUrl = fileName ? `${blobUrl}#${encodeURIComponent(fileName)}` : blobUrl;
						} catch { modelUrl = bustUrl; }
					}
					this._init3DPreview(canvasEl, modelUrl);
					const resetBtn = document.getElementById(resetId);
					if (resetBtn) {
						resetBtn.addEventListener('click', (ev) => {
							ev.stopPropagation();
							const ctx = canvasEl._sg3dCtx;
							if (!ctx) return;
							if (ctx.initialCameraPos) {
								ctx.camera.position.copy(ctx.initialCameraPos);
								ctx.controls.target.copy(ctx.initialTarget);
							} else {
								ctx.camera.position.set(2, 1.5, 3);
								ctx.controls.target.set(0, 0, 0);
							}
							ctx.controls.update();
						});
					}
				}, 0);
				body = `<div class="sg-chat-preview-3d-wrapper">`
					+ `<canvas id="${previewId}" class="sg-chat-preview-3d-canvas"></canvas>`
					+ `<button id="${resetId}" class="sg-chat-preview-3d-reset-btn" title="Reset camera">Reset</button>`
					+ `</div>`;
				break;
			}
			case 'text':
				setTimeout(() => {
					const el = document.getElementById(previewId);
					if (!el) return;
					const showText = (text) => {
						const escaped = text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
						el.innerHTML = `<pre class="sg-chat-preview-text-content">${escaped}</pre>`;
					};
					if (isDataUrl) {
						// Decode text from data URL directly (fetch may not support data: in all browsers)
						try {
							const commaIdx = bustUrl.indexOf(',');
							const isBase64 = bustUrl.slice(0, commaIdx).includes(';base64');
							const payload = bustUrl.slice(commaIdx + 1);
							showText(isBase64 ? atob(payload) : decodeURIComponent(payload));
						} catch { el.innerHTML = `<span style="color:#f44">Failed to decode text</span>`; }
					} else {
						fetch(bustUrl, { method: 'POST' }).then(r => r.text()).then(showText)
							.catch(() => { el.innerHTML = `<span style="color:#f44">Failed to load file</span>`; });
					}
				}, 0);
				body = `<div id="${previewId}" class="sg-chat-preview-text-body">Loading...</div>`;
				break;
			default:
				body = `<div class="sg-chat-preview-text-placeholder"><a href="${bustUrl}" target="_blank" download="${fileName}">Download ${fileName}</a></div>`;
				break;
		}

		const cls = type === 'model3d' ? 'sg-chat-preview sg-chat-preview-3d' : 'sg-chat-preview';
		return `<div class="${cls}">${hdr}${body}</div>`;
	}

	_init3DPreview(canvas, modelUrl) {
		const { THREE, OrbitControls, GLTFLoader, PLYLoader, OBJLoader, STLLoader, FBXLoader } = window.ThreeViewer;
		if (!THREE) return;

		// Clean up previous context on this canvas (e.g. on refresh)
		const prev = canvas._sg3dCtx;
		if (prev) {
			if (prev.animId != null) cancelAnimationFrame(prev.animId);
			prev.renderer?.dispose();
			prev.observer?.disconnect();
			canvas._sg3dCtx = null;
		}

		const w = canvas.clientWidth || 280;
		const h = canvas.clientHeight || 200;

		const scene = new THREE.Scene();
		scene.background = new THREE.Color(0x1a1a2e);

		const camera = new THREE.PerspectiveCamera(45, w / h, 0.01, 1000);
		camera.position.set(2, 1.5, 3);

		const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: false });
		renderer.setSize(w, h, false);
		renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
		renderer.toneMapping = THREE.ACESFilmicToneMapping;

		const controls = new OrbitControls(camera, canvas);
		controls.enableDamping = true;
		controls.dampingFactor = 0.1;

		scene.add(new THREE.AmbientLight(0xffffff, 0.6));
		const dir = new THREE.DirectionalLight(0xffffff, 1.0);
		dir.position.set(5, 10, 7);
		scene.add(dir);
		scene.add(new THREE.GridHelper(4, 8, 0x444466, 0x333355));

		// Detect format from URL, fragment hint, or data URL mime type
		let ext = '';
		const extMatch = modelUrl.match(/\.(\w+)(?:\?|#|$)/i);
		if (extMatch) {
			ext = extMatch[1].toLowerCase();
		}
		if (!ext) {
			// Check fragment hint (e.g. data:...#model.ply)
			const hashMatch = modelUrl.match(/#.*\.(\w+)$/i);
			if (hashMatch) ext = hashMatch[1].toLowerCase();
		}
		if (!ext && modelUrl.startsWith('data:')) {
			const mimeMatch = modelUrl.match(/^data:model\/([^;,]+)/);
			if (mimeMatch) ext = mimeMatch[1].replace('gltf-binary', 'glb').replace('gltf+json', 'gltf').toLowerCase();
			if (!ext || ext === 'octet-stream') {
				// Try application/octet-stream with filename hint in fragment
				const hintFallback = modelUrl.match(/#.*\.(\w+)$/i);
				if (hintFallback) ext = hintFallback[1].toLowerCase();
			}
		}
		// Last resort: sniff content from data URL prefix
		if (!ext && modelUrl.startsWith('data:')) {
			ext = this._sniff3DFormat(modelUrl) || '';
		}

		// Store context on canvas element for reset button and cleanup on refresh
		const ctx = { camera, controls, renderer, initialCameraPos: null, initialTarget: null, animId: null, observer: null };
		canvas._sg3dCtx = ctx;

		const _addModel = (model) => {
			const box = new THREE.Box3().setFromObject(model);
			const size = box.getSize(new THREE.Vector3());
			const center = box.getCenter(new THREE.Vector3());
			const maxDim = Math.max(size.x, size.y, size.z);
			const scale = maxDim > 0 ? 2 / maxDim : 1;
			model.scale.setScalar(scale);
			model.position.sub(center.multiplyScalar(scale));
			const newBox = new THREE.Box3().setFromObject(model);
			model.position.y -= newBox.min.y;
			scene.add(model);
			const mc = new THREE.Box3().setFromObject(model).getCenter(new THREE.Vector3());
			controls.target.copy(mc);
			controls.update();
			// Store initial camera state for reset
			ctx.initialCameraPos = camera.position.clone();
			ctx.initialTarget = mc.clone();
		};

		const onError = (err) => { console.error('[ChatPreview3D] Load error:', err); };

		const onLoadGeometry = (geometry) => {
			geometry.computeVertexNormals();
			const material = new THREE.MeshStandardMaterial({ color: 0x8899aa, flatShading: true });
			_addModel(new THREE.Mesh(geometry, material));
		};

		// Strip fragment hint before passing to loader
		const loadUrl = modelUrl.replace(/#.*$/, '');

		if (ext === 'mesh_dict') {
			// JSON mesh dictionary — decode from data URL and build geometry
			try {
				const commaIdx = loadUrl.indexOf(',');
				const isB64 = loadUrl.slice(0, commaIdx).includes(';base64');
				const payload = loadUrl.slice(commaIdx + 1);
				const dict = JSON.parse(isB64 ? atob(payload) : decodeURIComponent(payload));
				const geometry = this._buildMeshFromDict(dict, THREE);
				if (geometry) {
					const hasColors = geometry.hasAttribute('color');
					const material = new THREE.MeshStandardMaterial({
						color: hasColors ? 0xffffff : 0x8899aa,
						vertexColors: hasColors,
						flatShading: !dict.normals && !dict.vertex_normals,
					});
					_addModel(new THREE.Mesh(geometry, material));
				} else { onError(new Error('Invalid mesh dictionary')); }
			} catch (e) { onError(e); }
		} else if (ext === 'ply' && PLYLoader) {
			new PLYLoader().load(loadUrl, onLoadGeometry, undefined, onError);
		} else if (ext === 'stl' && STLLoader) {
			new STLLoader().load(loadUrl, onLoadGeometry, undefined, onError);
		} else if (ext === 'obj' && OBJLoader) {
			new OBJLoader().load(loadUrl, _addModel, undefined, onError);
		} else if (ext === 'fbx' && FBXLoader) {
			new FBXLoader().load(loadUrl, _addModel, undefined, onError);
		} else {
			new GLTFLoader().load(loadUrl, (gltf) => _addModel(gltf.scene), undefined, onError);
		}

		const animate = () => {
			ctx.animId = requestAnimationFrame(animate);
			controls.update();
			renderer.render(scene, camera);
		};
		animate();

		// Stop render loop when canvas is removed from DOM
		ctx.observer = new MutationObserver(() => {
			if (!canvas.isConnected) {
				cancelAnimationFrame(ctx.animId);
				renderer.dispose();
				ctx.observer.disconnect();
				canvas._sg3dCtx = null;
			}
		});
		ctx.observer.observe(canvas.parentElement || document.body, { childList: true, subtree: true });
	}

	/** Sniff 3D model format from a data URL by decoding a small prefix. */
	_sniff3DFormat(dataUrl) {
		try {
			const commaIdx = dataUrl.indexOf(',');
			if (commaIdx < 0) return null;
			const isBase64 = dataUrl.slice(0, commaIdx).includes(';base64');
			const payload = dataUrl.slice(commaIdx + 1);
			let header;
			if (isBase64) {
				// Decode just the first 24 bytes (32 base64 chars)
				header = atob(payload.slice(0, 32));
			} else {
				header = decodeURIComponent(payload.slice(0, 40));
			}
			if (header.startsWith('ply\n') || header.startsWith('ply\r')) return 'ply';
			if (header.startsWith('solid ')) return 'stl';
			if (header.startsWith('glTF')) return 'glb';
			if (header.startsWith('Kaydara FBX')) return 'fbx';
			// OBJ: look for lines starting with v/f/vn
			if (/^(v |vn |vt |f |# )/.test(header)) return 'obj';
			// JSON mesh dict: {"vertices":... or {"points":...
			const trimmed = header.trimStart();
			if (trimmed.startsWith('{') && /["'](vertices|points|positions)["']/.test(trimmed)) return 'mesh_dict';
		} catch (_) {}
		return null;
	}

	/**
	 * Build a Three.js BufferGeometry from a mesh dictionary.
	 * Accepts: { vertices|points|positions: [[x,y,z],...], faces|triangles: [[i,j,k],...],
	 *            normals?: [...], colors?: [...], uvs?: [...] }
	 * Flat arrays (e.g. vertices: [x,y,z,x,y,z,...]) are also supported.
	 */
	_buildMeshFromDict(dict, THREE) {
		const geometry = new THREE.BufferGeometry();

		const rawVerts = dict.vertices || dict.points || dict.positions;
		if (!rawVerts || !rawVerts.length) return null;

		const flatVerts = Array.isArray(rawVerts[0]) ? rawVerts.flat() : rawVerts;
		geometry.setAttribute('position', new THREE.Float32BufferAttribute(flatVerts, 3));

		const rawFaces = dict.faces || dict.triangles || dict.indices;
		if (rawFaces && rawFaces.length) {
			const flatFaces = Array.isArray(rawFaces[0]) ? rawFaces.flat() : rawFaces;
			geometry.setIndex(Array.from(flatFaces));
		}

		const rawNormals = dict.normals || dict.vertex_normals;
		if (rawNormals && rawNormals.length) {
			const flatNormals = Array.isArray(rawNormals[0]) ? rawNormals.flat() : rawNormals;
			geometry.setAttribute('normal', new THREE.Float32BufferAttribute(flatNormals, 3));
		} else {
			geometry.computeVertexNormals();
		}

		const rawColors = dict.colors || dict.vertex_colors;
		if (rawColors && rawColors.length) {
			const flatColors = Array.isArray(rawColors[0]) ? rawColors.flat() : rawColors;
			const maxVal = flatColors.reduce((m, v) => Math.max(m, v), 0);
			const scale = maxVal > 1 ? 1 / 255 : 1;
			const itemSize = Array.isArray(rawColors[0]) ? rawColors[0].length : (flatColors.length / (flatVerts.length / 3));
			const scaledColors = scale === 1 ? flatColors : flatColors.map(c => c * scale);
			geometry.setAttribute('color', new THREE.Float32BufferAttribute(scaledColors, itemSize >= 4 ? 4 : 3));
		}

		const rawUVs = dict.uvs || dict.uv || dict.texcoords;
		if (rawUVs && rawUVs.length) {
			const flatUVs = Array.isArray(rawUVs[0]) ? rawUVs.flat() : rawUVs;
			geometry.setAttribute('uv', new THREE.Float32BufferAttribute(flatUVs, 2));
		}

		return geometry;
	}

	async _openFileOnGraph(fileUrl, fileName) {
		const app = this.app;
		if (!fileUrl) return;
		try {
			const response = await fetch(fileUrl, { method: 'POST' });
			if (!response.ok) throw new Error(`Fetch failed: ${response.status}`);
			const blob = await response.blob();
			const file = new File([blob], fileName, { type: blob.type || 'application/octet-stream' });
			const [cx, cy] = this._getViewportCenter();
			await app._handleCanvasFileDrop([file], cx, cy);
			app.draw();
		} catch (err) {
			console.error('[ChatPreview] Open on graph failed:', err);
		}
	}

	async _handleOpenOnGraph(fileUrl, fileName) {
		await this._openFileOnGraph(fileUrl, fileName);
	}

	async _refreshChatPreview(btn) {
		const previewEl = btn.closest('.sg-chat-preview');
		if (!previewEl) return;

		const cacheId = btn.dataset.cacheId;
		let fileUrl = btn.dataset.fileUrl;
		// Re-read from disk via FileSystemFileHandle if available
		const fileHandle = cacheId ? _getPreviewHandle(cacheId) : null;
		if (fileHandle) {
			try {
				const file = await fileHandle.getFile();
				const isText = file.type.startsWith('text/') || file.type === 'application/json';
				const freshData = await new Promise((resolve, reject) => {
					const reader = new FileReader();
					reader.onload = () => resolve(reader.result);
					reader.onerror = () => reject(reader.error);
					if (isText) reader.readAsText(file);
					else reader.readAsDataURL(file);
				});
				// Update the cache with fresh data
				_previewDataCache.set(cacheId, freshData);
				fileUrl = freshData;
			} catch (err) {
				console.warn('[ChatPreview] Failed to re-read file from disk:', err);
			}
		}
		// Resolve cached data URL if needed
		if (!fileUrl && cacheId) {
			fileUrl = _getPreviewData(cacheId) || '';
		}
		const fileName = btn.dataset.fileName;
		const type = btn.dataset.previewType;
		if (!fileUrl) return; // nothing to refresh
		const ts = Date.now();
		const isDataUrl = fileUrl.startsWith('data:');
		const bustUrl = isDataUrl ? fileUrl : `${fileUrl}?t=${ts}`;

		// Refresh the content below the header
		switch (type) {
			case 'image': {
				const img = previewEl.querySelector('.sg-chat-preview-img');
				if (img) _fetchBlobUrl(bustUrl).then(blobUrl => { img.src = blobUrl; }).catch(() => {});
				break;
			}
			case 'audio': {
				const audio = previewEl.querySelector('.sg-chat-preview-audio');
				if (audio) _fetchBlobUrl(bustUrl).then(blobUrl => { audio.src = blobUrl; audio.load(); }).catch(() => {});
				break;
			}
			case 'video': {
				const video = previewEl.querySelector('.sg-chat-preview-video');
				if (video) _fetchBlobUrl(bustUrl).then(blobUrl => { video.src = blobUrl; video.load(); }).catch(() => {});
				break;
			}
			case 'text': {
				const body = previewEl.querySelector('.sg-chat-preview-text-body');
				if (body) {
					body.innerHTML = 'Loading...';
					fetch(bustUrl, { method: 'POST' }).then(r => r.text()).then(text => {
						const escaped = text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
						body.innerHTML = `<pre class="sg-chat-preview-text-content">${escaped}</pre>`;
					}).catch(() => {
						body.innerHTML = `<span style="color:#f44">Failed to load file</span>`;
					});
				}
				break;
			}
			case 'model3d': {
				const canvas = previewEl.querySelector('.sg-chat-preview-3d-canvas');
				if (canvas && window.ThreeViewer) {
					(async () => {
						let modelUrl;
						if (isDataUrl) {
							modelUrl = fileName ? `${bustUrl}#${encodeURIComponent(fileName)}` : bustUrl;
						} else {
							try {
								const blobUrl = await _fetchBlobUrl(bustUrl);
								modelUrl = fileName ? `${blobUrl}#${encodeURIComponent(fileName)}` : blobUrl;
							} catch { modelUrl = bustUrl; }
						}
						this._init3DPreview(canvas, modelUrl);
					})();
				}
				break;
			}
		}

		// Visual feedback
		btn.style.opacity = '0.3';
		setTimeout(() => { btn.style.opacity = ''; }, 300);
	}

	_handleGraphToChat(node, info) {
		// info: { fileData, fileName, mimeType, previewType } from graph preview node
		const ext = (info.fileName || '').split('.').pop()?.toLowerCase() || '';
		const type = info.previewType || _chatPreviewTypeFromExt(ext);

		if (info.fileUrl) {
			const marker = `<<preview:${type}:${info.fileUrl}>>`;
			this.app.api.chat?.addMessage(node, MessageRole.SYSTEM, marker);
		} else if (info.fileData != null && info.fileName) {
			let dataStr = typeof info.fileData === 'string' ? info.fileData : JSON.stringify(info.fileData, null, 2);

			// Binary preview types need data URLs — convert non-data-URL values
			const binaryTypes = ['image', 'model3d', 'audio', 'video'];
			if (binaryTypes.includes(type) && !dataStr.startsWith('data:')) {
				// Encode raw content (e.g. mesh dict JSON) as a data URL
				const bytes = new TextEncoder().encode(dataStr);
				let bin = '';
				for (let i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]);
				dataStr = `data:application/json;base64,${btoa(bin)}`;
			}

			if (dataStr.startsWith('data:')) {
				// Cache data URL and create preview marker
				const cacheId = _storePreviewData(dataStr);
				const marker = `<<preview:${type}:cached:${cacheId}:${info.fileName}>>`;
				this.app.api.chat?.addMessage(node, MessageRole.SYSTEM, marker);
			} else {
				// Text-type previews: use file_content marker
				const marker = `<<file_content:${info.fileName}>>\n${dataStr}`;
				this.app.api.chat?.addMessage(node, MessageRole.SYSTEM, marker);
			}
		}
	}

	async _handleFileDropOnChat(node, files) {
		for (const file of files) {
			const ext = file.name.split('.').pop()?.toLowerCase() || '';
			const type = _chatPreviewTypeFromExt(ext);

			// Text-type files: read as text and use file_content marker
			const textTypes = ['text', 'json'];
			if (textTypes.includes(type)) {
				const text = await new Promise((resolve) => {
					const reader = new FileReader();
					reader.onload = () => resolve(reader.result);
					reader.onerror = () => resolve(null);
					reader.readAsText(file);
				});
				if (text != null) {
					const marker = `<<file_content:${file.name}>>\n${text}`;
					this.app.api.chat?.addMessage(node, MessageRole.SYSTEM, marker);
				}
				continue;
			}

			// Binary files: read as data URL and cache
			const dataUrl = await new Promise((resolve) => {
				const reader = new FileReader();
				reader.onload = () => resolve(reader.result);
				reader.onerror = () => resolve(null);
				reader.readAsDataURL(file);
			});
			if (dataUrl) {
				const cacheId = _storePreviewData(dataUrl);
				if (file._fileHandle) _storePreviewHandle(cacheId, file._fileHandle);
				const marker = `<<preview:${type}:cached:${cacheId}:${file.name}>>`;
				this.app.api.chat?.addMessage(node, MessageRole.SYSTEM, marker);
			}
		}
	}

	_getViewportCenter() {
		const app = this.app;
		const canvas = app.canvas;
		const g = app.graph;
		const sw = canvas?.width || 800;
		const sh = canvas?.height || 600;
		return app.screenToWorld?.(sw / 2, sh / 2) || [0, 0];
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

	_handleWorkflowImport(node, msgId) {
		const msg = node.chatMessages.find(m => m.id === msgId);
		if (!msg?.workflow) return;

		const app = this.app;
		const schemas = app.graph.getRegisteredSchemas().filter(s => app.graph.isWorkflowSchema(s));
		if (schemas.length === 0) {
			app.showError?.('No workflow schema registered');
			return;
		}

		try {
			app.api.workflow.import(msg.workflow, schemas[0], {});
			app.applyLayout?.('hierarchical-horizontal');
			app.centerView?.();
		} catch (err) {
			app.showError?.('Import failed: ' + err.message);
		}
	}

	_handleWorkflowMerge(node, msgId) {
		const msg = node.chatMessages.find(m => m.id === msgId);
		if (!msg?.workflow) return;

		const app = this.app;
		const schemas = app.graph.getRegisteredSchemas().filter(s => app.graph.isWorkflowSchema(s));
		if (schemas.length === 0) {
			app.showError?.('No workflow schema registered');
			return;
		}

		try {
			app.api.workflow.import(msg.workflow, schemas[0], { merge: true });
			app.applyLayout?.('hierarchical-horizontal');
			app.centerView?.();
		} catch (err) {
			app.showError?.('Merge failed: ' + err.message);
		}
	}

	_handleWorkflowCopy(node, msgId, btn) {
		const msg = node.chatMessages.find(m => m.id === msgId);
		if (!msg?.workflow) return;
		const json = JSON.stringify(msg.workflow, null, 2);
		navigator.clipboard.writeText(json).then(() => {
			const orig = btn.textContent;
			btn.textContent = 'Copied!';
			setTimeout(() => { btn.textContent = orig; }, 1500);
		}).catch(err => {
			this.app.showError?.('Copy failed: ' + err.message);
		});
	}

	_handleWorkflowOpenTab(node, msgId) {
		const msg = node.chatMessages.find(m => m.id === msgId);
		if (!msg?.workflow) return;
		const app = this.app;
		const schemas = app.graph.getRegisteredSchemas().filter(s => app.graph.isWorkflowSchema(s));
		if (schemas.length === 0) {
			app.showError?.('No workflow schema registered');
			return;
		}
		try {
			const name = msg.workflow?.options?.name || 'Generated';
			app.api.tabs.add(name);
			app.api.workflow.import(msg.workflow, schemas[0], {});
			app.applyLayout?.('hierarchical-horizontal');
			app.centerView?.();
		} catch (err) {
			app.showError?.('Open in tab failed: ' + err.message);
		}
	}

	_showDropHighlight(overlay) {
		if (overlay._dropHighlight) return;
		const w = overlay.offsetWidth, h = overlay.offsetHeight;
		if (!w || !h) return;
		const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
		svg.setAttribute('class', 'sg-chat-drop-highlight');
		svg.setAttribute('width', w);
		svg.setAttribute('height', h);
		svg.setAttribute('viewBox', `0 0 ${w} ${h}`);
		const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
		rect.setAttribute('x', '1'); rect.setAttribute('y', '1');
		rect.setAttribute('width', w - 2); rect.setAttribute('height', h - 2);
		rect.setAttribute('rx', '4'); rect.setAttribute('ry', '4');
		rect.setAttribute('fill', 'rgba(218,186,60,0.06)');
		rect.setAttribute('stroke', 'rgba(218,186,60,0.9)');
		rect.setAttribute('stroke-width', '2');
		rect.setAttribute('stroke-dasharray', '6 4');
		svg.appendChild(rect);
		overlay.appendChild(svg);
		overlay._dropHighlight = svg;
	}

	_hideDropHighlight(overlay) {
		if (overlay._dropHighlight) { overlay._dropHighlight.remove(); overlay._dropHighlight = null; }
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

		// Receive preview data from graph nodes (Send to Chat button)
		this.on('preview:sendToChat', (e) => {
			this._handleReceivePreview(e);
		});

		// Detect canvas node dropped over a chat overlay
		this.on('mouse:up', (data) => {
			const dragNode = this.app.dragNode;
			if (!dragNode) return;
			const screenX = data.event?.clientX;
			const screenY = data.event?.clientY;
			if (screenX == null || screenY == null) return;
			const chatNode = this._findChatOverlayAtPoint(screenX, screenY);
			if (!chatNode) return;

			// Get preview data from the dragged node
			const previewData = this.app._getPreviewData?.(dragNode);
			if (previewData?.value) {
				this._handleReceivePreview({
					type: previewData.type,
					value: previewData.value,
					fileName: dragNode.extra?.fileName || dragNode.displayTitle || dragNode.title || 'preview',
					meta: previewData.meta,
				}, chatNode);
			} else {
				// Not a preview node — try to get any text output
				const text = dragNode.extra?.fileData || this._getNodeTextContent(dragNode);
				if (text) {
					this.app.api.chat?.addMessage(chatNode, MessageRole.SYSTEM, String(text));
				}
			}
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

	_findChatOverlayAtPoint(clientX, clientY) {
		for (const [chatId, overlay] of this.overlayManager.overlays) {
			const rect = overlay.getBoundingClientRect();
			if (clientX >= rect.left && clientX <= rect.right && clientY >= rect.top && clientY <= rect.bottom) {
				return this.overlayManager.nodeRefs.get(chatId);
			}
		}
		return null;
	}

	_getNodeTextContent(node) {
		// Try output data from the node's first output slot
		for (let i = 0; i < (node.outputs?.length || 0); i++) {
			const data = node.getOutputData?.(i);
			if (data != null) return typeof data === 'object' ? JSON.stringify(data, null, 2) : String(data);
		}
		return null;
	}

	_handleReceivePreview(e, targetChatNode) {
		const chatNode = targetChatNode || this.graph.nodes.find(n => n.isChat && n.chatId);
		if (!chatNode) return;

		const dataType = e.type || 'file';
		const value = e.value || '';
		let fileName = e.fileName || 'preview';

		// Ensure fileName has an extension (use metadata when available)
		if (!fileName.includes('.')) {
			const fmt = (e.meta?.format || '').toLowerCase();
			if (fmt) {
				fileName = `${fileName}.${fmt}`;
			} else if (typeof value === 'string' && value.startsWith('data:')) {
				// Infer from data URL MIME type
				const mime = value.slice(5, value.indexOf(';'));
				const ext = _mimeToExt(mime);
				fileName = `${fileName}.${ext || 'bin'}`;
			} else {
				const extMap = { image: 'png', model3d: 'glb', audio: 'mp3', video: 'mp4', text: 'txt', json: 'json' };
				fileName = `${fileName}.${extMap[dataType] || 'bin'}`;
			}
		}

		// Map graph preview type to chat preview type
		const typeMap = { image: 'image', audio: 'audio', video: 'video', model3d: 'model3d' };
		const previewType = typeMap[dataType] || 'text';

		if (typeof value === 'string' && value.startsWith('data:')) {
			// Store large data URL in cache, reference by ID in marker
			const cacheId = _storePreviewData(value);
			const marker = `<<preview:${previewType}:cached:${cacheId}:${fileName}>>`;
			this.app.api.chat?.addMessage(chatNode, MessageRole.SYSTEM, marker);
		} else if (typeof value === 'string') {
			// Plain text / structured content — use file_content marker
			const marker = `<<file_content:${fileName}>>\n${value}`;
			this.app.api.chat?.addMessage(chatNode, MessageRole.SYSTEM, marker);
		}
	}

	_reapplyChatToAllNodes() {
		for (const node of this.graph.nodes) {
			const schemaName = node.schemaName;
			const modelName = node.modelName;
			if (!schemaName || !modelName) continue;
			const chatConfig = this.schemaChats[schemaName]?.[modelName];
			if (!chatConfig) continue;

			try {
				if (node.isChat && node.chatId) {
					// Fully initialised (chatId set by initChat) — preserve messages/state.
					// createOverlay handles both existing (rebind) and missing (recreate) overlays.
					// updateMessages then restores the chat history into the DOM without resetting it.
					this.overlayManager.createOverlay(node);
					this.overlayManager.updateMessages(node);
				} else {
					// Not yet fully initialised — decorator may have set isChat=true early,
					// but initChat was never called (chatId is the definitive initialized signal).
					this._applyChatToNode(node);
				}
			} catch (err) {
				console.error(`[ChatExtension] Error processing chat for node ${node.id}:`, err);
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
					self.overlayManager.updateMessages(node, true);
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
					self.overlayManager.updateMessages(node, true);
				}
			},
			endStreaming: (nodeOrId) => {
				const node = typeof nodeOrId === 'object' ? nodeOrId : self.graph.getNodeById(nodeOrId);
				if (node?.isChat) {
					node.chatState = ChatState.READY;
					self.overlayManager.updateStatus(node);
				}
			},

			setBaseUrl: (url) => { self._baseUrl = url; },
			ChatState,
			MessageRole
		};

		this._baseUrl = '';
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

			.sg-chat-btn-active {
				background: var(--sg-accent, rgba(100, 149, 237, 0.3));
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
				cursor: grab;
			}
			.sg-chat-msg:active {
				cursor: grabbing;
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

			.sg-chat-hide-system > .sg-chat-msg-system:not(.sg-chat-msg-has-preview) {
				display: none;
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

			.sg-chat-input:disabled {
				opacity: 0.5;
				cursor: not-allowed;
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

			.sg-chat-workflow-actions {
				display: flex;
				flex-wrap: wrap;
				gap: 5px;
				margin-top: 6px;
			}

			.sg-chat-workflow-import-btn,
			.sg-chat-workflow-merge-btn {
				padding: 3px 10px;
				border: 1px solid var(--sg-accent-blue, #4a90d9);
				background: rgba(74, 144, 217, 0.15);
				color: var(--sg-accent-blue, #4a90d9);
				border-radius: 4px;
				cursor: pointer;
				font-size: 11px;
				transition: background 0.15s, color 0.15s;
			}

			.sg-chat-workflow-import-btn:hover,
			.sg-chat-workflow-merge-btn:hover {
				background: var(--sg-accent-blue, #4a90d9);
				color: #fff;
			}

			.sg-chat-workflow-preview {
				width: 100%;
				margin-top: 4px;
				font-size: 10px;
				color: var(--sg-text-tertiary, #888);
			}

			.sg-chat-workflow-preview summary {
				cursor: pointer;
				user-select: none;
			}

			.sg-chat-workflow-json {
				max-height: 120px;
				overflow-y: auto;
				font-size: 9px;
				background: var(--sg-bg-primary, rgba(0,0,0,0.3));
				padding: 4px 6px;
				border-radius: 3px;
				margin-top: 4px;
				white-space: pre;
			}

			/* Chat inline previews */
			.sg-chat-preview {
				margin: 6px 0;
				border-radius: 6px;
				overflow: hidden;
				background: rgba(0,0,0,0.2);
				border: 1px solid rgba(255,255,255,0.1);
			}
			.sg-chat-preview-header {
				display: flex;
				align-items: center;
				justify-content: space-between;
				padding: 4px 8px;
				font-size: 10px;
				color: rgba(255,255,255,0.5);
				background: rgba(0,0,0,0.15);
			}
			.sg-chat-preview-filename {
				overflow: hidden;
				text-overflow: ellipsis;
				white-space: nowrap;
				flex: 1;
				min-width: 0;
			}
			.sg-chat-preview-actions {
				display: flex;
				gap: 2px;
				flex-shrink: 0;
			}
			.sg-chat-preview-refresh-btn {
				display: inline-flex;
				align-items: center;
				justify-content: center;
				width: 20px;
				height: 18px;
				font-size: 14px;
				line-height: 1;
				cursor: pointer;
				color: rgba(255,255,255,0.4);
				border-radius: 3px;
				user-select: none;
				transition: opacity 0.2s;
			}
			.sg-chat-preview-refresh-btn:hover {
				color: #fff;
				background: rgba(255,255,255,0.15);
			}
			.sg-chat-preview-drag-handle {
				display: inline-flex;
				align-items: center;
				justify-content: center;
				width: 20px;
				height: 18px;
				font-size: 14px;
				line-height: 1;
				cursor: grab;
				color: rgba(255,255,255,0.4);
				border-radius: 3px;
				user-select: none;
			}
			.sg-chat-preview-drag-handle:hover {
				color: #fff;
				background: rgba(255,255,255,0.15);
			}
			.sg-chat-preview-drag-handle:active {
				cursor: grabbing;
			}
			@keyframes sg-chat-drop-march {
				from { stroke-dashoffset: 0; }
				to   { stroke-dashoffset: -20; }
			}
			.sg-chat-drop-highlight {
				position: absolute;
				inset: 0;
				pointer-events: none;
				z-index: 9999;
				overflow: visible;
			}
			.sg-chat-drop-highlight rect {
				animation: sg-chat-drop-march 0.67s linear infinite;
			}
			.sg-chat-preview-img {
				display: block;
				max-width: 100%;
				max-height: 200px;
				object-fit: contain;
			}
			.sg-chat-preview-audio {
				display: block;
				width: 100%;
				height: 36px;
			}
			.sg-chat-preview-video {
				display: block;
				max-width: 100%;
				max-height: 200px;
			}
			.sg-chat-preview-3d-wrapper {
				position: relative;
			}
			.sg-chat-preview-3d-canvas {
				display: block;
				width: 100%;
				height: 200px;
				border-radius: 0 0 6px 6px;
			}
			.sg-chat-preview-3d-reset-btn {
				position: absolute;
				bottom: 6px;
				right: 6px;
				padding: 2px 8px;
				font-size: 10px;
				line-height: 1.4;
				background: rgba(0,0,0,0.5);
				color: rgba(255,255,255,0.7);
				border: 1px solid rgba(255,255,255,0.2);
				border-radius: 3px;
				cursor: pointer;
				z-index: 1;
			}
			.sg-chat-preview-3d-reset-btn:hover {
				background: rgba(0,0,0,0.7);
				color: #fff;
			}
			.sg-chat-preview-3d-placeholder {
				padding: 20px;
				text-align: center;
				font-size: 11px;
				color: rgba(255,255,255,0.4);
			}
			.sg-chat-preview-text-placeholder {
				padding: 8px;
				font-size: 11px;
			}
			.sg-chat-preview-text-placeholder a {
				color: #6db3f2;
				text-decoration: none;
			}
			.sg-chat-preview-text-placeholder a:hover {
				text-decoration: underline;
			}
			.sg-chat-preview-text-body {
				padding: 6px 8px;
				font-size: 10px;
				color: rgba(255,255,255,0.5);
			}
			.sg-chat-preview-text-content {
				margin: 0;
				padding: 0;
				font-size: 10px;
				line-height: 1.4;
				color: rgba(255,255,255,0.8);
				white-space: pre-wrap;
				word-wrap: break-word;
				max-height: 200px;
				overflow-y: auto;
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
				if (node.schemaName === schemaName && !node.chatId) {
					// Gate on chatId (set by initChat) — not isChat, which may be set early
					// by the decorator parser before initChat is actually called.
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
