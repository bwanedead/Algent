"""
BIS central bank policy rates (free statistics, attribution) — one keyless CSV call for every central bank.

``/api/v1/data/WS_CBPOL/M../all?format=csv`` gives monthly end-of-period policy rates by ISO2 area. A year's
value is its latest month (the current year's is the latest reading so far, not a forecast). The euro area
("XM") is not a country: it is left out, so a euro member shows no policy rate here rather than a borrowed one.
"""

from __future__ import annotations

import csv
import math
from datetime import date

from algent_backend.polite_http import SourceError, get

from .. import registry
from ..catalog import HEADERS, HISTORY_YEARS
from ..contracts import Indicator, Observation, now_iso

API = "https://stats.bis.org/api/v1/data/WS_CBPOL/M../all"
PAGE = "https://data.bis.org/topics/CBPOL"


def parse_csv(text: str, indicator: Indicator, fetched_at: str) -> list[Observation]:
    """Year-end (latest month of each year) rate per country; non-countries and empty values dropped."""
    latest: dict[tuple[str, int], tuple[str, float]] = {}
    for row in csv.DictReader(text.splitlines()):
        country = registry.get(row.get("REF_AREA", ""))
        period, value = row.get("TIME_PERIOD", ""), row.get("OBS_VALUE", "")
        if country is None or not value or len(period) < 7 or not math.isfinite(float(value)):    # BIS writes "NaN"
            continue
        key = (country.iso2, int(period[:4]))
        if key not in latest or period > latest[key][0]:
            latest[key] = (period, float(value))
    return [Observation(iso2=iso2, indicator=indicator.id, year=year, value=v, source="bis", source_url=PAGE,
                        fetched_at=fetched_at) for (iso2, year), (_, v) in latest.items()]


def fetch(indicators: list[Indicator], today: date | None = None) -> dict[str, list[Observation] | str]:
    start = (today or date.today()).year - HISTORY_YEARS
    out: dict[str, list[Observation] | str] = {}
    for ind in indicators:
        try:
            out[ind.id] = parse_csv(get(API, {"format": "csv", "startPeriod": f"{start}-01"}, headers=HEADERS),
                                    ind, now_iso())
        except (SourceError, ValueError) as exc:
            out[ind.id] = str(exc)
    return out
