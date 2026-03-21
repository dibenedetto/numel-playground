/* ========================================================================
   NUMEL API CLIENT
   Centralized HTTP client for all backend API calls.
   All numel-* modules should use this instead of raw fetch().
   ======================================================================== */

console.log('[Numel] Loading API client...');

class NumelAPI {
	constructor(baseUrl) {
		this.baseUrl = baseUrl;
	}

	// ── Core request methods ─────────────────────────────────────

	/**
	 * POST request returning the raw Response object.
	 * Use this when you need access to headers, status, or streaming.
	 */
	async post(endpoint, body = null) {
		const opts = { method: 'POST' };
		if (body != null) {
			opts.headers = { 'Content-Type': 'application/json' };
			opts.body = JSON.stringify(body);
		}
		const resp = await fetch(`${this.baseUrl}${endpoint}`, opts);
		if (!resp.ok) {
			let detail = resp.statusText;
			try { const err = await resp.json(); detail = JSON.stringify(err.detail || err, null, 2); } catch {}
			throw new Error(`${endpoint} failed: ${detail}`);
		}
		return resp;
	}

	/** POST and parse response as JSON. */
	async json(endpoint, body = null) {
		return (await this.post(endpoint, body)).json();
	}

	/** POST and return response as Blob. */
	async blob(endpoint, body = null) {
		return (await this.post(endpoint, body)).blob();
	}

	/** POST and return response as text. */
	async text(endpoint, body = null) {
		return (await this.post(endpoint, body)).text();
	}

	/** POST with a raw URL (not endpoint-relative). Returns the raw Response. */
	async postUrl(url) {
		const resp = await fetch(url, { method: 'POST' });
		if (!resp.ok) throw new Error(`Fetch failed: ${resp.status}`);
		return resp;
	}

	/**
	 * POST-fetch a URL and return a blob: URL suitable for element src.
	 * For data: URLs, returns them as-is (no network call).
	 */
	async fetchBlobUrl(url) {
		if (url.startsWith('data:')) return url;
		const resp = await fetch(url, { method: 'POST' });
		if (!resp.ok) throw new Error(`Fetch failed: ${resp.status}`);
		const blob = await resp.blob();
		return URL.createObjectURL(blob);
	}

	/** POST multipart/form-data (for file uploads). */
	async upload(endpoint, formData) {
		const resp = await fetch(`${this.baseUrl}${endpoint}`, {
			method: 'POST',
			body: formData,
		});
		if (!resp.ok) {
			let detail = resp.statusText;
			try { const err = await resp.json(); detail = JSON.stringify(err.detail || err, null, 2); } catch {}
			throw new Error(`${endpoint} failed: ${detail}`);
		}
		return resp.json();
	}

	// ── Workflow API ─────────────────────────────────────────────

	ping()                        { return this.json('/ping'); }
	getSchema()                   { return this.json('/schema'); }
	listWorkflows()               { return this.json('/list'); }
	getWorkflow(name)             { return this.json(`/get${name != null ? '/' + encodeURIComponent(name) : ''}`); }
	addWorkflow(workflow, name)   { return this.json('/add', { workflow, name }); }
	removeWorkflow(name)          { return this.json(`/remove${name != null ? '/' + encodeURIComponent(name) : ''}`); }
	startWorkflow(name, data)     { return this.json('/start', { name, initial_data: data }); }
	getExecState(executionId)     { return this.json(`/exec_state${executionId != null ? '/' + executionId : ''}`); }
	cancelExecution(executionId)  { return this.json(`/exec_cancel${executionId != null ? '/' + executionId : ''}`); }
	listExecutions()              { return this.json('/exec_list'); }
	provideUserInput(execId, nodeId, inputData) {
		return this.json(`/exec_input/${execId}`, { node_id: nodeId, input_data: inputData });
	}

	// ── Tool Call ────────────────────────────────────────────────

	toolCall(nodeIndex, args)     { return this.json('/tool_call', { node_index: nodeIndex, args }); }

	// ── Generation ───────────────────────────────────────────────

	generationPrompt(body = {})   { return this.json('/generation-prompt', body); }

	// ── Console API ──────────────────────────────────────────────

