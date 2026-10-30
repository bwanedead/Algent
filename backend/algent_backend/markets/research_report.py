"""
The Evidence section of the published track record: how well the corpus served the bots, what they went looking for, and whether decisions with
richer corpus evidence did better. Read-only projections of the research traces, the gap ledger and the forecast / decision lines.

* coverage: of the decisions that rated their own evidence, the share "sufficient" vs "thin" vs "gap";
* citations per decision (the ids the bot said it used);
* tools: queries by tool, results per query, empty and failed shares, latency and cost per decision (from the traces, which are pruned by age);
* top gaps: what the bots asked for most, and whether a research run has covered it;
* accuracy by evidence richness: Brier (forecasts) and realised P&L (closed positions) for decisions that cited at least ``flags.RICH_MIN_CITED``
  corpus items against thinner ones, each group's numbers shown ONLY once it holds ``flags.MIN_RESOLVED_FOR_VERDICT`` resolved items (the same rule as the verdict);
* loop: did each gap research run help (re-asks, uptake, edge before/after, a plain verdict; gap_loop.py);
* horizons: Brier by time-to-resolution at the forecast, and how long each book's positions took to resolve.
"""

from __future__ import annotations

import statistics
from collections import Counter
from datetime import UTC, datetime
from typing import Any

from . import books, flags, gap_loop, gaps, store, trader_report
from .contracts import Decision, Forecast

BUCKETS = (("2 days or less", 0.0, 48.0), ("2 to 7 days", 48.0, 168.0), ("7 to 30 days", 168.0, 720.0), ("over 30 days", 720.0, 1e9))


def _share(n: int, d: int) -> float | None:
    return round(n / d, 3) if d else None


def coverage(fcs: list[Forecast], ds: list[Decision]) -> dict[str, Any]:
    def tally(rows: list[Any]) -> dict[str, Any]:
        c = Counter(r.evidence for r in rows if r.evidence)
        rated = sum(c.values())
        return {"n": len(rows), "rated": rated, "sufficient": c["sufficient"], "thin": c["thin"], "gap": c["gap"], "share_sufficient": _share(c["sufficient"], rated),
                "share_gap_requested": _share(c["thin"] + c["gap"], rated)}
    trades = [d for d in ds if d.action != "settle"]
    both = tally([*fcs, *trades])
    return {**both, "forecasts": tally(fcs), "trades": tally(trades)}


def citations(fcs: list[Forecast], ds: list[Decision]) -> dict[str, Any]:
    n = [len(r.evidence_ids) for r in [*fcs, *[d for d in ds if d.action != "settle"]] if r.evidence]
    return {"n": len(n), "mean": round(sum(n) / len(n), 2) if n else None, "median": statistics.median(n) if n else None, "none_share": _share(sum(x == 0 for x in n), len(n))}


def tools() -> dict[str, Any]:
    ts = store.traces()
    qs = [q for t in ts for q in t.queries]
    by_tool = Counter(q.tool for q in qs)
    lat = [t.latency_ms for t in ts if t.latency_ms]
    return {"traces": len(ts), "corpus": sum(t.mode == "corpus" for t in ts), "fallback": sum(t.mode == "base-fallback" for t in ts), "queries": len(qs),
            "by_tool": dict(by_tool.most_common()), "mean_results": round(sum(q.n for q in qs) / len(qs), 2) if qs else None,
            "empty_share": _share(sum(q.n == 0 for q in qs), len(qs)), "error_share": _share(sum(bool(q.error) for q in qs), len(qs)),
            "median_latency_ms": int(statistics.median(lat)) if lat else None,
            "mean_usd": round(sum(t.usd for t in ts) / len(ts), 4) if ts else None, "mean_tokens": int(sum(t.tokens for t in ts) / len(ts)) if ts else None,
            "mean_rounds": round(sum(t.rounds for t in ts) / len(ts), 2) if ts else None}


def _group(label: str, rows: list[tuple[float, float | None, float]], *, minimum: int) -> dict[str, Any]:
    """rows: (brier_ours, brier_market or None, weight unused). Numbers are withheld below ``minimum`` and the group says so."""
    n = len(rows)
    out: dict[str, Any] = {"label": label, "n": n, "shown": n >= minimum, "brier_ours": None, "brier_market": None, "skill": None}
    if n >= minimum:
        out["brier_ours"] = round(sum(r[0] for r in rows) / n, 4)
        cmp_ = [r for r in rows if r[1] is not None]
        if cmp_:
            bo, bm = sum(r[0] for r in cmp_) / len(cmp_), sum(r[1] for r in cmp_ if r[1] is not None) / len(cmp_)
            out.update(brier_ours=round(bo, 4), brier_market=round(bm, 4), skill=round(1 - bo / bm, 4) if bm else None, compared=len(cmp_))
    return out


