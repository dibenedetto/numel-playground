# api

import asyncio
import json
import os
import re


from   pathlib   import Path
from   fastapi   import FastAPI, HTTPException, UploadFile, WebSocket, WebSocketDisconnect, File, Form
from   pydantic  import BaseModel
from   typing    import Any, Dict, List, Optional


from   engine    import WorkflowEngine
from   event_bus import EventType, EventBus
from   manager   import WorkflowManager
from   schema    import Workflow, WorkflowExecutionOptions
from   utils     import get_now_str, get_timestamp_str, log_print, serialize_result
from   events    import (
	get_event_registry, init_event_registry, shutdown_event_registry,
	TimerSourceConfig, FSWatchSourceConfig,
	WebhookSourceConfig, BrowserSourceConfig, BrowserSource
)

# Tutorial extension (see docs/tutorial-extension.md)
from   tutorial_api import setup_tutorial_api


class WorkflowUploadRequest(BaseModel):
	workflow : Workflow
	name     : Optional[str] = None


class WorkflowStartRequest(BaseModel):
	name         : str
	initial_data : WorkflowExecutionOptions = None


class UserInputRequest(BaseModel):
	node_id    : str
	input_data : Any


class ToolCallRequest(BaseModel):
	node_index : int
	args       : Optional[Dict[str, Any]] = None


class ContentRemoveRequest(BaseModel):
	ids : List[str]


class TemplateSaveRequest(BaseModel):
	template : dict


class TemplateRenameRequest(BaseModel):
	name : str


class GenerateWorkflowRequest(BaseModel):
	prompt      : str
	# Agent subgraph config (each maps to a schema config type)
	backend     : Optional[dict] = None   # BackendConfig fields {engine}
	model       : Optional[dict] = None   # ModelConfig fields {source, name, version}
	options     : Optional[dict] = None   # AgentOptionsConfig fields {name, description, instructions, prompt_override, markdown}
	memory      : Optional[dict] = None   # MemoryManagerConfig fields {query, update, managed, prompt}
	session     : Optional[dict] = None   # SessionManagerConfig fields {query, update, history_size, prompt}
	tools       : Optional[List[dict]] = None  # List of ToolConfig fields [{name, args}]
	knowledge   : Optional[dict] = None   # KnowledgeManagerConfig fields {query, description, max_results, urls, content_db, index_db}
	# LLM params (separate from model config)
	temperature : float = 0.3
	max_tokens  : int = 4096
	history     : Optional[List[dict]] = None


