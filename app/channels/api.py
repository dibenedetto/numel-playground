# channels.api — Channel management API routes
#
# Provides REST endpoints for managing channel adapters:
# list, add, remove, start, stop, send, and webhook ingress.

from   fastapi   import FastAPI, HTTPException, Request, Response
from   pydantic  import BaseModel
from   typing    import Any, Dict, List, Optional

from   channels.base     import ChannelConfig
from   channels.registry import ChannelRegistry
from   providers.models  import Role


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

def setup_channel_api(app: FastAPI, registry: ChannelRegistry, pool=None):
	"""Register all channel-related API routes."""

	def _get_user(request: Request):
		"""Return (user_id, is_admin) from auth state."""
		user = getattr(request.state, "user", None)
		if not user:
			return None, False
		return user.id, user.role == Role.ADMIN

	def _require_owner(request: Request, adapter):
		"""Raise 403 if the caller is not the channel creator or an admin."""
		user_id, is_admin = _get_user(request)
		if is_admin:
			return
		owner = adapter.config.created_by
		if owner and user_id != owner:
			raise HTTPException(403, "Only the channel creator or an admin can perform this action")

	@app.post("/channels/types")
	async def channel_types():
		"""List available channel adapter types."""
		return registry.get_available_types()

	@app.post("/channels/list")
	async def channel_list():
		"""List all configured channels with status."""
		return registry.list()

	@app.post("/channels/add")
	async def channel_add(req: Request, request: ChannelAddRequest):
		"""Add a new channel adapter. Requires an authenticated (non-guest) user."""
		user_id, _ = _get_user(req)
		if not user_id:
			raise HTTPException(401, "Authentication required to create channels")
		config = ChannelConfig(
			name          = request.name,
			channel_type  = request.channel_type,
			token         = request.token,
			webhook_url   = request.webhook_url,
			auto_start    = request.auto_start,
			allowed_users = request.allowed_users,
			session_id    = request.session_id,
			extras        = request.extras,
			created_by    = user_id,
		)
		adapter = await registry.add(config)
		return adapter.get_status()

	@app.post("/channels/remove")
	async def channel_remove(req: Request):
		"""Remove a channel adapter."""
		body = await req.json()
		channel_id = body.get("channel_id", "")
		adapter = registry.get(channel_id)
		if not adapter:
			return {"removed": False}
		_require_owner(req, adapter)
		ok = await registry.remove(channel_id)
		return {"removed": ok}

	@app.post("/channels/start")
	async def channel_start(req: Request):
		"""Start a channel adapter."""
		body = await req.json()
		channel_id = body.get("channel_id", "")
		adapter = registry.get(channel_id)
		if not adapter:
			return {"error": "not found"}
		_require_owner(req, adapter)
		ok = await registry.start(channel_id)
		return adapter.get_status()

	@app.post("/channels/stop")
	async def channel_stop(req: Request):
		"""Stop a channel adapter."""
		body = await req.json()
		channel_id = body.get("channel_id", "")
		adapter = registry.get(channel_id)
		if not adapter:
			return {"error": "not found"}
		_require_owner(req, adapter)
		ok = await registry.stop(channel_id)
		return adapter.get_status()

	@app.post("/channels/send")
	async def channel_send(request: ChannelSendRequest):
		"""Send a message through a channel."""
		adapter = registry.get(request.channel_id)
		if not adapter:
			return {"error": "channel not found"}
		ok = await adapter.send(request.recipient_id, request.text)
		return {"sent": ok}

	@app.post("/channels/status")
	async def channel_status(req: Request):
		"""Get status of a specific channel."""
		body = await req.json()
		channel_id = body.get("channel_id", "")
		adapter = registry.get(channel_id)
		if not adapter:
			return {"error": "not found"}
		return adapter.get_status()

	# ── Agent Pool Config ─────────────────────────────────────────

	@app.post("/channels/pool/config")
	async def channel_pool_config(request: dict):
		"""Get or update channel agent pool settings."""
		if pool is None:
			return {"error": "agent pool not available"}
		if "idle_timeout" in request:
			pool._idle_timeout = max(60, float(request["idle_timeout"]))
		return {
			"idle_timeout": pool._idle_timeout,
			"pool_size":    pool.pool_size,
		}

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
