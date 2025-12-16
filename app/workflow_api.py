# workflow_api.py
# Updated for workflow_schema_new.py

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from typing import Any, Dict, Optional

from event_bus import EventBus
from utils import log_print
from workflow_engine import WorkflowEngine
from workflow_schema_new import Workflow


class WorkflowStartRequest(BaseModel):
	workflow: Workflow
	initial_data: Optional[Dict[str, Any]] = None


class UserInputRequest(BaseModel):
	node_id: str
	input_data: Any


def setup_workflow_api(app: FastAPI, workflow_engine: WorkflowEngine, event_bus: EventBus):
	"""Setup workflow API endpoints"""

	# current_routes = [route.path for route in app.routes]
	# if "/workflow/start" in current_routes:
	# 	return

	# @app.post("/workflow/start")
	async def start_workflow(request: WorkflowStartRequest):
		"""Start a new workflow execution"""
		try:
			execution_id = await workflow_engine.start_workflow(
				workflow=request.workflow,
				initial_data=request.initial_data
			)
			return {
				"execution_id": execution_id,
				"status": "started"
			}
		except Exception as e:
			log_print(f"Error starting workflow: {e}")
			raise HTTPException(status_code=500, detail=str(e))

	# @app.post("/workflow/{execution_id}/cancel")
	async def cancel_workflow(execution_id: str):
		"""Cancel a running workflow"""
		try:
			await workflow_engine.cancel_execution(execution_id)
			return {"status": "cancelled", "execution_id": execution_id}
		except Exception as e:
			log_print(f"Error cancelling workflow: {e}")
			raise HTTPException(status_code=500, detail=str(e))

	# @app.post("/workflow/{execution_id}/status")
	async def get_workflow_status(execution_id: str):
		"""Get workflow execution status"""
		state = workflow_engine.get_execution_state(execution_id)
		if not state:
			raise HTTPException(status_code=404, detail="Execution not found")
		return state

	# @app.post("/workflow/list")
	async def list_workflows():
		"""List all workflow executions"""
		return workflow_engine.list_executions()

	# @app.post("/workflow/{execution_id}/input")
	async def provide_user_input(execution_id: str, request: UserInputRequest):
		"""Provide user input for waiting workflow"""
		try:
			await workflow_engine.provide_user_input(
				execution_id=execution_id,
				node_id=request.node_id,
				user_input=request.input_data
			)
			return {"status": "input_received"}
		except Exception as e:
			log_print(f"Error providing user input: {e}")
			raise HTTPException(status_code=500, detail=str(e))

	# @app.websocket("/workflow/events")
	async def workflow_events_websocket(websocket: WebSocket):
		"""WebSocket endpoint for real-time workflow events"""
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

	app.add_api_route("/workflow/start"                , start_workflow     , methods=["POST"], tags=["Dynamic"])
	app.add_api_route("/workflow/{execution_id}/cancel", cancel_workflow    , methods=["POST"], tags=["Dynamic"])
	app.add_api_route("/workflow/{execution_id}/status", get_workflow_status, methods=["POST"], tags=["Dynamic"])
	app.add_api_route("/workflow/list"                 , list_workflows     , methods=["POST"], tags=["Dynamic"])
	app.add_api_route("/workflow/{execution_id}/input" , provide_user_input , methods=["POST"], tags=["Dynamic"])

	app.add_api_websocket_route("/workflow/events", workflow_events_websocket)

	app.openapi_schema = None
	
	log_print("✅ Workflow API endpoints registered")
