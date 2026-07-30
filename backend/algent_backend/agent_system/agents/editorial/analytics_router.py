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

UTILITY CLASSES (pick the one that helps most — geography often beats trajectory for place stories):
1. GEOGRAPHY / ORIENTATION MAP — warranted when the story turns on **spatial relationships a
   sentence cannot carry**: chokepoints (Bab el-Mandeb, Hormuz, Suez), multi-city strike patterns,
   borders, spread, theaters a cold Western reader cannot hold from prose alone. Prefer a
   **labeled map** (country/theater basemap + real lat/lon points) over a speculative
   shipping-cost series you may not fetch.

   **HARD RULE: a map must show a RELATIONSHIP BETWEEN AT LEAST TWO THINGS THE STORY IS ABOUT.**
   A distance, a route, a spread, a boundary, a chokepoint between two places both named in the
   piece. If the map's honest one-line description is "where X is", it is banned — no matter how
   load-bearing the place feels, no matter that the reader might wonder where it is. A named
   place plus a reader's general knowledge already answers "where is X" better than an outline
   with a dot, and we have now shipped that same useless figure three times:
     - a Canada-and-US outline with one point, for a fossil found in Saskatchewan;
     - a whole-Mars outline with one point, for dunes in Kaiser Crater — which did not even
       show the crater, let alone the dunes the article is about;
     - two Baja coordinates, where the story was the behaviour, not the geography.
   Asking "name the spatial question" was not enough of a filter, because a plausible-sounding
   question can be invented for any location. So: **count the things being related. Fewer than
   two, no map.**

   And a map may never be schematic. An approximated band, an indicative boundary, a "not an
   exact ice boundary" frost zone — a figure that has to disclaim its own geometry is not
   orienting anyone; it is decoration with a caveat. Real geocodes or no figure.

   Map rules (accuracy is paramount):
   - Default frame is **country or larger theater**, not a zoom-only cluster of three towns with
     no national context. The reader should see where the cluster sits relative to the country,
     capital, major city, and relevant border (and a named chokepoint if the story uses it).
   - Local detail may be an **inset callout** of the village/strait cluster *inside* that frame —
     not a floating schematic that could be anywhere.
   - Use real geocodes / standard basemap geometry (Natural Earth + city centroids are fine);
     never freehand place-names into invented relative positions. If coordinates cannot be found
     for a site, omit that point rather than ship a plausible-looking fiction.
   - Never invent boundaries, control areas, front lines, or rates not in the data.
   - Kind is usually `image` with spec that says **map** (worker has `lib.maps` + basemap).
   - **A map request MUST set `may_source=true`.** Coordinates, boundaries and basemap
     geometry are public reference data; they are never in a claim ledger, because a claim
     ledger holds what the *story* asserts, not where places are. A map with only
     `data_refs` is structurally unbuildable and the worker will correctly refuse it —
     observed: a typhoon-track map skipped with "no latitude/longitude for Huidong landfall
     or Hong Kong, no boundary geometry... because sourcing is disabled", leaving a
     landfall story with no picture at all. Put the story's own positions and times in
     `data_refs` as usual, and set `may_source=true` with a `source_hint` naming where the
     geocodes come from so the coordinates can be fetched and cited.
2. TRAJECTORY — counts or rates over time (is it rising, peaking, slowing?). Prefer a simple
   line/area chart with clear axes and period. Use when magnitude-over-time is the story; do not
   prefer an unfindable AIS freight series over a cheap accurate choke-point map.
3. COMPARATIVE SCALE — absolute counts float without a reference. Prefer a small comparison to a
   baseline the reader can hold (prior peak, share of population, share of a total, another
   country) when those numbers exist or are publicly standard.
4. STRUCTURE — a before/after or part-of-whole that prose makes the reader assemble row by row.

THE TEST THAT OVERRIDES ALL FOUR: **would a real publication have commissioned this?**
Ask it in that form, because a desk with a graphics budget only spends it when the picture
carries something the words cannot. Two failures, and we ship both:

- **Charting what should have stayed a sentence.** A three-step sequence of an animal's
  behaviour, drawn as boxes with arrows, is a diagram of a sentence — it adds no quantity, no
  comparison, no scale, nothing the sentence did not already deliver, and it reads as corny
  precisely because a reader can tell it was made to satisfy a slot rather than to explain
  something. If the figure is just prose in a box, it is worse than no figure.
- **Not charting what obviously wanted charting.** The reverse failure is quieter but just as
  common: a piece full of numbers over time, or a ranking, or a share-of-total, with no
  picture at all, leaving the reader to assemble a shape in their head from a paragraph of
  digits. If you find yourself declining while the profile holds three or more comparable
  magnitudes, look again.

