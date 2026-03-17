# channels.signal_adapter — Signal Messenger channel adapter
#
# Uses signal-cli REST API (https://github.com/bbernhard/signal-cli-rest-api)
# as a bridge to the Signal network. Requires a separate signal-cli-rest-api
# container running alongside.

import asyncio
import json

from   typing   import Any, Dict, List, Optional
from   utils    import log_print

from   channels.base import ChannelAdapter, ChannelConfig, ChannelMessage, ChannelStatus, MessageHandler


_DEFAULT_SIGNAL_API = "http://localhost:8080"


class SignalAdapter(ChannelAdapter):
	"""Signal Messenger adapter — chat with the Numel assistant via Signal.

	Requires signal-cli-rest-api running separately:
	  docker run -p 8080:8080 bbernhard/signal-cli-rest-api

	Config:
	  - token: Not used (signal-cli uses phone number registration)
	Config extras:
	  - api_url:      signal-cli REST API base URL (default: http://localhost:8080)
	  - phone_number: Registered Signal phone number (e.g. +1234567890)
	  - poll_interval: Seconds between message polls (default: 2)
	"""

	def __init__(self, config: ChannelConfig, message_handler: Optional[MessageHandler] = None):
		super().__init__(config, message_handler)
		self._api_url       = config.extras.get("api_url", config.api_endpoint or _DEFAULT_SIGNAL_API)
		self._phone_number  = config.extras.get("phone_number", "")
		self._poll_interval = config.extras.get("poll_interval", 2)
		self._poll_task     = None
		self._running       = False

	@property
	def type(self) -> str:
		return "signal"

	async def start(self):
		"""Start polling the signal-cli REST API for incoming messages."""
		if not self._phone_number:
			raise ValueError("Signal phone_number is required in extras (e.g. '+1234567890')")

		# Verify API is reachable
		try:
			import httpx
			async with httpx.AsyncClient() as client:
				resp = await client.get(f"{self._api_url}/v1/about", timeout=5)
				if resp.status_code != 200:
					raise ConnectionError(f"signal-cli API returned {resp.status_code}")
		except ImportError:
			raise ImportError("httpx is required for Signal integration.")
		except Exception as e:
			raise ConnectionError(
				f"Cannot reach signal-cli REST API at {self._api_url}: {e}\n"
				"Make sure signal-cli-rest-api is running:\n"
				"  docker run -p 8080:8080 bbernhard/signal-cli-rest-api"
			)

		self._running = True
		self._poll_task = asyncio.create_task(self._poll_loop())
		self.status = ChannelStatus.RUNNING
		log_print(f"Signal adapter started (polling {self._api_url}, number: {self._phone_number})")

	async def stop(self):
		"""Stop polling for messages."""
		self._running = False
		if self._poll_task:
			self._poll_task.cancel()
			try:
				await self._poll_task
			except asyncio.CancelledError:
				pass
			self._poll_task = None
		self.status = ChannelStatus.STOPPED

	async def send(self, recipient_id: str, text: str, **kwargs) -> bool:
		"""Send a message to a Signal user."""
		try:
			import httpx
			async with httpx.AsyncClient() as client:
				payload = {
					"message":    text,
					"number":     self._phone_number,
					"recipients": [recipient_id],
				}
				resp = await client.post(
					f"{self._api_url}/v2/send",
					json=payload,
					timeout=30,
				)
				return resp.status_code == 201
		except Exception as e:
			self._error = str(e)
			return False

	# ── Polling Loop ──────────────────────────────────────────────

	async def _poll_loop(self):
		"""Poll signal-cli for new messages."""
		import httpx

		while self._running:
			try:
				async with httpx.AsyncClient() as client:
					resp = await client.get(
						f"{self._api_url}/v1/receive/{self._phone_number}",
						timeout=30,
					)
					if resp.status_code == 200:
						messages = resp.json()
						for raw in messages:
							await self._handle_raw_message(raw)
			except asyncio.CancelledError:
				break
			except Exception as e:
				self._error = str(e)

			await asyncio.sleep(self._poll_interval)

	async def _handle_raw_message(self, raw: Dict[str, Any]):
		"""Process a raw message from signal-cli."""
		envelope = raw.get("envelope", {})
		data_msg = envelope.get("dataMessage")

		if not data_msg:
			return

		text = data_msg.get("message", "")
		if not text:
			return

		sender = envelope.get("source", "")
		sender_name = envelope.get("sourceName", "")

		# Determine if group or direct message
		group_info = data_msg.get("groupInfo", {})
		group_id = group_info.get("groupId", "")

		msg = ChannelMessage(
			channel_type = "signal",
			channel_id   = self.config.id,
			sender_id    = sender,
			sender_name  = sender_name,
			content      = text,
			metadata     = {
				"timestamp": envelope.get("timestamp"),
				"group_id":  group_id,
				"is_group":  bool(group_id),
			},
		)

		response = await self.on_message(msg)
		if response:
			# Reply to group or direct
			recipient = group_id if group_id else sender
			if group_id:
				await self._send_group(group_id, response)
			else:
				await self.send(sender, response)

	async def _send_group(self, group_id: str, text: str) -> bool:
		"""Send a message to a Signal group."""
		try:
			import httpx
			async with httpx.AsyncClient() as client:
				payload = {
					"message":    text,
					"number":     self._phone_number,
					"recipients": [group_id],
				}
				resp = await client.post(
					f"{self._api_url}/v2/send",
					json=payload,
					timeout=30,
				)
				return resp.status_code == 201
		except Exception as e:
			self._error = str(e)
			return False
