"""The forecast ledger, continuity and pulse tagging — no network, no model."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from algent_backend.agent_system.agents.intel import brief as br
from algent_backend.agent_system.agents.intel import desk, forecasts, render
from algent_backend.agent_system.agents.intel.contracts import Brief, Change, Indicator, Judgment, Theater
from algent_backend.agent_system.agents.pulse import PulseStore
from algent_backend.agent_system.agents.pulse.contracts import Pulse, PulseDefinition, Situation
from algent_backend.publishing import intel_page


def _j(statement: str, p: int, horizon: str = "2026-10-15") -> Judgment:
    return Judgment(statement=statement, probability=p, horizon=horizon, resolves_yes_if="y", resolves_no_if="n")


class _Fake:
    def __init__(self, out):
        self.out = out

    def with_structured_output(self, _s):
        return self

    def invoke(self, *_a, **_k):
        return self.out


def _ctx(out):
    return type("X", (), {"model_resolver": type("R", (), {
        "resolve": lambda _s, _spec: type("C", (), {"client": _Fake(out)})()})()})()


def test_ledger_records_idempotently_and_projects_resolutions(tmp_path) -> None:
    ids = forecasts.record("2026-09-30-a", "thr_a", [_j("A happens", 70), _j("B happens", 30)], root=tmp_path)
    assert len(ids) == 2 and forecasts.record("2026-09-30-a", "thr_a", [_j("A happens", 70)], root=tmp_path) == []
    assert forecasts.resolve(ids[0], "yes", "it did", root=tmp_path, at="2026-10-01")
    assert forecasts.resolve(ids[0], "no", "correction", root=tmp_path, at="2026-10-02")     # latest line wins
    assert not forecasts.resolve("fc_ghost", "yes", "x", root=tmp_path)
    assert not forecasts.resolve(ids[1], "maybe", "x", root=tmp_path)
    by_id = {f["id"]: f for f in forecasts.current(tmp_path)}
    assert by_id[ids[0]]["status"] == "no" and by_id[ids[0]]["evidence"] == "correction"
    assert by_id[ids[1]]["status"] == "open"
    assert len((tmp_path / "forecasts.jsonl").read_text().splitlines()) == 4


def test_scorecard_brier_and_calibration(tmp_path) -> None:
    ids = forecasts.record("s", "t", [_j("a", 90), _j("b", 90), _j("c", 20), _j("d", 60), _j("e", 50)], root=tmp_path)
    for fid, outcome in zip(ids, ("yes", "no", "no", "void"), strict=False):
        forecasts.resolve(fid, outcome, "e", root=tmp_path)
    card = forecasts.scorecard(tmp_path)
    assert card["resolved"] == 3 and card["void"] == 1 and card["open"] == 1
    assert card["brier"] == round((0.01 + 0.81 + 0.04) / 3, 4)
    assert card["calibration"] == [{"range": "20-29", "count": 1, "hit_rate": 0.0},
                                   {"range": "90-99", "count": 2, "hit_rate": 0.5}]
    assert forecasts.scorecard(tmp_path / "none")["brier"] is None


def test_due_is_past_horizon_or_the_theater_being_briefed(tmp_path) -> None:
    ids = forecasts.record("s", "thr_a", [_j("past", 50, "2026-09-01"), _j("future", 50, "2026-12-01")], root=tmp_path)
    forecasts.record("s2", "thr_b", [_j("other future", 50, "2026-12-01")], root=tmp_path)
    assert [f["id"] for f in forecasts.due("2026-09-30", root=tmp_path)] == [ids[0]]
    assert {f["statement"] for f in forecasts.due("2026-09-30", theater_id="thr_a", root=tmp_path)} == {"past", "future"}
    forecasts.resolve(ids[0], "no", "e", root=tmp_path)
    assert forecasts.due("2026-09-30", root=tmp_path) == []


def test_resolver_accepts_only_due_ids_with_evidence(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("ALGENT_INTEL_STORE", str(tmp_path))
    a, b = forecasts.record("s", "thr_a", [_j("past", 50, "2026-09-01"), _j("later", 50, "2026-12-01")])
    plan = forecasts.ResolutionPlan(resolutions=[
        forecasts.Resolution(id=a, outcome="yes", evidence="reported on 09-20"),
        forecasts.Resolution(id=b, outcome="yes", evidence="not due and no theater"),
        forecasts.Resolution(id="fc_ghost", outcome="no", evidence="x"),
        forecasts.Resolution(id=a, outcome="no", evidence="second verdict")])
    out = forecasts.resolve_due(_ctx(plan), None, None, "evidence", as_of="2026-09-30")
    assert out == [{"id": a, "outcome": "yes"}]
    assert {f["id"]: f["status"] for f in forecasts.current()} == {a: "yes", b: "open"}
    assert forecasts.resolve_due(_ctx(plan), None, None, "  ", as_of="2026-09-30") == []


def test_continuity_picks_the_newest_previous_brief_of_the_same_theater(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("ALGENT_INTEL_STORE", str(tmp_path))
    t = Theater(id="thr_a", name="A")
    for as_of, title in (("2026-09-20", "old"), ("2026-09-27", "newest"), ("2026-09-30", "today")):
        desk.persist_brief(Brief(title=title, bottom_line="b"), as_of=as_of, theater=t, heat={}, researched=False)
    desk.persist_brief(Brief(title="elsewhere", bottom_line="b"), as_of="2026-09-29",
                       theater=Theater(id="thr_b", name="B"), heat={}, researched=False)
    assert desk.previous_brief("thr_a", before_slug="2026-09-30-a")["title"] == "newest"
    assert desk.previous_brief("thr_zzz") is None and desk.previous_brief("") is None
    digest = br.previous_digest({"as_of": "x", "title": "T", "bottom_line": "BL", "escalation": {"direction": "rising"},
                                 "indicators": [{"status": "emerging", "signal": "SIG"}],
                                 "judgments": [{"probability": 70, "horizon": "2026-10-01", "statement": "J"}]})
    assert "BL" in digest and "[emerging] SIG" in digest and "70% by 2026-10-01: J" in digest


def test_pulse_names_are_filtered_to_the_table_and_changes_need_a_previous_brief(tmp_path) -> None:
    store = PulseStore(tmp_path / "pulses")
    store.save_situation(Situation(id="sit_a", title="Sit A", status="active"))
    store.save_situation(Situation(id="sit_x", title="Gone", status="merged"))
    for pid, sid, status in (("Alpha", "sit_a", "active"), ("Dormant", "sit_a", "dormant"), ("Orphan", "sit_x", "active")):
        store.create_pulse(Pulse(id=f"pls_{pid}", situation_id=sid, name=pid, status=status,
                                 definitions=[PulseDefinition(question="q", low_end="l", high_end="h")]))
    table = br.pulse_catalog(store)
    assert list(table) == ["Alpha"] and "Sit A | unassessed | unassessed" in table["Alpha"]
    raw = Brief(title="t", bottom_line="b", pulses=["alpha", "Invented", "Dormant", "Alpha"],
                changes=[Change(what="w", kind="new")],
                judgments=[_j("ok", 50), _j("bad date", 50, "soon")] + [_j(f"j{i}", 50) for i in range(5)])
    out = br.normalise(raw, pulse_table=table, has_previous=False)
    assert out.pulses == ["Alpha"] and out.changes == [] and len(out.judgments) == 4
    assert [j.statement for j in out.judgments][:2] == ["ok", "j0"]
    assert _j("x", 150).probability == 99 and _j("x", 0).probability == 1


def test_snapshot_carries_the_forecast_section_and_brief_renders_new_sections(tmp_path) -> None:
    intel = tmp_path / "intel"
    ids = forecasts.record("s1", "thr_a", [_j("late", 80, "2026-11-01"), _j("soon", 60, "2026-10-10"),
                                           _j("done", 70)], root=intel)
    forecasts.resolve(ids[2], "yes", "proof", root=intel, at="2026-09-29")
    (intel / "briefs").mkdir()
    (intel / "briefs" / "s1.json").write_text(json.dumps({"slug": "s1", "theater_name": "Alpha theater"}), encoding="utf-8")
    snap = intel_page.build_snapshot(PulseStore(tmp_path / "p"), intel, now=datetime(2026, 9, 30, tzinfo=UTC))
    f = snap["forecasts"]
    assert [o["statement"] for o in f["open"]] == ["soon", "late"] and f["open"][0]["theater_name"] == "Alpha theater"
    assert f["resolved"] == [{"statement": "done", "probability": 70, "outcome": "yes",
                              "resolved_at": "2026-09-29", "evidence": "proof"}]
    assert f["scorecard"]["resolved"] == 1 and f["scorecard"]["open"] == 2
    page = render.render_brief(
        Brief(title="t", bottom_line="b", changes=[Change(what="<b>moved</b>", kind="escalated", basis="why")],
              judgments=[_j("J1", 65)], would_change_our_mind=["a ceasefire"], pulses=["Alpha"],
              indicators=[Indicator(signal="s", status="emerging", previous_status="not seen")]),
        theater_name="t", heat={}, as_of="2026-09-30")
    assert "&lt;b&gt;moved" in page and "65%" in page and "a ceasefire" in page and "was not seen" in page
