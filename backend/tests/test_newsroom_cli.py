"""
Offline tests for ``newsroom run`` — the staged pipeline entry point.

No graph is invoked and nothing is fetched: these cover the parts that decide
*what would run*, which is where a mistake is both easy and expensive. The pick
resolver gets the most attention because its failure mode is the nasty one — a
dropped or misaligned pick produces a successful-looking run that researches and
publishes a story nobody chose.
"""

from __future__ import annotations

import pytest

from algent_backend.cli.newsroom import pipeline
from algent_backend.data_ingestion.cli.t0 import print_menu


def _portfolio(n: int = 5) -> dict:
    return {
        "vectors": [
            {"id": f"v{i}", "title": f"story {i}", "thesis": f"thesis {i}",
             "pillars": ["politics"], "key_questions": [f"q{i}"],
             "supporting_hits": [f"h{i}"], "sources": [f"http://s/{i}"]}
            for i in range(1, n + 1)
        ],
    }


# -- the stage ladder ---------------------------------------------------------

def test_span_is_the_contiguous_range() -> None:
    assert pipeline._span("t0", "menu") == ["t0", "synthesis", "menu"]
    assert pipeline._span("menu", "menu") == ["menu"]
    assert pipeline._span("t0", "publish") == list(pipeline.STAGES)


def test_span_rejects_a_backwards_range() -> None:
    with pytest.raises(ValueError, match="is after"):
        pipeline._span("editorial", "t0")


def test_publish_is_last_so_a_default_run_ships() -> None:
    # The site is the review surface: a plain `newsroom run` must reach publish.
    assert pipeline.STAGES[-1] == "publish"
    assert "publish" in pipeline._span("t0", "publish")


# -- picks --------------------------------------------------------------------

def test_picks_resolve_to_the_numbered_items() -> None:
    got = pipeline._resolve_picks(_portfolio(), "2,4")
    assert [ns for ns, _ in got] == [[2], [4]]
    assert [g[0]["title"] for _, g in got] == ["story 2", "story 4"]


def test_plus_joins_items_into_one_article() -> None:
    """`88+114,67` is two articles, the first built from two items."""
    got = pipeline._resolve_picks(_portfolio(), "1+3,5")
    assert [ns for ns, _ in got] == [[1, 3], [5]]
    assert [v["title"] for v in got[0][1]] == ["story 1", "story 3"]
    assert len(got[1][1]) == 1


def test_pick_numbering_matches_what_the_menu_printed(capsys) -> None:
    """The numbers the operator reads must index the vector list exactly.

    This is the alignment that makes a pick mean anything at all.
    """
    portfolio = _portfolio(5)
    import sys
    pipeline.print_vector_menu(portfolio, out=sys.stdout)
    printed = capsys.readouterr().out

    for numbers, group in pipeline._resolve_picks(portfolio, "1,2,3,4,5"):
        assert f"{numbers[0]:3}. (politics)  {group[0]['title']}" in printed


def test_out_of_range_pick_is_a_hard_error() -> None:
    with pytest.raises(ValueError, match="out of range"):
        pipeline._resolve_picks(_portfolio(), "99")


def test_non_numeric_pick_is_a_hard_error() -> None:
    with pytest.raises(ValueError, match="not a menu number"):
        pipeline._resolve_picks(_portfolio(), "typhoon")


def test_empty_pick_spec_is_a_hard_error() -> None:
    with pytest.raises(ValueError, match="no items"):
        pipeline._resolve_picks(_portfolio(), " , ")


# -- seeding ------------------------------------------------------------------

def _seed(tmp_path, monkeypatch, picked, numbers, **kw):
    monkeypatch.setattr(
        "algent_backend.data_ingestion.newsroom.discovery.pipeline.pool_dir",
        lambda: tmp_path,
    )
    import json
    path = pipeline._seed_portfolio(_portfolio(), picked, numbers, **kw)
    return json.loads(path.read_text(encoding="utf-8"))


def test_seed_portfolio_carries_exactly_one_vector(tmp_path, monkeypatch) -> None:
    """Routing must have nothing else it could promote — that is what makes a pick binding."""
    vs = _portfolio()["vectors"]
    seeded = _seed(tmp_path, monkeypatch, [vs[2]], [3])

    assert len(seeded["vectors"]) == 1
    assert seeded["vectors"][0]["title"] == "story 3"
    assert seeded["picked_from_menu"] == [3]


def test_joined_vectors_merge_rather_than_dropping_one(tmp_path, monkeypatch) -> None:
    vs = _portfolio()["vectors"]
    merged = _seed(tmp_path, monkeypatch, [vs[0], vs[2]], [1, 3])["vectors"][0]

    assert merged["key_questions"] == ["q1", "q3"]
    assert merged["supporting_hits"] == ["h1", "h3"]
    assert merged["sources"] == ["http://s/1", "http://s/3"]
    assert "story 1" in merged["title"] and "story 3" in merged["title"]
    assert "thesis 1" in merged["thesis"] and "thesis 3" in merged["thesis"]
    assert "ONE story" in merged["thesis"]


def test_angle_leads_the_thesis_so_research_reads_it_first(tmp_path, monkeypatch) -> None:
    """The flag is only real if it reaches the vector the rail researches."""
    vs = _portfolio()["vectors"]
    steered = _seed(tmp_path, monkeypatch, [vs[0]], [1],
                    angle="the monopoly, not the selloff")["vectors"][0]

    assert steered["thesis"].startswith("OPERATOR STEER")
    assert "the monopoly, not the selloff" in steered["thesis"]
    assert "thesis 1" in steered["thesis"]   # the original survives underneath


def test_no_angle_leaves_the_thesis_untouched(tmp_path, monkeypatch) -> None:
    vs = _portfolio()["vectors"]
    plain = _seed(tmp_path, monkeypatch, [vs[0]], [1])["vectors"][0]
    assert plain["thesis"] == "thesis 1"


# -- operator-composed vectors ------------------------------------------------

def _items() -> list[dict]:
    return [
        {"id": "sci:a", "label": "telescope wheels failing", "pillars": ["science"],
         "evidence": [{"url": "http://a"}]},
        {"id": "sci:b", "label": "telescope sees black hole", "pillars": ["science"],
         "evidence": [{"url": "http://b"}]},
    ]


def test_compose_joins_raw_items_into_one_vector() -> None:
    """The editor's grouping is final — synthesis does not get to split it again."""
    v = pipeline.compose_vector(_items(), [88, 114], angle=None)

    assert v["supporting_hits"] == ["sci:a", "sci:b"]
    assert v["sources"] == ["http://a", "http://b"]
    assert "telescope wheels failing" in v["title"]
    assert "telescope sees black hole" in v["title"]
    assert "ONE story" in v["thesis"]
    assert "88, 114" in v["rationale"]


def test_compose_uses_the_angle_as_the_thesis() -> None:
    v = pipeline.compose_vector(_items(), [88, 114], angle="a dying telescope still working")
    assert v["thesis"] == "a dying telescope still working"


def test_composed_vector_validates_against_the_contract() -> None:
    """It goes straight to the rail, so it must be a real ResearchVector."""
    from algent_backend.agent_system.agents.discovery.portfolio import ResearchVector

    ResearchVector.model_validate(pipeline.compose_vector(_items(), [1, 2], angle="x"))
