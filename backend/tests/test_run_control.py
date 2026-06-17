"""
Offline tests for the run control surface (the ``stop`` command).

No real process is launched: we fabricate a run directory and confirm stop marks
it terminal. Process termination is best-effort and platform-specific, so it is
exercised separately from this logic.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from types import SimpleNamespace

from algent_backend.agent_system.runs.control_plane.layout import prune_runs, run_paths
from algent_backend.agent_system.runs.control_plane.state import RunState, read_state, write_state
from algent_backend.cli.runs import agents, stop


def _running_state(run_id: str) -> RunState:
    now = datetime.now(UTC).isoformat()
    # pid=None: nothing real to kill, so stop exercises only the bookkeeping.
    return RunState(
        run_id=run_id,
        agent_id="general_discovery",
        runtime="langgraph",
        status="running",
        created_at=now,
        updated_at=now,
        pid=None,
    )


def test_stop_unknown_run_errors(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("ALGENT_RUNS_DIR", str(tmp_path))
    code = stop.run(SimpleNamespace(run_id="does-not-exist", reason="x"))
    assert code == 1


def test_stop_marks_run_terminal(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("ALGENT_RUNS_DIR", str(tmp_path))
    run_id = "run-1"
    paths = run_paths(run_id)
    write_state(paths, _running_state(run_id))

    code = stop.run(SimpleNamespace(run_id=run_id, reason="spinning"))

    assert code == 0
    assert paths.done_file.exists()
    assert json.loads(paths.done_file.read_text())["status"] == "stopped"
    assert read_state(paths).status == "stopped"


def test_stop_is_idempotent_on_terminal_run(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("ALGENT_RUNS_DIR", str(tmp_path))
    run_id = "run-2"
    paths = run_paths(run_id)
    write_state(paths, _running_state(run_id))

    assert stop.run(SimpleNamespace(run_id=run_id, reason="first")) == 0
    # second stop sees a terminal run and no-ops cleanly
    assert stop.run(SimpleNamespace(run_id=run_id, reason="second")) == 0
    assert read_state(paths).status == "stopped"


def test_prune_runs_keeps_only_recent(tmp_path) -> None:
    for i in range(8):
        (tmp_path / f"run-{i}").mkdir()
    removed = prune_runs(keep=5, root=tmp_path)
    remaining = [p.name for p in tmp_path.iterdir() if p.is_dir()]
    assert len(remaining) == 5
    assert len(removed) == 3


def test_prune_runs_noop_under_keep(tmp_path) -> None:
    for i in range(3):
        (tmp_path / f"run-{i}").mkdir()
    assert prune_runs(keep=5, root=tmp_path) == []
    assert len([p for p in tmp_path.iterdir() if p.is_dir()]) == 3


def test_recorder_writes_error_log_on_run_error(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("ALGENT_RUNS_DIR", str(tmp_path))
    from algent_backend.agent_system.runs import events as ev
    from algent_backend.agent_system.runs.control_plane.recorder import RunRecorder

    rec = RunRecorder("run-err", tmp_path)
    rec.emit(ev.RUN_ERROR, {"error": "boom", "traceback": "Traceback:\nValueError: boom"})

    assert rec.paths.error_file.exists()
    assert "ValueError: boom" in rec.paths.error_file.read_text(encoding="utf-8")


def test_agents_lists_the_catalog(capsys) -> None:
    code = agents.run(SimpleNamespace())
    assert code == 0
    catalog = json.loads(capsys.readouterr().out)
    ids = {entry["agent_id"] for entry in catalog}
    assert "general_discovery" in ids
