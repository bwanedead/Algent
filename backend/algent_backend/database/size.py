"""
Database size report and budget verdict (``newsroom db size``, ``newsroom doctor``).

Reads only catalog views: the whole database size, the biggest tables by total relation size (heap + indexes + TOAST) with their dead
tuple ratio (the churn signal: a high ratio means autovacuum is behind), and the WAL directory when the role may list it (Supabase
free usually does not; then ``wal_bytes`` is None). ``judge`` is pure so the thresholds are testable without a database.
"""

from __future__ import annotations

from typing import Any

from . import flags

OK, WARN, FAIL = "ok", "warn", "fail"

_TOP = """
select c.relname, pg_total_relation_size(c.oid), pg_relation_size(c.oid),
       coalesce(s.n_live_tup, 0), coalesce(s.n_dead_tup, 0)
  from pg_class c
  join pg_namespace n on n.oid = c.relnamespace
  left join pg_stat_user_tables s on s.relid = c.oid
 where n.nspname = 'public' and c.relkind = 'r'
 order by 2 desc
 limit %s
"""


_STORAGE = """
select split_part(name, '/', 1) as prefix, coalesce(sum((metadata ->> 'size')::bigint), 0)
  from storage.objects where bucket_id = 'published-assets' group by 1 order by 2 desc
"""


def judge(size_bytes: int, quota_bytes: int | None = None) -> dict[str, Any]:
    """``{status, share, size_bytes, quota_bytes}``: warn at ``WARN_SHARE`` of the quota, fail at ``FAIL_SHARE``."""
    quota = quota_bytes or flags.QUOTA_BYTES
    share = size_bytes / quota if quota else 0.0
    status = FAIL if share >= flags.FAIL_SHARE else WARN if share >= flags.WARN_SHARE else OK
    return {"status": status, "share": round(share, 4), "size_bytes": int(size_bytes), "quota_bytes": int(quota)}


def dead_ratio(live: int, dead: int) -> float:
    return round(dead / (live + dead), 3) if live + dead else 0.0


def report(conn: Any, *, top: int = 12) -> dict[str, Any]:
    """The full picture on an open connection."""
    with conn.cursor() as cur:
        cur.execute("select pg_database_size(current_database())")
        size = int(cur.fetchone()[0])
        cur.execute(_TOP, (top,))
        tables = [{"table": name, "total_bytes": int(total), "heap_bytes": int(heap), "live_rows": int(live), "dead_rows": int(dead),
                   "dead_ratio": dead_ratio(int(live), int(dead))} for name, total, heap, live, dead in cur.fetchall()]
    return {**judge(size), "tables": tables, "wal_bytes": wal_bytes(conn), "storage": storage_usage(conn)}


def storage_usage(conn: Any) -> dict[str, Any] | None:
    """Bytes in the ``published-assets`` bucket by top-level prefix (docs/, live/, analytics/ ...) against the plan's Storage quota;
    None when the role cannot read ``storage.objects``."""
    try:
        with conn.cursor() as cur:
            cur.execute(_STORAGE)
            by = {str(p): int(n) for p, n in cur.fetchall()}
    except Exception:  # noqa: BLE001
        try:
            conn.rollback()
        except Exception:  # noqa: BLE001
            pass
        return None
    return {**judge(sum(by.values()), flags.STORAGE_QUOTA_BYTES), "by_prefix": by}


def wal_bytes(conn: Any) -> int | None:
    """Total size of the WAL directory, or None when this role may not list it (or the server is too old)."""
    try:
        with conn.cursor() as cur:
            cur.execute("select coalesce(sum(size), 0) from pg_ls_waldir()")
            return int(cur.fetchone()[0])
    except Exception:  # noqa: BLE001 - permission denied is the normal answer on a managed plan
        try:
            conn.rollback()
        except Exception:  # noqa: BLE001
            pass
        return None


def human(n: int | None) -> str:
    if n is None:
        return "unknown"
    return f"{n / 1048576:.1f} MB"


def summary_line(rep: dict[str, Any]) -> str:
    head = f"{human(rep['size_bytes'])} of {human(rep['quota_bytes'])} ({rep['share'] * 100:.0f}%)"
    big = rep["tables"][0] if rep.get("tables") else None
    return head + (f"; biggest: {big['table']} {human(big['total_bytes'])}" if big else "")
