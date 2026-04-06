/* ========================================================================
   NUMEL GALLERY + PUBLISHED APPS MANAGERS
   Gallery: browse/search/load workflow templates into the current space.
   Apps:    publish the current workflow as a standalone web app,
            view/open/unpublish existing apps.
   ======================================================================== */

console.log('[Numel] Loading gallery + apps managers...');

// ========================================================================
// GalleryManager
// ========================================================================

class GalleryManager {
	constructor(serverUrl, api, loadWorkflowFn) {
		this.serverUrl    = serverUrl;
		this.api          = api;
		this._loadWorkflow = loadWorkflowFn;
		this._open        = false;
		this._categories  = [];
		this._activeCategory = null;
		this._searchTimer = null;

		this._fab     = document.getElementById('galleryToggleBtn');
		this._panel   = document.getElementById('galleryPanel');
		this._closeBtn = document.getElementById('galleryCloseBtn');
		this._searchInput = document.getElementById('gallerySearch');
		this._catBar  = document.getElementById('galleryCategoryBar');
		this._grid    = document.getElementById('galleryGrid');

		this._setupUI();
	}

	_setupUI() {
		this._fab.addEventListener('click', () => this.toggle());
		this._closeBtn.addEventListener('click', () => this.close());
		this._searchInput.addEventListener('input', () => {
			clearTimeout(this._searchTimer);
			this._searchTimer = setTimeout(() => this._load(), 300);
		});
	}

	toggle() { this._open ? this.close() : this.open(); }

	isOpen() { return !!this._open; }

	async open() {
		if (this._open) return;
		if (typeof window.closeNumelSidePanels === 'function') {
			window.closeNumelSidePanels(['gallery']);
		}
		this._open = true;
		this._panel.classList.add('open');
		this._searchInput.focus();
		await this._loadCategories();
		await this._load();
	}

	close() {
		if (!this._open) return;
		this._open = false;
		this._panel.classList.remove('open');
	}

	async _loadCategories() {
		try {
			this._categories = await this.api.galleryCategories();
			this._renderCategoryBar();
		} catch { /* ignore */ }
	}

	_renderCategoryBar() {
		this._catBar.innerHTML = '';
		const all = document.createElement('button');
		all.className = 'nw-gallery-cat' + (this._activeCategory === null ? ' active' : '');
		all.textContent = 'All';
		all.addEventListener('click', () => { this._activeCategory = null; this._load(); this._renderCategoryBar(); });
		this._catBar.appendChild(all);

		for (const cat of this._categories) {
			const btn = document.createElement('button');
			btn.className = 'nw-gallery-cat' + (this._activeCategory === cat ? ' active' : '');
			btn.textContent = cat.replace(/\b\w/g, c => c.toUpperCase());
			btn.addEventListener('click', () => {
				this._activeCategory = cat;
				this._load();
				this._renderCategoryBar();
			});
			this._catBar.appendChild(btn);
		}
	}

	async _load() {
		this._grid.innerHTML = '<div class="nw-gallery-loading">Loading...</div>';
		try {
			const items = await this.api.galleryList({
				category: this._activeCategory || undefined,
				search: this._searchInput.value.trim() || undefined,
			});
			this._renderGrid(items);
		} catch (err) {
			this._grid.innerHTML = `<div class="nw-gallery-empty">Failed to load: ${err.message}</div>`;
		}
	}

	_renderGrid(items) {
		this._grid.innerHTML = '';
		if (!items.length) {
			this._grid.innerHTML = '<div class="nw-gallery-empty">No workflows found.</div>';
			return;
		}
		for (const item of items) {
			this._grid.appendChild(this._makeCard(item));
		}
	}

