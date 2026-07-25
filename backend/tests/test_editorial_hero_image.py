"""Tests for hero-image briefs — the guards exist because of three real generations."""

from __future__ import annotations

import pytest

from algent_backend.agent_system.agents.editorial.hero_image import (
    IMAGE_LABEL,
    IMAGE_REJECTIONS,
    UnsafeImageSubject,
    build_image_prompt,
    check_subject,
    is_safe_subject,
)


def test_a_depictable_subject_builds_a_prompt_with_the_prohibitions_attached() -> None:
    prompt = build_image_prompt("an orca surfacing in coastal water")

    assert prompt.startswith("an orca surfacing in coastal water.")
    # The prohibitions are appended in code, never left to a prompt author to remember.
    for required in ("Do not render any text", "Do not render charts", "seals", "documentary"):
        assert required in prompt


def test_setting_is_appended_to_the_subject() -> None:
    prompt = build_image_prompt("a juvenile feathered tyrannosaur", setting="in conifer forest")
    assert prompt.startswith("a juvenile feathered tyrannosaur, in conifer forest.")


def test_a_headline_with_figures_is_refused() -> None:
    """The Florida failure: this headline, passed verbatim, produced a picture containing a
    fabricated BEA seal, the words DATA CONFIRMED, and an invented ranking chart."""
    headline = "Florida's $1.8 trillion economy claim is backed by BEA data"

    assert not is_safe_subject(headline)
    assert "quantity" in check_subject(headline)
    with pytest.raises(UnsafeImageSubject):
        build_image_prompt(headline)


def test_a_subject_naming_a_chart_or_document_is_refused() -> None:
    """A picture of a chart is a claim, and a generated chart is a claim we did not verify."""
    for bad in ("a bar chart of state GDP", "an official seal on a report", "a map of Florida"):
        assert not is_safe_subject(bad), bad
        assert "chart/document/logo" in check_subject(bad)


def test_a_whole_headline_is_refused_for_length() -> None:
    """Passing the T. rex headline verbatim rendered the entire sentence inside the image."""
    headline = (
        "2026 study provides new evidence that very young T. rex hatchlings fed early, "
        "but not hunting from birth"
    )
    assert "too long" in check_subject(headline)


def test_ranking_words_count_as_quantities() -> None:
    # "14th-largest" arrived as a ranking and came back as a drawn league table.
    assert not is_safe_subject("the ranking of state economies")
    assert not is_safe_subject("Florida ranked against peers")


def test_an_empty_subject_is_refused_so_no_image_beats_a_wrong_one() -> None:
    assert check_subject("") == "empty subject"
    assert check_subject("   ") == "empty subject"


def test_the_review_gate_names_the_failures_we_have_actually_seen() -> None:
    assert "chart_or_data" in IMAGE_REJECTIONS       # the fabricated ranking chart
    assert "official_insignia" in IMAGE_REJECTIONS   # the fabricated BEA seal
    assert "text_in_image" in IMAGE_REJECTIONS       # the headline baked into the T. rex image
    assert "reads_as_documentary" in IMAGE_REJECTIONS


def test_generated_images_carry_an_honest_label() -> None:
    assert "AI-generated" in IMAGE_LABEL and "not a photograph" in IMAGE_LABEL
