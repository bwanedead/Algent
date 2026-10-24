"""
The research trace: one appended line per forecast or trade decision saying HOW it was researched (``contracts.Trace``). It is observability, not
the scored record: scoring reads the cited ids on the forecast and decision lines themselves, so traces can be pruned by age
(``store.prune_traces``) without touching a score.
"""

from __future__ import annotations

from .contracts import Trace, trace_id
from .research import Researched
from . import store


def build(kind: str, *, book: str, market_id: str, ref: str, at: str, res: Researched | None, mode: str, cited: list[str], evidence: str, gap_topic: str,
          decision_usd: float, latency_ms: int, out_chars: int = 0) -> Trace:
    r = res or Researched(mode=mode)
    shown = set(r.ids)
    return Trace(id=trace_id(kind, ref or market_id, at), at=at, kind=kind, book=book, market_id=market_id, ref=ref, mode=mode,  # type: ignore[arg-type]
                 rounds=r.rounds, queries=r.runs, returned_ids=r.returned, shown_ids=list(r.ids), cited_ids=[c for c in cited if c in shown or not shown],
                 evidence=evidence, gap_topic=gap_topic, tokens=r.tokens + out_chars // 4, plan_usd=round(r.usd, 6), usd=round(r.usd + decision_usd, 6),
                 latency_ms=latency_ms + r.ms)


def write(rows: list[Trace]) -> None:
    store.append_traces(rows)
