# launch

import argparse
import asyncio
import os
import uvicorn


from   dotenv                  import load_dotenv
from   fastapi                 import FastAPI, HTTPException
from   fastapi.middleware.cors import CORSMiddleware


from   api                     import setup_workflow_api
from   engine                  import WorkflowContext, WorkflowEngine
from   event_bus               import get_event_bus
from   schema                  import DEFAULT_APP_PORT, DEFAULT_APP_SEED, Workflow
from   utils                   import get_time_str, log_print, seed_everything


load_dotenv()

current_dir = os.path.dirname(os.path.abspath(__file__))


def add_middleware(app: FastAPI):
	app.add_middleware(
		CORSMiddleware,
		allow_credentials = False,
		allow_headers     = ["*"],
		allow_methods     = ["*"],
		allow_origins     = ["*"],
	)


def apply_seed():
	if DEFAULT_APP_SEED is not None:
		seed_everything(DEFAULT_APP_SEED)


if True:
	parser = argparse.ArgumentParser(description="App configuration")
	parser .add_argument("--port", type=int, default=DEFAULT_APP_PORT, help="Listening port for control server")
	args   = parser.parse_args()


if True:
	schema = None
	try:
		schema_path = os.path.join(current_dir, "schema.py")
		with open(schema_path, "r", encoding="utf-8") as f:
			schema_text = f.read()
		schema = {
			"schema" : schema_text,
		}
	except Exception as e:
		log_print(f"Error reading schema definition: {e}")
		raise HTTPException(status_code=500, detail=str(e))


if True:
	event_bus = get_event_bus()
	engine    = WorkflowEngine(event_bus)


# if True:
# 	impl_modules = [os.path.splitext(f)[0] for f in os.listdir(current_dir) if (f.startswith("impl_") and f.endswith(".py"))]
# 	for module_name in impl_modules:
# 		try:
# 			impl_module = __import__(module_name)
# 			impl_module.register()
# 		except Exception as e:
# 			log_print(f"Error importing module '{module_name}': {e}")


if True:
	ctrl_server     = None
	ctrl_status     = None
	apps            = None
	running_servers = []
	ctrl_app        = FastAPI(title="Control")
	add_middleware(ctrl_app)


async def run_server():
	global args, ctrl_app, ctrl_server, ctrl_status

	host        = "0.0.0.0"
	port        = args.port
	ctrl_config = uvicorn.Config(ctrl_app, host=host, port=port)
	ctrl_server = uvicorn.Server(ctrl_config)
	ctrl_status = {"status" : "ready"}

	await ctrl_server.serve()


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


@ctrl_app.post("/add/{id}")
async def add_workflow():
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


if __name__ == "__main__":
	log_print("Server starting...")
	asyncio.run(run_server())
	log_print("Server shut down")
