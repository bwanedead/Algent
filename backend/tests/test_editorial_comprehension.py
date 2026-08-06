"""Tests for the comprehension_reviewer (gate C) — the naive-reader lane."""

from __future__ import annotations

from algent_backend.agent_system.agents.editorial import comprehension_loop as cl
from algent_backend.agent_system.agents.editorial.comprehension_contracts import (
    ComprehensionCheck,
    ComprehensionFinding,
)
from algent_backend.agent_system.agents.editorial.draft import ArticleDraft
from algent_backend.agent_system.foundation.models import ModelSpec
from algent_backend.agent_system.runs.context import AgentRunContext


class _Structured:
    def __init__(self, obj):
        self._o = obj

    def invoke(self, m, config=None):
        _Structured.last_message = m       # capture what the reviewer was shown
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


_SPEC = ModelSpec(provider="openai", model="gpt-5.6-luna")


def _draft(body="The FDA approved the drug. It lowers LDL-C.") -> ArticleDraft:
    return ArticleDraft(id="d", title="FDA approves drug", standfirst="a dek", body=body)


def test_reads_prose_and_flags_a_missing_ramp() -> None:
    out = ComprehensionCheck(id="", verdict="needs_ramp", findings=[
        ComprehensionFinding(id="", kind="unexplained_term", where="LDL-C",
                             issue="never says what LDL-C is", fix="add_handhold",
                             suggestion="'LDL-C — the cholesterol that drives heart risk'")])
    graph = cl.build_comprehension_reviewer_graph(_ctx(_Model(out), []), model_spec=_SPEC)
    r = graph.invoke({"draft": _draft().model_dump()})["comprehension_check"]

    assert r["verdict"] == "needs_ramp" and r["draft_id"] == "d"
    assert r["findings"][0]["id"] == "cmp_01" and r["findings"][0]["kind"] == "unexplained_term"
    assert r["reviewer"] == "comprehension_reviewer@v1"


def test_reviewer_is_shown_prose_only_never_the_evidence() -> None:
    # gate C must read cold — a reviewer that can see what the piece MEANT can't judge if it LANDED.
    cl.build_comprehension_reviewer_graph(_ctx(_Model(ComprehensionCheck(id="", verdict="clear")), []),
                                          model_spec=_SPEC).invoke({"draft": _draft().model_dump()})
    shown = _Structured.last_message[1].content   # the HumanMessage
    assert "LDL-C" in shown and "clm_" not in shown and "grounding" not in shown and "treatment" not in shown
    # friend-test + slop cut are part of the cold-read brief (not optional flavor)
    assert "FRIEND TEST" in shown and "announced_importance" in shown


def test_vague_conflict_and_announced_importance_kinds_are_valid() -> None:
    for kind, fix in (("vague_conflict", "add_handhold"), ("announced_importance", "cut")):
        f = ComprehensionFinding(id="x", kind=kind, issue="t", fix=fix)
        assert f.kind == kind


def test_clear_when_the_reader_follows_it() -> None:
    out = ComprehensionCheck(id="", verdict="clear", findings=[])
    r = cl.build_comprehension_reviewer_graph(_ctx(_Model(out), []), model_spec=_SPEC).invoke(
        {"draft": _draft().model_dump()})["comprehension_check"]
    assert r["verdict"] == "clear" and r["findings"] == []


def test_findings_coerce_the_verdict_honest() -> None:
    # a check that returns findings but a stale 'clear' verdict is corrected to needs_ramp.
    out = ComprehensionCheck(id="", verdict="clear",
                             findings=[ComprehensionFinding(id="", kind="lost_thread", issue="x")])
    r = cl.build_comprehension_reviewer_graph(_ctx(_Model(out), []), model_spec=_SPEC).invoke(
        {"draft": _draft().model_dump()})["comprehension_check"]
    assert r["verdict"] == "needs_ramp"


def test_empty_prose_skips_the_read() -> None:
    events: list = []
    graph = cl.build_comprehension_reviewer_graph(_ctx(_Model(None), events), model_spec=_SPEC)
    r = graph.invoke({"draft": _draft(body="").model_dump()})["comprehension_check"]
    assert r["verdict"] == "clear"
    assert any(et == cl.COMPREHENSION_SKIPPED for et, _ in events)


def test_comprehension_reviewer_registered() -> None:
    from algent_backend.agent_system.agents.registry import default_agent_registry
    spec = default_agent_registry().get("comprehension_reviewer")
    assert spec.default_model.provider == "meta" and spec.default_model.model == "muse-spark-1.2-contributor" and spec.family == "newsroom"
