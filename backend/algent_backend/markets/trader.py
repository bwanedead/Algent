"""
The trader: a once-a-day agent that manages a paper portfolio of Polymarket positions, layered ON TOP of the blind forecast.

The blind forecast (``forecast.py``) stays the honest calibration signal: the model never sees a price when it states a probability. The trader
is the next step: it is shown the desk's probability AND the market price AND the book, and decides what to do. Its book is scored against the
mechanical rule book (``paper.py``, the same edge rule every day) and against doing nothing (the flat bankroll), so the page can show whether
judgement on top of the forecast adds anything.

Per day: settle what resolved (free) -> choose the candidate markets (positions held first, then open markets with a recent forecast of ours,
widest gap first) -> for each batch, show the agent the markets, their evidence (``evidence.py`` + ``retrieval``) and the book -> pass every
decision through ``guards.py`` -> append every outcome, holds and clipped requests included, to the immutable ledger ``decisions.jsonl``.

Bounded: ``TRADE_MAX_USD_PER_DAY`` and a per-call cap, under the budget gate. Idempotent per day: a market already decided today is not asked
again, so a rerun after a failure buys nothing twice. PAPER ONLY: this module appends ledger lines; it cannot reach a venue.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from algent_backend.retrieval.docs import clip

from . import book
from . import evidence as evidence_mod
from . import flags, forecast, guards, paper, store
from .contracts import Decision, Market, decision_id
from .trader_prompt import PROMPT_VERSION, ROLE, Case, TraderOut, render_task

Ask = forecast.Ask


def default_ask() -> Ask:
    return forecast.default_ask(ROLE, TraderOut, flags.TRADE_CALL_CAP_USD, flags.TRADE_EFFORT, max_tokens=4096)


# ── settlement (free) ────────────────────────────────────────────────────────────────────────────
def settle(now: datetime | None = None) -> int:
    """Close every held position whose market has resolved: pays per share by ``book.payout`` and books the realised result."""
    now = now or datetime.now(UTC)
    at = now.isoformat(timespec="seconds")
    ms, new = store.markets(), []
    for mid, h in book.holdings(store.decisions()).items():
        m = ms.get(mid)
        if m is None or m.status == "open":
            continue
        pay = book.payout(m.outcome, h.side)
        flow = round(h.shares * pay, 2)
        said = {"yes": "YES", "no": "NO"}.get(m.outcome, "split 50-50")
        new.append(Decision(id=decision_id(mid, "settle", at), market_id=mid, at=at, day=at[:10], action="settle", side=h.side, price=pay,
                            shares=h.shares, cash_flow=flow, realised=round(flow - h.cost, 2), outcome=m.outcome,
                            rationale=f"The market resolved {said}; the {h.side.upper()} position paid ${flow:,.0f} on ${h.cost:,.0f} paid in."))
    store.append_decisions(new)
    return len(new)


# ── the day's cases ──────────────────────────────────────────────────────────────────────────────
def _path(rows: list, today: date) -> list[tuple[str, float]]:
    """One point per day (the day's last price) for the newest ``TRADE_PATH_DAYS`` days."""
    by_day = {s.at[:10]: s.p for s in sorted(rows, key=lambda s: s.at)}
    return sorted(by_day.items())[-flags.TRADE_PATH_DAYS:]


def _fresh_yes(rows: list, now: datetime) -> float | None:
    s = paper._fresh_price(rows, now)
    return s.p if s is not None else None


def candidates(now: datetime) -> list[tuple[Market, Any]]:
    """(market, our latest forecast or None), held positions first (largest first), then the widest gaps between our view and the price."""
    ms, prices, fcs = store.markets(), store.snapshots_by_market(), paper.latest_forecasts()
    held = book.holdings(store.decisions())
    out: list[tuple[Market, Any]] = [(ms[mid], fcs.get(mid)) for mid, h in sorted(held.items(), key=lambda kv: -kv[1].cost) if mid in ms and ms[mid].status == "open"]
    fresh: list[tuple[float, Market, Any]] = []
    for mid, f in fcs.items():
        m, ft = ms.get(mid), store.parse_iso(f.made_at)
        end = store.parse_iso(m.end_date) if m else None
        if m is None or m.status != "open" or mid in held or ft is None or (now - ft).days > flags.TRADE_FORECAST_MAX_AGE_DAYS:
            continue
        if end is not None and end <= now:
            continue
        p = _fresh_yes(prices.get(mid, []), now)
        if p is not None:
            fresh.append((abs(f.p - p), m, f))
    out += [(m, f) for _, m, f in sorted(fresh, key=lambda t: -t[0])]
    return out[:flags.TRADE_MAX_MARKETS_PER_DAY]


def _case(label: str, m: Market, f: Any, held: Any, now: datetime, record: dict, index: Any, prices: dict) -> Case:
    ev = evidence_mod.build(m, today=now.date(), record=record, index=index)
    end = store.parse_iso(m.end_date)
    rows = [s for s in prices.get(m.id, []) if s.source == "live"]
    return Case(label=label, market_id=m.id, question=m.question, event_title=m.event_title, rules=m.description, end_date=m.end_date,
                days_left=max(0, (end - now).days) if end else None, ours=f.p if f else None, ours_made=f.made_at[:10] if f else "",
                ours_why=f.rationale if f else "", yes_price=_fresh_yes(prices.get(m.id, []), now), path=_path(rows, now.date()), held=held,
                evidence=clip(ev.text, flags.TRADE_EVIDENCE_CHARS), forecast_id=f.id if f else "", ids=ev.ids)


# ── the pass ─────────────────────────────────────────────────────────────────────────────────────
def _decide(case: Case, call: Any, usd: float, now: datetime, ds: list[Decision]) -> Decision:
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
    return Decision(id=decision_id(case.market_id, fill.action, at), market_id=case.market_id, at=at, day=at[:10], action=fill.action,  # type: ignore[arg-type]
                    requested=round(asked, 2), side=fill.side, price=fill.price, shares=fill.shares, cash_flow=fill.cash_flow,  # type: ignore[arg-type]
                    realised=fill.realised, rationale=why, clips=clips, ours=case.ours, market=case.yes_price, forecast_id=case.forecast_id,
                    model="house-" + flags.TRADE_EFFORT, prompt_version=PROMPT_VERSION, usd=usd)


def today_spend(ds: list[Decision], day: str) -> tuple[set[str], float]:
    mine = [d for d in ds if d.day == day and d.action != "settle"]
    return {d.market_id for d in mine}, round(sum(d.usd for d in mine), 6)


def run(*, ask: Ask | None = None, now: datetime | None = None, limit: int | None = None, record: dict | None = None,
        index: Any = None) -> dict[str, Any]:
    """The paid pass (see module doc). Returns a report; never raises for a failed or refused call (it stops and says why)."""
    now = now or datetime.now(UTC)
    day = now.date().isoformat()
    report: dict[str, Any] = {"as_of": now.isoformat(timespec="seconds"), "settled": 0, "decided": 0, "filled": 0, "clipped": 0, "usd": 0.0, "failed": 0, "stopped": ""}
    report["settled"] = settle(now)
    if not flags.TRADE_ENABLED:
        return {**report, "stopped": "trading is switched off (markets/flags.TRADE_ENABLED)"}
    done, usd_today = today_spend(store.decisions(), day)
    todo = [(m, f) for m, f in candidates(now) if m.id not in done]
    if limit is not None:
        todo = todo[:limit]
    report["candidates"] = len(todo)
    if not todo:
        return report
    record = record if record is not None else evidence_mod.latest_record()
    index = index if index is not None else forecast.evidence_index(now.date())
    ask = ask or default_ask()
    prices = store.snapshots_by_market()
    for i in range(0, len(todo), flags.TRADE_BATCH):
        if usd_today >= flags.TRADE_MAX_USD_PER_DAY:
            report["stopped"] = f"day budget reached (${usd_today:.2f})"
            break
        ds = store.decisions()
        held = book.holdings(ds)
        cases = [_case(f"M{n}", m, f, held.get(m.id), now, record, index, prices) for n, (m, f) in enumerate(todo[i:i + flags.TRADE_BATCH], 1)]
        invested = sum(h.cost for h in held.values())
        pt = book.point("trader", now, cash_=book.cash(ds), held=held, realised_=book.realised(ds), prices=prices)
        try:
            out, usd = ask(render_task(day, cases, cash=pt.cash, equity=pt.equity, invested=invested, n_open=len(held)), ROLE)
        except Exception as exc:  # noqa: BLE001 - a failed or refused call skips this batch; a refusal ends the pass
            report["failed"] += 1
            report.setdefault("errors", []).append(f"{type(exc).__name__}: {str(exc)[:120]}")
            if type(exc).__name__ == "BudgetRefusedError":
                report["stopped"] = "the budget gate refused a call"
                break
            continue
        calls: dict[str, Any] = {}
        for c in getattr(out, "decisions", None) or []:
            calls.setdefault(str(getattr(c, "market", "")).strip().upper(), c)
        share = round(usd / len(cases), 6)
        for case in cases:                       # sequentially: each fill changes the cash and exposure the next sees
            d = _decide(case, calls.get(case.label), share, now, ds)
            ds.append(d)
            store.append_decisions([d])
            report["decided"] += 1
            report["filled"] += d.action in ("buy_yes", "buy_no", "sell")
            report["clipped"] += bool(d.clips)
        usd_today += usd
        report["usd"] = round(report["usd"] + usd, 6)
    return report
