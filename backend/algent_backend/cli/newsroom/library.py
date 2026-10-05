"""
``newsroom library`` — Ohmega's own source index: crawl the registry, search it, check its health.

    newsroom library crawl [--source ID ...] [--max N] [--per-source N]
    newsroom library search "<query>" [--days N] [--kind KIND ...] [--limit N]
    newsroom library stats

``crawl`` polls the registry's feeds and reads new pages (free, bounded, robots-aware; no model, no paid
call). ``search`` queries the index. ``stats`` shows documents per source, newest per source, failing
feeds and pages, and the db size against its budget. Every command prints one JSON document.
"""

from __future__ import annotations

import json
from typing import Any

from algent_backend.library import store
from algent_backend.library.crawl import DEFAULT_MAX_TOTAL, DEFAULT_PER_SOURCE, crawl
from algent_backend.library.search import search as library_search
from algent_backend.library.sources import by_id


def add_parser(sub: Any) -> None:
    p = sub.add_parser("library", help="source library: crawl trusted feeds into a local search index, search it")
    verbs = p.add_subparsers(dest="library_cmd", required=True)
    c = verbs.add_parser("crawl", help="poll feeds and index new pages (bounded per run)")
    c.add_argument("--source", action="append", help="source id (repeatable); default all")
    c.add_argument("--max", type=int, default=DEFAULT_MAX_TOTAL, help=f"page reads this run, all sources (default {DEFAULT_MAX_TOTAL})")
    c.add_argument("--per-source", type=int, default=DEFAULT_PER_SOURCE, help=f"page reads per source (default {DEFAULT_PER_SOURCE})")
    c.set_defaults(handler=run_crawl)
    s = verbs.add_parser("search", help="search the index")
    s.add_argument("query")
    s.add_argument("--days", type=int, help="only pages published in the last N days")
    s.add_argument("--kind", action="append", help="restrict to a source kind (repeatable), e.g. government")
    s.add_argument("--limit", type=int, default=10)
    s.set_defaults(handler=run_search)
    t = verbs.add_parser("stats", help="documents per source, failures, db size")
    t.set_defaults(handler=run_stats)


def _emit(doc: Any) -> int:
    print(json.dumps(doc, indent=2, ensure_ascii=False))
    return 0


def run_crawl(args: Any) -> int:
    for sid in args.source or []:
        if by_id(sid) is None:
            raise SystemExit(f"unknown source id: {sid}")        # fail fast, before any request
    return _emit(crawl(args.source, max_total=args.max, per_source=args.per_source))


def run_search(args: Any) -> int:
    hits = library_search(args.query, days=args.days, kinds=args.kind, limit=args.limit)
    return _emit({"query": args.query, "store": str(store.db_path()), "count": len(hits), "results": hits})


def run_stats(args: Any) -> int:
    conn = store.connect(create=False)
    if conn is None:
        return _emit({"store": str(store.db_path()), "documents": 0, "note": "no library yet: run `newsroom library crawl`"})
    try:
        return _emit(store.stats(conn))
    finally:
        conn.close()
