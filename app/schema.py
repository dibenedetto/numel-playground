# schema

<<<<<<< HEAD
from   collections.abc import Callable
from   enum            import Enum
from   pydantic        import BaseModel
from   typing          import Any, Dict, List, Optional, Union
=======
from pydantic import BaseModel
from typing   import Any, Dict, List, Optional, Union
>>>>>>> workflows


DEFAULT_APP_MAX_AGENTS                          : int  = 100
DEFAULT_APP_PORT                                : int  = 8000
DEFAULT_APP_API_KEY                             : str  = None

DEFAULT_APP_OPTIONS_RELOAD                      : bool = True
DEFAULT_APP_OPTIONS_SEED                        : int  = None

DEFAULT_BACKEND_TYPE                            : str  = "agno"
DEFAULT_BACKEND_VERSION                         : str  = ""
DEFAULT_BACKEND_FALLBACK                        : bool = False

DEFAULT_MODEL_TYPE                              : str  = "ollama"
DEFAULT_MODEL_ID                                : str  = "mistral"
DEFAULT_MODEL_FALLBACK                          : bool = False

DEFAULT_EMBEDDING_TYPE                          : str  = "ollama"
DEFAULT_EMBEDDING_ID                            : str  = "mistral"
DEFAULT_EMBEDDING_FALLBACK                      : bool = False

DEFAULT_CONTENT_DB_ENGINE                       : str  = "sqlite"
DEFAULT_CONTENT_DB_URL                          : str  = "storage/content"
DEFAULT_CONTENT_DB_FALLBACK                     : bool = False

DEFAULT_INDEX_DB_ENGINE                         : str  = "lancedb"
DEFAULT_INDEX_DB_URL                            : str  = "storage/index"
DEFAULT_INDEX_DB_SEARCH_TYPE                    : str  = "hybrid"
DEFAULT_INDEX_DB_FALLBACK                       : bool = False

DEFAULT_MEMORY_MANAGER_QUERY                    : bool = False
DEFAULT_MEMORY_MANAGER_UPDATE                   : bool = False
DEFAULT_MEMORY_MANAGER_MANAGED                  : bool = False
DEFAULT_MEMORY_MANAGER_CONTENT_DB_TABLE_NAME    : str  = "memory_manager_content_db_table"

DEFAULT_SESSION_MANAGER_QUERY                   : bool = False
DEFAULT_SESSION_MANAGER_UPDATE                  : bool = False
DEFAULT_SESSION_MANAGER_HISTORY_SIZE            : int  = 10
DEFAULT_SESSION_MANAGER_SUMMARIZE               : bool = False
DEFAULT_SESSION_MANAGER_CONTENT_DB_TABLE_NAME   : str  = "session_manager_content_db_table"

DEFAULT_KNOWLEDGE_MANAGER_QUERY                 : bool = True
DEFAULT_KNOWLEDGE_MANAGER_MAX_RESULTS           : int  = 10
DEFAULT_KNOWLEDGE_MANAGER_CONTENT_DB_TABLE_NAME : str  = "knowledge_manager_content_db_table"
DEFAULT_KNOWLEDGE_MANAGER_INDEX_DB_TABLE_NAME   : str  = "knowledge_manager_index_db_table"

DEFAULT_TOOL_FALLBACK                           : bool = False
DEFAULT_TOOL_MAX_WEB_SEARCH_RESULTS             : int  = 5

DEFAULT_AGENT_OPTIONS_MARKDOWN                  : bool = True
DEFAULT_AGENT_OPTIONS_USE_SESSION               : bool = False
DEFAULT_AGENT_OPTIONS_SESSION_HISTORY_SIZE      : int  = 10
DEFAULT_AGENT_OPTIONS_SUMMARIZE_SESSIONS        : bool = False
DEFAULT_AGENT_OPTIONS_USE_KNOWLEDGE             : bool = False


Index = int


class ConfigModel(BaseModel):
	data : Optional[Any] = None  # custom data


class MessageModel(ConfigModel):
	content_type : str
	content      : Optional[Any] = None


class InfoConfig(ConfigModel):
	version      : Optional[str      ] = None
	name         : Optional[str      ] = None
	author       : Optional[str      ] = None
	description  : Optional[str      ] = None
	instructions : Optional[List[str]] = None


