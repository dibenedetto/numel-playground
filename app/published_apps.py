# published_apps — Publish Workflows as Standalone Web Apps
#
# Exposes workflows as simple web endpoints with auto-generated HTML forms.
# Anyone with the URL can run the workflow without seeing the graph editor.

import asyncio
import json
import os
import uuid

from   datetime import datetime
from   fastapi  import FastAPI, Request
from   fastapi.responses import HTMLResponse, JSONResponse
from   pydantic import BaseModel, Field
from   typing   import Any, Dict, List, Optional

from   schema   import Workflow
from   utils    import log_print


_APPS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "published_apps.json")


# =============================================================================
# DATA MODELS
# =============================================================================

class PublishedApp(BaseModel):
	"""A published workflow app."""
	id          : str            = Field(default_factory=lambda: f"app_{uuid.uuid4().hex[:8]}")
	name        : str            = ""
	slug        : str            = ""           # URL-safe name: /apps/{slug}
	description : str            = ""
	workflow    : Dict[str, Any] = Field(default_factory=dict)  # Full compact workflow JSON
	inputs      : List[dict]     = Field(default_factory=list)  # [{name, type, label, default, required}]
	published   : str            = Field(default_factory=lambda: datetime.now().isoformat())
	enabled     : bool           = True
	runs        : int            = 0
	author      : str            = ""


# =============================================================================
# APP MANAGER
# =============================================================================

