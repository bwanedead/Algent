"""
The strategy roster: every live paper bot is one entry here, run by the one generic agentic loop (``day.py``). A strategy is a way of thinking (a lab mind,
``methods.py``, named by the lab's own id) plus a way of trading (style, horizon, caps, whether it must trade). Each is an INDEPENDENT mind: its own corpus
research and its own probability, its own $10,000 book, ledger lines (``Decision.book``), run traces, wishes and watchlist. Nothing reads another strategy's
forecasts or orders, and no desk forecast feeds any of them (the desk's blind forecaster survives only as the lab's frozen P0/P0b control and in the scoring of
past forecasts). ``daily`` and ``fast`` are the old trader books, kept on their ledgers and equity series so history is continuous, now forming their own view.

Values are read from ``flags.py`` when the roster is built (``roster()``), so a changed knob or a patched test flag takes effect without a reload.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from . import flags, methods


@dataclass(frozen=True)
class Strategy:
    id: str                       # the ledger tag (Decision.book) and the key of every per-strategy file line
    name: str
    method: str                   # a lab mind id: p0b | p0b+prior | b | b+prior
    style: str                    # the way it trades, in plain words (shown on the page)
    horizon_h: float              # markets it may trade end within this many hours
    run_hours: tuple[int, ...]    # UTC hours it runs, every day
    run_minute: int
    max_usd_day: float
    max_usd_run: float
    must_trade: bool = False
    min_orders: int = 0           # a must-trade run has to FILL at least this many orders (buys or sells)
    equity: str = ""              # the EquityPoint.book series ("" = the id)
    min_hours_left: float = 1.0
    enabled: bool = True
    max_turns: int = flags.STRAT_MAX_TURNS
    max_tool_calls: int = flags.STRAT_MAX_TOOL_CALLS
    calls_per_turn: int = flags.STRAT_MAX_CALLS_PER_TURN
    max_orders: int = flags.STRAT_MAX_ORDERS_PER_RUN
    call_cap_usd: float = flags.STRAT_CALL_CAP_USD
    effort: str = flags.STRAT_EFFORT
    position_frac: float = flags.DAY_MAX_POSITION_FRAC
    exposure_frac: float = flags.DAY_MAX_EXPOSURE_FRAC
    bankroll: float = flags.DAY_BANKROLL
    prompt_version: str = "day-v1"

    @property
    def series(self) -> str:
        return self.equity or self.id

    @property
    def method_name(self) -> str:
        return methods.NAMES[self.method]

    @property
    def slots(self) -> list[tuple[int, int]]:
        return [(h, self.run_minute) for h in self.run_hours]


def _new(id: str, name: str, method: str, style: str, hours: tuple[int, ...], minute: int, *, must: int = 0) -> Strategy:
    return Strategy(id=id, name=name, method=method, style=style, horizon_h=flags.STRAT_HORIZON_H, run_hours=hours, run_minute=minute,
                    max_usd_day=flags.STRAT_MAX_USD_PER_DAY, max_usd_run=flags.STRAT_MAX_USD_PER_RUN, must_trade=bool(must), min_orders=must,
                    enabled=flags.STRAT_ENABLED and flags.TRADE_ENABLED, prompt_version=f"{id}-v1")


def roster() -> list[Strategy]:
    daily_h, daily_m = (int(x) for x in flags.DAILY_UTC.split(":"))
    return [
        Strategy(id="day", name="Day bot", method="p0b", style="Opportunistic: picks its own bets, 0 to 2 days out", horizon_h=flags.DAY_HORIZON_H, run_hours=tuple(flags.DAY_RUN_HOURS),
                 run_minute=flags.DAY_RUN_MINUTE, max_usd_day=flags.DAY_MAX_USD_PER_DAY, max_usd_run=flags.DAY_MAX_USD_PER_RUN, min_hours_left=flags.DAY_MIN_HOURS_LEFT,
                 enabled=flags.DAY_ENABLED and flags.TRADE_ENABLED, max_turns=flags.DAY_MAX_TURNS, max_tool_calls=flags.DAY_MAX_TOOL_CALLS, calls_per_turn=flags.DAY_MAX_CALLS_PER_TURN,
                 max_orders=flags.DAY_MAX_ORDERS_PER_RUN, call_cap_usd=flags.DAY_CALL_CAP_USD, effort=flags.DAY_EFFORT, position_frac=flags.DAY_MAX_POSITION_FRAC,
                 exposure_frac=flags.DAY_MAX_EXPOSURE_FRAC, bankroll=flags.DAY_BANKROLL, prompt_version="day-v1"),
        Strategy(id="daily", name="Daily trader", method="p0b", style="Patient: once a day, any market up to 30 days out", horizon_h=flags.DAILY_STRAT_HORIZON_H, run_hours=(daily_h,),
                 run_minute=daily_m, max_usd_day=flags.DAILY_STRAT_MAX_USD_PER_DAY, max_usd_run=flags.STRAT_MAX_USD_PER_RUN, equity="trader", min_hours_left=flags.DAY_MIN_HOURS_LEFT,
                 enabled=flags.TRADE_ENABLED, prompt_version="daily-v2"),
        Strategy(id="fast", name="Fast trader", method="p0b", style="Short horizon: markets settling within a week, every 4 hours", horizon_h=flags.FAST_HORIZON_DAYS * 24,
                 run_hours=tuple(range(0, 24, flags.FAST_EVERY_H)), run_minute=20, max_usd_day=flags.FAST_STRAT_MAX_USD_PER_DAY, max_usd_run=flags.FAST_STRAT_MAX_USD_PER_RUN,
                 min_hours_left=flags.FAST_MIN_HOURS_LEFT, enabled=flags.FAST_ENABLED and flags.TRADE_ENABLED, prompt_version="fast-v2"),
        _new("base-rate", "Base-rate bot", "p0b+prior", "Starts from the base rate; trades only on edge the evidence earns", (9, 13, 17, 21), 5),
        _new("delineation", "Delineation bot", "b", "Maps the possible outcomes first, trades the ones the price mis-states", (10, 14, 18, 22), 5),
        _new("delineation-base-rate", "Delineation + base-rate bot", "b+prior", "Base rate first, then the possible outcomes", (11, 15, 19, 23), 5),
        _new("baseline-must-trade", "Baseline, must trade", "p0b", "Feedback fast: always places orders, best edge or else the smallest position", (9, 13, 17, 21), 35, must=2),
        _new("delineation-must-trade", "Delineation, must trade", "b", "Feedback fast: always places an order, best edge or else the smallest position", (10, 14, 18, 22), 55, must=1),
    ]


def ids() -> list[str]:
    return [s.id for s in roster()]


def get(strategy_id: str) -> Strategy:
    for s in roster():
        if s.id == strategy_id:
            return s
    raise KeyError(f"unknown strategy {strategy_id!r}; the roster is {ids()}")


def next_run(s: Strategy, now: datetime) -> datetime | None:
    """The next UTC slot of the strategy strictly after ``now``."""
    base = now.replace(second=0, microsecond=0)
    cands = [base.replace(hour=h, minute=m) + timedelta(days=d) for d in (0, 1) for h, m in s.slots]
    return min((c for c in cands if c > now), default=None)


def validate(rows: list[Strategy] | None = None) -> list[str]:
    """Problems with the roster (empty = sound): unique ids, lab method ids, usable caps, a must-trade strategy that can actually fill its minimum."""
    rows = rows if rows is not None else roster()
    bad: list[str] = []
    seen: set[str] = set()
    for s in rows:
        if s.id in seen:
            bad.append(f"duplicate id {s.id}")
        seen.add(s.id)
        if s.method not in methods.NAMES:
            bad.append(f"{s.id}: method {s.method!r} is not a lab mind id")
        if not s.run_hours or any(not 0 <= h < 24 for h in s.run_hours) or not 0 <= s.run_minute < 60:
            bad.append(f"{s.id}: bad run times")
        if s.max_usd_run <= 0 or s.max_usd_day < s.max_usd_run * 0.5 or s.horizon_h <= s.min_hours_left:
            bad.append(f"{s.id}: caps or horizon unusable")
        if s.must_trade and not 1 <= s.min_orders <= s.max_orders:
            bad.append(f"{s.id}: must_trade needs 1..max_orders minimum orders")
        if not s.must_trade and s.min_orders:
            bad.append(f"{s.id}: min_orders without must_trade")
    return bad
