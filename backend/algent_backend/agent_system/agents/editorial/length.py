"""House grain for a landed article — default vs earned ceiling.

Most pieces land at the digest (a 5-minute read). Extra minutes are earned by the
focal thing, not by research richness. The ceiling is the hard stop even then.
Completeness is the shape (sides, caveats, contrary evidence), not more words.
"""

from __future__ import annotations

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


def word_band(minutes: int) -> tuple[int, int]:
    """Low/high words for a treatment depth.

    At or under the default digest, the high end is the digest. Above it, the high
    end is the earned ceiling — a 10-minute treatment still cannot authorize a tour.
    """
    m = max(0, int(minutes))
    if m <= 0:
        return 0, 0
    cap = ceiling_words() if m > digest_minutes() else digest_words()
    low = int(m * _BAND_LOW_WPM)
    high = min(cap, int(m * _BAND_HIGH_WPM))
    if high < low:
        low = min(low, cap)
        high = cap
    return low, high


def reviewer_length_task(words: int) -> str:
    """The count the reviewer can see — doctrine without a number is how 2,300-word pieces ship."""
    n = max(0, int(words))
    return (
        f"This draft is {n} words (~{n / wpm():.1f} min). "
        f"If you rewrite, come in under {digest_words()} words: wrap the tour, "
        f"do not trim it. Cut what left the premise — do not drop a side of "
        f"the same dispute."
    )
