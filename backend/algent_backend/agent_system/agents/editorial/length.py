"""House grain for a landed article — default vs earned ceiling.

Most pieces land at the digest (a 5-minute read). Extra minutes are earned by the
focal thing, not by research richness. The ceiling is the hard stop even then.
Completeness is the shape (sides, caveats, contrary evidence), not more words.
"""

from __future__ import annotations

from typing import Any

from algent_backend.agent_system.agents.newsroom.flags import (
    ARTICLE_DIGEST_CEILING_MINUTES,
    ARTICLE_DIGEST_CEILING_WORDS,
    ARTICLE_DIGEST_MINUTES,
    ARTICLE_DIGEST_WORDS,
    ARTICLE_WPM,
)

# Same band the briefing has always shown (~220 wpm ± slack). The high end is then
# capped: treatments at or under the default cannot authorize past the digest;
# treatments that claimed more still cannot authorize past the earned ceiling.
_BAND_LOW_WPM = 190
_BAND_HIGH_WPM = 250


def digest_words() -> int:
    return max(400, int(ARTICLE_DIGEST_WORDS))


def digest_minutes() -> int:
    return max(3, int(ARTICLE_DIGEST_MINUTES))


def ceiling_words() -> int:
    return max(digest_words(), int(ARTICLE_DIGEST_CEILING_WORDS))


def ceiling_minutes() -> int:
    return max(digest_minutes(), int(ARTICLE_DIGEST_CEILING_MINUTES))


def wpm() -> int:
    return max(150, int(ARTICLE_WPM))


def count_words(text: str) -> int:
    return len((text or "").split())


def word_band(minutes: int, *, survey: bool = False) -> tuple[int, int]:
    """Low/high words for a treatment depth.

    At or under the default digest, the high end is the digest. Above it, the high
    end is the earned ceiling — a 10-minute treatment still cannot authorize a tour.

    ``survey`` is the one shape the ceiling does not fit. A piece whose subject IS a set of
    discrete members — eight proposed structures, every bidder — is browsed, not read straight
    through, and the grain that matters is per member. Squeezing eight structures under one
    article's ceiling is how each of them got a paragraph that named it and moved on. So the
    planner's minutes govern instead, and each member still has to earn its section.
    """
    m = max(0, int(minutes))
    if m <= 0:
        return 0, 0
    if survey:
        return int(m * _BAND_LOW_WPM), int(m * _BAND_HIGH_WPM)
    cap = ceiling_words() if m > digest_minutes() else digest_words()
    low = int(m * _BAND_LOW_WPM)
    high = min(cap, int(m * _BAND_HIGH_WPM))
    if high < low:
        low = min(low, cap)
        high = cap
    return low, high


def planned_band(treatment: Any) -> tuple[int, int]:
    """The (low, high) words a treatment planned — THE length authority for drafter and cut.

    Accepts the treatment as a model or a dict. No planned minutes means the house digest.
    """
    get = treatment.get if isinstance(treatment, dict) else (lambda k: getattr(treatment, k, None))
    minutes = int((get("read_minutes") if treatment else 0) or 0)
    if minutes <= 0:
        return 0, digest_words()
    return word_band(minutes, survey=str((get("shape") if treatment else "") or "") == "survey")


def paragraphs_for(words: int) -> int:
    """The same length in paragraphs. A model cannot count words as it writes; it can count
    paragraphs. ~75 words is a plain news paragraph of three or four sentences."""
    return max(1, round(max(0, int(words)) / 75))


def reviewer_length_task(words: int) -> str:
    """The count the reviewer can see — doctrine without a number is how 2,300-word pieces ship."""
    n = max(0, int(words))
    return (
        f"This draft is {n} words (~{n / wpm():.1f} min). "
        f"If you rewrite, come in under {digest_words()} words: wrap the tour, "
        f"do not trim it. Cut what left the premise — do not drop a side of "
        f"the same dispute. "
        f"UNLESS this piece is a survey — its subject IS a set of discrete members, each with "
        f"its own heading, that a reader browses rather than reads straight through. Then the "
        f"grain is per member: ask of each whether it earns its section and whether a reader "
        f"learns the thing itself, and cut whole members that repeat or say nothing specific. "
        f"Do not compress a survey's members into a list to hit a number — that is how eight "
        f"structures became eight sentences that named them."
    )
