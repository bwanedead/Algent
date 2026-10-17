"""
``newsroom ai-benchmarks`` — the AI benchmark tracker (free collectors) and the capped self-reported discovery pass.

    newsroom ai-benchmarks fetch [--source S ...] [--no-publish]   collect every free source, then publish the site document (free)
    newsroom ai-benchmarks discover [--dry-run]                    lab-claimed scores: free search, then ONE capped model call (flags.DISCOVERY_*)
    newsroom ai-benchmarks publish                                 push the document to the site database
    newsroom ai-benchmarks status                                  per-source freshness: last fetch, newest result, stale flag and why
    newsroom ai-benchmarks show [--benchmark ID] [--limit N]       the stored benchmarks (or one benchmark's derived view)

Every command prints one JSON document. See ``ai_benchmarks/`` and docs/architecture/ai-desk.md.
"""

from __future__ import annotations

import json
from typing import Any


def add_parser(sub: Any) -> None:
    p = sub.add_parser("ai-benchmarks", help="AI benchmark scores across public leaderboards, plus lab-claimed scores (capped discovery)")
    verbs = p.add_subparsers(dest="aib_cmd", required=True)
    f = verbs.add_parser("fetch", help="collect the free sources and publish (free)")
    f.add_argument("--source", action="append", default=[], help="only these sources (epoch, swebench, lmarena); repeatable")
    f.add_argument("--no-publish", action="store_true")
    f.set_defaults(handler=run_fetch)
    d = verbs.add_parser("discover", help="self-reported scores: SearXNG + one low-effort model call, hard-capped per day")
    d.add_argument("--dry-run", action="store_true", help="search and read pages but make no model call")
    d.add_argument("--no-publish", action="store_true")
    d.set_defaults(handler=run_discover)
    verbs.add_parser("publish", help="push the document to the site database").set_defaults(handler=run_publish)
    verbs.add_parser("status", help="per-source freshness").set_defaults(handler=run_status)
    s = verbs.add_parser("show", help="stored benchmarks, or one benchmark's derived view")
    s.add_argument("--benchmark")
    s.add_argument("--limit", type=int, default=40)
    s.set_defaults(handler=run_show)


def _emit(doc: Any) -> int:
    print(json.dumps(doc, indent=2, ensure_ascii=False))
    return 0


def run_fetch(args: Any) -> int:
    from algent_backend.ai_benchmarks import collect, publish

    report = collect.collect(args.source or None)
    if not args.no_publish:
        report["publish"] = publish.publish()
    _emit(report)
    return 0 if any(r["status"] == "ok" for r in report["sources"]) else 1


def run_discover(args: Any) -> int:
    from algent_backend.ai_benchmarks import discovery, publish

    report = discovery.run(dry_run=args.dry_run)
    if report.get("stored") and not args.no_publish:
        report["publish"] = publish.publish()
    return _emit(report)


def run_publish(_args: Any) -> int:
    from algent_backend.ai_benchmarks import publish

    return _emit(publish.publish())


def run_status(_args: Any) -> int:
    from algent_backend.ai_benchmarks import freshness, store

    rows = freshness.source_health()
    return _emit({"store": str(store.root()), "results": len(store.current()), "benchmarks": len(store.benchmarks()), "sources": rows,
                  "stale": [r["source"] for r in rows if r["stale"]]})


def run_show(args: Any) -> int:
    from datetime import UTC, datetime

    from algent_backend.ai_benchmarks import derive, store

    cat, results, today = store.benchmarks(), store.current(), datetime.now(UTC).date()
    if args.benchmark:
        if args.benchmark not in cat:
            return _emit({"error": f"unknown benchmark {args.benchmark!r}", "known": sorted(cat)[:60]}) or 2
        return _emit(derive.view(cat[args.benchmark], results, as_of=today))
    rows = [v for b in cat.values() if (v := derive.view(b, results, as_of=today))]
    rows.sort(key=lambda v: -v["n_models"])
    return _emit({"count": len(rows), "benchmarks": [{"id": v["id"], "name": v["name"], "models": v["n_models"], "as_of": v["as_of"],
                                                       "best": v["best"], "saturation": v["saturation"], "open_lag_days": v["open_lag_days"]}
                                                      for v in rows[:args.limit]]})
