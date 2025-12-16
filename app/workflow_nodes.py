# workflow_nodes.py
# Node executors for workflow_schema_new.py

from typing import Any, Callable, Dict, List, Optional
from jinja2 import Template


class NodeExecutionContext:
	"""Data flowing into a node"""
	def __init__(self):
		self.inputs: Dict[str, Any] = {}      # {slot_name: data}
		self.variables: Dict[str, Any] = {}   # Global workflow variables
		self.node_index: int = 0
		self.node_config: Dict[str, Any] = {} # Full node configuration


class NodeExecutionResult:
	"""Data flowing out of a node"""
	def __init__(self):
		self.outputs: Dict[str, Any] = {}  # {slot_name: data}
		self.success: bool = True
		self.error: Optional[str] = None
		self.next_target: Optional[str] = None  # For switch nodes


class BaseNode:
	"""All nodes inherit from this"""
	
	def __init__(self, config: Dict[str, Any] = None, **kwargs):
		self.config = config or {}
		self.extra = self.config.get("extra")
		
	async def execute(self, context: NodeExecutionContext) -> NodeExecutionResult:
		"""Override this - pure function: input data → output data"""
		raise NotImplementedError
		
	def get_input_slots(self) -> List[str]:
		return ["data"]
		
	def get_output_slots(self) -> List[str]:
		return ["get"]


# ========================================================================
# CONTROL FLOW NODES
# ========================================================================

class StartNode(BaseNode):
	"""Outputs initial workflow variables via 'start' slot"""
	
	def get_input_slots(self):
		return []
	
	def get_output_slots(self):
		return ["start"]
	
	async def execute(self, context: NodeExecutionContext) -> NodeExecutionResult:
		result = NodeExecutionResult()
		result.outputs = {"start": context.variables.copy()}
		return result


class EndNode(BaseNode):
	"""Receives final output via 'end' slot"""
	
	def get_input_slots(self):
		return ["end"]
	
	def get_output_slots(self):
		return []
	
	async def execute(self, context: NodeExecutionContext) -> NodeExecutionResult:
		result = NodeExecutionResult()
		return result


class SinkNode(BaseNode):
	"""Receives data via 'sink' slot (discards it)"""
	
	def get_input_slots(self):
		return ["sink"]
	
	def get_output_slots(self):
		return []
	
	async def execute(self, context: NodeExecutionContext) -> NodeExecutionResult:
		result = NodeExecutionResult()
		return result


# ========================================================================
# USER INTERACTION NODES
# ========================================================================

class UserInputNode(BaseNode):
	"""Waits for user input"""
	
	def get_input_slots(self):
		return ["query"]
	
	def get_output_slots(self):
		return ["message"]
	
	async def execute(self, context: NodeExecutionContext) -> NodeExecutionResult:
		result = NodeExecutionResult()
		result.outputs = {"message": {"awaiting_input": True}}
		return result


class UserOutputNode(BaseNode):
	"""Displays output to user"""
	
	def get_input_slots(self):
		return ["message"]
	
	def get_output_slots(self):
		return ["get"]
	
	async def execute(self, context: NodeExecutionContext) -> NodeExecutionResult:
		result = NodeExecutionResult()
		message = context.inputs.get("message", "")
		result.outputs = {"get": message}
		return result


# ========================================================================
# SCRIPT-BASED NODES
# ========================================================================

class ScriptNode(BaseNode):
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


class TransformNode(ScriptNode):
	"""Transforms data using Python code"""
	
	def get_input_slots(self):
		return ["source"]
	
	def get_output_slots(self):
		return ["target"]
	
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


class SwitchNode(ScriptNode):
	"""Routes data based on script evaluation to cases or default"""
	
	def get_input_slots(self):
		return ["value"]
	
	def get_output_slots(self):
		cases = self.config.get("cases", {})
		if isinstance(cases, dict):
			return [f"cases.{k}" for k in cases.keys()] + ["default"]
		return ["default"]
	
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


class SplitNode(ScriptNode):
	"""Splits data to multiple outputs based on mapping"""
	
	def get_input_slots(self):
		return ["source"]
	
	def get_output_slots(self):
		targets = self.config.get("targets", {})
		if isinstance(targets, dict):
			return [f"targets.{k}" for k in targets.keys()]
		return []
	
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


class MergeNode(BaseNode):
	"""Merges multiple inputs into one output"""
	
	def get_input_slots(self):
		sources = self.config.get("sources", {})
		if isinstance(sources, dict):
			return [f"sources.{k}" for k in sources.keys()]
		return ["sources.0", "sources.1"]
	
	def get_output_slots(self):
		return ["target"]
	
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
# TOOL & AGENT NODES
# ========================================================================

