# impl_agno

import copy
import os
import tempfile


from   importlib                       import import_module
from   inspect                         import iscoroutinefunction, getmembers, ismethod
from   fastapi                         import FastAPI
from   typing                          import Any, Dict, List, Tuple
from   utils                           import log_print


from   agno.agent                      import Agent
from   agno.db.postgres                import PostgresDb
from   agno.db.sqlite                  import SqliteDb
from   agno.knowledge.embedder.openai  import OpenAIEmbedder
from   agno.knowledge.embedder.ollama  import OllamaEmbedder
from   agno.knowledge.knowledge        import Knowledge
from   agno.memory.manager             import MemoryManager
from   agno.models.ollama              import Ollama
from   agno.models.openai              import OpenAIChat
from   agno.os                         import AgentOS
from   agno.os.interfaces.agui         import AGUI
from   agno.session.summary            import SessionSummaryManager
from   agno.tools.duckduckgo           import DuckDuckGoTools
from   agno.tools.reasoning            import ReasoningTools
# from   agno.vectordb.chroma            import ChromaDb
from   agno.vectordb.lancedb           import LanceDb
from   agno.vectordb.pgvector          import PgVector
from   agno.vectordb.search            import SearchType


from   schema                          import *
from   nodes                           import ImplementedBackend
from   utils                           import add_middleware


# Patch Agno's AG-UI utils: some model providers (e.g. Ollama) return None for
# tool_call_id, which causes a Pydantic validation error in ToolCallStartEvent.
# Generate a fallback UUID when the ID is missing.
def _patch_agno_tool_call_id():
	try:
		import uuid
		import agno.os.interfaces.agui.utils as _agui_utils
		from agno.agent import RunEvent
		_orig = _agui_utils._create_events_from_chunk
		_pending_ids = []  # stack: start pushes, end pops
		def _patched(chunk, message_id, message_started, event_buffer, **kw):
			if hasattr(chunk, 'tool') and chunk.tool:
				tc = chunk.tool
				if hasattr(tc, 'tool_call_id') and tc.tool_call_id is None:
					evt = getattr(chunk, 'event', None)
					if evt in (RunEvent.tool_call_started,):
						gen_id = f"tc_{uuid.uuid4().hex[:12]}"
						tc.tool_call_id = gen_id
						_pending_ids.append(gen_id)
					else:
						tc.tool_call_id = _pending_ids.pop() if _pending_ids else f"tc_{uuid.uuid4().hex[:12]}"
			if hasattr(chunk, 'tool_calls') and chunk.tool_calls:
				for tc in chunk.tool_calls:
					if hasattr(tc, 'tool_call_id') and tc.tool_call_id is None:
						gen_id = f"tc_{uuid.uuid4().hex[:12]}"
						tc.tool_call_id = gen_id
						_pending_ids.append(gen_id)
			return _orig(chunk, message_id, message_started, event_buffer, **kw)
		_agui_utils._create_events_from_chunk = _patched
	except Exception:
		pass

_patch_agno_tool_call_id()


