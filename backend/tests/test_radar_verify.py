"""The radar check — the only thing between a wire line and a published sentence."""

from __future__ import annotations

from algent_backend.agent_system.agents.radar.contracts import RadarPost
from algent_backend.agent_system.agents.radar.verify import (
    RadarCheck,
    apply_checks,
)


def _post(key: str, text: str) -> RadarPost:
    return RadarPost(source_key=key, text=text)


def test_a_trim_replaces_the_text_and_a_drop_removes_the_post() -> None:
    """The remedy for an unsupported clause is deletion, not a research trip.

    Live failure: "Baby was rescued from rubble after Colombia earthquake" was posted as
    "...following the earthquake that has left deaths rising" — a casualty trajectory nobody
    sourced, invented by the sentence wanting a fuller ending.
    """
    posts = [
        _post("k1", "Radar: a baby was rescued after the earthquake that has left deaths rising."),
        _post("k2", "Radar: a ferry caught fire in Indonesia."),
        _post("k3", "Radar: officials blamed sabotage."),
    ]
    checks = {
        "k1": RadarCheck(source_key="k1", verdict="trim",
                         text="Radar: a baby was rescued after the earthquake.",
                         reason="casualty trajectory not in the line"),
        "k2": RadarCheck(source_key="k2", verdict="keep"),
        "k3": RadarCheck(source_key="k3", verdict="drop", reason="cause not in the line"),
    }
    kept, rejected = apply_checks(posts, checks)

    assert [p.source_key for p in kept] == ["k1", "k2"]
    assert kept[0].text == "Radar: a baby was rescued after the earthquake."
    assert [r["source_key"] for r in rejected] == ["k3"]
    assert "cause not in the line" in rejected[0]["reason"]


def test_an_unchecked_post_survives() -> None:
    """Fail open. A check that cannot run must not silently empty the queue — the posts it
    guards were already written under the same doctrine."""
    posts = [_post("k1", "Radar: something happened.")]
    kept, rejected = apply_checks(posts, {})
    assert len(kept) == 1 and rejected == []


def test_an_unusable_trim_is_treated_as_a_drop() -> None:
    """A trim that comes back empty or over-length must not ship broken."""
    posts = [_post("k1", "Radar: a real post."), _post("k2", "Radar: another.")]
    checks = {
        "k1": RadarCheck(source_key="k1", verdict="trim", text="   ", reason="nothing left"),
        "k2": RadarCheck(source_key="k2", verdict="trim", text="x" * 400, reason="too long"),
    }
    kept, rejected = apply_checks(posts, checks)
    assert kept == [] and len(rejected) == 2
