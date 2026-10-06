"""
The lineage part of a dossier: where a theater came from and what folded into it. Pure over the registry
(``lineage.py`` writes it) and the dossiers already built.

    "lineage": {"parent":      {theater_id, name, at, why, url}|null,   # branched from; url null if it has no dossier
                "branches":    [{theater_id, name, at, why, url}],      # theaters that branched out of this one
                "merged_into": {theater_id, name, at, why, url}|null,   # this theater was absorbed by that one
                "absorbed":    [{theater_id, name, at, why, url, first_seen, last_seen, days_covered}]},
    "inherited": [<timeline rows>]   # a branch only: the parent's history up to the branch date, newest first

``url`` is set only when the other theater has a dossier, so a page never links to a missing one.
"""

from __future__ import annotations

from typing import Any

MAX_INHERITED = 12      # how much of a parent's history a branch's page shows; the full record is one link away


def _ref(tid: str, reg: dict[str, dict], dossiers: dict[str, dict], at: str, why: str) -> dict:
    other = dossiers.get(tid)
    return {"theater_id": tid, "name": (reg.get(tid) or {}).get("name") or (other or {}).get("name") or tid,
            "at": at, "why": why, "url": f"/intel/theaters/{tid}" if other else None}


def _event(reg: dict[str, dict], tid: str, event: str, role: str, other: str) -> dict:
    return next((e for e in (reg.get(tid) or {}).get("lineage") or []
                 if e.get("event") == event and e.get("role") == role and e.get("other_id") == other), {})


def build(tid: str, reg: dict[str, dict], dossiers: dict[str, dict]) -> dict[str, Any]:
    """``{"lineage": ..., "inherited": [...]}`` for one theater."""
    entry = reg.get(tid) or {}
    parent_id = entry.get("parent_id") or ""
    ev = _event(reg, tid, "branched", "child", parent_id) if parent_id else {}
    parent = _ref(parent_id, reg, dossiers, ev.get("at", ""), ev.get("why", "")) if parent_id else None
    branches = []
    for child, ce in reg.items():
        if ce.get("parent_id") == tid:
            e = _event(reg, tid, "branched", "parent", child)
            branches.append(_ref(child, reg, dossiers, e.get("at", ""), e.get("why", "")))
    into = entry.get("merged_into") or ""
    ev_into = _event(reg, tid, "merged", "absorbed", into) if into else {}
    merged_into = _ref(into, reg, dossiers, ev_into.get("at") or entry.get("merged_at", ""),
                       ev_into.get("why", "")) if into else None
    absorbed = []
    for old, oe in reg.items():
        if oe.get("merged_into") == tid:
            e = _event(reg, tid, "merged", "survivor", old)
            d = dossiers.get(old) or {}
            absorbed.append({**_ref(old, reg, dossiers, e.get("at") or oe.get("merged_at", ""), e.get("why", "")),
                             "first_seen": oe.get("first_seen", ""),
                             "last_seen": d.get("last_seen") or oe.get("last_seen", ""),
                             "days_covered": d.get("days_covered", 0)})
    inherited: list[dict] = []
    if parent and parent["at"] and parent_id in dossiers:
        history = [t for t in dossiers[parent_id].get("timeline") or [] if (t.get("date") or "9") <= parent["at"]]
        inherited = history[:MAX_INHERITED]                 # the parent's timeline is newest first
    return {"lineage": {"parent": parent, "branches": branches, "merged_into": merged_into, "absorbed": absorbed},
            "inherited": inherited}
