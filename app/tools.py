# tools

import os
import stat
import smtplib
import imaplib
import email as email_lib
from email.mime.text import MIMEText
from pathlib import Path
from datetime import datetime


def square_tool(n: int) -> int:
	"""
	Return the square of a number.
	Args:
		n (int): The number to be squared.
	Returns:
		int: The square of the number.
	Examples:
		>>> square_tool(3)
		9
		>>> square_tool(-4)
		16
		>>> square_tool(0)
		0
	"""
	result = n**2
	return result


# ---------------------------------------------------------------------------
# Safety helper
# ---------------------------------------------------------------------------

def _safe_resolve(path: str, root: str) -> Path:
	"""Resolve *path* relative to *root* and ensure it stays inside *root*."""
	root_abs = Path(root).resolve()
	target = (root_abs / path).resolve()
	try:
		target.relative_to(root_abs)
	except ValueError:
		raise ValueError(f"Path traversal blocked: '{path}' escapes root '{root}'")
	return target


# ---------------------------------------------------------------------------
# Filesystem tools
# ---------------------------------------------------------------------------

def list_directory(path: str = ".", root: str = ".") -> str:
	"""
	List the contents of a directory.

	Args:
		path (str): Directory path relative to root. Defaults to root itself.
		root (str): Root directory that constrains all file operations.

	Returns:
		str: Formatted directory listing with type indicators and file sizes.
	"""
	target = _safe_resolve(path, root)
	if not target.exists():
		raise FileNotFoundError(f"Directory not found: {path}")
	if not target.is_dir():
		raise NotADirectoryError(f"Not a directory: {path}")

	entries = sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
	lines = []
	for entry in entries:
		if entry.is_dir():
			lines.append(f"[DIR]  {entry.name}/")
		else:
			size = entry.stat().st_size
			lines.append(f"[FILE] {entry.name}  ({_fmt_size(size)})")
	if not lines:
		return "(empty directory)"
	return "\n".join(lines)


def read_file(path: str, root: str = ".") -> str:
	"""
	Read and return the text contents of a file.

	Args:
		path (str): File path relative to root.
		root (str): Root directory that constrains all file operations.

	Returns:
		str: The full text contents of the file.
	"""
	target = _safe_resolve(path, root)
	if not target.exists():
		raise FileNotFoundError(f"File not found: {path}")
	return target.read_text(encoding="utf-8")


def write_file(path: str, content: str, root: str = ".") -> str:
	"""
	Write text content to a file, creating parent directories if needed.

	Args:
		path (str): File path relative to root.
		content (str): The text content to write.
		root (str): Root directory that constrains all file operations.

	Returns:
		str: Confirmation message with the number of bytes written.
	"""
	target = _safe_resolve(path, root)
	# Also verify parent stays inside root
	_safe_resolve(str(target.parent.relative_to(Path(root).resolve())), root)
	target.parent.mkdir(parents=True, exist_ok=True)
	n = target.write_text(content, encoding="utf-8")
	return f"Wrote {n} bytes to {path}"


def file_info(path: str, root: str = ".") -> str:
	"""
	Return metadata about a file or directory.

	Args:
		path (str): File or directory path relative to root.
		root (str): Root directory that constrains all file operations.

	Returns:
		str: Formatted metadata including size, timestamps, type, and permissions.
	"""
	target = _safe_resolve(path, root)
	if not target.exists():
		raise FileNotFoundError(f"Path not found: {path}")
	st = target.stat()
	kind = "directory" if target.is_dir() else "file"
	perms = stat.filemode(st.st_mode)
	created = datetime.fromtimestamp(st.st_ctime).isoformat(sep=" ", timespec="seconds")
	modified = datetime.fromtimestamp(st.st_mtime).isoformat(sep=" ", timespec="seconds")
	lines = [
		f"Path: {path}",
		f"Type: {kind}",
		f"Size: {_fmt_size(st.st_size)}",
		f"Created: {created}",
		f"Modified: {modified}",
		f"Permissions: {perms}",
	]
	return "\n".join(lines)


def search_files(pattern: str = "*", path: str = ".", root: str = ".") -> str:
	"""
	Recursively search for files matching a glob pattern.

	Args:
		pattern (str): Glob pattern to match (e.g. "*.py", "**/*.txt"). Defaults to "*".
		path (str): Starting directory relative to root. Defaults to root itself.
		root (str): Root directory that constrains all file operations.

	Returns:
		str: Newline-separated list of matching file paths relative to root.
	"""
	target = _safe_resolve(path, root)
	if not target.exists():
		raise FileNotFoundError(f"Directory not found: {path}")
	root_abs = Path(root).resolve()
	# Use rglob for recursive matching
	matches = []
	for p in target.rglob(pattern):
		try:
			rel = p.relative_to(root_abs)
			matches.append(str(rel))
		except ValueError:
			continue
	matches.sort()
	if not matches:
		return "(no matches)"
	return "\n".join(matches)


