"""
The trader's part of the published track record: equity curves (trader vs rule book vs the flat bankroll), open positions with the
agent's own words, and the reverse-chronological trade log with each trade's outcome once its market resolved. Read-only projections of the
ledgers (``decisions.jsonl``, ``equity.jsonl``) and the mirror; nothing here writes.
"""

from __future__ import annotations

from typing import Any

from . import book, flags, paper, store
from .contracts import Decision

LOG_ROWS = 200


def _side_won(side: str, outcome: str) -> bool | None:
    return None if outcome not in ("yes", "no") else outcome == side


def curve() -> list[dict[str, Any]]:
    """One row per day: both books' equity and the flat bankroll (what doing nothing would be worth)."""
    days: dict[str, dict[str, Any]] = {}
    for e in store.equity_points():
        days.setdefault(e.day, {"day": e.day, "flat": flags.BANKROLL, "trader": None, "rule": None})[e.book] = e.equity
    return [days[d] for d in sorted(days)]


def _closed(ds: list[Decision]) -> dict[str, float]:
    """Realised result per market for positions that are fully out (sold down to nothing, or settled)."""
    held = book.holdings(ds)
    pnl: dict[str, float] = {}
    for d in ds:
        if d.realised or d.action in ("sell", "settle"):
            pnl[d.market_id] = pnl.get(d.market_id, 0.0) + d.realised
    return {m: round(v, 2) for m, v in pnl.items() if m not in held}


def _summary(ds: list[Decision]) -> dict[str, Any]:
    eq = [e for e in store.equity_points() if e.book == "trader"]
    last = eq[-1] if eq else None
    closed = _closed(ds)
    wins = sum(v > 0 for v in closed.values())
    return {"equity": last.equity if last else flags.BANKROLL, "pnl": round(last.equity - flags.BANKROLL, 2) if last else 0.0,
            "cash": last.cash if last else flags.BANKROLL, "realised": book.realised(ds), "unrealised": last.unrealised if last else 0.0,
            "open": len(book.holdings(ds)), "buys": sum(d.action in ("buy_yes", "buy_no") for d in ds), "sells": sum(d.action == "sell" for d in ds),
            "closed": len(closed), "wins": wins, "losses": sum(v < 0 for v in closed.values()),
            "hit_rate": round(wins / len(closed), 3) if closed else None}


def _last_words(ds: list[Decision]) -> dict[str, Decision]:
    out: dict[str, Decision] = {}
    for d in sorted(ds, key=lambda d: d.at):
        if d.rationale:
            out[d.market_id] = d
    return out


def open_positions(ds: list[Decision]) -> list[dict[str, Any]]:
    ms, prices, held, words = store.markets(), store.snapshots_by_market(), book.holdings(ds), _last_words(ds)
    rows = []
    for mid, h in held.items():
        m = ms.get(mid)
        p = book.last_price(prices.get(mid, []))
        if m is None:
            continue
        value = h.shares * book.side_price(p, h.side) if p is not None else h.cost
        w = words.get(mid)
        rows.append({"market_id": mid, "question": m.question, "url": m.url, "ends": m.end_date[:10], "side": h.side, "shares": round(h.shares, 2),
                     "entry": round(h.entry, 4), "now": None if p is None else round(book.side_price(p, h.side), 4), "cost": round(h.cost, 2),
                     "value": round(value, 2), "pnl": round(value - h.cost, 2), "opened": h.opened_at[:10],
                     "rationale": w.rationale if w else "", "rationale_on": w.day if w else "", "ours": w.ours if w else None})
    return sorted(rows, key=lambda r: -r["cost"])


def log(ds: list[Decision], limit: int = LOG_ROWS) -> list[dict[str, Any]]:
    """Every fill and settlement, newest first. A buy shows how it turned out once the market resolved (``result``: won | lost | void, else
    open or sold); a sell and a settlement show what they realised."""
    ms = store.markets()
    out = []
    for d in sorted((d for d in ds if d.action != "hold"), key=lambda d: d.at, reverse=True)[:limit]:
        m = ms.get(d.market_id)
        outcome = m.outcome if m and m.status != "open" else ""
        result = ""
        if d.action in ("buy_yes", "buy_no"):
            won = _side_won(d.side, outcome)
            result = "void" if outcome == "void" else ("" if won is None else "won" if won else "lost")
        out.append({"id": d.id, "market_id": d.market_id, "question": m.question if m else d.market_id, "url": m.url if m else "", "day": d.day,
                    "action": d.action, "side": d.side, "price": d.price, "stake": round(abs(d.cash_flow), 2), "shares": round(d.shares, 2),
                    "pnl": d.realised if d.action in ("sell", "settle") else None, "result": result, "outcome": outcome, "rationale": d.rationale,
                    "ours": d.ours, "market": d.market, "clips": d.clips})
    return out


def today(ds: list[Decision], day: str) -> dict[str, int]:
    mine = [d for d in ds if d.day == day and d.action != "settle"]
    return {"decided": len(mine), "bought": sum(d.action in ("buy_yes", "buy_no") for d in mine), "sold": sum(d.action == "sell" for d in mine),
            "held": sum(d.action == "hold" for d in mine), "clipped": sum(bool(d.clips) for d in mine)}


def section(day: str | None = None) -> dict[str, Any]:
    ds = store.decisions()
    day = day or store.now_iso()[:10]
    return {"summary": _summary(ds), "rule": paper.summary(), "curve": curve(), "open_positions": open_positions(ds), "log": log(ds),
            "today": today(ds, day), "since": min((d.day for d in ds), default=""), "spend_usd": round(sum(d.usd for d in ds), 4),
            "limits": {"bankroll": flags.BANKROLL, "max_position_frac": flags.MAX_POSITION_FRAC, "max_exposure_frac": flags.MAX_EXPOSURE_FRAC,
                       "slippage": flags.SLIPPAGE, "min_ticket": flags.TRADE_MIN_TICKET}}
