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
		this._candidatesEl = document.getElementById('proactiveVitalsCandidates');
		this._proposeBtn   = document.getElementById('proactiveVitalsProposeBtn');
		this._candidates   = [];
		this._mcpEl        = document.getElementById('proactiveVitalsMcp');
		this._mcpRefreshBtn = document.getElementById('proactiveVitalsMcpRefreshBtn');
		this._a2aEl        = document.getElementById('proactiveVitalsA2a');
		this._a2aRefreshBtn = document.getElementById('proactiveVitalsA2aRefreshBtn');
		this._transportsEl = document.getElementById('proactiveVitalsTransports');
		this._transportsRefreshBtn = document.getElementById('proactiveVitalsTransportsRefreshBtn');
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
		this._proposeBtn?.addEventListener('click', () => this._propose());
		this._mcpRefreshBtn?.addEventListener('click', () => this._refreshMcp());
		this._a2aRefreshBtn?.addEventListener('click', () => this._refreshA2a());
		this._transportsRefreshBtn?.addEventListener('click', () => this._refreshTransports());

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
			const [vitals, ledger, quarantine, snapshots,
			       mcpTools, mcpRemote, mcpCalls,
			       a2aPeers, a2aInbox, a2aOutbox, a2aShared,
			       transports, transportCalls] = await Promise.all([
				this.api.proactiveVitals(),
				this.api.proactiveLedger({ limit: 8 }),
				this.api.proactiveQuarantine(),
				this.api.proactiveSnapshots(),
				this.api.proactiveMcpTools(),
				this.api.proactiveMcpRemoteTools(),
				this.api.proactiveMcpCalls(5),
				this.api.proactiveA2aPeers(),
				this.api.proactiveA2aInbox(5),
				this.api.proactiveA2aOutbox(5),
				this.api.proactiveA2aShared(5),
				this.api.proactiveTransports(),
				this.api.proactiveTransportsCalls(5),
			]);
			this._lastError = null;
			this._renderStats(vitals);
			this._renderLedger(ledger?.entries || []);
			this._renderQuarantine(quarantine?.keys || {});
			this._renderSnapshots(snapshots?.snapshots || []);
			this._renderCandidates(this._candidates);
			this._renderMcp(mcpTools?.tools || [], mcpRemote?.remote_tools || [], mcpCalls?.entries || []);
			this._renderA2a(a2aPeers?.peers || [], a2aInbox?.entries || [], a2aOutbox?.entries || [], a2aShared?.entries || []);
			this._renderTransports(transports?.transports || [], transportCalls?.entries || []);
			if (this._lastUpd) {
				const t = new Date();
				this._lastUpd.textContent = t.toLocaleTimeString();
			}
		} catch (err) {
			this._lastError = err;
			this._renderError(err);
		}
	}

	async _refreshMcp() {
		// Manual force-refresh of the MCP panel (button under the subhead).
		if (this._mcpRefreshBtn) this._mcpRefreshBtn.disabled = true;
		try {
			await this.refresh();
		} finally {
			if (this._mcpRefreshBtn) this._mcpRefreshBtn.disabled = false;
		}
	}

	async _refreshA2a() {
		if (this._a2aRefreshBtn) this._a2aRefreshBtn.disabled = true;
		try {
			await this.refresh();
		} finally {
			if (this._a2aRefreshBtn) this._a2aRefreshBtn.disabled = false;
		}
	}

	async _refreshTransports() {
		if (this._transportsRefreshBtn) this._transportsRefreshBtn.disabled = true;
		try {
			await this.refresh();
		} finally {
			if (this._transportsRefreshBtn) this._transportsRefreshBtn.disabled = false;
		}
	}

	_renderTransports(transports, calls) {
		if (!this._transportsEl) return;
		if (!transports.length && !calls.length) {
			this._transportsEl.innerHTML = '<div class="nw-vitals-empty">No LLM transports registered.</div>';
			return;
		}
		const tList = transports.map((t) => `<code>${this._escape(t.alias)}</code><sup>${this._escape(t.kind || '')}</sup>`).join(' · ');
		const callRows = calls.slice(0, 4).map((c) => {
			const ok  = c?.response?.ok;
			const err = c?.response?.error || (c?.dry_run ? 'dry-run' : 'ok');
			const cls = ok ? 'good' : (err === 'alignment_veto' ? 'bad' : 'warn');
			return `
				<div class="nw-vitals-mcp-call">
					<span class="nw-vitals-mcp-call-tool">${this._escape(c.alias || '')}</span>
					<span class="nw-vitals-mcp-call-status nw-vitals-verdict-${cls}">${this._escape(err)}</span>
				</div>`;
		}).join('');
		this._transportsEl.innerHTML = `
			<div class="nw-vitals-mcp-row">
				<span class="nw-vitals-mcp-label">Bridges</span>
				<span class="nw-vitals-mcp-count">${transports.length}</span>
				<span class="nw-vitals-mcp-detail">${tList || '—'}</span>
			</div>
			<div class="nw-vitals-mcp-row nw-vitals-mcp-calls">
				<span class="nw-vitals-mcp-label">Recent calls</span>
				<span class="nw-vitals-mcp-detail">${callRows || '<em>none</em>'}</span>
			</div>`;
	}

	_renderA2a(peers, inbox, outbox, shared) {
		if (!this._a2aEl) return;
		if (!peers.length && !inbox.length && !outbox.length && !shared.length) {
			this._a2aEl.innerHTML = '<div class="nw-vitals-empty">No federated activity yet.</div>';
			return;
		}
		const peerRows = peers.map((p) => `<span class="nw-vitals-a2a-peer nw-vitals-a2a-tier-${this._escape(p.tier || '')}">${this._escape(p.peer_id)}<sup>${this._escape(p.tier || '')}</sup></span>`).join(' ');
		const inboxRows = inbox.slice(0, 3).map((m) => {
			const cls = m.accepted ? 'good' : (m.reason === 'adversarial' ? 'bad' : 'warn');
			return `
				<div class="nw-vitals-mcp-call">
					<span class="nw-vitals-mcp-call-tool">${this._escape(m.peer_id || '')} · ${this._escape(m.kind || '')}</span>
					<span class="nw-vitals-mcp-call-status nw-vitals-verdict-${cls}">${this._escape(m.reason || '')}</span>
				</div>`;
		}).join('');
		const sharedRows = shared.slice(0, 3).map((s) => {
			const ns = (s.namespaces || []).join(', ');
			const ref = s.refused?.length ? ` · refused: ${s.refused.length}` : '';
			return `
				<div class="nw-vitals-mcp-call">
					<span class="nw-vitals-mcp-call-tool">${this._escape(s.peer_id || '')} <i>(${this._escape(s.tier || '')})</i></span>
					<span class="nw-vitals-mcp-call-status">${this._escape(ns)}${this._escape(ref)}</span>
				</div>`;
		}).join('');
		this._a2aEl.innerHTML = `
			<div class="nw-vitals-mcp-row">
				<span class="nw-vitals-mcp-label">Peers</span>
				<span class="nw-vitals-mcp-count">${peers.length}</span>
				<span class="nw-vitals-mcp-detail">${peerRows || '—'}</span>
			</div>
			<div class="nw-vitals-mcp-row">
				<span class="nw-vitals-mcp-label">Inbox</span>
				<span class="nw-vitals-mcp-count">${inbox.length}</span>
				<span class="nw-vitals-mcp-detail">${inboxRows || '<em>—</em>'}</span>
			</div>
			<div class="nw-vitals-mcp-row">
				<span class="nw-vitals-mcp-label">Outbox</span>
				<span class="nw-vitals-mcp-count">${outbox.length}</span>
				<span class="nw-vitals-mcp-detail">${outbox.slice(0,3).map(m => `<code>${this._escape(m.peer_id || '')} · ${this._escape(m.kind || '')}</code>`).join(' / ') || '<em>—</em>'}</span>
			</div>
			<div class="nw-vitals-mcp-row">
				<span class="nw-vitals-mcp-label">Shared</span>
				<span class="nw-vitals-mcp-count">${shared.length}</span>
				<span class="nw-vitals-mcp-detail">${sharedRows || '<em>—</em>'}</span>
			</div>`;
	}

	_renderMcp(tools, remote, calls) {
		if (!this._mcpEl) return;
		if (!tools.length && !remote.length && !calls.length) {
			this._mcpEl.innerHTML = '<div class="nw-vitals-empty">No MCP activity yet.</div>';
			return;
		}
		const localTools = tools.filter((t) => !t?.annotations?.remote);
		const remoteTools = tools.filter((t) => t?.annotations?.remote);
		const callRows = calls.slice(0, 5).map((c) => {
			const ok       = c?.response?.ok;
			const status   = ok ? 'ok' : (c?.response?.error || 'error');
			const cls      = ok ? 'good' : (status === 'alignment_veto' || status === 'unknown_capability' ? 'bad' : 'warn');
			return `
				<div class="nw-vitals-mcp-call">
					<span class="nw-vitals-mcp-call-tool">${this._escape(c.tool || '')}</span>
					<span class="nw-vitals-mcp-call-status nw-vitals-verdict-${cls}">${this._escape(status)}</span>
				</div>`;
		}).join('');
		this._mcpEl.innerHTML = `
			<div class="nw-vitals-mcp-row">
				<span class="nw-vitals-mcp-label">Local tools</span>
				<span class="nw-vitals-mcp-count">${localTools.length}</span>
				<span class="nw-vitals-mcp-detail">${localTools.map((t) => this._escape(t.name)).join(', ') || '—'}</span>
			</div>
			<div class="nw-vitals-mcp-row">
				<span class="nw-vitals-mcp-label">Remote tools</span>
				<span class="nw-vitals-mcp-count">${remote.length}</span>
				<span class="nw-vitals-mcp-detail">${remote.map((r) => `${this._escape(r.name)} <i>← ${this._escape(r.server)}</i>`).join(', ') || '—'}</span>
			</div>
			<div class="nw-vitals-mcp-row nw-vitals-mcp-calls">
				<span class="nw-vitals-mcp-label">Recent calls</span>
				<span class="nw-vitals-mcp-detail">${callRows || '<em>none</em>'}</span>
			</div>`;
	}

	async _propose() {
		if (!this._proposeBtn) return;
		this._proposeBtn.disabled = true;
		const original = this._proposeBtn.textContent;
		this._proposeBtn.textContent = 'Proposing…';
		try {
			const resp = await this.api.proactiveOptimizationPropose();
			this._candidates = resp?.candidates || [];
			this._renderCandidates(this._candidates);
		} catch (err) {
			this._renderError(err);
		} finally {
			this._proposeBtn.disabled = false;
			this._proposeBtn.textContent = original;
		}
	}

	async _simulateCandidate(idx) {
		const cand = this._candidates[idx];
		if (!cand || !this._candidatesEl) return;
		const row = this._candidatesEl.querySelector(`[data-cand-idx="${idx}"]`);
		const sim = row?.querySelector('.nw-vitals-cand-sim');
		if (sim) sim.textContent = 'Simulating…';
		try {
			const resp = await this.api.proactiveOptimizationSimulate(cand);
			const diff = resp?.diff || {};
			let summary;
			if ('changed' in diff) {
				summary = `Δ ${diff.changed} entries  (unchanged: ${diff.unchanged ?? 0})`;
			} else if ('relaxable_denies' in diff) {
				summary = `${diff.relaxable_denies} past deny(ies) on ${diff.rule_target} could relax  (thumbs-up: ${diff.thumbs_up_total ?? 0})`;
			} else {
				summary = JSON.stringify(diff);
			}
			if (sim) sim.textContent = summary;
		} catch (err) {
			if (sim) sim.textContent = `Simulate failed: ${err?.message || err}`;
		}
	}

	_renderCandidates(candidates) {
		if (!this._candidatesEl) return;
		if (!candidates || !candidates.length) {
			this._candidatesEl.innerHTML = '<div class="nw-vitals-empty">No candidates. Click Propose to scan live state.</div>';
			return;
		}
		this._candidatesEl.innerHTML = candidates.map((c, i) => {
			const kind = c.kind === 'constitution_rule_add'    ? 'add' :
			             c.kind === 'constitution_rule_remove' ? 'remove' :
			             this._escape(c.kind || '?');
			const cls = c.kind === 'constitution_rule_add'    ? 'nw-vitals-cand-add'    :
			            c.kind === 'constitution_rule_remove' ? 'nw-vitals-cand-remove' : '';
			return `
				<div class="nw-vitals-cand-row ${cls}" data-cand-idx="${i}">
					<div class="nw-vitals-cand-head">
						<span class="nw-vitals-cand-by">${this._escape(c.by || '')}</span>
						<span class="nw-vitals-cand-kind">${this._escape(kind)}</span>
						<span class="nw-vitals-cand-target">${this._escape(c.target || '')}</span>
						<button class="nw-btn nw-btn-sm nw-btn-secondary" data-sim-idx="${i}" title="Replay the historical Ledger against this candidate">Simulate</button>
						<button class="nw-btn nw-btn-sm nw-btn-secondary" data-promote-idx="${i}" title="Run the Promotion gate: simulate, run every Alignment validator, and apply if all pass. A Ledger entry is recorded.">Promote</button>
					</div>
					<div class="nw-vitals-cand-rationale">${this._escape(c.rationale || '')}</div>
					<div class="nw-vitals-cand-sim"></div>
					<div class="nw-vitals-cand-promo"></div>
				</div>`;
		}).join('');
		this._candidatesEl.querySelectorAll('button[data-sim-idx]').forEach((btn) => {
			btn.addEventListener('click', () => this._simulateCandidate(parseInt(btn.getAttribute('data-sim-idx'), 10)));
		});
		this._candidatesEl.querySelectorAll('button[data-promote-idx]').forEach((btn) => {
			btn.addEventListener('click', () => this._promoteCandidate(parseInt(btn.getAttribute('data-promote-idx'), 10)));
		});
	}

	async _promoteCandidate(idx) {
		const cand = this._candidates[idx];
		if (!cand || !this._candidatesEl) return;
		const ok = window.confirm(
			`Promote this candidate?\n\n` +
			`  ${cand.kind}: ${cand.target}\n\n` +
			`Promotion will simulate, run every Alignment validator, and apply the change if all pass. A Ledger entry is recorded either way.`,
		);
		if (!ok) return;

		const row  = this._candidatesEl.querySelector(`[data-cand-idx="${idx}"]`);
		const slot = row?.querySelector('.nw-vitals-cand-promo');
		if (slot) slot.textContent = 'Promoting…';
		try {
			const resp = await this.api.proactivePromote(cand);
			const decision = resp?.decision || '?';
			const align    = (resp?.alignment?.decision) || '?';
			const applied  = (resp?.applied?.status) || '';
			let summary = `${decision}  (alignment: ${align}`;
			if (applied) summary += `, apply: ${applied}`;
			summary += ')';
			if (decision === 'refused_by_validator') {
				const vetoes = (resp?.alignment?.verdicts || [])
					.filter((v) => v.decision === 'veto')
					.map((v) => `${v.by}: ${v.reason}`)
					.join('; ');
				if (vetoes) summary += `  ← ${vetoes}`;
			}
			if (slot) {
				slot.textContent = summary;
				slot.dataset.outcome = decision;
			}
			// On apply / noop / remove the constitution may have changed —
			// reload candidates and refresh stats.
			if (decision === 'applied' || decision === 'noop') {
				setTimeout(() => this._propose().catch(() => {}), 600);
			}
		} catch (err) {
			if (slot) slot.textContent = `Promote failed: ${err?.message || err}`;
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
			const capName = e.intent?.capability || e.resolved_capability?.name || e.governor_verdict?.capability;
			const intent  = capName ? ` · intent: ${this._escape(capName)}` : '';
			const conf = e.governor_verdict?.confidence != null ? ` · conf=${e.governor_verdict.confidence.toFixed(2)}` : '';
			const id = this._escape(e.id || '');
			const cap = this._escape(capName || '');
			return `
				<div class="nw-vitals-ledger-row" data-entry="${id}" data-cap="${cap}">
					<span class="nw-vitals-ledger-id">${id}</span>
					<span class="nw-vitals-ledger-verdict ${kind ? 'nw-vitals-verdict-' + kind : ''}">${this._escape(verdict)}</span>
					<span class="nw-vitals-ledger-topic">${this._escape(topic)}${obs}${intent}${motor}${conf}</span>
					<span class="nw-vitals-ledger-thumbs">
						<button class="nw-vitals-thumb" data-thumb="up"   data-target="${id}" data-cap="${cap}" title="Mark this entry as helpful">&#x1F44D;</button>
						<button class="nw-vitals-thumb" data-thumb="down" data-target="${id}" data-cap="${cap}" title="Mark this entry as wrong">&#x1F44E;</button>
					</span>
				</div>`;
		}).join('');
		this._ledger.querySelectorAll('button[data-thumb]').forEach((btn) => {
			btn.addEventListener('click', () => this._sendThumb(btn));
		});
	}

	async _sendThumb(btn) {
		const target = btn.getAttribute('data-target');
		const cap    = btn.getAttribute('data-cap') || null;
		const value  = btn.getAttribute('data-thumb');
		if (!target || !value) return;
		btn.disabled = true;
		try {
			await this.api.proactiveFeedback(target, 'thumbs', value, cap ? { capability: cap } : {});
			btn.classList.add('is-active');
			// Remove the active state after 1.5s; refresh in case validators
			// downstream (e.g., recent_thumbs_down) react to the new signal.
			setTimeout(() => {
				btn.classList.remove('is-active');
				this.refresh().catch(() => {});
			}, 800);
		} catch (err) {
			console.warn('[ProactiveVitals] thumbs send failed:', err);
			btn.disabled = false;
		}
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
