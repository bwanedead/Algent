"""
UCDP Georeferenced Event Dataset, candidate events (Uppsala Conflict Data Program) — KEYED: the API wants an access token since 2025.
Request one by emailing UCDP as described at https://ucdp.uu.se/apidocs/ and set ``ALGENT_UCDP_TOKEN``. Not tested against the live service
(no token yet): written from the published API schema, parser covered by fixtures.

Candidate versions are named ``YY.0.M`` (month M of 20YY, published monthly), so a run asks for the latest one that answers.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import date, timedelta

from algent_backend.polite_http import SourceError

from ..contracts import COVERAGE, ConflictEvent, event_id
from . import NeedsKey, country_iso, env

URL = "https://ucdpapi.pcr.uu.se/api/gedevents/{version}"
KEY_ENV = "ALGENT_UCDP_TOKEN"
SIGNUP = "https://ucdp.uu.se/apidocs/"
PAGE = 1000
_VIOLENCE = {1: "state-based", 2: "non-state", 3: "one-sided"}


def versions(today: date) -> list[str]:
    """Candidate version names to try, newest first (this month, then the two before)."""
    out, d = [], today.replace(day=1)
    for _ in range(3):
        out.append(f"{d.year % 100}.0.{d.month}")
        d = (d - timedelta(days=1)).replace(day=1)
    return out


def parse(text: str, observed_at: str) -> list[ConflictEvent]:
    out = []
    for r in json.loads(text).get("Result", []):
        day = str(r.get("date_start", ""))[:10]
        if not day:
            continue
        try:
            lat, lon = float(r["latitude"]), float(r["longitude"])
        except (KeyError, TypeError, ValueError):
            lat = lon = None
        best = r.get("best")
        kind = _VIOLENCE.get(r.get("type_of_violence"), "")
        etype = "assault" if r.get("type_of_violence") == 3 else "armed_clash"
        place = ", ".join(x for x in (r.get("where_coordinates"), r.get("adm_1"), r.get("country")) if x)
        out.append(ConflictEvent(
            id=event_id("ucdp", str(r.get("id")), day), key=str(r.get("id")), source="ucdp", date=day, observed_at=observed_at, type=etype,
            code=kind, lat=lat, lon=lon, place=place, country=country_iso(r.get("country", "")), actor1=r.get("side_a", ""),
            actor2=r.get("side_b", ""), fatalities=int(best) if isinstance(best, (int, float)) else None,
            title=f"{kind} violence, {place}".strip(", ")[:240], urls=["https://ucdp.uu.se/"], coding="curated", confidence="high",
            basis="third_party", coverage_note=COVERAGE["ucdp"]))
    return out


def fetch(observed_at: str, *, get: Callable[..., str], today: date | None = None, days: int = 14) -> list[ConflictEvent]:
    token = env(KEY_ENV)
    if not token:
        raise NeedsKey(f"needs {KEY_ENV} (request a token at {SIGNUP})")
    today = today or date.today()
    last: Exception | None = None
    for v in versions(today):
        try:
            params = {"pagesize": str(PAGE), "StartDate": (today - timedelta(days=days)).isoformat(), "EndDate": today.isoformat()}
            return parse(get(URL.format(version=v), params=params, headers={"x-ucdp-access-token": token}), observed_at)
        except SourceError as exc:
            last = exc
    raise SourceError(f"no UCDP candidate version answered: {last}")
