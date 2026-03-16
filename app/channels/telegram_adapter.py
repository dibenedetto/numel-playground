# channels.telegram_adapter — Telegram Bot channel adapter
#
# Uses the Telegram Bot API (via python-telegram-bot or raw HTTP).
# Requires a bot token from @BotFather.

import asyncio
import json

from   typing   import Optional
from   utils    import log_print

from   channels.base import ChannelAdapter, ChannelConfig, ChannelMessage, ChannelStatus, MessageHandler


class TelegramAdapter(ChannelAdapter):
	"""Telegram Bot adapter — chat with the Numel assistant from Telegram."""

	def __init__(self, config: ChannelConfig, message_handler: Optional[MessageHandler] = None):
		super().__init__(config, message_handler)
		self._app       = None   # telegram.ext.Application
		self._poll_task = None

	@property
	def type(self) -> str:
		return "telegram"

	async def start(self):
		"""Start the Telegram bot polling loop."""
		token = self.config.token
		if not token:
			raise ValueError("Telegram bot token is required. Get one from @BotFather.")

		try:
			from telegram import Update
			from telegram.ext import Application, MessageHandler as TGHandler, filters, ContextTypes
		except ImportError:
			raise ImportError(
				"python-telegram-bot is required for Telegram integration. "
				"Install it with: pip install python-telegram-bot"
			)

		# Build the bot application
		self._app = Application.builder().token(token).build()

		# Register message handler
		async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
			if not update.message or not update.message.text:
				return

			msg = ChannelMessage(
				channel_type = "telegram",
				channel_id   = self.config.id,
				sender_id    = str(update.message.from_user.id),
				sender_name  = update.message.from_user.first_name or "",
				content      = update.message.text,
				metadata     = {
					"chat_id":    update.message.chat_id,
					"message_id": update.message.message_id,
					"chat_type":  update.message.chat.type,
				},
			)

			response = await self.on_message(msg)
			if response:
				# Split long messages (Telegram limit: 4096 chars)
				for chunk in _split_text(response, 4096):
					await update.message.reply_text(chunk)

		self._app.add_handler(TGHandler(filters.TEXT & ~filters.COMMAND, handle_message))

		# /start command
		async def handle_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
			await update.message.reply_text(
				f"Hello! I'm {self.config.name or 'Numel Assistant'}. "
				"Send me a message to interact with your Numel Playground workspace."
			)

		from telegram.ext import CommandHandler
		self._app.add_handler(CommandHandler("start", handle_start))

		# Start polling in background
		await self._app.initialize()
		await self._app.start()
		self._poll_task = asyncio.create_task(self._app.updater.start_polling())

		self.status = ChannelStatus.RUNNING
		log_print(f"Telegram bot started (polling)")

	async def stop(self):
		"""Stop the Telegram bot."""
		if self._app:
			try:
				if self._app.updater and self._app.updater.running:
					await self._app.updater.stop()
				await self._app.stop()
				await self._app.shutdown()
			except Exception as e:
				log_print(f"Telegram stop error: {e}")
			self._app = None
		self.status = ChannelStatus.STOPPED

	async def send(self, recipient_id: str, text: str, **kwargs) -> bool:
		"""Send a message to a Telegram chat."""
		if not self._app or not self._app.bot:
			return False
		try:
			for chunk in _split_text(text, 4096):
				await self._app.bot.send_message(chat_id=int(recipient_id), text=chunk)
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
		# Try to split at a newline
		split_at = text.rfind("\n", 0, max_len)
		if split_at < max_len // 2:
			split_at = max_len
		chunks.append(text[:split_at])
		text = text[split_at:].lstrip("\n")
	return chunks
