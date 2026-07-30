"""
X discovery via the native X API v2 — primary t0 X channel (sparse / cost-aware).

Same data plane as X's hosted MCP (``api.x.com/mcp``). Headless REST + app Bearer.

**Legs (novelty valve — not a domain overfit menu):**
  1. **General News** — platform story clusters; hydrate 1 cluster post (URL + engagement).
  2. **Novelty probes** — domain-agnostic recent-search (acts + long-tail curiosity/labor),
     ranked client-side by engagement (min_faves operators often unavailable on pay-per-use).
  3. **Wires** — cross-topic aggregators *plus* a small spectrum from: batch (independent /
     OSINT / multi-angle voices — not only one political wire).
  4. **AI pulse** — labs/people + AI News seeds (reserved band, not residual scraps).

Rejected: WOEID trends. Domain rosters as the *only* channel. Huge follow lists.

Cost: News metadata free of per-post billing; hydrated posts + probes + timelines
bill ~$0.005/post. Cap hard via ``ALGENT_X_MAX_POSTS`` (default ~36 ≈ $0.18).
"""

from __future__ import annotations

import json
import os
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from algent_backend.data_ingestion.newsroom.topic_filters import is_non_news_topic, is_sports_text

_RECENT_SEARCH = "https://api.x.com/2/tweets/search/recent"
_NEWS_SEARCH = "https://api.x.com/2/news/search"
_TWEETS_LOOKUP = "https://api.x.com/2/tweets"
_USER_BY_USERNAME = "https://api.x.com/2/users/by/username/{username}"
_USER_TWEETS = "https://api.x.com/2/users/{id}/tweets"
_LIST_TWEETS = "https://api.x.com/2/lists/{id}/tweets"
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
_USE_NOVELTY_ENV = "ALGENT_X_USE_NOVELTY"    # default on — domain-agnostic event probes
_NOVELTY_MAX_ENV = "ALGENT_X_NOVELTY_MAX"  # max novelty posts kept (default 6)
_HYDRATE_MAX_ENV = "ALGENT_X_HYDRATE_MAX"  # max News stories to attach a cluster post to

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
    "discovery",
    "archaeology",
    "physics",
    "biology",
    "diplomacy",
    "strike",
)

# ── X LISTS ─────────────────────────────────────────────────────────────────────────
# A list is a roster somebody else curates and keeps current, so we inherit their
# curation instead of maintaining handles ourselves — the single cheapest way to widen
# this channel. Verified working on this access tier: `GET /2/lists/:id/tweets` returns
# the list timeline.
#
# Three things learned probing it live, which shape how these are chosen:
#
#  1. **Most branded lists are dead.** TechCrunch's public lists are all "Disrupt SF
#     2015"; Reuters has "Davos 2023" and "Tokyo Olympics". A list's existence says
#     nothing about whether anyone still posts to it, so each entry below was checked
#     for recency, not just membership.
#  2. **Staff lists are firehoses, not topic feeds.** "AP Staff" (576 members) led with
#     a baseball score. They carry everything those journalists tweet, so the usual
#     sports/non-news filters and retweet stripping are not optional here.
#  3. **There is no list SEARCH endpoint.** v2 can look a list up by id or enumerate one
#     account's owned/followed lists — it cannot find lists by topic. So topical rosters
#     (AI, science, energy) have to be supplied as ids: paste an ``x.com/i/lists/<id>``
#     URL into ``ALGENT_X_LISTS`` and it is picked up with no code change.
_LISTS_ENV = "ALGENT_X_LISTS"          # comma list of "<list_id>:<label>:<pillar>"
_USE_LISTS_ENV = "ALGENT_X_USE_LISTS"
#: "RT @handle:" is how the API renders an amplification — there is no boolean field for it
#: on this endpoint, so the prefix is the signal.
_RETWEET_OF = re.compile(r"^RT @([A-Za-z0-9_]{1,15}):")

_LIST_FETCH_PER_ENV = "ALGENT_X_LIST_FETCH_PER"  # POSTS BOUGHT per list (default 8)
_LIST_POSTS_ENV = "ALGENT_X_LIST_POSTS"          # hard ceiling on the band's post spend

#: How many posts we BUY from each list. Deliberately expressed as spend rather than as
#: hits kept, because spend is the quantity we control and hits are not.
#:
#: The reason is that the list endpoint cannot filter server-side. Probing it: ``exclude``
#: is rejected outright — the only accepted parameters are ``id``, ``max_results``,
#: ``pagination_token`` and ``post.fields`` — and a baseline sample came back **9 retweets
#: out of 20**. So every retweet, every over-cap post from a prolific member, and every
#: sports item is billed before we discard it, and an earlier version that fetched 2x its
#: target to compensate was simply buying 45% waste on purpose.
#:
#: At ~$0.005/post, 8 posts per list is ~$0.04 per list per run. Three lists ~$0.12, and it
#: yields roughly 4-6 usable hits each. Fewer hits than overfetching bought, for less than
#: half the money — and the missing hits were mostly the retweets anyway.
#: The channel is budgeted around **measured yield per billed post**:
#:
#:     news         free metadata, 12 hits for 0 posts        -> maximise, always on
#:     hydration    turns those free hits into linked leads    -> highest leverage
#:     aggregators  6 hits / 8 posts = 75%                     -> best paid yield
#:     lists        ~1 hit per post now nothing is filtered    -> unique off-wire material
#:     novelty      3 hits / 10 posts, most over 72h old       -> off
#:     spectrum     3 hits / 10-post API floor                 -> off
#:     ai timelines 0 pool hits for ~15 posts                  -> off (news seeds are free)
#:
#: Lists used to yield ~56% because retweets and off-topic posts were dropped after being
#: paid for. They are no longer dropped — t0 collects, synthesis triages — so a bought post
#: is a kept post and this number is simply how many we want per list.
_DEFAULT_LIST_FETCH_PER = 5
_DEFAULT_LIST_POSTS = 18

