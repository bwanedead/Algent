"""
GDELT DOC 2.0 API source — *targeted* queries for the beat sweep.

Where GKG is the bulk firehose (the general net), the DOC API is the scalpel: it
answers "give me recent articles matching THIS query" — a theme, a keyword set, a
country, or a combination. That's what lets a beat like "China economics" be
fetched on purpose instead of hoped for in the general sweep.

Two hard-won facts (see ITERATION_LOG):
- **Filters go inside the query string**, not as separate params:
  ``theme:ECON_STOCKMARKET sourcecountry:China`` (country by *name*). A separate
  ``sourcecountry=`` URL param is ignored.
- **The rate limit is strict and stateful** (~1 req / 5s, and it escalates a
  cooldown if you burst). This module does a single request and raises
  ``RateLimited`` on a 429 so the *sweep* can pace and back off; it never retries
  on its own. A User-Agent is required.
"""

from __future__ import annotations

_ENDPOINT = "https://api.gdeltproject.org/api/v2/doc/doc"
_TIMEOUT_S = 25.0
_HEADERS = {"User-Agent": "Algent/0.1 (news discovery ingestion)"}


class RateLimited(Exception):
    """Raised on an HTTP 429 so the caller can back off (we never retry here)."""


def search(
    query: str,
    *,
    max_records: int = 25,
    timespan: str = "24h",
    sort: str = "datedesc",
    client: object | None = None,
) -> list[dict[str, str]]:
    """One DOC API artlist query -> normalized article dicts. Single attempt."""
    import httpx

    own = client is None
    http = client or httpx.Client(timeout=_TIMEOUT_S, headers=_HEADERS)
    try:
        response = http.get(  # type: ignore[attr-defined]
            _ENDPOINT,
            params={
                "query": query,
                "mode": "artlist",
                "format": "json",
                "maxrecords": max_records,
                "timespan": timespan,
                "sort": sort,
            },
        )
        if response.status_code == 429:
            raise RateLimited(response.text.strip()[:120])
        if response.status_code != 200:
            raise RuntimeError(f"DOC API HTTP {response.status_code} for {query!r}")
        articles = _parse(response)
    finally:
        if own:
            http.close()  # type: ignore[attr-defined]
    return articles[:max_records]


def _parse(response: object) -> list[dict[str, str]]:
    # A non-JSON 200 body is GDELT soft-throttling/erroring, not "no results" —
    # raise so the sweep records it as a (retryable) failure instead of silently
    # logging the beat as zero hits. A valid JSON with an empty list is genuine 0.
    try:
        raw = response.json().get("articles", [])  # type: ignore[attr-defined]
    except ValueError as exc:
        raise RuntimeError("DOC API returned a non-JSON body (likely throttled)") from exc
    return [
        {
            "title": a.get("title", ""),
            "url": a.get("url", ""),
            "domain": a.get("domain", ""),
            "country": a.get("sourcecountry", ""),
            "language": a.get("language", ""),
            "seendate": a.get("seendate", ""),
        }
        for a in raw
    ]
