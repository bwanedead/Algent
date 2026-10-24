"""
Maritime behaviour, from the daily summaries (the only long record of ship behaviour: the raw positions and event log are bounded and rolled up
into these). Per day: one series point per zone for ships seen / underway / median speed (our own AIS count, a floor), per-kind counts of
behaviour events opened, and the notable events with the vessel involved.
"""

from __future__ import annotations

from collections.abc import Iterator

from algent_backend.maritime import rollup

from .. import flags
from ..norm import day, slug
from ..sink import Sink
from .base import Source, Unit, digest_of, mark

_NOTE = "Ohmega AIS count: ships heard by our receivers only, a minimum"


def zone_id(zid: str) -> str:
    return f"place:zone:{zid}"


def vessel_id(row: dict) -> str:
    if row.get("imo"):
        return f"vessel:imo:{row['imo']}"
    return f"vessel:mmsi:{row['mmsi']}" if row.get("mmsi") else f"vessel:{slug(row.get('name') or row.get('id') or '')}"


def _emit(d: str, doc: dict, sink: Sink) -> None:
    for zid, z in sorted((doc.get("zones") or {}).items()):
        ent = zone_id(zid)
        sink.declare(ent, "place", z.get("label") or zid, rank=flags.RANK_DECLARED, attrs={"kind": "maritime zone"})
        for metric, key, unit, basis in (("maritime.ships", "ships", "ships", "our_count"), ("maritime.underway", "underway", "ships", "our_count"),
                                         ("maritime.median_kn", "median_kn", "knots", "our_derived"), ("maritime.samples", "samples", "samples", "our_count")):
            if z.get(key) is not None:
                sink.observation(metric, d, z[key], entity=ent, unit=unit, basis=basis, label=f"{z.get('label') or zid}: {key}", note=_NOTE)
    ev = doc.get("events") or {}
    for kind, n in sorted((ev.get("by_kind") or {}).items()):
        sink.observation(f"maritime.opened.{kind}", d, n, unit="events", basis="our_count", label=f"behaviour events opened: {kind}", note=_NOTE)
    for area, n in sorted((ev.get("gaps_by_area") or {}).items()):
        sink.observation("maritime.ais_gaps", d, n, unit="gaps", basis="our_count", label=f"AIS gaps in {area}", note=_NOTE)
    for row in doc.get("notable") or []:
        vid = vessel_id(row)
        if row.get("name") or row.get("imo") or row.get("mmsi"):
            sink.declare(vid, "vessel", str(row.get("name") or row.get("imo") or row.get("mmsi")), rank=flags.RANK_DECLARED,
                         attrs={k: row[k] for k in ("mmsi", "imo", "ship_class") if row.get(k)})
        when = day(row.get("at")) or d
        sink.event(f"event:maritime:{row.get('id')}:{row.get('state')}", f"maritime_{row.get('kind')}", date=when,
                   title=f"{row.get('name') or row.get('mmsi')}: {row.get('kind')} ({row.get('state')})", detail=str(row.get("summary") or ""),
                   status=str(row.get("state") or ""), place=str(row.get("area") or ""), actor_ids=[vid], role="vessel")


def _units() -> Iterator[Unit]:
    folder = rollup.daily_dir()
    for path in sorted(folder.glob("*.json.gz")) if folder.is_dir() else ():
        d = path.name.removesuffix(".json.gz")
        doc = rollup.read_day(d)
        if doc:
            yield Unit(f"maritime:{d}", digest_of(doc), lambda sink, d=d, doc=doc: _emit(d, doc, sink), date=d, path=f"maritime_store/daily/{path.name}")


def _watermark() -> str:
    folder = rollup.daily_dir()
    return mark(folder.glob("*.json.gz")) if folder.is_dir() else "none"


SOURCE = Source("maritime", "maritime", _units, _watermark)
