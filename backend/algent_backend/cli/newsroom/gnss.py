"""
``newsroom gnss`` — GPS / GNSS interference zones derived from aircraft navigation accuracy (ADS-B), cross-checked against GPSJam.

    newsroom gnss run [--no-gpsjam] [--no-publish]   sample ADS-B, tally, rebuild today's zones, read GPSJam once a day, publish
    newsroom gnss zones [--day YYYY-MM-DD]           the day's zones from the local store
    newsroom gnss status                             per source: last good run, collecting since, baseline days
    newsroom gnss publish                            push zones to the site database

Every command prints one JSON document. See ``gnss/`` and docs/architecture/conflict-events-gnss.md.
"""

from __future__ import annotations

import json
from typing import Any


def add_parser(sub: Any) -> None:
    p = sub.add_parser("gnss", help="GNSS interference zones (ADS-B navigation integrity, GPSJam)")
    verbs = p.add_subparsers(dest="gnss_cmd", required=True)
    r = verbs.add_parser("run", help="one hourly pass")
    r.add_argument("--no-gpsjam", action="store_true")
    r.add_argument("--no-publish", action="store_true")
    r.set_defaults(handler=run_pass)
    z = verbs.add_parser("zones", help="a day's zones from the local store")
    z.add_argument("--day")
    z.set_defaults(handler=run_zones)
    verbs.add_parser("status", help="freshness and baseline").set_defaults(handler=run_status)
    verbs.add_parser("publish", help="push zones to the site database").set_defaults(handler=run_publish)


def _emit(doc: Any) -> int:
    print(json.dumps(doc, indent=2, ensure_ascii=False))
    return 0


def run_pass(args: Any) -> int:
    from algent_backend.gnss import collect, publish

    report = collect.run(with_gpsjam=not args.no_gpsjam)
    if not args.no_publish:
        report["publish"] = publish.publish()
    return _emit(report)


def run_zones(args: Any) -> int:
    from algent_backend.gnss import store

    day = args.day or (store.zone_days() or [""])[-1]
    return _emit(store.load_zones(day) if day else {})


def run_status(_args: Any) -> int:
    from algent_backend.gnss import store

    return _emit({"store": str(store.root()), "since": store.since(), "baseline_days": store.baseline_days(), "zone_days": store.zone_days()[-5:],
                  "sources": store.load_status()})


def run_publish(_args: Any) -> int:
    from algent_backend.gnss import publish

    return _emit(publish.publish())