class BackendConfig(ConfigModel):
	type     : str  = DEFAULT_BACKEND_TYPE      # backend name
	version  : str  = DEFAULT_BACKEND_VERSION   # backend version
	fallback : bool = DEFAULT_BACKEND_FALLBACK  # backend fallback


class ModelConfig(ConfigModel):
	type     : str  = DEFAULT_MODEL_TYPE      # model provider name
	id       : str  = DEFAULT_MODEL_ID        # model name (relative to llm)
	fallback : bool = DEFAULT_MODEL_FALLBACK  # model fallback


class EmbeddingConfig(ConfigModel):
	type     : str  = DEFAULT_EMBEDDING_TYPE      # embedding provider name
	id       : str  = DEFAULT_EMBEDDING_TYPE      # embedding name (relative to embedder)
	fallback : bool = DEFAULT_EMBEDDING_FALLBACK  # embedding fallback


class PromptConfig(ConfigModel):
	model        : Optional[Union[ModelConfig    , Index]] = None  # model to use for agentic knowledge processing
	embedding    : Optional[Union[EmbeddingConfig, Index]] = None  # embedding to use for agentic knowledge processing
	description  : Optional[str]                           = None
	instructions : Optional[List[str]]                     = None
	override     : Optional[str]                           = None  # override prompt template


class ContentDBConfig(ConfigModel):
	engine               : str  = DEFAULT_CONTENT_DB_ENGINE                        # db engine name (eg. sqlite)
	url                  : str  = DEFAULT_CONTENT_DB_URL                           # db url (eg. sqlite file path)
	memory_table_name    : str  = DEFAULT_MEMORY_MANAGER_CONTENT_DB_TABLE_NAME     # name of the table to store memory content
	session_table_name   : str  = DEFAULT_SESSION_MANAGER_CONTENT_DB_TABLE_NAME    # name of the table to store session content
	knowledge_table_name : str  = DEFAULT_KNOWLEDGE_MANAGER_CONTENT_DB_TABLE_NAME  # name of the table to store knowledge content
	fallback             : bool = DEFAULT_CONTENT_DB_FALLBACK                      # engine fallback


class IndexDBConfig(ConfigModel):
	engine      : str  = DEFAULT_INDEX_DB_ENGINE       # db engine name (eg. sqlite)
	embedding   : Union[EmbeddingConfig, Index]
	url         : str  = DEFAULT_INDEX_DB_URL          # db url (eg. sqlite file path)
	search_type : str  = DEFAULT_INDEX_DB_SEARCH_TYPE  # search type (eg. hybrid)
	fallback    : bool = DEFAULT_INDEX_DB_FALLBACK     # engine fallback


class MemoryManagerConfig(ConfigModel):
	query   : bool                                 = DEFAULT_MEMORY_MANAGER_QUERY
	update  : bool                                 = DEFAULT_MEMORY_MANAGER_UPDATE
	managed : bool                                 = DEFAULT_MEMORY_MANAGER_MANAGED
	prompt  : Optional[Union[PromptConfig, Index]] = None  # prompt for memory processing


class SessionManagerConfig(ConfigModel):
	query        : bool                                 = DEFAULT_SESSION_MANAGER_QUERY
	update       : bool                                 = DEFAULT_SESSION_MANAGER_UPDATE
	summarize    : bool                                 = DEFAULT_SESSION_MANAGER_SUMMARIZE
	history_size : int                                  = DEFAULT_SESSION_MANAGER_HISTORY_SIZE
	prompt       : Optional[Union[PromptConfig, Index]] = None  # prompt for session summarization


class KnowledgeManagerConfig(ConfigModel):
	query       : bool                                      = DEFAULT_KNOWLEDGE_MANAGER_QUERY
	description : Optional [str                           ] = None
	content_db  : Optional [Union [ContentDBConfig, Index]] = None  # where to store knowledge content
	index_db    : Union    [IndexDBConfig, Index          ] = None  # where to store knowledge index
	max_results : int                                       = DEFAULT_KNOWLEDGE_MANAGER_MAX_RESULTS
	urls        : Optional [List  [str                   ]] = None  # urls to fetch knowledge from


class ToolConfig(ConfigModel):
	type     : str
	args     : Optional[Dict[str, Any]] = None
	ref      : Optional[str           ] = None
	fallback : bool                     = DEFAULT_TOOL_FALLBACK


class AgentOptionsConfig(ConfigModel):
	markdown : bool = DEFAULT_AGENT_OPTIONS_MARKDOWN


