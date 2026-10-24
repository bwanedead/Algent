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


class EquityPoint(BaseModel):
    """A book's value at the end of a day: cash plus open positions at their current side price. Written once per (book, day), never edited."""

    book: Literal["trader", "rule", "fast", "day"]
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


def day_run_id(at: str) -> str:
    return "dr-" + hashlib.sha1(at.encode()).hexdigest()[:14]
