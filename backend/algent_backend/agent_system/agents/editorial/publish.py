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

from .analytics_contracts import AI_ANALYTIC_LABEL
from .citations import unverified_prose_figures
from .draft import ArticleDraft

_IMAGE_SUFFIXES = (".svg", ".png")
_TABLE_ROW = re.compile(r"^\s*\|.*\|\s*$")


def _table_block(body_md: str) -> str:
    """The contiguous markdown table in ``body_md`` (its ``|…|`` rows), plus one heading/label line
    directly above it if present — and NOTHING else.

    The worker's markdown is grok-authored: any free-text it wraps around the table (a 'Source:'
    line, a 'hawkish momentum builds' aside) would otherwise reach the reader without passing the
    caveat gate the draft prose passes through. Bounding the inline to the table itself removes that
    vector deterministically; the residual — the cell wording — is largely pinned by the figure
    check and the receipts line. Prose-only analytics (an ``insight`` with no table) inline nothing
    here: ungated prose must not reach the reader (its provenance still shows in the receipts)."""
    lines = body_md.splitlines()
    start = end = None
    for i, ln in enumerate(lines):
        if _TABLE_ROW.match(ln):
            if start is None:
                start = i
            end = i
        elif start is not None:
            break                                  # first contiguous table run only
    if start is None:
        return ""
    head = start
    if start > 0 and lines[start - 1].strip() and not _TABLE_ROW.match(lines[start - 1]):
        head = start - 1                           # one adjacent heading/label line, if any
    return "\n".join(lines[head:end + 1]).strip()

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


def _capture_date(source) -> str:
    """The date a source was captured (YYYY-MM-DD), for as-of anchoring on volatile sources."""
    ca = (source.snapshot.captured_at if source.snapshot else "") or ""
    return ca[:10]


def _claim_asof(claim, sources: dict) -> str:
    """The capture date behind a deep-read claim (for fast-moving figures)."""
    for sid in claim.supported_by:
        s = sources.get(sid)
        if s and s.snapshot and s.snapshot.captured_at:
            return s.snapshot.captured_at[:10]
    return ""


def render_published_article(
    draft: ArticleDraft, profile: SignalProfile, analytics: list[dict] | None = None
) -> str:
    claims = {c.id: c for c in profile.claim_ledger}
    sources = {s.id: s for s in profile.source_ledger}
    cited_claims = [claims[c] for c in draft.cited_claim_ids if c in claims]
    cited_src_ids = set(draft.cited_source_ids) | {s for c in cited_claims for s in c.supported_by}
    cited_sources = [sources[s] for s in cited_src_ids if s in sources]
    produced = [a for a in (analytics or [])
                if a.get("status") == "produced" and (a.get("artifact_name") or a.get("body_md"))]

    out = [f"# {draft.title or '(untitled)'}"]
    if draft.standfirst:
        out += [f"*{draft.standfirst}*"]
    out += ["", _clean_prose(draft.body), ""]
    out += _figures(produced)                       # the produced charts, each with its AI label
    out += ["---", *_appendix(draft, cited_sources, cited_claims, sources, produced)]
    return "\n".join(out).rstrip() + "\n"


def _figures(produced: list[dict]) -> list[str]:
    """Place each produced analytic in the reader view by TYPE:

    - a chart/illustration (``.svg``/``.png``) is embedded as an image, with the harness caption
      (which carries the 'AI-assisted, built only from cited data' label) beneath it;
    - a table/insight (markdown) is INLINED as text — an image link to a ``.md`` file would render
      as a broken image — followed by the honesty label so the provenance travels with it either way.
    """
    out: list[str] = []
    for a in produced:
        name = a.get("artifact_name", "")
        if name.endswith(_IMAGE_SUFFIXES):
            alt = a.get("title") or "analytic"
            out += [f"![{alt}]({name})", "", f"*{a.get('caption', '').strip()}*", ""]
        elif a.get("body_md"):
            table = _table_block(a["body_md"])     # bounded to the table — no ungated free-text
            if table:
                out += [table, "", f"*{AI_ANALYTIC_LABEL}.*", ""]
    return out


def _appendix(draft: ArticleDraft, cited_sources: list, cited_claims: list, sources: dict,
              produced: list[dict] | None = None) -> list[str]:
    out = [
        "## How we know this — sources & verification",
        "_Optional. The receipts: what the piece rests on, when we captured it, and how far we could "
        "verify each part — so you can judge for yourself, and perhaps reach a source we did not._",
        "",
    ]
    if draft.frame:
        out += [f"**How this piece is framed:** {draft.frame}", ""]

    if produced:
        out.append("**Charts & tables** — _each built only from the cited claims below, by an AI tool_")
        for a in produced:
            refs = ", ".join(a.get("data_refs", []))
            asof = f" · as of {a['as_of']}" if a.get("as_of") else ""
            fc = a.get("figure_check") or {}
            check = ("" if fc.get("verified") else
                     f" · ⚠ figures not all matched to the cited claims: {', '.join(fc.get('unverified', []))}")
            out.append(f"- {a.get('title') or 'analytic'} — from claims {refs}{asof}{check}")
        out.append("")

    out.append("**Sources**")
    for s in sorted(cited_sources, key=lambda s: (s.snapshot is None, s.source_type)):
        if s.snapshot:
            d = _capture_date(s)
            access = "read in full" + (f" · captured {d}" if d else "")
        else:
            access = "full text not obtained — used its summary"
        out.append(f"- ({s.source_type}) {s.title or s.url} — {s.url}  ·  _{access}_")
    out.append("")

    out.append("**Claims, and how far we tracked each down**")
    for c in cited_claims:
        asof = _claim_asof(c, sources) if c.grounding == "snapshotted" else ""
        stamp = f" (as of {asof})" if asof else ""
        out.append(f"- _[{c.status}]_ {c.text}  ·  {_GROUNDING_WORDS.get(c.grounding, c.grounding)}{stamp}")
    out.append("")

    out += _limits(draft, cited_sources, cited_claims, sources)
    return out


def _limits(draft: ArticleDraft, cited_sources: list, cited_claims: list, sources: dict) -> list[str]:
    """The honest limits: sources we didn't get in full, our-synthesis claims, and any figures
    that don't appear in the cited evidence — what to double-check."""
    no_full = [s for s in cited_sources if s.snapshot is None]
    synth = [c for c in cited_claims if c.grounding == "unsourced"]
    prose = " ".join(x for x in (draft.title, draft.standfirst, draft.body) if x)
    figures = unverified_prose_figures(prose, cited_claims, sources)
    if not (no_full or synth or figures):
        return []
    out = ["**Where we hit a limit / what to double-check**"]
    for s in no_full:
        # Neutral: snapshot-less can mean "walled" OR "not pursued" — do not claim effort we may
        # not have spent. Say what is true: we did not obtain the full text.
        out.append(
            f"- We did not obtain the full text of **{s.title or s.url}** ({s.url}); claims resting "
            "on it are from its summary — you may be able to reach it directly."
        )
    for c in synth:
        out.append(f"- \"{c.text}\" is our reading across the evidence, not a single sourced fact.")
    if figures:
        # Honest about the two possibilities: a source we read may state the figure exactly (worth
        # confirming there), OR a live source moved since. Never asserts the figure is wrong.
        out.append(
            f"- Figures we could not match to our stored evidence — worth confirming against the "
            f"source (which may state them exactly), and note live sources move: {', '.join(figures)}."
        )
    out.append("")
    return out