class AgentConfig(ConfigModel):
	info          : Optional [InfoConfig                            ] = InfoConfig()
	options       : Optional [Union [AgentOptionsConfig    , Index ]] = AgentOptionsConfig()
	backend       : Union    [BackendConfig, Index                  ]
	prompt        : Union    [PromptConfig , Index                  ]
	content_db    : Optional [Union [ContentDBConfig       , Index ]] = None
	memory_mgr    : Optional [Union [MemoryManagerConfig   , Index ]] = None
	session_mgr   : Optional [Union [SessionManagerConfig  , Index ]] = None
	knowledge_mgr : Optional [Union [KnowledgeManagerConfig, Index ]] = None
	tools         : Optional [List  [Union[ToolConfig      , Index]]] = []
	port          : int                                               = 0


# class TeamOptionsConfig(ConfigModel):
# 	tag : int = 0


<<<<<<< HEAD
class TeamConfig(ConfigModel):
	info    : Optional[InfoConfig]                      = InfoConfig()
	options : Optional[Union[TeamOptionsConfig, Index]] = TeamOptionsConfig()
	agents  : List[Union[AgentConfig, Index]]           = []


# ========================================================================
# WORKFLOW SYSTEM
# ========================================================================

# ------------------------------------------------------------------------
# ENUMS
# ------------------------------------------------------------------------

class EventType(str, Enum):
	"""Core event types in the workflow system"""
	# Workflow lifecycle
	WORKFLOW_START = "workflow.start"
	WORKFLOW_END = "workflow.end"
	WORKFLOW_ERROR = "workflow.error"
	
	# Node execution
	NODE_START = "node.start"
	NODE_END = "node.end"
	NODE_ERROR = "node.error"
	NODE_SKIP = "node.skip"
	
	# Agent events
	AGENT_MESSAGE = "agent.message"
	AGENT_RESPONSE = "agent.response"
	AGENT_TOOL_CALL = "agent.tool_call"
	AGENT_TOOL_RESULT = "agent.tool_result"
	
	# User events
	USER_INPUT = "user.input"
	USER_APPROVAL = "user.approval"
	
	# Data events
	DATA_CHANGED = "data.changed"
	STATE_UPDATED = "state.updated"
	
	# Custom events
	CUSTOM = "custom"


class Event(BaseModel):
	"""Runtime event instance"""
	id: str
	type: EventType
	name: Optional[str] = None
	source_node_id: Optional[str] = None
	timestamp: float
	data: Dict[str, Any] = {}
	workflow_id: str
	execution_id: str

class NodeType(str, Enum):
	"""Types of nodes in workflow"""
	# Control flow
	START = "start"
	END = "end"
	DECISION = "decision"
	MERGE = "merge"
	PARALLEL = "parallel"
	LOOP = "loop"
	
	# AI operations
	AGENT = "agent"
	PROMPT = "prompt"
	EMBEDDING = "embedding"
	
	# Data operations
	TRANSFORM = "transform"
	EXTRACT = "extract"
	VALIDATE = "validate"
	
	# External operations
	API_CALL = "api_call"
	TOOL_CALL = "tool_call"
	WEBHOOK = "webhook"
	
	# User interaction
	USER_INPUT = "user_input"
	USER_APPROVAL = "user_approval"
	NOTIFICATION = "notification"
	
	# Storage
	SAVE = "save"
	LOAD = "load"
	QUERY = "query"


class EdgeType(str, Enum):
	"""Types of edges in workflow"""
	DEFAULT = "default"
	CONDITIONAL = "conditional"
	EVENT = "event"
	ERROR = "error"


class ExecutionStatus(str, Enum):
	"""Status of workflow/node execution"""
	PENDING = "pending"
	RUNNING = "running"
	WAITING_INPUT = "waiting_input"
	PAUSED = "paused"
	COMPLETED = "completed"
	FAILED = "failed"
	CANCELLED = "cancelled"


# ------------------------------------------------------------------------
# CONFIGURATION MODELS (Define workflow structure)
# ------------------------------------------------------------------------

class EventConfig(ConfigModel):
	"""Configuration for an event"""
	type: EventType
	name: Optional[str] = None
	data: Optional[Dict[str, Any]] = None
	filters: Optional[Dict[str, Any]] = None


