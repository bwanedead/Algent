"""
The one-shot recovery/diet pass (``newsroom db diet``) — docs/architecture/database-budget.md, "Recovery runbook".

  1. every ``published_intel_documents`` row that still holds its body inline is uploaded to Storage as ``docs/<path>.gz`` and its row is
     reduced to the index fields (body nulled): the big JSONB leaves Postgres, the path stays the same so nothing else changes;
  2. the retention prune (``prune.run``) removes what the windows no longer keep;
  3. ``VACUUM (ANALYZE)`` on the tables that shrank, so the freed pages are reusable (a ``VACUUM FULL`` to return them to the disk is the
     separate, explicit ``db vacuum-full`` step).

Idempotent: a row already in Storage is skipped, a re-run after a crash continues where it stopped, and it is safe to run while the
writers are paused or live. A document is nulled only AFTER its upload succeeded. Dry run (the default) changes nothing and prints what
it would do. The database must be writable (``set session characteristics as transaction read write;`` after Supabase support lifts the
read-only flag).
"""

from __future__ import annotations

from typing import Any, Callable

from algent_backend.publishing import asset_store, doc_store

from . import prune

_LEGACY = "select path, pg_column_size(body) from published_intel_documents where body is not null and storage_key is null order by path"
_BODY = "select body from published_intel_documents where path = %s"
_MOVED = """
update published_intel_documents
   set body = null, storage_key = %s, size_bytes = %s, sha256 = %s
 where path = %s and storage_key is null
"""


def legacy_documents(conn: Any) -> list[tuple[str, int]]:
    """(path, bytes the inline body occupies) for every document still stored in Postgres."""
    with conn.cursor() as cur:
        cur.execute(_LEGACY)
        return [(r[0], int(r[1] or 0)) for r in cur.fetchall()]


def move_documents(conn: Any, *, apply: bool, http: Callable[..., int] | None = None) -> dict[str, Any]:
    """Step 1. Returns counts and the paths that could not move (over the object cap, or an upload that failed)."""
    legacy = legacy_documents(conn)
    out: dict[str, Any] = {"inline_documents": len(legacy), "inline_bytes": sum(b for _p, b in legacy), "moved": 0, "left": []}
    if not apply:
        return out
    if http is None and not asset_store.enabled():
        raise RuntimeError("Storage is not configured: set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY (the diet uploads before it deletes)")
    for path, _bytes in legacy:
        with conn.cursor() as cur:
            cur.execute(_BODY, (path,))
            row = cur.fetchone()
        if row is None or row[0] is None:
            continue
        packed = doc_store.pack(path, row[0])
        if (why := doc_store.over_cap(packed)):
            out["left"].append(why)
            continue
        res = asset_store.upload({packed.site_path: packed.gz}, http=http, force=True, cache_control=doc_store.CACHE_CONTROL)
        if not res["ok"]:
            out["left"].append(f"{path}: upload failed {res['failed']}")
            continue
        with conn.cursor() as cur:
            cur.execute(_MOVED, (packed.key, packed.size_bytes, packed.sha256, path))
        conn.commit()                                   # one document per transaction: a crash loses nothing already moved
        out["moved"] += 1
    return out


def run(conn: Any, *, apply: bool = False, http: Callable[..., int] | None = None) -> dict[str, Any]:
    """The whole diet: move bodies, prune, vacuum. ``apply=False`` reports only."""
    moved = move_documents(conn, apply=apply, http=http)
    pruned = prune.run(conn, apply=apply, do_vacuum=False)
    out: dict[str, Any] = {"applied": apply, "documents": moved, "prune": pruned}
    if apply:
        tables = ["published_intel_documents", *[r["table"] for r in pruned["removed"] if r["deleted"]]]
        out["vacuumed"] = prune.vacuum(conn, tables)
    return out


def vacuum_full_plan(conn: Any, *, min_bytes: int = 5 * 1024 * 1024) -> list[dict[str, Any]]:
    """Tables worth a ``VACUUM FULL`` (they hold dead space), SMALLEST first: a full vacuum needs room to write the compact copy, so the
    small wins run first and each one frees room for the next. A table qualifies when it is over ``min_bytes`` and a tenth of its
    rows is dead, or when it is a document-index table that just had its bodies moved out."""
    from . import size

    rep = size.report(conn, top=60)
    chosen = [t for t in rep["tables"] if t["total_bytes"] >= min_bytes and (t["dead_ratio"] >= 0.1 or t["table"] == "published_intel_documents")]
    return sorted(chosen, key=lambda t: t["total_bytes"])


def vacuum_full(conn: Any, *, apply: bool = False) -> dict[str, Any]:
    """Step (d) of the runbook: rewrite the bloated tables, smallest first; before each, the table plus the database must fit in the quota (its compact copy is
    written beside it)."""
    from . import size

    todo = vacuum_full_plan(conn)
    if not apply:
        return {"applied": False, "tables": [t["table"] for t in todo], "sizes": {t["table"]: t["total_bytes"] for t in todo}}
    done, stopped = [], ""
    for t in todo:
        now = size.report(conn, top=1)
        if now["size_bytes"] + t["total_bytes"] > now["quota_bytes"]:       # worst case the compact copy is as big as the table
            stopped = f"{t['table']} ({size.human(t['total_bytes'])}) would not fit beside the database ({size.human(now['size_bytes'])}): stopped; free space first"
            break
        done += prune.vacuum(conn, [t["table"]], full=True)
    return {"applied": True, "vacuumed_full": done, "note": stopped, "after": size.report(conn, top=5)}
