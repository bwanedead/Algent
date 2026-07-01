"""
Guard ("lint"): every domain ENTITY contract must carry a stable ``id`` field.

This is the graph-ready invariant — anything that becomes a node the corpus/signal
graph can reference needs an addressable id. Ruff can't express "this Pydantic model
needs an id", so this guard test does: it fails the moment an entity contract is added
without one. When you add a new addressable entity, add it to ``ENTITY_CONTRACTS``.

Exempt by design (NOT listed): value objects (SourceSnapshot, ProfileModules) and
collections/aggregates (ResearchPortfolio, DiscoveryPool, RouteRanking) — those are
referenced through their members, not by their own id.
"""

from __future__ import annotations

import pytest

from algent_backend.agent_system.agents.discovery.portfolio import (
    ResearchPortfolio,
    ResearchVector,
    ensure_vector_ids,
    vector_id,
)
from algent_backend.agent_system.agents.editorial import (
    ArticleDraft,
    EditorialTreatment,
    PerspectiveTake,
    TreatmentConcept,
)
from algent_backend.agent_system.agents.research import (
    Claim,
    DerivedLead,
    Entity,
    SignalProfile,
    SourceArtifact,
    Thread,
)
from algent_backend.agent_system.agents.routing import RouteCandidate
from algent_backend.data_ingestion.newsroom.discovery.report import PoolItem

ENTITY_CONTRACTS = [
    PoolItem,         # t0
    ResearchVector,   # t1
    SignalProfile,    # t2
    Claim,            # ledger entity
    SourceArtifact,   # ledger entity
    Entity,           # knowledge-field node
    Thread,           # knowledge-field strand
    DerivedLead,      # backfeed entity
    RouteCandidate,   # routing entity
    EditorialTreatment,  # editorial artifact
    TreatmentConcept,    # molecule node
    PerspectiveTake,     # perspective-map node
    ArticleDraft,        # prose product
]


@pytest.mark.parametrize("model", ENTITY_CONTRACTS, ids=lambda m: m.__name__)
def test_entity_contract_has_str_id(model) -> None:
    assert "id" in model.model_fields, f"{model.__name__} must have an 'id' field (graph-ready invariant)"
    assert model.model_fields["id"].annotation is str, f"{model.__name__}.id must be a str"


def test_ensure_vector_ids_is_stable_and_idempotent() -> None:
    p = ResearchPortfolio(generated_at="t", vectors=[
        ResearchVector(title="A", thesis="ta", vector_type="story", rationale="r", research_effort="light"),
        ResearchVector(title="B", thesis="tb", vector_type="story", rationale="r", research_effort="deep"),
    ])
    once = ensure_vector_ids(p)
    assert all(v.id.startswith("vec_") for v in once.vectors)
    assert once.vectors[0].id != once.vectors[1].id            # distinct content -> distinct ids
    assert once.vectors[0].id == vector_id(p.vectors[0])       # content-derived, predictable

    # Idempotent: re-running doesn't churn already-assigned ids.
    twice = ensure_vector_ids(once)
    assert [v.id for v in twice.vectors] == [v.id for v in once.vectors]
