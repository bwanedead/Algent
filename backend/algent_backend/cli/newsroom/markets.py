"""
``newsroom markets`` — the Polymarket paper-trading benchmark. PAPER ONLY: no wallet, no key, no order is ever placed.

    newsroom markets refresh [--no-publish]     mirror (discover, snapshot, resolutions), then the paper pass (the retired rule book: settle and mark only) and publish (free)
    newsroom markets paper                      the paper pass alone: settle resolved positions, open per the edge rule, mark to market
    newsroom markets score [--full]             the scoreboard: us vs the market, calibration, paper P&L (--full: the whole document)
    newsroom markets list [--theater ID] [--status S] [--limit N]   the mirrored markets with their latest price
    newsroom markets forecast [--limit N] [--dry-run]   the DESK's blind forecast (the lab's P0 control + scoring; feeds no bot, not scheduled)
    newsroom markets strategy <id> | --list    one run of a roster strategy (each its own forecaster and trader; daily / fast / day are shortcuts)
    newsroom markets daily [--no-trade]         the scheduled job: refresh prices -> the daily trader strategy -> mark -> publish
    newsroom markets fast [--dry-run]           the FAST strategy (markets settling within days), every 4 h; capped, gated like a paid job
    newsroom markets day [--dry-run]            the DAY book: an agent that browses and chooses its own 0-2 day bets, 3 runs a day; capped, gated like a paid job
    newsroom markets gaps [--list] [--dry-run] [--limit N]          PAID, daily: research the bots' most-asked gaps into the corpus (capped at $0.50/day)
    newsroom markets evidence                   how the corpus served the bots: coverage, citations, tools, top gaps, accuracy by richness
    newsroom markets status                     last pass, counts, forecasts and trader decisions, spend

Every command prints one JSON document. See ``markets/`` and docs/architecture/markets-track-record.md.
"""

from __future__ import annotations

import json
from typing import Any


def add_parser(sub: Any) -> None:
    p = sub.add_parser("markets", help="Polymarket mirror, blind forecasts, paper portfolio and track record (paper only)")
    verbs = p.add_subparsers(dest="markets_cmd", required=True)
    r = verbs.add_parser("refresh", help="mirror pass + paper pass + publish (free)")
    r.add_argument("--no-publish", action="store_true")
    r.set_defaults(handler=run_refresh)
    verbs.add_parser("publish", help="push the track record to the site database").set_defaults(handler=run_publish)
    verbs.add_parser("paper", help="the paper portfolio pass").set_defaults(handler=run_paper)
    sc = verbs.add_parser("score", help="the scoreboard")
    sc.add_argument("--full", action="store_true")
    sc.set_defaults(handler=run_score)
    ls = verbs.add_parser("list", help="mirrored markets")
    ls.add_argument("--theater")
    ls.add_argument("--status", choices=["open", "resolved", "void"])
    ls.add_argument("--limit", type=int, default=40)
    ls.set_defaults(handler=run_list)
    fc = verbs.add_parser("forecast", help="blind forecasts for markets that need one (paid, capped per day)")
    fc.add_argument("--limit", type=int)
    fc.add_argument("--dry-run", action="store_true", help="list the markets that would be forecast; call nothing")
    fc.set_defaults(handler=run_forecast)
    dl = verbs.add_parser("daily", help="the once-a-day job: refresh prices, run the daily trader strategy, mark, publish")
    dl.add_argument("--no-trade", action="store_true")
    dl.set_defaults(handler=run_daily)
    dy = verbs.add_parser("day", help="the day strategy: an agent that browses and picks its own 0-2 day bets (capped, gated like a paid job)")
    dy.add_argument("--dry-run", action="store_true", help="print the schedule and caps; call nothing")
    dy.set_defaults(handler=run_day)
    fa = verbs.add_parser("fast", help="the fast strategy: trades the markets that settle within days, every few hours (capped)")
    fa.add_argument("--dry-run", action="store_true", help="print the schedule and caps; call nothing")
    fa.set_defaults(handler=run_fast)
    sg = verbs.add_parser("strategy", help="one run of a roster strategy (markets/strategies.py), or the roster with --list")
    sg.add_argument("id", nargs="?", default="", help="a strategy id from the roster")
    sg.add_argument("--list", action="store_true", help="print the roster, schedule and caps; call nothing")
    sg.add_argument("--dry-run", action="store_true")
    sg.set_defaults(handler=run_strategy)
    gp = verbs.add_parser("gaps", help="turn the most-asked gaps into research runs (paid, capped per day)")
    gp.add_argument("--list", action="store_true", help="show the top gaps and do nothing")
    gp.add_argument("--dry-run", action="store_true")
    gp.add_argument("--limit", type=int)
    gp.set_defaults(handler=run_gaps)
    verbs.add_parser("evidence", help="the evidence section: coverage, citations, tools, gaps, accuracy by richness").set_defaults(handler=run_evidence)
    verbs.add_parser("status", help="what the store holds and when it last ran").set_defaults(handler=run_status)


