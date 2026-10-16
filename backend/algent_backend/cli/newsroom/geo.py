"""
``newsroom geo`` — the geospatial asset ledger: places that exist and what has been said about their state.

    newsroom geo seed [--source wri|osm|all] [--file PATH] [--theater NAME | --bbox W,S,E,N] [--kinds K ...]
    newsroom geo extract [--since YYYY-MM-DD | --days 30] [--kinds daily profiles statements library] [--limit N] [--dry-run]
    newsroom geo add-event ASSET_ID --status S --claimant WHO --date YYYY-MM-DD --source URL [--confidence C] [--note T]
    newsroom geo find NAME [--country UA] [--type power_plant]
    newsroom geo show ASSET_ID
    newsroom geo merge DUP INTO [--note T]
    newsroom geo grid ISO [--as-of YYYY-MM-DD] [--publish]
    newsroom geo publish [--full]
    newsroom geo status

``seed`` downloads open data only when asked (WRI: one zip, CC BY 4.0; OSM: Overpass, cached, polite) or reads ``--file``.
``extract`` is the backfill over stored texts (one cheap model call per material, each text read once ever; ``--dry-run``
counts what it would read and spends nothing). Each command prints one JSON document. Store: ``geoledger_store/``
(override: ``ALGENT_GEOLEDGER_STORE``). Docs: docs/architecture/geoledger.md.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def add_parser(sub: Any) -> None:
    from algent_backend.geoledger import backfill, seed_osm

    p = sub.add_parser("geo", help="the geospatial asset ledger: places and their status history")
    v = p.add_subparsers(dest="geo_verb", required=True)
    s = v.add_parser("seed", help="seed assets from open data (WRI power plants, OpenStreetMap)")
    s.add_argument("--source", choices=("wri", "osm", "all"), default="all")
    s.add_argument("--file", help="a local WRI csv or zip instead of downloading it")
    s.add_argument("--theater", choices=sorted(seed_osm.PRESETS), action="append", help="an OSM box by name (repeatable); default all")
    s.add_argument("--bbox", help="an OSM box W,S,E,N in degrees")
    s.add_argument("--kinds", nargs="+", choices=sorted(seed_osm.KINDS), help="OSM kinds (default all)")
    e = v.add_parser("extract", help="backfill: read stored texts into the ledger (model calls; each text once)")
    e.add_argument("--since", help="only texts dated on/after this day")
    e.add_argument("--days", type=int, default=30, help="window when --since is not given")
    e.add_argument("--kinds", nargs="+", choices=backfill.KINDS, default=list(backfill.KINDS))
    e.add_argument("--limit", type=int, help="read at most this many materials")
    e.add_argument("--dry-run", action="store_true", help="count what would be read; no model call")
    a = v.add_parser("add-event", help="record one dated, sourced status event")
    a.add_argument("asset_id")
    a.add_argument("--status", required=True)
    a.add_argument("--claimant", required=True, help="who says it (a status is always somebody's word)")
    a.add_argument("--date", required=True, help="YYYY-MM-DD")
    a.add_argument("--source", action="append", required=True, help="source URL (repeatable)")
    a.add_argument("--confidence", default="medium", choices=("low", "medium", "high"))
    a.add_argument("--note", default="")
    f = v.add_parser("find", help="search assets by name")
    f.add_argument("name")
    f.add_argument("--country", default="")
    f.add_argument("--type", default="other")
    sh = v.add_parser("show", help="one asset and its status history")
    sh.add_argument("asset_id")
    pu = v.add_parser("publish", help="push new assets and events to the site database")
    pu.add_argument("--full", action="store_true", help="resend everything, not just what is new")
    v.add_parser("status", help="counts: assets by type, events, unpublished lines")
    mg = v.add_parser("merge", help="record that asset DUP is the same place as INTO (history kept, nothing deleted)")
    mg.add_argument("dup")
    mg.add_argument("into")
    mg.add_argument("--note", default="")
    g = v.add_parser("grid", help="grid-impact rollup of a country: installed capacity claimed / reported / confirmed struck")
    g.add_argument("iso")
    g.add_argument("--as-of", help="YYYY-MM-DD (default today)")
    g.add_argument("--publish", action="store_true", help="also upsert it to the site database")
    p.set_defaults(handler=run_geo)


def _emit(doc: Any, code: int = 0) -> int:
    print(json.dumps(doc, indent=2, ensure_ascii=False, default=str))
    return code


def run_geo(args: Any) -> int:
    return {"seed": _seed, "extract": _extract, "add-event": _add_event, "find": _find, "show": _show,
            "publish": _publish, "status": _status, "merge": _merge, "grid": _grid}[args.geo_verb](args)


def _seed(args: Any) -> int:
    from algent_backend.geoledger import seed_osm, seed_wri
    from algent_backend.geoledger.store import Ledger

    ledger, report = Ledger(), {}
    if args.source in ("wri", "all"):
        report["wri"] = seed_wri.seed(ledger, path=Path(args.file) if args.file else None)
    if args.source in ("osm", "all"):
        boxes = {args.bbox: [float(x) for x in args.bbox.split(",")]} if args.bbox else {t: seed_osm.PRESETS[t] for t in (args.theater or seed_osm.PRESETS)}
        report["osm"] = {name: seed_osm.seed(ledger, box, args.kinds) for name, box in boxes.items()}
    report["ledger"] = ledger.counts()
    return _emit(report)


def _extract(args: Any) -> int:
    from algent_backend.geoledger import backfill
    from algent_backend.geoledger.ask import house_ask
    from algent_backend.geoledger.store import Ledger

    since = args.since or backfill.since_from_days(args.days)
    ledger, kinds = Ledger(), tuple(args.kinds)
    if args.dry_run:
        todo = backfill.plan(since, kinds, ledger)
        chars = sum(len(i.text) for m in todo for i in m.items)
        return _emit({"since": since, "materials": len(todo), "input_chars": chars, "approx_input_tokens": chars // 4,
                      "calls": sum(len(m.batches()) for m in todo), "by_kind": {k: sum(1 for m in todo if m.via.startswith(k[:5])) for k in kinds}})
    report = backfill.run(ledger, house_ask(), since, kinds, limit=args.limit)
    return _emit({"since": since, **report, "ledger": ledger.counts()}, 1 if report["errors"] and not report["events"] else 0)


def _add_event(args: Any) -> int:
    from algent_backend.geoledger import ingest
    from algent_backend.geoledger.store import Ledger

    try:
        e = ingest.add_event(Ledger(), args.asset_id, status=args.status, claimant=args.claimant, occurred_on=args.date,
                             sources=args.source, confidence=args.confidence, note=args.note)
    except ValueError as exc:
        return _emit({"error": str(exc)}, 1)
    return _emit({"recorded": e.model_dump()})


def _find(args: Any) -> int:
    from algent_backend.geoledger import alias, match
    from algent_backend.geoledger.store import Ledger

    ledger = Ledger()
    hit = alias.find(ledger, [args.name], type_=args.type, country=args.country.upper())
    words = {w for w in match.tokens(args.name)[0]}
    near = ledger.candidates(words, args.country.upper())
    scored = sorted(((max(match.name_score(args.name, m) for m in (a.name, *a.aliases)), a) for a in near), key=lambda t: -t[0])[:8]
    return _emit({"match": hit.asset.model_dump() if hit.asset else None, "reason": hit.reason, "score": round(hit.score, 3),
                  "similar": [{"score": round(s, 3), "id": a.id, "name": a.name, "type": a.type, "country": a.country} for s, a in scored]})


def _show(args: Any) -> int:
    from algent_backend.geoledger.store import Ledger

    ledger = Ledger()
    a = ledger.assets.get(args.asset_id)
    if a is None:
        return _emit({"error": f"unknown asset {args.asset_id!r}"}, 1)
    return _emit({"asset": a.model_dump(), "status": (ledger.status(a.id).model_dump() if ledger.status(a.id) else None),
                  "history": [e.model_dump() for e in ledger.history(a.id)]})


def _publish(args: Any) -> int:
    from algent_backend.geoledger import publish

    from algent_backend.geoledger import grid

    return _emit({**publish.publish(full=args.full), "grid": grid.publish_rollups()})


def _merge(args: Any) -> int:
    from algent_backend.geoledger.store import Ledger

    try:
        return _emit({"merged": Ledger().merge(args.dup, args.into, note=args.note)})
    except ValueError as exc:
        return _emit({"error": str(exc)}, 1)


def _grid(args: Any) -> int:
    from algent_backend.geoledger import grid
    from algent_backend.geoledger.store import Ledger

    ledger = Ledger()
    doc = grid.rollup(ledger, args.iso, args.as_of)
    if args.publish:
        doc["published"] = grid.publish_rollups(ledger, as_of=doc["as_of"], isos=[args.iso])
    return _emit(doc)


def _status(_args: Any) -> int:
    from algent_backend.geoledger import store
    from algent_backend.geoledger.store import Ledger

    ledger = Ledger()
    return _emit({"store": str(ledger.base), **ledger.counts(), "lines": store.line_counts(ledger.base),
                  "published_lines": store.load_marker(ledger.base)})
