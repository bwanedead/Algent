"""
Run / article cost ledger — USD spend with soft-finish and hard-stop caps.

Two-tier article policy (env-overridable):
  soft  ALGENT_ARTICLE_SOFT_CAP_USD  default $1 — enter slim_finish (finish cheaply)
  hard  ALGENT_ARTICLE_HARD_CAP_USD  default $3 — refuse every new billable op

Canonical authorization (do not rely on post-hoc ``add()`` for hard-cap enforcement):
  1. ``try_reserve(estimate, op=...)`` before the operation
  2. refuse if ``spent + reserved + estimate > hard_cap``
  3. execute
  4. ``settle(reservation, actual)`` (or ``release`` on cancel)
  5. mode becomes ``slim_finish`` once settled spend reaches the soft cap

Stage ``scoped(...)`` still exists for per-agent allowances; under ``article_scoped``
those allowances draw from the remaining hard budget.
"""

from __future__ import annotations

import contextvars
import os
import uuid
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Literal

# ---------------------------------------------------------------------------
# Model list prices (USD per 1,000,000 tokens)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ModelRate:
    """Per-million-token list rates for one model."""

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
    # Meta Muse Spark — Contributor rates from Meta dashboard (train-on-data tier).
    # Override by changing this table if Meta revises list prices; caps still apply.
    "muse-spark-1.2-contributor": ModelRate(
        input=0.10,
        output=0.20,
        cached_input=0.002,
        cache_write=0.0,
    ),
    # Standard Muse Spark (non-contributor) — keep for ALGENT_HOUSE_MODEL swaps.
    "muse-spark-1.2": ModelRate(
        input=1.25,
        output=4.25,
        cached_input=0.15,
        cache_write=0.0,
    ),
    "muse-spark-1.1": ModelRate(
        input=1.25,
        output=4.25,
        cached_input=0.15,
        cache_write=0.0,
    ),
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

MODEL_PRICES: dict[str, tuple[float, float]] = {
    name: (rate.input, rate.output) for name, rate in MODEL_RATES.items()
}

_FALLBACK_RATE = ModelRate(input=1.00, output=5.00)

CALL_PRICES: dict[str, float] = {
    "keyword": 0.008,
    "semantic": 0.007,
    "read": 0.0,
    "rich": 0.001,
    "x": 0.05,
    "x_post": 0.005,
    "x_trends": 0.0,
    "x_grok": 0.008,
    "hero_image": 0.034,
}

BudgetMode = Literal["normal", "slim_finish", "hard_stop"]

DEFAULT_RUN_CAP_USD = 1.00
DEFAULT_ARTICLE_SOFT_CAP_USD = 1.00
DEFAULT_ARTICLE_HARD_CAP_USD = 3.00
# Back-compat alias — hard ceiling.
DEFAULT_ARTICLE_CAP_USD = DEFAULT_ARTICLE_HARD_CAP_USD

# Default max output tokens when a caller does not specify an allowance.
DEFAULT_MAX_OUTPUT_TOKENS = 4_096


def estimate_x_posts(n: int) -> float:
    return max(0, int(n)) * CALL_PRICES["x_post"]


@dataclass(frozen=True)
class Reservation:
    """Held estimate against the hard cap until settle/release."""

    id: str
    estimate: float
    op: str
    stage: str = ""
    essential: bool = False


@dataclass
class BudgetLedger:
    """One article (or standalone stage) budget state — the canonical ledger."""

    soft_cap_usd: float
    hard_cap_usd: float
    spent_usd: float = 0.0
    reserved_usd: float = 0.0
    mode: BudgetMode = "normal"
    soft_crossed_at_stage: str = ""
    hard_stop_stage: str = ""
    current_stage: str = ""
    soft_cap_crossed: bool = False
    hard_stop: bool = False
    skipped: list[dict[str, str]] = field(default_factory=list)
    refused: list[dict[str, str]] = field(default_factory=list)
    cost_by_stage: dict[str, float] = field(default_factory=dict)
    cost_by_op: dict[str, float] = field(default_factory=dict)
    _open: dict[str, Reservation] = field(default_factory=dict)

    def committed(self) -> float:
        return self.spent_usd + self.reserved_usd

    def snapshot(self) -> dict[str, Any]:
        return {
            "soft_cap_usd": round(self.soft_cap_usd, 6),
            "hard_cap_usd": round(self.hard_cap_usd, 6),
            "spent_usd": round(self.spent_usd, 6),
            "reserved_usd": round(self.reserved_usd, 6),
            "mode": self.mode,
            "soft_cap_crossed": self.soft_cap_crossed,
            "soft_crossed_at_stage": self.soft_crossed_at_stage,
            "hard_stop": self.hard_stop,
            "hard_stop_stage": self.hard_stop_stage,
            "cost_by_stage": dict(self.cost_by_stage),
            "cost_by_op": dict(self.cost_by_op),
            "skipped_operations": list(self.skipped),
            "refused_operations": list(self.refused),
        }


