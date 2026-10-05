"""
World Bank Open Data (WDI, CC BY 4.0) — one bulk call per indicator for every country.

``/v2/country/all/indicator/<code>?mrnev=5`` returns each country's five most recent non-empty values
(aggregates such as "World" come back in the same payload and are dropped: only ISO3 codes in the
registry survive). The same endpoint family serves the country list the registry is seeded from.
"""

from __future__ import annotations

import json
from typing import Any

from algent_backend.polite_http import SourceError, get

from .. import registry
from ..catalog import HEADERS
from ..contracts import Indicator, Observation, now_iso

API = "https://api.worldbank.org/v2"
MOST_RECENT = 5                       # non-empty values per country: enough to see a revision, small to pull


def indicator_url(code: str) -> str:
    return f"https://data.worldbank.org/indicator/{code}"


def parse_indicator(payload: Any, indicator: Indicator, fetched_at: str) -> list[Observation]:
    """Observations from a WDI indicator payload ``[meta, rows]``; empty values and non-registry codes dropped."""
    if not isinstance(payload, list) or len(payload) < 2 or not isinstance(payload[1], list):
        message = payload[0].get("message") if isinstance(payload, list) and payload and isinstance(payload[0], dict) else payload
        raise SourceError(f"World Bank {indicator.code}: unexpected payload {str(message)[:120]}")
    out = []
    for row in payload[1]:
        iso2 = registry.iso2_of_iso3(row.get("countryiso3code") or "")
        if iso2 is None or row.get("value") is None:
            continue
        out.append(Observation(iso2=iso2, indicator=indicator.id, year=int(row["date"]), value=float(row["value"]),
                               source="wb", source_url=indicator_url(indicator.code), fetched_at=fetched_at))
    return out


def fetch(indicators: list[Indicator], today: object = None) -> dict[str, list[Observation] | str]:
    """{indicator id: observations | error message}; one failing indicator never stops the others."""
    out: dict[str, list[Observation] | str] = {}
    fetched_at = now_iso()
    for ind in indicators:
        try:
            body = get(f"{API}/country/all/indicator/{ind.code}",
                       {"format": "json", "per_page": 20000, "mrnev": MOST_RECENT}, headers=HEADERS)
            out[ind.id] = parse_indicator(json.loads(body), ind, fetched_at)
        except (SourceError, ValueError) as exc:
            out[ind.id] = str(exc)
    return out


def fetch_countries() -> list[dict[str, Any]]:
    """The raw World Bank country list (aggregates included) — input to ``registry.build_rows``."""
    payload = json.loads(get(f"{API}/country", {"format": "json", "per_page": 400}, headers=HEADERS))
    return payload[1]
