"""Tests for the rake stage — chunked nano triage that prunes the t0 pool."""

from __future__ import annotations

from algent_backend.agent_system.agents.discovery.rake import loop as rake_loop
from algent_backend.agent_system.agents.discovery.rake.contracts import (
    RakeChunkResult,
    RakeVerdict,
)
from algent_backend.agent_system.runs.context import AgentRunContext
from algent_backend.agent_system.tools.sourcing.search.research import WEB_SEARCH_TOOL_ID


class _Resolved:
    client = object()


class _Resolver:
    def resolve(self, _spec):
        return _Resolved()


def _ctx() -> tuple[AgentRunContext, list]:
    events: list = []
    ctx = AgentRunContext(
        run_id="t",
        model_resolver=_Resolver(),  # type: ignore[arg-type]
        tools={WEB_SEARCH_TOOL_ID: object()},
        emit=lambda et, p=None: events.append((et, p or {})),
    )
    return ctx, events


def _pool() -> dict:
    return {
        "generated_at": "now",
        "items": [
            {"id": "gkg:a", "label": "A", "channel": "gkg", "kind": "theme", "pillars": ["economics"], "signals": {}},
            {"id": "gkg:b", "label": "Spam B", "channel": "gkg", "kind": "theme", "pillars": [], "signals": {}},
            {"id": "gkg:c", "label": "C", "channel": "gkg", "kind": "theme", "pillars": [], "signals": {}},
            {"id": "x:1", "label": "X lead", "channel": "x", "kind": "trending",
             "pillars": [], "signals": {"pre_vetted": True, "lane": "ai"}},
        ],
    }


def test_run_rake_drops_only_explicit_tosses_and_passes_prevetted(monkeypatch) -> None:
    # The scout tosses b, keeps a, and never mentions c (→ fail-open keep).
    def fake_stream(agent, inputs, *, context, config):
        return RakeChunkResult(verdicts=[
            RakeVerdict(id="gkg:a", keep=True, reason="real"),
            RakeVerdict(id="gkg:b", keep=False, reason="ad spam"),
        ])

    monkeypatch.setattr(rake_loop, "stream_react_loop", fake_stream)
    monkeypatch.setattr(rake_loop, "build_react_loop", lambda *a, **k: object())

    ctx, _events = _ctx()
    pruned, summary, usd = rake_loop.run_rake(ctx, _pool(), config=None)

    ids = {it["id"] for it in pruned["items"]}
    assert ids == {"gkg:a", "gkg:c", "x:1"}  # b dropped; c fail-open; x pre-vetted
    assert summary.considered == 3 and summary.kept == 2 and summary.dropped == 1
    assert summary.pre_vetted == 1
    assert pruned["item_count"] == 3
    assert pruned["by_channel"] == {"gkg": 2, "x": 1}
    assert pruned["by_pillar"] == {"economics": 1}
    assert isinstance(usd, float)


def test_run_rake_enriches_kept_items(monkeypatch) -> None:
    # A keeper read by the scout comes back with a real headline + synopsis, which
    # replace the abstract label (original preserved in signals.t0_label).
    def fake_stream(agent, inputs, *, context, config):
        return RakeChunkResult(verdicts=[
            RakeVerdict(id="gkg:a", keep=True, headline="Real headline", synopsis="What happened."),
        ])

    monkeypatch.setattr(rake_loop, "stream_react_loop", fake_stream)
    monkeypatch.setattr(rake_loop, "build_react_loop", lambda *a, **k: object())

    pruned, summary, _usd = rake_loop.run_rake(_ctx()[0], _pool(), config=None)
    a = next(it for it in pruned["items"] if it["id"] == "gkg:a")
    assert a["label"] == "Real headline"
    assert a["signals"]["synopsis"] == "What happened."
    assert a["signals"]["t0_label"] == "A"  # original label preserved
    assert summary.enriched == 1


def test_run_rake_noop_when_all_prevetted(monkeypatch) -> None:
    monkeypatch.setattr(rake_loop, "build_react_loop", lambda *a, **k: object())
    called = {"stream": 0}
    monkeypatch.setattr(
        rake_loop, "stream_react_loop",
        lambda *a, **k: called.__setitem__("stream", called["stream"] + 1),
    )
    pool = {"generated_at": "now", "items": [
        {"id": "x:1", "label": "L", "channel": "x", "kind": "trending", "signals": {"pre_vetted": True}},
    ]}
    pruned, summary, usd = rake_loop.run_rake(_ctx()[0], pool, config=None)
    assert pruned is pool and summary.pre_vetted == 1 and usd == 0.0
    assert called["stream"] == 0  # no model call when there's nothing to rake


def test_run_rake_fail_open_when_scout_returns_nothing(monkeypatch) -> None:
    # A chunk that yields no structured verdict must drop nothing.
    monkeypatch.setattr(rake_loop, "stream_react_loop", lambda *a, **k: None)
    monkeypatch.setattr(rake_loop, "build_react_loop", lambda *a, **k: object())
    pruned, summary, _usd = rake_loop.run_rake(_ctx()[0], _pool(), config=None)
    assert summary.dropped == 0 and summary.kept == 3
    assert {it["id"] for it in pruned["items"]} == {"gkg:a", "gkg:b", "gkg:c", "x:1"}
