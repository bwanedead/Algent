"""
X discovery via the native X API v2 — primary t0 X channel (sparse / cost-aware).

Same data plane as X's hosted MCP (``api.x.com/mcp``). Headless REST + app Bearer.

**Goal:** funnel significant *X-native* developments into discovery without overfitting
to a domain (AI, sports, …) or a huge account roster.

**Default strategy (two legs, both general):**
  1. **X News** (``GET /2/news/search``) — platform-clustered stories (headline + summary
     + category). Topic-agnostic seeds open the index; X decides what is a "story".
  2. **General aggregators** — a *tiny* list of cross-topic news wires on X
     (e.g. MarioNawfal, SpectatorIndex, DiscloseTV). Not domain notables; they
     rebroadcast "main stuff" that often lives only there. Sparse post budget.

Rejected: WOEID trends (fandom noise), AI/lab rosters, large follow lists.

Cost: News story metadata is not billed as post bodies. Aggregator timelines
pull a few posts each (~$0.005/post). Cap hard via ``ALGENT_X_MAX_POSTS``.
"""

from __future__ import annotations

import os
import re
from typing import Any

_RECENT_SEARCH = "https://api.x.com/2/tweets/search/recent"
_NEWS_SEARCH = "https://api.x.com/2/news/search"
_USER_BY_USERNAME = "https://api.x.com/2/users/by/username/{username}"
_USER_TWEETS = "https://api.x.com/2/users/{id}/tweets"
_TIMEOUT_S = 25.0

_USD_PER_POST = 0.005
# News story objects are not post bodies; treat as free of per-post billing until proven otherwise.
_USD_PER_NEWS_REQUEST = 0.0

_TOKEN_ENV_CANDIDATES = (
    "X_BEARER_TOKEN", "X_BEARER_KEY", "TWITTER_BEARER_TOKEN", "X_API_BEARER_TOKEN",
    "X_BEARER", "BEARER_TOKEN",
)

_MAX_STORIES_ENV = "ALGENT_X_MAX_TOPICS"   # max total hits (news + aggregators)
_MAX_POSTS_ENV = "ALGENT_X_MAX_POSTS"       # post bodies from aggregators / fallback
_NEWS_AGE_ENV = "ALGENT_X_NEWS_MAX_AGE_H"  # hours (default 48)
_NEWS_SEEDS_ENV = "ALGENT_X_NEWS_SEEDS"    # comma seed queries
_USE_NEWS_ENV = "ALGENT_X_USE_NEWS"        # default on
_USE_AGGS_ENV = "ALGENT_X_USE_AGGREGATORS"  # default on
_AGGS_ENV = "ALGENT_X_AGGREGATORS"         # comma handles without @
_AGGS_PER_ENV = "ALGENT_X_AGGREGATOR_POSTS"  # posts per aggregator account

# Topic-agnostic seeds: open the News index without scripting a domain menu.
# Avoid bare "breaking" — it heavily matches viral/social noise on X.
_DEFAULT_NEWS_SEEDS = (
    "war",
    "government",
    "election",
    "economy",
    "court",
    "military",
    "policy",
    "science",
    "diplomacy",
    "strike",
)

# Cross-topic news aggregators on X — general wires, not vertical domain lists.
# Env can replace entirely (ALGENT_X_AGGREGATORS=handle1,handle2) or disable (none/off).
_DEFAULT_AGGREGATORS = (
    "MarioNawfal",
    "spectatorindex",
    "Disclosetv",
    "visegrad24",
)

# Soft drop: News stories that are pure platform culture noise (not "main stuff").
_JUNK_TOPICS = frozenset({
    "relationships", "celebrity", "entertainment", "sports", "gaming",
    "memes", "travel", "fashion", "music",
})
_JUNK_CATEGORIES = frozenset({"entertainment", "sports"})

# Fallback recent-search if News + aggregators empty — still no account roster.
_FALLBACK_SEARCH = (
    '(announces OR announced OR confirms OR confirmed OR "said today" OR "press conference" '
    'OR "has ordered" OR "has approved" OR "has banned") -is:retweet -is:reply lang:en'
)

