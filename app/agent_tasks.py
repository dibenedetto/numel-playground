# agent_tasks — Autonomous Background Agent Tasks
#
# Agents that run unattended on a schedule or trigger.
# Each task is a console agent invocation with a prompt, running
# on a timer or event source trigger.

import asyncio
import json
import os
import uuid

from   datetime import datetime
from   enum     import Enum
from   fastapi  import FastAPI
from   pydantic import BaseModel, Field
from   typing   import Any, Dict, List, Optional

from   utils    import log_print


_TASKS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "agent_tasks.json")


# =============================================================================
# DATA MODELS
# =============================================================================

class TaskTrigger(str, Enum):
	INTERVAL  = "interval"    # Run every N seconds
	CRON      = "cron"        # Cron expression (future)
	EVENT     = "event"       # Triggered by event bus event
	ONCE      = "once"        # Run once immediately


class TaskStatus(str, Enum):
	STOPPED   = "stopped"
	RUNNING   = "running"
	ERROR     = "error"
	COMPLETED = "completed"   # For once-off tasks


class AgentTaskConfig(BaseModel):
	"""Configuration for an autonomous agent task."""
	id           : str            = Field(default_factory=lambda: f"task_{uuid.uuid4().hex[:8]}")
	name         : str            = ""
	description  : str            = ""
	prompt       : str            = ""       # The instruction sent to the agent each trigger
	trigger      : TaskTrigger    = TaskTrigger.INTERVAL
	interval_sec : int            = 300      # For interval trigger (default 5 min)
	event_type   : Optional[str]  = None     # For event trigger
	cron_expr    : Optional[str]  = None     # For cron trigger, e.g. "0 * * * *" (hourly)
	max_runs     : int            = -1       # -1 = unlimited
	enabled      : bool           = True
	created      : str            = Field(default_factory=lambda: datetime.now().isoformat())


class AgentTaskResult(BaseModel):
	"""Result of a single task execution."""
	run_id    : str = Field(default_factory=lambda: f"run_{uuid.uuid4().hex[:8]}")
	task_id   : str = ""
	timestamp : str = Field(default_factory=lambda: datetime.now().isoformat())
	response  : str = ""
	tool_calls: List[dict] = Field(default_factory=list)
	error     : Optional[str] = None


# =============================================================================
# TASK MANAGER
# =============================================================================

