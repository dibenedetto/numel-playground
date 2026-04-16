# console — Console Agent Manager
# Self-contained module: agent lifecycle, API routes, chat, proactive behavior.

import asyncio
import httpx
import importlib
import json
import os
import time
import uuid

from   datetime                        import datetime
from   fastapi                         import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from   pydantic                        import BaseModel
from   typing                          import Any, Dict, List, Optional, Set

from   workflow_validation             import validate_workflow_payload

from   event_bus                       import EventBus
from   backend_factory                 import (
	build_backend_skills,
	build_backend_toolkit,
	build_chat_agent,
	build_chat_runtime,
	clear_chat_memory,
	continue_chat_run,
	extract_chat_response_text,
	extract_chat_tool_calls,
	get_pending_tool_approval,
	is_chat_response_paused,
	run_chat_agent,
)
from   assistant_memory_contract       import (
	build_assistant_memory_components,
	normalize_assistant_memory_config,
	resolve_assistant_memory_db_path,
)
from   console_workflow               import build_console_workflow_export, parse_console_workflow_import
from   prompt_stack                    import PLANNER_MODE_DIRECTIVE, extend_instruction_block
from   runtime_settings                import get_runtime_settings
from   runtime_toolkit_bindings        import build_runtime_toolkit_args
from   schema                          import DEFAULT_BACKEND_NAME
from   toolkit_runtime                 import build_toolkit_record_from_instance, load_numel_toolkit
from   toolkits.console_toolkit        import ConsoleToolkit
from   utils                           import log_print
from   workflow_backed_runtime         import run_workflow_backed_agent_turn


_CONFIG_PATH = str(get_runtime_settings().console_agent_config_path)


def _describe_attachments(message: str, attachments: list) -> str:
	"""Inject a textual description of attachments into the message prompt.
	This allows the LLM to know about files even though it can't see binary content."""
	lines = []
	for att in attachments:
		url      = att.url if hasattr(att, "url") else att.get("url", "")
		mime     = att.mime_type if hasattr(att, "mime_type") else att.get("mime_type", "")
		filename = (att.filename if hasattr(att, "filename") else att.get("filename")) or None
		size     = (att.size if hasattr(att, "size") else att.get("size")) or None
		parts = []
		if filename:
			parts.append(filename)
		if mime:
			parts.append(f"type: {mime}")
		if size:
			kb = size / 1024
			parts.append(f"size: {kb:.1f} KB" if kb < 1024 else f"size: {kb/1024:.1f} MB")
		if url:
			parts.append(f"url: {url[:120]}")
		lines.append(f"  - {', '.join(parts)}")
	if lines:
		block = "[Attachments]\n" + "\n".join(lines)
		return f"{block}\n\n{message}" if message else block
	return message


def _wrap_numel_toolkit_for_backend(
	instance,
	*,
	name: Optional[str] = None,
	module_name: Optional[str] = None,
	confirm_all_tools: bool = False,
):
	record = build_toolkit_record_from_instance(instance, name=name, module_name=module_name)
	return build_backend_toolkit(
		record,
		backend_name=DEFAULT_BACKEND_NAME,
		confirm_all_tools=confirm_all_tools,
	)


def _load_native_toolkit(module_name: str, args: Optional[Dict[str, Any]] = None, *,
						 log_prefix: str = "Console toolkit",
						 confirm_all_tools: bool = False):
	record = load_numel_toolkit(module_name, args or None, log_prefix=log_prefix)
	if record is None:
		return None
	return build_backend_toolkit(
		record,
		backend_name=DEFAULT_BACKEND_NAME,
		confirm_all_tools=confirm_all_tools,
	)


def _resolve_native_skill_bundle(skill_mgr, skill_names: Optional[List[str]] = None,
								 backend_name: str = DEFAULT_BACKEND_NAME):
	"""Resolve selected or enabled skills into the active backend's native skill bundle."""
	if not skill_mgr:
		return None
	if skill_names is not None:
		skill_definitions = skill_mgr.get_definitions_for(skill_names)
	else:
		skill_definitions = skill_mgr.get_active_definitions()
	if not skill_definitions:
		return None
	return build_backend_skills(skill_definitions, backend_name=backend_name)


def _toolkit_runtime_args(
	tk_name: str,
	*,
	base_url: str,
	internal_token: str,
	user_id: Optional[str],
	auth_token: str = "",
	local_app = None,
	deployment_id: Optional[str] = None,
) -> Dict[str, Any]:
	"""Provide runtime-only constructor args for toolkits that need Numel app context."""
	return build_runtime_toolkit_args(
		tk_name,
		base_url=base_url,
		internal_token=internal_token,
		user_id=user_id,
		auth_token=auth_token,
		local_app=local_app,
		deployment_id=deployment_id,
	)

# ── Planner State (per-user) ────────────────────────────────────

class PlannerState:
	"""Per-session planner state.  One instance per (user, browser tab) pair."""

	__slots__ = (
		"key", "user_id", "enabled", "active", "session_id", "turn_count",
		"max_turns", "timeout", "session_timeout", "session_start",
		"debounce", "timer", "pending", "subs", "instructions", "profile",
		"browser_session_id", "pause_until", "suppress_added_until",
		"debounce_until", "last_event_type", "last_event_at", "last_processed_at",
		"last_pause_reason", "last_suppressed_event",
	)

	def __init__(self, key: str, user_id: Optional[str] = None, browser_session_id: Optional[str] = None):
		self.key: str               = key
		self.user_id: Optional[str] = user_id
		self.enabled: bool          = False
		self.active: bool           = False
		self.session_id: str        = f"planner-{key[:16]}-{uuid.uuid4().hex[:8]}"
		self.browser_session_id: Optional[str] = browser_session_id
		self.turn_count: int        = 0
		self.max_turns: int         = 10
		self.timeout: float         = 120.0      # per-turn timeout
		self.session_timeout: float = 600.0      # total wall-clock timeout
		self.session_start: float   = 0.0
		self.debounce: float        = 2.0        # seconds
		self.timer                  = None        # debounce handle
		self.pending: List[dict]    = []          # queued events
		self.subs: List[str]        = []          # subscribed event type strings
		self.instructions: str      = ""
		self.profile: str           = ""
		self.pause_until: float     = 0.0
		self.suppress_added_until: float = 0.0
		self.debounce_until: float  = 0.0
		self.last_event_type: str   = ""
		self.last_event_at: float   = 0.0
		self.last_processed_at: float = 0.0
		self.last_pause_reason: str = ""
		self.last_suppressed_event: str = ""

	def reset(self):
		self.turn_count = 0
		self.session_id = f"planner-{self.key[:16]}-{uuid.uuid4().hex[:8]}"
		self.pending.clear()
		self.debounce_until = 0.0
		self.last_event_type = ""
		self.last_event_at = 0.0
		self.last_processed_at = 0.0
		self.last_pause_reason = ""
		self.last_suppressed_event = ""


# ── Manager ────────────────────────────────────────────────────

