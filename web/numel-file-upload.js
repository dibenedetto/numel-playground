/* ========================================================================
   NUMEL FILE UPLOAD MANAGER
   Handles file uploads with two-phase visual feedback (upload + processing)
   ======================================================================== */

const UploadPhase = Object.freeze({
	IDLE: 'idle',
	UPLOADING: 'uploading',
	PROCESSING: 'processing',
	COMPLETED: 'completed',
	ERROR: 'error'
});

const PhaseColors = Object.freeze({
	[UploadPhase.IDLE]: null,
	[UploadPhase.UPLOADING]: '#3182ce',    // Blue - uploading
	[UploadPhase.PROCESSING]: '#805ad5',   // Purple - processing
	[UploadPhase.COMPLETED]: '#38a169',    // Green - success
	[UploadPhase.ERROR]: '#e53e3e',        // Red - error
});

const PhaseLabels = Object.freeze({
	[UploadPhase.IDLE]: '',
	[UploadPhase.UPLOADING]: 'Uploading...',
	[UploadPhase.PROCESSING]: 'Processing...',
	[UploadPhase.COMPLETED]: 'Complete',
	[UploadPhase.ERROR]: 'Error',
});


class FileUploadManager {
	constructor(baseUrl, app, syncCallback, eventBus) {
		this.baseUrl = baseUrl;
		this.app = app;
		this.syncCallback = syncCallback || function() {};
		this.eventBus = eventBus;
		this.activeUploads = new Map();  // uploadId -> state
		this._flashAnimating = false;
		
		this._setupListeners();
		this._injectStyles();
	}

	_setupListeners() {
		// Handle file drops on nodes
		this.eventBus.on('node:fileDrop', (e) => this._handleFileDrop(e));
		
		// Handle button clicks that trigger file selection
		this.eventBus.on('node:buttonClicked', (e) => this._handleButtonClick(e));
		
		// Listen for WebSocket events from backend
		this._setupBackendEventListeners();
	}

	_setupBackendEventListeners() {
		// These events come through the WorkflowClient WebSocket
		// They're forwarded by the client to the eventBus
		
		this.eventBus.on('upload.started', (e) => this._onBackendUploadStarted(e));
		this.eventBus.on('upload.completed', (e) => this._onBackendUploadCompleted(e));
		this.eventBus.on('upload.failed', (e) => this._onBackendUploadFailed(e));
		this.eventBus.on('processing.started', (e) => this._onBackendProcessingStarted(e));
		this.eventBus.on('processing.completed', (e) => this._onBackendProcessingCompleted(e));
		this.eventBus.on('processing.failed', (e) => this._onBackendProcessingFailed(e));
	}

	// ================================================================
	// Backend Event Handlers
	// ================================================================

	_onBackendUploadStarted(event) {
		const { node_index, upload_id, file_count, filenames } = event.data || {};
		const node = this._getNodeByWorkflowIndex(node_index);
		
		if (node) {
			this._setNodePhase(node, UploadPhase.UPLOADING, {
				uploadId: upload_id,
				fileCount: file_count,
				filenames,
			});
		}
		
		this.eventBus.emit('fileUpload:phaseChanged', {
			phase: UploadPhase.UPLOADING,
			nodeIndex: node_index,
			uploadId: upload_id,
		});
	}

	_onBackendUploadCompleted(event) {
		const { node_index, upload_id, file_count, total_size } = event.data || {};
		const node = this._getNodeByWorkflowIndex(node_index);
		
		// Upload done, but processing may follow - don't unlock yet
		// Visual state will transition to PROCESSING if handler exists
		
		this.eventBus.emit('fileUpload:uploadComplete', {
			nodeIndex: node_index,
			uploadId: upload_id,
			fileCount: file_count,
			totalSize: total_size,
		});
	}

