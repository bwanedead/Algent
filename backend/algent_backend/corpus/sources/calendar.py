"""Look-ahead calendar: upcoming elections, central-bank decisions, summits, deadlines. The latest revision of each item, as a document and an event."""

from __future__ import annotations

from collections.abc import Iterator

from algent_backend.lookahead import store as cal

from ..sink import Sink
from .actors import country_id
from .base import Source, Unit, digest_of, mark


def _emit(i, sink: Sink) -> None:                                           # noqa: ANN001 - CalendarItem
    doc = f"calendar:{i.id}"
    status = "active" if i.active else "withdrawn"
    sink.document(doc, "calendar", date=i.date, title=i.title, url=i.source_url, status=status,
                  body=f"{i.title} ({i.kind}, {i.confidence} confidence) {' '.join(i.countries)}")
    for iso in i.countries:
        sink.mention(entity=country_id(iso), document=doc, role="concerned", date=i.date)
    for thr in i.theaters:
        sink.mention(entity=f"situation:{thr}", document=doc, role="theater", date=i.date)
    sink.event(f"event:calendar:{i.id}", f"calendar_{i.kind}", date=i.date, end_date=i.end_date, title=i.title, status=status,
               detail=f"{i.kind}; source {i.source}; {i.confidence} confidence", document=doc, url=i.source_url,
               actor_ids=[country_id(c) for c in i.countries], role="concerned")


def _units() -> Iterator[Unit]:
    for i in cal.current().values():
        yield Unit(f"calendar:{i.id}", digest_of(i.model_dump()), lambda sink, i=i: _emit(i, sink), date=i.date, path="calendar_store/items.jsonl")


def _watermark() -> str:
    return mark([cal.root() / "items.jsonl"])


SOURCE = Source("calendar", "calendar", _units, _watermark)
