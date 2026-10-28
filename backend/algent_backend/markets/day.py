"""
THE GENERIC STRATEGY RUNNER (named for its first user, the day book). One run of any roster strategy (``strategies.py``): an agent that chooses its own bets on paper,
parametrised by the strategy's reasoning method, window, caps and must-trade rule. The day book is the first entry (0-2 days out, three runs a day).

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

from . import book, books, day_prompt, flags, forecast, polymarket, research, store, strategies, trader
from .contracts import DayRun, ToolEvent, Wish, day_run_id, wish_id
from .day_prompt import Call, Turn
from .day_tools import Session
from .polymarket import Fetch

Ask = forecast.Ask
COLLAPSED = 160


def default_ask(st: strategies.Strategy | None = None) -> Ask:
    st = st or strategies.get("day")
    return forecast.default_ask(day_prompt.role(st), Turn, st.call_cap_usd, st.effort, max_tokens=2500 if st.method == "p0b" else 4000)   # a worked method writes more per order


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


def _fills(session: Session) -> int:
    """Orders of this run that went through (a buy or a sell that filled); a refused or held order does not count."""
    mine = set(session.orders)
    return sum(d.action in ("buy_yes", "buy_no", "sell") for d in session.ds if d.id in mine)


def _owes(st: strategies.Strategy, session: Session) -> int:
    return max(0, st.min_orders - _fills(session)) if st.must_trade else 0


def _task(now: datetime, entries: list[tuple[str, str]], turn: int, session: Session) -> str:
    st = session.s
    calls_left = st.max_tool_calls - len(session.events)
    last = turn == st.max_turns - 1
    head = (f"NOW: {now.strftime('%Y-%m-%d %H:%MZ')}. TURN {turn + 1} of {st.max_turns}; tool calls left {calls_left}; orders left "
            f"{st.max_orders - session.attempts}.")
    if last or calls_left <= st.calls_per_turn:
        head += " THIS IS NEAR THE END OF YOUR BUDGET: place any orders you have decided on now and set done=true with your summary."
    if owes := _owes(st, session):
        head += (f" YOU MUST STILL FILL {owes} MORE ORDER{'S' if owes > 1 else ''} THIS RUN" +
                 (": do it this turn, at the smallest size if nothing has edge." if last or turn >= st.max_turns - 2 else "."))
    return head + "\n\n" + _transcript(entries, flags.DAY_TRANSCRIPT_CHARS)


def run(*, strategy_id: str = "day", ask: Ask | None = None, now: datetime | None = None, get: Fetch | None = None, corpus: Any = None) -> dict[str, Any]:
    """One run of a roster strategy (the day book by default). Never raises for a failed or refused model call: it stops, records the run and says why.
    A must-trade strategy that says it is done before it has filled its minimum is sent back to trade (at most ``MUST_TRADE_PUSHES`` times); a run that still
    falls short is recorded ``unmet`` on its trace, never faked."""
    now = now or datetime.now(UTC)
    st = strategies.get(strategy_id)
    report: dict[str, Any] = {"as_of": now.isoformat(timespec="seconds"), "book": st.id, "strategy": st.id, "settled": trader.settle(now, st.id), "turns": 0, "tool_calls": 0,
                              "orders": 0, "filled": 0, "usd": 0.0, "stopped": ""}
    if not st.enabled:
        return {**report, "stopped": f"the {st.name} is switched off (markets/flags)"}
    spent_day = books.agent_spend_today(st.id, now)
    if spent_day >= st.max_usd_day:
        return {**report, "stopped": f"day budget reached (${spent_day:.2f})"}
    corpus = corpus if corpus is not None else research.open_corpus()
    ask = ask or default_ask(st)
    session = Session(now=now, get=get or polymarket.fetch, corpus=corpus, strategy=st)
    entries: list[tuple[str, str]] = []
    pf = ToolEvent(n=0, turn=0, tool="portfolio", result="")
    text, _ = session.t_portfolio()
    pf.result = text
    entries.append(("PORTFOLIO (given at the start of the run):", text))
    entries.append(("WATCHLIST (kept between runs):", session.watch_text()))
    wished: list[Any] = []
    spent, worst, tokens, turns, stopped, summary, pushes = 0.0, 0.0, 0, 0, "", "", 0
    for turn in range(st.max_turns):
        if spent + worst > st.max_usd_run and turns:
            stopped = "run budget reached"
            break
        if spent_day + spent + worst > st.max_usd_day and turns:
            stopped = "day budget reached"
            break
        task = _task(now, entries, turn, session)
        try:
            out, usd = ask(task, day_prompt.role(st))
        except Exception as exc:  # noqa: BLE001 - the orders already filled stand; the run is recorded with why it stopped
            stopped = "the budget gate refused a call" if type(exc).__name__ == "BudgetRefusedError" else f"model call failed: {type(exc).__name__}: {str(exc)[:100]}"
            break
        turns += 1
        usd = float(usd or 0.0)
        spent += usd
        worst = max(worst, usd)
        calls = list(getattr(out, "calls", None) or [])[:st.calls_per_turn]
        tokens += (len(task) + sum(len(c.model_dump_json()) for c in calls) + len(getattr(out, "summary", "") or "")) // 4
        entries.append((f"TURN {turn + 1} plan: {' '.join((getattr(out, 'notes', '') or '').split())[:240] or '(none)'}", ""))
        for c in calls:
            if len(session.events) >= st.max_tool_calls:
                stopped = "tool-call limit"
                break
            ev = session.run(turn + 1, c)
            entries.append((f"-> {c.tool}({', '.join(f'{k}={v!r}' for k, v in ev.args.items())})", ev.result))
        wished += list(getattr(out, "wishes", None) or [])
        summary = " ".join((getattr(out, "summary", "") or "").split())[:600] or summary
        if stopped:
            break
        if getattr(out, "done", False) or not calls:
            if _owes(st, session) and pushes < flags.MUST_TRADE_PUSHES and turn + 1 < st.max_turns:
                pushes += 1                                  # not done yet: the book has to trade (the next task says how many orders it still owes)
                entries.append(("MUST TRADE: you ended the run before filling your minimum number of orders; keep going.", ""))
                continue
            stopped = "done"
            break
    else:
        stopped = "turn limit"
    settled = trader.settle(now, st.id)                      # a position that resolved while the run was going
    ds = session.ds
    held = book.holdings(ds)
    pt = book.point(st.series, now, cash_=book.cash(ds), held=held, realised_=book.realised(ds), prices=store.snapshots_by_market())
    run_line = DayRun(id=day_run_id(now.isoformat(timespec="seconds")), at=now.isoformat(timespec="seconds"), day=now.date().isoformat(), turns=turns,
                      tool_calls=len(session.events), events=[pf, *session.events], considered=list(session.considered.values()), queries=session.queries,
                      orders=session.orders, summary=summary, usd=round(spent, 6), tokens=tokens, stopped=stopped, settled=settled + report["settled"],
                      equity=pt.equity, cash=pt.cash, strategy=st.id,
                      must_trade=("" if not st.must_trade else "met" if _owes(st, session) == 0 else f"unmet: {_fills(session)} of {st.min_orders}"))
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
                               question=session.considered.get(mid, {}).get("question", ""), strategy=st.id))
    store.append_wishes(wishes)
    filled = sum(d.action in ("buy_yes", "buy_no", "sell") for d in ds if d.id in set(session.orders))
    return {**report, "turns": turns, "tool_calls": len(session.events), "orders": len(session.orders), "filled": filled, "usd": round(spent, 6), "stopped": stopped,
            "summary": summary, "must_trade": run_line.must_trade, "equity": pt.equity, "cash": pt.cash, "considered": len(session.considered), "wishes": len(wishes)}
