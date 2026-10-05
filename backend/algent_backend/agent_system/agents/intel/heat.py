"""
The heat detector — find what is actually boiling, without being told where to look.

Reads a broad headline base (``base``: our radar's editions, Wikipedia's Current Events, and recent
documents from our own trusted-source library), groups the headlines into THEATERS by the dynamic they
belong to (an ongoing contest between actors, not a shared keyword), and measures each theater's heat from
how often it appears, whether that is accelerating, and whether it is new. Then ``novelty`` counts what is
new in each theater since its last daily section and ``focus`` classifies its lifecycle (new / active /
quiet) and records it on the board and in the registry.

Nothing is configured per conflict. Theaters keep their identity across runs through a registry the
clustering is shown ("reuse an existing theater when it is the same dynamic"), so a theater's heat
accumulates into a trend instead of being renamed away each day. Cheap: one model call per run, over
headlines the newsroom already gathered for free.
"""

from __future__ import annotations

import json
import os
import re
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from . import base as base_mod
from . import lineage
from .contracts import ClassShare, HeatPoint, Member, Theater, TheaterHeat

_STORE_ENV = "ALGENT_INTEL_STORE"
_DEFAULT_DIR = "intel_store"

CLUSTER_ROLE = """\
You are the watch officer of an intelligence desk. You get the headlines the desk has logged over
recent days, each with an id and date. Group them into THEATERS: ongoing dynamics between actors
that an analyst would follow as one thing — "Russia's campaign against European logistics and
airspace", "the US–Iran confrontation over Hormuz", "China's pressure on Taiwan".

- Group by the DYNAMIC, not the keyword. Two stories about Russia belong together only when they are
  part of the same contest; a Russian ballet tour is not part of the war.
- Include peripheral stories that genuinely bear on a dynamic (an insurance market reacting to a
  blockade belongs to the blockade's theater).
- Headlines come from several source classes, tagged on each line (radar = our newsroom's picks,
  wikipedia = cited events of the day, library = documents from official and wire sources). The class is
  where a line came from, never what it is about: group by dynamic across classes, and let an event our
  radar and an official source both carry sit in one theater.
- A theater needs at least two headlines. One-off stories are left out — most headlines are.
- You are given the theaters the desk already tracks. When a group is the SAME dynamic, reuse its
  `existing_id` exactly — continuity is what lets heat build into a trend. Create a new theater only
  for a dynamic not already tracked.
- Theaters BRANCH and MERGE, because readers follow the dynamic, not our filing. When a group of headlines is
  a DISTINCT dynamic that grew out of a tracked theater — its own actors, its own stakes, its own path of
  escalation, a contest over one place or front that now drives events on its own (a besieged enclave inside a
  wider confrontation, a sea lane inside a regional standoff) — propose it as a NEW theater with `parent_id` set
  to the tracked theater it came out of, and leave the rest of the headlines in the parent. A story that merely
  happens in that place, or only illustrates the parent's dynamic, stays in the parent: branch only when
  following it separately would tell the reader something following the parent does not. The branch keeps its
  parent named, so its history is never lost.
- When two TRACKED theaters have turned out to be one dynamic, say so: give one of them as `existing_id` with
  `merge_into` set to the other (the one that should survive, usually the broader or older), and put the
  headlines in the survivor. Merge only when the actors, stakes and escalation path are the same, not when the
  two are neighbours or one feeds the other. Both histories are kept; future headlines go to the survivor.
- Where SIGNALS THAT MAY DESERVE THEIR OWN THEATER are listed, they are red lines and threats on the record
  that name a place or actor no tracked theater covers. They are leads, not instructions: a theater needs
  headlines (at least two) that show a dynamic, and a lone statement is not one.
- `domain`: geopolitics, economics, technology, science, health, politics, society — one word.
- `why`: one sentence on what ties these together and what is at stake.
"""


class ProposedTheater(BaseModel):
    existing_id: str = ""
    name: str
    domain: str = "geopolitics"
    description: str = ""
    why: str = ""
    headline_ids: list[str] = Field(default_factory=list)
    parent_id: str = ""        # a NEW theater that branched out of this tracked one
    merge_into: str = ""       # with ``existing_id``: that tracked theater is the same dynamic as this one


