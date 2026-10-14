"""Daily visuals: plan validation (ungrounded numbers rejected), cap, failure isolation, record shape (fake harness)."""

from __future__ import annotations

import pytest

from algent_backend.agent_system.agents.editorial import analytics_worker as w
from algent_backend.agent_system.agents.intel import visuals, visuals_facts as vf

SRC = "https://wire.example/strikes"


@pytest.fixture(autouse=True)
def _workspace(tmp_path, monkeypatch):
    monkeypatch.setattr(w, "default_workspace", lambda: tmp_path / "analytics_workspace")


def _sections() -> list[dict]:
    def dev(h, detail, when):
        return {"headline": h, "detail": detail, "when": when, "significance": "", "statements": [], "sources": [SRC]}
    return [
        {"theater_id": "thr_a", "name": "Alpha", "headline": "Alpha heats", "bottom_line": "x",
         "developments": [dev("Port strike", "Strikes hit 12.5% of berths", "2026-09-27"),
                          dev("Second wave", "Another 31.4% of berths were hit", "2026-09-28"),
                          dev("Third wave", "Damage reached 58.2% of berths", "2026-09-29")],
         "key_figures": [], "numbers": {}},
        {"theater_id": "thr_b", "name": "Bravo", "headline": "Bravo", "bottom_line": "y",
         "developments": [dev("Talks", "Delegations met", "2026-09-29")], "key_figures": [], "numbers": {}},
    ]


def _ask(**kw) -> visuals.VisualAsk:
    base = dict(theater_id="thr_a", form="chart", finding="Berth damage climbs each wave",
                caption="Share of berths hit, by wave.", reader_question="How fast is it growing?",
                why_not_prose="three numbers over time", fact_ids=["f1.1", "f1.2", "f1.3"],
                spec="bars of 12.5, 31.4 and 58.2 percent")
    return visuals.VisualAsk(**{**base, **kw})


def _validate(*asks, cap=3):
    return visuals.validate(visuals.VisualPlan(visuals=list(asks)), vf.collect(_sections()), {"thr_a", "thr_b"}, cap)


def test_ungrounded_numbers_and_thin_citations_are_rejected() -> None:
    kept, dropped = _validate(_ask(caption="Berth damage hit 99.9% by the third wave."))
    assert not kept and "numbers not in the cited facts" in dropped[0]
    kept, dropped = _validate(_ask(fact_ids=["f1.1"]))
    assert not kept and "too few" in dropped[0]
    kept, dropped = _validate(_ask(fact_ids=["f1.1", "nope"]))
    assert not kept
    kept, _ = _validate(_ask(fact_ids=["f1.1"], source_hint="CSIS missile database"))   # a fetched public spec
    assert len(kept) == 1


def test_cap_and_one_per_theater() -> None:
    kept, dropped = _validate(_ask(), _ask(form="comparison"))
    assert len(kept) == 1 and "already has a visual" in dropped[0]
    kept, dropped = _validate(_ask(), _ask(theater_id="thr_b", fact_ids=["f1.1", "f1.2"]), cap=1)
    assert len(kept) == 1 and "cap" in dropped[0]


def test_schematic_is_signposted_and_forms_map_to_worker_kinds() -> None:
    facts = vf.collect(_sections())
    req = visuals._request(_ask(form="schematic", caption="How the port is laid out."), facts[:2], 1, "2026-09-29")
    assert req.kind == "image" and "not to exact detail" in req.question and req.data_refs == ["f1.1", "f1.2"]
    assert visuals._request(_ask(form="comparison"), facts[:2], 1, "2026-09-29").kind == "chart"


def _runner(fail: bool = False):
    def run(prompt, folder):
        if fail:
            return False, "boom"
        (folder / "chart.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg" width="400" height="200">'
                                          '<rect x="10" y="10" width="50" height="50"/></svg>', encoding="utf-8")
        (folder / "data.csv").write_text("wave,share\n1,12.5%\n2,31.4%\n3,58.2%\n", encoding="utf-8")
        (folder / "caption.md").write_text("Share of berths hit.", encoding="utf-8")
        return True, "ok"
    return run


def _attach(sections, plan, *, runner, uploader=None, prior=None):
    uploaded: list[dict] = []
    def up(files):
        uploaded.append(files)
        return {"ok": True, "assets": len(files), "failed": []}
    rep = visuals.attach(sections, ctx=None, domain="geopolitics", as_of="2026-09-29", prior=prior,
                         ask=lambda *_a: plan, ready=lambda: (True, ""), runner=runner, uploader=uploader or up)
    return rep, uploaded


def test_record_shape_and_upload() -> None:
    secs = _sections()
    rep, up = _attach(secs, visuals.VisualPlan(visuals=[_ask()]), runner=_runner())
    assert rep["produced"] == 1, rep
    v = secs[0]["visuals"][0]
    assert v["kind"] == "chart" and v["asset"].startswith("/analytics/daily/geopolitics/2026-09-29/")
    assert v["caption"].startswith("Share of berths hit") and v["sources"][0]["url"] == SRC
    assert {"id", "title", "reader_question", "schematic", "ai_label", "detail"} <= set(v)
    assert list(up[0]) and "visuals" not in secs[1]


def test_failure_of_a_visual_never_fails_the_day() -> None:
    secs = _sections()
    rep, _ = _attach(secs, visuals.VisualPlan(visuals=[_ask()]), runner=_runner(fail=True))
    assert rep["produced"] == 0 and "visuals" not in secs[0] and rep["skipped"]
    def boom(*_a):
        raise RuntimeError("model down")
    out = visuals.attach(_sections(), ctx=None, domain="g", as_of="2026-09-29", ask=boom)
    assert out["produced"] == 0 and "model down" in out["skipped"][0]


def test_unhosted_figure_is_not_attached_and_prior_visuals_are_reused() -> None:
    secs = _sections()
    rep, _ = _attach(secs, visuals.VisualPlan(visuals=[_ask()]), runner=_runner(),
                     uploader=lambda files: {"ok": True, "note": "asset upload off", "failed": []})
    assert "visuals" not in secs[0] and "not hosted" in rep["skipped"][0]
    fresh = _sections()
    rep, _ = _attach(fresh, None, runner=None, prior={"theaters": [{"theater_id": "thr_a", "visuals": [{"id": "old"}]}]})
    assert rep == {"reused": 1} and fresh[0]["visuals"] == [{"id": "old"}]


def test_too_little_to_draw_from_skips_the_planning_call() -> None:
    called = []
    rep = visuals.attach(_sections()[1:], ctx=None, domain="g", as_of="2026-09-29", ask=lambda *a: called.append(a))
    assert rep is None and not called
