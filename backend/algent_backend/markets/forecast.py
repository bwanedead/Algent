"""
Our forecasts: one cheap structured model call per market, BLIND to the market's price.

Why blind. A forecaster shown 62% drifts toward 62%: the market's number anchors it, and a track record built on anchored forecasts measures
nothing but our ability to copy. So the model sees the question, the market's own resolution rules and what the desk knows (``evidence.py``)
and nothing the market believes. The price is read only AFTER we have committed, by ``paper.py`` and ``score.py``.

Forecasts are immutable. Each is one appended line with its timestamp, rationale, the evidence ids it cited and what it cost; a later view
of the same market is a new line, never an edit. The pass is bounded twice (``flags.MAX_FORECASTS_PER_DAY`` and
``flags.MAX_FORECAST_USD_PER_DAY``) and each call is capped (``flags.FORECAST_CALL_CAP_USD``); the budget gate refuses a call the day's spend
halt forbids.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from typing import Any

from pydantic import BaseModel, Field

from . import evidence as evidence_mod
from . import flags, store
from .contracts import Forecast, Market, forecast_id

PROMPT_VERSION = "blind-v1"

ROLE = """\
You are a forecaster on an intelligence desk. You are given ONE yes/no question about the world, the exact rules by which it will be settled, and
what the desk currently knows. Give the probability that it resolves YES.

You are deliberately NOT told what any prediction market, bookmaker or crowd currently thinks, and you must not try to guess or recall it. Your
value to the desk is an independent estimate: if you reproduce the crowd you add nothing, and your later score would only measure how well you
copy. Reason from the evidence and from base rates, then commit.

How to do it well:
- Start from the base rate for this KIND of event over this much time, and say what it is. Most dated "will X happen by D" questions resolve NO;
  status quo and slow institutions win far more often than headlines suggest. Move away from the base rate only as far as the evidence earns.
- Read the resolution rules literally. The question is settled by those rules, not by your sense of what the spirit of it is. A ceasefire that
  "continues through" a date, a leader "out" of office, an agreement "announced": each has a specific trigger, and the gap between the headline
  and the trigger is where forecasts go wrong. Note how much time is left; short windows leave little room.
- Use the evidence for what it is. A daily section is the desk's own earlier reading, not ground truth; a statement is a signal of intent, not an
  act; a calendar item is a plan, not an outcome. If the evidence says nothing relevant, say so and stay near the base rate; "I have no
  information beyond the base rate" is a legitimate, honest answer and is better than an invented story.
- Be calibrated, not cautious. Do not retreat to 50% to avoid being wrong: 50% means a coin flip, and almost nothing you are asked is one. Use
  small and large numbers (2%, 8%, 90%) when the situation warrants, but never 0% or 100%: you cannot be certain.
