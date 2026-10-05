"""
US Treasury daily par yield curve (XML, one document per month).

Public-domain US government data. The feed is OData-in-Atom; each ``<m:properties>`` block is one
day with ``BC_<tenor>`` columns, so both the 2y and 10y catalog series read the same memoised
month documents.

Series params: ``column`` (e.g. ``BC_10YEAR``).
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import date

from ..contracts import Observation, Series, now_iso
from algent_backend.polite_http import get

URL = "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml"
_D = "{http://schemas.microsoft.com/ado/2007/08/dataservices}"
_M = "{http://schemas.microsoft.com/ado/2007/08/dataservices/metadata}"


def parse(text: str, series: Series, fetched_at: str) -> list[Observation]:
    root = ET.fromstring(text.encode("utf-8") if text.lstrip().startswith("<?xml") else text)
    column = series.params["column"]
    out = []
    for props in root.iter(f"{_M}properties"):
        day, val = props.findtext(f"{_D}NEW_DATE"), props.findtext(f"{_D}{column}")
        if day and val and val.strip():
            out.append(Observation(series_id=series.id, period=day[:10], value=float(val),
                                   fetched_at=fetched_at, source_url=series.source_url))
    return out


def _months(since: date | None, today: date) -> list[str]:
    """YYYYMM for each month from ``since`` to now; with no ``since``, this month and last (the
    previous one so a fetch on the 1st still has data to compare against)."""
    y, m = (today.year, today.month - 1) if since is None else (since.year, since.month)
    if m == 0:
        y, m = y - 1, 12
    months = []
    while (y, m) <= (today.year, today.month):
        months.append(f"{y}{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return months


def fetch(series: Series, since: date | None) -> list[Observation]:
    fetched_at, out = now_iso(), []
    for month in _months(since, date.today()):
        text = get(URL, {"data": "daily_treasury_yield_curve", "field_tdr_date_value_month": month})
        out.extend(parse(text, series, fetched_at))
    return out
