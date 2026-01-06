# manager

import asyncio
import copy
# import json
import uvicorn


# from   pathlib   import Path
from   typing    import Any, Callable, Dict, List, Optional


from   event_bus import EventType, EventBus
from   schema    import InfoConfig, Workflow, WorkflowOptionsConfig
from   utils     import log_print, serialize_result


from nodes     import ImplementedBackend
from impl_agno import build_backend_agno


class WorkflowManager:

	# def __init__(self, event_bus: EventBus, storage_dir: str = "workflows"):
	def __init__(self, port: int, event_bus: EventBus):
		self._port            : int                 = port
		self._event_bus       : EventBus            = event_bus
		self._current_id      : int                 = 0
		self._workflows       : Dict[str, Any     ] = {}
		self._upload_handlers : Dict[str, Callable] = {}

		# self._storage_dir = Path(storage_dir)
		# self._storage_dir.mkdir(exist_ok=True)


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
			event_type = EventType.MANAGER_WORKFLOW_CREATED,
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


async def _handle_knowledge_upload(impl: Any, node_index: int, button_id: str, files: List[Any]) -> Any:
	backend = impl["backend"]
	handle  = backend.handles[node_index]
	try:
		res = await backend.add_content(handle, files)
	except Exception as e:
		msg    = f"Error uploading files to {impl['workflow'].nodes[node_index].type} by {button_id}: {str(e)}"
		result = {
			"status" : "error",
			"message": msg,
			"result" : None,
		}
		log_print(result)
		return result
	msg     = f"Processed {len(files)} files from {impl["workflow"].nodes[node_index].type} by {button_id}."
	result  = {
		"status" : "ok",
		"message": msg,
		"result" : serialize_result(res),
	}
	log_print(result)
	return result
