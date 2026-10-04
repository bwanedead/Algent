"""The intel desk: heat is measured, theaters keep their identity, briefs render safely."""

from __future__ import annotations

from datetime import date

from algent_backend.agent_system.agents.intel import heat, render
from algent_backend.agent_system.agents.intel.contracts import (
    Brief,
    Escalation,
    Member,
    Relation,
    Theater,
    TimelineItem,
)

EDITIONS = [
    {"slug": "2026-09-22-2200", "leads": [{"n": 1, "title": "Drones over Poland", "thesis": "t", "sources": ["https://a"]},
                                          {"n": 2, "title": "Sushi wars", "thesis": "t", "sources": []}]},
    {"slug": "2026-09-27-2200", "leads": [{"n": 1, "title": "Warehouse arson in Germany", "thesis": "t", "sources": []},
                                          {"n": 2, "title": "Baltic cable cut", "thesis": "t", "sources": []}]},
    {"slug": "2026-09-28-2200", "leads": [{"n": 1, "title": "Rail sabotage in Czechia", "thesis": "t", "sources": []}]},
]


class _Plan:
    def __init__(self, plan):
        self.plan = plan

    def with_structured_output(self, _s):
        return self

    def invoke(self, *_a, **_k):
        return self.plan


def _ctx(plan):
    return type("X", (), {"model_resolver": type("R", (), {
        "resolve": lambda _s, _spec: type("C", (), {"client": _Plan(plan)})()})()})()


def test_the_window_and_the_heat_math() -> None:
    heads = heat.headlines(EDITIONS, days=7)
    assert set(heads) == {"2026-09-22-2200#1", "2026-09-22-2200#2", "2026-09-27-2200#1",
                          "2026-09-27-2200#2", "2026-09-28-2200#1"}
    t = Theater(id="thr_x", name="Russia vs European infrastructure", members=[
        Member(edition=e, n=n, title="x") for e, n in
        (("2026-09-22-2200", 1), ("2026-09-27-2200", 1), ("2026-09-27-2200", 2), ("2026-09-28-2200", 1))])
    h = heat.measure(t, EDITIONS, days=7, today=date(2026, 9, 28))
    # no edition in the prior window (Sep 23-25) = no data: not "heating", and first seen Sep 22 is not new
    assert h.recent == 3 and h.prior == 0 and h.total == 4 and h.trend == "steady"
    assert h.recent_share == 1.0 and h.prior_share == 0.0
    assert [p.count for p in h.series][-3:] == [0, 2, 1] and h.first_seen == "2026-09-22"
    assert [p.editions for p in h.series] == [1, 0, 0, 0, 0, 1, 1]


def _eds(spec: dict[str, int]) -> list[dict]:
    """edition slug -> number of headlines"""
    return [{"slug": s, "leads": [{"n": i + 1} for i in range(n)]} for s, n in spec.items()]


def _theater(*slugs: str) -> Theater:
    return Theater(id="thr_t", name="T", members=[Member(edition=s, n=i + 1, title="x") for i, s in enumerate(slugs)])


TODAY = date(2026, 9, 28)


def test_same_share_with_irregular_editions_is_steady_not_cooling() -> None:
    # prior window: 4 editions of 10 (4 theater headlines = 10%); recent: 1 edition of 10 (1 = 10%)
    eds = _eds({"2026-09-23-0800": 10, "2026-09-23-2000": 10, "2026-09-24-0800": 10, "2026-09-25-0800": 10,
                "2026-09-28-0800": 10})
    t = _theater("2026-09-23-0800", "2026-09-23-2000", "2026-09-24-0800", "2026-09-25-0800", "2026-09-28-0800")
    h = heat.measure(t, eds, days=7, today=TODAY)
    assert (h.recent, h.prior) == (1, 4)                        # raw counts look like a collapse
    assert h.recent_share == h.prior_share == 0.1
    assert h.trend == "steady"


