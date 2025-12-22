# numel

import copy
import json


from   collections.abc import Callable
from   fastapi         import FastAPI
from   typing          import Dict, List, Tuple


from   schema          import *


def compatible_backends(a: BackendConfig, b: BackendConfig) -> bool:
	# TODO: improve compatibility check
	return a.type == b.type and (a.version == b.version or not a.version or not b.version)


def unroll_config(config: AppConfig) -> AppConfig:
	config_copy = copy.deepcopy(config) if config is not None else AppConfig()

	if DEFAULT_APP_MAX_AGENTS is not None and DEFAULT_APP_MAX_AGENTS > 0:
		if config_copy.agents is not None:
			if len(config_copy.agents) > DEFAULT_APP_MAX_AGENTS:
				config_copy.agents = config_copy.agents[:DEFAULT_APP_MAX_AGENTS]

	if True:
		if not config_copy.info             : config_copy.info             = InfoConfig()
		if not config_copy.options          : config_copy.options          = AppOptionsConfig()
		if not config_copy.infos            : config_copy.infos            = []
		if not config_copy.app_options      : config_copy.app_options      = []
		if not config_copy.backends         : config_copy.backends         = []
		if not config_copy.models           : config_copy.models           = []
		if not config_copy.embeddings       : config_copy.embeddings       = []
		if not config_copy.prompts          : config_copy.prompts          = []
		if not config_copy.content_dbs      : config_copy.content_dbs      = []
		if not config_copy.index_dbs        : config_copy.index_dbs        = []
		if not config_copy.memory_mgrs      : config_copy.memory_mgrs      = []
		if not config_copy.session_mgrs     : config_copy.session_mgrs     = []
		if not config_copy.knowledge_mgrs   : config_copy.knowledge_mgrs   = []
		if not config_copy.tools            : config_copy.tools            = []
		if not config_copy.agent_options    : config_copy.agent_options    = []
		if not config_copy.agents           : config_copy.agents           = []
		# if not config_copy.team_options     : config_copy.team_options     = []
		# if not config_copy.teams            : config_copy.teams            = []
		# if not config_copy.workflow_options : config_copy.workflow_options = []
		# if not config_copy.workflows        : config_copy.workflows        = []

	if True:
		if isinstance(config_copy.info, InfoConfig):
			config_copy.infos.append(config_copy.info)
			config_copy.info = len(config_copy.infos) - 1
		if not isinstance(config_copy.info, int) or config_copy.info < 0 or config_copy.info >= len(config_copy.infos):
			raise ValueError("Invalid config info")

	if True:
		if isinstance(config_copy.options, AppOptionsConfig):
			config_copy.app_options.append(config_copy.options)
			config_copy.options = len(config_copy.app_options) - 1
		if not isinstance(config_copy.options, int) or config_copy.options < 0 or config_copy.options >= len(config_copy.app_options):
			raise ValueError("Invalid config options")

	if True:
		for agent in config_copy.agents:
			if True:
				if isinstance(agent.info, InfoConfig):
					config_copy.infos.append(agent.info)
					agent.info = len(config_copy.infos) - 1
				if not isinstance(agent.info, int) or agent.info < 0 or agent.info >= len(config_copy.infos):
					raise ValueError("Invalid agent info")

			if True:
				if isinstance(agent.options, AgentOptionsConfig):
					config_copy.agent_options.append(agent.options)
					agent.options = len(config_copy.agent_options) - 1
				if not isinstance(agent.options, int) or agent.options < 0 or agent.options >= len(config_copy.agent_options):
					raise ValueError("Invalid agent options")

			if True:
				if isinstance(agent.backend, BackendConfig):
					config_copy.backends.append(agent.backend)
					agent.backend = len(config_copy.backends) - 1
				if not isinstance(agent.backend, int) or agent.backend < 0 or agent.backend >= len(config_copy.backends):
					raise ValueError("Invalid agent backend")

			if True:
				if agent.prompt is None:
						raise ValueError("Invalid agent prompt")
				if isinstance(agent.prompt, PromptConfig):
					config_copy.prompts.append(agent.prompt)
					agent.prompt = len(config_copy.prompts) - 1
				if not isinstance(agent.prompt, int) or agent.prompt < 0 or agent.prompt >= len(config_copy.prompts):
					raise ValueError("Invalid agent prompt")

			if True:
				if agent.content_db is not None:
					if isinstance(agent.content_db, ContentDBConfig):
						config_copy.content_dbs.append(agent.content_db)
						agent.content_db = len(config_copy.content_dbs) - 1
					if not isinstance(agent.content_db, int) or agent.content_db < 0 or agent.content_db >= len(config_copy.content_dbs):
						raise ValueError("Invalid agent content db")

			if True:
				if agent.memory_mgr is not None:
					if isinstance(agent.memory_mgr, MemoryManagerConfig):
						config_copy.memory_mgrs.append(agent.memory_mgr)
						agent.memory_mgr = len(config_copy.memory_mgrs) - 1
					if not isinstance(agent.memory_mgr, int) or agent.memory_mgr < 0 or agent.memory_mgr >= len(config_copy.memory_mgrs):
						raise ValueError("Invalid agent memory")

			if True:
				if agent.session_mgr is not None:
					if isinstance(agent.session_mgr, SessionManagerConfig):
						config_copy.session_mgrs.append(agent.session_mgr)
						agent.session_mgr = len(config_copy.session_mgrs) - 1
					if not isinstance(agent.session_mgr, int) or agent.session_mgr < 0 or agent.session_mgr >= len(config_copy.session_mgrs):
						raise ValueError("Invalid agent session")

			if True:
				if agent.knowledge_mgr is not None:
					if isinstance(agent.knowledge_mgr, KnowledgeManagerConfig):
						config_copy.knowledge_mgrs.append(agent.knowledge_mgr)
						agent.knowledge_mgr = len(config_copy.knowledge_mgrs) - 1
					if not isinstance(agent.knowledge_mgr, int) or agent.knowledge_mgr < 0 or agent.knowledge_mgr >= len(config_copy.knowledge_mgrs):
						raise ValueError("Invalid agent knowledge")

			if True:
				if agent.tools is not None:
					for tool in agent.tools:
						if isinstance(tool, ToolConfig):
							config_copy.tools.append(tool)
							tool = len(config_copy.tools) - 1
						if not isinstance(tool, int) or tool < 0 or tool >= len(config_copy.tools):
							raise ValueError("Invalid agent tool")

	if True:
		for memory_mgr in config_copy.memory_mgrs:
			if memory_mgr.prompt is not None:
				if isinstance(memory_mgr.prompt, PromptConfig):
					config_copy.prompts.append(memory_mgr.prompt)
					memory_mgr.prompt = len(config_copy.prompts) - 1
				if not isinstance(memory_mgr.prompt, int) or memory_mgr.prompt < 0 or memory_mgr.prompt >= len(config_copy.prompts):
					raise ValueError("Invalid memory prompt")
				prompt = config_copy.prompts[memory_mgr.prompt]

				if True:
					if prompt.model is None:
						raise ValueError("Invalid memory prompt model")
					if isinstance(prompt.model, ModelConfig):
						config_copy.models.append(prompt.model)
						prompt.model = len(config_copy.models) - 1
					if not isinstance(prompt.model, int) or prompt.model < 0 or prompt.model >= len(config_copy.models):
						raise ValueError("Invalid memory prompt model")

				if True:
					if prompt.embedding is None:
						raise ValueError("Invalid memory prompt embedding")
					if isinstance(prompt.embedding, EmbeddingConfig):
						config_copy.embeddings.append(prompt.embedding)
						prompt.embedding = len(config_copy.embeddings) - 1
					if not isinstance(prompt.embedding, int) or prompt.embedding < 0 or prompt.embedding >= len(config_copy.embeddings):
						raise ValueError("Invalid memory prompt embedding")

	if True:
		for session_mgr in config_copy.session_mgrs:
			if session_mgr.prompt is not None:
				if isinstance(session_mgr.prompt, PromptConfig):
					config_copy.prompts.append(session_mgr.prompt)
					session_mgr.prompt = len(config_copy.prompts) - 1
				if not isinstance(session_mgr.prompt, int) or session_mgr.prompt < 0 or session_mgr.prompt >= len(config_copy.prompts):
					raise ValueError("Invalid session prompt")
				prompt = config_copy.prompts[session_mgr.prompt]

				if True:
					if prompt.model is None:
						raise ValueError("Invalid session prompt model")
					if isinstance(prompt.model, ModelConfig):
						config_copy.models.append(prompt.model)
						prompt.model = len(config_copy.models) - 1
					if not isinstance(prompt.model, int) or prompt.model < 0 or prompt.model >= len(config_copy.models):
						raise ValueError("Invalid session prompt model")

				if True:
					if prompt.embedding is None:
						raise ValueError("Invalid session prompt embedding")
					if isinstance(prompt.embedding, EmbeddingConfig):
						config_copy.embeddings.append(prompt.embedding)
						prompt.embedding = len(config_copy.embeddings) - 1
					if not isinstance(prompt.embedding, int) or prompt.embedding < 0 or prompt.embedding >= len(config_copy.embeddings):
						raise ValueError("Invalid session prompt embedding")

	if True:
		for knowledge_mgr in config_copy.knowledge_mgrs:
			if True:
				if knowledge_mgr.content_db is not None:
					if isinstance(knowledge_mgr.content_db, ContentDBConfig):
						config_copy.content_dbs.append(knowledge_mgr.content_db)
						knowledge_mgr.content_db = len(knowledge_mgr.content_dbs) - 1
					if not isinstance(knowledge_mgr.content_db, int) or knowledge_mgr.content_db < 0 or knowledge_mgr.content_db >= len(config_copy.content_dbs):
						raise ValueError("Invalid knowledge manager content db")

			if True:
				if knowledge_mgr.index_db is not None:
					if isinstance(knowledge_mgr.index_db, IndexDBConfig):
						if isinstance(knowledge_mgr.index_db.embedding, EmbeddingConfig):
							config_copy.embeddings.append(knowledge_mgr.index_db.embedding)
							knowledge_mgr.index_db.embedding = len(config_copy.embeddings) - 1
						if not isinstance(knowledge_mgr.index_db.embedding, int) or knowledge_mgr.index_db.embedding < 0 or knowledge_mgr.index_db.embedding >= len(config_copy.index_dbs):
							raise ValueError("Invalid knowledge manager index db embedding")
						config_copy.index_dbs.append(knowledge_mgr.index_db)
						knowledge_mgr.index_db = len(config_copy.index_dbs) - 1
					if not isinstance(knowledge_mgr.index_db, int) or knowledge_mgr.index_db < 0 or knowledge_mgr.index_db >= len(config_copy.index_dbs):
						raise ValueError("Invalid knowledge manager index db")

	if True:
		for prompt in config_copy.prompts:
			if True:
				if prompt.model is None:
					raise ValueError("Invalid prompt model")
				if isinstance(prompt.model, ModelConfig):
					config_copy.models.append(prompt.model)
					prompt.model = len(config_copy.models) - 1
				if not isinstance(prompt.model, int) or prompt.model < 0 or prompt.model >= len(config_copy.models):
					raise ValueError("Invalid prompt model")

			if True:
				if prompt.embedding is None:
					raise ValueError("Invalid prompt embedding")
				if isinstance(prompt.embedding, EmbeddingConfig):
					config_copy.embeddings.append(prompt.embedding)
					prompt.embedding = len(config_copy.embeddings) - 1
				if not isinstance(prompt.embedding, int) or prompt.embedding < 0 or prompt.embedding >= len(config_copy.embeddings):
					raise ValueError("Invalid prompt embedding")

	return config_copy


