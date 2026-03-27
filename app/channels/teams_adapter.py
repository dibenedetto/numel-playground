# channels.teams_adapter — Microsoft Teams channel adapter
#
# Uses the Microsoft Bot Framework REST API.
# Requires an Azure Bot registration with app ID and password.
# Incoming messages arrive via webhook; outgoing via Bot Connector API.

import asyncio
import json
import time

from   typing   import Any, Dict, Optional
from   utils    import log_print

from   channels.base import Attachment, ChannelAdapter, ChannelConfig, ChannelMessage, ChannelStatus, MessageHandler


_BOT_FRAMEWORK_API = "https://smba.trafficmanager.net"
_LOGIN_URL         = "https://login.microsoftonline.com/botframework.com/oauth2/v2.0/token"


class TeamsAdapter(ChannelAdapter):
	"""Microsoft Teams adapter — chat with the Numel assistant from Teams.

	Requires an Azure Bot registration:
	  1. Register a bot at https://dev.botframework.com
	  2. Note the App ID and App Password

	Config:
	  - token: App Password (client secret)
	Config extras:
	  - app_id:   Microsoft App ID (from Azure Bot registration)
	"""

	def __init__(self, config: ChannelConfig, message_handler: Optional[MessageHandler] = None):
		super().__init__(config, message_handler)
		self._app_id        = config.extras.get("app_id", "")
		self._app_password  = config.token or ""
		self._access_token  = None
		self._token_expires = 0

	@property
	def type(self) -> str:
		return "teams"

	async def start(self):
		"""Start the Teams adapter (webhook mode).
		Teams sends activities to /channels/webhook/{id} via Bot Framework."""
		if not self._app_id:
			raise ValueError("Microsoft App ID is required in extras (app_id)")
		if not self._app_password:
			raise ValueError("App Password (token) is required")

		# Get initial access token
		await self._refresh_token()

		self.status = ChannelStatus.RUNNING
		log_print(f"Teams adapter started (webhook mode, app_id: {self._app_id})")

	async def stop(self):
		"""Stop the Teams adapter."""
		self._access_token = None
		self.status = ChannelStatus.STOPPED

	async def send(self, recipient_id: str, text: str, **kwargs) -> bool:
		"""Send a reply to a Teams conversation.

		kwargs:
		  service_url:     Bot Framework service URL
		  conversation_id: conversation to reply in
		  attachments:     list of Attachment objects (or dicts with url, mime_type, filename)
		  media_url:       single media URL shorthand
		"""
		service_url     = kwargs.get("service_url", _BOT_FRAMEWORK_API)
		conversation_id = kwargs.get("conversation_id", recipient_id)
		att_list        = kwargs.get("attachments", [])
		media_url       = kwargs.get("media_url")

		if media_url and not att_list:
			att_list = [{"url": media_url, "mime_type": "", "filename": "file"}]

		if not await self._ensure_token():
			return False

		try:
			import httpx
			async with httpx.AsyncClient() as client:
				url = f"{service_url}/v3/conversations/{conversation_id}/activities"
				payload: dict = {
					"type": "message",
					"text": text,
				}

				# Add Bot Framework attachments
				if att_list:
					bf_attachments = []
					for att in att_list:
						att_url  = att.url if hasattr(att, "url") else att.get("url", "")
						att_mime = att.mime_type if hasattr(att, "mime_type") else att.get("mime_type", "")
						att_name = (att.filename if hasattr(att, "filename") else att.get("filename")) or "file"
						if att_url:
							bf_attachments.append({
								"contentType": att_mime or "application/octet-stream",
								"contentUrl":  att_url,
								"name":        att_name,
							})
					if bf_attachments:
						payload["attachments"] = bf_attachments

				resp = await client.post(
					url,
					headers={
						"Authorization": f"Bearer {self._access_token}",
						"Content-Type":  "application/json",
					},
					json=payload,
					timeout=30,
				)
				if resp.status_code in (200, 201):
					return True
				self._error = f"Teams API {resp.status_code}: {resp.text[:200]}"
				return False
		except ImportError:
			self._error = "httpx not available"
			return False
		except Exception as e:
			self._error = str(e)
			return False

	# ── Webhook Processing ────────────────────────────────────────

	async def process_webhook(self, body: Dict[str, Any], headers: Optional[Dict[str, str]] = None) -> Optional[str]:
		"""Process an incoming Bot Framework activity.

		Activities include:
		  - message: user sent a text message
		  - conversationUpdate: user joined/left
		  - other activity types (ignored)
		"""
		activity_type = body.get("type")

		if activity_type != "message":
			return json.dumps({"status": "ok"})

		text = body.get("text", "").strip()

		# Strip bot mention if present
		if body.get("entities"):
			for entity in body["entities"]:
				if entity.get("type") == "mention":
					mentioned = entity.get("text", "")
					text = text.replace(mentioned, "").strip()

		# Extract attachments from Bot Framework activity
		attachments = []
		for att in body.get("attachments", []):
			content_url = att.get("contentUrl", "")
			if content_url:
				attachments.append(Attachment(
					url       = content_url,
					mime_type = att.get("contentType", "application/octet-stream"),
					filename  = att.get("name"),
				))

		if not text and not attachments:
			return json.dumps({"status": "ok"})

		sender      = body.get("from", {})
		sender_id   = sender.get("id", "")
		sender_name = sender.get("name", "")
		conversation = body.get("conversation", {})
		service_url  = body.get("serviceUrl", _BOT_FRAMEWORK_API)

		msg = ChannelMessage(
			channel_type = "teams",
			channel_id   = self.config.id,
			sender_id    = sender_id,
			sender_name  = sender_name,
			content      = text,
			attachments  = attachments,
			metadata     = {
				"conversation_id": conversation.get("id"),
				"service_url":     service_url,
				"activity_id":     body.get("id"),
				"tenant_id":       conversation.get("tenantId"),
			},
		)

		response = await self.on_message(msg)
		if response:
			await self.send(
				recipient_id    = sender_id,
				text            = response,
				service_url     = service_url,
				conversation_id = conversation.get("id"),
			)

		return json.dumps({"status": "ok"})

	# ── Token Management ──────────────────────────────────────────

	async def _ensure_token(self) -> bool:
		"""Ensure we have a valid access token."""
		if self._access_token and time.time() < self._token_expires - 60:
			return True
		return await self._refresh_token()

	async def _refresh_token(self) -> bool:
		"""Get a new access token from Azure AD."""
		try:
			import httpx
			async with httpx.AsyncClient() as client:
				resp = await client.post(
					_LOGIN_URL,
					data={
						"grant_type":    "client_credentials",
						"client_id":     self._app_id,
						"client_secret": self._app_password,
						"scope":         "https://api.botframework.com/.default",
					},
					timeout=30,
				)
				if resp.status_code == 200:
					data = resp.json()
					self._access_token  = data["access_token"]
					self._token_expires = time.time() + data.get("expires_in", 3600)
					return True
				else:
					self._error = f"Token refresh failed: {resp.status_code}"
					return False
		except Exception as e:
			self._error = f"Token refresh error: {e}"
			return False
