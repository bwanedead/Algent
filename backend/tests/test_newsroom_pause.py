"""Pausing a rail at a checkpoint so it can be resumed rather than restarted."""

from __future__ import annotations

import json

import pytest

from algent_backend.agent_system.foundation import pause as signal
from algent_backend.cli.newsroom import pause


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    # The signal lives in foundation; isolating only the CLI's alias once let a test write the
    # real pause file, which would stop the operator's next run at its first checkpoint.
    monkeypatch.setattr(signal, "PAUSE_FILE", tmp_path / "newsroom_run.pause")


def test_a_pause_request_is_a_file_so_it_does_not_need_a_healthy_run() -> None:
    """Same reason radar's stop is a file: stopping must not depend on anything being reachable."""
    assert pause.requested() is False
    pause.request()
    assert pause.requested() is True
    pause.clear()
    assert pause.requested() is False


def test_a_checkpoint_stops_only_when_asked_and_says_where() -> None:
    from algent_backend.agent_system.agents.newsroom.rail import _check_paused

    assert _check_paused("profile") is None       # nothing pending: the rail runs on
    pause.request()
    with pytest.raises(signal.RunPaused) as raised:
        _check_paused("editorial")
    # The message names where it stopped, so the operator knows what was already paid for.
    assert "editorial" in str(raised.value)


def test_resume_clears_a_pending_pause() -> None:
    """A pause request outlives the run it stopped.

    Left set, it would halt the resume at its first checkpoint — which reads as
    "resume is broken" rather than "you paused".
    """
    from algent_backend.cli.newsroom.resume import run_resume

    pause.request()
    args = type("A", (), {"run": "definitely-not-a-run", "from_stage": None, "dry_run": True})()
    run_resume(args)
    assert pause.requested() is False


def test_a_first_draft_on_disk_resumes_into_editorial_not_publish(tmp_path) -> None:
    """draft.json lands after the FIRST draft. Resume once took it as finished and published
    it raw — no cut, no review, no honesty check."""
    from algent_backend.cli.newsroom.progress import assess

    arts = tmp_path / "run" / "artifacts"
    arts.mkdir(parents=True)
    for name, blob in {
        "profile.json": {"id": "prof_x"},
        "gauntlet_report.json": {"final_verdict": "needs_enrichment"},
        "treatment.json": {"id": "trt_x"},
        "draft.json": {"id": "drf_x", "body": "first draft"},
    }.items():
        (arts / name).write_text(json.dumps(blob), encoding="utf-8")

    got = assess(tmp_path / "run")
    assert got.next_step == "continue" and got.next_stage == "editorial"

    (arts / "editorial_pipeline_report.json").write_text(json.dumps({"status": "publishable"}),
                                                         encoding="utf-8")
    assert assess(tmp_path / "run").next_step == "publish"


def test_a_resumed_first_draft_still_gets_its_checks(monkeypatch) -> None:
    """With the draft reused but no quality record, the cut/review/honesty lane runs."""
    from algent_backend.agent_system.agents.editorial import pipeline as pl
    from algent_backend.agent_system.runs.context import AgentRunContext

    ran: list[str] = []

    def quality(context, config, *, draft, treatment, profile):
        ran.append("checks")
        return {**draft, "body": "checked"}, profile, {"caveat_verdict": "verified"}

    monkeypatch.setattr(pl, "_post_draft_quality", quality)
    monkeypatch.setattr(pl, "_headline_and_hero", lambda c, cfg, d, **k: (d, None, []))
    ctx = AgentRunContext(run_id="t", model_resolver=object(), emit=lambda *a, **k: None)  # type: ignore[arg-type]

    draft, _p, _r, q, _h, _s = pl._drafting_stage(
        ctx, None, {"draft": {"id": "d", "body": "raw"}}, {"id": "p"}, {"id": "t"}, {})
    assert ran == ["checks"] and draft["body"] == "checked" and q["caveat_verdict"] == "verified"

    ran.clear()
    pl._drafting_stage(ctx, None, {"draft": {"id": "d", "body": "checked"},
                                   "draft_quality": {"caveat_verdict": "verified"}},
                       {"id": "p"}, {"id": "t"}, {})
    assert ran == []                                   # already done: not bought twice


def test_a_pause_mid_editorial_stops_at_the_next_step(monkeypatch) -> None:
    from algent_backend.agent_system.agents.editorial import pipeline as pl
    from algent_backend.agent_system.runs.context import AgentRunContext

    def quality(context, config, *, draft, treatment, profile):
        pause.request()                                # operator pauses during the review
        return draft, profile, {}

    monkeypatch.setattr(pl, "_post_draft_quality", quality)
    headline: list[int] = []
    monkeypatch.setattr(pl, "_headline_and_hero", lambda *a, **k: headline.append(1))
    ctx = AgentRunContext(run_id="t", model_resolver=object(), emit=lambda *a, **k: None)  # type: ignore[arg-type]

    with pytest.raises(signal.RunPaused) as raised:
        pl._drafting_stage(ctx, None, {"draft": {"id": "d", "body": "raw"}},
                           {"id": "p"}, {"id": "t"}, {})
    assert "honesty check" in str(raised.value) and headline == []
