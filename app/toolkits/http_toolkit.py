# http_toolkit.py - HTTP request toolkit for Numel workflow nodes
# Usage: set ToolkitConfig name="http_toolkit", args={"base_url": "https://api.example.com", "auth_token": "${MY_API_KEY}"}

from typing import Any, Dict, Optional


class HttpToolkit:
	"""Toolkit for making HTTP requests (GET, POST, PUT, DELETE, PATCH).
	Args: base_url (optional prefix for relative URLs), auth_token (added as Bearer token),
	headers (dict of extra headers), timeout (seconds, default 30)."""

	__toolkit__ = True

	def __init__(
		self,
		base_url  : str                        = "",
		headers   : Optional[Dict[str, str]]   = None,
		auth_token: Optional[str]              = None,
		timeout   : float                      = 30.0,
	):
		self._base_url = base_url.rstrip("/")
		self._headers  = dict(headers or {})
		if auth_token:
			self._headers["Authorization"] = f"Bearer {auth_token}"
		self._timeout = timeout

	def _url(self, path: str) -> str:
		if path.startswith("http://") or path.startswith("https://"):
			return path
		return (self._base_url + "/" + path.lstrip("/")) if self._base_url else path

	def get(self, url: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
		"""HTTP GET request. url: path or full URL; params: optional query params dict. Returns {status, body, headers}."""
		import httpx
		r = httpx.get(self._url(url), params=params, headers=self._headers, timeout=self._timeout)
		return {"status": r.status_code, "body": r.text, "headers": dict(r.headers)}

	def post(self, url: str, json_data: Any = None, form_data: Any = None) -> Dict[str, Any]:
		"""HTTP POST request. url: path or full URL; json_data: JSON body dict; form_data: form fields dict. Returns {status, body, headers}."""
		import httpx
		kw: dict = {}
		if json_data  is not None: kw["json"] = json_data
		elif form_data is not None: kw["data"] = form_data
		r = httpx.post(self._url(url), headers=self._headers, timeout=self._timeout, **kw)
		return {"status": r.status_code, "body": r.text, "headers": dict(r.headers)}

	def put(self, url: str, json_data: Any = None) -> Dict[str, Any]:
		"""HTTP PUT request. url: path or full URL; json_data: JSON body dict. Returns {status, body, headers}."""
		import httpx
		r = httpx.put(self._url(url), json=json_data, headers=self._headers, timeout=self._timeout)
		return {"status": r.status_code, "body": r.text, "headers": dict(r.headers)}

	def delete(self, url: str) -> Dict[str, Any]:
		"""HTTP DELETE request. url: path or full URL. Returns {status, body, headers}."""
		import httpx
		r = httpx.delete(self._url(url), headers=self._headers, timeout=self._timeout)
		return {"status": r.status_code, "body": r.text, "headers": dict(r.headers)}

	def request(self, method: str, url: str, json_data: Any = None, extra_headers: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
		"""Arbitrary HTTP request. method: GET/POST/PUT/DELETE/PATCH; url: path or full URL;
		json_data: optional JSON body; extra_headers: additional headers. Returns {status, body, headers}."""
		import httpx
		merged = {**self._headers, **(extra_headers or {})}
		kw: dict = {}
		if json_data is not None:
			kw["json"] = json_data
		r = httpx.request(method.upper(), self._url(url), headers=merged, timeout=self._timeout, **kw)
		return {"status": r.status_code, "body": r.text, "headers": dict(r.headers)}
