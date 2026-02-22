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
		try:
			name = await manager.add(request.workflow, request.name)
			impl = await manager.impl(name)
			wf   = impl["workflow"].model_dump() if impl else None
			result = {
				"name"     : name,
				"workflow" : wf,
				"status"   : "added" if name else "failed",
			}
			return result
		except Exception as e:
			import traceback
			log_print(f"[API] /add error: {e}\n{traceback.format_exc()}")
			raise HTTPException(status_code=500, detail=str(e))


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
			if isinstance(workflow, dict):
				workflow = {k: v.model_dump() for k, v in workflow.items()}
			else:
				workflow = workflow.model_dump()
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
		"""Create or update a browser event source (webcam, microphone, etc.)"""
		registry = get_event_registry()
		if registry.get(config.id):
			source = await registry.update(config.id, config)
			return {
				"status": "updated",
				"source": source.get_status()
			}
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
		return ["qwen3.5:cloud", "mistral", "llama3", "gpt-4o", "claude-sonnet", "gemini-pro"]

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

	def _parse_nodeinfo_metadata(code: str) -> dict:
		"""Parse @node_info decorators from schema source. Returns {ClassName: {title,desc,section,visible,icon}}."""
		lines = code.split('\n')
		meta = {}
		i = 0
		while i < len(lines):
			s = lines[i].strip()
			if s.startswith('@node_info('):
				# Collect full decorator across lines (track paren depth)
				text  = s
				depth = s.count('(') - s.count(')')
				j     = i + 1
				while depth > 0 and j < len(lines):
					ns     = lines[j].strip()
					text  += ' ' + ns
					depth += ns.count('(') - ns.count(')')
					j     += 1
				# Look ahead past other decorators to find the class
				while j < len(lines):
					ns = lines[j].strip()
					cm = re.match(r'class\s+(\w+)', ns)
					if cm:
						cname   = cm.group(1)
						title_m = re.search(r'title\s*=\s*"([^"]+)"', text) or re.search(r"title\s*=\s*'([^']+)'", text)
						desc_m  = re.search(r'description\s*=\s*"([^"]+)"', text) or re.search(r"description\s*=\s*'([^']+)'", text)
						sect_m  = re.search(r'section\s*=\s*"([^"]+)"', text) or re.search(r"section\s*=\s*'([^']+)'", text)
						vis_m   = re.search(r'visible\s*=\s*(True|False)', text)
						icon_m  = re.search(r'icon\s*=\s*"([^"]+)"', text) or re.search(r"icon\s*=\s*'([^']+)'", text)
						meta[cname] = {
							'title':   title_m.group(1) if title_m else cname,
							'desc':    desc_m.group(1)  if desc_m  else '',
							'section': sect_m.group(1)  if sect_m  else 'Misc',
							'visible': not (vis_m and vis_m.group(1) == 'False'),
							'icon':    icon_m.group(1)  if icon_m  else '',
						}
						break
					elif ns and not ns.startswith(('@', '#', '"""', "'''")):
						break
					j += 1
			i += 1
		return meta

	def _build_node_catalog(code: str) -> str:
		"""Parse schema source code to build a detailed node catalog for the LLM."""
		node_meta = _parse_nodeinfo_metadata(code)
		lines     = code.split('\n')

		# ── Pre-parse DEFAULT_* constant values ───────────────────────────────
		defaults_map: dict = {}
		for line in lines:
			dm = re.match(r'^DEFAULT_(\w+)\s*:\s*\w+\s*=\s*(.+?)(?:\s*#.*)?$', line.strip())
			if dm:
				defaults_map[f'DEFAULT_{dm.group(1)}'] = dm.group(2).strip()

		# ── Type simplification helpers ────────────────────────────────────────
		def _simplify_type(ftype: str) -> str:
			ftype = re.sub(r'^Optional\[(.+)\]$', r'\1', ftype.strip())
			# Literal[...] → show all options as "a"|"b"|...
			lit_m = re.match(r'^Literal\[(.+)\]$', ftype)
			if lit_m:
				raw_opts = lit_m.group(1)
				opts = [o.strip().strip('"').strip("'") for o in raw_opts.split(',')]
				return '|'.join(f'"{o}"' for o in opts if o)
			return (ftype
				.replace('Dict[str, Any]',               'dict')
				.replace('Dict[Union[int, str], str]',   'dict')
				.replace('List[str]',                    'list[str]')
				.replace('List[Any]',                    'list')
				.replace('List[int]',                    'list[int]')
				.replace('Union[List, Dict]',            'dict|list')
				.replace('Union[int, str]',              'int|str')
				.replace('Union[List[str], Dict[str, Any]]', 'dict|list')
				.replace('Any',                          'any')
			)

		def _multi_item_type(ftype_raw: str) -> str:
			"""Extract item type T from Dict[str, T] for MULTI_INPUT/OUTPUT."""
			m = re.match(r'(?:Optional\[)?Dict\[(?:str|Union\[int,\s*str\]),\s*(.+?)\]', ftype_raw.strip())
			return m.group(1).strip() if m else ''

		def _resolve_default(raw: str):
			raw = raw.strip()
			if raw == 'None':
				return None
			# Field(default=...) — extract the default= argument
			fd_m = re.search(r'Field\(default\s*=\s*([^,\)]+)', raw)
			if fd_m:
				inner = fd_m.group(1).strip()
				return _resolve_default(inner)
			# Resolve DEFAULT_* reference
			if raw.startswith('DEFAULT_'):
				val = defaults_map.get(raw)
				if val is None:
					return None
				# val may itself be a quoted string; strip outer quotes for display
				return val
			if raw in ('True', 'False') or re.match(r'^["\'\d]', raw):
				return raw
			return None

		def _extract_description(rhs: str) -> str:
			"""Extract description= from a Field(...) RHS string."""
			m = re.search(r'description\s*=\s*"([^"]*)"', rhs)
			if not m:
				m = re.search(r"description\s*=\s*'([^']*)'" , rhs)
			return m.group(1) if m else ''

		# ── Per-class field parsing ────────────────────────────────────────────
		# Field tuple: (name, display_type, role, default, item_type, description)
		# item_type is only set for MULTI_INPUT/OUTPUT; others use ''
		# description extracted from Field(description="..."); empty string if absent
		nodes         = {}   # {ClassName: {type_val, fields, docstring, parent}}
		current_class  = None
		current_parent = None
		current_type   = None
		current_fields: list = []
		current_docstring    = None
		in_docstring         = False
		docstring_lines: list = []
		docstring_quote      = None
		expecting_doc        = False
		in_property          = False

		def _flush():
			nonlocal current_class, current_parent, current_type, current_fields
			nonlocal current_docstring, in_docstring, docstring_lines, docstring_quote
			nonlocal expecting_doc, in_property
			if current_class and current_type:
				nodes[current_class] = {
					'type':      current_type,
					'fields':    list(current_fields),
					'docstring': current_docstring,
					'parent':    current_parent,
				}
			current_class     = None
			current_parent    = None
			current_type      = None
			current_fields    = []
			current_docstring = None
			in_docstring      = False
			docstring_lines   = []
			docstring_quote   = None
			expecting_doc     = False
			in_property       = False

		for line in lines:
			s = line.strip()

			# New class
			cm = re.match(r'^class\s+(\w+)\s*\((\w+)', s)
			if cm:
				_flush()
				current_class  = cm.group(1)
				current_parent = cm.group(2)
				expecting_doc  = True
				continue

			if not current_class:
				continue

			# ── Multi-line docstring continuation ─────────────────────────────
			if in_docstring:
				if docstring_quote in s:
					idx  = s.index(docstring_quote)
					tail = s[:idx].strip()
					if tail:
						docstring_lines.append(tail)
					current_docstring = ' '.join(docstring_lines)
					in_docstring = False
				else:
					if s:
						docstring_lines.append(s)
				continue

			# ── Class docstring ────────────────────────────────────────────────
			if expecting_doc:
				if s.startswith(('"""', "'''")):
					q       = '"""' if s.startswith('"""') else "'''"
					content = s[len(q):]
					if q in content:
						# Single-line docstring
						current_docstring = content[:content.index(q)].strip()
						expecting_doc = False
					else:
						# Multi-line docstring — collect until closing quote
						docstring_lines = [content.strip()] if content.strip() else []
						docstring_quote = q
						in_docstring    = True
						expecting_doc   = False
					continue
				elif s and not s.startswith('#'):
					expecting_doc = False
				# fall through to field parsing

			# ── @property decorator ────────────────────────────────────────────
			if s == '@property':
				in_property = True
				continue

			# ── @property OUTPUT slot (any def name, not just 'get') ───────────
			pm = re.match(r'^def (\w+)\(self\)\s*->\s*Annotated\[(.+?),\s*FieldRole\.(OUTPUT)\]', s)
			if pm and in_property:
				fname = pm.group(1)
				ftype = re.sub(r'^Optional\[(.+)\]$', r'\1', pm.group(2).strip())
				current_fields.append((fname, _simplify_type(ftype), 'OUTPUT', None, '', ''))
				in_property = False
				continue

			# Reset in_property if something else appears between @property and def
			if in_property and s and not s.startswith(('#', 'def', '@')):
				in_property = False

			# ── Annotated field ────────────────────────────────────────────────
			fm = re.match(r'^(\w+)\s*:\s*Annotated\[(.+?),\s*FieldRole\.(\w+)', s)
			if fm:
				fname, ftype_raw, frole = fm.group(1), fm.group(2).strip(), fm.group(3)
				in_property = False

				if frole == 'CONSTANT' and 'Literal[' in ftype_raw:
					lm = re.search(r'Literal\["([^"]+)"\]', ftype_raw)
					if lm:
						current_type = lm.group(1)
					continue

				if frole == 'ANNOTATION':
					continue

				# Determine display type and item type
				if frole in ('MULTI_INPUT', 'MULTI_OUTPUT'):
					item_t  = _multi_item_type(ftype_raw)
					disp_t  = _simplify_type(ftype_raw)
				else:
					item_t = ''
					disp_t = _simplify_type(ftype_raw)

				# Resolve default value and description
				fdefault = None
				fdesc    = ''
				dm = re.search(r'\]\s*=\s*(.+?)(?:\s*#.*)?$', s)
				if dm:
					rhs      = dm.group(1).strip()
					fdefault = _resolve_default(rhs)
					fdesc    = _extract_description(rhs)

				current_fields.append((fname, disp_t, frole, fdefault, item_t, fdesc))

		_flush()

		# ── Inherit parent fields ──────────────────────────────────────────────
		# Fields declared on invisible base classes (FlowType, NativeType, etc.)
		# must be propagated to their visible children.
		# Blacklist: base-plumbing fields not useful for LLM wiring.
		_INHERIT_BLACKLIST = {'extra', 'id', 'raw'}

		def _get_all_fields(cname: str, visited=None) -> list:
			"""Return all fields (own + inherited) for a class, deduplicated by name."""
			if visited is None:
				visited = set()
			if cname in visited:
				return []
			visited.add(cname)
			info   = nodes.get(cname, {})
			own    = info.get('fields', [])   # own fields always included (no blacklist)
			parent = info.get('parent')
			if not parent or parent not in nodes:
				return own
			parent_fields = _get_all_fields(parent, visited)
			own_names     = {f[0] for f in own}
			# Blacklist applies only to *inherited* plumbing fields, never to own redeclarations
			inherited     = [f for f in parent_fields if f[0] not in own_names and f[0] not in _INHERIT_BLACKLIST]
			return inherited + own   # parent fields first, own last (own overrides)

		# ── Section grouping and formatting ───────────────────────────────────
		section_order = [
			'Endpoints', 'Native Types', 'Data Sources',
			'Configurations', 'Workflow', 'Loops', 'Event Sources',
			'Interactive', 'Tutorial',
		]
		section_labels = {
			'Endpoints':      '─── Endpoint Nodes',
			'Native Types':   '─── Native Value Nodes  (output their value on the "value" slot)',
			'Data Sources':   '─── Data Source Nodes',
			'Configurations': '─── Config Nodes  (wire using source_slot matching the "out:" slot name)',
			'Workflow':       '─── Flow Nodes',
			'Loops':          '─── Loop Nodes',
			'Event Sources':  '─── Event Source Nodes',
			'Interactive':    '─── Interactive Nodes',
			'Tutorial':       '─── Extension/Tutorial Nodes',
		}

		by_section: dict = {s: [] for s in section_order}
		for cname, info in nodes.items():
			m = node_meta.get(cname, {})
			if not m.get('visible', True):
				continue
			sect = m.get('section', 'Other')
			by_section.setdefault(sect, []).append((cname, info, m))

		def fmt_f(name: str, typ: str, dflt, desc: str = '') -> str:
			s = f'{name}({typ})'
			if dflt is not None:
				s += f'={dflt}'
			if desc:
				s += f' – {desc}'
			return s

		out_lines = []
		for sect in section_order:
			entries = by_section.get(sect, [])
			if not entries:
				continue
			out_lines.append(section_labels.get(sect, f'─── {sect}'))
			for cname, info, m in entries:
				type_val = info['type']
				all_fields = _get_all_fields(cname)
				desc = m.get('desc', '')
				icon = m.get('icon', '')

				in_f   = [f for f in all_fields if f[2] == 'INPUT']
				min_f  = [f for f in all_fields if f[2] == 'MULTI_INPUT']
				out_f  = [f for f in all_fields if f[2] == 'OUTPUT']
				mout_f = [f for f in all_fields if f[2] == 'MULTI_OUTPUT']

				header = (f'{icon} ' if icon else '') + type_val
				if desc:
					header += f' – {desc}'
				out_lines.append(header)

				doc = info.get('docstring', '')
				if doc:
					out_lines.append(f'  doc: {doc}')
				if in_f:
					out_lines.append('  in:  ' + ', '.join(fmt_f(f[0], f[1], f[3], f[5]) for f in in_f))
				for f in min_f:
					item_hint = f'(item:{f[4]})' if f[4] else ''
					dflt_hint = f'={f[3]}'        if f[3] is not None else ''
					desc_hint = f' – {f[5]}'      if f[5] else ''
					out_lines.append(f'  multi-in: {f[0]}{item_hint}{dflt_hint}{desc_hint} | wire each branch via target_slot="{f[0]}.<key>"')
				if out_f:
					out_lines.append('  out: ' + ', '.join(fmt_f(f[0], f[1], f[3], f[5]) for f in out_f))
				for f in mout_f:
					item_hint = f'(item:{f[4]})' if f[4] else ''
					dflt_hint = f'={f[3]}'        if f[3] is not None else ''
					desc_hint = f' – {f[5]}'      if f[5] else ''
					out_lines.append(f'  multi-out: {f[0]}{item_hint}{dflt_hint}{desc_hint} | declare in JSON as "{f[0]}": {{"key": null, ...}}; edge source_slot="{f[0]}.<key>"')
				out_lines.append('')

		return '\n'.join(out_lines)

	_GENERATE_SYSTEM_PROMPT = """You generate workflow JSON for a visual node-graph AI workflow editor.

## Runtime Model
A workflow is a directed acyclic graph executed node-by-node in topological order:
- Execution begins at `start_flow` (always index 0) and ends at `end_flow` or `sink_flow`.
- Each node reads from its INPUT slots (wired by edges or set inline in JSON).
- Each node writes to its OUTPUT slots at runtime; downstream nodes consume them via edges.
- Config nodes (backend_config, model_config, etc.) each expose their value through a named
  output slot shown in the catalog as "out:". Use that slot name as source_slot when wiring.
  Example: model_config exposes slot "config"; wire with source_slot="config".
- Data flows as: start_flow.flow_out → [transform/agent/route nodes] → end_flow.flow_in.

## Slot Types
- INPUT       – value consumed by the node; set inline in JSON if not connected via edge.
- OUTPUT      – value produced at runtime; referenced as source_slot in outgoing edges.
- MULTI_INPUT – a named set of sub-inputs. Each sub-input is a separate edge with a dotted
                target_slot, e.g. target_slot="tools.list_dir". Never include these keys inline
                in node JSON (null placeholders cause validation errors).
- MULTI_OUTPUT – named sub-outputs for conditional routing. Declare sub-keys inline in node
                JSON as a dict with null values, e.g. "output": {"support": null, "sales": null}.
                Each branch connects via a dotted source_slot, e.g. source_slot="output.support".

## JSON Format
Return ONLY valid JSON with no markdown fences or explanation:
{
  "type": "workflow",
  "nodes": [
    {
      "type": "node_type_snake_case",
      "field": value,
      "output": {"branch_a": null, "branch_b": null},
      "extra": {"pos": [x, y], "size": [w, h], "name": "Display label"}
    }
  ],
  "edges": [
    {
      "type": "edge",
      "source": 0,
      "target": 1,
      "source_slot": "output_field_name",
      "target_slot": "input_field_name"
    }
  ]
}

Field semantics:
- nodes[i].type        – snake_case type string matching the catalog entry.
- nodes[i].<field>     – INPUT field value; omit if default is acceptable.
- nodes[i].<field>     – MULTI_OUTPUT field: dict of {key: null} declaring route names.
- nodes[i].extra       – optional display metadata (pos, size, name, color); safe to omit.
- edges[*].source      – 0-based index of the source node in the nodes array.
- edges[*].target      – 0-based index of the target node in the nodes array.
- edges[*].source_slot – OUTPUT field name on source node (or "output.key" for MULTI_OUTPUT).
- edges[*].target_slot – INPUT field name on target node (or "tools.key" for MULTI_INPUT).

## Common Patterns

### Agent subgraph
backend_config.config  → agent_config.backend   (source_slot="config")
model_config.config    → agent_config.model      (source_slot="config")
agent_options_config.options → agent_config.options  (source_slot="options")
agent_config.config    → agent_flow.config       (source_slot="config")
Tool nodes connect via dotted target_slot: target_slot="tools.tool_a" → agent_config

### Conditional routing (route_flow)
Declare outputs in JSON: "output": {"branch_a": null, "branch_b": null}
Edge from upstream: source_slot="flow_out" → route_flow.target (string deciding the branch)
Edges from route_flow: source_slot="output.branch_a" → downstream_node.flow_in

### Fan-in merging (merge_flow)
Set strategy: "first" | "last" | "concat" | "all"
Each branch: source_slot="flow_out" → merge_flow, target_slot="input.branch_name" (dotted)
Result: merge_flow.output → downstream.flow_in

### Loops
loop_start_flow.condition (bool) controls iteration. Connect body nodes between
loop_start_flow and loop_end_flow. loop_start_flow.iteration outputs current count.
For lists: for_each_start_flow.items → body → for_each_end_flow; current item on .current output.

### Event-driven workflows
Register a source: timer_source_flow or webhook_source_flow → registered_id output.
Listen: registered_id → event_listener_flow, target_slot="sources.<key>" (dotted MULTI_INPUT).
event_listener_flow.event carries the received event payload.

## Rules
1. Always place start_flow at index 0. Always end with end_flow or sink_flow.
2. source_slot must be an OUTPUT or MULTI_OUTPUT field name shown in the catalog "out:" line.
3. target_slot must be an INPUT or MULTI_INPUT field name shown in the catalog "in:" line.
4. MULTI_OUTPUT: declare sub-keys in node JSON as {"field": {"key": null}}; use dotted source_slot.
5. MULTI_INPUT: use dotted target_slot only; never include sub-keys inline in node JSON.
6. transform_flow: set lang="python"; write Python that assigns to the `output` variable.
7. Config nodes: use source_slot matching their "out:" slot (e.g. "config" for model_config).
8. Omit node fields that keep their default values to keep JSON concise.
9. Return ONLY the JSON object, nothing else.

## Available Node Types
{node_catalog}"""

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
		"""Build an AI agent subgraph from generation request config.

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


	# ── Docs / tutorials ──────────────────────────────────────────────

	_docs_dir = Path(__file__).resolve().parent.parent / "docs"

	@app.post("/docs")
	async def list_docs():
		"""Return the list of available documentation files."""
		if not _docs_dir.is_dir():
			return []
		items = []
		for md in sorted(_docs_dir.glob("*.md")):
			title = md.stem
			try:
				first_line = md.read_text(encoding="utf-8", errors="replace").split("\n", 1)[0]
				if first_line.startswith("# "):
					title = first_line[2:].strip()
			except Exception:
				pass
			has_workflow = (md.with_suffix(".json")).is_file()
			items.append({"filename": md.name, "title": title, "hasWorkflow": has_workflow})
		return items

	class DocRequest(BaseModel):
		filename: str

	@app.post("/docs/file")
	async def get_doc(req: DocRequest):
		"""Return the contents of a documentation file (.md or .json)."""
		filename = req.filename
		if ".." in filename or "/" in filename or "\\" in filename:
			raise HTTPException(status_code=400, detail="Invalid filename")
		path = _docs_dir / filename
		if not path.suffix in (".md", ".json") or not path.is_file():
			raise HTTPException(status_code=404, detail="File not found")
		content = path.read_text(encoding="utf-8", errors="replace")
		if path.suffix == ".json":
			return json.loads(content)
		return {"filename": filename, "content": content}

	log_print("✅ Workflow API endpoints registered")