class AgentTaskManager:
	"""Manages autonomous background agent tasks."""

	def __init__(self, console_mgr, config_path: str = _TASKS_PATH):
		self._console_mgr = console_mgr
		self._config_path = config_path
		self._tasks       : Dict[str, AgentTaskConfig] = {}
		self._statuses    : Dict[str, TaskStatus]       = {}
		self._bg_tasks    : Dict[str, asyncio.Task]     = {}     # asyncio background tasks
		self._run_counts  : Dict[str, int]              = {}
		self._last_results: Dict[str, AgentTaskResult]  = {}
		self._event_bus   = None

	def initialize(self, event_bus=None):
		"""Load saved tasks and set up event bus."""
		self._event_bus = event_bus
		self._load()
		log_print(f"Agent tasks initialized ({len(self._tasks)} tasks)")

	# ── CRUD ──────────────────────────────────────────────────────

	def add(self, config: AgentTaskConfig) -> AgentTaskConfig:
		"""Add a new task."""
		self._tasks[config.id] = config
		self._statuses[config.id] = TaskStatus.STOPPED
		self._run_counts[config.id] = 0
		self._save()
		log_print(f"Agent task added: {config.name} ({config.id})")
		return config

	def remove(self, task_id: str) -> bool:
		"""Remove a task (stops it first)."""
		if task_id not in self._tasks:
			return False

		# Stop if running
		if task_id in self._bg_tasks:
			self._bg_tasks[task_id].cancel()
			del self._bg_tasks[task_id]

		del self._tasks[task_id]
		self._statuses.pop(task_id, None)
		self._run_counts.pop(task_id, None)
		self._last_results.pop(task_id, None)
		self._save()
		log_print(f"Agent task removed: {task_id}")
		return True

	def get(self, task_id: str) -> Optional[dict]:
		"""Get task config + status."""
		config = self._tasks.get(task_id)
		if not config:
			return None
		return {
			**config.model_dump(),
			"status":      self._statuses.get(task_id, TaskStatus.STOPPED).value,
			"run_count":   self._run_counts.get(task_id, 0),
			"last_result": self._last_results.get(task_id, AgentTaskResult()).model_dump()
						   if task_id in self._last_results else None,
		}

	def list(self) -> List[dict]:
		"""List all tasks with status."""
		return [self.get(tid) for tid in self._tasks]

	# ── Lifecycle ─────────────────────────────────────────────────

	async def start(self, task_id: str) -> bool:
		"""Start a task."""
		config = self._tasks.get(task_id)
		if not config:
			return False

		if task_id in self._bg_tasks:
			return True  # Already running

		self._statuses[task_id] = TaskStatus.RUNNING

		if config.trigger == TaskTrigger.INTERVAL:
			self._bg_tasks[task_id] = asyncio.create_task(
				self._interval_loop(task_id)
			)
		elif config.trigger == TaskTrigger.ONCE:
			self._bg_tasks[task_id] = asyncio.create_task(
				self._run_once(task_id)
			)
		elif config.trigger == TaskTrigger.EVENT:
			if self._event_bus and config.event_type:
				self._event_bus.subscribe(
					config.event_type,
					lambda evt, tid=task_id: asyncio.create_task(self._run_task(tid))
				)
			self._statuses[task_id] = TaskStatus.RUNNING
		elif config.trigger == TaskTrigger.CRON:
			if not config.cron_expr:
				log_print(f"⚠️ CRON task {config.name} has no cron_expr, skipping")
				self._statuses[task_id] = TaskStatus.ERROR
				return False
			self._bg_tasks[task_id] = asyncio.create_task(
				self._cron_loop(task_id)
			)

		log_print(f"Agent task started: {config.name} ({config.trigger.value})")
		return True

	async def stop(self, task_id: str) -> bool:
		"""Stop a task."""
		if task_id in self._bg_tasks:
			self._bg_tasks[task_id].cancel()
			try:
				await self._bg_tasks[task_id]
			except asyncio.CancelledError:
				pass
			del self._bg_tasks[task_id]

		self._statuses[task_id] = TaskStatus.STOPPED
		return True

	async def start_all(self):
		"""Start all enabled tasks."""
		for task_id, config in self._tasks.items():
			if config.enabled:
				await self.start(task_id)

	async def stop_all(self):
		"""Stop all running tasks."""
		for task_id in list(self._bg_tasks.keys()):
			await self.stop(task_id)

	# ── Execution ─────────────────────────────────────────────────

	async def _interval_loop(self, task_id: str):
		"""Run a task on an interval."""
		config = self._tasks.get(task_id)
		if not config:
			return

		while True:
			await self._run_task(task_id)

			# Check max runs
			if config.max_runs > 0 and self._run_counts.get(task_id, 0) >= config.max_runs:
				self._statuses[task_id] = TaskStatus.COMPLETED
				log_print(f"Agent task completed (max runs reached): {config.name}")
				break

			await asyncio.sleep(config.interval_sec)

	async def _cron_loop(self, task_id: str):
		"""Run task on a cron schedule."""
		try:
			from croniter import croniter
		except ImportError:
			log_print("⚠️ croniter not installed; CRON tasks disabled. Run: pip install croniter")
			self._statuses[task_id] = TaskStatus.ERROR
			return

		config = self._tasks.get(task_id)
		if not config:
			return

		try:
			cron = croniter(config.cron_expr)
		except Exception as e:
			log_print(f"⚠️ Invalid cron expression '{config.cron_expr}': {e}")
			self._statuses[task_id] = TaskStatus.ERROR
			return

		log_print(f"CRON task '{config.name}' starting (expr: {config.cron_expr})")
		while True:
			try:
				next_ts = cron.get_next(float)
				now     = __import__('time').time()
				wait    = max(0, next_ts - now)
				await asyncio.sleep(wait)
				if task_id not in self._tasks:
					break
				await self._run_task(task_id)
				# Check max_runs
				config = self._tasks.get(task_id)
				if not config:
					break
				count = self._run_counts.get(task_id, 0)
				if config.max_runs > 0 and count >= config.max_runs:
					self._statuses[task_id] = TaskStatus.COMPLETED
					log_print(f"CRON task '{config.name}' completed after {count} runs")
					break
			except asyncio.CancelledError:
				break
			except Exception as e:
				log_print(f"CRON task error: {e}")
				await asyncio.sleep(60)

	async def _run_once(self, task_id: str):
		"""Run a task once."""
		await self._run_task(task_id)
		self._statuses[task_id] = TaskStatus.COMPLETED

	async def _run_task(self, task_id: str):
		"""Execute the task's prompt via the console agent."""
		config = self._tasks.get(task_id)
		if not config:
			return

		self._run_counts[task_id] = self._run_counts.get(task_id, 0) + 1
		run_count = self._run_counts[task_id]

		try:
			# Ensure console agent is started
			if not self._console_mgr._started:
				await self._console_mgr.start()

			# Build the prompt with task context
			prompt = (
				f"[Autonomous Task: {config.name}]\n"
				f"[Run #{run_count}, Trigger: {config.trigger.value}]\n"
				f"[Time: {datetime.now().isoformat()}]\n\n"
				f"{config.prompt}"
			)

			result = await self._console_mgr.chat(
				message    = prompt,
				session_id = f"task_{task_id}",
			)

			task_result = AgentTaskResult(
				task_id    = task_id,
				response   = result.get("response", ""),
				tool_calls = result.get("tool_calls", []),
			)
			self._last_results[task_id] = task_result

			log_print(f"Agent task run #{run_count}: {config.name} — "
					  f"{len(task_result.response)} chars response, "
					  f"{len(task_result.tool_calls)} tool calls")

		except Exception as e:
			self._statuses[task_id] = TaskStatus.ERROR
			self._last_results[task_id] = AgentTaskResult(
				task_id = task_id,
				error   = str(e),
			)
			log_print(f"Agent task error: {config.name} — {e}")

	# ── Persistence ───────────────────────────────────────────────

	def _save(self):
		configs = {tid: c.model_dump() for tid, c in self._tasks.items()}
		with open(self._config_path, "w") as f:
			json.dump(configs, f, indent=2)

	def _load(self):
		if not os.path.exists(self._config_path):
			return
		try:
			import credentials as _creds
			raw = _creds.load_json(self._config_path)
			for tid, data in raw.items():
				config = AgentTaskConfig(**data)
				self._tasks[tid] = config
				self._statuses[tid] = TaskStatus.STOPPED
				self._run_counts[tid] = 0
		except Exception as e:
			log_print(f"Failed to load agent tasks: {e}")


