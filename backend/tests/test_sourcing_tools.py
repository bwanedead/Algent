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