Numbers, magnitudes, positions, shares and change over time are what pictures are FOR.
Sequences, definitions and mechanisms are what sentences are for. `warranted=false` is a
perfectly good answer and always available — but so is asking for the chart the piece is
crying out for. Judge each request on whether the reader ends up knowing something they
could not have got from the paragraph beside it.

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
- `image` — **labeled map** when geography is the aid (primary use), or a rare structural
  diagram. Prefer country-scale + local inset (see GEOGRAPHY). Never invent rates, borders,
  or place positions; never decoration; never a fake news photograph of a real event.

Reader clarity is part of usefulness. PUBLISHED fields:
- `title`: what is measured (plain words).
- `question`: **the caption the reader will actually read, printed verbatim under the figure.**
  So write it to the reader, describing what they are looking at — "Where the bone was found",
  "Florida's economy against the countries it is being compared to". NEVER describe the figure's
  purpose to us, and never mention the reader in it. Shipped failures to avoid: *"This map
  orients a reader to the Canadian location"*, *"Gives readers immediate geographic
  orientation"* — that is our rationale for building it, published as though it were a caption
  (style.md, machine signature 4). If the sentence contains "the reader", "orients", "helps the
  story" or "gives readers", it is the wrong sentence.
- `spec`: how to build it so a cold reader can read axes/units/labels without reverse-engineering.
  For maps: list countries (ISO or names) + named points to plot + any inset.
  A comparison is far more useful with the **full spectrum** than with an arbitrary handful: when
  the story is a ranking or a standing, show the whole field or an explicit top-N *and* bottom-N,
  and put the rank numbers on it when the rank is the point. Seven unexplained peers invites the
  question "why these seven?".

  **ENOUGH POINTS TO SHOW THE SHAPE.** Two numbers are not a trend, they are a pair — and we
  shipped "EU data-centre electricity use, 2024–2030" as exactly two bars, which tells a reader
  the endpoints and hides the thing they actually want, which is how fast it is bending. If the
  story is growth, decline or acceleration, ask for the **series**: several years of history
  before the present, and the projection after it, so the curve is visible and the reader can see
  whether the future line continues the past one or breaks from it. History is usually the
  cheapest part to source and the part that makes the figure worth having.

  **SAY WHAT IS BEING COUNTED, AND WHETHER IT HAPPENED.** A shipped chart carried the label
  "279 total DUV systems, 47% immersion" and a reader could not tell what a "DUV system" is,
  whether 279 was a year's shipments or a running total, or whether the two bars beside it were
  actual output, capacity or an announced target. Every figure must state, on the figure:
    - the **unit** in words a general reader holds ("lithography machines shipped per year");
    - the **status** of each number — actual, reported, estimated, or *target*. Never plot a
      target adjacent to an actual without labelling which is which; that is the difference
      between a comparison and a false equivalence;
    - that the compared quantities are **the same kind of thing**. If our side is
      immersion-only and theirs is all types, either compute the comparable subset or separate
      the two visibly. Comparing a subset to a total silently overstates the gap.

  **A TIMELINE MUST EARN ITS SPACE.** A shipped Swift timeline put a 2004 launch at one end and
  a cluster of 2026 events at the other, leaving two-thirds of the canvas empty and crushing
  every event that mattered into the right margin — where the labels then ran off the edge. If
  most of a time axis is empty, break or compress the quiet span and give the room to the period
  where things happen. And if the sequence tells the reader nothing they did not get from the
  prose, do not request it: dates are not a finding.

  **INSTANTLY LEGIBLE, NOT STUDIABLE.** A reader gives a figure about three seconds. In that time
  they must get the point without decoding it. So:
    - the `title` states the FINDING, not the measure — "Data-centre demand nearly doubles by
      2030", not "EU data-centre electricity use, 2024–2030";
    - label the lines and bars **directly** on the plot; a legend that has to be matched back to
      colours is a puzzle;
    - annotate the one number that carries the story right where it happens on the chart;
    - units and scale in words a non-specialist holds — say what a terawatt-hour is comparable to
      if the quantity is unfamiliar;
    - few series, no dual axes, no stacked everything. If the figure needs a paragraph of study,
      it has failed and a simpler cut of the same data is the fix.
- `data_refs` and/or `may_source` + `source_hint` as above.

Prefer zero, one, or two requests. Do not ship three.

**Pick the form the story actually needs — do not default to a map.** Geography earns a map only
when *where* is genuinely load-bearing and the map can show something a sentence cannot: a choke
point, a spread, a multi-site theatre. A single find at one location does not need one; a
country-outline map with one dot tells the reader nothing they did not get from the place name,
and we have published exactly that. Ask what the reader is missing — a quantity over time, a
comparison against the full field, a mechanism, a sequence of events, a composition — and build
*that*. If nothing genuinely aids comprehension, `warranted=false` is the right answer and always
available.

OUTPUT — AnalyticsPlan: warranted=false when nothing useful; otherwise the best request(s).
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
