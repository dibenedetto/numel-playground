# workflow_schema

from enum     import Enum
from pydantic import BaseModel, field_validator
from typing   import Any, Dict, List, Optional


from schema   import InfoConfig


class WorkflowNodeType(str, Enum):
	"""Simplified node types"""
	START = "start"
	END = "end"
	AGENT = "agent"
	PROMPT = "prompt"
	TOOL = "tool"
	TRANSFORM = "transform"
	DECISION = "decision"
	MERGE = "merge"
	USER_INPUT = "user_input"


class WorkflowNodeStatus(str, Enum):
	PENDING = "pending"
	READY = "ready"
	RUNNING = "running"
	COMPLETED = "completed"
	FAILED = "failed"
	SKIPPED = "skipped"


class WorkflowNodeConfig(BaseModel):
	"""Base node configuration"""
	id: str
	type: WorkflowNodeType
	label: Optional[str] = None
	position: Optional[Dict[str, float]] = None
	
	# Node-specific config stored as dict
	config: Optional[Dict[str, Any]] = None


class WorkflowEdgeConfig(BaseModel):
	"""Edge connects nodes and carries data"""
	source: int  # Source node index
	target: int  # Target node index
	source_slot: str = "output"  # Output slot name
	target_slot: str = "input"   # Input slot name
	label: Optional[str] = None
	
	# Optional: filter data flowing through this edge
	filter: Optional[str] = None  # Python expression, e.g., "data.get('matched') == True"


class WorkflowConfig(BaseModel):
	"""Complete workflow definition"""
	info: InfoConfig = InfoConfig()
	nodes: List[WorkflowNodeConfig] = []
	edges: List[WorkflowEdgeConfig] = []
	variables: Optional[Dict[str, Any]] = None
	
	@field_validator('edges')
	def validate_edges(cls, edges, info):
		"""Validate edge indices"""
		if 'nodes' in info.data:
			node_count = len(info.data['nodes'])
			for edge in edges:
				if edge.source < 0 or edge.source >= node_count:
					raise ValueError(f"Invalid edge source: {edge.source}")
				if edge.target < 0 or edge.target >= node_count:
					raise ValueError(f"Invalid edge target: {edge.target}")
		return edges
