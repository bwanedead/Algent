"""
The planning task message — the profile as the editorial planner should see it.

Two inputs: the deterministic **briefing** (the holistic, drillable view) and a compact
**id index** of every addressable item (claims, threads, sources, entities). The planner
must ground its frame, concepts, and must-use items in those exact ids, so the index makes
the reference targets explicit rather than leaving the planner to scrape them from prose.
"""

from __future__ import annotations

from algent_backend.agent_system.agents.research.briefing import render_briefing
from algent_backend.agent_system.agents.research.profile import SignalProfile

from .briefing import render_treatment
from .review_contracts import TreatmentReview
from .treatment import EditorialTreatment


def build_treatment_message(
    profile: SignalProfile,
    *,
    prior: EditorialTreatment | None = None,
    review: TreatmentReview | None = None,
) -> str:
    """The planning task. With a prior treatment + its review, this is a REVISION pass."""
    parts = [
        f"# PROFILE TO PLAN — {profile.id}  (status: {profile.profile_status})",
        "",
        "## Addressable item ids (ground your treatment in these)",
        *_id_index(profile),
        "",
        "## Briefing (the profile as a consumer reads it)",
        "",
        render_briefing(profile),
        "",
    ]
    if prior is not None and review is not None:
        parts += _revision_block(prior, review)
    else:
        parts.append(
            "TASK: Produce an EditorialTreatment for this profile. Choose the most "
            "reality-revealing frame (and record the rejected alternatives), design the "
            "concept-molecule the reader must build (load-bearing concepts, dependencies, "
            "grounding by id, do-not-overstate ceilings), map every serious perspective, and "
            "name this story's deception risks. Cite item ids throughout. Do NOT write prose."
        )
    return "\n".join(parts)


def _revision_block(prior: EditorialTreatment, review: TreatmentReview) -> list[str]:
    findings = [
        f"- [{f.severity}/{f.type}] {f.target}: {f.explanation}"
        + (f"  → {f.recommendation}" if f.recommendation else "")
        + ("  (PROMOTION BLOCKER)" if f.promotion_blocker else "")
        for f in review.findings
    ]
    better = [f"- A reviewer suggested a possibly-better frame: {review.better_frame}"] if review.better_frame else []
    return [
        "## YOU ARE REVISING — a prior treatment was reviewed and is NOT yet promoted",
        "",
        "### Your prior treatment",
        "",
        render_treatment(prior),
        "",
        f"### The reviewer's critique (verdict: {review.verdict})",
        review.summary,
        *better,
        *findings,
        "",
        "TASK: Produce an IMPROVED EditorialTreatment. Address every promotion-blocking "
        "finding, weigh the better-frame suggestion honestly (adopt it only if it genuinely "
        "reveals more — do not switch frames to appease), keep what was sound, and do not "
        "discard good grounded work. Re-ground in the item ids. Do NOT write prose.",
    ]


def _id_index(profile: SignalProfile) -> list[str]:
    def _line(label: str, items: list[str]) -> str:
        return f"- {label}: " + (", ".join(items) if items else "none")

    return [
        _line("claims", [f"{c.id} ({c.salience}/{c.grounding})" for c in profile.claim_ledger]),
        _line("threads", [f"{t.id} “{t.title}”" for t in profile.threads]),
        _line("sources", [f"{s.id} ({s.source_type})" for s in profile.source_ledger]),
        _line("entities", [f"{e.id} {e.name}" for e in profile.entities]),
    ]
