"""
Decision replay: present the FROZEN trader (``controls.freeze_trader``) with the market state and the evidence of a past cutoff and record what it decides.

The state is the one production shows: the desk's probability (here: the stored forecast of a forecast run, so the trader is chained to a named forecaster),
the market's YES price at the cutoff and its daily path up to the cutoff, the evidence that forecast run was shown, and a flat book (full bankroll, no
position). The decision goes through the frozen guards exactly as in production (``guards.apply``, slippage included) and is filled HYPOTHETICALLY at the
cutoff price. It is scored by the realised P&L of that fill once the market resolves. This is a decision board, kept apart from the forecast board: a
forecaster is judged on calibration, a trader on money, and neither number stands in for the other.

Write-once: a decision is keyed by (question, protocol, forecast run) and never redone (a paid call is not repeated).
"""

from __future__ import annotations

import math
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, Field

from . import controls, policies, score, store
from .contracts import Protocol, Question, RunRecord

Ask = Callable[[str, str], tuple[Any, float]]


class DecisionRecord(BaseModel):
    id: str
    question_id: str
    protocol_id: str
    forecast_run: str
    action: str                         # what the book did after the guards: buy_yes | buy_no | sell | hold
    asked: dict[str, Any] = Field(default_factory=dict)      # what the agent asked for (action, stake) before the guards
    side: str = ""
    price: float = 0.0                  # fill price (cutoff price plus the book's slippage)
    shares: float = 0.0
    cash_flow: float = 0.0              # negative: dollars paid
    clips: list[str] = Field(default_factory=list)
    rationale: str = ""
    cited: list[str] = Field(default_factory=list)
    desk_p: float | None = None
    market_p: float | None = None
    usd: float = 0.0
    live: bool = False
    prompt_digest: str = ""
    at: str = ""


def market_state(q: Question) -> tuple[float | None, list[tuple[str, float]]]:
    """The market's YES price at the cutoff and its daily last-price path up to it (from the markets store). Only prices at or before the cutoff are read."""
    from algent_backend.markets import flags as mf
    from algent_backend.markets import store as ms

    if not q.source.startswith("market:"):
        return None, []
    rows = sorted((s for s in ms.snapshots(q.source.split(":", 1)[1]) if (t := store.parse_time(s.at)) is not None and t <= (store.parse_time(q.cutoff) or t)), key=lambda s: s.at)
    snap = ms.price_at(rows, q.cutoff)
    path = sorted({s.at[:10]: s.p for s in rows}.items())[-mf.TRADE_PATH_DAYS:]
    return (snap.p if snap else None), path


def _evidence_of(run: RunRecord) -> tuple[str, list[str], float | None, str]:
    """(evidence text, ids shown, desk probability, desk rationale) of a stored forecast run: what the trader is chained to."""
    prompt = store.path(f"runs/{run.run_id}/prompt.txt").read_text(encoding="utf-8")
    ev = prompt.split("WHAT THE DESK KNOWS:\n", 1)[1].rsplit("\n\nTASK:", 1)[0] if "WHAT THE DESK KNOWS:\n" in prompt else ""
    shown = [s["id"] for s in (store.read_json(f"runs/{run.run_id}/manifest.json") or {}).get("shown", [])]
    return ev, shown, run.p, str((store.read_json(f"runs/{run.run_id}/output.json") or {}).get("rationale", ""))


def decision_id(q: Question, proto: Protocol, run: RunRecord) -> str:
    return store.digest([q.id, proto.id, run.run_id])[:12]


