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
)


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
    """Sports or entertainment — drop from discovery menus."""
    return is_sports_text(text) or is_entertainment_junk(text)
