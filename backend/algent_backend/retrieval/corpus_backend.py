"""
The corpus index as retrieval's backend: documents come from one indexed query per kind (same windows, same ids, same text as ``docs.py``) and the
lexical ranking is the index's full-text search. ``load`` returns None whenever the index is absent, empty or unreadable, and retrieval then runs its
own loaders and BM25 unchanged.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, timedelta

from . import flags
from .docs import Doc


def _windows(today: date):
    from algent_backend.corpus.query.retrieval import Window

    t = today.isoformat()

    def back(days: int) -> str:
        return (today - timedelta(days=days)).isoformat()

    return [Window("daily", back(flags.DAILY_DAYS), t, domain="geopolitics"),
            Window("statement", back(flags.STATEMENT_DAYS), t),
            Window("sanction", back(flags.SANCTION_DAYS), t, not_status="baseline"),
            Window("calendar", back(flags.CALENDAR_DAYS_BACK), (today + timedelta(days=flags.CALENDAR_DAYS_AHEAD)).isoformat(), status="active"),
            Window("geo", back(flags.GEO_DAYS), t)]


def load(today: date) -> tuple[list[Doc], Callable[[str], list[int]]] | None:
    if not flags.USE_CORPUS_INDEX:
        return None
    try:
        from algent_backend.corpus import Corpus, available

        if not available():
            return None
        corpus = Corpus.open()
        docs = [Doc(r["id"], r["kind"], r["date"], r["title"], r["text"]) for r in corpus.window_docs(_windows(today))]
    except Exception:  # noqa: BLE001 - no usable index: fall back to the record itself
        return None
    if not docs:
        corpus.close()
        return None
    at = {d.id: i for i, d in enumerate(docs)}

    def ranker(query: str) -> list[int]:
        try:
            return [at[i] for i in corpus.rank_documents(query) if i in at]
        except Exception:  # noqa: BLE001
            return []

    return docs, ranker
