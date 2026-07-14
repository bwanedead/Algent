"""Tests for the analytics_worker — the sandboxed fulfill + the harness-owned integrity checks.

The grok subprocess is faked (a ``runner`` that writes files into the scratch folder), so these
run offline and deterministically. What they pin is the HARNESS behaviour: grounding the hand-off,
the sweep, the visual figure check, copying the artifact out, and emptying the scratch folder.
"""

from __future__ import annotations

from pathlib import Path

from algent_backend.agent_system.agents.editorial import analytics_worker as aw
from algent_backend.agent_system.agents.editorial.analytics_contracts import (
    AnalyticsPlan,
    AnalyticsRequest,
)
from algent_backend.agent_system.agents.research.profile import (
    Claim,
    SignalProfile,
    SourceArtifact,
    SourceSnapshot,
)
from algent_backend.agent_system.artifacts import ArtifactWriter
from algent_backend.agent_system.runs.context import AgentRunContext


def _profile() -> SignalProfile:
    return SignalProfile(
        id="prof_x", title="Fed path", as_of="2026-06-30",
        source_ledger=[SourceArtifact(
            id="s1", url="u", title="CPI report", publisher="BLS",
            snapshot=SourceSnapshot(excerpt="core PCE rose to 3.4% in May from 3.1% in April"))],
        claim_ledger=[
            Claim(id="c1", text="core PCE rose 3.4% in May", supported_by=["s1"]),
            Claim(id="c2", text="it was 3.1% in April", supported_by=["s1"]),
        ],
    )


def _request() -> AnalyticsRequest:
    return AnalyticsRequest(id="anx_01", kind="chart", title="PCE trend",
                            question="how is inflation moving?", spec="line chart of PCE y/y",
                            data_refs=["c1", "c2"], rationale="shows the trend")


def _ctx(tmp_path: Path, events: list) -> AgentRunContext:
    writer = ArtifactWriter(tmp_path / "artifacts", run_id="t")
    return AgentRunContext(
        run_id="t", model_resolver=None,  # type: ignore[arg-type]
        emit=lambda et, p=None: events.append((et, p or {})),
        artifacts=writer,
    )


def _good_runner(chart="x,y\nApril,3.1\nMay,3.4\n"):
    """A fake grok that draws a faithful chart from the given data."""
    def run(_prompt: str, folder: Path) -> tuple[bool, str]:
        (folder / "chart.svg").write_text("<svg>PCE</svg>", encoding="utf-8")
        (folder / "data.csv").write_text(chart, encoding="utf-8")
        (folder / "caption.md").write_text("Core PCE ticked up from April to May.", encoding="utf-8")
        return True, "{}"
    return run


