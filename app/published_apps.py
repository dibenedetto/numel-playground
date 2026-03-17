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
				inputs: Optional[List[dict]] = None, author: str = "") -> PublishedApp:
		"""Publish a workflow as a web app."""
		slug = self._make_slug(name)

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

	async def run(self, slug: str, input_data: Dict[str, Any]) -> Dict[str, Any]:
		"""Run a published app with the given inputs."""
		app = self._apps.get(slug)
		if not app or not app.enabled:
			return {"error": "App not found or disabled"}

		app.runs += 1
		self._save()

		try:
			ws = self._ws_mgr.get_default_workspace()
			mgr = ws.manager
			engine = ws.engine

			# Load workflow temporarily
			temp_name = f"_published_{slug}_{uuid.uuid4().hex[:6]}"
			await mgr.add(app.workflow, temp_name)
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
		"""Generate an HTML form for a published app."""
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
		   display: flex; align-items: center; justify-content: center; }}
	.container {{ max-width: 600px; width: 100%; padding: 40px 24px; }}
	h1 {{ font-size: 24px; margin-bottom: 8px; color: #fff; }}
	.desc {{ color: #888; margin-bottom: 24px; font-size: 14px; }}
	.field {{ margin-bottom: 16px; }}
	label {{ display: block; font-size: 13px; color: #aaa; margin-bottom: 4px; }}
	input, textarea {{ width: 100%; padding: 10px 12px; border: 1px solid #333;
		border-radius: 6px; background: #1a1a22; color: #fff; font-size: 14px; }}
	input:focus, textarea:focus {{ border-color: #2d5a7b; outline: none; }}
	textarea {{ min-height: 80px; resize: vertical; }}
	button {{ background: #2d5a7b; color: #fff; border: none; border-radius: 6px;
		padding: 12px 24px; font-size: 14px; cursor: pointer; width: 100%; margin-top: 8px; }}
	button:hover {{ background: #3a6f96; }}
	button:disabled {{ opacity: 0.5; cursor: not-allowed; }}
	.result {{ margin-top: 24px; padding: 16px; background: #1a1a22;
		border: 1px solid #333; border-radius: 6px; white-space: pre-wrap;
		font-family: monospace; font-size: 13px; max-height: 400px; overflow-y: auto; }}
	.error {{ border-color: #d9534f; color: #f88; }}
	.footer {{ text-align: center; margin-top: 32px; font-size: 11px; color: #555; }}
	.footer a {{ color: #6ba3d6; text-decoration: none; }}
</style>
</head>
<body>
<div class="container">
	<h1>{app.name}</h1>
	<p class="desc">{app.description or "Run this workflow"}</p>
	<form id="appForm">
		{input_fields}
		<button type="submit" id="runBtn">Run</button>
	</form>
	<div id="result" class="result" style="display:none"></div>
	<div class="footer">Powered by <a href="/">Numel Playground</a></div>
</div>
<script>
document.getElementById('appForm').addEventListener('submit', async (e) => {{
	e.preventDefault();
	const btn = document.getElementById('runBtn');
	const resultDiv = document.getElementById('result');
	btn.disabled = true;
	btn.textContent = 'Running...';
	resultDiv.style.display = 'none';
	resultDiv.className = 'result';

	const formData = new FormData(e.target);
	const data = Object.fromEntries(formData.entries());

	try {{
		const resp = await fetch('{base_url}/apps/{slug}/run', {{
			method: 'POST',
			headers: {{ 'Content-Type': 'application/json' }},
			body: JSON.stringify(data),
		}});
		const result = await resp.json();
		resultDiv.style.display = 'block';
		if (result.error) {{
			resultDiv.className = 'result error';
			resultDiv.textContent = 'Error: ' + result.error;
		}} else {{
			resultDiv.textContent = JSON.stringify(result.outputs, null, 2);
		}}
	}} catch (err) {{
		resultDiv.style.display = 'block';
		resultDiv.className = 'result error';
		resultDiv.textContent = 'Error: ' + err.message;
	}}
	btn.disabled = false;
	btn.textContent = 'Run';
}});
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
	name        : str
	workflow    : Dict[str, Any]
	description : str          = ""
	inputs      : Optional[List[dict]] = None
	author      : str          = ""


def setup_published_apps_api(app: FastAPI, app_mgr: PublishedAppManager):
	"""Register published app routes."""

	# Management API
	@app.post("/apps/list")
	async def apps_list():
		return app_mgr.list()

	@app.post("/apps/publish")
	async def apps_publish(request: PublishRequest):
		result = app_mgr.publish(
			name        = request.name,
			workflow    = request.workflow,
			description = request.description,
			inputs      = request.inputs,
			author      = request.author,
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

	@app.post("/apps/{slug}/run")
	async def apps_run(slug: str, request: Request):
		"""Execute a published app with the given inputs."""
		try:
			body = await request.json()
		except Exception:
			body = {}
		result = await app_mgr.run(slug, body)
		return JSONResponse(result)
