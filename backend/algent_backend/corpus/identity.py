"""
Who is who: which declarations are one real thing, and which entity a bare name means. Pure functions (no SQL), driven by the tables in ``flags.py``.

Two rules, both deterministic and both data-driven, replace what used to be reported as "ambiguous":

* **Precedence** (``resolution``): when a normalised name answers to several entities, the lowest ``KIND_TIER`` wins. "France" is the country, not a place of
  the same name; a typed entity beats an untyped speaker (``actor``); a free-text ``topic`` counts only when nothing real answers. What is left after
  that (two entities of one tier and different kinds, like a person and a place) is genuinely ambiguous and stays reported, never guessed.
* **Merging** (``merge_map``): sources declare one real thing under several ids ("Houthis" and "Houthi movement" from two profiles, the
  chokepoint a profile calls a place and the instruments call another). Two declarations of one family are one entity when the *name* of one is a name
  or alias of the other; an untyped speaker folds into the one typed entity that answers to its name (the speaker canonical map meeting the profiles).
  The lowest-ranked declaration names the merged entity and its id is the canonical one; the other ids stay resolvable (``entity_merge``).
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field

from . import flags
from .norm import norm


def tier(kind: str) -> int:
    return flags.KIND_TIER.get(kind, flags.KIND_TIER_DEFAULT)


@dataclass
class Ent:
    """What every source declared about one id, reduced to what identity needs."""

    id: str
    kind: str
    rank: int                                  # the best (lowest) rank any source gave it
    primary: str                               # normalised name given by the winning declaration
    names: set[str] = field(default_factory=set)   # every normalised name and alias, primary included


def ents_from_decl(rows: list[sqlite3.Row]) -> dict[str, Ent]:
    """One ``Ent`` per declared id. The winning declaration (lowest rank, then origin) fixes kind and primary name, exactly as ``materialise`` does."""
    out: dict[str, Ent] = {}
    for r in sorted(rows, key=lambda r: (r["entity_id"], r["rank"], r["origin"])):
        e = out.get(r["entity_id"])
        if e is None:
            e = out[r["entity_id"]] = Ent(r["entity_id"], r["kind"], r["rank"], norm(r["name"]))
        e.names.update(n for n in (norm(r["name"]), *map(norm, json.loads(r["aliases"]))) if n)
    return out


class _Union:
    def __init__(self) -> None:
        self.parent: dict[str, str] = {}

    def find(self, x: str) -> str:
        self.parent.setdefault(x, x)
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def join(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[max(ra, rb)] = min(ra, rb)         # the smaller id roots the set, so the outcome never depends on visit order


def _mergeable(e: Ent) -> bool:
    return e.kind in flags.MERGE_FAMILY and not e.id.startswith(flags.MERGE_EXEMPT_PREFIXES)


def merge_map(ents: dict[str, Ent]) -> dict[str, str]:
    """``{old id: canonical id}`` for every id that is the same real thing as a better-ranked one (canonical ids are not keys)."""
    by_name: dict[tuple[str, str], set[str]] = {}
    for e in ents.values():
        if _mergeable(e):
            for n in e.names:
                by_name.setdefault((flags.MERGE_FAMILY[e.kind], n), set()).add(e.id)
    sets = _Union()
    for e in ents.values():                                                 # a name of one is a name of the other
        if _mergeable(e):
            for other in by_name.get((flags.MERGE_FAMILY[e.kind], e.primary), ()):
                sets.join(e.id, other)
    typed: dict[str, set[str]] = {}                                         # normalised name -> typed entities answering to it (their set roots)
    for e in ents.values():
        if e.kind not in ("actor", "topic") and not e.id.startswith(flags.MERGE_EXEMPT_PREFIXES):
            for n in e.names:
                typed.setdefault(n, set()).add(sets.find(e.id))
    for e in ents.values():                                                 # an untyped speaker folds into the one typed entity of its name
        if e.kind == "actor" and not e.id.startswith(flags.MERGE_EXEMPT_PREFIXES):
            roots = typed.get(e.primary, set())
            if len(roots) == 1:
                sets.join(e.id, next(iter(roots)))
    clusters: dict[str, list[Ent]] = {}
    for e in ents.values():
        clusters.setdefault(sets.find(e.id), []).append(e)
    out: dict[str, str] = {}
    for members in clusters.values():
        if len(members) > 1:
            canon = min(members, key=lambda m: (m.rank, m.id)).id
            out.update({m.id: canon for m in members if m.id != canon})
    return out


def merge_is_monotone(old: dict[str, str], new: dict[str, str]) -> bool:
    """Whether ``new`` only ever joins what ``old`` already joined. Rows rewritten under ``old`` can be carried forward by ``new`` exactly then; a
    split (a revised profile no longer shares a name) cannot be undone in place, so the build starts over."""
    return all(new.get(canon, canon) == new.get(k, k) for k, canon in old.items())


def resolution(db: sqlite3.Connection) -> dict[str, tuple[str | None, int]]:
    """``{normalised name: (the one entity it means or None, how many entities of the best tier answer to it)}``."""
    best: dict[str, tuple[int, set[str]]] = {}
    for r in db.execute("SELECT a.norm, e.id, e.kind FROM entity_alias a JOIN entities e ON e.id = a.entity_id"):
        t = tier(r["kind"])
        cur = best.get(r["norm"])
        if cur is None or t < cur[0]:
            best[r["norm"]] = (t, {r["id"]})
        elif t == cur[0]:
            cur[1].add(r["id"])
    return {n: (next(iter(ids)) if len(ids) == 1 else None, len(ids)) for n, (_, ids) in best.items()}
