"""
Where evidence and questions come from. Read-only adapters over stores that already exist; nothing here writes to them.

``CorpusSource`` maps the corpus index's ``documents`` table onto L1: ``date`` is the publish time (a bare date counts as the end of that day), and
``ingested_at`` is the acquisition time. CAVEAT: the index is derived and a full rebuild resets ``ingested_at``, so for a HISTORICAL replay the acquisition
time is not trustworthy; the manifest records ``acquired_known`` so that fact stays visible (the real fix is the L1 acquisition ledger, phase 2).
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from pathlib import Path
from typing import Protocol as TypingProtocol

from . import store
from .contracts import Evidence, Question


class EvidenceSource(TypingProtocol):
    name: str
    acquired_known: bool

    def candidates(self, cutoff: str) -> Iterable[Evidence]: ...


class ListSource:
    """Evidence held in memory (tests, synthetic worlds)."""

    def __init__(self, items: Iterable[Evidence], name: str = "list", acquired_known: bool = True):
        self.items, self.name, self.acquired_known = list(items), name, acquired_known

    def candidates(self, cutoff: str) -> Iterable[Evidence]:
        return list(self.items)


class CorpusSource:
    """The corpus index (``corpus.db``), opened read-only. A coarse date pre-filter keeps the read small; the access gate still decides."""

    name = "corpus-index"
    acquired_known = False

    def __init__(self, db: Path | str, limit: int = 4000):
        self.db, self.limit = Path(db), limit

    def candidates(self, cutoff: str) -> Iterable[Evidence]:
        con = sqlite3.connect(f"file:{self.db.as_posix()}?mode=ro", uri=True)
        try:
            rows = con.execute("SELECT id, kind, product, title, body, date, ingested_at FROM documents WHERE date != '' AND date <= ? ORDER BY date DESC LIMIT ?",
                               (cutoff[:10], self.limit)).fetchall()
        finally:
            con.close()
        return [Evidence(id=r[0], kind=r[1], source=f"{r[2]}/{r[1]}", title=r[3], body=r[4], event_time=r[5], publish_time=r[5], acquired_at=r[6],
                         content_hash=store.digest(r[4])) for r in rows]


def question_from_market(market_id: str, cutoff: str) -> Question:
    """A question from a market already in the markets store. The cutoff must precede its resolution; the price at the cutoff is kept as a reference the
    protocols never see."""
    from algent_backend.markets import store as ms

    m = ms.markets().get(market_id)
    if m is None:
        raise KeyError(f"market {market_id} is not in the markets store")
    c, res = store.parse_time(cutoff), store.parse_time(m.resolved_at)
    if c is None or (res is not None and c >= res):
        raise ValueError("the cutoff must be a valid instant before the market resolved")
    snap = ms.price_at(ms.snapshots(market_id), cutoff)
    return Question(id=f"market-{market_id}-{cutoff[:10]}", text=m.question, rules=m.description, cutoff=cutoff, closes_at=m.end_date, source=f"market:{market_id}",
                    category="historical" if m.status != "open" else "live",
                    hints={"countries": list(m.countries), "theaters": list(m.theaters)}, reference={"market_p": snap.p if snap else None, "market_p_at": snap.at if snap else ""})
