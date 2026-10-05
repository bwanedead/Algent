"""
IMF DataMapper (World Economic Outlook) — keyless JSON, one call per series: ``{"values": {CODE: {ISO3: {year: value}}}}``.

Only the previous and current calendar year are kept: the WEO carries decades of history and a
forecast tail, and what a profile wants is "what the IMF now thinks this year is". An HTTP 403 raises
``SourceUnavailable`` (the collector records the source as blocked; nothing else is affected).
"""

from __future__ import annotations

import json
from datetime import date
from typing import Any

from algent_backend.polite_http import SourceError, get

from .. import registry
from ..catalog import HEADERS
from ..contracts import Indicator, Observation, now_iso

API = "https://www.imf.org/external/datamapper/api/v1"


def parse_series(payload: Any, indicator: Indicator, years: tuple[int, ...], fetched_at: str) -> list[Observation]:
    values = ((payload or {}).get("values") or {}).get(indicator.code)
    if not isinstance(values, dict):
        raise SourceError(f"IMF {indicator.code}: no values in payload")
    out = []
    for iso3, by_year in values.items():
        iso2 = registry.iso2_of_iso3(iso3)            # regional aggregates ("ADVEC", "WEOWORLD") are not in the table
        if iso2 is None or not isinstance(by_year, dict):
            continue
        for year in years:
            v = by_year.get(str(year))
            if isinstance(v, (int, float)):
                out.append(Observation(iso2=iso2, indicator=indicator.id, year=year, value=float(v), source="imf",
                                       source_url=f"https://www.imf.org/external/datamapper/{indicator.code}@WEO",
                                       fetched_at=fetched_at))
    return out


def fetch(indicators: list[Indicator], today: date | None = None) -> dict[str, list[Observation] | str]:
    this_year = (today or date.today()).year
    fetched_at, out = now_iso(), {}
    for ind in indicators:
        body = get(f"{API}/{ind.code}", headers=HEADERS)                # SourceUnavailable (403) propagates: the whole source is blocked
        try:
            out[ind.id] = parse_series(json.loads(body), ind, (this_year - 1, this_year), fetched_at)
        except (SourceError, ValueError) as exc:
            out[ind.id] = str(exc)
    return out
