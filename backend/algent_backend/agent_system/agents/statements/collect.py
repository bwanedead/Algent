"""
Collection: poll the catalog's feeds, fetch full text for what is new, persist transcripts.

Free only. Full text comes from the feed body when the feed carries it, otherwise from a free page
read (``allow_paid_fallback=False``) — never a paid crawler. One feed's failure never aborts the
run: every feed reports its own counts and errors. State lives in ``seen.json`` so a rerun picks up
only what is new (and retries what failed, up to ``MAX_ATTEMPTS`` times).

Network seams (``http_get``, ``read_page``, ``sleep``) are injectable so tests run offline.
"""

from __future__ import annotations

import hashlib
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import urljoin

from . import store
from .contracts import Transcript
from .sources import SOURCES, Source

MAX_ATTEMPTS = 3                      # a url that keeps failing is parked, not retried forever
_TIMEOUT_S = 45.0                     # Kremlin in particular is slow
_RETRIES = 3
_PACE_S = 1.0                         # politeness between page reads
_BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Accept": "application/rss+xml,application/atom+xml,application/xml,text/xml,text/html,*/*;q=0.8",
}
_EC_API = "https://ec.europa.eu/commission/presscorner/api/documents?language=en&reference="
_EC_DETAIL = re.compile(r"detail/en/([a-z]+)_(\d+)_(\d+)", re.I)
_URL_DATE = re.compile(r"t(\d{4})(\d{2})(\d{2})_")


@dataclass
class Entry:
    url: str
    title: str
    published: str = ""               # ISO timestamp
    text: str = ""                    # whatever the feed itself carried (may be empty or a stub)


# ── network seams ─────────────────────────────────────────────────────────────────────────────
def default_http_get(url: str) -> bytes:
    import httpx

    last: Exception | None = None
    for attempt in range(_RETRIES):
        try:
            r = httpx.get(url, headers=_BROWSER_HEADERS, timeout=_TIMEOUT_S, follow_redirects=True)
            r.raise_for_status()
            return r.content
        except Exception as exc:  # noqa: BLE001 - retried, then re-raised for the per-feed report
            last = exc
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"{type(last).__name__}: {str(last)[:120]}")


def default_read_page(url: str) -> str:
    """A FREE page read through the sourcing ladder; raises when the page yields no usable text."""
    from algent_backend.agent_system.tools.sourcing.depth.fetch_content import _fetch

    result = _fetch(url, allow_paid_fallback=False)
    if result.get("quality") not in ("good", "thin"):
        raise RuntimeError(f"page read was {result.get('quality')}")
    return str(result["content"])


# ── parsing ───────────────────────────────────────────────────────────────────────────────────
def html_to_text(html: str) -> str:
    """Readable paragraphs from an HTML fragment (feed bodies carry HTML)."""
    if not html or not html.strip():
        return ""
    import lxml.html

    spaced = re.sub(r"(?i)<br\s*/?>|</(p|div|li|h[1-6]|blockquote|tr)>", r"\g<0>\n", html)
    try:
        text = lxml.html.fromstring(f"<div>{spaced}</div>").text_content()
    except Exception:  # noqa: BLE001 - unparseable body: strip tags crudely rather than lose it
        text = re.sub(r"<[^>]+>", " ", spaced)
    lines = [" ".join(line.split()) for line in text.splitlines()]
    return "\n\n".join(line for line in lines if line)


def _iso(raw: str, parsed: Any) -> str:
    if raw:
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00")).isoformat()
        except ValueError:
            pass
        try:
            return parsedate_to_datetime(raw).isoformat()
        except (TypeError, ValueError):
            pass
    if parsed:
        return datetime(*parsed[:6], tzinfo=UTC).isoformat()
    return ""


def parse_feed(payload: bytes) -> list[Entry]:
    import feedparser

    entries = []
    for e in feedparser.parse(payload).entries:
        url = e.get("link") or e.get("id") or ""
        if not url:
            continue
        bodies = [c.get("value", "") for c in e.get("content", [])] + [e.get("summary", "") or ""]
        entries.append(Entry(url=url, title=" ".join((e.get("title") or "").split()),
                             published=_iso(e.get("published") or e.get("updated") or "",
                                            e.get("published_parsed") or e.get("updated_parsed")),
                             text=html_to_text(max(bodies, key=len))))
    return entries


def parse_listing(payload: bytes, source: Source) -> list[Entry]:
    """Items from an HTML index page: anchors whose href matches ``link_pattern``; date read from the url."""
    html = payload.decode("utf-8", "replace")
    pattern = re.compile(rf"""<a[^>]+href=["']([^"']*{source.link_pattern})["'][^>]*>(.*?)</a>""", re.S | re.I)
    seen: dict[str, Entry] = {}
    for m in pattern.finditer(html):
        title = " ".join(re.sub(r"<[^>]+>", " ", m.group(2)).split())
        url = urljoin(source.url, m.group(1))
        d = _URL_DATE.search(url)
        if title and url not in seen:
            seen[url] = Entry(url=url, title=title, published=f"{d.group(1)}-{d.group(2)}-{d.group(3)}" if d else "")
    return list(seen.values())


