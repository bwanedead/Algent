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
    caveat: dict | None = None,
    comprehension: dict | None = None,
) -> str:
    """The drafting task. With a prior draft + its citation audit, this is a REVISION pass.

    With ``caveat`` (the v3b findings), it is the narrower HEDGING repair lap. With
    ``comprehension`` (gate C findings), it is the RAMP repair lap: add the flagged handholds /
    transitions or cut, and change nothing else.
    """
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
    if prior is not None and comprehension is not None:
        parts += _comprehension_block(prior, comprehension)
    elif prior is not None and caveat is not None:
        parts += _caveat_block(prior, caveat)
    elif prior is not None and report is not None:
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


def _comprehension_block(prior: ArticleDraft, comprehension: dict) -> list[str]:
    """The RAMP repair lap — a general reader stumbled in specific places. Surgical, not a rewrite.

    The constraint is hard and one-directional: ADD A HANDHOLD (plain ramp in your own voice,
    uncited), CONNECT an island, or CUT. No new contested claims, no strengthening, no pad.
    For missing_scene / assumed_context / vague_conflict, a handhold may be up to three short
    sentences so the cold reader can hold the dispute and who wants what — still not a full rewrite.
    announced_importance → cut the label sentence (do not rephrase into another signpost).
    """
    lines = [
        "## YOU ARE REPAIRING COMPREHENSION — a cold general reader stumbled in specific places",
        "",
        "Your prior draft is below. A reader who has NOT been following this story read it cold",
        "and could not follow it in the places listed. Repair EXACTLY those and nothing else.",
        "Your ONLY moves: add a plain handhold (your own voice, no citation — textbook foothold,",
        "not evidence; usually one clause; up to three short sentences if the stumble is",
        "missing_scene/assumed_context/vague_conflict on what the dispute *is* and who wants what),",
        "connect an island onto the through-line with a real relation, or CUT announced-importance",
        "labels and circular restatement ('That first fact matters because…', 'this sets the frame',",
        "'put plainly', 'phase change not closure').",
        "Do NOT add new contested claims, do NOT strengthen any assertion, do NOT pad, do NOT",
        "re-report, do NOT collapse the body. Every sentence not named below stays as written.",
        "",
        "### Where the reader stumbled",
    ]
    for f in (comprehension.get("findings") or []):
        fid = f.get("id", "")
        lines.append(f"- [{f.get('kind', 'other')} -> {f.get('fix', 'add_handhold')}] {fid}: {f.get('issue', '')}")
        if f.get("where"):
            lines.append(f'  at: "{f["where"]}"')
        if f.get("suggestion"):
            lines.append(f"  do: {f['suggestion']}")
    lines += [
        "",
        "### Your prior draft",
        f"TITLE: {prior.title}",
        f"STANDFIRST: {prior.standfirst}",
        "",
        prior.body,
        "",
        "TASK: Emit a DraftPayload — the same piece with the flagged handholds/connections added or",
        "the flagged passages cut. Carry the same cited ids. No new research.",
    ]
    return lines


def _caveat_block(prior: ArticleDraft, caveat: dict) -> list[str]:
    """The HEDGING REPAIR lap — surgical, not a rewrite.

    The caveat reviewer found specific sentences claiming more than their evidence supports. Its
    findings name the claim and the problem, so the fix is targeted: hedge exactly those, leave
    everything else alone. This is what makes 'needs_hedging' one more lap instead of a held piece.
    """
    lines = [
        "## YOU ARE REPAIRING HEDGING — a reviewer found sentences that outrun their evidence",
        "",
        "Your prior draft is below. A semantic review found the places where the prose asserts more",
        "than the cited evidence establishes (certainty laundering — see spirit.md). Fix EXACTLY",
        "those and nothing else: this is a surgical repair, not a rewrite. Do NOT re-report, do NOT",
        "re-frame, do NOT cut load-bearing content, and do NOT 'fix' it by deleting the claim — hedge",
        "it to the level the evidence actually supports, or state what is established and stop.",
        "Keep the title/standfirst unless a finding names them. Every other sentence stays as written.",
        "",
        "### What the reviewer flagged",
    ]
    for f in (caveat.get("findings") or []):
        fid = f.get("id") or f.get("claim_id") or ""
        lines.append(f"- [{f.get('kind', 'overstatement')}] {fid} — {f.get('explanation') or f.get('detail') or ''}")
        if f.get("quote"):
            lines.append(f'  offending text: "{f["quote"]}"')
    if caveat.get("note"):
        lines += ["", f"Reviewer note: {caveat['note']}"]
    lines += [
        "",
        "### Your prior draft",
        f"TITLE: {prior.title}",
        f"STANDFIRST: {prior.standfirst}",
        "",
        prior.body,
        "",
        "TASK: Emit a DraftPayload with the same piece, hedged where flagged. Carry the same cited",
        "ids. No new research is needed — this is a wording repair against evidence you already have.",
    ]
    return lines


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
