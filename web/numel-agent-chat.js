/* ========================================================================
   NUMEL AGENT CHAT MANAGER
   Handles agent connections and chat events via AG-UI protocol
   Depends on: schemagraph-chat-ext.js, agui-bundle.js
   ======================================================================== */

console.log('[Numel] Loading agent chat manager...');

// ========================================================================
// Agent Handler - Individual agent connection
// ========================================================================

class AgentHandler {
	constructor() {
		this._clear();
	}

	static _randomId() {
		return ([1e7] + -1e3 + -4e3 + -8e3 + -1e11).replace(/[018]/g, a =>
			(a ^ Math.random() * 16 >> a / 4).toString(16)
		);
	}

	static _randomMessageId() {
		return `numel-message-${AgentHandler._randomId()}`;
	}

	_clear() {
		this.url = null;
		this.name = null;
		this.callbacks = null;
		this.agent = null;
		this.onEvent = null;
	}

	_handleAGUIEvent(event) {
		if (!event) return;

		this.onEvent?.(event);

		const message = event.delta || event.error || event.tool_name || event.type || '<EMPTY>';
		this.callbacks[event.type]?.(message);
	}

	connect(
		url,
		name = null,
		onEvent = null,
		onRunStarted = null,
		onRunFinished = null,
		onRunError = null,
		onToolCallStart = null,
		onToolCallResult = null,
		onTextMessageStart = null,
		onTextMessageEnd = null,
		onTextMessageContent = null,
	) {
		this.disconnect();

		// Check if AGUI is available
		if (typeof AGUI === 'undefined') {
			console.error('[AgentHandler] AGUI not available');
			return false;
		}

		const callbacks = {};
		callbacks[AGUI.EventType.RUN_STARTED] = onRunStarted;
		callbacks[AGUI.EventType.RUN_FINISHED] = onRunFinished;
		callbacks[AGUI.EventType.RUN_ERROR] = onRunError;
		callbacks[AGUI.EventType.TOOL_CALL_START] = onToolCallStart;
		callbacks[AGUI.EventType.TOOL_CALL_RESULT] = onToolCallResult;
		callbacks[AGUI.EventType.TEXT_MESSAGE_START] = onTextMessageStart;
		callbacks[AGUI.EventType.TEXT_MESSAGE_END] = onTextMessageEnd;
		callbacks[AGUI.EventType.TEXT_MESSAGE_CONTENT] = onTextMessageContent;
		callbacks[AGUI.EventType.TEXT_MESSAGE_CHUNK] = onTextMessageContent;

		const self = this;
		const target = `${url}/agui`;
		const subscriber = {
			onEvent(params) {
				self._handleAGUIEvent(params.event);
			}
		};

		const agent = new AGUI.HttpAgent({
			name: this.name,
			url: target,
		});
		agent.subscribe(subscriber);

		this.url = url;
		this.name = name;
		this.onEvent = onEvent;
		this.callbacks = callbacks;
		this.agent = agent;

		return true;
	}

	disconnect() {
		if (!this.isConnected()) {
			return false;
		}
		this._clear();
		return true;
	}

	isConnected() {
		return (this.agent != null);
	}

	async send(message) {
		if (!this.isConnected()) {
			return null;
		}
		const messageId = AgentHandler._randomMessageId();
		const userMessage = {
			id: messageId,
			role: "user",
			content: message,
		};
		this.agent.setMessages([userMessage]);
		return await this.agent.runAgent({});
	}
}

// ========================================================================
// Agent Chat Manager - Manages all agent chat connections
// ========================================================================

class AgentChatManager {
	constructor(url, app, syncWorkflowFn) {
		this.url = url;
		this.app = app;
		this.syncWorkflow = syncWorkflowFn;
		this.handlers = new Map(); // chatId -> { handler, port, dirty }

		this._setupListeners();
	}

