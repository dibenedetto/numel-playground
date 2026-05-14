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
import json
import os
import secrets
import shutil
import sys
import time
import uvicorn
import webbrowser
from   contextlib import asynccontextmanager
from   pathlib import Path
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
from   fastapi.responses import JSONResponse
from   inspect   import getsource, isawaitable
from   typing    import Any, Optional
from   urllib.parse import urlsplit, urlunsplit

import schema


import re        as _re
import subprocess
import threading

from   agent_tasks   import AgentTaskManager, setup_agent_tasks_api
from   assistant_deployments import AssistantDeploymentManager, setup_assistant_deployments_api
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
from   skills    import SkillManager, setup_skills_api
from   memory    import UserMemoryDB
from   published_apps import PublishedAppManager, setup_published_apps_api
from   domain.concrete import build_db_git_platform_spec
from   domain.models import ExecutionState
from   platform_client import PlatformHttpClient, PlatformRequestError
from   platform_http import setup_platform_api
from   platform_loader import (
	resolve_platform_backend_config_path,
	load_platform_backend_config,
	build_platform_stack_from_config,
)
from   runtime_settings import get_runtime_settings
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


async def run_server(
	args: Any,
	*,
	serve: bool = True,
	open_browser: bool = True,
	start_channels: bool = True,
	start_tunnel: Optional[bool] = None,
):
	asyncio.get_event_loop().set_exception_handler(_asyncio_exception_handler)
	log_print("Server starting...")
	_runtime_settings = get_runtime_settings()
	_runtime_settings.ensure_directories()
	_server_started_at = time.time()
	if start_tunnel is None:
		start_tunnel = bool(getattr(args, "tunnel", False))

	if args.seed != 0:
		seed_everything(args.seed)

	event_bus     : EventBus  = get_event_bus()
	workspace_mgr : WSManager = WSManager(
		base_port    = args.port,
		event_bus    = event_bus,
		storage_root = _runtime_settings.workspace_storage_dir,
	)
	await workspace_mgr.initialize()

	schema_code = getsource(schema)

	_platform = None
	_platform_stack = None
	console_mgr = None
	channel_registry = None
	task_mgr = None
	assistant_deployment_mgr = None
	_shutdown_started = False
	_channels_started = False
	_browser_opened = False
	_tunnel_started = False

	async def _maybe_aclose(obj: Any) -> None:
		if obj is None:
			return
		close = getattr(obj, "aclose", None)
		if close is None:
			return
		result = close()
		if isawaitable(result):
			await result

	async def _shutdown_runtime() -> None:
		nonlocal _shutdown_started
		if _shutdown_started:
			return
		_shutdown_started = True
		if task_mgr is not None:
			await task_mgr.stop_all()
		if assistant_deployment_mgr is not None:
			await assistant_deployment_mgr.shutdown()
		if channel_registry is not None:
			await channel_registry.stop_all()
		if console_mgr is not None:
			await console_mgr.stop()
		await workspace_mgr.shutdown()
		await _maybe_aclose(_platform)
		await _maybe_aclose(_platform_stack)

	@asynccontextmanager
	async def _lifespan(_app: FastAPI):
		try:
			yield
		finally:
			await _shutdown_runtime()

	app: FastAPI = FastAPI(title="App", lifespan=_lifespan)
	add_middleware(app)

	# ── Platform Backend ──────────────────────────────────────
	_platform_config_path = resolve_platform_backend_config_path()
	_platform_config = load_platform_backend_config(_platform_config_path)
	_platform_stack = build_platform_stack_from_config(
		_platform_config,
		workspace_manager=workspace_mgr,
	)
	_platform_startup_status = {}
	_startup_validate = getattr(_platform_stack, "startup_validate", None)
	if callable(_startup_validate):
		try:
			result = _startup_validate()
			_platform_startup_status = await result if isawaitable(result) else (result or {})
		except Exception:
			await _shutdown_runtime()
			raise
	_platform_backend_name = str(_platform_config.get("backend", "local") or "local").strip().lower()
	log_print(f"Platform backend: {_platform_backend_name} ({_platform_config_path})")

	_platform_internal_token = secrets.token_urlsafe(32)
	setup_platform_api(app, _platform_stack, _platform_internal_token)
	_platform = PlatformHttpClient(app, _platform_internal_token)
	app.state.platform = _platform
	app.state.platform_backend = _platform_backend_name
	app.state.platform_backend_config = _platform_config
	app.state.platform_backend_config_path = _platform_config_path
	app.state.platform_client = _platform
	app.state.platform_stack = _platform_stack
	app.state.platform_startup_status = _platform_startup_status
	app.state.platform_target = build_db_git_platform_spec()
	app.state.platform_internal_token = _platform_internal_token
	app.state.runtime_settings = _runtime_settings

	# Public routes that don't require authentication
	_PUBLIC_ROUTES = frozenset({
		"/auth/login", "/auth/register", "/auth/status",
		"/", "/status", "/ping", "/schema", "/schema-bootstrap",
		"/docs", "/docs/file",
		"/health/live", "/health/ready",
	})

	def _platform_http_error(exc: PlatformRequestError):
		raise HTTPException(status_code=exc.status_code, detail=exc.detail)

	@app.middleware("http")
	async def auth_middleware(request: Request, call_next):
		"""Inject request.state.user and request.state.workspace from bearer token."""
		request.state.user = None
		request.state.auth = _platform

		path = request.url.path.rstrip("/")
		# Skip auth for public routes and static files.
		if (path in _PUBLIC_ROUTES
			or path.startswith("/web")
			or path.startswith("/ws")
			or path.startswith("/platform")):
			# Lightweight public routes such as auth, ping, and health checks
			# should not pay the cost of resolving a per-session guest workspace.
			request.state.workspace = workspace_mgr.get_default_workspace()
			return await call_next(request)

		token = request.headers.get("authorization", "").removeprefix("Bearer ").strip()
		if token:
			try:
				request.state.user = await _platform.authenticate(token)
			except PlatformRequestError:
				request.state.user = None
		if request.state.user is None:
			internal_token = request.headers.get("x-numel-platform-internal", "")
			acting_user_id = request.headers.get("x-numel-acting-user", "").strip()
			if internal_token == _platform_internal_token and acting_user_id:
				try:
					request.state.user = await _platform.get_user(acting_user_id)
				except PlatformRequestError:
					request.state.user = None

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
			result = await _platform.register(username, email, password)
			user = result["user"]
			return {"token": result["token"], "user": {"id": user.id, "username": user.username, "email": user.email, "role": user.role.value}}
		except ValueError as e:
			raise HTTPException(409, str(e))
		except PlatformRequestError as exc:
			_platform_http_error(exc)

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
		try:
			result = await _platform.login_result(username, password)
		except PlatformRequestError as exc:
			_platform_http_error(exc)
		if not result:
			raise HTTPException(401, "Invalid credentials")
		user = result["user"]
		return {"token": result["token"], "user": {"id": user.id, "username": user.username, "email": user.email, "role": user.role.value}}

	@app.post("/auth/logout")
	async def auth_logout(request: Request):
		token = request.headers.get("authorization", "").removeprefix("Bearer ").strip()
		if token:
			try:
				await _platform.logout(token)
			except PlatformRequestError as exc:
				_platform_http_error(exc)
		return {"ok": True}

	@app.post("/auth/me")
	async def auth_me(request: Request):
		user = request.state.user
		if not user:
			raise HTTPException(401, "Not authenticated")
		try:
			return await _platform.post_json(f"/platform/users/{user.id}", {})
		except PlatformRequestError as exc:
			_platform_http_error(exc)

	@app.post("/auth/preferences/update")
	async def auth_update_preferences(request: Request):
		user = request.state.user
		if not user:
			raise HTTPException(401, "Not authenticated")
		try:
			body = await request.json()
		except Exception:
			raise HTTPException(400, "Invalid JSON body")
		ui_preferences = body.get("ui_preferences")
		if not isinstance(ui_preferences, dict):
			raise HTTPException(400, "ui_preferences must be an object")
		try:
			bundle = await _platform.post_json(f"/platform/users/{user.id}", {})
			profile_payload = bundle.get("profile") if isinstance(bundle, dict) else {}
			profile_payload = profile_payload if isinstance(profile_payload, dict) else {}
			metadata = dict(profile_payload.get("metadata") or {})
			current_preferences = metadata.get("ui_preferences")
			current_preferences = dict(current_preferences) if isinstance(current_preferences, dict) else {}
			current_preferences.update(ui_preferences)
			metadata["ui_preferences"] = current_preferences
			await _platform.update_profile(user.id, metadata=metadata)
			updated_bundle = await _platform.post_json(f"/platform/users/{user.id}", {})
			return {
				"profile": updated_bundle.get("profile"),
				"ui_preferences": current_preferences,
			}
		except PlatformRequestError as exc:
			_platform_http_error(exc)

	@app.post("/auth/status")
	async def auth_status():
		"""Check the active auth backend and whether any local users exist."""
		try:
			return await _platform.auth_status()
		except PlatformRequestError as exc:
			_platform_http_error(exc)

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
		try:
			ok = await _platform.change_password(user.id, current, new_pw)
		except PlatformRequestError as exc:
			_platform_http_error(exc)
		if not ok:
			raise HTTPException(403, "Current password is incorrect")
		return {"ok": True}

	# ── Role helpers ─────────────────────────────────────────

	def _role_value(user) -> str:
		if not user:
			return ""
		role = getattr(user, "role", "")
		return str(getattr(role, "value", role)).lower()

	def _is_admin(user) -> bool:
		return _role_value(user) == "admin"

	def _require_auth(request: Request):
		"""Return the authenticated user or raise 401."""
		user = request.state.user
		if not user:
			raise HTTPException(401, "Not authenticated")
		return user

	def _require_admin(request: Request):
		"""Return the authenticated admin user or raise 403."""
		user = _require_auth(request)
		if not _is_admin(user):
			raise HTTPException(403, "Admin access required")
		return user

	async def _build_health_payload() -> dict[str, Any]:
		payload = {
			"status": "ready",
			"backend": _platform_backend_name,
			"platform_config": os.path.basename(_platform_config_path),
			"components": _platform_stack.describe() if hasattr(_platform_stack, "describe") else {},
			"startup_checks": getattr(app.state, "platform_startup_status", {}) or {},
		}
		try:
			auth_status = await _platform.auth_status()
		except Exception as exc:
			auth_status = {
				"enabled": False,
				"provider": "unavailable",
				"has_users": False,
				"detail": str(exc),
			}
			payload["status"] = "degraded"
		payload["auth"] = auth_status
		return payload

	def _sanitize_url_value(value: Any) -> Any:
		if not isinstance(value, str) or "://" not in value:
			return value
		try:
			parts = urlsplit(value)
		except Exception:
			return value
		if not parts.netloc or "@" not in parts.netloc:
			return value
		userinfo, hostinfo = parts.netloc.rsplit("@", 1)
		if ":" in userinfo:
			username, _password = userinfo.split(":", 1)
			safe_userinfo = f"{username}:***REDACTED***"
		else:
			safe_userinfo = userinfo
		return urlunsplit((parts.scheme, f"{safe_userinfo}@{hostinfo}", parts.path, parts.query, parts.fragment))

	def _sanitize_config_value(value: Any, key_hint: str = "") -> Any:
		lower_key = key_hint.lower()
		if isinstance(value, dict):
			return {key: _sanitize_config_value(item, str(key)) for key, item in value.items()}
		if isinstance(value, list):
			return [_sanitize_config_value(item, key_hint) for item in value]
		if isinstance(value, str):
			if any(token in lower_key for token in ("password", "token", "secret", "api_key", "apikey")):
				return "***REDACTED***" if value else value
			if lower_key == "url":
				return _sanitize_url_value(value)
		return value

	def _runtime_path_entries() -> list[dict[str, Any]]:
		path_map = {
			"data_root": _runtime_settings.data_root,
			"workspace_storage_dir": _runtime_settings.workspace_storage_dir,
			"memory_storage_dir": _runtime_settings.memory_storage_dir,
			"user_memory_dir": _runtime_settings.user_memory_dir,
			"gallery_dir": _runtime_settings.gallery_dir,
			"user_skills_dir": _runtime_settings.user_skills_dir,
			"process_credentials_path": _runtime_settings.process_credentials_path,
			"channel_users_path": _runtime_settings.channel_users_path,
			"channels_config_path": _runtime_settings.channels_config_path,
			"agent_tasks_path": _runtime_settings.agent_tasks_path,
			"published_apps_path": _runtime_settings.published_apps_path,
			"skills_state_path": _runtime_settings.skills_state_path,
		}
		entries = []
		for name, path in path_map.items():
			path_obj = Path(path)
			entries.append({
				"name": name,
				"path": str(path_obj),
				"exists": path_obj.exists(),
				"is_dir": path_obj.is_dir(),
				"is_file": path_obj.is_file(),
			})
		return entries

	def _runtime_disk_usage() -> dict[str, Any]:
		try:
			usage = shutil.disk_usage(_runtime_settings.data_root)
		except Exception as exc:
			return {"ok": False, "detail": str(exc)}
		return {
			"ok": True,
			"total_bytes": usage.total,
			"used_bytes": usage.used,
			"free_bytes": usage.free,
		}

	def _summarize_execution_outputs(outputs: Any) -> list[str]:
		if isinstance(outputs, dict):
			return sorted(str(key) for key in outputs.keys())
		if isinstance(outputs, list):
			return [f"[{idx}]" for idx, _ in enumerate(outputs[:20])]
		return []

	def _execution_record_value(record: Any, key: str, default: Any = None) -> Any:
		if isinstance(record, dict):
			return record.get(key, default)
		return getattr(record, key, default)

	def _execution_display_name(record: Any) -> str:
		metadata = _execution_record_value(record, "metadata", {}) or {}
		if isinstance(metadata, dict):
			for candidate in (
				metadata.get("workflow_name"),
				metadata.get("display_name"),
			):
				value = str(candidate or "").strip()
				if value:
					return value
		outputs = _execution_record_value(record, "outputs", {}) or {}
		if isinstance(outputs, dict):
			execution_block = outputs.get("execution")
			if isinstance(execution_block, dict):
				value = str(execution_block.get("workflow_name", "") or "").strip()
				if value:
					return value
			workflow_block = outputs.get("workflow")
			if isinstance(workflow_block, dict):
				value = str(workflow_block.get("name", "") or "").strip()
				if value:
					return value
		asset_path = str(_execution_record_value(record, "asset_path", "") or "").strip()
		return asset_path or str(_execution_record_value(record, "execution_id", "") or "").strip() or "Execution"

	def _execution_duration_ms(record: Any) -> Optional[int]:
		started_at = _execution_record_value(record, "started_at")
		finished_at = _execution_record_value(record, "finished_at")
		try:
			start = float(started_at)
		except Exception:
			return None
		if start <= 0:
			return None
		try:
			end = float(finished_at if finished_at is not None else time.time())
		except Exception:
			end = time.time()
		return max(0, int(round((end - start) * 1000)))

	def _coerce_execution_state_filter(value: Any) -> Optional[ExecutionState]:
		raw = str(value or "").strip().casefold()
		if not raw or raw == "all":
			return None
		for state in ExecutionState:
			if str(state.value).casefold() == raw:
				return state
		return None

	def _serialize_admin_execution_summary(record: Any, *, source: str = "platform") -> dict[str, Any]:
		status_obj = _execution_record_value(record, "status", "unknown")
		status_value = getattr(status_obj, "value", str(status_obj))
		outputs = _execution_record_value(record, "outputs", {}) or {}
		return {
			"source": source,
			"execution_id": str(_execution_record_value(record, "execution_id", "") or ""),
			"display_name": _execution_display_name(record),
			"workflow_name": _execution_display_name(record),
			"user_id": str(_execution_record_value(record, "user_id", "") or ""),
			"space_id": str(_execution_record_value(record, "space_id", "") or ""),
			"asset_path": str(_execution_record_value(record, "asset_path", "") or ""),
			"ref": str(_execution_record_value(record, "ref", "") or ""),
			"status": status_value,
			"runtime_profile_id": str(_execution_record_value(record, "runtime_profile_id", "") or ""),
			"timestamp": _execution_record_value(record, "started_at") or _execution_record_value(record, "timestamp") or "",
			"started_at": _execution_record_value(record, "started_at") or 0,
			"finished_at": _execution_record_value(record, "finished_at"),
			"duration_ms": _execution_duration_ms(record),
			"error": _execution_record_value(record, "error"),
			"output_keys": _summarize_execution_outputs(outputs),
		}

	def _serialize_admin_execution_detail(record: Any, *, source: str = "platform") -> dict[str, Any]:
		summary = _serialize_admin_execution_summary(record, source=source)
		metadata = dict(_execution_record_value(record, "metadata", {}) or {})
		graph = metadata.pop("workflow_graph", None)
		outputs = _execution_record_value(record, "outputs", {}) or {}
		summary.update(
			{
				"metadata": _sanitize_config_value(metadata),
				"outputs": outputs,
				"graph": graph if isinstance(graph, dict) else None,
			}
		)
		return summary

	async def _list_active_platform_execution_ids(limit: int = 1000) -> list[str]:
		runtime = getattr(_platform_stack, "runtime", None)
		if runtime is None:
			return []
		active_records = []
		for status in (ExecutionState.RUNNING, ExecutionState.PENDING):
			try:
				active_records.extend(await runtime.list_executions(status=status, limit=limit))
			except Exception:
				return []
		seen = set()
		ids = []
		for record in active_records:
			execution_id = str(getattr(record, "execution_id", "") or "").strip()
			if not execution_id or execution_id in seen:
				continue
			seen.add(execution_id)
			ids.append(execution_id)
		return ids

	async def _list_admin_execution_summaries(
		*,
		workflow_name: Optional[str] = None,
		status: Optional[str] = None,
		limit: int = 100,
		offset: int = 0,
	) -> dict[str, Any]:
		runtime = getattr(_platform_stack, "runtime", None)
		filter_text = str(workflow_name or "").strip().casefold()
		status_filter = _coerce_execution_state_filter(status)
		status_filter_text = str(status or "").strip().casefold()
		if runtime is not None:
			try:
				fetch_limit = max(50, int(limit or 100) + int(offset or 0))
				if filter_text:
					fetch_limit = max(fetch_limit, 300)
				records = await runtime.list_executions(
					status=status_filter,
					limit=fetch_limit,
				)
				items = [_serialize_admin_execution_summary(record) for record in records]
				if filter_text:
					items = [
						item
						for item in items
						if filter_text in json.dumps(
							{
								"display_name": item.get("display_name"),
								"asset_path": item.get("asset_path"),
								"user_id": item.get("user_id"),
								"space_id": item.get("space_id"),
								"execution_id": item.get("execution_id"),
							},
							ensure_ascii=False,
						).casefold()
					]
				active_exec_ids = await _list_active_platform_execution_ids()
				if items or (not filter_text and not status_filter_text):
					return {
						"executions": items[offset : offset + limit],
						"active_execution_ids": active_exec_ids,
						"source": "platform",
					}
			except Exception:
				pass
		return {
			"executions": [],
			"active_execution_ids": [],
			"source": "platform",
		}

	async def _get_admin_execution_detail(execution_id: str) -> Optional[dict[str, Any]]:
		runtime = getattr(_platform_stack, "runtime", None)
		if runtime is not None:
			try:
				record = await runtime.get_execution(execution_id)
				if record is not None:
					return _serialize_admin_execution_detail(record, source="platform")
			except Exception:
				pass
		return None

	async def _recent_execution_diagnostics(
		*,
		limit: int = 5,
	) -> dict[str, Any]:
		runtime = getattr(_platform_stack, "runtime", None)
		if runtime is None:
			return {
				"available": False,
				"detail": "Platform runtime is not exposed on the active stack.",
				"recent": [],
				"active_count": 0,
			}
		try:
			records = await runtime.list_executions(limit=max(1, int(limit or 5)))
		except Exception as exc:
			return {
				"available": False,
				"detail": str(exc),
				"recent": [],
				"active_count": 0,
			}

		try:
			running_records = await runtime.list_executions(
				status=ExecutionState.RUNNING,
				limit=1000,
			)
			pending_records = await runtime.list_executions(
				status=ExecutionState.PENDING,
				limit=1000,
			)
			active_count = len(running_records) + len(pending_records)
		except Exception:
			active_count = 0

		recent = []
		for record in records:
			status_value = getattr(getattr(record, "status", None), "value", getattr(record, "status", "unknown"))
			recent.append({
				"execution_id": record.execution_id,
				"user_id": record.user_id,
				"space_id": record.space_id,
				"asset_path": record.asset_path,
				"ref": record.ref,
				"status": status_value,
				"runtime_profile_id": record.runtime_profile_id,
				"started_at": record.started_at,
				"finished_at": record.finished_at,
				"error": record.error,
				"output_keys": _summarize_execution_outputs(record.outputs),
				"metadata": _sanitize_config_value(
					{
						key: value
						for key, value in dict(record.metadata or {}).items()
						if key != "workflow_graph"
					}
				),
			})
		return {
			"available": True,
			"active_count": active_count,
			"recent": recent,
		}

	async def _build_admin_diagnostics_payload() -> dict[str, Any]:
		health = await _build_health_payload()
		backend_section = {}
		if isinstance(_platform_config, dict):
			backend_section = _platform_config.get(_platform_backend_name, {}) or {}
		execution_diagnostics = await _recent_execution_diagnostics()
		return {
			"status": health.get("status", "unknown"),
			"backend": _platform_backend_name,
			"platform_config_path": str(_platform_config_path),
			"process": {
				"pid": os.getpid(),
				"cwd": os.getcwd(),
				"python": sys.version.split()[0],
				"uptime_seconds": round(max(0.0, time.time() - _server_started_at), 3),
			},
			"platform": {
				"components": health.get("components", {}),
				"startup_checks": health.get("startup_checks", {}),
				"auth": health.get("auth", {}),
			},
			"runtime": {
				"paths": _runtime_path_entries(),
				"disk_usage": _runtime_disk_usage(),
			},
			"executions": execution_diagnostics,
			"backend_config": _sanitize_config_value(backend_section),
		}

	@app.get("/health/live")
	@app.post("/health/live")
	async def health_live():
		return {
			"status": "alive",
			"backend": _platform_backend_name,
			"uptime_seconds": round(max(0.0, time.time() - _server_started_at), 3),
		}

	@app.get("/health/ready")
	@app.post("/health/ready")
	async def health_ready():
		try:
			payload = await _build_health_payload()
			required_paths = [
				_runtime_settings.workspace_storage_dir,
				_runtime_settings.memory_storage_dir,
				_runtime_settings.user_memory_dir,
				_runtime_settings.gallery_dir,
				_runtime_settings.user_skills_dir,
			]
			missing = [str(path) for path in required_paths if not Path(path).exists()]
			if missing:
				payload["status"] = "degraded"
				payload["missing_paths"] = missing
				return JSONResponse(status_code=503, content=payload)
			if payload.get("status") != "ready":
				return JSONResponse(status_code=503, content=payload)
			return payload
		except Exception as exc:
			return JSONResponse(
				status_code=503,
				content={
					"status": "degraded",
					"backend": _platform_backend_name,
					"detail": str(exc),
				},
			)

	# ── Admin API Routes ─────────────────────────────────────

	@app.post("/admin/users")
	async def admin_list_users(request: Request):
		_require_admin(request)
		body = {}
		try: body = await request.json()
		except Exception: pass
		try:
			return await _platform.list_user_rows(
				offset=body.get("offset", 0),
				limit=body.get("limit", 50),
				active_only=body.get("active_only", True),
			)
		except PlatformRequestError as exc:
			_platform_http_error(exc)

	@app.post("/admin/users/{user_id}")
	async def admin_get_user(user_id: str, request: Request):
		_require_admin(request)
		try:
			return await _platform.post_json(f"/platform/users/{user_id}", {})
		except PlatformRequestError as exc:
			_platform_http_error(exc)

	@app.post("/admin/users/{user_id}/update")
	async def admin_update_user(user_id: str, request: Request):
		_require_admin(request)
		body = await request.json()
		allowed = {k: v for k, v in body.items() if k in ("email", "role", "active", "metadata")}
		if not allowed:
			raise HTTPException(400, "No valid fields to update")
		try:
			user = await _platform.update_user(user_id, **allowed)
			return {"user": {"id": user.id, "username": user.username, "email": user.email,
							 "role": user.role.value, "active": user.active}}
		except PlatformRequestError as exc:
			_platform_http_error(exc)

	@app.post("/admin/users/{user_id}/delete")
	async def admin_delete_user(user_id: str, request: Request):
		_require_admin(request)
		try:
			ok = await _platform.delete_user(user_id)
		except PlatformRequestError as exc:
			_platform_http_error(exc)
		if not ok:
			raise HTTPException(404, "User not found")
		return {"ok": True}

	@app.post("/admin/users/{user_id}/quota")
	async def admin_update_quota(user_id: str, request: Request):
		_require_admin(request)
		body = await request.json()
		try:
			quota = await _platform.update_quota(user_id, **body)
		except PlatformRequestError as exc:
			_platform_http_error(exc)
		return {
			"quota": {
				"user_id":                 quota.user_id,
				"cpu_seconds_remaining":   quota.cpu_seconds_remaining,
				"max_concurrent_runs":     quota.max_concurrent_runs,
				"storage_bytes_remaining": quota.storage_bytes_remaining,
				"max_loop_hours":          quota.max_loop_hours,
				"gpu_hours_remaining":     quota.gpu_hours_remaining,
				"max_spaces":              quota.max_spaces,
				"max_assets_per_space":    quota.max_assets_per_space,
			}
		}

	@app.post("/admin/users/{user_id}/permissions")
	async def admin_list_user_permissions(user_id: str, request: Request):
		raise HTTPException(410, "Legacy generic user permissions were removed; use space policies instead")

	@app.post("/admin/users/{user_id}/permissions/grant")
	async def admin_grant_permission(user_id: str, request: Request):
		raise HTTPException(410, "Legacy generic user permissions were removed; use space policies instead")

	@app.post("/admin/users/{user_id}/permissions/revoke")
	async def admin_revoke_permission(user_id: str, request: Request):
		raise HTTPException(410, "Legacy generic user permissions were removed; use space policies instead")

	@app.post("/admin/stats")
	async def admin_stats(request: Request):
		"""System-wide statistics: users, executions, active runs."""
		_require_admin(request)
		users = await _platform.list_users(limit=10000, active_only=False)
		active_users  = [u for u in users if u.active]
		runtime = getattr(_platform_stack, "runtime", None)
		records = []
		active_exec_ids = []
		try:
			if runtime is not None:
				records = await runtime.list_executions(limit=10000)
				active_exec_ids = await _list_active_platform_execution_ids()
		except Exception:
			pass
		status_counts = {}
		for record in records:
			s = str(getattr(record, "status", "unknown") or "unknown")
			status_counts[s] = status_counts.get(s, 0) + 1
		return {
			"total_users":       len(users),
			"active_users":      len(active_users),
			"total_executions":  len(records),
			"active_executions": len(active_exec_ids),
			"execution_status_breakdown": status_counts,
		}

	@app.post("/admin/diagnostics")
	async def admin_diagnostics(request: Request):
		"""Operational diagnostics for the active app/runtime/platform stack."""
		_require_admin(request)
		return await _build_admin_diagnostics_payload()

	@app.post("/admin/executions")
	async def admin_executions(request: Request):
		"""Paginated execution history for admin."""
		_require_admin(request)
		body = {}
		try: body = await request.json()
		except Exception: pass
		wf_name = body.get("workflow_name")
		status  = body.get("status")
		limit   = int(body.get("limit", 100) or 100)
		offset  = int(body.get("offset", 0) or 0)
		return await _list_admin_execution_summaries(
			workflow_name=wf_name,
			status=status,
			limit=limit,
			offset=offset,
		)

	@app.post("/admin/executions/{execution_id}")
	async def admin_execution_detail(execution_id: str, request: Request):
		_require_admin(request)
		detail = await _get_admin_execution_detail(execution_id)
		if detail is None:
			raise HTTPException(status_code=404, detail=f"Execution '{execution_id}' was not found")
		return {"execution": detail}

	@app.post("/admin/executions/{execution_id}/cancel")
	async def admin_cancel_execution(execution_id: str, request: Request):
		_require_admin(request)
		runtime = getattr(_platform_stack, "runtime", None)
		if runtime is not None:
			record = await runtime.get_execution(execution_id)
			if record is not None:
				ok = await runtime.cancel_execution(execution_id)
				return {"ok": bool(ok)}
		try:
			ws_obj = workspace_mgr.get_default_workspace()
			state  = await ws_obj.engine.cancel_execution(execution_id)
			return {"ok": True, "state": state}
		except KeyError:
			raise HTTPException(status_code=404, detail=f"Execution '{execution_id}' was not found")
		except Exception as e:
			raise HTTPException(500, str(e))

	# Serve the frontend from /web — must be mounted AFTER api routes are registered
	_web_dir = str(_runtime_settings.web_dir)

	host   = "0.0.0.0"
	port   = args.port
	config = uvicorn.Config(app, host=host, port=port)
	server = uvicorn.Server(config)
	app.state.uvicorn_server = server

	# ── Backend Memory Identity ───────────────────────────────
	user_memory_db = UserMemoryDB(storage_dir=str(_runtime_settings.user_memory_dir))

	# ── Console Agent ─────────────────────────────────────────
	_main_base_url = f"http://localhost:{args.port}"
	console_mgr = ConsoleAgentManager(workspace_mgr, event_bus, port=args.port + 1,
									  user_memory_db=user_memory_db,
									  base_url=_main_base_url,
									  internal_token=_platform_internal_token)
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
	_cfg_path = str(_runtime_settings.console_agent_config_path)
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
		auth_provider=_platform,
		store_path=str(_runtime_settings.channel_users_path),
		available_toolkits=_available_toolkits,
		default_toolkits=_default_toolkits,
		planner_callback=_planner_callback,
	)

	# Read pool config from console_agent.json
	_pool_cfg = _creds.load_json(_cfg_path).get("channel_pool", {})
	channel_pool = ChannelAgentPool(
		workspace_mgr=workspace_mgr,
		user_memory_db=user_memory_db,
		idle_timeout=_pool_cfg.get("idle_timeout", 1800),
		base_url=_main_base_url,
		internal_token=_platform_internal_token,
		fastapi_app=app)

	async def _dispatch_to_channel_sources(msg):
		"""Push incoming message to any registered ChannelSource event sources."""
		try:
			from events import get_event_registry
			from events.sources import ChannelSource
			registry = get_event_registry()
			for source in registry._sources.values():
				if isinstance(source, ChannelSource) and source.is_running:
					await source.receive_message(
						channel_id=msg.channel_id, channel_type=msg.channel_type,
						sender_id=msg.sender_id, sender_name=msg.sender_name,
						content=msg.content, metadata=msg.metadata,
						attachments=msg.attachments if msg.attachments else None)
		except Exception:
			pass  # best-effort; don't break the message pipeline

	async def channel_message_handler(msg):
		"""Route incoming channel messages to per-user agents."""
		try:
			# Push to any workflow channel_receive_flow sources (best-effort)
			await _dispatch_to_channel_sources(msg)

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

			primary_deployment = None
			deployment = None
			handoff = None
			external_session_id = str(msg.metadata.get("session_id") or "").strip() or None
			if assistant_deployment_mgr:
				primary_deployment, deployment, handoff = await assistant_deployment_mgr.resolve_for_message(
					msg.channel_id,
					msg.content,
					sender_id=msg.sender_id,
					session_id=external_session_id,
				)
			base_session_id = external_session_id or f"channel_{msg.channel_id}_{msg.sender_id}"
			if deployment is not None:
				session_id = f"deploy_{deployment.id}_{base_session_id}"
			else:
				session_id = f"ch_{base_session_id}"
			# Resolve per-user identity and toolkits
			numel_user_id = channel_cmd.get_linked_user_id(msg.channel_type, msg.sender_id)
			toolkits = channel_cmd.get_enabled_toolkits(msg.channel_type, msg.sender_id)
			deployment_toolkits = list(deployment.toolkit_names) if deployment and deployment.toolkit_names else None
			deployment_skills = list(deployment.skill_names) if deployment and deployment.skill_names else None
			handoff_source_id = str((handoff or {}).get("source_deployment_id") or "").strip() or None
			is_new_handoff = bool(
				handoff
				and str((handoff or {}).get("event") or "") == "handoff"
				and deployment is not None
				and handoff_source_id
				and handoff_source_id != deployment.id
			)
			extra_instructions = []
			if deployment and deployment.instructions.strip():
				extra_instructions.append(
					f"[Assistant Deployment]\nDeployment: {deployment.name}\nProfile: {deployment.profile}\n{deployment.instructions.strip()}"
				)
			if handoff and deployment and handoff_source_id and handoff_source_id != deployment.id:
				source_name = str((handoff or {}).get("source_name") or (primary_deployment.name if primary_deployment else handoff_source_id))
				handoff_title = "Conversation handoff" if is_new_handoff else "Active conversation owner"
				extra_instructions.append(
					f"[Assistant Handoff]\n{handoff_title}: {source_name} -> {deployment.name}\nReason: {handoff.get('reason', 'handoff active')}"
				)
			if not extra_instructions:
				extra_instructions = None
			sender   = channel_cmd.get_linked_username(msg.channel_type, msg.sender_id) \
				or msg.sender_name or msg.sender_id
			mem_user_id = numel_user_id or f"anon_{msg.channel_type}_{msg.sender_id}"
			result = await channel_pool.chat(
				msg.content, session_id,
				toolkits=deployment_toolkits if deployment_toolkits is not None else (toolkits or None),
				sender_name=sender,
				user_id=mem_user_id,
				attachments=msg.attachments if msg.attachments else None,
				model_source=deployment.model_source if deployment else None,
				model_name=deployment.model_name if deployment else None,
				skill_names=deployment_skills,
				deployment_id=deployment.id if deployment else None,
				tool_confirmation_mode=deployment.safety.tool_execution_mode if deployment else None,
				assistant_name=deployment.name if deployment else None,
				assistant_description=deployment.description if deployment else None,
				extra_instructions=extra_instructions,
			)
			if result.get("pending_tool_approval"):
				if assistant_deployment_mgr and deployment:
					assistant_deployment_mgr.record_tool_approval_request(
						deployment.id,
						channel_id=msg.channel_id,
						sender_id=msg.sender_id,
						approval=dict(result.get("pending_tool_approval") or {}),
						preview=str(result.get("response", "") or ""),
						routed_from=handoff_source_id if is_new_handoff else None,
						handoff=handoff,
					)
				return result.get("response", "") or "Approval requested before running a tool."
			if result.get("error"):
				if assistant_deployment_mgr and deployment:
					assistant_deployment_mgr.record_message(
						deployment.id,
						channel_id=msg.channel_id,
						sender_id=msg.sender_id,
						status="error",
						preview=str(result.get("error", "")),
						routed_from=handoff_source_id if is_new_handoff else None,
						handoff=handoff,
					)
				return f"⚠ {result['error']}"
			if assistant_deployment_mgr and deployment:
				assistant_deployment_mgr.record_message(
					deployment.id,
					channel_id=msg.channel_id,
					sender_id=msg.sender_id,
					status="ok",
					preview=str(result.get("response", "") or ""),
					routed_from=handoff_source_id if is_new_handoff else None,
					handoff=handoff,
				)
			return result.get("response", "") or "(no response from agent)"
		except Exception as e:
			log_print(f"Channel message handler error: {e}")
			return f"⚠ Something went wrong: {e}"

	channel_registry = ChannelRegistry(message_handler=channel_message_handler,
									   config_path=str(_runtime_settings.channels_config_path))
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
	assistant_deployment_mgr = AssistantDeploymentManager(
		config_path=str(_runtime_settings.assistant_deployments_path)
	)
	assistant_deployment_mgr.initialize(
		channel_registry=channel_registry,
		channel_pool=channel_pool,
		event_bus=event_bus,
	)
	# Make shared runtime services available to workspace engines and agent pool
	workspace_mgr.set_runtime_services(
		channel_registry=channel_registry,
		assistant_deployment_mgr=assistant_deployment_mgr,
		channel_pool=channel_pool,
	)
	channel_pool._channel_reg = channel_registry

	# ── Skills ────────────────────────────────────────────────
	skill_mgr = SkillManager(
		skills_dir=str(_runtime_settings.user_skills_dir),
		builtin_dirs=[str(_runtime_settings.builtin_skills_dir)],
		state_path=str(_runtime_settings.skills_state_path),
	)
	skill_mgr.initialize()

	# ── Workflow Gallery ──────────────────────────────────────
	gallery_mgr = GalleryManager(
		gallery_dir=str(_runtime_settings.gallery_dir),
		seed_dirs=[str(_runtime_settings.builtin_gallery_dir), str(_runtime_settings.examples_dir)],
	)
	gallery_mgr.initialize()
	app.state.gallery_manager = gallery_mgr

	# ── Autonomous Agent Tasks ────────────────────────────────
	task_mgr = AgentTaskManager(console_mgr, config_path=str(_runtime_settings.agent_tasks_path))
	task_mgr.initialize(event_bus)

	# ── Published Apps ────────────────────────────────────────
	pub_app_mgr = PublishedAppManager(
		workspace_mgr,
		config_path=str(_runtime_settings.published_apps_path),
		assets_root=str(_runtime_settings.published_apps_dir),
		backend_name=schema.DEFAULT_BACKEND_NAME,
	)
	pub_app_mgr.initialize()

	# Wire pool, channel registry, and skills into console manager
	console_mgr.set_channel_pool(channel_pool)
	console_mgr._channel_reg = channel_registry
	console_mgr.set_skill_mgr(skill_mgr)
	channel_pool.set_skill_mgr(skill_mgr)
	assistant_deployment_mgr.set_skill_mgr(skill_mgr)
	# Propagate skill_mgr to workspace manager and all existing workflow managers
	workspace_mgr._skill_mgr = skill_mgr
	for ws in workspace_mgr._workspaces.values():
		ws.manager._skill_mgr = skill_mgr

	# ── Proactive per-request state-dir override ─────────────────────────
	# When an `X-Proactive-Dir` header is present on a /proactive/* request,
	# scope the request to that state directory. The override is wired via
	# proactive.persistence.set_state_dir_override (contextvar) so concurrent
	# requests each see their own state without process-global mutation.

	@app.middleware("http")
	async def proactive_state_dir_middleware(request: Request, call_next):
		hdr = (request.headers.get("x-proactive-dir") or "").strip()
		if not hdr or not request.url.path.startswith("/proactive/"):
			return await call_next(request)
		from proactive.persistence import set_state_dir_override, reset_state_dir_override
		token = set_state_dir_override(hdr)
		try:
			return await call_next(request)
		finally:
			reset_state_dir_override(token)

	# ── API Routes (order matters: specific routes before static mount) ──
	setup_api(app, event_bus, schema_code, workspace_mgr, skill_mgr=skill_mgr, assistant_deployment_mgr=assistant_deployment_mgr)
	setup_console_api(app, console_mgr, channel_pool=channel_pool, channel_cmd=channel_cmd)
	setup_channel_api(app, channel_registry, pool=channel_pool)
	setup_assistant_deployments_api(app, assistant_deployment_mgr, channel_registry=channel_registry)
	setup_gallery_api(app, gallery_mgr)
	setup_skills_api(app, skill_mgr)
	setup_agent_tasks_api(app, task_mgr)
	setup_published_apps_api(app, pub_app_mgr, gallery_mgr=gallery_mgr)

	# ── Credential Store ───────────────────────────────────────

	@app.post("/credentials")
	async def list_credentials(request: Request):
		user = _require_auth(request)
		body = {}
		try:
			body = await request.json()
		except Exception:
			pass
		space_id = (body.get("space_id") or "").strip() or None
		try:
			records = await _platform.list_credentials(user.id, space_id=space_id)
			return {"names": [record.name for record in records]}
		except PlatformRequestError as exc:
			_platform_http_error(exc)

	@app.post("/credentials/{name}")
	async def set_credential(name: str, request: Request):
		user = _require_auth(request)
		body = await request.json()
		space_id = (body.get("space_id") or "").strip() or None
		try:
			record = await _platform.set_credential(
				user.id,
				name,
				body.get("value", ""),
				space_id=space_id,
				metadata=body.get("metadata"),
			)
			return {"ok": True, "credential": {"name": record.name, "scope": record.scope.value, "space_id": record.space_id}}
		except PlatformRequestError as exc:
			_platform_http_error(exc)

	@app.delete("/credentials/{name}")
	async def delete_credential(name: str, request: Request):
		user = _require_auth(request)
		body = {}
		try:
			body = await request.json()
		except Exception:
			pass
		space_id = (body.get("space_id") or "").strip() or None
		try:
			return {"ok": await _platform.delete_credential(user.id, name, space_id=space_id)}
		except PlatformRequestError as exc:
			_platform_http_error(exc)

	# ── Webhook Tunnel ─────────────────────────────────────────

	@app.post("/tunnel/url")
	async def get_tunnel_url():
		return {"url": _tunnel_url}

	# Serve index.html at / and all static assets (JS, CSS, dist/*)
	app.mount("/", StaticFiles(directory=_web_dir, html=True), name="static")

	url = f"http://localhost:{port}/"
	log_print(f"Frontend: {url}")

	async def _start_runtime_services(
		*,
		open_browser_now: bool = open_browser,
		start_channels_now: bool = start_channels,
		start_tunnel_now: bool = bool(start_tunnel),
	):
		nonlocal _browser_opened, _channels_started, _tunnel_started
		if open_browser_now and not _browser_opened:
			webbrowser.open(url)
			_browser_opened = True
		if start_channels_now and not _channels_started:
			await channel_registry.start_all()
			if assistant_deployment_mgr is not None:
				await assistant_deployment_mgr.start_auto()
			_channels_started = True
		if start_tunnel_now and not _tunnel_started:
			t = threading.Thread(target=_start_tunnel, args=(port,), daemon=True)
			t.start()
			_tunnel_started = True

	app.state.shutdown_runtime = _shutdown_runtime
	app.state.start_runtime_services = _start_runtime_services
	app.state.frontend_url = url
	app.state.workspace_mgr = workspace_mgr
	app.state.console_mgr = console_mgr
	app.state.channel_registry = channel_registry
	app.state.task_mgr = task_mgr
	app.state.assistant_deployment_mgr = assistant_deployment_mgr
	app.state.gallery_mgr = gallery_mgr
	app.state.skill_mgr = skill_mgr
	app.state.published_app_mgr = pub_app_mgr
	app.state.event_bus = event_bus

	if not serve:
		return app

	try:
		await _start_runtime_services()
		await server.serve()
	finally:
		await _shutdown_runtime()

	return app