def test_produces_artifact_copies_it_out_and_empties_scratch(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    ctx = _ctx(tmp_path, [])
    art = aw.fulfill_request(_request(), _profile(), workspace=ws, context=ctx, runner=_good_runner())

    assert art.status == "produced"
    assert art.figure_check["verified"] is True and art.figure_check["unverified"] == []
    assert art.ai_label and "cited claims c1, c2" in art.caption and "2026-06-30" in art.caption
    # the artifact + its data were copied into the run's artifact store
    assert (tmp_path / "artifacts" / art.artifact_name).exists()
    assert (tmp_path / "artifacts" / art.data_name).exists()
    # the scratch folder is emptied after — the workspace does not accumulate
    assert not (ws / "anx_01").exists()


def test_figure_check_flags_a_number_not_in_the_evidence(tmp_path: Path) -> None:
    # 9.9 is nowhere in the claims/snapshot — the visual analog of unverified_prose_figures.
    art = aw.fulfill_request(_request(), _profile(), workspace=tmp_path / "ws",
                             runner=_good_runner("x,y\nApril,3.1\nMay,9.9\n"))
    assert art.status == "produced"
    assert art.figure_check["verified"] is False and "9.9" in art.figure_check["unverified"]
    assert "9.9" in art.note


def test_skipped_when_worker_declines(tmp_path: Path) -> None:
    def run(_p: str, folder: Path) -> tuple[bool, str]:
        (folder / "SKIPPED.md").write_text("data too thin to plot honestly", encoding="utf-8")
        return True, "{}"
    art = aw.fulfill_request(_request(), _profile(), workspace=tmp_path / "ws", runner=run)
    assert art.status == "skipped" and "too thin" in art.note


def test_sweep_deletes_disallowed_files(tmp_path: Path) -> None:
    def run(_p: str, folder: Path) -> tuple[bool, str]:
        (folder / "chart.svg").write_text("<svg/>", encoding="utf-8")
        (folder / "data.csv").write_text("x,y\nMay,3.4\n", encoding="utf-8")
        (folder / "caption.md").write_text("cap", encoding="utf-8")
        (folder / "sneaky.exe").write_bytes(b"MZ\x00\x00")   # not on the allowlist
        return True, "{}"
    art = aw.fulfill_request(_request(), _profile(), workspace=tmp_path / "ws", runner=run)
    assert art.status == "produced"
    assert any("sneaky.exe" in s for s in art.swept)


def test_no_output_is_a_clean_failure(tmp_path: Path) -> None:
    art = aw.fulfill_request(_request(), _profile(), workspace=tmp_path / "ws",
                             runner=lambda _p, _f: (False, "grok error"))
    assert art.status == "failed" and art.artifact_name == ""


def test_new_escapes_diffs_against_baseline() -> None:
    # only paths that appear DURING the run count — the user's pre-existing dirt is ignored.
    assert aw._new_escapes({"a"}, {"a", "backend/evil.py"}) == ["backend/evil.py"]
    assert aw._new_escapes({"a"}, {"a"}) == []
    assert aw._new_escapes(None, {"x"}) == []   # git unavailable -> tripwire simply doesn't arm


def test_escape_tripwire_fails_loudly_even_on_a_good_chart(tmp_path: Path, monkeypatch) -> None:
    # A good-looking chart from a lane-breaking run is NOT trustworthy: hard fail + loud event.
    seen = iter([set(), {"backend/secrets.py"}])   # before -> after: a new write outside the lane
    monkeypatch.setattr(aw, "_git_status", lambda _root: next(seen))
    events: list = []
    ctx = _ctx(tmp_path, events)
    art = aw.fulfill_request(_request(), _profile(), workspace=tmp_path / "ws",
                             context=ctx, runner=_good_runner())
    assert art.status == "failed" and art.escaped_writes == ["backend/secrets.py"]
    assert any(et == aw.ANALYTICS_WORKER_ESCAPE for et, _ in events)
    assert not (tmp_path / "ws" / "anx_01").exists()   # scratch still emptied


def test_worker_graph_loops_warranted_requests(tmp_path: Path) -> None:
    events: list = []
    plan = AnalyticsPlan(id="analytics_prof_x", profile_id="prof_x", warranted=True, requests=[_request()])
    graph = aw.build_analytics_worker_graph(_ctx(tmp_path, events), runner=_good_runner())
    out = graph.invoke({"analytics_plan": plan.model_dump(), "profile": _profile().model_dump()})

    arts = out["analytics_artifacts"]
    assert len(arts) == 1 and arts[0]["status"] == "produced"
    done = next(p for et, p in events if et == aw.ANALYTICS_WORKER_COMPLETED)
    assert done["produced"] == 1


def test_worker_graph_does_nothing_when_not_warranted(tmp_path: Path) -> None:
    plan = AnalyticsPlan(id="x", warranted=False)
    graph = aw.build_analytics_worker_graph(_ctx(tmp_path, []), runner=_good_runner())
    out = graph.invoke({"analytics_plan": plan.model_dump(), "profile": _profile().model_dump()})
    assert out["analytics_artifacts"] == []
