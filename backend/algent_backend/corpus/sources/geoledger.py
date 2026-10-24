"""
The geoledger: places that exist (power plants, ports, bases, vessels...) and what somebody said about their state. Each live asset is a
``place`` entity (merged duplicates fold their names into it); each status event is a document, an event at that place, and a claim whose
sources are the URLs the claimant gave. A claim stays a claim: the claimant and its confidence travel with it.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterator

from algent_backend.geoledger.store import Ledger, root

from .. import flags
from ..norm import clip
from ..sink import Sink
from .actors import country_id
from .base import Source, Unit, digest_of, mark


def asset_id(raw: str) -> str:
    return f"asset:{raw}"


def _emit(led: Ledger, a, dups: list, events: list, sink: Sink) -> None:   # noqa: ANN001 - Asset / StatusEvent models
    eid = asset_id(a.id)
    attrs = {"type": a.type, "precision": a.precision, "source": a.source, "licence": a.licence, **a.attrs}
    sink.declare(eid, "place", a.name, aliases=a.aliases, iso2=a.country or None, lat=a.lat, lon=a.lon, attrs=attrs, rank=flags.RANK_DECLARED)
    for d in dups:                                                         # a merged duplicate lends its names to the asset it became
        sink.declare(eid, "place", d.name, aliases=d.aliases, rank=flags.RANK_MENTIONED)
    if a.country:
        sink.relation("located_in", src=eid, dst=country_id(a.country), date=a.recorded_at)
    for e in events:
        doc = f"geo:{e.id}"
        title = f"{a.name} ({a.type}, {a.country})"
        text = f"{a.name} {a.type} {a.country}: {e.status.replace('_', ' ')} per {e.claimant}. {e.note}"
        sink.document(doc, "geo", date=e.occurred_on, title=title, url=e.sources[0] if e.sources else "", status=e.status, body=text)
        sink.mention(entity=eid, document=doc, role="subject", date=e.occurred_on)
        cid = f"claim:geo:{e.id}"
        sink.claim(cid, f"{e.claimant}: {a.name} {e.status.replace('_', ' ')}. {clip(e.note, 300)}".strip(), document_id=doc, status=e.status,
                   grounding=e.provenance, confidence=e.confidence, created_at=e.observed_at or e.occurred_on)
        for url in e.sources:
            sink.cite(cid, url)
        sink.event(f"event:geo:{e.id}", f"status_{e.status}", date=e.occurred_on, title=f"{a.name}: {e.status.replace('_', ' ')}", detail=text,
                   place=a.name, place_id=eid, lat=a.lat, lon=a.lon, document=doc, url=e.sources[0] if e.sources else "",
                   actors=[e.claimant], role="claimant")


def _units() -> Iterator[Unit]:
    led = Ledger()
    dups: dict[str, list] = defaultdict(list)
    for dup_id in led.merged:
        if dup_id in led.assets:
            dups[led.canonical(dup_id)].append(led.assets[dup_id])
    for a in sorted(led.live(), key=lambda a: a.id):
        events = sorted(led.by_asset.get(a.id, []), key=lambda e: e.id)
        fp = digest_of([a.model_dump(), [d.model_dump() for d in dups[a.id]], [e.model_dump() for e in events]])
        latest = max((e.occurred_on for e in events), default="")
        yield Unit(f"geo:{a.id}", fp, lambda sink, a=a, events=events: _emit(led, a, dups[a.id], events, sink), date=latest, path="geoledger_store/assets.jsonl")


def _watermark() -> str:
    base = root()
    return mark([base / "assets.jsonl", base / "events.jsonl", base / "merges.jsonl"]) if base.is_dir() else "none"


SOURCE = Source("geoledger", "geoledger", _units, _watermark)
