# schema_workflow

from __future__ import annotations

from enum     import Enum
from pydantic import BaseModel, ConfigDict
from typing   import Annotated, Any, Dict, Generic, List, Optional, TypeVar, Union


class FieldRole(str, Enum):
	CONSTANT     = "constant"
	INPUT        = "input"
	OUTPUT       = "output"
	MULTI_INPUT  = "multi_input"
	MULTI_OUTPUT = "multi_output"


class BaseType(BaseModel):
	type : Annotated[str          , FieldRole.CONSTANT] = "base_type"
	data : Annotated[Optional[Any], FieldRole.INPUT   ] = None


class BaseConfig(BaseType):
	type : Annotated[str, FieldRole.CONSTANT] = "base_config"

	@property
	def get(self) -> Annotated[BaseConfig, FieldRole.OUTPUT]: # type: ignore
		return self


class InfoConfig(BaseConfig):
	type         : Annotated[str                , FieldRole.CONSTANT] = "info_config"
	version      : Annotated[Optional[str      ], FieldRole.INPUT   ] = None
	name         : Annotated[Optional[str      ], FieldRole.INPUT   ] = None
	author       : Annotated[Optional[str      ], FieldRole.INPUT   ] = None
	description  : Annotated[Optional[str      ], FieldRole.INPUT   ] = None
	instructions : Annotated[Optional[List[str]], FieldRole.INPUT   ] = None

	@property
	def get(self) -> Annotated[InfoConfig, FieldRole.OUTPUT]: # type: ignore
		return self


DEFAULT_BACKEND_NAME     : str  = "agno"
DEFAULT_BACKEND_VERSION  : str  = ""
DEFAULT_BACKEND_FALLBACK : bool = False


class BackendConfig(BaseConfig):
	type     : Annotated[str , FieldRole.CONSTANT] = "backend_config"
	name     : Annotated[str , FieldRole.INPUT   ] = DEFAULT_BACKEND_NAME
	version  : Annotated[str , FieldRole.INPUT   ] = DEFAULT_BACKEND_VERSION
	fallback : Annotated[bool, FieldRole.INPUT   ] = DEFAULT_BACKEND_FALLBACK

	@property
	def get(self) -> Annotated[BackendConfig, FieldRole.OUTPUT]: # type: ignore
		return self


DEFAULT_MODEL_SOURCE   : str  = "ollama"
DEFAULT_MODEL_ID       : str  = "mistral"
DEFAULT_MODEL_VERSION  : str  = ""
DEFAULT_MODEL_FALLBACK : bool = False


class ModelConfig(BaseConfig):
	type     : Annotated[str , FieldRole.CONSTANT] = "model_config"
	source   : Annotated[str , FieldRole.INPUT   ] = DEFAULT_MODEL_SOURCE
	id       : Annotated[str , FieldRole.INPUT   ] = DEFAULT_MODEL_ID
	version  : Annotated[str , FieldRole.INPUT   ] = DEFAULT_MODEL_VERSION
	fallback : Annotated[bool, FieldRole.INPUT   ] = DEFAULT_MODEL_FALLBACK

	@property
	def get(self) -> Annotated[ModelConfig, FieldRole.OUTPUT]: # type: ignore
		return self


DEFAULT_EMBEDDING_SOURCE   : str  = "ollama"
DEFAULT_EMBEDDING_ID       : str  = "mistral"
DEFAULT_EMBEDDING_VERSION  : str  = ""
DEFAULT_EMBEDDING_FALLBACK : bool = False


class EmbeddingConfig(BaseConfig):
	type     : Annotated[str , FieldRole.CONSTANT] = "embedding_config"
	source   : Annotated[str , FieldRole.INPUT   ] = DEFAULT_EMBEDDING_SOURCE
	id       : Annotated[str , FieldRole.INPUT   ] = DEFAULT_EMBEDDING_ID
	version  : Annotated[str , FieldRole.INPUT   ] = DEFAULT_EMBEDDING_VERSION
	fallback : Annotated[bool, FieldRole.INPUT   ] = DEFAULT_EMBEDDING_FALLBACK

	@property
	def get(self) -> Annotated[EmbeddingConfig, FieldRole.OUTPUT]: # type: ignore
		return self


