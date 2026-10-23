"""
Reading a persisted daily (``ohmega.daily/1``, raw dictionaries) the way the site's pages do: which of its theaters are sections, where each one
anchors, how it is led, which countries it names. The site's ``lib/daily.ts`` parses the same documents for rendering; this module only *selects*
and *joins*, so it stays tolerant (a missing field is an empty one) and never normalises what the site will normalise again.
"""

from __future__ import annotations

import re
from typing import Any

from . import flags


def clip(text: Any, n: int) -> str:
    """Whitespace-collapsed text cut to ``n`` characters on a word boundary, with an ellipsis when cut."""
    t = " ".join(str(text or "").split())
    if len(t) <= n:
        return t
    cut = t[: n - 1]
    return (cut.rsplit(" ", 1)[0] if " " in cut[n // 2:] else cut).rstrip(" ,;:-") + "…"


def strs(v: Any) -> list[str]:
    return [str(x) for x in v if isinstance(x, (str, int, float)) and str(x)] if isinstance(v, list) else []


def objs(v: Any) -> list[dict[str, Any]]:
    return [x for x in v if isinstance(x, dict)] if isinstance(v, list) else []


def is_section(t: dict[str, Any]) -> bool:
    return t.get("kind") != "update"


def sections(report: dict[str, Any]) -> list[tuple[int, dict[str, Any]]]:
    """``(index in the report, theater)`` for every section (an "update" is a later part's addition nested under its section)."""
    return [(i, t) for i, t in enumerate(objs(report.get("theaters"))) if is_section(t) and t.get("name")]


def anchor(theater_id: str, i: int) -> str:
    """The in-page anchor of a section: ``theaterAnchor`` in lib/daily.ts."""
    return f"theater-{i}-{re.sub(r'[^a-z0-9]+', '-', theater_id.lower()).strip('-')}"


def day_href(base: str, date: str, dates: list[str]) -> str:
    """Where a day's report lives: the newest is the section root, the rest are ``/<base>/<date>``."""
    return base if dates and date == dates[0] else f"{base}/{date}"


def lead(t: dict[str, Any], n: int = 300) -> str:
    """The line a section leads with, as raw text for the site to cut with ``claimOf``: the writer's headline, else the start of the bottom line."""
    return " ".join(str(t.get("headline") or "").split()) or clip(t.get("bottom_line"), n)


def headline(report: dict[str, Any]) -> str:
    s = report.get("summary")
    return str(s.get("headline") or "") if isinstance(s, dict) else ""


def the_day(report: dict[str, Any]) -> list[str]:
    s = report.get("summary")
    return strs(s.get("the_day")) if isinstance(s, dict) else []


def desk_of_domain(domain: str) -> str:
    d = (domain or "").strip().lower()
    for desk in flags.DESKS:
        if d in desk["domains"]:
            return str(desk["id"])
    return next((str(x["id"]) for x in flags.DESKS if x["catch_all"]), str(flags.DESKS[0]["id"]))


def pulse_isos(t: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for p in objs(t.get("pulses")):
        out += [c.upper() for c in strs(p.get("actors_iso2")) if re.fullmatch(r"[A-Za-z]{2}", c)]
    return out


def number_isos(t: dict[str, Any]) -> list[str]:
    nums = t.get("numbers")
    return [str(a.get("iso2")).upper() for a in objs(nums.get("actors"))] if isinstance(nums, dict) else []
