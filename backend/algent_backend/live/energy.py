"""
The /live energy panel's document (``live/energy.json``): EU gas storage against the same date in earlier years, LNG terminal
send-out, and the headline energy prices as compact tiles. Pure computation over the instruments store; a series with no data
yet is simply left out. GIE (AGSI, ALSI) requires a visible source credit on any display; the document carries the credit text and
link so the page cannot forget it.

Prices come from the Yahoo-backed instruments (delayed, an unofficial endpoint whose terms are unreviewed: the catalog keeps
them ``public_display=False`` for the desk). Showing them here is the operator's call; ``flags.ENERGY_TILES`` is the one place
to take them off the page.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from algent_backend.instruments import store as istore
from algent_backend.instruments.catalog import get_series
from algent_backend.instruments.contracts import period_date

from . import flags
from .contracts import iso

SPARK_DAYS = 120
LNG_DAYS = 60
TILE_DAYS = 30
YEARS_BACK = 5
SAME_DATE_TOLERANCE = 3        # days: gas days are daily, but a gap or a revision should not hide a year


def _history(series_id: str) -> dict[date, float]:
    return {period_date(o.period): o.value for o in istore.history(series_id)}


def _near(h: dict[date, float], d: date, tol: int) -> float | None:
    for off in sorted(range(-tol, tol + 1), key=abs):
        v = h.get(d + timedelta(days=off))
        if v is not None:
            return v
    return None


def _years_ago(d: date, k: int) -> date:
    try:
        return d.replace(year=d.year - k)
    except ValueError:                      # 29 Feb
        return d.replace(year=d.year - k, day=28)


def _credit(series_id: str) -> dict[str, str]:
    s = get_series(series_id)
    return {"source": s.source, "source_url": s.source_url}


def gas_storage(h: dict[date, float]) -> dict[str, Any] | None:
    """Fill now, the same date in each earlier year, and the spark with the earlier years' range behind it."""
    if not h:
        return None
    last = max(h)
    years = []
    for k in range(1, YEARS_BACK + 1):
        v = _near(h, _years_ago(last, k), SAME_DATE_TOLERANCE)
        if v is not None:
            years.append({"year": last.year - k, "value": round(v, 1)})
    spark, band = [], []
    for i in range(SPARK_DAYS - 1, -1, -1):
        d = last - timedelta(days=i)
        v = _near(h, d, 0)
        spark.append(None if v is None else round(v, 1))
        past = [x for k in range(1, YEARS_BACK + 1) if (x := _near(h, _years_ago(d, k), 1)) is not None]
        band.append([round(min(past), 1), round(max(past), 1)] if len(past) >= 2 else None)
    week = _near(h, last - timedelta(days=7), 1)
    return {"as_of_day": last.isoformat(), "value": round(h[last], 1), "week_change": None if week is None else round(h[last] - week, 1),
            "years": years, "spark": spark, "band": band}


def series_block(h: dict[date, float], days: int) -> dict[str, Any] | None:
    if not h:
        return None
    last = max(h)
    recent = [round(v, 1) for d, v in sorted(h.items()) if d > last - timedelta(days=days)]
    prior = [v for d, v in h.items() if last - timedelta(days=31) < d < last]
    return {"as_of_day": last.isoformat(), "value": round(h[last], 1), "spark": recent,
            "avg_30d": round(sum(prior) / len(prior), 1) if prior else None}


def tile(series_id: str, label: str) -> dict[str, Any] | None:
    h = _history(series_id)
    if not h:
        return None
    days = sorted(h)
    last, prev = h[days[-1]], h[days[-2]] if len(days) > 1 else None
    s = get_series(series_id)
    return {"id": series_id, "label": label, "unit": s.unit, "value": round(last, 2), "as_of_day": days[-1].isoformat(),
            "change_pct": None if not prev else round((last - prev) / prev * 100, 2),
            "spark": [round(h[d], 2) for d in days[-TILE_DAYS:]], **_credit(series_id)}


def build(now: datetime) -> dict[str, Any] | None:
    """The energy document, or None when no energy series has any data yet."""
    gas = gas_storage(_history("gas_eu_storage"))
    sendout = series_block(_history("lng_eu_sendout"), LNG_DAYS)
    full = series_block(_history("lng_eu_full"), LNG_DAYS)
    tiles = [t for sid, label in flags.ENERGY_TILES if (t := tile(sid, label))]
    if not (gas or sendout or full or tiles):
        return None
    return {"v": 1, "as_of": iso(now), "gas": gas, "lng": {"sendout": sendout, "full": full} if sendout or full else None, "tiles": tiles,
            "credits": {"gas": {"text": "Source: GIE AGSI+", "url": "https://agsi.gie.eu/"},
                        "lng": {"text": "Source: GIE ALSI", "url": "https://alsi.gie.eu/"}}}
