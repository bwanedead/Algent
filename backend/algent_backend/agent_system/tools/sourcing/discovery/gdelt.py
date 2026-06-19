"""
``gdelt_events`` — global news-event discovery via the GDELT 2.0 DOC API.

GDELT monitors world news media in 100+ languages and is completely free with
no key. It answers "what is breaking / being covered globally about X right
now" — the discovery firehose a topic-discovery agent will draw from.

API: GET https://api.gdeltproject.org/api/v2/doc/doc (artlist mode, JSON).

GDELT rate-limits to protect its backend (its 429 body asks for <= 1 request /
5 seconds). It also requires an identifying User-Agent. For now this tool makes
a **single attempt with no retry** — retry logic was masking the real failure
mode, so we keep it out of the problem space. On any non-200 it raises with the
exact status, URL, and response body so the failure is fully self-documenting in
the run's audit/error.log. Proper request pacing can be reintroduced once the
contact behaviour is understood.
"""

from __future__ import annotations

from typing import Any

from ...spec import GLOBAL_SCOPE, ToolSpec
from .._wrap import as_structured_tool

GDELT_EVENTS_TOOL_ID = "gdelt_events"

_ENDPOINT = "https://api.gdeltproject.org/api/v2/doc/doc"
_TIMEOUT_S = 20.0
_HEADERS = {"User-Agent": "Algent/0.1 (news discovery agent)"}


def _search(query: str, max_results: int = 10, timespan: str = "24h") -> list[dict[str, str]]:
    """Find recent global news articles; returns [{title, url, source, ...}, ...].

    One request, no retry. Raises a fully-detailed error on any non-200 so the
    nature of a GDELT failure is captured verbatim (status + URL + body).
    """
    import httpx

    response = httpx.get(
        _ENDPOINT,
        params={
            "query": query,
            "mode": "artlist",
            "format": "json",
            "maxrecords": max_results,
            "timespan": timespan,
        },
        headers=_HEADERS,
        timeout=_TIMEOUT_S,
    )
    if response.status_code != 200:
        raise RuntimeError(
            f"GDELT request failed: HTTP {response.status_code} for {response.url} "
            f"| response-body: {response.text.strip()[:400]!r}"
        )

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
