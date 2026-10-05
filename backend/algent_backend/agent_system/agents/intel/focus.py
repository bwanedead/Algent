"""
Focus — which theaters the desk is looking at today, and the lifecycle that decides it.

The world, not the schedule, sets the focus. A theater ENTERS when something new happens and LEAVES when
nothing has for about a week; the daily covers what is moving and says so plainly about the rest.

LIFECYCLE (``classify``; persisted per theater in the registry as ``state`` and ``last_novel``)
* ``last_novel`` is the date of the newest thing seen for the theater: a member headline of any source
  class, a statement on record that sensing ties to it, a series that newly left its range
  (``novelty``). It only moves forward, and it moves the moment a re-clustered headline brings the theater back.
* ``quiet``  — nothing new for ``FOCUS_DROP_DAYS``: it falls off the focus.
* ``new``    — first seen inside the window and never yet written up in a daily.
* ``active`` — anything else with novelty inside ``FOCUS_DROP_DAYS``. A quiet theater is ``active`` again the
  moment its ``last_novel`` is inside the span (there is no separate "revive" step: the state is recomputed
  from the dates on every board).
Legacy registry entries (no ``last_novel``) are seeded from ``last_seen``, the last board that carried them.

FOCUS (``plan``)
* In focus: ``new``/``active`` theaters with novelty since their last section, ranked by heat x novelty
  (how much is reported, times how much of it is new). ``top`` is a CEILING, not a quota: a quiet world
  yields a few sections, a busy one up to the ceiling.
* WATCH: ``new``/``active`` theaters not in focus — nothing new since the last section, or cut by the ceiling
  (the entry says which). One mechanical line each; no model call.
* QUIET: theaters that were once covered and have gone ``quiet``, with their last change date.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from . import novelty, sensing
from .contracts import Theater, TheaterHeat
from .heat import store_dir

# The operator's own rule (10-04): "if nothing new for a week it falls off". A decision about how long the
# desk's attention lasts, not something the data implies, so it is named here and nowhere else.
FOCUS_DROP_DAYS = 7
MAX_COUNTRIES = 3


def last_sections(intel_dir: Any, *, before: str) -> dict[str, dict]:
    """theater id -> {date, countries} of its newest daily section dated before ``before`` (any domain)."""
    found: dict[str, dict] = {}
    folder = intel_dir / "daily"
    paths = sorted(folder.glob("*/*.json"), key=lambda p: p.stem, reverse=True) if folder.is_dir() else []
    for path in paths:
        if path.stem >= before:
            continue
        try:
            rec = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for sec in rec.get("theaters") or []:
            tid = sec.get("theater_id")
            if tid and tid not in found:
                places = [(d.get("place") or {}).get("country", "") for d in sec.get("developments") or []]
                countries = list(dict.fromkeys(c for c in places if c and c.lower() != "sea"))[:MAX_COUNTRIES]
                found[tid] = {"date": rec.get("date", path.stem), "countries": countries}
    return found


def classify(*, last_novel: str, first_seen: str, covered: bool, as_of: date, days: int) -> str:
    """new / active / quiet (see module docstring)."""
    if not last_novel or (as_of - date.fromisoformat(last_novel)).days >= FOCUS_DROP_DAYS:
        return "quiet"
    if not covered and first_seen >= (as_of - timedelta(days=days - 1)).isoformat():
        return "new"
    return "active"


def annotate(theaters: list[Theater], heats: list[TheaterHeat], reg: dict[str, dict], *, as_of: date, days: int,
             covered_before: str) -> None:
    """Fill each heat row's novelty / state / last_novel and update the registry in place (the caller saves it).
    Registry theaters that are not on this board are re-classified from their persisted dates only."""
    covered = last_sections(store_dir(), before=covered_before)
    by_id = {t.id: t for t in theaters}
    for h in heats:
        t, entry = by_id[h.theater_id], reg[h.theater_id]
        since = novelty.since_for(covered.get(t.id, {}).get("date", ""), as_of=as_of, days=days)
        window = max(sensing.DAILY_STATEMENT_DAYS, (as_of - date.fromisoformat(since)).days + 1)
        ev = sensing.for_theater(t, as_of=as_of, statement_days=window)
        h.novelty = novelty.measure(t, since=since, as_of=as_of, ev=ev)
        newest_member = max((m.edition[:10] for m in t.members), default="")
        h.last_novel = max(entry.get("last_novel", ""), newest_member, h.novelty["newest"])
        h.state = classify(last_novel=h.last_novel, first_seen=entry.get("first_seen", ""), covered=t.id in covered,
                           as_of=as_of, days=days)
        entry.update(last_novel=h.last_novel, state=h.state)
    for tid, entry in reg.items():
        if tid not in by_id:
            entry["last_novel"] = entry.get("last_novel") or entry.get("last_seen", "")
            entry["state"] = classify(last_novel=entry["last_novel"], first_seen=entry.get("first_seen", ""),
                                      covered=tid in covered, as_of=as_of, days=days)


def offboard(reg: dict[str, dict], on_board: set[str], *, as_of: date, days: int) -> list[dict]:
    """Registry theaters the clustering did not return this run, with their persisted lifecycle."""
    covered = last_sections(store_dir(), before=as_of.isoformat())
    return [{"theater_id": tid, "name": e.get("name", tid), "domain": e.get("domain", ""),
             "state": e.get("state", ""), "last_novel": e.get("last_novel", ""),
             "last_section": covered.get(tid, {}).get("date", ""), "countries": covered.get(tid, {}).get("countries", [])}
            for tid, e in reg.items() if tid not in on_board and e.get("state")]


@dataclass
class Plan:
    focus: list[str] = field(default_factory=list)       # theater ids to write sections for, in rank order
    watch: list[dict] = field(default_factory=list)
    quiet: list[dict] = field(default_factory=list)


def plan(board: dict, top: int, domains: list[str] | None = None) -> Plan:
    """Today's focus from a board. A board without lifecycle data (built before it existed) falls back to the
    ``top`` hottest theaters and no watch/quiet lists, as before."""
    from . import desk

    heats = board.get("heat", [])
    if not any(h.get("state") for h in heats):
        return Plan(focus=desk.pick_theaters(board, top, domains))
    wanted = {d.strip().lower() for d in domains or [] if d.strip()}
    domain_of = {t["id"]: (t.get("domain") or "").lower() for t in board.get("theaters", [])}
    rows = [h for h in heats if not wanted or domain_of.get(h["theater_id"]) in wanted]
    live = [h for h in rows if h.get("state") in ("new", "active")]
    moving = sorted((h for h in live if (h.get("novelty") or {}).get("total", 0) > 0),
                    key=lambda h: (-h.get("heat", 0) * h["novelty"]["total"], -h.get("heat", 0)))
    chosen = moving[:max(top, 0)]
    chosen_ids = {h["theater_id"] for h in chosen}
    watch = []
    for h in sorted(live, key=lambda h: -h.get("heat", 0)):
        if h["theater_id"] in chosen_ids:
            continue
        nov = h.get("novelty") or {}
        total = nov.get("total", 0)
        since = nov.get("since", "")
        watch.append({"theater_id": h["theater_id"], "name": h["name"], "last_novel": h.get("last_novel", ""),
                      "since": since, "new_items": total,
                      "reason": "over_budget" if total else "nothing_new",
                      "note": (f"{total} new item{'s' if total != 1 else ''} since {since}; not in today's focus."
                               if total else f"No new developments since {since}.")})
    quiet = [{"theater_id": h["theater_id"], "name": h["name"], "last_novel": h.get("last_novel", "")}
             for h in rows if h.get("state") == "quiet"]
    for e in board.get("lifecycle", []):
        if wanted and (e.get("domain") or "").lower() not in wanted:
            continue
        if e.get("state") == "active":
            since = e.get("last_section") or e.get("last_novel", "")
            watch.append({"theater_id": e["theater_id"], "name": e["name"], "last_novel": e.get("last_novel", ""),
                          "since": since, "new_items": 0, "reason": "nothing_new",
                          "note": f"No new developments since {since}."})
        elif e.get("state") == "quiet" and e.get("last_section"):    # never covered = never mattered: not listed
            quiet.append({"theater_id": e["theater_id"], "name": e["name"], "last_novel": e.get("last_novel", ""),
                          "countries": e.get("countries", [])})
    quiet.sort(key=lambda q: q["last_novel"], reverse=True)
    return Plan(focus=[h["theater_id"] for h in chosen], watch=watch, quiet=quiet)
