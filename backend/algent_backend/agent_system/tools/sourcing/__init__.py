"""
Sourcing portfolio — the tools agents use to find and read information.

Organized by capability channel, one vendor per module, vendor SDK imports lazy
inside each ``build()``:

    search/      tavily (web_search), brave (brave_search), exa (semantic_search)
    social/      xai_x_search — Grok-mediated live X search (derived intelligence)
    depth/       fetch_content — full-page extraction (trafilatura -> optional Playwright -> Firecrawl)
    discovery/   rss_feed, gdelt_events, news_feeds — what's-happening + feed catalog

Adding a channel never touches agent orchestration: register the spec here,
agents reach it by tool id (or, later, by channel fan-out).
"""

from __future__ import annotations

from ..spec import ToolSpec


def sourcing_tool_specs() -> list[ToolSpec]:
    """All sourcing tool specs, for registry registration.

    Imports are local so that loading the registry stays cheap and a missing
    optional vendor dependency surfaces only when its tool is actually built.
    """
    from .depth.fetch_content import SPEC as fetch_content
    from .discovery.gdelt import SPEC as gdelt_events
    from .discovery.news_feeds import SPEC as news_feeds
    from .discovery.rss import SPEC as rss_feed
    from .search.brave import SPEC as brave_search
    from .search.exa import SPEC as semantic_search
    from .search.research import SPEC as web_search  # facade over tavily/exa/fetch (+x)
    from .social.xai_x_search import SPEC as xai_x_search

    return [
        web_search,
        brave_search,
        semantic_search,
        xai_x_search,
        fetch_content,
        rss_feed,
        gdelt_events,
        news_feeds,
    ]
