"""
Central-bank rate-decision dates from the banks' own published schedules: the Federal Reserve (FOMC calendar page), the ECB
(Governing Council monetary-policy meetings, Day 2 with press conference) and the Bank of England (MPC dates page). Official
pages of public bodies; the dates are facts, cited by link.
"""

from __future__ import annotations

import re
from datetime import date

from algent_backend import polite_http

from ..contracts import CalendarItem, make
from . import iso, inside, month_no, text_lines

FED_URL = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"
ECB_URL = "https://www.ecb.europa.eu/press/calendars/mgcgc/html/index.en.html"
BOE_URL = "https://www.bankofengland.co.uk/monetary-policy/upcoming-mpc-dates"

_FED_HEAD = re.compile(r"(\d{4}) FOMC Meetings")
_FED_ROW = re.compile(r'fomc-meeting__month[^>]*>\s*<strong>([^<]+)</strong>.*?fomc-meeting__date[^>]*>\s*([\d]+)\s*[-–]\s*([\d]+)(\*?)', re.S)


def parse_fed(html: str) -> list[CalendarItem]:
    heads = list(_FED_HEAD.finditer(html))
    out = []
    for k, h in enumerate(heads):
        seg = html[h.end(): heads[k + 1].start() if k + 1 < len(heads) else len(html)]
        year = int(h.group(1))
        for m in _FED_ROW.finditer(seg):
            months = [month_no(x) for x in re.split(r"[/-]", m.group(1)) if x.strip()]
            last = months[-1] if months and months[-1] else None
            day = iso(year, last, int(m.group(3))) if last else ""
            if day:
                out.append(make("central_bank", "fed", day, "Fed rate decision with projections" if m.group(4) else "Fed rate decision (FOMC)",
                                FED_URL, countries=["US"]))
    return out


def parse_ecb(html: str) -> list[CalendarItem]:
    lines = text_lines(html)
    out = []
    for k, ln in enumerate(lines[:-1]):
        d = re.fullmatch(r"(\d{2})/(\d{2})/(\d{4})", ln)
        desc = lines[k + 1]
        if d and "monetary policy meeting" in desc and "followed by press conference" in desc:
            day = iso(int(d.group(3)), int(d.group(2)), int(d.group(1)))
            if day:
                out.append(make("central_bank", "ecb", day, "ECB rate decision", ECB_URL, countries=["EU"]))
    return out


def parse_boe(html: str) -> list[CalendarItem]:
    out = []
    for h in re.finditer(r"<h2>\s*(\d{4}) confirmed dates\s*</h2>(.*?)</table>", html, re.S):
        for m in re.finditer(r"<td>\s*[A-Za-z]+(?:&nbsp;|\s)+(\d{1,2})\s+([A-Za-z]+)\s*</td>", h.group(2)):
            mo = month_no(m.group(2))
            day = iso(int(h.group(1)), mo, int(m.group(1))) if mo else ""
            if day:
                out.append(make("central_bank", "boe", day, "Bank of England rate decision", BOE_URL, countries=["GB"]))
    return out


def _upcoming(items: list[CalendarItem], today: date) -> list[CalendarItem]:
    return [i for i in items if inside(i.date, today)]


def fetch_fed(today: date) -> list[CalendarItem]:
    return _upcoming(parse_fed(polite_http.get(FED_URL)), today)


def fetch_ecb(today: date) -> list[CalendarItem]:
    return _upcoming(parse_ecb(polite_http.get(ECB_URL, system_trust=True)), today)


def fetch_boe(today: date) -> list[CalendarItem]:
    return _upcoming(parse_boe(polite_http.get(BOE_URL)), today)
