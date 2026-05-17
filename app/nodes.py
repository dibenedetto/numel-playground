# nodes

import copy
import json
import os


from   jinja2   import Template
from   pathlib  import Path
from   pydantic import BaseModel
from   typing   import Any, Callable, Dict, List, Optional


from   events   import get_event_registry, TimerSourceConfig, FSWatchSourceConfig, WebhookSourceConfig, BrowserSourceConfig, ChannelSourceConfig
from   agent_endpoint_runtime import normalize_agent_endpoint_config
from   knowledge_runtime import normalize_knowledge_inputs
from   schema   import DEFAULT_TRANSFORM_NODE_LANG, DEFAULT_TRANSFORM_NODE_SCRIPT, BaseType
from   utils	import log_print


class NodeExecutionContext:
	def __init__(self):
		self.inputs           : Dict[str, Any] = {}
		self.variables        : Dict[str, Any] = {}
		self.node_index       : int            = 0
		self.node_config      : Dict[str, Any] = {}
		self.event_bus        : Any            = None  # set by engine for nodes that publish events
		self.channel_registry : Any            = None  # set by engine for channel_send_flow


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


class WFHistoryManagerConfig(WFConfigType):
	pass


class WFMemoryManagerConfig(WFConfigType):
	pass


class WFSessionManagerConfig(WFConfigType):
	pass


class WFKnowledgeManagerConfig(WFConfigType):
	pass


class WFToolConfig(WFConfigType):
	pass


class WFToolkitConfig(WFConfigType):
	pass


class WFSkillConfig(WFConfigType):
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
	async def execute(self, context: NodeExecutionContext) -> NodeExecutionResult:
		result = await super().execute(context)
		result.outputs["flow_out"] = context.inputs.get("flow_in")
		return result


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
			args = context.inputs.get("args", {})

			if self.ref:
				tool_result = await self.ref(**args)
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
		self.ref               = kwargs["ref"]
		self._proactive_alias  = None   # populated lazily on first gated call


	async def execute(self, context: NodeExecutionContext) -> NodeExecutionResult:
		result = await super().execute(context)

		try:
			request = context.inputs.get("request", "")
			if isinstance(request, dict):
				message = request.get("message") or request.get("text") or request.get("value") or request.get("data") or request.get("input") or str(request)
			else:
				message = str(request)

			image = context.inputs.get("image")

			if self.ref is None:
				response = {"error": "No agent configured"}
			else:
				response = await self._run_via_proactive_gate(context, message, image)

			result.outputs["response"] = {
				"request"  : request,
				"response" : response,
			}

		except Exception as e:
			result.success = False
			result.error   = str(e)

		return result


	async def _run_via_proactive_gate(self, context: NodeExecutionContext, message: str, image: Optional[str]) -> Any:
		"""Route an agent_flow invocation through proactive.agents.call_agent
		so the Substrate Adversarial → Alignment → Privacy chain wraps the
		LLM call. Auto-registers a per-node Capability on first invocation."""
		from proactive import agents as _agents

		if self._proactive_alias is None:
			alias = f"node_{context.node_index}"
			handler = _make_agent_flow_handler(self.ref)
			_agents.register_agent_handler(
				alias,
				handler,
				kind        = _agents.KIND_LOCAL,
				description = f"agent_flow at workflow node {context.node_index}",
			)
			self._proactive_alias = alias

		response = _agents.call_agent(
			self._proactive_alias,
			message,
			image = image,
		)
		# call_agent returns the mcp.call_tool envelope — surface the
		# inner result on success so the workflow sees the same shape it
		# used to. On a gate veto / handler error, surface the envelope
		# verbatim so the operator can inspect what happened.
		if isinstance(response, dict) and response.get("ok") is True:
			return response.get("result")
		return response


def _make_agent_flow_handler(ref: Any) -> Callable[[Dict[str, Any]], Any]:
	"""Wrap a backend `run_agent` partial into a proactive.agents handler.

	The handler unpacks the args dict (`{request, image?}`) and awaits
	the underlying ref. Returning the raw coroutine lets _wrap_handler
	in proactive.agents detect it and run it on a fresh loop."""
	async def _handler(args: Dict[str, Any]) -> Any:
		request = args.get("request", "")
		image   = args.get("image")
		if image:
			return await ref(request, image=image)
		return await ref(request)
	return _handler


