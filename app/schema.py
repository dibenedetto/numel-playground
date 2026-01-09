# schema.py

from __future__ import annotations


from enum       import Enum
from pydantic   import BaseModel, Field
from typing     import Annotated, Any, Dict, List, Literal, Optional, Union
from uuid       import uuid4

# ========================================================================
# FIELD ROLES
# ========================================================================

class FieldRole(str, Enum):
	ANNOTATION   = "annotation"
	CONSTANT     = "constant"
	INPUT        = "input"
	OUTPUT       = "output"
	MULTI_INPUT  = "multi_input"
	MULTI_OUTPUT = "multi_output"


# ========================================================================
# DECORATORS
# ========================================================================

def node_button(id: str, label: str = "", icon: str = "", position: str = "bottom", **kwargs):
	def decorator(cls):
		return cls
	return decorator


def node_dropzone(accept: str = "*", area: str = "content", label: str = "Drop file here", **kwargs):
	def decorator(cls):
		return cls
	return decorator


def node_chat(**kwargs):
	def decorator(cls): return cls
	return decorator


# ========================================================================
# BASE TYPE
# ========================================================================

def generate_id():
	return str(uuid4())


class BaseType(BaseModel):
	type  : Annotated[Literal["base_type"]    , FieldRole.CONSTANT  ] = "base_type"
	id    : Annotated[str                     , FieldRole.ANNOTATION] = Field(default_factory=generate_id)
	data  : Annotated[Optional[Any]           , FieldRole.INPUT     ] = None
	extra : Annotated[Optional[Dict[str, Any]], FieldRole.INPUT     ] = None


# ========================================================================
# EDGE
# ========================================================================

DEFAULT_EDGE_PREVIEW : bool = False


class Edge(BaseType):
	type        : Annotated[Literal["edge"], FieldRole.CONSTANT  ] = "edge"
	preview     : Annotated[bool           , FieldRole.ANNOTATION] = DEFAULT_EDGE_PREVIEW
	source      : Annotated[int            , FieldRole.INPUT     ] = None
	target      : Annotated[int            , FieldRole.INPUT     ] = None
	source_slot : Annotated[str            , FieldRole.INPUT     ] = None
	target_slot : Annotated[str            , FieldRole.INPUT     ] = None


# ========================================================================
# NATIVE VALUE NODES
# ========================================================================

class NativeNode(BaseType):
	type  : Annotated[Literal["native_node"], FieldRole.CONSTANT] = "native_node"
	value : Annotated[Any                   , FieldRole.INPUT   ] = None

	@property
	def output(self) -> Annotated[Any, FieldRole.OUTPUT]:
		return self.value


class StringNode(NativeNode):
	type  : Annotated[Literal["native_string"], FieldRole.CONSTANT] = "native_string"
	value : Annotated[str                     , FieldRole.INPUT   ] = ""

	@property
	def output(self) -> Annotated[str, FieldRole.OUTPUT]:
		return self.value


class IntegerNode(NativeNode):
	type  : Annotated[Literal["native_integer"], FieldRole.CONSTANT] = "native_integer"
	value : Annotated[int                      , FieldRole.INPUT   ] = 0

	@property
	def output(self) -> Annotated[int, FieldRole.OUTPUT]:
		return self.value


class FloatNode(NativeNode):
	type  : Annotated[Literal["native_float"], FieldRole.CONSTANT] = "native_float"
	value : Annotated[float                  , FieldRole.INPUT   ] = 0.0

	@property
	def output(self) -> Annotated[float, FieldRole.OUTPUT]:
		return self.value


class BooleanNode(NativeNode):
	type  : Annotated[Literal["native_boolean"], FieldRole.CONSTANT] = "native_boolean"
	value : Annotated[bool                     , FieldRole.INPUT   ] = False

	@property
	def output(self) -> Annotated[bool, FieldRole.OUTPUT]:
		return self.value


class ListNode(NativeNode):
	type  : Annotated[Literal["native_list"], FieldRole.CONSTANT] = "native_list"
	value : Annotated[List[Any]             , FieldRole.INPUT   ] = []

	@property
	def output(self) -> Annotated[List[Any], FieldRole.OUTPUT]:
		return self.value


class DictNode(NativeNode):
	type  : Annotated[Literal["native_dict"], FieldRole.CONSTANT] = "native_dict"
	value : Annotated[Dict[str, Any]        , FieldRole.INPUT   ] = {}

	@property
	def output(self) -> Annotated[Dict[str, Any], FieldRole.OUTPUT]:
		return self.value


# ========================================================================
# DATA SOURCE NODES
# ========================================================================

