# channels.email_adapter — Email channel adapter (IMAP polling + SMTP send)
#
# Polls an IMAP inbox for new messages and routes them through the standard
# channel_message_handler.  Replies are sent via SMTP, threaded to the
# original email using In-Reply-To / References headers.
#
# Config:
#   - token: not used (credentials are in extras)
# Config extras:
#   - smtp_host:      SMTP server (default: smtp.gmail.com)
#   - smtp_port:      SMTP port   (default: 587)
#   - username:       Email login
#   - password:       Email/app password (supports ${VAR} substitution)
#   - from_addr:      Sender address (defaults to username)
#   - use_tls:        STARTTLS for SMTP (default: true)
#   - imap_host:      IMAP server (default: derived from smtp_host)
#   - imap_port:      IMAP port   (default: 993)
#   - imap_use_ssl:   SSL for IMAP (default: true)
#   - imap_folder:    Folder to watch (default: INBOX)
#   - poll_interval:  Seconds between polls (default: 30)
#   - subject_prefix: Only process emails whose subject starts with this (optional)
#   - max_body_len:   Truncate incoming body to this length (default: 4000)

import asyncio
import email      as _email
import imaplib
import re
import smtplib

from email.header         import decode_header as _decode_header
from email.mime.multipart import MIMEMultipart
from email.mime.text      import MIMEText
from email.utils          import make_msgid, formataddr, parseaddr
from typing               import Any, Dict, List, Optional

from channels.base import ChannelAdapter, ChannelConfig, ChannelMessage, ChannelStatus, MessageHandler
from utils         import log_print


def _decode_str(value: Any) -> str:
	"""Decode an RFC-2047-encoded header to a plain string."""
	if value is None:
		return ""
	parts = _decode_header(str(value))
	out   = []
	for raw, enc in parts:
		if isinstance(raw, bytes):
			out.append(raw.decode(enc or "utf-8", errors="replace"))
		else:
			out.append(str(raw))
	return " ".join(out)


def _extract_body(msg) -> str:
	"""Extract plain-text body from an email.message.Message."""
	if msg.is_multipart():
		for part in msg.walk():
			ct = part.get_content_type()
			cd = str(part.get("Content-Disposition", ""))
			if ct == "text/plain" and "attachment" not in cd:
				payload = part.get_payload(decode=True)
				if payload:
					return payload.decode(part.get_content_charset() or "utf-8", errors="replace")
		# Fallback: try text/html, strip tags
		for part in msg.walk():
			if part.get_content_type() == "text/html":
				payload = part.get_payload(decode=True)
				if payload:
					html = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
					return re.sub(r"<[^>]+>", "", html).strip()
	else:
		payload = msg.get_payload(decode=True)
		if payload:
			text = payload.decode(msg.get_content_charset() or "utf-8", errors="replace")
			if msg.get_content_type() == "text/html":
				return re.sub(r"<[^>]+>", "", text).strip()
			return text
	return ""