	_onBackendUploadFailed(event) {
		const { node_index, upload_id } = event.data || {};
		const error = event.error;
		const node = this._getNodeByWorkflowIndex(node_index);
		
		if (node) {
			this._setNodePhase(node, UploadPhase.ERROR, { error });
			this._schedulePhaseReset(node, 3000);
		}
		
		this._unlockGraph();
		
		this.eventBus.emit('fileUpload:failed', {
			phase: UploadPhase.UPLOADING,
			nodeIndex: node_index,
			uploadId: upload_id,
			error,
		});
	}

	_onBackendProcessingStarted(event) {
		this.app.api.lock.lock('Processing uploaded files');

		const { node_index, upload_id, handler } = event.data || {};
		const node = this._getNodeByWorkflowIndex(node_index);
		
		if (node) {
			this._setNodePhase(node, UploadPhase.PROCESSING, {
				uploadId: upload_id,
				handler,
			});
		}
		
		this.eventBus.emit('fileUpload:phaseChanged', {
			phase: UploadPhase.PROCESSING,
			nodeIndex: node_index,
			uploadId: upload_id,
		});
	}

	_onBackendProcessingCompleted(event) {
		const { node_index, upload_id, result } = event.data || {};
		const node = this._getNodeByWorkflowIndex(node_index);
		
		if (node) {
			this._setNodePhase(node, UploadPhase.COMPLETED, { result });
			this._flashNode(node, 'success');
			this._schedulePhaseReset(node, 2000);
		}
		
		this._unlockGraph();
		
		this.eventBus.emit('fileUpload:completed', {
			nodeIndex: node_index,
			uploadId: upload_id,
			result,
		});
	}

	_onBackendProcessingFailed(event) {
		const { node_index, upload_id } = event.data || {};
		const error = event.error;
		const node = this._getNodeByWorkflowIndex(node_index);
		
		if (node) {
			this._setNodePhase(node, UploadPhase.ERROR, { error });
			this._flashNode(node, 'error');
			this._schedulePhaseReset(node, 3000);
		}
		
		this._unlockGraph();
		
		this.eventBus.emit('fileUpload:failed', {
			phase: UploadPhase.PROCESSING,
			nodeIndex: node_index,
			uploadId: upload_id,
			error,
		});
	}

	// ================================================================
	// File Drop Handling
	// ================================================================

	async _handleFileDrop(event) {
		const { nodeId, files, dropZone } = event;
		
		if (!files || files.length === 0) return;
		
		const node = this.app.graph.getNodeById(nodeId);
		if (!node) return;
		
		console.log(`[FileUpload] Drop on node ${nodeId}:`, files.length, 'files');
		
		await this.uploadFiles(node, files, null, dropZone);
	}

	// ================================================================
	// Button Click Handling
	// ================================================================

	_handleButtonClick(event) {
		const { nodeId, buttonId, buttonConfig } = event;
		
		if (!this._isFileButton(buttonId, buttonConfig)) return;
		
		const node = this.app.graph.getNodeById(nodeId);
		if (!node) return;
		
		// Don't allow if graph is locked
		if (this.app.isLocked) {
			console.log('[FileUpload] Graph is locked, ignoring button click');
			return;
		}
		
		console.log(`[FileUpload] Button ${buttonId} on node ${nodeId}`);
		
		this._openFilePicker(node, buttonId, buttonConfig);
	}

	_isFileButton(buttonId, config) {
		const fileButtonIds = ['import', 'upload', 'add_file', 'browse'];
		if (fileButtonIds.includes(buttonId)) return true;
		if (config?.type === 'file') return true;
		if (config?.accept) return true;
		return false;
	}

	_openFilePicker(node, buttonId, config) {
		const input = document.createElement('input');
		input.type = 'file';
		input.multiple = config?.multiple !== false;
		
		const accept = config?.accept || this._getNodeAcceptFilter(node);
		if (accept) input.accept = accept;
		
		input.onchange = async (e) => {
			const files = Array.from(e.target.files);
			if (files.length > 0) {
				await this.uploadFiles(node, files, buttonId);
			}
		};
		
		input.click();
	}

