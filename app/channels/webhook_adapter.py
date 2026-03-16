# channels.webhook_adapter — Generic Webhook channel adapter
#
# Receives messages via HTTP POST webhooks and sends responses back
# to a configured callback URL. Works with Slack, custom systems, etc.

import asyncio
import json

from   typing   import Any, Dict, Optional
from   utils    import log_print

from   channels.base import ChannelAdapter, ChannelConfig, ChannelMessage, ChannelStatus, MessageHandler


class WebhookChannelAdapter(ChannelAdapter):
	"""Generic webhook adapter — receive messages via POST, respond via callback URL.

	Config extras:
	  - callback_url:    URL to POST responses to (optional, if omitted responses are returned inline)
	  - secret:          Shared secret for request validation
	  - response_format: "text" or "json" (default: "json")
	"""

	def __init__(self, config: ChannelConfig, message_handler: Optional[MessageHandler] = None):
		super().__init__(config, message_handler)
		self._callback_url    = config.extras.get("callback_url")
		self._secret          = config.extras.get("secret", "")
		self._response_format = config.extras.get("response_format", "json")

	@property
	def type(self) -> str:
		return "webhook"

	async def start(self):
		"""Activate the webhook endpoint."""
		self.status = ChannelStatus.RUNNING
		log_print(f"Webhook channel active: {self.config.name} ({self.config.id})")

	async def stop(self):
		"""Deactivate the webhook endpoint."""
		self.status = ChannelStatus.STOPPED

	async def send(self, recipient_id: str, text: str, **kwargs) -> bool:
		"""Send a response to the callback URL."""
		callback = kwargs.get("callback_url", self._callback_url)
		if not callback:
			return False

		try:
			import httpx
			async with httpx.AsyncClient() as client:
				payload = {"text": text, "recipient": recipient_id}
				resp = await client.post(callback, json=payload, timeout=30)
				return resp.status_code == 200
		except ImportError:
			try:
				import aiohttp
				async with aiohttp.ClientSession() as session:
					payload = {"text": text, "recipient": recipient_id}
					async with session.post(callback, json=payload) as resp:
						return resp.status == 200
			except ImportError:
				log_print("Neither httpx nor aiohttp available for webhook callback")
				return False
		except Exception as e:
			self._error = str(e)
			return False

	async def process_webhook(self, body: Dict[str, Any], headers: Optional[Dict[str, str]] = None) -> Optional[str]:
		"""Process an incoming webhook payload.

		Expected body format (flexible):
		  { "text": "...", "sender_id": "...", "sender_name": "..." }
		  OR
		  { "message": "...", "user": "...", "username": "..." }
		  OR Slack format:
		  { "text": "...", "user": "...", "channel": "..." }
		"""
		# Validate secret
		if self._secret:
			req_secret = (headers or {}).get("x-webhook-secret", "")
			if req_secret != self._secret:
				return None

		# Normalize the message
		text = (body.get("text") or body.get("message") or body.get("content") or "").strip()
		if not text:
			return None

		sender_id   = str(body.get("sender_id") or body.get("user") or body.get("user_id") or "webhook")
		sender_name = str(body.get("sender_name") or body.get("username") or body.get("user_name") or "")

		msg = ChannelMessage(
			channel_type = "webhook",
			channel_id   = self.config.id,
			sender_id    = sender_id,
			sender_name  = sender_name,
			content      = text,
			metadata     = {k: v for k, v in body.items()
						   if k not in ("text", "message", "content", "sender_id", "user",
									   "sender_name", "username")},
		)

		response = await self.on_message(msg)

		# If callback URL, send async and return ack
		callback = body.get("response_url") or self._callback_url
		if callback and response:
			asyncio.create_task(self.send(sender_id, response, callback_url=callback))
			return json.dumps({"status": "processing"})

		# Otherwise return inline
		if self._response_format == "text":
			return response or ""
		return json.dumps({"response": response or ""})
