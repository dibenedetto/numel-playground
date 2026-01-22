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
	type     : Annotated[Literal["model_config"], FieldRole.CONSTANT] = "model_config"
	source   : Annotated[str                    , FieldRole.INPUT   ] = DEFAULT_MODEL_SOURCE
	name     : Annotated[str                    , FieldRole.INPUT   ] = DEFAULT_MODEL_NAME
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
	type     : Annotated[Literal["embedding_config"], FieldRole.CONSTANT] = "embedding_config"
	source   : Annotated[str                        , FieldRole.INPUT   ] = DEFAULT_EMBEDDING_SOURCE
	name     : Annotated[str                        , FieldRole.INPUT   ] = DEFAULT_EMBEDDING_NAME
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
	type    : Annotated[Literal["memory_manager_config"], FieldRole.CONSTANT] = "memory_manager_config"
	query   : Annotated[bool                            , FieldRole.INPUT   ] = DEFAULT_MEMORY_MANAGER_QUERY
	update  : Annotated[bool                            , FieldRole.INPUT   ] = DEFAULT_MEMORY_MANAGER_UPDATE
	managed : Annotated[bool                            , FieldRole.INPUT   ] = DEFAULT_MEMORY_MANAGER_MANAGED
	zune    : Annotated[str, FieldRole.INPUT] = Field(default="oubi")
	model   : Annotated[Optional[ModelConfig]           , FieldRole.INPUT   ] = Field(default=None, title="Embedding Source", description="Source of embedding model (e.g., 'ollama', 'openai')")
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
	type          : Annotated[Literal["agent_config"]                            , FieldRole.CONSTANT   ] = "agent_config"
	port          : Annotated[Optional[int]                                      , FieldRole.ANNOTATION ] = None
	options       : Annotated[Optional[AgentOptionsConfig]                       , FieldRole.INPUT      ] = None
	backend       : Annotated[BackendConfig                                      , FieldRole.INPUT      ] = None
	model         : Annotated[ModelConfig                                        , FieldRole.INPUT      ] = None
	content_db    : Annotated[Optional[ContentDBConfig]                          , FieldRole.INPUT      ] = None
	memory_mgr    : Annotated[Optional[MemoryManagerConfig]                      , FieldRole.INPUT      ] = None
	session_mgr   : Annotated[Optional[SessionManagerConfig]                     , FieldRole.INPUT      ] = None
	knowledge_mgr : Annotated[Optional[KnowledgeManagerConfig]                   , FieldRole.INPUT      ] = None
	tools         : Annotated[Optional[Union[List[str], Dict[str, ToolConfig]]]  , FieldRole.MULTI_INPUT] = None

	@property
	def get(self) -> Annotated[AgentConfig, FieldRole.OUTPUT]:
		return self


@node_info(visible=False)
class FlowType(BaseType):
	type : Annotated[Literal["flow_type"], FieldRole.CONSTANT] = "flow_type"


@node_info(
	title       = "Start",
	description = "Represents the start of a workflow",
	icon        = "▶",
	section     = "Workflow",
	visible     = True
)
class StartFlow(FlowType):
	type : Annotated[Literal["start_flow"], FieldRole.CONSTANT] = "start_flow"
	pin  : Annotated[Any                  , FieldRole.OUTPUT  ] = None


@node_info(
	title       = "End",
	description = "Represents the end of a workflow",
	icon        = "🏁",
	section     = "Workflow",
	visible     = True
)
class EndFlow(FlowType):
	type : Annotated[Literal["end_flow"], FieldRole.CONSTANT] = "end_flow"
	pin  : Annotated[Any                , FieldRole.INPUT   ] = None


@node_info(
	title       = "Sink",
	description = "Workflow dead end",
	icon        = "🚧",
	section     = "Workflow",
	visible     = True
)
class SinkFlow(FlowType):
	type : Annotated[Literal["sink_flow"], FieldRole.CONSTANT] = "sink_flow"
	pin  : Annotated[Any                 , FieldRole.INPUT   ] = None


# @node_info(
# 	title       = "Passthrough",
# 	description = "Identity value pass through",
# 	icon        = "➠",
# 	section     = "Workflow",
# 	visible     = True
# )
# class PassthroughFlow(FlowType):
# 	type   : Annotated[Literal["passthrough_flow"], FieldRole.CONSTANT] = "passthrough_flow"
# 	input  : Annotated[Any                        , FieldRole.INPUT   ] = None
# 	output : Annotated[Any                        , FieldRole.OUTPUT  ] = None


