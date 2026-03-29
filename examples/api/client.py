"""
Numel API Client
================
Lightweight Python client for the Numel Playground backend API.
All examples in this directory use this client.

Usage:
	from client import NumelClient

	async with NumelClient() as c:
		await c.add_workflow(workflow_dict, "my-workflow")
		result = await c.start("my-workflow")
"""

import asyncio
import httpx
import json


from   typing  import Any, List, Optional


class NumelClient:
	"""Async client for the Numel Playground REST + WebSocket API."""

	def __init__(self, base_url: str = "http://localhost:11360"):
		self.base_url = base_url.rstrip("/")
		self._http: Optional[httpx.AsyncClient] = None

	async def __aenter__(self):
		self._http = httpx.AsyncClient(base_url=self.base_url, timeout=120)
		return self

	async def __aexit__(self, *exc):
		if self._http:
			await self._http.aclose()

	async def _post(self, path: str, json_data: Any = None) -> dict:
		resp = await self._http.post(path, json=json_data)
		resp.raise_for_status()
		return resp.json()

	# ── Workflow Management ────────────────────────────────────────

	async def add(self, workflow: dict, name: Optional[str] = None) -> dict:
		return await self._post("/add", {"workflow": workflow, "name": name})

	async def remove(self, name: str) -> dict:
		return await self._post(f"/remove/{name}")

	async def get(self, name: str) -> dict:
		return await self._post(f"/get/{name}")

	async def list(self) -> List[str]:
		r = await self._post("/list")
		return r.get("names", [])

	# ── Execution ──────────────────────────────────────────────────

	async def start(self, name: str, **exec_opts) -> str:
		"""Start a workflow. Returns execution_id."""
		body = {"name": name}
		if exec_opts:
			body["initial_data"] = exec_opts
		r = await self._post("/start", body)
		return r["execution_id"]

	async def state(self, execution_id: str) -> dict:
		return await self._post(f"/exec_state/{execution_id}")

	async def results(self, execution_id: str) -> dict:
		return await self._post(f"/exec_results/{execution_id}")

	async def cancel(self, execution_id: str) -> dict:
		return await self._post(f"/exec_cancel/{execution_id}")

	async def wait(self, execution_id: str, poll: float = 0.5) -> dict:
		"""Poll until execution completes or fails. Returns results."""
		while True:
			r = await self.state(execution_id)
			s = r.get("state", {})
			status = s.get("status") if isinstance(s, dict) else getattr(s, "status", None)
			if status in ("completed", "failed"):
				return await self.results(execution_id)
			await asyncio.sleep(poll)

	# ── Batch ──────────────────────────────────────────────────────

	async def batch_start(self, workflows: List[dict]) -> dict:
		"""Start multiple workflows in parallel.
		workflows: list of {"name": "...", "initial_data": {...}}
		"""
		return await self._post("/batch/start", {"workflows": workflows})

	async def batch_state(self, batch_id: str) -> dict:
		return await self._post(f"/batch/state/{batch_id}")

	async def batch_cancel(self, batch_id: str) -> dict:
		return await self._post(f"/batch/cancel/{batch_id}")

	async def batch_wait(self, batch_id: str, poll: float = 0.5) -> dict:
		while True:
			r = await self.batch_state(batch_id)
			if r.get("status") in ("completed", "failed", "cancelled"):
				return r
			await asyncio.sleep(poll)

	# ── Compose (Pipeline) ─────────────────────────────────────────

	async def compose(self, pipeline: List[dict]) -> dict:
		"""Run a sequential pipeline of workflows.
		pipeline: list of {"workflow_name": "...", "input_map": {...}}
		"""
		return await self._post("/compose", {"pipeline": pipeline})

	async def compose_state(self, compose_id: str) -> dict:
		return await self._post(f"/compose/state/{compose_id}")

	async def compose_cancel(self, compose_id: str) -> dict:
		return await self._post(f"/compose/cancel/{compose_id}")

	# ── Persistence ────────────────────────────────────────────────

	async def save(self, name: str) -> dict:
		return await self._post(f"/save/{name}")

	async def save_all(self) -> dict:
		return await self._post("/save_all")

	async def load(self, filepath: str, name: Optional[str] = None) -> dict:
		return await self._post("/load", {"filepath": filepath, "name": name})

	async def load_all(self) -> dict:
		return await self._post("/load_all")

	# ── Workspaces ─────────────────────────────────────────────────

	async def workspace_create(self, name: str, description: Optional[str] = None) -> dict:
		return await self._post("/workspace/create", None)  # query params
		# Actually needs query params, let's use params:

	async def workspace_list(self) -> dict:
		return await self._post("/workspace/list")

	async def workspace_delete(self, workspace_id: str) -> dict:
		return await self._post(f"/workspace/delete/{workspace_id}")

	async def ws_add(self, workspace_id: str, workflow: dict, name: Optional[str] = None) -> dict:
		return await self._post(f"/workspace/{workspace_id}/add", {"workflow": workflow, "name": name})

	async def ws_start(self, workspace_id: str, name: str, **exec_opts) -> str:
		body = {"name": name}
		if exec_opts:
			body["initial_data"] = exec_opts
		r = await self._post(f"/workspace/{workspace_id}/start", body)
		return r["execution_id"]

	async def ws_results(self, workspace_id: str, execution_id: str) -> dict:
		return await self._post(f"/workspace/{workspace_id}/exec_results/{execution_id}")

	async def ws_state(self, workspace_id: str, execution_id: str) -> dict:
		return await self._post(f"/workspace/{workspace_id}/exec_state/{execution_id}")

	# ── Schema & Generation ────────────────────────────────────────

	async def schema(self) -> dict:
		return await self._post("/schema")

	async def generation_prompt(self, tool_names: List[str] = None, toolkit_names: List[str] = None) -> dict:
		body = {}
		if tool_names:    body["tool_names"]    = tool_names
		if toolkit_names: body["toolkit_names"] = toolkit_names
		return await self._post("/generation-prompt", body)

	async def generate_workflow(self, description: str, **kwargs) -> dict:
		body = {"description": description, **kwargs}
		return await self._post("/generate-workflow", body)

	# ── Tool Call ──────────────────────────────────────────────────

	async def tool_call(self, node_index: int, args: dict = None) -> dict:
		return await self._post("/tool_call", {"node_index": node_index, "args": args or {}})

	# ── Templates ──────────────────────────────────────────────────

	async def templates_list(self) -> List[dict]:
		r = await self._post("/templates/list")
		return r.get("templates", [])

	async def templates_get(self, template_id: str) -> dict:
		r = await self._post(f"/templates/get/{template_id}")
		return r.get("template", {})

	async def templates_save(self, template: dict) -> dict:
		return await self._post("/templates/save", {"template": template})

	async def templates_delete(self, template_id: str) -> dict:
		return await self._post(f"/templates/delete/{template_id}")

	async def templates_rename(self, template_id: str, new_name: str) -> dict:
		return await self._post(f"/templates/rename/{template_id}", {"name": new_name})

	# ── Event Sources ──────────────────────────────────────────────

	async def event_sources_list(self) -> dict:
		return await self._post("/event-sources/list")

	async def event_sources_status(self) -> dict:
		return await self._post("/event-sources/status")

	async def event_source_get(self, source_id: str) -> dict:
		return await self._post(f"/event-sources/get/{source_id}")

	async def event_source_create_timer(self, interval: float, event_type: str = "timer", **kwargs) -> dict:
		return await self._post("/event-sources/timer", {"interval": interval, "event_type": event_type, **kwargs})

	async def event_source_start(self, source_id: str) -> dict:
		return await self._post(f"/event-sources/{source_id}/start")

	async def event_source_stop(self, source_id: str) -> dict:
		return await self._post(f"/event-sources/{source_id}/stop")

	async def event_source_delete(self, source_id: str) -> dict:
		return await self._post(f"/event-sources/delete/{source_id}")

	# ── Console Agent ──────────────────────────────────────────────

	async def console_start(self, model_source: str = None, model_name: str = None,
	                        toolkit_names: List[str] = None) -> dict:
		body = {}
		if model_source:  body["model_source"]  = model_source
		if model_name:    body["model_name"]    = model_name
		if toolkit_names: body["toolkit_names"] = toolkit_names
		return await self._post("/console/start", body)

	async def console_stop(self) -> dict:
		return await self._post("/console/stop")

	async def console_chat(self, message: str, session_id: str = None, include_context: bool = True) -> dict:
		return await self._post("/console/chat", {
			"message": message, "session_id": session_id, "include_context": include_context,
		})

	async def console_context(self) -> dict:
		return await self._post("/console/context")

	async def console_status(self) -> dict:
		return await self._post("/console/status")

	async def console_toolkits(self) -> List[dict]:
		return await self._post("/console/toolkits")

	# ── File Contents ──────────────────────────────────────────────

	async def contents_list(self, node_index: int) -> dict:
		return await self._post(f"/contents/list/{node_index}")

	async def contents_remove(self, node_index: int, ids: List[str]) -> dict:
		return await self._post(f"/contents/remove/{node_index}", {"ids": ids})

	async def upload(self, node_index: int, filepath: str, node_type: str = None) -> dict:
		"""Upload a file to a node."""
		import os
		with open(filepath, "rb") as f:
			files = {"files": (os.path.basename(filepath), f)}
			data  = {}
			if node_type: data["node_type"] = node_type
			resp = await self._http.post(f"/upload/{node_index}", files=files, data=data)
			resp.raise_for_status()
			return resp.json()

	# ── Documentation ──────────────────────────────────────────────

	async def docs_list(self) -> dict:
		return await self._post("/docs")

	async def docs_file(self, filename: str) -> dict:
		return await self._post("/docs/file", {"filename": filename})

	# ── Memory ─────────────────────────────────────────────────────

	async def memory_search(self, query: str, n: int = 5, type: str = None) -> List[dict]:
		return await self._post("/console/memory/search", {"query": query, "n_results": n, "type": type})

	async def memory_add(self, content: str, type: str = "general",
						 metadata: dict = None, importance: float = 0.5) -> dict:
		return await self._post("/console/memory/add", {
			"content": content, "type": type,
			"metadata": metadata or {}, "importance": importance,
		})

	async def memory_recent(self, n: int = 10, type: str = None) -> List[dict]:
		return await self._post("/console/memory/recent", {"n": n, "type": type})

	async def memory_delete(self, id: str) -> dict:
		return await self._post("/console/memory/delete", {"id": id})

	async def memory_clear(self) -> dict:
		return await self._post("/console/memory/clear")

	async def memory_stats(self) -> dict:
		return await self._post("/console/memory/stats")

	# ── Channels ───────────────────────────────────────────────────

	async def channel_types(self) -> List[dict]:
		return await self._post("/channels/types")

	async def channel_list(self) -> List[dict]:
		return await self._post("/channels/list")

	async def channel_add(self, name: str, channel_type: str, token: str = None,
						  auto_start: bool = False, **extras) -> dict:
		return await self._post("/channels/add", {
			"name": name, "channel_type": channel_type,
			"token": token, "auto_start": auto_start, "extras": extras,
		})

	async def channel_remove(self, channel_id: str) -> dict:
		return await self._post("/channels/remove", {"channel_id": channel_id})

	async def channel_start(self, channel_id: str) -> dict:
		return await self._post("/channels/start", {"channel_id": channel_id})

	async def channel_stop(self, channel_id: str) -> dict:
		return await self._post("/channels/stop", {"channel_id": channel_id})

	async def channel_send(self, channel_id: str, recipient_id: str, text: str,
						  attachments: list = None) -> dict:
		payload = {"channel_id": channel_id, "recipient_id": recipient_id, "text": text}
		if attachments:
			payload["attachments"] = attachments
		return await self._post("/channels/send", payload)

	# ── Gallery ────────────────────────────────────────────────────

	async def gallery_list(self, category: str = None, tags: List[str] = None,
						   search: str = None) -> List[dict]:
		body = {}
		if category: body["category"] = category
		if tags:     body["tags"]     = tags
		if search:   body["search"]   = search
		return await self._post("/gallery/list", body)

	async def gallery_get(self, id: str) -> dict:
		return await self._post("/gallery/get", {"id": id})

	async def gallery_publish(self, workflow_name: str, title: str = None,
							  description: str = None, category: str = None,
							  tags: List[str] = None) -> dict:
		body = {"workflow_name": workflow_name}
		if title:       body["title"]       = title
		if description: body["description"] = description
		if category:    body["category"]    = category
		if tags:        body["tags"]        = tags
		return await self._post("/gallery/publish", body)

	async def gallery_remove(self, id: str) -> dict:
		return await self._post("/gallery/remove", {"id": id})

	async def gallery_categories(self) -> List[str]:
		return await self._post("/gallery/categories")

	async def gallery_tags(self) -> List[str]:
		return await self._post("/gallery/tags")

	# ── Agent Tasks ────────────────────────────────────────────────

	async def task_list(self) -> List[dict]:
		return await self._post("/agent-tasks/list")

	async def task_get(self, id: str) -> dict:
		return await self._post("/agent-tasks/get", {"id": id})

	async def task_create(self, name: str, prompt: str, trigger: str = "interval",
						  interval_seconds: int = 3600, **kwargs) -> dict:
		body = {
			"name": name, "prompt": prompt,
			"trigger": trigger, "interval_seconds": interval_seconds,
			**kwargs,
		}
		return await self._post("/agent-tasks/create", body)

	async def task_remove(self, id: str) -> dict:
		return await self._post("/agent-tasks/remove", {"id": id})

	async def task_start(self, id: str) -> dict:
		return await self._post("/agent-tasks/start", {"id": id})

	async def task_stop(self, id: str) -> dict:
		return await self._post("/agent-tasks/stop", {"id": id})

	async def task_run(self, id: str) -> dict:
		"""Run a task immediately (one-shot)."""
		return await self._post("/agent-tasks/run", {"id": id})

	# ── Published Apps ─────────────────────────────────────────────

	async def apps_list(self) -> List[dict]:
		return await self._post("/apps/list")

	async def apps_publish(self, workflow_name: str, slug: str = None,
						   title: str = None, description: str = None) -> dict:
		body = {"workflow_name": workflow_name}
		if slug:        body["slug"]        = slug
		if title:       body["title"]       = title
		if description: body["description"] = description
		return await self._post("/apps/publish", body)

	async def apps_unpublish(self, slug: str) -> dict:
		return await self._post("/apps/unpublish", {"slug": slug})

	# ── Utility ────────────────────────────────────────────────────

	async def ping(self) -> dict:
		return await self._post("/ping")

	async def status(self) -> dict:
		return await self._post("/status")


def load_workflow(filepath: str) -> dict:
	"""Load a workflow JSON file from disk."""
	with open(filepath) as f:
		return json.load(f)
