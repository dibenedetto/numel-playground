/* ========================================================================
   YOUR ASSISTANT — user-facing proactive surface (M5.12)
   The plain-language counterpart to the Proactive Vitals dashboard.
   Reads /proactive/feed (cards translated server-side from the Ledger +
   consent store) and renders them the way a normal user expects: an
   inbox of "I noticed / Can I / I did" cards with one-tap actions.

   Three interaction modes, a placement choice, and a Vitals-visibility
   choice — all user-selectable and persisted to localStorage.
   ======================================================================== */

console.log('[Numel] Loading proactive assistant surface...');

const PROACTIVE_ASSISTANT_PREFS_KEY = 'numel_proactive_assistant_prefs_v1';
const PROACTIVE_ASSISTANT_INTERVAL_MS = 6000;

const PROACTIVE_ASSISTANT_DEFAULTS = {
	interaction: 'feed',       // 'feed' | 'cards' | 'chat'
	placement:   'panel',      // 'panel' | 'console' | 'both'
	vitals:      'developer',  // 'developer' | 'hidden' | 'asis'
};

class ProactiveAssistantPanel {
	constructor(api) {
		this.api      = api;
		this._section = document.getElementById('proactiveAssistantSection');
		this._feedEl  = document.getElementById('proactiveAssistantFeed');
		this._badge   = document.getElementById('proactiveAssistantBadge');
		this._refresh = document.getElementById('proactiveAssistantRefreshBtn');
		this._settingsBtn = document.getElementById('proactiveAssistantSettingsBtn');
		this._settings    = document.getElementById('proactiveAssistantSettings');
		this._selInteraction = document.getElementById('proactiveAssistantInteraction');
		this._selPlacement   = document.getElementById('proactiveAssistantPlacement');
		this._selVitals      = document.getElementById('proactiveAssistantVitals');
		this._replyWrap = document.getElementById('proactiveAssistantReplyWrap');
		this._replyInput = document.getElementById('proactiveAssistantReply');
		this._replySend  = document.getElementById('proactiveAssistantReplySend');
		this._timer = null;
		this._lastCards = [];
		this._dismissed = new Set();   // client-side dismissals this session

		if (!this._section || !this._feedEl) {
			console.warn('[ProactiveAssistant] markup missing; skipping init.');
			return;
		}

		this._prefs = this._loadPrefs();
		this._applyPrefsToControls();
		this._applyVitalsVisibility();
		this._applyInteractionChrome();

		this._refresh?.addEventListener('click', () => this.refresh());
		this._settingsBtn?.addEventListener('click', () => {
			if (this._settings) this._settings.hidden = !this._settings.hidden;
		});
		this._selInteraction?.addEventListener('change', () => this._onPrefChange());
		this._selPlacement?.addEventListener('change',   () => this._onPrefChange());
		this._selVitals?.addEventListener('change',      () => this._onPrefChange());
		this._feedEl.addEventListener('click', (e) => this._handleCardClick(e));
		this._replySend?.addEventListener('click', () => this._sendReply());
		this._replyInput?.addEventListener('keydown', (e) => {
			if (e.key === 'Enter') this._sendReply();
		});

		// Pause polling when the section collapses.
		const observer = new MutationObserver(() => this._reschedule());
		observer.observe(this._section, { attributes: true, attributeFilter: ['class'] });
		this._reschedule();
	}

	// ── Preferences ──────────────────────────────────────────────────

	_loadPrefs() {
		try {
			const raw = localStorage.getItem(PROACTIVE_ASSISTANT_PREFS_KEY);
			if (raw) return { ...PROACTIVE_ASSISTANT_DEFAULTS, ...JSON.parse(raw) };
		} catch {}
		return { ...PROACTIVE_ASSISTANT_DEFAULTS };
	}

	_savePrefs() {
		try { localStorage.setItem(PROACTIVE_ASSISTANT_PREFS_KEY, JSON.stringify(this._prefs)); } catch {}
	}

	_applyPrefsToControls() {
		if (this._selInteraction) this._selInteraction.value = this._prefs.interaction;
		if (this._selPlacement)   this._selPlacement.value   = this._prefs.placement;
		if (this._selVitals)      this._selVitals.value      = this._prefs.vitals;
	}

