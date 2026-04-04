# console — Console Agent Manager
# Self-contained module: agent lifecycle, API routes, chat, proactive behavior.

import asyncio
import httpx
import json
import os
import time
import uuid

from   importlib                       import import_module
from   inspect                         import getmembers, ismethod
from   fastapi                         import FastAPI, Request, WebSocket, WebSocketDisconnect
from   pydantic                        import BaseModel
from   typing                          import Any, Dict, List, Optional, Set

from   agno.agent                      import Agent
from   agno.models.ollama              import Ollama
from   agno.models.openai              import OpenAIChat
from   agno.os                         import AgentOS
from   agno.os.interfaces.agui         import AGUI

# Suppress agno's harmless SessionSummaryManager parse warnings (local models
# often return non-JSON for summary requests).  summary.py does
# `from agno.utils.log import log_warning` — a direct binding that our
# module-attr patch can't reach.  But log_warning internally calls
# `logger.warning()` through the shared global, so patching that method works.
import agno.utils.log as _agno_log
_SESSION_NOISE = frozenset([
    "Failed to parse cleaned JSON",
    "All parsing attempts failed",
    "Failed to parse session summary response",
])
_orig_logger_warning = _agno_log.logger.warning
def _logger_warning_filtered(msg, *args, **kwargs):
    if isinstance(msg, str) and any(msg.startswith(n) for n in _SESSION_NOISE):
        return
    _orig_logger_warning(msg, *args, **kwargs)
_agno_log.logger.warning = _logger_warning_filtered

from   event_bus                       import EventBus
from   memory                          import MemoryStore
from   runtime_settings                import get_runtime_settings
from   toolkits.console_toolkit        import ConsoleToolkit
from   utils                           import add_middleware, log_print


_CONFIG_PATH = str(get_runtime_settings().console_agent_config_path)


# ── Helpers ────────────────────────────────────────────────────

def _build_model(source: str, name: str):
	"""Instantiate an agno model from source/name strings."""
	if source == "ollama":
		return Ollama(id=name)
	elif source == "openai":
		# parallel_tool_calls=False prevents the AGUI streaming protocol from
		# breaking when the model would otherwise issue concurrent tool calls.
		return OpenAIChat(id=name, request_params={"parallel_tool_calls": False})
	elif source == "anthropic":
		from agno.models.anthropic import Claude
		return Claude(id=name)
	else:
		raise ValueError(f"Unsupported console agent model source: {source}")


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


def _load_toolkit(module_name: str, args: Optional[Dict[str, Any]] = None):
	"""Dynamically load a toolkit by module name.
	Returns list of public methods (tools), or empty list on failure.
	Uses the same resolution logic as impl_agno._build_toolkit."""
	module_name = module_name.replace("/", ".").replace("\\", ".")
	candidates = [module_name]
	if "." not in module_name:
		candidates.append(f"toolkits.{module_name}")
		candidates.append(f"contrib.toolkits.{module_name}")
	elif module_name.startswith("toolkits.") and not module_name.startswith("contrib."):
		candidates.append(f"contrib.{module_name}")

	md = None
	for candidate in candidates:
		try:
			md = import_module(candidate)
			break
		except (ImportError, ModuleNotFoundError):
			continue

	if md is None:
		log_print(f"⚠️  Console toolkit not found: {module_name} (tried: {', '.join(candidates)})")
		return []

	# Find toolkit class (__toolkit__ = True)
	toolkit_cls = None
	for attr_name in dir(md):
		attr = getattr(md, attr_name)
		if isinstance(attr, type) and getattr(attr, '__toolkit__', False):
			toolkit_cls = attr
			break

	# Fallback: first class with docstring
	if toolkit_cls is None:
		for attr_name in dir(md):
			attr = getattr(md, attr_name)
			if isinstance(attr, type) and attr.__module__ == md.__name__ and attr.__doc__:
				toolkit_cls = attr
				break

	if toolkit_cls is None:
		log_print(f"⚠️  No toolkit class found in module: {module_name}")
		return []

	try:
		import credentials as _creds
		resolved_args = _creds.resolve_dict(args or {})
		instance = toolkit_cls(**resolved_args)
	except Exception as e:
		log_print(f"⚠️  Toolkit instantiation failed: {toolkit_cls.__name__} ({e})")
		return []

	tools = []
	for name, method in getmembers(instance, predicate=ismethod):
		if not name.startswith('_'):
			tools.append(method)
	log_print(f"  Console toolkit loaded: {module_name} ({len(tools)} tools)")
	return tools


def _extract_tools(instance) -> list:
	"""Extract public methods from an already-instantiated toolkit."""
	return [getattr(instance, n) for n in dir(instance)
			if not n.startswith('_') and callable(getattr(instance, n))]


# ── Planner State (per-user) ────────────────────────────────────

