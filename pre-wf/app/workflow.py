import asyncio
import time
import uuid


from   pydantic     import BaseModel
from   typing       import Any, Callable, Dict, List, Optional
from   collections  import defaultdict


from   schema       import (
	Event, EventType,
	NodeConfig, NodeType, EdgeConfig, EdgeType,
	WorkflowConfig, WorkflowState,
	ExecutionStatus
)


# ========================================================================
# EVENT BUS
# ========================================================================

class EventBus:
	"""Central event bus for workflow system"""
	
	def __init__(self):
		self.listeners: Dict[str, List[Callable]] = defaultdict(list)
		self.event_history: List[Event] = []
	
	def subscribe(self, event_type: str, handler: Callable) -> None:
		"""Subscribe to an event type"""
		self.listeners[event_type].append(handler)
	
	def unsubscribe(self, event_type: str, handler: Callable) -> None:
		"""Unsubscribe from an event type"""
		if handler in self.listeners[event_type]:
			self.listeners[event_type].remove(handler)
	
	async def emit(self, event: Event) -> None:
		"""Emit an event to all listeners"""
		self.event_history.append(event)
		
		# Notify listeners
		handlers = self.listeners.get(event.type.value, []) + self.listeners.get("*", [])
		
		for handler in handlers:
			try:
				if asyncio.iscoroutinefunction(handler):
					await handler(event)
				else:
					handler(event)
			except Exception as e:
				print(f"Error in event handler: {e}")
	
	def clear_history(self) -> None:
		"""Clear event history"""
		self.event_history = []


# ------------------------------------------------------------------------
# RUNTIME MODELS (Track execution state)
# ------------------------------------------------------------------------

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


class NodeExecutionRecord(BaseModel):
	"""Record of a single node execution"""
	node_id: str
	status: ExecutionStatus
	start_time: Optional[float] = None
	end_time: Optional[float] = None
	input_data: Dict[str, Any] = {}
	output_data: Dict[str, Any] = {}
	error: Optional[str] = None
	events_emitted: List[str] = []


class WorkflowExecutionState(BaseModel):
	"""Runtime state of workflow execution"""
	workflow_id: str
	execution_id: str
	status: ExecutionStatus
	
	# Execution graph
	current_node_ids: List[str] = []
	completed_node_ids: List[str] = []
	node_executions: Dict[str, NodeExecutionRecord] = {}
	
	# State and data
	state: WorkflowState = WorkflowState()
	
	# Event queue
	event_queue: List[Event] = []
	processed_events: List[str] = []
	
	# Timing
	start_time: Optional[float] = None
	end_time: Optional[float] = None
	
	# Error handling
	errors: List[Dict[str, Any]] = []


# ------------------------------------------------------------------------
# WORKFLOW REGISTRY (Optional - for storing workflow metadata)
# ------------------------------------------------------------------------

class WorkflowRegistryEntry(BaseModel):
	"""Entry in the workflow registry"""
	workflow: WorkflowConfig
	created_at: float
	updated_at: float
	tags: List[str] = []
	metadata: Dict[str, Any] = {}


# ========================================================================
# NODE EXECUTORS
# ========================================================================

class NodeExecutor:
	"""Base class for node executors"""
	
	def __init__(self, app_context: Any):
		self.app_context = app_context
	
	async def execute(
		self, 
		node: NodeConfig, 
		state: WorkflowState,
		event_bus: EventBus
	) -> Dict[str, Any]:
		"""Execute the node and return output data"""
		raise NotImplementedError()


class StartNodeExecutor(NodeExecutor):
	"""Executor for start nodes"""
	
	async def execute(self, node: NodeConfig, state: WorkflowState, event_bus: EventBus) -> Dict[str, Any]:
		# Start nodes just pass through initial state
		return {"status": "started"}


class EndNodeExecutor(NodeExecutor):
	"""Executor for end nodes"""
	
	async def execute(self, node: NodeConfig, state: WorkflowState, event_bus: EventBus) -> Dict[str, Any]:
		# End nodes collect final outputs
		return {"status": "completed", "outputs": state.outputs}


