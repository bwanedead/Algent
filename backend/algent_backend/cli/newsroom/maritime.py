"""
``newsroom maritime`` — vessel behaviour events derived from our own AIS (free, no model).

    newsroom maritime events [--kind K] [--min-confidence C] [--limit N]   the current events (what the site and the daily read)
    newsroom maritime status                                               profile book size, event counts by kind, last pass
    newsroom maritime vessel MMSI                                          one vessel's profile: identity, changes, position history
    newsroom maritime compact-log [--apply]                                one-shot: rewrite the old log as compact transitions, summarise, cut to 7 days
    newsroom maritime publish [--full]                                     push events to the site database and link them into the ledger

The detectors run inside the stream service (``newsroom live ais``); these commands only read what it wrote. Every command prints one JSON
document. See ``maritime/`` and docs/architecture/maritime-behaviour.md.
"""

from __future__ import annotations

import json
from typing import Any


def add_parser(sub: Any) -> None:
    p = sub.add_parser("maritime", help="vessel behaviour events (AIS gaps, STS, identity changes, sanctioned vessels, loitering)")
    verbs = p.add_subparsers(dest="maritime_cmd", required=True)
    e = verbs.add_parser("events", help="the current behaviour events")
    e.add_argument("--kind", choices=["ais_gap", "sts", "identity", "sanctioned", "loiter"])
    e.add_argument("--min-confidence", type=float, default=0.0)
    e.add_argument("--limit", type=int, default=40)
    e.set_defaults(handler=run_events)
    verbs.add_parser("status", help="what the behaviour memory holds").set_defaults(handler=run_status)
    v = verbs.add_parser("vessel", help="one vessel's profile")
    v.add_argument("mmsi", type=int)
    v.set_defaults(handler=run_vessel)
    pb = verbs.add_parser("publish", help="push events to the site database and the ledger")
    pb.add_argument("--full", action="store_true", help="resend every current event, not just what changed")
    pb.set_defaults(handler=run_publish)
    ru = verbs.add_parser("rollup", help="daily per-zone summaries + retention of the raw event log (dry run unless --apply)")
    ru.add_argument("--apply", action="store_true", help="write the summaries and compact log.jsonl (default: report only)")
    ru.set_defaults(handler=run_rollup)
    cl = verbs.add_parser("compact-log", help="one-shot: summarise unrolled days, rewrite log.jsonl as compact transitions, cut to LOG_KEEP_DAYS (dry run unless --apply)")
    cl.add_argument("--apply", action="store_true", help="do it (default: report what it would do, with opens before / after dedupe)")
    cl.set_defaults(handler=run_compact_log)
    verbs.add_parser("store", help="size of every file in the maritime store").set_defaults(handler=run_store)


def run_rollup(args: Any) -> int:
    from algent_backend.maritime import rollup

    return _emit(rollup.run(apply=args.apply))


def run_compact_log(args: Any) -> int:
    from datetime import datetime, timezone

    from algent_backend.maritime import rollup

    return _emit(rollup.compact_log(now=datetime.now(timezone.utc).timestamp(), apply=args.apply))


def run_store(_args: Any) -> int:
    from algent_backend.maritime import rollup

    return _emit(rollup.store_report())


def _emit(doc: Any) -> int:
    print(json.dumps(doc, indent=2, ensure_ascii=False))
    return 0


def run_events(args: Any) -> int:
    from algent_backend.maritime import store

    rows = [e for e in store.read_current().values() if (not args.kind or e.kind == args.kind) and e.confidence >= args.min_confidence]
    rows.sort(key=lambda e: (e.last_seen or e.started_at), reverse=True)
    return _emit({"count": len(rows), "events": [e.model_dump() for e in rows[:args.limit]]})


def run_status(_args: Any) -> int:
    from algent_backend.maritime import store
    from algent_backend.maritime.profile import ProfileBook

    cur = list(store.read_current().values())
    kinds: dict[str, dict[str, int]] = {}
    for e in cur:
        k = kinds.setdefault(e.kind, {"total": 0, "active": 0})
        k["total"] += 1
        k["active"] += e.active
    p = store.profiles_path()
    book = ProfileBook.load(p)
    state = store.read_state()
    return _emit({"store": str(store.root()), "profiles": len(book.profiles), "profiles_bytes": p.stat().st_size if p.exists() else 0,
                  "with_imo": sum(1 for x in book.profiles.values() if x.imo), "events": kinds, "published_through": store.published_at(),
                  "last_cycle": state.get("last_cycle"), "blind_until": state.get("blind_until"),
                  "open_encounters": len(state.get("enc", {})), "open_dwell": len(state.get("dwell", {}))})


def run_vessel(args: Any) -> int:
    from algent_backend.maritime import store
    from algent_backend.maritime.contracts import iso
    from algent_backend.maritime.profile import ProfileBook

    p = ProfileBook.load(store.profiles_path()).get(args.mmsi)
    events = [e.model_dump() for e in store.read_current().values() if args.mmsi in (e.mmsi, e.mmsi2)]
    if p is None:
        return _emit({"mmsi": args.mmsi, "profile": None, "events": events})
    return _emit({"mmsi": p.mmsi, "name": p.name, "imo": p.imo, "ship_type": p.ship_type, "first": iso(p.first), "last": iso(p.last) if p.last else None,
                  "changes": [{"at": iso(c[0]), "kind": c[1], "from": c[2], "to": c[3]} for c in p.changes],
                  "track": [{"at": iso(t), "lat": la, "lon": lo, "kn": sg} for t, la, lo, sg in p.points()], "events": events})


def run_publish(args: Any) -> int:
    from algent_backend.maritime import publish

    out: dict[str, Any] = {"publish": publish.publish(full=args.full)}
    events, _ = publish.pending(full=True)
    out["ledger"] = publish.link_ledger(events)
    return _emit(out)
