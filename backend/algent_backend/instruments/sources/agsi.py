"""
GIE AGSI+ — EU gas storage fill (% full).

Verified 2026-10-04: the API answers HTTP 200 with ``"Invalid or missing API key"`` and no data
when called keyless — a key is required (free registration at agsi.gie.eu). So this provider
degrades honestly: with no key in the process environment (``ALGENT_AGSI_KEY``) it raises
``SourceUnavailable`` WITHOUT calling out, and the collector reports the series as blocked. The
response shape below follows GIE's published schema and is unverified against a live key.

Series params: ``type`` (``eu`` aggregate).
"""

from __future__ import annotations

import json
import os
from datetime import date, timedelta

from ..contracts import Observation, Series, now_iso
from ..http import SourceUnavailable, get

URL = "https://agsi.gie.eu/api"
KEY_ENV = "ALGENT_AGSI_KEY"


def parse(text: str, series: Series, fetched_at: str) -> list[Observation]:
    payload = json.loads(text)
    if payload.get("error"):
        raise SourceUnavailable(f"{URL}: {payload.get('message') or payload['error']}")
    return [
        Observation(series_id=series.id, period=row["gasDayStart"], value=float(row["full"]),
                    fetched_at=fetched_at, source_url=series.source_url)
        for row in payload.get("data", []) if row.get("full") not in (None, "", "-")
    ]


def fetch(series: Series, since: date | None) -> list[Observation]:
    key = os.environ.get(KEY_ENV)
    if not key:
        raise SourceUnavailable(f"{URL} needs an API key — set {KEY_ENV} (free at agsi.gie.eu)")
    start = since or date.today() - timedelta(days=30)
    text = get(URL, {"type": series.params.get("type", "eu"), "from": start.isoformat(),
                     "to": date.today().isoformat(), "size": 300}, headers={"x-key": key})
    return parse(text, series, now_iso())
