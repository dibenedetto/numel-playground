# email_toolkit.py - Email sending toolkit for Numel workflow nodes
# Usage: set ToolkitConfig name="email_toolkit", args={"host": "smtp.gmail.com", "username": "...", "password": "${GMAIL_PASS}"}

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text      import MIMEText
from typing               import List, Optional


class EmailToolkit:
	"""Toolkit for sending email via SMTP.
	Args: host (SMTP server), port (default 587), username, password,
	from_addr (defaults to username), use_tls (default True)."""

	__toolkit__ = True

	def __init__(
		self,
		host     : str  = "smtp.gmail.com",
		port     : int  = 587,
		username : str  = "",
		password : str  = "",
		from_addr: str  = "",
		use_tls  : bool = True,
	):
		self._host      = host
		self._port      = port
		self._username  = username
		self._password  = password
		self._from_addr = from_addr or username
		self._use_tls   = use_tls

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
