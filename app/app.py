# app

import argparse
import asyncio
import uvicorn


from   dotenv                  import load_dotenv
from   fastapi                 import FastAPI
from   fastapi.middleware.cors import CORSMiddleware
from   inspect                 import getsource
from   typing                  import Any, List


import schema


from   api                     import setup_api
from   engine                  import WorkflowEngine
from   event_bus               import EventBus, get_event_bus
from   manager                 import WorkflowManager
from   schema                  import BaseType
from   utils                   import log_print, seed_everything


load_dotenv()


DEFAULT_APP_SEED : int = 777
DEFAULT_APP_PORT : int = 8000


async def handle_knowledge_upload(node: BaseType, files: List[Any], button_id: str) -> Any:
	# Dummy handler for knowledge manager uploads
	await asyncio.sleep(2)  # Simulate processing time
	return {
		"message": f"Received {len(files)} files from {node.type} by {button_id}.",
	}


async def run_server(args: Any):
	log_print("Server starting...")

	if args.seed != 0:
		seed_everything(args.seed)

	event_bus   : EventBus        = get_event_bus   ()
	manager     : WorkflowManager = WorkflowManager (args.port, event_bus)
	engine      : WorkflowEngine  = WorkflowEngine  (event_bus)
	schema_code : str             = getsource       (schema)

	await manager.register_upload_handler(
		"knowledge_manager_config",
		handle_knowledge_upload,
	)

	app : FastAPI = FastAPI(title="App")
	app.add_middleware(
		CORSMiddleware,
		allow_credentials = False,
		allow_headers     = ["*"],
		allow_methods     = ["*"],
		allow_origins     = ["*"],
	)

	host   = "0.0.0.0"
	port   = args.port
	config = uvicorn.Config(app, host=host, port=port)
	server = uvicorn.Server(config)

	setup_api(server, app, event_bus, schema_code, manager, engine)

	await server  .serve  ()
	await manager .remove ()

	log_print("Server shut down.")


def main():
	parser = argparse.ArgumentParser(description="Numel Playground App")
	parser .add_argument("--port", type=int, default=DEFAULT_APP_PORT, help="Listening port for control server"     )
	parser .add_argument("--seed", type=int, default=DEFAULT_APP_SEED, help="Seed for pseudorandom number generator")
	args   = parser.parse_args()

	asyncio.run(run_server(args))


if __name__ == "__main__":
	main()
