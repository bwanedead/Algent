"""
The Postgres Pulse store — the live implementation of ``PulseRepository`` (schema: migrations/001).

Same surface and same invariants as the file store, with the database enforcing them a second time:
the influence key is the primary key (a retried run cannot write twice), the ledger rejects UPDATE
and DELETE by trigger, a definition version is a composite key, and a watch resolves once.

``pulse_state`` is refreshed after every append as a cache of the replay; state() still replays the
ledger, so a corrupted cache can never change what Ohmega believes.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from typing import Any

from .contracts import Event, Influence, Pulse, PulseDefinition, Situation, Source, Watch, influence_key
from .projection import PulseState, project
from .store import DuplicateInfluence


def _iso(v: Any) -> str:
    if isinstance(v, datetime):
        return v.astimezone(UTC).isoformat()
    if isinstance(v, date):
        return v.isoformat()
    return "" if v is None else str(v)


def _date_or_none(v: str) -> str | None:
    return v[:10] if v and len(v) >= 10 and v[:4].isdigit() else None


class PgPulseStore:
    def __init__(self, conn: Any = None) -> None:
        if conn is None:
            from algent_backend.database.migrate import connect

            conn = connect()
        self._c = conn

    def _q(self, sql: str, params: tuple = (), *, one: bool = False, rows: bool = True):
        with self._c.transaction():
            with self._c.cursor() as cur:
                cur.execute(sql, params)
                if not rows:
                    return None
                got = cur.fetchall() if cur.description else []
        return (got[0] if got else None) if one else got

    # ── situations ────────────────────────────────────────────────────────────────────────────
    def save_situation(self, s: Situation) -> None:
        self._q("""insert into situations (id, domain, title, summary, entities, parent_id, status)
                   values (%s, %s, %s, %s, %s, nullif(%s, ''), %s)
                   on conflict (id) do update set domain = excluded.domain, title = excluded.title,
                     summary = excluded.summary, entities = excluded.entities,
                     parent_id = excluded.parent_id, status = excluded.status""",
                (s.id, s.domain, s.title, s.summary, json.dumps(s.entities), s.parent_id, s.status),
                rows=False)

    def _situation(self, row) -> Situation:
        pulse_ids = [r[0] for r in self._q("select id from pulses where situation_id = %s order by created_at, id",
                                           (row[0],))]
        return Situation(id=row[0], domain=row[1], title=row[2], summary=row[3], entities=row[4] or [],
                         parent_id=row[5] or "", status=row[6], created_at=_iso(row[7]), pulse_ids=pulse_ids)

    _SIT = "select id, domain, title, summary, entities, parent_id, status, created_at from situations"

    def situation(self, situation_id: str) -> Situation | None:
        row = self._q(self._SIT + " where id = %s", (situation_id,), one=True)
        return self._situation(row) if row else None

    def situations(self) -> list[Situation]:
        return [self._situation(r) for r in self._q(self._SIT + " order by created_at, id")]

    # ── pulses and definitions ───────────────────────────────────────────────────────────────
    def create_pulse(self, pulse: Pulse) -> None:
        if not pulse.definitions:
            raise ValueError(f"pulse {pulse.id} has no definition (no ruler to assess against)")
        if self.pulse(pulse.id) is not None:
            raise ValueError(f"pulse {pulse.id} already exists — add a definition version instead")
        with self._c.transaction():
            with self._c.cursor() as cur:
                cur.execute("insert into pulses (id, situation_id, name, status) values (%s, %s, %s, %s)",
                            (pulse.id, pulse.situation_id, pulse.name, pulse.status))
                for i, d in enumerate(pulse.definitions, 1):
                    cur.execute("""insert into pulse_definitions (pulse_id, version, question, anchors, note)
                                   values (%s, %s, %s, %s, %s)""",
                                (pulse.id, i, d.question, json.dumps([a.model_dump() for a in d.anchors]), d.note))

    def add_definition(self, pulse_id: str, definition: PulseDefinition) -> int:
        pulse = self._require(pulse_id)
        version = pulse.definition.version + 1
        self._q("""insert into pulse_definitions (pulse_id, version, question, anchors, note)
                   values (%s, %s, %s, %s, %s)""",
                (pulse_id, version, definition.question,
                 json.dumps([a.model_dump() for a in definition.anchors]), definition.note), rows=False)
        return version

    def set_status(self, pulse_id: str, status: str) -> None:
        self._q("update pulses set status = %s where id = %s", (status, pulse_id), rows=False)

    def _pulse(self, row) -> Pulse:
        defs = [PulseDefinition(version=v, question=q, anchors=a or [], note=n or "", created_at=_iso(c))
                for v, q, a, n, c in self._q("""select version, question, anchors, note, created_at
                    from pulse_definitions where pulse_id = %s order by version""", (row[0],))]
        return Pulse(id=row[0], situation_id=row[1], name=row[2], status=row[3], definitions=defs)

    def pulse(self, pulse_id: str) -> Pulse | None:
        row = self._q("select id, situation_id, name, status from pulses where id = %s", (pulse_id,), one=True)
        return self._pulse(row) if row else None

    def pulses(self, situation_id: str | None = None) -> list[Pulse]:
        if situation_id is None:
            got = self._q("select id, situation_id, name, status from pulses order by situation_id, created_at, id")
        else:
            got = self._q("""select id, situation_id, name, status from pulses where situation_id = %s
                             order by created_at, id""", (situation_id,))
        return [self._pulse(r) for r in got]

    def _require(self, pulse_id: str) -> Pulse:
        pulse = self.pulse(pulse_id)
        if pulse is None:
            raise KeyError(f"no pulse {pulse_id}")
        return pulse

    # ── the influence ledger ─────────────────────────────────────────────────────────────────
    def append(self, influence: Influence) -> Influence:
        import psycopg

        if not influence.key:
            src = influence.source
            influence = influence.model_copy(update={"key": influence_key(
                influence.pulse_id, src.event_id, src.run_id, influence.mode)})
        i = influence
        try:
            self._q("""insert into pulse_influences (key, pulse_id, at, evidence_through, mode,
                         definition_version, proposed_position, decision, rationale, confidence, source,
                         prompt_version, model, watch_ids_triggered)
                       values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                    (i.key, i.pulse_id, i.at, _date_or_none(i.evidence_through), i.mode, i.definition_version,
                     i.proposed_position, i.decision, i.rationale, json.dumps(i.confidence.model_dump()),
                     json.dumps(i.source.model_dump()), i.prompt_version, i.model,
                     json.dumps(i.watch_ids_triggered)), rows=False)
        except psycopg.errors.UniqueViolation as exc:
            raise DuplicateInfluence(f"{i.key} already in {i.pulse_id}'s log") from exc
        self._cache_state(i.pulse_id)
        return i

    def log(self, pulse_id: str) -> list[Influence]:
        out = []
        for r in self._q("""select key, pulse_id, at, evidence_through, mode, definition_version,
                   proposed_position, decision, rationale, confidence, source, prompt_version, model,
                   watch_ids_triggered from pulse_influences where pulse_id = %s
                   order by at, recorded_at""", (pulse_id,)):
            out.append(Influence(key=r[0], pulse_id=r[1], at=_iso(r[2]), evidence_through=_iso(r[3]),
                                 mode=r[4], definition_version=r[5],
                                 proposed_position=float(r[6]) if r[6] is not None else None,
                                 decision=r[7], rationale=r[8], confidence=r[9] or {}, source=r[10] or {},
                                 prompt_version=r[11], model=r[12], watch_ids_triggered=r[13] or []))
        return out

    def state(self, pulse_id: str, *, as_of: str | None = None) -> PulseState:
        return project(pulse_id, self.log(pulse_id), as_of=as_of)

    def _cache_state(self, pulse_id: str) -> None:
        self._q("""insert into pulse_state (pulse_id, state, computed_at) values (%s, %s, now())
                   on conflict (pulse_id) do update set state = excluded.state, computed_at = now()""",
                (pulse_id, json.dumps(self.state(pulse_id).model_dump())), rows=False)

    # ── events ───────────────────────────────────────────────────────────────────────────────
    def record_event(self, event: Event) -> Event:
        old = self.event(event.id)
        if old is not None:
            event = old.model_copy(update={
                "situation_ids": list(dict.fromkeys([*old.situation_ids, *event.situation_ids])),
                "sources": [*old.sources, *[s for s in event.sources if s not in old.sources]]})
        with self._c.transaction():
            with self._c.cursor() as cur:
                cur.execute("""insert into events (id, occurred_on, place, summary, sources)
                               values (%s, %s, %s, %s, %s)
                               on conflict (id) do update set sources = excluded.sources""",
                            (event.id, _date_or_none(event.occurred_on), event.place, event.summary,
                             json.dumps([s.model_dump() for s in event.sources])))
                for sid in event.situation_ids:
                    cur.execute("""insert into situation_events (situation_id, event_id) values (%s, %s)
                                   on conflict do nothing""", (sid, event.id))
        return event

    def event(self, event_id: str) -> Event | None:
        row = self._q("select id, occurred_on, place, summary, sources from events where id = %s",
                      (event_id,), one=True)
        if row is None:
            return None
        sits = [r[0] for r in self._q("select situation_id from situation_events where event_id = %s", (event_id,))]
        return Event(id=row[0], occurred_on=_iso(row[1]), place=row[2], summary=row[3],
                     situation_ids=sits, sources=[Source.model_validate(s) for s in row[4] or []])

    # ── radar sightings ──────────────────────────────────────────────────────────────────────
    def add_sightings(self, situation_id: str, rows: list[dict]) -> int:
        added = 0
        with self._c.transaction():
            with self._c.cursor() as cur:
                for r in rows:
                    cur.execute("""insert into radar_sightings (situation_id, key, at, edition, headline)
                                   values (%s, %s, %s, %s, %s) on conflict do nothing""",
                                (situation_id, r["key"], r["at"], r["edition"], r["headline"]))
                    added += cur.rowcount
        return added

    def sightings(self, situation_id: str) -> list[dict]:
        return [{"key": k, "at": _iso(a), "edition": e, "headline": h} for k, a, e, h in self._q(
            "select key, at, edition, headline from radar_sightings where situation_id = %s order by at",
            (situation_id,))]

    # ── watches ──────────────────────────────────────────────────────────────────────────────
    _W = """select id, situation_id, condition, why, evidence_needed, expected_direction, horizon,
            origin_positions, status, created_at, resolved_at, resolved_by from watches"""

    def _watch(self, r) -> Watch:
        pids = [x[0] for x in self._q("select pulse_id from pulse_watches where watch_id = %s", (r[0],))]
        return Watch(id=r[0], situation_id=r[1], condition=r[2], why=r[3], evidence_needed=r[4],
                     expected_direction=r[5], horizon=_iso(r[6]), origin_positions=r[7] or {},
                     status=r[8], created_at=_iso(r[9]), resolved_at=_iso(r[10]),
                     resolved_by=Source.model_validate(r[11]) if r[11] else None, pulse_ids=pids)

    def save_watch(self, w: Watch) -> None:
        if self._q("select 1 from watches where id = %s", (w.id,), one=True):
            raise ValueError(f"watch {w.id} exists — resolve it, do not overwrite it")
        with self._c.transaction():
            with self._c.cursor() as cur:
                cur.execute("""insert into watches (id, situation_id, condition, why, evidence_needed,
                                 expected_direction, horizon, origin_positions)
                               values (%s, %s, %s, %s, %s, %s, %s, %s)""",
                            (w.id, w.situation_id, w.condition, w.why, w.evidence_needed,
                             w.expected_direction, _date_or_none(w.horizon), json.dumps(w.origin_positions)))
                for pid in w.pulse_ids:
                    cur.execute("insert into pulse_watches (pulse_id, watch_id) values (%s, %s)", (pid, w.id))

    def resolve_watch(self, watch_id: str, status: str, *, by: Any = None) -> Watch:
        if status not in ("triggered", "expired", "invalidated"):
            raise ValueError(f"not a terminal status: {status}")
        row = self._q(self._W + " where id = %s", (watch_id,), one=True)
        if row is None:
            raise KeyError(watch_id)
        if row[8] != "open":
            raise ValueError(f"watch {watch_id} is already {row[8]}")
        self._q("update watches set status = %s, resolved_at = now(), resolved_by = %s where id = %s",
                (status, json.dumps(by.model_dump()) if by else None, watch_id), rows=False)
        return self._watch(self._q(self._W + " where id = %s", (watch_id,), one=True))

    def watches(self, situation_id: str | None = None) -> list[Watch]:
        if situation_id is None:
            return [self._watch(r) for r in self._q(self._W + " order by created_at, id")]
        return [self._watch(r) for r in self._q(self._W + " where situation_id = %s order by created_at, id",
                                                (situation_id,))]
