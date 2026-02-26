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

	# @property
	# def get(self) -> Annotated[BaseType, FieldRole.OUTPUT]:
	# 	return self


@node_info(visible=False)
class ComponentType(BaseModel):
	type : Annotated[Literal["component_type"], FieldRole.CONSTANT] = "component_type"

	# @property
	# def get(self) -> Annotated[ComponentType, FieldRole.OUTPUT]:
	# 	return self


@node_info(visible=False)
class Edge(ComponentType):
	type        : Annotated[Literal["edge"], FieldRole.CONSTANT  ] = "edge"
	preview     : Annotated[bool           , FieldRole.ANNOTATION] = False  # Whether to show a preview of the data flowing through this edge in the UI
	loop        : Annotated[bool           , FieldRole.ANNOTATION] = False  # True for loop-back edges (visual hint)
	source      : Annotated[int            , FieldRole.INPUT     ] = None
	target      : Annotated[int            , FieldRole.INPUT     ] = None
	source_slot : Annotated[str            , FieldRole.INPUT     ] = None
	target_slot : Annotated[str            , FieldRole.INPUT     ] = None

	# @property
	# def get(self) -> Annotated[Edge, FieldRole.OUTPUT]:
	# 	return self


@node_info(
	title       = "Source Meta",
	description = "Holds meta information",
	icon        = "ⓘ",
	section     = "Data Sources",
	visible     = True
)
class SourceMeta(ComponentType):
	type        : Annotated[Literal["source_meta"], FieldRole.CONSTANT] = "source_meta"
	name        : Annotated[Optional[str  ]       , FieldRole.INPUT   ] = Field(default=None,  description="Human-readable name for the data source")
	description : Annotated[Optional[str  ]       , FieldRole.INPUT   ] = Field(default=None,  description="Short text description of the source content")
	source      : Annotated[Optional[str  ]       , FieldRole.INPUT   ] = Field(default=None,  description="Origin URI or identifier (e.g. file path, URL, database key)")
	mime_type   : Annotated[Optional[str  ]       , FieldRole.INPUT   ] = Field(default=None,  description="MIME type of the content (e.g. 'image/png', 'audio/wav')")
	format      : Annotated[Optional[str  ]       , FieldRole.INPUT   ] = Field(default=None,  description="Codec or data format identifier (e.g. 'mp3', 'h264')")
	streamable  : Annotated[Optional[bool ]       , FieldRole.INPUT   ] = Field(default=None,  description="Whether the source supports streaming delivery")
	size        : Annotated[Optional[int  ]       , FieldRole.INPUT   ] = Field(default=None,  description="Size of the source data in bytes")
	duration    : Annotated[Optional[float]       , FieldRole.INPUT   ] = Field(default=None,  description="Duration in seconds for audio or video sources")
	sampling    : Annotated[Optional[float]       , FieldRole.INPUT   ] = Field(default=None,  description="Sample rate or sampling frequency (e.g. 44100 for audio)")
	rate        : Annotated[Optional[float]       , FieldRole.INPUT   ] = Field(default=None,  description="Frame rate or data rate (e.g. 30 fps for video)")
	encoding    : Annotated[Optional[str  ]       , FieldRole.INPUT   ] = Field(default=None,  description="Character or binary encoding (e.g. 'utf-8', 'base64')")
	frames      : Annotated[Optional[int  ]       , FieldRole.INPUT   ] = Field(default=None,  description="Total number of frames for video or animation sources")

	@property
	def reference(self) -> Annotated[SourceMeta, FieldRole.OUTPUT]:
		return self


@node_info(visible=False)
class NativeType(BaseType):
	type : Annotated[Literal["native_type"], FieldRole.CONSTANT] = "native_type"
	raw  : Annotated[Any                   , FieldRole.INPUT   ] = None

	@property
	def value(self) -> Annotated[Any, FieldRole.OUTPUT]:
		return self.raw


@node_info(
	title       = "Boolean Constant",
	description = "Holds a boolean constant",
	icon        = "⏻",
	section     = "Native Types",
	visible     = True
)
class NativeBoolean(NativeType):
	"""Constant boolean value. Set value=true|false. Wire get→any bool input."""
	type : Annotated[Literal["native_boolean"], FieldRole.CONSTANT] = "native_boolean"
	raw  : Annotated[bool                     , FieldRole.INPUT   ] = Field(default=False, description="The constant boolean value (true or false)")

	@property
	def value(self) -> Annotated[bool, FieldRole.OUTPUT]:
		return self.raw


@node_info(
	title       = "Integer Number",
	description = "Holds an integer number",
	icon        = "🔢",
	section     = "Native Types",
	visible     = True
)
class NativeInteger(NativeType):
	"""Constant integer value. Set value to any integer. Wire get→any int input."""
	type : Annotated[Literal["native_integer"], FieldRole.CONSTANT] = "native_integer"
	raw  : Annotated[int                      , FieldRole.INPUT   ] = Field(default=0, description="The constant integer value")

	@property
	def value(self) -> Annotated[int, FieldRole.OUTPUT]:
		return self.raw


@node_info(
	title       = "Real Number",
	description = "Holds a real number",
	icon        = "ℛ",
	section     = "Native Types",
	visible     = True
)
class NativeReal(NativeType):
	"""Constant floating-point value. Set value to any number. Wire get→any float input."""
	type : Annotated[Literal["native_real"], FieldRole.CONSTANT] = "native_real"
	raw  : Annotated[float                 , FieldRole.INPUT   ] = Field(default=0.0, description="The constant floating-point value")

	@property
	def value(self) -> Annotated[float, FieldRole.OUTPUT]:
		return self.raw


@node_info(
	title       = "Character String",
	description = "Holds a string",
	icon        = "➰",
	section     = "Native Types",
	visible     = True
)
class NativeString(NativeType):
	"""Constant string value. Set value to any text. Wire get→any string input."""
	type : Annotated[Literal["native_string"], FieldRole.CONSTANT] = "native_string"
	raw  : Annotated[str                     , FieldRole.INPUT   ] = Field(default="", description="The constant string value")

	@property
	def value(self) -> Annotated[str, FieldRole.OUTPUT]:
		return self.raw


