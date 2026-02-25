# nodes

import copy


from   jinja2   import Template
from   pydantic import BaseModel
from   typing   import Any, Callable, Dict, List, Optional


from   schema   import DEFAULT_TRANSFORM_NODE_LANG, DEFAULT_TRANSFORM_NODE_SCRIPT, BaseType
from   events   import get_event_registry, TimerSourceConfig, FSWatchSourceConfig, WebhookSourceConfig, BrowserSourceConfig


class NodeExecutionContext:
	def __init__(self):
		self.inputs      : Dict[str, Any] = {}
		self.variables   : Dict[str, Any] = {}
		self.node_index  : int            = 0
		self.node_config : Dict[str, Any] = {}


class NodeExecutionResult:
	def __init__(self):
		self.outputs     : Dict[str, Any] = {}
		self.success     : bool           = True
		self.error       : Optional[str]  = None
		self.next_target : Optional[str]  = None
		self.wait_signal : Optional[Dict] = None  # If set, node wants to pause (timer/gate)


class WFBaseType:
	def __init__(self, config: Dict[str, Any] = None, impl: Any = None, **kwargs):
		self.config = config or {}
		self.impl   = impl
		
	async def execute(self, context: NodeExecutionContext) -> NodeExecutionResult:
		result = NodeExecutionResult()
		return result


class WFComponentType(WFBaseType):
	pass


class WFEdge(WFComponentType):
	pass


class WFNativeType(WFBaseType):
	pass


class WFNativeBoolean(WFNativeType):
	pass


class WFNativeInteger(WFNativeType):
	pass


class WFNativeReal(WFNativeType):
	pass


class WFNativeString(WFNativeType):
	pass


class WFNativeList(WFNativeType):
	pass


class WFNativeDictionary(WFNativeType):
	pass


class WFTensorType(WFBaseType):
	pass


class WFDataTensor(WFTensorType):
	pass


class WFConfigType(WFBaseType):
	async def execute(self, context: NodeExecutionContext) -> NodeExecutionResult:
		result = await super().execute(context)
		result.outputs["config"] = self.config
		return result


class WFBackendConfig(WFConfigType):
	pass


class WFModelConfig(WFConfigType):
	pass


class WFEmbeddingConfig(WFConfigType):
	pass


class WFContentDBConfig(WFConfigType):
	pass


class WFIndexDBConfig(WFConfigType):
	pass


class WFMemoryManagerConfig(WFConfigType):
	pass


class WFSessionManagerConfig(WFConfigType):
	pass


class WFKnowledgeManagerConfig(WFConfigType):
	pass


class WFToolConfig(WFConfigType):
	pass


class WFAgentOptionsConfig(WFConfigType):
	pass


class WFAgentConfig(WFConfigType):
	pass


class WFFlowType(WFBaseType):
	async def execute(self, context: NodeExecutionContext) -> NodeExecutionResult:
		result = await super().execute(context)
		result.outputs["flow_out"] = context.variables.copy()
		return result


class WFStartFlow(WFFlowType):
	async def execute(self, context: NodeExecutionContext) -> NodeExecutionResult:
		result = await super().execute(context)
		result.outputs["flow_out"] = context.inputs.get("flow_in")
		return result


class WFEndFlow(WFFlowType):
	pass


class WFSinkFlow(WFFlowType):
	pass


class WFPreviewFlow(WFFlowType):
	pass


class WFRouteFlow(WFFlowType):
	async def execute(self, context: NodeExecutionContext) -> NodeExecutionResult:
		result = await super().execute(context)

		try:
			target = context.inputs.get("target")
			if target is not None:
				target = str(target)

			outputs = self.config.output or {}

			if target in outputs:
				# MULTI_OUTPUT slot: edge uses source_slot "output.<key>"
				result.outputs[f"output.{target}"] = context.inputs.get("input")
			else:
				target = "default"
				result.outputs["default"] = context.inputs.get("input")

			result.next_target = target

		except Exception as e:
			result.success = False
			result.error   = str(e)
			
		return result


