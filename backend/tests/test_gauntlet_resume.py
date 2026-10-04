"""A gauntlet paused between lanes resumes without buying its review or finished lanes again."""

from __future__ import annotations

from typing import Any

from algent_backend.agent_system.agents.gauntlet import orchestrator as orch
from algent_backend.agent_system.runs.context import AgentRunContext


class _Graph:
    def __init__(self, fn):
        self.fn = fn

    def invoke(self, state, _config=None):
        return self.fn(state)


def test_a_resumed_gauntlet_skips_what_it_already_paid_for(monkeypatch) -> None:
    calls: list[str] = []
    review = {"verdict": "needs_verification", "findings": [
        {"id": "f1", "lane": "primary_source"}, {"id": "f2", "lane": "counter_perspective"}]}

    def reviewer(ctx):
        return _Graph(lambda s: calls.append("review") or {"review": {**review, "verdict": "mature"}})

    def lane(name):
        mod = type("M", (), {})()
        mod.build_graph = lambda ctx: _Graph(
            lambda s: calls.append(name) or {"profile": {**s["profile"], "revision": 4}})
        return mod

    monkeypatch.setattr(orch, "build_reviewer", reviewer)
    monkeypatch.setattr(orch, "_LANE_MODULES", [
        ("primary_source", lane("primary_source")),
        ("counter_perspective", lane("counter_perspective"))])
    ctx = AgentRunContext(run_id="t", model_resolver=object(), emit=lambda *a, **k: None)  # type: ignore[arg-type]

    out: dict[str, Any] = orch.build_gauntlet_graph(ctx).invoke({
        "profile": {"id": "p", "revision": 3},
        "progress": {"review": review, "lanes_done": ["primary_source"], "start_rev": 2},
    })
    # No first review, no primary_source lane — only the lane still owed, then the re-review.
    assert calls == ["counter_perspective", "review"]
    report = out["gauntlet"]
    assert report["lanes_run"] == ["primary_source", "counter_perspective"]
    assert report["starting_revision"] == 2 and report["final_verdict"] == "mature"