class WFAgentEndpointFlow(WFFlowType):
	def __init__(self, config: Dict[str, Any], impl: Any = None, **kwargs):
		assert "ref" in kwargs, "WFAgentEndpointFlow requires 'ref' argument"
		super().__init__(config, impl, **kwargs)
		self.ref                  = kwargs["ref"]
		self._proactive_aliases   = {}   # mode -> registered alias (cache)

	async def execute(self, context: NodeExecutionContext) -> NodeExecutionResult:
		result = await super().execute(context)
		result.outputs["output"] = None
		result.outputs["response"] = None
		result.outputs["status"] = None
		result.outputs["task_id"] = None
		result.outputs["endpoint_kind"] = None
		result.outputs["endpoint_name"] = None
		result.outputs["error"] = None

		try:
			prompt_value = context.inputs.get("prompt")
			if prompt_value is None:
				prompt_value = context.inputs.get("input")
			if isinstance(prompt_value, dict):
				prompt = (
					prompt_value.get("prompt")
					or prompt_value.get("message")
					or prompt_value.get("text")
					or prompt_value.get("value")
					or prompt_value.get("input")
					or json.dumps(prompt_value, ensure_ascii=False)
				)
			else:
				prompt = "" if prompt_value is None else str(prompt_value)
			if not prompt.strip():
				raise ValueError("prompt is required")

			mode = str(context.inputs.get("mode") or "consult").strip().lower() or "consult"
			config_value = context.inputs.get("config") or getattr(self.config, "config", None) or self.config
			endpoint_config = normalize_agent_endpoint_config(endpoint=config_value)

			extra_args = {
				"mode":                 mode,
				"session_id":           context.inputs.get("session_id"),
				"source_deployment_id": context.inputs.get("source_deployment_id"),
				"sender_name":          context.inputs.get("sender_name"),
				"user_id":              context.inputs.get("user_id"),
			}

			endpoint_result = await self._run_via_proactive_gate(context, prompt, mode, extra_args)

			error_text = str(endpoint_result.get("error") or "").strip() or None
			status_value = str(endpoint_result.get("status") or ("error" if error_text else "ok"))
			result.outputs["output"] = endpoint_result
			result.outputs["response"] = endpoint_result.get("response")
			result.outputs["status"] = status_value
			result.outputs["task_id"] = endpoint_result.get("task_id")
			result.outputs["endpoint_kind"] = endpoint_result.get("kind") or endpoint_config.kind
			result.outputs["endpoint_name"] = endpoint_result.get("name") or endpoint_config.name or endpoint_config.target
			result.outputs["error"] = error_text
			if error_text:
				result.success = False
				result.error = error_text
		except Exception as e:
			result.success = False
			result.error = str(e)
			result.outputs["error"] = str(e)

		return result


	async def _run_via_proactive_gate(self, context: NodeExecutionContext, prompt: str, mode: str, extra_args: Dict[str, Any]) -> Dict[str, Any]:
		"""Route an endpoint invocation through proactive.agents.call_agent.

		Each (node, mode) pair gets its own Capability so the Governor sees
		mode-specific scopes — `consult` calls don't carry the
		`delegates-authority` scope that `delegate` calls do, and `notify`
		picks up `affects-third-party`. Constitution rules can target a
		specific mode by full cap name (`agent.endpoint.node_3.delegate`)."""
		from proactive import agents as _agents

		alias = self._proactive_aliases.get(mode)
		if alias is None:
			alias = f"node_{context.node_index}.{mode}"
			scopes = _scopes_for_endpoint_mode(mode)
			handler = _make_endpoint_handler(self.ref)
			_agents.register_agent_handler(
				alias,
				handler,
				kind        = _agents.KIND_ENDPOINT,
				scopes      = scopes,
				description = f"agent_endpoint_flow at node {context.node_index} (mode={mode})",
			)
			self._proactive_aliases[mode] = alias

		response = _agents.call_agent(
			alias,
			prompt,
			kind       = _agents.KIND_ENDPOINT,
			extra_args = extra_args,
		)
		# Surface the inner result on success so the workflow sees the
		# same dict shape it used to. On gate veto / handler error,
		# return a dict that the surrounding error-handling can read.
		if isinstance(response, dict) and response.get("ok") is True:
			return response.get("result") or {}
		# Translate the gate-chain envelope into the endpoint result shape.
		return {
			"status":   "error",
			"error":    response.get("error") if isinstance(response, dict) else "gate_chain_failed",
			"verdicts": (response or {}).get("verdicts") if isinstance(response, dict) else None,
		}


_ENDPOINT_BASE_SCOPES   = ["external-network"]
_ENDPOINT_MODE_SCOPES = {
	"consult":  [],
	"delegate": ["delegates-authority"],
	"handoff":  ["delegates-authority", "non-reversible"],
	"notify":   ["affects-third-party"],
}


def _scopes_for_endpoint_mode(mode: str) -> List[str]:
	"""Mode-derived scope set so the Governor can apply different policy
	to consult vs delegate vs notify even though they share one underlying
	endpoint configuration."""
	extra = _ENDPOINT_MODE_SCOPES.get(mode, _ENDPOINT_MODE_SCOPES["consult"])
	return list(_ENDPOINT_BASE_SCOPES) + list(extra)


def _make_endpoint_handler(ref: Any) -> Callable[[Dict[str, Any]], Any]:
	"""Wrap the engine's `_run_agent_endpoint` partial into a proactive.agents handler."""
	async def _handler(args: Dict[str, Any]) -> Dict[str, Any]:
		return await ref(
			mode                 = args.get("mode") or "consult",
			prompt               = args.get("request") or "",
			session_id           = args.get("session_id"),
			source_deployment_id = args.get("source_deployment_id"),
			sender_name          = args.get("sender_name"),
			user_id              = args.get("user_id"),
		)
	return _handler


class WFKnowledgeIngestFlow(WFFlowType):
	def __init__(self, config: Dict[str, Any], impl: Any = None, **kwargs):
		assert "ref" in kwargs, "WFKnowledgeIngestFlow requires 'ref' argument"
		super().__init__(config, impl, **kwargs)
		self.ref = kwargs["ref"]

	async def execute(self, context: NodeExecutionContext) -> NodeExecutionResult:
		result = await super().execute(context)
		result.outputs["output"] = None
		result.outputs["ids"] = []
		result.outputs["count"] = 0
		result.outputs["added"] = []

		try:
			items = normalize_knowledge_inputs(
				context.inputs.get("input"),
				filename=context.inputs.get("filename"),
				metadata=context.inputs.get("metadata"),
			)
			if not items:
				payload = {"ids": [], "count": 0, "items": []}
				result.outputs["output"] = payload
				return result

			ids = await self.ref(items)
			added = []
			for knowledge_id, item in zip(ids, items):
				added.append(
					{
						"id": knowledge_id,
						"filename": item.get("filename"),
						"metadata": item.get("metadata") or {},
					}
				)

			payload = {"ids": ids, "count": len(ids), "items": added}
			result.outputs["output"] = payload
			result.outputs["ids"] = ids
			result.outputs["count"] = len(ids)
			result.outputs["added"] = added
		except Exception as e:
			result.success = False
			result.error = str(e)

		return result


class WFKnowledgeSearchFlow(WFFlowType):
	def __init__(self, config: Dict[str, Any], impl: Any = None, **kwargs):
		assert "ref" in kwargs, "WFKnowledgeSearchFlow requires 'ref' argument"
		super().__init__(config, impl, **kwargs)
		self.ref = kwargs["ref"]

	async def execute(self, context: NodeExecutionContext) -> NodeExecutionResult:
		result = await super().execute(context)
		result.outputs["output"] = []
		result.outputs["results"] = []
		result.outputs["count"] = 0

		try:
			query_value = context.inputs.get("query")
			if query_value is None:
				query_value = context.inputs.get("input")
			if isinstance(query_value, dict):
				query = (
					query_value.get("query")
					or query_value.get("text")
					or query_value.get("message")
					or query_value.get("value")
					or query_value.get("input")
					or json.dumps(query_value, ensure_ascii=False)
				)
			else:
				query = "" if query_value is None else str(query_value)
			if not query.strip():
				raise ValueError("query is required")

			filters = context.inputs.get("filters")
			if isinstance(filters, str):
				try:
					filters = json.loads(filters)
				except Exception:
					pass

			results = await self.ref(
				query=query,
				max_results=int(context.inputs.get("max_results", 5)),
				filters=filters,
				search_type=context.inputs.get("search_type"),
			)
			result.outputs["output"] = results
			result.outputs["results"] = results
			result.outputs["count"] = len(results or [])
		except Exception as e:
			result.success = False
			result.error = str(e)

		return result


