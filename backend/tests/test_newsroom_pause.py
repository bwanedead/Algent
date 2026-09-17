"""Pausing a rail between stages so it can be resumed rather than restarted."""

from __future__ import annotations

import pytest

from algent_backend.cli.newsroom import pause


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(pause, "PAUSE_FILE", tmp_path / "newsroom_run.pause")


def test_a_pause_request_is_a_file_so_it_does_not_need_a_healthy_run() -> None:
    """Same reason radar's stop is a file: stopping must not depend on anything being reachable."""
    assert pause.requested() is False
    pause.request()
    assert pause.requested() is True
    pause.clear()
    assert pause.requested() is False


def test_the_rail_stops_at_a_stage_boundary_not_mid_stage(monkeypatch) -> None:
    """A boundary is the only place stopping is free.

    The previous stage has written its artifact and the next has spent nothing. Killing
    mid-stage throws away what that stage had already bought — a profile three minutes into
    research dies with nothing to show, and resume has to buy it again.
    """
    from algent_backend.agent_system.agents.newsroom.rail import _check_paused

    monkeypatch.setattr(pause, "requested", lambda: False)
    assert _check_paused("profile") is None       # nothing pending: the rail runs on

    monkeypatch.setattr(pause, "requested", lambda: True)
    with pytest.raises(pause.RunPaused) as raised:
        _check_paused("editorial")
    # The message names where it stopped, so the operator knows what was already paid for.
    assert "editorial" in str(raised.value)


def test_resume_clears_a_pending_pause() -> None:
    """A pause request outlives the run it stopped.

    Left set, it would halt the resume at its first stage boundary — which reads as
    "resume is broken" rather than "you paused".
    """
    from algent_backend.cli.newsroom.resume import run_resume

    pause.request()
    args = type("A", (), {"run": "definitely-not-a-run", "from_stage": None, "dry_run": True})()
    run_resume(args)
    assert pause.requested() is False
