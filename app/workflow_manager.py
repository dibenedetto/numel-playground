# workflow_manager

import json


from   pathlib         import Path
from   typing          import Dict, List, Optional


from   schema          import AppConfig, InfoConfig
from   workflow_schema import WorkflowConfig


class WorkflowManager:
	"""
	Manages workflow storage, loading, and validation.
	Keeps workflows separate from app configuration.
	"""
	
	def __init__(self, app_config: AppConfig, storage_dir: str = "workflows"):
		self.app_config = app_config
		self.storage_dir = Path(storage_dir)
		self.storage_dir.mkdir(exist_ok=True)
		self.workflows: Dict[str, WorkflowConfig] = {}
	

	def load_workflow(self, filepath: str) -> WorkflowConfig:
		"""Load workflow from JSON file"""
		with open(filepath, 'r') as f:
			data = json.load(f)
		
		workflow = WorkflowConfig(**data)
		
		# Validate against app config
		errors = workflow.validate_against_app_config(self.app_config)
		if errors:
			raise ValueError(f"Workflow validation errors:\n" + "\n".join(errors))
		
		self.workflows[workflow.info.name] = workflow
		return workflow
	

	def save_workflow(self, workflow: WorkflowConfig, filepath: Optional[str] = None):
		"""Save workflow to JSON file"""
		if filepath is None:
			filename = f"{workflow.info.name.lower().replace(' ', '_')}.json"
			filepath = self.storage_dir / filename
		
		with open(filepath, 'w') as f:
			json.dump(workflow.dict(), f, indent=2)
	

	def list_workflows(self) -> List[str]:
		"""List all loaded workflow names"""
		return list(self.workflows.keys())
	

	def get_workflow(self, name: str) -> Optional[WorkflowConfig]:
		"""Get workflow by name"""
		return self.workflows.get(name)
	

	def load_all_from_directory(self, directory: Optional[str] = None):
		"""Load all workflow JSON files from directory"""
		if directory is None:
			directory = self.storage_dir
		
		for filepath in Path(directory).glob("*.json"):
			try:
				self.load_workflow(str(filepath))
			except Exception as e:
				print(f"Error loading workflow {filepath}: {e}")
	

	def create_workflow(self, name: str, description: str = "") -> WorkflowConfig:
		"""Create a new empty workflow"""
		workflow = WorkflowConfig(
			info=InfoConfig(
				name=name,
				description=description
			),
			nodes=[],
			edges=[],
			variables={}
		)
		
		self.workflows[name] = workflow
		return workflow
	

	def delete_workflow(self, name: str):
		"""Delete workflow from memory"""
		if name in self.workflows:
			del self.workflows[name]