class WFCombineFlow(WFFlowType):
	async def execute(self, context: NodeExecutionContext) -> NodeExecutionResult:
		result = await super().execute(context)

		try:
			inputs = {}
			for key, value in context.inputs.items():
				if key.startswith("input."):
					_, name, _ = key.split(".")
					inputs[name].append(value)

			mapping = context.inputs.get("mapping", {})
			for key, value in mapping.items():
				key  = str(key)
				name = f"output.{value}"
				result.outputs[name] = inputs[key]

		except Exception as e:
			result.success = False
			result.error   = str(e)
			
		return result


class WFMergeFlow(WFFlowType):
	async def execute(self, context: NodeExecutionContext) -> NodeExecutionResult:
		result = await super().execute(context)

		try:
			strategy = context.inputs.get("strategy", "first")

			inputs = []
			for key, value in context.inputs.items():
				if key.startswith("input."):
					inputs.append(value)

			if strategy == "first":
				merged = inputs[0] if inputs else None
			elif strategy == "last":
				merged = inputs[-1] if inputs else None
			elif strategy == "concat":
				if inputs and all(isinstance(i, str) for i in inputs):
					merged = "".join(inputs)
				elif inputs and all(isinstance(i, list) for i in inputs):
					merged = sum(inputs, [])
				else:
					merged = inputs
			elif strategy == "all":
				merged = inputs
			else:
				raise f"invalid strategy '{strategy}'"

			result.outputs["output"] = merged

		except Exception as e:
			result.success = False
			result.error   = str(e)

		return result


class WFTransformFlow(WFFlowType):
	async def execute(self, context: NodeExecutionContext) -> NodeExecutionResult:
		result = await super().execute(context)

		try:
			lang   = context.inputs.get("lang"   , DEFAULT_TRANSFORM_NODE_LANG  )
			script = context.inputs.get("script" , DEFAULT_TRANSFORM_NODE_SCRIPT)
			ctx    = context.inputs.get("context", {})
			input  = context.inputs.get("input"  , {})

			# if not isinstance(ctx, dict) or not isinstance(input, dict):
			# 	raise "Context and input must be dictionaries"

			if lang == "python":
				local_vars = {
					"variables" : context.variables,
					"context"   : ctx,
					"input"     : input,
					"output"    : None,
				}
				# exec(script, {"__builtins__": __builtins__}, local_vars)
				exec(script, None, local_vars)
				output = local_vars["output"]
			elif lang == "jinja2":
				template = Template(script)
				output = template.render(input=input, **context.variables)
			else:
				output = copy.deepcopy(input)

			result.outputs["output"] = output

		except Exception as e:
			result.success = False
			result.error   = str(e)

		return result


class WFUserInputFlow(WFFlowType):
	async def execute(self, context: NodeExecutionContext) -> NodeExecutionResult:
		result = await super().execute(context)
		result.outputs["content"] = {
			"awaiting_input": True,
		}
		return result


class WFToolFlow(WFFlowType):
	def __init__(self, config: Dict[str, Any], impl: Any = None, **kwargs):
		assert "ref" in kwargs, "WFToolNode requires 'ref' argument"
		super().__init__(config, impl, **kwargs)
		self.ref = kwargs["ref"]


	async def execute(self, context: NodeExecutionContext) -> NodeExecutionResult:
		result = await super().execute(context)

		try:
			args  = context.inputs.get("args" , {})
			input = context.inputs.get("input", {})

			if self.ref:
				tool_result = await self.ref(input, **args)
			else:
				tool_result = {
					"error": "No tool configured"
				}

			result.outputs["output"] = tool_result

		except Exception as e:
			result.success = False
			result.error   = str(e)

		return result


