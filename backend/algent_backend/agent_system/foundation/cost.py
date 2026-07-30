"""
Run cost meter — USD spend per run from real token buckets × list prices.

The safety rail for live runs: accumulate what a run is spending across every paid
surface (model tokens + paid search calls), and stop the run the moment that
crosses a per-run ceiling. Combined with the turn limit, the paid-call budget, and
the manual ``runs stop`` kill switch, this bounds *dollars*, not just call counts.

IMPORTANT: prices are list rates from provider pages, applied to the token counts
the API reports on each response. They are still not an invoice (free tiers, plan
discounts, and accounting quirks exist) — but they are token×rate, not a blunt
average. Update the tables when providers change list prices.

The meter is a ``ContextVar`` scoped per run (like the search policy), so it is
zero-overhead and isolated; nothing accumulates unless a run wraps itself in
``scoped(...)``.
"""

from __future__ import annotations

import contextvars
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

# ---------------------------------------------------------------------------
# Model list prices (USD per 1,000,000 tokens)
# ---------------------------------------------------------------------------
# OpenAI GPT-5.6 Luna (developers.openai.com; rates effective ~2026-07-30):
#   ordinary: input $0.20, cached input $0.02, cache write $0.25, output $1.20
#   long-context (>272k input tokens on the request): $0.40 / $0.04 / $0.50 / $1.80
# Legacy OpenAI tiers kept for historical runs / explicit overrides:
#   gpt-5.4-nano  $0.20 / $1.25  (cache write free)
#   gpt-5.4-mini  $0.75 / $4.50  (cache write free)
# xAI (x.ai/api):
#   grok-4-fast   $0.20 / $0.50
#   grok-4.3      $1.25 / $2.50


@dataclass(frozen=True)
class ModelRate:
    """Per-million-token list rates for one model.

    ``cached_input`` / ``cache_write`` default to ordinary input / 0 when unset
    (providers that do not bill cache writes separately). Long-context fields
    apply to the *entire* request when ``input_tokens`` exceeds the threshold.
    """

    input: float
    output: float
    cached_input: float | None = None
    cache_write: float | None = None
    long_context_threshold: int | None = None
    long_input: float | None = None
    long_output: float | None = None
    long_cached_input: float | None = None
    long_cache_write: float | None = None

    def for_request(self, input_tokens: int) -> tuple[float, float, float, float]:
        """Return (input, cached_input, cache_write, output) rates for this request size."""
        long = (
            self.long_context_threshold is not None
            and input_tokens > self.long_context_threshold
        )
        if long:
            return (
                self.long_input if self.long_input is not None else self.input,
                (
                    self.long_cached_input
                    if self.long_cached_input is not None
                    else (self.cached_input if self.cached_input is not None else self.input)
                ),
                (
                    self.long_cache_write
                    if self.long_cache_write is not None
                    else (self.cache_write if self.cache_write is not None else 0.0)
                ),
                self.long_output if self.long_output is not None else self.output,
            )
        return (
            self.input,
            self.cached_input if self.cached_input is not None else self.input,
            self.cache_write if self.cache_write is not None else 0.0,
            self.output,
        )


MODEL_RATES: dict[str, ModelRate] = {
    "gpt-5.6-luna": ModelRate(
        input=0.20,
        output=1.20,
        cached_input=0.02,
        cache_write=0.25,
        long_context_threshold=272_000,
        long_input=0.40,
        long_output=1.80,
        long_cached_input=0.04,
        long_cache_write=0.50,
    ),
    "gpt-5.4-nano": ModelRate(
        input=0.20, output=1.25, cached_input=0.02, cache_write=0.0,
    ),
    "gpt-5.4-mini": ModelRate(
        input=0.75, output=4.50, cached_input=0.075, cache_write=0.0,
    ),
    "grok-4-fast": ModelRate(input=0.20, output=0.50),
    "grok-4.3": ModelRate(input=1.25, output=2.50),
}

# Back-compat alias: (input, output) pairs for callers that still expect tuples.
MODEL_PRICES: dict[str, tuple[float, float]] = {
    name: (rate.input, rate.output) for name, rate in MODEL_RATES.items()
}