class SourceType(str, Enum):
	NONE   = "none"
	URL    = "url"
	FILE   = "file"
	INLINE = "inline"


class SourceMeta(BaseModel):
	filename      : Optional[str]   = None
	mime_type     : Optional[str]   = None
	size          : Optional[int]   = None
	last_modified : Optional[int]   = None
	width         : Optional[int]   = None
	height        : Optional[int]   = None
	duration      : Optional[float] = None
	encoding      : Optional[str]   = None
	language      : Optional[str]   = None


class DataNode(BaseType):
	type        : Annotated[Literal["base_data_node"], FieldRole.CONSTANT] = "data_node"
	source_type : Annotated[SourceType               , FieldRole.INPUT   ] = SourceType.NONE
	source_url  : Annotated[Optional[str]            , FieldRole.INPUT   ] = None
	source_path : Annotated[Optional[str]            , FieldRole.INPUT   ] = None
	source_data : Annotated[Optional[str]            , FieldRole.INPUT   ] = None
	source_meta : Annotated[Optional[SourceMeta]     , FieldRole.INPUT   ] = None
	data_type   : Annotated[Optional[str]            , FieldRole.INPUT   ] = None

	@property
	def output(self) -> Annotated[DataNode, FieldRole.OUTPUT]:
		return self


DEFAULT_TEXT_ENCODING : str = "utf-8"
DEFAULT_TEXT_LANGUAGE : str = "plain"


class TextDataNode(DataNode):
	type     : Annotated[Literal["data_text"], FieldRole.CONSTANT] = "data_text"
	encoding : Annotated[str                 , FieldRole.INPUT   ] = DEFAULT_TEXT_ENCODING
	language : Annotated[str                 , FieldRole.INPUT   ] = DEFAULT_TEXT_LANGUAGE

	@property
	def output(self) -> Annotated[TextDataNode, FieldRole.OUTPUT]:
		return self


class DocumentDataNode(DataNode):
	type : Annotated[Literal["data_document"], FieldRole.CONSTANT] = "data_document"

	@property
	def output(self) -> Annotated[DocumentDataNode, FieldRole.OUTPUT]:
		return self


class ImageDataNode(DataNode):
	type : Annotated[Literal["data_image"], FieldRole.CONSTANT] = "data_image"

	@property
	def output(self) -> Annotated[ImageDataNode, FieldRole.OUTPUT]:
		return self


class AudioDataNode(DataNode):
	type : Annotated[Literal["data_audio"], FieldRole.CONSTANT] = "data_audio"

	@property
	def output(self) -> Annotated[AudioDataNode, FieldRole.OUTPUT]:
		return self


class VideoDataNode(DataNode):
	type : Annotated[Literal["data_video"], FieldRole.CONSTANT] = "data_video"

	@property
	def output(self) -> Annotated[VideoDataNode, FieldRole.OUTPUT]:
		return self


class Model3DDataNode(DataNode):
	type : Annotated[Literal["data_model3d"], FieldRole.CONSTANT] = "data_model3d"

	@property
	def output(self) -> Annotated[Model3DDataNode, FieldRole.OUTPUT]:
		return self


class BinaryDataNode(DataNode):
	type : Annotated[Literal["data_binary"], FieldRole.CONSTANT] = "data_binary"

	@property
	def output(self) -> Annotated[BinaryDataNode, FieldRole.OUTPUT]:
		return self


# ========================================================================
# CONFIG NODES
# ========================================================================

class BaseConfig(BaseType):
	type : Annotated[Literal["base_config"], FieldRole.CONSTANT] = "base_config"

	@property
	def get(self) -> Annotated[BaseConfig, FieldRole.OUTPUT]:
		return self


class InfoConfig(BaseConfig):
	type         : Annotated[Literal["info_config"], FieldRole.CONSTANT] = "info_config"
	version      : Annotated[Optional[str]         , FieldRole.INPUT   ] = None
	name         : Annotated[Optional[str]         , FieldRole.INPUT   ] = None
	author       : Annotated[Optional[str]         , FieldRole.INPUT   ] = None
	description  : Annotated[Optional[str]         , FieldRole.INPUT   ] = None
	instructions : Annotated[Optional[List[str]]   , FieldRole.INPUT   ] = None

	@property
	def get(self) -> Annotated[InfoConfig, FieldRole.OUTPUT]:
		return self


DEFAULT_BACKEND_NAME     : str  = "agno"
DEFAULT_BACKEND_VERSION  : str  = ""
DEFAULT_BACKEND_FALLBACK : bool = False


