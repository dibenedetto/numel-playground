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

		const type = event.type;
		if (type === AGUI.EventType.TOOL_CALL_START) {
			this.callbacks[type]?.(event.toolCallName || event.type);
		} else if (type === AGUI.EventType.TOOL_CALL_RESULT) {
			this.callbacks[type]?.(event.toolCallId, event.content);
		} else {
			const message = event.delta || event.error || event.type || '<EMPTY>';
			this.callbacks[type]?.(message);
		}
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

	async abortRun() {
		if (!this.isConnected() || !this.agent?.abortRun) {
			return false;
		}
		return await this.agent.abortRun();
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
	constructor(url, app, syncWorkflowFn, api) {
		this.url = url;
		this.api = api;  // NumelAPI instance
		this.app = app;
		this.syncWorkflow = syncWorkflowFn;
		this.handlers = new Map(); // chatId -> { handler, port, dirty }
		this.executionId = null;    // current workflow execution ID (null when idle)

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
		eventBus.on('chat:stop', (e) => this._handleStop(e));

		// Track workflow execution lifecycle
		eventBus.on('workflow:started', (e) => { this.executionId = e.execution_id; });
		eventBus.on('workflow:completed', () => { this.executionId = null; });
		eventBus.on('workflow:cancelled', () => { this.executionId = null; });
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

			const liveNode = this._resolveLiveChatNode(chatId, node);
			const entry = this.handlers.get(chatId);
			if (!entry?.handler?.isConnected()) {
				throw new Error('Not connected to agent');
			}

			// Send message
			entry.abortRequested = false;
			entry.abortSuppressedUntil = 0;
			entry.stopping = false;
			this.app.api.chat.setState(liveNode, ChatState.SENDING);
			await entry.handler.send(message);

		} catch (err) {
			const liveNode = this._resolveLiveChatNode(chatId, node);
			this.app.api.chat.setState(liveNode, ChatState.ERROR, err.message);
			this.app.api.chat.addMessage(liveNode, MessageRole.ERROR, err.message);
		}
	}

	async _ensureConnected(node) {
		const chatId = node.chatId;
		let entry = this.handlers.get(chatId);

		const agentConfig = this._getConnectedAgentConfig(node);
		const currentPort = agentConfig?.annotations?.port || agentConfig?.port;
		const needsReconnect = !entry || entry.dirty || !entry.handler?.isConnected();
		const needsSync = !!entry?.dirty || !currentPort;

		if (!needsReconnect && entry.port === currentPort) {
			return;
		}

		this.app.api.chat.setState(node, ChatState.CONNECTING);

		let newNode = node;
		let updatedConfig = agentConfig;
		let port = currentPort;
		if (needsSync) {
			await this.syncWorkflow(null, null, true);

			// Re-fetch node by chatId after sync
			newNode = this._findNodeByChatId(chatId);
			if (!newNode) {
				throw new Error('Chat node not found after sync');
			}

			updatedConfig = this._getConnectedAgentConfig(newNode);
			port = updatedConfig?.annotations?.port || updatedConfig?.port;
		}

		if (!newNode) {
			throw new Error('Chat node not found after sync');
		}

		if (!port) {
			const implResponse = await this.api.ensureWorkflowImpl();
			if (implResponse?.workflow) {
				this._applyImplementationPorts(implResponse.workflow);
				newNode = this._findNodeByChatId(chatId) || newNode;
				updatedConfig = this._getConnectedAgentConfig(newNode) || updatedConfig;
				port = updatedConfig?.annotations?.port || updatedConfig?.port;
			}
		}

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

		this.handlers.set(chatId, {
			handler,
			port,
			dirty: false,
			abortRequested: false,
			abortSuppressedUntil: 0,
			stopping: false,
		});

		this.app.api.chat.setState(newNode, ChatState.READY);

		// Auto-send from input field if wired and has data
		this._checkAutoSend(newNode);
	}

	_resolveLiveChatNode(chatId, fallback = null) {
		return this._findNodeByChatId(chatId) || fallback;
	}

	_applyImplementationPorts(workflowDoc) {
		const nodes = Array.isArray(workflowDoc?.nodes) ? workflowDoc.nodes : [];
		for (const graphNode of this.app.graph.nodes || []) {
			if (graphNode?.workflowIndex == null) continue;
			const savedNode = nodes[graphNode.workflowIndex];
			if (!savedNode || savedNode.type !== graphNode.workflowType) continue;
			if (savedNode.type !== 'agent_config') continue;
			const port = savedNode.port ?? savedNode.annotations?.port;
			if (!port) continue;
			graphNode.annotations = { ...(graphNode.annotations || {}), port };
			graphNode.port = port;
		}
	}

	async _checkAutoSend(node) {
		const inputField = node.chatConfig?.inputField;
		if (!inputField) return;

		const slotIdx = node.getInputSlotByName?.(inputField);
		if (slotIdx < 0) return;

		const inputData = node.getInputData?.(slotIdx);
		if (inputData == null || inputData === '') return;

		// Avoid re-sending the same input
		if (node._lastAutoSentInput === inputData) return;
		node._lastAutoSentInput = inputData;

		const text = String(inputData).trim();
		if (!text) return;

		const chatId = node.chatId;
		const entry = this.handlers.get(chatId);
		if (!entry?.handler?.isConnected()) return;

		try {
			this.app.api.chat.addMessage(node, MessageRole.USER, text);
			this.app.api.chat.setState(node, ChatState.SENDING);
			await entry.handler.send(text);
		} catch (err) {
			const liveNode = this._resolveLiveChatNode(chatId, node);
			this.app.api.chat.setState(liveNode, ChatState.ERROR, err.message);
			this.app.api.chat.addMessage(liveNode, MessageRole.ERROR, err.message);
		}
	}

	/**
	 * Called by the engine when it reaches an agent_chat node during workflow execution.
	 * Ensures the agent is connected and sends the request message if provided.
	 */
	async activateForExecution(node, request) {
		try {
			await this._ensureConnected(node);

			if (request != null && request !== '') {
				const chatId = node.chatId;
				const entry = this.handlers.get(chatId);
				if (!entry?.handler?.isConnected()) return;

				// Avoid re-sending the same request
				if (node._lastAutoSentInput === request) return;
				node._lastAutoSentInput = request;

				const text = String(request).trim();
				if (!text) return;

				this.app.api.chat.addMessage(node, MessageRole.USER, text);
				entry.abortRequested = false;
				entry.abortSuppressedUntil = 0;
				entry.stopping = false;
				this.app.api.chat.setState(node, ChatState.SENDING);
				await entry.handler.send(text);
			}
		} catch (err) {
			console.error('[AgentChat] activateForExecution error:', err);
			const liveNode = this._resolveLiveChatNode(node.chatId, node);
			this.app.api.chat.setState(liveNode, ChatState.ERROR, err.message);
			this.app.api.chat.addMessage(liveNode, MessageRole.ERROR, err.message);
		}
	}

	_isAbortLikeError(error) {
		const name = String(error?.name || '');
		const message = String(error?.message || error || '').toLowerCase();
		return (
			name === 'AbortError'
			|| message.includes('bodystreambuffer was aborted')
			|| message.includes('aborted')
			|| message.includes('cancelled')
		);
	}

	_shouldSuppressAbortError(entry, error) {
		if (!entry) return false;
		return this._isAbortLikeError(error) && Number(entry.abortSuppressedUntil || 0) > Date.now();
	}

	_getLatestAssistantText(node) {
		const messages = Array.isArray(node?.chatMessages) ? node.chatMessages : [];
		const lastAssistant = [...messages].reverse().find((message) => message?.role === MessageRole.ASSISTANT);
		return lastAssistant ? String(lastAssistant.content || '') : '';
	}

	async _finalizeInterruptedChat(node, { signalEmptyResponse = false } = {}) {
		if (!node) return;
		const api = this.app.api.chat;
		const assistantText = this._getLatestAssistantText(node);
		const responseText = assistantText || (signalEmptyResponse ? '' : null);

		api.setState(node, ChatState.READY);
		if (responseText !== null) {
			const outputField = node.chatConfig?.outputField || 'output';
			const outputIdx = node.getOutputSlotByName?.(outputField);
			if (outputIdx >= 0) {
				node.setOutputData(outputIdx, responseText);
			}
			await this._signalChatResponse(node, responseText);
		}
	}

	async _handleStop({ node, chatId }) {
		const liveNode = this._resolveLiveChatNode(chatId, node);
		const entry = this.handlers.get(chatId);
		if (!liveNode || !entry?.handler?.isConnected()) {
			return;
		}
		if (entry.stopping) {
			return;
		}
		if (!entry.handler.agent?.abortRun) {
			this.app.api.chat.setState(liveNode, ChatState.ERROR, 'Stop is not available for this agent connection');
			this.app.api.chat.addMessage(liveNode, MessageRole.ERROR, 'Stop is not available for this agent connection');
			return;
		}

		entry.abortRequested = true;
		entry.stopping = true;
		entry.abortSuppressedUntil = Date.now() + 5000;
		this.app.api.chat.setState(liveNode, ChatState.STOPPING);

		try {
			await Promise.resolve()
				.then(() => entry.handler.abortRun())
				.catch((error) => {
					if (!this._isAbortLikeError(error)) {
						throw error;
					}
				});
			entry.abortRequested = false;
			entry.stopping = false;
			await this._finalizeInterruptedChat(liveNode, { signalEmptyResponse: true });
		} catch (error) {
			entry.abortRequested = false;
			entry.stopping = false;
			this.app.api.chat.setState(liveNode, ChatState.ERROR, error?.message || String(error));
			this.app.api.chat.addMessage(liveNode, MessageRole.ERROR, error?.message || String(error));
		}
	}

	/**
	 * Called when upstream node outputs change (e.g., tool_flow completes).
	 * Re-checks auto-send for all connected agent chat nodes.
	 */
	notifyInputsChanged() {
		for (const [chatId, entry] of this.handlers) {
			if (!entry?.handler?.isConnected()) continue;
			const node = this._findNodeByChatId(chatId);
			if (node) this._checkAutoSend(node);
		}
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
		const getEntry = () => this.handlers.get(chatId);

		// Track pending tool calls to render read_file results as inline previews
		const pendingTools = {};

		return {
			onEvent: (event) => {
				console.debug(`[AgentChat:${chatId}]`, event);
				// Track tool call name and args across events
				if (event.type === AGUI.EventType.TOOL_CALL_START) {
					pendingTools[event.toolCallId] = { name: event.toolCallName, args: '' };
				} else if (event.type === AGUI.EventType.TOOL_CALL_ARGS && pendingTools[event.toolCallId]) {
					pendingTools[event.toolCallId].args += event.delta || '';
				}
			},
			onRunStarted: () => { },
			onRunFinished: () => {
				const n = getNode();
				if (!n) return;
				const entry = getEntry();
				if (entry) {
					entry.stopping = false;
					entry.abortRequested = false;
				}
				if (n.chatState !== ChatState.ERROR) {
					api.setState(n, ChatState.READY);
				}
				this._updateResponseOutput(n);
			},
			onRunError: (error) => {
				const n = getNode();
				if (!n) return;
				const entry = getEntry();
				if (this._shouldSuppressAbortError(entry, error)) {
					if (entry) {
						entry.abortRequested = false;
						entry.stopping = false;
					}
					api.setState(n, ChatState.READY);
					return;
				}
				const msg = error?.message || String(error) || 'Agent error';
				api.setState(n, ChatState.ERROR, msg);
				api.addMessage(n, MessageRole.ERROR, msg);
			},
			onToolCallStart: (toolName) => {
				const n = getNode();
				if (n) api.addMessage(n, MessageRole.SYSTEM, `Tool: ${toolName}...`);
			},
			onToolCallResult: (_id, content) => {
				const n = getNode();
				if (!n) return;
				const messages = n.chatMessages || [];
				const lastPending = [...messages].reverse().find(m =>
					m.role === MessageRole.SYSTEM && m.content.startsWith('Tool:') && m.content.endsWith('...')
				);
				// Resolve tool info from tracked pending calls
				const toolInfo = pendingTools[_id] || {};
				const toolName = toolInfo.name || _id;
				let toolArgs = {};
				try { toolArgs = JSON.parse(toolInfo.args || '{}'); } catch {}

				if (lastPending) {
					const name = lastPending.content.slice(6, -3); // extract name from "Tool: NAME..."
					lastPending.content = `Tool: ${name} done`;
					api.updateLastMessage(n, lastPending.content, false);
				}
				// If tool result contains preview markers, add as a system message so they render inline
				if (content && /<<preview:\w+:.+?>>/.test(content)) {
					api.addMessage(n, MessageRole.SYSTEM, content);
				}
				// read_file result: show file content as inline collapsible preview
				else if (toolName === 'read_file' && content && toolArgs.path) {
					const fileName = toolArgs.path.split('/').pop().split('\\').pop();
					api.addMessage(n, MessageRole.SYSTEM, `<<file_content:${fileName}>>\n${content}`);
				}
			},
			onTextMessageStart: () => {
				const n = getNode();
				if (n) api.startStreaming(n);
			},
			onTextMessageEnd: () => {
				const n = getNode();
				if (!n) return;
				api.endStreaming(n);
				// Post-process /gen responses to extract workflow JSON
				if (n._pendingGeneration) {
					n._pendingGeneration = false;
					this._processGenerationResponse(n);
				}
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
			const outputField = node.chatConfig?.outputField || 'output';
			const outputIdx = node.getOutputSlotByName?.(outputField);
			if (outputIdx >= 0) {
				node.setOutputData(outputIdx, lastAssistant.content);
			}

			// Signal the engine if a workflow is running
			this._signalChatResponse(node, lastAssistant.content);
		}
	}

	async _signalChatResponse(node, response) {
		if (!this.executionId) return;
		const nodeId = node.workflowIndex;
		if (nodeId == null) return;

		try {
			await this.api.chatResponse(this.executionId, nodeId, response);
		} catch (err) {
			console.warn('[AgentChat] Failed to signal chat response:', err);
		}
	}

	// ================================================================
	// /gen command — Workflow generation via the connected agent
	// ================================================================

	async _handleGenerate(node, description) {
		const api = this.app.api.chat;

		try {
			// Connect to the same agent used for chat
			await this._ensureConnected(node);

			const entry = this.handlers.get(node.chatId);
			if (!entry?.handler?.isConnected()) {
				throw new Error('Not connected to agent');
			}

			api.setState(node, ChatState.SENDING);

			// Fetch generation prompt scoped to this agent's tools/toolkits
			const { tool_names, toolkit_names } = this._collectAgentToolNames(node);
			const genPrompt = await this._getGenerationPrompt(tool_names, toolkit_names);

			// Mark node so callbacks know to post-process the response
			node._pendingGeneration = true;

			// Send augmented message through AGUI — the agent's own
			// model, tools, memory, and knowledge are all available
			const augmented = `[Workflow Generation Contract]\n${genPrompt}\n\n[Generation Request]\nGenerate a workflow for: ${description}`;
			await entry.handler.send(augmented);

		} catch (err) {
			node._pendingGeneration = false;
			api.setState(node, ChatState.ERROR, err.message);
			api.addMessage(node, MessageRole.ERROR, `Generation failed: ${err.message}`);
		}
	}

	/**
	 * Collect tool_config and toolkit_config module names connected to
	 * the agent_config that feeds this chat node.
	 */
	_collectAgentToolNames(chatNode) {
		const tool_names = [];
		const toolkit_names = [];

		// Find the agent_config node connected to chat.config
		const configSlotIdx = chatNode.getInputSlotByName?.('config');
		if (configSlotIdx < 0) return { tool_names, toolkit_names };

		const input = chatNode.inputs?.[configSlotIdx];
		if (!input?.link) return { tool_names, toolkit_names };

		const link = this.app.graph.links[input.link];
		if (!link) return { tool_names, toolkit_names };

		const agentConfigNode = this.app.graph.getNodeById(link.origin_id);
		if (!agentConfigNode) return { tool_names, toolkit_names };

		// Walk all inputs on agent_config to find connected tool/toolkit configs
		for (let i = 0; i < (agentConfigNode.inputs?.length || 0); i++) {
			const inp = agentConfigNode.inputs[i];
			if (!inp?.link && !inp?.links) continue;

			// Handle both single-link and multi-link inputs
			const linkIds = inp.links || (inp.link ? [inp.link] : []);
			for (const lid of linkIds) {
				const lnk = this.app.graph.links[lid];
				if (!lnk) continue;
				const srcNode = this.app.graph.getNodeById(lnk.origin_id);
				if (!srcNode) continue;
				const nodeType = srcNode.constantFields?.type || srcNode.type;
				const name = srcNode.nativeInputs?.[srcNode.getInputSlotByName?.('name')]?.value
				          || srcNode.constantFields?.name;
				if (!name) continue;
				if (nodeType === 'tool_config') {
					tool_names.push(name);
				} else if (nodeType === 'toolkit_config') {
					toolkit_names.push(name);
				}
			}
		}

		return { tool_names, toolkit_names };
	}

	async _getGenerationPrompt(tool_names, toolkit_names) {
		// Build a cache key from the agent's tool/toolkit names
		const cacheKey = JSON.stringify({ tool_names, toolkit_names });
		if (this._cachedGenPromptKey === cacheKey && this._cachedGenPrompt) {
			return this._cachedGenPrompt;
		}
		const body = {};
		if (tool_names?.length)    body.tool_names    = tool_names;
		if (toolkit_names?.length) body.toolkit_names  = toolkit_names;
		const data = await this.api.generationPrompt(body);
		this._cachedGenPrompt    = data.prompt;
		this._cachedGenPromptKey = cacheKey;
		return this._cachedGenPrompt;
	}

	_processGenerationResponse(node) {
		const messages = node.chatMessages || [];
		const lastAssistant = [...messages].reverse()
			.find(m => m.role === MessageRole.ASSISTANT);
		if (!lastAssistant) return;

		const workflow = this._extractWorkflowJson(lastAssistant.content);
		if (workflow && workflow.nodes) {
			lastAssistant.workflow = workflow;
			node._lastGeneratedWorkflow = workflow;

			// Replace raw JSON in the message with a pretty-printed text preview
			const prettyJson = JSON.stringify(workflow, null, 2);
			const rawContent = lastAssistant.content || '';
			// Strip the JSON block (```json...``` or raw {…}) from the content
			let textPart = rawContent
				.replace(/```(?:json)?\s*\n?[\s\S]*?\n?```/, '')
				.trim();
			if (!textPart || textPart === rawContent) {
				// No code block found — try stripping raw JSON object
				const start = rawContent.indexOf('{');
				const end = rawContent.lastIndexOf('}');
				if (start !== -1 && end > start) {
					textPart = (rawContent.substring(0, start) + rawContent.substring(end + 1)).trim();
				}
			}
			// Build content with optional prose + file_content preview
			lastAssistant.content = (textPart ? textPart + '\n\n' : '')
				+ `<<file_content:workflow.json>>\n${prettyJson}`;

			// Force full re-render so the workflow action buttons appear
			const overlayMgr = this.app.chatManager?.overlayManager;
			if (overlayMgr) overlayMgr.updateMessages(node);
		}
	}

	_extractWorkflowJson(text) {
		if (!text) return null;
		text = text.trim();
		try { return JSON.parse(text); } catch (e) { /* not raw JSON */ }
		const blockMatch = text.match(/```(?:json)?\s*\n?([\s\S]*?)\n?```/);
		if (blockMatch) {
			try { return JSON.parse(blockMatch[1].trim()); } catch (e) { /* bad block */ }
		}
		const start = text.indexOf('{');
		const end = text.lastIndexOf('}');
		if (start !== -1 && end > start) {
			try { return JSON.parse(text.substring(start, end + 1)); } catch (e) { /* no luck */ }
		}
		return null;
	}

	// ================================================================

	disconnectNode(nodeId) {
		let chatId = nodeId;
		let entry = this.handlers.get(chatId);
		if (!entry) {
			const graphNode = this.app.graph.getNodeById?.(nodeId);
			chatId = graphNode?.chatId || nodeId;
			entry = this.handlers.get(chatId);
		}
		if (entry?.handler?.isConnected()) {
			entry.handler.disconnect();
		}
		this.handlers.delete(chatId);
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