# =============================================================================
# PROACTIVE FLOW NODES
# Thin executors for the Substrate stages — each one wraps the corresponding
# function in app/proactive/*.py so workflows compose Substrate primitives as
# first-class graph nodes instead of transform_flow scripts.
# =============================================================================

def _ensure_proactive_on_path() -> None:
	"""Make `import proactive.*` work regardless of how the engine launched."""
	try:
		import proactive  # noqa: F401
	except ImportError:
		import sys
		app_dir = os.path.dirname(os.path.abspath(__file__))
		if app_dir not in sys.path:
			sys.path.insert(0, app_dir)


def _coerce_envelope(input_value: Any) -> Dict[str, Any]:
	"""Coerce whatever arrived on `input` into a dict envelope. transform_flow
	users were doing this inline; centralising lets the Substrate nodes accept
	non-dict upstreams gracefully."""
	if isinstance(input_value, dict):
		return dict(input_value)
	return {"raw": input_value}


class _WFProactiveMiddlewareBase(WFFlowType):
	"""Shared scaffolding for the three Middleware gates — they're all the same
	shape (envelope in → envelope out) so factor it once."""
	_gate_attr: str = ""

	async def execute(self, context: NodeExecutionContext) -> NodeExecutionResult:
		result = await super().execute(context)
		try:
			_ensure_proactive_on_path()
			from proactive import middleware as _middleware
			env  = _coerce_envelope(context.inputs.get("input"))
			gate = getattr(_middleware, self._gate_attr)
			result.outputs["output"] = gate(env)
		except Exception as e:
			result.success = False
			result.error   = str(e)
		return result


class WFVeracityGateFlow(_WFProactiveMiddlewareBase):
	_gate_attr = "veracity_gate"


class WFPrivacyGateFlow(_WFProactiveMiddlewareBase):
	_gate_attr = "privacy_gate"


class WFAdversarialGateFlow(_WFProactiveMiddlewareBase):
	_gate_attr = "adversarial_gate"


class WFWorldModelWriteFlow(WFFlowType):
	"""Substrate §3.2 — append the envelope's observation under
	`<namespace>.<rev>` in `variables["world_model"]`. Maintains a per-namespace
	`__index__` list so revisions are dense and ordered."""

	async def execute(self, context: NodeExecutionContext) -> NodeExecutionResult:
		import time as _time
		result = await super().execute(context)
		try:
			env       = _coerce_envelope(context.inputs.get("input"))
			namespace = str(context.inputs.get("namespace") or "core.observations.email")
			wm        = context.variables.setdefault("world_model", {})
			index_key = f"{namespace}.__index__"
			index     = wm.setdefault(index_key, [])
			rev       = len(index) + 1
			path      = f"{namespace}.{rev}"
			wm[path]  = {
				"observation":       env.get("observation"),
				"untrusted_content": env.get("untrusted_content"),
				"confidence":        env.get("confidence"),
				"source":            env.get("source"),
				"revision":          rev,
				"ts":                _time.time(),
			}
			index.append(path)
			env["world_model_write"] = {"path": path, "revision": rev}
			result.outputs["output"] = env
		except Exception as e:
			result.success = False
			result.error   = str(e)
		return result


class WFLedgerAppendFlow(WFFlowType):
	"""Substrate §6.1 — append an audit entry to `variables["ledger"]`. The
	entry is auto-populated from the envelope so workflows don't have to
	enumerate the fields by hand."""

	async def execute(self, context: NodeExecutionContext) -> NodeExecutionResult:
		import time as _time
		result = await super().execute(context)
		try:
			env              = _coerce_envelope(context.inputs.get("input"))
			topic            = str(context.inputs.get("topic")            or "core.ledger")
			expected_outcome = context.inputs.get("expected_outcome")
			gate_on_intent   = bool(context.inputs.get("gate_on_intent")  or False)

			if gate_on_intent and not env.get("intent"):
				result.outputs["output"] = env
				return result

			ledger = context.variables.setdefault("ledger", [])
			entry = {
				"id":             f"led_{len(ledger) + 1}",
				"ts":             _time.time(),
				"correlation_id": env.get("correlation_id"),
				"trigger":        {"topic": topic},
				"provenance":     env.get("provenance", []),
			}
			# Carry over whichever envelope fields are populated; absent
			# fields stay absent rather than landing as `None`.
			for key in (
				"observation", "world_model_write",
				"intent", "resolved_capability", "relevant_goals",
				"governor_verdict", "motor_action", "motor_status",
				"social_consent_request",
			):
				if env.get(key) is not None:
					entry[key] = env[key]
			if expected_outcome is not None:
				entry["expected_outcome"] = str(expected_outcome)
			# `actual_outcome` defaults from motor_status (action entries) or
			# the literal "recorded" (observation entries).
			entry["actual_outcome"] = env.get("motor_status") or "recorded"
			ledger.append(entry)
			result.outputs["output"] = env
		except Exception as e:
			result.success = False
			result.error   = str(e)
		return result


class WFGoalMatchFlow(WFFlowType):
	"""Substrate §3.3 — lazy-seed a Standing Goal in `variables["goals"]` and
	emit the list of currently-active goal ids on the envelope."""

	async def execute(self, context: NodeExecutionContext) -> NodeExecutionResult:
		import time as _time
		result = await super().execute(context)
		try:
			env   = _coerce_envelope(context.inputs.get("input"))
			gid   = str(context.inputs.get("standing_goal_id")    or "core.demo.standing")
			title = str(context.inputs.get("standing_goal_title") or "Stay aware of inbound signals and route them safely")
			goals = context.variables.setdefault("goals", {})
			if gid not in goals:
				goals[gid] = {
					"id":         gid,
					"tier":       "Standing Goal",
					"title":      title,
					"lifecycle":  "active",
					"created_at": _time.time(),
				}
			active = [g["id"] for g in goals.values() if g.get("lifecycle") == "active"]
			env["relevant_goals"] = active
			env.setdefault("provenance", []).append({"stage": "goal_hierarchy", "matched": len(active)})
			result.outputs["output"] = env
		except Exception as e:
			result.success = False
			result.error   = str(e)
		return result


_BUILTIN_CAPS_SEED = {
	"core.notify": {
		"name": "core.notify", "purpose": "Surface a UI notification",
		"scopes": ["read-only"], "latency_tier": "interactive", "cost_estimate": 0.0,
	},
	"core.send_email": {
		"name": "core.send_email", "purpose": "Send an outbound email",
		"scopes": ["write", "external-network", "affects-third-party"],
		"latency_tier": "responsive", "cost_estimate": 0.001,
	},
	"core.transfer_funds": {
		"name": "core.transfer_funds", "purpose": "Initiate a money transfer",
		"scopes": ["spends-money", "write", "affects-third-party"],
		"latency_tier": "responsive", "cost_estimate": 0.5,
	},
}


