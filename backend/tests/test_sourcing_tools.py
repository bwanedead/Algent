"""
Tests for the sourcing portfolio and key management (Slice 5).

Offline — specs and registry only; no vendor is ever built, no network, no keys.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from algent_backend.agent_system.agents.agent_spec import AgentSpec
from algent_backend.agent_system.tools.registry import default_tool_registry
from algent_backend.agent_system.tools.spec import GLOBAL_SCOPE, ToolSpec
from algent_backend.config.env_file import load_env_file

EXPECTED_TOOLS = {
    "web_search": "search",
    "brave_search": "search",
    "semantic_search": "search",
    "xai_x_search": "social",
    "fetch_content": "depth",
    "rss_feed": "discovery",
    "gdelt_events": "discovery",
    "news_feeds": "discovery",
}

# Vendor modules that must only load when a tool is actually built.
VENDOR_MODULES = ("langchain_tavily", "langchain_exa", "trafilatura", "feedparser")


def test_default_registry_ships_the_full_portfolio() -> None:
    registry = default_tool_registry()
    by_id = {spec.tool_id: spec for spec in registry.list()}

    assert set(by_id) == set(EXPECTED_TOOLS)
    for tool_id, channel in EXPECTED_TOOLS.items():
        assert by_id[tool_id].channel == channel
        assert by_id[tool_id].scope == GLOBAL_SCOPE
        assert callable(by_id[tool_id].build)


def test_registering_portfolio_does_not_import_vendor_sdks() -> None:
    """Specs must stay metadata-only until build() — listing is not building."""
    for mod in VENDOR_MODULES:
        sys.modules.pop(mod, None)

    registry = default_tool_registry()
    registry.list()

    loaded = [mod for mod in VENDOR_MODULES if mod in sys.modules]
    assert not loaded, f"vendor SDKs imported without build(): {loaded}"


def test_portfolio_resolves_for_news_agent() -> None:
    agent = AgentSpec(
        agent_id="news_brief",
        name="News Brief",
        runtime="langgraph",
        build_graph=lambda _context: None,
        family="news",
        tool_ids=("web_search",),
    )
    resolved = default_tool_registry().resolve_for(agent)
    assert {spec.tool_id for spec in resolved} == set(EXPECTED_TOOLS)


def test_channel_defaults_to_general() -> None:
    spec = ToolSpec(tool_id="t", name="t", description="", scope=GLOBAL_SCOPE, build=lambda: None)
    assert spec.channel == "general"


def test_env_file_loads_without_overriding_environment(tmp_path: Path, monkeypatch: object) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "# comment\n"
        "\n"
        "ALGENT_TEST_NEW_KEY=from-file\n"
        'ALGENT_TEST_EXISTING_KEY="file-should-lose"\n'
        "not a kv line\n",
        encoding="utf-8",
    )
    os.environ.pop("ALGENT_TEST_NEW_KEY", None)
    os.environ["ALGENT_TEST_EXISTING_KEY"] = "env-wins"
    try:
        applied = load_env_file(env_file)

        assert applied == 1
        assert os.environ["ALGENT_TEST_NEW_KEY"] == "from-file"  # quotes stripped, value set
        assert os.environ["ALGENT_TEST_EXISTING_KEY"] == "env-wins"
    finally:
        os.environ.pop("ALGENT_TEST_NEW_KEY", None)
        os.environ.pop("ALGENT_TEST_EXISTING_KEY", None)


def test_missing_env_file_is_fine(tmp_path: Path) -> None:
    assert load_env_file(tmp_path / "nope.env") == 0


# -- fetch_content cheap-first ladder -----------------------------------------

from algent_backend.agent_system.tools.sourcing.depth import fetch_content as fc  # noqa: E402


def test_quality_grades_content() -> None:
    assert fc._quality(None) == ("empty", 0)
    assert fc._quality("  ") == ("empty", 0)
    good = " ".join(["word"] * 100)
    assert fc._quality(good) == ("good", 100)
    assert fc._quality("please enable javascript to continue")[0] == "blocked"
    assert fc._quality("just a few words here")[0] == "thin"


def test_long_article_mentioning_captcha_is_not_flagged_blocked() -> None:
    # A real article *about* captchas is long -> "good", not a wall false-positive.
    article = "captcha " + " ".join(["analysis"] * 200)
    assert fc._quality(article)[0] == "good"


def test_fetch_stays_free_when_extraction_is_good(monkeypatch) -> None:
    monkeypatch.setattr(fc, "_http_get", lambda url: "<html>...</html>")
    monkeypatch.setattr(fc, "_extract", lambda html: " ".join(["word"] * 120))
    called = []
    monkeypatch.setattr(fc, "_firecrawl_markdown", lambda u, k: called.append(u))

    result = fc._fetch("http://x")
    assert result["via"] == "trafilatura" and result["quality"] == "good"
    assert called == []  # never escalated — free result was good


def test_fetch_escalates_to_firecrawl_when_free_is_thin(monkeypatch) -> None:
    monkeypatch.setattr(fc, "_http_get", lambda url: "<html>shell</html>")
    monkeypatch.setattr(fc, "_extract", lambda html: "tiny")  # thin
    monkeypatch.setattr(fc, "get_service_api_key", lambda svc: "fc-key")
    monkeypatch.setattr(fc, "_firecrawl_markdown", lambda u, k: " ".join(["full"] * 300))

    result = fc._fetch("http://x", allow_paid_fallback=True)
    assert result["via"] == "firecrawl" and result["quality"] == "good"


def test_fetch_respects_free_only_switch(monkeypatch) -> None:
    monkeypatch.setattr(fc, "_http_get", lambda url: "<html>shell</html>")
    monkeypatch.setattr(fc, "_extract", lambda html: "tiny")
    called = []
    monkeypatch.setattr(fc, "_firecrawl_markdown", lambda u, k: called.append(u))

    result = fc._fetch("http://x", allow_paid_fallback=False)
    assert called == []  # budget rail: never spent
    assert result["via"] == "trafilatura" and result["content"] == "tiny"


def test_fetch_raises_when_nothing_extractable(monkeypatch) -> None:
    import pytest

    monkeypatch.setattr(fc, "_http_get", lambda url: None)
    monkeypatch.setattr(fc, "get_service_api_key", lambda svc: None)
    with pytest.raises(RuntimeError):
        fc._fetch("http://blocked")


# -- web_search unified research facade ----------------------------------------

from algent_backend.agent_system.tools.sourcing.search import (  # noqa: E402
    exa,
    policy,
    research,
    tavily,
)


def _engine(result):
    return lambda: type("E", (), {"invoke": lambda self, args: result})()


def test_web_search_reads_url_free_by_default(monkeypatch) -> None:
    seen = {}

    def fake_fetch(url, allow_paid_fallback=True):
        seen["paid"] = allow_paid_fallback
        return {"url": url, "content": "body", "via": "trafilatura", "quality": "good", "words": 90}

    monkeypatch.setattr(fc, "_fetch", fake_fetch)
    out = research._search(read_url="http://a")
    assert out["action"] == "read" and out["via"] == "trafilatura"
    assert seen["paid"] is False  # free unless richness="rich"


def test_web_search_rich_read_allows_paid_fallback(monkeypatch) -> None:
    seen = {}

    def fake_fetch(url, allow_paid_fallback=True):
        seen["paid"] = allow_paid_fallback
        return {"url": url, "content": "b", "via": "firecrawl", "quality": "good", "words": 40}

    monkeypatch.setattr(fc, "_fetch", fake_fetch)
    token = policy.set_allowed([policy.READ, policy.RICH])  # grant the paid channel
    try:
        research._search(read_url="http://a", richness="rich")
    finally:
        policy.reset_allowed(token)
    assert seen["paid"] is True


def test_web_search_keyword_routes_to_tavily(monkeypatch) -> None:
    monkeypatch.setattr(tavily, "_build", _engine(["r1", "r2"]))
    out = research._search(query="china economy")
    assert out["action"] == "search" and out["kind"] == "keyword" and out["results"] == ["r1", "r2"]


def test_web_search_semantic_routes_to_exa(monkeypatch) -> None:
    monkeypatch.setattr(exa, "_build", _engine(["s1"]))
    out = research._search(query="emerging strands", kind="semantic")
    assert out["kind"] == "semantic" and out["results"] == ["s1"]


def test_web_search_surfaces_engine_errors_cleanly(monkeypatch) -> None:
    def boom():
        raise RuntimeError("provider down")

    monkeypatch.setattr(tavily, "_build", boom)
    out = research._search(query="q")
    assert "error" in out and "provider down" in out["error"]


# -- per-channel permission gates ---------------------------------------------


def test_gate_blocks_paid_channels_by_default() -> None:
    # Default policy = free/cheap only; paid rich + x are hard-refused.
    rich = research._search(read_url="http://a", richness="rich")
    assert rich["error"].startswith("channel 'rich'") and "rich" not in rich["permitted_channels"]
    x = research._search(query="q", source="x")
    assert x["error"].startswith("channel 'x'")


def test_gate_allows_paid_channels_when_granted(monkeypatch) -> None:
    monkeypatch.setattr(
        fc, "_fetch",
        lambda url, allow_paid_fallback=True: {
            "url": url, "content": "c", "via": "firecrawl", "quality": "good", "words": 50
        },
    )
    token = policy.set_allowed([policy.KEYWORD, policy.READ, policy.RICH, policy.X])
    try:
        assert research._search(read_url="http://a", richness="rich")["action"] == "read"
        assert "not wired" in research._search(query="q", source="x")["error"]  # past the gate
    finally:
        policy.reset_allowed(token)


def test_gate_blocks_semantic_when_restricted() -> None:
    token = policy.set_allowed([policy.KEYWORD, policy.READ])  # no semantic
    try:
        out = research._search(query="q", kind="semantic")
        assert out["error"].startswith("channel 'semantic'")
    finally:
        policy.reset_allowed(token)


def test_policy_normalize_drops_unknown_and_defaults() -> None:
    assert policy.normalize(None) == policy.DEFAULT_CHANNELS
    assert policy.normalize(["x", "bogus"]) == frozenset({"x"})


def test_paid_budget_caps_paid_calls(monkeypatch) -> None:
    monkeypatch.setattr(
        fc, "_fetch",
        lambda url, allow_paid_fallback=True: {
            "url": url, "content": "c", "via": "firecrawl", "quality": "good", "words": 50
        },
    )
    with policy.scoped([policy.READ, policy.RICH], paid_budget=1):
        first = research._search(read_url="http://a", richness="rich")
        second = research._search(read_url="http://b", richness="rich")
    assert first["action"] == "read"  # first paid call within budget
    assert "budget exhausted" in second["error"]  # second hard-stopped by the cap


def test_scoped_sets_and_restores_policy() -> None:
    with policy.scoped([policy.KEYWORD], paid_budget=3):
        assert policy.allowed() == frozenset({policy.KEYWORD})
        assert policy.remaining_paid_budget() == 3
    assert policy.allowed() == policy.DEFAULT_CHANNELS  # restored after the run