class EmailAdapter(ChannelAdapter):
	"""Email channel adapter — chat with the Numel assistant via email.

	Polls an IMAP mailbox for new (UNSEEN) messages, routes them through
	the standard agent pipeline, and replies via SMTP in the same thread.

	Config extras:
	  - smtp_host, smtp_port, username, password, from_addr, use_tls
	  - imap_host, imap_port, imap_use_ssl, imap_folder
	  - poll_interval (seconds, default 30)
	  - subject_prefix (optional filter)
	  - max_body_len (default 4000)
	"""

	def __init__(self, config: ChannelConfig, message_handler: Optional[MessageHandler] = None):
		super().__init__(config, message_handler)
		e = config.extras

		# SMTP
		self._smtp_host  = e.get("smtp_host", "smtp.gmail.com")
		self._smtp_port  = int(e.get("smtp_port", 587))
		self._username   = e.get("username", "")
		self._password   = e.get("password", config.token or "")
		self._from_addr  = e.get("from_addr", self._username)
		self._use_tls    = e.get("use_tls", True)

		# IMAP
		self._imap_host    = e.get("imap_host", self._smtp_host.replace("smtp.", "imap.", 1))
		self._imap_port    = int(e.get("imap_port", 993))
		self._imap_use_ssl = e.get("imap_use_ssl", True)
		self._imap_folder  = e.get("imap_folder", "INBOX")

		# Behaviour
		self._poll_interval  = float(e.get("poll_interval", 30))
		self._subject_prefix = e.get("subject_prefix", "")
		self._max_body_len   = int(e.get("max_body_len", 4000))

		# State
		self._poll_task = None
		self._running   = False
		# Track threads: sender_email → {message_id, subject}  for In-Reply-To
		self._threads: Dict[str, Dict[str, str]] = {}

	@property
	def type(self) -> str:
		return "email"

	# ── Lifecycle ─────────────────────────────────────────────────

	async def start(self):
		if not self._username:
			raise ValueError("Email username is required in extras")
		if not self._password:
			raise ValueError("Email password (or token) is required")

		# Verify IMAP connectivity
		try:
			conn = self._imap_connect()
			conn.select(f'"{self._imap_folder}"')
			conn.logout()
		except Exception as e:
			raise ConnectionError(
				f"Cannot connect to IMAP {self._imap_host}:{self._imap_port}: {e}"
			)

		self._running   = True
		self._poll_task = asyncio.create_task(self._poll_loop())
		self.status     = ChannelStatus.RUNNING
		log_print(f"Email adapter started (IMAP {self._imap_host}, folder: {self._imap_folder}, "
				  f"poll: {self._poll_interval}s)")

	async def stop(self):
		self._running = False
		if self._poll_task:
			self._poll_task.cancel()
			try:
				await self._poll_task
			except asyncio.CancelledError:
				pass
			self._poll_task = None
		self.status = ChannelStatus.STOPPED

	# ── Send (SMTP) ──────────────────────────────────────────────

	async def send(self, recipient_id: str, text: str, **kwargs) -> bool:
		"""Send an email reply.  recipient_id is the email address."""
		subject = kwargs.get("subject", "")
		thread  = self._threads.get(recipient_id)

		if not subject:
			if thread:
				subj = thread.get("subject", "")
				subject = subj if subj.lower().startswith("re:") else f"Re: {subj}"
			else:
				subject = "Numel Assistant"

		msg = MIMEMultipart("alternative")
		msg["From"]    = formataddr(("Numel Assistant", self._from_addr))
		msg["To"]      = recipient_id
		msg["Subject"] = subject

		# Thread headers
		if thread and thread.get("message_id"):
			msg["In-Reply-To"] = thread["message_id"]
			msg["References"]  = thread["message_id"]

		msg.attach(MIMEText(text, "plain"))

		try:
			await asyncio.get_event_loop().run_in_executor(
				None, self._smtp_send, recipient_id, msg.as_string()
			)
			return True
		except Exception as e:
			self._error = str(e)
			log_print(f"Email send error to {recipient_id}: {e}")
			return False

	def _smtp_send(self, to: str, raw_msg: str):
		smtp = smtplib.SMTP(self._smtp_host, self._smtp_port, timeout=15)
		try:
			if self._use_tls:
				smtp.starttls()
			if self._username:
				smtp.login(self._username, self._password)
			smtp.sendmail(self._from_addr, to, raw_msg)
		finally:
			smtp.quit()

	# ── IMAP polling ─────────────────────────────────────────────

	def _imap_connect(self) -> imaplib.IMAP4:
		if self._imap_use_ssl:
			return imaplib.IMAP4_SSL(self._imap_host, self._imap_port)
		return imaplib.IMAP4(self._imap_host, self._imap_port)

	async def _poll_loop(self):
		while self._running:
			try:
				await asyncio.get_event_loop().run_in_executor(None, self._poll_once)
			except asyncio.CancelledError:
				break
			except Exception as e:
				self._error = str(e)
				log_print(f"Email poll error: {e}")
			await asyncio.sleep(self._poll_interval)

	def _poll_once(self):
		"""Fetch UNSEEN messages from IMAP and queue them for processing."""
		conn = self._imap_connect()
		try:
			conn.login(self._username, self._password)
			conn.select(f'"{self._imap_folder}"')
			_, data = conn.search(None, "UNSEEN")
			uids = data[0].split() if data[0] else []

			for uid in uids:
				try:
					_, raw = conn.fetch(uid, "(RFC822)")
					if not raw or not raw[0]:
						continue
					parsed = _email.message_from_bytes(raw[0][1])
					self._schedule_handle(parsed, uid, conn)
				except Exception as e:
					log_print(f"Email parse error (uid {uid}): {e}")
		finally:
			try:
				conn.logout()
			except Exception:
				pass

	def _schedule_handle(self, parsed, uid, conn):
		"""Extract fields from a parsed email and schedule async handling."""
		subject = _decode_str(parsed.get("Subject"))
		# Subject prefix filter
		if self._subject_prefix and not subject.lower().startswith(self._subject_prefix.lower()):
			return

		from_raw   = _decode_str(parsed.get("From"))
		from_name, from_addr = parseaddr(from_raw)

		# Skip our own messages
		if from_addr.lower() == self._from_addr.lower():
			return

		body = _extract_body(parsed)
		if not body.strip():
			return

		# Truncate
		if len(body) > self._max_body_len:
			body = body[:self._max_body_len] + "\n[truncated]"

		message_id = parsed.get("Message-ID", "")

		# Track thread for reply
		self._threads[from_addr] = {
			"message_id": message_id,
			"subject":    subject,
		}

		# Mark as seen
		try:
			conn.store(uid, "+FLAGS", "\\Seen")
		except Exception:
			pass

		msg = ChannelMessage(
			channel_type = "email",
			channel_id   = self.config.id,
			sender_id    = from_addr,
			sender_name  = from_name or from_addr.split("@")[0],
			content      = body,
			metadata     = {
				"subject":    subject,
				"message_id": message_id,
				"in_reply_to": parsed.get("In-Reply-To", ""),
			},
		)

		# Schedule async handler on the event loop
		loop = asyncio.get_event_loop()
		loop.call_soon_threadsafe(asyncio.ensure_future, self._handle_and_reply(msg, from_addr))

	async def _handle_and_reply(self, msg: ChannelMessage, reply_to: str):
		"""Route through the standard message handler and reply."""
		response = await self.on_message(msg)
		if response:
			await self.send(reply_to, response)
