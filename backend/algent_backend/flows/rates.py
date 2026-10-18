"""
Rates — the tracker's daily aggregates read as per-day rates over rolling windows, and a place's latest day judged against its own normal.

A rate is a count divided by the time the tracker was actually watching (``secs`` per day), expressed per 24 hours: a day the service
was down for half of it neither halves the rate nor reads as a collapse. The anomaly reuses live memory's robust modified z
(``live/memory/robust.py``) with the same cut (``live/memory/flags.Z_ENTER``): the latest complete watched day's visit rate against the
median and spread of the place's earlier watched days; a place with fewer than ``ANOMALY_MIN_DAYS`` of them is not scored yet.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from algent_backend.live.memory import flags as memory_flags
from algent_backend.live.memory import robust

from . import flags
from .tracker import day_of


def _window(days: dict[str, dict[str, Any]], now: float, window: int) -> tuple[list[dict[str, Any]], float]:
    """The day records inside the last ``window`` calendar days (today included) and the seconds watched across them."""
    today = date.fromisoformat(day_of(now))
    first = (today - timedelta(days=window - 1)).isoformat()
    recs = [v for d, v in days.items() if d >= first]
    return recs, sum(v["secs"] for v in recs)


def lane_rates(days: dict[str, dict[str, Any]], now: float, window: int) -> dict[str, dict[str, Any]]:
    """``{"a>b": {"by": {class: per-day rate}, "n": count, "inf": inferred count}}`` over the window (empty when nothing was watched)."""
    recs, secs = _window(days, now, window)
    if secs <= 0:
        return {}
    scale = 86400.0 / secs
    out: dict[str, dict[str, Any]] = {}
    for rec in recs:
        for key, by in rec["lanes"].items():
            slot = out.setdefault(key, {"by": {}, "n": 0, "inf": 0})
            for cls, (obs, inf) in by.items():
                slot["by"][cls] = slot["by"].get(cls, 0) + obs + inf
                slot["n"] += obs + inf
                slot["inf"] += inf
    for slot in out.values():
        slot["by"] = {c: round(n * scale, 2) for c, n in slot["by"].items()}
    return out


def visit_rates(days: dict[str, dict[str, Any]], now: float, window: int) -> dict[str, dict[str, Any]]:
    """``{place: {"by": {class: per-day rate}, "n": count}}`` of ships entering each place over the window."""
    recs, secs = _window(days, now, window)
    if secs <= 0:
        return {}
    scale = 86400.0 / secs
    out: dict[str, dict[str, Any]] = {}
    for rec in recs:
        for place, by in rec["visits"].items():
            slot = out.setdefault(place, {"by": {}, "n": 0})
            for cls, n in by.items():
                slot["by"][cls] = slot["by"].get(cls, 0) + n
                slot["n"] += n
    for slot in out.values():
        slot["by"] = {c: round(n * scale, 2) for c, n in slot["by"].items()}
    return out


def _watched_series(days: dict[str, dict[str, Any]], now: float) -> dict[str, dict[str, float]]:
    """``{place: {day: visits per 24 h}}`` over the complete days (before today) the tracker watched for most of the day."""
    today = day_of(now)
    out: dict[str, dict[str, float]] = {}
    for d, rec in days.items():
        if d >= today or rec["secs"] < flags.WATCHED_SHARE * 86400:
            continue
        for place, by in rec["visits"].items():
            out.setdefault(place, {})[d] = sum(by.values()) * 86400.0 / rec["secs"]
    return out


def anomalies(days: dict[str, dict[str, Any]], now: float) -> dict[str, dict[str, Any]]:
    """Per place with enough history: ``{"usual", "last", "day", "z", "dir" | None}`` (``dir`` is "above"/"below" when the latest day is
    outside the place's normal, else None). A place with a day missing from the watched record simply has fewer values."""
    watched = {d for d, rec in days.items() if rec["secs"] >= flags.WATCHED_SHARE * 86400 and d < day_of(now)}
    out: dict[str, dict[str, Any]] = {}
    if not watched:
        return out
    latest = max(watched)
    series = _watched_series(days, now)
    for place, by_day in series.items():
        earlier = [by_day.get(d, 0.0) for d in sorted(watched) if d < latest][-30:]      # a watched day without the place is a zero
        if len(earlier) < flags.ANOMALY_MIN_DAYS:
            continue
        normal = robust.normal_of(earlier)
        assert normal is not None
        value = by_day.get(latest, 0.0)                # a place not seen at all on the latest watched day had none
        z = robust.score(value, normal)
        direction = "above" if z >= memory_flags.Z_ENTER else "below" if z <= -memory_flags.Z_ENTER else None
        out[place] = {"usual": round(normal.median, 2), "last": round(value, 2), "day": latest, "z": round(z, 2), "dir": direction}
    return out