def replay(q: Question, proto: Protocol, forecast_run: RunRecord, ask: Ask, *, live: bool = False) -> DecisionRecord | None:
    """One frozen-trader decision at ``q.cutoff``. None when the forecaster abstained (the trader is never shown an invented probability) or no price exists."""
    from algent_backend.markets import guards, trader_prompt

    did = decision_id(q, proto, forecast_run)
    done = store.read_json(f"decisions/{did}/decision.json")
    if done:
        return DecisionRecord.model_validate(done)
    if forecast_run.p is None:
        return None
    yes_price, path = market_state(q)
    if yes_price is None:
        return None
    drift = list(controls.impl_drift_decision(proto))
    if drift:
        raise RuntimeError(f"the frozen trader's code changed since it was frozen: {drift}; re-freeze as a new protocol")
    params = proto.policies["decision"].params
    text, ids, desk_p, why = _evidence_of(forecast_run)
    c, e = store.parse_time(q.cutoff), store.parse_time(q.closes_at)
    case = trader_prompt.Case(label="M1", market_id=q.source, question=q.text, event_title="", rules=q.rules, end_date=q.closes_at,
                              days_left=max(0, (e - c).days) if c and e else None, ours=desk_p, ours_made=q.cutoff[:10], ours_why=why, yes_price=yes_price, path=path,
                              held=None, evidence=text, forecast_id=forecast_run.run_id, ids=ids)
    bank = float(params["bankroll"])
    task = trader_prompt.render_task(q.cutoff[:10], [case], cash=bank, equity=bank, invested=0.0, n_open=0)
    role = proto.policies["prompts"].params["role"]
    out, usd = ask(task, role)
    call = next((d for d in (getattr(out, "decisions", None) or []) if str(getattr(d, "market", "")).strip().upper() == "M1"), None)
    action = getattr(call, "action", "hold") if call is not None else "hold"
    asked = float(getattr(call, "stake_usd", 0.0) or 0.0) if call is not None else 0.0
    fill = guards.apply(action, asked, held=None, yes_price=yes_price, cash=bank, exposure=0.0, tradable=True,
                        position_frac=float(params["max_position_frac"]), exposure_frac=float(params["max_exposure_frac"]), bankroll=bank)
    clips = [*fill.clips, *(["the agent returned no decision for this market: held"] if call is None else [])]
    rec = DecisionRecord(id=did, question_id=q.id, protocol_id=proto.id, forecast_run=forecast_run.run_id, action=fill.action, asked={"action": action, "stake_usd": asked},
                         side=fill.side, price=fill.price, shares=fill.shares, cash_flow=fill.cash_flow, clips=clips,
                         rationale=" ".join(str(getattr(call, "rationale", "") or "").split())[:420], cited=[x for x in (getattr(call, "cited", None) or []) if x in set(ids)],
                         desk_p=desk_p, market_p=yes_price, usd=round(float(usd or 0.0), 6), live=live, prompt_digest=store.digest(task), at=store.now_iso())
    store.write_once(f"decisions/{did}/prompt.txt", task)
    store.write_once(f"decisions/{did}/decision.json", rec)
    return rec


def live_trader_ask(proto: Protocol) -> Ask:
    """The frozen trader's role, model effort and token bound on the house model under the budget gate, capped for the lab."""
    from algent_backend.markets import forecast, trader_prompt

    from . import flags

    m = proto.policies["model"].params
    return forecast.default_ask(proto.policies["prompts"].params["role"], trader_prompt.TraderOut, min(float(m["cap_usd"]), flags.RUN_CAP_USD), m["effort"], max_tokens=int(m["max_tokens"]))


