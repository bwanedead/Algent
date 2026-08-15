"""Ground one contemplated question in a public table that measures reality."""

from __future__ import annotations

from datetime import UTC, datetime

from langchain_core.messages import HumanMessage, SystemMessage

from algent_backend.agent_system.agents.insight.ambition import AMBITION
from algent_backend.agent_system.agents.insight.beats import render_beats
from algent_backend.agent_system.agents.insight.contracts import InsightSpec
from algent_backend.agent_system.foundation import cost
from algent_backend.agent_system.foundation.models import ModelSpec, house_spec
from algent_backend.agent_system.foundation.models.resolver import ModelResolver
from algent_backend.agent_system.prompting import UNIVERSAL_AGENT_BASE, compose_system_prompt

DEFAULT_MODEL: ModelSpec = house_spec(reasoning_effort="low", temperature=0.2)
COST_CAP_USD = 0.22

WARRANT_ROLE = """\
Ground ONE public-data figure from the contemplated question. The figure IS the post.
A stranger on a phone must get the insight from the picture in two seconds.

If that table does not exist, take a runner-up, then the open web.

Standing lenses are a TIE-BREAK when two tables are equally public, not a ranking:
""" + render_beats() + """

A short beat slug names the domain. Outside the list is normal.

FORMS (pick the one the question needs — not the same one every day):
- takeaway_slope — then/now or A/B per row (y and y2). The usual interesting snapshot.
- takeaway_line — one or two series over time, last point annotated.
- growing_line_gif — two or three competing series over time, revealed frame by frame.
  Use motion when motion is why a stranger stops, not whenever a series exists.
- takeaway_bars — last resort: ranking or scale when the table has no change,
  split, or race. A ranked list of sizes is a table, not a figure.

RULES:
- Search the web. Never invent a series.
- Plot the table that exists, not a window that makes the takeaway look dramatic.
- takeaway is the chart TITLE and the tweet — a claim, not "X by year".
- source_name + source_url of the table you used. as_of is the data's date, not today.
- rows: slope uses label + y + y2 (series[0] / series[1] name the two ends).
  Lines/gifs use x plus y / y2 / y3 matching series. Bars use label + value.
  Do not invent extra keys.
- unit is what the axis says (GW, $, %, TWh).
- highlight is the row the takeaway is about.
- Do not prefix with Radar or any lane label.

Drop (warranted=false) when the data is thin or unofficial, or the takeaway is the
source's own headline as the picture — not because the topic is unfamiliar or uncomfortable.
"""

SYSTEM_PROMPT = compose_system_prompt(UNIVERSAL_AGENT_BASE, AMBITION, WARRANT_ROLE)


def warrant(
    *,
    already: list[str] | None = None,
    today: str = "",
    seeds: str = "",
    brief: str = "",
    model_spec: ModelSpec | None = None,
    resolver: ModelResolver | None = None,
) -> InsightSpec:
    """One spec, or warranted=false. Never raises."""
    from algent_backend.agent_system.foundation.models.budget_gate import gate_chat_model

    spec = model_spec or DEFAULT_MODEL
    day = today or datetime.now(UTC).strftime("%Y-%m-%d")
    seen = "\n".join(f"- {t}" for t in (already or [])[:12]) or "(none yet)"
    seed_block = seeds.strip() or "(no pool or menu on disk)"
    brief_block = brief.strip() or "(no contemplate pick — search the open web for a question that earns a figure)"
    ask = (
        f"TODAY: {day}\n\n"
        f"ALREADY POSTED OR QUEUED (do not repeat):\n{seen}\n\n"
        f"CONTEMPLATED QUESTION:\n{brief_block}\n\n"
        f"DISCOVERY SEEDS (optional climate, not a whitelist):\n{seed_block}\n\n"
        "Search, then return one InsightSpec."
    )
    try:
        client = (resolver or ModelResolver()).resolve(spec).client
        model = gate_chat_model(client).bind_tools([{"type": "web_search"}])
        with cost.scoped(COST_CAP_USD, spec.model):
            result = model.with_structured_output(InsightSpec).invoke(
                [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=ask)],
            )
    except Exception as exc:  # noqa: BLE001 — a failed warrant is a skipped cycle
        return InsightSpec(beat="world", warranted=False,
                           note=f"warrant failed: {str(exc)[:140]}")
    if not isinstance(result, InsightSpec):
        return InsightSpec(beat="world", warranted=False, note="no structured result")
    return result
