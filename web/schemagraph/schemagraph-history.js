// ========================================================================
// SCHEMAGRAPH HISTORY
// Undo/Redo command pattern: delta commands + snapshot commands
// ========================================================================

console.log('[SchemaGraph] Loading history module...');

// ========================================================================
// BASE COMMAND
// ========================================================================

class HistoryCmd {
	constructor(label) { this.label = label || 'Action'; }
	undo(app) {}
	redo(app) {}
}

// ========================================================================
// SNAPSHOT COMMAND — serialize before/after for topology changes
// (node create/delete, link create/delete, graph clear)
// ========================================================================

class SnapshotCmd extends HistoryCmd {
	constructor(label, before, after) {
		super(label);
		this.before = before;
		this.after  = after;
	}
	undo(app) { app._historyRestore(this.before); }
	redo(app) { app._historyRestore(this.after);  }
}

// ========================================================================
// MOVE NODES COMMAND — pure delta, no serialization
// deltas: [{ nodeId, ox, oy, nx, ny }]
// ========================================================================

class MoveNodesCmd extends HistoryCmd {
	constructor(deltas) {
		super('Move');
		this.deltas = deltas;
	}
	undo(app) {
		for (const { nodeId, ox, oy } of this.deltas) {
			const n = app.graph.getNodeById(nodeId);
			if (n) { n.pos[0] = ox; n.pos[1] = oy; }
		}
		app._historyAfterDelta();
	}
	redo(app) {
		for (const { nodeId, nx, ny } of this.deltas) {
			const n = app.graph.getNodeById(nodeId);
			if (n) { n.pos[0] = nx; n.pos[1] = ny; }
		}
		app._historyAfterDelta();
	}
}

// ========================================================================
// RESIZE NODE COMMAND — pure delta
// ========================================================================

class ResizeNodeCmd extends HistoryCmd {
	constructor(nodeId, oldSize, newSize) {
		super('Resize');
		this.nodeId  = nodeId;
		this.oldSize = oldSize;
		this.newSize = newSize;
	}
	undo(app) {
		const n = app.graph.getNodeById(this.nodeId);
		if (n) { n.size[0] = this.oldSize[0]; n.size[1] = this.oldSize[1]; }
		app._historyAfterDelta();
	}
	redo(app) {
		const n = app.graph.getNodeById(this.nodeId);
		if (n) { n.size[0] = this.newSize[0]; n.size[1] = this.newSize[1]; }
		app._historyAfterDelta();
	}
}

// ========================================================================
// TITLE COMMAND — pure delta for node display title changes
// ========================================================================

class TitleCmd extends HistoryCmd {
	constructor(nodeId, oldTitle, newTitle) {
		super('Rename');
		this.nodeId   = nodeId;
		this.oldTitle = oldTitle;
		this.newTitle = newTitle;
	}
	undo(app) {
		const n = app.graph.getNodeById(this.nodeId);
		if (n) n.displayTitle = this.oldTitle;
		app._historyAfterDelta();
	}
	redo(app) {
		const n = app.graph.getNodeById(this.nodeId);
		if (n) n.displayTitle = this.newTitle;
		app._historyAfterDelta();
	}
}

// ========================================================================
// HISTORY MANAGER
// ========================================================================

class HistoryManager {
	constructor(maxSize = 100) {
		this.undoStack = [];
		this.redoStack = [];
		this.maxSize   = maxSize;
	}

	push(cmd) {
		this.undoStack.push(cmd);
		if (this.undoStack.length > this.maxSize) this.undoStack.shift();
		this.redoStack = [];  // new action clears redo
	}

	undo(app) {
		if (!this.undoStack.length) return false;
		const cmd = this.undoStack.pop();
		cmd.undo(app);
		this.redoStack.push(cmd);
		return true;
	}

	redo(app) {
		if (!this.redoStack.length) return false;
		const cmd = this.redoStack.pop();
		cmd.redo(app);
		this.undoStack.push(cmd);
		return true;
	}

	canUndo() { return this.undoStack.length > 0; }
	canRedo() { return this.redoStack.length > 0; }

	peekUndo() { return this.undoStack.length ? this.undoStack[this.undoStack.length - 1].label : null; }
	peekRedo() { return this.redoStack.length ? this.redoStack[this.redoStack.length - 1].label : null; }

	clear() { this.undoStack = []; this.redoStack = []; }

	loadStacks(undoStack, redoStack) {
		this.undoStack = undoStack || [];
		this.redoStack = redoStack || [];
	}
}

// ========================================================================
// EXPORTS
// ========================================================================

if (typeof module !== 'undefined' && module.exports) {
	module.exports = { HistoryCmd, SnapshotCmd, MoveNodesCmd, ResizeNodeCmd, TitleCmd, HistoryManager };
}

if (typeof window !== 'undefined') {
	window.HistoryCmd    = HistoryCmd;
	window.SnapshotCmd   = SnapshotCmd;
	window.MoveNodesCmd  = MoveNodesCmd;
	window.ResizeNodeCmd = ResizeNodeCmd;
	window.TitleCmd      = TitleCmd;
	window.HistoryManager = HistoryManager;
}

console.log('[SchemaGraph] History module loaded.');
