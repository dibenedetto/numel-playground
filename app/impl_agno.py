# impl_agno

import copy


# from   fastapi                         import FastAPI
from   typing                          import Any, List


from   agno.agent                      import Agent
from   agno.db.postgres                import PostgresDb
from   agno.db.sqlite                  import SqliteDb
from   agno.knowledge.embedder.openai  import OpenAIEmbedder
from   agno.knowledge.embedder.ollama  import OllamaEmbedder
from   agno.knowledge.knowledge        import Knowledge
from   agno.memory.manager             import MemoryManager
from   agno.models.ollama              import Ollama
from   agno.models.openai              import OpenAIChat
# from   agno.os                         import AgentOS
# from   agno.os.interfaces.agui         import AGUI
from   agno.session.summary            import SessionSummaryManager
from   agno.tools.duckduckgo           import DuckDuckGoTools
from   agno.tools.reasoning            import ReasoningTools
from   agno.vectordb.chroma            import ChromaDb
from   agno.vectordb.lancedb           import LanceDb
from   agno.vectordb.pgvector          import PgVector
from   agno.vectordb.search            import SearchType


from   schema                          import *
from   nodes                           import ImplementedBackend


def build_backend_agno(workflow: Workflow) -> ImplementedBackend:

	def _get_search_type(value: str) -> SearchType:
		if value == "hybrid":
			return SearchType.hybrid
		if value == "keyword":
			return SearchType.keyword
		if value == "vector":
			return SearchType.vector
		raise ValueError(f"Invalid Agno db search type: {value}")


	def _build_info(workflow: Workflow, links: List[Any], impl: List[Any], index: int):
		item_config = workflow.nodes[index]
		assert item_config is not None and item_config.type == "info_config", "Invalid Agno info"
		item = copy.deepcopy(item_config)
		impl[index] = item


	def _build_backend(workflow: Workflow, links: List[Any], impl: List[Any], index: int):
		item_config = workflow.nodes[index]
		assert item_config is not None and item_config.type == "backend_config", "Invalid Agno backend"
		item = copy.deepcopy(item_config)
		impl[index] = item


	def _build_model(workflow: Workflow, links: List[Any], impl: List[Any], index: int):
		item_config = workflow.nodes[index]
		assert item_config is not None and item_config.type == "model_config", "Invalid Agno model"
		if item_config.source == "ollama":
			item = Ollama(id=item_config.id)
		elif item_config.source == "openai":
			item = OpenAIChat(id=item_config.id)
		else:
			raise ValueError(f"Unsupported Agno model")
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
		supported_db_classes = {
			"chroma"   : (ChromaDb, lambda: {"collection": "vectors"}),
			"lancedb"  : (LanceDb , lambda: {}),
			"pgvector" : (PgVector, lambda: {}),
		}
		mkdb = supported_db_classes.get(item_config.engine)
		if not mkdb:
			raise ValueError(f"Unsupported Agno index db")
		search_type = _get_search_type(item_config.search_type)
		item = mkdb[0](
			embedder    = impl[links[index]["embedding"]] if item_config.embedding is not None else None,
			uri         = item_config.url,
			table_name  = item_config.table_name,
			search_type = search_type,
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
		args = item_config.args if item_config.args is not None else dict()
		if item_config.name == "@reasoning":
			item = ReasoningTools()
		elif item_config.name == "@web_search":
			max_results = args.get("max_results", DEFAULT_TOOL_MAX_WEB_SEARCH_RESULTS)
			item = DuckDuckGoTools(fixed_max_results=max_results)
		else:
			raise ValueError(f"Unsupported Agno tool")
		impl[index] = item


	def _build_agent_options(workflow: Workflow, links: List[Any], impl: List[Any], index: int):
		item_config = workflow.nodes[index]
		assert item_config is not None and item_config.type == "agent_options_config", "Invalid Agno agent options"
		item = copy.deepcopy(item_config)
		impl[index] = item


	def _build_agent(workflow: Workflow, links: List[Any], impl: List[Any], index: int):
		item_config = workflow.nodes[index]
		assert item_config is not None and item_config.type == "agent_config", "Invalid Agno agent"

		if True:
			name = f"Numel Agno Agent {index}"
			if item_config.info is not None:
				info = impl[links[index]["info"]]
				if info.name:
					name = info.name

		if True:
			model  = impl[links[index]["model"]] if item_config.model is not None else None
			if model is None:
				raise ValueError(f"Agno agent model is required")

		if True:
			options = impl[links[index]["options"]] if item_config.info is not None else AgentOptionsConfig()

		if True:
			content_db = impl[links[index]["content_db"]] if item_config.content_db is not None else None

		# TODO
		tools = None
		# if True:
		# 	tools = [impl.tools[i] for i in item_config.tools if impl.tools[i] is not None]

		if True:
			enable_agentic_memory   = False
			enable_user_memories    = False
			add_memories_to_context = False
			memory_mgr              = None
			if item_config.memory_mgr is not None:
				memory_mgr_index        = links[index]["memory_mgr"]
				memory_mgr_config       = workflow.nodes[memory_mgr_index]
				enable_agentic_memory   = memory_mgr_config.managed
				add_memories_to_context = memory_mgr_config.query
				enable_user_memories    = memory_mgr_config.update
				memory_mgr              = impl[memory_mgr_index]

		if True:
			search_session_history  = False
			num_history_sessions    = None
			session_summary_manager = None
			if item_config.session_mgr is not None:
				session_mgr_index      = links[index]["session_mgr"]
				session_mgr_config     = workflow.nodes[session_mgr_index]
				search_session_history = session_mgr_config.query
				num_history_sessions   = session_mgr_config.history_size
				if session_mgr_config.model is not None or session_mgr_config.prompt:
					session_mgr_model = impl[links[session_mgr_index]["model"]] if session_mgr_config.model is not None else None
					session_summary_manager = SessionSummaryManager(
						model                  = session_mgr_model,
						session_summary_prompt = session_mgr_config.prompt,
					)

		if True:
			item = Agent(
				name                    = name,

				model                   = model,

				description             = options.description,
				instructions            = options.instructions,
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

		impl[index] = item


	indices = {
		"info_config"              : [],
		"backend_config"           : [],
		"model_config"             : [],
		"embedding_config"         : [],
		"content_db_config"        : [],
		"index_db_config"          : [],
		"tool_config"              : [],
		"agent_options_config"     : [],
		"memory_manager_config"    : [],
		"session_manager_config"   : [],
		"knowledge_manager_config" : [],
		"agent_config"             : [],
	}

	unused_nodes = []
	for i, node in enumerate(workflow.nodes):
		indices.get(node.type, unused_nodes).append(i)

	links = [dict() for _ in range(len(workflow.nodes))]
	for edge in workflow.edges:
		links[edge.target][edge.target_slot] = edge.source

	impl = [None] * len(workflow.nodes)

	for i in indices["info_config"             ]: _build_info              (workflow, links, impl, i)
	for i in indices["backend_config"          ]: _build_backend           (workflow, links, impl, i)
	for i in indices["model_config"            ]: _build_model             (workflow, links, impl, i)
	for i in indices["embedding_config"        ]: _build_embedding         (workflow, links, impl, i)
	for i in indices["content_db_config"       ]: _build_content_db        (workflow, links, impl, i)
	for i in indices["index_db_config"         ]: _build_index_db          (workflow, links, impl, i)
	for i in indices["memory_manager_config"   ]: _build_memory_manager    (workflow, links, impl, i)
	for i in indices["session_manager_config"  ]: _build_session_manager   (workflow, links, impl, i)
	for i in indices["knowledge_manager_config"]: _build_knowledge_manager (workflow, links, impl, i)
	for i in indices["tool_config"             ]: _build_tool              (workflow, links, impl, i)
	for i in indices["agent_options_config"    ]: _build_agent_options     (workflow, links, impl, i)
	for i in indices["agent_config"            ]: _build_agent             (workflow, links, impl, i)


	async def run_tool(tool: Any, *args, **kwargs) -> dict:
		raw    = await tool(*args, **kwargs)
		result = dict(
			content_type = "",
			content      = raw,
		)
		return result


	async def run_agent(agent: Any, *args, **kwargs) -> dict:
		raw    = await agent.arun(input=args, **kwargs)
		result = dict(
			content_type = raw.content_type,
			content      = raw.content,
		)
		return result


	backend = ImplementedBackend(
		handles   = impl,
		run_tool  = run_tool,
		run_agent = run_agent,
	)

	return backend
