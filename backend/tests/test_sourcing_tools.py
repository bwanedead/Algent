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
    good = " ".join(["word"] * 150)
    assert fc._quality(good) == ("good", 150)
    assert fc._quality("please enable javascript to continue")[0] == "blocked"
    assert fc._quality("just a few words here")[0] in ("thin", "empty")
    # ~86-word podcast blurbs used to false-grade "good"; completeness floor is higher now.
    assert fc._quality(" ".join(["word"] * 86))[0] == "thin"


def test_incomplete_meta_body_is_thin_not_good() -> None:
    # Body barely longer than a rich meta description → we extracted the blurb, not the article.
    body = " ".join(["word"] * 130)
    meta = {"title": "Major Amazon earthworks study", "description": " ".join(["detail"] * 100)}
    assert fc._quality(body, meta)[0] == "thin"


def test_long_article_mentioning_captcha_is_not_flagged_blocked() -> None:
    # A real article *about* captchas is long -> "good", not a wall false-positive.
    article = "captcha " + " ".join(["analysis"] * 200)
    assert fc._quality(article)[0] == "good"


def test_fetch_stays_free_when_extraction_is_good(monkeypatch) -> None:
    monkeypatch.setenv("ALGENT_FETCH_CACHE", "0")
    monkeypatch.setenv("ALGENT_FETCH_PLAYWRIGHT", "0")
    monkeypatch.setattr(fc, "_http_get", lambda url: "<html>...</html>")
    monkeypatch.setattr(fc, "_extract", lambda html: " ".join(["word"] * 150))
    monkeypatch.setattr(fc, "_extract_meta", lambda html: {})
    called = []
    monkeypatch.setattr(fc, "_firecrawl_markdown", lambda u, k: called.append(u))
    monkeypatch.setattr(fc, "_playwright_html", lambda u: called.append(("pw", u)))

    result = fc._fetch("http://x")
    assert result["via"] == "trafilatura" and result["quality"] == "good"
    assert called == []  # never escalated — free result was good


def test_fetch_escalates_to_firecrawl_when_free_is_thin(monkeypatch) -> None:
    monkeypatch.setenv("ALGENT_FETCH_CACHE", "0")
    monkeypatch.setenv("ALGENT_FETCH_PLAYWRIGHT", "0")
    monkeypatch.setattr(fc, "_http_get", lambda url: "<html>shell</html>")
    monkeypatch.setattr(fc, "_extract", lambda html: "tiny")  # thin
    monkeypatch.setattr(fc, "_extract_meta", lambda html: {})
    monkeypatch.setattr(fc, "get_service_api_key", lambda svc: "fc-key")
    monkeypatch.setattr(fc, "_firecrawl_markdown", lambda u, k: " ".join(["full"] * 300))

    result = fc._fetch("http://x", allow_paid_fallback=True)
    assert result["via"] == "firecrawl" and result["quality"] == "good"


def test_better_candidate_prefers_quality_then_length() -> None:
    assert fc._better_candidate(
        new_quality="good", new_words=150, old_quality="thin", old_words=200,
    )
    assert not fc._better_candidate(
        new_quality="thin", new_words=200, old_quality="good", old_words=150,
    )
    assert fc._better_candidate(
        new_quality="good", new_words=200, old_quality="good", old_words=150,
    )


def test_fetch_prefers_quality_over_word_count(monkeypatch) -> None:
    """A complete 150-word article beats a longer thin navigation fragment."""
    monkeypatch.setenv("ALGENT_FETCH_CACHE", "0")
    monkeypatch.setenv("ALGENT_FETCH_PLAYWRIGHT", "0")
    thin_nav = " ".join(["link"] * 200)
    good_article = " ".join(["substance"] * 150)

    def grade(html, fallback_meta=None):
        if html and "shell" in html:
            return thin_nav, "trafilatura", "thin", 200, {}
        return good_article, "trafilatura", "good", 150, {}

    monkeypatch.setattr(fc, "_http_get", lambda url: "<html>shell</html>")
    monkeypatch.setattr(fc, "_grade_html", grade)
    monkeypatch.setattr(fc, "get_service_api_key", lambda svc: "fc-key")
    monkeypatch.setattr(fc, "_firecrawl_markdown", lambda u, k: good_article)

    result = fc._fetch("http://x", allow_paid_fallback=True)
    assert result["via"] == "firecrawl" and result["quality"] == "good"
    assert result["words"] == 150