#: ``(list id, label, pillar)`` — and deliberately EMPTY. This band does nothing until an
#: operator configures it, for two reasons that both came out of trying it.
#:
#: **The obvious seeds were the wrong ones.** The lists that are easiest to find and verify
#: are newsroom staff rosters — "FT journalists", "AP Staff", "The Economist's people". They
#: are live and high-volume, and wiring them makes discovery a projection of exactly the
#: press this newsroom exists to route around. The spectrum roster above was added so
#: discovery is "not only mega-wires + legacy press gravity"; seeding lists from mastheads
#: reinstates that gravity through a side door.
#:
#: **Community lists fix the provenance and not the signal.** Vetted live via
#: ``list_memberships`` on independent voices we already read: all were fresh (newest post
#: under half an hour) and most were unusable — a 4,061-member "interesting people" list
#: running to supplement spam and profit-margin chat, a 497-member geopolitics list carrying
#: unverified strike claims of exactly the kind the claim ledger exists to exclude. Two were
#: genuinely good ("AI Geo & OSINT", 12 members, zero retweets, real first-hand OSINT).
#:
#: Which lists to trust is an editorial judgment with our name on the output, so it belongs
#: to the operator, not to a default baked in by whoever wrote this file. Use
#: ``scout_community_lists`` to find candidates, then set ``ALGENT_X_LISTS``.
_DEFAULT_LISTS: tuple[tuple[str, str, str], ...] = ()


#: Operator-managed roster. A JSON file rather than a constant because this is curation, not
#: code — it changes when editorial judgment changes, and an operator should be able to add a
#: list without opening Python. See ``backend/config/x_lists.json``.
_LISTS_FILE = Path(__file__).resolve().parents[4] / "config" / "x_lists.json"


