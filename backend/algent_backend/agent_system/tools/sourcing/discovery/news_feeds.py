"""
``news_feeds`` — a curated catalog of working news RSS feed URLs. Free, no key.

``rss_feed`` reads a feed *URL*; without a catalog the model invents URLs (and
mostly invents dead ones). This tool hands the agent a vetted set of major outlet
feeds across beats so it can read real feeds. It just returns the catalog — no
network, no key.

The catalog is the source library's registry (``library.sources``) — one canonical feed list,
shared with the library crawl and the statements desk; add or retire a feed there.
"""

from __future__ import annotations

from typing import Any

from algent_backend.library.sources import all_sources

from ...spec import GLOBAL_SCOPE, ToolSpec
from .._wrap import as_structured_tool

NEWS_FEEDS_TOOL_ID = "news_feeds"


def _list_feeds() -> list[dict[str, str]]:
    """Return the curated feed catalog: name, url, beat, and the source's kind and region (RSS/Atom only)."""
    out = []
    for source in all_sources():
        rss = [f for f in source.feeds if f.type == "rss"]
        for feed in rss:
            name = source.name if len(rss) == 1 else f"{source.name} ({feed.beat})"
            out.append({"name": name, "url": feed.url, "beat": feed.beat, "kind": source.kind, "region": source.region})
    return out


def _build() -> Any:
    return as_structured_tool(
        _list_feeds,
        name="news_feeds",
        description="Lists curated, working news RSS feed URLs (read them with rss_feed).",
    )


SPEC = ToolSpec(
    tool_id=NEWS_FEEDS_TOOL_ID,
    name="news_feeds",
    description="Curated catalog of working news RSS feeds, to read with rss_feed.",
    scope=GLOBAL_SCOPE,
    build=_build,
    channel="discovery",
)
