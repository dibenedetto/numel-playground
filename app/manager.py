# manager

import asyncio
import copy
# import json
import uvicorn


# from   pathlib   import Path
from   typing    import Any, Dict, List, Optional


from   event_bus import EventBus, EventType
from   schema    import InfoConfig, Workflow, WorkflowOptionsConfig
# from   utils     import log_print


from nodes     import ImplementedBackend
from impl_agno import build_backend_agno


class WorkflowManager:

	# def __init__(self, event_bus: EventBus, storage_dir: str = "workflows"):
	def __init__(self, port: int, event_bus: EventBus):
		self._port       : int            = port
		self._event_bus  : EventBus       = event_bus
		self._current_id : int            = 0
		self._workflows  : Dict[str, Any] = {}
		# self._storage_dir = Path(storage_dir)
		# self._storage_dir.mkdir(exist_ok=True)


	async def clear(self):
		self._current_id = 0
		self._workflows  = {}
		await self._event_bus.emit(
			event_type = EventType.MANAGER_CLEARED,
		)

	async def create(self, name: str, description: str = None) -> Workflow:
		wf = Workflow(
			info = InfoConfig(
				name        = name,
				description = description
			),
			options = WorkflowOptionsConfig(),
			nodes   = [],
			edges   = [],
		)
		self._workflows[name] = self._make_workflow(wf)
		await self._event_bus.emit(
			event_type = EventType.MANAGER_CREATED,
		)
		return wf


	async def add(self, workflow: Workflow, name: Optional[str] = None) -> str:
		wf = copy.deepcopy(workflow)
		if not name:
			if wf.info and wf.info.name:
				name = wf.info.name
			else:
				self._current_id += 1
				name = f"workflow_{self._current_id}"
		wf.link()
		self._workflows[name] = self._make_workflow(wf)
		await self._event_bus.emit(
			event_type = EventType.MANAGER_ADDED,
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
			del self._workflows[key]
		await self._event_bus.emit(
			event_type = EventType.MANAGER_REMOVED,
		)
		return True


	async def get(self, name: str) -> Optional[Workflow]:
		if not name:
			result = {key:value["workflow"] for key, value in self._workflows.items()}
		elif name in self._workflows:
			data   = self._workflows.get(name)
			result = data["workflow"] if data else None
		else:
			return None
		result = copy.deepcopy(result)
		await self._event_bus.emit(
			event_type = EventType.MANAGER_GOT,
		)
		return result


	async def impl(self, name: str) -> Any:
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
		for i, (node, handle) in enumerate(zip(workflow.nodes, backend.handles)):
			if node.type != "agent_config":
				continue
			app    = backend.get_agent_app(handle)
			config = uvicorn.Config(app, host=host, port=port)
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
			port += 1
		data["backend"] = backend
		data["apps"   ] = apps
		await self._event_bus.emit(
			event_type = EventType.MANAGER_IMPL,
		)
		return data


	async def list(self) -> List[str]:
		result = list(self._workflows.keys())
		await self._event_bus.emit(
			event_type = EventType.MANAGER_LISTED,
		)
		return result


	def _make_workflow(self, workflow: Workflow) -> Any:
		result = {
			"workflow" : workflow,
			"backend"  : None,
			"apps"     : None,
		}
		return result


	def _build_backend(self, workflow: Workflow) -> ImplementedBackend:
		return build_backend_agno(workflow)


	# def load(self, filepath: str, name: Optional[str] = None) -> Workflow:
	# 	try:
	# 		with open(filepath, "r") as f:
	# 			data = json.load(f)
	# 		workflow = Workflow(**data)
	# 	except Exception as e:
	# 		log_print(f"Error reading workflow file: {e}")
	# 		return None
	# 	if not workflow.info:
	# 		workflow.info = InfoConfig(name=filepath)
	# 	if name:
	# 		workflow.info.name = name
	# 	elif not workflow.info.name:
	# 		workflow.info.name = filepath
	# 	self._workflows[workflow.info.name] = workflow
	# 	return workflow


	# def load_all(self, directory: Optional[str] = None) -> bool:
	# 	if directory is None:
	# 		directory = self.storage_dir
	# 	for filepath in Path(directory).glob("*.json"):
	# 		try:
	# 			self.load(str(filepath))
	# 		except Exception as e:
	# 			print(f"Error loading workflow {filepath}: {e}")
	# 			return False
	# 	return True


	# def save(self, name: str, filepath: Optional[str] = None) -> bool:
	# 	if filepath is None:
	# 		filename = f"{workflow.info.name.lower().replace(' ', '_')}.json"
	# 		filepath = self.storage_dir / filename
	# 	with open(filepath, "w") as f:
	# 		json.dump(workflow.model_dump(), f, indent=2)


	# def save_all(self, workflow: Workflow, filepath: Optional[str] = None):
	# 	if filepath is None:
	# 		filename = f"{workflow.info.name.lower().replace(' ', '_')}.json"
	# 		filepath = self.storage_dir / filename
	# 	with open(filepath, "w") as f:
	# 		json.dump(workflow.model_dump(), f, indent=2)
