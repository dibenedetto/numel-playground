# engine

import asyncio
import uuid


from   collections import defaultdict
from   datetime    import datetime
from   enum        import Enum
from   functools   import partial
from   pydantic    import BaseModel, Field
from   typing      import Any, Dict, List, Optional, Set, Tuple, Union, get_origin, get_args


from   event_bus   import EventType, EventBus
from   nodes       import ImplementedBackend, NodeExecutionContext, NodeExecutionResult, create_node
from   schema      import DEFAULT_WORKFLOW_NODE_DELAY, DEFAULT_WORKFLOW_EXEC_DELAY, DEFAULT_WORKFLOW_USER_INPUT_TIMEOUT, Edge, BaseType, FlowType, Workflow
from   events      import get_event_registry, EventSourceEvent


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


class WaitType(str, Enum):
	"""Types of wait conditions"""
	TIMER         = "timer"          # Wait for duration
	EVENT         = "event"          # Wait for external event
	GATE          = "gate"           # Wait for threshold/condition


class WaitSignal(BaseModel):
	"""Signal from a node requesting to pause execution"""
	wait_type     : WaitType
	duration_ms   : Optional[int] = None      # For TIMER: milliseconds to wait
	event_name    : Optional[str] = None      # For EVENT: event to wait for
	threshold     : Optional[int] = None      # For GATE: count threshold
	condition     : Optional[str] = None      # For GATE: custom condition expression
	accumulated   : List[Any] = Field(default_factory=list)  # Accumulated data for gate
	count         : int = 0                   # Current count for gate/timer
	max_count     : Optional[int] = None      # Max triggers before stopping
	resume_data   : Dict[str, Any] = Field(default_factory=dict)  # Data to pass on resume

	class Config:
		arbitrary_types_allowed = True


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
	waiting_nodes   : List[int] = []
	completed_nodes : List[int] = []
	failed_nodes    : List[int] = []
	node_outputs    : Dict[int, Dict[str, Any]] = {}
	start_time      : Optional[str] = None
	end_time        : Optional[str] = None
	error           : Optional[str] = None
	# Loop tracking
	loop_stack      : List[int] = []                    # Stack of active loop_start indices
	loop_contexts   : Dict[int, Dict[str, Any]] = {}    # loop_start_idx -> LoopContext dict
	# Wait/Event tracking
	wait_signals    : Dict[int, Dict[str, Any]] = {}    # node_idx -> WaitSignal dict
	scheduled_tasks : Dict[int, str] = {}               # node_idx -> task_id for timers

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

		# Validate Start node count (missing start/end is a warning, not an error;
		# the engine seeds execution from any flow node with no incoming edges)
		if len(start_indices) == 0:
			warnings.append("No Start node — execution begins from flow nodes with no incoming edges")
		elif len(start_indices) > 1:
			errors.append(f"Workflow can only have one Start node (found {len(start_indices)})")

		# Validate End node count
		if len(end_indices) == 0:
			warnings.append("No End node — execution halts when no more flow nodes are ready")
		elif len(end_indices) > 1:
			errors.append(f"Workflow can only have one End node (found {len(end_indices)})")

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
		loop_contexts: Dict[int, LoopContext] = None,
		waiting: Set[int] = None,
		wait_signals: Dict[int, Dict[str, Any]] = None,
		timer_tasks: Dict[int, Any] = None
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
			# Reset waiting state if node was waiting (e.g., gate not yet fired)
			if waiting is not None:
				waiting.discard(node_idx)
			if wait_signals is not None and node_idx in wait_signals:
				del wait_signals[node_idx]
			if timer_tasks is not None and node_idx in timer_tasks:
				# Cancel any pending timer task
				timer_tasks[node_idx].cancel()
				del timer_tasks[node_idx]

		# Also reset the loop end node
		if ctx.loop_end_idx is not None:
			completed.discard(ctx.loop_end_idx)
			running.discard(ctx.loop_end_idx)
			ready.discard(ctx.loop_end_idx)
			pending.add(ctx.loop_end_idx)
			if ctx.loop_end_idx in node_outputs:
				del node_outputs[ctx.loop_end_idx]
			if waiting is not None:
				waiting.discard(ctx.loop_end_idx)

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
		dependencies: Dict[int, Set[int]],
		waiting: Set[int] = None,
		wait_signals: Dict[int, Dict[str, Any]] = None,
		timer_tasks: Dict[int, Any] = None
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
				self._reset_loop_body(ctx, completed, pending, ready, running, node_outputs, loop_contexts,
					waiting, wait_signals, timer_tasks)
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
				self._reset_loop_body(ctx, completed, pending, ready, running, node_outputs, loop_contexts,
					waiting, wait_signals, timer_tasks)
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
			waiting = set()  # Nodes waiting for timer/event/gate

			# Node outputs storage
			node_outputs: Dict[int, Dict[str, Any]] = {}

			# Wait signal storage for paused nodes
			wait_signals: Dict[int, Dict[str, Any]] = {}
			timer_tasks: Dict[int, asyncio.Task] = {}  # Timer tasks for waiting nodes

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
			while ready or running or timer_tasks:
				# await asyncio.sleep(0.01)

				state.pending_nodes   = list(pending)
				state.ready_nodes     = list(ready)
				state.running_nodes   = list(running)
				state.waiting_nodes   = list(waiting)
				state.completed_nodes = list(completed)
				state.node_outputs    = node_outputs
				state.loop_stack      = loop_stack
				state.wait_signals    = {k: v for k, v in wait_signals.items()}

				# ===== TIMER/EVENT COMPLETION HANDLING =====
				# Check for completed timer or event listener tasks
				if timer_tasks:
					done_tasks = [idx for idx, t in timer_tasks.items() if t.done()]
					for node_idx in done_tasks:
						task = timer_tasks.pop(node_idx)
						try:
							result = await task
							waiting.discard(node_idx)

							# Check what type of wait signal this was
							wait_signal = wait_signals.get(node_idx, {})
							wait_type = wait_signal.get("wait_type", "timer")

							if wait_type == "event_listener":
								# Event listener completed: (idx, event_data, source_id, all_events)
								idx, event_data, source_id, all_events = result

								# Inject resume state for event listener
								variables[f"_event_listener_{idx}_resume"] = True
								variables[f"_event_listener_{idx}_event"] = event_data
								variables[f"_event_listener_{idx}_source"] = source_id
								variables[f"_event_listener_{idx}_events"] = all_events
								# timeout flag is already set by the task if needed

								await self.event_bus.emit(
									event_type   = EventType.NODE_RESUMED,
									workflow_id  = state.workflow_id,
									execution_id = state.execution_id,
									node_id      = str(idx),
									data         = {"resumed_from": "event_listener", "source_id": source_id}
								)
							else:
								# Timer/delay completed: (idx, signal)
								idx, signal = result

								# Inject resume state into variables (node-scoped)
								variables["_timer_resume"] = True
								variables["_timer_count"] = signal.get("count", 0) if signal else 0
								variables["_timer_elapsed"] = signal.get("elapsed_ms", 0) if signal else 0
								variables[f"_delay_{idx}_resume"] = True  # Node-scoped for delay nodes

								await self.event_bus.emit(
									event_type   = EventType.NODE_RESUMED,
									workflow_id  = state.workflow_id,
									execution_id = state.execution_id,
									node_id      = str(idx),
									data         = {"resumed_from": "timer"}
								)

							# Re-queue node for execution
							ready.add(idx)

						except Exception as e:
							# Task failed, mark node as failed
							state.failed_nodes.append(node_idx)
							waiting.discard(node_idx)
				# =====================================

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
									# Save loop context BEFORE handling (it may be removed from stack)
									pre_handle_ctx = self._get_current_loop_context(node_idx, loop_contexts, loop_stack)
									loop_start_idx = pre_handle_ctx.loop_start_idx if pre_handle_ctx else None

									signal_handled = self._handle_loop_signal(
										loop_signal, node_idx, nodes,
										loop_contexts, loop_stack,
										completed, pending, ready, running,
										node_outputs, dependencies,
										waiting, wait_signals, timer_tasks
									)
									if signal_handled:
										# Check if loop is continuing or finished
										node = nodes[node_idx]
										node_label = ""
										if hasattr(node, 'extra') and node.extra:
											node_label = node.extra.get("name", "") or node.extra.get("label", "")

										# Check if loop is still active after handling
										loop_still_active = pre_handle_ctx is not None and pre_handle_ctx.is_active

										if loop_still_active:
											# Loop is continuing - show waiting state for loop_end
											await self.event_bus.emit(
												event_type   = EventType.NODE_WAITING,
												workflow_id  = state.workflow_id,
												execution_id = state.execution_id,
												node_id      = str(node_idx),
												data         = {"wait_type": "loop", "iteration": pre_handle_ctx.iteration, "node_label": node_label}
											)
										else:
											# Loop finished - show completed state for loop_end
											await self.event_bus.emit(
												event_type   = EventType.NODE_COMPLETED,
												workflow_id  = state.workflow_id,
												execution_id = state.execution_id,
												node_id      = str(node_idx),
												data         = {"outputs": result.outputs, "node_label": node_label}
											)
											# Also emit NODE_COMPLETED for the loop_start node
											if loop_start_idx is not None:
												start_node = nodes[loop_start_idx]
												start_label = ""
												if hasattr(start_node, 'extra') and start_node.extra:
													start_label = start_node.extra.get("name", "") or start_node.extra.get("label", "")
												await self.event_bus.emit(
													event_type   = EventType.NODE_COMPLETED,
													workflow_id  = state.workflow_id,
													execution_id = state.execution_id,
													node_id      = str(loop_start_idx),
													data         = {"outputs": node_outputs.get(loop_start_idx, {}), "node_label": start_label}
												)

										# Update dependencies for ready check after reset
										for dep_idx in list(pending):
											if dependencies[dep_idx].issubset(completed):
												pending.discard(dep_idx)
												ready.add(dep_idx)
										continue
								# =================================

								# ===== WAIT SIGNAL HANDLING =====
								if result.wait_signal:
									wait_type = result.wait_signal.get("wait_type", "")

									if wait_type == "timer":
										# Timer/Delay wait - schedule a timer task
										duration_ms = result.wait_signal.get("duration_ms", 1000)
										wait_signals[node_idx] = result.wait_signal

										# Move to waiting state (don't propagate downstream yet)
										# Downstream will execute only after all timer triggers complete
										completed.discard(node_idx)
										waiting.add(node_idx)

										# Schedule timer to resume this node
										async def resume_after_timer(idx, duration, signals):
											await asyncio.sleep(duration / 1000.0)
											return idx, signals[idx]

										timer_task = asyncio.create_task(
											resume_after_timer(node_idx, duration_ms, wait_signals)
										)
										timer_tasks[node_idx] = timer_task

										await self.event_bus.emit(
											event_type   = EventType.NODE_WAITING,
											workflow_id  = state.workflow_id,
											execution_id = state.execution_id,
											node_id      = str(node_idx),
											data         = {"wait_type": "timer", "duration_ms": duration_ms}
										)
										continue

									elif wait_type == "gate":
										# Gate wait - hold until threshold met
										wait_signals[node_idx] = result.wait_signal
										completed.discard(node_idx)
										waiting.add(node_idx)

										await self.event_bus.emit(
											event_type   = EventType.NODE_WAITING,
											workflow_id  = state.workflow_id,
											execution_id = state.execution_id,
											node_id      = str(node_idx),
											data         = {"wait_type": "gate", "count": result.wait_signal.get("count", 0)}
										)
										continue

									elif wait_type == "event_listener":
										# Event listener wait - subscribe to event sources
										sources = result.wait_signal.get("sources", [])
										mode = result.wait_signal.get("mode", "any")
										timeout_ms = result.wait_signal.get("timeout_ms")

										wait_signals[node_idx] = result.wait_signal
										completed.discard(node_idx)
										waiting.add(node_idx)

										# Create event listener task
										async def wait_for_events(idx, srcs, md, timeout, signals, vars_ref):
											"""Wait for events from sources based on mode"""
											registry = get_event_registry()
											received_events = {}
											event_queue = asyncio.Queue()
											subscriber_id = f"workflow_{state.workflow_id}_{idx}"

											# Callback to receive events
											async def on_event(event: EventSourceEvent):
												await event_queue.put(event)

											try:
												# Subscribe to all sources
												for source_id in srcs:
													source = registry.get(source_id)
													if source:
														await registry.subscribe(source_id, subscriber_id, on_event)

												# Wait for events based on mode
												start_time = asyncio.get_event_loop().time()

												while True:
													# Calculate remaining timeout
													remaining_timeout = None
													if timeout:
														elapsed = (asyncio.get_event_loop().time() - start_time) * 1000
														remaining_timeout = max(0.1, (timeout - elapsed) / 1000.0)
														if elapsed >= timeout:
															# Timeout occurred
															vars_ref[f"_event_listener_{idx}_timeout"] = True
															return idx, None, None, received_events

													try:
														event = await asyncio.wait_for(
															event_queue.get(),
															timeout=remaining_timeout or 0.5
														)

														received_events[event.source_id] = event.data

														if md == "any" or md == "race":
															# First event triggers
															return idx, event.data, event.source_id, received_events

														elif md == "all":
															# Check if we have events from all sources
															if all(sid in received_events for sid in srcs):
																return idx, event.data, event.source_id, received_events

													except asyncio.TimeoutError:
														if timeout and remaining_timeout and remaining_timeout <= 0.1:
															vars_ref[f"_event_listener_{idx}_timeout"] = True
															return idx, None, None, received_events
														continue

											finally:
												# Unsubscribe from all sources
												for source_id in srcs:
													await registry.unsubscribe(source_id, subscriber_id)

										event_task = asyncio.create_task(
											wait_for_events(node_idx, sources, mode, timeout_ms, wait_signals, variables)
										)
										timer_tasks[node_idx] = event_task  # Reuse timer_tasks dict for event tasks

										await self.event_bus.emit(
											event_type   = EventType.NODE_WAITING,
											workflow_id  = state.workflow_id,
											execution_id = state.execution_id,
											node_id      = str(node_idx),
											data         = {"wait_type": "event_listener", "sources": sources, "mode": mode}
										)
										continue
								# =================================

								# Emit NODE_COMPLETED or NODE_WAITING for loop_start nodes
								node = nodes[node_idx]
								node_label = ""
								if hasattr(node, 'extra') and node.extra:
									node_label = node.extra.get("name", "") or node.extra.get("label", "")

								# Check if this is a loop_start node with active loop
								if self._is_loop_start_node(node):
									loop_ctx = loop_contexts.get(node_idx)
									if loop_ctx and loop_ctx.is_active:
										# Loop is active - show waiting state
										await self.event_bus.emit(
											event_type   = EventType.NODE_WAITING,
											workflow_id  = state.workflow_id,
											execution_id = state.execution_id,
											node_id      = str(node_idx),
											data         = {"wait_type": "loop", "iteration": loop_ctx.iteration, "node_label": node_label}
										)
									else:
										# Loop finished or skipped - show completed
										await self.event_bus.emit(
											event_type   = EventType.NODE_COMPLETED,
											workflow_id  = state.workflow_id,
											execution_id = state.execution_id,
											node_id      = str(node_idx),
											data         = {"outputs": result.outputs, "node_label": node_label}
										)
								else:
									# Regular node - emit completed
									await self.event_bus.emit(
										event_type   = EventType.NODE_COMPLETED,
										workflow_id  = state.workflow_id,
										execution_id = state.execution_id,
										node_id      = str(node_idx),
										data         = {"outputs": result.outputs, "node_label": node_label}
									)

								# Normal dependency propagation
								# For route nodes, only propagate to the selected branch
								allowed_deps = dependents[node_idx]
								if result.next_target is not None:
									target_key = result.next_target
									allowed_deps = set()
									skipped_deps = set()
									for edge in active_edges:
										if edge.source != node_idx or getattr(edge, 'loop', False):
											continue
										slot = edge.source_slot or ""
										# Match: exact slot name, dotted prefix (output.support), or "default"
										if slot == target_key or slot.split(".")[-1] == target_key:
											allowed_deps.add(edge.target)
										else:
											skipped_deps.add(edge.target)
									# Skip non-selected branches so they don't block downstream
									for skip_idx in skipped_deps - allowed_deps:
										if skip_idx in pending:
											completed.add(skip_idx)
											pending.discard(skip_idx)
											node_outputs[skip_idx] = {}

								for dep_idx in allowed_deps:
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
			context.inputs      = self._gather_inputs(edges, node_idx, node_outputs, node_config)
			context.variables   = variables
			context.node_index  = node_idx
			context.node_config = node_config

			if node_type == "user_input_flow":
				result = await self._handle_user_input(node_idx, node, context, state, input_timeout)
			else:
				result = await node.execute(context)

			# NOTE: NODE_COMPLETED is emitted in the main loop after checking for wait_signal
			# This ensures nodes waiting for timer/gate don't trigger premature visual feedback

			return node_idx, result

		except Exception as e:
			result = NodeExecutionResult()
			result.success = False
			result.error   = str(e)
			return node_idx, result


	# Fields from base classes that should not be treated as data inputs
	_BASE_FIELDS = frozenset({"type", "id", "extra", "flow"})

	@staticmethod
	def _unwrap_annotation(annotation: Any) -> Any:
		"""Unwrap Annotated[X, ...] and Optional[X] down to the core type."""
		if annotation is None or annotation is Any:
			return annotation
		# Unwrap Annotated[X, ...] — has __metadata__ attribute
		if hasattr(annotation, '__metadata__'):
			args = get_args(annotation)
			if args:
				return WorkflowEngine._unwrap_annotation(args[0])
		# Unwrap Optional[X] = Union[X, None]
		origin = get_origin(annotation)
		if origin is Union:
			non_none = [a for a in get_args(annotation) if a is not type(None)]
			if len(non_none) == 1:
				return WorkflowEngine._unwrap_annotation(non_none[0])
		return annotation

	@staticmethod
	def _coerce_edge_value(value: Any, annotation: Any) -> Any:
		"""Coerce an edge value to the target field's type annotation.
		Only coerces between primitive scalar types; leaves complex/Any types unchanged."""
		core = WorkflowEngine._unwrap_annotation(annotation)
		if core is None or core is Any or value is None:
			return value
		if isinstance(value, core):
			return value  # already correct type
		try:
			if core is int and not isinstance(value, bool):
				return int(value)
			if core is float:
				return float(value)
			if core is str:
				return str(value)
			if core is bool:
				if isinstance(value, str):
					return value.lower() not in ('false', '0', 'no', 'none', '')
				return bool(value)
		except (TypeError, ValueError):
			pass
		return value

	def _gather_inputs(self, edges: List[Edge], node_idx: int, node_outputs: Dict[int, Dict[str, Any]], node_config: Any = None) -> Dict[str, Any]:
		"""Gather input data from node config (native values) and connected edges.
		Edge-connected values override native values."""

		# Seed with native field values from the node config
		inputs = {}
		if node_config is not None:
			for key, val in node_config.dict().items():
				if key in self._BASE_FIELDS:
					continue
				if val is not None:
					inputs[key] = val

		# Precompute field annotations for coercion (Pydantic v2)
		field_annotations: Dict[str, Any] = {}
		if node_config is not None and hasattr(node_config, 'model_fields'):
			field_annotations = {name: fi.annotation for name, fi in node_config.model_fields.items()}

		# Override with edge-connected values
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
					# Coerce to target field type when possible
					ann = field_annotations.get(edge.target_slot)
					if ann is not None:
						data = self._coerce_edge_value(data, ann)
					inputs[edge.target_slot] = data

		return inputs


	async def _handle_user_input(self, node_idx: int, node: Any, context: NodeExecutionContext, state: WorkflowExecutionState, timeout: int = DEFAULT_WORKFLOW_USER_INPUT_TIMEOUT) -> NodeExecutionResult:
		"""Handle user input node"""
		prompt = getattr(context.node_config, 'query', None) or "Please provide input:"

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
			# Cancel any pending user-input futures
			for key in [k for k in self.pending_user_inputs if k.startswith(execution_id + ':')]:
				self.pending_user_inputs.pop(key, None)
			# Emit NODE_FAILED for every node still in running state
			for node_idx in list(state.running_nodes):
				await self.event_bus.emit(
					event_type   = EventType.NODE_FAILED,
					workflow_id  = state.workflow_id,
					execution_id = execution_id,
					node_id      = str(node_idx),
					data         = {"error": "Cancelled"}
				)
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
