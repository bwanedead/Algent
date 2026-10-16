"""
Anomalies as desk input — the ``OHMEGA LIVE ANOMALIES`` block a section writer sees, the sweep's version, and the per-theater
daily rollup record that makes the record compound.

Same stance as ``live/desk.py`` (events) and the grid block: sensing decides which countries a theater stands behind
(``sensing.corroborated``); this module only knows the current anomalies and renders the ones touching those countries. They are
Ohmega's own derivation (provenance ``ohmega_derived``): a daily may cite them as "Ohmega analysis of live ship / aircraft / satellite feeds",
never as something a source reported. Reads the local store only; never the network.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime, timedelta, timezone

from . import flags
from .anomalies import Anomaly, anomaly_dir, read_current
from .areas import AREAS

LIVE_URL = "https://www.ohmega.monster/live"
_HEAD = ("OHMEGA LIVE ANOMALIES - computed by Ohmega (no model) by comparing live ship, aircraft and satellite-fire counts with Ohmega's own "
         "learned normal for that place and hour of the week; cite them as \"Ohmega analysis\". They say a pattern departs from normal, not why "
         "(a closed port, a rerouting, a sensor gap we could not screen out, an exercise all look alike); gaps in receiver coverage are screened out, "
         "and one marked LEARNING rests on a young baseline:")


def _recent(a: Anomaly, now: datetime) -> bool:
    """Still going, or ended within the last day (a daily written this morning should still see last night's closure)."""
    return a.ends_at is None or a.ends_at >= (now - timedelta(days=1)).isoformat(timespec="seconds")


def _line(a: Anomaly) -> str:
    state = "ongoing" if a.ends_at is None else f"ended {a.ends_at[:16].replace('T', ' ')} UTC"
    young = ", LEARNING baseline" if a.learning else ""
    return f"- {a.sentence} (since {a.starts_at[:16].replace('T', ' ')} UTC, {state}; confidence {a.confidence:.0%}{young})"


def _block(hit: list[Anomaly], limit: int) -> tuple[str, set[str], int]:
    hit = sorted(hit, key=lambda a: (-a.confidence, -a.score))[:limit]
    return ("\n".join([_HEAD, *map(_line, hit)]), {LIVE_URL}, len(hit)) if hit else ("", set(), 0)


def touching(countries: set[str], now: datetime | None = None) -> list[Anomaly]:
    now = now or datetime.now(timezone.utc)
    return [a for a in read_current() if _recent(a, now) and set(a.countries) & countries]


def block(countries: set[str], now: datetime | None = None) -> tuple[str, set[str], int]:
    """(text, source urls, n lines) for the anomalies touching ``countries`` ('' when none)."""
    return _block(touching(countries, now), flags.DESK_LINES)


def block_all(now: datetime | None = None) -> tuple[str, set[str], int]:
    """The strongest anomalies anywhere (the world sweep's material)."""
    now = now or datetime.now(timezone.utc)
    return _block([a for a in read_current() if _recent(a, now)], flags.SWEEP_LINES)


def country_names() -> set[str]:
    return {c for a in read_current() for c in a.countries}


def for_theater(corroborate: Callable[[Callable[[str], set[str]]], set[str]], find_in: Callable[[str, set[str]], set[str]]
                ) -> tuple[str, set[str], int, set[str]]:
    """Glue for sensing: (text, urls, n lines, the countries the theater stands behind that we watch)."""
    names = {c for a in AREAS for c in a.countries} | country_names()
    stood = corroborate(lambda text: find_in(text, names))
    return (*block(stood), stood)


# ── the corpus record ───────────────────────────────────────────────────────────────────────────
def theater_rollup(countries: set[str], day: str, now: datetime | None = None) -> dict:
    """What was normal and abnormal across the watched places a theater touches on ``day``: abnormal = the anomalies there, normal = the
    named areas (chokepoints, aircraft regions, fire-watch boxes) in its countries that had none. {} when we watch nothing there."""
    hit = touching(countries, now)
    watched = [a for a in AREAS if set(a.countries) & countries]
    if not watched and not hit:
        return {}
    flagged = {a.place_id for a in hit}
    return {"day": day, "provenance": "ohmega_derived", "countries": sorted(countries & ({c for a in AREAS for c in a.countries} | {c for a in hit for c in a.countries})),
            "abnormal": [{"id": a.id, "sentence": a.sentence, "series": a.series, "direction": a.direction, "confidence": a.confidence,
                          "since": a.starts_at, "ongoing": a.ends_at is None, "learning": a.learning} for a in hit],
            "normal": [a.label for a in watched if a.id not in flagged]}


def record_theater_day(theater_id: str, rollup: dict) -> None:
    """Append the rollup to the compounding record (``anomalies/theater_days.jsonl``). Never raises."""
    if not rollup:
        return
    try:
        path = anomaly_dir() / "theater_days.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps({"theater": theater_id, **rollup}, ensure_ascii=False, separators=(",", ":")) + "\n")
    except OSError:
        pass
