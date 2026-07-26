"""
What we have already published — the cooldown reference.

A pool built from published-article volume keeps re-surfacing whatever is dominating the wires, so
the newsroom covers the same running story night after night. The cheapest correction is to tell
the promotion (and synthesis) agent what we JUST RAN: recent headlines as payload. The agent
judges story-family match semantically and flags cooldown — there is no lexical demotion floor.

Headlines are the reference because they are what a reader would recognise as "the same story",
and because they cost nothing to produce: they are already in the published frontmatter.

Headlines answer "did we write *this*?". They do not answer "have we been circling one thing?" —
four Hormuz pieces were four genuinely different days, each honestly not the same story as the
last, and the feed still read as a single obsession. So the frontmatter yields a second, coarser
reference: :func:`recurring_coverage`, the subjects/places/topics our recent output keeps
returning to. It is descriptive, not a taxonomy — it reports whatever we actually published,
which is why it needs no fixed category list. A thumb on the scale for tie-breaks, never a block;
the router brief spells out the difference between "same story" and "same rut".
"""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path

import yaml

_DEFAULT_LIMIT = 15       # article cooldown: how many recent pieces to hold in view
_DEFAULT_DAYS = 10        # time cooldown: how long a story stays "just covered"
# Only interesting once it *recurs* — one article on a subject is coverage, not a rut.
_RECURRENCE_MIN = 2
_RECURRENCE_TOP = 12      # keep the payload short: the worst offenders, not the whole tag cloud


def _frontmatter(path: Path) -> dict:
    try:
        text = path.read_text(encoding="utf-8")
        if text.startswith("---"):
            return yaml.safe_load(text.split("---\n", 2)[1]) or {}
    except Exception:  # noqa: BLE001 — one unreadable file must not break routing
        pass
    return {}


def recent_headlines(
    site_dirs: list[Path], *, limit: int = _DEFAULT_LIMIT, days: int = _DEFAULT_DAYS,
    now: datetime | None = None,
) -> list[tuple[str, str]]:
    """(date, title) for recently published pieces, newest first — the cooldown list.

    Reads whichever site dirs exist (the live worktree first, then the working tree), so it
    reflects what is actually on the site. Both cooldowns apply: within ``days``, capped at
    ``limit`` — an old article stops suppressing, and a busy week doesn't flood the prompt.
    """
    recent = _recent_frontmatter(site_dirs, days=days, now=now)[:limit]
    return [(when, str(fm.get("title") or "").strip()) for when, fm in recent]


def recurring_coverage(
    site_dirs: list[Path], *, limit: int = _DEFAULT_LIMIT, days: int = _DEFAULT_DAYS,
    now: datetime | None = None,
) -> list[tuple[str, int]]:
    """(label, count) for what recent output keeps returning to — the rut reference.

    Read straight off the frontmatter the publish step already writes, on the three axes
    a reader would notice repetition in: ``subject:`` (the specific named entity),
    ``place:`` (country), and ``topic:`` (the canonical desk). Only recurring labels are
    returned, worst first — one article on something is coverage, not a rut.
    """
    counts: Counter[str] = Counter()
    for _when, fm in _recent_frontmatter(site_dirs, days=days, now=now)[:limit]:
        for tag in _strings(fm.get("tags")):
            counts[f"{'topic' if _is_canonical_topic(tag) else 'subject'}:{tag}"] += 1
        for place in _strings(fm.get("places")):
            counts[f"place:{place}"] += 1
    ranked = [(label, n) for label, n in counts.most_common() if n >= _RECURRENCE_MIN]
    return ranked[:_RECURRENCE_TOP]


def _is_canonical_topic(tag: str) -> bool:
    """A canonical desk (economics, conflict, …) rather than a story-specific entity."""
    try:
        from .tagging import _TOPIC_VOCAB

        return tag.strip().lower() in _TOPIC_VOCAB
    except Exception:  # noqa: BLE001 — labelling is cosmetic; never break the reference
        return False


def _strings(value: object) -> list[str]:
    return [str(v).strip() for v in value if str(v).strip()] if isinstance(value, list) else []


def _recent_frontmatter(
    site_dirs: list[Path], *, days: int, now: datetime | None = None,
) -> list[tuple[str, dict]]:
    """(iso_when, frontmatter) for live, in-window pieces, newest first — the shared walk."""
    cutoff = (now or datetime.now(UTC)) - timedelta(days=days)
    seen: dict[str, tuple[str, dict]] = {}
    for site_dir in site_dirs:
        articles = site_dir / "content" / "articles"
        if not articles.is_dir():
            continue
        for path in articles.glob("*.md"):
            fm = _frontmatter(path)
            if not str(fm.get("title") or "").strip() or fm.get("status") == "retracted":
                continue
            stamp = str(fm.get("published_at") or fm.get("date") or "")
            try:
                when = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
                if when.tzinfo is None:
                    when = when.replace(tzinfo=UTC)
            except ValueError:
                continue
            if when < cutoff:
                continue
            seen.setdefault(path.stem, (when.isoformat(), fm))   # slug-keyed: live copy wins
    return sorted(seen.values(), key=lambda kv: kv[0], reverse=True)
