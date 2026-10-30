"""
Market contracts. A market is binary (YES/NO) with a YES price in [0, 1] read as a probability.

Everything on disk is one of these append-only line types (store.py): a Market REVISION, a price Snapshot, a Forecast, a rule-book paper
Trade, a trader Decision and a daily EquityPoint. Nothing is ever edited; a position's state is a projection of its lines.
"""

from __future__ import annotations

import hashlib
from typing import Literal

from pydantic import BaseModel, Field

Status = Literal["open", "resolved", "void"]
Outcome = Literal["", "yes", "no", "void"]


class Market(BaseModel):
    id: str                                   # Polymarket market id
    event_id: str = ""
    event_title: str = ""
    question: str
    slug: str = ""
    url: str = ""
    description: str = ""                     # the market's own resolution rules, trimmed
    tags: list[str] = Field(default_factory=list)
    token_yes: str = ""                       # CLOB token id of the YES outcome (price history)
    end_date: str = ""                        # ISO instant
    volume: float = 0.0
    liquidity: float = 0.0
    status: Status = "open"
    outcome: Outcome = ""
    resolved_at: str = ""
    theaters: list[str] = Field(default_factory=list)      # theater ids this market bears on (mapping.py)
    countries: list[str] = Field(default_factory=list)     # ISO2 found in the question
    map_score: int = 0
    first_seen: str = ""
    updated_at: str = ""
    origin: str = ""                                       # "day" = saved only because the day book bought it (not mirrored for us: never forecast)


class Snapshot(BaseModel):
    market_id: str
    at: str                                   # ISO instant
    p: float                                  # YES price, 0..1 (mid when both sides are quoted, else last trade)
    bid: float | None = None
    ask: float | None = None
    last: float | None = None
    volume: float = 0.0
    source: Literal["live", "history"] = "live"


class Forecast(BaseModel):
    id: str
    market_id: str
    made_at: str
    p: float                                  # OUR probability of YES, clamped to the bounds in flags
    rationale: str = ""
    evidence_ids: list[str] = Field(default_factory=list)   # what the forecaster cited (theater ids, statement ids, calendar ids)
    theaters: list[str] = Field(default_factory=list)
    model: str = ""
    prompt_version: str = ""
    usd: float = 0.0
    book: str = "daily"                       # which pass made it: "daily" or "fast" (the fast pass forecasts the markets it trades)
    evidence: str = ""                        # the forecaster's own verdict on its evidence: sufficient | thin | gap ("" before research existed)
    hours_to_end: float | None = None         # time to the market's end when forecast (for horizon splits)


class ForecastFailure(BaseModel):
    """A forecast call that produced no usable probability: kept as a visible row (what was said, why it was refused, what it cost), never dropped."""

    id: str                                   # the forecast id it would have had
    market_id: str
    made_at: str
    raw: str = ""                             # the model's raw probability value (repr), or "" when the call itself failed
    reason: str
    usd: float = 0.0
    book: str = "daily"
    prompt_version: str = ""


class Trade(BaseModel):
    """One paper action. ``open`` stakes ``stake`` paper dollars on ``side`` at ``price`` (the price of THAT side, after slippage);
    ``mark`` is the daily mark-to-market; ``settle`` closes the position at the outcome."""

    id: str
    market_id: str
    kind: Literal["open", "mark", "settle"]
    at: str
    side: Literal["yes", "no"] = "yes"
    price: float = 0.0
    stake: float = 0.0
    shares: float = 0.0
    value: float = 0.0                        # mark: current value of the position; settle: payout
    pnl: float = 0.0                          # mark: unrealised; settle: realised
    ours: float = 0.0
    market: float = 0.0
    forecast_id: str = ""
    note: str = ""


def forecast_id(market_id: str, made_at: str) -> str:
    return "fc-" + hashlib.sha1(f"{market_id}|{made_at}".encode()).hexdigest()[:14]


def trade_id(market_id: str, kind: str, at: str) -> str:
    return "tr-" + hashlib.sha1(f"{market_id}|{kind}|{at}".encode()).hexdigest()[:14]


