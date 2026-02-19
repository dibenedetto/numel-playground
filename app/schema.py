# schema.py

from __future__ import annotations


from enum       import Enum
from pydantic   import BaseModel, Field
from typing     import Annotated, Any, Dict, List, Literal, Optional, Union
from uuid       import uuid4


def node_info(title: str = None, description: str = None, icon: str = None, section: str = "Miscellanea", visible: bool = True, **kwargs):
	def decorator(cls):
		return cls
	return decorator


def node_button(id: str, label: str = "", icon: str = "", position: str = "bottom", **kwargs):
	def decorator(cls):
		return cls
	return decorator


def node_dropzone(accept: str = "*", area: str = "content", label: str = "Drop file here", reject: str = "File type not accepted", **kwargs):
	def decorator(cls):
		return cls
	return decorator


def node_chat(**kwargs):
	def decorator(cls):
		return cls
	return decorator


@node_info(visible=False)
class FieldRole(str, Enum):
	ANNOTATION   = "annotation"
	CONSTANT     = "constant"
	INPUT        = "input"
	OUTPUT       = "output"
	MULTI_INPUT  = "multi_input"
	MULTI_OUTPUT = "multi_output"


def generate_id():
	return str(uuid4())


@node_info(visible=False)
class BaseType(BaseModel):
	type  : Annotated[Literal["base_type"]    , FieldRole.CONSTANT  ] = "base_type"
	id    : Annotated[str                     , FieldRole.ANNOTATION] = Field(default_factory=generate_id)
	extra : Annotated[Optional[Dict[str, Any]], FieldRole.INPUT     ] = None

	@property
	def get(self) -> Annotated[BaseType, FieldRole.OUTPUT]:
		return self


@node_info(visible=False)
class ComponentType(BaseModel):
	type : Annotated[Literal["component_type"], FieldRole.CONSTANT] = "component_type"

	@property
	def get(self) -> Annotated[ComponentType, FieldRole.OUTPUT]:
		return self


@node_info(
	title       = "Source Meta",
	description = "Holds meta information",
	icon        = "ⓘ",
	section     = "Data Sources",
	visible     = True
)
class SourceMeta(ComponentType):
	type        : Annotated[Literal["source_meta"], FieldRole.CONSTANT] = "source_meta"
	name        : Annotated[Optional[str  ]       , FieldRole.INPUT   ] = None
	description : Annotated[Optional[str  ]       , FieldRole.INPUT   ] = None
	source      : Annotated[Optional[str  ]       , FieldRole.INPUT   ] = None
	mime_type   : Annotated[Optional[str  ]       , FieldRole.INPUT   ] = None
	format      : Annotated[Optional[str  ]       , FieldRole.INPUT   ] = None
	streamable  : Annotated[Optional[bool ]       , FieldRole.INPUT   ] = None
	size        : Annotated[Optional[int  ]       , FieldRole.INPUT   ] = None
	duration    : Annotated[Optional[float]       , FieldRole.INPUT   ] = None
	sampling    : Annotated[Optional[float]       , FieldRole.INPUT   ] = None
	rate        : Annotated[Optional[float]       , FieldRole.INPUT   ] = None
	encoding    : Annotated[Optional[str  ]       , FieldRole.INPUT   ] = None
	frames      : Annotated[Optional[int  ]       , FieldRole.INPUT   ] = None

	@property
	def get(self) -> Annotated[SourceMeta, FieldRole.OUTPUT]:
		return self


DEFAULT_EDGE_PREVIEW : bool = False


@node_info(visible=False)
class Edge(ComponentType):
	type        : Annotated[Literal["edge"], FieldRole.CONSTANT  ] = "edge"
	preview     : Annotated[bool           , FieldRole.ANNOTATION] = DEFAULT_EDGE_PREVIEW
	loop        : Annotated[bool           , FieldRole.ANNOTATION] = False  # True for loop-back edges (visual hint)
	source      : Annotated[int            , FieldRole.INPUT     ] = None
	target      : Annotated[int            , FieldRole.INPUT     ] = None
	source_slot : Annotated[str            , FieldRole.INPUT     ] = None
	target_slot : Annotated[str            , FieldRole.INPUT     ] = None

	@property
	def get(self) -> Annotated[Edge, FieldRole.OUTPUT]:
		return self


@node_info(visible=False)
class NativeType(BaseType):
	type  : Annotated[Literal["native_type"], FieldRole.CONSTANT] = "native_type"
	value : Annotated[Any                   , FieldRole.INPUT   ] = None

	@property
	def get(self) -> Annotated[Any, FieldRole.OUTPUT]:
		return self.value


@node_info(
	title       = "Boolean Constant",
	description = "Holds a boolean constant",
	icon        = "⏻",
	section     = "Native Types",
	visible     = True
)
class NativeBoolean(NativeType):
	"""Constant boolean value. Set value=true|false. Wire get→any bool input."""
	type  : Annotated[Literal["native_boolean"], FieldRole.CONSTANT] = "native_boolean"
	value : Annotated[bool                     , FieldRole.INPUT   ] = False

	@property
	def get(self) -> Annotated[bool, FieldRole.OUTPUT]:
		return self.value


@node_info(
	title       = "Integer Number",
	description = "Holds an integer number",
	icon        = "🔢",
	section     = "Native Types",
	visible     = True
)
class NativeInteger(NativeType):
	"""Constant integer value. Set value to any integer. Wire get→any int input."""
	type  : Annotated[Literal["native_integer"], FieldRole.CONSTANT] = "native_integer"
	value : Annotated[int                      , FieldRole.INPUT   ] = 0

	@property
	def get(self) -> Annotated[int, FieldRole.OUTPUT]:
		return self.value


@node_info(
	title       = "Real Number",
	description = "Holds a real number",
	icon        = "ℛ",
	section     = "Native Types",
	visible     = True
)
class NativeReal(NativeType):
	"""Constant floating-point value. Set value to any number. Wire get→any float input."""
	type  : Annotated[Literal["native_real"], FieldRole.CONSTANT] = "native_real"
	value : Annotated[float                 , FieldRole.INPUT   ] = 0.0

	@property
	def get(self) -> Annotated[float, FieldRole.OUTPUT]:
		return self.value


@node_info(
	title       = "Character String",
	description = "Holds a string",
	icon        = "➰",
	section     = "Native Types",
	visible     = True
)
class NativeString(NativeType):
	"""Constant string value. Set value to any text. Wire get→any string input."""
	type  : Annotated[Literal["native_string"], FieldRole.CONSTANT] = "native_string"
	value : Annotated[str                     , FieldRole.INPUT   ] = ""

	@property
	def get(self) -> Annotated[str, FieldRole.OUTPUT]:
		return self.value


@node_info(
	title       = "List",
	description = "Holds a list of values",
	icon        = "☰",
	section     = "Native Types",
	visible     = True
)
class NativeList(NativeType):
	"""Constant list value. Set value to a JSON array. Wire get→any list input."""
	type  : Annotated[Literal["native_list"], FieldRole.CONSTANT] = "native_list"
	value : Annotated[List[Any]             , FieldRole.INPUT   ] = []

	@property
	def get(self) -> Annotated[List[Any], FieldRole.OUTPUT]:
		return self.value


