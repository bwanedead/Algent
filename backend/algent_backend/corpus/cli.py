"""
Command handlers for ``newsroom corpus build | stats | ask`` (the argparse wiring lives in ``cli/newsroom/corpus.py``; this is the logic, so a server
job or a test can call it without a parser).

    newsroom corpus build [--full] [--since YYYY-MM-DD] [--only a,b]
    newsroom corpus stats
    newsroom corpus ask entity|about|timeline|search|related|series <text> [--since D] [--kinds a,b] [--limit N] [--metric M]
"""

from __future__ import annotations

import json
from typing import Any

from .build import build as _run_build  # the package re-exports the function `build`, which shadows the submodule
from . import flags
from .query import Corpus, CorpusMissing

ASK = ("entity", "about", "timeline", "search", "related", "series")


def run_build(*, full: bool = False, since: str = "", only: str = "", as_json: bool = False) -> int:
    r = _run_build(full=full, since=since, only=[s for s in only.split(",") if s] or None)
    if as_json:
        print(json.dumps(r, indent=2, ensure_ascii=False, default=str))
        return 1 if r["errors"] else 0
    print(f"corpus build ({'full' if r['full'] else 'incremental'}{', since ' + since if since else ''}): {r['seconds']}s, {r['bytes'] / 1e6:.1f} MB at {r['path']}")
    for name, s in r["sources"].items():
        note = "unchanged (watermark)" if s["skipped"] else f"{s['units']} units, {s['changed']} changed, {s['removed']} removed"
        print(f"  {name:<14} {note}  [{s['seconds']}s]")
    print("rows: " + ", ".join(f"{k} {v}" for k, v in r["rows"].items()))
    print(f"unresolved names: {r['unresolved']}")
    for e in r["errors"][:10]:
        print(f"  ERROR {e}")
    return 1 if r["errors"] else 0


def run_stats(*, as_json: bool = False, unresolved: int = 15) -> int:
    try:
        with Corpus.open() as c:
            s = c.stats()
            top = c.unresolved(unresolved)
    except CorpusMissing as exc:
        print(exc)
        return 1
    if as_json:
        print(json.dumps({**s, "top_unresolved": top}, indent=2, ensure_ascii=False, default=str))
        return 0
    print(f"{s['path']}  {s['bytes'] / 1e6:.1f} MB  built {s['built_at']}  search={s['fts']}")
    for t, n in s["rows"].items():
        print(f"  {t:<14}{n:>10}")
    print(f"unresolved names: {s['unresolved']}   dangling asserted ids: {s['dangling_ids']}")
    for kind in ("entities_by_kind", "documents_by_kind", "events_by_kind", "observations_by_basis"):
        print(f"  {kind}: " + ", ".join(f"{k} {v}" for k, v in s[kind].items()))
    if top:
        print("most-used unresolved names:")
        for r in top:
            print(f"  {r['uses']:>4}  {r['reason']:<9} {r['name']}")
    return 0


def _kinds(text: str) -> set[str] | None:
    return {k for k in (text or "").split(",") if k} or None


def ask(verb: str, text: str, *, since: str = "", until: str = "", kinds: str = "", limit: int = 0, metric: str = "") -> Any:
    """Run one query; returns the JSON-able answer (None when the entity is unknown)."""
    n = limit or flags.DEFAULT_LIMIT
    with Corpus.open() as c:
        if verb == "entity":
            return c.entity(text)
        if verb == "about":
            return c.about(text, since=since, until=until, kinds=_kinds(kinds), limit=n)
        if verb == "timeline":
            return c.timeline(text, since=since, until=until, kinds=_kinds(kinds), limit=limit or 50)
        if verb == "search":
            return c.search(text, kinds=_kinds(kinds), since=since, until=until, limit=n)
        if verb == "related":
            return c.related(text, limit=limit or 15, kinds=_kinds(kinds))
        if verb == "series":
            return c.series(text, metric=metric, since=since, until=until, points=False, limit=n)
    raise ValueError(f"unknown query {verb!r}; one of {', '.join(ASK)}")


def run_ask(verb: str, text: str, **kw: Any) -> int:
    try:
        out = ask(verb, text, **kw)
    except CorpusMissing as exc:
        print(exc)
        return 1
    if out is None:
        print(json.dumps({"error": f"no entity matches {text!r}"}))
        return 1
    print(json.dumps(out, indent=2, ensure_ascii=False, default=str))
    return 0