class Decision(BaseModel):
    """One line of the trader's ledger: what the agent decided about one market on one day and what the book did about it.

    ``action`` is the agent's call (buy_yes | buy_no | sell | hold) or ``settle`` (written by the book when a held market resolves). A buy
    spends ``-cash_flow`` paper dollars for ``shares`` at ``price`` (the side's quote plus slippage); a sell or settle returns ``cash_flow``
    and books ``realised`` against the cost of what left. ``clips`` records every way a mechanical guard cut the request (an empty list
    means it was filled as asked); a hold that was clipped from a buy shows both."""

    id: str
    market_id: str
    at: str
    day: str
    action: Literal["buy_yes", "buy_no", "sell", "hold", "settle"]
    requested: float = 0.0                    # stake the agent asked for (paper dollars)
    side: Literal["yes", "no", ""] = ""       # the side of the position acted on ("" for a hold with no position)
    price: float = 0.0                        # per-share fill price after slippage (0 when nothing filled)
    shares: float = 0.0
    cash_flow: float = 0.0                    # negative = cash spent on a buy
    realised: float = 0.0                     # sell / settle only: payout minus the cost basis of the shares that left
    rationale: str = ""                       # the agent's own words, reader-facing
    clips: list[str] = Field(default_factory=list)
    ours: float | None = None                 # our blind probability of YES when the agent decided
    market: float | None = None               # the market's YES price when the agent decided
    forecast_id: str = ""
    outcome: str = ""                         # settle only: yes | no | void
    model: str = ""
    prompt_version: str = ""
    usd: float = 0.0                          # this line's share of the call's cost
    book: str = "daily"                       # "daily" (the trader) or "fast" (the short-horizon book): two ledgers in one file
    evidence_ids: list[str] = Field(default_factory=list)   # corpus items the decision cited
    evidence: str = ""                        # sufficient | thin | gap ("" before research existed)
    hours_to_end: float | None = None
    basis: str = ""                           # a strategy order: the working its reasoning method asked for (reference class, possibilities ...), plain text
    tag: str = ""                             # "floor": a buy taken while under the minimum-exposure floor with no real edge; "resting": a fill of a resting limit order (resting.py)
    order_id: str = ""                        # a resting fill only: the RestingOrder it filled


class EquityPoint(BaseModel):
    """A book's value at the end of a day: cash plus open positions at their current side price. Written once per (book, day), never edited."""

    book: str                                 # the series: trader | rule | fast | day | a roster strategy id (strategies.py)
    day: str
    at: str
    cash: float
    holdings: float
    equity: float
    realised: float
    unrealised: float
    n_open: int


def decision_id(market_id: str, action: str, at: str) -> str:
    return "td-" + hashlib.sha1(f"{market_id}|{action}|{at}".encode()).hexdigest()[:14]


def resting_id(book: str, market_id: str, action: str, placed_at: str) -> str:
    return "ro-" + hashlib.sha1(f"{book}|{market_id}|{action}|{placed_at}".encode()).hexdigest()[:10]


class RestingOrder(BaseModel):
    """A paper limit order that waits between runs (``resting.py``). Append-only: the order is written ``open`` when placed and every later transition (filled,
    expired, cancelled) is a NEW line carrying the whole record again, so the last line per ``id`` is its state and the earlier lines are the audit trail.

    ``limit_price`` is the ALL-IN price on the order's own side (slippage included, the same price an immediate fill pays): a buy fills while that price is at or below the
    limit, a sell while it is at or above. ``usd`` sizes a buy; a sell closes ``fraction`` of the position held at fill time."""

    id: str
    book: str
    market_id: str
    action: Literal["buy_yes", "buy_no", "sell"]
    limit_price: float
    usd: float = 0.0
    fraction: float = 0.0
    p_yes: float
    reason: str = ""
    placed_at: str
    expires_at: str
    status: Literal["open", "filled", "expired", "cancelled"] = "open"
    at: str = ""                              # when THIS line was written (placement, or the transition)
    filled_at: str = ""
    fill_id: str = ""
    note: str = ""                            # why a transition happened (expiry, cancellation, a cap that blocked the fill)


# ── research traces and gaps (research.py, trace.py, gaps.py) ────────────────────────────────────
class QueryRun(BaseModel):
    """One planned corpus query and what it returned."""

    tool: str
    arg: str = ""
    since: str = ""
    kinds: list[str] = Field(default_factory=list)
    n: int = 0                                # rows returned (after the blindness filter)
    new: int = 0                              # of which not already found by an earlier query for the same market
    ids: list[str] = Field(default_factory=list)
    ms: int = 0
    error: str = ""


class Trace(BaseModel):
    """How one forecast or decision was researched: queries issued, ids returned, ids cited, cost and latency. Append-only; pruned by age."""

    id: str
    at: str
    kind: Literal["forecast", "trade"]
    book: str = "daily"
    market_id: str
    ref: str = ""                             # the forecast / decision line this trace belongs to
    mode: str = "corpus"                      # corpus | base-fallback (no corpus index here) | base (research switched off)
    rounds: int = 0
    queries: list[QueryRun] = Field(default_factory=list)
    returned_ids: list[str] = Field(default_factory=list)
    shown_ids: list[str] = Field(default_factory=list)       # returned AND fitted into what the decision read
    cited_ids: list[str] = Field(default_factory=list)
    evidence: str = ""                        # the decision's own verdict: sufficient | thin | gap
    gap_topic: str = ""
    tokens: int = 0                           # estimated: characters / 4 of what was read and written
    plan_usd: float = 0.0
    usd: float = 0.0                          # planning + decision
    latency_ms: int = 0