@node_info(
	title       = "Dictionary",
	description = "Holds a key-value dictionary",
	icon        = "📔",
	section     = "Native Types",
	visible     = True
)
class NativeDictionary(NativeType):
	"""Constant dict value. Set value to a JSON object. Wire get→any dict input."""
	type  : Annotated[Literal["native_dictionary"], FieldRole.CONSTANT] = "native_dictionary"
	value : Annotated[Dict[str, Any]              , FieldRole.INPUT   ] = {}

	@property
	def get(self) -> Annotated[Dict[str, Any], FieldRole.OUTPUT]:
		return self.value


DEFAULT_TENSOR_DTYPE  : str  = "float32"


@node_info(visible=False)
class TensorType(BaseType):
	type   : Annotated[Literal["tensor_type"], FieldRole.CONSTANT] = "tensor_type"
	meta   : Annotated[Optional[SourceMeta]  , FieldRole.INPUT   ] = None
	dtype  : Annotated[str                   , FieldRole.INPUT   ] = DEFAULT_TENSOR_DTYPE
	shape  : Annotated[List[int]             , FieldRole.INPUT   ] = []
	data   : Annotated[Any                   , FieldRole.INPUT   ] = []

	@property
	def get(self) -> Annotated[Any, FieldRole.OUTPUT]:
		return self.data


@node_info(
	title       = "Data Tensor",
	description = "Holds tensor data",
	icon        = "🔟",
	section     = "Data Sources",
	visible     = True
)
class DataTensor(TensorType):
	"""Generic data tensor value. Set dtype (e.g., 'float32'), shape (list of ints), and data (nested list matching shape). Wire get→any tensor input."""
	type : Annotated[Literal["data_tensor"], FieldRole.CONSTANT] = "data_tensor"


@node_info(visible=False)
class ConfigType(BaseType):
	type : Annotated[Literal["config_type"], FieldRole.CONSTANT] = "config_type"

	@property
	def get(self) -> Annotated[ConfigType, FieldRole.OUTPUT]:
		return self


DEFAULT_OPTIONS_NAME        : str  = "Zoe"
DEFAULT_OPTIONS_DESCRIPTION : str  = None


@node_info(visible=False)
class OptionsType(BaseType):
	type        : Annotated[Literal["options_type"], FieldRole.CONSTANT] = "options_type"
	name        : Annotated[Optional[str]          , FieldRole.INPUT   ] = DEFAULT_OPTIONS_NAME
	description : Annotated[Optional[str]          , FieldRole.INPUT   ] = DEFAULT_OPTIONS_DESCRIPTION

	@property
	def get(self) -> Annotated[OptionsType, FieldRole.OUTPUT]:
		return self


DEFAULT_BACKEND_NAME     : str  = "agno"
DEFAULT_BACKEND_VERSION  : str  = ""
DEFAULT_BACKEND_FALLBACK : bool = False


@node_info(
	title       = "Backend",
	description = "Holds backend framework reference",
	icon        = "⚙️",
	section     = "Configurations",
	visible     = True
)
class BackendConfig(ConfigType):
	"""AI backend engine config. Set name='agno' (default and only supported engine). Wire get→agent_config.backend."""
	type     : Annotated[Literal["backend_config"], FieldRole.CONSTANT] = "backend_config"
	name     : Annotated[str                      , FieldRole.INPUT   ] = DEFAULT_BACKEND_NAME
	version  : Annotated[Optional[str]            , FieldRole.INPUT   ] = DEFAULT_BACKEND_VERSION
	fallback : Annotated[bool                     , FieldRole.INPUT   ] = DEFAULT_BACKEND_FALLBACK

	@property
	def get(self) -> Annotated[BackendConfig, FieldRole.OUTPUT]:
		return self


DEFAULT_MODEL_SOURCE   : str  = "ollama"
DEFAULT_MODEL_NAME     : str  = "mistral"
DEFAULT_MODEL_VERSION  : str  = ""
DEFAULT_MODEL_FALLBACK : bool = False


@node_info(
	title       = "Language Model",
	description = "Holds language model reference",
	icon        = "🗣️",
	section     = "Configurations",
	visible     = True
)
class ModelConfig(ConfigType):
	"""Language model reference. Set source (ollama/openai/anthropic/groq/google) and name. Wire get→agent_config.model or memory_manager_config.model."""
	type     : Annotated[Literal["model_config"], FieldRole.CONSTANT] = "model_config"
	source   : Annotated[str                    , FieldRole.INPUT   ] = Field(default=DEFAULT_MODEL_SOURCE, json_schema_extra={"options_source": "model_sources"})
	name     : Annotated[str                    , FieldRole.INPUT   ] = Field(default=DEFAULT_MODEL_NAME, json_schema_extra={"options_source": "model_names"})
	version  : Annotated[Optional[str]          , FieldRole.INPUT   ] = DEFAULT_MODEL_VERSION
	fallback : Annotated[bool                   , FieldRole.INPUT   ] = DEFAULT_MODEL_FALLBACK

	@property
	def get(self) -> Annotated[ModelConfig, FieldRole.OUTPUT]:
		return self


DEFAULT_EMBEDDING_SOURCE   : str  = "ollama"
DEFAULT_EMBEDDING_NAME     : str  = "mistral"
DEFAULT_EMBEDDING_VERSION  : str  = ""
DEFAULT_EMBEDDING_FALLBACK : bool = False


@node_info(
	title       = "Embedding Model",
	description = "Holds embedding model reference",
	icon        = "📦",
	section     = "Configurations",
	visible     = True
)
class EmbeddingConfig(ConfigType):
	"""Embedding model reference for vector search. Set source+name matching your model provider. Wire get→index_db_config.embedding."""
	type     : Annotated[Literal["embedding_config"], FieldRole.CONSTANT] = "embedding_config"
	source   : Annotated[str                        , FieldRole.INPUT   ] = Field(default=DEFAULT_EMBEDDING_SOURCE, json_schema_extra={"options_source": "model_sources"})
	name     : Annotated[str                        , FieldRole.INPUT   ] = Field(default=DEFAULT_EMBEDDING_NAME, json_schema_extra={"options_source": "model_names"})
	version  : Annotated[Optional[str]              , FieldRole.INPUT   ] = DEFAULT_EMBEDDING_VERSION
	fallback : Annotated[bool                       , FieldRole.INPUT   ] = DEFAULT_EMBEDDING_FALLBACK

	@property
	def get(self) -> Annotated[EmbeddingConfig, FieldRole.OUTPUT]:
		return self


DEFAULT_CONTENT_DB_ENGINE               : str  = "sqlite"
DEFAULT_CONTENT_DB_URL                  : str  = "storage/content"
DEFAULT_CONTENT_DB_MEMORY_TABLE_NAME    : str  = "memory"
DEFAULT_CONTENT_DB_SESSION_TABLE_NAME   : str  = "session"
DEFAULT_CONTENT_DB_KNOWLEDGE_TABLE_NAME : str  = "knowledge"
DEFAULT_CONTENT_DB_FALLBACK             : bool = False


