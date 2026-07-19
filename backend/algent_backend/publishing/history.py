"""
What we have already published — the cooldown reference.

A pool built from published-article volume keeps re-surfacing whatever is dominating the wires, so
the newsroom covers the same running story night after night. The cheapest correction is to tell
the promotion router what we JUST RAN: recent headlines, as data, with an instruction not to pick a
close match. Judgment stays with the router (a genuinely new development on a running story should
still promote) — this is a cooldown, not a mechanical block.

Headlines are the reference because they are what a reader would recognise as "the same story",
and because they cost nothing to produce: they are already in the published frontmatter.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import yaml

_DEFAULT_LIMIT = 12       # article cooldown: how many recent pieces to hold in view
_DEFAULT_DAYS = 10        # time cooldown: how long a story stays "just covered"


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
    cutoff = (now or datetime.now(UTC)) - timedelta(days=days)
    seen: dict[str, tuple[str, str]] = {}
    for site_dir in site_dirs:
        articles = site_dir / "content" / "articles"
        if not articles.is_dir():
            continue
        for path in articles.glob("*.md"):
            fm = _frontmatter(path)
            title = str(fm.get("title") or "").strip()
            if not title or fm.get("status") == "retracted":
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
            seen.setdefault(path.stem, (when.isoformat(), title))   # slug-keyed: live copy wins
    return [v for _, v in sorted(seen.items(), key=lambda kv: kv[1][0], reverse=True)][:limit]