class WFAgentFlow(WFFlowType):
	def __init__(self, config: Dict[str, Any], impl: Any = None, **kwargs):
		assert "ref" in kwargs, "WFAgentNode requires 'ref' argument"
		super().__init__(config, impl, **kwargs)
		self.ref = kwargs["ref"]


	async def execute(self, context: NodeExecutionContext) -> NodeExecutionResult:
		result = await super().execute(context)

		try:
			request = context.inputs.get("request", "")
			if isinstance(request, dict):
				message = request.get("message") or request.get("text") or request.get("value") or request.get("data") or request.get("input") or str(request)
			else:
				message = str(request)

			if self.ref:
				response = await self.ref(message)
			else:
				response = {"error": "No agent configured"}

			result.outputs["response"] = {
				"request"  : request,
				"response" : response,
			}

		except Exception as e:
			result.success = False
			result.error   = str(e)

		return result


# =============================================================================
# LOOP FLOW NODES
# =============================================================================

class WFLoopStartFlow(WFFlowType):
	"""
	Loop Start node executor.

	The actual loop logic is handled by the engine. This node:
	1. Outputs the current iteration count
	2. Passes through the pin value

	The engine handles:
	- Condition evaluation
	- Iteration counting
	- Loop body reset
	"""
	async def execute(self, context: NodeExecutionContext) -> NodeExecutionResult:
		result = await super().execute(context)

		# Get iteration from engine-injected context
		iteration = context.variables.get("_loop_iteration", 0)

		result.outputs["iteration"] = iteration

		return result


class WFLoopEndFlow(WFFlowType):
	"""
	Loop End node executor.

	Signals the engine to check for loop continuation.
	The engine will:
	1. Find the paired LoopStart
	2. Re-evaluate the condition
	3. Reset loop body nodes if continuing
	"""
	async def execute(self, context: NodeExecutionContext) -> NodeExecutionResult:
		result = await super().execute(context)

		# Pass through input to output
		result.outputs["output"] = context.inputs.get("input")

		# Signal that this is a loop end (engine will handle the rest)
		result.outputs["_loop_signal"] = "end"

		return result


class WFForEachStartFlow(WFFlowType):
	"""
	For Each Start node executor.

	Iterates over a list of items. The engine manages:
	- Current index tracking
	- Item extraction
	- Loop continuation
	"""
	async def execute(self, context: NodeExecutionContext) -> NodeExecutionResult:
		result = await super().execute(context)

		# Get items from edge input or fall back to node's items field
		items = context.inputs.get("items")
		if items is None:
			items = getattr(self.config, 'items', None)
		if items is None:
			items = []

		# Get current index from engine-injected context
		index = context.variables.get("_loop_iteration", 0)

		# Get current item
		if isinstance(items, list) and 0 <= index < len(items):
			current = items[index]
		elif isinstance(items, dict):
			keys = list(items.keys())
			if 0 <= index < len(keys):
				current = items[keys[index]]
			else:
				current = None
		else:
			current = None

		result.outputs["current"] = current
		result.outputs["index"] = index

		# Store items count for engine to check loop end condition
		result.outputs["_items_count"] = len(items) if hasattr(items, '__len__') else 0

		return result


class WFForEachEndFlow(WFFlowType):
	"""
	For Each End node executor.

	Similar to LoopEnd but for ForEach loops.
	"""
	async def execute(self, context: NodeExecutionContext) -> NodeExecutionResult:
		result = await super().execute(context)

		result.outputs["output"] = context.inputs.get("input")
		result.outputs["_loop_signal"] = "for_each_end"

		return result


class WFBreakFlow(WFFlowType):
	"""
	Break node executor.

	Signals the engine to exit the current loop immediately.
	"""
	async def execute(self, context: NodeExecutionContext) -> NodeExecutionResult:
		result = await super().execute(context)

		# Signal break to the engine
		result.outputs["_loop_signal"] = "break"

		return result


