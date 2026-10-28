"""
The trader's mechanical guards. They live in code, not in the prompt: the agent may ask for anything, and this module decides what the book
will do. A request is never refused silently; it is CLIPPED to what is legal and every cut is written in ``Fill.clips`` (which the ledger keeps).

    * bankroll / cash: a buy never spends more cash than the book has, so cash cannot go negative;
    * ``MAX_POSITION_FRAC``: total cost in one market (adds included) stays inside this share of the fixed bankroll;
    * ``MAX_EXPOSURE_FRAC``: total cost across all open positions stays inside this share of it;
    * no shorting: the only way to bet against an outcome is to BUY the other side; holding YES and buying NO (or the reverse) is refused,
      the position must be sold first;
    * fills pay ``SLIPPAGE`` against the book (buys above the quote, sells below it); a mark pays none;
    * only open, priced markets trade; a ticket below ``TRADE_MIN_TICKET`` is not filled; a sell can never exceed the position.

Pure functions of their arguments (no store, no clock), so they are tested directly.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import flags
from .book import Holding, side_price

ACTIONS = ("buy_yes", "buy_no", "sell", "hold")


@dataclass
class Fill:
    action: str                          # what the book did: buy_yes | buy_no | sell | hold
    side: str = ""
    price: float = 0.0
    shares: float = 0.0
    cash_flow: float = 0.0               # negative on a buy
    realised: float = 0.0
    clips: list[str] = field(default_factory=list)


def _hold(held: Holding | None, clips: list[str]) -> Fill:
    return Fill("hold", held.side if held else "", clips=clips)


def apply(action: str, requested: float, *, held: Holding | None, yes_price: float | None, cash: float, exposure: float,
          tradable: bool, position_frac: float | None = None, exposure_frac: float | None = None, bankroll: float | None = None) -> Fill:
    """What the book does with one request. ``yes_price`` is the market's current YES price (None: no fresh price), ``exposure`` the cost of
    all open positions, ``tradable`` whether the market is still open. A book with its own caps (the day book) passes them; the default is the daily book's."""
    clips: list[str] = []
    requested = max(0.0, float(requested or 0.0))
    if action not in ACTIONS:
        return _hold(held, [f"unknown action {action!r}: held"])
    if action == "hold":
        return _hold(held, [])
    if not tradable:
        return _hold(held, ["market is closed to trading: held"])
    if yes_price is None:
        return _hold(held, ["no recent price on file: held"])
    return _sell(requested, held, yes_price, clips) if action == "sell" else _buy(action, requested, held, yes_price, cash, exposure, clips, (flags.MAX_POSITION_FRAC if position_frac is None else position_frac) * (flags.BANKROLL if bankroll is None else bankroll),
                                                                                                          (flags.MAX_EXPOSURE_FRAC if exposure_frac is None else exposure_frac) * (flags.BANKROLL if bankroll is None else bankroll))


def _buy(action: str, requested: float, held: Holding | None, yes_price: float, cash: float, exposure: float, clips: list[str], max_position: float, max_exposure: float) -> Fill:
    side = "yes" if action == "buy_yes" else "no"
    if held is not None and held.side != side:
        return _hold(held, [f"already holds {held.side.upper()}; sell it before buying {side.upper()}: held"])
    room = {"cash": cash, "position limit": max_position - (held.cost if held else 0.0),
            "exposure limit": max_exposure - exposure}
    stake = requested
    for name, limit in room.items():
        if stake > max(0.0, limit):
            clips.append(f"stake {stake:.0f} cut to {max(0.0, limit):.0f}: {name}")
            stake = max(0.0, limit)
    stake = round(stake, 2)
    if stake < flags.TRADE_MIN_TICKET:
        return _hold(held, [*clips, f"ticket {stake:.0f} below the {flags.TRADE_MIN_TICKET:.0f} minimum: held"] if requested else ["asked to buy nothing: held"])
    price = round(min(0.99, side_price(yes_price, side) + flags.SLIPPAGE), 4)
    return Fill(action, side, price, round(stake / price, 4), -stake, 0.0, clips)


def _sell(requested: float, held: Holding | None, yes_price: float, clips: list[str]) -> Fill:
    if held is None:
        return _hold(None, ["no position to sell: held"])
    price = round(max(0.01, side_price(yes_price, held.side) - flags.SLIPPAGE), 4)
    value = held.shares * price
    if requested <= 0:
        clips.append("no size given: closed the whole position")
        shares = held.shares
    elif requested >= value:
        shares = held.shares
    else:
        shares = requested / price
        if (held.shares - shares) * price < flags.TRADE_MIN_TICKET:
            clips.append("remainder below the minimum ticket: closed the whole position")
            shares = held.shares
    shares = held.shares if shares >= held.shares - 1e-9 else round(shares, 4)
    proceeds = round(shares * price, 2)
    realised = round(proceeds - held.cost * shares / held.shares, 2)
    return Fill("sell", held.side, price, shares, proceeds, realised, clips)


def floor_stake(p_yes: float, side: str, yes_price: float, bankroll: float) -> float:
    """The stake for a position taken only to fill the activity floor: fractional Kelly on the agent's OWN probability against the all-in price, never below the
    minimum ticket (no edge, or no probability given, means the ticket). The ordinary guards still clip it in ``apply``."""
    if not 0.0 < p_yes < 1.0:
        return flags.TRADE_MIN_TICKET
    q = p_yes if side == "yes" else 1.0 - p_yes
    cost = min(0.99, side_price(yes_price, side) + flags.SLIPPAGE)
    full = (q - cost) / (1.0 - cost)
    return round(max(flags.TRADE_MIN_TICKET, flags.KELLY_FRACTION * full * bankroll if full > 0 else 0.0), 2)
