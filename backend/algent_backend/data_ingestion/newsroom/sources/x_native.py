"""
X discovery via the native X API v2 — primary t0 X channel (sparse / cost-aware).

Same data plane as X's hosted MCP (``api.x.com/mcp``). Headless REST + app Bearer.

**Three legs (not one overfit domain menu):**
  1. **General News** (``GET /2/news/search``) — platform-clustered *any-topic* stories.
  2. **General aggregators** — tiny cross-topic wires (Mario Nawfal–class), not labs.
  3. **AI pulse** (dedicated) — main labs (US/CN/open-source), key people, AI media.
     Intentionally separate so general discovery is *not* AI-primary, while we still
     keep eyeballs on releases and lab moves. Efficient ``from:`` recent-search batches
     (not one timeline per account).

Rejected: WOEID trends (fandom noise). Domain rosters as the *only* channel. Huge follow lists.

Cost: News story metadata is not billed as post bodies. Aggregator timelines and AI
``from:`` searches bill ~$0.005/post. Cap hard via ``ALGENT_X_MAX_POSTS``.
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
_USD_PER_NEWS_REQUEST = 0.0

_TOKEN_ENV_CANDIDATES = (
    "X_BEARER_TOKEN", "X_BEARER_KEY", "TWITTER_BEARER_TOKEN", "X_API_BEARER_TOKEN",
    "X_BEARER", "BEARER_TOKEN",
)

_MAX_STORIES_ENV = "ALGENT_X_MAX_TOPICS"   # max total hits across all legs
_MAX_POSTS_ENV = "ALGENT_X_MAX_POSTS"       # post bodies (aggs + AI + fallback)
_NEWS_AGE_ENV = "ALGENT_X_NEWS_MAX_AGE_H"
_NEWS_SEEDS_ENV = "ALGENT_X_NEWS_SEEDS"
_USE_NEWS_ENV = "ALGENT_X_USE_NEWS"
_USE_AGGS_ENV = "ALGENT_X_USE_AGGREGATORS"
_AGGS_ENV = "ALGENT_X_AGGREGATORS"
_AGGS_PER_ENV = "ALGENT_X_AGGREGATOR_POSTS"
_USE_AI_ENV = "ALGENT_X_USE_AI_PULSE"       # default on — dedicated AI eyeballs
_AI_ACCOUNTS_ENV = "ALGENT_X_AI_ACCOUNTS"  # comma handles; overrides default roster
_AI_NEWS_SEEDS_ENV = "ALGENT_X_AI_NEWS_SEEDS"
_AI_MAX_POSTS_ENV = "ALGENT_X_AI_MAX_POSTS"  # soft cap within the shared post budget

# Topic-agnostic general seeds — open the News index without scripting a domain menu.
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
_DEFAULT_AGGREGATORS = (
    "MarioNawfal",
    "spectatorindex",
    "Disclosetv",
    "visegrad24",
)

# Dedicated AI pulse: labs (US + CN + open), people, AI media. Not used for *general*
# discovery quality — only this leg. Handles are replaceable via env.
# role: lab | person | media
_DEFAULT_AI_ACCOUNTS: tuple[tuple[str, str], ...] = (
    # ── Labs / orgs ──────────────────────────────────────────────────────────
    ("OpenAI", "lab"),
    ("AnthropicAI", "lab"),
    ("GoogleDeepMind", "lab"),
    ("xai", "lab"),
    ("AIatMeta", "lab"),
    ("MistralAI", "lab"),
    ("Cohere", "lab"),
    ("StabilityAI", "lab"),
    ("huggingface", "lab"),
    ("DeepSeek_AI", "lab"),
    ("Alibaba_Qwen", "lab"),
    ("MoonshotAI", "lab"),
    ("MiniMax_AI", "lab"),
    ("perplexity_ai", "lab"),
    ("midjourney", "lab"),
    ("EleutherAI", "lab"),
    ("togethercompute", "lab"),
    ("Scale_AI", "lab"),
    ("CharacterAI", "lab"),
    ("inflectionAI", "lab"),
    # ── People ───────────────────────────────────────────────────────────────
    ("sama", "person"),
    ("DarioAmodei", "person"),
    ("karpathy", "person"),
    ("elonmusk", "person"),       # noisy — AI-keyword filter applied
    ("demishassabis", "person"),
    ("ylecun", "person"),
    ("AndrewYNg", "person"),
    ("clementdelangue", "person"),
    ("jimfan", "person"),
    ("fchollet", "person"),
    ("hardmaru", "person"),
    ("emollick", "person"),
    ("mustafasuleyman", "person"),
    ("swyx", "person"),
    ("rowancheung", "person"),
    # ── AI media / analysts ──────────────────────────────────────────────────
    ("ArtificialAnlys", "media"),
    ("TeortaxesTex", "media"),
)

# High-volume accounts: only keep posts that look AI-related.
_NOISY_AI_HANDLES = frozenset({"elonmusk"})
_AI_SIGNAL_RE = re.compile(
    r"\b(ai|agi|llm|gpt|grok|claude|gemini|deepseek|openai|anthropic|mistral|"
    r"model|models|neural|training|inference|gpu|agent|agents|xai|robot|"
    r"superintelligence|alignment|scaling|transformer|diffusion|multimodal)\b",
    re.I,
)

# Platform News seeds that open AI story clusters (cheap — not posts).
_DEFAULT_AI_NEWS_SEEDS = (
    "artificial intelligence",
    "OpenAI",
    "LLM",
)

_JUNK_TOPICS = frozenset({
    "relationships", "celebrity", "entertainment", "sports", "gaming",
    "memes", "travel", "fashion", "music",
})
_JUNK_CATEGORIES = frozenset({"entertainment", "sports"})

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


def resolve_ai_accounts() -> tuple[tuple[str, str], ...]:
    """(handle, role) pairs for the dedicated AI pulse."""
    raw = os.environ.get(_AI_ACCOUNTS_ENV, "")
    if raw.strip().lower() in ("none", "off", "0"):
        return ()
    if raw.strip():
        # env list has no roles — treat as lab (generic pulse)
        return tuple((s.strip().lstrip("@"), "lab") for s in raw.split(",") if s.strip())
    if not _ai_pulse_enabled():
        return ()
    return _DEFAULT_AI_ACCOUNTS


def resolve_ai_news_seeds() -> tuple[str, ...]:
    raw = os.environ.get(_AI_NEWS_SEEDS_ENV, "")
    if raw.strip().lower() in ("none", "off", "0"):
        return ()
    if raw.strip():
        return tuple(s.strip() for s in raw.split(",") if s.strip())
    return _DEFAULT_AI_NEWS_SEEDS


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


def _ai_pulse_enabled() -> bool:
    return os.environ.get(_USE_AI_ENV, "1").strip().lower() not in ("0", "false", "no", "off")


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
    """X-native discovery: general News + general wires + dedicated AI pulse.

    General legs stay domain-agnostic. AI is a separate reserved slice so releases
    and lab moves still surface without making t0 "the AI channel."
    """
    if not resolve_bearer() and client is None:
        _record_cost()
        return []

    # Slightly larger default so three legs each get airtime.
    story_cap = max_stories if max_stories is not None else _int_env(_MAX_STORIES_ENV, 24, lo=1, hi=50)
    # ~$0.14 — aggs need min-5 timelines; AI uses efficient from: batches.
    post_budget = max_posts if max_posts is not None else _int_env(_MAX_POSTS_ENV, 28, lo=0, hi=100)
    age_h = _int_env(_NEWS_AGE_ENV, 48, lo=1, hi=720)
    posts_per_agg = _int_env(_AGGS_PER_ENV, 3, lo=1, hi=10)
    ai_post_soft = _int_env(_AI_MAX_POSTS_ENV, 12, lo=0, hi=50)

    hits: list[dict[str, Any]] = []
    news_reqs = 0
    search_reqs = 0
    timeline_reqs = 0
    posts_fetched = 0
    modes: list[str] = []

    aggs = resolve_aggregators() if post_budget > 0 else ()
    ai_accounts = resolve_ai_accounts()
    ai_on = _ai_pulse_enabled() and (bool(ai_accounts) or bool(resolve_ai_news_seeds()))

    # Reserve slots so News cannot starve wires / AI, and AI cannot monopolize.
    reserved_ai = min(story_cap // 4, 8) if ai_on else 0
    reserved_agg = 0
    if aggs:
        reserved_agg = min(
            story_cap // 4,
            len(aggs) * posts_per_agg,
            max(0, story_cap // 3),
        )
        reserved_agg = max(reserved_agg, min(4, story_cap // 3)) if post_budget else 0
    # Leave at least ~40% of slots for general News when all three are on.
    while reserved_ai + reserved_agg > story_cap * 0.6 and (reserved_ai or reserved_agg):
        if reserved_agg >= reserved_ai and reserved_agg:
            reserved_agg -= 1
        elif reserved_ai:
            reserved_ai -= 1
        else:
            break
    news_cap = max(1, story_cap - reserved_ai - reserved_agg)

    # ── 1. General X News ────────────────────────────────────────────────────
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
            except Exception:  # noqa: BLE001
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

    # Split post budget: AI gets a soft share; aggregators take the rest first
    # (timelines are chunkier), AI fills remaining with efficient from: search.
    if ai_on and aggs and post_budget:
        agg_post_budget = max(0, post_budget - min(ai_post_soft, post_budget // 2 + 1))
        # Leave at least some room for AI when both on
        agg_post_budget = min(agg_post_budget, max(0, post_budget - min(10, ai_post_soft)))
    elif aggs:
        agg_post_budget = post_budget
    else:
        agg_post_budget = 0

    # ── 2. General aggregators ───────────────────────────────────────────────
    remaining_slots = max(0, story_cap - reserved_ai - len(hits))
    if remaining_slots and agg_post_budget and aggs:
        try:
            agg_hits, n_posts, n_tl = _fetch_aggregators(
                handles=aggs,
                posts_per=posts_per_agg,
                max_posts=agg_post_budget,
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

    hits = _dedupe_hits(hits)
    # Keep room for AI reserved slots when present
    general_keep = max(0, story_cap - reserved_ai)
    if len(hits) > general_keep:
        hits = hits[:general_keep]

    # ── 3. Dedicated AI pulse (News seeds + lab/person from: search) ─────────
    remaining_slots = max(0, story_cap - len(hits))
    remaining_posts = max(0, post_budget - posts_fetched)
    if ai_on and remaining_slots:
        try:
            ai_hits, n_posts, n_news, n_search = _fetch_ai_pulse(
                accounts=ai_accounts,
                news_seeds=resolve_ai_news_seeds() if _news_enabled() else (),
                max_age_hours=age_h,
                max_posts=min(remaining_posts, ai_post_soft),
                max_hits=remaining_slots,
                client=client,
            )
            posts_fetched += n_posts
            news_reqs += n_news
            search_reqs += n_search
            hits.extend(ai_hits)
            if ai_hits:
                modes.append("ai_pulse")
        except Exception:  # noqa: BLE001
            pass

    hits = _dedupe_hits(hits)[:story_cap]

    # ── 4. Speech-act fallback only if everything empty ──────────────────────
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
    """Pull a few recent original posts from general news-wire accounts."""
    hits: list[dict[str, Any]] = []
    posts_fetched = 0
    timeline_reqs = 0
    per_handle: dict[str, list[dict[str, Any]]] = {}

    for handle in handles:
        if posts_fetched >= max_posts:
            break
        if posts_fetched > 0 and posts_fetched + 5 > max_posts:
            break
        try:
            uid = _user_id(handle, client=client)
        except Exception:  # noqa: BLE001
            continue
        if not uid:
            continue
        try:
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


def _fetch_ai_pulse(
    *,
    accounts: tuple[tuple[str, str], ...],
    news_seeds: tuple[str, ...],
    max_age_hours: int,
    max_posts: int,
    max_hits: int,
    client: object | None,
) -> tuple[list[dict[str, Any]], int, int, int]:
    """Dedicated AI eyeballs: AI News stories + sparse from: lab/person search.

    Uses batched ``from:a OR from:b`` recent-search (one request covers many
    accounts) instead of per-account timelines — far cheaper for a ~30-handle roster.
    """
    hits: list[dict[str, Any]] = []
    posts_fetched = 0
    news_reqs = 0
    search_reqs = 0
    role_by = {h.casefold(): role for h, role in accounts}

    # AI-specific News clusters (story objects — no post bill).
    for seed in news_seeds:
        if len(hits) >= max_hits:
            break
        try:
            stories = _search_news(
                seed, max_results=min(5, max_hits - len(hits)),
                max_age_hours=max_age_hours, client=client,
            )
            news_reqs += 1
        except Exception:  # noqa: BLE001
            stories = []
        for s in stories:
            if not (_news_story_usable(s) or _ai_news_story_usable(s)):
                continue
            h = _news_hit(s, seed=f"ai:{seed}")
            h["source"] = "x_ai_pulse"
            h["lane"] = f"ai_news:{s.get('category') or 'general'}"
            hits.append(h)
            if len(hits) >= max_hits:
                break

    # Account pulse via from: OR batches (posts bill).
    remaining_posts = max(0, max_posts - posts_fetched)
    remaining_hits = max(0, max_hits - len(hits))
    if accounts and remaining_posts >= 10 and remaining_hits:
        handles = [h for h, _ in accounts]
        # ~8 handles per query keeps under typical query-length limits.
        chunk_size = 8
        for i in range(0, len(handles), chunk_size):
            if posts_fetched >= max_posts or len(hits) >= max_hits:
                break
            chunk = handles[i : i + chunk_size]
            take = min(10, max_posts - posts_fetched, max(10, remaining_hits))
            if take < 10 and max_posts - posts_fetched < 10:
                break
            q = "(" + " OR ".join(f"from:{h}" for h in chunk) + ") -is:retweet -is:reply"
            try:
                posts = _recent_search(q, limit=take, client=client)
                search_reqs += 1
            except Exception:  # noqa: BLE001
                posts = []
            posts_fetched += len(posts)
            for p in posts:
                author = str(p.get("author") or "")
                role = role_by.get(author.casefold(), "lab")
                if not _ai_post_usable(p, role=role):
                    continue
                hits.append(_post_hit(p, lane=f"ai:{role}:{author}", source="x_ai_pulse"))
                if len(hits) >= max_hits:
                    break

    return hits[:max_hits], posts_fetched, news_reqs, search_reqs


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
    if cat == "other" and lowered and not (lowered & {"news", "politics", "crime"}):
        return False
    return True


def _ai_news_story_usable(story: dict[str, Any]) -> bool:
    """Looser gate for the AI News seeds — tech/product clusters are fine."""
    name = str(story.get("name") or story.get("hook") or story.get("summary") or "")
    if len(name.strip()) < 12:
        return False
    if _MEME_NAME_RE.search(name):
        return False
    cat = str(story.get("category") or "").strip().casefold()
    if cat in _JUNK_CATEGORIES:
        return False
    blob = name + " " + str(story.get("summary") or "")
    return bool(_AI_SIGNAL_RE.search(blob)) or "ai" in blob.casefold()


def _aggregator_post_usable(post: dict[str, Any]) -> bool:
    text = str(post.get("text") or "").strip()
    if len(text) < 40:
        return False
    if text.count("http") >= 1 and len(text) < 60:
        return False
    return True


def _ai_post_usable(post: dict[str, Any], *, role: str) -> bool:
    text = str(post.get("text") or "").strip()
    if len(text) < 30:
        return False
    author = str(post.get("author") or "").casefold()
    # Lab + media posts are inherently on-beat; people may wander.
    if author in _NOISY_AI_HANDLES or role == "person":
        if author in _NOISY_AI_HANDLES and not _AI_SIGNAL_RE.search(text):
            return False
        # Non-noisy people: keep most posts (they are the pulse); only drop pure fluff short takes
        if len(text) < 50 and text.count("http") and not _AI_SIGNAL_RE.search(text):
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
    return {
        "topic": name or f"X news {rid[:12]}",
        "summary": summary[:400] or name,
        "urls": [],
        "lane": f"news:{category or 'general'}",
        "source": "x_news",
        "author": "",
        "likes": 0,
        "reposts": 0,
        "news_id": rid,
        "category": category,
        "pre_vetted": False,
        "seed": seed,
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