class Gap(BaseModel):
    """One ask from a bot: it needed this and the corpus did not hold it."""

    id: str
    at: str
    day: str
    topic: str
    why: str = ""
    market_id: str
    question: str = ""
    book: str = "daily"
    kind: str = "forecast"                    # forecast | trade


class GapFill(BaseModel):
    """One research run started for a gap cluster (append-only; a gap is filled when a line for its topic exists inside the refill window)."""

    id: str
    at: str
    day: str
    key: str                                  # the cluster's token key (gaps.cluster_key)
    topic: str
    asks: int = 1
    markets: list[str] = Field(default_factory=list)
    ok: bool = False
    usd: float = 0.0                          # booked at the estimate until measured
    note: str = ""


def trace_id(kind: str, ref: str, at: str) -> str:
    return "rt-" + hashlib.sha1(f"{kind}|{ref}|{at}".encode()).hexdigest()[:14]


def gap_id(market_id: str, topic: str, at: str) -> str:
    return "gp-" + hashlib.sha1(f"{market_id}|{topic}|{at}".encode()).hexdigest()[:14]


# ── the day book's runs (day.py) ─────────────────────────────────────────────────────────────────
class ToolEvent(BaseModel):
    """One tool call of a day run: what the agent asked for, what came back (clipped) and how long it took."""

    n: int
    turn: int
    tool: str
    args: dict = Field(default_factory=dict)
    result: str = ""                          # what the agent was shown (clipped to flags.DAY_RESULT_CHARS)
    ok: bool = True
    ms: int = 0
    market_id: str = ""                       # the market the call concerned, when it did
    ref: str = ""                             # buy / sell: the ledger line (Decision.id) it produced or tried to


class DayRun(BaseModel):
    """The full trace of one run of the day book: every tool call, the orders it led to, the cost and why it stopped. Append-only; pruned by age."""

    id: str
    at: str
    day: str
    turns: int = 0
    tool_calls: int = 0
    events: list[ToolEvent] = Field(default_factory=list)
    considered: list[dict] = Field(default_factory=list)    # markets the agent looked at: {id, question, ends}
    queries: list[str] = Field(default_factory=list)        # corpus queries, as "tool(arg)"
    orders: list[str] = Field(default_factory=list)         # Decision ids written by buy / sell calls (filled, clipped and refused alike)
    summary: str = ""                                       # the agent's own closing note on what it did and why
    usd: float = 0.0
    tokens: int = 0                                         # estimated (characters / 4)
    stopped: str = ""                                       # why the loop ended: done | turn limit | tool-call limit | run budget | day budget | error ...
    settled: int = 0
    equity: float | None = None
    cash: float | None = None
    strategy: str = "day"                                   # which roster strategy ran (lines written before the roster are the day book's)
    must_trade: str = ""                                    # a must-trade run: "met" | "unmet: n of m" ("" for others)
    forecasts: int = 0                                      # distinct markets this run gave its own probability for
    exposure_pct: float | None = None                       # share of the bankroll at risk when the run ended


class Wish(BaseModel):
    """Product feedback from the day agent at the end of a run: information it wanted that our corpus lacks, and what would supply it. Not a research
    request (``request_research`` asks for a topic now); this says which data SOURCES to add. Append-only."""

    id: str
    at: str
    day: str
    run_id: str
    topic: str
    why: str = ""                             # why it mattered, for which market
    market_id: str = ""
    question: str = ""
    source: str = ""                          # the source or data type that would supply it
    strategy: str = "day"


class WatchEvent(BaseModel):
    """The agent's watchlist, persisted between runs as add / remove events (the list is their projection; the last event per market wins)."""

    id: str
    at: str
    market_id: str
    action: Literal["add", "remove"]
    question: str = ""
    note: str = ""
    strategy: str = "day"


def wish_id(run_id: str, topic: str) -> str:
    return "ws-" + hashlib.sha1(f"{run_id}|{topic}".encode()).hexdigest()[:14]


def day_run_id(at: str) -> str:
    return "dr-" + hashlib.sha1(at.encode()).hexdigest()[:14]


class BotForecast(BaseModel):
    """One strategy's own probability for one market, made during a run whether or not it traded. Append-only, per strategy, never shown to another bot. Scored on
    resolution against the outcome and against ``market`` (the YES price when it was made)."""

    id: str
    strategy: str
    run_id: str
    market_id: str
    at: str
    day: str
    p: float                                  # probability of YES, clipped inside P_MIN..P_MAX
    market: float | None = None               # the market's YES price at that moment
    confidence: str = ""                      # low | medium | high | ""
    reason: str = ""
    question: str = ""


def bot_forecast_id(strategy: str, run_id: str, market_id: str) -> str:
    return "bf-" + hashlib.sha1(f"{strategy}|{run_id}|{market_id}".encode()).hexdigest()[:14]
