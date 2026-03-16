# channels.whatsapp_adapter — WhatsApp channel adapter
#
# Uses the WhatsApp Business API (Cloud API) via Meta's Graph API.
# Requires a WhatsApp Business account, phone number ID, and access token.
# Incoming messages arrive via webhook; outgoing via REST API.

import asyncio
import hashlib
import hmac
import json

from   typing   import Any, Dict, Optional
from   utils    import log_print

from   channels.base import ChannelAdapter, ChannelConfig, ChannelMessage, ChannelStatus, MessageHandler


_GRAPH_API_BASE = "https://graph.facebook.com/v21.0"


class WhatsAppAdapter(ChannelAdapter):
	"""WhatsApp Business adapter — chat with Numel from WhatsApp.

	Config extras:
	  - phone_number_id: WhatsApp Business phone number ID
	  - verify_token:    Webhook verification token (for Meta webhook setup)
	  - app_secret:      App secret for webhook signature verification
	"""

	def __init__(self, config: ChannelConfig, message_handler: Optional[MessageHandler] = None):
		super().__init__(config, message_handler)
		self._phone_number_id = config.extras.get("phone_number_id", "")
		self._verify_token    = config.extras.get("verify_token", "numel_verify")
		self._app_secret      = config.extras.get("app_secret", "")

	@property
	def type(self) -> str:
		return "whatsapp"

	async def start(self):
		"""Start the WhatsApp adapter.
		Note: WhatsApp uses webhooks, so there's no polling loop.
		The adapter registers itself and waits for incoming webhook calls
		from the channel API routes."""
		if not self.config.token:
			raise ValueError("WhatsApp access token is required (Meta Graph API token)")
		if not self._phone_number_id:
			raise ValueError("phone_number_id is required in extras")

		self.status = ChannelStatus.RUNNING
		log_print(f"WhatsApp adapter started (webhook mode, phone: {self._phone_number_id})")

	async def stop(self):
		"""Stop the WhatsApp adapter."""
		self.status = ChannelStatus.STOPPED

	async def send(self, recipient_id: str, text: str, **kwargs) -> bool:
		"""Send a text message via the WhatsApp Cloud API."""
		if not self.config.token or not self._phone_number_id:
			return False

		try:
			import httpx
		except ImportError:
			try:
				import aiohttp
				return await self._send_aiohttp(recipient_id, text)
			except ImportError:
				log_print("Neither httpx nor aiohttp available for WhatsApp sending")
				return False

		url = f"{_GRAPH_API_BASE}/{self._phone_number_id}/messages"
		headers = {
			"Authorization": f"Bearer {self.config.token}",
			"Content-Type":  "application/json",
		}
		payload = {
			"messaging_product": "whatsapp",
			"to":                recipient_id,
			"type":              "text",
			"text":              {"body": text[:4096]},
		}

		try:
			async with httpx.AsyncClient() as client:
				resp = await client.post(url, headers=headers, json=payload, timeout=30)
				if resp.status_code == 200:
					return True
				else:
					self._error = f"WhatsApp API {resp.status_code}: {resp.text}"
					log_print(self._error)
					return False
		except Exception as e:
			self._error = str(e)
			return False

	async def _send_aiohttp(self, recipient_id: str, text: str) -> bool:
		"""Fallback sender using aiohttp."""
		import aiohttp
		url = f"{_GRAPH_API_BASE}/{self._phone_number_id}/messages"
		headers = {
			"Authorization": f"Bearer {self.config.token}",
			"Content-Type":  "application/json",
		}
		payload = {
			"messaging_product": "whatsapp",
			"to":                recipient_id,
			"type":              "text",
			"text":              {"body": text[:4096]},
		}
		try:
			async with aiohttp.ClientSession() as session:
				async with session.post(url, headers=headers, json=payload) as resp:
					return resp.status == 200
		except Exception as e:
			self._error = str(e)
			return False

	# ── Webhook Processing ────────────────────────────────────────

	def verify_webhook(self, mode: str, token: str, challenge: str) -> Optional[str]:
		"""Handle Meta webhook verification (GET request).
		Returns the challenge string if valid, None otherwise."""
		if mode == "subscribe" and token == self._verify_token:
			return challenge
		return None

	async def process_webhook(self, body: Dict[str, Any], signature: Optional[str] = None) -> Optional[str]:
		"""Process an incoming webhook payload from Meta.
		Returns the response to send, or None."""

		# Verify signature if app_secret is configured
		if self._app_secret and signature:
			if not self._verify_signature(body, signature):
				log_print("WhatsApp webhook signature verification failed")
				return None

		# Extract messages from the webhook payload
		try:
			entry = body.get("entry", [{}])[0]
			changes = entry.get("changes", [{}])[0]
			value = changes.get("value", {})
			messages = value.get("messages", [])
			contacts = value.get("contacts", [])
		except (IndexError, KeyError):
			return None

		if not messages:
			return None

		for wa_msg in messages:
			if wa_msg.get("type") != "text":
				continue

			sender_id = wa_msg.get("from", "")
			sender_name = ""
			for c in contacts:
				if c.get("wa_id") == sender_id:
					sender_name = c.get("profile", {}).get("name", "")
					break

			msg = ChannelMessage(
				channel_type = "whatsapp",
				channel_id   = self.config.id,
				sender_id    = sender_id,
				sender_name  = sender_name,
				content      = wa_msg.get("text", {}).get("body", ""),
				metadata     = {
					"wa_message_id": wa_msg.get("id"),
					"timestamp":     wa_msg.get("timestamp"),
				},
			)

			response = await self.on_message(msg)
			if response:
				await self.send(sender_id, response)

		return "ok"

	def _verify_signature(self, body: Dict[str, Any], signature: str) -> bool:
		"""Verify webhook payload signature."""
		if not self._app_secret:
			return True
		try:
			body_bytes = json.dumps(body).encode()
			expected = hmac.new(
				self._app_secret.encode(),
				body_bytes,
				hashlib.sha256,
			).hexdigest()
			return hmac.compare_digest(f"sha256={expected}", signature)
		except Exception:
			return False
