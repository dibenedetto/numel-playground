# workflow_engine.py
# Updated for workflow_schema_new.py

import asyncio
import uuid

from collections import defaultdict
from datetime import datetime
from enum import Enum
from functools import partial
from pydantic import BaseModel
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from core import AgentApp
from event_bus import EventBus, EventType, get_event_bus
from workflow_nodes import create_node, NodeExecutionContext, NodeExecutionResult
from workflow_schema_new import BaseNode, Workflow


class WorkflowNodeStatus(str, Enum):
	"""Status of a workflow node during execution"""
	PENDING = "pending"
	READY = "ready"
	RUNNING = "running"
	COMPLETED = "completed"
	FAILED = "failed"
	SKIPPED = "skipped"
	WAITING = "waiting"


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
	"""Frontier-based workflow execution engine"""
	
	def __init__(self, context: WorkflowContext, event_bus: Optional[EventBus] = None):
		self.context = context
		self.event_bus = event_bus or get_event_bus()
		self.executions: Dict[str, WorkflowExecutionState] = {}
		self.execution_tasks: Dict[str, asyncio.Task] = {}
		self.pending_user_inputs: Dict[str, asyncio.Future] = {}
		
	async def start_workflow(self, workflow: Workflow, 
							initial_data: Optional[Dict[str, Any]] = None) -> str:
		"""Start a new workflow execution"""
		execution_id = str(uuid.uuid4())
		workflow_id = workflow.info.name if workflow.info else "workflow"
		
		state = WorkflowExecutionState(
			workflow_id=workflow_id,
			execution_id=execution_id,
			status=WorkflowNodeStatus.RUNNING,
			start_time=datetime.now().isoformat()
		)
		
		self.executions[execution_id] = state
		
		await self.event_bus.emit(
			event_type=EventType.WORKFLOW_STARTED,
			workflow_id=workflow_id,
			execution_id=execution_id,
			data={"initial_data": initial_data}
		)
		
		task = asyncio.create_task(
			self._execute_workflow(workflow, state, initial_data or {})
		)
		self.execution_tasks[execution_id] = task
		
		return execution_id
	
	async def _execute_workflow(self, workflow: Workflow, 
							state: WorkflowExecutionState,
							initial_data: Dict[str, Any]):
		"""Main execution loop - frontier-based"""
		try:
			all_nodes = workflow.nodes or []
			nodes     = list(filter(lambda n: isinstance(n, BaseNode), all_nodes))
			all_edges = workflow.edges or []
			edges     = [e for e in all_edges if isinstance(all_nodes[e.source], BaseNode) and isinstance(all_nodes[e.target], BaseNode)]
			
			# Build dependency graph from edges
			dependencies = self._build_dependencies (edges)
			dependents   = self._build_dependents   (edges)
			
			# Track node states
			# pending = set(range(len(nodes)))
			pending = set(nodes)
			ready = set()
			running = set()
			completed = set()
			
			# Node outputs storage
			node_outputs: Dict[int, Dict[str, Any]] = {}
			
			# Find start nodes (no dependencies)
			for idx in range(len(nodes)):
				if not dependencies[idx]:
					ready.add(idx)
					pending.discard(idx)
			
			# Instantiate node executors
			node_instances = self._instantiate_nodes(nodes)
			
			# Global variables
			variables = dict(initial_data)
			
			# Main execution loop
			while ready or running:
				await asyncio.sleep(0.01)

				state.pending_nodes = list(pending)
				state.ready_nodes = list(ready)
				state.running_nodes = list(running)
				state.completed_nodes = list(completed)
				state.node_outputs = node_outputs
				
				if ready:
					tasks = []
					
					for node_idx in list(ready):
						ready.discard(node_idx)
						running.add(node_idx)
						
						task = asyncio.create_task(self._execute_node(
							nodes, all_edges, node_idx, node_instances[node_idx],
							node_outputs, dependencies, variables, state
						))
						tasks.append(task)
					
					if tasks:
						done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
						
						for task in done:
							node_idx, result = await task
							running.discard(node_idx)
							
							if result.success:
								completed.add(node_idx)
								node_outputs[node_idx] = result.outputs
								
								for dep_idx in dependents[node_idx]:
									if dep_idx not in completed and dep_idx not in running:
										if dependencies[dep_idx].issubset(completed):
											pending.discard(dep_idx)
											ready.add(dep_idx)
							else:
								state.failed_nodes.append(node_idx)
								await self.event_bus.emit(
									event_type=EventType.NODE_FAILED,
									workflow_id=state.workflow_id,
									execution_id=state.execution_id,
									node_id=str(node_idx),
									error=result.error
								)
				else:
					await asyncio.sleep(0.1)
			
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
	
	def _build_dependencies(self, edges: List) -> Dict[int, Set[int]]:
		"""Build dependency graph: target -> set of sources"""
		deps = defaultdict(set)
		for edge in edges:
			# Handle both dict and Pydantic model
			if hasattr(edge, 'target'):
				deps[edge.target].add(edge.source)
			elif isinstance(edge, dict):
				deps[edge['target']].add(edge['source'])
		return deps
	
	def _build_dependents(self, edges: List) -> Dict[int, Set[int]]:
		"""Build dependent graph: source -> set of targets"""
		deps = defaultdict(set)
		for edge in edges:
			if hasattr(edge, 'source'):
				deps[edge.source].add(edge.target)
			elif isinstance(edge, dict):
				deps[edge['source']].add(edge['target'])
		return deps
	
	def _instantiate_nodes(self, nodes: List) -> List[Any]:
		"""Create node instances from workflow definition"""
		instances = []
		
		for idx, node in enumerate(nodes):
			# Handle both dict and Pydantic model
			if hasattr(node, 'model_dump'):
				node_config = node.model_dump()
			elif hasattr(node, 'dict'):
				node_config = node.dict()
			elif isinstance(node, dict):
				node_config = node
			else:
				node_config = {}

			node_type = node_config.get("type", "base_node")
			kwargs    = {}

			# Inject tool for tool_node
			if node_type == "tool_node":
				config_field = node_config.get("config")
				if config_field:
					ref = None
					if isinstance(config_field, dict):
						ref = config_field.get("value", {}).get("ref") if isinstance(config_field.get("value"), dict) else None
					else:
						ref = None
					if ref is not None:
						try:
							kwargs["tool"] = self.context.get_tool(int(ref))
						except:
							pass
			
			# Inject agent for agent_node
			elif node_type == "agent_node":
				config_field = node_config.get("config")
				if config_field:
					ref = None
					if isinstance(config_field, dict):
						ref = config_field.get("value", {}).get("ref") if isinstance(config_field.get("value"), dict) else None
					if ref is not None:
						try:
							kwargs["agent"] = self.context.get_agent(int(ref))
						except:
							pass

			instance = create_node(node_type, node_config, **kwargs)
			instances.append(instance)
		
		return instances
	
	async def _execute_node(self, nodes: List, edges: List, node_idx: int, 
						node: Any, node_outputs: Dict[int, Dict[str, Any]],
						dependencies: Dict[int, Set[int]],
						variables: Dict[str, Any],
						state: WorkflowExecutionState):
		"""Execute a single node"""
		node_data = nodes[node_idx]
		
		if hasattr(node_data, 'model_dump'):
			node_config = node_data.model_dump()
		elif hasattr(node_data, 'dict'):
			node_config = node_data.dict()
		elif isinstance(node_data, dict):
			node_config = node_data
		else:
			node_config = {}
		
		node_type = node_config.get("type", "unknown")
		extra = node_config.get("extra")
		
		# Parse extra if it's a string
		if isinstance(extra, str):
			import json
			try:
				extra = json.loads(extra)
			except:
				extra = {}
		
		node_label = extra.get("name") if isinstance(extra, dict) else None
		node_label = node_label or node_type
		
		await self.event_bus.emit(
			event_type=EventType.NODE_STARTED,
			workflow_id=state.workflow_id,
			execution_id=state.execution_id,
			node_id=str(node_idx),
			data={"node_type": node_type, "node_label": node_label}
		)

		await asyncio.sleep(1)

		try:
			context = NodeExecutionContext()
			context.inputs = self._gather_inputs(edges, node_idx, node_outputs)
			context.variables = variables
			context.node_index = node_idx
			context.node_config = node_config
			
			if node_type == "user_input_node":
				result = await self._handle_user_input(node_idx, node, context, state)
			else:
				result = await node.execute(context)
			
			if result.success:
				await self.event_bus.emit(
					event_type=EventType.NODE_COMPLETED,
					workflow_id=state.workflow_id,
					execution_id=state.execution_id,
					node_id=str(node_idx),
					data={"outputs": result.outputs, "node_label": node_label}
				)
			
			return node_idx, result
			
		except Exception as e:
			result = NodeExecutionResult()
			result.success = False
			result.error = str(e)
			return node_idx, result
	
	def _gather_inputs(self, edges: List, node_idx: int,
					node_outputs: Dict[int, Dict[str, Any]]) -> Dict[str, Any]:
		"""Gather input data from connected edges"""
		inputs = {}
		
		for edge in edges:
			# Handle both dict and Pydantic model
			if hasattr(edge, 'target'):
				target = edge.target
				source = edge.source
				source_slot = edge.source_slot
				target_slot = edge.target_slot
			elif isinstance(edge, dict):
				target = edge['target']
				source = edge['source']
				source_slot = edge.get('source_slot', 'output')
				target_slot = edge.get('target_slot', 'input')
			else:
				continue
			
			if target != node_idx:
				continue
			
			if source in node_outputs:
				source_data = node_outputs[source]
				
				# Handle dotted slot names
				data = None
				if source_slot in source_data:
					data = source_data[source_slot]
				else:
					base_slot = source_slot.split(".")[0]
					if base_slot in source_data:
						data = source_data[base_slot]
				
				if data is not None:
					inputs[target_slot] = data
		
		return inputs
	
	async def _handle_user_input(self, node_idx: int, node: Any,
								context: NodeExecutionContext,
								state: WorkflowExecutionState) -> NodeExecutionResult:
		"""Handle user input node"""
		extra = context.node_config.get("extra")
		if isinstance(extra, str):
			import json
			try:
				extra = json.loads(extra)
			except:
				extra = {}
		
		prompt = "Please provide input:"
		if isinstance(extra, dict):
			prompt = extra.get("message") or extra.get("title") or prompt
		
		future = asyncio.Future()
		input_key = f"{state.execution_id}:{node_idx}"
		self.pending_user_inputs[input_key] = future
		
		await self.event_bus.emit(
			event_type=EventType.USER_INPUT_REQUESTED,
			workflow_id=state.workflow_id,
			execution_id=state.execution_id,
			node_id=str(node_idx),
			data={"prompt": prompt}
		)
		
		try:
			timeout = context.node_config.get("timeout", 300)
			user_input = await asyncio.wait_for(future, timeout=timeout)
			
			result = NodeExecutionResult()
			result.outputs = {"message": user_input}
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
			
			state = self.executions.get(execution_id)
			if state:
				await self.event_bus.emit(
					event_type=EventType.USER_INPUT_RECEIVED,
					workflow_id=state.workflow_id,
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
		return self.executions.get(execution_id)
	
	def list_executions(self) -> List[WorkflowExecutionState]:
		return list(self.executions.values())
