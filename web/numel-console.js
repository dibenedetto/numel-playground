/* ========================================================================
   NUMEL CONSOLE MANAGER
   Global AI assistant panel — slide-out chat with proactive suggestions.
   Reuses AgentHandler from numel-agent-chat.js for AGUI protocol.
   Features: model selection, session memory, /gen command.
   ======================================================================== */

console.log('[Numel] Loading console manager...');

class AgentConsoleManager {
	constructor(serverUrl, syncWorkflowFn, api) {
		this.serverUrl      = serverUrl;
		this.syncWorkflow   = syncWorkflowFn;
		this.api            = api;  // NumelAPI instance
		this.handler        = null;
		this.agentPort      = null;
		this.proactiveWs    = null;
		this._open          = false;
		this._streaming     = false;
		this._pendingSuggestions = [];
		this._history       = [];    // accumulated AGUI messages for session memory
		this._pendingGen    = false; // tracks /gen command in flight

		this._panel       = document.getElementById('consolePanel');
		this._messages    = document.getElementById('consoleMessages');
		this._input       = document.getElementById('consoleInput');
		this._sendBtn     = document.getElementById('consoleSendBtn');
		this._closeBtn    = document.getElementById('consoleCloseBtn');
		this._fab         = document.getElementById('consoleToggleBtn');
		this._badge       = document.getElementById('consoleBadge');
		this._status      = document.getElementById('consoleStatus');
		this._modelSelect  = document.getElementById('consoleModelSelect');
		this._toolkitList  = document.getElementById('consoleToolkitList');

		this._setupUI();
		this._fetchToolkits();
		this._setInputEnabled(false);
	}

	// ── UI Wiring ────────────────────────────────────────────────

	_setupUI() {
		this._fab.addEventListener('click', () => this.toggle());
		this._closeBtn.addEventListener('click', () => this.close());
		this._sendBtn.addEventListener('click', () => this._send());
		this._input.addEventListener('keydown', (e) => {
			if (e.key === 'Enter' && !e.shiftKey) {
				e.preventDefault();
				this._send();
			}
		});
		// Auto-resize textarea
		this._input.addEventListener('input', () => {
			this._input.style.height = 'auto';
			this._input.style.height = Math.min(this._input.scrollHeight, 120) + 'px';
		});
		// Model selector change → restart agent
		this._modelSelect.addEventListener('change', () => this._onConfigChanged());
	}

	// ── Toggle / Open / Close ────────────────────────────────────

	toggle() {
		if (this._open) this.close();
		else this.open();
	}

	async open() {
		if (this._open) return;
		this._open = true;
		this._panel.classList.add('open');
		this._badge.style.display = 'none';
		this._input.focus();

		// Show any pending suggestions
		for (const s of this._pendingSuggestions) {
			this._addMessage('suggestion', s);
		}
		this._pendingSuggestions = [];

		// Start agent if not already running
		if (!this.agentPort) {
			await this._startAgent();
		}
	}

	close() {
		if (!this._open) return;
		this._open = false;
		this._panel.classList.remove('open');
	}

	destroy() {
		this.close();
		this._disconnectAgent();
		this._disconnectProactive();
		this.agentPort = null;
		this._history = [];
		this._setInputEnabled(false);
	}

	// ── Configuration (Model + Toolkits) ─────────────────────────

	_getSelectedModel() {
		const val = this._modelSelect.value; // "ollama:mistral"
		const [source, ...rest] = val.split(':');
		return { source, name: rest.join(':') };
	}

	_getSelectedToolkits() {
		const checks = this._toolkitList.querySelectorAll('input[type="checkbox"]:checked');
		return [...checks].map(cb => cb.value);
	}

	async _fetchToolkits() {
		try {
			const toolkits = await this.api.consoleToolkits();
			this._toolkitList.innerHTML = '';
			for (const tk of toolkits) {
				const item = document.createElement('div');
				item.className = 'nw-console-toolkit-item' + (tk.builtin ? ' builtin' : '');
				const id = `console-tk-${tk.name}`;
				const cb = document.createElement('input');
				cb.type = 'checkbox';
				cb.id = id;
				cb.value = tk.name;
				cb.checked = tk.enabled || tk.builtin;
				if (tk.builtin) cb.disabled = true;
				else cb.addEventListener('change', () => this._onConfigChanged());
				const lbl = document.createElement('label');
				lbl.htmlFor = id;
				lbl.textContent = tk.name.replace(/_/g, ' ').replace(' toolkit', '');
				lbl.title = tk.description || tk.name;
				item.appendChild(cb);
				item.appendChild(lbl);
				this._toolkitList.appendChild(item);
			}
		} catch { /* ignore — toolkits will use defaults */ }
	}

	async _onConfigChanged() {
		if (!this.agentPort) return;
		this._addMessage('system', 'Reconfiguring agent...');
		this._history = [];
		await this._startAgent();
	}

