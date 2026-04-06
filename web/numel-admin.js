// numel-admin.js — System admin panel (users, executions, stats)

/* global NumelAPI */
/* exported NumelAdmin */

// eslint-disable-next-line no-unused-vars
const NumelAdmin = (() => {

	let _panel, _closeBtn, _openBtn;
	let _tabs;

	// ── Helpers ──────────────────────────────────────────────────

	function _baseUrl() {
		const el = document.getElementById('serverUrl');
		return (el && el.value) || window.location.origin;
	}

	async function _post(path, body = {}) {
		const token = window._numelToken || localStorage.getItem('numel_token');
		const headers = { 'Content-Type': 'application/json' };
		if (token) headers['Authorization'] = `Bearer ${token}`;
		const resp = await fetch(`${_baseUrl()}${path}`, {
			method: 'POST', headers, body: JSON.stringify(body),
		});
		if (!resp.ok) {
			const detail = await resp.text();
			throw new Error(`${resp.status}: ${detail}`);
		}
		return resp.json();
	}

	// ── Panel open / close / tabs ────────────────────────────────

	function toggle() {
		if (_panel && _panel.classList.contains('open')) close();
		else open();
	}

	function open() {
		if (typeof window.closeNumelSidePanels === 'function') {
			window.closeNumelSidePanels(['admin']);
		}
		if (_panel) _panel.classList.add('open');
		_refreshCurrentTab();
	}

	function close() {
		if (_panel) _panel.classList.remove('open');
	}

	function isOpen() {
		return !!(_panel && _panel.classList.contains('open'));
	}

	function _switchTab(tabId) {
		document.querySelectorAll('.nw-admin-tab').forEach(t => t.classList.toggle('active', t.dataset.tab === tabId));
		document.querySelectorAll('.nw-admin-tab-content').forEach(c => c.classList.toggle('active', c.id === tabId));
		_refreshCurrentTab();
	}

	function _refreshCurrentTab() {
		const active = document.querySelector('.nw-admin-tab.active');
		if (!active) return;
		const tabId = active.dataset.tab;
		if (tabId === 'adminTabUsers')  _loadUsers();
		if (tabId === 'adminTabExec')   _loadExecutions();
		if (tabId === 'adminTabStats')  _loadStats();
		if (tabId === 'adminTabDiagnostics') _loadDiagnostics();
	}

	// ── Users ────────────────────────────────────────────────────

	async function _loadUsers() {
		const list = document.getElementById('adminUserList');
		if (!list) return;
		const activeOnly = document.getElementById('adminActiveOnly')?.checked ?? true;
		list.innerHTML = '<div style="color:var(--sg-text-tertiary);font-size:12px;">Loading...</div>';
		try {
			const data = await _post('/admin/users', { active_only: activeOnly, limit: 200 });
			const users = data.users || [];
			if (!users.length) { list.innerHTML = '<div style="color:var(--sg-text-tertiary);font-size:12px;">No users.</div>'; return; }
			list.innerHTML = '';
			for (const u of users) {
				const q = u.quota || {};
				const cpuH   = (q.cpu_seconds_remaining / 3600).toFixed(1);
				const stoMB  = (q.storage_bytes_remaining / 1_048_576).toFixed(0);
				const card = document.createElement('div');
				card.className = 'nw-admin-card';
				card.innerHTML = `
					<div class="nw-admin-card-header">
						<span class="nw-admin-card-title">${_esc(u.username)}</span>
						<span class="nw-admin-card-badge nw-admin-badge-${u.role}">${u.role}</span>
					</div>
					<div class="nw-admin-card-detail">
						${_esc(u.email)}<br>
						CPU: ${cpuH}h &middot; Storage: ${stoMB}MB &middot; Concurrent: ${q.max_concurrent_runs || 0}
						${!u.active ? '<br><b style="color:var(--sg-accent-red)">INACTIVE</b>' : ''}
					</div>
					<div class="nw-admin-card-actions">
						<button class="nw-btn nw-btn-sm nw-btn-secondary" data-action="edit" data-uid="${u.id}">Edit</button>
						<button class="nw-btn nw-btn-sm nw-btn-secondary" data-action="quota" data-uid="${u.id}">Quota</button>
						${u.active ? `<button class="nw-btn nw-btn-sm nw-btn-danger" data-action="deactivate" data-uid="${u.id}" data-uname="${_esc(u.username)}">Deactivate</button>` : ''}
					</div>`;
				card.addEventListener('click', _onUserAction);
				list.appendChild(card);
			}
		} catch (e) {
			list.innerHTML = `<div style="color:var(--sg-accent-red);font-size:12px;">Error: ${_esc(e.message)}</div>`;
		}
	}

	function _onUserAction(e) {
		const btn = e.target.closest('[data-action]');
		if (!btn) return;
		const uid    = btn.dataset.uid;
		const action = btn.dataset.action;
		if (action === 'edit')       _showEditDialog(uid);
		if (action === 'quota')      _showQuotaDialog(uid);
		if (action === 'deactivate') _deactivateUser(uid, btn.dataset.uname);
	}

	async function _showEditDialog(uid) {
		try {
			const data = await _post(`/admin/users/${uid}`);
			const u = data.user;
			_dialog(`Edit User: ${u.username}`, `
				<label>Email</label>
				<input id="_adm_email" value="${_esc(u.email)}">
				<label>Role</label>
				<select id="_adm_role">
					<option value="admin" ${u.role === 'admin' ? 'selected' : ''}>Admin</option>
					<option value="user"  ${u.role === 'user'  ? 'selected' : ''}>User</option>
					<option value="viewer" ${u.role === 'viewer' ? 'selected' : ''}>Viewer</option>
				</select>
			`, async () => {
				const email = document.getElementById('_adm_email').value.trim();
				const role  = document.getElementById('_adm_role').value;
				await _post(`/admin/users/${uid}/update`, { email, role });
				_loadUsers();
			});
		} catch (e) {
			await NumelAlert('Admin Error', `Error: ${_esc(e.message)}`);
		}
	}

	async function _showQuotaDialog(uid) {
		try {
			const data = await _post(`/admin/users/${uid}`);
			const q = data.quota;
			_dialog(`Quota: ${data.user.username}`, `
				<label>CPU seconds remaining</label>
				<input id="_adm_cpu" type="number" value="${q.cpu_seconds_remaining}">
				<label>Storage bytes remaining</label>
				<input id="_adm_sto" type="number" value="${q.storage_bytes_remaining}">
				<label>Max concurrent runs</label>
				<input id="_adm_conc" type="number" value="${q.max_concurrent_runs}">
				<label>GPU hours remaining</label>
				<input id="_adm_gpu" type="number" value="${q.gpu_hours_remaining}">
				<label>Max spaces</label>
				<input id="_adm_spaces" type="number" value="${q.max_spaces}">
				<label>Max assets per space</label>
				<input id="_adm_assets" type="number" value="${q.max_assets_per_space}">
			`, async () => {
				await _post(`/admin/users/${uid}/quota`, {
					cpu_seconds_remaining:   parseFloat(document.getElementById('_adm_cpu').value),
					storage_bytes_remaining: parseInt(document.getElementById('_adm_sto').value),
					max_concurrent_runs:     parseInt(document.getElementById('_adm_conc').value),
					gpu_hours_remaining:     parseFloat(document.getElementById('_adm_gpu').value),
					max_spaces:              parseInt(document.getElementById('_adm_spaces').value),
					max_assets_per_space:    parseInt(document.getElementById('_adm_assets').value),
				});
				_loadUsers();
			});
		} catch (e) {
			await NumelAlert('Admin Error', `Error: ${_esc(e.message)}`);
		}
	}

	async function _deactivateUser(uid, username) {
		const ok = await NumelConfirm('Deactivate User', `Deactivate user "${_esc(username)}"? They will no longer be able to log in.`, 'Deactivate', true);
		if (!ok) return;
		try {
			await _post(`/admin/users/${uid}/delete`);
			_loadUsers();
		} catch (e) {
			await NumelAlert('Admin Error', `Error: ${_esc(e.message)}`);
		}
	}

	// ── Executions ───────────────────────────────────────────────

	async function _loadExecutions() {
		const activeList = document.getElementById('adminExecActive');
		const list       = document.getElementById('adminExecList');
		if (!list) return;
		const filter = (document.getElementById('adminExecFilter')?.value || '').trim();
		list.innerHTML = '<div style="color:var(--sg-text-tertiary);font-size:12px;">Loading...</div>';
		try {
			const body = { limit: 100 };
			if (filter) body.workflow_name = filter;
			const data = await _post('/admin/executions', body);
			const active = data.active_execution_ids || [];
			const items  = data.executions || [];

			// Active executions
			if (activeList) {
				if (active.length) {
					activeList.innerHTML = '<div style="font-size:11px;color:var(--sg-text-secondary);margin-bottom:4px;">Running:</div>' +
						active.map(id => `<span class="nw-admin-active-tag">${_esc(id.slice(0,8))}...</span>`).join(' ');
				} else {
					activeList.innerHTML = '';
				}
			}

			// History
			if (!items.length) { list.innerHTML = '<div style="color:var(--sg-text-tertiary);font-size:12px;">No executions.</div>'; return; }
			list.innerHTML = '';
			for (const ex of items) {
				const dur = ex.duration_ms != null ? `${ex.duration_ms}ms` : '—';
				const status = ex.status || 'unknown';
				const statusCls = `nw-admin-exec-${status}`;
				const card = document.createElement('div');
				card.className = 'nw-admin-card';
				card.innerHTML = `
					<div class="nw-admin-card-header">
						<span class="nw-admin-card-title">${_esc(ex.workflow_name || '?')}</span>
						<span class="nw-admin-exec-status ${statusCls}">${status}</span>
					</div>
					<div class="nw-admin-card-detail">
						ID: ${_esc((ex.execution_id || '').slice(0, 12))}... &middot; Duration: ${dur}<br>
						${_esc(ex.timestamp || '')}
						${ex.error ? `<br><span style="color:var(--sg-accent-red)">${_esc(ex.error)}</span>` : ''}
					</div>`;
				list.appendChild(card);
			}
		} catch (e) {
			list.innerHTML = `<div style="color:var(--sg-accent-red);font-size:12px;">Error: ${_esc(e.message)}</div>`;
		}
	}

	// ── Stats ────────────────────────────────────────────────────

	async function _loadStats() {
		const el = document.getElementById('adminStatsContent');
		if (!el) return;
		el.innerHTML = '<div style="color:var(--sg-text-tertiary);font-size:12px;">Loading...</div>';
		try {
			const s = await _post('/admin/stats');
			const breakdown = s.execution_status_breakdown || {};
			const bdParts = Object.entries(breakdown).map(([k, v]) =>
				`<span class="nw-admin-exec-status nw-admin-exec-${k}">${k}: ${v}</span>`
			).join(' ');
			el.innerHTML = `
				<div class="nw-admin-stat-row">
					<div class="nw-admin-stat-card">
						<div class="nw-admin-stat-value">${s.active_users}</div>
						<div class="nw-admin-stat-label">Active Users</div>
					</div>
					<div class="nw-admin-stat-card">
						<div class="nw-admin-stat-value">${s.total_users}</div>
						<div class="nw-admin-stat-label">Total Users</div>
					</div>
				</div>
				<div class="nw-admin-stat-row">
					<div class="nw-admin-stat-card">
						<div class="nw-admin-stat-value">${s.active_executions}</div>
						<div class="nw-admin-stat-label">Running Now</div>
					</div>
					<div class="nw-admin-stat-card">
						<div class="nw-admin-stat-value">${s.total_executions}</div>
						<div class="nw-admin-stat-label">Total Executions</div>
					</div>
				</div>
				${bdParts ? `<div class="nw-admin-card" style="margin-top:6px;"><b>Status Breakdown</b><br>${bdParts}</div>` : ''}
			`;
		} catch (e) {
			el.innerHTML = `<div style="color:var(--sg-accent-red);font-size:12px;">Error: ${_esc(e.message)}</div>`;
		}
	}

	// ── Diagnostics ──────────────────────────────────────────────

	async function _loadDiagnostics() {
		const el = document.getElementById('adminDiagnosticsContent');
		if (!el) return;
		el.innerHTML = '<div style="color:var(--sg-text-tertiary);font-size:12px;">Loading...</div>';
		try {
			const data = await _post('/admin/diagnostics');
			const process = data.process || {};
			const platform = data.platform || {};
			const runtime = data.runtime || {};
			const disk = runtime.disk_usage || {};
			const auth = platform.auth || {};
			const paths = Array.isArray(runtime.paths) ? runtime.paths : [];

			const diskLabel = disk.ok
				? `${_formatBytes(disk.used_bytes)} used / ${_formatBytes(disk.total_bytes)} total`
				: (disk.detail || 'Unavailable');

			const pathRows = paths.length
				? paths.map((entry) => {
					const flags = [];
					if (entry.exists) flags.push(entry.is_dir ? 'dir' : (entry.is_file ? 'file' : 'path'));
					else flags.push('missing');
					return `
						<div class="nw-admin-path-row">
							<div class="nw-admin-path-name">${_esc(entry.name || 'path')}</div>
							<div class="nw-admin-path-path">${_esc(entry.path || '')}</div>
							<div class="nw-admin-path-status ${entry.exists ? 'is-ok' : 'is-missing'}">${_esc(flags.join(' · '))}</div>
						</div>
					`;
				}).join('')
				: '<div class="nw-admin-card-detail">No runtime paths reported.</div>';

			el.innerHTML = `
				<div class="nw-admin-stat-row">
					<div class="nw-admin-stat-card">
						<div class="nw-admin-stat-value">${_esc(data.backend || '—')}</div>
						<div class="nw-admin-stat-label">Active Backend</div>
					</div>
					<div class="nw-admin-stat-card">
						<div class="nw-admin-stat-value">${_esc(_formatSeconds(process.uptime_seconds))}</div>
						<div class="nw-admin-stat-label">Process Uptime</div>
					</div>
				</div>
				<div class="nw-admin-card">
					<div class="nw-admin-card-header">
						<span class="nw-admin-card-title">Runtime Snapshot</span>
						<span class="nw-admin-exec-status nw-admin-exec-${_statusTone(data.status)}">${_esc(data.status || 'unknown')}</span>
					</div>
					<div class="nw-admin-diag-kv">
						<div class="nw-admin-diag-key">Python</div>
						<div class="nw-admin-diag-value">${_esc(process.python || '—')}</div>
						<div class="nw-admin-diag-key">PID</div>
						<div class="nw-admin-diag-value">${_esc(process.pid || '—')}</div>
						<div class="nw-admin-diag-key">CWD</div>
						<div class="nw-admin-diag-value">${_esc(process.cwd || '—')}</div>
						<div class="nw-admin-diag-key">Config</div>
						<div class="nw-admin-diag-value">${_esc(data.platform_config_path || '—')}</div>
						<div class="nw-admin-diag-key">Auth</div>
						<div class="nw-admin-diag-value">${_esc(auth.provider || 'unknown')} · has users: ${auth.has_users ? 'yes' : 'no'}</div>
						<div class="nw-admin-diag-key">Disk</div>
						<div class="nw-admin-diag-value">${_esc(diskLabel)}</div>
					</div>
				</div>
				<div class="nw-admin-card">
					<div class="nw-admin-card-title">Runtime Paths</div>
					<div class="nw-admin-path-list">${pathRows}</div>
				</div>
				${_renderJsonCard('Platform Components', platform.components || {})}
				${_renderJsonCard('Startup Checks', platform.startup_checks || {})}
				${_renderJsonCard('Backend Configuration', data.backend_config || {})}
			`;
		} catch (e) {
			el.innerHTML = `<div style="color:var(--sg-accent-red);font-size:12px;">Error: ${_esc(e.message)}</div>`;
		}
	}

	// ── Dialog helper ────────────────────────────────────────────

	function _dialog(title, bodyHtml, onSave) {
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

		overlay.querySelector('[data-role="cancel"]').onclick = () => overlay.remove();
		overlay.querySelector('[data-role="save"]').onclick = async () => {
			try {
				await onSave();
				overlay.remove();
			} catch (e) {
				await NumelAlert('Admin Error', `Error: ${_esc(e.message)}`);
			}
		};
		overlay.addEventListener('click', (e) => { if (e.target === overlay) overlay.remove(); });
	}

	// ── Escape HTML ──────────────────────────────────────────────

	function _esc(s) {
		if (!s) return '';
		const d = document.createElement('div');
		d.textContent = String(s);
		return d.innerHTML;
	}

	function _renderJsonCard(title, value) {
		return `
			<div class="nw-admin-card">
				<div class="nw-admin-card-title">${_esc(title)}</div>
				<pre class="nw-ext-pre">${_esc(JSON.stringify(value, null, 2))}</pre>
			</div>
		`;
	}

	function _formatBytes(value) {
		const num = Number(value);
		if (!Number.isFinite(num) || num < 0) return '—';
		if (num < 1024) return `${num} B`;
		const units = ['KB', 'MB', 'GB', 'TB'];
		let size = num;
		let unit = 'B';
		for (const nextUnit of units) {
			size /= 1024;
			unit = nextUnit;
			if (size < 1024) break;
		}
		return `${size >= 100 ? size.toFixed(0) : size.toFixed(1)} ${unit}`;
	}

	function _formatSeconds(value) {
		const num = Number(value);
		if (!Number.isFinite(num) || num < 0) return '—';
		if (num < 60) return `${num.toFixed(num >= 10 ? 0 : 1)}s`;
		if (num < 3600) return `${(num / 60).toFixed(1)}m`;
		return `${(num / 3600).toFixed(1)}h`;
	}

	function _statusTone(status) {
		switch ((status || '').toLowerCase()) {
			case 'ready':
			case 'completed':
				return 'completed';
			case 'degraded':
			case 'failed':
				return 'failed';
			case 'running':
				return 'running';
			case 'cancelled':
				return 'cancelled';
			default:
				return 'running';
		}
	}

	// ── Init ─────────────────────────────────────────────────────

	function init() {
		_panel    = document.getElementById('adminPanel');
		_closeBtn = document.getElementById('adminCloseBtn');
		_openBtn  = document.getElementById('adminOpenBtn');

		if (_closeBtn) _closeBtn.onclick = close;
		if (_openBtn)  _openBtn.onclick  = toggle;

		// Tab switching
		document.querySelectorAll('.nw-admin-tab').forEach(tab => {
			tab.addEventListener('click', () => _switchTab(tab.dataset.tab));
		});

		// Refresh buttons
		const ru = document.getElementById('adminRefreshUsers');
		const re = document.getElementById('adminRefreshExec');
		const rs = document.getElementById('adminRefreshStats');
		const rd = document.getElementById('adminRefreshDiagnostics');
		if (ru) ru.onclick = _loadUsers;
		if (re) re.onclick = _loadExecutions;
		if (rs) rs.onclick = _loadStats;
		if (rd) rd.onclick = _loadDiagnostics;

		// Active-only toggle
		const ao = document.getElementById('adminActiveOnly');
		if (ao) ao.onchange = _loadUsers;

		// Filter keyup
		const ef = document.getElementById('adminExecFilter');
		if (ef) ef.addEventListener('keydown', (e) => { if (e.key === 'Enter') _loadExecutions(); });
	}

	/** Call after login to show admin button if user is admin. */
	function checkAdminAccess(user) {
		const isAdmin = !!(user && user.role === 'admin');
		if (_openBtn) _openBtn.style.display = isAdmin ? '' : 'none';
		if (!isAdmin) close();
	}

	// Auto-init on DOMContentLoaded
	if (document.readyState === 'loading') {
		document.addEventListener('DOMContentLoaded', init);
	} else {
		init();
	}

	return { open, close, toggle, isOpen, checkAdminAccess };
})();

window.NumelAdmin = NumelAdmin;
