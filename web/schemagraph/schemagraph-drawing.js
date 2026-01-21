// ========================================================================
// SCHEMAGRAPH DRAWING
// DrawingStyleManager - visual styles for graph rendering
// ========================================================================

console.log('[SchemaGraph] Loading drawing module...');

// ========================================================================
// DRAWING STYLE MANAGER
// ========================================================================

class DrawingStyleManager {
	constructor() {
		this.currentStyle = 'default';
		this.styles = {
			default: {
				name: 'Default',
				nodeCornerRadius: 6,
				nodeShadowBlur: 10,
				nodeShadowOffset: 2,
				linkWidth: 2.5,
				linkShadowBlur: 6,
				linkCurve: 0.5,
				slotRadius: 4,
				gridOpacity: 1.0,
				textFont: 'Arial, sans-serif',
				useGradient: false,
				useGlow: false,
				useDashed: false
			},
			minimal: {
				name: 'Minimal',
				nodeCornerRadius: 2,
				nodeShadowBlur: 0,
				nodeShadowOffset: 0,
				linkWidth: 1.5,
				linkShadowBlur: 0,
				linkCurve: 0.5,
				slotRadius: 3,
				gridOpacity: 0.3,
				textFont: 'Arial, sans-serif',
				useGradient: false,
				useGlow: false,
				useDashed: false
			},
			blueprint: {
				name: 'Blueprint',
				nodeCornerRadius: 0,
				nodeShadowBlur: 0,
				nodeShadowOffset: 0,
				linkWidth: 1.5,
				linkShadowBlur: 8,
				linkCurve: 0,
				slotRadius: 3,
				gridOpacity: 1.5,
				textFont: 'Courier New, monospace',
				useGradient: false,
				useGlow: true,
				useDashed: true
			},
			neon: {
				name: 'Neon',
				nodeCornerRadius: 8,
				nodeShadowBlur: 20,
				nodeShadowOffset: 0,
				linkWidth: 3,
				linkShadowBlur: 15,
				linkCurve: 0.6,
				slotRadius: 5,
				gridOpacity: 0.5,
				textFont: 'Arial, sans-serif',
				useGradient: true,
				useGlow: true,
				useDashed: false
			},
			organic: {
				name: 'Organic',
				nodeCornerRadius: 15,
				nodeShadowBlur: 12,
				nodeShadowOffset: 3,
				linkWidth: 4,
				linkShadowBlur: 8,
				linkCurve: 0.7,
				slotRadius: 6,
				gridOpacity: 0.7,
				textFont: 'Georgia, serif',
				useGradient: true,
				useGlow: false,
				useDashed: false
			},
			wireframe: {
				name: 'Wireframe',
				nodeCornerRadius: 0,
				nodeShadowBlur: 0,
				nodeShadowOffset: 0,
				linkWidth: 1,
				linkShadowBlur: 0,
				linkCurve: 0.5,
				slotRadius: 2,
				gridOpacity: 0.8,
				textFont: 'Courier New, monospace',
				useGradient: false,
				useGlow: false,
				useDashed: true
			}
		};
	}

	setStyle(styleName) {
		if (this.styles[styleName]) {
			this.currentStyle = styleName;
			localStorage.setItem('schemagraph-drawing-style', styleName);
			return true;
		}
		return false;
	}

	getStyle() {
		return this.styles[this.currentStyle];
	}

	getCurrentStyleName() {
		return this.currentStyle;
	}

	loadSavedStyle() {
		const saved = localStorage.getItem('schemagraph-drawing-style');
		if (saved && this.styles[saved]) this.currentStyle = saved;
	}

	getStyleNames() {
		return Object.keys(this.styles);
	}

	addCustomStyle(name, styleConfig) {
		if (!name || this.styles[name]) return false;
		this.styles[name] = { ...this.styles.default, ...styleConfig, name };
		return true;
	}

	removeCustomStyle(name) {
		// Don't allow removing built-in styles
		const builtIn = ['default', 'minimal', 'blueprint', 'neon', 'organic', 'wireframe'];
		if (builtIn.includes(name)) return false;
		if (this.styles[name]) {
			delete this.styles[name];
			if (this.currentStyle === name) this.currentStyle = 'default';
			return true;
		}
		return false;
	}
}

// ========================================================================
// EXPORTS
// ========================================================================

// Module exports
if (typeof module !== 'undefined' && module.exports) {
	module.exports = { DrawingStyleManager };
}

// Global exports for browser (standard JS)
if (typeof window !== 'undefined') {
	window.DrawingStyleManager = DrawingStyleManager;
}

console.log('[SchemaGraph] Drawing module loaded.');
