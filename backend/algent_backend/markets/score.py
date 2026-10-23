"""
Scoring: how good were we, against the world and against the market that priced the same question at the same moment.

Pairs. For every resolved (yes/no) market where we made a forecast, the pair is (our probability, the market's YES price at our forecast's
timestamp, the outcome). The market's price is the last live snapshot at or before the forecast, no older than ``flags.SNAPSHOT_MAX_AGE_H``; with
none, the forecast is scored on its own but not compared. Void (50-50) resolutions are not scored. The headline uses each market's FIRST
forecast so that re-forecasting a market cannot multiply its weight or let a later, better-informed view stand in for the call as first made.

Math (o = 1 if YES else 0, p = probability stated for YES):
* Brier  = mean (p - o)^2. Lower is better; 0.25 is a constant 50% forecast. Reported for us and for the market on the SAME pairs.
* Brier skill vs market = 1 - Brier_ours / Brier_market. Positive means we beat the market; negative that the market beat us.
* Log loss = mean of -(o ln p + (1 - o) ln(1 - p)), with p clipped to [0.001, 0.999] so a market at 0 or 1 cannot produce infinity.
* Calibration = pairs grouped by stated probability into ``CALIBRATION_BUCKET`` bins: mean stated probability against the share that happened.
* Over time = the running mean Brier difference (ours - market) in order of resolution; below zero is us ahead.

Nothing is hidden by sample size: ``verdict`` says "too early" until ``MIN_RESOLVED_FOR_VERDICT`` compared pairs exist, and the worst misses are
listed first. Settled Pulse watches and the desk's older judgment ledger are scored beside it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from . import flags, paper, research_report, store, trader_report
from .contracts import Forecast, Market

EPS = 1e-3


@dataclass
class Pair:
    market: Market
    forecast: Forecast
    outcome: int                       # 1 = YES
    market_p: float | None             # the market's YES price at the forecast's timestamp, or None

    @property
    def ours(self) -> float:
        return self.forecast.p


def brier(p: float, o: int) -> float:
    return (p - o) ** 2


def log_loss(p: float, o: int) -> float:
    p = min(1 - EPS, max(EPS, p))
    return -(o * math.log(p) + (1 - o) * math.log(1 - p))


def pairs(*, first_only: bool = True) -> list[Pair]:
    ms, by_price = store.markets(), store.snapshots_by_market()
    fcs = sorted(store.forecasts(), key=lambda f: f.made_at)
    seen: set[str] = set()
    out = []
    for f in fcs:
        m = ms.get(f.market_id)
        if m is None or m.status != "resolved" or m.outcome not in ("yes", "no"):
            continue
        if first_only and f.market_id in seen:
            continue
        seen.add(f.market_id)
        snap = store.price_at([s for s in by_price.get(f.market_id, []) if s.source == "live"], f.made_at)
        out.append(Pair(m, f, 1 if m.outcome == "yes" else 0, snap.p if snap else None))
    return sorted(out, key=lambda p: p.market.resolved_at)


def _mean(xs: list[float]) -> float | None:
    return round(sum(xs) / len(xs), 4) if xs else None


def calibration(items: list[tuple[float, int]]) -> list[dict[str, Any]]:
    width = flags.CALIBRATION_BUCKET
    n_bins = round(1 / width)
    bins: dict[int, list[tuple[float, int]]] = {}
    for p, o in items:
        bins.setdefault(min(int(p / width), n_bins - 1), []).append((p, o))
    return [{"low": round(b * width, 2), "high": round((b + 1) * width, 2), "n": len(v), "mean_p": round(sum(p for p, _ in v) / len(v), 3),
             "hit_rate": round(sum(o for _, o in v) / len(v), 3)} for b, v in sorted(bins.items())]


def forecast_scores(ps: list[Pair]) -> dict[str, Any]:
    cmp_ = [p for p in ps if p.market_p is not None]
    out: dict[str, Any] = {
        "resolved_with_forecast": len(ps), "compared": len(cmp_),
        "brier_ours_all": _mean([brier(p.ours, p.outcome) for p in ps]), "log_loss_ours_all": _mean([log_loss(p.ours, p.outcome) for p in ps]),
        "brier_ours": _mean([brier(p.ours, p.outcome) for p in cmp_]), "brier_market": _mean([brier(p.market_p, p.outcome) for p in cmp_]),
        "log_loss_ours": _mean([log_loss(p.ours, p.outcome) for p in cmp_]), "log_loss_market": _mean([log_loss(p.market_p, p.outcome) for p in cmp_]),
        "calibration_ours": calibration([(p.ours, p.outcome) for p in ps]),
        "calibration_market": calibration([(p.market_p, p.outcome) for p in cmp_]),
        "yes_rate": _mean([float(p.outcome) for p in ps]), "mean_forecast": _mean([p.ours for p in ps]),
    }
    b_o, b_m = out["brier_ours"], out["brier_market"]
    out["brier_skill"] = round(1 - b_o / b_m, 4) if b_o is not None and b_m else None
    run, series = 0.0, []
    for i, p in enumerate(cmp_, 1):
        run += brier(p.ours, p.outcome) - brier(p.market_p, p.outcome)
        series.append({"n": i, "at": p.market.resolved_at[:10], "diff": round(run / i, 4)})
    out["brier_diff_series"] = series
    n = len(cmp_)
    if n < flags.MIN_RESOLVED_FOR_VERDICT:
        out["verdict"] = (f"Too early to say: {n} resolved markets compared, {flags.MIN_RESOLVED_FOR_VERDICT} needed before these numbers mean "
                          f"anything. Treat every score here as noise.")
    elif out["brier_skill"] is not None and out["brier_skill"] > 0:
        out["verdict"] = f"Ahead of the market on {n} markets (Brier skill {out['brier_skill']:+.1%}); this is a track record, not a guarantee."
    else:
        out["verdict"] = f"Not beating the market on {n} markets (Brier skill {out['brier_skill']:+.1%}): the market was the better forecaster."
    return out


def pair_row(p: Pair) -> dict[str, Any]:
    return {"market_id": p.market.id, "question": p.market.question, "url": p.market.url, "resolved_at": p.market.resolved_at[:10],
            "outcome": p.market.outcome, "ours": p.ours, "market": p.market_p, "made_at": p.forecast.made_at[:10],
            "brier_ours": round(brier(p.ours, p.outcome), 4), "brier_market": round(brier(p.market_p, p.outcome), 4) if p.market_p is not None else None,
            "ours_closer": None if p.market_p is None else brier(p.ours, p.outcome) < brier(p.market_p, p.outcome),
            "rationale": p.forecast.rationale, "theaters": p.forecast.theaters}


def watch_scores() -> dict[str, Any]:
    """Settled Pulse watches (triggered vs expired) and the desk's older judgment ledger. Best-effort: absent stores read as empty."""
    out: dict[str, Any] = {"watches": None, "judgments": None}
    try:
        from algent_backend.agent_system.agents.pulse.repository import pulse_store

        ws = pulse_store().watches()
        trig, exp = sum(w.status == "triggered" for w in ws), sum(w.status == "expired" for w in ws)
        out["watches"] = {"open": sum(w.status == "open" for w in ws), "triggered": trig, "expired": exp, "invalidated": sum(w.status == "invalidated" for w in ws),
                          "trigger_rate": round(trig / (trig + exp), 3) if trig + exp else None,
                          "note": "A watch is a condition, not a probability: it can be hit-rated but not Brier-scored."}
    except Exception:  # noqa: BLE001
        pass
    try:
        from algent_backend.agent_system.agents.intel import forecasts as desk_forecasts

        out["judgments"] = desk_forecasts.scorecard()
    except Exception:  # noqa: BLE001
        pass
    return out


