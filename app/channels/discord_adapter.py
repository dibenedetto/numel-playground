# channels.discord_adapter — Discord Bot channel adapter
#
# Uses discord.py to connect as a bot.
# Requires a bot token from the Discord Developer Portal.

import asyncio

from   typing   import Optional
from   utils    import log_print

from   channels.base import Attachment, ChannelAdapter, ChannelConfig, ChannelMessage, ChannelStatus, MessageHandler


class DiscordAdapter(ChannelAdapter):
	"""Discord Bot adapter — chat with the Numel assistant from Discord.

	Config extras:
	  - allowed_channels: list of channel IDs to listen in (empty = all)
	  - command_prefix:   prefix for bot commands (default: "!")
	"""

	def __init__(self, config: ChannelConfig, message_handler: Optional[MessageHandler] = None):
		super().__init__(config, message_handler)
		self._client           = None
		self._run_task         = None
		self._allowed_channels = set(str(c) for c in config.extras.get("allowed_channels", []))
		self._command_prefix   = config.extras.get("command_prefix", "!")

	@property
	def type(self) -> str:
		return "discord"

	async def start(self):
		"""Start the Discord bot."""
		token = self.config.token
		if not token:
			raise ValueError("Discord bot token is required. Get one from Discord Developer Portal.")

		try:
			import discord
		except ImportError:
			raise ImportError(
				"discord.py is required for Discord integration. "
				"Install it with: pip install discord.py"
			)

		intents = discord.Intents.default()
		intents.message_content = True
		self._client = discord.Client(intents=intents)

		adapter = self  # closure reference

		@self._client.event
		async def on_ready():
			adapter.status = ChannelStatus.RUNNING
			log_print(f"Discord bot connected as {adapter._client.user}")

		@self._client.event
		async def on_message(message):
			# Ignore own messages
			if message.author == adapter._client.user:
				return

			# Filter channels if configured
			if adapter._allowed_channels and str(message.channel.id) not in adapter._allowed_channels:
				return

			# Ignore messages that don't mention the bot and aren't DMs
			is_dm = isinstance(message.channel, discord.DMChannel)
			is_mention = adapter._client.user in message.mentions
			has_prefix = message.content.startswith(adapter._command_prefix)

			if not (is_dm or is_mention or has_prefix):
				return

			# Strip mention/prefix from content
			content = message.content
			if is_mention:
				content = content.replace(f"<@{adapter._client.user.id}>", "").strip()
			elif has_prefix:
				content = content[len(adapter._command_prefix):].strip()

			# Extract attachments
			attachments = []
			for att in message.attachments:
				attachments.append(Attachment(
					url       = att.url,
					mime_type = att.content_type or "application/octet-stream",
					filename  = att.filename,
					size      = att.size,
				))

			if not content and not attachments:
				return

			msg = ChannelMessage(
				channel_type = "discord",
				channel_id   = adapter.config.id,
				sender_id    = str(message.author.id),
				sender_name  = message.author.display_name,
				content      = content,
				attachments  = attachments,
				metadata     = {
					"guild_id":   str(message.guild.id) if message.guild else None,
					"channel_id": str(message.channel.id),
					"is_dm":      is_dm,
				},
			)

			response = await adapter.on_message(msg)
			if response:
				# Split long messages (Discord limit: 2000 chars)
				for chunk in _split_text(response, 2000):
					await message.reply(chunk)

		# Start the bot in background
		self._run_task = asyncio.create_task(self._client.start(token))
		# Wait briefly for connection
		for _ in range(40):  # up to 2s
			if self._client.is_ready():
				break
			await asyncio.sleep(0.05)

		self.status = ChannelStatus.RUNNING
		log_print(f"Discord bot started")

	async def stop(self):
		"""Stop the Discord bot."""
		if self._client:
			try:
				await self._client.close()
			except Exception as e:
				log_print(f"Discord stop error: {e}")
			self._client = None
		if self._run_task:
			self._run_task.cancel()
			self._run_task = None
		self.status = ChannelStatus.STOPPED

	async def send(self, recipient_id: str, text: str, **kwargs) -> bool:
		"""Send a message to a Discord channel or user.

		kwargs:
		  attachments: list of Attachment objects (or dicts with url, mime_type, filename)
		  media_url:   single media URL shorthand
		"""
		if not self._client:
			return False

		import discord

		attachments = kwargs.get("attachments", [])
		media_url   = kwargs.get("media_url")
		if media_url and not attachments:
			attachments = [{"url": media_url, "filename": "file", "mime_type": ""}]

		try:
			# Build discord.File objects from attachment URLs
			files = []
			if attachments:
				import httpx
				async with httpx.AsyncClient() as http:
					for att in attachments:
						url  = att.url if hasattr(att, "url") else att.get("url", "")
						name = (att.filename if hasattr(att, "filename") else att.get("filename")) or "file"
						if not url:
							continue
						resp = await http.get(url, timeout=30)
						if resp.status_code == 200:
							import io
							files.append(discord.File(io.BytesIO(resp.content), filename=name))

			# Try as channel first, then as user DM
			target = self._client.get_channel(int(recipient_id))
			if not target:
				user = self._client.get_user(int(recipient_id))
				if user:
					target = await user.create_dm()

			if not target:
				return False

			if files:
				await target.send(text[:2000] if text else None, files=files)
			else:
				for chunk in _split_text(text, 2000):
					await target.send(chunk)

			return True
		except Exception as e:
			self._error = str(e)
			return False


def _split_text(text: str, max_len: int) -> list:
	"""Split text into chunks respecting the platform's message size limit."""
	if len(text) <= max_len:
		return [text]
	chunks = []
	while text:
		if len(text) <= max_len:
			chunks.append(text)
			break
		split_at = text.rfind("\n", 0, max_len)
		if split_at < max_len // 2:
			split_at = max_len
		chunks.append(text[:split_at])
		text = text[split_at:].lstrip("\n")
	return chunks
