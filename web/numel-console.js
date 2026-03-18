/* ========================================================================
   NUMEL CONSOLE MANAGER
   Global AI assistant panel — slide-out chat with proactive suggestions.
   Two chat modes:
     - "streaming" (AGUI): Real-time token streaming via AgentHandler/AGUI protocol
     - "rest" (REST API): Uses /console/chat endpoint, no streaming but more reliable
       (avoids AGUI protocol errors with parallel tool calls)
   Features: model selection, session memory, /gen command, TTS.
   ======================================================================== */

console.log('[Numel] Loading console manager...');

class AgentConsoleManager {
	constructor(serverUrl, syncWorkflowFn, api) {
		this.serverUrl      = serverUrl;
		this.syncWorkflow   = syncWorkflowFn;
		this.api            = api;  // NumelAPI instance
		this.handler        = null;  // AgentHandler for AGUI mode
		this.agentPort      = null;
		this.proactiveWs    = null;
		this._open          = false;
		this._busy          = false;  // true while sending/streaming
		this._pendingSuggestions = [];
		this._sessionId     = null;  // server-side session ID (REST mode)
		this._history       = [];    // accumulated messages (AGUI mode)
		this._pendingGen    = false;
		this._streamingMode = true; // true = AGUI streaming (default), false = REST (reliable fallback)

		this._panel       = document.getElementById('consolePanel');
		this._messages    = document.getElementById('consoleMessages');
		this._input       = document.getElementById('consoleInput');
		this._sendBtn     = document.getElementById('consoleSendBtn');
		this._closeBtn    = document.getElementById('consoleCloseBtn');
		this._fab         = document.getElementById('consoleToggleBtn');
		this._badge       = document.getElementById('consoleBadge');
		this._status      = document.getElementById('consoleStatus');
		this._modelSelect    = document.getElementById('consoleModelSelect');
		this._toolkitList    = document.getElementById('consoleToolkitList');
		this._ttsToggle      = document.getElementById('consoleTtsToggle');
		this._ttsVoiceSelect = document.getElementById('consoleTtsVoice');
		this._streamToggle   = document.getElementById('consoleStreamToggle');
		this._memoryToggle   = document.getElementById('consoleMemoryToggle');
		this._settingsHeader = document.getElementById('consoleSettingsHeader');
		this._settingsBody   = document.getElementById('consoleSettingsBody');
		this._settingsSummary = document.getElementById('consoleSettingsSummary');
		this._ttsEnabled     = false;
		this._ttsVoice       = null;
		this._stopSpeakBtn   = document.getElementById('consoleStopSpeakBtn');
		this._showSysToggle  = document.getElementById('consoleShowSysToggle');
		this._micBtn         = document.getElementById('consoleMicBtn');
		this._sttActive      = false;
		this._recognition    = null;
		this._sttLangSelect  = document.getElementById('consoleSttLang');
		this._sttLangRow     = document.getElementById('consoleSttLangRow');
		this._autoGenToggle   = document.getElementById('consoleAutoGenToggle');
		this._autoGen         = true;
		this._autoSendToggle  = document.getElementById('consoleAutoSendToggle');
		this._autoSend        = true;

		this._setupUI();
		this._fetchToolkits();
		this._setupSTT();  // must run before _setupTTS so sttLangSelect is populated
		this._setupTTS();
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
		// Settings collapse toggle
		if (this._settingsHeader) {
			this._settingsHeader.addEventListener('click', () => {
				const open = this._settingsBody.classList.toggle('open');
				this._settingsHeader.setAttribute('aria-expanded', open ? 'true' : 'false');
				this._updateSettingsSummary();
			});
		}

		// Model selector change → restart agent
		this._modelSelect.addEventListener('change', () => {
			this._updateSettingsSummary();
			this._onConfigChanged();
		});

		// Memory toggle → restart agent
		if (this._memoryToggle) {
			this._memoryToggle.addEventListener('change', () => this._onConfigChanged());
		}

		// Streaming mode toggle
		if (this._streamToggle) {
			this._streamToggle.addEventListener('change', () => {
				this._streamingMode = this._streamToggle.checked;
				if (this._streamingMode && this.agentPort) {
					this._connectAgent();
				} else {
					this._disconnectAgent();
				}
			});
		}

		// Auto-gen toggle
		if (this._autoGenToggle) {
			this._autoGenToggle.addEventListener('change', () => {
				this._autoGen = this._autoGenToggle.checked;
				this._updateSettingsSummary();
			});
		}

		// Auto-send toggle
		if (this._autoSendToggle) {
			this._autoSendToggle.addEventListener('change', () => {
				this._autoSend = this._autoSendToggle.checked;
			});
		}

		// System messages visibility (hidden by default)
		const applyShowSys = (show) => {
			this._messages.classList.toggle('hide-system', !show);
		};
		applyShowSys(this._showSysToggle?.checked ?? false);
		this._showSysToggle?.addEventListener('change', () => applyShowSys(this._showSysToggle.checked));
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
		this._sessionId = null;
		this._history = [];
		this._setInputEnabled(false);
	}

