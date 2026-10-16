"""
Daily rollups — a COMPLETED UTC day of hour values becomes one observation per watched place in the instruments store
(``live_mem_<kind>_<slug>_<name>``: the mean number of ships / tankers / naval ships / military aircraft present).

These are the compact, long-lived form of the hourly detail: the hour files are deleted after 60 days, these stay, and
``live/publish.py`` sends the recent ones to the site's ``live_stats``. A day with fewer than ``DAY_MIN_HOURS`` observed hours is
skipped, never written as a low day (a service outage is not a quiet strait). Forward-only: only days memory itself observed.
"""

from __future__ import annotations

from datetime import datetime, timezone

from algent_backend.instruments import store as istore
from algent_backend.instruments.contracts import Observation, now_iso

from . import flags, hours
from .areas import DAILY, daily_series


def rollup_day(day: int) -> dict[str, int]:
    """Append day ``day`` (epoch day) of every watched place's presence. Idempotent; returns ``{"observed_hours", "written"}``."""
    from algent_backend.instruments.catalog import get_series

    hrs = [h for h in (hours.read_hour(x) for x in hours.day_hours(day)) if h.observed("stream", flags.MIN_HOUR_SAMPLES)]
    if len(hrs) < flags.DAY_MIN_HOURS:
        return {"observed_hours": len(hrs), "written": 0}
    period = datetime.fromtimestamp(day * 86400, tz=timezone.utc).date().isoformat()
    written = 0
    for sid, area, name in daily_series():
        series = DAILY[name][0]
        mean = sum(h.values.get(series, {}).get(area.id, 0.0) for h in hrs) / len(hrs)
        res = istore.append(sid, [Observation(series_id=sid, period=period, value=round(mean, 2), fetched_at=now_iso(),
                                              source_url=get_series(sid).source_url)])
        written += res.new + res.revised
    return {"observed_hours": len(hrs), "written": written}
