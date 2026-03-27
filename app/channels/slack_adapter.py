# channels.slack_adapter — Slack Bot channel adapter
#
# Uses the Slack Events API + Web API.
# Requires a Slack Bot token (xoxb-...) from a Slack App.
# Incoming messages arrive via webhook; outgoing via Web API.

import asyncio
import json

from   typing   import Any, Dict, Optional
from   utils    import log_print

from   channels.base import Attachment, ChannelAdapter, ChannelConfig, ChannelMessage, ChannelStatus, MessageHandler


_SLACK_API_BASE = "https://slack.com/api"


class SlackAdapter(ChannelAdapter):
	"""Slack Bot adapter — chat with the Numel assistant from Slack.

	Config:
	  - token:        Slack Bot token (xoxb-...)
	Config extras:
	  - signing_secret: Slack app signing secret (for webhook verification)
	  - allowed_channels: list of channel IDs to listen in (empty = all)
	  - app_token:    Slack App-level token (xapp-...) for Socket Mode (optional)
	"""

	def __init__(self, config: ChannelConfig, message_handler: Optional[MessageHandler] = None):
		super().__init__(config, message_handler)
		self._signing_secret    = config.extras.get("signing_secret", "")
		self._allowed_channels  = set(config.extras.get("allowed_channels", []))
		self._app_token         = config.extras.get("app_token")
		self._socket_client     = None
		self._socket_task       = None

	@property
	def type(self) -> str:
		return "slack"

	async def start(self):
		"""Start the Slack adapter.

		If app_token is provided, uses Socket Mode (no public webhook needed).
		Otherwise, uses webhook mode (Events API via /channels/webhook/{id}).
		"""
		if not self.config.token:
			raise ValueError("Slack bot token (xoxb-...) is required.")

		if self._app_token:
			await self._start_socket_mode()
		else:
			# Webhook mode — just mark as running; events come via /channels/webhook/{id}
			self.status = ChannelStatus.RUNNING
			log_print(f"Slack adapter started (webhook mode)")

	async def _start_socket_mode(self):
		"""Start in Socket Mode using slack_bolt."""
		try:
			from slack_bolt.async_app import AsyncApp
			from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler
		except ImportError:
			raise ImportError(
				"slack_bolt is required for Slack Socket Mode. "
				"Install with: pip install slack-bolt"
			)

		bolt_app = AsyncApp(token=self.config.token)
		adapter = self

		@bolt_app.event("message")
		async def handle_message(event, say):
			# Ignore bot messages
			if event.get("bot_id") or event.get("subtype"):
				return

			channel_id = event.get("channel", "")
			if adapter._allowed_channels and channel_id not in adapter._allowed_channels:
				return

			attachments = _extract_slack_files(event)

			msg = ChannelMessage(
				channel_type = "slack",
				channel_id   = adapter.config.id,
				sender_id    = event.get("user", ""),
				sender_name  = "",  # Resolved later if needed
				content      = event.get("text", ""),
				attachments  = attachments,
				metadata     = {
					"channel":   channel_id,
					"ts":        event.get("ts"),
					"thread_ts": event.get("thread_ts"),
				},
			)

			response = await adapter.on_message(msg)
			if response:
				thread_ts = event.get("thread_ts") or event.get("ts")
				await say(text=response, thread_ts=thread_ts)

		@bolt_app.event("app_mention")
		async def handle_mention(event, say):
			# Strip the bot mention from text
			text = event.get("text", "")
			# Remove <@BOT_ID> mentions
			import re
			text = re.sub(r"<@[A-Z0-9]+>", "", text).strip()
			if not text:
				return

			msg = ChannelMessage(
				channel_type = "slack",
				channel_id   = adapter.config.id,
				sender_id    = event.get("user", ""),
				content      = text,
				metadata     = {
					"channel":   event.get("channel", ""),
					"ts":        event.get("ts"),
					"thread_ts": event.get("thread_ts"),
				},
			)

			response = await adapter.on_message(msg)
			if response:
				thread_ts = event.get("thread_ts") or event.get("ts")
				await say(text=response, thread_ts=thread_ts)

		handler = AsyncSocketModeHandler(bolt_app, self._app_token)
		self._socket_client = handler
		self._socket_task = asyncio.create_task(handler.start_async())

		self.status = ChannelStatus.RUNNING
		log_print(f"Slack adapter started (Socket Mode)")

	async def stop(self):
		"""Stop the Slack adapter."""
		if self._socket_client:
			try:
				await self._socket_client.close_async()
			except Exception as e:
				log_print(f"Slack stop error: {e}")
			self._socket_client = None
		if self._socket_task:
			self._socket_task.cancel()
			self._socket_task = None
		self.status = ChannelStatus.STOPPED

	async def send(self, recipient_id: str, text: str, **kwargs) -> bool:
		"""Send a message to a Slack channel or user via Web API.

		kwargs:
		  thread_ts:   reply in thread
		  attachments: list of Attachment objects (or dicts with url, filename, mime_type)
		  media_url:   single file URL shorthand
		"""
		if not self.config.token:
			return False

		thread_ts   = kwargs.get("thread_ts")
		attachments = kwargs.get("attachments", [])
		media_url   = kwargs.get("media_url")
		if media_url and not attachments:
			attachments = [{"url": media_url, "filename": "file", "mime_type": ""}]

		try:
			import httpx
			headers = {"Authorization": f"Bearer {self.config.token}"}

			async with httpx.AsyncClient() as client:
				# Upload files if any
				for att in attachments:
					url  = att.url if hasattr(att, "url") else att.get("url", "")
					name = (att.filename if hasattr(att, "filename") else att.get("filename")) or "file"
					if not url:
						continue
					try:
						dl = await client.get(url, timeout=30)
						if dl.status_code != 200:
							continue
						# files.uploadV2
						resp = await client.post(
							f"{_SLACK_API_BASE}/files.uploadV2",
							headers=headers,
							data={
								"channel_id":      recipient_id,
								"filename":        name,
								"initial_comment": text or "",
								**({"thread_ts": thread_ts} if thread_ts else {}),
							},
							files={"file": (name, dl.content)},
							timeout=60,
						)
						if resp.json().get("ok"):
							text = ""  # comment sent with file
					except Exception:
						pass  # best-effort file upload

				# Send text message (if no files consumed the text)
				if text:
					payload = {"channel": recipient_id, "text": text}
					if thread_ts:
						payload["thread_ts"] = thread_ts

					resp = await client.post(
						f"{_SLACK_API_BASE}/chat.postMessage",
						headers=headers,
						json=payload,
						timeout=30,
					)
					data = resp.json()
					if not data.get("ok"):
						self._error = data.get("error", "unknown")
						return False

			return True
		except ImportError:
			self._error = "httpx not available"
			return False
		except Exception as e:
			self._error = str(e)
			return False

	# ── Webhook Processing (Events API) ───────────────────────────

	def verify_webhook(self, mode: str, token: str, challenge: str) -> Optional[str]:
		"""Not used for Slack (Slack uses url_verification event instead)."""
		return None

	async def process_webhook(self, body: Dict[str, Any], headers: Optional[Dict[str, str]] = None) -> Optional[str]:
		"""Process an incoming Slack Events API webhook payload.

		Handles:
		  - url_verification challenge
		  - event_callback with message events
		"""
		# URL verification challenge
		if body.get("type") == "url_verification":
			return json.dumps({"challenge": body.get("challenge", "")})

		# Verify signing secret if configured
		if self._signing_secret and headers:
			if not self._verify_request(body, headers):
				log_print("Slack webhook signature verification failed")
				return None

		# Event callback
		if body.get("type") != "event_callback":
			return json.dumps({"ok": True})

		event = body.get("event", {})
		event_type = event.get("type")

		# Skip bot messages and subtypes
		if event.get("bot_id") or event.get("subtype"):
			return json.dumps({"ok": True})

		if event_type not in ("message", "app_mention"):
			return json.dumps({"ok": True})

		channel_id = event.get("channel", "")
		if self._allowed_channels and channel_id not in self._allowed_channels:
			return json.dumps({"ok": True})

		text = event.get("text", "")
		# Strip bot mentions for app_mention events
		if event_type == "app_mention":
			import re
			text = re.sub(r"<@[A-Z0-9]+>", "", text).strip()

		attachments = _extract_slack_files(event)

		if not text and not attachments:
			return json.dumps({"ok": True})

		msg = ChannelMessage(
			channel_type = "slack",
			channel_id   = self.config.id,
			sender_id    = event.get("user", ""),
			content      = text,
			attachments  = attachments,
			metadata     = {
				"channel":   channel_id,
				"ts":        event.get("ts"),
				"thread_ts": event.get("thread_ts"),
			},
		)

		response = await self.on_message(msg)
		if response:
			thread_ts = event.get("thread_ts") or event.get("ts")
			await self.send(channel_id, response, thread_ts=thread_ts)

		return json.dumps({"ok": True})

	@staticmethod
	def _extract_files_from_event(event: Dict[str, Any]) -> list:
		"""Alias for module-level helper."""
		return _extract_slack_files(event)

	def _verify_request(self, body: Dict[str, Any], headers: Dict[str, str]) -> bool:
		"""Verify Slack request signature."""
		import hashlib
		import hmac
		import time

		timestamp = headers.get("x-slack-request-timestamp", "")
		signature = headers.get("x-slack-signature", "")

		if not timestamp or not signature:
			return False

		# Reject requests older than 5 minutes
		try:
			if abs(time.time() - int(timestamp)) > 300:
				return False
		except ValueError:
			return False

		sig_basestring = f"v0:{timestamp}:{json.dumps(body, separators=(',', ':'))}"
		my_signature = "v0=" + hmac.new(
			self._signing_secret.encode(),
			sig_basestring.encode(),
			hashlib.sha256,
		).hexdigest()

		return hmac.compare_digest(my_signature, signature)


def _extract_slack_files(event: Dict[str, Any]) -> list:
	"""Extract Attachment objects from Slack event files."""
	files = event.get("files", [])
	attachments = []
	for f in files:
		url = f.get("url_private_download") or f.get("url_private") or f.get("permalink", "")
		attachments.append(Attachment(
			url       = url,
			mime_type = f.get("mimetype", "application/octet-stream"),
			filename  = f.get("name") or f.get("title"),
			size      = f.get("size"),
		))
	return attachments