_LAST_COST: dict[str, Any] = {
    "posts_fetched": 0,
    "trend_requests": 0,
    "news_requests": 0,
    "search_requests": 0,
    "user_timeline_requests": 0,
    "topics": 0,
    "estimated_usd": 0.0,
    "mode": "news",
}


def last_cost() -> dict[str, Any]:
    return dict(_LAST_COST)


def resolve_bearer() -> str | None:
    try:
        from algent_backend.config import get_service_api_key
        tok = get_service_api_key("x")
        if tok:
            return tok
    except Exception:  # noqa: BLE001
        pass
    for name in _TOKEN_ENV_CANDIDATES:
        if os.environ.get(name):
            return os.environ[name]
    return None


def resolve_news_seeds() -> tuple[str, ...]:
    raw = os.environ.get(_NEWS_SEEDS_ENV, "")
    if raw.strip().lower() in ("none", "off", "0"):
        return ()
    if raw.strip():
        return tuple(s.strip() for s in raw.split(",") if s.strip())
    return _DEFAULT_NEWS_SEEDS


def resolve_aggregators() -> tuple[str, ...]:
    raw = os.environ.get(_AGGS_ENV, "")
    if raw.strip().lower() in ("none", "off", "0"):
        return ()
    if raw.strip():
        return tuple(s.strip().lstrip("@") for s in raw.split(",") if s.strip())
    if not _aggregators_enabled():
        return ()
    return _DEFAULT_AGGREGATORS


def _int_env(name: str, default: int, *, lo: int, hi: int) -> int:
    try:
        n = int(os.environ.get(name, default))
    except ValueError:
        n = default
    return max(lo, min(n, hi))


def _news_enabled() -> bool:
    return os.environ.get(_USE_NEWS_ENV, "1").strip().lower() not in ("0", "false", "no", "off")


def _aggregators_enabled() -> bool:
    return os.environ.get(_USE_AGGS_ENV, "1").strip().lower() not in ("0", "false", "no", "off")


def _record_cost(
    *,
    posts: int = 0,
    news_reqs: int = 0,
    search_reqs: int = 0,
    timeline_reqs: int = 0,
    topics: int = 0,
    mode: str = "news",
) -> float:
    usd = posts * _USD_PER_POST + news_reqs * _USD_PER_NEWS_REQUEST
    _LAST_COST.update({
        "posts_fetched": posts,
        "trend_requests": 0,
        "news_requests": news_reqs,
        "search_requests": search_reqs,
        "user_timeline_requests": timeline_reqs,
        "topics": topics,
        "estimated_usd": round(usd, 6),
        "usd_per_post": _USD_PER_POST,
        "mode": mode,
    })
    try:
        from algent_backend.agent_system.foundation import cost as run_cost
        if run_cost.is_active() and usd > 0:
            run_cost.add(usd)
    except Exception:  # noqa: BLE001
        pass
    return usd