class WFContinueFlow(WFFlowType):
	"""
	Continue node executor.

	Signals the engine to skip to the next iteration.
	"""
	async def execute(self, context: NodeExecutionContext) -> NodeExecutionResult:
		result = await super().execute(context)

		# Signal continue to the engine
		result.outputs["_loop_signal"] = "continue"

		return result


# =============================================================================
# END LOOP FLOW NODES
# =============================================================================


# =============================================================================
# EVENT/TRIGGER FLOW NODES
# =============================================================================

class WFGateFlow(WFFlowType):
	"""
	Gate/Accumulator node executor.

	Accumulates inputs and triggers when threshold or condition is met.
	State is scoped per-node using node_index to avoid conflicts between multiple gates.
	"""
	async def execute(self, context: NodeExecutionContext) -> NodeExecutionResult:
		result = await super().execute(context)

		# Get configuration
		threshold = context.inputs.get("threshold")
		if threshold is None:
			threshold = getattr(self.config, 'threshold', 1)

		condition = context.inputs.get("condition")
		if condition is None:
			condition = getattr(self.config, 'condition', None)

		reset_on_fire = context.inputs.get("reset_on_fire")
		if reset_on_fire is None:
			reset_on_fire = getattr(self.config, 'reset_on_fire', True)

		# Node-scoped state keys to avoid conflicts between multiple gates
		node_idx = context.node_index
		acc_key = f"_gate_{node_idx}_accumulated"
		count_key = f"_gate_{node_idx}_count"

		# Get accumulated state from context (node-scoped)
		accumulated = context.variables.get(acc_key, [])
		count = context.variables.get(count_key, 0)

		# Add current input to accumulator
		input_data = context.inputs.get("input")
		if input_data is not None:
			accumulated.append(input_data)
			count += 1

		# Update state in variables
		context.variables[acc_key] = accumulated
		context.variables[count_key] = count

		# Check if gate should fire
		should_fire = False

		if condition:
			# Evaluate custom condition
			try:
				local_vars = {
					"count": count,
					"threshold": threshold,
					"accumulated": accumulated,
					"input": input_data
				}
				should_fire = eval(condition, {"__builtins__": {}}, local_vars)
			except Exception:
				should_fire = False
		else:
			# Simple threshold check
			should_fire = count >= threshold

		result.outputs["count"] = count
		result.outputs["accumulated"] = accumulated.copy()
		result.outputs["triggered"] = should_fire

		if should_fire:
			# Gate fires - pass through accumulated data
			result.outputs["output"] = accumulated.copy() if len(accumulated) > 1 else (accumulated[0] if accumulated else None)

			if reset_on_fire:
				# Actually reset the state variables for next accumulation cycle
				context.variables[acc_key] = []
				context.variables[count_key] = 0
				result.outputs["_gate_reset"] = True
		else:
			# Gate holds - don't set output but still complete
			# This allows the workflow to continue (loop can iterate)
			# Downstream nodes should check 'triggered' output to decide whether to process
			result.outputs["output"] = None

		return result


class WFDelayFlow(WFFlowType):
	"""
	Delay node executor.

	Simple pause - waits for duration then passes through input.
	Uses node-scoped resume flag to properly handle loop iterations.
	"""
	async def execute(self, context: NodeExecutionContext) -> NodeExecutionResult:
		result = await super().execute(context)

		# Get duration from node or inputs
		duration_ms = context.inputs.get("duration_ms")
		if duration_ms is None:
			duration_ms = getattr(self.config, 'duration_ms', 1000)

		# Node-scoped resume key
		node_idx = context.node_index
		resume_key = f"_delay_{node_idx}_resume"

		# Check if this is a resume after waiting
		is_resume = context.variables.get(resume_key, False)

		if is_resume:
			# Resume after delay - pass through input and clear the flag
			result.outputs["output"] = context.inputs.get("input")
			# Clear the flag so next loop iteration will delay again
			context.variables[resume_key] = False
		else:
			# First execution - signal to wait
			result.outputs["output"] = context.inputs.get("input")
			result.wait_signal = {
				"wait_type": "timer",
				"duration_ms": duration_ms,
				"count": 0,
				"max_count": 1  # Only trigger once
			}

		return result


