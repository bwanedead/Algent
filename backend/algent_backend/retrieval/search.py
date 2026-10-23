"""
``Index``: build once per run, query many times. Lexical (BM25 with a mild recency lift) always; when an embedder is available the dense
ranking is fused with it by reciprocal rank. Profile claims come from the research corpus's own ranker and are appended (they are a different
kind of thing: graded facts with provenance, not dated reports), under their own cap.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any
from collections.abc import Callable

from . import corpus_backend, docs, embed, flags
from .docs import Doc
from .lexical import BM25


@dataclass(frozen=True)
class Hit:
    id: str
    kind: str
    date: str
    title: str
    text: str
    score: float

    def block(self) -> str:
        """One citable line group: ``[id] date title`` then the (clipped) text."""
        return f"[{self.id}] {self.date} {self.title}\n  {docs.clip(self.text, flags.HIT_CHARS)}"


def _recency(doc_date: str, today: date) -> float:
    try:
        age = (today - date.fromisoformat(doc_date)).days
    except ValueError:
        return 1.0
    if age < 0:
        return 1.0
    return 1 - flags.RECENCY_WEIGHT + flags.RECENCY_WEIGHT * 0.5 ** (age / flags.RECENCY_HALF_LIFE_DAYS)


class Index:
    def __init__(self, documents: list[Doc], *, today: date, embedder: embed.CachedEmbedder | None = None, claims: bool = True,
                 ranker: Callable[[str], list[int]] | None = None) -> None:
        self.docs, self.today, self.embedder, self.claims = documents, today, embedder, claims
        self.ranker = ranker                      # the corpus index's full-text ranking (doc indices, best first); None = in-process BM25
        self.bm25 = BM25(documents) if ranker is None else None
        self.vecs: list[list[float]] | None = None
        if embedder is not None and documents:
            try:
                self.vecs = embedder.encode([f"{d.title}. {d.text}"[:flags.EMBED_MAX_CHARS] for d in documents])
            except Exception:  # noqa: BLE001 - a failing dense side must not take retrieval down
                self.embedder, self.vecs = None, None

    @classmethod
    def build(cls, today: date, *, embedder: Any = "auto", claims: bool = True) -> Index:
        """The index over everything the desk holds as of ``today``. ``embedder="auto"`` follows ``flags.EMBEDDINGS_ENABLED``."""
        emb = embed.load() if embedder == "auto" else embedder
        backed = corpus_backend.load(today)
        if backed is not None:
            return cls(backed[0], today=today, embedder=emb, claims=claims, ranker=backed[1])
        return cls(docs.load_all(today), today=today, embedder=emb, claims=claims)

    # ── ranking ─────────────────────────────────────────────────────────────────────────────────
    def _lexical(self, query: str) -> list[int]:
        if self.ranker is not None:
            order = self.ranker(query)
            return sorted(order, key=lambda i: -(1.0 / (order.index(i) + 1)) * _recency(self.docs[i].date, self.today))
        s = self.bm25.scores(query)
        order = [i for i in range(len(s)) if s[i] > 0]
        return sorted(order, key=lambda i: -s[i] * _recency(self.docs[i].date, self.today))

    def _dense(self, query: str) -> list[int]:
        if self.embedder is None or self.vecs is None:
            return []
        try:
            q = self.embedder.encode([query[:flags.EMBED_MAX_CHARS]], query=True)[0]
        except Exception:  # noqa: BLE001
            return []
        sims = [sum(a * b for a, b in zip(q, v, strict=False)) for v in self.vecs]
        return sorted(range(len(sims)), key=lambda i: -sims[i] * _recency(self.docs[i].date, self.today))

    def search(self, query: str, *, k: int = flags.DEFAULT_K, kinds: set[str] | None = None,
               exclude: set[str] | frozenset[str] = frozenset()) -> list[Hit]:
        ranked = [[i for i in r if (kinds is None or self.docs[i].kind in kinds) and self.docs[i].id not in exclude]
                  for r in (self._lexical(query), self._dense(query))]
        fused: dict[int, float] = {}
        for r in ranked:
            for rank, i in enumerate(r):
                fused[i] = fused.get(i, 0.0) + 1.0 / (flags.RRF_K + rank + 1)
        top = sorted(fused, key=lambda i: (-fused[i], self.docs[i].id))[:k]
        hits = [Hit(d.id, d.kind, d.date, d.title, d.text, round(fused[i], 5)) for i in top for d in [self.docs[i]]]
        if self.claims and (kinds is None or "claim" in kinds):
            hits += [h for h in self._claims(query) if h.id not in exclude]
        return hits

    def _claims(self, query: str) -> list[Hit]:
        try:
            from algent_backend.agent_system.agents.research.corpus import related
            from algent_backend.agent_system.agents.research.store import JsonProfileStore

            found = related(JsonProfileStore(), query_text=query, as_of=self.today.isoformat(), limit=6)
        except Exception:  # noqa: BLE001
            return []
        return [Hit(f"claim:{c.claim_id}", "claim", c.date, f"profile {c.profile_id} [{c.grade}]", c.text, round(c.score, 5))
                for c in found.claims[:flags.CLAIMS_K]]
