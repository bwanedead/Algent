"""
Run cost meter — estimated USD spend per run, with a hard auto-stop cap.

The safety rail for live runs: accumulate an *estimate* of what a run is spending
across every paid surface (the model's tokens + paid search calls), and stop the
run the moment that estimate crosses a per-run ceiling. Combined with the turn
limit (model-loop spin), the paid-call count budget, and the manual ``runs stop``
kill switch, this is the layer that bounds *dollars*, not just call counts.

IMPORTANT: the prices below are **best-effort estimates**, not billing truth.
Providers change pricing, free tiers exist, and token accounting varies. Treat the
meter as a conservative guardrail and a live signal — not an invoice. Update the
tables as real numbers are confirmed.

The meter is a ``ContextVar`` scoped per run (like the search policy), so it is
zero-overhead and isolated; nothing accumulates unless a run wraps itself in
``scoped(...)``.
"""

from __future__ import annotations

import contextvars
from collections.abc import Iterator
from contextlib import contextmanager

# USD per 1,000,000 tokens, as (input, output). ESTIMATES — verify per provider.
MODEL_PRICES: dict[str, tuple[float, float]] = {
    "gpt-5.4-mini": (0.15, 0.60),
    "gpt-5.4": (1.25, 10.00),
    "claude-opus-4-8": (5.00, 25.00),
    "claude-sonnet-4-6": (3.00, 15.00),
}
_FALLBACK_MODEL_PRICE = (1.00, 5.00)  # conservative guess for an unknown model

# USD per paid call / unit, by web_search channel. ESTIMATES.
CALL_PRICES: dict[str, float] = {
    "rich": 0.005,  # one Firecrawl page
    "x": 0.005,  # one native-X read unit
    "x_grok": 0.010,  # one xAI Grok X-search (model + search), rough
}

DEFAULT_RUN_CAP_USD = 1.00

_cap: contextvars.ContextVar[float] = contextvars.ContextVar("run_cost_cap", default=0.0)
_spent: contextvars.ContextVar[float] = contextvars.ContextVar("run_cost_spent", default=0.0)
_model: contextvars.ContextVar[str] = contextvars.ContextVar("run_cost_model", default="")
_active: contextvars.ContextVar[bool] = contextvars.ContextVar("run_cost_active", default=False)


def estimate_model_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    pin, pout = MODEL_PRICES.get(model, _FALLBACK_MODEL_PRICE)
    return (input_tokens / 1_000_000) * pin + (output_tokens / 1_000_000) * pout


def estimate_call_cost(channel: str) -> float:
    return CALL_PRICES.get(channel, 0.0)


def is_active() -> bool:
    return _active.get()


def add(usd: float) -> None:
    _spent.set(_spent.get() + max(0.0, usd))


def add_model_usage(input_tokens: int, output_tokens: int) -> None:
    add(estimate_model_cost(_model.get(), input_tokens, output_tokens))


def spent_usd() -> float:
    return round(_spent.get(), 6)


def remaining_usd() -> float:
    return max(0.0, _cap.get() - _spent.get())


def over_cap() -> bool:
    return _active.get() and _spent.get() >= _cap.get()


def would_exceed(usd: float) -> bool:
    """True if charging ``usd`` now would breach the cap (so refuse it first)."""
    return _active.get() and (_spent.get() + usd) > _cap.get()


@contextmanager
def scoped(cap_usd: float, model: str) -> Iterator[None]:
    """Meter and cap one run's spend; resets afterwards."""
    tokens = (
        _cap.set(max(0.0, cap_usd)),
        _spent.set(0.0),
        _model.set(model),
        _active.set(True),
    )
    try:
        yield
    finally:
        _cap.reset(tokens[0])
        _spent.reset(tokens[1])
        _model.reset(tokens[2])
        _active.reset(tokens[3])
