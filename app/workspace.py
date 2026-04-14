# workspace — Multi-workspace management layer
#
# Each workspace owns its own WorkflowManager + WorkflowEngine pair,
# sharing a single global EventBus.  A "default" workspace is always
# created so that existing (pre-workspace) API calls continue to work.

import asyncio
import uuid


from   datetime  import datetime
from   pathlib   import Path
from   typing    import Any, Dict, List, Optional


from   engine    import WorkflowEngine
from   event_bus import EventType, EventBus
from   manager   import WorkflowManager


class WorkspaceState:
	"""An isolated workspace containing its own manager and engine."""

	def __init__(self, workspace_id: str, name: str, description: Optional[str],
				 manager: WorkflowManager, engine: WorkflowEngine):
		self.workspace_id : str              = workspace_id
		self.name         : str              = name
		self.description  : Optional[str]    = description
		self.created_at   : str              = datetime.now().isoformat()
		self.manager      : WorkflowManager  = manager
		self.engine       : WorkflowEngine   = engine

	def to_dict(self) -> dict:
		return {
			"workspace_id" : self.workspace_id,
			"name"         : self.name,
			"description"  : self.description,
			"created_at"   : self.created_at,
			"workflows"    : list(self.manager._workflows.keys()),
			"executions"   : self.engine.list_executions(),
		}


