"""
X discovery via the native X API v2 — primary t0 X channel (sparse / cost-aware).

Same data plane as X's hosted MCP (``api.x.com/mcp``). The pipeline uses REST with an
app-only Bearer so t0 stays headless.

**Default strategy (cheap wide net):**
  1. Pull **trends** for a few locations (worldwide + US) — topic *names*, not posts.
  2. Cap at ~30 pool items (topic seeds for synthesis).
  3. **Do not hydrate posts by default** — posts are the billable unit (~$0.005 each).
  4. Optional: hydrate only the top K trends with a tiny post budget (hard-capped).

Grok CLI remains an optional supplement (``x_grok_cli``), never the default.
"""

from __future__ import annotations

import os
import re
from typing import Any

_RECENT_SEARCH = "https://api.x.com/2/tweets/search/recent"
_TRENDS = "https://api.x.com/2/trends/by/woeid/{woeid}"
_TIMEOUT_S = 25.0

# Pay-per-use post read estimate (guardrail; confirm in X console).
_USD_PER_POST = 0.005
# Trends / counts return no post bodies — estimate as free of post-billing.
_USD_PER_TREND_REQUEST = 0.0

_TOKEN_ENV_CANDIDATES = (
    "X_BEARER_TOKEN", "X_BEARER_KEY", "TWITTER_BEARER_TOKEN", "X_API_BEARER_TOKEN",
    "X_BEARER", "BEARER_TOKEN",
)

# Locations: where attention is ranked — not topic categories.
# 1 = Worldwide, 23424977 = United States (Yahoo WOEID).
_WOEIDS_ENV = "ALGENT_X_TREND_WOEIDS"
_DEFAULT_WOEIDS = (1, 23424977)

_MAX_TOPICS_ENV = "ALGENT_X_MAX_TOPICS"       # pool items from X (default 30)
_MAX_TRENDS_ENV = "ALGENT_X_MAX_TRENDS_PER"  # per location (API max 50)
_HYDRATE_TOP_ENV = "ALGENT_X_HYDRATE_TOP"    # how many top trends get a post search (default 0)
_MAX_POSTS_ENV = "ALGENT_X_MAX_POSTS"        # hard ceiling on posts returned this run (default 20)
_POSTS_PER_ENV = "ALGENT_X_POSTS_PER"        # posts per hydrate call, min 10 API (default 10)

# Module-level ledger for the last discovery call (t0 progress + tests).
_LAST_COST: dict[str, Any] = {
    "posts_fetched": 0,
    "trend_requests": 0,
    "search_requests": 0,
    "topics": 0,
    "estimated_usd": 0.0,
}


def last_cost() -> dict[str, Any]:
    """Cost ledger from the most recent ``fetch_x_api_discovery`` call."""
    return dict(_LAST_COST)


def resolve_bearer() -> str | None:
    """App-only Bearer for X API v2 — same credential family as research ``web_search(source=x)``."""
    try:
        from algent_backend.config import get_service_api_key
        tok = get_service_api_key("x")
        if tok:
            return tok
    except Exception:  # noqa: BLE001 — env fallback is fine offline
        pass
    for name in _TOKEN_ENV_CANDIDATES:
        if os.environ.get(name):
            return os.environ[name]
    return None


def resolve_woeids() -> tuple[int, ...]:
    raw = os.environ.get(_WOEIDS_ENV, "")
    if raw.strip():
        out: list[int] = []
        for part in raw.split(","):
            part = part.strip()
            if part.isdigit():
                out.append(int(part))
        return tuple(out) or _DEFAULT_WOEIDS
    return _DEFAULT_WOEIDS


def _int_env(name: str, default: int, *, lo: int, hi: int) -> int:
    try:
        n = int(os.environ.get(name, default))
    except ValueError:
        n = default
    return max(lo, min(n, hi))


def _record_cost(*, posts: int = 0, trend_reqs: int = 0, search_reqs: int = 0, topics: int = 0) -> float:
    usd = posts * _USD_PER_POST + trend_reqs * _USD_PER_TREND_REQUEST
    _LAST_COST.update({
        "posts_fetched": posts,
        "trend_requests": trend_reqs,
        "search_requests": search_reqs,
        "topics": topics,
        "estimated_usd": round(usd, 6),
        "usd_per_post": _USD_PER_POST,
    })
    # When a run cost meter is active (research), fold in; t0 often has no meter — still logged.
    try:
        from algent_backend.agent_system.foundation import cost as run_cost
        if run_cost.is_active() and usd > 0:
            run_cost.add(usd)
    except Exception:  # noqa: BLE001
        pass
    return usd


