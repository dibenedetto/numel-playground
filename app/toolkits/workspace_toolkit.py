# workspace_toolkit.py - Live workflow graph editing toolkit for Numel
#
# Lets the agent read and modify the workflow currently open in the UI:
# add/remove nodes, connect them, set field values, run the workflow, and
# collect scored results for optimization loops.
#
# Usage: set ToolkitConfig name="workspace_toolkit",
#        args={"base_url": "http://localhost:11360"}

import json
import time
from typing import Any, Dict, List, Optional

from runtime_toolkit_context import get_runtime_toolkit_context
from toolkits.http_helpers import ToolkitHttpSession


# ── Compact node-type catalogue (agent reference) ────────────────────────────

_NODE_CATALOGUE = """
CONFIG NODES
  backend_config          – Optional agent backend choice when Numel exposes more than one backend
  model_config            – LLM model.    Fields: source (ollama/openai/anthropic/…), name
  agent_options_config    – Agent persona. Fields: name, instructions[], markdown, show_tool_calls
  agent_config            – Wires model+options → agent; backend is implicit unless explicitly exposed
  toolkit_config          – Python toolkit module. Fields: name (module path), args (dict)
  tool_config             – Single inline tool (Python). Fields: name, description, lang, script

FLOW NODES
  start_flow              – Workflow entry point
  end_flow                – Workflow exit point
  preview_flow            – Display output in UI. Fields: hint (text/image/json/audio)
  transform_flow          – Python data transform. Fields: lang, script, input, context
  user_input_flow         – Pause and ask user. Fields: query
  agent_flow              – Run LLM agent. Fields: request, config (→agent_config)
  tool_flow               – Call a toolkit method. Fields: config (→toolkit_config), method, args
  route_flow              – Fan-out: copies input to multiple outputs
  combine_flow            – Merge multiple inputs into one dict
  merge_flow              – Wait for first-arriving input from many wires
  if_else_flow            – Branch on condition. Fields: value, condition (Python expr)
  map_extract_flow        – Extract nested key. Fields: data, key (dot path), default
  http_request_flow       – HTTP call. Fields: url, method, headers, body, timeout_s
  retry_flow              – Retry on failure. Fields: input, script, max_attempts, delay_ms
  accumulate_flow         – Collect loop values. Fields: value, reset
  notify_flow             – Send notification. Fields: channel (webhook/email), url/to, subject, body
  eval_flow               – Score output. Fields: input, script (sets `score` float + `feedback` str)
  delay_flow              – Wait. Fields: duration_ms
  gate_flow               – Block until condition. Fields: condition

LOOP NODES
  loop_start_flow         – Loop header. Fields: condition, max_iter
  loop_end_flow           – Loop footer
  for_each_start_flow     – Iterate list. Fields: items
  for_each_end_flow       – For-each footer
  break_flow              – Break out of loop
  continue_flow           – Skip to next iteration

EVENT SOURCE NODES
  timer_source_flow       – Periodic trigger. Fields: interval_ms, max_triggers, immediate
  webhook_source_flow     – HTTP webhook. Fields: source_id, endpoint, methods, secret
  event_listener_flow     – Wait for registered event. Fields: mode (any/all), sources.*
"""


