"""
The shared book arithmetic: positions, cash, settlement payout, mark-to-market and the daily equity point. Used by BOTH books, so there is one
definition of how a position is valued and how a market's resolution pays:

* the TRADER (``trader.py``): the agent's book, projected from ``decisions.jsonl`` (buy / sell / settle lines);
* the RULE book (``paper.py``): the mechanical edge-rule baseline, projected from ``trades.jsonl``.

Both start from the same fixed ``flags.BANKROLL`` of paper dollars (not compounded: P&L is read against it), so their curves and the flat
bankroll line are directly comparable. PAPER ONLY: this module computes; it has no way to reach a venue.

    cash      = BANKROLL - what open positions cost + realised P&L  (equivalently: BANKROLL + sum of cash flows)
    holdings  = open positions valued at their side's current price (no slippage on a mark)
    equity    = cash + holdings;  P&L = equity - BANKROLL
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from . import flags, store
from .contracts import Decision, EquityPoint, Snapshot

VOID_PAYOUT = 0.5


@dataclass
class Holding:
    market_id: str
    side: str
    shares: float
    cost: float                  # dollars paid for the shares still held (the cost basis)
    opened_at: str
    entry: float                 # average price paid per share


def side_price(p_yes: float, side: str) -> float:
    return p_yes if side == "yes" else 1.0 - p_yes


def payout(outcome: str, side: str) -> float:
    """Per-share payout at resolution: 1 if the side won, 0 if it lost, 0.5 on a void (50-50) resolution."""
    return VOID_PAYOUT if outcome == "void" else (1.0 if outcome == side else 0.0)


def holdings(decisions: list[Decision]) -> dict[str, Holding]:
    """The trader's open positions, projected from its ledger. A sell removes shares at average cost; a settle removes the position."""
    out: dict[str, Holding] = {}
    for d in sorted(decisions, key=lambda d: d.at):
        h = out.get(d.market_id)
        if d.action in ("buy_yes", "buy_no") and d.shares > 0:
            if h is None:
                out[d.market_id] = Holding(d.market_id, d.side, d.shares, -d.cash_flow, d.at, d.price)
            else:
                h.shares, h.cost = h.shares + d.shares, h.cost - d.cash_flow
                h.entry = h.cost / h.shares
        elif d.action == "sell" and h is not None and d.shares > 0:
            keep = max(0.0, 1.0 - d.shares / h.shares)
            h.shares, h.cost = h.shares * keep, h.cost * keep
            if h.shares < 1e-6:
                del out[d.market_id]
        elif d.action == "settle" and h is not None:
            del out[d.market_id]
    return out


def cash(decisions: list[Decision]) -> float:
    return round(flags.BANKROLL + sum(d.cash_flow for d in decisions), 2)


def realised(decisions: list[Decision]) -> float:
    return round(sum(d.realised for d in decisions), 2)


def last_price(rows: list[Snapshot]) -> float | None:
    """The newest live YES price on file, however old (a mark prefers a stale price to none)."""
    live = [s for s in rows if s.source == "live"]
    return live[-1].p if live else None


def point(book: str, now: datetime, *, cash_: float, held: dict[str, Holding], realised_: float,
          prices: dict[str, list[Snapshot]]) -> EquityPoint:
    """The book's equity at ``now``. A position with no price on file is valued at cost."""
    value = 0.0
    for h in held.values():
        p = last_price(prices.get(h.market_id, []))
        value += h.shares * side_price(p, h.side) if p is not None else h.cost
    cost = sum(h.cost for h in held.values())
    return EquityPoint(book=book, day=now.date().isoformat(), at=now.isoformat(timespec="seconds"), cash=round(cash_, 2), holdings=round(value, 2),
                       equity=round(cash_ + value, 2), realised=round(realised_, 2), unrealised=round(value - cost, 2), n_open=len(held))


def rule_point(now: datetime, prices: dict[str, list[Snapshot]]) -> EquityPoint:
    """The mechanical rule book's equity, from its paper trades (so it is valued by exactly the same function as the trader)."""
    from . import paper

    pos = paper.positions()
    held = {mid: Holding(mid, p.side, p.shares, p.stake, p.opened_at, p.price) for mid, p in pos.items() if p.status == "open"}
    done = round(sum(p.pnl for p in pos.values() if p.status == "settled"), 2)
    return point("rule", now, cash_=flags.BANKROLL - sum(h.cost for h in held.values()) + done, held=held, realised_=done, prices=prices)


def mark(now: datetime | None = None) -> list[EquityPoint]:
    """Write today's equity point for each book (once per book per day: an existing day is left as first written). Returns what was written."""
    now = now or datetime.now(UTC)
    prices = store.snapshots_by_market()
    ds = store.decisions()
    pts = [point("trader", now, cash_=cash(ds), held=holdings(ds), realised_=realised(ds), prices=prices), rule_point(now, prices)]
    have = {(e.book, e.day) for e in store.equity_points()}
    fresh = [p for p in pts if (p.book, p.day) not in have]
    store.append_equity(fresh)
    return fresh
