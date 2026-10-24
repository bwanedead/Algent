"""
``newsroom markets`` — the Polymarket paper-trading benchmark. PAPER ONLY: no wallet, no key, no order is ever placed.

    newsroom markets refresh [--no-publish]     mirror (discover, snapshot, resolutions), then the paper pass (open, mark, settle) and publish (free)
    newsroom markets paper                      the paper pass alone: settle resolved positions, open per the edge rule, mark to market
    newsroom markets score [--full]             the scoreboard: us vs the market, calibration, paper P&L (--full: the whole document)
    newsroom markets list [--theater ID] [--status S] [--limit N]   the mirrored markets with their latest price
    newsroom markets forecast [--limit N] [--dry-run]   PAID: our blind probability for mirrored markets (day-capped)
    newsroom markets trade [--limit N] [--dry-run]      PAID: the trader's decisions on its book (day-capped)
    newsroom markets daily [--no-forecast] [--no-trade] PAID, the scheduled job: refresh prices -> blind forecasts -> rule book -> trade -> mark -> publish
    newsroom markets fast [--no-forecast] [--limit N] [--dry-run]   the FAST book (markets settling within days), every 4 h; capped, gated like a paid job
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
    tr = verbs.add_parser("trade", help="the trader's decisions for today (paid, capped per day)")
    tr.add_argument("--limit", type=int)
    tr.add_argument("--dry-run", action="store_true", help="list the markets that would be offered to the trader; call nothing")
    tr.set_defaults(handler=run_trade)
    dl = verbs.add_parser("daily", help="the once-a-day paid job: refresh, forecast, trade, mark, publish")
    dl.add_argument("--no-forecast", action="store_true")
    dl.add_argument("--no-trade", action="store_true")
    dl.set_defaults(handler=run_daily)
    dy = verbs.add_parser("day", help="the day book: an agent that browses and picks its own 0-2 day bets (capped, gated like a paid job)")
    dy.add_argument("--dry-run", action="store_true", help="print the schedule and caps; call nothing")
    dy.set_defaults(handler=run_day)
    fa = verbs.add_parser("fast", help="the fast book: forecast + trade the markets that settle within days (capped)")
    fa.add_argument("--no-forecast", action="store_true")
    fa.add_argument("--limit", type=int)
    fa.add_argument("--dry-run", action="store_true", help="list the markets the fast book would look at; call nothing")
    fa.set_defaults(handler=run_fast)
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
    report["paper"] = paper.run()
    report["trader_settled"] = trader.settle()               # free: a held market that resolved pays out
    report["day_settled"] = trader.settle(book_name="day")   # the day book is settled, and marked (the mirror pass above priced it), on every refresh
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


def run_trade(args: Any) -> int:
    from datetime import UTC, datetime

    from algent_backend.markets import publish, trader

    if args.dry_run:
        todo = trader.candidates(datetime.now(UTC))
        return _emit({"candidates": len(todo), "first": [{"id": m.id, "question": m.question, "ours": f.p if f else None} for m, f in todo[:20]]})
    report = trader.run(limit=args.limit)
    report["publish"] = publish.publish()
    return _emit(report)


def _step(fn: Any) -> tuple[dict[str, Any], bool]:
    try:
        return fn(), False
    except Exception as exc:  # noqa: BLE001 - the free steps after it (mark, publish) must still run
        return {"error": f"{type(exc).__name__}: {str(exc)[:200]}"}, True


def run_daily(args: Any) -> int:
    """refresh prices -> blind forecasts -> rule book -> trader -> mark both books -> publish. A paid step that raises does not stop the free
    steps after it (the books are still marked and published); the exit code is then 1 so the scheduler sees the failure."""
    from datetime import UTC, datetime

    from algent_backend.markets import book, forecast, mirror, paper, publish, trader

    now = datetime.now(UTC)
    report: dict[str, Any] = {"day": now.date().isoformat(), "mirror": mirror.refresh()}
    failed = False
    index = forecast.evidence_index(now.date())                  # built once, shared by the forecaster and the trader
    if not args.no_forecast:
        report["forecast"], bad = _step(lambda: forecast.run(index=index))
        failed = failed or bad
    report["paper"] = paper.run()
    if not args.no_trade:
        report["trade"], bad = _step(lambda: trader.run(index=index))
        failed = failed or bad
    report["marked"] = [p.model_dump() for p in book.mark()]
    report["publish"] = publish.publish()
    _emit(report)
    return 1 if failed else 0


def run_fast(args: Any) -> int:
    """The fast book: blind forecasts for the markets inside the horizon that lack a fresh one, then the fast trader, mark, publish. Gated like a paid
    job (the registry job is ``capped`` because the scheduler's paid class is daily-only): the same refusals apply, then its own caps."""
    from datetime import UTC, datetime

    from algent_backend.markets import book, flags, forecast, publish, trader

    now = datetime.now(UTC)
    if args.dry_run:
        todo = trader.candidates(now, "fast")
        return _emit({"horizon_days": flags.FAST_HORIZON_DAYS, "needs_forecast": len(forecast.candidates(now, "fast")),
                      "candidates": len(todo), "first": [{"id": m.id, "question": m.question, "ends": m.end_date[:16], "ours": f.p if f else None} for m, f in todo[:20]]})
    from algent_backend.ops import schedule

    if why := schedule._may_spend(schedule.Probes()):                       # noqa: SLF001 - the one gate every unattended spend passes
        return _emit({"book": "fast", "skipped": why})
    report: dict[str, Any] = {"book": "fast", "as_of": now.isoformat(timespec="seconds")}
    failed = False
    if not args.no_forecast:
        report["forecast"], bad = _step(lambda: forecast.run(book="fast", limit=args.limit))
        failed = failed or bad
    report["trade"], bad = _step(lambda: trader.run(book_name="fast", limit=args.limit))
    failed = failed or bad
    report["marked"] = [p.model_dump() for p in book.mark()]
    report["publish"] = publish.publish()
    _emit(report)
    return 1 if failed else 0


def run_day(args: Any) -> int:
    """One run of the day book: settle, the agent's tool loop, mark, publish. Gated like a paid job (registry class ``capped``: three runs a day do not fit
    the paid class, which is daily-only): the kill switch, runner claim and spend halt apply, then the book's own run and day caps."""
    from datetime import UTC, datetime

    from algent_backend.markets import book, day, flags, publish, store

    now = datetime.now(UTC)
    if args.dry_run:
        return _emit({"enabled": flags.DAY_ENABLED, "run_hours": list(flags.DAY_RUN_HOURS), "horizon_h": flags.DAY_HORIZON_H,
                      "caps": {"run": flags.DAY_MAX_USD_PER_RUN, "day": flags.DAY_MAX_USD_PER_DAY}, "watchlist": len(store.watchlist()), "runs": len(store.day_runs())})
    from algent_backend.ops import schedule

    if why := schedule._may_spend(schedule.Probes()):                       # noqa: SLF001 - the one gate every unattended spend passes
        return _emit({"book": "day", "skipped": why})
    report, bad = _step(lambda: day.run(now=now))
    report["marked"] = [p.model_dump() for p in book.mark()]
    report["publish"] = publish.publish()
    _emit(report)
    return 1 if bad else 0


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
