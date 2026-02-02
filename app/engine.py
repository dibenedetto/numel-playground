# engine

import asyncio
import uuid


from   collections import defaultdict
from   datetime    import datetime
from   enum        import Enum
from   functools   import partial
from   pydantic    import BaseModel, Field
from   typing      import Any, Dict, List, Optional, Set, Tuple


from   event_bus   import EventType, EventBus
from   nodes       import ImplementedBackend, NodeExecutionContext, NodeExecutionResult, create_node
from   schema      import DEFAULT_WORKFLOW_NODE_DELAY, DEFAULT_WORKFLOW_EXEC_DELAY, DEFAULT_WORKFLOW_USER_INPUT_TIMEOUT, Edge, BaseType, FlowType, Workflow


class WorkflowNodeStatus(str, Enum):
	"""Status of a workflow node during execution"""
	PENDING   = "pending"
	READY     = "ready"
	RUNNING   = "running"
	COMPLETED = "completed"
	FAILED    = "failed"
	SKIPPED   = "skipped"
	WAITING   = "waiting"


class LoopSignal(str, Enum):
	"""Signals from loop control nodes"""
	NONE          = "none"
	LOOP_END      = "end"
	FOR_EACH_END  = "for_each_end"
	BREAK         = "break"
	CONTINUE      = "continue"


class LoopContext(BaseModel):
	"""Context for a single loop (supports nesting via stack)"""
	loop_start_idx  : int                          # Index of LoopStart/ForEach node
	loop_end_idx    : Optional[int] = None         # Index of LoopEnd/ForEachEnd node
	loop_type       : str = "loop"                 # "loop" or "for_each"
	iteration       : int = 0                      # Current iteration (0-based)
	max_iterations  : int = 10000                  # Safety limit
	items_count     : int = 0                      # For ForEach: total items
	body_nodes      : Set[int] = Field(default_factory=set)  # Nodes inside this loop body
	is_active       : bool = True                  # False when loop is done/broken

	class Config:
		arbitrary_types_allowed = True


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
	# Loop tracking
	loop_stack      : List[int] = []                    # Stack of active loop_start indices
	loop_contexts   : Dict[int, Dict[str, Any]] = {}    # loop_start_idx -> LoopContext dict

	class Config:
		arbitrary_types_allowed = True


