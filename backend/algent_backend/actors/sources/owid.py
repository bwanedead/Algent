"""
Our World in Data energy dataset (CC BY 4.0) — one ~10 MB CSV, streamed line by line.

The file has a row per country-year and ~130 columns. Only the columns the catalog asks for are
kept, and for each (country, column) only the newest year that has a value: the full CSV is never
held in memory. Rows without a 3-letter ISO code (regions and income groups such as "Asia") and codes
the registry does not know (OWID_KOS) are skipped.
"""

from __future__ import annotations

import csv
from collections.abc import Iterable

from algent_backend.polite_http import stream_lines

from .. import registry
from ..catalog import HEADERS
from ..contracts import Indicator, Observation, now_iso

URL = "https://raw.githubusercontent.com/owid/energy-data/master/owid-energy-data.csv"
PAGE = "https://ourworldindata.org/energy"


def parse_rows(lines: Iterable[str], indicators: list[Indicator], fetched_at: str) -> list[Observation]:
    """Latest non-empty reading per (country, indicator) from CSV ``lines`` (header first)."""
    reader = csv.reader(lines)
    header = next(reader)
    col = {name: i for i, name in enumerate(header)}
    iso_i, year_i = col["iso_code"], col["year"]
    wanted = [(ind, col[ind.code]) for ind in indicators if ind.code in col]
    best: dict[tuple[str, str], Observation] = {}
    for row in reader:
        if len(row) <= max(iso_i, year_i) or len(row[iso_i]) != 3:
            continue
        iso2 = registry.iso2_of_iso3(row[iso_i])
        if iso2 is None:
            continue
        year = int(row[year_i])
        for ind, i in wanted:
            if i >= len(row) or row[i] == "":
                continue
            key = (iso2, ind.id)
            if key not in best or year > best[key].year:
                best[key] = Observation(iso2=iso2, indicator=ind.id, year=year, value=float(row[i]), source="owid",
                                        source_url=PAGE, fetched_at=fetched_at)
    return list(best.values())


def fetch(indicators: list[Indicator], today: object = None) -> dict[str, list[Observation] | str]:
    obs = parse_rows(stream_lines(URL, headers=HEADERS), indicators, now_iso())
    out: dict[str, list[Observation] | str] = {ind.id: [] for ind in indicators}
    for o in obs:
        out[o.indicator].append(o)        # type: ignore[union-attr]
    return out
