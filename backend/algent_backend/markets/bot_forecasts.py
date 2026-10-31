"""
The bots' own forecast feedback, scored apart from their trading. Every run of a roster strategy records its probability for the markets it examined
(``day_tools.Session.forecasts``) into ``bot_forecasts.jsonl``: append-only, per strategy, never shown to another bot. This module only READS it.

A forecast is scored when its market resolves YES or NO (void is not scored): Brier and log loss against the outcome, and against the market's own YES price
at the moment of the forecast (stored on the line, so no snapshot lookup can drift). Every forecast counts, not just each market's first: a bot restating a view
in a later run is a new prediction, made with new evidence. Numbers are withheld until ``FORECAST_MIN_RESOLVED`` forecasts have resolved; before that the page
says "n=3, too early". 
SKILL (``skill``) is the headline: mean of (market Brier - bot Brier) on the market's YES price at forecast time, positive = we beat the market, on all resolved markets and on
CONTESTED ones (price inside ``CONTESTED_LO..CONTESTED_HI``; near-decided markets flatter any Brier), each with n and a standard error. It dedupes to ONE forecast per
market (the LAST one made before resolution), so a bot restating a view 20 times counts once; the per-forecast numbers above keep every restatement.
(score.py's Brier and log loss are the same formulas; they are not imported because score.py imports the reports that import this.)
"""

from __future__ import annotations

import math
from typing import Any

from . import flags, store
from .contracts import BotForecast

RECENT = 8
EPS = 1e-3


def brier(p: float, o: int) -> float:
    return (p - o) ** 2


def log_loss(p: float, o: int) -> float:
    p = min(1 - EPS, max(EPS, p))
    return -(o * math.log(p) + (1 - o) * math.log(1 - p))


def scorable(f: Any, m: Any) -> bool:
    """A forecast is scored only if its market resolved yes/no AND it was made before the market's end time: after the end (the mirror can still list it as
    open for an hour or two while it settles) the price already shows the answer, and such a "forecast" is a read of the result, not a prediction."""
    if m is None or m.status != "resolved" or m.outcome not in ("yes", "no"):
        return False
    at, end = store.parse_iso(f.at), store.parse_iso(getattr(m, "end_date", "") or "")
    return (end is None or (at is not None and at < end)) and (not m.resolved_at or f.at <= m.resolved_at)


def _outcome(f: BotForecast, ms: dict) -> str:
    m = ms.get(f.market_id)
    return m.outcome if scorable(f, m) else ""


def _block(diffs: list[float]) -> dict[str, Any]:
    """n always; mean and standard error only at ``FORECAST_MIN_RESOLVED`` (and n >= 2 for an error)."""
    n = len(diffs)
    shown = n >= max(2, flags.FORECAST_MIN_RESOLVED)
    mean = sum(diffs) / n if n else 0.0
    se = math.sqrt(sum((d - mean) ** 2 for d in diffs) / (n - 1) / n) if n >= 2 else 0.0
    return {"n": n, "shown": shown, "mean": round(mean, 4) if shown else None, "se": round(se, 4) if shown else None}


def skill_stats(strategy: str) -> dict[str, Any]:
    """Skill vs the market, ``all`` and ``contested``: one forecast per market (the last before it resolved), (market Brier - bot Brier) each."""
    ms = store.markets()
    last: dict[str, BotForecast] = {}
    for f in sorted(store.bot_forecasts(strategy), key=lambda f: f.at):
        m = ms.get(f.market_id)
        if f.market is not None and scorable(f, m):
            last[f.market_id] = f
    diffs = [(brier(f.market, o) - brier(f.p, o), f.market) for f in last.values() if f.market is not None and (o := 1 if ms[f.market_id].outcome == "yes" else 0) in (0, 1)]
    return {"min_resolved": flags.FORECAST_MIN_RESOLVED, "all": _block([d for d, _ in diffs]),
            "contested": _block([d for d, m in diffs if flags.CONTESTED_LO <= m <= flags.CONTESTED_HI])}


def summary(strategy: str) -> dict[str, Any]:
    """Counts always; Brier, log loss and skill only at ``FORECAST_MIN_RESOLVED`` scored forecasts. ``recent`` lists the newest forecasts with the price and any outcome."""
    rows = sorted(store.bot_forecasts(strategy), key=lambda f: f.at)
    ms = store.markets()
    scored = [(f, 1 if _outcome(f, ms) == "yes" else 0) for f in rows if _outcome(f, ms) in ("yes", "no")]
    shown = len(scored) >= flags.FORECAST_MIN_RESOLVED
    mean = lambda xs: round(sum(xs) / len(xs), 4) if xs else None  # noqa: E731
    comp = [(brier(f.p, o), brier(f.market, o)) for f, o in scored if f.market is not None]
    skill = 1 - sum(a for a, _ in comp) / sum(b for _, b in comp) if comp and sum(b for _, b in comp) > 0 else None
    return {"skill": skill_stats(strategy), "made": len(rows), "resolved": len(scored), "min_resolved": flags.FORECAST_MIN_RESOLVED, "shown": shown,
            "brier": mean([brier(f.p, o) for f, o in scored]) if shown else None, "brier_market": mean([b for _, b in comp]) if shown else None,
            "log_loss": mean([log_loss(f.p, o) for f, o in scored]) if shown else None, "skill_vs_market": round(skill, 3) if shown and skill is not None else None,
            "recent": [{"market_id": f.market_id, "question": f.question or (ms[f.market_id].question if f.market_id in ms else f.market_id), "at": f.at, "p": f.p,
                        "market": f.market, "confidence": f.confidence, "outcome": _outcome(f, ms), "reason": f.reason} for f in rows[-RECENT:][::-1]]}
