"""
Market contracts. A market is binary (YES/NO) with a YES price in [0, 1] read as a probability.

Everything on disk is one of four append-only line types (store.py): a Market REVISION, a price Snapshot, a Forecast and a paper
Trade. A forecast is never edited; a position's state is a projection of its trade lines.
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
