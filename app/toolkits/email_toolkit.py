# email_toolkit.py - Email send/receive toolkit for Numel workflow nodes
# SMTP args: host, port (587), username, password, from_addr, use_tls (True)
# IMAP args: imap_host, imap_port (993), imap_use_ssl (True)
#            If imap_host is omitted, auto-derived from SMTP host (e.g. smtp.gmail.com → imap.gmail.com)
# Usage: set ToolkitConfig name="email_toolkit",
#        args={"host": "smtp.gmail.com", "username": "...", "password": "${GMAIL_PASS}"}

import email as _email
import imaplib
import smtplib
from email.header     import decode_header as _decode_header
from email.mime.multipart import MIMEMultipart
from email.mime.text  import MIMEText
from typing           import Any, Dict, List, Optional


def _decode_str(value: Any) -> str:
	"""Decode an RFC-2047-encoded email header value to a plain string."""
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


class EmailToolkit:
	"""Toolkit for sending and receiving email via SMTP and IMAP.
	SMTP args: host (SMTP server, default smtp.gmail.com), port (default 587),
	username, password, from_addr (defaults to username), use_tls (default True).
	IMAP args: imap_host (defaults to smtp host with smtp→imap prefix swap),
	imap_port (default 993), imap_use_ssl (default True)."""

	__toolkit__ = True

	def __init__(
		self,
		host        : str  = "smtp.gmail.com",
		port        : int  = 587,
		username    : str  = "",
		password    : str  = "",
		from_addr   : str  = "",
		use_tls     : bool = True,
		imap_host   : str  = "",
		imap_port   : int  = 993,
		imap_use_ssl: bool = True,
	):
		self._host         = host
		self._port         = port
		self._username     = username
		self._password     = password
		self._from_addr    = from_addr or username
		self._use_tls      = use_tls
		# Derive IMAP host from SMTP host when not provided
		self._imap_host    = imap_host or host.replace("smtp.", "imap.", 1)
		self._imap_port    = imap_port
		self._imap_use_ssl = imap_use_ssl

	def _connect(self) -> smtplib.SMTP:
		smtp = smtplib.SMTP(self._host, self._port, timeout=15)
		if self._use_tls:
			smtp.starttls()
		if self._username:
			smtp.login(self._username, self._password)
		return smtp

	def send(self, to: str, subject: str, body: str, html: bool = False) -> str:
		"""Send an email to a single recipient.
		to: recipient address; subject: email subject; body: message body text;
		html: if True, send as HTML. Returns 'ok' or an error string."""
		msg = MIMEMultipart("alternative")
		msg["From"]    = self._from_addr
		msg["To"]      = to
		msg["Subject"] = subject
		msg.attach(MIMEText(body, "html" if html else "plain"))
		try:
			with self._connect() as smtp:
				smtp.sendmail(self._from_addr, to, msg.as_string())
			return "ok"
		except Exception as e:
			return f"error: {e}"

	# ── IMAP helpers ──────────────────────────────────────────────────────

	def _imap(self) -> imaplib.IMAP4:
		if self._imap_use_ssl:
			conn = imaplib.IMAP4_SSL(self._imap_host, self._imap_port)
		else:
			conn = imaplib.IMAP4(self._imap_host, self._imap_port)
		conn.login(self._username, self._password)
		return conn

	def _parse_message(self, raw: bytes) -> Dict[str, Any]:
		msg  = _email.message_from_bytes(raw)
		body = ""
		if msg.is_multipart():
			for part in msg.walk():
				ct = part.get_content_type()
				cd = str(part.get("Content-Disposition", ""))
				if ct == "text/plain" and "attachment" not in cd:
					body = part.get_payload(decode=True).decode(
						part.get_content_charset() or "utf-8", errors="replace"
					)
					break
		else:
			payload = msg.get_payload(decode=True)
			if payload:
				body = payload.decode(
					msg.get_content_charset() or "utf-8", errors="replace"
				)
		return {
			"from"   : _decode_str(msg.get("From")),
			"to"     : _decode_str(msg.get("To")),
			"subject": _decode_str(msg.get("Subject")),
			"date"   : _decode_str(msg.get("Date")),
			"body"   : body.strip(),
		}

	# ── Fetch methods ──────────────────────────────────────────────────────

	def fetch(
		self,
		folder  : str           = "INBOX",
		limit   : int           = 10,
		unread  : bool          = False,
		search  : Optional[str] = None,
	) -> List[Dict[str, Any]]:
		"""Fetch emails from an IMAP mailbox.
		folder: mailbox folder name (default 'INBOX');
		limit: max number of messages to return (default 10, newest first);
		unread: if True, return only unseen messages;
		search: optional IMAP search string (e.g. 'FROM "boss@example.com"').
		Returns list of {from, to, subject, date, body} dicts."""
		conn = self._imap()
		try:
			conn.select(f'"{folder}"')
			if search:
				criteria = search
			elif unread:
				criteria = "UNSEEN"
			else:
				criteria = "ALL"
			_, data = conn.search(None, criteria)
			ids = data[0].split()
			ids = ids[-limit:]          # keep the N most recent
			ids = list(reversed(ids))   # newest first
			messages = []
			for uid in ids:
				_, raw = conn.fetch(uid, "(RFC822)")
				if raw and raw[0]:
					messages.append(self._parse_message(raw[0][1]))
			return messages
		finally:
			try:
				conn.logout()
			except Exception:
				pass

	def fetch_one(self, folder: str = "INBOX", unread: bool = True) -> Optional[Dict[str, Any]]:
		"""Fetch the most recent (or most recent unread) email.
		folder: mailbox folder (default 'INBOX'); unread: limit to unseen (default True).
		Returns a single {from, to, subject, date, body} dict, or None if no match."""
		results = self.fetch(folder=folder, limit=1, unread=unread)
		return results[0] if results else None

	def mark_read(self, folder: str = "INBOX", count: int = 1) -> str:
		"""Mark the N most recent unread messages as seen.
		folder: mailbox folder (default 'INBOX'); count: number of messages to mark (default 1).
		Returns 'ok: N marked' or an error string."""
		conn = self._imap()
		try:
			conn.select(f'"{folder}"')
			_, data = conn.search(None, "UNSEEN")
			ids = data[0].split()[-count:]
			for uid in ids:
				conn.store(uid, "+FLAGS", "\\Seen")
			return f"ok: {len(ids)} marked"
		except Exception as e:
			return f"error: {e}"
		finally:
			try:
				conn.logout()
			except Exception:
				pass

	def list_folders(self) -> List[str]:
		"""List all mailbox folders available on the IMAP server.
		Returns a list of folder name strings."""
		conn = self._imap()
		try:
			_, data = conn.list()
			folders = []
			for item in data:
				if item:
					parts = item.decode().split('"')
					name  = parts[-2] if len(parts) >= 2 else item.decode().split()[-1]
					folders.append(name.strip())
			return folders
		finally:
			try:
				conn.logout()
			except Exception:
				pass

	# ── Send methods ───────────────────────────────────────────────────────

	def send_bulk(self, recipients: List[str], subject: str, body: str) -> str:
		"""Send the same email to a list of addresses.
		recipients: list of email addresses; subject: email subject; body: plain-text body.
		Returns 'ok: N sent' or an error string."""
		count  = 0
		errors = []
		try:
			with self._connect() as smtp:
				for addr in recipients:
					msg = MIMEMultipart()
					msg["From"]    = self._from_addr
					msg["To"]      = addr
					msg["Subject"] = subject
					msg.attach(MIMEText(body, "plain"))
					try:
						smtp.sendmail(self._from_addr, addr, msg.as_string())
						count += 1
					except Exception as e:
						errors.append(f"{addr}: {e}")
		except Exception as e:
			return f"error: {e}"
		if errors:
			return f"ok: {count} sent, errors: {'; '.join(errors)}"
		return f"ok: {count} sent"