@node_info(
	title       = "Preview",
	description = "Data preview",
	icon        = "➠",
	section     = "Workflow",
	visible     = True
)
class PreviewFlow(FlowType):
	type   : Annotated[Literal["preview_flow"], FieldRole.CONSTANT] = "preview_flow"
	input  : Annotated[Any                    , FieldRole.INPUT   ] = None
	output : Annotated[Any                    , FieldRole.OUTPUT  ] = None


@node_info(
	title       = "Route",
	description = "Routes data through pathways",
	icon        = "🔁",
	section     = "Workflow",
	visible     = True
)
class RouteFlow(FlowType):
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
	type     : Annotated[Literal["merge_flow"]           , FieldRole.CONSTANT   ] = "merge_flow"
	strategy : Annotated[str                             , FieldRole.INPUT      ] = DEFAULT_MERGE_NODE_STRATEGY
	input    : Annotated[Union[List[str], Dict[str, Any]], FieldRole.MULTI_INPUT] = None
	output   : Annotated[Any                             , FieldRole.OUTPUT     ] = None


DEFAULT_TRANSFORM_NODE_LANG    : str            = "python"
DEFAULT_TRANSFORM_NODE_SCRIPT  : str            = "output = input"
DEFAULT_TRANSFORM_NODE_CONTEXT : Dict[str, Any] = {}


@node_info(
	title       = "Transform",
	description = "Transforms data according to script",
	icon        = "🏗️",
	section     = "Workflow",
	visible     = True
)
class TransformFlow(FlowType):
	type    : Annotated[Literal["transform_flow"], FieldRole.CONSTANT] = "transform_flow"
	lang    : Annotated[str                      , FieldRole.INPUT   ] = DEFAULT_TRANSFORM_NODE_LANG
	script  : Annotated[str                      , FieldRole.INPUT   ] = DEFAULT_TRANSFORM_NODE_SCRIPT
	context : Annotated[Dict[str, Any]           , FieldRole.INPUT   ] = DEFAULT_TRANSFORM_NODE_CONTEXT
	input   : Annotated[Any                      , FieldRole.INPUT   ] = None
	output  : Annotated[Any                      , FieldRole.OUTPUT  ] = None


@node_info(
	title       = "User Input",
	description = "Asks user for input during workflow execution",
	icon        = "👤",
	section     = "Workflow",
	visible     = True
)
class UserInputFlow(FlowType):
	type    : Annotated[Literal["user_input_flow"], FieldRole.CONSTANT] = "user_input_flow"
	query   : Annotated[Any                       , FieldRole.INPUT   ] = None
	content : Annotated[Any                       , FieldRole.OUTPUT  ] = None


DEFAULT_TOOL_NODE_ARGS : Dict[str, Any] = {}


@node_info(
	title       = "Tool Proxy",
	description = "Proxy for tool invocation",
	icon        = "👨🏻‍🔧",
	section     = "Workflow",
	visible     = True
)
class ToolFlow(FlowType):
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
	type   : Annotated[Literal["agent_flow"], FieldRole.CONSTANT] = "agent_flow"
	config : Annotated[AgentConfig          , FieldRole.INPUT   ] = None
	input  : Annotated[Any                  , FieldRole.INPUT   ] = None
	output : Annotated[Any                  , FieldRole.OUTPUT  ] = None


@node_info(visible=False)
class InteractiveType(BaseType):
	type : Annotated[Literal["interactive_type"], FieldRole.CONSTANT] = "interactive_type"


@node_info(
	title       = "Interactive Tool",
	description = "Calls tool interactively",
	icon        = "☎️",
	section     = "Workflow",
	visible     = True
)
class ToolCall(InteractiveType):
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
	section     = "Workflow",
	visible     = True
)
class AgentChat(InteractiveType):
	type          : Annotated[Literal["agent_chat"], FieldRole.CONSTANT] = "agent_chat"
	config        : Annotated[AgentConfig          , FieldRole.INPUT   ] = None
	system_prompt : Annotated[Optional[str]        , FieldRole.INPUT   ] = None
	# response      : Annotated[Any                  , FieldRole.OUTPUT  ] = None
	# chat          : Annotated[Any                  , FieldRole.OUTPUT  ] = None


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
	# BinaryTensor,
	# TextTensor,
	# DocumentTensor,
	# ImageTensor,
	# AudioTensor,
	# VideoTensor,
	# Model3DTensor,

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
	# PassthroughFlow,
	PreviewFlow,
	TransformFlow,
	RouteFlow,
	CombineFlow,
	MergeFlow,
	UserInputFlow,
	ToolFlow,
	AgentFlow,

	# Interactive nodes
	ToolCall,
	AgentChat,
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
				src_value = src_value[src_parts[0]]

			dst_base, *dst_parts = edge.target_slot.split(".")
			if dst_parts:
				dst_field = getattr(target_node, dst_base)
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
