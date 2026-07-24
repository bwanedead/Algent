"""
Beat sweep orchestrator — run the registry's targeted DOC queries into a sheet.

The general GKG net finds broad thematic trends; this is the complementary probe
that *guarantees* per-beat coverage by fetching each beat on purpose.

Everything here is shaped by one fact: **the DOC rate limit is stateful and
escalating**, so a sweep that keeps knocking at a fixed interval digs itself deeper.
A live 14-beat sweep at a flat 6s gap with one immediate retry apiece came back
12/14 throttled — the retries were feeding the thing that was blocking us. So:

- the gap between requests is **adaptive and carries across beats** — it doubles on
  every throttle and decays back down on success, because the limiter's state is
  global, not per-beat;
- there is **no immediate retry**. A throttled beat is left unstamped, which puts it
  at the front of the next rotation (see ``beat_refresh``) — the retry already exists,
  one cycle later and for free, instead of at the worst possible moment;
- the sweep runs under a **wall-clock budget**. Beats past the budget are simply not
  attempted; they stay stalest and go first next cycle. This is what keeps the sweep
  safe to call inline from ``ensure_t0``.

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

# Pacing, measured against the live limiter rather than its documentation. GDELT's
# own 429 body says "one request every 5 seconds", but a probe at a 10s gap scored
# 0/6 and at 15s scored 2/6 — because an earlier burst had put the caller in an
# escalated penalty state that decays over *minutes*. Treat 5s as a floor that is
# necessary and nowhere near sufficient, and treat burst size as the real variable.
PACE_S = 12.0        # baseline gap between requests
COOLDOWN_S = 25.0    # the gap floor once we've been throttled at all
MAX_GAP_S = 120.0    # ceiling — past here we are not getting in this cycle
DECAY = 0.7          # how fast the gap relaxes after a success
BUDGET_S = 300.0     # wall-clock cap for one sweep

SearchFn = Callable[..., list[dict]]
ClockFn = Callable[[], float]


def run_sweep(
    beats: list[Beat] | None = None,
    *,
    max_records: int = 25,
    search: SearchFn = gdelt_doc.search,
    sleep: Callable[[float], None] = time.sleep,
    pace_s: float = PACE_S,
    cooldown_s: float = COOLDOWN_S,
    max_gap_s: float = MAX_GAP_S,
    budget_s: float = BUDGET_S,
    clock: ClockFn = time.monotonic,
    on_progress: Callable[[int, int, BeatResult], None] | None = None,
) -> BeatSheet:
    """Sweep the registry (or a given subset) into a :class:`BeatSheet`.

    ``on_progress(done, total, result)`` is called after each beat so a caller can
    narrate this otherwise-silent, minutes-long paced sweep. Beats not reached inside
    ``budget_s`` are omitted from the sheet rather than recorded as failures — they
    were never asked, and the rotation will ask them first next time.
    """
    targets = beats if beats is not None else all_beats()
    results: list[BeatResult] = []
    started = clock()
    gap = pace_s

    for index, beat in enumerate(targets):
        if index:
            if clock() - started + gap > budget_s:
                break  # out of budget — leave the rest unswept, not failed
            sleep(gap)
        result = _sweep_one(beat, max_records, search)
        results.append(result)
        gap = _next_gap(gap, result, pace_s=pace_s, cooldown_s=cooldown_s, max_gap_s=max_gap_s)
        if on_progress is not None:
            on_progress(index + 1, len(targets), result)

    return BeatSheet(
        generated_at=datetime.now(UTC).isoformat(),
        timespan=targets[0].timespan if targets else "24h",
        beats_swept=len(results),
        beats_failed=sum(1 for r in results if r.error),
        total_hits=sum(r.hit_count for r in results),
        results=results,
    )


def _next_gap(
    gap: float, result: BeatResult, *, pace_s: float, cooldown_s: float, max_gap_s: float
) -> float:
    """Escalate on a throttle, relax on a success — the limiter's state is global."""
    if result.error == "rate_limited":
        return min(max_gap_s, max(cooldown_s, gap * 2))
    if result.error:
        return gap  # a source error tells us nothing about the limiter
    return max(pace_s, gap * DECAY)


def _sweep_one(beat: Beat, max_records: int, search: SearchFn) -> BeatResult:
    base = BeatResult(
        beat_id=beat.id,
        label=beat.label,
        kind=beat.kind,
        pillar=beat.pillar,
        country=beat.country,
        query=beat.query,
    )
    try:
        raw = search(beat.query, max_records=max_records, timespan=beat.timespan, sort=beat.sort)
    except gdelt_doc.RateLimited:
        # No retry here by design — see the module docstring. Unstamped means the
        # rotation puts this beat first next cycle.
        return base.model_copy(update={"error": "rate_limited"})
    except Exception as exc:  # noqa: BLE001 — record any source failure, keep sweeping
        return base.model_copy(update={"error": str(exc)[:200]})
    hits = [BeatHit(**a) for a in raw]
    # Stamp only the success path: a failed beat stays "never swept" so the
    # rotating refresh retries it next cycle instead of counting it as fresh.
    return base.model_copy(update={
        "hits": hits,
        "hit_count": len(hits),
        "swept_at": datetime.now(UTC).isoformat(),
    })
