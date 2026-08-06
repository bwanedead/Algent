"""Reader-entry contracts: treatment fields, briefing, publish quick-take, headline message."""

from __future__ import annotations

from algent_backend.agent_system.agents.editorial.briefing import render_treatment
from algent_backend.agent_system.agents.editorial.draft import ArticleDraft, QuickTake
from algent_backend.agent_system.agents.editorial.draft_prompts import DRAFTER_ROLE
from algent_backend.agent_system.agents.editorial.headline_messages import build_headline_message
from algent_backend.agent_system.agents.editorial.publish import render_published_article
from algent_backend.agent_system.agents.editorial.treatment import (
    CausalLink,
    EditorialTreatment,
    FrameOption,
)
from algent_backend.agent_system.agents.research.profile import SignalProfile


def test_treatment_entry_fields_round_trip_and_brief() -> None:
    t = EditorialTreatment(
        id="trt_ceuta",
        title="Ceuta",
        chosen_frame=FrameOption(frame="border pressure", rationale="spatial relationship"),
        news_kernel="Thousands attempted to cross into Ceuta from Morocco.",
        reader_payoff="An EU border enclave is under acute pressure.",
        key_uncertainty="Whether a Spanish policy change caused the surge.",
        plain_subject="",
        causal_chain=[
            CausalLink(
                cause="Spanish return-policy change",
                effect="mass crossing attempt",
                status="possible",
                note="participants may have misread the rule",
            ),
        ],
    )
    dumped = t.model_dump()
    back = EditorialTreatment.model_validate(dumped)
    assert back.news_kernel.startswith("Thousands")
    assert back.causal_chain[0].status == "possible"

    md = render_treatment(t)
    assert "News kernel:" in md and "Why it matters:" in md
    assert "[possible]" in md and "Spanish return-policy change" in md


def test_drafter_path_is_news_first_not_landscape_first() -> None:
    assert "News kernel" in DRAFTER_ROLE
    assert "**PATH (anti-circle; news-first):**" in DRAFTER_ROLE
    # The old landscape-first PATH was the buried-kernel failure mode.
    assert "(1) **Landscape**" not in DRAFTER_ROLE


def test_published_article_embeds_quick_take() -> None:
    draft = ArticleDraft(
        id="d",
        title="AI probes an undeciphered Bronze Age script",
        standfirst="Researchers tested a model on Linear A; it has not translated the corpus.",
        quick_take=QuickTake(
            what_happened="Researchers used an AI model to probe Linear A tablets.",
            why_it_matters="It may help study an undeciphered Bronze Age script.",
            what_is_uncertain="The work has not produced a translation.",
        ),
        body="Researchers applied a statistical model to Linear A, an undeciphered script.",
    )
    md = render_published_article(draft, SignalProfile(id="p", title="t"))
    assert "## At a glance" in md
    assert "**What happened:** Researchers used an AI model" in md
    assert "**What remains uncertain:** The work has not produced a translation." in md


def test_body_places_figures_by_placement() -> None:
    from algent_backend.agent_system.agents.editorial.publish import _body_with_figures

    body = (
        "Opening paragraph about the surge at the border fence after dawn, with enough "
        "words that the publisher treats this block as a complete landscape setup for the "
        "reader before any figure is inserted into the article body near the top of the piece.\n\n"
        "## What changed\n\n"
        "Policy detail in the first section.\n\n"
        "## What comes next\n\n"
        "Forward look for the reader.\n\n"
        "Closing paragraph."
    )
    produced = [
        {
            "title": "Locator", "placement": "after_opening",
            "artifact_name": "map.svg", "caption": "Ceuta and Morocco.",
            "status": "produced",
        },
        {
            "title": "Mechanism", "placement": "after_section",
            "artifact_name": "flow.svg", "caption": "How the surge formed.",
            "status": "produced",
        },
        {
            "title": "Trajectory", "placement": "mid_body",
            "artifact_name": "chart.svg", "caption": "Arrivals over weeks.",
            "status": "produced",
        },
    ]
    lines = _body_with_figures(body, produced)
    text = "\n".join(lines)
    assert text.index("Opening paragraph") < text.index("map.svg")
    assert text.index("map.svg") < text.index("## What changed")
    assert text.index("Policy detail") < text.index("flow.svg")
    assert text.index("flow.svg") < text.index("## What comes next")
    assert "chart.svg" in text


def test_receipts_list_visuals_not_shipped() -> None:
    draft = ArticleDraft(id="d", title="T", body="Body text.")
    md = render_published_article(
        draft,
        SignalProfile(id="p", title="t"),
        analytics=[
            {
                "id": "anx_02", "title": "Tablet photo", "status": "source_unavailable",
                "note": "licensed media lane not ready",
            },
            {
                "request_id": "anx_03", "title": "Extra chart", "status": "soft_cap_skipped",
            },
        ],
    )
    assert "**Visuals not shipped**" in md
    assert "source_unavailable" in md and "soft_cap_skipped" in md


def test_headline_message_includes_treatment_entry() -> None:
    draft = ArticleDraft(id="d", title="working", body="Body text about the event.")
    treatment = EditorialTreatment(
        id="trt",
        news_kernel="Event X happened.",
        reader_payoff="It changes Y.",
        key_uncertainty="Z remains open.",
        plain_subject="an undeciphered Bronze Age script",
    )
    msg = build_headline_message(draft, treatment)
    assert "news_kernel: Event X happened." in msg
    assert "plain_subject: an undeciphered Bronze Age script" in msg
    assert "FINAL SURFACE PACKAGE" in msg


def test_apply_headline_merges_partial_quick_take() -> None:
    from algent_backend.agent_system.agents.editorial.pipeline import _apply_headline

    draft = {
        "title": "working",
        "standfirst": "old dek",
        "quick_take": {
            "what_happened": "Prior what.",
            "why_it_matters": "Prior why.",
            "what_is_uncertain": "Prior open.",
        },
    }
    treatment = {
        "news_kernel": "Treatment what.",
        "reader_payoff": "Treatment why.",
        "key_uncertainty": "Treatment open.",
    }
    # Partial headline must not wipe the other gist fields.
    out = _apply_headline(draft, {
        "title": "Cold title",
        "standfirst": "Cold dek",
        "quick_take": {"what_happened": "Headline what."},
    }, treatment=treatment)
    assert out["title"] == "Cold title"
    assert out["quick_take"]["what_happened"] == "Headline what."
    assert out["quick_take"]["why_it_matters"] == "Prior why."
    assert out["quick_take"]["what_is_uncertain"] == "Prior open."

    # Empty draft quick_take falls back to treatment entry.
    bare = _apply_headline(
        {"title": "t"},
        {"title": "T2", "quick_take": {}},
        treatment=treatment,
    )
    assert bare["quick_take"]["what_happened"] == "Treatment what."
    assert bare["quick_take"]["why_it_matters"] == "Treatment why."


def test_surface_cold_browser_flags_specialist_title() -> None:
    from algent_backend.agent_system.agents.editorial.pipeline import (
        _surface_cold_browser_issues,
    )

    issues = _surface_cold_browser_issues(
        {"title": "Linear A", "standfirst": "A model ran.", "quick_take": {}},
        {
            "plain_subject": "an undeciphered Bronze Age script",
            "news_kernel": "Researchers probed Linear A.",
            "reader_payoff": "It may help study the script.",
            "key_uncertainty": "No translation yet.",
        },
    )
    assert any("plain_subject" in i for i in issues)
    assert any("quick_take.what_happened" in i for i in issues)