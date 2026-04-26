// numel-automations.js - First-class automation surface over deployments and proactive tasks

/* global NumelAlert, NumelAssistantDeployments, NumelChannels */
/* exported NumelAutomations */

// eslint-disable-next-line no-unused-vars
const NumelAutomations = (() => {
	let _panel, _openBtn, _closeBtn, _refreshBtn, _graphBtn, _advancedDeploymentsBtn, _advancedChannelsBtn, _addAssistantBtn;
	let _summaryEl, _listEl, _deploymentSelect, _triggerKind, _intervalSec, _taskName, _prompt, _createBtn, _createStatus;
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
		if (kind === 'channel') return source.trigger?.channel_id || task.trigger?.channel_id || 'channel message';
		if (kind === 'fswatch') return source.trigger?.path || task.trigger?.path || 'file watcher';
		if (kind === 'browser') return source.trigger?.device_type || task.trigger?.device_type || 'browser event';
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
		if (!_deployments.length) {
			_deploymentSelect.innerHTML = '<option value="">No assistant deployment</option>';
			_deploymentSelect.disabled = true;
			return;
		}
		_deploymentSelect.disabled = false;
		_deploymentSelect.innerHTML = _deployments.map((item) => {
			const label = item.name || item.id;
			return `<option value="${_esc(item.id)}">${_esc(label)}</option>`;
		}).join('');
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
		const kind = String(_triggerKind?.value || 'timer').trim().toLowerCase() || 'timer';
		const name = String(_taskName?.value || '').trim()
			|| prompt.replace(/\s+/g, ' ').slice(0, 48)
			|| 'Proactive task';
		const interval = Math.max(30, Number(_intervalSec?.value || 900) || 900);
		const task = {
			id: `proactive_${Date.now().toString(36)}`,
			name,
			prompt,
			trigger_kind: kind,
			interval_sec: kind === 'timer' ? interval : 0,
			enabled: true,
			send_response: true,
			trigger_mode: 'any',
		};
		if (kind === 'webhook') {
			task.trigger = { endpoint: `/hook/${_slug(name)}`, methods: 'POST' };
		} else if (kind === 'fswatch') {
			task.trigger = { path: '.', recursive: true, patterns: '*', events: 'created,modified,deleted,moved' };
		} else if (kind === 'browser') {
			task.trigger = { device_type: 'webcam', mode: 'event', interval_ms: 1000 };
		} else if (kind === 'channel') {
			const channelId = (deployment.channel_ids || [])[0] || (_channels[0]?.id || '');
			if (!channelId) throw new Error('Create or bind a channel before using a channel-message trigger.');
			task.trigger = { channel_id: channelId };
		}
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
		_triggerKind = document.getElementById('automationTriggerKind');
		_intervalSec = document.getElementById('automationIntervalSec');
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
		_listEl?.addEventListener('click', _bindListActions);
		document.querySelectorAll('.nw-automation-tab').forEach((button) => {
			button.addEventListener('click', () => {
				_activeTab = button.dataset.autoTab || 'tasks';
				_renderList();
			});
		});
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
