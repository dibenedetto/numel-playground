# manager

# import json


from   pathlib   import Path
from   typing    import Dict, List, Optional


from   event_bus import EventBus, EventType, get_event_bus
from   schema    import InfoConfig, Workflow, WorkflowOptionsConfig


class WorkflowManager:

	def __init__(self, event_bus: Optional[EventBus] = None, storage_dir: str = "workflows"):
		self._event_bus  : EventBus            = event_bus or get_event_bus()
		self._current_id : int                 = 0
		self._workflows  : Dict[str, Workflow] = {}
		self.storage_dir = Path(storage_dir)
		self.storage_dir.mkdir(exist_ok=True)


	async def clear(self):
		self._current_id = 0
		self._workflows  = {}
		await self._event_bus.emit(
			event_type = EventType.MANAGER_CLEARED,
		)

	async def create(self, name: str, description: str = None) -> Workflow:
		workflow = Workflow(
			info = InfoConfig(
				name        = name,
				description = description
			),
			options = WorkflowOptionsConfig(),
			nodes   = [],
			edges   = [],
		)
		self._workflows[name] = workflow
		await self._event_bus.emit(
			event_type = EventType.MANAGER_CREATED,
		)
		return workflow


	async def add(self, workflow: Workflow, name: Optional[str] = None) -> str:
		wf = Workflow(workflow)
		if not name:
			if not wf.info:
				wf.info = InfoConfig()
			if not wf.info.name:
				self._current_id += 1
				wf.info.name = f"workflow_{self._current_id}"
			name = wf.info.name
		wf.link()
		self.workflows[name] = workflow
		await self._event_bus.emit(
			event_type = EventType.MANAGER_ADDED,
		)
		return name


	async def remove(self, name: Optional[str] = None) -> bool:
		if not name:
			self._workflows = {}
			return True
		if name in self._workflows:
			del self._workflows[name]
			await self._event_bus.emit(
				event_type = EventType.MANAGER_REMOVED,
			)
			return True
		return False


	async def get(self, name: str) -> Optional[Workflow]:
		await self._event_bus.emit(
			event_type = EventType.MANAGER_GOT,
		)
		return self._workflows.get(name)


	async def list(self) -> List[str]:
		await self._event_bus.emit(
			event_type = EventType.MANAGER_LISTED,
		)
		return list(self._workflows.keys())


	# def load(self, filepath: str) -> Workflow:
	# 	with open(filepath, "r") as f:
	# 		data = json.load(f)
	# 	workflow = Workflow(**data)
	# 	if not workflow.info:
	# 		workflow.info = InfoConfig(name=filepath)
	# 	elif not workflow.info.name:
	# 		workflow.info.name = filepath
	# 	self.workflows[workflow.info.name] = workflow
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
