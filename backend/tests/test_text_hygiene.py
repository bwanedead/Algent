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


def test_c1_controls_are_scrubbed_too() -> None:
    """U+0080-U+009F is where a UTF-8 sequence misread as Latin-1 lands.

    An em dash mangled that way carries C1 bytes — the same invisible, slug-poisoning
    class as the NUL we actually observed, so it is covered before it is seen.
    """
    assert scrub_text("breathe  and why") == "breathe and why"
    assert scrub_text("ab") == "ab"


def test_ordinary_accented_text_is_still_safe() -> None:
    """The C1 range is control codes, not accents — U+00C0 and up must survive."""
    for text in ("Kühl", "Warnemünde", "café", "naïve", "37°C", "£100", "—"):
        assert scrub_text(text) == text


# -- provider corruption, and why it is repairable ----------------------------
#
# Derived by diffing the rake's own input against its output on a real run:
#     '’' U+2019, UTF-8 e2 80 99  ->  "\x00e2" "\x0080" "\x0099"
# Every byte arrives as NUL + that byte's hex, i.e. \xe2\x80\x99 escaping with the
# backslash-x replaced by a NUL. The original is therefore fully recoverable.

_NUL = chr(0)


def test_a_mangled_apostrophe_is_restored_exactly() -> None:
    corrupt = "One of China" + _NUL + "e2" + _NUL + "80" + _NUL + "99s Most Powerful"
    assert scrub_text(corrupt) == "One of China’s Most Powerful"


def test_a_mangled_em_dash_is_restored_exactly() -> None:
    corrupt = "Corals breathe " + _NUL + "e2" + _NUL + "80" + _NUL + "94 and why"
    assert scrub_text(corrupt) == "Corals breathe — and why"


def test_a_mangled_umlaut_is_restored() -> None:
    """Two-byte sequences too: 'ü' is c3 bc, which is how "Kühl" got wrecked."""
    assert scrub_text("K" + _NUL + "c3" + _NUL + "bchl") == "Kühl"


def test_a_truncated_corruption_is_dropped_not_left_as_hex() -> None:
    """The failure mode of a delete-only fix: "China\x00b9s" -> "Chinab9s"."""
    out = scrub_text("One of China" + _NUL + "b9s Most Powerful")
    assert "b9" not in out
    assert out == "One of Chinas Most Powerful"


def test_a_bare_nul_still_goes() -> None:
    """No hex to rebuild from — unrepairable, but it must never reach a slug."""
    assert scrub_text("Nonthaburi " + _NUL + " rare") == "Nonthaburi rare"


def test_repair_runs_before_stripping() -> None:
    """Ordering is the whole fix: strip first and the hex survives as garbage."""
    assert "e2" not in scrub_text("a" + _NUL + "e2" + _NUL + "80" + _NUL + "94b")


def test_a_restored_character_reaches_the_slug_intact() -> None:
    from algent_backend.publishing.converter import convert

    md = ("# China" + _NUL + "e2" + _NUL + "80" + _NUL + "99s chipmaking push\n"
          "*dek*\n\nBody.\n")
    art = convert(article_md=md, rail={}, pipeline={"profile_id": "p", "status": "publishable"},
                  profile={"id": "p"}, date="2026-08-07")
    assert art.title == "China’s chipmaking push"
    assert "e2" not in art.slug and "\x00" not in art.slug
