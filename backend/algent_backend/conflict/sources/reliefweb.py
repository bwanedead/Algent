"""
ReliefWeb reports (UN OCHA) — humanitarian reports about attacks and their toll. KEYED: since late 2025 the API refuses an `appname` that
ReliefWeb has not approved (HTTP 403). Request one at https://apidoc.reliefweb.int/parameters#appname and set ``ALGENT_RELIEFWEB_APPNAME``.

A report is not an event count: each becomes one ``report`` row, country-level (no coordinates), basis ``official`` (the publishing
organisation's own words). Fatalities are never read out of the headline.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Callable

from ..contracts import COVERAGE, ConflictEvent, event_id
from . import NeedsKey, country_iso, env

URL = "https://api.reliefweb.int/v2/reports"
KEY_ENV = "ALGENT_RELIEFWEB_APPNAME"
SIGNUP = "https://apidoc.reliefweb.int/parameters#appname"
QUERY = "attack OR airstrike OR shelling OR bombing OR strike OR killed OR massacre"
LIMIT = 100


def parse(text: str, observed_at: str) -> list[ConflictEvent]:
    out = []
    for item in json.loads(text).get("data", []):
        f = item.get("fields", {})
        created = (f.get("date") or {}).get("created", "")[:10]
        if not created or not f.get("title"):
            continue
        countries = f.get("country") or []
        primary = next((c for c in countries if c.get("primary")), countries[0] if countries else {})
        url = f.get("url") or f.get("url_alias") or ""
        out.append(ConflictEvent(
            id=event_id("reliefweb", str(item.get("id")), created), key=str(item.get("id")), source="reliefweb", date=created,
            observed_at=observed_at, type="report", code="report", place=primary.get("name", ""),
            country=country_iso(primary.get("name", "")) or country_iso(primary.get("iso3", "")), title=f["title"][:240],
            actor1=", ".join(s.get("name", "") for s in (f.get("source") or [])[:2]), urls=[url] if url else [],
            coding="report", confidence="medium", basis="official", coverage_note=COVERAGE["reliefweb"]))
    return out


def fetch(observed_at: str, *, get: Callable[..., str], today: date | None = None, days: int = 2) -> list[ConflictEvent]:
    app = env(KEY_ENV)
    if not app:
        raise NeedsKey(f"needs {KEY_ENV} (an approved appname; request one at {SIGNUP})")
    since = ((today or date.today()) - timedelta(days=days)).isoformat()
    params = {"appname": app, "limit": str(LIMIT), "sort[0]": "date.created:desc", "query[value]": QUERY, "query[fields][0]": "title",
              "filter[field]": "date.created", "filter[value][from]": f"{since}T00:00:00+00:00",
              "fields[include][0]": "title", "fields[include][1]": "date.created", "fields[include][2]": "country",
              "fields[include][3]": "url", "fields[include][4]": "source"}
    return parse(get(URL, params=params), observed_at)
