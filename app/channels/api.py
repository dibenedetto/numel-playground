# channels.api — Channel management API routes
#
# Provides REST endpoints for managing channel adapters:
# list, add, remove, start, stop, send, and webhook ingress.

from   fastapi   import FastAPI, Request, Response
from   pydantic  import BaseModel
from   typing    import Any, Dict, List, Optional

from   channels.base     import ChannelConfig
from   channels.registry import ChannelRegistry


# ── Request Models ────────────────────────────────────────────────

class ChannelAddRequest(BaseModel):
	name         : str
	channel_type : str                          # "telegram", "whatsapp", "discord", "webhook"
	token        : Optional[str]       = None
	webhook_url  : Optional[str]       = None
	auto_start   : bool                = False
	allowed_users: List[str]           = []
	session_id   : Optional[str]       = None   # Shared session for memory continuity
	extras       : Dict[str, Any]      = {}

class ChannelSendRequest(BaseModel):
	channel_id   : str
	recipient_id : str
	text         : str


# ── Route Setup ───────────────────────────────────────────────────

def setup_channel_api(app: FastAPI, registry: ChannelRegistry):
	"""Register all channel-related API routes."""

	@app.post("/channels/types")
	async def channel_types():
		"""List available channel adapter types."""
		return registry.get_available_types()

	@app.post("/channels/list")
	async def channel_list():
		"""List all configured channels with status."""
		return registry.list()

	@app.post("/channels/add")
	async def channel_add(request: ChannelAddRequest):
		"""Add a new channel adapter."""
		config = ChannelConfig(
			name          = request.name,
			channel_type  = request.channel_type,
			token         = request.token,
			webhook_url   = request.webhook_url,
			auto_start    = request.auto_start,
			allowed_users = request.allowed_users,
			session_id    = request.session_id,
			extras        = request.extras,
		)
		adapter = await registry.add(config)
		return adapter.get_status()

	@app.post("/channels/remove")
	async def channel_remove(request: dict):
		"""Remove a channel adapter."""
		channel_id = request.get("channel_id", "")
		ok = await registry.remove(channel_id)
		return {"removed": ok}

	@app.post("/channels/start")
	async def channel_start(request: dict):
		"""Start a channel adapter."""
		channel_id = request.get("channel_id", "")
		ok = await registry.start(channel_id)
		adapter = registry.get(channel_id)
		return adapter.get_status() if adapter else {"error": "not found"}

	@app.post("/channels/stop")
	async def channel_stop(request: dict):
		"""Stop a channel adapter."""
		channel_id = request.get("channel_id", "")
		ok = await registry.stop(channel_id)
		adapter = registry.get(channel_id)
		return adapter.get_status() if adapter else {"error": "not found"}

	@app.post("/channels/send")
	async def channel_send(request: ChannelSendRequest):
		"""Send a message through a channel."""
		adapter = registry.get(request.channel_id)
		if not adapter:
			return {"error": "channel not found"}
		ok = await adapter.send(request.recipient_id, request.text)
		return {"sent": ok}

	@app.post("/channels/status")
	async def channel_status(request: dict):
		"""Get status of a specific channel."""
		channel_id = request.get("channel_id", "")
		adapter = registry.get(channel_id)
		if not adapter:
			return {"error": "not found"}
		return adapter.get_status()

	# ── Webhook Ingress ───────────────────────────────────────────

	@app.api_route("/channels/webhook/{channel_id}", methods=["GET", "POST"])
	async def channel_webhook(channel_id: str, request: Request):
		"""Incoming webhook endpoint for channel adapters.

		GET:  Used for webhook verification (WhatsApp, Slack challenge).
		POST: Incoming messages from external platforms.
		"""
		adapter = registry.get(channel_id)
		if not adapter:
			return Response(status_code=404, content="Channel not found")

		if request.method == "GET":
			# Webhook verification (WhatsApp)
			params = dict(request.query_params)
			if hasattr(adapter, "verify_webhook"):
				mode      = params.get("hub.mode", "")
				token     = params.get("hub.verify_token", "")
				challenge = params.get("hub.challenge", "")
				result = adapter.verify_webhook(mode, token, challenge)
				if result:
					return Response(content=result, media_type="text/plain")
				return Response(status_code=403, content="Verification failed")
			return Response(status_code=405, content="GET not supported for this channel")

		# POST: incoming message
		try:
			body = await request.json()
		except Exception:
			return Response(status_code=400, content="Invalid JSON")

		headers = dict(request.headers)

		if hasattr(adapter, "process_webhook"):
			result = await adapter.process_webhook(body, headers)
			if result:
				return Response(content=result, media_type="application/json")
			return Response(status_code=200, content="ok")

		return Response(status_code=405, content="Webhook not supported for this channel type")
