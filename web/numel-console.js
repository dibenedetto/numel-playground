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
		this._clearMemBtn = document.getElementById('consoleClearMemoryBtn');
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
		this._plannerToggle    = document.getElementById('consolePlannerToggle');
		this._plannerStopBtn   = document.getElementById('consolePlannerStopBtn');
		this._plannerTimeoutSel  = document.getElementById('consolePlannerTimeout');
		this._plannerTimeoutRow  = document.getElementById('consolePlannerTimeoutRow');
		this._plannerProfileSel  = document.getElementById('consolePlannerProfile');
		this._plannerProfileRow  = document.getElementById('consolePlannerProfileRow');
		this._plannerEnabled   = false;
		this._plannerBusy      = false;  // true while planner is actively processing
		this._plannerTimeoutMs = (parseInt(this._plannerTimeoutSel?.value, 10) || 120) * 1000;

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
		this._clearMemBtn?.addEventListener('click', () => this._clearMemory());
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

		// Planner mode toggle
		this._plannerToggle?.addEventListener('change', () => {
			this._togglePlanner(this._plannerToggle.checked);
			const show = this._plannerToggle.checked ? '' : 'none';
			if (this._plannerTimeoutRow) this._plannerTimeoutRow.style.display = show;
			if (this._plannerProfileRow) this._plannerProfileRow.style.display = show;
		});

		// Planner profile selector
		this._plannerProfileSel?.addEventListener('change', () => {
			const profile = this._plannerProfileSel.value;
			this.api.consolePlannerConfig({ profile }).catch(() => {});
		});

		// Planner timeout selector — always sync to backend (safe even if planner not yet enabled)
		this._plannerTimeoutSel?.addEventListener('change', () => {
			const s = parseInt(this._plannerTimeoutSel.value, 10);
			this._plannerTimeoutMs = s * 1000;
			this.api.consolePlannerConfig({ timeout_s: s }).catch(() => {});
		});

		// Planner interrupt button
		this._plannerStopBtn?.addEventListener('click', () => this._interruptPlanner());
	}

	// ── Planner lock / interrupt ─────────────────────────────────

	_setPlannerBusy(busy) {
		if (this._plannerBusy === busy) return;  // avoid redundant toggles
		this._plannerBusy = busy;
		// Show/hide interrupt button
		if (this._plannerStopBtn) this._plannerStopBtn.style.display = busy ? '' : 'none';
		// Lock/unlock console input + reset _busy flag so _send() isn't blocked
		if (!busy) this._busy = false;
		this._setInputEnabled(!busy);
		if (busy) this._input.placeholder = 'Planner is working...';
		// Disable/enable all interactive controls outside the console panel
		const selectors = '.nw-panel, .sg-toolbar, .sg-tab-bar';
		const containers = document.querySelectorAll(selectors);
		if (busy) {
			// Save previously disabled state, then disable all
			this._plannerDisabledEls = [];
			for (const c of containers) {
				for (const el of c.querySelectorAll('button, select, input, textarea')) {
					if (!el.disabled) {
						this._plannerDisabledEls.push(el);
						el.disabled = true;
					}
				}
			}
		} else {
			// Restore only elements we disabled
			for (const el of (this._plannerDisabledEls || [])) {
				el.disabled = false;
			}
			this._plannerDisabledEls = [];
		}
		// Lock/unlock the graph (blocks canvas interaction + shows lock overlay badge)
		if (window.schemaGraph) {
			if (busy) {
				window.schemaGraph.lock('Planner working\u2026', true);
			} else {
				window.schemaGraph.unlock();
			}
		}
		// Clear safety timer when unlocking
		if (!busy) clearTimeout(this._plannerBusyTimer);
	}

	// Start safety-net timeout — only called when backend confirms processing
	// (planner_thinking WebSocket message). NOT from the initial user message send.
	_startPlannerSafetyTimer() {
		clearTimeout(this._plannerBusyTimer);
		const fallbackMs = (this._plannerTimeoutMs || 120_000) + 15_000;
		this._plannerBusyTimer = setTimeout(async () => {
			if (!this._plannerBusy) return;
			this._hideThinking();
			this._setPlannerBusy(false);
			try { await this.api.consolePlannerDisable(); } catch {}
			this._plannerEnabled = false;
			if (this._plannerToggle) this._plannerToggle.checked = false;
			if (this._plannerTimeoutRow) this._plannerTimeoutRow.style.display = 'none';
			this._addMessage('error', 'Planner timed out (connection lost). Planner disabled.');
			this._updateSettingsSummary();
		}, fallbackMs);
	}

	async _interruptPlanner() {
		const ok = await this._confirm('Interrupt Planner', 'Stop the planner? The current workflow will be kept as-is.', 'Interrupt', true);
		if (!ok) return;
		try {
			await this.api.consolePlannerDisable();
			this._plannerEnabled = false;
			if (this._plannerToggle) this._plannerToggle.checked = false;
			this._setPlannerBusy(false);
			this._hideThinking();
			this._addMessage('system', 'Planner interrupted.');
			this._updateSettingsSummary();
		} catch (err) {
			this._addMessage('error', `Interrupt failed: ${err.message}`);
		}
	}

	async _togglePlanner(enabled) {
		this._setInputEnabled(false);
		this._input.placeholder = 'Reconfiguring agent...';
		try {
			if (enabled) {
				const timeoutS = (this._plannerTimeoutMs || 120_000) / 1000;
				const profile = this._plannerProfileSel?.value || 'workflow';
				const result = await this.api.consolePlannerEnable({ timeout_s: timeoutS, profile });
				this._plannerEnabled = true;
				// Re-sync timeout in case user changed it while enable was in flight
				const currentS = this._plannerTimeoutMs / 1000;
				if (currentS !== timeoutS) {
					this.api.consolePlannerConfig({ timeout_s: currentS }).catch(() => {});
				}
				this._addMessage('system', 'Planner mode enabled — autonomous workflow building active.');
				// Planner auto-adds toolkits and restarts the agent → update port and reconnect AGUI
				if (result?.port) {
					this.agentPort = result.port;
					if (this._streamingMode) {
						this._disconnectAgent();
						this._connectAgent();
					}
				}
				await this._fetchToolkits();
			} else {
				await this.api.consolePlannerDisable();
				this._plannerEnabled = false;
				this._setPlannerBusy(false);
				this._addMessage('system', 'Planner mode disabled.');
			}
			this._setInputEnabled(true);
			this._updateSettingsSummary();
		} catch (err) {
			this._addMessage('error', `Planner toggle failed: ${err.message}`);
			this._plannerToggle.checked = !enabled;
		}
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

	async _clearMemory() {
		const ok = await this._confirm('Clear Memory', 'This will erase all agent memory, sessions, and chat history. Continue?', 'Clear', true);
		if (!ok) return;
		try {
			await this.api.consoleMemoryClear();
			this._messages.querySelectorAll('.nw-console-msg').forEach(m => m.remove());
			this._hideThinking();
			this._sessionId = null;
			this._history = [];
			this._addMessage('system', 'Memory cleared.');
		} catch (err) {
			this._addMessage('error', `Failed to clear memory: ${err.message}`);
		}
	}

	_confirm(title, message, confirmText = 'OK', danger = false) {
		return new Promise((resolve) => {
			const overlay = document.createElement('div');
			overlay.className = 'sg-input-dialog-overlay';
			const dangerClass = danger ? ' sg-confirm-danger' : '';
			overlay.innerHTML = `<div class="sg-input-dialog"><div class="sg-input-dialog-header"><span class="sg-input-dialog-title">${title}</span><button class="sg-input-dialog-close">\u2715</button></div><div class="sg-input-dialog-body"><p class="sg-confirm-dialog-message">${message}</p></div><div class="sg-input-dialog-footer"><button class="sg-input-dialog-btn sg-input-dialog-cancel">Cancel</button><button class="sg-input-dialog-btn sg-input-dialog-confirm${dangerClass}">${confirmText}</button></div></div>`;
			document.body.appendChild(overlay);
			const close = (val) => { overlay.remove(); resolve(val); };
			overlay.querySelector('.sg-input-dialog-close').onclick = () => close(false);
			overlay.querySelector('.sg-input-dialog-cancel').onclick = () => close(false);
			overlay.querySelector('.sg-input-dialog-confirm').onclick = () => close(true);
		});
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
		if (this._plannerEnabled) parts.push('planner');
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
		if (!this._toolkitArgs) this._toolkitArgs = {};  // name → {key: val}
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
				// Gear icon for args configuration (skip built-in console_toolkit)
				if (!tk.builtin) {
					const gear = document.createElement('button');
					gear.className = 'nw-console-toolkit-gear';
					gear.title = 'Configure arguments';
					gear.textContent = '\u2699';
					gear.onclick = (e) => { e.stopPropagation(); this._showToolkitArgsDialog(tk.name); };
					item.appendChild(gear);
				}
				this._toolkitList.appendChild(item);
			}
			this._updateSettingsSummary();
		} catch { /* ignore — toolkits will use defaults */ }
	}

	async _showToolkitArgsDialog(toolkitName) {
		// Fetch introspection
		let params = [], className = '', description = '';
		try {
			const data = await this.api.toolkitInspect(toolkitName);
			params = data.params || [];
			className = data.class_name || '';
			description = data.description || '';
		} catch { /* no params available */ }

		const currentArgs = this._toolkitArgs[toolkitName] || {};
		const paramNames = new Set(params.map(p => p.name));
		const extraKeys = Object.keys(currentArgs).filter(k => !paramNames.has(k));

		const title = className ? `${className} Arguments` : `${toolkitName} Arguments`;
		const descHtml = description ? `<div style="color:var(--sg-text-tertiary);font-size:12px;margin-bottom:10px">${description.split('\n')[0]}</div>` : '';

		let fieldsHtml = '';
		for (const p of params) {
			const val = currentArgs[p.name] ?? p.default ?? '';
			const displayVal = typeof val === 'object' ? JSON.stringify(val) : String(val ?? '');
			const req = p.required ? '<span style="color:var(--sg-accent-red)">*</span>' : '';
			fieldsHtml += `<div style="margin-bottom:8px"><label style="font-size:12px;color:var(--sg-text-secondary)">${p.name} ${req} <span style="font-size:10px;color:var(--sg-text-tertiary);font-family:monospace">${p.type}</span></label>`;
			if (p.type === 'bool') {
				fieldsHtml += `<label style="display:flex;align-items:center;gap:6px;font-size:12px"><input type="checkbox" data-key="${p.name}" ${val === true || displayVal === 'true' || displayVal === 'True' ? 'checked' : ''}> Enabled</label>`;
			} else {
				fieldsHtml += `<input type="text" data-key="${p.name}" value="${displayVal.replace(/"/g, '&quot;')}" placeholder="${p.default != null ? String(p.default) : ''}" style="width:100%;box-sizing:border-box;background:var(--sg-canvas-bg);border:1px solid var(--sg-border-color);border-radius:4px;padding:6px 8px;color:var(--sg-text-primary);font-size:12px;font-family:monospace">`;
			}
			fieldsHtml += '</div>';
		}
		for (const key of extraKeys) {
			const val = currentArgs[key];
			const displayVal = typeof val === 'object' ? JSON.stringify(val) : String(val ?? '');
			fieldsHtml += `<div class="nw-tk-arg-extra" data-param="${key}" style="margin-bottom:8px"><label style="font-size:12px;color:var(--sg-text-secondary)">${key} <span style="font-size:10px;color:var(--sg-text-tertiary)">custom</span></label><div style="display:flex;gap:6px;align-items:center"><input type="text" data-key="${key}" value="${displayVal.replace(/"/g, '&quot;')}" style="flex:1;box-sizing:border-box;background:var(--sg-canvas-bg);border:1px solid var(--sg-border-color);border-radius:4px;padding:6px 8px;color:var(--sg-text-primary);font-size:12px;font-family:monospace"><button class="nw-tk-arg-remove" data-key="${key}" style="background:none;border:none;color:var(--sg-text-tertiary);cursor:pointer;font-size:14px;padding:4px" title="Remove">\u2715</button></div></div>`;
		}
		if (!params.length && !extraKeys.length) {
			fieldsHtml += '<div style="color:var(--sg-text-tertiary);font-style:italic;font-size:12px">No constructor parameters.</div>';
		}
		// Add custom key row
		fieldsHtml += `<div class="nw-tk-arg-add" style="display:flex;gap:6px;align-items:center;padding-top:8px;border-top:1px solid var(--sg-border-color);margin-top:8px"><input type="text" class="nw-tk-new-key" placeholder="New key..." style="flex:1;background:var(--sg-canvas-bg);border:1px solid var(--sg-border-color);border-radius:4px;padding:5px 8px;color:var(--sg-text-primary);font-size:12px"><input type="text" class="nw-tk-new-val" placeholder="Value..." style="flex:1;background:var(--sg-canvas-bg);border:1px solid var(--sg-border-color);border-radius:4px;padding:5px 8px;color:var(--sg-text-primary);font-size:12px"><button class="nw-tk-arg-add-btn" style="background:var(--sg-border-highlight,#46a2da);border:none;color:#fff;padding:5px 10px;border-radius:4px;cursor:pointer;font-size:14px;font-weight:bold" title="Add">+</button></div>`;

		const overlay = document.createElement('div');
		overlay.className = 'sg-input-dialog-overlay';
		overlay.innerHTML = `
			<div class="sg-input-dialog" style="min-width:320px;max-width:420px">
				<div class="sg-input-dialog-header">
					<span class="sg-input-dialog-title">${title}</span>
					<button class="sg-input-dialog-close">\u2715</button>
				</div>
				<div class="sg-input-dialog-body" style="max-height:50vh;overflow-y:auto">
					${descHtml}${fieldsHtml}
				</div>
				<div class="sg-input-dialog-footer">
					<button class="sg-input-dialog-btn sg-input-dialog-cancel">Cancel</button>
					<button class="sg-input-dialog-btn sg-input-dialog-confirm">Save</button>
				</div>
			</div>`;
		document.body.appendChild(overlay);

		// Wire add custom key
		const addBtn = overlay.querySelector('.nw-tk-arg-add-btn');
		if (addBtn) {
			addBtn.onclick = () => {
				const keyInput = overlay.querySelector('.nw-tk-new-key');
				const valInput = overlay.querySelector('.nw-tk-new-val');
				const key = keyInput?.value?.trim();
				if (!key) return;
				const val = valInput?.value || '';
				const addRow = overlay.querySelector('.nw-tk-arg-add');
				const newField = document.createElement('div');
				newField.className = 'nw-tk-arg-extra';
				newField.dataset.param = key;
				newField.style.marginBottom = '8px';
				newField.innerHTML = `<label style="font-size:12px;color:var(--sg-text-secondary)">${key} <span style="font-size:10px;color:var(--sg-text-tertiary)">custom</span></label><div style="display:flex;gap:6px;align-items:center"><input type="text" data-key="${key}" value="${val.replace(/"/g, '&quot;')}" style="flex:1;box-sizing:border-box;background:var(--sg-canvas-bg);border:1px solid var(--sg-border-color);border-radius:4px;padding:6px 8px;color:var(--sg-text-primary);font-size:12px;font-family:monospace"><button class="nw-tk-arg-remove" style="background:none;border:none;color:var(--sg-text-tertiary);cursor:pointer;font-size:14px;padding:4px" title="Remove">\u2715</button></div>`;
				addRow.parentElement.insertBefore(newField, addRow);
				newField.querySelector('.nw-tk-arg-remove').onclick = () => newField.remove();
				keyInput.value = '';
				valInput.value = '';
			};
		}

		// Wire remove buttons
		overlay.querySelectorAll('.nw-tk-arg-remove').forEach(btn => {
			btn.onclick = () => btn.closest('.nw-tk-arg-extra')?.remove();
		});

		const close = () => overlay.remove();
		overlay.querySelector('.sg-input-dialog-close').onclick = close;
		overlay.querySelector('.sg-input-dialog-cancel').onclick = close;
		overlay.querySelector('.sg-input-dialog-confirm').onclick = () => {
			const args = {};
			overlay.querySelectorAll('[data-key]').forEach(el => {
				const key = el.dataset.key;
				if (el.type === 'checkbox') {
					args[key] = el.checked;
				} else if (el.tagName === 'INPUT') {
					const raw = el.value.trim();
					if (raw === '') return;
					try { args[key] = JSON.parse(raw); } catch { args[key] = raw; }
				}
			});
			this._toolkitArgs[toolkitName] = args;
			this._onConfigChanged();
			close();
		};
	}

	_onConfigChanged() {
		if (!this.agentPort) return;
		// Debounce: wait 400ms after the last change before restarting
		clearTimeout(this._configChangeTimer);
		this._configChangeTimer = setTimeout(() => this._applyConfigChange(), 400);
	}

	async _applyConfigChange() {
		this._setInputEnabled(false);
		this._input.placeholder = 'Reconfiguring agent...';
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
			const toolkit_args = this._toolkitArgs || {};
			const use_backend_memory = this._memoryToggle ? this._memoryToggle.checked : true;
			const data = await this.api.consoleStart({ model_source: source, model_name: name, toolkit_names, toolkit_args, use_backend_memory });
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
					} else if (msg.type === 'planner_thinking') {
						this._setPlannerBusy(true);
						this._startPlannerSafetyTimer();  // timeout starts NOW, not when message was sent
						this._showThinking();
					} else if (msg.type === 'planner_done') {
						// Safety net: always unlock after planner turn finishes
						this._hideThinking();
						this._setPlannerBusy(false);
					} else if (msg.type === 'planner_action' || msg.type === 'planner_error' || msg.type === 'planner_paused') {
						this._hideThinking();
						this._setPlannerBusy(false);
						if (msg.content) this._addMessage('planner', msg.content);
						if (msg.type === 'planner_action' && msg.content) {
							this._speak(msg.content);
							this._plannerAutoApply(msg.content);
						}
						if (!this._open) { this._badge.style.display = ''; }
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
		this._showThinking();

		// Lock UI immediately when planner is active
		if (this._plannerEnabled) this._setPlannerBusy(true);

		// Planner always uses REST mode (AGUI doesn't reliably work with tool-heavy prompts)
		if (!this._plannerEnabled && this._streamingMode && this.handler?.isConnected()) {
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
			this._hideThinking();

			// Store session ID for conversation continuity
			if (result.session_id) this._sessionId = result.session_id;

			// Show tool calls if any
			if (result.tool_calls?.length) {
				for (const tc of result.tool_calls) {
					this._addMessage('system', `Tool: ${tc.name}`);
				}
			}

			// Show assistant response
			if (result.error) {
				this._addMessage('error', result.error);
				// Error with planner active — no events will fire, so unlock
				if (this._plannerBusy) {
					this._hideThinking();
					this._setPlannerBusy(false);
				}
			} else if (result.response) {
				this._addMessage('assistant', result.response);
				this._speak(result.response);
				// Planner: auto-apply any workflow JSON in the response
				if (this._plannerBusy) {
					const applied = await this._plannerAutoApply(result.response);
					// If no workflow JSON was found/applied, no events will fire — unlock
					if (!applied) {
						this._hideThinking();
						this._setPlannerBusy(false);
					}
				}
			} else {
				// No response and no error — unlock if planner is busy
				if (this._plannerBusy) {
					this._hideThinking();
					this._setPlannerBusy(false);
				}
			}
		} catch (err) {
			this._hideThinking();
			this._addMessage('error', `Send failed: ${err.message}`);
			// Error with planner active — unlock
			if (this._plannerBusy) {
				this._setPlannerBusy(false);
			}
		}

		this._busy = false;
		if (!this._plannerBusy) {
			this._setInputEnabled(true);
		} else {
			// Planner is still active — show thinking dots again while waiting for events
			this._showThinking();
		}
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
			console.log('[Console] AGUI runAgent on port', this.agentPort);
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
		this._hideThinking();
		this._busy = false;
		this._setInputEnabled(true);
		console.log('[Console] Run finished. History length:', this._history.length);

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

		// Planner: auto-apply workflow JSON from streaming response
		if (this._plannerEnabled && lastAssistant) {
			this._plannerAutoApply(lastAssistant);
		}
	}

	_onRunError(error) {
		this._hideThinking();
		this._busy = false;
		this._setInputEnabled(true);
		this._pendingGen = false;
		const msg = error?.message || String(error) || 'Agent error';
		console.error('[Console] Run error:', msg);
		this._addMessage('error', msg);
	}

	_onToolCallStart(name) {
		this._addMessage('system', `Tool: ${name}...`);
	}

	_onTextStart() {
		this._hideThinking();
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
		// Run still active — re-show thinking dots until _onRunFinished
		this._showThinking();
	}

	async _plannerAutoApply(text) {
		// Extract workflow JSON from assistant response and apply it.
		// Returns true if JSON was found and applied, false otherwise.
		const wf = this._extractWorkflowJson(text);
		if (!wf) return false;
		try {
			await this.api.consolePlannerApply(wf);
			this._addMessage('system', `Workflow applied (${wf.nodes?.length || 0} nodes)`);
			return true;
		} catch (err) {
			console.warn('[Console] Planner auto-apply failed:', err.message);
			return false;
		}
	}

	_extractWorkflowJson(text) {
		// Try ```json ... ``` block
		const blockMatch = text.match(/```(?:json)?\s*\n?([\s\S]*?)\n?```/);
		if (blockMatch) {
			try {
				const d = JSON.parse(blockMatch[1].trim());
				if (d.nodes) return d;
			} catch {}
		}
		// Try raw JSON
		const start = text.indexOf('{');
		const end = text.lastIndexOf('}');
		if (start !== -1 && end > start) {
			try {
				const d = JSON.parse(text.substring(start, end + 1));
				if (d.nodes) return d;
			} catch {}
		}
		return null;
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

	_showThinking() {
		if (this._thinkingEl) return;
		const el = document.createElement('div');
		el.className = 'nw-console-thinking';
		el.innerHTML = '<span></span><span></span><span></span>';
		this._thinkingEl = el;
		this._messages.appendChild(el);
		this._scrollToBottom();
	}

	_hideThinking() {
		this._thinkingEl?.remove();
		this._thinkingEl = null;
	}

	_addMessage(role, content) {
		const el = document.createElement('div');
		el.className = `nw-console-msg ${role}`;
		el.innerHTML = this._renderContent(content);
		el._rawContent = content;
		// Insert before thinking dots so they always stay at the bottom
		if (this._thinkingEl) {
			this._messages.insertBefore(el, this._thinkingEl);
		} else {
			this._messages.appendChild(el);
		}
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
