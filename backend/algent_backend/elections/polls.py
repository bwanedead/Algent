"""
Opinion-polling tables from an "Opinion polling for the <election>" page.

A poll table is recognised by its header: a pollster column and a fieldwork-date column, then one column per party or candidate. Columns that are numbers but
not a party (undecided, others, lead) are kept apart in ``Poll.others`` and never enter the average. Seats or percent is read from the section heading, else
from the row: whole numbers adding up to more than 100 are seats. A row whose date or shares cannot be read is kept as raw cells (``uncertain``), never guessed.

The recent average (``average``): per party, the mean over the newest ``flags.AVERAGE_LAST_N`` polls of the table that carry it and have a readable date.
"""

from __future__ import annotations

import re
from datetime import date

from algent_backend.lookahead.sources import span_dates

from . import flags, wikitext
from .contracts import Poll, PollAverage, PollTable

_POLLSTER = re.compile(r"firm|pollster|agency|organi[sz]|institute|poll source|^source|commissioner|conducted by|^polling$|^poll$|^polling\b", re.I)
_DATE = re.compile(r"date|fieldwork|period|conducted|field", re.I)
_SAMPLE = re.compile(r"sample|^n$|size", re.I)
_OTHER = re.compile(r"^(others?|oth\.?|undecided|don.?t know|lead|margin|abst\w*|none|refused|blank|not voting|unsure|will not vote|no answer|turnout|ref\.?|und\.?)\b", re.I)
_SEATS_HEAD = re.compile(r"seat", re.I)
_YEAR = re.compile(r"\b(19|20)\d{2}\b")
_NUM = re.compile(r"(\d{1,3}(?:[ ,]\d{3})+|\d+)(?:[.,](\d{1,2}))?")


def number(text: str) -> float | None:
    """The first figure in a cell ("32.5", "32,5 %", "31 seats"), None for a dash, a "<1" or no figure. Thousands separators are not shares."""
    t = text.strip()
    if not t or t.startswith(("<", ">", "~<")) or t in ("-", "–", "—", "N/A", "n/a", "?"):
        return None
    m = _NUM.search(t)
    if not m:
        return None
    whole = m.group(1).replace(",", "").replace(" ", "")
    v = float(f"{whole}.{m.group(2)}") if m.group(2) else float(whole)
    return v if v <= 700 else None


def _sample(text: str) -> int | None:
    m = re.search(r"\d{1,3}(?:[ ,.]\d{3})+|\d+", text)
    n = int(re.sub(r"\D", "", m.group(0))) if m else 0
    return n if 50 <= n <= 1_000_000 else None


def _day(text: str, year: int) -> tuple[str, int]:
    """(ISO day the fieldwork ended, the year to carry on). The year is read from the text, else the carried one is added."""
    t = text.replace("–", "-").replace("—", "-")
    for cand in (t, f"{t} {year}"):
        first, last = span_dates(cand)
        if first:
            d = last or first
            return d, int(d[:4])
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", t.strip()):
        return t.strip(), int(t[:4])
    return "", year


def _roles(names: list[str]) -> tuple[dict[str, int], list[tuple[int, str]]]:
    """Which column is the pollster, the date, the sample; and the rest as (index, name) candidates for party columns."""
    roles: dict[str, int] = {}
    rest: list[tuple[int, str]] = []
    for i, n in enumerate(names):
        key = ""
        if _POLLSTER.search(n) and "pollster" not in roles:
            key = "pollster"
        elif _DATE.search(n) and "date" not in roles:
            key = "date"
        elif _SAMPLE.search(n) and "sample" not in roles:
            key = "sample"
        if key:
            roles[key] = i
        elif n.strip():
            rest.append((i, n.strip()))
    return roles, rest


def _poll_table(t: wikitext.Table, year: int) -> tuple[list[Poll], str] | None:
    g = wikitext.grid(t.rows)
    n = wikitext.header_rows(g)
    names = wikitext.column_names(g, n)
    roles, rest = _roles(names)
    if "pollster" not in roles or "date" not in roles:
        return None
    meta = {i: nm for i, nm in rest if _OTHER.match(nm)}
    parties = {i: nm for i, nm in rest if i not in meta}
    if len(parties) < 2:
        return None
    polls: list[Poll] = []
    seats_heading = bool(_SEATS_HEAD.search(f"{t.heading} {t.caption}"))
    for row in g[n:]:
        cells = [c.text for c in row]
        if len(set(id(c) for c in row)) == 1:                      # a band across the table: a year heading, or a note
            m = _YEAR.search(cells[0] if cells else "")
            year = int(m.group(0)) if m and len(cells[0]) <= 12 else year
            continue
        cell = lambda i: cells[i] if i < len(cells) else ""        # noqa: E731
        pollster = cell(roles["pollster"])
        if not pollster or re.search(r"election|results?$", pollster, re.I):   # the previous election's own result row sits in the table
            continue
        fieldwork = cell(roles["date"])
        day, year = _day(fieldwork, year)
        shares = {nm: v for i, nm in parties.items() if (v := number(cell(i))) is not None}
        others = {nm: v for i, nm in meta.items() if (v := number(cell(i))) is not None}
        total = sum(shares.values())
        ints = all(float(v).is_integer() for v in shares.values())
        unit = "seats" if seats_heading or (ints and total > 105) else "percent"
        ok = bool(day) and len(shares) >= flags.MIN_SHARES and (unit == "seats" or total <= 105)
        polls.append(Poll(pollster=pollster, fieldwork=fieldwork, date=day, sample=_sample(cell(roles["sample"])) if "sample" in roles else None, unit=unit,
                          shares=shares if ok else {}, others=others if ok else {}, uncertain=not ok, raw=[] if ok else [c for c in cells if c]))
    return (polls, "seats" if any(p.unit == "seats" for p in polls[:5]) else "percent") if polls else None


def average(polls: list[Poll], last_n: int = flags.AVERAGE_LAST_N) -> PollAverage | None:
    """Mean per party over the newest ``last_n`` readable polls (newest first by fieldwork end); None when there is none."""
    use = sorted((p for p in polls if not p.uncertain and p.date), key=lambda p: p.date, reverse=True)[:last_n]
    if not use:
        return None
    acc: dict[str, list[float]] = {}
    for p in use:
        for k, v in p.shares.items():
            acc.setdefault(k, []).append(v)
    return PollAverage(unit=use[0].unit, n_polls=len(use), first=use[-1].date, last=use[0].date, pollsters=list(dict.fromkeys(p.pollster for p in use)),
                       shares={k: round(sum(v) / len(v), 1) for k, v in acc.items()})


def extract(page: str, election_year: int | None = None) -> list[PollTable]:
    """The poll tables of a page: the ``MAX_TABLES`` with most polls, each with its newest ``MAX_POLLS_PER_TABLE`` polls and a recent average."""
    year = election_year or date.today().year
    out: list[PollTable] = []
    for t in wikitext.tables(page):
        got = _poll_table(t, year)
        if got is None:
            continue
        polls, unit = got
        polls = sorted(polls, key=lambda p: p.date or "0000", reverse=True)
        out.append(PollTable(heading=t.heading or t.caption, unit=unit, n_total=len(polls), polls=polls[:flags.MAX_POLLS_PER_TABLE], average=average(polls)))
    return sorted(out, key=lambda x: -x.n_total)[:flags.MAX_TABLES]