	// ── Agent Lifecycle ──────────────────────────────────────────

	async _startAgent() {
		this._setStatus('Starting...');
		this._setInputEnabled(false);
		try {
			const { source, name } = this._getSelectedModel();
			const toolkit_names = this._getSelectedToolkits();
			const data = await this.api.consoleStart({ model_source: source, model_name: name, toolkit_names });
			this.agentPort = data.port;

			this._connectAgent();
			this._connectProactive();
			this._setStatus(`${data.model_source}/${data.model_name}`);
			this._addMessage('system', 'Console agent connected.');
			this._setInputEnabled(true);
		} catch (err) {
			this._setStatus('Error');
			this._addMessage('error', `Failed to start agent: ${err.message}`);
			this._setInputEnabled(false);
		}
	}

	_connectAgent() {
		if (!this.agentPort) return;

		this._disconnectAgent();
		this.handler = new AgentHandler();
		const baseUrl = this.serverUrl.substring(0, this.serverUrl.lastIndexOf(':'));
		const url = `${baseUrl}:${this.agentPort}`;

		const connected = this.handler.connect(
			url,
			'Numel Assistant',
			null, // onEvent
			() => { /* onRunStarted */ },
			() => { this._onRunFinished(); },
			(err) => { this._onRunError(err); },
			(name) => { this._onToolCallStart(name); },
			null, // onToolCallResult
			() => { this._onTextStart(); },
			() => { this._onTextEnd(); },
			(chunk) => { this._onTextChunk(chunk); },
		);

		if (!connected) {
			this._addMessage('error', 'Failed to connect to agent (AGUI not available).');
		}
	}

	_disconnectAgent() {
		if (this.handler) {
			this.handler.disconnect();
			this.handler = null;
		}
	}

	_connectProactive() {
		this._disconnectProactive();
		const wsUrl = this.serverUrl.replace(/^http/, 'ws') + '/ws/console';
		try {
			this.proactiveWs = new WebSocket(wsUrl);
			this.proactiveWs.onmessage = (e) => {
				try {
					const msg = JSON.parse(e.data);
					if (msg.type === 'suggestion') {
						if (this._open) {
							this._addMessage('suggestion', msg.content);
						} else {
							this._pendingSuggestions.push(msg.content);
							this._badge.style.display = '';
						}
					}
				} catch { /* ignore parse errors */ }
			};
			this.proactiveWs.onclose = () => { this.proactiveWs = null; };
		} catch {
			this.proactiveWs = null;
		}
	}

	_disconnectProactive() {
		if (this.proactiveWs) {
			this.proactiveWs.close();
			this.proactiveWs = null;
		}
	}

	// ── Sending Messages ─────────────────────────────────────────

	async _send() {
		const text = this._input.value.trim();
		if (!text || this._streaming || !this.handler?.isConnected()) return;

		this._input.value = '';
		this._input.style.height = 'auto';

		// Intercept /gen command
		const genMatch = text.match(/^\/gen\s+(.+)/s);
		if (genMatch) {
			this._addMessage('user', text);
			return this._handleGenerate(genMatch[1].trim());
		}

		this._addMessage('user', text);

		// Fetch context and prepend to the current user message
		let augmented = text;
		try {
			const ctx = await this.api.consoleContext();
			if (ctx.context) {
				augmented = `[Current workspace state]\n${ctx.context}\n\n[User message]\n${text}`;
			}
		} catch { /* proceed without context */ }

		await this._sendWithHistory(augmented);
	}

	async _sendWithHistory(content) {
		const messageId = AgentHandler._randomMessageId();
		const userMessage = { id: messageId, role: 'user', content };

		// Accumulate into session history
		this._history.push(userMessage);

		// Send full history so agent has memory of the conversation
		this.handler.agent.setMessages([...this._history]);

		this._setInputEnabled(false);
		try {
			await this.handler.agent.runAgent({});
		} catch (err) {
			this._addMessage('error', `Send failed: ${err.message}`);
		}
		this._setInputEnabled(true);
	}

	// ── /gen Command ─────────────────────────────────────────────

	async _handleGenerate(description) {
		if (!this.handler?.isConnected()) return;

		this._setStatus('Generating...');
		this._pendingGen = true;

		try {
			// Fetch the generation prompt from the main server
			const { prompt: genPrompt } = await this.api.generationPrompt();

			const augmented = `${genPrompt}\n\n---\nGenerate a workflow for: ${description}`;
			await this._sendWithHistory(augmented);
		} catch (err) {
			this._pendingGen = false;
			this._addMessage('error', `Generation failed: ${err.message}`);
			this._setStatus(`${this._getSelectedModel().source}/${this._getSelectedModel().name}`);
		}
	}