class TheaterPlan(BaseModel):
    theaters: list[ProposedTheater] = Field(default_factory=list)


def store_dir() -> Path:
    return Path(os.environ.get(_STORE_ENV) or _DEFAULT_DIR)


def registry() -> dict[str, dict]:
    path = store_dir() / "theaters.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def _save_registry(reg: dict[str, dict]) -> None:
    path = store_dir() / "theaters.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(reg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def headlines(editions: list[dict], *, days: int, today: date | None = None) -> dict[str, dict]:
    """The window's headlines, keyed by a stable id (edition + number)."""
    last = today or max((date.fromisoformat(e["slug"][:10]) for e in editions), default=date.today())
    start = last - timedelta(days=days - 1)
    out = {}
    for e in editions:
        day = date.fromisoformat(e["slug"][:10])
        if day < start or day > last:
            continue
        for lead in e.get("leads") or []:
            out[f"{e['slug']}#{lead['n']}"] = {"edition": e["slug"], "day": day.isoformat(), **lead}
    return out


def _slug(name: str) -> str:
    return "thr_" + (re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")[:48] or "theater")


def cluster(context: Any, config: Any, heads: dict[str, dict], *, model_spec: Any) -> list[Theater]:
    """One call: group the window's headlines into theaters, reusing known theater ids."""
    from langchain_core.messages import HumanMessage, SystemMessage

    from algent_backend.agent_system.prompting import UNIVERSAL_AGENT_BASE, compose_system_prompt

    reg = registry()
    nominated = lineage.nominations_block(reg, as_of=max((date.fromisoformat(h["day"]) for h in heads.values()),
                                                         default=date.today()))
    lines = "\n".join(f"[{hid}] {h['day']} ({h.get('kind', 'radar')}) — {h['title']}"
                      + (f": {h['thesis'][:160]}" if h.get("thesis") else "") for hid, h in heads.items())
    signals = f"SIGNALS THAT MAY DESERVE THEIR OWN THEATER:\n{nominated}\n\n" if nominated else ""
    task = (f"THEATERS ALREADY TRACKED:\n{lineage.describe_known(reg)}\n\n{signals}"
            f"HEADLINES:\n{lines}\n\nTASK: group them into theaters.")
    model = context.model_resolver.resolve(model_spec).client.with_structured_output(TheaterPlan)
    plan = model.invoke([SystemMessage(content=compose_system_prompt(UNIVERSAL_AGENT_BASE, CLUSTER_ROLE)),
                         HumanMessage(content=task)], config=config)
    theaters: dict[str, Theater] = {}
    for p in getattr(plan, "theaters", []) or []:
        ids = [h for h in dict.fromkeys(p.headline_ids) if h in heads]
        if len(ids) < 2:
            continue
        r = lineage.resolve(p.existing_id, p.merge_into, p.parent_id, _slug(p.name), reg)
        members = [Member(edition=heads[h]["edition"], n=heads[h]["n"], kind=heads[h].get("kind", "radar"),
                          title=heads[h]["title"], thesis=heads[h].get("thesis", ""), sources=heads[h].get("sources", []))
                   for h in ids]
        have = theaters.get(r.id)
        if have is None:                     # two proposals landing in one theater (a merge) become one
            name = reg[r.id]["name"] if r.merged and r.id in reg else p.name
            theaters[r.id] = Theater(id=r.id, name=name, domain=p.domain, description=p.description, why=p.why,
                                     members=members, parent_id=r.parent_id, absorbed=list(r.merged))
        else:
            have.members += [m for m in members if (m.edition, m.n) not in {(x.edition, x.n) for x in have.members}]
            have.absorbed += [a for a in r.merged if a not in have.absorbed]
    return list(theaters.values())




def edition_sizes(editions: list[dict]) -> dict[str, int]:
    """Headlines per radar edition (slug -> count): the denominator that makes coverage comparable."""
    return {e["slug"]: len(e.get("leads") or []) for e in editions}


def radar_day_sizes(editions: list[dict]) -> dict[str, dict[str, int]]:
    """The radar-only denominators (class -> day -> headlines), for callers that have no ``Base``."""
    by_day: dict[str, int] = {}
    for slug, n in edition_sizes(editions).items():
        by_day[slug[:10]] = by_day.get(slug[:10], 0) + n
    return {base_mod.RADAR: by_day}


def _share(members: int, headlines: int) -> float:
    return members / headlines if headlines else 0.0


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _judge(pairs: list[tuple[int, int, int, int]]) -> str:
    """heating / cooling / steady from per-class (recent_m, recent_n, prior_m, prior_n). A change counts only
    when it exceeds its own noise: per class, the standard error of the difference between two proportions
    (pooled), so 2 of 10 vs 3 of 10 is steady while 10 of 100 vs 20 of 100 is heating. Classes are combined
    like the shares are: the mean of their differences against the standard error of that mean
    (sqrt of the summed variances / k). One class reduces to the plain test. Derived, not tuned."""
    diffs, variances = [], []
    for m1, n1, m2, n2 in pairs:
        if not n1 or not n2:
            continue
        pooled = _share(m1 + m2, n1 + n2)
        variances.append(pooled * (1 - pooled) * (1 / n1 + 1 / n2))
        diffs.append(_share(m1, n1) - _share(m2, n2))
    if not diffs:
        return "steady"
    diff, se = _mean(diffs), sum(variances) ** 0.5 / len(diffs)
    return "heating" if diff > se else "cooling" if diff < -se else "steady"


def measure(theater: Theater, editions: list[dict], *, days: int, today: date,
            sizes: dict[str, dict[str, int]] | None = None) -> TheaterHeat:
    """Deterministic heat, as a SHARE of coverage — never raw volume, which swings with how many radar
    editions we happened to build (several one day, none for three) and with how big each source class is.

    ``sizes`` is class -> day -> headlines in the base (``base.Base.sizes``); without it the radar editions
    are the whole base. For each source class and window, ``share = theater members of that class /
    headlines of that class``; the theater's share in a window is the MEAN of the shares of the classes that
    have headlines in it, so no class outvotes another and a class with no data (the radar skipped three days)
    is absent, never a zero.

    recent = the last 3 days, prior = the 3 before. A window with no headlines in any class is "no data": the
    trend is judged from what exists, never read as a drop to zero:
      - both windows have headlines: ``new`` if first seen in recent with nothing in prior; else
        ``heating``/``cooling``/``steady`` by whether the mean share change beats its standard error (``_judge``);
      - prior has none: ``new`` if first seen in the recent window, else ``steady``;
      - recent has none: ``steady`` (nothing to compare).
    heat = 100 * (w * recent_share + 0.25 * earlier_share), w = 1.5 when heating/new else 1; earlier
    share covers the rest of the window, so a long-running theater keeps a floor. Units: headlines per
    100 in the recent window. (1.5 and 0.25 are weights on the ranking, not gates on a trend.)
    """
    sizes = sizes if sizes is not None else radar_day_sizes(editions)
    counts: dict[str, dict[str, int]] = {}                  # class -> day -> this theater's members
    for m in theater.members:
        per = counts.setdefault(m.kind, {})
        per[m.edition[:10]] = per.get(m.edition[:10], 0) + 1
    ed_by_day: dict[str, int] = {}
    for slug in edition_sizes(editions):
        ed_by_day[slug[:10]] = ed_by_day.get(slug[:10], 0) + 1
    day_keys = [(today - timedelta(days=i)).isoformat() for i in range(days - 1, -1, -1)]
    series = [HeatPoint(day=d, count=sum(c.get(d, 0) for c in counts.values()), editions=ed_by_day.get(d, 0))
              for d in day_keys]
    windows = {"recent": day_keys[-3:], "prior": day_keys[-6:-3], "earlier": day_keys[:-3]}

    def window(cls: str, name: str) -> tuple[int, int]:      # (members, headlines)
        keys = windows[name]
        return (sum(counts.get(cls, {}).get(d, 0) for d in keys), sum(sizes.get(cls, {}).get(d, 0) for d in keys))

    classes = sorted(set(sizes) | set(counts))
    w = {name: {c: window(c, name) for c in classes} for name in windows}
    mean_share = {name: _mean([_share(m, n) for m, n in w[name].values() if n]) for name in windows}
    recent_has = any(n for _, n in w["recent"].values())
    prior_has = any(n for _, n in w["prior"].values())
    recent = sum(m for m, _ in w["recent"].values())
    prior = sum(m for m, _ in w["prior"].values())
    all_days = [d for per in counts.values() for d in per]
    first = min(all_days, default="")
    appeared = bool(first) and first >= day_keys[-3]        # first seen inside the recent window
    if not recent_has:
        trend = "steady"
    elif not prior_has:
        trend = "new" if appeared else "steady"
    elif appeared and prior == 0:
        trend = "new"
    else:
        trend = _judge([(*w["recent"][c], *w["prior"][c]) for c in classes])
    heat = 100 * ((1.5 if trend in ("heating", "new") else 1.0) * mean_share["recent"] + 0.25 * mean_share["earlier"])
    by_class = {c: ClassShare(recent=w["recent"][c][0], recent_n=w["recent"][c][1],
                              prior=w["prior"][c][0], prior_n=w["prior"][c][1])
                for c in classes if counts.get(c) or any(n for _, n in (w["recent"][c], w["prior"][c]))}
    return TheaterHeat(theater_id=theater.id, name=theater.name, series=series,
                       total=sum(sum(c.values()) for c in counts.values()),
                       recent=recent, prior=prior, recent_share=round(mean_share["recent"], 4),
                       prior_share=round(mean_share["prior"], 4), trend=trend, first_seen=first, heat=round(heat, 2),
                       by_class=by_class)


def run(context: Any, config: Any, editions: list[dict], *, model_spec: Any, days: int = 7,
        loaders: dict[str, base_mod.Loader] | None = None, today: date | None = None,
        covered_before: str = "", write: bool = True) -> dict:
    """Assemble the base, cluster it, measure heat, record novelty and lifecycle, remember the theaters.
    Returns the heat board.

    ``loaders`` adds source classes beyond the radar (``base.default_loaders()`` for the real ones; None =
    radar only, offline). ``covered_before`` is the date a daily written today would carry: a section on or
    after it does not count as "already covered" (default: the board's date). ``write=False`` builds the
    board without touching the registry or the board snapshot (the live check, tests)."""
    from . import focus

    base = base_mod.assemble(editions, days=days, today=today, loaders=loaders)
    heads = base.heads
    as_of = today or (max(date.fromisoformat(h["day"]) for h in heads.values()) if heads else date.today())
    theaters = cluster(context, config, heads, model_spec=model_spec)
    reg = registry()
    for t in theaters:
        entry = reg.get(t.id, {"first_seen": as_of.isoformat()})
        reg[t.id] = {**entry, "name": t.name, "domain": t.domain, "description": t.description,
                     "last_seen": as_of.isoformat()}
    events = [e for t in theaters for e in lineage.apply(reg, t, as_of=as_of.isoformat())]
    heat = sorted((measure(t, editions, days=days, today=as_of, sizes=base.sizes) for t in theaters),
                  key=lambda h: -h.heat)
    focus.annotate(theaters, heat, reg, as_of=as_of, days=days, covered_before=covered_before or as_of.isoformat())
    if write:
        _save_registry(reg)
    board = {"as_of": as_of.isoformat(), "window_days": days, "headlines": len(heads), "base": base.summary(),
             "theaters": [t.model_dump() for t in theaters], "lineage": events, "heat": [h.model_dump() for h in heat],
             "lifecycle": focus.offboard(reg, {t.id for t in theaters}, as_of=as_of, days=days)}
    if write:
        snap = store_dir() / "boards" / f"{as_of.isoformat()}.json"
        snap.parent.mkdir(parents=True, exist_ok=True)
        snap.write_text(json.dumps(board, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    return board
