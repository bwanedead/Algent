"""
The searchable corpus: every source becomes ``Doc`` rows. Ids are citable and carry their kind:
``daily:<date>:<theater>``, ``statement:<id>``, ``sanction:<id>``, ``calendar:<id>``, ``geo:<event id>``, and ``claim:<id>`` (profile claims,
ranked by the research corpus itself: see ``search.py``).

Loaders read local stores, best-effort and independently: a missing or broken store is simply absent. ``today`` bounds every source from above
(nothing dated later is returned, so a replay sees only what was known then) except the calendar, whose job is to look ahead.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from . import flags


@dataclass(frozen=True)
class Doc:
    id: str
    kind: str                       # daily | statement | sanction | calendar | geo
    date: str                       # YYYY-MM-DD, "" when unknown
    title: str
    text: str


def clip(text: Any, n: int) -> str:
    t = " ".join(str(text or "").split())
    return t if len(t) <= n else t[: n - 1].rstrip() + "…"


def _daily(today: date) -> list[Doc]:
    from algent_backend.agent_system.agents.intel.daily import daily_dir

    folder = daily_dir("geopolitics")
    floor = (today - timedelta(days=flags.DAILY_DAYS)).isoformat()
    out: list[Doc] = []
    for p in sorted(folder.glob("*.json")) if folder.is_dir() else []:
        if not (floor <= p.stem <= today.isoformat()):
            continue
        try:
            rec = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        day = str(rec.get("date") or p.stem)
        for s in rec.get("theaters") or []:
            if not isinstance(s, dict) or not s.get("theater_id"):
                continue
            parts = [s.get(k) for k in ("bottom_line", "since_yesterday", "outlook")]
            wn = s.get("watch_next") or []
            parts += [("Watch next: " + " | ".join(wn if isinstance(wn, list) else [wn])) if wn else ""]
            parts += [d.get("headline") for d in (s.get("developments") or []) if isinstance(d, dict)]
            out.append(Doc(f"daily:{day}:{s['theater_id']}", "daily", day, f"{s.get('name', '')} (daily of {day})",
                           " ".join(str(x) for x in parts if x)))
    return out


def _statements(today: date) -> list[Doc]:
    from algent_backend.agent_system.agents.statements import store as st

    rows = st.query(days=flags.STATEMENT_DAYS, today=today)
    return [Doc(f"statement:{s.id}", "statement", s.date, f"{s.speaker} ({s.affiliation or s.role})",
                " ".join([s.paraphrase or s.quote, s.significance, *s.about, *s.topics])) for s in rows if s.date <= today.isoformat()]


def _sanctions(today: date) -> list[Doc]:
    from algent_backend.sanctions import store as sx

    floor = (today - timedelta(days=flags.SANCTION_DAYS)).isoformat()
    return [Doc(f"sanction:{e.id}", "sanction", e.date, f"{e.source} {e.action}: {e.name}",
                " ".join([e.name, e.type, e.owner, e.flag, *e.programmes, *e.countries]))
            for e in sx.events() if not e.baseline and floor <= e.observed_on <= today.isoformat()]


def _calendar(today: date) -> list[Doc]:
    from algent_backend.lookahead import store as cal

    lo = (today - timedelta(days=flags.CALENDAR_DAYS_BACK)).isoformat()
    hi = (today + timedelta(days=flags.CALENDAR_DAYS_AHEAD)).isoformat()
    return [Doc(f"calendar:{i.id}", "calendar", i.date, i.title, f"{i.title} ({i.kind}, {i.confidence} confidence) {' '.join(i.countries)}")
            for i in cal.current().values() if i.active and lo <= i.date <= hi]


def _geo(today: date) -> list[Doc]:
    from algent_backend.geoledger.store import Ledger

    led = Ledger()
    floor = (today - timedelta(days=flags.GEO_DAYS)).isoformat()
    out = []
    for e in led.events.values():
        a = led.assets.get(led.canonical(e.asset_id))
        if a is None or not (floor <= e.occurred_on <= today.isoformat()):
            continue
        out.append(Doc(f"geo:{e.id}", "geo", e.occurred_on, f"{a.name} ({a.type}, {a.country})",
                       f"{a.name} {a.type} {a.country}: {e.status.replace('_', ' ')} per {e.claimant}. {e.note}"))
    return out


LOADERS = (_daily, _statements, _sanctions, _calendar, _geo)


def load_all(today: date) -> list[Doc]:
    out: list[Doc] = []
    for load in LOADERS:
        try:
            out += load(today)
        except Exception:  # noqa: BLE001 - one broken store must not blind the others
            continue
    return out
