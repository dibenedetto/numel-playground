// numel-confirm.js — Global themed confirmation/input dialogs
//
// Usage:
//   const ok = await NumelConfirm(title, message, confirmText, danger);
//   const val = await NumelPrompt(title, message, initialValue, confirmText, placeholder);
//   await NumelAlert(title, message, buttonText);
// Returns a Promise<boolean>, Promise<string|null>, or Promise<void>.

// eslint-disable-next-line no-unused-vars
function NumelConfirm(title, message, confirmText = 'Confirm', danger = false) {
	return new Promise((resolve) => {
		const overlay = document.createElement('div');
		overlay.className = 'sg-input-dialog-overlay';
		const dangerClass = danger ? ' sg-confirm-danger' : '';
		overlay.innerHTML =
			'<div class="sg-input-dialog">' +
				'<div class="sg-input-dialog-header">' +
					'<span class="sg-input-dialog-title">' + title + '</span>' +
					'<button class="sg-input-dialog-close">\u2715</button>' +
				'</div>' +
				'<div class="sg-input-dialog-body">' +
					'<p class="sg-confirm-dialog-message">' + message + '</p>' +
				'</div>' +
				'<div class="sg-input-dialog-footer">' +
					'<button class="sg-input-dialog-btn sg-input-dialog-cancel">Cancel</button>' +
					'<button class="sg-input-dialog-btn sg-input-dialog-confirm' + dangerClass + '">' + confirmText + '</button>' +
				'</div>' +
			'</div>';
		document.body.appendChild(overlay);
		const close = (val) => { overlay.remove(); resolve(val); };
		overlay.querySelector('.sg-input-dialog-close').onclick   = () => close(false);
		overlay.querySelector('.sg-input-dialog-cancel').onclick  = () => close(false);
		overlay.querySelector('.sg-input-dialog-confirm').onclick = () => close(true);
		overlay.addEventListener('click', (e) => { if (e.target === overlay) close(false); });
	});
}

// eslint-disable-next-line no-unused-vars
function NumelPrompt(title, message, initialValue = '', confirmText = 'Save', placeholder = '') {
	return new Promise((resolve) => {
		const overlay = document.createElement('div');
		overlay.className = 'sg-input-dialog-overlay';
		overlay.innerHTML =
			'<div class="sg-input-dialog" style="min-width:320px;max-width:420px">' +
				'<div class="sg-input-dialog-header">' +
					'<span class="sg-input-dialog-title">' + title + '</span>' +
					'<button class="sg-input-dialog-close">\u2715</button>' +
				'</div>' +
				'<div class="sg-input-dialog-body">' +
					'<p class="sg-confirm-dialog-message">' + message + '</p>' +
					'<input class="nw-input sg-input-dialog-field" type="text" autocomplete="off" spellcheck="false">' +
				'</div>' +
				'<div class="sg-input-dialog-footer">' +
					'<button class="sg-input-dialog-btn sg-input-dialog-cancel">Cancel</button>' +
					'<button class="sg-input-dialog-btn sg-input-dialog-confirm">' + confirmText + '</button>' +
				'</div>' +
			'</div>';
		document.body.appendChild(overlay);

		const input = overlay.querySelector('.sg-input-dialog-field');
		if (input) {
			input.value = initialValue || '';
			if (placeholder) input.placeholder = placeholder;
		}

		const close = (val) => {
			overlay.remove();
			resolve(val);
		};
		const submit = () => close(input ? input.value : null);

		overlay.querySelector('.sg-input-dialog-close').onclick   = () => close(null);
		overlay.querySelector('.sg-input-dialog-cancel').onclick  = () => close(null);
		overlay.querySelector('.sg-input-dialog-confirm').onclick = submit;
		overlay.addEventListener('click', (e) => { if (e.target === overlay) close(null); });
		overlay.addEventListener('keydown', (e) => {
			if (e.key === 'Escape') {
				e.preventDefault();
				close(null);
			}
			if (e.key === 'Enter') {
				e.preventDefault();
				submit();
			}
		});

		if (input) {
			queueMicrotask(() => {
				input.focus();
				input.select();
			});
		}
	});
}

// eslint-disable-next-line no-unused-vars
function NumelAlert(title, message, buttonText = 'OK') {
	return new Promise((resolve) => {
		const overlay = document.createElement('div');
		overlay.className = 'sg-input-dialog-overlay';
		overlay.innerHTML =
			'<div class="sg-input-dialog">' +
				'<div class="sg-input-dialog-header">' +
					'<span class="sg-input-dialog-title">' + title + '</span>' +
					'<button class="sg-input-dialog-close">\u2715</button>' +
				'</div>' +
				'<div class="sg-input-dialog-body">' +
					'<p class="sg-confirm-dialog-message">' + message + '</p>' +
				'</div>' +
				'<div class="sg-input-dialog-footer">' +
					'<button class="sg-input-dialog-btn sg-input-dialog-confirm">' + buttonText + '</button>' +
				'</div>' +
			'</div>';
		document.body.appendChild(overlay);

		const close = () => {
			overlay.remove();
			resolve();
		};

		overlay.querySelector('.sg-input-dialog-close').onclick = close;
		overlay.querySelector('.sg-input-dialog-confirm').onclick = close;
		overlay.addEventListener('click', (e) => { if (e.target === overlay) close(); });
		overlay.addEventListener('keydown', (e) => {
			if (e.key === 'Escape' || e.key === 'Enter') {
				e.preventDefault();
				close();
			}
		});

		queueMicrotask(() => {
			overlay.querySelector('.sg-input-dialog-confirm')?.focus();
		});
	});
}
