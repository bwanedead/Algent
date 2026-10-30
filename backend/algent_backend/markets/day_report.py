"""
The day book's part of the published track record, and the ledger statistics its own ``performance()`` tool reads. Read-only projections of
``decisions.jsonl`` (``book: "day"``), ``day_runs.jsonl``, ``day_wishes.jsonl`` and the mirror; nothing here writes.

``closed_trades`` is the one definition of "a finished trade" (a position fully sold or settled) used by the tool, the horizon table and the
category table, so the agent and the page can never disagree about its record.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from . import book, books, bot_forecasts, flags, gaps, store, strategies, trader_report
from .contracts import Decision

ORDER_ROWS = 8
LIST_ROWS = 12


def closed_trades(ds: list[Decision]) -> list[dict[str, Any]]:
    """Every fully closed position: result, cost, how long it was held, hours to the market's end when bought, and its category (first market tag)."""
    ms = store.markets()
    closed = trader_report._closed(ds)                       # noqa: SLF001 - the one definition of "closed" for every book
    out = []
    for mid, pnl in closed.items():
        mine = sorted((d for d in ds if d.market_id == mid), key=lambda d: d.at)
        buys = [d for d in mine if d.action in ("buy_yes", "buy_no")]
        if not buys:
            continue
        end = [d for d in mine if d.action in ("sell", "settle")][-1]
        a, b = store.parse_iso(buys[0].at), store.parse_iso(end.at)
        m = ms.get(mid)
        out.append({"market_id": mid, "question": m.question if m else mid, "pnl": pnl, "cost": round(sum(-d.cash_flow for d in buys), 2),
                    "hold_h": round((b - a).total_seconds() / 3600, 1) if a and b else None, "hours_to_end": buys[0].hours_to_end, "opened": buys[0].at,
                    "closed": end.at, "how": end.action, "floor": buys[0].tag == "floor", "category": (m.tags[0] if m and m.tags else "other")})
    return sorted(out, key=lambda t: t["closed"])


