"""
The heat detector — find what is actually boiling, without being told where to look.

Reads the headline radar's history (every daily edition), groups the headlines into THEATERS by the
dynamic they belong to (an ongoing contest between actors, not a shared keyword), and measures each
theater's heat from how often it appears, whether that is accelerating, and whether it is new.

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

from .contracts import HeatPoint, Member, Theater, TheaterHeat

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
- A theater needs at least two headlines. One-off stories are left out — most headlines are.
- You are given the theaters the desk already tracks. When a group is the SAME dynamic, reuse its
  `existing_id` exactly — continuity is what lets heat build into a trend. Create a new theater only
  for a dynamic not already tracked.
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
    known = "\n".join(f"- {tid}: {t['name']} — {t.get('description', '')}" for tid, t in reg.items()) or "none yet"
    lines = "\n".join(f"[{hid}] {h['day']} — {h['title']}: {h.get('thesis', '')[:160]}" for hid, h in heads.items())
    task = f"THEATERS ALREADY TRACKED:\n{known}\n\nHEADLINES:\n{lines}\n\nTASK: group them into theaters."
    model = context.model_resolver.resolve(model_spec).client.with_structured_output(TheaterPlan)
    plan = model.invoke([SystemMessage(content=compose_system_prompt(UNIVERSAL_AGENT_BASE, CLUSTER_ROLE)),
                         HumanMessage(content=task)], config=config)
    theaters: list[Theater] = []
    for p in getattr(plan, "theaters", []) or []:
        ids = [h for h in dict.fromkeys(p.headline_ids) if h in heads]
        if len(ids) < 2:
            continue
        tid = p.existing_id if p.existing_id in reg else _slug(p.name)
        theaters.append(Theater(
            id=tid, name=p.name, domain=p.domain, description=p.description, why=p.why,
            members=[Member(edition=heads[h]["edition"], n=heads[h]["n"], title=heads[h]["title"],
                            thesis=heads[h].get("thesis", ""), sources=heads[h].get("sources", []))
                     for h in ids]))
    return theaters


def edition_sizes(editions: list[dict]) -> dict[str, int]:
    """Headlines per radar edition (slug -> count): the denominator that makes coverage comparable."""
    return {e["slug"]: len(e.get("leads") or []) for e in editions}


def _share(members: int, headlines: int) -> float:
    return members / headlines if headlines else 0.0


def _judge(recent_m: int, recent_n: int, prior_m: int, prior_n: int) -> str:
    """heating / cooling / steady from two shares. A change counts only when it exceeds its own noise:
    the standard error of the difference between two proportions (pooled), so a theater seen in 2 of 10
    headlines vs 3 of 10 is steady while 10 of 100 vs 20 of 100 is heating. Derived, not tuned."""
    n1, n2 = recent_n, prior_n
    pooled = _share(recent_m + prior_m, n1 + n2)
    se = (pooled * (1 - pooled) * (1 / n1 + 1 / n2)) ** 0.5
    diff = _share(recent_m, n1) - _share(prior_m, n2)
    return "heating" if diff > se else "cooling" if diff < -se else "steady"


def measure(theater: Theater, editions: list[dict], *, days: int, today: date) -> TheaterHeat:
    """Deterministic heat, as a SHARE of coverage — never raw volume, which swings with how many radar
    editions we happened to build (several one day, none for three).

    recent = the last 3 days, prior = the 3 before. For each window,
    ``share = theater headlines / all headlines in that window's editions``. A window with no editions
    is "no data": the trend is judged from what exists, never read as a drop to zero:
      - both windows have editions: ``new`` if first seen in recent with nothing in prior; else
        ``heating``/``cooling``/``steady`` by whether the share change beats its standard error;
      - prior has none: ``new`` if first seen in the recent window, else ``steady``;
      - recent has none: ``steady`` (nothing to compare).
    heat = 100 * (w * recent_share + 0.25 * earlier_share), w = 1.5 when heating/new else 1; earlier
    share covers the rest of the window, so a long-running theater keeps a floor. Units: headlines per
    100 in the recent editions. (1.5 and 0.25 are weights on the ranking, not gates on a trend.)
    """
    counts: dict[str, int] = {}
    for m in theater.members:
        counts[m.edition[:10]] = counts.get(m.edition[:10], 0) + 1
    sizes = edition_sizes(editions)
    by_day: dict[str, list[int]] = {}                   # day -> sizes of that day's editions
    for slug, n in sizes.items():
        by_day.setdefault(slug[:10], []).append(n)
    day_keys = [(today - timedelta(days=i)).isoformat() for i in range(days - 1, -1, -1)]
    series = [HeatPoint(day=d, count=counts.get(d, 0), editions=len(by_day.get(d, []))) for d in day_keys]

    def window(keys: list[str]) -> tuple[int, int, int]:   # (members, headlines, editions)
        return (sum(counts.get(d, 0) for d in keys), sum(sum(by_day.get(d, [])) for d in keys),
                sum(len(by_day.get(d, [])) for d in keys))

    (recent, recent_n, recent_e), (prior, prior_n, prior_e) = window(day_keys[-3:]), window(day_keys[-6:-3])
    earlier, earlier_n, _ = window(day_keys[:-3])
    first = min(counts) if counts else ""
    appeared = bool(first) and first >= day_keys[-3]   # first seen inside the recent window
    if not recent_e or not recent_n:
        trend = "steady"
    elif not prior_e or not prior_n:
        trend = "new" if appeared else "steady"
    elif appeared and prior == 0:
        trend = "new"
    else:
        trend = _judge(recent, recent_n, prior, prior_n)
    recent_share, prior_share = _share(recent, recent_n), _share(prior, prior_n)
    heat = 100 * ((1.5 if trend in ("heating", "new") else 1.0) * recent_share + 0.25 * _share(earlier, earlier_n))
    return TheaterHeat(theater_id=theater.id, name=theater.name, series=series, total=sum(counts.values()),
                       recent=recent, prior=prior, recent_share=round(recent_share, 4),
                       prior_share=round(prior_share, 4), trend=trend, first_seen=first, heat=round(heat, 2))


def run(context: Any, config: Any, editions: list[dict], *, model_spec: Any, days: int = 7) -> dict:
    """Cluster the window, measure heat, remember the theaters. Returns the heat board."""
    heads = headlines(editions, days=days)
    today = max(date.fromisoformat(h["day"]) for h in heads.values()) if heads else date.today()
    theaters = cluster(context, config, heads, model_spec=model_spec)
    reg = registry()
    for t in theaters:
        entry = reg.get(t.id, {"first_seen": today.isoformat()})
        reg[t.id] = {**entry, "name": t.name, "domain": t.domain, "description": t.description,
                     "last_seen": today.isoformat()}
    _save_registry(reg)
    heat = sorted((measure(t, editions, days=days, today=today) for t in theaters), key=lambda h: -h.heat)
    board = {"as_of": today.isoformat(), "window_days": days, "headlines": len(heads),
             "theaters": [t.model_dump() for t in theaters], "heat": [h.model_dump() for h in heat]}
    snap = store_dir() / "boards" / f"{today.isoformat()}.json"
    snap.parent.mkdir(parents=True, exist_ok=True)
    snap.write_text(json.dumps(board, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    return board
