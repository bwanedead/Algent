"""
Where each live number comes from and how long we have been counting it, published inside ``live/summary.json`` (``provenance``).

The site's stats registry (sites/ohmega-monster/lib/stats) reads this instead of guessing: ``basis`` says whose count it is,
``since`` is the first day of OUR series (read from the instruments store, never typed in), ``history_days`` how many days that
is, and ``coverage_note`` why a count is a minimum. ``min_history_days`` is the backend's own maturity floor: live memory calls
any baseline younger than ``MIN_WEEKS`` weeks "learning" (confidence halved), so a day-count compared with "usual" is not
shown before the same age. Pure over the instruments store; a missing series just leaves its layer without a ``since``.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from algent_backend.instruments import store as istore
from algent_backend.instruments.contracts import period_date

from .memory import flags as memory_flags
from .regions import FIRE_BOXES, GATES, REGIONS


def _since(series_ids: list[str]) -> str:
    """Earliest period any of these series holds ('' when none has data yet)."""
    firsts = [o.period for sid in series_ids for o in istore.history(sid)[:1]]
    return min(firsts, default="")


def _layer(basis: str, ids: list[str], today: date, scope: str, coverage: str) -> dict[str, Any]:
    since = _since(ids)
    days = (today - period_date(since)).days if since else 0
    return {"basis": basis, "since": since, "history_days": days, "scope": scope, "coverage_note": coverage}


def build(today: date) -> dict[str, Any]:
    """``{layer: {basis, since, history_days, scope, coverage_note}, min_history_days}``; never raises (a store problem yields ``{}``)."""
    from algent_backend.instruments.live_series import ais_ids, fire_id, mil_ids

    try:
        return {
            "ships": _layer("our_count", [ais_ids(g.slug)[0] for g in GATES], today,
                            f"ships crossing {len(GATES)} counting lines ({', '.join(g.label for g in GATES)}), heard by volunteer coastal AIS receivers",
                            "A ship is counted only if a receiver heard it on both sides of the line; where receivers are sparse the count is far below the real traffic, so it is a minimum."),
            "aircraft": _layer("our_derived", [mil_ids(r.slug)[0] for r in REGIONS], today,
                               f"per day, the sum over {len(REGIONS)} watched regions of each region's peak number of military aircraft in the air at one moment (not unique aircraft)",
                               "Only aircraft broadcasting ADS-B to adsb.lol receivers; military flights often fly silent, so this is a minimum."),
            "fires": _layer("our_count", [fire_id(b.slug) for b in FIRE_BOXES], today,
                            f"satellite heat detections inside {len(FIRE_BOXES)} watched boxes ({', '.join(b.label for b in FIRE_BOXES)}), not the world",
                            "NASA FIRMS VIIRS passes a few times a day; cloud hides fires and a hotspot may be a wildfire or industrial flare."),
            "min_history_days": memory_flags.MIN_WEEKS * 7,
            "min_history_origin": f"live memory MIN_WEEKS={memory_flags.MIN_WEEKS} weeks: a baseline younger than this is 'learning'",
        }
    except Exception:                                     # provenance is context; it must never break the summary
        return {}
