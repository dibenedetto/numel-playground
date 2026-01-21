// ========================================================================
// SCHEMAGRAPH CONTROLLERS
// Input controllers: Mouse, Touch, Keyboard, Voice
// Depends on: schemagraph-core.js (EventBus)
// ========================================================================

console.log('[SchemaGraph] Loading controllers module...');

// ========================================================================
// MOUSE/TOUCH CONTROLLER
// ========================================================================

class MouseTouchController {
	constructor(canvas, eventBus) {
		this.canvas = canvas;
		this.eventBus = eventBus;
		this.setupListeners();
	}

	setupListeners() {
		this.canvas.addEventListener('mousedown', (e) => this.handleMouseDown(e));
		this.canvas.addEventListener('mousemove', (e) => this.handleMouseMove(e));
		this.canvas.addEventListener('mouseup', (e) => this.handleMouseUp(e));
		this.canvas.addEventListener('dblclick', (e) => this.handleDoubleClick(e));
		this.canvas.addEventListener('wheel', (e) => this.handleWheel(e));
		this.canvas.addEventListener('contextmenu', (e) => this.handleContextMenu(e));
	}

	handleMouseDown(e) {
		this.eventBus.emit('mouse:down', {
			button: e.button,
			coords: this.getCanvasCoordinates(e),
			event: e
		});
	}

	handleMouseMove(e) {
		this.eventBus.emit('mouse:move', {
			coords: this.getCanvasCoordinates(e),
			event: e
		});
	}

	handleMouseUp(e) {
		this.eventBus.emit('mouse:up', {
			button: e.button,
			coords: this.getCanvasCoordinates(e),
			event: e
		});
	}

	handleDoubleClick(e) {
		this.eventBus.emit('mouse:dblclick', {
			coords: this.getCanvasCoordinates(e),
			event: e
		});
	}

	handleWheel(e) {
		e.preventDefault();
		this.eventBus.emit('mouse:wheel', {
			delta: e.deltaY,
			coords: this.getCanvasCoordinates(e),
			event: e
		});
	}

	handleContextMenu(e) {
		e.preventDefault();
		this.eventBus.emit('mouse:contextmenu', {
			coords: this.getCanvasCoordinates(e),
			event: e
		});
	}

	getCanvasCoordinates(e) {
		const rect = this.canvas.getBoundingClientRect();
		return {
			screenX: ((e.clientX - rect.left) / rect.width) * this.canvas.width,
			screenY: ((e.clientY - rect.top) / rect.height) * this.canvas.height,
			clientX: e.clientX,
			clientY: e.clientY,
			rect
		};
	}
}

// ========================================================================
// KEYBOARD CONTROLLER
// ========================================================================

class KeyboardController {
	constructor(eventBus) {
		this.eventBus = eventBus;
		document.addEventListener('keydown', (e) => this.eventBus.emit('keyboard:down', {
			key: e.key,
			code: e.code,
			event: e
		}));
		document.addEventListener('keyup', (e) => this.eventBus.emit('keyboard:up', {
			key: e.key,
			code: e.code,
			event: e
		}));
	}
}

// ========================================================================
// VOICE CONTROLLER
// ========================================================================

class VoiceController {
	constructor(eventBus) {
		this.eventBus = eventBus;
		this.recognition = null;
		this.isListening = false;

		if ('webkitSpeechRecognition' in window || 'SpeechRecognition' in window) {
			const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
			this.recognition = new SpeechRecognition();
			this.recognition.continuous = false;
			this.recognition.interimResults = false;

			this.recognition.onresult = (event) => this.eventBus.emit('voice:result', {
				transcript: event.results[0][0].transcript,
				confidence: event.results[0][0].confidence
			});

			this.recognition.onerror = (event) => this.eventBus.emit('voice:error', {
				error: event.error
			});

			this.recognition.onend = () => {
				this.isListening = false;
				this.eventBus.emit('voice:stopped', {});
			};
		}
	}

	startListening() {
		if (this.recognition && !this.isListening) {
			this.recognition.start();
			this.isListening = true;
			this.eventBus.emit('voice:started', {});
		}
	}

	stopListening() {
		if (this.recognition && this.isListening) {
			this.recognition.stop();
		}
	}
}

// ========================================================================
// EXPORTS
// ========================================================================

// Module exports
if (typeof module !== 'undefined' && module.exports) {
	module.exports = {
		MouseTouchController,
		KeyboardController,
		VoiceController
	};
}

// Global exports for browser (standard JS)
if (typeof window !== 'undefined') {
	window.MouseTouchController = MouseTouchController;
	window.KeyboardController = KeyboardController;
	window.VoiceController = VoiceController;
}

console.log('[SchemaGraph] Controllers module loaded.');
