"""
Offline tests for the run control plane: recorder surfaces, artifacts,
timeline rendering, ledger folding, and the runs CLI mechanics.

No live API calls; agents run with fake models. The autouse conftest fixture
isolates every test under a temp runs-data root.
"""

from __future__ import annotations

import json
from pathlib import Path

from algent_backend.agent_system.artifacts import ArtifactWriter
from algent_backend.agent_system.runs import events as ev
from algent_backend.agent_system.runs.control_plane.events_log import read_events
from algent_backend.agent_system.runs.control_plane.layout import (
    RunPaths,
    find_run_root,
    runs_data_root,
)
from algent_backend.agent_system.runs.control_plane.ledger import RunLedger
from algent_backend.agent_system.runs.control_plane.recorder import RunRecorder
from algent_backend.agent_system.runs.control_plane.state import read_state
from algent_backend.agent_system.runs.control_plane.timeline import render_timeline
from algent_backend.agent_system.runs.events import RunEvent
from algent_backend.agent_system.runs.models import RunRequest
from algent_backend.agent_system.runs.service import RunService
from algent_backend.agent_system.tools import ToolRegistry
from algent_backend.cli.runs import list_runs, show, start, status, watch
from tests.test_langgraph_runtime import FakeChatModel, FakeModelResolver


def _service(response: str = "Brief.") -> RunService:
    return RunService(
        model_resolver=FakeModelResolver(FakeChatModel(response)),
        tool_registry=ToolRegistry(),
    )


# -- end-to-end through RunService ------------------------------------------


def test_run_writes_all_control_plane_surfaces() -> None:
    result = _service().run(RunRequest(agent_id="hello_workflow", input={"topic": "x"}))

    assert result.status == "completed"
    paths = RunPaths(find_run_root(result.run_id))
    assert read_state(paths).status == "completed"
    assert paths.done_file.exists()
    assert paths.timeline_file.exists()
    assert json.loads(paths.result_file.read_text(encoding="utf-8"))["status"] == "completed"

    types = [e.type for e in read_events(paths)]
    assert types[0] == ev.RUN_STARTED
    assert ev.NODE_COMPLETED in types
    assert types[-1] == ev.RUN_COMPLETED


def test_failed_lookup_still_reaches_terminal_record() -> None:
    """Watchers poll done.json — even a lookup failure must produce it."""
    result = _service().run(RunRequest(agent_id="missing", input={}))

    assert result.status == "failed"
    paths = RunPaths(find_run_root(result.run_id))
    assert paths.done_file.exists()
    assert read_state(paths).status == "failed"
    assert [e.type for e in read_events(paths)][-1] == ev.RUN_FAILED


def test_preallocated_run_id_is_honored() -> None:
    request = RunRequest(agent_id="hello_workflow", input={"topic": "x"}, run_id="fixed-id")
    result = _service().run(request)
    assert result.run_id == "fixed-id"
    assert RunPaths(find_run_root("fixed-id")).done_file.exists()


def test_ledger_folds_to_latest_entry_per_run() -> None:
    result = _service().run(RunRequest(agent_id="hello_workflow", input={"topic": "x"}))

    entries = RunLedger().list_runs()
    mine = [e for e in entries if e.run_id == result.run_id]
    assert len(mine) == 1  # start + finish rows folded
    assert mine[0].status == "completed"
    assert mine[0].duration_s is not None


# -- artifacts ----------------------------------------------------------------


def test_artifact_writer_records_ref_and_event() -> None:
    recorder = RunRecorder("art-run", "a")
    recorder.start(RunRequest(agent_id="a", input={}, run_id="art-run"))
    writer = ArtifactWriter(
        recorder.paths.artifacts_dir, "art-run", on_written=recorder.record_artifact
    )

    ref = writer.write_text("brief.md", "# Hello", kind="markdown")

    assert (recorder.paths.artifacts_dir / ref.relative_path).read_text(
        encoding="utf-8"
    ) == "# Hello"
    assert ref.size_bytes == len(b"# Hello")
    assert any(e.type == ev.ARTIFACT_WRITTEN for e in read_events(recorder.paths))


def test_artifact_names_are_sanitized() -> None:
    writer = ArtifactWriter(Path(runs_data_root()) / "loose", "r1")
    ref = writer.write_json("../../evil name.json", {"k": 1})
    assert "/" not in ref.relative_path and "\\" not in ref.relative_path


