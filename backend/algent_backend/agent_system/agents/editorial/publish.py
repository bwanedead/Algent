"""
Publish view — the reader-facing article + a transparency appendix ("the receipts").

The raw draft carries inline `[clm_…]` machine-citation markers (for the deterministic audit).
A reader shouldn't see those. This renders the clean piece, then appends an honest, organized
appendix: what the article rests on, and — crucially — HOW FAR we could actually verify each
source and claim, and where we hit a wall. It is pure + deterministic (draft + profile ledgers
in, markdown out) — no model, no cost. The spirit: give the reader the resources to double-check
and, where a wall stopped us, to go look for themselves (they may not share our wall).
"""

from __future__ import annotations

import re

from algent_backend.agent_system.agents.research.profile import SignalProfile

from .draft import ArticleDraft

# Inline machine markers the drafter emits, e.g. "[clm_ab12, clm_cd34, src_ef56]".
_MARKER = re.compile(r"\s*\[(?:clm_|src_)[^\]]*\]")

_GROUNDING_WORDS = {
    "snapshotted": "read in full",
    "snippet_only": "from a source summary — we did not read the full source",
    "unsourced": "our synthesis across the evidence — no single cited source",
}


def _clean_prose(body: str) -> str:
    """Strip the machine-citation markers for the reader view (the appendix carries the trace)."""
    return re.sub(r" {2,}", " ", _MARKER.sub("", body)).strip()


def render_published_article(draft: ArticleDraft, profile: SignalProfile) -> str:
    claims = {c.id: c for c in profile.claim_ledger}
    sources = {s.id: s for s in profile.source_ledger}
    cited_claims = [claims[c] for c in draft.cited_claim_ids if c in claims]
    cited_src_ids = set(draft.cited_source_ids) | {s for c in cited_claims for s in c.supported_by}
    cited_sources = [sources[s] for s in cited_src_ids if s in sources]

    out = [f"# {draft.title or '(untitled)'}"]
    if draft.standfirst:
        out += [f"*{draft.standfirst}*"]
    out += ["", _clean_prose(draft.body), "", "---", *_appendix(draft, cited_sources, cited_claims)]
    return "\n".join(out).rstrip() + "\n"


def _appendix(draft: ArticleDraft, cited_sources: list, cited_claims: list) -> list[str]:
    out = [
        "## How we know this — sources & verification",
        "_Optional. The receipts: what the piece rests on and how far we could verify it. Where a "
        "wall stopped us we say so — you may be able to reach a source we could not._",
        "",
    ]
    if draft.frame:
        out += [f"**How this piece is framed:** {draft.frame}", ""]

    out.append("**Sources**")
    for s in sorted(cited_sources, key=lambda s: (s.snapshot is None, s.source_type)):
        access = "read in full" if s.snapshot else "summary only — we could not access the full text"
        out.append(f"- ({s.source_type}) {s.title or s.url} — {s.url}  ·  _{access}_")
    out.append("")

    out.append("**Claims, and how far we tracked each down**")
    for c in cited_claims:
        out.append(f"- _[{c.status}]_ {c.text}  ·  {_GROUNDING_WORDS.get(c.grounding, c.grounding)}")
    out.append("")

    walls = [s for s in cited_sources if s.snapshot is None]
    synth = [c for c in cited_claims if c.grounding == "unsourced"]
    if walls or synth:
        out.append("**Where we hit a limit**")
        for s in walls:
            out.append(
                f"- We could not fully access **{s.title or s.url}** ({s.url}); claims resting on it "
                "are taken from its summary — you may be able to reach it directly."
            )
        for c in synth:
            out.append(f"- \"{c.text}\" is our reading across the evidence, not a single sourced fact.")
        out.append("")
    return out
