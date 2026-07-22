"""
The analytics router — profile -> AnalyticsPlan. Assesses whether a story would be clearer with an
analytic (chart / table / computed insight / illustrative image) and emits grounded requests.

Tool-free, one structured call on the nano tier. Honest by doctrine: most stories need NOTHING.
Analytics only when a real quantity or comparison would transfer understanding the prose alone
cannot. Never decoration, never a research notebook for the machine.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any, TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph

from algent_backend.agent_system.agents.newsroom import doctrine
from algent_backend.agent_system.agents.newsroom_map import NEWSROOM_SYSTEM_MAP
from algent_backend.agent_system.agents.research.briefing import render_briefing
from algent_backend.agent_system.agents.research.profile import SignalProfile
from algent_backend.agent_system.foundation.models import ModelSpec
from algent_backend.agent_system.prompting import UNIVERSAL_AGENT_BASE, compose_system_prompt
from algent_backend.agent_system.runs.context import AgentRunContext

from .analytics_contracts import AnalyticsPlan, AnalyticsRequest

ARTIFACT_NAME = "analytics_plan.json"
ANALYTICS_COMPLETED = "analytics.completed"
GENERATOR = "analytics_router@v1"

# Live failure mode: every run shipped 3 analytics, many of them 2-column "evidence ledgers"
# (confirmed vs unconfirmed, claim support buckets) that only restate the profile for the machine.
_META_LEDGER = re.compile(
    r"confirm(ed)?\s+vs|unconfirm|"
    r"evidence[- ]grade|evidence type|"
    r"what we can and cannot|"
    r"support in claims|claims? read|"
    r"status in verified|status text|"
    r"first-party|secondary source|"
    r"what .{0,60}(does|doesn't|does not).{0,30}prove|"
    r"bucket|claim.?status|ledger",
    re.I,
)

_ROLE = """\
You are Algent's analytics router. The only criterion is USEFULNESS for a house reader:

  What visual (if any) would most help them grasp scale, trajectory, place, or comparison —
  better than prose alone?

Profile and analytics are SEPARATE concerns. The profile is a researched story map — it is NOT
a data warehouse. Do NOT refuse a useful chart just because a multi-row series is not already
in the claim ledger. Ask: would a figure help, and is the data reasonably available?

- If something useful exists: request that one analytic.
- If nothing would help: warranted=false. That is success.
- Never decorate, never fill a quota, never invent numbers or a map without data.

UTILITY CLASSES (pick the one that helps most):
1. TRAJECTORY — counts or rates over time (is it rising, peaking, slowing?). Prefer a simple
   line/area chart with clear axes and period.
2. GEOGRAPHY — the story names subregions (provinces, cities, villages, zones) a cold reader will
   not place. Prefer a bar/ranked breakdown by region with counts or rates when magnitude is the
   point. Prefer a **map** when location/scope is the point. Map rules (accuracy is paramount):
   - Default frame is **country or larger theater**, not a zoom-only cluster of three towns with
     no national context. The reader should see where the cluster sits relative to the country,
     capital, major city, and relevant border (and a named river/line only if the story uses it).
   - Local detail may be an **inset callout** of the village cluster *inside* that country frame —
     not a floating schematic that could be anywhere.
   - Use real geocodes / standard basemap geometry when sourcing; never freehand place-names into
     invented relative positions presented as geographic truth. If coordinates cannot be found,
     skip the map rather than ship a plausible-looking fiction.
   - Never invent boundaries, control areas, or rates not in the data.
3. COMPARATIVE SCALE — absolute counts float without a reference. Prefer a small comparison to a
   baseline the reader can hold (prior peak, share of population, share of a total, another
   country) when those numbers exist or are publicly standard.
4. STRUCTURE — a before/after or part-of-whole that prose makes the reader assemble row by row.

DATA PATHS (either is fine):
A. PROFILE-HELD — key magnitudes already appear as claims/sources. Set `data_refs` to those ids.
B. SOURCE-AT-ANALYTICS-TIME — a series/breakdown would help but is not in the profile (normal).
   Set `may_source=true` and `source_hint` to a concrete public source hunch
   (e.g. "WHO / MoH weekly Ebola case counts for DRC provinces, last 8 weeks";
   "BLS CPI release table, last 12 months core PCE y/y"). The worker may fetch that data.
   Optional: still cite a few claim ids that motivate WHY the figure helps the story.

YES when one of those classes applies and either (A) numbers are already cited or (B) a
reasonable public source is likely to hold them.
NO when prose is enough; the ask would be an evidence notebook (confirmed vs unconfirmed,
claim grades); specialist matrices / legends; or pure decoration with no real quantity.

Kinds (only if useful):
- `chart` — preferred for trajectory, ranked regional breakdowns, and comparisons.
- `table` — only a few real quantities (never status/evidence ledgers).
- `insight` — one computed figure or tight comparison, not a multi-row claim essay.
- `image` — labeled map/diagram only when geography is the aid. Prefer country-scale + local
  inset (see GEOGRAPHY). Never invent rates, borders, or place positions; never decoration.

Reader clarity is part of usefulness. PUBLISHED fields:
- `title`: what is measured (plain words).
- `question`: what this shows — quantity/comparison + why it helps the story.
- `spec`: how to build it so a cold reader can read axes/units without reverse-engineering.
- `data_refs` and/or `may_source` + `source_hint` as above.

Prefer zero or one request.

