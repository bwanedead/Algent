"""
Which countries a daily's sections and developments name, and what theme each reads as: the one walker behind the globe's map fill and the country
panel's brief history, so a dot in the panel can never disagree with the colour the map gave the country.

This is ``lib/globe-mentions.ts`` moved to the server. A section names the states its Pulses and numbers name; a development names its actors that
resolve to a state and the country of its validated place. ``text`` is raw (the writer's headline, else the start of the bottom line): the site cuts
it to a line with ``claimOf`` as it always did.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from algent_backend.actors import names as country_names

from . import dailies, themes

BASE = "/daily/geopolitics"
_ISO = re.compile(r"^[A-Z]{2}$")


@dataclass(frozen=True)
class Mention:
    kind: str                 # "section" | "development"
    isos: tuple[str, ...]
    theme: str
    base: float
    text: str
    date: str
    t_ms: float               # when the report was built: the recency clock
    href: str


def iso_of(name: str) -> str | None:
    return country_names.iso2(name)


def report_ms(report: dict[str, Any], date: str) -> float:
    built = themes.ms(str(report.get("built_at") or ""))
    return built if built is not None else (themes.ms(f"{date}T12:00:00Z") or 0.0)


def daily_mentions(report: dict[str, Any], date: str, dates: list[str]) -> list[Mention]:
    """Every section and development of one daily that names a country, in report order."""
    t_ms = report_ms(report, date)
    out: list[Mention] = []
    for i, t in dailies.sections(report):
        href = f"{dailies.day_href(BASE, date, dates)}#{dailies.anchor(str(t.get('theater_id') or t.get('name')), i)}"
        text = dailies.lead(t)
        named = {iso for iso in dailies.pulse_isos(t) + dailies.number_isos(t) if _ISO.match(iso)}
        theme, base = themes.theme_of(str(t["name"]), text)
        out.append(Mention("section", tuple(sorted(named)), theme, base, text, date, t_ms, href))
        for dev in dailies.objs(t.get("developments")):
            isos = {iso for a in dailies.strs(dev.get("actors")) if (iso := iso_of(a))}
            place = dev.get("place") if isinstance(dev.get("place"), dict) else {}
            if place.get("country") and (iso := iso_of(str(place["country"]))):
                isos.add(iso)
            detail = str(dev.get("detail") or "")
            dtheme, dbase = themes.theme_of(str(t["name"]), str(dev.get("headline") or ""), detail)
            line = " ".join(str(dev.get("headline") or "").split()) or dailies.clip(detail, 300)
            out.append(Mention("development", tuple(sorted(isos)), dtheme, dbase, line, date, t_ms, href))
    return out


def age_days(t_ms: float, now: datetime) -> float:
    return (now.timestamp() * 1000 - t_ms) / 86_400_000