# =============================================================================
# EVENT SOURCE NODES
# =============================================================================

def _src_get(ctx, key, config, default=None):
	"""Get input value with config fallback for source flow executors."""
	v = ctx.inputs.get(key)
	if v is None:
		v = getattr(config, key, default)
	return v


class WFTimerSourceFlow(WFFlowType):
	"""Timer Source node executor - registers a timer event source."""
	async def execute(self, context: NodeExecutionContext) -> NodeExecutionResult:
		result = await super().execute(context)
		try:
			source_id    = _src_get(context, "source_id", self.config) or f"wf_timer_{context.node_index}"
			name         = _src_get(context, "name", self.config) or source_id
			interval_ms  = _src_get(context, "interval_ms", self.config, 1000)
			max_triggers = _src_get(context, "max_triggers", self.config, -1)
			immediate    = _src_get(context, "immediate", self.config, False)

			registry = get_event_registry()
			config = TimerSourceConfig(
				id=source_id, name=name, interval_ms=interval_ms,
				max_triggers=max_triggers, immediate=immediate
			)
			if registry.get(source_id):
				await registry.update(source_id, config)
			else:
				await registry.register(config)

			result.outputs["registered_id"] = source_id
		except Exception as e:
			result.success = False
			result.error = str(e)
		return result


class WFFSWatchSourceFlow(WFFlowType):
	"""FS Watch Source node executor - registers a filesystem watcher event source."""
	async def execute(self, context: NodeExecutionContext) -> NodeExecutionResult:
		result = await super().execute(context)
		try:
			source_id   = _src_get(context, "source_id", self.config) or f"wf_fswatch_{context.node_index}"
			name        = _src_get(context, "name", self.config) or source_id
			path        = _src_get(context, "path", self.config, ".")
			recursive   = _src_get(context, "recursive", self.config, True)
			patterns    = _src_get(context, "patterns", self.config, "*")
			events      = _src_get(context, "events", self.config, "created,modified,deleted,moved")
			debounce_ms = _src_get(context, "debounce_ms", self.config, 100)

			# Split comma-separated strings into lists
			if isinstance(patterns, str):
				patterns = [p.strip() for p in patterns.split(",") if p.strip()]
			if isinstance(events, str):
				events = [e.strip() for e in events.split(",") if e.strip()]

			registry = get_event_registry()
			config = FSWatchSourceConfig(
				id=source_id, name=name, path=path, recursive=recursive,
				patterns=patterns, events=events, debounce_ms=debounce_ms
			)
			if registry.get(source_id):
				await registry.update(source_id, config)
			else:
				await registry.register(config)

			result.outputs["registered_id"] = source_id
		except Exception as e:
			result.success = False
			result.error = str(e)
		return result


class WFWebhookSourceFlow(WFFlowType):
	"""Webhook Source node executor - registers a webhook event source."""
	async def execute(self, context: NodeExecutionContext) -> NodeExecutionResult:
		result = await super().execute(context)
		try:
			source_id = _src_get(context, "source_id", self.config) or f"wf_webhook_{context.node_index}"
			name      = _src_get(context, "name", self.config) or source_id
			endpoint  = _src_get(context, "endpoint", self.config, "/hook/default")
			methods   = _src_get(context, "methods", self.config, "POST")
			secret    = _src_get(context, "secret", self.config)

			# Split comma-separated string into list
			if isinstance(methods, str):
				methods = [m.strip() for m in methods.split(",") if m.strip()]

			registry = get_event_registry()
			config = WebhookSourceConfig(
				id=source_id, name=name, endpoint=endpoint,
				methods=methods, secret=secret
			)
			if registry.get(source_id):
				await registry.update(source_id, config)
			else:
				await registry.register(config)

			result.outputs["registered_id"] = source_id
		except Exception as e:
			result.success = False
			result.error = str(e)
		return result