def accuracy_split(ps: list[Any]) -> dict[str, Any]:
    """Brier for research-era forecasts that cited at least RICH_MIN_CITED corpus items vs fewer, and P&L of closed positions by the same rule."""
    from .score import brier

    minimum, rich_n = flags.MIN_RESOLVED_FOR_VERDICT, flags.RICH_MIN_CITED
    rich, thin = [], []
    for p in ps:
        if not p.forecast.evidence:                                     # forecast from before corpus research: no comparable evidence measure
            continue
        row = (brier(p.ours, p.outcome), brier(p.market_p, p.outcome) if p.market_p is not None else None, 1.0)
        (rich if len(p.forecast.evidence_ids) >= rich_n else thin).append(row)
    pnl: dict[str, list[float]] = {"rich": [], "thin": []}
    for name in ("daily", "fast"):
        ds = store.decisions(name)
        first_buy: dict[str, Decision] = {}
        for d in sorted(ds, key=lambda d: d.at):
            if d.action in ("buy_yes", "buy_no") and d.evidence:
                first_buy.setdefault(d.market_id, d)
        for mid, realised in trader_report._closed(ds).items():
            b = first_buy.get(mid)
            if b is not None:
                pnl["rich" if len(b.evidence_ids) >= rich_n else "thin"].append(realised)

    def money(label: str, xs: list[float]) -> dict[str, Any]:
        shown = len(xs) >= minimum
        return {"label": label, "n": len(xs), "shown": shown, "pnl": round(sum(xs), 2) if shown else None, "hit_rate": _share(sum(x > 0 for x in xs), len(xs)) if shown else None}

    return {"rich_min_cited": rich_n, "min_for_verdict": minimum,
            "forecasts": [_group(f"cited {rich_n} or more corpus items", rich, minimum=minimum), _group(f"cited fewer than {rich_n}", thin, minimum=minimum)],
            "trades": [money(f"opened on {rich_n} or more cited items", pnl["rich"]), money(f"opened on fewer than {rich_n}", pnl["thin"])],
            "note": (f"Each group's numbers appear only once it holds {minimum} resolved items; until then the counts are all that is shown. "
                     "Whether richer corpus evidence helps cannot be read from fewer.")}


def _hours(p: Any) -> float | None:
    if p.forecast.hours_to_end is not None:
        return p.forecast.hours_to_end
    end, made = store.parse_iso(p.market.end_date), store.parse_iso(p.forecast.made_at)
    return round((end - made).total_seconds() / 3600, 1) if end and made else None


def horizons(ps: list[Any], now: datetime | None = None) -> dict[str, Any]:
    """Forecast accuracy by how far ahead the market ended, and how long each book's closed positions took to resolve."""
    from .score import brier

    minimum = flags.MIN_RESOLVED_FOR_VERDICT
    rows = []
    for label, lo, hi in BUCKETS:
        got = [(brier(p.ours, p.outcome), brier(p.market_p, p.outcome) if p.market_p is not None else None, 1.0) for p in ps if (h := _hours(p)) is not None and lo <= h < hi]
        rows.append(_group(label, got, minimum=minimum))
    held: dict[str, Any] = {}
    ms = store.markets()
    for name in ("daily", "fast"):
        ds = store.decisions(name)
        first: dict[str, str] = {}
        for d in sorted(ds, key=lambda d: d.at):
            if d.action in ("buy_yes", "buy_no"):
                first.setdefault(d.market_id, d.at)
        days = []
        for mid, at in first.items():
            m = ms.get(mid)
            a, b = store.parse_iso(at), store.parse_iso(m.resolved_at) if m and m.resolved_at else None
            if a and b and m.status != "open":
                days.append(max(0.0, (b - a).total_seconds() / 86400))
        held[name] = {"positions": len(first), "resolved": len(days), "median_days_to_resolution": round(statistics.median(days), 2) if days else None,
                      "mean_days_to_resolution": round(sum(days) / len(days), 2) if days else None}
    return {"by_horizon": rows, "min_for_verdict": minimum, "books": held}


def section(ps: list[Any], now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    fcs, ds = store.forecasts(), store.decisions(None)
    return {"coverage": coverage(fcs, ds), "citations": citations(fcs, ds), "tools": tools(), "top_gaps": gaps.top(8, now), "accuracy": accuracy_split(ps),
            "caps": {"rounds": flags.RESEARCH_MAX_ROUNDS, "queries_per_round": flags.RESEARCH_QUERIES_PER_ROUND, "rows_per_query": flags.RESEARCH_ROWS_PER_QUERY,
                     "gap_fill_usd_per_day": flags.GAP_FILL_USD_PER_DAY, "corpus_only": flags.CORPUS_ONLY and flags.RESEARCH_ENABLED},
            "loop": gap_loop.block(now),
            "gap_spend": {"asks": len(store.gaps()), "fills": len(store.gap_fills()), "usd": round(sum(f.usd for f in store.gap_fills()), 4)}}


def fast_section(day: str | None = None) -> dict[str, Any]:
    """The fast book beside the daily trader: same shape as ``trader_report.section`` plus its horizon and cadence."""
    out = trader_report.section(day, "fast")
    out["horizon_days"] = flags.FAST_HORIZON_DAYS
    out["every_hours"] = flags.FAST_EVERY_H
    out["enabled"] = books.FAST.enabled()
    out["limits"] = {**out["limits"], "max_usd_per_day": flags.FAST_MAX_USD_PER_DAY}
    return out

