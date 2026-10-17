"""
``newsroom sanctions`` — designations and delistings from the OFAC, UK and EU lists (free, no model).

    newsroom sanctions fetch [--source ofac ...] [--no-publish]   download, diff against the last snapshot, store events, publish
    newsroom sanctions events [--days N] [--source S] [--limit N] recent events from the local log
    newsroom sanctions status                                     per source: last good fetch, entries, last error
    newsroom sanctions publish [--full]                           push stored events to the site database

Every command prints one JSON document. See ``sanctions/`` and docs/architecture/sanctions-calendar.md.
"""

from __future__ import annotations

import json
from typing import Any


def add_parser(sub: Any) -> None:
    p = sub.add_parser("sanctions", help="sanctions designations / delistings from the OFAC, UK and EU lists")
    verbs = p.add_subparsers(dest="sanctions_cmd", required=True)
    f = verbs.add_parser("fetch", help="fetch the lists, diff, store, publish")
    f.add_argument("--source", action="append", choices=["ofac", "uk", "eu"], help="repeatable; default all")
    f.add_argument("--no-publish", action="store_true")
    f.set_defaults(handler=run_fetch)
    e = verbs.add_parser("events", help="recent events from the local log")
    e.add_argument("--days", type=int, default=14)
    e.add_argument("--source", choices=["ofac", "uk", "eu"])
    e.add_argument("--limit", type=int, default=40)
    e.set_defaults(handler=run_events)
    verbs.add_parser("status", help="per-source freshness").set_defaults(handler=run_status)
    pb = verbs.add_parser("publish", help="push stored events to the site database")
    pb.add_argument("--full", action="store_true", help="resend the recent window, not just what is new")
    pb.set_defaults(handler=run_publish)


def _emit(doc: Any) -> int:
    print(json.dumps(doc, indent=2, ensure_ascii=False))
    return 0


def run_fetch(args: Any) -> int:
    from algent_backend.sanctions import publish
    from algent_backend.sanctions.collect import collect

    report = collect(args.source)
    if not args.no_publish:
        report["publish"] = publish.publish()
        if report.get("vessels", {}).get("events"):          # newly designated ships are in the geoledger now: send them on
            from algent_backend.geoledger import publish as geo_publish

            report["geoledger_publish"] = geo_publish.publish()
    return _emit(report)


def run_events(args: Any) -> int:
    from datetime import date, timedelta

    from algent_backend.sanctions import store

    horizon = (date.today() - timedelta(days=args.days)).isoformat()
    rows = [e for e in store.events() if e.date >= horizon and (not args.source or e.source == args.source)]
    rows.sort(key=lambda e: (e.date, e.observed_on), reverse=True)
    return _emit({"count": len(rows), "events": [e.model_dump() for e in rows[:args.limit]]})


def run_status(_args: Any) -> int:
    from algent_backend.sanctions import store

    return _emit({"store": str(store.root()), "events": store.line_count(), "published": store.published_count(), "sources": store.load_status()})


def run_publish(args: Any) -> int:
    from algent_backend.sanctions import publish

    return _emit(publish.publish(full=args.full))
