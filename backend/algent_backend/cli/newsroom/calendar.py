"""
``newsroom calendar`` — the forward-looking calendar (free, no model).

    newsroom calendar refresh [--source fed ...] [--group schedules|fast] [--no-publish]   fetch the schedules, sync the store, publish
    newsroom calendar upcoming [--days N] [--kind K] [--country ISO2]   what is coming up, from the local store
    newsroom calendar status                                       per source: last good fetch, items, last error
    newsroom calendar publish                                      push the store to the site database
    newsroom calendar extract --date YYYY-MM-DD [--domain geopolitics]   (re)extract deadlines from a stored daily report

Every command prints one JSON document. See ``lookahead/`` and docs/architecture/sanctions-calendar.md.
"""

from __future__ import annotations

import json
from typing import Any

def _sources() -> list[str]:
    from algent_backend.lookahead import collect

    return collect.names()


def add_parser(sub: Any) -> None:
    p = sub.add_parser("calendar", help="upcoming elections, central-bank decisions, releases, summits, launches, our markets, extracted deadlines")
    verbs = p.add_subparsers(dest="calendar_cmd", required=True)
    r = verbs.add_parser("refresh", help="fetch the schedule sources, sync, publish")
    r.add_argument("--source", action="append", choices=_sources(), help="repeatable; default all")
    r.add_argument("--group", choices=["schedules", "fast"], help="a cadence class (daily schedules; the six-hourly fast sources)")
    r.add_argument("--no-publish", action="store_true")
    r.set_defaults(handler=run_refresh)
    u = verbs.add_parser("upcoming", help="the local store's upcoming items")
    u.add_argument("--days", type=int, default=30)
    u.add_argument("--kind")
    u.add_argument("--country")
    u.set_defaults(handler=run_upcoming)
    verbs.add_parser("status", help="per-source freshness").set_defaults(handler=run_status)
    verbs.add_parser("publish", help="push the store to the site database").set_defaults(handler=run_publish)
    x = verbs.add_parser("extract", help="extract deadlines from a stored daily report")
    x.add_argument("--date", required=True)
    x.add_argument("--domain", default="geopolitics")
    x.set_defaults(handler=run_extract)


def _emit(doc: Any) -> int:
    print(json.dumps(doc, indent=2, ensure_ascii=False))
    return 0


def run_refresh(args: Any) -> int:
    from algent_backend.lookahead import publish
    from algent_backend.lookahead.collect import refresh

    report = refresh(args.source, group=args.group)
    if not args.no_publish:
        report["publish"] = publish.publish()
    return _emit(report)


def run_upcoming(args: Any) -> int:
    from datetime import date

    from algent_backend.lookahead import store

    rows = [i for i in store.upcoming(date.today(), args.days) if (not args.kind or i.kind == args.kind) and (not args.country or args.country.upper() in i.countries)]
    return _emit({"count": len(rows), "items": [i.model_dump() for i in rows]})


def run_status(_args: Any) -> int:
    from algent_backend.lookahead import store

    cur = store.current()
    return _emit({"store": str(store.root()), "items": len(cur), "active": sum(i.active for i in cur.values()), "sources": store.load_status()})


def run_publish(_args: Any) -> int:
    from algent_backend.lookahead import publish

    return _emit(publish.publish())


def run_extract(args: Any) -> int:
    from algent_backend.agent_system.agents.intel.daily import daily_dir
    from algent_backend.lookahead import extract, publish

    path = daily_dir(args.domain) / f"{args.date}.json"
    if not path.is_file():
        return _emit({"error": f"no stored daily for {args.domain} {args.date}"})
    report = json.loads(path.read_text(encoding="utf-8"))
    res = extract.attach(report.get("theaters") or [], as_of=args.date)
    return _emit({"extract": res, "publish": publish.publish()})
