# api

import asyncio


from   fastapi   import FastAPI, HTTPException, UploadFile, WebSocket, WebSocketDisconnect, File, Form
from   pydantic  import BaseModel
from   typing    import Any, Dict, List, Optional


from   engine    import WorkflowEngine
from   event_bus import EventType, EventBus
from   manager   import WorkflowManager
from   schema    import Workflow
from   utils     import get_now_str, get_timestamp_str, log_print, serialize_result


class WorkflowUploadRequest(BaseModel):
	workflow : Workflow
	name     : Optional[str] = None


class WorkflowStartRequest(BaseModel):
	name         : str
	initial_data : Optional[Dict[str, Any]] = None


class UserInputRequest(BaseModel):
	node_id    : str
	input_data : Any


class ToolCallRequest(BaseModel):
	args : Any


def setup_api(server: Any, app: FastAPI, event_bus: EventBus, schema_code: str, manager: WorkflowManager, engine: WorkflowEngine):

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


	@app.post("/chat_open/{name}")
	async def chat_open(name: str):
		raise HTTPException(status_code=501, detail=f"Chat open not implemented")
		result = {
			"name"  : name,
			"port"  : 0,
			"error" : 501,
		}
		return result


	@app.post("/chat_close")
	@app.post("/chat_close/{name}")
	async def chat_close(name: Optional[str] = None):
		raise HTTPException(status_code=501, detail=f"Chat close not implemented")
		result = {
			"name"  : name,
			"error" : 501,
		}
		return result


	@app.post("/tool_call/{name}")
	async def tool_call(name: str, request: ToolCallRequest):
		raise HTTPException(status_code=501, detail=f"Tool call not implemented")
		result = {
			"name"    : name,
			"request" : request,
			"error"   : 501,
		}
		return result


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
			execution_id = await engine.start_workflow(
				workflow     = impl["workflow"],
				backend      = impl["backend"],
				initial_data = request.initial_data,
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


	log_print("✅ Workflow API endpoints registered")
