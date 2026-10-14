"""
Seed the ledger with named infrastructure from OpenStreetMap (ODbL, © OpenStreetMap contributors) through Overpass.

On demand and by theater box, never the whole planet: ``seed(ledger, bbox, kinds)`` sends ONE query per (box, kind) to an
Overpass server, politely (an identifying User-Agent, a pause between queries, a single attempt that waits out a busy
server once), and caches every answer under ``<store>/cache/overpass`` for ``CACHE_DAYS`` so a rerun asks nobody.

Only named features are taken, and only what matters for a status ledger: power plants, high-voltage substations
(200 kV and up), refineries, fuel depots, ports, military airfields and named bases, dams. An OSM power plant that is
already a WRI plant (same name, within a few kilometres) enriches that asset (alias and OSM id) instead of duplicating it.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from .contracts import Asset
from .match import name_score
from .store import Ledger, root

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
USER_AGENT = "OhmegaGeoledger/1.0 (+https://ohmega.monster; open-data status ledger)"
SOURCE = "OpenStreetMap contributors via Overpass"
LICENCE = "ODbL 1.0"
CACHE_DAYS = 7
PAUSE_S = 6.0                 # between live queries (Overpass fair use: one at a time, spaced)
DEDUP_KM = 4.0

#: Named theater boxes, [west, south, east, north].
PRESETS: dict[str, list[float]] = {
    "ukraine": [22.0, 44.0, 40.5, 52.5],
    "russia-west": [27.0, 43.0, 60.0, 62.0],
    "middle-east": [34.0, 12.0, 63.0, 42.0],
}

#: type -> Overpass selectors (each is OR-ed; every one also requires a name).
KINDS: dict[str, list[str]] = {
    "power_plant": ['["power"="plant"]'],
    "substation": ['["power"="substation"]["voltage"~"[2-9][0-9]{5}|[0-9]{7}"]'],
    "refinery": ['["industrial"="refinery"]', '["man_made"="works"]["product"~"oil|petroleum|fuel"]'],
    "fuel_depot": ['["industrial"="oil"]', '["industrial"="depot"]["product"~"oil|fuel|petrol|diesel"]'],
    "port": ['["landuse"="port"]', '["harbour"="yes"]'],
    "airbase": ['["military"="airfield"]'],
    "military_base": ['["military"="base"]'],
    "dam": ['["waterway"="dam"]'],
}
Fetch = Callable[[str], dict]


def query_for(kind: str, bbox: list[float]) -> str:
    w, s, e, n = bbox
    body = "".join(f'nwr{sel}["name"]({s},{w},{n},{e});' for sel in KINDS[kind])
    return f"[out:json][timeout:120];({body});out center tags 5000;"


def _cache_file(query: str) -> Path:
    return root() / "cache" / "overpass" / (hashlib.sha1(query.encode("utf-8")).hexdigest()[:20] + ".json")


def _cached(query: str, now: datetime) -> dict | None:
    path = _cache_file(query)
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        if now - datetime.fromisoformat(doc["fetched_at"]) < timedelta(days=CACHE_DAYS):
            return doc["answer"]
    except (OSError, ValueError, KeyError):
        pass
    return None


def fetch_overpass(query: str) -> dict:
    import httpx

    for attempt in (0, 1):
        resp = httpx.post(OVERPASS_URL, data={"data": query}, headers={"User-Agent": USER_AGENT}, timeout=180.0)
        if resp.status_code in (429, 504) and attempt == 0:
            time.sleep(30.0)                       # a busy server: wait once, then give up rather than hammer it
            continue
        resp.raise_for_status()
        return resp.json()
    raise RuntimeError("Overpass stayed busy")


def _tag(tags: dict, *keys: str) -> str:
    return next((str(tags[k]).strip() for k in keys if tags.get(k)), "")


def _mw(raw: str) -> float | None:
    """'1.2 GW' / '600 MW' / '600000 kW' -> MW; a bare number is watts (the OSM convention)."""
    raw = raw.strip().lower()
    for unit, k in (("gw", 1000.0), ("mw", 1.0), ("kw", 0.001), ("w", 1e-6)):
        if raw.endswith(unit):
            try:
                return float(raw[: -len(unit)].strip().replace(",", ".")) * k
            except ValueError:
                return None
    try:
        return float(raw.replace(",", ".")) * 1e-6
    except ValueError:
        return None


def element_to_asset(el: dict, type_: str, iso_at: Callable[[float, float], str]) -> Asset | None:
    tags = el.get("tags") or {}
    name = _tag(tags, "name:en", "name")
    c = el.get("center") or el
    lat, lon = c.get("lat"), c.get("lon")
    if not name or lat is None or lon is None:
        return None
    attrs: dict[str, Any] = {}
    if type_ == "power_plant":
        if (mw := _mw(_tag(tags, "plant:output:electricity", "generator:output:electricity"))) is not None:
            attrs["capacity_mw"] = round(mw, 1)
        if fuel := _tag(tags, "plant:source", "generator:source"):
            attrs["fuel"] = fuel
    if type_ == "substation" and (v := _tag(tags, "voltage")):
        attrs["voltage"] = v
    if op := _tag(tags, "operator", "owner"):
        attrs["owner"] = op[:80]
    aliases = [a for a in {_tag(tags, "name"), _tag(tags, "name:uk"), _tag(tags, "name:ru"), _tag(tags, "old_name")} if a and a != name]
    kind = {"node": "n", "way": "w", "relation": "r"}.get(el.get("type", ""), "x")
    return Asset(id=f"osm-{kind}{el.get('id')}", name=name, aliases=sorted(aliases)[:4], type=type_,  # type: ignore[arg-type]
                 country=iso_at(lat, lon), lat=round(lat, 5), lon=round(lon, 5), precision="approximate", attrs=attrs,
                 source=SOURCE, licence=LICENCE, source_url=f"https://www.openstreetmap.org/{el.get('type', 'node')}/{el.get('id')}",
                 provenance="aggregated")


def default_iso_at() -> Callable[[float, float], str]:
    """lat/lon -> ISO alpha-2 through the desk's Natural Earth basemap; "" where unknown (sea, no basemap)."""
    def at(lat: float, lon: float) -> str:
        try:
            from algent_backend.actors import registry
            from algent_backend.live.places import country_at

            name = country_at(lat, lon)
            if not name:
                return ""
            want = name.casefold()
            return next((c.iso2 for c in registry.load().values() if c.name.casefold() == want or want in {a.casefold() for a in c.aliases}), "")
        except Exception:  # noqa: BLE001 - a missing basemap means no country, never a failed seed
            return ""
    return at


