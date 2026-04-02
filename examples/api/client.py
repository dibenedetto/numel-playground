"""
Numel API Client
================
Async helper used by the example scripts in this directory.

The current public workflow interface is space-based:
- authenticate
- create or select a space
- save one current workflow into that space
- start executions for the current workflow
"""

import asyncio
import json
import os
import uuid

import httpx


from typing import Any, List, Optional


class NumelClient:
	"""Async client for the Numel REST API."""

	def __init__(
		self,
		base_url: str = "http://localhost:11360",
		username: Optional[str] = None,
		email: Optional[str] = None,
		password: Optional[str] = None,
	):
		self.base_url = base_url.rstrip("/")
		self._http: Optional[httpx.AsyncClient] = None
		self.session_id = f"sess_{uuid.uuid4().hex[:16]}"
		self.token: Optional[str] = None
		self.username = username or os.environ.get("NUMEL_USERNAME", "demo")
		self.email = email or os.environ.get("NUMEL_EMAIL", f"{self.username}@local")
		self.password = password or os.environ.get("NUMEL_PASSWORD", "demo-pass")

	async def __aenter__(self):
		self._http = httpx.AsyncClient(base_url=self.base_url, timeout=120)
		return self

	async def __aexit__(self, *exc):
		if self._http:
			await self._http.aclose()

	def _headers(self, include_json: bool = True) -> dict:
		headers = {}
		if include_json:
			headers["Content-Type"] = "application/json"
		if self.token:
			headers["Authorization"] = f"Bearer {self.token}"
		headers["X-Session-Id"] = self.session_id
		return headers

	async def _post(self, path: str, json_data: Any = None) -> dict:
		resp = await self._http.post(path, json=json_data, headers=self._headers(json_data is not None))
		resp.raise_for_status()
		return resp.json()

	# ── Auth ─────────────────────────────────────────────────────

	async def auth_status(self) -> dict:
		return await self._post("/auth/status")

	async def register(self, username: str, email: str, password: str) -> dict:
		result = await self._post("/auth/register", {"username": username, "email": email, "password": password})
		self.token = result.get("token")
		return result

	async def login(self, username: str, password: str) -> dict:
		result = await self._post("/auth/login", {"username": username, "password": password})
		self.token = result.get("token")
		return result

	async def logout(self) -> dict:
		result = await self._post("/auth/logout")
		self.token = None
		return result

	async def me(self) -> dict:
		return await self._post("/auth/me")

	async def ensure_auth(self, username: Optional[str] = None, email: Optional[str] = None, password: Optional[str] = None) -> dict:
		"""Login if possible, otherwise register the requested user."""
		username = username or self.username
		email = email or self.email
		password = password or self.password

		status = await self.auth_status()
		if not status.get("enabled", False):
			return {"enabled": False}

		try:
			return await self.login(username, password)
		except httpx.HTTPStatusError as exc:
			if exc.response.status_code != 401:
				raise
		return await self.register(username, email, password)

	# ── Core / Space Workflow Interface ─────────────────────────

	async def ping(self) -> dict:
		return await self._post("/ping")

	async def status(self) -> dict:
		return await self._post("/status")

	async def schema(self) -> dict:
		return await self._post("/schema")

	async def current_space(self) -> dict:
		return await self._post("/spaces/current")

	async def list_spaces(self) -> dict:
		return await self._post("/spaces/list")

	async def create_space(self, title: str, slug: Optional[str] = None, description: str = "", visibility: str = "private") -> dict:
		return await self._post(
			"/spaces/create",
			{
				"title": title,
				"slug": slug,
				"description": description,
				"visibility": visibility,
			},
		)

	async def select_space(self, space_id: str) -> dict:
		return await self._post("/spaces/select", {"space_id": space_id})

	async def delete_space(self, space_id: str) -> dict:
		return await self._post("/spaces/delete", {"space_id": space_id})

	async def get_workflow(self) -> dict:
		return await self._post("/workflow/get")

	async def save_workflow(self, workflow: dict) -> dict:
		return await self._post("/workflow/save", {"workflow": workflow})

	async def delete_workflow(self) -> dict:
		return await self._post("/workflow/delete")

	async def start_workflow(self, initial_data: Optional[dict] = None) -> dict:
		return await self._post("/workflow/start", {"initial_data": initial_data or {}})

	async def execution_state(self, execution_id: str) -> dict:
		return await self._post(f"/executions/{execution_id}")

	async def execution_results(self, execution_id: str) -> dict:
		return await self._post(f"/executions/{execution_id}/results")

	async def execution_cancel(self, execution_id: str) -> dict:
		return await self._post(f"/executions/{execution_id}/cancel")

	async def list_executions(self) -> dict:
		return await self._post("/executions/list")

	async def wait(self, execution_id: str, poll: float = 0.5) -> dict:
		"""Poll until execution completes or fails. Returns execution results."""
		while True:
			state = await self.execution_state(execution_id)
			status = (state.get("state") or {}).get("status")
			if status in ("completed", "failed", "cancelled"):
				return await self.execution_results(execution_id)
			await asyncio.sleep(poll)

	# ── Helper shortcuts for examples ───────────────────────────

	async def ensure_space(self, title: str, slug: Optional[str] = None, description: str = "") -> dict:
		spaces = (await self.list_spaces()).get("spaces", [])
		match = next(
			(
				item for item in spaces
				if item.get("title") == title or (slug and item.get("slug") == slug)
			),
			None,
		)
		if match is None:
			created = await self.create_space(title=title, slug=slug, description=description)
			match = created.get("space", {})
		await self.select_space(match["id"])
		return match

	async def replace_current_workflow(self, workflow: dict, *, name: Optional[str] = None) -> dict:
		if name:
			workflow = json.loads(json.dumps(workflow))
			workflow.setdefault("options", {})
			workflow["options"]["name"] = name
		return await self.save_workflow(workflow)

	# ── Generation ───────────────────────────────────────────────

	async def generation_prompt(self, body: Optional[dict] = None) -> dict:
		return await self._post("/generation-prompt", body or {})

	# ── Tool Call ────────────────────────────────────────────────

	async def tool_call(self, node_index: int, args: Optional[dict] = None) -> dict:
		return await self._post("/tool_call", {"node_index": node_index, "args": args or {}})

	# ── Advanced Runtime / Platform Features ────────────────────

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

	# ── Console Agent ────────────────────────────────────────────

	async def console_start(self, model_source: str = None, model_name: str = None, toolkit_names: List[str] = None) -> dict:
		body = {}
		if model_source:
			body["model_source"] = model_source
		if model_name:
			body["model_name"] = model_name
		if toolkit_names:
			body["toolkit_names"] = toolkit_names
		return await self._post("/console/start", body)

	async def console_stop(self) -> dict:
		return await self._post("/console/stop")

	async def console_chat(self, message: str, session_id: str = None, include_context: bool = True) -> dict:
		return await self._post(
			"/console/chat",
			{"message": message, "session_id": session_id, "include_context": include_context},
		)

	async def console_context(self) -> dict:
		return await self._post("/console/context")

	async def console_status(self) -> dict:
		return await self._post("/console/status")

	async def console_toolkits(self) -> List[dict]:
		return await self._post("/console/toolkits")

	# ── File Contents ────────────────────────────────────────────

	async def contents_list(self, node_index: int) -> dict:
		return await self._post(f"/contents/list/{node_index}")

	async def contents_remove(self, node_index: int, ids: List[str]) -> dict:
		return await self._post(f"/contents/remove/{node_index}", {"ids": ids})

	async def upload(self, node_index: int, filepath: str, node_type: str = None) -> dict:
		"""Upload a file to a node."""
		with open(filepath, "rb") as f:
			files = {"files": (os.path.basename(filepath), f)}
			data = {}
			if node_type:
				data["node_type"] = node_type
			resp = await self._http.post(f"/upload/{node_index}", files=files, data=data, headers=self._headers(False))
			resp.raise_for_status()
			return resp.json()

	# ── Documentation ────────────────────────────────────────────

	async def docs_list(self) -> dict:
		return await self._post("/docs")

	async def docs_file(self, filename: str) -> dict:
		return await self._post("/docs/file", {"filename": filename})

	# ── Memory ───────────────────────────────────────────────────

	async def memory_search(self, query: str, n: int = 5, type: str = None) -> List[dict]:
		return await self._post("/console/memory/search", {"query": query, "n_results": n, "type": type})

	async def memory_add(self, content: str, type: str = "general", metadata: dict = None, importance: float = 0.5) -> dict:
		return await self._post(
			"/console/memory/add",
			{"content": content, "type": type, "metadata": metadata or {}, "importance": importance},
		)

	async def memory_recent(self, n: int = 10, type: str = None) -> List[dict]:
		return await self._post("/console/memory/recent", {"n": n, "type": type})

	async def memory_delete(self, id: str) -> dict:
		return await self._post("/console/memory/delete", {"id": id})

	async def memory_clear(self) -> dict:
		return await self._post("/console/memory/clear")

	async def memory_stats(self) -> dict:
		return await self._post("/console/memory/stats")

	# ── Toolkits / Skills ───────────────────────────────────────

	async def toolkit_list(self) -> dict:
		return await self._post("/toolkits/list")

	async def toolkit_inspect(self, name: str) -> dict:
		return await self._post("/toolkits/inspect", {"name": name})

	async def skills_list(self, opts: Optional[dict] = None) -> dict:
		return await self._post("/skills/list", opts or {})

	async def skills_get(self, name: str) -> dict:
		return await self._post("/skills/get", {"name": name})

	# ── Channels ─────────────────────────────────────────────────

	async def channel_types(self) -> List[dict]:
		return await self._post("/channels/types")

	async def channel_list(self) -> List[dict]:
		return await self._post("/channels/list")

	async def channel_add(self, name: str, channel_type: str, token: str = None, auto_start: bool = False, **extras) -> dict:
		return await self._post(
			"/channels/add",
			{
				"name": name,
				"channel_type": channel_type,
				"token": token,
				"auto_start": auto_start,
				"extras": extras,
			},
		)

	async def channel_remove(self, channel_id: str) -> dict:
		return await self._post("/channels/remove", {"channel_id": channel_id})

	async def channel_start(self, channel_id: str) -> dict:
		return await self._post("/channels/start", {"channel_id": channel_id})

	async def channel_stop(self, channel_id: str) -> dict:
		return await self._post("/channels/stop", {"channel_id": channel_id})

	async def channel_send(self, channel_id: str, recipient_id: str, text: str, attachments: list = None) -> dict:
		payload = {"channel_id": channel_id, "recipient_id": recipient_id, "text": text}
		if attachments:
			payload["attachments"] = attachments
		return await self._post("/channels/send", payload)

	# ── Gallery ──────────────────────────────────────────────────

	async def gallery_list(self, category: str = None, tags: List[str] = None, search: str = None) -> List[dict]:
		body = {}
		if category:
			body["category"] = category
		if tags:
			body["tags"] = tags
		if search:
			body["search"] = search
		return await self._post("/gallery/list", body)

	async def gallery_get(self, id: str) -> dict:
		return await self._post("/gallery/get", {"id": id})

	async def gallery_categories(self) -> List[str]:
		return await self._post("/gallery/categories")

	async def gallery_tags(self) -> List[str]:
		return await self._post("/gallery/tags")

	# ── Agent Tasks ──────────────────────────────────────────────

	async def task_list(self) -> List[dict]:
		return await self._post("/agent-tasks/list")

	async def task_get(self, id: str) -> dict:
		return await self._post("/agent-tasks/get", {"id": id})

	async def task_create(self, name: str, prompt: str, trigger: str = "interval", interval_seconds: int = 3600, **kwargs) -> dict:
		return await self._post(
			"/agent-tasks/create",
			{"name": name, "prompt": prompt, "trigger": trigger, "interval_seconds": interval_seconds, **kwargs},
		)

	async def task_remove(self, id: str) -> dict:
		return await self._post("/agent-tasks/remove", {"id": id})

	async def task_start(self, id: str) -> dict:
		return await self._post("/agent-tasks/start", {"id": id})

	async def task_stop(self, id: str) -> dict:
		return await self._post("/agent-tasks/stop", {"id": id})

	async def task_run(self, id: str) -> dict:
		return await self._post("/agent-tasks/run", {"id": id})

	# ── Published Apps ───────────────────────────────────────────

	async def apps_list(self) -> List[dict]:
		return await self._post("/apps/list")

	async def apps_publish(self, workflow: Optional[dict] = None, workflow_name: Optional[str] = None, slug: str = None, title: str = None, description: str = None) -> dict:
		body = {}
		if workflow is not None:
			body["workflow"] = workflow
		if workflow_name:
			body["workflow_name"] = workflow_name
		if slug:
			body["slug"] = slug
		if title:
			body["title"] = title
		if description:
			body["description"] = description
		return await self._post("/apps/publish", body)

	async def apps_unpublish(self, slug: str) -> dict:
		return await self._post("/apps/unpublish", {"slug": slug})


def load_workflow(filepath: str) -> dict:
	"""Load a workflow JSON file from disk."""
	with open(filepath, encoding="utf-8") as f:
		return json.load(f)
