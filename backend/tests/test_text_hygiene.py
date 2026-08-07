"""
Control characters must not reach a contract, an artifact, or a URL.

A live synthesis run wrote 333 NULs into its portfolio — one wherever an em dash should
have been — and they travelled into article front-matter and then into a published slug.
A slug is a permanent URL: it cannot be corrected later without breaking every link.
"""

from __future__ import annotations

from algent_backend.agent_system.foundation.text_hygiene import (
    has_control_chars,
    scrub,
    scrub_text,
)


def test_a_nul_is_removed() -> None:
    assert scrub_text("Debsirin Nonthaburi \x00 rare mass shooting") == (
        "Debsirin Nonthaburi rare mass shooting"
    )


def test_removal_does_not_leave_a_double_space() -> None:
    """The NUL sat between words, so naive removal leaves "Nonthaburi  rare"."""
    assert "  " not in scrub_text("a \x00 b")


def test_ordinary_text_is_returned_untouched() -> None:
    """Non-ASCII prose is fine — this scrubs controls, not Unicode."""
    for text in ("Corals breathe — and why heat breaks it",
                 "Michael Kühl at Warnemünde, 37°C",
                 "plain ascii"):
        assert scrub_text(text) == text


def test_tabs_and_newlines_survive() -> None:
    """A body legitimately contains newlines; only the unprintable C0 set goes."""
    assert scrub_text("para one\n\npara two") == "para one\n\npara two"


def test_other_c0_controls_go_too() -> None:
    assert scrub_text("a\x01b\x1fc\x7fd") == "abcd"


def test_scrub_walks_nested_structures() -> None:
    payload = {"vectors": [{"title": "x \x00 y", "tags": ["a\x00b"]}], "n": 3}
    assert scrub(payload) == {"vectors": [{"title": "x y", "tags": ["ab"]}], "n": 3}


def test_detection_is_available_for_reporting() -> None:
    assert has_control_chars("a\x00b") is True
    assert has_control_chars("a — b") is False


def test_a_corrupt_title_cannot_reach_a_slug() -> None:
    """The published failure: '...breathe-94-and-why...' in a permanent URL."""
    from algent_backend.publishing.converter import convert

    md = "# Corals breathe \x00 and why heat makes the pump fail\n*dek*\n\nBody text.\n"
    art = convert(article_md=md, rail={}, pipeline={"profile_id": "p", "status": "publishable"},
                  profile={"id": "p"}, date="2026-08-07")
    assert "\x00" not in art.title
    assert "94" not in art.slug
    assert art.title == "Corals breathe and why heat makes the pump fail"


def test_a_corrupt_portfolio_is_cleaned_before_validation() -> None:
    from algent_backend.agent_system.agents.discovery.portfolio import coerce_portfolio

    port = coerce_portfolio({"vectors": [{
        "title": "Thailand school shooting \x00 rare in a low-gun country",
        "thesis": "t", "vector_type": "story", "rationale": "r", "research_effort": "light",
    }]})
    assert port is not None
    assert "\x00" not in port.vectors[0].title
