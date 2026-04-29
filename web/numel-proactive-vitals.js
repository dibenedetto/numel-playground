/* ========================================================================
   PROACTIVE VITALS PANEL — Phase 3 M3.3
   Reads /proactive/vitals + /proactive/ledger and renders a compact
   health surface in the left sidebar. Auto-refresh every 5 s when the
   section is expanded; pauses when collapsed to avoid wasted polls.
   ======================================================================== */

console.log('[Numel] Loading proactive vitals panel...');

const PROACTIVE_VITALS_AUTO_KEY = 'numel_proactive_vitals_auto_v1';
const PROACTIVE_VITALS_INTERVAL_MS = 5000;

class ProactiveVitalsPanel {
	constructor(api) {
		this.api      = api;
		this._section = document.getElementById('proactiveVitalsSection');
		this._stats   = document.getElementById('proactiveVitalsStats');
		this._ledger  = document.getElementById('proactiveVitalsLedger');
		this._auto    = document.getElementById('proactiveVitalsAuto');
		this._refresh = document.getElementById('proactiveVitalsRefreshBtn');
		this._lastUpd = document.getElementById('proactiveVitalsLastUpdate');
		this._quarantineEl = document.getElementById('proactiveVitalsQuarantine');
		this._snapshotsEl  = document.getElementById('proactiveVitalsSnapshots');
		this._snapshotBtn  = document.getElementById('proactiveVitalsSnapshotBtn');
		this._snapshotLbl  = document.getElementById('proactiveVitalsSnapshotLabel');
		this._timer   = null;
		this._lastError = null;

		if (!this._section || !this._stats) {
			console.warn('[ProactiveVitals] section markup missing; skipping init.');
			return;
		}

		try {
			const stored = localStorage.getItem(PROACTIVE_VITALS_AUTO_KEY);
			if (stored !== null && this._auto) this._auto.checked = stored === '1';
		} catch {}

		this._refresh?.addEventListener('click', () => this.refresh());
		this._auto?.addEventListener('change', () => {
			try { localStorage.setItem(PROACTIVE_VITALS_AUTO_KEY, this._auto.checked ? '1' : '0'); } catch {}
			this._reschedule();
		});
		this._snapshotBtn?.addEventListener('click', () => this._takeSnapshot());

		// React to section collapse/expand to pause polling when hidden.
		const observer = new MutationObserver(() => this._reschedule());
		observer.observe(this._section, { attributes: true, attributeFilter: ['class'] });

		// First load — only run when not collapsed; otherwise wait for expand.
		this._reschedule();
	}

	_isVisible() {
		if (!this._section) return false;
		return !this._section.classList.contains('nw-section-collapsed');
	}

	_reschedule() {
		if (this._timer) {
			clearInterval(this._timer);
			this._timer = null;
		}
		if (!this._isVisible()) return;
		this.refresh();
		if (this._auto?.checked) {
			this._timer = setInterval(() => this.refresh(), PROACTIVE_VITALS_INTERVAL_MS);
		}
	}

	async refresh() {
		if (!this._stats) return;
		try {
			const [vitals, ledger, quarantine, snapshots] = await Promise.all([
				this.api.proactiveVitals(),
				this.api.proactiveLedger({ limit: 8 }),
				this.api.proactiveQuarantine(),
				this.api.proactiveSnapshots(),
			]);
			this._lastError = null;
			this._renderStats(vitals);
			this._renderLedger(ledger?.entries || []);
			this._renderQuarantine(quarantine?.keys || {});
			this._renderSnapshots(snapshots?.snapshots || []);
			if (this._lastUpd) {
				const t = new Date();
				this._lastUpd.textContent = t.toLocaleTimeString();
			}
		} catch (err) {
			this._lastError = err;
			this._renderError(err);
		}
	}

