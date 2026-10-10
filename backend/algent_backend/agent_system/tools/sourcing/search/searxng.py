"""
``searxng`` — Ohmega's own metasearch (free, no quota): the first engine in every search chain.

One query fans out to many engines (Google, DuckDuckGo, Brave, Wikipedia…) on our own server and the answers
are merged, so no single engine's rate limit or paid quota decides whether research can search. It honours
``site:`` and quotes like the engines behind it. The instance is localhost-only on the worker server
(``infra/server/searxng/``); a laptop reaches it through an SSH tunnel on the same port, so one URL works on
both. When nothing answers there (no tunnel, server down) this raises and the chain falls through to the next
engine at the cost of one refused local connection.
"""

from __future__ import annotations

import os
from typing import Any

_URL_ENV = "ALGENT_SEARXNG_URL"
_DEFAULT_URL = "http://127.0.0.1:8080"
#: SearXNG waits for its slowest engine up to its own max_request_timeout (8 s, infra settings.yml).
_TIMEOUT_S = 12.0


def base_url() -> str:
    return (os.environ.get(_URL_ENV) or _DEFAULT_URL).rstrip("/")


def parse(payload: dict[str, Any], max_results: int) -> list[dict[str, str]]:
    """SearXNG JSON -> ``[{title, url, content, published?, engines}]`` (the shape every provider returns)."""
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for r in payload.get("results") or []:
        url = str(r.get("url") or "").strip()
        if not url or url in seen:
            continue
        seen.add(url)
        row = {"title": str(r.get("title") or "").strip(), "url": url, "content": str(r.get("content") or "").strip(),
               "engines": ",".join(r.get("engines") or [])}
        if r.get("publishedDate"):
            row["published"] = str(r["publishedDate"])[:10]
        out.append(row)
        if len(out) >= max_results:
            break
    return out


def search(query: str, *, max_results: int = 5, news: bool = False) -> list[dict[str, str]]:
    """Search our own SearXNG. ``news`` asks its news category (dated coverage)."""
    import httpx

    params = {"q": query, "format": "json"}
    if news:
        params["categories"] = "news"
    resp = httpx.get(f"{base_url()}/search", params=params, timeout=_TIMEOUT_S)
    resp.raise_for_status()
    return parse(resp.json(), max_results)
