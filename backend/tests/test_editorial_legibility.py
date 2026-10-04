"""
Tests for figure geometry and for reviewer-owned flag reconciliation.

Two things are checked here and the split between them is deliberate. Whether a figure
fits its canvas is geometry — decidable from the file, so it belongs in code. Whether an
acronym is adequately explained, or whether an article earns a country's flag, is a
semantic judgment, so it belongs to the review pass and what is tested here is only the
*plumbing* that carries the reviewer's decision, never a guess at the decision itself.

The geometry check had a wrong first implementation — it read matplotlib's font-unit
glyph advances as page coordinates and flagged 6 of 30 published figures, every one a
false positive — so the nested-transform case is pinned explicitly rather than trusted.
"""

from __future__ import annotations

from algent_backend.agent_system.agents.editorial.analytics_geometry import (
    TOLERANCE,
    canvas_size,
    check_fit,
    overflow,
)
from algent_backend.agent_system.agents.editorial.comprehension_contracts import (
    ComprehensionCheck,
    ComprehensionFinding,
)
from algent_backend.agent_system.agents.editorial.comprehension_loop import _finalize, _message
from algent_backend.agent_system.agents.editorial.draft import ArticleDraft
from algent_backend.publishing.converter import _derived_frontmatter

# -- figure geometry ----------------------------------------------------------


def _svg(body: str, *, w: int = 100, h: int = 100) -> str:
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}">{body}</svg>'


def test_content_inside_the_canvas_passes() -> None:
    assert check_fit(_svg('<g transform="translate(50 50)"><use x="0" y="0"/></g>')) is None


def test_content_past_the_edge_is_reported() -> None:
    why = check_fit(_svg('<g transform="translate(180 50)"><use x="0" y="0"/></g>'))
    assert why is not None
    assert "horizontally" in why and "cut off" in why


def test_glyph_advances_under_a_scale_are_not_page_coordinates() -> None:
    """The regression that made the first version of this check useless.

    Matplotlib writes text as glyph refs carrying font-unit advances inside a
    scale(0.01) group. A raw read sees x=4000 on a 100-wide canvas and screams; the real
    position is 4000 * 0.01 = 40, comfortably inside.
    """
    svg = _svg(
        '<g transform="translate(10 50) scale(0.01 -0.01)">'
        '<use x="0" y="0"/><use transform="translate(4000 0)"/></g>'
    )
    assert check_fit(svg) is None
    assert overflow(svg)[0] < 1.0


def test_scaled_text_that_really_does_overrun_is_still_caught() -> None:
    """Same shape, but the scaled extent genuinely leaves the canvas: 80 + 900*0.1 = 170."""
    svg = _svg(
        '<g transform="translate(80 50) scale(0.1 -0.1)">'
        '<use x="0" y="0"/><use transform="translate(900 0)"/></g>'
    )
    assert check_fit(svg) is not None


def test_glyph_definitions_in_defs_are_ignored() -> None:
    """<defs> holds outlines in their own space and is never painted where it sits."""
    svg = _svg(
        '<defs><path id="g" transform="translate(9000 9000)" d="M0 0"/></defs>'
        '<g transform="translate(50 50)"><use x="0" y="0"/></g>'
    )
    assert check_fit(svg) is None


def test_a_file_with_no_viewbox_is_not_judged() -> None:
    """Unknown is not the same as broken — never fail a figure we cannot measure."""
    assert check_fit('<svg xmlns="http://www.w3.org/2000/svg"><use x="9999"/></svg>') is None
    assert canvas_size("<svg/>") is None


def test_unparseable_svg_does_not_raise() -> None:
    assert check_fit('<svg viewBox="0 0 10 10"><g unclosed>') is None


def test_tolerance_sits_at_the_canvas_edge() -> None:
    # Calibrated against every published figure: 29 landed <= 0.98, the reported-broken
    # one at 1.02. A looser bound would have missed the only real failure.
    assert TOLERANCE == 1.0


# -- flags: the reviewer decides, the plumbing obeys --------------------------


def _draft() -> ArticleDraft:
    return ArticleDraft(id="drf_1", title="A telescope is failing",
                        standfirst="It has no engine.", body="NASA is attempting a rescue.")


def _check(**kw) -> ComprehensionCheck:
    return ComprehensionCheck(id="", verdict="clear", **kw)


def test_reviewer_sees_the_flags_it_is_asked_to_judge() -> None:
    msg = _message(_draft(), ["United States", "South Africa"])
    assert "United States, South Africa" in msg
    assert "COUNTRY FLAGS" in msg


def test_no_flags_block_when_there_are_no_flags() -> None:
    assert "COUNTRY FLAGS" not in _message(_draft(), [])


def test_a_drop_is_kept_when_the_flag_was_offered() -> None:
    out = _finalize(_check(places_to_drop=["South Africa"]), _draft(), "m",
                    places=["United States", "South Africa"])
    assert out.places_to_drop == ["South Africa"]


def test_a_drop_for_a_flag_never_offered_is_discarded() -> None:
    """The reviewer can keep, explain or remove — never invent. A name we did not show it
    means it is confused, and honouring that would let a review fabricate removals."""
    out = _finalize(_check(places_to_drop=["Peru"]), _draft(), "m", places=["United States"])
    assert out.places_to_drop == []


def test_drop_matching_is_case_and_space_insensitive() -> None:
    out = _finalize(_check(places_to_drop=["  south africa "]), _draft(), "m",
                    places=["South Africa"])
    assert out.places_to_drop == ["  south africa "]


def test_dropping_a_flag_alone_does_not_force_a_repair_lap() -> None:
    """Removing the flag already resolves it — rewriting the prose would be busywork."""
    out = _finalize(
        _check(places_to_drop=["South Africa"],
               findings=[ComprehensionFinding(id="", kind="unjustified_flag",
                                              where="South Africa", issue="never mentioned")]),
        _draft(), "m", places=["South Africa"],
    )
    assert out.verdict == "clear"


def test_a_flag_the_reviewer_wants_earned_does_force_a_repair_lap() -> None:
    """The other repair: the country belongs, so the piece must say why."""
    out = _finalize(
        _check(findings=[ComprehensionFinding(id="", kind="unjustified_flag", where="Chile",
                                              issue="never says why Chile is involved",
                                              fix="add_handhold")]),
        _draft(), "m", places=["Chile"],
    )
    assert out.verdict == "needs_ramp"


def test_publish_removes_the_rejected_flag_and_keeps_its_pairing() -> None:
    profile = {"countries_of_relevance": [
        {"iso2": "US", "name": "United States"},
        {"iso2": "ZA", "name": "South Africa"},
    ]}
    fm = _derived_frontmatter(profile, {}, {"places_to_drop": ["South Africa"]})

    assert fm["places"] == ["United States"]
    assert len(fm["flags"]) == 1          # places and flags are positional — filter together
    assert "🇿🇦" not in fm["flags"]


def test_publish_leaves_flags_alone_when_nothing_was_rejected() -> None:
    profile = {"countries_of_relevance": [{"iso2": "US", "name": "United States"}]}
    fm = _derived_frontmatter(profile, {}, {})
    assert fm["places"] == ["United States"]
    assert len(fm["flags"]) == 1