class PromptConfig(BaseConfig):
	type         : Annotated[str                      , FieldRole.CONSTANT] = "prompt_config"
	model        : Annotated[Optional[ModelConfig    ], FieldRole.INPUT   ] = None
	embedding    : Annotated[Optional[EmbeddingConfig], FieldRole.INPUT   ] = None
	description  : Annotated[Optional[str            ], FieldRole.INPUT   ] = None
	instructions : Annotated[Optional[List[str]      ], FieldRole.INPUT   ] = None
	override     : Annotated[Optional[str            ], FieldRole.INPUT   ] = None

	@property
	def get(self) -> Annotated[PromptConfig, FieldRole.OUTPUT]: # type: ignore
		return self


DEFAULT_CONTENT_DB_ENGINE               : str  = "sqlite"
DEFAULT_CONTENT_DB_URL                  : str  = "storage/content"
DEFAULT_CONTENT_DB_MEMORY_TABLE_NAME    : str  = "memory"
DEFAULT_CONTENT_DB_SESSION_TABLE_NAME   : str  = "session"
DEFAULT_CONTENT_DB_KNOWLEDGE_TABLE_NAME : str  = "knowledge"
DEFAULT_CONTENT_DB_FALLBACK             : bool = False


class ContentDBConfig(BaseConfig):
	type                 : Annotated[str , FieldRole.CONSTANT] = "content_db_config"
	engine               : Annotated[str , FieldRole.INPUT   ] = DEFAULT_CONTENT_DB_ENGINE
	url                  : Annotated[str , FieldRole.INPUT   ] = DEFAULT_CONTENT_DB_URL
	memory_table_name    : Annotated[str , FieldRole.INPUT   ] = DEFAULT_CONTENT_DB_MEMORY_TABLE_NAME
	session_table_name   : Annotated[str , FieldRole.INPUT   ] = DEFAULT_CONTENT_DB_SESSION_TABLE_NAME
	knowledge_table_name : Annotated[str , FieldRole.INPUT   ] = DEFAULT_CONTENT_DB_KNOWLEDGE_TABLE_NAME
	fallback             : Annotated[bool, FieldRole.INPUT   ] = DEFAULT_CONTENT_DB_FALLBACK

	@property
	def get(self) -> Annotated[ContentDBConfig, FieldRole.OUTPUT]: # type: ignore
		return self


DEFAULT_INDEX_DB_ENGINE      : str  = "lancedb"
DEFAULT_INDEX_DB_URL         : str  = "storage/index"
DEFAULT_INDEX_DB_SEARCH_TYPE : str  = "hybrid"
DEFAULT_INDEX_DB_FALLBACK    : bool = False


class IndexDBConfig(BaseConfig):
	type        : Annotated[str                      , FieldRole.CONSTANT] = "index_db_config"
	engine      : Annotated[str                      , FieldRole.INPUT   ] = DEFAULT_INDEX_DB_ENGINE
	url         : Annotated[str                      , FieldRole.INPUT   ] = DEFAULT_INDEX_DB_URL
	embedding   : Annotated[Optional[EmbeddingConfig], FieldRole.INPUT   ] = None
	search_type : Annotated[str                      , FieldRole.INPUT   ] = DEFAULT_INDEX_DB_SEARCH_TYPE
	fallback    : Annotated[bool                     , FieldRole.INPUT   ] = DEFAULT_INDEX_DB_FALLBACK

	@property
	def get(self) -> Annotated[IndexDBConfig, FieldRole.OUTPUT]: # type: ignore
		return self


DEFAULT_MEMORY_MANAGER_QUERY   : bool = False
DEFAULT_MEMORY_MANAGER_UPDATE  : bool = False
DEFAULT_MEMORY_MANAGER_MANAGED : bool = False


