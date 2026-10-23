"""
Statements on the record: one document per statement (its speaker, what was said, why it matters), the speaker and the affiliation as entities,
and a typed stance edge from the speaker to whoever the statement is about. Spellings of one speaker are folded with the desk's own
``speakers.canonical_map``, so "Zelensky" and "Zelenskyy" are one person here as they are on the site.
"""

from __future__ import annotations

from collections.abc import Iterator

from algent_backend.actors import names as country_names
from algent_backend.agent_system.agents.statements import speakers
from algent_backend.agent_system.agents.statements import store as st

from .. import flags
from ..norm import clip, norm, slug
from ..sink import Sink
from .actors import country_id
from .base import Source, Unit, digest_of, mark


def _party(name: str, kind: str) -> tuple[str, str]:
    if (iso := country_names.iso2(name)):
        return country_id(iso), "country"
    return f"{'person' if kind == 'actor' else kind}:{slug(name)}", kind


def _emit(s, speaker: str, sink: Sink) -> None:                       # noqa: ANN001 - the statements Statement model
    doc = f"statement:{s.id}"
    title = f"{speaker} ({s.affiliation or s.role})"
    sink.document(doc, "statement", date=s.date, title=title, url=s.source_url, status=s.source_kind,
                  body=" ".join([s.paraphrase or s.quote, s.significance, *s.about, *s.topics]))
    pid, pkind = _party(speaker, "org" if norm(speaker) == norm(s.affiliation) else "actor")   # a person or an institution: the ledger does not say
    sink.declare(pid, pkind, speaker, aliases=[s.speaker], rank=flags.RANK_INFERRED)
    sink.mention(entity=pid, document=doc, role="speaker", date=s.date)
    if s.affiliation:
        aid, akind = _party(s.affiliation, "org")
        if akind != "country":
            sink.declare(aid, akind, s.affiliation, rank=flags.RANK_MENTIONED)
        sink.mention(entity=aid, document=doc, role="affiliation", date=s.date)
        if aid != pid:
            sink.relation("affiliated_with", src=pid, dst=aid, document=doc, date=s.date, note=s.role)
    for target in s.about:
        sink.mention(surface=target, document=doc, role="about", date=s.date)
        sink.relation(f"stance:{s.signal}", src=pid, dst_surface=target, document=doc, date=s.date, note=f"stance {s.stance:+d}: {clip(s.significance, 200)}")
    for topic in s.topics:
        tid = f"topic:{slug(topic)}"
        sink.declare(tid, "topic", topic, rank=flags.RANK_MENTIONED)
        sink.mention(entity=tid, document=doc, role="topic", date=s.date)


def _units() -> Iterator[Unit]:
    rows = st.load_statements()
    canon = speakers.canonical_map(rows)
    for s in rows:
        speaker = canon.get(s.speaker.strip(), s.speaker.strip())
        yield Unit(f"statement:{s.id}", digest_of([s.model_dump(), speaker]), lambda sink, s=s, speaker=speaker: _emit(s, speaker, sink),
                   date=s.date, path="statements_store/statements.jsonl")


def _watermark() -> str:
    return mark([st.store_dir() / "statements.jsonl"])


SOURCE = Source("statements", "statements", _units, _watermark)