	_onPrefChange() {
		this._prefs = {
			interaction: this._selInteraction?.value || 'feed',
			placement:   this._selPlacement?.value   || 'panel',
			vitals:      this._selVitals?.value      || 'developer',
		};
		this._savePrefs();
		this._applyVitalsVisibility();
		this._applyInteractionChrome();
		this._render(this._lastCards);   // re-render in the new mode immediately
	}

	_applyVitalsVisibility() {
		const vitals = document.getElementById('proactiveVitalsSection');
		if (!vitals) return;
		if (this._prefs.vitals === 'hidden') {
			vitals.style.display = 'none';
		} else {
			vitals.style.display = '';
			// 'developer' collapses it by default; 'asis' leaves whatever state.
			if (this._prefs.vitals === 'developer' && !vitals.classList.contains('nw-section-collapsed')) {
				// don't force-collapse if the user expanded it this session;
				// only apply the default on first paint
				if (!this._vitalsTouched) vitals.classList.add('nw-section-collapsed');
			}
		}
		this._vitalsTouched = true;
	}

	_applyInteractionChrome() {
		// Reply box only shows in feed + chat modes.
		const showReply = this._prefs.interaction === 'feed' || this._prefs.interaction === 'chat';
		if (this._replyWrap) this._replyWrap.hidden = !showReply;
		this._feedEl.classList.toggle('nw-assistant-mode-chat',  this._prefs.interaction === 'chat');
		this._feedEl.classList.toggle('nw-assistant-mode-cards', this._prefs.interaction === 'cards');
		this._feedEl.classList.toggle('nw-assistant-mode-feed',  this._prefs.interaction === 'feed');
	}

	// ── Polling ──────────────────────────────────────────────────────

	_isCollapsed() {
		return this._section?.classList.contains('nw-section-collapsed');
	}

	_reschedule() {
		if (this._timer) { clearInterval(this._timer); this._timer = null; }
		if (this._isCollapsed()) return;
		this.refresh();
		this._timer = setInterval(() => this.refresh(), PROACTIVE_ASSISTANT_INTERVAL_MS);
	}

	async refresh() {
		if (!this._feedEl) return;
		try {
			const out = await this.api.proactiveFeed(30, true);
			const cards = (out?.cards || []).filter((c) => !this._dismissed.has(c.id));
			this._lastCards = cards;
			this._render(cards);
			this._updateBadge(out?.pending_count || 0);
			if (this._prefs.placement === 'console' || this._prefs.placement === 'both') {
				this._mirrorToConsole(cards);
			}
		} catch (err) {
			this._feedEl.innerHTML = `<div class="nw-vitals-empty">Assistant unavailable: ${this._escape(String(err?.message || err))}</div>`;
		}
	}

	_updateBadge(pending) {
		if (!this._badge) return;
		if (pending > 0) {
			this._badge.textContent = String(pending);
			this._badge.style.display = '';
		} else {
			this._badge.style.display = 'none';
		}
	}

	// ── Rendering ────────────────────────────────────────────────────

	_render(cards) {
		if (!this._feedEl) return;
		if (!cards || !cards.length) {
			this._feedEl.innerHTML = '<div class="nw-vitals-empty">Nothing needs you right now. I’ll let you know.</div>';
			return;
		}
		const mode = this._prefs.interaction;
		this._feedEl.innerHTML = cards.map((c) =>
			mode === 'chat' ? this._renderChatBubble(c) : this._renderCard(c)
		).join('');
	}

	_renderCard(c) {
		const when = c.ts ? new Date(c.ts * 1000).toLocaleTimeString() : '';
		const src  = c.source ? ` · ${this._escape(c.source)}` : '';
		const detail = c.detail ? `<div class="nw-assistant-card-detail">${this._escape(c.detail)}</div>` : '';
		const actions = (c.actions || []).map((a) => this._actionBtn(c, a)).join(' ');
		return `
			<div class="nw-assistant-card nw-assistant-card-${this._escape(c.kind)}" data-card-id="${this._escape(c.id)}">
				<div class="nw-assistant-card-head">
					<span class="nw-assistant-card-icon">${c.icon || ''}</span>
					<span class="nw-assistant-card-headline">${this._escape(c.headline || '')}</span>
				</div>
				${detail}
				<div class="nw-assistant-card-meta">${this._escape(when)}${src}</div>
				<div class="nw-assistant-card-actions">${actions}</div>
			</div>`;
	}

