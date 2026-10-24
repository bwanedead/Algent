"""
EU AI Act milestones from the Future of Life Institute's AI Act implementation timeline (artificialintelligenceact.eu): each entry is a
date block followed by a text block that starts with a bold "<Who>:" label ("Application:", "Member States:", "Commission:"). The dates
are written into the Regulation, so they are official in substance; the page is a trusted transcription and the Commission has proposed
postponements before, hence ``announced``, not ``official``.
"""

from __future__ import annotations

import re
from datetime import date

from algent_backend import polite_http

from ..contracts import CalendarItem, make
from . import span_dates, upcoming

URL = "https://artificialintelligenceact.eu/implementation-timeline/"
_BLOCK = re.compile(r'<p>\s*(\d{1,2} [A-Za-z]+ \d{4})\s*</p>\s*</div>.*?<div class="et_pb_text_inner">(.*?)</div>', re.S)


def _text(cell: str) -> str:
    import html as htmllib

    return " ".join(htmllib.unescape(re.sub(r"<[^>]+>", "", re.sub(r"<br\s*/?>", " ", cell))).split())


def parse(html: str) -> list[CalendarItem]:
    out: dict[str, CalendarItem] = {}
    for m in _BLOCK.finditer(html):
        day, _ = span_dates(m.group(1))
        text = _text(m.group(2))
        who, _, rest = text.partition(":")
        if not day or not rest.strip() or len(who) > 40:
            continue
        what = re.split(r"[.;(,]", rest.strip())[0].strip()
        it = make("regulation", "ai_act", day, f"EU AI Act, {who.strip().lower()}: {what}", URL, countries=["EU"], confidence="medium")
        out[it.id] = it
    return list(out.values())


def fetch(today: date) -> list[CalendarItem]:
    return upcoming(parse(polite_http.get(URL)), today)