class ConsoleAgentManager:
	"""Manages the global console agent: lazy start, context gathering, chat sessions, proactive suggestions."""

	def __init__(self, workspace_mgr, event_bus: EventBus, port: int,
				 config_path: str = _CONFIG_PATH,
				 user_memory_db=None,
				 base_url: str = "http://localhost:11360",
				 internal_token: str = ""):
		self._ws_mgr       = workspace_mgr
		self._event_bus     = event_bus
		self._port          = port
		self._base_url      = base_url.rstrip("/")
		self._internal_token = internal_token
		self._config_path   = config_path
		self._user_memory_db = user_memory_db       # UserMemoryDB for per-user isolation
		self._current_user_id: Optional[str] = None # set on start / chat
		self._agent_user_id: Optional[str] = None
		self._agent         = None
		self._app           = None
		self._server        = None
		self._server_task   = None
		self._started       = False
		self._model_source  = None
		self._model_name    = None
		self._toolkit_names = []      # e.g. ["console_toolkit", "file_toolkit"]
		self._toolkit_args  = {}
		self._skill_names   = None    # e.g. ["web-search", "git-assistant"]
		self._options_override = None
		self._memory_override  = None
		self._skill_mgr     = None    # set via set_skill_mgr()
		self._proactive_ws       : Dict[WebSocket, Optional[str]] = {}
		self._sessions           : Dict[str, List[dict]] = {}  # session_id → message history
		self._start_lock         = asyncio.Lock()               # prevents concurrent start/stop
		self._use_backend_memory = True                         # backend memory is the only supported mode

		# ── Planner mode (per-session) ──
		# Keyed by planner_key (typically "user_{user_id}_{session_id}" or
		# "guest_{session_id}") so the same user in two tabs gets independent planners.
		self._planners: Dict[str, PlannerState] = {}   # planner_key → PlannerState
		self._planner_lock  = asyncio.Lock()          # serializes planner turns across sessions
		self._workflow_lock = asyncio.Lock()           # exclusive workflow access during planner modifications
		self._channel_pool: Optional['ChannelAgentPool'] = None  # set later via set_channel_pool()
		self._fastapi_app   = None
		self._auth_token    = ""

	def set_channel_pool(self, pool: 'ChannelAgentPool'):
		"""Inject the channel pool so planner turns use per-user agents."""
		self._channel_pool = pool

	def set_skill_mgr(self, mgr):
		"""Inject the skill manager for resolving skill instructions."""
		self._skill_mgr = mgr

	@staticmethod
	def _planner_key(user_id: Optional[str], session_id: Optional[str]) -> str:
		"""Build a unique key for a planner instance."""
		uid = user_id or "anon"
		sid = session_id or "default"
		return f"{uid}_{sid}"

	@property
	def _planner_enabled(self) -> bool:
		"""True if ANY session has an active planner — used by route branching."""
		return any(p.enabled for p in self._planners.values())

	@property
	def _planner_instructions(self) -> str:
		"""Return instructions from the first active planner (for context injection)."""
		for ps in self._planners.values():
			if ps.enabled and ps.instructions:
				return ps.instructions
		return ""

	def _planner_for_session(self, user_id: Optional[str], session_id: Optional[str]) -> bool:
		"""Check if a specific session has planner enabled."""
		p = self._planners.get(self._planner_key(user_id, session_id))
		return p is not None and p.enabled

	def _resolve_planner_state(self, user_id: Optional[str], session_id: Optional[str]) -> Optional[PlannerState]:
		"""Resolve a planner by exact key first, then fall back to the user's sole active planner."""
		p = self._planners.get(self._planner_key(user_id, session_id))
		if p is not None:
			return p
		if user_id is None:
			return None
		candidates = [ps for ps in self._planners.values() if ps.enabled and ps.user_id == user_id]
		if len(candidates) == 1:
			return candidates[0]
		return candidates[0] if candidates else None

	@staticmethod
	def _planner_remaining(now: float, deadline: float) -> float:
		return max(0.0, float(deadline or 0.0) - now)

	def _planner_status_payload(self, ps: Optional[PlannerState]) -> Dict[str, Any]:
		now = time.time()
		if ps is None:
			return {
				"enabled": False,
				"active": False,
				"turn_count": 0,
				"max_turns": 10,
				"session_id": None,
				"subscribed_events": [],
				"browser_session_id": None,
				"pending_events": [],
				"pending_event_count": 0,
				"pending_event_types": [],
				"pause_remaining_s": 0.0,
				"suppress_added_remaining_s": 0.0,
				"debounce_remaining_s": 0.0,
				"last_event_type": None,
				"last_event_at": None,
				"last_processed_at": None,
				"last_pause_reason": "",
				"last_suppressed_event": "",
			}
		pending_rows = list(ps.pending or [])
		return {
			"enabled": ps.enabled,
			"active": ps.active,
			"turn_count": ps.turn_count,
			"max_turns": ps.max_turns,
			"session_id": ps.session_id,
			"browser_session_id": ps.browser_session_id,
			"subscribed_events": list(ps.subs),
			"pending_events": [
				{
					"type": str(row.get("type", "") or ""),
					"count": int(row.get("count", 1) or 1),
				}
				for row in pending_rows
			],
			"pending_event_count": sum(int(row.get("count", 1) or 1) for row in pending_rows),
			"pending_event_types": [str(row.get("type", "") or "") for row in pending_rows],
			"pause_remaining_s": round(self._planner_remaining(now, ps.pause_until), 3),
			"suppress_added_remaining_s": round(self._planner_remaining(now, ps.suppress_added_until), 3),
			"debounce_remaining_s": round(self._planner_remaining(now, ps.debounce_until), 3),
			"last_event_type": ps.last_event_type or None,
			"last_event_at": datetime.fromtimestamp(ps.last_event_at).isoformat() if ps.last_event_at else None,
			"last_processed_at": datetime.fromtimestamp(ps.last_processed_at).isoformat() if ps.last_processed_at else None,
			"last_pause_reason": ps.last_pause_reason,
			"last_suppressed_event": ps.last_suppressed_event,
		}

	def _planner_export_state(self, ps: Optional[PlannerState]) -> Optional[Dict[str, Any]]:
		"""Return the minimal active planner state needed for workbench export."""
		if ps is None or not ps.enabled:
			return None
		return {
			"enabled": True,
			"profile": ps.profile,
			"instructions": ps.instructions,
			"subscribe_events": list(ps.subs or []),
			"timeout_s": ps.timeout,
			"session_timeout_s": ps.session_timeout,
			"max_iterations": ps.max_turns,
			"debounce_s": ps.debounce,
			"browser_session_id": ps.browser_session_id,
			"planner_session_id": ps.session_id,
		}

	def _queue_planner_event(self, ps: PlannerState, evt_type: str, evt_data: Dict[str, Any]) -> None:
		now = time.time()
		ps.last_event_type = evt_type
		ps.last_event_at = now
		for existing in ps.pending:
			if str(existing.get("type", "") or "") != evt_type:
				continue
			existing["data"] = dict(evt_data)
			existing["count"] = int(existing.get("count", 1) or 1) + 1
			existing["last_received_at"] = now
			return
		ps.pending.append({
			"type": evt_type,
			"data": dict(evt_data),
			"count": 1,
			"last_received_at": now,
		})

	def _schedule_planner_processing(self, ps: PlannerState, *, delay: Optional[float] = None) -> None:
		if not ps.enabled:
			return
		if ps.timer:
			ps.timer.cancel()
			ps.timer = None
		actual_delay = max(0.0, ps.debounce if delay is None else float(delay))
		ps.debounce_until = time.time() + actual_delay if actual_delay > 0 else 0.0
		loop = asyncio.get_event_loop()
		pkey = ps.key
		ps.timer = loop.call_later(
			actual_delay,
			lambda k=pkey: asyncio.ensure_future(self._process_planner_events(k))
		)

	def _request_headers(self, user_id: Optional[str] = None) -> Dict[str, str]:
		headers: Dict[str, str] = {}
		acting_user_id = user_id or self._current_user_id
		if self._auth_token and (acting_user_id is None or acting_user_id == self._current_user_id):
			headers["Authorization"] = f"Bearer {self._auth_token}"
		elif self._internal_token and acting_user_id:
			headers["x-numel-platform-internal"] = self._internal_token
			headers["x-numel-acting-user"] = acting_user_id
		return headers

	async def _post_json(self, path: str, body: Optional[Dict[str, Any]] = None,
						 user_id: Optional[str] = None) -> Dict[str, Any]:
		headers = self._request_headers(user_id=user_id)
		if self._fastapi_app is not None:
			async with httpx.AsyncClient(
				transport=httpx.ASGITransport(app=self._fastapi_app),
				base_url=self._base_url,
				timeout=30.0,
			) as client:
				resp = await client.post(path, json=body or {}, headers=headers)
		else:
			async with httpx.AsyncClient(base_url=self._base_url, timeout=30.0) as client:
				resp = await client.post(path, json=body or {}, headers=headers)
		resp.raise_for_status()
		data = resp.json()
		return data if isinstance(data, dict) else {}

	# ── Lifecycle ──────────────────────────────────────────────────

	async def start(self, model_source: Optional[str] = None,
					model_name: Optional[str] = None,
					toolkit_names: Optional[List[str]] = None,
					use_backend_memory: Optional[bool] = None,
					toolkit_args: Optional[Dict[str, Dict[str, Any]]] = None,
					skill_names: Optional[List[str]] = None,
					options_override: Optional[Dict[str, Any]] = None,
					memory_override: Optional[Dict[str, Any]] = None,
					user_id: Optional[str] = None) -> int:
		"""Start (or restart) the console agent server. Returns the port.
		Concurrent calls are serialized — a second call waits for the first to finish."""

		async with self._start_lock:
			return await self._start_impl(
				model_source,
				model_name,
				toolkit_names,
				use_backend_memory,
				toolkit_args,
				skill_names=skill_names,
				options_override=options_override,
				memory_override=memory_override,
				user_id=user_id,
			)

	async def _start_impl(self, model_source: Optional[str] = None,
						  model_name: Optional[str] = None,
						  toolkit_names: Optional[List[str]] = None,
						  use_backend_memory: Optional[bool] = None,
						  toolkit_args: Optional[Dict[str, Dict[str, Any]]] = None,
						  skill_names: Optional[List[str]] = None,
						  options_override: Optional[Dict[str, Any]] = None,
						  memory_override: Optional[Dict[str, Any]] = None,
						  user_id: Optional[str] = None) -> int:
		self._current_user_id = user_id
		_toolkit_args = toolkit_args or {}
		_options_override = dict(options_override) if options_override is not None else dict(self._options_override or {})
		_memory_override = dict(memory_override) if memory_override is not None else dict(self._memory_override or {})
		# Load config for defaults and instructions
		import credentials as _creds
		config = _creds.load_json(self._config_path)
		self._config = config
		effective_config = self._build_effective_console_config(
			config=config,
			options_override=_options_override or None,
			memory_override=_memory_override or None,
		)
		requested_use_backend = True

		model_cfg = effective_config.get("model", {})
		source = model_source or model_cfg.get("source", "ollama")
		name   = model_name   or model_cfg.get("name", "mistral")

		# Default toolkits: console_toolkit is always included
		cfg_toolkits = effective_config.get("toolkits", ["console_toolkit"])
		toolkits = toolkit_names if toolkit_names is not None else cfg_toolkits

		# Ensure console_toolkit is always present
		if "console_toolkit" not in toolkits:
			toolkits = ["console_toolkit"] + list(toolkits)

		# Check if anything changed
		if (self._started
			and source == self._model_source
			and name == self._model_name
			and toolkits == self._toolkit_names
			and skill_names == self._skill_names
			and requested_use_backend == self._use_backend_memory
			and _options_override == dict(self._options_override or {})
			and _memory_override == dict(self._memory_override or {})
			and user_id == self._agent_user_id):
			return self._port

		# Restart if already running
		if self._started:
			await self.stop()

		self._model_source  = source
		self._model_name    = name
		self._toolkit_names = toolkits
		self._toolkit_args  = dict(_toolkit_args)
		self._skill_names   = skill_names
		self._options_override = _options_override or None
		self._memory_override = _memory_override or None
		self._agent_user_id = user_id

		# Build tools from all configured toolkits
		tools = []
		for tk_name in toolkits:
			if tk_name == "console_toolkit":
				toolkit = ConsoleToolkit(
					base_url=self._base_url,
					auth_token=self._auth_token,
					internal_token=self._internal_token,
					user_id=user_id,
					local_app=self._fastapi_app,
				)
				native_toolkit = _wrap_numel_toolkit_for_backend(
					toolkit,
					name="console_toolkit",
					module_name="toolkits.console_toolkit",
				)
				if native_toolkit is not None:
					tools.append(native_toolkit)
			elif tk_name == "channel_toolkit":
				from toolkits.channel_toolkit import ChannelToolkit
				toolkit = ChannelToolkit(channel_registry=getattr(self, '_channel_reg', None))
				native_toolkit = _wrap_numel_toolkit_for_backend(
					toolkit,
					name="channel_toolkit",
					module_name="toolkits.channel_toolkit",
				)
				if native_toolkit is not None:
					tools.append(native_toolkit)
			else:
				tk_args = dict(_toolkit_args.get(tk_name) or {})
				for key, value in _toolkit_runtime_args(
					tk_name,
					base_url=self._base_url,
					internal_token=self._internal_token,
					user_id=user_id,
					auth_token=getattr(self, "_auth_token", ""),
					local_app=self._fastapi_app,
				).items():
					tk_args[key] = value
				native_toolkit = _load_native_toolkit(tk_name, tk_args or None)
				if native_toolkit is not None:
					tools.append(native_toolkit)

		log_print(f"Console agent tools: {[getattr(t, 'name', getattr(t, '__name__', str(t))) for t in tools]}")

		mem_cfg = normalize_assistant_memory_config(effective_config.get("memory", {}))
		self._use_backend_memory = True
		memory_db_path = resolve_assistant_memory_db_path(
			user_memory_db=self._user_memory_db,
			identity=user_id,
			fallback_config_path=self._config_path,
			backend_name=DEFAULT_BACKEND_NAME,
		)
		memory_components = build_assistant_memory_components(
			memory_cfg=mem_cfg,
			model_source=source,
			model_name=name,
			memory_db_path=memory_db_path,
		)
		log_print(f"Console agent: using backend memory ({memory_db_path})")

		# Build agent
		opts = effective_config.get("options", {})
		instructions = list(opts.get("instructions", []))

		native_skills = _resolve_native_skill_bundle(
			self._skill_mgr,
			skill_names=skill_names,
			backend_name=DEFAULT_BACKEND_NAME,
		)
		if native_skills is not None:
			log_print(f"Console agent: attached {len(native_skills.skills)} native skill(s)")

		self._agent, self._app = build_chat_runtime(
			backend_name=DEFAULT_BACKEND_NAME,
			name                    = opts.get("name", "Numel Assistant"),
			model_source            = source,
			model_name              = name,
			description             = opts.get("description", ""),
			instructions            = instructions,
			markdown                = opts.get("markdown", True),
			tools                   = tools,
			skills                  = native_skills,
			memory_db_path          = memory_db_path,
			history_config          = memory_components["history_mgr"],
			memory_config           = memory_components["memory_mgr"],
			session_config          = memory_components["session_mgr"],
		)

		# Start uvicorn server and wait for it to actually bind the port
		import uvicorn
		uv_config = uvicorn.Config(self._app, host="0.0.0.0", port=self._port, log_level="warning")
		self._server = uvicorn.Server(uv_config)
		self._server_task = asyncio.create_task(self._server.serve())

		# Wait until uvicorn signals it has finished startup (port is bound)
		for _ in range(40):  # up to 2 s
			if self._server.started:
				break
			await asyncio.sleep(0.05)

		self._started = True
		log_print(f"Console agent started on port {self._port} ({source}/{name}) toolkits={toolkits}")
		return self._port

	async def stop(self):
		"""Stop the console agent server."""
		if not self._started:
			return
		if self._server:
			self._server.should_exit = True
			if self._server_task:
				try:
					await asyncio.wait_for(self._server_task, timeout=5.0)
				except asyncio.TimeoutError:
					self._server_task.cancel()
		self._started    = False
		self._agent      = None
		self._app        = None
		self._server     = None
		self._server_task = None
		self._sessions   = {}
		log_print("Console agent stopped")

	def clear_memory(self):
		"""Clear all agent memory: sessions, backend memories, and in-memory history."""
		if self._agent:
			clear_chat_memory(self._agent, backend_name=DEFAULT_BACKEND_NAME)
		self._sessions.clear()
		log_print("Console memory cleared")

	@staticmethod
	def _build_effective_console_config(
		*,
		config: Dict[str, Any],
		options_override: Optional[Dict[str, Any]] = None,
		memory_override: Optional[Dict[str, Any]] = None,
	) -> Dict[str, Any]:
		effective = dict(config or {})
		options = dict(effective.get("options") or {})
		memory = dict(effective.get("memory") or {})

		if options_override:
			for key in ("name", "description", "prompt_override"):
				if key in options_override and options_override.get(key) is not None:
					options[key] = options_override.get(key)
			if "instructions" in options_override:
				options["instructions"] = list(options_override.get("instructions") or [])
			if "markdown" in options_override and options_override.get("markdown") is not None:
				options["markdown"] = bool(options_override.get("markdown"))

		if memory_override:
			for key, value in dict(memory_override).items():
				if value is not None:
					memory[key] = value

		memory["backend"] = True
		effective["options"] = options
		effective["memory"] = normalize_assistant_memory_config(memory)
		return effective

	def current_console_options(self) -> Dict[str, Any]:
		import credentials as _creds

		config = getattr(self, "_config", None) or _creds.load_json(self._config_path)
		effective_config = self._build_effective_console_config(
			config=config,
			options_override=self._options_override,
			memory_override=self._memory_override,
		)
		return dict(effective_config.get("options") or {})

	def _current_runtime_console_state(self) -> Dict[str, Any]:
		import credentials as _creds

		config = getattr(self, "_config", None) or _creds.load_json(self._config_path)
		effective_config = self._build_effective_console_config(
			config=config,
			options_override=self._options_override,
			memory_override=self._memory_override,
		)
		model_cfg = dict(effective_config.get("model") or config.get("model") or {})
		toolkit_names = list(self._toolkit_names or effective_config.get("toolkits") or ["console_toolkit"])
		if "console_toolkit" not in toolkit_names:
			toolkit_names = ["console_toolkit"] + list(toolkit_names)
		return {
			"config": config,
			"effective_config": effective_config,
			"model_source": self._model_source or model_cfg.get("source", "ollama"),
			"model_name": self._model_name or model_cfg.get("name", "mistral"),
			"toolkit_names": toolkit_names,
			"toolkit_args": dict(self._toolkit_args or {}),
			"skill_names": list(self._skill_names or []),
			"options": dict(effective_config.get("options") or {}),
			"memory": normalize_assistant_memory_config(effective_config.get("memory") or {}),
		}

	async def _run_workflow_backed_console_turn(
		self,
		*,
		message: str,
		user_id: Optional[str] = None,
		auth_token: str = "",
		extra_instructions: Optional[List[str]] = None,
		workflow_name: str = "Console Agent Turn",
		sender_name: Optional[str] = None,
		assistant_name: Optional[str] = None,
		assistant_description: Optional[str] = None,
		include_context: bool = False,
	) -> Dict[str, Any]:
		state = self._current_runtime_console_state()
		options = dict(state.get("options") or {})
		augmented = message
		if include_context:
			try:
				ctx = await self.get_context(user_id=user_id)
				parts = []
				if ctx.get("context"):
					parts.append(f"[Current space state]\n{ctx['context']}")
				if parts:
					augmented = "\n\n".join(parts) + f"\n\n[User message]\n{message}"
			except Exception as exc:
				log_print(f"Workflow-backed console turn: context augmentation failed: {exc}")

		result = await run_workflow_backed_agent_turn(
			workflow_name=workflow_name,
			request=augmented,
			model_source=str(state["model_source"]),
			model_name=str(state["model_name"]),
			toolkit_names=list(state["toolkit_names"]),
			toolkit_args=dict(state["toolkit_args"]),
			skill_names=list(state["skill_names"]),
			options_config=options,
			extra_instructions=list(extra_instructions or []),
			sender_name=sender_name,
			assistant_name=assistant_name or str(options.get("name") or "Numel Assistant"),
			assistant_description=assistant_description if assistant_description is not None else str(options.get("description") or ""),
			base_url=self._base_url,
			internal_token=self._internal_token,
			user_id=user_id,
			auth_token=auth_token or self._auth_token,
			local_app=self._fastapi_app,
			channel_registry=getattr(self, "_channel_reg", None),
			memory_config=dict(state.get("memory") or {}),
			memory_db_path=resolve_assistant_memory_db_path(
				user_memory_db=self._user_memory_db,
				identity=user_id or self._agent_user_id,
				fallback_config_path=self._config_path,
				backend_name=DEFAULT_BACKEND_NAME,
			),
			backend_name=DEFAULT_BACKEND_NAME,
		)
		result.setdefault("tool_calls", [])
		return result

	def build_workflow_export(
		self,
		*,
		include_planner: bool = False,
		user_id: Optional[str] = None,
		session_id: Optional[str] = None,
	) -> Dict[str, Any]:
		"""Materialize the current console assistant configuration as a workflow payload."""
		import credentials as _creds

		config = getattr(self, "_config", None) or _creds.load_json(self._config_path)
		effective_config = self._build_effective_console_config(
			config=config,
			options_override=self._options_override,
			memory_override=self._memory_override,
		)
		model_cfg = dict(config.get("model") or {})
		source = self._model_source or model_cfg.get("source", "ollama")
		name = self._model_name or model_cfg.get("name", "mistral")
		toolkit_names = list(self._toolkit_names or config.get("toolkits", ["console_toolkit"]))
		if "console_toolkit" not in toolkit_names:
			toolkit_names = ["console_toolkit"] + list(toolkit_names)
		skill_names = list(self._skill_names or [])
		use_backend_memory = True
		export_user_id = user_id or self._agent_user_id
		planner_state = None
		if include_planner:
			planner_state = self._planner_export_state(
				self._resolve_planner_state(user_id, session_id)
			)
		payload = build_console_workflow_export(
			config=effective_config,
			model_source=source,
			model_name=name,
			toolkit_names=toolkit_names,
			toolkit_args=dict(self._toolkit_args or {}),
			skill_names=skill_names,
			use_backend_memory=use_backend_memory,
			memory_db_path=resolve_assistant_memory_db_path(
				user_memory_db=self._user_memory_db,
				identity=export_user_id,
				fallback_config_path=self._config_path,
				backend_name=DEFAULT_BACKEND_NAME,
			),
			backend_name=DEFAULT_BACKEND_NAME,
			planner_state=planner_state,
		)
		payload["planner_requested"] = bool(include_planner)
		payload["planner_available"] = planner_state is not None
		return payload

	async def apply_workflow_import(self, workflow: Dict[str, Any], *, user_id: Optional[str] = None) -> Dict[str, Any]:
		parsed = parse_console_workflow_import(workflow, backend_name=DEFAULT_BACKEND_NAME)
		port = await self.start(
			model_source=parsed["model_source"],
			model_name=parsed["model_name"],
			toolkit_names=parsed["toolkit_names"],
			use_backend_memory=True,
			toolkit_args=parsed["toolkit_args"],
			skill_names=parsed["skill_names"],
			options_override=parsed["options_override"],
			memory_override=parsed.get("memory_override"),
			user_id=user_id,
		)
		return {
			"applied": True,
			"started": self._started,
			"port": port,
			"workflow_name": parsed["workflow_name"],
			"model_source": self._model_source,
			"model_name": self._model_name,
			"toolkit_names": list(self._toolkit_names or []),
			"toolkit_args": dict(self._toolkit_args or {}),
			"skill_names": list(self._skill_names or []),
			"use_backend_memory": bool(self._use_backend_memory),
			"memory_override": dict(self._current_runtime_console_state().get("memory") or {}),
			"options": self.current_console_options(),
			"warnings": list(parsed.get("warnings") or []),
		}

	# ── Planner Mode (per-session) ────────────────────────────────

	async def enable_planner(self, config: Optional[Dict[str, Any]] = None,
							 user_id: Optional[str] = None,
							 session_id: Optional[str] = None):
		"""Activate planner mode for a specific session."""
		if not hasattr(self, "_config") or not isinstance(getattr(self, "_config", None), dict):
			import credentials as _creds
			self._config = _creds.load_json(self._config_path)
		pkey = self._planner_key(user_id, session_id)
		# If this session already has an active planner, skip
		existing = self._planners.get(pkey)
		if existing and existing.enabled:
			return

		cfg = config or {}
		log_print(f"Planner enable [{pkey[:20]}] config: {cfg}")

		ps = PlannerState(key=pkey, user_id=user_id, browser_session_id=session_id)
		ps.max_turns        = cfg.get("max_iterations", cfg.get("max_autonomous_turns", 10))
		ps.debounce         = cfg.get("debounce_ms", 2000) / 1000.0
		ps.timeout          = cfg.get("timeout_s", 120)
		ps.session_timeout  = cfg.get("session_timeout_s", 600)
		ps.session_start    = time.time()
		log_print(f"Planner [{pkey[:20]}]: {ps.timeout}s per-turn, {ps.session_timeout}s total, max {ps.max_turns} iter")

		# Resolve profile
		profile_name = cfg.get("profile", "")
		planner_cfg = self._config.get("planner", {})
		profiles = planner_cfg.get("profiles", {})
		profile = profiles.get(profile_name, {}) if profile_name else {}
		ps.profile = profile_name or "workflow"

		# Load planner instructions
		instr_file = profile.get("instructions_file") or cfg.get("instructions_file", "planner_instructions.txt")
		instr_path = os.path.join(os.path.dirname(self._config_path), instr_file)
		try:
			with open(instr_path) as f:
				ps.instructions = f.read().replace("{max_autonomous_turns}", str(ps.max_turns))
		except FileNotFoundError:
			log_print(f"Planner instructions file not found: {instr_path}")

		# Auto-add toolkits required by the profile (affects singleton agent)
		required_toolkits = profile.get("toolkits", ["workspace_toolkit", "file_toolkit"])
		added = []
		for tk in required_toolkits:
			if tk not in self._toolkit_names:
				self._toolkit_names.append(tk)
				added.append(tk)
		if added:
			log_print(f"Planner: auto-adding {', '.join(added)}")
			if self._started:
				await self.stop()
				await self.start(
					model_source=self._model_source,
					model_name=self._model_name,
					toolkit_names=list(self._toolkit_names),
					skill_names=self._skill_names,
				)

		# Subscribe to events (shared handler — dispatches to all active planners)
		event_types = cfg.get("subscribe_events", [
			"workflow.completed", "workflow.failed", "manager.workflow_added"
		])
		ps.subs = list(event_types)
		# Only subscribe if this is the first active planner (events are shared)
		if not self._planner_enabled:
			for et in event_types:
				self._event_bus.subscribe(et, self._on_planner_event)

		ps.enabled = True
		self._planners[pkey] = ps

		# Inject planner directive into the singleton agent's system prompt
		if self._agent:
			if not hasattr(self, '_base_instructions'):
				self._base_instructions = list(self._agent.instructions or [])
			self._agent.instructions = extend_instruction_block(
				self._base_instructions,
				"Planner Mode",
				[PLANNER_MODE_DIRECTIVE],
			)

		log_print(f"Planner [{pkey[:20]}] enabled (events={event_types})")

	def disable_planner(self, user_id: Optional[str] = None,
						session_id: Optional[str] = None):
		"""Deactivate planner for a specific session, or all sessions if both are None."""
		ps = None
		if user_id is None and session_id is None:
			# Disable all planners
			keys = list(self._planners.keys())
			for k in keys:
				self._disable_planner_state(self._planners[k])
			self._planners.clear()
		else:
			ps = self._resolve_planner_state(user_id, session_id)
			if ps:
				self._planners.pop(ps.key, None)
				self._disable_planner_state(ps)

		# Unsubscribe from events if no planners remain active
		if not self._planner_enabled:
			# Gather all event types from disabled planners' subs
			all_subs = set()
			if ps:
				all_subs.update(ps.subs)
			for et in all_subs:
				try:
					self._event_bus.unsubscribe(et, self._on_planner_event)
				except (ValueError, KeyError):
					pass
			# Restore original system prompt
			if self._agent and hasattr(self, '_base_instructions'):
				self._agent.instructions = self._base_instructions

		log_print(f"Planner disabled (active planners: {sum(1 for p in self._planners.values() if p.enabled)})")

	def _disable_planner_state(self, ps: PlannerState):
		"""Clean up a single PlannerState."""
		ps.enabled = False
		ps.active  = False
		ps.pause_until = 0.0
		ps.suppress_added_until = 0.0
		ps.debounce_until = 0.0
		ps.pending.clear()
		if ps.timer:
			ps.timer.cancel()
			ps.timer = None

	def pause_planner_for_manual_run(self, user_id: Optional[str] = None,
	                                 session_id: Optional[str] = None,
	                                 duration_s: int = 180) -> bool:
		"""Keep planner enabled but ignore the next workflow execution reaction window."""
		ps = self._resolve_planner_state(user_id, session_id)
		if not ps or not ps.enabled:
			return False
		ps.pause_until = time.time() + max(10, int(duration_s))
		ps.last_pause_reason = "manual_run"
		ps.pending.clear()
		if ps.timer:
			ps.timer.cancel()
			ps.timer = None
		ps.debounce_until = 0.0
		log_print(f"Planner [{ps.key[:20]}] paused for manual run ({duration_s}s)")
		return True

	def suppress_planner_added_reaction(self, user_id: Optional[str] = None,
	                                    session_id: Optional[str] = None,
	                                    duration_s: int = 15) -> bool:
		"""Ignore manager.workflow_added briefly after planner-driven workflow apply."""
		ps = self._resolve_planner_state(user_id, session_id)
		if not ps or not ps.enabled:
			return False
		ps.suppress_added_until = time.time() + max(2, int(duration_s))
		ps.last_pause_reason = "planner_apply"
		log_print(f"Planner [{ps.key[:20]}] suppressing workflow_added for {duration_s}s")
		return True

	async def _on_planner_event(self, event):
		"""EventBus callback — dispatch event to ALL active planners with debounce."""
		evt_type = getattr(event, 'event_type', str(event))
		evt_data = {"type": evt_type, "data": getattr(event, 'data', {})}
		now = time.time()

		for ps in list(self._planners.values()):
			if not ps.enabled:
				continue
			if evt_type == "manager.workflow_added" and now < ps.suppress_added_until:
				ps.last_suppressed_event = evt_type
				log_print(f"Planner [{ps.key[:20]}] ignored {evt_type} after planner apply")
				continue
			if evt_type in {"workflow.completed", "workflow.failed", "manager.workflow_added"} and now < ps.pause_until:
				ps.last_suppressed_event = evt_type
				log_print(f"Planner [{ps.key[:20]}] ignored {evt_type} during manual-run pause window")
				continue
			self._queue_planner_event(ps, evt_type, evt_data)
			if not ps.active:
				self._schedule_planner_processing(ps)

	async def _process_planner_events(self, planner_key: str):
		"""Process queued events for a specific planner session."""
		ps = self._planners.get(planner_key)
		if not ps:
			return
		if ps.timer:
			ps.timer.cancel()
			ps.timer = None
		ps.debounce_until = 0.0

		async with self._planner_lock:
			ps = self._planners.get(planner_key)
			if not ps or not ps.enabled or not ps.pending or ps.active:
				return

			if ps.turn_count >= ps.max_turns:
				await self.push_proactive(
					f"Planner reached max iterations ({ps.max_turns}). Send a message to continue.",
					"planner_paused",
					session_id=ps.browser_session_id,
				)
				return

			elapsed = time.time() - ps.session_start
			if elapsed >= ps.session_timeout:
				await self.push_proactive(
					f"Planner session timed out after {int(elapsed)}s (limit: {ps.session_timeout}s). Disabling.",
					"planner_error",
					session_id=ps.browser_session_id,
				)
				self.disable_planner(ps.user_id, ps.browser_session_id)
				return

			ps.active = True
			try:
				events = ps.pending[:]
				ps.pending.clear()

				summary_lines: List[str] = []
				for e in events:
					count = int(e.get("count", 1) or 1)
					count_suffix = f" x{count}" if count > 1 else ""
					summary_lines.append(
						f"- {e['type']}{count_suffix}: {json.dumps(e['data'], default=str)[:200]}"
					)
				event_summary = "\n".join(summary_lines)
				event_types = [str(e.get("type", "") or "") for e in events]
				unique_event_types: List[str] = []
				for event_type in event_types:
					if event_type and event_type not in unique_event_types:
						unique_event_types.append(event_type)
				if unique_event_types:
					reason = "Planner triggered by " + ", ".join(unique_event_types) + "."
					await self.push_proactive(reason, "planner_reason", session_id=ps.browser_session_id)
				await self.push_proactive("", "planner_thinking", session_id=ps.browser_session_id)
				message = (
					f"[Planner Event]\n{event_summary}\n\n"
					"Analyze the results. If the score is below 0.7 or there are workflow logic errors, "
					"output a FIXED workflow as a ```json code block. The system will load it automatically.\n"
					"IMPORTANT: If the error is about port conflicts, timeouts, or server issues, "
					"do NOT modify the workflow — just report the infrastructure error and stop."
				)

				# Acquire workflow lock for exclusive access during planner modifications
				async with self._workflow_lock:
					try:
						result = await asyncio.wait_for(
							self._run_workflow_backed_console_turn(
								message=message,
								user_id=ps.user_id,
								extra_instructions=[PLANNER_MODE_DIRECTIVE],
								workflow_name="Planner Event Turn",
								sender_name="Planner",
								include_context=True,
							),
							timeout=ps.timeout,
						)
						ps.turn_count += 1
						ps.last_processed_at = time.time()
						response = result.get("response", "")
						if response:
							await self.push_proactive(response, "planner_action", session_id=ps.browser_session_id)
						else:
							await self.push_proactive("Planner turn completed (no output).", "planner_action", session_id=ps.browser_session_id)
					except asyncio.TimeoutError:
						log_print(f"Planner [{planner_key[:20]}] timed out after {ps.timeout}s")
						await self.push_proactive(
							f"Planner turn timed out after {ps.timeout}s. Disabling.",
							"planner_error",
							session_id=ps.browser_session_id,
						)
						self.disable_planner(ps.user_id, ps.browser_session_id)
					except Exception as e:
						log_print(f"Planner [{planner_key[:20]}] error: {e}")
						await self.push_proactive(f"Planner error: {e}", "planner_error", session_id=ps.browser_session_id)
			finally:
				ps.active = False
				await self.push_proactive("", "planner_done", session_id=ps.browser_session_id)
				if ps.enabled and ps.pending and time.time() >= ps.pause_until:
					self._schedule_planner_processing(ps, delay=0.05)

	def reset_planner(self, user_id: Optional[str] = None,
					  session_id: Optional[str] = None):
		"""Reset planner turn count and session for a specific session."""
		pkey = self._planner_key(user_id, session_id)
		ps = self._planners.get(pkey)
		if ps:
			ps.reset()

	# ── Chat ───────────────────────────────────────────────────────

	async def chat(self, message: str, session_id: Optional[str] = None,
				   include_context: bool = True,
				   attachments: Optional[list] = None) -> dict:
		"""Send a message and get a response. Uses backend-managed session history.
		Returns { session_id, response, tool_calls }.
		attachments: list of Attachment objects from ChannelMessage (described in prompt)."""

		if not self._started or not self._agent:
			raise RuntimeError("Console agent is not running. Call /console/start first.")

		# Resolve or create session
		if not session_id:
			session_id = str(uuid.uuid4())

		# Reset planner turn count on user-initiated messages (not planner events)
		if self._planner_enabled:
			for ps in self._planners.values():
				if ps.enabled and session_id != ps.session_id:
					ps.turn_count = 0

		# Inject attachment descriptions into the message
		if attachments:
			message = _describe_attachments(message, attachments)

		# Prepend workspace context to the user message
		augmented = message

		if include_context:
			try:
				ctx = await self.get_context()
				parts = []
				if ctx.get("context"):
					parts.append(f"[Current space state]\n{ctx['context']}")
				if parts:
					augmented = "\n\n".join(parts) + f"\n\n[User message]\n{message}"
			except Exception as e:
				log_print(f"Console chat: context augmentation failed: {e}")

		# Track turn count per session for memory persistence
		if session_id not in self._sessions:
			self._sessions[session_id] = 0
		self._sessions[session_id] += 1

		# Run the agent asynchronously with session_id for built-in history
		tool_names = [getattr(t, '__name__', getattr(t, 'name', str(t))) for t in (self._agent.tools or [])]
		log_print(f"Console chat: running agent (session={session_id[:8]}..., tools={tool_names}, msg={message[:60]}...)")
		try:
			response = await run_chat_agent(
				self._agent,
				augmented,
				session_id=session_id,
				backend_name=DEFAULT_BACKEND_NAME,
			)
		except Exception as e:
			log_print(f"ERROR    Error in Agent run: {e}")
			return {"session_id": session_id, "error": str(e), "tool_calls": []}
		log_print(f"Console chat: agent done (tools={len(response.tools or [])} msgs={len(response.messages or [])})")

		# Extract the assistant response
		assistant_content = ""
		tool_calls = extract_chat_tool_calls(response, backend_name=DEFAULT_BACKEND_NAME)
		assistant_content = extract_chat_response_text(response, backend_name=DEFAULT_BACKEND_NAME)

		# Planner responses may include workflow JSON, but web/app clients are responsible
		# for validating and applying it through the explicit planner-apply route.
		if self._planner_enabled and assistant_content and not tool_calls:
			wf_json = self._extract_workflow_json(assistant_content)
			if wf_json:
				log_print(
					f"Planner: workflow JSON prepared for client-side apply "
					f"({len(wf_json.get('nodes', []))} nodes)"
				)

		# Detect model/infra errors returned as assistant content by the backend
		_ERROR_PATTERNS = ("not found", "status code:", "connection refused", "timed out", "unreachable")
		if assistant_content and not tool_calls and any(p in assistant_content.lower() for p in _ERROR_PATTERNS):
			return {
				"session_id": session_id,
				"error":      assistant_content,
				"tool_calls": [],
			}

		return {
			"session_id": session_id,
			"response":   assistant_content,
			"tool_calls": tool_calls,
		}

	# ── Planner helpers ────────────────────────────────────────────

	@staticmethod
	def _extract_workflow_json(text: str):
		"""Try to extract a workflow JSON object from the assistant response."""
		import re
		# Try ```json ... ``` block first
		m = re.search(r'```(?:json)?\s*\n?([\s\S]*?)\n?```', text)
		if m:
			try:
				d = json.loads(m.group(1).strip())
				if "nodes" in d:
					return d
			except json.JSONDecodeError:
				pass
		# Try raw JSON object
		start = text.find('{')
		end = text.rfind('}')
		if start != -1 and end > start:
			try:
				d = json.loads(text[start:end + 1])
				if "nodes" in d:
					return d
			except json.JSONDecodeError:
				pass
		return None

	async def _apply_workflow_json(self, wf_json: dict, user_id: Optional[str] = None) -> Dict[str, Any]:
		"""Apply a workflow JSON dict through the current-workflow HTTP routes."""
		acting_user_id = user_id or self._current_user_id
		validation = validate_workflow_payload(wf_json, apply_repairs=True)
		if not validation["valid"]:
			error_msg = "; ".join(validation["errors"])
			raise ValueError(error_msg or "Workflow validation failed")
		workflow_doc = validation["workflow"]
		resp = await self._post_json("/workflow/save", {"workflow": workflow_doc}, user_id=acting_user_id)
		name = resp.get("name") or "Current Workflow"
		return {
			"name": name,
			"nodes": len(workflow_doc.get("nodes", [])),
			"workflow": workflow_doc,
			"repaired": bool(validation["repaired"]),
			"repairs": list(validation["repairs"]),
			"warnings": list(validation["warnings"]),
			"message": f"ok: saved '{name}' ({len(workflow_doc.get('nodes', []))} nodes)",
		}

	# ── Context ────────────────────────────────────────────────────

	async def get_context(self, user_id: Optional[str] = None) -> dict:
		"""Gather current space context for the console agent through HTTP routes."""
		acting_user_id = user_id or self._current_user_id
		context_parts = []
		has_workflow = False
		execution_active = False

		workflow_data = await self._post_json("/workflow/get", user_id=acting_user_id)
		space = workflow_data.get("space") or {}
		workflow = workflow_data.get("workflow")
		if space:
			space_title = str(space.get("title", "") or space.get("slug", "") or "Current Space")
			context_parts.append(f"Space: {space_title}")

		if isinstance(workflow, dict):
			has_workflow = True
			nodes = workflow.get("nodes") or []
			edges = workflow.get("edges") or []
			wf_name = workflow_data.get("name") or "Current Workflow"
			node_types = []
			for i, node in enumerate(nodes):
				if not isinstance(node, dict):
					continue
				ntype = str(node.get("type", "?"))
				extra = node.get("extra") if isinstance(node.get("extra"), dict) else {}
				nname = str(extra.get("name", "") or "")
				node_types.append(f"[{i}] {ntype}" + (f" ({nname})" if nname else ""))

			context_parts.append(f"Workflow '{wf_name}': {len(nodes)} nodes, {len(edges)} edges")
			context_parts.append("Nodes: " + ", ".join(node_types[:20]))
			if len(node_types) > 20:
				context_parts.append(f"  ... and {len(node_types) - 20} more")
		else:
			context_parts.append("No workflow is currently loaded in the current space.")

		execution_data = await self._post_json("/executions/list", user_id=acting_user_id)
		executions = execution_data.get("executions", []) or []
		active = [row for row in executions if str(row.get("status", "")).lower() in ("queued", "running")]
		execution_active = len(active) > 0
		if active:
			context_parts.append(f"Active executions: {len(active)}")
		else:
			context_parts.append("No active executions.")
		if executions:
			recent = executions[:3]
			recent_summary = ", ".join(
				f"{str(row.get('execution_id', '') or '')[:8]} ({row.get('status', '?')})"
				for row in recent
			)
			if recent_summary:
				context_parts.append(f"Recent executions: {recent_summary}")

		# Prepend planner generation contract and instructions if active
		planner_ctx = ""
		if self._planner_enabled and self._planner_instructions:
			active_generation_toolkits = [
				name for name in self._toolkit_names
				if name not in ("console_toolkit", "channel_toolkit")
			]
			# Include generation prompt (node catalog + JSON schema) so the planner can build workflows
			build_prompt = getattr(getattr(self, '_fastapi_app', None), 'state', None)
			build_prompt = getattr(build_prompt, 'build_generation_prompt', None) if build_prompt else None
			if build_prompt:
				try:
					gen_prompt = build_prompt(
						toolkit_names=active_generation_toolkits if active_generation_toolkits else [],
					)
					log_print(f"Planner: injecting node catalog ({len(gen_prompt)} chars)")
					planner_ctx += f"[Workflow Generation Contract]\n{gen_prompt}\n\n"
				except Exception as e:
					log_print(f"Planner: node catalog build failed: {e}")
			else:
				log_print(f"Planner: no build_generation_prompt (fastapi_app={self._fastapi_app is not None})")
			planner_ctx += f"[Planner Instructions]\n{self._planner_instructions}\n\n"

		return {
			"context":          planner_ctx + "\n".join(context_parts),
			"has_workflow":     has_workflow,
			"execution_active": execution_active,
		}

	# ── Proactive ──────────────────────────────────────────────────

	async def push_proactive(self, content: str, msg_type: str = "suggestion", severity: str = "info",
	                         session_id: Optional[str] = None):
		"""Push a proactive message to connected console WebSocket clients, optionally scoped to one tab session."""
		msg = json.dumps({"type": msg_type, "content": content, "severity": severity, "session_id": session_id})
		disconnected = set()
		for ws, ws_session_id in list(self._proactive_ws.items()):
			if session_id is not None and ws_session_id not in (session_id, None):
				continue
			try:
				await ws.send_text(msg)
			except Exception:
				disconnected.add(ws)
		for ws in disconnected:
			self._proactive_ws.pop(ws, None)

	def setup_proactive_listeners(self):
		"""Subscribe to EventBus events that trigger proactive suggestions."""
		async def on_workflow_added(event):
			ctx = await self.get_context()
			if ctx["has_workflow"]:
				await self.push_proactive(
					f"Workflow loaded. {ctx['context']}\n\nWould you like me to review it for issues?",
					severity="info"
				)

		self._event_bus.subscribe("MANAGER_WORKFLOW_ADDED", on_workflow_added)


