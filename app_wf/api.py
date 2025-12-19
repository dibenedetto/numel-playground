# api

from fastapi   import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from pydantic  import BaseModel
from typing    import Any, Dict, Optional


from engine    import WorkflowEngine
from event_bus import EventBus
from manager   import WorkflowManager
from schema    import Workflow
from utils     import get_time_str, log_print


class WorkflowUploadRequest(BaseModel):
	workflow : Workflow
	name     : Optional[str] = None


class WorkflowStartRequest(BaseModel):
	name         : str
	initial_data : Optional[Dict[str, Any]] = None


class UserInputRequest(BaseModel):
	node_id    : str
	input_data : Any


def setup_api(server: Any, app: FastAPI, event_bus: EventBus, schema: str, manager: WorkflowManager, engine: WorkflowEngine):

	@app.post("/shutdown")
	async def shutdown_server():
		nonlocal engine, server
		await engine.cancel_all_executions()
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
			"timestamp" : get_time_str(),
		}
		return result


	@app.post("/schema")
	async def export_schema():
		nonlocal schema
		result = {
			"schema": schema,
		}
		return result


	@app.post("/add")
	async def add_workflow(request: WorkflowUploadRequest):
		nonlocal manager
		name   = await manager.add(request.workflow, request.name)
		result = {
			"name": name,
		}
		return result


	@app.post("/remove/{name}")
	async def remove_workflow(name: str):
		nonlocal manager
		status = await manager.remove(name)
		result = {
			"name"   : name,
			"status" : "removed" if status else "failed",
		}
		return result


	@app.post("/get/{name}")
	async def get_workflow(name: str):
		nonlocal manager
		workflow = await manager.get(name)
		result   = {
			"name"     : name,
			"workflow" : workflow.model_dump() if workflow else None,
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
			workflow = engine.get(request.name)
			if not workflow:
				raise HTTPException(status_code=404, detail=f"Workflow 'request.name' not found")
			execution_id = await engine.start_workflow(workflow=workflow, initial_data=request.initial_data)
			result = {
				"execution_id" : execution_id,
				"status"       : "started",
			}
			return result
		except Exception as e:
			log_print(f"Error starting workflow: {e}")
			raise HTTPException(status_code=500, detail=str(e))


	@app.post("/exec_state/{execution_id}")
	async def execution_state(execution_id: str):
		nonlocal engine
		state  = engine.get_execution_state(execution_id)
		result = {
			"execution_id" : execution_id,
			"state"        : state,
		}
		return result


	@app.post("/exec_cancel/{execution_id}")
	async def cancel_execution(execution_id: str):
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


	@app.websocket("/events")
	async def workflow_events(websocket: WebSocket):
		nonlocal event_bus
		await event_bus.add_websocket_client(websocket)
		try:
			while True:
				try:
					data = await websocket.receive_text()
					log_print(f"Received WebSocket message: {data}")
				except Exception as e:
					log_print(f"WebSocket receive error: {e}")
					break
		except WebSocketDisconnect:
			log_print("WebSocket client disconnected")
			event_bus.remove_websocket_client(websocket)
		except Exception as e:
			log_print(f"WebSocket error: {e}")
			event_bus.remove_websocket_client(websocket)


	log_print("✅ Workflow API endpoints registered")
