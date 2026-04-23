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
		this._items = [];

		this._fab     = document.getElementById('galleryToggleBtn');
		this._panel   = document.getElementById('galleryPanel');
		this._closeBtn = document.getElementById('galleryCloseBtn');
		this._searchInput = document.getElementById('gallerySearch');
		this._filterSelect = document.getElementById('galleryDiscoveryFilter');
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
		this._filterSelect?.addEventListener('change', () => this._renderGrid(this._items));
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
			this._items = await this.api.galleryList({
				category: this._activeCategory || undefined,
				search: this._searchInput.value.trim() || undefined,
			});
			this._renderGrid(this._items);
		} catch (err) {
			this._grid.innerHTML = `<div class="nw-gallery-empty">Failed to load: ${err.message}</div>`;
		}
	}

	_matchesDiscoveryFilter(item) {
		const filter = String(this._filterSelect?.value || 'all').trim().toLowerCase();
		const provenance = item?.provenance || {};
		switch (filter) {
			case 'featured': return !!provenance.featured;
			case 'curated': return !!provenance.curated;
			case 'repo': return !!provenance.repo_backed;
			case 'public': return !!provenance.public_source;
			case 'builtin': return String(item?.author || '').trim().toLowerCase() === 'system';
			case 'community': return String(item?.author || '').trim().toLowerCase() !== 'system';
			default: return true;
		}
	}

	_renderGrid(items) {
		this._grid.innerHTML = '';
		const visibleItems = Array.isArray(items) ? items.filter((item) => this._matchesDiscoveryFilter(item)) : [];
		if (!Array.isArray(items) || !items.length) {
			this._grid.innerHTML = '<div class="nw-gallery-empty">No workflows found.</div>';
			return;
		}
		if (!visibleItems.length) {
			this._grid.innerHTML = '<div class="nw-gallery-empty">No workflows match the current gallery filter.</div>';
			return;
		}
		for (const item of visibleItems) {
			this._grid.appendChild(this._makeCard(item));
		}
	}

	_cardBadges(item) {
		const provenance = item?.provenance || {};
		const badges = [];
		if (provenance.featured) badges.push('<span class="nw-gallery-badge nw-gallery-badge-featured">Featured</span>');
		else if (provenance.curated) badges.push('<span class="nw-gallery-badge nw-gallery-badge-curated">Curated</span>');
		if (provenance.repo_backed) badges.push('<span class="nw-gallery-badge nw-gallery-badge-repo">Repo-backed</span>');
		if (provenance.public_source) badges.push('<span class="nw-gallery-badge nw-gallery-badge-public">Public Source</span>');
		if (String(item?.author || '').trim().toLowerCase() === 'system') {
			badges.push('<span class="nw-gallery-badge nw-gallery-badge-system">Built-in</span>');
		}
		return badges.join('');
	}

	_formatDate(ts) {
		const value = Number(ts || 0);
		if (!Number.isFinite(value) || value <= 0) return '';
		try {
			return new Date(value * 1000).toLocaleDateString(undefined, {
				year: 'numeric',
				month: 'short',
				day: 'numeric',
			});
		} catch {
			return '';
		}
	}

	_sourceRepoInfo(item) {
		const source = item?.metadata?.source || {};
		const namespace = String(source.namespace || '').trim();
		const slug = String(source.slug || '').trim();
		const namespaceSlug = String(source.namespace_slug || '').trim();
		const isPublic = !!source.is_public || String(source.visibility || '').trim().toLowerCase() === 'public';
		if (!isPublic) return null;
		if (namespace && slug) {
			return {
				namespace,
				slug,
				ref: String(source.ref || '').trim() || null,
				assetPath: String(source.asset_path || '').trim() || 'workflow.json',
			};
		}
		const parts = namespaceSlug.split('/').map((part) => String(part || '').trim()).filter(Boolean);
		if (parts.length >= 2) {
			return {
				namespace: parts[0],
				slug: parts.slice(1).join('/'),
				ref: String(source.ref || '').trim() || null,
				assetPath: String(source.asset_path || '').trim() || 'workflow.json',
			};
		}
		return null;
	}

	_sourceSummary(item) {
		const provenanceLabel = String(item?.provenance?.source_label || '').trim();
		if (provenanceLabel) {
			return `Source: ${provenanceLabel}`;
		}
		const source = item?.metadata?.source || {};
		const sourceType = String(source.type || '').trim().toLowerCase();
		if (!sourceType) return '';
		const locator = String(source.namespace_slug || '').trim();
		const assetPath = String(source.asset_path || '').trim();
		if (sourceType === 'commit') {
			const commitId = String(source.commit_id || '').trim();
			return locator
				? `Curated from ${locator}${commitId ? ` @ ${commitId.slice(0, 8)}` : ''}${assetPath ? ` · ${assetPath}` : ''}`
				: `Curated from snapshot${commitId ? ` ${commitId.slice(0, 8)}` : ''}${assetPath ? ` · ${assetPath}` : ''}`;
		}
		const ref = String(source.ref || source.active_ref || '').trim();
		return locator
			? `Curated from ${locator}${ref ? ` @ ${ref}` : ''}${assetPath ? ` · ${assetPath}` : ''}`
			: `Curated from ${sourceType === 'canvas' ? 'canvas state' : 'repo ref'}${ref ? ` ${ref}` : ''}${assetPath ? ` · ${assetPath}` : ''}`;
	}

	async _openSourceRepo(item, button) {
		const sourceRepo = this._sourceRepoInfo(item);
		if (!sourceRepo) return;
		button.disabled = true;
		const previousLabel = button.textContent;
		button.textContent = 'Opening...';
		try {
			if (typeof window.openPublicHub !== 'function') {
				throw new Error('Public Hub is not ready yet');
			}
			await window.openPublicHub({
				mode: 'repo',
				namespace: sourceRepo.namespace,
				slug: sourceRepo.slug,
				ref: sourceRepo.ref,
			});
			this.close();
		} catch (err) {
			button.textContent = 'Error';
			setTimeout(() => {
				button.disabled = false;
				button.textContent = previousLabel;
			}, 2000);
			return;
		}
	}

	async _openCreator(item, button) {
		const creator = String(item?.author || '').trim();
		if (!creator) return;
		button.disabled = true;
		const previousLabel = button.textContent;
		button.textContent = 'Opening...';
		try {
			if (typeof window.openPublicHub !== 'function') {
				throw new Error('Public Hub is not ready yet');
			}
			await window.openPublicHub({
				mode: 'creator',
				creator,
			});
			this.close();
		} catch (err) {
			button.textContent = 'Error';
			setTimeout(() => {
				button.disabled = false;
				button.textContent = previousLabel;
			}, 2000);
			return;
		}
	}

	_makeCard(item) {
		const card = document.createElement('div');
		card.className = 'nw-gallery-card';
		const sourceSummary = this._sourceSummary(item);
		const sourceRepo = this._sourceRepoInfo(item);
		const provenance = item?.provenance || {};
		const author = String(item?.author || '').trim();
		const versionLabel = String(provenance.version_label || '').trim();
		const publishedDate = this._formatDate(item?.created_at);
		const metaParts = [
			author || 'Unknown creator',
			versionLabel ? `Version ${versionLabel}` : '',
			publishedDate ? `Published ${publishedDate}` : '',
		].filter(Boolean).join(' · ');

		const title = document.createElement('div');
		title.className = 'nw-gallery-card-title';
		title.textContent = item.title || item.id;

		const badges = document.createElement('div');
		badges.className = 'nw-gallery-card-badges';
		badges.innerHTML = this._cardBadges(item);

		const meta = document.createElement('div');
		meta.className = 'nw-gallery-card-meta';
		meta.textContent = metaParts;

		const desc = document.createElement('div');
		desc.className = 'nw-gallery-card-desc';
		desc.textContent = item.description || '';

		const source = document.createElement('div');
		source.className = 'nw-gallery-card-source';
		source.textContent = sourceSummary;

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

		const actions = document.createElement('div');
		actions.className = 'nw-gallery-card-actions';

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
				setTimeout(() => { loadBtn.disabled = false; loadBtn.textContent = 'Load into Space'; }, 2000);
			}
		});

		actions.appendChild(loadBtn);
		if (item.author && String(item.author).trim().toLowerCase() !== 'system') {
			const creatorBtn = document.createElement('button');
			creatorBtn.className = 'nw-gallery-source-btn';
			creatorBtn.textContent = 'View Creator';
			creatorBtn.addEventListener('click', async () => {
				await this._openCreator(item, creatorBtn);
			});
			actions.appendChild(creatorBtn);
		}
		if (sourceRepo) {
			const sourceBtn = document.createElement('button');
			sourceBtn.className = 'nw-gallery-source-btn';
			sourceBtn.textContent = 'View Source Repo';
			sourceBtn.addEventListener('click', async () => {
				await this._openSourceRepo(item, sourceBtn);
			});
			actions.appendChild(sourceBtn);
		}

		footer.appendChild(tags);
		footer.appendChild(actions);
		card.appendChild(title);
		if (badges.innerHTML) card.appendChild(badges);
		if (meta.textContent) card.appendChild(meta);
		if (item.description) card.appendChild(desc);
		if (sourceSummary) card.appendChild(source);
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
		this._descriptionInput = document.getElementById('appsDescriptionInput');
		this._modelSourceSelect = document.getElementById('appsModelSourceSelect');
		this._modelNameInput = document.getElementById('appsModelNameInput');
		this._temperatureInput = document.getElementById('appsTemperatureInput');
		this._maxTokensInput = document.getElementById('appsMaxTokensInput');
		this._pagePromptInput = document.getElementById('appsPagePromptInput');
		this._advancedToggle = document.getElementById('appsAdvancedToggle');
		this._advancedBody = document.getElementById('appsAdvancedBody');
		this._cancelBtn = document.getElementById('appsCancelBtn');
		this._statusEl = document.getElementById('appsStatus');
		this._list       = document.getElementById('appsList');
		this._modelNames = [];
		this._fallbackModelSources = ['ollama', 'openai', 'anthropic'];
		this._fallbackModelNamesBySource = {
			ollama: ['qwen3.5:cloud', 'mistral', 'llama3', 'qwen2.5'],
			openai: ['gpt-4o-mini', 'gpt-4o'],
			anthropic: ['claude-sonnet-4-20250514'],
		};
		this._modelSourcesLoaded = false;
		this._publishAbortController = null;
		this._publishing = false;

		this._setupUI();
	}

	_setupUI() {
		this._fab.addEventListener('click', () => this.toggle());
		this._closeBtn.addEventListener('click', () => this.close());
		this._publishBtn.addEventListener('click', () => this._publish());
		this._cancelBtn?.addEventListener('click', () => this._cancelPublish());
		this._advancedToggle?.addEventListener('click', () => this._toggleAdvanced());

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
		this._modelSourceSelect?.addEventListener('change', () => {
			this._loadModelNamesForSource(this._modelSourceSelect.value);
		});
	}

	_toggleAdvanced(forceExpanded = null) {
		if (!this._advancedToggle || !this._advancedBody) return;
		const nextExpanded = typeof forceExpanded === 'boolean'
			? forceExpanded
			: this._advancedToggle.getAttribute('aria-expanded') !== 'true';
		this._advancedToggle.setAttribute('aria-expanded', nextExpanded ? 'true' : 'false');
		this._advancedBody.style.display = nextExpanded ? '' : 'none';
	}

	_normalizeOptionValues(items) {
		if (!Array.isArray(items)) return [];
		return items
			.map((item) => {
				if (typeof item === 'string') return item.trim();
				if (item && typeof item === 'object') {
					return String(item.value ?? item.name ?? item.id ?? '').trim();
				}
				return '';
			})
			.filter(Boolean);
	}

	_setSelectOptions(selectEl, values) {
		if (!selectEl) return;
		const previous = String(selectEl.value || '').trim();
		selectEl.innerHTML = '';
		for (const value of values) {
			const opt = document.createElement('option');
			opt.value = value;
			opt.textContent = value;
			selectEl.appendChild(opt);
		}
		if (previous && values.includes(previous)) {
			selectEl.value = previous;
		} else if (values.length) {
			selectEl.value = values[0];
		}
	}

	_fallbackModelNames(source) {
		return [...(this._fallbackModelNamesBySource[source] || this._fallbackModelNamesBySource.ollama)];
	}

	async _loadModelNamesForSource(source) {
		const normalizedSource = String(source || '').trim().toLowerCase() || 'ollama';
		try {
			const response = await this.api.options('published_app_model_names', { source: normalizedSource });
			const names = this._normalizeOptionValues(response?.options);
			this._modelNames = names.length ? names : this._fallbackModelNames(normalizedSource);
			this._setSelectOptions(this._modelNameInput, this._modelNames);
			if (!names.length) {
				this._setStatus(`Model names for ${normalizedSource} were empty, using defaults.`, 'info');
			}
		} catch (err) {
			this._modelNames = this._fallbackModelNames(normalizedSource);
			this._setSelectOptions(this._modelNameInput, this._modelNames);
			this._setStatus(`Model names unavailable for ${normalizedSource}, using defaults: ${err.message}`, 'error');
		}
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
		await this._ensureGenerationOptions();
		this._prefillFromCurrentWorkflow();
		await this._loadList();
	}

	close() {
		if (!this._open) return;
		if (this._publishing) this._cancelPublish();
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

	async _ensureGenerationOptions() {
		if (this._modelSourcesLoaded) return;
		try {
			const sourcesResp = await this.api.options('published_app_model_sources');
			const sources = this._normalizeOptionValues(sourcesResp?.options);
			if (!sources.length) {
				this._setStatus('Model sources were empty, using defaults.', 'info');
			}
			this._setSelectOptions(this._modelSourceSelect, sources.length ? sources : this._fallbackModelSources);
			await this._loadModelNamesForSource(this._modelSourceSelect.value);
			this._modelSourcesLoaded = true;
		} catch (err) {
			this._setSelectOptions(this._modelSourceSelect, this._fallbackModelSources);
			await this._loadModelNamesForSource(this._modelSourceSelect.value || 'ollama');
			this._modelSourcesLoaded = true;
			this._setStatus(`Model options unavailable, using defaults: ${err.message}`, 'error');
		}
	}

	async _publish() {
		const slug  = this._slugInput.value.trim();
		const title = this._titleInput.value.trim();
		const description = this._descriptionInput.value.trim();
		if (!slug) { this._slugInput.focus(); return; }

		const temperatureRaw = this._temperatureInput.value.trim();
		const maxTokensRaw = this._maxTokensInput.value.trim();
		const pageGeneration = {
			model_source: this._modelSourceSelect.value || 'ollama',
			model_name: this._modelNameInput.value || 'qwen3.5:cloud',
			page_prompt: this._pagePromptInput.value.trim(),
		};
		if (temperatureRaw !== '') pageGeneration.temperature = Number(temperatureRaw);
		if (maxTokensRaw !== '') pageGeneration.max_tokens = Number(maxTokensRaw);

		this._publishAbortController = new AbortController();
		this._setPublishingState(true);
		this._setStatus('Generating published app…', 'thinking', { sticky: true });
		try {
			let workflow = null;
			try {
				const current = this._getWorkflow();
				workflow = current?.workflow || null;
			} catch {}
			if (!workflow) {
				throw new Error('No current workflow is available to publish');
			}
			await this.api.appsPublish({
				slug,
				title: title || slug,
				description,
				workflow,
				page_generation: pageGeneration,
			}, { signal: this._publishAbortController.signal });
			this._slugInput.value = '';
			this._titleInput.value = '';
			this._descriptionInput.value = '';
			this._temperatureInput.value = '';
			this._maxTokensInput.value = '';
			this._pagePromptInput.value = '';
			delete this._slugInput.dataset.manuallyEdited;
			await this._loadList();
			this._setStatus('Published app generated.', 'success');
		} catch (err) {
			if (err?.name === 'AbortError') {
				this._setStatus('Generation cancelled.', 'info');
			} else {
				this._setStatus(`Error: ${err.message}`, 'error');
			}
		}
		this._publishAbortController = null;
		this._setPublishingState(false);
	}

	_cancelPublish() {
		if (!this._publishAbortController) return;
		this._publishAbortController.abort();
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
		url.href = `${base}/apps/${app.owner_username}/${app.slug}`;
		url.target = '_blank';
		url.textContent = `/apps/${app.owner_username}/${app.slug}`;

		const meta = document.createElement('div');
		meta.className = 'nw-apps-meta';
		meta.textContent = app.generated_summary || app.description || 'Generated published app';

		info.appendChild(name);
		info.appendChild(url);
		info.appendChild(meta);

		const actions = document.createElement('div');
		actions.className = 'nw-apps-actions';

		const openBtn = document.createElement('button');
		openBtn.className = 'nw-apps-btn';
		openBtn.title = 'Open app';
		openBtn.innerHTML = '<svg viewBox="0 0 24 24"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>';
		openBtn.addEventListener('click', () => window.open(`${base}/apps/${app.owner_username}/${app.slug}`, '_blank'));

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

	_setPublishingState(isPublishing) {
		this._publishing = !!isPublishing;
		this._publishBtn.disabled = this._publishing;
		this._publishBtn.textContent = this._publishing
			? 'Generating Published App...'
			: 'Generate and Publish Current Workflow';
		if (this._cancelBtn) this._cancelBtn.style.display = this._publishing ? '' : 'none';
	}

	_setStatus(msg, type = 'info', options = {}) {
		const el = this._statusEl;
		if (!el) return;
		const sticky = !!options.sticky;
		el.textContent = msg;
		el.className = `nw-apps-status ${type === 'thinking' ? 'info is-thinking' : type}`;
		clearTimeout(this._statusTimer);
		if (!sticky) {
			this._statusTimer = setTimeout(() => {
				el.textContent = '';
				el.className = 'nw-apps-status';
			}, 3000);
		}
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