class WorkspaceToolkit:
	"""Toolkit for reading and modifying the Numel workflow currently open in the UI.
	Supports adding/removing nodes, connecting them, editing field values, and
	running the workflow to collect output scores for optimization loops.
	Args: base_url (server URL, default http://localhost:11360),
	      workflow_name (legacy label; Numel now edits the current workflow in the current space)."""

	__toolkit__ = True

	def __init__(self, base_url: str = "http://localhost:11360", workflow_name: str = "",
				 auth_token: str = "", internal_token: str = "",
				 user_id: Optional[str] = None, local_app = None,
				 runtime_context_id: str = ""):
		if local_app is None and runtime_context_id:
			local_app = get_runtime_toolkit_context(runtime_context_id).get("local_app")
		self._name: Optional[str] = workflow_name or None
		self._wf:   Optional[Dict] = None   # cached dict: {type, nodes, edges}
		self._http = ToolkitHttpSession(
			base_url=base_url,
			auth_token=auth_token,
			internal_token=internal_token,
			user_id=user_id,
			local_app=local_app,
		)

	# ── Internal helpers ──────────────────────────────────────────────────

	def _post(self, path: str, data: Any = None) -> dict:
		return self._http.post_json(path, data)

	@staticmethod
	def _workflow_title(workflow: Optional[Dict[str, Any]]) -> str:
		if not isinstance(workflow, dict):
			return "Current Workflow"
		options = workflow.get("options")
		if isinstance(options, dict):
			name = str(options.get("name", "") or "").strip()
			if name:
				return name
		return "Current Workflow"

	def _ensure(self):
		"""Load the workflow into self._wf if not already cached."""
		if self._wf is not None:
			return
		resp = self._post("/workflow/get")
		self._wf = resp.get("workflow") or {"type": "workflow", "nodes": [], "edges": []}
		self._name = resp.get("name") or self._workflow_title(self._wf)
		if resp.get("workflow") is None:
			self._save_and_notify()

	def _save_and_notify(self) -> str:
		"""Upload self._wf to the server through the current workflow route."""
		self._ensure()
		if self._wf is None:
			return "error: no workflow loaded"
		# Ensure workflow JSON is plain dicts (not Pydantic models)
		wf = self._wf
		if hasattr(wf, 'model_dump'):
			wf = wf.model_dump()
		elif isinstance(wf, dict):
			# Deep-convert any Pydantic models in nodes/edges
			import copy
			wf = copy.deepcopy(wf)
			for i, n in enumerate(wf.get("nodes") or []):
				if n and hasattr(n, 'model_dump'):
					wf["nodes"][i] = n.model_dump()
			for i, e in enumerate(wf.get("edges") or []):
				if e and hasattr(e, 'model_dump'):
					wf["edges"][i] = e.model_dump()
		else:
			return f"error: unexpected workflow type: {type(wf)}"
		try:
			resp = self._post("/workflow/save", {"workflow": wf})
			if resp.get("status") != "saved":
				return f"error saving workflow: {resp}"
			self._name = resp.get("name") or self._workflow_title(wf)
		except Exception as e:
			return f"error saving workflow: {e}"
		return f"ok: saved '{self._name or self._workflow_title(wf)}'"

	def _fmt_workflow(self) -> str:
		"""Return a compact, human-readable summary of the current workflow."""
		self._ensure()
		nodes = self._wf.get("nodes", [])
		edges = self._wf.get("edges", [])
		lines = ["NODES"]
		for i, n in enumerate(nodes):
			if not n:
				lines.append(f"  [{i}] <empty>")
				continue
			pos  = (n.get("extra") or {}).get("pos", [0, 0])
			name = (n.get("extra") or {}).get("name", "")
			ntype = n.get("type", "?")
			lbl  = f"  [{i}] {ntype}"
			if name:
				lbl += f' "{name}"'
			lbl += f"  @({pos[0]},{pos[1]})"
			# show key fields (skip meta keys)
			META = {"type", "extra", "flow_in", "flow_out"}
			kv   = [(k, v) for k, v in n.items()
			        if k not in META and v not in (None, "", [], {})]
			if kv:
				lbl += "  {" + ", ".join(f"{k}: {json.dumps(v)[:40]}" for k, v in kv[:4]) + "}"
			lines.append(lbl)
		lines.append("\nEDGES")
		for e in edges:
			lbl = f"  {e['source']}→{e['target']}  {e['source_slot']}→{e['target_slot']}"
			if e.get("loop"):
				lbl += "  [loop]"
			lines.append(lbl)
		return "\n".join(lines)

	# ── Read methods ──────────────────────────────────────────────────────

	def get_workflow(self) -> str:
		"""Return a compact view of the current workflow: each node with its index,
		type, name, position, and key field values; and each edge with source/target indices
		and slot names. Use node indices in other methods (add_node, remove_node, connect…)."""
		self._ensure()
		return self._fmt_workflow()

	def list_workflows(self) -> str:
		"""Describe the current space and its single editable workflow."""
		space = self._post("/spaces/current").get("space", {}) or {}
		self._ensure()
		title = str(space.get("title", "") or space.get("slug", "") or "Current Space")
		name = self._name or self._workflow_title(self._wf)
		return f"Current space: {title}. Editable workflow: {name}."

	def list_node_types(self) -> str:
		"""List all available node type strings, grouped by category, with their purpose
		and key fields. Use these type strings in add_node()."""
		return _NODE_CATALOGUE.strip()

	def load(self, name: str) -> str:
		"""Reload the current workflow after changing spaces in the UI."""
		self._name = name or self._name
		self._wf   = None
		self._ensure()
		return f"ok: loaded '{self._name or self._workflow_title(self._wf)}'"

	# ── Edit methods ──────────────────────────────────────────────────────

	def add_node(self, node_type: str, fields: Optional[Dict[str, Any]] = None,
	             x: float = 0, y: float = 0, name: str = "") -> str:
		"""Add a new node to the workflow.
		node_type: type string from list_node_types() (e.g. 'transform_flow');
		fields: dict of field values (e.g. {"script": "output = input * 2"});
		x, y: canvas position; name: display label.
		Returns 'ok: added <type> at index N'."""
		self._ensure()
		# Prevent duplicate singleton nodes
		_SINGLETONS = {"start_flow", "end_flow"}
		if node_type in _SINGLETONS:
			for i, n in enumerate(self._wf.get("nodes", [])):
				if n and n.get("type") == node_type:
					return f"ok: {node_type} already exists at index {i} (skipped)"
		node: Dict[str, Any] = {"type": node_type}
		if fields:
			node.update(fields)
		node["extra"] = {"pos": [x, y], "name": name or node_type}
		self._wf.setdefault("nodes", []).append(node)
		idx = len(self._wf["nodes"]) - 1
		return self._save_and_notify() + f", index {idx}"

	def remove_node(self, index: int) -> str:
		"""Remove a node by index, along with all edges connected to it.
		Remaining node indices are renumbered automatically.
		index: 0-based node index from get_workflow(). Returns 'ok' or error."""
		self._ensure()
		nodes = self._wf.get("nodes", [])
		if index < 0 or index >= len(nodes):
			return f"error: index {index} out of range (workflow has {len(nodes)} nodes)"
		nodes.pop(index)
		# Remove edges touching this node; renumber remaining
		kept = []
		for e in self._wf.get("edges", []):
			if e["source"] == index or e["target"] == index:
				continue
			e = dict(e)
			if e["source"] > index: e["source"] -= 1
			if e["target"] > index: e["target"] -= 1
			kept.append(e)
		self._wf["edges"] = kept
		return self._save_and_notify()

	def connect(self, source: int, target: int,
	            source_slot: str, target_slot: str) -> str:
		"""Add an edge between two nodes.
		source/target: 0-based node indices;
		source_slot: output field name on source node (e.g. 'flow_out', 'output', 'config');
		target_slot: input field name on target node (e.g. 'flow_in', 'input', 'request').
		Returns 'ok'."""
		self._ensure()
		edge = {"source": source, "target": target,
		        "source_slot": source_slot, "target_slot": target_slot}
		self._wf.setdefault("edges", []).append(edge)
		return self._save_and_notify()

	def disconnect(self, source: int, target: int,
	               source_slot: Optional[str] = None,
	               target_slot: Optional[str] = None) -> str:
		"""Remove edges between two nodes.
		If source_slot and target_slot are given, removes only that specific edge;
		otherwise removes all edges between the pair.
		Returns 'ok: N removed'."""
		self._ensure()
		before = len(self._wf.get("edges", []))
		def _match(e):
			if e["source"] != source or e["target"] != target:
				return False
			if source_slot and e["source_slot"] != source_slot:
				return False
			if target_slot and e["target_slot"] != target_slot:
				return False
			return True
		self._wf["edges"] = [e for e in self._wf.get("edges", []) if not _match(e)]
		removed = before - len(self._wf["edges"])
		return self._save_and_notify() + f", {removed} edge(s) removed"

	def set_field(self, node_index: int, field: str, value: Any) -> str:
		"""Set a field value on a node.
		node_index: 0-based index; field: field name (e.g. 'script', 'name', 'request');
		value: new value (string, number, list, or dict).
		For the display name use field='extra.name'. Returns 'ok'."""
		self._ensure()
		nodes = self._wf.get("nodes", [])
		if node_index < 0 or node_index >= len(nodes):
			return f"error: index {node_index} out of range"
		if field == "extra.name":
			nodes[node_index].setdefault("extra", {})["name"] = str(value)
		else:
			nodes[node_index][field] = value
		return self._save_and_notify()

	def replace_workflow(self, workflow_json: str) -> str:
		"""Replace the entire workflow with a new one.
		workflow_json: JSON string with 'nodes' and 'edges' arrays (same format as get_workflow
		returns when you call the /get endpoint). Returns 'ok' or error."""
		try:
			wf = json.loads(workflow_json)
		except json.JSONDecodeError as e:
			return f"error: invalid JSON — {e}"
		if "nodes" not in wf:
			return "error: JSON must have a 'nodes' array"
		wf.setdefault("type", "workflow")
		wf.setdefault("edges", [])
		self._wf = wf
		return self._save_and_notify()

	# ── Run / evaluate methods ─────────────────────────────────────────────

	def run(self, initial_data: Optional[Dict[str, Any]] = None,
	        timeout: int = 120) -> str:
		"""Save and execute the current workflow, wait for it to finish, and
		return the results as a JSON string.
		initial_data: optional dict of initial field values (e.g. {"request": "hello"});
		timeout: max seconds to wait (default 120). Returns results JSON or error string."""
		save_result = self._save_and_notify()
		# Save errors are non-fatal — the workflow may already exist in the manager
		if save_result.startswith("error"):
			pass  # try to start anyway
		# Start execution
		payload: Dict[str, Any] = {}
		if initial_data:
			payload["initial_data"] = initial_data
		try:
			resp = self._post("/workflow/start", payload)
		except Exception as e:
			err_str = str(e)
			if "10048" in err_str or "bind" in err_str or "address already in use" in err_str.lower():
				return "error: port conflict — a previous workflow execution is still running. Wait a moment and retry, or cancel the old execution first. This is NOT a workflow design problem."
			return f"error starting workflow: {e}"
		exec_id = resp.get("execution_id")
		if not exec_id:
			return f"error: no execution_id in response: {resp}"
		# Poll until done
		deadline = time.time() + timeout
		while time.time() < deadline:
			time.sleep(1.5)
			try:
				state = self._post(f"/executions/{exec_id}")
				st    = state.get("state", {})
				if isinstance(st, dict):
					status = st.get("status", "")
				else:
					status = str(st)
				if status in ("completed", "failed", "cancelled"):
					break
			except Exception:
				pass
		else:
			return f"error: workflow timed out after {timeout}s (exec_id={exec_id})"
		# Collect results
		try:
			results = self._post(f"/executions/{exec_id}/results")
			return json.dumps(results, default=str, indent=2)
		except Exception as e:
			return f"error fetching results: {e}"

	def get_eval_scores(self, results_json: str) -> str:
		"""Extract all eval_flow scores from a results JSON string returned by run().
		Returns a summary of node indices, scores, and feedback for all eval nodes."""
		try:
			results = json.loads(results_json)
		except Exception:
			return "error: invalid JSON"
		lines = []
		nodes = self._wf.get("nodes", []) if self._wf else []

		if isinstance(results, dict) and isinstance(results.get("node_outputs"), dict):
			for raw_idx, outs in results.get("node_outputs", {}).items():
				try:
					idx = int(raw_idx)
				except Exception:
					idx = raw_idx
				if not isinstance(outs, dict) or "score" not in outs:
					continue
				ntype = nodes[idx].get("type", "?") if isinstance(idx, int) and idx < len(nodes) else "?"
				name  = nodes[idx].get("extra", {}).get("name", "") if isinstance(idx, int) and idx < len(nodes) else ""
				lines.append(f"[{idx}] {ntype} {name!r}: score={outs['score']}, feedback={outs.get('feedback','')!r}")
		else:
			for node_result in (results if isinstance(results, list) else [results]):
				if not isinstance(node_result, dict):
					continue
				idx  = node_result.get("node_index", "?")
				outs = node_result.get("outputs", {})
				if "score" in outs:
					ntype = nodes[idx].get("type", "?") if isinstance(idx, int) and idx < len(nodes) else "?"
					name  = nodes[idx].get("extra", {}).get("name", "") if isinstance(idx, int) and idx < len(nodes) else ""
					lines.append(f"[{idx}] {ntype} {name!r}: score={outs['score']}, feedback={outs.get('feedback','')!r}")
		return "\n".join(lines) if lines else "No eval_flow nodes found in results."
