# workspace — Multi-workspace management layer
#
# Each workspace owns its own WorkflowManager + WorkflowEngine pair,
# sharing a single global EventBus.  A "default" workspace is always
# created so that existing (pre-workspace) API calls continue to work.

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
				 storage_root: Optional[Path] = None):
		self._event_bus     : EventBus                   = event_bus
		self._base_port     : int                        = base_port
		self._next_port     : int                        = base_port + 1  # reserve base_port for main server
		self._storage_root  : Optional[Path]             = Path(storage_root) if storage_root else None
		self._workspaces    : Dict[str, WorkspaceState]  = {}
		self._default_ws_id : Optional[str]              = None

		if self._storage_root:
			self._storage_root.mkdir(parents=True, exist_ok=True)


	async def initialize(self):
		"""Create the default workspace."""
		ws = await self.create_workspace("default", "Default workspace")
		self._default_ws_id = ws.workspace_id
		await ws.manager.initialize()


	async def shutdown(self):
		"""Shutdown all workspaces — stop servers, clean up."""
		for ws in list(self._workspaces.values()):
			await ws.manager.remove()


	def get_default_workspace(self) -> WorkspaceState:
		"""Return the default workspace (always exists)."""
		return self._workspaces[self._default_ws_id]


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
		eng    = WorkflowEngine(self._event_bus)

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
