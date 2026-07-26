"""Operator topic freeze hard-block."""

from __future__ import annotations

from algent_backend.agent_system.agents.discovery.portfolio import ResearchVector
from algent_backend.agent_system.agents.routing.contracts import RankedChoice, RouteRanking
from algent_backend.agent_system.agents.routing.promotion import apply_topic_freeze, top_vector
from algent_backend.data_ingestion.newsroom import topic_freeze as tf


def test_freeze_matches_iran_strike_phrase(tmp_path, monkeypatch) -> None:
    md = tmp_path / "topic_freeze.md"
    md.write_text("# f\n- strikes on iran\n- hormuz\n", encoding="utf-8")
    monkeypatch.setattr(tf, "_FREEZE_FILE", md)
    tf.clear_freeze_cache()
    assert tf.match_freeze("U.S. strikes on Iran continue into a second week") == "strikes on iran"
    assert tf.match_freeze("Strait of Hormuz traffic returns") == "hormuz"
    assert tf.match_freeze("Ortega ends elections in Nicaragua") is None
    tf.clear_freeze_cache()


def test_apply_topic_freeze_promotes_non_iran() -> None:
    tf.clear_freeze_cache()  # use real freeze file with iran/hormuz
    ranking = RouteRanking(choices=[
        RankedChoice(candidate_id="v01", rank=1, score=93, cooldown=False),
        RankedChoice(candidate_id="v03", rank=2, score=88, cooldown=False),
    ])
    by_id = {
        "v01": ResearchVector(
            title="U.S. strikes on Iran continue into a second week",
            thesis="multi-night strikes", vector_type="story", rationale="war",
            research_effort="deep",
        ),
        "v03": ResearchVector(
            title="Ortega says Nicaragua will no longer hold elections",
            thesis="cancels elections", vector_type="story", rationale="democracy",
            research_effort="standard",
        ),
    }
    out, hits = apply_topic_freeze(ranking, by_id)
    assert any("v01" in h for h in hits)
    assert out.choices[0].candidate_id == "v03"
    assert out.choices[0].cooldown is False
    assert top_vector(out, by_id).title.startswith("Ortega")