class MemoryManagerConfig(BaseConfig):
	type    : Annotated[str                   , FieldRole.CONSTANT] = "memory_manager_config"
	query   : Annotated[bool                  , FieldRole.INPUT   ] = DEFAULT_MEMORY_MANAGER_QUERY
	update  : Annotated[bool                  , FieldRole.INPUT   ] = DEFAULT_MEMORY_MANAGER_UPDATE
	managed : Annotated[bool                  , FieldRole.INPUT   ] = DEFAULT_MEMORY_MANAGER_MANAGED
	prompt  : Annotated[Optional[PromptConfig], FieldRole.INPUT   ] = None

	@property
	def get(self) -> Annotated[MemoryManagerConfig, FieldRole.OUTPUT]: # type: ignore
		return self


DEFAULT_SESSION_MANAGER_QUERY        : bool = False
DEFAULT_SESSION_MANAGER_UPDATE       : bool = False
DEFAULT_SESSION_MANAGER_HISTORY_SIZE : int  = 10
DEFAULT_SESSION_MANAGER_SUMMARIZE    : bool = False


class SessionManagerConfig(BaseConfig):
	type         : Annotated[str                   , FieldRole.CONSTANT] = "session_manager_config"
	query        : Annotated[bool                  , FieldRole.INPUT   ] = DEFAULT_SESSION_MANAGER_QUERY
	update       : Annotated[bool                  , FieldRole.INPUT   ] = DEFAULT_SESSION_MANAGER_UPDATE
	summarize    : Annotated[bool                  , FieldRole.INPUT   ] = DEFAULT_SESSION_MANAGER_SUMMARIZE
	history_size : Annotated[int                   , FieldRole.INPUT   ] = DEFAULT_SESSION_MANAGER_HISTORY_SIZE
	prompt       : Annotated[Optional[PromptConfig], FieldRole.INPUT   ] = None

	@property
	def get(self) -> Annotated[SessionManagerConfig, FieldRole.OUTPUT]: # type: ignore
		return self


DEFAULT_KNOWLEDGE_MANAGER_QUERY       : bool = True
DEFAULT_KNOWLEDGE_MANAGER_MAX_RESULTS : int  = 10

class KnowledgeManagerConfig(BaseConfig):
	type        : Annotated[str                      , FieldRole.CONSTANT] = "knowledge_manager_config"
	query       : Annotated[bool                     , FieldRole.INPUT   ] = DEFAULT_KNOWLEDGE_MANAGER_QUERY
	description : Annotated[Optional[str]            , FieldRole.INPUT   ] = None
	content_db  : Annotated[Optional[ContentDBConfig], FieldRole.INPUT   ] = None
	index_db    : Annotated[IndexDBConfig            , FieldRole.INPUT   ] = None
	max_results : Annotated[int                      , FieldRole.INPUT   ] = DEFAULT_KNOWLEDGE_MANAGER_MAX_RESULTS
	urls        : Annotated[Optional[List[str]]      , FieldRole.INPUT   ] = None

	@property
	def get(self) -> Annotated[KnowledgeManagerConfig, FieldRole.OUTPUT]: # type: ignore
		return self


DEFAULT_TOOL_FALLBACK : bool = False


class ToolConfig(BaseConfig):
	type     : Annotated[str                     , FieldRole.CONSTANT] = "tool_config"
	name     : Annotated[str                     , FieldRole.INPUT   ]
	args     : Annotated[Optional[Dict[str, Any]], FieldRole.INPUT   ] = None
	ref      : Annotated[str                     , FieldRole.INPUT   ] = None
	fallback : Annotated[bool                    , FieldRole.INPUT   ] = DEFAULT_TOOL_FALLBACK

	@property
	def get(self) -> Annotated[ToolConfig, FieldRole.OUTPUT]: # type: ignore
		return self


DEFAULT_AGENT_OPTIONS_MARKDOWN : bool = True


class AgentOptionsConfig(BaseConfig):
	type     : Annotated[str , FieldRole.CONSTANT] = "agent_options_config"
	markdown : Annotated[bool, FieldRole.INPUT   ] = DEFAULT_AGENT_OPTIONS_MARKDOWN

	@property
	def get(self) -> Annotated[AgentOptionsConfig, FieldRole.OUTPUT]: # type: ignore
		return self