OUTPUT — AnalyticsPlan: warranted=false when nothing useful; otherwise the single best request
(or the minimal set if two distinct utilities truly need separate figures).
"""

SYSTEM_PROMPT = compose_system_prompt(UNIVERSAL_AGENT_BASE, NEWSROOM_SYSTEM_MAP, doctrine("spirit"), _ROLE)


class AnalyticsState(TypedDict, total=False):
    profile: dict[str, Any]         # the profile to assess (input)
    analytics_plan: dict[str, Any]  # the produced AnalyticsPlan


def build_analytics_router_graph(context: AgentRunContext, *, model_spec: ModelSpec) -> Any:
    model = context.model_resolver.resolve(model_spec).client
    structured = model.with_structured_output(AnalyticsPlan)

    def route(state: AnalyticsState, config: RunnableConfig) -> dict[str, Any]:
        pdict = state.get("profile")
        if not pdict:
            return _finish(context, AnalyticsPlan(id="analytics_none", warranted=False,
                                                  note="no profile supplied"))
        profile = SignalProfile.model_validate(pdict)
        raw = structured.invoke(
            [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=_message(profile))],
            config=config,
        )
        plan = raw if isinstance(raw, AnalyticsPlan) else AnalyticsPlan(id="", warranted=False)
        return _finish(context, _finalize(plan, profile, model_spec.model))

    graph = StateGraph(AnalyticsState)
    graph.add_node("route", route)
    graph.add_edge(START, "route")
    graph.add_edge("route", END)
    return graph.compile()


def _message(profile: SignalProfile) -> str:
    ids = [
        "- claims: " + ", ".join(f"{c.id} ({c.salience})" for c in profile.claim_ledger),
        "- sources: " + ", ".join(s.id for s in profile.source_ledger),
    ]
    # Researcher flags are optional hints only — never a quota to fill.
    flags = profile.data_notes + profile.visual_opportunities
    return "\n".join([
        f"# ASSESS FOR ANALYTICS — {profile.id}",
        "",
        "## Profile data ids (optional grounding when numbers are already held)",
        *ids,
        *(["", "## Optional researcher notes (not a mandate to chart):",
           *[f"- {f}" for f in flags]] if flags else []),
        "",
        render_briefing(profile),
        "",
        "TASK: Decide only by usefulness for a house reader. A multi-row series need NOT already "
        "live in the profile — if a trajectory, place breakdown, or scale comparison would help "
        "and public data is a reasonable hunch, set may_source=true with a concrete source_hint. "
        "When key numbers are already in claims, set data_refs. Title what is measured; question "
        "what the figure shows. Never evidence ledgers or claim-status tables. Zero is a normal "
        "success.",
    ])


def _is_reader_facing(req: AnalyticsRequest) -> bool:
    """Drop research-notebook analytics that restated the claim ledger as a 2-column status grid.

    Soft doctrine alone still shipped these every run; this is the mechanical floor.
    """
    blob = " ".join(filter(None, (req.title, req.question, req.spec, req.rationale)))
    if _META_LEDGER.search(blob):
        return False
    # Status-grid tables: kind table/insight + claim-grade vocabulary without a real quantity ask.
    if req.kind in ("table", "insight"):
        grades = bool(re.search(r"\b(confirmed|unconfirmed|likely|speculative|snippet)\b", blob, re.I))
        meta = bool(re.search(r"\b(claim|evidence|status|first-party|secondary)\b", blob, re.I))
        if grades and meta:
            return False
    return True


def _finalize(plan: AnalyticsPlan, profile: SignalProfile, model: str) -> AnalyticsPlan:
    requests = [r if r.id else r.model_copy(update={"id": f"anx_{i:02d}"})
                for i, r in enumerate(plan.requests, 1)]
    # Keep profile-grounded refs that resolve; keep source-at-analytics-time asks with a real hint.
    # Drop pure ungrounded/unsourceable asks — never invent a chart with nowhere to get numbers.
    valid = {x.id for x in (*profile.claim_ledger, *profile.source_ledger, *profile.threads)}
    kept: list[AnalyticsRequest] = []
    for r in requests:
        refs = [d for d in r.data_refs if d in valid]
        r = r.model_copy(update={"data_refs": refs})
        if refs:
            kept.append(r)
            continue
        if r.may_source and (r.source_hint.strip() or r.spec.strip()):
            # Prefer an explicit source_hint; fall back to spec as the fetch brief.
            if not r.source_hint.strip() and r.spec.strip():
                r = r.model_copy(update={"source_hint": r.spec.strip()})
            kept.append(r)
    requests = [r for r in kept if _is_reader_facing(r)]
    note = plan.note
    if plan.requests and not requests:
        note = (note + " | dropped non-reader-facing / ungrounded / unsourceable analytics").strip(" |")
    return plan.model_copy(update={
        "id": f"analytics_{profile.id}", "profile_id": profile.id,
        "warranted": bool(requests) and plan.warranted, "requests": requests,
        "note": note,
        "generator": GENERATOR, "model": model, "generated_at": datetime.now(UTC).isoformat(),
    })


def _finish(context: AgentRunContext, plan: AnalyticsPlan) -> dict[str, Any]:
    if context.artifacts is not None:
        context.artifacts.write_json(ARTIFACT_NAME, plan.model_dump())
    context.emit(ANALYTICS_COMPLETED, {
        "profile_id": plan.profile_id, "warranted": plan.warranted, "requests": len(plan.requests),
    })
    return {"analytics_plan": plan.model_dump()}