def _merge(ledger: Ledger, a: Asset) -> Asset | None:
    """The asset to write for an OSM element: the WRI plant it duplicates (enriched), or itself when new; None to skip."""
    if a.type != "power_plant" or a.lat is None or a.lon is None:
        return a
    for other in ledger.near(a.lat, a.lon, DEDUP_KM, "power_plant"):
        if other.id.startswith("wri-") and max((name_score(a.name, m) for m in (other.name, *other.aliases)), default=0) >= 0.8:
            names = [*other.aliases, *( [a.name] if a.name != other.name else []), *a.aliases]
            attrs = {**other.attrs, "osm": a.id.removeprefix("osm-")}
            return other.model_copy(update={"aliases": sorted(dict.fromkeys(names))[:6], "attrs": attrs})
    return a


def seed(ledger: Ledger, bbox: list[float], kinds: list[str] | None = None, *, fetch: Fetch | None = None,
         iso_at: Callable[[float, float], str] | None = None, now: datetime | None = None,
         pause: float = PAUSE_S) -> dict[str, Any]:
    """Seed one box: for each kind, the cached or freshly fetched answer becomes assets. Returns counts per kind;
    a kind whose query fails is reported and skipped (the rest still run)."""
    fetch, iso_at, now = fetch or fetch_overpass, iso_at or default_iso_at(), now or datetime.now(UTC)
    report: dict[str, Any] = {"bbox": bbox, "kinds": {}, "errors": []}
    for kind in kinds or list(KINDS):
        q = query_for(kind, bbox)
        answer, live = _cached(q, now), False
        if answer is None:
            try:
                answer, live = fetch(q), True
            except Exception as exc:  # noqa: BLE001 - one failed query must not lose the others
                report["errors"].append(f"{kind}: {type(exc).__name__}: {str(exc)[:120]}")
                continue
            path = _cache_file(q)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"fetched_at": now.isoformat(), "answer": answer}), encoding="utf-8")
        built = [m for el in answer.get("elements", []) if (a := element_to_asset(el, kind, iso_at)) and (m := _merge(ledger, a))]
        report["kinds"][kind] = {"features": len(built), "added": ledger.add_assets(built), "cached": not live}
        if live:
            time.sleep(pause)
    return report
