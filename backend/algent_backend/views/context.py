"""
``ViewContext``: everything one build run reads, behind small typed accessors, so a builder never opens a file or a database itself and a test
hands it a few dictionaries. The accessors are the only place the staged documents' paths and shapes are spelled (``publishing/intel_page.py``
documents them); builders ask for "the newest geopolitics daily" or "the dossier of this theater".
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from . import flags
from .sources import Staged, Tables

DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
ISO = re.compile(r"^[A-Z]{2}$")


@dataclass
class ViewContext:
    staged: Staged
    tables: Tables = field(default_factory=Tables)
    corpus: Any = None                                  # corpus.Corpus | None
    now: datetime = field(default_factory=lambda: datetime.now(UTC))

    _memo: dict[str, Any] = field(default_factory=dict)

    # ── time ─────────────────────────────────────────────────────────────────────────────
    @property
    def today(self) -> str:
        return self.now.date().isoformat()

    def memo(self, key: str, compute: Any) -> Any:
        """A value several builders share (the theater-state graph, the actors' medians), computed once per run."""
        if key not in self._memo:
            self._memo[key] = compute()
        return self._memo[key]

    # ── dailies ──────────────────────────────────────────────────────────────────────────
    def domains(self) -> list[str]:
        """Every desk's domain that has dailies, in the registry's order (a domain nobody registered is not a desk)."""
        return [d["id"] for d in flags.DESKS if self.daily_dates(d["id"])]

    def daily_dates(self, domain: str) -> list[str]:
        """Dates with a daily for the domain, newest first."""
        key = f"daily_dates:{domain}"
        cached = self.staged._cache.get(key)             # noqa: SLF001 - one cache per run, owned by the staged source
        if cached is None:
            cached = sorted((n[:-5] for n in self.staged.names(f"daily/{domain}") if n.endswith(".json") and DATE.match(n[:-5])), reverse=True)
            self.staged._cache[key] = cached              # noqa: SLF001
        return cached

    def daily(self, domain: str, date: str) -> dict[str, Any] | None:
        doc = self.staged.get(f"daily/{domain}/{date}.json")
        return doc if isinstance(doc, dict) else None

    def scan_dailies(self, domain: str):
        """``(date, report)`` for every daily of the domain, newest first, each parsed and dropped (a pass over the whole archive in bounded memory)."""
        for d in self.daily_dates(domain):
            doc = self.staged.get(f"daily/{domain}/{d}.json", keep=False)
            if isinstance(doc, dict):
                yield d, doc

    def latest_daily(self, domain: str) -> dict[str, Any] | None:
        dates = self.daily_dates(domain)
        return self.daily(domain, dates[0]) if dates else None

    # ── theaters (situations) ─────────────────────────────────────────────────────────────
    def dossier_index(self) -> list[dict[str, Any]]:
        """Index rows of every theater that has a readable dossier (``theaters/index.json``)."""
        raw = self.staged.get("theaters/index.json")
        rows = raw.get("theaters") if isinstance(raw, dict) else None
        have = set(self.staged.slugs("theaters"))
        return [r for r in rows or [] if isinstance(r, dict) and r.get("theater_id") in have and r.get("theater_id") != "index"]

    def dossier(self, theater_id: str) -> dict[str, Any] | None:
        doc = self.staged.get(f"theaters/{theater_id}.json")
        return doc if isinstance(doc, dict) else None

    # ── the desk snapshot, actor pages, the record ────────────────────────────────────────
    def snapshot(self) -> dict[str, Any] | None:
        """The newest ``snapshots/<slug>.json`` (slugs are UTC ``YYYY-MM-DD-HHMM``, so the last sorts newest)."""
        slugs = self.staged.slugs("snapshots")
        doc = self.staged.get(f"snapshots/{slugs[-1]}.json") if slugs else None
        return doc if isinstance(doc, dict) else None

    def actor_isos(self) -> list[str]:
        return [s for s in self.staged.slugs("actors") if ISO.match(s)]

    def actor(self, iso: str) -> dict[str, Any] | None:
        doc = self.staged.get(f"actors/{iso}.json")
        return doc if isinstance(doc, dict) else None

    def record(self) -> dict[str, Any] | None:
        doc = self.staged.get("record.json")
        return doc if isinstance(doc, dict) else None

    # ── table-shaped products ─────────────────────────────────────────────────────────────
    def table(self, path: str) -> Any:
        return self.tables.get(path)

    def rows(self, path: str, key: str) -> list[dict[str, Any]]:
        doc = self.table(path)
        got = doc.get(key) if isinstance(doc, dict) else None
        return [r for r in got or [] if isinstance(r, dict)]


def open_context(*, with_corpus: bool = True, now: datetime | None = None) -> ViewContext:
    """The production context: the site checkouts on disk, each domain's own document builders, and the corpus index when one has been built."""
    from algent_backend.publishing import rebuild

    from .sources import TreeStaged, default_tables

    corpus = None
    if with_corpus:
        from algent_backend import corpus as index

        if index.available():
            corpus = index.Corpus.open()
    return ViewContext(staged=TreeStaged(rebuild.site_roots()), tables=default_tables(), corpus=corpus, now=now or datetime.now(UTC))
