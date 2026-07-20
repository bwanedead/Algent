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
You are Algent's analytics router. Your DEFAULT is no analytic. Emit requests ONLY when a
specific quantity, series, or comparison would make the story clearer for a house reader than
prose alone. If you are unsure, return warranted=false.

WHEN TO SAY YES (rare):
- A real time series or before/after numbers exist in the profile and a chart would show the shape.
- Two or three competing quantities side by side that a small table or one computed figure
  clarifies better than sentences.
- One computed share/rate/comparison the reader would want that is already grounded in the data.

WHEN TO SAY NO (common):
- The prose can carry the facts without a figure.
- You would only be restating claims, exemptions, or "confirmed vs reported" as a table.
- The ask is a research notebook for us (claim grades, evidence buckets, what the dossier proves).
- No real numbers exist — do not invent a chart-shaped decoration.
- Specialist matrices, legends, scoring scales, or source-grid restatements.

Kinds (only if warranted):
- `chart` — preferred when a real series or comparison exists.
- `table` — rare; only a few real quantities a house reader can scan. NEVER a confirmed/unconfirmed
  status grid, evidence-type ledger, or claim-support scoreboard.
- `insight` — rare; a single computed figure or tight comparison, not a multi-row evidence essay.
- `image` — only a genuine structural diagram; never decoration.

Hard caps on judgment: prefer ZERO requests; if something is essential, usually ONE. Never pad to
fill a quota. Do not invent analytics because the researcher listed "visual opportunities."

Ground every request in profile data ids. Titles and questions are PUBLISHED for the reader —
plain language, no pipeline ids, no "what the claims prove" framing.

OUTPUT — AnalyticsPlan: warranted=false with empty requests is the normal success; warranted=true
only with the minimal grounded requests that actually help.
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
        "## Addressable data ids (ground any request in these)",
        *ids,
        *(["", "## Optional researcher notes (not a mandate to chart):",
           *[f"- {f}" for f in flags]] if flags else []),
        "",
        render_briefing(profile),
        "",
        "TASK: Default is warranted=false. Request an analytic ONLY if a real quantity/series/"
        "comparison in the data would help a house reader more than prose. Never emit evidence "
        "ledgers, claim-status tables, or padded multi-request sets. Zero is success.",
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
    # Drop any request whose data_refs don't resolve to the profile (no ungrounded analytics).
    valid = {x.id for x in (*profile.claim_ledger, *profile.source_ledger, *profile.threads)}
    requests = [r.model_copy(update={"data_refs": [d for d in r.data_refs if d in valid]}) for r in requests]
    requests = [r for r in requests if r.data_refs]  # a request grounded in nothing is not a request
    requests = [r for r in requests if _is_reader_facing(r)]
    note = plan.note
    if plan.requests and not requests:
        note = (note + " | dropped non-reader-facing / ungrounded analytics").strip(" |")
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
