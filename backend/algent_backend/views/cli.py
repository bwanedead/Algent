"""
Command handlers for ``newsroom views build | stats | show`` (the argparse wiring is in ``cli/newsroom/views.py``).

    newsroom views build [--only a,b] [--dry-run] [--json]    build the views, store them in views_store/ and send the changed ones to the bucket
    newsroom views stats [--json]                             what the local store holds: per family count, bytes, largest, and the R2 guard's month so far
    newsroom views show <key>                                 print one stored view (e.g. country/FR, entity/org/nato)
"""

from __future__ import annotations

import json
from typing import Any

from . import build, flags, publish
from .context import open_context


def run_build(*, only: str = "", dry_run: bool = False, as_json: bool = False) -> int:
    names = [n for n in only.split(",") if n] or None
    needs_corpus = names is None or any(n in names for n in ("country", "entity", "series", "search-index"))
    ctx = open_context(with_corpus=needs_corpus)
    try:
        res = build.build_all(ctx, names)
    finally:
        if ctx.corpus is not None:
            ctx.corpus.close()
    views = res.ok_views()
    out = publish.publish(views, dry_run=dry_run, complete=names is None and not res.errors)
    report = {"families": sorted({v.family for v in views}), "views": len(views), "seconds": res.seconds, "errors": res.errors, "over_budget": res.over_budget, "publish": out}
    if as_json:
        print(json.dumps(report, indent=2, ensure_ascii=False, default=str))
    else:
        print(f"views build{' (dry run)' if dry_run else ''}: {len(views)} views, {out.get('bytes', 0) / 1e6:.2f} MB, " + ", ".join(f"{k} {v}s" for k, v in res.seconds.items()))
        up = out.get("upload") or out
        print("  upload: " + ", ".join(f"{k} {v}" for k, v in up.items() if k in ("documents", "unchanged", "would_upload", "bytes_gz", "of", "ok", "note")))
        if "store" in out:
            print("  store: " + ", ".join(f"{k} {v}" for k, v in out["store"].items()))
        for e in res.errors:
            print(f"  ERROR {e}")
    return 1 if res.errors else 0


def stats() -> dict[str, Any]:
    root = publish.store_dir()
    fams: dict[str, dict[str, Any]] = {}
    for f in sorted(root.rglob("*.json")) if root.is_dir() else []:
        rel = f.relative_to(root).as_posix()
        if rel == publish.STATE_FILE:
            continue
        fam = rel.split("/", 1)[0] if "/" in rel else rel.removesuffix(".json")
        d = fams.setdefault(fam, {"count": 0, "bytes": 0, "largest": {"key": "", "bytes": 0}})
        n = f.stat().st_size
        d["count"] += 1
        d["bytes"] += n
        if n > d["largest"]["bytes"]:
            d["largest"] = {"key": rel.removesuffix(".json"), "bytes": n}
    guard: dict[str, Any] = {}
    try:
        from algent_backend.publishing.object_budget import meter

        guard = meter().status()
    except Exception as exc:  # noqa: BLE001
        guard = {"note": f"R2 guard unavailable: {exc}"}
    return {"store": str(root), "families": fams, "budgets": flags.BUDGET_BYTES, "r2": guard}


def run_stats(*, as_json: bool = False) -> int:
    s = stats()
    if as_json:
        print(json.dumps(s, indent=2, ensure_ascii=False, default=str))
        return 0
    print(f"{s['store']}")
    for name, d in s["families"].items():
        print(f"  {name:<14}{d['count']:>7} views {d['bytes'] / 1e6:>8.2f} MB   largest {d['largest']['key']} ({d['largest']['bytes'] / 1e3:.0f} KB)")
    usage = (s["r2"] or {}).get("usage")
    if usage:
        print("  R2 this month: " + ", ".join(f"{k} {v['used']:,} ({v['share']:.1%})" for k, v in usage.items()))
    return 0


def run_show(key: str) -> int:
    f = publish.store_dir() / f"{key.removesuffix('.json')}.json"
    if not f.is_file():
        print(json.dumps({"error": f"no stored view {key!r}"}))
        return 1
    print(json.dumps(json.loads(f.read_text(encoding="utf-8")), indent=2, ensure_ascii=False))
    return 0