class PlannerState:
	"""Per-session planner state.  One instance per (user, browser tab) pair."""

	__slots__ = (
		"key", "user_id", "enabled", "active", "session_id", "turn_count",
		"max_turns", "timeout", "session_timeout", "session_start",
		"debounce", "timer", "pending", "subs", "instructions", "profile",
	)

	def __init__(self, key: str, user_id: Optional[str] = None):
		self.key: str               = key
		self.user_id: Optional[str] = user_id
		self.enabled: bool          = False
		self.active: bool           = False
		self.session_id: str        = f"planner-{key[:16]}-{uuid.uuid4().hex[:8]}"
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

	def reset(self):
		self.turn_count = 0
		self.session_id = f"planner-{self.key[:16]}-{uuid.uuid4().hex[:8]}"
		self.pending.clear()


# ── Manager ────────────────────────────────────────────────────

class ConsoleAgentManager:
	"""Manages the global console agent: lazy start, context gathering, chat sessions, proactive suggestions."""

	def __init__(self, workspace_mgr, event_bus: EventBus, port: int,
				 config_path: str = _CONFIG_PATH,
				 memory_store: Optional['MemoryStore'] = None,
				 user_memory_db=None,
				 base_url: str = "http://localhost:11360",
				 internal_token: str = ""):
		self._ws_mgr       = workspace_mgr
		self._event_bus     = event_bus
		self._port          = port
		self._base_url      = base_url.rstrip("/")
		self._internal_token = internal_token
		self._config_path   = config_path
		self._memory        = memory_store
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
		self._skill_names   = None    # e.g. ["web-search", "git-assistant"]
		self._skill_mgr     = None    # set via set_skill_mgr()
		self._proactive_ws       : Set[WebSocket] = set()
		self._sessions           : Dict[str, List[dict]] = {}  # session_id → message history
		self._start_lock         = asyncio.Lock()               # prevents concurrent start/stop
		self._use_backend_memory = False                        # set during start()

		# ── Planner mode (per-session) ──
		# Keyed by planner_key (typically "user_{user_id}_{session_id}" or
		# "guest_{session_id}") so the same user in two tabs gets independent planners.
		self._resource_index: str = ""                 # cached toolkit+skill index for planner
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

	def refresh_resource_index(self) -> str:
		"""Rebuild and cache the toolkit+skill index. Returns the new index."""
		self._resource_index = self._build_resource_index()
		return self._resource_index

	def _build_resource_index(self) -> str:
		"""Build a compact index of available toolkits and skills for planner context."""
		import glob as _glob, re as _re
		lines = []

		# ── Toolkits (file-based, no import — avoids module cache staleness) ──
		app_dir      = os.path.dirname(os.path.abspath(__file__))
		project_root = os.path.dirname(app_dir)
		tk_entries = []
		for base_dir in [os.path.join(app_dir, "toolkits"),
		                  os.path.join(project_root, "contrib", "toolkits")]:
			for fpath in sorted(_glob.glob(os.path.join(base_dir, "*_toolkit.py"))):
				short = os.path.basename(fpath).replace(".py", "")
				doc   = ""
				try:
					text = open(fpath, encoding="utf-8").read(4096)
					if "__toolkit__" not in text:
						continue
					m = _re.search(r'"""(.+?)"""', text, _re.DOTALL)
					if m:
						doc = m.group(1).strip().split('\n')[0]
				except Exception:
					pass
				tk_entries.append(f"- {short} — {doc}" if doc else f"- {short}")
		if tk_entries:
			lines.append("## Available Toolkits")
			lines.extend(tk_entries)

		# ── Skills ──
		if self._skill_mgr:
			skills = self._skill_mgr.list()
			if skills:
				lines.append("\n## Available Skills")
				for sk in skills:
					req = ""
					toolkits_req = (sk.get("requires") or {}).get("toolkits", [])
					if toolkits_req:
						req = f" (requires: {', '.join(toolkits_req)})"
					lines.append(f"- {sk['name']} — {sk['description']}{req}")

		return "\n".join(lines)

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
					user_id: Optional[str] = None) -> int:
		"""Start (or restart) the console agent server. Returns the port.
		Concurrent calls are serialized — a second call waits for the first to finish."""

		async with self._start_lock:
			return await self._start_impl(model_source, model_name, toolkit_names, use_backend_memory, toolkit_args, skill_names=skill_names, user_id=user_id)

	async def _start_impl(self, model_source: Optional[str] = None,
						  model_name: Optional[str] = None,
						  toolkit_names: Optional[List[str]] = None,
						  use_backend_memory: Optional[bool] = None,
						  toolkit_args: Optional[Dict[str, Dict[str, Any]]] = None,
						  skill_names: Optional[List[str]] = None,
						  user_id: Optional[str] = None) -> int:
		self._current_user_id = user_id
		_toolkit_args = toolkit_args or {}
		# Load config for defaults and instructions
		import credentials as _creds
		config = _creds.load_json(self._config_path)
		self._config = config

		model_cfg = config.get("model", {})
		source = model_source or model_cfg.get("source", "ollama")
		name   = model_name   or model_cfg.get("name", "mistral")

		# Default toolkits: console_toolkit is always included
		cfg_toolkits = config.get("toolkits", ["console_toolkit"])
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
			and user_id == self._agent_user_id):
			return self._port

		# Restart if already running
		if self._started:
			await self.stop()

		model = _build_model(source, name)
		self._model_source  = source
		self._model_name    = name
		self._toolkit_names = toolkits
		self._skill_names   = skill_names
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
				tools.extend(_extract_tools(toolkit))
			elif tk_name == "channel_toolkit":
				from toolkits.channel_toolkit import ChannelToolkit
				toolkit = ChannelToolkit(channel_registry=getattr(self, '_channel_reg', None))
				tools.extend(_extract_tools(toolkit))
			else:
				tk_args = dict(_toolkit_args.get(tk_name) or {})
				if tk_name == "workspace_toolkit":
					tk_args.setdefault("base_url", self._base_url)
					tk_args.setdefault("internal_token", self._internal_token)
					tk_args.setdefault("user_id", user_id)
					tk_args.setdefault("local_app", self._fastapi_app)
					if getattr(self, '_auth_token', ''):
						tk_args.setdefault("auth_token", self._auth_token)
				tools.extend(_load_toolkit(tk_name, tk_args or None))

		log_print(f"Console agent tools: {[getattr(t, '__name__', str(t)) for t in tools]}")

		# Memory: backend (SqliteDb) or manual MemoryStore
		mem_cfg = config.get("memory", {})
		# use_backend_memory param overrides the config file value
		use_backend = use_backend_memory if use_backend_memory is not None else mem_cfg.get("backend", True)
		self._use_backend_memory = use_backend

		db                      = None
		enable_agentic_memory   = False
		add_memories_to_context = False
		search_session_history  = False
		num_history_sessions    = None
		session_summary_manager = None
		if use_backend:
			from agno.db.sqlite import SqliteDb
			if self._user_memory_db and user_id:
				db_path = self._user_memory_db.get_db_path(user_id)
			else:
				db_path = os.path.join(os.path.dirname(self._config_path), "console_memory.db")
			db                      = SqliteDb(db_file=db_path)
			enable_agentic_memory   = True
			add_memories_to_context = True
			search_session_history  = True
			num_history_sessions    = mem_cfg.get("session_history", 5)

			from agno.session.summary import SessionSummaryManager

			class _BgSessionSummaryManager(SessionSummaryManager):
				"""Fire-and-forget wrapper: runs the summary in a background task
				so it never blocks the response end-event."""
				async def acreate_session_summary(self, session, run_metrics=None):
					asyncio.get_event_loop().create_task(
						super().acreate_session_summary(session, run_metrics)
					)
					return None

			session_summary_manager = _BgSessionSummaryManager(model=model)
			log_print(f"Console agent: using backend memory ({db_path})")
		else:
			log_print("Console agent: using manual MemoryStore")

		# Build agent
		opts = config.get("options", {})
		instructions = list(opts.get("instructions", []))

		# Inject skill instructions (explicit names from frontend, or all enabled as fallback)
		if self._skill_mgr:
			if skill_names:
				skill_instructions = self._skill_mgr.get_instructions_for(skill_names)
			else:
				skill_instructions = self._skill_mgr.get_active_instructions()
			if skill_instructions:
				instructions.append("\n--- Active Skills ---")
				instructions.extend(skill_instructions)
				log_print(f"Console agent: injected {len(skill_instructions)} skill(s)")

		self._agent = Agent(
			name                    = opts.get("name", "Numel Assistant"),
			model                   = model,
			description             = opts.get("description", ""),
			instructions            = instructions,
			markdown                = opts.get("markdown", True),
			tools                   = tools,

			db                      = db,
			enable_agentic_memory   = enable_agentic_memory,
			add_memories_to_context = add_memories_to_context,
			search_session_history  = search_session_history,
			num_history_sessions    = num_history_sessions,
			session_summary_manager = session_summary_manager,
		)

		# Build AGUI app
		self._app = AgentOS(
			agents     = [self._agent],
			interfaces = [AGUI(agent=self._agent)]
		).get_app()
		add_middleware(self._app)

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
		"""Clear all agent memory: sessions, agno memories, and in-memory history."""
		# 1. Clear agno backend DB via public API (if agent was started with backend)
		if self._agent and getattr(self._agent, 'db', None):
			db = self._agent.db
			try:
				from agno.db.base import SessionType
				sessions = db.get_sessions(session_type=SessionType.AGENT) or []
				session_ids = [s.session_id for s in sessions]
				if session_ids:
					db.delete_sessions(session_ids)
			except Exception:
				pass
			try:
				if hasattr(db, 'clear_memories'):
					db.clear_memories()
			except Exception:
				pass
		# 2. Clear custom MemoryStore
		if self._memory:
			self._memory.clear()
		# 3. Clear in-memory session history
		self._sessions.clear()
		log_print("Console memory cleared")

	# ── Planner Mode (per-session) ────────────────────────────────

	async def enable_planner(self, config: Optional[Dict[str, Any]] = None,
							 user_id: Optional[str] = None,
							 session_id: Optional[str] = None):
		"""Activate planner mode for a specific session."""
		pkey = self._planner_key(user_id, session_id)
		# If this session already has an active planner, skip
		existing = self._planners.get(pkey)
		if existing and existing.enabled:
			return

		cfg = config or {}
		log_print(f"Planner enable [{pkey[:20]}] config: {cfg}")

		ps = PlannerState(key=pkey, user_id=user_id)
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
		self.refresh_resource_index()

		# Inject planner directive into the singleton agent's system prompt
		if self._agent:
			if not hasattr(self, '_base_instructions'):
				self._base_instructions = list(self._agent.instructions or [])
			self._agent.instructions = self._base_instructions + [
				"You are in PLANNER MODE. When asked to build a workflow, output a complete workflow JSON inside a ```json code block. The system will load it automatically. Always include eval_flow nodes."
			]

		log_print(f"Planner [{pkey[:20]}] enabled (events={event_types})")

	def disable_planner(self, user_id: Optional[str] = None,
						session_id: Optional[str] = None):
		"""Deactivate planner for a specific session, or all sessions if both are None."""
		if user_id is None and session_id is None:
			# Disable all planners
			keys = list(self._planners.keys())
			for k in keys:
				self._disable_planner_state(self._planners[k])
			self._planners.clear()
		else:
			pkey = self._planner_key(user_id, session_id)
			ps = self._planners.pop(pkey, None)
			if ps:
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
		ps.pending.clear()
		if ps.timer:
			ps.timer.cancel()
			ps.timer = None

	async def _on_planner_event(self, event):
		"""EventBus callback — dispatch event to ALL active planners with debounce."""
		evt_type = getattr(event, 'event_type', str(event))
		evt_data = {"type": evt_type, "data": getattr(event, 'data', {})}

		for ps in list(self._planners.values()):
			if not ps.enabled or ps.active:
				continue
			ps.pending.append(evt_data)
			# Cancel existing debounce for this planner
			if ps.timer:
				ps.timer.cancel()
			loop = asyncio.get_event_loop()
			pkey = ps.key
			ps.timer = loop.call_later(
				ps.debounce,
				lambda k=pkey: asyncio.ensure_future(self._process_planner_events(k))
			)

	async def _process_planner_events(self, planner_key: str):
		"""Process queued events for a specific planner session."""
		ps = self._planners.get(planner_key)
		if not ps or not ps.enabled or not ps.pending:
			return
		if ps.active:
			return

		if ps.turn_count >= ps.max_turns:
			await self.push_proactive(
				f"Planner reached max iterations ({ps.max_turns}). Send a message to continue.",
				"planner_paused"
			)
			return

		elapsed = time.time() - ps.session_start
		if elapsed >= ps.session_timeout:
			await self.push_proactive(
				f"Planner session timed out after {int(elapsed)}s (limit: {ps.session_timeout}s). Disabling.",
				"planner_error"
			)
			self.disable_planner(ps.user_id, ps.key.split("_", 1)[-1] if "_" in ps.key else None)
			return

		ps.active = True
		try:
			await self.push_proactive("", "planner_thinking")

			events = ps.pending[:]
			ps.pending.clear()

			event_summary = "\n".join(
				f"- {e['type']}: {json.dumps(e['data'], default=str)[:200]}"
				for e in events
			)
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
					# Use pool agent if available (per-user memory), else fall back to singleton
					if self._channel_pool and ps.user_id:
						# Augment message with planner context (pool agent has no built-in injection)
						augmented = message
						try:
							ctx = await self.get_context(user_id=ps.user_id)
							parts = []
							if ctx.get("context"):
								parts.append(f"[Current space state]\n{ctx['context']}")
							if parts:
								augmented = "\n\n".join(parts) + f"\n\n{message}"
						except Exception:
							pass
						_planner_directive = [
							"You are in PLANNER MODE. When asked to build a workflow, output a complete workflow JSON inside a ```json code block. The system will load it automatically. Always include eval_flow nodes."
						]
						pool_session = f"planner_{ps.key}"
						result = await asyncio.wait_for(
							self._channel_pool.chat(
								augmented, pool_session,
								toolkits=list(self._toolkit_names),
								sender_name="Planner",
								user_id=ps.user_id,
								extra_instructions=_planner_directive,
							),
							timeout=ps.timeout,
						)
					else:
						result = await asyncio.wait_for(
							self.chat(message, session_id=ps.session_id, include_context=True),
							timeout=ps.timeout,
						)
					ps.turn_count += 1
					response = result.get("response", "")
					if response:
						await self.push_proactive(response, "planner_action")
					else:
						await self.push_proactive("Planner turn completed (no output).", "planner_action")
				except asyncio.TimeoutError:
					log_print(f"Planner [{planner_key[:20]}] timed out after {ps.timeout}s")
					await self.push_proactive(
						f"Planner turn timed out after {ps.timeout}s. Disabling.",
						"planner_error"
					)
					self.disable_planner(ps.user_id)
				except Exception as e:
					log_print(f"Planner [{planner_key[:20]}] error: {e}")
					await self.push_proactive(f"Planner error: {e}", "planner_error")
		finally:
			ps.active = False
			await self.push_proactive("", "planner_done")

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
		"""Send a message and get a response. Uses agno's built-in session history.
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

		# Prepend planner instructions + workspace context to the user message
		augmented = message

		if include_context:
			try:
				ctx = await self.get_context()
				parts = []
				if self._planner_enabled and self._planner_instructions:
					parts.append(f"[Planner Instructions]\n{self._planner_instructions}")
				if ctx.get("context"):
					parts.append(f"[Current space state]\n{ctx['context']}")
				# Manual memory retrieval (only when not using backend)
				if self._memory and not self._use_backend_memory:
					mem_ctx = self._memory.get_context_for_query(message)
					if mem_ctx:
						parts.append(mem_ctx)
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
			response = await self._agent.arun(augmented, session_id=session_id)
		except Exception as e:
			log_print(f"ERROR    Error in Agent run: {e}")
			return {"session_id": session_id, "error": str(e), "tool_calls": []}
		log_print(f"Console chat: agent done (tools={len(response.tools or [])} msgs={len(response.messages or [])})")

		# Extract the assistant response
		assistant_content = ""
		tool_calls = []

		# Try response.content first (the main output)
		if response and response.content:
			assistant_content = response.get_content_as_string() if hasattr(response, 'get_content_as_string') else str(response.content)

		# Extract tool call info from messages
		if response and response.messages:
			for msg in response.messages:
				role = getattr(msg, 'role', None)
				if role == "tool":
					tool_calls.append({
						"name": getattr(msg, 'tool_name', None) or getattr(msg, 'tool_call_id', None),
						"result": (msg.content[:200] if msg.content else None) if hasattr(msg, 'content') else None,
					})
				# Fallback: if content is empty, grab from last assistant message
				if not assistant_content and role == "assistant" and getattr(msg, 'content', None):
					assistant_content = msg.content

		# Extract tool calls from response.tools if available
		if response and response.tools and not tool_calls:
			for tc in response.tools:
				tool_calls.append({
					"name": getattr(tc, 'tool_name', None) or getattr(tc, 'name', None),
					"result": None,
				})

		# Planner fallback: if the model produced JSON instead of calling tools, apply it
		if self._planner_enabled and assistant_content and not tool_calls:
			wf_json = self._extract_workflow_json(assistant_content)
			if wf_json:
				try:
					result = await self._apply_workflow_json(wf_json)
					log_print(f"Planner: auto-applied workflow JSON ({len(wf_json.get('nodes',[]))} nodes) — {result}")
					tool_calls.append({"name": "replace_workflow", "result": result})
				except Exception as e:
					log_print(f"Planner: auto-apply failed: {e}")

		# Save conversation to manual MemoryStore (only when not using backend, every 3 turns)
		turn_count = self._sessions.get(session_id, 0)
		if self._memory and not self._use_backend_memory and turn_count >= 3 and turn_count % 3 == 0:
			try:
				self._memory.add(
					content=f"User: {message}\nAssistant: {assistant_content[:500]}",
					type="conversation",
					metadata={"session_id": session_id},
				)
			except Exception:
				pass

		# Detect model/infra errors returned as assistant content by agno
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

	async def _apply_workflow_json(self, wf_json: dict, user_id: Optional[str] = None) -> str:
		"""Apply a workflow JSON dict through the current-workflow HTTP routes."""
		acting_user_id = user_id or self._current_user_id
		# Normalize alternate node formats the model may produce
		for n in wf_json.get("nodes", []):
			if "extra" not in n:
				x = n.pop("x", 0)
				y = n.pop("y", 0)
				label = n.pop("name", n.get("type", ""))
				n["extra"] = {"pos": [x, y], "name": label}
			# Merge "fields" dict into the node body
			fields = n.pop("fields", None)
			if fields and isinstance(fields, dict):
				n.update(fields)
		wf_json.setdefault("type", "workflow")
		wf_json.setdefault("edges", [])
		resp = await self._post_json("/workflow/save", {"workflow": wf_json}, user_id=acting_user_id)
		name = resp.get("name") or "Current Workflow"
		return f"ok: saved '{name}' ({len(wf_json.get('nodes', []))} nodes)"

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

		# Prepend planner instructions if active
		planner_ctx = ""
		if self._planner_enabled and self._planner_instructions:
			planner_ctx = f"[Planner Instructions]\n{self._planner_instructions}\n\n"
			if self._resource_index:
				planner_ctx += f"[Available Resources]\n{self._resource_index}\n\n"
			# Include generation prompt (node catalog + JSON schema) so the planner can build workflows
			build_prompt = getattr(getattr(self, '_fastapi_app', None), 'state', None)
			build_prompt = getattr(build_prompt, 'build_generation_prompt', None) if build_prompt else None
			if build_prompt:
				try:
					gen_prompt = build_prompt()
					log_print(f"Planner: injecting node catalog ({len(gen_prompt)} chars)")
					planner_ctx += f"[Node Catalog & JSON Format]\n{gen_prompt}\n\n"
				except Exception as e:
					log_print(f"Planner: node catalog build failed: {e}")
			else:
				log_print(f"Planner: no build_generation_prompt (fastapi_app={self._fastapi_app is not None})")

		return {
			"context":          planner_ctx + "\n".join(context_parts),
			"has_workflow":     has_workflow,
			"execution_active": execution_active,
		}

	# ── Proactive ──────────────────────────────────────────────────

	async def push_proactive(self, content: str, msg_type: str = "suggestion", severity: str = "info"):
		"""Push a proactive message to all connected console WebSocket clients."""
		msg = json.dumps({"type": msg_type, "content": content, "severity": severity})
		disconnected = set()
		for ws in self._proactive_ws:
			try:
				await ws.send_text(msg)
			except Exception:
				disconnected.add(ws)
		self._proactive_ws -= disconnected

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
	"""Manages per-session Agent instances for channel message handling."""

	def __init__(self, config_path: str = _CONFIG_PATH,
				 workspace_mgr=None, memory_store=None,
				 user_memory_db=None, channel_registry=None,
				 idle_timeout: float = 1800,
				 base_url: str = "http://localhost:11360",
				 internal_token: str = "",
				 fastapi_app=None):
		self._config_path    = config_path
		self._ws_mgr         = workspace_mgr
		self._memory_store   = memory_store
		self._user_memory_db = user_memory_db       # UserMemoryDB for per-user isolation
		self._channel_reg    = channel_registry      # ChannelRegistry for cross-channel messaging
		self._idle_timeout   = idle_timeout          # seconds before evicting idle agent
		self._base_url       = base_url.rstrip("/")
		self._internal_token = internal_token
		self._fastapi_app    = fastapi_app
		self._skill_mgr      = None                  # set via set_skill_mgr()
		self._agents: Dict[str, Agent]      = {}    # session_id → Agent
		self._agent_tks: Dict[str, List[str]] = {}  # session_id → toolkit names used at build
		self._agent_uids: Dict[str, str]    = {}    # session_id → user_id used at build
		self._agent_tokens: Dict[str, str]  = {}    # session_id → auth token
		self._last_used: Dict[str, float]   = {}    # session_id → timestamp
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
							 extra_instructions: Optional[List[str]] = None) -> Agent:
		"""Return (or lazily build) the Agent for this session."""
		async with self._lock:
			# Update stored token if a fresh one is provided
			if auth_token:
				self._agent_tokens[session_id] = auth_token

			if session_id in self._agents:
				# Rebuild if toolkit list or user identity changed
				tk_changed = toolkits is not None and sorted(toolkits) != sorted(self._agent_tks.get(session_id, []))
				uid_changed = user_id is not None and user_id != self._agent_uids.get(session_id)
				if tk_changed or uid_changed:
					self._agents.pop(session_id, None)
					self._agent_tks.pop(session_id, None)
					self._agent_uids.pop(session_id, None)
				else:
					self._last_used[session_id] = time.time()
					return self._agents[session_id]

			token = self._agent_tokens.get(session_id, "")
			agent = await self._build_agent(
				toolkits=toolkits, sender_name=sender_name,
				user_id=user_id, is_guest=is_guest, auth_token=token,
				extra_instructions=extra_instructions)
			self._agents[session_id]   = agent
			self._agent_tks[session_id] = list(toolkits) if toolkits else []
			self._agent_uids[session_id] = user_id or session_id
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
			self._agent_tokens.pop(session_id, None)
			self._last_used.pop(session_id, None)

	async def _build_agent(self, toolkits: Optional[List[str]] = None,
						   sender_name: Optional[str] = None,
						   user_id: Optional[str] = None,
						   is_guest: bool = False,
						   auth_token: str = "",
						   extra_instructions: Optional[List[str]] = None) -> Agent:
		"""Build a lightweight Agent from console_agent.json defaults."""
		import credentials as _creds
		config = _creds.load_json(self._config_path)

		model_cfg = config.get("model", {})
		source    = model_cfg.get("source", "ollama")
		name      = model_cfg.get("name", "mistral")
		model     = _build_model(source, name)

		# Build tools — use per-user toolkit list if provided, else config defaults
		tk_names = toolkits if toolkits is not None else config.get("toolkits", ["console_toolkit"])
		# Always include console_toolkit if workspace is available
		if self._ws_mgr and "console_toolkit" not in tk_names:
			tk_names = ["console_toolkit"] + list(tk_names)

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
				tools.extend(_extract_tools(toolkit))
			elif tk_name == "channel_toolkit" and self._channel_reg:
				from toolkits.channel_toolkit import ChannelToolkit
				toolkit = ChannelToolkit(channel_registry=self._channel_reg)
				tools.extend(_extract_tools(toolkit))
			elif tk_name not in _INJECTED:
				tk_args = {}
				if tk_name == "workspace_toolkit" and auth_token:
					tk_args["auth_token"] = auth_token
				if tk_name == "workspace_toolkit":
					tk_args.setdefault("base_url", self._base_url)
					tk_args.setdefault("internal_token", self._internal_token)
					tk_args.setdefault("user_id", user_id)
					tk_args.setdefault("local_app", self._fastapi_app)
				tools.extend(_load_toolkit(tk_name, tk_args or None))

		# Memory — per-user isolation via UserMemoryDB
		mem_cfg     = config.get("memory", {})
		use_backend = mem_cfg.get("backend", True)
		db          = None
		if use_backend:
			from agno.db.sqlite import SqliteDb
			if self._user_memory_db and user_id:
				db_path = self._user_memory_db.get_db_path(user_id, is_guest=is_guest)
			else:
				# Fallback: shared db (no user isolation available)
				db_path = os.path.join(os.path.dirname(self._config_path), "console_memory.db")
			db = SqliteDb(db_file=db_path)
			log_print(f"ChannelAgentPool: memory db → {os.path.basename(db_path)}")

		opts = config.get("options", {})
		instructions = list(opts.get("instructions", []))
		if sender_name:
			instructions.insert(0, f"You are chatting with {sender_name}.")

		# Inject skill instructions (all enabled — channels don't send explicit skill_names)
		if self._skill_mgr:
			skill_instructions = self._skill_mgr.get_active_instructions()
			if skill_instructions:
				instructions.append("\n--- Active Skills ---")
				instructions.extend(skill_instructions)

		# Inject extra instructions (e.g. planner directive)
		if extra_instructions:
			instructions.extend(extra_instructions)

		return Agent(
			name                    = opts.get("name", "Numel Assistant"),
			model                   = model,
			description             = opts.get("description", ""),
			instructions            = instructions,
			markdown                = opts.get("markdown", True),
			tools                   = tools,
			db                      = db,
			enable_agentic_memory   = bool(db),
			add_memories_to_context = bool(db),
			search_session_history  = bool(db),
			num_history_sessions    = mem_cfg.get("session_history", 5) if db else None,
		)

	async def chat(self, message: str, session_id: str,
				   toolkits: Optional[List[str]] = None,
				   sender_name: Optional[str] = None,
				   user_id: Optional[str] = None,
				   is_guest: bool = False,
				   auth_token: Optional[str] = None,
				   attachments: Optional[list] = None,
				   extra_instructions: Optional[List[str]] = None) -> dict:
		"""Send a message to the per-session agent. Returns {session_id, response, tool_calls}.
		attachments: list of Attachment objects from ChannelMessage (described in prompt)."""
		try:
			agent = await self._get_or_create(
				session_id, toolkits=toolkits, sender_name=sender_name,
				user_id=user_id, is_guest=is_guest, auth_token=auth_token,
				extra_instructions=extra_instructions)
		except Exception as e:
			log_print(f"ChannelAgentPool: agent creation failed for {session_id[:16]}: {e}")
			return {"session_id": session_id, "error": f"Failed to create agent: {e}", "tool_calls": []}

		# Inject attachment descriptions into the message so the agent knows about them
		if attachments:
			message = _describe_attachments(message, attachments)

		try:
			response = await agent.arun(message, user_id=user_id, session_id=session_id)
		except Exception as e:
			log_print(f"ChannelAgentPool: agent run failed for {session_id[:16]}: {e}")
			return {"session_id": session_id, "error": str(e), "tool_calls": []}

		# Extract response text
		content = ""
		if response and response.content:
			content = response.get_content_as_string() if hasattr(response, 'get_content_as_string') else str(response.content)
		if not content and response and response.messages:
			for msg in reversed(response.messages):
				if getattr(msg, 'role', None) == "assistant" and getattr(msg, 'content', None):
					content = msg.content
					break

		tool_calls = []
		if response and response.messages:
			for msg in response.messages:
				if getattr(msg, 'role', None) == "tool":
					tool_calls.append({
						"name":   getattr(msg, 'tool_name', None) or getattr(msg, 'tool_call_id', None),
						"result": (msg.content[:200] if msg.content else None) if hasattr(msg, 'content') else None,
					})

		# Detect model/infra errors returned as assistant content by agno
		_ERROR_PATTERNS = ("not found", "status code:", "connection refused", "timed out", "unreachable")
		if content and not tool_calls and any(p in content.lower() for p in _ERROR_PATTERNS):
			return {"session_id": session_id, "error": content, "tool_calls": []}

		self._last_used[session_id] = time.time()
		return {"session_id": session_id, "response": content, "tool_calls": tool_calls}

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
					self._agent_tokens.pop(sid, None)
					self._last_used.pop(sid, None)
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
		use_backend_memory: Optional[bool]                   = None   # None = use console_agent.json default
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
		port = await console_mgr.start(request.model_source, request.model_name, request.toolkit_names, request.use_backend_memory, request.toolkit_args, skill_names=request.skill_names, user_id=user_id)
		return {
			"port":          port,
			"status":        "running",
			"model_source":  console_mgr._model_source,
			"model_name":    console_mgr._model_name,
			"toolkit_names": console_mgr._toolkit_names,
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

			# Check if this user has an active planner (any session)
			ps = None
			for _ps in console_mgr._planners.values():
				if _ps.enabled and _ps.user_id == (user_id or "anon"):
					ps = _ps
					break
			if ps:
				ps.session_start = time.time()
				ps.turn_count = 0
				# Use pool agent for planner chat (per-user memory)
				if channel_pool and user_id:
					# Augment message with planner context (pool agent has no built-in injection)
					augmented = request.message
					try:
						ctx = await console_mgr.get_context(user_id=user_id)
						parts = []
						if ctx.get("context"):
							parts.append(f"[Current space state]\n{ctx['context']}")
						if parts:
							augmented = "\n\n".join(parts) + f"\n\n[User message]\n{request.message}"
					except Exception as e:
						log_print(f"Planner context augmentation failed: {e}")
					log_print(f"Planner augmented msg length: {len(augmented)} chars, starts: {augmented[:200]}...")
					pool_session = f"planner_{ps.key}"
					_token = req.headers.get("authorization", "").removeprefix("Bearer ").strip()
					_planner_directive = [
						"You are in PLANNER MODE. When asked to build a workflow, output a complete workflow JSON inside a ```json code block. The system will load it automatically. Always include eval_flow nodes."
					]
					result = await channel_pool.chat(
						message     = augmented,
						session_id  = pool_session,
						toolkits    = list(console_mgr._toolkit_names),
						sender_name = sender_name,
						user_id     = user_id,
						auth_token  = _token or None,
						extra_instructions = _planner_directive,
					)
				else:
					result = await console_mgr.chat(
						message         = request.message,
						session_id      = ps.session_id,
						include_context = request.include_context,
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
		pkey = console_mgr._planner_key(user_id, session_id)
		ps = console_mgr._planners.get(pkey)
		return {
			"enabled":    ps.enabled if ps else False,
			"turn_count": ps.turn_count if ps else 0,
			"max_turns":  ps.max_turns if ps else 10,
			"session_id": ps.session_id if ps else None,
			"subscribed_events": ps.subs if ps else [],
			"active_planners": sum(1 for p in console_mgr._planners.values() if p.enabled),
		}

	@app.post("/console/planner/refresh-resources")
	async def console_planner_refresh_resources():
		index = console_mgr.refresh_resource_index()
		return {"ok": True, "length": len(index)}

	@app.post("/console/planner/config")
	async def console_planner_config(request: Request):
		try:
			body = await request.json()
		except Exception:
			body = {}
		user = getattr(request.state, 'user', None)
		user_id = user.id if user else None
		session_id = body.get("session_id")
		pkey = console_mgr._planner_key(user_id, session_id)
		ps = console_mgr._planners.get(pkey)
		if not ps:
			return {"error": "No active planner for this session"}
		if "timeout_s" in body:
			ps.timeout = max(10, int(body["timeout_s"]))
			log_print(f"Planner [{pkey[:20]}] per-turn timeout → {ps.timeout}s")
		if "session_timeout_s" in body:
			ps.session_timeout = max(30, int(body["session_timeout_s"]))
			log_print(f"Planner [{pkey[:20]}] session timeout → {ps.session_timeout}s")
		if "max_iterations" in body:
			ps.max_turns = max(1, int(body["max_iterations"]))
			log_print(f"Planner [{pkey[:20]}] max iterations → {ps.max_turns}")
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
				log_print(f"Planner [{pkey[:20]}] profile → {profile_name}")
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

	@app.post("/console/planner/apply")
	async def console_planner_apply(request: dict, req: Request):
		wf_json = request.get("workflow")
		if not wf_json or "nodes" not in wf_json:
			return {"error": "No valid workflow JSON"}
		try:
			user = getattr(req.state, 'user', None)
			result = await console_mgr._apply_workflow_json(wf_json, user_id=user.id if user else None)
			return {"ok": True, "result": result}
		except Exception as e:
			return {"error": str(e)}

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

	@app.post("/console/memory/search")
	async def console_memory_search(request: dict):
		"""Search agent memory."""
		if not console_mgr._memory:
			return {"error": "memory not available"}
		query       = request.get("query", "")
		n_results   = request.get("n_results", 5)
		type_filter = request.get("type", None)
		results = console_mgr._memory.search(query, n_results, type_filter)
		return [{"entry": r.entry.model_dump(), "score": r.score} for r in results]

	@app.post("/console/memory/add")
	async def console_memory_add(request: dict):
		"""Manually add a memory."""
		if not console_mgr._memory:
			return {"error": "memory not available"}
		mem_id = console_mgr._memory.add(
			content    = request.get("content", ""),
			type       = request.get("type", "general"),
			metadata   = request.get("metadata", {}),
			importance = request.get("importance", 0.5),
		)
		return {"id": mem_id}

	@app.post("/console/memory/recent")
	async def console_memory_recent(request: dict):
		"""Get recent memories."""
		if not console_mgr._memory:
			return {"error": "memory not available"}
		n           = request.get("n", 10)
		type_filter = request.get("type", None)
		entries = console_mgr._memory.get_recent(n, type_filter)
		return [e.model_dump() for e in entries]

	@app.post("/console/memory/delete")
	async def console_memory_delete(request: dict):
		"""Delete a memory entry."""
		if not console_mgr._memory:
			return {"error": "memory not available"}
		return {"deleted": console_mgr._memory.delete(request.get("id", ""))}

	@app.post("/console/memory/clear")
	async def console_memory_clear():
		"""Clear all agent memory: sessions, agno memories, and in-memory history."""
		console_mgr.clear_memory()
		return {"cleared": True}

	@app.post("/console/memory/stats")
	async def console_memory_stats():
		"""Get memory store statistics."""
		if not console_mgr._memory:
			return {"error": "memory not available"}
		return console_mgr._memory.get_stats()

	@app.websocket("/ws/console")
	async def console_ws(websocket: WebSocket):
		"""WebSocket for proactive messages from console agent to frontend."""
		await websocket.accept()
		console_mgr._proactive_ws.add(websocket)
		try:
			while True:
				await websocket.receive_text()  # keep-alive
		except WebSocketDisconnect:
			console_mgr._proactive_ws.discard(websocket)