async def build_app(args: Any) -> FastAPI:
	return await run_server(
		args,
		serve=False,
		open_browser=False,
		start_channels=False,
		start_tunnel=False,
	)


def main():
	parser = argparse.ArgumentParser(description="Numel Playground App")
	parser .add_argument("--port",   type=int,  default=DEFAULT_APP_PORT, help="Listening port for control server"     )
	parser .add_argument("--seed",   type=int,  default=DEFAULT_APP_SEED, help="Seed for pseudorandom number generator")
	parser .add_argument("--tunnel", action="store_true",                 help="Start a cloudflared/ngrok tunnel for public webhook access")
	parser .add_argument("--open-browser", action="store_false",          help="Open the frontend in the default browser after startup")
	parser .add_argument("--proactive-dir",                                help="Override the proactive state directory for this run (default: app/storage/proactive/). All ledger / world-model / capabilities / feedback / config / prompts state lands under the given path. Equivalent to setting NUMEL_PROACTIVE_DIR.")
	args   = parser.parse_args()

	# Per-run proactive state location. The proactive package reads
	# NUMEL_PROACTIVE_DIR on every state_dir() call, so setting it
	# process-wide here makes it stick for the whole run without
	# touching any module-level constant.
	if getattr(args, "proactive_dir", None):
		os.environ["NUMEL_PROACTIVE_DIR"] = str(args.proactive_dir)
		log_print(f"Proactive state directory: {args.proactive_dir}")

	asyncio.run(run_server(args, open_browser=bool(getattr(args, "open_browser", False))))


if __name__ == "__main__":
	main()
