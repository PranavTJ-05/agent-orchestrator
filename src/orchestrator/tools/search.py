from __future__ import annotations

import html
import re
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

import httpx

from ..core.tool import Tool

USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) agent-orchestrator/0.1"
NUM_RESULTS = 5
MAX_SNIPPET_CHARS = 300


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", text))).strip()


def _real_url(href: str) -> str:
    """DuckDuckGo wraps result links in a redirect; extract the target URL."""
    if href.startswith("//"):
        href = "https:" + href
    target = parse_qs(urlparse(href).query).get("uddg")
    return unquote(target[0]) if target else href


class WebSearchTool(Tool):
    def __init__(self) -> None:
        super().__init__(
            name="web_search",
            description="Search the web for current information. Use this for research, news, facts.",
        )

    async def execute(self, query: str) -> list[dict[str, Any]]:
        """Search the web (DuckDuckGo, falling back to Wikipedia). No API key needed.

        Args:
            query: What to search for
        """
        errors: list[str] = []
        for backend in (self._duckduckgo, self._wikipedia):
            try:
                results = await backend(query)
                if results:
                    return results
                errors.append(f"{backend.__name__}: no results")
            except Exception as e:
                errors.append(f"{backend.__name__}: {e}")
        return [{
            "title": "SEARCH FAILED",
            "snippet": "No search results could be retrieved (" + "; ".join(errors) + "). "
                       "Do not guess; tell the user the information could not be retrieved.",
            "url": "",
        }]

    async def _duckduckgo(self, query: str) -> list[dict[str, Any]]:
        async with httpx.AsyncClient(timeout=15.0, headers={"User-Agent": USER_AGENT}) as client:
            resp = await client.post("https://html.duckduckgo.com/html/", data={"q": query})
            resp.raise_for_status()
        titles = re.findall(r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', resp.text, re.S)
        snippets = re.findall(r'class="result__snippet"[^>]*>(.*?)</a>', resp.text, re.S)
        results = []
        for i, (href, title) in enumerate(titles[:NUM_RESULTS]):
            results.append({
                "title": _clean(title),
                "snippet": _clean(snippets[i])[:MAX_SNIPPET_CHARS] if i < len(snippets) else "",
                "url": _real_url(href),
            })
        return results

    async def _wikipedia(self, query: str) -> list[dict[str, Any]]:
        params = {"action": "query", "list": "search", "srsearch": query,
                  "srlimit": NUM_RESULTS, "format": "json"}
        async with httpx.AsyncClient(timeout=15.0, headers={"User-Agent": USER_AGENT}) as client:
            resp = await client.get("https://en.wikipedia.org/w/api.php", params=params)
            resp.raise_for_status()
        return [
            {
                "title": item["title"],
                "snippet": _clean(item["snippet"])[:MAX_SNIPPET_CHARS],
                "url": "https://en.wikipedia.org/wiki/" + item["title"].replace(" ", "_"),
            }
            for item in resp.json().get("query", {}).get("search", [])
        ]
