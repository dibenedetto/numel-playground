/* ========================================================================
   NUMEL AGENT CHAT MANAGER - Agent Chat Management
   ======================================================================== */

class AgentHandler {

	constructor() {
		this._clear();
	}

	static _randomId() {
		// https://gist.github.com/jed/982883?permalink_comment_id=852670#gistcomment-852670
		return ([1e7]+-1e3+-4e3+-8e3+-1e11).replace(/[018]/g,a=>(a^Math.random()*16>>a/4).toString(16));
	}

	static _randomMessageId() {
		const id = `numel-message-${AgentHandler._randomId()}`;
		return id;
	}

	_clear() {
		this.url       = null;
		this.name      = null;
		this.callbacks = null;
		this.agent     = null;
	}

	_handleAGUIEvent(event) {
		// addLog("ag-ui", event);
		if (!event) return;

		this.onEvent?.(event);

		const message = event.delta || event.error || event.tool_name || event.type || '<EMPTY>';
		this.callbacks[event.type]?.(message);
	}

	connect(
		url,
		name                 = null,
		onEvent              = null,
		onRunStarted         = null,
		onRunFinished        = null,
		onRunError           = null,
		onToolCallStart      = null,
		onToolCallResult     = null,
		onTextMessageStart   = null,
		onTextMessageEnd     = null,
		onTextMessageContent = null,
	) {
		this.disconnect();

		const callbacks = {}
		callbacks[AGUI.EventType.RUN_STARTED         ] = onRunStarted;
		callbacks[AGUI.EventType.RUN_FINISHED        ] = onRunFinished;
		callbacks[AGUI.EventType.RUN_ERROR           ] = onRunError;
		callbacks[AGUI.EventType.TOOL_CALL_START     ] = onToolCallStart;
		callbacks[AGUI.EventType.TOOL_CALL_RESULT    ] = onToolCallResult;
		callbacks[AGUI.EventType.TEXT_MESSAGE_START  ] = onTextMessageStart;
		callbacks[AGUI.EventType.TEXT_MESSAGE_END    ] = onTextMessageEnd;
		callbacks[AGUI.EventType.TEXT_MESSAGE_CONTENT] = onTextMessageContent;
		callbacks[AGUI.EventType.TEXT_MESSAGE_CHUNK  ] = onTextMessageContent;

		const self       = this;
		const target     = `${url}/agui`;
		const subscriber = {
			onEvent(params) {
				self._handleAGUIEvent(params.event)
			}
		};

		const agent = new AGUI.HttpAgent({
			name : this.name,
			url  : target,
		});
		agent.subscribe(subscriber);

		this.url       = url;
		this.name      = name;
		this.onEvent   = onEvent;
		this.callbacks = callbacks;
		this.agent     = agent;

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
		const messageId   = AgentHandler._randomMessageId();
		const userMessage = {
			id      : messageId,
			role    : "user",
			content : message,
		};
		this.agent.setMessages([userMessage]);
		return await this.agent.runAgent({});
	}
};


class AgentChatManager {
	constructor(url, app, syncWorkflowFn) {
		this.url = url;
		this.app = app;
		this.syncWorkflow = syncWorkflowFn;  // async () => Promise<void>
		this.handlers = new Map();           // nodeId -> { handler, port, dirty }
		
		this._setupListeners();
	}

	_setupListeners() {
		const { eventBus } = this.app;

		// Mark all handlers dirty on any graph change
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
		const nodeId = node.chatId;

		try {
			// Ensure connected (lazy reconnect if dirty)
			await this._ensureConnected(node);

			const entry = this.handlers.get(nodeId);
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
		const chatId = node.chatId;  // Stable ID
		let entry = this.handlers.get(chatId);

		const agentConfig = this._getConnectedAgentConfig(node);
		const currentPort = agentConfig?.annotations?.port || agentConfig?.port;
		const needsReconnect = !entry || entry.dirty || !entry.handler?.isConnected();

		if (!needsReconnect && entry.port === currentPort) {
			return;
		}

		this.app.api.chat.setState(node, ChatState.CONNECTING);

		await this.syncWorkflow();

		// Re-fetch node by chatId after sync (node reference is now stale)
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
		const name = updatedConfig?.info?.name || null;
		const callbacks = this._createCallbacks(newNode, chatId);  // Pass chatId

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

		// Include annotation fields at top level too for convenience
		if (node.annotations) {
			Object.assign(data, node.annotations);
		}

		// Extract native input values
		for (let i = 0; i < (node.inputs?.length || 0); i++) {
			const input = node.inputs[i];
			const name = input.name;

			// Skip multi-input base fields
			const baseName = name.split('.')[0];
			if (node.multiInputSlots?.[baseName]) continue;

			// Connected value
			const connected = node.getInputData?.(i);
			if (connected !== undefined && connected !== null) {
				data[name] = connected;
				continue;
			}

			// Native input value
			const native = node.nativeInputs?.[i];
			if (native?.value !== null && native?.value !== undefined && native?.value !== '') {
				data[name] = native.value;
			}
		}

		return data;
	}

	_createCallbacks(node, chatId) {
		const api = this.app.api.chat;
		
		// Always get fresh node reference via chatId
		const getNode = () => this._findNodeByChatId(chatId);

		return {
			onEvent: (event) => {
				console.debug(`[AgentChat:${chatId}]`, event);
			},
			onRunStarted: () => {},
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
				if (n) api.addMessage(n, MessageRole.SYSTEM, `🔧 ${toolName}...`);
			},
			onToolCallResult: (toolName) => {
				const n = getNode();
				if (!n) return;
				const messages = n.chatMessages || [];
				const lastSystem = [...messages].reverse().find(m => 
					m.role === MessageRole.SYSTEM && m.content.includes(toolName)
				);
				if (lastSystem) {
					lastSystem.content = `🔧 ${toolName} ✔`;
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

// Export
if (typeof window !== 'undefined') {
	window.AgentChatManager = AgentChatManager;
}