# ── Channel Agent Pool ──────────────────────────────────────────
#
# Per-user agent instances for channel messages.  Each session_id gets
# its own lightweight Agent (no AGUI server, no planner, no WebSocket).
# Idle agents are cleaned up after a configurable timeout.

class ChannelAgentPool:
	"""Manages per-session backend chat-agent instances for channel messages."""

	def __init__(self, config_path: str = _CONFIG_PATH,
				 workspace_mgr=None,
				 user_memory_db=None, channel_registry=None,
				 idle_timeout: float = 1800,
				 base_url: str = "http://localhost:11360",
				 internal_token: str = "",
				 fastapi_app=None):
		self._config_path    = config_path
		self._ws_mgr         = workspace_mgr
		self._user_memory_db = user_memory_db       # UserMemoryDB for per-user isolation
		self._channel_reg    = channel_registry      # ChannelRegistry for cross-channel messaging
		self._idle_timeout   = idle_timeout          # seconds before evicting idle agent
		self._base_url       = base_url.rstrip("/")
		self._internal_token = internal_token
		self._fastapi_app    = fastapi_app
		self._skill_mgr      = None                  # set via set_skill_mgr()
		self._agents: Dict[str, Any]        = {}    # session_id → backend agent handle
		self._agent_tks: Dict[str, List[str]] = {}  # session_id → toolkit names used at build
		self._agent_uids: Dict[str, str]    = {}    # session_id → user_id used at build
		self._agent_specs: Dict[str, Dict[str, Any]] = {}  # session_id → build overrides
		self._agent_tokens: Dict[str, str]  = {}    # session_id → auth token
		self._last_used: Dict[str, float]   = {}    # session_id → timestamp
		self._pending_tool_approvals: Dict[str, Dict[str, Any]] = {}
		self._lock = asyncio.Lock()
		self._cleanup_task: Optional[asyncio.Task] = None

	def set_skill_mgr(self, mgr):
		"""Inject the skill manager for resolving skill instructions."""
		self._skill_mgr = mgr

	async def _get_or_create(self, session_id: str,
							 toolkits: Optional[List[str]] = None,
							 sender_name: Optional[str] = None,
							 user_id: Optional[str] = None,
							 is_guest: bool = False,
							 auth_token: Optional[str] = None,
							 extra_instructions: Optional[List[str]] = None,
							 model_source: Optional[str] = None,
							 model_name: Optional[str] = None,
							 skill_names: Optional[List[str]] = None,
							 tool_confirmation_mode: Optional[str] = None,
							 assistant_name: Optional[str] = None,
							 assistant_description: Optional[str] = None,
							 deployment_id: Optional[str] = None):
		"""Return (or lazily build) the backend chat agent for this session."""
		async with self._lock:
			# Update stored token if a fresh one is provided
			if auth_token:
				self._agent_tokens[session_id] = auth_token

			spec = {
				"toolkits": list(toolkits) if toolkits is not None else None,
				"user_id": user_id or session_id,
				"model_source": model_source or "",
				"model_name": model_name or "",
				"skill_names": list(skill_names) if skill_names is not None else None,
				"tool_confirmation_mode": tool_confirmation_mode or "",
				"assistant_name": assistant_name or "",
				"assistant_description": assistant_description or "",
				"deployment_id": deployment_id or "",
				"extra_instructions": list(extra_instructions) if extra_instructions else [],
			}

			if session_id in self._agents:
				# Rebuild if toolkit list or user identity changed
				if spec != self._agent_specs.get(session_id):
					self._agents.pop(session_id, None)
					self._agent_tks.pop(session_id, None)
					self._agent_uids.pop(session_id, None)
					self._agent_specs.pop(session_id, None)
				else:
					self._last_used[session_id] = time.time()
					return self._agents[session_id]

			token = self._agent_tokens.get(session_id, "")
			agent = await self._build_agent(
				toolkits=toolkits, sender_name=sender_name,
				user_id=user_id, is_guest=is_guest, auth_token=token,
				extra_instructions=extra_instructions,
				model_source=model_source,
				model_name=model_name,
				skill_names=skill_names,
				tool_confirmation_mode=tool_confirmation_mode,
				assistant_name=assistant_name,
				assistant_description=assistant_description,
				deployment_id=deployment_id,
			)
			self._agents[session_id]   = agent
			self._agent_tks[session_id] = list(toolkits) if toolkits else []
			self._agent_uids[session_id] = user_id or session_id
			self._agent_specs[session_id] = spec
			self._last_used[session_id] = time.time()

			# Start periodic cleanup if not running
			if self._cleanup_task is None or self._cleanup_task.done():
				self._cleanup_task = asyncio.create_task(self._cleanup_loop())

			log_print(f"ChannelAgentPool: created agent for session {session_id[:16]} "
					  f"(user={user_id or 'anon'}, pool size: {len(self._agents)})")
			return agent

	async def evict(self, session_id: str):
		"""Remove a cached agent so it gets rebuilt on next message."""
		async with self._lock:
			self._agents.pop(session_id, None)
			self._agent_tks.pop(session_id, None)
			self._agent_uids.pop(session_id, None)
			self._agent_specs.pop(session_id, None)
			self._agent_tokens.pop(session_id, None)
			self._last_used.pop(session_id, None)
			self._pending_tool_approvals = {
				approval_id: row
				for approval_id, row in self._pending_tool_approvals.items()
				if row.get("session_id") != session_id
			}

	async def _build_agent(self, toolkits: Optional[List[str]] = None,
						   sender_name: Optional[str] = None,
						   user_id: Optional[str] = None,
						   is_guest: bool = False,
						   auth_token: str = "",
						   extra_instructions: Optional[List[str]] = None,
						   model_source: Optional[str] = None,
						   model_name: Optional[str] = None,
						   skill_names: Optional[List[str]] = None,
						   tool_confirmation_mode: Optional[str] = None,
						   assistant_name: Optional[str] = None,
						   assistant_description: Optional[str] = None,
						   deployment_id: Optional[str] = None):
		"""Build a lightweight backend chat agent from console defaults."""
		import credentials as _creds
		config = _creds.load_json(self._config_path)
		effective_config = ConsoleAgentManager._build_effective_console_config(
			config=config,
		)

		model_cfg = effective_config.get("model", {})
		source    = model_source or model_cfg.get("source", "ollama")
		name      = model_name or model_cfg.get("name", "mistral")

		# Build tools — use per-user toolkit list if provided, else config defaults
		tk_names = toolkits if toolkits is not None else effective_config.get("toolkits", ["console_toolkit"])
		# Always include console_toolkit if workspace is available
		if self._ws_mgr and "console_toolkit" not in tk_names:
			tk_names = ["console_toolkit"] + list(tk_names)
		confirm_all_tools = str(tool_confirmation_mode or "auto").strip().lower() == "approval"

		tools = []
		_INJECTED = {"console_toolkit", "channel_toolkit"}
		for tk_name in tk_names:
			if tk_name == "console_toolkit" and self._ws_mgr:
				toolkit = ConsoleToolkit(
					base_url=self._base_url,
					auth_token=auth_token,
					internal_token=self._internal_token,
					user_id=user_id,
					local_app=self._fastapi_app,
				)
				native_toolkit = _wrap_numel_toolkit_for_backend(
					toolkit,
					name="console_toolkit",
					module_name="toolkits.console_toolkit",
					confirm_all_tools=confirm_all_tools,
				)
				if native_toolkit is not None:
					tools.append(native_toolkit)
			elif tk_name == "channel_toolkit" and self._channel_reg:
				from toolkits.channel_toolkit import ChannelToolkit
				toolkit = ChannelToolkit(channel_registry=self._channel_reg)
				native_toolkit = _wrap_numel_toolkit_for_backend(
					toolkit,
					name="channel_toolkit",
					module_name="toolkits.channel_toolkit",
					confirm_all_tools=confirm_all_tools,
				)
				if native_toolkit is not None:
					tools.append(native_toolkit)
			elif tk_name not in _INJECTED:
				tk_args = {}
				for key, value in _toolkit_runtime_args(
					tk_name,
					base_url=self._base_url,
					internal_token=self._internal_token,
					user_id=user_id,
					auth_token=auth_token,
					local_app=self._fastapi_app,
					deployment_id=deployment_id,
				).items():
					tk_args[key] = value
				native_toolkit = _load_native_toolkit(
					tk_name,
					tk_args or None,
					log_prefix="Channel toolkit",
					confirm_all_tools=confirm_all_tools,
				)
				if native_toolkit is not None:
					tools.append(native_toolkit)

		mem_cfg = normalize_assistant_memory_config(effective_config.get("memory", {}))
		identity = user_id or (f"guest_{sender_name or session_id}" if is_guest else session_id)
		memory_db_path = resolve_assistant_memory_db_path(
			user_memory_db=self._user_memory_db,
			identity=identity,
			is_guest=is_guest,
			fallback_config_path=self._config_path,
			backend_name=DEFAULT_BACKEND_NAME,
		)
		memory_components = build_assistant_memory_components(
			memory_cfg=mem_cfg,
			model_source=source,
			model_name=name,
			memory_db_path=memory_db_path,
		)
		log_print(f"ChannelAgentPool: memory db → {os.path.basename(memory_db_path)}")

		opts = effective_config.get("options", {})
		instructions = list(opts.get("instructions", []))
		if sender_name:
			instructions.insert(0, f"You are chatting with {sender_name}.")

		native_skills = _resolve_native_skill_bundle(
			self._skill_mgr,
			skill_names=skill_names,
			backend_name=DEFAULT_BACKEND_NAME,
		)

		# Inject extra instructions (e.g. planner directive)
		if extra_instructions:
			instructions.extend(extra_instructions)

		return build_chat_agent(
			backend_name            = DEFAULT_BACKEND_NAME,
			name                    = assistant_name or opts.get("name", "Numel Assistant"),
			model_source            = source,
			model_name              = name,
			description             = assistant_description if assistant_description is not None else opts.get("description", ""),
			instructions            = instructions,
			markdown                = opts.get("markdown", True),
			tools                   = tools,
			skills                  = native_skills,
			memory_db_path          = memory_db_path,
			history_config          = memory_components["history_mgr"],
			memory_config           = memory_components["memory_mgr"],
			session_config          = memory_components["session_mgr"],
		)

	async def chat(self, message: str, session_id: str,
				   toolkits: Optional[List[str]] = None,
				   sender_name: Optional[str] = None,
				   user_id: Optional[str] = None,
				   is_guest: bool = False,
				   auth_token: Optional[str] = None,
				   attachments: Optional[list] = None,
				   extra_instructions: Optional[List[str]] = None,
				   model_source: Optional[str] = None,
				   model_name: Optional[str] = None,
				   skill_names: Optional[List[str]] = None,
				   deployment_id: Optional[str] = None,
				   tool_confirmation_mode: Optional[str] = None,
				   assistant_name: Optional[str] = None,
				   assistant_description: Optional[str] = None) -> dict:
		"""Send a message to the per-session agent. Returns {session_id, response, tool_calls}.
		attachments: list of Attachment objects from ChannelMessage (described in prompt)."""
		try:
			agent = await self._get_or_create(
				session_id, toolkits=toolkits, sender_name=sender_name,
				user_id=user_id, is_guest=is_guest, auth_token=auth_token,
				extra_instructions=extra_instructions,
				model_source=model_source,
				model_name=model_name,
				skill_names=skill_names,
				tool_confirmation_mode=tool_confirmation_mode,
				assistant_name=assistant_name,
				assistant_description=assistant_description,
				deployment_id=deployment_id,
			)
		except Exception as e:
			log_print(f"ChannelAgentPool: agent creation failed for {session_id[:16]}: {e}")
			return {"session_id": session_id, "error": f"Failed to create agent: {e}", "tool_calls": []}

		# Inject attachment descriptions into the message so the agent knows about them
		if attachments:
			message = _describe_attachments(message, attachments)

		try:
			response = await run_chat_agent(
				agent,
				message,
				user_id=user_id,
				session_id=session_id,
				backend_name=DEFAULT_BACKEND_NAME,
			)
		except Exception as e:
			log_print(f"ChannelAgentPool: agent run failed for {session_id[:16]}: {e}")
			return {"session_id": session_id, "error": str(e), "tool_calls": []}

		content = extract_chat_response_text(response, backend_name=DEFAULT_BACKEND_NAME)
		tool_calls = extract_chat_tool_calls(response, backend_name=DEFAULT_BACKEND_NAME)

		if is_chat_response_paused(response, backend_name=DEFAULT_BACKEND_NAME):
			pending_tool_approval = self._register_pending_tool_approval(
				session_id=session_id,
				deployment_id=deployment_id,
				user_id=user_id,
				message=message,
				run_response=response,
			)
			tool_name = pending_tool_approval.get("tool_name") or "the requested tool"
			notice = (
				f"Approval requested before running tool '{tool_name}'. "
				"An operator can approve or reject it from Assistant Deployments."
			)
			self._last_used[session_id] = time.time()
			return {
				"session_id": session_id,
				"response": notice,
				"tool_calls": tool_calls,
				"paused": True,
				"pending_tool_approval": pending_tool_approval,
			}

		# Detect model/infra errors returned as assistant content by the backend
		_ERROR_PATTERNS = ("not found", "status code:", "connection refused", "timed out", "unreachable")
		if content and not tool_calls and any(p in content.lower() for p in _ERROR_PATTERNS):
			return {"session_id": session_id, "error": content, "tool_calls": []}

		self._last_used[session_id] = time.time()
		return {"session_id": session_id, "response": content, "tool_calls": tool_calls}

	def _register_pending_tool_approval(
		self,
		*,
		session_id: str,
		deployment_id: Optional[str],
		user_id: Optional[str],
		message: str,
		run_response,
	) -> Dict[str, Any]:
		pending = get_pending_tool_approval(run_response, backend_name=DEFAULT_BACKEND_NAME) or {}
		approval_id = str(pending.get("approval_id") or f"tool_approval_{uuid.uuid4().hex[:10]}")
		row = {
			"id": approval_id,
			"deployment_id": deployment_id,
			"session_id": session_id,
			"user_id": user_id,
			"message": message,
			"created_at": datetime.now().isoformat(),
			"tool_name": str(pending.get("tool_name") or "tool"),
			"tool_args": pending.get("tool_args"),
			"approval_type": pending.get("approval_type") or "required",
			"pause_type": "confirmation",
			"run_response": run_response,
		}
		self._pending_tool_approvals[approval_id] = row
		return {k: v for k, v in row.items() if k not in {"run_response", "message"}}

	def get_pending_tool_approval(self, approval_id: str) -> Optional[Dict[str, Any]]:
		row = self._pending_tool_approvals.get(approval_id)
		if row is None:
			return None
		return {k: v for k, v in row.items() if k not in {"run_response", "message"}}

	async def resolve_pending_tool_approval(
		self,
		approval_id: str,
		*,
		approved: bool,
		note: Optional[str] = None,
	) -> Optional[Dict[str, Any]]:
		pending = self._pending_tool_approvals.get(approval_id)
		if pending is None:
			return None

		session_id = str(pending.get("session_id") or "")
		agent = self._agents.get(session_id)
		run_response = pending.get("run_response")
		user_id = pending.get("user_id")
		if agent is None:
			return {
				"approval_id": approval_id,
				"error": "The assistant session is no longer available.",
			}
		if run_response is None:
			return {
				"approval_id": approval_id,
				"error": "The paused tool approval is no longer available.",
			}

		try:
			continued = await continue_chat_run(
				agent,
				run_response=run_response,
				approved=approved,
				note=note,
				user_id=user_id,
				session_id=session_id,
				backend_name=DEFAULT_BACKEND_NAME,
			)
		except Exception as exc:
			log_print(f"ChannelAgentPool: continue_run failed for {session_id[:16]}: {exc}")
			return {
				"approval_id": approval_id,
				"error": str(exc),
			}

		self._pending_tool_approvals.pop(approval_id, None)
		self._last_used[session_id] = time.time()

		content = extract_chat_response_text(continued, backend_name=DEFAULT_BACKEND_NAME)
		tool_calls = extract_chat_tool_calls(continued, backend_name=DEFAULT_BACKEND_NAME)
		result = {
			"approval_id": approval_id,
			"approved": approved,
			"session_id": session_id,
			"response": content,
			"tool_calls": tool_calls,
		}
		if is_chat_response_paused(continued, backend_name=DEFAULT_BACKEND_NAME):
			next_pending = self._register_pending_tool_approval(
				session_id=session_id,
				deployment_id=str(pending.get("deployment_id") or "") or None,
				user_id=str(user_id or "") or None,
				message=str(pending.get("message") or ""),
				run_response=continued,
			)
			result["paused"] = True
			result["pending_tool_approval"] = next_pending
		return result

	async def _cleanup_loop(self):
		"""Periodically evict agents that haven't been used recently."""
		while True:
			await asyncio.sleep(300)  # check every 5 min
			now = time.time()
			expired = [sid for sid, ts in self._last_used.items()
					   if now - ts > self._idle_timeout]
			async with self._lock:
				for sid in expired:
					self._agents.pop(sid, None)
					self._agent_tks.pop(sid, None)
					self._agent_uids.pop(sid, None)
					self._agent_specs.pop(sid, None)
					self._agent_tokens.pop(sid, None)
					self._last_used.pop(sid, None)
					self._pending_tool_approvals = {
						approval_id: row
						for approval_id, row in self._pending_tool_approvals.items()
						if row.get("session_id") != sid
					}
				if expired:
					log_print(f"ChannelAgentPool: evicted {len(expired)} idle agents (pool size: {len(self._agents)})")
			# Clean up expired guest memory databases and workspaces
			if self._user_memory_db:
				try:
					self._user_memory_db.cleanup_expired_guests()
				except Exception:
					pass
			if self._ws_mgr:
				try:
					await self._ws_mgr.cleanup_guest_workspaces()
				except Exception:
					pass
			async with self._lock:
				if not self._agents:
					return  # stop loop when pool is empty

	@property
	def pool_size(self) -> int:
		return len(self._agents)