@node_info(
	title       = "List",
	description = "Holds a list of values",
	icon        = "☰",
	section     = "Native Types",
	visible     = True
)
class NativeList(NativeType):
	"""Constant list value. Set value to a JSON array. Wire get→any list input."""
	type : Annotated[Literal["native_list"], FieldRole.CONSTANT] = "native_list"
	raw  : Annotated[List[Any]             , FieldRole.INPUT   ] = Field(default=[], description="The constant list value (JSON array)")

	@property
	def value(self) -> Annotated[List[Any], FieldRole.OUTPUT]:
		return self.raw


@node_info(
	title       = "Dictionary",
	description = "Holds a key-value dictionary",
	icon        = "📔",
	section     = "Native Types",
	visible     = True
)
class NativeDictionary(NativeType):
	"""Constant dict value. Set value to a JSON object. Wire get→any dict input."""
	type : Annotated[Literal["native_dictionary"], FieldRole.CONSTANT] = "native_dictionary"
	raw  : Annotated[Dict[str, Any]              , FieldRole.INPUT   ] = Field(default={}, description="The constant dictionary value (JSON object)")

	@property
	def value(self) -> Annotated[Dict[str, Any], FieldRole.OUTPUT]:
		return self.raw


DEFAULT_TENSOR_DTYPE  : str  = "float32"


@node_info(visible=False)
class TensorType(BaseType):
	type   : Annotated[Literal["tensor_type"], FieldRole.CONSTANT] = "tensor_type"
	meta   : Annotated[Optional[SourceMeta]  , FieldRole.INPUT   ] = Field(default=None, description="Optional source metadata describing the tensor origin and properties")
	dtype  : Annotated[str                   , FieldRole.INPUT   ] = Field(default=DEFAULT_TENSOR_DTYPE, description="Data type of tensor elements (e.g. 'float32', 'int8', 'uint8')")
	shape  : Annotated[List[int]             , FieldRole.INPUT   ] = Field(default=[], description="Tensor dimensions as a list of integers (e.g. [batch, height, width, channels])")
	data   : Annotated[Any                   , FieldRole.INPUT   ] = Field(default=[], description="Nested list of values matching the declared shape")

	@property
	def tensor(self) -> Annotated[Any, FieldRole.OUTPUT]:
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
	def config(self) -> Annotated[ConfigType, FieldRole.OUTPUT]:
		return self


DEFAULT_OPTIONS_NAME        : str  = "Zoe"
DEFAULT_OPTIONS_DESCRIPTION : str  = None


