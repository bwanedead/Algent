"""
``news_feeds`` — a curated catalog of working news RSS feed URLs. Free, no key.

``rss_feed`` reads a feed *URL*; without a catalog the model invents URLs (and
mostly invents dead ones). This tool hands the agent a vetted set of major outlet
feeds across beats so it can read real feeds. It just returns the catalog — no
network, no key.

Curated by hand; verify entries with ``probe_tool rss_feed <url>`` and edit
freely. This is the obvious early tuning surface for discovery quality.
"""

from __future__ import annotations

from typing import Any

from ...spec import GLOBAL_SCOPE, ToolSpec
from .._wrap import as_structured_tool

NEWS_FEEDS_TOOL_ID = "news_feeds"

# Curated, reasonably reliable feeds. Beats let the agent pick by interest.
_FEEDS: list[dict[str, str]] = [
    {"name": "BBC World", "url": "https://feeds.bbci.co.uk/news/world/rss.xml", "beat": "world"},
    {"name": "BBC Business", "url": "https://feeds.bbci.co.uk/news/business/rss.xml", "beat": "business"},
    {"name": "BBC Technology", "url": "https://feeds.bbci.co.uk/news/technology/rss.xml", "beat": "tech"},
    {"name": "The Guardian World", "url": "https://www.theguardian.com/world/rss", "beat": "world"},
    {"name": "NPR News", "url": "https://feeds.npr.org/1001/rss.xml", "beat": "general"},
    {"name": "Al Jazeera", "url": "https://www.aljazeera.com/xml/rss/all.xml", "beat": "world"},
    {"name": "NYT World", "url": "https://rss.nytimes.com/services/xml/rss/nyt/World.xml", "beat": "world"},
    {"name": "NYT Business", "url": "https://rss.nytimes.com/services/xml/rss/nyt/Business.xml", "beat": "business"},
]


def _list_feeds() -> list[dict[str, str]]:
    """Return the curated catalog of news RSS feeds (name, url, beat)."""
    return list(_FEEDS)


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
