"""
Offline tests for the run control surface: per-agent run layout, retention, the
``stop`` command, traceback capture, and the agent catalog.

No real process is launched: we fabricate run directories and confirm behavior.
Process termination is best-effort and platform-specific, exercised elsewhere.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from types import SimpleNamespace

from algent_backend.agent_system.runs.control_plane.layout import (
    RunPaths,
    allocate_run_root,
    find_run_root,
    prune_runs,
)
from algent_backend.agent_system.runs.control_plane.state import RunState, read_state, write_state
from algent_backend.cli.runs import agents, stop

_AGENT = "general_discovery"


def _fabricate_running_run(run_id: str) -> RunPaths:
    """Create a run dir (via the real allocator) with a running state, no pid."""
    paths = RunPaths(allocate_run_root(_AGENT, run_id))  # uses ALGENT_RUNS_DIR
    now = datetime.now(UTC).isoformat()
    write_state(
        paths,
        RunState(
            run_id=run_id,
            agent_id=_AGENT,
            runtime="langgraph",
            status="running",
            created_at=now,
            updated_at=now,
            pid=None,
        ),
    )
    return paths


def test_allocate_increments_and_find_locates(tmp_path) -> None:
    a = allocate_run_root("disco", "id-a", tmp_path)
    b = allocate_run_root("disco", "id-b", tmp_path)
    assert a.name.startswith("0001__")
    assert b.name.startswith("0002__")
    a.mkdir(parents=True, exist_ok=True)
    b.mkdir(parents=True, exist_ok=True)
    assert find_run_root("id-b", tmp_path) == b
    assert find_run_root("nope", tmp_path) is None


def test_stop_unknown_run_errors(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("ALGENT_RUNS_DIR", str(tmp_path))
    assert stop.run(SimpleNamespace(run_id="does-not-exist", reason="x")) == 1


def test_stop_marks_run_terminal(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("ALGENT_RUNS_DIR", str(tmp_path))
    paths = _fabricate_running_run("run-1")

    code = stop.run(SimpleNamespace(run_id="run-1", reason="spinning"))

    assert code == 0
    assert paths.done_file.exists()
    assert json.loads(paths.done_file.read_text())["status"] == "stopped"
    assert read_state(paths).status == "stopped"


def test_stop_is_idempotent_on_terminal_run(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("ALGENT_RUNS_DIR", str(tmp_path))
    paths = _fabricate_running_run("run-2")

    assert stop.run(SimpleNamespace(run_id="run-2", reason="first")) == 0
    assert stop.run(SimpleNamespace(run_id="run-2", reason="second")) == 0
    assert read_state(paths).status == "stopped"


def test_prune_runs_keeps_only_recent_per_agent(tmp_path) -> None:
    for i in range(8):
        allocate_run_root(_AGENT, f"r{i}", tmp_path).mkdir(parents=True, exist_ok=True)
    removed = prune_runs(keep=5, root=tmp_path)
    agent_dir = tmp_path / _AGENT
    remaining = [p for p in agent_dir.iterdir() if p.is_dir() and "__" in p.name]
    assert len(remaining) == 5
    assert len(removed) == 3


def test_prune_runs_noop_under_keep(tmp_path) -> None:
    for i in range(3):
        allocate_run_root(_AGENT, f"r{i}", tmp_path).mkdir(parents=True, exist_ok=True)
    assert prune_runs(keep=5, root=tmp_path) == []


def test_recorder_writes_error_log_on_run_error(tmp_path) -> None:
    from algent_backend.agent_system.runs import events as ev
    from algent_backend.agent_system.runs.control_plane.recorder import RunRecorder

    rec = RunRecorder("run-err", _AGENT, tmp_path)
    rec.emit(ev.RUN_ERROR, {"error": "boom", "traceback": "Traceback:\nValueError: boom"})

    assert rec.paths.error_file.exists()
    assert "ValueError: boom" in rec.paths.error_file.read_text(encoding="utf-8")


def test_agents_lists_the_catalog(capsys) -> None:
    assert agents.run(SimpleNamespace()) == 0
    catalog = json.loads(capsys.readouterr().out)
    assert "general_discovery" in {entry["agent_id"] for entry in catalog}