class ToolNode(BaseNode):
	"""Executes a tool"""
	
	def __init__(self, config: Dict[str, Any], tool: Callable = None, **kwargs):
		super().__init__(config, **kwargs)
		self.tool = tool
	
	def get_input_slots(self):
		return ["config", "arguments", "source"]
	
	def get_output_slots(self):
		return ["target"]
	
	async def execute(self, context: NodeExecutionContext) -> NodeExecutionResult:
		result = NodeExecutionResult()
		
		try:
			source = context.inputs.get("source", {})
			arguments = context.inputs.get("arguments", {})
			
			if isinstance(arguments, dict) and "value" in arguments:
				arguments = arguments["value"]
			
			if self.tool:
				tool_result = await self.tool(**arguments)
			else:
				tool_result = {"error": "No tool configured"}
			
			result.outputs = {"target": {"result": tool_result, "input": source}}
			
		except Exception as e:
			result.success = False
			result.error = str(e)
			
		return result


class AgentNode(BaseNode):
	"""Executes an agent"""
	
	def __init__(self, config: Dict[str, Any], agent: Callable = None, **kwargs):
		super().__init__(config, **kwargs)
		self.agent = agent
	
	def get_input_slots(self):
		return ["config", "request"]
	
	def get_output_slots(self):
		return ["response"]
		
	async def execute(self, context: NodeExecutionContext) -> NodeExecutionResult:
		result = NodeExecutionResult()
		
		try:
			request = context.inputs.get("request", {})
			
			if isinstance(request, dict):
				message = request.get("message") or request.get("data") or request.get("value") or str(request)
			else:
				message = str(request)
			
			if self.agent:
				response = await self.agent(message)
			else:
				response = {"error": "No agent configured"}
			
			result.outputs = {"response": {"response": response, "input": request}}
			
		except Exception as e:
			result.success = False
			result.error = str(e)
			
		return result


# ========================================================================
# CONFIG NODES (passthrough their configuration)
# ========================================================================

class ConfigNode(BaseNode):
	"""Base class for config nodes"""
	
	def get_output_slots(self):
		return ["get"]
	
	async def execute(self, context: NodeExecutionContext) -> NodeExecutionResult:
		result = NodeExecutionResult()
		result.outputs = {"get": self.config}
		return result


class InfoConfigNode(ConfigNode):
	def get_input_slots(self):
		return []


class BackendConfigNode(ConfigNode):
	def get_input_slots(self):
		return []


class ModelConfigNode(ConfigNode):
	def get_input_slots(self):
		return []


class EmbeddingConfigNode(ConfigNode):
	def get_input_slots(self):
		return []


class PromptConfigNode(ConfigNode):
	def get_input_slots(self):
		return ["model", "embedding"]


class ContentDBConfigNode(ConfigNode):
	def get_input_slots(self):
		return []


class IndexDBConfigNode(ConfigNode):
	def get_input_slots(self):
		return ["embedding"]


class MemoryManagerConfigNode(ConfigNode):
	def get_input_slots(self):
		return ["prompt"]


class SessionManagerConfigNode(ConfigNode):
	def get_input_slots(self):
		return ["prompt"]


class KnowledgeManagerConfigNode(ConfigNode):
	def get_input_slots(self):
		return ["content_db", "index_db"]


class ToolConfigNode(ConfigNode):
	def get_input_slots(self):
		return []


class AgentOptionsConfigNode(ConfigNode):
	def get_input_slots(self):
		return []


class AgentConfigNode(ConfigNode):
	def get_input_slots(self):
		return ["info", "options", "backend", "prompt", "content_db", 
				"memory_mgr", "session_mgr", "knowledge_mgr", "tools"]


class WorkflowOptionsConfigNode(ConfigNode):
	def get_input_slots(self):
		return []


# ========================================================================
# NODE FACTORY
# ========================================================================

NODE_TYPES = {
	# Control flow
	"start_node": StartNode,
	"end_node": EndNode,
	"sink_node": SinkNode,
	
	# User interaction
	"user_input_node": UserInputNode,
	"user_output_node": UserOutputNode,
	
	# Script-based
	"script_node": ScriptNode,
	"transform_node": TransformNode,
	"switch_node": SwitchNode,
	"split_node": SplitNode,
	"merge_node": MergeNode,
	
	# Tool & Agent
	"tool_node": ToolNode,
	"agent_node": AgentNode,
	
	# Config nodes
	"info_config": InfoConfigNode,
	"backend_config": BackendConfigNode,
	"model_config": ModelConfigNode,
	"embedding_config": EmbeddingConfigNode,
	"prompt_config": PromptConfigNode,
	"content_db_config": ContentDBConfigNode,
	"index_db_config": IndexDBConfigNode,
	"memory_manager_config": MemoryManagerConfigNode,
	"session_manager_config": SessionManagerConfigNode,
	"knowledge_manager_config": KnowledgeManagerConfigNode,
	"tool_config": ToolConfigNode,
	"agent_options_config": AgentOptionsConfigNode,
	"agent_config": AgentConfigNode,
	"workflow_options_config": WorkflowOptionsConfigNode,
}


def create_node(node_type: str, config: Dict[str, Any] = None, **kwargs) -> BaseNode:
	"""Factory function to create nodes"""
	node_class = NODE_TYPES.get(node_type, ConfigNode)
	return node_class(config, **kwargs)


def get_node_types() -> List[str]:
	"""Get list of all registered node types"""
	return list(NODE_TYPES.keys())
