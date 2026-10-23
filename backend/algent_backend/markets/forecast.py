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

import time
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from typing import Any, Literal

from pydantic import BaseModel, Field

from . import books, gaps, research, trace
from . import evidence as evidence_mod
from . import flags, store
from .contracts import Forecast, Market, forecast_id

PROMPT_VERSION = "blind-v1"
PROMPT_VERSION_RESEARCH = "blind-v2"

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


RESEARCH_ADDENDUM = """
Where the evidence comes from. What the desk knows is what its own corpus returned for queries planned for this question: dated documents,
claims, events and entities, each with a bracketed id. That is all there is; nothing outside it is available, and a thin result is information too.
Cite the ids you actually used. Say how well the evidence served you in `evidence`: "sufficient" (it bears directly on the trigger in the
rules), "thin" (some bearing, large holes) or "gap" (it tells you little). When it is thin or a gap, name in `gap_topic` the one specific thing the
desk's research should look into next (a short noun phrase a researcher could act on: a person, event, document or figure) and in `gap_why` what you
would do with it. Do not name a gap you did not need.
"""


class ForecastOut(BaseModel):
    probability: float = Field(description="Probability the question resolves YES, between 0 and 1 (never exactly 0 or 1).")
    rationale: str = Field(description="Two to four sentences: base rate, what moved you from it, what would change your mind.")
    cited: list[str] = Field(default_factory=list, description="Evidence ids (bracketed ids in the evidence) that bore on the answer.")
    evidence: Literal["sufficient", "thin", "gap"] = Field(default="sufficient", description="How well the evidence served this question.")
    gap_topic: str = Field(default="", description="When thin or a gap: the one specific thing the desk should research next. Empty if sufficient.")
    gap_why: str = Field(default="", description="When you named a gap: what you would do with it.")


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
def today_spend(forecasts: list[Forecast], day: str, book: str = "daily") -> tuple[int, float]:
    mine = [f for f in forecasts if f.made_at.startswith(day) and f.book == book]
    return len(mine), round(sum(f.usd for f in mine), 6)


def candidates(now: datetime, book: str = "daily") -> list[Market]:
    """Open markets worth a forecast now, best first: not forecast within ``REFORECAST_DAYS`` (the fast book: ``FAST_FORECAST_MAX_AGE_H`` hours, and only
    markets inside its horizon), priced inside the skip band, still running. Order: markets we hold evidence for (mapped to a theater) first, then by volume."""
    spec = books.get(book)
    again = timedelta(days=flags.REFORECAST_DAYS) if book == "daily" else spec.forecast_max_age()
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
        if (book != "daily" and not spec.in_scope(m, now)) or (m.id in last and now - last[m.id] < again):
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


def _evidence_for(m: Market, now: datetime, *, plan_ask: Any, corpus: Any, record: dict[str, Any], index: Any) -> tuple[evidence_mod.Evidence, research.Researched | None, str]:
    """(what the forecaster reads, the research behind it, the mode). Research on and a corpus index present: the corpus results (plus evidence.py's blocks
    only if ``CORPUS_ONLY`` is off). Otherwise evidence.py's blocks, and the mode says why."""
    if not flags.RESEARCH_ENABLED:
        return evidence_mod.build(m, today=now.date(), record=record, index=index), None, "base"
    if corpus is None:
        return evidence_mod.build(m, today=now.date(), record=record, index=index), None, "base-fallback"
    res = research.research([research.item_for("M1", m)], plan_ask=plan_ask, corpus=corpus, today=now.date())["M1"]
    if flags.CORPUS_ONLY:
        return evidence_mod.Evidence(text=res.text, ids=list(res.ids), n_blocks=1 if res.text else 0), res, "corpus"
    base = evidence_mod.build(m, today=now.date(), record=record, index=index)
    return evidence_mod.Evidence(text="\n\n".join(t for t in (res.text, base.text) if t), ids=[*res.ids, *base.ids], n_blocks=base.n_blocks + 1), res, "corpus"


