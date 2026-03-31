# manager

import asyncio
import copy
import json
import uvicorn


from   pathlib   import Path
from   typing    import Any, Callable, Dict, List, Optional


from   event_bus import EventType, EventBus
from   schema    import Workflow, WorkflowOptions
from   utils     import serialize_result


from   nodes     import ImplementedBackend
from   impl_agno import build_backend_agno


class WorkflowManager:

	def __init__(self, port: int, event_bus: EventBus, storage_dir: Optional[Path] = None):
		self._port            : int                 = port
		self._event_bus       : EventBus            = event_bus
		self._current_id      : int                 = 0
		self._workflows       : Dict[str, Any     ] = {}
		self._upload_handlers : Dict[str, Callable] = {}
		self._storage_dir     : Optional[Path]      = Path(storage_dir) if storage_dir else None

		if self._storage_dir:
			self._storage_dir.mkdir(parents=True, exist_ok=True)


	async def initialize(self):
		await self.register_upload_handler(
			"knowledge_manager_config",
			_handle_knowledge_upload,
		)


	async def clear(self):
		await self.remove()
		await self.unregister_upload_handler()
		self._current_id      = 0
		self._workflows       = {}
		self._upload_handlers = {}
		await self._event_bus.emit(
			event_type = EventType.MANAGER_CLEARED,
		)


	async def register_upload_handler(self, node_type: str, handler: Callable) -> bool:
		self._upload_handlers[node_type] = handler
		await self._event_bus.emit(
			event_type = EventType.MANAGER_UPLOAD_ADDED,
		)
		return True


	async def unregister_upload_handler(self, node_type: Optional[str] = None) -> bool:
		if not node_type:
			names = list(self._upload_handlers.keys())
		elif node_type in self._upload_handlers:
			names = [node_type]
		else:
			return False
		for key in names:
			del self._upload_handlers[key]
		await self._event_bus.emit(
			event_type = EventType.MANAGER_UPLOAD_REMOVED,
		)
		return True


	async def get_upload_handler(self, node_type: Optional[str] = None) -> Any:
		if not node_type:
			result = copy.deepcopy(self._upload_handlers)
		elif node_type in self._upload_handlers:
			result = self._upload_handlers.get(node_type)
		else:
			return None
		await self._event_bus.emit(
			event_type = EventType.MANAGER_UPLOAD_GOT,
		)
		return result


	async def create(self, name: str, description: Optional[str] = None) -> Workflow:
		wf = Workflow(
			options = WorkflowOptions(
				name        = name,
				description = description
			),
			nodes   = [],
			edges   = [],
		)
		self._workflows[name] = self._make_workflow(wf)
		await self._event_bus.emit(
			event_type = EventType.MANAGER_WORKFLOW_CREATED,
		)
		return wf


	async def add(self, workflow: Workflow, name: Optional[str] = None) -> str:
		wf = copy.deepcopy(workflow)
		if not name:
			if wf.options and wf.options.name:
				name = wf.options.name
			else:
				self._current_id += 1
				name = f"workflow_{self._current_id}"
		await self.remove(name)
		wf.link()
		self._workflows[name] = self._make_workflow(wf)
		await self._event_bus.emit(
			event_type = EventType.MANAGER_WORKFLOW_ADDED,
		)
		return name


	async def remove(self, name: Optional[str] = None) -> bool:
		if not name:
			names = list(self._workflows.keys())
		elif name in self._workflows:
			names = [name]
		else:
			return False
		for key in names:
			data = self._workflows[key]
			await self._kill_workflow(data)
			del self._workflows[key]
		await self._event_bus.emit(
			event_type = EventType.MANAGER_WORKFLOW_REMOVED,
		)
		return True


	async def get(self, name: Optional[str] = None) -> Any:
		if not name:
			result = {key:value["workflow"] for key, value in self._workflows.items()}
		elif name in self._workflows:
			data   = self._workflows.get(name)
			result = data["workflow"] if data else None
		else:
			return None
		result = copy.deepcopy(result)
		await self._event_bus.emit(
			event_type = EventType.MANAGER_WORKFLOW_GOT,
		)
		return result


	async def impl(self, name: Optional[str] = None) -> Any:
		if not name:
			name = list(self._workflows.keys())[-1] if self._workflows else None
		data = self._workflows.get(name)
		if not data:
			return None
		if data["backend"] is not None:
			return data
		workflow = data["workflow"]
		backend  = self._build_backend(workflow)
		apps     = [None] * len(backend.handles)
		host     = "0.0.0.0"
		port     = self._port + 1
		servers  = []
		for i, (node, handle) in enumerate(zip(workflow.nodes, backend.handles)):
			if node.type != "agent_config":
				continue
			app    = backend.get_agent_app(handle)
			config = uvicorn.Config(app, host=host, port=port, log_level="warning")
			server = uvicorn.Server(config)
			task   = asyncio.create_task(server.serve())
			info   = {
				"app"    : app,
				"config" : config,
				"server" : server,
				"task"   : task,
			}
			apps[i]   = info
			node.port = port
			servers.append(server)
			port += 1

		# Wait for all agent servers to actually bind their ports before returning
		for _ in range(40):  # up to 2 s
			if all(s.started for s in servers):
				break
			await asyncio.sleep(0.05)
		data["backend"] = backend
		data["apps"   ] = apps
		await self._event_bus.emit(
			event_type = EventType.MANAGER_WORKFLOW_IMPL,
		)
		return data


	async def list(self) -> List[str]:
		result = list(self._workflows.keys())
		await self._event_bus.emit(
			event_type = EventType.MANAGER_WORKFLOW_LISTED,
		)
		return result


	def _make_workflow(self, workflow: Workflow) -> Any:
		result = {
			"workflow" : workflow,
			"backend"  : None,
			"apps"     : None,
		}
		return result


	async def _kill_workflow(self, data: Any):
		if data["apps"]:
			for item in data["apps"]:
				if not item:
					continue
				server = item["server"]
				task   = item["task"  ]
				if server and server.should_exit is False:
					server.should_exit = True
				if task:
					await task


	def _build_backend(self, workflow: Workflow) -> ImplementedBackend:
		return build_backend_agno(workflow, skill_mgr=getattr(self, '_skill_mgr', None))


	async def save(self, name: str, filepath: Optional[str] = None) -> bool:
		"""Save a single workflow to disk as JSON."""
		data = self._workflows.get(name)
		if not data:
			return False
		wf = data["workflow"]
		if filepath is None:
			if not self._storage_dir:
				return False
			safe_name = name.lower().replace(" ", "_")
			filepath  = self._storage_dir / f"{safe_name}.json"
		else:
			filepath = Path(filepath)
		filepath.parent.mkdir(parents=True, exist_ok=True)
		with open(filepath, "w") as f:
			json.dump(wf.model_dump(), f, indent=2)
		await self._event_bus.emit(
			event_type = EventType.MANAGER_WORKFLOW_SAVED,
			data       = {"name": name, "path": str(filepath)},
		)
		return True


	async def save_all(self) -> int:
		"""Save all workflows to storage_dir. Returns count of saved workflows."""
		if not self._storage_dir:
			return 0
		count = 0
		for name in list(self._workflows.keys()):
			if await self.save(name):
				count += 1
		return count


	async def load(self, filepath: str, name: Optional[str] = None) -> Optional[str]:
		"""Load a workflow from a JSON file. Returns the workflow name."""
		try:
			with open(filepath, "r") as f:
				data = json.load(f)
			workflow = Workflow(**data)
		except Exception as e:
			from utils import log_print
			log_print(f"Error reading workflow file: {e}")
			return None
		if not workflow.options:
			workflow.options = WorkflowOptions(name=Path(filepath).stem)
		if name:
			workflow.options.name = name
		elif not workflow.options.name:
			workflow.options.name = Path(filepath).stem
		loaded_name = await self.add(workflow, name or workflow.options.name)
		await self._event_bus.emit(
			event_type = EventType.MANAGER_WORKFLOW_LOADED,
			data       = {"name": loaded_name, "path": filepath},
		)
		return loaded_name


	async def load_all(self, directory: Optional[str] = None) -> int:
		"""Load all JSON workflow files from a directory. Returns count loaded."""
		target = Path(directory) if directory else self._storage_dir
		if not target or not target.is_dir():
			return 0
		count = 0
		for filepath in sorted(target.glob("*.json")):
			loaded = await self.load(str(filepath))
			if loaded:
				count += 1
		return count


async def _handle_knowledge_upload(impl: Any, node_index: int, button_id: str, files: List[Any]) -> Any:
	backend = impl["backend"]
	handle  = backend.handles[node_index]
	try:
		res = await backend.add_contents(handle, files)
	except Exception as e:
		msg    = f"Error processing files with '{impl['workflow'].nodes[node_index].type}': {str(e)}"
		result = {
			"status" : "error",
			"message": msg,
			"result" : None,
		}
		return result
	msg     = f"Processed {len(files)} files from '{impl["workflow"].nodes[node_index].type}' by '{button_id}'."
	result  = {
		"status" : "ok",
		"message": msg,
		"result" : serialize_result(res),
	}
	return result
