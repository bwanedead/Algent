"""
The watch list: which places get fresh imagery. Nothing is hand-listed: the places come from what the desk already tracks.

* **Struck or damaged places**: ledger assets (``geoledger``) with a damage statement inside ``STRIKE_WINDOW_DAYS``, weighted by how firmly it is
  stated (a claim < a report < a confirmation) and faded with age. The earliest such statement's date is the site's ``event_on``: its baseline is the
  clearest scene BEFORE that day.
* **In today's developments**: assets the daily's own sections named in the last ``DEVELOPMENT_DAYS`` (ledger events carry ``via: daily:<date>:<theater>``),
  with the theater the statement came from.
* **Chokepoints**: the maritime watch zones (``maritime/sites``), at the floor of the list.

Only assets placed ``exact`` or ``approximate`` are watched: a city-level centroid is not a place a picture can be taken of.

``select_due`` rotates: a pass takes the sites that are most overdue weighted by priority, so a high-priority site is revisited every
``REVISIT_HOURS`` and the tail of the list still comes round. Pure functions over the ledger and a clock: no network.
"""

from __future__ import annotations

import math
import re
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from typing import Any

from algent_backend.geoledger.contracts import Asset, StatusEvent, slug
from algent_backend.geoledger.store import Ledger

from . import flags

_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


@dataclass
class Site:
    id: str
    name: str
    kind: str                       # asset | zone
    lat: float
    lon: float
    half_km: float
    priority: float
    why: list[str] = field(default_factory=list)
    asset_type: str = ""
    country: str = ""               # ISO alpha-2 for assets; "" for zones
    countries: list[str] = field(default_factory=list)   # names, for zones
    asset_id: str = ""
    theater: str = ""
    event_on: str = ""              # earliest damage statement inside the window ("" when none)

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


def site_id(raw: str) -> str:
    return _SAFE.sub("_", raw)[:80]


def bbox_of(lat: float, lon: float, half_km: float) -> tuple[float, float, float, float]:
    """(west, south, east, north) of a square of ``half_km`` around a point."""
    dlat = half_km / 111.32
    dlon = half_km / (111.32 * max(math.cos(math.radians(lat)), 0.05))
    return (round(lon - dlon, 5), round(lat - dlat, 5), round(lon + dlon, 5), round(lat + dlat, 5))


def _day(raw: str) -> date | None:
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def _theater_of(ev: StatusEvent) -> str:
    parts = ev.via.split(":", 2)
    return parts[2] if len(parts) == 3 and parts[0] == "daily" else ""


def _from_asset(a: Asset, events: list[StatusEvent], today: date) -> Site | None:
    if a.lat is None or a.lon is None or a.precision not in ("exact", "approximate"):
        return None
    why: list[str] = []
    prio = 0.0
    strikes: list[tuple[date, StatusEvent]] = []
    for e in events:
        d = _day(e.occurred_on)
        if d is None or e.status not in flags.STATUS_WEIGHT:
            continue
        age = (today - d).days
        if 0 <= age <= flags.STRIKE_WINDOW_DAYS:
            prio += flags.STATUS_WEIGHT[e.status] / (1.0 + age / 7.0)
            strikes.append((d, e))
    if strikes:
        first = min(strikes, key=lambda x: x[0])
        latest = max(strikes, key=lambda x: x[0])
        why.append(f"{latest[1].status.replace('_', ' ')} on {latest[1].occurred_on} ({latest[1].claimant})")
    dev = [e for e in events if e.via.startswith("daily:") and (d := _day(e.occurred_on)) and 0 <= (today - d).days <= flags.DEVELOPMENT_DAYS]
    if dev:
        prio += flags.DEVELOPMENT_BONUS
        why.append("in the daily's developments")
    if prio <= 0:
        return None
    pick = max(dev or [e for _, e in strikes], key=lambda e: e.occurred_on)
    return Site(id=site_id(a.id), name=a.name, kind="asset", lat=a.lat, lon=a.lon, half_km=flags.SITE_HALF_KM, priority=round(prio, 3), why=why,
                asset_type=a.type, country=a.country, asset_id=a.id, theater=_theater_of(pick),
                event_on=first[0].isoformat() if strikes else "")


def _zones() -> list[Site]:
    from algent_backend.maritime.sites import ZONES

    out = []
    for z in ZONES:
        if z.kind != "chokepoint":
            continue
        s, w, n, e = z.box
        lat, lon = (s + n) / 2, (w + e) / 2
        half = min(flags.ZONE_HALF_KM_MAX, 0.5 * min((n - s) * 111.32, (e - w) * 111.32 * math.cos(math.radians(lat))))
        out.append(Site(id=site_id("zone-" + slug(z.slug)), name=z.label, kind="zone", lat=round(lat, 4), lon=round(lon, 4), half_km=round(half, 1),
                        priority=flags.ZONE_PRIORITY, why=["chokepoint under maritime watch"], countries=list(z.countries)))
    return out


def build(ledger: Ledger, now: datetime | None = None, *, zones: bool = True) -> list[Site]:
    """The ranked watch list (highest priority first), at most ``POOL_SIZE`` long."""
    today = (now or datetime.now(timezone.utc)).date()
    sites = [s for a in ledger.live() if (s := _from_asset(a, ledger.by_asset.get(a.id, []), today))]
    if zones:
        sites += _zones()
    sites.sort(key=lambda s: (-s.priority, s.id))
    return sites[:flags.POOL_SIZE]


def select_due(sites: list[Site], last_checked: dict[str, float], now_ts: float, limit: int | None = None) -> list[Site]:
    """The sites this pass should take: eligible when not looked at within ``REVISIT_HOURS``, ordered by priority x (1 + days overdue)."""
    cap = flags.MAX_SITES_PER_PASS if limit is None else limit
    due: list[tuple[float, Site]] = []
    for s in sites:
        seen = last_checked.get(s.id)
        age_h = (now_ts - seen) / 3600.0 if seen is not None else 1e4
        if age_h >= flags.REVISIT_HOURS:
            due.append((s.priority * (1.0 + age_h / 24.0), s))
    due.sort(key=lambda x: (-x[0], x[1].id))
    return [s for _, s in due[:cap]]
