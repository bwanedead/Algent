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


class EquityPoint(BaseModel):
    """A book's value at the end of a day: cash plus open positions at their current side price. Written once per (book, day), never edited."""

    book: Literal["trader", "rule"]
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
