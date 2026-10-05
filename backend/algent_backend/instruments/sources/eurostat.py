"""
Eurostat dissemination API (JSON-stat 2.0) — euro-area inflation and other statistics.

Free to reuse with attribution (Eurostat copyright policy). JSON-stat stores values in a flat
``value`` map indexed by position in the cube; the catalog pins every dimension except time to one
member, so the flat index equals the time position (checked, not assumed).

Series params: ``dataset`` (e.g. ``prc_hicp_manr``), ``filters`` (dimension -> member).
"""

from __future__ import annotations

import json
from datetime import date

from ..contracts import Observation, Series, now_iso
from algent_backend.polite_http import SourceError, get

BASE = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data"


def parse(text: str, series: Series, fetched_at: str) -> list[Observation]:
    cube = json.loads(text)
    if any(n != 1 for dim, n in zip(cube["id"], cube["size"]) if dim != "time"):
        raise SourceError(f"{BASE}/{series.params['dataset']}: filters leave more than a time axis")
    times = cube["dimension"]["time"]["category"]["index"]          # {"2025-09": 0, ...}
    values = cube.get("value", {})
    return [
        Observation(series_id=series.id, period=period, value=float(values[str(i)]),
                    fetched_at=fetched_at, source_url=series.source_url)
        for period, i in sorted(times.items(), key=lambda kv: kv[1]) if str(i) in values
    ]


def fetch(series: Series, since: date | None) -> list[Observation]:
    p = series.params
    window = {"sinceTimePeriod": since.strftime("%Y-%m")} if since else {"lastTimePeriod": 14}
    text = get(f"{BASE}/{p['dataset']}", {**p["filters"], **window})
    return parse(text, series, now_iso())