# Stage-scope ContextVars (standalone agent runs + nested stage ceilings).
_cap: contextvars.ContextVar[float] = contextvars.ContextVar("run_cost_cap", default=0.0)
_spent: contextvars.ContextVar[float] = contextvars.ContextVar("run_cost_spent", default=0.0)
_model: contextvars.ContextVar[str] = contextvars.ContextVar("run_cost_model", default="")
_active: contextvars.ContextVar[bool] = contextvars.ContextVar("run_cost_active", default=False)
_article_active: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "article_cost_active", default=False,
)
_stage_start: contextvars.ContextVar[float] = contextvars.ContextVar(
    "run_cost_stage_start", default=0.0,
)
_ledger: contextvars.ContextVar[BudgetLedger | None] = contextvars.ContextVar(
    "article_budget_ledger", default=None,
)
# When True, model/tool reserves are treated as finish-path essential (draft/headline/hero).
_essential: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "article_budget_essential", default=False,
)


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
    total_input = max(0, int(input_tokens)) + max(0, int(cached_input_tokens))
    pin, pcached, pwrite, pout = model_rate(model).for_request(total_input)
    return (
        (max(0, int(input_tokens)) / 1_000_000) * pin
        + (max(0, int(cached_input_tokens)) / 1_000_000) * pcached
        + (max(0, int(cache_write_tokens)) / 1_000_000) * pwrite
        + (max(0, int(output_tokens)) / 1_000_000) * pout
    )


def estimate_usage_cost(model: str, usage: Mapping[str, Any] | None) -> float:
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


def estimate_model_call_ceiling(
    model: str, input_tokens: int, max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS,
) -> float:
    """Conservative USD ceiling for one model call (uncached input + max output)."""
    return estimate_model_cost(model, max(0, input_tokens), max(0, max_output_tokens))


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return max(0.0, float(raw))
    except ValueError:
        return default


def soft_cap_usd() -> float:
    return _env_float("ALGENT_ARTICLE_SOFT_CAP_USD", DEFAULT_ARTICLE_SOFT_CAP_USD)


def hard_cap_usd() -> float:
    # Prefer new name; fall back to legacy ALGENT_ARTICLE_CAP_USD.
    if os.environ.get("ALGENT_ARTICLE_HARD_CAP_USD", "").strip():
        return _env_float("ALGENT_ARTICLE_HARD_CAP_USD", DEFAULT_ARTICLE_HARD_CAP_USD)
    if os.environ.get("ALGENT_ARTICLE_CAP_USD", "").strip():
        return _env_float("ALGENT_ARTICLE_CAP_USD", DEFAULT_ARTICLE_HARD_CAP_USD)
    return DEFAULT_ARTICLE_HARD_CAP_USD


def article_cap_usd() -> float:
    """Hard article ceiling (back-compat name)."""
    return hard_cap_usd()


def ledger() -> BudgetLedger | None:
    return _ledger.get()


def mode() -> BudgetMode:
    led = _ledger.get()
    return led.mode if led is not None else "normal"


def is_slim() -> bool:
    return mode() == "slim_finish"


def is_hard_stop() -> bool:
    return mode() == "hard_stop"


def is_essential() -> bool:
    return _essential.get()


def active_model() -> str:
    return _model.get()


@contextmanager
def essential_scope(active: bool = True) -> Iterator[None]:
    """Mark finish-path work (initial draft / headline / hero) as essential under slim_finish."""
    token = _essential.set(bool(active))
    try:
        yield
    finally:
        _essential.reset(token)


def set_stage(stage: str) -> None:
    led = _ledger.get()
    if led is not None:
        led.current_stage = str(stage or "")


def snapshot() -> dict[str, Any]:
    led = _ledger.get()
    if led is None:
        return {
            "soft_cap_usd": soft_cap_usd(),
            "hard_cap_usd": hard_cap_usd(),
            "spent_usd": round(_spent.get(), 6) if _active.get() else 0.0,
            "reserved_usd": 0.0,
            "mode": "normal",
            "soft_cap_crossed": False,
            "soft_crossed_at_stage": "",
            "hard_stop": False,
            "hard_stop_stage": "",
            "cost_by_stage": {},
            "cost_by_op": {},
            "skipped_operations": [],
            "refused_operations": [],
        }
    return led.snapshot()


