"""
Publish behaviour events to the site database (migration 013: ``maritime_events``, anon read-only) and link them into the geoledger.

Same contract as ``sanctions/publish`` and ``live/memory/anomalies.publish``: never raises, idempotent (upsert by id), a no-op without
``DATABASE_URL``. The events file is the source; a watermark (``published.json``: the newest ``updated_at`` sent) means a run sends only
what changed, and an unchanged picture costs no database call. Events that ended more than ``RETAIN_DAYS`` ago are pruned from the table.

Geoledger link: an event on a vessel the ledger already knows (sanctioned vessels are assets of type ``vessel``; any other whose IMO has
an asset) becomes a ``behaviour_flagged`` status event, claimant "Ohmega analysis", provenance ``ohmega_derived`` - so the place view of
the ship carries what we saw beside everything else on record. Never creates an asset.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from algent_backend.publishing.published_db import _run

from . import flags, store
from .contracts import LABEL, BehaviourEvent

SITE_URL = "https://www.ohmega.monster/intel/maritime"
CLAIMANT = "Ohmega analysis"
_COLUMNS = ("id", "kind", "mmsi", "mmsi2", "name", "name2", "imo", "flag", "flag2", "ship_class", "started_at", "ended_at", "last_seen", "state",
            "active", "lat", "lon", "area", "countries", "confidence", "rationale", "summary", "detail", "evidence", "provenance")
_UPSERT = f"""
insert into maritime_events ({', '.join(_COLUMNS)})
values ({', '.join('%s::jsonb' if c in ('detail', 'evidence') else '%s' for c in _COLUMNS)})
on conflict (id) do update set {', '.join(f'{c} = excluded.{c}' for c in _COLUMNS if c != 'id')}, updated_at = now()
"""
_PRUNE = "delete from maritime_events where ended_at is not null and ended_at < now() - make_interval(days => %s)"


def row(e: BehaviourEvent) -> tuple:
    d = e.model_dump()
    d["active"] = e.active
    d["last_seen"] = e.last_seen or None
    d["detail"] = json.dumps(e.detail, ensure_ascii=False).replace("\\u0000", "")
    d["evidence"] = json.dumps(e.evidence, ensure_ascii=False)
    return tuple(d[c] for c in _COLUMNS)


def pending(*, full: bool = False) -> tuple[list[BehaviourEvent], str]:
    """(events changed since the watermark, the new watermark)."""
    cur = list(store.read_current().values())
    mark = "" if full else store.published_at()
    fresh = [e for e in cur if e.updated_at > mark]
    return fresh, max((e.updated_at for e in cur), default=mark)


def publish(*, full: bool = False, connect: Callable[[], Any] | None = None) -> dict[str, Any]:
    events, mark = pending(full=full)
    if not events:
        return {"db": True, "events": 0, "note": "nothing new"}

    def work(conn: Any) -> dict:
        with conn.cursor() as cur:
            cur.executemany(_UPSERT, [row(e) for e in events])
            cur.execute(_PRUNE, (flags.RETAIN_DAYS,))
        return {"events": len(events)}

    result = _run(work, connect)
    if result.get("db"):
        store.save_published(mark)               # only after the commit: a failed publish is retried whole
    return result


# ── geoledger ────────────────────────────────────────────────────────────────────────────────────
def _asset_for(e: BehaviourEvent, ledger: Any) -> str | None:
    for aid in (e.detail.get("asset_id"), f"og-xx-vessel-imo{e.imo}" if e.imo else None):
        if aid and aid in ledger.assets:
            return str(aid)
    return None


def link_ledger(events: list[BehaviourEvent], ledger: Any = None) -> dict[str, int]:
    """Record each event on a vessel the ledger knows as a ``behaviour_flagged`` status event. Idempotent (deterministic ids: one claim per
    vessel and day). Never raises."""
    done = {"events": 0, "skipped": 0}
    try:
        from algent_backend.geoledger.ingest import add_event
        from algent_backend.geoledger.store import Ledger

        ledger = ledger or Ledger()
        for e in events:
            aid = _asset_for(e, ledger)
            if aid is None:
                continue
            conf = "high" if e.confidence >= 0.7 else "medium" if e.confidence >= 0.4 else "low"
            try:
                add_event(ledger, aid, status="behaviour_flagged", claimant=CLAIMANT, occurred_on=e.started_at[:10], sources=[SITE_URL],
                          confidence=conf, note=f"{LABEL[e.kind]}: {e.summary}"[:240], via=f"maritime:{e.id}")
                done["events"] += 1
            except ValueError:
                done["skipped"] += 1
    except Exception:  # noqa: BLE001 - the ledger link is an addition; the events are already stored
        done["skipped"] += 1
    return done


def run(*, connect: Callable[[], Any] | None = None) -> dict[str, Any]:
    """What the timer runner calls: publish what changed, and link the changed events into the ledger. Never raises."""
    try:
        events, _ = pending()
        out = {"publish": publish(connect=connect)}
        if events:
            out["ledger"] = link_ledger(events)
        return out
    except Exception as exc:  # noqa: BLE001
        return {"error": f"{type(exc).__name__}: {str(exc)[:160]}"}
