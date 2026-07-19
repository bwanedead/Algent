"""
The analytics router — profile -> AnalyticsPlan. Assesses whether a story would be clearer with an
analytic (chart / table / computed insight / illustrative image) and emits grounded requests.

Tool-free, one structured call on the nano tier. Honest by doctrine: it may only request analytics
that AID understanding and are grounded in the profile's actual data (by id) — never invented data,
never decoration. Most stories warrant nothing, and that is the expected common outcome.
"""

from __future__ import annotations

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

from .analytics_contracts import AnalyticsPlan

ARTIFACT_NAME = "analytics_plan.json"
ANALYTICS_COMPLETED = "analytics.completed"
GENERATOR = "analytics_router@v1"

_ROLE = """\
You are Algent's analytics router. Assess whether this story would be conveyed MORE CLEARLY with an
analytic, and if so, request exactly what would help — no more.

Kinds — pick the form the QUESTION deserves, and PREFER A VISUAL when the data supports one:
- `chart` — a plot of real data, and the FIRST thing to reach for when there is a real series or
  comparison. A reader takes a shape in at a glance that a table makes them assemble row by row.
  The bar is honest data, not lots of it: three real points over time is a chart. What is NOT a
  chart is numbers that aren't a series at all.
- `table` — LOWER pressure: use it when values genuinely exist but no visual would add anything
  (competing figures side by side, a definitional dispute, before/after pairs). A table is the
  fallback, not the default. Keep it SMALL — a few columns a HOUSE READER can scan. If it needs
  seven columns it is a data dump, not an analytic; cut it down or make it a chart.
  NEVER restate a source's own matrix (version→patch, CVE→severity, "score → meaning" legend) —
  that is the advisory's compliance grid re-gridded. A table must COMPUTE, COMPARE, or REVEAL
  something a general reader could not get by reading the source; a table only an affected
  specialist could use fails even when the cells are accurate. Drop it.
  NEVER emit a key/legend/scoring-scale as its own analytic — fold it into the thing it describes
  or drop it.
- `insight` — ANY analysis of the cited data that is not a picture: a computed figure the reader
  would want (a rate of change, a share, a baseline comparison, a reconciliation of two sources
  that disagree, a bound on what the numbers can support). This is the widest kind and the most
  under-used — reach for it whenever the value is in the COMPUTATION, not the visual.
- `image` — an AI-generated ILLUSTRATION/diagram, never a fabricated photo of a real event/person.
The worker is a general analysis tool, not a chart generator; the kind is your judgement about what
would actually help, and "no visual, but this figure computed and stated" is a first-class answer.

RULES (honesty first — see spirit.md):
- Ground every request in the profile's ACTUAL data: cite the claim/source/thread ids that supply
  it. If the data for a chart is not in the profile, do not request the chart.
- Request only what AIDS understanding — the key quantity, the trend, the comparison that carries
  the story. Never decoration, never a chart for its own sake.
- Prefer none. MOST stories do not need an analytic; returning warranted=false with no requests is
  the common, correct outcome. Do not manufacture a reason.

WRITE `title` AND `question` FOR THE READER — they are PUBLISHED, not internal notes. The title
captions the figure and the question becomes the line under it that says what it shows, so a reader
meeting the artifact cold knows what they are looking at. Plain language, no pipeline vocabulary,
no ids. "What share of normal traffic is still moving through Hormuz?" — not "quantify transit
delta vs baseline per clm refs".

OUTPUT — an AnalyticsPlan: warranted (bool) and, if true, the grounded requests (kind, title,
question, spec, data_refs by id, rationale).
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
    flags = profile.data_notes + profile.visual_opportunities
    return "\n".join([
        f"# ASSESS FOR ANALYTICS — {profile.id}",
        "",
        "## Addressable data ids (ground any request in these)",
        *ids,
        *(["", "## The researcher already flagged:", *[f"- {f}" for f in flags]] if flags else []),
        "",
        render_briefing(profile),
        "",
        "TASK: Would an analytic make this story clearer? If so, emit grounded AnalyticsRequests "
        "(cite data ids). If not — the common case — return warranted=false. No decoration.",
    ])


def _finalize(plan: AnalyticsPlan, profile: SignalProfile, model: str) -> AnalyticsPlan:
    requests = [r if r.id else r.model_copy(update={"id": f"anx_{i:02d}"})
                for i, r in enumerate(plan.requests, 1)]
    # Drop any request whose data_refs don't resolve to the profile (no ungrounded analytics).
    valid = {x.id for x in (*profile.claim_ledger, *profile.source_ledger, *profile.threads)}
    requests = [r.model_copy(update={"data_refs": [d for d in r.data_refs if d in valid]}) for r in requests]
    requests = [r for r in requests if r.data_refs]  # a request grounded in nothing is not a request
    return plan.model_copy(update={
        "id": f"analytics_{profile.id}", "profile_id": profile.id,
        "warranted": bool(requests) and plan.warranted, "requests": requests,
        "generator": GENERATOR, "model": model, "generated_at": datetime.now(UTC).isoformat(),
    })


def _finish(context: AgentRunContext, plan: AnalyticsPlan) -> dict[str, Any]:
    if context.artifacts is not None:
        context.artifacts.write_json(ARTIFACT_NAME, plan.model_dump())
    context.emit(ANALYTICS_COMPLETED, {
        "profile_id": plan.profile_id, "warranted": plan.warranted, "requests": len(plan.requests),
    })
    return {"analytics_plan": plan.model_dump()}
