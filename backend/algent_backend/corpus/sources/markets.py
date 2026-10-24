"""
Polymarket mirror and our paper trader: each market is an entity bearing on the countries and situations it concerns, with the market's own price
(one point per day: reported, not ours), our blind forecast of it (model-assessed) and what the trader decided and why. The scored record itself
stays in the markets store; this is how the rest of the corpus finds it.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterator

from algent_backend.markets import store as mk

from .. import flags
from ..norm import clip, day
from ..sink import Sink
from .actors import country_id
from .base import Source, Unit, digest_of, mark


def market_id(raw: str) -> str:
    return f"market:{raw}"


def _emit(m, snaps: list, forecasts: list, decisions: list, sink: Sink) -> None:         # noqa: ANN001 - markets contracts
    mid = market_id(m.id)
    sink.declare(mid, "market", m.question, aliases=[m.event_title] if m.event_title else (), rank=flags.RANK_DECLARED,
                 attrs={"status": m.status, "outcome": m.outcome, "end_date": m.end_date, "url": m.url, "tags": m.tags})
    for iso in m.countries:
        sink.relation("bears_on", src=mid, dst=country_id(iso), date=m.first_seen)
    for thr in m.theaters:
        sink.relation("bears_on", src=mid, dst=f"situation:{thr}", date=m.first_seen)
    if m.status != "open" and m.resolved_at:
        sink.event(f"event:market:{m.id}:resolved", "market_resolved", date=m.resolved_at, title=f"Market resolved {m.outcome or m.status}: {m.question}",
                   status=m.outcome or m.status, url=m.url, actor_ids=[mid], role="market")
    last_per_day = {day(s.at): s for s in snaps if day(s.at)}
    for d, s in sorted(last_per_day.items()):
        sink.observation("market.p", d, s.p, entity=mid, unit="probability", basis="reported", label=f"market price (YES): {clip(m.question, 80)}",
                         source_url=m.url, note="Polymarket mid price")
    for f in forecasts:
        doc = f"forecast:{f.id}"
        sink.document(doc, "forecast", date=f.made_at, title=f"Forecast: {m.question}", body=f"{m.question} Our probability {f.p:.2f}. {f.rationale}",
                      status="model")
        sink.mention(entity=mid, document=doc, role="forecast of", date=f.made_at)
        sink.observation("forecast.p", f.made_at, f.p, entity=mid, unit="probability", basis="model", label=f"our forecast (YES): {clip(m.question, 80)}",
                         note=f.model)
    for d in decisions:
        sink.event(f"event:trade:{d.id}", f"paper_{d.action}", date=d.day, title=f"{d.action}: {m.question}", detail=d.rationale, status=d.action,
                   url=m.url, actor_ids=[mid], role="market")


def _units() -> Iterator[Unit]:
    snaps = mk.snapshots_by_market()
    forecasts: dict[str, list] = defaultdict(list)
    for f in mk.forecasts():
        forecasts[f.market_id].append(f)
    decisions: dict[str, list] = defaultdict(list)
    for d in mk.decisions(None):
        decisions[d.market_id].append(d)
    for m in sorted(mk.markets().values(), key=lambda m: m.id):
        s, f, d = snaps.get(m.id, []), forecasts.get(m.id, []), decisions.get(m.id, [])
        fp = digest_of([m.model_dump(exclude={"volume", "liquidity", "updated_at"}), [(x.at, x.p) for x in s], [x.model_dump() for x in f],
                        [x.model_dump() for x in d]])
        yield Unit(f"market:{m.id}", fp, lambda sink, m=m, s=s, f=f, d=d: _emit(m, s, f, d, sink), date=day(m.end_date) or "", path="markets_store/markets.jsonl")
    equity = mk.equity_points()
    if equity:
        def emit_equity(sink: Sink) -> None:
            for e in equity:
                sink.observation(f"paper.equity.{e.book}", e.day, e.equity, unit="paper usd", basis="model", label=f"paper trader equity ({e.book})")
        yield Unit("market:equity", digest_of([e.model_dump() for e in equity]), emit_equity, path="markets_store/equity.jsonl")


def _watermark() -> str:
    base = mk.root()
    return mark(base.glob("*.jsonl")) if base.is_dir() else "none"


SOURCE = Source("markets", "markets", _units, _watermark)