def test_fetch_playwright_stays_off_by_default(monkeypatch) -> None:
    monkeypatch.setenv("ALGENT_FETCH_CACHE", "0")
    monkeypatch.delenv("ALGENT_FETCH_PLAYWRIGHT", raising=False)
    monkeypatch.setattr(fc, "_http_get", lambda url: "<html>shell</html>")
    monkeypatch.setattr(fc, "_extract", lambda html: " ".join(["word"] * 50))
    monkeypatch.setattr(fc, "_extract_meta", lambda html: {})
    monkeypatch.setattr(fc, "get_service_api_key", lambda svc: None)
    pw = []
    monkeypatch.setattr(fc, "_playwright_html", lambda u: pw.append(u) or None)

    result = fc._fetch("http://x", allow_paid_fallback=False)
    assert pw == []  # default off — no browser launch on a low-end laptop
    assert result["quality"] == "thin"


def test_fetch_playwright_used_when_enabled(monkeypatch) -> None:
    monkeypatch.setenv("ALGENT_FETCH_CACHE", "0")
    monkeypatch.setenv("ALGENT_FETCH_PLAYWRIGHT", "1")
    monkeypatch.setattr(fc, "_http_get", lambda url: "<html>shell</html>")
    monkeypatch.setattr(fc, "_extract", lambda html: "tiny" if "shell" in html else " ".join(["word"] * 200))
    monkeypatch.setattr(fc, "_extract_meta", lambda html: {})
    monkeypatch.setattr(fc, "get_service_api_key", lambda svc: None)
    monkeypatch.setattr(fc, "_playwright_html", lambda u: "<html>rendered article body</html>")

    result = fc._fetch("http://x", allow_paid_fallback=False)
    assert result["via"] == "playwright" and result["quality"] == "good"


def test_fetch_respects_free_only_switch(monkeypatch) -> None:
    monkeypatch.setenv("ALGENT_FETCH_CACHE", "0")
    monkeypatch.setenv("ALGENT_FETCH_PLAYWRIGHT", "0")
    monkeypatch.setattr(fc, "_http_get", lambda url: "<html>shell</html>")
    thin = " ".join(["word"] * 50)
    monkeypatch.setattr(fc, "_extract", lambda html: thin)
    monkeypatch.setattr(fc, "_extract_meta", lambda html: {})
    called = []
    monkeypatch.setattr(fc, "_firecrawl_markdown", lambda u, k: called.append(u))

    result = fc._fetch("http://x", allow_paid_fallback=False)
    assert called == []  # budget rail: never spent
    assert result["via"] == "trafilatura" and result["quality"] == "thin"
    assert result["content"] == thin


def test_fetch_raises_when_nothing_extractable(monkeypatch) -> None:
    import pytest

    monkeypatch.setenv("ALGENT_FETCH_CACHE", "0")
    monkeypatch.setenv("ALGENT_FETCH_PLAYWRIGHT", "0")
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
    x_search,
)


class _XResp:
    """A fake X API response so the gate test exercises the wired path without the network."""

    status_code = 200
    text = ""

    def json(self):
        return {
            "data": [{"id": "1", "text": "hi", "author_id": "a",
                      "public_metrics": {"like_count": 1, "retweet_count": 0}}],
            "includes": {"users": [{"id": "a", "username": "acme", "verified": True}]},
        }


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
    research.circuit.reset()
    monkeypatch.setattr(tavily, "_build", _engine(["r1", "r2"]))
    out = research._search(query="china economy")
    assert out["action"] == "search" and out["kind"] == "keyword" and out["results"] == ["r1", "r2"]
    assert out.get("provider") == "tavily"


def test_web_search_semantic_routes_to_exa(monkeypatch) -> None:
    research.circuit.reset()
    monkeypatch.setattr(exa, "_build", _engine(["s1"]))
    out = research._search(query="emerging strands", kind="semantic")
    assert out["kind"] == "semantic" and out["results"] == ["s1"]
    assert out.get("provider") == "exa"


def test_web_search_surfaces_engine_errors_cleanly(monkeypatch) -> None:
    research.circuit.reset()

    def boom():
        raise RuntimeError("provider down")

    monkeypatch.setattr(tavily, "_build", boom)
    monkeypatch.setattr(exa, "_build", boom)
    monkeypatch.setattr(research, "_invoke_provider", lambda provider, q, n: (_ for _ in ()).throw(RuntimeError("provider down")))
    out = research._search(query="q")
    assert "error" in out and "provider down" in out["error"]


def test_web_search_falls_through_on_quota_failure(monkeypatch) -> None:
    research.circuit.reset()
    calls: list[str] = []

    def invoke(provider, query, max_results):
        calls.append(provider)
        if provider == "tavily":
            raise RuntimeError("HTTP 432 quota exceeded")
        return [{"title": "ok", "url": "http://x"}]

    monkeypatch.setattr(research, "_invoke_provider", invoke)
    out = research._search(query="amazon earthworks paper")
    assert out["results"] and out["provider"] == "brave"
    assert out.get("fallback_from") == "tavily"
    assert calls[0] == "tavily" and "brave" in calls
    assert research.circuit.is_open("tavily")