@node_info(visible=False)
class OptionsType(BaseType):
	type        : Annotated[Literal["options_type"], FieldRole.CONSTANT] = "options_type"
	name        : Annotated[Optional[str]          , FieldRole.INPUT   ] = Field(default=DEFAULT_OPTIONS_NAME, description="Display name or identifier for this options configuration")
	description : Annotated[Optional[str]          , FieldRole.INPUT   ] = Field(default=DEFAULT_OPTIONS_DESCRIPTION, description="Optional description of the purpose of this options block")

	@property
	def options(self) -> Annotated[OptionsType, FieldRole.OUTPUT]:
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
	name     : Annotated[str                      , FieldRole.INPUT   ] = Field(default=DEFAULT_BACKEND_NAME,     description="Backend engine name; currently only 'agno' is supported")
	version  : Annotated[Optional[str]            , FieldRole.INPUT   ] = Field(default=DEFAULT_BACKEND_VERSION,  description="Optional engine version string; leave empty for latest")
	fallback : Annotated[bool                     , FieldRole.INPUT   ] = Field(default=DEFAULT_BACKEND_FALLBACK, description="If true, skip this backend silently when unavailable instead of raising an error")

	@property
	def config(self) -> Annotated[BackendConfig, FieldRole.OUTPUT]:
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
	source   : Annotated[str                    , FieldRole.INPUT   ] = Field(default=DEFAULT_MODEL_SOURCE,   json_schema_extra={"options_source": "model_sources"}, description="LLM provider (e.g. 'ollama', 'openai', 'anthropic', 'groq', 'google')")
	name     : Annotated[str                    , FieldRole.INPUT   ] = Field(default=DEFAULT_MODEL_NAME,    json_schema_extra={"options_source": "model_names"},   description="Model identifier as recognized by the provider (e.g. 'mistral', 'gpt-4o', 'claude-sonnet-4-6')")
	version  : Annotated[Optional[str]          , FieldRole.INPUT   ] = Field(default=DEFAULT_MODEL_VERSION,  description="Optional model version string; leave empty for provider default")
	fallback : Annotated[bool                   , FieldRole.INPUT   ] = Field(default=DEFAULT_MODEL_FALLBACK, description="If true, skip this model config silently when unavailable")

	@property
	def config(self) -> Annotated[ModelConfig, FieldRole.OUTPUT]:
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
	source   : Annotated[str                        , FieldRole.INPUT   ] = Field(default=DEFAULT_EMBEDDING_SOURCE,   json_schema_extra={"options_source": "model_sources"}, description="Embedding provider (e.g. 'ollama', 'openai', 'anthropic', 'groq', 'google')")
	name     : Annotated[str                        , FieldRole.INPUT   ] = Field(default=DEFAULT_EMBEDDING_NAME,    json_schema_extra={"options_source": "model_names"},   description="Embedding model identifier (e.g. 'nomic-embed-text', 'text-embedding-3-small')")
	version  : Annotated[Optional[str]              , FieldRole.INPUT   ] = Field(default=DEFAULT_EMBEDDING_VERSION,  description="Optional model version string; leave empty for provider default")
	fallback : Annotated[bool                       , FieldRole.INPUT   ] = Field(default=DEFAULT_EMBEDDING_FALLBACK, description="If true, skip this embedding config silently when unavailable")

	@property
	def config(self) -> Annotated[EmbeddingConfig, FieldRole.OUTPUT]:
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
	engine               : Annotated[str                         , FieldRole.INPUT     ] = Field(default=DEFAULT_CONTENT_DB_ENGINE,               description="Storage engine type; currently 'sqlite' is supported")
	url                  : Annotated[str                         , FieldRole.INPUT     ] = Field(default=DEFAULT_CONTENT_DB_URL,                  description="File path or connection URL for the database (e.g. 'storage/content')")
	memory_table_name    : Annotated[str                         , FieldRole.INPUT     ] = Field(default=DEFAULT_CONTENT_DB_MEMORY_TABLE_NAME,    description="Table name used to store long-term agent memory records")
	session_table_name   : Annotated[str                         , FieldRole.INPUT     ] = Field(default=DEFAULT_CONTENT_DB_SESSION_TABLE_NAME,   description="Table name used to store per-conversation session history")
	knowledge_table_name : Annotated[str                         , FieldRole.INPUT     ] = Field(default=DEFAULT_CONTENT_DB_KNOWLEDGE_TABLE_NAME, description="Table name used to store knowledge base documents for RAG")
	fallback             : Annotated[bool                        , FieldRole.INPUT     ] = Field(default=DEFAULT_CONTENT_DB_FALLBACK,             description="If true, skip this DB config silently when unavailable")

	@property
	def config(self) -> Annotated[ContentDBConfig, FieldRole.OUTPUT]:
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
	engine      : Annotated[str                       , FieldRole.INPUT   ] = Field(default=DEFAULT_INDEX_DB_ENGINE,      description="Vector database engine; currently 'lancedb' is supported")
	url         : Annotated[str                       , FieldRole.INPUT   ] = Field(default=DEFAULT_INDEX_DB_URL,         description="File path or connection URL for the vector database (e.g. 'storage/index')")
	embedding   : Annotated[EmbeddingConfig           , FieldRole.INPUT   ] = Field(default=None,                        description="EmbeddingConfig providing the model used to vectorize documents and queries")
	search_type : Annotated[str                       , FieldRole.INPUT   ] = Field(default=DEFAULT_INDEX_DB_SEARCH_TYPE, description="Search strategy — 'hybrid' combines vector similarity with keyword search")
	table_name  : Annotated[str                       , FieldRole.INPUT   ] = Field(default=DEFAULT_INDEX_DB_TABLE_NAME,  description="Table (collection) name within the vector database")
	fallback    : Annotated[bool                      , FieldRole.INPUT   ] = Field(default=DEFAULT_INDEX_DB_FALLBACK,    description="If true, skip this DB config silently when unavailable")

	@property
	def config(self) -> Annotated[IndexDBConfig, FieldRole.OUTPUT]:
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
	query   : Annotated[bool                            , FieldRole.INPUT   ] = Field(default=DEFAULT_MEMORY_MANAGER_QUERY,   description="If true, retrieve relevant memories before each agent response")
	update  : Annotated[bool                            , FieldRole.INPUT   ] = Field(default=DEFAULT_MEMORY_MANAGER_UPDATE,  description="If true, store new information as memories after each agent exchange")
	managed : Annotated[bool                            , FieldRole.INPUT   ] = Field(default=DEFAULT_MEMORY_MANAGER_MANAGED, description="If true, the backend manages memory consolidation automatically")
	model   : Annotated[Optional[ModelConfig]           , FieldRole.INPUT   ] = Field(default=None,                          description="Optional language model used for memory summarization and extraction")
	prompt  : Annotated[Optional[str]                   , FieldRole.INPUT   ] = Field(default=DEFAULT_MEMORY_MANAGER_PROMPT,  description="Optional custom system prompt override for the memory manager")

	@property
	def config(self) -> Annotated[MemoryManagerConfig, FieldRole.OUTPUT]:
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
	query        : Annotated[bool                             , FieldRole.INPUT   ] = Field(default=DEFAULT_SESSION_MANAGER_QUERY,        description="If true, include conversation history in each agent request")
	update       : Annotated[bool                             , FieldRole.INPUT   ] = Field(default=DEFAULT_SESSION_MANAGER_UPDATE,       description="If true, append each exchange to the persisted session history")
	history_size : Annotated[int                              , FieldRole.INPUT   ] = Field(default=DEFAULT_SESSION_MANAGER_HISTORY_SIZE, description="Maximum number of past exchanges included as context (sliding window)")
	model        : Annotated[Optional[ModelConfig]            , FieldRole.INPUT   ] = Field(default=None,                                description="Optional language model used for history summarization when history is long")
	prompt       : Annotated[Optional[str]                    , FieldRole.INPUT   ] = Field(default=DEFAULT_SESSION_MANAGER_PROMPT,       description="Optional custom system prompt override for the session manager")

	@property
	def config(self) -> Annotated[SessionManagerConfig, FieldRole.OUTPUT]:
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
	query       : Annotated[bool                               , FieldRole.INPUT   ] = Field(default=DEFAULT_KNOWLEDGE_MANAGER_QUERY,       description="If true, perform RAG retrieval to augment the agent's context on each request")
	description : Annotated[Optional[str]                      , FieldRole.INPUT   ] = Field(default=None,                                  description="Short description of this knowledge base, used to guide the agent's retrieval")
	# content_db  : Annotated[Optional[ContentDBConfig]          , FieldRole.INPUT   ] = None
	content_db  : Annotated[ContentDBConfig                    , FieldRole.INPUT   ] = Field(default=None,                                  description="ContentDBConfig providing the raw document storage backend")
	index_db    : Annotated[IndexDBConfig                      , FieldRole.INPUT   ] = Field(default=None,                                  description="IndexDBConfig providing the vector index for semantic search")
	max_results : Annotated[int                                , FieldRole.INPUT   ] = Field(default=DEFAULT_KNOWLEDGE_MANAGER_MAX_RESULTS, description="Maximum number of documents to retrieve per query")
	urls        : Annotated[Optional[List[str]]                , FieldRole.INPUT   ] = Field(default=None,                                  description="Optional list of URLs to seed the knowledge base with on startup")

	@property
	def config(self) -> Annotated[KnowledgeManagerConfig, FieldRole.OUTPUT]:
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
	name     : Annotated[str                     , FieldRole.INPUT   ] = Field(default="",   description="Python import path to the tool function (e.g. 'tools.search_web', 'tools.list_directory')")
	args     : Annotated[Optional[Dict[str, Any]], FieldRole.INPUT   ] = Field(default=None, description="Optional default arguments passed to the tool; merged with any runtime arguments")
	lang     : Annotated[Optional[str]           , FieldRole.INPUT   ] = Field(default=None, description="Scripting language for inline script tools (e.g. 'python'); leave None when using name")
	script   : Annotated[Optional[str]           , FieldRole.INPUT   ] = Field(default=None, description="Inline script body when lang is set; the return value or last expression becomes the result")
	fallback : Annotated[bool                    , FieldRole.INPUT   ] = Field(default=DEFAULT_TOOL_FALLBACK, description="If true, skip this tool silently when unavailable instead of raising an error")

	@property
	def config(self) -> Annotated[ToolConfig, FieldRole.OUTPUT]:
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
	instructions    : Annotated[Optional[List[str]]            , FieldRole.INPUT   ] = Field(default=DEFAULT_AGENT_OPTIONS_INSTRUCTIONS,    description="List of instruction strings appended to the agent system prompt (one per line)")
	prompt_override : Annotated[Optional[str]                  , FieldRole.INPUT   ] = Field(default=DEFAULT_AGENT_OPTIONS_PROMPT_OVERRIDE, description="Full system prompt text; when set, replaces all default instructions entirely")
	markdown        : Annotated[bool                           , FieldRole.INPUT   ] = Field(default=DEFAULT_AGENT_OPTIONS_MARKDOWN,        description="If true, instruct the agent to format its responses using Markdown")

	@property
	def options(self) -> Annotated[AgentOptionsConfig, FieldRole.OUTPUT]:
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
	type          : Annotated[Literal["agent_config"]                           , FieldRole.CONSTANT   ] = "agent_config"
	port          : Annotated[Optional[int]                                     , FieldRole.ANNOTATION ] = None
	options       : Annotated[Optional[AgentOptionsConfig]                      , FieldRole.INPUT      ] = Field(default=None, description="AgentOptionsConfig defining the agent persona, instructions, and system prompt")
	backend       : Annotated[BackendConfig                                     , FieldRole.INPUT      ] = Field(default=None, description="BackendConfig specifying which AI engine to use (e.g. 'agno')")
	model         : Annotated[ModelConfig                                       , FieldRole.INPUT      ] = Field(default=None, description="ModelConfig specifying the language model provider and name")
	content_db    : Annotated[Optional[ContentDBConfig]                         , FieldRole.INPUT      ] = Field(default=None, description="Optional ContentDBConfig for direct database access (bypasses the knowledge manager)")
	memory_mgr    : Annotated[Optional[MemoryManagerConfig]                     , FieldRole.INPUT      ] = Field(default=None, description="Optional MemoryManagerConfig for long-term memory persistence across sessions")
	session_mgr   : Annotated[Optional[SessionManagerConfig]                    , FieldRole.INPUT      ] = Field(default=None, description="Optional SessionManagerConfig for per-conversation history management")
	knowledge_mgr : Annotated[Optional[KnowledgeManagerConfig]                  , FieldRole.INPUT      ] = Field(default=None, description="Optional KnowledgeManagerConfig enabling RAG retrieval from a document store")
	tools         : Annotated[Optional[Dict[str, ToolConfig]]                   , FieldRole.MULTI_INPUT] = Field(default=None, description="Dict of ToolConfig nodes; each key becomes a callable tool name available to the agent")

	@property
	def config(self) -> Annotated[AgentConfig, FieldRole.OUTPUT]:
		return self


