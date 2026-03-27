# channels.telegram_adapter — Telegram Bot channel adapter
#
# Uses the Telegram Bot API (via python-telegram-bot or raw HTTP).
# Requires a bot token from @BotFather.

import asyncio
import json

from   typing   import Optional
from   utils    import log_print

from   channels.base import Attachment, ChannelAdapter, ChannelConfig, ChannelMessage, ChannelStatus, MessageHandler


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
			if not update.message:
				return

			# Extract text (may be empty for media-only messages)
			text = update.message.text or update.message.caption or ""

			# Extract attachments from photos, documents, audio, video, voice, stickers
			attachments = []
			bot = context.bot

			if update.message.photo:
				# Telegram sends multiple sizes; take the largest
				photo = update.message.photo[-1]
				f = await bot.get_file(photo.file_id)
				attachments.append(Attachment(
					url       = f.file_path or "",
					mime_type = "image/jpeg",
					filename  = f"{photo.file_unique_id}.jpg",
					size      = photo.file_size,
				))

			if update.message.document:
				doc = update.message.document
				f = await bot.get_file(doc.file_id)
				attachments.append(Attachment(
					url       = f.file_path or "",
					mime_type = doc.mime_type or "application/octet-stream",
					filename  = doc.file_name,
					size      = doc.file_size,
				))

			if update.message.audio:
				aud = update.message.audio
				f = await bot.get_file(aud.file_id)
				attachments.append(Attachment(
					url       = f.file_path or "",
					mime_type = aud.mime_type or "audio/mpeg",
					filename  = aud.file_name or f"{aud.file_unique_id}.mp3",
					size      = aud.file_size,
				))

			if update.message.video:
				vid = update.message.video
				f = await bot.get_file(vid.file_id)
				attachments.append(Attachment(
					url       = f.file_path or "",
					mime_type = vid.mime_type or "video/mp4",
					filename  = vid.file_name or f"{vid.file_unique_id}.mp4",
					size      = vid.file_size,
				))

			if update.message.voice:
				voice = update.message.voice
				f = await bot.get_file(voice.file_id)
				attachments.append(Attachment(
					url       = f.file_path or "",
					mime_type = voice.mime_type or "audio/ogg",
					filename  = f"{voice.file_unique_id}.ogg",
					size      = voice.file_size,
				))

			if update.message.sticker:
				stk = update.message.sticker
				f = await bot.get_file(stk.file_id)
				attachments.append(Attachment(
					url       = f.file_path or "",
					mime_type = "image/webp",
					filename  = f"{stk.file_unique_id}.webp",
					size      = stk.file_size,
				))

			# Skip if no text and no attachments
			if not text and not attachments:
				return

			msg = ChannelMessage(
				channel_type = "telegram",
				channel_id   = self.config.id,
				sender_id    = str(update.message.from_user.id),
				sender_name  = update.message.from_user.first_name or "",
				content      = text,
				attachments  = attachments,
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

		# Accept text, photos, documents, audio, video, voice, stickers
		self._app.add_handler(TGHandler(
			(filters.TEXT | filters.PHOTO | filters.Document.ALL |
			 filters.AUDIO | filters.VIDEO | filters.VOICE | filters.Sticker.ALL)
			& ~filters.COMMAND,
			handle_message,
		))

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
		"""Send a message to a Telegram chat.

		kwargs:
		  attachments: list of Attachment objects (or dicts with url, mime_type)
		  media_url:   single media URL shorthand
		  media_type:  MIME type for media_url
		"""
		if not self._app or not self._app.bot:
			return False

		chat_id = int(recipient_id)
		attachments = kwargs.get("attachments", [])
		media_url   = kwargs.get("media_url")
		media_type  = kwargs.get("media_type", "")

		# Single media shorthand → attachments list
		if media_url and not attachments:
			attachments = [{"url": media_url, "mime_type": media_type}]

		try:
			# Send attachments
			for att in attachments:
				url  = att.url if hasattr(att, "url") else att.get("url", "")
				mime = att.mime_type if hasattr(att, "mime_type") else att.get("mime_type", "")
				if not url:
					continue

				if mime.startswith("image/"):
					await self._app.bot.send_photo(chat_id=chat_id, photo=url, caption=text[:1024] if text else None)
					text = ""  # caption sent with first media
				elif mime.startswith("video/"):
					await self._app.bot.send_video(chat_id=chat_id, video=url, caption=text[:1024] if text else None)
					text = ""
				elif mime.startswith("audio/"):
					await self._app.bot.send_audio(chat_id=chat_id, audio=url, caption=text[:1024] if text else None)
					text = ""
				else:
					await self._app.bot.send_document(chat_id=chat_id, document=url, caption=text[:1024] if text else None)
					text = ""

			# Send remaining text (if no attachments or text wasn't used as caption)
			if text:
				for chunk in _split_text(text, 4096):
					await self._app.bot.send_message(chat_id=chat_id, text=chunk)

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