# @node_button(id="export", label="Export", icon="📤", position="bottom")
@node_info(
	title       = "Content Database",
	description = "Holds raw contents",
	icon        = "🛢",
	section     = "Configurations",
	visible     = True
)
class ContentDBConfig(ConfigType):
	"""Raw document content database (SQLite by default). Set engine and url (storage path). Wire get→knowledge_manager_config.content_db."""
	type                 : Annotated[Literal["content_db_config"], FieldRole.CONSTANT  ] = "content_db_config"
	interactable         : Annotated[bool                        , FieldRole.ANNOTATION] = DEFAULT_EDGE_PREVIEW
	engine               : Annotated[str                         , FieldRole.INPUT     ] = DEFAULT_CONTENT_DB_ENGINE
	url                  : Annotated[str                         , FieldRole.INPUT     ] = DEFAULT_CONTENT_DB_URL
	memory_table_name    : Annotated[str                         , FieldRole.INPUT     ] = DEFAULT_CONTENT_DB_MEMORY_TABLE_NAME
	session_table_name   : Annotated[str                         , FieldRole.INPUT     ] = DEFAULT_CONTENT_DB_SESSION_TABLE_NAME
	knowledge_table_name : Annotated[str                         , FieldRole.INPUT     ] = DEFAULT_CONTENT_DB_KNOWLEDGE_TABLE_NAME
	fallback             : Annotated[bool                        , FieldRole.INPUT     ] = DEFAULT_CONTENT_DB_FALLBACK

	@property
	def get(self) -> Annotated[ContentDBConfig, FieldRole.OUTPUT]:
		return self


DEFAULT_INDEX_DB_ENGINE      : str  = "lancedb"
DEFAULT_INDEX_DB_URL         : str  = "storage/index"
DEFAULT_INDEX_DB_SEARCH_TYPE : str  = "hybrid"
DEFAULT_INDEX_DB_TABLE_NAME  : str  = "documents"
DEFAULT_INDEX_DB_FALLBACK    : bool = False


@node_info(
	title       = "Vector Database",
	description = "Holds vector contents",
	icon        = "↗",
	section     = "Configurations",
	visible     = True
)
class IndexDBConfig(ConfigType):
	"""Vector index database for semantic search (lancedb by default). Requires embedding_config. Wire get→knowledge_manager_config.index_db."""
	type        : Annotated[Literal["index_db_config"], FieldRole.CONSTANT] = "index_db_config"
	engine      : Annotated[str                       , FieldRole.INPUT   ] = DEFAULT_INDEX_DB_ENGINE
	url         : Annotated[str                       , FieldRole.INPUT   ] = DEFAULT_INDEX_DB_URL
	embedding   : Annotated[EmbeddingConfig           , FieldRole.INPUT   ] = None
	search_type : Annotated[str                       , FieldRole.INPUT   ] = DEFAULT_INDEX_DB_SEARCH_TYPE
	table_name  : Annotated[str                       , FieldRole.INPUT   ] = DEFAULT_INDEX_DB_TABLE_NAME
	fallback    : Annotated[bool                      , FieldRole.INPUT   ] = DEFAULT_INDEX_DB_FALLBACK

	@property
	def get(self) -> Annotated[IndexDBConfig, FieldRole.OUTPUT]:
		return self


DEFAULT_MEMORY_MANAGER_QUERY   : bool = False
DEFAULT_MEMORY_MANAGER_UPDATE  : bool = False
DEFAULT_MEMORY_MANAGER_MANAGED : bool = False
DEFAULT_MEMORY_MANAGER_PROMPT  : str  = None


@node_info(
	title       = "Memory Manager",
	description = "Manages memory information",
	icon        = "💭",
	section     = "Configurations",
	visible     = True
)
class MemoryManagerConfig(ConfigType):
	"""Agent long-term memory across conversations. Set query=true to retrieve, update=true to store. Wire get→agent_config.memory_mgr."""
	type    : Annotated[Literal["memory_manager_config"], FieldRole.CONSTANT] = "memory_manager_config"
	query   : Annotated[bool                            , FieldRole.INPUT   ] = DEFAULT_MEMORY_MANAGER_QUERY
	update  : Annotated[bool                            , FieldRole.INPUT   ] = DEFAULT_MEMORY_MANAGER_UPDATE
	managed : Annotated[bool                            , FieldRole.INPUT   ] = DEFAULT_MEMORY_MANAGER_MANAGED
	# model   : Annotated[Optional[ModelConfig]           , FieldRole.INPUT   ] = Field(default=None, title="Model Source", description="Source of language model (e.g., 'ollama', 'openai')")
	model   : Annotated[Optional[ModelConfig]           , FieldRole.INPUT   ] = None
	prompt  : Annotated[Optional[str]                   , FieldRole.INPUT   ] = DEFAULT_MEMORY_MANAGER_PROMPT

	@property
	def get(self) -> Annotated[MemoryManagerConfig, FieldRole.OUTPUT]:
		return self


DEFAULT_SESSION_MANAGER_QUERY        : bool = False
DEFAULT_SESSION_MANAGER_UPDATE       : bool = False
DEFAULT_SESSION_MANAGER_HISTORY_SIZE : int  = 10
DEFAULT_SESSION_MANAGER_SUMMARIZE    : bool = False
DEFAULT_SESSION_MANAGER_PROMPT       : str  = None


@node_info(
	title       = "Session Manager",
	description = "Manages session information",
	icon        = "🗓️",
	section     = "Configurations",
	visible     = True
)
class SessionManagerConfig(ConfigType):
	"""Chat history manager for multi-turn conversations. Set history_size for context window. Wire get→agent_config.session_mgr."""
	type         : Annotated[Literal["session_manager_config"], FieldRole.CONSTANT] = "session_manager_config"
	query        : Annotated[bool                             , FieldRole.INPUT   ] = DEFAULT_SESSION_MANAGER_QUERY
	update       : Annotated[bool                             , FieldRole.INPUT   ] = DEFAULT_SESSION_MANAGER_UPDATE
	history_size : Annotated[int                              , FieldRole.INPUT   ] = DEFAULT_SESSION_MANAGER_HISTORY_SIZE
	model        : Annotated[Optional[ModelConfig]            , FieldRole.INPUT   ] = None
	prompt       : Annotated[Optional[str]                    , FieldRole.INPUT   ] = DEFAULT_SESSION_MANAGER_PROMPT

	@property
	def get(self) -> Annotated[SessionManagerConfig, FieldRole.OUTPUT]:
		return self


DEFAULT_KNOWLEDGE_MANAGER_QUERY       : bool = True
DEFAULT_KNOWLEDGE_MANAGER_MAX_RESULTS : int  = 10