	_renderStats(v) {
		if (!v) {
			this._stats.innerHTML = '<div class="nw-vitals-empty">No data</div>';
			return;
		}
		const dec    = v.governor_decisions    || {};
		const motor  = v.motor_status_counts   || {};
		const topics = v.trigger_topics        || {};

		const cells = [
			{ label: 'Ledger entries',  value: v.ledger_count ?? 0 },
			{ label: 'Observations',    value: topics['core.sensory.observation'] ?? 0 },
			{ label: 'Action attempts', value: topics['core.motor.action_attempt'] ?? 0 },
			{ label: 'Allow',           value: dec.allow            ?? 0, kind: 'good' },
			{ label: 'Consent',         value: dec.consent_required ?? 0, kind: 'warn' },
			{ label: 'Deny',            value: dec.deny             ?? 0, kind: 'bad'  },
			{ label: 'Pending consent', value: v.consent_pending      ?? 0, kind: (v.consent_pending ? 'warn' : '') },
			{ label: 'Injection hits',  value: v.injection_hits_total ?? 0, kind: (v.injection_hits_total ? 'bad' : '') },
			{ label: 'Avg latency',     value: this._formatLatency(v.avg_pipeline_latency_s) },
			{ label: 'Motor: executed', value: motor.executed            ?? 0 },
			{ label: 'Motor: deferred', value: motor.deferred_to_social  ?? 0, kind: (motor.deferred_to_social ? 'warn' : '') },
			{ label: 'Motor: no action',value: motor.no_action           ?? 0 },
		];

		this._stats.innerHTML = cells.map((c) => `
			<div class="nw-vitals-cell ${c.kind ? 'nw-vitals-cell-' + c.kind : ''}">
				<div class="nw-vitals-cell-value">${this._escape(String(c.value))}</div>
				<div class="nw-vitals-cell-label">${this._escape(c.label)}</div>
			</div>`).join('');
	}

	_renderLedger(entries) {
		if (!this._ledger) return;
		if (!entries.length) {
			this._ledger.innerHTML = '<div class="nw-vitals-empty">No entries yet — start a proactive workflow.</div>';
			return;
		}
		this._ledger.innerHTML = entries.map((e) => {
			const verdict = (e.governor_verdict?.decision) || '—';
			const kind = verdict === 'deny' ? 'bad' : verdict === 'consent_required' ? 'warn' : verdict === 'allow' ? 'good' : '';
			const topic = e.trigger?.topic || '—';
			const motor = e.motor_status ? ` · motor: ${this._escape(e.motor_status)}` : '';
			const obs   = e.observation ? ` · ${this._escape(e.observation.subject || e.observation.observation_type || '')}` : '';
			const capName = e.intent?.capability || e.resolved_capability?.name;
			const intent  = capName ? ` · intent: ${this._escape(capName)}` : '';
			const conf = e.governor_verdict?.confidence != null ? ` · conf=${e.governor_verdict.confidence.toFixed(2)}` : '';
			return `
				<div class="nw-vitals-ledger-row">
					<span class="nw-vitals-ledger-id">${this._escape(e.id || '')}</span>
					<span class="nw-vitals-ledger-verdict ${kind ? 'nw-vitals-verdict-' + kind : ''}">${this._escape(verdict)}</span>
					<span class="nw-vitals-ledger-topic">${this._escape(topic)}${obs}${intent}${motor}${conf}</span>
				</div>`;
		}).join('');
	}

	_renderQuarantine(keys) {
		if (!this._quarantineEl) return;
		const entries = Object.entries(keys || {});
		const quarantined = entries.filter(([_, v]) => v && v.quarantined);
		if (!quarantined.length) {
			this._quarantineEl.innerHTML = '<div class="nw-vitals-empty">No keys quarantined.</div>';
			return;
		}
		this._quarantineEl.innerHTML = quarantined.map(([key, v]) => {
			const reason = this._escape(v.quarantined_reason || '—');
			const since  = v.quarantined_at ? new Date(v.quarantined_at * 1000).toLocaleString() : '';
			return `
				<div class="nw-vitals-quarantine-row">
					<span class="nw-vitals-quarantine-key" title="${this._escape(since)}">${this._escape(key)}</span>
					<span class="nw-vitals-quarantine-reason">${reason}</span>
					<button class="nw-btn nw-btn-sm nw-btn-secondary" data-release="${this._escape(key)}">Release</button>
				</div>`;
		}).join('');
		this._quarantineEl.querySelectorAll('button[data-release]').forEach((btn) => {
			btn.addEventListener('click', () => this._releaseKey(btn.getAttribute('data-release')));
		});
	}

