"""
What did we already surface? — the cross-run novelty ledger.

The stagnation this fixes, and why it is structural rather than a tuning problem:

The rolling memory in ``memory.py`` gives GKG a baseline for velocity, and **only
GKG**. X, science, beats and markets have no cross-run state at all, so every run
re-collects whatever those sources currently show with no notion that yesterday's
menu existed. The consequences are exactly what an operator reports as "stagnated":

- **science** takes the top 8 entries of each of 12 feeds. Nature publishes weekly,
  ESA and Quanta change slowly — so 6 of those 8 are items we listed yesterday, and
  the day before. The feed is fine; the harvesting has no memory.
- **X** searched with ``sort_order="relevancy"`` over the platform's 7-day window,
  which returns the *most engaged* posts of the week. Engagement accumulates with
  age, so the ranking is systematically biased toward the same posts every run. One
  measured pool carried a post 163 hours old.
- **beats** sweeps 8 of 41 slices per run, so a given slice is visited rarely and
  serves a stale cached row when it is not.

None of that is fixed by better queries. A source cannot tell you what is new to
*you* — only we know what we have already seen, so only we can subtract it.

## What this is not

Not a cooldown and not a topic freeze. Those act on *stories we published* and on
*subjects we over-cover*; both live downstream and both should stay. This is one
level earlier and much dumber: this exact item — this URL, this post — was already
in a pool, so it is not a discovery today.

Repeats are **demoted, not deleted**. A story genuinely developing over days should
still be reachable, and a hard drop would empty the pool on a quiet day. So a seen
item survives only as backfill, after everything genuinely new has taken its place.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

FILENAME = "seen_items.json"

#: How long an item stays "already seen". Long enough that a slow weekly feed does
#: not re-offer the same entry on every run for a fortnight; short enough that a
#: genuinely recurring subject can come back around.
DEFAULT_HORIZON_DAYS = 10

#: Tracking parameters and other per-visit junk that make one URL look like many.
_JUNK_QUERY = re.compile(r"[?&](utm_[^&]*|fbclid|gclid|ref|source|amp)=[^&]*", re.I)


def _normalize(url: str) -> str:
    """A URL reduced to what identifies the item, so one story is one key."""
    text = (url or "").strip().lower()
    if not text:
        return ""
    text = _JUNK_QUERY.sub("", text)
    text = re.sub(r"^https?://", "", text)
    text = re.sub(r"^(www|amp)\.", "", text)
    return text.rstrip("/#?&")


def item_key(item: Any) -> str:
    """The identity of a pool item for novelty purposes: its first evidence URL, else its id.

    URL first because the same story reaches us through several channels with different
    ids, and it is the *story* we have already seen.
    """
    evidence = getattr(item, "evidence", None) or []
    for entry in evidence:
        url = getattr(entry, "url", None) or (entry.get("url") if isinstance(entry, dict) else None)
        if url:
            key = _normalize(str(url))
            if key:
                return key
    return str(getattr(item, "id", "") or "")


@dataclass
class SeenLedger:
    """Item key -> ISO date we first put it in a pool."""

    first_seen: dict[str, str] = field(default_factory=dict)

    def is_seen(self, key: str) -> bool:
        return bool(key) and key in self.first_seen

    def record(self, keys: list[str], *, today: str | None = None) -> SeenLedger:
        """Add this run's keys, keeping the FIRST date each was seen."""
        stamp = today or datetime.now(UTC).date().isoformat()
        merged = dict(self.first_seen)
        for key in keys:
            if key:
                merged.setdefault(key, stamp)
        return SeenLedger(first_seen=merged)

    def pruned(self, *, horizon_days: int = DEFAULT_HORIZON_DAYS,
               now: datetime | None = None) -> SeenLedger:
        """Forget anything older than the horizon, so the file cannot grow forever."""
        cutoff = ((now or datetime.now(UTC)) - timedelta(days=horizon_days)).date().isoformat()
        return SeenLedger(first_seen={k: v for k, v in self.first_seen.items() if v >= cutoff})


def load_seen(directory: Path) -> SeenLedger:
    path = Path(directory) / FILENAME
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return SeenLedger()
    seen = raw.get("first_seen") if isinstance(raw, dict) else None
    if not isinstance(seen, dict):
        return SeenLedger()
    return SeenLedger(first_seen={str(k): str(v) for k, v in seen.items()})


def save_seen(ledger: SeenLedger, directory: Path) -> None:
    path = Path(directory)
    path.mkdir(parents=True, exist_ok=True)
    (path / FILENAME).write_text(
        json.dumps({"first_seen": ledger.first_seen}, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )


def partition(items: list[Any], ledger: SeenLedger) -> tuple[list[Any], list[Any]]:
    """Split into ``(fresh, repeats)`` preserving order within each group.

    Repeats are returned rather than discarded so the caller can backfill with them —
    a quiet day should still produce a full pool, just one honestly marked as such.
    """
    fresh: list[Any] = []
    repeats: list[Any] = []
    for item in items:
        (repeats if ledger.is_seen(item_key(item)) else fresh).append(item)
    return fresh, repeats