_FALLBACK_RATE = ModelRate(input=1.00, output=5.00)

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


def model_rate(model: str) -> ModelRate:
    return MODEL_RATES.get(model, _FALLBACK_RATE)


def _detail(mapping: Mapping[str, Any] | None, *keys: str) -> int:
    if not mapping:
        return 0
    for key in keys:
        if key in mapping and mapping[key] is not None:
            try:
                return max(0, int(mapping[key]))
            except (TypeError, ValueError):
                return 0
    return 0


def parse_usage_buckets(usage: Mapping[str, Any] | None) -> tuple[int, int, int, int]:
    """Split a LangChain / OpenAI ``usage_metadata`` dict into billable buckets.

    Returns ``(uncached_input, cached_input, cache_write, output)``.

    OpenAI's ``input_tokens`` / ``prompt_tokens`` already include cached tokens, so
    uncached = input − cache_read. Reasoning tokens are billed as output and stay
    inside ``output_tokens`` (we do not subtract them).
    """
    if not usage:
        return 0, 0, 0, 0
    input_tokens = _detail(usage, "input_tokens", "prompt_tokens")
    output_tokens = _detail(usage, "output_tokens", "completion_tokens")
    details_in = usage.get("input_token_details") or usage.get("prompt_tokens_details") or {}
    if not isinstance(details_in, Mapping):
        details_in = {}
    cached = _detail(details_in, "cache_read", "cached_tokens")
    cache_write = _detail(details_in, "cache_creation", "cache_write_tokens")
    if cached > input_tokens:
        cached = input_tokens
    uncached = max(0, input_tokens - cached)
    return uncached, cached, cache_write, output_tokens


def estimate_model_cost(
    model: str,
    input_tokens: int = 0,
    output_tokens: int = 0,
    *,
    cached_input_tokens: int = 0,
    cache_write_tokens: int = 0,
) -> float:
    """USD for explicit token buckets. ``input_tokens`` here is *uncached* input.

    Prefer :func:`estimate_usage_cost` when you have a full usage_metadata dict —
    it handles the input-includes-cached accounting correctly.
    """
    total_input = max(0, int(input_tokens)) + max(0, int(cached_input_tokens))
    pin, pcached, pwrite, pout = model_rate(model).for_request(total_input)
    return (
        (max(0, int(input_tokens)) / 1_000_000) * pin
        + (max(0, int(cached_input_tokens)) / 1_000_000) * pcached
        + (max(0, int(cache_write_tokens)) / 1_000_000) * pwrite
        + (max(0, int(output_tokens)) / 1_000_000) * pout
    )


def estimate_usage_cost(model: str, usage: Mapping[str, Any] | None) -> float:
    """USD for one model response from its reported usage_metadata."""
    uncached, cached, cache_write, output_tokens = parse_usage_buckets(usage)
    return estimate_model_cost(
        model,
        uncached,
        output_tokens,
        cached_input_tokens=cached,
        cache_write_tokens=cache_write,
    )


def estimate_call_cost(channel: str) -> float:
    return CALL_PRICES.get(channel, 0.0)


def is_active() -> bool:
    return _active.get()


def add(usd: float) -> None:
    _spent.set(_spent.get() + max(0.0, usd))


def add_model_usage(
    input_tokens: int = 0,
    output_tokens: int = 0,
    *,
    cached_input_tokens: int = 0,
    cache_write_tokens: int = 0,
    usage: Mapping[str, Any] | None = None,
) -> None:
    """Charge the active run for one model response.

    Pass ``usage=usage_metadata`` when available (precise). The positional
    input/output form remains for simple call sites; there ``input_tokens`` means
    uncached input unless ``cached_input_tokens`` is also supplied.
    """
    if usage is not None:
        add(estimate_usage_cost(_model.get(), usage))
        return
    add(
        estimate_model_cost(
            _model.get(),
            input_tokens,
            output_tokens,
            cached_input_tokens=cached_input_tokens,
            cache_write_tokens=cache_write_tokens,
        )
    )


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
