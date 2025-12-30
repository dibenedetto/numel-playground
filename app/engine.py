# engine

import asyncio
import uuid


from   collections import defaultdict
from   datetime    import datetime
from   enum        import Enum
from   functools   import partial
from   pydantic    import BaseModel
from   typing      import Any, Dict, List, Optional, Set, Tuple


from   event_bus   import EventBus, EventType
from   nodes       import ImplementedBackend, NodeExecutionContext, NodeExecutionResult, create_node
from   schema      import Edge, BaseType, BaseNode, Workflow


DEFAULT_ENGINE_NODE_DELAY_SEC         : float = 0.0
DEFAULT_ENGINE_EXEC_DELAY_SEC         : float = 0.1
DEFAULT_ENGINE_USER_INPUT_TIMEOUT_SEC : float = 300.0


class WorkflowNodeStatus(str, Enum):
	"""Status of a workflow node during execution"""
	PENDING   = "pending"
	READY     = "ready"
	RUNNING   = "running"
	COMPLETED = "completed"
	FAILED    = "failed"
	SKIPPED   = "skipped"
	WAITING   = "waiting"


class WorkflowExecutionState(BaseModel):
	"""State of a workflow execution"""
	workflow_id     : str
	execution_id    : str
	status          : WorkflowNodeStatus
	pending_nodes   : List[int] = []
	ready_nodes     : List[int] = []
	running_nodes   : List[int] = []
	completed_nodes : List[int] = []
	failed_nodes    : List[int] = []
	node_outputs    : Dict[int, Dict[str, Any]] = {}
	start_time      : Optional[str] = None
	end_time        : Optional[str] = None
	error           : Optional[str] = None