def test_a_real_share_change_heats_and_cools() -> None:
    eds = _eds({"2026-09-24-0800": 30, "2026-09-28-0800": 30})
    up = heat.measure(_theater(*["2026-09-24-0800"] * 3, *["2026-09-28-0800"] * 15), eds, days=7, today=TODAY)
    down = heat.measure(_theater(*["2026-09-24-0800"] * 15, *["2026-09-28-0800"] * 3), eds, days=7, today=TODAY)
    assert (up.trend, down.trend) == ("heating", "cooling")
    assert up.heat > down.heat                                  # same totals, the accelerating one ranks higher


def test_empty_windows_are_no_data_never_a_drop() -> None:
    # recent window has no editions at all: steady, whatever the older history says
    h = heat.measure(_theater("2026-09-24-0800", "2026-09-24-0800"), _eds({"2026-09-24-0800": 10}),
                     days=7, today=TODAY)
    assert h.trend == "steady" and h.recent == 0 and h.recent_share == 0.0
    # prior window has none: first seen in recent -> new
    new = heat.measure(_theater("2026-09-27-0800", "2026-09-28-0800"), _eds({"2026-09-27-0800": 5, "2026-09-28-0800": 5}),
                       days=7, today=TODAY)
    assert new.trend == "new" and new.prior_share == 0.0 and new.recent_share == 0.2


def test_new_theater_needs_its_first_sighting_in_the_recent_window() -> None:
    eds = _eds({"2026-09-24-0800": 10, "2026-09-28-0800": 10})
    assert heat.measure(_theater("2026-09-28-0800", "2026-09-28-0800"), eds, days=7, today=TODAY).trend == "new"
    seen_before = heat.measure(_theater("2026-09-24-0800", "2026-09-28-0800"), eds, days=7, today=TODAY)
    assert seen_before.trend == "steady" and seen_before.first_seen == "2026-09-24"


def test_clustering_drops_singletons_and_reuses_a_known_theater(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("ALGENT_INTEL_STORE", str(tmp_path))
    heat._save_registry({"thr_russia_europe": {"name": "Russia vs Europe", "description": "d"}})
    plan = heat.TheaterPlan(theaters=[
        heat.ProposedTheater(existing_id="thr_russia_europe", name="Russia's campaign on European infrastructure",
                             headline_ids=["2026-09-27-2200#1", "2026-09-27-2200#2", "2026-09-28-2200#1", "ghost#9"]),
        heat.ProposedTheater(name="Sushi", headline_ids=["2026-09-22-2200#2"])])
    board = heat.run(_ctx(plan), None, EDITIONS, model_spec=None, days=7)
    assert [t["id"] for t in board["theaters"]] == ["thr_russia_europe"]      # identity kept; sushi dropped
    assert len(board["theaters"][0]["members"]) == 3                          # the invented id ignored
    assert (tmp_path / "boards" / "2026-09-28.json").exists()


def test_a_brief_renders_with_visible_verification_and_escaped_text() -> None:
    brief = Brief(title="<script>x</script> Russia–Europe", bottom_line="Rising.",
                  escalation=Escalation(direction="rising", pace="gradual", assessment="likely to continue"),
                  timeline=[TimelineItem(date="2026-09-27", what="Warehouse arson", verification="reported",
                                         source="https://a.example")],
                  relations=[Relation(source="Russia", target="Germany", kind="sabotage")])
    page = render.render_brief(brief, theater_name="t", heat={"recent": 3, "trend": "heating"}, as_of="2026-09-28")
    assert "<script>x</script>" not in page and "&lt;script&gt;" in page
    assert "pill reported" in page and ">sabotage</text>" in page          # edge labelled on the mark
    board_page = render.render_board({"headlines": 5, "window_days": 7, "as_of": "2026-09-28", "theaters": [],
                                      "heat": []})
    assert "No theaters found" in board_page
