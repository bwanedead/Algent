"""
``newsroom conflict`` — the attack / conflict event log (GDELT keyless; ReliefWeb, ACLED, UCDP behind keys).

    newsroom conflict fetch [--source gdelt ...] [--no-publish]   read the sources, dedupe, join assets, store, publish
    newsroom conflict events [--days N] [--country XX] [--type T] [--limit N]   recent events from the local log
    newsroom conflict status                                      per source: last good fetch, key needs, collecting since
    newsroom conflict publish [--full]                            push stored events to the site database

Every command prints one JSON document. See ``conflict/`` and docs/architecture/conflict-events-gnss.md.
"""

from __future__ import annotations

import json
from typing import Any

_SOURCES = ["gdelt", "reliefweb", "acled", "ucdp"]


def add_parser(sub: Any) -> None:
    p = sub.add_parser("conflict", help="attack / conflict event log (GDELT, ReliefWeb, ACLED, UCDP)")
    verbs = p.add_subparsers(dest="conflict_cmd", required=True)
    f = verbs.add_parser("fetch", help="read sources, store new events, publish")
    f.add_argument("--source", action="append", choices=_SOURCES, help="repeatable; default all")
    f.add_argument("--no-publish", action="store_true")
    f.set_defaults(handler=run_fetch)
    e = verbs.add_parser("events", help="recent events from the local log")
    e.add_argument("--days", type=int, default=3)
    e.add_argument("--country")
    e.add_argument("--type")
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
    from algent_backend.conflict import publish
    from algent_backend.conflict.collect import collect

    report = collect(args.source)
    if not args.no_publish:
        report["publish"] = publish.publish()
    return _emit(report)


def run_events(args: Any) -> int:
    from algent_backend.conflict import store

    rows = [e for e in store.events(args.days) if (not args.country or e.country == args.country.upper()) and (not args.type or e.type == args.type)]
    rows.sort(key=lambda e: (e.date, e.articles), reverse=True)
    return _emit({"count": len(rows), "events": [e.model_dump(exclude={"key"}) for e in rows[:args.limit]]})


def run_status(_args: Any) -> int:
    from algent_backend.conflict import store

    return _emit({"store": str(store.root()), "events": store.line_count(), "collecting_since": store.collecting_since(), "since": store.since(),
                  "cursor": store.load_cursor(), "sources": store.load_status()})


def run_publish(args: Any) -> int:
    from algent_backend.conflict import publish

    return _emit(publish.publish(full=args.full))
