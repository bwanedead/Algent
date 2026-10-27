"""
A cutoff-bounded view of the corpus index: the same query doors production's research uses (``entity``, ``about``, ``search``, ``timeline``, ``related``,
``series``), but a row comes back only if it was knowable at the cutoff. The view is built from the evidence snapshot (the documents visible at the
cutoff) plus the cutoff itself; whatever the real index would add is dropped at the door, so a buggy query or a lucky best match cannot import hindsight.

Rules (the access rules of ``access.py`` applied to corpus rows):
- a document is visible iff its id is in the snapshot;
- a derived row (claim, event) needs a known date <= cutoff AND, when it names a document, that document visible (derivation can import hindsight);
- an observation counts only if its timestamp <= cutoff;
- ``entity`` is REBUILT from bounded queries (counts, latest event, latest numbers, timeline), never passed through, because the stored profile's
  counts and "latest" are computed over the whole index; ``situations`` and ``relations`` are not time-indexed and are omitted;
- ``related`` (a co-occurrence score over the whole index) is not time-indexed and returns nothing: a stated difference from production, in ``dropped``.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from typing import Any

from . import store

_FETCH = 4          # over-fetch factor: rows are dropped after the query, so ask for more to still fill a page


class CutoffCorpus:
    def __init__(self, corpus: Any, visible_ids: Iterable[str], cutoff: str, ledger: dict[Any, dict[str, Any]] | None = None):
        self.corpus, self.visible, self.cutoff = corpus, set(visible_ids), cutoff
        self._ledger = ledger                            # the acquisition ledger (loaded on first need); decides whether a row with no source document was held by the cutoff
        self.unproven: Counter[str] = Counter()          # rows kept although nothing proves they predate the cutoff (audit only)
        self._t = store.parse_time(cutoff)
        if self._t is None:
            raise ValueError("a cutoff-bounded corpus needs a valid cutoff")
        self._day = cutoff[:10]
        self.dropped: Counter[str] = Counter()          # why rows were hidden (audit only; ids and bodies are never kept)

    # ── the row tests ────────────────────────────────────────────────────────────────────
    def _known_by_cutoff(self, when: Any) -> bool:
        t = store.parse_time(str(when or ""))
        return t is not None and t <= self._t

    def _claim_document(self, claim_id: str) -> str:
        """The document a claim was drawn from (search rows do not carry it); '' when the handle has no index (a test double) or the claim is unknown."""
        db = getattr(self.corpus, "db", None)
        try:
            r = db.execute("SELECT document_id FROM claims WHERE id = ?", (claim_id,)).fetchone() if db is not None else None
        except Exception:  # noqa: BLE001 - an unreadable index just means no extra check
            return ""
        return str(r[0] or "") if r else ""

    def _held_by_cutoff(self, table: str, row_id: str) -> bool:
        """False only when the ledger proves the unit holding this row first reached us AFTER the cutoff. An unknown acquisition time keeps the row but counts it as unproven."""
        from algent_backend.acquisition import store as acq

        db = getattr(self.corpus, "db", None)
        try:
            r = db.execute(f"SELECT s.fingerprint, t.origin FROM {table} t LEFT JOIN ingest_state s ON s.unit = t.origin WHERE t.id = ?", (row_id,)).fetchone() if db is not None else None
        except Exception:  # noqa: BLE001 - an index without provenance tables: nothing to look up
            r = None
        if self._ledger is None:
            self._ledger = acq.load()
        got = acq.acquired_at(self._ledger.get((r[1], r[0]))) if r else ""
        if not got:
            self.unproven[f"{table}-without-source-document-acquisition-unknown"] += 1
            return True
        t = store.parse_time(got)
        return t is not None and t <= self._t

    def _ok(self, row: dict[str, Any]) -> bool:
        kind, rid = row.get("type"), str(row.get("id", ""))
        if kind == "document":
            ok, reason = rid in self.visible, "document-not-in-snapshot"
        else:
            doc = str(row.get("document_id") or "") or (self._claim_document(rid) if kind == "claim" else "")
            when = (row.get("at") or row.get("created_at") or row.get("date")) if kind == "claim" else (row.get("date") or row.get("at"))
            ok, reason = self._known_by_cutoff(when) and (not doc or doc in self.visible), "derived-after-cutoff-or-source-hidden"
            if ok and not doc and kind in ("claim", "event"):          # no source document to test: the row's own date is only its EVENT time, so ask the acquisition ledger
                ok, reason = self._held_by_cutoff("claims" if kind == "claim" else "events", rid), "ungrounded-derived-row-acquired-after-cutoff"
        if not ok:
            self.dropped[reason] += 1
        return ok

    def _keep(self, rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
        return [r for r in rows if self._ok(r)]

    # ── the doors ────────────────────────────────────────────────────────────────────────
    def search(self, text: str, *, kinds: set[str] | None = None, since: str = "", limit: int = 20, **_: Any) -> list[dict[str, Any]]:
        return self._keep(self.corpus.search(text, kinds=kinds, since=since, until=self._day, limit=limit * _FETCH))[:limit]

    def about(self, ref: str, *, since: str = "", kinds: set[str] | None = None, limit: int = 20, **_: Any) -> dict[str, Any] | None:
        a = self.corpus.about(ref, since=since, until=self._day, kinds=kinds, limit=limit * _FETCH)
        if a is None:
            return None
        docs = [{**d, "type": "document"} for d in a.get("documents", [])]
        kept_docs = self._keep(docs)
        claims = self._keep([{**c, "type": "claim"} for c in a.get("claims", [])])
        events = self._keep([{**e, "type": "event"} for e in a.get("events", [])])
        return {**a, "documents": kept_docs[:limit], "claims": claims[:limit], "events": events[:limit]}

    def timeline(self, ref: str, *, since: str = "", kinds: set[str] | None = None, limit: int = 50, **_: Any) -> list[dict[str, Any]] | None:
        rows = self.corpus.timeline(ref, since=since, until=self._day, kinds=kinds, limit=limit * _FETCH)
        return None if rows is None else self._keep(rows)[-limit:]

    def series(self, ref: str, *, metric: str = "", since: str = "", points: bool = True, limit: int = 40, **_: Any) -> list[dict[str, Any]]:
        out = []
        for s in self.corpus.series(ref, metric=metric, since=since, until=self._day, points=True, limit=limit):
            pts = [p for p in (s.get("points") or []) if self._known_by_cutoff(p[0])]
            if not pts:
                self.dropped["series-without-points-before-cutoff"] += 1
                continue
            last = pts[-1]
            out.append({**s, "points": pts if points else [], "n": len(pts), "first": pts[0][0], "last": last[0], "latest": {"ts": last[0], "value": last[1]}})
        return out

    def related(self, ref: str, *, limit: int = 15, **_: Any) -> list[dict[str, Any]]:
        self.dropped["related-not-time-indexed"] += 1
        return []

    def entity(self, ref: str) -> dict[str, Any] | None:
        prof = self.corpus.entity(ref)
        if not prof:
            return None
        eid = prof["entity"]["id"]
        a = self.about(eid, limit=200) or {"documents": [], "claims": [], "events": []}
        events = sorted(a["events"], key=lambda e: (str(e.get("date", "")), str(e.get("id", ""))))
        obs = [{"metric": s["metric"], "label": s.get("label", ""), "ts": s["latest"]["ts"], "value": s["latest"]["value"], "unit": s.get("unit", ""), "basis": s.get("basis", "")}
               for s in self.series(eid, limit=8)]
        tl = self.timeline(eid, limit=10) or []
        self.dropped["entity-situations-relations-omitted"] += 1
        return {"entity": prof["entity"], "counts": {"documents": len(a["documents"]), "claims": len(a["claims"]), "events": len(a["events"]), "series": len(obs)},
                "latest": {"event": events[-1] if events else None, "observations": obs}, "situations": [], "relations": [], "timeline": tl}
