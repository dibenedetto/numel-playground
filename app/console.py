# console — Console Agent Manager
# Self-contained module: agent lifecycle, API routes, chat, proactive behavior.

import asyncio
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
from   toolkits.console_toolkit        import ConsoleToolkit
from   utils                           import add_middleware, log_print


_CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "console_agent.json")


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


# ── Manager ────────────────────────────────────────────────────

class ConsoleAgentManager:
	"""Manages the global console agent: lazy start, context gathering, chat sessions, proactive suggestions."""

	def __init__(self, workspace_mgr, event_bus: EventBus, port: int,
				 config_path: str = _CONFIG_PATH,
				 memory_store: Optional['MemoryStore'] = None):
		self._ws_mgr       = workspace_mgr
		self._event_bus     = event_bus
		self._port          = port
		self._config_path   = config_path
		self._memory        = memory_store
		self._agent         = None
		self._app           = None
		self._server        = None
		self._server_task   = None
		self._started       = False
		self._model_source  = None
		self._model_name    = None
		self._toolkit_names = []      # e.g. ["console_toolkit", "file_toolkit"]
		self._proactive_ws       : Set[WebSocket] = set()
		self._sessions           : Dict[str, List[dict]] = {}  # session_id → message history
		self._start_lock         = asyncio.Lock()               # prevents concurrent start/stop
		self._use_backend_memory = False                        # set during start()

		# ── Planner mode ──
		self._planner_enabled         = False
		self._planner_lock            = asyncio.Lock()
		self._planner_session_id      = None
		self._planner_turn_count      = 0
		self._planner_max_turns       = 10
		self._planner_timeout         = 120
		self._planner_session_timeout = 600
		self._planner_session_start   = 0.0
		self._planner_debounce        = 2.0                     # seconds
		self._planner_timer           = None                    # debounce handle
		self._planner_pending    : List[dict] = []              # queued events
		self._planner_active          = False                   # True while planner turn is running
		self._planner_subs       : List[str]  = []              # subscribed event type strings
		self._planner_instructions    = ""

	# ── Lifecycle ──────────────────────────────────────────────────

	async def start(self, model_source: Optional[str] = None,
					model_name: Optional[str] = None,
					toolkit_names: Optional[List[str]] = None,
					use_backend_memory: Optional[bool] = None,
					toolkit_args: Optional[Dict[str, Dict[str, Any]]] = None) -> int:
		"""Start (or restart) the console agent server. Returns the port.
		Concurrent calls are serialized — a second call waits for the first to finish."""

		async with self._start_lock:
			return await self._start_impl(model_source, model_name, toolkit_names, use_backend_memory, toolkit_args)

	async def _start_impl(self, model_source: Optional[str] = None,
						  model_name: Optional[str] = None,
						  toolkit_names: Optional[List[str]] = None,
						  use_backend_memory: Optional[bool] = None,
						  toolkit_args: Optional[Dict[str, Dict[str, Any]]] = None) -> int:
		_toolkit_args = toolkit_args or {}
		# Load config for defaults and instructions
		with open(self._config_path) as f:
			config = json.load(f)
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
			and toolkits == self._toolkit_names):
			return self._port

		# Restart if already running
		if self._started:
			await self.stop()

		model = _build_model(source, name)
		self._model_source  = source
		self._model_name    = name
		self._toolkit_names = toolkits

		# Build tools from all configured toolkits
		tools = []
		for tk_name in toolkits:
			if tk_name == "console_toolkit":
				# Built-in: pass workspace manager
				toolkit = ConsoleToolkit(self._ws_mgr)
				for attr_name in dir(toolkit):
					if attr_name.startswith('_'):
						continue
					method = getattr(toolkit, attr_name)
					if callable(method):
						tools.append(method)
			else:
				tools.extend(_load_toolkit(tk_name, _toolkit_args.get(tk_name)))

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
			db_path                 = os.path.join(os.path.dirname(self._config_path), "console_memory.db")
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
		self._agent = Agent(
			name                    = opts.get("name", "Numel Assistant"),
			model                   = model,
			description             = opts.get("description", ""),
			instructions            = opts.get("instructions", []),
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

	# ── Planner Mode ──────────────────────────────────────────────

	async def enable_planner(self, config: Optional[Dict[str, Any]] = None):
		"""Activate planner mode — subscribe to events and enable autonomous loop."""
		if self._planner_enabled:
			return
		cfg = config or {}
		log_print(f"Planner enable config: {cfg}")
		self._planner_max_turns      = cfg.get("max_iterations", cfg.get("max_autonomous_turns", 10))
		self._planner_debounce       = cfg.get("debounce_ms", 2000) / 1000.0
		self._planner_timeout        = cfg.get("timeout_s", 120)       # per-turn timeout
		self._planner_session_timeout = cfg.get("session_timeout_s", 600)  # total wall-clock timeout
		log_print(f"Planner timeout: {self._planner_timeout}s per-turn, {self._planner_session_timeout}s total, max {self._planner_max_turns} iterations")
		self._planner_turn_count     = 0
		self._planner_session_start  = time.time()
		self._planner_session_id = f"planner-{uuid.uuid4().hex[:8]}"
		self._planner_pending    = []

		# Resolve profile — if a profile name is given, merge its settings
		profile_name = cfg.get("profile", "")
		planner_cfg = self._config.get("planner", {})
		profiles = planner_cfg.get("profiles", {})
		profile = profiles.get(profile_name, {}) if profile_name else {}
		self._planner_profile = profile_name or "workflow"

		# Load planner instructions (profile overrides default)
		instr_file = profile.get("instructions_file") or cfg.get("instructions_file", "planner_instructions.txt")
		instr_path = os.path.join(os.path.dirname(self._config_path), instr_file)
		try:
			with open(instr_path) as f:
				self._planner_instructions = f.read().replace("{max_autonomous_turns}", str(self._planner_max_turns))
		except FileNotFoundError:
			self._planner_instructions = ""
			log_print(f"⚠️  Planner instructions file not found: {instr_path}")

		# Auto-add toolkits required by the profile
		required_toolkits = profile.get("toolkits", ["workspace_toolkit", "file_toolkit"])
		added = []
		for tk in required_toolkits:
			if tk not in self._toolkit_names:
				self._toolkit_names.append(tk)
				added.append(tk)
		if added:
			log_print(f"Planner: auto-adding {', '.join(added)}")
			# Force restart: stop first so the same-list comparison doesn't skip it
			if self._started:
				await self.stop()
				await self.start(
					model_source=self._model_source,
					model_name=self._model_name,
					toolkit_names=list(self._toolkit_names),
				)

		# Subscribe to events
		event_types = cfg.get("subscribe_events", [
			"workflow.completed", "workflow.failed", "manager.workflow_added"
		])
		self._planner_subs = []
		for et in event_types:
			self._event_bus.subscribe(et, self._on_planner_event)
			self._planner_subs.append(et)

		self._planner_enabled = True

		# Inject a short directive into the system prompt so the model uses tools
		if self._agent:
			if not hasattr(self, '_base_instructions'):
				self._base_instructions = list(self._agent.instructions or [])
			self._agent.instructions = self._base_instructions + [
				"You are in PLANNER MODE. When asked to build a workflow, output a complete workflow JSON inside a ```json code block. The system will load it automatically. Always include eval_flow nodes."
			]

		log_print(f"Planner mode enabled (events={event_types}, max_turns={self._planner_max_turns})")

	def disable_planner(self):
		"""Deactivate planner mode."""
		if not self._planner_enabled:
			return
		# Restore original system prompt
		if self._agent and hasattr(self, '_base_instructions'):
			self._agent.instructions = self._base_instructions

		for et in self._planner_subs:
			self._event_bus.unsubscribe(et, self._on_planner_event)
		self._planner_subs = []
		self._planner_enabled = False
		self._planner_active  = False
		self._planner_pending = []
		if self._planner_timer:
			self._planner_timer.cancel()
			self._planner_timer = None
		log_print("Planner mode disabled")

	async def _on_planner_event(self, event):
		"""EventBus callback — debounce and queue for processing."""
		evt_type = getattr(event, 'event_type', str(event))
		log_print(f"Planner event received: {evt_type} (enabled={self._planner_enabled}, active={self._planner_active})")
		if not self._planner_enabled:
			return
		# Ignore ALL events while the planner is actively processing (including post-tool events)
		if self._planner_active:
			return
		evt_data = {
			"type": evt_type,
			"data": getattr(event, 'data', {}),
		}
		self._planner_pending.append(evt_data)
		# Cancel existing debounce
		if self._planner_timer:
			self._planner_timer.cancel()
		# Schedule processing after debounce
		loop = asyncio.get_event_loop()
		self._planner_timer = loop.call_later(
			self._planner_debounce,
			lambda: asyncio.ensure_future(self._process_planner_events())
		)

	async def _process_planner_events(self):
		"""Process queued planner events — call agent with event context."""
		if not self._planner_enabled or not self._planner_pending:
			return
		if self._planner_active:
			return  # already processing
		if self._planner_turn_count >= self._planner_max_turns:
			await self.push_proactive(
				f"Planner reached max iterations ({self._planner_max_turns}). Send a message to continue.",
				"planner_paused"
			)
			return
		elapsed = time.time() - self._planner_session_start
		if elapsed >= self._planner_session_timeout:
			await self.push_proactive(
				f"Planner session timed out after {int(elapsed)}s (limit: {self._planner_session_timeout}s). Disabling planner.",
				"planner_error"
			)
			self.disable_planner()
			return

		self._planner_active = True
		try:
			# Notify frontend that planner is thinking
			await self.push_proactive("", "planner_thinking")

			events = self._planner_pending[:]
			self._planner_pending.clear()

			# Build synthetic message
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

			try:
				result = await asyncio.wait_for(
					self.chat(
						message,
						session_id=self._planner_session_id,
						include_context=True,
					),
					timeout=self._planner_timeout,
				)
				self._planner_turn_count += 1
				response = result.get("response", "")
				if response:
					await self.push_proactive(response, "planner_action")
				else:
					await self.push_proactive("Planner turn completed (no output).", "planner_action")
			except asyncio.TimeoutError:
				log_print(f"Planner turn timed out after {self._planner_timeout}s")
				await self.push_proactive(
					f"Planner turn timed out after {self._planner_timeout}s. Disabling planner.",
					"planner_error"
				)
				self.disable_planner()
			except Exception as e:
				log_print(f"Planner error: {e}")
				await self.push_proactive(f"Planner error: {e}", "planner_error")
		finally:
			self._planner_active = False
			# Always signal the frontend that the turn is done (safety net)
			await self.push_proactive("", "planner_done")

	def reset_planner(self):
		"""Reset planner turn count and session."""
		self._planner_turn_count = 0
		self._planner_session_id = f"planner-{uuid.uuid4().hex[:8]}"
		self._planner_pending = []

	# ── Chat ───────────────────────────────────────────────────────

	async def chat(self, message: str, session_id: Optional[str] = None,
				   include_context: bool = True) -> dict:
		"""Send a message and get a response. Uses agno's built-in session history.
		Returns { session_id, response, tool_calls }."""

		if not self._started or not self._agent:
			raise RuntimeError("Console agent is not running. Call /console/start first.")

		# Resolve or create session
		if not session_id:
			session_id = str(uuid.uuid4())

		# Reset planner turn count on user-initiated messages (not planner events)
		if self._planner_enabled and session_id != self._planner_session_id:
			self._planner_turn_count = 0

		# Prepend planner instructions + workspace context to the user message
		augmented = message

		if include_context:
			try:
				ctx = self.get_context()
				parts = []
				if self._planner_enabled and self._planner_instructions:
					parts.append(f"[Planner Instructions]\n{self._planner_instructions}")
				if ctx.get("context"):
					parts.append(f"[Current workspace state]\n{ctx['context']}")
				# Manual memory retrieval (only when not using backend)
				if self._memory and not self._use_backend_memory:
					mem_ctx = self._memory.get_context_for_query(message)
					if mem_ctx:
						parts.append(mem_ctx)
				if parts:
					augmented = "\n\n".join(parts) + f"\n\n[User message]\n{message}"
			except Exception:
				pass

		# Track turn count per session for memory persistence
		if session_id not in self._sessions:
			self._sessions[session_id] = 0
		self._sessions[session_id] += 1

		# Run the agent asynchronously with session_id for built-in history
		tool_names = [getattr(t, '__name__', getattr(t, 'name', str(t))) for t in (self._agent.tools or [])]
		log_print(f"Console chat: running agent (session={session_id[:8]}..., tools={tool_names}, msg={message[:60]}...)")
		response = await self._agent.arun(augmented, session_id=session_id)
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

	async def _apply_workflow_json(self, wf_json: dict) -> str:
		"""Apply a workflow JSON dict directly via the workspace manager (in-process, no HTTP)."""
		ws = self._ws_mgr.get_default_workspace()
		mgr = ws.manager
		names = list(mgr._workflows.keys())
		name = names[0] if names else "workspace"
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
		# Build a minimal Workflow pydantic model from the JSON
		from schema import Workflow
		wf_json.setdefault("type", "workflow")
		wf_json.setdefault("edges", [])
		wf = Workflow.model_validate(wf_json)
		await mgr.add(wf, name)
		# Notify frontend
		from event_bus import EventType as _ET, WorkflowEvent
		import uuid as _uuid
		from datetime import datetime as _dt, timezone as _tz
		ev = WorkflowEvent(
			event_id   = str(_uuid.uuid4()),
			event_type = _ET.WORKSPACE_CHANGED,
			timestamp  = _dt.now(_tz.utc).isoformat(),
			data       = {"name": name},
		)
		await self._event_bus.publish(ev)
		return f"ok: saved '{name}' ({len(wf_json.get('nodes', []))} nodes)"

	# ── Context ────────────────────────────────────────────────────

	def get_context(self) -> dict:
		"""Gather current workspace context for the console agent."""
		ws = self._ws_mgr.get_default_workspace()
		mgr = ws.manager

		context_parts = []
		has_workflow = False

		if mgr._workflows:
			has_workflow = True
			for wf_name, wf_data in mgr._workflows.items():
				wf = wf_data.get("workflow") if isinstance(wf_data, dict) else wf_data
				if wf is None:
					continue
				nodes = getattr(wf, 'nodes', None) or []
				edges = getattr(wf, 'edges', None) or []
				node_types = []
				for i, n in enumerate(nodes):
					if n is None:
						continue
					ntype = getattr(n, 'type', '?')
					nname = getattr(n, 'name', '') or ''
					node_types.append(f"[{i}] {ntype}" + (f" ({nname})" if nname else ""))

				context_parts.append(f"Workflow '{wf_name}': {len(nodes)} nodes, {len(edges)} edges")
				context_parts.append("Nodes: " + ", ".join(node_types[:20]))
				if len(node_types) > 20:
					context_parts.append(f"  ... and {len(node_types) - 20} more")
		else:
			context_parts.append("No workflow is currently loaded.")

		engine = ws.engine
		active = getattr(engine, '_active_executions', {}) if engine else {}
		if active:
			context_parts.append(f"Active executions: {len(active)}")
		else:
			context_parts.append("No active executions.")

		# Prepend planner instructions if active
		planner_ctx = ""
		if self._planner_enabled and self._planner_instructions:
			planner_ctx = f"[Planner Instructions]\n{self._planner_instructions}\n\n"

		return {
			"context":          planner_ctx + "\n".join(context_parts),
			"has_workflow":     has_workflow,
			"execution_active": len(active) > 0,
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
			ctx = self.get_context()
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
				 idle_timeout: float = 1800):
		self._config_path   = config_path
		self._ws_mgr        = workspace_mgr
		self._memory_store  = memory_store
		self._idle_timeout  = idle_timeout          # seconds before evicting idle agent
		self._agents: Dict[str, Agent]      = {}    # session_id → Agent
		self._last_used: Dict[str, float]   = {}    # session_id → timestamp
		self._lock = asyncio.Lock()
		self._cleanup_task: Optional[asyncio.Task] = None

	async def _get_or_create(self, session_id: str) -> Agent:
		"""Return (or lazily build) the Agent for this session."""
		async with self._lock:
			if session_id in self._agents:
				self._last_used[session_id] = time.time()
				return self._agents[session_id]

			agent = await self._build_agent()
			self._agents[session_id]   = agent
			self._last_used[session_id] = time.time()

			# Start periodic cleanup if not running
			if self._cleanup_task is None or self._cleanup_task.done():
				self._cleanup_task = asyncio.create_task(self._cleanup_loop())

			log_print(f"ChannelAgentPool: created agent for session {session_id[:16]} (pool size: {len(self._agents)})")
			return agent

	async def _build_agent(self) -> Agent:
		"""Build a lightweight Agent from console_agent.json defaults."""
		with open(self._config_path) as f:
			config = json.load(f)

		model_cfg = config.get("model", {})
		source    = model_cfg.get("source", "ollama")
		name      = model_cfg.get("name", "mistral")
		model     = _build_model(source, name)

		# Build tools
		cfg_toolkits = config.get("toolkits", ["console_toolkit"])
		tools = []
		for tk_name in cfg_toolkits:
			if tk_name == "console_toolkit" and self._ws_mgr:
				toolkit = ConsoleToolkit(self._ws_mgr)
				for attr_name in dir(toolkit):
					if attr_name.startswith('_'):
						continue
					method = getattr(toolkit, attr_name)
					if callable(method):
						tools.append(method)
			elif tk_name != "console_toolkit":
				tools.extend(_load_toolkit(tk_name))

		# Memory (backend if configured)
		mem_cfg     = config.get("memory", {})
		use_backend = mem_cfg.get("backend", True)
		db          = None
		if use_backend:
			from agno.db.sqlite import SqliteDb
			db_path = os.path.join(os.path.dirname(self._config_path), "console_memory.db")
			db = SqliteDb(db_file=db_path)

		opts = config.get("options", {})
		return Agent(
			name                    = opts.get("name", "Numel Assistant"),
			model                   = model,
			description             = opts.get("description", ""),
			instructions            = opts.get("instructions", []),
			markdown                = opts.get("markdown", True),
			tools                   = tools,
			db                      = db,
			enable_agentic_memory   = bool(db),
			add_memories_to_context = bool(db),
			search_session_history  = bool(db),
			num_history_sessions    = mem_cfg.get("session_history", 5) if db else None,
		)

	async def chat(self, message: str, session_id: str) -> dict:
		"""Send a message to the per-session agent. Returns {session_id, response, tool_calls}."""
		agent = await self._get_or_create(session_id)
		try:
			response = await agent.arun(message, session_id=session_id)
		except Exception as e:
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
					self._last_used.pop(sid, None)
				if expired:
					log_print(f"ChannelAgentPool: evicted {len(expired)} idle agents (pool size: {len(self._agents)})")
				if not self._agents:
					return  # stop loop when pool is empty

	@property
	def pool_size(self) -> int:
		return len(self._agents)


# ── API Routes ─────────────────────────────────────────────────

def setup_console_api(app: FastAPI, console_mgr: ConsoleAgentManager):
	"""Register all console-related API routes on the FastAPI app."""

	class ConsoleStartRequest(BaseModel):
		model_source:       Optional[str]                    = None   # "ollama", "openai", "anthropic"
		model_name:         Optional[str]                    = None   # e.g. "mistral", "gpt-4o-mini"
		toolkit_names:      Optional[List[str]]              = None   # e.g. ["console_toolkit", "file_toolkit"]
		toolkit_args:       Optional[Dict[str, Dict[str, Any]]] = None   # e.g. {"file_toolkit": {"root": "."}}
		use_backend_memory: Optional[bool]                   = None   # None = use console_agent.json default

	class ConsoleChatRequest(BaseModel):
		message:         str
		session_id:      Optional[str]  = None   # omit to create a new session
		include_context: bool           = True   # prepend workspace state to the message

	@app.post("/console/start")
	async def console_start(request: ConsoleStartRequest = ConsoleStartRequest()):
		port = await console_mgr.start(request.model_source, request.model_name, request.toolkit_names, request.use_backend_memory, request.toolkit_args)
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
	async def console_chat(request: ConsoleChatRequest):
		try:
			# Reset planner session clock on each user message
			if console_mgr._planner_enabled:
				console_mgr._planner_session_start = time.time()
				console_mgr._planner_turn_count = 0
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
		await console_mgr.enable_planner(body)
		return {"enabled": True, "port": console_mgr._port}

	@app.post("/console/planner/disable")
	async def console_planner_disable():
		console_mgr.disable_planner()
		return {"enabled": False}

	@app.post("/console/planner/status")
	async def console_planner_status():
		return {
			"enabled":    console_mgr._planner_enabled,
			"turn_count": console_mgr._planner_turn_count,
			"max_turns":  console_mgr._planner_max_turns,
			"session_id": console_mgr._planner_session_id,
			"subscribed_events": console_mgr._planner_subs,
		}

	@app.post("/console/planner/config")
	async def console_planner_config(request: Request):
		try:
			body = await request.json()
		except Exception:
			body = {}
		if "timeout_s" in body:
			console_mgr._planner_timeout = max(10, int(body["timeout_s"]))
			log_print(f"Planner per-turn timeout updated to {console_mgr._planner_timeout}s")
		if "session_timeout_s" in body:
			console_mgr._planner_session_timeout = max(30, int(body["session_timeout_s"]))
			log_print(f"Planner session timeout updated to {console_mgr._planner_session_timeout}s")
		if "max_iterations" in body:
			console_mgr._planner_max_turns = max(1, int(body["max_iterations"]))
			log_print(f"Planner max iterations updated to {console_mgr._planner_max_turns}")
		if "max_autonomous_turns" in body and "max_iterations" not in body:
			console_mgr._planner_max_turns = max(1, int(body["max_autonomous_turns"]))
		if "debounce_ms" in body:
			console_mgr._planner_debounce = max(500, int(body["debounce_ms"])) / 1000.0
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
						console_mgr._planner_instructions = f.read().replace(
							"{max_autonomous_turns}", str(console_mgr._planner_max_turns))
				except FileNotFoundError:
					pass
				console_mgr._planner_profile = profile_name
				# Inject updated instructions into agent
				if console_mgr._agent and hasattr(console_mgr, '_base_instructions'):
					console_mgr._agent.instructions = console_mgr._base_instructions + [console_mgr._planner_instructions]
				log_print(f"Planner profile switched to: {profile_name}")
		return {
			"timeout_s": console_mgr._planner_timeout,
			"session_timeout_s": console_mgr._planner_session_timeout,
			"max_iterations": console_mgr._planner_max_turns,
			"debounce_s": console_mgr._planner_debounce,
			"profile": getattr(console_mgr, '_planner_profile', 'workflow'),
		}

	@app.post("/console/planner/reset")
	async def console_planner_reset():
		console_mgr.reset_planner()
		return {"reset": True}

	@app.post("/console/planner/apply")
	async def console_planner_apply(request: dict):
		wf_json = request.get("workflow")
		if not wf_json or "nodes" not in wf_json:
			return {"error": "No valid workflow JSON"}
		try:
			result = await console_mgr._apply_workflow_json(wf_json)
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
	async def console_context():
		return console_mgr.get_context()

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
