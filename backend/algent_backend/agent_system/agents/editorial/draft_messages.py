"""
The drafting task message — the treatment to write from, and the profile to write from.

The drafter needs both: the treatment (the shape it must build and hold) and the profile (the
evidence, with addressable ids to cite and to research from). The rendered treatment carries
the frame, molecule, perspectives, ceilings, and must-use items; the profile briefing + id
index carry the evidence and the pointers the drafter will chase down for precision.
"""

from __future__ import annotations

from algent_backend.agent_system.agents.research.briefing import render_briefing
from algent_backend.agent_system.agents.research.profile import SignalProfile

from .briefing import render_treatment
from .treatment import EditorialTreatment


def build_draft_message(treatment: EditorialTreatment, profile: SignalProfile) -> str:
    return "\n".join([
        f"# WRITE THE PIECE — treatment {treatment.id} (rev {treatment.revision})",
        "",
        "## The treatment — your governing decisions (hold the frame; assemble this molecule)",
        "",
        render_treatment(treatment),
        "",
        "## The source profile — your evidence (cite these ids; chase the pointers for precision)",
        "",
        "### Addressable item ids",
        *_id_index(profile),
        "",
        render_briefing(profile),
        "",
        "TASK: Write the article from the treatment's frame, assembling its molecule in "
        "dependency order at the right resolution, carrying every must-use item and serious "
        "perspective, and respecting every do-not-overstate ceiling. Research for PRECISION "
        "(exact quotes, figures, details the profile only points at) and put everything new "
        "you find into `additions` so it enriches the profile. Cite the claim/source ids the "
        "prose rests on. Emit a DraftPayload.",
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