class AgentNodeExecutor(NodeExecutor):
	"""Executor for agent nodes"""
	
	async def execute(self, node: NodeConfig, state: WorkflowState, event_bus: EventBus) -> Dict[str, Any]:
		agent_config = node.config.get("agent", {})
		agent_ref = agent_config.get("agent_ref")
		
		# Validate agent reference
		if agent_ref is None:
			raise ValueError(f"Agent node {node.id} has no agent_ref configured")
		
		if not isinstance(agent_ref, int):
			raise ValueError(f"Agent node {node.id} has invalid agent_ref type: {type(agent_ref)}")
		
		# Get agent from app context
		agent = self.app_context.get_agent(agent_ref)
		if not agent:
			raise ValueError(f"Agent {agent_ref} not found in app context")
		
		# Map input from state
		input_mapping = agent_config.get("input_mapping", {})
		agent_input = self._map_data(state.variables, input_mapping)
		
		# Get message
		message = agent_input.get("message", "")
		
		# Execute agent
		response = await agent(message)
		
		# Emit events during execution
		await event_bus.emit(Event(
			id=str(uuid.uuid4()),
			type=EventType.AGENT_RESPONSE,
			source_node_id=node.id,
			timestamp=time.time(),
			data={"response": response},
			workflow_id=state.context.get("workflow_id", ""),
			execution_id=state.context.get("execution_id", "")
		))
		
		# Map output to state
		output_mapping = agent_config.get("output_mapping", {})
		return self._map_data({"response": response}, output_mapping)
	
	def _map_data(self, source: Dict[str, Any], mapping: Dict[str, str]) -> Dict[str, Any]:
		"""Map data using mapping dictionary"""
		result = {}
		for target_key, source_path in mapping.items():
			# Simple path resolution (can be extended with JSONPath)
			value = source.get(source_path, None)
			result[target_key] = value
		return result


class DecisionNodeExecutor(NodeExecutor):
	"""Executor for decision nodes"""
	
	async def execute(self, node: NodeConfig, state: WorkflowState, event_bus: EventBus) -> Dict[str, Any]:
		decision_config = node.config.get("decision", {})
		conditions = decision_config.get("conditions", [])
		
		for condition in conditions:
			condition_expr = condition.get("condition")
			target_node = condition.get("target_node")
			
			# Evaluate condition (simplified - use safer evaluation in production)
			try:
				result = eval(condition_expr, {"state": state.variables})
				if result:
					return {
						"decision": target_node,
						"matched_condition": condition_expr
					}
			except Exception as e:
				print(f"Error evaluating condition: {e}")
		
		# Default path
		default_node = decision_config.get("default_node")
		return {"decision": default_node, "matched_condition": "default"}


class TransformNodeExecutor(NodeExecutor):
	"""Executor for data transformation nodes"""
	
	async def execute(self, node: NodeConfig, state: WorkflowState, event_bus: EventBus) -> Dict[str, Any]:
		transform_config = node.config.get("transform", {})
		transform_expr = transform_config.get("expression", "")
		
		# Execute transformation (simplified - use safer evaluation)
		try:
			result = eval(transform_expr, {"state": state.variables})
			return {"transformed": result}
		except Exception as e:
			raise ValueError(f"Transform error: {e}")


class ToolCallNodeExecutor(NodeExecutor):
	"""Executor for tool call nodes"""
	
	async def execute(self, node: NodeConfig, state: WorkflowState, event_bus: EventBus) -> Dict[str, Any]:
		tool_config = node.config.get("tool", {})
		tool_ref = tool_config.get("tool_ref")
		
		# Get tool from app context
		tool = self.app_context.get_tool(tool_ref)
		if not tool:
			raise ValueError(f"Tool {tool_ref} not found")
		
		# Prepare arguments
		args = tool_config.get("args", {})
		resolved_args = self._resolve_args(args, state.variables)
		
		# Execute tool
		result = await tool(**resolved_args)
		
		return {"result": result}
	
	def _resolve_args(self, args: Dict[str, Any], state_vars: Dict[str, Any]) -> Dict[str, Any]:
		"""Resolve arguments from state"""
		resolved = {}
		for key, value in args.items():
			if isinstance(value, str) and value.startswith("$"):
				# Reference to state variable
				var_name = value[1:]
				resolved[key] = state_vars.get(var_name)
			else:
				resolved[key] = value
		return resolved


