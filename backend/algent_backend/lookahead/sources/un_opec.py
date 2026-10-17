"""
UN Security Council meetings and OPEC+ meetings.

* UNSC: the Council's own "Programme of Work" page (main.un.org) embeds its calendar events as JSON in the HTML. The site sits
  behind a bot-challenge firewall that sometimes answers with an empty "202": that is reported as the source being unavailable
  (we do not try to get around it) and the previous items stay. Numbered Council meetings only, one item per day and topic.
* OPEC+: opec.org's press releases announce "the next meeting of the JMMC is scheduled for <date>"; the home page links the
  latest releases, which are scanned for that sentence. Medium confidence (a press-release sentence, not a schedule).
"""

from __future__ import annotations

import re
from datetime import date

from algent_backend import polite_http
from algent_backend.actors import names as cnames

from ..contracts import CalendarItem, make
from . import iso, inside, month_no, text_lines

UNSC_URL = "https://main.un.org/securitycouncil/en/content/programme-work"
UN_BASE = "https://main.un.org"
OPEC_URL = "https://www.opec.org/"

_EVENT = re.compile(r'"title":"(.*?)","id":"[^"]*","eid":"[^"]*","url":"([^"]*)",'
                    r'"des":"[^"]*","editable":false,"start":"(\d{4}-\d\d-\d\d)T')
_MEETING = re.compile(r"^\d+(?:st|nd|rd|th)(?:\s*\(resumed\))?\s+meeting\s*-\s*(.+)$", re.I)


def _countries_in(topic: str) -> list[str]:
    found = []
    for part in re.split(r"[,:/;]| and | - ", topic):
        c = cnames.iso2(part.strip())
        if c:
            found.append(c)
    return found


def parse_unsc(html: str) -> list[CalendarItem]:
    s = html.replace("\\u0022", '"').replace("\\u003C", "<").replace("\\u003E", ">").replace("\\/", "/").replace("\\", "")
    out: dict[tuple[str, str], CalendarItem] = {}
    for m in _EVENT.finditer(s):
        title = re.sub(r"<[^>]+>", "", re.sub(r"<div[^>]*>[^<]*</div>", "", m.group(1))).strip()
        mt = _MEETING.match(title)
        if not mt:
            continue
        topic = " ".join(mt.group(1).split())
        out.setdefault((m.group(3), topic.casefold()), make(
            "security_council", "unsc", m.group(3), f"UN Security Council: {topic}", UN_BASE + m.group(2),
            countries=_countries_in(topic)))
    return list(out.values())


_NEXT = re.compile(r"next\s+(?:meeting|JMMC meeting|ONOMM)[^.]{0,120}?(?:scheduled|to be held|will (?:take place|be held)|set)\s*(?:for|on)?\s+"
                   r"(\d{1,2})\s+([A-Za-z]+)(?:\s+(\d{4}))?", re.I)
_BODY = re.compile(r"\b(JMMC|ONOMM|OPEC and non-OPEC Ministerial Meeting)\b")


def parse_opec_release(text: str, url: str, today: date) -> list[CalendarItem]:
    flat = " ".join(text.split())
    out = []
    for m in _NEXT.finditer(flat):
        mo = month_no(m.group(2))
        if not mo:
            continue
        year = int(m.group(3)) if m.group(3) else today.year
        day = iso(year, mo, int(m.group(1)))
        if day and day < today.isoformat() and not m.group(3):
            day = iso(year + 1, mo, int(m.group(1)))
        body = _BODY.search(flat[max(0, m.start() - 160): m.end()])
        out.append(make("opec", "opec", day, f"OPEC+ {('ministerial' if body and body.group(1) != 'JMMC' else 'JMMC')} meeting", url, confidence="medium"))
    return out


def fetch_unsc(today: date) -> list[CalendarItem]:
    html = polite_http.get(UNSC_URL)
    if "calendar-event-datetime" not in html:
        raise polite_http.SourceUnavailable(f"{UNSC_URL} returned a page without the calendar events (bot challenge or layout change)")
    return [i for i in parse_unsc(html) if inside(i.date, today)]


def fetch_opec(today: date) -> list[CalendarItem]:
    home = polite_http.get(OPEC_URL, system_trust=True)
    links = list(dict.fromkeys(re.findall(r'href="\.?/?(pr-detail/[^"]+)"', home)))[:4]
    items: list[CalendarItem] = []
    for rel in links:
        url = f"{OPEC_URL}{rel}"
        try:
            items += parse_opec_release("\n".join(text_lines(polite_http.get(url, system_trust=True))), url, today)
        except polite_http.SourceError:
            continue
    return [i for i in items if inside(i.date, today)]
