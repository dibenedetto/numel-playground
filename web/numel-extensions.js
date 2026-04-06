// numel-extensions.js - Toolkit and skill management panel

/* global NumelConfirm, NumelAPI, NumelAdmin, NumelChannels */
/* exported NumelExtensions */

// eslint-disable-next-line no-unused-vars
const NumelExtensions = (() => {

	let _panel;
	let _toolkitList;
	let _skillList;
	let _uploadBtn;
	let _uploadInput;

	function _baseUrl() {
		const el = document.getElementById('serverUrl');
		return (el && el.value) || window.location.origin;
	}

	function _api() {
		return new NumelAPI(_baseUrl());
	}

	function _isAdmin() {
		return !!(window._numelUser && String(window._numelUser.role || '').toLowerCase() === 'admin');
	}

	function _esc(s) {
		if (s == null) return '';
		const d = document.createElement('div');
		d.textContent = String(s);
		return d.innerHTML;
	}

	function _escAttr(s) {
		return String(s == null ? '' : s)
			.replace(/&/g, '&amp;')
			.replace(/"/g, '&quot;')
			.replace(/</g, '&lt;')
			.replace(/>/g, '&gt;');
	}

	function _boolBadge(on, onText, offText) {
		return `<span class="nw-ext-badge ${on ? 'nw-ext-badge-enabled' : 'nw-ext-badge-disabled'}">${on ? onText : offText}</span>`;
	}

	function _setUploadVisibility() {
		if (_uploadBtn) _uploadBtn.style.display = _isAdmin() ? '' : 'none';
	}

	function toggle() {
		if (_panel && _panel.classList.contains('open')) close();
		else open();
	}

	function open() {
		if (typeof window.closeNumelSidePanels === 'function') {
			window.closeNumelSidePanels(['extensions']);
		}
		if (_panel) _panel.classList.add('open');
		_setUploadVisibility();
		refresh();
	}

	function close() {
		if (_panel) _panel.classList.remove('open');
	}

	function isOpen() {
		return !!(_panel && _panel.classList.contains('open'));
	}

	function _activeTabId() {
		return document.querySelector('.nw-ext-tab.active')?.dataset.tab || 'extensionsTabToolkits';
	}

	function _switchTab(tabId) {
		document.querySelectorAll('.nw-ext-tab').forEach(tab => {
			tab.classList.toggle('active', tab.dataset.tab === tabId);
		});
		document.querySelectorAll('.nw-ext-tab-content').forEach(panel => {
			panel.classList.toggle('active', panel.id === tabId);
		});
		refresh();
	}

	async function refresh() {
		if (_activeTabId() === 'extensionsTabSkills') return _loadSkills();
		return _loadToolkits();
	}

	async function _loadToolkits() {
		if (!_toolkitList) return;
		_toolkitList.innerHTML = '<div class="nw-ext-empty">Loading toolkits...</div>';
		try {
			const toolkits = await _api().toolkitList();
			_renderToolkits(toolkits || []);
		} catch (e) {
			_toolkitList.innerHTML = `<div class="nw-ext-empty">Error loading toolkits: ${_esc(e.message)}</div>`;
		}
	}

	function _renderToolkits(toolkits) {
		if (!_toolkitList) return;
		if (!toolkits.length) {
			_toolkitList.innerHTML = '<div class="nw-ext-empty">No toolkits available.</div>';
			return;
		}
		_toolkitList.innerHTML = '';
		for (const tk of toolkits) {
			const card = document.createElement('div');
			card.className = 'nw-admin-card';
			card.innerHTML = `
				<div class="nw-admin-card-header">
					<span class="nw-admin-card-title">${_esc(tk.name)}</span>
					<div class="nw-ext-card-badges">
						<span class="nw-ext-badge ${tk.builtin ? 'nw-ext-badge-builtin' : 'nw-ext-badge-shared'}">${tk.builtin ? 'Built-in' : 'Shared'}</span>
					</div>
				</div>
				<div class="nw-admin-card-detail">
					${_esc(tk.description || 'No description available.')}
					${tk.class_name ? `<br><span class="nw-ext-code">${_esc(tk.class_name)}</span>` : ''}
				</div>
				<div class="nw-admin-card-actions">
					<button class="nw-btn nw-btn-sm nw-btn-secondary" data-action="inspect" data-name="${_escAttr(tk.name)}">Inspect</button>
					${_isAdmin() && tk.removable ? `<button class="nw-btn nw-btn-sm nw-btn-danger" data-action="remove" data-name="${_escAttr(tk.name)}">Remove</button>` : ''}
				</div>`;
			card.addEventListener('click', _onToolkitAction);
			_toolkitList.appendChild(card);
		}
	}

	async function _onToolkitAction(e) {
		const btn = e.target.closest('[data-action]');
		if (!btn) return;
		if (btn.dataset.action === 'inspect') {
			await _inspectToolkit(btn.dataset.name);
			return;
		}
		if (btn.dataset.action === 'remove') {
			await _removeToolkit(btn.dataset.name);
		}
	}

	async function _inspectToolkit(name) {
		try {
			const data = await _api().toolkitInspect(name);
			const params = (data.params || []).map(p =>
				`<li><span class="nw-ext-code">${_esc(p.name)}</span> : ${_esc(p.type || 'Any')}${p.required ? ' (required)' : ''}${p.default != null ? ` = ${_esc(String(p.default))}` : ''}</li>`
			).join('');
			const methods = (data.methods || []).map(m =>
				`<li><span class="nw-ext-code">${_esc(m.name)}${_esc(m.signature || '')}</span>${m.description ? ` - ${_esc(m.description)}` : ''}</li>`
			).join('');
			_dialog(
				`Toolkit: ${data.class_name || name}`,
				`
					<div class="nw-ext-note">${_esc((data.description || '').split('\n')[0] || 'No description available.')}</div>
					<h4>Constructor Parameters</h4>
					${params ? `<ul>${params}</ul>` : '<div class="nw-ext-empty">No constructor parameters.</div>'}
					<h4>Methods</h4>
					${methods ? `<ul>${methods}</ul>` : '<div class="nw-ext-empty">No public methods found.</div>'}
				`,
				null,
				{ wide: true }
			);
		} catch (e) {
			_messageDialog('Toolkit Error', `Could not inspect "${name}": ${e.message}`);
		}
	}

	async function _removeToolkit(name) {
		const ok = await NumelConfirm(
			'Remove Toolkit',
			`Remove toolkit "${name}"? Built-in toolkits are protected, but deleting a shared contrib toolkit may break workflows that still reference it.`,
			'Remove',
			true
		);
		if (!ok) return;
		try {
			await _api().toolkitRemove(name);
			await _loadToolkits();
		} catch (e) {
			_messageDialog('Toolkit Remove Error', `Could not remove "${name}": ${e.message}`);
		}
	}

	async function _loadSkills() {
		if (!_skillList) return;
		_skillList.innerHTML = '<div class="nw-ext-empty">Loading skills...</div>';
		try {
			const skills = await _api().skillsList();
			_renderSkills(skills || []);
		} catch (e) {
			_skillList.innerHTML = `<div class="nw-ext-empty">Error loading skills: ${_esc(e.message)}</div>`;
		}
	}

	function _renderSkills(skills) {
		if (!_skillList) return;
		if (!skills.length) {
			_skillList.innerHTML = '<div class="nw-ext-empty">No skills installed.</div>';
			return;
		}
		_skillList.innerHTML = '';
		for (const sk of skills) {
			const tags = Array.isArray(sk.tags) && sk.tags.length ? `<br>Tags: ${_esc(sk.tags.join(', '))}` : '';
			const example = Array.isArray(sk.examples) && sk.examples.length ? `<br>Example: ${_esc(sk.examples[0])}` : '';
			const scripts = Array.isArray(sk.scripts) && sk.scripts.length ? `<br>Scripts: ${_esc(sk.scripts.join(', '))}` : '';
			const card = document.createElement('div');
			card.className = 'nw-admin-card';
			card.innerHTML = `
				<div class="nw-admin-card-header">
					<span class="nw-admin-card-title">${_esc(sk.name)}</span>
					<div class="nw-ext-card-badges">
						${_boolBadge(!!sk.enabled, 'Enabled', 'Disabled')}
						<span class="nw-ext-badge ${sk.setup_done ? 'nw-ext-badge-enabled' : 'nw-ext-badge-setup'}">${sk.setup_done ? 'Setup Done' : 'Setup Pending'}</span>
					</div>
				</div>
				<div class="nw-admin-card-detail">
					${_esc(sk.description || 'No description available.')}
					${tags}
					${example}
					${scripts}
				</div>
				<div class="nw-admin-card-actions">
					<button class="nw-btn nw-btn-sm nw-btn-secondary" data-action="view" data-name="${_escAttr(sk.name)}">View</button>
					<button class="nw-btn nw-btn-sm nw-btn-secondary" data-action="setup" data-name="${_escAttr(sk.name)}">Setup</button>
					<button class="nw-btn nw-btn-sm ${sk.enabled ? 'nw-btn-secondary' : 'nw-btn-success'}" data-action="${sk.enabled ? 'disable' : 'enable'}" data-name="${_escAttr(sk.name)}">${sk.enabled ? 'Disable' : 'Enable'}</button>
					<button class="nw-btn nw-btn-sm nw-btn-danger" data-action="remove" data-name="${_escAttr(sk.name)}">Remove</button>
				</div>`;
			card.addEventListener('click', _onSkillAction);
			_skillList.appendChild(card);
		}
	}

	async function _onSkillAction(e) {
		const btn = e.target.closest('[data-action]');
		if (!btn) return;
		const action = btn.dataset.action;
		const name = btn.dataset.name;
		try {
			if (action === 'view') return _viewSkill(name);
			if (action === 'setup') return _setupSkill(name);
			if (action === 'enable') await _api().skillsEnable(name);
			if (action === 'disable') await _api().skillsDisable(name);
			if (action === 'remove') return _removeSkill(name);
			await _loadSkills();
		} catch (e2) {
			_messageDialog('Skill Error', `Action failed for "${name}": ${e2.message}`);
		}
	}

	async function _viewSkill(name) {
		try {
			const sk = await _api().skillsGet(name);
			if (sk && sk.error) throw new Error(sk.error);
			const requires = sk.requires && Object.keys(sk.requires).length
				? `<div class="nw-ext-note">Requires: ${_esc(JSON.stringify(sk.requires))}</div>`
				: '';
			_dialog(
				`Skill: ${sk.name || name}`,
				`
					<div class="nw-ext-note">${_esc(sk.description || 'No description available.')}</div>
					${requires}
					<div class="nw-ext-pre">${_esc(sk.body || 'No body content.')}</div>
				`,
				null,
				{ wide: true }
			);
		} catch (e) {
			_messageDialog('Skill Error', `Could not load "${name}": ${e.message}`);
		}
	}

	async function _setupSkill(name) {
		try {
			const result = await _api().skillsSetup(name);
			const out = Array.isArray(result.output) ? result.output.join('\n') : '';
			const errs = Array.isArray(result.errors) ? result.errors.join('\n') : '';
			_dialog(
				`Skill Setup: ${name}`,
				`
					<div class="nw-ext-note">${result.ok ? 'Setup completed successfully.' : 'Setup finished with errors.'}</div>
					${out ? `<h4>Output</h4><div class="nw-ext-pre">${_esc(out)}</div>` : ''}
					${errs ? `<h4>Errors</h4><div class="nw-ext-pre">${_esc(errs)}</div>` : ''}
				`,
				null,
				{ wide: true }
			);
			await _loadSkills();
		} catch (e) {
			_messageDialog('Skill Setup Error', `Could not run setup for "${name}": ${e.message}`);
		}
	}

	function _skillTemplate(name) {
		const safeName = (name || 'my-skill').trim() || 'my-skill';
		return `---\nname: ${safeName}\ndescription: Short description\nauthor: \ntags: [custom]\n---\nWrite the skill instructions here.\n\n## Example Prompts\n- **"Use ${safeName} to help me with ..."**\n`;
	}

	function _showAddSkillDialog() {
		const initialName = 'my-skill';
		_dialog(
			'Add Skill',
			`
				<label>Name</label>
				<input id="_ext_skill_name" value="${_escAttr(initialName)}" autocomplete="off">
				<label>SKILL.md Content</label>
				<textarea id="_ext_skill_content" rows="18" spellcheck="false">${_esc(_skillTemplate(initialName))}</textarea>
			`,
			async () => {
				const name = document.getElementById('_ext_skill_name').value.trim();
				const content = document.getElementById('_ext_skill_content').value;
				if (!name) throw new Error('Skill name is required');
				if (!content.trim()) throw new Error('SKILL.md content is required');
				await _api().skillsAdd(name, content);
				await _loadSkills();
			},
			{ wide: true, saveText: 'Add Skill' }
		);
	}

	async function _removeSkill(name) {
		const ok = await NumelConfirm('Remove Skill', `Remove skill "${name}"? This cannot be undone.`, 'Remove', true);
		if (!ok) return;
		try {
			await _api().skillsRemove(name);
			await _loadSkills();
		} catch (e) {
			_messageDialog('Skill Remove Error', `Could not remove "${name}": ${e.message}`);
		}
	}

	function _dialog(title, bodyHtml, onSave = null, options = {}) {
		const overlay = document.createElement('div');
		const wideClass = options.wide ? ' nw-ext-dialog-wide' : '';
		const saveText = options.saveText || 'Save';
		overlay.className = 'nw-admin-dialog-overlay';
		overlay.innerHTML = `
			<div class="nw-admin-dialog${wideClass}">
				<h3>${_esc(title)}</h3>
				${bodyHtml}
				<div class="nw-admin-dialog-btns">
					<button class="nw-btn nw-btn-sm nw-btn-secondary" data-role="cancel">${onSave ? 'Cancel' : 'Close'}</button>
					${onSave ? `<button class="nw-btn nw-btn-sm nw-btn-success" data-role="save">${_esc(saveText)}</button>` : ''}
				</div>
			</div>`;
		document.body.appendChild(overlay);

		overlay.querySelector('[data-role="cancel"]').onclick = () => overlay.remove();
		const saveBtn = overlay.querySelector('[data-role="save"]');
		if (saveBtn) {
			saveBtn.onclick = async () => {
				try {
					await onSave();
					overlay.remove();
				} catch (e) {
					_messageDialog('Extensions Error', e.message);
				}
			};
		}
		overlay.addEventListener('click', (e) => {
			if (e.target === overlay) overlay.remove();
		});
	}

	function _messageDialog(title, message) {
		_dialog(title, `<div class="nw-ext-pre">${_esc(message)}</div>`, null, { wide: true });
	}

	async function _uploadToolkitFile(file) {
		if (!file) return;
		try {
			const formData = new FormData();
			formData.append('file', file);
			const result = await _api().toolkitUpload(formData, true);
			_messageDialog('Toolkit Uploaded', `Uploaded ${result.module || file.name}${result.has_toolkit_class ? '' : '\n\nWarning: no __toolkit__ class was found.'}`);
			await _loadToolkits();
		} catch (e) {
			_messageDialog('Toolkit Upload Error', e.message);
		}
	}

	function init() {
		_panel = document.getElementById('extensionsPanel');
		_toolkitList = document.getElementById('extensionsToolkitList');
		_skillList = document.getElementById('extensionsSkillList');
		_uploadBtn = document.getElementById('extensionsUploadToolkitBtn');
		_uploadInput = document.getElementById('extensionsUploadToolkitFile');

		document.getElementById('extensionsOpenBtn')?.addEventListener('click', toggle);
		document.getElementById('extensionsOpenBtnConsole')?.addEventListener('click', toggle);
		document.getElementById('extensionsCloseBtn')?.addEventListener('click', close);
		document.getElementById('extensionsRefreshToolkits')?.addEventListener('click', _loadToolkits);
		document.getElementById('extensionsRefreshSkills')?.addEventListener('click', _loadSkills);
		document.getElementById('extensionsAddSkillBtn')?.addEventListener('click', _showAddSkillDialog);
		_uploadBtn?.addEventListener('click', () => _uploadInput?.click());
		_uploadInput?.addEventListener('change', async (e) => {
			const file = e.target.files?.[0];
			e.target.value = '';
			await _uploadToolkitFile(file);
		});
		document.querySelectorAll('.nw-ext-tab').forEach(tab => {
			tab.addEventListener('click', () => _switchTab(tab.dataset.tab));
		});
		_setUploadVisibility();
	}

	if (document.readyState === 'loading') {
		document.addEventListener('DOMContentLoaded', init);
	} else {
		init();
	}

	return { open, close, toggle, isOpen, refresh };
})();

window.NumelExtensions = NumelExtensions;