@node_info(visible=False)
class FlowType(BaseType):
	type     : Annotated[Literal["flow_type"], FieldRole.CONSTANT] = "flow_type"
	flow_in  : Annotated[Optional[Any]       , FieldRole.INPUT   ] = Field(default=None, description="Receives the execution token from the upstream flow node; connect from the previous node's flow_out")
	flow_out : Annotated[Optional[Any]       , FieldRole.OUTPUT  ] = Field(default=None, description="Passes the execution token to the next downstream flow node; connect to the next node's flow_in")


@node_info(
	title       = "Start",
	description = "Represents the start of a workflow",
	icon        = "▶",
	section     = "Endpoints",
	visible     = True
)
class StartFlow(FlowType):
	"""Required workflow entry point. Always place at index 0. Outputs initial workflow variables as a dict on 'flow_out'."""
	type : Annotated[Literal["start_flow"], FieldRole.CONSTANT] = "start_flow"


@node_info(
	title       = "End",
	description = "Represents the end of a workflow",
	icon        = "🏁",
	section     = "Endpoints",
	visible     = True
)
class EndFlow(FlowType):
	"""Successful workflow termination. Connect final data value to 'flow_in'."""
	type : Annotated[Literal["end_flow"], FieldRole.CONSTANT] = "end_flow"


