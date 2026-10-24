"""
GPS-interference zones (our own ADS-B derivation, GPSJam's top band as the cross-check). Per day: the number of zones and how many are high as series points
(``our_derived``: a minimum, because only aircraft we hear in cells we sample are seen), and each flagged zone (``new`` or ``intensifying`` against its cell's own
history) as an event with its coordinates, so "where did interference start this week" is one query.
"""

from __future__ import annotations

from collections.abc import Iterator

from algent_backend.gnss import store as gx
from algent_backend.gnss.contracts import COVERAGE

from ..sink import Sink
from .actors import country_id
from .base import Source, Unit, digest_of, mark

_NOTE = "Ohmega's ADS-B estimate: aircraft we hear in cells we sample only, a minimum"


def _emit(day: str, doc: dict, sink: Sink) -> None:
    ours = doc.get("zones", [])
    sink.observation("gnss.zones", day, len(ours), unit="zones", basis="our_derived", label="GPS interference zones (ours)", note=_NOTE)
    sink.observation("gnss.zones.high", day, sum(1 for z in ours if z["severity"] == "high"), unit="zones", basis="our_derived", label="high-severity zones (ours)", note=_NOTE)
    for z in ours:
        if not z.get("flag"):
            continue
        iso = z.get("country", "")
        agrees = {"agrees": " GPSJam shows it too.", "not_in_gpsjam": " GPSJam's file does not show it."}.get(z.get("cross_check", ""), "")
        where = iso or "sea or border area"
        sink.event(f"event:gnss:{z['id']}", f"gnss_{z['flag']}", date=day, title=f"GPS interference {z['flag']}: {where} ({z['severity']})",
                   detail=f"{z['degraded_share']:.0%} of {z['aircraft']} aircraft observations degraded around {z['lat']:.1f}, {z['lon']:.1f}.{agrees} {COVERAGE['ohmega_adsb']}",
                   status=z["flag"], place=where, place_id=country_id(iso) if iso else None, lat=z["lat"], lon=z["lon"])


def _units() -> Iterator[Unit]:
    for day in gx.zone_days():
        doc = gx.load_zones(day)
        if doc:
            yield Unit(f"gnss:{day}", digest_of(doc.get("zones", [])), lambda sink, day=day, doc=doc: _emit(day, doc, sink), date=day, path=f"gnss_store/zones/{day}.json")


def _watermark() -> str:
    d = gx.root() / "zones"
    return mark(d.glob("*.json")) if d.is_dir() else "none"


SOURCE = Source("gnss", "gnss", _units, _watermark)
