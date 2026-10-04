"""What is worth charting today — before anyone looks up a table.

Discovery seeds are optional climate. This pass is allowed to go off-menu.
"""

from __future__ import annotations

from datetime import UTC, datetime

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, ConfigDict, Field

from algent_backend.agent_system.agents.insight.ambition import AMBITION
from algent_backend.agent_system.foundation import cost
from algent_backend.agent_system.foundation.models import ModelSpec, house_spec
from algent_backend.agent_system.foundation.models.resolver import ModelResolver
from algent_backend.agent_system.prompting import UNIVERSAL_AGENT_BASE, compose_system_prompt

DEFAULT_MODEL: ModelSpec = house_spec(reasoning_effort="medium", temperature=0.3)
COST_CAP_USD = 0.18
_CLOSED = ConfigDict(extra="forbid")

CONTEMPLATE_ROLE = """\
You pick ONE question worth a newsroom figure today. You do not draw it and you
do not fill a table — that is the next pass.

Search the open web for what is actually moving: decisions, builds, stocks,
rates, official prints, operator claims. Discovery seeds below are optional
weather, not the assignment.

Return a Brief: climate (two sentences on the present), one pick, up to two
runners-up. The pick must be a question a public table could answer. Prefer a
change, a split, or a competition over time. Prefer a question whose answer
would surprise a well-informed reader, including when that means leaving the
mainstream wire. Do not pick a question whose answer is the source's own figure.
"""

SYSTEM_PROMPT = compose_system_prompt(UNIVERSAL_AGENT_BASE, AMBITION, CONTEMPLATE_ROLE)


class Candidate(BaseModel):
    model_config = _CLOSED
    question: str = ""
    why_it_matters: str = ""
    table_hint: str = ""


class Brief(BaseModel):
    model_config = _CLOSED
    climate: str = ""
    pick: Candidate = Field(default_factory=Candidate)
    runners_up: list[Candidate] = Field(default_factory=list)


def render_brief(brief: Brief) -> str:
    """Human block for warrant. Empty string if contemplate found nothing."""
    pick = brief.pick
    if not (pick.question or "").strip():
        return ""
    lines = [
        f"CLIMATE: {brief.climate.strip()}" if brief.climate.strip() else "",
        f"PICK: {pick.question.strip()}",
    ]
    if pick.why_it_matters.strip():
        lines.append(f"WHY: {pick.why_it_matters.strip()}")
    if pick.table_hint.strip():
        lines.append(f"TABLE HINT: {pick.table_hint.strip()}")
    for alt in brief.runners_up[:2]:
        q = (alt.question or "").strip()
        if q:
            lines.append(f"ALSO: {q}")
    return "\n".join(p for p in lines if p)


def contemplate(
    *,
    already: list[str] | None = None,
    today: str = "",
    seeds: str = "",
    model_spec: ModelSpec | None = None,
    resolver: ModelResolver | None = None,
) -> Brief:
    """A question worth grounding. Never raises — empty pick means warrant is on its own."""
    from algent_backend.agent_system.foundation.models.budget_gate import gate_chat_model

    spec = model_spec or DEFAULT_MODEL
    day = today or datetime.now(UTC).strftime("%Y-%m-%d")
    seen = "\n".join(f"- {t}" for t in (already or [])[:12]) or "(none yet)"
    seed_block = seeds.strip() or "(no pool or menu on disk — search the open web)"
    ask = (
        f"TODAY: {day}\n\n"
        f"ALREADY POSTED OR QUEUED (do not repeat):\n{seen}\n\n"
        f"DISCOVERY SEEDS (optional climate, not a whitelist):\n{seed_block}\n\n"
        "Search, then return one Brief."
    )
    try:
        client = (resolver or ModelResolver()).resolve(spec).client
        model = gate_chat_model(client).bind_tools([{"type": "web_search"}])
        with cost.scoped(COST_CAP_USD, spec.model):
            result = model.with_structured_output(Brief).invoke(
                [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=ask)],
            )
    except Exception:  # noqa: BLE001 — a missed brief is an open warrant, not a crash
        return Brief()
    return result if isinstance(result, Brief) else Brief()