	_makeCard(item) {
		const card = document.createElement('div');
		card.className = 'nw-gallery-card';

		const title = document.createElement('div');
		title.className = 'nw-gallery-card-title';
		title.textContent = item.title || item.id;

		const desc = document.createElement('div');
		desc.className = 'nw-gallery-card-desc';
		desc.textContent = item.description || '';

		const footer = document.createElement('div');
		footer.className = 'nw-gallery-card-footer';

		const tags = document.createElement('div');
		tags.className = 'nw-gallery-card-tags';
		for (const tag of (item.tags || []).slice(0, 4)) {
			const t = document.createElement('span');
			t.className = 'nw-gallery-tag';
			t.textContent = tag;
			tags.appendChild(t);
		}

		const loadBtn = document.createElement('button');
		loadBtn.className = 'nw-gallery-load-btn';
		loadBtn.textContent = 'Load into Space';
		loadBtn.addEventListener('click', async () => {
			loadBtn.disabled = true;
			loadBtn.textContent = 'Loading...';
			try {
				const full = await this.api.galleryGet(item.id);
				if (full?.workflow) {
					await this._loadWorkflow(full.workflow, full.title || full.id);
					this.close();
				}
			} catch (err) {
				loadBtn.textContent = 'Error';
				setTimeout(() => { loadBtn.disabled = false; loadBtn.textContent = 'Load'; }, 2000);
			}
		});

		footer.appendChild(tags);
		footer.appendChild(loadBtn);
		card.appendChild(title);
		if (item.description) card.appendChild(desc);
		card.appendChild(footer);
		return card;
	}
}

// ========================================================================
// AppsManager
// ========================================================================

class AppsManager {
	constructor(serverUrl, api, getWorkflowFn) {
		this.serverUrl    = serverUrl;
		this.api          = api;
		this._getWorkflow = getWorkflowFn;  // returns { name, workflow } for the current space/canvas
		this._open        = false;

		this._fab       = document.getElementById('appsToggleBtn');
		this._panel     = document.getElementById('appsPanel');
		this._closeBtn  = document.getElementById('appsCloseBtn');
		this._publishBtn = document.getElementById('appsPublishBtn');
		this._slugInput  = document.getElementById('appsSlugInput');
		this._titleInput = document.getElementById('appsTitleInput');
		this._list       = document.getElementById('appsList');

		this._setupUI();
	}

	_setupUI() {
		this._fab.addEventListener('click', () => this.toggle());
		this._closeBtn.addEventListener('click', () => this.close());
		this._publishBtn.addEventListener('click', () => this._publish());

		// Auto-fill slug from title
		this._titleInput.addEventListener('input', () => {
			if (!this._slugInput.dataset.manuallyEdited) {
				this._slugInput.value = this._titleInput.value
					.toLowerCase().replace(/\s+/g, '-').replace(/[^a-z0-9-]/g, '');
			}
		});
		this._slugInput.addEventListener('input', () => {
			this._slugInput.dataset.manuallyEdited = '1';
		});
	}

	toggle() { this._open ? this.close() : this.open(); }

	isOpen() { return !!this._open; }

	async open() {
		if (this._open) return;
		if (typeof window.closeNumelSidePanels === 'function') {
			window.closeNumelSidePanels(['apps']);
		}
		this._open = true;
		this._panel.classList.add('open');
		this._prefillFromCurrentWorkflow();
		await this._loadList();
	}

	close() {
		if (!this._open) return;
		this._open = false;
		this._panel.classList.remove('open');
	}

	_prefillFromCurrentWorkflow() {
		try {
			const { name } = this._getWorkflow();
			if (name) {
				this._titleInput.value = name;
				this._slugInput.value = name.toLowerCase().replace(/\s+/g, '-').replace(/[^a-z0-9-]/g, '');
				delete this._slugInput.dataset.manuallyEdited;
			}
		} catch { /* no workflow loaded */ }
	}