@node_button(
	id          = "import",
	label       = "Import",
	icon        = "📥",
	position    = "bottom"
)
@node_button(
	id          = "list",
	label       = "List",
	icon        = "📋",
	position    = "bottom"
)
@node_button(
	id          = "remove",
	label       = "Remove",
	icon        = "🗑",
	position    = "bottom"
)
@node_dropzone(
	accept      = ".csv,.doc,.docx,.json,.md,.pdf,.pptx,.txt,.xls,.xlsx",
	area        = "content",
	label       = "Drop file here",
	reject      = "File type not accepted"
)
@node_info(
	title       = "Knowledge Manager",
	description = "Manages knowledge information (RAG)",
	icon        = "📚",
	section     = "Configurations",
	visible     = True
)
class KnowledgeManagerConfig(ConfigType):
	"""RAG knowledge store combining content_db and index_db. Requires both DBs wired. Set query=true to enable retrieval. Wire get→agent_config.knowledge_mgr."""
	type        : Annotated[Literal["knowledge_manager_config"], FieldRole.CONSTANT] = "knowledge_manager_config"
	query       : Annotated[bool                               , FieldRole.INPUT   ] = DEFAULT_KNOWLEDGE_MANAGER_QUERY
	description : Annotated[Optional[str]                      , FieldRole.INPUT   ] = None
	# content_db  : Annotated[Optional[ContentDBConfig]          , FieldRole.INPUT   ] = None
	content_db  : Annotated[ContentDBConfig                    , FieldRole.INPUT   ] = None
	index_db    : Annotated[IndexDBConfig                      , FieldRole.INPUT   ] = None
	max_results : Annotated[int                                , FieldRole.INPUT   ] = DEFAULT_KNOWLEDGE_MANAGER_MAX_RESULTS
	urls        : Annotated[Optional[List[str]]                , FieldRole.INPUT   ] = None

	@property
	def get(self) -> Annotated[KnowledgeManagerConfig, FieldRole.OUTPUT]:
		return self


DEFAULT_TOOL_MAX_WEB_SEARCH_RESULTS : int  = 5
DEFAULT_TOOL_FALLBACK               : bool = False


@node_info(
	title       = "Tool Provider",
	description = "Handles tool usage",
	icon        = "🔧",
	section     = "Configurations",
	visible     = True
)
class ToolConfig(ConfigType):
	"""External tool/function for agents. Set name to Python import path (e.g. 'tools.list_directory'). Wire get→agent_config.tools.<key> via MULTI_INPUT edge (target_slot='tools.<key>')."""
	type     : Annotated[Literal["tool_config"]  , FieldRole.CONSTANT] = "tool_config"
	name     : Annotated[str                     , FieldRole.INPUT   ] = ""
	args     : Annotated[Optional[Dict[str, Any]], FieldRole.INPUT   ] = None
	lang     : Annotated[Optional[str]           , FieldRole.INPUT   ] = None
	script   : Annotated[Optional[str]           , FieldRole.INPUT   ] = None
	fallback : Annotated[bool                    , FieldRole.INPUT   ] = DEFAULT_TOOL_FALLBACK

	@property
	def get(self) -> Annotated[ToolConfig, FieldRole.OUTPUT]:
		return self


DEFAULT_AGENT_OPTIONS_INSTRUCTIONS    : str  = None
DEFAULT_AGENT_OPTIONS_PROMPT_OVERRIDE : str  = None
DEFAULT_AGENT_OPTIONS_MARKDOWN        : bool = True


@node_info(
	title       = "Agent Options",
	description = "Stores agent configuration options",
	icon        = "🛠️",
	section     = "Configurations",
	visible     = True
)
class AgentOptionsConfig(OptionsType):
	"""Agent personality and prompt configuration. Set name, description, instructions (list of strings), or prompt_override (full system prompt). Wire get→agent_config.options."""
	type            : Annotated[Literal["agent_options_config"], FieldRole.CONSTANT] = "agent_options_config"
	instructions    : Annotated[Optional[List[str]]            , FieldRole.INPUT   ] = DEFAULT_AGENT_OPTIONS_INSTRUCTIONS
	prompt_override : Annotated[Optional[str]                  , FieldRole.INPUT   ] = DEFAULT_AGENT_OPTIONS_PROMPT_OVERRIDE
	markdown        : Annotated[bool                           , FieldRole.INPUT   ] = DEFAULT_AGENT_OPTIONS_MARKDOWN

	@property
	def get(self) -> Annotated[AgentOptionsConfig, FieldRole.OUTPUT]:
		return self


@node_info(
	title       = "Agent Reference",
	description = "Stores agent reference",
	icon        = "🤖",
	section     = "Configurations",
	visible     = True
)
class AgentConfig(ConfigType):
	"""Complete agent definition combining backend, model, options, and optional tools/memory/knowledge. Wire get→agent_flow.config or agent_chat.config."""
	type          : Annotated[Literal["agent_config"]                            , FieldRole.CONSTANT   ] = "agent_config"
	port          : Annotated[Optional[int]                                      , FieldRole.ANNOTATION ] = None
	options       : Annotated[Optional[AgentOptionsConfig]                       , FieldRole.INPUT      ] = None
	backend       : Annotated[BackendConfig                                      , FieldRole.INPUT      ] = None
	model         : Annotated[ModelConfig                                        , FieldRole.INPUT      ] = None
	content_db    : Annotated[Optional[ContentDBConfig]                          , FieldRole.INPUT      ] = None
	memory_mgr    : Annotated[Optional[MemoryManagerConfig]                      , FieldRole.INPUT      ] = None
	session_mgr   : Annotated[Optional[SessionManagerConfig]                     , FieldRole.INPUT      ] = None
	knowledge_mgr : Annotated[Optional[KnowledgeManagerConfig]                   , FieldRole.INPUT      ] = None
	tools         : Annotated[Optional[Dict[str, ToolConfig]]                   , FieldRole.MULTI_INPUT] = None

	@property
	def get(self) -> Annotated[AgentConfig, FieldRole.OUTPUT]:
		return self


@node_info(visible=False)
class FlowType(BaseType):
	type     : Annotated[Literal["flow_type"], FieldRole.CONSTANT] = "flow_type"
	flow_in  : Annotated[Optional[Any]       , FieldRole.INPUT   ] = None
	flow_out : Annotated[Optional[Any]       , FieldRole.OUTPUT  ] = None


@node_info(
	title       = "Start",
	description = "Represents the start of a workflow",
	icon        = "▶",
	section     = "Endpoints",
	visible     = True
)
class StartFlow(FlowType):
	"""Required workflow entry point. Always place at index 0. Outputs initial workflow variables as a dict on 'output'."""
	type   : Annotated[Literal["start_flow"], FieldRole.CONSTANT] = "start_flow"
	output : Annotated[Any                  , FieldRole.OUTPUT  ] = None


@node_info(
	title       = "End",
	description = "Represents the end of a workflow",
	icon        = "🏁",
	section     = "Endpoints",
	visible     = True
)
class EndFlow(FlowType):
	"""Successful workflow termination. Connect final data value to 'input'."""
	type  : Annotated[Literal["end_flow"], FieldRole.CONSTANT] = "end_flow"
	input : Annotated[Any                , FieldRole.INPUT   ] = None


@node_info(
	title       = "Sink",
	description = "Workflow dead end",
	icon        = "🚧",
	section     = "Endpoints",
	visible     = True
)
class SinkFlow(FlowType):
	"""Workflow dead end — discards its input. Use to terminate branches that produce no result."""
	type  : Annotated[Literal["sink_flow"], FieldRole.CONSTANT] = "sink_flow"
	input : Annotated[Any                 , FieldRole.INPUT   ] = None


