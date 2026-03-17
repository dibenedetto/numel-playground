# search_toolkit.py - Web search toolkit for Numel workflow nodes
# Usage: set ToolkitConfig name="search_toolkit", args={"engine": "tavily", "api_key": "${TAVILY_KEY}"}
# Requires: pip install duckduckgo-search   (for duckduckgo engine)
#           pip install httpx               (for tavily engine)

from typing import Any, Dict, List, Optional


class SearchToolkit:
	"""Toolkit for web and news search.
	Args: engine ('duckduckgo' or 'tavily', default 'duckduckgo');
	api_key (required for tavily); max_results (default 5)."""

	__toolkit__ = True

	def __init__(
		self,
		engine     : str = "duckduckgo",
		api_key    : str = "",
		max_results: int = 5,
	):
		self._engine      = engine.lower()
		self._api_key     = api_key
		self._max_results = max_results

	def search(self, query: str, max_results: Optional[int] = None) -> List[Dict[str, Any]]:
		"""Search the web for a query.
		query: search query string; max_results: override default result count.
		Returns list of {title, url, snippet} dicts."""
		n = max_results or self._max_results
		return self._tavily(query, n) if self._engine == "tavily" else self._ddg(query, n)

	def news(self, query: str, max_results: Optional[int] = None) -> List[Dict[str, Any]]:
		"""Search for recent news articles about a query.
		query: search query string; max_results: override default result count.
		Returns list of {title, url, snippet, date} dicts."""
		n = max_results or self._max_results
		if self._engine == "tavily":
			return self._tavily(query, n, topic="news")
		from duckduckgo_search import DDGS
		with DDGS() as ddgs:
			results = list(ddgs.news(query, max_results=n))
		return [
			{"title": r.get("title", ""), "url": r.get("url", ""),
			 "snippet": r.get("body", ""), "date": r.get("date", "")}
			for r in results
		]

	def _ddg(self, query: str, n: int) -> List[Dict[str, Any]]:
		from duckduckgo_search import DDGS
		with DDGS() as ddgs:
			results = list(ddgs.text(query, max_results=n))
		return [
			{"title": r.get("title", ""), "url": r.get("href", ""), "snippet": r.get("body", "")}
			for r in results
		]

	def _tavily(self, query: str, n: int, topic: str = "general") -> List[Dict[str, Any]]:
		import httpx
		payload: dict = {"api_key": self._api_key, "query": query, "max_results": n}
		if topic != "general":
			payload["topic"] = topic
		r = httpx.post("https://api.tavily.com/search", json=payload, timeout=20)
		results = r.json().get("results", [])
		return [
			{"title": r.get("title", ""), "url": r.get("url", ""),
			 "snippet": r.get("content", ""), "date": r.get("published_date", "")}
			for r in results
		]
