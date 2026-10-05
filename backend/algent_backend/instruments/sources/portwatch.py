"""
IMF PortWatch — daily vessel transits through the world's chokepoints (satellite AIS derived).

The decisive free evidence for shipping-dependent situations (Hormuz, Red Sea): a count of ships
that actually passed, not a headline about a threat. ArcGIS feature service, keyless, history back
to 2019, ~1-week publication lag. One query serves both ``n_total`` and ``n_tanker`` for a port, so
the two catalog series share one memoised response.

Series params: ``port`` (exact ``portname`` — see the catalog), ``field`` (``n_total`` | ``n_tanker``).
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone

from ..contracts import Observation, Series, now_iso
from algent_backend.polite_http import SourceError, get

URL = (
    "https://services9.arcgis.com/weJ1QsnbMYJlCHdG/arcgis/rest/services/"
    "Daily_Chokepoints_Data/FeatureServer/0/query"
)
PAGE = 1000          # the service's own maximum records per request
DEFAULT_DAYS = 120   # no ``since``: a quarter-ish of recent days, enough to refresh and re-judge


def _day(raw: object) -> str:
    """The ``date`` attribute arrives as an ISO string or as epoch milliseconds."""
    if isinstance(raw, (int, float)):
        return datetime.fromtimestamp(raw / 1000, tz=timezone.utc).date().isoformat()
    return str(raw)[:10]


def parse(text: str, series: Series, fetched_at: str) -> list[Observation]:
    payload = json.loads(text)
    if "error" in payload:
        raise SourceError(f"{URL}: {payload['error']}")
    field = series.params["field"]
    out = []
    for feat in payload.get("features", []):
        attrs = feat.get("attributes", {})
        if attrs.get(field) is None or attrs.get("date") is None:
            continue
        out.append(Observation(
            series_id=series.id, period=_day(attrs["date"]), value=float(attrs[field]),
            fetched_at=fetched_at, source_url=series.source_url,
        ))
    return out


def fetch(series: Series, since: date | None) -> list[Observation]:
    port = series.params["port"]
    want = DEFAULT_DAYS if since is None else max((date.today() - since).days + 5, 5)
    fetched_at, out, offset = now_iso(), [], 0
    while offset < want:
        text = get(URL, {
            "where": f"portname='{port}'", "outFields": "date,portname,n_total,n_tanker,capacity",
            "orderByFields": "date DESC", "resultRecordCount": min(PAGE, want - offset),
            "resultOffset": offset, "f": "json",
        })
        page = parse(text, series, fetched_at)
        out.extend(page)
        if len(json.loads(text).get("features", [])) < min(PAGE, want - offset):
            break
        offset += PAGE
    return out