	_processGenerationResponse(content) {
		if (!content) return;

		const workflow = this._extractWorkflowJson(content);
		if (!workflow?.nodes) return;

		// Add styled action button below the message
		const btn = document.createElement('button');
		btn.className = 'nw-console-action-btn';
		const btnLabel = '<svg viewBox="0 0 24 24"><path d="M3 15v4c0 1.1.9 2 2 2h14a2 2 0 0 0 2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>Load workflow';
		btn.innerHTML = btnLabel;
		btn.addEventListener('click', async () => {
			btn.disabled = true;
			btn.textContent = 'Loading...';
			try {
				await this._loadGeneratedWorkflow(workflow);
				btn.innerHTML = btnLabel;
				btn.disabled = false;
			} catch (err) {
				btn.textContent = `Failed: ${err.message}`;
				btn.disabled = false;
			}
		});
		this._messages.appendChild(btn);
		this._scrollToBottom();
	}

	async _loadGeneratedWorkflow(workflow) {
		if (typeof window.loadAndSyncWorkflow === 'function') {
			await window.loadAndSyncWorkflow(workflow, workflow.name || 'Generated Workflow');
		} else {
			// Fallback: post to backend
			await this.api.addWorkflow(workflow);
		}
	}

	_extractWorkflowJson(text) {
		if (!text) return null;
		text = text.trim();
		try { return JSON.parse(text); } catch { /* not raw JSON */ }
		const blockMatch = text.match(/```(?:json)?\s*\n?([\s\S]*?)\n?```/);
		if (blockMatch) {
			try { return JSON.parse(blockMatch[1].trim()); } catch { /* bad block */ }
		}
		const start = text.indexOf('{');
		const end = text.lastIndexOf('}');
		if (start !== -1 && end > start) {
			try { return JSON.parse(text.substring(start, end + 1)); } catch { /* no luck */ }
		}
		return null;
	}

	// ── AGUI Callbacks ───────────────────────────────────────────

	_onRunFinished() {
		this._streaming = false;
		this._setInputEnabled(true);

		// Capture the assistant response into history for memory
		const lastAssistant = this._getLastAssistantContent();
		if (lastAssistant) {
			this._history.push({
				id: AgentHandler._randomMessageId(),
				role: 'assistant',
				content: lastAssistant,
			});
		}

		// Handle /gen response
		if (this._pendingGen) {
			this._pendingGen = false;
			const { source, name } = this._getSelectedModel();
			this._setStatus(`${source}/${name}`);
			if (lastAssistant) {
				this._processGenerationResponse(lastAssistant);
			}
		}
	}

	_getLastAssistantContent() {
		const msgs = this._messages.querySelectorAll('.nw-console-msg.assistant');
		const last = msgs[msgs.length - 1];
		return last?._streamContent || last?.textContent || null;
	}

	_onRunError(error) {
		this._streaming = false;
		this._setInputEnabled(true);
		this._pendingGen = false;
		const msg = error?.message || String(error) || 'Agent error';
		this._addMessage('error', msg);
	}

	_onToolCallStart(name) {
		this._addMessage('system', `Tool: ${name}...`);
	}

	_onTextStart() {
		this._streaming = true;
		this._setInputEnabled(false);
		const el = this._addMessage('assistant', '');
		el.classList.add('streaming');
		el._streamContent = '';
	}

	_onTextEnd() {
		const msgs = this._messages.querySelectorAll('.nw-console-msg.assistant.streaming');
		for (const m of msgs) m.classList.remove('streaming');
		this._streaming = false;
		this._setInputEnabled(true);
	}

	_onTextChunk(chunk) {
		const msgs = this._messages.querySelectorAll('.nw-console-msg.assistant.streaming');
		const last = msgs[msgs.length - 1];
		if (last) {
			last._streamContent = (last._streamContent || '') + chunk;
			last.textContent = last._streamContent;
			this._scrollToBottom();
		}
	}

	// ── Message Display ──────────────────────────────────────────

	_addMessage(role, content) {
		const el = document.createElement('div');
		el.className = `nw-console-msg ${role}`;
		el.textContent = content;
		this._messages.appendChild(el);
		this._scrollToBottom();
		return el;
	}

	_scrollToBottom() {
		this._messages.scrollTop = this._messages.scrollHeight;
	}

	_setStatus(text) {
		if (this._status) this._status.textContent = text;
	}

	_setInputEnabled(enabled) {
		this._input.disabled = !enabled;
		this._sendBtn.disabled = !enabled;
		if (enabled) {
			this._input.placeholder = 'Ask about your workflow...';
		} else {
			this._input.placeholder = 'Connecting to assistant...';
		}
	}
}

// ========================================================================
// EXPORTS
// ========================================================================

if (typeof window !== 'undefined') {
	window.AgentConsoleManager = AgentConsoleManager;
}

console.log('[Numel] Console manager loaded');
