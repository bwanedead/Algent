"""The radar supervisor's control surface — above all, that stopping is reliable."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from algent_backend.publishing import radar_daemon as d


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    """Never touch the real pid/stop/log files from a test."""
    monkeypatch.setattr(d, "PID_FILE", tmp_path / "radar_daemon.json")
    monkeypatch.setattr(d, "STOP_FILE", tmp_path / "radar_daemon.stop")
    monkeypatch.setattr(d, "LOG_FILE", tmp_path / "radar_daemon.log")


def _state(pid: int) -> d.DaemonState:
    return d.DaemonState(pid=pid, started_at=datetime.now(UTC).isoformat())


def test_a_dead_pid_is_not_running(monkeypatch) -> None:
    """The lid closing must read as 'off', not as 'on'.

    This is why liveness goes through the house probe: a local os.kill(pid, 0) is
    CTRL_C_EVENT on Windows and reports dead pids as alive, which would leave status
    claiming radar was running forever after a crash.
    """
    d.write_state(_state(4242))
    monkeypatch.setattr(d, "process_alive", lambda pid: False)
    alive, state = d.running()
    assert alive is False and state is not None and state.pid == 4242


def test_stopping_something_already_gone_is_success_not_an_error(monkeypatch) -> None:
    """`stop` is the panic button; it must never fail because the thing already died."""
    d.write_state(_state(4242))
    monkeypatch.setattr(d, "process_alive", lambda pid: False)

    report = d.stop()
    assert report["stopped"] is True and report["was_running"] is False
    # The stop flag must not survive: a stale one would kill the NEXT start immediately.
    assert not d.STOP_FILE.exists()


def test_a_loop_that_exits_on_the_flag_stops_gracefully(monkeypatch) -> None:
    calls = {"n": 0}

    def alive(_pid: int) -> bool:
        calls["n"] += 1
        return calls["n"] < 3          # dies shortly after the flag is written

    monkeypatch.setattr(d, "process_alive", alive)
    d.write_state(_state(4242))

    report = d.stop(timeout_s=5)
    assert report["stopped"] is True and "graceful" in report["how"]
    assert not d.STOP_FILE.exists()


def test_a_wedged_loop_is_force_killed_rather_than_left_running(monkeypatch) -> None:
    """A radar that cannot be turned off on demand is worse than a lost discovery cycle.

    The loop can be blocked inside a discovery subprocess for minutes; when it is, waiting
    politely is the wrong answer.
    """
    killed: list[int] = []
    state = {"alive": True}

    monkeypatch.setattr(d, "process_alive", lambda pid: state["alive"])

    def terminate(pid: int) -> bool:
        killed.append(pid)
        state["alive"] = False          # the tree-kill is what actually ends it
        return True

    monkeypatch.setattr(d, "terminate_tree", terminate)
    d.write_state(_state(4242))

    report = d.stop(timeout_s=1)
    assert killed == [4242]
    assert report["stopped"] is True and "force" in report["how"]
    assert d.read_state().stopped_at


def test_start_state_survives_a_crash_for_status_to_explain(monkeypatch) -> None:
    """A pid file with no clean stop is the signature of a kill or a sleeping machine."""
    d.write_state(_state(4242))
    monkeypatch.setattr(d, "process_alive", lambda pid: False)

    alive, state = d.running()
    assert not alive and state.stopped_at == ""     # never stopped -> it was interrupted
    assert json.loads(d.PID_FILE.read_text(encoding="utf-8"))["pid"] == 4242


def test_read_state_survives_a_new_field() -> None:
    """A pid file from an older daemon must still load after we add a field."""
    d.write_state(_state(7))
    raw = json.loads(d.PID_FILE.read_text(encoding="utf-8"))
    raw.pop("last_heartbeat_at", None)
    raw["future_field"] = "ignore me"
    d.PID_FILE.write_text(json.dumps(raw), encoding="utf-8")
    state = d.read_state()
    assert state is not None and state.pid == 7
    assert state.last_heartbeat_at == ""


def test_a_long_sleep_is_a_lid_close_not_jitter() -> None:
    from datetime import timedelta

    now = datetime(2026, 8, 13, 12, 0, tzinfo=UTC)
    assert d.sleep_gap_s(now, now + timedelta(seconds=5)) is None
    gap = d.sleep_gap_s(now, now + timedelta(minutes=40))
    assert gap is not None and gap >= 40 * 60


def test_duplicate_content_is_skipped_so_the_queue_can_move(monkeypatch) -> None:
    """The live stall: 403 duplicate, item stays queued, every tempo retries it, nothing else ships."""
    from algent_backend.cli.newsroom import radar as cli
    from algent_backend.publishing import radar_queue as rq
    from algent_backend.publishing.x_client import Posted, XWriteError

    items = [
        rq.RadarPost(id="a", key="a", text="Radar: already said", status="queued",
                     scheduled_for="2026-08-13T00:00:00+00:00"),
        rq.RadarPost(id="b", key="b", text="Radar: new fact", status="queued",
                     scheduled_for="2026-08-13T00:01:00+00:00"),
    ]
    marked: list[tuple[str, str]] = []
    monkeypatch.setattr(cli, "write_configured", lambda: True)
    monkeypatch.setattr(cli, "_review_if_stale", lambda: [])
    monkeypatch.setattr(cli.q, "due", lambda: list(items))

    def mark(pid: str, **kw):
        marked.append((pid, str(kw.get("status"))))
        if kw.get("status") == "skipped":
            items[:] = [p for p in items if p.id != pid]

    monkeypatch.setattr(cli.q, "mark", mark)

    def fake_post(text: str, **k):
        if "already said" in text:
            raise XWriteError(
                'post failed (403): {"detail":"You are not allowed to create a Tweet with duplicate content."}'
            )
        return Posted(id="1", text=text, url="https://x.test/1")

    monkeypatch.setattr(cli, "post", fake_post)
    url, outcome = cli._release_one(_state(1))
    assert outcome == "posted" and url == "https://x.test/1"
    assert marked == [("a", "skipped"), ("b", "posted")]


def test_an_empty_release_tick_does_not_burn_a_tempo_slot() -> None:
    """The live failure: daemon alive, posts overdue, clock jumped another 40 minutes.

    Discovery had scheduled the first item ~30 minutes out. The first tick fired a few
    minutes early, nothing was due, and advancing the tempo anyway left overdue posts
    sitting until the next slot — which is how 'running' produced nothing for two hours.
    """
    from datetime import timedelta

    from algent_backend.cli.newsroom.radar import next_release_at

    now = datetime(2026, 8, 12, 21, 58, tzinfo=UTC)
    first_slot = datetime(2026, 8, 12, 22, 7, tzinfo=UTC)

    empty = next_release_at(
        now=now, outcome="empty", post_every_min=40, next_queued_at=first_slot)
    assert empty == first_slot

    posted = next_release_at(
        now=now, outcome="posted", post_every_min=40, next_queued_at=first_slot, wait_min=40)
    assert posted == now + timedelta(minutes=40)

    idle = next_release_at(
        now=now, outcome="empty", post_every_min=40, next_queued_at=None)
    assert idle == now


def test_radar_yields_discovery_to_a_running_article_rail(monkeypatch, tmp_path) -> None:
    """Radar is the background job; it must never make the operator stop it to do real work.

    Only discovery touches the rail, so a deferral costs nothing visible — posting continues.
    And a deferral must not count as a completed cycle, or radar would wait another full
    interval after losing one race.
    """
    import json as _json

    from algent_backend.cli.newsroom import radar as cli

    lock = tmp_path / "newsroom_run.lock"
    lock.write_text(_json.dumps({"pid": 4242}), encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    (tmp_path / "runs_data").mkdir(exist_ok=True)
    (tmp_path / "runs_data" / "newsroom_run.lock").write_text(
        _json.dumps({"pid": 4242}), encoding="utf-8")

    monkeypatch.setattr(
        "algent_backend.agent_system.runs.control_plane.liveness.process_alive",
        lambda pid: True,
    )
    assert cli._rail_busy() is True

    spawned: list[str] = []
    monkeypatch.setattr(cli.subprocess, "Popen", lambda *a, **k: spawned.append("ran"))
    state = d.DaemonState(pid=1, started_at="")
    assert cli._refresh(state) == -1        # deferred
    assert spawned == []                     # and it never spent anything

    # A dead lock-holder is not busy — a crashed run must not block radar forever.
    monkeypatch.setattr(
        "algent_backend.agent_system.runs.control_plane.liveness.process_alive",
        lambda pid: False,
    )
    assert cli._rail_busy() is False
