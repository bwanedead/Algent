"""Tests for the topic cooldown — recent headlines as the 'already covered' reference,
plus the coarser recurring-coverage reference ('have we been circling one thing?')."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from algent_backend.agent_system.agents.routing.contracts import RouteCandidate, RoutingBrief
from algent_backend.agent_system.agents.routing.prompts import build_router_message
from algent_backend.publishing.history import recent_headlines, recurring_coverage

_NOW = datetime(2026, 7, 18, tzinfo=UTC)


def _article(
    d: Path, slug: str, title: str, published_at: str, status: str = "publishable",
    tags: tuple[str, ...] = (), places: tuple[str, ...] = (),
) -> None:
    (d / "content" / "articles").mkdir(parents=True, exist_ok=True)
    blocks = "".join(
        f"{key}:\n" + "".join(f"- {v}\n" for v in vals)
        for key, vals in (("tags", tags), ("places", places)) if vals
    )
    (d / "content" / "articles" / f"{slug}.md").write_text(
        f'---\ntitle: "{title}"\npublished_at: "{published_at}"\nstatus: {status}\n'
        f"{blocks}---\n\nBody.\n",
        encoding="utf-8")


def test_recent_headlines_newest_first(tmp_path: Path) -> None:
    _article(tmp_path, "a", "Hormuz disruption", "2026-07-16T10:00:00+00:00")
    _article(tmp_path, "b", "FDA approves drug", "2026-07-17T21:00:00+00:00")
    out = recent_headlines([tmp_path], now=_NOW)
    assert [t for _, t in out] == ["FDA approves drug", "Hormuz disruption"]


def test_time_cooldown_expires_old_stories(tmp_path: Path) -> None:
    _article(tmp_path, "old", "Ancient news", "2026-06-01T10:00:00+00:00")   # >10 days back
    _article(tmp_path, "new", "Fresh news", "2026-07-17T10:00:00+00:00")
    assert [t for _, t in recent_headlines([tmp_path], now=_NOW)] == ["Fresh news"]


def test_article_cooldown_caps_the_list(tmp_path: Path) -> None:
    for i in range(8):
        _article(tmp_path, f"s{i}", f"Story {i}", f"2026-07-1{i % 8}T10:00:00+00:00")
    assert len(recent_headlines([tmp_path], limit=3, now=_NOW)) == 3


def test_retracted_articles_do_not_suppress_new_coverage(tmp_path: Path) -> None:
    # A retracted piece is withdrawn — the story is emphatically NOT covered.
    _article(tmp_path, "r", "Retracted piece", "2026-07-17T10:00:00+00:00", status="retracted")
    assert recent_headlines([tmp_path], now=_NOW) == []


def test_live_worktree_wins_over_the_working_tree_copy(tmp_path: Path) -> None:
    live, work = tmp_path / "live", tmp_path / "work"
    _article(live, "same", "Published title", "2026-07-17T10:00:00+00:00")
    _article(work, "same", "Stale staged title", "2026-07-17T10:00:00+00:00")
    out = recent_headlines([live, work], now=_NOW)          # live listed first -> it wins
    assert [t for _, t in out] == ["Published title"]


def test_missing_site_dir_is_not_an_error(tmp_path: Path) -> None:
    assert recent_headlines([tmp_path / "nope"], now=_NOW) == []


def test_cooldown_reaches_the_router_message() -> None:
    brief = RoutingBrief(role="r", candidate_kind="k", selecting_for="s", downstream="d",
                         recent=(("2026-07-17T10:00:00+00:00", "Hormuz disruption"),))
    msg = build_router_message(
        [RouteCandidate(id="v1", label="Hormuz again", summary="same story")],
        brief,
    )
    assert "ALREADY COVERED" in msg and "Hormuz disruption" in msg
    assert "SEMANTICALLY" in msg
    assert "cooldown" in msg.lower()


def test_no_cooldown_section_when_nothing_published() -> None:
    brief = RoutingBrief(role="r", candidate_kind="k", selecting_for="s", downstream="d")
    msg = build_router_message([RouteCandidate(id="v1", label="x", summary="y")], brief)
    assert "none loaded" in msg.lower() or "no recent" in msg.lower()


# -- recurring coverage: the coarser 'one rut' reference ----------------------


def _shipping(d: Path, slug: str, title: str, when: str) -> None:
    _article(d, slug, title, when, tags=("trade", "Strait of Hormuz"), places=("Iran",))


def test_recurrence_counted_on_subject_place_and_topic(tmp_path: Path) -> None:
    """Honestly-different Hormuz stories should still register as one thing circled."""
    for i in range(3):
        _shipping(tmp_path, f"h{i}", f"Hormuz day {i}", f"2026-07-1{i + 4}T10:00:00+00:00")

    seen = dict(recurring_coverage([tmp_path], now=_NOW))

    assert seen["topic:trade"] == 3                # canonical desk
    assert seen["subject:Strait of Hormuz"] == 3   # the specific named entity
    assert seen["place:Iran"] == 3                 # geography


def test_recurrence_ignores_what_was_covered_only_once(tmp_path: Path) -> None:
    """One article on a subject is coverage, not a rut — it must not register."""
    _shipping(tmp_path, "h", "Hormuz once", "2026-07-16T10:00:00+00:00")
    _article(tmp_path, "s", "Exomoon found", "2026-07-17T10:00:00+00:00",
             tags=("science", "Kepler-1625b"), places=("United States",))

    assert recurring_coverage([tmp_path], now=_NOW) == []


def test_recurrence_respects_the_same_time_window_as_cooldown(tmp_path: Path) -> None:
    for i in range(3):
        _shipping(tmp_path, f"old{i}", f"Old Hormuz {i}", f"2026-06-0{i + 1}T10:00:00+00:00")

    assert recurring_coverage([tmp_path], now=_NOW) == []


def test_recurrence_reaches_the_router_message_as_a_tiebreak_not_a_block() -> None:
    brief = RoutingBrief(role="r", candidate_kind="k", selecting_for="s", downstream="d",
                         saturated=(("subject:Strait of Hormuz", 4),))
    msg = build_router_message([RouteCandidate(id="v1", label="x", summary="y")], brief)

    assert "WHAT WE KEEP CIRCLING" in msg and "Strait of Hormuz" in msg
    # The distinction from cooldown has to survive into the prompt, or the agent
    # treats a recurring subject as a blocked one and starves a live story.
    assert "tie-break" in msg.lower()
    assert "not a block" in msg.lower()
    # And it must not read as a checklist of categories to fill.
    assert "not a quota" in msg.lower() or "nothing is owed a slot" in msg.lower()


def test_no_recurrence_section_when_nothing_recurs() -> None:
    brief = RoutingBrief(role="r", candidate_kind="k", selecting_for="s", downstream="d")
    msg = build_router_message([RouteCandidate(id="v1", label="x", summary="y")], brief)
    assert "WHAT WE KEEP CIRCLING" not in msg
