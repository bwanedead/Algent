"""
``newsroom satellite`` — fresh imagery and change flags for the places the desk tracks.

    newsroom satellite watch [--limit N]                    the ranked watch list (from the ledger, today's developments, chokepoints) and who is due
    newsroom satellite run [--site ID ...] [--limit N] [--no-publish]   one pass: look at the due sites, build the document, upload chips then document
    newsroom satellite status                               what the store holds: sites with imagery, last pass, verdict counts

Free (keyless public imagery); the timer runs ``run`` daily. Every command prints one JSON document. See satellite/ and docs/architecture/satellite.md.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Any


def add_parser(sub: Any) -> None:
    p = sub.add_parser("satellite", help="fresh satellite imagery of watched sites, with change flagged as a machine signal")
    verbs = p.add_subparsers(dest="satellite_cmd", required=True)
    w = verbs.add_parser("watch", help="the ranked watch list and who is due")
    w.add_argument("--limit", type=int, default=None)
    w.set_defaults(handler=run_watch)
    r = verbs.add_parser("run", help="one pass (the timer's job)")
    r.add_argument("--site", action="append", help="only this site id (repeatable); ignores the revisit rule")
    r.add_argument("--limit", type=int, default=None, help="sites this pass (default: flags.MAX_SITES_PER_PASS)")
    r.add_argument("--no-publish", action="store_true")
    r.set_defaults(handler=run_pass)
    verbs.add_parser("status", help="what the store holds").set_defaults(handler=run_status)


def _emit(doc: Any) -> int:
    print(json.dumps(doc, indent=2, ensure_ascii=False))
    return 0


def run_watch(args: Any) -> int:
    from algent_backend.geoledger.store import Ledger
    from algent_backend.satellite import store, watchlist

    now = datetime.now(timezone.utc)
    sites = watchlist.build(Ledger(), now)
    last = {s.id: (store.read_json(f"sites/{s.id}/state.json", {}) or {}).get("checked_at") for s in sites}
    due = {s.id for s in watchlist.select_due(sites, {k: v for k, v in last.items() if v}, now.timestamp(), args.limit)}
    return _emit({"watched": len(sites), "due": len(due),
                  "sites": [{"id": s.id, "name": s.name, "kind": s.kind, "priority": s.priority, "why": s.why, "event_on": s.event_on or None,
                             "due": s.id in due} for s in sites]})


def run_pass(args: Any) -> int:
    from algent_backend.satellite import run

    return _emit(run.run(only=args.site, limit=args.limit, do_publish=not args.no_publish))


def run_status(_args: Any) -> int:
    from algent_backend.satellite import store

    doc = store.read_json("doc.json") or {}
    recs = store.records()
    return _emit({"store": str(store.root()), "as_of": doc.get("as_of"), "age_hours": round((time.time() - datetime.fromisoformat(doc["as_of"]).timestamp()) / 3600, 1) if doc.get("as_of") else None,
                  "counts": doc.get("counts"), "records": len(recs), "last_pass": recs[-1]["pass_id"] if recs else None})
