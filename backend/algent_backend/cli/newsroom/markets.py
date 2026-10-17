"""
``newsroom markets`` — the Polymarket paper-trading benchmark. PAPER ONLY: no wallet, no key, no order is ever placed.

    newsroom markets refresh [--no-publish]     mirror (discover, snapshot, resolutions), then the paper pass (open, mark, settle) and publish (free)
    newsroom markets paper                      the paper pass alone: settle resolved positions, open per the edge rule, mark to market
    newsroom markets score [--full]             the scoreboard: us vs the market, calibration, paper P&L (--full: the whole document)
    newsroom markets list [--theater ID] [--status S] [--limit N]   the mirrored markets with their latest price
    newsroom markets forecast [--limit N] [--dry-run]   PAID: our blind probability for mirrored markets (day-capped)
    newsroom markets status                     last pass, counts, forecasts today and their spend

Every command prints one JSON document. See ``markets/`` and docs/architecture/markets-track-record.md.
"""

from __future__ import annotations

import json
from typing import Any


def add_parser(sub: Any) -> None:
    p = sub.add_parser("markets", help="Polymarket mirror, blind forecasts, paper portfolio and track record (paper only)")
    verbs = p.add_subparsers(dest="markets_cmd", required=True)
    r = verbs.add_parser("refresh", help="mirror pass + paper pass + publish (free)")
    r.add_argument("--no-publish", action="store_true")
    r.set_defaults(handler=run_refresh)
    verbs.add_parser("publish", help="push the track record to the site database").set_defaults(handler=run_publish)
    verbs.add_parser("paper", help="the paper portfolio pass").set_defaults(handler=run_paper)
    sc = verbs.add_parser("score", help="the scoreboard")
    sc.add_argument("--full", action="store_true")
    sc.set_defaults(handler=run_score)
    ls = verbs.add_parser("list", help="mirrored markets")
    ls.add_argument("--theater")
    ls.add_argument("--status", choices=["open", "resolved", "void"])
    ls.add_argument("--limit", type=int, default=40)
    ls.set_defaults(handler=run_list)
    fc = verbs.add_parser("forecast", help="blind forecasts for markets that need one (paid, capped per day)")
    fc.add_argument("--limit", type=int)
    fc.add_argument("--dry-run", action="store_true", help="list the markets that would be forecast; call nothing")
    fc.set_defaults(handler=run_forecast)
    verbs.add_parser("status", help="what the store holds and when it last ran").set_defaults(handler=run_status)


def _emit(doc: Any) -> int:
    print(json.dumps(doc, indent=2, ensure_ascii=False))
    return 0


def run_refresh(args: Any) -> int:
    from algent_backend.markets import mirror, paper

    from algent_backend.markets import publish

    report = mirror.refresh()
    report["paper"] = paper.run()
    if not args.no_publish:
        report["publish"] = publish.publish()
    return _emit(report)


def run_publish(_args: Any) -> int:
    from algent_backend.markets import publish

    return _emit(publish.publish())


def run_paper(_args: Any) -> int:
    from algent_backend.markets import paper

    return _emit({"pass": paper.run(), "portfolio": paper.summary()})


def run_score(args: Any) -> int:
    from algent_backend.markets import score

    doc = score.track_record()
    return _emit(doc if args.full else {k: doc[k] for k in ("markets", "forecasts", "scores", "portfolio", "market_beat_us")})


def _latest_prices() -> dict[str, float]:
    from algent_backend.markets import store

    return {mid: rows[-1].p for mid, rows in store.snapshots_by_market().items() if rows}


def run_list(args: Any) -> int:
    from algent_backend.markets import store

    price = _latest_prices()
    rows = [m for m in store.markets().values() if (not args.status or m.status == args.status) and (not args.theater or args.theater in m.theaters)]
    rows.sort(key=lambda m: -m.volume)
    return _emit({"count": len(rows), "markets": [{"id": m.id, "question": m.question, "p_yes": price.get(m.id), "status": m.status, "outcome": m.outcome,
                                                   "ends": m.end_date[:10], "volume": round(m.volume), "theaters": m.theaters, "countries": m.countries}
                                                  for m in rows[:args.limit]]})


def run_forecast(args: Any) -> int:
    from datetime import UTC, datetime

    from algent_backend.markets import forecast

    if args.dry_run:
        todo = forecast.candidates(datetime.now(UTC))
        return _emit({"candidates": len(todo), "first": [{"id": m.id, "question": m.question, "theaters": m.theaters} for m in todo[:20]]})
    from algent_backend.markets import paper, publish

    report = forecast.run(limit=args.limit)
    report["paper"] = paper.run()
    report["publish"] = publish.publish()
    return _emit(report)


def run_status(_args: Any) -> int:
    from algent_backend.markets import store

    ms = list(store.markets().values())
    return _emit({"store": str(store.root()), "markets": {s: sum(m.status == s for m in ms) for s in ("open", "resolved", "void")},
                  "snapshots": len(store.snapshots()), "forecasts": len(store.forecasts()), "trades": len(store.trades()), **store.load_status()})
