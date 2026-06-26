"""
X discovery via the native X API v2 — the paid, raw-control side of the A/B.

Where the Grok CLI returns a synthesized "here's what's trending" summary, this
returns raw recent posts matching a news query — cheaper per unit, fully
controllable, clean provenance. Pay-per-post (~$0.005 read), so volume is the cost
knob: ``limit`` caps it. App-only Bearer auth (read-only discovery).

This is the unambiguously-licensed channel (the API is *for* programmatic use), so
it's the safe baseline to compare the subscription-CLI route against.
"""

from __future__ import annotations

import os
from typing import Any

_RECENT_SEARCH = "https://api.x.com/2/tweets/search/recent"
_TIMEOUT_S = 25.0
# Broad news query — recent, original, English. Tunable; keep it news-shaped.
_DEFAULT_QUERY = '(breaking OR "just in" OR announces OR confirms) -is:retweet -is:reply lang:en'


def fetch_x_native(*, query: str | None = None, limit: int = 20, client: object | None = None) -> list[dict[str, Any]]:
    """Recent news-shaped posts from X, normalized. Raises if the key is missing."""
    import httpx

    bearer = os.environ.get("X_BEARER_KEY")
    if not bearer:
        raise RuntimeError("X_BEARER_KEY not set (see backend/.env)")

    own = client is None
    http = client or httpx.Client(timeout=_TIMEOUT_S, headers={"Authorization": f"Bearer {bearer}"})
    try:
        response = http.get(  # type: ignore[attr-defined]
            _RECENT_SEARCH,
            params={
                "query": query or _DEFAULT_QUERY,
                "max_results": max(10, min(limit, 100)),
                "tweet.fields": "public_metrics,created_at",
            },
        )
        if response.status_code != 200:
            raise RuntimeError(f"X API HTTP {response.status_code}: {response.text[:160]}")
        body = response.json()
    finally:
        if own:
            http.close()  # type: ignore[attr-defined]

    out: list[dict[str, Any]] = []
    for post in body.get("data", []):
        metrics = post.get("public_metrics", {}) or {}
        out.append({
            "text": post.get("text", ""),
            "url": f"https://x.com/i/web/status/{post.get('id', '')}",
            "likes": metrics.get("like_count", 0),
            "reposts": metrics.get("retweet_count", 0),
            "created_at": post.get("created_at", ""),
            "source": "x_native",
        })
    return out[:limit]
