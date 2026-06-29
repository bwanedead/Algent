"""Tests for the signal_profile agent graph (v2) — t1 vector -> t2 profile."""

from __future__ import annotations

from algent_backend.agent_system.agents.research import loop as profile_loop
from algent_backend.agent_system.agents.research.profile import (
    Claim,
    SignalProfile,
    SourceArtifact,
)
from algent_backend.agent_system.foundation.models import ModelSpec
from algent_backend.agent_system.runs.context import AgentRunContext


class _Resolver:
    def resolve(self, _spec):
        return type("R", (), {"client": object()})()


def _ctx(events: list) -> AgentRunContext:
    return AgentRunContext(
        run_id="t",
        model_resolver=_Resolver(),  # type: ignore[arg-type]
        tools={"web_search": object()},
        emit=lambda et, p=None: events.append((et, p or {})),
    )


def _graph(context, monkeypatch, produced):
    monkeypatch.setattr(profile_loop, "build_react_loop", lambda *a, **k: object())
    monkeypatch.setattr(profile_loop, "stream_react_loop", lambda *a, **k: produced)
    return profile_loop.build_profile_graph(
        context, model_spec=ModelSpec(provider="openai", model="gpt-5.4-mini"),
        tool_ids=("web_search",), system_prompt="sys",
        search_channels=("keyword", "read"), paid_budget=2, cost_cap_usd=1.0,
    )


def test_profile_graph_produces_persists_and_writes_briefing(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("ALGENT_PROFILE_STORE", str(tmp_path))
    produced = SignalProfile(
        id="model-set", title="Fed path under inflation pressure", profile_status="complete",
        source_ledger=[SourceArtifact(id="s1", url="https://reuters.com/fed", source_type="secondary")],
        claim_ledger=[Claim(id="c1", text="Fed held rates", status="confirmed", supported_by=["s1"])],
        output_recommendations=["article"],
    )
    events: list = []
    graph = _graph(_ctx(events), monkeypatch, produced)

    out = graph.invoke({"vector": {"id": "vec_bd540e7822", "title": "Fed path", "thesis": "x"}})

    prof = out["profile"]
    assert prof["id"] == "prof_bd540e7822"               # harness id, not the model's
    assert prof["parent_vector_id"] == "vec_bd540e7822"
    assert prof["source_ledger"][0]["id"].startswith("src_")     # content-addressed
    assert prof["claim_ledger"][0]["supported_by"] == [prof["source_ledger"][0]["id"]]  # ref rewritten
    assert (tmp_path / "prof_bd540e7822.json").exists()  # persisted to the ProfileStore
    done = next(p for et, p in events if et == "profile.completed")
    assert done["status"] == "complete" and "threads" in done


def test_profile_graph_no_vector_is_insufficient_not_failure(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("ALGENT_PROFILE_STORE", str(tmp_path))
    graph = _graph(_ctx([]), monkeypatch, None)
    out = graph.invoke({})
    assert out["profile"]["profile_status"] == "insufficient_evidence"  # valid, not a crash


def test_signal_profile_registered_with_fixture() -> None:
    from pathlib import Path

    from algent_backend.agent_system.agents.registry import default_agent_registry

    spec = default_agent_registry().get("signal_profile")
    assert spec.tool_ids == ("web_search",)
    assert spec.test_fixture is not None and spec.test_fixture.input_key == "vector"
    assert Path(spec.test_fixture.input_file).exists()  # the banked selected vector
