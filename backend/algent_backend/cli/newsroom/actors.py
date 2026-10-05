"""
``newsroom actors`` — Ohmega's power profiles of states: fetch, inspect, compare.

    newsroom actors fetch [--source wb|owid|wikidata|imf ...]
    newsroom actors show <iso2|name>
    newsroom actors compare RU UA DE
    newsroom actors registry [--write]

``fetch`` pulls the free open-licence sources into the append-only store (no model, no paid call).
``show`` prints one actor's profile; ``compare`` lines actors up on shared scales; ``registry`` prints
the country table (``--write`` re-seeds it from the World Bank list). Every command prints one JSON document.
"""

from __future__ import annotations

import json
from typing import Any

from algent_backend.actors import registry, store
from algent_backend.actors.collect import SOURCE_KEYS, collect
from algent_backend.actors.profile import compare, load_corpus, profile
from algent_backend.actors.sources import worldbank


def add_parser(sub: Any) -> None:
    p = sub.add_parser("actors", help="power profiles of states: fetch free open data, show one actor, compare several")
    verbs = p.add_subparsers(dest="actors_cmd", required=True)
    f = verbs.add_parser("fetch", help="pull sources into the store (all, or --source)")
    f.add_argument("--source", action="append", choices=SOURCE_KEYS, help="source (repeatable); default all")
    f.add_argument("--countries", help="comma-separated ISO2 codes whose ranked trade (source wits) is fetched; "
                                       "default the G20 and UN P5")
    f.set_defaults(handler=run_fetch)
    s = verbs.add_parser("show", help="one actor's profile")
    s.add_argument("actor", help="ISO2 code or country name")
    s.set_defaults(handler=run_show)
    c = verbs.add_parser("compare", help="actors side by side on shared scales")
    c.add_argument("actors", nargs="+", help="ISO2 codes or names")
    c.set_defaults(handler=run_compare)
    r = verbs.add_parser("registry", help="the country table")
    r.add_argument("--write", action="store_true", help="re-seed countries.json from the World Bank country list")
    r.set_defaults(handler=run_registry)


def _emit(doc: Any) -> int:
    print(json.dumps(doc, indent=2, ensure_ascii=False))
    return 0


def _iso(text: str) -> str:
    code = registry.resolve(text)
    if code is None:
        raise SystemExit(f"unknown actor {text!r}: not a country name, alias or code (try `newsroom actors registry`)")
    return code


def run_fetch(args: Any) -> int:
    return _emit(collect(args.source, [c.strip().upper() for c in args.countries.split(',')] if args.countries else None))


def run_show(args: Any) -> int:
    doc = profile(_iso(args.actor))
    return _emit({"store": str(store.store_dir()), **doc})


def run_compare(args: Any) -> int:
    return _emit(compare([_iso(a) for a in args.actors], load_corpus()))


def run_registry(args: Any) -> int:
    if args.write:
        rows = registry.build_rows(worldbank.fetch_countries())
        return _emit({"written": str(registry.write_seed(rows)), "countries": len(rows)})
    return _emit({"count": len(registry.load()),
                  "countries": [c.model_dump() for c in registry.load().values()]})
