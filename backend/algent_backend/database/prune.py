"""
Retention for the growing tables (``newsroom db prune``, a free daily timer) — windows live in ``database/flags.py``.

Only tables whose old rows nothing reads and that can be rebuilt (or that are pure archive) are listed here. NEVER pruned, by design:
``published_articles``, the Pulse ledgers and claims, ``geo_*``, ``sanctions_events``, ``calendar_items`` — corpus that cannot be
rebuilt, and small anyway. In doubt, a table is left out.

Deletes run in batches of ``flags.PRUNE_BATCH`` (one commit each: no long lock, no WAL burst on a nearly full disk) and are followed by
``VACUUM (ANALYZE)`` on the tables that lost rows, so the freed pages are reusable at once. ``rules()`` is pure data so the selection
logic is testable without a database.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from . import flags


@dataclass(frozen=True)
class Rule:
    table: str
    where: str            # SQL condition over the table; %(n)s is the window in days (or the number of rows kept)
    arg: int              # the window
    why: str
    #: ``ctid`` for plain tables, or the key column when the selection is a window function (revisions)
    keyed: str = "ctid"
    #: full subselect producing the keys to delete; None means ``select <keyed> from <table> where <where>``
    custom: str | None = None


def rules() -> list[Rule]:
    return [
        Rule("live_events", "not active and updated_at < now() - make_interval(days => %(n)s)", flags.LIVE_EVENTS_ENDED_DAYS,
             "ended events: the site shows active rows only"),
        Rule("live_stats", "not partial and period < current_date - %(n)s::int", flags.LIVE_STATS_DAYS,
             "daily rows older than the year-ago comparison window"),
        Rule("live_anomalies", "not active and coalesce(ends_at, updated_at) < now() - make_interval(days => %(n)s)", flags.LIVE_ANOMALIES_DAYS,
             "closed anomalies past the site's recent-closed window"),
        Rule("maritime_events",
             "(ended_at is not null and ended_at < now() - make_interval(days => %(n)s)) or (not active and updated_at < now() - make_interval(days => %(n)s))",
             flags.MARITIME_EVENTS_DAYS, "ended events past the 30-day picture; the long record is the server's log.jsonl"),
        Rule("radar_sightings", "at < now() - make_interval(days => %(n)s)", flags.RADAR_SIGHTINGS_DAYS,
             "sightings only mean 'new since the last assessment'"),
        Rule("published_article_revisions", "rn > %(n)s", flags.REVISIONS_KEEP, "keep the last few revisions per slug", keyed="id",
             custom="select id from (select id, row_number() over (partition by slug order by id desc) rn "
                    "from published_article_revisions) ranked where rn > %(n)s"),
    ]


def _params(rule: Rule) -> dict[str, int]:
    return {"n": rule.arg}


def _selection(rule: Rule) -> str:
    return rule.custom or f"select {rule.keyed} from {rule.table} where {rule.where}"


def count_sql(rule: Rule) -> str:
    return f"select count(*) from ({_selection(rule)}) doomed"


def delete_sql(rule: Rule) -> str:
    return f"delete from {rule.table} where {rule.keyed} in ({_selection(rule)} limit {int(flags.PRUNE_BATCH)})"


def plan(conn: Any) -> list[dict[str, Any]]:
    """How many rows each rule would delete now (nothing is changed)."""
    out = []
    with conn.cursor() as cur:
        for r in rules():
            cur.execute(count_sql(r), _params(r))
            out.append({"table": r.table, "rows": int(cur.fetchone()[0]), "window": r.arg, "why": r.why})
    conn.rollback()
    return out


def delete_rule(conn: Any, rule: Rule) -> int:
    """Delete everything the rule selects, a batch and a commit at a time. Returns the rows removed."""
    total = 0
    while True:
        with conn.cursor() as cur:
            cur.execute(delete_sql(rule), _params(rule))
            n = int(cur.rowcount or 0)
        conn.commit()
        total += n
        if n < flags.PRUNE_BATCH:
            return total


def vacuum(conn: Any, tables: list[str], *, full: bool = False) -> list[str]:
    """``VACUUM (ANALYZE)`` (or ``FULL``) each table; needs autocommit (VACUUM cannot run in a transaction). Returns the tables done."""
    done = []
    previous = getattr(conn, "autocommit", False)
    conn.autocommit = True
    try:
        for t in tables:
            with conn.cursor() as cur:
                cur.execute(f"vacuum ({'full, ' if full else ''}analyze) {t}")
            done.append(t)
    finally:
        conn.autocommit = previous
    return done


def run(conn: Any, *, apply: bool = False, do_vacuum: bool = True) -> dict[str, Any]:
    """Dry run (default) lists the counts; ``apply`` deletes in batches and vacuums the tables that lost rows."""
    if not apply:
        return {"applied": False, "plan": plan(conn)}
    removed, touched = [], []
    for r in rules():
        n = delete_rule(conn, r)
        removed.append({"table": r.table, "deleted": n, "window": r.arg})
        if n:
            touched.append(r.table)
    return {"applied": True, "removed": removed, "vacuumed": vacuum(conn, touched) if do_vacuum and touched else []}
