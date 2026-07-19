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
    # Human-readable provenance only — claim ids stay out of the reader-facing caption.
    assert art.ai_label and "cited claims" not in art.caption and "clm_" not in art.caption
    assert "BLS" in art.caption and "2026-06-30" in art.caption
    # the artifact + its data were copied into the run's artifact store
    assert (tmp_path / "artifacts" / art.artifact_name).exists()
    assert (tmp_path / "artifacts" / art.data_name).exists()
    # the scratch folder is emptied after — the workspace does not accumulate
    assert not (ws / "anx_01").exists()


def test_table_kind_carries_body_md_for_inlining(tmp_path: Path) -> None:
    def run(_p: str, folder: Path) -> tuple[bool, str]:
        (folder / "table.md").write_text("| Outcome | P |\n|--|--|\n| Hold | 3.4 |", encoding="utf-8")
        (folder / "data.csv").write_text("outcome,p\nHold,3.4\n", encoding="utf-8")
        (folder / "caption.md").write_text("the odds", encoding="utf-8")
        return True, "{}"
    req = _request().model_copy(update={"kind": "table"})
    art = aw.fulfill_request(req, _profile(), workspace=tmp_path / "ws", runner=run)
    assert art.status == "produced" and art.artifact_name.endswith(".md")
    assert "| Outcome | P |" in art.body_md          # the markdown body travels for the publish view


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


def test_store_escapes_catches_new_and_modified_files() -> None:
    # git status can't see gitignored stores; this fingerprint diff is the complement.
    before = {"p/prof_a.json": (100, 10)}
    after = {"p/prof_a.json": (200, 10),   # same size, newer mtime -> a silent overwrite
             "p/prof_b.json": (50, 5)}     # a brand-new file
    assert aw._store_escapes(before, after) == ["p/prof_a.json", "p/prof_b.json"]
    assert aw._store_escapes(before, before) == []   # unchanged -> nothing


def test_store_fingerprint_covers_stores_and_env(tmp_path: Path) -> None:
    (tmp_path / "backend" / "profile_store").mkdir(parents=True)
    (tmp_path / "backend" / "profile_store" / "p.json").write_text("{}", encoding="utf-8")
    (tmp_path / ".env").write_text("SECRET=1", encoding="utf-8")   # the classic escape target
    fp = aw._store_fingerprint(tmp_path)
    assert any("p.json" in k for k in fp)
    assert any(k.endswith(".env") for k in fp)   # .env is fingerprinted (metadata only, never read)


def test_tripwire_catches_a_poisoned_store_json(tmp_path: Path, monkeypatch) -> None:
    # A worker that overwrites a gitignored profile JSON must be caught even though git is clean.
    monkeypatch.setattr(aw, "_git_status", lambda _root: set())   # git sees nothing (ignored path)
    fps = iter([{}, {"backend/profile_store/prof_x.json": (1, 2)}])   # before -> after: a new write
    monkeypatch.setattr(aw, "_store_fingerprint", lambda _root: next(fps))
    events: list = []
    art = aw.fulfill_request(_request(), _profile(), workspace=tmp_path / "ws",
                             context=_ctx(tmp_path, events), runner=_good_runner())
    assert art.status == "failed" and "prof_x.json" in art.escaped_writes[0]
    assert any(et == aw.ANALYTICS_WORKER_ESCAPE for et, _ in events)


def test_worker_graph_loops_warranted_requests(tmp_path: Path) -> None:
    events: list = []
    plan = AnalyticsPlan(id="analytics_prof_x", profile_id="prof_x", warranted=True, requests=[_request()])
    graph = aw.build_analytics_worker_graph(_ctx(tmp_path, events), runner=_good_runner(), refresh=False)
    out = graph.invoke({"analytics_plan": plan.model_dump(), "profile": _profile().model_dump()})

    arts = out["analytics_artifacts"]
    assert len(arts) == 1 and arts[0]["status"] == "produced"
    done = next(p for et, p in events if et == aw.ANALYTICS_WORKER_COMPLETED)
    assert done["produced"] == 1


