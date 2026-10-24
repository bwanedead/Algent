"""
Our own system as calendar items — read from local stores, no network.

* ``markets``: every open Polymarket market the markets product tracks gets an item on its resolution day (kind ``market_resolves``,
  linked to /intel/track-record, where the desk's forecast for it is scored). Countries and theaters are the ones the market was mapped
  to when it was mirrored (markets/mapping.py), nothing new is inferred.
* ``watches``: an open Pulse watch with a ``horizon`` date is a forward condition of a situation ("by 12 Nov the truce must hold"); it
  becomes a ``deadline`` item linked to its situation. Both are ours, so provenance is ``ohmega_derived``: a market's end date is
  ``estimated`` (Polymarket moves them), a watch horizon is ``unconfirmed`` (our own forward condition, like the corpus extractor's
  deadlines named in dailies, extract.py).

Sanctions and treaty expiries are not here because neither store records an expiry date; they join when the data does.
"""

from __future__ import annotations

from datetime import date

from ..contracts import CalendarItem, make
from . import upcoming

SITE = "https://www.ohmega.monster"
TRACK_RECORD = SITE + "/intel/track-record"


def markets_items(markets: list, today: date) -> list[CalendarItem]:
    out = []
    for m in markets:
        day = (m.end_date or "")[:10]
        if m.status != "open" or len(day) != 10:
            continue
        out.append(make("market_resolves", "markets", day, f"Market resolves: {m.question}", TRACK_RECORD, countries=m.countries, theaters=m.theaters,
                        provenance="ohmega_derived", via=f"market:{m.id}", grade="estimated", confidence="medium"))
    return upcoming(out, today)


def watches_items(watches: list, today: date) -> list[CalendarItem]:
    out = []
    for w in watches:
        day = (w.horizon or "")[:10]
        if w.status != "open" or len(day) != 10:
            continue
        out.append(make("deadline", "watches", day, f"Watch horizon: {w.condition}", f"{SITE}/situations/{w.situation_id}",
                        situations=[w.situation_id], provenance="ohmega_derived", via=f"watch:{w.id}", grade="unconfirmed", confidence="low"))
    return upcoming(out, today)


def fetch_markets(today: date) -> list[CalendarItem]:
    from algent_backend.markets import store

    return markets_items(list(store.markets().values()), today)


def fetch_watches(today: date) -> list[CalendarItem]:
    from algent_backend.agent_system.agents.pulse.repository import pulse_store

    return watches_items(pulse_store().watches(), today)
