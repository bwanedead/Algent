"""House grain for a landed article — default vs earned ceiling."""

from __future__ import annotations

from algent_backend.agent_system.agents.editorial.length import (
    ceiling_words,
    digest_words,
    reviewer_length_task,
    word_band,
)


def test_typical_band_is_unchanged() -> None:
    assert word_band(4) == (760, 1000)


def test_default_five_minutes_cannot_authorize_past_the_digest() -> None:
    low, high = word_band(5)
    assert high == digest_words()
    assert low <= high <= 1100


def test_generous_treatment_cannot_authorize_a_tour() -> None:
    low, high = word_band(10)
    assert high == ceiling_words()
    assert low <= high
    assert high <= 1500


def test_reviewer_task_names_the_count_and_the_premise() -> None:
    line = reviewer_length_task(2354)
    assert "2354 words" in line
    assert f"{digest_words()} words" in line
    assert "10.7 min" in line
    assert "left the premise" in line
    assert "wrap the tour" in line


def test_drafter_task_carries_the_plans_band_in_paragraphs() -> None:
    # One length authority: the treatment's band. No plan falls back to the digest.
    from algent_backend.agent_system.agents.editorial.draft_messages import build_draft_message
    from algent_backend.agent_system.agents.editorial.length import paragraphs_for, planned_band
    from algent_backend.agent_system.agents.editorial.treatment import EditorialTreatment
    from algent_backend.agent_system.agents.research.profile import SignalProfile

    msg = build_draft_message(
        EditorialTreatment(id="t", title="X"), SignalProfile(id="p", title="X"),
    )
    assert f"0-{digest_words()} words" in msg and "adjacent world" in msg

    planned = EditorialTreatment(id="t", title="X", read_minutes=6)
    low, high = planned_band(planned)
    msg = build_draft_message(planned, SignalProfile(id="p", title="X"))
    assert f"LENGTH: {low}-{high} words" in msg
    assert f"about {paragraphs_for(high)} paragraphs" in msg
    assert high <= ceiling_words()


def test_cut_names_the_share_and_paragraphs_to_remove() -> None:
    from algent_backend.agent_system.agents.editorial.compress import _cut_task

    task = _cut_task(2305, 1140, 1500, again=False)
    assert "Remove about 985 words" in task and "43%" in task and "13 whole paragraphs" in task
