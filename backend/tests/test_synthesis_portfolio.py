"""Portfolio coercion and empty-synthesis guards."""

from __future__ import annotations

from algent_backend.agent_system.agents.discovery.portfolio import (
    ResearchPortfolio,
    coerce_portfolio,
)
from algent_backend.agent_system.agents.discovery.synthesis import loop as syn_loop


def test_coerce_portfolio_accepts_portfolio_alias() -> None:
    raw = {
        "generated_at": "2026-01-01T00:00:00Z",
        "portfolio": [
            {
                "title": "Tuscany magma",
                "thesis": "hidden reservoir",
                "type": "story",
                "rationale": "reader gains a map of hidden systems",
                "research_effort": "deep",
                "supporting_hits": ["sci:1"],
                "pillars": "science",
                "scope": "Italy",
            }
        ],
    }
    got = coerce_portfolio(raw)
    assert got is not None
    assert len(got.vectors) == 1
    assert got.vectors[0].title == "Tuscany magma"
    assert got.vectors[0].vector_type == "story"
    assert got.vectors[0].pillars == ["science"]
    assert got.vectors[0].scope == ["Italy"]


def test_coerce_portfolio_rejects_empty() -> None:
    assert coerce_portfolio({"vectors": [], "dropped_note": "delivered 40"}) is None
    assert coerce_portfolio("nope") is None


def test_portfolio_from_model_keeps_research_portfolio() -> None:
    class _Ctx:
        def emit(self, *_a, **_k) -> None:
            return None

    p = ResearchPortfolio(generated_at="t", vectors=[])
    assert syn_loop._portfolio_from_model(p, context=_Ctx()) is p


def test_portfolio_from_model_coerces_alias() -> None:
    class _Ctx:
        def emit(self, *_a, **_k) -> None:
            return None

    raw = {
        "portfolio": [{
            "title": "Coral vortices",
            "thesis": "oxygen microflows",
            "type": "story",
            "rationale": "why heat kills the pump",
            "research_effort": "standard",
        }],
    }
    got = syn_loop._portfolio_from_model(raw, context=_Ctx())
    assert len(got.vectors) == 1
    assert got.vectors[0].title == "Coral vortices"
