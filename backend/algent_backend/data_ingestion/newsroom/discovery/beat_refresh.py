"""
Keeping the beat sheet current — the rotating refresh that makes ``beats`` a live
t0 channel rather than a file somebody once wrote.

The registry is a **sampling frame**, not a set of categories owed coverage: 40-odd
standing queries that reach parts of the corpus the loudness channels (GKG volume, X
trends, markets) structurally cannot see. Nothing downstream owes any query a slot —
what the sweep buys is a wider net, and the pool then keeps whatever is least alike
(see ``pool._diversify``). It only works if the sheet is actually fresh, and a full
sweep is minutes long (the DOC rate limit forces a paced request every few seconds)
— too slow to run on every t0.

So we rotate. Each cycle re-sweeps the **stalest slice** of the registry and merges
it into the standing sheet, which means:

- a cold start covers the broad topical queries first (registry order breaks ties,
  and those lead the registry) — the widest net arrives on cycle one;
- the whole registry stays covered over a few cycles at ~a minute apiece;
- a beat that fails is left un-stamped, so it is first in line next cycle rather
  than counting as fresh;
- results past :data:`STALE_HOURS` are dropped outright, so a sheet that went stale
  (or a run with refresh disabled) contributes *nothing* instead of folding
  month-old articles into t0 as if they were today's news.

Pure functions over an injected sweep callable — no I/O, no clock of its own.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from datetime import UTC, datetime

from .beats import Beat, all_beats
from .report import BeatResult, BeatSheet
from .sweep import run_sweep

# A beat result older than this is not news any more — beats query a 24h timespan,
# so past this point the hits are stale by their own definition. Dropped on load.
STALE_HOURS = 24.0
# A beat older than this is eligible for re-sweep. Below it, the sheet is current
# enough to serve as-is, so a t0 close behind another one costs nothing.
REFRESH_HOURS = 6.0
# How many beats one cycle re-sweeps. Kept small on purpose: the DOC limiter
# escalates on burst size and decays over minutes, so a big slice does not fetch more
# — it fetches a little and then locks the caller out for the rest of the cycle. A
# measured 14-beat slice came back 12/14 throttled. Small and often beats big and once.
DEFAULT_SLICE = 8

_ENV_ENABLED = "ALGENT_BEATS_REFRESH"      # "0" to disable the auto-refresh
_ENV_SLICE = "ALGENT_BEATS_SLICE"
_ENV_STALE_HOURS = "ALGENT_BEATS_STALE_HOURS"
_ENV_REFRESH_HOURS = "ALGENT_BEATS_REFRESH_HOURS"

ProgressFn = Callable[[str], None]


def refresh_enabled() -> bool:
    """Auto-refresh is ON by default; ``ALGENT_BEATS_REFRESH=0`` opts out."""
    return os.environ.get(_ENV_ENABLED, "1").strip().lower() not in ("0", "false", "no", "off")


def slice_size() -> int:
    return _int_env(_ENV_SLICE, DEFAULT_SLICE, lo=1, hi=len(all_beats()))


def stale_hours() -> float:
    return _float_env(_ENV_STALE_HOURS, STALE_HOURS, lo=0.5, hi=24 * 14)


def refresh_hours() -> float:
    return _float_env(_ENV_REFRESH_HOURS, REFRESH_HOURS, lo=0.0, hi=24 * 14)


def age_hours(result: BeatResult, *, now: datetime) -> float:
    """Hours since this beat was last fetched. Never-swept reads as effectively infinite."""
    if not result.swept_at:
        return float("inf")
    try:
        when = datetime.fromisoformat(result.swept_at.replace("Z", "+00:00"))
    except ValueError:
        return float("inf")
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    return (now - when).total_seconds() / 3600.0


def prune_stale(
    sheet: BeatSheet | None, *, hours: float | None = None, now: datetime | None = None
) -> BeatSheet | None:
    """Drop beat results older than ``hours``. Returns None when nothing survives.

    This is the age guard: it runs on load as well as on refresh, so no path can
    fold a stale sheet into t0.
    """
    if sheet is None:
        return None
    limit = stale_hours() if hours is None else hours
    at = now or datetime.now(UTC)
    kept = [r for r in sheet.results if age_hours(r, now=at) <= limit]
    if not kept:
        return None
    return _resheet(sheet, kept)


def stalest_beats(
    sheet: BeatSheet | None,
    *,
    limit: int,
    eligible_after: float,
    registry: list[Beat] | None = None,
    now: datetime | None = None,
) -> list[Beat]:
    """The ``limit`` beats most in need of a re-sweep, stalest first.

    Only beats at least ``eligible_after`` hours old qualify, so a current sheet
    schedules no work at all. Registry order breaks ties, which is what gives a
    cold start its useful shape: the pillars lead the registry, so the first
    refresh buys topical breadth before it buys another country.
    """
    beats = all_beats() if registry is None else registry
    at = now or datetime.now(UTC)
    by_id = {r.beat_id: r for r in (sheet.results if sheet else [])}

    scored: list[tuple[float, int, Beat]] = []
    for index, beat in enumerate(beats):
        result = by_id.get(beat.id)
        age = float("inf") if result is None else age_hours(result, now=at)
        if age >= eligible_after:
            # Negate age so the sort puts the stalest first; inf stays first.
            scored.append((-age, index, beat))
    scored.sort(key=lambda t: (t[0], t[1]))
    return [beat for _, _, beat in scored[:limit]]


def refresh_sheet(
    sheet: BeatSheet | None,
    *,
    limit: int | None = None,
    eligible_after: float | None = None,
    hours: float | None = None,
    now: datetime | None = None,
    registry: list[Beat] | None = None,
    sweep: Callable[..., BeatSheet] = run_sweep,
    on_progress: ProgressFn | None = None,
    **sweep_kwargs: object,
) -> BeatSheet | None:
    """Re-sweep the stalest slice and merge it into ``sheet``. Returns the new sheet.

    ``sweep`` and ``registry`` are injected so this is testable with no network and no
    waiting — and so the rotation can be pointed at a subset of beats deliberately.
    """
    say = on_progress or (lambda _m: None)
    at = now or datetime.now(UTC)
    beats = all_beats() if registry is None else registry
    current = prune_stale(sheet, hours=hours, now=at)

    targets = stalest_beats(
        current,
        limit=slice_size() if limit is None else limit,
        eligible_after=refresh_hours() if eligible_after is None else eligible_after,
        registry=beats,
        now=at,
    )
    if not targets:
        say("beats: sheet is current — no re-sweep needed")
        return current

    say(f"beats: re-sweeping {len(targets)} stalest of {len(beats)} (paced, free)…")
    # Narrate per beat: this is a minutes-long paced fetch, and a t0 that goes silent
    # for minutes is indistinguishable from a t0 that hung.
    sweep_kwargs.setdefault("on_progress", _beat_narrator(say))
    # Resume the limiter's pace from where the last sweep left it (see sweep.run_sweep).
    if current is not None and current.last_gap_s:
        sweep_kwargs.setdefault("start_gap_s", current.last_gap_s)
    swept = sweep(targets, **sweep_kwargs)
    merged = merge(current, swept)
    fresh = sum(1 for r in swept.results if not r.error)
    say(
        f"beats: {fresh}/{len(targets)} refreshed ({swept.total_hits} hits); "
        f"sheet now {merged.beats_swept if merged else 0} beats / "
        f"{merged.total_hits if merged else 0} hits"
    )
    return merged


def _beat_narrator(say: ProgressFn) -> Callable[[int, int, BeatResult], None]:
    """Render one line per swept beat onto the run timeline."""

    def narrate(done: int, total: int, result: BeatResult) -> None:
        outcome = f"{result.hit_count} hits" if not result.error else result.error
        say(f"  beats {done}/{total}  {result.beat_id:24} {outcome}")

    return narrate


def merge(sheet: BeatSheet | None, swept: BeatSheet) -> BeatSheet | None:
    """Fold a fresh partial sweep into the standing sheet, keyed by beat id.

    A successful result replaces whatever was there. A *failed* one does not: the
    previous hits are better coverage than none, and leaving the old (or absent)
    stamp in place is what puts the beat back at the front of the next rotation.
    """
    by_id: dict[str, BeatResult] = {r.beat_id: r for r in (sheet.results if sheet else [])}
    for result in swept.results:
        if result.error and result.beat_id in by_id:
            continue
        by_id[result.beat_id] = result
    kept = list(by_id.values())
    if not kept:
        return None
    # The fresh sweep is the authority on what the limiter is currently allowing.
    return _resheet(sheet or swept, kept, last_gap_s=swept.last_gap_s or None)


def _resheet(
    base: BeatSheet, results: list[BeatResult], *, last_gap_s: float | None = None
) -> BeatSheet:
    """``base`` with ``results`` swapped in and the roll-up counters recomputed."""
    return base.model_copy(update={
        "generated_at": datetime.now(UTC).isoformat(),
        "results": results,
        "beats_swept": len(results),
        "beats_failed": sum(1 for r in results if r.error),
        "total_hits": sum(r.hit_count for r in results),
        "last_gap_s": base.last_gap_s if last_gap_s is None else last_gap_s,
    })


def _int_env(name: str, default: int, *, lo: int, hi: int) -> int:
    try:
        return max(lo, min(hi, int(os.environ.get(name, str(default)))))
    except ValueError:
        return default


def _float_env(name: str, default: float, *, lo: float, hi: float) -> float:
    try:
        return max(lo, min(hi, float(os.environ.get(name, str(default)))))
    except ValueError:
        return default
