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

from   event_bus                       import EventBus
from   toolkits.console_toolkit        import ConsoleToolkit
from   utils                           import add_middleware, log_print


_CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "console_agent.json")


# ── Helpers ────────────────────────────────────────────────────

def _build_model(source: str, name: str):
	"""Instantiate an agno model from source/name strings."""
	if source == "ollama":
		return Ollama(id=name)
	elif source == "openai":
		return OpenAIChat(id=name)
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
		instance = toolkit_cls(**(args or {}))
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
				 config_path: str = _CONFIG_PATH):
		self._ws_mgr       = workspace_mgr
		self._event_bus     = event_bus
		self._port          = port
		self._config_path   = config_path
		self._agent         = None
		self._app           = None
		self._server        = None
		self._server_task   = None
		self._started       = False
		self._model_source  = None
		self._model_name    = None
		self._toolkit_names = []      # e.g. ["console_toolkit", "file_toolkit"]
		self._proactive_ws  : Set[WebSocket] = set()
		self._sessions      : Dict[str, List[dict]] = {}  # session_id → message history

	# ── Lifecycle ──────────────────────────────────────────────────

	async def start(self, model_source: Optional[str] = None,
					model_name: Optional[str] = None,
					toolkit_names: Optional[List[str]] = None) -> int:
		"""Start (or restart) the console agent server. Returns the port."""

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
				tools.extend(_load_toolkit(tk_name))

		# Build agent
		opts = config.get("options", {})
		self._agent = Agent(
			name         = opts.get("name", "Numel Assistant"),
			model        = model,
			description  = opts.get("description", ""),
			instructions = opts.get("instructions", []),
			markdown     = opts.get("markdown", True),
			tools        = tools,
		)

		# Build AGUI app
		self._app = AgentOS(
			agents     = [self._agent],
			interfaces = [AGUI(agent=self._agent)]
		).get_app()
		add_middleware(self._app)

		# Start uvicorn server
		import uvicorn
		uv_config = uvicorn.Config(self._app, host="0.0.0.0", port=self._port)
		self._server = uvicorn.Server(uv_config)
		self._server_task = asyncio.create_task(self._server.serve())

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

	# ── Chat ───────────────────────────────────────────────────────

	async def chat(self, message: str, session_id: Optional[str] = None,
				   include_context: bool = True) -> dict:
		"""Send a message and get a response. Maintains session history.
		Returns { session_id, response, tool_calls }."""

		if not self._started or not self._agent:
			raise RuntimeError("Console agent is not running. Call /console/start first.")

		# Resolve or create session
		if not session_id:
			session_id = str(uuid.uuid4())
		if session_id not in self._sessions:
			self._sessions[session_id] = []
		history = self._sessions[session_id]

		# Optionally prepend workspace context to the user message
		augmented = message
		if include_context:
			try:
				ctx = self.get_context()
				if ctx.get("context"):
					augmented = f"[Current workspace state]\n{ctx['context']}\n\n[User message]\n{message}"
			except Exception:
				pass

		# Add user message to history
		history.append({"role": "user", "content": augmented})

		# Run the agent
		response = self._agent.run(messages=history)

		# Extract the assistant response
		assistant_content = ""
		tool_calls = []

		if response and response.messages:
			for msg in response.messages:
				if msg.role == "assistant" and msg.content:
					assistant_content = msg.content
				elif msg.role == "tool":
					tool_calls.append({
						"name": getattr(msg, 'tool_name', None),
						"result": msg.content[:200] if msg.content else None,
					})

		# If no structured response found, try response.content
		if not assistant_content and hasattr(response, 'content') and response.content:
			assistant_content = response.content

		# Add assistant response to history
		history.append({"role": "assistant", "content": assistant_content})

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
		model_source:  Optional[str]       = None  # "ollama", "openai", "anthropic"
		model_name:    Optional[str]       = None  # e.g. "mistral", "gpt-4o-mini"
		toolkit_names: Optional[List[str]] = None  # e.g. ["console_toolkit", "file_toolkit"]

	class ConsoleChatRequest(BaseModel):
		message:         str
		session_id:      Optional[str]  = None   # omit to create a new session
		include_context: bool           = True   # prepend workspace state to the message

	@app.post("/console/start")
	async def console_start(request: ConsoleStartRequest = ConsoleStartRequest()):
		port = await console_mgr.start(request.model_source, request.model_name, request.toolkit_names)
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
		except RuntimeError as e:
			return {"error": str(e)}

	@app.get("/console/toolkits")
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
