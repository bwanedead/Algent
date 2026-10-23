"""
AI benchmark scores: labs and models as entities (model built_by lab), one observation per score. ``basis`` keeps independently ``measured``
scores apart from ``self_reported`` ones, as the desk does: the two are never one series.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterator

from algent_backend.ai_benchmarks import store

from .. import flags
from ..norm import slug
from ..sink import Sink
from .base import Source, Unit, digest_of, mark


def _emit(b, rows: list, sink: Sink) -> None:                                 # noqa: ANN001 - Benchmark / Result models
    for r in rows:
        lab = f"lab:{slug(r.lab)}"
        model = f"model:{slug(r.lab)}:{slug(r.model_id)}"
        sink.declare(lab, "lab", r.lab_name or r.lab, rank=flags.RANK_DECLARED)
        sink.declare(model, "model", r.model, aliases=[r.model_id], rank=flags.RANK_DECLARED, attrs={"weights": r.weights, "lab": r.lab})
        sink.relation("built_by", src=model, dst=lab, date=r.date)
        sink.observation(f"bench.{r.benchmark}", r.date, r.score, entity=model, unit=b.unit if b else "", basis=r.verification,
                         label=f"{r.model} on {b.name if b else r.benchmark}", source_url=r.url or (b.source_url if b else ""),
                         note=f"{r.source}; first seen {r.observed_on}{'; revised' if r.revised else ''}")


def _units() -> Iterator[Unit]:
    catalog = store.benchmarks()
    by_bench: dict[str, list] = defaultdict(list)
    for r in store.current():
        by_bench[r.benchmark].append(r)
    for bid in sorted(by_bench):
        rows = sorted(by_bench[bid], key=lambda r: (r.date, r.model_id))
        yield Unit(f"bench:{bid}", digest_of([r.model_dump() for r in rows]), lambda sink, b=catalog.get(bid), rows=rows: _emit(b, rows, sink),
                   date=rows[-1].date, path="ai_benchmarks_store/results.jsonl")


def _watermark() -> str:
    base = store.root()
    return mark([base / "results.jsonl", base / "benchmarks.json"]) if base.is_dir() else "none"


SOURCE = Source("ai_benchmarks", "ai_benchmarks", _units, _watermark)
