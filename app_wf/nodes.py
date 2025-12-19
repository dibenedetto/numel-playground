# nodes

from jinja2   import Template
from pydantic import BaseModel
from typing   import Any, Callable, Dict, List, Optional


from schema   import BaseType


class NodeExecutionContext:
	"""Data flowing into a node"""
	def __init__(self):
		self.inputs      : Dict[str, Any] = {} # {slot_name: data}
		self.variables   : Dict[str, Any] = {} # Global workflow variables
		self.node_index  : int            = 0
		self.node_config : Dict[str, Any] = {} # Full node configuration


class NodeExecutionResult:
	"""Data flowing out of a node"""
	def __init__(self):
		self.outputs     : Dict[str, Any] = {}  # {slot_name: data}
		self.success     : bool           = True
		self.error       : Optional[str]  = None
		self.next_target : Optional[str]  = None  # For switch nodes


# ========================================================================
# BASE TYPE
# ========================================================================

class WFBaseType:
	"""All nodes inherit from this"""
	
	def __init__(self, config: Dict[str, Any] = None, impl: Any = None, **kwargs):
		self.config = config or {}
		self.impl   = impl
		
	async def execute(self, context: NodeExecutionContext) -> NodeExecutionResult:
		"""Override this - pure function: input data → output data"""
		raise NotImplementedError


# ========================================================================
# CONFIG NODE
# ========================================================================

class WFBaseConfig(WFBaseType):
	"""Base class for config nodes"""
	
	async def execute(self, context: NodeExecutionContext) -> NodeExecutionResult:
		result = NodeExecutionResult()
		result.outputs = {"get": self.config}
		return result


# ========================================================================
# CONFIG NODES (passthrough their configuration)
# ========================================================================

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


# ========================================================================
# BASE NODE
# ========================================================================

class WFBaseNode(WFBaseType):
	"""All nodes inherit from this"""
	pass


# ========================================================================
# CONTROL FLOW NODES
# ========================================================================

class WFStartNode(WFBaseNode):
	"""Outputs initial workflow variables via 'start' slot"""
	
	async def execute(self, context: NodeExecutionContext) -> NodeExecutionResult:
		result = NodeExecutionResult()
		result.outputs = {"start": context.variables.copy()}
		return result


class WFEndNode(WFBaseNode):
	"""Receives final output via 'end' slot"""
	
	async def execute(self, context: NodeExecutionContext) -> NodeExecutionResult:
		result = NodeExecutionResult()
		return result


class WFSinkNode(WFBaseNode):
	"""Receives data via 'sink' slot (discards it)"""
	
	async def execute(self, context: NodeExecutionContext) -> NodeExecutionResult:
		result = NodeExecutionResult()
		return result


# ========================================================================
# SCRIPT-BASED NODES
# ========================================================================

class WFScriptNode(WFBaseNode):
	"""Base class for script-executing nodes"""
	
	def _get_lang(self) -> str:
		lang = self.config.get("lang", "python")
		# Handle Message format: {"type": "", "value": "python"}
		if isinstance(lang, dict):
			return lang.get("value", "python")
		return lang
	
	def _get_script(self) -> str:
		script = self.config.get("script", "")
		if isinstance(script, dict):
			return script.get("value", "")
		return script


class WFTransformNode(WFScriptNode):
	"""Transforms data using Python code"""
	
	async def execute(self, context: NodeExecutionContext) -> NodeExecutionResult:
		result = NodeExecutionResult()
		
		try:
			input_data = context.inputs.get("source", {})
			lang = self._get_lang()
			script = self._get_script()
			
			if lang == "python":
				local_vars = {
					"input": input_data,
					"output": None,
					"variables": context.variables,
					"__target": None,
				}
				exec(script, {"__builtins__": {}}, local_vars)
				output = local_vars.get("output", input_data)
				
				if local_vars.get("__target"):
					result.next_target = local_vars["__target"]
				
			elif lang == "jinja2":
				template = Template(script)
				output = template.render(input=input_data, **context.variables)
			else:
				output = input_data
			
			result.outputs = {"target": output}
			
		except Exception as e:
			result.success = False
			result.error = str(e)
			
		return result


class WFSwitchNode(WFScriptNode):
	"""Routes data based on script evaluation to cases or default"""
	
	async def execute(self, context: NodeExecutionContext) -> NodeExecutionResult:
		result = NodeExecutionResult()
		
		try:
			input_value = context.inputs.get("value", {})
			lang = self._get_lang()
			script = self._get_script()
			cases = self.config.get("cases", {})
			
			if isinstance(cases, dict):
				case_keys = list(cases.keys())
			else:
				case_keys = []
			
			selected_case = "default"
			
			if script and lang == "python":
				local_vars = {
					"input": input_value,
					"__value": input_value,
					"val": None,
				}
				exec(script, {"__builtins__": {}}, local_vars)
				selected_case = local_vars.get("val", "default")
			
			# Output to matched case slot
			for case_key in case_keys:
				slot_name = f"cases.{case_key}"
				is_matched = (selected_case == case_key)
				result.outputs[slot_name] = {
					"data": input_value,
					"matched": is_matched,
					"case": case_key
				}
			
			result.outputs["default"] = {
				"data": input_value,
				"matched": (selected_case == "default" or selected_case not in case_keys),
				"case": "default"
			}
			
			result.next_target = selected_case
			
		except Exception as e:
			result.success = False
			result.error = str(e)
			
		return result


