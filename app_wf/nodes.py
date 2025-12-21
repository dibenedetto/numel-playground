# nodes

from jinja2   import Template
from pydantic import BaseModel
from typing   import Any, Callable, Dict, List, Optional


from schema   import BaseType


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
		raise NotImplementedError


class WFBaseConfig(WFBaseType):
	async def execute(self, context: NodeExecutionContext) -> NodeExecutionResult:
		result = NodeExecutionResult()
		result.outputs = {"get": self.config}
		return result


class WFInfoConfig(WFBaseConfig):
	pass


class WFBackendConfig(WFBaseConfig):
	pass


class WFModelConfig(WFBaseConfig):
	pass


class WFEmbeddingConfig(WFBaseConfig):
	pass


class WFPromptConfig(WFBaseConfig):
	pass


class WFContentDBConfig(WFBaseConfig):
	pass


class WFIndexDBConfig(WFBaseConfig):
	pass


class WFMemoryManagerConfig(WFBaseConfig):
	pass


class WFSessionManagerConfig(WFBaseConfig):
	pass


class WFKnowledgeManagerConfig(WFBaseConfig):
	pass


class WFToolConfig(WFBaseConfig):
	pass


class WFAgentOptionsConfig(WFBaseConfig):
	pass


class WFAgentConfig(WFBaseConfig):
	pass


class WFWorkflowOptionsConfig(WFBaseConfig):
	pass


class WFBaseNode(WFBaseType):
	pass


class WFStartNode(WFBaseNode):
	async def execute(self, context: NodeExecutionContext) -> NodeExecutionResult:
		result = NodeExecutionResult()
		result.outputs["pin"] = context.variables.copy()
		return result


class WFEndNode(WFBaseNode):
	async def execute(self, context: NodeExecutionContext) -> NodeExecutionResult:
		result = NodeExecutionResult()
		return result


class WFRouteNode(WFBaseNode):
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


class WFCombineNode(WFBaseNode):
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


class WFMergeNode(WFBaseNode):
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


class WFTransformNode(WFBaseNode):
	async def execute(self, context: NodeExecutionContext) -> NodeExecutionResult:
		result = NodeExecutionResult()
		
		try:
			lang   = context.inputs.get("lang"  , "python")
			script = context.inputs.get("script", ""      )
			input  = context.inputs.get("input" , {}      )

			if lang == "python":
				local_vars = {
					"context" : context.variables,
					"input"   : input,
					"output"  : None,
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


class WFUserInputNode(WFBaseNode):
	async def execute(self, context: NodeExecutionContext) -> NodeExecutionResult:
		result = NodeExecutionResult()
		result.outputs["content"] = {
			"awaiting_input": True,
		}
		return result


class WFToolNode(WFBaseNode):
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


class WFAgentNode(WFBaseNode):
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


class WFBaseInteractive(WFBaseType):
	pass


class WFToolCall(WFBaseInteractive):
	pass


class WFAgentChat(WFBaseInteractive):
	pass


class ImplementedBackend(BaseModel):
	handles   : List[Any]
	run_tool  : Callable
	run_agent : Callable


_NODE_TYPES = {
	"info_config"              : WFInfoConfig,
	"backend_config"           : WFBackendConfig,
	"model_config"             : WFModelConfig,
	"embedding_config"         : WFEmbeddingConfig,
	"prompt_config"            : WFPromptConfig,
	"content_db_config"        : WFContentDBConfig,
	"index_db_config"          : WFIndexDBConfig,
	"memory_manager_config"    : WFMemoryManagerConfig,
	"session_manager_config"   : WFSessionManagerConfig,
	"knowledge_manager_config" : WFKnowledgeManagerConfig,
	"tool_config"              : WFToolConfig,
	"agent_options_config"     : WFAgentOptionsConfig,
	"agent_config"             : WFAgentConfig,
	"workflow_options_config"  : WFWorkflowOptionsConfig,
	"start_node"               : WFStartNode,
	"end_node"                 : WFEndNode,
	"route_node"               : WFRouteNode,
	"combine_node"             : WFCombineNode,
	"merge_node"               : WFMergeNode,
	"transform_node"           : WFTransformNode,
	"user_input_node"          : WFUserInputNode,
	"tool_node"                : WFToolNode,
	"agent_node"               : WFAgentNode,
	"tool_call"                : WFToolCall,
	"agent_chat"               : WFAgentChat,
}


def create_node(node: BaseType, impl: Any = None, **kwargs) -> WFBaseType:
	node_class = _NODE_TYPES.get(node.type, WFBaseType)
	return node_class(node, impl, **kwargs)
