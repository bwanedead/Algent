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

# USD per 1,000,000 tokens, as (input, output). Sourced from provider pricing
# pages (as of ~mid-2026; verify periodically — pricing changes):
#   gpt-5.4-nano  $0.20 / $1.25   (developers.openai.com/api/docs/pricing) — the triage tier
#   gpt-5.4-mini  $0.75 / $4.50   (developers.openai.com/api/docs/pricing) — the synthesis tier
#   grok-4-fast   $0.20 / $0.50   (x.ai/api)
#   grok-4.3      $1.25 / $2.50   (x.ai/api)
MODEL_PRICES: dict[str, tuple[float, float]] = {
    "gpt-5.4-nano": (0.20, 1.25),
    "gpt-5.4-mini": (0.75, 4.50),
    "grok-4-fast": (0.20, 0.50),
    "grok-4.3": (1.25, 2.50),
}
_FALLBACK_MODEL_PRICE = (1.00, 5.00)  # conservative guess for an unknown model

# USD per web_search call/unit, sourced from provider pricing (verify periodically):
#   keyword (Tavily basic search)  $0.008/search   (docs.tavily.com api-credits; free <=1k/mo)
#   semantic (Exa /search)         $0.007/search   (exa.ai/pricing)
#   read (trafilatura, local)      $0.00           (no external call)
#   rich (Firecrawl /scrape)       ~$0.001/page    (firecrawl.dev/pricing; ~$0.00083 Standard..$0.0032 Hobby)
#   x post read                    $0.005/post     (X pay-per-use; confirm in console)
#   x (research default call)      10 posts × $0.005 = $0.05  (web_search source=x default max)
#   x_trends                       $0.00 posts     (trend names only; t0 sparse path)
#   x_grok (xAI Grok X-search)     $0.005/call + tokens (x.ai live search $5/1k)
CALL_PRICES: dict[str, float] = {
    "keyword": 0.008,
    "semantic": 0.007,
    "read": 0.0,
    "rich": 0.001,
    "x": 0.05,           # default research call (~10 posts); prefer estimate_x_posts(n)
    "x_post": 0.005,     # per post body returned
    "x_trends": 0.0,     # WOEID trends (no post bodies)
    "x_grok": 0.008,
}


def estimate_x_posts(n: int) -> float:
    """Estimated USD for ``n`` X post bodies returned (t0 hydrate / research search)."""
    return max(0, int(n)) * CALL_PRICES["x_post"]

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