class WorkflowEngine:
	"""Frontier-based workflow execution engine"""

	def __init__(self, event_bus: EventBus):
		self.event_bus           : EventBus                          = event_bus
		self.executions          : Dict[str, WorkflowExecutionState] = {}
		self.execution_tasks     : Dict[str, asyncio.Task]           = {}
		self.pending_user_inputs : Dict[str, asyncio.Future]         = {}


	def validate_workflow(self, workflow: Workflow) -> Dict[str, Any]:
		"""
		Validate workflow structure before execution.
		Checks:
		- Exactly one Start node exists
		- Exactly one End node exists
		- A path exists from Start to End

		Returns dict with 'valid', 'errors', and 'warnings' keys.
		"""
		errors   : List[str] = []
		warnings : List[str] = []

		nodes = workflow.nodes or []
		edges = workflow.edges or []

		# Find Start and End nodes
		start_indices = []
		end_indices   = []

		for i, node in enumerate(nodes):
			node_type = getattr(node, 'type', None)
			if node_type == 'start_flow':
				start_indices.append(i)
			elif node_type == 'end_flow':
				end_indices.append(i)

		# Validate Start node count
		if len(start_indices) == 0:
			errors.append("Workflow requires a Start node")
		elif len(start_indices) > 1:
			errors.append(f"Workflow can only have one Start node (found {len(start_indices)})")

		# Validate End node count
		if len(end_indices) == 0:
			errors.append("Workflow requires an End node")
		elif len(end_indices) > 1:
			errors.append(f"Workflow can only have one End node (found {len(end_indices)})")

		# Validate path from Start to End (only if both exist and are unique)
		if len(start_indices) == 1 and len(end_indices) == 1:
			start_idx = start_indices[0]
			end_idx   = end_indices[0]

			# Build adjacency list
			adjacency: Dict[int, Set[int]] = defaultdict(set)
			for edge in edges:
				adjacency[edge.source].add(edge.target)

			# BFS from Start to End
			visited = set()
			queue   = [start_idx]
			visited.add(start_idx)
			found_path = False

			while queue:
				current = queue.pop(0)
				if current == end_idx:
					found_path = True
					break
				for neighbor in adjacency[current]:
					if neighbor not in visited:
						visited.add(neighbor)
						queue.append(neighbor)

			if not found_path:
				errors.append("No path exists from Start to End node")

		# Check for disconnected flow nodes (warning)
		connected_nodes: Set[int] = set()
		for edge in edges:
			connected_nodes.add(edge.source)
			connected_nodes.add(edge.target)

		flow_nodes = [i for i, n in enumerate(nodes) if isinstance(n, FlowType)]
		disconnected = [i for i in flow_nodes if i not in connected_nodes]
		if disconnected:
			warnings.append(f"{len(disconnected)} workflow node(s) are not connected")

		return {
			"valid"    : len(errors) == 0,
			"errors"   : errors,
			"warnings" : warnings
		}


	# =========================================================================
	# LOOP HANDLING METHODS
	# =========================================================================

	def _is_loop_start_node(self, node: BaseType) -> bool:
		"""Check if node is a loop start (LoopStart or ForEach)"""
		return getattr(node, 'type', None) in ('loop_start_flow', 'for_each_start_flow')

	def _is_loop_end_node(self, node: BaseType) -> bool:
		"""Check if node is a loop end (LoopEnd or ForEachEnd)"""
		return getattr(node, 'type', None) in ('loop_end_flow', 'for_each_end_flow')

	def _is_break_node(self, node: BaseType) -> bool:
		"""Check if node is a Break node"""
		return getattr(node, 'type', None) == 'break_flow'

	def _is_continue_node(self, node: BaseType) -> bool:
		"""Check if node is a Continue node"""
		return getattr(node, 'type', None) == 'continue_flow'

	def _is_loop_control_node(self, node: BaseType) -> bool:
		"""Check if node is any loop control node"""
		return self._is_loop_start_node(node) or self._is_loop_end_node(node) or \
		       self._is_break_node(node) or self._is_continue_node(node)

	def _detect_loop_structures(
		self,
		nodes: List[BaseType],
		edges: List[Edge]
	) -> Dict[int, LoopContext]:
		"""
		Detect and pair loop structures in the workflow.

		Uses DFS from each LoopStart to find its corresponding LoopEnd.
		Supports nested loops by tracking the loop stack.

		Returns: Dict mapping loop_start_idx -> LoopContext
		"""
		loop_contexts: Dict[int, LoopContext] = {}

		# Build adjacency list for forward traversal (excluding loop-back edges)
		forward_edges: Dict[int, Set[int]] = defaultdict(set)
		for edge in edges:
			if getattr(edge, 'loop', False):
				continue
			forward_edges[edge.source].add(edge.target)

		# Find all loop start nodes
		loop_starts = [
			i for i, node in enumerate(nodes)
			if self._is_loop_start_node(node)
		]

		# For each loop start, find its body and end
		for start_idx in loop_starts:
			node = nodes[start_idx]
			loop_type = "for_each" if node.type == 'for_each_start_flow' else "loop"
			end_type = 'for_each_end_flow' if loop_type == "for_each" else 'loop_end_flow'

			# DFS to find loop body and matching end
			body_nodes: Set[int] = set()
			loop_end_idx: Optional[int] = None
			stack = list(forward_edges[start_idx])
			visited = {start_idx}

			while stack and loop_end_idx is None:
				current = stack.pop()
				if current in visited:
					continue
				visited.add(current)

				current_node = nodes[current]
				current_type = getattr(current_node, 'type', None)

				# Found matching loop end
				if current_type == end_type:
					loop_end_idx = current
					break

				# Handle nested loop starts - include all their body nodes
				if self._is_loop_start_node(current_node) and current != start_idx:
					# Find the nested loop's end and its body
					nested_end, nested_body = self._find_loop_end_and_body(nodes, edges, current)
					if nested_end is not None:
						body_nodes.add(current)
						body_nodes.add(nested_end)
						# Add all nested loop body nodes too
						body_nodes.update(nested_body)
						# Continue from after the nested loop
						stack.extend(forward_edges[nested_end])
					continue

				body_nodes.add(current)
				stack.extend(forward_edges[current])

			# Create loop context
			max_iter = getattr(node, 'max_iter', 10000) if hasattr(node, 'max_iter') else 10000
			loop_contexts[start_idx] = LoopContext(
				loop_start_idx=start_idx,
				loop_end_idx=loop_end_idx,
				loop_type=loop_type,
				iteration=0,
				max_iterations=max_iter,
				body_nodes=body_nodes,
				is_active=True
			)

		return loop_contexts

	def _find_loop_end(
		self,
		nodes: List[BaseType],
		edges: List[Edge],
		start_idx: int
	) -> Optional[int]:
		"""Find the loop end node for a given loop start"""
		node = nodes[start_idx]
		end_type = 'for_each_end_flow' if node.type == 'for_each_start_flow' else 'loop_end_flow'

		forward_edges: Dict[int, Set[int]] = defaultdict(set)
		for edge in edges:
			if getattr(edge, 'loop', False):
				continue
			forward_edges[edge.source].add(edge.target)

		stack = list(forward_edges[start_idx])
		visited = {start_idx}
		nested_depth = 0

		while stack:
			current = stack.pop()
			if current in visited:
				continue
			visited.add(current)

			current_node = nodes[current]
			current_type = getattr(current_node, 'type', None)

			# Track nested loops
			if self._is_loop_start_node(current_node):
				nested_depth += 1
			elif self._is_loop_end_node(current_node):
				if nested_depth > 0:
					nested_depth -= 1
				elif current_type == end_type:
					return current

			stack.extend(forward_edges[current])

		return None

	def _find_loop_end_and_body(
		self,
		nodes: List[BaseType],
		edges: List[Edge],
		start_idx: int
	) -> tuple[Optional[int], Set[int]]:
		"""Find the loop end node and all body nodes for a given loop start"""
		node = nodes[start_idx]
		end_type = 'for_each_end_flow' if node.type == 'for_each_start_flow' else 'loop_end_flow'

		forward_edges: Dict[int, Set[int]] = defaultdict(set)
		for edge in edges:
			if getattr(edge, 'loop', False):
				continue
			forward_edges[edge.source].add(edge.target)

		stack = list(forward_edges[start_idx])
		visited = {start_idx}
		body_nodes: Set[int] = set()
		nested_depth = 0

		while stack:
			current = stack.pop()
			if current in visited:
				continue
			visited.add(current)

			current_node = nodes[current]
			current_type = getattr(current_node, 'type', None)

			# Track nested loops
			if self._is_loop_start_node(current_node):
				nested_depth += 1
				body_nodes.add(current)
			elif self._is_loop_end_node(current_node):
				if nested_depth > 0:
					nested_depth -= 1
					body_nodes.add(current)
				elif current_type == end_type:
					return current, body_nodes
			else:
				body_nodes.add(current)

			stack.extend(forward_edges[current])

		return None, body_nodes

	def _get_current_loop_context(
		self,
		node_idx: int,
		loop_contexts: Dict[int, LoopContext],
		loop_stack: List[int]
	) -> Optional[LoopContext]:
		"""Get the innermost active loop context for a node"""
		for loop_start_idx in reversed(loop_stack):
			ctx = loop_contexts.get(loop_start_idx)
			if ctx and ctx.is_active:
				if node_idx in ctx.body_nodes or node_idx == ctx.loop_start_idx or node_idx == ctx.loop_end_idx:
					return ctx
		return None

	def _reset_loop_body(
		self,
		ctx: LoopContext,
		completed: Set[int],
		pending: Set[int],
		ready: Set[int],
		running: Set[int],
		node_outputs: Dict[int, Dict[str, Any]],
		loop_contexts: Dict[int, LoopContext] = None
	):
		"""Reset all nodes in a loop body for the next iteration"""
		for node_idx in ctx.body_nodes:
			completed.discard(node_idx)
			running.discard(node_idx)
			ready.discard(node_idx)
			pending.add(node_idx)
			# Clear outputs from previous iteration
			if node_idx in node_outputs:
				del node_outputs[node_idx]
			# Reset any nested loop context iteration counters
			if loop_contexts and node_idx in loop_contexts:
				nested_ctx = loop_contexts[node_idx]
				nested_ctx.iteration = 0
				nested_ctx.is_active = True

		# Also reset the loop end node
		if ctx.loop_end_idx is not None:
			completed.discard(ctx.loop_end_idx)
			running.discard(ctx.loop_end_idx)
			ready.discard(ctx.loop_end_idx)
			pending.add(ctx.loop_end_idx)
			if ctx.loop_end_idx in node_outputs:
				del node_outputs[ctx.loop_end_idx]

	def _skip_loop_body(
		self,
		ctx: LoopContext,
		completed: Set[int],
		pending: Set[int],
		ready: Set[int]
	):
		"""Skip all nodes in a loop body (when condition is false or break)"""
		for node_idx in ctx.body_nodes:
			pending.discard(node_idx)
			ready.discard(node_idx)
			completed.add(node_idx)

		# Mark loop end as completed too
		if ctx.loop_end_idx is not None:
			pending.discard(ctx.loop_end_idx)
			ready.discard(ctx.loop_end_idx)
			completed.add(ctx.loop_end_idx)

		ctx.is_active = False

	def _handle_loop_signal(
		self,
		signal: str,
		node_idx: int,
		nodes: List[BaseType],
		loop_contexts: Dict[int, LoopContext],
		loop_stack: List[int],
		completed: Set[int],
		pending: Set[int],
		ready: Set[int],
		running: Set[int],
		node_outputs: Dict[int, Dict[str, Any]],
		dependencies: Dict[int, Set[int]]
	) -> bool:
		"""
		Handle a loop control signal.

		Returns True if the signal was handled and normal flow should be interrupted.
		"""
		if signal == LoopSignal.NONE.value or not signal:
			return False

		# Find the current loop context
		ctx = self._get_current_loop_context(node_idx, loop_contexts, loop_stack)
		if not ctx:
			return False

		if signal == LoopSignal.BREAK.value:
			# Exit the loop immediately
			self._skip_loop_body(ctx, completed, pending, ready)
			if ctx.loop_start_idx in loop_stack:
				loop_stack.remove(ctx.loop_start_idx)
			return True

		elif signal == LoopSignal.CONTINUE.value:
			# Skip remaining body nodes and go to next iteration
			# Reset body but increment iteration first
			ctx.iteration += 1

			# Check if we should continue or exit
			should_continue = self._evaluate_loop_condition(ctx, nodes, node_outputs)
			if should_continue:
				self._reset_loop_body(ctx, completed, pending, ready, running, node_outputs, loop_contexts)
				# Re-queue the loop start
				completed.discard(ctx.loop_start_idx)
				ready.add(ctx.loop_start_idx)
			else:
				self._skip_loop_body(ctx, completed, pending, ready)
				if ctx.loop_start_idx in loop_stack:
					loop_stack.remove(ctx.loop_start_idx)
			return True

		elif signal in (LoopSignal.LOOP_END.value, LoopSignal.FOR_EACH_END.value):
			# End of current iteration - check condition for next
			ctx.iteration += 1

			should_continue = self._evaluate_loop_condition(ctx, nodes, node_outputs)
			if should_continue:
				self._reset_loop_body(ctx, completed, pending, ready, running, node_outputs, loop_contexts)
				# Re-queue the loop start
				completed.discard(ctx.loop_start_idx)
				ready.add(ctx.loop_start_idx)
			else:
				# Loop is done
				ctx.is_active = False
				if ctx.loop_start_idx in loop_stack:
					loop_stack.remove(ctx.loop_start_idx)
			return True

		return False

	def _evaluate_loop_condition(
		self,
		ctx: LoopContext,
		nodes: List[BaseType],
		node_outputs: Dict[int, Dict[str, Any]]
	) -> bool:
		"""Evaluate whether a loop should continue"""
		# Check max iterations
		if ctx.iteration >= ctx.max_iterations:
			return False

		if ctx.loop_type == "for_each":
			# ForEach continues while there are items
			outputs = node_outputs.get(ctx.loop_start_idx, {})
			items_count = outputs.get("_items_count", 0)
			return ctx.iteration < items_count
		else:
			# Regular loop - check condition input
			# The condition is evaluated at the loop start node
			# For now, we check the last known condition value
			# A more sophisticated approach would re-evaluate connected inputs
			node = nodes[ctx.loop_start_idx]
			condition = getattr(node, 'condition', True)
			return bool(condition)

	# =========================================================================
	# END LOOP HANDLING METHODS
	# =========================================================================


	async def start_workflow(self, workflow: Workflow, backend: ImplementedBackend, initial_data: Optional[Dict[str, Any]] = None) -> str:
		"""Start a new workflow execution"""

		# Validate workflow before starting
		validation = self.validate_workflow(workflow)
		if not validation["valid"]:
			error_msg = "; ".join(validation["errors"])
			raise ValueError(f"Invalid workflow: {error_msg}")

		execution_id = str(uuid.uuid4())
		workflow_id  = workflow.options.name if workflow.options else "Lou"

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

		task = asyncio.create_task(self._execute_workflow(workflow, backend, state, initial_data))
		self.execution_tasks[execution_id] = task

		return execution_id


	async def _execute_workflow(self, workflow: Workflow, backend: ImplementedBackend, state: WorkflowExecutionState, initial_data: Dict[str, Any]):
		"""Main execution loop - frontier-based with loop support"""
		try:
			if not initial_data:
				initial_data = {}

			exec_delay    = initial_data.get("exec_delay"        , DEFAULT_WORKFLOW_EXEC_DELAY        )
			node_delay    = initial_data.get("node_delay"        , DEFAULT_WORKFLOW_NODE_DELAY        )
			input_timeout = initial_data.get("user_input_timeout", DEFAULT_WORKFLOW_USER_INPUT_TIMEOUT)

			nodes     = workflow.nodes or []
			pending   = set()
			completed = set()
			for i, n in enumerate(nodes):
				if isinstance(n, FlowType):
					pending.add(i)
				else:
					completed.add(i)

			edges = workflow.edges or []
			active_edges = [e for e in edges if isinstance(nodes[e.source], FlowType) and isinstance(nodes[e.target], FlowType)]

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

			# ===== LOOP SUPPORT =====
			# Detect and initialize loop structures
			loop_contexts = self._detect_loop_structures(nodes, active_edges)
			loop_stack: List[int] = []  # Stack of active loop_start indices

			# Store in state for visibility
			state.loop_contexts = {k: v.model_dump() for k, v in loop_contexts.items()}
			state.loop_stack = loop_stack
			# ========================

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
				state.loop_stack      = loop_stack

				if ready:
					tasks = set()

					for node_idx in list(ready):
						node = nodes[node_idx]

						# ===== LOOP START HANDLING =====
						if self._is_loop_start_node(node):
							ctx = loop_contexts.get(node_idx)
							if ctx:
								# Inject iteration into variables for the node
								variables["_loop_iteration"] = ctx.iteration

								# Check if this is the first time or a repeat
								if ctx.iteration == 0:
									# First iteration - evaluate condition
									condition = self._gather_loop_condition(node_idx, nodes, edges, node_outputs)
									if not condition:
										# Condition false from start - skip entire loop
										self._skip_loop_body(ctx, completed, pending, ready)
										ready.discard(node_idx)
										completed.add(node_idx)
										continue

									# Push to loop stack
									if node_idx not in loop_stack:
										loop_stack.append(node_idx)
								else:
									# Subsequent iteration - push back if not in stack
									if node_idx not in loop_stack:
										loop_stack.append(node_idx)
						# ===============================

						ready.discard(node_idx)
						running.add(node_idx)

						task = asyncio.create_task(self._execute_node(
							nodes, edges, node_idx, node_instances[node_idx],
							node_outputs, dependencies, variables, state,
							node_delay, input_timeout,
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

								# ===== LOOP SIGNAL HANDLING =====
								loop_signal = result.outputs.get("_loop_signal", "")
								if loop_signal:
									signal_handled = self._handle_loop_signal(
										loop_signal, node_idx, nodes,
										loop_contexts, loop_stack,
										completed, pending, ready, running,
										node_outputs, dependencies
									)
									if signal_handled:
										# Update dependencies for ready check after reset
										for dep_idx in list(pending):
											if dependencies[dep_idx].issubset(completed):
												pending.discard(dep_idx)
												ready.add(dep_idx)
										continue
								# =================================

								# Normal dependency propagation
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
					await asyncio.sleep(exec_delay)

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

	def _gather_loop_condition(
		self,
		loop_start_idx: int,
		nodes: List[BaseType],
		edges: List[Edge],
		node_outputs: Dict[int, Dict[str, Any]]
	) -> bool:
		"""Gather the condition input for a loop start node"""
		node = nodes[loop_start_idx]

		# Check for connected condition input
		for edge in edges:
			if edge.target == loop_start_idx and edge.target_slot == "condition":
				source_outputs = node_outputs.get(edge.source, {})
				if edge.source_slot in source_outputs:
					return bool(source_outputs[edge.source_slot])

		# Fall back to node's default condition
		return getattr(node, 'condition', True)


	def _build_dependencies(self, edges: List[Edge]) -> Dict[int, Set[int]]:
		"""Build dependency graph: target -> set of sources (excluding loop-back edges)"""
		deps = defaultdict(set)
		for edge in edges:
			# Skip loop-back edges - they don't create execution dependencies
			if getattr(edge, 'loop', False):
				continue
			deps[edge.target].add(edge.source)
		return deps


	def _build_dependents(self, edges: List[Edge]) -> Dict[int, Set[int]]:
		"""Build dependent graph: source -> set of targets (excluding loop-back edges)"""
		deps = defaultdict(set)
		for edge in edges:
			# Skip loop-back edges - they don't create execution dependencies
			if getattr(edge, 'loop', False):
				continue
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
		nodes         : List[BaseType],
		edges         : List[Edge],
		node_idx      : int,
		node          : Any,
		node_outputs  : Dict[int, Dict[str, Any]],
		dependencies  : Dict[int, Set[int]],
		variables     : Dict[str, Any],
		state         : WorkflowExecutionState,
		delay         : int = DEFAULT_WORKFLOW_NODE_DELAY,
		input_timeout : int = DEFAULT_WORKFLOW_USER_INPUT_TIMEOUT,
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

		if delay > 0:
			await asyncio.sleep(delay)

		try:
			context = NodeExecutionContext()
			context.inputs      = self._gather_inputs(edges, node_idx, node_outputs)
			context.variables   = variables
			context.node_index  = node_idx
			context.node_config = node_config

			if node_type == "user_input_node":
				result = await self._handle_user_input(node_idx, node, context, state, input_timeout)
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


	async def _handle_user_input(self, node_idx: int, node: Any, context: NodeExecutionContext, state: WorkflowExecutionState, timeout: int = DEFAULT_WORKFLOW_USER_INPUT_TIMEOUT) -> NodeExecutionResult:
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