def _lists_from_file(path: Path | None = None) -> tuple[tuple[str, str, str], ...]:
    """Read the roster file. A missing or malformed file means no lists, never an error."""
    try:
        raw = json.loads((path or _LISTS_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ()
    out: list[tuple[str, str, str]] = []
    for entry in (raw.get("lists") or []) if isinstance(raw, dict) else []:
        if not isinstance(entry, dict) or not entry.get("enabled", True):
            continue
        lid = str(entry.get("id") or "").strip()
        if not lid.isdigit():
            continue
        out.append((lid, str(entry.get("label") or f"list_{lid[:6]}"),
                    str(entry.get("pillar") or "")))
    return tuple(out)


def resolve_lists() -> tuple[tuple[str, str, str], ...]:
    """Lists to read: ``ALGENT_X_LISTS`` if set, else the roster file, else none.

    The env var wins so a run can be pointed at one list for testing without editing the
    roster; the file is the durable record of what we actually read.
    """
    raw = os.environ.get(_LISTS_ENV, "")
    if not raw.strip():
        return _lists_from_file() or _DEFAULT_LISTS
    out: list[tuple[str, str, str]] = []
    for chunk in raw.split(","):
        parts = [p.strip() for p in chunk.split(":") if p.strip()]
        if not parts or not parts[0].isdigit():
            continue
        out.append((parts[0], parts[1] if len(parts) > 1 else f"list_{parts[0][:6]}",
                    parts[2] if len(parts) > 2 else ""))
    return tuple(out) or _lists_from_file() or _DEFAULT_LISTS


def scout_community_lists(
    handles: tuple[str, ...] | None = None, *, per_handle: int = 10,
    client: object | None = None,
) -> list[dict[str, Any]]:
    """Find community-built lists by asking which lists our trusted voices are ON.

    The route matters. ``followed_lists`` would be the natural question — what do these
    accounts choose to follow — but it is **403 on app-only auth**, needing OAuth user
    context we do not have. ``list_memberships`` does work, and answers a subtly different
    and arguably better question: which rosters has the community independently built that
    include this person? Nobody's masthead is involved, and a list holding SEVERAL voices we
    already read is a meaningful quality signal, so results are ranked by exactly that.

    This is a scouting utility, not a per-run step. It costs a lookup and a memberships call
    per handle and hits 429 quickly, and its output is a shortlist for a human to judge —
    live vetting found most community lists unusable despite being perfectly fresh.
    """
    seeds = handles or (resolve_spectrum() + tuple(h for h, _role in resolve_ai_accounts()))
    found: dict[str, dict[str, Any]] = {}

    for handle in seeds:
        try:
            resp = _http_get(_USER_BY_USERNAME.format(username=handle), None, client)
            if resp.status_code != 200:
                continue
            uid = ((resp.json() or {}).get("data") or {}).get("id")
            if not uid:
                continue
            resp = _http_get(
                f"https://api.x.com/2/users/{uid}/list_memberships",
                {"max_results": max(1, min(int(per_handle), 100)),
                 "list.fields": "member_count,follower_count,private,owner_id"},
                client,
            )
            if resp.status_code != 200:
                continue        # 429 is expected here; stop caring, keep what we have
            for lst in ((resp.json() or {}).get("data") or []):
                if lst.get("private"):
                    continue
                lid = str(lst.get("id") or "")
                if not lid:
                    continue
                entry = found.setdefault(lid, {
                    "id": lid, "name": str(lst.get("name") or ""),
                    "members": lst.get("member_count"),
                    "followers": lst.get("follower_count"),
                    "via": [],
                })
                entry["via"].append(handle)
        except Exception:  # noqa: BLE001 — scouting is best-effort by nature
            continue

    # Most overlap first: a list carrying several voices we already read is the signal.
    return sorted(found.values(), key=lambda e: (-len(e["via"]), -(e["members"] or 0)))


def _lists_enabled() -> bool:
    return os.environ.get(_USE_LISTS_ENV, "1").strip().lower() not in ("0", "false", "no", "off")


# Cross-topic news aggregators on X — general wires, not vertical domain lists.
_DEFAULT_AGGREGATORS = (
    "MarioNawfal",
    "spectatorindex",
    "Disclosetv",
    "visegrad24",
)

# Spectrum voices (from: batch, not timelines) — multi-angle primary/OSINT/commentary
# so discovery is not only mega-wires + legacy press gravity. Env: ALGENT_X_SPECTRUM.
_SPECTRUM_ENV = "ALGENT_X_SPECTRUM"
_USE_SPECTRUM_ENV = "ALGENT_X_USE_SPECTRUM"
_DEFAULT_SPECTRUM = (
    "mtracey",           # independent US politics
    "ggreenwald",        # independent / System Update
    "RnaudBertrand",     # non-Western geopolitics angle
    "Osinttechnical",    # OSINT / conflict primary-ish
    "BrunoMacaes",       # geopolitics / Europe-Asia
    "public_citizen",    # progressive regulatory
    "CatoInstitute",     # libertarian policy
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
# Not a product menu: broad AI speech so lab/security/release clusters can surface.
_DEFAULT_AI_NEWS_SEEDS = (
    "artificial intelligence",
    "machine learning",
    "AI agent",
    # Lab names open the News index for whatever those labs are in *today* — not a
    # fixed narrative list (releases, safety, product, etc.).
    "OpenAI",
    "Anthropic",
)

# Domain-agnostic novelty probes — *event morphology*, not celebrity JUST-IN.
# Sports excluded in-query and client-side. Engagement ranked client-side.
_SPORTS_EXCLUDE_Q = (
    '-NBA -NFL -MLB -NHL -UFC -soccer -football -transfer -"Premier League" '
    '-"Champions League" -Barcelona -Messi -LeBron -matchday'
)
_DEFAULT_NOVELTY_PROBES = (
    # Kinetic / diplomatic moves (grain: who did what)
    f'(struck OR sank OR seized OR downed OR "air strike" OR airstrike OR "missile hit" '
    f'OR blockade OR "ceasefire collapsed" OR "talks failed" OR ultimatum OR "peace talks" '
    f'OR "has ordered strikes" OR bombed OR invaded) '
    f"-is:retweet -is:reply lang:en {_SPORTS_EXCLUDE_Q}",
    # Institutional / legal / money ruptures
    f'(indicted OR "ruled that" OR overturned OR sanctioned OR nationalized OR '
    f'"export ban" OR "defaults on" OR "emergency session" OR "has banned" OR '
    f'"central bank" OR "interest rate" OR "declared emergency") '
    f"-is:retweet -is:reply lang:en {_SPORTS_EXCLUDE_Q}",
    # Science / knowledge feats
    f'("for the first time" OR "scientists discover" OR "peer-reviewed" OR breakthrough '
    f'OR archaeology OR fossil OR quantum OR genome OR telescope OR conjecture OR '
    f'"Nature journal" OR "Science journal" OR "has confirmed") '
    f"-is:retweet -is:reply lang:en {_SPORTS_EXCLUDE_Q}",
    # Labor / cost-of-living
    f'(walkout OR "laid off" OR "union vote" OR "cost of living" OR "rent prices" '
    f'OR "mass layoff" OR "plant closed") '
    f"-is:retweet -is:reply lang:en {_SPORTS_EXCLUDE_Q}",
)

_JUNK_TOPICS = frozenset({
    "relationships", "celebrity", "entertainment", "sports", "gaming",
    "memes", "travel", "fashion", "music",
})
_JUNK_CATEGORIES = frozenset({"entertainment", "sports"})

_FALLBACK_SEARCH = (
    '(announces OR announced OR confirms OR confirmed OR "said today" OR "press conference" '
    'OR "has ordered" OR "has approved" OR "has banned") -is:retweet -is:reply lang:en '
    f"{_SPORTS_EXCLUDE_Q}"
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


def resolve_spectrum() -> tuple[str, ...]:
    """Independent / OSINT / multi-angle handles for spectrum from: batch."""
    raw = os.environ.get(_SPECTRUM_ENV, "")
    if raw.strip().lower() in ("none", "off", "0"):
        return ()
    if raw.strip():
        return tuple(s.strip().lstrip("@") for s in raw.split(",") if s.strip())
    # OFF by default: the recent-search API floor is 10 posts, and a live run turned those
    # 10 billed posts into 3 pool items — the worst fixed cost per hit in the channel. The
    # intent (multi-angle independent voices, not one political wire) is right and is now
    # better served by a curated list, which has no 10-post floor. ALGENT_X_USE_SPECTRUM=1.
    if os.environ.get(_USE_SPECTRUM_ENV, "0").strip().lower() in ("0", "false", "no", "off"):
        return ()
    return _DEFAULT_SPECTRUM


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
    """ON — the best measured yield per billed post in the whole channel.

    This was briefly switched off on the argument that four aggregator timelines "returned 2
    pool items", which was a bad reading: 2 was the count that SURVIVED echo suppression and
    cross-channel dedup, not what the leg produced. Measured properly, 8 billed posts yielded
    **6 hits (75%)** against 56% for curated lists — and the material was events rather than
    commentary: Kyiv residents sheltering in subways, Saudi coalition-building, the IRGC
    turning back tankers, X suspending an Iranian state agency.

    The "an aggregator only re-posts the wires" objection does not hold for these accounts
    either; they routinely carry things the wires are slow on or skip. Cheap, fast, and
    high-yield, so it stays on.
    """
    return os.environ.get(_USE_AGGS_ENV, "1").strip().lower() not in ("0", "false", "no", "off")


def _ai_pulse_enabled() -> bool:
    return os.environ.get(_USE_AI_ENV, "1").strip().lower() not in ("0", "false", "no", "off")


def _novelty_enabled() -> bool:
    """OFF by default — the worst value per dollar of any leg, measured.

    Novelty probes are engagement-ranked recent-searches, and engagement accumulates with
    age, so the leg systematically bought the WEEK's most-liked posts rather than the day's
    news. A live pool carried three of them over 72 hours old, the worst at 163 hours, and
    what they returned was commentary ("1948 Arab-Israeli War Arab states started it")
    rather than events. That is ~10 billed posts for material the claim ledger cannot use.
    Curated lists cover the same ground — platform-native, off-wire leads — for the same
    money and with a human maintaining the roster. Set ``ALGENT_X_USE_NOVELTY=1`` to revive.
    """
    return os.environ.get(_USE_NOVELTY_ENV, "0").strip().lower() not in ("0", "false", "no", "off")


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
    """X-native discovery: News (hydrated) + novelty probes + wires + AI pulse.

    Bands are reserved so one leg cannot starve the novelty valve. Cost-capped.
    """
    if not resolve_bearer() and client is None:
        _record_cost()
        return []

    story_cap = max_stories if max_stories is not None else _int_env(_MAX_STORIES_ENV, 36, lo=1, hi=50)
    # ~$0.18 default: hydrate + novelty + spectrum + sparse aggs + AI.
    # 30 posts = ~$0.15, the channel ceiling. Every paid leg draws from THIS, including the
    # lists band, so the number is a real promise rather than a suggestion — it briefly was
    # not, and the measured spend ran to 44 posts against a declared cap of 36.
    post_budget = max_posts if max_posts is not None else _int_env(_MAX_POSTS_ENV, 30, lo=0, hi=100)
    age_h = _int_env(_NEWS_AGE_ENV, 48, lo=1, hi=720)
    # Five, because five is the API floor for a timeline read — asking for 2 bills 5 anyway,
    # so a lower number bought less material for identical money. Naming the real unit is
    # what makes the budget arithmetic below trustworthy.
    posts_per_agg = _int_env(_AGGS_PER_ENV, 5, lo=1, hi=10)
    # ZERO paid posts by default: the AI pulse keeps its FREE news-seed half and drops its
    # paid timeline half. Measured, all 6 of its hits came from news clusters (free), while
    # ~15 billed posts on lab/person timelines produced nothing that reached the pool — and a
    # curated `ai` list now reads those same accounts at 5 posts instead of 15.
    ai_post_soft = _int_env(_AI_MAX_POSTS_ENV, 0, lo=0, hi=50)
    novelty_max = _int_env(_NOVELTY_MAX_ENV, 10, lo=0, hi=20)
    hydrate_max = _int_env(_HYDRATE_MAX_ENV, 6, lo=0, hi=20)

    news_reqs = 0
    search_reqs = 0
    timeline_reqs = 0
    posts_fetched = 0
    modes: list[str] = []

    aggs = resolve_aggregators() if post_budget > 0 else ()
    spectrum = resolve_spectrum() if post_budget > 0 else ()
    ai_accounts = resolve_ai_accounts()
    ai_on = _ai_pulse_enabled() and (bool(ai_accounts) or bool(resolve_ai_news_seeds()))
    novelty_on = _novelty_enabled() and post_budget > 0 and novelty_max > 0
    spectrum_on = bool(spectrum)

    lists_on = _lists_enabled() and bool(resolve_lists()) and post_budget > 0

    # Fixed band sizes so fill order cannot starve novelty/AI/spectrum.
    active = sum(
        1 for on in (_news_enabled(), novelty_on, bool(aggs), spectrum_on, ai_on, lists_on) if on
    ) or 1
    share = max(1, story_cap // active)
    band_news = share if _news_enabled() else 0
    band_nov = min(novelty_max, max(share, 6)) if novelty_on else 0
    band_agg = min(6, max(share, min(4, story_cap))) if aggs else 0
    band_spectrum = min(5, max(3, share)) if spectrum_on else 0
    band_ai = min(6, max(share, min(4, story_cap))) if ai_on else 0
    # Scales with the roster rather than sitting at a fixed 8: the point of configuring three
    # lists is three lists' worth of material, and a flat cap would silently make the 2nd and
    # 3rd list decorative. Bounded at half the story cap so lists cannot become the whole menu.
    band_lists = min(
        max(4, story_cap // 2),
        _int_env(_LIST_FETCH_PER_ENV, _DEFAULT_LIST_FETCH_PER, lo=1, hi=40) * len(resolve_lists()),
    ) if lists_on else 0
    total_b = band_news + band_nov + band_agg + band_spectrum + band_ai + band_lists
    if total_b > story_cap:
        overflow = total_b - story_cap
        for _ in range(overflow):
            if band_news > 2:
                band_news -= 1
            elif band_agg > 2:
                band_agg -= 1
            elif band_ai > 2:
                band_ai -= 1
            elif band_spectrum > 2:
                band_spectrum -= 1
            elif band_nov > 2:
                band_nov -= 1
            elif band_lists > 2:
                band_lists -= 1
            else:
                break

    # Post budget split (hydrate first — makes News usable for rake).
    hydrate_budget = (
        min(hydrate_max, max(0, post_budget // 3)) if (_news_enabled() and hydrate_max) else 0
    )
    # Reserve ≥10 posts for spectrum/novelty when on (recent-search API floor is 10).
    spectrum_budget = 10 if spectrum_on and post_budget - hydrate_budget >= 20 else 0
    novelty_budget = 0
    if novelty_on:
        left_for_nov = max(0, post_budget - hydrate_budget - spectrum_budget)
        novelty_budget = min(max(10, novelty_max + 4), left_for_nov)
        if novelty_budget < 10:
            novelty_budget = 0
    # Lists are RESERVED before the residue is shared out. They ran last and were funded from
    # what remained, so aggregators taking their fill first left lists with 10 of the 15 posts
    # they were configured for — the curated roster, the one thing here an operator actually
    # chose, was the leg absorbing every other leg's appetite.
    #
    # Clamped to what is actually left, which is not a formality: a reservation larger than
    # the whole budget silently zeroed every other leg. With `max_posts=5` and three lists
    # configured, an unclamped reservation of 15 drove the residue negative and the
    # aggregator leg fetched nothing at all.
    unreserved = max(0, post_budget - hydrate_budget - novelty_budget - spectrum_budget)
    lists_budget = min(
        _int_env(_LIST_POSTS_ENV, _DEFAULT_LIST_POSTS, lo=0, hi=200),
        max(5, _int_env(_LIST_FETCH_PER_ENV, _DEFAULT_LIST_FETCH_PER, lo=1, hi=40))
        * len(resolve_lists()),
        # Never take the last of it — a reserved leg that consumes the entire budget is the
        # starvation bug this reservation exists to prevent, just pointing the other way.
        (unreserved * 2) // 3 if aggs else unreserved,
    ) if lists_on else 0

    rest = max(0, unreserved - lists_budget)
    # Aggregators are bounded by their OWN roster, not by the residue. This used to be
    # `rest`, which was harmless only while other legs consumed most of the budget first —
    # switching off novelty, spectrum and the paid AI timelines handed the aggregator leg the
    # entire remainder, and it quietly grew from ~8 posts to ~23. A leg's cost should be a
    # function of what it is asked to read, never of what happens to be left over.
    agg_ceiling = posts_per_agg * len(aggs)
    if ai_on and aggs:
        ai_budget = min(ai_post_soft, max(0, rest // 2))
        agg_budget = min(agg_ceiling, rest - ai_budget)
    elif ai_on:
        ai_budget, agg_budget = min(ai_post_soft, rest), 0
    else:
        ai_budget, agg_budget = 0, min(agg_ceiling, rest)

    band_hits: dict[str, list[dict[str, Any]]] = {
        "news": [], "novelty": [], "aggregators": [], "spectrum": [], "ai_pulse": [],
        "lists": [],
    }

    # ── 1. General X News (+ hydrate cluster posts) ──────────────────────────
    if _news_enabled() and band_news:
        seeds = resolve_news_seeds()
        per_seed = max(3, min(6, band_news // max(1, min(len(seeds), 5)) or 3))
        raw_stories: list[tuple[dict[str, Any], str]] = []
        for seed in seeds:
            if len(raw_stories) >= band_news * 2:
                break
            try:
                stories = _search_news(
                    seed, max_results=per_seed, max_age_hours=age_h, client=client,
                )
                news_reqs += 1
            except Exception:  # noqa: BLE001
                stories = []
            for s in stories:
                if _news_story_usable(s):
                    raw_stories.append((s, seed))
        # Prefer News category / serious topics when packing the band.
        raw_stories.sort(key=lambda pair: (0 if str(pair[0].get("category") or "").lower() == "news" else 1))
        news_hits = [_news_hit(s, seed=seed) for s, seed in raw_stories[: band_news * 2]]
        news_hits = _dedupe_hits(news_hits)[:band_news]
        if hydrate_budget and news_hits:
            n_h, n_posts = _hydrate_news_hits(
                news_hits, max_hydrate=hydrate_budget, client=client,
            )
            posts_fetched += n_posts
            if n_h:
                modes.append("hydrate")
        band_hits["news"] = news_hits
        if news_hits:
            modes.append("news")

    # ── 2. Novelty probes (engagement-ranked, domain-agnostic) ───────────────
    if novelty_on and band_nov and novelty_budget >= 10:
        try:
            nov_hits, n_posts, n_search = _fetch_novelty_probes(
                max_hits=band_nov, max_posts=novelty_budget, client=client,
            )
            posts_fetched += n_posts
            search_reqs += n_search
            band_hits["novelty"] = nov_hits
            if nov_hits:
                modes.append("novelty")
        except Exception:  # noqa: BLE001
            pass

    # ── 3. Aggregators ───────────────────────────────────────────────────────
    if aggs and band_agg and agg_budget > 0:
        try:
            agg_hits, n_posts, n_tl = _fetch_aggregators(
                handles=aggs, posts_per=posts_per_agg,
                max_posts=agg_budget, max_hits=band_agg, client=client,
            )
            posts_fetched += n_posts
            timeline_reqs += n_tl
            band_hits["aggregators"] = agg_hits
            if agg_hits:
                modes.append("aggregators")
        except Exception:  # noqa: BLE001
            pass

    # ── 3b. Spectrum from: batch (multi-angle voices, not wire-only) ──────────
    if spectrum_on and band_spectrum and spectrum_budget >= 10:
        try:
            sp_hits, n_posts, n_search = _fetch_spectrum_batch(
                handles=spectrum, max_hits=band_spectrum, max_posts=spectrum_budget,
                client=client,
            )
            posts_fetched += n_posts
            search_reqs += n_search
            band_hits["spectrum"] = sp_hits
            if sp_hits:
                modes.append("spectrum")
        except Exception:  # noqa: BLE001
            pass

    # ── 4. AI pulse (reserved band — not residual) ───────────────────────────
    if ai_on and band_ai:
        try:
            ai_hits, n_posts, n_news, n_search = _fetch_ai_pulse(
                accounts=ai_accounts,
                news_seeds=resolve_ai_news_seeds() if _news_enabled() else (),
                max_age_hours=age_h,
                max_posts=min(ai_budget, ai_post_soft) if ai_budget else 0,
                max_hits=band_ai,
                client=client,
            )
            posts_fetched += n_posts
            news_reqs += n_news
            search_reqs += n_search
            # Hydrate AI news stories that still lack URLs (cheap, shared budget leftover).
            left = max(0, post_budget - posts_fetched)
            if left and ai_hits:
                n_h, n_p = _hydrate_news_hits(ai_hits, max_hydrate=min(3, left), client=client)
                posts_fetched += n_p
            band_hits["ai_pulse"] = ai_hits[:band_ai]
            if ai_hits:
                modes.append("ai_pulse")
        except Exception:  # noqa: BLE001
            pass

    # ── 5. Curated lists (reserved band) ─────────────────────────────────────
    if lists_on and band_lists:
        try:
            # Bounded by the SHARED budget, not by a private one. A private budget was a cost
            # leak: ``ALGENT_X_MAX_POSTS`` is supposed to be the channel's ceiling, and a leg
            # that spends outside it makes that promise false — the measured total ran to 44
            # posts against a declared cap of 36. Lists are funded first among the paid legs
            # (see the reservation above), so they get a real allocation rather than residue,
            # but they cannot exceed the total.
            lst_hits, n_posts = fetch_list_hits(
                max_hits=band_lists,
                max_posts=lists_budget,
                client=client,
            )
            posts_fetched += n_posts
            band_hits["lists"] = lst_hits[:band_lists]
            if lst_hits:
                modes.append("lists")
        except Exception:  # noqa: BLE001
            pass

    # Merge bands: novelty/spectrum/AI/lists early so synthesis sees the valve first.
    hits: list[dict[str, Any]] = []
    for key in ("novelty", "spectrum", "ai_pulse", "lists", "news", "aggregators"):
        hits.extend(band_hits[key])
    hits = _dedupe_hits(hits)[:story_cap]

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
        h["x_band"] = h.get("source") or "x"
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
            "news.fields": (
                "id,name,summary,category,hook,keywords,updated_at,contexts,"
                "cluster_posts_results"
            ),
        },
        client,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"X news HTTP {resp.status_code}: {resp.text[:180]}")
    data = (resp.json() or {}).get("data") or []
    return [row for row in data if isinstance(row, dict)]


#: How far back a novelty/spectrum search reaches. X's recent-search window is 7 days, and
#: leaving it unbounded was the core stagnation bug: with ``sort_order="relevancy"`` the API
#: returns the most-ENGAGED posts of the week, and engagement accumulates with age, so the
#: ranking is systematically biased toward the same posts on every run. A measured pool
#: carried a post 163 hours old alongside three others over 72 hours.
_SEARCH_WINDOW_H = 24


def _recent_search(query: str, *, limit: int, client: object | None,
                   window_hours: int | None = None) -> list[dict[str, Any]]:
    start = datetime.now(UTC) - timedelta(hours=window_hours or _SEARCH_WINDOW_H)
    resp = _http_get(
        _RECENT_SEARCH,
        {
            "query": query,
            "max_results": max(10, min(int(limit), 100)),
            "tweet.fields": "public_metrics,created_at,lang,author_id",
            "expansions": "author_id",
            "user.fields": "username,name,verified",
            # RECENCY, not relevancy. Relevancy ranks by engagement, which is a proxy for age
            # — the opposite of what a discovery pass wants. The time bound is belt-and-braces:
            # even ranked by recency, an unbounded window lets a quiet query reach back a week.
            "sort_order": "recency",
            "start_time": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
        },
        client,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"X search HTTP {resp.status_code}: {resp.text[:160]}")
    return _shape_posts(resp.json())


def _list_tweets(list_id: str, *, limit: int, client: object | None) -> list[dict[str, Any]]:
    """One list's timeline. Bills as posts read, same as a user timeline."""
    resp = _http_get(
        _LIST_TWEETS.format(id=list_id),
        {
            "max_results": max(5, min(int(limit), 100)),
            "tweet.fields": "public_metrics,created_at,lang,author_id,referenced_tweets",
            # referenced_tweets.id pulls the quoted/retweeted post's TEXT into `includes`,
            # which is what turns '@someone: "interesting"' from an unusable fragment into a
            # lead. Its author too, so the original source is attributable.
            "expansions": "author_id,referenced_tweets.id,referenced_tweets.id.author_id",
            "user.fields": "username,name,verified",
        },
        client,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"X list {list_id} HTTP {resp.status_code}: {resp.text[:160]}")
    return _shape_posts(resp.json())


def fetch_list_hits(
    *, max_hits: int, max_posts: int, client: object | None = None,
    max_age_hours: int = 36,
) -> tuple[list[dict[str, Any]], int]:
    """Curated-list posts as discovery hits. Returns ``(hits, posts_fetched)``.

    **Nothing is filtered here, deliberately.** t0 collects; synthesis triages. That division
    is not just tidiness, it is the economics: the list endpoint cannot filter server-side
    (``exclude`` is rejected; the only accepted parameters are ``id``, ``max_results``,
    ``pagination_token`` and ``post.fields``), so every post is billed the moment it arrives.
    Discarding retweets and off-topic posts *after* paying for them was buying 45% of a
    sample and throwing it away — the cost was already sunk and the triage is free one layer
    down, where the pool's echo suppression, the crystallizer and synthesis all run on it for
    nothing.

    So the only knob that matters is how many posts we BUY (``ALGENT_X_LIST_FETCH_PER``).
    Everything bought is kept, which takes the leg's yield from ~56% to ~100% and makes the
    per-post price the whole cost model.
    """
    lists = resolve_lists()
    if not lists or max_hits <= 0:
        return [], 0

    # What we BUY per list — and, since nothing is filtered, also what we keep.
    per_list = max(5, _int_env(_LIST_FETCH_PER_ENV, _DEFAULT_LIST_FETCH_PER, lo=1, hi=40))
    del max_age_hours   # no age cut here either; the cross-run novelty ledger handles repeats
    fetched = 0

    # Collect per list, then interleave. Filling one shared budget in roster order starves
    # whatever comes last — measured: the first two lists took all 12 slots and the third
    # contributed nothing at all. Every configured list should reach the menu.
    per_list_hits: list[list[dict[str, Any]]] = []
    for list_id, label, pillar in lists:
        if fetched >= max_posts:
            break
        try:
            posts = _list_tweets(list_id, limit=per_list, client=client)
        except Exception:  # noqa: BLE001 — a private or deleted list is one fewer, not an error
            continue
        fetched += len(posts)
        hits = []
        for post in posts:
            text = str(post.get("text") or "").strip()
            if not text:
                continue        # nothing for any downstream stage to read
            author = str(post.get("author") or "")
            # PROVENANCE, not filtering. Nothing is dropped here, so synthesis has to be able
            # to tell what it is reading: which list vouched for the account, whether the
            # account wrote this or merely amplified someone else, and who the original was.
            # A retweet is weaker evidence than a first-hand post but it is not noise — it is
            # a signal about what a curated roster is paying attention to — and that judgment
            # belongs to the stage that can weigh it, not to the collector.
            ref_type = str(post.get("ref_type") or "")
            ref_text = str(post.get("ref_text") or "").strip()
            ref_author = str(post.get("ref_author") or "")
            match = _RETWEET_OF.match(text)
            retweet_of = ref_author or (match.group(1) if match else "")

            # When a post amplifies something, the amplified text usually IS the story and the
            # amplifier's own words are "interesting" or nothing at all. So the summary carries
            # both, attributed — synthesis gets the substance without losing the fact that this
            # reached us second-hand. Without this the item is a fragment nobody can triage.
            summary = text
            if ref_text and ref_text[:60] not in text:
                via = f"@{ref_author}" if ref_author else "original"
                summary = f"{text}\n\n[{ref_type or 'references'} {via}] {ref_text}".strip()

            hits.append({
                "topic": f"@{author}: {(ref_text or text)[:150]}" if author else text[:150],
                "summary": summary,
                "urls": [str(post.get("url") or "")],
                "source": "x_list",
                "lane": f"list:{label}",
                "list_label": label,
                "author": author,
                "is_retweet": bool(ref_type in ("retweeted", "quoted") or match),
                "ref_type": ref_type,
                "retweet_of": retweet_of,
                "created_at": str(post.get("created_at") or ""),
                "likes": post.get("likes"),
                "reposts": post.get("reposts"),
                "pillar": pillar,
            })
        per_list_hits.append(hits)

    return _interleave(per_list_hits, max_hits), fetched


def _interleave(groups: list[list[dict[str, Any]]], limit: int) -> list[dict[str, Any]]:
    """Round-robin across lists so the cap is shared, not claimed by whoever ran first.

    Deduplicated as it goes, because rosters overlap: one prolific account belonged to all
    three configured lists, so the same post arrived three times and spent three slots. The
    first list to carry a post keeps it.
    """
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for rank in range(max((len(g) for g in groups), default=0)):
        for group in groups:
            if rank >= len(group):
                continue
            hit = group[rank]
            key = next((u for u in (hit.get("urls") or []) if u), "") or hit.get("summary", "")
            if key in seen:
                continue
            seen.add(key)
            out.append(hit)
            if len(out) >= limit:
                return out
    return out




def _lookup_tweets(ids: list[str], *, client: object | None) -> list[dict[str, Any]]:
    """Batch post hydrate by id (bills as posts)."""
    clean = [i for i in ids if i][:100]
    if not clean:
        return []
    resp = _http_get(
        _TWEETS_LOOKUP,
        {
            "ids": ",".join(clean),
            "tweet.fields": "public_metrics,created_at,lang,author_id",
            "expansions": "author_id",
            "user.fields": "username,name,verified",
        },
        client,
    )
    if resp.status_code != 200:
        return []
    return _shape_posts(resp.json())


def _cluster_post_ids(story: dict[str, Any], *, limit: int = 3) -> list[str]:
    raw = story.get("cluster_posts_results") or []
    out: list[str] = []
    if not isinstance(raw, list):
        return out
    for row in raw:
        if isinstance(row, dict):
            pid = str(row.get("post_id") or row.get("id") or "")
        else:
            pid = str(row or "")
        if pid and pid not in out:
            out.append(pid)
        if len(out) >= limit:
            break
    return out


def _hydrate_news_hits(
    hits: list[dict[str, Any]], *, max_hydrate: int, client: object | None,
) -> tuple[int, int]:
    """Attach one cluster post URL + engagement to News hits that lack urls.

    Returns (stories_hydrated, posts_fetched).
    """
    if max_hydrate <= 0:
        return 0, 0
    need: list[tuple[dict[str, Any], str]] = []
    for h in hits:
        if h.get("urls"):
            h.pop("_cluster_ids", None)
            continue
        cids = h.get("_cluster_ids") or []
        if not cids:
            continue
        need.append((h, str(cids[0])))
        if len(need) >= max_hydrate:
            break
    if not need:
        for h in hits:
            h.pop("_cluster_ids", None)
        return 0, 0
    posts = _lookup_tweets([pid for _, pid in need], client=client)
    by_id = {str(p.get("id") or ""): p for p in posts}
    hydrated = 0
    for h, pid in need:
        p = by_id.get(pid)
        if p:
            url = p.get("url") or ""
            if url:
                h["urls"] = [url]
            h["likes"] = p.get("likes", 0)
            h["reposts"] = p.get("reposts", 0)
            if p.get("author"):
                h["author"] = p.get("author")
            hydrated += 1
        h.pop("_cluster_ids", None)
    for h in hits:
        h.pop("_cluster_ids", None)
    return hydrated, len(posts)


def _fetch_novelty_probes(
    *, max_hits: int, max_posts: int, client: object | None,
) -> tuple[list[dict[str, Any]], int, int]:
    """Domain-agnostic event + long-tail probes; mix viral head with mid-tail."""
    hits: list[dict[str, Any]] = []
    posts_fetched = 0
    search_reqs = 0
    scored: list[tuple[int, dict[str, Any]]] = []
    for probe in _DEFAULT_NOVELTY_PROBES:
        if posts_fetched + 10 > max_posts:
            break
        try:
            posts = _recent_search(probe, limit=10, client=client)
            search_reqs += 1
        except Exception:  # noqa: BLE001
            posts = []
        posts_fetched += len(posts)
        for p in posts:
            if not _aggregator_post_usable(p):
                continue
            eng = int(p.get("likes") or 0) + 2 * int(p.get("reposts") or 0)
            scored.append((eng, p))
    scored.sort(key=lambda t: t[0], reverse=True)
    # Interleave head (high engagement) with mid-tail so we do not only surface
    # mega-viral accounts — long-tail curiosities stay in the menu.
    head = scored[: max(1, len(scored) // 3)]
    mid = scored[max(1, len(scored) // 3) : max(2, (2 * len(scored)) // 3)]
    mixed: list[tuple[int, dict[str, Any]]] = []
    for i in range(max(len(head), len(mid))):
        if i < len(head):
            mixed.append(head[i])
        if i < len(mid):
            mixed.append(mid[i])
    seen_text: set[str] = set()
    per_author: dict[str, int] = {}
    for _eng, p in mixed:
        if len(hits) >= max_hits:
            break
        text = str(p.get("text") or "")
        if is_non_news_topic(text):
            continue
        key = text[:80].casefold()
        if key in seen_text:
            continue
        author = str(p.get("author") or "").casefold()
        if author and per_author.get(author, 0) >= 1:
            continue
        seen_text.add(key)
        if author:
            per_author[author] = per_author.get(author, 0) + 1
        hits.append(_post_hit(p, lane="novelty:event", source="x_novelty"))
    return hits, posts_fetched, search_reqs


def _fetch_spectrum_batch(
    *,
    handles: tuple[str, ...],
    max_hits: int,
    max_posts: int,
    client: object | None,
) -> tuple[list[dict[str, Any]], int, int]:
    """One or two from: OR batches across spectrum voices — multi-angle, cheap."""
    if max_posts < 10 or not handles:
        return [], 0, 0
    posts_fetched = 0
    search_reqs = 0
    scored: list[tuple[int, dict[str, Any]]] = []
    chunk_size = 7
    for i in range(0, len(handles), chunk_size):
        if posts_fetched + 10 > max_posts:
            break
        chunk = handles[i : i + chunk_size]
        q = "(" + " OR ".join(f"from:{h}" for h in chunk) + ") -is:retweet -is:reply"
        try:
            posts = _recent_search(q, limit=10, client=client)
            search_reqs += 1
        except Exception:  # noqa: BLE001
            posts = []
        posts_fetched += len(posts)
        for p in posts:
            if len(str(p.get("text") or "")) < 40:
                continue
            eng = int(p.get("likes") or 0) + 2 * int(p.get("reposts") or 0)
            scored.append((eng, p))
    scored.sort(key=lambda t: t[0], reverse=True)
    # Cap per author so one OSINT/war account cannot own the spectrum band.
    per_author: dict[str, int] = {}
    hits: list[dict[str, Any]] = []
    for _e, p in scored:
        if len(hits) >= max_hits:
            break
        text = str(p.get("text") or "")
        if is_non_news_topic(text):
            continue
        author = str(p.get("author") or "x").casefold()
        if per_author.get(author, 0) >= 1:
            continue
        per_author[author] = per_author.get(author, 0) + 1
        hits.append(
            _post_hit(p, lane=f"spectrum:{p.get('author') or 'x'}", source="x_spectrum")
        )
    return hits, posts_fetched, search_reqs


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
    # Recent-search max_results floor is 10 — need at least that much post budget.
    if accounts and remaining_posts >= 10 and remaining_hits:
        handles = [h for h, _ in accounts]
        chunk_size = 8
        for i in range(0, len(handles), chunk_size):
            if posts_fetched + 10 > max_posts or len(hits) >= max_hits:
                break
            chunk = handles[i : i + chunk_size]
            take = 10  # API floor; we keep only usable posts below
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
    # Referenced posts, when the request asked for them. This is what makes an amplification
    # legible: a quote-tweet's own text is often just "interesting" or "wow", and ALL the
    # substance lives in the post being quoted. Without the referenced text such an item is
    # uninterpretable to synthesis and would have to be discarded for being empty — with it,
    # the same item carries a real story plus the fact that a trusted account thought it
    # worth passing on. The API truncates a retweet's own text at ~140 chars too, so the
    # referenced copy is frequently the only complete version.
    referenced = {
        str(t.get("id")): t
        for t in payload.get("includes", {}).get("tweets", []) or []
        if t.get("id")
    }
    out: list[dict[str, Any]] = []
    for t in payload.get("data") or []:
        u = users.get(t.get("author_id"), {})
        handle = u.get("username", "")
        pm = t.get("public_metrics") or {}
        tid = t.get("id", "")

        ref_type = ref_text = ref_author = ""
        for ref in (t.get("referenced_tweets") or []):
            parent = referenced.get(str(ref.get("id")))
            if not parent:
                continue
            ref_type = str(ref.get("type") or "")
            ref_text = str(parent.get("text") or "")
            ref_author = (users.get(parent.get("author_id"), {}) or {}).get("username", "")
            break

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
            # "retweeted" | "quoted" | "replied_to", plus the referenced post's own words.
            "ref_type": ref_type,
            "ref_text": ref_text,
            "ref_author": ref_author,
        })
    return out


_MEME_NAME_RE = re.compile(
    r"\b(meme|memes|comedy|comedic|delights|stuns in|draws divided views|"
    r"dating|girlfriend|boyfriend|broke boys)\b",
    re.I,
)


def _news_story_usable(story: dict[str, Any]) -> bool:
    """Drop pure viral/social/sports noise; keep real news-shaped clusters."""
    name = str(story.get("name") or story.get("hook") or "").strip()
    if len(name) < 12:
        return False
    if _MEME_NAME_RE.search(name):
        return False
    if is_non_news_topic(name) or is_sports_text(str(story.get("summary") or "")):
        return False
    cat = str(story.get("category") or "").strip().casefold()
    if cat in _JUNK_CATEGORIES:
        return False
    contexts = story.get("contexts") or {}
    topics = contexts.get("topics") if isinstance(contexts, dict) else None
    lowered: set[str] = set()
    if isinstance(topics, list) and topics:
        lowered = {str(t).casefold() for t in topics}
        if lowered & {"sports", "entertainment", "gaming", "celebrity"}:
            return False
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
    if is_non_news_topic(text):
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
    cids = _cluster_post_ids(story, limit=3)
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
        "_cluster_ids": cids,  # stripped/used by hydrate; not for pool serialization
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