class WFCapabilityLookupFlow(WFFlowType):
	"""Substrate §3.4 — look up `intent.capability` in `variables["capabilities"]`
	(lazy-seeded with the built-in registry), merge scopes, emit
	`resolved_capability`."""

	async def execute(self, context: NodeExecutionContext) -> NodeExecutionResult:
		result = await super().execute(context)
		try:
			env  = _coerce_envelope(context.inputs.get("input"))
			caps = context.variables.setdefault("capabilities", {})
			if not caps:
				for name, cap in _BUILTIN_CAPS_SEED.items():
					caps[name] = dict(cap)
			intent   = env.get("intent") or {}
			cap_name = intent.get("capability")
			prov     = env.setdefault("provenance", [])
			if cap_name and cap_name in caps:
				cap = caps[cap_name]
				env["resolved_capability"] = {
					"name":         cap_name,
					"scopes":       cap["scopes"],
					"latency_tier": cap["latency_tier"],
				}
				env["scopes"] = sorted(set(list(env.get("scopes", [])) + list(cap["scopes"])))
				prov.append({"stage": "capability_registry", "resolved": cap_name})
			else:
				prov.append({"stage": "capability_registry", "resolved": None})
			result.outputs["output"] = env
		except Exception as e:
			result.success = False
			result.error   = str(e)
		return result


class WFGovernorDecideFlow(WFFlowType):
	"""Substrate §3.5 — Governor verdict over scopes + confidence.

	Logic lives in `proactive.governor.gate`; this executor is a thin
	adapter that reads the per-node tunables (`high_stake_scopes`,
	`write_scopes`, `write_confidence_threshold`) off the node's inputs.
	"""

	async def execute(self, context: NodeExecutionContext) -> NodeExecutionResult:
		result = await super().execute(context)
		try:
			_ensure_proactive_on_path()
			from proactive import governor as _g
			env = _coerce_envelope(context.inputs.get("input"))
			result.outputs["output"] = _g.gate(
				env,
				high_stake_scopes          = context.inputs.get("high_stake_scopes"),
				write_scopes               = context.inputs.get("write_scopes"),
				write_confidence_threshold = float(context.inputs.get("write_confidence_threshold") or _g.DEFAULT_WRITE_CONF_THRESHOLD),
			)
		except Exception as e:
			result.success = False
			result.error   = str(e)
		return result


class WFMotorExecuteFlow(WFFlowType):
	"""Substrate §4 Motor — execute (allow) or defer (consent_required)."""

	async def execute(self, context: NodeExecutionContext) -> NodeExecutionResult:
		import time as _time
		result = await super().execute(context)
		try:
			env     = _coerce_envelope(context.inputs.get("input"))
			intent  = env.get("intent")
			verdict = (env.get("governor_verdict") or {}).get("decision")
			if intent and verdict == "allow":
				actions = context.variables.setdefault("actions", [])
				rev     = len(actions) + 1
				action  = {
					"id":          f"act_{rev}",
					"capability":  intent.get("capability"),
					"args":        intent.get("args"),
					"executed_at": _time.time(),
					"result":      "stub_success",
				}
				actions.append(action)
				env["motor_action"] = action
				env["motor_status"] = "executed"
			elif intent and verdict == "consent_required":
				env["motor_status"] = "deferred_to_social"
			else:
				env["motor_status"] = "no_action"
			env.setdefault("provenance", []).append({"stage": "motor", "status": env["motor_status"]})
			result.outputs["output"] = env
		except Exception as e:
			result.success = False
			result.error   = str(e)
		return result


class WFSocialConsentFlow(WFFlowType):
	"""Substrate §4 Social — emit a pending consent request on consent_required."""

	async def execute(self, context: NodeExecutionContext) -> NodeExecutionResult:
		import time as _time
		result = await super().execute(context)
		try:
			env     = _coerce_envelope(context.inputs.get("input"))
			intent  = env.get("intent")
			verdict = (env.get("governor_verdict") or {}).get("decision")
			if intent and verdict == "consent_required":
				pending = context.variables.setdefault("pending_consents", [])
				rev     = len(pending) + 1
				consent = {
					"id":             f"consent_{rev}",
					"capability":     intent.get("capability"),
					"rationale":      intent.get("rationale"),
					"correlation_id": env.get("correlation_id"),
					"requested_at":   _time.time(),
					"status":         "awaiting_user",
				}
				pending.append(consent)
				env["social_consent_request"] = consent
			result.outputs["output"] = env
		except Exception as e:
			result.success = False
			result.error   = str(e)
		return result


class WFProactiveStateDirFlow(WFFlowType):
	"""Set the proactive state directory for the rest of this workflow run.

	The contextvar set here lives for the duration of the workflow's
	asyncio task — concurrent workflows each see their own override
	because `proactive.persistence._STATE_DIR_OVERRIDE` is a ContextVar.
	The node never resets the override on the way out: it deliberately
	persists so every downstream node in the same workflow inherits the
	new path. When the workflow's task ends the context is discarded by
	the asyncio runtime, so nothing leaks across workflows."""

	async def execute(self, context: NodeExecutionContext) -> NodeExecutionResult:
		result = await super().execute(context)
		try:
			path = (context.inputs.get("path") or "").strip() if isinstance(context.inputs.get("path"), str) else context.inputs.get("path")
			if path:
				_ensure_proactive_on_path()
				from proactive import persistence as _p
				_p.set_state_dir_override(str(path))
			# Pass the upstream envelope through unchanged so the node can
			# sit mid-pipeline without disturbing data flow.
			result.outputs["output"] = context.inputs.get("input")
		except Exception as e:
			result.success = False
			result.error   = str(e)
		return result