class BackendConfig(BaseConfig):
	type     : Annotated[Literal["backend_config"], FieldRole.CONSTANT] = "backend_config"
	name     : Annotated[str                      , FieldRole.INPUT   ] = DEFAULT_BACKEND_NAME
	version  : Annotated[str                      , FieldRole.INPUT   ] = DEFAULT_BACKEND_VERSION
	fallback : Annotated[bool                     , FieldRole.INPUT   ] = DEFAULT_BACKEND_FALLBACK

	@property
	def get(self) -> Annotated[BackendConfig, FieldRole.OUTPUT]:
		return self


DEFAULT_MODEL_SOURCE   : str  = "ollama"
DEFAULT_MODEL_NAME     : str  = "mistral"
DEFAULT_MODEL_VERSION  : str  = ""
DEFAULT_MODEL_FALLBACK : bool = False


class ModelConfig(BaseConfig):
	type     : Annotated[Literal["model_config"], FieldRole.CONSTANT] = "model_config"
	source   : Annotated[str                    , FieldRole.INPUT   ] = DEFAULT_MODEL_SOURCE
	name     : Annotated[str                    , FieldRole.INPUT   ] = DEFAULT_MODEL_NAME
	version  : Annotated[str                    , FieldRole.INPUT   ] = DEFAULT_MODEL_VERSION
	fallback : Annotated[bool                   , FieldRole.INPUT   ] = DEFAULT_MODEL_FALLBACK

	@property
	def get(self) -> Annotated[ModelConfig, FieldRole.OUTPUT]:
		return self


DEFAULT_EMBEDDING_SOURCE   : str  = "ollama"
DEFAULT_EMBEDDING_NAME     : str  = "mistral"
DEFAULT_EMBEDDING_VERSION  : str  = ""
DEFAULT_EMBEDDING_FALLBACK : bool = False


class EmbeddingConfig(BaseConfig):
	type     : Annotated[Literal["embedding_config"], FieldRole.CONSTANT] = "embedding_config"
	source   : Annotated[str                        , FieldRole.INPUT   ] = DEFAULT_EMBEDDING_SOURCE
	name     : Annotated[str                        , FieldRole.INPUT   ] = DEFAULT_EMBEDDING_NAME
	version  : Annotated[str                        , FieldRole.INPUT   ] = DEFAULT_EMBEDDING_VERSION
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


# @node_button(id="import", label="Import", icon="📥", position="bottom")
# @node_dropzone(accept=".json,.txt", area="content", label="Drop file")
class ContentDBConfig(BaseConfig):
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


# @node_button(id="import", label="Import", icon="📥", position="bottom")
# @node_dropzone(accept=".json,.txt", area="content", label="Drop file")
class IndexDBConfig(BaseConfig):
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


class MemoryManagerConfig(BaseConfig):
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


class SessionManagerConfig(BaseConfig):
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


@node_button(id="import", label="Import", icon="📥", position="bottom")
@node_dropzone(accept=".csv,.doc,.docx,.json,.md,.pdf,.pptx,.txt,.xls,.xlsx", area="content", label="Drop file")
class KnowledgeManagerConfig(BaseConfig):
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


class ToolConfig(BaseConfig):
	type     : Annotated[Literal["tool_config"]  , FieldRole.CONSTANT] = "tool_config"
	name     : Annotated[str                     , FieldRole.INPUT   ] = ""
	args     : Annotated[Optional[Dict[str, Any]], FieldRole.INPUT   ] = None
	lang     : Annotated[Optional[str]           , FieldRole.INPUT   ] = None
	script   : Annotated[Optional[str]           , FieldRole.INPUT   ] = None
	fallback : Annotated[bool                    , FieldRole.INPUT   ] = DEFAULT_TOOL_FALLBACK

	@property
	def get(self) -> Annotated[ToolConfig, FieldRole.OUTPUT]:
		return self


DEFAULT_AGENT_OPTIONS_DESCRIPTION     : str  = None
DEFAULT_AGENT_OPTIONS_INSTRUCTIONS    : str  = None
DEFAULT_AGENT_OPTIONS_PROMPT_OVERRIDE : str  = None
DEFAULT_AGENT_OPTIONS_MARKDOWN        : bool = True


