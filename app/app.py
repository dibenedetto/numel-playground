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
import time
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

from   providers.models import AccessLevel, Role


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
from   channels.commands        import ChannelCommandHandler
from   channels.telegram_adapter  import TelegramAdapter
from   channels.whatsapp_adapter  import WhatsAppAdapter
from   channels.discord_adapter   import DiscordAdapter
from   channels.signal_adapter    import SignalAdapter
from   channels.slack_adapter     import SlackAdapter
from   channels.email_adapter     import EmailAdapter
from   channels.teams_adapter     import TeamsAdapter
from   channels.web_adapter       import WebChannelAdapter
from   channels.webhook_adapter   import WebhookChannelAdapter
from   console   import ConsoleAgentManager, ChannelAgentPool, setup_console_api
from   event_bus import EventBus, get_event_bus
from   gallery   import GalleryManager, setup_gallery_api
from   memory    import MemoryStore, UserMemoryDB
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
		"""Inject request.state.user and request.state.workspace from bearer token."""
		request.state.user = None
		request.state.auth = _auth_provider

		path = request.url.path.rstrip("/")
		# Skip auth for public routes, static files, and when auth is disabled
		if (path in _PUBLIC_ROUTES
			or path.startswith("/web")
			or path.startswith("/ws")
			or _auth_provider.__class__.__name__ == "NoneAuthProvider"):
			# Even with auth disabled, resolve a session-based workspace
			session_id = request.headers.get("x-session-id", "").strip()
			if session_id:
				request.state.workspace = await workspace_mgr.resolve_workspace(f"guest_{session_id}")
			else:
				request.state.workspace = workspace_mgr.get_default_workspace()
			return await call_next(request)

		token = request.headers.get("authorization", "").removeprefix("Bearer ").strip()
		if token:
			user = await _auth_provider.authenticate(token)
			if user:
				request.state.user = user

		# Resolve workspace: authenticated user → per-user, guest → per-session ephemeral
		user = request.state.user
		if user:
			request.state.workspace = await workspace_mgr.resolve_workspace(user.id)
		else:
			session_id = request.headers.get("x-session-id", "").strip()
			if session_id:
				request.state.workspace = await workspace_mgr.resolve_workspace(f"guest_{session_id}")
			else:
				request.state.workspace = workspace_mgr.get_default_workspace()

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
		"""Check if auth is enabled, what provider is active, and if any users exist."""
		provider_name = _auth_provider.__class__.__name__
		enabled = provider_name != "NoneAuthProvider"
		has_users = True
		if enabled:
			try:
				users = await _auth_provider.list_users(limit=1, active_only=False)
				has_users = len(users) > 0
			except Exception:
				pass
		return {"enabled": enabled, "provider": provider_name, "has_users": has_users}

	@app.post("/auth/change-password")
	async def auth_change_password(request: Request):
		user = request.state.user
		if not user:
			raise HTTPException(401, "Not authenticated")
		try:
			body = await request.json()
		except Exception:
			raise HTTPException(400, "Invalid JSON body")
		current  = body.get("current_password", "")
		new_pw   = body.get("new_password", "")
		if not current or not new_pw:
			raise HTTPException(400, "current_password and new_password are required")
		if len(new_pw) < 4:
			raise HTTPException(400, "Password must be at least 4 characters")
		# Verify current password via login attempt
		token = await _auth_provider.login(user.username, current)
		if not token:
			raise HTTPException(403, "Current password is incorrect")
		# Invalidate the verification token
		await _auth_provider.logout(token)
		# Update password hash
		import hashlib as _hl
		new_hash = _hl.sha256(new_pw.encode()).hexdigest()
		if hasattr(_auth_provider, '_data'):
			u = _auth_provider._data["users"].get(user.id)
			if u:
				u["password_hash"] = new_hash
				_auth_provider._save()
		return {"ok": True}

	# ── Role helpers ─────────────────────────────────────────

	def _require_auth(request: Request):
		"""Return the authenticated user or raise 401."""
		user = request.state.user
		if not user:
			raise HTTPException(401, "Not authenticated")
		return user

	def _require_admin(request: Request):
		"""Return the authenticated admin user or raise 403."""
		user = _require_auth(request)
		if user.role != Role.ADMIN:
			raise HTTPException(403, "Admin access required")
		return user

	# ── Admin API Routes ─────────────────────────────────────

	@app.post("/admin/users")
	async def admin_list_users(request: Request):
		_require_admin(request)
		body = {}
		try: body = await request.json()
		except Exception: pass
		offset      = body.get("offset", 0)
		limit       = body.get("limit", 50)
		active_only = body.get("active_only", True)
		users = await _auth_provider.list_users(offset=offset, limit=limit, active_only=active_only)
		result = []
		for u in users:
			quota = await _auth_provider.get_quota(u.id)
			result.append({
				"id": u.id, "username": u.username, "email": u.email,
				"role": u.role.value, "active": u.active,
				"created_at": u.created_at, "metadata": u.metadata,
				"quota": {
					"cpu_seconds_remaining":   quota.cpu_seconds_remaining,
					"max_concurrent_runs":     quota.max_concurrent_runs,
					"storage_bytes_remaining": quota.storage_bytes_remaining,
					"gpu_hours_remaining":     quota.gpu_hours_remaining,
					"max_repos":               quota.max_repos,
				},
			})
		return {"users": result, "count": len(result)}

	@app.post("/admin/users/{user_id}")
	async def admin_get_user(user_id: str, request: Request):
		_require_admin(request)
		user = await _auth_provider.get_user(user_id)
		if not user:
			raise HTTPException(404, "User not found")
		quota = await _auth_provider.get_quota(user.id)
		perms = await _auth_provider.list_permissions(user.id)
		return {
			"user": {
				"id": user.id, "username": user.username, "email": user.email,
				"role": user.role.value, "active": user.active,
				"created_at": user.created_at, "metadata": user.metadata,
			},
			"quota": {
				"cpu_seconds_remaining":   quota.cpu_seconds_remaining,
				"max_concurrent_runs":     quota.max_concurrent_runs,
				"storage_bytes_remaining": quota.storage_bytes_remaining,
				"gpu_hours_remaining":     quota.gpu_hours_remaining,
				"max_repos":               quota.max_repos,
			},
			"permissions": [{"resource": p.resource, "access": p.access.value} for p in perms],
		}

	@app.post("/admin/users/{user_id}/update")
	async def admin_update_user(user_id: str, request: Request):
		_require_admin(request)
		body = await request.json()
		allowed = {k: v for k, v in body.items() if k in ("email", "role", "active", "metadata")}
		if not allowed:
			raise HTTPException(400, "No valid fields to update")
		user = await _auth_provider.update_user(user_id, **allowed)
		return {"user": {"id": user.id, "username": user.username, "email": user.email,
						 "role": user.role.value, "active": user.active}}

	@app.post("/admin/users/{user_id}/delete")
	async def admin_delete_user(user_id: str, request: Request):
		_require_admin(request)
		ok = await _auth_provider.delete_user(user_id)
		if not ok:
			raise HTTPException(404, "User not found")
		return {"ok": True}

	@app.post("/admin/users/{user_id}/quota")
	async def admin_update_quota(user_id: str, request: Request):
		_require_admin(request)
		body = await request.json()
		quota = await _auth_provider.update_quota(user_id, **body)
		return {
			"quota": {
				"user_id":                 quota.user_id,
				"cpu_seconds_remaining":   quota.cpu_seconds_remaining,
				"max_concurrent_runs":     quota.max_concurrent_runs,
				"storage_bytes_remaining": quota.storage_bytes_remaining,
				"gpu_hours_remaining":     quota.gpu_hours_remaining,
				"max_repos":               quota.max_repos,
			}
		}

	@app.post("/admin/users/{user_id}/permissions")
	async def admin_list_user_permissions(user_id: str, request: Request):
		_require_admin(request)
		perms = await _auth_provider.list_permissions(user_id)
		return {"permissions": [{"resource": p.resource, "access": p.access.value} for p in perms]}

	@app.post("/admin/users/{user_id}/permissions/grant")
	async def admin_grant_permission(user_id: str, request: Request):
		_require_admin(request)
		body = await request.json()
		resource = body.get("resource", "")
		access   = body.get("access", "read")
		if not resource:
			raise HTTPException(400, "resource is required")
		perm = await _auth_provider.grant_permission(user_id, resource, AccessLevel(access))
		return {"permission": {"resource": perm.resource, "user_id": perm.user_id, "access": perm.access.value}}

	@app.post("/admin/users/{user_id}/permissions/revoke")
	async def admin_revoke_permission(user_id: str, request: Request):
		_require_admin(request)
		body = await request.json()
		resource = body.get("resource", "")
		if not resource:
			raise HTTPException(400, "resource is required")
		ok = await _auth_provider.revoke_permission(user_id, resource)
		return {"ok": ok}

	@app.post("/admin/stats")
	async def admin_stats(request: Request):
		"""System-wide statistics: users, executions, active runs."""
		_require_admin(request)
		users = await _auth_provider.list_users(limit=10000, active_only=False)
		active_users  = [u for u in users if u.active]
		history_items = exec_history.list(limit=10000)
		# Active executions from default workspace engine
		active_exec_ids = []
		try:
			ws_obj = workspace_mgr.get_default_workspace()
			active_exec_ids = ws_obj.engine.list_executions()
		except Exception:
			pass
		# Breakdown by status
		status_counts = {}
		for h in history_items:
			s = h.get("status", "unknown")
			status_counts[s] = status_counts.get(s, 0) + 1
		return {
			"total_users":       len(users),
			"active_users":      len(active_users),
			"total_executions":  len(history_items),
			"active_executions": len(active_exec_ids),
			"execution_status_breakdown": status_counts,
		}

	@app.post("/admin/executions")
	async def admin_executions(request: Request):
		"""Paginated execution history for admin."""
		_require_admin(request)
		body = {}
		try: body = await request.json()
		except Exception: pass
		wf_name = body.get("workflow_name")
		limit   = body.get("limit", 100)
		offset  = body.get("offset", 0)
		items   = exec_history.list(workflow_name=wf_name, limit=limit, offset=offset)
		# Active executions
		active_exec_ids = []
		try:
			ws_obj = workspace_mgr.get_default_workspace()
			active_exec_ids = ws_obj.engine.list_executions()
		except Exception:
			pass
		return {"executions": items, "active_execution_ids": active_exec_ids}

	@app.post("/admin/executions/{execution_id}/cancel")
	async def admin_cancel_execution(execution_id: str, request: Request):
		_require_admin(request)
		try:
			ws_obj = workspace_mgr.get_default_workspace()
			state  = await ws_obj.engine.cancel_execution(execution_id)
			return {"ok": True, "state": state}
		except Exception as e:
			raise HTTPException(500, str(e))

	# Serve the frontend from /web — must be mounted AFTER api routes are registered
	_web_dir = os.path.join(_project_root, "web")

	host   = "0.0.0.0"
	port   = args.port
	config = uvicorn.Config(app, host=host, port=port)
	server = uvicorn.Server(config)

	# ── Persistent Memory ─────────────────────────────────────
	memory_store = MemoryStore()
	memory_store.initialize()
	user_memory_db = UserMemoryDB()

	# ── Console Agent ─────────────────────────────────────────
	console_mgr = ConsoleAgentManager(workspace_mgr, event_bus, port=args.port + 1,
									  memory_store=memory_store,
									  user_memory_db=user_memory_db)
	console_mgr.setup_proactive_listeners()

	# ── Channel Adapters ──────────────────────────────────────
	# Discover available toolkits for channel command handler
	_tk_dirs = [
		os.path.join(_app_dir, "toolkits"),
		os.path.join(os.path.dirname(_app_dir), "contrib", "toolkits"),
	]
	_available_toolkits = sorted({
		f.removesuffix(".py")
		for d in _tk_dirs if os.path.isdir(d)
		for f in os.listdir(d)
		if f.endswith(".py") and not f.startswith("_")
	})

	# Read default toolkits from console_agent.json
	_cfg_path = os.path.join(_app_dir, "console_agent.json")
	_default_toolkits = _creds.load_json(_cfg_path).get("toolkits", [])

	async def _planner_callback(action, user_id, session_id, config):
		"""Bridge between channel /planner command and ConsoleAgentManager."""
		if action == "enable":
			await console_mgr.enable_planner(config, user_id=user_id, session_id=session_id)
			pkey = console_mgr._planner_key(user_id, session_id)
			ps = console_mgr._planners.get(pkey)
			if ps:
				return (f"Planner enabled (profile={ps.profile}, "
						f"max_iter={ps.max_turns}, timeout={ps.timeout}s, "
						f"session_timeout={ps.session_timeout}s)")
			return "Planner enabled for this session."
		elif action == "status":
			pkey = console_mgr._planner_key(user_id, session_id)
			ps = console_mgr._planners.get(pkey)
			if not ps or not ps.enabled:
				return "No active planner for this session."
			elapsed = int(time.time() - ps.session_start)
			return (f"Planner active\n"
					f"  Profile: {ps.profile}\n"
					f"  Turns: {ps.turn_count}/{ps.max_turns}\n"
					f"  Elapsed: {elapsed}s / {int(ps.session_timeout)}s\n"
					f"  Per-turn timeout: {int(ps.timeout)}s\n"
					f"  Pending events: {len(ps.pending)}")
		else:
			console_mgr.disable_planner(user_id=user_id, session_id=session_id)
			return "Planner disabled for this session."

	channel_cmd = ChannelCommandHandler(
		auth_provider=_auth_provider,
		store_path=os.path.join(_app_dir, "channel_users.json"),
		available_toolkits=_available_toolkits,
		default_toolkits=_default_toolkits,
		planner_callback=_planner_callback,
	)

	# Read pool config from console_agent.json
	_pool_cfg = _creds.load_json(_cfg_path).get("channel_pool", {})
	channel_pool = ChannelAgentPool(
		workspace_mgr=workspace_mgr, memory_store=memory_store,
		user_memory_db=user_memory_db,
		idle_timeout=_pool_cfg.get("idle_timeout", 1800))

	async def channel_message_handler(msg):
		"""Route incoming channel messages to per-user agents."""
		try:
			# Check for /commands first
			cmd_response = await channel_cmd.handle(
				msg.content, msg.channel_type, msg.sender_id, msg.sender_name)
			if cmd_response is not None:
				# Toolkit change may require agent rebuild
				if msg.content.strip().lower().startswith("/toolkit "):
					session_id = msg.metadata.get("session_id") or \
						f"ch_{msg.channel_type}_{msg.sender_id}"
					await channel_pool.evict(session_id)
				return cmd_response

			session_id = msg.metadata.get("session_id") or f"ch_{msg.channel_type}_{msg.sender_id}"
			# Resolve per-user identity and toolkits
			numel_user_id = channel_cmd.get_linked_user_id(msg.channel_type, msg.sender_id)
			toolkits = channel_cmd.get_enabled_toolkits(msg.channel_type, msg.sender_id)
			sender   = channel_cmd.get_linked_username(msg.channel_type, msg.sender_id) \
				or msg.sender_name or msg.sender_id
			mem_user_id = numel_user_id or f"anon_{msg.channel_type}_{msg.sender_id}"
			result = await channel_pool.chat(
				msg.content, session_id,
				toolkits=toolkits or None,
				sender_name=sender,
				user_id=mem_user_id,
			)
			return result.get("response", "") or result.get("error", "")
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
	ChannelRegistry.register_type("email",    EmailAdapter)
	ChannelRegistry.register_type("webhook",  WebhookChannelAdapter)
	ChannelRegistry.register_type("web",      WebChannelAdapter)
	channel_registry.load()
	# Make channel registry available to workspace engines and agent pool
	workspace_mgr._channel_registry = channel_registry
	for _ws in workspace_mgr._workspaces.values():
		_ws.engine.channel_registry = channel_registry
	channel_pool._channel_reg = channel_registry

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

	# Wire pool and channel registry into console manager
	console_mgr.set_channel_pool(channel_pool)
	console_mgr._channel_reg = channel_registry

	# ── API Routes (order matters: specific routes before static mount) ──
	setup_api(server, app, event_bus, schema_code, workspace_mgr)
	setup_console_api(app, console_mgr, channel_pool=channel_pool, channel_cmd=channel_cmd)
	setup_channel_api(app, channel_registry, pool=channel_pool)
	setup_gallery_api(app, gallery_mgr)
	setup_agent_tasks_api(app, task_mgr)
	setup_published_apps_api(app, pub_app_mgr)

	# ── Execution History Routes ───────────────────────────────

	@app.post("/exec-history")
	async def get_exec_history(request: Request):
		body = {}
		try: body = await request.json()
		except Exception: pass
		wf_name = body.get("workflow_name")
		limit   = body.get("limit", 100)
		offset  = body.get("offset", 0)
		# Scope to current user (admins see all)
		user = getattr(request.state, 'user', None)
		user_id = None
		if user and user.role != Role.ADMIN:
			user_id = user.id
		return exec_history.list(workflow_name=wf_name, user_id=user_id, limit=limit, offset=offset)

	@app.post("/exec-history/{execution_id}")
	async def get_exec_record(execution_id: str):
		rec = exec_history.get(execution_id)
		if not rec:
			raise HTTPException(status_code=404, detail="Not found")
		return rec

	@app.post("/exec-history/clear")
	async def clear_exec_history(request: Request):
		body = {}
		try: body = await request.json()
		except Exception: pass
		wf_name = body.get("workflow_name")
		exec_history.clear(workflow_name=wf_name)
		return {"ok": True}

	@app.post("/exec-history/record")
	async def record_execution(request: Request):
		body = await request.json()
		# Inject user_id from auth context
		user = getattr(request.state, 'user', None)
		if user and 'user_id' not in body:
			body['user_id'] = user.id
		rec = exec_history.record(**body)
		return rec.model_dump()

	# ── Workspace ZIP Export ───────────────────────────────────

	@app.post("/workspace/export")
	async def export_workspace(request: Request):
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
				ws_obj   = request.state.workspace
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
	async def schedule_run(request: ScheduledRunRequest, req: Request):
		"""Schedule a workflow to run after a delay (or immediately)."""
		ws_obj = req.state.workspace
		async def _run_later():
			if request.delay_seconds > 0:
				await asyncio.sleep(request.delay_seconds)
			try:
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

	@app.post("/credentials")
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

	@app.post("/tunnel/url")
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
