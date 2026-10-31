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
from typing import Any
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
    acquired_known = False                  # true only after ``candidates`` found the acquisition ledger holding EVERY candidate unit (see ``n_acquired``)

    def __init__(self, db: Path | str, limit: int = 4000, ledger: dict[Any, dict[str, Any]] | None = None):
        self.db, self.limit, self._ledger = Path(db), limit, ledger
        self.n_acquired = 0

    def candidates(self, cutoff: str) -> Iterable[Evidence]:
        """Acquired time comes from the acquisition ledger (never from the index's own ``ingested_at``, which a rebuild resets): a document whose unit and content
        fingerprint the ledger holds gets that first-seen time; any other document has an unknown acquired time, which the manifest says."""
        from algent_backend.acquisition import store as acq

        ledger = acq.load() if self._ledger is None else self._ledger
        con = sqlite3.connect(f"file:{self.db.as_posix()}?mode=ro", uri=True)
        try:
            try:
                rows = con.execute("SELECT d.id, d.kind, d.product, d.title, d.body, d.date, d.origin, s.fingerprint, d.url FROM documents d LEFT JOIN ingest_state s ON s.unit = d.origin "
                                   "WHERE d.date != '' AND d.date <= ? ORDER BY d.date DESC LIMIT ?", (cutoff[:10], self.limit)).fetchall()
            except sqlite3.OperationalError:              # an index without provenance tables: no unit to look up
                rows = [(*r, "", "", "") for r in con.execute("SELECT id, kind, product, title, body, date FROM documents WHERE date != '' AND date <= ? ORDER BY date DESC LIMIT ?",
                                                          (cutoff[:10], self.limit))]
        finally:
            con.close()
        out = [Evidence(id=r[0], kind=r[1], source=f"{r[2]}/{r[1]}", title=r[3], body=r[4], event_time=r[5], publish_time=r[5],
                        acquired_at=acq.acquired_at(ledger.get((r[6], r[7]))), url=r[8], content_hash=store.digest(r[4])) for r in rows]
        self.n_acquired = sum(1 for e in out if e.acquired_at)
        self.acquired_known = bool(out) and self.n_acquired == len(out)
        return out


def market_as_of(market_id: str, cutoff: str) -> tuple[Any, dict[str, Any]]:
    """The market as it was stored at the cutoff: the newest revision whose ``updated_at`` is at or before it. The markets store keeps every revision, but
    ``markets()`` returns the last one, which may carry rules text, a corrected end date or a resolution note added AFTER the cutoff (a leak into the prompt).
    When no revision predates the cutoff (the market was first stored later, e.g. a history backfill) the earliest one is used and ``proven`` is False: the
    rules text cannot be shown to be pre-cutoff, and the audit says so."""
    from algent_backend.markets import store as ms

    revs = ms.market_revisions(market_id)
    if not revs:
        raise KeyError(f"market {market_id} is not in the markets store")
    c = store.parse_time(cutoff)
    known = [m for m in revs if (t := store.parse_time(m.updated_at)) is not None and c is not None and t <= c]
    chosen = known[-1] if known else revs[0]
    return chosen, {"rev_updated_at": chosen.updated_at, "n_revisions": len(revs), "proven_pre_cutoff": bool(known), "differs_from_latest": _text(chosen) != _text(revs[-1])}


def _text(m: Any) -> tuple[str, str, str]:
    return (m.question, m.description, m.end_date)


def question_from_market(market_id: str, cutoff: str) -> Question:
    """A question from a market already in the markets store, read AS OF the cutoff (``market_as_of``). The cutoff must precede its resolution; the price at the
    cutoff is kept as a reference the protocols never see."""
    from algent_backend.markets import store as ms

    m, rev = market_as_of(market_id, cutoff)
    latest = ms.markets()[market_id]
    c, res = store.parse_time(cutoff), store.parse_time(latest.resolved_at)
    if c is None or (res is not None and c >= res):
        raise ValueError("the cutoff must be a valid instant before the market resolved")
    snap = ms.price_at(sorted(ms.snapshots(market_id), key=lambda s: s.at), cutoff)      # price_at wants time order; a history backfill is appended after live rows
    qid = f"market-{market_id}-{cutoff[:10]}" + (f"-r{store.digest(m.updated_at)[:4]}" if rev["differs_from_latest"] else "")   # a corrected text is a NEW question id: old stored ones stay as they were
    return Question(id=qid, text=m.question, rules=m.description, cutoff=cutoff, closes_at=m.end_date, source=f"market:{market_id}",
                    category="historical" if latest.status != "open" else "live",
                    hints={"countries": list(m.countries), "theaters": list(m.theaters)}, reference={"market_p": snap.p if snap else None, "market_p_at": snap.at if snap else "", "market_rev": rev})