# -- timeline -----------------------------------------------------------------


def _event(seq: int, type_: str, payload: dict) -> RunEvent:
    return RunEvent(
        seq=seq, ts="2026-01-01T00:00:00+00:00", run_id="r", type=type_, payload=payload
    )


def test_timeline_renders_known_and_unknown_events() -> None:
    body = render_timeline(
        [
            _event(1, ev.RUN_STARTED, {"agent_id": "a", "runtime": "langgraph", "input": {"t": 1}}),
            _event(2, "custom.thing", {"note": "organic event type"}),
            _event(3, ev.RUN_COMPLETED, {"status": "completed", "output": {"ok": True}}),
        ]
    )
    assert "run.started" in body
    assert "custom.thing" in body and "organic event type" in body
    assert "status: completed" in body


def test_timeline_truncates_long_fields_with_marker() -> None:
    body = render_timeline([_event(1, "x", {"big": "y" * 5000})])
    assert "[truncated" in body


def test_timeline_numbers_turns() -> None:
    body = render_timeline(
        [
            _event(1, ev.RUN_STARTED, {"agent_id": "a", "runtime": "langgraph", "input": {}}),
            _event(2, ev.AGENT_STEP, {"content": "surveying", "tool_calls": [{"name": "gdelt_events", "args": {}}]}),
            _event(3, ev.TOOL_RESULT, {"tool": "gdelt_events", "content": "429"}),
            _event(4, ev.AGENT_STEP, {"content": "done", "tool_calls": []}),
            _event(5, ev.RUN_COMPLETED, {"status": "completed", "output": {}}),
        ]
    )
    assert "TURN 0001" in body
    assert "TURN 0002" in body
    assert "model turns: 2" in body


# -- CLI ------------------------------------------------------------------------


def _capture_json(capsys) -> dict | list:
    return json.loads(capsys.readouterr().out)


def test_cli_start_allocates_run_and_request(monkeypatch, capsys) -> None:
    spawned: list[str] = []
    monkeypatch.setattr(start, "_spawn_detached", lambda run_id: spawned.append(run_id))

    code = start.run(
        _ns(
            agent_id="news_brief",
            input=None,
            topic="cli",
            goal=None,
            runtime="langgraph",
            max_turns=7,
            foreground=False,
        )
    )

    assert code == 0
    out = _capture_json(capsys)
    assert spawned == [out["run_id"]]
    paths = RunPaths(find_run_root(out["run_id"]))
    request = json.loads(paths.request_file.read_text(encoding="utf-8"))
    assert request["input"] == {"topic": "cli"}
    assert request["max_turns"] == 7
    assert read_state(paths).status == "queued"


def test_cli_status_watch_show_list_roundtrip(capsys) -> None:
    result = _service().run(RunRequest(agent_id="hello_workflow", input={"topic": "x"}))

    assert status.run(_ns(run_id=result.run_id)) == 0
    assert _capture_json(capsys)["done"] is True

    assert watch.run(_ns(run_id=result.run_id, timeout=5.0, poll_interval=0.1)) == 0
    assert _capture_json(capsys)["event"] == "loop_done"

    assert show.run(_ns(run_id=result.run_id)) == 0
    shown = _capture_json(capsys)
    assert shown["state"]["status"] == "completed"
    assert shown["event_count"] >= 2

    assert list_runs.run(_ns(limit=10)) == 0
    assert any(e["run_id"] == result.run_id for e in _capture_json(capsys))


def test_cli_watch_reports_dead_process(capsys) -> None:
    recorder = RunRecorder("dead-run", "a")
    request = RunRequest(agent_id="a", input={}, run_id="dead-run")
    recorder.start(request)  # status=running, pid=this process
    # Rewrite state with a pid that cannot exist.
    from algent_backend.agent_system.runs.control_plane.state import write_state

    state = read_state(recorder.paths).model_copy(update={"pid": 2})
    write_state(recorder.paths, state)

    code = watch.run(_ns(run_id="dead-run", timeout=5.0, poll_interval=0.1))
    out = _capture_json(capsys)
    assert code == 1
    assert out["event"] == "error" and out["reason"] == "process_dead"


def test_cli_unknown_run(capsys) -> None:
    assert status.run(_ns(run_id="nope")) == 1
    assert "unknown run" in _capture_json(capsys)["error"]


class _ns:
    def __init__(self, **kwargs) -> None:
        self.__dict__.update(kwargs)
