# channel_toolkit.py - Cross-channel messaging toolkit for Numel agents
# Usage: injected directly by ChannelAgentPool (not loaded via config args)

from typing import Any, Dict, List, Optional


class ChannelToolkit:
	"""Toolkit for sending messages across communication channels (Telegram, Discord, Slack, etc.).
	Allows the agent to list active channels and send messages to users on any running channel."""

	__toolkit__ = True

	def __init__(self, channel_registry=None):
		self._registry = channel_registry

	def list_channels(self) -> List[Dict[str, Any]]:
		"""List all configured channels with their type, name, status, and ID.
		Use the channel_id from the result to send messages."""
		if not self._registry:
			return []
		result = []
		for ch_id, adapter in self._registry._adapters.items():
			cfg = adapter.config
			result.append({
				"channel_id":   cfg.id,
				"name":         cfg.name,
				"channel_type": cfg.channel_type,
				"status":       adapter.status.value if hasattr(adapter.status, 'value') else str(adapter.status),
			})
		return result

	def send_message(self, channel_id: str, recipient_id: str, text: str,
					 attachments: str = "") -> Dict[str, Any]:
		"""Send a message to a specific user on a channel.
		channel_id: the adapter ID (from list_channels).
		recipient_id: platform-specific user/chat ID (e.g. Telegram chat_id, Discord channel_id).
		text: message content to send.
		attachments: optional JSON string of attachment list, e.g. '[{"url":"https://...","mime_type":"image/png","filename":"photo.png"}]'.
		Returns {sent: bool, error: str or None}."""
		if not self._registry:
			return {"sent": False, "error": "Channel registry not available"}
		adapter = self._registry._adapters.get(channel_id)
		if not adapter:
			return {"sent": False, "error": f"Channel '{channel_id}' not found"}
		status = adapter.status.value if hasattr(adapter.status, 'value') else str(adapter.status)
		if status != "running":
			return {"sent": False, "error": f"Channel '{channel_id}' is not running (status: {status})"}

		# Parse attachments JSON
		send_kwargs = {}
		if attachments:
			import json
			try:
				att_list = json.loads(attachments) if isinstance(attachments, str) else attachments
				if isinstance(att_list, list):
					send_kwargs["attachments"] = att_list
			except Exception:
				pass  # ignore malformed attachments JSON

		import asyncio
		try:
			loop = asyncio.get_event_loop()
			if loop.is_running():
				import concurrent.futures
				with concurrent.futures.ThreadPoolExecutor() as pool:
					future = pool.submit(asyncio.run, adapter.send(recipient_id, text, **send_kwargs))
					future.result(timeout=30)
			else:
				loop.run_until_complete(adapter.send(recipient_id, text, **send_kwargs))
			return {"sent": True, "error": None}
		except Exception as e:
			return {"sent": False, "error": str(e)}

	def broadcast(self, text: str, channel_types: str = "") -> Dict[str, Any]:
		"""Broadcast a message to all running channels (or specific types).
		text: message content.
		channel_types: comma-separated filter e.g. 'telegram,discord' (empty = all).
		Note: sends to each channel's default/last-known chat. Best for notification-style messages.
		Returns {sent_count: int, errors: list}."""
		if not self._registry:
			return {"sent_count": 0, "errors": ["Channel registry not available"]}
		type_filter = set(t.strip().lower() for t in channel_types.split(",") if t.strip()) if channel_types else None
		sent = 0
		errors = []
		for ch_id, adapter in self._registry._adapters.items():
			cfg = adapter.config
			status = adapter.status.value if hasattr(adapter.status, 'value') else str(adapter.status)
			if status != "running":
				continue
			if type_filter and cfg.channel_type.lower() not in type_filter:
				continue
			# Use session_id as default recipient if available
			recipient = cfg.session_id or cfg.extras.get("default_chat_id", "")
			if not recipient:
				errors.append(f"{cfg.name}: no default recipient configured")
				continue
			import asyncio
			try:
				import concurrent.futures
				with concurrent.futures.ThreadPoolExecutor() as pool:
					future = pool.submit(asyncio.run, adapter.send(recipient, text))
					future.result(timeout=30)
				sent += 1
			except Exception as e:
				errors.append(f"{cfg.name}: {e}")
		return {"sent_count": sent, "errors": errors}
