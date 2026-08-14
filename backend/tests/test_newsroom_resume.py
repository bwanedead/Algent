"""Resume assesses surviving artifacts and continues from the next unpaid stage."""

from __future__ import annotations

import json
from pathlib import Path

from algent_backend.cli.newsroom import progress as pg
from algent_backend.cli.newsroom import resume as rs


def _write(run: Path, name: str, payload) -> None:
    arts = run / "artifacts"
    arts.mkdir(parents=True, exist_ok=True)
    (arts / name).write_text(json.dumps(payload), encoding="utf-8")


def _run(tmp_path: Path, name: str = "0042__deadbeef") -> Path:
    run = tmp_path / name
    run.mkdir()
    (run / "state.json").write_text(json.dumps({"run_id": "deadbeef"}), encoding="utf-8")
    return run


def test_assess_draft_without_publish_is_ready_to_ship(tmp_path: Path) -> None:
    run = _run(tmp_path)
    _write(run, "profile.json", {"id": "prof_1"})
    _write(run, "draft.json", {"id": "drf_1", "title": "Kept"})
    _write(run, "gauntlet_report.json", {"final_verdict": "mature"})
    _write(run, "analytics_artifacts.json", [
        {"status": "produced", "artifact_name": "analytic_a.svg"},
    ])
    p = pg.assess(run)
    assert p.next_step == "publish"
    assert p.next_stage == "publish"
    assert "drafting" in p.skip
    assert "analytics_worker" in p.skip


def test_assess_profile_without_draft_continues_editorial(tmp_path: Path) -> None:
    run = _run(tmp_path)
    _write(run, "research_portfolio.json", {"vectors": [{"id": "v1"}], "total_considered": 3})
    _write(run, "selected_vector.json", {"id": "v1", "title": "Hit"})
    _write(run, "profile.json", {"id": "prof_1"})
    _write(run, "gauntlet_report.json", {"final_verdict": "mature"})
    p = pg.assess(run)
    assert p.next_step == "continue"
    assert p.next_stage == "editorial"
    assert "profile" in p.skip and "routing" in p.skip
    assert "drafting" not in p.skip


def test_from_editorial_drops_the_draft(tmp_path: Path) -> None:
    run = _run(tmp_path)
    _write(run, "profile.json", {"id": "prof_1"})
    _write(run, "gauntlet_report.json", {"final_verdict": "mature"})
    _write(run, "draft.json", {"id": "drf_1"})
    p = pg.assess(run, from_stage="editorial")
    assert p.next_step == "continue"
    assert p.next_stage == "editorial"
    assert "draft" not in p.present
    assert "profile" in p.present


def test_already_shipped_is_done(tmp_path: Path) -> None:
    run = _run(tmp_path)
    _write(run, "profile.json", {"id": "prof_1"})
    _write(run, "draft.json", {"id": "drf_1"})
    _write(run, "gauntlet_report.json", {"final_verdict": "mature"})
    (run / "artifacts" / "article_published.md").write_text("# hi\n", encoding="utf-8")
    _write(run, "newsroom_rail_report.json", {"published": True, "publish_action": "published"})
    p = pg.assess(run)
    assert p.next_step == "already_done"


def test_unfulfilled_analytics_keeps_editorial_open(tmp_path: Path) -> None:
    run = _run(tmp_path)
    _write(run, "profile.json", {"id": "prof_1"})
    _write(run, "gauntlet_report.json", {"final_verdict": "mature"})
    _write(run, "draft.json", {"id": "drf_1"})
    _write(run, "analytics_plan.json", {
        "warranted": True,
        "requests": [{"id": "anx_01", "status": "requested"}],
    })
    p = pg.assess(run)
    assert p.next_step == "continue"
    assert p.next_stage == "editorial"


def test_inject_state_replaces_artifact_keys_so_from_cannot_resurrect_them() -> None:
    existing = {"pool": {"items": []}, "draft": {"id": "old"}, "treatment": {"id": "old"}}
    state = {"profile": {"id": "prof_1"}, "source_run_id": "deadbeef"}
    out = pg.inject_state(existing, state)
    assert "draft" not in out and "treatment" not in out
    assert out["profile"]["id"] == "prof_1"
    assert out["pool"] == {"items": []}


def test_resume_dry_run_prints_the_plan(tmp_path: Path, capsys, monkeypatch) -> None:
    run = _run(tmp_path)
    _write(run, "profile.json", {"id": "prof_1"})
    _write(run, "draft.json", {"id": "drf_1", "title": "Kept"})
    _write(run, "gauntlet_report.json", {"final_verdict": "mature"})
    monkeypatch.setattr(rs, "runs_root", lambda: tmp_path)
    args = type("A", (), {"run": str(run), "from_stage": None, "dry_run": True})()
    assert rs.run_resume(args) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["dry_run"] is True
    assert out["next_step"] == "publish"


def test_continue_run_injects_profile_and_clears_done(tmp_path: Path, monkeypatch) -> None:
    """A leftover NameError on ARTIFACT_STATE_KEYS aborted resume before the rail started."""
    run = _run(tmp_path)
    _write(run, "selected_vector.json", {"id": "v1"})
    _write(run, "profile.json", {"id": "prof_1"})
    (run / "request.json").write_text(json.dumps({
        "agent_id": "newsroom_rail", "run_id": "deadbeef",
        "input": {"portfolio": {"vectors": []}},
    }), encoding="utf-8")
    (run / "done.json").write_text("{}", encoding="utf-8")

    class _Lock:
        def __enter__(self):
            return self
        def __exit__(self, *_a):
            return False

    monkeypatch.setattr("algent_backend.cli.newsroom.single_flight.NewsroomRunLock", _Lock)
    monkeypatch.setattr("algent_backend.cli.runs.exec_run.execute", lambda *_a, **_k: 0)

    progress = pg.assess(run)
    assert rs._continue_run(run, progress) == 0
    assert not (run / "done.json").exists()
    req = json.loads((run / "request.json").read_text(encoding="utf-8"))
    assert req["input"]["profile"]["id"] == "prof_1"
