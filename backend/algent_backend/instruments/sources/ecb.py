"""
ECB data portal (SDMX, ``csvdata`` format) — euro reference exchange rates and policy rates.

Free to reuse with attribution (ECB statistics copyright notice). One generic module: a series
names the dataflow and key; the CSV always carries ``TIME_PERIOD`` and ``OBS_VALUE``.

Series params: ``flow`` (e.g. ``EXR``), ``key`` (e.g. ``D.USD.EUR.SP00.A``).
"""

from __future__ import annotations

import csv
import io
from datetime import date

from ..contracts import Observation, Series, now_iso
from algent_backend.polite_http import get

BASE = "https://data-api.ecb.europa.eu/service/data"


def parse(text: str, series: Series, fetched_at: str) -> list[Observation]:
    return [
        Observation(series_id=series.id, period=row["TIME_PERIOD"], value=float(row["OBS_VALUE"]),
                    fetched_at=fetched_at, source_url=series.source_url)
        for row in csv.DictReader(io.StringIO(text)) if row.get("OBS_VALUE")
    ]


def fetch(series: Series, since: date | None) -> list[Observation]:
    p = series.params
    query = {"format": "csvdata", **({"startPeriod": since.isoformat()} if since else {"lastNObservations": 30})}
    return parse(get(f"{BASE}/{p['flow']}/{p['key']}", query), series, now_iso())