def replay_set(doc: dict[str, Any], forecast_proto: Protocol, *, live: bool, cap_usd: float, ask: Ask | None = None) -> dict[str, Any]:
    """The frozen trader on every question of a set that ``forecast_proto`` has answered. A stored decision is reused; spend is bounded by ``cap_usd`` in total."""
    from . import flags, qset

    trader = controls.freeze_trader()
    by_q = {r.question_id: r for r in score.runs() if r.protocol_id == forecast_proto.id and r.mode == "controlled"}
    ask = ask or (live_trader_ask(trader) if live else None)
    spent, out, pending, skipped, stopped = 0.0, [], [], [], ""
    for q in qset.questions_of(doc):
        run = by_q.get(q.id)
        if run is None or run.p is None:
            skipped.append({"question": q.id, "why": "no forecast run" if run is None else "the forecaster abstained"})
            continue
        if store.exists(f"decisions/{decision_id(q, trader, run)}/decision.json"):
            continue
        if not live or spent + flags.RUN_CAP_USD > cap_usd:
            stopped = stopped or ("" if not live else f"the ${cap_usd:.2f} cap would be exceeded by the next decision (spent ${spent:.3f})")
            pending.append(q.id)
            continue
        rec = replay(q, trader, run, ask, live=True)  # type: ignore[arg-type]
        if rec is None:
            skipped.append({"question": q.id, "why": "no market price at the cutoff"})
            continue
        spent += rec.usd
        out.append({"question": q.id, "action": rec.action, "stake": round(-rec.cash_flow, 2), "usd": rec.usd})
    return {"set": doc["id"], "live": live, "trader": trader.id, "forecast_protocol": forecast_proto.id, "decided": out, "spent_usd": round(spent, 4), "cap_usd": cap_usd,
            "not_run": pending, "skipped": skipped, "stopped": stopped}


# ── scoring: the decision board ──────────────────────────────────────────────────────────────────
def decisions() -> list[DecisionRecord]:
    return [DecisionRecord.model_validate(r) for n in store.listing("decisions") if (r := store.read_json(f"decisions/{n}/decision.json"))]


def pnl(d: DecisionRecord, outcome: str) -> float:
    """Realised P&L of the hypothetical fill once the market resolved: shares x payout, less the dollars paid. A hold earns nothing."""
    if d.action not in ("buy_yes", "buy_no"):
        return 0.0
    pay = 0.5 if outcome == "void" else (1.0 if outcome == d.side else 0.0)
    return round(d.shares * pay + d.cash_flow, 2)


def board() -> dict[str, Any]:
    """Per protocol: decisions, trades, dollars staked, realised P&L, return on stake, and the mean P&L per decision with a standard error. Paired differences
    between protocols over the questions both decided. Unresolved questions are listed, not scored. Never mixed with the forecast board."""
    qs = score.questions()
    res = {qid: r for qid, q in qs.items() if (r := score.resolve(q))}
    rows = [{"decision": d.id, "question": d.question_id, "protocol": d.protocol_id, "action": d.action, "staked": round(-d.cash_flow, 2), "pnl": pnl(d, res[d.question_id].outcome),
             "usd": d.usd} for d in decisions() if d.question_id in res]
    per: dict[str, Any] = {}
    for pid in sorted({r["protocol"] for r in rows}):
        pr = [r for r in rows if r["protocol"] == pid]
        staked, total = sum(r["staked"] for r in pr), sum(r["pnl"] for r in pr)
        m, se = score.mean_se([r["pnl"] for r in pr])
        per[pid] = {"n": len(pr), "trades": sum(1 for r in pr if r["staked"] > 0), "staked": round(staked, 2), "pnl": round(total, 2),
                    "return_on_stake": round(total / staked, 4) if staked else None, "mean_pnl": m, "se_pnl": se, "usd": round(sum(r["usd"] for r in pr), 4)}
    diffs = {}
    pids = sorted(per)
    for i, a in enumerate(pids):
        for b in pids[i + 1:]:
            ba = {r["question"]: r["pnl"] for r in rows if r["protocol"] == a}
            bb = {r["question"]: r["pnl"] for r in rows if r["protocol"] == b}
            d = [ba[k] - bb[k] for k in ba.keys() & bb.keys()]
            m, se = score.mean_se(d)
            diffs[f"{a} - {b}"] = {"n_shared": len(d), "mean_pnl_diff": m, "se": se if not math.isnan(se or 0.0) else None, "note": "positive = first earned more per question"}
    return {"protocols": per, "differences": diffs, "unresolved": sorted({d.question_id for d in decisions()} - set(res)), "rows": rows,
            "note": "hypothetical fills at the cutoff price (plus slippage); decisions are judged by money, never mixed with the forecast board"}
