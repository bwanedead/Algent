"""
The article-drafter loop — (treatment, profile) -> ArticleDraft, and an enriched profile.

The drafter is a researching react-agent (like signal_profile) whose output ALSO carries a
``ProfileAdditions`` block: what it turned up while chasing precision. The harness folds those
back through the SAME merge path the enrichers use, stamped ``stage="drafting"`` — so provenance
records that this evidence arrived after the framing, and nothing the drafter found is lost.

Two things the harness owns (not the model): the draft's id/lineage, and the tamper-evident
snapshots for sources the drafter actually read (captured during the loop, attached in the
merge by URL). Citations are validated against the ENRICHED profile — a cited id that does not
exist is dropped (deterministic grounding; the citation/accuracy check hardens in a later
stage). LangGraph/LangChain imports live here; spec.py stays rail-free.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any, TypedDict

from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph

from algent_backend.agent_system.agents.loop import build_react_loop, stream_react_loop
from algent_backend.agent_system.agents.research.assembly import merge_additions
from algent_backend.agent_system.agents.research.briefing import render_briefing
from algent_backend.agent_system.agents.research.profile import ProfileAdditions, SignalProfile
from algent_backend.agent_system.agents.research.store import JsonProfileStore
from algent_backend.agent_system.foundation import cost, snapshots
from algent_backend.agent_system.foundation.models import ModelSpec
from algent_backend.agent_system.runs import events as ev
from algent_backend.agent_system.runs.context import AgentRunContext
from algent_backend.agent_system.tools.sourcing.search import policy

from .citations import CitationReport, check_citations, render_citation_report
from .draft import ArticleDraft, DraftPayload
from .draft_messages import build_draft_message
from .draft_store import JsonDraftStore, render_draft
from .treatment import EditorialTreatment

ARTIFACT_JSON = "draft.json"
ARTIFACT_MD = "draft.md"
DRAFT_COMPLETED = "draft.completed"
DRAFT_NO_INPUT = "draft.no_input"
GENERATOR = "article_drafter@v1"
STAGE = "drafting"


class DraftState(TypedDict, total=False):
    treatment: dict[str, Any]        # the promoted treatment to write from (input)
    profile: dict[str, Any]          # its source profile — evidence + enrich-back target (input)
    prior_draft: dict[str, Any]      # a prior draft to revise (drafting-gauntlet revision pass)
    citation_report: dict[str, Any]  # the audit that revision must clear (worklist + missing)
    draft: dict[str, Any]            # the produced ArticleDraft
    # NOTE: `profile` is also the OUTPUT — the enriched (revision++) profile after drafting.


def build_draft_graph(
    context: AgentRunContext,
    *,
    model_spec: ModelSpec,
    tool_ids: tuple[str, ...],
    system_prompt: str,
    search_channels: tuple[str, ...],
    paid_budget: int,
    cost_cap_usd: float,
) -> Any:
    """Compile the drafting graph for an agent's model, tools, and gate."""
    model = context.model_resolver.resolve(model_spec).client
    tools = [context.tools[tool_id] for tool_id in tool_ids]
    agent = build_react_loop(model, tools, system_prompt=system_prompt, response_format=DraftPayload)

    def draft(state: DraftState, config: RunnableConfig) -> dict[str, Any]:
        tdict, pdict = state.get("treatment"), state.get("profile")
        if not tdict or not pdict:
            context.emit(DRAFT_NO_INPUT, {"message": "treatment or profile missing to the drafter"})
            return {"draft": ArticleDraft(id="draft_none", title="(no input)").model_dump(),
                    "profile": pdict or {}}

        treatment = EditorialTreatment.model_validate(tdict)
        profile = SignalProfile.model_validate(pdict)
        prior = ArticleDraft.model_validate(state["prior_draft"]) if state.get("prior_draft") else None
        report = CitationReport.model_validate(state["citation_report"]) if state.get("citation_report") else None
        context.emit(ev.INPUT_PREVIEW, _input_preview(treatment, profile, prior))

        with policy.scoped(search_channels, paid_budget), \
                cost.scoped(cost_cap_usd, model_spec.model), snapshots.scoped():
            produced = stream_react_loop(
                agent,
                {"messages": [HumanMessage(content=build_draft_message(treatment, profile, prior=prior, report=report))]},
                context=context, config=config,
            )
            captured = snapshots.collected()
        payload = produced if isinstance(produced, DraftPayload) else DraftPayload()

        # Enrich-back: fold the drafter's findings into the profile (stage="drafting"). Run the
        # merge if it added items OR merely re-read sources — a re-read of an existing snippet
        # source upgrades ITS grounding (the merge attaches captures to existing sources too),
        # which is how a revision round clears the citation floor.
        enriched = profile
        if _has_additions(payload.additions) or captured:
            enriched = merge_additions(profile, payload.additions, captured, generator=GENERATOR, stage=STAGE)
            try:
                JsonProfileStore().save(enriched)
            except Exception:  # noqa: BLE001
                pass

        draft_obj = _finalize_draft(payload, treatment, enriched, model_spec.model)
        # Deterministic citation/accuracy audit (the grounding floor) — stamp its verdict on
        # the draft so the drafting gauntlet can gate on it later.
        report = check_citations(draft_obj, treatment, enriched)
        draft_obj = draft_obj.model_copy(update={"grounding_verdict": report.verdict})
        return _finish(context, draft_obj, report, enriched, profile)

    graph = StateGraph(DraftState)
    graph.add_node("draft", draft)
    graph.add_edge(START, "draft")
    graph.add_edge("draft", END)
    return graph.compile()