class PublishedAppManager:
	"""Manages published workflow apps."""

	def __init__(self, workspace_mgr, config_path: str = _APPS_PATH):
		self._ws_mgr     = workspace_mgr
		self._config_path = config_path
		self._apps        : Dict[str, PublishedApp] = {}   # slug → app

	def initialize(self):
		"""Load saved apps."""
		self._load()
		log_print(f"Published apps initialized ({len(self._apps)} apps)")

	# ── CRUD ──────────────────────────────────────────────────────

	def publish(self, name: str, workflow: Dict[str, Any], description: str = "",
				inputs: Optional[List[dict]] = None, author: str = "",
				slug: Optional[str] = None) -> PublishedApp:
		"""Publish a workflow as a web app."""
		slug = slug or self._make_slug(name)

		# Auto-detect inputs from workflow if not provided
		if inputs is None:
			inputs = self._detect_inputs(workflow)

		app = PublishedApp(
			name        = name,
			slug        = slug,
			description = description,
			workflow    = workflow,
			inputs      = inputs,
			author      = author,
		)

		self._apps[slug] = app
		self._save()
		log_print(f"Published app: {name} → /apps/{slug}")
		return app

	def unpublish(self, slug: str) -> bool:
		"""Remove a published app."""
		if slug in self._apps:
			del self._apps[slug]
			self._save()
			return True
		return False

	def get(self, slug: str) -> Optional[PublishedApp]:
		return self._apps.get(slug)

	def list(self) -> List[dict]:
		return [
			{
				"id":          a.id,
				"name":        a.name,
				"slug":        a.slug,
				"description": a.description,
				"inputs":      a.inputs,
				"published":   a.published,
				"enabled":     a.enabled,
				"runs":        a.runs,
				"author":      a.author,
			}
			for a in self._apps.values()
		]

	# ── Execution ─────────────────────────────────────────────────

	async def start(self, slug: str, input_data: Dict[str, Any]) -> Dict[str, Any]:
		"""Start a published app execution and return execution_id immediately."""
		app = self._apps.get(slug)
		if not app or not app.enabled:
			return {"error": "App not found or disabled"}

		app.runs += 1
		self._save()

		try:
			ws_obj = self._ws_mgr.get_default_workspace()
			mgr    = ws_obj.manager
			engine = ws_obj.engine

			temp_name = f"_published_{slug}_{uuid.uuid4().hex[:6]}"
			wf_obj    = Workflow.model_validate(app.workflow)
			await mgr.add(wf_obj, temp_name)
			impl = await mgr.impl(temp_name)

			if not impl:
				await mgr.remove(temp_name)
				return {"error": "Failed to build workflow"}

			execution_id = await engine.start_workflow(
				workflow     = impl["workflow"],
				backend      = impl["backend"],
				initial_data = input_data,
			)

			# Spawn background cleanup task
			asyncio.create_task(self._cleanup_when_done(engine, mgr, execution_id, temp_name))

			return {"execution_id": execution_id}

		except Exception as e:
			return {"error": str(e)}

	async def _cleanup_when_done(self, engine, mgr, execution_id: str, temp_name: str):
		"""Background task: wait for execution to finish then remove temp workflow."""
		for _ in range(960):  # max 8 min
			results = engine.get_execution_results(execution_id)
			if results and results.get("status") in ("completed", "failed"):
				break
			await asyncio.sleep(0.5)
		try:
			await mgr.remove(temp_name)
		except Exception:
			pass

	async def run(self, slug: str, input_data: Dict[str, Any]) -> Dict[str, Any]:
		"""Run a published app synchronously (blocking until complete, no user-input support)."""
		app = self._apps.get(slug)
		if not app or not app.enabled:
			return {"error": "App not found or disabled"}

		app.runs += 1
		self._save()

		try:
			ws_obj = self._ws_mgr.get_default_workspace()
			mgr    = ws_obj.manager
			engine = ws_obj.engine

			# Load workflow temporarily — reconstruct Workflow object from stored dict
			temp_name = f"_published_{slug}_{uuid.uuid4().hex[:6]}"
			wf_obj = Workflow.model_validate(app.workflow)
			await mgr.add(wf_obj, temp_name)
			impl = await mgr.impl(temp_name)

			if not impl:
				return {"error": "Failed to build workflow"}

			# Start execution
			execution_id = await engine.start_workflow(
				workflow     = impl["workflow"],
				backend      = impl["backend"],
				initial_data = input_data,
			)

			# Wait for completion (max 120s)
			for _ in range(240):
				results = engine.get_execution_results(execution_id)
				if results and results.get("status") in ("completed", "failed"):
					break
				await asyncio.sleep(0.5)

			results = engine.get_execution_results(execution_id)

			# Cleanup
			await mgr.remove(temp_name)

			if not results:
				return {"error": "Execution timed out"}

			return {
				"status":  results.get("status", "unknown"),
				"outputs": results.get("node_outputs", {}),
				"error":   results.get("error"),
			}

		except Exception as e:
			return {"error": str(e)}

	# ── HTML Generation ───────────────────────────────────────────

	def render_form(self, slug: str, base_url: str = "") -> str:
		"""Generate an HTML form for a published app with user-input dialog support."""
		app = self._apps.get(slug)
		if not app:
			return "<h1>App not found</h1>"

		input_fields = ""
		for inp in app.inputs:
			name     = inp.get("name", "")
			label    = inp.get("label", name)
			inp_type = inp.get("type", "text")
			default  = inp.get("default", "")
			required = "required" if inp.get("required", True) else ""

			html_type = "text"
			if inp_type in ("int", "integer", "float", "number"):
				html_type = "number"
			elif inp_type == "bool":
				html_type = "checkbox"
			elif inp_type == "textarea":
				input_fields += f'''
				<div class="field">
					<label for="{name}">{label}</label>
					<textarea id="{name}" name="{name}" {required}>{default}</textarea>
				</div>'''
				continue

			input_fields += f'''
				<div class="field">
					<label for="{name}">{label}</label>
					<input type="{html_type}" id="{name}" name="{name}" value="{default}" {required}>
				</div>'''

		return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{app.name} — Numel App</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
       background: #0f0f12; color: #e0e0e0; min-height: 100vh;
       display: flex; align-items: center; justify-content: center; padding: 20px; }}