	_getNodeAcceptFilter(node) {
		const dropzoneConfig = node._dropzoneConfig || node.dropzoneConfig;
		if (dropzoneConfig?.accept) return dropzoneConfig.accept;
		
		const typeFilters = {
			'knowledge_manager_config': '.csv,.doc,.docx,.json,.md,.pdf,.pptx,.txt,.xls,.xlsx',
			'content_db_config': '.json,.txt',
			'index_db_config': '.json,.txt',
			'data_text': '.txt,.md,.json',
			'data_document': '.pdf,.doc,.docx',
			'data_image': '.png,.jpg,.jpeg,.gif,.webp,.svg',
			'data_audio': '.mp3,.wav,.ogg,.m4a',
			'data_video': '.mp4,.webm,.mov,.avi',
		};
		
		return typeFilters[node.workflowType] || '*';
	}

	_ensureStableId(node) {
		// Use existing stable ID or create one
		if (node.workflowId) return node.workflowId;
		if (node.extra?.id) return node.extra.id;
		if (node.annotations?.id) return node.annotations.id;
		
		// Generate and store a stable ID
		const stableId = `node_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
		node.extra = node.extra || {};
		node.extra._uploadStableId = stableId;
		
		return stableId;
	}

	_findNodeByStableId(stableId) {
		for (const n of this.app.graph.nodes) {
			if (n.workflowId === stableId) return n;
			if (n.extra?.id === stableId) return n;
			if (n.annotations?.id === stableId) return n;
			if (n.extra?._uploadStableId === stableId) return n;
		}
		return null;
	}

	// ================================================================
	// Upload Logic
	// ================================================================

	async uploadFiles(node, files, buttonId = null, dropZone = null) {
		// Ensure node has a stable ID before sync
		const stableId = this._ensureStableId(node);
		
		// Sync workflow (assigns workflowIndex to new nodes)
		await this.syncCallback();
		
		// Re-find node after sync (old reference is stale)
		node = this._findNodeByStableId(stableId);
		if (!node) {
			console.error('[FileUpload] Node not found after sync');
			this._emitError(null, 'Node lost during sync');
			return null;
		}
		
		const nodeIndex = node.workflowIndex;
		if (nodeIndex === undefined || nodeIndex === null) {
			console.error('[FileUpload] Node still has no workflow index after sync');
			this._emitError(node, 'Node not part of workflow');
			return null;
		}

		// Lock graph
		this._lockGraph('Uploading files');

		// Set initial visual state
		this._setNodePhase(node, UploadPhase.UPLOADING, {
			fileCount: files.length,
			filenames: files.map(f => f.name),
		});

		// Create FormData
		const formData = new FormData();
		
		for (const file of files) {
			formData.append('files', file);
		}
		
		if (node.workflowType) {
			formData.append('node_type', node.workflowType);
		}
		
		if (buttonId) {
			formData.append('button_id', buttonId);
		}

		try {
			const response = await fetch(`${this.baseUrl}/upload/${nodeIndex}`, {
				method: 'POST',
				body: formData,
			});

			if (!response.ok) {
				const error = await response.text();
				throw new Error(error || `Upload failed: ${response.status}`);
			}

			const result = await response.json();

			// If no handler was invoked, complete immediately
			if (!result.handler_result && result.status === 'completed') {
				this._setNodePhase(node, UploadPhase.COMPLETED);
				this._flashNode(node, 'success');
				this._schedulePhaseReset(node, 2000);
				this._unlockGraph();
			}
			// Otherwise, backend events will handle phase transitions

			console.log(`[FileUpload] Response:`, result);
			return result;

		} catch (error) {
			console.error('[FileUpload] Error:', error);

			this._setNodePhase(node, UploadPhase.ERROR, { error: error.message });
			this._flashNode(node, 'error');
			this._schedulePhaseReset(node, 3000);
			this._unlockGraph();

			this.eventBus.emit('fileUpload:failed', {
				nodeId: node.id,
				nodeIndex,
				error: error.message,
			});

			return null;
		}
	}

	// ================================================================
	// Graph Locking
	// ================================================================

	_lockGraph(message) {
		if (this.app.api?.lock) {
			this.app.api.lock.lock(message);
		} else {
			this.app.isLocked = true;
		}
		
		this.eventBus.emit('fileUpload:graphLocked', { message });
	}

	_unlockGraph() {
		if (this.app.api?.lock) {
			this.app.api.lock.unlock();
		} else {
			this.app.isLocked = false;
		}
		
		this.eventBus.emit('fileUpload:graphUnlocked', {});
	}

	// ================================================================
	// Visual Feedback
	// ================================================================

	_setNodePhase(node, phase, data = {}) {
		// Store previous state on first phase change
		if (!node._uploadOriginalColor && phase !== UploadPhase.IDLE) {
			node._uploadOriginalColor = node.color;
		}
		
		node._uploadPhase = phase;
		node._uploadPhaseData = data;
		node._uploadPhaseTime = Date.now();
		
		// Update color
		node.color = PhaseColors[phase] || node._uploadOriginalColor;
		
		// Update overlay if exists
		this._updateNodeOverlay(node, phase, data);
		
		this.app.draw?.();
	}

	_updateNodeOverlay(node, phase, data) {
		// Create or update status overlay on node
		let overlay = document.getElementById(`upload-overlay-${node.id}`);
		
		if (phase === UploadPhase.IDLE) {
			overlay?.remove();
			return;
		}
		
		if (!overlay) {
			overlay = document.createElement('div');
			overlay.id = `upload-overlay-${node.id}`;
			overlay.className = 'sg-upload-overlay';
			this.app.canvas.parentElement.appendChild(overlay);
		}
		
		// Update content
		const label = PhaseLabels[phase];
		const icon = this._getPhaseIcon(phase);
		const detail = this._getPhaseDetail(phase, data);
		
		overlay.innerHTML = `
			<div class="sg-upload-overlay-content sg-upload-phase-${phase}">
				<span class="sg-upload-icon">${icon}</span>
				<span class="sg-upload-label">${label}</span>
				${detail ? `<span class="sg-upload-detail">${detail}</span>` : ''}
			</div>
		`;
		
		// Position overlay
		this._positionNodeOverlay(node, overlay);
	}

	_getPhaseIcon(phase) {
		switch (phase) {
			case UploadPhase.UPLOADING: return '⬆️';
			case UploadPhase.PROCESSING: return '⚙️';
			case UploadPhase.COMPLETED: return '✅';
			case UploadPhase.ERROR: return '❌';
			default: return '';
		}
	}

	_getPhaseDetail(phase, data) {
		switch (phase) {
			case UploadPhase.UPLOADING:
				if (data.fileCount) {
					return `${data.fileCount} file(s)`;
				}
				return null;
			case UploadPhase.PROCESSING:
				return data.handler || null;
			case UploadPhase.ERROR:
				return data.error || null;
			default:
				return null;
		}
	}

	_positionNodeOverlay(node, overlay) {
		const camera = this.app.camera;
		
		const screenX = node.pos[0] * camera.scale + camera.x;
		const screenY = node.pos[1] * camera.scale + camera.y;
		const screenW = node.size[0] * camera.scale;
		
		// Position at top of node
		overlay.style.left = `${screenX + screenW / 2}px`;
		overlay.style.top = `${screenY - 10}px`;
		overlay.style.transform = 'translate(-50%, -100%)';
		overlay.style.zIndex = '10001';
	}

	_schedulePhaseReset(node, delay) {
		setTimeout(() => {
			if (node._uploadPhase === UploadPhase.COMPLETED || 
				node._uploadPhase === UploadPhase.ERROR) {
				this._resetNodePhase(node);
			}
		}, delay);
	}

	_resetNodePhase(node) {
		// Restore original color
		if (node._uploadOriginalColor) {
			node.color = node._uploadOriginalColor;
			delete node._uploadOriginalColor;
		}
		
		delete node._uploadPhase;
		delete node._uploadPhaseData;
		delete node._uploadPhaseTime;
		
		// Remove overlay
		const overlay = document.getElementById(`upload-overlay-${node.id}`);
		overlay?.remove();
		
		this.app.draw?.();
	}

	_flashNode(node, type) {
		node._flashStart = performance.now();
		node._flashDuration = 600;
		node._flashType = type;
		node._isFlashing = true;
		
		this._animateFlash();
	}

	_animateFlash() {
		if (this._flashAnimating) return;
		this._flashAnimating = true;
		
		const animate = () => {
			const now = performance.now();
			let anyFlashing = false;
			
			for (const node of this.app.graph.nodes) {
				if (!node._isFlashing) continue;
				
				const elapsed = now - node._flashStart;
				if (elapsed < node._flashDuration) {
					node._flashProgress = elapsed / node._flashDuration;
					anyFlashing = true;
				} else {
					node._isFlashing = false;
					node._flashProgress = 0;
				}
			}
			
			this.app.draw?.();
			
			if (anyFlashing) {
				requestAnimationFrame(animate);
			} else {
				this._flashAnimating = false;
			}
		};
		
		requestAnimationFrame(animate);
	}

	// ================================================================
	// Helpers
	// ================================================================

	_getNodeByWorkflowIndex(index) {
		if (index === undefined || index === null) return null;
		return this.app.graph.nodes.find(n => n.workflowIndex === index);
	}

	_emitError(node, message) {
		this.eventBus.emit('fileUpload:error', {
			nodeId: node?.id,
			error: message,
		});
	}

	// ================================================================
	// Styles
	// ================================================================

	_injectStyles() {
		if (document.getElementById('sg-upload-styles')) return;
		
		const style = document.createElement('style');
		style.id = 'sg-upload-styles';
		style.textContent = `
			.sg-upload-overlay {
				position: absolute;
				pointer-events: none;
				font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
				font-size: 11px;
				z-index: 10001;
			}
			
			.sg-upload-overlay-content {
				display: flex;
				align-items: center;
				gap: 6px;
				padding: 6px 12px;
				border-radius: 6px;
				background: rgba(0, 0, 0, 0.85);
				color: #fff;
				white-space: nowrap;
				box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
			}
			
			.sg-upload-phase-uploading {
				border: 1px solid #3182ce;
			}
			
			.sg-upload-phase-processing {
				border: 1px solid #805ad5;
			}
			
			.sg-upload-phase-completed {
				border: 1px solid #38a169;
			}
			
			.sg-upload-phase-error {
				border: 1px solid #e53e3e;
			}
			
			.sg-upload-icon {
				font-size: 14px;
			}
			
			.sg-upload-label {
				font-weight: 600;
			}
			
			.sg-upload-detail {
				opacity: 0.7;
				font-size: 10px;
				max-width: 150px;
				overflow: hidden;
				text-overflow: ellipsis;
			}
			
			/* Pulsing animation for active phases */
			.sg-upload-phase-uploading .sg-upload-icon,
			.sg-upload-phase-processing .sg-upload-icon {
				animation: sg-upload-pulse 1s ease-in-out infinite;
			}
			
			@keyframes sg-upload-pulse {
				0%, 100% { opacity: 1; }
				50% { opacity: 0.5; }
			}
		`;
		
		document.head.appendChild(style);
	}

	// ================================================================
	// Update overlay positions on camera change
	// ================================================================

	updateOverlayPositions() {
		for (const node of this.app.graph.nodes) {
			if (node._uploadPhase && node._uploadPhase !== UploadPhase.IDLE) {
				const overlay = document.getElementById(`upload-overlay-${node.id}`);
				if (overlay) {
					this._positionNodeOverlay(node, overlay);
				}
			}
		}
	}

	// ================================================================
	// Cleanup
	// ================================================================

	destroy() {
		// Remove all overlays
		for (const node of this.app.graph.nodes) {
			const overlay = document.getElementById(`upload-overlay-${node.id}`);
			overlay?.remove();
		}
		
		this.activeUploads.clear();
		
		// Ensure graph is unlocked
		this._unlockGraph();
	}
}

// Export
if (typeof window !== 'undefined') {
	window.FileUploadManager = FileUploadManager;
	window.UploadPhase = UploadPhase;
}
