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
from .citations import CitationReport
from .draft import ArticleDraft
from .treatment import EditorialTreatment


def build_draft_message(
    treatment: EditorialTreatment,
    profile: SignalProfile,
    *,
    prior: ArticleDraft | None = None,
    report: CitationReport | None = None,
) -> str:
    """The drafting task. With a prior draft + its citation audit, this is a REVISION pass."""
    parts = [
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
    ]
    if prior is not None and report is not None:
        parts += _revision_block(prior, report, profile)
    else:
        parts.append(
            "TASK: Write the article from the treatment's frame, assembling its molecule in "
            "dependency order at the right resolution, carrying every must-use item and serious "
            "perspective, and respecting every do-not-overstate ceiling. Research for PRECISION "
            "(exact quotes, figures, details the profile only points at) and put everything new "
            "you find into `additions` so it enriches the profile. Cite the claim/source ids the "
            "prose rests on. Emit a DraftPayload."
        )
    return "\n".join(parts)


def _revision_block(prior: ArticleDraft, report: CitationReport, profile: SignalProfile) -> list[str]:
    url_of = {s.id: (s.url or s.title or s.id) for s in profile.source_ledger}
    lines = ["## YOU ARE REVISING — a deterministic audit found your prior draft not yet grounded",
             "", "### Your prior draft", "", prior.body.strip(), ""]
    if report.deep_read_worklist:
        reads = "; ".join(f"{sid} ({url_of.get(sid, sid)})" for sid in report.deep_read_worklist)
        lines += [
            f"**DEEP-READ these {len(report.deep_read_worklist)} source(s), then revise the sentences that "
            f"rest on them** — the prose is leaning on snippets, not full reads:",
            f"  {reads}",
            f"  (these ground the under-read claims: {', '.join(report.weak_load_bearing)})",
        ]
    if report.must_use_missing:
        lines.append(f"**CARRY the dropped must-use evidence** the piece omitted: {', '.join(report.must_use_missing)}")
    lines += [
        "",
        "TASK: Revise the piece. `read_url` each source above IN FULL (reads are free), record what "
        "you read into `additions.sources`, and rewrite the affected sentences from the real source. "
        "Carry any dropped must-use items. Keep the frame, molecule, and everything already sound. "
        "Re-cite the claim/source ids. Emit a DraftPayload.",
    ]
    return lines


def _id_index(profile: SignalProfile) -> list[str]:
    def _line(label: str, items: list[str]) -> str:
        return f"- {label}: " + (", ".join(items) if items else "none")

    return [
        _line("claims", [f"{c.id} ({c.salience}/{c.grounding})" for c in profile.claim_ledger]),
        _line("threads", [f"{t.id} “{t.title}”" for t in profile.threads]),
        _line("sources", [f"{s.id} ({s.source_type})" for s in profile.source_ledger]),
        _line("entities", [f"{e.id} {e.name}" for e in profile.entities]),
    ]