class WorkflowEngine:
	"""Frontier-based workflow execution engine"""

	def __init__(self, event_bus: EventBus):
		self.event_bus           : EventBus                          = event_bus
		self.executions          : Dict[str, WorkflowExecutionState] = {}
		self.execution_tasks     : Dict[str, asyncio.Task]           = {}
		self.pending_user_inputs : Dict[str, asyncio.Future]         = {}


	async def start_workflow(self, workflow: Workflow, backend: ImplementedBackend, initial_data: Optional[Dict[str, Any]] = None) -> str:
		"""Start a new workflow execution"""
		execution_id = str(uuid.uuid4())
		workflow_id  = workflow.info.name if workflow.info else "workflow"

		state = WorkflowExecutionState(
			workflow_id  = workflow_id,
			execution_id = execution_id,
			status       = WorkflowNodeStatus.RUNNING,
			start_time   = datetime.now().isoformat()
		)

		self.executions[execution_id] = state

		await self.event_bus.emit(
			event_type   = EventType.WORKFLOW_STARTED,
			workflow_id  = workflow_id,
			execution_id = execution_id,
			data         = {"initial_data": initial_data}
		)

		task = asyncio.create_task(self._execute_workflow(workflow, backend, state, initial_data or {}))
		self.execution_tasks[execution_id] = task

		return execution_id


	async def _execute_workflow(self, workflow: Workflow, backend: ImplementedBackend, state: WorkflowExecutionState, initial_data: Dict[str, Any]):
		"""Main execution loop - frontier-based"""
		try:
			exec_delay_sec = (workflow.extra or {}).get("exec_delay_sec", DEFAULT_ENGINE_EXEC_DELAY_SEC)
			node_delay_sec = (workflow.extra or {}).get("node_delay_sec", DEFAULT_ENGINE_NODE_DELAY_SEC)

			nodes     = workflow.nodes or []
			pending   = set()
			completed = set()
			for i, n in enumerate(nodes):
				if isinstance(n, BaseNode):
					pending.add(i)
				else:
					completed.add(i)

			edges = workflow.edges or []
			active_edges = [e for e in edges if isinstance(nodes[e.source], BaseNode) and isinstance(nodes[e.target], BaseNode)]

			# Instantiate node executors
			node_instances = self._instantiate_nodes(nodes, edges, backend)

			# Build dependency graph from edges
			dependencies = self._build_dependencies (active_edges)
			dependents   = self._build_dependents   (active_edges)

			# Track node states
			ready   = set()
			running = set()

			# Node outputs storage
			node_outputs: Dict[int, Dict[str, Any]] = {}

			# Find start nodes (no dependencies)
			for idx in list(pending):
				if not dependencies[idx]:
					ready.add(idx)
					pending.discard(idx)

			# Global variables
			variables = dict(initial_data)

			# Main execution loop
			while ready or running:
				# await asyncio.sleep(0.01)

				state.pending_nodes   = list(pending)
				state.ready_nodes     = list(ready)
				state.running_nodes   = list(running)
				state.completed_nodes = list(completed)
				state.node_outputs    = node_outputs

				if ready:
					tasks = set()

					for node_idx in list(ready):
						ready.discard(node_idx)
						running.add(node_idx)

						task = asyncio.create_task(self._execute_node(
							nodes, edges, node_idx, node_instances[node_idx],
							node_outputs, dependencies, variables, state,
							node_delay_sec
						))
						tasks.add(task)

					while len(tasks) > 0:
						done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)

						for task in done:
							node_idx, result = await task
							running.discard(node_idx)
							tasks.remove(task)

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
									event_type   = EventType.NODE_FAILED,
									workflow_id  = state.workflow_id,
									execution_id = state.execution_id,
									node_id      = str(node_idx),
									error        = result.error
								)
								raise Exception(f"Node {node_idx} failed: {result.error}")
				else:
					await asyncio.sleep(exec_delay_sec)

			state.status   = WorkflowNodeStatus.COMPLETED
			state.end_time = datetime.now().isoformat()

			await self.event_bus.emit(
				event_type   = EventType.WORKFLOW_COMPLETED,
				workflow_id  = state.workflow_id,
				execution_id = state.execution_id,
				data         = {"outputs": node_outputs}
			)

		except Exception as e:
			state.status   = WorkflowNodeStatus.FAILED
			state.error    = str(e)
			state.end_time = datetime.now().isoformat()

			await self.event_bus.emit(
				event_type   = EventType.WORKFLOW_FAILED,
				workflow_id  = state.workflow_id,
				execution_id = state.execution_id,
				error        = str(e)
			)


	def _build_dependencies(self, edges: List[Edge]) -> Dict[int, Set[int]]:
		"""Build dependency graph: target -> set of sources"""
		deps = defaultdict(set)
		for edge in edges:
			deps[edge.target].add(edge.source)
		return deps


	def _build_dependents(self, edges: List[Edge]) -> Dict[int, Set[int]]:
		"""Build dependent graph: source -> set of targets"""
		deps = defaultdict(set)
		for edge in edges:
			deps[edge.source].add(edge.target)
		return deps


	def _instantiate_nodes(self, nodes: List[BaseType], edges: List[Edge], backend: ImplementedBackend) -> List[Any]:
		"""Create node instances from workflow definition"""

		instances      = [None] * len(nodes)
		with_reference = []

		for i, (node, impl) in enumerate(zip(nodes, backend.handles)):
			if node.type == "agent_node" or node.type == "tool_node":
				with_reference.append(i)
				continue
			instances[i] = create_node(node, impl)

		links = [dict() for _ in range(len(nodes))]
		for edge in edges:
			links[edge.target][edge.target_slot] = edge.source

		for i in with_reference:
			node   = nodes[i]
			impl   = backend.handles[i]
			arg    = instances[links[i]["config"]].impl
			fn     = backend.run_agent if node.type == "agent_node" else backend.run_tool
			ref    = partial(fn, arg)
			kwargs = {"ref": ref}
			instances[i] = create_node(node, impl, **kwargs)

		return instances


	async def _execute_node(self,
		nodes        : List[BaseType],
		edges        : List[Edge],
		node_idx     : int,
		node         : Any,
		node_outputs : Dict[int, Dict[str, Any]],
		dependencies : Dict[int, Set[int]],
		variables    : Dict[str, Any],
		state        : WorkflowExecutionState,
		delay_sec    : int = 0
	) -> Tuple[int, NodeExecutionResult]:
		"""Execute a single node"""
		node_config = nodes[node_idx]
		node_type   = node_config.type
		node_label  = (node_config.extra or {}).get("name", node_type)

		await self.event_bus.emit(
			event_type   = EventType.NODE_STARTED,
			workflow_id  = state.workflow_id,
			execution_id = state.execution_id,
			node_id      = str(node_idx),
			data         = {"node_type": node_type, "node_label": node_label}
		)

		if delay_sec >= 0:
			await asyncio.sleep(delay_sec)

		try:
			context = NodeExecutionContext()
			context.inputs      = self._gather_inputs(edges, node_idx, node_outputs)
			context.variables   = variables
			context.node_index  = node_idx
			context.node_config = node_config

			if node_type == "user_input_node":
				result = await self._handle_user_input(node_idx, node, context, state)
			else:
				result = await node.execute(context)

			if result.success:
				await self.event_bus.emit(
					event_type   = EventType.NODE_COMPLETED,
					workflow_id  = state.workflow_id,
					execution_id = state.execution_id,
					node_id      = str(node_idx),
					data         = {"outputs": result.outputs, "node_label": node_label}
				)

			return node_idx, result

		except Exception as e:
			result = NodeExecutionResult()
			result.success = False
			result.error   = str(e)
			return node_idx, result


	def _gather_inputs(self, edges: List[Edge], node_idx: int, node_outputs: Dict[int, Dict[str, Any]]) -> Dict[str, Any]:
		"""Gather input data from connected edges"""
		inputs = {}

		for edge in edges:
			if edge.target != node_idx:
				continue

			if edge.source in node_outputs:
				source_data = node_outputs[edge.source]
				
				# Handle dotted slot names
				data = None
				if edge.source_slot in source_data:
					data = source_data[edge.source_slot]
				else:
					base_slot = edge.source_slot.split(".")[0]
					if base_slot in source_data:
						data = source_data[base_slot]

				if data is not None:
					inputs[edge.target_slot] = data

		return inputs


	async def _handle_user_input(self, node_idx: int, node: Any, context: NodeExecutionContext, state: WorkflowExecutionState) -> NodeExecutionResult:
		"""Handle user input node"""
		extra  = context.node_config.extra or {}
		prompt = extra.get("message") or extra.get("title") or "Please provide input:"

		future    = asyncio.Future()
		input_key = f"{state.execution_id}:{node_idx}"
		self.pending_user_inputs[input_key] = future

		await self.event_bus.emit(
			event_type   = EventType.USER_INPUT_REQUESTED,
			workflow_id  = state.workflow_id,
			execution_id = state.execution_id,
			node_id      = str(node_idx),
			data         = {"prompt": prompt}
		)

		result = NodeExecutionResult()

		try:
			timeout        = extra.get("timeout", DEFAULT_ENGINE_USER_INPUT_TIMEOUT_SEC)
			user_input     = await asyncio.wait_for(future, timeout=timeout)
			result.outputs = {"message": user_input}

		except asyncio.TimeoutError:
			result.success = False
			result.error   = f"User input timeout after {timeout}s"

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
					event_type   = EventType.USER_INPUT_RECEIVED,
					workflow_id  = state.workflow_id,
					execution_id = execution_id,
					node_id      = node_id,
					data         = {"input": user_input}
				)


	async def cancel_execution(self, execution_id: Optional[str] = None):
		"""Cancel a running workflow"""
		if not execution_id:
			return self._cancel_all_executions()
		state = None
		if execution_id in self.execution_tasks:
			task = self.execution_tasks[execution_id]
			task.cancel()
			state = self.executions.get(execution_id)
			if state:
				state.status   = WorkflowNodeStatus.FAILED
				state.error    = "Cancelled by user"
				state.end_time = datetime.now().isoformat()
		if state:
			await self.event_bus.emit(
				event_type   = EventType.WORKFLOW_CANCELLED,
				workflow_id  = state.workflow_id,
				execution_id = execution_id,
				data         = state.model_dump()
			)
		else:
			await self.event_bus.emit(
				event_type   = EventType.ERROR,
				workflow_id  = state.workflow_id,
				execution_id = execution_id
			)
		return state


	async def _cancel_all_executions(self):
		execs = list(self.execution_tasks.keys())
		for execution_id in execs:
			await self.cancel_execution(execution_id)
		state = {
			"state" : None,
		}
		return state


	def get_execution_state(self, execution_id: Optional[str] = None) -> Optional[WorkflowExecutionState]:
		if not execution_id:
			return self._get_all_execution_states()
		return self.executions.get(execution_id)


	def _get_all_execution_states(self) -> List[WorkflowExecutionState]:
		execs  = list(self.execution_tasks.keys())
		states = {}
		for execution_id in execs:
			states[execution_id] = self.get_execution_state(execution_id)
		return states


	def list_executions(self) -> List[str]:
		return list(self.executions.keys())