def validate_config(config: AppConfig) -> bool:
	if config is None:
		return False

	if True:
		# TODO: check app info
		pass

	if True:
		# TODO: check options
		pass

	if True:
		# TODO: check port
		pass

	if True:
		for info in config.infos:
			# TODO: check info
			pass

	if True:
		for app_options in config.app_options:
			# TODO: check app_options
			pass

	if True:
		for backend in config.backends:
			# TODO: check backend
			pass

	if True:
		for model in config.models:
			# TODO: check model
			pass

	if True:
		for embedding in config.embeddings:
			# TODO: check embedding
			pass

	if True:
		for prompt in config.prompts:
			# TODO: check prompt
			pass

	if True:
		for content_db in config.content_dbs:
			# TODO: check content_db
			pass

	if True:
		for index_db in config.index_dbs:
			# TODO: check index_db
			pass

	if True:
		for memory_mgr in config.memory_mgrs:
			# TODO: check memory_mgr
			pass

	if True:
		for session_mgr in config.session_mgrs:
			# TODO: check session_mgr
			pass

	if True:
		for knowledge_mgr in config.knowledge_mgrs:
			# TODO: check knowledge_mgr
			pass

	if True:
		for tool in config.tools:
			# TODO: check tool
			pass

	if True:
		for agent_option in config.agent_options:
			# TODO: check agent_option
			pass

	if True:
		for agent in config.agents:
			# TODO: check agent
			pass

	# if True:
	# 	for team_option in config.team_options:
	# 		# TODO: check team_option
	# 		pass

	# if True:
	# 	for team in config.teams:
	# 		# TODO: check team
	# 		pass

	# if True:
	# 	for workflow_option in config.workflow_options:
	# 		# TODO: check workflow_option
	# 		pass

	# if True:
	# 	for workflow in config.workflows:
	# 		# TODO: check workflow
	# 		pass

	return True


