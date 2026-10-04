"""
Pure parsing: RSS/Atom feeds and Google-News-style sitemaps into ``Candidate`` rows. No network.

A candidate is what a feed promises (url, title, date, a stamp that changes when the page does); the
crawler decides what to fetch. ``stamp`` is the feed's own updated/lastmod string — an unchanged stamp
means "do not refetch", a different one is how a revised page is noticed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


class ParseError(ValueError):
    """The payload is not something we can read as a feed or sitemap."""


@dataclass(frozen=True)
class Candidate:
    url: str
    title: str = ""
    published: str = ""      # ISO 8601, UTC; "" when the feed gave no date
    stamp: str = ""          # raw updated/lastmod, compared for equality only
    summary: str = ""        # feed-supplied blurb (plain text); the fallback body if the page cannot be read


def canonical_url(url: str) -> str:
    """Drop the fragment and tracking parameters so one article is one row."""
    parts = urlsplit(url.strip())
    query = urlencode([(k, v) for k, v in parse_qsl(parts.query) if not k.lower().startswith("utm_")])
    return urlunsplit((parts.scheme, parts.netloc, parts.path, query, ""))


def to_iso(raw: str = "", parsed: Any = None) -> str:
    """Best-effort ISO UTC from an RFC 822 / ISO string or a feedparser time struct; "" if hopeless."""
    raw = (raw or "").strip()
    for attempt in (lambda: datetime.fromisoformat(raw.replace("Z", "+00:00")), lambda: parsedate_to_datetime(raw)):
        try:
            dt = attempt()
            return (dt if dt.tzinfo else dt.replace(tzinfo=UTC)).astimezone(UTC).isoformat()
        except (TypeError, ValueError):
            continue
    if parsed:
        return datetime(*parsed[:6], tzinfo=UTC).isoformat()
    return ""


def html_to_text(html: str) -> str:
    """Readable text from an HTML fragment (feed summaries carry markup)."""
    if not html or not html.strip():
        return ""
    import lxml.html

    try:
        text = lxml.html.fromstring(f"<div>{html}</div>").text_content()
    except Exception:  # noqa: BLE001 - unparseable: strip tags crudely rather than lose the blurb
        text = re.sub(r"<[^>]+>", " ", html)
    return " ".join(text.split())


def parse_feed(payload: bytes) -> list[Candidate]:
    import feedparser

    parsed = feedparser.parse(payload)
    out = []
    for e in parsed.entries:
        url = e.get("link") or e.get("id") or ""
        if not url.startswith("http"):
            continue
        raw_date = e.get("published") or e.get("updated") or ""
        parsed_date = e.get("published_parsed") or e.get("updated_parsed")
        out.append(Candidate(
            url=canonical_url(url),
            title=" ".join((e.get("title") or "").split()),
            published=to_iso(raw_date, parsed_date),
            stamp=e.get("updated") or e.get("published") or "",
            summary=html_to_text(e.get("summary") or ""),
        ))
    return out


def parse_sitemap(payload: bytes) -> list[Candidate]:
    """A flat ``urlset`` (Google News sitemaps included). A ``sitemapindex`` is refused, not followed."""
    from lxml import etree

    try:
        root = etree.fromstring(payload, etree.XMLParser(resolve_entities=False, no_network=True, recover=True))
    except etree.XMLSyntaxError as exc:
        raise ParseError(f"sitemap is not XML: {exc}") from exc
    if root is None or not isinstance(root.tag, str):
        raise ParseError("sitemap is empty")
    if root.tag.endswith("sitemapindex"):
        raise ParseError("sitemap index (not followed: point the registry at a child sitemap)")
    out = []
    for node in root.iterfind("{*}url"):
        loc = (node.findtext("{*}loc") or "").strip()
        if not loc.startswith("http"):
            continue
        lastmod = (node.findtext("{*}lastmod") or "").strip()
        news = node.find("{*}news")
        title = (news.findtext("{*}title") or "").strip() if news is not None else ""
        pub = (news.findtext("{*}publication_date") or "").strip() if news is not None else ""
        out.append(Candidate(url=canonical_url(loc), title=" ".join(title.split()),
                             published=to_iso(pub or lastmod), stamp=lastmod or pub))
    return out