def test_web_search_falls_through_on_tavily_error_payload(monkeypatch) -> None:
    """Amazon 0041 shape: Tavily returns an error dict without raising."""
    research.circuit.reset()
    calls: list[str] = []

    def invoke(provider, query, max_results):
        calls.append(provider)
        if provider == "tavily":
            return {"error": ValueError("Error 432 quota exceeded")}
        return [{"title": "recovered", "url": "http://nature.example/paper"}]

    monkeypatch.setattr(research, "_invoke_provider", invoke)
    out = research._search(query="amazon earthworks Pärssinen")
    assert out["provider"] == "brave" and out["results"]
    assert out.get("fallback_from") == "tavily"
    assert research.circuit.is_open("tavily")
    assert "432" in (out.get("error") or "") or calls[0] == "tavily"


def test_web_search_scholar_resolve(monkeypatch) -> None:
    from algent_backend.agent_system.tools.sourcing.search import scholarly

    monkeypatch.setattr(
        scholarly, "resolve",
        lambda query="", doi="": {
            "action": "scholar", "doi": doi or "10.1/x", "results": [{"title": "Paper", "doi": "10.1/x"}],
        },
    )
    out = research._search(doi="10.1038/s41586-026-10835-7")
    assert out["action"] == "scholar" and out["results"]


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
    # X is wired now: past the gate it reaches the real engine. Mock the transport so the unit
    # suite never touches the live API (and never depends on a real bearer in the env).
    monkeypatch.setattr(x_search, "_resolve_bearer", lambda: "tok")
    monkeypatch.setattr(x_search, "_get", lambda params, token: _XResp())
    token = policy.set_allowed([policy.KEYWORD, policy.READ, policy.RICH, policy.X])
    try:
        assert research._search(read_url="http://a", richness="rich")["action"] == "read"
        x = research._search(query="q", source="x")  # past the gate, into the (mocked) engine
        assert x["kind"] == "x" and x["source"] == "x" and x["results"][0]["author"] == "acme"
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


def test_rich_read_does_not_charge_when_free_path_wins(monkeypatch) -> None:
    monkeypatch.setattr(
        fc, "_fetch",
        lambda url, allow_paid_fallback=True: {
            "url": url, "content": "c", "via": "trafilatura", "quality": "good", "words": 150
        },
    )
    with policy.scoped([policy.READ, policy.RICH], paid_budget=1):
        out = research._search(read_url="http://a", richness="rich")
        assert out["via"] == "trafilatura"
        assert policy.remaining_paid_budget() == 1  # Firecrawl unused → no charge


def test_scoped_sets_and_restores_policy() -> None:
    with policy.scoped([policy.KEYWORD], paid_budget=3):
        assert policy.allowed() == frozenset({policy.KEYWORD})
        assert policy.remaining_paid_budget() == 3
    assert policy.allowed() == policy.DEFAULT_CHANNELS  # restored after the run


# -- run cost meter + dollar cap ----------------------------------------------

from algent_backend.agent_system.foundation import cost  # noqa: E402


def test_cost_estimates_model_and_calls() -> None:
    # 1M uncached in + 1M out at gpt-5.4-mini ($0.75 in, $4.50 out) = 5.25.
    assert round(cost.estimate_model_cost("gpt-5.4-mini", 1_000_000, 1_000_000), 2) == 5.25
    # Luna ordinary (under 272k cliff): 100k uncached + 50k out = 0.02 + 0.06 = 0.08
    assert round(cost.estimate_model_cost("gpt-5.6-luna", 100_000, 50_000), 4) == 0.08
    # Luna with cache: 50k uncached @0.20 + 50k cached @0.02 + 10k cache_write @0.25 + 20k out @1.20
    assert round(
        cost.estimate_model_cost(
            "gpt-5.6-luna", 50_000, 20_000,
            cached_input_tokens=50_000, cache_write_tokens=10_000,
        ),
        5,
    ) == round(0.01 + 0.001 + 0.0025 + 0.024, 5)
    # usage_metadata: input includes cached — uncached = input - cache_read
    assert round(
        cost.estimate_usage_cost(
            "gpt-5.6-luna",
            {
                "input_tokens": 100_000,
                "output_tokens": 10_000,
                "input_token_details": {"cache_read": 40_000, "cache_creation": 5_000},
            },
        ),
        5,
    ) == round(
        # 60k uncached @0.20 + 40k cached @0.02 + 5k write @0.25 + 10k out @1.20
        0.012 + 0.0008 + 0.00125 + 0.012,
        5,
    )
    # Long-context cliff: >272k input uses long rates for the whole request
    assert round(
        cost.estimate_model_cost("gpt-5.6-luna", 300_000, 10_000),
        4,
    ) == round(300_000 / 1_000_000 * 0.40 + 10_000 / 1_000_000 * 1.80, 4)
    # Grok stays in the table
    assert round(cost.estimate_model_cost("grok-4-fast", 1_000_000, 1_000_000), 2) == 0.70
    assert cost.estimate_call_cost("rich") == 0.001
    assert cost.estimate_call_cost("keyword") == 0.008
    assert cost.estimate_call_cost("unknown") == 0.0


