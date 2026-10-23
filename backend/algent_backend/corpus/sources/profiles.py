"""
Research profiles (the claim corpus): each profile is a document; its claims keep their grounding and their sources; its entities are
declared (countries resolve to the country table instead) and linked to the claims they appear in, by the research's own threads and by
their names occurring in the claim text.
"""

from __future__ import annotations

import re
from collections.abc import Iterator

from algent_backend.actors import names as country_names
from algent_backend.agent_system.agents.research.store import JsonProfileStore

from .. import flags
from ..norm import clip, day, norm, slug
from ..sink import Sink
from .actors import country_id
from .base import Source, Unit, file_digest, mark

_KIND = {"person": "person", "org": "org", "place": "place"}
_THREAD_ENTITIES_MAX = 8
_NAME_MIN = 4
_DATED_LINE = re.compile(r"^\s*(\d{4}-\d{2}-\d{2})\b[\s:–—-]*(.*)$")


def entity_ref(name: str, type_: str) -> tuple[str, str]:
    """(entity id, kind) for a profile's entity: a country when its name is one, else a typed entity named by its slug."""
    if (iso := country_names.iso2(name)):
        return country_id(iso), "country"
    kind = _KIND.get(type_, "topic")
    return f"{kind}:{slug(name)}", kind


def _emit(store: JsonProfileStore, stem: str, sink: Sink) -> None:
    p = store.get(stem)
    if p is None:
        return
    doc = f"profile:{p.id}"
    when = day(p.as_of) or day(p.generated_at)
    body = " ".join([p.summary, *p.open_questions, *p.omissions, *(t.title for t in p.threads)])
    sink.document(doc, "profile", date=when, title=p.title, body=body, status=p.profile_status)

    ids: dict[str, str] = {}                                  # profile-local entity id -> index entity id
    for e in p.entities:
        canon = e.canonical_name or e.name
        eid, kind = entity_ref(canon, e.type)
        ids[e.id] = eid
        if kind != "country":
            sink.declare(eid, kind, canon, aliases=[e.name, *e.aliases], rank=flags.RANK_MENTIONED)
        sink.mention(entity=eid, document=doc, role=clip(e.role, 160) or e.type, date=when)
    for c in p.countries_of_relevance:
        iso = c.iso2 or country_names.iso2(c.name)
        if iso:
            sink.mention(entity=country_id(iso), document=doc, role=c.role or "country of relevance", date=when)

    sources = {s.id: s for s in p.source_ledger}
    known = [(norm(e.canonical_name or e.name), ids[e.id]) for e in p.entities if len(norm(e.canonical_name or e.name)) >= _NAME_MIN]
    for c in p.claim_ledger:
        cid = f"claim:{p.id}:{c.id}"
        created = (c.provenance.created_at if c.provenance else "") or p.generated_at
        sink.claim(cid, c.text, document_id=doc, status=c.status, grounding=c.grounding, created_at=day(created) or created)
        for ids_, relation in ((c.supported_by, "supports"), (c.contradicted_by, "contradicts")):
            for sid in ids_:
                s = sources.get(sid)
                if s is not None and s.url:
                    sink.cite(cid, s.url, title=s.title or s.publisher, fetched_at=s.retrieved_at, relation=relation)
        text = f" {norm(c.text)} "
        for n, eid in known:
            if f" {n} " in text:
                sink.mention(entity=eid, claim=cid, document=doc, role="in text", date=when)
    claims = {c.id for c in p.claim_ledger}
    for t in p.threads:
        linked = [ids[i] for i in t.entities if i in ids][:_THREAD_ENTITIES_MAX]
        for cl in t.claims:
            if cl in claims:
                for eid in linked:
                    sink.mention(entity=eid, claim=f"claim:{p.id}:{cl}", document=doc, role=f"thread: {clip(t.title, 80)}", date=when)
    for line in p.timeline:
        m = _DATED_LINE.match(line)
        if m and m.group(2):
            sink.event(f"profile-timeline:{p.id}:{m.group(1)}:{clip(m.group(2), 40)}", "profile_timeline", date=m.group(1), title=clip(m.group(2), 200),
                       document=doc)


def _units() -> Iterator[Unit]:
    store = JsonProfileStore()
    root = store.root
    for path in sorted(root.glob("*.json")) if root.is_dir() else ():
        yield Unit(f"profile:{path.stem}", file_digest(path), lambda sink, stem=path.stem: _emit(store, stem, sink), path=f"profile_store/{path.name}")


def _watermark() -> str:
    root = JsonProfileStore().root
    return mark(root.glob("*.json")) if root.is_dir() else "none"


SOURCE = Source("profiles", "profiles", _units, _watermark)
