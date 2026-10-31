"""
The paper portfolio. PAPER ONLY: this module writes lines to ``trades.jsonl`` and nothing else; it has no way to reach a venue.

Rules (every number in ``flags.py``, with its reason):

* OPEN. A market with a forecast of ours and no position gets one when the gap between our probability and the market's current price is at
  least ``EDGE_MIN``. The side is YES when we are above the market, NO when below. The fill is at the quoted price of that side plus
  ``SLIPPAGE`` (a stand-in for spread). Size is fractional Kelly for a binary contract: with our probability q for the side and cost c,
  full Kelly stakes (q - c) / (1 - c) of the bankroll; we stake ``KELLY_FRACTION`` of that, never more than ``MAX_POSITION_FRAC`` of the
  (fixed) bankroll, and never past ``MAX_EXPOSURE_FRAC`` open in total.
* MARK. Once per UTC day each open position is valued at the current price of its side (no slippage): the mark-to-market.
* SETTLE. When the market resolves the position pays 1 per share if its side won, 0 if it lost, and 0.5 on a void (50-50) resolution.
  A position is never closed early, never added to, never flipped: a later forecast does not change an open position.

This is the RULE book: the mechanical baseline the agent's book (``trader.py``) is compared with. Valuation and payout are shared (``book.py``).
The bankroll is a constant, not compounded: P&L is read against it, so a bad run cannot hide by shrinking the stake base.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from . import flags, sizing, store
from .book import payout, side_price
from .contracts import Forecast, Market, Snapshot, Trade, trade_id


@dataclass
class Position:
    market_id: str
    side: str
    price: float
    stake: float
    shares: float
    opened_at: str
    forecast_id: str
    ours: float
    market_at_open: float
    status: str = "open"                 # open | settled
    value: float = 0.0
    pnl: float = 0.0
    outcome: str = ""
    settled_at: str = ""
    marked_at: str = ""


def kelly_stake(q: float, cost: float) -> float:
    """Paper dollars for a binary contract: fractional Kelly, capped. ``q`` is our probability for the side, ``cost`` its all-in price."""
    full = sizing.full_kelly(q, cost)               # the retired rule book trusts its desk forecast fully (w=1, no extreme cap): its history is unchanged
    if full <= 0:
        return 0.0
    return round(min(flags.KELLY_FRACTION * full, flags.MAX_POSITION_FRAC) * flags.BANKROLL, 2)


def positions(trades: list[Trade] | None = None) -> dict[str, Position]:
    """Each market's position, projected from its trade lines."""
    out: dict[str, Position] = {}
    for t in sorted(trades if trades is not None else store.trades(), key=lambda t: t.at):
        if t.kind == "open":
            out[t.market_id] = Position(t.market_id, t.side, t.price, t.stake, t.shares, t.at, t.forecast_id, t.ours, t.market,
                                        value=t.stake, marked_at=t.at)
        elif (p := out.get(t.market_id)) is not None and p.status == "open":
            if t.kind == "mark":
                p.value, p.pnl, p.marked_at = t.value, t.pnl, t.at
            else:
                p.status, p.value, p.pnl, p.outcome, p.settled_at = "settled", t.value, t.pnl, t.note, t.at
    return out


def latest_forecasts() -> dict[str, Forecast]:
    out: dict[str, Forecast] = {}
    for f in sorted(store.forecasts(), key=lambda f: f.made_at):
        out[f.market_id] = f
    return out


def _fresh_price(rows: list[Snapshot], now: datetime) -> Snapshot | None:
    live = [s for s in rows if s.source == "live"]
    return store.price_at(live, now.isoformat(), max_age_h=flags.PRICE_FRESH_H)