def record_skip(op: str, reason: str = "slim_finish") -> None:
    led = _ledger.get()
    if led is None:
        return
    led.skipped.append({
        "op": op, "reason": reason, "stage": led.current_stage,
    })


def _record_refuse(led: BudgetLedger, op: str, reason: str) -> None:
    led.refused.append({
        "op": op, "reason": reason, "stage": led.current_stage,
    })


def _enter_slim(led: BudgetLedger) -> None:
    if led.mode == "hard_stop":
        return
    if led.mode != "slim_finish":
        led.mode = "slim_finish"
        led.soft_cap_crossed = True
        if not led.soft_crossed_at_stage:
            led.soft_crossed_at_stage = led.current_stage or "unknown"


def _enter_hard_stop(led: BudgetLedger) -> None:
    led.mode = "hard_stop"
    led.hard_stop = True
    if not led.hard_stop_stage:
        led.hard_stop_stage = led.current_stage or "unknown"


def _sync_mode(led: BudgetLedger) -> None:
    if led.spent_usd >= led.hard_cap_usd:
        _enter_hard_stop(led)
    elif led.spent_usd >= led.soft_cap_usd:
        _enter_slim(led)


def try_reserve(
    estimate: float,
    *,
    op: str,
    essential: bool | None = None,
) -> Reservation | None:
    """Reserve estimated maximum cost. None = refused (recorded on the ledger)."""
    est = max(0.0, float(estimate))
    is_ess = _essential.get() if essential is None else bool(essential)
    led = _ledger.get()
    if led is None:
        # Standalone stage scope: gate against stage cap via would_exceed.
        if _active.get() and (_spent.get() + est) > _cap.get():
            return None
        return Reservation(
            id=uuid.uuid4().hex[:12], estimate=est, op=op, essential=is_ess,
        )

    if led.mode == "hard_stop":
        # Even essential finish work must not start once hard-stopped.
        _record_refuse(led, op, "hard_stop")
        return None
    if led.committed() + est > led.hard_cap_usd + 1e-12:
        _record_refuse(led, op, "hard_cap")
        _enter_hard_stop(led)
        return None
    # Nested stage ``scoped`` ceiling (per-agent allowance under the article envelope).
    if _active.get() and (led.committed() + est) > _cap.get() + 1e-12:
        _record_refuse(led, op, "stage_cap")
        return None
    # Slim mode: only essential finish-path ops may reserve new spend.
    if led.mode == "slim_finish" and not is_ess:
        _record_refuse(led, op, "slim_finish")
        return None

    res = Reservation(
        id=uuid.uuid4().hex[:12], estimate=est, op=op,
        stage=led.current_stage, essential=is_ess,
    )
    led._open[res.id] = res
    led.reserved_usd = round(led.reserved_usd + est, 6)
    return res


def settle(reservation: Reservation | None, actual: float) -> None:
    """Apply actual usage against a reservation (or charge without one via add).

    If actual exceeds the reserved estimate, charge the real spend and record the overrun.
    Mode follows settled spend only (``_charge`` → ``_sync_mode``): soft → slim_finish,
    hard → hard_stop. Do **not** force slim on under-estimate alone — that used to strand
    ~$2 of hard headroom and kill mid-rail work (gauntlet review) while still under soft.
    """
    if reservation is None:
        add(actual)
        return
    act = max(0.0, float(actual))
    led = _ledger.get()
    if led is None:
        add(act)
        return
    held = led._open.pop(reservation.id, None)
    estimate = held.estimate if held is not None else 0.0
    if held is not None:
        led.reserved_usd = round(max(0.0, led.reserved_usd - held.estimate), 6)
    _charge(led, act, op=reservation.op)
    if act > estimate + 1e-9:
        _record_refuse(led, reservation.op, "reservation_overrun")


def release(reservation: Reservation | None) -> None:
    """Cancel a reservation with no spend."""
    if reservation is None:
        return
    led = _ledger.get()
    if led is None:
        return
    held = led._open.pop(reservation.id, None)
    if held is not None:
        led.reserved_usd = round(max(0.0, led.reserved_usd - held.estimate), 6)


def _charge(led: BudgetLedger, usd: float, *, op: str = "") -> None:
    usd = max(0.0, float(usd))
    if usd <= 0:
        _sync_mode(led)
        return
    led.spent_usd = round(led.spent_usd + usd, 6)
    _spent.set(led.spent_usd)
    stage = led.current_stage or "unknown"
    led.cost_by_stage[stage] = round(led.cost_by_stage.get(stage, 0.0) + usd, 6)
    if op:
        led.cost_by_op[op] = round(led.cost_by_op.get(op, 0.0) + usd, 6)
    _sync_mode(led)


def is_active() -> bool:
    return _active.get()