	async _releaseKey(key) {
		if (!key) return;
		try {
			await this.api.proactiveQuarantineRelease(key, 'released from Vitals panel');
			await this.refresh();
		} catch (err) {
			this._renderError(err);
		}
	}

	_renderSnapshots(snapshots) {
		if (!this._snapshotsEl) return;
		if (!snapshots.length) {
			this._snapshotsEl.innerHTML = '<div class="nw-vitals-empty">No snapshots taken yet.</div>';
			return;
		}
		this._snapshotsEl.innerHTML = snapshots.map((s) => {
			const created = s.created_at ? new Date(s.created_at * 1000).toLocaleString() : '';
			const label   = s.label ? ` · ${this._escape(s.label)}` : '';
			const files   = (s.files || []).length;
			return `
				<div class="nw-vitals-snapshot-row">
					<span class="nw-vitals-snapshot-id">${this._escape(s.id || '')}</span>
					<span class="nw-vitals-snapshot-meta">${this._escape(created)}${label} · ${files} file${files === 1 ? '' : 's'}</span>
					<span class="nw-vitals-snapshot-actions">
						<button class="nw-btn nw-btn-sm nw-btn-secondary" data-restore="${this._escape(s.id)}">Restore</button>
						<button class="nw-btn nw-btn-sm nw-btn-secondary" data-delete="${this._escape(s.id)}">Delete</button>
					</span>
				</div>`;
		}).join('');
		this._snapshotsEl.querySelectorAll('button[data-restore]').forEach((btn) => {
			btn.addEventListener('click', () => this._restoreSnapshot(btn.getAttribute('data-restore')));
		});
		this._snapshotsEl.querySelectorAll('button[data-delete]').forEach((btn) => {
			btn.addEventListener('click', () => this._deleteSnapshot(btn.getAttribute('data-delete')));
		});
	}

	async _takeSnapshot() {
		const label = (this._snapshotLbl?.value || '').trim();
		try {
			this._snapshotBtn.disabled = true;
			await this.api.proactiveSnapshotTake(label);
			if (this._snapshotLbl) this._snapshotLbl.value = '';
			await this.refresh();
		} catch (err) {
			this._renderError(err);
		} finally {
			if (this._snapshotBtn) this._snapshotBtn.disabled = false;
		}
	}

	async _restoreSnapshot(id) {
		if (!id) return;
		const ok = window.confirm(`Restore snapshot "${id}"? Current state files will be overwritten.`);
		if (!ok) return;
		try {
			await this.api.proactiveSnapshotRestore(id);
			await this.refresh();
		} catch (err) {
			this._renderError(err);
		}
	}

	async _deleteSnapshot(id) {
		if (!id) return;
		const ok = window.confirm(`Delete snapshot "${id}"? This cannot be undone.`);
		if (!ok) return;
		try {
			await this.api.proactiveSnapshotDelete(id);
			await this.refresh();
		} catch (err) {
			this._renderError(err);
		}
	}

	_renderError(err) {
		const msg = err?.message || String(err);
		this._stats.innerHTML  = `<div class="nw-vitals-error">Vitals unavailable: ${this._escape(msg)}</div>`;
		this._ledger.innerHTML = '';
	}

	_formatLatency(s) {
		const v = Number(s) || 0;
		if (v < 0.001) return '< 1 ms';
		if (v < 1)     return `${(v * 1000).toFixed(0)} ms`;
		return `${v.toFixed(2)} s`;
	}

	_escape(s) {
		return String(s ?? '').replace(/[&<>"']/g, (c) => ({
			'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
		}[c]));
	}
}

window.ProactiveVitalsPanel = ProactiveVitalsPanel;