def open_rows(limit: int = 100) -> list[dict[str, Any]]:
    """Open paper positions with our probability beside the market's, largest stake first."""
    ms, by_price = store.markets(), store.snapshots_by_market()
    rows = []
    for p in paper.positions().values():
        m = ms.get(p.market_id)
        live = [s for s in by_price.get(p.market_id, []) if s.source == "live"]
        if p.status != "open" or m is None:
            continue
        rows.append({"market_id": m.id, "question": m.question, "url": m.url, "ends": m.end_date[:10], "side": p.side, "stake": p.stake, "entry": p.price,
                     "ours": p.ours, "market_at_open": p.market_at_open, "market_now": live[-1].p if live else None, "value": p.value, "pnl": p.pnl,
                     "opened": p.opened_at[:10], "theaters": m.theaters})
    return sorted(rows, key=lambda r: -r["stake"])[:limit]


def disagreements(now_iso: str | None = None) -> list[dict[str, Any]]:
    """Open markets where our newest forecast and the market's current price differ most, newest forecasts only."""
    from datetime import UTC, datetime, timedelta

    now = store.parse_iso(now_iso) if now_iso else datetime.now(UTC)
    ms, by_price = store.markets(), store.snapshots_by_market()
    out = []
    for mid, f in paper.latest_forecasts().items():
        m = ms.get(mid)
        ft = store.parse_iso(f.made_at)
        live = [s for s in by_price.get(mid, []) if s.source == "live"]
        if m is None or m.status != "open" or not live or ft is None or now is None or now - ft > timedelta(days=flags.DISAGREE_MAX_AGE_DAYS):
            continue
        gap = f.p - live[-1].p
        if abs(gap) >= flags.DISAGREE_MIN:
            out.append({"market_id": mid, "question": m.question, "url": m.url, "ours": f.p, "market": live[-1].p, "gap": round(gap, 3),
                        "made_at": f.made_at[:10], "rationale": f.rationale, "theaters": m.theaters})
    return sorted(out, key=lambda r: -abs(r["gap"]))