- Cite only evidence ids that appear in the evidence (the bracketed ids such as theater:..., calendar:..., statement:...). Do not invent ids.
- The rationale is two to four sentences a reader can check: the base rate, what moved you from it, what would change your mind.
"""


class ForecastOut(BaseModel):
    probability: float = Field(description="Probability the question resolves YES, between 0 and 1 (never exactly 0 or 1).")
    rationale: str = Field(description="Two to four sentences: base rate, what moved you from it, what would change your mind.")
    cited: list[str] = Field(default_factory=list, description="Evidence ids (bracketed ids in the evidence) that bore on the answer.")


Ask = Callable[[str, str], tuple[Any, float]]


def clamp(p: float) -> float:
    return round(min(flags.P_MAX, max(flags.P_MIN, float(p))), 4)


def task_for(m: Market, ev: evidence_mod.Evidence, today: date) -> str:
    end = m.end_date[:10] or "unspecified"
    left = ""
    if (e := store.parse_iso(m.end_date)) is not None:
        left = f" ({max(0, (e - datetime.now(UTC)).days)} days from now)"
    body = ev.text or "(The desk holds nothing relevant to this question. Say so and use base rates.)"
    return (f"TODAY: {today.isoformat()}\n\nQUESTION: {m.question}\n"
            + (f"PART OF: {m.event_title}\n" if m.event_title and m.event_title != m.question else "")
            + f"ENDS: {end}{left}\n\nRESOLUTION RULES (the market's own text):\n{m.description or '(none given)'}\n\n"
              f"WHAT THE DESK KNOWS:\n{body}\n\nTASK: the probability this resolves YES, with a brief rationale and the evidence ids you used.")


def default_ask(role: str = ROLE, schema: type[BaseModel] = ForecastOut, cap_usd: float = flags.FORECAST_CALL_CAP_USD,
                effort: str = "low", max_tokens: int = 2048) -> Ask:
    """(task, role) -> (structured answer, usd). The house model under a per-call cap and the budget gate. The trader reuses this
    plumbing with its own role, schema and cap."""
    from langchain_core.messages import HumanMessage, SystemMessage

    from algent_backend.agent_system.foundation import cost
    from algent_backend.agent_system.foundation.models import house_spec
    from algent_backend.agent_system.foundation.models.budget_gate import gate_chat_model
    from algent_backend.agent_system.foundation.models.resolver import ModelResolver
    from algent_backend.agent_system.prompting import UNIVERSAL_AGENT_BASE, compose_system_prompt

    spec = house_spec(reasoning_effort=effort, temperature=0.2, max_tokens=max_tokens)
    client = ModelResolver().resolve(spec).client
    model = gate_chat_model(client)
    system = compose_system_prompt(UNIVERSAL_AGENT_BASE, role)

    def ask(task: str, _role: str = "") -> tuple[Any, float]:
        with cost.scoped(cap_usd, spec.model):
            out = model.with_structured_output(schema).invoke([SystemMessage(content=system), HumanMessage(content=task)])
            led = cost.current_ledger()
            usd = led.spent_usd if led is not None else cost.spent_usd()
        return out, round(float(usd), 6)

    return ask


# ── selection ────────────────────────────────────────────────────────────────────────────────────
def today_spend(forecasts: list[Forecast], day: str) -> tuple[int, float]:
    mine = [f for f in forecasts if f.made_at.startswith(day)]
    return len(mine), round(sum(f.usd for f in mine), 6)


def candidates(now: datetime) -> list[Market]:
    """Open markets worth a forecast now, best first: not forecast within ``REFORECAST_DAYS``, priced inside the skip band, still running.
    Order: markets we hold evidence for (mapped to a theater) first, then by volume."""
    by_price = store.snapshots_by_market()
    last: dict[str, datetime] = {}
    for f in store.forecasts():
        t = store.parse_iso(f.made_at)
        if t is not None and t > last.get(f.market_id, datetime.min.replace(tzinfo=UTC)):
            last[f.market_id] = t
    out = []
    for m in store.markets().values():
        if m.status != "open":
            continue
        end = store.parse_iso(m.end_date)
        if end is not None and end <= now:
            continue
        if m.id in last and now - last[m.id] < timedelta(days=flags.REFORECAST_DAYS):
            continue
        live = [s for s in by_price.get(m.id, []) if s.source == "live"]
        newest = store.parse_iso(live[-1].at) if live else None
        if newest is None or now - newest > timedelta(hours=flags.PRICE_FRESH_H) or not (flags.SKIP_BELOW <= live[-1].p <= flags.SKIP_ABOVE):
            continue
        out.append(m)
    return sorted(out, key=lambda m: (not m.theaters, -m.volume))


def evidence_index(today: date) -> Any:
    """The retrieval index shared by a pass (built once). None if it cannot be built: the base evidence still works."""
    try:
        from algent_backend.retrieval.search import Index

        return Index.build(today)
    except Exception:  # noqa: BLE001
        return None


def run(*, ask: Ask | None = None, now: datetime | None = None, limit: int | None = None, record: dict[str, Any] | None = None,
        index: Any = None) -> dict[str, Any]:
    """The paid pass. Stops at the day's count or dollar limit, on a refused call, or when the list is done. Returns a report."""
    now = now or datetime.now(UTC)
    day = now.date().isoformat()
    report: dict[str, Any] = {"as_of": now.isoformat(timespec="seconds"), "made": 0, "usd": 0.0, "failed": 0, "stopped": ""}
    if not flags.FORECAST_ENABLED:
        return {**report, "stopped": "forecasting is switched off (markets/flags.FORECAST_ENABLED)"}
    n_today, usd_today = today_spend(store.forecasts(), day)
    quota = min(flags.MAX_FORECASTS_PER_DAY - n_today, limit if limit is not None else flags.MAX_FORECASTS_PER_DAY)
    todo = candidates(now)
    report["candidates"] = len(todo)
    if quota <= 0:
        return {**report, "stopped": f"day limit reached ({n_today} forecasts today)"}
    if not todo:
        return report
    record = record if record is not None else evidence_mod.latest_record()
    ask = ask or default_ask()
    index = index if index is not None else evidence_index(now.date())
    for m in todo[:quota]:
        if usd_today >= flags.MAX_FORECAST_USD_PER_DAY:
            report["stopped"] = f"day budget reached (${usd_today:.2f})"
            break
        ev = evidence_mod.build(m, today=now.date(), record=record, index=index)
        try:
            out, usd = ask(task_for(m, ev, now.date()), ROLE)
        except Exception as exc:  # noqa: BLE001 - a refused or failed call skips this market, and a refusal ends the pass
            report["failed"] += 1
            report.setdefault("errors", []).append(f"{m.id}: {type(exc).__name__}: {str(exc)[:120]}")
            if type(exc).__name__ == "BudgetRefusedError":
                report["stopped"] = "the budget gate refused a call"
                break
            continue
        p = getattr(out, "probability", None)
        if not isinstance(p, (int, float)) or not (0.0 <= float(p) <= 1.0):
            report["failed"] += 1
            continue
        made_at = datetime.now(UTC).isoformat(timespec="seconds") if now is None else now.isoformat(timespec="seconds")
        cited = [c for c in getattr(out, "cited", []) or [] if c in set(ev.ids)]            # only ids that were actually shown
        store.append_forecast(Forecast(id=forecast_id(m.id, made_at), market_id=m.id, made_at=made_at, p=clamp(p),
                                       rationale=" ".join(str(getattr(out, "rationale", "")).split())[:900], evidence_ids=cited,
                                       theaters=m.theaters, model="house-low", prompt_version=PROMPT_VERSION, usd=usd))
        usd_today += usd
        report["made"] += 1
        report["usd"] = round(report["usd"] + usd, 6)
    return report
