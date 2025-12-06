# workflow_engine

import asyncio
import uuid


from   collections     import defaultdict
from   datetime        import datetime
from   functools       import partial
from   pydantic        import BaseModel
from   typing          import Any, Callable, Dict, List, Optional, Set, Tuple

from   core            import AgentApp
from   event_bus       import EventBus, EventType, get_event_bus
from   workflow_nodes  import create_node, NodeExecutionContext, NodeExecutionResult
from   workflow_schema import WorkflowConfig, WorkflowNodeStatus


class WorkflowExecutionState(BaseModel):
	"""State of a workflow execution"""
	workflow_id: str
	execution_id: str
	status: WorkflowNodeStatus
	pending_nodes: List[int] = []
	ready_nodes: List[int] = []
	running_nodes: List[int] = []
	completed_nodes: List[int] = []
	failed_nodes: List[int] = []
	node_outputs: Dict[int, Dict[str, Any]] = {}
	start_time: Optional[str] = None
	end_time: Optional[str] = None
	error: Optional[str] = None


class WorkflowContext:
	"""Context providing access to app resources"""

	def __init__(self, apps: List[AgentApp], agent_remap: Dict[int, Tuple[int, int]], tool_remap: Dict[int, Tuple[int, int]]):
		async def run_agent(app: AgentApp, agent_index, *args, **kwargs) -> Any:
			result = await app.run_agent(agent_index, *args, **kwargs)
			return result

		self._agents = {
			global_idx: partial(run_agent, apps[app_idx], local_idx)
			for global_idx, (app_idx, local_idx) in agent_remap.items()
		}

		async def run_tool(app: AgentApp, tool_index, *args, **kwargs) -> Any:
			result = await app.run_tool(tool_index, *args, **kwargs)
			return result

		self._tools = {
			global_idx: partial(run_tool, apps[app_idx], local_idx)
			for global_idx, (app_idx, local_idx) in tool_remap.items()
		}


	def get_agent(self, ref: int) -> Callable:
		"""Get agent by reference"""
		agent = self._agents.get(ref)
		if agent is None:
			raise ValueError(f"Agent at index {ref} is None")
		return agent


	def get_tool(self, ref: int) -> Callable:
		"""Get tool by reference"""
		tool = self._tools.get(ref)
		if tool is None:
			raise ValueError(f"Tool at index {ref} is None")
		return tool