def test_cost_cap_refuses_paid_call_when_near_limit(monkeypatch) -> None:
    monkeypatch.setattr(
        fc, "_fetch",
        lambda url, allow_paid_fallback=True: {
            "url": url, "content": "c", "via": "firecrawl", "quality": "good", "words": 50
        },
    )
    # cap below one rich call's cost ($0.001) -> the paid call is refused outright.
    with policy.scoped([policy.READ, policy.RICH], paid_budget=10), cost.scoped(0.0001, "gpt-5.4-mini"):
        out = research._search(read_url="http://a", richness="rich")
    assert "cost cap reached" in out["error"]


def test_cost_meter_accumulates_and_trips_over_cap() -> None:
    with cost.scoped(0.01, "gpt-5.4-mini"):
        assert not cost.over_cap()
        cost.add(0.02)  # blow past the cap
        assert cost.over_cap() and cost.spent_usd() == 0.02
    assert not cost.is_active()  # scope reset after the run


def test_article_scoped_nests_stage_allowances() -> None:
    with cost.article_scoped(1.0, soft_usd=1.0):  # hard=soft=$1 for this unit test
        with cost.scoped(0.4, "gpt-5.4-mini"):
            cost.add(0.3)
            assert cost.spent_usd() == 0.3  # stage-relative
            assert cost.article_spent_usd() == 0.3
        with cost.scoped(1.0, "gpt-5.4-mini"):  # stage wants $1 but only $0.70 remains
            cost.add(0.5)
            assert cost.spent_usd() == 0.5
            assert not cost.would_exceed(0.19)
            assert cost.would_exceed(0.21)  # would breach article remaining
        assert cost.article_spent_usd() == 0.8
    assert not cost.is_active()


def test_soft_cap_enters_slim_finish() -> None:
    with cost.article_scoped(3.0, soft_usd=1.0):
        cost.set_stage("profile")
        cost.add(1.0)
        assert cost.mode() == "slim_finish"
        assert cost.snapshot()["soft_cap_crossed"] is True
        assert cost.snapshot()["soft_crossed_at_stage"] == "profile"
        # Optional paid ops refuse under slim
        assert cost.try_reserve(0.01, op="rich") is None
        # Essential finish path still reserves under hard
        with cost.essential_scope():
            res = cost.try_reserve(0.05, op="model_turn", essential=True)
            assert res is not None
            cost.settle(res, 0.04)
        assert cost.article_spent_usd() == 1.04


def test_hard_cap_refuses_new_reservations() -> None:
    with cost.article_scoped(0.05, soft_usd=0.01):
        cost.add(0.05)
        assert cost.mode() == "hard_stop"
        assert cost.try_reserve(0.001, op="keyword") is None
        with cost.essential_scope():
            assert cost.try_reserve(0.001, op="hero_image", essential=True) is None


def test_reserve_settle_releases_hold() -> None:
    with cost.article_scoped(1.0, soft_usd=1.0):
        res = cost.try_reserve(0.5, op="keyword")
        assert res is not None
        assert cost.snapshot()["reserved_usd"] == 0.5
        assert cost.would_exceed(0.6)  # spent 0 + reserved 0.5 + 0.6 > 1
        cost.settle(res, 0.1)
        assert cost.article_spent_usd() == 0.1
        assert cost.snapshot()["reserved_usd"] == 0.0
        assert not cost.would_exceed(0.8)


def test_fallback_provider_contacts_are_metered(monkeypatch) -> None:
    research.circuit.reset()

    def fake_invoke(provider, q, n):
        if provider == "tavily":
            raise RuntimeError("Error 432 quota exceeded")
        return [{"title": "ok"}]

    monkeypatch.setattr(research, "_invoke_provider", fake_invoke)
    with cost.scoped(1.0, "gpt-5.4-mini"):
        out = research._search(query="china economy")
        # Tavily fail + Brave success → two keyword contacts metered
        assert out.get("provider") == "brave"
        assert abs(cost.spent_usd() - 2 * cost.estimate_call_cost("keyword")) < 1e-9
