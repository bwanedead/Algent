"""
Theater lineage — a theater can BRANCH from another and two theaters can MERGE, and neither forgets.

The clustering model decides meaning (is this a distinct dynamic that grew out of a tracked one? are these two
tracked theaters really one?); this module is the mechanics around that decision (harness-ethos): validate the
ids the model named, move future clustering to the survivor, and write the lineage into the registry. Nothing is
ever deleted: a merged theater stays in the registry with ``merged_into`` and is simply no longer clustered into.

REGISTRY SHAPE (``intel_store/theaters.json``, all fields optional)
    parent_id    a branch names the theater it grew out of (set once, at creation)
    merged_into  the survivor, on a theater that was absorbed; ``merged_at`` is the date
    lineage      [{event: "branched"|"merged", role, other_id, at, why}]; ``role`` says which side this entry
                 is: "child"/"parent" for a branch, "absorbed"/"survivor" for a merge. Events are never removed.

VALIDATION (``resolve``): a parent / merge target must be a tracked, not-merged-away theater (a merged one is
followed to its survivor); no self-merge; no merge that would close a cycle; a branch is a NEW theater, so
``parent_id`` on a reused theater is ignored. A branch needs at least two headlines like any theater (the
clustering loop already drops anything thinner).

NOMINATION (``nominations_block``): red-line / threat statements on the ledger that name a place or actor no
tracked theater mentions are surfaced to the clustering call, bounded, with dates and links. Code only surfaces
them; whether one deserves its own theater is the model's call.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any

# How far back the ledger is read for nominations, how many places/actors are offered, and how many statements
# are shown for each. Bounds on prompt size, not judgments about what matters.
NOMINATION_DAYS = 14
MAX_NOMINATIONS = 8
PER_NOMINATION = 3
NOMINATION_SIGNALS = frozenset({"red_line", "threat"})
_MAX_EVENTS = 40


def active(reg: dict[str, dict]) -> dict[str, dict]:
    """The registry theaters the clustering may still assign headlines to (not merged away)."""
    return {tid: e for tid, e in reg.items() if not e.get("merged_into")}


def survivor(reg: dict[str, dict], tid: str) -> str:
    """Follow ``merged_into`` to the theater that is still live ('' when the id is unknown or the chain loops)."""
    seen: set[str] = set()
    while tid in reg and tid not in seen:
        seen.add(tid)
        nxt = reg[tid].get("merged_into")
        if not nxt:
            return tid
        tid = nxt
    return ""


@dataclass
class Resolved:
    """One proposal after validation. ``id`` is the theater the headlines land in (a survivor for a merge)."""

    id: str
    parent_id: str = ""
    merged: list[str] = field(default_factory=list)     # tracked ids this proposal absorbed


def resolve(existing_id: str, merge_into: str, parent_id: str, new_id: str, reg: dict[str, dict]) -> Resolved:
    """Validate one proposal's lineage claims against the registry (see module docstring)."""
    if existing_id in reg:
        mine = survivor(reg, existing_id) or existing_id
        if merge_into and mine == existing_id:           # a live tracked theater asked to be folded into another
            target = survivor(reg, merge_into)
            if target and target != existing_id:         # unknown / self / a theater already folded into this one: ignored
                return Resolved(id=target, merged=[existing_id])
        return Resolved(id=mine)                         # a reused theater keeps its own lineage; parent_id is moot
    if new_id in reg:                                    # the slug collides with a tracked theater: it IS that one
        return Resolved(id=survivor(reg, new_id) or new_id)
    parent = survivor(reg, parent_id) if parent_id else ""
    return Resolved(id=new_id, parent_id=parent)