	_setupListeners() {
		const { eventBus } = this.app;

		// Mark all handlers dirty on graph changes
		eventBus.on('graph:changed', () => this._markAllDirty());
		eventBus.on('link:created', () => this._markAllDirty());
		eventBus.on('link:removed', () => this._markAllDirty());
		eventBus.on('node:created', () => this._markAllDirty());
		eventBus.on('node:removed', (e) => {
			this._markAllDirty();
			this.disconnectNode(e.nodeId);
		});

		// Handle chat send events from ChatExtension
		eventBus.on('chat:send', (e) => this._handleSend(e));
	}

	_markAllDirty() {
		for (const entry of this.handlers.values()) {
			entry.dirty = true;
		}
	}

	async _handleSend({ node, message }) {
		const chatId = node.chatId;

		// Intercept /gen command for workflow generation
		const genMatch = message.match(/^\/gen\s+(.+)/s);
		if (genMatch) {
			return this._handleGenerate(node, genMatch[1].trim());
		}

		try {
			// Ensure connected (lazy reconnect if dirty)
			await this._ensureConnected(node);

			const entry = this.handlers.get(chatId);
			if (!entry?.handler?.isConnected()) {
				throw new Error('Not connected to agent');
			}

			// Send message
			this.app.api.chat.setState(node, ChatState.SENDING);
			await entry.handler.send(message);

		} catch (err) {
			this.app.api.chat.setState(node, ChatState.ERROR, err.message);
			this.app.api.chat.addMessage(node, MessageRole.ERROR, err.message);
		}
	}

	async _ensureConnected(node) {
		const chatId = node.chatId;
		let entry = this.handlers.get(chatId);

		const agentConfig = this._getConnectedAgentConfig(node);
		const currentPort = agentConfig?.annotations?.port || agentConfig?.port;
		const needsReconnect = !entry || entry.dirty || !entry.handler?.isConnected();

		if (!needsReconnect && entry.port === currentPort) {
			return;
		}

		this.app.api.chat.setState(node, ChatState.CONNECTING);

		await this.syncWorkflow();

		// Re-fetch node by chatId after sync
		const newNode = this._findNodeByChatId(chatId);
		if (!newNode) {
			throw new Error('Chat node not found after sync');
		}

		const updatedConfig = this._getConnectedAgentConfig(newNode);
		const port = updatedConfig?.annotations?.port || updatedConfig?.port;

		if (!port) {
			throw new Error('No agent port assigned - check AgentConfig connection');
		}

		if (entry?.handler?.isConnected()) {
			entry.handler.disconnect();
		}

		const handler = new AgentHandler();
		const baseUrl = this.url.substr(0, this.url.lastIndexOf(":"));
		const url = `${baseUrl}:${port}`;
		const name = updatedConfig?.options?.name || null;
		const callbacks = this._createCallbacks(newNode, chatId);

		handler.connect(url, name, ...Object.values(callbacks));

		this.handlers.set(chatId, { handler, port, dirty: false });

		this.app.api.chat.setState(newNode, ChatState.READY);
	}

	_findNodeByChatId(chatId) {
		for (const node of this.app.graph.nodes) {
			if (node.chatId === chatId) return node;
		}
		return null;
	}

	_getConnectedAgentConfig(chatNode) {
		const configSlotIdx = chatNode.getInputSlotByName?.('config');
		if (configSlotIdx < 0) return null;

		const input = chatNode.inputs?.[configSlotIdx];
		if (!input?.link) return null;

		const link = this.app.graph.links[input.link];
		if (!link) return null;

		const configNode = this.app.graph.getNodeById(link.origin_id);
		if (!configNode) return null;

		return this._extractNodeData(configNode);
	}

	_extractNodeData(node) {
		const data = {
			...node.constantFields,
			annotations: { ...node.annotations }
		};

		if (node.annotations) {
			Object.assign(data, node.annotations);
		}

		for (let i = 0; i < (node.inputs?.length || 0); i++) {
			const input = node.inputs[i];
			const name = input.name;

			const baseName = name.split('.')[0];
			if (node.multiInputSlots?.[baseName]) continue;

			const connected = node.getInputData?.(i);
			if (connected !== undefined && connected !== null) {
				data[name] = connected;
				continue;
			}

			const native = node.nativeInputs?.[i];
			if (native?.value !== null && native?.value !== undefined && native?.value !== '') {
				data[name] = native.value;
			}
		}

		return data;
	}

