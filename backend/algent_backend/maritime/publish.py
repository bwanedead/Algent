"""
Publish behaviour events to the site database (migration 013: ``maritime_events``, anon read-only) and link them into the geoledger.

Same contract as ``sanctions/publish`` and ``live/memory/anomalies.publish``: never raises, idempotent (upsert by id), a no-op without
``DATABASE_URL``. The events file is the source. An ONGOING event changes on every detector pass (its last-heard time, its evidence
points, its detail numbers), and rewriting a ~3 KB row with two JSONB columns every five minutes for a thousand events was the churn that
bloated the table; so a run sends an event only when its ``signature`` (what the site shows: state, area, confidence, words) changed or the
row is older than ``flags.PUBLISH_REFRESH_H`` (so ``last_seen`` and the evidence never go stale on the site). Events that ended more than
``RETAIN_DAYS`` ago are pruned from the table (and by the daily ``newsroom db prune``).

Geoledger link: an event on a vessel the ledger already knows (sanctioned vessels are assets of type ``vessel``; any other whose IMO has
an asset) becomes a ``behaviour_flagged`` status event, claimant "Ohmega analysis", provenance ``ohmega_derived`` - so the place view of
the ship carries what we saw beside everything else on record. Never creates an asset.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Any

from algent_backend.publishing import published_db, site_data
from algent_backend.publishing.published_db import _run

from . import flags, store
from .contracts import KINDS, LABEL, BehaviourEvent

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


def signature(e: BehaviourEvent) -> str:
    """Hash of what a reader of the site sees of an event; moving evidence, the last-heard time and raw detail numbers are not in it."""
    key = (e.kind, e.state, e.active, e.ended_at, e.started_at, e.name, e.name2, e.imo, e.flag, e.flag2, e.area, round(e.confidence, 2),
           e.rationale, e.summary)
    return hashlib.sha1(json.dumps(key, default=str).encode("utf-8")).hexdigest()[:16]


def _due(e: BehaviourEvent, sent: dict[str, list[str]], now: datetime) -> bool:
    prior = sent.get(e.id)
    if not prior or prior[0] != signature(e):
        return True
    try:
        return now - datetime.fromisoformat(prior[1]) >= timedelta(hours=flags.PUBLISH_REFRESH_H) and e.updated_at > prior[1]
    except ValueError:
        return True


def pending(*, full: bool = False, now: datetime | None = None) -> tuple[list[BehaviourEvent], str]:
    """(events to send, the new watermark): the ones whose signature changed, new ones, and ones not refreshed for PUBLISH_REFRESH_H."""
    now = now or datetime.now(timezone.utc)
    cur = list(store.read_current().values())
    sent = {} if full else store.published_sent()
    fresh = [e for e in cur if _due(e, sent, now)]
    return fresh, max((e.updated_at for e in cur), default=store.published_at())


# ── the site's documents (no database) ───────────────────────────────────────────────────────────
#: Evidence points kept in each published form: the /live map draws the last few, the analysis page lists a short track.
EVIDENCE_LIVE = 4
EVIDENCE_RECENT = 12
#: The /live layer shows what is going on now: still-going events and those that ended in the last LIVE_HOURS.
LIVE_HOURS = 48
RECENT_MAX = 1500
LIVE_MAX = 400
STABLE_FILE = "maritime_rows.json"


def event_row(e: BehaviourEvent, evidence: int) -> dict[str, Any]:
    """The site's row for one event (``MaritimeEvent`` in lib/maritime-shared.ts), with its evidence trimmed to the last ``evidence`` points."""
    d = e.model_dump()
    d["active"] = e.active
    d["last_seen"] = e.last_seen or None
    d["evidence"] = d["evidence"][-evidence:]
    return d


