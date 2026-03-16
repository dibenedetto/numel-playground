/* ========================================================================
   NUMEL GALLERY
   Workflow Gallery / Marketplace UI.
   Browse, search, install, and publish workflow templates.
   ======================================================================== */

console.log('[Numel] Loading gallery...');

class GalleryManager {
	constructor(api, loadWorkflowFn) {
		this.api            = api;             // NumelAPI instance
		this.loadWorkflow   = loadWorkflowFn;  // function(workflowJson) to load into editor
		this._open          = false;
		this._items         = [];
		this._categories    = [];

		// DOM elements
		this.panel          = document.getElementById('galleryPanel');
		this.grid           = document.getElementById('galleryGrid');
		this.searchInput    = document.getElementById('gallerySearch');
		this.categorySelect = document.getElementById('galleryCategory');
		this.countSpan      = document.getElementById('galleryCount');
		this.toggleBtn      = document.getElementById('galleryToggleBtn');
		this.closeBtn       = document.getElementById('galleryCloseBtn');

		this._bindEvents();
	}

	// ── Lifecycle ────────────────────────────────────────────────

	toggle() {
		this._open ? this.close() : this.open();
	}

	async open() {
		this._open = true;
		this.panel.style.display = '';
		await this._refresh();
	}

	close() {
		this._open = false;
		this.panel.style.display = 'none';
	}

	// ── Data ─────────────────────────────────────────────────────

	async _refresh() {
		try {
			const [items, cats] = await Promise.all([
				this.api.galleryList({
					search:   this.searchInput.value || null,
					category: this.categorySelect.value || null,
				}),
				this.api.galleryCategories(),
			]);
			this._items      = items;
			this._categories = cats;
			this._renderCategories();
			this._renderGrid();
		} catch (e) {
			this.grid.innerHTML = `<div class="nw-gallery-empty">Failed to load gallery: ${e.message}</div>`;
		}
	}

	// ── Rendering ────────────────────────────────────────────────

	_renderCategories() {
		const current = this.categorySelect.value;
		this.categorySelect.innerHTML = '<option value="">All categories</option>';
		for (const cat of this._categories) {
			const opt = document.createElement('option');
			opt.value = cat.category;
			opt.textContent = `${cat.category} (${cat.count})`;
			this.categorySelect.appendChild(opt);
		}
		this.categorySelect.value = current;
	}

	_renderGrid() {
		this.countSpan.textContent = `(${this._items.length})`;

		if (!this._items.length) {
			this.grid.innerHTML = '<div class="nw-gallery-empty">No workflows found. Publish one to get started!</div>';
			return;
		}

		this.grid.innerHTML = '';
		for (const item of this._items) {
			const card = document.createElement('div');
			card.className = 'nw-gallery-card';
			if (item.featured) card.classList.add('featured');

			const tags = item.tags.map(t => `<span class="nw-gallery-tag">${t}</span>`).join('');

			card.innerHTML = `
				<div class="nw-gallery-card-header">
					<span class="nw-gallery-card-name">${this._esc(item.name)}</span>
					<span class="nw-gallery-card-category">${item.category}</span>
				</div>
				<div class="nw-gallery-card-desc">${this._esc(item.description || 'No description')}</div>
				<div class="nw-gallery-card-meta">
					<span>${item.node_count} nodes, ${item.edge_count} edges</span>
					<span>${item.downloads} downloads</span>
				</div>
				<div class="nw-gallery-card-tags">${tags}</div>
				<div class="nw-gallery-card-footer">
					<span class="nw-gallery-card-author">${this._esc(item.author || 'Anonymous')}</span>
					<button class="nw-gallery-card-install" data-id="${item.id}">Install</button>
				</div>
			`;

			card.querySelector('.nw-gallery-card-install').addEventListener('click', () => this._install(item.id));
			this.grid.appendChild(card);
		}
	}

	async _install(itemId) {
		try {
			const item = await this.api.galleryGet(itemId);
			if (item.error) throw new Error(item.error);
			if (item.workflow && this.loadWorkflow) {
				this.loadWorkflow(item.workflow);
				this.close();
			}
		} catch (e) {
			alert(`Failed to install workflow: ${e.message}`);
		}
	}

	// ── Publish ──────────────────────────────────────────────────

	async publish(name, description, workflow, author, tags, category) {
		try {
			const result = await this.api.galleryPublish({
				name, description, workflow, author,
				tags: tags || [], category: category || 'general',
			});
			if (this._open) await this._refresh();
			return result;
		} catch (e) {
			console.error('Gallery publish failed:', e);
			throw e;
		}
	}

	// ── Events ───────────────────────────────────────────────────

	_bindEvents() {
		if (this.toggleBtn) this.toggleBtn.addEventListener('click', () => this.toggle());
		if (this.closeBtn)  this.closeBtn.addEventListener('click',  () => this.close());

		if (this.searchInput) {
			let timer;
			this.searchInput.addEventListener('input', () => {
				clearTimeout(timer);
				timer = setTimeout(() => this._refresh(), 300);
			});
		}

		if (this.categorySelect) {
			this.categorySelect.addEventListener('change', () => this._refresh());
		}
	}

	_esc(str) {
		const div = document.createElement('div');
		div.textContent = str;
		return div.innerHTML;
	}
}

// ── Export ────────────────────────────────────────────────────────

if (typeof window !== 'undefined') {
	window.GalleryManager = GalleryManager;
}

console.log('[Numel] Gallery loaded');
