# workflow_nodes

from typing import Any, Dict, List, Optional
from jinja2 import Template


class NodeExecutionContext:
	"""Data flowing into a node"""
	def __init__(self):
		self.inputs: Dict[str, Any] = {}  # {slot_name: data}
		self.variables: Dict[str, Any] = {}  # Global workflow variables
		self.node_index: int = 0


class NodeExecutionResult:
	"""Data flowing out of a node"""
	def __init__(self):
		self.outputs: Dict[str, Any] = {}  # {slot_name: data}
		self.success: bool = True
		self.error: Optional[str] = None


class BaseNode:
	"""All nodes inherit from this - pure data transformer"""
	
	def __init__(self, config: Dict[str, Any] = None):
		self.config = config or {}
		
	async def execute(self, context: NodeExecutionContext) -> NodeExecutionResult:
		"""Override this - pure function: input data → output data"""
		raise NotImplementedError
		
	def get_input_slots(self) -> List[str]:
		"""Define what inputs this node accepts"""
		return ["input"]
		
	def get_output_slots(self) -> List[str]:
		"""Define what outputs this node produces"""
		return ["output"]


class StartNode(BaseNode):
	"""Outputs initial workflow variables"""
	
	def get_input_slots(self):
		return []
	
	async def execute(self, context: NodeExecutionContext) -> NodeExecutionResult:
		result = NodeExecutionResult()
		result.outputs = {"output": context.variables.copy()}
		return result


class EndNode(BaseNode):
	"""Collects final outputs"""
	
	def get_output_slots(self):
		return []
	
	async def execute(self, context: NodeExecutionContext) -> NodeExecutionResult:
		result = NodeExecutionResult()
		# Just pass through - end node doesn't need outputs
		return result


class AgentNode(BaseNode):
	"""Executes an agent with input data"""
	
	def __init__(self, config: Dict[str, Any], agent):
		super().__init__(config)
		self.agent = agent
		
	async def execute(self, context: NodeExecutionContext) -> NodeExecutionResult:
		result = NodeExecutionResult()
		
		try:
			# Get input data
			input_data = context.inputs.get('input', {})
			
			# Prepare message
			if isinstance(input_data, dict):
				message = input_data.get('message', str(input_data))
			else:
				message = str(input_data)
			
			# Run agent
			# response = f"Agent processed: {message}"
			response = await self.agent(message)
			
			result.outputs = {
				"output": {
					"response": response,
					"input": input_data
				}
			}
		except Exception as e:
			result.success = False
			result.error = str(e)
			
		return result


class PromptNode(BaseNode):
	"""Renders a prompt template with input data"""
	
	async def execute(self, context: NodeExecutionContext) -> NodeExecutionResult:
		result = NodeExecutionResult()
		
		try:
			template_str = self.config.get('template', '{{input}}')
			input_data = context.inputs.get('input', {})
			
			# Render template
			template = Template(template_str)
			rendered = template.render(input=input_data, **context.variables)
			
			result.outputs = {
				"output": {
					"prompt": rendered,
					"input": input_data
				}
			}
		except Exception as e:
			result.success = False
			result.error = str(e)
			
		return result


class ToolNode(BaseNode):
	"""Executes a tool with input data"""
	
	def __init__(self, config: Dict[str, Any], tool):
		super().__init__(config)
		self.tool = tool
		
	async def execute(self, context: NodeExecutionContext) -> NodeExecutionResult:
		result = NodeExecutionResult()
		
		try:
			input_data = context.inputs.get('input', {})
			
			# Execute tool
			# tool_result = f"Tool executed with: {input_data}"
			tool_result = await self.tool(input_data)
			
			result.outputs = {
				"output": {
					"result": tool_result,
					"input": input_data
				}
			}
		except Exception as e:
			result.success = False
			result.error = str(e)
			
		return result


class TransformNode(BaseNode):
	"""Transforms data using Python code or template"""
	
	async def execute(self, context: NodeExecutionContext) -> NodeExecutionResult:
		result = NodeExecutionResult()
		
		try:
			input_data = context.inputs.get('input', {})
			transform_type = self.config.get('type', 'python')
			script = self.config.get('script', 'output = input')
			
			if transform_type == 'python':
				# Execute Python transform
				local_vars = {
					'input': input_data,
					'output': None,
					'variables': context.variables
				}
				exec(script, {}, local_vars)
				output = local_vars.get('output', input_data)
				
			elif transform_type == 'jinja2':
				# Render template
				template = Template(script)
				output = template.render(input=input_data, **context.variables)
				
			else:
				# Pass through
				output = input_data
			
			result.outputs = {"output": output}
			
		except Exception as e:
			result.success = False
			result.error = str(e)
			
		return result


class DecisionNode(BaseNode):
	"""Routes data to different output slots based on condition"""
	
	def get_output_slots(self):
		branches = self.config.get('branches', {})
		return list(branches.keys()) if branches else ['default']
	
	async def execute(self, context: NodeExecutionContext) -> NodeExecutionResult:
		result = NodeExecutionResult()
		
		try:
			input_data = context.inputs.get('input', {})
			condition_field = self.config.get('condition_field', 'value')
			
			# Get value to check
			if isinstance(input_data, dict):
				value = input_data.get(condition_field)
			else:
				value = input_data
			
			# Output to all branches with match indicator
			branches = self.config.get('branches', {})
			for branch_name in branches.keys():
				result.outputs[branch_name] = {
					'data': input_data,
					'matched': (str(value) == branch_name)
				}
				
			# Default branch if no branches defined
			if not branches:
				result.outputs['default'] = {
					'data': input_data,
					'matched': True
				}
				
		except Exception as e:
			result.success = False
			result.error = str(e)
			
		return result


class MergeNode(BaseNode):
	"""Merges multiple inputs into one output"""
	
	async def execute(self, context: NodeExecutionContext) -> NodeExecutionResult:
		result = NodeExecutionResult()
		
		try:
			# Collect all inputs
			inputs = list(context.inputs.values())
			strategy = self.config.get('strategy', 'all')
			
			if strategy == 'first':
				merged = inputs[0] if inputs else None
			elif strategy == 'last':
				merged = inputs[-1] if inputs else None
			else:  # 'all'
				merged = inputs
			
			result.outputs = {"output": merged}
			
		except Exception as e:
			result.success = False
			result.error = str(e)
			
		return result


class UserInputNode(BaseNode):
	"""Waits for user input"""
	
	async def execute(self, context: NodeExecutionContext) -> NodeExecutionResult:
		result = NodeExecutionResult()
		
		# This will be handled by the engine setting up a future
		# Just return the context for now
		result.outputs = {"output": {"awaiting_input": True}}
		
		return result


# Node factory
NODE_TYPES = {
	"start": StartNode,
	"end": EndNode,
	"agent": AgentNode,
	"prompt": PromptNode,
	"tool": ToolNode,
	"transform": TransformNode,
	"decision": DecisionNode,
	"merge": MergeNode,
	"user_input": UserInputNode,
}


def create_node(node_type: str, config: Dict[str, Any] = None, **kwargs) -> BaseNode:
	"""Factory function to create nodes"""
	node_class = NODE_TYPES.get(node_type)
	if not node_class:
		raise ValueError(f"Unknown node type: {node_type}")
	return node_class(config, **kwargs)