class NodeConfig(ConfigModel):
	"""Configuration for a workflow node"""
	id: str
	type: NodeType
	name: str
	description: Optional[str] = None
	
	# Position in visual editor
	position: Dict[str, float] = {"x": 0, "y": 0}
	
	# Node-specific configuration
	config: Dict[str, Any] = {}
	
	# Input/output definitions
	inputs: Dict[str, Any] = {}
	outputs: Dict[str, Any] = {}
	
	# Events this node can emit
	emits: List[EventConfig] = []
	
	# Events this node listens to
	listens: List[EventConfig] = []
	
	# Error handling
	on_error: Optional[str] = None
	retry_config: Optional[Dict[str, Any]] = None


class EdgeConfig(ConfigModel):
	"""Configuration for workflow edge"""
	id: str
	source_node_id: str
	target_node_id: str
	type: EdgeType = EdgeType.DEFAULT
	
	# Condition for conditional edges
	condition: Optional[str] = None
	
	# Event trigger for event edges
	event_trigger: Optional[EventConfig] = None
	
	# Data transformation on edge
	transform: Optional[str] = None
	
	# Visual properties
	style: Dict[str, Any] = {}


class WorkflowState(ConfigModel):
	"""State structure for workflow execution"""
	variables: Dict[str, Any] = {}
	context: Dict[str, Any] = {}
	memory: List[Dict[str, Any]] = []
	outputs: Dict[str, Any] = {}


class WorkflowOptionsConfig(ConfigModel):
	"""Options for workflow execution"""
	max_iterations: int = 1000
	timeout_seconds: Optional[int] = None
	parallel_execution: bool = True


class WorkflowConfig(ConfigModel):
	"""Complete workflow definition"""
	id: str
	name: str
	description: Optional[str] = None
	version: str = "1.0.0"
	
	# Graph structure
	nodes: List[NodeConfig] = []
	edges: List[EdgeConfig] = []
	
	# Entry and exit points
	start_node_id: str
	end_node_ids: List[str] = []
	
	# Initial state
	initial_state: WorkflowState = WorkflowState()
	
	# Workflow-level configuration
	config: Dict[str, Any] = {}
	
	# References to app-level resources (by index)
	agents: List[int] = []
	tools: List[int] = []
	
	# Event handlers
	global_event_handlers: Dict[str, str] = {}
=======
# class TeamConfig(ConfigModel):
# 	info    : Optional[InfoConfig]                      = InfoConfig()
# 	options : Optional[Union[TeamOptionsConfig, Index]] = TeamOptionsConfig()
# 	agents  : List[Union[AgentConfig, Index]]           = []
>>>>>>> workflows


class AppOptionsConfig(ConfigModel):
	seed   : Optional[int] = DEFAULT_APP_OPTIONS_SEED
	reload : bool          = DEFAULT_APP_OPTIONS_RELOAD


class AppConfig(ConfigModel):
	info             : Optional[Union[InfoConfig      , Index]] = InfoConfig()
	options          : Optional[Union[AppOptionsConfig, Index]] = AppOptionsConfig()
	infos            : Optional[List[InfoConfig              ]] = []
	app_options      : Optional[List[AppOptionsConfig        ]] = []
	backends         : Optional[List[BackendConfig           ]] = []
	models           : Optional[List[ModelConfig             ]] = []
	embeddings       : Optional[List[EmbeddingConfig         ]] = []
	prompts          : Optional[List[PromptConfig            ]] = []
	content_dbs      : Optional[List[ContentDBConfig         ]] = []
	index_dbs        : Optional[List[IndexDBConfig           ]] = []
	memory_mgrs      : Optional[List[MemoryManagerConfig     ]] = []
	session_mgrs     : Optional[List[SessionManagerConfig    ]] = []
	knowledge_mgrs   : Optional[List[KnowledgeManagerConfig  ]] = []
	tools            : Optional[List[ToolConfig              ]] = []
	agent_options    : Optional[List[AgentOptionsConfig      ]] = []
	agents           : Optional[List[AgentConfig             ]] = []
	# team_options     : Optional[List[TeamOptionsConfig       ]] = []
	# teams            : Optional[List[TeamConfig              ]] = []
	# workflow_options : Optional[List[WorkflowOptionsConfig   ]] = []
	# workflows        : Optional[List[WorkflowConfig          ]] = []
	port             : int                                      = DEFAULT_APP_PORT
