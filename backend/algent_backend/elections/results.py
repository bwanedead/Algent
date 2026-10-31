"""
The results table of an election's own page: party or candidate, votes, percent, seats, and whether the page calls the figures official or preliminary.

The table is the first one under a "Results" heading with a votes (or seats) column and at least two named rows; failing that, the best-scoring table of the
page. Rows named total / valid / invalid / turnout go to ``totals``. Status is read from the words around the table (the section's lead-in, the table's own
footnotes): "preliminary / provisional / partial / unofficial" or "official / final / certified"; if the page says neither it is ``unstated``, never guessed.
"""

from __future__ import annotations

import re

from . import flags, wikitext
from .contracts import ResultRow, Results

_NAME = re.compile(r"party|candidate|alliance|list|coalition|bloc|ticket|name|choice|option|response", re.I)
_VOTES = re.compile(r"votes?\b", re.I)
_PCT = re.compile(r"%|percent|share", re.I)
_SEATS = re.compile(r"seats?|won|elected", re.I)
_TOTAL = re.compile(r"^(total|valid|invalid|blank|registered|turnout|votes? cast|electorate|spoil\w*|void)\b", re.I)
_PRELIM = re.compile(r"\b(preliminary|provisional|partial|unofficial|incomplete|\d+(?:\.\d+)?\s*%\s+of (?:the )?(?:votes|polling stations|precincts)\s+(?:counted|reported))", re.I)
_OFFICIAL = re.compile(r"\b(official|final|certified|confirmed)\b[^.|]{0,40}\b(results?|count|tally|figures)\b|\b(results?|count)\b[^.|]{0,30}\b(certified|official|final)\b", re.I)
_WIDE = 700


def _int(text: str) -> int | None:
    m = re.search(r"\d{1,3}(?:[ ,. ]\d{3})+|\d+", text)
    return int(re.sub(r"\D", "", m.group(0))) if m and not text.strip().startswith("<") else None


def _pct(text: str) -> float | None:
    m = re.search(r"(\d+)(?:[.,](\d+))?", text)
    if not m or text.strip().startswith("<"):
        return None
    v = float(f"{m.group(1)}.{m.group(2)}") if m.group(2) else float(m.group(1))
    return v if v <= 100 else None


def status_of(context: str) -> tuple[str, str]:
    """('official' | 'preliminary' | 'unstated', the words that say so). Preliminary wins a tie: the more careful reading."""
    if (m := _PRELIM.search(context)):
        return "preliminary", m.group(0)[:100]
    if (m := _OFFICIAL.search(context)):
        return "official", m.group(0)[:100]
    return "unstated", ""


def _columns(names: list[str]) -> dict[str, int]:
    cols: dict[str, int] = {}
    seats = [i for i, n in enumerate(names) if _SEATS.search(n) and not _VOTES.search(n) and not re.search(r"[±+Δ]|change|gain|loss", n, re.I)]
    for i, n in enumerate(names):
        if i in seats:
            continue
        if _PCT.search(n):
            cols.setdefault("percent", i)
        elif _VOTES.search(n):
            cols.setdefault("votes", i)
        elif _NAME.search(n) and not (i and names[i - 1] == n):            # a header spanning two columns names the first
            cols.setdefault("party" if "name" in cols else "name", i)
    if seats:
        cols["seats"] = next((i for i in seats if "total" in names[i].lower()), seats[-1])
    return cols


def _read(t: wikitext.Table) -> tuple[list[ResultRow], dict[str, float]] | None:
    g = wikitext.grid(t.rows)
    n = wikitext.header_rows(g)
    names = wikitext.column_names(g, n)
    if any(re.search(r"fieldwork|polling firm|pollster", x, re.I) for x in names):
        return None                                                  # a poll table
    cols = _columns(names)
    if "votes" not in cols and "seats" not in cols:
        return None
    rows: list[ResultRow] = []
    totals: dict[str, float] = {}
    for r in g[n:]:
        cells = [c.text for c in r]
        if len(set(id(c) for c in r)) == 1:
            continue
        at = lambda k: cells[cols[k]] if k in cols and cols[k] < len(cells) else ""   # noqa: E731
        name = at("name") or next((c for c in cells if c and not re.fullmatch(r"[\d.,%\s±+-]+", c)), "")
        if not name:
            continue
        votes, pct = _int(at("votes")), _pct(at("percent"))
        seats = _int(at("seats"))
        seats = seats if seats is not None and seats < _WIDE * 2 else None
        if _TOTAL.match(name):
            val = votes if votes is not None else pct if pct is not None else seats
            if val is not None:
                totals[name.lower()[:30]] = float(val)
            continue
        if votes is None and pct is None and seats is None:
            continue
        rows.append(ResultRow(name=name[:80], party=at("party")[:60], votes=votes, percent=pct, seats=seats))
    return (rows[:flags.MAX_RESULT_ROWS], totals) if len(rows) >= 2 else None


def extract(page: str) -> Results | None:
    """The results of the page, or None when it shows none (an election not yet held)."""
    best: tuple[int, wikitext.Table, list[ResultRow], dict[str, float]] | None = None
    for t in wikitext.tables(page):
        got = _read(t)
        if got is None:
            continue
        score = len(got[0]) + (50 if re.search(r"result", t.heading, re.I) else 0) + (3 if any(r.votes and r.seats is not None for r in got[0]) else 0)
        if best is None or score > best[0]:
            best = (score, t, *got)
    if best is None:
        return None
    _, t, rows, totals = best
    context = page[max(0, t.start - 700):t.start] + page[t.end:t.end + 400] + " " + t.caption + " " + " ".join(c.text for r in t.rows[-3:] for c in r[:1])
    status, note = status_of(context)
    return Results(heading=t.heading or t.caption, status=status, status_note=note, rows=rows, totals=totals)