def _group(label: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Counts always; win rate and P&L only at ``MIN_RESOLVED_FOR_VERDICT`` closed trades (the page's single verdict threshold)."""
    n, shown = len(rows), len(rows) >= flags.MIN_RESOLVED_FOR_VERDICT
    wins = sum(r["pnl"] > 0 for r in rows)
    return {"label": label, "n": n, "shown": shown, "wins": wins if shown else None, "hit_rate": round(wins / n, 3) if shown else None,
            "pnl": round(sum(r["pnl"] for r in rows), 2) if shown else None}


def by_horizon(trades: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [_group(label, [t for t in trades if t["hours_to_end"] is not None and lo <= t["hours_to_end"] < hi]) for label, lo, hi in flags.DAY_HORIZON_BUCKETS]


def by_category(trades: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cats = sorted({t["category"] for t in trades}, key=lambda c: -sum(t["category"] == c for t in trades))
    return [_group(c, [t for t in trades if t["category"] == c]) for c in cats[:8]]


def stats(ds: list[Decision], series: str = "day") -> dict[str, Any]:
    """The agent's own record for its `performance()` tool: plain numbers, no withholding (it may read its own small sample; the page may not)."""
    ts = closed_trades(ds)
    eq = [e for e in store.equity_points() if e.book == series]
    holds = [t["hold_h"] for t in ts if t["hold_h"] is not None]
    ranked = sorted(ts, key=lambda t: t["pnl"])
    return {"equity": [(e.day, e.equity) for e in eq[-14:]], "closed": len(ts), "wins": sum(t["pnl"] > 0 for t in ts), "realised": book.realised(ds),
            "avg_hold_h": round(sum(holds) / len(holds), 1) if holds else None, "best": ranked[-3:][::-1] if ts else [], "worst": ranked[:3] if ts else [],
            "horizon": [_group_plain(label, [t for t in ts if t["hours_to_end"] is not None and lo <= t["hours_to_end"] < hi]) for label, lo, hi in flags.DAY_HORIZON_BUCKETS],
            "category": [_group_plain(c, [t for t in ts if t["category"] == c]) for c in sorted({t["category"] for t in ts})[:8]]}


def _group_plain(label: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {"label": label, "n": len(rows), "wins": sum(r["pnl"] > 0 for r in rows), "pnl": round(sum(r["pnl"] for r in rows), 2)}


def wishes_top(n: int = 8, strategy: str | None = "day") -> list[dict[str, Any]]:
    """The agent's data wishes merged across runs (near-duplicate topics are one wish, as in ``gaps.clusters``), most-asked first."""
    groups: list[dict[str, Any]] = []
    for w in sorted(store.wishes(strategy), key=lambda w: w.at):
        key = gaps.tokens(w.topic)
        g = next((g for g in groups if gaps._same(g["key"], key)), None)    # noqa: SLF001
        if g is None:
            g = {"key": key, "topic": w.topic, "asks": 0, "runs": set(), "why": w.why, "source": w.source, "last": w.day, "markets": []}
            groups.append(g)
        g["asks"] += 1
        g["runs"].add(w.run_id)
        g["last"], g["why"], g["source"] = w.day, w.why or g["why"], w.source or g["source"]
        if w.market_id and w.market_id not in {m["market_id"] for m in g["markets"]}:
            g["markets"].append({"market_id": w.market_id, "question": w.question})
    top = sorted(groups, key=lambda g: (-len(g["runs"]), -int(g["last"].replace("-", "") or 0)))[:n]
    return [{"topic": g["topic"], "runs": len(g["runs"]), "asks": g["asks"], "why": g["why"], "source": g["source"], "last": g["last"], "markets": g["markets"][:3]} for g in top]


def runs(ds: list[Decision], limit: int | None = None, strategy: str | None = "day") -> list[dict[str, Any]]:
    """The newest runs, compact: what it browsed, which corpus queries, what it ordered and why, and what it cost."""
    ms, by_id = store.markets(), {d.id: d for d in ds}
    out = []
    for r in sorted(store.day_runs(strategy), key=lambda r: r.at, reverse=True)[:limit or flags.DAY_RUNS_SHOWN]:
        orders = []
        for oid in r.orders:
            d = by_id.get(oid)
            if d is None:
                continue
            m = ms.get(d.market_id)
            orders.append({"market_id": d.market_id, "question": m.question if m else d.market_id, "action": d.action, "side": d.side, "stake": round(abs(d.cash_flow), 2),
                           "requested": d.requested, "price": d.price, "reason": d.rationale, "clips": d.clips})
        out.append({"id": r.id, "at": r.at, "usd": round(r.usd, 4), "turns": r.turns, "tool_calls": r.tool_calls, "stopped": r.stopped, "summary": r.summary,
                    "considered": r.considered[:LIST_ROWS], "n_considered": len(r.considered), "queries": r.queries[:LIST_ROWS], "n_queries": len(r.queries),
                    "orders": orders[:ORDER_ROWS], "equity": r.equity, "must_trade": r.must_trade,
                    "forecasts": r.forecasts, "exposure_pct": r.exposure_pct})
    return out


def section(day: str | None = None, strategy_id: str = "day") -> dict[str, Any]:
    """One roster strategy's part of the published document: shaped like the other books' (so the page reuses its tables) plus its roster facts and its own
    parts (runs, wishes, watchlist). ``section()`` with no argument is the day book's, as before."""
    st = strategies.get(strategy_id)
    ds = store.decisions(st.id)
    out = trader_report.section(day, st.id)
    trades = closed_trades(ds)
    today = day or store.now_iso()[:10]
    now = datetime.fromisoformat(today + "T12:00:00+00:00")
    nxt = strategies.next_run(st, datetime.now(now.tzinfo))
    out.update({"id": st.id, "name": st.name, "method": st.method, "method_name": st.method_name, "bot": st.bot, "bot_name": st.bot_name,
                "desk": st.desk, "desk_name": st.desk_name, "desk_about": strategies.DESKS[st.desk].about, "min_fills_day": st.min_fills_day, "style": st.style, "must_trade": st.must_trade, "min_orders": st.min_orders})
    out["limits"] = {"bankroll": st.bankroll, "max_position_frac": st.position_frac, "max_exposure_frac": st.exposure_frac,
                     "slippage": flags.SLIPPAGE, "min_ticket": flags.TRADE_MIN_TICKET, "max_usd_per_day": st.max_usd_day, "max_usd_per_run": st.max_usd_run}
    out["spend_usd"] = round(sum(r.usd for r in store.day_runs(st.id)), 4)
    out["horizon_hours"] = st.horizon_h
    out["run_hours"] = list(st.run_hours)
    out["run_minute"] = st.run_minute
    out["next_run"] = nxt.isoformat(timespec="minutes") if nxt else ""
    out["enabled"] = st.enabled
    out["min_for_verdict"] = flags.MIN_RESOLVED_FOR_VERDICT
    held = book.holdings(ds)
    out["forecasts"] = bot_forecasts.summary(st.id)
    out["exposure"] = {"pct": round(sum(h.cost for h in held.values()) / st.bankroll, 4), "floor_pct": round(st.floor_pct, 4)}
    out["floor"] = {"opened": sum(d.tag == "floor" and d.action in ("buy_yes", "buy_no") for d in ds),
                    "groups": [_group("floor (no edge)", [t for t in trades if t["floor"]]), _group("chosen", [t for t in trades if not t["floor"]])]}
    out["by_horizon"] = by_horizon(trades)
    out["by_category"] = by_category(trades)
    out["avg_hold_h"] = stats(ds, st.series)["avg_hold_h"]
    out["runs"] = runs(ds, strategy=st.id)
    out["spend_today"] = books.agent_spend_today(st.id, now)
    out["wishes"] = wishes_top(strategy=st.id)
    out["watchlist"] = [{"market_id": e.market_id, "question": e.question, "note": e.note, "since": e.at[:10]} for e in store.watchlist(st.id).values()][:LIST_ROWS]
    return out
