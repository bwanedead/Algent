"""Pick one chartable question from the standing beats. Search is the evidence, not decoration."""

from __future__ import annotations

from datetime import UTC, datetime

from langchain_core.messages import HumanMessage, SystemMessage

from algent_backend.agent_system.agents.insight.beats import render_beats
from algent_backend.agent_system.agents.insight.contracts import InsightSpec
from algent_backend.agent_system.foundation import cost
from algent_backend.agent_system.foundation.models import ModelSpec, house_spec
from algent_backend.agent_system.foundation.models.resolver import ModelResolver
from algent_backend.agent_system.prompting import UNIVERSAL_AGENT_BASE, compose_system_prompt

DEFAULT_MODEL: ModelSpec = house_spec(reasoning_effort="low", temperature=0.2)
COST_CAP_USD = 0.20

WARRANT_ROLE = """\
You are commissioning ONE public-data figure for a newsroom account. The figure IS the post.
A stranger on a phone must get the insight from the picture in two seconds.

STANDING BEATS (pick one; these are the only topics):
""" + render_beats() + """

FORMS (pick one):
- takeaway_bars — 3 to 8 labeled magnitudes, one of them highlighted. Best for scale/share.
- takeaway_line — one or two series over time, last point annotated.
- growing_line_gif — two or three competing series over time, revealed frame by frame.

THE TEST: would a graphics desk spend budget on this? If the insight is a sentence, drop it
(warranted=false). If the numbers are not in a public table you can name, drop it.

RULES:
- Search the web. Every row must come from that search. Never invent a series.
- Plot the table that exists, not a window that makes the takeaway look dramatic.
- takeaway is the chart TITLE and the tweet — a claim, not "X by year".
- source_name + source_url of the table you used. as_of is the data's date, not today.
- rows: for bars, objects with label + value. For line/gif, objects with the x_key field
  and one number per series name.
- unit is what the axis says (GW, $, %, TWh).
- highlight is the bar label the takeaway is about (bars only).
- Do not prefix with Radar or any lane label.

Drop (warranted=false) when the data is thin, unofficial, or the question is not one of the beats.
"""

SYSTEM_PROMPT = compose_system_prompt(UNIVERSAL_AGENT_BASE, WARRANT_ROLE)


def warrant(
    *,
    already: list[str] | None = None,
    today: str = "",
    model_spec: ModelSpec | None = None,
    resolver: ModelResolver | None = None,
) -> InsightSpec:
    """One spec, or warranted=false. Never raises."""
    from algent_backend.agent_system.foundation.models.budget_gate import gate_chat_model

    spec = model_spec or DEFAULT_MODEL
    day = today or datetime.now(UTC).strftime("%Y-%m-%d")
    seen = "\n".join(f"- {t}" for t in (already or [])[:12]) or "(none yet)"
    ask = (
        f"TODAY: {day}\n\nALREADY POSTED OR QUEUED (do not repeat):\n{seen}\n\n"
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
        return InsightSpec(beat="ai_power", warranted=False,
                           note=f"warrant failed: {str(exc)[:140]}")
    if not isinstance(result, InsightSpec):
        return InsightSpec(beat="ai_power", warranted=False, note="no structured result")
    return result