def _emit(doc: Any) -> int:
    print(json.dumps(doc, indent=2, ensure_ascii=False))
    return 0


def run_refresh(args: Any) -> int:
    from algent_backend.markets import book, mirror, paper, publish, store, trader

    report = mirror.refresh()
    report["traces_pruned"] = store.prune_traces()
    report["paper"] = paper.run()                            # the retired rule book: settles and marks what it still holds, opens nothing
    from algent_backend.markets import strategies

    report["settled"] = {st.id: trader.settle(book_name=st.id) for st in strategies.roster()}   # free: every strategy's resolved positions pay out, then the mark below
    report["marked"] = len(book.mark())
    if not args.no_publish:
        report["publish"] = publish.publish()
    return _emit(report)


def run_publish(_args: Any) -> int:
    from algent_backend.markets import publish

    return _emit(publish.publish())


def run_paper(_args: Any) -> int:
    from algent_backend.markets import paper

    return _emit({"pass": paper.run(), "portfolio": paper.summary()})


def run_score(args: Any) -> int:
    from algent_backend.markets import score

    doc = score.track_record()
    return _emit(doc if args.full else {k: doc[k] for k in ("markets", "forecasts", "scores", "portfolio", "market_beat_us")})


def _latest_prices() -> dict[str, float]:
    from algent_backend.markets import store

    return {mid: rows[-1].p for mid, rows in store.snapshots_by_market().items() if rows}


def run_list(args: Any) -> int:
    from algent_backend.markets import store

    price = _latest_prices()
    rows = [m for m in store.markets().values() if (not args.status or m.status == args.status) and (not args.theater or args.theater in m.theaters)]
    rows.sort(key=lambda m: -m.volume)
    return _emit({"count": len(rows), "markets": [{"id": m.id, "question": m.question, "p_yes": price.get(m.id), "status": m.status, "outcome": m.outcome,
                                                   "ends": m.end_date[:10], "volume": round(m.volume), "theaters": m.theaters, "countries": m.countries}
                                                  for m in rows[:args.limit]]})


def run_forecast(args: Any) -> int:
    from datetime import UTC, datetime

    from algent_backend.markets import forecast

    if args.dry_run:
        todo = forecast.candidates(datetime.now(UTC))
        return _emit({"candidates": len(todo), "first": [{"id": m.id, "question": m.question, "theaters": m.theaters} for m in todo[:20]]})
    from algent_backend.markets import paper, publish

    report = forecast.run(limit=args.limit)
    report["paper"] = paper.run()
    report["publish"] = publish.publish()
    return _emit(report)


def _step(fn: Any) -> tuple[dict[str, Any], bool]:
    try:
        return fn(), False
    except Exception as exc:  # noqa: BLE001 - the free steps after it (mark, publish) must still run
        return {"error": f"{type(exc).__name__}: {str(exc)[:200]}"}, True


