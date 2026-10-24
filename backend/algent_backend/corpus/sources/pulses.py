"""
Pulses (0-100 assessed gauges of a situation): situations and pulses as entities, every reading of a pulse as a model-basis observation and a
searchable document (its rationale), recorded events, and the forward watches. The influence log stays the record; this is how it is found.
"""

from __future__ import annotations

from collections.abc import Iterator

from algent_backend.agent_system.agents.pulse import PulseStore

from .. import flags
from ..norm import clip, day
from ..sink import Sink
from .base import Source, Unit, digest_of, tree_mark


def pulse_id(raw: str) -> str:
    return f"pulse:{raw}"


def sit_id(raw: str) -> str:
    return f"situation:{raw}"


def _emit_situation(sit, pulses: list, sink: Sink) -> None:                      # noqa: ANN001 - pulse contracts
    sid = sit_id(sit.id)
    sink.declare(sid, "situation", sit.title, rank=flags.RANK_DECLARED, attrs={"domain": sit.domain, "status": sit.status, "summary": clip(sit.summary, 400)})
    for name in sit.entities:
        sink.relation("covers", src=sid, dst_surface=name, date=sit.created_at)
    for p in pulses:
        pid = pulse_id(p.id)
        sink.declare(pid, "pulse", p.name, rank=flags.RANK_DECLARED, attrs={"status": p.status, "question": p.definition.question if p.definitions else ""})
        sink.relation("has_pulse", src=sid, dst=pid, date=sit.created_at)


def _emit_log(p, log: list, sink: Sink) -> None:                                  # noqa: ANN001
    pid = pulse_id(p.id)
    sink.declare(pid, "pulse", p.name, rank=flags.RANK_DECLARED)
    for i in log:
        d = day(i.at)
        if i.rationale:
            doc = f"pulse-reading:{i.key or i.at}"
            sink.document(doc, "pulse_reading", date=d, title=f"{p.name}: {i.proposed_position if i.proposed_position is not None else 'no position'} ({i.decision})",
                          status=i.decision, body=i.rationale)
            sink.mention(entity=pid, document=doc, role=i.mode, date=d)
            sink.mention(entity=sit_id(p.situation_id), document=doc, role="situation", date=d)
        if i.proposed_position is not None and i.decision in ("applied", "reconcile"):
            sink.observation("pulse.position", i.at, i.proposed_position, entity=pid, unit="0-100", basis="model", label=p.name,
                             note=f"{i.mode}; confidence {i.confidence.overall()}; evidence through {i.evidence_through}")
        if i.mode == "blind" and i.absolute_position is not None:
            sink.observation("pulse.blind_position", i.at, i.absolute_position, entity=pid, unit="0-100", basis="model", label=f"{p.name} (blind read)",
                             note="a fresh read with the history set aside; never applied")


def _emit_event(e, sink: Sink) -> None:                                           # noqa: ANN001
    sink.event(f"event:pulse:{e.id}", "pulse_event", date=e.occurred_on, title=clip(e.summary, 200), detail=e.summary, place=e.place,
               actor_ids=[sit_id(s) for s in e.situation_ids], role="situation")


def _emit_watch(w, sink: Sink) -> None:                                           # noqa: ANN001
    sink.event(f"event:watch:{w.id}", "watch", date=w.horizon or day(w.created_at), title=clip(w.condition, 200), detail=f"{w.condition} {w.why} {w.evidence_needed}",
               status=w.status, actor_ids=[sit_id(w.situation_id)], role="situation")


def _units() -> Iterator[Unit]:
    store = PulseStore()
    for sit in store.situations():
        pulses = store.pulses(sit.id)
        yield Unit(f"pulse:situation:{sit.id}", digest_of([sit.model_dump(), [p.model_dump() for p in pulses]]),
                   lambda sink, sit=sit, pulses=pulses: _emit_situation(sit, pulses, sink), path=f"pulse_store/situations/{sit.id}.json")
    for p in store.pulses():
        log = store.log(p.id)
        yield Unit(f"pulse:log:{p.id}", digest_of([p.model_dump(), [i.model_dump() for i in log]]), lambda sink, p=p, log=log: _emit_log(p, log, sink),
                   date=day(log[-1].at) if log else "", path=f"pulse_store/log/{p.id}.jsonl")
    for e in store.events():
        yield Unit(f"pulse:event:{e.id}", digest_of(e.model_dump()), lambda sink, e=e: _emit_event(e, sink), date=e.occurred_on, path=f"pulse_store/events/{e.id}.json")
    for w in store.watches():
        yield Unit(f"pulse:watch:{w.id}", digest_of(w.model_dump()), lambda sink, w=w: _emit_watch(w, sink), path=f"pulse_store/watches/{w.id}.json")


def _watermark() -> str:
    root = PulseStore().root
    return "|".join(tree_mark(root / sub, "*.json*") for sub in ("situations", "pulses", "log", "events", "watches"))


SOURCE = Source("pulses", "pulses", _units, _watermark)
