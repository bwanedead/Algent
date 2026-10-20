"""
ACLED (Armed Conflict Location & Event Data) — the best curated source. KEYED: built, inactive until the operator adds credentials.
Register (free for research use) at https://acleddata.com/register/ and set ``ALGENT_ACLED_EMAIL`` and ``ALGENT_ACLED_PASSWORD``.
Not tested against the live service (no credentials yet): written from ACLED's published API schema, parser covered by fixtures.

OAuth password grant -> bearer token -> /api/acled/read. We keep the violent event types (Battles, Explosions/Remote violence, Violence against
civilians); protests, riots and strategic developments are not attacks and are dropped.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import date, timedelta

from ..contracts import COVERAGE, ConflictEvent, event_id
from . import NeedsKey, country_iso, env

TOKEN_URL = "https://acleddata.com/oauth/token"
URL = "https://acleddata.com/api/acled/read"
KEY_ENV = ("ALGENT_ACLED_EMAIL", "ALGENT_ACLED_PASSWORD")
SIGNUP = "https://acleddata.com/register/"
PAGE_ROWS = 1000

_TYPE = {"Battles": "armed_clash", "Explosions/Remote violence": "bombing", "Violence against civilians": "assault"}
_SUB = {"Air/drone strike": "airstrike", "Shelling/artillery/missile attack": "bombing", "Suicide bomb": "bombing", "Remote explosive/landmine/IED": "bombing",
        "Mob violence": "assault", "Sexual violence": "assault"}


def parse(text: str, observed_at: str) -> list[ConflictEvent]:
    out = []
    for r in json.loads(text).get("data", []):
        etype = _SUB.get(r.get("sub_event_type", "")) or _TYPE.get(r.get("event_type", ""))
        if not etype or not r.get("event_date"):
            continue
        try:
            lat, lon = float(r["latitude"]), float(r["longitude"])
        except (KeyError, TypeError, ValueError):
            lat = lon = None
        fat = r.get("fatalities")
        place = ", ".join(x for x in (r.get("location"), r.get("admin1"), r.get("country")) if x)
        out.append(ConflictEvent(
            id=event_id("acled", str(r.get("event_id_cnty")), r["event_date"]), key=str(r.get("event_id_cnty")), source="acled",
            date=r["event_date"], observed_at=observed_at, type=etype, code=r.get("sub_event_type", ""), lat=lat, lon=lon, place=place,
            country=country_iso(r.get("country", "")), actor1=r.get("actor1", ""), actor2=r.get("actor2", ""),
            fatalities=int(fat) if str(fat or "").isdigit() else None, title=(r.get("notes") or place)[:240],
            urls=["https://acleddata.com/data-export-tool/"], coding="curated", confidence="high", basis="third_party",
            coverage_note=COVERAGE["acled"]))
    return out


def token(post: Callable[..., str]) -> str:
    email, pw = env(KEY_ENV[0]), env(KEY_ENV[1])
    if not (email and pw):
        raise NeedsKey(f"needs {KEY_ENV[0]} and {KEY_ENV[1]} (free registration at {SIGNUP})")
    return json.loads(post(TOKEN_URL, {"username": email, "password": pw, "grant_type": "password", "client_id": "acled"}))["access_token"]


def fetch(observed_at: str, *, get: Callable[..., str], post: Callable[..., str], today: date | None = None, days: int = 7) -> list[ConflictEvent]:
    bearer = token(post)
    today = today or date.today()
    params = {"_format": "json", "event_date": f"{(today - timedelta(days=days)).isoformat()}|{today.isoformat()}", "event_date_where": "BETWEEN",
              "limit": str(PAGE_ROWS)}
    return parse(get(URL, params=params, headers={"Authorization": f"Bearer {bearer}"}), observed_at)
