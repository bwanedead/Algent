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
            input_file=None,
            input_key=None,
            fixture=False,
            runtime="langgraph",
            max_turns=7,
            foreground=False,
        )
    )

    assert code == 0
    out = _capture_json(capsys)
    assert spawned == [out["run_id"]]
    # start surfaces locators so the run is immediately findable.
    assert out["timeline"].replace("\\", "/").endswith("audit/timeline.md")
    assert "run_dir" in out and out["run_id"] in out["run_dir"]
    paths = RunPaths(find_run_root(out["run_id"]))
    request = json.loads(paths.request_file.read_text(encoding="utf-8"))
    assert request["input"] == {"topic": "cli"}
    assert request["max_turns"] == 7
    assert read_state(paths).status == "queued"


def test_timeline_renders_reasoning_tools_used_and_t0_preview() -> None:
    body = render_timeline(
        [
            _event(1, ev.INPUT_PREVIEW, {
                "title": "t0 discovery pool", "summary": "40 items | pillars {'economics': 13}",
                "top": ["ECON_X  [theme]  economics"], "link": "C:/x/pool.json",
            }),
            _event(2, ev.AGENT_STEP, {"content": "read the top hit", "tool_calls": [{"name": "web_search", "args": {}}]}),
            _event(3, ev.AGENT_STEP, {"content": "done", "tool_calls": []}),
        ]
    )
    assert "t0 discovery pool: 40 items" in body
    assert "pool.json)" in body  # markdown link to the full t0 file
    assert "reasoning: read the top hit" in body
    assert "tools used: web_search" in body
    assert "tools used: none (final answer)" in body


def test_timeline_renders_all_t1_vectors_in_output_preview() -> None:
    body = render_timeline(
        [
            _event(1, ev.OUTPUT_PREVIEW, {
                "title": "t1 research portfolio", "summary": "5 vectors from 40 t0 hits",
                "items": [f"{i}. Vector {i}  [story/deep]  hits=['H']  sources=2" for i in range(1, 6)],
                "link": "../artifacts/research_portfolio.json",
            }),
        ]
    )
    for i in range(1, 6):  # all five vectors present, not a truncated 2
        assert f"{i}. Vector {i}" in body
    assert "research_portfolio.json)" in body  # link to the full t1


def test_build_turns_groups_steps_with_their_tool_results() -> None:
    from algent_backend.agent_system.runs.control_plane.turns import build_turns

    turns = build_turns(
        [
            _event(1, ev.RUN_STARTED, {"agent_id": "a"}),
            _event(2, ev.AGENT_STEP, {"content": "thinking", "tool_calls": [{"name": "web_search", "args": {"q": "x"}}]}),
            _event(3, ev.TOOL_RESULT, {"tool": "web_search", "content": "results"}),
            _event(4, ev.AGENT_STEP, {"content": "done", "tool_calls": []}),
        ]
    )
    assert len(turns) == 2
    assert turns[0]["turn"] == 1
    assert turns[0]["model_output"]["tool_calls"][0]["name"] == "web_search"
    assert turns[0]["tool_results"][0]["tool"] == "web_search"
    assert turns[1]["model_output"]["content"] == "done" and turns[1]["tool_results"] == []


def test_recorder_writes_per_turn_json_files() -> None:
    recorder = RunRecorder("turn-run", "a")
    recorder.start(RunRequest(agent_id="a", input={}, run_id="turn-run"))
    recorder.emit(ev.AGENT_STEP, {"content": "c", "tool_calls": [{"name": "t", "args": {}}]})
    recorder.emit(ev.TOOL_RESULT, {"tool": "t", "content": "r"})

    turn_file = recorder.paths.turn_file(1)
    assert turn_file.exists()
    data = json.loads(turn_file.read_text(encoding="utf-8"))
    assert data["model_output"]["tool_calls"][0]["name"] == "t"
    assert data["tool_results"][0]["content"] == "r"


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


# -- watch surfaces live cost ------------------------------------------------


def test_watch_cost_summary_reports_spend_and_cap_trip() -> None:
    from algent_backend.cli.runs.watch import _cost_summary

    recorder = RunRecorder("cost-run", "a")
    recorder.start(RunRequest(agent_id="a", input={}, run_id="cost-run"))
    recorder.emit(ev.COST_LIMIT_REACHED, {"estimated_usd": 1.23})

    summary = _cost_summary(recorder.paths)
    assert summary["estimated_usd"] == 1.23
    assert summary["cost_limit_reached"] is True
