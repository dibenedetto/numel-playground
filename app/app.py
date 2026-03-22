# app

import warnings

# Suppress harmless UnsupportedFieldAttributeWarning spam emitted by agno's
# internal Pydantic models (alias/validation_alias on union members).
# These originate in pydantic._internal._generate_schema — not our code.
warnings.filterwarnings(
	"ignore",
	message = r".*attribute.*has no effect in the context it was used.*",
	module  = r"pydantic.*",
)


import argparse
import asyncio
import io
import os
import sys
import uvicorn
import webbrowser
import zipfile
from   fastapi.staticfiles  import StaticFiles


# Add project root and app/ dir to sys.path so both internal packages
# (tools, toolkits.*) and contrib packages (contrib.toolkits.*) are importable
# regardless of which directory the process is started from.
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_app_dir      = os.path.dirname(os.path.abspath(__file__))
if _project_root not in sys.path:
	sys.path.insert(0, _project_root)
if _app_dir not in sys.path:
	sys.path.insert(1, _app_dir)


from   dotenv    import load_dotenv
from   fastapi   import FastAPI, HTTPException, Request
from   fastapi.responses import StreamingResponse
from   inspect   import getsource
from   typing    import Any, Optional


import schema


import re        as _re
import subprocess
import threading

from   agent_tasks   import AgentTaskManager, setup_agent_tasks_api
from   exec_history  import ExecHistoryManager
from   api       import setup_api
import credentials as _creds
from   channels  import ChannelRegistry
from   channels.api            import setup_channel_api
from   channels.telegram_adapter  import TelegramAdapter
from   channels.whatsapp_adapter  import WhatsAppAdapter
from   channels.discord_adapter   import DiscordAdapter
from   channels.signal_adapter    import SignalAdapter
from   channels.slack_adapter     import SlackAdapter
from   channels.teams_adapter     import TeamsAdapter
from   channels.webhook_adapter   import WebhookChannelAdapter
from   console   import ConsoleAgentManager, setup_console_api
from   event_bus import EventBus, get_event_bus
from   gallery   import GalleryManager, setup_gallery_api
from   memory    import MemoryStore
from   published_apps import PublishedAppManager, setup_published_apps_api
from   utils     import add_middleware, log_print, seed_everything
from   workspace import WorkspaceManager as WSManager


load_dotenv()


DEFAULT_APP_SEED : int = 7
DEFAULT_APP_PORT : int = 11360

# ── Webhook tunnel (cloudflared / ngrok) ─────────────────────────────────────
_tunnel_url  : Optional[str] = None
_tunnel_proc : Optional[Any] = None


def _start_tunnel(port: int) -> None:
	"""Try cloudflared then ngrok; parse and store the public URL."""
	global _tunnel_url, _tunnel_proc
	# --- cloudflared ---
	try:
		proc = subprocess.Popen(
			["cloudflared", "tunnel", "--url", f"http://localhost:{port}"],
			stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
			text=True, bufsize=1,
		)
		_tunnel_proc = proc
		for line in proc.stdout:
			m = _re.search(r'https://[a-zA-Z0-9-]+\.trycloudflare\.com', line)
			if m:
				_tunnel_url = m.group(0)
				log_print(f"🌐 Tunnel URL (cloudflared): {_tunnel_url}")
				return
	except FileNotFoundError:
		pass
	# --- ngrok ---
	try:
		import time, urllib.request, json as _json
		proc = subprocess.Popen(
			["ngrok", "http", str(port)],
			stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
			text=True,
		)
		_tunnel_proc = proc
		time.sleep(2)
		try:
			with urllib.request.urlopen("http://localhost:4040/api/tunnels", timeout=3) as resp:
				data    = _json.loads(resp.read())
				tunnels = data.get("tunnels", [])
				if tunnels:
					_tunnel_url = tunnels[0]["public_url"]
					log_print(f"🌐 Tunnel URL (ngrok): {_tunnel_url}")
		except Exception:
			pass
	except FileNotFoundError:
		pass


def _asyncio_exception_handler(loop, context):
	# Suppress harmless ConnectionResetError noise from Windows asyncio Proactor
	# transport when the browser closes a fetch connection before the server finishes.
	# (WinError 10054 — WSAECONNRESET — in _ProactorBasePipeTransport._call_connection_lost)
	if isinstance(context.get('exception'), ConnectionResetError):
		return
	loop.default_exception_handler(context)