def apply(reg: dict[str, dict], t: Any, *, as_of: str) -> list[dict]:
    """Write one board theater's lineage (``parent_id`` / ``absorbed``) into ``reg`` (in place; the caller saves
    it). Idempotent: an event already recorded for the same pair is not repeated. Returns the new events."""
    tid, why, new = t.id, t.why, []

    def note(owner: str, event: str, role: str, other: str) -> None:
        events = reg[owner].setdefault("lineage", [])
        if any(e.get("event") == event and e.get("other_id") == other and e.get("role") == role for e in events):
            return
        row = {"event": event, "role": role, "other_id": other, "at": as_of, "why": why}
        events.append(row)
        del events[:-_MAX_EVENTS]
        new.append({"theater_id": owner, **row})

    if t.parent_id and tid in reg and not reg[tid].get("parent_id") and t.parent_id in reg:
        reg[tid]["parent_id"] = t.parent_id
        note(tid, "branched", "child", t.parent_id)
        note(t.parent_id, "branched", "parent", tid)
    for old in t.absorbed:
        if old in reg and tid in reg and old != tid and survivor(reg, tid) == tid:
            reg[old]["merged_into"], reg[old]["merged_at"] = tid, as_of
            note(old, "merged", "absorbed", tid)
            note(tid, "merged", "survivor", old)
            reg[tid]["first_seen"] = min(reg[tid].get("first_seen") or as_of, reg[old].get("first_seen") or as_of)
            reg[tid]["last_novel"] = max(reg[tid].get("last_novel", ""), reg[old].get("last_novel", ""))
    return new


# ── statement-driven nomination ───────────────────────────────────────────────────────────────
def _tokens(text: str) -> set[str]:
    return set(re.findall(r"\w+", (text or "").casefold()))


def _covered(term: str, covered_text: list[set[str]]) -> bool:
    tt = _tokens(term)
    return not tt or any(tt <= c for c in covered_text)


def nominations_block(reg: dict[str, dict], *, as_of: date, extra_text: list[str] | None = None) -> str:
    """The "SIGNALS THAT MAY DESERVE THEIR OWN THEATER" block, or '' when there are none. A signal is a recent
    red-line / threat statement whose ``about`` names a place or actor that no tracked theater's name or
    description mentions (``extra_text``: further text that counts as covering, e.g. the headlines' own theaters).
    Read-only over the statements ledger; never raises (a missing ledger is no nomination)."""
    from ..statements import store

    try:
        rows = [s for s in store.query(days=NOMINATION_DAYS, today=as_of) if s.signal in NOMINATION_SIGNALS]
    except Exception:  # noqa: BLE001 - nomination is an aid; a broken ledger must not cost the clustering
        return ""
    covered = [_tokens(f"{e.get('name', '')} {e.get('description', '')}") for e in active(reg).values()]
    covered += [_tokens(t) for t in extra_text or []]
    groups: dict[str, list] = {}
    for s in rows:                                       # newest first
        for about in dict.fromkeys(a.strip() for a in s.about if a.strip()):
            if not _covered(about, covered):
                groups.setdefault(about.casefold(), []).append((about, s))
    ranked = sorted(groups.values(), key=lambda g: (-len(g), -max(int(s.date.replace("-", "")) for _a, s in g)))
    lines = []
    for g in ranked[:MAX_NOMINATIONS]:
        lines.append(f"- {g[0][0]} ({len(g)} statement{'s' if len(g) != 1 else ''})")
        for _a, s in g[:PER_NOMINATION]:
            said = " ".join((s.paraphrase or s.quote).split())[:200]
            lines.append(f"    {s.date} [{s.signal}] {s.speaker}: {said} <{s.source_url}>")
    return "\n".join(lines)


def describe_known(reg: dict[str, dict]) -> str:
    """The tracked-theaters list the clustering is shown: live theaters only, with a branch's parent named."""
    lines = []
    for tid, t in active(reg).items():
        tail = f" (branched from {reg[t['parent_id']].get('name', t['parent_id'])})" if t.get("parent_id") in reg else ""
        lines.append(f"- {tid}: {t['name']} — {t.get('description', '')}{tail}")
    return "\n".join(lines) or "none yet"