class WFVitalsSweepFlow(WFFlowType):
	"""Substrate §3.6 — recompute Vitals counters over the rolling Ledger."""

	async def execute(self, context: NodeExecutionContext) -> NodeExecutionResult:
		import time as _time
		result = await super().execute(context)
		try:
			env_in = context.inputs.get("input")
			env    = env_in if isinstance(env_in, dict) else {}
			vitals = context.variables.setdefault("vitals", {
				"updated_at": 0.0, "ledger_count": 0,
				"observation_count": 0, "action_attempt_count": 0,
				"governor_decisions": {}, "motor_status_counts": {},
				"avg_pipeline_latency_s": 0.0,
			})
			ledger = context.variables.get("ledger", [])
			obs_n, act_n = 0, 0
			decisions, motor_states = {}, {}
			latencies = []
			# Bucket per-topic for observation/action counters; count any
			# entry that carries a governor_verdict (regardless of topic) so
			# substrate-only workflows that route everything through one
			# topic still get accurate decision counters.
			for entry in ledger:
				topic = (entry.get("trigger") or {}).get("topic", "")
				if topic == "core.sensory.observation":
					obs_n += 1
				elif topic == "core.motor.action_attempt":
					act_n += 1
				verdict = entry.get("governor_verdict") or {}
				if verdict:
					d = verdict.get("decision", "unknown")
					decisions[d] = decisions.get(d, 0) + 1
					m = entry.get("motor_status")
					if m:
						motor_states[m] = motor_states.get(m, 0) + 1
				prov     = entry.get("provenance") or []
				ts_first = next((p.get("ts") for p in prov if "ts" in p), None)
				if ts_first and entry.get("ts"):
					latencies.append(entry["ts"] - ts_first)
			vitals.update({
				"updated_at":             _time.time(),
				"ledger_count":           len(ledger),
				"observation_count":      obs_n,
				"action_attempt_count":   act_n,
				"governor_decisions":     decisions,
				"motor_status_counts":    motor_states,
				"avg_pipeline_latency_s": (sum(latencies) / len(latencies)) if latencies else 0.0,
			})
			snapshot = {
				"vitals":              vitals,
				"latest_observation":  env.get("observation"),
				"latest_intent":       env.get("intent"),
				"latest_motor_status": env.get("motor_status"),
				"latest_consent_id":   ((env.get("social_consent_request") or {}).get("id")),
			}
			result.outputs["output"] = snapshot
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