	_renderChatBubble(c) {
		// In chat mode, the assistant "speaks" each card as a bubble.
		const actions = (c.actions || []).map((a) => this._actionBtn(c, a)).join(' ');
		const detail = c.detail ? ` ${this._escape(c.detail)}` : '';
		return `
			<div class="nw-assistant-bubble nw-assistant-bubble-${this._escape(c.kind)}" data-card-id="${this._escape(c.id)}">
				<span class="nw-assistant-bubble-icon">${c.icon || '🤖'}</span>
				<div class="nw-assistant-bubble-body">
					<div>${this._escape(c.headline || '')}${detail}</div>
					<div class="nw-assistant-card-actions">${actions}</div>
				</div>
			</div>`;
	}

	_actionBtn(card, a) {
		const data = [
			`data-action="${this._escape(a.action)}"`,
			`data-card-id="${this._escape(card.id)}"`,
		];
		if (a.consent_id) data.push(`data-consent-id="${this._escape(a.consent_id)}"`);
		if (a.action_id)  data.push(`data-action-id="${this._escape(a.action_id)}"`);
		if (a.capability) data.push(`data-capability="${this._escape(a.capability)}"`);
		const primary = (a.action === 'approve') ? 'nw-btn-primary' : 'nw-btn-secondary';
		return `<button class="nw-btn nw-btn-sm ${primary}" ${data.join(' ')}>${this._escape(a.label)}</button>`;
	}

	// ── Actions ──────────────────────────────────────────────────────

	async _handleCardClick(e) {
		const btn = e.target?.closest('button[data-action]');
		if (!btn) return;
		const action     = btn.dataset.action;
		const cardId     = btn.dataset.cardId;
		const consentId  = btn.dataset.consentId;
		const actionId   = btn.dataset.actionId;
		const capability = btn.dataset.capability || null;
		btn.disabled = true;
		try {
			if (action === 'approve' && consentId) {
				await this.api.proactiveConsentApprove(consentId, { operator: 'assistant_ui' });
			} else if (action === 'reject' && consentId) {
				await this.api.proactiveConsentReject(consentId, { operator: 'assistant_ui' });
			} else if (action === 'undo' && actionId) {
				await this.api.proactiveMotorUndo(actionId, capability, 'user undid from assistant');
			} else if (action === 'dismiss') {
				this._dismissed.add(cardId);
				try { await this.api.proactiveFeedDismiss(cardId, capability); } catch {}
			} else if (action === 'ok' || action === 'show') {
				// 'ok' acknowledges (hide); 'show' could expand — for now both hide.
				this._dismissed.add(cardId);
			}
			await this.refresh();
		} catch (err) {
			console.warn('[ProactiveAssistant] action failed:', err);
			btn.disabled = false;
		}
	}

	async _sendReply() {
		const text = (this._replyInput?.value || '').trim();
		if (!text) return;
		this._replyInput.value = '';
		// Standing instructions land in the User Constitution as a freeform
		// preference. The Optimization loop + operator can later promote
		// them into formal rules; for now we record the intent verbatim.
		try {
			await this.api.json('/proactive/constitution/update', {
				patch: { preferences: { [`note_${Date.now()}`]: text } },
			});
			// Echo into the feed as a "did" acknowledgement.
			this._feedEl.insertAdjacentHTML('afterbegin', this._renderCard({
				id: `local_${Date.now()}`, kind: 'did', icon: '✅',
				headline: 'Noted your instruction',
				detail: text, ts: Date.now() / 1000, source: 'you', actions: [],
			}));
		} catch (err) {
			console.warn('[ProactiveAssistant] reply failed:', err);
		}
	}

	// ── Console mirror ───────────────────────────────────────────────

	_mirrorToConsole(cards) {
		// Push the top pending "asks" card as a console suggestion so the
		// user sees it wherever they already are. Best-effort: only if a
		// console instance exposes a public add hook.
		const console_ = window._numelConsole || window.numelConsole || null;
		if (!console_ || typeof console_.pushProactiveCard !== 'function') return;
		const top = cards.find((c) => c.kind === 'asks');
		if (top && top.id !== this._lastMirroredId) {
			this._lastMirroredId = top.id;
			try { console_.pushProactiveCard(top); } catch {}
		}
	}

	_escape(s) {
		return String(s ?? '').replace(/[&<>"']/g, (ch) => (
			{ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]
		));
	}
}

window.ProactiveAssistantPanel = ProactiveAssistantPanel;