class AgentOptionsConfig(BaseConfig):
	type            : Annotated[Literal["agent_options_config"], FieldRole.CONSTANT] = "agent_options_config"
	description     : Annotated[Optional[str]                  , FieldRole.INPUT   ] = DEFAULT_AGENT_OPTIONS_DESCRIPTION
	instructions    : Annotated[Optional[List[str]]            , FieldRole.INPUT   ] = DEFAULT_AGENT_OPTIONS_INSTRUCTIONS
	prompt_override : Annotated[Optional[str]                  , FieldRole.INPUT   ] = DEFAULT_AGENT_OPTIONS_PROMPT_OVERRIDE
	markdown        : Annotated[bool                           , FieldRole.INPUT   ] = DEFAULT_AGENT_OPTIONS_MARKDOWN

	@property
	def get(self) -> Annotated[AgentOptionsConfig, FieldRole.OUTPUT]:
		return self


class AgentConfig(BaseConfig):
	type          : Annotated[Literal["agent_config"]                            , FieldRole.CONSTANT   ] = "agent_config"
	port          : Annotated[Optional[int]                                      , FieldRole.ANNOTATION ] = None
	info          : Annotated[Optional[InfoConfig]                               , FieldRole.INPUT      ] = None
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


# ========================================================================
# WORKFLOW NODES
# ========================================================================

class BaseNode(BaseType):
	type : Annotated[Literal["base_node"], FieldRole.CONSTANT] = "base_node"


class StartNode(BaseNode):
	type : Annotated[Literal["start_node"], FieldRole.CONSTANT] = "start_node"
	pin  : Annotated[Any                  , FieldRole.OUTPUT  ] = None


class EndNode(BaseNode):
	type : Annotated[Literal["end_node"], FieldRole.CONSTANT] = "end_node"
	pin  : Annotated[Any                , FieldRole.INPUT   ] = None


class SinkNode(BaseNode):
	type : Annotated[Literal["sink_node"], FieldRole.CONSTANT] = "sink_node"
	pin  : Annotated[Any                 , FieldRole.INPUT   ] = None


class PassThroughNode(BaseNode):
	type   : Annotated[Literal["pass_through_node"], FieldRole.CONSTANT] = "pass_through_node"
	input  : Annotated[Any                         , FieldRole.INPUT   ] = None
	output : Annotated[Any                         , FieldRole.OUTPUT  ] = None


class RouteNode(BaseNode):
	type    : Annotated[Literal["route_node"]           , FieldRole.CONSTANT    ] = "route_node"
	target  : Annotated[Union[int, str]                 , FieldRole.INPUT       ] = None
	input   : Annotated[Any                             , FieldRole.INPUT       ] = None
	output  : Annotated[Union[List[str], Dict[str, Any]], FieldRole.MULTI_OUTPUT] = None
	default : Annotated[Any                             , FieldRole.OUTPUT      ] = None


class CombineNode(BaseNode):
	type    : Annotated[Literal["combine_node"]         , FieldRole.CONSTANT    ] = "combine_node"
	mapping : Annotated[Dict[Union[int, str], str]      , FieldRole.INPUT       ] = None
	input   : Annotated[Union[List[str], Dict[str, Any]], FieldRole.MULTI_INPUT ] = None
	output  : Annotated[Union[List[str], Dict[str, Any]], FieldRole.MULTI_OUTPUT] = None


DEFAULT_MERGE_NODE_STRATEGY : str = "first"


class MergeNode(BaseNode):
	type     : Annotated[Literal["merge_node"]                  , FieldRole.CONSTANT   ] = "merge_node"
	strategy : Annotated[str                                    , FieldRole.INPUT      ] = DEFAULT_MERGE_NODE_STRATEGY
	input    : Annotated[Union[List[str], Dict[str, Any]]       , FieldRole.MULTI_INPUT] = None
	output   : Annotated[Any                                    , FieldRole.OUTPUT     ] = None


DEFAULT_TRANSFORM_NODE_LANG    : str            = "python"
DEFAULT_TRANSFORM_NODE_SCRIPT  : str            = "output = input"
DEFAULT_TRANSFORM_NODE_CONTEXT : Dict[str, Any] = {}


class TransformNode(BaseNode):
	type    : Annotated[Literal["transform_node"], FieldRole.CONSTANT] = "transform_node"
	lang    : Annotated[str                      , FieldRole.INPUT   ] = DEFAULT_TRANSFORM_NODE_LANG
	script  : Annotated[str                      , FieldRole.INPUT   ] = DEFAULT_TRANSFORM_NODE_SCRIPT
	context : Annotated[Dict[str, Any]           , FieldRole.INPUT   ] = DEFAULT_TRANSFORM_NODE_CONTEXT
	input   : Annotated[Any                      , FieldRole.INPUT   ] = None
	output  : Annotated[Any                      , FieldRole.OUTPUT  ] = None


