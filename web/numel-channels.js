// numel-channels.js — Channel management panel (Telegram, Discord, Slack, etc.)

/* global NumelConfirm */
/* exported NumelChannels */

// eslint-disable-next-line no-unused-vars
const NumelChannels = (() => {

	let _panel, _closeBtn, _openBtn, _refreshBtn, _addBtn, _listEl, _summaryEl;
	let _availableTypes = [];

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

	function _esc(s) {
		if (!s) return '';
		const d = document.createElement('div');
		d.textContent = String(s);
		return d.innerHTML;
	}

	// ── Panel open / close ──────────────────────────────────────

	function toggle() {
		if (_panel && _panel.classList.contains('open')) close();
		else open();
	}

	function open() {
		if (typeof window.closeNumelSidePanels === 'function') {
			window.closeNumelSidePanels(['channels']);
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

	// ── Refresh channel list ────────────────────────────────────

	async function refresh() {
		if (!_listEl) return;
		_listEl.innerHTML = '<div style="color:var(--sg-text-tertiary);font-size:12px;">Loading...</div>';
		try {
			const data = await _post('/channels/list');
			const channels = Array.isArray(data) ? data : (data.channels || []);
			_renderList(channels);
			_updateSummary(channels);
			// Sync pool idle timeout
			_post('/channels/pool/config', {}).then(cfg => {
				const sel = document.getElementById('channelIdleTimeout');
				if (sel && cfg.idle_timeout) sel.value = String(cfg.idle_timeout);
			}).catch(() => {});
		} catch (e) {
			_listEl.innerHTML = `<div style="color:var(--sg-accent-red);font-size:12px;">Error: ${_esc(e.message)}</div>`;
		}
	}

	function _updateSummary(channels) {
		if (!_summaryEl) return;
		if (!channels.length) {
			_summaryEl.innerHTML = 'No channels configured';
			return;
		}
		const parts = channels.map(ch => {
			const status = (ch.status || 'stopped').toLowerCase();
			const dotCls = `nw-ch-dot nw-ch-dot-${status}`;
			return `<span class="${dotCls}"></span>${_esc(ch.name || ch.channel_type)}`;
		});
		_summaryEl.innerHTML = parts.join(' &middot; ');
	}

	function _renderList(channels) {
		_listEl.innerHTML = '';
		if (!channels.length) {
			_listEl.innerHTML = '<div style="color:var(--sg-text-tertiary);font-size:12px;">No channels. Click "+ Add Channel" to get started.</div>';
			return;
		}
		for (const ch of channels) {
			const status = (ch.status || 'stopped').toLowerCase();
			const badgeCls = `nw-channel-status-badge nw-ch-badge-${status}`;
			const isRunning = status === 'running';
			const card = document.createElement('div');
			card.className = 'nw-admin-card';
			card.innerHTML = `
				<div class="nw-admin-card-header">
					<span class="nw-admin-card-title">${_esc(ch.name || ch.id)}</span>
					<span class="${badgeCls}">${status}</span>
				</div>
				<div class="nw-admin-card-detail">
					Type: ${_esc(ch.channel_type)} &middot; ID: ${_esc((ch.id || '').slice(0, 12))}
					${ch.auto_start ? ' &middot; auto-start' : ''}
					${ch.error ? `<br><span style="color:var(--sg-accent-red)">${_esc(ch.error)}</span>` : ''}
				</div>
				<div class="nw-admin-card-actions">
					${isRunning
						? `<button class="nw-btn nw-btn-sm nw-btn-secondary" data-action="stop" data-cid="${ch.id}">Stop</button>`
						: `<button class="nw-btn nw-btn-sm nw-btn-success" data-action="start" data-cid="${ch.id}">Start</button>`
					}
					<button class="nw-btn nw-btn-sm nw-btn-secondary" data-action="edit" data-cid="${ch.id}">Edit</button>
					<button class="nw-btn nw-btn-sm nw-btn-danger" data-action="remove" data-cid="${ch.id}" data-cname="${_esc(ch.name || ch.id)}">Remove</button>
				</div>`;
			card.addEventListener('click', _onAction);
			_listEl.appendChild(card);
		}
	}

	// ── Actions ─────────────────────────────────────────────────

	async function _onAction(e) {
		const btn = e.target.closest('[data-action]');
		if (!btn) return;
		const cid    = btn.dataset.cid;
		const action = btn.dataset.action;
		try {
			if (action === 'start') {
				await _post('/channels/start', { channel_id: cid });
				refresh();
			} else if (action === 'stop') {
				await _post('/channels/stop', { channel_id: cid });
				refresh();
			} else if (action === 'remove') {
				const ok = await NumelConfirm(
					'Remove Channel',
					`Remove channel "${btn.dataset.cname}"? This cannot be undone.`,
					'Remove', true
				);
				if (!ok) return;
				await _post('/channels/remove', { channel_id: cid });
				refresh();
			} else if (action === 'edit') {
				_showEditDialog(cid);
			}
		} catch (err) {
			await NumelAlert('Channel Error', `Error: ${err.message}`);
		}
	}

	// ── Add Channel Dialog ──────────────────────────────────────

	async function _showAddDialog() {
		// Fetch available types if not cached
		if (!_availableTypes.length) {
			try {
				const data = await _post('/channels/types');
				// API returns list of {type, class, doc} objects
				_availableTypes = Array.isArray(data) ? data.map(t => t.type || t) : (data.types || []);
			} catch {
				_availableTypes = ['telegram', 'discord', 'slack', 'whatsapp', 'signal', 'teams', 'webhook'];
			}
		}

		const typeOptions = _availableTypes.map(t =>
			`<option value="${t}">${t.charAt(0).toUpperCase() + t.slice(1)}</option>`
		).join('');

		_dialog('Add Channel', `
			<label>Name</label>
			<input id="_ch_name" placeholder="my-bot" autocomplete="off">
			<label>Type</label>
			<select id="_ch_type">${typeOptions}</select>
			<label>Token / API Key</label>
			<input id="_ch_token" type="password" placeholder="Bot token or ${'\u0024{VAR_NAME}'}" autocomplete="off">
			<label class="nw-checkbox-row">
				<input id="_ch_autostart" type="checkbox" checked> Auto-start on server boot
			</label>
		`, async () => {
			const name       = document.getElementById('_ch_name').value.trim();
			const type       = document.getElementById('_ch_type').value;
			const token      = document.getElementById('_ch_token').value.trim();
			const auto_start = document.getElementById('_ch_autostart').checked;
			if (!name) throw new Error('Name is required');
			if (!token) throw new Error('Token is required');
			await _post('/channels/add', { name, channel_type: type, token, auto_start });
			refresh();
		});
	}

	// ── Edit Channel Dialog ─────────────────────────────────────

	async function _showEditDialog(channelId) {
		try {
			const data = await _post('/channels/status', { channel_id: channelId });
			const ch = data;
			_dialog(`Edit: ${_esc(ch.name || channelId)}`, `
				<label>Name</label>
				<input id="_ch_name" value="${_esc(ch.name || '')}" autocomplete="off">
				<label>Token / API Key</label>
				<input id="_ch_token" type="password" placeholder="(unchanged if empty)" autocomplete="off">
				<label class="nw-checkbox-row">
					<input id="_ch_autostart" type="checkbox" ${ch.auto_start ? 'checked' : ''}> Auto-start on server boot
				</label>
			`, async () => {
				const updates = {};
				const name  = document.getElementById('_ch_name').value.trim();
				const token = document.getElementById('_ch_token').value.trim();
				updates.auto_start = document.getElementById('_ch_autostart').checked;
				if (name)  updates.name  = name;
				if (token) updates.token = token;
				// Use remove + re-add pattern since there's no update endpoint
				// For now just refresh — update endpoint would be better
				await _post('/channels/remove', { channel_id: channelId });
				await _post('/channels/add', {
					name: name || ch.name,
					channel_type: ch.channel_type,
					token: token || ch.token || '',
					auto_start: updates.auto_start,
				});
				refresh();
			});
		} catch (e) {
			await NumelAlert('Channel Error', `Error: ${e.message}`);
		}
	}

	// ── Dialog helper (reuses admin dialog pattern) ─────────────

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
				await NumelAlert('Channel Error', `Error: ${e.message}`);
			}
		};
		overlay.addEventListener('click', (e) => { if (e.target === overlay) overlay.remove(); });
	}

	// ── Init ─────────────────────────────────────────────────────

	function init() {
		_panel      = document.getElementById('channelPanel');
		_closeBtn   = document.getElementById('channelCloseBtn');
		_openBtn    = document.getElementById('channelPanelBtn');
		_refreshBtn = document.getElementById('channelRefreshBtn');
		_addBtn     = document.getElementById('channelAddBtn');
		_listEl     = document.getElementById('channelList');
		_summaryEl  = document.getElementById('channelSummary');

		if (_closeBtn)   _closeBtn.onclick   = close;
		if (_openBtn)    _openBtn.onclick    = toggle;
		if (_refreshBtn) _refreshBtn.onclick = refresh;
		if (_addBtn)     _addBtn.onclick     = _showAddDialog;

		// Agent idle timeout control
		const idleSel = document.getElementById('channelIdleTimeout');
		if (idleSel) {
			idleSel.addEventListener('change', () => {
				_post('/channels/pool/config', { idle_timeout: Number(idleSel.value) }).catch(() => {});
			});
		}
	}

	/** Refresh summary in left panel (call after connect). */
	async function refreshSummary() {
		try {
			const data = await _post('/channels/list');
			const channels = Array.isArray(data) ? data : (data.channels || []);
			_updateSummary(channels);
		} catch {
			// Server not ready yet — ignore
		}
	}

	// Auto-init
	if (document.readyState === 'loading') {
		document.addEventListener('DOMContentLoaded', init);
	} else {
		init();
	}

	return { open, close, toggle, isOpen, refresh, refreshSummary };
})();