# ── per-source collection ─────────────────────────────────────────────────────────────────────
def _transcript_id(url: str) -> str:
    return "tr_" + hashlib.sha1(url.encode("utf-8")).hexdigest()[:12]


def _title_key(e: Entry) -> str:
    """Event identity across feeds (Kremlin lists one event under both transcripts and news)."""
    return e.published[:10] + "|" + " ".join(re.findall(r"\w+", e.title.casefold()))


def _ec_reference(url: str) -> str:
    m = _EC_DETAIL.search(url)
    return f"{m.group(1).upper()}/{m.group(2)}/{m.group(3)}" if m else ""


def _body(source: Source, entry: Entry, http_get: Callable[[str], bytes], read_page: Callable[[str], str]) -> str:
    """The entry's full text per the source's declared route; falls back to a page read when the
    feed's own body is only a stub."""
    if source.body == "feed" and len(entry.text.split()) >= 40:
        return entry.text
    if source.body == "ec_api":
        ref = _ec_reference(entry.url)
        if ref:
            import json
            doc = json.loads(http_get(_EC_API + ref)).get("docuLanguageResource") or {}
            text = html_to_text(doc.get("htmlContent", ""))
            if text:
                return text
        return entry.text
    return read_page(entry.url)


def collect_source(source: Source, *, root: Any = None, days: int = 14, max_new: int = 15,
                   http_get: Callable[[str], bytes] = default_http_get,
                   read_page: Callable[[str], str] = default_read_page,
                   sleep: Callable[[float], None] = time.sleep, now: datetime | None = None) -> dict:
    """Collect one source. Returns ``{feed, entries, new, collected, skipped, failed, errors}``."""
    report: dict[str, Any] = {"feed": source.id, "entries": 0, "new": 0, "collected": 0, "skipped": 0,
                              "failed": 0, "errors": []}
    try:
        payload = http_get(source.url)
        entries = parse_listing(payload, source) if source.kind == "listing" else parse_feed(payload)
    except Exception as exc:  # noqa: BLE001 - this feed is down; the others carry on
        report["errors"].append(f"feed: {str(exc)[:160]}")
        return report
    report["entries"] = len(entries)

    horizon = ((now or datetime.now(UTC)) - timedelta(days=days)).date().isoformat()
    skip = re.compile(source.skip_title, re.I) if source.skip_title else None
    seen = store.load_seen(root)
    todo = []
    for e in entries:
        if e.url in seen["collected"] or seen["failed"].get(e.url, 0) >= MAX_ATTEMPTS:
            continue
        if (e.published and e.published[:10] < horizon) or (skip and skip.search(e.title)):
            report["skipped"] += 1
            continue
        if _title_key(e) in seen["titles"]:             # the same event already collected from another feed
            seen["collected"][e.url] = "dup:" + seen["titles"][_title_key(e)]
            report["skipped"] += 1
            continue
        todo.append(e)
    report["new"] = len(todo)
    for e in todo[:max_new]:
        try:
            text = _body(source, e, http_get, read_page)
            if source.body == "page":
                sleep(_PACE_S)
        except Exception as exc:  # noqa: BLE001 - one unreadable page must not stop the rest
            seen["failed"][e.url] = seen["failed"].get(e.url, 0) + 1
            report["failed"] += 1
            report["errors"].append(f"{e.url}: {str(exc)[:120]}")
            continue
        if not text.strip():
            seen["failed"][e.url] = seen["failed"].get(e.url, 0) + 1
            report["failed"] += 1
            report["errors"].append(f"{e.url}: empty text")
            continue
        tid = _transcript_id(e.url)
        store.save_transcript(Transcript(id=tid, feed=source.id, url=e.url, title=e.title, published=e.published,
                                         text=text, fetched_at=(now or datetime.now(UTC)).isoformat(),
                                         language=source.language), root)
        seen["collected"][e.url] = tid
        seen["titles"][_title_key(e)] = tid
        seen["failed"].pop(e.url, None)
        report["collected"] += 1
    store.save_seen(seen, root)
    return report


def collect(*, feeds: list[str] | None = None, root: Any = None, days: int = 14, max_new: int = 15,
            http_get: Callable[[str], bytes] = default_http_get,
            read_page: Callable[[str], str] = default_read_page,
            sleep: Callable[[float], None] = time.sleep, now: datetime | None = None) -> list[dict]:
    """Collect the chosen feeds (default: the whole catalog). One report per feed."""
    wanted = [s for s in SOURCES if not feeds or s.id in feeds]
    return [collect_source(s, root=root, days=days, max_new=max_new, http_get=http_get, read_page=read_page,
                           sleep=sleep, now=now) for s in wanted]
