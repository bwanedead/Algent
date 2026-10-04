"""Radar enrichment — the search pass that turns a wire line into a post, or drops it."""

from __future__ import annotations

from algent_backend.agent_system.agents.radar.contracts import RadarPost, stamp
from algent_backend.agent_system.agents.radar.enrich import (
    EnrichedPost,
    enrich,
    looks_like_wire_pr,
)
from algent_backend.agent_system.agents.radar.sweep import sweep_pool
from algent_backend.cli.newsroom import radar as radar_cli
from algent_backend.publishing.x_client import CARD


def test_stamp_peels_a_lane_label_and_never_adds_one() -> None:
    """Radar is the internal name. The tweet is the news item, nothing in front of it."""
    assert stamp("A 7.6 quake hit off Colombia's coast.") == (
        "A 7.6 quake hit off Colombia's coast.")
    assert stamp("Radar: the model prefixed it itself.") == "the model prefixed it itself."
    assert stamp("  RADAR: already stamped  ") == "already stamped"
    assert stamp("Radar: Radar: Eleven people were charged in Houston.") == (
        "Eleven people were charged in Houston.")


def test_a_failed_lookup_is_a_drop_not_a_crash(monkeypatch) -> None:
    from algent_backend.agent_system.agents.radar import enrich as en

    class _Resolver:
        def resolve(self, _spec):
            raise RuntimeError("no model")

    out = en.enrich("a wire line", resolver=_Resolver())
    assert out.verdict == "drop" and "lookup failed" in out.reason


def test_overlong_text_is_cut_to_a_timeline_card(monkeypatch) -> None:
    """A body past the card budget is rewritten rather than shipped over-length."""
    from algent_backend.agent_system.agents.radar import enrich as en

    long = "x" * (CARD + 40)
    shortened = "Tornadoes in Illinois on Monday killed three."

    class _Structured:
        def invoke(self, _messages):
            return EnrichedPost(verdict="post", text=long, added="numbers", sources=["http://x"])

    class _Model:
        def bind_tools(self, _tools):
            return self

        def with_structured_output(self, _schema):
            return _Structured()

        def invoke(self, _messages):
            return type("R", (), {"content": shortened})()

    class _Resolver:
        def resolve(self, _spec):
            return type("R", (), {"client": _Model()})()

    import algent_backend.agent_system.foundation.models.budget_gate as bg
    monkeypatch.setattr(bg, "gate_chat_model", lambda client: client)

    out = en.enrich("storms", resolver=_Resolver())
    assert out.verdict == "post"
    assert out.text == shortened
    assert len(stamp(out.text)) <= CARD


def test_pr_wires_are_recognized_without_a_search() -> None:
    """The OPC Energy Q2 print was exact, recent, and worthless. Catch the mill, skip the lookup."""
    assert looks_like_wire_pr(
        "OPC Energy reports strong quarter\nURL: http://www.prnewswire.com/news-releases/opc")
    assert looks_like_wire_pr("https://www.businesswire.com/news/home/123")
    assert not looks_like_wire_pr("https://www.reuters.com/world/asia/tencent-q2")


def test_enrich_drops_a_pr_wire_without_searching() -> None:
    """A promotional mill must not cost a search to reject."""
    out = enrich(
        "OPC Energy reports strong quarter",
        url="http://www.prnewswire.com/news-releases/opc",
    )
    assert out.verdict == "drop" and out.reason == "promotional wire"


def test_a_beat_id_that_is_a_url_is_handed_to_search() -> None:
    item = {
        "id": "beat:http://www.prnewswire.com/news-releases/opc-energy",
        "label": "OPC Energy reports strong second quarter",
        "evidence": [],
    }
    assert radar_cli._item_url(item).startswith("http://www.prnewswire.com")
    assert looks_like_wire_pr(radar_cli._item_url(item))


def test_sweep_keeps_candidates_with_empty_text() -> None:
    """The sweep selects; enrichment writes. Empty text is the expected candidate shape."""
    from algent_backend.agent_system.agents.radar.contracts import RadarSweep

    result = RadarSweep(posts=[
        RadarPost(source_key="k1", rationale="a quake"),
        RadarPost(source_key="k1", rationale="duplicate key"),
        RadarPost(source_key="k2", text="ignored", rationale="also a candidate"),
    ])

    class _Model:
        def with_structured_output(self, _schema):
            return self

        def invoke(self, _messages):
            return result

    class _Resolver:
        def resolve(self, _spec):
            return type("R", (), {"client": _Model()})()

    out = sweep_pool({"items": [
        {"id": "k1", "label": "quake", "channel": "gkg"},
        {"id": "k2", "label": "other", "channel": "gkg"},
    ]}, resolver=_Resolver())
    assert [p.source_key for p in out.posts] == ["k1", "k2"]
    assert out.posts[0].text == ""
