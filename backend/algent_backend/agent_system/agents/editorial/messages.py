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


def build_treatment_message(profile: SignalProfile) -> str:
    return "\n".join([
        f"# PROFILE TO PLAN — {profile.id}  (status: {profile.profile_status})",
        "",
        "## Addressable item ids (ground your treatment in these)",
        *_id_index(profile),
        "",
        "## Briefing (the profile as a consumer reads it)",
        "",
        render_briefing(profile),
        "",
        "TASK: Produce an EditorialTreatment for this profile. Choose the most "
        "reality-revealing frame (and record the rejected alternatives), design the "
        "concept-molecule the reader must build (load-bearing concepts, dependencies, "
        "grounding by id, do-not-overstate ceilings), map every serious perspective, and "
        "name this story's deception risks. Cite item ids throughout. Do NOT write prose.",
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
