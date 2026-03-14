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

	# ── Utility ────────────────────────────────────────────────────

	async def ping(self) -> dict:
		return await self._post("/ping")

	async def status(self) -> dict:
		return await self._post("/status")


def load_workflow(filepath: str) -> dict:
	"""Load a workflow JSON file from disk."""
	with open(filepath) as f:
		return json.load(f)
