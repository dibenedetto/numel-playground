// numel-user-panel.js — User profile panel (quota, password change)

/* global NumelConfirm */
/* exported NumelUserPanel */

// eslint-disable-next-line no-unused-vars
const NumelUserPanel = (() => {

	let _panel;

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
			const data = await resp.json().catch(() => ({}));
			throw new Error(data.detail || `${resp.status}`);
		}
		return resp.json();
	}

	// ── Open / Close ─────────────────────────────────────────

	function toggle() {
		if (_panel && _panel.classList.contains('open')) close();
		else open();
	}

	function open() {
		if (_panel) _panel.classList.add('open');
		_loadProfile();
	}

	function close() {
		if (_panel) _panel.classList.remove('open');
	}

	// ── Profile ──────────────────────────────────────────────

	async function _loadProfile() {
		try {
			const data = await _post('/auth/me');
			const u = data.user;
			const q = data.quota || {};

			// Avatar initial
			const avatar = document.getElementById('userAvatar');
			if (avatar) avatar.textContent = (u.username || '?')[0];

			const name = document.getElementById('userProfileName');
			if (name) name.textContent = u.username;

			const email = document.getElementById('userProfileEmail');
			if (email) email.textContent = u.email;

			const role = document.getElementById('userProfileRole');
			if (role) role.textContent = u.role.charAt(0).toUpperCase() + u.role.slice(1);

			_renderQuota(q);
		} catch (e) {
			const name = document.getElementById('userProfileName');
			if (name) name.textContent = 'Error loading profile';
		}
	}

	function _renderQuota(q) {
		const container = document.getElementById('userQuotaBars');
		if (!container) return;

		const defaults = {
			cpu_seconds_remaining:   36000,
			storage_bytes_remaining: 1_073_741_824,
			max_concurrent_runs:     5,
			gpu_hours_remaining:     0,
		};

		const items = [
			{
				label: 'CPU Time',
				used: defaults.cpu_seconds_remaining - (q.cpu_seconds_remaining || 0),
				total: defaults.cpu_seconds_remaining,
				fmt: (v) => (v / 3600).toFixed(1) + 'h',
			},
			{
				label: 'Storage',
				used: defaults.storage_bytes_remaining - (q.storage_bytes_remaining || 0),
				total: defaults.storage_bytes_remaining,
				fmt: (v) => (v / 1_048_576).toFixed(0) + ' MB',
			},
			{
				label: 'Concurrent Runs',
				used: 0,  // we don't track active count here
				total: q.max_concurrent_runs || defaults.max_concurrent_runs,
				fmt: (v) => String(v),
				showMax: true,
			},
		];

		// Only show GPU if quota > 0
		if (q.gpu_hours_remaining > 0) {
			items.push({
				label: 'GPU Hours',
				used: 0,
				total: q.gpu_hours_remaining,
				fmt: (v) => v.toFixed(1) + 'h',
				showMax: true,
			});
		}

		container.innerHTML = '';
		for (const item of items) {
			if (item.showMax) {
				// Just show the max value, no bar
				const el = document.createElement('div');
				el.className = 'nw-user-quota-item';
				el.innerHTML = `
					<div class="nw-user-quota-label">
						<span>${item.label}</span>
						<span class="nw-user-quota-value">${item.fmt(item.total)}</span>
					</div>`;
				container.appendChild(el);
			} else {
				const pct = item.total > 0 ? Math.min(100, (item.used / item.total) * 100) : 0;
				const colorClass = pct < 60 ? 'green' : pct < 85 ? 'yellow' : 'red';
				const remaining = item.total - item.used;
				const el = document.createElement('div');
				el.className = 'nw-user-quota-item';
				el.innerHTML = `
					<div class="nw-user-quota-label">
						<span>${item.label}</span>
						<span class="nw-user-quota-value">${item.fmt(remaining)} remaining</span>
					</div>
					<div class="nw-user-quota-bar">
						<div class="nw-user-quota-fill ${colorClass}" style="width:${pct}%"></div>
					</div>`;
				container.appendChild(el);
			}
		}
	}

	// ── Password Change ──────────────────────────────────────

	async function _changePassword() {
		const current = document.getElementById('userPwCurrent').value;
		const newPw   = document.getElementById('userPwNew').value;
		const confirm = document.getElementById('userPwConfirm').value;
		const msgEl   = document.getElementById('userPwMsg');

		const showMsg = (text, success) => {
			if (!msgEl) return;
			msgEl.textContent = text;
			msgEl.className = 'nw-user-pw-msg ' + (success ? 'success' : 'error');
			msgEl.style.display = '';
		};

		if (!current || !newPw) return showMsg('All fields are required.', false);
		if (newPw !== confirm)  return showMsg('New passwords do not match.', false);
		if (newPw.length < 4)   return showMsg('Password must be at least 4 characters.', false);

		try {
			await _post('/auth/change-password', {
				current_password: current,
				new_password: newPw,
			});
			showMsg('Password updated successfully.', true);
			document.getElementById('userPwCurrent').value = '';
			document.getElementById('userPwNew').value     = '';
			document.getElementById('userPwConfirm').value = '';
		} catch (e) {
			showMsg(e.message, false);
		}
	}

	// ── Init ─────────────────────────────────────────────────

	function init() {
		_panel = document.getElementById('userPanel');

		const closeBtn  = document.getElementById('userPanelClose');
		const openBtn   = document.getElementById('userPanelBtn');
		const nameEl    = document.getElementById('authUserName');
		const pwBtn     = document.getElementById('userPwSaveBtn');

		if (closeBtn) closeBtn.onclick = close;
		if (openBtn)  openBtn.onclick  = toggle;
		if (nameEl)   nameEl.onclick   = toggle;
		if (pwBtn)    pwBtn.onclick    = _changePassword;
	}

	if (document.readyState === 'loading') {
		document.addEventListener('DOMContentLoaded', init);
	} else {
		init();
	}

	return { open, close, toggle };
})();
