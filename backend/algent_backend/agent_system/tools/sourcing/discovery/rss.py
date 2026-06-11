"""
``rss_feed`` — fetch and parse an RSS/Atom feed. Free, no key.

Discovery-channel tool: point it at outlet feeds to see what is being published
right now. Aimed at the future topic-discovery agent more than per-topic
research, but generally useful supplemental aid.

Only this module imports ``feedparser``.
"""

from __future__ import annotations

from typing import Any

from ...spec import GLOBAL_SCOPE, ToolSpec
from .._wrap import as_structured_tool

RSS_FEED_TOOL_ID = "rss_feed"


def _fetch(feed_url: str, max_items: int = 10) -> list[dict[str, str]]:
    """Parse a feed and return [{title, link, published, summary}, ...]."""
    import feedparser

    parsed = feedparser.parse(feed_url)
    items: list[dict[str, str]] = []
    for entry in parsed.entries[:max_items]:
        items.append(
            {
                "title": entry.get("title", ""),
                "link": entry.get("link", ""),
                "published": entry.get("published", entry.get("updated", "")),
                "summary": entry.get("summary", ""),
            }
        )
    return items


def _build() -> Any:
    return as_structured_tool(
        _fetch,
        name="rss_feed",
        description="Fetches an RSS/Atom feed URL and returns its latest entries.",
    )


SPEC = ToolSpec(
    tool_id=RSS_FEED_TOOL_ID,
    name="rss_feed",
    description="Reads RSS/Atom feeds for what outlets are publishing right now.",
    scope=GLOBAL_SCOPE,
    build=_build,
    channel="discovery",
)