class WFBrowserSourceFlow(WFFlowType):
	"""Browser Source node executor - registers a browser media event source."""
	async def execute(self, context: NodeExecutionContext) -> NodeExecutionResult:
		result = await super().execute(context)
		try:
			source_id    = _src_get(context, "source_id", self.config) or f"wf_browser_{context.node_index}"
			name         = _src_get(context, "name", self.config) or source_id
			device_type  = _src_get(context, "device_type", self.config, "webcam")
			mode         = _src_get(context, "mode", self.config, "event")
			interval_ms  = _src_get(context, "interval_ms", self.config, 1000)
			resolution   = _src_get(context, "resolution", self.config)
			audio_format = _src_get(context, "audio_format", self.config)

			registry = get_event_registry()
			config = BrowserSourceConfig(
				id=source_id, name=name, device_type=device_type,
				mode=mode, interval_ms=interval_ms,
				resolution=resolution, audio_format=audio_format
			)
			if registry.get(source_id):
				await registry.update(source_id, config)
			else:
				await registry.register(config)

			result.outputs["registered_id"] = source_id
		except Exception as e:
			result.success = False
			result.error = str(e)
		return result


# =============================================================================
# EXTERNAL EVENT LISTENER
# =============================================================================

class WFEventListenerFlow(WFFlowType):
	"""
	Event Listener node executor.

	Waits for events from external event sources. The engine handles the actual
	subscription and event waiting; this executor just signals the wait and
	processes the received event.
	"""
	async def execute(self, context: NodeExecutionContext) -> NodeExecutionResult:
		result = await super().execute(context)

		# Gather sources from MULTI_INPUT dotted keys (sources.timer_1, sources.timer_2, ...)
		sources = []
		for key, value in context.inputs.items():
			if key.startswith("sources.") and isinstance(value, str) and value:
				sources.append(value)
		if not sources:
			src = context.inputs.get("sources")
			if isinstance(src, dict):    sources = [v for v in src.values() if isinstance(v, str) and v]
			elif isinstance(src, list):  sources = src
			elif isinstance(src, str) and src: sources = [src]
		if not sources:
			src = getattr(self.config, 'sources', None)
			if isinstance(src, dict):    sources = [v for v in src.values() if isinstance(v, str) and v]
			elif isinstance(src, list):  sources = src
			elif isinstance(src, str) and src: sources = [src]
			else: sources = []

		mode = context.inputs.get("mode")
		if not mode:
			mode = getattr(self.config, 'mode', 'any')

		timeout_ms = context.inputs.get("timeout_ms")
		if timeout_ms is None:
			timeout_ms = getattr(self.config, 'timeout_ms', None)

		# Node-scoped keys for tracking state
		node_idx = context.node_index
		resume_key = f"_event_listener_{node_idx}_resume"
		event_key = f"_event_listener_{node_idx}_event"
		events_key = f"_event_listener_{node_idx}_events"
		source_key = f"_event_listener_{node_idx}_source"
		timeout_key = f"_event_listener_{node_idx}_timeout"

		# Check if this is a resume after receiving event
		is_resume = context.variables.get(resume_key, False)

		if is_resume:
			# Event received - get the data
			event_data = context.variables.get(event_key)
			source_id = context.variables.get(source_key)
			all_events = context.variables.get(events_key, {})
			timed_out = context.variables.get(timeout_key, False)

			result.outputs["event"] = event_data
			result.outputs["source_id"] = source_id
			result.outputs["events"] = all_events if all_events else None
			result.outputs["timed_out"] = timed_out

			# Clear state for next iteration (if in a loop)
			context.variables[resume_key] = False
			context.variables[event_key] = None
			context.variables[events_key] = {}
			context.variables[source_key] = None
			context.variables[timeout_key] = False
		else:
			# First execution - signal to wait for events
			result.wait_signal = {
				"wait_type": "event_listener",
				"sources": sources,
				"mode": mode,
				"timeout_ms": timeout_ms,
			}

		return result