def fetch_x_api_discovery(
    *,
    max_stories: int | None = None,
    max_posts: int | None = None,
    client: object | None = None,
) -> list[dict[str, Any]]:
    """X-native discovery: News stories + sparse general aggregators.

    No trends lists. No domain rosters. Caps volume and post pull hard.
    """
    if not resolve_bearer() and client is None:
        _record_cost()
        return []

    story_cap = max_stories if max_stories is not None else _int_env(_MAX_STORIES_ENV, 20, lo=1, hi=50)
    # Default 20 posts ≈ $0.10 — X user-timeline min is 5/req, so 4 wires need ~20.
    post_budget = max_posts if max_posts is not None else _int_env(_MAX_POSTS_ENV, 20, lo=0, hi=100)
    age_h = _int_env(_NEWS_AGE_ENV, 48, lo=1, hi=720)
    posts_per_agg = _int_env(_AGGS_PER_ENV, 3, lo=1, hi=10)

    hits: list[dict[str, Any]] = []
    news_reqs = 0
    search_reqs = 0
    timeline_reqs = 0
    posts_fetched = 0
    modes: list[str] = []

    # Reserve room for aggregators so News cannot starve the wire leg.
    aggs = resolve_aggregators() if post_budget > 0 else ()
    reserved_agg = 0
    if aggs:
        # ~1/3 of slots or posts_per × accounts, whichever is smaller; leave ≥ half for News.
        reserved_agg = min(
            story_cap // 3,
            len(aggs) * posts_per_agg,
            post_budget,
            max(0, story_cap // 2),
        )
        reserved_agg = max(reserved_agg, min(4, story_cap // 2, post_budget)) if post_budget else 0
    news_cap = max(1, story_cap - reserved_agg) if reserved_agg else story_cap

    # ── 1. X News stories ────────────────────────────────────────────────────
    if _news_enabled():
        seeds = resolve_news_seeds()
        per_seed = max(3, min(8, news_cap // max(1, min(len(seeds), 5)) or 4))
        for seed in seeds:
            if len(hits) >= news_cap:
                break
            try:
                stories = _search_news(
                    seed, max_results=per_seed, max_age_hours=age_h, client=client,
                )
                news_reqs += 1
            except Exception:  # noqa: BLE001 — tier/perm issues fall through
                stories = []
            for s in stories:
                if not _news_story_usable(s):
                    continue
                hits.append(_news_hit(s, seed=seed))
                if len(hits) >= news_cap:
                    break
        if hits:
            modes.append("news")

    hits = _dedupe_hits(hits)[:news_cap]

    # ── 2. General aggregators (Mario Nawfal–class wires) ────────────────────
    remaining_slots = max(0, story_cap - len(hits))
    remaining_posts = max(0, post_budget - posts_fetched)
    if remaining_slots and remaining_posts and aggs:
        try:
            agg_hits, n_posts, n_tl = _fetch_aggregators(
                handles=aggs,
                posts_per=posts_per_agg,
                max_posts=remaining_posts,
                max_hits=remaining_slots,
                client=client,
            )
            posts_fetched += n_posts
            timeline_reqs += n_tl
            hits.extend(agg_hits)
            if agg_hits:
                modes.append("aggregators")
        except Exception:  # noqa: BLE001
            pass

    hits = _dedupe_hits(hits)[:story_cap]

    # ── 3. Speech-act search only if both legs empty ─────────────────────────
    if not hits and post_budget >= 10:
        modes.append("search_fallback")
        try:
            take = min(10, post_budget)
            posts = _recent_search(_FALLBACK_SEARCH, limit=take, client=client)
            search_reqs += 1
            posts_fetched += len(posts)
            hits = [_post_hit(p, lane="probe:news_speech", source="x_api") for p in posts]
        except Exception:  # noqa: BLE001
            hits = []

    mode = "+".join(modes) if modes else "empty"
    usd = _record_cost(
        posts=posts_fetched, news_reqs=news_reqs, search_reqs=search_reqs,
        timeline_reqs=timeline_reqs, topics=len(hits), mode=mode,
    )
    for h in hits:
        h["estimated_usd_run"] = usd
    return hits[:story_cap]


def fetch_x_native(
    *,
    query: str | None = None,
    limit: int = 10,
    client: object | None = None,
) -> list[dict[str, Any]]:
    """CLI probe: News if possible, else recent search (bills posts)."""
    if not resolve_bearer() and client is None:
        _record_cost()
        return []
    q = (query or "government").strip() or "government"
    try:
        stories = _search_news(q, max_results=max(1, min(limit, 100)), max_age_hours=48, client=client)
        hits = [_news_hit(s, seed=q) for s in stories if _news_story_usable(s)]
        if hits:
            _record_cost(news_reqs=1, topics=len(hits), mode="news")
            return hits[:limit]
        # empty/junk → fall through; still count the news attempt
        news_reqs = 1
    except Exception:  # noqa: BLE001
        news_reqs = 0
    posts = _recent_search(query or _FALLBACK_SEARCH, limit=max(10, min(limit, 100)), client=client)
    _record_cost(
        posts=len(posts), news_reqs=news_reqs, search_reqs=1,
        topics=len(posts), mode="search_fallback",
    )
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


def _search_news(
    query: str, *, max_results: int, max_age_hours: int, client: object | None,
) -> list[dict[str, Any]]:
    """Platform news stories (headline/summary/category) — not WOEID trends."""
    # Valid news.fields (live API 2026): id, name, summary, category, hook, keywords,
    # disclaimer, updated_at, cluster_posts_results, contexts.
    resp = _http_get(
        _NEWS_SEARCH,
        {
            "query": query,
            "max_results": max(1, min(int(max_results), 100)),
            "max_age_hours": max(1, min(int(max_age_hours), 720)),
            "news.fields": "id,name,summary,category,hook,keywords,updated_at,contexts",
        },
        client,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"X news HTTP {resp.status_code}: {resp.text[:180]}")
    data = (resp.json() or {}).get("data") or []
    return [row for row in data if isinstance(row, dict)]


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


def _fetch_aggregators(
    *,
    handles: tuple[str, ...],
    posts_per: int,
    max_posts: int,
    max_hits: int,
    client: object | None,
) -> tuple[list[dict[str, Any]], int, int]:
    """Pull a few recent original posts from general news-wire accounts.

    Spreads across handles (round-robin keep) so one loud wire cannot monopolize
    the aggregator slice. X timelines require max_results ≥ 5; we still only
    *keep* ``posts_per`` usable posts per handle.
    """
    hits: list[dict[str, Any]] = []
    posts_fetched = 0
    timeline_reqs = 0
    per_handle: dict[str, list[dict[str, Any]]] = {}

    for handle in handles:
        if posts_fetched >= max_posts:
            break
        # User-timeline max_results minimum is 5; skip further handles if we can't afford it.
        if posts_fetched > 0 and posts_fetched + 5 > max_posts:
            break
        try:
            uid = _user_id(handle, client=client)
        except Exception:  # noqa: BLE001
            continue
        if not uid:
            continue
        try:
            # API floor is 5; we keep only posts_per usable posts below.
            posts = _user_timeline(uid, handle=handle, limit=max(5, posts_per), client=client)
            timeline_reqs += 1
        except Exception:  # noqa: BLE001
            continue
        posts_fetched += len(posts)
        kept: list[dict[str, Any]] = []
        for p in posts:
            if not _aggregator_post_usable(p):
                continue
            kept.append(_post_hit(p, lane=f"agg:{handle}", source="x_aggregator"))
            if len(kept) >= posts_per:
                break
        per_handle[handle] = kept

    # Round-robin merge so Mario / Spectator / Disclose / Visegrad all surface.
    if per_handle:
        depth = max(len(v) for v in per_handle.values())
        for i in range(depth):
            for handle in handles:
                bucket = per_handle.get(handle) or []
                if i < len(bucket):
                    hits.append(bucket[i])
                    if len(hits) >= max_hits:
                        return hits, posts_fetched, timeline_reqs
    return hits, posts_fetched, timeline_reqs


def _user_id(username: str, *, client: object | None) -> str | None:
    resp = _http_get(_USER_BY_USERNAME.format(username=username.lstrip("@")), None, client)
    if resp.status_code != 200:
        return None
    data = (resp.json() or {}).get("data") or {}
    return str(data["id"]) if data.get("id") else None


def _user_timeline(
    user_id: str, *, handle: str, limit: int, client: object | None,
) -> list[dict[str, Any]]:
    resp = _http_get(
        _USER_TWEETS.format(id=user_id),
        {
            "max_results": max(5, min(int(limit), 100)),
            "exclude": "retweets,replies",
            "tweet.fields": "public_metrics,created_at,lang",
        },
        client,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"X timeline HTTP {resp.status_code}: {resp.text[:160]}")
    out: list[dict[str, Any]] = []
    for t in (resp.json() or {}).get("data") or []:
        pm = t.get("public_metrics") or {}
        tid = t.get("id", "")
        out.append({
            "id": tid,
            "text": t.get("text", ""),
            "author": handle,
            "url": f"https://x.com/{handle}/status/{tid}" if handle and tid else "",
            "created_at": t.get("created_at", ""),
            "likes": int(pm.get("like_count") or 0),
            "reposts": int(pm.get("retweet_count") or 0),
        })
    return out


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


_MEME_NAME_RE = re.compile(
    r"\b(meme|memes|comedy|comedic|delights|stuns in|draws divided views|"
    r"dating|girlfriend|boyfriend|broke boys)\b",
    re.I,
)


def _news_story_usable(story: dict[str, Any]) -> bool:
    """Drop pure viral/social noise; keep real news-shaped clusters."""
    name = str(story.get("name") or story.get("hook") or "").strip()
    if len(name) < 12:
        return False
    if _MEME_NAME_RE.search(name):
        return False
    cat = str(story.get("category") or "").strip().casefold()
    if cat in _JUNK_CATEGORIES:
        return False
    contexts = story.get("contexts") or {}
    topics = contexts.get("topics") if isinstance(contexts, dict) else None
    lowered: set[str] = set()
    if isinstance(topics, list) and topics:
        lowered = {str(t).casefold() for t in topics}
        serious = lowered & {
            "news", "politics", "business & finance", "business", "finance",
            "elections", "crime", "science", "health", "technology", "world",
            "religion", "islam", "war", "military",
        }
        if not serious and lowered <= _JUNK_TOPICS:
            return False
        if lowered <= {"relationships", "celebrity", "memes"}:
            return False
    # Category "Other" with only soft topics is usually viral culture, not main stuff.
    if cat == "other" and lowered and not (lowered & {"news", "politics", "crime"}):
        return False
    return True


def _aggregator_post_usable(post: dict[str, Any]) -> bool:
    text = str(post.get("text") or "").strip()
    if len(text) < 40:
        return False
    # Drop pure link dumps / engagement bait with almost no text
    if text.count("http") >= 1 and len(text) < 60:
        return False
    return True


def _news_hit(story: dict[str, Any], *, seed: str) -> dict[str, Any]:
    name = str(story.get("name") or story.get("hook") or "").strip()
    summary = str(story.get("summary") or story.get("hook") or "").strip()
    rid = str(story.get("id") or story.get("rest_id") or "")
    category = str(story.get("category") or "").strip()
    keywords = story.get("keywords") or []
    if isinstance(keywords, list):
        kw = ", ".join(str(k) for k in keywords[:8])
    else:
        kw = ""
    bits = [b for b in (category, f"seed:{seed}" if seed else "", kw) if b]
    return {
        "topic": name or f"X news {rid[:12]}",
        "summary": summary[:400] or name,
        "urls": [],  # story-level; no post bill
        "lane": f"news:{category or 'general'}",
        "source": "x_news",
        "author": "",
        "likes": 0,
        "reposts": 0,
        "news_id": rid,
        "category": category,
        "pre_vetted": False,
    }


def _dedupe_hits(hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    best: dict[str, dict[str, Any]] = {}
    for h in hits:
        key = (
            h.get("news_id")
            or (h.get("urls") or [None])[0]
            or h.get("topic")
            or ""
        )
        key = str(key).casefold()
        if not key:
            continue
        if key not in best:
            best[key] = h
    return list(best.values())


_WS = re.compile(r"\s+")


def _post_hit(post: dict[str, Any], *, lane: str, source: str) -> dict[str, Any]:
    text = _WS.sub(" ", str(post.get("text") or "")).strip()
    author = str(post.get("author") or "").strip()
    lead = text[:100] + ("…" if len(text) > 100 else "")
    topic = f"@{author}: {lead}" if author and lead else (lead or f"x post {post.get('id', '')}")
    return {
        "topic": topic,
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