@node_info(
	title       = "Sink",
	description = "Workflow dead end",
	icon        = "🚧",
	section     = "Endpoints",
	visible     = True
)
class SinkFlow(FlowType):
	"""Workflow dead end — discards its input. Use to terminate branches that produce no result."""
	type : Annotated[Literal["sink_flow"], FieldRole.CONSTANT] = "sink_flow"


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
	hint   : Annotated[Literal["auto", "text", "json", "image", "audio", "video", "model3d"], FieldRole.INPUT   ] = Field(default="auto",  description="Rendering hint for the UI preview panel — controls how the incoming data is visualized")
	input  : Annotated[Optional[Any]                                                        , FieldRole.INPUT   ] = Field(default=None,    description="Data to preview — wire from any node output (base64 JPEG for image, dict/list for json, string for text)")
	output : Annotated[Optional[Any]                                                        , FieldRole.OUTPUT  ] = Field(default=None,    description="Input data passed through unchanged")


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
	target  : Annotated[Optional[Any]                   , FieldRole.INPUT       ] = Field(default=None, description="Branch key or index to route to; unmatched values pass through to the 'default' output")
	input   : Annotated[Optional[Any]                   , FieldRole.INPUT       ] = Field(default=None, description="Data value to forward to the selected output branch")
	output  : Annotated[Union[List[str], Dict[str, Any]], FieldRole.MULTI_OUTPUT] = Field(default=None, description="Named output branches — declare as JSON dict with null values (e.g. {branch_a: null, branch_b: null})")
	default : Annotated[Optional[Any]                   , FieldRole.OUTPUT      ] = Field(default=None, description="Fallback output when target does not match any declared branch key")


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
	mapping : Annotated[Dict[Union[int, str], str]      , FieldRole.INPUT       ] = Field(default=None, description="Dict mapping input branch keys to output branch keys (e.g. {src: dst})")
	input   : Annotated[Union[List[str], Dict[str, Any]], FieldRole.MULTI_INPUT ] = Field(default=None, description="Named input branches — connect via dotted edges (target_slot='input.<key>')")
	output  : Annotated[Union[List[str], Dict[str, Any]], FieldRole.MULTI_OUTPUT] = Field(default=None, description="Named output branches — declare as JSON object and connect via dotted edges")


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
	strategy : Annotated[str                             , FieldRole.INPUT      ] = Field(default=DEFAULT_MERGE_NODE_STRATEGY, description="Merge strategy — 'first' (first non-None), 'last', 'concat' (join strings/lists), 'all' (return list)")
	input    : Annotated[Union[List[str], Dict[str, Any]], FieldRole.MULTI_INPUT] = Field(default=None,                       description="Named input branches to merge — connect via dotted edges (target_slot='input.<key>')")
	output   : Annotated[Any                             , FieldRole.OUTPUT     ] = Field(default=None,                       description="Merged result passed downstream according to the selected strategy")


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
	lang    : Annotated[str                      , FieldRole.INPUT   ] = Field(default=DEFAULT_TRANSFORM_NODE_LANG,   description="Scripting language for the transform; currently only 'python' is supported")
	script  : Annotated[str                      , FieldRole.INPUT   ] = Field(default=DEFAULT_TRANSFORM_NODE_SCRIPT, json_schema_extra={"editor": "code"}, description="Python code to execute; assign `output` to produce a result; read `input`, `variables`, `context`")
	context : Annotated[Optional[Dict[str, Any]] , FieldRole.INPUT   ] = Field(default=None,                         description="Optional extra dict injected into the script scope as the `context` variable")
	input   : Annotated[Optional[Any]            , FieldRole.INPUT   ] = Field(default=None,                         description="Data passed into the script as the `input` variable")
	output  : Annotated[Any                      , FieldRole.OUTPUT  ] = Field(default=None,                         description="Result produced by the script (the value assigned to `output` inside the script)")


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
	config : Annotated[ToolConfig          , FieldRole.INPUT   ] = Field(default=None,                 description="ToolConfig describing which tool to invoke; wire from a tool_config node")
	args   : Annotated[Dict[str, Any]      , FieldRole.INPUT   ] = Field(default=DEFAULT_TOOL_NODE_ARGS, description="Optional runtime argument overrides merged with the tool's default arguments")
	input  : Annotated[Any                 , FieldRole.INPUT   ] = Field(default=None,                 description="Primary data passed to the tool as its main input")
	output : Annotated[Any                 , FieldRole.OUTPUT  ] = Field(default=None,                 description="Result returned by the tool after execution")


