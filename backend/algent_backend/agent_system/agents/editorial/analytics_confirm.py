"""
The confirmation lap over analytics-contributed claims.

Runs after a figure has folded its sourced data into the ledger. The MODEL judges; the HARNESS
enforces — an upgrade to ``confirmed`` without a URL to point at is refused here rather than
trusted, because "confirmed" is the one word in the ledger a reader is entitled to lean on.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig

from algent_backend.agent_system.agents.loop import build_react_loop, stream_react_loop
from algent_backend.agent_system.foundation import cost
from algent_backend.agent_system.foundation.models import ModelSpec, house_spec
from algent_backend.agent_system.runs.context import AgentRunContext
from algent_backend.agent_system.tools.sourcing.search import policy
from algent_backend.agent_system.tools.sourcing.search.research import WEB_SEARCH_TOOL_ID

from .analytics_confirm_contracts import AnalyticsConfirmReport, ClaimCheck
from .analytics_confirm_prompts import SYSTEM_PROMPT

GENERATOR = "analytics_confirm/1.0"
CLAIMS_CONFIRMED = "editorial_pipeline.analytics_claims_confirmed"

#: The stage marker _absorb_sourced_claims stamps on anything a figure contributed.
ANALYTICS_STAGE = "editorial.analytics"

TOOL_IDS = (WEB_SEARCH_TOOL_ID,)
#: Free channels plus READ. Deliberately no RICH/paid: this is a verification lap over a handful
#: of table rows, and an unverifiable row is an honest `unconfirmed`, not something worth buying.
SEARCH_CHANNELS = (policy.KEYWORD, policy.SEMANTIC, policy.READ)
PAID_BUDGET = 0
COST_CAP_USD = 0.25

DEFAULT_MODEL: ModelSpec = house_spec(reasoning_effort="low", temperature=0.1, streaming=True)


def analytics_claims(profile: dict[str, Any]) -> list[dict[str, Any]]:
    """Claims a figure contributed and nobody has checked yet."""
    out = []
    for claim in profile.get("claim_ledger") or []:
        if not isinstance(claim, dict):
            continue
        prov = claim.get("provenance") or {}
        stage = prov.get("added_by_stage") if isinstance(prov, dict) else None
        if stage == ANALYTICS_STAGE and claim.get("status") == "unconfirmed":
            out.append(claim)
    return out


def _message(claims: list[dict[str, Any]], sources: dict[str, str]) -> str:
    lines = [
        "# CONFIRM THESE ANALYTICS-CONTRIBUTED CLAIMS",
        "",
        "Each was fetched by the analytics worker while building a published figure. Verify each "
        "against a source YOU choose — not the one listed, which is recorded so you can avoid "
        "merely re-reading it.",
        "",
    ]
    for c in claims:
        cited = ", ".join(sources.get(s, s) for s in (c.get("supported_by") or [])) or "(none)"
        lines += [f"- id: {c.get('id')}", f"  claim: {c.get('text')}",
                  f"  worker cited: {cited}"]
    lines += ["", "Return an AnalyticsConfirmReport with one ClaimCheck per id above."]
    return "\n".join(lines)


def _apply(
    profile: dict[str, Any], report: AnalyticsConfirmReport,
) -> tuple[dict[str, Any], list[str]]:
    """Write verdicts back onto the ledger. Returns (profile, contested claim ids).

    A ``confirmed`` with no ``checked_against`` is DEMOTED rather than trusted. The model is
    asked for a URL and usually gives one; when it does not, the honest record is that nothing
    independent was seen — and silently accepting it would make the ledger's strongest word the
    one with the least behind it.
    """
    by_id: dict[str, ClaimCheck] = {c.claim_id: c for c in report.checks}
    claims, contested = [], []
    for claim in profile.get("claim_ledger") or []:
        check = by_id.get(str(claim.get("id"))) if isinstance(claim, dict) else None
        if check is None:
            claims.append(claim)
            continue
        verdict = check.verdict
        if verdict == "confirmed" and not check.checked_against:
            verdict = "unconfirmed"
        note = (check.reason or "").strip()
        if check.source_value:
            note = f"{note} (independent source: {check.source_value})".strip()
        if verdict == "contested":
            contested.append(str(claim.get("id")))
        claims.append({**claim, "status": verdict,
                       "note": note or str(claim.get("note") or "")})
    return {**profile, "claim_ledger": claims}, contested


def confirm_analytics_claims(
    context: AgentRunContext,
    config: RunnableConfig,
    profile: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Verify anything analytics contributed. Returns (profile, report dict or None)."""
    pending = analytics_claims(profile)
    if not pending:
        return profile, None

    sources = {str(s.get("id")): str(s.get("url") or "")
               for s in (profile.get("source_ledger") or []) if isinstance(s, dict)}

    model = context.model_resolver.resolve(DEFAULT_MODEL).client
    tools = [context.tools[t] for t in TOOL_IDS]
    agent = build_react_loop(
        model, tools, system_prompt=SYSTEM_PROMPT, response_format=AnalyticsConfirmReport)

    with policy.scoped(SEARCH_CHANNELS, PAID_BUDGET), \
            cost.scoped(COST_CAP_USD, DEFAULT_MODEL.model):
        produced = stream_react_loop(
            agent,
            {"messages": [HumanMessage(content=_message(pending, sources))]},
            context=context,
            config=config,
        )

    if not isinstance(produced, AnalyticsConfirmReport):
        # No structured verdict is not a reason to upgrade anything: the claims stay
        # `unconfirmed`, which is what they already are and what they honestly remain.
        return profile, None

    produced.profile_id = str(profile.get("id") or "")
    produced.generated_at = datetime.now(UTC).isoformat()
    produced.generator = GENERATOR
    produced.model = DEFAULT_MODEL.model
    # Only rule on what we asked about — a check for an id outside the pending set is discarded
    # rather than allowed to rewrite a research-graded claim.
    pending_ids = {str(c.get("id")) for c in pending}
    produced.checks = [c for c in produced.checks if c.claim_id in pending_ids]

    profile, contested = _apply(profile, produced)
    context.emit(CLAIMS_CONFIRMED, {**produced.counts(), "contested_ids": contested})
    if context.artifacts is not None:
        context.artifacts.write_json("analytics_confirm_report.json", produced.model_dump())
    return profile, produced.model_dump()
