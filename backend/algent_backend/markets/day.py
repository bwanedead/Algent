"""
The day book: an agent that chooses its own bets, 0-2 days out, on paper. Three runs a day (``flags.DAY_RUN_HOURS``).

It is handed no market list. It browses Polymarket live and our mirror (``browse.py``), reads our corpus only (no open-web search), files research
requests the daily gap job fills, and buys and sells freely under the same guards, ledger, settlement and arithmetic as the other books
(``day_tools.py``, ``guards.py``, ``book.py``, ``trader.settle``). Its own $10k, its own caps.

THE LOOP. The model harness (``forecast.default_ask``) is one structured call, and every other bot here is built on it, so this is a bounded loop of
structured TURNS rather than native tool calling: each turn the agent names up to ``DAY_MAX_CALLS_PER_TURN`` tool calls, we run them, and the next
turn reads the transcript with the results. It ends when the agent says done, or at ``DAY_MAX_TURNS`` / ``DAY_MAX_TOOL_CALLS`` / the run or day
dollar cap. Cost is read from the same per-call ledger as everything else, under the budget gate.

THE TRACE. Every run appends one ``DayRun`` (``day_runs.jsonl``): each tool call with its arguments, what the agent was shown and how long it took,
the orders it led to, the markets it considered, the corpus queries, its own closing note, tokens (estimated) and dollars. The orders themselves
are ordinary ledger lines (``decisions.jsonl``, ``book: "day"``) and are never pruned; the run trace is observability and is pruned by age.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from . import book, books, day_prompt, flags, forecast, polymarket, research, store, trader
from .contracts import DayRun, ToolEvent, Wish, day_run_id, wish_id
from .day_prompt import Call, Turn
from .day_tools import Session
from .polymarket import Fetch

Ask = forecast.Ask
COLLAPSED = 160


def default_ask() -> Ask:
    return forecast.default_ask(day_prompt.role(), Turn, flags.DAY_CALL_CAP_USD, flags.DAY_EFFORT, max_tokens=2500)


def _transcript(entries: list[tuple[str, str]], limit: int) -> str:
    """The turns so far. Over ``limit`` characters the OLDEST results are collapsed to one clipped line, so the prompt stays bounded and the
    newest evidence is intact."""
    rows = [list(e) for e in entries]
    total = sum(len(h) + len(r) + 2 for h, r in rows)
    for row in rows:
        if total <= limit:
            break
        short = " ".join(row[1].split())[:COLLAPSED] + (" ..." if len(row[1]) > COLLAPSED else "")
        total -= len(row[1]) - len(short)
        row[1] = short
    return "\n".join(f"{h}\n{r}" if r else h for h, r in rows)


def _task(now: datetime, entries: list[tuple[str, str]], turn: int, session: Session) -> str:
    calls_left = flags.DAY_MAX_TOOL_CALLS - len(session.events)
    last = turn == flags.DAY_MAX_TURNS - 1
    head = (f"NOW: {now.strftime('%Y-%m-%d %H:%MZ')}. TURN {turn + 1} of {flags.DAY_MAX_TURNS}; tool calls left {calls_left}; orders left "
            f"{flags.DAY_MAX_ORDERS_PER_RUN - session.attempts}.")
    if last or calls_left <= flags.DAY_MAX_CALLS_PER_TURN:
        head += " THIS IS NEAR THE END OF YOUR BUDGET: place any orders you have decided on now and set done=true with your summary."
    return head + "\n\n" + _transcript(entries, flags.DAY_TRANSCRIPT_CHARS)


def run(*, ask: Ask | None = None, now: datetime | None = None, get: Fetch | None = None, corpus: Any = None) -> dict[str, Any]:
    """One run of the day book. Never raises for a failed or refused model call: it stops, records the run and says why."""
    now = now or datetime.now(UTC)
    report: dict[str, Any] = {"as_of": now.isoformat(timespec="seconds"), "book": "day", "settled": trader.settle(now, "day"), "turns": 0, "tool_calls": 0, "orders": 0,
                              "filled": 0, "usd": 0.0, "stopped": ""}
    if not flags.DAY_ENABLED or not flags.TRADE_ENABLED:
        return {**report, "stopped": "the day book is switched off (markets/flags)"}
    spec = books.DAY
    spent_day = books.spend_today([], [], now, spec)
    if spent_day >= spec.max_usd_day():
        return {**report, "stopped": f"day budget reached (${spent_day:.2f})"}
    corpus = corpus if corpus is not None else research.open_corpus()
    ask = ask or default_ask()
    session = Session(now=now, get=get or polymarket.fetch, corpus=corpus)
    entries: list[tuple[str, str]] = []
    pf = ToolEvent(n=0, turn=0, tool="portfolio", result="")
    text, _ = session.t_portfolio()
    pf.result = text
    entries.append(("PORTFOLIO (given at the start of the run):", text))
    entries.append(("WATCHLIST (kept between runs):", session.watch_text()))
    wished: list[Any] = []
    spent, worst, tokens, turns, stopped, summary = 0.0, 0.0, 0, 0, "", ""
    for turn in range(flags.DAY_MAX_TURNS):
        if spent + worst > spec.max_usd_run() and turns:
            stopped = "run budget reached"
            break
        if spent_day + spent + worst > spec.max_usd_day() and turns:
            stopped = "day budget reached"
            break
        task = _task(now, entries, turn, session)
        try:
            out, usd = ask(task, day_prompt.role())
        except Exception as exc:  # noqa: BLE001 - the orders already filled stand; the run is recorded with why it stopped
            stopped = "the budget gate refused a call" if type(exc).__name__ == "BudgetRefusedError" else f"model call failed: {type(exc).__name__}: {str(exc)[:100]}"
            break
        turns += 1
        usd = float(usd or 0.0)
        spent += usd
        worst = max(worst, usd)
        calls = list(getattr(out, "calls", None) or [])[:flags.DAY_MAX_CALLS_PER_TURN]
        tokens += (len(task) + sum(len(c.model_dump_json()) for c in calls) + len(getattr(out, "summary", "") or "")) // 4
        entries.append((f"TURN {turn + 1} plan: {' '.join((getattr(out, 'notes', '') or '').split())[:240] or '(none)'}", ""))
        for c in calls:
            if len(session.events) >= flags.DAY_MAX_TOOL_CALLS:
                stopped = "tool-call limit"
                break
            ev = session.run(turn + 1, c)
            entries.append((f"-> {c.tool}({', '.join(f'{k}={v!r}' for k, v in ev.args.items())})", ev.result))
        wished += list(getattr(out, "wishes", None) or [])
        summary = " ".join((getattr(out, "summary", "") or "").split())[:600] or summary
        if stopped:
            break
        if getattr(out, "done", False) or not calls:
            stopped = "done"
            break
    else:
        stopped = "turn limit"
    settled = trader.settle(now, "day")                      # a position that resolved while the run was going
    ds = session.ds
    held = book.holdings(ds)
    pt = book.point("day", now, cash_=book.cash(ds), held=held, realised_=book.realised(ds), prices=store.snapshots_by_market())
    run_line = DayRun(id=day_run_id(now.isoformat(timespec="seconds")), at=now.isoformat(timespec="seconds"), day=now.date().isoformat(), turns=turns,
                      tool_calls=len(session.events), events=[pf, *session.events], considered=list(session.considered.values()), queries=session.queries,
                      orders=session.orders, summary=summary, usd=round(spent, 6), tokens=tokens, stopped=stopped, settled=settled + report["settled"],
                      equity=pt.equity, cash=pt.cash)
    store.append_day_run(run_line)
    seen_topics: set[str] = set()
    wishes = []
    for w in wished:                                         # one line per distinct topic in the run; the aggregation across runs is day_report.wishes_top
        topic = " ".join((getattr(w, "topic", "") or "").split())[:160]
        if topic and topic.lower() not in seen_topics:
            seen_topics.add(topic.lower())
            mid = str(getattr(w, "market", "") or "").strip()
            wishes.append(Wish(id=wish_id(run_line.id, topic), at=run_line.at, day=run_line.day, run_id=run_line.id, topic=topic, market_id=mid,
                               why=" ".join((getattr(w, "why", "") or "").split())[:300], source=" ".join((getattr(w, "source", "") or "").split())[:200],
                               question=session.considered.get(mid, {}).get("question", "")))
    store.append_wishes(wishes)
    filled = sum(d.action in ("buy_yes", "buy_no", "sell") for d in ds if d.id in set(session.orders))
    return {**report, "turns": turns, "tool_calls": len(session.events), "orders": len(session.orders), "filled": filled, "usd": round(spent, 6), "stopped": stopped,
            "summary": summary, "equity": pt.equity, "cash": pt.cash, "considered": len(session.considered), "wishes": len(wishes)}