# =============================================================================
# API ROUTES
# =============================================================================

class TaskCreateRequest(BaseModel):
	name         : str
	prompt       : str
	description  : str          = ""
	trigger      : str          = "interval"   # interval, once, event, cron
	interval_sec : int          = 300
	event_type   : Optional[str] = None
	cron_expr    : Optional[str] = None
	max_runs     : int          = -1
	enabled      : bool         = True


def setup_agent_tasks_api(app: FastAPI, task_mgr: AgentTaskManager):
	"""Register agent task API routes."""

	@app.post("/agent-tasks/list")
	async def task_list():
		return task_mgr.list()

	@app.post("/agent-tasks/get")
	async def task_get(request: dict):
		task = task_mgr.get(request.get("id", ""))
		if not task:
			return {"error": "not found"}
		return task

	@app.post("/agent-tasks/create")
	async def task_create(request: TaskCreateRequest):
		config = AgentTaskConfig(
			name         = request.name,
			prompt       = request.prompt,
			description  = request.description,
			trigger      = TaskTrigger(request.trigger),
			interval_sec = request.interval_sec,
			event_type   = request.event_type,
			cron_expr    = request.cron_expr,
			max_runs     = request.max_runs,
			enabled      = request.enabled,
		)
		result = task_mgr.add(config)
		return result.model_dump()

	@app.post("/agent-tasks/remove")
	async def task_remove(request: dict):
		return {"removed": task_mgr.remove(request.get("id", ""))}

	@app.post("/agent-tasks/start")
	async def task_start(request: dict):
		ok = await task_mgr.start(request.get("id", ""))
		return {"started": ok}

	@app.post("/agent-tasks/stop")
	async def task_stop(request: dict):
		ok = await task_mgr.stop(request.get("id", ""))
		return {"stopped": ok}

	@app.post("/agent-tasks/run")
	async def task_run_now(request: dict):
		"""Run a task immediately (one-shot), regardless of its trigger."""
		task_id = request.get("id", "")
		if task_id not in task_mgr._tasks:
			return {"error": "not found"}
		await task_mgr._run_task(task_id)
		result = task_mgr._last_results.get(task_id)
		return result.model_dump() if result else {"error": "no result"}
