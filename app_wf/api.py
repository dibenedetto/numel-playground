# api

from fastapi   import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from pydantic  import BaseModel
from typing    import Any, Dict, Optional


from engine    import WorkflowEngine
from event_bus import EventBus
from manager   import WorkflowManager
from schema    import Workflow
from utils     import log_print


class WorkflowStartRequest(BaseModel):
	workflow     : Workflow
	initial_data : Optional[Dict[str, Any]] = None

	def prepare(self):
		if self.workflow:
			self.workflow.link()


class UserInputRequest(BaseModel):
	node_id    : str
	input_data : Any

	def prepare(self):
		pass


def setup_api(app: FastAPI, event_bus: EventBus, manager: WorkflowManager, engine: WorkflowEngine):
	"""Setup workflow API endpoints"""

	# current_routes = [route.path for route in app.routes]
	# if "/workflow/start" in current_routes:
	# 	return

	# @app.post("/workflow/start")
	async def start_workflow(request: WorkflowStartRequest):
		"""Start a new workflow execution"""
		try:
			request.prepare()
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
			request.prepare()
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










@ctrl_app.post("/shutdown")
async def shutdown_server():
	global ctrl_app, ctrl_server, ctrl_status, engine

	await engine.cancel_all_executions()

	if ctrl_server and ctrl_server.should_exit is False:
		ctrl_server.should_exit = True

	engine      = None
	ctrl_app    = None
	ctrl_server = None
	ctrl_status = None
	return {"message": "Server shut down"}


@ctrl_app.post("/status")
async def server_status():
	global ctrl_status, engine
	
	status = dict(ctrl_status)
	status["executions"] = engine.get_all_execution_states()
	
	return status


@ctrl_app.post("/ping")
async def ping():
	timestamp = get_time_str()
	result = {
		"message"   : "pong",
		"timestamp" : timestamp,
	}
	return result


@ctrl_app.post("/schema")
async def export_schema():
	"""Export app schema"""
	global schema
	return schema


@ctrl_app.post("/add")
async def add_workflow(request: WorkflowStartRequest):
	"""Export app schema"""
	global schema
	return schema


@ctrl_app.post("/remove/{id}")
async def remove_workflow():
	"""Export app schema"""
	global schema
	return schema


@ctrl_app.post("/get/{id}")
async def get_workflow():
	"""Export app schema"""
	global schema
	return schema


@ctrl_app.post("/list")
async def list_workflows():
	"""Export app schema"""
	global schema
	return schema


@ctrl_app.post("/start/{id}")
async def start_workflow():
	global apps, config, ctrl_status, running_servers, workflow_eng
	if apps is not None:
		return {"error": "App is already running"}
	try:
		host = "0.0.0.0"
		port = DEFAULT_APP_PORT

		apply_seed(config)

		active_agents = [True] * len(config.agents)
		backends      = get_backends()
		apps          = []

		agent_index   = 0
		agent_remap   = {}
		tool_remap    = {}

		for backend, ctor in backends.values():
			bkd_cfg, agent_rmp, tool_rmp = extract_config(config, backend, active_agents)
			if not bkd_cfg or not bkd_cfg.agents:
				continue

			app     = ctor(bkd_cfg)
			app_idx = len(apps)
			rmp     = { global_idx : (app_idx, local_idx) for global_idx, local_idx in agent_rmp.items() }
			agent_remap.update(rmp)

			apps.append(app)

			for i in range(len(app.config.agents)):
				agent_app = app.generate_app(i)
				add_middleware(agent_app)

				agent_config = uvicorn.Config(agent_app, host=host, port=agent_port)
				agent_server = uvicorn.Server(agent_config)
				agent_task   = asyncio.create_task(agent_server.serve())
				item         = {
					"server" : agent_server,
					"task"   : agent_task,
				}
				running_servers.append(item)

				config.agents[agent_index].port = agent_port
				agent_index += 1
				agent_port  += 1

		# Initialize workflow engine
		workflow_ctx = WorkflowContext (apps, agent_remap, tool_remap)
		workflow_eng = WorkflowEngine  (workflow_ctx, event_bus)
		setup_workflow_api(ctrl_app, workflow_eng, event_bus)

		log_print("✅ Workflow engine initialized")

		ctrl_status["config"] = config
		ctrl_status["status"] = "running"

	except Exception as e:
		log_print(f"Error starting app: {e}")
		return {"error": str(e)}

	return ctrl_status


@ctrl_app.post("/exec_status/{execution_id}")
async def execution_status():
	global apps, config, ctrl_status, running_servers, workflow_eng
	if apps is None:
		return {"error": "App is not running"}
	try:
		for item in running_servers:
			server = item["server"]
			task   = item["task"  ]
			if server and server.should_exit is False:
				server.should_exit = True
			if task:
				await task
		for app in apps:
			app.close()
		for agent in config.agents:
			agent.port = 0
		
		# Clean up workflow engine
		workflow_eng = None
		log_print("Workflow engine stopped")
		
		apps                  = None
		running_servers       = []
		ctrl_status["config"] = None
		ctrl_status["status"] = "stopped"
	except Exception as e:
		log_print(f"Error stopping app: {e}")
		return {"error": str(e)}
	return ctrl_status


@ctrl_app.post("/exec_cancel/{execution_id}")
async def cancel_execution():
	global apps, config, ctrl_status, running_servers, workflow_eng
	if apps is None:
		return {"error": "App is not running"}
	try:
		for item in running_servers:
			server = item["server"]
			task   = item["task"  ]
			if server and server.should_exit is False:
				server.should_exit = True
			if task:
				await task
		for app in apps:
			app.close()
		for agent in config.agents:
			agent.port = 0
		
		# Clean up workflow engine
		workflow_eng = None
		log_print("Workflow engine stopped")
		
		apps                  = None
		running_servers       = []
		ctrl_status["config"] = None
		ctrl_status["status"] = "stopped"
	except Exception as e:
		log_print(f"Error stopping app: {e}")
		return {"error": str(e)}
	return ctrl_status
