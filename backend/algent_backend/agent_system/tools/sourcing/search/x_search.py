"""
X (Twitter) search — recent-post search via the X API v2, behind the web_search `x` channel.

Uses the operator's X bearer token from the credential registry (``X_BEARER_TOKEN``). This is the
direct-API path — no MCP client dependency. X's official hosted MCP (``api.x.com/mcp``) is a
wrapper over this same API; if we ever want its fuller operation surface, it swaps in behind this
seam without the agents changing (they only ever see ``web_search(source="x", ...)``).
"""

from __future__ import annotations

from typing import Any

from algent_backend.config import get_service_api_key

_ENDPOINT = "https://api.x.com/2/tweets/search/recent"
_TIMEOUT_S = 20.0


def x_recent_search(query: str, max_results: int = 10) -> dict[str, Any]:
    """Search recent X posts for ``query``. Returns ``{source, query, results}`` or ``{source, error}``.

    Results are compact: text, author handle, url, timestamp, and engagement — enough for an agent
    to gauge social signal / find primary posts, without flooding the prompt.
    """
    import httpx

    token = get_service_api_key("x")
    if not token:
        return {"source": "x", "error": "no X bearer token configured (set X_BEARER_TOKEN)"}

    params = {
        "query": query,
        "max_results": max(10, min(int(max_results), 100)),  # X requires 10..100
        "tweet.fields": "created_at,public_metrics,lang",
        "expansions": "author_id",
        "user.fields": "username,name,verified",
    }
    try:
        resp = httpx.get(
            _ENDPOINT, params=params,
            headers={"Authorization": f"Bearer {token}"}, timeout=_TIMEOUT_S,
        )
    except Exception as exc:  # noqa: BLE001 — a clean error, never crash the loop
        return {"source": "x", "error": str(exc)[:200]}
    if resp.status_code != 200:
        return {"source": "x", "error": f"X API {resp.status_code}: {resp.text[:180]}"}

    return {"source": "x", "query": query, "results": _shape(resp.json())}


def _shape(payload: dict[str, Any]) -> list[dict[str, Any]]:
    users = {u["id"]: u for u in payload.get("includes", {}).get("users", [])}
    posts = []
    for t in payload.get("data", []):
        u = users.get(t.get("author_id"), {})
        handle = u.get("username", "")
        pm = t.get("public_metrics", {})
        posts.append({
            "text": t.get("text", ""),
            "author": handle,
            "verified": bool(u.get("verified")),
            "url": f"https://x.com/{handle}/status/{t['id']}" if handle and t.get("id") else "",
            "created_at": t.get("created_at", ""),
            "likes": pm.get("like_count"),
            "reposts": pm.get("retweet_count"),
        })
    return posts
