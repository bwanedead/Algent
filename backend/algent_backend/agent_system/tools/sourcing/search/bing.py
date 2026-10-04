"""
``bing`` — keyless web search over Bing's RSS output (free, last-resort of the free engines).

Why it exists: DuckDuckGo answers a scraper's burst with a multi-minute challenge page, and a
free tier with one engine is a free tier that is down half the time. Bing's ``format=rss`` is
plain XML that keeps answering while DDG is blocked. The trade is honest and stated to the agent:
a broad index with mediocre relevance, and it does NOT honour ``site:`` (it returns unrelated
pages). So it sits AFTER the paid engines in the keyword chain, and a ``site:domain`` query is
handled here by folding the domain into the words and then keeping only results on that domain —
empty beats junk, because an agent reads whatever comes back.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

_ENDPOINT = "https://www.bing.com/search"
_TIMEOUT_S = 15.0
_SITE_RE = re.compile(r"\bsite:(\S+)", re.I)
_TAG_RE = re.compile(r"<[^>]+>")


def _host(url: str) -> str:
    host = urlparse(url).netloc.lower()
    return host[4:] if host.startswith("www.") else host


def _on_domain(url: str, domain: str) -> bool:
    host = _host(url)
    return host == domain or host.endswith("." + domain)


def parse_feed(xml: str) -> list[dict[str, str]]:
    """Bing RSS -> ``[{title, url, content}]`` (the shape every provider returns)."""
    import feedparser

    return [
        {
            "title": e.get("title", "").strip(),
            "url": e.get("link", ""),
            "content": _TAG_RE.sub("", e.get("description", "") or e.get("summary", "")).strip(),
        }
        for e in feedparser.parse(xml).entries
        if e.get("link")
    ]


def search(query: str, max_results: int = 10) -> list[dict[str, str]]:
    """Search Bing; a ``site:`` query is domain-filtered after the fact (may return ``[]``)."""
    import httpx

    sites = [m.lower().removeprefix("www.").rstrip("/") for m in _SITE_RE.findall(query)]
    words = _SITE_RE.sub(lambda m: m.group(1), query).strip()  # keep the domain as a hint word
    response = httpx.get(
        _ENDPOINT, params={"q": words, "format": "rss", "setlang": "en"},
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/123.0.0.0 Safari/537.36"},
        timeout=_TIMEOUT_S, follow_redirects=True,
    )
    response.raise_for_status()
    hits = parse_feed(response.text)
    if sites:
        hits = [h for h in hits if any(_on_domain(h["url"], d) for d in sites)]
    return hits[:max_results]
