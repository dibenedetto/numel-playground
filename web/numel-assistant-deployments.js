/* global NumelConfirm */
/* exported NumelAssistantDeployments */

// eslint-disable-next-line no-unused-vars
const NumelAssistantDeployments = (() => {
	let _panel, _closeBtn, _openBtn, _openInlineBtn, _refreshBtn, _openWorkflowBtn, _addBtn, _listEl, _summaryEl;
	let _statusFilterEl, _searchEl, _pendingOnlyEl;
	let _lastItems = [];
	const _pendingOps = new Map();
	const _filters = {
		status: 'all',
		search: '',
		pendingOnly: false,
	};

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
		let parsed = null;
		let raw = '';
		try {
			raw = await resp.text();
			parsed = raw ? JSON.parse(raw) : null;
		} catch {
			parsed = null;
		}
		const detail = (parsed?.detail ?? parsed ?? raw) || resp.statusText;
		const message = typeof detail === 'string' ? detail : JSON.stringify(detail);
		const error = new Error(`${resp.status}: ${message}`);
		error.status = resp.status;
		error.detail = detail;
		throw error;
	}
	return resp.json();
}

	function _esc(s) {
		if (s == null) return '';
		const d = document.createElement('div');
		d.textContent = String(s);
		return d.innerHTML;
	}

	function _readWorkbenchContext() {
		try {
			if (typeof window.getNumelWorkbenchContext === 'function') {
				return window.getNumelWorkbenchContext() || {};
			}
		} catch {}
		return {};
	}

	function _hasAttention(item) {
		const status = String(item?.status || '').toLowerCase();
		const runtime = item?.runtime || {};
		const failures = Array.isArray(item?.recent_failures) ? item.recent_failures : [];
		return status === 'error'
			|| status === 'partial'
			|| status === 'missing'
			|| Number(runtime.pending_approval_count || 0) > 0
			|| failures.length > 0;
	}

	function _splitCsv(value) {
		return String(value || '')
			.split(',')
			.map((item) => item.trim())
			.filter(Boolean);
	}

	function _formatTimestamp(value) {
		if (!value) return 'never';
		const date = new Date(value);
		if (Number.isNaN(date.getTime())) return String(value);
		return date.toLocaleString();
	}

	function _routingRulesToText(rules = []) {
		return (Array.isArray(rules) ? rules : []).map((rule) => {
			const name = String(rule?.name || '').trim();
			const target = String(rule?.target_deployment_id || '').trim();
			const keywords = Array.isArray(rule?.keywords) ? rule.keywords.join(', ') : '';
			return `${name ? `${name}: ` : ''}${keywords} => ${target}`;
		}).join('\n');
	}

	function _parseRoutingRules(text) {
		return String(text || '')
			.split(/\r?\n/)
			.map((line) => line.trim())
			.filter(Boolean)
			.map((line) => {
				const parts = line.split('=>');
				if (parts.length !== 2) {
					throw new Error(`Invalid routing rule "${line}". Use "keyword1, keyword2 => target_deployment_id".`);
				}
				const left = parts[0].trim();
				const right = parts[1].trim();
				let name = '';
				let keywordPart = left;
				if (left.includes(':')) {
					const named = left.split(':');
					name = named.shift().trim();
					keywordPart = named.join(':').trim();
				}
				const keywords = _splitCsv(keywordPart);
				if (!right) throw new Error(`Routing rule "${line}" is missing the target deployment ID.`);
				if (!keywords.length) throw new Error(`Routing rule "${line}" has no keywords.`);
				return { name, target_deployment_id: right, keywords, enabled: true };
			});
	}

	function _taskIntervalLabel(seconds) {
		const value = Number(seconds || 0);
		if (!Number.isFinite(value) || value <= 0) return 'manual';
		if (value % 3600 === 0) return `every ${value / 3600}h`;
		if (value % 60 === 0) return `every ${value / 60}m`;
		return `every ${value}s`;
	}

	function _formatToolArgsPreview(value) {
		if (!value || typeof value !== 'object') return '';
		try {
			const text = JSON.stringify(value);
			return text.length > 220 ? `${text.slice(0, 217)}...` : text;
		} catch {
			return '';
		}
	}

	function _proactiveTasksSummary(tasks = []) {
		const rows = Array.isArray(tasks) ? tasks : [];
		if (!rows.length) return 'No proactive tasks';
		return rows.map((task) => {
			const runtime = task?.runtime || {};
			const status = String(runtime.status || (task.enabled === false ? 'disabled' : 'stopped'));
			return `${task.name} (${_taskIntervalLabel(task.interval_sec)} · ${status})`;
		}).join(' · ');
	}

	function _renderPendingApprovals(approvals = []) {
		const rows = Array.isArray(approvals) ? approvals : [];
		if (!rows.length) return '';
		return `
			<div class="nw-assist-approval-stack">
				<div class="nw-assist-approval-title">Pending approvals</div>
				${rows.map((approval) => `
					<div class="nw-assist-approval-card">
						<div class="nw-assist-approval-meta">
							<span>${_esc(approval.task_name || 'Proactive Task')}</span>
							<span>${_esc(_formatTimestamp(approval.created_at))}</span>
						</div>
						<div class="nw-assist-approval-preview">${_esc(approval.response_text || '')}</div>
						<div class="nw-assist-approval-actions">
							<button class="nw-btn nw-btn-sm nw-btn-success" data-action="approve-approval" data-approval-id="${_esc(approval.id)}">Approve</button>
							<button class="nw-btn nw-btn-sm nw-btn-danger" data-action="reject-approval" data-approval-id="${_esc(approval.id)}">Reject</button>
						</div>
					</div>
				`).join('')}
			</div>`;
	}

	function _renderPendingToolApprovals(approvals = []) {
		const rows = Array.isArray(approvals) ? approvals : [];
		if (!rows.length) return '';
		return `
			<div class="nw-assist-approval-stack">
				<div class="nw-assist-approval-title">Pending tool approvals</div>
				${rows.map((approval) => `
					<div class="nw-assist-approval-card">
						<div class="nw-assist-approval-meta">
							<span>${_esc(approval.tool_name || 'Tool Call')}</span>
							<span>${_esc(_formatTimestamp(approval.created_at))}</span>
						</div>
						<div class="nw-assist-approval-preview">${_esc(_formatToolArgsPreview(approval.tool_args) || approval.preview || 'Awaiting operator approval before the assistant can continue.')}</div>
						<div class="nw-assist-approval-actions">
							<button class="nw-btn nw-btn-sm nw-btn-success" data-action="approve-tool-approval" data-approval-id="${_esc(approval.id)}">Approve</button>
							<button class="nw-btn nw-btn-sm nw-btn-danger" data-action="reject-tool-approval" data-approval-id="${_esc(approval.id)}">Reject</button>
						</div>
					</div>
				`).join('')}
			</div>`;
	}

	function _renderRecentActivity(items = []) {
		const rows = Array.isArray(items) ? items : [];
		if (!rows.length) {
			return '<div class="nw-assist-activity-empty">No recent activity yet.</div>';
		}
		return `
			<div class="nw-assist-activity-stack">
				${rows.slice(-5).reverse().map((item) => `
					<div class="nw-assist-activity-row ${['error', 'approval_error', 'rejected'].includes(String(item.status || '').toLowerCase()) ? 'is-error' : ''}">
						<div class="nw-assist-activity-main">
							<div class="nw-assist-activity-title">${_esc(item.title || item.kind || 'Activity')}</div>
							<div class="nw-assist-activity-detail">${_esc(item.detail || '')}</div>
							${item.preview ? `<div class="nw-assist-activity-preview">${_esc(item.preview)}</div>` : ''}
						</div>
						<div class="nw-assist-activity-meta">
							<span>${_esc(item.status || 'info')}</span>
							<span>${_esc(_formatTimestamp(item.timestamp))}</span>
						</div>
					</div>
				`).join('')}
			</div>`;
	}

	function _renderRecentFailures(items = []) {
		const rows = Array.isArray(items) ? items : [];
		if (!rows.length) return '';
		return `
			<div class="nw-assist-failure-stack">
				<div class="nw-assist-failure-title">Recent failures</div>
				${rows.slice(-3).reverse().map((item) => `
					<div class="nw-assist-failure-row">
						<div class="nw-assist-failure-row-title">${_esc(item.title || item.kind || 'Failure')}</div>
						${item.detail ? `<div class="nw-assist-failure-row-detail">${_esc(item.detail)}</div>` : ''}
						${item.preview ? `<div class="nw-assist-failure-row-preview">${_esc(item.preview)}</div>` : ''}
					</div>
				`).join('')}
			</div>`;
	}

	function _renderSummary(allItems = [], visibleItems = []) {
		if (!_summaryEl) return;
		const total = allItems.length;
		const running = allItems.filter((item) => String(item?.status || '').toLowerCase() === 'running').length;
		const approvals = allItems.reduce((count, item) => count + Number(item?.runtime?.pending_approval_count || 0), 0);
		const attention = allItems.filter((item) => _hasAttention(item)).length;
		_summaryEl.innerHTML = `
			<div class="nw-assist-ops-chip">Total <strong>${_esc(String(total))}</strong></div>
			<div class="nw-assist-ops-chip">Visible <strong>${_esc(String(visibleItems.length))}</strong></div>
			<div class="nw-assist-ops-chip">Running <strong>${_esc(String(running))}</strong></div>
			<div class="nw-assist-ops-chip ${attention ? 'is-alert' : ''}">Needs attention <strong>${_esc(String(attention))}</strong></div>
			<div class="nw-assist-ops-chip ${approvals ? 'is-alert' : ''}">Pending approvals <strong>${_esc(String(approvals))}</strong></div>
		`;
	}

	function _applyFilters(items = []) {
		const search = String(_filters.search || '').trim().toLowerCase();
		return (Array.isArray(items) ? items : []).filter((item) => {
			const status = String(item?.status || '').toLowerCase();
			if (_filters.pendingOnly && !Number(item?.runtime?.pending_approval_count || 0)) return false;
			if (_filters.status === 'needs-attention' && !_hasAttention(item)) return false;
			if (_filters.status !== 'all' && _filters.status !== 'needs-attention' && status !== _filters.status) return false;
			if (!search) return true;
			const haystack = [
				item?.name,
				item?.profile,
				item?.description,
				item?.linked_space_id,
				item?.linked_space_title,
				item?.linked_workflow_name,
				...(item?.toolkit_names || []),
				...(item?.skill_names || []),
				...(item?.channel_ids || []),
			].join(' ').toLowerCase();
			return haystack.includes(search);
		});
	}

	function _fillLinkedWorkbenchFields(dialog, context = {}) {
		const spaceIdEl = dialog.querySelector('#_assist_linked_space_id');
		const spaceTitleEl = dialog.querySelector('#_assist_linked_space_title');
		const workflowNameEl = dialog.querySelector('#_assist_linked_workflow_name');
		if (spaceIdEl) spaceIdEl.value = context.space_id || '';
		if (spaceTitleEl) spaceTitleEl.value = context.space_title || '';
		if (workflowNameEl) workflowNameEl.value = context.workflow_name || '';
	}

	function _renderProactiveTaskRow(channels, task = {}) {
		const selectedChannel = String(task.channel_id || '');
		const options = [
			'<option value="">Use first bound channel</option>',
			...(channels || []).map((channel) => `<option value="${_esc(channel.id)}" ${channel.id === selectedChannel ? 'selected' : ''}>${_esc(channel.name || channel.id)} (${_esc(channel.channel_type || 'channel')})</option>`),
		].join('');
		return `
			<div class="nw-assist-task-card" data-role="proactive-task" data-id="${_esc(task.id || '')}">
				<div class="nw-assist-task-header">
					<span>Proactive Task</span>
					<button type="button" class="nw-btn nw-btn-sm nw-btn-secondary" data-role="remove-proactive-task">Remove</button>
				</div>
				<div class="nw-assist-task-grid">
					<div>
						<label>Name</label>
						<input data-field="name" value="${_esc(task.name || '')}" placeholder="Morning Summary" autocomplete="off">
					</div>
					<div>
						<label>Interval (seconds)</label>
						<input data-field="interval_sec" type="number" min="30" step="30" value="${_esc(String(task.interval_sec || 900))}" autocomplete="off">
					</div>
				</div>
				<label>Prompt</label>
				<textarea data-field="prompt" rows="3" placeholder="Summarize the latest inbound activity and send the top items.">${_esc(task.prompt || '')}</textarea>
				<div class="nw-assist-task-grid">
					<div>
						<label>Delivery Channel</label>
						<select data-field="channel_id">${options}</select>
					</div>
					<div>
						<label>Recipient ID</label>
						<input data-field="recipient_id" value="${_esc(task.recipient_id || '')}" placeholder="Optional default recipient" autocomplete="off">
					</div>
				</div>
				<label class="nw-checkbox-row">
					<input data-field="enabled" type="checkbox" ${task.enabled === false ? '' : 'checked'}> Task enabled
				</label>
				<label class="nw-checkbox-row">
					<input data-field="send_response" type="checkbox" ${task.send_response === false ? '' : 'checked'}> Send assistant response back to the delivery channel
				</label>
			</div>`;
	}

	function _mountProactiveTaskEditor(dialog, channels, tasks = []) {
		const container = dialog.querySelector('[data-role="proactive-tasks"]');
		const addBtn = dialog.querySelector('[data-role="add-proactive-task"]');
		if (!container || !addBtn) return;
		const ensureEmptyState = () => {
			if (container.querySelector('[data-role="proactive-task"]')) return;
			container.innerHTML = '<div class="nw-ext-note">No proactive tasks yet. Add one to let this deployment run itself on a schedule.</div>';
		};
		const appendRow = (task = {}) => {
			const placeholder = container.querySelector('.nw-ext-note');
			if (placeholder) placeholder.remove();
			container.insertAdjacentHTML('beforeend', _renderProactiveTaskRow(channels, task));
		};
		container.innerHTML = '';
		(Array.isArray(tasks) ? tasks : []).forEach((task) => appendRow(task));
		ensureEmptyState();
		addBtn.onclick = () => appendRow({ interval_sec: 900, enabled: true, send_response: true });
		container.addEventListener('click', (event) => {
			const btn = event.target.closest('[data-role="remove-proactive-task"]');
			if (!btn) return;
			const row = btn.closest('[data-role="proactive-task"]');
			if (row) row.remove();
			ensureEmptyState();
		});
	}

	function _collectProactiveTasks(dialog) {
		return Array.from(dialog.querySelectorAll('[data-role="proactive-task"]')).map((row) => {
			const intervalRaw = row.querySelector('[data-field="interval_sec"]')?.value;
			return {
				id: row.dataset.id || undefined,
				name: row.querySelector('[data-field="name"]')?.value.trim(),
				prompt: row.querySelector('[data-field="prompt"]')?.value.trim(),
				interval_sec: Math.max(30, Number(intervalRaw || 0) || 0),
				channel_id: row.querySelector('[data-field="channel_id"]')?.value.trim() || '',
				recipient_id: row.querySelector('[data-field="recipient_id"]')?.value.trim() || '',
				enabled: !!row.querySelector('[data-field="enabled"]')?.checked,
				send_response: !!row.querySelector('[data-field="send_response"]')?.checked,
			};
		}).filter((task) => task.name && task.prompt);
	}

	function open() {
		if (typeof window.closeNumelSidePanels === 'function') {
			window.closeNumelSidePanels(['assistantDeployments']);
		}
		if (_panel) _panel.classList.add('open');
		refresh();
	}

	function close() {
		if (_panel) _panel.classList.remove('open');
	}

	function isOpen() {
		return !!(_panel && _panel.classList.contains('open'));
	}

	function toggle() {
		if (isOpen()) close();
		else open();
	}

	async function refresh() {
		if (!_listEl) return;
		_listEl.innerHTML = '<div style="color:var(--sg-text-tertiary);font-size:12px;">Loading...</div>';
		try {
			const data = await _post('/assistant-deployments/list');
			const items = Array.isArray(data?.deployments) ? data.deployments : [];
			_lastItems = items;
			_renderList(items);
		} catch (err) {
			_listEl.innerHTML = `<div style="color:var(--sg-accent-red);font-size:12px;">Error: ${_esc(err.message)}</div>`;
		}
	}

	async function _openNetworkInWorkbench() {
		if (typeof window.loadWorkflowFromServer !== 'function') {
			await NumelAlert('Assistant Deployment Network', 'Workbench loader is not available.');
			return;
		}
		const btn = _openWorkflowBtn;
		const originalLabel = btn?.textContent || 'Open Network In Workbench';
		if (btn) {
			btn.disabled = true;
			btn.textContent = 'Loading...';
		}
		try {
			const data = await _post('/assistant-deployments/network-workflow');
			const workflow = data?.workflow;
			const name = data?.name || 'Assistant Deployment Network';
			if (!workflow?.nodes) {
				throw new Error('The assistant deployment network is empty.');
			}
			await window.loadWorkflowFromServer(workflow, name, { source: 'assistant-deployment-network' });
			close();
		} catch (err) {
			await NumelAlert('Assistant Deployment Network', `Error: ${_esc(err.message)}`);
		} finally {
			if (btn) {
				btn.disabled = false;
				btn.textContent = originalLabel;
			}
		}
	}

	function _renderList(items) {
		_listEl.innerHTML = '';
		const visibleItems = _applyFilters(items);
		_renderSummary(items, visibleItems);
		if (!items.length) {
			_listEl.innerHTML = '<div style="color:var(--sg-text-tertiary);font-size:12px;">No assistant deployments yet. Click "+ Add Deployment" to create one.</div>';
			return;
		}
		if (!visibleItems.length) {
			_listEl.innerHTML = '<div style="color:var(--sg-text-tertiary);font-size:12px;">No deployments match the current filters.</div>';
			return;
		}
		for (const item of visibleItems) {
			const pendingAction = _pendingOps.get(item.id) || '';
			const channels = Array.isArray(item.channels) ? item.channels : [];
			const runtime = item.runtime || {};
			const handoffs = Array.isArray(item.recent_handoffs) ? item.recent_handoffs : [];
			const proactiveRuns = Array.isArray(item.recent_proactive_runs) ? item.recent_proactive_runs : [];
			const pendingApprovals = Array.isArray(item.pending_proactive_approvals) ? item.pending_proactive_approvals : [];
			const pendingToolApprovals = Array.isArray(item.pending_tool_approvals) ? item.pending_tool_approvals : [];
			const recentActivity = Array.isArray(item.recent_activity) ? item.recent_activity : [];
			const recentFailures = Array.isArray(item.recent_failures) ? item.recent_failures : [];
			const channelSummary = channels.length
				? channels.map((channel) => `${channel.name || channel.id} (${channel.status || 'unknown'})`).join(' · ')
				: 'No channels bound';
			const routingSummary = Array.isArray(item.routing_rules) && item.routing_rules.length
				? item.routing_rules.map((rule) => `${(rule.keywords || []).join(', ')} → ${rule.target_deployment_id}`).join(' · ')
				: 'No routing rules';
			const lastActivity = runtime.last_message_at ? _formatTimestamp(runtime.last_message_at) : 'No traffic yet';
			const handoffSummary = handoffs.length
				? handoffs.slice(-2).map((handoff) => `${handoff.source_deployment_id} → ${handoff.target_deployment_id} (${(handoff.matched_keywords || []).join(', ')})`).join(' · ')
				: 'No recent handoffs';
			const proactiveSummary = _proactiveTasksSummary(item.proactive_tasks || []);
			const proactiveActivity = proactiveRuns.length
				? proactiveRuns.slice(-2).map((run) => `${run.task_name} (${run.status}${run.delivered ? ', delivered' : ''})`).join(' · ')
				: 'No proactive runs yet';
			const toolSafetyLabel = item.safety?.tool_execution_mode === 'approval'
				? 'Approve tool calls before execution'
				: 'Run tool calls automatically';
			const lifecycleState = pendingAction === 'start'
				? 'starting'
				: pendingAction === 'stop'
					? 'stopping'
					: item.enabled ? 'active' : 'inactive';
			const effectiveStatus = pendingAction === 'start'
				? 'starting'
				: pendingAction === 'stop'
					? 'stopping'
					: String(item.status || 'stopped').toLowerCase();
			const isBusy = !!pendingAction;
			const workbenchSummary = item.linked_space_title || item.linked_workflow_name
				? `${item.linked_space_title || item.linked_space_id || 'Unlinked space'}${item.linked_workflow_name ? ` → ${item.linked_workflow_name}` : ''}`
				: 'Not linked to a workbench yet';
			const card = document.createElement('div');
			card.className = 'nw-admin-card';
			card.innerHTML = `
				<div class="nw-admin-card-header">
					<span class="nw-admin-card-title">${_esc(item.name || item.id)}</span>
					<div class="nw-assist-deploy-badges">
						<span class="nw-channel-status-badge nw-assist-lifecycle-badge nw-assist-lifecycle-${_esc(lifecycleState)}">${_esc(lifecycleState)}</span>
						<span class="nw-channel-status-badge nw-ch-badge-${_esc(effectiveStatus)}">${_esc(effectiveStatus)}</span>
					</div>
				</div>
				<div class="nw-admin-card-detail">
					${item.description ? `${_esc(item.description)}<br>` : ''}
					Profile: ${_esc(item.profile || 'general')}<br>
					Model: ${_esc(item.model_source || 'default')}${item.model_name ? ` / ${_esc(item.model_name)}` : ''}<br>
					Deployment: ${_esc(lifecycleState)}<br>
					Channels: ${_esc(channelSummary)}<br>
					Toolkits: ${_esc((item.toolkit_names || []).join(', ') || 'default')}<br>
					Skills: ${_esc((item.skill_names || []).join(', ') || 'active defaults')}<br>
					Workbench: ${_esc(workbenchSummary)}<br>
					Routing: ${_esc(routingSummary)}<br>
					Proactive: ${_esc(proactiveSummary)}<br>
					Safety: ${_esc(item.safety?.proactive_delivery_mode === 'approval' ? 'Approval before proactive delivery' : 'Auto proactive delivery')} · ${_esc(toolSafetyLabel)}<br>
					Last activity: ${_esc(lastActivity)}${runtime.message_count ? ` · ${_esc(String(runtime.message_count))} message(s)` : ''}<br>
					Handoffs: ${_esc(handoffSummary)}<br>
					Proactive runs: ${_esc(proactiveActivity)}${runtime.pending_approval_count ? `<br>Pending approvals: ${_esc(String(runtime.pending_approval_count))}` : ''}
				</div>
				${_renderRecentFailures(recentFailures)}
				<div class="nw-assist-activity-block">
					<div class="nw-assist-activity-block-title">Recent activity</div>
					${_renderRecentActivity(recentActivity)}
				</div>
				${_renderPendingApprovals(pendingApprovals)}
				${_renderPendingToolApprovals(pendingToolApprovals)}
				<div class="nw-admin-card-actions">
					${isBusy
						? `<button class="nw-btn nw-btn-sm ${pendingAction === 'stop' ? 'nw-btn-danger' : 'nw-btn-success'} nw-btn-busy" disabled><span class="nw-btn-spinner" aria-hidden="true"></span>${pendingAction === 'stop' ? 'Stopping...' : 'Starting...'}</button>`
						: item.enabled
							? `<button class="nw-btn nw-btn-sm nw-btn-danger" data-action="stop" data-id="${_esc(item.id)}">Stop</button>`
							: `<button class="nw-btn nw-btn-sm nw-btn-success" data-action="start" data-id="${_esc(item.id)}">Start</button>`
					}
					<button class="nw-btn nw-btn-sm nw-btn-secondary" data-action="refresh-runtime" data-id="${_esc(item.id)}">Refresh State</button>
					${Array.isArray(item.proactive_tasks) && item.proactive_tasks.length
						? `<button class="nw-btn nw-btn-sm" data-action="run-proactive" data-id="${_esc(item.id)}">Run Tasks</button>`
						: ''
					}
					${item.linked_space_id
						? `<button class="nw-btn nw-btn-sm" data-action="open-workbench" data-id="${_esc(item.id)}" data-space-id="${_esc(item.linked_space_id)}" data-workflow-name="${_esc(item.linked_workflow_name || '')}">Open Workbench</button>`
						: ''
					}
					<button class="nw-btn nw-btn-sm nw-btn-secondary" data-action="edit" data-id="${_esc(item.id)}">Edit</button>
					<button class="nw-btn nw-btn-sm nw-btn-danger" data-action="remove" data-id="${_esc(item.id)}" data-name="${_esc(item.name || item.id)}">Remove</button>
				</div>`;
			card.addEventListener('click', _onAction);
			_listEl.appendChild(card);
		}
	}

	async function _onAction(event) {
		const btn = event.target.closest('[data-action]');
		if (!btn) return;
		const deploymentId = btn.dataset.id;
		const approvalId = btn.dataset.approvalId;
		const action = btn.dataset.action;
		try {
			if (action === 'start') {
				_pendingOps.set(deploymentId, 'start');
				_renderList(_lastItems);
				await _post('/assistant-deployments/start', { id: deploymentId });
				_pendingOps.delete(deploymentId);
				await refresh();
				_tryRefreshChannels();
				return;
			}
			if (action === 'stop') {
				_pendingOps.set(deploymentId, 'stop');
				_renderList(_lastItems);
				await _post('/assistant-deployments/stop', { id: deploymentId });
				_pendingOps.delete(deploymentId);
				await refresh();
				_tryRefreshChannels();
				return;
			}
			if (action === 'edit') {
				await _showEditDialog(deploymentId);
				return;
			}
			if (action === 'run-proactive') {
				await _post('/assistant-deployments/run-proactive', { id: deploymentId });
				await refresh();
				return;
			}
			if (action === 'refresh-runtime') {
				await _post('/assistant-deployments/refresh-runtime', { id: deploymentId });
				await refresh();
				return;
			}
			if (action === 'open-workbench') {
				if (typeof window.openLinkedWorkbench === 'function') {
					const opened = await window.openLinkedWorkbench(btn.dataset.spaceId, btn.dataset.workflowName || '');
					if (opened) close();
				}
				return;
			}
			if (action === 'approve-approval') {
				await _post('/assistant-deployments/approve-proactive', { id: approvalId });
				await refresh();
				return;
			}
			if (action === 'reject-approval') {
				await _post('/assistant-deployments/reject-proactive', { id: approvalId });
				await refresh();
				return;
			}
			if (action === 'approve-tool-approval') {
				await _post('/assistant-deployments/approve-tool-call', { id: approvalId });
				await refresh();
				return;
			}
			if (action === 'reject-tool-approval') {
				await _post('/assistant-deployments/reject-tool-call', { id: approvalId });
				await refresh();
				return;
			}
			if (action === 'remove') {
				const ok = await NumelConfirm(
					'Remove Assistant Deployment',
					`Remove assistant deployment "${btn.dataset.name}"? This cannot be undone.`,
					'Remove',
					true,
				);
				if (!ok) return;
				await _post('/assistant-deployments/remove', { id: deploymentId });
				await refresh();
				_tryRefreshChannels();
			}
		} catch (err) {
			if (deploymentId) {
				_pendingOps.delete(deploymentId);
				_renderList(_lastItems);
			}
			await NumelAlert('Assistant Deployment Error', `Error: ${_esc(err.message)}`);
		}
	}

	function _tryRefreshChannels() {
		try { window.NumelChannels?.refresh?.(); } catch {}
		try { window.NumelChannels?.refreshSummary?.(); } catch {}
	}

	async function _loadChannelChoices() {
		const data = await _post('/channels/list');
		const channels = Array.isArray(data) ? data : (data.channels || []);
		return channels;
	}

	async function _loadDeploymentChoices() {
		const data = await _post('/assistant-deployments/list');
		return Array.isArray(data?.deployments) ? data.deployments : [];
	}

	function _buildChannelBindings(deployments = [], currentDeploymentId = '') {
		const bindings = new Map();
		for (const deployment of Array.isArray(deployments) ? deployments : []) {
			for (const channelId of Array.isArray(deployment?.channel_ids) ? deployment.channel_ids : []) {
				if (!channelId) continue;
				if (currentDeploymentId && deployment?.id === currentDeploymentId) continue;
				bindings.set(channelId, {
					id: deployment?.id || '',
					name: deployment?.name || deployment?.id || 'deployment',
					enabled: !!deployment?.enabled,
				});
			}
		}
		return bindings;
	}

	function _renderChannelCheckboxes(channels, selectedIds = [], deployments = [], currentDeploymentId = '') {
		if (!channels.length) {
			return '<div style="color:var(--sg-text-tertiary);font-size:12px;">No channels available yet. Create a channel first, then bind it here.</div>';
		}
		const selected = new Set(selectedIds);
		const bindings = _buildChannelBindings(deployments, currentDeploymentId);
		return channels.map((channel) => `
			<label class="nw-checkbox-row">
				<input type="checkbox" value="${_esc(channel.id)}" ${selected.has(channel.id) ? 'checked' : ''}>
				<span>${_esc(channel.name || channel.id)} <span style="color:var(--sg-text-tertiary)">(${_esc(channel.channel_type || 'channel')})</span>${
					bindings.has(channel.id)
						? ` <span style="color:var(--sg-warning);font-size:11px;">bound to ${_esc(bindings.get(channel.id)?.name || 'another deployment')}</span>`
						: ''
				}</span>
			</label>
		`).join('');
	}

	function _formatChannelConflictMessage(conflicts = []) {
		if (!Array.isArray(conflicts) || !conflicts.length) {
			return 'One or more selected channels are already bound to another assistant deployment.';
		}
		const lines = conflicts.map((item) => {
			const deploymentName = _esc(item?.existing_deployment_name || item?.existing_deployment_id || 'another deployment');
			const channelId = _esc(item?.channel_id || 'channel');
			return `Channel <strong>${channelId}</strong> is currently bound to <strong>${deploymentName}</strong>.`;
		});
		return `${lines.join('<br>')}<br><br>Do you want to unbind the existing deployment and continue?`;
	}

	async function _saveDeploymentRequest(path, payload) {
		try {
			await _post(path, payload);
			return true;
		} catch (err) {
			const detail = err?.detail;
			if (Number(err?.status) === 409 && detail?.code === 'channel_conflict' && !payload.force_rebind_channels) {
				const ok = await NumelConfirm(
					'Rebind Channel',
					_formatChannelConflictMessage(detail.conflicts || []),
					'Unbind and Continue',
					true,
				);
				if (!ok) return false;
				await _post(path, { ...payload, force_rebind_channels: true });
				return true;
			}
			throw err;
		}
	}

	function _collectDialogData(dialog) {
		const channelIds = Array.from(dialog.querySelectorAll('[data-role="channel-list"] input[type="checkbox"]:checked'))
			.map((input) => input.value);
		return {
			name: dialog.querySelector('#_assist_name').value.trim(),
			profile: dialog.querySelector('#_assist_profile').value.trim(),
			description: dialog.querySelector('#_assist_description').value.trim(),
			instructions: dialog.querySelector('#_assist_instructions').value.trim(),
			linked_space_id: dialog.querySelector('#_assist_linked_space_id').value.trim(),
			linked_space_title: dialog.querySelector('#_assist_linked_space_title').value.trim(),
			linked_workflow_name: dialog.querySelector('#_assist_linked_workflow_name').value.trim(),
			model_source: dialog.querySelector('#_assist_model_source').value.trim(),
			model_name: dialog.querySelector('#_assist_model_name').value.trim(),
			toolkit_names: _splitCsv(dialog.querySelector('#_assist_toolkits').value),
			skill_names: _splitCsv(dialog.querySelector('#_assist_skills').value),
			channel_ids: channelIds,
			routing_rules: _parseRoutingRules(dialog.querySelector('#_assist_routing').value),
			proactive_tasks: _collectProactiveTasks(dialog),
			safety: {
				proactive_delivery_mode: dialog.querySelector('#_assist_proactive_delivery_mode').value || 'auto',
				tool_execution_mode: dialog.querySelector('#_assist_tool_execution_mode').value || 'auto',
			},
			auto_start: !!dialog.querySelector('#_assist_autostart').checked,
		};
	}

	async function _showAddDialog() {
		const [channels, deployments] = await Promise.all([
			_loadChannelChoices(),
			_loadDeploymentChoices(),
		]);
		const currentWorkbench = _readWorkbenchContext();
		const deploymentHint = deployments.length
			? deployments.map((item) => `${item.id} (${item.name})`).join('\n')
			: 'No existing deployments yet.';
		_dialog('Add Assistant Deployment', `
			<label>Name</label>
			<input id="_assist_name" placeholder="Customer Support Assistant" autocomplete="off">
			<label>Profile</label>
			<input id="_assist_profile" value="general" placeholder="general" autocomplete="off">
			<label>Description</label>
			<input id="_assist_description" placeholder="Short operator-facing summary" autocomplete="off">
			<label>Instructions</label>
			<textarea id="_assist_instructions" rows="4" placeholder="Deployment-specific guidance for this assistant."></textarea>
			<label>Linked Workbench</label>
			<div class="nw-ext-note">Operator-facing link back to the space and workflow this deployment belongs to.</div>
			<div class="nw-assist-link-grid">
				<div>
					<label>Space ID</label>
					<input id="_assist_linked_space_id" value="${_esc(currentWorkbench.space_id || '')}" placeholder="Current space id" autocomplete="off">
				</div>
				<div>
					<label>Space Title</label>
					<input id="_assist_linked_space_title" value="${_esc(currentWorkbench.space_title || '')}" placeholder="Current space title" autocomplete="off">
				</div>
			</div>
			<label>Workflow Name</label>
			<input id="_assist_linked_workflow_name" value="${_esc(currentWorkbench.workflow_name || '')}" placeholder="Current workflow name" autocomplete="off">
			<button type="button" class="nw-btn nw-btn-sm nw-btn-secondary" data-role="use-current-workbench">Use Current Workbench</button>
			<label>Model Source</label>
			<select id="_assist_model_source">
				<option value="">Default</option>
				<option value="ollama">ollama</option>
				<option value="openai">openai</option>
				<option value="anthropic">anthropic</option>
			</select>
			<label>Model Name</label>
			<input id="_assist_model_name" placeholder="Leave empty to use the default model" autocomplete="off">
			<label>Toolkits (comma-separated)</label>
			<input id="_assist_toolkits" placeholder="channel_toolkit,file_toolkit" autocomplete="off">
			<label>Skills (comma-separated)</label>
			<input id="_assist_skills" placeholder="Leave empty to use active defaults" autocomplete="off">
			<label>Proactive Delivery</label>
			<select id="_assist_proactive_delivery_mode">
				<option value="auto">Send automatically</option>
				<option value="approval">Require approval before sending</option>
			</select>
			<label>Tool Execution</label>
			<select id="_assist_tool_execution_mode">
				<option value="auto">Run tool calls automatically</option>
				<option value="approval">Require approval before each tool call</option>
			</select>
			<label>Routing Rules</label>
			<textarea id="_assist_routing" rows="4" placeholder="billing,invoice => deploy_ab12cd34&#10;support triage: refund,chargeback => deploy_ef56gh78"></textarea>
			<div class="nw-ext-note"><div class="nw-ext-note-pre">Target deployment IDs for routing:
${_esc(deploymentHint)}</div></div>
			<label>Channels</label>
			<div class="nw-ext-note">A channel can be bound to only one deployment at a time. If you choose a channel already in use, Numel will ask before reassigning it.</div>
			<div data-role="channel-list">${_renderChannelCheckboxes(channels, [], deployments)}</div>
			<label>Proactive Tasks</label>
			<div class="nw-ext-note">Attach recurring jobs to this deployment. Starting or stopping the deployment pauses and resumes them.</div>
			<div data-role="proactive-tasks" class="nw-assist-task-stack"></div>
			<button type="button" class="nw-btn nw-btn-sm nw-btn-secondary" data-role="add-proactive-task">+ Add Proactive Task</button>
			<label class="nw-checkbox-row">
				<input id="_assist_autostart" type="checkbox"> Start this deployment automatically on server startup
			</label>
		`, async (overlay) => {
			const payload = _collectDialogData(overlay);
			if (!payload.name) throw new Error('Name is required');
			const saved = await _saveDeploymentRequest('/assistant-deployments/create', payload);
			if (!saved) return false;
			await refresh();
		}, (overlay) => {
			_mountProactiveTaskEditor(overlay, channels, []);
			overlay.querySelector('[data-role="use-current-workbench"]')?.addEventListener('click', () => {
				_fillLinkedWorkbenchFields(overlay, _readWorkbenchContext());
			});
		});
	}

	async function _showEditDialog(deploymentId) {
		const [deployment, channels, deployments] = await Promise.all([
			_post('/assistant-deployments/get', { id: deploymentId }),
			_loadChannelChoices(),
			_loadDeploymentChoices(),
		]);
		const deploymentHint = deployments
			.filter((item) => item.id !== deploymentId)
			.map((item) => `${item.id} (${item.name})`).join('\n') || 'No other deployments available.';
		_dialog(`Edit: ${_esc(deployment.name || deployment.id)}`, `
			<label>Name</label>
			<input id="_assist_name" value="${_esc(deployment.name || '')}" autocomplete="off">
			<label>Profile</label>
			<input id="_assist_profile" value="${_esc(deployment.profile || 'general')}" autocomplete="off">
			<label>Description</label>
			<input id="_assist_description" value="${_esc(deployment.description || '')}" autocomplete="off">
			<label>Instructions</label>
			<textarea id="_assist_instructions" rows="4">${_esc(deployment.instructions || '')}</textarea>
			<label>Linked Workbench</label>
			<div class="nw-ext-note">Operator-facing link back to the space and workflow this deployment belongs to.</div>
			<div class="nw-assist-link-grid">
				<div>
					<label>Space ID</label>
					<input id="_assist_linked_space_id" value="${_esc(deployment.linked_space_id || '')}" autocomplete="off">
				</div>
				<div>
					<label>Space Title</label>
					<input id="_assist_linked_space_title" value="${_esc(deployment.linked_space_title || '')}" autocomplete="off">
				</div>
			</div>
			<label>Workflow Name</label>
			<input id="_assist_linked_workflow_name" value="${_esc(deployment.linked_workflow_name || '')}" autocomplete="off">
			<button type="button" class="nw-btn nw-btn-sm nw-btn-secondary" data-role="use-current-workbench">Use Current Workbench</button>
			<label>Model Source</label>
			<select id="_assist_model_source">
				<option value="" ${!deployment.model_source ? 'selected' : ''}>Default</option>
				<option value="ollama" ${deployment.model_source === 'ollama' ? 'selected' : ''}>ollama</option>
				<option value="openai" ${deployment.model_source === 'openai' ? 'selected' : ''}>openai</option>
				<option value="anthropic" ${deployment.model_source === 'anthropic' ? 'selected' : ''}>anthropic</option>
			</select>
			<label>Model Name</label>
			<input id="_assist_model_name" value="${_esc(deployment.model_name || '')}" autocomplete="off">
			<label>Toolkits (comma-separated)</label>
			<input id="_assist_toolkits" value="${_esc((deployment.toolkit_names || []).join(', '))}" autocomplete="off">
			<label>Skills (comma-separated)</label>
			<input id="_assist_skills" value="${_esc((deployment.skill_names || []).join(', '))}" autocomplete="off">
			<label>Proactive Delivery</label>
			<select id="_assist_proactive_delivery_mode">
				<option value="auto" ${deployment.safety?.proactive_delivery_mode !== 'approval' ? 'selected' : ''}>Send automatically</option>
				<option value="approval" ${deployment.safety?.proactive_delivery_mode === 'approval' ? 'selected' : ''}>Require approval before sending</option>
			</select>
			<label>Tool Execution</label>
			<select id="_assist_tool_execution_mode">
				<option value="auto" ${deployment.safety?.tool_execution_mode !== 'approval' ? 'selected' : ''}>Run tool calls automatically</option>
				<option value="approval" ${deployment.safety?.tool_execution_mode === 'approval' ? 'selected' : ''}>Require approval before each tool call</option>
			</select>
			<label>Routing Rules</label>
			<textarea id="_assist_routing" rows="4">${_esc(_routingRulesToText(deployment.routing_rules || []))}</textarea>
			<div class="nw-ext-note"><div class="nw-ext-note-pre">Target deployment IDs for routing:
${_esc(deploymentHint)}</div></div>
			<label>Channels</label>
			<div class="nw-ext-note">A channel can be bound to only one deployment at a time. Choosing a channel already used elsewhere will ask before reassigning it.</div>
			<div data-role="channel-list">${_renderChannelCheckboxes(channels, deployment.channel_ids || [], deployments, deploymentId)}</div>
			<label>Proactive Tasks</label>
			<div class="nw-ext-note">Attach recurring jobs to this deployment. Starting or stopping the deployment pauses and resumes them.</div>
			<div data-role="proactive-tasks" class="nw-assist-task-stack"></div>
			<button type="button" class="nw-btn nw-btn-sm nw-btn-secondary" data-role="add-proactive-task">+ Add Proactive Task</button>
			<label class="nw-checkbox-row">
				<input id="_assist_autostart" type="checkbox" ${deployment.auto_start ? 'checked' : ''}> Start this deployment automatically on server startup
			</label>
		`, async (overlay) => {
			const payload = _collectDialogData(overlay);
			if (!payload.name) throw new Error('Name is required');
			const saved = await _saveDeploymentRequest('/assistant-deployments/update', { id: deploymentId, ...payload });
			if (!saved) return false;
			await refresh();
		}, (overlay) => {
			_mountProactiveTaskEditor(overlay, channels, deployment.proactive_tasks || []);
			overlay.querySelector('[data-role="use-current-workbench"]')?.addEventListener('click', () => {
				_fillLinkedWorkbenchFields(overlay, _readWorkbenchContext());
			});
		});
	}

	function _dialog(title, bodyHtml, onSave, onReady) {
		const overlay = document.createElement('div');
		overlay.className = 'nw-admin-dialog-overlay';
		overlay.innerHTML = `
			<div class="nw-admin-dialog">
				<h3>${title}</h3>
				${bodyHtml}
				<div class="nw-admin-dialog-btns">
					<button class="nw-btn nw-btn-sm nw-btn-secondary" data-role="cancel">Cancel</button>
					<button class="nw-btn nw-btn-sm nw-btn-success" data-role="save">Save</button>
				</div>
			</div>`;
		document.body.appendChild(overlay);
		if (typeof onReady === 'function') onReady(overlay);

		overlay.querySelector('[data-role="cancel"]').onclick = () => overlay.remove();
		overlay.querySelector('[data-role="save"]').onclick = async () => {
			try {
				const result = await onSave(overlay);
				if (result === false) return;
				overlay.remove();
				_tryRefreshChannels();
			} catch (err) {
				await NumelAlert('Assistant Deployment Error', `Error: ${_esc(err.message)}`);
			}
		};
		overlay.addEventListener('click', (event) => {
			if (event.target === overlay) overlay.remove();
		});
	}

	function init() {
		_panel = document.getElementById('assistantDeploymentPanel');
		_closeBtn = document.getElementById('assistantDeploymentCloseBtn');
		_openBtn = document.getElementById('assistantDeploymentPanelBtn');
		_openInlineBtn = document.getElementById('assistantDeploymentPanelBtnInline');
		_refreshBtn = document.getElementById('assistantDeploymentRefreshBtn');
		_openWorkflowBtn = document.getElementById('assistantDeploymentOpenWorkflowBtn');
		_addBtn = document.getElementById('assistantDeploymentAddBtn');
		_listEl = document.getElementById('assistantDeploymentList');
		_summaryEl = document.getElementById('assistantDeploymentSummary');
		_statusFilterEl = document.getElementById('assistantDeploymentStatusFilter');
		_searchEl = document.getElementById('assistantDeploymentSearch');
		_pendingOnlyEl = document.getElementById('assistantDeploymentPendingOnly');

		if (_closeBtn) _closeBtn.onclick = close;
		if (_openBtn) _openBtn.onclick = toggle;
		if (_openInlineBtn) _openInlineBtn.onclick = open;
		if (_refreshBtn) _refreshBtn.onclick = refresh;
		if (_openWorkflowBtn) _openWorkflowBtn.onclick = _openNetworkInWorkbench;
		if (_addBtn) _addBtn.onclick = _showAddDialog;
		if (_statusFilterEl) {
			_statusFilterEl.addEventListener('change', () => {
				_filters.status = _statusFilterEl.value || 'all';
				_renderList(_lastItems);
			});
		}
		if (_searchEl) {
			_searchEl.addEventListener('input', () => {
				_filters.search = _searchEl.value || '';
				_renderList(_lastItems);
			});
		}
		if (_pendingOnlyEl) {
			_pendingOnlyEl.addEventListener('change', () => {
				_filters.pendingOnly = !!_pendingOnlyEl.checked;
				_renderList(_lastItems);
			});
		}
	}

	if (document.readyState === 'loading') {
		document.addEventListener('DOMContentLoaded', init);
	} else {
		init();
	}

	return { open, close, toggle, isOpen, refresh };
})();

window.NumelAssistantDeployments = NumelAssistantDeployments;
