"""
``newsroom flows`` — the world's circulation: ship lanes from our own AIS, and (apart from them) grain and money between countries.

    newsroom flows status                          what the lane tracker holds, how long it has watched, the trade cache's age
    newsroom flows lanes [--limit N]               the busiest lanes now (per-day rates over 7 and 30 days, by ship class)
    newsroom flows trade [--force]                 refresh the Comtrade grain and money picture when due (or now) and print its size
    newsroom flows backfill                        seed an EMPTY tracker from the maritime profile book's last days of positions
    newsroom flows publish [--no-publish] [--allow-empty]   refresh trade if due, build the ``flows`` document, upload it (the timer's job)

The lane tracker runs inside the stream service (``newsroom live ais``); these commands read what it wrote. Free: no model, no spend.
Every command prints one JSON document. See ``flows/`` and docs/architecture/flows.md.
"""

from __future__ import annotations

import json
import time
from typing import Any


def add_parser(sub: Any) -> None:
    p = sub.add_parser("flows", help="ship lanes from our AIS; grain and money flows between countries")
    verbs = p.add_subparsers(dest="flows_cmd", required=True)
    verbs.add_parser("status", help="tracker and trade cache state").set_defaults(handler=run_status)
    ln = verbs.add_parser("lanes", help="the busiest lanes")
    ln.add_argument("--limit", type=int, default=25)
    ln.set_defaults(handler=run_lanes)
    tr = verbs.add_parser("trade", help="refresh the Comtrade picture")
    tr.add_argument("--force", action="store_true", help="refresh even if the cache is fresh")
    tr.set_defaults(handler=run_trade)
    verbs.add_parser("backfill", help="seed an empty tracker from the maritime profile book").set_defaults(handler=run_backfill)
    pb = verbs.add_parser("publish", help="build and upload the flows document")
    pb.add_argument("--no-publish", action="store_true", help="build and keep the local copy only")
    pb.add_argument("--allow-empty", action="store_true", help="publish even when this machine holds no lane aggregates")
    pb.add_argument("--force-trade", action="store_true")
    pb.set_defaults(handler=run_publish)


def _emit(doc: Any) -> int:
    print(json.dumps(doc, indent=2, ensure_ascii=False))
    return 0


def run_status(_args: Any) -> int:
    from algent_backend.flows import store
    from algent_backend.flows.tracker import LaneTracker
    from algent_backend.flows.trade import refresh

    t = LaneTracker.load()
    trade = refresh.load()
    return _emit({"store": str(store.root()), "vessels_tracked": len(t.last), "days": {d: {"hours_watched": round(v["secs"] / 3600, 1),
                  "lane_counts": sum(sum(sum(x) for x in cs.values()) for cs in v["lanes"].values()),
                  "visits": sum(sum(cs.values()) for cs in v["visits"].values())} for d, v in sorted(t.days.items())[-10:]},
                  "trade_fetched_at": (trade or {}).get("fetched_at"),
                  "trade_flows": {"grain": {k: len(c["flows"]) for k, c in ((trade or {}).get("grain") or {}).items()},
                                  "money": len(((trade or {}).get("money") or {}).get("flows", []))}})


def run_lanes(args: Any) -> int:
    from algent_backend.flows import document
    from algent_backend.flows.tracker import LaneTracker

    t = LaneTracker.load()
    doc = document.build(t.days, t.samples, None, time.time())
    lanes = sorted(doc["ais"]["lanes"], key=lambda x: -(x["r7"] or x["r30"]))[:args.limit]
    return _emit({"days_watched": doc["ais"]["days"], "since": doc["ais"]["since"],
                  "lanes": [{"lane": f"{x['a']} > {x['b']}", "per_day_7d": x["r7"], "per_day_30d": x["r30"], "by_class": x["by"], "inferred_share": x["inf"]} for x in lanes],
                  "anomalies": [{"place": p["id"], "dir": p["dir"], "z": p["z"], "usual": p["usual"], "last": p["last"]} for p in doc["ais"]["places"] if p.get("dir")]})


def run_trade(args: Any) -> int:
    from algent_backend.flows.trade import refresh

    doc = refresh.refresh(force=args.force)
    return _emit({"fetched_at": doc.get("fetched_at"),
                  "grain": {k: {"flows": len(c["flows"]), "missing": c["missing"]} for k, c in (doc.get("grain") or {}).items()},
                  "money": {"flows": len((doc.get("money") or {}).get("flows", [])), "missing": (doc.get("money") or {}).get("missing", [])}})


def run_backfill(_args: Any) -> int:
    from algent_backend.flows import backfill
    from algent_backend.flows.tracker import LaneTracker
    from algent_backend.maritime import store as maritime_store
    from algent_backend.maritime.profile import ProfileBook

    book = ProfileBook.load(maritime_store.profiles_path())
    t = LaneTracker.load()
    out = backfill.from_book(book, t)
    if "skipped" not in out:
        LaneTracker.write(t.snapshot(time.time()))
    return _emit(out)


def run_publish(args: Any) -> int:
    from algent_backend.flows import publish

    return _emit(publish.run(publish=not args.no_publish, allow_empty=args.allow_empty, force_trade=args.force_trade))