class UserInputNode(BaseNode):
	type    : Annotated[Literal["user_input_node"], FieldRole.CONSTANT] = "user_input_node"
	query   : Annotated[Any                       , FieldRole.INPUT   ] = None
	content : Annotated[Any                       , FieldRole.OUTPUT  ] = None


DEFAULT_TOOL_NODE_ARGS : Dict[str, Any] = {}


class ToolNode(BaseNode):
	type   : Annotated[Literal["tool_node"], FieldRole.CONSTANT] = "tool_node"
	config : Annotated[ToolConfig          , FieldRole.INPUT   ] = None
	args   : Annotated[Dict[str, Any]      , FieldRole.INPUT   ] = DEFAULT_TOOL_NODE_ARGS
	input  : Annotated[Any                 , FieldRole.INPUT   ] = None
	output : Annotated[Any                 , FieldRole.OUTPUT  ] = None


class AgentNode(BaseNode):
	type   : Annotated[Literal["agent_node"], FieldRole.CONSTANT] = "agent_node"
	config : Annotated[AgentConfig          , FieldRole.INPUT   ] = None
	input  : Annotated[Any                  , FieldRole.INPUT   ] = None
	output : Annotated[Any                  , FieldRole.OUTPUT  ] = None


# ========================================================================
# INTERACTIVE NODES
# ========================================================================

class BaseInteractive(BaseType):
	type : Annotated[Literal["base_interactive"], FieldRole.CONSTANT] = "base_interactive"


class ToolCall(BaseInteractive):
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
class AgentChat(BaseInteractive):
	type          : Annotated[Literal["agent_chat"], FieldRole.CONSTANT] = "agent_chat"
	config        : Annotated[AgentConfig          , FieldRole.INPUT   ] = None
	system_prompt : Annotated[Optional[str]        , FieldRole.INPUT   ] = None
	# response      : Annotated[Any                  , FieldRole.OUTPUT  ] = None
	# chat          : Annotated[Any                  , FieldRole.OUTPUT  ] = None


# ========================================================================
# WORKFLOW NODE UNION
# ========================================================================

WorkflowNodeUnion = Union[
	# Native value nodes
	StringNode,
	IntegerNode,
	FloatNode,
	BooleanNode,
	ListNode,
	DictNode,

	# Data source nodes
	DataNode,
	TextDataNode,
	DocumentDataNode,
	ImageDataNode,
	AudioDataNode,
	VideoDataNode,
	Model3DDataNode,
	BinaryDataNode,

	# Config nodes
	InfoConfig,
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

	# Workflow nodes
	StartNode,
	EndNode,
	SinkNode,
	PassThroughNode,
	TransformNode,
	RouteNode,
	CombineNode,
	MergeNode,
	UserInputNode,
	ToolNode,
	AgentNode,

	# Interactive nodes
	ToolCall,
	AgentChat,
]


# ========================================================================
# WORKFLOW
# ========================================================================

DEFAULT_WORKFLOW_OPTIONS_SEED : int = 777


class WorkflowOptionsConfig(BaseConfig):
	type : Annotated[Literal["workflow_options_config"], FieldRole.CONSTANT] = "workflow_options_config"
	seed : Annotated[int                               , FieldRole.INPUT   ] = DEFAULT_WORKFLOW_OPTIONS_SEED

	@property
	def get(self) -> Annotated[WorkflowOptionsConfig, FieldRole.OUTPUT]:
		return self


class Workflow(BaseConfig):
	type    : Annotated[Literal["workflow"]            , FieldRole.CONSTANT] = "workflow"
	info    : Annotated[Optional[InfoConfig]           , FieldRole.INPUT   ] = None
	options : Annotated[Optional[WorkflowOptionsConfig], FieldRole.INPUT   ] = None
	nodes   : Annotated[Optional[List[Annotated[WorkflowNodeUnion, Field(discriminator="type")]]], FieldRole.INPUT] = None
	edges   : Annotated[Optional[List[Edge]]           , FieldRole.INPUT   ] = None

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


# ========================================================================
# TYPE MAPPINGS (for JS interop)
# ========================================================================

NATIVE_NODE_TYPES = {
	"native_string" : StringNode,
	"native_integer": IntegerNode,
	"native_float"  : FloatNode,
	"native_boolean": BooleanNode,
	"native_list"   : ListNode,
	"native_dict"   : DictNode,
}


NATIVE_NODE_TYPES = {
	"native_string" : StringNode,
	"native_integer": IntegerNode,
	"native_float"  : FloatNode,
	"native_boolean": BooleanNode,
	"native_list"   : ListNode,
	"native_dict"   : DictNode,
}


# ========================================================================
# MAIN
# ========================================================================

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
