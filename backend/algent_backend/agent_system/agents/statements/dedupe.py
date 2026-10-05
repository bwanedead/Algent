"""
Same statement, two sources: when a leader's own text and a news report of it both reach the ledger,
the primary stands and the report is shadowed. Mechanical only — no judgement about meaning:
the same speaker, within a day of each other, saying near-identical words (a shared verbatim quote, or
mostly the same content words in the paraphrase).

Used on write (``store.append_statements`` skips a statement an existing one already covers) and on
read (``store.query`` hides a secondary a primary has since covered, since the ledger is append-only).
"""

from __future__ import annotations

import re
from datetime import date, timedelta

from .contracts import Statement

SIMILARITY = 0.5            # share of content words in common (Jaccard) that makes two paraphrases "the same"
_MIN_WORD = 4               # shorter words are mostly function words in the languages we meet
_DAY_SLACK = 1              # a report filed after midnight, or in another timezone, dates a day off


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"\w+", text.casefold()) if len(w) >= _MIN_WORD}


def _day(s: Statement) -> date | None:
    try:
        return date.fromisoformat(s.date)
    except ValueError:
        return None


def _same_speaker(a: str, b: str) -> bool:
    ta, tb = set(re.findall(r"\w+", a.casefold())), set(re.findall(r"\w+", b.casefold()))
    return bool(ta and tb and (ta <= tb or tb <= ta))


def _text(s: Statement) -> str:
    return f"{s.quote} {s.paraphrase}"


def same_statement(a: Statement, b: Statement) -> bool:
    """True when ``a`` and ``b`` are the same person saying the same thing on (nearly) the same day."""
    da, db = _day(a), _day(b)
    if da is None or db is None or abs((da - db).days) > _DAY_SLACK or not _same_speaker(a.speaker, b.speaker):
        return False
    qa, qb = " ".join(a.quote.casefold().split()), " ".join(b.quote.casefold().split())
    if qa and qb and (qa in qb or qb in qa):
        return True
    wa, wb = _words(_text(a)), _words(_text(b))
    return bool(wa and wb and len(wa & wb) / len(wa | wb) >= SIMILARITY)


def covered_by(candidate: Statement, existing: list[Statement]) -> Statement | None:
    """The statement already on file that makes ``candidate`` redundant, if any. A primary is only ever
    covered by its own id (two primaries are two records); a secondary is also covered by a primary or by
    an earlier secondary that says the same."""
    for e in existing:
        if e.id == candidate.id:
            return e
        if candidate.source_kind == "secondary" and same_statement(candidate, e):
            return e
    return None


def visible(rows: list[Statement]) -> list[Statement]:
    """``rows`` without the secondaries a primary covers (and repeats among secondaries), order kept."""
    if all(r.source_kind == "primary" for r in rows):
        return rows
    by_day: dict[str, list[Statement]] = {}              # primaries bucketed by date: only neighbours are compared
    for r in rows:
        if r.source_kind == "primary":
            by_day.setdefault(r.date, []).append(r)
    kept: list[Statement] = []
    seen_secondary: list[Statement] = []
    for r in rows:
        if r.source_kind == "primary":
            kept.append(r)
            continue
        d = _day(r)
        near = [p for k in (d + timedelta(days=i) for i in range(-_DAY_SLACK, _DAY_SLACK + 1))
                for p in by_day.get(k.isoformat(), [])] if d else []
        if covered_by(r, near) is None and covered_by(r, seen_secondary) is None:
            seen_secondary.append(r)
            kept.append(r)
    return kept
