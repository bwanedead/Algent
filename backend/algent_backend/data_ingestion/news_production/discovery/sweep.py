"""
Beat sweep orchestrator — run the registry's targeted DOC queries into a sheet.

The general GKG net finds broad thematic trends; this is the complementary probe
that *guarantees* per-beat coverage by fetching each beat on purpose. It paces
itself to respect the DOC API's strict, stateful rate limit (see ``gdelt_doc``):
a fixed gap between requests, a longer back-off + one retry on a 429, and — if a
beat still can't be fetched — it records the error and moves on. A beat missing
one sweep is fine; the floor/refresh model fills it next cycle.

Pure orchestration over an injected ``search`` callable + a ``sleep`` hook, so it
is fully testable offline with no network and no real waiting.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import UTC, datetime

from ..sources import gdelt_doc
from .beats import Beat, all_beats
from .report import BeatHit, BeatResult, BeatSheet

# Pacing defaults, tuned to the observed rate limit: a request roughly every
# PACE_S, a longer COOLDOWN_S after a 429, one retry, then give up on the beat.
PACE_S = 6.0
COOLDOWN_S = 15.0

SearchFn = Callable[..., list[dict]]


def run_sweep(
    beats: list[Beat] | None = None,
    *,
    max_records: int = 25,
    search: SearchFn = gdelt_doc.search,
    sleep: Callable[[float], None] = time.sleep,
    pace_s: float = PACE_S,
    cooldown_s: float = COOLDOWN_S,
) -> BeatSheet:
    """Sweep the registry (or a given subset) into a :class:`BeatSheet`."""
    targets = beats if beats is not None else all_beats()
    results: list[BeatResult] = []
    for index, beat in enumerate(targets):
        if index:
            sleep(pace_s)
        results.append(_sweep_one(beat, max_records, search, sleep, cooldown_s))

    failed = sum(1 for r in results if r.error)
    return BeatSheet(
        generated_at=datetime.now(UTC).isoformat(),
        timespan=targets[0].timespan if targets else "24h",
        beats_swept=len(results),
        beats_failed=failed,
        total_hits=sum(r.hit_count for r in results),
        results=results,
    )


def _sweep_one(
    beat: Beat, max_records: int, search: SearchFn, sleep: Callable[[float], None], cooldown_s: float
) -> BeatResult:
    base = BeatResult(
        beat_id=beat.id,
        label=beat.label,
        kind=beat.kind,
        pillar=beat.pillar,
        country=beat.country,
        query=beat.query,
    )
    for attempt in range(2):  # one retry, after a cooldown, on rate-limit only
        try:
            raw = search(
                beat.query, max_records=max_records, timespan=beat.timespan, sort=beat.sort
            )
        except gdelt_doc.RateLimited:
            if attempt == 0:
                sleep(cooldown_s)
                continue
            return base.model_copy(update={"error": "rate_limited"})
        except Exception as exc:  # noqa: BLE001 — record any source failure, keep sweeping
            return base.model_copy(update={"error": str(exc)[:200]})
        hits = [BeatHit(**a) for a in raw]
        return base.model_copy(update={"hits": hits, "hit_count": len(hits)})
    return base  # unreachable; keeps type-checkers happy