# ---------------------------------------------------------------------------
# Email tools
# ---------------------------------------------------------------------------

def send_email(
	to: str,
	subject: str,
	body: str,
	smtp_host: str = "localhost",
	smtp_port: int = 587,
	smtp_user: str = "",
	smtp_pass: str = "",
	from_addr: str = "",
) -> str:
	"""
	Send a plain-text email via SMTP.

	Args:
		to (str): Recipient email address.
		subject (str): Email subject line.
		body (str): Plain-text email body.
		smtp_host (str): SMTP server hostname.
		smtp_port (int): SMTP server port (587 for STARTTLS, 465 for SSL).
		smtp_user (str): SMTP username for authentication. Leave empty for anonymous.
		smtp_pass (str): SMTP password for authentication.
		from_addr (str): Sender address. Defaults to smtp_user if empty.

	Returns:
		str: Confirmation message with the message ID.
	"""
	sender = from_addr or smtp_user or "noreply@localhost"
	msg = MIMEText(body, "plain", "utf-8")
	msg["Subject"] = subject
	msg["From"] = sender
	msg["To"] = to

	with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as srv:
		srv.ehlo()
		if smtp_port != 25:
			srv.starttls()
			srv.ehlo()
		if smtp_user and smtp_pass:
			srv.login(smtp_user, smtp_pass)
		srv.sendmail(sender, [to], msg.as_string())

	return f"Email sent to {to} (subject: {subject})"


def retrieve_emails(
	folder: str = "INBOX",
	limit: int = 10,
	imap_host: str = "localhost",
	imap_port: int = 993,
	imap_user: str = "",
	imap_pass: str = "",
	search_criteria: str = "ALL",
) -> str:
	"""
	Retrieve emails from an IMAP mailbox.

	Args:
		folder (str): Mailbox folder to read. Defaults to "INBOX".
		limit (int): Maximum number of emails to return (most recent first).
		imap_host (str): IMAP server hostname.
		imap_port (int): IMAP server port (993 for SSL).
		imap_user (str): IMAP username for authentication.
		imap_pass (str): IMAP password for authentication.
		search_criteria (str): IMAP search query (e.g. "ALL", "UNSEEN", "FROM \"user@example.com\"").

	Returns:
		str: Formatted text with email details (From, To, Date, Subject, Body) for each message.
	"""
	conn = imaplib.IMAP4_SSL(imap_host, imap_port)
	try:
		conn.login(imap_user, imap_pass)
		conn.select(folder, readonly=True)
		_, data = conn.search(None, search_criteria)
		msg_ids = data[0].split()
		if not msg_ids:
			return "(no emails found)"

		# Most recent first, apply limit
		msg_ids = msg_ids[-limit:][::-1]

		results = []
		for mid in msg_ids:
			_, msg_data = conn.fetch(mid, "(RFC822)")
			raw = msg_data[0][1]
			msg = email_lib.message_from_bytes(raw)

			body_text = _extract_email_body(msg)
			results.append(
				f"From: {msg.get('From', '(unknown)')}\n"
				f"To: {msg.get('To', '(unknown)')}\n"
				f"Date: {msg.get('Date', '(unknown)')}\n"
				f"Subject: {msg.get('Subject', '(no subject)')}\n"
				f"Body:\n{body_text}"
			)
		return "\n\n---\n\n".join(results)
	finally:
		try:
			conn.close()
		except Exception:
			pass
		conn.logout()


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _fmt_size(size: int) -> str:
	"""Format byte size to human-readable string."""
	for unit in ("B", "KB", "MB", "GB"):
		if size < 1024:
			return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
		size /= 1024
	return f"{size:.1f} TB"


def _extract_email_body(msg) -> str:
	"""Extract plain-text body from an email message, stripping HTML tags if needed."""
	if msg.is_multipart():
		for part in msg.walk():
			ct = part.get_content_type()
			if ct == "text/plain":
				payload = part.get_payload(decode=True)
				if payload:
					return payload.decode("utf-8", errors="replace")
		# Fallback: try text/html with tag stripping
		for part in msg.walk():
			ct = part.get_content_type()
			if ct == "text/html":
				payload = part.get_payload(decode=True)
				if payload:
					import re
					html = payload.decode("utf-8", errors="replace")
					return re.sub(r"<[^>]+>", "", html).strip()
	else:
		payload = msg.get_payload(decode=True)
		if payload:
			return payload.decode("utf-8", errors="replace")
	return "(no body)"