# ── API Routes ─────────────────────────────────────────────────

def setup_console_api(app: FastAPI, console_mgr: ConsoleAgentManager,
					  channel_pool: Optional[ChannelAgentPool] = None,
					  channel_cmd=None,
					  schema_code: Optional[str] = None):
	"""Register all console-related API routes on the FastAPI app."""
	console_mgr._fastapi_app = app

	class ConsoleStartRequest(BaseModel):
		model_source:       Optional[str]                    = None   # "ollama", "openai", "anthropic"
		model_name:         Optional[str]                    = None   # e.g. "mistral", "gpt-4o-mini"
		toolkit_names:      Optional[List[str]]              = None   # e.g. ["console_toolkit", "file_toolkit"]
		toolkit_args:       Optional[Dict[str, Dict[str, Any]]] = None   # e.g. {"file_toolkit": {"root": "."}}
		use_backend_memory: Optional[bool]                   = None   # deprecated, ignored
		memory_override:    Optional[Dict[str, Any]]         = None
		skill_names:        Optional[List[str]]              = None   # e.g. ["web-search", "git-assistant"]

	class ConsoleChatRequest(BaseModel):
		message:         str
		session_id:      Optional[str]  = None   # omit to create a new session
		include_context: bool           = True   # prepend current space state to the message

	@app.post("/console/start")
	async def console_start(req: Request, request: ConsoleStartRequest = ConsoleStartRequest()):
		user = getattr(req.state, 'user', None)
		user_id = user.id if user else None
		# Store auth token so assistant toolkits can operate on the caller's current space
		token = req.headers.get("authorization", "").removeprefix("Bearer ").strip()
		console_mgr._auth_token = token
		port = await console_mgr.start(
			request.model_source,
			request.model_name,
			request.toolkit_names,
			request.use_backend_memory,
			request.toolkit_args,
			skill_names=request.skill_names,
			memory_override=request.memory_override,
			user_id=user_id,
		)
		return {
			"port":          port,
			"status":        "running",
			"model_source":  console_mgr._model_source,
			"model_name":    console_mgr._model_name,
			"toolkit_names": console_mgr._toolkit_names,
			"memory_override": dict(console_mgr._current_runtime_console_state().get("memory") or {}),
			"options": console_mgr.current_console_options(),
		}

	@app.post("/console/stop")
	async def console_stop():
		await console_mgr.stop()
		return {"status": "stopped"}

	@app.post("/console/chat")
	async def console_chat(request: ConsoleChatRequest, req: Request):
		try:
			# Extract user identity from auth middleware
			user = getattr(req.state, 'user', None)
			user_id = user.id if user else None
			is_guest = user_id is None
			sender_id = user_id or "web_guest"
			sender_name = user.username if user else "Guest"
			session_id = request.session_id or str(uuid.uuid4())

			# ── Unified channel path: route /commands through ChannelCommandHandler ──
			if channel_cmd and request.message.strip().startswith("/"):
				# Auto-link web users who are already authenticated via HTTP auth
				if user:
					channel_cmd.ensure_linked("web", sender_id, user.username, user.id)
				cmd_response = await channel_cmd.handle(
					request.message, "web", sender_id, sender_name)
				if cmd_response is not None:
					# Toolkit change may require agent rebuild
					if request.message.strip().lower().startswith("/toolkit "):
						pool_session = f"web_{user_id}_{session_id}" if user_id else f"web_guest_{session_id}"
						if channel_pool:
							await channel_pool.evict(pool_session)
					return {
						"session_id": session_id,
						"response":   cmd_response,
						"command":    True,
						"tool_calls": [],
					}

			# Check if this browser-tab session has an active planner.
			ps = console_mgr._resolve_planner_state(user_id, request.session_id)
			if ps:
				ps.session_start = time.time()
				ps.turn_count = 0
				_token = req.headers.get("authorization", "").removeprefix("Bearer ").strip()
				result = await console_mgr._run_workflow_backed_console_turn(
					message=request.message,
					user_id=user_id,
					auth_token=_token or "",
					extra_instructions=[PLANNER_MODE_DIRECTIVE],
					workflow_name="Planner User Turn",
					sender_name=sender_name,
					include_context=request.include_context,
				)
				result["session_id"] = session_id
				return result

			# Multi-user mode: route through ChannelAgentPool for per-user memory
			if channel_pool:
				pool_session = f"web_{user_id}_{session_id}" if user_id else f"web_guest_{session_id}"
				token = req.headers.get("authorization", "").removeprefix("Bearer ").strip()
				result = await channel_pool.chat(
					message     = request.message,
					session_id  = pool_session,
					sender_name = sender_name,
					user_id     = user_id or f"guest_{session_id}",
					is_guest    = is_guest,
					auth_token  = token or None,
				)
				result["session_id"] = session_id
				return result

			# Fallback: singleton ConsoleAgentManager (no pool available)
			result = await console_mgr.chat(
				message         = request.message,
				session_id      = request.session_id,
				include_context = request.include_context,
			)
			return result
		except Exception as e:
			log_print(f"Console chat error: {type(e).__name__}: {e}")
			return {"error": str(e)}

	# ── Planner Routes ────────────────────────────────────────────

	@app.post("/console/planner/enable")
	async def console_planner_enable(request: Request):
		try:
			body = await request.json()
		except Exception:
			body = {}
		user = getattr(request.state, 'user', None)
		user_id = user.id if user else None
		session_id = body.pop("session_id", None)
		await console_mgr.enable_planner(body, user_id=user_id, session_id=session_id)
		return {"enabled": True, "port": console_mgr._port}

	@app.post("/console/planner/disable")
	async def console_planner_disable(request: Request):
		try:
			body = await request.json()
		except Exception:
			body = {}
		user = getattr(request.state, 'user', None)
		user_id = user.id if user else None
		session_id = body.get("session_id")
		console_mgr.disable_planner(user_id=user_id, session_id=session_id)
		return {"enabled": False}

	@app.post("/console/planner/status")
	async def console_planner_status(request: Request):
		try:
			body = await request.json()
		except Exception:
			body = {}
		user = getattr(request.state, 'user', None)
		user_id = user.id if user else None
		session_id = body.get("session_id")
		ps = console_mgr._resolve_planner_state(user_id, session_id)
		payload = console_mgr._planner_status_payload(ps)
		payload["active_planners"] = sum(1 for p in console_mgr._planners.values() if p.enabled)
		return payload

	@app.post("/console/planner/config")
	async def console_planner_config(request: Request):
		try:
			body = await request.json()
		except Exception:
			body = {}
		user = getattr(request.state, 'user', None)
		user_id = user.id if user else None
		session_id = body.get("session_id")
		ps = console_mgr._resolve_planner_state(user_id, session_id)
		if not ps:
			return {"error": "No active planner for this session"}
		if "timeout_s" in body:
			ps.timeout = max(10, int(body["timeout_s"]))
			log_print(f"Planner [{ps.key[:20]}] per-turn timeout → {ps.timeout}s")
		if "session_timeout_s" in body:
			ps.session_timeout = max(30, int(body["session_timeout_s"]))
			log_print(f"Planner [{ps.key[:20]}] session timeout → {ps.session_timeout}s")
		if "max_iterations" in body:
			ps.max_turns = max(1, int(body["max_iterations"]))
			log_print(f"Planner [{ps.key[:20]}] max iterations → {ps.max_turns}")
		if "max_autonomous_turns" in body and "max_iterations" not in body:
			ps.max_turns = max(1, int(body["max_autonomous_turns"]))
		if "debounce_ms" in body:
			ps.debounce = max(500, int(body["debounce_ms"])) / 1000.0
		if "profile" in body:
			profile_name = body["profile"]
			planner_cfg = console_mgr._config.get("planner", {})
			profiles = planner_cfg.get("profiles", {})
			profile = profiles.get(profile_name, {})
			if profile:
				instr_file = profile.get("instructions_file", "planner_instructions.txt")
				instr_path = os.path.join(os.path.dirname(console_mgr._config_path), instr_file)
				try:
					with open(instr_path) as f:
						ps.instructions = f.read().replace("{max_autonomous_turns}", str(ps.max_turns))
				except FileNotFoundError:
					log_print(f"Planner: instructions file not found: {instr_path}")
					return {"error": f"Profile '{profile_name}' instructions file not found: {instr_file}"}
				ps.profile = profile_name
				log_print(f"Planner [{ps.key[:20]}] profile → {profile_name}")
		return {
			"timeout_s": ps.timeout,
			"session_timeout_s": ps.session_timeout,
			"max_iterations": ps.max_turns,
			"debounce_s": ps.debounce,
			"profile": ps.profile,
		}

	@app.post("/console/planner/reset")
	async def console_planner_reset(request: Request):
		try:
			body = await request.json()
		except Exception:
			body = {}
		user = getattr(request.state, 'user', None)
		user_id = user.id if user else None
		session_id = body.get("session_id")
		console_mgr.reset_planner(user_id=user_id, session_id=session_id)
		return {"reset": True}

	@app.post("/console/planner/pause")
	async def console_planner_pause(request: Request):
		try:
			body = await request.json()
		except Exception:
			body = {}
		user = getattr(request.state, 'user', None)
		user_id = user.id if user else None
		session_id = body.get("session_id")
		duration_s = int(body.get("duration_s", 180))
		paused = console_mgr.pause_planner_for_manual_run(user_id=user_id, session_id=session_id, duration_s=duration_s)
		return {"paused": paused}

	@app.post("/console/planner/apply")
	async def console_planner_apply(request: dict, req: Request):
		wf_json = request.get("workflow")
		if not wf_json or "nodes" not in wf_json:
			raise HTTPException(status_code=400, detail="No valid workflow JSON")
		try:
			user = getattr(req.state, 'user', None)
			user_id = user.id if user else None
			session_id = request.get("session_id")
			auto_disable = bool(request.get("auto_disable"))
			if auto_disable:
				console_mgr.disable_planner(user_id=user_id, session_id=session_id)
			else:
				console_mgr.suppress_planner_added_reaction(user_id=user_id, session_id=session_id, duration_s=15)
			result = await console_mgr._apply_workflow_json(wf_json, user_id=user_id)
			return {
				"ok": True,
				"result": result,
				"planner_disabled": auto_disable,
				"validation": {
					"repaired": result.get("repaired", False),
					"repairs": result.get("repairs", []),
					"warnings": result.get("warnings", []),
				},
			}
		except Exception as e:
			raise HTTPException(status_code=400, detail=str(e))

	@app.post("/console/toolkits")
	async def console_list_toolkits():
		"""List all available toolkits that can be attached to the console agent."""
		import importlib
		_app_dir = os.path.dirname(os.path.abspath(__file__))
		_project_root = os.path.dirname(_app_dir)
		results = []
		for search_dir, prefix in [("app/toolkits", "toolkits"), ("contrib/toolkits", "contrib.toolkits")]:
			abs_dir = os.path.join(_project_root, search_dir)
			if not os.path.isdir(abs_dir):
				continue
			for fname in sorted(os.listdir(abs_dir)):
				if fname.startswith('_') or not fname.endswith('.py'):
					continue
				mod_name = fname[:-3]
				description = ""
				try:
					md = importlib.import_module(f"{prefix}.{mod_name}")
					for attr_name in dir(md):
						attr = getattr(md, attr_name)
						if isinstance(attr, type) and getattr(attr, '__toolkit__', False):
							description = (attr.__doc__ or "").strip().split('\n')[0]
							break
				except Exception:
					description = "(failed to load)"
				results.append({
					"name": mod_name,
					"description": description,
					"builtin": mod_name == "console_toolkit",
					"enabled": mod_name in console_mgr._toolkit_names,
				})
		return results

	@app.post("/console/context")
	async def console_context(req: Request):
		user = getattr(req.state, 'user', None)
		return await console_mgr.get_context(user_id=user.id if user else None)

	@app.post("/console/workflow")
	async def console_workflow(request: Request):
		try:
			body = await request.json()
		except Exception:
			body = {}
		user = getattr(request.state, 'user', None)
		user_id = user.id if user else None
		payload = console_mgr.build_workflow_export(
			include_planner=bool(body.get("include_planner")),
			user_id=user_id,
			session_id=body.get("session_id"),
		)
		payload["started"] = console_mgr._started
		payload["model_source"] = console_mgr._model_source
		payload["model_name"] = console_mgr._model_name
		payload["toolkit_names"] = list(console_mgr._toolkit_names or [])
		payload["skill_names"] = list(console_mgr._skill_names or [])
		return payload

	@app.post("/console/workflow/apply")
	async def console_workflow_apply(request: dict, req: Request):
		workflow = request.get("workflow")
		if not isinstance(workflow, dict):
			raise HTTPException(status_code=400, detail="No valid workflow JSON")
		user = getattr(req.state, 'user', None)
		user_id = user.id if user else None
		token = req.headers.get("authorization", "").removeprefix("Bearer ").strip()
		console_mgr._auth_token = token
		try:
			payload = await console_mgr.apply_workflow_import(workflow, user_id=user_id)
			return payload
		except ValueError as exc:
			raise HTTPException(status_code=400, detail=str(exc)) from exc

	@app.post("/console/status")
	async def console_status():
		return {
			"started":       console_mgr._started,
			"port":          console_mgr._port,
			"model_source":  console_mgr._model_source,
			"model_name":    console_mgr._model_name,
			"toolkit_names": console_mgr._toolkit_names,
			"sessions":      list(console_mgr._sessions.keys()),
		}

	# ── Memory Routes ─────────────────────────────────────────────

	@app.post("/console/memory/clear")
	async def console_memory_clear():
		"""Clear backend-managed assistant memory and in-memory session state."""
		console_mgr.clear_memory()
		return {"cleared": True}

	@app.websocket("/ws/console")
	async def console_ws(websocket: WebSocket):
		"""WebSocket for proactive messages from console agent to frontend."""
		await websocket.accept()
		session_id = websocket.query_params.get("session_id", "").strip() or None
		console_mgr._proactive_ws[websocket] = session_id
		try:
			while True:
				await websocket.receive_text()  # keep-alive
		except WebSocketDisconnect:
			console_mgr._proactive_ws.pop(websocket, None)
