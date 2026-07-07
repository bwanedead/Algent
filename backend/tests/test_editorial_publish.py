"""Tests for the publish view — clean reader prose + the transparency appendix."""

from __future__ import annotations

from algent_backend.agent_system.agents.editorial.draft import ArticleDraft
from algent_backend.agent_system.agents.editorial.publish import render_published_article
from algent_backend.agent_system.agents.research.profile import (
    Claim,
    SignalProfile,
    SourceArtifact,
    SourceSnapshot,
)


def _profile() -> SignalProfile:
    return SignalProfile(
        id="p", title="t",
        source_ledger=[
            SourceArtifact(id="s1", url="https://bea.gov/x", title="BEA release", source_type="primary",
                           snapshot=SourceSnapshot(content_hash="h", excerpt="e")),   # read in full
            SourceArtifact(id="s2", url="https://reuters.com/y", title="Reuters poll", source_type="secondary"),  # walled
        ],
        claim_ledger=[
            Claim(id="c1", text="Core PCE rose 3.4%", status="confirmed", grounding="snapshotted", supported_by=["s1"]),
            Claim(id="c2", text="Markets price some hike risk", status="likely", grounding="snippet_only", supported_by=["s2"]),
            Claim(id="c3", text="Bitcoin tracks Fed pricing", status="speculative", grounding="unsourced"),
        ],
    )


def _draft() -> ArticleDraft:
    return ArticleDraft(
        id="d", title="Fed piece", standfirst="the dek", frame="a market-pricing story",
        body="Core PCE rose 3.4%. [clm_c1, src_s1] Markets price some hike risk. [clm_c2]",
        cited_claim_ids=["c1", "c2", "c3"], cited_source_ids=["s1", "s2"],
    )


def test_published_view_cleans_prose_and_appends_receipts() -> None:
    md = render_published_article(_draft(), _profile())

    # Prose is clean (machine markers stripped), text preserved.
    assert "[clm_c1" not in md and "src_s1]" not in md
    assert "Core PCE rose 3.4%. Markets price some hike risk." in md

    # The appendix exists, with the frame disclosed.
    assert "How we know this" in md
    assert "a market-pricing story" in md

    # Sources with honest access levels.
    assert "BEA release" in md and "read in full" in md
    assert "Reuters poll" in md and "summary only" in md

    # Claims with how-far-verified, in plain words.
    assert "Core PCE rose 3.4%" in md and "Markets price some hike risk" in md
    assert "from a source summary" in md   # the snippet_only claim

    # The honest limits section: the wall + the synthesis claim.
    assert "Where we hit a limit" in md
    assert "could not fully access" in md and "reuters.com" in md
    assert "our reading across the evidence" in md and "Bitcoin tracks Fed pricing" in md
