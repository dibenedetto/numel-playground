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
	run_count   : int            = 0
	error_count : int            = 0
	last_run_at : Optional[str]  = None
	last_error  : Optional[str]  = None


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
				"run_count":   a.run_count,
				"error_count": a.error_count,
				"last_run_at": a.last_run_at,
				"last_error":  a.last_error,
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
			asyncio.create_task(self._cleanup_when_done(engine, mgr, execution_id, temp_name, slug))

			return {"execution_id": execution_id}

		except Exception as e:
			return {"error": str(e)}

	async def _cleanup_when_done(self, engine, mgr, execution_id: str, temp_name: str, slug: str):
		"""Background task: wait for execution to finish then remove temp workflow."""
		results = None
		for _ in range(960):  # max 8 min
			results = engine.get_execution_results(execution_id)
			if results and results.get("status") in ("completed", "failed"):
				break
			await asyncio.sleep(0.5)
		try:
			await mgr.remove(temp_name)
		except Exception:
			pass
		# Update analytics
		app = self._apps.get(slug)
		if app:
			app.run_count  += 1
			app.last_run_at = datetime.now().isoformat()
			if results and results.get("status") == "failed":
				app.error_count += 1
				app.last_error   = results.get("error") or "unknown error"
			self._save()

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

	@staticmethod
	def _scan_media_nodes(workflow: Dict[str, Any]) -> dict:
		"""Pre-scan workflow for preview_flow, browser_source_flow, and computer_vision_flow nodes."""
		nodes = workflow.get("nodes", [])
		edges = workflow.get("edges", [])
		previews   = []   # [{index, name, hint}]
		sources    = []   # [{index, name, device_type, mode, interval_ms, resolution, audio_format}]
		cv_nodes   = []   # [{index, name, task, model_size, min_confidence, inference_location, source_index, preview_index}]
		for i, node in enumerate(nodes):
			ntype = node.get("type", "")
			name  = (node.get("extra") or {}).get("name", f"Node {i}")
			if ntype == "preview_flow":
				previews.append({"index": i, "name": name,
								 "hint": node.get("hint", "auto")})
			elif ntype == "browser_source_flow":
				sources.append({"index": i, "name": name,
								"device_type": node.get("device_type", "webcam"),
								"mode": node.get("mode", "event"),
								"interval_ms": node.get("interval_ms", 1000),
								"resolution": node.get("resolution", ""),
								"audio_format": node.get("audio_format", "")})
			elif ntype == "computer_vision_flow":
				cv_nodes.append({"index": i, "name": name,
								 "task": node.get("task", "pose"),
								 "model_size": node.get("model_size", "lite"),
								 "min_confidence": node.get("min_confidence", 0.5),
								 "inference_location": node.get("inference_location", "frontend"),
								 "source_index": -1, "preview_index": -1})

		# Resolve CV node connections via edges
		for cv in cv_nodes:
			ci = cv["index"]
			for edge in edges:
				# source_id edge: browser_source → cv node
				if edge.get("target") == ci and edge.get("target_slot") == "source_id":
					cv["source_index"] = edge["source"]
				# rendered_image → preview's flow_in
				if edge.get("source") == ci and edge.get("source_slot") == "rendered_image":
					cv["preview_index"] = edge["target"]

		return {"previews": previews, "sources": sources, "cv_nodes": cv_nodes}

	def render_form(self, slug: str, base_url: str = "", embed: bool = False) -> str:
		"""Generate an HTML form for a published app with user-input dialog support."""
		app = self._apps.get(slug)
		if not app:
			return "<h1>App not found</h1>"

		# Pre-scan for media nodes
		media_info = self._scan_media_nodes(app.workflow)
		has_media  = bool(media_info["previews"] or media_info["sources"] or media_info["cv_nodes"])

		# Build conditional media sections
		media_css  = self._render_media_css()            if has_media else ""
		media_html = self._render_media_html(media_info) if has_media else ""
		media_js   = self._render_media_js(media_info)   if has_media else ""
		# Conditional CDN scripts
		has_frontend_cv = any(cv["inference_location"] == "frontend" for cv in media_info.get("cv_nodes", []))
		has_3d = any(p["hint"] == "model3d" for p in media_info.get("previews", []))
		media_head_parts = []
		if has_frontend_cv:
			media_head_parts.append(
				'<script>\n'
				'import("https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.32/+esm")\n'
				'.then(function(v){window._mpVision=v;console.log("[CV] MediaPipe loaded");})\n'
				'.catch(function(e){console.error("[CV] MediaPipe load failed:",e);});\n'
				'</script>')
		if has_3d:
			media_head_parts.append(
				'<script async src="https://cdn.jsdelivr.net/npm/es-module-shims@1.10.0/dist/es-module-shims.min.js"></script>\n'
				'<script type="importmap">{"imports":{'
				'"three":"https://cdn.jsdelivr.net/npm/three@0.170.0/build/three.module.min.js",'
				'"three/addons/":"https://cdn.jsdelivr.net/npm/three@0.170.0/examples/jsm/"}}</script>\n'
				'<script type="module">\n'
				'import * as THREE from "three";\n'
				'import {OrbitControls} from "three/addons/controls/OrbitControls.js";\n'
				'import {GLTFLoader} from "three/addons/loaders/GLTFLoader.js";\n'
				'import {OBJLoader} from "three/addons/loaders/OBJLoader.js";\n'
				'import {STLLoader} from "three/addons/loaders/STLLoader.js";\n'
				'window._three={THREE,OrbitControls,GLTFLoader,OBJLoader,STLLoader};\n'
				'console.log("[3D] Three.js loaded");\n'
				'</script>')
		media_head = "\n".join(media_head_parts)

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

		embed_css = '''
body { padding: 8px !important; background: transparent !important; }
h1, .desc, .footer { display: none !important; }
''' if embed else ''

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
{embed_css}
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
{media_css}</style>
{media_head}
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
  {media_html}
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