def run(*, now: datetime | None = None) -> dict[str, Any]:
    """One paper pass: settle what resolved, open what the rule says, mark what is open. Free (no model, no network)."""
    now = now or datetime.now(UTC)
    at, day = now.isoformat(timespec="seconds"), now.date().isoformat()
    ms, by_price, fcs = store.markets(), store.snapshots_by_market(), latest_forecasts()
    pos = positions()
    new: list[Trade] = []
    out = {"as_of": at, "opened": 0, "marked": 0, "settled": 0, "skipped_small": 0}

    # settle
    for mid, p in pos.items():
        m = ms.get(mid)
        if p.status != "open" or m is None or m.status == "open":
            continue
        value = round(p.shares * payout(m.outcome, p.side), 2)
        new.append(Trade(id=trade_id(mid, "settle", at), market_id=mid, kind="settle", at=at, side=p.side, price=p.price, stake=p.stake, shares=p.shares,
                         value=value, pnl=round(value - p.stake, 2), ours=p.ours, forecast_id=p.forecast_id, note=m.outcome))
        p.status = "settled"
        out["settled"] += 1

    exposure = sum(p.stake for p in pos.values() if p.status == "open")
    # open
    for mid, f in sorted(fcs.items() if flags.RULE_BOOK_ENABLED else [], key=lambda kv: -abs(kv[1].p - 0.5)):   # retired: no desk forecast feeds a bot any more
        m = ms.get(mid)
        if m is None or m.status != "open" or mid in pos:
            continue
        snap = _fresh_price(by_price.get(mid, []), now)
        if snap is None:
            continue
        edge = f.p - snap.p
        if abs(edge) < flags.EDGE_MIN:
            continue
        side = "yes" if edge > 0 else "no"
        cost = min(0.99, side_price(snap.p, side) + flags.SLIPPAGE)
        q = f.p if side == "yes" else 1.0 - f.p
        stake = min(kelly_stake(q, cost), max(0.0, flags.MAX_EXPOSURE_FRAC * flags.BANKROLL - exposure))
        if stake < 1.0:
            out["skipped_small"] += 1
            continue
        t = Trade(id=trade_id(mid, "open", at), market_id=mid, kind="open", at=at, side=side, price=round(cost, 4), stake=round(stake, 2),
                  shares=round(stake / cost, 4), ours=f.p, market=snap.p, forecast_id=f.id,
                  note=f"edge {edge:+.2f}: ours {f.p:.2f} vs market {snap.p:.2f}")
        new.append(t)
        pos[mid] = Position(mid, side, t.price, t.stake, t.shares, at, f.id, f.p, snap.p, value=t.stake, marked_at=at)
        exposure += t.stake
        out["opened"] += 1

    # mark
    for mid, p in pos.items():
        if p.status != "open" or p.marked_at[:10] == day:
            continue
        snap = _fresh_price(by_price.get(mid, []), now)
        if snap is None:
            continue
        value = round(p.shares * side_price(snap.p, p.side), 2)
        new.append(Trade(id=trade_id(mid, "mark", at), market_id=mid, kind="mark", at=at, side=p.side, price=p.price, stake=p.stake, shares=p.shares,
                         value=value, pnl=round(value - p.stake, 2), ours=p.ours, market=snap.p, forecast_id=p.forecast_id))
        out["marked"] += 1
    store.append_trades(new)
    return out


def summary(pos: dict[str, Position] | None = None) -> dict[str, Any]:
    pos = pos if pos is not None else positions()
    open_ = [p for p in pos.values() if p.status == "open"]
    done = [p for p in pos.values() if p.status == "settled"]
    realised = round(sum(p.pnl for p in done), 2)
    unreal = round(sum(p.pnl for p in open_), 2)
    return {"bankroll": flags.BANKROLL, "open": len(open_), "settled": len(done), "staked_open": round(sum(p.stake for p in open_), 2),
            "realised_pnl": realised, "unrealised_pnl": unreal, "total_pnl": round(realised + unreal, 2),
            "return_on_bankroll": round((realised + unreal) / flags.BANKROLL, 4),
            "wins": sum(p.pnl > 0 for p in done), "losses": sum(p.pnl < 0 for p in done),
            "hit_rate": round(sum(p.pnl > 0 for p in done) / len(done), 3) if done else None}


def market_of(p: Position) -> Market | None:
    return store.markets().get(p.market_id)
