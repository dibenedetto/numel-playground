# console_toolkit — workspace introspection tools for the console agent


class ConsoleToolkit:
	"""Console Assistant Toolkit for inspecting the current workspace.

Provides tools to inspect the user's workflow graph, available node types,
tools, toolkits, and execution state. All tools are read-only.

Available operations:
- get_workflow_summary: overview of current workflow nodes and edges
- get_node_details: detailed config for a specific node
- get_execution_status: current/recent execution state and results
- get_available_node_types: all registered node types with descriptions
- get_available_tools: available tool/toolkit modules
- validate_workflow: check for missing connections and config errors"""

	__toolkit__ = True

	def __init__(self, workspace_mgr, user_id=None):
		self._ws_mgr = workspace_mgr
		self._user_id = user_id

	def _get_ws(self):
		return self._ws_mgr.resolve_workspace_sync(self._user_id)

	def _get_workflow(self):
		"""Get the first loaded workflow object from the user's workspace, or None."""
		ws = self._get_ws()
		mgr = ws.manager
		if not mgr._workflows:
			return None
		first_data = next(iter(mgr._workflows.values()))
		wf = first_data.get("workflow") if isinstance(first_data, dict) else first_data
		return wf

	def get_workflow_summary(self) -> str:
		"""Get a summary of the current workflow: node types, names, edges, and status.

		Returns:
			Formatted overview of the loaded workflow, or a message if none is loaded.
		"""
		wf = self._get_workflow()
		if not wf:
			return "No workflow is currently loaded."

		nodes = getattr(wf, 'nodes', None) or []
		edges = getattr(wf, 'edges', None) or []

		lines = [f"Workflow: {getattr(wf, 'name', 'unnamed')}"]
		lines.append(f"Nodes: {len(nodes)}")
		for i, node in enumerate(nodes):
			if node is None:
				continue
			name = getattr(node, 'name', None) or getattr(node, 'type', '?')
			ntype = getattr(node, 'type', '?')
			extra = ""
			if ntype == "model_config":
				extra = f" (source={getattr(node, 'source', '?')}, model={getattr(node, 'name', '?')})"
			elif ntype == "tool_config":
				extra = f" (module={getattr(node, 'name', '?')})"
			elif ntype == "toolkit_config":
				extra = f" (module={getattr(node, 'name', '?')})"
			elif ntype == "transform_flow":
				script = getattr(node, 'script', '') or ''
				extra = f" (script={script[:60]}{'...' if len(script) > 60 else ''})"
			lines.append(f"  [{i}] {ntype}: {name}{extra}")

		lines.append(f"\nEdges: {len(edges)}")
		for edge in edges:
			src = getattr(edge, 'source', '?')
			tgt = getattr(edge, 'target', '?')
			ss = getattr(edge, 'source_slot', '?')
			ts = getattr(edge, 'target_slot', '?')
			lines.append(f"  {src}.{ss} → {tgt}.{ts}")

		return "\n".join(lines)

	def get_node_details(self, node_index: int) -> str:
		"""Get detailed configuration for a specific node by index.

		Args:
			node_index: Zero-based index of the node in the workflow.

		Returns:
			Formatted node configuration details.
		"""
		wf = self._get_workflow()
		if not wf:
			return "No workflow is currently loaded."

		nodes = getattr(wf, 'nodes', None) or []
		if node_index < 0 or node_index >= len(nodes):
			return f"Invalid node index {node_index}. Valid range: 0-{len(nodes) - 1}"

		node = nodes[node_index]
		if node is None:
			return f"Node {node_index} is empty/null."

		lines = [f"Node [{node_index}]"]
		# Dump all non-private fields
		for key, value in node.__dict__.items():
			if key.startswith('_'):
				continue
			lines.append(f"  {key}: {value}")
		return "\n".join(lines)

	def get_execution_status(self) -> str:
		"""Get the current/recent execution state and results.

		Returns:
			Execution status summary, or a message if no execution has run.
		"""
		ws = self._get_ws()
		engine = ws.engine
		if not engine:
			return "No execution engine available."

		# Check for active executions
		active = getattr(engine, '_active_executions', {})
		if not active:
			# Check for completed
			results = getattr(engine, '_execution_results', {})
			if not results:
				return "No executions have been run yet."

			# Show most recent result
			lines = ["Recent executions:"]
			for exec_id, result in list(results.items())[-3:]:
				status = result.get('status', '?')
				lines.append(f"  {exec_id[:12]}... status={status}")
				outputs = result.get('node_outputs', {})
				if outputs:
					for nidx, out in list(outputs.items())[:5]:
						lines.append(f"    node {nidx}: {str(out)[:100]}")
			return "\n".join(lines)

		lines = ["Active executions:"]
		for exec_id, state in active.items():
			status = getattr(state, 'status', '?')
			lines.append(f"  {exec_id[:12]}... status={status}")
		return "\n".join(lines)

	def get_available_node_types(self) -> str:
		"""List all registered workflow node types with descriptions.

		Returns:
			Formatted list of available node types.
		"""
		import inspect
		import schema as _schema
		lines = ["Available node types:"]
		seen = set()
		for attr_name in dir(_schema):
			cls = getattr(_schema, attr_name, None)
			if not inspect.isclass(cls):
				continue
			# Only Pydantic model classes with a 'type' field
			fields = getattr(cls, 'model_fields', None)
			if not fields or 'type' not in fields:
				continue
			type_val = fields['type'].default
			if not isinstance(type_val, str) or type_val in seen:
				continue
			seen.add(type_val)
			doc = (cls.__doc__ or '').strip().split('\n')[0]
			lines.append(f"  {type_val}: {doc}")
		return "\n".join(lines)

	def get_available_tools(self) -> str:
		"""List available tool and toolkit modules that can be used in workflows.

		Returns:
			Formatted list of tools and toolkits with descriptions.
		"""
		import os
		import importlib

		lines = ["Available tools and toolkits:"]

		# Scan toolkits directories
		for search_dir in ["app/toolkits", "contrib/toolkits"]:
			abs_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), search_dir)
			if not os.path.isdir(abs_dir):
				continue
			for fname in sorted(os.listdir(abs_dir)):
				if fname.startswith('_') or not fname.endswith('.py'):
					continue
				mod_name = fname[:-3]
				# Skip self
				if mod_name == 'console_toolkit':
					continue
				try:
					mod = importlib.import_module(f"toolkits.{mod_name}")
					for attr_name in dir(mod):
						obj = getattr(mod, attr_name)
						if isinstance(obj, type) and getattr(obj, '__toolkit__', False):
							doc = obj.__doc__ or ''
							lines.append(f"\n  [Toolkit] {mod_name}")
							if doc:
								lines.append(f"    {doc.strip().split(chr(10))[0]}")
				except Exception:
					lines.append(f"  [Toolkit] {mod_name} (failed to load)")

		# List built-in agno tools
		lines.append("\n  Built-in tools (agno):")
		lines.append("    tools.duckduckgo - Web search")
		lines.append("    tools.reasoning - Reasoning/chain-of-thought")

		return "\n".join(lines)

	def validate_workflow(self) -> str:
		"""Check the current workflow for common issues: missing connections, unlinked nodes, config errors.

		Returns:
			List of warnings/errors found, or a success message.
		"""
		wf = self._get_workflow()
		if not wf:
			return "No workflow is currently loaded."

		nodes = getattr(wf, 'nodes', None) or []
		edges = getattr(wf, 'edges', None) or []
		issues = []

		# Build connectivity map
		connected_as_target = set()
		connected_as_source = set()
		for edge in edges:
			src = getattr(edge, 'source', None)
			tgt = getattr(edge, 'target', None)
			if src is not None:
				connected_as_source.add(src)
			if tgt is not None:
				connected_as_target.add(tgt)

		for i, node in enumerate(nodes):
			if node is None:
				issues.append(f"[WARNING] Node {i} is null")
				continue

			ntype = getattr(node, 'type', '?')

			# Check for isolated nodes (no incoming or outgoing)
			if i not in connected_as_target and i not in connected_as_source:
				if ntype not in ('start_flow',):
					issues.append(f"[WARNING] Node {i} ({ntype}) is completely disconnected")

			# Config nodes should be connected as source
			if ntype.endswith('_config') and i not in connected_as_source:
				issues.append(f"[WARNING] Config node {i} ({ntype}) has no outgoing connections — it's unused")

			# Agent config needs model and options
			if ntype == 'agent_config':
				has_model = any(
					getattr(e, 'target', None) == i and getattr(e, 'target_slot', '') == 'model'
					for e in edges
				)
				has_options = any(
					getattr(e, 'target', None) == i and getattr(e, 'target_slot', '') == 'options'
					for e in edges
				)
				if not has_model:
					issues.append(f"[ERROR] Agent config node {i} has no model connection")
				if not has_options:
					issues.append(f"[INFO] Agent config node {i} has no options connection (will use defaults)")

		if not issues:
			return "No issues found. Workflow looks good!"

		return f"Found {len(issues)} issue(s):\n" + "\n".join(issues)
