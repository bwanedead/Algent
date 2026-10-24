"""
Importance — how much an item matters, from what it is and what it touches. A rule, written down; no model.

    1 routine   the weekly EIA stock reports, UN Security Council meetings and presidency changes, small launches, a market resolving
    2 notable   most central-bank meetings, national elections, hearings, conferences, earnings, commodity reports, summits
    3 major     G7/G20/NATO/COP/APEC/BRICS summits, the big-eight central banks (Fed, ECB, BoE, BoJ, PBoC, BoC, RBA, SNB), GDP and
                PCE releases, presidential or general elections and referendums, ICJ judgments

Then two adjustments: +1 (to at most 3) when the item is linked to a hot situation or theater, and a cap at 2 for anything graded
``unconfirmed`` (our own reading of our own report is never "major"). "Hot" = one of the ``HOT_TOP`` theaters with the highest heat on
the latest desk board (``hot_theaters``). No threshold on a number the data does not already rank.
"""

from __future__ import annotations

import re

from .contracts import CalendarItem

HOT_TOP = 5
BIG_BANKS = {"US", "EU", "GB", "JP", "CN", "CA", "AU", "CH"}
_MAJOR_SUMMIT = re.compile(r"\b(G7|G20|NATO|COP\d*|APEC|BRICS|SCO|ASEAN)\b")
_MAJOR_RELEASE = re.compile(r"\b(GDP|PCE|CPI|payrolls?|jobs)\b", re.I)
_TOP_OFFICE = re.compile(r"president|general|parliament|legislative|referendum|prime minister|house of|national assembly", re.I)
_BIG_LAUNCH = re.compile(r"starship|new glenn|sls|artemis|crew|gaganyaan|long march 10|shenzhou|mars", re.I)


def base(i: CalendarItem) -> int:
    k, t = i.kind, i.title
    if k == "central_bank":
        return 3 if BIG_BANKS & set(i.countries) and "Loan Prime" not in t else 2
    if k == "summit":
        return 3 if _MAJOR_SUMMIT.search(t) else 2
    if k == "data_release":
        return 3 if _MAJOR_RELEASE.search(t) else 2
    if k in ("election", "vote"):
        return 3 if k == "vote" or _TOP_OFFICE.search(t) else 2
    if k == "court":
        return 3 if "judgment" in t.lower() or "advisory" in t.lower() else 2
    if k == "commodity_report":
        return 1 if i.source.startswith("eia_") else 2
    if k == "launch":
        return 2 if _BIG_LAUNCH.search(t) else 1
    if k in ("conference", "earnings", "opec", "regulation", "deadline"):
        return 2
    return 1                                                    # security_council, market_resolves


def importance(i: CalendarItem, hot: set[str] | None = None) -> int:
    n = base(i)
    if hot and (hot & (set(i.theaters) | set(i.situations))):
        n += 1
    return min(2 if i.grade == "unconfirmed" else 3, n)


def hot_theaters(top: int = HOT_TOP) -> set[str]:
    """Ids of the ``top`` hottest theaters on the latest desk board. Never raises: without a board nothing is hot."""
    try:
        from algent_backend.agent_system.agents.intel import desk

        board = desk.latest_board() or {}
        heat = sorted(board.get("heat") or [], key=lambda h: -float(h.get("heat") or 0))
        return {str(h["theater_id"]) for h in heat[:top] if h.get("theater_id") and float(h.get("heat") or 0) > 0}
    except Exception:  # noqa: BLE001 - ranking is an addition; the calendar must publish without it
        return set()