.container {{ max-width: 600px; width: 100%; }}
h1 {{ font-size: 24px; margin-bottom: 8px; color: #fff; }}
.desc {{ color: #888; margin-bottom: 24px; font-size: 14px; }}
.field {{ margin-bottom: 16px; }}
.field label {{ display: block; font-size: 13px; color: #aaa; margin-bottom: 4px; }}
input[type=text], input[type=number], textarea {{
    width: 100%; padding: 10px 12px; border: 1px solid #333;
    border-radius: 6px; background: #1a1a22; color: #fff; font-size: 14px;
    font-family: inherit; box-sizing: border-box; }}
input:focus, textarea:focus {{ border-color: #2d5a7b; outline: none; }}
textarea {{ min-height: 80px; resize: vertical; }}
.btn-row {{ display: flex; gap: 8px; margin-top: 8px; }}
.run-btn {{ flex: 1; background: #2d5a7b; color: #fff; border: none; border-radius: 6px;
    padding: 12px 24px; font-size: 14px; cursor: pointer; }}
.run-btn:hover {{ background: #3a6f96; }}
.run-btn:disabled {{ opacity: 0.5; cursor: not-allowed; }}
.cancel-btn {{ background: transparent; color: #f87171; border: 1px solid #f87171;
    border-radius: 6px; padding: 12px 20px; font-size: 14px; cursor: pointer;
    display: none; }}
.cancel-btn:hover {{ background: rgba(248,113,113,0.12); }}
.status {{ margin-top: 12px; font-size: 13px; color: #888; min-height: 18px; }}
.status.running {{ color: #6ba3d6; }}
.status.waiting {{ color: #f0a04b; font-weight: 600; }}
.status.done {{ color: #4ade80; }}
.status.error {{ color: #f87171; }}

/* Event log */
.log-wrap {{ margin-top: 14px; display: none; }}
.log-header {{ font-size: 11px; color: #555; text-transform: uppercase;
    letter-spacing: 0.08em; margin-bottom: 6px; }}
.event-log {{ background: #111116; border: 1px solid #222; border-radius: 6px;
    padding: 8px 10px; max-height: 160px; overflow-y: auto;
    font-family: monospace; font-size: 11px; display: flex; flex-direction: column; gap: 2px; }}
.event-log::-webkit-scrollbar {{ width: 4px; }}
.event-log::-webkit-scrollbar-thumb {{ background: #333; border-radius: 2px; }}
.log-entry {{ display: flex; gap: 8px; }}
.log-time {{ color: #555; flex-shrink: 0; }}
.log-type {{ flex-shrink: 0; }}
.log-type.node {{ color: #7dd3fc; }}
.log-type.workflow {{ color: #86efac; }}
.log-type.input {{ color: #fbbf24; }}
.log-type.error {{ color: #f87171; }}
.log-type.other {{ color: #a78bfa; }}
.log-desc {{ color: #888; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}

/* Result */
.result {{ margin-top: 16px; padding: 16px; background: #1a1a22;
    border: 1px solid #333; border-radius: 6px; white-space: pre-wrap;
    font-family: monospace; font-size: 13px; max-height: 400px; overflow-y: auto; display: none; }}
.result.error {{ border-color: #f87171; color: #f88; }}
.footer {{ text-align: center; margin-top: 32px; font-size: 11px; color: #555; }}
.footer a {{ color: #6ba3d6; text-decoration: none; }}

/* User-input modal */
.modal-overlay {{ display: none; position: fixed; inset: 0;
    background: rgba(0,0,0,0.75); z-index: 1000;
    align-items: center; justify-content: center; }}
.modal-overlay.open {{ display: flex; }}
.modal-box {{ background: #1a1a22; border: 1px solid #2d5a7b; border-radius: 10px;
    padding: 28px 24px; max-width: 440px; width: 90%; }}
.modal-label {{ font-size: 11px; font-weight: 600; color: #6ba3d6;
    text-transform: uppercase; letter-spacing: 0.08em; margin-bottom: 12px; }}
.modal-prompt {{ font-size: 15px; color: #e0e0e0; margin-bottom: 20px; line-height: 1.5; }}
.modal-input {{ width: 100%; padding: 10px 12px; border: 1px solid #444;
    border-radius: 6px; background: #0f0f12; color: #fff; font-size: 14px;
    font-family: inherit; outline: none; margin-bottom: 14px; box-sizing: border-box; }}
.modal-input:focus {{ border-color: #2d5a7b; }}
.modal-submit {{ background: #2d5a7b; color: #fff; border: none; border-radius: 6px;
    padding: 10px 20px; font-size: 14px; cursor: pointer; width: 100%; }}
.modal-submit:hover {{ background: #3a6f96; }}
</style>
</head>
<body>
<div class="container">
  <h1>{app.name}</h1>
  <p class="desc">{app.description or "Run this workflow"}</p>
  <form id="appForm">
    {input_fields}
    <div class="btn-row">
      <button type="submit" id="runBtn" class="run-btn">Run</button>
      <button type="button" id="cancelBtn" class="cancel-btn">Cancel</button>
    </div>
  </form>
  <div id="statusMsg" class="status"></div>
  <div class="log-wrap" id="logWrap">
    <div class="log-header">Event log</div>
    <div class="event-log" id="eventLog"></div>
  </div>
  <div id="result" class="result"></div>
  <div class="footer">Powered by <a href="/">Numel Playground</a></div>
</div>

<!-- User-input modal -->
<div id="inputModal" class="modal-overlay">
  <div class="modal-box">
    <div class="modal-label">&#9654; Workflow waiting for input</div>
    <p id="modalPrompt" class="modal-prompt"></p>
    <input type="text" id="modalInput" class="modal-input" placeholder="Enter your response\u2026">
    <button id="modalSubmit" class="modal-submit">Submit</button>
  </div>
</div>

<script>
(function () {{
  var BASE = '{base_url}';
  var SLUG = '{slug}';

  var execId       = null;
  var ws           = null;
  var pollTimer    = null;
  var pendingNodeId = null;
  var done         = false;

  var form        = document.getElementById('appForm');
  var runBtn      = document.getElementById('runBtn');
  var cancelBtn   = document.getElementById('cancelBtn');
  var statusMsg   = document.getElementById('statusMsg');
  var logWrap     = document.getElementById('logWrap');
  var eventLog    = document.getElementById('eventLog');
  var resultDiv   = document.getElementById('result');
  var modal       = document.getElementById('inputModal');
  var modalPrompt = document.getElementById('modalPrompt');
  var modalInput  = document.getElementById('modalInput');
  var modalSubmit = document.getElementById('modalSubmit');

  /* ── helpers ───────────────────────────────────────── */

  function setStatus(msg, cls) {{
    statusMsg.textContent = msg;
    statusMsg.className = 'status' + (cls ? ' ' + cls : '');
  }}

  function showResult(text, isError) {{
    resultDiv.style.display = 'block';
    resultDiv.className = 'result' + (isError ? ' error' : '');
    resultDiv.textContent = text;
  }}

  function addLog(evType, desc) {{
    logWrap.style.display = 'block';
    var now = new Date();
    var ts  = now.toTimeString().slice(0,8);

    var cls = 'other';
    if (evType.startsWith('node.'))          cls = 'node';
    else if (evType.startsWith('workflow.')) cls = 'workflow';
    else if (evType.startsWith('user_input')) cls = 'input';
    else if (evType.startsWith('error'))     cls = 'error';

    var row = document.createElement('div');
    row.className = 'log-entry';
    row.innerHTML =
      '<span class="log-time">' + ts + '</span>' +
      '<span class="log-type ' + cls + '">' + evType + '</span>' +
      '<span class="log-desc">' + (desc || '') + '</span>';
    eventLog.appendChild(row);
    eventLog.scrollTop = eventLog.scrollHeight;
  }}

  function cleanup() {{
    if (pollTimer) {{ clearInterval(pollTimer); pollTimer = null; }}
    if (ws) {{ try {{ ws.close(); }} catch(e) {{}} ws = null; }}
    runBtn.disabled    = false;
    runBtn.textContent = 'Run';
    cancelBtn.style.display = 'none';
  }}

  /* ── modal ─────────────────────────────────────────── */

  function openModal(prompt, nodeId) {{
    pendingNodeId = nodeId;
    modalPrompt.textContent = prompt || 'Please provide input:';
    modalInput.value = '';
    modal.classList.add('open');
    setStatus('\u23f3 Waiting for your input\u2026', 'waiting');
    addLog('user_input.requested', prompt || '');
    setTimeout(function() {{ modalInput.focus(); }}, 60);
  }}

  function closeModal() {{
    modal.classList.remove('open');
  }}

  async function submitInput() {{
    var value = modalInput.value;
    closeModal();
    setStatus('Resuming\u2026', 'running');
    addLog('user_input.received', value);
    try {{
      await fetch(BASE + '/exec_input/' + execId, {{
        method:  'POST',
        headers: {{'Content-Type': 'application/json'}},
        body:    JSON.stringify({{node_id: pendingNodeId, input_data: value}}),
      }});
    }} catch (e) {{
      addLog('error', 'submit input: ' + e.message);
    }}
  }}

  /* ── event handling ────────────────────────────────── */

  function handleEvent(ev) {{
    if (!ev || !ev.event_type) return;
    if (ev.execution_id && ev.execution_id !== execId) return;

    var etype = ev.event_type;
    var data  = ev.data || {{}};

    /* log everything except high-frequency noise */
    var quiet = ['edge.traversed', 'data.updated', 'stream.display',
                 'manager.workflow_added', 'manager.workflow_removed',
                 'manager.workflow_impl'];
    if (quiet.indexOf(etype) === -1) {{
      var desc = '';
      if (data.prompt) desc = data.prompt;
      else if (ev.node_id) desc = 'node ' + ev.node_id;
      else if (ev.error)   desc = ev.error;
      addLog(etype, desc);
    }}

    if (etype === 'user_input.requested') {{
      openModal(data.prompt, ev.node_id);
      return;
    }}

    if (etype === 'workflow.completed') {{
      finishWithState();
      return;
    }}

    if (etype === 'workflow.failed' || etype === 'workflow.cancelled') {{
      done = true;
      cleanup();
      setStatus('');
      showResult('Workflow ' + etype.split('.')[1] + ': ' + (ev.error || data.error || ''), true);
      return;
    }}
  }}

  /* ── poll state ────────────────────────────────────── */

  async function finishWithState() {{
    if (done) return;
    done = true;
    cleanup();
    try {{
      var resp  = await fetch(BASE + '/exec_state/' + execId, {{method: 'POST'}});
      var body  = await resp.json();
      var state = body.state || {{}};
      var st    = (state.status || '').toLowerCase();
      if (st === 'failed') {{
        setStatus('');
        showResult('Error: ' + (state.error || 'Execution failed'), true);
      }} else {{
        setStatus('\u2713 Done', 'done');
        var outputs = state.node_outputs || {{}};
        showResult(JSON.stringify(outputs, null, 2), false);
      }}
    }} catch (e) {{
      setStatus('');
      showResult('Error fetching result: ' + e.message, true);
    }}
  }}

  async function pollStatus() {{
    if (done) return;
    try {{
      var resp  = await fetch(BASE + '/exec_state/' + execId, {{method: 'POST'}});
      var body  = await resp.json();
      var state = body.state || {{}};
      var st    = (state.status || '').toLowerCase();
      if (st === 'completed' || st === 'failed') {{
        finishWithState();
      }}
    }} catch (e) {{
      /* ignore transient errors */
    }}
  }}

  /* ── websocket ─────────────────────────────────────── */

  function connectEvents() {{
    var proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
    var wsUrl = proto + '//' + location.host + '/events';
    ws = new WebSocket(wsUrl);

    ws.onopen = function() {{
      /* subscribe filtered to our execution_id */
      ws.send(JSON.stringify({{type: 'subscribe', filters: {{execution_id: execId}}}}));
    }};

    ws.onmessage = function(e) {{
      if (done) return;
      var msg;
      try {{ msg = JSON.parse(e.data); }} catch (ex) {{ return; }}

      if (msg.type === 'workflow_event') {{
        handleEvent(msg.event);

      }} else if (msg.type === 'event_history') {{
        /* scan past events — may contain user_input.requested already fired */
        var events = msg.events || [];
        for (var i = 0; i < events.length; i++) {{
          var ev = events[i];
          if (ev.execution_id === execId && ev.event_type === 'user_input.requested') {{
            openModal((ev.data || {{}}).prompt, ev.node_id);
            break;
          }}
        }}
      }}
    }};

    ws.onerror = function() {{}};
    ws.onclose = function() {{}};
  }}

  /* ── cancel ────────────────────────────────────────── */

  cancelBtn.addEventListener('click', async function() {{
    if (!execId || done) return;
    done = true;
    cleanup();
    closeModal();
    addLog('workflow.cancelled', 'user cancelled');
    setStatus('Cancelled', 'error');
    try {{
      await fetch(BASE + '/exec_cancel/' + execId, {{method: 'POST'}});
    }} catch (e) {{}}
  }});

  /* ── form submit ───────────────────────────────────── */

  form.addEventListener('submit', async function(e) {{
    e.preventDefault();
    if (runBtn.disabled) return;

    done = false;
    runBtn.disabled    = true;
    runBtn.textContent = 'Starting\u2026';
    resultDiv.style.display = 'none';
    resultDiv.className = 'result';
    logWrap.style.display = 'none';
    eventLog.innerHTML = '';
    setStatus('Starting\u2026', 'running');

    var formData = new FormData(form);
    var data = {{}};
    formData.forEach(function(v, k) {{ data[k] = v; }});

    try {{
      var resp = await fetch(BASE + '/apps/' + SLUG + '/start', {{
        method:  'POST',
        headers: {{'Content-Type': 'application/json'}},
        body:    JSON.stringify(data),
      }});
      var body = await resp.json();
      if (body.error) throw new Error(body.error);

      execId = body.execution_id;
      runBtn.textContent = 'Running\u2026';
      cancelBtn.style.display = 'block';
      setStatus('Running\u2026', 'running');
      addLog('workflow.started', execId);

      connectEvents();
      pollTimer = setInterval(pollStatus, 1500);

    }} catch (err) {{
      cleanup();
      setStatus('');
      showResult('Error: ' + err.message, true);
    }}
  }});

  modalSubmit.addEventListener('click', submitInput);
  modalInput.addEventListener('keydown', function(e) {{
    if (e.key === 'Enter') submitInput();
  }});

}})();
</script>
</body>
</html>'''

	# ── Helpers ───────────────────────────────────────────────────

	def _make_slug(self, name: str) -> str:
		"""Convert a name to a URL-safe slug."""
		slug = name.lower().strip()
		slug = "".join(c if c.isalnum() or c == "-" else "-" for c in slug)
		slug = "-".join(part for part in slug.split("-") if part)
		# Ensure uniqueness
		base = slug
		counter = 1
		while slug in self._apps:
			slug = f"{base}-{counter}"
			counter += 1
		return slug

	def _detect_inputs(self, workflow: Dict[str, Any]) -> List[dict]:
		"""Auto-detect workflow inputs from start_flow node fields."""
		inputs = []
		nodes = workflow.get("nodes", [])
		for node in nodes:
			if not node:
				continue
			ntype = node.get("type", "")
			if ntype == "start_flow":
				# Start flow may have initial_data or prompt fields
				for key, value in node.items():
					if key in ("type", "extra", "flow_in", "flow_out", "name"):
						continue
					inp_type = "text"
					if isinstance(value, bool):
						inp_type = "bool"
					elif isinstance(value, (int, float)):
						inp_type = "number"
					inputs.append({
						"name":     key,
						"label":    key.replace("_", " ").title(),
						"type":     inp_type,
						"default":  value if value is not None else "",
						"required": True,
					})
		return inputs

	def _save(self):
		data = {slug: app.model_dump() for slug, app in self._apps.items()}
		with open(self._config_path, "w") as f:
			json.dump(data, f, indent=2)

	def _load(self):
		if not os.path.exists(self._config_path):
			return
		try:
			with open(self._config_path) as f:
				raw = json.load(f)
			for slug, data in raw.items():
				self._apps[slug] = PublishedApp(**data)
		except Exception as e:
			log_print(f"Failed to load published apps: {e}")


# =============================================================================
# API ROUTES
# =============================================================================

class PublishRequest(BaseModel):
	# Accept either direct workflow dict OR a workflow_name to look up
	workflow_name : Optional[str]      = None
	workflow      : Optional[Dict[str, Any]] = None
	# slug can be provided; if omitted it's derived from title/name
	slug          : Optional[str]      = None
	title         : Optional[str]      = None   # display name (alias for name)
	name          : Optional[str]      = None   # kept for backwards compat
	description   : str                = ""
	inputs        : Optional[List[dict]] = None
	author        : str                = ""


def setup_published_apps_api(app: FastAPI, app_mgr: PublishedAppManager):
	"""Register published app routes."""

	# Management API
	@app.post("/apps/list")
	async def apps_list():
		return app_mgr.list()

	@app.post("/apps/publish")
	async def apps_publish(request: PublishRequest):
		# Resolve display name: title > name > workflow_name > "Untitled"
		display_name = request.title or request.name or request.workflow_name or "Untitled"

		# Resolve workflow dict
		workflow = request.workflow
		if workflow is None:
			if request.workflow_name:
				ws = app_mgr._ws_mgr.get_default_workspace()
				wf = await ws.manager.get(request.workflow_name)
				if wf is None:
					return JSONResponse(status_code=404, content={"error": f"Workflow '{request.workflow_name}' not found"})
				# Serialise to JSON-safe dict (round-trip through JSON to strip non-serializable objects)
				try:
					workflow = json.loads(wf.model_dump_json())
				except Exception:
					workflow = json.loads(json.dumps(wf.model_dump(), default=str))
			else:
				return JSONResponse(status_code=400, content={"error": "Provide either 'workflow' or 'workflow_name'"})

		result = app_mgr.publish(
			name        = display_name,
			workflow    = workflow,
			description = request.description,
			inputs      = request.inputs,
			author      = request.author,
			slug        = request.slug,
		)
		return {"slug": result.slug, "url": f"/apps/{result.slug}"}

	@app.post("/apps/unpublish")
	async def apps_unpublish(request: dict):
		return {"removed": app_mgr.unpublish(request.get("slug", ""))}

	# Public endpoints — these are what end users access
	@app.get("/apps/{slug}")
	async def apps_page(slug: str, request: Request):
		"""Serve the auto-generated HTML form for a published app."""
		published_app = app_mgr.get(slug)
		if not published_app or not published_app.enabled:
			return HTMLResponse("<h1>App not found</h1>", status_code=404)
		base_url = str(request.base_url).rstrip("/")
		html = app_mgr.render_form(slug, base_url)
		return HTMLResponse(html)

	@app.post("/apps/{slug}/start")
	async def apps_start(slug: str, request: Request):
		"""Start a published app execution; returns execution_id immediately."""
		try:
			body = await request.json()
		except Exception:
			body = {}
		result = await app_mgr.start(slug, body)
		return JSONResponse(result)

	@app.post("/apps/{slug}/run")
	async def apps_run(slug: str, request: Request):
		"""Execute a published app synchronously (blocks until complete)."""
		try:
			body = await request.json()
		except Exception:
			body = {}
		result = await app_mgr.run(slug, body)
		return JSONResponse(result)
