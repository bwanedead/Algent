"""
The link pass: runs once at the end of every build, over the whole index, so its result is a function of the final content and not of the order
sources were read in (that is what makes "rebuild equals incremental" hold).

1. ``materialise``  builds ``entities`` and ``entity_alias`` from ``entity_decl``. Declarations of one real thing under several ids are merged first
   (``identity.merge_map``); the lowest rank names the merged entity (a country registry beats a story's mention), ties broken by origin;
   aliases are the union of every declaration's names.
2. ``remap``        rewrites ids the sources asserted so that every row points at the canonical entity (``entity_merge`` keeps old id -> canonical).
3. ``link``         resolves each text-only name (mention, relation end, event actor, event place) against the alias table. A name resolves to the one
   entity of the best kind tier that answers to it (``identity.resolution``). A name nothing answers to, or several equals do, stays unresolved
   and is reported, never guessed.
4. ``collect``      drops sources no claim cites any more.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from . import identity
from .norm import norm


def materialise(db: sqlite3.Connection) -> tuple[int, dict[str, str]]:
    """Fill ``entities`` / ``entity_alias``; returns (entity count, the merge map ``{old id: canonical id}``)."""
    rows = db.execute("SELECT * FROM entity_decl").fetchall()
    merge = identity.merge_map(identity.ents_from_decl(rows))
    groups: dict[str, list[sqlite3.Row]] = {}
    for r in rows:
        groups.setdefault(merge.get(r["entity_id"], r["entity_id"]), []).append(r)
    db.execute("DELETE FROM entities")
    db.execute("DELETE FROM entity_alias")
    out: list[tuple] = []
    aliases: dict[tuple[str, str], str] = {}
    for eid in sorted(groups):
        group = sorted(groups[eid], key=lambda d: (d["rank"], d["origin"], d["entity_id"]))
        win = group[0]
        names: dict[str, str] = {}
        for d in group:
            for a in (d["name"], *json.loads(d["aliases"])):
                names.setdefault(norm(a), a)
        attrs: dict[str, Any] = {}
        for d in reversed(group):                               # the winner's keys go on last, so they win
            attrs.update(json.loads(d["attrs"]))
        pick = lambda col: next((d[col] for d in group if d[col] is not None), None)  # noqa: E731 - first non-null by rank
        listed = sorted(a for n, a in names.items() if n != norm(win["name"]))
        out.append((eid, win["kind"], win["name"], json.dumps(listed, ensure_ascii=False), pick("iso2"), pick("lat"), pick("lon"),
                    json.dumps(attrs, ensure_ascii=False, sort_keys=True), win["product"], win["origin"], win["ingested_at"]))
        for n, a in names.items():
            if n:
                aliases[(n, eid)] = a
    db.executemany("INSERT INTO entities VALUES (?,?,?,?,?,?,?,?,?,?,?)", out)
    db.executemany("INSERT INTO entity_alias VALUES (?,?,?)", [(n, e, a) for (n, e), a in aliases.items()])
    return len(out), merge


#: (table, id column) for every place a source can assert an entity id; remapped to the canonical id after a merge.
_ASSERTED = (("mentions", "entity_id"), ("relations", "src_id"), ("relations", "dst_id"), ("event_actors", "entity_id"), ("events", "place_id"),
             ("observations", "entity_id"))


def store_merge(db: sqlite3.Connection, merge: dict[str, str]) -> bool:
    """Persist the merge map and rewrite asserted ids to canonical. Returns False when the new map splits something the old one joined: rows already
    rewritten cannot be un-merged in place, so the caller rebuilds from nothing."""
    old = {r[0]: r[1] for r in db.execute("SELECT old_id, canon_id FROM entity_merge")}
    db.execute("DELETE FROM entity_merge")
    db.executemany("INSERT INTO entity_merge VALUES (?,?)", sorted(merge.items()))
    for table, col in _ASSERTED:
        db.execute(f"UPDATE {table} SET {col} = (SELECT canon_id FROM entity_merge WHERE old_id = {table}.{col}) "      # noqa: S608
                   f"WHERE {col} IN (SELECT old_id FROM entity_merge)")
    return identity.merge_is_monotone(old, merge)


#: (table, text column, id column, asserted column) for every place a name can wait to be resolved.
_TARGETS = (
    ("mentions", "surface_norm", "entity_id", "asserted"),
    ("relations", "src_norm", "src_id", "src_asserted"),
    ("relations", "dst_norm", "dst_id", "dst_asserted"),
    ("event_actors", "surface_norm", "entity_id", "asserted"),
    ("events", "place_norm", "place_id", "place_asserted"),
)


def link(db: sqlite3.Connection) -> None:
    db.execute("CREATE TEMP TABLE IF NOT EXISTS alias_unique (norm TEXT, entity_id TEXT)")
    db.execute("DELETE FROM alias_unique")
    db.executemany("INSERT INTO alias_unique VALUES (?,?)", [(n, eid) for n, (eid, _) in identity.resolution(db).items() if eid])
    db.execute("CREATE UNIQUE INDEX IF NOT EXISTS temp.ix_alias_unique ON alias_unique(norm)")
    for table, text, ident, asserted in _TARGETS:
        db.execute(f"UPDATE {table} SET {ident} = NULL WHERE {asserted} = 0")                                  # noqa: S608
        db.execute(f"UPDATE {table} SET {ident} = (SELECT entity_id FROM alias_unique a WHERE a.norm = {table}.{text}) "   # noqa: S608
                   f"WHERE {asserted} = 0 AND {text} != ''")


def collect(db: sqlite3.Connection) -> None:
    db.execute("DELETE FROM sources WHERE url NOT IN (SELECT url FROM claim_sources)")


def finish(db: sqlite3.Connection) -> tuple[int, bool]:
    """The whole pass; returns (entity count, whether the merge map stayed monotone). False means the index must be rebuilt from nothing."""
    n, merge = materialise(db)
    monotone = store_merge(db, merge)
    link(db)
    collect(db)
    return n, monotone


def unresolved(db: sqlite3.Connection, *, limit: int = 100) -> list[dict[str, Any]]:
    """Names the index could not tie to one entity, most frequent first: ``reason`` is ``unknown`` (nothing answers to it) or ``ambiguous``
    (several entities of the best tier do)."""
    parts = [
        "SELECT surface_norm AS n, surface AS s, 'mention' AS w FROM mentions WHERE entity_id IS NULL AND surface_norm != ''",
        "SELECT src_norm, src_surface, 'relation' FROM relations WHERE src_id IS NULL AND src_norm != ''",
        "SELECT dst_norm, dst_surface, 'relation' FROM relations WHERE dst_id IS NULL AND dst_norm != ''",
        "SELECT surface_norm, surface, 'event actor' FROM event_actors WHERE entity_id IS NULL AND surface_norm != ''",
        "SELECT place_norm, place, 'event place' FROM events WHERE place_id IS NULL AND place_norm != ''",
    ]
    sql = ("SELECT n, MIN(s) AS name, COUNT(*) AS uses, group_concat(DISTINCT w) AS seen_in "
           f"FROM ({' UNION ALL '.join(parts)}) u GROUP BY n ORDER BY uses DESC, n LIMIT ?")
    known = identity.resolution(db)
    return [{"name": r["name"], "uses": r["uses"], "seen_in": r["seen_in"], "reason": "ambiguous" if known.get(r["n"], (None, 0))[1] > 1 else "unknown"}
            for r in db.execute(sql, (limit,))]


def unresolved_count(db: sqlite3.Connection) -> int:
    """How many distinct names are unresolved (the figure ``stats`` prints)."""
    return len(unresolved(db, limit=10**9))