def compact_config(config: AppConfig) -> AppConfig:
	# TODO: compact pydantic models
	config_copy = copy.deepcopy(config) if config is not None else AppConfig()
	return config_copy


def extract_config(config: AppConfig, backend: BackendConfig, active_agents: List[bool]) -> Tuple[AppConfig, dict, dict]:
	if config is None or backend is None or len(active_agents) != len(config.agents):
		return (None, None, None)

	extracted = AppConfig()

	extracted.infos            = []
	extracted.app_options      = []
	extracted.backends         = []
	extracted.models           = []
	extracted.embeddings       = []
	extracted.prompts          = []
	extracted.content_dbs      = []
	extracted.index_dbs        = []
	extracted.memory_mgrs      = []
	extracted.session_mgrs     = []
	extracted.knowledge_mgrs   = []
	extracted.tools            = []
	extracted.agent_options    = []
	extracted.agents           = []
	# extracted.team_options     = []
	# extracted.teams            = []
	# extracted.workflow_options = []
	# extracted.workflows        = []

	info_remap                 = dict()
	app_options_remap          = dict()
	model_remap                = dict()
	embedding_remap            = dict()
	prompt_remap               = dict()
	content_db_remap           = dict()
	index_db_remap             = dict()
	memory_mgr_remap           = dict()
	session_mgr_remap          = dict()
	knowledge_mgr_remap        = dict()
	tool_remap                 = dict()
	agent_options_remap        = dict()
	agent_remap                = dict()

	if True:
		if config.info is not None:
			if config.info not in info_remap:
				info_remap[config.info] = len(extracted.infos)
				extracted.infos.append(None)

	if True:
		if config.options is not None:
			if config.options not in app_options_remap:
				app_options_remap[config.options] = len(extracted.app_options)
				extracted.app_options.append(None)

	for i, agent in enumerate(config.agents):
		if not active_agents[i] or not compatible_backends(config.backends[agent.backend], backend):
			continue

		active_agents[i] = False

		agent_remap[i] = len(extracted.agents)
		extracted.agents.append(None)

		if True:
			if agent.info is not None:
				if agent.info not in info_remap:
					info_remap[agent.info] = len(extracted.infos)
					extracted.infos.append(None)

		if True:
			if agent.prompt is not None:
				if agent.prompt not in prompt_remap:
					prompt_remap[agent.prompt] = len(extracted.prompts)
					extracted.prompts.append(None)
					prompt = config.prompts[agent.prompt]
					if True:
						if prompt.model is not None:
							if prompt.model not in model_remap:
								model_remap[prompt.model] = len(extracted.models)
								extracted.models.append(None)
					if True:
						if prompt.embedding is not None:
							if prompt.embedding not in embedding_remap:
								embedding_remap[prompt.embedding] = len(extracted.embeddings)
								extracted.embeddings.append(None)

		if True:
			if agent.options is not None:
				if agent.options not in agent_options_remap:
					agent_options_remap[agent.options] = len(extracted.agent_options)
					extracted.agent_options.append(None)

		if True:
			if agent.content_db is not None:
				if agent.content_db not in content_db_remap:
					content_db_remap[agent.content_db] = len(extracted.content_dbs)
					extracted.content_dbs.append(None)

		if True:
			if agent.memory_mgr is not None:
				if agent.memory_mgr not in memory_mgr_remap:
					memory_mgr_remap[agent.memory_mgr] = len(extracted.memory_mgrs)
					extracted.memory_mgrs.append(None)
					memory_mgr = config.memory_mgrs[agent.memory_mgr]
					if True:
						if memory_mgr.prompt is not None:
							if memory_mgr.prompt not in prompt_remap:
								prompt_remap[memory_mgr.prompt] = len(extracted.prompts)
								extracted.prompts.append(None)
								prompt = config.prompts[memory_mgr.prompt]
								if True:
									if prompt.model is not None:
										if prompt.model not in model_remap:
											model_remap[prompt.model] = len(extracted.models)
											extracted.models.append(None)
								if True:
									if prompt.embedding is not None:
										if prompt.embedding not in embedding_remap:
											embedding_remap[prompt.embedding] = len(extracted.embeddings)
											extracted.embeddings.append(None)

		if True:
			if agent.session_mgr is not None:
				if agent.session_mgr not in session_mgr_remap:
					session_mgr_remap[agent.session_mgr] = len(extracted.session_mgrs)
					extracted.session_mgrs.append(None)
					session_mgr = config.session_mgrs[agent.session_mgr]
					if True:
						if session_mgr.prompt is not None:
							if session_mgr.prompt not in prompt_remap:
								prompt_remap[session_mgr.prompt] = len(extracted.prompts)
								extracted.prompts.append(None)
								prompt = config.prompts[session_mgr.prompt]
								if True:
									if prompt.model is not None:
										if prompt.model not in model_remap:
											model_remap[prompt.model] = len(extracted.models)
											extracted.models.append(None)
								if True:
									if prompt.embedding is not None:
										if prompt.embedding not in embedding_remap:
											embedding_remap[prompt.embedding] = len(extracted.embeddings)
											extracted.embeddings.append(None)

		if True:
			if agent.knowledge_mgr is not None:
				if agent.knowledge_mgr not in knowledge_mgr_remap:
					knowledge_mgr_remap[agent.knowledge_mgr] = len(extracted.knowledge_mgrs)
					extracted.knowledge_mgrs.append(None)
					knowledge_mgr = config.knowledge_mgrs[agent.knowledge_mgr]
					if True:
						if knowledge_mgr.content_db is not None:
							if knowledge_mgr.content_db not in content_db_remap:
								content_db_remap[knowledge_mgr.content_db] = len(extracted.content_dbs)
								extracted.content_dbs.append(None)
					if True:
						if knowledge_mgr.index_db is not None:
							if knowledge_mgr.index_db not in index_db_remap:
								index_db = config.index_dbs[knowledge_mgr.index_db]
								if True:
									if index_db.embedding not in embedding_remap:
										embedding_remap[index_db.embedding] = len(extracted.embeddings)
										extracted.embeddings.append(None)
								index_db_remap[knowledge_mgr.index_db] = len(extracted.index_dbs)
								extracted.index_dbs.append(None)

		if True:
			if agent.tools is not None:
				for tool in agent.tools:
					if tool not in tool_remap:
						tool_remap[tool] = len(extracted.tools)
						extracted.tools.append(None)

	if True:
		src_item = backend
		dst_item = copy.deepcopy(src_item)
		extracted.backends = [dst_item]

	for src, dst in info_remap.items():
		src_item = config.infos[src]
		dst_item = copy.deepcopy(src_item)
		extracted.infos[dst] = dst_item

	for src, dst in app_options_remap.items():
		src_item = config.app_options[src]
		dst_item = copy.deepcopy(src_item)
		extracted.app_options[dst] = dst_item

	for src, dst in model_remap.items():
		src_item = config.models[src]
		dst_item = copy.deepcopy(src_item)
		extracted.models[dst] = dst_item

	for src, dst in embedding_remap.items():
		src_item = config.embeddings[src]
		dst_item = copy.deepcopy(src_item)
		extracted.embeddings[dst] = dst_item

	for src, dst in prompt_remap.items():
		src_item = config.prompts[src]
		dst_item = copy.deepcopy(src_item)
		dst_item.model     = model_remap     [src_item.model    ]
		dst_item.embedding = embedding_remap [src_item.embedding]
		extracted.prompts[dst] = dst_item

	for src, dst in content_db_remap.items():
		src_item = config.content_dbs[src]
		dst_item = copy.deepcopy(src_item)
		extracted.content_dbs[dst] = dst_item

	for src, dst in index_db_remap.items():
		src_item = config.index_dbs[src]
		dst_item = copy.deepcopy(src_item)
		extracted.index_dbs[dst] = dst_item

	for src, dst in memory_mgr_remap.items():
		src_item = config.memory_mgrs[src]
		dst_item = copy.deepcopy(src_item)
		if src_item.prompt is not None:
			dst_item.prompt = prompt_remap[src_item.prompt]
		extracted.memory_mgrs[dst] = dst_item

	for src, dst in session_mgr_remap.items():
		src_item = config.session_mgrs[src]
		dst_item = copy.deepcopy(src_item)
		if src_item.prompt is not None:
			dst_item.prompt = prompt_remap[src_item.prompt]
		extracted.session_mgrs[dst] = dst_item

	for src, dst in knowledge_mgr_remap.items():
		src_item = config.knowledge_mgrs[src]
		dst_item = copy.deepcopy(src_item)
		if src_item.content_db is not None:
			dst_item.content_db = content_db_remap[src_item.content_db]
		if src_item.index_db is not None:
			dst_item.index_db = index_db_remap[src_item.index_db]
		extracted.knowledge_mgrs[dst] = dst_item

	for src, dst in tool_remap.items():
		src_item = config.tools[src]
		dst_item = copy.deepcopy(src_item)
		extracted.tools[dst] = dst_item

	for src, dst in agent_options_remap.items():
		src_item = config.agent_options[src]
		dst_item = copy.deepcopy(src_item)
		extracted.agent_options[dst] = dst_item

	info_remap          [None] = None
	app_options_remap   [None] = None
	model_remap         [None] = None
	embedding_remap     [None] = None
	prompt_remap        [None] = None
	content_db_remap    [None] = None
	index_db_remap      [None] = None
	memory_mgr_remap    [None] = None
	session_mgr_remap   [None] = None
	knowledge_mgr_remap [None] = None
	tool_remap          [None] = None
	agent_options_remap [None] = None

	if True:
		extracted.info = info_remap[config.info]

	if True:
		extracted.options = app_options_remap[config.options]

	if True:
		extracted.port = config.port

	for src, dst in agent_remap.items():
		src_item = config.agents[src]
		dst_item = copy.deepcopy(src_item)
		dst_item.backend       = 0
		dst_item.info          = info_remap          [src_item.info         ]
		dst_item.prompt        = prompt_remap        [src_item.prompt       ]
		dst_item.options       = agent_options_remap [src_item.options      ]
		dst_item.content_db    = content_db_remap    [src_item.content_db   ]
		dst_item.memory_mgr    = memory_mgr_remap    [src_item.memory_mgr   ]
		dst_item.session_mgr   = session_mgr_remap   [src_item.session_mgr  ]
		dst_item.knowledge_mgr = knowledge_mgr_remap [src_item.knowledge_mgr]
		dst_item.tools         = []
		if src_item.tools is not None:
			for src_tool in src_item.tools:
				dst_tool = tool_remap[src_tool]
				dst_item.tools.append(dst_tool)
		extracted.agents[dst] = dst_item

	return (extracted, agent_remap, tool_remap)


def load_config(file_path: str) -> AppConfig:
	try:
		with open(file_path, "r") as f:
			data = json.load(f)
		config = AppConfig(**data)
		return config
	except Exception as e:
		print(f"Error loading config: {e}")
		return None


_backends: Dict[Tuple[str, str], Callable] = dict()


def register_backend(backend: BackendConfig, ctor: Callable) -> bool:
	global _backends
	key = (backend.type, backend.version)
	_backends[key] = (copy.deepcopy(backend), ctor)
	return True


def get_backends() -> Dict[Tuple[str, str], Callable]:
	global _backends
	result = copy.deepcopy(_backends)
	return result


class AgentApp:

	def __init__(self, config: AppConfig):
		self.config = copy.deepcopy(config)


	def generate_app(self, agent_index: int) -> FastAPI:
		raise NotImplementedError("Subclasses must implement the generate_app method")


	async def run_agent(self, agent_index: int, *args, **kwargs) -> Any:
		raise NotImplementedError("Subclasses must implement the run_agent method")


	async def run_tool(self, tool_index: int, *args, **kwargs) -> Any:
		raise NotImplementedError("Subclasses must implement the run_tool method")


	def close(self) -> bool:
		raise NotImplementedError("Subclasses must implement the close method")
