// numel-confirm.js — Global themed confirmation dialog
//
// Usage:  const ok = await NumelConfirm(title, message, confirmText, danger);
// Returns a Promise<boolean>.

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
