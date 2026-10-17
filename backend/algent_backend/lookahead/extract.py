"""
Corpus extraction — upcoming dated items from Ohmega's own daily sections, mechanically (no model, no cost).

A sentence of a section (a development, what-to-watch, outlook) becomes a calendar item when it carries BOTH a trigger word
for something scheduled (deadline / expires / vote / summit / talks ...) AND an explicit calendar date that lies after the
daily's own date and inside the lookahead window. Relative dates ("next Tuesday") are ignored: without the writer's own
anchor they would be guesses. Items are ``low`` confidence, provenance ``ohmega_derived``, and link back to the theater and the
daily that said it; the source cited is the development's own first source when it has one, else the day's report page.

Countries come only from names the writer already chose on the development (``actors``, ``where``), never from scanning prose.
Forward-only: ``attach`` is called with each new daily and never re-reads old ones unless asked (``backfill``).
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Any

from algent_backend.actors import names as cnames

from . import store
from .contracts import CalendarItem, make, short
from .sources import HORIZON_DAYS, iso, month_no

REPORT_URL = "https://www.ohmega.monster/geopolitics/{date}"

_MONTH = r"(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|June?|July?|Aug(?:ust)?|Sept?(?:ember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\.?"
_DMY = re.compile(rf"\b(?:on |by |before |until |from )?(\d{{1,2}})(?:st|nd|rd|th)?\s+{_MONTH}(?:,?\s+(\d{{4}}))?\b")
_MDY = re.compile(rf"\b(?:on |by |before |until |from )?{_MONTH}\s+(\d{{1,2}})(?:st|nd|rd|th)?(?:,?\s+(\d{{4}}))?\b")
_SENT = re.compile(r"(?<=[.!?])\s+(?=[A-Z\"'(])")

#: kind -> trigger words. The first kind whose trigger the sentence carries wins (a deadline beats a vote beats a summit).
_TRIGGERS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("deadline", re.compile(r"\b(deadline|expires?|expiring|expiry|expiration|lapses?|runs? out|sunsets?|waiver ends|truce ends|ceasefire ends)\b", re.I)),
    ("vote", re.compile(r"\b(will vote|to vote|vote (?:on|is)|votes? (?:is |are )?(?:scheduled|due|expected)|referendum|ballot|plenary vote|vote scheduled)\b", re.I)),
    ("summit", re.compile(r"\b(summit|ministerial|talks (?:are |is )?(?:scheduled|due|set|planned)|will meet|to meet|meeting (?:is |are )?(?:scheduled|due|set|planned)|"
                          r"scheduled (?:to meet|for)|due to (?:meet|visit)|state visit|conference (?:on|in))\b", re.I)),
)
_LEAD = re.compile(r"^(?:according to [^,]{3,60},|[A-Z][\w .'-]{2,40} (?:said|says|announced|confirmed|warned|stated) (?:that )?)\s*", re.I)
_PAREN = re.compile(r"\s*[\(\[][^)\]]{0,120}[\)\]]")


def _find_date(sentence: str, today: date) -> tuple[str, str]:
    """(iso date, the matched text) of the first explicit date after ``today`` inside the window, else ("", "")."""
    hi = (today + timedelta(days=HORIZON_DAYS)).isoformat()
    for rx, dm in ((_DMY, (1, 2, 3)), (_MDY, (2, 1, 3))):
        for m in rx.finditer(sentence):
            mo, d, y = month_no(m.group(dm[1])), int(m.group(dm[0])), m.group(dm[2])
            if not mo:
                continue
            day = iso(int(y) if y else today.year, mo, d)
            if day and not y and day < today.isoformat():
                day = iso(today.year + 1, mo, d)                # "on 3 February" said in December means next year
            if day and today.isoformat() < day <= hi:
                return day, m.group(0)
    return "", ""


def title_of(sentence: str, matched: str) -> str:
    """A short label for the thing: the sentence without its date, brackets and leading attribution, cut to ten words."""
    t = _PAREN.sub("", sentence.replace(matched, " ")).strip(" .;,-")
    t = _LEAD.sub("", t)
    t = re.split(r"[;:]| — | – ", t)[0]
    t = re.sub(r"\s+(?:on|by|before|until|from|in)\s*$", "", t.strip(" ,"))
    return short(t[:1].upper() + t[1:])


def items_from_text(text: str, *, today: date, url: str, theater: str = "", via: str = "", countries: list[str] | None = None) -> list[CalendarItem]:
    out = []
    for sent in _SENT.split(" ".join((text or "").split())):
        kind = next((k for k, rx in _TRIGGERS if rx.search(sent)), None)
        if kind is None:
            continue
        day, matched = _find_date(sent, today)
        title = title_of(sent, matched) if day else ""
        if day and len(title.split()) >= 3:
            out.append(make(kind, "corpus", day, title, url, countries=countries, theaters=[theater] if theater else [],
                            confidence="low", provenance="ohmega_derived", via=via))
    return out


def _dev_countries(d: dict[str, Any]) -> list[str]:
    from algent_backend.actors import registry

    names = [*(d.get("actors") or []), d.get("where") or ""]
    return [c for c in dict.fromkeys(registry.resolve(n) for n in names if n) if c]


def from_section(section: dict[str, Any], as_of: str, *, today: date | None = None) -> list[CalendarItem]:
    today = today or date.fromisoformat(as_of)
    tid = section.get("theater_id", "")
    page = REPORT_URL.format(date=as_of)
    out: list[CalendarItem] = []
    via = f"daily:{as_of}:{tid}"
    for d in section.get("developments") or []:
        url = next(iter(d.get("sources") or []), page)
        out += items_from_text(f"{d.get('headline', '')}. {d.get('detail', '')}", today=today, url=url, theater=tid, via=via, countries=_dev_countries(d))
    for field in ("watch_next", "since_yesterday", "outlook"):
        val = section.get(field)
        for chunk in (val if isinstance(val, list) else [val]):
            out += items_from_text(str(chunk or ""), today=today, url=page, theater=tid, via=via)
    return list({i.id: i for i in out}.values())


def attach(sections: list[dict], *, as_of: str, today: date | None = None) -> dict[str, Any] | None:
    """Extract from a day's sections into the store (additive; never raises, never gates the day)."""
    try:
        day = today or date.fromisoformat(as_of)
        items = [i for s in sections for i in from_section(s, as_of, today=day)]
        res = store.sync("corpus", list({i.id: i for i in items}.values()), day, withdraw=False)
        return {"found": len(items), **res}
    except Exception as exc:  # noqa: BLE001
        return {"found": 0, "error": f"{type(exc).__name__}: {str(exc)[:160]}"}