class AgentConfig(BaseConfig):
	type          : Annotated[str                             , FieldRole.CONSTANT   ] = "agent_config"
	info          : Annotated[Optional[InfoConfig]            , FieldRole.INPUT      ] = None
	options       : Annotated[Optional[AgentOptionsConfig]    , FieldRole.INPUT      ] = None
	backend       : Annotated[BackendConfig                   , FieldRole.INPUT      ]
	prompt        : Annotated[PromptConfig                    , FieldRole.INPUT      ]
	content_db    : Annotated[Optional[ContentDBConfig]       , FieldRole.INPUT      ] = None
	memory_mgr    : Annotated[Optional[MemoryManagerConfig]   , FieldRole.INPUT      ] = None
	session_mgr   : Annotated[Optional[SessionManagerConfig]  , FieldRole.INPUT      ] = None
	knowledge_mgr : Annotated[Optional[KnowledgeManagerConfig], FieldRole.INPUT      ] = None
	tools         : Annotated[Optional[List[ToolConfig]]      , FieldRole.MULTI_INPUT] = []

	@property
	def get(self) -> Annotated[AgentConfig, FieldRole.OUTPUT]: # type: ignore
		return self


TValue = TypeVar("TValue")


class Message(BaseModel, Generic[TValue]):
	model_config = ConfigDict(arbitrary_types_allowed=True)

	type  : str
	value : Optional[TValue] = None


MessageAny   = Union[Any           , Message[Any           ]]
MessageBool  = Union[bool          , Message[bool          ]]
MessageInt   = Union[int           , Message[int           ]]
MessageFloat = Union[float         , Message[float         ]]
MessageStr   = Union[str           , Message[str           ]]
MessageList  = Union[List[Any]     , Message[List[Any]     ]]
MessageDict  = Union[Dict[str, Any], Message[Dict[str, Any]]]


SkipMessage : MessageAny = Message(type="skip", value=None)


class Edge(BaseType):
	type        : Annotated[str          , FieldRole.CONSTANT] = "edge"
	source      : Annotated[int          , FieldRole.INPUT   ]
	target      : Annotated[int          , FieldRole.INPUT   ]
	source_slot : Annotated[str          , FieldRole.INPUT   ]
	target_slot : Annotated[str          , FieldRole.INPUT   ]
	extra       : Annotated[Optional[str], FieldRole.INPUT   ]


class BaseNode(BaseType):
	type   : Annotated[str          , FieldRole.CONSTANT] = "base_node"
	extra  : Annotated[Optional[str], FieldRole.INPUT   ]


class StartNode(BaseNode):
	type  : Annotated[str       , FieldRole.CONSTANT] = "start_node"
	start : Annotated[MessageAny, FieldRole.OUTPUT  ]


class EndNode(BaseNode):
	type : Annotated[str       , FieldRole.CONSTANT] = "end_node"
	end  : Annotated[MessageAny, FieldRole.INPUT   ]


class SinkNode(BaseNode):
	type : Annotated[str       , FieldRole.CONSTANT] = "sink_node"
	sink : Annotated[MessageAny, FieldRole.INPUT   ]


DEFAULT_SCRIPT_NODE_LANG   : MessageStr = Message(type="", value="python")
DEFAULT_SCRIPT_NODE_SCRIPT : MessageStr = Message(type="", value="return None")


class ScriptNode(BaseNode):
	type   : Annotated[str       , FieldRole.CONSTANT] = "script_node"
	lang   : Annotated[MessageStr, FieldRole.INPUT   ] = DEFAULT_SCRIPT_NODE_LANG
	script : Annotated[MessageStr, FieldRole.INPUT   ] = DEFAULT_SCRIPT_NODE_SCRIPT


class TransformNode(ScriptNode):
	type   : Annotated[str       , FieldRole.CONSTANT] = "transform_node"
	source : Annotated[MessageAny, FieldRole.INPUT   ]
	target : Annotated[MessageAny, FieldRole.OUTPUT  ]


