/* ========================================================================
   NUMEL API CLIENT
   Centralized HTTP client for all backend API calls.
   All numel-* modules should use this instead of raw fetch().
   ======================================================================== */

console.log('[Numel] Loading API client...');

class NumelAPI {
	constructor(baseUrl) {
		this.baseUrl = baseUrl;
		// Stable per-tab session ID — used for per-tab request scoping and event correlation
		this.sessionId = sessionStorage.getItem('numel_session_id');
		if (!this.sessionId) {
			this.sessionId = 'sess_' + crypto.randomUUID().replace(/-/g, '').slice(0, 16);
			sessionStorage.setItem('numel_session_id', this.sessionId);
		}
	}

	_sameOrigin(url) {
		try {
			const base = new URL(this.baseUrl || window.location.origin, window.location.origin);
			const target = new URL(url, base);
			return target.origin === base.origin;
		} catch {
			return false;
		}
	}

	_authHeaders(includeJson = false, requestUrl = null) {
		const headers = {};
		if (includeJson) headers['Content-Type'] = 'application/json';
		if (requestUrl && !this._sameOrigin(requestUrl)) return headers;

		const token = window._numelToken || localStorage.getItem('numel_token');
		if (token) headers['Authorization'] = `Bearer ${token}`;
		if (this.sessionId) headers['X-Session-Id'] = this.sessionId;
		return headers;
	}

	// ── Core request methods ─────────────────────────────────────