# =============================================================================
# END EVENT/TRIGGER FLOW NODES
# =============================================================================


class WFInteractiveType(WFBaseType):
	pass


class WFToolCall(WFInteractiveType):
	pass


class WFAgentChat(WFInteractiveType):
	pass


class WFWorkflowOptions(WFComponentType):
	pass


class WFWorkflow(WFComponentType):
	pass


# =============================================================================
# ML / STREAM INFERENCE NODES
# =============================================================================

# Cached MediaPipe detectors keyed by (model_complexity, min_confidence)
_POSE_DETECTORS: Dict[tuple, Any] = {}


def _get_pose_detector(model_complexity: int, min_confidence: float) -> Optional[Any]:
	"""Return a cached MediaPipe Pose detector, creating one if needed."""
	key = (model_complexity, round(min_confidence, 2))
	if key not in _POSE_DETECTORS:
		try:
			import mediapipe as mp
			_POSE_DETECTORS[key] = mp.solutions.pose.Pose(
				static_image_mode         = False,
				model_complexity          = model_complexity,
				min_detection_confidence  = min_confidence,
				min_tracking_confidence   = min_confidence,
			)
		except Exception:
			return None
	return _POSE_DETECTORS[key]


class WFPoseDetectorFlow(WFFlowType):
	"""Runs MediaPipe Pose on a base64-encoded JPEG frame received from a Browser Source."""

	async def execute(self, context: NodeExecutionContext) -> NodeExecutionResult:
		result = await super().execute(context)
		try:
			frame          = context.inputs.get("frame")
			model_name     = context.inputs.get("model", "lite")
			min_confidence = float(context.inputs.get("min_confidence", 0.5))
			complexity     = {"lite": 0, "full": 1, "heavy": 2}.get(model_name, 0)

			# Empty outputs for no-frame case
			result.outputs["keypoints"]  = None
			result.outputs["landmarks"]  = []
			result.outputs["pose_found"] = False

			if frame is None:
				return result

			# Import optional deps
			try:
				import base64 as _b64
				import io
				import numpy as np
				from PIL import Image
			except ImportError as e:
				result.success = False
				result.error   = f"Missing dependency: {e}. Install: pip install mediapipe Pillow numpy"
				return result

			# Decode base64 JPEG → numpy RGB array
			if isinstance(frame, str):
				if "," in frame:         # data-URL prefix
					frame = frame.split(",", 1)[1]
				img_bytes = _b64.b64decode(frame)
			elif isinstance(frame, bytes):
				img_bytes = frame
			else:
				return result

			img       = Image.open(io.BytesIO(img_bytes)).convert("RGB")
			img_array = np.array(img)
			h, w      = img_array.shape[:2]

			# Run detection
			detector = _get_pose_detector(complexity, min_confidence)
			if detector is None:
				result.success = False
				result.error   = "mediapipe not installed. Run: pip install mediapipe"
				return result

			detection = detector.process(img_array)

			if detection.pose_landmarks:
				landmarks = [
					{"x": lm.x, "y": lm.y, "z": lm.z, "visibility": lm.visibility}
					for lm in detection.pose_landmarks.landmark
				]
				result.outputs["keypoints"]  = {"landmarks": landmarks, "width": w, "height": h, "model": model_name}
				result.outputs["landmarks"]  = landmarks
				result.outputs["pose_found"] = True

		except Exception as e:
			result.success = False
			result.error   = str(e)

		return result


