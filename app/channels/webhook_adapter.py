# channels.webhook_adapter — Generic Webhook channel adapter
#
# Receives messages via HTTP POST webhooks and sends responses back
# to a configured callback URL. Works with Slack, custom systems, etc.

import asyncio
import json

from   typing   import Any, Dict, Optional
from   utils    import log_print

from   channels.base import Attachment, ChannelAdapter, ChannelConfig, ChannelMessage, ChannelStatus, MessageHandler


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
		"""Send a response to the callback URL.

		kwargs:
		  callback_url: override callback URL
		  attachments:  list of Attachment objects (or dicts with url, mime_type, filename)
		  media_url:    single media URL shorthand
		"""
		callback    = kwargs.get("callback_url", self._callback_url)
		att_list    = kwargs.get("attachments", [])
		media_url   = kwargs.get("media_url")
		if media_url and not att_list:
			att_list = [{"url": media_url}]

		if not callback:
			return False

		try:
			import httpx
			async with httpx.AsyncClient() as client:
				payload: dict = {"text": text, "recipient": recipient_id}
				if att_list:
					payload["attachments"] = [
						{
							"url":       a.url if hasattr(a, "url") else a.get("url", ""),
							"mime_type": a.mime_type if hasattr(a, "mime_type") else a.get("mime_type", ""),
							"filename":  (a.filename if hasattr(a, "filename") else a.get("filename")) or None,
						}
						for a in att_list
					]
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

		sender_id   = str(body.get("sender_id") or body.get("user") or body.get("user_id") or "webhook")
		sender_name = str(body.get("sender_name") or body.get("username") or body.get("user_name") or "")

		# Extract attachments from payload
		attachments = []
		for att in body.get("attachments", body.get("files", [])):
			if isinstance(att, dict):
				attachments.append(Attachment(
					url       = att.get("url", ""),
					mime_type = att.get("mime_type") or att.get("content_type", ""),
					filename  = att.get("filename") or att.get("name"),
					size      = att.get("size"),
				))
		# Legacy single-media fields
		media_url = body.get("media_url", "")
		if media_url:
			attachments.append(Attachment(
				url       = media_url,
				mime_type = body.get("media_type", ""),
			))

		if not text and not attachments:
			return None

		_skip_keys = {"text", "message", "content", "sender_id", "user", "user_id",
					  "sender_name", "username", "user_name", "attachments", "files",
					  "media_url", "media_type"}

		msg = ChannelMessage(
			channel_type = "webhook",
			channel_id   = self.config.id,
			sender_id    = sender_id,
			sender_name  = sender_name,
			content      = text,
			attachments  = attachments,
			metadata     = {k: v for k, v in body.items() if k not in _skip_keys},
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