def add(usd: float) -> None:
    """Post-hoc charge. Prefer try_reserve/settle for hard-cap enforcement."""
    usd = max(0.0, float(usd))
    led = _ledger.get()
    if led is not None:
        _charge(led, usd)
        return
    _spent.set(_spent.get() + usd)


def add_model_usage(
    input_tokens: int = 0,
    output_tokens: int = 0,
    *,
    cached_input_tokens: int = 0,
    cache_write_tokens: int = 0,
    usage: Mapping[str, Any] | None = None,
) -> None:
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
    led = _ledger.get()
    if led is not None and _article_active.get():
        return round(max(0.0, led.spent_usd - _stage_start.get()), 6)
    return round(max(0.0, _spent.get() - _stage_start.get()), 6)


def article_spent_usd() -> float:
    led = _ledger.get()
    if led is not None:
        return round(led.spent_usd, 6)
    if not _article_active.get():
        return 0.0
    return round(_spent.get(), 6)


def remaining_usd() -> float:
    led = _ledger.get()
    if led is not None:
        hard_left = max(0.0, led.hard_cap_usd - led.committed())
        if _active.get():
            stage_left = max(0.0, _cap.get() - led.committed())
            return min(hard_left, stage_left)
        return hard_left
    return max(0.0, _cap.get() - _spent.get())


def over_cap() -> bool:
    led = _ledger.get()
    if led is not None:
        if led.spent_usd >= led.hard_cap_usd or led.mode == "hard_stop":
            return True
        if _active.get() and led.committed() >= _cap.get():
            return True
        return False
    return _active.get() and _spent.get() >= _cap.get()


def would_exceed(usd: float) -> bool:
    usd = max(0.0, float(usd))
    led = _ledger.get()
    if led is not None:
        if (led.committed() + usd) > led.hard_cap_usd:
            return True
        if _active.get() and (led.committed() + usd) > _cap.get():
            return True
        return False
    return _active.get() and (_spent.get() + usd) > _cap.get()


@contextmanager
def article_scoped(
    hard_usd: float | None = None,
    *,
    soft_usd: float | None = None,
    cap_usd: float | None = None,
) -> Iterator[None]:
    """Open the full-rail article budget (soft + hard).

    Positional / ``cap_usd`` set the hard ceiling.
    """
    hard = max(
        0.0,
        float(
            hard_usd if hard_usd is not None
            else (cap_usd if cap_usd is not None else hard_cap_usd())
        ),
    )
    soft = max(0.0, float(soft_usd if soft_usd is not None else soft_cap_usd()))
    if soft > hard:
        soft = hard
    led = BudgetLedger(soft_cap_usd=soft, hard_cap_usd=hard)
    tokens = (
        _ledger.set(led),
        _article_active.set(True),
        _cap.set(hard),
        _spent.set(0.0),
        _stage_start.set(0.0),
        _model.set(""),
        _active.set(True),
    )
    try:
        yield
    finally:
        _ledger.reset(tokens[0])
        _article_active.reset(tokens[1])
        _cap.reset(tokens[2])
        _spent.reset(tokens[3])
        _stage_start.reset(tokens[4])
        _model.reset(tokens[5])
        _active.reset(tokens[6])


@contextmanager
def scoped(cap_usd: float, model: str) -> Iterator[None]:
    """Meter and cap one stage's spend under the article hard remaining pool."""
    if _article_active.get():
        led = _ledger.get()
        start = led.spent_usd if led is not None else _spent.get()
        hard = led.hard_cap_usd if led is not None else hard_cap_usd()
        remaining = max(0.0, hard - start - (led.reserved_usd if led else 0.0))
        stage_ceiling = start + min(max(0.0, cap_usd), remaining)
        tokens = (
            _cap.set(stage_ceiling),
            _stage_start.set(start),
            _model.set(model),
            _active.set(True),
        )
        try:
            yield
        finally:
            _cap.reset(tokens[0])
            _stage_start.reset(tokens[1])
            _model.reset(tokens[2])
    else:
        # Standalone: also open a mini-ledger so reserve/settle works in tests.
        led = BudgetLedger(soft_cap_usd=cap_usd, hard_cap_usd=cap_usd)
        tokens = (
            _ledger.set(led),
            _cap.set(max(0.0, cap_usd)),
            _spent.set(0.0),
            _stage_start.set(0.0),
            _model.set(model),
            _active.set(True),
        )
        try:
            yield
        finally:
            _ledger.reset(tokens[0])
            _cap.reset(tokens[1])
            _spent.reset(tokens[2])
            _stage_start.reset(tokens[3])
            _model.reset(tokens[4])
            _active.reset(tokens[5])