@node_info(
	title       = "Preview",
	description = "Data preview",
	icon        = "➠",
	section     = "Workflow",
	visible     = True
)
class PreviewFlow(FlowType):
	"""Passthrough node with UI data preview. Set hint to control rendering (auto/text/json/image/audio/video). Data passes unchanged to 'output'."""
	type   : Annotated[Literal["preview_flow"]                                              , FieldRole.CONSTANT] = "preview_flow"
	input  : Annotated[Any                                                                  , FieldRole.INPUT   ] = None
	hint   : Annotated[Literal["auto", "text", "json", "image", "audio", "video", "model3d"], FieldRole.INPUT   ] = "auto"
	output : Annotated[Any                                                                  , FieldRole.OUTPUT  ] = None


@node_info(
	title       = "Route",
	description = "Routes data through pathways",
	icon        = "🔁",
	section     = "Workflow",
	visible     = True
)
class RouteFlow(FlowType):
	"""Conditional routing to named output branches. Declare outputs in JSON as "output":{"branch_a":null,"branch_b":null}. At runtime, target(str) selects the branch; unmatched input falls to 'default' output."""
	type    : Annotated[Literal["route_flow"]           , FieldRole.CONSTANT    ] = "route_flow"
	target  : Annotated[Union[int, str]                 , FieldRole.INPUT       ] = None
	input   : Annotated[Any                             , FieldRole.INPUT       ] = None
	output  : Annotated[Union[List[str], Dict[str, Any]], FieldRole.MULTI_OUTPUT] = None
	default : Annotated[Any                             , FieldRole.OUTPUT      ] = None


@node_info(
	title       = "Combine",
	description = "Combines data through pathways",
	icon        = "🔀",
	section     = "Workflow",
	visible     = True
)
class CombineFlow(FlowType):
	"""Map named inputs to named outputs via a mapping dict. Both input and output are MULTI slots. mapping={src_key: dst_key}."""
	type    : Annotated[Literal["combine_flow"]         , FieldRole.CONSTANT    ] = "combine_flow"
	mapping : Annotated[Dict[Union[int, str], str]      , FieldRole.INPUT       ] = None
	input   : Annotated[Union[List[str], Dict[str, Any]], FieldRole.MULTI_INPUT ] = None
	output  : Annotated[Union[List[str], Dict[str, Any]], FieldRole.MULTI_OUTPUT] = None


DEFAULT_MERGE_NODE_STRATEGY : str = "first"


@node_info(
	title       = "Merge",
	description = "Merges multiple data into one",
	icon        = "🪢",
	section     = "Workflow",
	visible     = True
)
class MergeFlow(FlowType):
	"""Collect multiple branches into one output. strategy: first (first non-None), last, concat (join strings/lists), all (return list). Connect branches via MULTI_INPUT dotted edges (target_slot='input.<branch>')."""
	type     : Annotated[Literal["merge_flow"]           , FieldRole.CONSTANT   ] = "merge_flow"
	strategy : Annotated[str                             , FieldRole.INPUT      ] = DEFAULT_MERGE_NODE_STRATEGY
	input    : Annotated[Union[List[str], Dict[str, Any]], FieldRole.MULTI_INPUT] = None
	output   : Annotated[Any                             , FieldRole.OUTPUT     ] = None


DEFAULT_TRANSFORM_NODE_LANG   : str = "python"
DEFAULT_TRANSFORM_NODE_SCRIPT : str = "output = input"


@node_info(
	title       = "Transform",
	description = "Transforms data according to script",
	icon        = "🏗️",
	section     = "Workflow",
	visible     = True
)
class TransformFlow(FlowType):
	"""Script-based data transform. Set lang='python' and write Python; assign result to `output` variable. Access input via `input`, workflow state via `variables`, extra context via `context`."""
	type    : Annotated[Literal["transform_flow"], FieldRole.CONSTANT] = "transform_flow"
	lang    : Annotated[str                      , FieldRole.INPUT   ] = DEFAULT_TRANSFORM_NODE_LANG
	script  : Annotated[str                      , FieldRole.INPUT   ] = Field(default=DEFAULT_TRANSFORM_NODE_SCRIPT, json_schema_extra={"editor": "code"})
	context : Annotated[Optional[Dict[str, Any]] , FieldRole.INPUT   ] = None
	input   : Annotated[Optional[Any]            , FieldRole.INPUT   ] = None
	output  : Annotated[Any                      , FieldRole.OUTPUT  ] = None


DEFAULT_TOOL_NODE_ARGS : Dict[str, Any] = {}


@node_info(
	title       = "Tool Proxy",
	description = "Proxy for tool invocation",
	icon        = "👨🏻‍🔧",
	section     = "Workflow",
	visible     = True
)
class ToolFlow(FlowType):
	"""Execute a tool within the flow graph. Wire tool_config→config. Input data is passed to the tool; result appears on 'output'."""
	type   : Annotated[Literal["tool_flow"], FieldRole.CONSTANT] = "tool_flow"
	config : Annotated[ToolConfig          , FieldRole.INPUT   ] = None
	args   : Annotated[Dict[str, Any]      , FieldRole.INPUT   ] = DEFAULT_TOOL_NODE_ARGS
	input  : Annotated[Any                 , FieldRole.INPUT   ] = None
	output : Annotated[Any                 , FieldRole.OUTPUT  ] = None


@node_info(
	title       = "Agent Proxy",
	description = "Proxy for agent invocation",
	icon        = "🕵️‍♂️",
	section     = "Workflow",
	visible     = True
)
class AgentFlow(FlowType):
	"""Execute one agent turn within the flow graph. Wire agent_config→config. Text/dict input; LLM response dict on 'output'."""
	type   : Annotated[Literal["agent_flow"], FieldRole.CONSTANT] = "agent_flow"
	config : Annotated[AgentConfig          , FieldRole.INPUT   ] = None
	input  : Annotated[Any                  , FieldRole.INPUT   ] = None
	output : Annotated[Any                  , FieldRole.OUTPUT  ] = None


# =============================================================================
# LOOP FLOW NODES
# Enables nested loops within workflows
# =============================================================================

DEFAULT_LOOP_MAX_ITERATIONS : int = 10000


@node_info(
	title       = "Loop Start",
	description = "Marks the beginning of a loop. Connect to a Loop End node to define the loop body. "
	              "The loop continues while 'condition' is True (up to max_iterations).",
	icon        = "🔁",
	section     = "Loops",
	visible     = True
)
class LoopStartFlow(FlowType):
	"""
	Loop Start node - begins a loop construct.

	The loop body consists of all nodes between this LoopStart and its paired LoopEnd.
	Each iteration:
	1. Evaluates 'condition' - if False, skips to after LoopEnd
	2. Increments 'iteration' counter
	3. Executes all nodes in the loop body
	4. When LoopEnd is reached, returns here for next iteration
	"""
	type          : Annotated[Literal["loop_start_flow"], FieldRole.CONSTANT] = "loop_start_flow"
	condition     : Annotated[bool                      , FieldRole.INPUT   ] = True
	max_iter      : Annotated[int                       , FieldRole.INPUT   ] = DEFAULT_LOOP_MAX_ITERATIONS
	iteration     : Annotated[int                       , FieldRole.OUTPUT  ] = 0


