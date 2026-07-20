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
You are Algent's analytics router. The only question is USEFULNESS for a house reader:

  Would a chart/table of real numbers make this story easier to understand than prose alone?

- If YES and the data exists in the profile: request it (usually one, grounded request).
- If NO, or you are unsure, or the data is not there: warranted=false. That is success, not failure.
- Never request an analytic for decoration, completeness, or because a field is empty.

YES when: a real series, before/after, share, or small comparison exists and a figure would show
the shape or magnitudes faster than sentences.
NO when: prose is enough; no real numbers; the ask would only restate claims or build an
evidence notebook (confirmed vs unconfirmed, claim grades, "what the dossier proves");
specialist matrices / legends / scoreboards.

Kinds (only if useful):
- `chart` — preferred when a real series or comparison exists.
- `table` — only a few real quantities a house reader can scan (never a status/evidence ledger).
- `insight` — a single computed figure or tight comparison, not a multi-row evidence essay.
- `image` — genuine structural diagram only; never decoration.

Reader clarity is part of usefulness. Every request's `title` and `question` are PUBLISHED:
- `title`: names what is measured in plain words (not jargon, not pipeline ids).
- `question`: one sentence a cold reader can use as "what this shows" — the comparison or quantity
  and why it matters to the story. No "what the claims prove" framing.

Ground every request in profile data ids. Do not invent analytics because the researcher listed
visual opportunities. Prefer zero or one request; never pad.

OUTPUT — AnalyticsPlan: warranted=false with empty requests when nothing useful; otherwise the
minimal grounded request(s) that actually help.
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
        "TASK: Decide only by usefulness. If a real quantity/series/comparison would help a "
        "house reader more than prose, request it with a title that names what is measured and a "
        "question that states what the figure shows. Otherwise warranted=false. Never evidence "
        "ledgers or claim-status tables. Zero is a normal success.",
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