	// ── Configuration (Model + Toolkits) ─────────────────────────

	_updateSettingsSummary() {
		if (!this._settingsSummary) return;
		// Only show summary when collapsed
		if (this._settingsBody && this._settingsBody.classList.contains('open')) {
			this._settingsSummary.textContent = '';
			return;
		}
		const val = this._modelSelect ? this._modelSelect.value : '';
		const [source, ...rest] = val.split(':');
		const modelLabel = rest.join(':') || source;
		const toolkits = this._getSelectedToolkits().filter(t => t !== 'console_toolkit');
		const memOn     = this._memoryToggle    ? this._memoryToggle.checked    : true;
		const autoGenOn = this._autoGenToggle   ? this._autoGenToggle.checked   : true;
		const parts = [modelLabel];
		if (toolkits.length) parts.push(`+${toolkits.length} toolkit${toolkits.length > 1 ? 's' : ''}`);
		if (memOn)     parts.push('mem');
		if (autoGenOn) parts.push('auto-gen');
		this._settingsSummary.textContent = parts.join(' · ');
	}

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
				else cb.addEventListener('change', () => {
					this._updateSettingsSummary();
					this._onConfigChanged();
				});
				const lbl = document.createElement('label');
				lbl.htmlFor = id;
				lbl.textContent = tk.name.replace(/_/g, ' ').replace(/\btoolkit\b/i, '').trim()
				.replace(/\b\w/g, c => c.toUpperCase());
				lbl.title = tk.description || tk.name;
				item.appendChild(cb);
				item.appendChild(lbl);
				this._toolkitList.appendChild(item);
			}
			this._updateSettingsSummary();
		} catch { /* ignore — toolkits will use defaults */ }
	}

	_onConfigChanged() {
		if (!this.agentPort) return;
		// Debounce: wait 400ms after the last change before restarting
		clearTimeout(this._configChangeTimer);
		this._configChangeTimer = setTimeout(() => this._applyConfigChange(), 400);
	}

	async _applyConfigChange() {
		this._addMessage('system', 'Reconfiguring agent...');
		this._history = [];
		this._sessionId = null;
		await this._startAgent();
	}

	// ── Agent Lifecycle ──────────────────────────────────────────

	async _startAgent() {
		this._setStatus('Starting...');
		this._setInputEnabled(false);
		try {
			const { source, name } = this._getSelectedModel();
			const toolkit_names = this._getSelectedToolkits();
			const use_backend_memory = this._memoryToggle ? this._memoryToggle.checked : true;
			const data = await this.api.consoleStart({ model_source: source, model_name: name, toolkit_names, use_backend_memory });
			this.agentPort = data.port;

			// Connect AGUI handler if streaming mode is on
			if (this._streamingMode) {
				this._connectAgent();
			}
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

	// ── AGUI Connection (streaming mode) ─────────────────────────

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
		if (!text || this._busy) return;

		this._input.value = '';
		this._input.style.height = 'auto';

		// Auto-rewrite "generate …" → /gen … when toggle is on
		let finalText = text;
		if (this._autoGen) {
			const autoGenRe = /^(?:generate|genera|générer|générez|generar|genere|generieren|generiere|genereer|генерировать|生成|生成して|생성|انشئ|إنشاء)\b[,:\s]+(.+)/is;
			const m = text.match(autoGenRe);
			if (m) finalText = `/gen ${m[1].trim()}`;
		}

		// Intercept /gen command
		const genMatch = finalText.match(/^\/gen\s+(.+)/s);
		if (genMatch) {
			this._addMessage('user', finalText);
			return this._handleGenerate(genMatch[1].trim());
		}

		this._addMessage('user', text);

		if (this._streamingMode && this.handler?.isConnected()) {
			await this._sendViaAGUI(text);
		} else {
			await this._sendViaREST(text);
		}
	}

	// ── REST mode (reliable, no streaming) ───────────────────────

	async _sendViaREST(message) {
		this._busy = true;
		this._setInputEnabled(false);

		try {
			const result = await this.api.consoleChat(message, this._sessionId);

			// Store session ID for conversation continuity
			if (result.session_id) this._sessionId = result.session_id;

			// Show tool calls if any
			if (result.tool_calls?.length) {
				for (const tc of result.tool_calls) {
					this._addMessage('system', `Tool: ${tc.name}`);
				}
			}

			// Show assistant response
			if (result.response) {
				this._addMessage('assistant', result.response);
				this._speak(result.response);
			} else if (result.error) {
				this._addMessage('error', result.error);
			}
		} catch (err) {
			this._addMessage('error', `Send failed: ${err.message}`);
		}

		this._busy = false;
		this._setInputEnabled(true);
	}

	// ── AGUI mode (streaming) ────────────────────────────────────

	async _sendViaAGUI(text) {
		// Fetch context and prepend to the user message
		let augmented = text;
		try {
			const ctx = await this.api.consoleContext();
			if (ctx.context) {
				augmented = `[Current workspace state]\n${ctx.context}\n\n[User message]\n${text}`;
			}
		} catch { /* proceed without context */ }

		const messageId = AgentHandler._randomMessageId();
		const userMessage = { id: messageId, role: 'user', content: augmented };

		this._history.push(userMessage);
		this.handler.agent.setMessages([...this._history]);

		this._setInputEnabled(false);
		try {
			await this.handler.agent.runAgent({});
		} catch (err) {
			// AGUI protocol error (e.g. parallel tool calls) → fall back to REST silently
			console.warn('[Console] AGUI error, falling back to REST:', err.message);
			this._setStatus('REST mode');
			// Remove the history entry we just added (the REST path manages its own session)
			this._history.pop();
			await this._sendViaREST(text);
		}
	}

	// ── AGUI Callbacks ───────────────────────────────────────────

	_onRunFinished() {
		this._busy = false;
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

	_onRunError(error) {
		this._busy = false;
		this._setInputEnabled(true);
		this._pendingGen = false;
		const msg = error?.message || String(error) || 'Agent error';
		this._addMessage('error', msg);
	}

	_onToolCallStart(name) {
		this._addMessage('system', `Tool: ${name}...`);
	}

	_onTextStart() {
		this._busy = true;
		this._setInputEnabled(false);
		const el = this._addMessage('assistant', '');
		el.classList.add('streaming');
		el._streamContent = '';
	}

	_onTextEnd() {
		const msgs = this._messages.querySelectorAll('.nw-console-msg.assistant.streaming');
		for (const m of msgs) {
			m.classList.remove('streaming');
			if (m._rawContent?.trim()) {
				this._speak(m._rawContent);
			} else {
				m.remove();  // drop empty assistant messages
			}
		}
		this._busy = false;
		this._setInputEnabled(true);
	}

	_onTextChunk(chunk) {
		const msgs = this._messages.querySelectorAll('.nw-console-msg.assistant.streaming');
		const last = msgs[msgs.length - 1];
		if (last) {
			last._streamContent = (last._streamContent || '') + chunk;
			last._rawContent = last._streamContent;
			last.innerHTML = this._renderContent(last._streamContent);
			this._scrollToBottom();
		}
	}

	// ── /gen Command ─────────────────────────────────────────────

	async _handleGenerate(description) {
		this._setStatus('Generating...');
		this._pendingGen = true;

		try {
			// Fetch the generation prompt from the main server
			const { prompt: genPrompt } = await this.api.generationPrompt();

			const augmented = `${genPrompt}\n\n---\nGenerate a workflow for: ${description}`;

			if (this._streamingMode && this.handler?.isConnected()) {
				await this._sendViaAGUI(augmented);
				// _onRunFinished will handle _processGenerationResponse
			} else {
				await this._sendViaREST(augmented);
				const lastContent = this._getLastAssistantContent();
				if (lastContent) {
					this._processGenerationResponse(lastContent);
				}
				this._pendingGen = false;
				const { source, name } = this._getSelectedModel();
				this._setStatus(`${source}/${name}`);
			}
		} catch (err) {
			this._pendingGen = false;
			this._addMessage('error', `Generation failed: ${err.message}`);
			const { source, name } = this._getSelectedModel();
			this._setStatus(`${source}/${name}`);
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

	_getLastAssistantContent() {
		const msgs = this._messages.querySelectorAll('.nw-console-msg.assistant');
		const last = msgs[msgs.length - 1];
		return last?._rawContent || null;
	}

	// ── Message Display ──────────────────────────────────────────

	_addMessage(role, content) {
		const el = document.createElement('div');
		el.className = `nw-console-msg ${role}`;
		el.innerHTML = this._renderContent(content);
		el._rawContent = content;
		this._messages.appendChild(el);
		this._scrollToBottom();
		return el;
	}

	_renderContent(content) {
		if (!content) return '';
		let html = content
			.replace(/&/g, '&amp;')
			.replace(/</g, '&lt;')
			.replace(/>/g, '&gt;');
		html = html.replace(/```(\w*)\n?([\s\S]*?)```/g,
			'<pre class="nw-console-code"><code>$2</code></pre>');
		html = html.replace(/`([^`]+)`/g, '<code class="nw-console-inline-code">$1</code>');
		html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
		html = html.replace(/\*([^*]+)\*/g, '<em>$1</em>');
		return html;
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
		if (this._micBtn) this._micBtn.disabled = !enabled;
		if (enabled) {
			this._input.placeholder = 'Ask about your workflow...';
		} else {
			this._input.placeholder = 'Connecting to assistant...';
		}
	}

	// ── TTS (Text-to-Speech) ─────────────────────────────────────

	_setupTTS() {
		if (!('speechSynthesis' in window)) {
			if (this._ttsToggle) this._ttsToggle.parentElement.style.display = 'none';
			return;
		}

		// Populate voice selector
		const populateVoices = () => {
			const voices = speechSynthesis.getVoices();
			if (!voices.length) return;
			this._ttsVoiceSelect.innerHTML = '';
			const preferred = ['Google', 'Microsoft', 'English'];
			const sorted = [...voices].sort((a, b) => {
				// Female voices sort before male within the same quality tier
				const aFemale = this._isFemaleVoice(a) ? 0 : 1;
				const bFemale = this._isFemaleVoice(b) ? 0 : 1;
				const aScore  = preferred.some(p => a.name.includes(p)) ? 0 : 1;
				const bScore  = preferred.some(p => b.name.includes(p)) ? 0 : 1;
				return aScore - bScore || aFemale - bFemale || a.name.localeCompare(b.name);
			});
			for (const voice of sorted) {
				const opt = document.createElement('option');
				opt.value = voice.name;
				opt.textContent = `${voice.name} (${voice.lang})`;
				this._ttsVoiceSelect.appendChild(opt);
			}
			// Match TTS voice to current STT language, fall back to English
			this._matchTTSVoiceToLang(this._sttLangSelect?.value || navigator.language || 'en-US');
		};

		speechSynthesis.onvoiceschanged = populateVoices;
		populateVoices();

		// Toggle handler
		this._ttsToggle.addEventListener('change', () => {
			this._ttsEnabled = this._ttsToggle.checked;
			this._ttsVoiceSelect.style.display = this._ttsEnabled ? '' : 'none';
		});

		this._ttsVoiceSelect.addEventListener('change', () => {
			this._ttsVoice = this._ttsVoiceSelect.value;
		});

		this._stopSpeakBtn?.addEventListener('click', () => this._stopSpeaking());
	}

	// ── STT (Speech-to-Text) ─────────────────────────────────────

	_setupSTT() {
		const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
		if (!SR || !this._micBtn) {
			if (this._micBtn) this._micBtn.style.display = 'none';
			return;
		}

		// Populate language selector
		const STT_LANGS = [
			['Auto (browser)',   navigator.language || 'en-US'],
			['English (US)',     'en-US'],
			['English (UK)',     'en-GB'],
			['French',           'fr-FR'],
			['Spanish (Spain)',  'es-ES'],
			['Spanish (LATAM)',  'es-419'],
			['German',           'de-DE'],
			['Italian',          'it-IT'],
			['Portuguese (BR)',  'pt-BR'],
			['Portuguese (PT)',  'pt-PT'],
			['Dutch',            'nl-NL'],
			['Polish',           'pl-PL'],
			['Russian',          'ru-RU'],
			['Japanese',         'ja-JP'],
			['Chinese (Simp.)',  'zh-CN'],
			['Chinese (Trad.)',  'zh-TW'],
			['Korean',           'ko-KR'],
			['Arabic',           'ar-SA'],
			['Hindi',            'hi-IN'],
			['Turkish',          'tr-TR'],
		];
		if (this._sttLangSelect) {
			this._sttLangSelect.innerHTML = '';
			const browserLang = navigator.language || 'en-US';
			let defaultSet = false;
			for (const [label, code] of STT_LANGS) {
				const opt = document.createElement('option');
				opt.value = code;
				opt.textContent = label;
				// Auto entry stores the actual browser locale as value
				if (label.startsWith('Auto')) opt.value = browserLang;
				this._sttLangSelect.appendChild(opt);
				// Pre-select the option that matches the browser language
				if (!defaultSet && code.startsWith(browserLang.split('-')[0])) {
					this._sttLangSelect.value = opt.value;
					defaultSet = true;
				}
			}
			if (this._sttLangRow) this._sttLangRow.style.display = '';
		}

		const rec = new SR();
		rec.continuous     = false;
		rec.interimResults = true;
		rec.lang           = this._sttLangSelect?.value || navigator.language || 'en-US';
		this._recognition  = rec;

		// Update lang and sync TTS voice whenever the selector changes
		if (this._sttLangSelect) {
			this._sttLangSelect.addEventListener('change', () => {
				rec.lang = this._sttLangSelect.value;
				this._matchTTSVoiceToLang(this._sttLangSelect.value);
			});
		}

		// Accumulate interim transcript in the textarea
		let _savedText = '';
		rec.onstart = () => {
			this._sttActive = true;
			_savedText = this._input.value;
			this._micBtn.classList.add('recording');
			this._micBtn.title = 'Stop recording';
		};
		rec.onresult = (e) => {
			let interim = '';
			let final   = '';
			for (const res of e.results) {
				if (res.isFinal) final   += res[0].transcript;
				else             interim += res[0].transcript;
			}
			// Show interim in grey via placeholder trick — just update value
			this._input.value = (_savedText + (final || interim)).trimStart();
			// Auto-resize
			this._input.style.height = 'auto';
			this._input.style.height = Math.min(this._input.scrollHeight, 120) + 'px';
		};
		rec.onend = () => {
			this._sttActive = false;
			this._micBtn.classList.remove('recording');
			this._micBtn.title = 'Voice input';
			if (this._input.value.trim()) {
				if (this._autoSend) {
					this._send();
				} else {
					this._input.focus();
				}
			}
		};
		rec.onerror = (e) => {
			this._sttActive = false;
			this._micBtn.classList.remove('recording');
			this._micBtn.title = 'Voice input';
			if (e.error !== 'no-speech' && e.error !== 'aborted') {
				console.warn('[STT] error:', e.error);
			}
		};

		this._micBtn.addEventListener('click', () => {
			if (this._sttActive) {
				rec.stop();
			} else {
				_savedText = this._input.value;
				rec.start();
			}
		});
	}

	_isFemaleVoice(voice) {
		const n = voice.name.toLowerCase();
		if (n.includes('female') || n.includes('woman') || n.includes('girl')) return true;
		if (n.includes(' male') || n.includes('man ') || n.includes(' boy'))   return false;
		// Well-known female voice names across browsers / OS
		const femaleNames = [
			// English
			'samantha','victoria','karen','moira','fiona','tessa','veena',
			'zira','eva','anna','susan','catherine','alice','vicki','kathy',
			'julie','emily','emma','claire','michelle','amy','jane','kate',
			'natasha','grace','olivia','ava','serena','sophie','chloe','lily',
			// Microsoft Natural/Online voices (female)
			'aria','jenny','sonia','libby','maisie','abbi','bella','hollie','leah','oliwia',
			'amelie','marie','celine',
			// Asian
			'kyoko','mei','sin-ji','sinji','yuna','haruka','heami','heera',
			// Romance
			'monica','paulina','ioana','milena',
			'laura','carmen','luciana','joana','sara','nora',
			'elsa','elisa','giovanna','carla','isabella','valentina','francesca',
			'sofia','luna','mila','clara',
			// Misc
			'lekha','kanya','damayanti','daria',
		];
		return femaleNames.some(fn => n.includes(fn));
	}

	_matchTTSVoiceToLang(langCode) {
		if (!this._ttsVoiceSelect || !('speechSynthesis' in window)) return;
		const voices = speechSynthesis.getVoices();
		if (!voices.length) return;
		const prefix = langCode.split('-')[0];

		// Build candidate lists in priority order
		const exact  = voices.filter(v => v.lang === langCode);
		const region = voices.filter(v => v.lang.startsWith(prefix + '-') || v.lang === prefix);

		// Prefer female within each tier, fall back to any
		const pickFemale = (vs) => vs.find(v => this._isFemaleVoice(v)) || vs[0] || null;
		const match = pickFemale(exact) || pickFemale(region);

		if (match) {
			this._ttsVoiceSelect.value = match.name;
			this._ttsVoice = match.name;
		}
	}

	_speak(text) {
		if (!this._ttsEnabled || !('speechSynthesis' in window)) return;
		// Strip markdown/code for cleaner speech
		let clean = text
			.replace(/```[\s\S]*?```/g, ' code block ')
			.replace(/`([^`]+)`/g, '$1')
			.replace(/\*\*([^*]+)\*\*/g, '$1')
			.replace(/\*([^*]+)\*/g, '$1')
			.replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
			.replace(/#{1,6}\s*/g, '')
			.replace(/\n+/g, '. ')
			.trim();

		if (!clean) return;

		// Cancel any ongoing speech
		speechSynthesis.cancel();

		const utterance = new SpeechSynthesisUtterance(clean);
		utterance.rate = 1.0;
		utterance.pitch = 1.0;

		// Set selected voice
		const voiceName = this._ttsVoice || this._ttsVoiceSelect?.value;
		if (voiceName) {
			const voice = speechSynthesis.getVoices().find(v => v.name === voiceName);
			if (voice) utterance.voice = voice;
		}

		utterance.onstart = () => { if (this._stopSpeakBtn) this._stopSpeakBtn.style.display = ''; };
		utterance.onend   = () => { if (this._stopSpeakBtn) this._stopSpeakBtn.style.display = 'none'; };
		utterance.onerror = () => { if (this._stopSpeakBtn) this._stopSpeakBtn.style.display = 'none'; };

		speechSynthesis.speak(utterance);
	}

	_stopSpeaking() {
		if ('speechSynthesis' in window) {
			speechSynthesis.cancel();
			if (this._stopSpeakBtn) this._stopSpeakBtn.style.display = 'none';
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