class WFChannelReceiveFlow(WFFlowType):
	"""Channel Receive node executor — registers a channel message event source."""
	async def execute(self, context: NodeExecutionContext) -> NodeExecutionResult:
		result = await super().execute(context)
		try:
			source_id      = _src_get(context, "source_id", self.config) or f"wf_channel_{context.node_index}"
			name           = _src_get(context, "name", self.config) or source_id
			channel_id     = _src_get(context, "channel_id", self.config, "")
			channel_types  = _src_get(context, "channel_types", self.config, "")
			sender_filter  = _src_get(context, "sender_filter", self.config)

			# Split comma-separated string into list
			if isinstance(channel_types, str):
				channel_types = [t.strip() for t in channel_types.split(",") if t.strip()]

			registry = get_event_registry()
			config = ChannelSourceConfig(
				id=source_id, name=name, channel_id=channel_id,
				channel_types=channel_types, sender_filter=sender_filter
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


class WFAgentChat(WFFlowType):
	"""Agent chat node — execution is handled by the engine via Future-based wait."""
	pass


class WFWorkflowOptions(WFComponentType):
	pass


class WFWorkflow(WFComponentType):
	pass


# =============================================================================
# ML / STREAM INFERENCE NODES
# =============================================================================

# Cached MediaPipe Tasks PoseLandmarker instances keyed by (model_name, min_confidence)
_POSE_DETECTORS: Dict[tuple, Any] = {}

_POSE_MODEL_URLS = {
	"lite":  "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/latest/pose_landmarker_lite.task",
	"full":  "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_full/float16/latest/pose_landmarker_full.task",
	"heavy": "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_heavy/float16/latest/pose_landmarker_heavy.task",
}
_POSE_MODEL_DIR = Path(__file__).resolve().parent.parent / "models"


def _get_pose_model_path(model_name: str) -> Optional[str]:
	"""Return path to the .task model file, downloading it if necessary."""
	import urllib.request
	os.makedirs(_POSE_MODEL_DIR, exist_ok=True)
	fname = f"pose_landmarker_{model_name}.task"
	path  = os.path.join(_POSE_MODEL_DIR, fname)
	if not os.path.exists(path):
		url = _POSE_MODEL_URLS.get(model_name)
		if not url:
			return None
		try:
			log_print(f"Downloading MediaPipe model {fname} …")
			urllib.request.urlretrieve(url, path)
			log_print(f"Saved to {path}")
		except Exception as e:
			log_print(f"Model download failed: {e}")
			return None
	return path


def _get_pose_detector(model_name: str, min_confidence: float) -> Optional[Any]:
	"""Return a cached MediaPipe Tasks PoseLandmarker (Tasks API, 0.10.14+)."""
	key = (model_name, round(min_confidence, 2))
	if key not in _POSE_DETECTORS:
		try:
			from mediapipe.tasks import python as _mp_python
			from mediapipe.tasks.python import vision as _mp_vision

			model_path = _get_pose_model_path(model_name)
			if model_path is None:
				return None

			options = _mp_vision.PoseLandmarkerOptions(
				base_options                  = _mp_python.BaseOptions(model_asset_path=model_path),
				running_mode                  = _mp_vision.RunningMode.IMAGE,
				min_pose_detection_confidence = min_confidence,
				min_pose_presence_confidence  = min_confidence,
				min_tracking_confidence       = min_confidence,
			)
			_POSE_DETECTORS[key] = _mp_vision.PoseLandmarker.create_from_options(options)
		except Exception as e:
			log_print(e)
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
				import mediapipe as mp
				import numpy as np
				from PIL import Image
			except ImportError as e:
				result.success = False
				result.error   = f"Missing dependency: {e}. Install: pip install mediapipe Pillow numpy"
				return result

			# Accept ndarray directly (preferred), fall back to base64/bytes
			if isinstance(frame, np.ndarray):
				img_array = frame
			elif isinstance(frame, str):
				if "," in frame:
					frame = frame.split(",", 1)[1]
				img_bytes = _b64.b64decode(frame)
				img_array = np.array(Image.open(io.BytesIO(img_bytes)).convert("RGB"))
			elif isinstance(frame, bytes):
				img_array = np.array(Image.open(io.BytesIO(frame)).convert("RGB"))
			else:
				return result
			h, w = img_array.shape[:2]

			# Run detection (Tasks API)
			detector = _get_pose_detector(model_name, min_confidence)
			if detector is None:
				result.success = False
				result.error   = "mediapipe not available or model download failed"
				return result

			mp_image  = mp.Image(image_format=mp.ImageFormat.SRGB, data=img_array)
			detection = detector.detect(mp_image)

			if detection.pose_landmarks:
				landmarks = [
					{"x": lm.x, "y": lm.y, "z": lm.z, "visibility": lm.visibility}
					for lm in detection.pose_landmarks[0]
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


# ── Pose connections for PIL drawing ─────────────────────────────────────────
_POSE_CONNECTIONS = [
	(11,12),(11,13),(13,15),(12,14),(14,16),
	(11,23),(12,24),(23,24),
	(23,25),(25,27),(27,29),(29,31),
	(24,26),(26,28),(28,30),(30,32),
	(0,1),(1,2),(2,3),(3,7),
	(0,4),(4,5),(5,6),(6,8),
	(9,10),
]


def _draw_pose_on_image(img: Any, landmarks: list, w: int, h: int) -> Any:
	"""Draw pose skeleton and joint dots on a PIL Image in-place and return it."""
	try:
		from PIL import ImageDraw
	except ImportError:
		return img
	draw = ImageDraw.Draw(img)
	# Skeleton lines (green)
	for a, b in _POSE_CONNECTIONS:
		if a >= len(landmarks) or b >= len(landmarks):
			continue
		la, lb = landmarks[a], landmarks[b]
		x1, y1 = int(la["x"] * w), int(la["y"] * h)
		x2, y2 = int(lb["x"] * w), int(lb["y"] * h)
		draw.line([(x1, y1), (x2, y2)], fill=(0, 255, 100), width=2)
	# Joint dots (red)
	r = 4
	for lm in landmarks:
		x, y = int(lm["x"] * w), int(lm["y"] * h)
		draw.ellipse([(x - r, y - r), (x + r, y + r)], fill=(255, 80, 80))
	return img


class WFComputerVisionFlow(WFFlowType):
	"""Computer Vision node — runs ML inference in the browser (frontend) or on the server (backend)."""

	async def execute(self, context: NodeExecutionContext) -> NodeExecutionResult:
		result = await super().execute(context)

		result.outputs["rendered_image"] = None
		result.outputs["detections"]     = None

		inference_location = context.inputs.get("inference_location", "frontend")

		if inference_location == "frontend":
			# Frontend Worker handles everything — backend is a no-op.
			# Detections arrive via the stream WebSocket instead of output edges.
			return result

		# ── Backend inference ─────────────────────────────────────────────────
		frame = context.inputs.get("image")
		if frame is None:
			return result

		task           = context.inputs.get("task", "pose")
		model_size     = context.inputs.get("model_size", "lite")
		min_confidence = float(context.inputs.get("min_confidence", 0.5))
		draw_overlay   = bool(context.inputs.get("draw_overlay", True))

		try:
			import base64 as _b64
			import io
			import numpy as np
			from PIL import Image
		except ImportError as e:
			result.success = False
			result.error   = f"Missing dependency: {e}. Install: pip install mediapipe Pillow numpy"
			return result

		# Accept ndarray directly (preferred), fall back to base64/bytes
		if isinstance(frame, np.ndarray):
			img_arr = frame
		elif isinstance(frame, str):
			if "," in frame:
				frame = frame.split(",", 1)[1]
			img_arr = np.array(Image.open(io.BytesIO(_b64.b64decode(frame))).convert("RGB"))
		elif isinstance(frame, bytes):
			img_arr = np.array(Image.open(io.BytesIO(frame)).convert("RGB"))
		else:
			return result

		try:
			h, w = img_arr.shape[:2]
			img  = Image.fromarray(img_arr)
		except Exception as e:
			result.success = False
			result.error   = f"Image decode failed: {e}"
			return result

		if task == "pose":
			detector = _get_pose_detector(model_size, min_confidence)
			if detector is None:
				result.success = False
				result.error   = "mediapipe not available or model download failed"
				return result

			import mediapipe as mp
			mp_image  = mp.Image(image_format=mp.ImageFormat.SRGB, data=img_arr)
			detection = detector.detect(mp_image)
			if detection.pose_landmarks:
				landmarks = [
					{"x": lm.x, "y": lm.y, "z": lm.z, "visibility": lm.visibility}
					for lm in detection.pose_landmarks[0]
				]
				result.outputs["detections"] = landmarks
				if draw_overlay:
					img = _draw_pose_on_image(img, landmarks, w, h)
		elif task in ("face", "hands"):
			# Simplified: use MediaPipe legacy API available in mediapipe 0.10+
			try:
				import mediapipe as mp

				if task == "face":
					with mp.solutions.face_detection.FaceDetection(
						model_selection=0,
						min_detection_confidence=min_confidence
					) as detector_f:
						det = detector_f.process(img_arr)
						faces = []
						if det.detections:
							for d in det.detections:
								bb = d.location_data.relative_bounding_box
								faces.append({
									"x": bb.xmin, "y": bb.ymin,
									"width": bb.width, "height": bb.height,
									"score": d.score[0] if d.score else 0.0,
								})
							result.outputs["detections"] = faces
							if draw_overlay:
								from PIL import ImageDraw
								draw_obj = ImageDraw.Draw(img)
								for f in faces:
									x0 = int(f["x"] * w); y0 = int(f["y"] * h)
									x1 = x0 + int(f["width"] * w); y1 = y0 + int(f["height"] * h)
									draw_obj.rectangle([x0, y0, x1, y1], outline=(0, 255, 0), width=2)
						else:
							result.outputs["detections"] = []

				elif task == "hands":
					with mp.solutions.hands.Hands(
						static_image_mode=True,
						max_num_hands=2,
						min_detection_confidence=min_confidence
					) as detector_h:
						det = detector_h.process(img_arr)
						hands = []
						if det.multi_hand_landmarks:
							for hand_lms in det.multi_hand_landmarks:
								hands.append([
									{"x": lm.x, "y": lm.y, "z": lm.z}
									for lm in hand_lms.landmark
								])
								if draw_overlay:
									from PIL import ImageDraw
									draw_obj = ImageDraw.Draw(img)
									for lm in hand_lms.landmark:
										px = int(lm.x * w); py = int(lm.y * h)
										draw_obj.ellipse([px-4, py-4, px+4, py+4], fill=(0, 200, 255))
						result.outputs["detections"] = hands
			except ImportError:
				result.success = False
				result.error = "mediapipe not available"
			except Exception as e:
				result.success = False
				result.error = str(e)

		# Output rendered image as ndarray (drawn overlay baked in)
		if draw_overlay and result.outputs["detections"]:
			try:
				result.outputs["rendered_image"] = np.array(img)
			except Exception:
				pass

		return result


# =============================================================================
# END ML / STREAM INFERENCE NODES
# =============================================================================


# =============================================================================
# UTILITY FLOW NODE EXECUTORS
# =============================================================================

class WFHttpRequestFlow(WFFlowType):
	async def execute(self, context: NodeExecutionContext) -> NodeExecutionResult:
		result = await super().execute(context)
		result.outputs["response"]    = None
		result.outputs["status_code"] = None
		result.outputs["ok"]          = False
		try:
			import aiohttp
			url        = context.inputs.get("url")
			method     = str(context.inputs.get("method", "GET")).upper()
			headers    = context.inputs.get("headers") or {}
			body       = context.inputs.get("body")
			timeout_s  = int(context.inputs.get("timeout_s", 30))
			if not url:
				raise ValueError("url is required")
			timeout = aiohttp.ClientTimeout(total=timeout_s)
			async with aiohttp.ClientSession(timeout=timeout) as session:
				kwargs = {"headers": headers}
				if body is not None:
					if isinstance(body, (dict, list)):
						kwargs["json"] = body
					else:
						kwargs["data"] = str(body)
				async with session.request(method, url, **kwargs) as resp:
					status = resp.status
					try:
						data = await resp.json(content_type=None)
					except Exception:
						data = await resp.text()
					result.outputs["response"]    = data
					result.outputs["status_code"] = status
					result.outputs["ok"]          = 200 <= status < 300
		except ImportError:
			result.success = False
			result.error   = "aiohttp is not installed. Run: pip install aiohttp"
		except Exception as e:
			result.success = False
			result.error   = str(e)
		return result


class WFIfElseFlow(WFFlowType):
	async def execute(self, context: NodeExecutionContext) -> NodeExecutionResult:
		result = await super().execute(context)
		result.outputs["true_out"]  = None
		result.outputs["false_out"] = None
		try:
			value     = context.inputs.get("value")
			condition = context.inputs.get("condition", "bool(value)")
			local_vars = {"value": value, "variables": context.variables}
			cond_result = bool(eval(condition, None, local_vars))
			if cond_result:
				result.outputs["true_out"]  = value
			else:
				result.outputs["false_out"] = value
		except Exception as e:
			result.success = False
			result.error   = str(e)
		return result


class WFMapExtractFlow(WFFlowType):
	async def execute(self, context: NodeExecutionContext) -> NodeExecutionResult:
		result = await super().execute(context)
		result.outputs["output"] = None
		result.outputs["found"]  = False
		try:
			data    = context.inputs.get("data")
			key     = str(context.inputs.get("key", ""))
			default = context.inputs.get("default")
			if not key:
				result.outputs["output"] = data
				result.outputs["found"]  = data is not None
				return result
			parts   = key.split(".")
			current = data
			for part in parts:
				if current is None:
					current = default
					break
				if isinstance(current, dict):
					current = current.get(part, default)
				elif isinstance(current, (list, tuple)):
					try:
						current = current[int(part)]
					except (IndexError, ValueError):
						current = default
						break
				else:
					current = default
					break
			result.outputs["output"] = current
			result.outputs["found"]  = current is not default
		except Exception as e:
			result.success = False
			result.error   = str(e)
		return result


class WFRetryFlow(WFFlowType):
	async def execute(self, context: NodeExecutionContext) -> NodeExecutionResult:
		result = await super().execute(context)
		result.outputs["output"]    = None
		result.outputs["attempts"]  = 0
		result.outputs["succeeded"] = False
		try:
			import asyncio as _asyncio
			input_val    = context.inputs.get("input")
			script       = context.inputs.get("script")
			max_attempts = int(context.inputs.get("max_attempts", 3))
			delay_ms     = int(context.inputs.get("delay_ms", 500))
			# If no script, just pass through the input
			if not script:
				result.outputs["output"]    = input_val
				result.outputs["attempts"]  = 1
				result.outputs["succeeded"] = True
				return result
			local_vars = {"input": input_val, "variables": context.variables, "output": None}
			for attempt in range(1, max_attempts + 1):
				result.outputs["attempts"] = attempt
				try:
					exec(script, None, local_vars)
					if local_vars.get("output") is not None:
						result.outputs["output"]    = local_vars["output"]
						result.outputs["succeeded"] = True
						return result
				except Exception:
					pass
				if attempt < max_attempts:
					await _asyncio.sleep((delay_ms * (2 ** (attempt - 1))) / 1000.0)
			result.success = False
			result.error   = f"All {max_attempts} attempts failed"
		except Exception as e:
			result.success = False
			result.error   = str(e)
		return result


class WFAccumulateFlow(WFFlowType):
	"""Accumulates values across calls using node-level state stored in context.variables."""
	def __init__(self, config, impl=None, **kwargs):
		super().__init__(config, impl, **kwargs)
		node_id = getattr(config, "id", None) or str(id(self))
		self._key = f"__accumulate_{node_id}"

	async def execute(self, context: NodeExecutionContext) -> NodeExecutionResult:
		result = await super().execute(context)
		value  = context.inputs.get("value")
		reset  = bool(context.inputs.get("reset", False))
		if reset or self._key not in context.variables:
			context.variables[self._key] = []
		if value is not None:
			context.variables[self._key].append(value)
		items = list(context.variables[self._key])
		result.outputs["items"] = items
		result.outputs["count"] = len(items)
		return result


class WFEvalFlow(WFFlowType):
	async def execute(self, context: NodeExecutionContext) -> NodeExecutionResult:
		result = await super().execute(context)
		result.outputs["score"]    = 0.0
		result.outputs["feedback"] = ""
		try:
			local_vars = {
				"input"    : context.inputs.get("input"),
				"variables": context.variables,
				"score"    : 0.0,
				"feedback" : "",
			}
			exec(context.inputs.get("script", "score = 0.0"), None, local_vars)
			result.outputs["score"]    = float(local_vars.get("score", 0.0))
			result.outputs["feedback"] = str(local_vars.get("feedback", ""))
		except Exception as e:
			result.success = False
			result.error   = str(e)

		# Publish eval score event so the planner can react mid-execution
		if context.event_bus:
			try:
				from event_bus import EventType as _ET
				await context.event_bus.emit(
					event_type = _ET.WORKFLOW_EVAL_SCORED,
					data       = {
						"node_index": context.node_index,
						"score":      result.outputs["score"],
						"feedback":   result.outputs["feedback"],
					},
				)
			except Exception:
				pass  # never fail the node over event publishing

		return result


class WFNotifyFlow(WFFlowType):
	async def execute(self, context: NodeExecutionContext) -> NodeExecutionResult:
		result = await super().execute(context)
		result.outputs["sent"]  = False
		result.outputs["error"] = None
		try:
			import json as _json
			channel = str(context.inputs.get("channel", "webhook")).lower()
			body    = context.inputs.get("body")
			if isinstance(body, (dict, list)):
				body_str = _json.dumps(body)
			elif body is None:
				body_str = ""
			else:
				body_str = str(body)

			if channel == "webhook":
				import aiohttp
				url     = context.inputs.get("url")
				headers = context.inputs.get("headers") or {"Content-Type": "application/json"}
				if not url:
					raise ValueError("url is required for webhook channel")
				async with aiohttp.ClientSession() as session:
					async with session.post(url, data=body_str, headers=headers) as resp:
						if resp.status >= 400:
							raise ValueError(f"Webhook returned HTTP {resp.status}")

			elif channel == "email":
				import smtplib, os as _os
				from email.mime.text import MIMEText
				to      = context.inputs.get("to")
				subject = context.inputs.get("subject", "Numel Notification")
				smtp_host = _os.environ.get("SMTP_HOST", "localhost")
				smtp_port = int(_os.environ.get("SMTP_PORT", "25"))
				smtp_user = _os.environ.get("SMTP_USER", "")
				smtp_pass = _os.environ.get("SMTP_PASS", "")
				smtp_from = _os.environ.get("SMTP_FROM", smtp_user or "numel@localhost")
				if not to:
					raise ValueError("'to' is required for email channel")
				msg = MIMEText(body_str)
				msg["Subject"] = subject
				msg["From"]    = smtp_from
				msg["To"]      = to
				with smtplib.SMTP(smtp_host, smtp_port) as srv:
					if smtp_user:
						srv.login(smtp_user, smtp_pass)
					srv.send_message(msg)
			else:
				raise ValueError(f"Unknown notify channel: {channel}")

			result.outputs["sent"] = True
		except Exception as e:
			result.success = False
			result.error   = str(e)
			result.outputs["error"] = str(e)
		return result


class WFChannelSendFlow(WFFlowType):
	async def execute(self, context: NodeExecutionContext) -> NodeExecutionResult:
		result = await super().execute(context)
		result.outputs["sent"]  = False
		result.outputs["error"] = None
		try:
			channel_id   = str(context.inputs.get("channel_id", "")).strip()
			recipient_id = str(context.inputs.get("recipient_id", "")).strip()
			message      = context.inputs.get("message")
			attachments  = context.inputs.get("attachments")
			if not channel_id:
				raise ValueError("channel_id is required")
			if not recipient_id:
				raise ValueError("recipient_id is required")

			import json as _json
			if isinstance(message, (dict, list)):
				text = _json.dumps(message)
			elif message is None:
				text = ""
			else:
				text = str(message)

			registry = getattr(context, 'channel_registry', None)
			if not registry:
				raise ValueError("Channel registry not available in execution context")

			adapter = registry._adapters.get(channel_id)
			if not adapter:
				raise ValueError(f"Channel '{channel_id}' not found")

			# Normalize attachments to list of dicts
			send_kwargs = {}
			if attachments:
				if isinstance(attachments, str):
					try:
						attachments = _json.loads(attachments)
					except Exception:
						attachments = None
				if isinstance(attachments, list):
					send_kwargs["attachments"] = attachments

			await adapter.send(recipient_id, text, **send_kwargs)
			result.outputs["sent"] = True
		except Exception as e:
			result.success = False
			result.error   = str(e)
			result.outputs["error"] = str(e)
		return result


# =============================================================================
# END UTILITY FLOW NODE EXECUTORS
# =============================================================================


class ImplementedBackend(BaseModel):
	handles         : List[Any]
	run_tool        : Callable
	run_agent       : Callable
	get_agent_app   : Callable
	add_contents    : Callable
	search_contents : Callable
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
	"vector_db_config"         : WFIndexDBConfig,   # legacy alias
	"index_db_config"          : WFIndexDBConfig,
	"history_manager_config"   : WFHistoryManagerConfig,
	"memory_manager_config"    : WFMemoryManagerConfig,
	"session_manager_config"   : WFSessionManagerConfig,
	"knowledge_manager_config" : WFKnowledgeManagerConfig,
	"tool_config"              : WFToolConfig,
	"toolkit_config"           : WFToolkitConfig,
	"skill_config"             : WFSkillConfig,
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
	"agent_endpoint_flow"      : WFAgentEndpointFlow,
	"knowledge_ingest_flow"    : WFKnowledgeIngestFlow,
	"knowledge_search_flow"    : WFKnowledgeSearchFlow,

	# Proactive Substrate nodes (Phase 5 / M5.7)
	"veracity_gate_flow"       : WFVeracityGateFlow,
	"privacy_gate_flow"        : WFPrivacyGateFlow,
	"adversarial_gate_flow"    : WFAdversarialGateFlow,
	"world_model_write_flow"   : WFWorldModelWriteFlow,
	"ledger_append_flow"       : WFLedgerAppendFlow,
	"goal_match_flow"          : WFGoalMatchFlow,
	"capability_lookup_flow"   : WFCapabilityLookupFlow,
	"governor_decide_flow"     : WFGovernorDecideFlow,
	"motor_execute_flow"       : WFMotorExecuteFlow,
	"social_consent_flow"      : WFSocialConsentFlow,
	"proactive_state_dir_flow" : WFProactiveStateDirFlow,
	"vitals_sweep_flow"        : WFVitalsSweepFlow,

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
	"channel_receive_flow"     : WFChannelReceiveFlow,

	# Utility nodes
	"http_request_flow"        : WFHttpRequestFlow,
	"if_else_flow"             : WFIfElseFlow,
	"map_extract_flow"         : WFMapExtractFlow,
	"retry_flow"               : WFRetryFlow,
	"accumulate_flow"          : WFAccumulateFlow,
	"notify_flow"              : WFNotifyFlow,
	"channel_send_flow"        : WFChannelSendFlow,
	"eval_flow"                : WFEvalFlow,

	# ML / Stream nodes
	"pose_detector_flow"       : WFPoseDetectorFlow,

	"stream_display_flow"      : WFStreamDisplayFlow,
	"computer_vision_flow"     : WFComputerVisionFlow,

	# Interactive nodes
	"tool_call"                : WFToolCall,
	"agent_chat"               : WFAgentChat,
}


def create_node(node: BaseType, impl: Any = None, **kwargs) -> WFBaseType:
	node_class = _NODE_TYPES.get(node.type, WFBaseType)
	return node_class(node, impl, **kwargs)
