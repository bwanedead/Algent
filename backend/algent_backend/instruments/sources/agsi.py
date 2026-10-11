"""
GIE AGSI+ — EU gas storage fill (% full).

Verified 2026-10-04: the API answers HTTP 200 with ``"Invalid or missing API key"`` and no data
when called keyless — a key is required (free registration at agsi.gie.eu). So this provider
degrades honestly: with no key in the process environment (``ALGENT_AGSI_KEY``) it raises
``SourceUnavailable`` WITHOUT calling out, and the collector reports the series as blocked. The
response shape below follows GIE's published schema and is unverified against a live key.

Series params: ``type`` (``eu`` aggregate), ``field`` (default ``full``, the % full; the ALSI sibling reads ``sendOut`` etc.).
A first fetch (nothing stored) backfills ``BACKFILL_DAYS`` of history so "same date in earlier years" has something to compare
with; pages of 300 days are walked until the API says there are no more (``MAX_PAGES`` bounds it). GIE asks that its data be
credited wherever it is shown (the /live energy panel does: "Source: GIE AGSI+").
"""

from __future__ import annotations

import json
import os
from datetime import date, timedelta

from ..contracts import Observation, Series, now_iso
from algent_backend.polite_http import SourceUnavailable, get

URL = "https://agsi.gie.eu/api"
KEY_ENV = "ALGENT_AGSI_KEY"
BACKFILL_DAYS = 5 * 365 + 10
MAX_PAGES = 8
PAGE_SIZE = 300


def parse(text: str, series: Series, fetched_at: str) -> list[Observation]:
    payload = json.loads(text)
    field = series.params.get("field", "full")
    if payload.get("error"):
        raise SourceUnavailable(f"{URL}: {payload.get('message') or payload['error']}")
    return [
        Observation(series_id=series.id, period=row["gasDayStart"], value=float(row[field]),
                    fetched_at=fetched_at, source_url=series.source_url)
        for row in payload.get("data", []) if row.get(field) not in (None, "", "-")
    ]


def fetch_pages(url: str, series: Series, since: date | None) -> list[Observation]:
    """Every observation from ``since`` (default: ``BACKFILL_DAYS`` ago) to today, walking GIE's pages (newest first)."""
    key = os.environ.get(KEY_ENV)
    if not key:
        raise SourceUnavailable(f"needs AGSI key (free registration at agsi.gie.eu): set {KEY_ENV}")
    start = since or date.today() - timedelta(days=BACKFILL_DAYS)
    out: list[Observation] = []
    for page in range(1, MAX_PAGES + 1):
        text = get(url, {"type": series.params.get("type", "eu"), "from": start.isoformat(), "to": date.today().isoformat(),
                         "size": PAGE_SIZE, "page": page}, headers={"x-key": key})
        out += parse(text, series, now_iso())
        if page >= int(json.loads(text).get("last_page") or 1):
            break
    return out


def fetch(series: Series, since: date | None) -> list[Observation]:
    return fetch_pages(URL, series, since)
