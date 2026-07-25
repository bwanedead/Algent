"""Tests for the publish view — clean reader prose + the transparency appendix."""

from __future__ import annotations

from algent_backend.agent_system.agents.editorial.analytics_contracts import AI_ANALYTIC_LABEL
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
         "title": "Core PCE, Mar-May",
         "question": "How did core PCE change from March to May?",
         "caption": "How did core PCE change from March to May? PCE climbed. — AI-assisted analytic, built only from cited data. Source: BLS. As of 2026-06-26.",
         "data_refs": ["c1"], "as_of": "2026-06-26", "figure_check": {"verified": True, "unverified": []}},
        {"request_id": "anx_02", "status": "failed", "artifact_name": ""},   # not embedded
    ]
    md = render_published_article(_draft(), _profile(), analytics)
    # the produced chart is embedded in the body with its AI-labelled caption; the failed one is not.
    assert "![Core PCE, Mar-May](analytic_anx_01.svg)" in md
    assert "**Core PCE, Mar-May**" in md  # labelled figure heading
    assert "How did core PCE change" in md  # cold-reader explainer under the chart
    assert "AI-assisted analytic, built only from cited data" in md
    assert "anx_02" not in md
    # and it earns a receipts line carrying its claim provenance + as-of.
    assert "Charts & tables" in md and "from claims c1" in md and "as of 2026-06-26" in md


def test_clean_prose_strips_backtick_and_bare_markers() -> None:
    # the drafter's marker format varies run to run; the reader view must strip every form.
    from algent_backend.agent_system.agents.editorial.publish import _clean_prose
    out = _clean_prose("CENTCOM said it would act. `clm_0fd2078` `src_1a68d97` The fee was dropped. clm_abc123")
    assert "clm_" not in out and "src_" not in out and "`" not in out
    assert out == "CENTCOM said it would act. The fee was dropped."


def test_clean_prose_strips_markdown_link_citation_form() -> None:
    # 2026-07 Wangchuk draft: markers as `` [`[clm_hex](#)`, `[`[ent_…](#)` ``
    from algent_backend.agent_system.agents.editorial.publish import _clean_prose
    raw = (
        "Education Minister Dharmendra Pradhan. "
        "`[`[clm_9747f4f642](#)`, `[`[clm_c8240631d4](#)`, `[`[ent_1e9b5b6bf5](#)`\n\n"
        "That first fact matters."
    )
    out = _clean_prose(raw)
    assert "clm_" not in out and "ent_" not in out and "(#)" not in out
    assert "`" not in out and "[`" not in out
    assert ",," not in out
    assert "Pradhan." in out and "That first fact matters." in out
    assert out.startswith("Education Minister Dharmendra Pradhan.")


def test_table_analytic_is_inlined_not_image_embedded() -> None:
    # A markdown table must be inlined as text; an ![](x.md) image link would render broken.
    analytics = [{"request_id": "anx_t", "status": "produced", "artifact_name": "analytic_anx_t.md",
                  "title": "Odds table", "body_md": "| Outcome | P |\n|--|--|\n| Hold | 81% |",
                  "data_refs": ["c1"], "figure_check": {"verified": True, "unverified": []}}]
    md = render_published_article(_draft(), _profile(), analytics)
    assert "| Outcome | P |" in md and "| Hold | 81% |" in md   # the table itself is present
    assert "![" not in md.split("How we know this")[0]           # no image embed in the body
    # The honesty label still travels. Asserted against the constant, not a copy of its
    # wording: this test held a hand-typed version and silently went red when the label
    # was reworded, which reads for months like the disclosure had been dropped.
    assert AI_ANALYTIC_LABEL in md
    assert "Charts & tables" in md and "from claims c1" in md    # and it still earns a receipts line


def test_analytic_renders_as_a_labelled_figure_not_a_naked_table() -> None:
    # A table dropped in with no label is a puzzle: a real run shipped a bare "Score | Meaning"
    # grid with nothing saying what it was. Every figure now carries a heading and an explainer,
    # both from harness/router-controlled fields (title, question) — no new ungated text.
    analytics = [{"request_id": "a1", "status": "produced", "artifact_name": "a.md",
                  "title": "Transits vs normal", "question": "How much traffic is still moving?",
                  "body_md": "| Day | Transits |\n|--|--|\n| Mon | 9 |",
                  "data_refs": ["c1"], "figure_check": {"verified": True, "unverified": []}}]
    md = render_published_article(_draft(), _profile(), analytics)
    body = md.split("How we know this")[0]
    assert "**Transits vs normal**" in body                      # you know what it is
    assert "How much traffic is still moving?" in body           # and what it shows
    assert "| Mon | 9 |" in body                                 # the data itself
    assert body.index("**Transits vs normal**") < body.index("| Day | Transits |")   # label first


def test_inlined_table_strips_ungated_free_text() -> None:
    # grok-authored commentary around the table must NOT reach the reader ungated; only the table
    # (and its numbers, which the figure-check pins) is inlined.
    body = ("# Odds\n\n**Source:** made-up dashboard\n\nHawkish momentum is clearly building.\n\n"
            "| Outcome | P |\n|--|--|\n| Hold | 81% |\n\n**Note:** my spicy editorial take here.")
    analytics = [{"request_id": "anx_t", "status": "produced", "artifact_name": "analytic_anx_t.md",
                  "title": "Odds", "body_md": body, "data_refs": ["c1"],
                  "figure_check": {"verified": True, "unverified": []}}]
    md = render_published_article(_draft(), _profile(), analytics)
    body_region = md.split("How we know this")[0]
    assert "| Hold | 81% |" in body_region                    # the table survives
    assert "Hawkish momentum" not in md and "spicy editorial" not in md   # the free-text does not
    assert "made-up dashboard" not in md