# ========================================================================
# WORKFLOW EXECUTOR
# ========================================================================

class WorkflowExecutor:
	"""Main workflow execution engine"""
	
	def __init__(self, app_context: Any):
		self.app_context = app_context
		self.event_bus = EventBus()
		
		# Register node executors
		self.node_executors: Dict[NodeType, NodeExecutor] = {
			NodeType.START: StartNodeExecutor(app_context),
			NodeType.END: EndNodeExecutor(app_context),
			NodeType.AGENT: AgentNodeExecutor(app_context),
			NodeType.DECISION: DecisionNodeExecutor(app_context),
			NodeType.TRANSFORM: TransformNodeExecutor(app_context),
			NodeType.TOOL_CALL: ToolCallNodeExecutor(app_context),
		}
		
		# Active executions
		self.executions: Dict[str, WorkflowExecutionState] = {}
	
	def subscribe_to_events(self, event_type: str, handler: Callable) -> None:
		"""Subscribe to workflow events"""
		self.event_bus.subscribe(event_type, handler)
	
	async def execute_workflow(
		self, 
		workflow: WorkflowConfig,
		initial_input: Dict[str, Any] = None
	) -> WorkflowExecutionState:
		"""Execute a workflow and return execution state"""
		
		# Create execution state
		execution_id = str(uuid.uuid4())
		execution = WorkflowExecutionState(
			workflow_id=workflow.id,
			execution_id=execution_id,
			status=ExecutionStatus.RUNNING,
			start_time=time.time(),
			state=workflow.initial_state.copy() if workflow.initial_state else WorkflowState()
		)
		
		# Add initial input to state
		if initial_input:
			execution.state.variables.update(initial_input)
		
		execution.state.context["workflow_id"] = workflow.id
		execution.state.context["execution_id"] = execution_id
		
		self.executions[execution_id] = execution
		
		# Emit workflow start event
		await self.event_bus.emit(Event(
			id=str(uuid.uuid4()),
			type=EventType.WORKFLOW_START,
			timestamp=time.time(),
			data={"workflow_id": workflow.id},
			workflow_id=workflow.id,
			execution_id=execution_id
		))
		
		try:
			# Start execution from start node
			execution.current_node_ids = [workflow.start_node_id]
			
			# Execute workflow
			await self._execute_nodes(workflow, execution)
			
			# Mark as completed
			execution.status = ExecutionStatus.COMPLETED
			execution.end_time = time.time()
			
		except Exception as e:
			execution.status = ExecutionStatus.FAILED
			execution.end_time = time.time()
			execution.errors.append({
				"error": str(e),
				"timestamp": time.time()
			})
			
			# Emit error event
			await self.event_bus.emit(Event(
				id=str(uuid.uuid4()),
				type=EventType.WORKFLOW_ERROR,
				timestamp=time.time(),
				data={"error": str(e)},
				workflow_id=workflow.id,
				execution_id=execution_id
			))
		
		# Emit workflow end event
		await self.event_bus.emit(Event(
			id=str(uuid.uuid4()),
			type=EventType.WORKFLOW_END,
			timestamp=time.time(),
			data={"status": execution.status.value},
			workflow_id=workflow.id,
			execution_id=execution_id
		))
		
		return execution
	
	async def _execute_nodes(
		self, 
		workflow: WorkflowConfig, 
		execution: WorkflowExecutionState
	) -> None:
		"""Execute nodes in the workflow"""
		
		nodes_by_id = {node.id: node for node in workflow.nodes}
		max_iterations = 1000  # Prevent infinite loops
		iteration = 0
		
		while execution.current_node_ids and iteration < max_iterations:
			iteration += 1
			
			# Get current nodes to execute
			current_ids = execution.current_node_ids.copy()
			execution.current_node_ids = []
			
			# Execute nodes (supports parallel execution)
			tasks = []
			for node_id in current_ids:
				node = nodes_by_id.get(node_id)
				if not node:
					continue
				
				tasks.append(self._execute_node(node, workflow, execution))
			
			# Wait for all parallel executions
			results = await asyncio.gather(*tasks, return_exceptions=True)
			
			# Handle results and determine next nodes
			for i, result in enumerate(results):
				if isinstance(result, Exception):
					raise result
				
				node_id = current_ids[i]
				node = nodes_by_id[node_id]
				
				# Get next nodes based on edges
				next_nodes = self._get_next_nodes(node, workflow, execution, result)
				execution.current_node_ids.extend(next_nodes)
			
			# Remove duplicates
			execution.current_node_ids = list(set(execution.current_node_ids))
	
	async def _execute_node(
		self, 
		node: NodeConfig, 
		workflow: WorkflowConfig,
		execution: WorkflowExecutionState
	) -> Dict[str, Any]:
		"""Execute a single node"""
		
		# Create execution record
		record = NodeExecutionRecord(
			node_id=node.id,
			status=ExecutionStatus.RUNNING,
			start_time=time.time()
		)
		execution.node_executions[node.id] = record
		
		# Emit node start event
		await self.event_bus.emit(Event(
			id=str(uuid.uuid4()),
			type=EventType.NODE_START,
			source_node_id=node.id,
			timestamp=time.time(),
			data={"node_id": node.id, "node_type": node.type.value},
			workflow_id=workflow.id,
			execution_id=execution.execution_id
		))
		
		try:
			# Get executor for node type
			executor = self.node_executors.get(node.type)
			if not executor:
				raise ValueError(f"No executor for node type {node.type}")
			
			# Execute node
			output_data = await executor.execute(node, execution.state, self.event_bus)
			
			# Update state with output
			if output_data:
				execution.state.variables.update(output_data)
			
			# Update record
			record.status = ExecutionStatus.COMPLETED
			record.end_time = time.time()
			record.output_data = output_data
			
			execution.completed_node_ids.append(node.id)
			
			# Emit node end event
			await self.event_bus.emit(Event(
				id=str(uuid.uuid4()),
				type=EventType.NODE_END,
				source_node_id=node.id,
				timestamp=time.time(),
				data={"node_id": node.id, "output": output_data},
				workflow_id=workflow.id,
				execution_id=execution.execution_id
			))
			
			return output_data
			
		except Exception as e:
			record.status = ExecutionStatus.FAILED
			record.end_time = time.time()
			record.error = str(e)
			
			# Emit node error event
			await self.event_bus.emit(Event(
				id=str(uuid.uuid4()),
				type=EventType.NODE_ERROR,
				source_node_id=node.id,
				timestamp=time.time(),
				data={"node_id": node.id, "error": str(e)},
				workflow_id=workflow.id,
				execution_id=execution.execution_id
			))
			
			raise
	
	def _get_next_nodes(
		self, 
		node: NodeConfig, 
		workflow: WorkflowConfig,
		execution: WorkflowExecutionState,
		node_output: Dict[str, Any]
	) -> List[str]:
		"""Determine next nodes to execute based on edges"""
		
		next_nodes = []
		
		# Check if node is an end node
		if node.id in workflow.end_node_ids:
			return []
		
		# Find outgoing edges
		for edge in workflow.edges:
			if edge.source_node_id != node.id:
				continue
			
			# Check edge conditions
			if edge.type == EdgeType.CONDITIONAL:
				if not self._evaluate_edge_condition(edge, execution.state, node_output):
					continue
			
			# Check event triggers
			if edge.type == EdgeType.EVENT:
				# Event edges are handled separately
				continue
			
			next_nodes.append(edge.target_node_id)
		
		return next_nodes
	
	def _evaluate_edge_condition(
		self, 
		edge: EdgeConfig, 
		state: WorkflowState,
		node_output: Dict[str, Any]
	) -> bool:
		"""Evaluate edge condition"""
		if not edge.condition:
			return True
		
		try:
			# Simplified evaluation (use safer method in production)
			result = eval(edge.condition, {
				"state": state.variables,
				"output": node_output
			})
			return bool(result)
		except Exception as e:
			print(f"Error evaluating edge condition: {e}")
			return False