{media_js}
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
    if (typeof cleanupMedia === 'function') cleanupMedia();
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

    if (typeof handleMediaEvent === 'function') handleMediaEvent(ev, etype, data);

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
        /* replay past events — catches node.completed, user_input, etc. fired before WS connected */
        var events = msg.events || [];
        for (var i = 0; i < events.length; i++) {{
          var ev = events[i];
          if (ev.execution_id === execId) {{
            handleEvent(ev);
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
      if (typeof initMediaPanels === 'function') initMediaPanels();
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

	@staticmethod
	def _render_media_css() -> str:
		"""CSS for preview panels and browser source elements in published apps."""
		return """/* Media: previews & browser sources */
.media-section { margin-top: 16px; display: flex; flex-direction: column; gap: 12px; }
.preview-panel { background: #1a1a22; border: 1px solid #333; border-radius: 6px;
    overflow: hidden; display: none; }
.preview-header { padding: 8px 12px; font-size: 11px; color: #888; text-transform: uppercase;
    letter-spacing: 0.06em; border-bottom: 1px solid #222; background: #15151c; }
.preview-content { padding: 12px; max-height: 500px; overflow: auto; }
.preview-content pre { margin: 0; white-space: pre-wrap; word-break: break-word;
    font-size: 13px; color: #e0e0e0; font-family: monospace; }
.preview-content img, .preview-content video { max-width: 100%; border-radius: 4px; display: block; }
.preview-content audio { width: 100%; }
.source-panel { background: #1a1a22; border: 1px solid #333; border-radius: 6px;
    overflow: hidden; }
.source-header { padding: 8px 12px; font-size: 11px; color: #888; text-transform: uppercase;
    letter-spacing: 0.06em; border-bottom: 1px solid #222; background: #15151c;
    display: flex; justify-content: space-between; align-items: center; }
.source-header button { background: #2d5a7b; color: #fff; border: none; border-radius: 4px;
    padding: 4px 10px; font-size: 11px; cursor: pointer; }
.source-body { position: relative; background: #000; min-height: 120px; }
.source-body video { width: 100%; display: block; }
.source-body canvas { position: absolute; top: 0; left: 0; width: 100%; height: 100%;
    pointer-events: none; }
.source-body-audio { min-height: 60px; display: flex; align-items: center; justify-content: center; }
.audio-level-canvas { width: 100%; height: 60px; display: block; }
"""

	@staticmethod
	def _render_media_html(media_info: dict) -> str:
		"""HTML panels for preview outputs and browser source capture areas."""
		panels = ""
		for p in media_info["previews"]:
			panels += (
				f'  <div class="preview-panel" id="preview-{p["index"]}" data-hint="{p["hint"]}">'
				f'<div class="preview-header">{p["name"]}</div>'
				f'<div class="preview-content" id="preview-content-{p["index"]}"></div>'
				f'</div>\n')
		for s in media_info["sources"]:
			if s["device_type"] == "microphone":
				# Audio-only: level meter canvas instead of video
				panels += (
					f'  <div class="source-panel" id="source-{s["index"]}" data-device="microphone">'
					f'<div class="source-header">'
					f'<span>{s["name"]} (microphone)</span>'
					f'<button onclick="window._toggleSource({s["index"]})">Start</button>'
					f'</div>'
					f'<div class="source-body source-body-audio">'
					f'<canvas id="source-level-{s["index"]}" class="audio-level-canvas"></canvas>'
					f'</div>'
					f'</div>\n')
			else:
				panels += (
					f'  <div class="source-panel" id="source-{s["index"]}" data-device="{s["device_type"]}">'
					f'<div class="source-header">'
					f'<span>{s["name"]} ({s["device_type"]})</span>'
					f'<button onclick="window._toggleSource({s["index"]})">Start</button>'
					f'</div>'
					f'<div class="source-body">'
					f'<video id="source-video-{s["index"]}" autoplay muted playsinline></video>'
					f'<canvas id="source-canvas-{s["index"]}"></canvas>'
					f'</div>'
					f'</div>\n')
		return '<div class="media-section" id="mediaSection">\n' + panels + '</div>'

	@staticmethod
	def _render_media_js(media_info: dict) -> str:
		"""JavaScript for preview rendering, browser source capture, and stream display."""
		info_json = json.dumps(media_info)
		return "  var MEDIA_INFO = " + info_json + ";\n" + """  var activeStreams = {};

  function handleMediaEvent(ev, etype, data) {
    if (etype === 'node.completed') {
      var nodeIdx = parseInt(ev.node_id, 10);
      for (var pi = 0; pi < MEDIA_INFO.previews.length; pi++) {
        if (MEDIA_INFO.previews[pi].index === nodeIdx) {
          renderPreview(nodeIdx, data.outputs || {}, MEDIA_INFO.previews[pi].hint);
          break;
        }
      }
      for (var si = 0; si < MEDIA_INFO.sources.length; si++) {
        if (MEDIA_INFO.sources[si].index === nodeIdx) {
          var regId = (data.outputs || {}).registered_id;
          if (regId) {
            activeStreams[nodeIdx] = activeStreams[nodeIdx] || {};
            activeStreams[nodeIdx].sourceId = regId;
            var sp = document.getElementById('source-' + nodeIdx);
            if (sp) sp.style.display = 'block';
            if (activeStreams[nodeIdx].stream) {
              connectStreamWs(nodeIdx, regId, MEDIA_INFO.sources[si]);
            }
          }
          break;
        }
      }
    }
    if (etype === 'stream.display') {
      var sid = data.source_id;
      for (var key in activeStreams) {
        if (activeStreams[key].sourceId === sid) {
          if (!activeStreams[key].ws || activeStreams[key].ws.readyState !== 1) {
            renderStreamDisplay(parseInt(key), {render_type: data.render_type, payload: data.payload});
          }
          break;
        }
      }
    }
  }

  function initMediaPanels() {
    for (var i = 0; i < MEDIA_INFO.sources.length; i++) {
      var s = MEDIA_INFO.sources[i];
      var panel = document.getElementById('source-' + s.index);
      if (panel) panel.style.display = 'block';
    }
  }

  function cleanupMedia() {
    if (typeof _stopCVDetectors === 'function') _stopCVDetectors();
    for (var key in activeStreams) { stopSource(parseInt(key)); }
  }

  function renderPreview(nodeIdx, outputs, hint) {
    var panel = document.getElementById('preview-' + nodeIdx);
    var content = document.getElementById('preview-content-' + nodeIdx);
    if (!panel || !content) return;
    panel.style.display = 'block';
    var val = outputs.flow_out !== undefined ? outputs.flow_out
            : (outputs.output !== undefined ? outputs.output : outputs);
    if (val === undefined || val === null) {
      /* Skip "(no data)" if a frontend CV node will drive this preview live */
      var cvNodes = MEDIA_INFO.cv_nodes || [];
      for (var ci = 0; ci < cvNodes.length; ci++) {
        if (cvNodes[ci].preview_index === nodeIdx && cvNodes[ci].inference_location === 'frontend') return;
      }
      content.innerHTML = '<pre style="color:#666">(no data)</pre>';
      return;
    }
    /* Auto-detect content type */
    if (hint === 'auto') {
      if (typeof val === 'string') {
        if (val.match(/^data:image\\//) || val.match(/\\.(png|jpg|jpeg|gif|webp|svg)(\\?|$)/i)) hint = 'image';
        else if (val.match(/^data:audio\\//) || val.match(/\\.(mp3|wav|ogg|m4a|flac)(\\?|$)/i)) hint = 'audio';
        else if (val.match(/^data:video\\//) || val.match(/\\.(mp4|webm|mov|avi)(\\?|$)/i)) hint = 'video';
        else if (val.match(/\\.(glb|gltf|obj|stl|fbx|ply)(\\?|$)/i)) hint = 'model3d';
        else if (val.trim().charAt(0) === '{' || val.trim().charAt(0) === '[') {
          try { JSON.parse(val); hint = 'json'; } catch(_) { hint = 'text'; }
        } else hint = 'text';
      } else if (typeof val === 'object') {
        if (val.url || val.src || val.data) {
          var probe = val.url || val.src || val.data || '';
          if (probe.match(/^data:image\\//) || probe.match(/\\.(png|jpg|jpeg|gif|webp|svg)(\\?|$)/i)) hint = 'image';
          else if (probe.match(/^data:audio\\//) || probe.match(/\\.(mp3|wav|ogg)(\\?|$)/i)) hint = 'audio';
          else if (probe.match(/^data:video\\//) || probe.match(/\\.(mp4|webm|mov)(\\?|$)/i)) hint = 'video';
          else hint = 'json';
        } else hint = 'json';
      } else hint = 'text';
    }
    var src;
    if (hint === 'image') {
      src = typeof val === 'string' ? val : (val.url || val.src || val.data || '');
      content.innerHTML = '<img src="' + _mEscAttr(src) + '" alt="preview">';
    } else if (hint === 'audio') {
      src = typeof val === 'string' ? val : (val.url || val.src || val.data || '');
      content.innerHTML = '<audio controls src="' + _mEscAttr(src) + '"></audio>';
    } else if (hint === 'video') {
      src = typeof val === 'string' ? val : (val.url || val.src || val.data || '');
      content.innerHTML = '<video controls src="' + _mEscAttr(src) + '" style="max-width:100%"></video>';
    } else if (hint === 'model3d') {
      src = typeof val === 'string' ? val : (val.url || val.src || val.data || '');
      var fname = src.split('/').pop().split('?')[0] || '3D Model';
      if (window._three && src) {
        _render3DModel(content, src, fname);
      } else {
        content.innerHTML = '<div style="text-align:center;padding:16px">'
          + '<div style="font-size:32px;margin-bottom:8px">&#x1f4e6;</div>'
          + '<a href="' + _mEscAttr(src) + '" download style="color:#6ba3d6">' + _mEscHtml(fname) + '</a>'
          + '<div style="font-size:11px;color:#666;margin-top:4px">3D model — download to view</div></div>';
      }
    } else if (hint === 'json') {
      var txt = typeof val === 'string' ? val : JSON.stringify(val, null, 2);
      content.innerHTML = '<pre>' + _mEscHtml(txt) + '</pre>';
    } else {
      /* text fallback */
      content.innerHTML = '<pre>' + _mEscHtml(String(val)) + '</pre>';
    }
  }

  function _mEscHtml(s) { var d = document.createElement('div'); d.textContent = s; return d.innerHTML; }
  function _mEscAttr(s) { return s.replace(/&/g,'&amp;').replace(/"/g,'&quot;').replace(/</g,'&lt;'); }

  /* ── 3D model viewer (Three.js) ────────────────────── */

  function _render3DModel(container, src, fname) {
    var T = window._three;
    if (!T) return;
    var THREE = T.THREE;

    container.innerHTML = '';
    var wrap = document.createElement('div');
    wrap.style.cssText = 'position:relative;width:100%;height:300px;background:#111;border-radius:4px;overflow:hidden';
    container.appendChild(wrap);

    var scene    = new THREE.Scene();
    scene.background = new THREE.Color(0x111116);
    var camera   = new THREE.PerspectiveCamera(50, wrap.clientWidth / wrap.clientHeight, 0.01, 1000);
    camera.position.set(0, 1, 3);
    var renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setSize(wrap.clientWidth, wrap.clientHeight);
    renderer.setPixelRatio(window.devicePixelRatio);
    wrap.appendChild(renderer.domElement);

    var controls = new T.OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;

    /* Lights */
    scene.add(new THREE.AmbientLight(0xffffff, 0.6));
    var dirLight = new THREE.DirectionalLight(0xffffff, 0.8);
    dirLight.position.set(5, 10, 7);
    scene.add(dirLight);

    /* Grid */
    scene.add(new THREE.GridHelper(10, 10, 0x333333, 0x222222));

    /* Status */
    var status = document.createElement('div');
    status.style.cssText = 'position:absolute;top:8px;left:8px;font-size:11px;color:#666';
    status.textContent = 'Loading ' + fname + '...';
    wrap.appendChild(status);

    /* Download link */
    var dl = document.createElement('a');
    dl.href = src; dl.download = fname;
    dl.style.cssText = 'position:absolute;bottom:8px;right:8px;font-size:11px;color:#6ba3d6;text-decoration:none';
    dl.textContent = 'Download';
    wrap.appendChild(dl);

    /* Fit model to view */
    function fitCamera(obj) {
      var box = new THREE.Box3().setFromObject(obj);
      var size = box.getSize(new THREE.Vector3());
      var center = box.getCenter(new THREE.Vector3());
      var maxDim = Math.max(size.x, size.y, size.z);
      if (maxDim === 0) maxDim = 1;
      var scale = 2 / maxDim;
      obj.scale.multiplyScalar(scale);
      box.setFromObject(obj);
      box.getCenter(center);
      obj.position.sub(center);
      camera.position.set(0, 1, 3);
      controls.target.set(0, 0, 0);
      controls.update();
    }

    function onLoad(obj) {
      scene.add(obj);
      fitCamera(obj);
      status.textContent = fname;
    }

    function onError(err) {
      status.textContent = 'Load error';
      console.error('[3D]', err);
    }

    /* Pick loader by extension */
    var ext = fname.split('.').pop().toLowerCase();
    var loader;
    if ((ext === 'glb' || ext === 'gltf') && T.GLTFLoader) {
      loader = new T.GLTFLoader();
      loader.load(src, function(gltf) { onLoad(gltf.scene); }, undefined, onError);
    } else if (ext === 'obj' && T.OBJLoader) {
      loader = new T.OBJLoader();
      loader.load(src, onLoad, undefined, onError);
    } else if (ext === 'stl' && T.STLLoader) {
      loader = new T.STLLoader();
      loader.load(src, function(geom) {
        var mat = new THREE.MeshStandardMaterial({ color: 0x8888cc, flatShading: true });
        onLoad(new THREE.Mesh(geom, mat));
      }, undefined, onError);
    } else {
      /* Fallback: try GLTF */
      if (T.GLTFLoader) {
        loader = new T.GLTFLoader();
        loader.load(src, function(gltf) { onLoad(gltf.scene); }, undefined, onError);
      } else { status.textContent = 'Unsupported format'; }
    }

    /* Render loop */
    var animId;
    function animate() { animId = requestAnimationFrame(animate); controls.update(); renderer.render(scene, camera); }
    animate();

    /* Resize observer */
    var ro = new ResizeObserver(function() {
      var w = wrap.clientWidth, h = wrap.clientHeight;
      camera.aspect = w / h; camera.updateProjectionMatrix();
      renderer.setSize(w, h);
    });
    ro.observe(wrap);

    /* Store cleanup ref */
    container._3dCleanup = function() {
      cancelAnimationFrame(animId); ro.disconnect();
      renderer.dispose(); controls.dispose();
    };
  }

  window._toggleSource = async function(nodeIdx) {
    var info = activeStreams[nodeIdx];
    if (info && info.stream) { stopSource(nodeIdx); return; }
    var cfg = null;
    for (var i = 0; i < MEDIA_INFO.sources.length; i++) {
      if (MEDIA_INFO.sources[i].index === nodeIdx) { cfg = MEDIA_INFO.sources[i]; break; }
    }
    if (!cfg) return;
    activeStreams[nodeIdx] = activeStreams[nodeIdx] || {};
    activeStreams[nodeIdx].cfg = cfg;
    await startCapture(nodeIdx, cfg);
    if (activeStreams[nodeIdx].sourceId) connectStreamWs(nodeIdx, activeStreams[nodeIdx].sourceId, cfg);
  };

  async function startCapture(nodeIdx, cfg) {
    var stream;
    try {
      if (cfg.device_type === 'screen') stream = await navigator.mediaDevices.getDisplayMedia({video: true, audio: true});
      else if (cfg.device_type === 'microphone') stream = await navigator.mediaDevices.getUserMedia({audio: true});
      else {
        var vc = true;
        if (cfg.resolution) { var p = cfg.resolution.split('x'); if (p.length === 2) vc = {width: {ideal: +p[0]}, height: {ideal: +p[1]}}; }
        stream = await navigator.mediaDevices.getUserMedia({video: vc});
      }
    } catch(e) { console.error('Capture failed:', e); return; }
    activeStreams[nodeIdx].stream = stream;
    if (cfg.device_type === 'microphone') {
      _startAudioLevel(nodeIdx, stream);
    } else {
      var video = document.getElementById('source-video-' + nodeIdx);
      if (video) {
        video.srcObject = stream;
        if (cfg.device_type === 'webcam') video.parentElement.style.transform = 'scaleX(-1)';
        video.play();
      }
    }
    _updateSourceBtn(nodeIdx, true);
    /* Kick off frontend CV inference if any CV node targets this source */
    setTimeout(function() { if (typeof _tryStartFrontendCV === 'function') _tryStartFrontendCV(); }, 200);
    /* Auto-stop when the browser ends the stream (e.g. user clicks "Stop sharing") */
    stream.getTracks().forEach(function(track) {
      track.addEventListener('ended', function() { stopSource(nodeIdx); });
    });
  }

  function _startAudioLevel(nodeIdx, stream) {
    var canvas = document.getElementById('source-level-' + nodeIdx);
    if (!canvas) return;
    var actx = new (window.AudioContext || window.webkitAudioContext)();
    var src = actx.createMediaStreamSource(stream);
    var analyser = actx.createAnalyser();
    analyser.fftSize = 256;
    src.connect(analyser);
    var buf = new Uint8Array(analyser.frequencyBinCount);
    var info = activeStreams[nodeIdx];
    info.audioCtx = actx;
    function draw() {
      if (!activeStreams[nodeIdx] || !activeStreams[nodeIdx].audioCtx) return;
      info.levelRaf = requestAnimationFrame(draw);
      analyser.getByteFrequencyData(buf);
      var w = canvas.clientWidth, h = canvas.clientHeight;
      if (canvas.width !== w || canvas.height !== h) { canvas.width = w; canvas.height = h; }
      var ctx = canvas.getContext('2d');
      ctx.fillStyle = '#000'; ctx.fillRect(0, 0, w, h);
      var bars = buf.length, bw = w / bars;
      for (var i = 0; i < bars; i++) {
        var bh = (buf[i] / 255) * h;
        ctx.fillStyle = 'hsl(' + (120 - (buf[i] / 255) * 80) + ',80%,50%)';
        ctx.fillRect(i * bw, h - bh, bw - 1, bh);
      }
    }
    draw();
  }

  function connectStreamWs(nodeIdx, sourceId, cfg) {
    var info = activeStreams[nodeIdx];
    if (!info || info.ws) return;
    var proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
    var sws = new WebSocket(proto + '//' + location.host + '/ws/stream/' + sourceId);
    info.ws = sws;
    sws.binaryType = 'arraybuffer';
    sws.onopen = function() {
      if (cfg.device_type === 'microphone') {
        if (info.stream) {
          var mimeType = 'audio/webm;codecs=opus';
          if (!MediaRecorder.isTypeSupported(mimeType)) mimeType = 'audio/webm';
          var recorder = new MediaRecorder(info.stream, {mimeType: mimeType});
          info.recorder = recorder;
          recorder.ondataavailable = function(e) {
            if (e.data && e.data.size > 0 && sws.readyState === 1) sws.send(e.data);
          };
          recorder.start(cfg.interval_ms || 1000);
        }
      } else {
        var video = document.getElementById('source-video-' + nodeIdx);
        var cvs = document.createElement('canvas');
        var cctx = cvs.getContext('2d');
        info.sendInterval = setInterval(function() {
          if (!video || !video.videoWidth || sws.readyState !== 1) return;
          cvs.width = video.videoWidth; cvs.height = video.videoHeight;
          cctx.drawImage(video, 0, 0);
          cvs.toBlob(function(b) { if (b && sws.readyState === 1) sws.send(b); }, 'image/jpeg', 0.8);
        }, cfg.interval_ms || 1000);
      }
    };
    sws.onmessage = function(e) {
      if (typeof e.data === 'string') {
        try { var msg = JSON.parse(e.data); if (msg.type === 'stream.display') renderStreamDisplay(nodeIdx, msg); } catch(ex) {}
      } else if (e.data instanceof ArrayBuffer) {
        var arr = new Uint8Array(e.data);
        if (arr[0] === 0x01) {
          var blob = new Blob([arr.slice(1)], {type: 'image/jpeg'});
          var url = URL.createObjectURL(blob);
          var ov = document.getElementById('source-canvas-' + nodeIdx);
          if (ov) {
            var img = new Image();
            img.onload = function() { ov.width = img.width; ov.height = img.height; ov.getContext('2d').drawImage(img, 0, 0); URL.revokeObjectURL(url); };
            img.src = url;
          }
        }
      }
    };
    sws.onclose = function() { if (info) info.ws = null; };
  }

  function renderStreamDisplay(nodeIdx, msg) {
    var canvas = document.getElementById('source-canvas-' + nodeIdx);
    if (!canvas) return;
    var video = document.getElementById('source-video-' + nodeIdx);
    if (video && video.videoWidth) { canvas.width = video.videoWidth; canvas.height = video.videoHeight; }
    var ctx = canvas.getContext('2d');
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    var rt = msg.render_type, payload = msg.payload;
    if (rt === 'text' && payload) {
      ctx.fillStyle = 'rgba(0,255,0,0.9)'; ctx.font = '16px monospace';
      ctx.fillText(typeof payload === 'string' ? payload : JSON.stringify(payload), 10, 30);
    } else if (rt === 'pose' && Array.isArray(payload)) {
      _drawPose(ctx, payload, canvas.width, canvas.height);
    } else if (rt === 'image' && typeof payload === 'string') {
      var im = new Image();
      im.onload = function() { ctx.drawImage(im, 0, 0, canvas.width, canvas.height); };
      im.src = payload.startsWith('data:') ? payload : 'data:image/jpeg;base64,' + payload;
    }
  }

  function _drawPose(ctx, lm, w, h) {
    ctx.fillStyle = '#00ff00';
    for (var i = 0; i < lm.length; i++) {
      ctx.beginPath(); ctx.arc((lm[i].x||0)*w, (lm[i].y||0)*h, 3, 0, Math.PI*2); ctx.fill();
    }
    ctx.strokeStyle = '#00ff00'; ctx.lineWidth = 2;
    var cn = [[11,12],[11,13],[13,15],[12,14],[14,16],[11,23],[12,24],[23,24],[23,25],[24,26],[25,27],[26,28]];
    for (var c = 0; c < cn.length; c++) {
      var a = lm[cn[c][0]], b = lm[cn[c][1]];
      if (a && b) { ctx.beginPath(); ctx.moveTo(a.x*w,a.y*h); ctx.lineTo(b.x*w,b.y*h); ctx.stroke(); }
    }
  }

  function stopSource(nodeIdx) {
    var info = activeStreams[nodeIdx]; if (!info) return;
    if (info.sendInterval) clearInterval(info.sendInterval);
    if (info.recorder) try { info.recorder.stop(); } catch(e) {}
    if (info.levelRaf) cancelAnimationFrame(info.levelRaf);
    if (info.audioCtx) try { info.audioCtx.close(); } catch(e) {}
    if (info.ws) try { info.ws.close(); } catch(e) {}
    if (info.stream) info.stream.getTracks().forEach(function(t) { t.stop(); });
    var video = document.getElementById('source-video-' + nodeIdx);
    if (video) video.srcObject = null;
    var lvl = document.getElementById('source-level-' + nodeIdx);
    if (lvl) { var lctx = lvl.getContext('2d'); lctx.fillStyle = '#000'; lctx.fillRect(0, 0, lvl.width, lvl.height); }
    activeStreams[nodeIdx] = {};
    _updateSourceBtn(nodeIdx, false);
  }

  function _updateSourceBtn(nodeIdx, on) {
    var p = document.getElementById('source-' + nodeIdx);
    if (!p) return;
    var btn = p.querySelector('.source-header button');
    if (btn) { btn.textContent = on ? 'Stop' : 'Start'; btn.style.background = on ? '#b91c1c' : '#2d5a7b'; }
  }

  /* ── Frontend MediaPipe inference ─────────────────────── */

  var _cvDetectors = {};  // cvIndex -> {detector, raf, running}

  var _POSE_CONNECTIONS = [
    [11,12],[11,13],[13,15],[12,14],[14,16],
    [11,23],[12,24],[23,24],
    [23,25],[25,27],[24,26],[26,28],
    [27,29],[29,31],[28,30],[30,32],
    [0,1],[1,2],[2,3],[3,7],[0,4],[4,5],[5,6],[6,8],[9,10]
  ];

  async function _initCVDetector(cvCfg) {
    if (!window._mpVision) return;
    var vision = window._mpVision;
    var modelMap = {
      lite:  'https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task',
      full:  'https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_full/float16/1/pose_landmarker_full.task',
      heavy: 'https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_heavy/float16/1/pose_landmarker_heavy.task',
    };
    var modelUrl = modelMap[cvCfg.model_size] || modelMap.lite;
    var minConf  = cvCfg.min_confidence || 0.5;
    try {
      var resolver = await vision.FilesetResolver.forVisionTasks(
        'https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.32/wasm'
      );
      var detector = await vision.PoseLandmarker.createFromOptions(resolver, {
        baseOptions: { modelAssetPath: modelUrl, delegate: 'GPU' },
        runningMode: 'VIDEO',
        numPoses: 1,
        minPoseDetectionConfidence: minConf,
        minPosePresenceConfidence:  minConf,
        minTrackingConfidence:      minConf,
      });
      return detector;
    } catch(e) { console.error('[CV] Init failed:', e); return null; }
  }

  function _startCVLoop(cvCfg, detector) {
    var srcIdx = cvCfg.source_index;
    var prvIdx = cvCfg.preview_index;
    var video  = document.getElementById('source-video-' + srcIdx);
    var canvas = document.getElementById('source-canvas-' + srcIdx);
    if (!video || !canvas) return;

    var state = { detector: detector, running: true, raf: null };
    _cvDetectors[cvCfg.index] = state;

    /* Offscreen canvas for compositing webcam + skeleton (preview output) */
    var offCvs = document.createElement('canvas');
    var offCtx = offCvs.getContext('2d');

    var lastTs = -1;
    function loop() {
      if (!state.running) return;
      state.raf = requestAnimationFrame(loop);
      if (!video.videoWidth || video.paused) return;
      var ts = performance.now();
      if (ts - lastTs < 33) return;  /* ~30 fps cap */
      lastTs = ts;

      var w = video.videoWidth, h = video.videoHeight;
      var landmarks = null;
      try {
        var result = detector.detectForVideo(video, ts);
        if (result.landmarks && result.landmarks.length > 0) {
          landmarks = result.landmarks[0];
        }
      } catch(_) {}

      /* Draw overlay on source canvas */
      if (canvas.width !== w || canvas.height !== h) { canvas.width = w; canvas.height = h; }
      var ctx = canvas.getContext('2d');
      ctx.clearRect(0, 0, w, h);
      if (landmarks) _drawPoseFull(ctx, landmarks, w, h);

      /* Composite to preview panel */
      if (prvIdx >= 0) {
        var panel   = document.getElementById('preview-' + prvIdx);
        var content = document.getElementById('preview-content-' + prvIdx);
        if (panel && content) {
          panel.style.display = 'block';
          var prvCanvas = content.querySelector('canvas');
          if (!prvCanvas) {
            prvCanvas = document.createElement('canvas');
            prvCanvas.style.maxWidth = '100%';
            prvCanvas.style.borderRadius = '4px';
            prvCanvas.style.display = 'block';
            content.innerHTML = '';
            content.appendChild(prvCanvas);
          }
          if (prvCanvas.width !== w || prvCanvas.height !== h) { prvCanvas.width = w; prvCanvas.height = h; }
          offCvs.width = w; offCvs.height = h;
          offCtx.drawImage(video, 0, 0);
          if (landmarks) _drawPoseFull(offCtx, landmarks, w, h);
          var pctx = prvCanvas.getContext('2d');
          pctx.drawImage(offCvs, 0, 0);
        }
      }
    }
    loop();
  }

  function _drawPoseFull(ctx, landmarks, w, h) {
    ctx.strokeStyle = 'rgba(0, 255, 100, 0.85)';
    ctx.lineWidth = 2;
    for (var c = 0; c < _POSE_CONNECTIONS.length; c++) {
      var a = landmarks[_POSE_CONNECTIONS[c][0]], b = landmarks[_POSE_CONNECTIONS[c][1]];
      if (a && b) {
        ctx.beginPath(); ctx.moveTo(a.x*w, a.y*h); ctx.lineTo(b.x*w, b.y*h); ctx.stroke();
      }
    }
    ctx.fillStyle = 'rgba(255, 80, 80, 0.9)';
    for (var i = 0; i < landmarks.length; i++) {
      ctx.beginPath(); ctx.arc(landmarks[i].x*w, landmarks[i].y*h, 4, 0, Math.PI*2); ctx.fill();
    }
  }

  function _stopCVDetectors() {
    for (var key in _cvDetectors) {
      var s = _cvDetectors[key];
      s.running = false;
      if (s.raf) cancelAnimationFrame(s.raf);
      if (s.detector) try { s.detector.close(); } catch(e) {}
    }
    _cvDetectors = {};
  }

  /* Auto-start frontend CV when source video begins playing */
  function _tryStartFrontendCV() {
    var cvNodes = MEDIA_INFO.cv_nodes || [];
    var pending = false;
    for (var ci = 0; ci < cvNodes.length; ci++) {
      var cv = cvNodes[ci];
      if (cv.inference_location !== 'frontend') continue;
      if (_cvDetectors[cv.index]) continue;  /* already running */
      var srcIdx = cv.source_index;
      if (srcIdx < 0) continue;
      var video = document.getElementById('source-video-' + srcIdx);
      if (!video || !video.srcObject) { pending = true; continue; }
      if (!window._mpVision) { pending = true; continue; }
      /* Video + MediaPipe ready — init detector and start loop */
      (function(cvCfg) {
        _initCVDetector(cvCfg).then(function(det) {
          if (det) _startCVLoop(cvCfg, det);
        });
      })(cv);
    }
    /* Retry until all CV nodes are running (MediaPipe CDN may still be loading) */
    if (pending) setTimeout(_tryStartFrontendCV, 500);
  }
"""

	def _save(self):
		data = {slug: app.model_dump() for slug, app in self._apps.items()}
		with open(self._config_path, "w") as f:
			json.dump(data, f, indent=2)

	def _load(self):
		if not os.path.exists(self._config_path):
			return
		try:
			import credentials as _creds
			raw = _creds.load_json(self._config_path)
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


def setup_published_apps_api(app: FastAPI, app_mgr: PublishedAppManager, gallery_mgr=None):
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
				# 1) Try workspace manager first
				ws = app_mgr._ws_mgr.get_default_workspace()
				wf = await ws.manager.get(request.workflow_name)
				if wf is not None:
					try:
						workflow = json.loads(wf.model_dump_json())
					except Exception:
						workflow = json.loads(json.dumps(wf.model_dump(), default=str))
				# 2) Fallback: search gallery by title (case-insensitive)
				if workflow is None and gallery_mgr:
					q = request.workflow_name.lower()
					for item in gallery_mgr._items.values():
						if item.title.lower() == q:
							workflow = item.workflow
							if not request.description and item.description:
								request.description = item.description
							break
				if workflow is None:
					return JSONResponse(status_code=404, content={"error": f"Workflow '{request.workflow_name}' not found"})
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
	async def apps_page(slug: str, request: Request, embed: bool = False):
		"""Serve the auto-generated HTML form for a published app."""
		published_app = app_mgr.get(slug)
		if not published_app or not published_app.enabled:
			return HTMLResponse("<h1>App not found</h1>", status_code=404)
		base_url = str(request.base_url).rstrip("/")
		html = app_mgr.render_form(slug, base_url, embed=embed)
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