	_createCallbacks(node, chatId) {
		const api = this.app.api.chat;

		const getNode = () => this._findNodeByChatId(chatId);

		return {
			onEvent: (event) => {
				console.debug(`[AgentChat:${chatId}]`, event);
			},
			onRunStarted: () => { },
			onRunFinished: () => {
				const n = getNode();
				if (n) this._updateResponseOutput(n);
			},
			onRunError: (error) => {
				const n = getNode();
				if (!n) return;
				const msg = error?.message || String(error) || 'Agent error';
				api.setState(n, ChatState.ERROR, msg);
				api.addMessage(n, MessageRole.ERROR, msg);
			},
			onToolCallStart: (toolName) => {
				const n = getNode();
				if (n) api.addMessage(n, MessageRole.SYSTEM, `Tool: ${toolName}...`);
			},
			onToolCallResult: (toolName) => {
				const n = getNode();
				if (!n) return;
				const messages = n.chatMessages || [];
				const lastSystem = [...messages].reverse().find(m =>
					m.role === MessageRole.SYSTEM && m.content.includes(toolName)
				);
				if (lastSystem) {
					lastSystem.content = `Tool: ${toolName} done`;
					api.updateLastMessage(n, lastSystem.content, false);
				}
			},
			onTextMessageStart: () => {
				const n = getNode();
				if (n) api.startStreaming(n);
			},
			onTextMessageEnd: () => {
				const n = getNode();
				if (n) api.endStreaming(n);
			},
			onTextMessageContent: (chunk) => {
				const n = getNode();
				if (n) api.appendStream(n, chunk);
			}
		};
	}

	_updateResponseOutput(node) {
		const messages = node.chatMessages || [];
		const lastAssistant = [...messages].reverse()
			.find(m => m.role === MessageRole.ASSISTANT);

		if (lastAssistant) {
			const outputIdx = node.getOutputSlotByName?.('response');
			if (outputIdx >= 0) {
				node.setOutputData(outputIdx, lastAssistant.content);
			}
		}
	}

	// ================================================================
	// /gen command — Workflow generation via chat
	// ================================================================

