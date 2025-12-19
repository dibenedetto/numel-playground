# launch

import argparse
import asyncio
import os
import uvicorn


from   dotenv                  import load_dotenv
from   fastapi                 import FastAPI, HTTPException
from   fastapi.middleware.cors import CORSMiddleware
from   typing                  import Any


from   api                     import setup_api
from   engine                  import WorkflowEngine
from   event_bus               import EventBus, get_event_bus
from   manager                 import WorkflowManager
from   schema                  import DEFAULT_APP_PORT, DEFAULT_APP_SEED
from   utils                   import log_print, seed_everything


load_dotenv()


async def run_server(args: Any):
	current_dir = os.path.dirname(os.path.abspath(__file__))

	if args.seed != 0:
		seed_everything(args.seed)

	try:
		with open(current_dir / "schema.py", "r", encoding="utf-8") as f:
			schema_text = f.read()
		schema = {
			"schema" : schema_text,
		}
	except Exception as e:
		log_print(f"Error reading schema definition: {e}")
		raise HTTPException(status_code=500, detail=str(e))

	event_bus : EventBus        = get_event_bus   ()
	manager   : WorkflowManager = WorkflowManager (event_bus)
	engine    : WorkflowEngine  = WorkflowEngine  (event_bus)

	app : FastAPI = FastAPI(title="Control")
	app.add_middleware(
		CORSMiddleware,
		allow_credentials = False,
		allow_headers     = ["*"],
		allow_methods     = ["*"],
		allow_origins     = ["*"],
	)

	setup_api(app, event_bus, schema, manager, engine)

	example_config_path = current_dir / "config.json"
	await manager.load(example_config_path, "Simple Example")

	host   = "0.0.0.0"
	port   = args.port
	config = uvicorn.Config(app, host=host, port=port)
	server = uvicorn.Server(config)

	await server.serve()


def main():
	parser = argparse.ArgumentParser(description="Numel Playground App")
	parser .add_argument("--port", type=int, default=DEFAULT_APP_PORT, help="Listening port for control server"     )
	parser .add_argument("--seed", type=int, default=DEFAULT_APP_SEED, help="Seed for pseudorandom number generator")
	args   = parser.parse_args()

	log_print("Server starting...")

	asyncio.run(run_server(args))

	log_print("Server shut down")


if __name__ == "__main__":
	main()