@node_info(
	title       = "Agent Proxy",
	description = "Proxy for agent invocation",
	icon        = "🕵️‍♂️",
	section     = "Workflow",
	visible     = True
)
class AgentFlow(FlowType):
	"""Execute one agent turn within the flow graph. Wire agent_config→config. Text/dict on 'request'; LLM response dict on 'response'."""
	type     : Annotated[Literal["agent_flow"], FieldRole.CONSTANT] = "agent_flow"
	config   : Annotated[AgentConfig          , FieldRole.INPUT   ] = Field(default=None, description="AgentConfig describing the agent to invoke; wire from an agent_config node")
	request  : Annotated[Any                  , FieldRole.INPUT   ] = Field(default=None, description="Text or dict sent as the user message to the agent for this turn")
	response : Annotated[Any                  , FieldRole.OUTPUT  ] = Field(default=None, description="Dict containing the agent's response content and metadata")


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
	type      : Annotated[Literal["loop_start_flow"], FieldRole.CONSTANT] = "loop_start_flow"
	condition : Annotated[bool                      , FieldRole.INPUT   ] = Field(default=True,                        description="Loop continuation condition; evaluated before each iteration — loop stops when False")
	max_iter  : Annotated[int                       , FieldRole.INPUT   ] = Field(default=DEFAULT_LOOP_MAX_ITERATIONS, description="Safety cap on the number of iterations to prevent infinite loops")
	iteration : Annotated[int                       , FieldRole.OUTPUT  ] = Field(default=0,                           description="Current iteration counter, starting at 0 and incrementing each loop cycle")


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
	type : Annotated[Literal["loop_end_flow"], FieldRole.CONSTANT] = "loop_end_flow"


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
	items   : Annotated[List[Any]                     , FieldRole.INPUT   ] = Field(default=None, description="List to iterate over; the loop body executes once for each element")
	current : Annotated[Any                           , FieldRole.OUTPUT  ] = Field(default=None, description="The current item in the iteration, updated on each loop cycle")
	index   : Annotated[int                           , FieldRole.OUTPUT  ] = Field(default=0,    description="Zero-based index of the current item within the list")


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
	type : Annotated[Literal["for_each_end_flow"], FieldRole.CONSTANT] = "for_each_end_flow"


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
	type : Annotated[Literal["break_flow"], FieldRole.CONSTANT] = "break_flow"


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
	3. Return to the LoopStart/ForEachStart for the next iteration
	"""
	type : Annotated[Literal["continue_flow"], FieldRole.CONSTANT] = "continue_flow"


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
	input         : Annotated[Any                 , FieldRole.INPUT   ] = Field(default=None,                  description="Data to accumulate; each execution adds this value to the internal buffer")
	threshold     : Annotated[int                 , FieldRole.INPUT   ] = Field(default=DEFAULT_GATE_THRESHOLD, description="Number of inputs that must arrive before the gate fires and passes data downstream")
	condition     : Annotated[Optional[str]       , FieldRole.INPUT   ] = Field(default=None,                  description="Optional Python expression evaluated on each input; gate fires immediately when True")  # Python expression
	reset_on_fire : Annotated[bool                , FieldRole.INPUT   ] = Field(default=DEFAULT_GATE_RESET,    description="If true, reset the counter and accumulated buffer after the gate fires")
	count         : Annotated[int                 , FieldRole.OUTPUT  ] = Field(default=0,                     description="Number of inputs received since the last reset")
	accumulated   : Annotated[List[Any]           , FieldRole.OUTPUT  ] = Field(default=None,                  description="List of all input values accumulated since the last reset")
	triggered     : Annotated[bool                , FieldRole.OUTPUT  ] = Field(default=False,                 description="True on the execution step when the gate fires; False otherwise")
	output        : Annotated[Any                 , FieldRole.OUTPUT  ] = Field(default=None,                  description="The latest input value passed downstream when the gate fires")


DEFAULT_DELAY_DURATION_MS : int  = 1000


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
	type        : Annotated[Literal["delay_flow"], FieldRole.CONSTANT] = "delay_flow"
	duration_ms : Annotated[int                  , FieldRole.INPUT   ] = Field(default=DEFAULT_DELAY_DURATION_MS, description="Pause duration in milliseconds before passing data to the next node")
	input       : Annotated[Optional[Any]        , FieldRole.INPUT   ] = Field(default=None,                     description="Data to pass through unchanged after the delay expires")
	output      : Annotated[Any                  , FieldRole.OUTPUT  ] = Field(default=None,                     description="Input data forwarded downstream after the delay")


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
	type       : Annotated[Literal["event_listener_flow"], FieldRole.CONSTANT   ] = "event_listener_flow"
	sources    : Annotated[Optional[Dict[str, Any]]      , FieldRole.MULTI_INPUT] = Field(default=None,   description="Dict of registered source IDs to listen to — wire from source node 'registered_id' outputs")  # Source IDs (multi-input from source nodes)
	mode       : Annotated[Literal["any", "all", "race"] , FieldRole.INPUT      ] = Field(default="any",  description="Trigger mode — 'any' fires on first source, 'all' waits for all sources, 'race' fires then resets")
	timeout_ms : Annotated[Optional[int]                 , FieldRole.INPUT      ] = Field(default=None,   description="Maximum wait time in milliseconds; None means wait indefinitely for an event")  # None = no timeout
	# Outputs
	event      : Annotated[Any                           , FieldRole.OUTPUT     ] = Field(default=None,   description="The event data payload received from the triggering source")
	source_id  : Annotated[Optional[str]                 , FieldRole.OUTPUT     ] = Field(default=None,   description="ID of the event source that triggered this listener")
	events     : Annotated[Optional[Dict[str, Any]]      , FieldRole.OUTPUT     ] = Field(default=None,   description="Dict of all received events keyed by source ID (populated in 'all' mode)")
	timed_out  : Annotated[bool                          , FieldRole.OUTPUT     ] = Field(default=False,  description="True if the listener exited because the timeout elapsed rather than receiving an event")


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
	type          : Annotated[Literal["timer_source_flow"], FieldRole.CONSTANT] = "timer_source_flow"
	source_id     : Annotated[Optional[str]               , FieldRole.INPUT   ] = Field(default=None,                         description="Optional stable identifier for this timer; auto-generated if not set")
	interval_ms   : Annotated[int                         , FieldRole.INPUT   ] = Field(default=DEFAULT_TIMER_INTERVAL_MS,    description="Time between timer events in milliseconds (e.g. 1000 = once per second)")
	max_triggers  : Annotated[int                         , FieldRole.INPUT   ] = Field(default=DEFAULT_TIMER_MAX_TRIGGERS,   description="Maximum number of times the timer fires before stopping (-1 = unlimited)")
	immediate     : Annotated[bool                        , FieldRole.INPUT   ] = Field(default=False,                        description="If true, fire one event immediately before starting the regular interval")
	registered_id : Annotated[Optional[str]               , FieldRole.OUTPUT  ] = Field(default=None,                        description="The ID assigned to this timer source after registration; wire to event_listener.sources")


@node_info(
	title       = "FS Watch Source",
	description = "Registers a filesystem watcher event source. Connect its output to an Event Listener's sources input.",
	icon        = "📂",
	section     = "Event Sources",
	visible     = True
)
class FSWatchSourceFlow(FlowType):
	"""FS Watch Source node - watches filesystem paths for changes."""
	type          : Annotated[Literal["fswatch_source_flow"], FieldRole.CONSTANT] = "fswatch_source_flow"
	source_id     : Annotated[Optional[str]                 , FieldRole.INPUT   ] = Field(default=None,       description="Optional stable identifier for this watcher; auto-generated if not set")
	path          : Annotated[str                           , FieldRole.INPUT   ] = Field(default=".",        description="File system path to watch for changes (file or directory)")
	recursive     : Annotated[bool                          , FieldRole.INPUT   ] = Field(default=True,       description="If true, watch all subdirectories recursively under the given path")
	patterns      : Annotated[Optional[str]                 , FieldRole.INPUT   ] = Field(default="*",        description="Comma-separated glob patterns to filter file events (e.g. '*.py,*.json')")
	events        : Annotated[Optional[str]                 , FieldRole.INPUT   ] = Field(default="created,modified,deleted,moved", description="Comma-separated event types to watch for: created, modified, deleted, moved")
	debounce_ms   : Annotated[int                           , FieldRole.INPUT   ] = Field(default=100,        description="Milliseconds to wait after the last change before emitting an event (reduces noise)")
	registered_id : Annotated[Optional[str]                 , FieldRole.OUTPUT  ] = Field(default=None,       description="The ID assigned to this watcher after registration; wire to event_listener.sources")


@node_info(
	title       = "Webhook Source",
	description = "Registers a webhook event source. Connect its output to an Event Listener's sources input.",
	icon        = "🔗",
	section     = "Event Sources",
	visible     = True
)
class WebhookSourceFlow(FlowType):
	"""Webhook Source node - receives HTTP webhook events."""
	type          : Annotated[Literal["webhook_source_flow"], FieldRole.CONSTANT] = "webhook_source_flow"
	source_id     : Annotated[Optional[str]                 , FieldRole.INPUT   ] = Field(default=None,             description="Optional stable identifier for this webhook; auto-generated if not set")
	endpoint      : Annotated[str                           , FieldRole.INPUT   ] = Field(default="/hook/default",  description="URL path at which this webhook listens for incoming HTTP requests (e.g. '/hook/my-event')")
	methods       : Annotated[Optional[str]                 , FieldRole.INPUT   ] = Field(default="POST",           description="Comma-separated HTTP methods accepted by this webhook (e.g. 'POST,GET')")
	secret        : Annotated[Optional[str]                 , FieldRole.INPUT   ] = Field(default=None,             description="Optional secret token used to validate incoming webhook request signatures")
	registered_id : Annotated[Optional[str]                 , FieldRole.OUTPUT  ] = Field(default=None,             description="The ID assigned to this webhook after registration; wire to event_listener.sources")


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
	type          : Annotated[Literal["browser_source_flow"]             , FieldRole.CONSTANT] = "browser_source_flow"
	source_id     : Annotated[Optional[str]                              , FieldRole.INPUT   ] = Field(default=None,       description="Optional stable identifier for this browser source; auto-generated if not set")
	device_type   : Annotated[Literal["webcam", "microphone", "screen"]  , FieldRole.INPUT   ] = Field(default="webcam",   description="Media device to capture from — 'webcam' for video, 'microphone' for audio, 'screen' for screen capture")
	mode          : Annotated[Literal["stream", "event"]                 , FieldRole.INPUT   ] = Field(default="event",    description="Capture mode — 'stream' for continuous data delivery, 'event' for periodic snapshots")
	interval_ms   : Annotated[int                                        , FieldRole.INPUT   ] = Field(default=1000,       description="Milliseconds between capture snapshots when mode is 'event'")
	resolution    : Annotated[Optional[str]                              , FieldRole.INPUT   ] = Field(default=None,       description="Optional resolution string for video sources (e.g. '1280x720', '1920x1080')")
	audio_format  : Annotated[Optional[str]                              , FieldRole.INPUT   ] = Field(default=None,       description="Optional audio encoding format for microphone sources (e.g. 'wav', 'opus')")
	registered_id : Annotated[Optional[str]                              , FieldRole.OUTPUT  ] = Field(default=None,       description="The ID assigned to this browser source after registration; wire to event_listener.sources")


# =============================================================================
# ML INFERENCE / STREAM DISPLAY FLOW NODES
# =============================================================================

@node_info(
	title       = "Pose Detector",
	description = "Runs MediaPipe pose detection on a video frame. "
	              "Receives a frame (base64 JPEG) from a Browser Source event and outputs "
	              "the detected skeleton landmarks. Install: pip install mediapipe Pillow numpy",
	icon        = "🦴",
	section     = "ML / Stream",
	visible     = True
)
class PoseDetectorFlow(FlowType):
	"""Pose detection node — runs MediaPipe Pose on a received video frame."""
	type           : Annotated[Literal["pose_detector_flow"]              , FieldRole.CONSTANT] = "pose_detector_flow"
	frame          : Annotated[Optional[Any]                              , FieldRole.INPUT   ] = Field(default=None,      description="Video frame to analyse — base64-encoded JPEG string, as produced by the Browser Source event data['frame'] field")
	model          : Annotated[Literal["lite", "full", "heavy"]           , FieldRole.INPUT   ] = Field(default="lite",    description="MediaPipe model complexity — 'lite' is fastest, 'heavy' is most accurate")
	min_confidence : Annotated[float                                      , FieldRole.INPUT   ] = Field(default=0.5,       description="Minimum detection confidence threshold (0–1); lower = more detections but more false positives")
	keypoints      : Annotated[Optional[Any]                              , FieldRole.OUTPUT  ] = Field(default=None,      description="Detected pose as a dict with 'landmarks' (list of 33 points with x/y/z/visibility), 'width', 'height'")
	landmarks      : Annotated[Optional[List]                             , FieldRole.OUTPUT  ] = Field(default=None,      description="Raw list of 33 landmark dicts [{x, y, z, visibility}] in normalised coordinates (0–1)")
	pose_found     : Annotated[bool                                       , FieldRole.OUTPUT  ] = Field(default=False,     description="True when at least one person was detected in the frame")


@node_info(
	title       = "Stream Display",
	description = "Sends data (pose keypoints, text, or custom payload) back to the browser "
	              "for overlay rendering on the live video feed. Wire from Pose Detector or "
	              "any transform node; the matching Browser Source overlay canvas will be updated.",
	icon        = "📺",
	section     = "ML / Stream",
	visible     = True
)
class StreamDisplayFlow(FlowType):
	"""Stream Display node — pushes overlay render data to the browser over the stream WebSocket."""
	type        : Annotated[Literal["stream_display_flow"]                                   , FieldRole.CONSTANT] = "stream_display_flow"
	source_id   : Annotated[Optional[str]                                                    , FieldRole.INPUT   ] = Field(default=None,    description="ID of the Browser Source whose overlay should be updated; wire from browser_source_flow.registered_id")
	data        : Annotated[Optional[Any]                                                    , FieldRole.INPUT   ] = Field(default=None,    description="Data to render — for 'pose' use the keypoints output from Pose Detector; for 'text' use any string or dict")
	render_type : Annotated[Literal["pose", "landmarks", "text", "custom", "image"]          , FieldRole.INPUT   ] = Field(default="pose",  description="How to render the data — 'pose' draws a skeleton, 'landmarks' draws dots only, 'text' shows a text overlay, 'image' displays a full annotated JPEG frame, 'custom' passes raw JSON to the frontend")
	done        : Annotated[Optional[bool]                                                   , FieldRole.OUTPUT  ] = Field(default=None,    description="True after the display event has been dispatched to the browser")


@node_info(
	title       = "Computer Vision",
	description = "Runs a computer vision task (pose, face, hands) on an image frame. "
	              "Set inference_location='frontend' for zero-latency in-browser inference "
	              "via a MediaPipe Web Worker (~20 fps, no backend round-trip). "
	              "Set inference_location='backend' for server-side Python MediaPipe inference "
	              "(chainable with other backend nodes; wire rendered_image → stream_display_flow). "
	              "Connect source_id from a Browser Source to link the live video stream.",
	icon        = "🤖",
	section     = "ML / Stream",
	visible     = True
)
class ComputerVisionFlow(FlowType):
	"""Computer Vision node — runs ML inference on video frames in the browser or on the server."""
	type               : Annotated[Literal["computer_vision_flow"]                           , FieldRole.CONSTANT] = "computer_vision_flow"
	image              : Annotated[Optional[Any]                                             , FieldRole.INPUT   ] = Field(default=None,        description="Input image — base64-encoded JPEG from a Browser Source frame. Not required in frontend mode (the browser Worker reads directly from the live <video> element).")
	source_id          : Annotated[Optional[str]                                             , FieldRole.INPUT   ] = Field(default=None,        description="Browser Source ID — wire from browser_source_flow.registered_id. Used to route the rendered result back to the correct overlay (both modes) and to identify the live video element (frontend mode).")
	task               : Annotated[Literal["pose", "face", "hands"]                          , FieldRole.INPUT   ] = Field(default="pose",      description="Computer vision task — 'pose' detects a full-body skeleton (33 keypoints), 'face' detects face mesh landmarks, 'hands' detects hand landmarks")
	model_size         : Annotated[Literal["lite", "full", "heavy"]                          , FieldRole.INPUT   ] = Field(default="lite",      description="Model complexity: 'lite' is fastest (~15 ms/frame), 'full' is balanced, 'heavy' is most accurate but slowest")
	min_confidence     : Annotated[float                                                     , FieldRole.INPUT   ] = Field(default=0.5,         description="Minimum detection confidence (0–1); lower values detect more but increase false positives")
	draw_overlay       : Annotated[bool                                                      , FieldRole.INPUT   ] = Field(default=True,        description="When True, detected skeleton/landmarks are drawn on top of the input image and returned as rendered_image (backend mode only)")
	inference_location : Annotated[Literal["frontend", "backend"]                            , FieldRole.INPUT   ] = Field(default="frontend",  description="Where to run inference — 'frontend' uses a browser Web Worker (zero network latency, ~20 fps, no backend dependency); 'backend' uses server-side Python MediaPipe (adds ~30–80 ms round-trip but lets you chain results with other backend nodes)")
	rendered_image     : Annotated[Optional[Any]                                             , FieldRole.OUTPUT  ] = Field(default=None,        description="Annotated image with skeleton/landmarks drawn — base64 JPEG. Available only in backend mode; wire to stream_display_flow with render_type='image' to display on the Browser Source overlay.")
	detections         : Annotated[Optional[Any]                                             , FieldRole.OUTPUT  ] = Field(default=None,        description="Detection results — for 'pose', a list of 33 landmark dicts [{x,y,z,visibility}] in normalised 0–1 coordinates. Null when nothing is detected or in frontend mode (results are delivered via the stream WebSocket instead).")


# =============================================================================
# END ML INFERENCE / STREAM DISPLAY FLOW NODES
# =============================================================================


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
	query   : Annotated[Optional[Any]             , FieldRole.INPUT   ] = Field(default=DEFAULT_USER_INPUT_QUERY, description="Prompt text or rich content displayed to the user when the workflow pauses for input")
	message : Annotated[Optional[Any]             , FieldRole.OUTPUT  ] = Field(default=None,                     description="The user's response text or data, available downstream after the user submits input")


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
	config : Annotated[ToolConfig              , FieldRole.INPUT   ] = Field(default=None, description="ToolConfig describing which tool to invoke; wire from a tool_config node")
	args   : Annotated[Optional[Dict[str, Any]], FieldRole.INPUT   ] = Field(default=None, description="Optional argument overrides for this interactive invocation")
	result : Annotated[Any                     , FieldRole.OUTPUT  ] = Field(default=None, description="The tool's return value after the user triggers execution")


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
	config        : Annotated[AgentConfig          , FieldRole.INPUT   ] = Field(default=None, description="AgentConfig defining the agent to converse with; wire from an agent_config node")
	system_prompt : Annotated[Optional[str]        , FieldRole.INPUT   ] = Field(default=None, description="Optional system prompt override applied to this chat session only")
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
	step  : Annotated[int               , FieldRole.INPUT   ] = Field(default=1, description="Amount added or subtracted on each Increment or Decrement button press")
	value : Annotated[int               , FieldRole.OUTPUT  ] = Field(default=0, description="Current counter value; wire to any integer input downstream")

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

	# ML / Stream nodes
	PoseDetectorFlow,
	StreamDisplayFlow,
	ComputerVisionFlow,

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
	exec_delay         : Annotated[Optional[float]                      , FieldRole.INPUT   ] = Field(default=DEFAULT_WORKFLOW_EXEC_DELAY,         description="Seconds to pause between each workflow execution cycle (throttles the main loop)")
	node_delay         : Annotated[Optional[float]                      , FieldRole.INPUT   ] = Field(default=DEFAULT_WORKFLOW_NODE_DELAY,         description="Seconds to pause after each individual node execution completes")
	user_input_timeout : Annotated[Optional[float]                      , FieldRole.INPUT   ] = Field(default=DEFAULT_WORKFLOW_USER_INPUT_TIMEOUT, description="Maximum seconds to wait for user input before the workflow times out")

	@property
	def get(self) -> Annotated[WorkflowExecutionOptions, FieldRole.OUTPUT]:
		return self


DEFAULT_WORKFLOW_OPTIONS_SEED : int = 777


@node_info(visible=False)
class WorkflowOptions(OptionsType):
	type : Annotated[Literal["workflow_options"], FieldRole.CONSTANT] = "workflow_options"
	seed : Annotated[int                        , FieldRole.INPUT   ] = Field(default=DEFAULT_WORKFLOW_OPTIONS_SEED, description="Random seed for reproducibility across workflow runs")

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
