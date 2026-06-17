"""
``gdelt_events`` — global news-event discovery via the GDELT 2.0 DOC API.

GDELT monitors world news media in 100+ languages and is completely free with
no key. It answers "what is breaking / being covered globally about X right
now" — the discovery firehose a topic-discovery agent will draw from.

API: GET https://api.gdeltproject.org/api/v2/doc/doc (artlist mode, JSON).
"""

from __future__ import annotations

from typing import Any

from ...spec import GLOBAL_SCOPE, ToolSpec
from .._wrap import as_structured_tool

GDELT_EVENTS_TOOL_ID = "gdelt_events"

_ENDPOINT = "https://api.gdeltproject.org/api/v2/doc/doc"
_TIMEOUT_S = 20.0


def _search(query: str, max_results: int = 10, timespan: str = "24h") -> list[dict[str, str]]:
    """Find recent global news articles; returns [{title, url, source, ...}, ...].

    GDELT rate-limits aggressively (429); retry a couple of times with backoff so
    a transient throttle does not fail the agent's turn outright.
    """
    import time

    import httpx

    params = {
        "query": query,
        "mode": "artlist",
        "format": "json",
        "maxrecords": max_results,
        "timespan": timespan,
    }
    response: httpx.Response | None = None
    for attempt in range(3):
        response = httpx.get(_ENDPOINT, params=params, timeout=_TIMEOUT_S)
        if response.status_code == 429 and attempt < 2:
            time.sleep(1.5 * (attempt + 1))
            continue
        break

    assert response is not None  # the loop always runs at least once
    response.raise_for_status()
    articles = response.json().get("articles", [])
    return [
        {
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "source": item.get("domain", ""),
            "country": item.get("sourcecountry", ""),
            "language": item.get("language", ""),
            "seendate": item.get("seendate", ""),
        }
        for item in articles[:max_results]
    ]


def _build() -> Any:
    return as_structured_tool(
        _search,
        name="gdelt_events",
        description=(
            "Finds recent news articles worldwide about a query via GDELT "
            "(global, multi-language, free). timespan examples: 1h, 24h, 7d."
        ),
    )


SPEC = ToolSpec(
    tool_id=GDELT_EVENTS_TOOL_ID,
    name="gdelt_events",
    description="Global breaking-news discovery across worldwide media via GDELT.",
    scope=GLOBAL_SCOPE,
    build=_build,
    channel="discovery",
)