def test_prose_only_analytic_inlines_nothing_but_still_receipts() -> None:
    # An insight with no table = ungated prose -> not inlined, but its provenance still shows.
    analytics = [{"request_id": "anx_i", "status": "produced", "artifact_name": "analytic_anx_i.md",
                  "title": "A computed insight", "body_md": "PCE climbed 0.4pp over three months.",
                  "data_refs": ["c1"], "figure_check": {"verified": True, "unverified": []}}]
    md = render_published_article(_draft(), _profile(), analytics)
    assert "PCE climbed 0.4pp" not in md.split("How we know this")[0]   # prose body not inlined
    assert "Charts & tables" in md and "A computed insight" in md       # receipts still carry it


def test_analytic_with_unverified_figures_is_flagged_in_receipts() -> None:
    analytics = [{"request_id": "anx_09", "status": "produced", "artifact_name": "a.svg",
                  "title": "drifty chart", "caption": "c", "data_refs": ["c1"],
                  "figure_check": {"verified": False, "unverified": ["9.9"]}}]
    md = render_published_article(_draft(), _profile(), analytics)
    assert "figures not all matched to the cited claims: 9.9" in md


def test_x_status_url_injected_for_embed_when_handle_named_without_link() -> None:
    from algent_backend.agent_system.agents.editorial.publish import render_published_article

    prof = SignalProfile(
        id="p", title="t",
        source_ledger=[
            SourceArtifact(
                id="sx",
                url="https://x.com/Osinttechnical/status/2080427489298391112",
                title="Post by @Osinttechnical",
                source_type="secondary",
            ),
            SourceArtifact(id="s1", url="https://reuters.com/a", title="Wire", source_type="secondary",
                           snapshot=SourceSnapshot(content_hash="h")),
        ],
        claim_ledger=[
            Claim(id="c1", text="A post showed fire", status="confirmed", grounding="snippet_only",
                  supported_by=["sx"]),
        ],
    )
    draft = ArticleDraft(
        id="d", title="Strike", standfirst="dek",
        body="An X post by the open-source account Osinttechnical showed a fire at the warehouse.",
        cited_claim_ids=["c1"], cited_source_ids=["sx"],
    )
    md = render_published_article(draft, prof)
    body = md.split("How we know this")[0]
    assert "https://x.com/Osinttechnical/status/2080427489298391112" in body
    assert "Post on X · @Osinttechnical" in body


def test_map_figure_is_placed_after_opening_paragraph() -> None:
    from algent_backend.agent_system.agents.editorial.publish import render_published_article

    prof = _profile()
    draft = _draft()
    draft = ArticleDraft(
        id="d", title="Fed piece", standfirst="the dek", frame="a market-pricing story",
        body=(
            "First landscape paragraph about the choke point and the theater.\n\n"
            "Second paragraph continues the news move and the dispute."
        ),
        cited_claim_ids=["c1", "c2", "c3"], cited_source_ids=["s1", "s2"],
    )
    analytics = [{
        "request_id": "m1", "status": "produced", "kind": "image",
        "artifact_name": "map_bab_el_mandeb.svg",
        "title": "Bab el-Mandeb theater map",
        "question": "Where is the choke point relative to Saudi Arabia and Yemen?",
        "caption": "Theater map. — AI-assisted analytic, built only from cited data.",
        "data_refs": ["c1"], "figure_check": {"verified": True, "unverified": []},
    }]
    md = render_published_article(draft, prof, analytics)
    body = md.split("How we know this")[0]
    assert body.index("First landscape") < body.index("map_bab_el_mandeb.svg")
    assert body.index("map_bab_el_mandeb.svg") < body.index("Second paragraph")


def test_source_label_names_x_medium_not_bare_handle() -> None:
    """Receipts must not present an X handle as if it were a wire outlet."""
    from algent_backend.agent_system.agents.editorial.publish import _source_label

    bare = SourceArtifact(
        id="x1",
        url="https://x.com/Osinttechnical/status/2080393908685566041",
        title="Post by @Osinttechnical",
        source_type="primary",
    )
    label = _source_label(bare)
    assert "X post" in label
    assert "@Osinttechnical" in label
    assert not label.lower().startswith("post by")

    honest_pub = SourceArtifact(
        id="x2",
        url="https://x.com/WhiteHouse/status/1",
        title="unused",
        publisher="X post · @WhiteHouse (official account)",
        source_type="primary",
    )
    assert _source_label(honest_pub) == "X post · @WhiteHouse (official account) — unused"

    wrapper = SourceArtifact(
        id="x3",
        url="https://x.com/i/web/status/2080393908685566041",
        title="X web status wrapper for @Osinttechnical post",
        source_type="primary",
    )
    assert _source_label(wrapper) == "X post"

    wire = SourceArtifact(
        id="r1",
        url="https://www.reuters.com/world/x",
        title="Israel tankers",
        publisher="Reuters",
        source_type="secondary",
    )
    assert _source_label(wire) == "Israel tankers — Reuters"


def test_appendix_is_silent_when_everything_is_clean() -> None:
    prof = SignalProfile(id="p", title="t",
        source_ledger=[SourceArtifact(id="s1", url="u", title="src", source_type="primary",
                                      snapshot=SourceSnapshot(content_hash="h"))],
        claim_ledger=[Claim(id="c1", text="rose 3.4%", status="confirmed", grounding="snapshotted", supported_by=["s1"])])
    d = ArticleDraft(id="d", title="t", body="Inflation rose 3.4%. [clm_c1]",
                     cited_claim_ids=["c1"], cited_source_ids=["s1"])
    md = render_published_article(d, prof)
    assert "Where we hit a limit" not in md   # nothing to flag -> no alarm section