def _stable_rows(events: list[BehaviourEvent], now: datetime) -> dict[str, dict[str, Any]]:
    """Per event id the row to publish. An ongoing event changes on every detector pass (last heard, evidence, detail numbers); publishing
    each change would rewrite the documents every five minutes, so a row is replaced only when its ``signature`` (what a reader sees)
    changed or it is older than ``PUBLISH_REFRESH_H`` - the same rule the old table writer used."""
    from algent_backend.publishing import object_store

    path = object_store.held_dir() / STABLE_FILE
    try:
        kept = json.loads(path.read_text(encoding="utf-8"))
        kept = kept if isinstance(kept, dict) else {}
    except (OSError, ValueError):
        kept = {}
    out: dict[str, dict[str, Any]] = {}
    cache: dict[str, Any] = {}
    stamp = now.isoformat(timespec="seconds")
    for e in events:
        prior, sig = kept.get(e.id), signature(e)
        fresh = prior and prior["sig"] == sig and now - datetime.fromisoformat(prior["at"]) < timedelta(hours=flags.PUBLISH_REFRESH_H)
        entry = prior if fresh else {"sig": sig, "at": stamp, "row": event_row(e, EVIDENCE_RECENT)}
        cache[e.id] = entry
        out[e.id] = entry["row"]
    if cache != kept:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(cache, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        except OSError:
            pass
    return out


def documents(now: datetime | None = None, *, vessels: bool = True) -> dict[str, Any]:
    """The maritime products as site documents (egress-aware: each page fetches only what it renders):

    ``maritime/live.json``     still-going events plus those ended in the last ``LIVE_HOURS`` h, evidence trimmed to the last few points (/live, home)
    ``maritime/recent.json``   the last ``RETAIN_DAYS`` days, newest first (/intel/maritime)
    ``maritime/counts.json``   real totals for the page lead: all events kept, those still open, per kind
    ``maritime/vessel/<imo>.json``   the events of one vessel (a place page); only with ``vessels`` - the live passes leave them out (see ``run``)"""
    now = now or datetime.now(timezone.utc)
    cut = (now - timedelta(days=flags.RETAIN_DAYS)).isoformat(timespec="seconds")
    live_cut = (now - timedelta(hours=LIVE_HOURS)).isoformat(timespec="seconds")
    cur = [e for e in store.read_current().values() if e.ended_at is None or e.ended_at >= cut]
    cur.sort(key=lambda e: e.started_at, reverse=True)
    cur.sort(key=lambda e: not e.active)                        # stable sorts: active first, then newest start
    rows = _stable_rows(cur, now)
    recent = [rows[e.id] for e in cur][:RECENT_MAX]
    live = [{**rows[e.id], "evidence": rows[e.id]["evidence"][-EVIDENCE_LIVE:]} for e in cur
            if e.ended_at is None or e.ended_at >= live_cut][:LIVE_MAX]
    by_kind = {k: sum(1 for e in cur if e.kind == k) for k in KINDS}
    docs: dict[str, Any] = {
        "maritime/recent.json": {"events": recent},
        "maritime/live.json": {"events": live},
        "maritime/counts.json": {"total": len(cur), "ongoing": sum(1 for e in cur if e.ended_at is None), "byKind": by_kind},
    }
    if not vessels:
        return docs
    imos: dict[str, list[dict[str, Any]]] = {}
    for e in cur:
        if len(e.imo) == 7 and e.imo.isdigit():
            imos.setdefault(e.imo, []).append(rows[e.id])
    docs.update({f"maritime/vessel/{imo}.json": {"events": evs} for imo, evs in sorted(imos.items())})
    return docs


def publish_files(now: datetime | None = None, *, vessels: bool = True) -> dict[str, Any]:
    return site_data.publish_built(lambda: documents(now, vessels=vessels))


def publish(*, full: bool = False, connect: Callable[[], Any] | None = None, vessels: bool = True) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    files = publish_files(now, vessels=vessels)
    events, mark = pending(full=full, now=now)
    if published_db.files_only(connect):
        if files.get("ok") and events:                 # the default: documents only, no database; the record of what was sent still moves
            sent = {**store.published_sent(), **{e.id: [signature(e), now.isoformat(timespec="seconds")] for e in events}}
            store.save_published(mark, sent)
        return files
    if not events:
        return {"db": True, "events": 0, "note": "nothing new"}

    def work(conn: Any) -> dict:
        with conn.cursor() as cur:
            cur.executemany(_UPSERT, [row(e) for e in events])
            cur.execute(_PRUNE, (flags.RETAIN_DAYS,))
        return {"events": len(events)}

    result = _run(work, connect)
    if result.get("db"):
        sent = {**store.published_sent(), **{e.id: [signature(e), now.isoformat(timespec="seconds")] for e in events}}
        store.save_published(mark, sent)         # only after the commit: a failed publish is retried whole
    if files.get("ok"):
        result["files"] = files
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
        # The ~1,000 per-vessel documents are left to the daily ``maritime-vessels`` job: rewritten on every live pass (~340 a day) they were
        # ~80% of the R2 Class A budget (2026-10-28), for place pages that are rarely opened and do not need minute freshness.
        out = {"publish": publish(connect=connect, vessels=False)}
        if events:
            out["ledger"] = link_ledger(events)
        return out
    except Exception as exc:  # noqa: BLE001
        return {"error": f"{type(exc).__name__}: {str(exc)[:160]}"}
