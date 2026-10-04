"""
``gnews`` — keyless recent-news search over Google News RSS (the free "what is being reported" tier).

Gives dated headlines with the publishing outlet — the right shape for "what has been said about
X this week", which a keyword index answers badly. The cost: each item's ``link`` is an opaque
``news.google.com/rss/articles/...`` token that does NOT redirect to the article on a plain GET,
so a bare feed hands the agent unreadable URLs — and an agent with unreadable URLs guesses.

So the top few items are resolved to a real article URL, cheapest-and-surest first:
1. **decode the link** — old ids are protobuf-in-base64 with the URL inside (no request at all);
   new ids ("CBMi...") are decoded by Google's own ``batchexecute`` endpoint using the signature
   and timestamp embedded in the article page. Keyless, no search engine involved, so it keeps
   working while DuckDuckGo is serving its challenge page.
2. **title search** — the exact headline plus ``site:<outlet domain>`` through DDG, then Bing,
   taking the first hit on that domain.
Resolution is best-effort and bounded; an item that does not resolve keeps its Google link and
says ``resolved: false`` so the agent knows to search for it rather than try to read it.
"""

from __future__ import annotations

import base64
import calendar
import datetime as dt
import json
import re
from typing import Any
from urllib.parse import quote, urlparse

from . import bing, circuit, ddg

_ENDPOINT = "https://news.google.com/rss/search"
_TIMEOUT_S = 15.0
#: How many of the top items get a DDG resolution query. Each costs one paced (~1.5s) DDG
#: request, so 3 bounds the added latency to a few seconds while covering the headlines an agent
#: actually reads first; the rest stay as headline + outlet, still useful as leads.
_RESOLVE_TOP = 3
_DECODE_TIMEOUT_S = 8.0  # per decode request; two requests per item, so a stall stays bounded
_BATCH_ENDPOINT = "https://news.google.com/_/DotsSplashUi/data/batchexecute"
_ARTICLE_PAGE = "https://news.google.com/rss/articles/{gid}"
_SIG_RE = re.compile(r'data-n-a-sg="([^"]+)"')
_TS_RE = re.compile(r'data-n-a-ts="([^"]+)"')
_EMBEDDED_URL_RE = re.compile(r"https?://[!-~]+")


def _host(url: str) -> str:
    host = urlparse(url).netloc.lower()
    return host[4:] if host.startswith("www.") else host


def _same_site(url: str, outlet_host: str) -> bool:
    host = _host(url)
    return bool(outlet_host) and (host == outlet_host or host.endswith("." + outlet_host))


def _clean_title(title: str, outlet: str) -> str:
    """Google appends ' - Outlet' to every headline; the outlet is its own field."""
    suffix = f" - {outlet}"
    return title[: -len(suffix)].rstrip() if outlet and title.endswith(suffix) else title


def _iso_date(struct_time: Any) -> str:
    if not struct_time:
        return ""
    return dt.datetime.fromtimestamp(calendar.timegm(struct_time), dt.timezone.utc).date().isoformat()


def parse_feed(xml: str) -> list[dict[str, Any]]:
    """Parse Google News RSS into unresolved items (``url`` is still the opaque Google link)."""
    import feedparser

    items: list[dict[str, Any]] = []
    for entry in feedparser.parse(xml).entries:
        source = entry.get("source") or {}
        outlet = source.get("title", "")
        items.append({
            "title": _clean_title(entry.get("title", ""), outlet),
            "outlet": outlet,
            "outlet_url": source.get("href", ""),
            "published": _iso_date(entry.get("published_parsed")),
            "url": entry.get("link", ""),
            "resolved": False,
        })
    return items


def _article_id(link: str) -> str:
    path = urlparse(link).path
    return path.rsplit("/articles/", 1)[1] if "/articles/" in path else ""


def decode_embedded(gid: str) -> str | None:
    """Old-format ids carry the destination URL in plain protobuf bytes; None for new-format ids."""
    try:
        raw = base64.urlsafe_b64decode(gid + "=" * (-len(gid) % 4))
    except ValueError:
        return None
    m = _EMBEDDED_URL_RE.search(raw.decode("latin-1"))
    return m.group(0) if m else None