@node_info(
	title       = "Loop End",
	description = "Marks the end of a loop. Must be connected downstream from a Loop Start node. "
	              "When reached, execution returns to the paired Loop Start for the next iteration.",
	icon        = "↩️",
	section     = "Loops",
	visible     = True
)
class LoopEndFlow(FlowType):
	"""
	Loop End node - ends a loop construct and triggers the next iteration.

	When this node executes:
	1. Finds its paired LoopStart (the nearest upstream LoopStart)
	2. Signals the engine to re-evaluate the LoopStart condition
	3. If condition is still True, resets all loop body nodes and re-executes
	4. If condition is False, execution continues past this LoopEnd
	"""
	type   : Annotated[Literal["loop_end_flow"], FieldRole.CONSTANT] = "loop_end_flow"
	input  : Annotated[Any                     , FieldRole.INPUT   ] = None
	output : Annotated[Any                     , FieldRole.OUTPUT  ] = None


@node_info(
	title       = "For Each Start",
	description = "Iterates over a list of items. For each item, executes the loop body once. "
	              "Outputs 'current' (the current item) and 'index' (0-based position).",
	icon        = "📋",
	section     = "Loops",
	visible     = True
)
class ForEachStartFlow(FlowType):
	"""
	For Each Start node - iterates over a collection.

	This is a convenience node that combines LoopStart logic with list iteration.
	For each item in 'items':
	1. Sets 'current' to the current item
	2. Sets 'index' to the current position (0-based)
	3. Executes all downstream nodes until ForEachEnd
	4. Moves to the next item
	"""
	type    : Annotated[Literal["for_each_start_flow"], FieldRole.CONSTANT] = "for_each_start_flow"
	items   : Annotated[List[Any]                     , FieldRole.INPUT   ] = None
	current : Annotated[Any                           , FieldRole.OUTPUT  ] = None
	index   : Annotated[int                           , FieldRole.OUTPUT  ] = 0


@node_info(
	title       = "For Each End",
	description = "Marks the end of a For Each loop body. When reached, moves to the next item.",
	icon        = "↩️",
	section     = "Loops",
	visible     = True
)
class ForEachEndFlow(FlowType):
	"""
	For Each End node - ends a For Each loop iteration.
	"""
	type   : Annotated[Literal["for_each_end_flow"], FieldRole.CONSTANT] = "for_each_end_flow"
	input  : Annotated[Any                         , FieldRole.INPUT   ] = None
	output : Annotated[Any                         , FieldRole.OUTPUT  ] = None


@node_info(
	title       = "Break",
	description = "Immediately exits the innermost loop. Execution continues after the loop end.",
	icon        = "⏹️",
	section     = "Loops",
	visible     = True
)
class BreakFlow(FlowType):
	"""
	Break node - exits the current loop immediately.

	When executed, signals the engine to:
	1. Stop the current loop iteration
	2. Mark the loop as complete
	3. Continue execution after the LoopEnd/ForEachEnd
	"""
	type  : Annotated[Literal["break_flow"], FieldRole.CONSTANT] = "break_flow"
	input : Annotated[Any                  , FieldRole.INPUT   ] = None


@node_info(
	title       = "Continue",
	description = "Skips the rest of the current iteration and moves to the next loop iteration.",
	icon        = "⏭️",
	section     = "Loops",
	visible     = True
)
class ContinueFlow(FlowType):
	"""
	Continue node - skips to the next loop iteration.

	When executed, signals the engine to:
	1. Stop the current iteration immediately
	2. Skip any remaining nodes in the loop body
	3. Return to the LoopStart/ForEach for the next iteration
	"""
	type  : Annotated[Literal["continue_flow"], FieldRole.CONSTANT] = "continue_flow"
	input : Annotated[Any                     , FieldRole.INPUT   ] = None


# =============================================================================
# END LOOP FLOW NODES
# =============================================================================


# =============================================================================
# EVENT/TRIGGER FLOW NODES
# Nodes for event-driven workflow execution (timers, gates, accumulators)
# =============================================================================

DEFAULT_GATE_THRESHOLD : int  = 1
DEFAULT_GATE_RESET     : bool = True


@node_info(
	title       = "Gate",
	description = "Accumulates inputs and triggers when threshold is reached. "
	              "Use for batching, throttling, or conditional triggering.",
	icon        = "🚧",
	section     = "Workflow",
	visible     = True
)
class GateFlow(FlowType):
	"""
	Gate/Accumulator node - collects inputs and triggers on condition.

	The gate accumulates incoming data and triggers when:
	1. 'threshold' number of inputs received, OR
	2. 'condition' expression evaluates to True

	Useful for:
	- Batching: process every N items together
	- Throttling: limit rate of downstream execution
	- Conditional: trigger only when custom condition met
	"""
	type          : Annotated[Literal["gate_flow"], FieldRole.CONSTANT] = "gate_flow"
	input         : Annotated[Any                 , FieldRole.INPUT   ] = None
	threshold     : Annotated[int                 , FieldRole.INPUT   ] = DEFAULT_GATE_THRESHOLD
	condition     : Annotated[Optional[str]       , FieldRole.INPUT   ] = None  # Python expression
	reset_on_fire : Annotated[bool                , FieldRole.INPUT   ] = DEFAULT_GATE_RESET
	count         : Annotated[int                 , FieldRole.OUTPUT  ] = 0
	accumulated   : Annotated[List[Any]           , FieldRole.OUTPUT  ] = None
	triggered     : Annotated[bool                , FieldRole.OUTPUT  ] = False
	output        : Annotated[Any                 , FieldRole.OUTPUT  ] = None


@node_info(
	title       = "Delay",
	description = "Pauses execution for specified duration, then continues.",
	icon        = "⏸️",
	section     = "Workflow",
	visible     = True
)
class DelayFlow(FlowType):
	"""
	Delay node - simple pause in execution.

	Unlike Timer, Delay executes only once and passes through data.
	"""
	type          : Annotated[Literal["delay_flow"], FieldRole.CONSTANT] = "delay_flow"
	input         : Annotated[Any                  , FieldRole.INPUT   ] = None
	duration_ms   : Annotated[int                  , FieldRole.INPUT   ] = 1000
	output        : Annotated[Any                  , FieldRole.OUTPUT  ] = None


# =============================================================================
# EXTERNAL EVENT LISTENER NODE
# =============================================================================

@node_info(
	title       = "Event Listener",
	description = "Listens for external events from registered event sources (timers, file watchers, "
	              "webhooks, browser sources). Can listen to multiple sources with different modes.",
	icon        = "📡",
	section     = "Event Sources",
	visible     = True
)
class EventListenerFlow(FlowType):
	"""
	Event Listener node - waits for events from external event sources.

	Modes:
	- 'any': Triggers on first event from any source (default)
	- 'all': Waits for one event from each source before triggering
	- 'race': First event wins, resets listener for next round

	The node blocks workflow execution until an event is received.
	"""
	type        : Annotated[Literal["event_listener_flow"], FieldRole.CONSTANT   ] = "event_listener_flow"
	sources     : Annotated[Optional[Dict[str, Any]]      , FieldRole.MULTI_INPUT] = None   # Source IDs (multi-input from source nodes)
	mode        : Annotated[Literal["any", "all", "race"] , FieldRole.INPUT      ] = "any"
	timeout_ms  : Annotated[Optional[int]                 , FieldRole.INPUT      ] = None   # None = no timeout
	# Outputs
	event       : Annotated[Any                           , FieldRole.OUTPUT     ] = None   # The event data
	source_id   : Annotated[Optional[str]                 , FieldRole.OUTPUT     ] = None   # Which source triggered
	events      : Annotated[Optional[Dict[str, Any]]      , FieldRole.OUTPUT     ] = None   # All events (for 'all' mode)
	timed_out   : Annotated[bool                          , FieldRole.OUTPUT     ] = False  # True if timeout occurred


