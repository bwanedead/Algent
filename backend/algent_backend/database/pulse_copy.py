"""
Copy the Pulse ledger from one repository into another — the file store into Postgres, once it exists.

Pulses accumulate history on the file store while the database is being set up; this moves all of it
across without loss: situations, every definition version, the full influence log (original keys and
timestamps preserved, so idempotency carries over), events, watches with their resolution, and radar
sightings. Running it twice is harmless — every write is keyed and duplicates are skipped.

    python -m algent_backend.database copy-pulses
"""

from __future__ import annotations

from typing import Any


def copy_ledger(src: Any, dst: Any) -> dict:
    from algent_backend.agent_system.agents.pulse.store import DuplicateInfluence

    counts = {"situations": 0, "pulses": 0, "influences": 0, "watches": 0, "sightings": 0, "events": 0}
    for sit in src.situations():
        dst.save_situation(sit.model_copy(update={"pulse_ids": []}))
        counts["situations"] += 1
        counts["sightings"] += dst.add_sightings(sit.id, src.sightings(sit.id))
    for pulse in src.pulses():
        if dst.pulse(pulse.id) is None:
            dst.create_pulse(pulse)
            counts["pulses"] += 1
        for inf in src.log(pulse.id):
            try:
                dst.append(inf)
                counts["influences"] += 1
            except DuplicateInfluence:
                pass
            if inf.source.event_id:
                ev = src.event(inf.source.event_id)
                if ev is not None and dst.event(ev.id) is None:
                    dst.record_event(ev)
                    counts["events"] += 1
    done = {w.id for w in dst.watches()}
    for w in src.watches():
        if w.id in done:
            continue
        dst.save_watch(w.model_copy(update={"status": "open", "resolved_at": "", "resolved_by": None}))
        if w.status != "open":
            dst.resolve_watch(w.id, w.status, by=w.resolved_by)
        counts["watches"] += 1
    return counts


def copy_files_to_postgres() -> dict:
    from algent_backend.agent_system.agents.pulse.pg_store import PgPulseStore
    from algent_backend.agent_system.agents.pulse.store import PulseStore

    return copy_ledger(PulseStore(), PgPulseStore())
