"""
The treatment-review task message — the treatment AND its source profile, side by side.

The reviewer cannot judge a treatment in isolation: a missing branch or an overstatement is
only visible against the evidence the treatment was built from. So it gets the rendered
treatment (frame + molecule) plus the profile's briefing and item-id index — the same
grounding the planner had, so it can check the planner's work against reality.
"""

from __future__ import annotations

from algent_backend.agent_system.agents.research.briefing import render_briefing
from algent_backend.agent_system.agents.research.profile import SignalProfile

from .briefing import render_treatment
from .treatment import EditorialTreatment


def build_treatment_review_message(treatment: EditorialTreatment, profile: SignalProfile) -> str:
    return "\n".join([
        f"# TREATMENT UNDER REVIEW — {treatment.id}  (rev {treatment.revision})",
        "",
        "## The treatment (what the planner decided)",
        "",
        render_treatment(treatment),
        "",
        "## The source profile — judge the treatment against THIS evidence",
        "",
        "### Addressable item ids",
        *_id_index(profile),
        "",
        render_briefing(profile),
        "",
        "TASK: Review this treatment with fresh, independent eyes. Challenge the frame (is "
        "there a more reality-revealing one?), hunt for a missing load-bearing branch or a "
        "flattened perspective, check every concept against its grounding for certainty "
        "laundering, and watch for steering. Emit a TreatmentReview — targeted findings "
        "(cite frame/concept/perspective and item ids), a verdict, and a better_frame if one "
        "exists. Be specific to THIS treatment.",
    ])


def _id_index(profile: SignalProfile) -> list[str]:
    def _line(label: str, items: list[str]) -> str:
        return f"- {label}: " + (", ".join(items) if items else "none")

    return [
        _line("claims", [f"{c.id} ({c.salience}/{c.grounding})" for c in profile.claim_ledger]),
        _line("threads", [f"{t.id} “{t.title}”" for t in profile.threads]),
        _line("sources", [f"{s.id} ({s.source_type})" for s in profile.source_ledger]),
        _line("entities", [f"{e.id} {e.name}" for e in profile.entities]),
    ]