	/**
	 * POST request returning the raw Response object.
	 * Use this when you need access to headers, status, or streaming.
	 */
	async post(endpoint, body = null, requestOpts = {}) {
		const opts = { method: 'POST', headers: this._authHeaders(body != null) };
		if (body != null) {
			opts.body = JSON.stringify(body);
		}
		if (requestOpts && requestOpts.signal) {
			opts.signal = requestOpts.signal;
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
	async json(endpoint, body = null, requestOpts = {}) {
		return (await this.post(endpoint, body, requestOpts)).json();
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
		const resp = await fetch(url, {
			method: 'POST',
			headers: this._authHeaders(false, url),
		});
		if (!resp.ok) throw new Error(`Fetch failed: ${resp.status}`);
		return resp;
	}

	/**
	 * POST-fetch a URL and return a blob: URL suitable for element src.
	 * For data: URLs, returns them as-is (no network call).
	 */
	async fetchBlobUrl(url) {
		if (url.startsWith('data:')) return url;
		const resp = await fetch(url, {
			method: 'POST',
			headers: this._authHeaders(false, url),
		});
		if (!resp.ok) throw new Error(`Fetch failed: ${resp.status}`);
		const blob = await resp.blob();
		return URL.createObjectURL(blob);
	}

	/** POST multipart/form-data (for file uploads). */
	async upload(endpoint, formData) {
		const resp = await fetch(`${this.baseUrl}${endpoint}`, {
			method: 'POST',
			headers: this._authHeaders(),
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
	async getSchema() {
		const requestUrl = `${this.baseUrl}/schema-bootstrap`;
		const resp = await fetch(requestUrl, {
			method: 'GET',
			headers: this._authHeaders(false, requestUrl),
		});
		if (!resp.ok) {
			let detail = resp.statusText;
			try { const err = await resp.json(); detail = JSON.stringify(err.detail || err, null, 2); } catch {}
			throw new Error(`/schema-bootstrap failed: ${detail}`);
		}
		return resp.json();
	}
	getCurrentSpace()             { return this.json('/spaces/current'); }
	listSpaces()                  { return this.json('/spaces/list'); }
	createSpace(title, slug = null, description = '') {
		return this.json('/spaces/create', { title, slug, description, visibility: 'private' });
	}
	updateSpace(spaceId, updates = {})  {
		return this.json(`/platform/spaces/${encodeURIComponent(spaceId)}/update`, updates || {});
	}
	forkSpace(spaceId, title = null, slug = null) {
		return this.json('/spaces/fork', { space_id: spaceId, title, slug });
	}
	resolvePublicSpace(namespace, slug) { return this.json('/spaces/public/resolve', { namespace, slug }); }
	listPublicNamespaceSpaces(namespace) { return this.json('/spaces/public/namespace', { namespace }); }
	publicCreatorPage(creator, limit = 12) { return this.json('/spaces/public/creator', { creator, limit }); }
	publicRepoPage(namespace, slug, ref = null, limit = 12) { return this.json('/spaces/public/repo', { namespace, slug, ref, limit }); }
	readPublicRepoAsset(namespace, slug, path, ref = null) { return this.json('/spaces/public/repo/assets/read', { namespace, slug, path, ref }); }
	comparePublicRepo(namespace, slug, left, right = null, path = '', limit = 200) {
		return this.json('/spaces/public/repo/compare', { namespace, slug, left, right, path, limit });
	}
	selectSpace(spaceId)          { return this.json('/spaces/select', { space_id: spaceId }); }
	deleteSpace(spaceId)          { return this.json('/spaces/delete', { space_id: spaceId }); }
	repoRefs()                    { return this.json('/spaces/repo/refs'); }
	setRepoRef(name)              { return this.json('/spaces/repo/ref/set', { name }); }
	createRepoRef(name, kind = 'branch', fromRef = null) {
		return this.json('/spaces/repo/refs/create', { name, kind, from_ref: fromRef });
	}
	deleteRepoRef(name)           { return this.json('/spaces/repo/refs/delete', { name }); }
	repoHistory(limit = 20)       { return this.json('/spaces/repo/history', { limit }); }
	compareRepo(left, right = null, path = '', limit = 200) {
		return this.json('/spaces/repo/compare', { left, right, path, limit });
	}
	repoAssets(prefix = '')       { return this.json('/spaces/repo/assets', { prefix }); }
	readRepoAsset(path)           { return this.json('/spaces/repo/assets/read', { path }); }
	writeRepoAsset(opts = {})     { return this.json('/spaces/repo/assets/write', opts); }
	openRepoAsset(path)           { return this.json('/spaces/repo/assets/open', { path }); }
	restoreRepo(source, note = null) { return this.json('/spaces/repo/restore', { source, note }); }
	getWorkflow()                 { return this.json('/workflow/get'); }
	importWorkflowDocument(document, opts = {}) {
		return this.json('/workflow/interop/import', {
			document,
			source_format: opts?.sourceFormat || null,
			file_name: opts?.fileName || null,
		});
	}
	validateWorkflow(workflow, opts = {}) { return this.json('/workflow/validate', { workflow, ...opts }); }
	saveWorkflow(workflow, opts = {}) { return this.json('/workflow/save', { workflow, ...(opts || {}) }); }
	ensureWorkflowImpl()          { return this.json('/workflow/impl'); }
	deleteWorkflow()              { return this.json('/workflow/delete'); }
	workflowHistory(limit = 20)   { return this.json('/workflow/history', { limit }); }
	restoreWorkflowSnapshot(commitId, note = null) { return this.json('/workflow/restore', { commit_id: commitId, note }); }
	publishWorkflowTemplate(opts = {}) { return this.json('/workflow/publish-template', opts); }
	startWorkflow(data = null)    { return this.json('/workflow/start', { initial_data: data }); }
	getExecState(executionId)     { return this.json(`/executions/${encodeURIComponent(executionId)}`); }
	cancelExecution(executionId)  { return this.json(`/executions/${encodeURIComponent(executionId)}/cancel`); }
	getExecutionResults(executionId) { return this.json(`/executions/${encodeURIComponent(executionId)}/results`); }
	listExecutions()              { return this.json('/executions/list'); }
	provideUserInput(execId, nodeId, inputData) {
		return this.json(`/executions/${encodeURIComponent(execId)}/input`, { node_id: nodeId, input_data: inputData });
	}

	// ── Tool Call ────────────────────────────────────────────────

	toolCall(nodeIndex, args)     { return this.json('/tool_call', { node_index: nodeIndex, args }); }

	// ── Generation ───────────────────────────────────────────────

	generationPrompt(body = {})   { return this.json('/generation-prompt', body); }
	options(providerKey, body = {}) { return this.json(`/options/${encodeURIComponent(providerKey)}`, body); }

	// ── Proactive Substrate (Phase 3 M3.3 + M3.4) ────────────────

	proactiveVitals()               { return this.json('/proactive/vitals'); }
	proactiveLedger(opts = {})      { return this.json('/proactive/ledger', opts); }
	proactiveQuarantine()           { return this.json('/proactive/quarantine'); }
	proactiveQuarantineRelease(key, reason = 'manual') { return this.json('/proactive/quarantine/release', { key, reason }); }
	proactiveSnapshots()            { return this.json('/proactive/snapshots'); }
	proactiveSnapshotTake(label = '') { return this.json('/proactive/snapshot/take', { label }); }
	proactiveSnapshotRestore(id)    { return this.json('/proactive/snapshot/restore', { snapshot_id: id }); }
	proactiveSnapshotDelete(id)     { return this.json('/proactive/snapshot/delete', { snapshot_id: id }); }

	// ── Phase 4 (M4.1) Alignment ─────────────────────────────────

	proactiveFeedback(target_id, kind, value, context = {}) {
		return this.json('/proactive/feedback', { target_id, kind, value, context });
	}
	proactiveFeedbackList(opts = {})         { return this.json('/proactive/feedback/list', opts); }
	proactiveConstitution()                  { return this.json('/proactive/constitution'); }
	proactiveConstitutionUpdate(patch)       { return this.json('/proactive/constitution/update', { patch }); }
	proactiveAlignmentValidators()           { return this.json('/proactive/alignment/validators'); }
	proactiveAlignmentCheck(candidate)       { return this.json('/proactive/alignment/check', { candidate }); }

	// ── Phase 4 (M4.2) Optimization ──────────────────────────────

	proactiveOptimizationPropose()           { return this.json('/proactive/optimization/propose'); }
	proactiveOptimizationSimulate(candidate) { return this.json('/proactive/optimization/simulate', { candidate }); }

	// ── Phase 4 (M4.3) Promotion gate ────────────────────────────

	proactivePromote(candidate, simulate = true) {
		return this.json('/proactive/promotion/promote', { candidate, simulate });
	}

	// ── Phase 5 (M5.1) MCP — external integrations ───────────────

	proactiveMcpTools()                            { return this.json('/proactive/mcp/tools'); }
	proactiveMcpCall(name, args = {})              { return this.json('/proactive/mcp/call', { name, arguments: args }); }
	proactiveMcpRegisterRemote(server, tool, scopes = null) {
		const body = { server, tool };
		if (scopes) body.scopes = scopes;
		return this.json('/proactive/mcp/register_remote', body);
	}
	proactiveMcpRemoteTools()                      { return this.json('/proactive/mcp/remote_tools'); }
	proactiveMcpDropRemote(name)                   { return this.json('/proactive/mcp/drop_remote', { name }); }
	proactiveMcpCalls(limit = 25)                  { return this.json('/proactive/mcp/calls', { limit }); }

	// ── Phase 5 (M5.2) A2A federation ────────────────────────────

	proactiveA2aPeers()                                { return this.json('/proactive/a2a/peers'); }
	proactiveA2aRegisterPeer(peer_id, tier, name=null, contact=null) {
		const body = { peer_id, tier };
		if (name)    body.name    = name;
		if (contact) body.contact = contact;
		return this.json('/proactive/a2a/peers/register', body);
	}
	proactiveA2aDropPeer(peer_id)                      { return this.json('/proactive/a2a/peers/drop', { peer_id }); }
	proactiveA2aReceive(peer_id, message, kind='message') { return this.json('/proactive/a2a/receive', { peer_id, message, kind }); }
	proactiveA2aSend(peer_id, message, kind='message')    { return this.json('/proactive/a2a/send',    { peer_id, message, kind }); }
	proactiveA2aShareState(peer_id, namespaces)        { return this.json('/proactive/a2a/share_state', { peer_id, namespaces }); }
	proactiveA2aInbox(limit=25)                        { return this.json('/proactive/a2a/inbox',  { limit }); }
	proactiveA2aOutbox(limit=25)                       { return this.json('/proactive/a2a/outbox', { limit }); }
	proactiveA2aShared(limit=25)                       { return this.json('/proactive/a2a/shared', { limit }); }

	// ── Phase 5 (M5.3) Generic transports ────────────────────────

	proactiveTransports()                              { return this.json('/proactive/transports'); }
	proactiveTransportsRegister(opts)                  { return this.json('/proactive/transports/register', opts); }
	proactiveTransportsDrop(alias)                     { return this.json('/proactive/transports/drop', { alias }); }
	proactiveTransportsCall(alias, prompt, dry_run = false) {
		return this.json('/proactive/transports/call', { alias, prompt, dry_run });
	}
	proactiveTransportsCalls(limit = 25)               { return this.json('/proactive/transports/calls', { limit }); }

	// ── Phase 5 (M5.9-M5.11) Config overlay + consent + state-dir ────

	proactiveStateDir()                                { return this.json('/proactive/state_dir'); }
	proactiveConfig()                                  { return this.json('/proactive/config'); }
	proactiveConfigSet(path, value)                    { return this.json('/proactive/config/set',   { path, value }); }
	proactiveConfigClear(path = null)                  { return this.json('/proactive/config/clear', path ? { path } : {}); }
	proactiveConsentList(status = null)                { return this.json('/proactive/social/consent', status ? { status } : {}); }
	proactiveConsentApprove(id, opts = {})             { return this.json(`/proactive/social/consent/${encodeURIComponent(id)}/approve`, opts); }
	proactiveConsentReject (id, opts = {})             { return this.json(`/proactive/social/consent/${encodeURIComponent(id)}/reject`,  opts); }

	// ── Phase 5 (M5.12) User-facing feed ─────────────────────────
	proactiveFeed(limit = 30, include_done = true)     { return this.json('/proactive/feed', { limit, include_done }); }
	proactiveFeedDismiss(target_id, capability = null) { return this.json('/proactive/feed/dismiss', capability ? { target_id, capability } : { target_id }); }
	proactiveMotorUndo(action_id, capability = null, reason = null) {
		const body = { action_id };
		if (capability) body.capability = capability;
		if (reason)     body.reason     = reason;
		return this.json('/proactive/motor/undo', body);
	}

	// ── Console API ──────────────────────────────────────────────

	consoleStart(opts = {})       { return this.json('/console/start', opts); }
	consoleStop()                 { return this.json('/console/stop'); }
	consoleContext()              { return this.json('/console/context'); }
	consoleWorkflow(opts = {})    { return this.json('/console/workflow', opts); }
	consoleApplyWorkflow(workflow) { return this.json('/console/workflow/apply', { workflow }); }
	consoleStatus()               { return this.json('/console/status'); }
	consoleToolkits()             { return this.json('/console/toolkits'); }
	consoleChat(message, sessionId = null, includeContext = true) {
		return this.json('/console/chat', { message, session_id: sessionId, include_context: includeContext });
	}
	consoleMemoryClear()          { return this.json('/console/memory/clear'); }
	consolePlannerEnable(opts={}) { return this.json('/console/planner/enable', opts); }
	consolePlannerDisable(opts={}) { return this.json('/console/planner/disable', opts); }
	consolePlannerStatus(opts={}) { return this.json('/console/planner/status', opts); }
	consolePlannerReset(opts={})  { return this.json('/console/planner/reset', opts); }
	consolePlannerPause(opts={})  { return this.json('/console/planner/pause', opts); }
	consolePlannerConfig(opts={}) { return this.json('/console/planner/config', opts); }
	consolePlannerApply(wf, opts = {}) { return this.json('/console/planner/apply', { workflow: wf, ...opts }); }

	// ── Toolkits ─────────────────────────────────────────────────

	toolkitList()                  { return this.json('/toolkits/list'); }
	toolkitInspect(name)           { return this.json('/toolkits/inspect', { name }); }
	toolkitUpload(formData, overwrite = false) {
		return this.upload(`/toolkits/upload?overwrite=${overwrite}`, formData);
	}
	toolkitRemove(name)            { return this.json('/toolkits/remove', { name }); }
	extensionsRegistry()           { return this.json('/extensions/registry'); }

	// ── Skills ──────────────────────────────────────────────────

	skillsList(opts = {})          { return this.json('/skills/list', opts); }
	skillsGet(name)                { return this.json('/skills/get', { name }); }
	skillsEnable(name)             { return this.json('/skills/enable', { name }); }
	skillsDisable(name)            { return this.json('/skills/disable', { name }); }
	skillsAdd(name, content)       { return this.json('/skills/add', { name, content }); }
	skillsRemove(name)             { return this.json('/skills/remove', { name }); }
	skillsCheck(name)              { return this.json('/skills/check', { name }); }
	skillsSetup(name)              { return this.json('/skills/setup', { name }); }

	// ── File Upload / Contents ───────────────────────────────────

	contentsList(nodeIndex)       { return this.json(`/contents/list/${nodeIndex}`); }
	contentsRemove(nodeIndex, ids){ return this.json(`/contents/remove/${nodeIndex}`, { ids }); }
	uploadFile(nodeIndex, formData) { return this.upload(`/upload/${nodeIndex}`, formData); }

	// ── Chat Response ────────────────────────────────────────────

	chatResponse(executionId, nodeId, response) {
		return this.json(`/chat_response/${executionId}`, { node_id: String(nodeId), response });
	}

	// ── Channel API ──────────────────────────────────────────────

	channelTypes()                             { return this.json('/channels/types'); }
	channelList()                              { return this.json('/channels/list'); }
	channelAdd(opts)                           { return this.json('/channels/add', opts); }
	channelRemove(channelId)                   { return this.json('/channels/remove', { channel_id: channelId }); }
	channelStart(channelId)                    { return this.json('/channels/start', { channel_id: channelId }); }
	channelStop(channelId)                     { return this.json('/channels/stop', { channel_id: channelId }); }
	channelSend(channelId, recipientId, text)  { return this.json('/channels/send', { channel_id: channelId, recipient_id: recipientId, text }); }
	channelStatus(channelId)                   { return this.json('/channels/status', { channel_id: channelId }); }

	// ── Assistant Deployments API ────────────────────────────────

	assistantDeploymentList()                  { return this.json('/assistant-deployments/list'); }
	assistantDeploymentGet(id)                 { return this.json('/assistant-deployments/get', { id }); }
	assistantDeploymentCreate(opts)            { return this.json('/assistant-deployments/create', opts); }
	assistantDeploymentUpdate(opts)            { return this.json('/assistant-deployments/update', opts); }
	assistantDeploymentRemove(id)              { return this.json('/assistant-deployments/remove', { id }); }
	assistantDeploymentStart(id)               { return this.json('/assistant-deployments/start', { id }); }
	assistantDeploymentStop(id)                { return this.json('/assistant-deployments/stop', { id }); }
	assistantDeploymentRefreshRuntime(id)      { return this.json('/assistant-deployments/refresh-runtime', { id }); }

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
	appsPublish(opts, requestOpts = {})        { return this.json('/apps/publish', opts, requestOpts); }
	appsUnpublish(slug)                        { return this.json('/apps/unpublish', { slug }); }

}

// ========================================================================
// EXPORTS
// ========================================================================

if (typeof window !== 'undefined') {
	window.NumelAPI = NumelAPI;
}

console.log('[Numel] API client loaded');