def test_sweep_removes_orphaned_scratch_but_spares_a_live_one(tmp_path: Path) -> None:
    # A killed run can't empty its own scratch (the finally never runs), so the workspace
    # accumulates dead folders. Age-gating is what makes the sweep safe under concurrency.
    import os
    import time as _t

    ws = tmp_path / "ws"
    (ws / "req_dead").mkdir(parents=True)
    (ws / "req_dead" / "chart.svg").write_text("<svg/>", encoding="utf-8")
    (ws / "req_live").mkdir()
    old = _t.time() - (5 * 60 * 60)
    os.utime(ws / "req_dead", (old, old))          # hours old -> its run is gone

    cleaned = aw.sweep_stale_scratch(ws)
    assert cleaned == ["req_dead"] and not (ws / "req_dead").exists()
    assert (ws / "req_live").exists()               # a concurrent run's live scratch is untouched


def test_sweep_is_a_noop_on_a_clean_workspace(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "AGENTS.md").write_text("doctrine", encoding="utf-8")
    assert aw.sweep_stale_scratch(ws) == [] and (ws / "AGENTS.md").exists()   # files are never touched


def test_canary_passes_when_the_harness_draws(tmp_path: Path) -> None:
    ok, note = aw.canary(tmp_path / "ws", runner=_good_runner())
    assert ok and note == "canary ok"
    assert not (tmp_path / "ws" / "_canary").exists()   # scratch cleaned even on the canary


def test_canary_fails_when_the_harness_draws_nothing(tmp_path: Path) -> None:
    ok, note = aw.canary(tmp_path / "ws", runner=lambda _p, _f: (True, "{}"))   # ran, drew nothing
    assert not ok and "no chart" in note


def test_a_failed_canary_skips_analytics_without_breaking_the_article(tmp_path: Path, monkeypatch) -> None:
    # The property that makes always-updating affordable: a bad harness release costs this run's
    # visuals and SAYS SO — it never blocks the piece.
    monkeypatch.setattr(aw, "update_grok", lambda: "updated to 9.9.9")
    monkeypatch.setattr(aw, "grok_version", lambda: "grok 9.9.9")
    monkeypatch.setattr(aw, "canary", lambda _ws, runner=None: (False, "canary produced no chart"))
    events: list = []
    plan = AnalyticsPlan(id="x", profile_id="prof_x", warranted=True, requests=[_request()])
    graph = aw.build_analytics_worker_graph(_ctx(tmp_path, events), runner=_good_runner(), refresh=True)
    out = graph.invoke({"analytics_plan": plan.model_dump(), "profile": _profile().model_dump()})

    assert out["analytics_artifacts"] == []            # degraded, not crashed
    done = next(p for et, p in events if et == aw.ANALYTICS_WORKER_COMPLETED)
    assert "analytics skipped" in done["note"] and "9.9.9" in done["note"]   # and it says why
    ready = next(p for et, p in events if et == aw.ANALYTICS_WORKER_READY)
    assert ready["version"] == "grok 9.9.9"            # version stamped even on the failure path


def test_produced_artifact_is_version_stamped(tmp_path: Path) -> None:
    art = aw.fulfill_request(_request(), _profile(), workspace=tmp_path / "ws",
                             runner=_good_runner(), version="grok 0.2.63 (2ade4617f)")
    assert art.model == "grok 0.2.63 (2ade4617f)"      # provenance: which tool drew this


def test_worker_graph_does_nothing_when_not_warranted(tmp_path: Path) -> None:
    plan = AnalyticsPlan(id="x", warranted=False)
    graph = aw.build_analytics_worker_graph(_ctx(tmp_path, []), runner=_good_runner(), refresh=False)
    out = graph.invoke({"analytics_plan": plan.model_dump(), "profile": _profile().model_dump()})
    assert out["analytics_artifacts"] == []