def run(*, ask: Ask | None = None, now: datetime | None = None, limit: int | None = None, record: dict[str, Any] | None = None,
        index: Any = None, book: str = "daily", plan_ask: Any = None, corpus: Any = None) -> dict[str, Any]:
    """The paid pass. Stops at the day's count or dollar limit, on a refused call, or when the list is done. Returns a report.

    ``book="fast"`` forecasts only markets inside the fast horizon, at most ``FAST_FORECASTS_PER_RUN`` a run and within the fast book's spend cap
    (which also pays for its trade call), so the short-horizon trader always has a fresh blind forecast to compare the price with."""
    now = now or datetime.now(UTC)
    day = now.date().isoformat()
    spec = books.get(book)
    report: dict[str, Any] = {"as_of": now.isoformat(timespec="seconds"), "book": book, "made": 0, "usd": 0.0, "failed": 0, "stopped": ""}
    if not flags.FORECAST_ENABLED or (book == "fast" and not spec.enabled()):
        return {**report, "stopped": "forecasting is switched off (markets/flags)"}
    n_today, usd_today = today_spend(store.forecasts(), day, book)
    if book == "fast":
        usd_today = books.spend_today(store.decisions("fast"), store.forecasts(), now, spec)
        quota = min(flags.FAST_FORECASTS_PER_RUN, limit if limit is not None else flags.FAST_FORECASTS_PER_RUN)
        usd_cap, run_cap = flags.FAST_MAX_USD_PER_DAY, flags.FAST_MAX_USD_PER_RUN * 0.5          # forecasts take at most half a run's money; the trade call needs the rest
    else:
        quota = min(flags.MAX_FORECASTS_PER_DAY - n_today, limit if limit is not None else flags.MAX_FORECASTS_PER_DAY)
        usd_cap, run_cap = flags.MAX_FORECAST_USD_PER_DAY, flags.MAX_FORECAST_USD_PER_DAY
    todo = candidates(now, book)
    report["candidates"] = len(todo)
    if quota <= 0:
        return {**report, "stopped": f"day limit reached ({n_today} forecasts today)"}
    if not todo:
        return report
    record = record if record is not None else evidence_mod.latest_record()
    role = ROLE + (RESEARCH_ADDENDUM if flags.RESEARCH_ENABLED else "")
    ask = ask or default_ask(role)
    if flags.RESEARCH_ENABLED:
        corpus = corpus if corpus is not None else research.open_corpus()
        plan_ask = plan_ask or (research.default_plan_ask() if corpus is not None else None)
    if index is None and not (corpus is not None and flags.RESEARCH_ENABLED and flags.CORPUS_ONLY):         # evidence.py's retrieval index is only read when its blocks are
        index = evidence_index(now.date())
    spent_run = 0.0
    for m in todo[:quota]:
        if usd_today >= usd_cap or spent_run >= run_cap:
            report["stopped"] = f"day budget reached (${usd_today:.2f})" if usd_today >= usd_cap else f"run budget reached (${spent_run:.2f})"
            break
        t0 = time.monotonic()
        try:
            ev, res, mode = _evidence_for(m, now, plan_ask=plan_ask, corpus=corpus, record=record, index=index)
            out, usd = ask(task_for(m, ev, now.date()), role)
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
        plan_usd = res.usd if res else 0.0
        usd = round(usd + plan_usd, 6)                                                         # planning is part of this forecast's cost
        made_at = now.isoformat(timespec="seconds")
        shown = set(ev.ids)
        cited = [c for c in getattr(out, "cited", []) or [] if c in shown]                     # only ids that were actually shown
        verdict = (getattr(out, "evidence", "") or "") if mode == "corpus" else ""
        topic = " ".join(str(getattr(out, "gap_topic", "") or "").split()) if verdict in ("thin", "gap") else ""
        end = store.parse_iso(m.end_date)
        fid = forecast_id(m.id, made_at)
        store.append_forecast(Forecast(id=fid, market_id=m.id, made_at=made_at, p=clamp(p),
                                       rationale=" ".join(str(getattr(out, "rationale", "")).split())[:900], evidence_ids=cited,
                                       theaters=m.theaters, model="house-low", prompt_version=PROMPT_VERSION_RESEARCH if mode == "corpus" else PROMPT_VERSION, usd=usd, book=book, evidence=verdict,
                                       hours_to_end=round((end - now).total_seconds() / 3600, 1) if end else None))
        trace.write([trace.build("forecast", book=book, market_id=m.id, ref=fid, at=made_at, res=res, mode=mode, cited=cited, evidence=verdict, gap_topic=topic,
                                 decision_usd=usd - plan_usd, latency_ms=int((time.monotonic() - t0) * 1000), out_chars=len(str(getattr(out, "rationale", ""))))])
        if topic:
            gaps.record(topic, str(getattr(out, "gap_why", "") or ""), market_id=m.id, question=m.question, book=book, kind="forecast", at=made_at)
        usd_today += usd
        spent_run += usd
        report["made"] += 1
        report["usd"] = round(report["usd"] + usd, 6)
    return report