class WFStreamDisplayFlow(WFFlowType):
	"""Pushes overlay render data (pose keypoints, text, etc.) to the browser via event bus."""

	async def execute(self, context: NodeExecutionContext) -> NodeExecutionResult:
		result = await super().execute(context)
		try:
			from event_bus import get_event_bus, EventType as ET

			source_id   = context.inputs.get("source_id")
			data        = context.inputs.get("data")
			render_type = context.inputs.get("render_type", "pose")

			bus = get_event_bus()
			await bus.emit(
				event_type = ET.STREAM_DISPLAY,
				data = {
					"source_id"   : source_id,
					"render_type" : render_type,
					"payload"     : data,
				}
			)
			result.outputs["done"] = True

		except Exception as e:
			result.success = False
			result.error   = str(e)

		return result


# =============================================================================
# END ML / STREAM INFERENCE NODES
# =============================================================================


class ImplementedBackend(BaseModel):
	handles         : List[Any]
	run_tool        : Callable
	run_agent       : Callable
	get_agent_app   : Callable
	add_contents    : Callable
	remove_contents : Callable
	list_contents   : Callable


_NODE_TYPES = {
	"native_boolean"           : WFNativeBoolean,
	"native_integer"           : WFNativeInteger,
	"native_real"              : WFNativeReal,
	"native_string"            : WFNativeString,
	"native_list"              : WFNativeList,
	"native_dictionary"        : WFNativeDictionary,

	"data_tensor"              : WFDataTensor,

	"backend_config"           : WFBackendConfig,
	"model_config"             : WFModelConfig,
	"embedding_config"         : WFEmbeddingConfig,
	"content_db_config"        : WFContentDBConfig,
	"vector_db_config"         : WFIndexDBConfig,
	"memory_manager_config"    : WFMemoryManagerConfig,
	"session_manager_config"   : WFSessionManagerConfig,
	"knowledge_manager_config" : WFKnowledgeManagerConfig,
	"tool_config"              : WFToolConfig,
	"agent_options_config"     : WFAgentOptionsConfig,
	"agent_config"             : WFAgentConfig,

	"start_flow"               : WFStartFlow,
	"end_flow"                 : WFEndFlow,
	"sink_flow"                : WFSinkFlow,
	"preview_flow"             : WFPreviewFlow,
	"route_flow"               : WFRouteFlow,
	"combine_flow"             : WFCombineFlow,
	"merge_flow"               : WFMergeFlow,
	"transform_flow"           : WFTransformFlow,
	"user_input_flow"          : WFUserInputFlow,
	"tool_flow"                : WFToolFlow,
	"agent_flow"               : WFAgentFlow,

	# Loop nodes
	"loop_start_flow"          : WFLoopStartFlow,
	"loop_end_flow"            : WFLoopEndFlow,
	"for_each_start_flow"      : WFForEachStartFlow,
	"for_each_end_flow"        : WFForEachEndFlow,
	"break_flow"               : WFBreakFlow,
	"continue_flow"            : WFContinueFlow,

	# Event/Trigger nodes
	"gate_flow"                : WFGateFlow,
	"delay_flow"               : WFDelayFlow,
	"event_listener_flow"      : WFEventListenerFlow,

	# Event Source nodes
	"timer_source_flow"        : WFTimerSourceFlow,
	"fswatch_source_flow"      : WFFSWatchSourceFlow,
	"webhook_source_flow"      : WFWebhookSourceFlow,
	"browser_source_flow"      : WFBrowserSourceFlow,

	# ML / Stream nodes
	"pose_detector_flow"       : WFPoseDetectorFlow,
	"stream_display_flow"      : WFStreamDisplayFlow,

	# Interactive nodes
	"tool_call"                : WFToolCall,
	"agent_chat"               : WFAgentChat,
}


def create_node(node: BaseType, impl: Any = None, **kwargs) -> WFBaseType:
	node_class = _NODE_TYPES.get(node.type, WFBaseType)
	return node_class(node, impl, **kwargs)
