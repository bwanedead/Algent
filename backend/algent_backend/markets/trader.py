"""
The trader: an agent that manages a paper portfolio of Polymarket positions, layered ON TOP of the blind forecast. Two books run this same code
(``books.py``): the DAILY book (once a UTC day, every market with a recent forecast) and the FAST book (every few hours, only markets that settle
within days), so the page can compare predictive ability by horizon.

The blind forecast (``forecast.py``) stays the honest calibration signal: the model never sees a price when it states a probability. The trader
is the next step: it is shown the desk's probability AND the market price AND the book, and decides what to do. Its book is scored against the
mechanical rule book (``paper.py``, the same edge rule every day) and against doing nothing (the flat bankroll), so the page can show whether
judgement on top of the forecast adds anything.

Per pass: settle what resolved (free) -> choose the candidate markets (positions held first, then open markets with a recent forecast of ours,
widest gap first) -> for each batch, research the markets in the CORPUS ONLY (``research.py``: one planning call, queries run against the corpus
index) and show the agent the markets, the results and the book -> pass every decision through ``guards.py`` -> append every outcome, holds and
clipped requests included, to the immutable ledger ``decisions.jsonl`` with the corpus items it cited, and a research trace (``trace.py``). A
market the corpus could not serve becomes a gap request (``gaps.py``), not a web search.

Bounded: the book's per-day (and, fast, per-run) dollar cap and a per-call cap, under the budget gate. Idempotent: a market already decided in the
book's window (today / the last few hours) is not asked again, so a rerun after a failure buys nothing twice. PAPER ONLY: this module appends ledger
lines; it cannot reach a venue.
"""

from __future__ import annotations

import time
from datetime import UTC, date, datetime
from typing import Any

from algent_backend.retrieval.docs import clip

from . import book, books, gaps, paper, research, trace
from . import evidence as evidence_mod
from . import flags, forecast, guards, store
from .contracts import Decision, Market, decision_id
from .trader_prompt import FAST_ADDENDUM, PROMPT_VERSION, PROMPT_VERSION_RESEARCH, RESEARCH_ADDENDUM, ROLE, Case, TraderOut, render_task

Ask = forecast.Ask


def role_for(book_name: str = "daily") -> str:
    return ROLE + (RESEARCH_ADDENDUM if flags.RESEARCH_ENABLED else "") + (FAST_ADDENDUM if book_name == "fast" else "")


def default_ask(book_name: str = "daily") -> Ask:
    return forecast.default_ask(role_for(book_name), TraderOut, books.get(book_name).call_cap_usd(), flags.TRADE_EFFORT, max_tokens=4096)


# ── settlement (free) ────────────────────────────────────────────────────────────────────────────
def settle(now: datetime | None = None, book_name: str = "daily") -> int:
    """Close every held position of the book whose market has resolved: pays per share by ``book.payout`` and books the realised result."""
    now = now or datetime.now(UTC)
    at = now.isoformat(timespec="seconds")
    ms, new = store.markets(), []
    for mid, h in book.holdings(store.decisions(book_name)).items():
        m = ms.get(mid)
        if m is None or m.status == "open":
            continue
        pay = book.payout(m.outcome, h.side)
        flow = round(h.shares * pay, 2)
        said = {"yes": "YES", "no": "NO"}.get(m.outcome, "split 50-50")
        new.append(Decision(id=decision_id(mid, "settle", at + ("" if book_name == "daily" else book_name)), market_id=mid, at=at, day=at[:10], action="settle", side=h.side, price=pay,
                            shares=h.shares, cash_flow=flow, realised=round(flow - h.cost, 2), outcome=m.outcome, book=book_name,
                            rationale=f"The market resolved {said}; the {h.side.upper()} position paid ${flow:,.0f} on ${h.cost:,.0f} paid in."))
    store.append_decisions(new)
    return len(new)


# ── the pass's cases ─────────────────────────────────────────────────────────────────────────────
def _path(rows: list, today: date) -> list[tuple[str, float]]:
    """One point per day (the day's last price) for the newest ``TRADE_PATH_DAYS`` days."""
    by_day = {s.at[:10]: s.p for s in sorted(rows, key=lambda s: s.at)}
    return sorted(by_day.items())[-flags.TRADE_PATH_DAYS:]


def _fresh_yes(rows: list, now: datetime) -> float | None:
    s = paper._fresh_price(rows, now)
    return s.p if s is not None else None


