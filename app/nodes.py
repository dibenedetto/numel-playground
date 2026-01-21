# nodes

from jinja2   import Template
from pydantic import BaseModel
from typing   import Any, Callable, Dict, List, Optional


from schema   import DEFAULT_TRANSFORM_NODE_LANG, DEFAULT_TRANSFORM_NODE_SCRIPT, DEFAULT_TRANSFORM_NODE_CONTEXT, BaseType


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


class WFContentType(WFBaseType):
	pass


class WFBinaryContent(WFContentType):
	pass


class WFTextContent(WFContentType):
	pass


class WFDocumentContent(WFContentType):
	pass


class WFImageContent(WFContentType):
	pass


class WFAudioContent(WFContentType):
	pass


class WFVideoContent(WFContentType):
	pass


# class WFModel3DContent(WFContentType):
# 	pass


class WFConfigType(WFBaseType):
	async def execute(self, context: NodeExecutionContext) -> NodeExecutionResult:
		result = NodeExecutionResult()
		result.outputs["get"] = self.config
		return result


class WFInfoConfig(WFConfigType):
	pass


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
	pass


class WFStartFlow(WFFlowType):
	async def execute(self, context: NodeExecutionContext) -> NodeExecutionResult:
		result = NodeExecutionResult()
		result.outputs["pin"] = context.variables.copy()
		return result


class WFEndFlow(WFFlowType):
	pass


class WFSinkFlow(WFFlowType):
	pass


# class WFPassthroughFlow(WFFlowType):
# 	async def execute(self, context: NodeExecutionContext) -> NodeExecutionResult:
# 		result = NodeExecutionResult()
# 		result.outputs["output"] = context.inputs.get("input")
# 		return result


class WFPreviewFlow(WFFlowType):
	async def execute(self, context: NodeExecutionContext) -> NodeExecutionResult:
		result = NodeExecutionResult()
		result.outputs["output"] = context.inputs.get("input")
		return result


class WFRouteFlow(WFFlowType):
	async def execute(self, context: NodeExecutionContext) -> NodeExecutionResult:
		result = NodeExecutionResult()
		
		try:
			target  = context.inputs.get("target")
			outputs = self.config.output or {}

			if not target in outputs:
				target = "default"

			result.outputs[target] = context.inputs.get("input")
			result.next_target = target

		except Exception as e:
			result.success = False
			result.error   = str(e)
			
		return result


class WFCombineFlow(WFFlowType):
	async def execute(self, context: NodeExecutionContext) -> NodeExecutionResult:
		result = NodeExecutionResult()
		
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
		result = NodeExecutionResult()

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
		result = NodeExecutionResult()
		
		try:
			lang   = context.inputs.get("lang"   , DEFAULT_TRANSFORM_NODE_LANG   )
			script = context.inputs.get("script" , DEFAULT_TRANSFORM_NODE_SCRIPT )
			ctx    = context.inputs.get("context", DEFAULT_TRANSFORM_NODE_CONTEXT)
			input  = context.inputs.get("input"  , {})

			if lang == "python":
				local_vars = {
					"variables" : context.variables,
					"context"   : ctx,
					"input"     : input,
					"output"    : None,
				}
				exec(script, {"__builtins__": {}}, local_vars)
				output = local_vars.get("output", input)
			elif lang == "jinja2":
				template = Template(script)
				output = template.render(input=input, **context.variables)
			else:
				output = input

			result.outputs["output"] = output

		except Exception as e:
			result.success = False
			result.error = str(e)

		return result


class WFUserInputFlow(WFFlowType):
	async def execute(self, context: NodeExecutionContext) -> NodeExecutionResult:
		result = NodeExecutionResult()
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
		result = NodeExecutionResult()

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
		result = NodeExecutionResult()

		try:
			request = context.inputs.get("input", "")
			if isinstance(request, dict):
				message = request.get("message") or request.get("text") or request.get("value") or request.get("data") or request.get("input") or str(request)
			else:
				message = str(request)

			if self.ref:
				response = await self.ref(message)
			else:
				response = {"error": "No agent configured"}

			result.outputs["output"] = {
				"request"  : request,
				"response" : response,
			}

		except Exception as e:
			result.success = False
			result.error   = str(e)

		return result


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


class ImplementedBackend(BaseModel):
	handles         : List[Any]
	run_tool        : Callable
	run_agent       : Callable
	get_agent_app   : Callable
	add_contents    : Callable
	remove_contents : Callable


# _NODE_CLASSES = [
# 	WFNativeBoolean, WFNativeInteger, WFNativeReal, WFNativeString, WFNativeList, WFNativeDictionary,
# 	WFTextContent, WFDocumentContent, WFImageContent, WFAudioContent, WFVideoContent, # WFModel3DContent,
# 	WFInfoConfig, WFBackendConfig, WFModelConfig, WFEmbeddingConfig, WFContentDBConfig, WFIndexDBConfig, WFMemoryManagerConfig, WFSessionManagerConfig, WFKnowledgeManagerConfig, WFToolConfig, WFAgentOptionsConfig, WFAgentConfig,
# 	WFStartFlow, WFEndFlow, WFSinkFlow, WFPassthroughFlow, WFRouteFlow, WFCombineFlow, WFMergeFlow, WFTransformFlow, WFUserInputFlow, WFToolFlow, WFAgentFlow,
# ]


_NODE_TYPES = {
	"native_boolean"           : WFNativeBoolean,
	"native_integer"           : WFNativeInteger,
	"native_real"              : WFNativeReal,
	"native_string"            : WFNativeString,
	"native_list"              : WFNativeList,
	"native_dictionary"        : WFNativeDictionary,

	"text_content"             : WFTextContent,
	"document_content"         : WFDocumentContent,
	"image_content"            : WFImageContent,
	"audio_content"            : WFAudioContent,
	"video_content"            : WFVideoContent,
	# "model3d_content"          : WFModel3DContent,

	"info_config"              : WFInfoConfig,
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
	# "passthrough_flow"         : WFPassthroughFlow,
	"preview_flow"             : WFPreviewFlow,
	"route_flow"               : WFRouteFlow,
	"combine_flow"             : WFCombineFlow,
	"merge_flow"               : WFMergeFlow,
	"transform_flow"           : WFTransformFlow,
	"user_input_flow"          : WFUserInputFlow,
	"tool_flow"                : WFToolFlow,
	"agent_flow"               : WFAgentFlow,

	"tool_call"                : WFToolCall,
	"agent_chat"               : WFAgentChat,
}


def create_node(node: BaseType, impl: Any = None, **kwargs) -> WFBaseType:
	node_class = _NODE_TYPES.get(node.type, WFBaseType)
	return node_class(node, impl, **kwargs)