def _run_strategy(sid: str, *, gated: bool) -> int:
    """One run of a roster strategy: settle, the agent loop, mark, publish. ``gated`` applies the scheduler's refusals (kill switch, runner claim, spend halt)
    first, for the ``capped`` registry jobs (the scheduler's paid class is daily-only); the daily job already passes the gate through ``schedule run``."""
    from datetime import UTC, datetime

    from algent_backend.markets import book, day, publish

    if gated:
        from algent_backend.ops import schedule

        if why := schedule._may_spend(schedule.Probes()):                   # noqa: SLF001 - the one gate every unattended spend passes
            return _emit({"book": sid, "skipped": why})
    report, bad = _step(lambda: day.run(strategy_id=sid, now=datetime.now(UTC)))
    report["marked"] = [p.model_dump() for p in book.mark()]
    report["publish"] = publish.publish()
    _emit(report)
    return 1 if bad else 0


def _plan(sid: str) -> dict[str, Any]:
    from algent_backend.markets import store, strategies

    st = strategies.get(sid)
    return {"id": st.id, "name": st.name, "method": st.method, "enabled": st.enabled, "run_hours": list(st.run_hours), "run_minute": st.run_minute, "horizon_h": st.horizon_h,
            "must_trade": st.must_trade, "min_orders": st.min_orders, "caps": {"run": st.max_usd_run, "day": st.max_usd_day}, "watchlist": len(store.watchlist(st.id)),
            "runs": len(store.day_runs(st.id))}


def run_daily(args: Any) -> int:
    """refresh prices -> the daily trader strategy (its own research and probabilities; no desk forecast) -> mark -> publish. A failed paid step still marks and
    publishes; the exit code is then 1 so the scheduler sees the failure."""
    from datetime import UTC, datetime

    from algent_backend.markets import book, mirror, publish

    if args.no_trade:
        report: dict[str, Any] = {"day": datetime.now(UTC).date().isoformat(), "mirror": mirror.refresh(), "marked": [p.model_dump() for p in book.mark()], "publish": publish.publish()}
        return _emit(report)
    mirror.refresh()
    return _run_strategy("daily", gated=False)


def run_fast(args: Any) -> int:
    return _emit(_plan("fast")) if args.dry_run else _run_strategy("fast", gated=True)


def run_day(args: Any) -> int:
    return _emit(_plan("day")) if args.dry_run else _run_strategy("day", gated=True)


def run_strategy(args: Any) -> int:
    from algent_backend.markets import strategies

    if args.list or not args.id:
        return _emit([_plan(i) for i in strategies.ids()])
    return _emit(_plan(args.id)) if args.dry_run else _run_strategy(args.id, gated=True)


def run_gaps(args: Any) -> int:
    from datetime import UTC, datetime

    from algent_backend.markets import gaps

    now = datetime.now(UTC)
    if args.list or args.dry_run:
        return _emit({"spent_today": gaps.spent_today(now), "top": gaps.top(15, now)})
    return _emit(gaps.fill(limit=args.limit))


def run_evidence(_args: Any) -> int:
    from algent_backend.markets import research_report, score

    return _emit(research_report.section(score.pairs()))


def run_status(_args: Any) -> int:
    from algent_backend.markets import store

    ms = list(store.markets().values())
    return _emit({"store": str(store.root()), "markets": {s: sum(m.status == s for m in ms) for s in ("open", "resolved", "void")},
                  "snapshots": len(store.snapshots()), "forecasts": len(store.forecasts()), "trades": len(store.trades()),
                  "trader_decisions": len(store.decisions()), "fast_decisions": len(store.decisions("fast")), "day_decisions": len(store.decisions("day")), "day_runs": len(store.day_runs()), "traces": len(store.traces()),
                  "gap_asks": len(store.gaps()), "gap_fills": len(store.gap_fills()), "equity_points": len(store.equity_points()), **store.load_status()})
