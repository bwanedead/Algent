"""
``newsroom instruments`` — Ohmega's numbers layer: fetch, inspect, and read the moves.

    newsroom instruments fetch [--series ID ...] [--backfill]
    newsroom instruments show [--series ID] [--last N]
    newsroom instruments moves [--tag hormuz ...] [--series ID ...] [--as-of YYYY-MM-DD]

``fetch`` pulls the free public sources into the append-only store (no model, no paid call);
``--backfill`` additionally asks each provider for up to ~5 years of history (bounded, one-off).
``show`` lists the catalog or one series' stored observations; ``moves`` prints the latest
reading, changes and unusual flags per series. Every command prints one JSON document.
"""

from __future__ import annotations

import json
from datetime import date
from typing import Any

from algent_backend.instruments import store
from algent_backend.instruments.catalog import CATALOG, get_series
from algent_backend.instruments.collect import collect
from algent_backend.instruments.evidence import moves_board


def add_parser(sub: Any) -> None:
    p = sub.add_parser("instruments", help="numbers layer: fetch free public series, show them, read the moves")
    verbs = p.add_subparsers(dest="instruments_cmd", required=True)
    f = verbs.add_parser("fetch", help="pull series into the store (all, or --series)")
    f.add_argument("--series", action="append", help="series id (repeatable); default all")
    f.add_argument("--backfill", action="store_true", help="also pull up to ~5 years of history (bounded, one-off)")
    f.set_defaults(handler=run_fetch)
    s = verbs.add_parser("show", help="the catalog with stored coverage, or one series' observations")
    s.add_argument("--series")
    s.add_argument("--last", type=int, default=30, help="observations to show for --series (default 30)")
    s.set_defaults(handler=run_show)
    m = verbs.add_parser("moves", help="latest reading, changes and unusual flags per series")
    m.add_argument("--tag", action="append", help="match series carrying this tag (repeatable), e.g. hormuz")
    m.add_argument("--series", action="append", help="series id (repeatable)")
    m.add_argument("--as-of", help="replay the numbers as of YYYY-MM-DD")
    m.set_defaults(handler=run_moves)


def _emit(doc: Any) -> int:
    print(json.dumps(doc, indent=2, ensure_ascii=False))
    return 0


def run_fetch(args: Any) -> int:
    for sid in args.series or []:
        get_series(sid)                      # unknown id fails fast, before any request
    return _emit(collect(args.series, backfill=args.backfill))


def run_show(args: Any) -> int:
    if args.series:
        s = get_series(args.series)
        hist = store.history(s.id)
        return _emit({"series": s.model_dump(), "n_obs": len(hist),
                      "observations": [o.model_dump() for o in hist[-args.last:]]})
    rows = []
    for s in CATALOG:
        hist = store.history(s.id)
        rows.append({"id": s.id, "name": s.name, "unit": s.unit, "frequency": s.frequency, "source": s.source,
                     "public_display": s.public_display, "n_obs": len(hist),
                     "latest": {"period": hist[-1].period, "value": hist[-1].value} if hist else None})
    return _emit({"store": str(store.store_dir()), "series": rows})


def run_moves(args: Any) -> int:
    as_of = date.fromisoformat(args.as_of) if args.as_of else None
    rows = moves_board(args.tag, as_of=as_of)
    if args.series:
        rows = [r for r in rows if r["series_id"] in set(args.series)]
    return _emit({"as_of": (as_of or date.today()).isoformat(), "tags": args.tag or [],
                  "count": len(rows), "unusual": [r["series_id"] for r in rows if r["unusual"]], "moves": rows})