def parse_batch_response(text: str) -> str | None:
    """Pull the article URL out of a ``batchexecute`` reply (JSON chunks after an XSSI prefix)."""
    for chunk in text.split("\n\n"):
        try:
            payload = json.loads(chunk)[0][2]
            url = json.loads(payload)[1]
        except (ValueError, IndexError, KeyError, TypeError):
            continue
        if isinstance(url, str) and url.startswith("http"):
            return url
    return None


def decode_via_google(gid: str) -> str | None:
    """New-format ids: read the page's signature+timestamp, ask ``batchexecute`` for the URL."""
    import httpx

    page = httpx.get(_ARTICLE_PAGE.format(gid=gid), headers=ddg._HEADERS,  # noqa: SLF001
                     timeout=_DECODE_TIMEOUT_S, follow_redirects=True)
    sig, ts = _SIG_RE.search(page.text), _TS_RE.search(page.text)
    if not (sig and ts):
        return None
    inner = ["garturlreq", [["X", "X", ["X", "X"], None, None, 1, 1, "US:en", None, 1, None, None,
                             None, None, None, 0, 1], "X", "X", 1, [1, 1, 1], 1, 1, None, 0, 0,
                            None, 0], gid, int(ts.group(1)), sig.group(1)]
    form = json.dumps([[["Fbv4je", json.dumps(inner), None, "generic"]]])
    reply = httpx.post(
        _BATCH_ENDPOINT, content="f.req=" + quote(form),
        headers={**ddg._HEADERS,  # noqa: SLF001
                 "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8"},
        timeout=_DECODE_TIMEOUT_S,
    )
    return parse_batch_response(reply.text) if reply.status_code == 200 else None


def _decode(item: dict[str, Any]) -> bool:
    gid = _article_id(item["url"])
    if not gid:
        return False
    url = decode_embedded(gid)
    if url is None:
        try:
            url = decode_via_google(gid)
        except Exception:  # noqa: BLE001 — falls through to the title search
            url = None
    if url and not _host(url).endswith("google.com"):
        item["url"], item["resolved"] = url, True
        return True
    return False


def _resolve_by_title(item: dict[str, Any]) -> None:
    """Swap ``item['url']`` for the real article URL when DDG finds it on the outlet's domain."""
    outlet_host = _host(item["outlet_url"])
    if not outlet_host or not item["title"]:
        return
    query = f'"{item["title"]}" site:{outlet_host}'
    # DDG first (honours site:); Bing second, filtered to the outlet's domain so its weak
    # relevance can only produce a miss, never a wrong page.
    for name, engine in (("ddg", ddg.search), ("bing", bing.search)):
        if circuit.is_open(name):
            continue  # a blocked engine stays untouched; retrying it only extends the block
        try:
            hits = engine(query, max_results=5)
        except Exception as exc:  # noqa: BLE001
            circuit.record_failure(name, exc)
            continue
        for hit in hits:
            if _same_site(hit["url"], outlet_host):
                item["url"], item["resolved"] = hit["url"], True
                return


def _resolve(item: dict[str, Any]) -> None:
    """Best-effort: decode the Google link; failing that, find the article by title."""
    if not _decode(item):
        _resolve_by_title(item)


def search(query: str, max_results: int = 10) -> list[dict[str, Any]]:
    """Recent dated coverage for ``query``: ``[{title, outlet, outlet_url, published, url, resolved}]``."""
    import httpx

    response = httpx.get(
        _ENDPOINT,
        params={"q": query, "hl": "en-US", "gl": "US", "ceid": "US:en"},
        headers=ddg._HEADERS, timeout=_TIMEOUT_S, follow_redirects=True,  # noqa: SLF001
    )
    response.raise_for_status()
    items = parse_feed(response.text)[:max_results]
    for item in items[:_RESOLVE_TOP]:
        try:
            _resolve(item)
        except Exception:  # noqa: BLE001 — resolution is a bonus; the headline stands alone
            continue
    return items
