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
                           snapshot=SourceSnapshot(content_hash="h", excerpt="e",
                                                   captured_at="2026-06-26T12:00:00Z")),   # read in full
            SourceArtifact(id="s2", url="https://reuters.com/y", title="Reuters poll", source_type="secondary"),  # no full text
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
        # "83%" appears in no cited claim -> a drifted figure the appendix must flag.
        body="Core PCE rose 3.4%. [clm_c1, src_s1] Odds sit at 83% now. [clm_c2] Bitcoin wobbled. [clm_c3]",
        cited_claim_ids=["c1", "c2", "c3"], cited_source_ids=["s1", "s2"],
    )


def test_published_view_cleans_prose_and_appends_receipts() -> None:
    md = render_published_article(_draft(), _profile())

    # Prose is clean (machine markers stripped), text preserved.
    assert "[clm_c1" not in md and "src_s1]" not in md
    assert "Core PCE rose 3.4%. Odds sit at 83% now. Bitcoin wobbled." in md

    # The appendix exists, with the frame disclosed.
    assert "How we know this" in md and "a market-pricing story" in md

    # Sources with honest access + as-of capture date.
    assert "BEA release" in md and "read in full · captured 2026-06-26" in md
    assert "Reuters poll" in md and "full text not obtained" in md   # neutral wording, no overclaim

    # Claims stamped with as-of on the deep-read one.
    assert "Core PCE rose 3.4%" in md and "as of 2026-06-26" in md
    assert "from a source summary" in md   # the snippet_only claim

    # Honest limits: no-full source (neutral), synthesis claim, AND the drifted figure.
    assert "Where we hit a limit" in md
    assert "did not obtain the full text" in md and "reuters.com" in md
    assert "our reading across the evidence" in md and "Bitcoin tracks Fed pricing" in md
    # honest framing — never asserts the figure is wrong, points the reader at the source
    assert "could not match to our stored evidence" in md and "83%" in md


def test_produced_analytics_are_embedded_and_receipted() -> None:
    analytics = [
        {"request_id": "anx_01", "status": "produced", "artifact_name": "analytic_anx_01.svg",
         "title": "Core PCE, Mar-May", "caption": "PCE climbed — AI-assisted analytic, built only from cited data.",
         "data_refs": ["c1"], "as_of": "2026-06-26", "figure_check": {"verified": True, "unverified": []}},
        {"request_id": "anx_02", "status": "failed", "artifact_name": ""},   # not embedded
    ]
    md = render_published_article(_draft(), _profile(), analytics)
    # the produced chart is embedded in the body with its AI-labelled caption; the failed one is not.
    assert "![Core PCE, Mar-May](analytic_anx_01.svg)" in md
    assert "AI-assisted analytic, built only from cited data" in md
    assert "anx_02" not in md
    # and it earns a receipts line carrying its claim provenance + as-of.
    assert "Charts & tables" in md and "from claims c1" in md and "as of 2026-06-26" in md


def test_table_analytic_is_inlined_not_image_embedded() -> None:
    # A markdown table must be inlined as text; an ![](x.md) image link would render broken.
    analytics = [{"request_id": "anx_t", "status": "produced", "artifact_name": "analytic_anx_t.md",
                  "title": "Odds table", "body_md": "| Outcome | P |\n|--|--|\n| Hold | 81% |",
                  "data_refs": ["c1"], "figure_check": {"verified": True, "unverified": []}}]
    md = render_published_article(_draft(), _profile(), analytics)
    assert "| Outcome | P |" in md and "| Hold | 81% |" in md   # the table itself is present
    assert "![" not in md.split("How we know this")[0]           # no image embed in the body
    assert "AI-assisted analytic, built only from cited data" in md   # honesty label still travels
    assert "Charts & tables" in md and "from claims c1" in md    # and it still earns a receipts line


def test_analytic_with_unverified_figures_is_flagged_in_receipts() -> None:
    analytics = [{"request_id": "anx_09", "status": "produced", "artifact_name": "a.svg",
                  "title": "drifty chart", "caption": "c", "data_refs": ["c1"],
                  "figure_check": {"verified": False, "unverified": ["9.9"]}}]
    md = render_published_article(_draft(), _profile(), analytics)
    assert "figures not all matched to the cited claims: 9.9" in md


def test_appendix_is_silent_when_everything_is_clean() -> None:
    prof = SignalProfile(id="p", title="t",
        source_ledger=[SourceArtifact(id="s1", url="u", title="src", source_type="primary",
                                      snapshot=SourceSnapshot(content_hash="h"))],
        claim_ledger=[Claim(id="c1", text="rose 3.4%", status="confirmed", grounding="snapshotted", supported_by=["s1"])])
    d = ArticleDraft(id="d", title="t", body="Inflation rose 3.4%. [clm_c1]",
                     cited_claim_ids=["c1"], cited_source_ids=["s1"])
    md = render_published_article(d, prof)
    assert "Where we hit a limit" not in md   # nothing to flag -> no alarm section