class SwitchNode(ScriptNode):
	type     : Annotated[str                  , FieldRole.CONSTANT    ] = "switch_node"
	value    : Annotated[MessageAny           , FieldRole.INPUT       ]
	cases    : Annotated[Dict[str, MessageAny], FieldRole.MULTI_OUTPUT]
	default  : Annotated[MessageAny           , FieldRole.OUTPUT      ]


class SplitNode(ScriptNode):
	type     : Annotated[str                  , FieldRole.CONSTANT    ] = "split_node"
	mapping  : Annotated[Dict[str, str       ], FieldRole.INPUT       ]
	source   : Annotated[Dict[str, MessageAny], FieldRole.INPUT       ]
	targets  : Annotated[Dict[str, MessageAny], FieldRole.MULTI_OUTPUT]


DEFAULT_MERGE_NODE_STRATEGY : MessageStr = Message(type="", value="first")


class MergeNode(BaseNode):
	type     : Annotated[str                  , FieldRole.CONSTANT   ] = "merge_node"
	strategy : Annotated[MessageAny           , FieldRole.INPUT      ] = DEFAULT_MERGE_NODE_STRATEGY
	sources  : Annotated[Dict[str, MessageAny], FieldRole.MULTI_INPUT]
	target   : Annotated[MessageAny           , FieldRole.OUTPUT     ]


class UserInputNode(BaseNode):
	type    : Annotated[str       , FieldRole.CONSTANT] = "user_input_node"
	query   : Annotated[MessageAny, FieldRole.INPUT   ]
	message : Annotated[MessageAny, FieldRole.OUTPUT  ]


class UserOutputNode(BaseNode):
	type    : Annotated[str       , FieldRole.CONSTANT] = "user_output_node"
	message : Annotated[MessageAny, FieldRole.INPUT   ]
	get     : Annotated[MessageAny, FieldRole.OUTPUT  ]


MessageToolConfig = Union[ToolConfig, Message[ToolConfig]]


class ToolNode(BaseNode):
	type      : Annotated[str              , FieldRole.CONSTANT] = "tool_node"
	config    : Annotated[MessageToolConfig, FieldRole.INPUT   ]
	arguments : Annotated[MessageDict      , FieldRole.INPUT   ]
	source    : Annotated[MessageAny       , FieldRole.INPUT   ]
	target    : Annotated[MessageAny       , FieldRole.OUTPUT  ]


MessageAgentConfig = Union[AgentConfig, Message[AgentConfig]]


class AgentNode(BaseNode):
	type     : Annotated[str               , FieldRole.CONSTANT] = "agent_node"
	config   : Annotated[MessageAgentConfig, FieldRole.INPUT   ]
	request  : Annotated[MessageAny        , FieldRole.INPUT   ]
	response : Annotated[MessageAny        , FieldRole.OUTPUT  ]


DEFAULT_WORKFLOW_OPTIONS_TAG : int = 0


class WorkflowOptionsConfig(BaseConfig):
	type : Annotated[str, FieldRole.CONSTANT] = "workflow_options_config"
	tag  : Annotated[int, FieldRole.INPUT   ] = DEFAULT_WORKFLOW_OPTIONS_TAG

	@property
	def get(self) -> Annotated[WorkflowOptionsConfig, FieldRole.OUTPUT]: # type: ignore
		return self


class Workflow(BaseConfig):
	type     : Annotated[str                            , FieldRole.CONSTANT] = "workflow"
	info     : Annotated[Optional[InfoConfig]           , FieldRole.INPUT   ] = None
	options  : Annotated[Optional[WorkflowOptionsConfig], FieldRole.INPUT   ] = None
	nodes    : Annotated[Optional[List[BaseNode]]       , FieldRole.INPUT   ] = []
	edges    : Annotated[Optional[List[Edge]]           , FieldRole.INPUT   ] = []

	@property
	def get(self) -> Annotated[Workflow, FieldRole.OUTPUT]: # type: ignore
		return self