# =============================================================================
# EVENT SOURCE FLOW NODES
# =============================================================================

DEFAULT_TIMER_INTERVAL_MS   : int  = 1000
DEFAULT_TIMER_MAX_TRIGGERS  : int  = -1      # -1 = infinite


@node_info(
	title       = "Timer Source",
	description = "Registers a timer event source. Connect its output to an Event Listener's sources input.",
	icon        = "🕐",
	section     = "Event Sources",
	visible     = True
)
class TimerSourceFlow(FlowType):
	"""Timer Source node - creates/registers a timer event source."""
	type           : Annotated[Literal["timer_source_flow"], FieldRole.CONSTANT] = "timer_source_flow"
	source_id      : Annotated[Optional[str]               , FieldRole.INPUT   ] = None
	interval_ms    : Annotated[int                         , FieldRole.INPUT   ] = DEFAULT_TIMER_INTERVAL_MS
	max_triggers   : Annotated[int                         , FieldRole.INPUT   ] = DEFAULT_TIMER_MAX_TRIGGERS
	immediate      : Annotated[bool                        , FieldRole.INPUT   ] = False
	registered_id  : Annotated[Optional[str]                , FieldRole.OUTPUT  ] = None


@node_info(
	title       = "FS Watch Source",
	description = "Registers a filesystem watcher event source. Connect its output to an Event Listener's sources input.",
	icon        = "📂",
	section     = "Event Sources",
	visible     = True
)
class FSWatchSourceFlow(FlowType):
	"""FS Watch Source node - watches filesystem paths for changes."""
	type           : Annotated[Literal["fswatch_source_flow"], FieldRole.CONSTANT] = "fswatch_source_flow"
	source_id      : Annotated[Optional[str]                 , FieldRole.INPUT   ] = None
	path           : Annotated[str                           , FieldRole.INPUT   ] = "."
	recursive      : Annotated[bool                          , FieldRole.INPUT   ] = True
	patterns       : Annotated[Optional[str]                 , FieldRole.INPUT   ] = "*"
	events         : Annotated[Optional[str]                 , FieldRole.INPUT   ] = "created,modified,deleted,moved"
	debounce_ms    : Annotated[int                           , FieldRole.INPUT   ] = 100
	registered_id  : Annotated[Optional[str]                  , FieldRole.OUTPUT  ] = None


@node_info(
	title       = "Webhook Source",
	description = "Registers a webhook event source. Connect its output to an Event Listener's sources input.",
	icon        = "🔗",
	section     = "Event Sources",
	visible     = True
)
class WebhookSourceFlow(FlowType):
	"""Webhook Source node - receives HTTP webhook events."""
	type           : Annotated[Literal["webhook_source_flow"], FieldRole.CONSTANT] = "webhook_source_flow"
	source_id      : Annotated[Optional[str]                 , FieldRole.INPUT   ] = None
	endpoint       : Annotated[str                           , FieldRole.INPUT   ] = "/hook/default"
	methods        : Annotated[Optional[str]                 , FieldRole.INPUT   ] = "POST"
	secret         : Annotated[Optional[str]                 , FieldRole.INPUT   ] = None
	registered_id  : Annotated[Optional[str]                  , FieldRole.OUTPUT  ] = None


@node_info(
	title       = "Browser Source",
	description = "Registers a browser media event source (webcam, microphone, screen). "
	              "Connect its output to an Event Listener's sources input.",
	icon        = "🎥",
	section     = "Event Sources",
	visible     = True
)
class BrowserSourceFlow(FlowType):
	"""Browser Source node - captures browser media events."""
	type           : Annotated[Literal["browser_source_flow"]             , FieldRole.CONSTANT] = "browser_source_flow"
	source_id      : Annotated[Optional[str]                              , FieldRole.INPUT   ] = None
	device_type    : Annotated[Literal["webcam", "microphone", "screen"]  , FieldRole.INPUT   ] = "webcam"
	mode           : Annotated[Literal["stream", "event"]                 , FieldRole.INPUT   ] = "event"
	interval_ms    : Annotated[int                                        , FieldRole.INPUT   ] = 1000
	resolution     : Annotated[Optional[str]                              , FieldRole.INPUT   ] = None
	audio_format   : Annotated[Optional[str]                              , FieldRole.INPUT   ] = None
	registered_id  : Annotated[Optional[str]                               , FieldRole.OUTPUT  ] = None


# =============================================================================
# END EVENT/TRIGGER FLOW NODES
# =============================================================================


@node_info(visible=False)
class InteractiveType(BaseType):
	type : Annotated[Literal["interactive_type"], FieldRole.CONSTANT] = "interactive_type"


DEFAULT_USER_INPUT_QUERY : str = "Please provide input for the workflow to continue."


@node_info(
	title       = "User Input",
	description = "Asks user for input during workflow execution",
	icon        = "👤",
	section     = "Interactive",
	visible     = True
)
class UserInputFlow(FlowType):
	"""Pause workflow and request user input. Set query for the prompt shown to the user. User's response appears on 'message' output."""
	type    : Annotated[Literal["user_input_flow"], FieldRole.CONSTANT] = "user_input_flow"
	query   : Annotated[Optional[Any]             , FieldRole.INPUT   ] = DEFAULT_USER_INPUT_QUERY
	message : Annotated[Optional[Any]             , FieldRole.OUTPUT  ] = None


@node_button(
	id          = "execute",
	label       = "Execute",
	icon        = "▶",
	position    = "bottom"
)
@node_info(
	title       = "Interactive Tool",
	description = "Calls tool interactively",
	icon        = "☎️",
	section     = "Interactive",
	visible     = True
)
class ToolCall(InteractiveType):
	"""Interactive tool execution UI panel. Wire tool_config→config; optional args override. Result shown on 'result' output."""
	type   : Annotated[Literal["tool_call"]    , FieldRole.CONSTANT] = "tool_call"
	config : Annotated[ToolConfig              , FieldRole.INPUT   ] = None
	args   : Annotated[Optional[Dict[str, Any]], FieldRole.INPUT   ] = None
	result : Annotated[Any                     , FieldRole.OUTPUT  ] = None