def candidates(now: datetime, book_name: str = "daily") -> list[tuple[Market, Any]]:
    """(market, our latest forecast or None), held positions first (largest first), then the widest gaps between our view and the price.
    The fast book only offers NEW positions inside its horizon, and wants a forecast made within ``FAST_FORECAST_MAX_AGE_H`` hours."""
    spec = books.get(book_name)
    ms, prices, fcs = store.markets(), store.snapshots_by_market(), paper.latest_forecasts()
    held = book.holdings(store.decisions(book_name))
    out: list[tuple[Market, Any]] = [(ms[mid], fcs.get(mid)) for mid, h in sorted(held.items(), key=lambda kv: -kv[1].cost) if mid in ms and ms[mid].status == "open"]
    fresh: list[tuple[float, Market, Any]] = []
    for mid, f in fcs.items():
        m, ft = ms.get(mid), store.parse_iso(f.made_at)
        end = store.parse_iso(m.end_date) if m else None
        if m is None or m.status != "open" or mid in held or ft is None or now - ft > spec.forecast_max_age() or not spec.in_scope(m, now):
            continue
        if end is not None and end <= now:
            continue
        p = _fresh_yes(prices.get(mid, []), now)
        if p is not None:
            fresh.append((abs(f.p - p), m, f))
    out += [(m, f) for _, m, f in sorted(fresh, key=lambda t: -t[0])]
    return out[:spec.max_markets()]


def _case(label: str, m: Market, f: Any, held: Any, now: datetime, prices: dict, evidence: str = "", ids: list[str] | None = None) -> Case:
    end = store.parse_iso(m.end_date)
    rows = [s for s in prices.get(m.id, []) if s.source == "live"]
    return Case(label=label, market_id=m.id, question=m.question, event_title=m.event_title, rules=m.description, end_date=m.end_date,
                days_left=max(0, (end - now).days) if end else None, ours=f.p if f else None, ours_made=f.made_at[:10] if f else "",
                ours_why=f.rationale if f else "", yes_price=_fresh_yes(prices.get(m.id, []), now), path=_path(rows, now.date()), held=held,
                evidence=evidence, forecast_id=f.id if f else "", ids=list(ids or []))


# ── the pass ─────────────────────────────────────────────────────────────────────────────────────
def _decide(case: Case, call: Any, usd: float, now: datetime, ds: list[Decision], *, book_name: str = "daily", researched: bool = False) -> Decision:
    """Pass one agent call (or its absence) through the guards against the book as it stands, and return the ledger line."""
    held = book.holdings(ds).get(case.market_id)
    action = getattr(call, "action", "hold") if call is not None else "hold"
    asked = float(getattr(call, "stake_usd", 0.0) or 0.0) if call is not None else 0.0
    fill = guards.apply(action, asked, held=held, yes_price=case.yes_price, cash=book.cash(ds),
                        exposure=sum(h.cost for h in book.holdings(ds).values()), tradable=True)         # candidates() only offers open markets
    clips = list(fill.clips)
    if call is None:
        clips.append("the agent returned no decision for this market: held")
    at = now.isoformat(timespec="seconds")
    why = " ".join(str(getattr(call, "rationale", "") or "").split())[:420] if call is not None else ""
    shown = set(case.ids)
    cited = [c for c in (getattr(call, "cited", None) or []) if c in shown] if call is not None else []
    verdict = (getattr(call, "evidence", "") or "") if (call is not None and researched) else ""
    end = store.parse_iso(case.end_date)
    return Decision(id=decision_id(case.market_id, fill.action, at + ("" if book_name == "daily" else book_name)), market_id=case.market_id, at=at, day=at[:10], action=fill.action,  # type: ignore[arg-type]
                    requested=round(asked, 2), side=fill.side, price=fill.price, shares=fill.shares, cash_flow=fill.cash_flow,  # type: ignore[arg-type]
                    realised=fill.realised, rationale=why, clips=clips, ours=case.ours, market=case.yes_price, forecast_id=case.forecast_id,
                    model="house-" + flags.TRADE_EFFORT, prompt_version=PROMPT_VERSION_RESEARCH if researched else PROMPT_VERSION, usd=usd, book=book_name,
                    evidence_ids=cited, evidence=verdict, hours_to_end=round((end - now).total_seconds() / 3600, 1) if end else None)


def today_spend(ds: list[Decision], day: str) -> tuple[set[str], float]:
    mine = [d for d in ds if d.day == day and d.action != "settle"]
    return {d.market_id for d in mine}, round(sum(d.usd for d in mine), 6)


