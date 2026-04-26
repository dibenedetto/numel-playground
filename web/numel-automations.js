// numel-automations.js - First-class automation surface over deployments and proactive tasks

/* global NumelAlert, NumelAssistantDeployments, NumelChannels */
/* exported NumelAutomations */

// eslint-disable-next-line no-unused-vars
const NumelAutomations = (() => {
	let _panel, _openBtn, _closeBtn, _refreshBtn, _graphBtn, _advancedDeploymentsBtn, _advancedChannelsBtn, _addAssistantBtn;
	let _summaryEl, _listEl, _deploymentSelect, _triggerMode, _triggerList, _addTriggerBtn, _taskName, _prompt, _createBtn, _createStatus;
	let _activeTab = 'tasks';
	let _deployments = [];
	let _channels = [];

	function _baseUrl() {
		const el = document.getElementById('serverUrl');
		return (el && el.value) || window.location.origin;
	}

	async function _post(path, body = {}) {
		const token = window._numelToken || localStorage.getItem('numel_token');
		const headers = { 'Content-Type': 'application/json' };
		if (token) headers.Authorization = `Bearer ${token}`;
		const resp = await fetch(`${_baseUrl()}${path}`, {
			method: 'POST',
			headers,
			body: JSON.stringify(body),
		});
		if (!resp.ok) {
			let detail = resp.statusText;
			try {
				const text = await resp.text();
				const parsed = text ? JSON.parse(text) : null;
				detail = parsed?.detail ?? parsed ?? text ?? detail;
			} catch {}
			throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail));
		}
		return resp.json();
	}

	function _esc(value) {
		const div = document.createElement('div');
		div.textContent = value == null ? '' : String(value);
		return div.innerHTML;
	}

	function _slug(value) {
		return String(value || 'task')
			.toLowerCase()
			.replace(/[^a-z0-9]+/g, '-')
			.replace(/^-+|-+$/g, '')
			.slice(0, 40) || 'task';
	}

	function _countLabel(count, singular, plural = `${singular}s`) {
		return `${count} ${count === 1 ? singular : plural}`;
	}

	function _taskSources(task = {}) {
		const rows = Array.isArray(task.trigger_sources) ? task.trigger_sources.filter(Boolean) : [];
		if (rows.length) return rows;
		return [{
			kind: task.trigger_kind || 'timer',
			trigger: task.trigger || {},
			interval_sec: Number(task.interval_sec || 0) || 0,
		}];
	}

	function _triggerLabel(task = {}) {
		const sources = _taskSources(task);
		if (sources.length > 1) return `${sources.length} sources (${task.trigger_mode || 'any'})`;
		const source = sources[0] || {};
		const kind = String(source.kind || task.trigger_kind || 'timer');
		if (kind === 'timer') {
			const seconds = Number(source.interval_sec || task.interval_sec || 0) || 0;
			if (seconds >= 3600 && seconds % 3600 === 0) return `every ${seconds / 3600}h`;
			if (seconds >= 60 && seconds % 60 === 0) return `every ${seconds / 60}m`;
			return seconds ? `every ${seconds}s` : 'manual run';
		}
		if (kind === 'webhook') return source.trigger?.endpoint || task.trigger?.endpoint || 'webhook';
		if (kind === 'channel') return source.trigger?.channel_id || task.trigger?.channel_id || 'channel source';
		if (kind === 'fswatch') return source.trigger?.path || task.trigger?.path || 'file source';
		if (kind === 'browser') return source.trigger?.device_type || task.trigger?.device_type || 'browser source';
		return kind;
	}

	function _flattenTasks() {
		const rows = [];
		for (const deployment of _deployments) {
			const tasks = Array.isArray(deployment?.proactive_tasks) ? deployment.proactive_tasks : [];
			for (const task of tasks) {
				rows.push({ deployment, task });
			}
		}
		return rows;
	}

	function _attentionRows() {
		const rows = [];
		for (const deployment of _deployments) {
			const runtime = deployment?.runtime || {};
			const pending = Number(runtime.pending_approval_count || 0) || 0;
			const failures = Array.isArray(deployment?.recent_failures) ? deployment.recent_failures : [];
			if (pending > 0) rows.push({ deployment, title: `${pending} pending approval${pending === 1 ? '' : 's'}`, detail: 'Approval needed before automation can continue.' });
			for (const failure of failures.slice(-4).reverse()) {
				rows.push({
					deployment,
					title: failure.title || failure.kind || 'Recent failure',
					detail: failure.error || failure.message || failure.status || 'Failure details unavailable.',
				});
			}
		}
		return rows;
	}

	function _renderSummary() {
		if (!_summaryEl) return;
		const taskRows = _flattenTasks();
		const enabledTasks = taskRows.filter(({ task }) => task.enabled !== false).length;
		const runningDeployments = _deployments.filter((item) => String(item?.runtime?.state || item?.status || '').toLowerCase() === 'running').length;
		const activeDeployments = _deployments.filter((item) => item?.enabled).length;
		const pendingApprovals = _deployments.reduce((sum, item) => sum + (Number(item?.runtime?.pending_approval_count || 0) || 0), 0);
		_summaryEl.innerHTML = `
			<div class="nw-assist-ops-chip"><strong>${_deployments.length}</strong> assistants</div>
			<div class="nw-assist-ops-chip"><strong>${enabledTasks}</strong> active tasks</div>
			<div class="nw-assist-ops-chip"><strong>${runningDeployments}</strong> running</div>
			<div class="nw-assist-ops-chip ${pendingApprovals ? 'is-alert' : ''}"><strong>${pendingApprovals}</strong> pending</div>
			<div class="nw-assist-ops-chip"><strong>${_channels.length}</strong> channels</div>
		`;
		const sideSummary = document.getElementById('channelSummary');
		if (sideSummary) {
			sideSummary.textContent = `${_countLabel(enabledTasks, 'active task')} · ${_countLabel(activeDeployments, 'enabled assistant')}`;
		}
	}

	function _renderDeploymentOptions() {
		if (!_deploymentSelect) return;
		const selected = _deploymentSelect.value || '';
		if (!_deployments.length) {
			_deploymentSelect.innerHTML = '<option value="">No assistant deployment</option>';
			_deploymentSelect.disabled = true;
			return;
		}
		_deploymentSelect.disabled = false;
		_deploymentSelect.innerHTML = _deployments.map((item) => {
			const label = item.name || item.id;
			return `<option value="${_esc(item.id)}" ${item.id === selected ? 'selected' : ''}>${_esc(label)}</option>`;
		}).join('');
	}

	function _normalizeTriggerKind(value) {
		const kind = String(value || 'timer').trim().toLowerCase() || 'timer';
		return ['timer', 'webhook', 'fswatch', 'channel', 'browser'].includes(kind) ? kind : 'timer';
	}

	function _normalizeTriggerMode(value) {
		const mode = String(value || 'any').trim().toLowerCase() || 'any';
		return ['any', 'all', 'race'].includes(mode) ? mode : 'any';
	}

	function _selectedDeployment() {
		const deploymentId = _deploymentSelect?.value || '';
		return _deployments.find((item) => item.id === deploymentId) || null;
	}

	function _channelOptions(selected = '') {
		const rows = Array.isArray(_channels) ? _channels : [];
		return [
			`<option value="" ${selected ? '' : 'selected'}>Any visible channel</option>`,
			...rows.map((channel) => {
				const label = channel.name || channel.id;
				const type = channel.channel_type || channel.type || 'channel';
				return `<option value="${_esc(channel.id)}" ${channel.id === selected ? 'selected' : ''}>${_esc(label)} (${_esc(type)})</option>`;
			}),
		].join('');
	}

	function _defaultTriggerSource(kind = 'timer', taskName = '', deployment = null) {
		const normalizedKind = _normalizeTriggerKind(kind);
		const slug = _slug(taskName || 'proactive-task');
		if (normalizedKind === 'webhook') {
			return { kind: 'webhook', interval_sec: 0, trigger: { endpoint: `/hook/${slug}`, methods: 'POST' } };
		}
		if (normalizedKind === 'fswatch') {
			return {
				kind: 'fswatch',
				interval_sec: 0,
				trigger: { path: '.', recursive: true, patterns: '*', events: 'created,modified,deleted,moved', debounce_ms: 100 },
			};
		}
		if (normalizedKind === 'channel') {
			const channelId = (deployment?.channel_ids || [])[0] || '';
			return { kind: 'channel', interval_sec: 0, trigger: channelId ? { channel_id: channelId } : {} };
		}
		if (normalizedKind === 'browser') {
			return { kind: 'browser', interval_sec: 0, trigger: { device_type: 'webcam', mode: 'event', interval_ms: 1000 } };
		}
		return { kind: 'timer', interval_sec: 900, trigger: { immediate: false } };
	}

	function _sourceWithDefaults(source = {}, taskName = '', deployment = null) {
		const kind = _normalizeTriggerKind(source.kind || source.trigger_kind);
		const defaults = _defaultTriggerSource(kind, taskName, deployment);
		const trigger = source.trigger && typeof source.trigger === 'object' ? source.trigger : {};
		return {
			kind,
			interval_sec: source.interval_sec == null ? defaults.interval_sec : Number(source.interval_sec || 0),
			trigger: { ...(defaults.trigger || {}), ...trigger },
		};
	}

	function _renderTriggerRow(source = {}) {
		const taskName = String(_taskName?.value || '').trim();
		const deployment = _selectedDeployment();
		const row = _sourceWithDefaults(source, taskName, deployment);
		const trigger = row.trigger || {};
		const interval = row.kind === 'timer' ? Math.max(30, Number(row.interval_sec || 900) || 900) : 0;
		const maxTriggers = trigger.max_triggers == null ? '' : String(trigger.max_triggers);
		return `
			<div class="nw-automation-trigger-card" data-trigger-row data-trigger-kind="${_esc(row.kind)}">
				<div class="nw-automation-trigger-head">
					<label class="nw-automation-field">
						<span>Kind</span>
						<select class="nw-select" data-trigger-field="kind">
							<option value="timer" ${row.kind === 'timer' ? 'selected' : ''}>Timer</option>
							<option value="webhook" ${row.kind === 'webhook' ? 'selected' : ''}>Webhook</option>
							<option value="fswatch" ${row.kind === 'fswatch' ? 'selected' : ''}>File watcher source</option>
							<option value="channel" ${row.kind === 'channel' ? 'selected' : ''}>Channel source</option>
							<option value="browser" ${row.kind === 'browser' ? 'selected' : ''}>Browser source</option>
						</select>
					</label>
					<button class="nw-btn nw-btn-sm nw-btn-secondary" type="button" data-trigger-action="remove">Remove</button>
				</div>
				<div class="nw-automation-trigger-panel" data-trigger-panel="timer">
					<div class="nw-automation-trigger-fields">
						<label class="nw-automation-field">
							<span>Every seconds</span>
							<input class="nw-input" data-trigger-field="interval_sec" type="number" min="30" step="30" value="${_esc(interval)}">
						</label>
						<label class="nw-automation-field">
							<span>Max triggers</span>
							<input class="nw-input" data-trigger-field="max_triggers" type="number" value="${_esc(maxTriggers)}" placeholder="-1 unlimited">
						</label>
					</div>
					<label class="nw-checkbox-row nw-automation-check">
						<input data-trigger-field="immediate" type="checkbox" ${trigger.immediate ? 'checked' : ''}> Fire immediately when the deployment starts
					</label>
				</div>
				<div class="nw-automation-trigger-panel" data-trigger-panel="webhook">
					<div class="nw-automation-trigger-fields">
						<label class="nw-automation-field">
							<span>Endpoint</span>
							<input class="nw-input" data-trigger-field="endpoint" value="${_esc(trigger.endpoint || `/hook/${_slug(taskName || 'proactive-task')}`)}" placeholder="/hook/daily-summary">
						</label>
						<label class="nw-automation-field">
							<span>Methods</span>
							<input class="nw-input" data-trigger-field="methods" value="${_esc(trigger.methods || 'POST')}" placeholder="POST">
						</label>
					</div>
					<label class="nw-automation-field">
						<span>Secret</span>
						<input class="nw-input" data-trigger-field="secret" value="${_esc(trigger.secret || '')}" placeholder="Optional shared secret">
					</label>
				</div>
				<div class="nw-automation-trigger-panel" data-trigger-panel="fswatch">
					<div class="nw-automation-trigger-fields">
						<label class="nw-automation-field">
							<span>Path</span>
							<input class="nw-input" data-trigger-field="path" value="${_esc(trigger.path || '.')}" placeholder="storage/inbox">
						</label>
						<label class="nw-automation-field">
							<span>Patterns</span>
							<input class="nw-input" data-trigger-field="patterns" value="${_esc(trigger.patterns || '*')}" placeholder="*.md,*.txt">
						</label>
					</div>
					<div class="nw-automation-trigger-fields">
						<label class="nw-automation-field">
							<span>Events</span>
							<input class="nw-input" data-trigger-field="events" value="${_esc(trigger.events || 'created,modified,deleted,moved')}" placeholder="created,modified">
						</label>
						<label class="nw-automation-field">
							<span>Debounce ms</span>
							<input class="nw-input" data-trigger-field="debounce_ms" type="number" min="0" step="50" value="${_esc(String(trigger.debounce_ms ?? 100))}">
						</label>
					</div>
					<label class="nw-checkbox-row nw-automation-check">
						<input data-trigger-field="recursive" type="checkbox" ${trigger.recursive === false ? '' : 'checked'}> Watch subfolders recursively
					</label>
				</div>
				<div class="nw-automation-trigger-panel" data-trigger-panel="channel">
					<div class="nw-automation-trigger-fields">
						<label class="nw-automation-field">
							<span>Trigger channel</span>
							<select class="nw-select" data-trigger-field="channel_id">${_channelOptions(String(trigger.channel_id || ''))}</select>
						</label>
						<label class="nw-automation-field">
							<span>Channel types</span>
							<input class="nw-input" data-trigger-field="channel_types" value="${_esc(trigger.channel_types || '')}" placeholder="telegram,webhook">
						</label>
					</div>
					<label class="nw-automation-field">
						<span>Sender filter</span>
						<input class="nw-input" data-trigger-field="sender_filter" value="${_esc(trigger.sender_filter || '')}" placeholder="Optional sender id or regex">
					</label>
				</div>
				<div class="nw-automation-trigger-panel" data-trigger-panel="browser">
					<div class="nw-automation-trigger-fields">
						<label class="nw-automation-field">
							<span>Device type</span>
							<input class="nw-input" data-trigger-field="device_type" value="${_esc(trigger.device_type || 'webcam')}" placeholder="webcam">
						</label>
						<label class="nw-automation-field">
							<span>Mode</span>
							<input class="nw-input" data-trigger-field="mode" value="${_esc(trigger.mode || 'event')}" placeholder="event">
						</label>
					</div>
					<div class="nw-automation-trigger-fields">
						<label class="nw-automation-field">
							<span>Interval ms</span>
							<input class="nw-input" data-trigger-field="interval_ms" type="number" min="100" step="100" value="${_esc(String(trigger.interval_ms ?? 1000))}">
						</label>
						<label class="nw-automation-field">
							<span>Resolution</span>
							<input class="nw-input" data-trigger-field="resolution" value="${_esc(trigger.resolution || '')}" placeholder="1280x720">
						</label>
					</div>
					<label class="nw-automation-field">
						<span>Audio format</span>
						<input class="nw-input" data-trigger-field="audio_format" value="${_esc(trigger.audio_format || '')}" placeholder="Optional audio format">
					</label>
				</div>
			</div>`;
	}

	function _updateTriggerRemoveState() {
		if (!_triggerList) return;
		const rows = Array.from(_triggerList.querySelectorAll('[data-trigger-row]'));
		rows.forEach((row) => {
			const removeBtn = row.querySelector('[data-trigger-action="remove"]');
			if (removeBtn) removeBtn.disabled = rows.length <= 1;
		});
	}

	function _syncTriggerRowPanels(row) {
		if (!row) return;
		const kind = _normalizeTriggerKind(row.querySelector('[data-trigger-field="kind"]')?.value);
		row.dataset.triggerKind = kind;
		row.querySelectorAll('[data-trigger-panel]').forEach((panel) => {
			panel.hidden = panel.dataset.triggerPanel !== kind;
		});
		_updateTriggerRemoveState();
	}

	function _addTriggerRow(source = {}) {
		if (!_triggerList) return;
		_triggerList.insertAdjacentHTML('beforeend', _renderTriggerRow(source));
		_syncTriggerRowPanels(_triggerList.lastElementChild);
	}

	function _mountTriggerRows(sources = null) {
		if (!_triggerList) return;
		const rows = Array.isArray(sources) && sources.length ? sources : [_defaultTriggerSource('timer', String(_taskName?.value || ''), _selectedDeployment())];
		_triggerList.innerHTML = rows.map((source) => _renderTriggerRow(source)).join('');
		_triggerList.querySelectorAll('[data-trigger-row]').forEach(_syncTriggerRowPanels);
		_updateTriggerRemoveState();
	}

	function _ensureTriggerRows() {
		if (!_triggerList || _triggerList.querySelector('[data-trigger-row]')) return;
		_mountTriggerRows();
	}

	function _triggerField(row, name) {
		return row.querySelector(`[data-trigger-field="${name}"]`);
	}

	function _collectTriggerSources(deployment, taskName) {
		_ensureTriggerRows();
		const rows = Array.from(_triggerList?.querySelectorAll('[data-trigger-row]') || []);
		return rows.map((row) => {
			const kind = _normalizeTriggerKind(_triggerField(row, 'kind')?.value);
			const trigger = {};
			let intervalSec = 0;
			if (kind === 'timer') {
				intervalSec = Math.max(30, Number(_triggerField(row, 'interval_sec')?.value || 900) || 900);
				trigger.immediate = !!_triggerField(row, 'immediate')?.checked;
				const maxTriggers = String(_triggerField(row, 'max_triggers')?.value || '').trim();
				if (maxTriggers) trigger.max_triggers = Number(maxTriggers || -1) || -1;
			} else if (kind === 'webhook') {
				const endpoint = String(_triggerField(row, 'endpoint')?.value || '').trim() || `/hook/${_slug(taskName || 'proactive-task')}`;
				const methods = String(_triggerField(row, 'methods')?.value || '').trim() || 'POST';
				const secret = String(_triggerField(row, 'secret')?.value || '').trim();
				trigger.endpoint = endpoint;
				trigger.methods = methods;
				if (secret) trigger.secret = secret;
			} else if (kind === 'fswatch') {
				trigger.path = String(_triggerField(row, 'path')?.value || '').trim() || '.';
				trigger.patterns = String(_triggerField(row, 'patterns')?.value || '').trim() || '*';
				trigger.events = String(_triggerField(row, 'events')?.value || '').trim() || 'created,modified,deleted,moved';
				trigger.recursive = !!_triggerField(row, 'recursive')?.checked;
				trigger.debounce_ms = Math.max(0, Number(_triggerField(row, 'debounce_ms')?.value || 100) || 0);
			} else if (kind === 'channel') {
				const channelId = String(_triggerField(row, 'channel_id')?.value || '').trim();
				const channelTypes = String(_triggerField(row, 'channel_types')?.value || '').trim();
				const senderFilter = String(_triggerField(row, 'sender_filter')?.value || '').trim();
				if (channelId) trigger.channel_id = channelId;
				if (channelTypes) trigger.channel_types = channelTypes;
				if (senderFilter) trigger.sender_filter = senderFilter;
			} else if (kind === 'browser') {
				trigger.device_type = String(_triggerField(row, 'device_type')?.value || '').trim() || 'webcam';
				trigger.mode = String(_triggerField(row, 'mode')?.value || '').trim() || 'event';
				trigger.interval_ms = Math.max(100, Number(_triggerField(row, 'interval_ms')?.value || 1000) || 1000);
				const resolution = String(_triggerField(row, 'resolution')?.value || '').trim();
				const audioFormat = String(_triggerField(row, 'audio_format')?.value || '').trim();
				if (resolution) trigger.resolution = resolution;
				if (audioFormat) trigger.audio_format = audioFormat;
			}
			return {
				kind,
				interval_sec: intervalSec,
				trigger: Object.keys(trigger).length ? trigger : undefined,
			};
		}).filter(Boolean);
	}

	function _setCreateStatus(message = '', kind = '') {
		if (!_createStatus) return;
		_createStatus.textContent = message;
		_createStatus.dataset.kind = kind || '';
	}

	function _taskPayloadFromComposer(deployment) {
		const prompt = String(_prompt?.value || '').trim();
		if (!deployment?.id) throw new Error('Choose an assistant deployment first.');
		if (!prompt) throw new Error('Describe what the task should do.');
		const name = String(_taskName?.value || '').trim()
			|| prompt.replace(/\s+/g, ' ').slice(0, 48)
			|| 'Proactive task';
		const triggerSources = _collectTriggerSources(deployment, name);
		if (!triggerSources.length) throw new Error('Add at least one trigger source.');
		const task = {
			id: `proactive_${Date.now().toString(36)}`,
			name,
			prompt,
			enabled: true,
			send_response: true,
			trigger_mode: _normalizeTriggerMode(_triggerMode?.value),
			trigger_sources: triggerSources,
		};
		return task;
	}

	async function _createTask() {
		if (!_createBtn) return;
		const deploymentId = _deploymentSelect?.value || '';
		const deployment = _deployments.find((item) => item.id === deploymentId);
		const original = _createBtn.textContent;
		_createBtn.disabled = true;
		_createBtn.textContent = 'Creating...';
		_setCreateStatus('', '');
		try {
			const task = _taskPayloadFromComposer(deployment);
			const full = await _post('/assistant-deployments/get', { id: deployment.id });
			const tasks = Array.isArray(full?.proactive_tasks) ? full.proactive_tasks : [];
			await _post('/assistant-deployments/update', {
				id: deployment.id,
				proactive_tasks: [...tasks, task],
			});
			if (_prompt) _prompt.value = '';
			if (_taskName) _taskName.value = '';
			_mountTriggerRows();
			_setCreateStatus('Task created.', 'ok');
			await refresh();
		} catch (err) {
			_setCreateStatus(err.message || 'Failed to create task.', 'error');
		} finally {
			_createBtn.disabled = false;
			_createBtn.textContent = original;
		}
	}

	async function _runTask(deploymentId, taskId, button) {
		const original = button?.textContent || 'Run';
		if (button) {
			button.disabled = true;
			button.textContent = 'Running...';
		}
		try {
			await _post('/assistant-deployments/run-proactive', { id: deploymentId, task_id: taskId });
			await refresh();
		} catch (err) {
			await NumelAlert('Run Proactive Task', err.message || 'Failed to run this proactive task.');
		} finally {
			if (button) {
				button.disabled = false;
				button.textContent = original;
			}
		}
	}

	async function _setDeploymentEnabled(deploymentId, enabled, button) {
		const original = button?.textContent || (enabled ? 'Start' : 'Stop');
		if (button) {
			button.disabled = true;
			button.textContent = enabled ? 'Starting...' : 'Stopping...';
		}
		try {
			await _post(enabled ? '/assistant-deployments/start' : '/assistant-deployments/stop', { id: deploymentId });
			await refresh();
		} catch (err) {
			await NumelAlert('Assistant Deployment', err.message || 'Failed to update deployment runtime.');
		} finally {
			if (button) {
				button.disabled = false;
				button.textContent = original;
			}
		}
	}

	function _renderTasks() {
		const rows = _flattenTasks();
		if (!rows.length) {
			_listEl.innerHTML = '<div class="nw-ext-empty">No proactive tasks yet.</div>';
			return;
		}
		_listEl.innerHTML = rows.map(({ deployment, task }) => `
			<div class="nw-admin-card nw-automation-card">
				<div class="nw-admin-card-header">
					<span class="nw-admin-card-title">${_esc(task.name || 'Proactive task')}</span>
					<span class="nw-ext-badge ${task.enabled === false ? 'nw-ext-badge-disabled' : 'nw-ext-badge-enabled'}">${task.enabled === false ? 'Paused' : 'Active'}</span>
				</div>
				<div class="nw-admin-card-detail">
					<div>${_esc(deployment.name || deployment.id)} · ${_esc(_triggerLabel(task))}</div>
					<div>${_esc(task.prompt || '')}</div>
				</div>
				<div class="nw-admin-card-actions">
					<button class="nw-btn nw-btn-sm nw-btn-secondary" data-action="run-task" data-deployment-id="${_esc(deployment.id)}" data-task-id="${_esc(task.id)}">Run</button>
					<button class="nw-btn nw-btn-sm nw-btn-secondary" data-action="advanced">Advanced</button>
				</div>
			</div>
		`).join('');
	}

	function _renderAssistants() {
		if (!_deployments.length) {
			_listEl.innerHTML = '<div class="nw-ext-empty">No assistant deployments yet.</div>';
			return;
		}
		_listEl.innerHTML = _deployments.map((item) => {
			const runtime = item.runtime || {};
			const running = String(runtime.state || item.status || '').toLowerCase() === 'running';
			const tasks = Array.isArray(item.proactive_tasks) ? item.proactive_tasks.length : 0;
			return `
				<div class="nw-admin-card nw-automation-card">
					<div class="nw-admin-card-header">
						<span class="nw-admin-card-title">${_esc(item.name || item.id)}</span>
						<span class="nw-ext-badge ${running ? 'nw-ext-badge-enabled' : 'nw-ext-badge-disabled'}">${running ? 'Running' : (item.enabled ? 'Enabled' : 'Stopped')}</span>
					</div>
					<div class="nw-admin-card-detail">
						<div>${_esc(item.profile || 'general')} · ${_countLabel(tasks, 'task')} · ${_countLabel((item.channel_ids || []).length, 'channel')}</div>
						<div>${_esc(item.description || item.instructions || 'No description')}</div>
					</div>
					<div class="nw-admin-card-actions">
						<button class="nw-btn nw-btn-sm ${running ? 'nw-btn-danger' : 'nw-btn-success'}" data-action="toggle-deployment" data-deployment-id="${_esc(item.id)}" data-enabled="${running ? 'false' : 'true'}">${running ? 'Stop' : 'Start'}</button>
						<button class="nw-btn nw-btn-sm nw-btn-secondary" data-action="advanced">Advanced</button>
					</div>
				</div>
			`;
		}).join('');
	}

	function _renderAttention() {
		const rows = _attentionRows();
		if (!rows.length) {
			_listEl.innerHTML = '<div class="nw-ext-empty">No pending approvals or recent failures.</div>';
			return;
		}
		_listEl.innerHTML = rows.map(({ deployment, title, detail }) => `
			<div class="nw-admin-card nw-automation-card is-alert">
				<div class="nw-admin-card-header">
					<span class="nw-admin-card-title">${_esc(title)}</span>
					<span class="nw-ext-badge nw-ext-badge-setup">${_esc(deployment.name || deployment.id)}</span>
				</div>
				<div class="nw-admin-card-detail">${_esc(detail)}</div>
				<div class="nw-admin-card-actions">
					<button class="nw-btn nw-btn-sm nw-btn-secondary" data-action="advanced">Advanced</button>
				</div>
			</div>
		`).join('');
	}

	function _renderList() {
		if (!_listEl) return;
		document.querySelectorAll('.nw-automation-tab').forEach((button) => {
			button.classList.toggle('active', button.dataset.autoTab === _activeTab);
		});
		if (_activeTab === 'assistants') return _renderAssistants();
		if (_activeTab === 'attention') return _renderAttention();
		return _renderTasks();
	}

	async function refresh() {
		if (_listEl) _listEl.innerHTML = '<div class="nw-ext-empty">Loading automations...</div>';
		try {
			const [deploymentPayload, channelPayload] = await Promise.all([
				_post('/assistant-deployments/list'),
				_post('/channels/list').catch(() => ({ channels: [] })),
			]);
			_deployments = Array.isArray(deploymentPayload?.deployments) ? deploymentPayload.deployments : [];
			_channels = Array.isArray(channelPayload) ? channelPayload : (Array.isArray(channelPayload?.channels) ? channelPayload.channels : []);
			_renderDeploymentOptions();
			if (_triggerList) {
				const currentSources = _triggerList.querySelector('[data-trigger-row]')
					? _collectTriggerSources(_selectedDeployment(), String(_taskName?.value || '').trim())
					: [];
				_mountTriggerRows(currentSources);
			}
			_renderSummary();
			_renderList();
		} catch (err) {
			if (_listEl) _listEl.innerHTML = `<div class="nw-ext-empty">Error loading automations: ${_esc(err.message)}</div>`;
		}
	}

	function open() {
		if (typeof window.closeNumelSidePanels === 'function') {
			window.closeNumelSidePanels(['automations']);
		}
		_panel?.classList.add('open');
		refresh();
	}

	function close() {
		_panel?.classList.remove('open');
	}

	function toggle() {
		if (_panel?.classList.contains('open')) close();
		else open();
	}

	function _openAdvancedDeployments() {
		close();
		NumelAssistantDeployments?.open?.();
	}

	function _openAdvancedChannels() {
		close();
		NumelChannels?.open?.();
	}

	function _bindListActions(event) {
		const button = event.target.closest('[data-action]');
		if (!button) return;
		const action = button.dataset.action;
		if (action === 'advanced') return _openAdvancedDeployments();
		if (action === 'run-task') return void _runTask(button.dataset.deploymentId, button.dataset.taskId, button);
		if (action === 'toggle-deployment') return void _setDeploymentEnabled(button.dataset.deploymentId, button.dataset.enabled === 'true', button);
	}

	function init() {
		_panel = document.getElementById('automationPanel');
		_openBtn = document.getElementById('automationPanelBtn');
		_closeBtn = document.getElementById('automationCloseBtn');
		_refreshBtn = document.getElementById('automationRefreshBtn');
		_graphBtn = document.getElementById('automationNetworkGraphBtn');
		_advancedDeploymentsBtn = document.getElementById('automationAdvancedDeploymentsBtn');
		_advancedChannelsBtn = document.getElementById('automationAdvancedChannelsBtn');
		_addAssistantBtn = document.getElementById('automationAddAssistantBtn');
		_summaryEl = document.getElementById('automationSummary');
		_listEl = document.getElementById('automationList');
		_deploymentSelect = document.getElementById('automationDeploymentSelect');
		_triggerMode = document.getElementById('automationTriggerMode');
		_triggerList = document.getElementById('automationTriggerList');
		_addTriggerBtn = document.getElementById('automationAddTriggerBtn');
		_taskName = document.getElementById('automationTaskName');
		_prompt = document.getElementById('automationPrompt');
		_createBtn = document.getElementById('automationCreateTaskBtn');
		_createStatus = document.getElementById('automationCreateStatus');

		_openBtn?.addEventListener('click', toggle);
		_closeBtn?.addEventListener('click', close);
		_refreshBtn?.addEventListener('click', refresh);
		_graphBtn?.addEventListener('click', () => NumelAssistantDeployments?.openNetworkGraph?.());
		_advancedDeploymentsBtn?.addEventListener('click', _openAdvancedDeployments);
		_advancedChannelsBtn?.addEventListener('click', _openAdvancedChannels);
		_addAssistantBtn?.addEventListener('click', () => {
			if (typeof NumelAssistantDeployments?.openAddDeployment === 'function') NumelAssistantDeployments.openAddDeployment();
			else NumelAssistantDeployments?.open?.();
		});
		_createBtn?.addEventListener('click', () => { void _createTask(); });
		_addTriggerBtn?.addEventListener('click', () => _addTriggerRow(_defaultTriggerSource('timer', String(_taskName?.value || ''), _selectedDeployment())));
		_deploymentSelect?.addEventListener('change', () => {
			if (!_triggerList?.querySelector('[data-trigger-row]')) _mountTriggerRows();
		});
		_triggerList?.addEventListener('click', (event) => {
			const button = event.target.closest('[data-trigger-action="remove"]');
			if (!button) return;
			const rows = Array.from(_triggerList.querySelectorAll('[data-trigger-row]'));
			if (rows.length <= 1) return;
			button.closest('[data-trigger-row]')?.remove();
			_updateTriggerRemoveState();
		});
		_triggerList?.addEventListener('change', (event) => {
			const kindSelect = event.target.closest('[data-trigger-field="kind"]');
			if (!kindSelect) return;
			_syncTriggerRowPanels(kindSelect.closest('[data-trigger-row]'));
		});
		_listEl?.addEventListener('click', _bindListActions);
		document.querySelectorAll('.nw-automation-tab').forEach((button) => {
			button.addEventListener('click', () => {
				_activeTab = button.dataset.autoTab || 'tasks';
				_renderList();
			});
		});
		_mountTriggerRows();
		refresh().catch(() => {});
	}

	if (document.readyState === 'loading') {
		document.addEventListener('DOMContentLoaded', init);
	} else {
		init();
	}

	return { open, close, toggle, refresh };
})();

window.NumelAutomations = NumelAutomations;