class WorkspaceManager:
	"""Manages multiple isolated workspaces, each with its own manager + engine."""

	# Port block size per workspace (for agent uvicorn servers)
	PORT_BLOCK = 100

	def __init__(self, base_port: int, event_bus: EventBus,
				 storage_root: Optional[Path] = None,
				 channel_registry=None):
		self._event_bus        : EventBus                   = event_bus
		self._base_port        : int                        = base_port
		self._next_port        : int                        = base_port + 2  # +0 = main server, +1 = console agent
		self._storage_root     : Optional[Path]             = Path(storage_root) if storage_root else None
		self._channel_registry                              = channel_registry
		self._assistant_deployment_mgr                      = None
		self._channel_pool                                  = None
		self._workspaces       : Dict[str, WorkspaceState]  = {}
		self._default_ws_id    : Optional[str]              = None
		self._user_ws          : Dict[str, str]             = {}   # user_id → workspace_id
		self._user_ws_lock     : asyncio.Lock               = asyncio.Lock()
		self._skill_mgr                                     = None  # set via set_skill_mgr()

		if self._storage_root:
			self._storage_root.mkdir(parents=True, exist_ok=True)


	async def initialize(self):
		"""Create the default workspace."""
		ws = await self.create_workspace("default", "Default workspace")
		self._default_ws_id = ws.workspace_id
		await ws.manager.initialize()

	def set_runtime_services(self, *, channel_registry=None, assistant_deployment_mgr=None, channel_pool=None) -> None:
		"""Propagate shared runtime services into current and future workspace engines."""
		if channel_registry is not None:
			self._channel_registry = channel_registry
		if assistant_deployment_mgr is not None:
			self._assistant_deployment_mgr = assistant_deployment_mgr
		if channel_pool is not None:
			self._channel_pool = channel_pool
		for ws in self._workspaces.values():
			ws.engine.set_runtime_services(
				channel_registry=self._channel_registry,
				assistant_deployment_mgr=self._assistant_deployment_mgr,
				channel_pool=self._channel_pool,
			)


	async def shutdown(self):
		"""Shutdown all workspaces — stop servers, clean up."""
		for ws in list(self._workspaces.values()):
			await ws.manager.remove()


	def get_default_workspace(self) -> WorkspaceState:
		"""Return the default workspace (always exists)."""
		return self._workspaces[self._default_ws_id]


	async def get_or_create_user_workspace(self, user_id: str) -> WorkspaceState:
		"""Return the workspace for *user_id*, creating it lazily on first use."""
		# Fast path — already exists
		ws_id = self._user_ws.get(user_id)
		if ws_id and ws_id in self._workspaces:
			return self._workspaces[ws_id]

		# Slow path — create under lock to prevent duplicates
		async with self._user_ws_lock:
			ws_id = self._user_ws.get(user_id)
			if ws_id and ws_id in self._workspaces:
				return self._workspaces[ws_id]

			ws = await self.create_workspace(
				name=f"user_{user_id}",
				description=f"Workspace for user {user_id}",
			)
			await ws.manager.initialize()
			self._user_ws[user_id] = ws.workspace_id
			return ws


	async def resolve_workspace(self, user_id: Optional[str] = None) -> WorkspaceState:
		"""Return the workspace for *user_id*, or the default workspace for
		guests / unauthenticated callers (user_id is None)."""
		if user_id:
			return await self.get_or_create_user_workspace(user_id)
		return self.get_default_workspace()


	def resolve_workspace_sync(self, user_id: Optional[str] = None) -> WorkspaceState:
		"""Synchronous fast-path: look up an *already-created* user workspace.
		Falls back to the default workspace when the user workspace hasn't been
		created yet (or user_id is None)."""
		if user_id:
			ws_id = self._user_ws.get(user_id)
			if ws_id and ws_id in self._workspaces:
				return self._workspaces[ws_id]
		return self.get_default_workspace()


	async def create_workspace(self, name: str, description: Optional[str] = None) -> WorkspaceState:
		"""Create a new isolated workspace."""
		workspace_id = f"ws_{uuid.uuid4().hex[:10]}"

		# Allocate a port range for this workspace
		port = self._next_port
		self._next_port += self.PORT_BLOCK

		# Per-workspace storage directory
		storage_dir = None
		if self._storage_root:
			storage_dir = self._storage_root / workspace_id
			storage_dir.mkdir(parents=True, exist_ok=True)

		mgr    = WorkflowManager(port, self._event_bus, storage_dir=storage_dir)
		mgr._skill_mgr = self._skill_mgr
		eng    = WorkflowEngine(
			self._event_bus,
			channel_registry=self._channel_registry,
			assistant_deployment_mgr=self._assistant_deployment_mgr,
			channel_pool=self._channel_pool,
		)

		ws = WorkspaceState(
			workspace_id = workspace_id,
			name         = name,
			description  = description,
			manager      = mgr,
			engine       = eng,
		)
		self._workspaces[workspace_id] = ws

		await self._event_bus.emit(
			event_type   = EventType.WORKSPACE_CREATED,
			workspace_id = workspace_id,
			data         = {"name": name, "workspace_id": workspace_id},
		)
		return ws


	async def delete_workspace(self, workspace_id: str) -> bool:
		"""Delete a workspace. Cannot delete the default workspace."""
		if workspace_id == self._default_ws_id:
			return False
		ws = self._workspaces.get(workspace_id)
		if not ws:
			return False

		# Clean up: cancel executions, remove workflows, kill servers
		await ws.engine.cancel_execution()  # cancel all
		await ws.manager.remove()           # remove all workflows + stop servers

		del self._workspaces[workspace_id]

		await self._event_bus.emit(
			event_type   = EventType.WORKSPACE_DELETED,
			workspace_id = workspace_id,
			data         = {"workspace_id": workspace_id},
		)
		return True


	async def get_workspace(self, workspace_id: str) -> Optional[WorkspaceState]:
		"""Get a workspace by ID."""
		return self._workspaces.get(workspace_id)


	async def list_workspaces(self) -> List[dict]:
		"""List all workspaces with summary info."""
		return [ws.to_dict() for ws in self._workspaces.values()]


	async def evict_user_workspace(self, user_key: str) -> bool:
		"""Remove an ephemeral workspace by its user key (e.g. 'guest_...')."""
		ws_id = self._user_ws.pop(user_key, None)
		if not ws_id:
			return False
		return await self.delete_workspace(ws_id)


	async def cleanup_guest_workspaces(self, max_age_s: float = 86400):
		"""Evict guest workspaces older than *max_age_s* seconds."""
		now = datetime.now()
		to_evict = []
		for user_key, ws_id in list(self._user_ws.items()):
			if not user_key.startswith("guest_"):
				continue
			ws = self._workspaces.get(ws_id)
			if not ws:
				to_evict.append(user_key)
				continue
			age = (now - datetime.fromisoformat(ws.created_at)).total_seconds()
			if age > max_age_s:
				to_evict.append(user_key)
		for key in to_evict:
			await self.evict_user_workspace(key)