def run(*, ask: Ask | None = None, now: datetime | None = None, limit: int | None = None, record: dict | None = None,
        index: Any = None, book_name: str = "daily", plan_ask: Any = None, corpus: Any = None) -> dict[str, Any]:
    """The paid pass (see module doc). Returns a report; never raises for a failed or refused call (it stops and says why)."""
    now = now or datetime.now(UTC)
    day = now.date().isoformat()
    spec = books.get(book_name)
    report: dict[str, Any] = {"as_of": now.isoformat(timespec="seconds"), "book": book_name, "settled": 0, "decided": 0, "filled": 0, "clipped": 0,
                              "usd": 0.0, "failed": 0, "stopped": ""}
    report["settled"] = settle(now, book_name)
    if not flags.TRADE_ENABLED or not spec.enabled():
        return {**report, "stopped": f"the {book_name} book is switched off (markets/flags)"}
    ds_all = store.decisions(book_name)
    done = books.recent_ids(ds_all, now, spec)
    usd_today = books.spend_today(ds_all, store.forecasts(), now, spec)
    todo = [(m, f) for m, f in candidates(now, book_name) if m.id not in done]
    if limit is not None:
        todo = todo[:limit]
    report["candidates"] = len(todo)
    if not todo:
        return report
    researching = flags.RESEARCH_ENABLED
    if researching:
        corpus = corpus if corpus is not None else research.open_corpus()
        plan_ask = plan_ask or (research.default_plan_ask() if corpus is not None else None)
    use_corpus = researching and corpus is not None
    mode = "corpus" if use_corpus else ("base-fallback" if researching else "base")
    record = record if record is not None else (evidence_mod.latest_record() if (not use_corpus or not flags.CORPUS_ONLY) else {})
    index = index if index is not None else (forecast.evidence_index(now.date()) if (not use_corpus or not flags.CORPUS_ONLY) else None)
    ask = ask or (default_ask() if book_name == "daily" else default_ask(book_name))
    prices = store.snapshots_by_market()
    spent_run = 0.0
    for i in range(0, len(todo), flags.TRADE_BATCH):
        if usd_today >= spec.max_usd_day() or spent_run >= spec.max_usd_run():
            report["stopped"] = f"day budget reached (${usd_today:.2f})" if usd_today >= spec.max_usd_day() else f"run budget reached (${spent_run:.2f})"
            break
        t0 = time.monotonic()
        ds = store.decisions(book_name)
        held = book.holdings(ds)
        chunk = todo[i:i + flags.TRADE_BATCH]
        cases = [_case(f"M{n}", m, f, held.get(m.id), now, prices) for n, (m, f) in enumerate(chunk, 1)]
        invested = sum(h.cost for h in held.values())
        pt = book.point(spec.equity, now, cash_=book.cash(ds), held=held, realised_=book.realised(ds), prices=prices)
        try:
            found: dict[str, research.Researched] = {}
            if use_corpus:
                found = research.research([research.item_for(c.label, m) for c, (m, _) in zip(cases, chunk, strict=True)], plan_ask=plan_ask, corpus=corpus,
                                          today=now.date(), chars=flags.TRADE_EVIDENCE_CHARS)
            for c, (m, _) in zip(cases, chunk, strict=True):
                r = found.get(c.label)
                if r is not None and flags.CORPUS_ONLY:
                    c.evidence, c.ids = r.text, list(r.ids)
                else:
                    ev = evidence_mod.build(m, today=now.date(), record=record, index=index)
                    c.evidence = clip("\n\n".join(t for t in (r.text if r else "", ev.text) if t), flags.TRADE_EVIDENCE_CHARS + (flags.RESEARCH_CHARS_PER_MARKET if r else 0))
                    c.ids = [*(r.ids if r else []), *ev.ids]
            out, usd = ask(render_task(day, cases, cash=pt.cash, equity=pt.equity, invested=invested, n_open=len(held), fast=book_name == "fast"), role_for(book_name))
        except Exception as exc:  # noqa: BLE001 - a failed or refused call skips this batch; a refusal ends the pass
            report["failed"] += 1
            report.setdefault("errors", []).append(f"{type(exc).__name__}: {str(exc)[:120]}")
            if type(exc).__name__ == "BudgetRefusedError":
                report["stopped"] = "the budget gate refused a call"
                break
            continue
        plan_total = sum(r.usd for r in found.values())
        calls: dict[str, Any] = {}
        for c in getattr(out, "decisions", None) or []:
            calls.setdefault(str(getattr(c, "market", "")).strip().upper(), c)
        share = round(usd / len(cases), 6)
        ms_each = int((time.monotonic() - t0) * 1000) // len(cases)
        for case, (m, _) in zip(cases, chunk, strict=True):                  # sequentially: each fill changes the cash and exposure the next sees
            r = found.get(case.label)
            call = calls.get(case.label)
            d = _decide(case, call, round(share + (r.usd if r else 0.0), 6), now, ds, book_name=book_name, researched=use_corpus)
            ds.append(d)
            store.append_decisions([d])
            topic = " ".join(str(getattr(call, "gap_topic", "") or "").split()) if (call is not None and d.evidence in ("thin", "gap")) else ""
            if flags.RESEARCH_ENABLED:
                trace.write([trace.build("trade", book=book_name, market_id=case.market_id, ref=d.id, at=d.at, res=r, mode=mode, cited=d.evidence_ids, evidence=d.evidence,
                                         gap_topic=topic, decision_usd=share, latency_ms=ms_each, out_chars=len(d.rationale))])
            if topic:
                gaps.record(topic, str(getattr(call, "gap_why", "") or ""), market_id=case.market_id, question=case.question, book=book_name, kind="trade", at=d.at)
            report["decided"] += 1
            report["filled"] += d.action in ("buy_yes", "buy_no", "sell")
            report["clipped"] += bool(d.clips)
        usd_total = usd + plan_total
        usd_today += usd_total
        spent_run += usd_total
        report["usd"] = round(report["usd"] + usd_total, 6)
    return report
