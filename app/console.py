# console — Console Agent Manager
# Self-contained module: agent lifecycle, API routes, chat, proactive behavior.

import asyncio
import json
import os
import uuid

from   importlib                       import import_module
from   inspect                         import getmembers, ismethod
from   fastapi                         import FastAPI, WebSocket, WebSocketDisconnect
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

		# Prepend workspace context to the user message
		augmented = message
		if include_context:
			try:
				ctx = self.get_context()
				parts = []
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
		response = await self._agent.arun(augmented, session_id=session_id)

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

		return {
			"session_id": session_id,
			"response":   assistant_content,
			"tool_calls": tool_calls,
		}

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

		return {
			"context":          "\n".join(context_parts),
			"has_workflow":     has_workflow,
			"execution_active": len(active) > 0,
		}

	# ── Proactive ──────────────────────────────────────────────────

	async def push_proactive(self, content: str, severity: str = "info"):
		"""Push a proactive message to all connected console WebSocket clients."""
		msg = json.dumps({"type": "suggestion", "content": content, "severity": severity})
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
					"info"
				)

		self._event_bus.subscribe("MANAGER_WORKFLOW_ADDED", on_workflow_added)


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
			result = await console_mgr.chat(
				message         = request.message,
				session_id      = request.session_id,
				include_context = request.include_context,
			)
			return result
		except Exception as e:
			log_print(f"Console chat error: {type(e).__name__}: {e}")
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
