"""X seed hydration for research — restore x.com URLs from t0 supporting hits."""

from __future__ import annotations

from algent_backend.agent_system.agents.research.x_seeds import (
    hydrate_vector_with_x_seeds,
    is_x_url,
    x_url_from_hit_id,
)
from algent_backend.agent_system.agents.research.messages import build_vector_message


def test_x_url_from_hit_id() -> None:
    assert x_url_from_hit_id("x:x_news:2079576369290228200") == (
        "https://x.com/i/web/status/2079576369290228200"
    )
    assert x_url_from_hit_id("gkg:story:foo") is None


def test_hydrate_prefers_pool_evidence_url() -> None:
    vector = {
        "id": "v03",
        "title": "Ortega elections",
        "supporting_hits": ["x:x_news:2079576369290228200"],
        "sources": [
            "https://www.npr.org/2026/07/21/nx-s1-5902228/nicaragua-ortega-no-elections",
        ],
    }
    pool = {
        "items": [{
            "id": "x:x_news:2079576369290228200",
            "channel": "x",
            "evidence": [{
                "url": "https://x.com/SecRubio/status/2079576369290228200",
                "title": "Ortega",
            }],
        }],
    }
    out = hydrate_vector_with_x_seeds(vector, pool)
    assert out["x_primary"] is True
    assert out["sources"][0] == "https://x.com/SecRubio/status/2079576369290228200"
    assert "npr.org" in out["sources"][1]
    assert out["x_seed_urls"][0].startswith("https://x.com/")


def test_hydrate_reconstructs_status_url_without_pool() -> None:
    vector = {
        "supporting_hits": ["x:x_novelty:1234567890123456789"],
        "sources": [],
    }
    out = hydrate_vector_with_x_seeds(vector, None)
    assert out["x_seed_urls"] == ["https://x.com/i/web/status/1234567890123456789"]


def test_research_message_requires_x_duty_when_seeded() -> None:
    vector = hydrate_vector_with_x_seeds({
        "id": "v1",
        "title": "Ortega",
        "thesis": "elections end",
        "rationale": "auth",
        "supporting_hits": ["x:x_news:1"],
        "sources": ["https://x.com/a/status/1"],
        "key_questions": [],
    }, None)
    msg = build_vector_message(vector)
    assert "X PRIMARY FOOTING" in msg
    assert 'source="x"' in msg or "source=\\\"x\\\"" in msg or "source=\"x\"" in msg
    assert is_x_url("https://x.com/a/status/1")