def _draft_id(treatment_id: str) -> str:
    return "drf_" + hashlib.sha1(treatment_id.encode("utf-8")).hexdigest()[:10]


def _has_additions(a: ProfileAdditions) -> bool:
    return any((a.sources, a.claims, a.threads, a.entities, a.omissions, a.open_questions))


def _finalize_draft(
    payload: DraftPayload, treatment: EditorialTreatment, profile: SignalProfile, model: str,
) -> ArticleDraft:
    """Stamp id/lineage + validate citations against the (enriched) profile (drop dangling)."""
    valid_claims = {c.id for c in profile.claim_ledger}
    valid_sources = {s.id for s in profile.source_ledger}
    return ArticleDraft(
        id=_draft_id(treatment.id),
        treatment_id=treatment.id,
        profile_id=treatment.profile_id,
        profile_revision=profile.revision,
        frame=treatment.chosen_frame.frame,
        title=payload.title or treatment.title,
        standfirst=payload.standfirst,
        body=payload.body,
        cited_claim_ids=[c for c in dict.fromkeys(payload.cited_claim_ids) if c in valid_claims],
        cited_source_ids=[s for s in dict.fromkeys(payload.cited_source_ids) if s in valid_sources],
        research_note=payload.research_note,
        word_count=len(payload.body.split()),
        generator=GENERATOR,
        model=model,
        generated_at=datetime.now(UTC).isoformat(),
    )


def _finish(
    context: AgentRunContext, draft: ArticleDraft, report: CitationReport,
    enriched: SignalProfile, before: SignalProfile,
) -> dict[str, Any]:
    if draft.treatment_id:
        try:
            JsonDraftStore().save(draft)
        except Exception:  # noqa: BLE001
            pass
    link = None
    if context.artifacts is not None:
        context.artifacts.write_json(ARTIFACT_JSON, draft.model_dump())
        context.artifacts.write_text(ARTIFACT_MD, render_draft(draft))
        context.artifacts.write_json("citation_report.json", report.model_dump())
        context.artifacts.write_text("citation_report.md", render_citation_report(report))
        context.artifacts.write_json("profile.json", enriched.model_dump())
        context.artifacts.write_text("briefing.md", render_briefing(enriched))
        link = "../artifacts/" + ARTIFACT_MD
    context.emit(ev.OUTPUT_PREVIEW, _draft_preview(draft, enriched, before, link))
    context.emit(DRAFT_COMPLETED, {
        "draft_id": draft.id, "treatment_id": draft.treatment_id,
        "word_count": draft.word_count, "cited_claims": len(draft.cited_claim_ids),
        "grounding_verdict": report.verdict,
        "must_use_missing": len(report.must_use_missing),
        "weak_load_bearing": len(report.weak_load_bearing),
        "profile_revision": enriched.revision,
        "added_claims": len(enriched.claim_ledger) - len(before.claim_ledger),
        "added_sources": len(enriched.source_ledger) - len(before.source_ledger),
    })
    # Return the audit too, so the drafting gauntlet drives revision off the exact lists.
    return {"draft": draft.model_dump(), "profile": enriched.model_dump(),
            "citation_report": report.model_dump()}


def _input_preview(t: EditorialTreatment, p: SignalProfile, prior: ArticleDraft | None = None) -> dict[str, Any]:
    mode = f"revising (prior verdict: {prior.grounding_verdict})" if prior else "fresh draft"
    return {
        "title": f"input: treatment + profile to draft from ({mode})",
        "summary": f"treatment {t.id} (rev {t.revision}) · frame: {t.chosen_frame.frame[:70]}",
        "top": [f"profile {p.id} rev {p.revision}: {len(p.claim_ledger)} claims, {len(p.threads)} threads"],
        "link": None,
    }


def _draft_preview(
    draft: ArticleDraft, enriched: SignalProfile, before: SignalProfile, link: str | None,
) -> dict[str, Any]:
    added_c = len(enriched.claim_ledger) - len(before.claim_ledger)
    added_s = len(enriched.source_ledger) - len(before.source_ledger)
    return {
        "title": f"article draft — {draft.word_count} words",
        "summary": (
            f"“{draft.title}” | frame: {draft.frame[:60]} | cites {len(draft.cited_claim_ids)} claims | "
            f"enrich-back: +{added_c} claims, +{added_s} sources (profile rev {enriched.revision})"
        ),
        "items": ([draft.standfirst] if draft.standfirst else [])
                 + ([f"research: {draft.research_note[:90]}"] if draft.research_note else []),
        "link": link,
    }