def setup_api(server: Any, app: FastAPI, event_bus: EventBus, schema_code: str, manager: WorkflowManager, engine: WorkflowEngine):

	# Setup tutorial extension API (see docs/tutorial-extension.md)
	setup_tutorial_api(app, manager)

	@app.post("/shutdown")
	async def shutdown_server():
		nonlocal engine, server
		await engine.cancel_execution()
		if server and server.should_exit is False:
			server.should_exit = True
		engine = None
		server = None
		result = {
			"status"  : "none",
			"message" : "Server shut down",
		}
		return result


	@app.post("/status")
	async def server_status():
		nonlocal engine
		result = {
			"status"     : "ready",
			"executions" : engine.get_all_execution_states(),
		}
		return result


	@app.post("/ping")
	async def ping():
		result = {
			"message"   : "pong",
			"timestamp" : get_now_str(),
		}
		return result


	@app.post("/schema")
	async def export_schema():
		nonlocal schema_code
		result = {
			"schema": schema_code,
		}
		return result


	# @app.post("/chat_open/{name}")
	# async def chat_open(name: str):
	# 	raise HTTPException(status_code=501, detail=f"Chat open not implemented")
	# 	result = {
	# 		"name"  : name,
	# 		"port"  : 0,
	# 		"error" : 501,
	# 	}
	# 	return result


	# @app.post("/chat_close")
	# @app.post("/chat_close/{name}")
	# async def chat_close(name: Optional[str] = None):
	# 	raise HTTPException(status_code=501, detail=f"Chat close not implemented")
	# 	result = {
	# 		"name"  : name,
	# 		"error" : 501,
	# 	}
	# 	return result


	@app.post("/tool_call")
	async def tool_call(request: ToolCallRequest):
		nonlocal manager
		try:
			impl = await manager.impl()
			if not impl:
				raise HTTPException(status_code=404, detail="No active workflow")

			workflow = impl["workflow"]
			backend  = impl["backend" ]

			if not backend:
				raise HTTPException(status_code=400, detail=f"Workflow has no backend implementation")

			node_index = request.node_index
			if node_index < 0 or node_index >= len(workflow.nodes):
				raise HTTPException(status_code=400, detail=f"Invalid node index: {node_index}")

			node = workflow.nodes[node_index]
			if node.type != "tool_config":
				raise HTTPException(status_code=400, detail=f"Node at index {node_index} is not a tool_config (got {node.type})")

			handle = backend.handles[node_index]
			if not handle:
				raise HTTPException(status_code=400, detail=f"Tool at index {node_index} has no implementation")

			# Merge default args from config with request args
			args = dict(node.args or {})
			if request.args:
				args.update(request.args)

			# Execute the tool
			result_data = await backend.run_tool(handle, **args)

			result = {
				"status"     : "success",
				"node_index" : node_index,
				"tool_name"  : node.name,
				"result"     : result_data,
			}
			return result

		except HTTPException:
			raise
		except Exception as e:
			log_print(f"[API] Tool call error: {str(e)}")
			raise HTTPException(status_code=500, detail=str(e))


	@app.post("/add")
	async def add_workflow(request: WorkflowUploadRequest):
		nonlocal manager
		name = await manager.add(request.workflow, request.name)
		impl = await manager.impl(name)
		wf   = impl["workflow"].model_dump() if impl else None
		result = {
			"name"     : name,
			"workflow" : wf,
			"status"   : "added" if name else "failed",
		}
		return result


	@app.post("/remove")
	@app.post("/remove/{name}")
	async def remove_workflow(name: Optional[str] = None):
		nonlocal manager
		status = await manager.remove(name)
		result = {
			"name"   : name,
			"status" : "removed" if status else "failed",
		}
		return result


	@app.post("/get")
	@app.post("/get/{name}")
	async def get_workflow(name: Optional[str] = None):
		nonlocal manager
		workflow = await manager.get(name)
		if workflow:
			workflow = workflow["workflow"].model_dump()
		result   = {
			"name"     : name,
			"workflow" : workflow,
		}
		return result


	@app.post("/list")
	async def list_workflows():
		nonlocal manager
		names  = await manager.list()
		result = {
			"names": names,
		}
		return result


	@app.post("/start")
	async def start_workflow(request: WorkflowStartRequest):
		nonlocal engine, manager
		try:
			impl = await manager.impl(request.name)
			if not impl:
				raise HTTPException(status_code=404, detail=f"Workflow 'request.name' not found")
			options      = request.initial_data or WorkflowExecutionOptions()
			initial_data = options.model_dump()
			execution_id = await engine.start_workflow(
				workflow     = impl["workflow"],
				backend      = impl["backend" ],
				initial_data = initial_data,
			)
			result = {
				"execution_id" : execution_id,
				"status"       : "started",
			}
			return result
		except Exception as e:
			log_print(f"Error starting workflow: {e}")
			raise HTTPException(status_code=500, detail=str(e))


	@app.post("/exec_list")
	async def list_executions():
		nonlocal engine
		try:
			execution_ids = engine.list_executions()
			result =  {
				"execution_ids": execution_ids,
			}
			return result
		except Exception as e:
			log_print(f"Error listing executions: {e}")
			raise HTTPException(status_code=500, detail=str(e))


	@app.post("/exec_state")
	@app.post("/exec_state/{execution_id}")
	async def execution_state(execution_id: Optional[str] = None):
		nonlocal engine
		state  = engine.get_execution_state(execution_id)
		result = {
			"execution_id" : execution_id,
			"state"        : state,
		}
		return result


	@app.post("/exec_cancel")
	@app.post("/exec_cancel/{execution_id}")
	async def cancel_execution(execution_id: Optional[str] = None):
		nonlocal engine
		try:
			state  = await engine.cancel_execution(execution_id)
			result =  {
				"execution_id" : execution_id,
				"status"       : "cancelled" if state else "failed",
				"state"        : state,
			}
			return result
		except Exception as e:
			log_print(f"Error cancelling execution: {e}")
			raise HTTPException(status_code=500, detail=str(e))


	@app.post("/exec_input/{execution_id}")
	async def provide_user_input(execution_id: str, request: UserInputRequest):
		nonlocal engine
		try:
			await engine.provide_user_input(
				execution_id = execution_id,
				node_id      = request.node_id,
				user_input   = request.input_data
			)
			result =  {
				"execution_id" : execution_id,
				"status"       : "input_received",
				"node_id"      : request.node_id,
				"input_data"   : request.input_data,
			}
			return result
		except Exception as e:
			log_print(f"Error providing user input: {e}")
			raise HTTPException(status_code=500, detail=str(e))


	@app.post("/upload/{node_index}")
	async def upload_files(
		node_index : int,
		files      : List[UploadFile] = File(...),
		node_type  : str = Form(None),
		button_id  : str = Form(None),
	):
		"""Handle file uploads from node drop zones or buttons"""
		nonlocal event_bus, manager
		
		upload_id = f"upload_{node_index}_{get_timestamp_str()}"
		
		try:
			# Get current workflow to find node info
			impl = await manager.impl()
			if not impl:
				raise HTTPException(status_code=404, detail="No active workflow")
			
			workflow = impl["workflow"]
			if node_index < 0 or node_index >= len(workflow.nodes):
				raise HTTPException(status_code=404, detail=f"Node {node_index} not found")
			
			node = workflow.nodes[node_index]
			
			# === PHASE 1: UPLOAD ===
			await event_bus.emit(
				EventType.UPLOAD_STARTED,
				node_id = str(node_index),
				data    = {
					"upload_id"  : upload_id,
					"node_index" : node_index,
					"node_type"  : node_type or node.type,
					"file_count" : len(files),
					"filenames"  : [f.filename for f in files],
				}
			)
			
			# Read file contents
			uploaded   = []
			total_size = 0
			for file in files:
				content   = await file.read()
				file_size = len(content) if content else 0
				file_info = {
					"filename"     : file.filename,
					"content_type" : file.content_type,
					"size"         : file_size,
					"content"      : content,
					"file"         : file,
				}
				uploaded.append(file_info)
				total_size += file_size
			
			# Upload complete
			await event_bus.emit(
				EventType.UPLOAD_COMPLETED,
				node_id = str(node_index),
				data    = {
					"upload_id"  : upload_id,
					"node_index" : node_index,
					"file_count" : len(uploaded),
					"total_size" : total_size,
				}
			)
			
			# === PHASE 2: PROCESSING ===
			handler_result = None
			handler        = await manager.get_upload_handler(node.type)
			
			if handler:
				await event_bus.emit(
					EventType.PROCESSING_STARTED,
					node_id = str(node_index),
					data    = {
						"upload_id"  : upload_id,
						"node_index" : node_index,
						"node_type"  : node.type,
						"handler"    : handler.__name__ if hasattr(handler, '__name__') else str(handler),
					}
				)
				
				try:
					if asyncio.iscoroutinefunction(handler):
						handler_result = await handler(impl, node_index, button_id, uploaded)
					else:
						handler_result = handler(impl, node_index, button_id, uploaded)
					
					await event_bus.emit(
						EventType.PROCESSING_COMPLETED,
						node_id = str(node_index),
						data    = {
							"upload_id"  : upload_id,
							"node_index" : node_index,
							"result"     : serialize_result(handler_result),
						}
					)
					
				except Exception as e:
					log_print(f"Processing handler error: {e}")
					await event_bus.emit(
						EventType.PROCESSING_FAILED,
						node_id = str(node_index),
						error   = str(e),
						data    = {
							"upload_id"  : upload_id,
							"node_index" : node_index,
						}
					)
					raise HTTPException(status_code=500, detail=f"Processing failed: {str(e)}")
			
			result = {
				"status"         : "completed",
				"upload_id"      : upload_id,
				"node_index"     : node_index,
				"node_type"      : node.type,
				"files_count"    : len(uploaded),
				"total_size"     : total_size,
				"handler_result" : serialize_result(handler_result),
				"files"          : [
					{
						"filename"     : f["filename"],
						"content_type" : f["content_type"],
						"size"         : f["size"],
					}
					for f in uploaded
				],
			}
			return result
			
		except HTTPException:
			raise
		except Exception as e:
			log_print(f"Error in upload: {e}")
			await event_bus.emit(
				EventType.UPLOAD_FAILED,
				node_id = str(node_index),
				error   = str(e),
				data    = {
					"upload_id"  : upload_id,
					"node_index" : node_index,
				}
			)
			raise HTTPException(status_code=500, detail=str(e))


	@app.post("/contents/list/{node_index}")
	async def list_contents(node_index: int):
		"""List all contents for a node (e.g., knowledge manager)"""
		nonlocal manager

		try:
			impl = await manager.impl()
			if not impl:
				raise HTTPException(status_code=404, detail="No active workflow")

			workflow = impl["workflow"]
			if node_index < 0 or node_index >= len(workflow.nodes):
				raise HTTPException(status_code=404, detail=f"Node {node_index} not found")

			node    = workflow.nodes[node_index]
			backend = impl["backend"]
			handle  = backend.handles[node_index]

			if not handle:
				raise HTTPException(status_code=400, detail=f"Node {node_index} has no content handle")

			contents = await backend.list_contents(handle)

			result = {
				"status"     : "ok",
				"node_index" : node_index,
				"node_type"  : node.type,
				"contents"   : [
					{"id": id, "metadata": metadata}
					for id, metadata in contents
				],
			}
			return result

		except HTTPException:
			raise
		except Exception as e:
			log_print(f"Error listing contents: {e}")
			raise HTTPException(status_code=500, detail=str(e))


	@app.post("/contents/remove/{node_index}")
	async def remove_contents(node_index: int, request: ContentRemoveRequest):
		"""Remove contents from a node by their IDs"""
		nonlocal event_bus, manager

		try:
			impl = await manager.impl()
			if not impl:
				raise HTTPException(status_code=404, detail="No active workflow")

			workflow = impl["workflow"]
			if node_index < 0 or node_index >= len(workflow.nodes):
				raise HTTPException(status_code=404, detail=f"Node {node_index} not found")

			node    = workflow.nodes[node_index]
			backend = impl["backend"]
			handle  = backend.handles[node_index]

			if not handle:
				raise HTTPException(status_code=400, detail=f"Node {node_index} has no content handle")

			await event_bus.emit(
				EventType.CONTENT_REMOVE_STARTED,
				node_id = str(node_index),
				data    = {
					"node_index" : node_index,
					"node_type"  : node.type,
					"ids"        : request.ids,
				}
			)

			removed = await backend.remove_contents(handle, request.ids)

			await event_bus.emit(
				EventType.CONTENT_REMOVE_COMPLETED,
				node_id = str(node_index),
				data    = {
					"node_index" : node_index,
					"node_type"  : node.type,
					"removed"    : removed,
				}
			)

			result = {
				"status"     : "ok",
				"node_index" : node_index,
				"node_type"  : node.type,
				"removed"    : [
					{"id": id, "success": success}
					for id, success in zip(request.ids, removed)
				],
			}
			return result

		except HTTPException:
			raise
		except Exception as e:
			log_print(f"Error removing contents: {e}")
			await event_bus.emit(
				EventType.CONTENT_REMOVE_FAILED,
				node_id = str(node_index),
				error   = str(e),
				data    = {
					"node_index" : node_index,
				}
			)
			raise HTTPException(status_code=500, detail=str(e))


	@app.websocket("/events")
	async def workflow_events(websocket: WebSocket):
		nonlocal event_bus
		await event_bus.add_websocket_client(websocket)
		try:
			while True:
				data = await websocket.receive_text()
				log_print(f"Received WebSocket message: {data}")
		except WebSocketDisconnect:
			log_print("WebSocket client disconnected")
		except Exception as e:
			log_print(f"WebSocket error: {e}")
		event_bus.remove_websocket_client(websocket)


	# =========================================================================
	# EVENT SOURCE MANAGEMENT API
	# =========================================================================

	@app.on_event("startup")
	async def init_event_sources():
		"""Initialize event source registry on startup"""
		await init_event_registry()
		log_print("✅ Event source registry initialized")

	@app.on_event("shutdown")
	async def shutdown_event_sources():
		"""Shutdown event source registry"""
		await shutdown_event_registry()
		log_print("✅ Event source registry shut down")

	@app.post("/event-sources/list")
	async def list_event_sources():
		"""List all registered event sources"""
		registry = get_event_registry()
		return {
			"status": "ok",
			"sources": registry.list_sources()
		}

	@app.post("/event-sources/get/{source_id}")
	async def get_event_source(source_id: str):
		"""Get a specific event source"""
		registry = get_event_registry()
		source = registry.get(source_id)
		if not source:
			raise HTTPException(status_code=404, detail=f"Source not found: {source_id}")
		return {
			"status": "ok",
			"source": source.get_status()
		}

	@app.post("/event-sources/timer")
	async def create_timer_source(config: TimerSourceConfig):
		"""Create a new timer event source"""
		registry = get_event_registry()
		try:
			source = await registry.register(config)
			return {
				"status": "created",
				"source": source.get_status()
			}
		except ValueError as e:
			raise HTTPException(status_code=400, detail=str(e))

	@app.post("/event-sources/fswatch")
	async def create_fswatch_source(config: FSWatchSourceConfig):
		"""Create a new filesystem watcher event source"""
		registry = get_event_registry()
		try:
			source = await registry.register(config)
			return {
				"status": "created",
				"source": source.get_status()
			}
		except ValueError as e:
			raise HTTPException(status_code=400, detail=str(e))

	@app.post("/event-sources/webhook")
	async def create_webhook_source(config: WebhookSourceConfig):
		"""Create a new webhook event source"""
		registry = get_event_registry()
		try:
			source = await registry.register(config)
			return {
				"status": "created",
				"source": source.get_status()
			}
		except ValueError as e:
			raise HTTPException(status_code=400, detail=str(e))

	@app.post("/event-sources/browser")
	async def create_browser_source(config: BrowserSourceConfig):
		"""Create a new browser event source (webcam, microphone, etc.)"""
		registry = get_event_registry()
		try:
			source = await registry.register(config)
			return {
				"status": "created",
				"source": source.get_status()
			}
		except ValueError as e:
			raise HTTPException(status_code=400, detail=str(e))

	@app.post("/event-sources/browser/{source_id}/event")
	async def receive_browser_event(source_id: str, data: dict):
		"""Receive a browser media event (frame, audio chunk) from the frontend"""
		registry = get_event_registry()
		source = registry.get(source_id)
		if not source:
			raise HTTPException(status_code=404, detail=f"Source not found: {source_id}")
		if not isinstance(source, BrowserSource):
			raise HTTPException(status_code=400, detail=f"Source {source_id} is not a browser source")
		if not source.is_running:
			raise HTTPException(status_code=400, detail=f"Source {source_id} is not running")
		client_id = data.pop("client_id", None)
		await source.receive_event(data, client_id=client_id)
		return {"status": "ok"}

	@app.post("/event-sources/delete/{source_id}")
	async def delete_event_source(source_id: str):
		"""Delete an event source"""
		registry = get_event_registry()
		try:
			await registry.unregister(source_id)
			return {
				"status": "deleted",
				"source_id": source_id
			}
		except ValueError as e:
			raise HTTPException(status_code=404, detail=str(e))

	@app.post("/event-sources/{source_id}/start")
	async def start_event_source(source_id: str):
		"""Manually start an event source"""
		registry = get_event_registry()
		source = registry.get(source_id)
		if not source:
			raise HTTPException(status_code=404, detail=f"Source not found: {source_id}")
		try:
			await source.start()
			return {
				"status": "started",
				"source": source.get_status()
			}
		except Exception as e:
			raise HTTPException(status_code=500, detail=str(e))

	@app.post("/event-sources/{source_id}/stop")
	async def stop_event_source(source_id: str):
		"""Manually stop an event source"""
		registry = get_event_registry()
		source = registry.get(source_id)
		if not source:
			raise HTTPException(status_code=404, detail=f"Source not found: {source_id}")
		try:
			await source.stop()
			return {
				"status": "stopped",
				"source": source.get_status()
			}
		except Exception as e:
			raise HTTPException(status_code=500, detail=str(e))

	@app.post("/event-sources/status")
	async def get_event_registry_status():
		"""Get overall event registry status"""
		registry = get_event_registry()
		return {
			"status": "ok",
			**registry.get_status()
		}


	# === Dynamic Options API ===

	_options_providers: Dict[str, callable] = {}

	def register_options_provider(key: str, fn: callable):
		_options_providers[key] = fn

	def _get_model_sources(context=None):
		return ["ollama", "openai", "anthropic", "groq", "google"]

	def _get_model_names(context=None):
		return ["mistral", "llama3", "gpt-4o", "claude-sonnet", "gemini-pro"]

	register_options_provider("model_sources", _get_model_sources)
	register_options_provider("model_names", _get_model_names)

	@app.post("/options/{provider_key}")
	async def get_options(provider_key: str):
		if provider_key not in _options_providers:
			raise HTTPException(status_code=404, detail=f"Unknown options provider: {provider_key}")
		fn = _options_providers[provider_key]
		options = await fn() if asyncio.iscoroutinefunction(fn) else fn()
		return {"options": options}


	# === Sub-Graph Templates API ===

	_templates_path = str(Path(__file__).parent / "templates.json")

	def _load_templates() -> list:
		if not os.path.exists(_templates_path):
			return []
		try:
			with open(_templates_path, "r") as f:
				return json.load(f)
		except Exception as e:
			log_print(f"Error loading templates: {e}")
			return []

	def _save_templates(templates: list):
		try:
			with open(_templates_path, "w") as f:
				json.dump(templates, f, indent=2)
		except Exception as e:
			log_print(f"Error saving templates: {e}")

	@app.post("/templates/list")
	async def list_templates():
		templates = _load_templates()
		meta_list = []
		for t in templates:
			meta_list.append({
				"id":        t.get("id"),
				"name":      t.get("name", "Untitled"),
				"description": t.get("description", ""),
				"builtIn":   t.get("builtIn", False),
				"createdAt": t.get("createdAt", ""),
				"nodeCount": t.get("nodeCount", 0),
				"edgeCount": t.get("edgeCount", 0),
			})
		return {"templates": meta_list}

	@app.post("/templates/get/{template_id}")
	async def get_template(template_id: str):
		templates = _load_templates()
		for t in templates:
			if t.get("id") == template_id:
				return {"template": t}
		raise HTTPException(status_code=404, detail=f"Template not found: {template_id}")

	@app.post("/templates/save")
	async def save_template(request: TemplateSaveRequest):
		templates = _load_templates()
		tpl = request.template
		tpl_id = tpl.get("id")
		if not tpl_id:
			raise HTTPException(status_code=400, detail="Template must have an id")
		# Upsert
		found = False
		for i, t in enumerate(templates):
			if t.get("id") == tpl_id:
				if t.get("builtIn", False):
					raise HTTPException(status_code=403, detail="Cannot overwrite built-in template")
				templates[i] = tpl
				found = True
				break
		if not found:
			templates.append(tpl)
		_save_templates(templates)
		return {"status": "ok", "id": tpl_id}

	@app.post("/templates/delete/{template_id}")
	async def delete_template(template_id: str):
		templates = _load_templates()
		for t in templates:
			if t.get("id") == template_id:
				if t.get("builtIn", False):
					raise HTTPException(status_code=403, detail="Cannot delete built-in template")
				templates.remove(t)
				_save_templates(templates)
				return {"status": "ok"}
		raise HTTPException(status_code=404, detail=f"Template not found: {template_id}")

	@app.post("/templates/rename/{template_id}")
	async def rename_template(template_id: str, request: TemplateRenameRequest):
		templates = _load_templates()
		for t in templates:
			if t.get("id") == template_id:
				if t.get("builtIn", False):
					raise HTTPException(status_code=403, detail="Cannot rename built-in template")
				t["name"] = request.name
				_save_templates(templates)
				return {"status": "ok"}
		raise HTTPException(status_code=404, detail=f"Template not found: {template_id}")


	# === Text-to-Workflow Generation API ===

	def _build_node_catalog(code: str) -> str:
		"""Parse schema source code to build a compact node catalog for the LLM."""
		lines = code.split('\n')
		catalog = []
		current_class = None
		current_type_val = None
		fields = []

		for line in lines:
			stripped = line.strip()
			# Detect class definition
			class_match = re.match(r'^class\s+(\w+)\s*\(', stripped)
			if class_match:
				# Flush previous class
				if current_class and current_type_val and fields:
					inputs = [f for f in fields if f[2] in ('INPUT', 'MULTI_INPUT')]
					outputs = [f for f in fields if f[2] in ('OUTPUT', 'MULTI_OUTPUT')]
					parts = [f'{current_class}: type="{current_type_val}"']
					if inputs:
						parts.append('inputs: [' + ', '.join(f'{f[0]}:{f[1]}' for f in inputs) + ']')
					if outputs:
						parts.append('outputs: [' + ', '.join(f'{f[0]}:{f[1]}' for f in outputs) + ']')
					catalog.append(', '.join(parts))
				current_class = class_match.group(1)
				current_type_val = None
				fields = []
				continue

			if not current_class:
				continue

			# Parse field lines like: name : Annotated[Type, FieldRole.ROLE] = default
			field_match = re.match(r'^(\w+)\s*:\s*Annotated\[(.+?),\s*FieldRole\.(\w+)', stripped)
			if field_match:
				fname = field_match.group(1)
				ftype = field_match.group(2).strip()
				frole = field_match.group(3)

				# Extract type value from Literal
				if frole == 'CONSTANT' and 'Literal[' in ftype:
					lit_match = re.search(r'Literal\["([^"]+)"\]', ftype)
					if lit_match:
						current_type_val = lit_match.group(1)
					continue

				if frole == 'ANNOTATION':
					continue

				# Simplify type names
				ftype = re.sub(r'^Optional\[(.+)\]$', r'\1', ftype)
				ftype = ftype.replace('Dict[str, Any]', 'Dict').replace('List[str]', 'List')
				ftype = ftype.replace('Union[List, Dict]', 'Dict|List')
				ftype = ftype.replace('Union[int, str]', 'int|str')
				ftype = ftype.replace('Union[List[str], Dict[str, Any]]', 'Dict|List')

				fields.append((fname, ftype, frole))

		# Flush last class
		if current_class and current_type_val and fields:
			inputs = [f for f in fields if f[2] in ('INPUT', 'MULTI_INPUT')]
			outputs = [f for f in fields if f[2] in ('OUTPUT', 'MULTI_OUTPUT')]
			parts = [f'{current_class}: type="{current_type_val}"']
			if inputs:
				parts.append('inputs: [' + ', '.join(f'{f[0]}:{f[1]}' for f in inputs) + ']')
			if outputs:
				parts.append('outputs: [' + ', '.join(f'{f[0]}:{f[1]}' for f in outputs) + ']')
			catalog.append(', '.join(parts))

		return '\n'.join(catalog)

	_GENERATE_SYSTEM_PROMPT = """You generate workflow JSON for a visual node editor.

## Available Node Types
{node_catalog}

## Output Format
Return ONLY valid JSON (no markdown, no explanation), in this format:
{{
  "type": "workflow",
  "nodes": [
    {{"type": "node_type_snake_case", "field_name": "value", ...}},
    ...
  ],
  "edges": [
    {{"type": "edge", "source": 0, "target": 1, "source_slot": "output_field_name", "target_slot": "input_field_name"}},
    ...
  ]
}}

## Rules
- Always start with a start_flow node (index 0) and end with an end_flow or sink_flow node
- Connect nodes via edges: source/target are node indices (0-based), source_slot/target_slot are field names
- Only use node types from the catalog above
- For TransformFlow, set lang="python" and write the script in the "script" field
- source_slot must be an output field name, target_slot must be an input field name
- Return ONLY the JSON object, nothing else
"""

	def _extract_json_from_response(text: str) -> dict:
		"""Extract JSON from LLM response, handling markdown code blocks."""
		text = text.strip()
		# Try direct JSON parse first
		try:
			return json.loads(text)
		except json.JSONDecodeError:
			pass
		# Try extracting from markdown code block
		match = re.search(r'```(?:json)?\s*\n?([\s\S]*?)\n?```', text)
		if match:
			try:
				return json.loads(match.group(1).strip())
			except json.JSONDecodeError:
				pass
		# Try finding first { to last }
		start = text.find('{')
		end = text.rfind('}')
		if start != -1 and end != -1 and end > start:
			try:
				return json.loads(text[start:end + 1])
			except json.JSONDecodeError:
				pass
		raise ValueError("Could not extract valid JSON from LLM response")

	_generation_cache = {"config_hash": None, "backend": None, "agent_index": None}

	def _build_generation_agent(request: GenerateWorkflowRequest, system_prompt: str):
		"""Build an Agno agent subgraph from generation request config.

		Constructs a Workflow graph with BackendConfig → ModelConfig → AgentOptionsConfig → AgentConfig
		(plus optional MemoryManager, SessionManager, Tools, Knowledge) and builds it via build_backend_agno().
		Results are cached and reused when the config hasn't changed.
		"""
		from schema import (
			BackendConfig, ModelConfig, AgentOptionsConfig, AgentConfig,
			MemoryManagerConfig, SessionManagerConfig, ToolConfig,
			KnowledgeManagerConfig, ContentDBConfig, IndexDBConfig,
			EmbeddingConfig, Edge, Workflow
		)
		from impl_agno import build_backend_agno

		# Config hash for cache invalidation
		config_hash = hash(json.dumps({
			"backend": request.backend, "model": request.model, "options": request.options,
			"memory": request.memory, "session": request.session, "tools": request.tools,
			"knowledge": request.knowledge, "system_prompt": system_prompt,
		}, sort_keys=True, default=str))

		cache = _generation_cache
		if cache["config_hash"] == config_hash and cache["backend"] is not None:
			return cache["backend"], cache["agent_index"]

		# Build nodes and edges for the agent subgraph
		nodes = []
		edges = []

		# 0: BackendConfig (always present — field is 'name' in schema, 'engine' in frontend)
		bcfg = request.backend or {}
		nodes.append(BackendConfig(name=bcfg.get("engine", "agno")))
		backend_idx = 0

		# 1: ModelConfig (always present)
		mcfg = request.model or {}
		nodes.append(ModelConfig(
			source  = mcfg.get("source", "ollama"),
			name    = mcfg.get("name", "mistral"),
			version = mcfg.get("version", ""),
		))
		model_idx = 1

		# 2: AgentOptionsConfig (always present)
		ocfg = request.options or {}
		nodes.append(AgentOptionsConfig(
			name            = ocfg.get("name", "Workflow Generator"),
			description     = ocfg.get("description", None),
			instructions    = ocfg.get("instructions", None),
			prompt_override = ocfg.get("prompt_override", None) or system_prompt,
			markdown        = ocfg.get("markdown", False),
		))
		options_idx = 2

		next_idx = 3

		# Optional: MemoryManagerConfig
		memory_idx = None
		if request.memory:
			m = request.memory
			nodes.append(MemoryManagerConfig(
				query   = m.get("query", False),
				update  = m.get("update", False),
				managed = m.get("managed", False),
				prompt  = m.get("prompt", None),
			))
			memory_idx = next_idx
			edges.append(Edge(source=model_idx, target=memory_idx, source_slot="get", target_slot="model"))
			next_idx += 1

		# Optional: SessionManagerConfig
		session_idx = None
		if request.session:
			s = request.session
			nodes.append(SessionManagerConfig(
				query        = s.get("query", False),
				update       = s.get("update", False),
				history_size = s.get("history_size", 10),
				prompt       = s.get("prompt", None),
			))
			session_idx = next_idx
			next_idx += 1

		# Optional: ToolConfig[] (multiple)
		tool_indices = []
		if request.tools:
			for t in request.tools:
				nodes.append(ToolConfig(
					name = t.get("name", ""),
					args = t.get("args", None),
				))
				tool_indices.append(next_idx)
				next_idx += 1

		# Optional: KnowledgeManagerConfig (needs ContentDB + IndexDB + Embedding)
		knowledge_idx = None
		if request.knowledge:
			k = request.knowledge
			# EmbeddingConfig (uses same source as model)
			nodes.append(EmbeddingConfig(
				source = mcfg.get("source", "ollama"),
				name   = mcfg.get("name", "mistral"),
			))
			embed_idx = next_idx
			next_idx += 1
			# ContentDBConfig
			cdb = k.get("content_db", {})
			nodes.append(ContentDBConfig(
				engine = cdb.get("engine", "sqlite"),
				url    = cdb.get("url", "storage/gen_content"),
			))
			cdb_idx = next_idx
			next_idx += 1
			# IndexDBConfig
			idb = k.get("index_db", {})
			nodes.append(IndexDBConfig(
				engine = idb.get("engine", "lancedb"),
				url    = idb.get("url", "storage/gen_index"),
			))
			idb_idx = next_idx
			next_idx += 1
			edges.append(Edge(source=embed_idx, target=idb_idx, source_slot="get", target_slot="embedding"))
			# KnowledgeManagerConfig
			nodes.append(KnowledgeManagerConfig(
				query       = k.get("query", True),
				description = k.get("description", None),
				max_results = k.get("max_results", 10),
				urls        = k.get("urls", None),
			))
			knowledge_idx = next_idx
			next_idx += 1
			edges.append(Edge(source=cdb_idx, target=knowledge_idx, source_slot="get", target_slot="content_db"))
			edges.append(Edge(source=idb_idx, target=knowledge_idx, source_slot="get", target_slot="index_db"))

		# AgentConfig (last node — connects to all above)
		# For MULTI_INPUT tools, use string keys matching dotted edge slot convention
		tool_keys = [str(i) for i in range(len(tool_indices))] if tool_indices else None
		nodes.append(AgentConfig(
			memory_mgr    = nodes[memory_idx]    if memory_idx    is not None else None,
			session_mgr   = nodes[session_idx]   if session_idx   is not None else None,
			tools         = tool_keys,
			knowledge_mgr = nodes[knowledge_idx] if knowledge_idx is not None else None,
		))
		agent_idx = next_idx

		# Core edges: backend, model, options → agent
		edges.append(Edge(source=backend_idx, target=agent_idx, source_slot="get", target_slot="backend"))
		edges.append(Edge(source=model_idx,   target=agent_idx, source_slot="get", target_slot="model"))
		edges.append(Edge(source=options_idx,  target=agent_idx, source_slot="get", target_slot="options"))
		if memory_idx is not None:
			edges.append(Edge(source=memory_idx, target=agent_idx, source_slot="get", target_slot="memory_mgr"))
		if session_idx is not None:
			edges.append(Edge(source=session_idx, target=agent_idx, source_slot="get", target_slot="session_mgr"))
		# Tools use dotted slot names for MULTI_INPUT: tools.0, tools.1, ...
		for i, ti in enumerate(tool_indices):
			edges.append(Edge(source=ti, target=agent_idx, source_slot="get", target_slot=f"tools.{i}"))
		if knowledge_idx is not None:
			edges.append(Edge(source=knowledge_idx, target=agent_idx, source_slot="get", target_slot="knowledge_mgr"))

		workflow = Workflow(nodes=nodes, edges=edges)
		workflow.link()
		backend  = build_backend_agno(workflow)

		cache.update({"config_hash": config_hash, "backend": backend, "agent_index": agent_idx})
		return backend, agent_idx

	@app.post("/generation-prompt")
	async def get_generation_prompt():
		"""Return the generation system prompt (node catalog + instructions) for chat-based /gen."""
		nonlocal schema_code
		node_catalog = _build_node_catalog(schema_code)
		prompt = _GENERATE_SYSTEM_PROMPT.replace("{node_catalog}", node_catalog)
		return {"prompt": prompt}

	@app.post("/generate-workflow")
	async def generate_workflow(request: GenerateWorkflowRequest):
		nonlocal schema_code

		try:
			# Build node catalog and system prompt
			node_catalog = _build_node_catalog(schema_code)
			system_prompt = _GENERATE_SYSTEM_PROMPT.replace("{node_catalog}", node_catalog)

			# Build user message with history context
			user_message = ""
			if request.history:
				for msg in request.history:
					role = msg.get("role", "user")
					content = msg.get("content", "")
					user_message += f"[{role}]: {content}\n\n"
				user_message += f"[user]: {request.prompt}"
			else:
				user_message = request.prompt

			# Build agent from full subgraph config
			backend, agent_idx = _build_generation_agent(request, system_prompt)
			agent_handle = backend.handles[agent_idx]

			# Call the agent
			result = await backend.run_agent(agent_handle, user_message)
			response_text = result.get("content", "")
			if not isinstance(response_text, str):
				response_text = str(response_text)

			# Extract and validate JSON
			workflow = _extract_json_from_response(response_text)

			if "nodes" not in workflow or not isinstance(workflow["nodes"], list):
				raise ValueError("Generated workflow missing 'nodes' array")
			if "edges" not in workflow:
				workflow["edges"] = []

			node_count = len(workflow["nodes"])
			edge_count = len(workflow["edges"])

			return {
				"workflow": workflow,
				"raw_response": response_text,
				"message": f"Generated {node_count} nodes, {edge_count} edges"
			}

		except ValueError as e:
			raise HTTPException(status_code=422, detail=str(e))
		except ImportError as e:
			raise HTTPException(status_code=502, detail=f"Model provider not available: {e}")
		except Exception as e:
			_generation_cache["backend"] = None
			raise HTTPException(status_code=500, detail=f"Generation failed: {str(e)}")


	log_print("✅ Workflow API endpoints registered")
