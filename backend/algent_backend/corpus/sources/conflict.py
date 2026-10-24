"""
Attack / conflict events (GDELT, ReliefWeb, ACLED, UCDP), one record across sources. Each stored event becomes an ``events`` row (dated, placed, with its
country) and a document that carries its PROVENANCE in words: which source, whether software or researchers coded it, how many reports stand behind it, what the
source cannot see. A machine-coded event a single source barely supports (``confidence`` low) stays out of the index: the index is for evidence, and the log
page keeps the full stream. A unit is one event date (a shard), so the index never holds more than the rolling window the store keeps.
"""

from __future__ import annotations

from collections.abc import Iterator

from algent_backend.conflict import store as cx
from algent_backend.conflict.contracts import SOURCES, TYPE_LABEL, ConflictEvent

from ..sink import Sink
from .actors import country_id
from .geoledger import asset_id
from .base import Source, Unit, file_digest, mark

_CODING = {"machine": "machine-coded from news text by software", "curated": "coded by researchers", "report": "a published humanitarian report"}


def indexed(e: ConflictEvent) -> bool:
    return not (e.coding == "machine" and e.confidence == "low")


def _emit(e: ConflictEvent, sink: Sink) -> None:
    doc = f"conflict:{e.id}"
    label = SOURCES[e.source]["label"]
    where = e.place or e.country or "location unknown"
    title = f"{TYPE_LABEL[e.type]}, {where} ({e.source})"
    killed = f"{e.fatalities} killed per the source. " if e.fatalities else "Casualties not stated. "
    provenance = f"Source: {label}. {_CODING[e.coding].capitalize()}; confidence {e.confidence}; {e.articles} report(s). Basis: {e.basis}. {killed}"
    sink.document(doc, "conflict_event", date=e.date, title=title, url=e.urls[0] if e.urls else SOURCES[e.source]["page"], status=e.coding,
                  body=provenance + e.coverage_note + " " + " ".join([e.title, e.place, e.actor1, e.actor2, *(a.name for a in e.assets)]))
    iso = e.country.upper() if len(e.country) == 2 else ""
    if iso:
        sink.mention(entity=country_id(iso), document=doc, role="location of the event", date=e.date)
    for who in (e.actor1, e.actor2):
        if who:
            sink.mention(surface=who, document=doc, role="party named in the event", date=e.date)
    sink.event(f"event:conflict:{e.id}", f"conflict_{e.type}", date=e.date, title=title, detail=provenance + e.coverage_note, status=e.coding,
               place=e.place, place_id=country_id(iso) if iso and not e.place else None, lat=e.lat, lon=e.lon, document=doc,
               url=e.urls[0] if e.urls else "", actors=[x for x in (e.actor1, e.actor2) if x])
    for a in e.assets:                                                     # proximity to a tracked place, never a claim that it was hit
        sink.mention(entity=asset_id(a.id), document=doc, role=f"within {a.km} km of the event (proximity only)", date=e.date)


def _units() -> Iterator[Unit]:
    for day in cx.shard_days():
        path = cx.shard_path(day)

        def emit(sink: Sink, day: str = day) -> None:
            for e in cx.shard(day):
                if indexed(e):
                    _emit(e, sink)

        yield Unit(f"conflict:{day}", file_digest(path), emit, date=day, path=f"conflict_store/events/{day}.jsonl")


def _watermark() -> str:
    return mark(cx.root().joinpath("events").glob("*.jsonl")) if cx.root().joinpath("events").is_dir() else "none"


SOURCE = Source("conflict", "conflict", _units, _watermark)
