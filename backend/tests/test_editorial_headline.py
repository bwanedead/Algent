"""Tests for the headline_writer (a truthful post-draft title + dek)."""

from __future__ import annotations

from algent_backend.agent_system.agents.editorial import headline_loop
from algent_backend.agent_system.agents.editorial.draft import ArticleDraft
from algent_backend.agent_system.agents.editorial.headline_contracts import Headline
from algent_backend.agent_system.foundation.models import ModelSpec
from algent_backend.agent_system.runs.context import AgentRunContext


class _Structured:
    def __init__(self, obj):
        self._o = obj

    def invoke(self, _m, config=None):
        return self._o


class _Model:
    def __init__(self, obj):
        self._o = obj

    def with_structured_output(self, _s):
        return _Structured(self._o)


class _Resolver:
    def __init__(self, m):
        self._m = m

    def resolve(self, _s):
        return type("R", (), {"client": self._m})()


def _ctx(model, events):
    return AgentRunContext(
        run_id="t", model_resolver=_Resolver(model),  # type: ignore[arg-type]
        emit=lambda et, p=None: events.append((et, p or {})),
    )


def _spec():
    return ModelSpec(provider="openai", model="gpt-5.6-luna")


def test_headline_writer_produces_title_and_dek() -> None:
    hl = Headline(title="Fed holds, but a hike tail is still live", standfirst="the nuance")
    events: list = []
    graph = headline_loop.build_headline_writer_graph(_ctx(_Model(hl), events), model_spec=_spec())
    out = graph.invoke({"draft": ArticleDraft(id="d", title="working", body="the piece").model_dump()})
    assert out["headline"]["title"] == "Fed holds, but a hike tail is still live"
    assert out["headline"]["standfirst"] == "the nuance"
    assert any(et == "headline.completed" for et, _ in events)


def test_headline_writer_no_draft_is_empty() -> None:
    graph = headline_loop.build_headline_writer_graph(_ctx(_Model(Headline()), []), model_spec=_spec())
    assert graph.invoke({})["headline"]["title"] == ""


def test_headline_writer_registered_on_nano() -> None:
    from algent_backend.agent_system.agents.registry import default_agent_registry

    spec = default_agent_registry().get("headline_writer")
    assert spec.tool_ids == () and spec.default_model.provider == "meta" and spec.default_model.model == "muse-spark-1.2-contributor"
