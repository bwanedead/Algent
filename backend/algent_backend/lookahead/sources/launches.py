"""
Notable space launches from Launch Library 2 (ll.thespacedevs.com, free tier: no key, ~15 requests an hour, one request here).
Notable means: a crewed flight, a planetary or deep-space mission, or a heavy or new vehicle (see ``NOTABLE_ROCKETS``); the ordinary
Starlink and small-satellite cadence is left out. Launch dates are "no earlier than", so a date is graded ``announced`` when the
launch is "Go" and the time is precise to the day, ``estimated`` otherwise.
"""

from __future__ import annotations

import json
from datetime import date

from algent_backend import polite_http
from algent_backend.actors import registry

from ..contracts import CalendarItem, make
from . import upcoming

API = "https://ll.thespacedevs.com/2.2.0/launch/upcoming/"
PAGE = "https://thespacedevs.com/llapi"
NOTABLE_ROCKETS = ("starship", "new glenn", "sls", "space launch system", "falcon heavy", "vulcan", "ariane 6", "long march 10", "long march 9", "neutron", "h3", "gslv mk iii", "lvm3")
NOTABLE_MISSIONS = ("human", "planetary", "crew", "lunar", "moon", "mars", "deep space", "space station resupply", "astrophysics")


def notable(r: dict) -> bool:
    rocket = (((r.get("rocket") or {}).get("configuration") or {}).get("name") or "").casefold()
    mission = r.get("mission") or {}
    kind = f"{mission.get('type') or ''} {mission.get('name') or ''} {r.get('name') or ''}".casefold()
    return any(k in rocket for k in NOTABLE_ROCKETS) or any(k in kind for k in NOTABLE_MISSIONS)


def parse(payload: dict) -> list[CalendarItem]:
    out = []
    for r in (payload or {}).get("results") or []:
        net = str(r.get("net") or "")[:10]
        if not net or not notable(r):
            continue
        status = ((r.get("status") or {}).get("abbrev") or "").casefold()
        day_precise = ((r.get("net_precision") or {}).get("abbrev") or "") in ("MIN", "HR", "DAY")
        name = str(r.get("name") or "Launch").split("|")[0].strip() + " | " + str((r.get("mission") or {}).get("name") or "").strip()
        code = registry.iso2_of_iso3(str(((r.get("pad") or {}).get("location") or {}).get("country_code") or "")) or ""
        out.append(make("launch", "launches", net, "Launch: " + name.strip(" |"), PAGE, countries=[code] if code else [],
                        grade="announced" if status == "go" and day_precise else "estimated", confidence="medium"))
    return out


def fetch(today: date) -> list[CalendarItem]:
    payload = json.loads(polite_http.get(API, params={"limit": 100, "format": "json", "mode": "detailed"}, headers={"Accept": "application/json"}))
    return upcoming(parse(payload), today)
