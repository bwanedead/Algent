"""
Sanctions designations and delistings (the diff history of the OFAC / UK / EU lists). Each event is a document (searchable), an event (dated, with
the country it concerns) and edges from the listed party to the list that named it, its flag state and its owner.
"""

from __future__ import annotations

from collections.abc import Iterator

from algent_backend.sanctions import store as sx

from .. import flags
from ..norm import slug
from ..sink import Sink
from .actors import country_id
from .base import Source, Unit, digest_of, mark

LISTS = {"ofac": "US Treasury OFAC sanctions list", "uk": "UK sanctions list", "eu": "EU consolidated sanctions list"}
_KIND = {"person": "person", "entity": "org", "vessel": "vessel", "aircraft": "aircraft"}


def listed_id(e) -> str:                                                    # noqa: ANN001 - SanctionsEvent
    kind = _KIND.get(e.type, "org")
    return f"vessel:imo:{e.imo}" if kind == "vessel" and e.imo else f"{kind}:{slug(e.name)}"


def _emit(e, sink: Sink) -> None:                                          # noqa: ANN001
    kind = _KIND.get(e.type, "org")
    who = listed_id(e)
    title = f"{e.source} {e.action}: {e.name}"
    doc = f"sanction:{e.id}"
    sink.document(doc, "sanction", date=e.observed_on, title=title, url=e.source_url, status="baseline" if e.baseline else e.action,
                  body=" ".join([e.name, e.type, e.owner, e.flag, *e.programmes, *e.countries]))
    attrs = {"imo": e.imo, "programmes": e.programmes} if e.imo or e.programmes else None
    sink.declare(who, kind, e.name, rank=flags.RANK_DECLARED, attrs=attrs)
    list_id = f"org:{e.source}-sanctions-list"
    sink.declare(list_id, "org", LISTS.get(e.source, e.source), aliases=[e.source.upper()], rank=flags.RANK_DECLARED)
    sink.mention(entity=who, document=doc, role="listed party", date=e.observed_on)
    sink.relation(f"sanctions_{e.action}", src=list_id, dst=who, document=doc, date=e.date, note=", ".join(e.programmes))
    if e.flag and (iso := e.flag.upper()):
        sink.relation("flagged_in", src=who, dst=country_id(iso), document=doc, date=e.date)
    for iso in e.countries:
        sink.mention(entity=country_id(iso), document=doc, role="listed party's country", date=e.observed_on)
    if e.owner:
        sink.relation("owned_by", src=who, dst_surface=e.owner, document=doc, date=e.date)
    sink.event(f"event:sanction:{e.id}", f"sanction_{e.action}", date=e.date, title=title, detail=" ".join([e.name, *e.programmes]),
               status="baseline" if e.baseline else "", document=doc, url=e.source_url, actors=[e.owner] if e.owner else [],
               actor_ids=[list_id, who])


def _units() -> Iterator[Unit]:
    for e in sx.events():
        yield Unit(f"sanction:{e.id}", digest_of(e.model_dump()), lambda sink, e=e: _emit(e, sink), date=e.observed_on, path="sanctions_store/events.jsonl")


def _watermark() -> str:
    return mark([sx.root() / "events.jsonl"])


SOURCE = Source("sanctions", "sanctions", _units, _watermark)
