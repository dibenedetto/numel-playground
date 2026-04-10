# console_toolkit — current-space introspection tools for the console agent

from __future__ import annotations

from typing import Any, Dict, Optional

from toolkits.http_helpers import ToolkitHttpSession


class ConsoleToolkit:
	"""Console Assistant Toolkit for inspecting the current space and workflow.

Provides tools to inspect the current workflow graph, available node types,
tools, toolkits, and recent execution state. All tools are read-only.

Available operations:
- get_workflow_summary: overview of current workflow nodes and edges
- get_node_details: detailed config for a specific node
- get_execution_status: current/recent execution state and results
- get_available_node_types: all registered node types with descriptions
- get_available_tools: available tool/toolkit modules
- validate_workflow: check for missing connections and config errors"""

	__toolkit__ = True

	def __init__(
		self,
		base_url: str = "http://localhost:11360",
		auth_token: str = "",
		internal_token: str = "",
		user_id: Optional[str] = None,
		local_app = None,
	):
		self._http = ToolkitHttpSession(
			base_url=base_url,
			auth_token=auth_token,
			internal_token=internal_token,
			user_id=user_id,
			local_app=local_app,
		)

	def _post(self, path: str, body: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
		return self._http.post_json(path, body)

	def _get_workflow_doc(self) -> Optional[Dict[str, Any]]:
		data = self._post("/workflow/get")
		workflow = data.get("workflow")
		return workflow if isinstance(workflow, dict) else None

	def _get_execution_rows(self) -> list:
		return list((self._post("/executions/list").get("executions") or []))

	def get_workflow_summary(self) -> str:
		"""Get a summary of the current workflow: node types, names, edges, and status."""
		wf = self._get_workflow_doc()
		if not wf:
			return "No workflow is currently loaded in the current space."

		nodes = wf.get("nodes") or []
		edges = wf.get("edges") or []
		options = wf.get("options") if isinstance(wf.get("options"), dict) else {}
		name = str(options.get("name", "") or "Current Workflow")

		lines = [f"Workflow: {name}", f"Nodes: {len(nodes)}"]
		for i, node in enumerate(nodes):
			if not isinstance(node, dict):
				continue
			extra = node.get("extra") if isinstance(node.get("extra"), dict) else {}
			node_name = str(extra.get("name", "") or node.get("type", "?"))
			ntype = str(node.get("type", "?"))
			more = ""
			if ntype == "model_config":
				more = f" (source={node.get('source', '?')}, model={node.get('name', '?')})"
			elif ntype in ("tool_config", "toolkit_config"):
				more = f" (module={node.get('name', '?')})"
			elif ntype == "transform_flow":
				script = str(node.get("script", "") or "")
				more = f" (script={script[:60]}{'...' if len(script) > 60 else ''})"
			lines.append(f"  [{i}] {ntype}: {node_name}{more}")

		lines.append(f"\nEdges: {len(edges)}")
		for edge in edges:
			if not isinstance(edge, dict):
				continue
			src = edge.get("source", "?")
			tgt = edge.get("target", "?")
			ss = edge.get("source_slot", "?")
			ts = edge.get("target_slot", "?")
			lines.append(f"  {src}.{ss} -> {tgt}.{ts}")

		return "\n".join(lines)

	def get_node_details(self, node_index: int) -> str:
		"""Get detailed configuration for a specific node by index."""
		wf = self._get_workflow_doc()
		if not wf:
			return "No workflow is currently loaded in the current space."

		nodes = wf.get("nodes") or []
		if node_index < 0 or node_index >= len(nodes):
			return f"Invalid node index {node_index}. Valid range: 0-{len(nodes) - 1}"

		node = nodes[node_index]
		if not isinstance(node, dict):
			return f"Node {node_index} is empty/null."

		lines = [f"Node [{node_index}]"]
		for key, value in node.items():
			lines.append(f"  {key}: {value}")
		return "\n".join(lines)

	def get_execution_status(self) -> str:
		"""Get the current/recent execution state and results."""
		executions = self._get_execution_rows()
		if not executions:
			return "No executions have been run in the current space yet."

		active = [row for row in executions if str(row.get("status", "")).lower() in ("queued", "running")]
		if active:
			lines = ["Active executions:"]
			for row in active[:5]:
				lines.append(f"  {row.get('execution_id', '')[:12]}... status={row.get('status', '?')}")
			return "\n".join(lines)

		lines = ["Recent executions:"]
		for row in executions[:3]:
			execution_id = str(row.get("execution_id", "") or "")
			status = row.get("status", "?")
			lines.append(f"  {execution_id[:12]}... status={status}")
			outputs = row.get("outputs", {}) or {}
			if isinstance(outputs, dict):
				for node_id, out in list(outputs.items())[:5]:
					lines.append(f"    node {node_id}: {str(out)[:100]}")
		return "\n".join(lines)

	def get_available_node_types(self) -> str:
		"""List all registered workflow node types with descriptions."""
		import inspect
		import schema as _schema

		lines = ["Available node types:"]
		seen = set()
		for attr_name in dir(_schema):
			cls = getattr(_schema, attr_name, None)
			if not inspect.isclass(cls):
				continue
			fields = getattr(cls, "model_fields", None)
			if not fields or "type" not in fields:
				continue
			type_val = fields["type"].default
			if not isinstance(type_val, str) or type_val in seen:
				continue
			seen.add(type_val)
			doc = (cls.__doc__ or "").strip().split("\n")[0]
			lines.append(f"  {type_val}: {doc}")
		return "\n".join(lines)

	def get_available_tools(self) -> str:
		"""List available tool and toolkit modules that can be used in workflows."""
		import importlib
		import os

		lines = ["Available tools and toolkits:"]
		for search_dir in ["app/toolkits", "contrib/toolkits"]:
			abs_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), search_dir)
			if not os.path.isdir(abs_dir):
				continue
			for fname in sorted(os.listdir(abs_dir)):
				if fname.startswith("_") or not fname.endswith(".py"):
					continue
				mod_name = fname[:-3]
				if mod_name == "console_toolkit":
					continue
				try:
					mod = importlib.import_module(f"toolkits.{mod_name}")
					for attr_name in dir(mod):
						obj = getattr(mod, attr_name)
						if isinstance(obj, type) and getattr(obj, "__toolkit__", False):
							doc = obj.__doc__ or ""
							lines.append(f"\n  [Toolkit] {mod_name}")
							if doc:
								lines.append(f"    {doc.strip().split(chr(10))[0]}")
				except Exception:
					lines.append(f"  [Toolkit] {mod_name} (failed to load)")

		lines.append("\n  Built-in agent tools:")
		lines.append("    tools.duckduckgo - Web search")
		lines.append("    tools.reasoning - Reasoning/chain-of-thought")
		return "\n".join(lines)

	def validate_workflow(self) -> str:
		"""Check the current workflow for common issues."""
		wf = self._get_workflow_doc()
		if not wf:
			return "No workflow is currently loaded in the current space."

		nodes = wf.get("nodes") or []
		edges = wf.get("edges") or []
		issues = []

		connected_as_target = set()
		connected_as_source = set()
		for edge in edges:
			if not isinstance(edge, dict):
				continue
			src = edge.get("source")
			tgt = edge.get("target")
			if src is not None:
				connected_as_source.add(src)
			if tgt is not None:
				connected_as_target.add(tgt)

		for i, node in enumerate(nodes):
			if not isinstance(node, dict):
				issues.append(f"[WARNING] Node {i} is null")
				continue

			ntype = str(node.get("type", "?"))
			if i not in connected_as_target and i not in connected_as_source and ntype not in ("start_flow",):
				issues.append(f"[WARNING] Node {i} ({ntype}) is completely disconnected")

			if ntype.endswith("_config") and i not in connected_as_source:
				issues.append(f"[WARNING] Config node {i} ({ntype}) has no outgoing connections")

			if ntype == "agent_config":
				has_model = any(
					isinstance(edge, dict)
					and edge.get("target") == i
					and edge.get("target_slot") == "model"
					for edge in edges
				)
				has_options = any(
					isinstance(edge, dict)
					and edge.get("target") == i
					and edge.get("target_slot") == "options"
					for edge in edges
				)
				if not has_model:
					issues.append(f"[ERROR] Agent config node {i} has no model connection")
				if not has_options:
					issues.append(f"[INFO] Agent config node {i} has no options connection (will use defaults)")

		if not issues:
			return "No issues found. Workflow looks good!"
		return f"Found {len(issues)} issue(s):\n" + "\n".join(issues)