class WFSplitNode(WFScriptNode):
	"""Splits data to multiple outputs based on mapping"""
	
	async def execute(self, context: NodeExecutionContext) -> NodeExecutionResult:
		result = NodeExecutionResult()
		
		try:
			source = context.inputs.get("source", {})
			mapping = self.config.get("mapping", {})
			
			if isinstance(mapping, dict):
				mapping_dict = mapping.get("value", mapping) if isinstance(mapping.get("value"), dict) else mapping
			else:
				mapping_dict = {}
			
			for target_key, source_path in mapping_dict.items():
				slot_name = f"targets.{target_key}"
				if isinstance(source, dict):
					result.outputs[slot_name] = source.get(source_path, None)
				else:
					result.outputs[slot_name] = source
			
		except Exception as e:
			result.success = False
			result.error = str(e)
			
		return result


class WFMergeNode(WFBaseNode):
	"""Merges multiple inputs into one output"""
	
	async def execute(self, context: NodeExecutionContext) -> NodeExecutionResult:
		result = NodeExecutionResult()
		
		try:
			strategy = self.config.get("strategy", "first")
			if isinstance(strategy, dict):
				strategy = strategy.get("value", "first")
			
			inputs = []
			for key, value in context.inputs.items():
				if key.startswith("sources."):
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
			else:  # "all"
				merged = inputs
			
			result.outputs = {"target": merged}
			
		except Exception as e:
			result.success = False
			result.error = str(e)
			
		return result


# ========================================================================
# USER INTERACTION NODES
# ========================================================================

class WFUserInputNode(WFBaseNode):
	"""Waits for user input"""
	
	async def execute(self, context: NodeExecutionContext) -> NodeExecutionResult:
		result = NodeExecutionResult()
		result.outputs = {"message": {"awaiting_input": True}}
		return result


class WFUserOutputNode(WFBaseNode):
	"""Displays output to user"""
	
	async def execute(self, context: NodeExecutionContext) -> NodeExecutionResult:
		result = NodeExecutionResult()
		message = context.inputs.get("message", "")
		result.outputs = {"get": message}
		return result


# ========================================================================
# TOOL & AGENT NODES
# ========================================================================

class WFToolNode(WFBaseNode):
	"""Executes a tool"""
	
	def __init__(self, config: Dict[str, Any], impl: Any = None, **kwargs):
		assert "ref" in kwargs, "WFToolNode requires 'ref' argument"
		super().__init__(config, impl, **kwargs)
		self.ref = kwargs["ref"]
	
	async def execute(self, context: NodeExecutionContext) -> NodeExecutionResult:
		result = NodeExecutionResult()
		
		try:
			source = context.inputs.get("source", {})
			arguments = context.inputs.get("arguments", {})
			
			if isinstance(arguments, dict) and "value" in arguments:
				arguments = arguments["value"]
			
			if self.ref:
				tool_result = await self.ref(**arguments)
			else:
				tool_result = {"error": "No tool configured"}
			
			result.outputs = {"target": {"result": tool_result, "input": source}}
			
		except Exception as e:
			result.success = False
			result.error   = str(e)
			
		return result


class WFAgentNode(WFBaseNode):
	"""Executes an agent"""
	
	def __init__(self, config: Dict[str, Any], impl: Any = None, **kwargs):
		assert "ref" in kwargs, "WFAgentNode requires 'ref' argument"
		super().__init__(config, impl, **kwargs)
		self.ref = kwargs["ref"]
	
	async def execute(self, context: NodeExecutionContext) -> NodeExecutionResult:
		result = NodeExecutionResult()
		
		try:
			request = context.inputs.get("request", {})
			
			if isinstance(request, dict):
				message = request.get("message") or request.get("data") or request.get("value") or str(request)
			else:
				message = str(request)
			
			if self.ref:
				response = await self.ref(message)
			else:
				response = {"error": "No agent configured"}
			
			result.outputs = {"response": {"response": response, "input": request}}
			
		except Exception as e:
			result.success = False
			result.error   = str(e)
			
		return result


class ImplementedBackend(BaseModel):
	handles   : List[Any]
	run_tool  : Callable
	run_agent : Callable


# ========================================================================
# NODE FACTORY
# ========================================================================

_NODE_TYPES = {
	# Config nodes
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

	# Control flow
	"start_node"               : WFStartNode,
	"end_node"                 : WFEndNode,
	"sink_node"                : WFSinkNode,

	# Script-based
	"script_node"              : WFScriptNode,
	"transform_node"           : WFTransformNode,
	"switch_node"              : WFSwitchNode,
	"split_node"               : WFSplitNode,
	"merge_node"               : WFMergeNode,

	# User interaction
	"user_input_node"          : WFUserInputNode,
	"user_output_node"         : WFUserOutputNode,

	# Tool & Agent
	"tool_node"                : WFToolNode,
	"agent_node"               : WFAgentNode,
}


def create_node(node: BaseType, impl: Any = None, **kwargs) -> WFBaseType:
	"""Factory function to create nodes"""
	node_class = _NODE_TYPES.get(node.type, WFBaseType)
	return node_class(node, impl, **kwargs)
