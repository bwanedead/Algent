"""
Shared topic filters — sports/entertainment denylists used across discovery channels.

One audited home so X novelty, prediction markets, and GKG entity extraction do not
drift into three incompatible sports policies. Expand only on observed noise.
MMA/UFC are included in the denylist for now (product choice: no sports focus);
remove those markers when that beat is deliberately opened later.
"""

from __future__ import annotations

import re

# Substring markers (case-insensitive) that mark sports / match markets / team news.
# Conservative: prefer false negatives over killing legitimate policy stories.
_SPORTS_MARKERS: tuple[str, ...] = (
    # leagues / competitions
    "world cup", "fifa", "uefa", "nba", "nfl", "mlb", "nhl", "ncaa", "mls",
    "premier league", "champions league", "la liga", "serie a", "bundesliga",
    "ligue 1", "super bowl", "world series", "stanley cup", "ballon d'or",
    "grand prix", "formula 1", " f1 ", "ufc", "mma", "boxing", "wimbledon",
    "ryder cup", "olympics", "olympic games", "paralympic",
    # clubs / teams (common leaks)
    "manchester united", "manchester city", "real madrid", "barcelona",
    "bayern munich", "liverpool fc", "chelsea fc", "arsenal fc", "psg ",
    "lakers", "celtics", "yankees", "dodgers", "chiefs", "cowboys",
    "raptors", "miami heat", "golden state", "tottenham",
    # Leaked through a live GKG pool as a roster move ("phillies place ... on il").
    "phillies", "mets", "red sox", "cubs", "astros", "braves", "padres",
    "76ers", "warriors", "bucks", "nuggets", "packers", "eagles nfl", "steelers",
    # athletes / transfer speech
    "lebron", "messi", "ronaldo", "mbappe", "haaland", "mahomes",
    "transfer window", "transfer fee", "has signed for", "loan deal",
    "matchday", "kickoff", "kick-off", "box score", "playoff", "playoffs",
    "to win the match", "vs.", " vs ", "won the game", "scored a goal",
    "touchdown", "home run", "grand slam", "penalty shoot",
    # market / parlay shape
    "win on 20", "winner of the", "open 20", "to lift the",
    "tennis", "golf tournament", "cricket", "rugby", "nascar",
    "esports", "e-sports",
)

# Whole-word-ish sport tokens (avoid matching "court" politics via "court").
_SPORTS_WORD_RE = re.compile(
    r"\b("
    r"soccer|footballer|goalkeeper|midfielder|striker|quarterback|"
    r"pitcher|batting|wicket|wickets|innings|halftime|fulltime|"
    r"fixture|fixtures|relegation|promotion race|transfer|"
    r"lineup|line-up|roster move|free agent|draft pick|"
    r"ufc|mma|wrestlemania|knicks|nets|yankees"
    r")\b",
    re.I,
)

_ENTERTAINMENT_MARKERS: tuple[str, ...] = (
    "box office", "netflix series", "reality show", "grammy", "oscar nominee",
    "celebrity dating", "red carpet", "kardashian", "onlyfans",
    # Observed on a live GKG pool: concert cancellations, radio-show clips, a wellness
    # podcast episode, celebrity marriage gossip, travel listicles. All arrived as
    # "stories" with URL-slug labels.
    "concert short", "comeback tour", "full show", "soul sessions",
    "divorce", "dating rumors", "engagement ring", "baby bump",
    "isnt just for", "is wild as", "things to do in",
)
# NOTE: release-PR markers ("release date", "new dlc", "gameplay trailer") were tried
# here and removed. Gaming is a wanted beat, and a denylist broad enough to catch
# marketing copy also catches "Nintendo announces release date for X", which is real
# gaming news. The fix for a beat returning marketing belongs in the beat's *query*
# (see beats._PILLAR_QUERIES["gaming"]), not in a filter that can't tell the two apart.

# Algorithmic finance SEO — the ticker-roundup mills. Observed on a live sweep:
# "Promising Cryptocurrency Stocks To Follow Today – July 24th", "Top Blockchain
# Stocks To Consider – July 24th". These are generated daily from a template, carry
# no event, and arrive in volume, so they crowd a capped menu with nothing. Matched
# on headline *shape* rather than by domain, because the mills rotate domains.
_PROMO_MARKERS: tuple[str, ...] = (
    "stocks to follow", "stocks to consider", "stocks to watch", "stocks to buy",
    "shares to watch", "stocks you should", "stocks that could",
    "shares sold by", "shares bought by", "shares acquired by", "stake boosted by",
    "position increased by", "position lowered by", "position raised by",
    "buys new stake", "sells shares of", "purchases shares of",
    "short interest update", "short interest down", "short interest up",
    "price target raised", "price target lowered", "given average rating",
    "sets new 52-week", "reaches new 52-week", "trading up", "trading down",
    "analysts expect", "expected to post", "eps estimate",
    "here's what to know about", "what you need to know about",
)


def is_promo_listicle(text: str) -> bool:
    """True for template-generated ticker/SEO roundups — volume with no event."""
    if not text:
        return False
    return any(marker in text.casefold() for marker in _PROMO_MARKERS)


# A GKG story label is scraped from a URL path, and plenty of CMSs put a UUID there
# instead of a slug. Observed live: "fd3f4cef f9d9 4f86 86c7 361c42ecefa8". There is no
# story in it and never will be, so it should never reach a menu.
_HEXISH_RE = re.compile(r"^[0-9a-f]{4,}$")


def is_label_garbage(text: str) -> bool:
    """True when a label carries no words — a UUID or hash scraped from a URL path."""
    words = text.split()
    if not words:
        return True
    hexish = sum(1 for w in words if _HEXISH_RE.fullmatch(w.casefold()))
    return hexish >= max(2, len(words) - 1)


def is_sports_text(text: str) -> bool:
    """True when text is primarily sports / match / transfer noise."""
    if not text or not text.strip():
        return False
    blob = f" {text.casefold()} "
    if any(m in blob for m in _SPORTS_MARKERS):
        return True
    return bool(_SPORTS_WORD_RE.search(text))


def is_entertainment_junk(text: str) -> bool:
    """True for pure celebrity/entertainment noise (not culture policy)."""
    if not text:
        return False
    blob = text.casefold()
    return any(m in blob for m in _ENTERTAINMENT_MARKERS)


def is_non_news_topic(text: str) -> bool:
    """Sports, entertainment, ticker-mill SEO, or wordless junk — drop from menus."""
    return (
        is_sports_text(text)
        or is_entertainment_junk(text)
        or is_promo_listicle(text)
        or is_label_garbage(text)
    )
