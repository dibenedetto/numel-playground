# app

import warnings

# Suppress harmless UnsupportedFieldAttributeWarning spam emitted by agno's
# internal Pydantic models (alias/validation_alias on union members).
# These originate in pydantic._internal._generate_schema — not our code.
warnings.filterwarnings(
	"ignore",
	message = r".*attribute.*has no effect in the context it was used.*",
	module  = r"pydantic.*",
)


import argparse
import asyncio
import os
import sys
import uvicorn
import webbrowser
from   fastapi.staticfiles  import StaticFiles


# Add project root and app/ dir to sys.path so both internal packages
# (tools, toolkits.*) and contrib packages (contrib.toolkits.*) are importable
# regardless of which directory the process is started from.
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_app_dir      = os.path.dirname(os.path.abspath(__file__))
if _project_root not in sys.path:
	sys.path.insert(0, _project_root)
if _app_dir not in sys.path:
	sys.path.insert(1, _app_dir)


from   dotenv    import load_dotenv
from   fastapi   import FastAPI
from   inspect   import getsource
from   typing    import Any


import schema


from   agent_tasks import AgentTaskManager, setup_agent_tasks_api
from   api       import setup_api
from   channels  import ChannelRegistry
from   channels.api            import setup_channel_api
from   channels.telegram_adapter  import TelegramAdapter
from   channels.whatsapp_adapter  import WhatsAppAdapter
from   channels.discord_adapter   import DiscordAdapter
from   channels.signal_adapter    import SignalAdapter
from   channels.slack_adapter     import SlackAdapter
from   channels.teams_adapter     import TeamsAdapter
from   channels.webhook_adapter   import WebhookChannelAdapter
from   console   import ConsoleAgentManager, setup_console_api
from   event_bus import EventBus, get_event_bus
from   gallery   import GalleryManager, setup_gallery_api
from   memory    import MemoryStore
from   published_apps import PublishedAppManager, setup_published_apps_api
from   utils     import add_middleware, log_print, seed_everything
from   workspace import WorkspaceManager as WSManager


load_dotenv()


DEFAULT_APP_SEED : int = 7
DEFAULT_APP_PORT : int = 11360


def _asyncio_exception_handler(loop, context):
	# Suppress harmless ConnectionResetError noise from Windows asyncio Proactor
	# transport when the browser closes a fetch connection before the server finishes.
	# (WinError 10054 — WSAECONNRESET — in _ProactorBasePipeTransport._call_connection_lost)
	if isinstance(context.get('exception'), ConnectionResetError):
		return
	loop.default_exception_handler(context)


async def run_server(args: Any):
	log_print("Server starting...")

	asyncio.get_event_loop().set_exception_handler(_asyncio_exception_handler)

	if args.seed != 0:
		seed_everything(args.seed)

	event_bus     : EventBus  = get_event_bus()
	workspace_mgr : WSManager = WSManager(
		base_port    = args.port,
		event_bus    = event_bus,
		storage_root = os.path.join(_app_dir, "workspaces"),
	)
	await workspace_mgr.initialize()

	schema_code = getsource(schema)

	app: FastAPI = FastAPI(title="App")
	add_middleware(app)

	# Serve the frontend from /web — must be mounted AFTER api routes are registered
	_web_dir = os.path.join(_project_root, "web")

	host   = "0.0.0.0"
	port   = args.port
	config = uvicorn.Config(app, host=host, port=port)
	server = uvicorn.Server(config)

	# ── Persistent Memory ─────────────────────────────────────
	memory_store = MemoryStore()
	memory_store.initialize()

	# ── Console Agent ─────────────────────────────────────────
	console_mgr = ConsoleAgentManager(workspace_mgr, event_bus, port=args.port + 1,
									  memory_store=memory_store)
	console_mgr.setup_proactive_listeners()

	# ── Channel Adapters ──────────────────────────────────────
	async def channel_message_handler(msg):
		"""Route incoming channel messages to the console agent."""
		try:
			result = await console_mgr.chat(
				message    = msg.content,
				session_id = msg.metadata.get("session_id") or f"ch_{msg.channel_type}_{msg.sender_id}",
			)
			return result.get("response", "")
		except Exception as e:
			return f"Error: {e}"

	channel_registry = ChannelRegistry(message_handler=channel_message_handler,
									   config_path=os.path.join(_app_dir, "channels.json"))
	# Register adapter types
	ChannelRegistry.register_type("telegram", TelegramAdapter)
	ChannelRegistry.register_type("whatsapp", WhatsAppAdapter)
	ChannelRegistry.register_type("discord",  DiscordAdapter)
	ChannelRegistry.register_type("slack",    SlackAdapter)
	ChannelRegistry.register_type("signal",   SignalAdapter)
	ChannelRegistry.register_type("teams",    TeamsAdapter)
	ChannelRegistry.register_type("webhook",  WebhookChannelAdapter)
	channel_registry.load()

	# ── Workflow Gallery ──────────────────────────────────────
	gallery_mgr = GalleryManager()
	gallery_mgr.initialize()

	# ── Autonomous Agent Tasks ────────────────────────────────
	task_mgr = AgentTaskManager(console_mgr)
	task_mgr.initialize(event_bus)

	# ── Published Apps ────────────────────────────────────────
	pub_app_mgr = PublishedAppManager(workspace_mgr)
	pub_app_mgr.initialize()

	# ── API Routes (order matters: specific routes before static mount) ──
	setup_api(server, app, event_bus, schema_code, workspace_mgr)
	setup_console_api(app, console_mgr)
	setup_channel_api(app, channel_registry)
	setup_gallery_api(app, gallery_mgr)
	setup_agent_tasks_api(app, task_mgr)
	setup_published_apps_api(app, pub_app_mgr)

	# Serve index.html at / and all static assets (JS, CSS, dist/*)
	app.mount("/", StaticFiles(directory=_web_dir, html=True), name="static")

	url = f"http://localhost:{port}/"
	log_print(f"Frontend: {url}")
	webbrowser.open(url)

	# Start auto-start channels
	await channel_registry.start_all()

	await server.serve()

	# Shutdown
	await task_mgr.stop_all()
	await channel_registry.stop_all()
	await console_mgr.stop()
	await workspace_mgr.shutdown()

	log_print("Server shut down.")


def main():
	parser = argparse.ArgumentParser(description="Numel Playground App")
	parser .add_argument("--port", type=int, default=DEFAULT_APP_PORT, help="Listening port for control server"     )
	parser .add_argument("--seed", type=int, default=DEFAULT_APP_SEED, help="Seed for pseudorandom number generator")
	args   = parser.parse_args()

	asyncio.run(run_server(args))


if __name__ == "__main__":
	main()
