"""Judge a drafted figure. Fix it if the picture can be saved; abandon only a bad question."""

from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage

from algent_backend.agent_system.agents.insight.contracts import Critique, InsightSpec
from algent_backend.agent_system.foundation import cost
from algent_backend.agent_system.foundation.models import ModelSpec, house_spec
from algent_backend.agent_system.foundation.models.resolver import ModelResolver
from algent_backend.agent_system.prompting import UNIVERSAL_AGENT_BASE, compose_system_prompt

DEFAULT_MODEL: ModelSpec = house_spec(reasoning_effort="low", temperature=0.0)
COST_CAP_USD = 0.08

CRITIQUE_ROLE = """\
You are checking one newsroom figure before it is posted. The picture has to work on a phone
in two seconds: takeaway in the title, one thing to look at, source on the image.

verdict:
- ship — the question is worth asking and the spec will read as a clear chart.
- fix — the question is good; change takeaway / highlight / form so a stranger gets it.
  Fill the fields you want changed. Keep the rows; do not invent new numbers.
- abandon — the question itself is thin, the rows look unsourced, or this is a sentence
  pretending to be a chart. Do not fix a bad premise.

Refuse dual-axis thinking, 12-slice pies, process diagrams, and titles like "X by year".
A takeaway sounds like "US debt service now exceeds the defense budget" — a claim, not a topic.
Abandon a bad picture or unsourced rows, not an unfamiliar but chartable topic.
"""

SYSTEM_PROMPT = compose_system_prompt(UNIVERSAL_AGENT_BASE, CRITIQUE_ROLE)


def mechanical_ok(spec: InsightSpec) -> str:
    """Empty string if the spec can be drawn; otherwise why not."""
    if not spec.warranted:
        return spec.note or "not warranted"
    if not spec.takeaway.strip():
        return "no takeaway"
    if not spec.rows or len(spec.rows) < 2:
        return "need at least two rows"
    if not (spec.source_url or "").strip().startswith("http"):
        return "source_url missing"
    if spec.form == "takeaway_bars":
        return _bars_ok(spec)
    if spec.form in ("takeaway_line", "growing_line_gif"):
        return _line_ok(spec)
    return ""


def _bars_ok(spec: InsightSpec) -> str:
    if len(spec.rows) > 8:
        return "too many bars"
    if any((r.value if r.value is not None else r.y) is None for r in spec.rows):
        return "bars need numeric values"
    return ""


def _line_ok(spec: InsightSpec) -> str:
    if not spec.series:
        return "line forms need series names"
    if len(spec.rows) < 3:
        return "a trajectory needs at least three points"
    return ""


def critique(
    spec: InsightSpec,
    *,
    model_spec: ModelSpec | None = None,
    resolver: ModelResolver | None = None,
) -> Critique:
    """Never raises. A failed call is abandon so we do not ship unreviewed."""
    from algent_backend.agent_system.foundation.models.budget_gate import gate_chat_model

    gate = mechanical_ok(spec)
    if gate:
        return Critique(verdict="abandon", reason=gate)
    try:
        client = (resolver or ModelResolver()).resolve(model_spec or DEFAULT_MODEL).client
        with cost.scoped(COST_CAP_USD, (model_spec or DEFAULT_MODEL).model):
            result = gate_chat_model(client).with_structured_output(Critique).invoke(
                [SystemMessage(content=SYSTEM_PROMPT),
                 HumanMessage(content=spec.model_dump_json())],
            )
    except Exception as exc:  # noqa: BLE001
        return Critique(verdict="abandon", reason=f"critique failed: {str(exc)[:140]}")
    if not isinstance(result, Critique):
        return Critique(verdict="abandon", reason="no structured critique")
    return result
