"""
The link pass: runs once at the end of every build, over the whole index, so its result is a function of the final content and not of the order
sources were read in (that is what makes "rebuild equals incremental" hold).

1. ``materialise``  builds ``entities`` and ``entity_alias`` from ``entity_decl``. When several sources declare one id the lowest rank names it
   (a country registry beats a story's mention), ties broken by origin; aliases are the union of every declaration's names.
2. ``link``         resolves each text-only name (mention, relation end, event actor, event place) against the alias table. A name resolves only
   when exactly one entity answers to it. A name nothing answers to, or several do, stays unresolved and is reported, never guessed.
3. ``collect``      drops sources no claim cites any more.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from .norm import norm


def materialise(db: sqlite3.Connection) -> int:
    rows = db.execute("SELECT * FROM entity_decl ORDER BY entity_id, rank, origin").fetchall()
    db.execute("DELETE FROM entities")
    db.execute("DELETE FROM entity_alias")
    out: list[tuple] = []
    aliases: dict[tuple[str, str], str] = {}
    i = 0
    while i < len(rows):
        j = i
        while j < len(rows) and rows[j]["entity_id"] == rows[i]["entity_id"]:
            j += 1
        group = rows[i:j]
        win = group[0]
        names: dict[str, str] = {}
        for d in group:
            for a in (d["name"], *json.loads(d["aliases"])):
                names.setdefault(norm(a), a)
        attrs: dict[str, Any] = {}
        for d in reversed(group):                               # the winner's keys go on last, so they win
            attrs.update(json.loads(d["attrs"]))
        pick = lambda col: next((d[col] for d in group if d[col] is not None), None)  # noqa: E731 - first non-null by rank
        eid = win["entity_id"]
        listed = sorted(a for n, a in names.items() if n != norm(win["name"]))
        out.append((eid, win["kind"], win["name"], json.dumps(listed, ensure_ascii=False), pick("iso2"), pick("lat"), pick("lon"),
                    json.dumps(attrs, ensure_ascii=False, sort_keys=True), win["product"], win["origin"], win["ingested_at"]))
        for n, a in names.items():
            if n:
                aliases[(n, eid)] = a
        i = j
    db.executemany("INSERT INTO entities VALUES (?,?,?,?,?,?,?,?,?,?,?)", out)
    db.executemany("INSERT INTO entity_alias VALUES (?,?,?)", [(n, e, a) for (n, e), a in aliases.items()])
    return len(out)


#: (table, text column, normalised column, id column, asserted column, extra WHERE) for every place a name can wait to be resolved.
_TARGETS = (
    ("mentions", "surface_norm", "entity_id", "asserted"),
    ("relations", "src_norm", "src_id", "src_asserted"),
    ("relations", "dst_norm", "dst_id", "dst_asserted"),
    ("event_actors", "surface_norm", "entity_id", "asserted"),
    ("events", "place_norm", "place_id", "place_asserted"),
)


#: A name resolves to the one entity answering to it, where a ``topic`` (a free-text tag) only counts when no real entity answers: "Russia" the
#: tag never competes with Russia the country.
_UNIQUE = ("WITH x AS (SELECT a.norm, a.entity_id, (e.kind = 'topic') AS t FROM entity_alias a JOIN entities e ON e.id = a.entity_id), "
           "m AS (SELECT norm, MIN(t) AS t FROM x GROUP BY norm) "
           "INSERT INTO alias_unique SELECT x.norm, MIN(x.entity_id) FROM x JOIN m ON m.norm = x.norm AND m.t = x.t GROUP BY x.norm "
           "HAVING COUNT(DISTINCT x.entity_id) = 1")
_CANDIDATES = ("(SELECT COUNT(DISTINCT a.entity_id) FROM entity_alias a JOIN entities e ON e.id = a.entity_id WHERE a.norm = u.n AND (e.kind != 'topic' OR NOT EXISTS "
               "(SELECT 1 FROM entity_alias a2 JOIN entities e2 ON e2.id = a2.entity_id WHERE a2.norm = u.n AND e2.kind != 'topic')))")


def link(db: sqlite3.Connection) -> None:
    db.execute("CREATE TEMP TABLE IF NOT EXISTS alias_unique AS SELECT norm, entity_id FROM entity_alias WHERE 0")
    db.execute("DELETE FROM alias_unique")
    db.execute(_UNIQUE)
    db.execute("CREATE UNIQUE INDEX IF NOT EXISTS temp.ix_alias_unique ON alias_unique(norm)")
    for table, text, ident, asserted in _TARGETS:
        db.execute(f"UPDATE {table} SET {ident} = NULL WHERE {asserted} = 0")                                  # noqa: S608
        db.execute(f"UPDATE {table} SET {ident} = (SELECT entity_id FROM alias_unique a WHERE a.norm = {table}.{text}) "   # noqa: S608
                   f"WHERE {asserted} = 0 AND {text} != ''")


def collect(db: sqlite3.Connection) -> None:
    db.execute("DELETE FROM sources WHERE url NOT IN (SELECT url FROM claim_sources)")


def finish(db: sqlite3.Connection) -> int:
    n = materialise(db)
    link(db)
    collect(db)
    return n


def unresolved(db: sqlite3.Connection, *, limit: int = 100) -> list[dict[str, Any]]:
    """Names the index could not tie to one entity, most frequent first: ``reason`` is ``unknown`` (nothing answers to it) or ``ambiguous``."""
    parts = [
        "SELECT surface_norm AS n, surface AS s, 'mention' AS w FROM mentions WHERE entity_id IS NULL AND surface_norm != ''",
        "SELECT src_norm, src_surface, 'relation' FROM relations WHERE src_id IS NULL AND src_norm != ''",
        "SELECT dst_norm, dst_surface, 'relation' FROM relations WHERE dst_id IS NULL AND dst_norm != ''",
        "SELECT surface_norm, surface, 'event actor' FROM event_actors WHERE entity_id IS NULL AND surface_norm != ''",
        "SELECT place_norm, place, 'event place' FROM events WHERE place_id IS NULL AND place_norm != ''",
    ]
    sql = ("SELECT n, MIN(s) AS name, COUNT(*) AS uses, group_concat(DISTINCT w) AS seen_in, "
           f"{_CANDIDATES} AS candidates "
           f"FROM ({' UNION ALL '.join(parts)}) u GROUP BY n ORDER BY uses DESC, n LIMIT ?")
    return [{"name": r["name"], "uses": r["uses"], "seen_in": r["seen_in"], "reason": "ambiguous" if r["candidates"] > 1 else "unknown"}
            for r in db.execute(sql, (limit,))]


def unresolved_count(db: sqlite3.Connection) -> int:
    """How many distinct names are unresolved (the figure ``stats`` prints)."""
    return len(unresolved(db, limit=10**9))