@node_chat(
	title               = "Agent Chat",
	placeholder         = "Ask the agent...",
	config_field        = "config",
	system_prompt_field = "system_prompt",
	min_width           = 350,
	min_height          = 450,
	show_timestamps     = True,
	stream_response     = True
)
@node_info(
	title       = "Interactive Agent Chat",
	description = "Allows to chat with agent interactively",
	icon        = "🗪",
	section     = "Interactive",
	visible     = True
)
class AgentChat(InteractiveType):
	"""Interactive chat UI for conversing with an agent. Wire agent_config→config. Supports streaming responses. Use system_prompt to override agent prompt for this chat."""
	type          : Annotated[Literal["agent_chat"], FieldRole.CONSTANT] = "agent_chat"
	config        : Annotated[AgentConfig          , FieldRole.INPUT   ] = None
	system_prompt : Annotated[Optional[str]        , FieldRole.INPUT   ] = None
	# response      : Annotated[Any                  , FieldRole.OUTPUT  ] = None
	# chat          : Annotated[Any                  , FieldRole.OUTPUT  ] = None


# =============================================================================
# TUTORIAL EXTENSION
# Counter node example - demonstrates @node_info and @node_button decorators
# See docs/tutorial-extension.md for full documentation
# =============================================================================

@node_button(
	id       = "reset",
	label    = "Reset",
	icon     = "0",
	position = "bottom"
)
@node_button(
	id       = "decrement",
	label    = "Decrement",
	icon     = "➖",
	position = "bottom"
)
@node_button(
	id       = "increment",
	label    = "Increment",
	icon     = "➕",
	position = "bottom"
)
@node_info(
	title       = "Counter",
	description = "A simple counter that can be incremented, decremented, or reset. "
	              "Connect 'step' to control the increment/decrement amount.",
	icon        = "#️⃣",
	section     = "Tutorial",
	visible     = True
)
class Counter(InteractiveType):
	"""Tutorial: A Counter node demonstrating basic interactivity."""
	type  : Annotated[Literal["counter"], FieldRole.CONSTANT] = "counter"
	step  : Annotated[int               , FieldRole.INPUT   ] = 1
	value : Annotated[int               , FieldRole.OUTPUT  ] = 0

# =============================================================================
# END TUTORIAL
# =============================================================================


WorkflowNodeUnion = Union[
	# Native nodes
	NativeBoolean,
	NativeInteger,
	NativeReal,
	NativeString,
	NativeList,
	NativeDictionary,

	# Tensor nodes
	DataTensor,

	# Config nodes
	BackendConfig,
	ModelConfig,
	EmbeddingConfig,
	ContentDBConfig,
	IndexDBConfig,
	MemoryManagerConfig,
	SessionManagerConfig,
	KnowledgeManagerConfig,
	ToolConfig,
	AgentOptionsConfig,
	AgentConfig,

	# Flow nodes
	StartFlow,
	EndFlow,
	SinkFlow,
	PreviewFlow,
	TransformFlow,
	RouteFlow,
	CombineFlow,
	MergeFlow,
	UserInputFlow,
	ToolFlow,
	AgentFlow,

	# Loop nodes
	LoopStartFlow,
	LoopEndFlow,
	ForEachStartFlow,
	ForEachEndFlow,
	BreakFlow,
	ContinueFlow,

	# Event/Trigger nodes
	GateFlow,
	DelayFlow,
	EventListenerFlow,

	# Event Source nodes
	TimerSourceFlow,
	FSWatchSourceFlow,
	WebhookSourceFlow,
	BrowserSourceFlow,

	# Interactive nodes
	ToolCall,
	AgentChat,

	# Tutorial nodes
	Counter
]


DEFAULT_WORKFLOW_NODE_DELAY         : float = 0.0
DEFAULT_WORKFLOW_EXEC_DELAY         : float = 0.1
DEFAULT_WORKFLOW_USER_INPUT_TIMEOUT : float = 300.0


@node_info(visible=False)
class WorkflowExecutionOptions(OptionsType):
	type               : Annotated[Literal["workflow_execution_options"], FieldRole.CONSTANT] = "workflow_execution_options"
	exec_delay         : Annotated[Optional[float]                      , FieldRole.INPUT   ] = DEFAULT_WORKFLOW_EXEC_DELAY
	node_delay         : Annotated[Optional[float]                      , FieldRole.INPUT   ] = DEFAULT_WORKFLOW_NODE_DELAY
	user_input_timeout : Annotated[Optional[float]                      , FieldRole.INPUT   ] = DEFAULT_WORKFLOW_USER_INPUT_TIMEOUT

	@property
	def get(self) -> Annotated[WorkflowExecutionOptions, FieldRole.OUTPUT]:
		return self


DEFAULT_WORKFLOW_OPTIONS_SEED : int = 777


@node_info(visible=False)
class WorkflowOptions(OptionsType):
	type : Annotated[Literal["workflow_options"], FieldRole.CONSTANT] = "workflow_options"
	seed : Annotated[int                        , FieldRole.INPUT   ] = DEFAULT_WORKFLOW_OPTIONS_SEED

	@property
	def get(self) -> Annotated[WorkflowOptions, FieldRole.OUTPUT]:
		return self


@node_info(visible=False)
class Workflow(ComponentType):
	type    : Annotated[Literal["workflow"]      , FieldRole.CONSTANT] = "workflow"
	options : Annotated[Optional[WorkflowOptions], FieldRole.INPUT   ] = None
	nodes   : Annotated[Optional[List[Annotated[WorkflowNodeUnion, Field(discriminator="type")]]], FieldRole.INPUT] = None
	edges   : Annotated[Optional[List[Edge]]     , FieldRole.INPUT   ] = None

	def model_dump(self, **kwargs):
		# link() mutates node fields (List→Dict for MULTI_INPUT/OUTPUT), which triggers
		# Pydantic serialization warnings on the discriminated union. Suppress them.
		kwargs.setdefault('warnings', False)
		return super().model_dump(**kwargs)

	@property
	def get(self) -> Annotated[Workflow, FieldRole.OUTPUT]:
		return self

	def link(self):
		roles = (FieldRole.MULTI_INPUT, FieldRole.MULTI_OUTPUT)
		for node in self.nodes or []:
			for name, info in node.model_fields.items():
				for meta in info.metadata:
					if meta in roles:
						value = getattr(node, name)
						if isinstance(value, list):
							remap = {key: None for key in value}
							setattr(node, name, remap)

		for edge in self.edges or []:
			source_node = self.nodes[edge.source]
			target_node = self.nodes[edge.target]

			src_base, *src_parts = edge.source_slot.split(".")
			src_value = getattr(source_node, src_base)
			if src_parts:
				if src_value is None:
					src_value = {}
					setattr(source_node, src_base, src_value)
				# Ensure the sub-key exists in the dict (needed for routing)
				if src_parts[0] not in src_value:
					src_value[src_parts[0]] = None
				src_value = src_value.get(src_parts[0])

			dst_base, *dst_parts = edge.target_slot.split(".")
			if dst_parts:
				dst_field = getattr(target_node, dst_base)
				if dst_field is None:
					dst_field = {}
					setattr(target_node, dst_base, dst_field)
				dst_field[dst_parts[0]] = src_value
			else:
				setattr(target_node, dst_base, src_value)


if __name__ == "__main__":
	import json
	import os
	current_dir = os.path.dirname(os.path.abspath(__file__))
	print("-- start --")
	with open(f"{current_dir}/../web_wf/workflow_example_simple.json") as f:
		data = json.load(f)
		workflow = Workflow(**data)
		print(workflow)
	print("-- end --")
