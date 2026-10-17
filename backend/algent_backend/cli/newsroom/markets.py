"""
``newsroom markets`` — the Polymarket paper-trading benchmark. PAPER ONLY: no wallet, no key, no order is ever placed.

    newsroom markets refresh                    mirror: discover relevant markets, snapshot prices, record resolutions (free)
    newsroom markets list [--theater ID] [--status S] [--limit N]   the mirrored markets with their latest price
    newsroom markets status                     last pass, counts, forecasts today and their spend

Every command prints one JSON document. See ``markets/`` and docs/architecture/markets-track-record.md.
"""

from __future__ import annotations

import json
from typing import Any


def add_parser(sub: Any) -> None:
    p = sub.add_parser("markets", help="Polymarket mirror, blind forecasts, paper portfolio and track record (paper only)")
    verbs = p.add_subparsers(dest="markets_cmd", required=True)
    verbs.add_parser("refresh", help="mirror pass: discover, snapshot, record resolutions (free)").set_defaults(handler=run_refresh)
    ls = verbs.add_parser("list", help="mirrored markets")
    ls.add_argument("--theater")
    ls.add_argument("--status", choices=["open", "resolved", "void"])
    ls.add_argument("--limit", type=int, default=40)
    ls.set_defaults(handler=run_list)
    verbs.add_parser("status", help="what the store holds and when it last ran").set_defaults(handler=run_status)


def _emit(doc: Any) -> int:
    print(json.dumps(doc, indent=2, ensure_ascii=False))
    return 0


def run_refresh(_args: Any) -> int:
    from algent_backend.markets import mirror

    return _emit(mirror.refresh())


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


def run_status(_args: Any) -> int:
    from algent_backend.markets import store

    ms = list(store.markets().values())
    return _emit({"store": str(store.root()), "markets": {s: sum(m.status == s for m in ms) for s in ("open", "resolved", "void")},
                  "snapshots": len(store.snapshots()), "forecasts": len(store.forecasts()), "trades": len(store.trades()), **store.load_status()})