	async _publish() {
		const slug  = this._slugInput.value.trim();
		const title = this._titleInput.value.trim();
		if (!slug) { this._slugInput.focus(); return; }

		this._publishBtn.disabled = true;
		this._publishBtn.textContent = 'Publishing...';
		try {
			let workflowName = null;
			let workflow = null;
			try {
				const current = this._getWorkflow();
				workflowName = current?.name || null;
				workflow = current?.workflow || null;
			} catch {}
			await this.api.appsPublish({ slug, title: title || slug, workflow_name: workflowName, workflow });
			this._slugInput.value = '';
			this._titleInput.value = '';
			delete this._slugInput.dataset.manuallyEdited;
			await this._loadList();
		} catch (err) {
			this._setStatus(`Error: ${err.message}`, 'error');
		}
		this._publishBtn.disabled = false;
		this._publishBtn.textContent = 'Publish';
	}

	async _loadList() {
		this._list.innerHTML = '<div class="nw-apps-empty">Loading...</div>';
		try {
			const apps = await this.api.appsList();
			this._renderList(apps);
		} catch (err) {
			this._list.innerHTML = `<div class="nw-apps-empty">Failed to load: ${err.message}</div>`;
		}
	}

	_renderList(apps) {
		this._list.innerHTML = '';
		if (!apps.length) {
			this._list.innerHTML = '<div class="nw-apps-empty">No published apps yet.</div>';
			return;
		}
		// Build base URL (same host, different path)
		const base = this.serverUrl.replace(/\/$/, '');
		for (const app of apps) {
			this._list.appendChild(this._makeRow(app, base));
		}
	}

	_makeRow(app, base) {
		const row = document.createElement('div');
		row.className = 'nw-apps-row';

		const info = document.createElement('div');
		info.className = 'nw-apps-info';

		const name = document.createElement('div');
		name.className = 'nw-apps-name';
		name.textContent = app.name || app.slug;

		const url = document.createElement('a');
		url.className = 'nw-apps-url';
		url.href = `${base}/apps/${app.slug}`;
		url.target = '_blank';
		url.textContent = `/apps/${app.slug}`;

		info.appendChild(name);
		info.appendChild(url);

		const actions = document.createElement('div');
		actions.className = 'nw-apps-actions';

		const openBtn = document.createElement('button');
		openBtn.className = 'nw-apps-btn';
		openBtn.title = 'Open app';
		openBtn.innerHTML = '<svg viewBox="0 0 24 24"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>';
		openBtn.addEventListener('click', () => window.open(`${base}/apps/${app.slug}`, '_blank'));

		const removeBtn = document.createElement('button');
		removeBtn.className = 'nw-apps-btn danger';
		removeBtn.title = 'Unpublish';
		removeBtn.innerHTML = '<svg viewBox="0 0 24 24"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6"/><path d="M14 11v6"/></svg>';
		removeBtn.addEventListener('click', async () => {
			const ok = await NumelConfirm('Unpublish App', `Remove published app "${app.name || app.slug}"?`, 'Unpublish', true);
			if (!ok) return;
			removeBtn.disabled = true;
			try {
				await this.api.appsUnpublish(app.slug);
				row.remove();
				if (!this._list.children.length) {
					this._list.innerHTML = '<div class="nw-apps-empty">No published apps yet.</div>';
				}
			} catch { removeBtn.disabled = false; }
		});

		actions.appendChild(openBtn);
		actions.appendChild(removeBtn);
		row.appendChild(info);
		row.appendChild(actions);
		return row;
	}

	_setStatus(msg, type = 'info') {
		// Briefly show a status line below the publish form
		let el = document.getElementById('appsStatus');
		if (!el) {
			el = document.createElement('div');
			el.id = 'appsStatus';
			el.className = 'nw-apps-status';
			this._publishBtn.parentElement.after(el);
		}
		el.textContent = msg;
		el.className = `nw-apps-status ${type}`;
		clearTimeout(this._statusTimer);
		this._statusTimer = setTimeout(() => { el.textContent = ''; }, 3000);
	}
}

// ========================================================================
// EXPORTS
// ========================================================================

if (typeof window !== 'undefined') {
	window.GalleryManager = GalleryManager;
	window.AppsManager    = AppsManager;
}

console.log('[Numel] Gallery + apps managers loaded');