	consoleStart(opts = {})       { return this.json('/console/start', opts); }
	consoleStop()                 { return this.json('/console/stop'); }
	consoleContext()              { return this.json('/console/context'); }
	consoleStatus()               { return this.json('/console/status'); }
	consoleToolkits()             { return this.json('/console/toolkits'); }
	consoleChat(message, sessionId = null, includeContext = true) {
		return this.json('/console/chat', { message, session_id: sessionId, include_context: includeContext });
	}
	consoleMemoryClear()          { return this.json('/console/memory/clear'); }
	consolePlannerEnable(opts={}) { return this.json('/console/planner/enable', opts); }
	consolePlannerDisable()       { return this.json('/console/planner/disable'); }
	consolePlannerStatus()        { return this.json('/console/planner/status'); }
	consolePlannerReset()         { return this.json('/console/planner/reset'); }
	consolePlannerApply(wf)       { return this.json('/console/planner/apply', { workflow: wf }); }

	// ── Toolkits ─────────────────────────────────────────────────

	toolkitList()                  { return this.json('/toolkits/list'); }
	toolkitInspect(name)           { return this.json('/toolkits/inspect', { name }); }
	toolkitUpload(formData, overwrite = false) {
		return this.upload(`/toolkits/upload?overwrite=${overwrite}`, formData);
	}

	// ── File Upload / Contents ───────────────────────────────────

	contentsList(nodeIndex)       { return this.json(`/contents/list/${nodeIndex}`); }
	contentsRemove(nodeIndex, ids){ return this.json(`/contents/remove/${nodeIndex}`, { ids }); }
	uploadFile(nodeIndex, formData) { return this.upload(`/upload/${nodeIndex}`, formData); }

	// ── Chat Response ────────────────────────────────────────────

	chatResponse(executionId, nodeId, response) {
		return this.json(`/chat_response/${executionId}`, { node_id: String(nodeId), response });
	}

	// ── Memory API ───────────────────────────────────────────────

	memorySearch(query, n = 5, type = null)   { return this.json('/console/memory/search', { query, n_results: n, type }); }
	memoryAdd(content, type = 'general', metadata = {}, importance = 0.5) {
		return this.json('/console/memory/add', { content, type, metadata, importance });
	}
	memoryRecent(n = 10, type = null)          { return this.json('/console/memory/recent', { n, type }); }
	memoryDelete(id)                           { return this.json('/console/memory/delete', { id }); }
	memoryClear()                              { return this.json('/console/memory/clear'); }
	memoryStats()                              { return this.json('/console/memory/stats'); }

	// ── Channel API ──────────────────────────────────────────────

	channelTypes()                             { return this.json('/channels/types'); }
	channelList()                              { return this.json('/channels/list'); }
	channelAdd(opts)                           { return this.json('/channels/add', opts); }
	channelRemove(channelId)                   { return this.json('/channels/remove', { channel_id: channelId }); }
	channelStart(channelId)                    { return this.json('/channels/start', { channel_id: channelId }); }
	channelStop(channelId)                     { return this.json('/channels/stop', { channel_id: channelId }); }
	channelSend(channelId, recipientId, text)  { return this.json('/channels/send', { channel_id: channelId, recipient_id: recipientId, text }); }
	channelStatus(channelId)                   { return this.json('/channels/status', { channel_id: channelId }); }

	// ── Gallery API ──────────────────────────────────────────────

	galleryList(opts = {})                     { return this.json('/gallery/list', opts); }
	galleryGet(id)                             { return this.json('/gallery/get', { id }); }
	galleryPublish(opts)                       { return this.json('/gallery/publish', opts); }
	galleryRemove(id)                          { return this.json('/gallery/remove', { id }); }
	galleryCategories()                        { return this.json('/gallery/categories'); }
	galleryTags()                              { return this.json('/gallery/tags'); }

	// ── Agent Tasks API ──────────────────────────────────────────

	taskList()                                 { return this.json('/agent-tasks/list'); }
	taskGet(id)                                { return this.json('/agent-tasks/get', { id }); }
	taskCreate(opts)                           { return this.json('/agent-tasks/create', opts); }
	taskRemove(id)                             { return this.json('/agent-tasks/remove', { id }); }
	taskStart(id)                              { return this.json('/agent-tasks/start', { id }); }
	taskStop(id)                               { return this.json('/agent-tasks/stop', { id }); }
	taskRun(id)                                { return this.json('/agent-tasks/run', { id }); }

	// ── Published Apps API ───────────────────────────────────────

	appsList()                                 { return this.json('/apps/list'); }
	appsPublish(opts)                          { return this.json('/apps/publish', opts); }
	appsUnpublish(slug)                        { return this.json('/apps/unpublish', { slug }); }

}

// ========================================================================
// EXPORTS
// ========================================================================

if (typeof window !== 'undefined') {
	window.NumelAPI = NumelAPI;
}

console.log('[Numel] API client loaded');
