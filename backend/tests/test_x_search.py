"""Tests for X (Twitter) search — the direct X API v2 path behind the web_search `x` channel."""

from __future__ import annotations

from algent_backend.agent_system.tools.sourcing.search import x_search


class _Resp:
    def __init__(self, status, payload=None, text=""):
        self.status_code = status
        self._p = payload or {}
        self.text = text

    def json(self):
        return self._p


def test_x_search_shapes_results(monkeypatch) -> None:
    monkeypatch.setattr(x_search, "get_service_api_key", lambda _: "tok")
    payload = {
        "data": [{"id": "1", "text": "hello", "author_id": "a", "created_at": "2026-07-01",
                  "public_metrics": {"like_count": 5, "retweet_count": 2}}],
        "includes": {"users": [{"id": "a", "username": "acme", "verified": True}]},
    }
    monkeypatch.setattr("httpx.get", lambda *a, **k: _Resp(200, payload))

    out = x_search.x_recent_search("fed rates", max_results=10)
    assert out["source"] == "x" and out["query"] == "fed rates"
    r = out["results"][0]
    assert r["text"] == "hello" and r["author"] == "acme"
    assert r["url"] == "https://x.com/acme/status/1"
    assert r["likes"] == 5 and r["reposts"] == 2 and r["verified"] is True


def test_x_search_missing_token_is_a_clean_error(monkeypatch) -> None:
    monkeypatch.setattr(x_search, "get_service_api_key", lambda _: None)
    out = x_search.x_recent_search("q")
    assert "error" in out and "X_BEARER_TOKEN" in out["error"]


def test_x_search_non_200_is_a_clean_error(monkeypatch) -> None:
    monkeypatch.setattr(x_search, "get_service_api_key", lambda _: "tok")
    monkeypatch.setattr("httpx.get", lambda *a, **k: _Resp(429, {}, "rate limited"))
    out = x_search.x_recent_search("q")
    assert "429" in out["error"]


def test_x_provider_registered() -> None:
    from algent_backend.config.providers import PROVIDERS
    assert "x" in PROVIDERS and PROVIDERS["x"].key_env == "X_BEARER_TOKEN"


def test_research_and_drafter_granted_the_x_channel() -> None:
    from algent_backend.agent_system.agents.registry import default_agent_registry
    from algent_backend.agent_system.tools.sourcing.search import policy

    reg = default_agent_registry()
    for agent_id in ("signal_profile", "article_drafter", "enrich_primary_source"):
        assert policy.X in reg.get(agent_id).search_channels
