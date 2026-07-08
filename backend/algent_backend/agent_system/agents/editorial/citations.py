"""
The citation / accuracy harness — a DETERMINISTIC check over a finished draft.

Doctrine can push the drafter to read deeply, but it cannot GUARANTEE a floor (the model
slips through sometimes — a load-bearing sentence left resting on a snippet). This harness is
the floor: pure code (no model, no cost, no variance) that inspects the draft against its
treatment + profile and reports the mechanically-checkable accuracy conditions:

- COVERAGE — did the piece carry every must-use item the treatment marked load-bearing?
  (a dropped must-use item is a missing branch — deception by omission, caught mechanically.)
- GROUNDING FLOOR — do the claims the piece leans on rest on DEEP-READ sources, or on thin
  snippets? (the exact gap deep-read doctrine can't fully close on its own.)
- OVERSTATEMENT RISK — which cited claims are hedged/contested, so their prose must be checked
  for certainty laundering. (the harness flags them; a reviewer LLM judges the actual wording.)

It shares the ONE grounding-floor definition with the research layer (``research/grounding.py``)
so a draft and a profile judge "deep-read" identically. The report is produced now; the
drafting gauntlet will use it as a promotion GATE (revise-until-grounded) once it exists.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field

from algent_backend.agent_system.agents.research.grounding import is_draft_citation_violation
from algent_backend.agent_system.agents.research.profile import Claim, SignalProfile

from .draft import ArticleDraft
from .treatment import EditorialTreatment

_PROSE_PCT = re.compile(r"\d+(?:\.\d+)?%")


def unverified_prose_figures(prose: str, cited_claims: list[Claim], sources_by_id: dict) -> list[str]:
    """Percentages in the prose that appear NOWHERE in the cited evidence — a cheap, deterministic
    catch for prose drifting off its own evidence (e.g. a live dashboard read at two moments giving
    83% vs 81%).

    The corpus is the cited claims' text PLUS the captured excerpt of those claims' OWN sources: a
    figure a deep-read source really carried is verified-at-capture, even if the ledger claim
    summarized the number out — that is "more specific than our summary", NOT drift. The corpus is
    restricted to the cited claims' sources (not the whole ledger) so a numbers-dense page can't
    coincidentally absolve a genuinely drifted figure.

    Deliberately conservative: percentages only (dollar amounts/counts fall to the semantic judge),
    and a plain substring test (so "8%" can hide inside "78%") — it errs toward MISSING a drift, not
    inventing one; do not "fix" that into a false-positive generator.
    """
    corpus = " ".join(c.text for c in cited_claims)
    for c in cited_claims:
        for sid in c.supported_by:
            s = sources_by_id.get(sid)
            if s and s.snapshot and s.snapshot.excerpt:
                corpus += " " + s.snapshot.excerpt
    return [f for f in dict.fromkeys(_PROSE_PCT.findall(prose)) if f not in corpus]

# The floor verdict, worst-first: dropping required evidence is worse than thin grounding.
CitationVerdict = Literal["drops_must_use", "needs_deep_read", "grounded"]


class CitationReport(BaseModel):
    """The deterministic accuracy audit of one draft."""

    draft_id: str = ""
    treatment_id: str = ""
    profile_id: str = ""
    verdict: CitationVerdict = "grounded"

    must_use_present: list[str] = Field(default_factory=list)
    must_use_missing: list[str] = Field(default_factory=list)  # load-bearing evidence the draft dropped

    cited_claims: int = 0
    grounding_tally: dict[str, int] = Field(default_factory=dict)  # snapshotted / snippet_only / unsourced
    weak_load_bearing: list[str] = Field(default_factory=list)     # cited consequential claims NOT deep-read
    deep_read_worklist: list[str] = Field(default_factory=list)    # SOURCE ids behind the weak claims (the reads to do)
    overstatement_flags: list[str] = Field(default_factory=list)   # cited non-confirmed claims (reviewer must check hedging)
    unverified_figures: list[str] = Field(default_factory=list)    # percentages in the prose not found in any cited claim

    def promotable(self) -> bool:
        """A draft clears the deterministic floor only when it carries its required evidence
        and leans on deep-read grounding."""
        return self.verdict == "grounded"


def check_citations(
    draft: ArticleDraft, treatment: EditorialTreatment, profile: SignalProfile
) -> CitationReport:
    """Audit a draft's citations against its treatment (coverage) and profile (grounding)."""
    claims_by_id = {c.id: c for c in profile.claim_ledger}
    thread_claims = {t.id: set(t.claims) for t in profile.threads}
    cited_claims = set(draft.cited_claim_ids)
    cited_any = cited_claims | set(draft.cited_source_ids)

    # The treatment's own declaration of what's load-bearing — a cross-check on salience, which
    # the profile-authoring model could otherwise sandbag to slip a thin claim under the floor.
    treatment_consequential = set(treatment.must_use_items)
    for concept in treatment.concepts:
        treatment_consequential.update(concept.grounds_in)

    # COVERAGE: a must-use id is carried if the draft cites it directly, or (for a must-use
    # thread) if the draft cites any of the claims that ground that thread.
    present, missing = [], []
    for m in treatment.must_use_items:
        covered = m in cited_any or bool(thread_claims.get(m, set()) & cited_claims)
        (present if covered else missing).append(m)

    # GROUNDING: tally the cited claims; flag floor violations (shared predicate); collect the
    # SOURCE ids behind the weak ones as the deep-read worklist (reads are per-source, not per-claim).
    tally = {"snapshotted": 0, "snippet_only": 0, "unsourced": 0}
    weak, overstate, worklist = [], [], []
    for cid in draft.cited_claim_ids:
        c = claims_by_id.get(cid)
        if c is None:
            continue
        tally[c.grounding] = tally.get(c.grounding, 0) + 1
        if is_draft_citation_violation(c, treatment_consequential=cid in treatment_consequential):
            weak.append(cid)
            worklist.extend(c.supported_by)   # the sources to actually read (snippet-sourced weak claims)
        if c.status != "confirmed":
            overstate.append(cid)

    cited_objs = [claims_by_id[cid] for cid in draft.cited_claim_ids if cid in claims_by_id]
    sources_by_id = {s.id: s for s in profile.source_ledger}
    prose = " ".join(x for x in (draft.title, draft.standfirst, draft.body) if x)  # all read prose
    verdict: CitationVerdict = (
        "drops_must_use" if missing else "needs_deep_read" if weak else "grounded"
    )
    return CitationReport(
        draft_id=draft.id, treatment_id=draft.treatment_id, profile_id=draft.profile_id,
        verdict=verdict,
        must_use_present=present, must_use_missing=missing,
        cited_claims=len(draft.cited_claim_ids), grounding_tally=tally,
        weak_load_bearing=weak, deep_read_worklist=list(dict.fromkeys(worklist)),
        overstatement_flags=overstate,
        unverified_figures=unverified_prose_figures(prose, cited_objs, sources_by_id),
    )


def render_citation_report(r: CitationReport) -> str:
    """A readable view of the audit."""
    out = [
        f"# Citation audit — {r.draft_id}  (verdict: {r.verdict})",
        f"- coverage: {len(r.must_use_present)} must-use present, {len(r.must_use_missing)} MISSING"
        + (f" -> {', '.join(r.must_use_missing)}" if r.must_use_missing else ""),
        f"- grounding of {r.cited_claims} cited claims: {r.grounding_tally}",
    ]
    if r.weak_load_bearing:
        out.append(f"- ⚠ consequential claims not deep-read: {', '.join(r.weak_load_bearing)}")
        if r.deep_read_worklist:
            out.append(f"  → deep-read these sources: {', '.join(r.deep_read_worklist)}")
    if r.overstatement_flags:
        out.append(f"- verify hedging on non-confirmed cited claims: {', '.join(r.overstatement_flags)}")
    return "\n".join(out) + "\n"
