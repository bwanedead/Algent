"""Tests for the drafting_gauntlet (v3a): draft -> audit -> revise until grounded."""

from __future__ import annotations

from algent_backend.agent_system.agents.editorial import draft_gauntlet as dg
from algent_backend.agent_system.runs.context import AgentRunContext


class _FakeDrafter:
    """Stands in for the drafter sub-graph; returns queued outputs across rounds."""

    def __init__(self, outputs):
        self._outputs = list(outputs)
        self.calls = 0

    def invoke(self, _state, _config=None):
        out = self._outputs[min(self.calls, len(self._outputs) - 1)]
        self.calls += 1
        return out


def _out(verdict, weak=0, missing=0, rev=1):
    return {
        "draft": {"id": "drf_x", "treatment_id": "trt_x", "profile_id": "prof_x",
                  "grounding_verdict": verdict},
        "profile": {"id": "prof_x", "revision": rev},
        "citation_report": {
            "verdict": verdict,
            "weak_load_bearing": ["clm_a"] * weak,
            "deep_read_worklist": ["src_a"] * (1 if weak else 0),
            "must_use_missing": ["clm_m"] * missing,
        },
    }


def _ctx(events):
    # model_resolver is unused — the drafter sub-graph is mocked out via build_drafter.
    return AgentRunContext(
        run_id="t", model_resolver=object(),  # type: ignore[arg-type]
        emit=lambda et, p=None: events.append((et, p or {})),
    )


def _run(monkeypatch, outputs, state):
    drafter = _FakeDrafter(outputs)
    monkeypatch.setattr(dg, "build_drafter", lambda context: drafter)
    events: list = []
    out = dg.build_drafting_gauntlet_graph(_ctx(events)).invoke(state)
    return out["gauntlet"], drafter, events


def test_gauntlet_revises_until_grounded(monkeypatch) -> None:
    # round 1 ungrounded (2 weak claims), round 2 clears -> stops at 2 rounds, clean grounded.
    g, drafter, events = _run(
        monkeypatch, [_out("needs_deep_read", weak=2), _out("grounded", rev=2)],
        {"treatment": {"id": "trt_x"}, "profile": {"id": "prof_x", "revision": 1}})
    assert g["rounds"] == 2 and drafter.calls == 2 and g["promoted"] is True
    assert g["outcome"] == "grounded" and g["barriers"] == []
    assert g["initial_weak_claims"] == 2 and g["final_weak_claims"] == 0
    assert g["ending_profile_revision"] == 2   # enrich-back landed as the read cleared the floor
    assert any(et == "drafting_gauntlet.completed" for et, _ in events)


def test_gauntlet_promotes_with_caveats_when_a_source_is_walled(monkeypatch) -> None:
    # Never clears (source is walled) but drops no required evidence -> honest-barrier path:
    # promotable with caveats, the wall reported. And it STOPS EARLY on no progress (a revision
    # that didn't shrink the problem = a wall) rather than burning all rounds.
    g, drafter, _ = _run(
        monkeypatch, [_out("needs_deep_read", weak=1)],   # always ungrounded, no must-use missing
        {"treatment": {"id": "trt_x"}, "profile": {"id": "prof_x"}})
    assert g["rounds"] == 2 and drafter.calls == 2   # one revision, no progress -> stop
    assert g["promoted"] is True and g["outcome"] == "grounded_with_caveats"
    assert g["barriers"] == ["src_a"]   # the walled source, carried with an honest caveat


def test_gauntlet_keeps_the_best_draft_not_a_regressive_last_one(monkeypatch) -> None:
    # round 1 clean-ish (1 weak, no missing); round 2 REGRESSES (drops a must-use). The gauntlet
    # must keep round 1 and promote with caveats — a bad revision can't ruin a good draft.
    g, _, _ = _run(
        monkeypatch, [_out("needs_deep_read", weak=1), _out("drops_must_use", weak=1, missing=2)],
        {"treatment": {"id": "trt_x"}, "profile": {"id": "prof_x"}})
    assert g["outcome"] == "grounded_with_caveats" and g["promoted"] is True
    assert g["final_must_use_missing"] == 0   # kept the non-regressed draft


def test_gauntlet_blocks_when_required_evidence_is_dropped(monkeypatch) -> None:
    # Dropping a must-use item is a real, fixable omission — NOT excused by the barrier path.
    g, _, _ = _run(
        monkeypatch, [_out("drops_must_use", weak=1, missing=1)],
        {"treatment": {"id": "trt_x"}, "profile": {"id": "prof_x"}})
    assert g["promoted"] is False and g["outcome"] == "blocked_omission"


def test_gauntlet_stops_at_one_round_when_grounded(monkeypatch) -> None:
    g, drafter, _ = _run(
        monkeypatch, [_out("grounded")],
        {"treatment": {"id": "trt_x"}, "profile": {"id": "prof_x"}})
    assert g["rounds"] == 1 and drafter.calls == 1 and g["promoted"] is True and g["outcome"] == "grounded"


def test_gauntlet_no_input_is_not_promoted(monkeypatch) -> None:
    g, drafter, events = _run(monkeypatch, [_out("grounded")], {})
    assert g["promoted"] is False and drafter.calls == 0
    assert any(et == "drafting_gauntlet.no_input" for et, _ in events)


def test_drafting_gauntlet_registered_with_fixture() -> None:
    from pathlib import Path

    from algent_backend.agent_system.agents.registry import default_agent_registry

    spec = default_agent_registry().get("drafting_gauntlet")
    assert spec.test_fixture is not None and spec.test_fixture.input_key is None
    assert Path(spec.test_fixture.input_file).exists()
