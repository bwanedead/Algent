"""
``evidence/production-research@1``: production's corpus research (``markets/research.py``: a cheap model plans queries over six corpus tools, the tools run, the
decision reads the results) run against a cutoff-bounded view of the corpus (``cutoff_corpus.CutoffCorpus``) instead of the live index.

The planner prompt and the research knobs are captured as policy params at freeze time (``controls.freeze_production_research``); the planner is built from
the captured prompt, not from the live module. The query runner and the renderer are production's own code, so a change there changes ``impl_sha`` and the
protocol must be re-frozen: that is the drift detector. Unlike the snapshot policies this one calls a model (the planner); its cost is returned and added to
the run's cost.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from . import store
from .contracts import Evidence, Question
from .cutoff_corpus import CutoffCorpus

NAME, VERSION = "production-research", 1
PlanAsk = Callable[[str, str], tuple[Any, float]]
_LINE = re.compile(r"\[(?P<id>[^\]]+)\] (?P<date>\S*) (?P<kind>[^:]*): (?P<body>.*)")      # markets/research.py::Hit.line


@dataclass
class Retrieved:
    chosen: list[Evidence]
    text: str                                   # exactly what the decision reads (production renders the same way)
    usd: float = 0.0
    trace: dict[str, Any] = field(default_factory=dict)


def captured_params() -> dict[str, Any]:
    """Production's research settings AS THEY ARE NOW (planner prompt included), for the freeze."""
    from algent_backend.markets import flags as mf
    from algent_backend.markets import research as rs

    return {"plan_role": rs.PLAN_ROLE, "plan_cap_usd": mf.RESEARCH_PLAN_CAP_USD, "plan_effort": mf.RESEARCH_PLAN_EFFORT, "plan_max_tokens": 1200, "tools": list(rs.TOOLS),
            "max_rounds": mf.RESEARCH_MAX_ROUNDS, "queries_per_round": mf.RESEARCH_QUERIES_PER_ROUND, "rows_per_query": mf.RESEARCH_ROWS_PER_QUERY,
            "chars_per_market": mf.RESEARCH_CHARS_PER_MARKET, "lookback_days": mf.RESEARCH_LOOKBACK_DAYS}


def live_plan_ask(params: dict[str, Any]) -> PlanAsk:
    """The planner as frozen: its captured prompt, effort and cap, one structured call under the budget gate."""
    from algent_backend.markets import forecast, research

    return forecast.default_ask(params["plan_role"], research.Plan, float(params["plan_cap_usd"]), params["plan_effort"], max_tokens=int(params["plan_max_tokens"]))


def knob_drift(params: dict[str, Any]) -> dict[str, Any]:
    """Settings the research code reads live that now differ from the frozen params (production's flags moved since the freeze). Reported, not hidden."""
    now = captured_params()
    return {k: {"frozen": params.get(k), "now": now[k]} for k in now if k != "plan_role" and params.get(k) != now[k]}


def _to_evidence(row: re.Match[str], known: dict[str, Evidence], cutoff: str) -> Evidence | None:
    rid, kind = row["id"], row["kind"]
    if kind == "entity":                          # an entity summary is rebuilt from bounded queries, so it is "as of" the cutoff
        when = cutoff
    else:
        t, c = store.parse_time(row["date"]), store.parse_time(cutoff)
        if rid in known:
            return known[rid]
        if t is None or c is None or t > c:       # defence in depth: nothing undated or later than the cutoff reaches the model, whatever the corpus view did
            return None
        when = row["date"]
    if rid in known:
        return known[rid]
    return Evidence(id=rid, kind=kind, source=f"corpus/{kind}", title="", body=row["body"], event_time=when, publish_time=when, content_hash=store.digest(row["body"]))


def retrieve(items: list[Evidence], q: Question, params: dict[str, Any], *, plan_ask: PlanAsk | None, corpus: Any) -> Retrieved:
    """Production's planned research over the cutoff-bounded corpus. ``items`` is what the access reader allows (the snapshot)."""
    from algent_backend.markets import research as rs

    if plan_ask is None or corpus is None:
        raise ValueError("evidence/production-research needs a planner and a corpus handle")
    known = {e.id: e for e in items}
    view = CutoffCorpus(corpus, known, q.cutoff)
    item = rs.Item(label="M1", question=q.text, rules=q.rules, end_date=q.closes_at, countries=list(q.hints.get("countries", [])), theaters=list(q.hints.get("theaters", [])))
    res = rs.research([item], plan_ask=plan_ask, corpus=view, today=date.fromisoformat(q.cutoff[:10]), chars=int(params["chars_per_market"]))["M1"]
    kept: list[tuple[str, Evidence]] = []
    for ln in res.text.splitlines():
        m = _LINE.match(ln)
        ev = _to_evidence(m, known, q.cutoff) if m else None
        if ev is not None:
            kept.append((ln, ev))
    trace = {"queries": [r.model_dump() for r in res.runs], "rounds": res.rounds, "returned": len(res.returned), "shown": [e.id for _, e in kept],
             "hidden_by_cutoff": dict(view.dropped), "unproven_derived_rows": dict(view.unproven), "knob_drift": knob_drift(params)}
    return Retrieved(chosen=[e for _, e in kept], text="\n".join(ln for ln, _ in kept), usd=float(res.usd), trace=trace)
