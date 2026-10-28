"""
The bots' own forecast feedback, scored apart from their trading. Every run of a roster strategy records its probability for the markets it examined
(``day_tools.Session.forecasts``) into ``bot_forecasts.jsonl``: append-only, per strategy, never shown to another bot. This module only READS it.

A forecast is scored when its market resolves YES or NO (void is not scored): Brier and log loss against the outcome, and against the market's own YES price
at the moment of the forecast (stored on the line, so no snapshot lookup can drift). Every forecast counts, not just each market's first: a bot restating a view
in a later run is a new prediction, made with new evidence. Numbers are withheld until ``FORECAST_MIN_RESOLVED`` forecasts have resolved; before that the page
says "n=3, too early". (score.py's Brier and log loss are the same formulas; they are not imported because score.py imports the reports that import this.)
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


def _outcome(f: BotForecast, ms: dict) -> str:
    m = ms.get(f.market_id)
    return m.outcome if m is not None and m.status == "resolved" else ""


def summary(strategy: str) -> dict[str, Any]:
    """Counts always; Brier, log loss and skill only at ``FORECAST_MIN_RESOLVED`` scored forecasts. ``recent`` lists the newest forecasts with the price and any outcome."""
    rows = sorted(store.bot_forecasts(strategy), key=lambda f: f.at)
    ms = store.markets()
    scored = [(f, 1 if _outcome(f, ms) == "yes" else 0) for f in rows if _outcome(f, ms) in ("yes", "no")]
    shown = len(scored) >= flags.FORECAST_MIN_RESOLVED
    mean = lambda xs: round(sum(xs) / len(xs), 4) if xs else None  # noqa: E731
    comp = [(brier(f.p, o), brier(f.market, o)) for f, o in scored if f.market is not None]
    skill = 1 - sum(a for a, _ in comp) / sum(b for _, b in comp) if comp and sum(b for _, b in comp) > 0 else None
    return {"made": len(rows), "resolved": len(scored), "min_resolved": flags.FORECAST_MIN_RESOLVED, "shown": shown,
            "brier": mean([brier(f.p, o) for f, o in scored]) if shown else None, "brier_market": mean([b for _, b in comp]) if shown else None,
            "log_loss": mean([log_loss(f.p, o) for f, o in scored]) if shown else None, "skill_vs_market": round(skill, 3) if shown and skill is not None else None,
            "recent": [{"market_id": f.market_id, "question": f.question or (ms[f.market_id].question if f.market_id in ms else f.market_id), "at": f.at, "p": f.p,
                        "market": f.market, "confidence": f.confidence, "outcome": _outcome(f, ms), "reason": f.reason} for f in rows[-RECENT:][::-1]]}
