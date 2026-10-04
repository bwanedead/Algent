"""
Yahoo Finance chart API — daily closes for futures, indices and FX pairs.

UNOFFICIAL endpoint (no published terms for this API), so series using it are catalogued
``public_display=False``: internal signal for the desk until the terms are reviewed. It rejects
non-browser clients, hence the shared browser User-Agent. The most recent bar is the live
session, so it legitimately gets revised on later fetches until the day closes — the store's
revision lines record that.

Series params: ``symbol`` (e.g. ``BZ=F``).
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone

from ..contracts import Observation, Series, now_iso
from ..http import SourceError, get

URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
# The API takes named ranges only; pick the smallest that covers what was asked for.
_RANGES = ((30, "1mo"), (90, "3mo"), (180, "6mo"), (365, "1y"), (730, "2y"), (1825, "5y"))


def range_for(since: date | None, today: date | None = None) -> str:
    if since is None:
        return "1mo"
    days = ((today or date.today()) - since).days
    return next((name for limit, name in _RANGES if days <= limit), "10y")


def parse(text: str, series: Series, fetched_at: str) -> list[Observation]:
    chart = json.loads(text).get("chart", {})
    if chart.get("error"):
        raise SourceError(f"{URL.format(symbol=series.params['symbol'])}: {chart['error']}")
    results = chart.get("result") or []
    if not results:
        return []
    res = results[0]
    offset = timedelta(seconds=res.get("meta", {}).get("gmtoffset", 0))   # bar date in exchange-local time
    closes = res.get("indicators", {}).get("quote", [{}])[0].get("close", [])
    out = []
    for ts, close in zip(res.get("timestamp", []), closes):
        if close is None:
            continue
        day = (datetime.fromtimestamp(ts, tz=timezone.utc) + offset).date().isoformat()
        out.append(Observation(series_id=series.id, period=day, value=round(float(close), 6),
                               fetched_at=fetched_at, source_url=series.source_url))
    return out


def fetch(series: Series, since: date | None) -> list[Observation]:
    url = URL.format(symbol=series.params["symbol"])
    text = get(url, {"range": range_for(since), "interval": "1d"})
    return parse(text, series, now_iso())