	async _handleGenerate(node, description) {
		const api = this.app.api.chat;

		try {
			api.setState(node, ChatState.SENDING);

			// Collect full agent subgraph config from connected nodes
			const agentConfig = this._collectGenerationConfig(node);

			const resp = await fetch(this.url + '/generate-workflow', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({
					prompt: description,
					...agentConfig,
				})
			});

			if (!resp.ok) {
				const detail = await resp.json().catch(() => ({}));
				throw new Error(detail.detail || `HTTP ${resp.status}`);
			}

			const data = await resp.json();

			// Store workflow on node for later import
			node._lastGeneratedWorkflow = data.workflow;

			// Add assistant message with workflow metadata for Import button
			const summary = data.message || 'Generated workflow';
			api.addMessage(node, MessageRole.ASSISTANT, summary, {
				workflow: data.workflow
			});

			api.setState(node, ChatState.READY);

		} catch (err) {
			api.setState(node, ChatState.ERROR, err.message);
			api.addMessage(node, MessageRole.ERROR, `Generation failed: ${err.message}`);
		}
	}

	// ================================================================
	// Graph traversal helpers for config collection
	// ================================================================

	_getConnectedNode(node, slotName) {
		const slotIdx = node.getInputSlotByName?.(slotName);
		if (slotIdx == null || slotIdx < 0) return null;
		const input = node.inputs?.[slotIdx];
		if (!input?.link) return null;
		const link = this.app.graph.links[input.link];
		if (!link) return null;
		return this.app.graph.getNodeById(link.origin_id);
	}

	_getConnectedMultiInputNodes(node, fieldName) {
		const indices = node.multiInputSlots?.[fieldName];
		if (!indices || indices.length === 0) return [];

		const results = [];
		for (const idx of indices) {
			const multiEntry = node.multiInputs?.[idx];
			if (!multiEntry?.links?.length) continue;
			const linkId = multiEntry.links[0];
			const link = this.app.graph.links[linkId];
			if (!link) continue;
			const connectedNode = this.app.graph.getNodeById(link.origin_id);
			if (connectedNode) results.push(connectedNode);
		}
		return results;
	}

	_collectGenerationConfig(chatNode) {
		const configNode = this._getConnectedNode(chatNode, 'config');
		if (!configNode) return {};

		const config = {};

		// Backend
		const backendNode = this._getConnectedNode(configNode, 'backend');
		if (backendNode) {
			const cf = backendNode.constantFields || {};
			config.backend = { engine: cf.name || 'agno' };
		}

		// Model
		const modelNode = this._getConnectedNode(configNode, 'model');
		if (modelNode) {
			const cf = modelNode.constantFields || {};
			config.model = {
				source:  cf.source  || 'ollama',
				name:    cf.name    || 'mistral',
				version: cf.version || '',
			};
		}

		// Options
		const optionsNode = this._getConnectedNode(configNode, 'options');
		if (optionsNode) {
			const cf = optionsNode.constantFields || {};
			config.options = {
				name:            cf.name            || null,
				description:     cf.description     || null,
				instructions:    cf.instructions    || null,
				prompt_override: cf.prompt_override || null,
				markdown:        cf.markdown === true || cf.markdown === 'true',
			};
		}

		// Memory Manager
		const memoryNode = this._getConnectedNode(configNode, 'memory_mgr');
		if (memoryNode) {
			const cf = memoryNode.constantFields || {};
			config.memory = {
				query:   cf.query   === true || cf.query   === 'true',
				update:  cf.update  === true || cf.update  === 'true',
				managed: cf.managed === true || cf.managed === 'true',
				prompt:  cf.prompt  || null,
			};
		}

		// Session Manager
		const sessionNode = this._getConnectedNode(configNode, 'session_mgr');
		if (sessionNode) {
			const cf = sessionNode.constantFields || {};
			config.session = {
				query:        cf.query  === true || cf.query  === 'true',
				update:       cf.update === true || cf.update === 'true',
				history_size: parseInt(cf.history_size) || 10,
				prompt:       cf.prompt || null,
			};
		}

		// Tools (MULTI_INPUT)
		const toolNodes = this._getConnectedMultiInputNodes(configNode, 'tools');
		if (toolNodes.length > 0) {
			config.tools = toolNodes.map(tn => {
				const cf = tn.constantFields || {};
				return { name: cf.name || '', args: cf.args || null };
			}).filter(t => t.name);
		}

		// Knowledge Manager (with nested content_db / index_db)
		const knowledgeNode = this._getConnectedNode(configNode, 'knowledge_mgr');
		if (knowledgeNode) {
			const cf = knowledgeNode.constantFields || {};
			const knowledge = {
				query:       cf.query === true || cf.query === 'true' || cf.query == null,
				description: cf.description || null,
				max_results: parseInt(cf.max_results) || 10,
				urls:        cf.urls || null,
			};

			const contentDBNode = this._getConnectedNode(knowledgeNode, 'content_db');
			if (contentDBNode) {
				const cdb = contentDBNode.constantFields || {};
				knowledge.content_db = { engine: cdb.engine || 'sqlite', url: cdb.url || '' };
			}
			const indexDBNode = this._getConnectedNode(knowledgeNode, 'index_db');
			if (indexDBNode) {
				const idb = indexDBNode.constantFields || {};
				knowledge.index_db = { engine: idb.engine || 'lancedb', url: idb.url || '' };
			}

			config.knowledge = knowledge;
		}

		return config;
	}

	// ================================================================

	disconnectNode(nodeId) {
		const entry = this.handlers.get(nodeId);
		if (entry?.handler?.isConnected()) {
			entry.handler.disconnect();
		}
		this.handlers.delete(nodeId);
	}

	disconnectAll() {
		for (const [nodeId] of this.handlers) {
			this.disconnectNode(nodeId);
		}
	}
}

// ========================================================================
// EXPORTS
// ========================================================================

if (typeof window !== 'undefined') {
	window.AgentHandler = AgentHandler;
	window.AgentChatManager = AgentChatManager;
}

console.log('[Numel] Agent chat manager loaded');