def build_backend_agno(workflow: Workflow, skill_mgr=None) -> ImplementedBackend:

	def _get_search_type(value: str) -> SearchType:
		if value == "hybrid":
			return SearchType.hybrid
		if value == "keyword":
			return SearchType.keyword
		if value == "vector":
			return SearchType.vector
		raise ValueError(f"Invalid Agno db search type: {value}")


	# def _build_backend(workflow: Workflow, links: List[Any], impl: List[Any], index: int):
	# 	item_config = workflow.nodes[index]
	# 	assert item_config is not None and item_config.type == "backend_config", "Invalid Agno backend"
	# 	item = copy.deepcopy(item_config)
	# 	impl[index] = item


	def _build_model(workflow: Workflow, links: List[Any], impl: List[Any], index: int):
		item_config = workflow.nodes[index]
		assert item_config is not None and item_config.type == "model_config", "Invalid Agno model"
		if item_config.source == "ollama":
			item = Ollama(id=item_config.name)
		elif item_config.source == "openai":
			item = OpenAIChat(id=item_config.name)
		elif item_config.source == "anthropic":
			from agno.models.anthropic import Claude
			item = Claude(id=item_config.name)
		else:
			raise ValueError(f"Unsupported Agno model source: {item_config.source}")
		impl[index] = item


	def _build_embedding(workflow: Workflow, links: List[Any], impl: List[Any], index: int):
		item_config = workflow.nodes[index]
		assert item_config is not None and item_config.type == "embedding_config", "Invalid Agno embedding"
		if item_config.source == "ollama":
			item = OllamaEmbedder()
		elif item_config.source == "openai":
			item = OpenAIEmbedder()
		else:
			raise ValueError(f"Unsupported Agno embedding")
		impl[index] = item


	def _build_content_db(workflow: Workflow, links: List[Any], impl: List[Any], index: int):
		item_config = workflow.nodes[index]
		assert item_config is not None and item_config.type == "content_db_config", "Invalid Agno content db"
		supported_db_classes = {
			"postgres" : (PostgresDb, lambda: {}),
			"sqlite"   : (SqliteDb  , lambda: {}),
		}
		mkdb = supported_db_classes.get(item_config.engine)
		if not mkdb:
			raise ValueError(f"Unsupported Agno content db")
		item = mkdb[0](
			db_file         = item_config.url,
			memory_table    = item_config.memory_table_name,
			session_table   = item_config.session_table_name,
			knowledge_table = item_config.knowledge_table_name,
			# # Table to store all metrics aggregations
			# metrics_table="your_metrics_table_name",
			# # Table to store all your evaluation data
			# eval_table="your_evals_table_name",
			# # Table to store all your knowledge content
			**(mkdb[1]()),
		)
		impl[index] = item


	def _build_index_db(workflow: Workflow, links: List[Any], impl: List[Any], index: int):
		item_config = workflow.nodes[index]
		assert item_config is not None and item_config.type == "index_db_config", "Invalid Agno index db"
		search_type = _get_search_type(item_config.search_type)
		full_path   = f"{item_config.url}_{item_config.table_name}"
		supported_db_classes = {
			# "chroma"   : (ChromaDb, lambda: {
			# 	"path"        : f"{full_path}",
			# 	"search_type" : search_type,
			# 	"collection"  : "vectors",
			# }),
			"lancedb"  : (LanceDb , lambda: {
				"uri"         : f"{full_path}",
				"table_name"  : item_config.table_name,
				"search_type" : search_type,
			}),
			"pgvector" : (PgVector, lambda: {
				"uri"         : f"{full_path}",
				"table_name"  : item_config.table_name,
				"search_type" : search_type,
			}),
		}
		mkdb = supported_db_classes.get(item_config.engine)
		if not mkdb:
			raise ValueError(f"Unsupported Agno index db")
		embedder = impl[links[index]["embedding"]] if item_config.embedding is not None else None
		item     = mkdb[0](
			embedder = embedder,
			**(mkdb[1]()),
		)
		impl[index] = item


	def _build_memory_manager(workflow: Workflow, links: List[Any], impl: List[Any], index: int):
		item_config = workflow.nodes[index]
		assert item_config is not None and item_config.type == "memory_manager_config", "Invalid Agno memory manager"
		model = impl[links[index]["model"]] if item_config.model is not None else None
		item = MemoryManager(
			model          = model,
			system_message = item_config.prompt,
		)
		impl[index] = item


	def _build_session_manager(workflow: Workflow, links: List[Any], impl: List[Any], index: int):
		item_config = workflow.nodes[index]
		assert item_config is not None and item_config.type == "session_manager_config", "Invalid Agno session manager"
		item = copy.deepcopy(item_config)
		impl[index] = item


	def _build_knowledge_manager(workflow: Workflow, links: List[Any], impl: List[Any], index: int):
		item_config = workflow.nodes[index]
		assert item_config is not None and item_config.type == "knowledge_manager_config", "Invalid Agno knowledge manager"
		description = item_config.description
		content_db  = impl[links[index]["content_db"]] if item_config.content_db is not None else None
		index_db    = impl[links[index]["index_db"  ]] if item_config.index_db   is not None else None
		item = Knowledge(
			description = description,
			contents_db = content_db,
			vector_db   = index_db,
			max_results = item_config.max_results,
		)
		impl[index] = item


	def _build_tool(workflow: Workflow, links: List[Any], impl: List[Any], index: int):
		item_config = workflow.nodes[index]
		assert item_config is not None and item_config.type == "tool_config", "Invalid Agno tool"
		if item_config.lang and item_config.script:
			# Inline tool: compile the script into a Python function named 'run'
			script = item_config.script
			lang   = item_config.lang
			if lang not in ("python",):
				raise ValueError(f"Inline tool only supports lang='python', got '{lang}'")
			# The script should define a function called 'run' (async or sync)
			# Example:
			#   async def run(query: str) -> str:
			#       return query.upper()
			ns = {}
			exec(compile(script, f"<inline_tool:{item_config.name or 'unnamed'}>", "exec"), ns)
			run_fn = ns.get("run")
			if run_fn is None:
				raise ValueError("Inline tool script must define a function named 'run'")
			# Wrap sync functions in an async wrapper
			import inspect as _inspect
			if not _inspect.iscoroutinefunction(run_fn):
				_sync_run = run_fn
				async def run_fn(**kwargs):
					return _sync_run(**kwargs)
			impl[index] = run_fn
			return
		if not item_config.name:
			raise ValueError(f"Agno tool needs name")
		args = item_config.args or dict()
		item = None
		if item_config.name[0] == "@":
			if item_config.name == "@reasoning":
				item = ReasoningTools()
			elif item_config.name == "@web_search":
				max_results = args.get("max_results", DEFAULT_TOOL_MAX_WEB_SEARCH_RESULTS)
				item = DuckDuckGoTools(fixed_max_results=max_results)
		else:
			module_path, func_name = item_config.name.rsplit(".", 1)
			# Try the exact module, then fallback paths for convenience
			candidates = [module_path]
			if "." not in module_path:
				candidates.append(f"toolkits.{module_path}")
				candidates.append(f"contrib.toolkits.{module_path}")
			elif module_path.startswith("toolkits.") and not module_path.startswith("contrib."):
				candidates.append(f"contrib.{module_path}")
			for candidate in candidates:
				try:
					md = import_module(candidate)
					fn = getattr(md, func_name, None)
					if fn:
						item = fn
						if candidate != module_path:
							log_print(f"ℹ️  Resolved tool '{module_path}.{func_name}' → '{candidate}.{func_name}'")
						break
				except (ImportError, ModuleNotFoundError):
					continue
			if item is None:
				log_print(f"⚠️  Agno tool not found: {item_config.name} (tried: {', '.join(c + '.' + func_name for c in candidates)})")
		impl[index] = item


	def _build_toolkit(workflow: Workflow, links: List[Any], impl: List[Any], index: int):
		item_config = workflow.nodes[index]
		assert item_config is not None and item_config.type == "toolkit_config", "Invalid Agno toolkit"
		if not item_config.name:
			raise ValueError("Agno toolkit needs name")
		import credentials as _creds
		args = _creds.resolve_dict(item_config.args or {})
		module_name = item_config.name.replace("/", ".").replace("\\", ".")
		# Try the exact name first, then fallback paths for convenience:
		#   "mesh_toolkit"          → try "toolkits.mesh_toolkit", "contrib.toolkits.mesh_toolkit"
		#   "toolkits.mesh_toolkit" → try "contrib.toolkits.mesh_toolkit"
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
				if candidate != module_name:
					log_print(f"ℹ️  Resolved toolkit '{module_name}' → '{candidate}'")
				break
			except (ImportError, ModuleNotFoundError):
				continue
		if md is None:
			log_print(f"⚠️  Agno toolkit module not found: {module_name} (tried: {', '.join(candidates)})")
			impl[index] = None
			return
		# Find the toolkit class: look for a class with __toolkit__ = True, or the first class with __doc__
		toolkit_cls = None
		for attr_name in dir(md):
			attr = getattr(md, attr_name)
			if isinstance(attr, type) and getattr(attr, '__toolkit__', False):
				toolkit_cls = attr
				break
		if toolkit_cls is None:
			for attr_name in dir(md):
				attr = getattr(md, attr_name)
				if isinstance(attr, type) and attr.__module__ == md.__name__ and attr.__doc__:
					toolkit_cls = attr
					break
		if toolkit_cls is None:
			log_print(f"⚠️  Agno toolkit class not found in module: {item_config.name}")
			impl[index] = None
			return
		# Instantiate
		try:
			instance = toolkit_cls(**args)
		except Exception as e:
			log_print(f"⚠️  Agno toolkit instantiation failed: {toolkit_cls.__name__} ({e})")
			impl[index] = None
			return
		# Extract description from class docstring
		description = toolkit_cls.__doc__ or ""
		# Extract public methods as tools
		tools = []
		for name, method in getmembers(instance, predicate=ismethod):
			if name.startswith('_'):
				continue
			tools.append(method)
		impl[index] = {
			"instance"    : instance,
			"description" : description.strip(),
			"tools"       : tools,
		}


	def _build_skill(workflow: Workflow, links: List[Any], impl: List[Any], index: int):
		item_config = workflow.nodes[index]
		assert item_config is not None and item_config.type == "skill_config", "Invalid Agno skill"
		item = copy.deepcopy(item_config)
		impl[index] = item


	def _build_agent_options(workflow: Workflow, links: List[Any], impl: List[Any], index: int):
		item_config = workflow.nodes[index]
		assert item_config is not None and item_config.type == "agent_options_config", "Invalid Agno agent options"
		item = copy.deepcopy(item_config)
		impl[index] = item


	def _build_agent(workflow: Workflow, links: List[Any], impl: List[Any], index: int):
		item_config = workflow.nodes[index]
		assert item_config is not None and item_config.type == "agent_config", "Invalid Agno agent"

		node_links = links[index]

		if True:
			model = impl[node_links["model"]] if "model" in node_links else None
			if model is None:
				raise ValueError(f"Agno agent model is required")

		if True:
			options = impl[node_links["options"]] if "options" in node_links else AgentOptionsConfig()

		if True:
			content_db = impl[node_links["content_db"]] if "content_db" in node_links else None

		tools = None
		tools_links = node_links.get("tools")
		if isinstance(tools_links, dict) and tools_links:
			tools = [impl[src] for src in tools_links.values() if impl[src] is not None]

		# Toolkits: extract descriptions for prompt and merge functions into tools
		toolkit_descriptions = []
		toolkits_links = node_links.get("toolkits")
		if isinstance(toolkits_links, dict) and toolkits_links:
			for src in toolkits_links.values():
				tk = impl[src]
				if tk is None:
					continue
				if tk["description"]:
					toolkit_descriptions.append(tk["description"])
				if tk["tools"]:
					if tools is None:
						tools = []
					tools.extend(tk["tools"])

		if True:
			enable_agentic_memory   = False
			enable_user_memories    = False
			add_memories_to_context = False
			memory_mgr              = None
			if "memory_mgr" in node_links:
				memory_mgr_index        = node_links["memory_mgr"]
				memory_mgr_config       = workflow.nodes[memory_mgr_index]
				enable_agentic_memory   = memory_mgr_config.managed
				add_memories_to_context = memory_mgr_config.query
				enable_user_memories    = memory_mgr_config.update
				memory_mgr              = impl[memory_mgr_index]

		if True:
			search_session_history  = False
			num_history_sessions    = None
			session_summary_manager = None
			if "session_mgr" in node_links:
				session_mgr_index      = node_links["session_mgr"]
				session_mgr_config     = workflow.nodes[session_mgr_index]
				search_session_history = session_mgr_config.query
				num_history_sessions   = session_mgr_config.history_size
				if "model" in links[session_mgr_index] or session_mgr_config.prompt:
					session_mgr_model = impl[links[session_mgr_index]["model"]] if "model" in links[session_mgr_index] else None
					session_summary_manager = SessionSummaryManager(
						model                  = session_mgr_model,
						session_summary_prompt = session_mgr_config.prompt,
					)

		# Merge toolkit descriptions into agent instructions
		agent_instructions = options.instructions
		if toolkit_descriptions:
			extra = ["\n## Available Toolkits\n"] + toolkit_descriptions
			if agent_instructions:
				agent_instructions = list(agent_instructions) + extra
			else:
				agent_instructions = extra

		# Skills: resolve names to instruction text via SkillManager
		skills_links = node_links.get("skills")
		if isinstance(skills_links, dict) and skills_links and skill_mgr:
			skill_names = []
			for src in skills_links.values():
				skill_cfg = workflow.nodes[src]
				if skill_cfg and hasattr(skill_cfg, 'name') and skill_cfg.name:
					skill_names.append(skill_cfg.name)
			if skill_names:
				skill_instructions = skill_mgr.get_instructions_for(skill_names)
				if skill_instructions:
					extra = ["\n--- Active Skills ---"] + skill_instructions
					if agent_instructions:
						agent_instructions = list(agent_instructions) + extra
					else:
						agent_instructions = extra

		if True:
			item = Agent(
				name                    = options.name or "Agent",

				model                   = model,

				description             = options.description,
				instructions            = agent_instructions,
				system_message          = options.prompt_override,

				markdown                = options.markdown,
				db                      = content_db,
				tools                   = tools,

				enable_agentic_memory   = enable_agentic_memory,
				enable_user_memories    = enable_user_memories,
				add_memories_to_context = add_memories_to_context,
				memory_manager          = memory_mgr,

				search_session_history  = search_session_history,
				num_history_sessions    = num_history_sessions,
				session_summary_manager = session_summary_manager,
			)

		if True:
			app = AgentOS(
				agents     = [item],
				interfaces = [AGUI(agent=item)]
			).get_app()

			add_middleware(app)

			item.__extra = {
				"app": app
			}

		impl[index] = item


	indices = {
		"backend_config"           : [],
		"model_config"             : [],
		"embedding_config"         : [],
		"content_db_config"        : [],
		"index_db_config"          : [],
		"tool_config"              : [],
		"toolkit_config"           : [],
		"skill_config"             : [],
		"agent_options_config"     : [],
		"memory_manager_config"    : [],
		"session_manager_config"   : [],
		"knowledge_manager_config" : [],
		"agent_config"             : [],
	}

	unused_nodes = []
	for i, node in enumerate(workflow.nodes):
		indices.get(node.type, unused_nodes).append(i)

	default_embedding_index = None
	default_embedding       = None
	for i in indices["index_db_config"]:
		item_config = workflow.nodes[i]
		if item_config.embedding is None:
			if default_embedding_index is None:
				default_embedding_index = len(workflow.nodes)
				default_embedding       = EmbeddingConfig()
				workflow.nodes.append(default_embedding)
				indices["embedding_config"].append(default_embedding_index)
			edge = Edge(
				source      = default_embedding_index,
				target      = i,
				source_slot = "get",
				target_slot = "embedding",
			)
			workflow.edges.append(edge)
			item_config.embedding = default_embedding

	links = [dict() for _ in range(len(workflow.nodes))]
	for edge in workflow.edges:
		slot = edge.target_slot
		if '.' in slot:
			# Dotted slots like "tools.list_dir" → nested dict: links[target]["tools"]["list_dir"] = source
			field, sub = slot.split('.', 1)
			if field not in links[edge.target]:
				links[edge.target][field] = {}
			links[edge.target][field][sub] = edge.source
		else:
			links[edge.target][slot] = edge.source

	impl = [None] * len(workflow.nodes)

	# for i in indices["backend_config"          ]: _build_backend           (workflow, links, impl, i)
	for i in indices["model_config"            ]: _build_model             (workflow, links, impl, i)
	for i in indices["embedding_config"        ]: _build_embedding         (workflow, links, impl, i)
	for i in indices["content_db_config"       ]: _build_content_db        (workflow, links, impl, i)
	for i in indices["index_db_config"         ]: _build_index_db          (workflow, links, impl, i)
	for i in indices["memory_manager_config"   ]: _build_memory_manager    (workflow, links, impl, i)
	for i in indices["session_manager_config"  ]: _build_session_manager   (workflow, links, impl, i)
	for i in indices["knowledge_manager_config"]: _build_knowledge_manager (workflow, links, impl, i)
	for i in indices["tool_config"             ]: _build_tool              (workflow, links, impl, i)
	for i in indices["toolkit_config"          ]: _build_toolkit           (workflow, links, impl, i)
	for i in indices["skill_config"            ]: _build_skill             (workflow, links, impl, i)
	for i in indices["agent_options_config"    ]: _build_agent_options     (workflow, links, impl, i)
	for i in indices["agent_config"            ]: _build_agent             (workflow, links, impl, i)


	async def run_tool(tool: Any, *args, **kwargs) -> dict:
		if iscoroutinefunction(tool):
			raw = await tool(*args, **kwargs)
		else:
			raw = tool(*args, **kwargs)
		# result = dict(
		# 	content_type = "",
		# 	content      = raw,
		# )
		# return result
		return raw


	async def run_agent(agent: Any, *args, **kwargs) -> dict:
		# If image is provided, build a multimodal message
		image_b64 = kwargs.pop("image", None)
		message = args[0] if args else ""
		if image_b64 and message:
			if isinstance(message, str):
				from agno.media import Image as AgnoImage
				# strip data: prefix if present
				if "," in image_b64:
					image_b64 = image_b64.split(",", 1)[1]
				message = [
					{"type": "text", "text": message},
					AgnoImage(base64_data=image_b64),
				]
		raw    = await agent.arun(input=message, **kwargs)
		result = dict(
			content_type = raw.content_type,
			content      = raw.content,
		)
		return result


	def get_agent_app(agent: Any) -> FastAPI:
		app = agent.__extra["app"]
		return app


	async def add_contents(knowledge: Any, files: List[Any]) -> List[str]:
		if not isinstance(knowledge, Knowledge):
			raise "Invalid Agno Knowledge instance"
		if not knowledge.contents_db or not knowledge.vector_db:
			raise "No content or index db present in Agno Knowledge instance"
		p_res = []
		for i, info in enumerate(files):
			content = info["content"]
			if not content:
				file = info["file"]
				if not file:
					continue
				content = await file.read()
			filename  = info["filename"]
			extension = os.path.splitext(filename)[1]
			metadata  = {"source": filename}
			with tempfile.NamedTemporaryFile(suffix=extension, delete=True, delete_on_close=False) as temp_file:
				temp_file.write(content)
				temp_file.flush()
				temp_file.close()
				await knowledge.add_content_async(
					upsert         = False,
					skip_if_exists = False,
					path           = temp_file.name,
					metadata       = metadata,
				)
			p_res.append(i)
		contents, _ = knowledge.get_content()
		# contents.sort(key=lambda x: x.created_at)
		contents = contents[-len(p_res):]
		result   = [None] * len(files)
		for i, content in zip(p_res, contents):
			result[i] = content.id
		return result


	async def remove_contents(knowledge: Any, ids: List[str]) -> List[bool]:
		if not isinstance(knowledge, Knowledge):
			raise "Invalid Agno Knowledge instance"
		result = [False] * len(ids)
		for i, id in enumerate(ids):
			if not id:
				continue
			knowledge.remove_content_by_id(id)
			result[i] = True
		return result


	async def list_contents(knowledge: Any) -> List[Tuple[str, Dict[str, Any]]]:
		if not isinstance(knowledge, Knowledge):
			raise "Invalid Agno Knowledge instance"
		contents, _ = knowledge.get_content()
		result = [(content.id, content.metadata) for content in contents]
		return result


	backend = ImplementedBackend(
		handles         = impl,
		run_tool        = run_tool,
		run_agent       = run_agent,
		get_agent_app   = get_agent_app,
		add_contents    = add_contents,
		remove_contents = remove_contents,
		list_contents   = list_contents,
	)

	return backend
