"""
``newsroom elections`` — polls, poll averages and results for the elections near today (Wikipedia, free, no model call).

    newsroom elections run [--ask TEXT ...] [--no-gap-asks]   read the pages of calendar elections (past 30 / next 120 days) and of those the bots asked about; append changed snapshots
    newsroom elections show [SLUG]                            the elections held (latest snapshot summary), or one election's latest snapshot in full
    newsroom elections status                                 last run: when, elections read, snapshots added, errors

Every command prints one JSON document. See ``elections/`` and docs/architecture/elections.md.
"""

from __future__ import annotations

import json
from typing import Any


def add_parser(sub: Any) -> None:
    p = sub.add_parser("elections", help="election polls, poll averages and results (Wikipedia, free)")
    verbs = p.add_subparsers(dest="elections_cmd", required=True)
    r = verbs.add_parser("run", help="one daily pass")
    r.add_argument("--ask", action="append", default=[], help="an election named by hand (a poll or result ask); repeatable")
    r.add_argument("--no-gap-asks", action="store_true", help="do not read the bots' recent poll / result asks from the gap ledger")
    r.set_defaults(handler=run_pass)
    s = verbs.add_parser("show", help="the elections held, or one election's latest snapshot")
    s.add_argument("slug", nargs="?", default="")
    s.set_defaults(handler=run_show)
    verbs.add_parser("status", help="last run").set_defaults(handler=run_status)


def _emit(doc: Any) -> int:
    print(json.dumps(doc, indent=2, ensure_ascii=False))
    return 0


def gap_asks() -> list[str]:
    """The bots' recent poll / result asks, most-asked first. This package never reads markets itself; the CLI is the seam. A missing gap ledger is no asks."""
    try:
        from algent_backend.markets import gap_router, gaps

        return [c.topic for c in gaps.clusters() if gap_router.classify(c.topic, c.why) in ("poll", "result")]
    except Exception:  # noqa: BLE001 - the feed does not depend on the bots having asked
        return []


def run_pass(args: Any) -> int:
    from algent_backend.elections import collect

    asks = [*args.ask, *([] if args.no_gap_asks else gap_asks())]
    report = collect.run(asks=asks)
    report["asks"] = asks[:20]
    _emit(report)
    return 1 if report["errors"] and not report["elections"] else 0


def run_show(args: Any) -> int:
    from algent_backend.elections import store

    if args.slug:
        snap = store.latest(args.slug)
        return _emit(snap.model_dump(by_alias=True) if snap else {"error": f"no election {args.slug!r} in {store.root()}"})
    return _emit([{"slug": s.slug, "election": s.election, "country": s.country, "date": s.date, "read": s.acquired_at, "polls": sum(t.n_total for t in s.polls),
                   "tables": [{"heading": t.heading, "unit": t.unit, "n": t.n_total, "average": t.average.shares if t.average else None} for t in s.polls],
                   "results": s.results.status if s.results else None} for s in store.latest_all()])


def run_status(_args: Any) -> int:
    from algent_backend.elections import store

    return _emit({"store": str(store.root()), "elections": len(store.slugs()), **store.load_status()})
