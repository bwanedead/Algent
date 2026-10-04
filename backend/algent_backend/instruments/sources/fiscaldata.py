"""
US Treasury FiscalData — "Debt to the Penny" (total public debt outstanding, business days).

Public-domain US government data, keyless JSON. Amounts arrive as strings of whole dollars; the
series divides by ``scale`` so the stored unit is readable (trillions).

Series params: ``field`` (e.g. ``tot_pub_debt_out_amt``), ``scale`` (divisor, default 1).
"""

from __future__ import annotations

import json
from datetime import date

from ..contracts import Observation, Series, now_iso
from ..http import get

URL = "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v2/accounting/od/debt_to_penny"
PAGE = 1000


def parse(text: str, series: Series, fetched_at: str) -> list[Observation]:
    field, scale = series.params["field"], float(series.params.get("scale", 1))
    return [
        Observation(series_id=series.id, period=row["record_date"], value=float(row[field]) / scale,
                    fetched_at=fetched_at, source_url=series.source_url)
        for row in json.loads(text).get("data", []) if row.get(field) not in (None, "", "null")
    ]


def fetch(series: Series, since: date | None) -> list[Observation]:
    days = 30 if since is None else (date.today() - since).days + 5
    text = get(URL, {"sort": "-record_date", "page[size]": min(PAGE, max(days, 5))})
    return parse(text, series, now_iso())