def fetch_x_api_discovery(
    *,
    woeids: tuple[int, ...] | None = None,
    max_topics: int | None = None,
    hydrate_top: int | None = None,
    max_posts: int | None = None,
    client: object | None = None,
) -> list[dict[str, Any]]:
    """Sparse wide-net X discovery for t0.

    Default: **trends only** (worldwide + US) → up to ~30 topic seeds, **0 posts**.
    Optional hydrate of the top few trends is hard-capped by ``max_posts``.
    """
    if not resolve_bearer() and client is None:
        _record_cost()
        return []

    places = woeids if woeids is not None else resolve_woeids()
    cap_topics = max_topics if max_topics is not None else _int_env(_MAX_TOPICS_ENV, 30, lo=1, hi=50)
    per_place = _int_env(_MAX_TRENDS_ENV, 20, lo=1, hi=50)
    n_hydrate = hydrate_top if hydrate_top is not None else _int_env(_HYDRATE_TOP_ENV, 0, lo=0, hi=10)
    post_budget = max_posts if max_posts is not None else _int_env(_MAX_POSTS_ENV, 20, lo=0, hi=100)
    posts_per = _int_env(_POSTS_PER_ENV, 10, lo=10, hi=25)  # API min 10 for recent search

    trends: list[dict[str, Any]] = []
    trend_reqs = 0
    for woeid in places:
        try:
            batch = _fetch_trends(woeid, max_trends=per_place, client=client)
            trend_reqs += 1
            for t in batch:
                t = {**t, "woeid": woeid}
                trends.append(t)
        except Exception:  # noqa: BLE001 — one location must not sink X
            continue

    merged = _merge_trends(trends)[:cap_topics]
    hits = [_trend_hit(t) for t in merged]

    posts_fetched = 0
    search_reqs = 0
    if n_hydrate > 0 and post_budget >= 10:
        for t in merged[:n_hydrate]:
            if posts_fetched + 10 > post_budget:
                break
            name = str(t.get("trend_name") or "").strip()
            if not name:
                continue
            try:
                take = min(posts_per, post_budget - posts_fetched)
                if take < 10:
                    break
                posts = _recent_search(
                    f'"{name}" -is:retweet lang:en',
                    limit=take,
                    client=client,
                )
                search_reqs += 1
                posts_fetched += len(posts)
                # Attach best post URLs onto the matching topic hit (still one pool item).
                for h in hits:
                    if h.get("topic") == name:
                        urls = [p["url"] for p in posts if p.get("url")][:3]
                        if urls:
                            h["urls"] = urls
                            h["summary"] = (posts[0].get("text") or h["summary"])[:280]
                            h["likes"] = posts[0].get("likes", 0)
                        break
            except Exception:  # noqa: BLE001
                continue

    usd = _record_cost(
        posts=posts_fetched, trend_reqs=trend_reqs, search_reqs=search_reqs, topics=len(hits),
    )
    for h in hits:
        h["estimated_usd_run"] = usd  # observability on each hit is redundant; ledger is canonical
    return hits


def fetch_x_native(
    *,
    query: str | None = None,
    limit: int = 10,
    client: object | None = None,
) -> list[dict[str, Any]]:
    """Single recent-search probe (CLI / tests). Avoid for t0 — use ``fetch_x_api_discovery``."""
    q = query or '("breaking" OR "just in") -is:retweet lang:en'
    posts = _recent_search(q, limit=max(10, min(limit, 100)), client=client)
    _record_cost(posts=len(posts), search_reqs=1, topics=len(posts))
    return [_post_hit(p, lane="probe", source="x_api") for p in posts]


# ── HTTP ──────────────────────────────────────────────────────────────────────

def _http_get(url: str, params: dict[str, Any] | None, client: object | None) -> Any:
    import httpx

    bearer = resolve_bearer()
    if not bearer and client is None:
        raise RuntimeError(
            "no X bearer token (set X_BEARER_TOKEN / X_BEARER_KEY or service key 'x')"
        )
    own = client is None
    http = client or httpx.Client(
        timeout=_TIMEOUT_S,
        headers={"Authorization": f"Bearer {bearer}"},
    )
    try:
        return http.get(url, params=params or {})  # type: ignore[attr-defined]
    finally:
        if own:
            http.close()  # type: ignore[attr-defined]