def track_record() -> dict[str, Any]:
    """The whole scoreboard as one document (what the site and the API read)."""
    ps = pairs()
    ms = store.markets().values()
    rows = [pair_row(p) for p in ps]
    worst = sorted((r for r in rows), key=lambda r: -r["brier_ours"])[:10]
    market_won = [r for r in rows if r["ours_closer"] is False]
    return {
        "schema": "ohmega.track-record/2", "as_of": store.now_iso(), "paper_only": True,
        "disclaimer": "Paper trading only. These are Ohmega's own probability forecasts compared with a prediction market's prices; "
                      "no money is staked and nothing here is financial advice.",
        "markets": {"open": sum(m.status == "open" for m in ms), "resolved": sum(m.status == "resolved" for m in ms), "void": sum(m.status == "void" for m in ms)},
        "forecasts": len(store.forecasts()), "scores": forecast_scores(ps), "portfolio": paper.summary(),
        "trader": trader_report.section(), "fast": research_report.fast_section(), "evidence": research_report.section(ps),
        "horizons": research_report.horizons(ps), "open_positions": open_rows(), "disagreements": disagreements()[:20], "worst_misses": worst,
        "market_beat_us": len(market_won), "resolved": rows[::-1][:flags.PUBLISH_RESOLVED],
        "other": watch_scores(),
        "rules": {"bankroll": flags.BANKROLL, "edge_min": flags.EDGE_MIN, "kelly_fraction": flags.KELLY_FRACTION, "max_position_frac": flags.MAX_POSITION_FRAC,
                  "max_exposure_frac": flags.MAX_EXPOSURE_FRAC, "slippage": flags.SLIPPAGE, "min_for_verdict": flags.MIN_RESOLVED_FOR_VERDICT},
    }
