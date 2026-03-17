# _template.py — Toolkit Template
#
# Copy this file to create a new toolkit.
# Rename it to your_toolkit_name.py and update the class.
#
# Toolkits are auto-discovered by the system. Place them in:
#   - app/toolkits/    (built-in, shipped with Numel)
#   - contrib/toolkits/ (user-created, third-party)
#
# The agent can also create toolkits at runtime via the code_toolkit.

class MyToolkit:
	"""Short description of what this toolkit does.

A longer description can go here. This docstring is shown when
listing available toolkits. The first line is used as the summary.

Available operations:
- my_tool: description of this tool
- another_tool: description of another tool"""

	# REQUIRED: This flag tells the system this class is a toolkit
	__toolkit__ = True

	def __init__(self):
		"""Initialize the toolkit. Called once when the toolkit is loaded.
		You can accept constructor arguments (e.g. api_key, config_path).
		"""
		pass

	def my_tool(self, input_text: str) -> str:
		"""Do something useful with the input.

		Every public method (no leading underscore) becomes a tool
		that the agent can call. Methods MUST have:
		  1. A docstring (used as the tool description)
		  2. Type hints on parameters (used for argument parsing)
		  3. A return value (str is safest — the agent reads it)

		Args:
			input_text: Description of this parameter.

		Returns:
			Description of what's returned.
		"""
		return f"Processed: {input_text}"

	def another_tool(self, count: int = 5) -> str:
		"""Another tool with a default parameter.

		Args:
			count: How many items to return. Defaults to 5.

		Returns:
			A formatted result string.
		"""
		items = [f"Item {i+1}" for i in range(count)]
		return "\n".join(items)

	def _private_helper(self):
		"""Methods starting with _ are NOT exposed as tools.
		Use them for internal logic."""
		pass
