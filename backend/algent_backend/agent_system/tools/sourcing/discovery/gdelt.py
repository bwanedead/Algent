"""
``gdelt_events`` — global news-event discovery via the GDELT 2.0 DOC API.

GDELT monitors world news media in 100+ languages and is completely free with
no key. It answers "what is breaking / being covered globally about X right
now" — the discovery firehose a topic-discovery agent will draw from.

API: GET https://api.gdeltproject.org/api/v2/doc/doc (artlist mode, JSON).

GDELT enforces **one request per 5 seconds per IP** (its 429 body says so). We
honor that with a process-wide minimum interval before every request — retrying
faster than 5s just keeps violating the limit and escalates the throttle. We also
send an identifying User-Agent rather than the default client string.
"""

from __future__ import annotations

import time
from typing import Any

from ...spec import GLOBAL_SCOPE, ToolSpec
from .._wrap import as_structured_tool

GDELT_EVENTS_TOOL_ID = "gdelt_events"

_ENDPOINT = "https://api.gdeltproject.org/api/v2/doc/doc"
_TIMEOUT_S = 20.0
# GDELT asks for <= 1 request / 5 seconds per IP; keep a margin.
_MIN_INTERVAL_S = 5.5
_HEADERS = {"User-Agent": "Algent/0.1 (news discovery agent)"}
_last_request_monotonic = 0.0


def _search(query: str, max_results: int = 10, timespan: str = "24h") -> list[dict[str, str]]:
    """Find recent global news articles; returns [{title, url, source, ...}, ...].

    Honors GDELT's 1-request-per-5-seconds limit process-wide (sleeping out any
    remaining interval), and retries once after a full interval on a 429.
    """
    global _last_request_monotonic
    import httpx

    params = {
        "query": query,
        "mode": "artlist",
        "format": "json",
        "maxrecords": max_results,
        "timespan": timespan,
    }
    response: httpx.Response | None = None
    for attempt in range(2):
        wait = _MIN_INTERVAL_S - (time.monotonic() - _last_request_monotonic)
        if wait > 0:
            time.sleep(wait)
        _last_request_monotonic = time.monotonic()
        response = httpx.get(_ENDPOINT, params=params, headers=_HEADERS, timeout=_TIMEOUT_S)
        if response.status_code == 429 and attempt == 0:
            continue  # the loop waits a full interval before retrying
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