class WorkflowEngine:
	"""Simplified frontier-based workflow execution engine"""
	
	def __init__(self, context: WorkflowContext, event_bus: Optional[EventBus] = None):
		self.context   = context
		self.event_bus = event_bus or get_event_bus()
		self.executions: Dict[str, WorkflowExecutionState] = {}
		self.execution_tasks: Dict[str, asyncio.Task] = {}
		
		# User input handling
		self.pending_user_inputs: Dict[str, asyncio.Future] = {}
		
	async def start_workflow(self, workflow: WorkflowConfig, 
							initial_data: Optional[Dict[str, Any]] = None) -> str:
		"""Start a new workflow execution"""
		execution_id = str(uuid.uuid4())
		workflow_id = workflow.info.name if workflow.info else "workflow"
		
		# Initialize execution state
		state = WorkflowExecutionState(
			workflow_id=workflow_id,
			execution_id=execution_id,
			status=WorkflowNodeStatus.RUNNING,
			start_time=datetime.now().isoformat()
		)
		
		self.executions[execution_id] = state
		
		# Emit started event
		await self.event_bus.emit(
			event_type=EventType.WORKFLOW_STARTED,
			workflow_id=workflow_id,
			execution_id=execution_id,
			data={"initial_data": initial_data}
		)
		
		# Start execution task
		task = asyncio.create_task(
			self._execute_workflow(workflow, state, initial_data or {})
		)
		self.execution_tasks[execution_id] = task
		
		return execution_id
	
	async def _execute_workflow(self, workflow: WorkflowConfig, 
								state: WorkflowExecutionState,
								initial_data: Dict[str, Any]):
		"""Main execution loop - frontier-based"""
		try:
			# Build dependency graph
			dependencies = self._build_dependencies(workflow)
			dependents = self._build_dependents(workflow)
			
			# Initialize frontier
			pending = set(range(len(workflow.nodes)))
			ready = set()
			running = set()
			completed = set()
			
			# Node outputs storage
			node_outputs: Dict[int, Dict[str, Any]] = {}
			
			# Find start nodes (no dependencies)
			for idx in range(len(workflow.nodes)):
				if not dependencies[idx]:
					ready.add(idx)
					pending.discard(idx)
			
			# Instantiate nodes
			node_instances = self._instantiate_nodes(workflow)
			
			# Global variables
			variables = workflow.variables or {}
			variables.update(initial_data)
			
			# Main execution loop
			while ready or running:
				await asyncio.sleep(1)  # Yield control

				# Update state
				state.pending_nodes = list(pending)
				state.ready_nodes = list(ready)
				state.running_nodes = list(running)
				state.completed_nodes = list(completed)
				state.node_outputs = node_outputs
				
				# Execute ready nodes
				if ready:
					tasks = []
					for node_idx in list(ready):
						ready.discard(node_idx)
						running.add(node_idx)
						
						task = asyncio.create_task(self._execute_node(
							workflow, node_idx, node_instances[node_idx],
							node_outputs, dependencies, variables, state
						))
						tasks.append(task)
					
					# Wait for at least one completion
					done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
					
					# Process completed nodes
					for task in done:
						node_idx, result = await task
						
						running.discard(node_idx)
						
						if result.success:
							completed.add(node_idx)
							node_outputs[node_idx] = result.outputs
							
							# Check which dependent nodes are now ready
							for dep_idx in dependents[node_idx]:
								if dep_idx not in completed and dep_idx not in running:
									# Check if all dependencies completed
									if dependencies[dep_idx].issubset(completed):
										pending.discard(dep_idx)
										ready.add(dep_idx)
						else:
							# Node failed
							state.failed_nodes.append(node_idx)
							await self.event_bus.emit(
								event_type=EventType.NODE_FAILED,
								workflow_id=state.workflow_id,
								execution_id=state.execution_id,
								node_id=str(node_idx),
								error=result.error
							)
				else:
					# Wait for running nodes
					await asyncio.sleep(0.1)
			
			# Workflow complete
			state.status = WorkflowNodeStatus.COMPLETED
			state.end_time = datetime.now().isoformat()
			
			await self.event_bus.emit(
				event_type=EventType.WORKFLOW_COMPLETED,
				workflow_id=state.workflow_id,
				execution_id=state.execution_id,
				data={"outputs": node_outputs}
			)
			
		except Exception as e:
			state.status = WorkflowNodeStatus.FAILED
			state.error = str(e)
			state.end_time = datetime.now().isoformat()
			
			await self.event_bus.emit(
				event_type=EventType.WORKFLOW_FAILED,
				workflow_id=state.workflow_id,
				execution_id=state.execution_id,
				error=str(e)
			)
	
	def _build_dependencies(self, workflow: WorkflowConfig) -> Dict[int, Set[int]]:
		"""Build dependency graph: target -> set of sources"""
		deps = defaultdict(set)
		for edge in workflow.edges:
			deps[edge.target].add(edge.source)
		return deps
	
	def _build_dependents(self, workflow: WorkflowConfig) -> Dict[int, Set[int]]:
		"""Build dependent graph: source -> set of targets"""
		deps = defaultdict(set)
		for edge in workflow.edges:
			deps[edge.source].add(edge.target)
		return deps
	
	def _instantiate_nodes(self, workflow: WorkflowConfig) -> List[Any]:
		"""Create node instances"""
		nodes = []
		for node_config in workflow.nodes:
			config = node_config.config or {}
			
			# Add node-specific resources
			kwargs = {}
			if node_config.type == "agent" and config.get('agent') is not None:
				agent_idx = config.get('agent')
				kwargs['agent'] = self.context.get_agent(agent_idx)
			
			elif node_config.type == "tool" and config.get('tool') is not None:
				tool_idx = config.get('tool')
				kwargs['tool'] = self.context.get_tool(tool_idx)
			
			node = create_node(node_config.type, config, **kwargs)
			nodes.append(node)
		
		return nodes
	
	async def _execute_node(self, workflow: WorkflowConfig, node_idx: int, 
						   node: Any, node_outputs: Dict[int, Dict[str, Any]],
						   dependencies: Dict[int, Set[int]],
						   variables: Dict[str, Any],
						   state: WorkflowExecutionState):
		"""Execute a single node"""
		node_config = workflow.nodes[node_idx]
		
		await self.event_bus.emit(
			event_type=EventType.NODE_STARTED,
			workflow_id=state.workflow_id,
			execution_id=state.execution_id,
			node_id=str(node_idx),
			data={"node_type": node_config.type, "node_label": node_config.label}
		)
		
		try:
			# Gather inputs from dependencies
			context = NodeExecutionContext()
			context.inputs = self._gather_inputs(
				workflow, node_idx, node_outputs, dependencies
			)
			context.variables = variables
			context.node_index = node_idx
			
			# Handle user input nodes specially
			if node_config.type == "user_input":
				result = await self._handle_user_input(node_idx, node, context, state)
			else:
				# Execute node
				result = await node.execute(context)
			
			if result.success:
				await self.event_bus.emit(
					event_type=EventType.NODE_COMPLETED,
					workflow_id=state.workflow_id,
					execution_id=state.execution_id,
					node_id=str(node_idx),
					data={"outputs": result.outputs}
				)
			
			return node_idx, result
			
		except Exception as e:
			result = NodeExecutionResult()
			result.success = False
			result.error = str(e)
			return node_idx, result
	
	def _gather_inputs(self, workflow: WorkflowConfig, node_idx: int,
					  node_outputs: Dict[int, Dict[str, Any]],
					  dependencies: Dict[int, Set[int]]) -> Dict[str, Any]:
		"""Gather input data from connected edges"""
		inputs = {}
		
		for edge in workflow.edges:
			if edge.target == node_idx:
				source_idx = edge.source
				
				if source_idx in node_outputs:
					source_data = node_outputs[source_idx]
					data = source_data.get(edge.source_slot, None)
					
					# Apply filter if present
					if edge.filter:
						try:
							if not self._evaluate_filter(edge.filter, data):
								continue  # Skip this edge
						except:
							continue
					
					# Store in target slot
					inputs[edge.target_slot] = data
		
		return inputs
	
	def _evaluate_filter(self, filter_expr: str, data: Any) -> bool:
		"""Evaluate edge filter expression"""
		try:
			return eval(filter_expr, {"data": data})
		except:
			return True  # Default to passing data through
	
	async def _handle_user_input(self, node_idx: int, node: Any,
								 context: NodeExecutionContext,
								 state: WorkflowExecutionState) -> NodeExecutionResult:
		"""Handle user input node"""
		config = node.config
		prompt = config.get('prompt', 'Please provide input:')
		
		# Create future for user input
		future = asyncio.Future()
		input_key = f"{state.execution_id}:{node_idx}"
		self.pending_user_inputs[input_key] = future
		
		# Emit event requesting input
		await self.event_bus.emit(
			event_type=EventType.USER_INPUT_REQUESTED,
			workflow_id=state.workflow_id,
			execution_id=state.execution_id,
			node_id=str(node_idx),
			data={"prompt": prompt}
		)
		
		# Wait for input
		try:
			timeout = config.get('timeout', 300)
			user_input = await asyncio.wait_for(future, timeout=timeout)
			
			result = NodeExecutionResult()
			result.outputs = {"output": user_input}
			return result
			
		except asyncio.TimeoutError:
			result = NodeExecutionResult()
			result.success = False
			result.error = f"User input timeout after {timeout}s"
			return result
	
	async def provide_user_input(self, execution_id: str, node_id: str, user_input: Any):
		"""Provide user input for waiting node"""
		input_key = f"{execution_id}:{node_id}"
		
		if input_key in self.pending_user_inputs:
			future = self.pending_user_inputs.pop(input_key)
			future.set_result(user_input)
			
			await self.event_bus.emit(
				event_type=EventType.USER_INPUT_RECEIVED,
				workflow_id=self.executions[execution_id].workflow_id,
				execution_id=execution_id,
				node_id=node_id,
				data={"input": user_input}
			)
	
	async def cancel_execution(self, execution_id: str):
		"""Cancel a running workflow"""
		if execution_id in self.execution_tasks:
			task = self.execution_tasks[execution_id]
			task.cancel()
			
			state = self.executions.get(execution_id)
			if state:
				state.status = WorkflowNodeStatus.FAILED
				state.error = "Cancelled by user"
				state.end_time = datetime.now().isoformat()
				
				await self.event_bus.emit(
					event_type=EventType.WORKFLOW_CANCELLED,
					workflow_id=state.workflow_id,
					execution_id=execution_id
				)
	
	def get_execution_state(self, execution_id: str) -> Optional[WorkflowExecutionState]:
		"""Get current execution state"""
		return self.executions.get(execution_id)
	
	def list_executions(self) -> List[WorkflowExecutionState]:
		"""List all executions"""
		return list(self.executions.values())
