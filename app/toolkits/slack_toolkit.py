# slack_toolkit.py - Slack messaging toolkit for Numel workflow nodes
# Usage: set ToolkitConfig name="slack_toolkit", args={"token": "${SLACK_TOKEN}"}

from typing import Any, Dict, List, Optional


class SlackToolkit:
	"""Toolkit for Slack API messaging and channel management.
	Args: token (Bot User OAuth Token, starts with xoxb-)."""

	__toolkit__ = True

	def __init__(self, token: str = ""):
		self._token = token

	def _headers(self) -> dict:
		return {"Authorization": f"Bearer {self._token}", "Content-Type": "application/json"}

	def _api(self, method: str, payload: dict) -> dict:
		import httpx
		r = httpx.post(f"https://slack.com/api/{method}", json=payload, headers=self._headers(), timeout=15)
		return r.json()

	def send_message(self, channel: str, text: str, thread_ts: Optional[str] = None) -> Dict[str, Any]:
		"""Send a message to a Slack channel or DM.
		channel: channel ID or name (e.g. '#general' or 'C012AB3CD');
		text: message text (supports Slack mrkdwn);
		thread_ts: optional thread timestamp to reply in a thread.
		Returns Slack API response dict."""
		payload: dict = {"channel": channel, "text": text}
		if thread_ts:
			payload["thread_ts"] = thread_ts
		return self._api("chat.postMessage", payload)

	def list_channels(self, limit: int = 50) -> List[Dict[str, Any]]:
		"""List public channels in the workspace.
		limit: max number of channels to return (default 50).
		Returns list of {id, name, topic} dicts."""
		import httpx
		r = httpx.get(
			"https://slack.com/api/conversations.list",
			headers=self._headers(),
			params={"limit": limit},
			timeout=15,
		)
		data = r.json()
		return [
			{"id": c["id"], "name": c["name"], "topic": c.get("topic", {}).get("value", "")}
			for c in data.get("channels", [])
		]

	def get_messages(self, channel: str, limit: int = 10) -> List[Dict[str, Any]]:
		"""Fetch recent messages from a channel.
		channel: channel ID; limit: number of messages to fetch (default 10).
		Returns list of message dicts."""
		import httpx
		r = httpx.get(
			"https://slack.com/api/conversations.history",
			headers=self._headers(),
			params={"channel": channel, "limit": limit},
			timeout=15,
		)
		return r.json().get("messages", [])

	def upload_file(self, channel: str, content: str, filename: str = "output.txt", title: str = "") -> Dict[str, Any]:
		"""Upload a text snippet/file to a channel.
		channel: channel ID; content: text content; filename: displayed filename; title: optional title.
		Returns Slack API response dict."""
		import httpx
		r = httpx.post(
			"https://slack.com/api/files.upload",
			headers={"Authorization": f"Bearer {self._token}"},
			data={"channels": channel, "content": content, "filename": filename, "title": title or filename},
			timeout=30,
		)
		return r.json()
