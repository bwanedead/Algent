"""Themed menu briefings — roundups off the t1 portfolio, not Radar."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from algent_backend.agent_system.agents.briefing.compose import (
    _COLLAGE_SUBJECT,
    collage_subject,
    cluster_portfolio,
    format_briefing,
    topic_label,
)
from algent_backend.agent_system.agents.editorial.hero_image import check_subject, MAX_SUBJECT_WORDS
from algent_backend.publishing import briefing_queue as q


def _vec(i: str, pillar: str, thesis: str) -> dict:
    return {"id": i, "pillars": [pillar], "title": f"Title {i}", "thesis": thesis}


def test_the_post_is_a_topic_line_then_blurbs() -> None:
    text = format_briefing("energy", [
        _vec("a", "energy", "Amazon's Texas campus got a huge CO2 permit."),
        _vec("b", "energy", "Turkey is wiring Saudi power through Jordan and Syria."),
    ])
    assert text.startswith("today's headlines on energy:\n")
    assert "• Amazon's Texas campus got a huge CO2 permit." in text
    assert "Radar:" not in text
    assert "effort" not in text
    assert "hits" not in text


def test_ai_and_world_events_get_readable_topic_labels() -> None:
    assert topic_label("ai") == "AI"
    assert topic_label("world_events") == "world events"
    assert format_briefing("ai", [_vec("x", "ai", "A model shipped.")]).startswith(
        "today's headlines on AI:"
    )


def test_vectors_cluster_by_primary_pillar_within_the_cap() -> None:
    portfolio = {"t0_ref": "t", "vectors": [
        _vec("e1", "energy", "one"),
        _vec("e2", "energy", "two"),
        _vec("e3", "energy", "three"),
        _vec("g1", "geopolitics", "geo one"),
        _vec("g2", "geopolitics", "geo two"),
        _vec("s1", "science", "lonely"),
    ]}
    clusters = cluster_portfolio(portfolio)
    by_pillar = {c.pillar: c for c in clusters}
    assert "energy" in by_pillar and len(by_pillar["energy"].vectors) == 3
    assert "geopolitics" in by_pillar and len(by_pillar["geopolitics"].vectors) == 2
    assert "science" not in by_pillar  # a one-item pillar is not a roundup


def test_a_full_menu_does_not_queue_a_day_of_roundups() -> None:
    """One t1 menu can yield a dozen pillars. The timeline gets the meatier six."""
    vectors = []
    for pillar in ("energy", "geopolitics", "economics", "ai", "science",
                   "technology", "finance", "politics", "environment"):
        vectors += [_vec(f"{pillar}-{i}", pillar, f"{pillar} {i}") for i in range(3)]
    clusters = cluster_portfolio({"vectors": vectors})
    assert len(clusters) == 6


def test_a_long_pillar_splits_instead_of_dumping() -> None:
    items = [_vec(str(i), "energy", f"blurb {i}") for i in range(7)]
    clusters = cluster_portfolio({"vectors": items})
    energy = [c for c in clusters if c.pillar == "energy"]
    assert [len(c.vectors) for c in energy] == [5, 2]


def test_collage_subjects_pass_the_hero_guards() -> None:
    """Headlines never go to the image model. The Florida chart failure lives here too."""
    for pillar, subject in {**_COLLAGE_SUBJECT, "other": collage_subject("other")}.items():
        reason = check_subject(subject)
        assert reason is None, f"{pillar}: {subject!r} -> {reason}"
        assert len(subject.split()) <= MAX_SUBJECT_WORDS


def test_the_same_cluster_is_not_queued_twice(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(q, "queue_path", lambda: tmp_path / "b.jsonl")
    now = datetime(2026, 8, 12, 18, 0, tzinfo=UTC)
    post = q.BriefingPost(key="t:energy:a,b", pillar="energy", text="today's headlines on energy:\n")
    added, dupes = q.enqueue([post], now=now)
    assert len(added) == 1 and dupes == []
    again, dupes2 = q.enqueue([
        q.BriefingPost(key="t:energy:a,b", pillar="energy", text="different wording"),
    ], now=now + timedelta(hours=1))
    assert again == [] and len(dupes2) == 1
