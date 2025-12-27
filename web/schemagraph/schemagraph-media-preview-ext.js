// ========================================================================
// SCHEMAGRAPH MEDIA PREVIEW RENDERER
// Shared rendering utilities for DataNodes and PreviewNodes
// ========================================================================

const MediaPreviewRenderer = {
	imageCache: new Map(),
	videoFrameCache: new Map(),

	// ====================================================================
	// IMAGE RENDERING
	// ====================================================================

	drawCachedImage(ctx, src, x, y, w, h, options = {}) {
		const { colors = {}, contain = false, onLoad = null } = options;
		let img = this.imageCache.get(src);

		if (!img) {
			img = new Image();
			img.onload = () => {
				img._loaded = true;
				if (onLoad) onLoad();
			};
			img.onerror = () => { img._error = true; };
			img.src = src;
			this.imageCache.set(src, img);
		}

		if (img._loaded) {
			const imgAspect = img.width / img.height;
			const boxAspect = w / h;
			let drawW, drawH, drawX, drawY;

			if (contain) {
				if (imgAspect > boxAspect) {
					drawW = w; drawH = w / imgAspect;
				} else {
					drawH = h; drawW = h * imgAspect;
				}
				drawX = x + (w - drawW) / 2;
				drawY = y + (h - drawH) / 2;
			} else {
				if (imgAspect > boxAspect) {
					drawH = h; drawW = h * imgAspect;
					drawX = x + (w - drawW) / 2; drawY = y;
				} else {
					drawW = w; drawH = w / imgAspect;
					drawX = x; drawY = y + (h - drawH) / 2;
				}
			}
			ctx.drawImage(img, drawX, drawY, drawW, drawH);
			return true;
		} else if (img._error) {
			ctx.fillStyle = colors.textTertiary || '#555';
			ctx.font = '12px sans-serif';
			ctx.textAlign = 'center';
			ctx.textBaseline = 'middle';
			ctx.fillText('Failed to load', x + w / 2, y + h / 2);
			return false;
		} else {
			ctx.fillStyle = colors.textTertiary || '#555';
			ctx.font = '10px sans-serif';
			ctx.textAlign = 'center';
			ctx.textBaseline = 'middle';
			ctx.fillText('Loading...', x + w / 2, y + h / 2);
			return false;
		}
	},

	// ====================================================================
	// VIDEO FRAME RENDERING
	// ====================================================================

	drawCachedVideoFrame(ctx, src, x, y, w, h, options = {}) {
		const { colors = {}, color = '#ff4757', icon = '🎬', onLoad = null } = options;
		let frame = this.videoFrameCache.get(src);

		if (!frame) {
			frame = { canvas: null, loading: true };
			this.videoFrameCache.set(src, frame);

			const video = document.createElement('video');
			video.crossOrigin = 'anonymous';
			video.muted = true;
			video.preload = 'metadata';

			video.onloadedmetadata = () => {
				video.currentTime = video.duration / 2;
			};
			video.onseeked = () => {
				const canvas = document.createElement('canvas');
				canvas.width = video.videoWidth;
				canvas.height = video.videoHeight;
				canvas.getContext('2d').drawImage(video, 0, 0);
				frame.canvas = canvas;
				frame.loading = false;
				if (onLoad) onLoad();
			};
			video.onerror = () => {
				frame.error = true;
				frame.loading = false;
			};
			video.src = src;
		}

		if (frame.canvas) {
			const imgAspect = frame.canvas.width / frame.canvas.height;
			const boxAspect = w / h;
			let drawW, drawH, drawX, drawY;

			if (imgAspect > boxAspect) {
				drawW = w; drawH = w / imgAspect;
			} else {
				drawH = h; drawW = h * imgAspect;
			}
			drawX = x + (w - drawW) / 2;
			drawY = y + (h - drawH) / 2;
			ctx.drawImage(frame.canvas, drawX, drawY, drawW, drawH);
			return true;
		} else if (frame.error) {
			ctx.fillStyle = 'rgba(0,0,0,0.3)';
			ctx.fillRect(x, y, w, h);
			ctx.fillStyle = colors.textTertiary || '#555';
			ctx.font = '10px sans-serif';
			ctx.textAlign = 'center';
			ctx.textBaseline = 'middle';
			ctx.fillText('No preview', x + w / 2, y + h / 2);
			return false;
		} else {
			ctx.fillStyle = 'rgba(0,0,0,0.3)';
			ctx.fillRect(x, y, w, h);
			ctx.font = '24px sans-serif';
			ctx.textAlign = 'center';
			ctx.textBaseline = 'middle';
			ctx.fillStyle = color;
			ctx.fillText(icon, x + w / 2, y + h / 2);
			return false;
		}
	},

	// ====================================================================
	// TEXT PREVIEW
	// ====================================================================

	drawTextPreview(ctx, text, x, y, w, h, options = {}) {
		const { colors = {}, textScale = 1, font = 'sans-serif', maxLines = null } = options;
		if (!text) {
			ctx.fillStyle = colors.textTertiary || '#555';
			ctx.font = `${12 * textScale}px ${font}`;
			ctx.textAlign = 'center';
			ctx.textBaseline = 'middle';
			ctx.fillText('No text content', x + w / 2, y + h / 2);
			return;
		}

		const lines = text.split('\n');
		const lineHeight = 11 * textScale;
		const visibleLines = maxLines || Math.floor(h / lineHeight);

		ctx.font = `${9 * textScale}px 'Courier New', monospace`;
		ctx.textAlign = 'left';
		ctx.textBaseline = 'top';
		ctx.fillStyle = colors.textSecondary || '#aaa';

		for (let i = 0; i < Math.min(lines.length, visibleLines); i++) {
			let line = lines[i];
			if (ctx.measureText(line).width > w) {
				while (line.length > 3 && ctx.measureText(line + '...').width > w) {
					line = line.slice(0, -1);
				}
				line += '...';
			}
			ctx.fillText(line, x, y + i * lineHeight);
		}

		if (lines.length > visibleLines) {
			ctx.fillStyle = colors.textTertiary || '#555';
			ctx.fillText('...', x, y + visibleLines * lineHeight);
		}
	},

	// ====================================================================
	// MEDIA PLACEHOLDERS
	// ====================================================================

	drawMediaPlaceholder(ctx, type, x, y, w, h, options = {}) {
		const { textScale = 1, font = 'sans-serif', label = '' } = options;
		const centerX = x + w / 2;
		const centerY = y + h / 2;

		const config = {
			image:   { icon: '🖼️', color: '#00d4aa' },
			audio:   { icon: '🔊', color: '#ffd700' },
			video:   { icon: '🎬', color: '#ff4757' },
			model3d: { icon: '🧊', color: '#00bcd4' },
			document:{ icon: '📄', color: '#ff9f4a' },
			binary:  { icon: '📦', color: '#9370db' },
			text:    { icon: '📝', color: '#4a9eff' },
			unknown: { icon: '❓', color: '#888888' }
		};

		const { icon, color } = config[type] || config.unknown;

		ctx.font = `${28 * textScale}px ${font}`;
		ctx.textAlign = 'center';
		ctx.textBaseline = 'middle';
		ctx.fillStyle = color;
		ctx.fillText(icon, centerX, centerY - (label ? 15 : 0));

		if (label) {
			ctx.font = `${10 * textScale}px ${font}`;
			ctx.fillStyle = '#888';
			ctx.fillText(label, centerX, centerY + 20);
		}
	},

	// ====================================================================
	// COLLAPSED PREVIEW (icon + summary line)
	// ====================================================================

	drawCollapsedPreview(ctx, type, summary, x, y, w, h, options = {}) {
		const { textScale = 1, font = 'sans-serif', colors = {} } = options;
		const centerY = y + h / 2;

		const icons = {
			text: '📝', document: '📄', image: '🖼️', audio: '🔊',
			video: '🎬', model3d: '🧊', binary: '📦',
			string: '📝', number: '🔢', boolean: '⚡', json: '📋', list: '📚',
			unknown: '❓'
		};
		const typeColors = {
			text: '#4a9eff', document: '#ff9f4a', image: '#00d4aa', audio: '#ffd700',
			video: '#ff4757', model3d: '#00bcd4', binary: '#9370db',
			string: '#4a9eff', number: '#ff9f4a', boolean: '#92d050', json: '#9370db', list: '#ff6b9d',
			unknown: '#888'
		};

		const icon = icons[type] || icons.unknown;
		const color = typeColors[type] || typeColors.unknown;

		// Icon
		ctx.font = `${18 * textScale}px ${font}`;
		ctx.textAlign = 'center';
		ctx.textBaseline = 'middle';
		ctx.fillStyle = color;
		ctx.fillText(icon, x + 14, centerY);

		// Summary text
		ctx.font = `${10 * textScale}px ${font}`;
		ctx.textAlign = 'left';
		ctx.fillStyle = colors.textPrimary || '#eee';

		const textX = x + 32;
		const maxW = w - 36;
		let displayText = summary;
		if (ctx.measureText(displayText).width > maxW) {
			while (displayText.length > 3 && ctx.measureText(displayText + '...').width > maxW) {
				displayText = displayText.slice(0, -1);
			}
			displayText += '...';
		}
		ctx.fillText(displayText, textX, centerY);
	},

	// ====================================================================
	// EXPANDED CONTENT AREA (background box)
	// ====================================================================

	drawExpandedBackground(ctx, x, y, w, h, options = {}) {
		const { radius = 6, scale = 1 } = options;

		ctx.fillStyle = 'rgba(0, 0, 0, 0.3)';
		ctx.beginPath();
		ctx.roundRect(x, y, w, h, radius);
		ctx.fill();

		ctx.strokeStyle = 'rgba(255, 255, 255, 0.1)';
		ctx.lineWidth = 1 / scale;
		ctx.stroke();
	},

	// ====================================================================
	// BOOLEAN PREVIEW
	// ====================================================================

	drawBooleanPreview(ctx, value, x, y, w, h, options = {}) {
		const { textScale = 1, font = 'sans-serif' } = options;
		const centerX = x + w / 2;
		const centerY = y + h / 2;
		const color = value ? '#92d050' : '#dc6464';
		const icon = value ? '✔' : '✗';
		const text = value ? 'true' : 'false';

		ctx.font = `bold ${28 * textScale}px ${font}`;
		ctx.textAlign = 'center';
		ctx.textBaseline = 'middle';
		ctx.fillStyle = color;
		ctx.fillText(icon, centerX, centerY - 12);

		ctx.font = `bold ${14 * textScale}px ${font}`;
		ctx.fillText(text, centerX, centerY + 16);
	},

	// ====================================================================
	// NUMBER PREVIEW
	// ====================================================================

	drawNumberPreview(ctx, value, x, y, w, h, options = {}) {
		const { textScale = 1, font = 'sans-serif' } = options;
		const centerX = x + w / 2;
		const centerY = y + h / 2;

		ctx.font = `bold ${24 * textScale}px ${font}`;
		ctx.textAlign = 'center';
		ctx.textBaseline = 'middle';
		ctx.fillStyle = '#ff9f4a';
		ctx.fillText(String(value), centerX, centerY);
	},

	// ====================================================================
	// DETAILED INFO PREVIEW (document, binary, model3d)
	// ====================================================================

	drawDetailedInfoPreview(ctx, type, info, x, y, w, h, options = {}) {
		const { textScale = 1, font = 'sans-serif', colors = {} } = options;
		const centerX = x + w / 2;

		const config = {
			document: { icon: '📄', color: '#ff9f4a' },
			binary:   { icon: '📦', color: '#9370db' },
			model3d:  { icon: '🧊', color: '#00bcd4' },
			audio:    { icon: '🔊', color: '#ffd700' }
		};
		const { icon, color } = config[type] || { icon: '📄', color: '#888' };

		// Icon
		ctx.font = `${32 * textScale}px ${font}`;
		ctx.textAlign = 'center';
		ctx.textBaseline = 'middle';
		ctx.fillStyle = color;
		ctx.fillText(icon, centerX, y + 30);

		// Filename
		ctx.font = `bold ${11 * textScale}px ${font}`;
		ctx.fillStyle = colors.textPrimary || '#eee';
		ctx.fillText(info.filename || 'Unknown', centerX, y + 60);

		// Details
		ctx.font = `${9 * textScale}px ${font}`;
		ctx.fillStyle = colors.textSecondary || '#aaa';
		let lineY = y + 80;

		if (info.size) {
			ctx.fillText(`Size: ${this.formatFileSize(info.size)}`, centerX, lineY);
			lineY += 15;
		}
		if (info.mimeType) {
			ctx.fillText(`Type: ${info.mimeType}`, centerX, lineY);
			lineY += 15;
		}
		if (info.duration) {
			const mins = Math.floor(info.duration / 60);
			const secs = Math.floor(info.duration % 60);
			ctx.fillText(`Duration: ${mins}:${secs.toString().padStart(2, '0')}`, centerX, lineY);
			lineY += 15;
		}
		if (info.url) {
			ctx.fillStyle = colors.textTertiary || '#666';
			const url = info.url.length > 35 ? info.url.slice(0, 35) + '...' : info.url;
			ctx.fillText(url, centerX, lineY);
		}
	},

	// ====================================================================
	// UTILITIES
	// ====================================================================

	formatFileSize(bytes) {
		if (!bytes) return '0 B';
		const units = ['B', 'KB', 'MB', 'GB'];
		let i = 0;
		while (bytes >= 1024 && i < units.length - 1) {
			bytes /= 1024;
			i++;
		}
		return `${bytes.toFixed(i > 0 ? 1 : 0)} ${units[i]}`;
	},

	getTypeIcon(type) {
		const icons = {
			text: '📝', document: '📄', image: '🖼️', audio: '🔊',
			video: '🎬', model3d: '🧊', binary: '📦',
			string: '📝', number: '🔢', boolean: '⚡', json: '📋', list: '📚',
			unknown: '❓', auto: '🔄'
		};
		return icons[type] || icons.unknown;
	},

	getTypeColor(type) {
		const colors = {
			text: '#4a9eff', document: '#ff9f4a', image: '#00d4aa', audio: '#ffd700',
			video: '#ff4757', model3d: '#00bcd4', binary: '#9370db',
			string: '#4a9eff', number: '#ff9f4a', boolean: '#92d050', json: '#9370db', list: '#ff6b9d',
			unknown: '#888888'
		};
		return colors[type] || colors.unknown;
	},

	clearCaches() {
		this.imageCache.clear();
		this.videoFrameCache.clear();
	}
};

// Export
if (typeof module !== 'undefined' && module.exports) {
	module.exports = { MediaPreviewRenderer };
}
