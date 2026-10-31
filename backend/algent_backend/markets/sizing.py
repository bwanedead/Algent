"""
Mechanical, trust-weighted sizing: the ONE place a buy's stake ceiling is computed (``guards.apply`` for the agentic bots and resting fills, ``guards.floor_stake``,
``paper.kelly_stake`` for the retired rule book). The forecaster's job is a probability; how much to bet on it is not its call.

    q       = w*p + (1-w)*price           the bot's p for the side, shrunk toward the market price by its TRUST w
    ceiling = KELLY_FRACTION * (q - c)/(1 - c) * bankroll   on the all-in cost c (slippage included); q <= c: no trade
              and, when c > EXTREME_PRICE, also at most MAX_LOSS_FRAC_EXTREME * bankroll (the whole stake is the loss if it fails)
    w       = clamp(TRUST_PRIOR + TRUST_GAIN * t, TRUST_MIN, TRUST_MAX),   t = contested skill / its standard error

``t`` is the t-statistic of a strategy's mean (market Brier - bot Brier) on contested markets (``bot_forecasts.skill_stats``): monotone in skill, grows with evidence, negative
skill lowers trust. Below ``FORECAST_MIN_RESOLVED`` contested forecasts (or a zero spread) there is no t and trust stays at the prior. The agent's stake is honoured only up to the ceiling.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from . import bot_forecasts, flags


@dataclass(frozen=True)
class Ceiling:
    stake: float          # dollars; 0 = no trade
    q: float              # trust-shrunk probability for the side
    cost: float           # all-in price per share
    full: float           # full Kelly as a share of the bankroll (<= 0: no edge)
    why: str              # the binding limit as a clip reads it (at stake 0: "no edge after trust shrink")


def full_kelly(q: float, cost: float) -> float:
    """Full Kelly share of bankroll for a binary contract paying 1: q is the win probability, cost the price. Negative or zero = no edge."""
    return 0.0 if cost >= 1.0 else (q - cost) / (1.0 - cost)


def shrink(p: float, price: float, w: float) -> float:
    return w * p + (1.0 - w) * price


def trust_from(skill: dict[str, Any] | None) -> float:
    """Trust from a ``bot_forecasts.skill_stats`` block's contested part: the prior until it is shown, then the prior moved by its t-statistic, clamped."""
    c = (skill or {}).get("contested") or {}
    mean, se = c.get("mean"), c.get("se")
    if not c.get("shown") or mean is None or not se:
        return flags.TRUST_PRIOR
    return round(min(flags.TRUST_MAX, max(flags.TRUST_MIN, flags.TRUST_PRIOR + flags.TRUST_GAIN * mean / se)), 3)


def trust(strategy: str) -> float:
    return trust_from(bot_forecasts.skill_stats(strategy))


def ceiling(p_yes: float, side: str, cost: float, bankroll: float, w: float) -> Ceiling:
    """The most a buy of ``side`` may stake. ``cost`` is the all-in price of that side; the market price it shrinks toward is the cost less slippage."""
    p = p_yes if side == "yes" else 1.0 - p_yes
    q = shrink(p, max(0.0, cost - flags.SLIPPAGE), w)
    full = full_kelly(q, cost)
    if full <= 0:
        return Ceiling(0.0, q, cost, full, "no edge after trust shrink")
    stake, why = flags.KELLY_FRACTION * full * bankroll, "trust-weighted Kelly"
    if cost > flags.EXTREME_PRICE and stake > flags.MAX_LOSS_FRAC_EXTREME * bankroll:
        stake, why = flags.MAX_LOSS_FRAC_EXTREME * bankroll, f"max loss at an extreme price ({cost:.2f})"
    return Ceiling(round(stake, 2), q, cost, full, why)