async def run_server(args: Any):
	log_print("Server starting...")

	asyncio.get_event_loop().set_exception_handler(_asyncio_exception_handler)

	if args.seed != 0:
		seed_everything(args.seed)

	event_bus     : EventBus  = get_event_bus()
	workspace_mgr : WSManager = WSManager(
		base_port    = args.port,
		event_bus    = event_bus,
		storage_root = os.path.join(_app_dir, "workspaces"),
	)
	await workspace_mgr.initialize()

	schema_code = getsource(schema)

	app: FastAPI = FastAPI(title="App")
	add_middleware(app)

	# ── Auth Provider ─────────────────────────────────────────
	from providers_impl.loader import load_providers as _load_providers
	_auth_provider, _data_provider, _exec_provider = _load_providers()

	# Public routes that don't require authentication
	_PUBLIC_ROUTES = frozenset({
		"/auth/login", "/auth/register", "/auth/status",
		"/", "/status", "/ping",
	})

	@app.middleware("http")
	async def auth_middleware(request: Request, call_next):
		"""Inject request.state.user from bearer token.  Skip for public routes."""
		request.state.user = None
		request.state.auth = _auth_provider

		path = request.url.path.rstrip("/")
		# Skip auth for public routes, static files, and when auth is disabled
		if (path in _PUBLIC_ROUTES
			or path.startswith("/web")
			or path.startswith("/ws")
			or _auth_provider.__class__.__name__ == "NoneAuthProvider"):
			return await call_next(request)

		token = request.headers.get("authorization", "").removeprefix("Bearer ").strip()
		if token:
			user = await _auth_provider.authenticate(token)
			if user:
				request.state.user = user

		return await call_next(request)

	# ── Auth Routes ───────────────────────────────────────────

	@app.post("/auth/register")
	async def auth_register(request: Request):
		try:
			body = await request.json()
		except Exception:
			raise HTTPException(400, "Invalid JSON body")
		username = body.get("username", "").strip()
		email    = body.get("email", "").strip()
		password = body.get("password", "")
		if not username or not password:
			raise HTTPException(400, "username and password are required")
		if not email:
			email = f"{username}@local"
		try:
			user  = await _auth_provider.create_user(username, email, password)
			token = await _auth_provider.login(username, password)
			return {"token": token, "user": {"id": user.id, "username": user.username, "email": user.email, "role": user.role.value}}
		except ValueError as e:
			raise HTTPException(409, str(e))

	@app.post("/auth/login")
	async def auth_login(request: Request):
		try:
			body = await request.json()
		except Exception:
			raise HTTPException(400, "Invalid JSON body")
		username = body.get("username", "").strip()
		password = body.get("password", "")
		if not username or not password:
			raise HTTPException(400, "username and password are required")
		token = await _auth_provider.login(username, password)
		if not token:
			raise HTTPException(401, "Invalid credentials")
		user = await _auth_provider.get_user_by_username(username)
		return {"token": token, "user": {"id": user.id, "username": user.username, "email": user.email, "role": user.role.value}}

	@app.post("/auth/logout")
	async def auth_logout(request: Request):
		token = request.headers.get("authorization", "").removeprefix("Bearer ").strip()
		if token:
			await _auth_provider.logout(token)
		return {"ok": True}

	@app.post("/auth/me")
	async def auth_me(request: Request):
		user = request.state.user
		if not user:
			raise HTTPException(401, "Not authenticated")
		quota = await _auth_provider.get_quota(user.id)
		return {
			"user": {"id": user.id, "username": user.username, "email": user.email, "role": user.role.value},
			"quota": {
				"cpu_seconds_remaining":   quota.cpu_seconds_remaining,
				"max_concurrent_runs":     quota.max_concurrent_runs,
				"storage_bytes_remaining": quota.storage_bytes_remaining,
				"max_loop_hours":          quota.max_loop_hours,
				"gpu_hours_remaining":     quota.gpu_hours_remaining,
			}
		}

	@app.post("/auth/status")
	async def auth_status():
		"""Check if auth is enabled and what provider is active."""
		provider_name = _auth_provider.__class__.__name__
		enabled = provider_name != "NoneAuthProvider"
		return {"enabled": enabled, "provider": provider_name}

	# Serve the frontend from /web — must be mounted AFTER api routes are registered
	_web_dir = os.path.join(_project_root, "web")

	host   = "0.0.0.0"
	port   = args.port
	config = uvicorn.Config(app, host=host, port=port)
	server = uvicorn.Server(config)

	# ── Persistent Memory ─────────────────────────────────────
	memory_store = MemoryStore()
	memory_store.initialize()

	# ── Console Agent ─────────────────────────────────────────
	console_mgr = ConsoleAgentManager(workspace_mgr, event_bus, port=args.port + 1,
									  memory_store=memory_store)
	console_mgr.setup_proactive_listeners()

	# ── Channel Adapters ──────────────────────────────────────
	async def channel_message_handler(msg):
		"""Route incoming channel messages to the console agent."""
		try:
			result = await console_mgr.chat(
				message    = msg.content,
				session_id = msg.metadata.get("session_id") or f"ch_{msg.channel_type}_{msg.sender_id}",
			)
			return result.get("response", "")
		except Exception as e:
			return f"Error: {e}"

	channel_registry = ChannelRegistry(message_handler=channel_message_handler,
									   config_path=os.path.join(_app_dir, "channels.json"))
	# Register adapter types
	ChannelRegistry.register_type("telegram", TelegramAdapter)
	ChannelRegistry.register_type("whatsapp", WhatsAppAdapter)
	ChannelRegistry.register_type("discord",  DiscordAdapter)
	ChannelRegistry.register_type("slack",    SlackAdapter)
	ChannelRegistry.register_type("signal",   SignalAdapter)
	ChannelRegistry.register_type("teams",    TeamsAdapter)
	ChannelRegistry.register_type("webhook",  WebhookChannelAdapter)
	channel_registry.load()

	# ── Workflow Gallery ──────────────────────────────────────
	gallery_mgr = GalleryManager()
	gallery_mgr.initialize()

	# ── Autonomous Agent Tasks ────────────────────────────────
	task_mgr = AgentTaskManager(console_mgr)
	task_mgr.initialize(event_bus)

	# ── Published Apps ────────────────────────────────────────
	pub_app_mgr = PublishedAppManager(workspace_mgr)
	pub_app_mgr.initialize()

	# ── Execution History ─────────────────────────────────────
	exec_history = ExecHistoryManager()

	# ── API Routes (order matters: specific routes before static mount) ──
	setup_api(server, app, event_bus, schema_code, workspace_mgr)
	setup_console_api(app, console_mgr)
	setup_channel_api(app, channel_registry)
	setup_gallery_api(app, gallery_mgr)
	setup_agent_tasks_api(app, task_mgr)
	setup_published_apps_api(app, pub_app_mgr)

	# ── Execution History Routes ───────────────────────────────

	@app.get("/exec-history")
	async def get_exec_history(workflow_name: str = None, limit: int = 100, offset: int = 0):
		return exec_history.list(workflow_name=workflow_name, limit=limit, offset=offset)

	@app.get("/exec-history/{execution_id}")
	async def get_exec_record(execution_id: str):
		rec = exec_history.get(execution_id)
		if not rec:
			raise HTTPException(status_code=404, detail="Not found")
		return rec

	@app.delete("/exec-history")
	async def clear_exec_history(workflow_name: str = None):
		exec_history.clear(workflow_name=workflow_name)
		return {"ok": True}

	@app.post("/exec-history/record")
	async def record_execution(request: Request):
		body = await request.json()
		rec = exec_history.record(**body)
		return rec.model_dump()

	# ── Workspace ZIP Export ───────────────────────────────────

	@app.get("/workspace/export")
	async def export_workspace():
		"""Export entire workspace (workflows + configs) as a ZIP archive."""
		workspace_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
		include_patterns = [
			"app/console_agent.json",
			"app/agent_tasks.json",
			"app/published_apps.json",
			"app/gallery.json",
			"app/exec_history.json",
		]

		buf = io.BytesIO()
		with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
			for pattern in include_patterns:
				full_path = os.path.join(workspace_dir, pattern)
				if os.path.exists(full_path):
					zf.write(full_path, pattern)
			# Also serialize workflows directly from the workspace manager
			try:
				ws_obj   = workspace_mgr.get_default_workspace()
				mgr      = ws_obj.manager
				wf_names = await mgr.list()
				for name in wf_names:
					wf = await mgr.get(name)
					if wf:
						import json as _json
						zf.writestr(f"workflows/{name}.json", _json.dumps(wf.model_dump(), indent=2))
			except Exception:
				pass
		buf.seek(0)
		from datetime import datetime as _dt
		filename = f"numel-workspace-{_dt.now().strftime('%Y%m%d-%H%M%S')}.zip"
		return StreamingResponse(
			buf,
			media_type="application/zip",
			headers={"Content-Disposition": f'attachment; filename="{filename}"'},
		)

	# ── Scheduled Workflow Runs ────────────────────────────────

	from pydantic import BaseModel as _BaseModel

	class ScheduledRunRequest(_BaseModel):
		workflow_name : str
		delay_seconds : float        = 0
		inputs        : Optional[dict] = None

	@app.post("/schedule-run")
	async def schedule_run(request: ScheduledRunRequest):
		"""Schedule a workflow to run after a delay (or immediately)."""
		async def _run_later():
			if request.delay_seconds > 0:
				await asyncio.sleep(request.delay_seconds)
			try:
				ws_obj = workspace_mgr.get_default_workspace()
				mgr    = ws_obj.manager
				engine = ws_obj.engine
				wf = await mgr.get(request.workflow_name)
				if wf is None:
					return
				impl = await mgr.impl(request.workflow_name)
				if not impl:
					return
				exec_id = await engine.start_workflow(
					workflow     = impl["workflow"],
					backend      = impl["backend"],
					initial_data = request.inputs or {},
				)
				log_print(f"Scheduled run started: {request.workflow_name} → {exec_id}")
			except Exception as e:
				log_print(f"Scheduled run failed: {e}")

		asyncio.create_task(_run_later())
		return {"ok": True, "scheduled": True, "workflow_name": request.workflow_name}

	# ── Workspace Changed Notification ────────────────────────

	@app.post("/workspace/changed")
	async def notify_workspace_changed(request: Request):
		"""Called by WorkspaceToolkit after saving; broadcasts workspace.changed
		over the /events WebSocket so the UI can reload the workflow."""
		body = {}
		try:
			body = await request.json()
		except Exception:
			pass
		from event_bus import WorkflowEvent, EventType as _ET
		import uuid as _uuid
		from datetime import datetime as _dt, timezone as _tz
		ev = WorkflowEvent(
			event_id   = str(_uuid.uuid4()),
			event_type = _ET.WORKSPACE_CHANGED,
			timestamp  = _dt.now(_tz.utc).isoformat(),
			data       = {"name": body.get("name", "")},
		)
		await event_bus.publish(ev)
		return {"ok": True}

	# ── Credential Store ───────────────────────────────────────

	@app.get("/credentials")
	async def list_credentials():
		return {"names": _creds.list_names()}

	@app.post("/credentials/{name}")
	async def set_credential(name: str, request: Request):
		body = await request.json()
		_creds.set(name, body.get("value", ""))
		return {"ok": True}

	@app.delete("/credentials/{name}")
	async def delete_credential(name: str):
		return {"ok": _creds.delete(name)}

	# ── Webhook Tunnel ─────────────────────────────────────────

	@app.get("/tunnel/url")
	async def get_tunnel_url():
		return {"url": _tunnel_url}

	# Serve index.html at / and all static assets (JS, CSS, dist/*)
	app.mount("/", StaticFiles(directory=_web_dir, html=True), name="static")

	url = f"http://localhost:{port}/"
	log_print(f"Frontend: {url}")
	webbrowser.open(url)

	# Start auto-start channels
	await channel_registry.start_all()

	# Start tunnel if requested
	if getattr(args, "tunnel", False):
		t = threading.Thread(target=_start_tunnel, args=(port,), daemon=True)
		t.start()

	await server.serve()

	# Shutdown
	await task_mgr.stop_all()
	await channel_registry.stop_all()
	await console_mgr.stop()
	await workspace_mgr.shutdown()

	log_print("Server shut down.")


def main():
	parser = argparse.ArgumentParser(description="Numel Playground App")
	parser .add_argument("--port",   type=int,  default=DEFAULT_APP_PORT, help="Listening port for control server"     )
	parser .add_argument("--seed",   type=int,  default=DEFAULT_APP_SEED, help="Seed for pseudorandom number generator")
	parser .add_argument("--tunnel", action="store_true",                  help="Start a cloudflared/ngrok tunnel for public webhook access")
	args   = parser.parse_args()

	asyncio.run(run_server(args))


if __name__ == "__main__":
	main()