def _fetch_trends(woeid: int, *, max_trends: int, client: object | None) -> list[dict[str, Any]]:
    resp = _http_get(
        _TRENDS.format(woeid=woeid),
        {
            "max_trends": max(1, min(max_trends, 50)),
            "trend.fields": "trend_name,tweet_count",
        },
        client,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"X trends HTTP {resp.status_code}: {resp.text[:160]}")
    data = (resp.json() or {}).get("data") or []
    out: list[dict[str, Any]] = []
    for row in data:
        name = str(row.get("trend_name") or "").strip()
        if not name:
            continue
        out.append({
            "trend_name": name,
            "tweet_count": int(row.get("tweet_count") or 0),
        })
    return out


def _recent_search(query: str, *, limit: int, client: object | None) -> list[dict[str, Any]]:
    resp = _http_get(
        _RECENT_SEARCH,
        {
            "query": query,
            "max_results": max(10, min(int(limit), 100)),
            "tweet.fields": "public_metrics,created_at,lang,author_id",
            "expansions": "author_id",
            "user.fields": "username,name,verified",
        },
        client,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"X search HTTP {resp.status_code}: {resp.text[:160]}")
    return _shape_posts(resp.json())


def _shape_posts(payload: dict[str, Any]) -> list[dict[str, Any]]:
    users = {u["id"]: u for u in payload.get("includes", {}).get("users", []) if "id" in u}
    out: list[dict[str, Any]] = []
    for t in payload.get("data") or []:
        u = users.get(t.get("author_id"), {})
        handle = u.get("username", "")
        pm = t.get("public_metrics") or {}
        tid = t.get("id", "")
        out.append({
            "id": tid,
            "text": t.get("text", ""),
            "author": handle,
            "url": (
                f"https://x.com/{handle}/status/{tid}" if handle and tid
                else f"https://x.com/i/web/status/{tid}"
            ),
            "created_at": t.get("created_at", ""),
            "likes": int(pm.get("like_count") or 0),
            "reposts": int(pm.get("retweet_count") or 0),
        })
    return out


def _merge_trends(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Dedupe by name (casefold); keep max tweet_count; sort by volume desc."""
    best: dict[str, dict[str, Any]] = {}
    for r in rows:
        name = str(r.get("trend_name") or "").strip()
        if not name:
            continue
        key = name.casefold()
        prev = best.get(key)
        if prev is None or int(r.get("tweet_count") or 0) > int(prev.get("tweet_count") or 0):
            best[key] = r
    return sorted(best.values(), key=lambda x: int(x.get("tweet_count") or 0), reverse=True)


def _trend_hit(t: dict[str, Any]) -> dict[str, Any]:
    name = str(t.get("trend_name") or "").strip()
    count = int(t.get("tweet_count") or 0)
    woeid = t.get("woeid", "")
    where = "worldwide" if woeid == 1 else f"woeid:{woeid}"
    return {
        "topic": name,
        "summary": f"Trending on X ({where})" + (f" · ~{count:,} posts" if count else ""),
        "urls": [],  # no post bill; synthesis uses the topic name as a seed
        "lane": f"trend:{where}",
        "source": "x_trends",
        "author": "",
        "likes": 0,
        "reposts": 0,
        "tweet_count": count,
        "pre_vetted": False,
    }


_WS = re.compile(r"\s+")


def _post_hit(post: dict[str, Any], *, lane: str, source: str) -> dict[str, Any]:
    text = _WS.sub(" ", str(post.get("text") or "")).strip()
    author = str(post.get("author") or "").strip()
    topic = text[:90] + ("…" if len(text) > 90 else "")
    if author:
        topic = f"@{author}: {topic}" if topic else f"@{author}"
    return {
        "topic": topic or f"x post {post.get('id', '')}",
        "summary": text[:280],
        "urls": [u for u in [post.get("url")] if u],
        "lane": lane,
        "source": source,
        "author": author,
        "likes": post.get("likes", 0),
        "reposts": post.get("reposts", 0),
        "created_at": post.get("created_at", ""),
        "pre_vetted": False,
    }
