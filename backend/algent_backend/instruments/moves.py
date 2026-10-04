"""
Moves — what the latest reading of a series says, judged against that series' own history.

Pure and deterministic (no I/O, no model). For one series it reports the latest value, how it
changed against the previous reading and ~7d / ~30d / ~1y earlier, where it sits in its trailing
year (percentile), whether it is AT its high/low over a window (30d/90d/1y, ties allowed, only windows its history covers), and whether it is ``unusual``.

"Unusual" is DERIVED, not tuned — there is no per-series threshold anywhere:

* ``change_z`` — the latest period-over-period change, in standard deviations of the series' own
  earlier changes (log-changes when every value is positive, plain differences otherwise, so a
  price and a ship count are both judged on a sensible scale).
* ``level_z`` — the latest value, in standard deviations of its own trailing year (excluding the
  latest). This catches a sustained collapse that no single day-over-day change would flag.
* ``long_run_z`` — the latest value against ALL stored history. A regime that lasts longer than
  the trailing year's worth of "normal" (Hormuz has sat at 1-13 ships/day since March 2026 while
  its five-year mean is ~80) drags the trailing-year mean down with it and hides itself from
  ``level_z``; the full record does not forget. It is reported as ``long_run_outside`` and NOT
  folded into ``unusual``: any trending series (debt, a rising yield) sits "outside" its own past
  by construction, so as a flag it would cry wolf; as a note beside the reading it is exactly the
  context a reader wants.

``unusual`` is true when any |z| exceeds ``Z_LIMIT`` (2 — the conventional two-sigma reading of
"outside the series' own normal", not a fitted number) and there are at least ``MIN_SAMPLE``
earlier observations for the standard deviation to mean anything (a statistical floor, not a
judgement about the data). A flat history (std 0) with any departure is unusual by definition.

Horizons (7d/30d/1y) shorter than the series' own median spacing are omitted — a 7-day change on a
monthly series would just be last month's change under another name.
"""

from __future__ import annotations

import math
from datetime import date, timedelta
from statistics import mean, median, pstdev
from typing import Any

from .contracts import Observation, Series, period_date

Z_LIMIT = 2.0
MIN_SAMPLE = 10
HORIZONS = (("7d", 7), ("30d", 30), ("1y", 365))
EXTREME_WINDOWS = (("30d", 30), ("90d", 90), ("1y", 365))
TRAILING_DAYS = 365

Point = tuple[date, float]


def _change(frm: Point, to: Point) -> dict[str, Any]:
    delta = to[1] - frm[1]
    return {"from_period": frm[0].isoformat(), "from_value": frm[1], "abs": delta,
            "pct": (delta / abs(frm[1]) * 100) if frm[1] else None}


def _steps(points: list[Point]) -> list[float]:
    """Period-over-period changes on a scale comparable across the series' history."""
    use_log = all(v > 0 for _, v in points)
    return [math.log(b[1] / a[1]) if use_log else b[1] - a[1] for a, b in zip(points, points[1:])]


def _z(x: float, sample: list[float]) -> float | None | str:
    """(x - mean) / std of ``sample``; None when the sample is too small, 'flat' when std is 0 and x departs."""
    if len(sample) < MIN_SAMPLE:
        return None
    sd = pstdev(sample)
    if sd == 0:
        return "flat" if x != sample[0] else 0.0
    return (x - mean(sample)) / sd


def beyond(z: float | None | str) -> bool:
    return z == "flat" or (isinstance(z, float) and abs(z) > Z_LIMIT)


def compute(points: list[Point], today: date | None = None) -> dict[str, Any] | None:
    """The moves for ``points`` (date, value) in ascending date order; None when empty."""
    if not points:
        return None
    latest = points[-1]
    spacing = median((b[0] - a[0]).days for a, b in zip(points, points[1:])) if len(points) > 1 else None
    out: dict[str, Any] = {
        "latest": {"period": latest[0].isoformat(), "value": latest[1]},
        "n_obs": len(points),
        "age_days": ((today or date.today()) - latest[0]).days,
        "changes": {},
    }
    if len(points) > 1:
        out["changes"]["prev"] = _change(points[-2], latest)
        for label, days in HORIZONS:
            if spacing is not None and days > spacing:
                ref = [p for p in points if p[0] <= latest[0] - timedelta(days=days)]
                if ref:
                    out["changes"][label] = _change(ref[-1], latest)

    window = [p for p in points[:-1] if p[0] > latest[0] - timedelta(days=TRAILING_DAYS)]
    trailing = [v for _, v in window] + [latest[1]]
    below = sum(v < latest[1] for v in trailing) + 0.5 * sum(v == latest[1] for v in trailing)
    out["percentile_1y"] = round(below / len(trailing) * 100, 1)

    steps = _steps(points)
    change_z = _z(steps[-1], steps[:-1]) if steps else None
    level_z = _z(latest[1], [v for _, v in window])
    long_z = _z(latest[1], [v for _, v in points[:-1]])
    reasons = [name for name, z in (("change", change_z), ("level", level_z)) if beyond(z)]
    out.update(change_z=_round(change_z), level_z=_round(level_z), long_run_z=_round(long_z),
               long_run_outside=beyond(long_z), unusual=bool(reasons), unusual_reasons=reasons)

    first = points[0][0]
    for key, pick in (("new_high", max), ("new_low", min)):
        out[key] = None
        for label, days in EXTREME_WINDOWS:
            prior = [v for d, v in points[:-1] if d > latest[0] - timedelta(days=days)]
            covered = first <= latest[0] - timedelta(days=days) and len(prior) >= 2
            # "at" the extreme, ties allowed: a collapse that has sat at its low for days is still AT
            # its low. A flat window has no extreme, so it never qualifies.
            if covered and latest[1] == pick(prior + [latest[1]]) and set(prior) != {latest[1]}:
                out[key] = label
    return out


def _round(z: float | None | str) -> float | None | str:
    return round(z, 2) if isinstance(z, float) else z


def series_moves(series: Series, observations: list[Observation], as_of: date | None = None,
                 today: date | None = None) -> dict[str, Any] | None:
    """Moves for one series as of ``as_of`` (default: everything stored), with its catalog identity."""
    pts = [(period_date(o.period), o.value) for o in observations]
    if as_of is not None:
        pts = [p for p in pts if p[0] <= as_of]
    body = compute(sorted(pts), today=as_of or today)
    if body is None:
        return None
    return {"series_id": series.id, "name": series.name, "unit": series.unit, "frequency": series.frequency,
            "source": series.source, "source_url": series.source_url, "public_display": series.public_display,
            "tags": series.tags, **body}
